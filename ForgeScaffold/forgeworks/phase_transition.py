"""
ForgeWorks Phase Transition Helper
====================================
Enforces the sequential model lifecycle contract:

    UNLOAD current model → LOAD next model → RUN phase → collect artifacts

This is the missing piece the AI Dev needs. The root problem is:

    ❌ WRONG (what causes the stall):
        Phase 1 loads reasoning_model (32B DeepSeek) → starts generating
        Phase 3 loads code_model (8B Qwen) — WHILE 32B IS STILL IN VRAM
        → Both models fight for GPU memory → 8B starves → /api/generate hangs

    ✅ CORRECT (this module enforces):
        Phase 1 loads reasoning_model (32B) → generates → unloads 32B
        Phase 3 loads code_model (8B) → only 8B in VRAM → generates cleanly

Usage in sam_like_runner.py:

    from forgeworks.runner.phase_transition import PhaseTransitionController

    controller = PhaseTransitionController()

    with controller.transition(from_phase=None, to_phase=1, ticket_id=ticket_id):
        run_scout(baton, work_dir)

    with controller.transition(from_phase=1, to_phase=2, ticket_id=ticket_id):
        run_legislator(baton, work_dir)

    with controller.transition(from_phase=2, to_phase=3, ticket_id=ticket_id):
        run_builder(baton, work_dir)

    # Phases 4 and 5 (Judge, Deployer) do NOT call the LLM — no model needed.
    run_judge(baton, work_dir)
    run_deployer(baton, work_dir)
"""

import logging
import requests
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase → model role mapping
# ---------------------------------------------------------------------------
# Which model role does each phase require?
# Phases 4 (Judge) and 5 (Deployer) use subprocess/ForgeGate, not the LLM.

PHASE_MODEL_ROLE = {
    1: "reasoning",   # Scout    — analyse the ticket, produce ValidatedHypothesis
    2: "reasoning",   # Legislator — produce SpecContract (also a reasoning task)
    3: "code",        # Builder  — write code, produce artifacts
    # 4: Judge     — no LLM (runs subprocess test_script.py via ForgeGate)
    # 5: Deployer  — no LLM (copies verified artifacts via ForgeGate)
}


class PhaseTransitionController:
    """
    Manages sequential model lifecycle across phase boundaries.

    Key contract:
        1. Before entering any LLM phase, unload the currently active model.
        2. Load only the model required for the next phase.
        3. After the phase completes (or errors), unload that model.
        4. Never let two models share VRAM simultaneously.

    This controller reads models.conf to determine which Ollama model name
    corresponds to each role (reasoning, code, general).
    """

    def __init__(self, api_url: str = "http://localhost:11434"):
        self._config: Optional[dict] = None
        self._active_model: Optional[str] = None
        self.api_url = api_url
        self._load_config()

    def _load_config(self) -> None:
        """Read models.conf once at construction time."""
        try:
            from forgeworks.core_engines.config.model_config_manager import get_model_config_manager
            mgr = get_model_config_manager()
            self._config = mgr.load_config()
            self.api_url = self._config.get("api_url", self.api_url)
            logger.info(
                f"⚙️  PhaseTransitionController loaded config — "
                f"reasoning={self._config.get('reasoning_model')}, "
                f"code={self._config.get('code_model')}"
            )
        except Exception as e:
            logger.warning(f"Could not load models.conf ({e}). Using defaults.")
            self._config = {}

    def model_for_phase(self, phase: int) -> Optional[str]:
        """Return the Ollama model name required for the given phase number."""
        role = PHASE_MODEL_ROLE.get(phase)
        if role is None:
            return None  # Phase 4/5 need no model
        key = f"{role}_model"
        name = self._config.get(key, "").strip('"')
        if not name:
            logger.warning(f"Phase {phase} wants role '{role}' but no '{key}' set in models.conf")
        return name or None

    # ------------------------------------------------------------------
    # Ollama API helpers
    # ------------------------------------------------------------------

    def _unload(self, model_name: str) -> bool:
        """
        Unload a model from Ollama VRAM by sending keep_alive=0.
        Returns True on success or if model was already unloaded.
        """
        if not model_name:
            return True
        try:
            # Check if actually loaded first — avoids pointless 404s
            ps = requests.get(f"{self.api_url}/api/ps", timeout=5)
            if ps.status_code == 200:
                running = [m.get("name") for m in ps.json().get("models", [])]
                if model_name not in running:
                    logger.info(f"ℹ️  {model_name} not in VRAM — skip unload")
                    return True

            logger.info(f"🔻 Unloading {model_name} from VRAM...")
            resp = requests.post(
                f"{self.api_url}/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": 0, "stream": False},
                timeout=30,
            )
            if resp.status_code in (200, 404):
                logger.info(f"✅ {model_name} unloaded (or was already gone)")
                return True
            logger.warning(f"⚠️  Unload returned {resp.status_code} for {model_name}")
            return False
        except Exception as exc:
            logger.warning(f"⚠️  Unload call failed for {model_name}: {exc}")
            return False

    def _verify_only_one_loaded(self) -> None:
        """Log a warning if more than one model is currently in VRAM."""
        try:
            ps = requests.get(f"{self.api_url}/api/ps", timeout=5)
            if ps.status_code == 200:
                loaded = ps.json().get("models", [])
                names = [m.get("name") for m in loaded]
                if len(names) > 1:
                    logger.warning(
                        f"⚠️  GPU CONTENTION: {len(names)} models in VRAM simultaneously: {names}. "
                        "This will starve inference. Unloading all except the active phase model."
                    )
                    # Force-unload everything except the one we just loaded
                    for name in names:
                        if name != self._active_model:
                            self._unload(name)
                else:
                    logger.info(f"✅ VRAM clean — only {names} loaded")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Context manager for phase transitions
    # ------------------------------------------------------------------

    @contextmanager
    def transition(self, from_phase: Optional[int], to_phase: int, ticket_id: str = ""):
        """
        Context manager that performs the unload-load handoff at phase boundaries.

        Usage:
            with controller.transition(from_phase=1, to_phase=2, ticket_id="CI-001"):
                run_legislator(baton, work_dir)

        On entry:
            - Unloads the model used by from_phase (if any)
            - Loads the model required for to_phase (if any)
            - Verifies only one model is in VRAM
        On exit (success or error):
            - Unloads the model used by to_phase to keep VRAM clean
        """
        next_model = self.model_for_phase(to_phase)
        prev_model = self.model_for_phase(from_phase) if from_phase is not None else self._active_model

        tag = f"[ticket={ticket_id} phase={from_phase}→{to_phase}]"
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 PHASE TRANSITION {tag}")
        logger.info(f"   Unloading: {prev_model or 'none'}")
        logger.info(f"   Loading:   {next_model or 'none (non-LLM phase)'}")
        logger.info(f"{'='*60}")

        # Step 1: Unload previous model
        if prev_model and prev_model != next_model:
            self._unload(prev_model)

        # Step 2: Skip warm-up. Phase model calls will stream and load on demand.
        self._active_model = next_model

        # Step 3: Safety check — should be exactly one model in VRAM
        if next_model:
            self._verify_only_one_loaded()

        try:
            yield  # ← caller's phase code runs here
        finally:
            # Step 4: Unload the phase model after work is done (keep VRAM clean)
            if next_model:
                logger.info(f"🔻 Phase {to_phase} complete — unloading {next_model}")
                self._unload(next_model)
                self._active_model = None


# ---------------------------------------------------------------------------
# Convenience: pre-flight VRAM check
# ---------------------------------------------------------------------------

def assert_vram_clear(api_url: str = "http://localhost:11434") -> None:
    """
    Call at the start of run_workcell() to ensure VRAM is clear before
    beginning a ticket run. Raises RuntimeError if models are still loaded.

    Use this as a pre-flight gate instead of manually stopping models.
    """
    try:
        ps = requests.get(f"{api_url}/api/ps", timeout=5)
        if ps.status_code == 200:
            loaded = [m.get("name") for m in ps.json().get("models", [])]
            if loaded:
                logger.warning(f"⚠️  VRAM PRE-FLIGHT: {loaded} are still loaded. Unloading...")
                for model in loaded:
                    requests.post(
                        f"{api_url}/api/generate",
                        json={"model": model, "prompt": "", "keep_alive": 0, "stream": False},
                        timeout=30,
                    )
                logger.info("✅ VRAM cleared. Ready to begin ticket run.")
    except Exception as exc:
        logger.warning(f"Pre-flight VRAM check could not reach Ollama: {exc}")

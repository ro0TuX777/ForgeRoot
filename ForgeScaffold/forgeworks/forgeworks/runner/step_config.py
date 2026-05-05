"""
ForgeWorks Step Configuration
==============================
Declarative per-phase error handling and execution mode, inspired by
OpenFang's StepMode/ErrorMode pattern.

Instead of hardcoding retry logic in sam_like_runner.py, each phase
declares its own behaviour via PHASE_CONFIG. The runner reads this to
decide what to do on success, skip, or repeated failure.

Execution contract:
    ErrorMode.FAIL   — abort the ticket run immediately on exception
    ErrorMode.SKIP   — log the error, mark phase as skipped, continue
    ErrorMode.RETRY  — retry up to max_retries times before FAIL

StepMode is reserved for future fan-out/parallel phases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StepMode(Enum):
    """Execution mode for a workflow phase."""
    SEQUENTIAL  = "sequential"   # default — one after another (current behaviour)
    # Future: FAN_OUT / COLLECT for parallel sub-agents


class ErrorMode(Enum):
    """What to do when a phase raises an unhandled exception."""
    FAIL  = "fail"   # abort the ticket run (default — safe)
    SKIP  = "skip"   # log + skip this phase, continue to next
    RETRY = "retry"  # retry up to max_retries times, then FAIL


@dataclass
class PhaseConfig:
    """Configuration for a single pipeline phase."""
    phase_num:   int
    phase_name:  str
    action_id:   str
    step_mode:   StepMode  = StepMode.SEQUENTIAL
    error_mode:  ErrorMode = ErrorMode.FAIL
    max_retries: int       = 0   # only meaningful when error_mode == RETRY
    uses_llm:    bool      = True   # False for Judge and Deployer (no model needed)


# ---------------------------------------------------------------------------
# Canonical phase pipeline — single source of truth for the runner
# ---------------------------------------------------------------------------
PHASE_PIPELINE: list[PhaseConfig] = [
    PhaseConfig(
        phase_num=1,
        phase_name="Scout",
        action_id="phase.scout",
        error_mode=ErrorMode.RETRY,
        max_retries=2,         # Scout can transiently fail on Ollama hiccups
        uses_llm=True,
    ),
    PhaseConfig(
        phase_num=2,
        phase_name="Legislator",
        action_id="phase.legislator",
        error_mode=ErrorMode.RETRY,
        max_retries=2,
        uses_llm=True,
    ),
    PhaseConfig(
        phase_num=3,
        phase_name="Builder",
        action_id="phase.builder",
        error_mode=ErrorMode.RETRY,
        max_retries=3,         # Builder retries are driven by Judge; this covers exceptions
        uses_llm=True,
    ),
    PhaseConfig(
        phase_num=4,
        phase_name="Judge",
        action_id="execute_sandbox_test",
        error_mode=ErrorMode.FAIL,  # Judge failures are structural — don't silently skip
        uses_llm=False,
    ),
    PhaseConfig(
        phase_num=5,
        phase_name="Deployer",
        action_id="deploy_verified_artifact",
        error_mode=ErrorMode.FAIL,
        uses_llm=False,
    ),
]

# Fast lookup by phase number
PHASE_CONFIG: dict[int, PhaseConfig] = {p.phase_num: p for p in PHASE_PIPELINE}
# Fast lookup by phase name
PHASE_CONFIG_BY_NAME: dict[str, PhaseConfig] = {p.phase_name: p for p in PHASE_PIPELINE}

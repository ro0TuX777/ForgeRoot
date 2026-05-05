# ForgeWorks Model Lifecycle — Sequential Phase Contract

## The Problem Being Solved

The AI Dev observed this in logs:
```
ollama ps → reasoning_model (32B) + code_model (8B) both loaded → GPU 100%
→ /api/generate for 8B hangs indefinitely
```

**Why it happens**: The phases each lazy-load their model on first call, but never
unload the previous one. Both models compete for VRAM, the smaller one starves.

---

## The Correct Sequential Lifecycle

Each phase uses **one model**. When the phase completes, that model is unloaded
before the next phase's model loads. Only ONE model is ever in VRAM at a time.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Ticket Lifecycle: Sequential Model Handoff                               │
├──────────────┬──────────────────────────┬────────────────────────────── │
│ Phase        │ Model Role               │ Action                         │
├──────────────┼──────────────────────────┼────────────────────────────── │
│ [pre-flight] │ —                        │ assert_vram_clear()            │
│ Phase 1      │ reasoning_model (32B)    │ LOAD → Scout → save artifacts  │
│              │                          │ UNLOAD 32B                     │
│ Phase 2      │ reasoning_model (32B)    │ LOAD → Legislator → save spec  │
│              │                          │ UNLOAD 32B                     │
│ Phase 3      │ code_model (8B Qwen)     │ LOAD → Builder → write code    │
│              │                          │ UNLOAD 8B                      │
│ Phase 4      │ — (no LLM)              │ Judge runs subprocess test      │
│ Phase 5      │ — (no LLM)              │ Deployer copies verified files  │
└──────────────┴──────────────────────────┴────────────────────────────── ┘
```

Phases 4 (Judge) and 5 (Deployer) are **compute-free** — they call `subprocess`
and `shutil.copy2`. No model loading at all.

---

## How to Use PhaseTransitionController

```python
from forgeworks.runner.phase_transition import PhaseTransitionController, assert_vram_clear
from forgeworks.runner.phases import run_scout, run_legislator, run_builder, run_judge, run_deployer
from forgeworks.runner.tokio_baton import RelayBaton

# 1. Pre-flight: ensure VRAM is clean before starting any ticket
assert_vram_clear()

# 2. Create the controller (reads models.conf once)
controller = PhaseTransitionController()

# 3. Create a baton per ticket
baton = RelayBaton(ticket_id="CI-001", ticket_intent="Fix failing test: test_auth_login")
work_dir = Path("work/CI-001")
work_dir.mkdir(parents=True, exist_ok=True)

# 4. Run phases — controller handles UNLOAD → LOAD at each boundary
with controller.transition(from_phase=None, to_phase=1, ticket_id=baton.ticket_id):
    run_scout(baton, str(work_dir))

with controller.transition(from_phase=1, to_phase=2, ticket_id=baton.ticket_id):
    run_legislator(baton, str(work_dir))

with controller.transition(from_phase=2, to_phase=3, ticket_id=baton.ticket_id):
    run_builder(baton, str(work_dir))

# Phases 4 and 5: no transition needed — they don't use the LLM
run_judge(baton, str(work_dir))

# Check baton state after Judge (it may loop back to Builder on failure)
if baton.current_phase == 3:
    with controller.transition(from_phase=None, to_phase=3, ticket_id=baton.ticket_id):
        run_builder(baton, str(work_dir))      # retry with error log injected
    run_judge(baton, str(work_dir))

if baton.current_phase == 5:
    run_deployer(baton, str(work_dir))
```

---

## What `transition()` Does Internally

```
on entry:
  1. Unload from_phase model (POST /api/generate keep_alive=0)
  2. Load to_phase model   (POST /api/generate keep_alive=-1, empty prompt)
  3. Check GET /api/ps — if >1 model in VRAM, force-unload all extras

on exit (even on exception):
  4. Unload to_phase model (keeps VRAM clean for next transition)
```

The `keep_alive=-1` warm-up on entry ensures the model is fully resident in VRAM
before the phase starts generating, eliminating cold-start latency during inference.

---

## Key Files

| File | Purpose |
|---|---|
| `runner/phase_transition.py` | `PhaseTransitionController` + `assert_vram_clear()` |
| `core_engines/config/model_config_manager.py` | `unload_model()` — sends `keep_alive=0` to Ollama |
| `core_engines/integration/model_manager_integration.py` | `switch_model(unload_previous=True)` — in-process thread lock |
| `core_engines/config/models.conf` | Maps roles to Ollama model names |

---

## Key models.conf Fields

```ini
[llm_model]
provider = ollama
api_url = http://localhost:11434
reasoning_model = hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_M  ; Phase 1 + 2
code_model = qwen2.5-coder:7b                                               ; Phase 3
general_model = llama3.2:3b                                                 ; fallback
smart_selection = false   ; MUST BE false to force role-based routing
```

> [!IMPORTANT]
> `smart_selection = false` is required. When `true`, SmartModelSelector picks
> the model based on content heuristics — it may pick the wrong model for a phase.
> Role-based routing (reasoning/code/general) must be explicit for the sequential
> lifecycle to work correctly.

---

## Debugging VRAM Contention

If you see the `/api/generate` hang again, run this to inspect what's in VRAM:

```bash
curl http://localhost:11434/api/ps | python3 -m json.tool
```

Expected output during a clean phase run (one model at a time):
```json
{
  "models": [
    { "name": "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_M", ... }
  ]
}
```

If you see two models listed — call `assert_vram_clear()` and restart the run.

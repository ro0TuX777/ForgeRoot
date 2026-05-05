# SPEC-02_AZUL_COCKPIT_BLUEPRINT

## Goal
Build the Streamlit-based "Glass Box" for the Federation Leads.

## 1. The "Ignition" Sidebar
- Warden Toggle: A switch to start/stop the Background Daemon.
- Visuals: Green (Running), Yellow (Stopped), Red (Error/Blocked).
- Model Selector: Dropdown menus for Local Engine and Frontier Engine.
- Project Context: Input field for `PROJECT_ROOT` (defaults to `.env`).

## 2. Main Dashboard Layout
### Tab 1: Tactical Map (Progress)
- Visual "Progress Ribbon": Scan -> Assess -> Contract -> Verify.
- Risk Heatmap: Renders `danger_map.json` into a visual grid of the codebase.

### Tab 2: The Warden's Desk (Approvals)
- Display `action_catalogs/stubs/*.yaml`.
- A "Vibe Check" button that moves approved YAMLs to `action_catalogs/active/`.

### Tab 3: XP Scoreboard (Value)
- Live feed of `XP_LEDGER.jsonl`.
- Metrics: "Security Catastrophes Blocked" (Count of REJECT verdicts).

## 3. Hang-up Monitoring
A dedicated notification area for `status=FAILED`. It must display the traceback from the failed Shadow-Run so the Lead Architect can fix the "Friction" immediately.

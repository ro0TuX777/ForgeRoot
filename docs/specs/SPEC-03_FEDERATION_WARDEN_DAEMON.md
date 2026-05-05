# SPEC-03_FEDERATION_WARDEN_DAEMON

## Goal
Implement the background service that automates the "Volume" work.

## 1. The Background Loop
- Trigger: The Cockpit UI toggles the daemon.
- Process: A Python process that watches `PROJECT_ROOT` for file changes.
- Orchestration:
  - On change: Trigger `scripts/forge-scan`.
  - If new risks detected: Trigger `scripts/forge-assess`.
  - If a risk has no contract: Use vLLM to generate a Contract Stub in `action_catalogs/stubs/`.

## 2. The File-Move Logic
- Strict Registry Pathing:
  - Generated Stubs: `/Users/vinsoncornejo/ForgedRoot/action_catalogs/stubs/`
  - Active Contracts: `/Users/vinsoncornejo/ForgedRoot/action_catalogs/active/`
- Human-in-the-loop: The Warden never moves a stub to active. Only the human clicking the button in the Cockpit can perform the `shutil.move` operation.

## 3. CONCORD Integration
- The Warden must update the `danger_map.json` after every scan.
- It must flag any "Unit" that has a `risk_tag` but no corresponding YAML in `active/`.

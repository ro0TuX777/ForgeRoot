# ForgeScaffold Phase 1 Architecture

ForgeScaffold is a DAWN-native blueprint runner that materializes a deterministic supply chain for monoliths, service meshes, and agent-based systems. Phase 1 stitches three purpose-built links into a single pipeline:

1. **ingest.project_bundle** (DAWN stock link) collects the workspace snapshot.
2. **forgescaffold.system_catalog** enumerates units (modules, services, agent steps, datastores, and external dependencies) using path heuristics, service manifests, and dependency manifests.
3. **forgescaffold.map_dataflow** synthesizes edges (`imports`, `http`, `event`, `reads`, `writes`, `spawns`, `retrieves`) by combining AST-driven import tracking with configuration and keyword detection.
4. **forgescaffold.test_matrix** spins up a level-based checklist (L0-L3) per unit, referencing the generated catalog and dataflow map.

Each link is deterministic, sandbox-safe, and registers outputs through DAWN’s artifact store. Running `scripts/verify_forgescaffold_phase1.py` reuses the same pipeline and asserts artifact/digest stability, ledger traceability, and rerun determinism.

Heuristics are intentionally pragmatic: package names map to `module` units, compose/k8s manifests become `service` units, filesystem folders such as `agents/` or `flows/` seed `agent_step` units, and dependency files (`requirements.txt`, `package.json`, `pyproject.toml`) spawn `external_dependency` units.

This architecture keeps the blueprint portable: a single schema governs the catalog, dataflow, and test matrix so monolith, mesh, and agent codebases can reuse the same artifact/contract/gate pattern.

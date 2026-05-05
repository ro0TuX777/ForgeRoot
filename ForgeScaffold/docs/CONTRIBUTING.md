# Contributing to ForgeScaffold Phase 1

Follow these rules to keep the blueprint deterministic and auditable:

1. **Update contracts when logic changes:** Any change that affects the schema, link behavior, or verifier must include an update to one of the following:
   - A schema file in `dawn_extensions/schemas/`
   - A link contract (`link.yaml`) or runtime hook (`run.py`)
   - `scripts/verify_forgescaffold_phase1.py`
   - Documentation in `docs/`
2. **Run the verifier after edits:** Execute `python3 scripts/verify_forgescaffold_phase1.py --project <existing-project-id>` to ensure artifacts, ledger events, and rerun determinism still hold.
3. **Keep outputs deterministic:** Avoid timestamps, use sorted collections, and reuse DAWN’s artifact store APIs (`sandbox.publish`, `publish_text`).
4. **Document heuristics:** If you introduce a new unit type or edge category, document the heuristic in `docs/ARCHITECTURE.md` and update the relevant schema.
5. **CI expectations:** Every PR must touch at least one schema, link contract, verifier, or documentation file and ensure the pipeline verification can run end-to-end.

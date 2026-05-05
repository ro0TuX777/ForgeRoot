# ForgeScaffold Phase 1 Artifacts

| Artifact ID | File | Description | Schema |
| --- | --- | --- | --- |
| `forgescaffold.system_catalog.json` | `system_catalog.json` | Structured catalog of discovered units (modules, services, agent steps, datastores, external dependencies) with owner/risk metadata. | `dawn_extensions/schemas/system_catalog.schema.json` |
| `forgescaffold.dataflow_map.json` | `dataflow_map.json` | Graph edges between catalog units, covering `imports`, `http`, `grpc`, `event`, `reads`, `writes`, `spawns`, and `retrieves` flows plus node metadata. | `dawn_extensions/schemas/dataflow_map.schema.json` |
| `forgescaffold.test_matrix.yaml` | `test_matrix.yaml` | YAML matrix listing success criteria and level-based commands (L0–L3) per unit; ensures every cataloged node has contract/integration/smoke/non-functional intents. | `dawn_extensions/schemas/test_matrix.schema.json` |

All artifacts are produced under the DAWN artifact store (`artifacts/<link_id>/…`), registered in `artifact_index.json`, and validated against their JSON Schema definitions. The verifier script also ensures the ledger emits start/complete events and rerun digests remain stable.

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def register_schema(schema_name: str, schema_path: Path) -> None:
    try:
        from dawn.runtime import schemas as runtime_schemas
    except ImportError:
        return

    if schema_name in runtime_schemas.SCHEMA_REGISTRY:
        return

    if not schema_path.exists():
        return

    with schema_path.open("r") as fh:
        schema_data = json.load(fh)

    runtime_schemas.SCHEMA_REGISTRY[schema_name] = schema_data


def _load_artifact(artifact_store, artifact_id: str) -> Dict[str, Any]:
    meta = artifact_store.get(artifact_id)
    if not meta:
        raise RuntimeError(f"Missing required artifact: {artifact_id}")
    with open(meta["path"], "r") as fh:
        return json.load(fh)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _logger_wrapper_content() -> str:
    return """import json
import time


def log_event(**kwargs):
    payload = {
        "schema_version": "1.0.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "severity": kwargs.get("severity", "INFO"),
        "run_id": kwargs.get("run_id", "unknown"),
        "unit_id": kwargs.get("unit_id", "unknown"),
        "operation": kwargs.get("operation", "operation"),
        "result": kwargs.get("result", "ok"),
        "duration_ms": kwargs.get("duration_ms"),
        "message": kwargs.get("message"),
    }
    print(json.dumps(payload, sort_keys=True))
"""


def _build_modify_op(path: str, unit_id: str, anchor_line: str, indent: str) -> Dict[str, Any]:
    content = (
        f"{indent}from forgescaffold_logging import log_event\n"
        f"{indent}log_event(unit_id=\"{unit_id}\", operation=\"entrypoint\", result=\"ok\")\n"
    )
    return {
        "op": "modify",
        "path": path,
        "reason": "Insert minimal entrypoint logging",
        "unit_id": unit_id,
        "tags": ["observability", "entrypoint"],
        "patch": [
            {
                "anchor": {
                    "type": "literal",
                    "value": anchor_line,
                    "occurrence": 1,
                },
                "action": "insert_after",
                "content": content,
            }
        ],
        "safety": {"risk": "low", "reversible": True, "apply_guard": "profile=dev"},
    }


def _detect_entrypoint_patch(file_path: Path, unit_id: str) -> Optional[Dict[str, Any]]:
    try:
        content = file_path.read_text()
    except Exception:
        return None

    if "forgescaffold_logging" in content:
        return None

    anchor_candidates = ["if __name__ == \"__main__\":", "if __name__ == '__main__':"]
    for anchor in anchor_candidates:
        if anchor in content:
            return _build_modify_op(file_path.as_posix(), unit_id, anchor, "    ")

    return None


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    artifact_store = project_context.get("artifact_store")
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not artifact_store or not sandbox:
        raise RuntimeError("Sandbox or artifact store missing")

    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "instrumentation.patchset.schema.json"
    register_schema("forgescaffold.instrumentation.patchset", schema_path)

    catalog = _load_artifact(artifact_store, "forgescaffold.system_catalog.json")
    _load_artifact(artifact_store, "forgescaffold.dataflow_map.json")
    bundle = _load_artifact(artifact_store, "dawn.project.bundle")

    units = catalog.get("units", [])
    languages = sorted({unit.get("language") for unit in units if unit.get("language")})
    operations: List[Dict[str, Any]] = []

    python_units = [unit for unit in units if unit.get("language") == "python"]
    if python_units:
        wrapper_path = "src/forgescaffold_logging.py"
        wrapper_content = _logger_wrapper_content()
        operations.append({
            "op": "add",
            "path": wrapper_path,
            "reason": "Add minimal JSON logger wrapper for instrumentation",
            "tags": ["observability", "logger"],
            "content": wrapper_content,
            "content_sha256": _sha256_text(wrapper_content),
            "safety": {"risk": "low", "reversible": True, "apply_guard": "profile=dev"},
        })

        for unit in python_units:
            entry = unit.get("entrypoint") or unit.get("path")
            if not entry or not str(entry).endswith(".py"):
                continue
            path = project_root / entry
            if not path.exists():
                continue
            patch = _detect_entrypoint_patch(path, unit.get("id", "unknown"))
            if patch:
                operations.append(patch)

    if not operations:
        placeholder_content = "# No instrumentation operations generated for this project."
        operations.append({
            "op": "add",
            "path": "forgescaffold/NO_OP_INSTRUMENTATION.md",
            "reason": "Fallback when no language targets were detected",
            "tags": ["observability", "noop"],
            "content": placeholder_content,
            "content_sha256": _sha256_text(placeholder_content),
            "safety": {"risk": "low", "reversible": True, "apply_guard": "profile=dev"},
        })

    operations = sorted(operations, key=lambda op: op["path"])

    bundle_content_sha256 = bundle.get("bundle_content_sha256")

    patchset = {
        "schema_version": "1.0.1",
        "patchset_id": _sha256_text(json.dumps(operations, sort_keys=True)),
        "generator": {
            "name": "forgescaffold.obs_instrument_patchset",
            "version": "1.0.0",
        },
        "target": {
            "project_id": project_context.get("project_id"),
            "bundle_content_sha256": bundle_content_sha256 or "",
            "root_dir": ".",
            "language_hints": languages,
        },
        "intent": {
            "category": "observability_instrumentation",
            "scope": "generate_only",
            "constraints": [
                "instrumentation_only",
                "no_core_logic_changes",
                "no_network_calls",
            ],
        },
        "requires": {
            "artifacts": [
                "forgescaffold.system_catalog.json",
                "forgescaffold.dataflow_map.json",
                "forgescaffold.log_envelope.schema.json",
            ]
        },
        "operations": operations,
        "ext": {},
    }

    patchset_path = sandbox.publish(
        "forgescaffold.instrumentation.patchset.json",
        "instrumentation.patchset.json",
        patchset,
        schema="forgescaffold.instrumentation.patchset",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.instrumentation.patchset.json": {"path": patchset_path}},
        "metrics": {"operations": len(operations)},
    }

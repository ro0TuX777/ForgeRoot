import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft202012Validator


class RegistryError(Exception):
    pass


def _registry_root(base: str) -> Path:
    return Path(base) / "registry"


def _manifest_path(base: str) -> Path:
    return _registry_root(base) / "manifest.json"


def _load_schema(name: str) -> Dict[str, Any]:
    base = Path(__file__).resolve().parents[1] / "schemas"
    return json.loads((base / name).read_text())


def _validate(payload: Dict[str, Any], schema_name: str) -> None:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msg = "; ".join([f"{'.'.join([str(p) for p in e.path])}: {e.message}" for e in errors])
        raise RegistryError(f"schema validation failed for {schema_name}: {msg}")


def _load_manifest(base: str) -> Dict[str, Any]:
    path = _manifest_path(base)
    if not path.exists():
        return {"schema_version": "0.1", "intents": [], "history": []}
    return json.loads(path.read_text())


def _write_manifest(base: str, manifest: Dict[str, Any]) -> None:
    path = _manifest_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_intents = sorted(manifest.get("intents", []), key=lambda x: x.get("intent_id", ""))
    ordered_history = manifest.get("history", [])
    data = {"schema_version": "0.1", "intents": ordered_intents, "history": ordered_history}
    _validate(data, "registry_manifest.v0_1.json")
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))


def registry_add(base: str, bundle_path: str, intent_id: str, intent_version: str) -> None:
    registry_root = _registry_root(base)
    dest = registry_root / "intents" / intent_id / intent_version / "IntentBundle"
    if dest.exists():
        raise RegistryError("intent bundle already exists in registry")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_path, dest)

    manifest = _load_manifest(base)
    intents = manifest.get("intents", [])
    entry = next((i for i in intents if i.get("intent_id") == intent_id), None)
    if not entry:
        entry = {"intent_id": intent_id, "active_version": None, "versions": []}
        intents.append(entry)
    if intent_version not in entry["versions"]:
        entry["versions"].append(intent_version)
        entry["versions"] = sorted(entry["versions"])
    manifest["intents"] = intents
    _write_manifest(base, manifest)


def registry_list(base: str) -> Dict[str, Any]:
    manifest = _load_manifest(base)
    _validate(manifest, "registry_manifest.v0_1.json")
    return manifest


def registry_promote(base: str, intent_id: str, intent_version: str) -> None:
    manifest = _load_manifest(base)
    intents = manifest.get("intents", [])
    entry = next((i for i in intents if i.get("intent_id") == intent_id), None)
    if not entry or intent_version not in entry.get("versions", []):
        raise RegistryError("intent version not found")
    entry["active_version"] = intent_version
    history = manifest.get("history", [])
    history.append({"id": len(history) + 1, "action": "promote", "intent_id": intent_id, "version": intent_version})
    manifest["history"] = history
    _write_manifest(base, manifest)


def registry_rollback(base: str, intent_id: str, intent_version: str) -> None:
    manifest = _load_manifest(base)
    intents = manifest.get("intents", [])
    entry = next((i for i in intents if i.get("intent_id") == intent_id), None)
    if not entry or intent_version not in entry.get("versions", []):
        raise RegistryError("intent version not found")
    entry["active_version"] = intent_version
    history = manifest.get("history", [])
    history.append({"id": len(history) + 1, "action": "rollback", "intent_id": intent_id, "version": intent_version})
    manifest["history"] = history
    _write_manifest(base, manifest)


def registry_approve(base: str, intent_id: str, intent_version: str, approver: str, reason: str) -> Path:
    stamp = {
        "schema_version": "0.1",
        "intent_id": intent_id,
        "intent_version": intent_version,
        "approved_by": approver,
        "reason": reason,
    }
    _validate(stamp, "approval_stamp.v0_1.json")
    stamp_path = _registry_root(base) / "intents" / intent_id / intent_version / "approval_stamp.json"
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(json.dumps(stamp, sort_keys=True, separators=(",", ":")))
    return stamp_path


def registry_get_active_intent(base: str, intent_id: str) -> Path:
    manifest = _load_manifest(base)
    intents = manifest.get("intents", [])
    entry = next((i for i in intents if i.get("intent_id") == intent_id), None)
    if not entry or not entry.get("active_version"):
        raise RegistryError("active intent not set")
    return _registry_root(base) / "intents" / intent_id / entry["active_version"] / "IntentBundle"

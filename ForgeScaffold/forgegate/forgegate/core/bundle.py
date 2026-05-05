import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator

from .bundle_signing import BundleSignatureError, verify_bundle
from .signing import CryptoUnavailableError
from .lint import LintError, lint_intent


class BundleValidationError(Exception):
    def __init__(self, errors: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _load_schema(schema_name: str) -> Dict[str, Any]:
    base = Path(__file__).resolve().parents[1] / "schemas"
    return json.loads((base / schema_name).read_text())


def _validate(payload: Dict[str, Any], schema_name: str, errors: List[str], label: str) -> None:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    for err in validator.iter_errors(payload):
        loc = ".".join([str(p) for p in err.path])
        errors.append(f"{label}: {loc} {err.message}")


def validate_bundle(
    bundle_path: str,
    require_signature: bool = False,
    pubkey_path: str = "",
    strict: bool = False,
) -> Dict[str, Any]:
    base = Path(bundle_path)
    errors: List[str] = []

    catalogs_dir = base / "catalogs"
    intent_dir = base / "intent"
    tests_dir = base / "tests" / "scenarios"
    meta_path = base / "meta.yaml"

    action_catalog_path = catalogs_dir / "action_catalog.json"
    signal_catalog_path = catalogs_dir / "signal_catalog.json"
    intent_path = intent_dir / "intent_spec.json"

    for required in [catalogs_dir, intent_dir, tests_dir]:
        if not required.exists():
            errors.append(f"missing directory: {required}")

    for required in [action_catalog_path, signal_catalog_path, intent_path, meta_path]:
        if not required.exists():
            errors.append(f"missing file: {required}")

    scenarios = sorted(tests_dir.glob("*.json")) if tests_dir.exists() else []
    if not scenarios:
        errors.append("no scenarios found")

    if errors:
        raise BundleValidationError(errors)

    action_catalog = _load_json(action_catalog_path)
    signal_catalog = _load_json(signal_catalog_path)
    intent_spec = _load_json(intent_path)

    _validate(action_catalog, "action_catalog.v0_1.json", errors, "action_catalog")
    _validate(signal_catalog, "signal_catalog.v0_1.json", errors, "signal_catalog")
    _validate(intent_spec, "intent_spec.v0_1.json", errors, "intent_spec")

    signal_types = {s.get("signal_id"): s for s in signal_catalog.get("signals", [])}

    for scenario_path in scenarios:
        scenario = _load_json(scenario_path)
        if "expected" not in scenario or "decision" not in scenario["expected"]:
            errors.append(f"{scenario_path.name}: missing expected.decision")
        if "proposed_action" in scenario:
            _validate(scenario["proposed_action"], "proposed_action.v0_1.json", errors, scenario_path.name)
        else:
            errors.append(f"{scenario_path.name}: missing proposed_action")
        if "signals" in scenario:
            _validate(scenario["signals"], "signals.v0_1.json", errors, scenario_path.name)
            values = scenario["signals"].get("values", {})
            for key, value in values.items():
                spec = signal_types.get(key)
                if not spec:
                    continue
                expected = spec.get("type")
                if expected == "string" and not isinstance(value, str):
                    errors.append(f"{scenario_path.name}: signal {key} expected string")
                if expected == "number" and not isinstance(value, (int, float)):
                    errors.append(f"{scenario_path.name}: signal {key} expected number")
                if expected == "boolean" and not isinstance(value, bool):
                    errors.append(f"{scenario_path.name}: signal {key} expected boolean")
                if expected == "enum":
                    allowed = spec.get("enum") or []
                    if value not in allowed:
                        errors.append(f"{scenario_path.name}: signal {key} expected enum")
        else:
            errors.append(f"{scenario_path.name}: missing signals")
        if "budget_snapshot" in scenario:
            _validate(scenario["budget_snapshot"], "budget_snapshot.v0_1.json", errors, scenario_path.name)

    try:
        lint_result = lint_intent(bundle_path, strict=strict)
    except LintError as exc:
        errors.extend(exc.errors)
        if strict:
            errors.extend(exc.warnings)
        lint_result = {"warnings": exc.warnings}

    if errors:
        raise BundleValidationError(errors)

    result = {"status": "PASS", "bundle_path": str(base), "scenarios": len(scenarios)}
    if lint_result.get("warnings"):
        result["warnings"] = lint_result["warnings"]
    if require_signature:
        if not pubkey_path:
            raise BundleValidationError(["public key required for signature verification"])
        try:
            verify_bundle(bundle_path, pubkey_path)
        except CryptoUnavailableError as exc:
            raise BundleValidationError([str(exc)]) from exc
        except BundleSignatureError as exc:
            raise BundleValidationError([str(exc)]) from exc
    return result

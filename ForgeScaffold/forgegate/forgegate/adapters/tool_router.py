import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from jsonschema import Draft202012Validator

from forgegate.core.bundle import validate_bundle
from forgegate.core.canonicalize import strip_volatile
from forgegate.core.evaluate import evaluate
from forgegate.core.hashing import compute_decision_id, compute_input_hash


@dataclass
class ToolSpec:
    tool_name: str
    action_id: str
    side_effect: str  # none|read|write|external_write|irreversible
    risk_tier: str  # low|med|high|critical
    params_schema: Optional[Dict[str, Any]] = None


@dataclass
class ToolResult:
    status: str
    decision: str
    output: Optional[Any]
    error: Optional[str]
    decision_record: Dict[str, Any]


PROFILES = {
    "default_offline": {
        "allowed_base_dirs": ["/tmp", "./sandbox"],
        "allowed_commands": ["echo", "ls"],
    },
    "restricted_fs": {
        "allowed_base_dirs": ["./sandbox"],
        "allowed_commands": ["echo"],
    },
    "restricted_subprocess": {
        "allowed_base_dirs": ["/tmp", "./sandbox"],
        "allowed_commands": [],
    },
}


class ToolRouter:
    def __init__(self, intent_spec: Optional[Dict[str, Any]] = None, registry_root: Optional[str] = None, profile: str = "default_offline"):
        self.intent_spec = intent_spec
        self.registry_root = registry_root
        self.tools: Dict[str, Tuple[ToolSpec, Callable[..., Any]]] = {}
        self.ledger_path = None
        self.profile = profile

    def register_tool(self, tool_spec: ToolSpec, func: Callable[..., Any]) -> None:
        self.tools[tool_spec.tool_name] = (tool_spec, func)

    def _load_schema(self, name: str) -> Dict[str, Any]:
        base = Path(__file__).resolve().parents[1] / "schemas"
        return json.loads((base / name).read_text())

    def _validate(self, payload: Dict[str, Any], schema_name: str) -> None:
        schema = self._load_schema(schema_name)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
        if errors:
            msg = "; ".join([f"{'.'.join([str(p) for p in e.path])}: {e.message}" for e in errors])
            raise ValueError(f"schema validation failed for {schema_name}: {msg}")

    def _active_intent_spec(self) -> Dict[str, Any]:
        if self.intent_spec:
            return self.intent_spec
        if not self.registry_root:
            raise ValueError("intent_spec or registry_root required")
        manifest_path = Path(self.registry_root) / "registry" / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("registry manifest missing")
        manifest = json.loads(manifest_path.read_text())
        if not manifest.get("intents"):
            raise ValueError("no intents in registry")
        # select first active intent
        for entry in manifest.get("intents", []):
            if entry.get("active_version"):
                bundle_path = Path(self.registry_root) / "registry" / "intents" / entry["intent_id"] / entry["active_version"] / "IntentBundle"
                validate_bundle(str(bundle_path))
                intent_path = bundle_path / "intent" / "intent_spec.json"
                return json.loads(intent_path.read_text())
        raise ValueError("no active intent set")

    def _bundle_root(self) -> Optional[Path]:
        if not self.registry_root:
            return None
        manifest_path = Path(self.registry_root) / "registry" / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text())
        for entry in manifest.get("intents", []):
            if entry.get("active_version"):
                return Path(self.registry_root) / "registry" / "intents" / entry["intent_id"] / entry["active_version"] / "IntentBundle"
        return None

    def _redaction_rules(self, intent_spec: Dict[str, Any], bundle_root: Optional[Path]) -> list:
        rules = intent_spec.get("redactions") or []
        if bundle_root:
            redaction_path = bundle_root / "governance" / "redaction_rules.yaml"
            if redaction_path.exists():
                import yaml

                payload = yaml.safe_load(redaction_path.read_text()) or {}
                rules = payload.get("redactions", rules)
        return rules

    def _load_signal_catalog(self, bundle_root: Optional[Path]) -> Optional[Dict[str, Any]]:
        if not bundle_root:
            return None
        path = bundle_root / "catalogs" / "signal_catalog.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _validate_signal_types(self, signals: Dict[str, Any], catalog: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not catalog:
            return None
        values = signals.get("values") if isinstance(signals, dict) else signals
        if not isinstance(values, dict):
            return None
        by_id = {s.get("signal_id"): s for s in catalog.get("signals", [])}
        for key, value in values.items():
            spec = by_id.get(key)
            if not spec:
                continue
            expected = spec.get("type")
            if expected == "string" and not isinstance(value, str):
                return {"id": "signal_type_mismatch", "signal": key, "expected": "string"}
            if expected == "number" and not isinstance(value, (int, float)):
                return {"id": "signal_type_mismatch", "signal": key, "expected": "number"}
            if expected == "boolean" and not isinstance(value, bool):
                return {"id": "signal_type_mismatch", "signal": key, "expected": "boolean"}
            if expected == "enum":
                allowed = spec.get("enum") or []
                if value not in allowed:
                    return {"id": "signal_type_mismatch", "signal": key, "expected": "enum"}
        return None

    def _apply_redactions(self, payload: Dict[str, Any], rules: list) -> Dict[str, Any]:
        if not rules:
            return payload
        redacted = json.loads(json.dumps(payload))
        for rule in rules:
            parts = rule.split(".")
            cur = redacted
            for part in parts[:-1]:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    cur = None
                    break
            if isinstance(cur, dict) and parts[-1] in cur:
                cur.pop(parts[-1], None)
        return redacted

    def _check_payload_limits(self, intent_spec: Dict[str, Any], proposed_action: Dict[str, Any], signals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        limits = intent_spec.get("payload_limits") or {}
        max_params = limits.get("max_params_bytes")
        max_signals = limits.get("max_signals_bytes")
        params = proposed_action.get("params") or {}
        signal_values = (signals or {}).get("values", signals) or {}
        params_size = len(json.dumps(params, sort_keys=True, separators=(",", ":")))
        signals_size = len(json.dumps(signal_values, sort_keys=True, separators=(",", ":")))
        if max_params is not None and params_size > max_params:
            return {"id": "payload_limit_exceeded", "field": "params", "size": params_size, "limit": max_params}
        if max_signals is not None and signals_size > max_signals:
            return {"id": "payload_limit_exceeded", "field": "signals", "size": signals_size, "limit": max_signals}
        return None

    def _profile_limits(self) -> Dict[str, Any]:
        return PROFILES.get(self.profile, PROFILES["default_offline"])

    def _enforce_profile(self, tool_spec: ToolSpec, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        limits = self._profile_limits()
        if tool_spec.tool_name == "subprocess_run":
            cmd = params.get("cmd") or []
            allowed = limits.get("allowed_commands", [])
            if cmd and cmd[0] not in allowed:
                return {"id": "profile_blocked", "kind": "subprocess", "cmd": cmd[0]}
        if tool_spec.tool_name == "file_write":
            path = params.get("path") or params.get("target") or params.get("file")
            if path:
                allowed_dirs = [Path(p).resolve() for p in limits.get("allowed_base_dirs", [])]
                target = Path(path).resolve()
                if not any(str(target).startswith(str(d)) for d in allowed_dirs):
                    return {"id": "profile_blocked", "kind": "filesystem", "path": str(target)}
        return None

    def _append_ledger(self, entry: Dict[str, Any]) -> None:
        if not self.ledger_path:
            return
        path = Path(self.ledger_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")

    def call_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        actor: Dict[str, Any],
        signals: Dict[str, Any],
        context_refs: Optional[list] = None,
        budget_snapshot: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        if tool_name not in self.tools:
            raise ValueError("tool not registered")
        spec, func = self.tools[tool_name]
        intent_spec = self._active_intent_spec()
        bundle_root = self._bundle_root()

        proposed_action = {
            "schema_version": "0.1",
            "action_id": spec.action_id,
            "actor_id": actor.get("id"),
            "actor_profile": actor.get("profile"),
            "action_type": spec.side_effect,
            "params": params,
            "metadata": {
                "tool_name": tool_name,
                "risk_tier": spec.risk_tier,
                "context_refs": context_refs or [],
            },
        }

        self._validate(proposed_action, "proposed_action.v0_1.json")
        self._validate(signals, "signals.v0_1.json")
        if budget_snapshot is not None:
            self._validate(budget_snapshot, "budget_snapshot.v0_1.json")

        profile_block = self._enforce_profile(spec, params)
        if profile_block:
            input_hash = compute_input_hash(proposed_action, signals, budget_snapshot)
            decision_id = compute_decision_id(intent_spec.get("intent_version", ""), input_hash)
            decision_record = {
                "schema_version": "0.1",
                "gate_version": "0.3.0",
                "intent_id": intent_spec.get("intent_id"),
                "intent_version": intent_spec.get("intent_version"),
                "decision": "ESCALATE",
                "decision_id": decision_id,
                "input_hash": input_hash,
                "reasons": {"triggered_rules": [profile_block]},
                "escalation": {
                    "kind": "profile_blocked",
                    "channels": (intent_spec.get("escalation") or {}).get("channels", []),
                    "required_payload_fields": (intent_spec.get("escalation") or {}).get("required_payload_fields", []),
                    "sla_minutes": (intent_spec.get("escalation") or {}).get("sla_minutes"),
                },
            }
            return ToolResult("blocked", "ESCALATE", None, "profile_blocked", decision_record)

        signal_catalog = self._load_signal_catalog(bundle_root)
        type_issue = self._validate_signal_types(signals, signal_catalog)
        if type_issue:
            input_hash = compute_input_hash(proposed_action, signals, budget_snapshot)
            decision_id = compute_decision_id(intent_spec.get("intent_version", ""), input_hash)
            decision_record = {
                "schema_version": "0.1",
                "gate_version": "0.3.0",
                "intent_id": intent_spec.get("intent_id"),
                "intent_version": intent_spec.get("intent_version"),
                "decision": "ESCALATE",
                "decision_id": decision_id,
                "input_hash": input_hash,
                "reasons": {"triggered_rules": [type_issue]},
                "escalation": {
                    "kind": "signal_type_mismatch",
                    "channels": (intent_spec.get("escalation") or {}).get("channels", []),
                    "required_payload_fields": (intent_spec.get("escalation") or {}).get("required_payload_fields", []),
                    "sla_minutes": (intent_spec.get("escalation") or {}).get("sla_minutes"),
                },
            }
            return ToolResult("blocked", "ESCALATE", None, "signal_type_mismatch", decision_record)

        payload_limit = self._check_payload_limits(intent_spec, proposed_action, signals)
        if payload_limit:
            input_hash = compute_input_hash(proposed_action, signals, budget_snapshot)
            decision_id = compute_decision_id(intent_spec.get("intent_version", ""), input_hash)
            decision_record = {
                "schema_version": "0.1",
                "gate_version": "0.3.0",
                "intent_id": intent_spec.get("intent_id"),
                "intent_version": intent_spec.get("intent_version"),
                "decision": "ESCALATE",
                "decision_id": decision_id,
                "input_hash": input_hash,
                "reasons": {"triggered_rules": [payload_limit]},
                "escalation": {
                    "kind": "payload_limit",
                    "channels": (intent_spec.get("escalation") or {}).get("channels", []),
                    "required_payload_fields": (intent_spec.get("escalation") or {}).get("required_payload_fields", []),
                    "sla_minutes": (intent_spec.get("escalation") or {}).get("sla_minutes"),
                },
            }
            return ToolResult("blocked", "ESCALATE", None, "payload_limit_exceeded", decision_record)

        decision_record = evaluate(intent_spec, proposed_action, signals, budget_snapshot)
        decision = decision_record.get("decision")

        if decision == "ALLOW_WITH_MODS":
            mods = decision_record.get("mods") or {}
            params.update(mods.get("param_overrides") or {})
            caps = mods.get("caps") or {}
            for key, cap in caps.items():
                if key in params and isinstance(params[key], (int, float)):
                    params[key] = min(params[key], cap)

        if decision in {"ESCALATE", "DENY"}:
            result = ToolResult("blocked", decision, None, "blocked_by_gate", decision_record)
        else:
            output = func(params)
            result = ToolResult("ok", decision, output, None, decision_record)

        redactions = self._redaction_rules(intent_spec, bundle_root)
        redacted_action = self._apply_redactions({"params": proposed_action.get("params", {})}, redactions)
        redacted_signals = self._apply_redactions({"values": signals.get("values", {})}, redactions)

        ledger_entry = {
            "schema_version": "0.1",
            "timestamp": os.environ.get("FORGEGATE_TIMESTAMP", "1970-01-01T00:00:00Z"),
            "intent_id": intent_spec.get("intent_id"),
            "intent_version": intent_spec.get("intent_version"),
            "decision": decision,
            "decision_id": decision_record.get("decision_id"),
            "input_hash": decision_record.get("input_hash"),
            "action_id": proposed_action.get("action_id"),
            "actor_id": proposed_action.get("actor_id"),
            "actor_profile": proposed_action.get("actor_profile"),
            "decision_record": decision_record,
            "proposed_action": {"params": redacted_action.get("params")},
            "signals": {"values": redacted_signals.get("values")},
        }
        self._append_ledger(ledger_entry)

        return result

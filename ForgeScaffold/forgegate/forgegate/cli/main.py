import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from forgegate.core.bundle import BundleValidationError, validate_bundle
from forgegate.core.bundle_signing import BundleSignatureError, sign_bundle, verify_bundle
from forgegate.core.signing import CryptoUnavailableError
from forgegate.core.drift import compute_drift, load_ledger
from forgegate.core.lint import LintError, lint_intent
from forgegate.core.replay import replay_diff, replay_ledger
from forgegate.registry.registry import (
    RegistryError,
    registry_add,
    registry_approve,
    registry_list,
    registry_promote,
    registry_rollback,
)
from forgegate.core.ledger_signing import LedgerSignatureError, sign_ledger, verify_ledger
from forgegate.core.evaluate import evaluate


EXIT_ALLOW = 0
EXIT_ESCALATE = 10
EXIT_DENY = 20
EXIT_BUNDLE_INVALID = 20
EXIT_BUNDLE_MISSING = 21
EXIT_BUNDLE_CRYPTO_MISSING = 22


def _load_json(path: str):
    return json.loads(Path(path).read_text())


def _load_policy(path: str):
    if path.endswith((".yaml", ".yml")):
        return yaml.safe_load(Path(path).read_text())
    return _load_json(path)


def _load_schema(name: str) -> dict:
    base = Path(__file__).resolve().parents[1] / "schemas"
    return json.loads((base / name).read_text())


def _validate(payload: dict, schema_name: str) -> None:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msg = "; ".join([f"{'.'.join([str(p) for p in e.path])}: {e.message}" for e in errors])
        raise ValueError(f"schema validation failed for {schema_name}: {msg}")


def cmd_evaluate(args: argparse.Namespace) -> int:
    intent = _load_json(args.intent)
    action = _load_json(args.action)
    signals = _load_json(args.signals)
    budget = _load_json(args.budget) if args.budget else None

    _validate(intent, "intent_spec.v0_1.json")
    _validate(action, "proposed_action.v0_1.json")
    _validate(signals, "signals.v0_1.json")
    if budget is not None:
        _validate(budget, "budget_snapshot.v0_1.json")

    decision = evaluate(intent, action, signals, budget)
    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))

    if decision["decision"] in {"ALLOW", "ALLOW_WITH_MODS"}:
        return EXIT_ALLOW
    if decision["decision"] == "ESCALATE":
        return EXIT_ESCALATE
    return EXIT_DENY


def cmd_validate_bundle(args: argparse.Namespace) -> int:
    try:
        result = validate_bundle(
            args.bundle,
            require_signature=bool(args.require_signature),
            pubkey_path=args.pubkey or "",
            strict=bool(getattr(args, "strict", False)),
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except BundleValidationError as exc:
        payload = {"status": "FAIL", "errors": exc.errors, "bundle_path": args.bundle}
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 1


def cmd_sign_bundle(args: argparse.Namespace) -> int:
    try:
        sig_path = sign_bundle(args.bundle, args.key)
        print(json.dumps({"status": "PASS", "signature": str(sig_path)}, sort_keys=True, separators=(",", ":")))
        return 0
    except CryptoUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BUNDLE_CRYPTO_MISSING
    except BundleSignatureError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BUNDLE_INVALID


def cmd_verify_bundle(args: argparse.Namespace) -> int:
    try:
        result = verify_bundle(args.bundle, args.pubkey)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except CryptoUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BUNDLE_CRYPTO_MISSING
    except BundleSignatureError as exc:
        print(str(exc), file=sys.stderr)
        if getattr(exc, "code", "") == "missing":
            return EXIT_BUNDLE_MISSING
        return EXIT_BUNDLE_INVALID


def cmd_sign_ledger(args: argparse.Namespace) -> int:
    try:
        result = sign_ledger(args.ledger, args.key, args.checkpoints, args.every_n)
        print(json.dumps({"status": "PASS", **result}, sort_keys=True, separators=(",", ":")))
        return 0
    except LedgerSignatureError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_verify_ledger(args: argparse.Namespace) -> int:
    try:
        result = verify_ledger(args.ledger, args.pubkey, args.checkpoints)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except LedgerSignatureError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_drift_report(args: argparse.Namespace) -> int:
    config = _load_json(args.config) if args.config else None
    policy = _load_policy(args.policy) if args.policy else None
    entries = load_ledger(args.ledger)
    report = compute_drift(entries, config)

    exit_code = 0
    if policy:
        thresholds = policy.get("thresholds", {})
        deny_max = thresholds.get("deny_rate.max")
        miss_max = thresholds.get("missing_signal_rate.max")
        esc_max = thresholds.get("escalation_rate_by_action.max")
        deny_rate = 0.0
        for item in report.get("decision_distribution", []):
            if item.get("id") == "DENY":
                deny_rate = item.get("count", 0) / max(report.get("total_entries", 1), 1)
        missing_rate = report.get("missing_signal_rate", 0.0)
        max_esc = 0.0
        for item in report.get("escalation_rate_by_action_and_role", []):
            max_esc = max(max_esc, item.get("rate", 0.0))

        exceeded = []
        if deny_max is not None and deny_rate > deny_max:
            exceeded.append("deny_rate.max")
        if miss_max is not None and missing_rate > miss_max:
            exceeded.append("missing_signal_rate.max")
        if esc_max is not None and max_esc > esc_max:
            exceeded.append("escalation_rate_by_action.max")

        if exceeded:
            exit_code = 2
            for key in exceeded:
                if key in (policy.get("severities", {}) or {}).get("critical", []):
                    exit_code = 3
                    break
            report["policy_evaluation"] = {"status": "exceeded", "thresholds": exceeded}
        else:
            report["policy_evaluation"] = {"status": "ok"}

    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return exit_code


def cmd_registry(args: argparse.Namespace) -> int:
    base = args.base or str(Path(__file__).resolve().parents[2])
    try:
        if args.registry_cmd == "list":
            manifest = registry_list(base)
            print(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            return 0
        if args.registry_cmd == "add":
            bundle = Path(args.bundle)
            intent_spec = _load_json(str(bundle / "intent" / "intent_spec.json"))
            registry_add(base, str(bundle), intent_spec["intent_id"], intent_spec["intent_version"])
            print(json.dumps({"status": "ok"}, sort_keys=True, separators=(",", ":")))
            return 0
        if args.registry_cmd == "promote":
            intent_id, version = args.intent.split("@", 1)
            if args.simulate_against:
                from forgegate.registry.registry import registry_get_active_intent

                active_bundle = registry_get_active_intent(base, intent_id)
                old_intent = str(Path(active_bundle) / "intent" / "intent_spec.json")
                new_intent = str(Path(base) / "registry" / "intents" / intent_id / version / "IntentBundle" / "intent" / "intent_spec.json")
                report = replay_diff(args.simulate_against, old_intent, new_intent)
                flips = report.get("flip_count", 0)
                evaluated = report.get("evaluated_entries", 1)
                ratio = flips / max(evaluated, 1)
                if args.max_flips is not None and ratio > args.max_flips:
                    print(json.dumps({"status": "blocked", "flip_ratio": ratio, "report": report}, sort_keys=True, separators=(",", ":")))
                    return 1
            registry_promote(base, intent_id, version)
            print(json.dumps({"status": "ok"}, sort_keys=True, separators=(",", ":")))
            return 0
        if args.registry_cmd == "rollback":
            intent_id, version = args.intent.split("@", 1)
            registry_rollback(base, intent_id, version)
            print(json.dumps({"status": "ok"}, sort_keys=True, separators=(",", ":")))
            return 0
        if args.registry_cmd == "approve":
            intent_id, version = args.intent.split("@", 1)
            stamp = registry_approve(base, intent_id, version, args.by, args.reason)
            print(json.dumps({"status": "ok", "approval_stamp": str(stamp)}, sort_keys=True, separators=(",", ":")))
            return 0
    except (RegistryError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 1


def cmd_lint_intent(args: argparse.Namespace) -> int:
    try:
        result = lint_intent(args.bundle, strict=bool(getattr(args, "strict", False)))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except LintError as exc:
        payload = {"status": "FAIL", "errors": exc.errors, "warnings": exc.warnings}
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 1


def cmd_replay(args: argparse.Namespace) -> int:
    if args.intent_old and args.intent_new:
        report = replay_diff(args.ledger, args.intent_old, args.intent_new)
    elif args.intent:
        report = replay_ledger(args.ledger, args.intent)
    else:
        print("intent required", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgegate", description="ForgeGate deterministic action gate")
    sub = parser.add_subparsers(dest="command")
    eval_cmd = sub.add_parser("evaluate", help="Evaluate a proposed action")
    eval_cmd.add_argument("--intent", required=True)
    eval_cmd.add_argument("--action", required=True)
    eval_cmd.add_argument("--signals", required=True)
    eval_cmd.add_argument("--budget")
    bundle_cmd = sub.add_parser("validate-bundle", help="Validate an IntentBundle")
    bundle_cmd.add_argument("bundle")
    bundle_cmd.add_argument("--require-signature", action="store_true")
    bundle_cmd.add_argument("--pubkey")
    bundle_cmd.add_argument("--strict", action="store_true", help="Treat policy warnings as errors")
    sign_bundle_cmd = sub.add_parser("sign-bundle", help="Sign an IntentBundle")
    sign_bundle_cmd.add_argument("bundle")
    sign_bundle_cmd.add_argument("--key", required=True)
    verify_bundle_cmd = sub.add_parser("verify-bundle", help="Verify an IntentBundle signature")
    verify_bundle_cmd.add_argument("bundle")
    verify_bundle_cmd.add_argument("--pubkey", required=True)
    sign_ledger_cmd = sub.add_parser("sign-ledger", help="Sign a decision ledger")
    sign_ledger_cmd.add_argument("ledger")
    sign_ledger_cmd.add_argument("--key", required=True)
    sign_ledger_cmd.add_argument("--checkpoints")
    sign_ledger_cmd.add_argument("--every-n", type=int)
    verify_ledger_cmd = sub.add_parser("verify-ledger", help="Verify a decision ledger signature")
    verify_ledger_cmd.add_argument("ledger")
    verify_ledger_cmd.add_argument("--pubkey", required=True)
    verify_ledger_cmd.add_argument("--checkpoints")
    drift_cmd = sub.add_parser("drift-report", help="Generate drift report from a decision ledger")
    drift_cmd.add_argument("--ledger", required=True)
    drift_cmd.add_argument("--config")
    drift_cmd.add_argument("--policy")
    registry_cmd = sub.add_parser("registry", help="Manage intent registry")
    registry_cmd.add_argument("--base")
    registry_sub = registry_cmd.add_subparsers(dest="registry_cmd")
    reg_add = registry_sub.add_parser("add", help="Add bundle to registry")
    reg_add.add_argument("bundle")
    registry_sub.add_parser("list", help="List registry intents")
    reg_promote = registry_sub.add_parser("promote", help="Promote intent version")
    reg_promote.add_argument("intent")
    reg_promote.add_argument("--simulate-against")
    reg_promote.add_argument("--max-flips", type=float)
    reg_rollback = registry_sub.add_parser("rollback", help="Rollback intent version")
    reg_rollback.add_argument("intent")
    reg_approve = registry_sub.add_parser("approve", help="Approve intent version")
    reg_approve.add_argument("intent")
    reg_approve.add_argument("--by", required=True)
    reg_approve.add_argument("--reason", required=True)
    lint_cmd = sub.add_parser("lint-intent", help="Lint an IntentBundle")
    lint_cmd.add_argument("bundle")
    lint_cmd.add_argument("--strict", action="store_true", help="Treat policy warnings as errors")
    replay_cmd = sub.add_parser("replay", help="Replay ledger against intent")
    replay_cmd.add_argument("--ledger", required=True)
    replay_cmd.add_argument("--intent")
    replay_cmd.add_argument("--intent-old")
    replay_cmd.add_argument("--intent-new")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "evaluate":
            sys.exit(cmd_evaluate(args))
        if args.command == "validate-bundle":
            sys.exit(cmd_validate_bundle(args))
        if args.command == "drift-report":
            sys.exit(cmd_drift_report(args))
        if args.command == "registry":
            sys.exit(cmd_registry(args))
        if args.command == "lint-intent":
            sys.exit(cmd_lint_intent(args))
        if args.command == "replay":
            sys.exit(cmd_replay(args))
        if args.command == "sign-bundle":
            sys.exit(cmd_sign_bundle(args))
        if args.command == "verify-bundle":
            sys.exit(cmd_verify_bundle(args))
        if args.command == "sign-ledger":
            sys.exit(cmd_sign_ledger(args))
        if args.command == "verify-ledger":
            sys.exit(cmd_verify_ledger(args))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()

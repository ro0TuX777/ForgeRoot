import argparse
import json
import configparser
import subprocess
import sys
from pathlib import Path

from .adapters.base import AdapterError, get_adapter
from .adapters.registry import register_builtin_adapters
from .core.report_md import generate_report
from .core.score import ScoreError, score_results
from .core.summary import generate_summary
from .core.regression import regression_check
from .core.validate import WorkcellValidationError, validate_workcell
from .runner.sam_like_runner import RunnerError, run_workcell


def _print_success(result: dict) -> None:
    print("Validation: OK")
    print(f"Workcell: {result['workcell']}")
    print("Schemas checked: ticket, artifact_index, signals, run_config")
    print(f"workcell_hash: {result['workcell_hash']}")


def _print_failure(workcell: str, error: dict) -> None:
    print("Validation: FAILED")
    print(f"Workcell: {workcell}")
    print(f"File: {error.get('file', 'unknown')}")
    print(f"Error: {error.get('error', 'unknown error')}")


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        result = validate_workcell(args.workcell)
        _print_success(result)
        return 0
    except WorkcellValidationError as exc:
        first = exc.errors[0] if exc.errors else {"file": "workcell", "error": "unknown"}
        _print_failure(args.workcell, first)
        return 1


def cmd_ingest(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.domain)
        adapter.ingest(args.source, args.out)
        print("Ingest: OK")
        print(f"Domain: {args.domain}")
        print(f"Source: {args.source}")
        print(f"Raw output: {args.out}")
        return 0
    except AdapterError as exc:
        print("Ingest: FAILED")
        print(f"Domain: {args.domain}")
        print(f"Error: {exc}")
        return 1


def cmd_normalize(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.domain)
        result = adapter.normalize(args.raw, args.out)
        print("Normalization: OK")
        print(f"Domain: {args.domain}")
        print(f"Raw input: {args.raw}")
        print(f"Workcell output: {args.out}")
        print(f"Tickets written: {result['tickets']}")
        print(f"Artifacts indexed: {result['artifacts']}")
        print(f"Signals written: {result['signals']}")
        print(f"workcell_hash: {result['workcell_hash']}")
        return 0
    except AdapterError as exc:
        print("Normalization: FAILED")
        print(f"Domain: {args.domain}")
        print(f"Error: {exc}")
        return 1
    except WorkcellValidationError as exc:
        first = exc.errors[0] if exc.errors else {"file": "workcell", "error": "unknown"}
        print("Normalization: FAILED")
        print(f"Domain: {args.domain}")
        print(f"File: {first.get('file')}")
        print(f"Error: {first.get('error')}")
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    try:
        summary = run_workcell(args.workcell, args.out, mode=args.mode, drift_plan_path=args.drift_plan)
        print("Run: OK")
        print(f"Workcell: {summary['workcell_path']}")
        print(f"Mode: {summary['mode']}")
        print(f"Tickets processed: {summary['ticket_count']}")
        print(f"Decisions written: {summary['decision_count']}")
        print(f"Ledger: {summary['ledger_path']}")
        if summary.get("approval_records_path"):
            print(f"Approval records written: {summary['approval_count']}")
            print(f"Approvals: {summary['approval_records_path']}")
        print(f"workcell_hash: {summary['workcell_hash']}")
        return 0
    except (RunnerError, WorkcellValidationError) as exc:
        print("Run: FAILED")
        print(f"Workcell: {args.workcell}")
        print(f"Error: {exc}")
        return 1


def cmd_score(args: argparse.Namespace) -> int:
    try:
        result = score_results(args.results, args.oracle, args.scoring)
        print("Score: OK")
        print(f"Results: {args.results}")
        print(f"Oracle: {args.oracle}")
        print(f"Scoring config: {args.scoring}")
        print(f"Total score: {result['total_score']}")
        print(f"Pass: {str(result['pass_fail']).lower()}")
        print(f"score.json: {Path(args.results) / 'score.json'}")
        return 0
    except ScoreError as exc:
        print(f"Score: FAILED\nError: {exc}")
        return 1


def cmd_report(args: argparse.Namespace) -> int:
    try:
        out_path = generate_report(args.results, args.score, args.out)
        print("Report: OK")
        print(f"Results: {args.results}")
        print(f"Markdown report: {out_path}")
        return 0
    except Exception as exc:
        print(f"Report: FAILED\nError: {exc}")
        return 1


def cmd_summary(args: argparse.Namespace) -> int:
    try:
        out_path = generate_summary(args.results_root, args.out)
        runs = len(list(Path(args.results_root).glob("*/run_summary.json")))
        print("Summary: OK")
        print(f"Results root: {args.results_root}")
        print(f"Markdown summary: {out_path}")
        print(f"Runs summarized: {runs}")
        return 0
    except Exception as exc:
        print(f"Summary: FAILED\nError: {exc}")
        return 1


def cmd_regression_check(args: argparse.Namespace) -> int:
    try:
        summary = regression_check(args.manifest)
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
        return 0 if summary["status"] == "ok" else 2
    except Exception as exc:
        print(f"Regression check failed: {exc}")
        return 2


def _models_conf_path() -> Path:
    return Path(__file__).resolve().parent / "core_engines" / "config" / "models.conf"


def _load_models_conf() -> configparser.ConfigParser:
    path = _models_conf_path()
    if not path.exists():
        raise FileNotFoundError(f"models.conf not found: {path}")
    config = configparser.ConfigParser()
    config.read(path)
    return config


def _write_models_conf(config: configparser.ConfigParser) -> None:
    path = _models_conf_path()
    with path.open("w") as f:
        config.write(f)


def _ollama_list() -> list[str]:
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ollama not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("failed to run ollama list") from exc
    models: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        if line.strip().startswith("NAME"):
            continue
        name = line.split()[0]
        if name:
            models.append(name)
    return models


def cmd_models(args: argparse.Namespace) -> int:
    subcmd = args.models_command
    if subcmd == "list":
        if args.provider != "ollama":
            print("Models: FAILED\nError: only provider=ollama is supported")
            return 1
        try:
            models = _ollama_list()
        except RuntimeError as exc:
            print(f"Models: FAILED\nError: {exc}")
            return 1
        print("Models: OK")
        for name in models:
            print(name)
        return 0

    if subcmd == "show":
        try:
            config = _load_models_conf()
        except FileNotFoundError as exc:
            print(f"Models: FAILED\nError: {exc}")
            return 1
        llm = config["llm_model"] if "llm_model" in config else {}
        print("Models: OK")
        print(f"provider: {llm.get('provider', '')}")
        print(f"reasoning_model: {llm.get('reasoning_model', '')}")
        print(f"code_model: {llm.get('code_model', '')}")
        print(f"general_model: {llm.get('general_model', '')}")
        return 0

    if subcmd == "set":
        if args.provider != "ollama":
            print("Models: FAILED\nError: only provider=ollama is supported")
            return 1
        if not (args.reasoning_model or args.code_model or args.general_model):
            print("Models: FAILED\nError: no model roles provided")
            return 1
        try:
            available = _ollama_list()
        except RuntimeError as exc:
            print(f"Models: FAILED\nError: {exc}")
            return 1
        for name in [args.reasoning_model, args.code_model, args.general_model]:
            if name and name not in available:
                print(f"Models: FAILED\nError: model not found in ollama list: {name}")
                return 1
        try:
            config = _load_models_conf()
        except FileNotFoundError as exc:
            print(f"Models: FAILED\nError: {exc}")
            return 1
        if "llm_model" not in config:
            config["llm_model"] = {}
        config["llm_model"]["provider"] = args.provider
        if args.reasoning_model:
            config["llm_model"]["reasoning_model"] = args.reasoning_model
        if args.code_model:
            config["llm_model"]["code_model"] = args.code_model
        if args.general_model:
            config["llm_model"]["general_model"] = args.general_model
        _write_models_conf(config)
        print("Models: OK")
        return 0

    print("Models: FAILED\nError: unknown models subcommand")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgeworks")
    sub = parser.add_subparsers(dest="command")
    validate_cmd = sub.add_parser("validate", help="Validate a workcell")
    validate_cmd.add_argument("--workcell", required=True)

    ingest_cmd = sub.add_parser("ingest", help="Ingest raw domain data")
    ingest_cmd.add_argument("--domain", required=True)
    ingest_cmd.add_argument("--source", required=True)
    ingest_cmd.add_argument("--out", required=True)

    normalize_cmd = sub.add_parser("normalize", help="Normalize raw data into a workcell")
    normalize_cmd.add_argument("--domain", required=True)
    normalize_cmd.add_argument("--raw", required=True)
    normalize_cmd.add_argument("--out", required=True)

    run_cmd = sub.add_parser("run", help="Run a workcell")
    run_cmd.add_argument("--workcell", required=True)
    run_cmd.add_argument("--mode", required=True)
    run_cmd.add_argument("--out", required=True)
    run_cmd.add_argument("--drift-plan")

    score_cmd = sub.add_parser("score", help="Score a run against an oracle")
    score_cmd.add_argument("--results", required=True)
    score_cmd.add_argument("--oracle", required=True)
    score_cmd.add_argument("--scoring", required=True)

    report_cmd = sub.add_parser("report", help="Generate a markdown report")
    report_cmd.add_argument("--results", required=True)
    report_cmd.add_argument("--score", required=True)
    report_cmd.add_argument("--out", required=True)

    summary_cmd = sub.add_parser("summary", help="Generate a cross-run summary")
    summary_cmd.add_argument("--results-root", required=True)
    summary_cmd.add_argument("--out", required=True)
    regression_cmd = sub.add_parser("regression-check", help="Check frozen regression batches")
    regression_cmd.add_argument("--manifest", required=True)

    models_cmd = sub.add_parser("models", help="Manage local model selection")
    models_sub = models_cmd.add_subparsers(dest="models_command")

    models_list = models_sub.add_parser("list", help="List available local models")
    models_list.add_argument("--provider", default="ollama")

    models_show = models_sub.add_parser("show", help="Show current model configuration")

    models_set = models_sub.add_parser("set", help="Set model roles")
    models_set.add_argument("--provider", default="ollama")
    models_set.add_argument("--reasoning", dest="reasoning_model")
    models_set.add_argument("--code", dest="code_model")
    models_set.add_argument("--general", dest="general_model")

    return parser


def main() -> None:
    register_builtin_adapters()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "validate":
        sys.exit(cmd_validate(args))
    if args.command == "ingest":
        sys.exit(cmd_ingest(args))
    if args.command == "normalize":
        sys.exit(cmd_normalize(args))
    if args.command == "run":
        sys.exit(cmd_run(args))
    if args.command == "score":
        sys.exit(cmd_score(args))
    if args.command == "report":
        sys.exit(cmd_report(args))
    if args.command == "summary":
        sys.exit(cmd_summary(args))
    if args.command == "regression-check":
        sys.exit(cmd_regression_check(args))
    if args.command == "models":
        sys.exit(cmd_models(args))
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()

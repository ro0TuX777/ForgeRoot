"""Minimal ForgeGate CLI compatibility entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forgegate.core.evaluate import evaluate


def app() -> None:
    parser = argparse.ArgumentParser(description="ForgeGate evaluate")
    subparsers = parser.add_subparsers(dest="command")

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--intent", required=True)
    evaluate_parser.add_argument("--action", required=True)
    evaluate_parser.add_argument("--signals", required=True)

    args = parser.parse_args()
    if args.command != "evaluate":
        parser.print_help()
        raise SystemExit(1)

    intent = json.loads(Path(args.intent).read_text(encoding="utf-8"))
    action = json.loads(Path(args.action).read_text(encoding="utf-8"))
    signals = json.loads(Path(args.signals).read_text(encoding="utf-8"))
    print(json.dumps(evaluate(intent, action, signals), indent=2))


if __name__ == "__main__":
    app()

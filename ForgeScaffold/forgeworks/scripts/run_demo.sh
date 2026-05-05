#!/usr/bin/env bash
set -euo pipefail

root="${1:-./results/demo}"
ci_out="${root}/ci_supervised"
ops_out="${root}/ops_ramped"

./scripts/run_pack.sh ci_change_control 0.1.0 supervised "${ci_out}"
./scripts/run_pack.sh it_ops_runbook 0.1.0 ramped "${ops_out}"

forgeworks summary --results-root "${root}" --out "${root}/summary.md"

echo "Summary: ${root}/summary.md"

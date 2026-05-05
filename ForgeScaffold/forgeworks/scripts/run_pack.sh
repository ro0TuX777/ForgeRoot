#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <domain> <version> <mode> <out_dir>" >&2
  exit 1
fi

domain="$1"
version="$2"
mode="$3"
out_dir="$4"

workcell="./packs/${domain}/${version}"
oracle="${workcell}/oracle/expectations.jsonl"
scoring="${workcell}/scoring/scoring.json"
report_out="${out_dir}/report.md"

printf "[1/4] validate ... "
forgeworks validate --workcell "${workcell}"

printf "[2/4] run ... "
forgeworks run --workcell "${workcell}" --mode "${mode}" --out "${out_dir}"

printf "[3/4] score ... "
forgeworks score --results "${out_dir}" --oracle "${oracle}" --scoring "${scoring}"

printf "[4/4] report ... "
forgeworks report --results "${out_dir}" --score "${out_dir}/score.json" --out "${report_out}"

echo "Done."
echo "Results: ${out_dir}"

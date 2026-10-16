#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
if [[ $# -eq 2 && "$1" == "--package" ]]; then
  bash publishing/prepare_package.sh "$2" > "$2/package_result.json"
  package_status=$?
  bash reporting/summarize_run.sh "$2" > "$2/summary.json"
  cat "$2/summary.json"
  exit "$package_status"
elif [[ $# -eq 0 ]]; then
  mode="live"
elif [[ $# -eq 1 && "$1" == "--collect-only" ]]; then
  mode="collection_only"
else
  echo "Usage: bash run.sh [--collect-only] | --package runs/RUN_ID" >&2
  exit 2
fi
run_dir=$("${PYTHON_BIN:-python3}" run_setup.py "$mode") || exit $?
bash data/store.sh init
init_status=$?
bash workflows/collect_sources.sh "$run_dir"
collect_status=$?
series_status=0
if [[ "$mode" == "live" ]]; then
  bash workflows/create_series.sh "$run_dir"
  series_status=$?
fi
bash reporting/summarize_run.sh "$run_dir" > "$run_dir/summary.json"
summary_status=$?
if [[ "$summary_status" -eq 0 ]]; then
  cat "$run_dir/summary.json"
fi
if [[ "$init_status" -ne 0 || "$collect_status" -ne 0 || "$series_status" -ne 0 || "$summary_status" -ne 0 ]]; then
  exit 1
fi

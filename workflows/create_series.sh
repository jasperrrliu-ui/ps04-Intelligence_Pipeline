#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 1 || ! -f "$1/run.json" ]]; then
  echo "Usage: create_series.sh RUN_DIR" >&2
  exit 2
fi
run_dir="$1"
selection=1 briefs=1 articles=1 video_scripts=1 review=1
cat "$run_dir/eligible.jsonl" | bash editorial/select_items.sh "$run_dir" > "$run_dir/decisions.jsonl"
selection=$?
if [[ "$selection" -eq 0 ]]; then
  cat "$run_dir/decisions.jsonl" | bash editorial/create_briefs.sh "$run_dir" > "$run_dir/briefs.jsonl"
  briefs=$?
fi
if [[ "$briefs" -eq 0 ]]; then
  cat "$run_dir/briefs.jsonl" | bash content/write_articles.sh "$run_dir" > "$run_dir/articles.jsonl"
  articles=$?
  cat "$run_dir/briefs.jsonl" | bash content/write_video_scripts.sh "$run_dir" > "$run_dir/video_scripts.jsonl"
  video_scripts=$?
fi
if [[ "$articles" -eq 0 && "$video_scripts" -eq 0 ]]; then
  bash review/check_content.sh "$run_dir" > "$run_dir/review.json"
  review=$?
fi
printf '{"selection":%s,"briefs":%s,"articles":%s,"video_scripts":%s,"review":%s}\n' "$selection" "$briefs" "$articles" "$video_scripts" "$review" > "$run_dir/series_status.json"
if [[ "$selection" -ne 0 || "$briefs" -ne 0 || "$articles" -ne 0 || "$video_scripts" -ne 0 || "$review" -ne 0 ]]; then
  exit 1
fi
"${PYTHON_BIN:-python3}" -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1],encoding="utf-8"))["passed"] else 1)' "$run_dir/review.json"

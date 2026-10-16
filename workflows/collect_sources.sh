#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 1 || ! -f "$1/run.json" ]]; then
  echo "Usage: collect_sources.sh RUN_DIR" >&2
  exit 2
fi
run_dir="$1"
mkdir -p "$run_dir/candidates" "$run_dir/logs"
failed=0

bash collectors/fetch_feeds.sh "$run_dir" > "$run_dir/candidates/feeds.jsonl"
feed_status=$?
bash collectors/fetch_youtube.sh "$run_dir" > "$run_dir/candidates/youtube.jsonl"
youtube_status=$?
bash collectors/fetch_podcasts.sh "$run_dir" > "$run_dir/candidates/podcasts.jsonl"
podcast_status=$?
bash collectors/fetch_web.sh "$run_dir" > "$run_dir/candidates/web.jsonl"
web_status=$?
cat "$run_dir/candidates/feeds.jsonl" "$run_dir/candidates/youtube.jsonl" "$run_dir/candidates/podcasts.jsonl" "$run_dir/candidates/web.jsonl" > "$run_dir/candidates.jsonl"

# A real pipe connects candidate records to the extraction component.
cat "$run_dir/candidates.jsonl" | bash processing/extract_content.sh "$run_dir" > "$run_dir/items.jsonl"
extract_status=$?
cat "$run_dir/items.jsonl" | bash data/store.sh upsert "$run_dir" > "$run_dir/changes.jsonl"
store_status=$?
bash data/store.sh list > "$run_dir/corpus.jsonl"
list_status=$?
cat "$run_dir/corpus.jsonl" | bash processing/filter_items.sh "$run_dir" > "$run_dir/eligible.jsonl"
filter_status=$?
cat "$run_dir/eligible.jsonl" | "${PYTHON_BIN:-python3}" processing/material_shortlist.py "$run_dir" > "$run_dir/material_shortlist.jsonl"
focus_status=$?

printf '{"feed":%d,"youtube":%d,"podcast":%d,"web":%d,"extract":%d,"store":%d,"list":%d,"filter":%d,"focus":%d}\n' \
  "$feed_status" "$youtube_status" "$podcast_status" "$web_status" "$extract_status" "$store_status" "$list_status" "$filter_status" "$focus_status" > "$run_dir/collection_status.json"
for status in "$feed_status" "$youtube_status" "$podcast_status" "$web_status" "$extract_status" "$store_status" "$list_status" "$filter_status" "$focus_status"; do
  if [[ "$status" -ne 0 ]]; then failed=1; fi
done
exit "$failed"

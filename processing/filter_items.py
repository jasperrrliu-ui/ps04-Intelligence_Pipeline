"""Mechanical UTC 30-calendar-day eligibility filter."""

import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import emit, now, receipt, run_dir


def reason(item, as_of):
    value = item.get("published_at")
    if not value:
        return "unknown_date"
    try:
        if len(value) == 10:
            day = dt.date.fromisoformat(value)
        else:
            stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                return "invalid_date"
            day = stamp.astimezone(dt.timezone.utc).date()
    except (TypeError, ValueError):
        return "invalid_date"
    if day > as_of:
        return "future_date"
    if day < as_of - dt.timedelta(days=29):
        return "outside_window"
    return None


def main():
    if len(sys.argv) != 2:
        print("Usage: filter_items.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        as_of = dt.date.fromisoformat(json.loads((run / "run.json").read_text(encoding="utf-8-sig"))["as_of_date"])
        records = [json.loads(line) for line in sys.stdin if line.strip()]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, eligible, excluded = now(), 0, 0
    with (run / "exclusions.jsonl").open("w", encoding="utf-8") as output:
        for item in records:
            if not isinstance(item, dict) or not item.get("item_id") or not item.get("version_id"):
                print("Malformed item", file=sys.stderr)
                return 2
            exclusion = reason(item, as_of)
            if exclusion:
                output.write(json.dumps({"item_id": item["item_id"], "version_id": item["version_id"], "reason": exclusion, "detail": f"published_at={item.get('published_at')!r}; as_of_date={as_of.isoformat()}"}, ensure_ascii=False) + "\n")
                excluded += 1
            else:
                emit(item)
                eligible += 1
    receipt(run, "filter_items", started, len(records), eligible, ["python:datetime"], [])
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

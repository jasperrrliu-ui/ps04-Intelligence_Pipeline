"""Confirm a reviewable twelve-item topical collection from current eligible evidence."""

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import emit, now, receipt, run_dir


def main():
    if len(sys.argv) != 2:
        print("Usage: material_shortlist.py RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        focus = json.loads((run / "config" / "material_focus.json").read_text(encoding="utf-8-sig"))
        eligible = {row["item_id"]: row for row in (json.loads(line) for line in sys.stdin if line.strip())}
        if not isinstance(focus, list) or len(focus) < 12 or len({row["item_id"] for row in focus}) != len(focus):
            raise ValueError("Material focus must list at least 12 distinct item IDs")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, chosen = now(), [], []
    try:
        for entry in focus:
            item = eligible.get(entry["item_id"])
            if not item:
                raise ValueError(f"Focused item is unavailable or outside the window: {entry['item_id']}")
            if not (ROOT / item["text_path"]).is_file() or (item["kind"] in ("youtube", "podcast") and (not item.get("segments_path") or not (ROOT / item["segments_path"]).is_file())):
                raise ValueError(f"Focused item lacks retained text or segments: {entry['item_id']}")
            chosen.append(dict(item, collection_screen={"status": "candidate_for_editorial_review", "reason": entry["reason"]}))
        kinds = collections.Counter(row["kind"] for row in chosen)
        if len({row["publisher_id"] for row in chosen}) < 6 or any(kinds[kind] < 2 for kind in ("feed", "youtube", "podcast")):
            raise ValueError("Focused collection lacks six publishers or two of each required input type")
        for item in chosen:
            emit(item)
    except Exception as exc:
        errors.append(str(exc))
        print(exc, file=sys.stderr)
    receipt(run, "material_shortlist", started, len(focus), len(chosen) if not errors else 0, ["python:json"], errors)
    return 1 if errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

"""Discover podcast episodes and audio enclosures using curl."""

import json
import sys
import uuid
import re

from _common import ROOT, canonical_url, emit, fetch_with_curl, now, receipt, recent_or_unverified, rel, run_dir, sources, stable_id
from _rss import entries


def main():
    if len(sys.argv) != 2:
        print("Usage: fetch_podcasts.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        configured = sources(run, "podcast")
    except (ValueError, OSError, KeyError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, count, tools = now(), [], 0, set()
    skipped = []
    raw_dir = ROOT / "data" / "media" / "podcasts" / run.name
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source in configured:
        raw = raw_dir / (source["source_id"] + "-" + uuid.uuid4().hex + ".xml")
        try:
            tools.add(fetch_with_curl(source["url"], raw))
            for entry in entries(raw.read_bytes()):
                if not entry["title"] or not entry["media_url"]:
                    continue
                if not recent_or_unverified(run, entry["published_at"]):
                    continue
                pattern = source.get("title_include_regex")
                if pattern and not re.search(pattern, entry["title"], re.IGNORECASE):
                    skipped.append({"source_id": source["source_id"], "title": entry["title"], "url": entry["url"], "published_at": entry["published_at"], "reason": "outside_configured_podcast_topic_filter", "title_include_regex": pattern})
                    continue
                url = canonical_url(entry["url"] or entry["media_url"])
                identity = source["publisher_id"] + ":" + (entry["guid"] or url)
                emit({
                    "item_id": stable_id("podcast", identity),
                    "source_id": source["source_id"],
                    "publisher_id": source["publisher_id"],
                    "kind": "podcast",
                    "title": entry["title"],
                    "url": url,
                    "published_at": entry["published_at"],
                    "retrieved_at": now(),
                    "media_url": entry["media_url"],
                    "transcript_url": entry["transcript_url"],
                    "feed_guid": entry["guid"],
                    "raw_feed_path": rel(raw),
                })
                count += 1
        except Exception as exc:
            message = f'{source["source_id"]}: {exc}'
            errors.append(message)
            print(message, file=sys.stderr)
    (run / "podcast_skips.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in skipped), encoding="utf-8")
    receipt(run, "fetch_podcasts", started, len(configured), count, sorted(tools | {"python:xml.etree.ElementTree"}), errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

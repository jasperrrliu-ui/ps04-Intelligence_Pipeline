"""Discover written RSS entries using curl, retaining the original XML."""

import sys
import uuid

from _common import ROOT, canonical_url, emit, fetch_with_curl, now, receipt, recent_or_unverified, rel, run_dir, sources, stable_id
from _rss import entries


def main():
    if len(sys.argv) != 2:
        print("Usage: fetch_feeds.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        configured = sources(run, "feed")
    except (ValueError, OSError, KeyError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, count, tools = now(), [], 0, set()
    raw_dir = ROOT / "data" / "media" / "feeds" / run.name
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source in configured:
        raw = raw_dir / (source["source_id"] + "-" + uuid.uuid4().hex + ".xml")
        try:
            tools.add(fetch_with_curl(source["url"], raw))
            for entry in entries(raw.read_bytes()):
                if not entry["url"] or not entry["title"]:
                    continue
                if not recent_or_unverified(run, entry["published_at"]):
                    continue
                url = canonical_url(entry["url"])
                emit({
                    "item_id": stable_id("article", url),
                    "source_id": source["source_id"],
                    "publisher_id": source["publisher_id"],
                    "kind": "feed",
                    "title": entry["title"],
                    "url": url,
                    "published_at": entry["published_at"],
                    "retrieved_at": now(),
                    "media_url": None,
                    "feed_guid": entry["guid"],
                    "raw_feed_path": rel(raw),
                })
                count += 1
        except Exception as exc:
            message = f'{source["source_id"]}: {exc}'
            errors.append(message)
            print(message, file=sys.stderr)
    receipt(run, "fetch_feeds", started, len(configured), count, sorted(tools | {"python:xml.etree.ElementTree"}), errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

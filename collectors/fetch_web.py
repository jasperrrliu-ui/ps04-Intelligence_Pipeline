"""Collect explicitly curated written web supplements, separate from RSS coverage."""

import json
import pathlib
import sys
import uuid

from _common import ROOT, canonical_url, emit, fetch_with_curl, now, receipt, recent_or_unverified, rel, run_dir, stable_id


def main():
    if len(sys.argv) != 2:
        print("Usage: fetch_web.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        configured = json.loads((run / "config" / "supplemental_articles.json").read_text(encoding="utf-8-sig"))
        if not isinstance(configured, list):
            raise ValueError("supplemental_articles.json must be an array")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, count, tools = now(), [], 0, set()
    raw_dir = ROOT / "data" / "media" / "web" / run.name
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source in configured:
        try:
            for key in ("source_id", "publisher_id", "title", "url", "published_at", "date_evidence"):
                if not isinstance(source.get(key), str) or not source[key].strip():
                    raise ValueError(f"Missing {key}")
            if not recent_or_unverified(run, source["published_at"]):
                continue
            url = canonical_url(source["url"])
            raw = raw_dir / (source["source_id"] + "-" + uuid.uuid4().hex + ".html")
            tools.add(fetch_with_curl(url, raw))
            body = raw.read_text(encoding="utf-8", errors="replace")
            if len(body) < 500 or "Just a moment..." in body[:300]:
                raise RuntimeError("Publisher page is unavailable or blocked")
            emit({
                "item_id": stable_id("article", url),
                "source_id": source["source_id"],
                "publisher_id": source["publisher_id"],
                "kind": "web",
                "title": source["title"],
                "url": url,
                "published_at": source["published_at"],
                "published_date_precision": "day" if len(source["published_at"]) == 10 else "second",
                "date_evidence": source["date_evidence"],
                "retrieved_at": now(),
                "media_url": None,
                "discovery_method": "curated_web_supplement",
                "source_interest": source.get("source_interest"),
                "raw_page_path": rel(raw),
            })
            count += 1
        except Exception as exc:
            message = f'{source.get("source_id", "unknown")}: {exc}'
            errors.append(message)
            print(message, file=sys.stderr)
    receipt(run, "fetch_web", started, len(configured), count, sorted(tools), errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

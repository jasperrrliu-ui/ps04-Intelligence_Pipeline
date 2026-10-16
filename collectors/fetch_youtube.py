"""Discover configured YouTube videos with yt-dlp and retain comments."""

import datetime as dt
import json
import shutil
import sys
import uuid

from _common import ROOT, command, emit, now, receipt, recent_or_unverified, rel, run_dir, sources


def youtube_date(info):
    value = info.get("release_timestamp") or info.get("timestamp")
    if value:
        return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    value = info.get("upload_date")
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}T00:00:00Z"
    return None


def main():
    if len(sys.argv) != 2:
        print("Usage: fetch_youtube.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        configured = sources(run, "youtube")
    except (ValueError, OSError, KeyError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, count = now(), [], 0
    raw_dir = ROOT / "data" / "media" / "youtube" / run.name
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source in configured:
        try:
            source_dir = raw_dir / (source["source_id"] + "-" + uuid.uuid4().hex[:8])
            source_dir.mkdir(parents=True, exist_ok=True)
            # Reference.txt: --write-comments with --write-info-json, but no full video download here.
            executable = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]
            result = command(executable + ["--skip-download", "--write-comments", "--write-info-json", "--no-playlist", "--socket-timeout", "30", "-o", str(source_dir / "%(id)s.%(ext)s"), source["url"]], 600)
            if result.returncode:
                raise RuntimeError(result.stderr.strip()[-1000:] or f"yt-dlp exit {result.returncode}")
            video_id = source["url"].split("v=", 1)[-1].split("&", 1)[0]
            info_path = source_dir / f"{video_id}.info.json"
            if not info_path.is_file():
                raise RuntimeError("yt-dlp did not create the expected info.json")
            info = json.loads(info_path.read_text(encoding="utf-8"))
            native_id = info.get("id") or video_id
            if info.get("_type") == "playlist":
                raise RuntimeError("playlist/channel expansion is not implemented for this source")
            if not recent_or_unverified(run, youtube_date(info)):
                continue
            emit({
                "item_id": "youtube:" + native_id,
                "source_id": source["source_id"],
                "publisher_id": source["publisher_id"],
                "kind": "youtube",
                "title": info.get("title") or native_id,
                "url": info.get("webpage_url") or source["url"],
                "published_at": youtube_date(info),
                "retrieved_at": now(),
                "media_url": info.get("webpage_url") or source["url"],
                "comments_path": rel(info_path),
                "comment_count": len(info.get("comments") or []),
                "description": info.get("description"),
                "duration_seconds": info.get("duration"),
            })
            count += 1
        except Exception as exc:
            message = f'{source["source_id"]}: {exc}'
            errors.append(message)
            print(message, file=sys.stderr)
    receipt(run, "fetch_youtube", started, len(configured), count, ["yt-dlp"], errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

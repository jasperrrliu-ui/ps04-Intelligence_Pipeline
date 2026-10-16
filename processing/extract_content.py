"""Turn collector candidates into retained text and timestamped evidence assets."""

import hashlib
import html
from html.parser import HTMLParser
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import traceback
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "collectors"))
from _common import ROOT, command, fetch_with_curl, now, receipt, rel, run_dir


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self.skip += 1
        elif tag in ("p", "h1", "h2", "h3", "li", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header") and self.skip:
            self.skip -= 1
        elif tag in ("p", "h1", "h2", "h3", "li", "blockquote"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        return "\n".join(line.strip() for line in raw.splitlines() if line.strip())


def ytdlp():
    return ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]


def cached_youtube_audio(video_id):
    cache = ROOT / "data" / "media" / "youtube_audio"
    return next((path for path in cache.glob(video_id + ".*") if path.is_file() and path.suffix in (".mp4", ".m4a", ".webm", ".mp3") and path.stat().st_size > 1024), None)


def timestamp(value):
    match = re.search(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)", value)
    if not match:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    hours, minutes, seconds, fraction = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction.ljust(3, "0")[:3]) / 1000


def parse_vtt(path):
    blocks = re.split(r"\r?\n\s*\r?\n", path.read_text(encoding="utf-8-sig", errors="replace"))
    segments = []
    for block in blocks:
        lines = block.splitlines()
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        left, right = lines[timing].split("-->", 1)
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", "", line)).strip() for line in lines[timing + 1 :] if line.strip())
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        start, end = timestamp(left), timestamp(right)
        # yt-dlp auto captions can repeat sliding lines; retain one copy per span.
        if segments and segments[-1]["text"] == text and segments[-1]["end_seconds"] >= start:
            segments[-1]["end_seconds"] = max(end, segments[-1]["end_seconds"])
        else:
            segments.append({"segment_id": f"s{len(segments)+1:05d}", "start_seconds": start, "end_seconds": end, "text": text})
    return segments


def whisper_segments(audio, work):
    model = os.environ.get("WHISPER_MODEL")
    whisper_bin = os.environ.get("WHISPER_BIN", "whisper-cli")
    ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
    if not model:
        raise RuntimeError("No transcript found; set WHISPER_MODEL for whisper.cpp fallback")
    if not shutil.which(ffmpeg_bin) and not pathlib.Path(ffmpeg_bin).is_file():
        raise RuntimeError("No transcript found; ffmpeg is required for whisper.cpp fallback")
    if not shutil.which(whisper_bin) and not pathlib.Path(whisper_bin).is_file():
        raise RuntimeError("No transcript found; whisper.cpp whisper-cli is unavailable")
    wav = work / "audio-16k.wav"
    result = command([ffmpeg_bin, "-y", "-i", str(audio), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], 600)
    if result.returncode:
        raise RuntimeError("ffmpeg conversion failed: " + result.stderr[-500:])
    prefix = work / "whisper"
    result = command([whisper_bin, "-m", model, "-f", str(wav), "-l", "en", "-t", os.environ.get("WHISPER_THREADS", "4"), "-ojf", "-of", str(prefix)], 7200)
    if result.returncode:
        raise RuntimeError("whisper.cpp failed: " + result.stderr[-500:])
    output = prefix.with_suffix(".json")
    if not output.is_file():
        raise RuntimeError("whisper.cpp did not produce JSON segments")
    payload = json.loads(output.read_text(encoding="utf-8"))
    segments = []
    for row in payload.get("transcription", []):
        offsets = row.get("offsets") or {}
        if "from" not in offsets or "to" not in offsets:
            continue
        segments.append({"segment_id": f"s{len(segments)+1:05d}", "start_seconds": offsets["from"] / 1000, "end_seconds": offsets["to"] / 1000, "text": row.get("text", "").strip()})
    if not segments:
        raise RuntimeError("whisper.cpp returned no timestamped segments")
    return segments


def require_whisper():
    ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
    if not os.environ.get("WHISPER_MODEL") or not (shutil.which(ffmpeg_bin) or pathlib.Path(ffmpeg_bin).is_file()) or not (shutil.which(os.environ.get("WHISPER_BIN", "whisper-cli")) or pathlib.Path(os.environ.get("WHISPER_BIN", "whisper-cli")).is_file()):
        raise RuntimeError("No transcript found; WHISPER_MODEL, ffmpeg, and whisper.cpp are required")


def article(candidate, work):
    source = work / "article.html"
    tool = fetch_with_curl(candidate["url"], source)
    parser = ArticleText()
    parser.feed(source.read_text(encoding="utf-8", errors="replace"))
    text = parser.text()
    if len(text) < 400:
        raise RuntimeError("Article body too short or not extractable")
    return text, None, tool


def youtube(candidate, work):
    command_line = ytdlp() + ["--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en.*", "--sub-format", "vtt", "--no-playlist", "-o", str(work / "%(id)s.%(ext)s"), candidate["url"]]
    result = command(command_line, 300)
    captions = sorted(work.glob("*.vtt"), key=lambda p: (".en.vtt" not in p.name, p.name))
    cache = ROOT / "data" / "media" / "youtube_audio"
    cache.mkdir(parents=True, exist_ok=True)
    video_id = candidate["url"].split("v=", 1)[-1].split("&", 1)[0]
    audio = cached_youtube_audio(video_id)
    if audio is None:
        audio_result = command(ytdlp() + ["--js-runtimes", "node", "-f", "234/233/ba/best", "--no-playlist", "--no-progress", "-o", str(cache / (video_id + ".%(ext)s")), candidate["url"]], 1200)
        if audio_result.returncode:
            raise RuntimeError("YouTube audio download failed: " + audio_result.stderr[-500:])
        audio = cached_youtube_audio(video_id)
    if audio is None:
        raise RuntimeError("yt-dlp produced no retained YouTube audio")
    candidate["raw_media_path"] = rel(audio)
    for caption in captions:
        segments = parse_vtt(caption)
        if segments:
            return "\n".join(row["text"] for row in segments), segments, "yt-dlp captions"
    require_whisper()
    segments = whisper_segments(audio, work)
    return "\n".join(row["text"] for row in segments), segments, "yt-dlp audio + ffmpeg + whisper.cpp"


def podcast(candidate, work):
    transcript_url = candidate.get("transcript_url")
    if transcript_url:
        saved = work / "publisher-transcript.vtt"
        try:
            fetch_with_curl(transcript_url, saved)
            segments = parse_vtt(saved)
            if segments:
                return "\n".join(row["text"] for row in segments), segments, "publisher transcript"
        except Exception:
            pass
    require_whisper()
    cache = ROOT / "data" / "media" / "podcast_audio" / hashlib.sha256(candidate["media_url"].encode("utf-8")).hexdigest()[:24]
    cache.mkdir(parents=True, exist_ok=True)
    audio = cache / "episode-audio"
    if not audio.is_file():
        staged = cache / ("download-" + uuid.uuid4().hex)
        fetch_with_curl(candidate["media_url"], staged)
        staged.replace(audio)
    candidate["raw_media_path"] = rel(audio)
    segments = whisper_segments(audio, work)
    return "\n".join(row["text"] for row in segments), segments, "curl audio + ffmpeg + whisper.cpp"


def stored_media(candidate):
    """Reuse fixed media through the store interface when retained evidence exists."""
    if candidate["kind"] not in ("youtube", "podcast"):
        return None
    result = command([sys.executable, str(ROOT / "data" / "store.py"), "get", candidate["item_id"]], 30)
    if result.returncode:
        return None
    try:
        previous = json.loads(result.stdout)
        if previous.get("published_at") != candidate.get("published_at") or previous.get("url") != candidate.get("url"):
            return None
        for key in ("text_path", "segments_path"):
            if not previous.get(key) or not (ROOT / previous[key]).is_file():
                return None
        retained = dict(previous, retrieved_at=candidate["retrieved_at"], reused_from_store=True)
        if candidate["kind"] == "youtube":
            video_id = candidate["url"].split("v=", 1)[-1].split("&", 1)[0]
            audio = cached_youtube_audio(video_id)
            if audio:
                retained["raw_media_path"] = rel(audio)
            elif not previous.get("raw_media_path") or not (ROOT / previous["raw_media_path"]).is_file():
                return None
        return retained
    except (ValueError, KeyError, OSError):
        return None


def main():
    if len(sys.argv) != 2:
        print("Usage: extract_content.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        candidates = [json.loads(line) for line in sys.stdin if line.strip()]
        for row in candidates:
            if not isinstance(row, dict) or any(key not in row for key in ("item_id", "source_id", "publisher_id", "kind", "title", "url", "published_at", "retrieved_at", "media_url")):
                raise ValueError("Invalid candidate record")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, count, tools = now(), [], 0, set()
    for row in candidates:
        previous = stored_media(row)
        if previous:
            tools.add("data/store.py get (retained media reuse)")
            sys.stdout.write(json.dumps(previous, ensure_ascii=False) + "\n")
            count += 1
            continue
        work = ROOT / "data" / "media" / "extraction" / run.name / (hashlib.sha256(row["item_id"].encode()).hexdigest()[:20] + "-" + uuid.uuid4().hex[:8])
        work.mkdir(parents=True, exist_ok=True)
        try:
            if row["kind"] in ("feed", "web"):
                body, segments, tool = article(row, work)
            elif row["kind"] == "youtube":
                body, segments, tool = youtube(row, work)
            elif row["kind"] == "podcast":
                body, segments, tool = podcast(row, work)
            else:
                raise ValueError("Unsupported kind")
            tools.add(tool)
            material = json.dumps({"title": row["title"], "published_at": row["published_at"], "text": body, "segments": segments}, ensure_ascii=False, sort_keys=True)
            version = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
            target = ROOT / "data" / "assets" / hashlib.sha256(row["item_id"].encode()).hexdigest()[:20] / version
            target.mkdir(parents=True, exist_ok=True)
            text_path = target / "text.txt"
            if not text_path.exists():
                text_path.write_text(body + "\n", encoding="utf-8")
            segments_path = None
            if segments is not None:
                segments_path = target / "segments.json"
                if not segments_path.exists():
                    segments_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            item = dict(row, version_id=version, text_path=rel(text_path), segments_path=rel(segments_path) if segments_path else None, extraction_tool=tool)
            if row["kind"] == "youtube" and tool == "yt-dlp captions":
                item["transcription_verified"] = False
            if "whisper.cpp" in tool:
                item["transcription_model"] = pathlib.Path(os.environ["WHISPER_MODEL"]).name
                item["transcription_verified"] = False
                tools.add("whisper.cpp:" + item["transcription_model"])
            sys.stdout.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
        except Exception as exc:
            message = f'{row["item_id"]}: {exc}'
            errors.append(message)
            print(message, file=sys.stderr)
            if os.environ.get("PIPELINE_DEBUG") == "1":
                traceback.print_exc(file=sys.stderr)
    receipt(run, "extract_content", started, len(candidates), count, sorted(tools), errors)
    return 1 if errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

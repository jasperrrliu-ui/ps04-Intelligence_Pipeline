"""Shared collector utilities. Collector-specific work stays in each collector."""

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import uuid
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


def now():
    return dt.datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_dir(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT) or not (path / "run.json").is_file():
        raise ValueError("RUN_DIR must be an existing run directory containing run.json")
    return path


def sources(path, kind):
    config = path / "config" / "sources.json"
    entries = json.loads(config.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("sources.json must contain an array")
    matches = []
    for entry in entries:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in ("source_id", "publisher_id", "kind", "url")):
            raise ValueError("Invalid source definition")
        if entry["kind"] == kind:
            matches.append(entry)
    return matches


def command(argv, timeout=120):
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)


def fetch_with_curl(url, destination):
    """Use the reference curl command, with HTTPS fallback for broken Windows Schannel."""
    result = command(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "45", url, "--output", str(destination)], 55)
    if result.returncode == 0:
        return "curl"
    try:
        import requests

        response = requests.get(url, timeout=45, headers={"User-Agent": "ps04-intelligence-pipeline/1.0"})
        response.raise_for_status()
        destination.write_bytes(response.content)
        return "requests (curl failed: " + (result.stderr.strip()[:160] or str(result.returncode)) + ")"
    except Exception as exc:
        raise RuntimeError((result.stderr.strip() or f"curl exit {result.returncode}") + f"; requests fallback: {exc}") from exc


def canonical_url(value):
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", parts.query, ""))


def stable_id(prefix, value):
    return prefix + ":" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def date_utc(value):
    if not value:
        return None
    try:
        stamp = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def recent_or_unverified(run, published_at):
    """Avoid extracting known old material; let the later filter assess unknown/future dates."""
    if published_at is None:
        return True
    as_of = dt.date.fromisoformat(json.loads((run / "run.json").read_text(encoding="utf-8-sig"))["as_of_date"])
    published = dt.date.fromisoformat(published_at[:10])
    return published >= as_of - dt.timedelta(days=29)


def rel(path):
    return path.resolve().relative_to(ROOT).as_posix()


def receipt(path, stage, started, input_count, output_count, tools, errors):
    logs = path / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    record = {
        "stage": stage,
        "status": "incomplete" if errors else "completed",
        "input_count": input_count,
        "output_count": output_count,
        "started_at": started,
        "finished_at": now(),
        "tools": tools,
        "cost_usd": None,
        "cost_basis": "network and compute cost not measured",
        "errors": errors,
    }
    (logs / f"{stage}-{uuid.uuid4().hex}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit(record):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")

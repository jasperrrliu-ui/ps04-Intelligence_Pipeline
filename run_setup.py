"""Validate live configuration and create immutable run snapshots."""

import datetime as dt
import json
import pathlib
import shutil
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("live", "collection_only"):
        print("Usage: run_setup.py live|collection_only", file=sys.stderr)
        return 2
    try:
        project = json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8-sig"))
        sources = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8-sig"))
        if any(not isinstance(project.get(k), str) or not project[k].strip() for k in ("publication_name", "topic", "audience", "central_question")):
            raise ValueError("config/project.json is incomplete")
        if not isinstance(sources, list) or not sources:
            raise ValueError("config/sources.json must be a nonempty array")
        for source in sources:
            if not isinstance(source, dict) or any(not isinstance(source.get(k), str) or not source[k].strip() for k in ("source_id", "publisher_id", "kind", "url")) or source["kind"] not in ("feed", "youtube", "podcast"):
                raise ValueError("Invalid source definition")
        started = dt.datetime.now(dt.timezone.utc)
        run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        path = ROOT / "runs" / run_id
        path.mkdir(parents=True, exist_ok=False)
        for folder in ("config", "prompts", "logs", "candidates"):
            (path / folder).mkdir()
        for name in ("project.json", "sources.json", "supplemental_articles.json", "material_focus.json", "editorial_policy.md"):
            shutil.copy2(ROOT / "config" / name, path / "config" / name)
        for source in (ROOT / "prompts").glob("*.md"):
            shutil.copy2(source, path / "prompts" / source.name)
        previous = sorted((ROOT / "runs").glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        previous_id = next((json.loads(p.read_text(encoding="utf-8-sig")).get("run_id") for p in previous if p.parent != path and json.loads(p.read_text(encoding="utf-8-sig")).get("mode") == "live"), None)
        metadata = {"run_id": run_id, "started_at": started.isoformat(timespec="seconds").replace("+00:00", "Z"), "as_of_date": started.date().isoformat(), "mode": sys.argv[1], "previous_run_id": previous_id}
        (path / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path.relative_to(ROOT).as_posix())
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

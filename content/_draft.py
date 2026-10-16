"""Shared evidence resolver for the distinct article and video-script writers."""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
sys.path.insert(0, str(ROOT / "editorial"))
from _common import emit, now, receipt, run_dir
from _model import generate_json


def evidence_for(run, brief):
    eligible = {row["item_id"]: row for row in (json.loads(line) for line in (run / "eligible.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip())}
    output = []
    seen = set()
    for claim in brief["claims"]:
        for ref in claim["evidence"]:
            item = eligible.get(ref["item_id"])
            if not item or item["version_id"] != ref["version_id"]:
                raise ValueError(f"Unresolved evidence: {ref['item_id']}")
            locator = ref["locator"]
            if locator["type"] == "text":
                quote = locator["quote"]
                if quote not in (ROOT / item["text_path"]).read_text(encoding="utf-8"):
                    raise ValueError("Text quote not found in retained source")
                passage, timestamp = quote, None
            elif locator["type"] == "segment":
                segments = json.loads((ROOT / item["segments_path"]).read_text(encoding="utf-8"))
                segment = next((s for s in segments if s["segment_id"] == locator["segment_id"]), None)
                if not segment:
                    raise ValueError("Transcript segment not found")
                passage, timestamp = segment["text"], segment["start_seconds"]
            else:
                raise ValueError("Unknown locator type")
            identity = (claim["claim_id"], item["item_id"], json.dumps(locator, sort_keys=True))
            if identity in seen:
                continue
            seen.add(identity)
            output.append({"claim_id": claim["claim_id"], "item_id": item["item_id"], "publisher_id": item["publisher_id"], "title": item["title"], "url": item["url"], "published_at": item["published_at"], "passage": passage, "timestamp_seconds": timestamp, "transcription_verified": item.get("transcription_verified")})
    return output


def source_references(passages):
    lines = ["## Source references", ""]
    for row in passages:
        stamp = row["timestamp_seconds"]
        url = row["url"]
        if stamp is not None and row["item_id"].startswith("youtube:"):
            url += ("&" if "?" in url else "?") + f"t={int(stamp)}s"
        time_label = ""
        if stamp is not None:
            seconds = int(stamp)
            time_label = f" ({seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d})"
        verification = " [automatic transcript: check audio]" if row["transcription_verified"] is False else ""
        lines.append(f"- [{row['claim_id']}] [{row['title']}]({url}) — {row['publisher_id']}, {row['published_at']}{time_label}{verification}")
    return "\n".join(lines)


def model_markdown(result, kind):
    body = result.get("markdown") or (result.get("article") if kind == "articles" else None) or (result.get("script") if kind == "video_scripts" and isinstance(result.get("script"), str) else None)
    if isinstance(body, str):
        return body
    if kind == "video_scripts":
        script = result.get("video_script")
        if not isinstance(script, dict):
            script = result.get("script")
    else:
        script = None
    if kind == "video_scripts" and isinstance(script, dict):
        lines = ["# " + str(script.get("title") or "Video script")]
        if script.get("duration_minutes") is not None:
            lines.extend(["", f"**Target runtime:** {script['duration_minutes']} minutes"])
        elif script.get("duration_seconds") is not None:
            lines.extend(["", f"**Target runtime:** {int(script['duration_seconds']) // 60} minutes"])
        segments = script.get("narration_and_visuals") or script.get("narration") or script.get("segments") or []
        visuals = script.get("visual_suggestions") or script.get("visuals") or []
        for index, segment in enumerate(segments):
            segment = segment if isinstance(segment, dict) else {"text": segment}
            visual = segment.get("visual")
            if not visual and isinstance(visuals, list) and index < len(visuals):
                suggestion = visuals[index]
                visual = (suggestion.get("visual") or suggestion.get("suggestion") or suggestion.get("text")) if isinstance(suggestion, dict) else suggestion
            lines.extend(["", "## " + str(segment.get("segment") or segment.get("segment_title") or f"Segment {index + 1}"), "", "**Narration:** " + str(segment.get("narration") or segment.get("text") or ""), "", "**Visual suggestion:** " + str(visual or "")])
        insight = script.get("cross_source_insight") or script.get("insights")
        if insight:
            content = "\n".join(f"- {value}" for value in insight) if isinstance(insight, list) else str(insight)
            lines.extend(["", "## Cross-source insight", "", content])
        limitation = script.get("limitation") or script.get("limitation_note") or script.get("limitation_highlight") or script.get("limitations")
        if limitation:
            content = "\n".join(f"- {value}" for value in limitation) if isinstance(limitation, list) else str(limitation)
            lines.extend(["", "## Limitation", "", content])
        return "\n".join(lines)
    return None


def write(kind):
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print(f"Usage: write_{kind}.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        briefs = [json.loads(line) for line in sys.stdin if line.strip()]
        if {row.get("piece_id") for row in briefs} != {"01", "02", "03"} or len(briefs) != 3:
            raise ValueError("Exactly three distinct briefs are required")
        prompt_name = "write_articles.md" if kind == "articles" else "write_video_scripts.md"
        prompt = (run / "prompts" / prompt_name).read_text(encoding="utf-8")
        project = json.loads((run / "config" / "project.json").read_text(encoding="utf-8-sig"))
        if not prompt.strip():
            raise ValueError("Writing prompt is empty")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, count, errors, models = now(), 0, [], set()
    folder = run / kind
    folder.mkdir(exist_ok=True)
    try:
        for brief in briefs:
            passages = evidence_for(run, brief)
            result, model, _, _ = generate_json(run, "write_" + kind, prompt, {"project": project, "brief": brief, "source_passages": passages}, 6500)
            models.add(model)
            markdown = model_markdown(result, kind)
            claim_ids = result.get("claim_ids")
            if kind == "video_scripts" and not isinstance(claim_ids, list):
                claim_ids = result.get("claims_used") or result.get("claim_ids_used")
            if kind == "video_scripts" and not isinstance(claim_ids, list):
                script = result.get("video_script") or result.get("script")
                notes = (script.get("source_notes") or script.get("sources") or script.get("sources_and_timestamps") or script.get("sources_and_media")) if isinstance(script, dict) else None
                if isinstance(notes, list):
                    claim_ids = sorted({claim_id for note in notes for claim_id in re.findall(r"\b\d\d-c\d+\b", json.dumps(note, ensure_ascii=False))})
            known = {row["claim_id"] for row in brief["claims"]}
            if isinstance(markdown, str) and isinstance(claim_ids, list):
                missing_markers = [claim_id for claim_id in claim_ids if f"[{claim_id}]" not in markdown]
                if missing_markers:
                    marker_heading = "## Claim markers" if kind == "video_scripts" else "## Claim references"
                    markdown = markdown.rstrip() + f"\n\n{marker_heading}\n\n" + " ".join(f"[{claim_id}]" for claim_id in missing_markers)
            if not isinstance(claim_ids, list) and isinstance(markdown, str):
                claim_ids = sorted(set(re.findall(r"\[(\d\d-c\d+)\]", markdown)))
            if not isinstance(markdown, str) or len(markdown.strip()) < 500 or not isinstance(claim_ids, list) or not claim_ids or any(x not in known or f"[{x}]" not in markdown for x in claim_ids):
                raise ValueError(f"Invalid {kind} output for piece {brief['piece_id']}")
            path = folder / (brief["piece_id"] + ".md")
            path.write_text(markdown.strip() + "\n\n" + source_references(passages) + "\n", encoding="utf-8")
            emit({"piece_id": brief["piece_id"], "path": path.relative_to(ROOT).as_posix(), "claim_ids": claim_ids})
            count += 1
    except Exception as exc:
        errors.append(str(exc))
        print(exc, file=sys.stderr)
    receipt(run, "write_" + kind, started, 3, count, ["OpenAI Responses API:" + x for x in sorted(models)], errors)
    return 1 if errors else 0

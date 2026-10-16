"""Deterministic assessment of drafts, citations, freshness, and coverage."""

import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import now, receipt, run_dir
sys.path.insert(0, str(ROOT / "processing"))
from filter_items import reason as window_exclusion


def read_jsonl(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def fingerprint(run, briefs, articles, scripts):
    digest = hashlib.sha256()
    paths = [run / "run.json", run / "briefs.jsonl", run / "articles.jsonl", run / "video_scripts.jsonl"]
    for record in articles + scripts:
        paths.append(ROOT / record["path"])
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    for brief in briefs:
        for claim in brief.get("claims", []):
            for ref in claim.get("evidence", []):
                digest.update(json.dumps(ref, ensure_ascii=False, sort_keys=True).encode())
    return digest.hexdigest()[:32]


def main():
    if len(sys.argv) != 2:
        print("Usage: check_content.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        started = now()
        metadata = json.loads((run / "run.json").read_text(encoding="utf-8-sig"))
        shortlist = read_jsonl(run / "material_shortlist.jsonl")
        eligible = {x["item_id"]: x for x in read_jsonl(run / "eligible.jsonl")}
        decisions = {x["item_id"]: x for x in read_jsonl(run / "decisions.jsonl")}
        briefs = read_jsonl(run / "briefs.jsonl")
        articles = read_jsonl(run / "articles.jsonl")
        scripts = read_jsonl(run / "video_scripts.jsonl")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    issues = []

    def issue(severity, artifact, explanation):
        issues.append({"severity": severity, "artifact": artifact, "explanation": explanation})

    kinds = collections.Counter(x.get("kind") for x in shortlist)
    if len({x.get("item_id") for x in shortlist}) < 12 or len({x.get("publisher_id") for x in shortlist}) < 6 or any(kinds[k] < 2 for k in ("feed", "youtube", "podcast")):
        issue("error", "material_shortlist.jsonl", "Collection focus lacks 12 items, six publishers, or two each of RSS, YouTube and Podcast")
    as_of = dt.date.fromisoformat(metadata["as_of_date"])
    for focused in shortlist:
        item = eligible.get(focused.get("item_id"))
        if not item or item.get("version_id") != focused.get("version_id"):
            issue("error", "material_shortlist.jsonl", f"Focused item is absent or has a different version: {focused.get('item_id')}")
            continue
        exclusion = window_exclusion(item, as_of)
        if exclusion:
            issue("error", "material_shortlist.jsonl", f"Focused item fails the 30-day UTC window: {item['item_id']} ({exclusion})")
        if item.get("kind") in ("youtube", "podcast") and (not item.get("segments_path") or not (ROOT / item["segments_path"]).is_file()):
            issue("error", "material_shortlist.jsonl", f"Media item lacks retained timestamped segments: {item['item_id']}")
        if item.get("kind") in ("youtube", "podcast") and (not item.get("raw_media_path") or not (ROOT / item["raw_media_path"]).is_file()):
            issue("error", "material_shortlist.jsonl", f"Media item lacks retained audio: {item['item_id']}")
    if any(len(records) != 3 or {x.get("piece_id") for x in records} != {"01", "02", "03"} for records in (briefs, articles, scripts)):
        issue("error", "series", "Exactly three distinct briefs, articles, and video scripts are required")
    article_by_id = {x.get("piece_id"): x for x in articles}
    script_by_id = {x.get("piece_id"): x for x in scripts}
    used_kinds = set()
    for brief in briefs:
        pid = brief.get("piece_id")
        claims = brief.get("claims", [])
        claim_ids = {x.get("claim_id") for x in claims}
        cited_publishers = set()
        if not brief.get("argument") or not brief.get("synthesis") or not brief.get("limitations") or not any(x.get("type") == "inference" for x in claims):
            issue("error", pid, "Brief needs an argument, synthesis, limitation, and inference claim")
        for claim in claims:
            if not claim.get("evidence"):
                issue("error", pid, f"Claim {claim.get('claim_id')} has no evidence")
            for ref in claim.get("evidence", []):
                item = eligible.get(ref.get("item_id"))
                if not item or item.get("version_id") != ref.get("version_id"):
                    issue("error", pid, f"Unresolved source version for {claim.get('claim_id')}")
                    continue
                decision = decisions.get(item["item_id"])
                if not decision or decision.get("decision") != "accept":
                    issue("error", pid, f"Cited item was not accepted: {item['item_id']}")
                cited_publishers.add(item["publisher_id"])
                used_kinds.add(item["kind"])
                locator = ref.get("locator", {})
                if locator.get("type") == "text":
                    if not locator.get("quote") or locator["quote"] not in (ROOT / item["text_path"]).read_text(encoding="utf-8"):
                        issue("error", pid, f"Text quote cannot be found for {claim.get('claim_id')}")
                elif locator.get("type") == "segment":
                    segments = json.loads((ROOT / item["segments_path"]).read_text(encoding="utf-8")) if item.get("segments_path") else []
                    matched = next((x for x in segments if x.get("segment_id") == locator.get("segment_id")), None)
                    if not matched:
                        issue("error", pid, f"Transcript segment cannot be found for {claim.get('claim_id')}")
                    elif ref.get("start_seconds") is not None and abs(float(ref["start_seconds"]) - float(matched["start_seconds"])) > 0.1:
                        issue("error", pid, f"Transcript timestamp mismatch for {claim.get('claim_id')}")
                    if item.get("transcription_verified") is False:
                        issue("warning", pid, f"Verify ASR passage against original media: {item['item_id']} {locator.get('segment_id')}")
                else:
                    issue("error", pid, "Evidence locator is missing or invalid")
        if len(cited_publishers) < 3:
            issue("error", pid, "Piece cites fewer than three independent publishers")
        for label, manifest in (("article", article_by_id.get(pid)), ("video_script", script_by_id.get(pid))):
            if not manifest or not manifest.get("path") or not (ROOT / manifest["path"]).is_file():
                issue("error", pid, f"Missing {label} file or manifest")
                continue
            body = (ROOT / manifest["path"]).read_text(encoding="utf-8")
            if any(cid not in claim_ids or f"[{cid}]" not in body for cid in manifest.get("claim_ids", [])) or not manifest.get("claim_ids"):
                issue("error", pid, f"{label} claim markers are missing or unknown")
            if label == "article" and not 600 <= len(body.split()) <= 1200:
                issue("warning", pid, "Check article length against the 600–900 word target; Chinese word counting needs human review")
            if label == "video_script" and not 300 <= len(body.split()) <= 1000:
                issue("warning", pid, "Check video narration against the 3–5 minute target")
    if not {"feed", "youtube", "podcast"}.issubset(used_kinds):
        issue("error", "series", "All three required input types must contribute cited evidence to the series")
    issue("warning", "human_review", "A person must verify interpretation, commercial incentives, critical ASR passages, and final publication wording")
    try:
        review_id = fingerprint(run, briefs, articles, scripts)
    except (OSError, KeyError) as exc:
        print(exc, file=sys.stderr)
        return 1
    result = {"review_id": review_id, "passed": not any(x["severity"] == "error" for x in issues), "issues": issues, "as_of_date": metadata["as_of_date"]}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    receipt(run, "check_content", started, len(briefs), 1, ["python:json", "python:hashlib"], [])
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

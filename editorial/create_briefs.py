"""Build three argument briefs from accepted, passage-level evidence."""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import emit, now, receipt, run_dir
from _model import generate_json

QUESTIONS = {
    "01": "What changed in recent professional scenic and lighting practice, and which developments matter to beginners?",
    "02": "Which claims about learning and AI-assisted stage design withstand scrutiny, and where does evidence conflict or remain thin?",
    "03": "What do these findings imply for a beginner-facing AI stage-design app, and what should readers watch next?",
}
TERMS = re.compile(r"design|stage|scenic|set|lighting|light|rehears|audience|script|cue|space|AI|model|tool|collaborat|constraint", re.I)


def passages(item):
    if item.get("segments_path"):
        segments = json.loads((ROOT / item["segments_path"]).read_text(encoding="utf-8"))
        ranked = sorted(segments, key=lambda row: (len(TERMS.findall(row.get("text", ""))), len(row.get("text", ""))), reverse=True)
        chosen = sorted(ranked[:25], key=lambda row: row["start_seconds"])
        return [{"item_id": item["item_id"], "version_id": item["version_id"], "publisher_id": item["publisher_id"], "kind": item["kind"], "url": item["url"], "transcription_verified": item.get("transcription_verified"), "locator": {"type": "segment", "segment_id": row["segment_id"]}, "start_seconds": row["start_seconds"], "passage": row["text"]} for row in chosen]
    lines = [line.strip() for line in (ROOT / item["text_path"]).read_text(encoding="utf-8").splitlines() if len(line.strip()) >= 45]
    ranked = sorted(lines, key=lambda line: (len(TERMS.findall(line)), len(line)), reverse=True)
    return [{"item_id": item["item_id"], "version_id": item["version_id"], "publisher_id": item["publisher_id"], "kind": item["kind"], "url": item["url"], "locator": {"type": "text", "quote": line}, "passage": line} for line in ranked[:8]]


def key(reference):
    return json.dumps({"item_id": reference.get("item_id"), "version_id": reference.get("version_id"), "locator": reference.get("locator")}, ensure_ascii=False, sort_keys=True)


def main():
    if len(sys.argv) != 2:
        print("Usage: create_briefs.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        decisions = [json.loads(line) for line in sys.stdin if line.strip()]
        eligible = {row["item_id"]: row for row in (json.loads(line) for line in (run / "eligible.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip())}
        project = json.loads((run / "config" / "project.json").read_text(encoding="utf-8-sig"))
        policy = (run / "config" / "editorial_policy.md").read_text(encoding="utf-8")
        prompt = (run / "prompts" / "create_briefs.md").read_text(encoding="utf-8")
        if not decisions or not prompt.strip() or not policy.strip():
            raise ValueError("Decisions, policy, and brief prompt are required")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, count, errors, models = now(), 0, [], set()
    try:
        for piece_id, question in QUESTIONS.items():
            chosen = [eligible[row["item_id"]] for row in decisions if row.get("decision") == "accept" and piece_id in row.get("piece_ids", []) and row.get("item_id") in eligible]
            if len({row["publisher_id"] for row in chosen}) < 3:
                raise ValueError(f"Piece {piece_id} has fewer than three accepted independent publishers")
            evidence = [p for item in chosen for p in passages(item)]
            evidence_by_id = {f"e{index:04d}": passage for index, passage in enumerate(evidence, 1)}
            model_evidence = [{"evidence_id": evidence_id, "item_id": passage["item_id"], "kind": passage["kind"], "publisher_id": passage["publisher_id"], "url": passage["url"], "passage": passage["passage"], "start_seconds": passage.get("start_seconds"), "transcription_verified": passage.get("transcription_verified")} for evidence_id, passage in evidence_by_id.items()]
            result, model, _, _ = generate_json(run, "create_briefs", prompt, {"project": project, "policy": policy, "piece_id": piece_id, "question": question, "evidence": model_evidence}, 6500)
            models.add(model)
            if result.get("piece_id") != piece_id or not isinstance(result.get("claims"), list) or not result["claims"]:
                raise ValueError(f"Piece {piece_id} brief is incomplete")
            for field in ("title", "question", "argument", "synthesis", "limitations"):
                if not isinstance(result.get(field), str) or not result[field].strip():
                    raise ValueError(f"Piece {piece_id} missing {field}")
            publishers = set()
            for index, claim in enumerate(result["claims"], 1):
                if claim.get("type") not in ("reported_fact", "source_claim", "inference") or not claim.get("statement") or not claim.get("evidence"):
                    raise ValueError(f"Piece {piece_id} has invalid claim")
                claim["claim_id"] = f"{piece_id}-c{index}"
                resolved = []
                for reference in claim["evidence"]:
                    evidence_id = reference if isinstance(reference, str) else reference.get("evidence_id") if isinstance(reference, dict) else None
                    passage = evidence_by_id.get(evidence_id)
                    if not passage:
                        raise ValueError(f"Piece {piece_id} cites an unavailable evidence_id: {evidence_id}")
                    resolved.append({"item_id": passage["item_id"], "version_id": passage["version_id"], "locator": passage["locator"], **({"start_seconds": passage["start_seconds"]} if "start_seconds" in passage else {})})
                    publishers.add(passage["publisher_id"])
                claim["evidence"] = resolved
            if len(publishers) < 3 or not any(claim["type"] == "inference" for claim in result["claims"]):
                raise ValueError(f"Piece {piece_id} needs three cited publishers and a synthesis inference")
            emit(result)
            count += 1
    except Exception as exc:
        errors.append(str(exc))
        print(exc, file=sys.stderr)
    receipt(run, "create_briefs", started, len(decisions), count, ["OpenAI Responses API:" + x for x in sorted(models)], errors)
    return 1 if errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

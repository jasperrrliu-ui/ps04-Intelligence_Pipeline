"""AI editorial selection for every mechanically eligible item."""

import json
import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import emit, now, receipt, run_dir
from _model import generate_json

KEYWORDS = re.compile(r"stage|scenic|set design|lighting|light cue|rehears|audience|theat|theater|dramaturg|director|design process|artificial intelligence|\bAI\b", re.I)
STRONG = re.compile(r"set design|scenic design|lighting design|stage design|lighting cue|design process|space|audience|mood|script|visual|designer|collaborat|production", re.I)


def sample(item):
    path = ROOT / item["text_path"]
    if not path.is_file():
        raise ValueError(f"Missing retained text: {item['text_path']}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return ""
    scored = []
    for index, line in enumerate(lines):
        score = 2 * len(STRONG.findall(line)) + len(KEYWORDS.findall(line))
        if score:
            scored.append((score, index))
    chosen = {index for _, index in sorted(scored, reverse=True)[:12]}
    chosen.update(range(min(2, len(lines))))
    for index in list(chosen):
        if index + 1 < len(lines):
            chosen.add(index + 1)
    return "\n".join(f"line {index + 1}: {lines[index][:420]}" for index in sorted(chosen))[:4800]


def main():
    if len(sys.argv) != 2:
        print("Usage: select_items.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        rows = [json.loads(line) for line in sys.stdin if line.strip()]
        if not rows or any(not row.get("item_id") or not row.get("version_id") or not row.get("text_path") for row in rows):
            raise ValueError("Eligible input is empty or malformed")
        project = json.loads((run / "config" / "project.json").read_text(encoding="utf-8-sig"))
        policy = (run / "config" / "editorial_policy.md").read_text(encoding="utf-8")
        prompt = (run / "prompts" / "select_items.md").read_text(encoding="utf-8")
        if not policy.strip() or not prompt.strip():
            raise ValueError("Editorial policy and selection prompt are required")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    started, errors, models, count = now(), [], set(), 0
    try:
        for offset in range(0, len(rows), 8):
            batch = rows[offset:offset + 8]
            payload = {
                "project": project,
                "as_of_date": json.loads((run / "run.json").read_text(encoding="utf-8"))["as_of_date"],
                "window_start_date": (dt.date.fromisoformat(json.loads((run / "run.json").read_text(encoding="utf-8"))["as_of_date"]) - dt.timedelta(days=29)).isoformat(),
                "all_items_mechanically_date_eligible": True,
                "policy": policy,
                "items": [{"item_id": row["item_id"], "version_id": row["version_id"], "kind": row["kind"], "title": row["title"], "publisher_id": row["publisher_id"], "published_at": row["published_at"], "source_interest": row.get("source_interest"), "transcription_verified": row.get("transcription_verified"), "excerpt": sample(row)} for row in batch],
            }
            result, model, _, _ = generate_json(run, "select_items", prompt, payload, 4500)
            models.add(model)
            decisions = result.get("decisions")
            if not isinstance(decisions, list) or {row.get("item_id") for row in decisions} != {row["item_id"] for row in batch}:
                raise ValueError("Model did not decide exactly once for every batch item")
            by_id = {row["item_id"]: row for row in decisions}
            for item in batch:
                decision = by_id[item["item_id"]]
                if decision.get("decision") not in ("accept", "reject", "defer") or not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
                    raise ValueError(f"Invalid decision for {item['item_id']}")
                # Selection is the model's decision. Fixed-series eligibility is
                # deterministic: every accepted source can be considered by each
                # of the three briefs, which choose their actual cited evidence.
                piece_ids = ["01", "02", "03"] if decision["decision"] == "accept" else []
                emit({"item_id": item["item_id"], "version_id": item["version_id"], "decision": decision["decision"], "reason": decision["reason"], "piece_ids": piece_ids, "piece_assignment_method": "fixed_series_scope"})
                count += 1
    except Exception as exc:
        errors.append(str(exc))
        print(exc, file=sys.stderr)
    receipt(run, "select_items", started, len(rows), count, ["OpenAI Responses API:" + x for x in sorted(models)], errors)
    return 1 if errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

"""Describe completed and incomplete runs without implying publication."""

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import now, receipt, run_dir


def rows(path):
    if not path.is_file():
        return None
    return [json.loads(line) for line in path.open(encoding="utf-8-sig") if line.strip()]


def estimated_api_usage(run):
    """Estimate model token charges; this is not a billing receipt."""
    rates = {"gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60}}
    totals = collections.Counter()
    unknown_models = set()
    for path in (run / "model_calls").glob("*/*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        model = record.get("request", {}).get("model")
        usage = record.get("response", {}).get("usage") or {}
        if model not in rates or not usage:
            unknown_models.add(model or "unknown")
            continue
        totals["calls"] += 1
        totals["input_tokens"] += usage.get("input_tokens", 0)
        totals["cached_input_tokens"] += (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
        totals["output_tokens"] += usage.get("output_tokens", 0)
    price = rates["gpt-4.1-mini"]
    uncached = totals["input_tokens"] - totals["cached_input_tokens"]
    amount = (uncached * price["input"] + totals["cached_input_tokens"] * price["cached_input"] + totals["output_tokens"] * price["output"]) / 1_000_000
    return {"estimated_usd": round(amount, 6), **dict(totals), "unknown_models": sorted(unknown_models), "basis": "Saved Responses API usage; gpt-4.1-mini standard rates in USD per 1M tokens: input 0.40, cached input 0.10, output 1.60. Excludes local compute, network, tax, and prior runs.", "pricing_source": "https://developers.openai.com/api/docs/models/gpt-4.1-mini"}


def main():
    if len(sys.argv) != 2:
        print("Usage: summarize_run.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        metadata = json.loads((run / "run.json").read_text(encoding="utf-8-sig"))
        candidates = rows(run / "candidates.jsonl")
        items = rows(run / "items.jsonl")
        changes = rows(run / "changes.jsonl")
        eligible = rows(run / "eligible.jsonl")
        exclusions = rows(run / "exclusions.jsonl")
        decisions = rows(run / "decisions.jsonl")
        focused = rows(run / "material_shortlist.jsonl")
        articles = rows(run / "articles.jsonl")
        scripts = rows(run / "video_scripts.jsonl")
        stages = json.loads((run / "collection_status.json").read_text(encoding="utf-8")) if (run / "collection_status.json").is_file() else {}
        series_stages = json.loads((run / "series_status.json").read_text(encoding="utf-8")) if (run / "series_status.json").is_file() else {}
        stages.update(series_stages)
        receipt_files = sorted((run / "logs").glob("*.json"), key=lambda p: p.stat().st_mtime)
        receipts = [json.loads(p.read_text(encoding="utf-8")) for p in receipt_files]
        latest_receipts = {row.get("stage"): row for row in receipts}
        failed = [{"stage": k, "exit_code": v} for k, v in stages.items() if v is not None and v != 0]
        recovered_ids = {row.get("item_id") for row in (items or [])}
        historical_extraction_errors = {error for row in receipts if row.get("stage") == "extract_content" for error in row.get("errors", [])}
        unresolved_extraction_errors = {error for error in historical_extraction_errors if error.split(": ", 1)[0] not in recovered_ids}
        for receipt_data in latest_receipts.values():
            if receipt_data.get("status") != "completed" and not any(f["stage"] == receipt_data.get("stage") for f in failed):
                errors = receipt_data.get("errors", [])
                if receipt_data.get("stage") == "extract_content":
                    errors = [error for error in errors if error in unresolved_extraction_errors]
                if errors:
                    entry = {"stage": receipt_data.get("stage"), "status": receipt_data.get("status"), "errors": errors}
                    if receipt_data.get("stage") == "extract_content":
                        entry["note"] = "Historical errors; remaining candidates have not been retried after transcription tools became available."
                    failed.append(entry)
        if metadata["mode"] == "collection_only":
            failed.append({"stage": "series", "status": "not_run_by_collection_only_mode"})
        coverage = collections.Counter(row.get("kind") for row in (eligible or []))
        publishers = {row.get("publisher_id") for row in (eligible or []) if row.get("publisher_id")}
        counts = {
            "discovered": len(candidates) if candidates is not None else None,
            "extracted": len(items) if items is not None else None,
            "new": sum(row.get("change") == "new" for row in changes) if changes is not None else None,
            "changed": sum(row.get("change") == "changed" for row in changes) if changes is not None else None,
            "unchanged": sum(row.get("change") == "unchanged" for row in changes) if changes is not None else None,
            "eligible": len(eligible) if eligible is not None else None,
            "focused_materials": len(focused) if focused is not None else None,
            "excluded": len(exclusions) if exclusions is not None else None,
            "accepted": sum(row.get("decision") == "accept" for row in decisions) if decisions is not None else None,
            "rejected": sum(row.get("decision") == "reject" for row in decisions) if decisions is not None else None,
            "deferred": sum(row.get("decision") == "defer" for row in decisions) if decisions is not None else None,
            "articles": len(articles) if articles is not None else None,
            "video_scripts": len(scripts) if scripts is not None else None,
        }
        review = json.loads((run / "review.json").read_text(encoding="utf-8-sig")) if (run / "review.json").is_file() and (run / "review.json").stat().st_size else None
        package_ready = (run / "package" / "manifest.json").is_file()
        if failed or metadata["mode"] == "collection_only" or not review or not review.get("passed"):
            status = "failed"
        elif package_ready:
            status = "ready_for_production"
        else:
            status = "awaiting_review"
        approval_path = run / "approval.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8-sig")) if approval_path.is_file() else {}
        approval_current = bool(review and approval.get("review_id") == review.get("review_id") and approval.get("decision") == "approve")
        manual_actions = []
        if not approval_current:
            manual_actions.extend(["Review AI editorial choices and ASR passages", "Write approval.json after reviewing the current passing review"])
        else:
            manual_actions.append("Produce three videos in Google Vids or HeyGen and publish three Substack/YouTube pairs")
        live_dates = set()
        for candidate in (ROOT / "runs").iterdir():
            run_file = candidate / "run.json"
            if not candidate.is_dir() or not run_file.is_file():
                continue
            try:
                candidate_meta = json.loads(run_file.read_text(encoding="utf-8-sig"))
                if candidate_meta.get("mode") == "live":
                    live_dates.add(candidate_meta.get("as_of_date"))
            except (OSError, ValueError):
                continue
        if len(live_dates) < 2:
            manual_actions.append("Complete a second live run on a different UTC date")
        manual_actions.append("Record a separate 4–6 minute technical demonstration")
        if metadata["mode"] == "collection_only":
            manual_actions.insert(0, "Run AI selection, three briefs, article drafts, video scripts, and content checks in a live run")
        output = {
            "run_id": metadata["run_id"],
            "as_of_date": metadata["as_of_date"],
            "mode": metadata["mode"],
            "status": status,
            "counts": counts,
            "coverage": {"by_kind": dict(coverage), "independent_publishers": len(publishers), "duplicate_observations": len(candidates) - len({row.get("item_id") for row in candidates}) if candidates is not None else None},
            "focused_coverage": {"by_kind": dict(collections.Counter(row.get("kind") for row in (focused or []))), "independent_publishers": len({row.get("publisher_id") for row in (focused or [])}) if focused is not None else None},
            "failed_or_incomplete_stages": failed,
            "recovered_collection_items": len(historical_extraction_errors - unresolved_extraction_errors),
            "unresolved_collection_items": len(unresolved_extraction_errors),
            "tools": sorted({tool for row in receipts for tool in row.get("tools", [])}),
            "known_cost_usd": sum(row["cost_usd"] for row in receipts if row.get("cost_usd") is not None) if any(row.get("cost_usd") is not None for row in receipts) else None,
            "estimated_model_api_cost": estimated_api_usage(run),
            "unknown_cost_stages": [row.get("stage") for row in receipts if row.get("cost_usd") is None],
            "finished_at": now(),
            "remaining_manual_actions": manual_actions,
        }
        sys.stdout.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        receipt(run, "summarize_run", now(), len(receipts), 1, ["python:json"], [])
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

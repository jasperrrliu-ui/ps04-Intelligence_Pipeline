"""Create production handoff only after a current passing check and human approval."""

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
sys.path.insert(0, str(ROOT / "review"))
from _common import now, receipt, run_dir
from check_content import fingerprint, read_jsonl


def main():
    if len(sys.argv) != 2:
        print("Usage: prepare_package.sh RUN_DIR", file=sys.stderr)
        return 2
    try:
        run = run_dir(sys.argv[1])
        started = now()
        review = json.loads((run / "review.json").read_text(encoding="utf-8-sig"))
        approval = json.loads((run / "approval.json").read_text(encoding="utf-8-sig"))
        briefs = read_jsonl(run / "briefs.jsonl")
        articles = read_jsonl(run / "articles.jsonl")
        scripts = read_jsonl(run / "video_scripts.jsonl")
        eligible = {row["item_id"]: row for row in read_jsonl(run / "eligible.jsonl")}
        if not review.get("passed") or review.get("review_id") != fingerprint(run, briefs, articles, scripts):
            raise ValueError("Review is failed or stale")
        if approval.get("review_id") != review["review_id"] or approval.get("decision") != "approve" or not all(approval.get(k) for k in ("reviewer", "reviewed_at", "notes")):
            raise ValueError("Matching human approval is required")
        if {x.get("piece_id") for x in briefs} != {"01", "02", "03"}:
            raise ValueError("Three briefs are required")
        package = run / "package"
        package.mkdir(exist_ok=True)
        (package / "articles").mkdir(exist_ok=True)
        (package / "video_scripts").mkdir(exist_ok=True)
        (package / "source_notes").mkdir(exist_ok=True)
        assets = []
        for pid in ("01", "02", "03"):
            for label, records, folder in (("article", articles, "articles"), ("video_script", scripts, "video_scripts")):
                record = next((x for x in records if x["piece_id"] == pid), None)
                if not record:
                    raise ValueError(f"Missing {label} for {pid}")
                target = package / folder / (pid + ".md")
                shutil.copy2(ROOT / record["path"], target)
                assets.append({"piece_id": pid, "type": label, "path": target.relative_to(ROOT).as_posix()})
            brief = next(x for x in briefs if x["piece_id"] == pid)
            refs = []
            for claim in brief["claims"]:
                for evidence in claim["evidence"]:
                    item = eligible[evidence["item_id"]]
                    if item["version_id"] != evidence["version_id"]:
                        raise ValueError(f"Stale source version in piece {pid}")
                    refs.append({**evidence, "claim_id": claim["claim_id"], "claim_type": claim["type"], "claim": claim["statement"], "source_title": item["title"], "publisher_id": item["publisher_id"], "kind": item["kind"], "url": item["url"], "published_at": item["published_at"], "version_id": item["version_id"], "transcription_verified": item.get("transcription_verified")})
            target = package / "source_notes" / (pid + ".json")
            target.write_text(json.dumps(refs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            assets.append({"piece_id": pid, "type": "source_notes", "path": target.relative_to(ROOT).as_posix()})
        links = package / "publication_links.json"
        if not links.exists():
            links.write_text(json.dumps([{"piece_id": pid, "substack_url": None, "youtube_url": None} for pid in ("01", "02", "03")], indent=2) + "\n", encoding="utf-8")
        manifest = {"review_id": review["review_id"], "assets": assets, "publication_links_path": links.relative_to(ROOT).as_posix(), "manual_steps": ["Produce three videos in Google Vids or HeyGen from the scripts", "Publish three Substack articles and three YouTube videos", "Link each article and video, verify access, and update publication_links.json"]}
        (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sys.stdout.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        receipt(run, "prepare_package", started, 3, 1, ["python:json", "python:shutil"], [])
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

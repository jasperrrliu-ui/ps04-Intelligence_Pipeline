"""The sole owner of the persistent evidence index."""

import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from _common import emit, now, receipt, run_dir

DB = ROOT / "data" / "evidence" / "index.sqlite3"


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS versions (item_id TEXT NOT NULL, version_id TEXT NOT NULL, record_json TEXT NOT NULL, first_seen_at TEXT NOT NULL, PRIMARY KEY (item_id, version_id))")
    db.execute("CREATE TABLE IF NOT EXISTS latest (item_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, updated_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS observations (run_id TEXT NOT NULL, item_id TEXT NOT NULL, version_id TEXT NOT NULL, observed_at TEXT NOT NULL, PRIMARY KEY (run_id, item_id, version_id))")
    db.commit()
    return db


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("init", "upsert", "list", "get"):
        print("Usage: store.sh init | upsert RUN_DIR | list | get ITEM_ID [VERSION_ID]", file=sys.stderr)
        return 2
    mode = sys.argv[1]
    if mode == "upsert" and len(sys.argv) != 3:
        print("upsert requires RUN_DIR", file=sys.stderr)
        return 2
    if mode == "get" and len(sys.argv) not in (3, 4):
        print("get requires ITEM_ID [VERSION_ID]", file=sys.stderr)
        return 2
    if mode in ("init", "list") and len(sys.argv) != 2:
        return 2
    try:
        run = run_dir(sys.argv[2]) if mode == "upsert" else None
        db = connect()
        if mode == "init":
            return 0
        if mode == "upsert":
            started, count = now(), 0
            run_id = json.loads((run / "run.json").read_text(encoding="utf-8-sig"))["run_id"]
            with db:
                for line in sys.stdin:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if not isinstance(item, dict) or any(not item.get(k) for k in ("item_id", "version_id", "text_path")):
                        raise ValueError("Malformed item")
                    item_id, version_id = item["item_id"], item["version_id"]
                    previous = db.execute("SELECT version_id FROM latest WHERE item_id=?", (item_id,)).fetchone()
                    known = db.execute("SELECT record_json FROM versions WHERE item_id=? AND version_id=?", (item_id, version_id)).fetchone()
                    change = "new" if previous is None else "unchanged" if previous[0] == version_id else "changed"
                    if not known:
                        db.execute("INSERT INTO versions VALUES (?,?,?,?)", (item_id, version_id, json.dumps(item, ensure_ascii=False), now()))
                    else:
                        # Metadata such as a newly retained audio path can improve
                        # without changing the content-addressed evidence version.
                        stored = json.loads(known[0])
                        stored.update({key: value for key, value in item.items() if value is not None})
                        db.execute("UPDATE versions SET record_json=? WHERE item_id=? AND version_id=?", (json.dumps(stored, ensure_ascii=False), item_id, version_id))
                    db.execute("INSERT INTO latest VALUES (?,?,?) ON CONFLICT(item_id) DO UPDATE SET version_id=excluded.version_id, updated_at=excluded.updated_at", (item_id, version_id, now()))
                    db.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?)", (run_id, item_id, version_id, now()))
                    emit({"item_id": item_id, "version_id": version_id, "change": change})
                    count += 1
            receipt(run, "store_upsert", started, count, count, ["python:sqlite3"], [])
            return 0
        if mode == "list":
            for (record,) in db.execute("SELECT v.record_json FROM versions v JOIN latest l ON v.item_id=l.item_id AND v.version_id=l.version_id ORDER BY v.item_id"):
                emit(json.loads(record))
            return 0
        item_id = sys.argv[2]
        version_id = sys.argv[3] if len(sys.argv) == 4 else None
        query = "SELECT record_json FROM versions WHERE item_id=? AND version_id=?" if version_id else "SELECT v.record_json FROM versions v JOIN latest l ON v.item_id=l.item_id AND v.version_id=l.version_id WHERE v.item_id=?"
        row = db.execute(query, (item_id, version_id) if version_id else (item_id,)).fetchone()
        if not row:
            print(f"Evidence not found: {item_id} {version_id or ''}", file=sys.stderr)
            return 1
        emit(json.loads(row[0]))
        return 0
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

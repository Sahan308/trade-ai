"""Logical database backup: every table to gzipped JSON Lines, keeping the newest N files.

    python -m app.backup                 # write /srv/backups/tradeai-YYYYmmdd-HHMMSS.jsonl.gz
    python -m app.backup --restore FILE  # load into an EMPTY database (after `alembic upgrade head`)

Each line is {"table": name, "row": {...}}. Neon also keeps its own point-in-time history; this is an
independent copy stored off the database host."""
import argparse
import base64
import datetime as dt
import gzip
import json
import os
import pathlib
import sys

from sqlalchemy import MetaData, insert, select, text

from .db import get_engine

DEFAULT_DIR = os.environ.get("TRADEAI_BACKUP_DIR", "/srv/backups")
SKIP = {"alembic_version", "daily_visitors"}  # visitor hashes are temporary by design


def _enc(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__b64__": base64.b64encode(bytes(v)).decode()}
    return v


def backup(out_dir: str = DEFAULT_DIR, keep: int = 14) -> pathlib.Path:
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    md = MetaData()
    eng = get_engine()
    md.reflect(eng)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp = d / f".tradeai-{stamp}.jsonl.gz.part"
    counts = {}
    with eng.connect() as c, gzip.open(tmp, "wt", encoding="utf-8") as f:
        for t in md.sorted_tables:
            if t.name in SKIP:
                continue
            n = 0
            for row in c.execute(select(t)).mappings():
                f.write(json.dumps({"table": t.name, "row": {k: _enc(v) for k, v in row.items()}}, default=str) + "\n")
                n += 1
            counts[t.name] = n
    final = d / f"tradeai-{stamp}.jsonl.gz"
    tmp.rename(final)
    os.chmod(final, 0o600)
    old = sorted(d.glob("tradeai-*.jsonl.gz"))[:-keep] if keep > 0 else []
    for p in old:
        p.unlink()
    print(json.dumps({"file": str(final), "bytes": final.stat().st_size, "rows": counts, "pruned": len(old)}))
    return final


def restore(path: str) -> None:
    md = MetaData()
    eng = get_engine()
    md.reflect(eng)
    rows: dict[str, list] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.setdefault(r["table"], []).append(r["row"])
    with eng.begin() as c:
        for t in md.sorted_tables:
            if t.name in rows:
                if c.execute(select(t).limit(1)).first():
                    sys.exit(f"Refusing to restore: table {t.name} is not empty")
                vals = []
                for r in rows[t.name]:
                    for col in t.columns:
                        v = r.get(col.name)
                        if isinstance(v, dict) and "__b64__" in v:
                            r[col.name] = base64.b64decode(v["__b64__"])
                        elif isinstance(v, str) and col.type.python_type in (dt.datetime, dt.date):
                            r[col.name] = dt.datetime.fromisoformat(v) if col.type.python_type is dt.datetime else dt.date.fromisoformat(v)
                    vals.append(r)
                c.execute(insert(t), vals)
        if eng.dialect.name == "postgresql":  # move id sequences past restored rows
            for t in md.sorted_tables:
                for col in t.columns:
                    if col.autoincrement is True or (col.primary_key and col.type.python_type is int):
                        c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', '{col.name}'), "
                                       f"COALESCE((SELECT MAX({col.name}) FROM {t.name}), 0) + 1, false)"))
    print(json.dumps({"restored": {k: len(v) for k, v in rows.items()}}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--keep", type=int, default=14)
    ap.add_argument("--restore")
    a = ap.parse_args()
    restore(a.restore) if a.restore else backup(a.dir, a.keep)


if __name__ == "__main__":
    main()

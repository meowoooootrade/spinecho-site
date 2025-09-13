# tools/build_items.py
import csv
import json
import pathlib
import re
import hashlib
from typing import Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "items.csv"
OUT_DIR = ROOT / "data"

SCHEMA_VERSION = 1

# -------- precompiled regex --------
TAG_SPLIT_RE = re.compile(r"[;,\n]+")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")

MONTH_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
MONTH_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# Explicit output key order for stable JSON hashing
OUT_KEYS = [
    "id", "title", "date", "master", "production", "category",
    "cast", "notes", "format", "url", "tags",
    "schemaVersion", "dateKey", "niceDate",
]

def split_tags(s: Optional[str]) -> List[str]:
    return [t.strip() for t in TAG_SPLIT_RE.split(s or "") if t.strip()]

def parse_partial_date(iso: str) -> Optional[Tuple[int,int,int]]:
    m = DATE_RE.match((iso or "").strip())
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2) or 0)
    d = int(m.group(3) or 0)
    return y, mo, d

def nice_date_en(iso: str) -> str:
    p = parse_partial_date(iso)
    if not p:
        return iso
    y, m, d = p
    if m == 0:
        return f"{y}"
    if d == 0:
        return f"{MONTH_LONG[m-1]}, {y}"
    return f"{MONTH_SHORT[m-1]} {d}, {y}"

def date_key_desc(iso: str) -> Tuple[int,int,int]:
    p = parse_partial_date(iso)
    if not p:
        # invalid dates end up at the bottom when sorting desc
        return (0, 0, 0)
    y, m, d = p
    return (-y, -m, -d)

def truthy(v) -> bool:
    s = str(v or "").strip().lower()
    return s in {"1","true","yes","y","on"}

def normalize_row(r: Dict[str,str]) -> Dict:
    # prefer new field names, fallback to legacy
    production = (r.get("production") or r.get("location") or "").strip()
    notes = (r.get("notes") or r.get("description") or "").strip()

    # category resolution: explicit first, else infer from legacy booleans
    raw_cat = (r.get("category") or "").strip().lower()
    if raw_cat in {"video","audio"}:
        category = raw_cat
    else:
        category = "video" if truthy(r.get("video")) else ("audio" if truthy(r.get("audio")) else "")

    tags = split_tags(r.get("tags"))
    tags += split_tags(r.get("details"))

    cast = (r.get("cast") or "").replace(";", "; ").strip()

    return {
        "id": (r.get("id") or "").strip(),
        "title": (r.get("title") or "").strip(),
        "date": (r.get("date") or "").strip(),
        "master": (r.get("master") or "").strip(),
        "production": production,
        "category": category,
        "cast": cast,
        "notes": notes,
        "format": (r.get("format") or "").strip(),
        "url": (r.get("url") or "").strip(),
        "tags": tags,
    }

def validate(rows: List[Dict]) -> List[str]:
    problems = []
    for i, r in enumerate(rows, 1):
        if not r["title"]:
            problems.append(f"[row {i}] title is empty")
        if r["category"] and r["category"] not in {"video","audio"}:
            problems.append(f"[row {i}] invalid category: {r['category']}")
        if r["date"] and not parse_partial_date(r["date"]):
            problems.append(f"[row {i}] invalid date: {r['date']}")
    return problems

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # load & normalize
    rows: List[Dict] = []
    with SRC.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(normalize_row(r))

    # validate (non-fatal)
    probs = validate(rows)
    if probs:
        print("Validation warnings:")
        for p in probs:
            print(" -", p)

    # sort: date desc, then title asc
    rows.sort(key=lambda x: (date_key_desc(x["date"]), (x["title"] or "").lower()))

    # enrich + build stable-key dicts for hashing/output
    enriched: List[Dict] = []
    for r in rows:
        payload = {
            **r,
            "schemaVersion": SCHEMA_VERSION,
            "dateKey": "|".join(map(str, date_key_desc(r["date"]))),
            "niceDate": nice_date_en(r["date"]),
        }
        # re-pack with OUT_KEYS order so JSON key order is deterministic
        packed = {k: payload.get(k) for k in OUT_KEYS}
        enriched.append(packed)

    # hash for cache-busting (stable due to deterministic key order)
    blob = json.dumps(enriched, ensure_ascii=False, separators=(",",":")).encode("utf-8")
    digest = hashlib.sha1(blob).hexdigest()[:8]
    items_name = f"items.{digest}.json"
    (OUT_DIR / items_name).write_bytes(blob)

    # manifest
    manifest = {"items": items_name}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # indexes (sorted keys and IDs for stable diffs)
    by_cat: Dict[str, List[str]] = {}
    by_tag: Dict[str, List[str]] = {}
    for r in enriched:
        rid = str(r.get("id") or "").strip()
        cat = (r.get("category") or "unknown").strip() or "unknown"
        by_cat.setdefault(cat, []).append(rid)
        for t in (r.get("tags") or []):
            by_tag.setdefault(t, []).append(rid)

    for v in by_cat.values():
        v.sort()
    for v in by_tag.values():
        v.sort()

    # write indexes with sorted keys
    (OUT_DIR / "index.categories.json").write_text(
        json.dumps(dict(sorted(by_cat.items())), indent=2),
        encoding="utf-8"
    )
    (OUT_DIR / "index.tags.json").write_text(
        json.dumps(dict(sorted(by_tag.items())), indent=2),
        encoding="utf-8"
    )

    # stats
    latest = next((r["date"] for r in enriched if (r.get("date") or "")), "")
    stats = {
        "schemaVersion": SCHEMA_VERSION,
        "count": len(enriched),
        "latest": latest,
        "categories": {k: len(v) for k, v in by_cat.items()},
        "uniqueTags": len(by_tag),
    }
    (OUT_DIR / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    # human-friendly CSV (sorted, tags as ;-separated)
    fieldnames = ["id","title","date","master","production","category","cast","notes","format","tags","url","niceDate"]
    with (OUT_DIR / "items.sorted.csv").open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=fieldnames)
        w.writeheader()
        for r in enriched:
            w.writerow({
                **{k: r.get(k, "") for k in fieldnames if k != "tags"},
                "tags": "; ".join(r.get("tags", [])),
            })

if __name__ == "__main__":
    main()

# script/build_items.py
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

# ---------- precompiled regex ----------

TAG_SPLIT_RE = re.compile(r"[;,\n]+")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")

MONTH_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
MONTH_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

# Deterministic JSON key order for stable hashing/diffs
OUT_KEYS = [
    "id","title","date","master","production","category",
    "cast","notes","format","url","tags","encora",
    "schemaVersion","dateKey","niceDate",
]

# ---------- helpers ----------

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

def date_key_asc(iso: str) -> Tuple[int,int,int]:
    p = parse_partial_date(iso)
    if not p:
        # invalid/empty dates go to the bottom for DESC
        return (9999, 99, 99)
    y, m, d = p
    return (y, m, d)

def truthy(v) -> bool:
    s = str(v or "").strip().lower()
    return s in {"1","true","yes","y","on"}

def normalize_row(r: Dict[str,str]) -> Dict:
    # prefer new names; keep backward-compatible fallbacks
    production = (r.get("production") or r.get("location") or "").strip()
    notes = (r.get("notes") or r.get("description") or "").strip()

    # category: explicit first; else infer from legacy booleans
    raw_cat = (r.get("category") or "").strip().lower()
    if raw_cat in {"video","audio"}:
        category = raw_cat
    else:
        category = "video" if truthy(r.get("video")) else ("audio" if truthy(r.get("audio")) else "")

    tags = split_tags(r.get("tags"))
    tags += split_tags(r.get("details"))

    _cast = (r.get("cast") or "").strip()
    # normalize any spaces around semicolons to exactly "; "
    _cast = re.sub(r"\s*;\s*", "; ", _cast)
    cast = _cast

    raw_url = (r.get("url") or "").strip()
    url = raw_url if raw_url else "MEGA"

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
        "url": url,
        "tags": tags,
        "encora": (r.get("encora") or "").strip(),  # NEW
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

def title_sort_key(title: Optional[str]) -> str:
    s = (title or "").strip()
    s = re.sub(r"^[\W_]+", "", s, flags=re.UNICODE)
    s = re.sub(r"^(the|a|an)\s+", "", s, flags=re.IGNORECASE)
    return s.lower()

# ---------- main ----------

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

    # sort: date DESC, then title ASC
    rows.sort(key=lambda x: (title_sort_key(x["title"]), date_key_asc(x["date"])))

    # enrich and repack to deterministic key order
    enriched: List[Dict] = []
    for r in rows:
        payload = {
            **r,
            "schemaVersion": SCHEMA_VERSION,
            "dateKey": "|".join(map(str, date_key_asc(r["date"]))),  # e.g. "-2025|-9|-1"
            "niceDate": nice_date_en(r["date"]),
        }
        packed = {k: payload.get(k) for k in OUT_KEYS}
        enriched.append(packed)

    # write items.<hash>.json (hash is stable due to deterministic key order)
    blob = json.dumps(enriched, ensure_ascii=False, separators=(",",":")).encode("utf-8")
    digest = hashlib.sha1(blob).hexdigest()[:8]
    items_name = f"items.{digest}.json"
    (OUT_DIR / items_name).write_bytes(blob)

    # manifest
    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"items": items_name}, indent=2), encoding="utf-8"
    )

    # indexes
    by_cat: Dict[str, List[str]] = {}
    by_tag: Dict[str, List[str]] = {}
    for r in enriched:
        rid = str(r.get("id") or "")
        cat = (r.get("category") or "unknown") or "unknown"
        by_cat.setdefault(cat, []).append(rid)
        for t in (r.get("tags") or []):
            by_tag.setdefault(t, []).append(rid)

    # sort values for stable diffs
    for v in by_cat.values():
        v.sort()
    for v in by_tag.values():
        v.sort()

    (OUT_DIR / "index.categories.json").write_text(
        json.dumps(dict(sorted(by_cat.items())), indent=2), encoding="utf-8"
    )
    (OUT_DIR / "index.tags.json").write_text(
        json.dumps(dict(sorted(by_tag.items())), indent=2), encoding="utf-8"
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

    # human-friendly CSV (sorted; tags are semicolon-separated)
    fieldnames = [
        "id","title","date","master","production","category",
        "cast","notes","format","tags","url","encora","niceDate"
    ]
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

# tools/build_items.py
import csv, json, pathlib, re, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "items.csv"
OUT_DIR = ROOT / "data"

SCHEMA_VERSION = 1

# ---------- helpers ----------

def split_tags(s):
    import re as _re
    return [t.strip() for t in _re.split(r"[;,\n,]+", s or "") if t.strip()]

def parse_partial_date(iso: str):
    m = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", (iso or "").strip())
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2) or 0)
    d = int(m.group(3) or 0)
    return y, mo, d

MONTH_NAMES_LONG  = ["January","February","March","April","May","June","July","August","September","October","November","December"]
MONTH_NAMES_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def nice_date_en(iso: str):
    p = parse_partial_date(iso)
    if not p: return iso
    y, m, d = p
    if m == 0:  return f"{y}"
    if d == 0:  return f"{MONTH_NAMES_LONG[m-1]}, {y}"
    return f"{MONTH_NAMES_SHORT[m-1]} {d}, {y}"

def date_key_desc(iso: str):
    p = parse_partial_date(iso)
    if not p: return (0,0,0)  # invalid goes last
    y,m,d = p
    return (-y,-m,-d)

def truthy(v):
    s = str(v or "").strip().lower()
    return s in {"1","true","yes","y","on"}

def normalize_row(r: dict) -> dict:
    production = (r.get("production") or r.get("location") or "").strip()
    notes = (r.get("notes") or r.get("description") or "").strip()
    # category: explicit (video|audio) 優先、なければ legacy boolean から推定
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
        "category": category,                          # "video" | "audio" | ""
        "cast": cast,
        "notes": notes,
        "format": (r.get("format") or "").strip(),
        "url": (r.get("url") or "").strip(),
        "tags": tags,
    }

def validate(rows):
    problems = []
    for i, r in enumerate(rows, 1):
        if not r["title"]:
            problems.append(f"[row {i}] title is empty")
        if r["category"] and r["category"] not in {"video","audio"}:
            problems.append(f"[row {i}] invalid category: {r['category']}")
        if r["date"] and not parse_partial_date(r["date"]):
            problems.append(f"[row {i}] invalid date: {r['date']}")
    return problems

# ---------- main ----------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # load & normalize
    rows = []
    with SRC.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(normalize_row(r))

    # validate
    probs = validate(rows)
    if probs:
        print("Validation warnings:")
        for p in probs: print(" -", p)

    # sort: date desc, title asc
    rows.sort(key=lambda x: (date_key_desc(x["date"]), x["title"].lower()))

    # enrich (schemaVersion, dateKey, niceDate)
    for r in rows:
        r["schemaVersion"] = SCHEMA_VERSION
        r["dateKey"] = "|".join(map(str, date_key_desc(r["date"])))  # e.g. "-2025|-9|-1"
        r["niceDate"] = nice_date_en(r["date"])

    # hash for cache-busting
    blob = json.dumps(rows, ensure_ascii=False, separators=(",",":")).encode("utf-8")
    digest = hashlib.sha1(blob).hexdigest()[:8]
    items_name = f"items.{digest}.json"
    (OUT_DIR / items_name).write_bytes(blob)

    # manifest
    manifest = {"items": items_name}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # indexes
    by_cat = {}
    by_tag = {}
    for r in rows:
        cid = r.get("id")
        cat = r.get("category") or "unknown"
        by_cat.setdefault(cat, []).append(cid)
        for t in (r.get("tags") or []):
            by_tag.setdefault(t, []).append(cid)

    (OUT_DIR / "index.categories.json").write_text(json.dumps(by_cat, indent=2), encoding="utf-8")
    (OUT_DIR / "index.tags.json").write_text(json.dumps(by_tag, indent=2), encoding="utf-8")

    # stats
    stats = {
        "schemaVersion": SCHEMA_VERSION,
        "count": len(rows),
        "latest": rows[0]["date"] if rows else "",
        "categories": {k: len(v) for k, v in by_cat.items()},
        "uniqueTags": len(by_tag),
    }
    (OUT_DIR / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    # human-friendly CSV（ソート済み、tagsは;区切りで出力）
    fieldnames = ["id","title","date","master","production","category","cast","notes","format","tags","url","niceDate"]
    with (OUT_DIR / "items.sorted.csv").open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({
                **{k: r.get(k, "") for k in fieldnames if k not in {"tags"}},
                "tags": "; ".join(r.get("tags", [])),
            })

if __name__ == "__main__":
    main()

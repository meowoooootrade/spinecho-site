import csv, json, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "items.csv"
DST_JSON = ROOT / "data" / "items.json"
DST_SORTED_CSV = ROOT / "data" / "items.sorted.csv"  # Optional: sorted CSV for humans

def to_date(s):
    """Convert string to date object (fallback to min if invalid)."""
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return datetime.date.min

def main():
    rows = []
    with SRC.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # Normalize types and fields
            r["date_iso"] = r.get("date", "").strip()
            r["date_obj"] = to_date(r["date_iso"])
            r["tags"] = [t.strip() for t in (r.get("tags") or "").split(";") if t.strip()]
            rows.append(r)

    # Sort order: date descending → title ascending
    rows.sort(key=lambda r: (r["date_obj"], r.get("title","").lower()), reverse=True)

    # Build JSON (exclude helper fields)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "title": r.get("title"),
            "date": r.get("date_iso"),
            "category": r.get("category"),
            "tags": r.get("tags"),
            "url": r.get("url"),
            "notes": r.get("notes"),
        })

    DST_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Optional: also write sorted CSV for manual browsing
    fieldnames = ["id","title","date","category","tags","url","notes"]
    with DST_SORTED_CSV.open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=fieldnames)
        w.writeheader()
        for r in out:
            w.writerow({
                **r,
                "tags": ";".join(r["tags"]) if isinstance(r["tags"], list) else (r["tags"] or "")
            })

if __name__ == "__main__":
    main()

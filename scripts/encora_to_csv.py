#!/usr/bin/env python3
# encora_to_csv.py
#
# Fetch your Encora collection (paginated or targeted) and export to CSV.
# Duplicates are removed by the "encora" column (recording id).
# If duplicates occur, the row with more information is kept.
#
# Usage examples:
#   python encora_to_csv.py --token $ENCORA_API_TOKEN --out data/encora.csv
#   python encora_to_csv.py --out data/encora.csv --page 1
#   python encora_to_csv.py --out data/encora.csv --pages 1,2,3
#   python encora_to_csv.py --out data/encora.csv --ids 111111,222222
#
# CSV columns:
#   title,date,master,production,category,cast,notes,format,tags,url,encora

import argparse
import csv
import html as _html
import os
import sys
import time
from typing import Dict, List, Optional, Tuple
import re

import requests

API_BASE = "https://encora.it/api"
HEADERS = lambda token: {"Authorization": f"Bearer {token}", "Accept": "application/json"}

# Throttle: ~15 requests/minute (Encora default is 30/min). Be conservative.
MIN_REQUEST_INTERVAL = 4.0  # seconds between requests

COLS = ["title","date","master","production","category","cast","notes","format","tags","url","encora"]

# ---------------------- helpers ----------------------

_BR_RE  = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")  # drop any other tags
FULL_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")

def _coerce_bool(v) -> Optional[bool]:
    """Coerce API boolean-ish values reliably. Returns True/False or None if unknown."""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true","1","yes","y","on"}:
        return True
    if s in {"false","0","no","n","off"}:
        return False
    return None

def score_row(row: Dict[str,str]) -> Tuple[int, int, int]:
    """Comparison tuple for dedup choice: non-empty fields, notes length, format length."""
    non_empty = sum(1 for k,v in row.items() if k != "encora" and str(v or "").strip())
    notes_len = len((row.get("notes") or "").strip())
    fmt_len   = len((row.get("format") or "").strip())
    return (non_empty, notes_len, fmt_len)

def clean_notes(s: Optional[str]) -> str:
    """Make notes one line: <br> -> space, strip tags, unescape, collapse whitespace."""
    if not s:
        return ""
    s = _BR_RE.sub(" ", s)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def partial_date_from_recording(rec: dict) -> str:
    """
    Build partial ISO-like date using Encora flags:
      - year only:        YYYY-00-00
      - year + month:     YYYY-MM-00
      - full date:        YYYY-MM-DD
    Logic:
      1) Parse recording.date.full_date if present.
      2) Respect month_known/day_known when they are explicitly True/False (incl. string forms).
      3) If flags are missing/None, infer from the parsed parts if they already contain '00'.
      4) If parsing fails, return "".
    """
    d  = rec.get("date") or {}
    fd = (d.get("full_date") or "").strip()

    m = FULL_DATE_RE.match(fd)
    if not m:
        return ""  # nothing we can safely normalize

    y, mm, dd = m.groups()

    mk = _coerce_bool(d.get("month_known"))
    dk = _coerce_bool(d.get("day_known"))

    # Explicit flags take precedence over whatever is in full_date.
    if mk is False:
        return f"{y}-00-00"
    if mk is True and (dk is False):
        return f"{y}-{mm}-00"
    if mk is True and dk is True:
        return f"{y}-{mm}-{dd}"

    # Flags unknown -> infer from parts if they carry zeroes already.
    if mm == "00":
        return f"{y}-00-00"
    if dd == "00":
        return f"{y}-{mm}-00"
    return f"{y}-{mm}-{dd}"

def _norm_status(status: dict) -> str:
    """Prefer abbreviation; fall back to label → short form."""
    abbr = (status or {}).get("abbreviation") or ""
    label = (status or {}).get("label") or ""
    abbr = abbr.strip()
    if abbr:
        return abbr.lower()  # e.g., "u/s", "s/w"
    lbl = label.strip().lower()
    if lbl == "understudy":
        return "u/s"
    if lbl == "swing":
        return "s/w"
    return ""

def cast_line(rec: dict) -> str:
    """Format as 'Name (u/s Role)' or 'Name (Role)'. Separate with comma+space."""
    out = []
    for c in (rec.get("cast") or []):
        perf = c.get("performer") or {}
        char = c.get("character") or {}
        name = (perf.get("name") or "").strip()
        role = (char.get("name") or "").strip()
        st   = _norm_status(c.get("status") or {})
        inside = f"{st} {role}".strip() if role else st
        inside = re.sub(r"\s+", " ", inside).strip()
        out.append(f"{name} ({inside})" if inside else name)
    return ", ".join(out)

def to_row(obj: dict) -> Dict[str,str]:
    """Map one collection item to our CSV schema."""
    rec   = obj.get("recording") or {}
    meta  = rec.get("metadata") or {}
    rid   = rec.get("id")

    row = {
        "title":       (rec.get("show") or "").strip(),
        "date":        partial_date_from_recording(rec),
        "master":      (rec.get("master") or "").strip(),
        "production":  (rec.get("tour") or "").strip(),             # tour => production
        "category":    (meta.get("media_type") or "").strip(),      # video/audio
        "cast":        cast_line(rec),
        "notes":       " ".join([
                           clean_notes(obj.get("notes")),
                           clean_notes(rec.get("master_notes"))
                       ]).strip(),
        "format":      (rec.get("release_format") or "").strip(),
        "tags":        "",                                          # leave empty
        "url":         "",                                          # leave empty
        "encora":      str(rid) if rid is not None else "",
    }
    return row

def _throttled_get(url: str, token: str, timeout: int, last_ts: List[float]) -> requests.Response:
    """GET with conservative pacing. `last_ts` is a single-element list carrying last request time."""
    now = time.time()
    if last_ts and last_ts[0] is not None:
        elapsed = now - last_ts[0]
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    resp = requests.get(url, headers=HEADERS(token), timeout=timeout)
    last_ts[:] = [time.time()]
    return resp

def fetch_collection_crawl(token: str, per_page: int, max_pages: int, timeout: int) -> List[dict]:
    """Crawl /collection with pagination, honoring rate limits."""
    url  = f"{API_BASE}/collection?per_page={per_page}"
    page = 1
    out: List[dict] = []
    last_ts = [None]
    while url and page <= max_pages:
        r = _throttled_get(url, token, timeout, last_ts)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("data") or [])
        url = data.get("next_page_url")
        page += 1
    return out

def fetch_collection_pages(token: str, pages: List[int], per_page: int, timeout: int) -> List[dict]:
    """Fetch specific collection pages."""
    out: List[dict] = []
    last_ts = [None]
    for p in pages:
        url = f"{API_BASE}/collection?per_page={per_page}&page={p}"
        r = _throttled_get(url, token, timeout, last_ts)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("data") or [])
    return out

def fetch_recordings_by_ids(token: str, ids: List[str], timeout: int) -> List[dict]:
    """Fetch /recording/{id} for a set of ids and wrap them in collection-like objects."""
    out: List[dict] = []
    last_ts = [None]
    for rid in ids:
        url = f"{API_BASE}/recording/{rid}"
        r = _throttled_get(url, token, timeout, last_ts)
        r.raise_for_status()
        rec = r.json() or {}
        # Normalize into the shape used by `to_row`: an item with top-level notes/format etc.
        out.append({
            "recording": rec,
            "notes": None,
            "format": None,
            "user_watched": 0,
            "collected_at": None,
        })
    return out

# ---------------------- main ----------------------

def main():
    ap = argparse.ArgumentParser(description="Export Encora collection to CSV with deduplication by 'encora' recording id.")
    ap.add_argument("--token", default=os.getenv("ENCORA_API_TOKEN"), help="Encora API token (or set ENCORA_API_TOKEN)")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--per-page", type=int, default=500, help="Items per page (max 500)")
    ap.add_argument("--max-pages", type=int, default=999, help="Max pages to crawl")
    ap.add_argument("--page", type=int, help="Fetch this single collection page (overrides crawl)")
    ap.add_argument("--pages", type=str, help="Comma-separated list of collection pages (overrides crawl)")
    ap.add_argument("--ids", type=str, help="Comma-separated recording ids to fetch via /recording/{id}")
    ap.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    ap.add_argument("--dry-run", action="store_true", help="Fetch and dedupe, but do not write CSV")
    args = ap.parse_args()

    if not args.token:
        print("ERROR: missing --token (or ENCORA_API_TOKEN).", file=sys.stderr)
        sys.exit(2)

    # Choose fetch mode
    if args.ids:
        ids = [s.strip() for s in args.ids.split(",") if s.strip()]
        print(f"Fetching {len(ids)} recording id(s) with pacing ~{60/MIN_REQUEST_INTERVAL:.1f}/min…")
        raw_items = fetch_recordings_by_ids(args.token, ids, args.timeout)
    elif args.page:
        print(f"Fetching collection page {args.page} (per_page={args.per_page}) with pacing…")
        raw_items = fetch_collection_pages(args.token, [args.page], args.per_page, args.timeout)
    elif args.pages:
        pages = [int(s.strip()) for s in args.pages.split(",") if s.strip()]
        print(f"Fetching collection pages {pages} (per_page={args.per_page}) with pacing…")
        raw_items = fetch_collection_pages(args.token, pages, args.per_page, args.timeout)
    else:
        print(f"Crawling collection… per_page={args.per_page} max_pages={args.max_pages} with pacing…")
        raw_items = fetch_collection_crawl(args.token, args.per_page, args.max_pages, args.timeout)

    print(f"Fetched {len(raw_items)} items.")

    # Map to rows
    rows = [to_row(it) for it in raw_items]

    # Dedupe by encora id
    unique: Dict[str, Dict[str,str]] = {}
    dup_count = 0
    for r in rows:
        key = r.get("encora","").strip()
        if not key:
            key = f"_noid_{hash(tuple(r.get(c, '') for c in COLS))}"
        if key in unique:
            if score_row(r) > score_row(unique[key]):
                print(f"[dedupe] Replacing encora={key} with richer row.")
                unique[key] = r
            else:
                dup_count += 1
        else:
            unique[key] = r

    rows_out = list(unique.values())
    print(f"Deduplicated: {len(rows)} -> {len(rows_out)} (removed {dup_count} duplicates)")

    if args.dry_run:
        print("Dry run complete. Not writing CSV.")
        return

    # Write CSV
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows_out:
            w.writerow({k: r.get(k, "") for k in COLS})

    print(f"Wrote {len(rows_out)} unique rows -> {args.out}")

if __name__ == "__main__":
    main()

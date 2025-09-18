#!/usr/bin/env python3
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

YOUTUBE_ID_RE = re.compile(r"\b[A-Za-z0-9_-]{11}\b")

def coerce_str(x: Any) -> Optional[str]:
    s = str(x or "").strip()
    return s if s else None

def find_key(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    lower_keys = {k.lower(): k for k in row.keys()}
    for c in candidates:
        if c.lower() in lower_keys:
            return lower_keys[c.lower()]
    return None

def row_get(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    k = find_key(row, candidates)
    return coerce_str(row.get(k)) if k else None

def extract_video_id(row: Dict[str, Any]) -> Optional[str]:
    # First, try dedicated ID columns
    vid = row_get(row, ["Video ID", "VideoId", "Id"])
    if vid and YOUTUBE_ID_RE.fullmatch(vid):
        return vid
    # If not found, search all values in the row for a YouTube ID
    for v in row.values():
        s = coerce_str(v)
        if s:
            m = YOUTUBE_ID_RE.search(s)
            if m:
                return m.group(0)
    return None

def convert_csv_file(csv_path: Path, remove_suffix: bool) -> Optional[Path]:
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print(f"[WARN] Failed to read CSV {csv_path}: {e}", file=sys.stderr)
        return None

    if not rows:
        print(f"[INFO] Empty CSV {csv_path}, skipping.", file=sys.stderr)
        return None

    tracks: List[Dict[str, Any]] = []
    for row in rows:
        video_id = extract_video_id(row)
        if not video_id:
            continue
        url = row_get(row, ["Video URL", "URL", "Link"]) or f"https://music.youtube.com/watch?v={video_id}"
        title = row_get(row, ["Video Title", "Title", "Song", "Track", "Name"])

        tracks.append({
            "title": title or "",
            "url": url,
            "videoId": video_id,
            "source": "csv"
        })

    if not tracks:
        print(f"[INFO] No tracks parsed from {csv_path}, skipping.", file=sys.stderr)
        return None

    playlist_name = csv_path.stem
    if remove_suffix and playlist_name.lower().endswith("-videos"):
        playlist_name = playlist_name[:-7]

    out_obj = {
        "type": "playlist",
        "name": playlist_name,
        "tracks": tracks,
    }

    out_path = csv_path.with_suffix(".json")
    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(out_obj, f, ensure_ascii=False, indent=2)
        print(f"[OK] Converted CSV -> JSON: {csv_path.name} -> {out_path.name} ({len(tracks)} tracks)")
        return out_path
    except Exception as e:
        print(f"[WARN] Failed to write JSON {out_path}: {e}", file=sys.stderr)
        return None

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("base_path", nargs="?", default="/data", help="Path to scan for CSVs")
    ap.add_argument("--remove-videos-suffix", action="store_true", help="Remove '-videos' suffix from playlist names")
    args = ap.parse_args()

    base = Path(args.base_path)
    if not base.exists():
        print(f"[ERROR] Input path not found: {base}", file=sys.stderr)
        return 2

    count = 0
    for p in base.rglob("*.csv"):
        if p.is_file():
            if convert_csv_file(p, args.remove_videos_suffix):
                count += 1

    print(f"[DONE] Converted {count} CSV file(s) under {base}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

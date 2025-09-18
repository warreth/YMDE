#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# A regex to validate and extract an 11-character YouTube video ID.
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

def eprint(msg: str) -> None:
    """Prints a message to standard error."""
    print(msg, file=sys.stderr, flush=True)

def coerce_str(value: Any) -> Optional[str]:
    """Converts a value to a stripped string, or None if empty."""
    s = str(value or "").strip()
    return s if s else None

def find_key(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    """Finds the first matching key from a list of candidates in a dictionary, case-insensitively."""
    lower_keys = {k.lower(): k for k in row.keys()}
    for c in candidates:
        if c.lower() in lower_keys:
            return lower_keys[c.lower()]
    return None

def row_get(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    """Gets a value from a row by trying multiple possible key names."""
    key = find_key(row, candidates)
    return coerce_str(row.get(key)) if key else None

def extract_video_id(row: Dict[str, Any]) -> Optional[str]:
    """
    Extracts a YouTube video ID from a CSV row.
    It first checks common ID columns, then falls back to searching all values in the row.
    """
    # 1. Try dedicated ID columns first for an exact match.
    vid = row_get(row, ["Video ID", "VideoId", "Id"])
    if vid and YOUTUBE_ID_RE.fullmatch(vid):
        return vid
        
    # 2. If not found, search all string values in the row for a potential ID.
    for value in row.values():
        s = coerce_str(value)
        if s:
            # This regex is more lenient to find IDs inside URLs or other text.
            m = re.search(r"[A-Za-z0-9_-]{11}", s)
            if m:
                return m.group(0)
    return None

def convert_csv_file(csv_path: Path, remove_suffix: bool) -> Optional[Path]:
    """
    Converts a single CSV playlist file to the target JSON format.
    Returns the path to the new .json file on success, otherwise None.
    """
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            # Use DictReader to handle CSVs with headers
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        eprint(f"[WARN] Failed to read CSV {csv_path.name}: {e}")
        return None

    if not rows:
        eprint(f"[INFO] Empty or invalid CSV: {csv_path.name}, skipping.")
        return None

    tracks: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        video_id = extract_video_id(row)
        if not video_id:
            eprint(f"[WARN] No video ID found in row {i+1} of {csv_path.name}")
            continue
            
        url = row_get(row, ["Video URL", "URL", "Link"]) or f"https://music.youtube.com/watch?v={video_id}"
        title = row_get(row, ["Video Title", "Title", "Song", "Track", "Name"])

        tracks.append({
            "title": title or "Unknown Title",
            "url": url,
            "videoId": video_id,
            "source": "csv"
        })

    if not tracks:
        eprint(f"[INFO] No valid tracks parsed from {csv_path.name}, skipping.")
        return None

    playlist_name = csv_path.stem
    if remove_suffix and playlist_name.lower().endswith("-videos"):
        playlist_name = playlist_name[:-7].strip()

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
        eprint(f"[ERR] Failed to write JSON {out_path.name}: {e}")
        return None

def main() -> int:
    """Main entrypoint for the CSV conversion script."""
    parser = argparse.ArgumentParser(
        description="Convert CSV playlists to the JSON format used by the downloader.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("base_path", nargs="?", default="/data", help="Directory to scan recursively for .csv files.")
    parser.add_argument("--remove-videos-suffix", action="store_true", help="Remove '-videos' suffix from playlist names.")
    args = parser.parse_args()

    base = Path(args.base_path)
    if not base.is_dir():
        eprint(f"[ERROR] Input path is not a directory or not found: {base}")
        return 2

    csv_files = sorted(list(base.rglob("*.csv")))
    if not csv_files:
        print(f"[INFO] No CSV files found under {base}.")
        return 0

    print(f"Found {len(csv_files)} CSV file(s) to process...")
    count = 0
    for p in csv_files:
        if p.is_file():
            if convert_csv_file(p, args.remove_videos_suffix):
                count += 1

    print(f"[DONE] Successfully converted {count} of {len(csv_files)} CSV file(s).")
    return 0

if __name__ == "__main__":
    sys.exit(main())

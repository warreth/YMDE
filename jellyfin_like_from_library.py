#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


def log(msg: str) -> None:
    """Print normal output to stdout."""
    print(msg, flush=True)


def eprint(msg: str) -> None:
    """Print error/warn to stderr."""
    print(msg, file=sys.stderr, flush=True)


def extract_video_id(p: Path) -> Optional[str]:
    """Extract the 11-char YouTube ID inside square brackets from filename."""
    m = re.search(r"\[([A-Za-z0-9_-]{11})\]\.[^.]+$", p.name)
    return m.group(1) if m else None


def scan_library_for_ids(root: Path) -> Dict[str, Path]:
    """Return mapping videoId -> file path for files containing an ID."""
    mapping: Dict[str, Path] = {}
    for p in root.rglob("*.*"):
        if not p.is_file():
            continue
        vid = extract_video_id(p)
        if vid and vid not in mapping:
            mapping[vid] = p
    return mapping


def jellyfin_headers(api_key: str, client: str = "YMDE", device: str = "container", version: str = "1.0") -> Dict[str, str]:
    """Build Jellyfin headers."""
    return {
        "X-Emby-Token": api_key,
        "X-Emby-Authorization": f"MediaBrowser Client={client}, Device={device}, DeviceId=ymde, Version={version}",
        "Accept": "application/json",
    }


def get_me_user_id(base_url: str, api_key: str) -> Optional[str]:
    """Resolve current user's Id using /Users/Me."""
    try:
        r = requests.get(f"{base_url}/Users/Me", headers=jellyfin_headers(api_key), timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        uid = data.get("Id") if isinstance(data, dict) else None
        return str(uid) if uid else None
    except Exception:
        return None


def fetch_all_audio_items(base_url: str, api_key: str, user_id: str) -> List[Dict[str, any]]:
    """Fetch all audio items with Path field for the user."""
    try:
        url = f"{base_url}/Items"
        params = {
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "Fields": "Path",
            "UserId": user_id,
            "Limit": 100000,
        }
        r = requests.get(url, headers=jellyfin_headers(api_key), params=params, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        items = data.get("Items") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []
    except Exception:
        return []


def search_item(base_url: str, api_key: str, user_id: str, query: str) -> Optional[str]:
    """Search Jellyfin items by name. Return first ItemId or None."""
    try:
        url = f"{base_url}/Items"
        params = {
            "SearchTerm": query,
            "IncludeItemTypes": "Audio",
            "Limit": 1,
            "Recursive": "true",
            "UserId": user_id,
        }
        r = requests.get(url, headers=jellyfin_headers(api_key), params=params, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        items = data.get("Items") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            it = items[0]
            iid = it.get("Id")
            return str(iid) if iid else None
        return None
    except Exception:
        return None


def set_favorite(base_url: str, api_key: str, user_id: str, item_id: str, fav: bool) -> bool:
    """Set favorite state for an item. True on success."""
    try:
        url = f"{base_url}/Users/{user_id}/FavoriteItems/{item_id}"
        if fav:
            r = requests.post(url, headers=jellyfin_headers(api_key), timeout=20)
        else:
            r = requests.delete(url, headers=jellyfin_headers(api_key), timeout=20)
        return r.status_code in (200, 204, 202)
    except Exception:
        return False


def like_by_video_ids(base_url: str, api_key: str, video_ids: List[str]) -> Tuple[int, int]:
    """Attempt to like items by searching with their YouTube video ID."""
    ok = 0
    fail = 0
    user_id = get_me_user_id(base_url, api_key)
    if not user_id:
        return 0, len(video_ids)

    # Build map from videoId in file path to item id by scanning all audio items once
    items = fetch_all_audio_items(base_url, api_key, user_id)
    id_from_path: Dict[str, str] = {}
    for it in items:
        path = str(it.get("Path") or "")
        m = re.search(r"\[([A-Za-z0-9_-]{11})\]", path)
        if m:
            id_from_path[m.group(1)] = str(it.get("Id"))

    for vid in video_ids:
        item_id = id_from_path.get(vid)
        if not item_id:
            item_id = search_item(base_url, api_key, user_id, vid)
        if not item_id:
            fail += 1
            continue
        if set_favorite(base_url, api_key, user_id, item_id, True):
            ok += 1
        else:
            fail += 1
    return ok, fail


def main() -> int:
    """CLI entry point: like all tracks present in a library folder in Jellyfin."""
    ap = argparse.ArgumentParser(description="Mark audio tracks as favorite in Jellyfin.")
    ap.add_argument("--library", dest="library", default="/library", help="Path to the music library root to scan when no playlist JSON is provided.")
    ap.add_argument("--playlist-json", dest="playlist_json", help="Optional path to a playlist JSON file whose videoIds will be liked.")
    ap.add_argument("--jellyfin-url", dest="jf_url", required=True, help="Base URL of Jellyfin, e.g., http://host:8096")
    ap.add_argument("--jellyfin-api-key", dest="jf_key", required=True, help="Jellyfin API token")
    args = ap.parse_args()

    vids: List[str] = []
    if args.playlist_json:
        p = Path(args.playlist_json).resolve()
        if not p.exists():
            eprint(f"[ERROR] Playlist JSON not found: {p}")
            return 2
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            tracks = data.get("tracks") if isinstance(data, dict) else None
            if not isinstance(tracks, list):
                eprint("[ERROR] Invalid playlist JSON format: missing 'tracks' list")
                return 2
            for t in tracks:
                vid = str(t.get("videoId") or "").strip()
                if vid:
                    vids.append(vid)
        except Exception as e:
            eprint(f"[ERROR] Failed to parse playlist JSON: {e}")
            return 2
    else:
        root = Path(args.library).resolve()
        if not root.exists():
            eprint(f"[ERROR] Library path not found: {root}")
            return 2
        mapping = scan_library_for_ids(root)
        if not mapping:
            log("[INFO] No files with YouTube IDs found in library.")
            return 0
        vids = list(mapping.keys())

    ok, fail = like_by_video_ids(args.jf_url.rstrip("/"), args.jf_key, vids)
    log(f"[Jellyfin] Marked favorite: {ok}, Failed: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


# Simple logger helpers
def log(msg: str) -> None:
    """Print a normal progress/info message."""
    print(msg, flush=True)


def eprint(msg: str) -> None:
    """Print a warning/error style message to stderr."""
    print(msg, file=sys.stderr, flush=True)


def run_cmd(cmd: List[str]) -> tuple[int, str, str]:
    """Run a command and capture output."""
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8")
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "yt-dlp not found"
    except Exception as e:  # Defensive: unexpected failure
        return 1, "", str(e)


def build_playlist_json(playlist_name: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transform yt-dlp entries into our standard playlist JSON format."""
    tracks: List[Dict[str, Any]] = []
    for e in entries:
        vid = str(e.get("id") or "").strip()
        if not vid:
            continue
        title = str(e.get("title") or "Unknown Title").strip() or "Unknown Title"
        url = f"https://www.youtube.com/watch?v={vid}"
        tracks.append({
            "title": title,
            "url": url,
            "videoId": vid,
            "source": "liked"
        })
    return {"type": "playlist", "name": playlist_name, "tracks": tracks}


def export_liked_songs(cookies: str | None, out_dir: Path, playlist_name: str) -> Path:
    """Fetch liked songs from YouTube Music and write a single JSON playlist file.

    Uses yt-dlp to query the special 'Liked Music' playlist (LM).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    playlist_url = "https://music.youtube.com/playlist?list=LM"

    cmd: List[str] = [
        "yt-dlp",
        "-J",  # dump full JSON for the playlist
        "--flat-playlist",  # only basic metadata per entry
        playlist_url,
    ]
    if cookies and Path(cookies).is_file():
        cmd += ["--cookies", cookies]

    rc, stdout, stderr = run_cmd(cmd)
    if rc != 0:
        eprint(f"[ERROR] Could not fetch liked songs: {stderr.strip()}")
        raise SystemExit(1)

    try:
        data = json.loads(stdout)
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            eprint("[ERROR] Unexpected yt-dlp JSON format (no entries).")
            raise SystemExit(1)
    except Exception as e:  # Defensive: bad JSON
        eprint(f"[ERROR] Failed to parse yt-dlp JSON: {e}")
        raise SystemExit(1)

    playlist = build_playlist_json(playlist_name, entries)
    out_path = out_dir / f"{playlist_name}.json"
    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        eprint(f"[ERROR] Failed to write JSON file: {e}")
        raise SystemExit(1)

    log(f"[OK] Exported {len(playlist['tracks'])} liked song(s) -> {out_path}")
    return out_path


def main() -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Export YouTube Music liked songs to a JSON playlist.")
    ap.add_argument("--cookies", dest="cookies", help="Path to cookies.txt for private playlists.")
    ap.add_argument("--out-dir", dest="out_dir", default="/data", help="Directory to write the JSON playlist into.")
    ap.add_argument("--name", dest="name", default="Liked Songs", help="Playlist name to use in the JSON file.")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    export_liked_songs(args.cookies, out_dir, args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

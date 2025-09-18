#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Conditional import of tqdm for progress bars
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

def log(msg: str) -> None:
    print(msg, flush=True)

def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

def get_video_id(url: str) -> Optional[str]:
    m = re.search(r"(?:youtube\.com|youtu\.be).*?([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def find_json_playlists(root: Path) -> List[Path]:
    return [p for p in root.rglob("*.json") if p.is_file()]

def load_playlist(json_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("type") == "playlist" and isinstance(data.get("tracks"), list):
            return data
        return None
    except Exception as e:
        eprint(f"[WARN] Failed to read JSON {json_path}: {e}")
        return None

def maybe_rewrite_to_ytmusic(url: str, prefer_music: bool) -> str:
    if not prefer_music:
        return url
    m = re.search(r"(?:youtube\.com|youtu\.be).*?([A-Za-z0-9_-]{11})", url)
    if not m:
        return url
    vid = m.group(1)
    return f"https://music.youtube.com/watch?v={vid}"

def _add_sleep_flags(cmd: List[str], sleep: Optional[str]) -> None:
    s = (sleep or "").strip()
    if not s:
        return
    if "," in s:
        lo, hi = [x.strip() for x in s.split(",", 1)]
        if lo and hi:
            cmd.extend(["--min-sleep-interval", lo, "--max-sleep-interval", hi])
        elif lo or hi:
            cmd.extend(["--sleep-interval", lo or hi])
    else:
        cmd.extend(["--sleep-interval", s])

def build_ytdlp_cmd(
    url: str,
    outtmpl: str,
    audio_format: str,
    audio_quality: Optional[str],
    cookies: Optional[str],
    rate_limit: Optional[str],
    sleep: Optional[str],
    prefer_music: bool,
    dry_run: bool,
) -> List[str]:
    u = maybe_rewrite_to_ytmusic(url, prefer_music)

    cmd: List[str] = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format", audio_format,
        "--embed-metadata",
        "--embed-thumbnail",
        "--add-metadata",
        "--no-abort-on-error",
        "--no-overwrites",
        "--print", "after_move:filepath",
        "-o", outtmpl,
    ]

    if audio_format.lower() == "mp3" and audio_quality:
        cmd.extend(["--audio-quality", audio_quality])

    if cookies and Path(cookies).is_file():
        cmd.extend(["--cookies", cookies])

    if rate_limit:
        cmd.extend(["--limit-rate", rate_limit])

    _add_sleep_flags(cmd, sleep)

    if dry_run:
        cmd.append("--skip-download")

    cmd.append(u)
    return cmd

def run_cmd(cmd: List[str]) -> Tuple[int, str]:
    try:
        # Let yt-dlp print directly to stdout/stderr, but capture final filename
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            eprint(f"[yt-dlp stderr] {proc.stderr.strip()}")
        return proc.returncode, proc.stdout.strip()
    except FileNotFoundError:
        eprint("yt-dlp not found. Make sure it is installed in the image.")
        return 127, ""
    except Exception as e:
        eprint(f"[ERR] Failed to run yt-dlp: {e}")
        return 1, ""

def download_track(
    url: str,
    output_dir: Path,
    playlist_name: str,
    audio_format: str,
    audio_quality: Optional[str],
    cookies: Optional[str],
    rate_limit: Optional[str],
    sleep: Optional[str],
    prefer_youtube_music: bool,
    dry_run: bool,
) -> Tuple[bool, str, Optional[str], Optional[Path]]:
    # Use yt-dlp’s own metadata for naming
    outtmpl = str(
        output_dir
        / playlist_name
        / "%(track|title)s.%(ext)s"
    )

    cmd = build_ytdlp_cmd(
        url=url,
        outtmpl=outtmpl,
        audio_format=audio_format,
        audio_quality=audio_quality,
        cookies=cookies,
        rate_limit=rate_limit,
        sleep=sleep,
        prefer_music=prefer_youtube_music,
        dry_run=dry_run,
    )
    rc, final_path_str = run_cmd(cmd)
    vid = get_video_id(url)
    
    final_path = Path(final_path_str) if final_path_str and rc == 0 else None
    
    return rc == 0, url, vid, final_path

def find_existing_file(vid: str, library_root: Path) -> Optional[Path]:
    """Scans the library for a file matching the video ID."""
    for f in library_root.rglob("*"):
        if f.is_file() and f.stem == vid:
            return f
    return None

def write_m3u_for_playlist(library_root: Path, playlist_name: str, files: List[Path]) -> None:
    pl_dir = library_root / "_playlists"
    pl_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = re.sub(r'[\\/*?:"<>|]', "_", playlist_name)
    m3u_path = pl_dir / f"{safe_name}.m3u8"

    sorted_files = sorted(files, key=lambda p: p.name.lower())

    try:
        with m3u_path.open("w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for p in sorted_files:
                rel_path = p.relative_to(library_root)
                f.write(str(rel_path).replace("\\", "/") + "\n")
        log(f"[M3U] Wrote playlist: {m3u_path}")
    except Exception as e:
        eprint(f"[WARN] Failed to write M3U playlist {m3u_path}: {e}")

def process_playlist(
    playlist_path: Path,
    out_root: Path,
    args: argparse.Namespace,
    downloaded_vids: Dict[str, Path],
) -> Tuple[int, int]:
    """
    Processes a single playlist file: loads tracks, downloads them, and reports results.
    Returns a tuple of (success_count, failure_count).
    """
    pl = load_playlist(playlist_path)
    if not pl:
        return 0, 0

    playlist_name = pl.get("name", playlist_path.stem)
    log(f"\n>>> Processing playlist: {playlist_name}")

    urls_to_download: List[str] = []
    playlist_track_files: List[Path] = []

    for t in pl.get("tracks", []):
        url = t.get("url")
        vid = None
        if not url:
            vid = t.get("videoId")
            if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(vid)):
                url = f"https://www.youtube.com/watch?v={vid}"
        
        if url and not vid:
            vid = get_video_id(url)

        if url and vid:
            if vid not in downloaded_vids:
                urls_to_download.append(url)
            else:
                log(f"Skipping duplicate track in '{playlist_name}': {url}")
                if downloaded_vids[vid]:
                    playlist_track_files.append(downloaded_vids[vid])

    if not urls_to_download:
        log(f"No new tracks to download in playlist: {playlist_name}")
        if args.write_m3u and playlist_track_files:
            write_m3u_for_playlist(out_root, playlist_name, playlist_track_files)
        return 0, 0

    log(f"Found {len(urls_to_download)} new tracks. Starting downloads with concurrency={args.concurrency}...")

    failures: List[str] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = {
            ex.submit(
                download_track,
                url=url,
                output_dir=out_root,
                playlist_name=playlist_name,
                audio_format=args.audio_format,
                audio_quality=args.quality,
                cookies=args.cookies,
                rate_limit=args.rate_limit,
                sleep=args.sleep,
                prefer_youtube_music=args.prefer_youtube_music,
                dry_run=args.dry_run,
            ): url
            for url in urls_to_download
        }

        iterator = as_completed(futs)
        if tqdm:
            iterator = tqdm(iterator, total=len(futs), desc=f"Downloading '{playlist_name}'", unit="song", leave=False)

        for f in iterator:
            ok, url, vid, final_path = f.result()
            if ok:
                if vid:
                    downloaded_vids[vid] = final_path
                if final_path:
                    playlist_track_files.append(final_path)
            else:
                failures.append(url)

    success_count = len(urls_to_download) - len(failures)
    log(f"Playlist '{playlist_name}' summary: {success_count} downloaded, {len(failures)} failed.")

    if failures:
        eprint(f"  [FAILURES] for '{playlist_name}':")
        for url in failures:
            eprint(f"    - {url}")

    if args.write_m3u:
        write_m3u_for_playlist(out_root, playlist_name, playlist_track_files)

    return success_count, len(failures)


def main() -> int:
    ap = argparse.ArgumentParser(description="Download YouTube Music playlists from a Google Takeout.")
    ap.add_argument("takeout_path", help="Path to folder containing Takeout JSON and/or CSV files")
    ap.add_argument("-o", "--output-dir", default="/library", help="Output library directory")
    ap.add_argument("--audio-format", default="m4a", choices=["m4a", "mp3"], help="Output audio format")
    ap.add_argument("--quality", default="0", help="Audio quality (for mp3: 0=best VBR, 9=worst)")
    ap.add_argument("--concurrency", type=int, default=2, help="Number of parallel downloads")
    ap.add_argument("--prefer-youtube-music", action="store_true", help="Rewrite video URLs to music.youtube.com for better music metadata")
    ap.add_argument("--write-m3u", action="store_true", help="Write m3u8 playlists for each album folder after download")
    ap.add_argument("--rate-limit", help="Limit download rate, e.g. 1M")
    ap.add_argument("--sleep", help='Sleep between downloads: "N" for fixed, or "min,max" for random')
    ap.add_argument("--cookies", help="Path to a cookies.txt file (Netscape format)")
    ap.add_argument("--dry-run", action="store_true", help="Simulate the process without downloading files")

    args = ap.parse_args()

    takeout_path = Path(args.takeout_path).resolve()
    out_root = Path(args.output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if not takeout_path.exists():
        eprint(f"[ERROR] Path not found: {takeout_path}")
        return 2

    # Gather and process playlists one by one
    json_paths = find_json_playlists(takeout_path)
    if not json_paths:
        eprint("No JSON playlist files found in the provided path.")
        return 1

    log(f"Found {len(json_paths)} JSON playlist(s) to process.")
    total_success = 0
    total_failures = 0
    downloaded_vids: Dict[str, Path] = {}

    for jp in sorted(json_paths):
        s, f = process_playlist(jp, out_root, args, downloaded_vids)
        total_success += s
        total_failures += f

    log("\n" + "="*40)
    if total_failures > 0:
        eprint(f"\n[DONE] Completed with {total_failures} total failure(s).")
    else:
        log("\n[DONE] All downloads completed successfully.")
    log(f"Total tracks downloaded: {total_success}")
    log("="*40)

    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

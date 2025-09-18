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
        "--print", "filename",
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

def run_cmd(cmd: List[str], verbose: bool, url: str) -> Tuple[int, str]:
    try:
        # Let yt-dlp print to stderr. We only capture stdout for the filename.
        # In non-verbose mode, tqdm will hide the stderr spam.
        # In verbose mode, the user will see it.
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        
        if proc.returncode != 0:
            # Always print stderr on failure.
            eprint(f"--- yt-dlp error for {url} ---\n{proc.stderr.strip()}\n--- end error ---")
            
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
    audio_format: str,
    audio_quality: Optional[str],
    cookies: Optional[str],
    rate_limit: Optional[str],
    sleep: Optional[str],
    prefer_youtube_music: bool,
    dry_run: bool,
    verbose: bool,
) -> Tuple[bool, str, Optional[Path]]:
    # Use yt-dlp’s own metadata for naming
    outtmpl = str(
        output_dir
        / "%(artist|album_artist|uploader|channel)s"
        / "%(album|playlist_title|uploader)s"
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
    rc, downloaded_path_str = run_cmd(cmd, verbose, url)
    
    downloaded_path = None
    if rc == 0 and downloaded_path_str:
        downloaded_path = Path(downloaded_path_str)

    return (rc == 0, url, downloaded_path)

def main() -> int:
    ap = argparse.ArgumentParser(description="Download YouTube Music playlists from a Google Takeout.")
    ap.add_argument("takeout_path", help="Path to folder containing Takeout JSON and/or CSV files")
    ap.add_argument("-o", "--output-dir", default="/library", help="Output library directory")
    ap.add_argument("--audio-format", default="m4a", choices=["m4a", "mp3"], help="Output audio format")
    ap.add_argument("--quality", default="0", help="Audio quality (for mp3: 0=best VBR, 9=worst)")
    ap.add_argument("--concurrency", type=int, default=2, help="Number of parallel downloads")
    ap.add_argument("--prefer-youtube-music", action="store_true", help="Rewrite video URLs to music.youtube.com for better music metadata")
    ap.add_argument("--write-m3u", action="store_true", help="Write an m3u8 playlist for each source JSON file")
    ap.add_argument("--rate-limit", help="Limit download rate, e.g. 1M")
    ap.add_argument("--sleep", help='Sleep between downloads: "N" for fixed, or "min,max" for random')
    ap.add_argument("--cookies", help="Path to a cookies.txt file (Netscape format)")
    ap.add_argument("--dry-run", action="store_true", help="Simulate the process without downloading files")
    ap.add_argument("--verbose", action="store_true", help="Show detailed yt-dlp output instead of a progress bar")

    args = ap.parse_args()

    takeout_path = Path(args.takeout_path).resolve()
    out_root = Path(args.output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if not takeout_path.exists():
        eprint(f"[ERROR] Path not found: {takeout_path}")
        return 2

    # Gather playlists from JSON files
    json_paths = find_json_playlists(takeout_path)
    if not json_paths:
        eprint("No JSON files found in the provided path.")
        return 1

    playlists: Dict[str, List[str]] = {}
    for jp in json_paths:
        pl = load_playlist(jp)
        if not pl:
            continue
        
        playlist_name = pl.get("name") or jp.stem
        urls: List[str] = []
        for t in pl.get("tracks", []):
            url = t.get("url")
            if not url:
                vid = t.get("videoId")
                if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(vid)):
                    url = f"https://www.youtube.com/watch?v={vid}"
            if url:
                urls.append(url)
        if urls:
            playlists[playlist_name] = urls

    if not playlists:
        eprint("No tracks to process.")
        return 1

    total_tracks = sum(len(urls) for urls in playlists.values())
    log(f"Found {len(playlists)} playlists with a total of {total_tracks} tracks.")

    failures: List[str] = []
    
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        for name, urls in playlists.items():
            if not args.verbose:
                log(f"\nProcessing playlist: {name}")
            else:
                log(f"\nProcessing playlist: {name} ({len(urls)} tracks)")
            
            playlist_files: List[Path] = []
            futs = {
                ex.submit(
                    download_track,
                    url=url,
                    output_dir=out_root,
                    audio_format=args.audio_format,
                    audio_quality=args.quality,
                    cookies=args.cookies,
                    rate_limit=args.rate_limit,
                    sleep=args.sleep,
                    prefer_youtube_music=args.prefer_youtube_music,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                ): url
                for url in urls
            }

            # Choose iterator based on verbosity
            iterator = as_completed(futs)
            progress_bar = None
            if not args.verbose and tqdm:
                progress_bar = tqdm(iterator, total=len(futs), desc="Downloading", unit="song")
                iterator = progress_bar

            for f in iterator:
                ok, url, downloaded_path = f.result()
                if ok:
                    if downloaded_path:
                        playlist_files.append(downloaded_path)
                else:
                    failures.append(url)
            
            if progress_bar:
                progress_bar.close()

            if args.write_m3u and playlist_files:
                write_m3u_for_playlist(out_root, name, playlist_files)

    if failures:
        eprint(f"\n[DONE] Completed with {len(failures)} failures.")
        for url in failures:
            eprint(f"  - {url}")
    else:
        log("\n[DONE] All downloads completed successfully.")

    return 0 if not failures else 1

def write_m3u_for_playlist(library_root: Path, playlist_name: str, files: List[Path]) -> None:
    pl_dir = library_root / "_playlists"
    pl_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize playlist name for use as a filename
    safe_name = re.sub(r'[\\/*?:"<>|]', "_", playlist_name)
    m3u_path = pl_dir / f"{safe_name}.m3u8"

    # Sort files alphabetically for consistent playlist order
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


if __name__ == "__main__":
    sys.exit(main())

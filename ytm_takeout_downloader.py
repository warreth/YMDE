#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import shlex
import math

# Failure categories for optional future reporting (simple heuristics)
FAIL_AGE_RESTRICTED = "age_restricted"
FAIL_PREMIUM_ONLY = "premium_only"
FAIL_REGION = "region_blocked"
FAIL_UNAVAILABLE = "unavailable"
FAIL_OTHER = "other"

"""YouTube Music Takeout Downloader.

Simplified logging: normal output to stdout, warnings/errors to stderr.
Use -v/--verbose for extra per-track skip information.
"""

###############################################################################
# Logging Setup
###############################################################################

VERBOSE = False  # Set in main() based on --verbose flag

# Conditional import of tqdm for progress bars (optional dependency)
try:  # noqa: SIM105
    from tqdm import tqdm  # type: ignore
except Exception:
    tqdm = None  # type: ignore

def log(msg: str) -> None:
    """Print a normal progress/info message."""
    print(msg, flush=True)

def vlog(msg: str) -> None:
    """Print a verbose-only message."""
    if VERBOSE:
        print(msg, flush=True)

def eprint(msg: str) -> None:
    """Print a warning/error style message to stderr."""
    print(msg, file=sys.stderr, flush=True)

def validate_cookies_file(cookies_path: Path) -> Tuple[bool, str]:
    """Lightweight validation for a Netscape cookies.txt file.

    Checks:
    1. File exists and is not empty (ignoring comment lines).
    2. At least one non-comment line has 7+ tab-separated fields.
    3. Looks for at least one expected YouTube auth cookie name (heuristic).
    """
    if not cookies_path.exists():
        return False, f"Cookies file not found: {cookies_path}"
    try:
        lines = cookies_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:  # Defensive: IO error
        return False, f"Failed to read cookies file: {e}"

    # Strip comments / blanks
    content = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    if not content:
        return False, "Cookies file is empty (only comments or blank lines)."

    structured = [ln for ln in content if len(ln.split("\t")) >= 7]
    if not structured:
        return False, "File does not look like Netscape format (no tab-separated records)."

    important = {"SAPISID", "__Secure-3PAPISID", "HSID", "SSID", "APISID"}
    found = False
    for ln in structured:
        parts = ln.split("\t")
        # Netscape format: domain, flag, path, secure, expiration, name, value
        name = parts[5] if len(parts) >= 6 else ""
        if name in important:
            found = True
            break
    if not found:
        return False, "Could not find expected YouTube auth cookies (e.g., SAPISID)."
    return True, "Cookies file looks OK."

def find_existing_downloads(library_root: Path) -> Dict[str, Path]:
    """Scans the library for existing files and maps video IDs to their paths."""
    vlog("Scanning library for existing downloads...")
    vids: Dict[str, Path] = {}
    # Regex to find the 11-char ID in brackets just before the extension
    id_re = re.compile(r"\[([A-Za-z0-9_-]{11})\]\.[^.]+$")

    # Using rglob to find all files in all subdirectories
    for p in library_root.rglob("*.*"):
        if not p.is_file():
            continue

        m = id_re.search(p.name)
        if m:
            vid = m.group(1)
            if vid not in vids:
                vids[vid] = p

    log(f"Found {len(vids)} existing tracks in the library.")
    return vids

def get_video_id(url: str) -> Optional[str]:
    """Extracts the 11-character video ID from a YouTube URL."""
    m = re.search(r"(?:youtube\.com|youtu\.be).*?([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def find_json_playlists(root: Path) -> List[Path]:
    """Finds all .json files in a directory, sorted alphabetically."""
    return sorted([p for p in root.rglob("*.json") if p.is_file()])

def load_playlist(json_path: Path) -> Optional[Dict[str, Any]]:
    """Loads a JSON playlist file, returning None if it's invalid."""
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Basic validation
        if isinstance(data, dict) and data.get("type") == "playlist" and isinstance(data.get("tracks"), list):
            return data
        eprint(f"[WARN] Invalid playlist format in {json_path}")
        return None
    except Exception as e:
        eprint(f"[WARN] Failed to read JSON {json_path}: {e}")
        return None

def maybe_rewrite_to_ytmusic(url: str, prefer_music: bool) -> str:
    """Rewrites a standard YouTube URL to a YouTube Music URL if preferred."""
    if not prefer_music:
        return url
    vid = get_video_id(url)
    return f"https://music.youtube.com/watch?v={vid}" if vid else url

def _add_sleep_flags(cmd: List[str], sleep: Optional[str]) -> None:
    """Adds sleep-related flags to the yt-dlp command."""
    s = (sleep or "").strip()
    if not s:
        return
    try:
        if "," in s:
            lo, hi = [float(x.strip()) for x in s.split(",", 1)]
            cmd.extend(["--min-sleep-interval", str(lo), "--max-sleep-interval", str(hi)])
        else:
            cmd.extend(["--sleep-interval", str(float(s))])
    except ValueError:
        eprint(f"[WARN] Invalid sleep value '{s}'. It must be a number or 'min,max'.")


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
    trim_non_music: bool,
    sb_categories: Optional[str],
) -> List[str]:
    """Builds the full yt-dlp command as a list of strings."""
    u = maybe_rewrite_to_ytmusic(url, prefer_music)

    cmd: List[str] = [
        "yt-dlp",
        "--no-playlist",
        "-x",  # Extract audio
        "--audio-format", audio_format,
        "--embed-metadata",
        "--embed-thumbnail",
        "--add-metadata",
        # Parse the title from the infojson, remove anything in brackets, and use that for the metadata title.
        # This gives a clean title in the media player while keeping the ID in the filename.
        "--parse-metadata", "title:%(title)s",
        "--parse-metadata", r'title:(?P<title>.+?)\s*\[.+\]',
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

    # Add SponsorBlock removal if requested.
    if trim_non_music:
        cats = (sb_categories or "").strip() or "sponsor,intro,outro,selfpromo,music_offtopic"
        cmd.extend(["--sponsorblock-remove", cats])

    cmd.append(u)
    return cmd

def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    """Executes a command, capturing its output and return code."""
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8")
        # The caller is responsible for logging stderr
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        eprint("yt-dlp not found. Make sure it is installed and in your PATH.")
        return 127, "", "yt-dlp not found"
    except Exception as e:
        eprint(f"[ERR] Failed to run command '{' '.join(cmd)}': {e}")
        return 1, "", str(e)

def classify_failure(stderr: str) -> str:
    """Classify a yt-dlp stderr snippet into a simple category."""
    s = stderr.lower()
    if "sign in to confirm your age" in s:
        return FAIL_AGE_RESTRICTED
    if "music premium" in s or "premium members" in s:
        return FAIL_PREMIUM_ONLY
    if "not made this video available in your country" in s or "uploader has not made" in s:
        return FAIL_REGION
    if "video unavailable" in s:
        return FAIL_UNAVAILABLE
    return FAIL_OTHER

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
    trim_non_music: bool,
    sb_categories: Optional[str],
    retry_search_if_unavailable: bool,
    original_title: Optional[str],
    fallback_max_results: int,
) -> Tuple[bool, str, Optional[str], Optional[Path], Optional[str]]:
    """Download a single track with optional fallback search.

    Returns (success, url_used, video_id, final_path, error_message).

    If the initial download fails with an error containing 'unavailable' and
    retry_search_if_unavailable is True, this function will perform a YouTube
    search (via yt-dlp) using the original_title (if provided) or the URL's
    extracted ID, then attempt to re-download the best-matching candidate.
    """
    # Use yt-dlp's output template for naming. Using the video ID in the filename
    # helps with deduplication and lookups.
    outtmpl = str(
        output_dir
        / playlist_name
        / "%(title)s [%(id)s].%(ext)s"
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
        trim_non_music=trim_non_music,
        sb_categories=sb_categories,
    )
    # First attempt (no geo override). We will only add --xff after detecting region restriction.
    rc, final_path_str, stderr = run_cmd(cmd)
    vid = get_video_id(url)
    
    final_path = Path(final_path_str) if final_path_str and rc == 0 else None
    error_message = f"[yt-dlp stderr] {stderr}" if rc != 0 and stderr else None

    # If region locked and stderr lists countries, attempt sequential retries using first N countries.
    # Pattern: "This video is available in Country1, Country2, Country3." (we reuse original stderr)
    if rc != 0 and stderr and classify_failure(error_message or "") == FAIL_REGION:
        # Extract country list after 'available in'
        m = re.search(r"available in (.+?)(?:\.|$)", stderr, re.IGNORECASE)
        if m:
            raw_list = m.group(1)
            # Split by comma and trim
            countries = [c.strip() for c in raw_list.split(",") if c.strip()]
            # Heuristic: map country names to ISO-like codes by taking first word letters
            # We attempt the first country with an uppercase word of 2+ letters (e.g., 'Canada', 'Poland').
            # For multi-word like 'United States' we pick 'US'. Basic mapping.
            tried = 0
            for country in countries:
                if tried >= 5:  # Don't loop forever
                    break
                # Generate candidate code
                parts = country.split()
                if len(parts) == 1 and len(parts[0]) <= 3:
                    code = parts[0].upper()
                elif len(parts) == 1:
                    # Take first two letters
                    code = parts[0][:2].upper()
                else:
                    # Multi-word -> use initials of first two words
                    code = (parts[0][0] + parts[1][0]).upper()
                # Skip obviously invalid codes
                if not re.fullmatch(r"[A-Z]{2,3}", code):
                    continue
                tried += 1
                vlog(f"[REGION] Retrying with X-Forwarded-For country hint: {code}")
                cmd_geo = build_ytdlp_cmd(
                    url=url,
                    outtmpl=outtmpl,
                    audio_format=audio_format,
                    audio_quality=audio_quality,
                    cookies=cookies,
                    rate_limit=rate_limit,
                    sleep=sleep,
                    prefer_music=prefer_youtube_music,
                    dry_run=dry_run,
                    trim_non_music=trim_non_music,
                    sb_categories=sb_categories,
                )
                # Inject XFF header code
                if "--xff" not in cmd_geo:
                    cmd_geo.insert(1, code)
                    cmd_geo.insert(1, "--xff")
                rc_geo, fp_geo, stderr_geo = run_cmd(cmd_geo)
                if rc_geo == 0 and fp_geo:
                    vid = get_video_id(url)  # Same video ID
                    final_path = Path(fp_geo)
                    error_message = None
                    rc = 0
                    stderr = ""
                    vlog(f"[REGION] Success with country hint {code}")
                    break
                else:
                    vlog(f"[REGION] Failed with {code}: {stderr_geo.splitlines()[-1] if stderr_geo else 'unknown error'}")

    # Fallback path: search for a replacement if unavailable
    if (
        not dry_run
        and retry_search_if_unavailable
        and rc != 0
        and error_message
        and classify_failure(error_message) == FAIL_UNAVAILABLE
    ):
        vlog(f"[FALLBACK] '{original_title or url}' reported unavailable. Attempting search for replacement...")
        expected_duration: Optional[int] = None
        # Try to probe original metadata (in case infojson still retrievable) to get duration
        probe_cmd: List[str] = ["yt-dlp", "-j", "--skip-download", url]
        if cookies and Path(cookies).is_file():
            probe_cmd += ["--cookies", cookies]
        prc, pout, perr = run_cmd(probe_cmd)
        if prc == 0 and pout:
            try:
                meta = json.loads(pout.splitlines()[0])
                if isinstance(meta, dict) and isinstance(meta.get("duration"), int):
                    expected_duration = meta.get("duration")
            except Exception:
                pass
        replacement_url = search_for_replacement(
            original_title=original_title,
            failed_url=url,
            cookies=cookies,
            rate_limit=rate_limit,
            sleep=sleep,
            prefer_music=prefer_youtube_music,
            max_results=fallback_max_results,
            expected_duration=expected_duration,
        )
        if replacement_url and replacement_url != url:
            vlog(f"[FALLBACK] Trying candidate: {replacement_url}")
            cmd2 = build_ytdlp_cmd(
                url=replacement_url,
                outtmpl=outtmpl,
                audio_format=audio_format,
                audio_quality=audio_quality,
                cookies=cookies,
                rate_limit=rate_limit,
                sleep=sleep,
                prefer_music=prefer_youtube_music,
                dry_run=dry_run,
                trim_non_music=trim_non_music,
                sb_categories=sb_categories,
            )
            rc2, fp2, stderr2 = run_cmd(cmd2)
            if rc2 == 0 and fp2:
                vlog(f"[FALLBACK] Replacement succeeded for '{original_title or url}'.")
                vid2 = get_video_id(replacement_url)
                return True, replacement_url, vid2, Path(fp2), None
            else:
                eprint(f"[FALLBACK-FAIL] Replacement attempt failed: {stderr2}")
        else:
            vlog("[FALLBACK] No viable replacement candidate found.")
    return rc == 0, url, vid, final_path, error_message

def normalize_title_for_search(title: str) -> str:
    """Normalize a title for searching: remove bracketed/parenthetical parts and excessive punctuation."""
    # Remove content inside brackets or parentheses to generalize the query
    cleaned = re.sub(r"\s*[\[(].*?[\])]", "", title)
    cleaned = re.sub(r"[\t\n\r]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def tokenize(s: str) -> List[str]:
    """Tokenize a string into lowercase alphanumeric words for simple overlap scoring."""
    return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if w]

def score_title_similarity(a: str, b: str) -> float:
    """Compute a simple overlap score between two titles (Jaccard on token sets)."""
    ta = set(tokenize(a))
    tb = set(tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0

MIN_FALLBACK_DURATION = 40  # seconds
DURATION_TOLERANCE = 0.25  # ±25%

def is_latin_dominant(title: str) -> bool:
    """Return True if a title is mostly Latin letters (basic ASCII a-z)."""
    letters = [c for c in title if c.isalpha()]
    if not letters:
        return False
    latin = [c for c in letters if ("a" <= c.lower() <= "z")]  # Basic ASCII only
    return (len(latin) / len(letters)) >= 0.7

def title_looks_noise(original_latin: bool, candidate: str) -> bool:
    """Determine if candidate title should be discarded for script/noise when original was Latin."""
    if not original_latin:
        return False
    if candidate.lower().startswith("unknown title"):
        return True
    if not is_latin_dominant(candidate):
        return True
    return False

def extract_best_audio_codec(formats: Any) -> Optional[str]:
    """Return the first usable audio codec from a list of formats."""
    if not isinstance(formats, list):
        return None
    for f in formats:
        if not isinstance(f, dict):
            continue
        ac = f.get("acodec")
        if ac and ac != "none":
            return str(ac)
    return None

def duration_within(expected: Optional[int], candidate: Optional[int]) -> bool:
    """Check duration similarity if expected known; otherwise always True."""
    if candidate is None:
        return False  # If we cannot know candidate duration, treat as unsuitable
    if candidate < MIN_FALLBACK_DURATION:
        return False
    if expected is None:
        return True
    low = expected * (1 - DURATION_TOLERANCE)
    high = expected * (1 + DURATION_TOLERANCE)
    return low <= candidate <= high

def search_for_replacement(
    original_title: Optional[str],
    failed_url: str,
    cookies: Optional[str],
    rate_limit: Optional[str],
    sleep: Optional[str],
    prefer_music: bool,
    max_results: int = 6,
    expected_duration: Optional[int] = None,
) -> Optional[str]:
    """Search YouTube for a replacement video using yt-dlp JSON output with filtering.

    Filtering steps:
    1. Discard candidates without a valid audio codec.
    2. Discard candidates shorter than MIN_FALLBACK_DURATION seconds.
    3. If expected_duration is known, enforce ± DURATION_TOLERANCE similarity.
    4. If original title is Latin dominant, discard non-Latin or "Unknown Title" style noise.
    5. Rank remaining by title similarity.
    """
    failed_vid = get_video_id(failed_url)
    if not original_title and not failed_vid:
        return None
    query_title = original_title or failed_vid or ""
    query_title = normalize_title_for_search(query_title)
    if not query_title:
        return None

    search_term = f"ytsearch{max_results}:{query_title}"  # yt-dlp search expression
    cmd: List[str] = ["yt-dlp", "-j", search_term]
    # Add optional common flags
    if cookies and Path(cookies).is_file():
        cmd += ["--cookies", cookies]
    if rate_limit:
        cmd += ["--limit-rate", rate_limit]
    _add_sleep_flags(cmd, sleep)

    rc, stdout, stderr = run_cmd(cmd)
    if rc != 0:
        vlog(f"[FALLBACK] Search command failed: {stderr}")
        return None
    # Each line is JSON; parse individually.
    candidates: List[Dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("id") and obj.get("title"):
                # Exclude the failed video id if present
                if obj.get("id") == failed_vid:
                    continue
                candidates.append(obj)
        except json.JSONDecodeError:
            continue
    if not candidates:
        return None
    original_latin = is_latin_dominant(original_title) if original_title else False

    filtered: List[Dict[str, Any]] = []
    for c in candidates:
        title = str(c.get("title", ""))
        duration = c.get("duration") if isinstance(c.get("duration"), int) else None
        acodec = extract_best_audio_codec(c.get("formats"))
        # Apply filters
        if title_looks_noise(original_latin, title):
            vlog(f"[FALLBACK-FILTER] Reject '{title}' (script/noise)")
            continue
        if not duration_within(expected_duration, duration):
            vlog(f"[FALLBACK-FILTER] Reject '{title}' (duration {duration})")
            continue
        if not acodec:
            vlog(f"[FALLBACK-FILTER] Reject '{title}' (no audio codec)")
            continue
        filtered.append(c)

    if not filtered:
        vlog("[FALLBACK] All candidates filtered out.")
        return None

    if original_title:
        for c in filtered:
            c["_sim"] = score_title_similarity(original_title, c.get("title", ""))
        filtered.sort(key=lambda x: x.get("_sim", 0.0), reverse=True)
    best = filtered[0]
    new_vid = best.get("id")
    if not new_vid:
        return None
    base = "https://music.youtube.com/watch?v=" if prefer_music else "https://www.youtube.com/watch?v="
    return f"{base}{new_vid}"

def write_m3u_for_playlist(library_root: Path, playlist_name: str, files: List[Path]) -> None:
    """Writes an M3U8 playlist file for a given list of tracks."""
    safe_name = re.sub(r'[\\/*?:"<>|]', "_", playlist_name)
    m3u_path = library_root / f"{safe_name}.m3u8"

    # Sort files alphabetically by filename
    sorted_files = sorted(files, key=lambda p: p.name.lower())

    try:
        with m3u_path.open("w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for p in sorted_files:
                # M3U paths should be relative to the library root, not the playlist file
                rel_path = p.relative_to(library_root)
                f.write(f"{rel_path.as_posix()}\n")

        vlog(f"[M3U] Wrote playlist: {m3u_path}")
    except Exception as e:
        eprint(f"[WARN] Failed to write M3U playlist {m3u_path}: {e}")

def process_playlist(
    playlist_path: Path,
    out_root: Path,
    args: argparse.Namespace,
    downloaded_vids: Dict[str, Path],
) -> Tuple[int, int, int, List[str]]:
    """
    Processes a single playlist file: loads tracks, downloads them, and reports results.
    Returns a tuple of (success_count, failure_count, skipped_count, failed_urls).
    """
    pl = load_playlist(playlist_path)
    if not pl:
        return 0, 0, 0, []

    playlist_name = pl.get("name", playlist_path.stem)
    if args.remove_videos_suffix and playlist_name.lower().endswith("-videos"):
        playlist_name = playlist_name[:-7].strip()
        
    log(f"\n>>> Processing playlist: {playlist_name}")

    urls_to_download: List[str] = []
    playlist_track_files: List[Path] = []
    skipped_count = 0

    # Map URL -> title for fallback search context
    url_title_map: Dict[str, str] = {}

    for t in pl.get("tracks", []):
        url = t.get("url")
        vid = t.get("videoId")
        title = t.get("title")

        # If we only have a videoId, construct the URL.
        if vid and not url:
            url = f"https://www.youtube.com/watch?v={vid}"
        
        # If we have a URL but no videoId, extract it.
        if url and not vid:
            vid = get_video_id(url)

        if not (url and vid):
            vlog(f"Skipping track with missing URL or videoId: {t.get('title', 'Unknown')}")
            continue

        if vid not in downloaded_vids:
            urls_to_download.append(url)
            if url and title:
                url_title_map[url] = title
        else:
            vlog(f"Skipping duplicate track in '{playlist_name}': {t.get('title', url)}")
            skipped_count += 1
            existing_path = downloaded_vids.get(vid)
            if existing_path:
                playlist_track_files.append(existing_path)

    if skipped_count > 0 and not VERBOSE:
        log(f"Skipped {skipped_count} tracks that already exist.")

    if not urls_to_download:
        log(f"No new tracks to download in playlist: {playlist_name}")
        if args.write_m3u and playlist_track_files:
            write_m3u_for_playlist(out_root, playlist_name, playlist_track_files)
        return 0, 0, skipped_count, []

    log(f"Found {len(urls_to_download)} new tracks. Starting downloads with concurrency={args.concurrency}...")

    failed_urls: List[str] = []
    download_errors: List[str] = []
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
                trim_non_music=args.trim_non_music,
                sb_categories=args.sb_categories,
                retry_search_if_unavailable=args.retry_search_if_unavailable,
                original_title=url_title_map.get(url),
                fallback_max_results=args.fallback_max_results,
            ): url
            for url in urls_to_download
        }

        # Add a progress bar if tqdm is installed
        iterator = as_completed(futs)
        start_time = time.time()
        downloaded_bytes = 0
        success_count_so_far = 0
        if tqdm:
            desc = f"Downloading '{playlist_name}'"
            # Custom bar format: show n/total and postfix (ETA + failures)
            bar_format = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{postfix}]"
            pbar = tqdm(iterator, total=len(futs), desc=desc, unit="song", leave=True, bar_format=bar_format)
            pbar.set_postfix_str("ETA --:-- | failed: 0")
            iterator = pbar

        failed_count = 0
        total_tasks = len(futs)

        def _fmt_eta(seconds: float) -> str:
            if seconds < 0 or seconds == float("inf"):
                return "--:--"
            if seconds >= 3600:
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                return f"{h:d}:{m:02d}:{s:02d}"
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m:02d}:{s:02d}"

        for f in iterator:
            ok, url, vid, final_path, error_message = f.result()
            if ok and vid and final_path:
                success_count_so_far += 1
                downloaded_vids[vid] = final_path
                playlist_track_files.append(final_path)
                try:
                    downloaded_bytes += final_path.stat().st_size
                except Exception:
                    pass
            else:
                failed_urls.append(url)
                failed_count += 1
                if error_message:
                    download_errors.append(error_message)

            if tqdm:
                processed = success_count_so_far + failed_count
                remaining = total_tasks - processed
                elapsed = time.time() - start_time
                # Time-based ETA
                eta_time = (elapsed / processed * remaining) if processed else float('inf')
                # Size/throughput-based ETA (if at least one success and bytes tracked)
                if success_count_so_far > 0 and downloaded_bytes > 0 and elapsed > 0:
                    avg_speed = downloaded_bytes / elapsed  # bytes per second
                    avg_size_per_track = downloaded_bytes / success_count_so_far
                    remaining_bytes = avg_size_per_track * remaining
                    if avg_speed > 0:
                        eta_size = remaining_bytes / avg_speed
                        # Blend: prefer size-based but fall back to time-based if wildly off
                        eta = min(max(eta_size, 0), eta_time * 3) if processed > 1 else eta_size
                    else:
                        eta = eta_time
                else:
                    eta = eta_time
                pbar.set_postfix_str(f"ETA {_fmt_eta(eta)} | failed: {failed_count}")

    # After the progress bar is finished, print any errors that occurred.
    if download_errors:
        for err in download_errors:
            eprint(err)

    success_count = len(urls_to_download) - len(failed_urls)
    log(f"Playlist '{playlist_name}' summary: {success_count} downloaded, {len(failed_urls)} failed, {skipped_count} skipped.")

    if failed_urls:
        eprint(f"  [FAILURES] for '{playlist_name}':")
        for url in failed_urls:
            eprint(f"    - {url}")

    if args.write_m3u and playlist_track_files:
        write_m3u_for_playlist(out_root, playlist_name, playlist_track_files)

    return success_count, len(failed_urls), skipped_count, failed_urls


def main() -> int:
    """Main entrypoint for the script."""
    ap = argparse.ArgumentParser(
        description="Download YouTube Music playlists from a Google Takeout.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    ap.add_argument("takeout_path", help="Path to folder containing Takeout JSON and/or CSV files.")
    ap.add_argument("-o", "--output-dir", default="/library", help="Output library directory.")
    ap.add_argument("--audio-format", default="m4a", choices=["flac", "alac", "wav", "aiff", "opus", "vorbis", "aac", "mp4a", "mp3", "ac4", "eac3", "ac3", "dts"], help="Output audio format.")
    ap.add_argument("--quality", default="0", help="For MP3, VBR quality from 0 (best) to 9 (worst).")
    ap.add_argument("--concurrency", type=int, default=2, help="Number of parallel downloads.")
    ap.add_argument("--prefer-youtube-music", action="store_true", help="Rewrite video URLs to music.youtube.com for better metadata.")
    ap.add_argument("--write-m3u", action="store_true", help="Write M3U8 playlists for each playlist.")
    ap.add_argument("--rate-limit", help="Limit download rate (e.g., '1M' for 1MB/s).")
    ap.add_argument("--sleep", help='Sleep between downloads: "N" for fixed seconds, or "MIN,MAX" for a random range.')
    ap.add_argument("--cookies", help="Path to a cookies.txt file (Netscape format) for private/gated content.")
    ap.add_argument("--dry-run", action="store_true", help="Simulate the process without downloading any files.")
    ap.add_argument("--remove-videos-suffix", action="store_true", help="Remove '-videos' suffix from playlist names.")
    ap.add_argument("--trim-non-music", action="store_true", help="Trim non-music segments using SponsorBlock (requires network access to API via yt-dlp).")
    ap.add_argument("--sb-categories", help="Comma-separated SponsorBlock categories to remove. Default: sponsor,intro,outro,selfpromo,music_offtopic")
    ap.add_argument("--retry-search-if-unavailable", action="store_true", help="On 'video unavailable' errors, search YouTube for a likely replacement and retry once.")
    ap.add_argument("--fallback-max-results", type=int, default=6, help="Max search results to consider for a fallback replacement.")
    ap.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output, e.g., for skipped tracks.")

    args = ap.parse_args()
    global VERBOSE
    VERBOSE = args.verbose

    takeout_path = Path(args.takeout_path).resolve()
    out_root = Path(args.output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if not takeout_path.exists():
        eprint(f"[ERROR] Path not found: {takeout_path}")
        return 2

    # Pre-scan the library to find tracks that have already been downloaded.
    downloaded_vids = find_existing_downloads(out_root)

    # Validate cookies file (non-fatal if invalid)
    if args.cookies:
        valid, msg = validate_cookies_file(Path(args.cookies))
        if valid:
            log(f"[COOKIES] {msg}")
        else:
            eprint(f"[COOKIES] {msg}")

    json_paths = find_json_playlists(takeout_path)
    if not json_paths:
        eprint("No JSON playlist files found in the provided path.")
        # Still exit 0 if we found existing files, as it's not an error.
        return 0 if downloaded_vids else 1

    log(f"Found {len(json_paths)} JSON playlist(s) to process.")
    total_success = 0
    total_failures = 0
    total_skipped = 0
    all_failed_urls: List[str] = []
    # This dictionary tracks all downloaded video IDs and their file paths across all playlists
    # It is pre-populated by the scan above.

    for jp in json_paths:
        s, f, sk, failed_urls = process_playlist(jp, out_root, args, downloaded_vids)
        total_success += s
        total_failures += f
        total_skipped += sk
        all_failed_urls.extend(failed_urls)

    log("\n" + "="*40)
    log("           DOWNLOAD SUMMARY")
    log("="*40)
    log(f"Total playlists processed: {len(json_paths)}")
    log(f"Total unique tracks downloaded: {total_success}")
    log(f"Total tracks skipped (already exist): {total_skipped}")
    log(f"Total failures: {total_failures}")
    log("="*40)

    if all_failed_urls:
        failure_log_path = takeout_path / "failed_downloads.log"
        try:
            with failure_log_path.open("w", encoding="utf-8") as f:
                f.write("# Failed Downloads\n\n")
                f.write("The following URLs failed to download:\n")
                for url in all_failed_urls:
                    f.write(f"- {url}\n")
            eprint(f"\n[INFO] A log of {total_failures} failed downloads was written to: {failure_log_path}")
        except Exception as e:
            eprint(f"\n[ERROR] Could not write failure log: {e}")

        eprint(f"\n[DONE] Completed with {total_failures} total failure(s).")
        return 1
    else:
        log("\n[DONE] All downloads completed successfully.")
        return 0


if __name__ == "__main__":
    sys.exit(main())

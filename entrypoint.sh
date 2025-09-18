#!/usr/bin/env bash
set -euo pipefail

TAKEOUT_PATH="${TAKEOUT_PATH:-/data}"
OUTPUT_DIR="${OUTPUT_DIR:-/library}"

# Convert any CSV playlists to JSON before running the downloader
echo "Scanning for CSV playlists in: ${TAKEOUT_PATH}"
python /app/convert_csv_to_takeout_json.py "${TAKEOUT_PATH}"

# Runtime options
AUDIO_FORMAT="${AUDIO_FORMAT:-m4a}"
QUALITY="${QUALITY:-0}"
COOKIES="${COOKIES:-}"
RATE_LIMIT="${RATE_LIMIT:-}"
SLEEP="${SLEEP:-}"
PREFER_YOUTUBE_MUSIC="${PREFER_YOUTUBE_MUSIC:-1}"
CONCURRENCY="${CONCURRENCY:-2}"
WRITE_M3U="${WRITE_M3U:-1}"
DRY_RUN="${DRY_RUN:-0}"

ARGS=()
ARGS+=("$TAKEOUT_PATH" "-o" "$OUTPUT_DIR" "--audio-format" "$AUDIO_FORMAT" "--quality" "$QUALITY" "--concurrency" "$CONCURRENCY")

# Apply a default rate limit if no cookies are used, to be safer against IP bans.
# The user can override this by setting RATE_LIMIT to a value or an empty string.
if ! [[ -n "$COOKIES" && -f "$COOKIES" ]] && [[ -z "$RATE_LIMIT" ]]; then
    # Check if RATE_LIMIT was explicitly set to empty in the environment
    if ! (env | grep -q "^RATE_LIMIT=$"); then
        echo "No cookies found. Applying a default rate limit of 500K to be safe."
        RATE_LIMIT="500K"
    fi
fi

if [[ -n "$COOKIES" && -f "$COOKIES" ]]; then
  ARGS+=("--cookies" "$COOKIES")
fi
if [[ -n "$RATE_LIMIT" ]]; then
  ARGS+=("--rate-limit" "$RATE_LIMIT")
fi
if [[ -n "$SLEEP" ]]; then
  ARGS+=("--sleep" "$SLEEP")
fi
if [[ "$PREFER_YOUTUBE_MUSIC" == "1" ]]; then
  ARGS+=("--prefer-youtube-music")
fi
if [[ "$WRITE_M3U" == "1" ]]; then
  ARGS+=("--write-m3u")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  ARGS+=("--dry-run")
fi

echo "Running: python /app/ytm_takeout_downloader.py ${ARGS[*]}"
exec python /app/ytm_takeout_downloader.py "${ARGS[@]}"
fi

echo "Running: python /app/ytm_takeout_downloader.py ${ARGS[*]}"
exec python /app/ytm_takeout_downloader.py "${ARGS[@]}"

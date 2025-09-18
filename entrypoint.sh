#!/usr/bin/env bash
set -euo pipefail

# Default values for environment variables
TAKEOUT_PATH="${TAKEOUT_PATH:-/data}"
OUTPUT_DIR="${OUTPUT_DIR:-/library}"
AUDIO_FORMAT="${AUDIO_FORMAT:-m4a}"
QUALITY="${QUALITY:-0}"
CONCURRENCY="${CONCURRENCY:-2}"
WRITE_M3U="${WRITE_M3U:-1}"
REMOVE_VIDEOS_SUFFIX="${REMOVE_VIDEOS_SUFFIX:-1}"
PREFER_YOUTUBE_MUSIC="${PREFER_YOUTUBE_MUSIC:-1}"
DRY_RUN="${DRY_RUN:-0}"
COOKIES_PATH="${COOKIES:-}" # Use a different name to avoid conflict with the arg
RATE_LIMIT_VAL="${RATE_LIMIT:-}" # Use a different name
SLEEP_VAL="${SLEEP:-}" # Use a different name

# 1. Convert CSVs to JSON
# Build arguments for the conversion script
CONVERT_ARGS=("${TAKEOUT_PATH}")
if [[ "$REMOVE_VIDEOS_SUFFIX" == "1" ]]; then
    CONVERT_ARGS+=("--remove-videos-suffix")
fi
echo "--> Scanning for CSV playlists in '${TAKEOUT_PATH}' to convert..."
python /app/convert_csv_to_takeout_json.py "${CONVERT_ARGS[@]}"
echo "--> CSV conversion finished."

# 2. Build arguments for the main downloader script
ARGS=()
ARGS+=("$TAKEOUT_PATH")
ARGS+=("-o" "$OUTPUT_DIR")
ARGS+=("--audio-format" "$AUDIO_FORMAT")
ARGS+=("--quality" "$QUALITY")
ARGS+=("--concurrency" "$CONCURRENCY")

# Apply a default rate limit if no cookies are used, to be safer against IP bans.
# The user can override this by setting RATE_LIMIT to a value or an empty string.
if ! [[ -n "$COOKIES_PATH" && -f "$COOKIES_PATH" ]] && [[ -z "$RATE_LIMIT_VAL" ]]; then
    # Check if RATE_LIMIT was explicitly set to empty in the environment
    if ! (env | grep -q "^RATE_LIMIT=$"); then
        echo "--> No cookies file found. Applying a default rate limit of 500K to be safe."
        RATE_LIMIT_VAL="500K"
    fi
fi

# Add optional arguments if they are set
if [[ -n "$COOKIES_PATH" && -f "$COOKIES_PATH" ]]; then
  ARGS+=("--cookies" "$COOKIES_PATH")
fi
if [[ -n "$RATE_LIMIT_VAL" ]]; then
  ARGS+=("--rate-limit" "$RATE_LIMIT_VAL")
fi
if [[ -n "$SLEEP_VAL" ]]; then
  ARGS+=("--sleep" "$SLEEP_VAL")
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
if [[ "$REMOVE_VIDEOS_SUFFIX" == "1" ]]; then
  ARGS+=("--remove-videos-suffix")
fi

# 3. Run the downloader
echo "--> Starting downloader with arguments: ${ARGS[*]}"
exec python /app/ytm_takeout_downloader.py "${ARGS[@]}"


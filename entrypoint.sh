#!/usr/bin/env bash
set -euo pipefail

# Activate virtual environment
export PATH="/opt/venv/bin:$PATH"

# Default values for environment variables
TAKEOUT_PATH="${TAKEOUT_PATH:-/data}"
OUTPUT_DIR="${OUTPUT_DIR:-/library}"
AUDIO_FORMAT="${AUDIO_FORMAT:-m4a}"
QUALITY="${QUALITY:-0}"
CONCURRENCY="${CONCURRENCY:-4}"
WRITE_M3U="${WRITE_M3U:-1}"
REMOVE_VIDEOS_SUFFIX="${REMOVE_VIDEOS_SUFFIX:-1}"
PREFER_YOUTUBE_MUSIC="${PREFER_YOUTUBE_MUSIC:-1}"
DRY_RUN="${DRY_RUN:-0}"
COOKIES_PATH="${COOKIES:-}" # Use a different name to avoid conflict with the arg
RATE_LIMIT_VAL="${RATE_LIMIT:-}" # Use a different name
SLEEP_VAL="${SLEEP:-}" # Use a different name
TRIM_NON_MUSIC="${TRIM_NON_MUSIC:-0}"
SPONSORBLOCK_CATEGORIES="${SPONSORBLOCK_CATEGORIES:-}" # Optional custom list
RETRY_SEARCH_IF_UNAVAILABLE="${RETRY_SEARCH_IF_UNAVAILABLE:-1}" # Enable fallback search by default
FALLBACK_MAX_RESULTS="${FALLBACK_MAX_RESULTS:-6}" # Number of search results to consider for replacement

# Mode selection: 'takeout' or 'liked' (mutually exclusive)
MODE="${MODE:-takeout}"
LIKED_PLAYLIST_NAME="${LIKED_PLAYLIST_NAME:-Liked Songs}"
JELLYFIN_URL="${JELLYFIN_URL:-}"
JELLYFIN_API_KEY="${JELLYFIN_API_KEY:-}"

TAKEOUT_SOURCE_PATH="$TAKEOUT_PATH"
if [[ "$MODE" == "takeout" ]]; then
  # 1. Convert CSVs to JSON
  # Build arguments for the conversion script
  CONVERT_ARGS=("${TAKEOUT_PATH}")
  if [[ "$REMOVE_VIDEOS_SUFFIX" == "1" ]]; then
      CONVERT_ARGS+=("--remove-videos-suffix")
  fi
  echo "--> Scanning for CSV playlists in '${TAKEOUT_PATH}' to convert..."
  python /app/convert_csv_to_takeout_json.py "${CONVERT_ARGS[@]}"
  echo "--> CSV conversion finished."
elif [[ "$MODE" == "liked" ]]; then
  # 1. Export liked songs to a single JSON file in /data
  echo "--> Exporting YouTube Music liked songs to JSON..."
  L_OUT_DIR="${TAKEOUT_PATH}/.liked"
  mkdir -p "${L_OUT_DIR}"
  python /app/ytm_liked_songs_exporter.py --cookies "${COOKIES_PATH}" --out-dir "${L_OUT_DIR}" --name "${LIKED_PLAYLIST_NAME}"
  LIKED_JSON_PATH="${L_OUT_DIR}/${LIKED_PLAYLIST_NAME}.json"
  echo "--> Liked songs export finished."
  TAKEOUT_SOURCE_PATH="${L_OUT_DIR}"
else
  echo "[ERROR] MODE must be either 'takeout' or 'liked'" >&2
  exit 2
fi

# 2. Build arguments for the main downloader script
ARGS=()
ARGS+=("$TAKEOUT_SOURCE_PATH")
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
if [[ "$TRIM_NON_MUSIC" == "1" ]]; then
  ARGS+=("--trim-non-music")
  if [[ -n "$SPONSORBLOCK_CATEGORIES" ]]; then
    ARGS+=("--sb-categories" "$SPONSORBLOCK_CATEGORIES")
  fi
fi
if [[ "$RETRY_SEARCH_IF_UNAVAILABLE" == "1" ]]; then
  ARGS+=("--retry-search-if-unavailable")
fi
if [[ -n "$FALLBACK_MAX_RESULTS" ]]; then
  ARGS+=("--fallback-max-results" "$FALLBACK_MAX_RESULTS")
fi

# 3. Run the downloader
echo "--> Starting downloader with arguments: ${ARGS[*]}"
set +e
python /app/ytm_takeout_downloader.py "${ARGS[@]}"
DL_RC=$?
set -e

# 4. If requested, like all downloaded songs in Jellyfin (liked mode only or when explicitly configured)
if [[ -n "${JELLYFIN_URL}" && -n "${JELLYFIN_API_KEY}" ]]; then
  echo "--> Marking downloaded songs as favorite in Jellyfin..."
  if [[ "$MODE" == "liked" && -n "${LIKED_JSON_PATH:-}" && -f "${LIKED_JSON_PATH}" ]]; then
    python /app/jellyfin_like_from_library.py --playlist-json "${LIKED_JSON_PATH}" --jellyfin-url "${JELLYFIN_URL}" --jellyfin-api-key "${JELLYFIN_API_KEY}" || true
  else
    python /app/jellyfin_like_from_library.py --library "${OUTPUT_DIR}" --jellyfin-url "${JELLYFIN_URL}" --jellyfin-api-key "${JELLYFIN_API_KEY}" || true
  fi
fi

exit ${DL_RC}


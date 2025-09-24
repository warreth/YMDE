# Get started — Takeout mode

Use this if you exported playlists via Google Takeout.

## Prerequisites

- Docker and Docker Compose installed.
- Create working folders once:

```bash
mkdir -p data library
```

## 1. Prepare your Takeout files

- Copy your `.json` and/or `.csv` playlists from
  `Takeout/YouTube and YouTube Music/playlists/` into `./data/`.

## 2. Minimal compose.yml

```yaml
services:
  ymde:
    image: ghcr.io/warreth/ymde:latest
    container_name: ymde
    volumes:
      - ./data:/data
      - ./library:/library
    environment:
      # --- Mode ---
      - MODE=takeout

      # --- General ---
      - AUDIO_FORMAT=m4a
      - QUALITY=0
      - CONCURRENCY=4
      - WRITE_M3U=1
      - PREFER_YOUTUBE_MUSIC=1
      - TRIM_NON_MUSIC=1
      - RETRY_SEARCH_IF_UNAVAILABLE=1
      # Optional advanced
      # - RATE_LIMIT=1M
      # - SLEEP="2,8"
      # - DRY_RUN=1
      # - COOKIES=/data/cookies.txt

      # --- Takeout specific ---
      - REMOVE_VIDEOS_SUFFIX=1
```

## 3. Run it

```bash
docker compose run --rm ymde
```

## What happens

- CSVs (if present) are converted to the downloader’s JSON format.
- Tracks are downloaded to `./library` with embedded metadata and thumbnails.
- `.m3u8` playlists are created when `WRITE_M3U=1`.

## Tips

- Use a cookies file if some items are private/age-restricted. See `docs/COOKIES.md`.
- You can map `/library` directly to your media server’s music path for zero copy.

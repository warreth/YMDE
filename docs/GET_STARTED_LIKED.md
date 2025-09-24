# Get started — Liked mode

Use this to export and download your YouTube Music “Liked Songs”.

## Prerequisites

- Docker and Docker Compose installed.
- Create working folders once:

```bash
mkdir -p data library
```

## 1. Export your cookies

Follow `docs/COOKIES.md` to export a Netscape `cookies.txt` from your logged-in browser and place it at `./data/cookies.txt`.

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
      - MODE=liked

      # --- General ---
      - AUDIO_FORMAT=m4a
      - QUALITY=0
      - CONCURRENCY=4
      - WRITE_M3U=1       # default; can be overridden below in liked mode
      - PREFER_YOUTUBE_MUSIC=1
      - TRIM_NON_MUSIC=1
      - RETRY_SEARCH_IF_UNAVAILABLE=1
      - COOKIES=/data/cookies.txt

      # --- Liked specific ---
      - LIKED_PLAYLIST_NAME=Liked Songs
      - LIKED_CREATE_PLAYLIST=1   # set 0 to not create an .m3u playlist

      # --- Jellyfin (optional) ---
      - JELLYFIN_URL=              # e.g., http://localhost:8096
      - JELLYFIN_API_KEY=
```

## 3. Run it

```bash
docker compose run --rm ymde
```

## What happens

- YMDE exports your “Liked Songs” to `./data/.liked/Liked Songs.json` (name configurable).
- Downloads into `./library/Liked Songs/`.
- If `JELLYFIN_URL` and `JELLYFIN_API_KEY` are set, it marks those tracks as Favorite in Jellyfin.
- If `LIKED_CREATE_PLAYLIST=1`, it also creates `Liked Songs.m3u8`.

## Tips

- If you only want to like songs in Jellyfin without an M3U, set `LIKED_CREATE_PLAYLIST=0`.
- You can still use `RATE_LIMIT`, `SLEEP`, or `DRY_RUN` from the advanced options to control behavior.

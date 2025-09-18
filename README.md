# YMDE (YouTube Music Downloader and Exporter)

This container:
- Scans your Google Takeout JSON playlists (from YouTube/YouTube Music).
- Also converts CSV playlists to the same JSON format.
- Downloads audio for each track using `yt-dlp`.
- Organizes and tags files for media servers like Jellyfin.
- Saves files to `library/Artist/Album/Title.ext`.
- Optionally writes `.m3u8` playlists to `library/_playlists/`.

Note: Use this tool only in ways permitted by YouTube’s Terms of Service and your local laws.

## Quick Start

1.  **Prerequisites**: Docker and Docker Compose must be installed.

2.  **Setup Folders**: Create `data` and `library` directories next to your `compose.yml` file.

    ```bash
    mkdir -p data library
    ```

    - Place your Takeout JSON and/or CSV files in `./data`.
    - If needed for private or age-gated content, save your browser cookies as `./data/cookies.txt` (Netscape format).

3.  **Build the Image**:

    ```bash
    docker compose build
    ```

4.  **Run the Downloader**:

    ```bash
    docker compose run --rm ymde
    ```

5.  **Check the Results**:
    - Your audio files will be in `./library`.
    - Playlists, if enabled, will be in `./library/_playlists/*.m3u8`.

## Configuration

Edit `compose.yml` to change the default settings via environment variables:

- `AUDIO_FORMAT`: `m4a` (default) or `mp3`.
- `QUALITY`: For `mp3`, this is the VBR quality from `0` (best) to `9` (worst). Default is `0`.
- `CONCURRENCY`: Number of parallel downloads (e.g., `4`).
- `WRITE_M3U`: `1` to create M3U8 playlists from the downloaded folder structure (one per album).
- `REMOVE_VIDEOS_SUFFIX`: `1` (default) to automatically remove the `-videos` suffix from playlist names (e.g., `My Playlist-videos` becomes `My Playlist`). Set to `0` to disable.
- `PREFER_YOUTUBE_MUSIC`: `1` to rewrite YouTube video URLs to `music.youtube.com` for better metadata.
- `VERBOSE`: `0` (default) to show a progress bar, or `1` to show detailed real-time output from `yt-dlp`.
- `RATE_LIMIT`: Download speed limit, e.g., `1M`. To prevent IP bans, this is automatically set to `500K` if you are not using cookies. You can set it to `""` to disable the limit or choose your own value.
- `SLEEP`: A fixed or random delay between downloads, e.g., `5` or `2,8` (for 2-8 seconds).
- `DRY_RUN`: `1` to simulate the process without downloading files.
- `COOKIES`: Path to a cookies file inside the container (default: `/data/cookies.txt`).


## Alternative: `docker run` (without Compose)

```bash
docker build -t ymde .
docker run --rm \
  -v "$PWD/data:/data" \
  -v "$PWD/library:/library" \
  -e AUDIO_FORMAT=m4a \
  -e QUALITY=0 \
  -e CONCURRENCY=2 \
  -e WRITE_M3U=1 \
  -e PREFER_YOUTUBE_MUSIC=1 \
  -e SLEEP="1,3" \
  -e COOKIES=/data/cookies.txt \
  ymde
```

## Tips

- **Folder Structure**: The downloader saves files in an `Artist/Album` structure. This is highly recommended for media servers like Jellyfin, as it helps them correctly identify and organize your music library.
- **Cookies**: Install `cookies.txt` only if needed for age-gated/region/private content.
- **Metadata**: If `yt-dlp` occasionally picks the wrong version of a song, you can edit the URL in your source JSON file and re-run the downloader.

## Disclaimer

This tool is a wrapper around `yt-dlp`. Ensure your use of this software complies with all applicable laws and the terms of service of any websites you access. The developers of this tool are not responsible for its misuse.

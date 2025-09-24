# YMDE: YouTube Music Downloader & Exporter

<!-- Badges -->
![GitHub Stars](https://img.shields.io/github/stars/WarreTh/YMDE?style=flat&color=yellow)
![Release Build](https://github.com/WarreTh/ymde/actions/workflows/build-docker.yml/badge.svg)
![Docker Downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fipitio%2Fbackage%2Frefs%2Fheads%2Findex%2FWarreTh%2FYMDE%2F.json&query=%24%5B0%5D.downloads&label=Total%20Downloads&color=blue)
![Docker Daily Downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fipitio%2Fbackage%2Frefs%2Fheads%2Findex%2FWarreTh%2FYMDE%2F.json&query=%24%5B0%5D.downloads_day&label=Dowloads%20(today)&color=teal)

> **Enjoying YMDE? Please consider [starring the project on GitHub](https://github.com/WarreTh/ymde/stargazers)! Your support helps the project grow.**

YMDE is a simple tool for downloading your music from YouTube and organizing it into a clean, tagged library suitable for media servers like Jellyfin or Plex.

It can either:

- Process your Google Takeout playlists (JSON/CSV), or
- Log in using your browser cookies to export your YouTube Music Liked Songs and download them.

Both flows save audio into a structured, tagged library folder.

**Disclaimer**: This tool is for personal, archival purposes only. Ensure your use complies with YouTube's Terms of Service and all applicable laws in your country.

## Features

- **Process Google Takeout**: Directly handles `JSON` and `CSV` playlists from your YouTube Music export.
- **Optimized for Media Servers**: Creates a clean library structure compatible with Jellyfin, Plex, and others.
- **Parallel Downloads**: Uses `yt-dlp` with multiple concurrent downloads for speed.
- **Embedded Metadata & Thumbnails**: Automatically tags audio files with track info and cover art.
- **Automatic Playlist Generation**: Creates `.m3u8` playlist files for easy importing.
- **Smart Deduplication**: Avoids re-downloading tracks that already exist anywhere in your library.
- **Automatic Title Cleaning**: Removes clutter like `(Official Video)` from track titles.
- **Optional Non-Music Trimming (SponsorBlock)**: Remove intros/outros/sponsor/selfpromo/misc segments using community data (enabled by default).
- **Automatic Replacement Search**: If a track fails with a "video unavailable" error, YMDE can automatically search YouTube for a likely replacement and download it instead (enabled by default).

## Get Started

Pick one of these guides based on your workflow:

- Get started with Google Takeout playlists: [GET_STARTED_TAKEOUT.md](docs/GET_STARTED_TAKEOUT.md)
- Get started with Liked Songs: [GET_STARTED_LIKED.md](docs/GET_STARTED_LIKED.md)

## Choose your mode

Set `MODE` to select exactly one flow:

- `takeout`: read your Takeout playlists (JSON/CSV) and download.
- `liked`: export YouTube Music “Liked Songs” using cookies and download; optionally auto-like in Jellyfin.

At the end of the run, YMDE prints a summary of downloaded, skipped, and failed tracks.

## Configuration

All settings are managed through environment variables in your `compose.yml` file.

| Variable                 | Description                                                                                             | Default     |
| ------------------------ | ------------------------------------------------------------------------------------------------------- | ----------- |
| `AUDIO_FORMAT`           | Output audio format.                                                                                    | `m4a`       |
| `QUALITY`                | For `mp3`, VBR quality (`0`=best, `9`=worst).                                                           | `0`         |
| `CONCURRENCY`            | Number of downloads to run in parallel.                                                                 | `4`         |
| `WRITE_M3U`              | `1` to create `.m3u8` playlists in a `_playlists` folder.                                               | `1`         |
| `REMOVE_VIDEOS_SUFFIX`   | `1` to change `My Playlist-videos` to `My Playlist`.                                                      | `1`         |
| `PREFER_YOUTUBE_MUSIC`   | `1` to rewrite URLs to `music.youtube.com` for better metadata.                                           | `1`         |
| `TRIM_NON_MUSIC`         | `1` to trim non-music segments (SponsorBlock).                                                            | `1`         |
| `RETRY_SEARCH_IF_UNAVAILABLE` | `1` to auto-search & retry when a video is unavailable.                                           | `1`         |
| `FALLBACK_MAX_RESULTS`    | Max search results considered for a replacement when unavailable.                                     | `6`         |
| `SPONSORBLOCK_CATEGORIES`| Override categories (comma list). Default when enabled: `sponsor,intro,outro,selfpromo,music_offtopic`   | ` `         |
| `RATE_LIMIT`             | Download speed limit (e.g., `1M`). **Automatically set to `500K` if no cookies are used.**                | ` `         |
| `SLEEP`                  | Delay between downloads. Fixed (`5`) or random range (`2,8`).                                           | ` `         |
| `DRY_RUN`                | `1` to simulate the process without downloading files.                                                  | `0`         |
| `COOKIES`                | Path to a `cookies.txt` file (Netscape format) for accessing private or age-gated content.              | ` `         |
| `MODE`                   | Flow selector: `takeout` (Takeout playlists) or `liked` (YouTube Music Liked Songs).                   | `takeout`   |
| `LIKED_PLAYLIST_NAME`    | Playlist name for the exported liked songs JSON (MODE=liked).                                         | `Liked Songs` |
| `LIKED_CREATE_PLAYLIST`  | In liked mode, `1` to create an `.m3u8` playlist, `0` to skip creating a playlist.                    | `1`         |
| `JELLYFIN_URL`           | Base URL to your Jellyfin server. If set with `JELLYFIN_API_KEY`, YMDE will mark downloaded songs as favorite. | ` `         |
| `JELLYFIN_API_KEY`       | Jellyfin API key for the user to mark items as favorite.                                               | ` `         |

## Usage with Jellyfin

There are two easy ways to get your downloaded music into Jellyfin:

### Method 1: Manual Copy

1. Run the downloader as described in the Quick Start.
2. Once finished, copy all the contents from the local `./library` folder into your Jellyfin music library directory.
3. In Jellyfin, go to **Dashboard** -> **Libraries**, click the three dots on your music library, and select **Scan Library**.

Jellyfin will import the music and automatically detect the `.m3u8` playlists.

### Method 2: Direct Mapping (Recommended)

For a seamless experience, you can map the output directory directly to your Jellyfin music library. This way, music and playlists appear in Jellyfin automatically after the downloader runs.

1. Find the absolute path to your Jellyfin music library on your host machine (e.g., `/storage/music` or `/home/user/jellyfin/music`).
2. Update the `volumes` section in your `compose.yml` to point to that path:

    ```yaml
    services:
      ymde:
        # ... other settings
        volumes:
          - ./data:/data
          - /path/to/your/jellyfin/music:/library # <-- Change this line
        # ... other settings
    ```

3. Run the downloader: `docker compose run --rm ymde`.
4. Scan your library in Jellyfin. New content will be added automatically.

This avoids any manual copying and keeps your library perfectly in sync.

## FAQ

### Why do I see "video unavailable" or "age-restricted" errors?

This often happens when YouTube requires you to be logged in to view certain content (e.g., age-gated videos) or when a video is private or unavailable in your region.

**Solution**: Use a `cookies.txt` file. By providing cookies from your logged-in YouTube session, YMDE can access these videos just like your browser.

1. Export your cookies from your browser into a `cookies.txt` file. For detailed instructions, see the guide on [how to use cookies](/docs/COOKIES.md).
2. Place the `cookies.txt` file in your `./data/` folder.
3. Uncomment and set the `COOKIES` environment variable in your `compose.yml`:

    ```yaml
    environment:
      # ...
      - COOKIES=/data/cookies.txt
    ```

### How do I keep my library updated?

You can run YMDE periodically to download new songs from your playlists. The tool automatically skips any tracks that are already in your library (even in different playlists), so it only downloads what's new.

This is a great way to maintain a long-term archive of your music. Just re-run the same command whenever you want to sync:

```bash
docker compose run --rm ymde
```

## Building the Image Manually

If you prefer to build the Docker image locally instead of using a pre-built one from a registry:

1. **Clone the repository**:

    ```bash
    git clone https://github.com/WarreTh/ymde.git
    cd ymde
    ```

    > **Error Checking**: If you already have the repo, skip this step. If you get an error, check your internet connection or repository URL.

2. **Build the image**:

    ```bash
    docker compose build
    ```

    > **Error Checking**: If you get a build error, ensure Docker is running and you are in the correct directory.

3. **Run the container**:

    ```bash
    docker compose run --rm ymde
    ```

    > **Error Checking**: If you get a runtime error, check your Docker Compose file and environment variables.

## License

This project is licensed under the AGPL-3.0 License. See the [LICENSE](LICENSE) file for details.

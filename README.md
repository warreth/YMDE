# YMDE: YouTube Music Downloader & Exporter

<!-- Badges -->
![GitHub Stars](https://img.shields.io/github/stars/WarreTh/YMDE?style=flat&color=yellow)
![Release Build](https://github.com/WarreTh/ymde/actions/workflows/build-docker.yml/badge.svg)
![Docker Downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fipitio%2Fbackage%2Frefs%2Fheads%2Findex%2FWarreTh%2FYMDE%2F.json&query=%24%5B0%5D.downloads&label=Total%20Downloads&color=blue)
![Docker Daily Downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fipitio%2Fbackage%2Frefs%2Fheads%2Findex%2FWarreTh%2FYMDE%2F.json&query=%24%5B0%5D.downloads_day&label=Dowloads%20(today)&color=teal)


> **Enjoying YMDE? Please consider [starring the project on GitHub](https://github.com/WarreTh/ymde/stargazers)! Your support helps the project grow.**

YMDE is a simple tool for downloading your music from YouTube and organizing it into a clean, tagged library suitable for media servers like Jellyfin or Plex.

It scans your Google Takeout playlists (both JSON and CSV), downloads the audio for each track, and saves it into a structured folder format.

**Disclaimer**: This tool is for personal, archival purposes only. Ensure your use complies with YouTube's Terms of Service and all applicable laws in your country.

## Features

* **Process Google Takeout**: Directly handles `JSON` and `CSV` playlists from your YouTube Music export.
* **Optimized for Media Servers**: Creates a clean library structure compatible with Jellyfin, Plex, and others.
* **Parallel Downloads**: Uses `yt-dlp` with multiple concurrent downloads for speed.
* **Embedded Metadata & Thumbnails**: Automatically tags audio files with track info and cover art.
* **Automatic Playlist Generation**: Creates `.m3u8` playlist files for easy importing.
* **Smart Deduplication**: Avoids re-downloading tracks that already exist anywhere in your library.
* **Automatic Title Cleaning**: Removes clutter like `(Official Video)` from track titles.
* **Optional Non-Music Trimming (SponsorBlock)**: Remove intros/outros/sponsor/selfpromo/misc segments using community data (enabled by default).
* **Automatic Replacement Search**: If a track fails with a "video unavailable" error, YMDE can automatically search YouTube for a likely replacement and download it instead (enabled by default).

## Get Started

**Prerequisites**: You need Docker and Docker Compose installed.

### 1. Set Up Your Folders

Create `data` and `library` folders in the same directory as the `compose.yml` file.

```bash
mkdir -p data library
```
 
### 2. Download Google Takeout Data

**Quick Steps:**

1. Go to [Google Takeout](https://takeout.google.com/).
2. **Uncheck all categories** except **"YouTube and YouTube Music"**.
3. Click **"Multiple formats"** and set **History** to **JSON** or **CSV**.
4. Click **"Next step"** and **request your data**.
5. When your archive is ready, **download and extract it**.
6. **Copy all `.csv` and `.json` files** from  
   `Takeout/YouTube and YouTube Music/playlists/`  
   into your local `./data/` folder.

### 3. Create a `compose.yml` File

Copy the example below and save it as `compose.yml`.

```yaml
services:
  ymde:
    image: ghcr.io/warreth/ymde:latest
    container_name: ymde
    volumes:
      - ./data:/data
      - ./library:/library
    environment:
      # --- Basic Configuration ---
      - AUDIO_FORMAT=m4a          # m4a or mp3
      - QUALITY=0                 # For MP3, VBR quality (0=best, 9=worst)
      - CONCURRENCY=4             # Number of parallel downloads
      - WRITE_M3U=1               # 1=Create M3U8 playlists, 0=disable
      - REMOVE_VIDEOS_SUFFIX=1    # 1=Remove "-videos" from playlist names, 0=disable
      - PREFER_YOUTUBE_MUSIC=1    # 1=Rewrite URLs to music.youtube.com for better metadata
      - TRIM_NON_MUSIC=1          # 1=Trim non-music segments via SponsorBlock
      - RETRY_SEARCH_IF_UNAVAILABLE=1 # 1=Search for replacement if original video is unavailable
      
      # --- Advanced Configuration ---
      # - RATE_LIMIT=1M             # Limit download speed (e.g., 500K, 1M).
      # - SLEEP="2,8"               # Sleep for a random 2-8 seconds between downloads.
      # - DRY_RUN=1                 # 1=Simulate without downloading, 0=disable
      # - COOKIES=/data/cookies.txt # Path to cookies file for private/gated content.
      # - SPONSORBLOCK_CATEGORIES="sponsor,intro,outro" # Example overriding categories
```

### 4. Run the Downloader

Execute the downloader using Docker Compose. It will pull the image (if not local), run the process, and then exit.

```bash
docker compose run --rm ymde
```

Your music will appear in the `./library` directory, organized by playlist.

At the end of the process, you will see a summary of how many tracks were downloaded, skipped, or failed.

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

# YMDE: YouTube Music Downloader & Exporter

YMDE is a simple tool for downloading your music from YouTube and organizing it into a clean, tagged library suitable for media servers like Jellyfin or Plex.

It scans your Google Takeout playlists (both JSON and CSV), downloads the audio for each track, and saves it into a structured folder format.

**Disclaimer**: This tool is for personal, archival purposes only. Ensure your use complies with YouTube's Terms of Service and all applicable laws in your country.

## Features

- **Google Takeout Support**: Directly processes playlists from your YouTube Music data.
- **CSV Conversion**: Automatically converts `.csv` playlists into the required format.
- **Efficient Downloading**: Uses `yt-dlp` for reliable downloads with parallel processing.
- **Organized Library**: Saves files as `Playlist Name/Title [VideoID].ext`.
- **Metadata & Thumbnails**: Embeds metadata and video thumbnails into audio files.
- **M3U Playlists**: Optionally generates `.m3u8` playlists in a `_playlists` folder.
- **Deduplication**: Prevents re-downloading tracks that already exist across all playlists.

## Quick Start

**Prerequisites**: You need Docker and Docker Compose installed.

### 1. Set Up Your Folders

Create `data` and `library` folders in the same directory as the `compose.yml` file.

```bash
mkdir -p data library
```

- **`./data`**: Place your Google Takeout `*.json` or `*.csv` playlist files here.
- **`./library`**: This is where your downloaded music will be saved.

### 2. Create a `compose.yml` File

Copy the example below and save it as `compose.yml`.

```yaml
services:
  ymde:
    image: ghcr.io/your-github-username/ymde:latest
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
      
      # --- Advanced Configuration ---
      # - RATE_LIMIT=1M             # Limit download speed (e.g., 500K, 1M). Auto-set to 500K if no cookies.
      # - SLEEP="2,8"               # Sleep for a random 2-8 seconds between downloads.
      # - DRY_RUN=1                 # 1=Simulate without downloading, 0=disable
      # - COOKIES=/data/cookies.txt # Path to cookies file for private/gated content.
```

**Important**: Replace `ghcr.io/your-github-username/ymde:latest` with the actual image path after you set up the GitHub Action.

### 3. Run the Downloader

Execute the downloader using Docker Compose. It will pull the image (if not local), run the process, and then exit.

```bash
docker compose run --rm ymde
```

Your music will appear in the `./library` directory, organized by playlist.

## Configuration

All settings are managed through environment variables in your `compose.yml` file.

| Variable                 | Description                                                                                             | Default     |
| ------------------------ | ------------------------------------------------------------------------------------------------------- | ----------- |
| `AUDIO_FORMAT`           | Output audio format.                                                                                    | `m4a`       |
| `QUALITY`                | For `mp3`, VBR quality (`0`=best, `9`=worst).                                                           | `0`         |
| `CONCURRENCY`            | Number of downloads to run in parallel.                                                                 | `2`         |
| `WRITE_M3U`              | `1` to create `.m3u8` playlists in a `_playlists` folder.                                               | `1`         |
| `REMOVE_VIDEOS_SUFFIX`   | `1` to change `My Playlist-videos` to `My Playlist`.                                                      | `1`         |
| `PREFER_YOUTUBE_MUSIC`   | `1` to rewrite URLs to `music.youtube.com` for better metadata.                                           | `1`         |
| `RATE_LIMIT`             | Download speed limit (e.g., `1M`). **Automatically set to `500K` if no cookies are used.**                | ` `         |
| `SLEEP`                  | Delay between downloads. Fixed (`5`) or random range (`2,8`).                                           | ` `         |
| `DRY_RUN`                | `1` to simulate the process without downloading files.                                                  | `0`         |
| `COOKIES`                | Path to a `cookies.txt` file (Netscape format) for accessing private or age-gated content.              | ` `         |

## Building the Image Manually

If you prefer to build the Docker image locally instead of using a pre-built one from a registry:

1.  **Build the image**:
    ```bash
    docker compose build
    ```

2.  **Run the container**:
    ```bash
    docker compose run --rm ymde
    ```

## Setting Up a GitHub Action to Build the Image

You can automate building and publishing the Docker image to the GitHub Container Registry (ghcr.io) with a GitHub Action.

1.  **Create the workflow file**: Create a file named `.github/workflows/build-docker.yml`.
2.  **Add the workflow content**:

    ```yaml
    name: Build and Publish Docker Image

    on:
      push:
        branches:
          - main
      workflow_dispatch:

    jobs:
      build-and-push:
        runs-on: ubuntu-latest
        permissions:
          contents: read
          packages: write

        steps:
          - name: Checkout repository
            uses: actions/checkout@v3

          - name: Log in to the Container registry
            uses: docker/login-action@v2
            with:
              registry: ghcr.io
              username: ${{ github.actor }}
              password: ${{ secrets.GITHUB_TOKEN }}

          - name: Build and push Docker image
            uses: docker/build-push-action@v4
            with:
              context: .
              push: true
              tags: ghcr.io/${{ github.repository }}:latest
    ```

3.  **Run the Action**: Push to `main` or trigger it manually from the "Actions" tab in your GitHub repository. Your image will be available at `ghcr.io/YOUR_USERNAME/YOUR_REPO:latest`.

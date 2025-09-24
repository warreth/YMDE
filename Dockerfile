# ---- Builder Stage ----
FROM python:3.11-slim as builder

ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git

WORKDIR /app

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies into the virtual environment
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY ytm_takeout_downloader.py /app/ytm_takeout_downloader.py
COPY convert_csv_to_takeout_json.py /app/convert_csv_to_takeout_json.py
COPY ytm_liked_songs_exporter.py /app/ytm_liked_songs_exporter.py
COPY jellyfin_like_from_library.py /app/jellyfin_like_from_library.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh


# ---- Final Stage ----
FROM python:3.11-slim

ARG BUILD_DATE
ARG VERSION
ARG VCS_REF

LABEL org.opencontainers.image.created=$BUILD_DATE \
  org.opencontainers.image.version=$VERSION \
  org.opencontainers.image.revision=$VCS_REF \
  org.opencontainers.image.source=https://github.com/${GITHUB_REPOSITORY}

# System deps
RUN bash -euxo pipefail -c '\
  printf "Acquire::Retries \"5\";\nAcquire::ForceIPv4 \"true\";\n" > /etc/apt/apt.conf.d/99acquire; \
  apt-get update; \
  apt-get install -y --no-install-recommends ffmpeg ca-certificates; \
  rm -rf /var/lib/apt/lists/* \
  '

WORKDIR /app

# Copy virtual environment and application code from builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Set path to use the virtual environment's Python
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

VOLUME ["/data", "/library"]

ENTRYPOINT ["/app/entrypoint.sh"]

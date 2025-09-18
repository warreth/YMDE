FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
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

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code
COPY ytm_takeout_downloader.py /app/ytm_takeout_downloader.py
COPY convert_csv_to_takeout_json.py /app/convert_csv_to_takeout_json.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

VOLUME ["/data", "/library"]
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/entrypoint.sh"]

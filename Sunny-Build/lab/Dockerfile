FROM python:3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential pkg-config cmake \
        sqlite3 libsqlite3-dev \
        tesseract-ocr ocrmypdf poppler-utils \
        ffmpeg libsndfile1 espeak-ng \
        chromium \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv huggingface_hub

ENV CHROME_PATH=/usr/bin/chromium \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    HF_HUB_OFFLINE=0 \
    PYTHONDONTWRITEBYTECODE=1

ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} dev && useradd -m -u ${UID} -g ${GID} -s /bin/bash dev \
    && git config --system --add safe.directory /workspace
USER dev
WORKDIR /workspace

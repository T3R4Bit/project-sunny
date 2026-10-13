# --- Stage 1: build the PWA ---
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: runtime ---
FROM python:3.12-slim

LABEL sunny.service=true

# Install runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    libexpat1 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached unless pyproject changes), then the package itself
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN mkdir -p /app/backend/sunny && touch /app/backend/sunny/__init__.py \
    && pip install --no-cache-dir /app/backend && pip uninstall -y sunny
COPY backend/ /app/backend/
RUN pip install --no-cache-dir --no-deps /app/backend

COPY --from=frontend /fe/dist /app/frontend/dist

# Non-root user. UID 1000 matches Syncthing's default PUID so both can write the shared vault.
# Volume mount points are created here so fresh named volumes inherit dev ownership.
RUN groupadd -g 1000 dev && useradd -u 1000 -g dev -d /app -s /sbin/nologin dev \
    && mkdir -p /app/.sunny/secrets /data/sunny-vault \
    && chown -R dev:dev /app/.sunny /data/sunny-vault \
    && chmod 700 /app/.sunny/secrets
USER dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUNNY_FRONTEND_DIR=/app/frontend/dist

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "sunny.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]

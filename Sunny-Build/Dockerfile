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

# Copy backend with dependencies
COPY backend/ /app/backend/

# Install Python deps (production, no dev)
RUN pip install --no-cache-dir -e /app/backend/

# Create non-root user
RUN groupadd -r dev && useradd -r -g dev -d /app -s /sbin/nologin dev
USER dev

# Secrets and data dirs
RUN mkdir -p /app/.sunny/secrets && chmod 700 /app/.sunny/secrets

EXPOSE 8080

CMD ["uvicorn", "sunny.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]

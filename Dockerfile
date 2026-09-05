FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (matching standard host UID 1000 for volume mount write permissions)
RUN (groupadd -g 1000 appuser 2>/dev/null || groupadd appuser) && \
    (useradd -u 1000 -g appuser -d /app -s /sbin/nologin appuser 2>/dev/null || useradd -g appuser -d /app -s /sbin/nologin appuser)

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure storage, secrets, and temp download directories exist with proper permissions
RUN mkdir -p /app/storage/.tmp-downloads /app/secrets && \
    chmod -R 777 /app/storage /app/secrets && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

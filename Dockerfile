# Container image for DBresearch OCR Worker
# Includes OCR toolchain (Tesseract Thai + English) and python runtime
FROM python:3.13-slim-trixie

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-tha tesseract-ocr-eng \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Create app user. /data/blobs is created here for default blob storage.
RUN useradd --system --uid 10001 --create-home app \
 && mkdir -p /data/blobs /app /app/secrets \
 && chown -R app:app /data /app

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first (cached layer), then the project itself.
COPY --chown=app:app pyproject.toml uv.lock .python-version ./
RUN uv sync --no-install-project --all-extras
COPY --chown=app:app . .
RUN uv sync --all-extras

# Entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "dbresearch.worker"]

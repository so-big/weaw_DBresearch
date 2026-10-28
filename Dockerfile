# One image for api + worker. Includes the OCR toolchain (Tesseract Thai + English).
FROM python:3.13-slim-trixie

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-tha tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Non-root user. /data/blobs is created here so a fresh named volume inherits its ownership.
RUN useradd --system --uid 10001 --create-home app \
 && mkdir -p /data/blobs /app \
 && chown -R app:app /data /app

WORKDIR /app
USER app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first (cached layer), then the project itself.
COPY --chown=app:app pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project --all-extras
COPY --chown=app:app . .
RUN uv sync --locked --all-extras

CMD ["uvicorn", "dbresearch.main:app", "--host", "0.0.0.0", "--port", "8000"]

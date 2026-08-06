FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# CairoSVG runtime dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libffi8 \
    libgdk-pixbuf-2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxml2 \
    libxslt1.1 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /uvx /bin/

# Install deps first for better layer caching.
COPY pyproject.toml uv.lock ./
COPY python-chess ./python-chess

RUN uv sync --locked --no-dev

# Copy app code + assets.
COPY server.py ./
COPY themes ./themes
COPY LICENSE.txt README.md ./

EXPOSE 8080

CMD ["python", "server.py", "--bind", "0.0.0.0", "--port", "8080"]

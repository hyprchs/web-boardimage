FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

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

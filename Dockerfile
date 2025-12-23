FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false

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

RUN pip install --no-cache-dir poetry

# Install deps first for better layer caching.
COPY pyproject.toml poetry.lock ./
COPY python-chess ./python-chess

RUN poetry install --no-interaction --no-ansi

# Copy app code + assets.
COPY server.py ./
COPY *.json ./
COPY piece_png ./piece_png
COPY LICENSE.txt README.md ./

EXPOSE 8080

CMD ["python", "server.py", "--bind", "0.0.0.0", "--port", "8080"]


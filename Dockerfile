FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pull the uv binary from the official uv image.
# This is faster and more reproducible than running the curl install script.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Force Python stdout/stderr to be unbuffered so logs appear in `docker compose logs`
# immediately rather than being held in a buffer until the process exits.
ENV PYTHONUNBUFFERED=1

# Copy lockfile and project metadata BEFORE source code.
# Docker caches layers by file changes — if pyproject.toml and uv.lock
# haven't changed, the expensive `uv sync` step is skipped on rebuilds,
# even if your source code changed. Always copy deps before src.
COPY pyproject.toml uv.lock ./

# uv sync:
#   - Downloads Python 3.13 (Ubuntu 24.04 only ships with 3.12)
#   - Creates a .venv inside /app
#   - Installs all dependencies from uv.lock exactly (--frozen = no drift)
RUN uv sync --frozen

# Copy source after deps so src/ changes don't invalidate the dep cache layer
COPY src/ ./src/
COPY main.py ./

# Discord bot holds a persistent WebSocket connection — no HTTP server needed
CMD ["uv", "run", "python", "main.py"]

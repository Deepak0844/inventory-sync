FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# Chromium for the worker; a fixed path so the non-root user can read it.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PATH="/srv/.venv/bin:$PATH"
RUN playwright install --with-deps chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    novnc websockify x11vnc xvfb \
    && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY manual-browser-entrypoint.sh /usr/local/bin/manual-browser-entrypoint
RUN chmod 755 /usr/local/bin/manual-browser-entrypoint \
    && useradd --system --no-create-home app \
    && mkdir /srv/data \
    && chown app /srv/data
USER app
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# Chromium for the worker; a fixed path so the non-root user can read it.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PATH="/srv/.venv/bin:$PATH"
RUN playwright install --with-deps chromium
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd --system --no-create-home app
USER app
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]

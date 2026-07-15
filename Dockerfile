# --- Stage 1: build the React HUD -------------------------------------------
FROM node:22-slim AS hud-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime --------------------------------------------------
FROM python:3.11-slim AS runtime
WORKDIR /app

RUN pip install --no-cache-dir poetry==2.1.4 \
    && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-interaction --no-ansi --no-root

COPY app/ app/
COPY static/ static/
COPY scripts/ scripts/
COPY data/ data/
COPY --from=hud-build /frontend/dist/ frontend/dist/

RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

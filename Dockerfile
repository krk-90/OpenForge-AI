FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY APP/Frontend/package*.json ./
RUN npm ci
COPY APP/Frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt requirements-rag.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . ./
COPY --from=frontend-build --chown=appuser:appuser /frontend/dist ./APP/Frontend/dist

USER appuser
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '10000') + '/health', timeout=2)"]
CMD ["sh", "-c", "uvicorn APP.main:app --host 0.0.0.0 --port ${PORT:-10000}"]

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
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . ./
COPY --from=frontend-build /frontend/dist ./APP/Frontend/dist
EXPOSE 10000
CMD ["sh", "-c", "uvicorn APP.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
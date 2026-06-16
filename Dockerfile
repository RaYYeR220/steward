# Stage 1: Build the React SPA
FROM node:22-slim AS spa
WORKDIR /spa
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install
COPY dashboard/ ./
RUN npm run build

# Stage 2: Python API + SPA server
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[api]"
COPY --from=spa /spa/dist /app/dashboard/dist
ENV STEWARD_SPA_DIR=/app/dashboard/dist \
    STEWARD_API_PROVIDERS=mock \
    PYTHONUNBUFFERED=1
EXPOSE 9000
CMD ["sh", "-c", "uvicorn steward.api.app:app --host 0.0.0.0 --port ${FC_SERVER_PORT:-9000}"]

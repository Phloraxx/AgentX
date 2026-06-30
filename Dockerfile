# Multi-stage build: frontend build → production image
# Works on ARM64 (aarch64) and AMD64

# ── Stage 1: Build frontend ──
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --prefer-offline --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Production image ──
FROM python:3.11-slim AS production

WORKDIR /app

# Copy backend source
COPY backend/ ./

# Install ALL dependencies from pyproject.toml
RUN pip install --no-cache-dir .

# Copy frontend build output
COPY --from=frontend-build /app/frontend/dist /app/static

EXPOSE 8000
VOLUME /app/data

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

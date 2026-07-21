# syntax=docker/dockerfile:1.6
#
# Reco — Image multi-stage pour kit self-hostable.
# Cf. docs/adr/0037-docker-compose-deployment.md
#
# Stages :
#   1. node-builder   : Astro 5 → dist/ statique
#   2. python-builder : venv 3.12 + dépendances pipeline (tools/requirements.txt)
#   3. runtime        : slim final (venv + dist + code Python)

# -----------------------------------------------------------------------------
# Stage 1 — Astro build (Node 20)
# -----------------------------------------------------------------------------
FROM node:26-slim AS node-builder
WORKDIR /app

# Install deps en couche dédiée (cache friendly)
COPY package.json package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

# Code Astro
COPY astro.config.mjs tsconfig.json vitest.config.ts ./
COPY src ./src
COPY public ./public

ARG SITE_URL=http://localhost:4321
ENV SITE_URL=${SITE_URL}
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2 — Python venv (build-essential nécessaire pour faster-whisper/onnx)
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS python-builder
WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        git \
 && rm -rf /var/lib/apt/lists/*

COPY tools/requirements.txt ./tools/requirements.txt
COPY pyproject.toml ./

RUN python -m venv /app/.venv \
 && /app/.venv/bin/pip install --upgrade pip wheel \
 && /app/.venv/bin/pip install -r tools/requirements.txt

# -----------------------------------------------------------------------------
# Stage 3 — Runtime slim
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/tools \
    PATH=/app/.venv/bin:$PATH \
    OUTPUT_DIR=/app/tools/output

# curl utile pour debug/healthcheck manuel ; jq pratique en shell.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        jq \
 && rm -rf /var/lib/apt/lists/*

# 1) venv Python
COPY --from=python-builder /app/.venv /app/.venv

# 2) site statique builé
COPY --from=node-builder /app/dist /app/dist

# 3) Code Python + données
COPY tools ./tools
COPY src/content ./src/content
COPY pyproject.toml ./
COPY docker ./docker

RUN chmod +x docker/*.sh \
 && mkdir -p \
        tools/output/logs \
        tools/output/cache \
        tools/output/embeddings \
        tools/output/enrich_audit \
        tools/output/match_audit \
        tools/output/reports

# Healthcheck — TCP check (review_server n'expose pas /healthz).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(3); \
sys.exit(0) if s.connect_ex(('127.0.0.1',8000))==0 else sys.exit(1)" || exit 1

EXPOSE 8000 4321

ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["review"]

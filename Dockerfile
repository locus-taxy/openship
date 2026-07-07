# Backend API (FastAPI + local fastembed embedding model).
# The React UI deploys separately as a static build; this image is API-only.
# DB migrations run automatically on startup (lifespan -> run_startup_migrations),
# so the container just needs to serve the app.
FROM python:3.12-slim

# onnxruntime (used by fastembed) needs libgomp at runtime. Keep the layer lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user — the app should never run as root.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

# Cache HuggingFace/fastembed weights at a fixed path. This ENV persists into the
# running container, so the model baked in below is found at runtime (no re-download).
ENV HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install Python deps first for better layer caching (only re-runs if deps change).
COPY requirements.txt .
RUN pip install -r requirements.txt

# Hand /app (incl. the HF cache dir) to the non-root user, then switch to it so the
# baked model and all runtime files are owned/readable without root.
RUN mkdir -p "$HF_HOME" && chown -R appuser:appuser /app
USER appuser

# --- Bake the embedding model (~130MB) into the image ---
# Runs as appuser so the cache is owned by the runtime user. Downloads at build time
# so free-tier cold starts don't re-fetch it (and it works with no network at
# runtime). Keep this name in sync with config.EMBEDDING_MODEL (BAAI/bge-small-en-v1.5).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Copy the backend source last (changes most often), owned by the runtime user.
COPY --chown=appuser:appuser . .

# Hosts like Render/Fly inject $PORT; fall back to 3005 for local runs.
EXPOSE 3005
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-3005}

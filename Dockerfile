# Backend API (FastAPI + local fastembed embedding model).
# The React UI deploys separately as a static build; this image is API-only.
# DB migrations run automatically on startup (lifespan -> run_startup_migrations),
# so the container just needs to serve the app.
FROM python:3.9-slim

# onnxruntime (used by fastembed) needs libgomp at runtime. Keep the layer lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache HuggingFace/fastembed weights at a fixed path. This ENV persists into the
# running container, so the model baked in below is found at runtime (no re-download).
ENV HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install Python deps first for better layer caching (only re-runs if deps change).
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Bake the embedding model (~130MB) into the image ---
# Downloads it at build time so free-tier cold starts don't re-fetch it (and so
# it works with no network at runtime). Keep this name in sync with
# config.EMBEDDING_MODEL (default: BAAI/bge-small-en-v1.5).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Copy the backend source last (changes most often).
COPY . .

# Hosts like Render/Fly inject $PORT; fall back to 3005 for local runs.
EXPOSE 3005
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-3005}

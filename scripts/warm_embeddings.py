"""Pre-download the local embedding model so the first ingest doesn't wait on it.

fastembed fetches the model weights (~a few hundred MB) lazily on first use and
caches them on disk forever. Running this once — at setup or in a Docker build —
means no user ever pays that download cost on their first "Ingest" click.

Deliberately does NOT import `config` (which requires DATABASE_URL/JWT to be set),
so it also runs in a bare build environment with no database. It reads .env if
present to honour a custom EMBEDDING_MODEL, otherwise uses the app default.
"""

import os
import sys
from pathlib import Path

# Mirror config.EMBEDDING_MODEL's default; keep the two in sync.
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

def main() -> int:
    root = Path(__file__).resolve().parent.parent
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except Exception:
        pass  # .env is optional here

    model_name = os.getenv("EMBEDDING_MODEL") or _DEFAULT_MODEL
    print(f"Downloading / warming embedding model: {model_name}")

    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=model_name)
    # Force a real embed so the ONNX weights are fully fetched and initialised.
    dims = len(next(iter(model.embed(["warmup"]))))
    print(f"Embedding model ready ({dims} dims). Cached for all future ingests.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
.venv/bin/python3 - <<'EOF'
import time, os, psycopg2
url = os.environ["DATABASE_URL"]
for _ in range(30):
    try:
        conn = psycopg2.connect(url)
        conn.close()
        print("PostgreSQL is ready.")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("Database not ready after 60s")
EOF

echo "Running migrations..."
.venv/bin/alembic upgrade head

echo "Starting server..."
exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port 3005

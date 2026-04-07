"""Apply Alembic migrations programmatically (e.g. on FastAPI startup)."""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine.url import make_url

from config import DATABASE_URL, RUN_MIGRATIONS_ON_STARTUP

logger = logging.getLogger("openship.migrations")

def run_startup_migrations() -> None:
    if not RUN_MIGRATIONS_ON_STARTUP:
        msg = "Skipping Alembic (RUN_MIGRATIONS_ON_STARTUP is false)"
        logger.info("openship: %s", msg)
        print(f"openship: {msg}", flush=True)
        return

    root = Path(__file__).resolve().parent
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        raise RuntimeError(f"alembic.ini not found at {ini_path}")

    try:
        url = make_url(DATABASE_URL)
        logger.info(
            "openship: Alembic upgrade head → host=%s port=%s database=%s user=%s",
            url.host,
            url.port,
            url.database,
            url.username,
        )
    except Exception:
        logger.info("openship: Alembic upgrade head (could not parse DATABASE_URL for log)")

    print("openship: running Alembic upgrade head...", flush=True)
    cfg = Config(str(ini_path))
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
        logger.exception("openship: Alembic upgrade failed: %s", exc)
        print("openship: Alembic upgrade FAILED — see log above.", flush=True)
        if "permission denied for schema public" in str(exc).lower():
            print(
                "openship: hint — PostgreSQL 15+ often requires GRANT on schema public for your DB user. "
                "See docs/postgres-public-schema.md",
                flush=True,
            )
        raise
    logger.info("openship: Alembic upgrade head completed successfully")
    print("openship: Alembic upgrade finished.", flush=True)

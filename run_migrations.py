"""Apply Alembic migrations programmatically (e.g. on FastAPI startup)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from config import RUN_MIGRATIONS_ON_STARTUP

def run_startup_migrations() -> None:
    if not RUN_MIGRATIONS_ON_STARTUP:
        return

    root = Path(__file__).resolve().parent
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        raise RuntimeError(f"alembic.ini not found at {ini_path}")

    cfg = Config(str(ini_path))
    command.upgrade(cfg, "head")

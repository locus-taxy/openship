import sys
import os
import time
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel
from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import DATABASE_URL
import models  # noqa: F401 — registers all SQLModel tables in metadata for autogenerate

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Session-level advisory lock so only one process runs Alembic at a time (multi-worker / multi-instance).
# Same connection must hold the lock while migrations run.
_ADVISORY_LOCK_KEY_1 = 72655931
_ADVISORY_LOCK_KEY_2 = 184291
_MIGRATION_LOCK_MAX_WAIT_S = 120.0
_MIGRATION_LOCK_BACKOFF_INITIAL_S = 0.1
_MIGRATION_LOCK_BACKOFF_MAX_S = 2.0

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_pg = connection.dialect.name == "postgresql"
        lock_acquired = False
        if is_pg:
            deadline = time.monotonic() + _MIGRATION_LOCK_MAX_WAIT_S
            backoff = _MIGRATION_LOCK_BACKOFF_INITIAL_S
            while time.monotonic() < deadline:
                got = connection.execute(
                    text("SELECT pg_try_advisory_lock(:k1, :k2)"),
                    {"k1": _ADVISORY_LOCK_KEY_1, "k2": _ADVISORY_LOCK_KEY_2},
                ).scalar()
                if got:
                    lock_acquired = True
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(backoff, remaining))
                backoff = min(backoff * 1.5, _MIGRATION_LOCK_BACKOFF_MAX_S)
            if not lock_acquired:
                raise RuntimeError(
                    f"Could not acquire PostgreSQL migration advisory lock within "
                    f"{_MIGRATION_LOCK_MAX_WAIT_S:.0f}s (another process may be running migrations). "
                    "Retry startup; migrations are idempotent once complete."
                )
            # The advisory lock SELECT opens an implicit transaction in SQLAlchemy 2.x.
            # Commit it now so alembic's own begin_transaction() gets a clean connection
            # and its commit actually persists the migration + version update.
            connection.commit()
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            if is_pg and lock_acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:k1, :k2)"),
                    {"k1": _ADVISORY_LOCK_KEY_1, "k2": _ADVISORY_LOCK_KEY_2},
                )
                connection.commit()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

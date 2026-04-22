"""encrypt_legacy_api_keys

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2026-04-22 10:00:00.000000

Backfill-encrypts any user_api_keys rows whose api_key is still plaintext
(i.e. not prefixed with "FULL:"). Keys migrated by e3f4g5h6i7j8 from the
old per-provider columns were inserted as plaintext because they predate the
encryption layer; this migration encrypts them at rest.

Safety:
- Checks LLM_ENCRYPTION_KEY before starting; aborts cleanly if missing.
- Skips rows that are already encrypted (idempotent).
- Processes rows in batches of 500 to bound transaction size.
- Never logs or prints key material.
- downgrade() is a no-op: decryption on read still works via decrypt_api_key().
"""

import os
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

try:
    from cryptography.fernet import Fernet
except ImportError as exc:
    raise RuntimeError(
        "cryptography package is required for this migration. "
        "Install it with: pip install cryptography"
    ) from exc

revision: str = "h6i7j8k9l0m1"
down_revision: Union[str, Sequence[str], None] = "g5h6i7j8k9l0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FULL_PREFIX = "FULL:"
_BATCH_SIZE = 500

def _get_fernet() -> Fernet:
    raw = os.environ.get("LLM_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise RuntimeError(
            "LLM_ENCRYPTION_KEY is not set. "
            "Set it before running this migration.\n"
            'Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(raw.encode())

def upgrade() -> None:
    fernet = _get_fernet()
    conn = op.get_bind()

    offset = 0
    while True:
        rows = conn.execute(
            text(
                "SELECT id, api_key FROM user_api_keys "
                "WHERE api_key NOT LIKE 'FULL:%' "
                "ORDER BY id "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": _BATCH_SIZE, "offset": offset},
        ).fetchall()

        if not rows:
            break

        for row_id, plaintext in rows:
            encrypted = _FULL_PREFIX + fernet.encrypt(plaintext.encode()).decode()
            conn.execute(
                text("UPDATE user_api_keys SET api_key = :encrypted WHERE id = :id"),
                {"encrypted": encrypted, "id": row_id},
            )

        offset += len(rows)
        if len(rows) < _BATCH_SIZE:
            break

def downgrade() -> None:
    # Intentional no-op: decrypt_api_key() already handles the FULL: prefix,
    # so rolling back the schema does not require decrypting stored values.
    pass

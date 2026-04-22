"""encrypt_legacy_api_keys

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2026-04-22 10:00:00.000000

Backfill-encrypts any user_api_keys rows whose api_key is still plaintext.
Keys migrated by e3f4g5h6i7j8 predate the encryption layer and were
inserted as plaintext; this migration brings them to the current
partial-encryption format (prefix||ENC||<fernet_token_of_last_5_chars>).

Safety:
- Checks LLM_ENCRYPTION_KEY before starting; aborts cleanly if missing.
- Skips rows already in partial-encryption format (idempotent — checks for
  the ||ENC|| separator).
- Cursor-based pagination (id > :last_id) avoids OFFSET skipping caused
  by updated rows dropping out of the WHERE filter mid-loop.
- Processes rows in batches of 500 to bound transaction size.
- Never logs or prints key material.
- downgrade() is a no-op: decrypt_api_key() handles both formats.
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

_SEPARATOR = "||ENC||"
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

def _partial_encrypt(plaintext: str, fernet: Fernet) -> str:
    """Encrypt the last 5 chars; store as 'prefix||ENC||<token>'."""
    if len(plaintext) <= 5:
        prefix, suffix = "", plaintext
    else:
        prefix, suffix = plaintext[:-5], plaintext[-5:]
    return prefix + _SEPARATOR + fernet.encrypt(suffix.encode()).decode()

def upgrade() -> None:
    fernet = _get_fernet()
    conn = op.get_bind()

    # Only target rows that have no ||ENC|| separator yet (plaintext).
    # Cursor-based pagination so UPDATEs don't cause rows to be skipped.
    last_id = 0
    while True:
        rows = conn.execute(
            text(
                "SELECT id, api_key FROM user_api_keys "
                "WHERE api_key NOT LIKE '%||ENC||%' AND id > :last_id "
                "ORDER BY id "
                "LIMIT :limit"
            ),
            {"last_id": last_id, "limit": _BATCH_SIZE},
        ).fetchall()

        if not rows:
            break

        for row_id, plaintext in rows:
            encrypted = _partial_encrypt(plaintext, fernet)
            conn.execute(
                text("UPDATE user_api_keys SET api_key = :encrypted WHERE id = :id"),
                {"encrypted": encrypted, "id": row_id},
            )

        last_id = rows[-1][0]

def downgrade() -> None:
    # Intentional no-op: decrypt_api_key() in services/encryption.py handles
    # both the ||ENC|| format and plaintext, so rolling back the schema does
    # not require decrypting stored values.
    pass

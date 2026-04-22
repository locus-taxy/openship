"""encrypt_legacy_api_keys

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2026-04-22 10:00:00.000000

Backfill-encrypts any user_api_keys rows whose api_key is still plaintext
or in the legacy "prefix||ENC||<token>" partial-encryption format.
Keys migrated by e3f4g5h6i7j8 predate the encryption layer and were
inserted as plaintext; this migration brings them to the current FULL: format.

Safety:
- Checks LLM_ENCRYPTION_KEY before starting; aborts cleanly if missing.
- Skips rows that are already encrypted (idempotent — FULL: prefix check).
- Cursor-based pagination (id > :last_id) avoids OFFSET skipping caused
  by updated rows dropping out of the WHERE filter mid-loop.
- Legacy "prefix||ENC||<token>" rows are decrypted first, then re-encrypted
  as FULL: — they are never double-encrypted.
- Processes rows in batches of 500 to bound transaction size.
- Never logs or prints key material.
- downgrade() is a no-op: decrypt_api_key() handles all three formats.
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
_LEGACY_SEPARATOR = "||ENC||"
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

def _to_plaintext(stored: str, fernet: Fernet) -> str:
    """
    Return the raw API key regardless of storage format.

    - "FULL:<token>"         — already encrypted, should not reach here (filtered by WHERE)
    - "prefix||ENC||<token>" — legacy partial encryption; decrypt suffix to reconstruct plaintext
    - anything else          — already plaintext; return as-is
    """
    if _LEGACY_SEPARATOR in stored:
        prefix, enc_suffix = stored.rsplit(_LEGACY_SEPARATOR, 1)
        suffix = fernet.decrypt(enc_suffix.encode()).decode()
        return prefix + suffix
    return stored

def upgrade() -> None:
    fernet = _get_fernet()
    conn = op.get_bind()

    # Cursor-based pagination: track the highest id processed so far.
    # This is correct even after UPDATEs remove rows from the WHERE filter —
    # OFFSET pagination would skip rows as the filtered set shrinks.
    last_id = 0
    while True:
        rows = conn.execute(
            text(
                "SELECT id, api_key FROM user_api_keys "
                "WHERE api_key NOT LIKE 'FULL:%' AND id > :last_id "
                "ORDER BY id "
                "LIMIT :limit"
            ),
            {"last_id": last_id, "limit": _BATCH_SIZE},
        ).fetchall()

        if not rows:
            break

        for row_id, stored in rows:
            plaintext = _to_plaintext(stored, fernet)
            encrypted = _FULL_PREFIX + fernet.encrypt(plaintext.encode()).decode()
            conn.execute(
                text("UPDATE user_api_keys SET api_key = :encrypted WHERE id = :id"),
                {"encrypted": encrypted, "id": row_id},
            )

        last_id = rows[-1][0]

def downgrade() -> None:
    # Intentional no-op: decrypt_api_key() in services/encryption.py already
    # handles FULL:, ||ENC||, and plaintext formats, so rolling back the schema
    # does not require decrypting stored values.
    pass

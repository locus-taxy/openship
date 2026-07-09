"""link users to their company (users.company_id) + backfill from email

Company is resolved from email at signup (domain for corporate, full email for
personal/generic). This adds the explicit FK and backfills existing users, so the
company can be shown (read-only) in account settings and used for future membership
features. Isolation still keyed by companies.domain.

Revision ID: onb_user_company
Revises: onb_page_meta
Create Date: 2026-07-06
"""

import sqlalchemy as sa
from alembic import op

revision = "onb_user_company"
down_revision = "onb_page_meta"
branch_labels = None
depends_on = None

# Kept in sync with services.company._GENERIC_EMAIL_DOMAINS (inlined so the migration
# is self-contained and won't drift if app code changes later).
_GENERIC = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "ymail.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "zoho.com",
    "mail.com",
    "yandex.com",
    "pm.me",
}

def _key_and_name(email):
    domain = email.rsplit("@", 1)[-1].strip().lower()
    if domain in _GENERIC:
        key = email.strip().lower()
        return key, key.split("@", 1)[0]
    return domain, domain

def upgrade():
    op.add_column("users", sa.Column("company_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_company_id", "users", ["company_id"])
    op.create_foreign_key("fk_users_company_id", "users", "companies", ["company_id"], ["id"])

    # Backfill: resolve/create each existing user's company and link it.
    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, email FROM users WHERE email IS NOT NULL")).fetchall()
    cache = {}  # key -> company id
    for uid, email in users:
        if not email:
            continue
        key, name = _key_and_name(email)
        cid = cache.get(key)
        if cid is None:
            row = bind.execute(
                sa.text("SELECT id FROM companies WHERE domain = :d"), {"d": key}
            ).fetchone()
            if row:
                cid = row[0]
            else:
                cid = bind.execute(
                    sa.text("INSERT INTO companies (name, domain) VALUES (:n, :d) RETURNING id"),
                    {"n": name, "d": key},
                ).fetchone()[0]
            cache[key] = cid
        bind.execute(
            sa.text("UPDATE users SET company_id = :c WHERE id = :u"), {"c": cid, "u": uid}
        )

def downgrade():
    op.drop_constraint("fk_users_company_id", "users", type_="foreignkey")
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_column("users", "company_id")

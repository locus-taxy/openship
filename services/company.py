"""Company resolution — maps a user to their company (org).

A company is keyed by the user's email: the DOMAIN for a corporate address (teammates
share one org) or the FULL email for a personal/generic address (a private one-person
org, so unrelated personal users are never pooled together). Lives here (not in the
Confluence module) so signup/auth can resolve a company without pulling in the whole
Atlassian client. `onboarding.services.confluence` re-exports these for back-compat.
"""

from typing import Optional, Tuple

from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

from database import engine
from onboarding.models.company import Company

# Free/public email providers. Users on these are NOT pooled by domain (two strangers
# @gmail.com aren't one org) — each becomes a private one-person org keyed by full email.
_GENERIC_EMAIL_DOMAINS = frozenset(
    {
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
)

def _domain_from_email(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()

def _company_key_and_name(email: str) -> Tuple[str, str]:
    """(isolation_key, display_name) for an email. Corporate domain → shared org keyed
    by domain. Personal/generic → private org keyed by the FULL email (the local part
    alone collides — john@gmail vs john@yahoo), with the local part as display name."""
    domain = _domain_from_email(email)
    if domain in _GENERIC_EMAIL_DOMAINS:
        key = email.strip().lower()
        return key, key.split("@", 1)[0]
    return domain, domain

def get_or_create_company(email: str) -> Company:
    """Fetch (or create) the company for an email, keyed as above."""
    key, name = _company_key_and_name(email)
    with Session(engine) as session:
        company = session.exec(select(Company).where(Company.domain == key)).first()
        if company:
            return company
        company = Company(name=name, domain=key)
        session.add(company)
        try:
            session.commit()
        except IntegrityError:  # concurrent create — fetch the winner
            session.rollback()
            return session.exec(select(Company).where(Company.domain == key)).first()
        session.refresh(company)
        return company

def get_or_create_company_for_user(user) -> Company:
    """Map a user (anything with `.email`) to their company, creating it if needed."""
    return get_or_create_company(user.email)

def get_company_by_id(company_id: int) -> Optional[Company]:
    with Session(engine) as session:
        return session.get(Company, company_id)

def company_display_name(user) -> Optional[str]:
    """The company name to show a user. Prefers the stored FK (users.company_id); falls
    back to deriving from the email for legacy users whose FK isn't backfilled yet.
    Pure display — never writes."""
    company_id = getattr(user, "company_id", None)
    if company_id:
        company = get_company_by_id(company_id)
        if company:
            return company.name
    return _company_key_and_name(user.email)[1] if getattr(user, "email", None) else None

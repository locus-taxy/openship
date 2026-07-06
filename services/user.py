from typing import Optional, Tuple
from sqlmodel import Session, select
from database import engine
from models.user import User
from models.user_api_key import UserApiKey
from models.llm_provider import LlmProvider
from services.password import hash_password
from services.encryption import encrypt_api_key, decrypt_api_key
from services.company import get_or_create_company

def get_user_by_id(user_id: int) -> Optional[User]:
    with Session(engine) as session:
        return session.get(User, user_id)

def get_user_by_email(email: str) -> Optional[User]:
    with Session(engine) as session:
        statement = select(User).where(User.email == email)
        return session.exec(statement).first()

def get_provider_by_name(name: str) -> Optional[LlmProvider]:
    """Return the LlmProvider row for the given internal name, e.g. 'gemini'."""
    with Session(engine) as session:
        return session.exec(select(LlmProvider).where(LlmProvider.name == name)).first()

def get_provider_by_id(provider_id: int) -> Optional[LlmProvider]:
    """Return the LlmProvider row for the given integer ID."""
    with Session(engine) as session:
        return session.get(LlmProvider, provider_id)

def get_provider_key(user_id: int, provider_id: int) -> Optional[str]:
    """Return the decrypted API key for a user+provider pair, or None."""
    with Session(engine) as session:
        record = session.exec(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.llm_provider_id == provider_id,
            )
        ).first()
        if not record:
            return None
        raw = record.api_key  # capture before session closes
    return decrypt_api_key(raw)

def get_provider_model(user_id: int, provider_id: int) -> Optional[str]:
    """Return the saved model for a user+provider pair, or None."""
    with Session(engine) as session:
        record = session.exec(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.llm_provider_id == provider_id,
            )
        ).first()
        return record.llm_model if record else None

def get_all_saved_provider_ids(user_id: int) -> set:
    """Return the set of llm_provider_id values that have a key saved for this user."""
    with Session(engine) as session:
        records = session.exec(select(UserApiKey).where(UserApiKey.user_id == user_id)).all()
        return {r.llm_provider_id for r in records}

def update_llm_settings(
    user_id: int,
    provider_id: Optional[int],
    api_key: Optional[str],
    model: Optional[str] = None,
) -> None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return

        # Upsert / delete the API key row for this provider
        if provider_id is not None and api_key is not None:
            record = session.exec(
                select(UserApiKey).where(
                    UserApiKey.user_id == user_id,
                    UserApiKey.llm_provider_id == provider_id,
                )
            ).first()

            if api_key == "":
                # Empty string = user clicked Delete — remove the row
                if record:
                    session.delete(record)
                # If this was the active provider, clear it — user has no key for it anymore
                if user.llm_provider_id == provider_id:
                    user.llm_provider_id = None
                session.add(user)
            else:
                # Saving a key — set this as the active provider
                user.llm_provider_id = provider_id
                session.add(user)
                if record:
                    record.api_key = encrypt_api_key(api_key)
                    if model is not None:
                        record.llm_model = model
                    session.add(record)
                else:
                    session.add(
                        UserApiKey(
                            user_id=user_id,
                            llm_provider_id=provider_id,
                            llm_model=model,
                            api_key=encrypt_api_key(api_key),
                        )
                    )

        elif provider_id is not None:
            # No key change — switching active provider or updating model only
            user.llm_provider_id = provider_id
            session.add(user)
            if model is not None:
                record = session.exec(
                    select(UserApiKey).where(
                        UserApiKey.user_id == user_id,
                        UserApiKey.llm_provider_id == provider_id,
                    )
                ).first()
                if record:
                    record.llm_model = model
                    session.add(record)

        session.commit()

def get_provider_pricing(user_id: int, provider_id: int) -> Tuple[Optional[float], Optional[float]]:
    """Return (input_per_1m_usd, output_per_1m_usd) for a user+provider pair."""
    with Session(engine) as session:
        record = session.exec(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.llm_provider_id == provider_id,
            )
        ).first()
        if not record:
            return None, None
        return record.input_per_1m_usd, record.output_per_1m_usd

def update_llm_pricing(
    user_id: int,
    provider_id: int,
    input_per_1m_usd: Optional[float],
    output_per_1m_usd: Optional[float],
) -> None:
    """Save pricing fields on the existing user_api_keys row for a user+provider pair."""
    with Session(engine) as session:
        record = session.exec(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.llm_provider_id == provider_id,
            )
        ).first()
        if not record:
            return
        record.input_per_1m_usd = input_per_1m_usd
        record.output_per_1m_usd = output_per_1m_usd
        session.add(record)
        session.commit()

def update_currency_settings(
    user_id: int,
    display_currency: str,
    currency_exchange_rate: float,
) -> None:
    """Save display currency and exchange rate on the users row."""
    if currency_exchange_rate <= 0:
        raise ValueError("currency_exchange_rate must be positive")
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return
        user.display_currency = display_currency.upper()[:8]
        user.currency_exchange_rate = currency_exchange_rate
        session.add(user)
        session.commit()

def get_currency_settings(user_id: int) -> Tuple[str, float]:
    """Return (display_currency, exchange_rate); defaults to ('USD', 1.0)."""
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            return "USD", 1.0
        return (user.display_currency or "USD"), (user.currency_exchange_rate or 1.0)

def compute_generation_cost_usd(
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    input_price_per_m: Optional[float],
    output_price_per_m: Optional[float],
) -> Optional[float]:
    """Compute USD cost from token counts and per-million prices. Returns None if any value missing."""
    if None in (input_tokens, output_tokens, input_price_per_m, output_price_per_m):
        return None
    if any(v < 0 for v in (input_tokens, output_tokens, input_price_per_m, output_price_per_m)):
        return None
    return (input_tokens * input_price_per_m + output_tokens * output_price_per_m) / 1_000_000

def create_user(email: str, name: str, password: str) -> User:
    # Resolve the user's company from their email at signup and link it (read-only).
    company = get_or_create_company(email)
    with Session(engine) as session:
        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(password),
            company_id=company.id,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

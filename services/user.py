from typing import Optional
from sqlmodel import Session, select
from database import engine
from models.user import User
from models.user_api_key import UserApiKey
from models.llm_provider import LlmProvider
from services.password import hash_password
from services.encryption import encrypt_api_key, decrypt_api_key

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

def create_user(email: str, name: str, password: str) -> User:
    with Session(engine) as session:
        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

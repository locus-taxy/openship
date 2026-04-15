from typing import Optional
from sqlmodel import Session, select
from database import engine
from models.user import User
from services.password import hash_password

def get_user_by_id(user_id: int) -> Optional[User]:
    with Session(engine) as session:
        return session.get(User, user_id)

def get_user_by_email(email: str) -> Optional[User]:
    with Session(engine) as session:
        statement = select(User).where(User.email == email)
        return session.exec(statement).first()

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

def update_gemini_api_key(user_id: int, api_key: Optional[str]) -> None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user:
            user.gemini_api_key = api_key
            session.add(user)
            session.commit()

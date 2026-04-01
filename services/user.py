from typing import Optional
from sqlmodel import Session, select

from database import engine
from models.user import User
from services.password import hash_password


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

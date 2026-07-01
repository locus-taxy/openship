from sqlmodel import SQLModel, Session, create_engine
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Import all models here so SQLModel.metadata is fully populated before
# Alembic or any table-creation call runs.
from models.llm_provider import LlmProvider  # noqa: F401, E402
from models.user import User  # noqa: F401, E402
from models.user_api_key import UserApiKey  # noqa: F401, E402
from models.week_remediation_topic import WeekRemediationTopic  # noqa: F401, E402

def get_session():
    with Session(engine) as session:
        yield session

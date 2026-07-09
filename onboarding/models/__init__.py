"""Onboarding / RAG models. Importing this package registers all tables in
SQLModel metadata (used by app startup and alembic autogenerate)."""

from onboarding.models.company import Company
from onboarding.models.confluence_connection import ConfluenceConnection
from onboarding.models.document_page import DocumentPage
from onboarding.models.document_chunk import DocumentChunk
from onboarding.models.ingestion_job import IngestionJob
from onboarding.models.onboarding_plan import OnboardingPlan
from onboarding.models.onboarding_day import OnboardingDay
from onboarding.models.onboarding_quiz_attempt import OnboardingQuizAttempt
from onboarding.models.knowledge_chat import KnowledgeChat
from onboarding.models.knowledge_message import KnowledgeMessage

__all__ = [
    "Company",
    "ConfluenceConnection",
    "DocumentPage",
    "DocumentChunk",
    "IngestionJob",
    "OnboardingPlan",
    "OnboardingDay",
    "OnboardingQuizAttempt",
    "KnowledgeChat",
    "KnowledgeMessage",
]

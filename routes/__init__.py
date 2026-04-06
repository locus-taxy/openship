from fastapi import FastAPI

from routes.subscription import router as subscription_router
from routes.syllabus import router as syllabus_router
from routes.content import router as content_router
from routes.newsletter import router as newsletter_router


def register_routers(app: FastAPI):
    app.include_router(subscription_router)
    app.include_router(syllabus_router)
    app.include_router(content_router)
    app.include_router(newsletter_router)

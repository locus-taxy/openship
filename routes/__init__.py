from fastapi import FastAPI
from routes.auth import router as auth_router
from routes.subscription import router as subscription_router
from routes.syllabus import router as syllabus_router
from routes.content import router as content_router
from routes.newsletter import router as newsletter_router
from routes.quiz import router as quiz_router
from routes.onboarding import router as onboarding_router
from routes.confluence import router as confluence_router

def register_routers(app: FastAPI):
    app.include_router(auth_router)
    app.include_router(subscription_router)
    app.include_router(syllabus_router)
    app.include_router(content_router)
    app.include_router(newsletter_router)
    app.include_router(quiz_router)
    app.include_router(onboarding_router)
    app.include_router(confluence_router)

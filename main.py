import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from limiter import limiter
from run_migrations import run_startup_migrations
from routes import register_routers

logger = logging.getLogger("openship")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("openship: application startup — running migrations if enabled")
    run_startup_migrations()
    logger.info("openship: application startup — serving API")
    yield

app = FastAPI(
    title="Openship Automation API",
    version="2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    # Vite may use 5174+ if the default port is busy; include common dev origins.
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routers(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3005, reload=True)

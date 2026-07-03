import logging
import logging.config
from contextlib import asynccontextmanager

# Attach an explicit handler to app loggers so they are not affected by
# uvicorn's reload subprocess reconfiguring root.  propagate stays True so
# pytest's caplog (which hooks into root) still captures records in tests.
_app_handler = logging.StreamHandler()
_app_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
for _logger_name in ("openship", "services", "controllers"):
    _lg = logging.getLogger(_logger_name)
    _lg.setLevel(logging.INFO)
    if not _lg.handlers:
        _lg.addHandler(_app_handler)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from middleware.auth import AuthMiddleware
from config import limiter
from run_migrations import run_startup_migrations
from routes import register_routers

logger = logging.getLogger("openship")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("openship: application startup — running migrations if enabled")
    run_startup_migrations()
    # Background ingest/reconcile jobs run in-process; a restart orphans any that
    # were mid-run as 'running' forever. Reap them so the feature isn't wedged.
    try:
        from onboarding.services.confluence import reap_running_jobs

        reaped = reap_running_jobs()
        if reaped:
            logger.info("openship: reaped %d interrupted ingestion job(s)", reaped)
    except Exception:
        logger.exception("openship: failed to reap interrupted ingestion jobs")
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

app.add_middleware(AuthMiddleware)

register_routers(app)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3005, reload=True)

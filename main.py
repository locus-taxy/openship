from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from run_migrations import run_startup_migrations
from routes import register_routers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_startup_migrations()
    yield


app = FastAPI(
    title="Openship Automation API",
    version="2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routers(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3005, reload=True)

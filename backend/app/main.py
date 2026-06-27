from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import sessions, tools, summaries
from app.db.database import engine, init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Health Assistant Control Plane", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(summaries.router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Health Assistant Backend is running"}


@app.get("/health")
async def health_liveness():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_readiness():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready"}

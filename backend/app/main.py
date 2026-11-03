"""AURORA Backend — Application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.db.session import init_db
from app.core.config import settings

app = FastAPI(
    title="AURORA Campus Intelligence API",
    description=(
        "AURORA is an independent educational prototype. "
        "Not affiliated with, endorsed by, or operated by Stony Brook University or IBM."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()


app.include_router(api_router, prefix="/api/v1")

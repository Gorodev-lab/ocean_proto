"""
ocean_proto / src / api / main.py
=================================
FastAPI application entry point.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

from .routes import router
from .megafauna_routes import router as megafauna_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hook."""
    os.makedirs("data", exist_ok=True)
    os.makedirs("src/static", exist_ok=True)
    yield
    # Cleanup si se agrega estado en el futuro


app = FastAPI(
    title="Ocean Proto — Maritime Intelligence API",
    description=(
        "Plataforma de inteligencia marítima para proteger la megafauna "
        "en Baja California Sur. Vigila cruceros, flotas pesqueras y dark events."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(megafauna_router)

app.mount("/static", StaticFiles(directory="src/static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    return FileResponse("src/static/index.html")


@app.get("/health", tags=["Meta"])
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0"}

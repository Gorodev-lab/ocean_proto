from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .routes import router
import os

app = FastAPI(
    title="Megafauna-Vessel Collision Risk API",
    description="API para analizar el riesgo de colisión entre grandes embarcaciones y megafauna.",
    version="1.0.0"
)

app.include_router(router)

# Mount static files to serve frontend
os.makedirs("src/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="src/static"), name="static")

@app.get("/")
def serve_index():
    return FileResponse("src/static/index.html")

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Risk Analyzer API is running."}

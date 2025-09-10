from fastapi import FastAPI
import logging

from logging_config import setup_logging
from services.vector_db import initialize_pinecone
from api.endpoints.matching import router as matching_router
from api.endpoints.monitoring import router as monitoring_router

setup_logging()

app = FastAPI(
    title="Moteur de Matching Sémantique",
    description="API pour l'analyse sémantique et le matching de profils de candidats.",
    version="1.0.0"
)

logger = logging.getLogger(__name__)

@app.on_event("startup")
def startup_event():
    logger.info("Démarrage de l'application et initialisation des connexions...")
    initialize_pinecone()

app.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
app.include_router(matching_router, tags=["Matching & Candidates"])

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Bienvenue sur l'API du Moteur de Matching Sémantique"}

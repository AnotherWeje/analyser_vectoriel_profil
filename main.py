"""
Point d'entrée de l'application FastAPI pour le moteur de matching sémantique.

Cette API expose des endpoints pour :
- Soumettre des profils de candidats (traitement asynchrone)
- Rechercher des correspondances entre offres d'emploi et candidats
- Monitoring et administration de la base vectorielle

Architecture :
- Démarrage avec initialisation de Pinecone
- Intégration des routers pour les différents endpoints
- Configuration du logging centralisé
"""

from fastapi import FastAPI  # Framework web asynchrone pour l'API REST
import logging  # Configuration du système de logging

from logging_config import setup_logging  # Configuration centralisée du logging
from services.vector_db import initialize_pinecone  # Initialisation de la connexion Pinecone
from api.endpoints.matching import router as matching_router  # Endpoints de matching et candidats
from api.endpoints.monitoring import router as monitoring_router  # Endpoints de monitoring

setup_logging()

app = FastAPI(
    title="Moteur de Matching Sémantique",
    description="API pour l'analyse sémantique et le matching de profils de candidats.",
    version="1.0.0"
)

logger = logging.getLogger(__name__)

@app.on_event("startup")
def startup_event():
    """
    Événement de démarrage de l'application.

    Initialise les connexions aux services externes (Pinecone)
    avant que l'API ne commence à accepter les requêtes.
    """
    logger.info("Démarrage de l'application et initialisation des connexions...")
    initialize_pinecone()

app.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
app.include_router(matching_router, tags=["Matching & Candidates"])

@app.get("/", tags=["Root"])
def read_root():
    """
    Endpoint racine de l'API.

    Retourne un message de bienvenue et confirme que l'API est opérationnelle.
    """
    return {"message": "Bienvenue sur l'API du Moteur de Matching Sémantique"}

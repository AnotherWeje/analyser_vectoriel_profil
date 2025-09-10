import os
import logging
import redis
from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult

from services.vector_db import pc, index_name

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Connexion Redis pour le Health Check ---
try:
    redis_url = os.getenv('CELERY_BROKER_URL')
    redis_client = redis.from_url(redis_url, socket_connect_timeout=2, decode_responses=True)
    logger.info("Connexion Redis pour le Health Check initialisée.")
except Exception as e:
    logger.error(f"Impossible de configurer le client Redis pour le Health Check: {e}")
    redis_client = None

@router.get("/health", tags=["Monitoring"], status_code=status.HTTP_200_OK)
def health_check():
    services_status = {"pinecone": "error", "redis": "error"}
    is_healthy = True
    try:
        pc.describe_index(str(index_name))
        services_status["pinecone"] = "ok"
    except Exception as e:
        is_healthy = False
        logger.warning(f"Health check a échoué pour Pinecone: {e}")
    if redis_client:
        try:
            if redis_client.ping():
                services_status["redis"] = "ok"
            else:
                is_healthy = False
        except Exception as e:
            is_healthy = False
            logger.warning(f"Health check a échoué pour Redis: {e}")
    else:
        is_healthy = False
    response_body = {"status": "healthy" if is_healthy else "unhealthy", "services": services_status}
    if not is_healthy:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=response_body)
    return response_body

@router.get("/vectordb/info", tags=["Monitoring"])
def get_vectordb_info():
    try:
        index = pc.Index(str(index_name))
        stats = index.describe_index_stats()
        return {
            "num_vectors": stats.total_vector_count,
            "dimension": stats.dimension,
            "namespaces": {name: {"vector_count": ns_stats.vector_count} for name, ns_stats in stats.namespaces.items()}
        }
    except Exception as e:
        logger.error("Erreur lors de la récupération des informations de l'index Pinecone.", exc_info=True)
        return {"error": str(e)}

@router.get("/tasks/{task_id}", tags=["Monitoring"])
def get_task_status(task_id: str):
    task = AsyncResult(task_id)
    return {"task_id": task.id, "status": task.status, "result": task.result if task.ready() else None}
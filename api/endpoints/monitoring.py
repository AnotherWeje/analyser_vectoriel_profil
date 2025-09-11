import os
import logging
import ssl
import redis
from urllib.parse import urlparse, parse_qs, urlunparse
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult

from services.vector_db import pc, index_name

logger = logging.getLogger(__name__)

# Charger les variables d'environnement depuis .env en local (utile hors Docker Compose)
load_dotenv()
router = APIRouter()

def configure_redis_url(redis_url: str) -> str:
    """Normalise l'URL Redis. Pour rediss://, on NE modifie PAS ssl_cert_reqs dans l'URL
    (redis-py n'accepte pas la valeur symbolique 'CERT_NONE' en tant que chaîne)."""
    if not redis_url:
        return redis_url
    if not redis_url.startswith('rediss://'):
        return redis_url
    # Retirer ssl_cert_reqs éventuel dans l'URL pour éviter l'erreur redis-py
    parsed = urlparse(redis_url)
    query_params = parse_qs(parsed.query)
    if 'ssl_cert_reqs' in query_params:
        query_params.pop('ssl_cert_reqs', None)
        # Reconstruire l'URL sans ce paramètre
        new_query = '&'.join(
            f"{k}={v[0]}" if len(v) == 1 else '&'.join(f"{k}={item}" for item in v)
            for k, v in query_params.items()
        )
        redis_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    return redis_url

# --- Connexion Redis pour le Health Check ---
try:
    # S'aligner sur le worker: on lit exclusivement REDIS_URL
    raw_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_url = configure_redis_url(raw_url)
    # Utiliser la gestion TLS automatique de redis-py pour rediss://
    redis_client = redis.from_url(
        redis_url,
        socket_connect_timeout=2,
        decode_responses=True,
    )
    # Log non sensible: schéma et hôte masqué
    parsed = urlparse(redis_url)
    logger.info(f"HealthCheck Redis: scheme={parsed.scheme}, host={parsed.hostname}, port={parsed.port}")
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
import os
import logging
import ssl
import redis
from urllib.parse import urlparse, parse_qs, urlunparse
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult
from pydantic import BaseModel

from services.vector_db import pc, index_name, fetch_metadata, update_metadata

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

# --- Admin: Normaliser les technologies stockées en métadonnées ---
class NormalizeRequest(BaseModel):
    ids: list[str]
    dry_run: bool = True


@router.post("/admin/normalize_technologies", tags=["Admin"])
def normalize_technologies(req: NormalizeRequest):
    """
    Normalise les noms de technologies dans les métadonnées pour les IDs donnés.
    - Met en minuscules et trim la partie nom des entrées "name:level".
    - dry_run=True par défaut pour voir les changements sans les appliquer.
    """
    if not req.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La liste d'IDs ne peut pas être vide.")

    try:
        metas = fetch_metadata(req.ids)
        result = {"updated": [], "skipped": [], "preview": {}}
        for vid, meta in metas.items():
            techs = meta.get("technologies")
            if not techs or not isinstance(techs, list):
                result["skipped"].append({"id": vid, "reason": "no_technologies"})
                continue

            def norm_one(t: str) -> str:
                parts = str(t).split(":", 1)
                name = parts[0].strip().lower()
                level = parts[1] if len(parts) > 1 else ""
                return f"{name}:{level}" if level != "" else name

            normalized = [norm_one(t) for t in techs]

            # Prévisualisation des changements
            if normalized != techs:
                result["preview"][vid] = {"before": techs, "after": normalized}
                if not req.dry_run:
                    new_meta = dict(meta)
                    new_meta["technologies"] = normalized
                    update_metadata(vid, new_meta)
                    result["updated"].append(vid)
            else:
                result["skipped"].append({"id": vid, "reason": "already_normalized"})

        return {"dry_run": req.dry_run, **result}
    except Exception as e:
        logger.error("Erreur lors de la normalisation des technologies", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# --- Admin: Lister les IDs (limitation Pinecone) ---
@router.get("/admin/vector_ids", tags=["Admin"])
def list_vector_ids():
    """
    Pinecone ne fournit pas d'API publique pour lister tous les IDs d'un index.
    Merci de fournir la liste d'IDs via vos propres sources (ex: base de données applicative)
    et d'utiliser les endpoints de normalisation avec ces IDs.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Listing des IDs non supporté par l'API Pinecone. "
            "Fournissez les IDs en entrée des endpoints de normalisation."
        ),
    )


# --- Admin: Normaliser toutes les technologies par lots ---
class NormalizeAllRequest(BaseModel):
    ids: list[str]
    batch_size: int = 100
    dry_run: bool = True


@router.post("/admin/normalize_all", tags=["Admin"])
def normalize_all(req: NormalizeAllRequest):
    """
    Normalise les technologies pour un grand volume d'IDs, traités par lots.
    Fournissez la liste complète d'IDs (limitation Pinecone) et un batch_size.
    """
    if not req.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La liste d'IDs ne peut pas être vide.")
    if req.batch_size <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="batch_size doit être > 0.")

    updated_total: list[str] = []
    skipped_total: list[dict] = []
    preview_total: dict[str, dict] = {}

    for i in range(0, len(req.ids), req.batch_size):
        chunk = req.ids[i:i + req.batch_size]
        # Réutiliser la logique de normalisation par lot
        metas = fetch_metadata(chunk)
        for vid, meta in metas.items():
            techs = meta.get("technologies")
            if not techs or not isinstance(techs, list):
                skipped_total.append({"id": vid, "reason": "no_technologies"})
                continue

            def norm_one(t: str) -> str:
                parts = str(t).split(":", 1)
                name = parts[0].strip().lower()
                level = parts[1] if len(parts) > 1 else ""
                return f"{name}:{level}" if level != "" else name

            normalized = [norm_one(t) for t in techs]
            if normalized != techs:
                preview_total[vid] = {"before": techs, "after": normalized}
                if not req.dry_run:
                    new_meta = dict(meta)
                    new_meta["technologies"] = normalized
                    update_metadata(vid, new_meta)
                    updated_total.append(vid)
            else:
                skipped_total.append({"id": vid, "reason": "already_normalized"})

    return {
        "dry_run": req.dry_run,
        "updated_count": len(updated_total),
        "updated": updated_total,
        "skipped": skipped_total,
        "preview": preview_total,
    }
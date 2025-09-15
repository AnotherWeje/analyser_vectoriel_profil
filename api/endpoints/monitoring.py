import os
import logging
import ssl
import redis
import statistics
from urllib.parse import urlparse, parse_qs, urlunparse
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult
from pydantic import BaseModel
from typing import Optional

from services.vector_db import pc, index_name, fetch_metadata, update_metadata
from services.vector_db import search_similar_vectors
from services.nlp_service import NLPService
from models.candidate import Job

logger = logging.getLogger(__name__)

# Charger les variables d'environnement depuis .env en local (utile hors Docker Compose)
load_dotenv()
router = APIRouter()

# Service NLP local à ce module et seuil configurable
nlp_service = NLPService()
try:
    MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", "0.60"))
except ValueError:
    MIN_MATCH_SCORE = 0.60
    logger.warning("MIN_MATCH_SCORE invalide dans l'environnement (monitoring). Valeur par défaut 0.60 utilisée.")

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

 

@router.post("/monitoring/score_preview", tags=["Monitoring"])
def score_preview(job: Job, top_k: int = 50, threshold: Optional[float] = None, return_top: int = 10):
    """
    Calcule la distribution des scores pour une offre donnée et retourne les top résultats.
    - Utilise le même calcul de score que l'endpoint /match (0.7 * similarité + 0.3 * skills).
    - Permet de surcharger le seuil via query param `threshold`, sinon utilise MIN_MATCH_SCORE.
    """
    thr = float(threshold) if threshold is not None else float(MIN_MATCH_SCORE)
    # Embedding du job (cohérent avec matching.py) avec sections explicites
    job_text_structured = (
        f"Description du poste: {job.description}\n"
        f"Compétences requises: {', '.join(job.required_skills or [])}\n"
        f"Années d'expérience minimales: {getattr(job, 'min_experience_years', 0) or 0}"
    )
    job_text = job_text_structured.lower()
    job_embedding = list(nlp_service.generate_embedding(job_text))
    logger.info(
        "Score preview: job_id=%s top_k=%d threshold=%.2f return_top=%d",
        getattr(job, 'id', None), top_k, thr, return_top
    )
    # Construire un filtre Pinecone aligné avec /match
    metadata_filter = {"open_to_work": True}
    min_years = getattr(job, 'min_experience_years', 0) or 0
    if isinstance(min_years, (int, float)) and min_years > 0:
        metadata_filter["years_experience"] = {"$gte": int(min_years)}
    matches = search_similar_vectors(job_embedding, top_k=top_k, metadata_filter=metadata_filter)
    logger.info("Score preview: %d correspondances brutes retournées par Pinecone", len(matches))

    scores: list[float] = []
    items: list[dict] = []

    # Normaliser les compétences requises
    job_skills_norm = {s.strip().lower() for s in (job.required_skills or [])}

    for match in matches:
        metadata = match.metadata
        if not metadata:
            continue
        candidate_id = match.id
        similarity_score = match.score
        candidate_skills = [str(tech).split(':')[0] for tech in metadata.get("technologies", [])]
        candidate_skills_norm = {s.strip().lower() for s in candidate_skills}
        skill_match_score = (
            len(job_skills_norm & candidate_skills_norm) / len(job_skills_norm)
        ) if job_skills_norm else 0.0
        final_score = 0.7 * float(similarity_score) + 0.3 * float(skill_match_score)
        scores.append(final_score)
        items.append({
            "candidate_id": candidate_id,
            "score": round(final_score, 3),
            "breakdown": {
                "similarity": round(float(similarity_score), 3),
                "skill_match": round(float(skill_match_score), 3)
            },
            "metadata": {
                "profession": metadata.get("profession"),
                "location": metadata.get("location"),
                "years_experience": metadata.get("years_experience"),
            }
        })

    items.sort(key=lambda x: x["score"], reverse=True)
    count_total = len(scores)
    count_above = sum(1 for s in scores if s >= thr)

    if scores:
        stats = {
            "min": round(min(scores), 3),
            "max": round(max(scores), 3),
            "mean": round(statistics.mean(scores), 3),
            "median": round(statistics.median(scores), 3),
        }
    else:
        stats = {"min": None, "max": None, "mean": None, "median": None}

    return {
        "params": {"top_k": top_k, "threshold_used": thr, "return_top": return_top},
        "counts": {"total": count_total, "above_threshold": count_above},
        "stats": stats,
        "top": items[: max(0, int(return_top))],
    }
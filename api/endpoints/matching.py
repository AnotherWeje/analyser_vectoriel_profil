import logging
import os
from fastapi import APIRouter

from models.candidate import Candidate, Job
from services.nlp_service import NLPService
from services.vector_db import search_similar_vectors
from tasks.process_candidate import process_candidate_task

logger = logging.getLogger(__name__)
router = APIRouter()
nlp_service = NLPService()

# Seuil minimal configurable pour considérer qu'un match est acceptable
try:
    MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", "0.50"))
    logger.info("MIN_MATCH_SCORE valide dans l'environnement.")
except ValueError:
    MIN_MATCH_SCORE = 0.50
    logger.warning("MIN_MATCH_SCORE invalide dans l'environnement. Valeur par défaut 0.50 utilisée.")

@router.post("/candidates", tags=["Candidates"])
async def add_candidate(candidate: Candidate):
    task = process_candidate_task.delay(candidate.dict())
    logger.info(f"Tâche de traitement pour le candidat ID {candidate.id} envoyée à Celery. Task ID: {task.id}")
    return {"status": "Profil en cours de traitement", "task_id": task.id}

@router.post("/match", tags=["Matching"])
async def match_job(job: Job):
    # Normaliser le texte pour l'embedding selon le nouveau schéma Job
    parts = [
        f"Titre: {job.title}",
        f"Description du poste: {job.description}",
        f"Responsabilités: {job.responsibilities}",
        f"Exigences: {job.requirements}",
        f"Avantages: {job.benefits}",
        f"Type de poste: {job.jobType}",
        f"Niveau d'expérience: {job.experienceLevel}",
        f"Localisation: {job.location}",
        f"Télétravail autorisé: {job.remoteAllowed}",
        f"Mis en avant: {job.featured}",
        f"Compétences: {', '.join(job.skills or [])}",
    ]
    job_text_structured = "\n".join(parts)
    job_text = job_text_structured.lower()
    job_embedding = list(nlp_service.generate_embedding(job_text))
    logger.info(f"Recherche de correspondances pour l'offre d'emploi: {job.title}")
    # Construire un filtre Pinecone pour réduire le bruit
    metadata_filter = {"open_to_work": True}
    matches = search_similar_vectors(job_embedding, top_k=20, metadata_filter=metadata_filter)
    logger.info(f"Trouvé {len(matches)} correspondances depuis Pinecone.")
    results = []
    for match in matches:
        metadata = match.metadata
        if metadata:
            candidate_id = match.id
            similarity_score = match.score
            # Normaliser les compétences pour une comparaison insensible à la casse et aux espaces
            job_skills_norm = {s.strip().lower() for s in (job.skills or [])}
            candidate_skills = [tech.split(':')[0] for tech in metadata.get("technologies", [])]
            candidate_skills_norm = {s.strip().lower() for s in candidate_skills}
            skill_match_score = (
                len(job_skills_norm & candidate_skills_norm) / len(job_skills_norm)
            ) if job_skills_norm else 0
            final_score = 0.7 * similarity_score + 0.3 * skill_match_score
            # Filtrer selon le seuil minimal
            if final_score >= MIN_MATCH_SCORE:
                results.append({
                    "candidate_id": candidate_id,
                    "score": round(final_score, 2),
                    "breakdown": {
                        "similarity": round(similarity_score, 2),
                        "skill_match": round(skill_match_score, 2)
                    }
                })
            else:
                logger.debug(
                    "Candidat %s filtré: score final %.3f < seuil %.2f (sim=%.3f, skills=%.3f)",
                    candidate_id, final_score, MIN_MATCH_SCORE, similarity_score, skill_match_score
                )
    results.sort(key=lambda x: x['score'], reverse=True)
    logger.info("Nombre de matches après filtrage (seuil %.2f): %d", MIN_MATCH_SCORE, len(results))
    # Mapper vers le format demandé: rang (1-based), id, score final
    formatted = [
        {"rank": idx + 1, "candidate_id": item["candidate_id"], "score": item["score"]}
        for idx, item in enumerate(results)
    ]
    return formatted
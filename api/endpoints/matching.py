import logging
from fastapi import APIRouter

from models.candidate import Candidate, Job
from services.nlp_service import NLPService
from services.vector_db import search_similar_vectors
from tasks.process_candidate import process_candidate_task

logger = logging.getLogger(__name__)
router = APIRouter()
nlp_service = NLPService()

@router.post("/candidates", tags=["Candidates"])
async def add_candidate(candidate: Candidate):
    task = process_candidate_task.delay(candidate.dict())
    logger.info(f"Tâche de traitement pour le candidat ID {candidate.id} envoyée à Celery. Task ID: {task.id}")
    return {"status": "Profil en cours de traitement", "task_id": task.id}

@router.post("/match", tags=["Matching"])
async def match_job(job: Job):
    # Normaliser le texte pour l'embedding (cohérent avec le profil candidat en minuscules)
    job_text = f"{job.description} {' '.join(job.required_skills)}".lower()
    job_embedding = list(nlp_service.generate_embedding(job_text))
    logger.info(f"Recherche de correspondances pour l'offre d'emploi ID: {job.id}")
    matches = search_similar_vectors(job_embedding, top_k=10)
    logger.info(f"Trouvé {len(matches)} correspondances depuis Pinecone.")
    results = []
    for match in matches:
        metadata = match.metadata
        if metadata:
            candidate_id = match.id
            similarity_score = match.score
            # Normaliser les compétences pour une comparaison insensible à la casse et aux espaces
            job_skills_norm = {s.strip().lower() for s in (job.required_skills or [])}
            candidate_skills = [tech.split(':')[0] for tech in metadata.get("technologies", [])]
            candidate_skills_norm = {s.strip().lower() for s in candidate_skills}
            skill_match_score = (
                len(job_skills_norm & candidate_skills_norm) / len(job_skills_norm)
            ) if job_skills_norm else 0
            final_score = 0.7 * similarity_score + 0.3 * skill_match_score
            results.append({
                "candidate_id": candidate_id, 
                "score": round(final_score, 2), 
                "breakdown": {"similarity": round(similarity_score, 2), "skill_match": round(skill_match_score, 2)}
            })
    results.sort(key=lambda x: x['score'], reverse=True)
    return results
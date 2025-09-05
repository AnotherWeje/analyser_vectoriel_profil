from fastapi import FastAPI, Body
from models.candidate import Candidate, Job
from services.nlp_service import NLPService
from services.vector_db import VectorDB
from services.storage import Storage

app = FastAPI()
nlp_service = NLPService()
vector_db = VectorDB()
storage = Storage()

@app.post("/candidates")
async def add_candidate(candidate: Candidate):
    from tasks.process_candidate import process_candidate_task
    # Lancer tâche asynchrone pour traitement lourd
    # task = process_candidate_task.delay(candidate.dict())
    # return {"status": "Profil en cours de traitement", "task_id": task.id}
    task = process_candidate_task(candidate.dict())
    return {"status": "Profil en cours de traitement", "task_id": task}

@app.post("/jobs")
async def match_job(job: Job):
    # Préparer texte de l'offre
    job_text = f"{job.description} {' '.join(job.required_skills)}"
    job_embedding = nlp_service.generate_embedding(job_text)
    
    # Query vectorielle
    matches = vector_db.query(job_embedding, top_k=100)
    print(f"Found {len(matches)} matches")
    
    # Récupérer métadonnées pour scoring
    results = []
    for candidate_id, score in matches:
        if candidate_id:
            metadata = storage.get_candidate_metadata(candidate_id)
            skill_match = len(set(job.required_skills) & set(metadata.get("skills", []))) / len(job.required_skills) if job.required_skills else 0
            final_score = 0.7 * score + 0.3 * skill_match  # Score composite
            results.append({"candidate_id": candidate_id, "score": final_score, "skills": metadata.get("skills", [])})
    return results

    # return sorted(results, key=lambda x: x["score"], reverse=True)


@app.get("/vectordb/info")
async def get_vectordb_info():
    """
    Retourne des informations de débogage sur la base de données vectorielle.
    """
    return {
        "num_vectors": vector_db.index.ntotal,  # type: ignore
        "dimension": vector_db.dimension,
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    from celery.result import AsyncResult
    task = AsyncResult(task_id)
    return {"task_id": task_id, "status": task.status, "result": task.result if task.ready() else None}
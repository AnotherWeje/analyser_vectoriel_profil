from fastapi import FastAPI, Body
from models.candidate import Candidate, Job
from services.nlp_service import NLPService
from services.vector_db import VectorDB
from services.storage import Storage
from tasks.process_candidate import process_candidate_task

app = FastAPI()
nlp_service = NLPService()
storage = Storage()

@app.post("/candidates")
async def add_candidate(candidate: Candidate):
    # Lancer tâche asynchrone pour traitement lourd
    task = process_candidate_task.delay(candidate.dict())
    return {"status": "Profil en cours de traitement", "task_id": task.id}
    # task = process_candidate_task(candidate.dict())
    # return {"status": "Profil en cours de traitement", "task_id": task}

@app.post("/jobs")
async def match_job(job: Job):
    # Préparer texte de l'offre
    job_text = f"{job.description} {' '.join(job.required_skills)}"
    job_embedding = nlp_service.generate_embedding(job_text)
    
    # Query vectorielle
    fresh_vector_db = VectorDB()
    matches = fresh_vector_db.query(job_embedding, top_k=100)
    print(f"Found {len(matches)} matches")
    
    # Récupérer métadonnées pour scoring
    results = []
    for candidate_id, score in matches:
        if candidate_id:
            metadata = storage.get_candidate_metadata(candidate_id)
            # Borner les scores pour éviter les dépassements dus aux imprécisions de calcul
            score = min(score, 1.0)
            skill_match = min(len(set(job.required_skills) & set(metadata.get("skills", []))) / len(job.required_skills) if job.required_skills else 0, 1.0)
            final_score = round((0.7 * score + 0.3 * skill_match) * 10, 2)  # Score composite sur 10, arrondi à 2 décimales
            results.append({"candidate_id": candidate_id, "score": final_score, "skills": metadata.get("skills", [])})
    return results

    # return sorted(results, key=lambda x: x["score"], reverse=True)


@app.get("/vectordb/info")
async def get_vectordb_info():
    """
    Retourne des informations de débogage sur la base de données vectorielle.
    """
    fresh_vector_db = VectorDB()
    return {
        "num_vectors": fresh_vector_db.index.ntotal,
        "dimension": fresh_vector_db.dimension,
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    from celery.result import AsyncResult
    task = AsyncResult(task_id)
    return {"task_id": task_id, "status": task.status, "result": task.result if task.ready() else None}

if __name__ == "__main__":
    nlp_service_test = NLPService()

    # Exemple de texte en français
    texte_fr = "Le candidat a des compétences en développement web avec Python et Django."
    print("--- Traitement du texte en français ---")
    features_fr = nlp_service_test.extract_features(texte_fr)
    print(f"Caractéristiques extraites : {features_fr}")

    print("\n" + "="*30 + "\n")

    # Exemple de texte en anglais
    texte_en = "The candidate has skills in web development with Python and Django."
    print("--- Processing English text ---")
    features_en = nlp_service_test.extract_features(texte_en)
    print(f"Extracted features: {features_en}")

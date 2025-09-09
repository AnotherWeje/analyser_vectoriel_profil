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
    # Convertit l'objet Candidate en dictionnaire pour le passer à la tâche Celery.
    # Celery sérialise les arguments de la tâche en JSON, et les objets Pydantic
    # doivent être convertis en types Python natifs (dict) pour cela.
    task = process_candidate_task.delay(candidate.dict())
    return {"status": "Profil en cours de traitement", "task_id": task.id}

@app.post("/jobs")
async def match_job(job: Job):
    # Concatène la description de l'offre et les compétences requises en un seul texte
    # pour générer un embedding représentatif de l'offre d'emploi.
    job_text = f"{job.description} {' '.join(job.required_skills)}"
    job_embedding = nlp_service.generate_embedding(job_text)
    
    # Initialise une nouvelle instance de VectorDB pour s'assurer que l'index est chargé
    # depuis le disque avec les dernières données des candidats.
    fresh_vector_db = VectorDB()
    # Effectue une recherche de similarité vectorielle pour trouver les candidats les plus pertinents.
    # top_k définit le nombre maximum de résultats à retourner.
    matches = fresh_vector_db.query(job_embedding, top_k=10)
    print(f"Found {len(matches)} matches")
    
    # Traite les résultats de la recherche vectorielle et calcule un score composite.
    results = []
    for candidate_id, score in matches:
        if candidate_id:
            # Récupère les métadonnées complètes du candidat depuis le stockage SQLite.
            metadata = storage.get_candidate_metadata(candidate_id)
            # Calcule la correspondance des compétences directes entre l'offre et le candidat.
            # Le score est basé sur le nombre de compétences requises qui sont également possédées par le candidat.
            skill_match = len(set(job.required_skills) & set(metadata.get("skills", []))) / len(job.required_skills) if job.required_skills else 0
            # Calcule le score final composite : 70% de similarité vectorielle et 30% de correspondance des compétences.
            final_score = 0.7 * score + 0.3 * skill_match  # Score composite
            results.append({"candidate_id": candidate_id, "score": final_score})
    return results

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

    # Test embeddings for different texts
    text1 = "Développeur Python avec expérience en Django."
    text2 = "Ingénieur logiciel Java et Spring Boot."
    embedding1 = nlp_service_test.generate_embedding(text1)
    embedding2 = nlp_service_test.generate_embedding(text2)
    print(f"Embedding 1 (first 5 elements): {embedding1[:5]}")
    print(f"Embedding 2 (first 5 elements): {embedding2[:5]}")
    print(f"Embeddings are identical: {embedding1 == embedding2}")

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
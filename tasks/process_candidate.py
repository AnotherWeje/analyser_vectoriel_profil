from celery import Celery
from services.nlp_service import NLPService
from services.storage import Storage
from services.vector_db import VectorDB

app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'

nlp_service = NLPService()
vector_db = VectorDB()
storage = Storage()

@app.task
def process_candidate_task(candidate: dict):
    # Préparer texte unifié
    profile_text = (
        f"{candidate['education']} "
        f"{' '.join(candidate['experience_pro'])} "
        f"{' '.join(candidate['certifications'])} "
        f"{' '.join(candidate['competences'])} "
        f"{' '.join(candidate['langues'])} "
        f"{candidate['niveau_etudes']}"
    ).lower()
    
    # Extraire features
    features = nlp_service.extract_features(profile_text)
    metadata = {
        "skills": list(set(candidate["competences"] + features["skills"])),
        "experience_years": len(candidate["experience_pro"]),  # Approximation
        "niveau_etudes": candidate["niveau_etudes"],
        "langues": candidate["langues"]
    }
    
    # Générer embedding
    embedding = nlp_service.generate_embedding(profile_text)
    print("Embedding length:", len(embedding))

    # Stocker
    vector_db.add(candidate["id"], embedding)
    storage.save_candidate(candidate["id"], metadata)

    total_vectors = vector_db.index.ntotal
    print(f"[INFO] Traitement terminé pour le candidat ID: {candidate['id']}. L'index contient maintenant {total_vectors} vecteurs.")
    
    return {"status": "completed", "candidate_id": candidate["id"]}
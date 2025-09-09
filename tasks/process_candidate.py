from celery import Celery
from services.nlp_service import NLPService
# MODIFICATION: Import new Pinecone functions and system utilities
from services.vector_db import initialize_pinecone, save_vector
from models.candidate import Candidate
import sys
import os

# MODIFICATION: Use environment variables for broker and backend URLs for production readiness
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
backend_url = os.getenv('CELERY_BACKEND_URL', 'redis://localhost:6379/0')

app = Celery('tasks', broker=broker_url, backend=backend_url)
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'

nlp_service = NLPService()

# MODIFICATION: Initialize Pinecone once when the worker starts using a Celery signal
@app.on_after_configure.connect  # type: ignore
def setup_pinecone(sender, **kwargs):
    """Initialize Pinecone connection when the Celery worker starts."""
    try:
        initialize_pinecone()
    except Exception as e:
        print(f"FATAL: Could not initialize Pinecone. Worker will exit. Error: {e}")
        sys.exit(1) # Exit if DB connection fails


@app.task
def process_candidate_task(candidate_data: dict):
    """
    Tâche Celery pour traiter un profil de candidat.
    Cette tâche extrait les caractéristiques textuelles, génère un embedding vectoriel,
    et stocke l'embedding et les métadonnées dans la base de données vectorielle (Pinecone).
    """
    candidate = Candidate(**candidate_data)

    technology_names = [tech.name for tech in candidate.technologies]
    profile_text = (
        f"{candidate.profession} "
        f"{candidate.shortBio} "
        f"{candidate.biography} "
        f"{candidate.interestedBy} "
        f"{' '.join(technology_names)} "
        f"{candidate.location}"
    ).lower()

    features = nlp_service.extract_features(profile_text)
    
    # MODIFICATION: Adapt metadata to be Pinecone-compatible (values must be string, number, bool, or list of strings)
    metadata = {
        "profession": candidate.profession,
        "technologies": [f'{tech.name}:{tech.level}' for tech in candidate.technologies],
        "years_experience": candidate.yearsExperience,
        "highest_degree": candidate.highestDegree,
        "location": candidate.location,
        "disability": candidate.disability,
        "open_to_work": candidate.openToWork,
        "interested_by": candidate.interestedBy,
        "extracted_skills": features["skills"]
    }

    embedding = nlp_service.generate_embedding(profile_text)
    print("Embedding length:", len(embedding))

    # MODIFICATION: Replace old db calls with a single call to save_vector for Pinecone
    vector_id = str(candidate.id)
    save_vector(vector_id, embedding, metadata)

    # MODIFICATION: Update print statement for clarity
    print(f"[INFO] Traitement terminé pour le candidat ID: {candidate.id}. Vecteur sauvegardé dans Pinecone.")

    return {"status": "completed", "candidate_id": candidate.id}

from celery import Celery
from services.nlp_service import NLPService
from services.storage import Storage
from services.vector_db import VectorDB
from models.candidate import Candidate # Import the Candidate model

app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'

nlp_service = NLPService()
vector_db = VectorDB()
storage = Storage()

@app.task
def process_candidate_task(candidate_data: dict):
    """
    Tâche Celery pour traiter un profil de candidat.
    Cette tâche extrait les caractéristiques textuelles, génère un embedding vectoriel,
    et stocke l'embedding dans la base de données vectorielle (FAISS) ainsi que les
    métadonnées du candidat dans le stockage (SQLite).
    """
    # Convertit les données brutes du candidat (dictionnaire) en un objet Pydantic Candidate.
    # Cela assure la validation des données et un accès structuré aux attributs du candidat.
    candidate = Candidate(**candidate_data)

    # Prépare un texte unifié à partir des informations clés du profil du candidat.
    # Ce texte sera utilisé pour l'extraction de caractéristiques NLP et la génération d'embeddings.
    technology_names = [tech.name for tech in candidate.technologies]
    profile_text = (
        f"{candidate.profession} "
        f"{candidate.shortBio} "
        f"{candidate.biography} "
        f"{candidate.interestedBy} "
        f"{' '.join(technology_names)} "
        f"{candidate.location}"
    ).lower()

    # Extrait des caractéristiques (comme les compétences) du texte unifié du profil
    # en utilisant le service NLP.
    features = nlp_service.extract_features(profile_text)
    # Construit un dictionnaire de métadonnées à stocker avec l'embedding.
    # Ces métadonnées sont utilisées pour le filtrage et le scoring post-recherche vectorielle.
    metadata = {
        "profession": candidate.profession,
        "technologies": [{"name": tech.name, "level": tech.level} for tech in candidate.technologies],
        "years_experience": candidate.yearsExperience,
        "highest_degree": candidate.highestDegree,
        "location": candidate.location,
        "disability": candidate.disability,
        "open_to_work": candidate.openToWork,
        "interested_by": candidate.interestedBy,
        "extracted_skills": features["skills"] # Les compétences extraites par le NLP
    }

    # Génère l'embedding vectoriel du texte unifié du profil en utilisant le service NLP.
    # Cet embedding est la représentation numérique du sens sémantique du profil.
    embedding = nlp_service.generate_embedding(profile_text)
    print("Embedding length:", len(embedding))

    # Stocke l'embedding dans la base de données vectorielle (FAISS) et les métadonnées
    # associées dans le stockage (SQLite). L'ID du candidat est utilisé comme clé.
    vector_db.add(str(candidate.id), embedding)
    storage.save_candidate(str(candidate.id), metadata)

    total_vectors = vector_db.index.ntotal
    print(f"[INFO] Traitement terminé pour le candidat ID: {candidate.id}. L'index contient maintenant {total_vectors} vecteurs.")

    return {"status": "completed", "candidate_id": candidate.id}
# MODIFICATION: Import system utilities and new vector_db functions
import pinecone
from fastapi import FastAPI, Body
from models.candidate import Candidate, Job
from services.nlp_service import NLPService
from services.vector_db import initialize_pinecone, search_similar_vectors, pc, index_name
from tasks.process_candidate import process_candidate_task
import os
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()
nlp_service = NLPService()

# MODIFICATION: Initialize Pinecone connection on application startup
@app.on_event("startup")
def startup_event():
    initialize_pinecone()

@app.post("/candidates")
async def add_candidate(candidate: Candidate):
    # This endpoint correctly uses Celery and remains unchanged.
    task = process_candidate_task.delay(candidate.dict())
    return {"status": "Profil en cours de traitement", "task_id": task.id}

@app.post("/match")
async def match_job(job: Job):
    # MODIFICATION: This entire endpoint is rewritten to use Pinecone
    job_text = f"{job.description} {' '.join(job.required_skills)}"
    # Ensure the embedding is a standard Python list for Pinecone
    job_embedding = list(nlp_service.generate_embedding(job_text))
    
    # Perform the search using the new service function
    matches = search_similar_vectors(job_embedding, top_k=10)
    print(f"Found {len(matches)} matches from Pinecone")
    
    results = []
    for match in matches:
        # Metadata now comes directly from the search result, not from a separate storage
        metadata = match.metadata
        if metadata:
            # The vector ID from pinecone is the candidate ID
            candidate_id = match.id
            # The similarity score from pinecone
            similarity_score = match.score

            # Calculate skill match from metadata
            # The technologies are stored as "name:level", so we split to get the name
            candidate_skills = [tech.split(':')[0] for tech in metadata.get("technologies", [])]
            skill_match_score = len(set(job.required_skills) & set(candidate_skills)) / len(job.required_skills) if job.required_skills else 0
            
            # Composite score: 70% vector similarity, 30% direct skill match
            final_score = 0.7 * similarity_score + 0.3 * skill_match_score
            results.append({"candidate_id": candidate_id, "score": final_score, "breakdown": {"similarity": similarity_score, "skill_match": skill_match_score}})
    
    # Sort results by the new final score
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

@app.get("/vectordb/info")
def get_vectordb_info():
    """
    MODIFICATION: Returns debug information from the Pinecone index.
    """
    try:
        index = pc.Index(index_name)  # type: ignore
        stats = index.describe_index_stats()
        return {
            "num_vectors": stats.total_vector_count,
            "dimension": stats.dimension,
            "namespaces": {
                name: {
                    "vector_count": ns_stats.vector_count
                }
                for name, ns_stats in stats.namespaces.items()
            }
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    # This endpoint for checking Celery tasks remains unchanged.
    from celery.result import AsyncResult
    task = AsyncResult(task_id)
    return {"task_id": task_id, "status": task.status, "result": task.result if task.ready() else None}

# The __main__ block for local testing is unchanged.
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

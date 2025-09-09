# services/vector_db.py
import os
from pinecone import Pinecone

# --- NOUVELLE APPROCHE D'INITIALISATION ---

# 1. Récupérer la clé d'API depuis l'environnement
api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_ENVIRONMENT")

if not api_key or not index_name:
    raise ValueError("PINECONE_API_KEY and PINECONE_ENVIRONMENT must be set in the environment")

# 2. Créer une instance globale du client Pinecone
pc = Pinecone(api_key=api_key, environment=index_name)

# --- Fonctions du service ---

def initialize_pinecone():
    """
    Vérifie que l'index existe dans Pinecone au démarrage.
    """
    print("Connecting to Pinecone and verifying index...")
    try:
        index_list = pc.list_indexes().names()
        if index_name not in index_list:
            print(f"WARNING: Index '{index_name}' does not exist. Please create it in the Pinecone console.")
            # Vous pourriez vouloir lever une exception ici si l'index est absolument requis pour démarrer
            # raise ReferenceError(f"Pinecone index '{index_name}' not found.")
        else:
            print(f"Pinecone index '{index_name}' found and ready.")
    except Exception as e:
        print(f"FATAL: An error occurred while connecting to Pinecone: {e}")
        raise

def save_vector(vector_id: str, vector_data: list[float], metadata: dict):
    """
    Sauvegarde (ou met à jour) un vecteur dans l'index Pinecone.
    """
    try:
        # Obtenir une référence à l'index via l'instance pc
        index = pc.Index(str(index_name))
        index.upsert(
            vectors=[(vector_id, vector_data, metadata)]
        )
        print(f"Successfully upserted vector {vector_id}")
    except Exception as e:
        print(f"Error saving vector to Pinecone: {e}")
        raise

def search_similar_vectors(query_vector: list[float], top_k: int = 5):
    """
    Recherche les vecteurs les plus similaires dans Pinecone.
    """
    try:
        # Obtenir une référence à l'index via l'instance pc
        index = pc.Index(str(index_name))
        results = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
        return results.matches  # type: ignore
    except Exception as e:
        print(f"Error searching in Pinecone: {e}")
        raise
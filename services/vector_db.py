# services/vector_db.py
import os
import logging
from pinecone import Pinecone

# Obtenir un logger pour ce module
logger = logging.getLogger(__name__)

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
    logger.info("Connexion à Pinecone et vérification de l'index...")
    try:
        index_list = pc.list_indexes().names()
        if index_name not in index_list:
            logger.warning(f"L'index '{index_name}' n'existe pas. Veuillez le créer dans la console Pinecone.")
            # Vous pourriez vouloir lever une exception ici si l'index est absolument requis pour démarrer
            # raise ReferenceError(f"Pinecone index '{index_name}' not found.")
        else:
            logger.info(f"L'index Pinecone '{index_name}' est trouvé et prêt.")
    except Exception as e:
        logger.critical(f"FATAL: Une erreur est survenue lors de la connexion à Pinecone: {e}", exc_info=True)
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
        logger.info(f"Vecteur {vector_id} sauvegardé avec succès dans Pinecone.")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde du vecteur dans Pinecone: {e}", exc_info=True)
        raise

def search_similar_vectors(query_vector: list[float], top_k: int = 20):
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
        logger.error(f"Erreur lors de la recherche dans Pinecone: {e}", exc_info=True)
        raise

def fetch_metadata(ids: list[str]) -> dict[str, dict]:
    """
    Récupère les métadonnées pour une liste d'IDs.
    Retourne un dict {id: metadata} pour les IDs trouvés.
    """
    try:
        index = pc.Index(str(index_name))
        resp = index.fetch(ids=ids)
        vectors = getattr(resp, "vectors", {}) or {}
        return {vid: (v.get("metadata") or {}) for vid, v in vectors.items()}
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des métadonnées: {e}", exc_info=True)
        raise

def update_metadata(vector_id: str, metadata: dict) -> None:
    """
    Met à jour uniquement les métadonnées d'un vecteur existant.
    """
    try:
        index = pc.Index(str(index_name))
        index.update(id=vector_id, set_metadata=metadata)
        logger.info(f"Métadonnées mises à jour pour le vecteur {vector_id}.")
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour des métadonnées pour {vector_id}: {e}", exc_info=True)
        raise

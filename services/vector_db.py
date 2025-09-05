import faiss
import numpy as np
from typing import List, Tuple, Optional, Union
import os
import json

class VectorDB:
    def __init__(self, index_file="faiss.index", mappings_file="mappings.json"):
        self.dimension = 384  # Dimension pour paraphrase-multilingual-MiniLM-L12-v2
        self.index_file = index_file
        self.mappings_file = mappings_file
        
        if not self._load_from_disk():
            # Utiliser IndexFlatIP pour la similarité cosinus (produit scalaire sur vecteurs normalisés)
            self.index = faiss.IndexFlatIP(self.dimension)
            self.id_to_index: dict[str, int] = {}
            self.index_to_id: dict[int, str] = {}
            self.next_index = 0

    def _load_from_disk(self) -> bool:
        if os.path.exists(self.index_file) and os.path.exists(self.mappings_file):
            try:
                self.index = faiss.read_index(self.index_file)
                with open(self.mappings_file, 'r') as f:
                    mappings_data = json.load(f)
                    self.id_to_index = mappings_data['id_to_index']
                    self.index_to_id = {int(k): v for k, v in mappings_data['index_to_id'].items()}
                    self.next_index = mappings_data['next_index']
                print("Index et mappings chargés depuis le disque.")
                return True
            except Exception as e:
                print(f"Erreur lors du chargement de l'index : {e}")
                return False
        return False

    def _save_to_disk(self):
        try:
            faiss.write_index(self.index, self.index_file)
            mappings_data = {
                'id_to_index': self.id_to_index,
                'index_to_id': self.index_to_id,
                'next_index': self.next_index
            }
            with open(self.mappings_file, 'w') as f:
                json.dump(mappings_data, f)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde de l'index : {e}")

    def add(self, candidate_id: str, embedding: Union[List[float], np.ndarray]) -> None:
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        # Normaliser le vecteur pour que le produit scalaire soit la similarité cosinus
        faiss.normalize_L2(embedding)
        
        self.index.add(embedding) # type: ignore
        self.id_to_index[candidate_id] = self.next_index
        self.index_to_id[self.next_index] = candidate_id
        self.next_index += 1
        
        self._save_to_disk()

    def query(self, embedding: Union[List[float], np.ndarray], top_k: int = 100) -> List[Tuple[Optional[str], float]]:
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)

        # Normaliser le vecteur de requête
        faiss.normalize_L2(embedding)
        
        # La recherche renvoie maintenant la similarité cosinus directement
        scores, indices = self.index.search(embedding, top_k) # type: ignore
        
        return [(self.index_to_id.get(idx, None), float(score)) for idx, score in zip(indices[0], scores[0]) if idx in self.index_to_id]
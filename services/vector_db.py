import faiss
import numpy as np
from typing import List, Tuple, Optional, Union
import os
import json

class VectorDB:
    def __init__(self, index_file="faiss.index", mappings_file="mappings.json"):
        self.dimension = 384  # Dimension de all-MiniLM-L6-v2
        self.index_file = index_file
        self.mappings_file = mappings_file
        
        # Essayer de charger l'index et les mappings depuis le disque
        if not self._load_from_disk():
            # Si le chargement échoue, initialiser un index vide
            self.index = faiss.IndexFlatL2(self.dimension)
            self.id_to_index: dict[str, int] = {}
            self.index_to_id: dict[int, str] = {}
            self.next_index = 0

    def _load_from_disk(self) -> bool:
        """Charge l'index et les mappings depuis le disque. Retourne True en cas de succès."""
        if os.path.exists(self.index_file) and os.path.exists(self.mappings_file):
            try:
                self.index = faiss.read_index(self.index_file)
                with open(self.mappings_file, 'r') as f:
                    mappings_data = json.load(f)
                    self.id_to_index = mappings_data['id_to_index']
                    # Les clés JSON sont des str, il faut les reconvertir en int pour index_to_id
                    self.index_to_id = {int(k): v for k, v in mappings_data['index_to_id'].items()}
                    self.next_index = mappings_data['next_index']
                print("Index et mappings chargés depuis le disque.")
                return True
            except Exception as e:
                print(f"Erreur lors du chargement de l'index : {e}")
                return False
        return False

    def _save_to_disk(self):
        """Sauvegarde l'index et les mappings sur le disque."""
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
        # Convertir l'embedding en tableau NumPy float32
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        self.index.add(embedding)  # type: ignore
        self.id_to_index[candidate_id] = self.next_index
        self.index_to_id[self.next_index] = candidate_id
        self.next_index += 1
        
        # Sauvegarder l'état après modification
        self._save_to_disk()

    def query(self, embedding: Union[List[float], np.ndarray], top_k: int = 100) -> List[Tuple[Optional[str], float]]:
        # Convertir l'embedding en tableau NumPy float32
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        # Appeler search avec arguments nommés pour clarifier
        distances, indices = self.index.search(embedding, top_k)  # type: ignore
        
        # Convertir distances L2 en similarité cosinus (approximation)
        scores = 1 - (distances / 2.0)  # Normalisation approximative
        return [(self.index_to_id.get(idx, None), score) for idx, score in zip(indices[0], scores[0]) if idx in self.index_to_id]

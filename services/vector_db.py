import faiss
import numpy as np
from typing import List, Tuple, Optional, Union
import os
import json

class VectorDB:
    def __init__(self, index_file="faiss.index", mappings_file="mappings.json"):
        # Dimension des embeddings générés par le modèle SentenceTransformer (paraphrase-multilingual-MiniLM-L12-v2).
        self.dimension = 384
        self.index_file = index_file
        self.mappings_file = mappings_file
        
        # Essayer de charger l'index et les mappings depuis le disque.
        # Cela permet de persister l'état de la base de données vectorielle entre les exécutions.
        if not self._load_from_disk():
            # Si le chargement échoue (première exécution ou fichiers corrompus), initialiser un index vide.
            # IndexFlatL2 est utilisé pour calculer la distance euclidienne (L2) entre les vecteurs.
            self.index = faiss.IndexFlatL2(self.dimension)
            # Mappings pour associer les IDs de candidats (chaînes) aux indices internes de FAISS (entiers).
            self.id_to_index: dict[str, int] = {}
            self.index_to_id: dict[int, str] = {}
            # Compteur pour attribuer des indices uniques aux nouveaux embeddings.
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
        # Convertir l'embedding en tableau NumPy float32 pour FAISS.
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        # Ajoute l'embedding à l'index FAISS. Notez que IndexFlatL2 ajoute simplement le vecteur
        # et ne gère pas les mises à jour ou suppressions directes par ID. Si un candidat est ajouté
        # plusieurs fois, il y aura des entrées multiples dans l'index.
        self.index.add(embedding)  # type: ignore
        # Met à jour les mappings pour associer l'ID du candidat à l'indice FAISS nouvellement attribué.
        # Si le candidat existe déjà, son ancien mapping sera écrasé, mais l'ancien vecteur restera dans l'index.
        self.id_to_index[candidate_id] = self.next_index
        self.index_to_id[self.next_index] = candidate_id
        self.next_index += 1
        
        # Sauvegarder l'état après modification pour persistance.
        self._save_to_disk()

    def query(self, embedding: Union[List[float], np.ndarray], top_k: int = 100) -> List[Tuple[Optional[str], float]]:
        # Convertir l'embedding de la requête en tableau NumPy float32.
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding, dtype=np.float32)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        # Effectue la recherche de similarité dans l'index FAISS.
        # Retourne les distances (L2) et les indices des vecteurs les plus proches.
        distances, indices = self.index.search(embedding, top_k)  # type: ignore
        
        # Convertit les distances L2 en une approximation de similarité cosinus.
        # Une distance L2 plus petite indique une plus grande similarité, donc 1 - (distance / 2.0)
        # permet de transformer cela en un score où 1 est le plus similaire et 0 le moins.
        scores = 1 - (distances / 2.0)  # Normalisation approximative

        # Filtre les résultats pour ne retourner qu'une seule entrée par ID de candidat unique.
        # Si un candidat a plusieurs embeddings dans l'index (suite à des ajouts multiples),
        # seule la première occurrence (celle avec la meilleure distance/score) sera conservée.
        results = []
        seen_candidate_ids = set()
        for idx, score in zip(indices[0], scores[0]):
            candidate_id = self.index_to_id.get(idx, None)
            if candidate_id and candidate_id not in seen_candidate_ids:
                results.append((candidate_id, float(score)))
                seen_candidate_ids.add(candidate_id)
        return results

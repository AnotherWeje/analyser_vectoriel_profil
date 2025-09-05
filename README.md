# Moteur de Matching Sémantique pour le Recrutement

## 1. Description

Ce projet est une application FastAPI conçue pour analyser des profils de candidats et les faire correspondre à des offres d'emploi. La particularité de ce moteur est qu'il utilise des techniques de **traitement du langage naturel (NLP)** pour comprendre le *sens* des profils et des offres, allant au-delà de la simple correspondance de mots-clés.

Le score de matching final est un score composite qui évalue à la fois la similarité sémantique et la correspondance directe des compétences.

## 2. Architecture

Le système est composé de plusieurs services :
- **API FastAPI (`main.py`)** : Le point d'entrée de l'application, qui expose les endpoints pour ajouter des candidats et rechercher des offres.
- **Service NLP (`services/nlp_service.py`)** : Utilise un modèle `Sentence-Transformers` pour convertir les textes en vecteurs numériques (embeddings).
- **Base de Données Vectorielle (`services/vector_db.py`)** : Utilise **FAISS** (de Facebook AI) pour stocker les vecteurs et effectuer des recherches de similarité très rapides.
- **Stockage de Métadonnées (`services/storage.py`)** : Utilise **SQLite** pour sauvegarder les informations textuelles des candidats (compétences, expérience, etc.).

## 3. Fonctionnalités Principales

- **API RESTful** complète pour la gestion des candidats et des offres.
- **Matching Sémantique** basé sur le modèle de langage `all-MiniLM-L6-v2`.
- **Recherche de Similarité** haute performance avec FAISS.
- **Persistance de l'Index Vectoriel** : L'index Faiss et les mappings d'ID sont sauvegardés sur le disque (`faiss.index`, `mappings.json`) pour survivre aux redémarrages du serveur.
- **Score de Matching Composite** : Combine la pertinence sémantique (70%) et la correspondance des compétences (30%).
- **Endpoint de Débogage** pour inspecter l'état de la base de données vectorielle en temps réel.

## 4. Installation

1.  Assurez-vous d'avoir **Python 3.8+** installé.
2.  Créez un environnement virtuel et activez-le :
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```
3.  Installez les dépendances, y compris `faiss-cpu` :
    ```bash
    pip install -r requirements.txt
    ```
4.  Téléchargez le modèle de langage spaCy utilisé par le service NLP :
    ```bash
    python -m spacy download fr_core_news_sm
    ```

## 5. Lancement

Le projet est actuellement configuré pour fonctionner de manière **synchrone** (les tâches sont exécutées immédiatement).

1.  Lancez le serveur FastAPI avec Uvicorn :
    ```bash
    uvicorn main:app --reload
    ```
2.  Le serveur sera accessible à l'adresse `http://127.0.0.1:8000`.

> **Note sur le mode Asynchrone (Celery)** :
> Le code pour utiliser Celery et Redis est présent mais actuellement non activé dans `main.py`. Pour passer en mode asynchrone (recommandé pour la production), vous devrez installer et lancer Redis, puis décommenter la ligne `task = process_candidate_task.delay(...)` et commenter l'appel direct dans `main.py`.

## 6. Utilisation de l'API

### Ajouter un Candidat
- **Endpoint** : `POST /candidates`
- **Body** (exemple) :
```json
{
    "id": "cand_001",
    "nom": "Alice Martin",
    "email": "alice.martin@example.com",
    "education": "Master en Intelligence Artificielle",
    "experience_pro": ["Data Scientist chez TechCorp pendant 4 ans", "Stage de 6 mois en machine learning"],
    "certifications": ["Certification TensorFlow Developer"],
    "competences": ["Python", "PyTorch", "Scikit-learn", "SQL", "Analyse de données"],
    "langues": ["Français", "Anglais"],
    "niveau_etudes": "Master"
}
```

### Rechercher une Offre d'Emploi
- **Endpoint** : `POST /jobs`
- **Body** (exemple) :
```json
{
    "id": "job_123",
    "description": "Nous recherchons un Data Scientist expérimenté pour rejoindre notre équipe. Le candidat idéal aura une solide expérience en machine learning et en analyse de données pour construire des modèles prédictifs.",
    "required_skills": ["Python", "Machine Learning", "SQL", "Communication"]
}
```

### Consulter l'état de la DB Vectorielle
- **Endpoint** : `GET /vectordb/info`
- **Description** : Retourne le nombre de vecteurs actuellement dans l'index Faiss et leur dimension. Utile pour le débogage.
- **Réponse** (exemple) :
```json
{
  "num_vectors": 1,
  "dimension": 384
}
```

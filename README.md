# Moteur de Matching Sémantique pour le Recrutement

## 1. Description

Ce projet est un moteur de matching sémantique conçu pour analyser des profils de candidats et les faire correspondre à des offres d'emploi. Il utilise des techniques avancées de **traitement du langage naturel (NLP)** pour comprendre le *sens* des textes, allant au-delà de la simple correspondance de mots-clés.

L'architecture est désormais **découplée et asynchrone**, ce qui la rend plus robuste et scalable pour la production. Le score de matching final est un score composite qui évalue à la fois la similarité sémantique et la correspondance directe des compétences.

## 2. Architecture

Le système est composé de plusieurs services communicant via une file de messages :

-   **API FastAPI (`main.py`)** : Le point d'entrée de l'application, exposant les endpoints pour soumettre des candidats (traitement asynchrone) et rechercher des correspondances d'offres d'emploi.
-   **Worker Celery (`tasks/process_candidate.py`)** : Un processus de fond qui consomme les tâches de traitement de candidats depuis la file de messages. Il effectue l'analyse NLP et stocke les vecteurs dans Pinecone.
-   **Service NLP (`services/nlp_service.py`)** : Utilise un modèle `Sentence-Transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) pour convertir les textes en embeddings (vecteurs numériques).
-   **Base de Données Vectorielle (`services/vector_db.py`)** : Intègre **Pinecone**, un service managé de base de données vectorielle, pour stocker les embeddings des candidats et leurs métadonnées, et effectuer des recherches de similarité très rapides.
-   **File de Messages (Redis/RabbitMQ)** : Sert de broker pour Celery, permettant une communication asynchrone fiable entre l'API FastAPI et le Worker Celery.

## 3. Fonctionnalités Principales

-   **API RESTful** complète pour la gestion des candidats et des offres.
-   **Traitement Asynchrone des Candidats** via Celery pour une meilleure scalabilité.
-   **Matching Sémantique** basé sur le modèle de langage `paraphrase-multilingual-MiniLM-L12-v2`.
-   **Recherche de Similarité** haute performance et scalable avec **Pinecone**.
-   **Persistance des Vecteurs et Métadonnées** : Toutes les données de recherche (embeddings et métadonnées des candidats) sont stockées et gérées par Pinecone.
-   **Score de Matching Composite** : Combine la pertinence sémantique (70%) et la correspondance des compétences (30%).
-   **Endpoint de Débogage** pour inspecter l'état de la base de données vectorielle Pinecone en temps réel.

## 4. Installation

1.  Assurez-vous d'avoir **Python 3.8+** installé.
2.  **Clonez le dépôt** :
    ```bash
    git clone https://github.com/votre_utilisateur/analyser_vectoriel_profil.git
    cd analyser_vectoriel_profil
    ```
3.  **Créez et activez un environnement virtuel** :
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```
4.  **Installez les dépendances Python** :
    ```bash
    pip install -r requirements.txt
    ```
5.  **Configuration des Variables d'Environnement** :
    Créez un fichier `.env` à la racine du projet et remplissez-le avec vos informations. Ce fichier ne doit **pas** être versionné.
    ```dotenv
    # .env
    PINECONE_API_KEY="VOTRE_CLE_API_PINECONE"
    PINECONE_ENVIRONMENT="VOTRE_ENVIRONNEMENT_PINECODE" # ex: us-west1-gcp

    # Configuration Celery (choisissez Redis ou RabbitMQ)
    CELERY_BROKER_URL="redis://localhost:6379/0" # Ou "amqp://guest:guest@localhost:5672//"
    CELERY_BACKEND_URL="redis://localhost:6379/0" # Ou "rpc://"

    # Si votre backend Django est séparé et nécessite une clé API pour la communication
    # DJANGO_API_URL="http://localhost:8000/api/v1/"
    # DJANGO_API_TOKEN="VOTRE_TOKEN_API_DJANGO"
    ```
6.  **Créez votre Index Pinecone** :
    Allez sur [pinecone.io](https://www.pinecone.io/), créez un compte et un index avec le nom `candidate-profiles`. Assurez-vous que les dimensions correspondent à celles de votre modèle NLP (ex: `384` pour `paraphrase-multilingual-MiniLM-L12-v2`).

## 5. Lancement

Pour lancer l'application, vous devez démarrer le broker Celery, le worker Celery et le serveur FastAPI.

1.  **Démarrez votre Broker Celery** (ex: Redis ou RabbitMQ). Si vous utilisez Docker :
    ```bash
    # Pour Redis
    docker run -d -p 6379:6379 --name my-redis redis
    # Pour RabbitMQ
    docker run -d -p 5672:5672 -p 15672:15672 --name my-rabbit rabbitmq:management
    ```
2.  **Démarrez le Worker Celery** :
    ```bash
    dotenv run -- celery -A tasks.process_candidate worker --loglevel=info
    ```
3.  **Démarrez le Serveur FastAPI** :
    ```bash
    dotenv run -- uvicorn main:app --reload
    ```

Le serveur FastAPI sera accessible à l'adresse `http://127.0.0.1:8000`.

## 6. Utilisation de l'API

### Ajouter un Candidat (Traitement Asynchrone)
-   **Endpoint** : `POST /candidates`
-   **Description** : Soumet un profil de candidat pour analyse. Le traitement est mis en file d'attente et exécuté par le worker Celery.
-   **Body** (exemple) :
    ```json
    {
      "id": 1,
      "profession": "Développeur.euse Full stack",
      "user": "http://wib-challenge-dev-backend-213-32-91-101.traefik.me/api/users/13/",
      "technologies": [
        {
          "id": 1,
          "name": "PHP",
          "level": 50
        }
      ],
      "createdAt": "2025-09-01T10:24:18.889648Z",
      "updatedAt": "2025-09-01T10:24:18.889679Z",
      "location": "Douala",
      "shortBio": "je suis developpeur",
      "biography": "je fais les applications",
      "disability": false,
      "openToWork": false,
      "yearsExperience": 1,
      "otherYearsExperience": 3,
      "highestDegree": 2,
      "interestedBy": "nouvelle technologie"
    }
    ```

### Rechercher des Candidats pour une Offre d'Emploi
-   **Endpoint** : `POST /match`
-   **Description** : Recherche les candidats les plus pertinents pour une offre d'emploi donnée, basée sur la similarité sémantique et la correspondance des compétences.
-   **Body** (exemple) :
    ```json
    {
        "id": "job_123",
        "description": "Nous recherchons un Data Scientist expérimenté pour rejoindre notre équipe. Le candidat idéal aura une solide expérience en machine learning et en analyse de données pour construire des modèles prédictifs.",
        "required_skills": ["Python", "Machine Learning", "SQL", "Communication"]
    }
    ```

### Consulter l'état de la DB Vectorielle
-   **Endpoint** : `GET /vectordb/info`
-   **Description** : Retourne des informations de débogage sur l'index Pinecone (nombre de vecteurs, dimension, namespaces).
-   **Réponse** (exemple) :
    ```json
    {
      "num_vectors": 1,
      "dimension": 384, # Exemple
      "namespaces": {}
    }
    ```
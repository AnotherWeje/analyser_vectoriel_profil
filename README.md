# Moteur de Matching Sémantique pour le Recrutement

## 1. Description

Ce projet est un moteur de matching sémantique conçu pour analyser des profils de candidats et les faire correspondre à des offres d'emploi. Il utilise des techniques avancées de **traitement du langage naturel (NLP)** pour comprendre le *sens* des textes, allant au-delà de la simple correspondance de mots-clés.

L'architecture est **microservices découplée et asynchrone**, optimisée pour la production avec :
- **Consumer Redis Streams** pour l'ingestion en temps réel
- **Worker Celery** pour le traitement asynchrone
- **API FastAPI** pour l'interface utilisateur
- **Optimisations Docker** pour chaque service

Le score de matching final est un score composite qui évalue à la fois la similarité sémantique (70%) et la correspondance des compétences (30%).

## 2. Architecture

Le système est composé de plusieurs services microservices orchestrés via Docker Compose :

### Services principaux :
- **API FastAPI (`main.py`)** : Point d'entrée REST exposant les endpoints pour soumettre des candidats et rechercher des correspondances.
- **Worker Celery (`tasks/process_candidate.py`)** : Traitement asynchrone des candidats avec analyse NLP et stockage dans Pinecone.
- **Consumer Redis Streams (`services/stream_consumer.py`)** : Écoute les événements Redis Streams et les transmet au worker Celery.
- **Service NLP (`services/nlp_service.py`)** : Utilise le modèle `Sentence-Transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) pour générer des embeddings.
- **Base Vectorielle (`services/vector_db.py`)** : Intégration avec **Pinecone** pour le stockage et la recherche de similarité.

### Services externes requis :
- **Redis** : Broker pour Celery et streams de messages (support SSL/TLS)
- **Pinecone** : Base de données vectorielle managée

### Optimisations :
- **Dockerfiles dédiés** : Chaque service a son propre Dockerfile optimisé
- **Consumer minimaliste** : Conteneur léger avec uniquement les dépendances nécessaires
- **Configuration SSL** : Support automatique pour les connexions Redis sécurisées
- **Logging structuré** : Format JSON pour la production, lisible pour le développement

## 3. Fonctionnalités Principales

- **API RESTful** complète pour la gestion des candidats et des offres d'emploi
- **Traitement Asynchrone** via Celery avec file de messages Redis
- **Ingestion temps réel** via Redis Streams pour l'intégration continue
- **Matching Sémantique** basé sur le modèle multilingue `paraphrase-multilingual-MiniLM-L12-v2`
- **Recherche de Similarité** haute performance avec Pinecone
- **Score Composite** : 70% similarité sémantique + 30% correspondance des compétences
- **Monitoring intégré** : Endpoints pour inspecter l'état des services
- **Architecture microservices** : Services découplés et scalables
- **Optimisations Docker** : Conteneurs optimisés pour chaque service
- **Support SSL/TLS** : Connexions sécurisées à Redis et autres services
- **Logging intelligent** : Format adaptatif selon l'environnement

## 4. Installation et Configuration

### 4.1 Prérequis

- **Docker et Docker Compose** installés
- **Compte Pinecone** avec index configuré
- **Instance Redis** accessible (ou utilisation de Docker)

### 4.2 Configuration des Variables d'Environnement

Créez un fichier `.env` à la racine du projet :

```dotenv
# Configuration Pinecone
PINECONE_API_KEY=votre_clé_api_pinecone
PINECONE_ENVIRONMENT=votre_index_pinecone  # ex: us-west1-gcp

# Configuration Redis
REDIS_URL=redis://localhost:6379/0  # Ou rediss:// pour SSL/TLS

# Configuration Logging
LOG_FORMAT=json  # ou 'human' pour le développement
LOG_LEVEL=INFO

# Configuration Matching
MIN_MATCH_SCORE=0.50

# Configuration Production (optionnel)
ENVIRONMENT=production
```

### 4.3 Index Pinecone

1. Créez un compte sur [pinecone.io](https://www.pinecone.io/)
2. Créez un index nommé `candidate-profiles`
3. Configurez les dimensions à `384` (modèle `paraphrase-multilingual-MiniLM-L12-v2`)
4. Notez votre clé API et l'environnement

## 5. Lancement avec Docker Compose

### Démarrage rapide :

```bash
# Construire et démarrer tous les services
cd /path/to/analyser_vectoriel_profil
docker compose up -d --build
```

### Services démarrés :
- **api** : FastAPI sur `http://localhost:8000`
- **worker** : Worker Celery pour le traitement asynchrone
- **consumer** : Consumer Redis Streams pour l'ingestion temps réel

### Commandes utiles :

```bash
# Voir les logs de tous les services
docker compose logs -f

# Logs d'un service spécifique
docker compose logs -f consumer

# Redémarrer un service
docker compose restart consumer

# Arrêter tous les services
docker compose down
```

### Vérification du fonctionnement :

```bash
# Vérifier que l'API répond
curl http://localhost:8000/

# Vérifier la santé des services
curl http://localhost:8000/monitoring/health
```

## 6. Utilisation de l'API

### Ajouter un Candidat (Traitement Asynchrone)
- **Endpoint** : `POST /candidates`
- **Description** : Soumet un profil de candidat. Le traitement est mis en file d'attente et exécuté par le worker Celery.

**Body (exemple) :**
```json
{
  "id": 1,
  "profession": "Développeur Full Stack",
  "technologies": [
    {"id": 1, "name": "Python", "level": 4},
    {"id": 2, "name": "FastAPI", "level": 3}
  ],
  "location": "Paris",
  "shortBio": "Développeur passionné par l'IA",
  "biography": "Expérience en développement web et machine learning",
  "yearsExperience": 3,
  "highestDegree": 2,
  "openToWork": true
}
```

### Rechercher des Candidats pour une Offre d'Emploi
- **Endpoint** : `POST /match`
- **Description** : Recherche les candidats les plus pertinents basée sur la similarité sémantique.

**Body (exemple) :**
```json
{
  "id": "job_123",
  "title": "Data Scientist Senior",
  "description": "Nous recherchons un Data Scientist expérimenté pour rejoindre notre équipe IA.",
  "requirements": "Machine Learning, Python, SQL, Communication",
  "skills": ["Python", "Machine Learning", "TensorFlow", "SQL"],
  "location": "Paris",
  "experienceLevel": "Senior",
  "remoteAllowed": true
}
```

**Réponse (exemple) :**
```json
[
  {"rank": 1, "candidate_id": "123", "score": 0.85},
  {"rank": 2, "candidate_id": "124", "score": 0.78}
]
```

### Monitoring et Débogage

#### État des Services
- `GET /monitoring/health` : Vérifie la santé de Redis et Pinecone

#### Informations Pinecone
- `GET /vectordb/info` : Statistiques sur l'index vectoriel

#### État des Tâches Celery
- `GET /monitoring/tasks/{task_id}` : État d'une tâche spécifique

## 7. Développement Local (sans Docker)

Si vous préférez développer sans Docker :

### Installation
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Lancement
```bash
# Démarrer Redis (si pas déjà fait)
docker run -d -p 6379:6379 redis

# Worker Celery en arrière-plan
celery -A tasks.process_candidate worker --loglevel=info &

# Consumer Redis Streams
python -m services.stream_consumer &

# API FastAPI
uvicorn main:app --reload
```

## 8. Architecture Détaillée

### Flux de Traitement

1. **Ingestion** : Le Consumer écoute `candidate_test_passed` dans Redis Streams
2. **Distribution** : Les messages sont envoyés au worker Celery via `process_candidate_task.delay()`
3. **Traitement NLP** : Extraction des entités et génération d'embeddings
4. **Stockage** : Sauvegarde dans Pinecone avec métadonnées
5. **Recherche** : L'API utilise la similarité vectorielle pour le matching

### Optimisations

- **Consumer minimaliste** : `requirements-consumer.txt` ne contient que les dépendances essentielles
- **Dockerfiles spécialisés** : Chaque service a son Dockerfile optimisé
- **Logging adaptatif** : Format JSON en production, lisible en développement
- **Reconnexion automatique** : Gestion robuste des pannes Redis
- **Dead Letter Queue** : Gestion des erreurs de traitement

### Services Découplés

Chaque service peut être scalé indépendamment :
- **API** : Load balancer pour gérer le trafic
- **Worker** : Scale horizontal pour le traitement
- **Consumer** : Multiple instances pour l'ingestion

## 9. Analyse de CV PDF (Utilitaire)

Un utilitaire est fourni pour extraire les informations d'un CV PDF.

### Utilisation
```bash
python -m analyse_de_cv_pdf.cli extract path/to/cv.pdf --out candidate.json
```

### Intégration
```bash
python -m analyse_de_cv_pdf.cli extract cv.pdf | \
curl -X POST http://localhost:8000/candidates \
  -H "Content-Type: application/json" \
  -d @-
```

## 10. Déploiement en Production

### Variables d'Environnement Supplémentaires
```dotenv
ENVIRONMENT=production
LOG_FORMAT=json

# SSL/TLS pour Redis (recommandé)
REDIS_URL=rediss://username:password@host:port/0

# Monitoring (optionnel)
SENTRY_DSN=https://your-sentry-dsn
```

### Scaling
```bash
# Scale le nombre de workers Celery
docker compose up -d --scale worker=3

# Scale les consumers pour plus d'ingestion
docker compose up -d --scale consumer=2
```

### Monitoring
- Logs centralisés avec le format JSON
- Health checks intégrés (`/monitoring/health`)
- Métriques Celery disponibles
- Surveillance des performances Pinecone

## 11. Contribution

### Structure du Projet
```
├── api/                    # Endpoints FastAPI
├── services/              # Services métier
├── tasks/                 # Tâches Celery
├── models/               # Modèles Pydantic
├── docker-compose.yml    # Orchestration des services
├── consumer.Dockerfile   # Dockerfile optimisé pour le consumer
├── api.Dockerfile       # Dockerfile pour l'API
├── worker.Dockerfile     # Dockerfile pour le worker
└── requirements-*.txt    # Dépendances spécialisées
```

### Standards de Code
- Commentaires en français dans le code
- Typage avec Pydantic
- Tests unitaires recommandés
- Documentation des fonctions importantes

---

*Projet créé avec ❤️ pour révolutionner le recrutement par la sémantique*
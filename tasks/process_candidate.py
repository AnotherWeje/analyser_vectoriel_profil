"""
Tâches Celery pour le traitement asynchrone des profils de candidats.

Ce module contient les tâches Celery qui sont exécutées par les workers
pour analyser les profils de candidats et les stocker dans Pinecone.

Fonctionnement :
1. Réception des données du candidat depuis la queue Celery
2. Extraction des features NLP (compétences, entités)
3. Génération d'embeddings sémantiques avec SentenceTransformers
4. Stockage des vecteurs et métadonnées dans Pinecone

Configuration Redis :
- Support SSL/TLS automatique pour les connexions sécurisées
- Keepalives et timeouts pour la stabilité
- Health checks automatiques

Logging :
- Format JSON pour la production
- Format lisible par l'homme pour le développement
- Filtrage des logs verbeux (kombu, redis, etc.)
"""
import os  # Accès aux variables d'environnement
import socket  # Configuration des options de socket pour Redis
import sys  # Accès aux fonctions système
from celery import Celery  # Framework de tâches asynchrones
from celery.signals import after_setup_logger  # Signal pour configurer le logging Celery
from dotenv import load_dotenv  # Chargement des variables d'environnement
import logging  # Configuration du système de logging
from logging_config import HumanReadableFormatter  # Formateur de logs lisible
from services.nlp_service import NLPService  # Service d'analyse NLP
from services.vector_db import initialize_pinecone, save_vector  # Services Pinecone
from models.candidate import Candidate  # Modèle de données pour les candidats
from urllib.parse import urlparse, parse_qs  # Parsing des URLs Redis

# --- Configuration initiale ---
load_dotenv()
logger = logging.getLogger(__name__)

# --- Fonction pour configurer l'URL Redis avec SSL ---
def configure_redis_url(redis_url):
    """Configure l'URL Redis avec les paramètres SSL appropriés si nécessaire"""
    if not redis_url.startswith('rediss://'):
        return redis_url
    
    # Parse l'URL pour vérifier les paramètres SSL existants
    parsed_url = urlparse(redis_url)
    query_params = parse_qs(parsed_url.query)
    
    # Si ssl_cert_reqs n'est pas déjà défini, l'ajouter
    if 'ssl_cert_reqs' not in query_params:
        # Ajouter le paramètre ssl_cert_reqs=CERT_NONE pour accepter les certificats auto-signés
        separator = '&' if parsed_url.query else '?'
        redis_url = f"{redis_url}{separator}ssl_cert_reqs=CERT_NONE"
    
    return redis_url

# --- Récupération et configuration de l'URL Redis ---
redis_url_base = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_url_final = configure_redis_url(redis_url_base)

# --- Création de l'application Celery ---
app = Celery('tasks', broker=redis_url_final, backend=redis_url_final)

# --- Configuration de l'application Celery ---
app.conf.task_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.result_serializer = 'json'

# Options de transport pour la stabilité (Keepalives, timeouts, health checks)
broker_transport_options = {
    'visibility_timeout': 3600,
    'socket_keepalive': True,
    'socket_keepalive_options': {
        socket.TCP_KEEPIDLE: 60,
        socket.TCP_KEEPINTVL: 30,
        socket.TCP_KEEPCNT: 3
    },
    # Timeouts et stratégies de retry côté broker
    'socket_timeout': 10,
    'retry_on_timeout': True,
    'health_check_interval': 30,
}

# Ajouter les options SSL si l'URL utilise rediss://
if redis_url_final.startswith('rediss://'):
    broker_transport_options.update({
        'ssl_cert_reqs': None,  # Équivalent à CERT_NONE
        'ssl_check_hostname': False,
        'ssl_ca_certs': None,
        'ssl_certfile': None,
        'ssl_keyfile': None,
    })

app.conf.broker_transport_options = broker_transport_options

# Paramètres généraux de connexion broker (au bon niveau de conf)
app.conf.broker_connection_retry_on_startup = True
app.conf.broker_connection_max_retries = None  # retry indéfini
app.conf.broker_heartbeat = 30
app.conf.broker_pool_limit = 0  # forcer des reconnexions propres en cas de bascule

# Configuration robuste pour le backend de résultats Redis (timeouts, keepalive, health checks)
result_backend_transport_options = {
    'socket_keepalive': True,
    'socket_keepalive_options': {
        socket.TCP_KEEPIDLE: 60,
        socket.TCP_KEEPINTVL: 30,
        socket.TCP_KEEPCNT: 3
    },
    'socket_timeout': 10,
    'retry_on_timeout': True,
    'health_check_interval': 30,
    # Stratégie de retry progressive côté transport pour encaisser les bascules
    'max_retries': 100,
    'interval_start': 0,
    'interval_step': 2,
    'interval_max': 30,
}

if redis_url_final.startswith('rediss://'):
    result_backend_transport_options.update({
        'ssl_cert_reqs': None,
        'ssl_check_hostname': False,
        'ssl_ca_certs': None,
        'ssl_certfile': None,
        'ssl_keyfile': None,
    })

app.conf.result_backend_transport_options = result_backend_transport_options

nlp_service = NLPService()

# --- Configuration des Logs de Celery ---
@after_setup_logger.connect
def setup_celery_logging(logger, **kwargs):
    if os.getenv('LOG_FORMAT', 'json').lower() == 'human':
        for handler in logger.handlers:
            handler.setFormatter(HumanReadableFormatter())
    
    noisy_loggers = ['kombu', 'billiard', 'redis', 'urllib3', 'celery.worker.consumer']
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

# --- Tâches Celery ---
@app.on_after_configure.connect  # type: ignore
def setup_pinecone(sender, **kwargs):
    try:
        initialize_pinecone()
    except Exception as e:
        logger.critical(f"FATAL: Impossible d'initialiser Pinecone. Le worker va s'arrêter. Erreur: {e}", exc_info=True)
        sys.exit(1)

@app.task
def process_candidate_task(candidate_data: dict):
    candidate = Candidate(**candidate_data)
    logger.info(f"Début du traitement pour le candidat ID: {candidate.id}")
    
    technology_names = [tech.name for tech in candidate.technologies]
    # Texte du profil structuré avec sections explicites pour de meilleurs embeddings
    profile_text_structured = (
        f"Profession: {candidate.profession}\n"
        f"Résumé court: {candidate.shortBio}\n"
        f"Biographie: {candidate.biography}\n"
        f"Intérêts: {candidate.interestedBy}\n"
        f"Technologies: {', '.join(technology_names)}\n"
        f"Localisation: {candidate.location}\n"
        f"Années d'expérience: {candidate.yearsExperience}\n"
        f"Diplôme le plus élevé: {candidate.highestDegree}\n"
        f"Ouvert aux opportunités: {candidate.openToWork}\n"
        f"Situation de handicap: {candidate.disability}"
    )
    # Normaliser en minuscules pour cohérence avec la recherche
    profile_text = profile_text_structured.lower()
    
    features = nlp_service.extract_features(profile_text)
    metadata = {
        "profession": candidate.profession,
        # Stocker les technologies en minuscules et sans espaces superflus pour la cohérence
        "technologies": [f"{tech.name.strip().lower()}:{tech.level}" for tech in candidate.technologies],
        "years_experience": candidate.yearsExperience,
        "highest_degree": candidate.highestDegree,
        "location": candidate.location,
        "disability": candidate.disability,
        "open_to_work": candidate.openToWork,
        "interested_by": candidate.interestedBy,
        "extracted_skills": features["skills"]
    }
    
    embedding = nlp_service.generate_embedding(profile_text)
    vector_id = str(candidate.id)
    save_vector(vector_id, embedding, metadata)
    
    logger.info(f"Traitement terminé pour le candidat ID: {candidate.id}. Vecteur sauvegardé dans Pinecone.")
    return {"status": "completed", "candidate_id": candidate.id}
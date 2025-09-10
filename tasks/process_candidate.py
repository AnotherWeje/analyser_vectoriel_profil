# import os
# import socket
# import sys
# from celery import Celery
# from celery.signals import after_setup_logger
# from dotenv import load_dotenv
# import logging

# from logging_config import HumanReadableFormatter
# from services.nlp_service import NLPService
# from services.vector_db import initialize_pinecone, save_vector
# from models.candidate import Candidate

# # --- Configuration initiale ---
# load_dotenv()
# logger = logging.getLogger(__name__)

# # --- Récupération de l'URL Redis complète depuis l'environnement ---
# # Utilisation directe de REDIS_URL, comme indiqué par l'utilisateur
# redis_url_final = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# # --- Création de l'application Celery ---
# # On utilise la même URL pour le broker et le backend pour plus de simplicité
# app = Celery('tasks', broker=redis_url_final, backend=redis_url_final)

# # --- Configuration de l'application Celery ---
# app.conf.task_serializer = 'json'
# app.conf.accept_content = ['json']
# app.conf.result_serializer = 'json'

# # Options de transport pour la stabilité (Keepalives)
# app.conf.broker_transport_options = {
#     'visibility_timeout': 3600,
#     'socket_keepalive': True,
#     'socket_keepalive_options': {
#         socket.TCP_KEEPIDLE: 60,
#         socket.TCP_KEEPINTVL: 30,
#         socket.TCP_KEEPCNT: 3
#     },
#     'broker_connection_retry_on_startup': True
# }

# nlp_service = NLPService()

# # --- Configuration des Logs de Celery ---
# @after_setup_logger.connect
# def setup_celery_logging(logger, **kwargs):
#     if os.getenv('LOG_FORMAT', 'json').lower() == 'human':
#         for handler in logger.handlers:
#             handler.setFormatter(HumanReadableFormatter())
#         noisy_loggers = ['kombu', 'billiard', 'redis', 'urllib3', 'celery.worker.consumer']
#         for logger_name in noisy_loggers:
#             logging.getLogger(logger_name).setLevel(logging.WARNING)

# # --- Tâches Celery ---
# @app.on_after_configure.connect # type: ignore
# def setup_pinecone(sender, **kwargs):
#     try:
#         initialize_pinecone()
#     except Exception as e:
#         logger.critical(f"FATAL: Impossible d'initialiser Pinecone. Le worker va s'arrêter. Erreur: {e}", exc_info=True)
#         sys.exit(1)

# @app.task
# def process_candidate_task(candidate_data: dict):
#     candidate = Candidate(**candidate_data)
#     logger.info(f"Début du traitement pour le candidat ID: {candidate.id}")
#     technology_names = [tech.name for tech in candidate.technologies]
#     profile_text = (
#         f"{candidate.profession} "
#         f"{candidate.shortBio} "
#         f"{candidate.biography} "
#         f"{candidate.interestedBy} "
#         f"{' '.join(technology_names)} "
#         f"{candidate.location}"
#     ).lower()
#     features = nlp_service.extract_features(profile_text)
#     metadata = {
#         "profession": candidate.profession,
#         "technologies": [f'{tech.name}:{tech.level}' for tech in candidate.technologies],
#         "years_experience": candidate.yearsExperience,
#         "highest_degree": candidate.highestDegree,
#         "location": candidate.location,
#         "disability": candidate.disability,
#         "open_to_work": candidate.openToWork,
#         "interested_by": candidate.interestedBy,
#         "extracted_skills": features["skills"]
#     }
#     embedding = nlp_service.generate_embedding(profile_text)
#     vector_id = str(candidate.id)
#     save_vector(vector_id, embedding, metadata)
#     logger.info(f"Traitement terminé pour le candidat ID: {candidate.id}. Vecteur sauvegardé dans Pinecone.")
#     return {"status": "completed", "candidate_id": candidate.id}


import os
import socket
import sys
from celery import Celery
from celery.signals import after_setup_logger
from dotenv import load_dotenv
import logging
from logging_config import HumanReadableFormatter
from services.nlp_service import NLPService
from services.vector_db import initialize_pinecone, save_vector
from models.candidate import Candidate
from urllib.parse import urlparse, parse_qs

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

# Options de transport pour la stabilité (Keepalives) avec gestion SSL
broker_transport_options = {
    'visibility_timeout': 3600,
    'socket_keepalive': True,
    'socket_keepalive_options': {
        socket.TCP_KEEPIDLE: 60,
        socket.TCP_KEEPINTVL: 30,
        socket.TCP_KEEPCNT: 3
    },
    'broker_connection_retry_on_startup': True
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

# Même configuration pour le backend si nécessaire
if redis_url_final.startswith('rediss://'):
    app.conf.result_backend_transport_options = {
        'ssl_cert_reqs': None,
        'ssl_check_hostname': False,
        'ssl_ca_certs': None,
        'ssl_certfile': None,
        'ssl_keyfile': None,
    }

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
    profile_text = (
        f"{candidate.profession} "
        f"{candidate.shortBio} "
        f"{candidate.biography} "
        f"{candidate.interestedBy} "
        f"{' '.join(technology_names)} "
        f"{candidate.location}"
    ).lower()
    
    features = nlp_service.extract_features(profile_text)
    metadata = {
        "profession": candidate.profession,
        "technologies": [f'{tech.name}:{tech.level}' for tech in candidate.technologies],
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
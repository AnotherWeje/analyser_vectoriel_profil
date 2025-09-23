"""
Consumer Redis Streams pour le traitement asynchrone des candidats.

Ce module écoute le stream Redis 'candidate_test_passed' et transmet
les messages reçus vers une tâche Celery pour traitement NLP et stockage
dans Pinecone.

Architecture :
- Lit les messages depuis Redis Streams en mode continu
- Gère les erreurs avec une Dead Letter Queue (DLQ)
- Reconnexion automatique en cas de perte de connexion
- Backoff exponentiel pour éviter la surcharge
"""
import sys
import os
import logging
import time
import json
import redis
from dotenv import load_dotenv
from typing import Dict, Any

# Ajouter le répertoire racine au PYTHONPATH pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Charger .env en local
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

STREAM_KEY = "candidate_test_passed"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def configure_redis_client() -> "redis.Redis[str]":
    """
    Configure et teste la connexion au serveur Redis.

    Returns:
        redis.Redis: Client Redis configuré et testé

    Raises:
        Exception: Si la connexion à Redis échoue
    """
    client = redis.from_url(REDIS_URL, decode_responses=True)
    client.ping()
    return client


def process_message(data: Dict[str, Any]) -> None:
    """Transmet l'événement à la tâche Celery de traitement candidat."""
    try:
        from tasks.process_candidate import process_candidate_task  # import local pour éviter coût au boot
        process_candidate_task.delay(data)
        logger.info("Task dispatched for candidate_id=%s", data.get("candidate_id"))
    except Exception:
        logger.exception("Failed to enqueue Celery task")
        raise


def main_loop() -> None:
    """
    Boucle principale du consumer Redis Streams.

    Écoute en continu le stream Redis et traite les messages reçus.
    Gère les erreurs avec reconnexion automatique et DLQ.
    """
    client = configure_redis_client()
    # Lire uniquement les nouveaux messages à partir de maintenant
    last_id = "$"
    backoff = 1.0
    max_backoff = 30.0

    while True:
        try:
            # XREAD bloque 10000ms, lit jusqu'à 10 messages à partir de last_id
            resp = client.xread(
                streams={STREAM_KEY: last_id},
                count=10,
                block=10000,
            )

            if not resp:
                continue

            # resp format: [(stream, [(id, {field: value}), ...])]
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    try:
                        raw = fields.get("data") or "{}"
                        payload = json.loads(raw)
                        process_message(payload)
                        # Mémoriser le dernier ID traité
                        last_id = msg_id
                    except Exception:
                        logger.exception("Processing failed for message id=%s; sending to DLQ", msg_id)
                        try:
                            client.xadd(
                                f"{STREAM_KEY}:dlq",
                                {"data": json.dumps({"id": msg_id, "raw": fields}, ensure_ascii=False)},
                                id="*",
                            )
                        except Exception:
                            logger.exception("Failed to push to DLQ for message id=%s", msg_id)

            backoff = 1.0  # reset backoff après succès
        except redis.exceptions.ConnectionError:
            logger.warning("Redis connection lost; retrying in %.1fs", backoff)
            time.sleep(backoff)
            backoff = min(max_backoff, backoff * 2)
            try:
                client = configure_redis_client()
                # Après reconnexion, repartir de "$" pour ne lire que les nouveaux messages
                last_id = "$"
            except Exception:
                logger.exception("Reconnection attempt failed")
        except Exception:
            logger.exception("Unexpected error in consumer loop")
            time.sleep(1)


if __name__ == "__main__":
    main_loop()
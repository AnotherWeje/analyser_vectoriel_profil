import logging
import sys
import os
from pythonjsonlogger import jsonlogger
from dotenv import load_dotenv

class HumanReadableFormatter(logging.Formatter):
    """
    Un formateur personnalisé qui détecte les logs structurés de Celery et les
    affiche de manière lisible, tout en affichant les autres logs simplement.
    """
    def format(self, record):
        # Si le log a un attribut 'data' (spécifique à nos logs Celery enrichis)
        if hasattr(record, 'data') and isinstance(record.data, dict): # type: ignore
            # C'est un log de trace de tâche Celery
            runtime = record.data.get('runtime', 0) # type: ignore
            task_name = record.data.get('name', 'unknown_task') # type: ignore
            task_id = record.data.get('id', 'unknown_id') # type: ignore
            
            # On reconstruit un message clair et concis
            if 'succeeded' in record.message:
                return f"[INFO] Tâche {task_name}[{task_id[:8]}...] réussie en {runtime:.2f}s"
            else:
                # Gérer d'autres états de Celery si nécessaire (échec, etc.)
                return f"[%(levelname)s] {record.message}"
        
        # Pour tous les autres logs, utiliser un format simple
        return f"[%(levelname)s] %(message)s"

def setup_logging():
    """
    Configure le logging pour émettre soit du JSON, soit un format lisible par l'homme.
    """
    load_dotenv()
    log_format_type = os.getenv('LOG_FORMAT', 'json').lower()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    logHandler = logging.StreamHandler(sys.stdout)
    
    if log_format_type == 'human':
        # Utiliser notre nouveau formateur intelligent
        formatter = HumanReadableFormatter()
        msg = "Logging configuré en mode HUMAIN (intelligent)."

        noisy_loggers = ['kombu', 'billiard', 'redis', 'urllib3']
        for logger_name in noisy_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

    else:
        formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
        msg = "Logging configuré en mode JSON (production)."

    logHandler.setFormatter(formatter)
    root_logger.addHandler(logHandler)
    
    logging.info(msg)

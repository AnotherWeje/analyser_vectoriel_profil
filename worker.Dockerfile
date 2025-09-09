# worker.Dockerfile

# Utilise la même image Python que l'API
FROM python:3.11-slim

# Définit le répertoire de travail
WORKDIR /app

# Copie les requirements et installe les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installe python-dotenv explicitement pour la commande dotenv run
RUN pip install python-dotenv

# Copie le reste du code de l'application
COPY . .

# Commande pour lancer le worker Celery
# Utilise dotenv run pour charger les variables d'environnement du .env
CMD ["dotenv", "run", "--", "celery", "-A", "tasks.process_candidate", "worker", "--loglevel=info"]
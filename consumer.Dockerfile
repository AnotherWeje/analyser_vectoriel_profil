# consumer.Dockerfile
#
# Dockerfile optimisé pour le service Consumer Redis Streams
#
# Ce conteneur ne contient que les dépendances essentielles pour
# le service stream_consumer.py, évitant les packages lourds
# comme Torch, CUDA, etc. qui ne sont pas nécessaires ici.
#
# Contrairement aux autres services (API, Worker), ce conteneur
# est minimaliste pour un démarrage rapide et une empreinte réduite.

# Utilise la même image Python que l'API et le worker
FROM python:3.11-slim

# Installation des dépendances système de base
# git et curl peuvent être utiles pour le debugging
RUN apt update && apt install -y git curl \
    && rm -rf /var/lib/apt/lists/*

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie le fichier requirements minimal et installe les dépendances
# Utilise requirements-consumer.txt qui ne contient que les packages essentiels
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le reste du code de l'application dans le conteneur
COPY . .

# Commande pour lancer le consumer Redis Streams
CMD ["python", "-m", "services.stream_consumer"]

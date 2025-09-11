# api.Dockerfile

# Utilise une image Python légère basée sur la version 3.11
FROM python:3.11-slim

RUN apt update && apt install -y git curl

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie le fichier requirements.txt et installe les dépendances
# Cela permet de tirer parti du cache Docker si les dépendances ne changent pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le reste du code de l'application dans le conteneur
COPY . .

# Expose le port sur lequel l'application FastAPI écoute
EXPOSE 8000

# Commande pour lancer le serveur Uvicorn
# --host 0.0.0.0 est nécessaire pour que l'application soit accessible depuis l'extérieur du conteneur
CMD ["dotenv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
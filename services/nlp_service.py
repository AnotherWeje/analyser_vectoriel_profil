import spacy
import logging
from sentence_transformers import SentenceTransformer
from langdetect import detect

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NLPService:
    def __init__(self):
        # Charger les modèles spaCy pour le français et l'anglais
        self.nlp_fr = spacy.load("fr_core_news_sm")
        self.nlp_en = spacy.load("en_core_web_sm")
        # Charger un modèle SentenceTransformer multilingue pour générer des embeddings (vecteurs numériques) de texte.
        # Ce modèle est optimisé pour la similarité sémantique entre phrases.
        # Forcer l'utilisation du CPU pour éviter toute dépendance CUDA
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', device='cpu')
        logging.info("Modèles NLP chargés.")

    def extract_features(self, text: str) -> dict:
        # Extrait des entités nommées (comme les compétences ou organisations) du texte en utilisant spaCy.
        # La langue du texte est d'abord détectée pour utiliser le modèle spaCy approprié.
        try:
            lang = detect(text)
            logging.info(f"Langue détectée : {lang}")
        except Exception as e:
            lang = 'fr'
            logging.warning(f"Échec de la détection de la langue : {e}. Utilisation du français par défaut.")

        if lang == 'fr':
            nlp = self.nlp_fr
            logging.info("Utilisation du modèle spaCy français.")
        elif lang == 'en':
            nlp = self.nlp_en
            logging.info("Utilisation du modèle spaCy anglais.")
        else:
            nlp = self.nlp_fr
            logging.info(f"Langue non supportée ({lang}). Utilisation du modèle spaCy français par défaut.")

        doc = nlp(text.lower())
        skills = [ent.text for ent in doc.ents if ent.label_ in ["SKILL", "ORG"]]
        return {"skills": skills}

    def generate_embedding(self, text: str) -> list:
        # Convertit le texte d'entrée en un vecteur numérique (embedding) en utilisant le modèle SentenceTransformer.
        # Cet embedding représente le sens sémantique du texte et est utilisé pour les calculs de similarité.
        return self.model.encode(text).tolist()
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
        # Charger un modèle SentenceTransformer multilingue
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        logging.info("Modèles NLP chargés.")

    def extract_features(self, text: str) -> dict:
        try:
            # Détecter la langue du texte
            lang = detect(text)
            logging.info(f"Langue détectée : {lang}")
        except Exception as e:
            # Si la détection échoue, utiliser le français par défaut
            lang = 'fr'
            logging.warning(f"Échec de la détection de la langue : {e}. Utilisation du français par défaut.")

        # Sélectionner le modèle spaCy approprié
        if lang == 'fr':
            nlp = self.nlp_fr
            logging.info("Utilisation du modèle spaCy français.")
        elif lang == 'en':
            nlp = self.nlp_en
            logging.info("Utilisation du modèle spaCy anglais.")
        else:
            # Utiliser le français par défaut pour les autres langues
            nlp = self.nlp_fr
            logging.info(f"Langue non supportée ({lang}). Utilisation du modèle spaCy français par défaut.")

        doc = nlp(text.lower())
        skills = [ent.text for ent in doc.ents if ent.label_ in ["SKILL", "ORG"]]
        return {"skills": skills}

    def generate_embedding(self, text: str) -> list:
        return self.model.encode(text).tolist()
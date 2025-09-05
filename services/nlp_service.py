import spacy
from sentence_transformers import SentenceTransformer

class NLPService:
    def __init__(self):
        self.nlp = spacy.load("fr_core_news_sm")  # Modèle français, adaptez si besoin
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def extract_features(self, text: str) -> dict:
        doc = self.nlp(text.lower())
        skills = [ent.text for ent in doc.ents if ent.label_ in ["SKILL", "ORG"]]
        return {"skills": skills}

    def generate_embedding(self, text: str) -> list:
        return self.model.encode(text).tolist()
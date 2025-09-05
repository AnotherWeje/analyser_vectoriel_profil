from pydantic import BaseModel
from typing import List, Optional

class Candidate(BaseModel):
    id: str
    nom: str
    email: str
    education: str
    experience_pro: List[str]
    certifications: List[str]
    competences: List[str]
    langues: List[str]
    niveau_etudes: str

class Job(BaseModel):
    description: str
    required_skills: List[str]
    min_experience_years: Optional[int] = 0
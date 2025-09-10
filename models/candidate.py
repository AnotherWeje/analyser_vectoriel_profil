from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Technology(BaseModel):
    id: int
    name: str
    level: int

class Candidate(BaseModel):
    id: int
    profession: str
    user: str
    technologies: List[Technology]
    createdAt: datetime
    updatedAt: datetime
    location: str
    shortBio: str
    biography: str
    disability: bool
    openToWork: bool
    yearsExperience: int
    otherYearsExperience: int
    highestDegree: int
    interestedBy: str

class Job(BaseModel):
    id: str
    description: str
    required_skills: List[str]
    min_experience_years: Optional[int] = 0
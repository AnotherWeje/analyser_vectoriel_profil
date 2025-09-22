from pydantic import BaseModel
from typing import List
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
    title: str
    description: str
    responsibilities: str
    requirements: str
    benefits: str
    jobType: str
    experienceLevel: str
    location: str
    remoteAllowed: bool
    featured: bool
    skills: List[str]
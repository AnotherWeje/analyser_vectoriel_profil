import logging
import os
import math
import re
import unicodedata
from fastapi import APIRouter, Response

from models.candidate import Candidate, Job
from services.nlp_service import NLPService
from services.vector_db import search_similar_vectors
from tasks.process_candidate import process_candidate_task

logger = logging.getLogger(__name__)
router = APIRouter()
nlp_service = NLPService()

# Gestion explicite des requêtes OPTIONS préflight pour CORS
@router.options("/match")
async def options_match():
    """
    Gestion des requêtes OPTIONS préflight pour l'endpoint /match.
    Nécessaire pour que les navigateurs puissent faire des requêtes cross-origin.
    """
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

@router.options("/candidates")
async def options_candidates():
    """
    Gestion des requêtes OPTIONS préflight pour l'endpoint /candidates.
    Nécessaire pour que les navigateurs puissent faire des requêtes cross-origin.
    """
    return Response(status_code=200, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true"
    })

# Seuil minimal configurable pour considérer qu'un match est acceptable
try:
    MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", "0.50"))
    logger.info("MIN_MATCH_SCORE valide dans l'environnement.")
except ValueError:
    MIN_MATCH_SCORE = 0.50
    logger.warning("MIN_MATCH_SCORE invalide dans l'environnement. Valeur par défaut 0.50 utilisée.")

OUT_OF_SCOPE_THRESHOLD = 0.25

TITLE_LEVEL_KEYWORDS = {
    "junior": ["junior", "debutant", "débutant", "beginner"],
    "intermediate": ["intermediaire", "intermédiaire", "confirmé", "confirme", "middle"],
    "senior": ["senior", "expérimenté", "experimente", "expert", "lead"],
}

TITLE_CONTRACT_KEYWORDS = {
    "internship": ["stage", "stagiaire", "intern"],
    "freelance": ["freelance", "independant", "indépendant"],
}

TECH_KEYWORDS = {
    "react": ["react", "reactjs", "react.js"],
    "node": ["node", "nodejs", "node.js"],
    "python": ["python"],
    "javascript": ["javascript", "js"],
    "typescript": ["typescript", "ts"],
    "java": ["java "],
    "data scientist": ["data scientist", "data science"],
    "devops": ["devops", "dev ops"],
}

# Mots-clés pour reconnaître les rôles orientés données / analyste
DATA_ROLE_KEYWORDS = [
    "data",
    "donnee",
    "donnée",
    "donnees",
    "données",
    "analyste",
    "analyst",
    "statisticien",
    "statistique",
    "business intelligence",
    "bi ",
    "reporting",
    "tableau de bord",
]

# Outils typiques de data / BI qu'on considère comme naturels pour ces rôles
DATA_TOOL_KEYWORDS = [
    "r",
    "rstudio",
    "power bi",
    "tableau",
    "qlik",
    "excel",
    "sql",
    "sas",
    "stata",
    "python",
    "pandas",
]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in normalized if not unicodedata.category(c).startswith("M"))


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


def _status_from_similarity(score: float) -> str:
    if score >= 0.55:
        return "ok"
    if score >= 0.35:
        return "warning"
    return "incoherent"


def _extract_title_keywords(title: str) -> dict:
    text = _normalize_text(title)
    level = None
    for key, patterns in TITLE_LEVEL_KEYWORDS.items():
        if any(p in text for p in patterns):
            level = key
            break
    contract = None
    for key, patterns in TITLE_CONTRACT_KEYWORDS.items():
        if any(p in text for p in patterns):
            contract = key
            break
    techs: list[str] = []
    for tech, patterns in TECH_KEYWORDS.items():
        if any(p in text for p in patterns):
            techs.append(tech)
    return {"level": level, "contract": contract, "techs": techs}


def _compute_missing_techs(title_techs: list[str], skills: list[str], description: str) -> list[str]:
    if not title_techs:
        return []
    skills_text = _normalize_text(" ".join(skills))
    desc_text = _normalize_text(description)
    missing: list[str] = []
    for tech in title_techs:
        if tech not in skills_text and tech not in desc_text:
            missing.append(tech)
    return missing


def _split_items(text: str) -> list[str]:
    cleaned = text.replace("\u2022", " ")
    parts = re.split(r"[\n;,\-\u2013\u2014]", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _is_trivial_requirement_item(text: str) -> bool:
    """Retourne True pour les items très génériques à ignorer dans l'analyse (ex: "aucune")."""
    normalized = _normalize_text(text)
    if not normalized:
        return True
    if normalized in {"aucune", "aucun", "neant", "néant", "rien"}:
        return True
    if "aucune experience" in normalized or "aucune expérience" in normalized:
        return True
    return False

@router.post("/candidates", tags=["Candidates"])
async def add_candidate(candidate: Candidate):
    task = process_candidate_task.delay(candidate.dict())
    logger.info(f"Tâche de traitement pour le candidat ID {candidate.id} envoyée à Celery. Task ID: {task.id}")
    return {"status": "Profil en cours de traitement", "task_id": task.id}

@router.post("/match", tags=["Matching"])
async def match_job(job: Job):
    # Normaliser le texte pour l'embedding selon le nouveau schéma Job
    parts = [
        f"Titre: {job.title}",
        f"Description du poste: {job.description}",
        f"Responsabilités: {job.responsibilities}",
        f"Exigences: {job.requirements}",
        f"Avantages: {job.benefits}",
        f"Type de poste: {job.jobType}",
        f"Niveau d'expérience: {job.experienceLevel}",
        f"Localisation: {job.location}",
        f"Télétravail autorisé: {job.remoteAllowed}",
        f"Mis en avant: {job.featured}",
        f"Compétences: {', '.join(job.skills or [])}",
    ]
    job_text_structured = "\n".join(parts)
    job_text = job_text_structured.lower()
    job_embedding = list(nlp_service.generate_embedding(job_text))
    logger.info(f"Recherche de correspondances pour l'offre d'emploi: {job.title}")
    # Construire un filtre Pinecone pour réduire le bruit
    metadata_filter = {"open_to_work": True}
    matches = search_similar_vectors(job_embedding, top_k=20, metadata_filter=metadata_filter)
    logger.info(f"Trouvé {len(matches)} correspondances depuis Pinecone.")
    results = []
    for match in matches:
        metadata = match.metadata
        if metadata:
            candidate_id = match.id
            similarity_score = match.score
            # Normaliser les compétences pour une comparaison insensible à la casse et aux espaces
            job_skills_norm = {s.strip().lower() for s in (job.skills or [])}
            candidate_skills = [tech.split(':')[0] for tech in metadata.get("technologies", [])]
            candidate_skills_norm = {s.strip().lower() for s in candidate_skills}
            skill_match_score = (
                len(job_skills_norm & candidate_skills_norm) / len(job_skills_norm)
            ) if job_skills_norm else 0
            final_score = 0.7 * similarity_score + 0.3 * skill_match_score
            # Filtrer selon le seuil minimal
            if final_score >= MIN_MATCH_SCORE:
                results.append({
                    "candidate_id": candidate_id,
                    "score": round(final_score, 2),
                    "breakdown": {
                        "similarity": round(similarity_score, 2),
                        "skill_match": round(skill_match_score, 2)
                    }
                })
            else:
                logger.debug(
                    "Candidat %s filtré: score final %.3f < seuil %.2f (sim=%.3f, skills=%.3f)",
                    candidate_id, final_score, MIN_MATCH_SCORE, similarity_score, skill_match_score
                )
    results.sort(key=lambda x: x['score'], reverse=True)
    logger.info("Nombre de matches après filtrage (seuil %.2f): %d", MIN_MATCH_SCORE, len(results))
    # Mapper vers le format demandé: rang (1-based), id, score final
    formatted = [
        {"rank": idx + 1, "candidate_id": item["candidate_id"], "score": item["score"]}
        for idx, item in enumerate(results)
    ]
    return formatted


@router.post("/job/coherence", tags=["Matching"])
async def check_job_coherence(job: Job):
    title_text = (job.title or "").strip()
    desc_text = (job.description or "").strip()
    responsibilities_text = (job.responsibilities or "").strip()
    requirements_text = (job.requirements or "").strip()
    benefits_text = (job.benefits or "").strip()
    skills_list = job.skills or []
    skills_text = ", ".join(skills_list)

    reference_text = f"{title_text}. {desc_text}" if desc_text else title_text
    reference_vec = nlp_service.generate_embedding(reference_text.lower())
    normalized_ref = _normalize_text(reference_text)
    is_data_role = any(kw in normalized_ref for kw in DATA_ROLE_KEYWORDS)

    title_vec = nlp_service.generate_embedding(title_text.lower())
    desc_vec = nlp_service.generate_embedding(desc_text.lower()) if desc_text else []
    skills_vec = nlp_service.generate_embedding(skills_text.lower()) if skills_text else []

    sim_title_desc = _cosine_similarity(title_vec, desc_vec) if desc_vec else 0.0
    # On compare les compétences au texte de référence (titre + description) pour une vision plus globale
    sim_title_skills = _cosine_similarity(reference_vec, skills_vec) if skills_text else 0.0

    sections: dict = {}
    issues: list[dict] = []

    # Description
    if not desc_text:
        sections["description"] = {
            "similarity": 0.0,
            "status": "incoherent",
            "issues": ["missing_description"],
        }
        issues.append({
            "code": "missing_description",
            "message": "La description du poste est vide, impossible de vérifier la cohérence avec le titre.",
        })
    else:
        status_desc = _status_from_similarity(sim_title_desc)
        sections["description"] = {
            "similarity": round(sim_title_desc, 4),
            "status": status_desc,
            "issues": [] if status_desc == "ok" else ["title_desc_low_similarity"],
        }
        if status_desc != "ok":
            message = (
                "La description pourrait être précisée pour mieux refléter le titre du poste."
                if status_desc == "warning"
                else "La description ne semble pas décrire le même type de poste que le titre."
            )
            issues.append({
                "code": "title_desc_low_similarity",
                "message": message,
            })

    # Compétences
    if not skills_list:
        sections["skills"] = {
            "similarity": 0.0,
            "status": "incoherent",
            "issues": ["missing_skills"],
            "missing_keywords": [],
        }
        issues.append({
            "code": "missing_skills",
            "message": "Aucune compétence n'est renseignée pour ce poste.",
        })
    else:
        status_skills = _status_from_similarity(sim_title_skills)
        title_info = _extract_title_keywords(title_text)
        missing_techs = _compute_missing_techs(title_info.get("techs", []), skills_list, desc_text)

        normalized_skills = [_normalize_text(s) for s in skills_list]
        has_data_tool = any(
            any(tool in s for tool in DATA_TOOL_KEYWORDS)
            for s in normalized_skills
        )

        sections["skills"] = {
            "similarity": round(sim_title_skills, 4),
            "status": status_skills,
            "issues": [],
            "missing_keywords": missing_techs,
        }

        # Pour les rôles data avec des outils data typiques, ne pas considérer les compétences comme
        # totalement incohérentes même si la similarité numérique est un peu faible.
        if is_data_role and has_data_tool and status_skills == "incoherent":
            status_skills = "warning"
            sections["skills"]["status"] = status_skills

        # N'ajouter le message de faible similarité que si les compétences semblent vraiment déconnectées
        # ET qu'on n'est pas dans un cas classique data/BI avec des outils standards.
        if status_skills != "ok" and not (is_data_role and has_data_tool):
            issues.append({
                "code": "title_skills_low_similarity",
                "message": "Les compétences listées ne correspondent pas fortement au titre du poste.",
            })

        if missing_techs:
            issues.append({
                "code": "missing_skill_keyword",
                "message": "Le titre mentionne des technologies qui n'apparaissent pas dans les compétences ni la description : "
                           + ", ".join(missing_techs),
            })

        out_of_scope_skills: list[str] = []
        if skills_list:
            for skill, skill_norm in zip(skills_list, normalized_skills):
                # Pour les rôles data avec des outils data typiques, ne jamais marquer ces outils
                # comme "hors sujet" même si la similarité brute est basse.
                if is_data_role and any(tool in skill_norm for tool in DATA_TOOL_KEYWORDS):
                    continue
                skill_vec_item = nlp_service.generate_embedding(skill.lower())
                score_item = _cosine_similarity(reference_vec, skill_vec_item)
                if score_item < OUT_OF_SCOPE_THRESHOLD:
                    out_of_scope_skills.append(skill)
        sections["skills"]["out_of_scope"] = out_of_scope_skills
        if out_of_scope_skills:
            issues.append({
                "code": "out_of_scope_skills",
                "message": "Certaines compétences semblent hors sujet par rapport au titre et à la description : "
                           + ", ".join(out_of_scope_skills),
            })

    # Exigences (requirements) : détection des éléments hors sujet
    if requirements_text:
        req_items = _split_items(requirements_text)
        out_of_scope_requirements: list[str] = []
        for item in req_items:
            # Ignorer les items triviaux comme "aucune"
            if _is_trivial_requirement_item(item):
                continue
            item_vec = nlp_service.generate_embedding(item.lower())
            score_item = _cosine_similarity(reference_vec, item_vec)
            if score_item < OUT_OF_SCOPE_THRESHOLD:
                out_of_scope_requirements.append(item)

        sections["requirements"] = {
            "status": "ok" if not out_of_scope_requirements else "warning",
            "issues": [] if not out_of_scope_requirements else ["out_of_scope_requirements"],
            "out_of_scope": out_of_scope_requirements,
        }
        if out_of_scope_requirements:
            issues.append({
                "code": "out_of_scope_requirements",
                "message": "Certaines exigences semblent hors sujet par rapport au titre et à la description : "
                           + "; ".join(out_of_scope_requirements),
            })

    # Contrat et niveau d'expérience
    title_info = _extract_title_keywords(title_text)
    level_in_title = title_info.get("level")
    contract_in_title = title_info.get("contract")

    # Contrat
    if contract_in_title:
        sections.setdefault("contract", {"status": "ok", "issues": []})
        if not job.jobType:
            sections["contract"]["status"] = "warning"
            sections["contract"].setdefault("issues", []).append("contract_unspecified")
            issues.append({
                "code": "contract_unspecified",
                "message": "Le titre évoque un type de contrat mais aucun type n'est sélectionné pour l'offre.",
            })
        elif job.jobType != contract_in_title:
            sections["contract"]["status"] = "incoherent"
            sections["contract"].setdefault("issues", []).append("contract_mismatch_with_title")
            issues.append({
                "code": "contract_mismatch_with_title",
                "message": "Le titre évoque un type de contrat différent de celui sélectionné pour l'offre.",
            })

    # Niveau d'expérience
    if level_in_title:
        sections.setdefault("experience", {"status": "ok", "issues": []})
        if not job.experienceLevel:
            sections["experience"]["status"] = "warning"
            sections["experience"].setdefault("issues", []).append("experience_unspecified")
            issues.append({
                "code": "experience_unspecified",
                "message": "Le titre évoque un niveau (junior/senior) mais aucun niveau d'expérience n'est sélectionné.",
            })
        elif _normalize_text(job.experienceLevel) != level_in_title:
            sections["experience"]["status"] = "warning"
            sections["experience"].setdefault("issues", []).append("experience_mismatch_with_title")
            issues.append({
                "code": "experience_mismatch_with_title",
                "message": "Le niveau d'expérience sélectionné ne correspond pas au niveau évoqué dans le titre.",
            })

    # Score global pondéré : description plus importante que les compétences
    sims: list[float] = []
    weights: list[float] = []
    if desc_text:
        sims.append(sim_title_desc)
        weights.append(0.6)
    if skills_list:
        sims.append(sim_title_skills)
        weights.append(0.4)

    if sims:
        weighted_sum = sum(s * w for s, w in zip(sims, weights))
        total_weight = sum(weights) or 1.0
        global_score = float(weighted_sum / total_weight)
    else:
        global_score = 0.0

    has_incoherent_section = any(
        isinstance(v, dict) and v.get("status") == "incoherent" for v in sections.values()
    )
    # Seuil légèrement plus permissif pour considérer l'offre globalement cohérente
    is_consistent = global_score >= 0.4 and not has_incoherent_section

    return {
        "is_consistent": is_consistent,
        "global_score": round(global_score, 4),
        "similarities": {
            "title_description": round(sim_title_desc, 4) if desc_text else None,
            "title_skills": round(sim_title_skills, 4) if skills_list else None,
        },
        "sections": sections,
        "issues": issues,
    }
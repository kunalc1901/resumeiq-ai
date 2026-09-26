"""Helpers for parsing and normalizing LLM resume output."""

import ast
import json

_OVERALL_MAXES = {
    "content_quality": 25,
    "experience_impact": 20,
    "skills_relevance": 15,
    "structure_clarity": 15,
    "projects_education_certifications": 10,
    "professionalism_consistency": 10,
    "completeness": 5,
}

_ATS_MAXES = {
    "structure": 25,
    "keyword_terminology": 20,
    "experience_skills_parsability": 15,
    "formatting_consistency": 15,
    "content_organization": 10,
    "contact_parsability": 5,
    "date_consistency": 5,
}


def parse_llm_dict(text: str) -> dict:
    """Extract the dictionary/JSON object from the LLM's output text."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No dictionary found in LLM output")
    payload = text[start : end + 1]
    try:
        return json.loads(payload)
    except ValueError:
        return ast.literal_eval(payload)


def has_real_value(value) -> bool:
    """Return True if a field holds a real value (not None / 'None' / empty)."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in ("", "none", "null", "n/a", "na")
    if isinstance(value, dict):
        return any(has_real_value(v) for v in value.values())
    return bool(value)


def merge_orphan_projects(work_experience: list) -> list:
    """Merge entries without a real designation/duration into the previous company.

    Sub-projects the LLM still emits as separate elements get their details
    appended to the parent company's work_summary instead of being dropped.
    """
    merged = []
    for item in work_experience:
        is_real_company = has_real_value(item.get("designation")) and has_real_value(
            item.get("duration")
        )
        if is_real_company:
            merged.append(dict(item))
            continue
        if merged:
            prev = merged[-1]
            extra = item.get("work_summary", "").strip()
            if extra:
                prev["work_summary"] = (
                    prev.get("work_summary", "").strip() + " " + extra
                ).strip()
        else:
            merged.append(dict(item))
    return merged


def _clamp(value, low, high):
    return max(low, min(high, value))


def _normalize_breakdown_score(score, breakdown, maxes):
    """Make a (score, breakdown) pair internally consistent.

    Small LLMs often return a total that does not match the sum of the
    category scores. Clamp every category to [0, max] and recompute the
    top-level score as the sum of the categories, so the stored numbers
    always agree.
    """
    if isinstance(breakdown, dict):
        clamped = {}
        for key, max_val in maxes.items():
            try:
                clamped[key] = _clamp(int(breakdown.get(key, 0)), 0, max_val)
            except (TypeError, ValueError):
                clamped[key] = 0
        return sum(clamped.values()), clamped
    if score is not None:
        try:
            return _clamp(int(score), 0, 100), None
        except (TypeError, ValueError):
            return None, None
    return None, None


def build_structured_profile(analysis) -> str:
    """Flatten a ResumeAnalysis into a compact text block for the LLM.

    Used by the job-matching flow so the model can do a structured
    comparison of skills, experience, projects, and education.
    """
    lines = []
    lines.append(f"Name: {analysis.name}")
    if analysis.summary:
        lines.append(f"Summary: {analysis.summary}")
    if analysis.college or analysis.degree:
        lines.append(
            f"Education: {analysis.degree or ''} at {analysis.college or ''}".strip()
        )

    lines.append("Skills:")
    for category, skills in (analysis.skills or {}).items():
        lines.append(f"  - {category}: {', '.join(skills)}")

    lines.append("Work experience:")
    for exp in analysis.work_experience or []:
        duration = ""
        if exp.duration:
            duration = f" ({exp.duration.from_} - {exp.duration.to})"
        lines.append(
            f"  - {exp.designation} at {exp.company}{duration}: {exp.work_summary}"
        )

    return "\n".join(lines)


def normalize_score_fields(data: dict) -> dict:
    """Recompute overall_score/ats_score from their breakdowns (and clamp ranges)."""
    overall_score, score_breakdown = _normalize_breakdown_score(
        data.get("overall_score"), data.get("score_breakdown"), _OVERALL_MAXES
    )
    ats_score, ats_score_breakdown = _normalize_breakdown_score(
        data.get("ats_score"), data.get("ats_score_breakdown"), _ATS_MAXES
    )
    data["overall_score"] = overall_score
    data["score_breakdown"] = score_breakdown
    data["ats_score"] = ats_score
    data["ats_score_breakdown"] = ats_score_breakdown

    return data

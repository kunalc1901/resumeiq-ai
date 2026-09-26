from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Duration(BaseModel):
    """Duration of a work experience. The MongoDB field is 'from' (Python keyword)."""

    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None

    model_config = {"populate_by_name": True}


class WorkExperience(BaseModel):
    """A single company the candidate worked at."""

    company: str
    designation: str
    duration: Optional[Duration] = None
    work_summary: str


class ScoreBreakdown(BaseModel):
    """Per-dimension points that sum to the overall resume score."""

    content_quality: int = 0
    experience_impact: int = 0
    skills_relevance: int = 0
    structure_clarity: int = 0
    projects_education_certifications: int = 0
    professionalism_consistency: int = 0
    completeness: int = 0


class AtsScoreBreakdown(BaseModel):
    """Per-dimension points that sum to the ATS compatibility score."""

    structure: int = 0
    keyword_terminology: int = 0
    experience_skills_parsability: int = 0
    formatting_consistency: int = 0
    content_organization: int = 0
    contact_parsability: int = 0
    date_consistency: int = 0


class ResumeAnalysis(BaseModel):
    """Structured data extracted from a processed resume."""

    name: str
    email: Optional[str] = None
    pno: Optional[str] = None
    summary: Optional[str] = None
    college: Optional[str] = None
    degree: Optional[str] = None
    work_experience: List[WorkExperience] = Field(default_factory=list)
    skills: Dict[str, List[str]] = Field(default_factory=dict)

    # ResumeIQ overall scoring (0-100)
    overall_score: Optional[int] = Field(default=None, ge=0, le=100)
    score_breakdown: Optional[ScoreBreakdown] = Field(default=None)
    score_summary: Optional[str] = Field(default=None)
    strengths: Optional[List[str]] = Field(default=None)
    improvements: Optional[List[str]] = Field(default=None)

    # ResumeIQ ATS compatibility scoring (0-100)
    ats_score: Optional[int] = Field(default=None, ge=0, le=100)
    ats_score_breakdown: Optional[AtsScoreBreakdown] = Field(default=None)
    ats_summary: Optional[str] = Field(default=None)
    ats_strengths: Optional[List[str]] = Field(default=None)
    ats_improvements: Optional[List[str]] = Field(default=None)


class ResumeModel(BaseModel):
    """Represents a resume document stored in MongoDB.

    Created by the frontend/SWE app on upload (carrying ``user_id`` and
    ``file_name`` for the S3 object); the backend fills ``analysis`` after
    processing. The id field holds the hex string of the ObjectId.
    """

    id: Optional[str] = None
    user_id: Optional[str] = None
    file_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    analysis: Optional[ResumeAnalysis] = None
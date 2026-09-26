from datetime import datetime

from pydantic import BaseModel, Field


class Duration(BaseModel):
    """Duration of a work experience. The MongoDB field is 'from' (Python keyword)."""

    from_: str | None = Field(default=None, alias="from")
    to: str | None = None

    model_config = {"populate_by_name": True}


class WorkExperience(BaseModel):
    """A single company the candidate worked at."""

    company: str
    designation: str
    duration: Duration | None = None
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
    email: str | None = None
    pno: str | None = None
    summary: str | None = None
    college: str | None = None
    degree: str | None = None
    work_experience: list[WorkExperience] = Field(default_factory=list)
    skills: dict[str, list[str]] = Field(default_factory=dict)

    # ResumeIQ overall scoring (0-100)
    overall_score: int | None = Field(default=None, ge=0, le=100)
    score_breakdown: ScoreBreakdown | None = Field(default=None)
    score_summary: str | None = Field(default=None)
    strengths: list[str] | None = Field(default=None)
    improvements: list[str] | None = Field(default=None)

    # ResumeIQ ATS compatibility scoring (0-100)
    ats_score: int | None = Field(default=None, ge=0, le=100)
    ats_score_breakdown: AtsScoreBreakdown | None = Field(default=None)
    ats_summary: str | None = Field(default=None)
    ats_strengths: list[str] | None = Field(default=None)
    ats_improvements: list[str] | None = Field(default=None)


class ResumeModel(BaseModel):
    """Represents a resume document stored in MongoDB.

    Created by the frontend/SWE app on upload (carrying ``user_id`` and
    ``file_name`` for the S3 object); the backend fills ``analysis`` after
    processing. The id field holds the hex string of the ObjectId.
    """

    id: str | None = None
    user_id: str | None = None
    file_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    analysis: ResumeAnalysis | None = None

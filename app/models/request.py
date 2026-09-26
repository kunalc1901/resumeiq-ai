from pydantic import BaseModel


class ResumeProcessRequest(BaseModel):
    """Request body for processing an existing resume (created on upload)."""

    token: str
    resume_id: str


class ChatRequest(BaseModel):
    """Request body for asking a question about a processed resume."""

    token: str
    resume_id: str
    question: str


class JobMatchRequest(BaseModel):
    """Request body for matching resume to a job."""

    token: str
    resume_id: str
    job_description: str = ""

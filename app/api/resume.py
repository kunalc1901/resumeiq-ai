from fastapi import APIRouter, Request

from models.request import ChatRequest, JobMatchRequest, ResumeProcessRequest
from services.resume_service import (
    ask_resume,
    match_resume_with_job,
    process_new_resume,
)

router = APIRouter()


@router.post("/process", status_code=200)
def process_resume(request: ResumeProcessRequest, http_request: Request):
    """Process a new resume and return its resume_id."""
    resume_id = process_new_resume(request, http_request.state.user)
    return {"resume_id": resume_id}


@router.post("/ask")
def ask_question(request: ChatRequest, http_request: Request):
    """Answer a question about a specific resume."""
    answer = ask_resume(request.question, http_request.state.user, request.resume_id)
    return {"answer": answer}


@router.post("/job-match")
def match_job(request: JobMatchRequest, http_request: Request):
    """Matches a resume to a specific job description."""
    return match_resume_with_job(
        http_request.state.user, request.resume_id, request.job_description
    )

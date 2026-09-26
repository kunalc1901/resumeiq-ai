import json
import time
from collections import OrderedDict
from typing import Any

from core.exceptions import BadRequestException, NotFoundException
from core.prompts import RESUME_EXTRACTION_PROMPT, get_job_match_prompt
from database.mongodb import get_collection
from models.request import ResumeProcessRequest
from models.resume import ResumeAnalysis
from repositories.resume_repository import ResumeRepository
from services.llm import ask_llm, ask_llm_full_text
from utils.aws import fetch_pdf_bytes_from_s3
from utils.chunker import chunk_document
from utils.pdf_reader import read_pdf
from utils.resume_utils import (
    build_structured_profile,
    merge_orphan_projects,
    normalize_score_fields,
    parse_llm_dict,
)
from utils.vector_store import VectorStore


def ask_resume(question: str, user: dict, resume_id: str) -> str:
    """Answer a question about a specific resume using its indexed chunks."""
    store = VectorStore()
    chunks = store.search(question, user_id=user["sub"], resume_id=resume_id, top_k=5)
    if not chunks:
        return f"No resume data has been indexed for this resume ({resume_id}). Process it first."
    return ask_llm(question, chunks)


def process_new_resume(request: ResumeProcessRequest, user: dict) -> str:
    """Analyze a resume and write the extracted data to its Mongo document."""

    repository = ResumeRepository(get_collection())

    resume = repository.find_by_id(request.resume_id, user["sub"])
    if resume is None or not resume.file_name:
        raise NotFoundException(
            f"Resume {request.resume_id} not found for this user. Create the resume object first."
        )

    pdf_key = f"unzipped/6a7c71a6779ce5a3090ce92c/{user['sub']}/{resume.file_name}"
    print(
        f"[0/6] Authenticated user: {user.get('email')} ({user.get('sub')})", flush=True
    )

    print(f"[1/6] Fetching PDF from S3: {pdf_key}", flush=True)
    pdf_bytes = fetch_pdf_bytes_from_s3(pdf_key)
    print(f"      >> {len(pdf_bytes)} bytes fetched", flush=True)

    print("[2/6] Reading PDF pages...", flush=True)
    pages = read_pdf(pdf_bytes)
    print(f"      >> {len(pages)} pages read", flush=True)

    full_text = "\n\n".join(page["text"] for page in pages)
    print(
        f"[3/6] Sending full resume text to LLM ({len(full_text)} chars)...", flush=True
    )

    extracted = ask_llm_full_text(RESUME_EXTRACTION_PROMPT, full_text)
    print("[4/6] Parsing LLM output...", flush=True)

    data = parse_llm_dict(extracted)
    print("[5/6] Merging sub-projects into their parent company...", flush=True)

    data["work_experience"] = merge_orphan_projects(data.get("work_experience", []))

    print("\nExtracted data (JSON):", flush=True)
    print(json.dumps(data, indent=2), flush=True)

    data = normalize_score_fields(data)
    print(
        f"\nNormalized scores -> overall: {data.get('overall_score')} / 100, "
        f"ATS: {data.get('ats_score')} / 100",
        flush=True,
    )

    analysis = ResumeAnalysis.model_validate(data)
    repository.update_analysis(request.resume_id, user["sub"], analysis)
    print(
        f"[6/6] Analysis saved to MongoDB (collection: resumes): {request.resume_id}",
        flush=True,
    )

    chunks = chunk_document(pages)
    store = VectorStore()
    store.add_chunks(chunks, user["sub"], request.resume_id)
    print(
        f"      >> {len(chunks)} chunks indexed for resume {request.resume_id}",
        flush=True,
    )

    return request.resume_id


# ============================================================
# JOB REQUIREMENT EXTRACTION
# ============================================================


def extract_job_requirements(
    job_description: str,
) -> list[dict[str, Any]]:
    """
    Extract atomic, structured requirements from a job description.

    This function ONLY extracts requirements.
    It does not perform resume matching or scoring.
    """

    if not job_description or not job_description.strip():
        raise BadRequestException("job_description is required.")

    prompt = """
You are ResumeIQ's Job Description Requirement Extraction Engine.

Analyze the provided job description and extract its meaningful,
atomic requirements.

Your task is ONLY to extract requirements.
Do NOT compare against a resume.
Do NOT score a candidate.
Do NOT make hiring predictions.

------------------------------------------------------------
REQUIREMENT EXTRACTION
------------------------------------------------------------

Break compound requirements into separate atomic requirements.

Example:

"Build scalable backend services using Node.js, MongoDB and AWS."

Should produce separate requirements such as:

Node.js backend development
MongoDB
AWS
Scalable backend services

For every requirement determine:

1. category
2. requirement
3. priority
4. importance
5. searchQuery

Allowed categories:

SKILL
RESPONSIBILITY
EXPERIENCE
EDUCATION
CERTIFICATION
DOMAIN
SOFT_SKILL
TOOL

Allowed priorities:

REQUIRED
PREFERRED
GENERAL

Importance:

Integer from 1 to 10.
10 = extremely important / mandatory / central to the role.
1 = minor / low importance.

------------------------------------------------------------
PRIORITY RULES
------------------------------------------------------------

Use REQUIRED when the JD explicitly indicates:

required
must have
mandatory
essential
minimum
need to have

Use PREFERRED when the JD indicates:

preferred
nice to have
bonus
desirable
plus

Use GENERAL when priority is unclear.

Do not invent priority when the JD does not provide enough information.

------------------------------------------------------------
SEARCH QUERY
------------------------------------------------------------

For every requirement generate a concise semantic search query
that can be used against a resume vector store.

The query should retrieve evidence that could demonstrate
the requirement.

Examples:

Requirement:
"Node.js backend development"

Search query:
"Node.js backend REST API development Express server experience"

Requirement:
"3+ years of backend experience"

Search query:
"backend software engineering employment history years experience responsibilities"

Requirement:
"Bachelor's degree in Computer Science"

Search query:
"education bachelor's degree computer science university"

Requirement:
"Experience leading engineering teams"

Search query:
"engineering team leadership management mentoring lead responsibilities"

------------------------------------------------------------
IMPORTANT RULES
------------------------------------------------------------

Preserve the actual meaning of the JD.
Do not invent requirements.
Do not duplicate requirements.
Separate explicitly listed technologies.
Preserve explicit experience requirements.
Preserve explicit education requirements.
Preserve certifications.
Preserve important responsibilities.
Do not treat related technologies as identical.
Do not add requirements that are merely implied without reasonable textual support.

Return ONLY valid JSON.

Required output:

{
  "requirements": [
    {
      "id": "REQ-001",
      "category": "SKILL",
      "requirement": "Node.js backend development",
      "priority": "REQUIRED",
      "importance": 10,
      "searchQuery": "Node.js backend REST API development Express server experience"
    }
  ]
}

Final rules:

Every requirement must have a unique id.
Requirements must be atomic.
Do not duplicate requirements.
importance must be between 1 and 10.
searchQuery must be useful for semantic resume retrieval.
Return JSON only.
"""

    raw = ask_llm_full_text(
        prompt,
        f"JOB DESCRIPTION:\n\n{job_description.strip()}",
    )

    try:
        result = parse_llm_dict(raw)
    except (ValueError, SyntaxError) as exc:
        raise BadRequestException(f"Failed to parse job requirements: {exc}") from exc

    requirements = result.get("requirements")

    if not isinstance(requirements, list):
        raise BadRequestException("LLM returned invalid job requirements format.")

    allowed_categories = {
        "SKILL",
        "RESPONSIBILITY",
        "EXPERIENCE",
        "EDUCATION",
        "CERTIFICATION",
        "DOMAIN",
        "SOFT_SKILL",
        "TOOL",
    }

    allowed_priorities = {
        "REQUIRED",
        "PREFERRED",
        "GENERAL",
    }

    cleaned: list[dict[str, Any]] = []

    for index, item in enumerate(requirements, start=1):
        if not isinstance(item, dict):
            continue

        requirement = str(item.get("requirement", "")).strip()

        search_query = str(item.get("searchQuery", "")).strip()

        if not requirement or not search_query:
            continue

        category = str(item.get("category", "SKILL")).upper()

        priority = str(item.get("priority", "GENERAL")).upper()

        if category not in allowed_categories:
            category = "SKILL"

        if priority not in allowed_priorities:
            priority = "GENERAL"

        try:
            importance = int(item.get("importance", 5))
        except (TypeError, ValueError):
            importance = 5

        importance = max(
            1,
            min(10, importance),
        )

        cleaned.append(
            {
                "id": str(item.get("id") or f"REQ-{index:03d}"),
                "category": category,
                "requirement": requirement,
                "priority": priority,
                "importance": importance,
                "searchQuery": search_query,
            }
        )

    if not cleaned:
        raise BadRequestException(
            "Could not extract meaningful requirements from job description."
        )

    return cleaned


# ============================================================
# CATEGORY-AWARE RETRIEVAL QUERY
# ============================================================


def build_retrieval_query(
    requirement: dict[str, Any],
) -> str:
    """
    Adds category-specific context to the LLM-generated
    semantic search query.
    """

    base_query = requirement["searchQuery"]

    category_context = {
        "SKILL": (
            "skills technologies frameworks programming languages "
            "tools databases cloud technical experience"
        ),
        "RESPONSIBILITY": (
            "work responsibilities duties achievements "
            "professional experience implementation"
        ),
        "EXPERIENCE": (
            "employment history job titles dates years "
            "professional experience responsibilities"
        ),
        "EDUCATION": ("education degree university college academic qualification"),
        "CERTIFICATION": (
            "certifications licenses credentials professional qualifications"
        ),
        "DOMAIN": ("industry domain experience projects business domain knowledge"),
        "SOFT_SKILL": (
            "leadership communication teamwork collaboration "
            "mentoring management professional experience"
        ),
        "TOOL": ("software tools platforms technologies professional experience"),
    }

    context = category_context.get(
        requirement["category"],
        "",
    )

    return f"{base_query}. {context}"


# ============================================================
# RETRIEVE RESUME EVIDENCE
# ============================================================


def retrieve_requirement_evidence(
    requirements: list[dict[str, Any]],
    user_id: str,
    resume_id: str,
    per_requirement_top_k: int = 4,
    max_total_chunks: int = 30,
) -> list[dict[str, Any]]:
    """
    Retrieve targeted resume evidence for every job requirement.

    Each requirement gets its own semantic retrieval query.

    Results are deduplicated across requirements so the same
    resume chunk is not repeatedly sent to the LLM.
    """

    if not requirements:
        return []

    store = VectorStore()

    unique_chunks: OrderedDict[str, dict[str, Any]] = OrderedDict()

    requirement_evidence: list[dict[str, Any]] = []

    for requirement in requirements:
        requirement_id = requirement["id"]

        search_query = build_retrieval_query(requirement)

        try:
            chunks = store.search(
                search_query,
                user_id=user_id,
                resume_id=resume_id,
                top_k=per_requirement_top_k,
            )

        except Exception as exc:  # noqa: BLE001 - vector search failures are non-fatal
            print(
                f"[job-match] retrieval failed for {requirement_id}: {exc}",
                flush=True,
            )

            chunks = []

        evidence_items = []

        for chunk in chunks:
            meta = (
                chunk.get(
                    "meta",
                    {},
                )
                or {}
            )

            content = str(
                chunk.get(
                    "content",
                    "",
                )
            ).strip()

            if not content:
                continue

            page = meta.get("page")

            chunk_id = (
                meta.get("chunk_id")
                or meta.get("chunkId")
                or meta.get("_id")
                or meta.get("id")
            )

            # Fallback when the vector store does not provide
            # a stable chunk ID.
            dedupe_key = str(chunk_id or f"{resume_id}:{page}:{content}")

            evidence = {
                "chunkId": dedupe_key,
                "page": page,
                "content": content,
            }

            evidence_items.append(evidence)

            if dedupe_key not in unique_chunks:
                unique_chunks[dedupe_key] = {
                    "chunkId": dedupe_key,
                    "page": page,
                    "content": content,
                }

        requirement_evidence.append(
            {
                "requirementId": requirement_id,
                "requirement": requirement["requirement"],
                "category": requirement["category"],
                "priority": requirement["priority"],
                "importance": requirement["importance"],
                "evidence": evidence_items,
            }
        )

    # Prevent huge context from reaching the LLM.
    unique_evidence = list(unique_chunks.values())[:max_total_chunks]

    allowed_chunk_ids = {item["chunkId"] for item in unique_evidence}

    # Keep only evidence that survived the global limit.
    for item in requirement_evidence:
        item["evidence"] = [
            evidence
            for evidence in item["evidence"]
            if evidence["chunkId"] in allowed_chunk_ids
        ]

    print(
        f"[job-match] requirements="
        f"{len(requirements)}, "
        f"unique_evidence_chunks="
        f"{len(unique_evidence)}",
        flush=True,
    )

    return requirement_evidence


# ============================================================
# BUILD LLM EVIDENCE CONTEXT
# ============================================================


def build_requirement_evidence_context(
    requirement_evidence: list[dict[str, Any]],
) -> str:
    """
    Convert retrieved requirement evidence into a clean,
    LLM-readable context.
    """

    parts: list[str] = []

    for item in requirement_evidence:
        parts.append(
            f"REQUIREMENT {item['requirementId']}\n"
            f"Requirement: {item['requirement']}\n"
            f"Category: {item['category']}\n"
            f"Priority: {item['priority']}\n"
            f"Importance: {item['importance']}\n"
        )

        evidence = item.get(
            "evidence",
            [],
        )

        if not evidence:
            parts.append("No targeted resume evidence was retrieved.\n")

        else:
            for chunk in evidence:
                page = chunk.get(
                    "page",
                    "unknown",
                )

                parts.append(
                    f"[Page {page} | Chunk {chunk['chunkId']}]\n{chunk['content']}\n"
                )

        parts.append("\n---\n")

    return "\n".join(parts)


def _log_job_match(message: str) -> None:
    """Print a timestamped [job-match] log line."""
    from datetime import datetime

    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[job-match] {ts} {message}", flush=True)


# ============================================================
# FINAL RESUME ↔ JOB MATCH
# ============================================================


def match_resume_with_job(
    user: dict,
    resume_id: str,
    job_description: str,
):
    """
    Match a resume against a job description.

    Pipeline:

    Job Description
        ↓
    Requirement Extraction
        ↓
    Requirement-wise Vector Retrieval
        ↓
    Structured Resume Profile
        ↓
    Evidence Aggregation
        ↓
    LLM Requirement-level Matching
        ↓
    Final Structured Result
    """

    _job_match_started = time.time()

    if not job_description or not job_description.strip():
        raise BadRequestException("job_description is required.")

    repository = ResumeRepository(get_collection())

    resume = repository.find_by_id(
        resume_id,
        user["sub"],
    )

    if resume is None:
        raise NotFoundException(f"Resume {resume_id} not found for this user.")

    if resume.analysis is None:
        raise NotFoundException(
            f"Resume {resume_id} has no analysis yet. Process it first."
        )

    # --------------------------------------------------------
    # 1. Extract atomic requirements
    # --------------------------------------------------------

    requirements = extract_job_requirements(job_description)

    # --------------------------------------------------------
    # 2. Retrieve targeted evidence
    # --------------------------------------------------------

    requirement_evidence = retrieve_requirement_evidence(
        requirements=requirements,
        user_id=user["sub"],
        resume_id=resume_id,
        per_requirement_top_k=4,
        max_total_chunks=30,
    )

    # --------------------------------------------------------
    # 3. Build structured resume profile
    # --------------------------------------------------------

    structured = build_structured_profile(resume.analysis)

    # --------------------------------------------------------
    # 4. Build evidence context
    # --------------------------------------------------------

    evidence_context = build_requirement_evidence_context(requirement_evidence)

    # --------------------------------------------------------
    # 5. Build final LLM context
    # --------------------------------------------------------

    full_context = (
        "STRUCTURED RESUME:\n"
        + structured
        + "\n\n"
        + "EXTRACTED JOB REQUIREMENTS:\n"
        + json.dumps(
            requirements,
            ensure_ascii=False,
            indent=2,
        )
        + "\n\n"
        + "TARGETED RESUME EVIDENCE:\n"
        + evidence_context
    )

    _log_job_match(
        f"resume={resume_id}, "
        f"requirements={len(requirements)}, "
        f"evidence_groups={len(requirement_evidence)}"
    )

    # --------------------------------------------------------
    # 6. Final matching prompt
    # --------------------------------------------------------

    job_match_prompt = get_job_match_prompt(job_description)

    requirements_json = json.dumps(
        requirements,
        ensure_ascii=False,
        indent=2,
    )

    _log_job_match(
        "context sizes -> "
        f"prompt={len(job_match_prompt)} chars, "
        f"structured={len(structured)} chars, "
        f"requirements_json={len(requirements_json)} chars, "
        f"evidence={len(evidence_context)} chars, "
        f"total_context={len(full_context)} chars, "
        f"est_total_tokens={(len(job_match_prompt) + len(full_context)) // 4}"
    )

    raw = ask_llm_full_text(
        job_match_prompt,
        full_context,
        num_predict=16384,
    )

    _log_job_match(f"LLM response -> {len(raw)} chars")

    # --------------------------------------------------------
    # 7. Parse structured JSON response
    # --------------------------------------------------------

    result = parse_llm_dict(raw)
    _log_job_match(f"total elapsed={time.time() - _job_match_started:.1f}s")

    return result

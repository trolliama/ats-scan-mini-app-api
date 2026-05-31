import uuid
from typing import Any

from fastapi import BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel

from src.agent import run_agent
from src.app import get_app
from src.logger import configure_logging, format_bytes, get_logger
from src.resume_parser import (
    extract_markdown_from_resume,
    validate_resume_filename,
)

configure_logging()

logger = get_logger("resume")
app = get_app()

JobStatus = str  # pending | running | completed | failed

jobs: dict[str, dict[str, Any]] = {}


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: str | None = None
    error: str | None = None


def process_resume(job_id: str, resume_content: bytes, filename: str) -> None:
    log = logger.bind(job_id=job_id)
    log.info("Processing started", size=format_bytes(len(resume_content)))
    jobs[job_id]["status"] = "running"

    try:
        markdown = extract_markdown_from_resume(resume_content, filename)
        print(markdown)
        result = run_agent(markdown)
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
        log.info("Processing completed")
    except Exception as exc:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(exc)
        log.error("Processing failed", exc_info=True)


@app.post("/resume/analyze", response_model=JobCreateResponse)
async def send_resume(resume: UploadFile, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    resume_content = await resume.read()
    log = logger.bind(job_id=job_id)

    filename = resume.filename or ""

    if not resume_content:
        log.warning("Empty upload rejected", file=filename)
        raise HTTPException(status_code=400, detail="Empty resume upload")

    try:
        validate_resume_filename(filename)
    except ValueError as exc:
        log.warning("Unsupported format rejected", file=filename)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log.info(
        "Upload accepted",
        file=filename,
        size=format_bytes(len(resume_content)),
    )

    jobs[job_id] = {
        "status": "pending",
        "result": None,
        "error": None,
    }

    background_tasks.add_task(process_resume, job_id, resume_content, filename)

    return JobCreateResponse(
        job_id=job_id,
        status="pending",
        message="Resume processing started",
    )


@app.get("/resume/analyze/{job_id}", response_model=JobStatusResponse)
async def get_resume_job_status(job_id: str):
    job = jobs.get(job_id)
    log = logger.bind(job_id=job_id)

    if job is None:
        log.warning("Job not found")
        raise HTTPException(status_code=404, detail="Job not found")

    log.info("Status returned", status=job["status"])

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        error=job.get("error"),
    )

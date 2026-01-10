"""API router for background job management.

Provides endpoints for:
- Submitting jobs
- Checking job status
- Listing jobs
- Cancelling jobs

All endpoints require appropriate authentication/authorization.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from titan.jobs import Job, JobQueue, JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])

# Shared queue instance
_queue: JobQueue | None = None


async def get_queue() -> JobQueue:
    """Get or initialize job queue."""
    global _queue
    if _queue is None:
        _queue = JobQueue()
        await _queue.initialize()
    return _queue


class JobSubmitRequest(BaseModel):
    """Request to submit a new job."""

    task: str = Field(..., description="Task type (e.g., 'export_aasx', 'cleanup')")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Task-specific payload data",
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Job priority (0-100, higher = more urgent)",
    )


class JobResponse(BaseModel):
    """Job details response."""

    id: str
    task: str
    status: str
    payload: dict[str, Any]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int
    max_retries: int

    @classmethod
    def from_job(cls, job: Job) -> JobResponse:
        """Create response from Job instance."""
        return cls(
            id=job.id,
            task=job.task,
            status=job.status.value,
            payload=job.payload,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            result=job.result,
            error=job.error,
            attempts=job.attempts,
            max_retries=job.max_retries,
        )


class JobListResponse(BaseModel):
    """List of jobs response."""

    jobs: list[JobResponse]
    count: int


class QueueStatsResponse(BaseModel):
    """Queue statistics response."""

    pending: int
    processing: int
    dlq: int


@router.post("", response_model=JobResponse, status_code=201)
async def submit_job(request: JobSubmitRequest) -> JobResponse:
    """Submit a new background job.

    Creates a job and adds it to the processing queue.
    The job will be picked up by an available worker.

    Returns the job details including the assigned ID.
    """
    queue = await get_queue()

    job_id = await queue.submit(
        task=request.task,
        payload=request.payload,
        priority=request.priority,
    )

    job = await queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to create job")

    return JobResponse.from_job(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Get job details by ID.

    Returns the current status and details of a job.
    """
    queue = await get_queue()
    job = await queue.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return JobResponse.from_job(job)


@router.delete("/{job_id}", status_code=204)
async def cancel_job(job_id: str) -> None:
    """Cancel a pending or running job.

    Only jobs in PENDING or RUNNING status can be cancelled.
    """
    queue = await get_queue()

    success = await queue.cancel_job(job_id)
    if not success:
        job = await queue.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status.value} status",
        )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = Query(
        None,
        description="Filter by status (pending, running, completed, failed, dead)",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum jobs to return"),
) -> JobListResponse:
    """List jobs with optional filtering.

    Returns jobs ordered by creation time (newest first).
    """
    queue = await get_queue()

    # Parse status filter
    status_filter: JobStatus | None = None
    if status:
        try:
            status_filter = JobStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}",
            )

    jobs = await queue.list_jobs(status=status_filter, limit=limit)

    return JobListResponse(
        jobs=[JobResponse.from_job(j) for j in jobs],
        count=len(jobs),
    )


@router.get("/stats/queue", response_model=QueueStatsResponse)
async def get_queue_stats() -> QueueStatsResponse:
    """Get queue statistics.

    Returns counts of jobs in each queue state.
    """
    queue = await get_queue()
    stats = await queue.get_queue_stats()

    return QueueStatsResponse(**stats)

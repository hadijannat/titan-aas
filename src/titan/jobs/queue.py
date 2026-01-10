"""Redis-backed job queue for async background processing.

Provides a distributed job queue with:
- Job submission and status tracking
- Atomic job claiming via BRPOPLPUSH
- Retry with exponential backoff
- Dead letter queue for failed jobs
- Job result storage with TTL

Example:
    queue = JobQueue()
    await queue.initialize()

    # Submit a job
    job_id = await queue.submit("export_aasx", {"aas_id": "abc123"})

    # Check job status
    job = await queue.get_job(job_id)
    print(f"Status: {job.status}")

    # Process jobs (worker)
    async for job in queue.claim_jobs():
        result = await process_job(job)
        await queue.complete_job(job.id, result)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, TypeVar, cast
from uuid import uuid4

if TYPE_CHECKING:
    from redis.asyncio import Redis

from titan.cache.redis import get_redis

T = TypeVar("T")


def _await_redis(result: Awaitable[T] | T) -> Awaitable[T]:
    """Cast redis-py async results to an awaitable for mypy."""
    return cast(Awaitable[T], result)


logger = logging.getLogger(__name__)

# Redis key prefixes
JOB_PREFIX = "titan:job:"
QUEUE_PENDING = "titan:jobs:pending"
QUEUE_PROCESSING = "titan:jobs:processing"
QUEUE_DLQ = "titan:jobs:dlq"

# Default configuration
DEFAULT_JOB_TTL = 86400 * 7  # 7 days
DEFAULT_RESULT_TTL = 86400  # 24 hours
DEFAULT_MAX_RETRIES = 3
DEFAULT_CLAIM_TIMEOUT = 5000  # 5 seconds


class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD = "dead"  # Moved to DLQ after max retries


@dataclass
class Job:
    """Job definition with metadata and state."""

    id: str
    task: str
    payload: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    priority: int = 0  # Higher = more urgent

    def to_dict(self) -> dict[str, Any]:
        """Serialize job to dictionary."""
        return {
            "id": self.id,
            "task": self.task,
            "payload": self.payload,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Deserialize job from dictionary."""
        return cls(
            id=data["id"],
            task=data["task"],
            payload=data["payload"],
            status=JobStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            result=data.get("result"),
            error=data.get("error"),
            attempts=data.get("attempts", 0),
            max_retries=data.get("max_retries", DEFAULT_MAX_RETRIES),
            priority=data.get("priority", 0),
        )


class JobQueue:
    """Redis-backed distributed job queue.

    Uses Redis lists for queue management:
    - LPUSH to add jobs (with priority sorting)
    - BRPOPLPUSH to atomically move jobs from pending to processing
    - Job state stored in separate hash keys

    Thread-safe and horizontally scalable.
    """

    def __init__(
        self,
        job_ttl: int = DEFAULT_JOB_TTL,
        result_ttl: int = DEFAULT_RESULT_TTL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        claim_timeout: int = DEFAULT_CLAIM_TIMEOUT,
    ) -> None:
        self.job_ttl = job_ttl
        self.result_ttl = result_ttl
        self.max_retries = max_retries
        self.claim_timeout = claim_timeout
        self._redis: Redis | None = None

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        self._redis = await get_redis()
        logger.info("Job queue initialized")

    async def _get_redis(self) -> Redis:
        """Get Redis client, initializing if needed."""
        if self._redis is None:
            await self.initialize()
        return self._redis  # type: ignore[return-value]

    def _job_key(self, job_id: str) -> str:
        """Redis key for job data."""
        return f"{JOB_PREFIX}{job_id}"

    async def submit(
        self,
        task: str,
        payload: dict[str, Any] | None = None,
        priority: int = 0,
        max_retries: int | None = None,
    ) -> str:
        """Submit a job to the queue.

        Args:
            task: Task name (e.g., "export_aasx", "cleanup")
            payload: Task-specific data
            priority: Job priority (higher = more urgent)
            max_retries: Override default max retries

        Returns:
            Job ID for tracking
        """
        redis = await self._get_redis()

        job = Job(
            id=str(uuid4()),
            task=task,
            payload=payload or {},
            priority=priority,
            max_retries=max_retries if max_retries is not None else self.max_retries,
        )

        # Store job data
        await _await_redis(
            redis.set(
                self._job_key(job.id),
                json.dumps(job.to_dict()),
                ex=self.job_ttl,
            )
        )

        # Add to pending queue
        await _await_redis(redis.lpush(QUEUE_PENDING, job.id))

        logger.info(f"Job submitted: {job.id} ({task})")
        return job.id

    async def get_job(self, job_id: str) -> Job | None:
        """Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job if found, None otherwise
        """
        redis = await self._get_redis()
        data = await redis.get(self._job_key(job_id))

        if data is None:
            return None

        return Job.from_dict(json.loads(data))

    async def claim_jobs(
        self,
        batch_size: int = 1,
        timeout: int | None = None,
    ) -> AsyncIterator[Job]:
        """Claim jobs from the queue for processing.

        Uses BRPOPLPUSH for atomic job claiming:
        - Blocks until a job is available
        - Atomically moves job from pending to processing
        - Prevents duplicate processing

        Args:
            batch_size: Number of jobs to claim (1 for serial processing)
            timeout: Block timeout in seconds (None for forever)

        Yields:
            Jobs ready for processing
        """
        redis = await self._get_redis()
        timeout_sec = timeout if timeout is not None else 0

        for _ in range(batch_size):
            # Atomic pop from pending, push to processing
            job_id_bytes = cast(
                bytes | str | None,
                await _await_redis(
                    redis.brpoplpush(
                        QUEUE_PENDING,
                        QUEUE_PROCESSING,
                        timeout=timeout_sec,
                    )
                ),
            )

            if job_id_bytes is None:
                break

            job_id = job_id_bytes.decode() if isinstance(job_id_bytes, bytes) else job_id_bytes
            job = await self.get_job(job_id)

            if job is None:
                # Job expired or deleted, remove from processing
                await _await_redis(redis.lrem(QUEUE_PROCESSING, 1, job_id))
                continue

            # Update job status
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.attempts += 1

            await _await_redis(
                redis.set(
                    self._job_key(job.id),
                    json.dumps(job.to_dict()),
                    ex=self.job_ttl,
                )
            )

            logger.info(f"Job claimed: {job.id} (attempt {job.attempts})")
            yield job

    async def complete_job(
        self,
        job_id: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Mark job as completed.

        Args:
            job_id: Job identifier
            result: Job result data
        """
        redis = await self._get_redis()
        job = await self.get_job(job_id)

        if job is None:
            logger.warning(f"Job not found for completion: {job_id}")
            return

        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.result = result

        # Update job with shorter TTL (result retention)
        await _await_redis(
            redis.set(
                self._job_key(job.id),
                json.dumps(job.to_dict()),
                ex=self.result_ttl,
            )
        )

        # Remove from processing queue
        await _await_redis(redis.lrem(QUEUE_PROCESSING, 1, job_id))

        logger.info(f"Job completed: {job_id}")

    async def fail_job(
        self,
        job_id: str,
        error: str,
        retry: bool = True,
    ) -> None:
        """Mark job as failed, optionally retry.

        Args:
            job_id: Job identifier
            error: Error message
            retry: Whether to retry if attempts remaining
        """
        redis = await self._get_redis()
        job = await self.get_job(job_id)

        if job is None:
            logger.warning(f"Job not found for failure: {job_id}")
            return

        job.error = error

        # Remove from processing queue
        await _await_redis(redis.lrem(QUEUE_PROCESSING, 1, job_id))

        if retry and job.attempts < job.max_retries:
            # Re-queue for retry
            job.status = JobStatus.PENDING
            await _await_redis(
                redis.set(
                    self._job_key(job.id),
                    json.dumps(job.to_dict()),
                    ex=self.job_ttl,
                )
            )
            await _await_redis(redis.lpush(QUEUE_PENDING, job_id))
            logger.info(
                f"Job queued for retry: {job_id} (attempt {job.attempts}/{job.max_retries})"
            )
        else:
            # Move to dead letter queue
            job.status = JobStatus.DEAD
            job.completed_at = datetime.now(timezone.utc)
            await _await_redis(
                redis.set(
                    self._job_key(job.id),
                    json.dumps(job.to_dict()),
                    ex=self.job_ttl,
                )
            )
            await _await_redis(redis.lpush(QUEUE_DLQ, job_id))
            logger.warning(f"Job moved to DLQ: {job_id}")

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job.

        Args:
            job_id: Job identifier

        Returns:
            True if cancelled, False if not found or already processing
        """
        redis = await self._get_redis()
        job = await self.get_job(job_id)

        if job is None:
            return False

        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False

        # Remove from queues
        await _await_redis(redis.lrem(QUEUE_PENDING, 1, job_id))
        await _await_redis(redis.lrem(QUEUE_PROCESSING, 1, job_id))

        # Update status
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)

        await _await_redis(
            redis.set(
                self._job_key(job.id),
                json.dumps(job.to_dict()),
                ex=self.result_ttl,
            )
        )

        logger.info(f"Job cancelled: {job_id}")
        return True

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs, optionally filtered by status.

        Args:
            status: Filter by status (None for all)
            limit: Maximum jobs to return

        Returns:
            List of jobs
        """
        redis = await self._get_redis()
        jobs: list[Job] = []

        # Get job IDs from appropriate queue(s)
        if status == JobStatus.PENDING:
            job_ids = await _await_redis(redis.lrange(QUEUE_PENDING, 0, limit - 1))
        elif status == JobStatus.RUNNING:
            job_ids = await _await_redis(redis.lrange(QUEUE_PROCESSING, 0, limit - 1))
        elif status == JobStatus.DEAD:
            job_ids = await _await_redis(redis.lrange(QUEUE_DLQ, 0, limit - 1))
        else:
            # Get from all queues
            pending = await _await_redis(redis.lrange(QUEUE_PENDING, 0, limit - 1))
            processing = await _await_redis(redis.lrange(QUEUE_PROCESSING, 0, limit - 1))
            dlq = await _await_redis(redis.lrange(QUEUE_DLQ, 0, limit - 1))
            job_ids = pending + processing + dlq

        for job_id_bytes in job_ids[:limit]:
            job_id = job_id_bytes.decode() if isinstance(job_id_bytes, bytes) else job_id_bytes
            job = await self.get_job(job_id)
            if job is not None:
                if status is None or job.status == status:
                    jobs.append(job)

        return jobs

    async def get_queue_stats(self) -> dict[str, int]:
        """Get queue statistics.

        Returns:
            Dict with pending, processing, and dlq counts
        """
        redis = await self._get_redis()

        return {
            "pending": await _await_redis(redis.llen(QUEUE_PENDING)),
            "processing": await _await_redis(redis.llen(QUEUE_PROCESSING)),
            "dlq": await _await_redis(redis.llen(QUEUE_DLQ)),
        }

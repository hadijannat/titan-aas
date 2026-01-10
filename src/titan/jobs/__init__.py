"""Background job processing for Titan-AAS.

Provides distributed job queue with:
- Redis-backed job storage
- Atomic job claiming with BRPOPLPUSH
- Retry with exponential backoff
- Cron-like scheduling
- Leader election for singleton workers

Example:
    # Submit a job
    from titan.jobs import JobQueue

    queue = JobQueue()
    await queue.initialize()
    job_id = await queue.submit("export_aasx", {"aas_id": "abc123"})

    # Process jobs with worker
    from titan.jobs import JobWorker, register_all_handlers

    worker = JobWorker()
    register_all_handlers(worker)
    await worker.run()

    # Schedule recurring jobs
    from titan.jobs import JobScheduler

    scheduler = JobScheduler()
    scheduler.add_job("cleanup", cron="0 2 * * *")
    await scheduler.run()
"""

from titan.jobs.queue import (
    DEFAULT_CLAIM_TIMEOUT,
    DEFAULT_JOB_TTL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RESULT_TTL,
    Job,
    JobQueue,
    JobStatus,
)
from titan.jobs.scheduler import (
    SCHEDULE_PRESETS,
    CronExpression,
    JobScheduler,
    ScheduledJob,
)
from titan.jobs.tasks import BUILTIN_HANDLERS, register_all_handlers
from titan.jobs.worker import (
    JobHandler,
    JobWorker,
    WorkerConfig,
    create_worker,
    job_handler,
)

__all__ = [
    # Queue
    "Job",
    "JobQueue",
    "JobStatus",
    "DEFAULT_JOB_TTL",
    "DEFAULT_RESULT_TTL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_CLAIM_TIMEOUT",
    # Worker
    "JobWorker",
    "JobHandler",
    "WorkerConfig",
    "job_handler",
    "create_worker",
    # Tasks
    "BUILTIN_HANDLERS",
    "register_all_handlers",
    # Scheduler
    "JobScheduler",
    "ScheduledJob",
    "CronExpression",
    "SCHEDULE_PRESETS",
]

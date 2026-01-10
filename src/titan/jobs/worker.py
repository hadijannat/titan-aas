"""Background worker for processing queued jobs.

Provides a worker that:
- Claims and processes jobs from the queue
- Handles retries with exponential backoff
- Integrates with leader election for singleton workers
- Supports graceful shutdown

Example:
    worker = JobWorker()
    worker.register_handler("export_aasx", handle_export)
    worker.register_handler("cleanup", handle_cleanup)

    # Run worker (blocks until shutdown)
    await worker.run()

    # Or as context manager
    async with worker:
        await asyncio.Event().wait()  # Wait for signal
"""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Awaitable, Callable

from titan.distributed.leader import LeaderElection
from titan.jobs.queue import Job, JobQueue

logger = logging.getLogger(__name__)

# Type alias for job handlers
JobHandler = Callable[[Job], Awaitable[dict[str, Any] | None]]


@dataclass
class WorkerConfig:
    """Worker configuration."""

    # Worker identification
    name: str = "default"

    # Job processing
    batch_size: int = 1
    poll_interval: float = 1.0
    claim_timeout: int = 5

    # Retry behavior
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0

    # Leader election (for singleton workers)
    leader_election: bool = False
    leader_lease_ttl: int = 30


class JobWorker:
    """Background worker for processing queued jobs.

    Features:
    - Concurrent job processing (configurable batch size)
    - Handler registration for task types
    - Exponential backoff for retries
    - Graceful shutdown with signal handling
    - Optional leader election for singleton workers
    """

    def __init__(
        self,
        queue: JobQueue | None = None,
        config: WorkerConfig | None = None,
    ) -> None:
        self.queue = queue or JobQueue()
        self.config = config or WorkerConfig()
        self._handlers: dict[str, JobHandler] = {}
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._leader: LeaderElection | None = None
        self._tasks: list[asyncio.Task[None]] = []

    def register_handler(self, task: str, handler: JobHandler) -> None:
        """Register a handler for a task type.

        Args:
            task: Task name (e.g., "export_aasx")
            handler: Async function that processes the job

        Example:
            async def handle_export(job: Job) -> dict:
                aas_id = job.payload["aas_id"]
                path = await export_aasx(aas_id)
                return {"path": path}

            worker.register_handler("export_aasx", handle_export)
        """
        self._handlers[task] = handler
        logger.info(f"Registered handler for task: {task}")

    async def start(self) -> None:
        """Start the worker.

        Initializes the queue, sets up signal handlers, and starts processing.
        """
        await self.queue.initialize()
        self._running = True
        self._shutdown_event.clear()

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler)

        # Start leader election if configured
        if self.config.leader_election:
            self._leader = LeaderElection(
                name=f"worker-{self.config.name}",
                lease_ttl=self.config.leader_lease_ttl,
            )
            await self._leader.start()
            logger.info(
                f"Started leader election for worker: {self.config.name}"
            )

        logger.info(f"Worker started: {self.config.name}")

    async def stop(self) -> None:
        """Stop the worker gracefully.

        Waits for current jobs to complete before stopping.
        """
        logger.info(f"Stopping worker: {self.config.name}")
        self._running = False
        self._shutdown_event.set()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop leader election
        if self._leader:
            await self._leader.stop()

        logger.info(f"Worker stopped: {self.config.name}")

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        logger.info("Received shutdown signal")
        asyncio.create_task(self.stop())

    async def run(self) -> None:
        """Run the worker until shutdown.

        Main loop that claims and processes jobs.
        """
        await self.start()

        try:
            while self._running:
                # Check leader status if using leader election
                if self._leader and not self._leader.is_leader:
                    await asyncio.sleep(self.config.poll_interval)
                    continue

                # Claim and process jobs
                try:
                    async for job in self.queue.claim_jobs(
                        batch_size=self.config.batch_size,
                        timeout=self.config.claim_timeout,
                    ):
                        # Process job in a task
                        task = asyncio.create_task(self._process_job(job))
                        self._tasks.append(task)
                        task.add_done_callback(
                            lambda t: self._tasks.remove(t)
                        )

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error claiming jobs: {e}")
                    await asyncio.sleep(self.config.poll_interval)

                # Brief pause between batches
                await asyncio.sleep(self.config.poll_interval)

        finally:
            await self.stop()

    async def _process_job(self, job: Job) -> None:
        """Process a single job.

        Args:
            job: Job to process
        """
        handler = self._handlers.get(job.task)

        if handler is None:
            logger.error(f"No handler for task: {job.task}")
            await self.queue.fail_job(
                job.id,
                f"Unknown task type: {job.task}",
                retry=False,
            )
            return

        try:
            logger.info(f"Processing job: {job.id} ({job.task})")
            result = await handler(job)
            await self.queue.complete_job(job.id, result)
            logger.info(f"Job completed successfully: {job.id}")

        except Exception as e:
            logger.error(f"Job failed: {job.id} - {e}")
            await self.queue.fail_job(
                job.id,
                str(e),
                retry=True,
            )

    async def run_once(self) -> int:
        """Process one batch of jobs and return.

        Useful for testing or cron-like execution.

        Returns:
            Number of jobs processed
        """
        await self.queue.initialize()
        count = 0

        async for job in self.queue.claim_jobs(
            batch_size=self.config.batch_size,
            timeout=1,  # Short timeout for run_once
        ):
            await self._process_job(job)
            count += 1

        return count

    async def __aenter__(self) -> "JobWorker":
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        await self.stop()


def job_handler(task: str) -> Callable[[JobHandler], JobHandler]:
    """Decorator to mark a function as a job handler.

    Example:
        @job_handler("export_aasx")
        async def handle_export(job: Job) -> dict:
            ...

        # Later, register with worker
        worker.register_handler("export_aasx", handle_export)
    """

    def decorator(func: JobHandler) -> JobHandler:
        func.__job_task__ = task  # type: ignore[attr-defined]
        return func

    return decorator


async def create_worker(
    handlers: dict[str, JobHandler] | None = None,
    config: WorkerConfig | None = None,
) -> JobWorker:
    """Factory function to create a configured worker.

    Args:
        handlers: Dict mapping task names to handlers
        config: Worker configuration

    Returns:
        Configured and initialized worker
    """
    worker = JobWorker(config=config)

    if handlers:
        for task, handler in handlers.items():
            worker.register_handler(task, handler)

    return worker

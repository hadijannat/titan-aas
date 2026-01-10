"""Cron-like job scheduler.

Schedules recurring jobs based on cron expressions:
- Minute, hour, day scheduling
- Integration with job queue
- Leader election for distributed scheduling

Example:
    scheduler = JobScheduler()
    scheduler.add_job("cleanup", cron="0 2 * * *")  # Daily at 2 AM
    scheduler.add_job("report", cron="0 9 * * 1")   # Mondays at 9 AM

    await scheduler.run()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from titan.distributed.leader import LeaderElection
from titan.jobs.queue import JobQueue

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """A scheduled job definition."""

    name: str
    task: str
    cron: str
    payload: dict[str, Any]
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None


class CronExpression:
    """Parse and evaluate cron expressions.

    Supports standard 5-field cron format:
    - minute (0-59)
    - hour (0-23)
    - day of month (1-31)
    - month (1-12)
    - day of week (0-6, 0=Sunday)

    Special characters:
    - * : any value
    - */n : every n values
    - n-m : range from n to m
    - n,m : specific values n and m
    """

    def __init__(self, expression: str) -> None:
        self.expression = expression
        self._parse(expression)

    def _parse(self, expression: str) -> None:
        """Parse cron expression into components."""
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression (expected 5 parts): {expression}")

        self.minute = self._parse_field(parts[0], 0, 59)
        self.hour = self._parse_field(parts[1], 0, 23)
        self.day_of_month = self._parse_field(parts[2], 1, 31)
        self.month = self._parse_field(parts[3], 1, 12)
        self.day_of_week = self._parse_field(parts[4], 0, 6)

    def _parse_field(self, field: str, min_val: int, max_val: int) -> set[int]:
        """Parse a single cron field."""
        values: set[int] = set()

        for part in field.split(","):
            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif part.startswith("*/"):
                step = int(part[2:])
                values.update(range(min_val, max_val + 1, step))
            elif "-" in part:
                start, end = map(int, part.split("-"))
                values.update(range(start, end + 1))
            else:
                values.add(int(part))

        return values

    def matches(self, dt: datetime) -> bool:
        """Check if datetime matches this cron expression."""
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day_of_month
            and dt.month in self.month
            and dt.weekday() in self._convert_weekday(self.day_of_week)
        )

    def _convert_weekday(self, cron_days: set[int]) -> set[int]:
        """Convert cron weekdays (0=Sun) to Python weekdays (0=Mon)."""
        # Cron: 0=Sun, 1=Mon, ..., 6=Sat
        # Python: 0=Mon, 1=Tue, ..., 6=Sun
        python_days: set[int] = set()
        for day in cron_days:
            if day == 0:
                python_days.add(6)  # Sunday
            else:
                python_days.add(day - 1)
        return python_days

    def next_run(self, after: datetime | None = None) -> datetime:
        """Calculate next run time after given datetime."""
        if after is None:
            after = datetime.now(UTC)

        # Start from next minute
        current = after.replace(second=0, microsecond=0)

        # Search for next matching time (max 1 year)
        for _ in range(525600):  # Minutes in a year
            current = current.replace(
                minute=(current.minute + 1) % 60,
            )
            if current.minute == 0:
                current = current.replace(hour=(current.hour + 1) % 24)
                if current.hour == 0:
                    # Move to next day
                    current = current.replace(
                        day=current.day + 1,
                    )

            if self.matches(current):
                return current

        raise ValueError(f"No matching time found for: {self.expression}")


class JobScheduler:
    """Cron-like scheduler for recurring jobs.

    Uses leader election to ensure only one scheduler instance
    runs in a distributed environment.
    """

    def __init__(
        self,
        queue: JobQueue | None = None,
        check_interval: float = 60.0,
        use_leader_election: bool = True,
    ) -> None:
        self.queue = queue or JobQueue()
        self.check_interval = check_interval
        self.use_leader_election = use_leader_election
        self._jobs: dict[str, ScheduledJob] = {}
        self._crons: dict[str, CronExpression] = {}
        self._running = False
        self._leader: LeaderElection | None = None

    def add_job(
        self,
        name: str,
        task: str | None = None,
        cron: str = "* * * * *",
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> ScheduledJob:
        """Add a scheduled job.

        Args:
            name: Unique job name (also used as task if task not provided)
            task: Task type to submit (defaults to name)
            cron: Cron expression (5-field format)
            payload: Default payload for job submissions
            enabled: Whether job is active

        Returns:
            ScheduledJob instance
        """
        task = task or name
        cron_expr = CronExpression(cron)

        job = ScheduledJob(
            name=name,
            task=task,
            cron=cron,
            payload=payload or {},
            enabled=enabled,
            next_run=cron_expr.next_run(),
        )

        self._jobs[name] = job
        self._crons[name] = cron_expr

        logger.info(f"Scheduled job added: {name} ({cron}), next run: {job.next_run}")
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job.

        Args:
            name: Job name to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._jobs:
            del self._jobs[name]
            del self._crons[name]
            logger.info(f"Scheduled job removed: {name}")
            return True
        return False

    def enable_job(self, name: str) -> bool:
        """Enable a scheduled job."""
        if name in self._jobs:
            self._jobs[name].enabled = True
            return True
        return False

    def disable_job(self, name: str) -> bool:
        """Disable a scheduled job."""
        if name in self._jobs:
            self._jobs[name].enabled = False
            return True
        return False

    def list_jobs(self) -> list[ScheduledJob]:
        """List all scheduled jobs."""
        return list(self._jobs.values())

    async def start(self) -> None:
        """Start the scheduler."""
        await self.queue.initialize()
        self._running = True

        if self.use_leader_election:
            self._leader = LeaderElection(
                name="job-scheduler",
                lease_ttl=30,
            )
            await self._leader.start()
            logger.info("Scheduler started with leader election")
        else:
            logger.info("Scheduler started (no leader election)")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._leader:
            await self._leader.stop()
        logger.info("Scheduler stopped")

    async def run(self) -> None:
        """Run the scheduler until stopped."""
        await self.start()

        try:
            while self._running:
                # Only schedule if we're the leader (or not using election)
                if self._leader is None or self._leader.is_leader:
                    await self._check_schedules()

                await asyncio.sleep(self.check_interval)

        finally:
            await self.stop()

    async def _check_schedules(self) -> None:
        """Check all schedules and submit due jobs."""
        now = datetime.now(UTC)

        for name, job in self._jobs.items():
            if not job.enabled:
                continue

            cron = self._crons[name]

            # Check if it's time to run
            if job.next_run and now >= job.next_run:
                try:
                    # Submit job to queue
                    job_id = await self.queue.submit(
                        task=job.task,
                        payload={
                            **job.payload,
                            "_scheduled": True,
                            "_schedule_name": name,
                        },
                    )

                    logger.info(f"Scheduled job submitted: {name} -> {job_id}")

                    # Update last/next run times
                    job.last_run = now
                    job.next_run = cron.next_run(now)

                except Exception as e:
                    logger.error(f"Failed to submit scheduled job {name}: {e}")

    async def run_now(self, name: str) -> str | None:
        """Manually trigger a scheduled job immediately.

        Args:
            name: Job name to trigger

        Returns:
            Job ID if submitted, None if job not found
        """
        job = self._jobs.get(name)
        if job is None:
            return None

        job_id = await self.queue.submit(
            task=job.task,
            payload={
                **job.payload,
                "_scheduled": True,
                "_schedule_name": name,
                "_manual_trigger": True,
            },
        )

        logger.info(f"Manually triggered scheduled job: {name} -> {job_id}")
        return job_id


# Common schedule presets
SCHEDULE_PRESETS = {
    "every_minute": "* * * * *",
    "every_5_minutes": "*/5 * * * *",
    "every_15_minutes": "*/15 * * * *",
    "every_hour": "0 * * * *",
    "daily_midnight": "0 0 * * *",
    "daily_2am": "0 2 * * *",
    "weekly_sunday": "0 0 * * 0",
    "weekly_monday": "0 0 * * 1",
    "monthly_first": "0 0 1 * *",
}

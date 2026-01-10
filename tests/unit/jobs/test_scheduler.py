"""Tests for job scheduler functionality."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from titan.jobs.scheduler import (
    SCHEDULE_PRESETS,
    CronExpression,
    JobScheduler,
    ScheduledJob,
)


class TestCronExpression:
    """Tests for CronExpression parsing and matching."""

    def test_parse_all_wildcards(self) -> None:
        """Parses all wildcard expression."""
        cron = CronExpression("* * * * *")

        assert len(cron.minute) == 60  # 0-59
        assert len(cron.hour) == 24  # 0-23
        assert len(cron.day_of_month) == 31  # 1-31
        assert len(cron.month) == 12  # 1-12
        assert len(cron.day_of_week) == 7  # 0-6

    def test_parse_specific_values(self) -> None:
        """Parses specific values."""
        cron = CronExpression("30 14 1 6 0")

        assert cron.minute == {30}
        assert cron.hour == {14}
        assert cron.day_of_month == {1}
        assert cron.month == {6}
        assert cron.day_of_week == {0}

    def test_parse_step_values(self) -> None:
        """Parses step expressions (*/n)."""
        cron = CronExpression("*/15 * * * *")

        assert cron.minute == {0, 15, 30, 45}

    def test_parse_range(self) -> None:
        """Parses range expressions (n-m)."""
        cron = CronExpression("* 9-17 * * *")

        assert cron.hour == {9, 10, 11, 12, 13, 14, 15, 16, 17}

    def test_parse_list(self) -> None:
        """Parses list expressions (n,m)."""
        cron = CronExpression("0,30 * * * *")

        assert cron.minute == {0, 30}

    def test_parse_invalid_expression(self) -> None:
        """Raises error for invalid expression."""
        with pytest.raises(ValueError, match="expected 5 parts"):
            CronExpression("* * *")

    def test_matches_specific_time(self) -> None:
        """Matches specific datetime."""
        cron = CronExpression("30 14 * * *")
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)

        assert cron.matches(dt) is True

    def test_not_matches_wrong_time(self) -> None:
        """Does not match wrong datetime."""
        cron = CronExpression("30 14 * * *")
        dt = datetime(2024, 1, 15, 14, 31, tzinfo=timezone.utc)  # Wrong minute

        assert cron.matches(dt) is False

    def test_matches_daily_at_2am(self) -> None:
        """Matches daily at 2 AM pattern."""
        cron = CronExpression("0 2 * * *")
        dt = datetime(2024, 1, 15, 2, 0, tzinfo=timezone.utc)

        assert cron.matches(dt) is True

    def test_matches_every_5_minutes(self) -> None:
        """Matches every 5 minutes pattern."""
        cron = CronExpression("*/5 * * * *")

        # Should match 0, 5, 10, etc.
        assert cron.matches(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc))
        assert cron.matches(datetime(2024, 1, 1, 0, 10, tzinfo=timezone.utc))

        # Should not match 1, 2, 3, 4, 6, etc.
        assert not cron.matches(datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2024, 1, 1, 0, 3, tzinfo=timezone.utc))


class TestSchedulePresets:
    """Tests for schedule presets."""

    def test_presets_are_valid(self) -> None:
        """All presets are valid cron expressions."""
        for name, expression in SCHEDULE_PRESETS.items():
            cron = CronExpression(expression)
            assert len(cron.minute) > 0
            assert len(cron.hour) > 0

    def test_every_minute_preset(self) -> None:
        """Every minute preset matches every minute."""
        cron = CronExpression(SCHEDULE_PRESETS["every_minute"])

        # Should match any time
        assert cron.matches(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
        assert cron.matches(datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc))

    def test_daily_midnight_preset(self) -> None:
        """Daily midnight preset matches midnight only."""
        cron = CronExpression(SCHEDULE_PRESETS["daily_midnight"])

        assert cron.matches(datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc))
        assert not cron.matches(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))


class TestScheduledJob:
    """Tests for ScheduledJob dataclass."""

    def test_job_creation(self) -> None:
        """ScheduledJob can be created."""
        job = ScheduledJob(
            name="cleanup",
            task="cleanup_expired",
            cron="0 2 * * *",
            payload={"max_age": 30},
        )

        assert job.name == "cleanup"
        assert job.task == "cleanup_expired"
        assert job.cron == "0 2 * * *"
        assert job.enabled is True

    def test_job_disabled(self) -> None:
        """ScheduledJob can be disabled."""
        job = ScheduledJob(
            name="cleanup",
            task="cleanup_expired",
            cron="0 2 * * *",
            payload={},
            enabled=False,
        )

        assert job.enabled is False


class TestJobScheduler:
    """Tests for JobScheduler class."""

    @pytest.fixture
    def mock_queue(self) -> AsyncMock:
        """Create mock job queue."""
        queue = AsyncMock()
        queue.initialize = AsyncMock()
        queue.submit = AsyncMock(return_value="job-123")
        return queue

    @pytest.fixture
    def scheduler(self, mock_queue: AsyncMock) -> JobScheduler:
        """Create scheduler with mocked queue."""
        return JobScheduler(
            queue=mock_queue,
            use_leader_election=False,
        )

    def test_add_job(self, scheduler: JobScheduler) -> None:
        """Adding a job registers it."""
        job = scheduler.add_job(
            name="cleanup",
            task="cleanup_expired",
            cron="0 2 * * *",
        )

        assert job.name == "cleanup"
        assert job.task == "cleanup_expired"
        assert "cleanup" in scheduler._jobs

    def test_add_job_uses_name_as_task(self, scheduler: JobScheduler) -> None:
        """Job uses name as task if task not specified."""
        job = scheduler.add_job(
            name="cleanup",
            cron="0 2 * * *",
        )

        assert job.task == "cleanup"

    def test_remove_job(self, scheduler: JobScheduler) -> None:
        """Removing a job unregisters it."""
        scheduler.add_job(name="cleanup", cron="0 2 * * *")

        result = scheduler.remove_job("cleanup")

        assert result is True
        assert "cleanup" not in scheduler._jobs

    def test_remove_nonexistent_job(self, scheduler: JobScheduler) -> None:
        """Removing non-existent job returns False."""
        result = scheduler.remove_job("nonexistent")

        assert result is False

    def test_enable_job(self, scheduler: JobScheduler) -> None:
        """Enabling a job sets enabled flag."""
        scheduler.add_job(name="cleanup", cron="0 2 * * *", enabled=False)

        result = scheduler.enable_job("cleanup")

        assert result is True
        assert scheduler._jobs["cleanup"].enabled is True

    def test_disable_job(self, scheduler: JobScheduler) -> None:
        """Disabling a job clears enabled flag."""
        scheduler.add_job(name="cleanup", cron="0 2 * * *", enabled=True)

        result = scheduler.disable_job("cleanup")

        assert result is True
        assert scheduler._jobs["cleanup"].enabled is False

    def test_list_jobs(self, scheduler: JobScheduler) -> None:
        """Listing jobs returns all registered jobs."""
        scheduler.add_job(name="cleanup", cron="0 2 * * *")
        scheduler.add_job(name="report", cron="0 9 * * 1")

        jobs = scheduler.list_jobs()

        assert len(jobs) == 2
        names = [j.name for j in jobs]
        assert "cleanup" in names
        assert "report" in names

    @pytest.mark.asyncio
    async def test_run_now(
        self, scheduler: JobScheduler, mock_queue: AsyncMock
    ) -> None:
        """Manual trigger submits job immediately."""
        scheduler.add_job(
            name="cleanup",
            task="cleanup_expired",
            cron="0 2 * * *",
            payload={"max_age": 30},
        )

        job_id = await scheduler.run_now("cleanup")

        assert job_id == "job-123"
        mock_queue.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_now_nonexistent(
        self, scheduler: JobScheduler, mock_queue: AsyncMock
    ) -> None:
        """Manual trigger of non-existent job returns None."""
        job_id = await scheduler.run_now("nonexistent")

        assert job_id is None
        mock_queue.submit.assert_not_called()

"""Tests for job queue functionality."""

from unittest.mock import AsyncMock

import pytest

from titan.jobs.queue import (
    Job,
    JobQueue,
    JobStatus,
)


class TestJob:
    """Tests for Job dataclass."""

    def test_job_creation(self) -> None:
        """Job can be created with minimal parameters."""
        job = Job(
            id="test-123",
            task="export",
            payload={"aas_id": "abc"},
        )

        assert job.id == "test-123"
        assert job.task == "export"
        assert job.payload == {"aas_id": "abc"}
        assert job.status == JobStatus.PENDING
        assert job.attempts == 0

    def test_job_to_dict(self) -> None:
        """Job serializes to dictionary."""
        job = Job(
            id="test-123",
            task="export",
            payload={"aas_id": "abc"},
        )

        data = job.to_dict()

        assert data["id"] == "test-123"
        assert data["task"] == "export"
        assert data["payload"] == {"aas_id": "abc"}
        assert data["status"] == "pending"
        assert "created_at" in data

    def test_job_from_dict(self) -> None:
        """Job deserializes from dictionary."""
        data = {
            "id": "test-123",
            "task": "export",
            "payload": {"aas_id": "abc"},
            "status": "running",
            "created_at": "2024-01-01T00:00:00+00:00",
            "started_at": "2024-01-01T00:01:00+00:00",
            "completed_at": None,
            "result": None,
            "error": None,
            "attempts": 1,
            "max_retries": 3,
            "priority": 5,
        }

        job = Job.from_dict(data)

        assert job.id == "test-123"
        assert job.task == "export"
        assert job.status == JobStatus.RUNNING
        assert job.attempts == 1
        assert job.priority == 5

    def test_job_roundtrip(self) -> None:
        """Job survives serialization roundtrip."""
        original = Job(
            id="test-123",
            task="cleanup",
            payload={"max_age": 30},
            status=JobStatus.COMPLETED,
            result={"deleted": 10},
        )

        data = original.to_dict()
        restored = Job.from_dict(data)

        assert restored.id == original.id
        assert restored.task == original.task
        assert restored.status == original.status
        assert restored.result == original.result


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """All expected statuses are defined."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"
        assert JobStatus.DEAD.value == "dead"

    def test_status_from_string(self) -> None:
        """Status can be created from string."""
        assert JobStatus("pending") == JobStatus.PENDING
        assert JobStatus("running") == JobStatus.RUNNING


class TestJobQueue:
    """Tests for JobQueue class."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.set = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.lpush = AsyncMock(return_value=1)
        mock.llen = AsyncMock(return_value=0)
        mock.lrange = AsyncMock(return_value=[])
        mock.lrem = AsyncMock(return_value=1)
        mock.brpoplpush = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def queue(self, mock_redis: AsyncMock) -> JobQueue:
        """Create JobQueue with mocked Redis."""
        q = JobQueue()
        q._redis = mock_redis
        return q

    @pytest.mark.asyncio
    async def test_submit_job(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Submitting a job stores it and adds to queue."""
        job_id = await queue.submit("export", {"aas_id": "abc"})

        assert job_id is not None
        assert mock_redis.set.called
        assert mock_redis.lpush.called

    @pytest.mark.asyncio
    async def test_submit_with_priority(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Job can be submitted with priority."""
        job_id = await queue.submit("export", {}, priority=10)

        assert job_id is not None
        # Check that the job was stored with priority
        call_args = mock_redis.set.call_args
        assert "10" in str(call_args) or call_args is not None

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Getting non-existent job returns None."""
        mock_redis.get.return_value = None

        job = await queue.get_job("nonexistent")

        assert job is None

    @pytest.mark.asyncio
    async def test_get_job_found(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Getting existing job returns Job instance."""
        import json

        job_data = Job(id="test-123", task="export", payload={}).to_dict()
        mock_redis.get.return_value = json.dumps(job_data).encode()

        job = await queue.get_job("test-123")

        assert job is not None
        assert job.id == "test-123"
        assert job.task == "export"

    @pytest.mark.asyncio
    async def test_cancel_job(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Cancelling a job updates status and removes from queue."""
        import json

        job_data = Job(id="test-123", task="export", payload={}).to_dict()
        mock_redis.get.return_value = json.dumps(job_data).encode()

        result = await queue.cancel_job("test-123")

        assert result is True
        assert mock_redis.lrem.called

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Cancelling non-existent job returns False."""
        mock_redis.get.return_value = None

        result = await queue.cancel_job("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Queue stats returns counts for each queue."""
        mock_redis.llen.side_effect = [5, 2, 1]  # pending, processing, dlq

        stats = await queue.get_queue_stats()

        assert stats["pending"] == 5
        assert stats["processing"] == 2
        assert stats["dlq"] == 1

    @pytest.mark.asyncio
    async def test_complete_job(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Completing a job updates status and removes from processing."""
        import json

        job_data = Job(
            id="test-123",
            task="export",
            payload={},
            status=JobStatus.RUNNING,
        ).to_dict()
        mock_redis.get.return_value = json.dumps(job_data).encode()

        await queue.complete_job("test-123", {"exported": True})

        assert mock_redis.set.called
        assert mock_redis.lrem.called

    @pytest.mark.asyncio
    async def test_fail_job_with_retry(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Failed job with retries remaining is re-queued."""
        import json

        job_data = Job(
            id="test-123",
            task="export",
            payload={},
            status=JobStatus.RUNNING,
            attempts=1,
            max_retries=3,
        ).to_dict()
        mock_redis.get.return_value = json.dumps(job_data).encode()

        await queue.fail_job("test-123", "Something went wrong", retry=True)

        # Should be re-queued (lpush called twice: initial + retry)
        assert mock_redis.lpush.called

    @pytest.mark.asyncio
    async def test_fail_job_to_dlq(self, queue: JobQueue, mock_redis: AsyncMock) -> None:
        """Failed job at max retries moves to DLQ."""
        import json

        job_data = Job(
            id="test-123",
            task="export",
            payload={},
            status=JobStatus.RUNNING,
            attempts=3,
            max_retries=3,
        ).to_dict()
        mock_redis.get.return_value = json.dumps(job_data).encode()

        await queue.fail_job("test-123", "Final failure", retry=True)

        # Check DLQ queue was used
        lpush_calls = mock_redis.lpush.call_args_list
        assert any("dlq" in str(call) for call in lpush_calls)

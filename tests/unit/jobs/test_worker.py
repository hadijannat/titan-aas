"""Tests for job worker functionality."""

from unittest.mock import AsyncMock, patch

import pytest

from titan.jobs.queue import Job
from titan.jobs.worker import JobWorker, WorkerConfig, job_handler


class TestWorkerConfig:
    """Tests for WorkerConfig."""

    def test_default_config(self) -> None:
        """Default config has expected values."""
        config = WorkerConfig()

        assert config.name == "default"
        assert config.batch_size == 1
        assert config.poll_interval == 1.0
        assert config.max_retries == 3
        assert config.leader_election is False

    def test_custom_config(self) -> None:
        """Config accepts custom values."""
        config = WorkerConfig(
            name="custom-worker",
            batch_size=5,
            leader_election=True,
        )

        assert config.name == "custom-worker"
        assert config.batch_size == 5
        assert config.leader_election is True


class TestJobWorker:
    """Tests for JobWorker class."""

    @pytest.fixture
    def mock_queue(self) -> AsyncMock:
        """Create mock job queue."""
        queue = AsyncMock()
        queue.initialize = AsyncMock()
        queue.claim_jobs = AsyncMock(return_value=iter([]))
        queue.complete_job = AsyncMock()
        queue.fail_job = AsyncMock()
        return queue

    @pytest.fixture
    def worker(self, mock_queue: AsyncMock) -> JobWorker:
        """Create worker with mocked queue."""
        return JobWorker(queue=mock_queue)

    def test_register_handler(self, worker: JobWorker) -> None:
        """Handler registration works."""

        async def my_handler(job: Job) -> dict:
            return {"done": True}

        worker.register_handler("my_task", my_handler)

        assert "my_task" in worker._handlers
        assert worker._handlers["my_task"] is my_handler

    def test_register_multiple_handlers(self, worker: JobWorker) -> None:
        """Multiple handlers can be registered."""

        async def handler1(job: Job) -> dict:
            return {}

        async def handler2(job: Job) -> dict:
            return {}

        worker.register_handler("task1", handler1)
        worker.register_handler("task2", handler2)

        assert len(worker._handlers) == 2

    @pytest.mark.asyncio
    async def test_process_job_success(
        self, worker: JobWorker, mock_queue: AsyncMock
    ) -> None:
        """Successful job processing completes the job."""
        job = Job(id="test-123", task="export", payload={})

        async def handler(j: Job) -> dict:
            return {"exported": True}

        worker.register_handler("export", handler)
        await worker._process_job(job)

        mock_queue.complete_job.assert_called_once_with(
            "test-123", {"exported": True}
        )

    @pytest.mark.asyncio
    async def test_process_job_failure(
        self, worker: JobWorker, mock_queue: AsyncMock
    ) -> None:
        """Failed job processing marks job as failed."""
        job = Job(id="test-123", task="export", payload={})

        async def handler(j: Job) -> dict:
            raise ValueError("Something went wrong")

        worker.register_handler("export", handler)
        await worker._process_job(job)

        mock_queue.fail_job.assert_called_once()
        call_args = mock_queue.fail_job.call_args
        assert call_args[0][0] == "test-123"
        assert "Something went wrong" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_process_unknown_task(
        self, worker: JobWorker, mock_queue: AsyncMock
    ) -> None:
        """Unknown task type fails without retry."""
        job = Job(id="test-123", task="unknown_task", payload={})

        await worker._process_job(job)

        mock_queue.fail_job.assert_called_once()
        call_args = mock_queue.fail_job.call_args
        assert call_args[1]["retry"] is False


class TestJobHandlerDecorator:
    """Tests for @job_handler decorator."""

    def test_decorator_marks_function(self) -> None:
        """Decorator adds task metadata to function."""

        @job_handler("my_task")
        async def my_handler(job: Job) -> dict:
            return {}

        assert hasattr(my_handler, "__job_task__")
        assert my_handler.__job_task__ == "my_task"

    def test_decorator_preserves_function(self) -> None:
        """Decorator doesn't alter function behavior."""

        @job_handler("test")
        async def my_handler(job: Job) -> dict:
            return {"result": job.payload.get("value", 0) * 2}

        # Function should still be callable (though async)
        assert callable(my_handler)


class TestWorkerLifecycle:
    """Tests for worker start/stop lifecycle."""

    @pytest.fixture
    def mock_queue(self) -> AsyncMock:
        """Create mock job queue."""
        queue = AsyncMock()
        queue.initialize = AsyncMock()
        return queue

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_queue: AsyncMock) -> None:
        """Worker works as context manager."""
        worker = JobWorker(queue=mock_queue)

        # Mock signal handlers to avoid issues in tests
        with patch("asyncio.get_running_loop"):
            async with worker:
                assert worker._running is True

            assert worker._running is False

    @pytest.mark.asyncio
    async def test_start_initializes_queue(self, mock_queue: AsyncMock) -> None:
        """Starting worker initializes the queue."""
        worker = JobWorker(queue=mock_queue)

        with patch("asyncio.get_running_loop"):
            await worker.start()

        mock_queue.initialize.assert_called_once()
        assert worker._running is True

        await worker.stop()

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, mock_queue: AsyncMock) -> None:
        """Stopping worker sets running to False."""
        worker = JobWorker(queue=mock_queue)

        with patch("asyncio.get_running_loop"):
            await worker.start()
            await worker.stop()

        assert worker._running is False

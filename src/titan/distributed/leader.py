"""Leader election for distributed background workers.

Uses Redis-based distributed locking to ensure only one instance runs
certain background tasks at a time. This is critical for:
- Scheduled cleanup jobs
- Periodic aggregation tasks
- Any singleton background worker

The leader election uses a lease-based approach:
1. Leaders acquire a lock with a TTL
2. Leaders renew the lock periodically
3. If a leader dies, the lock expires and another instance can claim it

Example:
    async with LeaderElection("cleanup-job") as leader:
        if leader.is_leader:
            await run_cleanup()
        else:
            # Another instance is the leader
            pass

    # Or as a continuous election
    election = LeaderElection("background-worker")
    await election.start()

    while running:
        if election.is_leader:
            await do_leader_work()
        await asyncio.sleep(1)

    await election.stop()
"""

from __future__ import annotations

import asyncio
import logging
import os
from types import TracebackType
from typing import TYPE_CHECKING, Awaitable, Callable, ParamSpec, TypeVar, cast
from uuid import uuid4

from titan.cache.redis import get_redis

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Lock configuration
LOCK_PREFIX = "titan:leader:"
DEFAULT_LEASE_TTL = 30  # Seconds
RENEWAL_INTERVAL = 10  # Renew every 10 seconds (well before 30s TTL)


def _generate_instance_id() -> str:
    """Generate a unique instance ID for leader identification."""
    hostname = os.environ.get("HOSTNAME", os.environ.get("POD_NAME", "unknown"))
    return f"{hostname}-{uuid4().hex[:8]}"


class LeaderElection:
    """Redis-based leader election for distributed singleton workers.

    Uses Redis SETNX with TTL to implement a distributed lock that ensures
    only one instance holds leadership at a time. The leader renews the
    lock periodically to maintain leadership.

    Features:
    - Automatic lease renewal
    - Graceful leadership transfer on shutdown
    - Callbacks for leadership changes
    - Health monitoring

    Args:
        name: Name of the leadership role (e.g., "cleanup-worker")
        instance_id: Unique identifier for this instance (auto-generated if None)
        lease_ttl: Lock TTL in seconds (default 30)
        renewal_interval: How often to renew the lock (default 10)
    """

    def __init__(
        self,
        name: str,
        instance_id: str | None = None,
        lease_ttl: int = DEFAULT_LEASE_TTL,
        renewal_interval: int = RENEWAL_INTERVAL,
    ):
        self.name = name
        self.instance_id = instance_id or _generate_instance_id()
        self.lease_ttl = lease_ttl
        self.renewal_interval = renewal_interval

        self._lock_key = f"{LOCK_PREFIX}{name}"
        self._is_leader = False
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._redis: Redis | None = None

        # Callbacks
        self._on_elected: list[asyncio.Future[None]] = []
        self._on_demoted: list[asyncio.Future[None]] = []

    @property
    def is_leader(self) -> bool:
        """Check if this instance is currently the leader."""
        return self._is_leader

    @property
    def lock_key(self) -> str:
        """The Redis key used for the lock."""
        return self._lock_key

    async def _get_redis(self) -> Redis:
        """Get Redis client."""
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def start(self) -> None:
        """Start participating in leader election.

        This starts a background task that continuously tries to acquire
        or renew leadership.
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._election_loop())
        logger.info(f"Started leader election for '{self.name}' as {self.instance_id}")

    async def stop(self) -> None:
        """Stop participating in leader election.

        If this instance is the leader, it will release the lock to allow
        another instance to take over.
        """
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Release lock if we were the leader
        if self._is_leader:
            await self._release_lock()

        logger.info(f"Stopped leader election for '{self.name}'")

    async def _election_loop(self) -> None:
        """Main election loop."""
        while self._running:
            try:
                if self._is_leader:
                    # Try to renew our lock
                    success = await self._renew_lock()
                    if not success:
                        # Lost leadership
                        await self._handle_demotion()
                else:
                    # Try to acquire leadership
                    success = await self._acquire_lock()
                    if success:
                        await self._handle_election()

                await asyncio.sleep(self.renewal_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in election loop for '{self.name}': {e}")
                self._is_leader = False
                await asyncio.sleep(self.renewal_interval)

    async def _acquire_lock(self) -> bool:
        """Try to acquire the leader lock."""
        redis = await self._get_redis()

        # Use SET NX EX for atomic acquire
        acquired = await redis.set(
            self._lock_key,
            self.instance_id,
            nx=True,  # Only set if not exists
            ex=self.lease_ttl,  # Expire after TTL
        )

        if acquired:
            logger.info(f"Acquired leadership for '{self.name}'")
            return True

        return False

    async def _renew_lock(self) -> bool:
        """Renew the leader lock if we own it."""
        redis = await self._get_redis()

        # Check if we still own the lock
        current_owner = await redis.get(self._lock_key)
        if current_owner is None:
            return False

        current_owner_str = (
            current_owner.decode() if isinstance(current_owner, bytes) else current_owner
        )
        if current_owner_str != self.instance_id:
            logger.warning(f"Lock for '{self.name}' taken by {current_owner_str}")
            return False

        # Renew the TTL
        await redis.expire(self._lock_key, self.lease_ttl)
        logger.debug(f"Renewed leadership for '{self.name}'")
        return True

    async def _release_lock(self) -> bool:
        """Release the leader lock if we own it."""
        redis = await self._get_redis()

        # Only delete if we own it (use Lua script for atomicity)
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await cast(
            Awaitable[int],
            redis.eval(script, 1, self._lock_key, self.instance_id),
        )
        if result:
            logger.info(f"Released leadership for '{self.name}'")
            self._is_leader = False
            return True
        return False

    async def _handle_election(self) -> None:
        """Handle being elected as leader."""
        self._is_leader = True
        logger.info(f"Elected as leader for '{self.name}'")

        # Notify waiters
        for future in self._on_elected:
            if not future.done():
                future.set_result(None)
        self._on_elected.clear()

    async def _handle_demotion(self) -> None:
        """Handle losing leadership."""
        self._is_leader = False
        logger.warning(f"Lost leadership for '{self.name}'")

        # Notify waiters
        for future in self._on_demoted:
            if not future.done():
                future.set_result(None)
        self._on_demoted.clear()

    async def wait_for_leadership(self, timeout: float | None = None) -> bool:
        """Wait until this instance becomes the leader.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)

        Returns:
            True if leadership was acquired, False if timeout
        """
        if self._is_leader:
            return True

        future: asyncio.Future[None] = asyncio.Future()
        self._on_elected.append(future)

        try:
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            self._on_elected.remove(future)
            return False

    async def get_current_leader(self) -> str | None:
        """Get the instance ID of the current leader."""
        redis = await self._get_redis()
        value = await redis.get(self._lock_key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    async def __aenter__(self) -> "LeaderElection":
        """Context manager entry - try to acquire leadership once."""
        redis = await self._get_redis()
        acquired = await redis.set(
            self._lock_key,
            self.instance_id,
            nx=True,
            ex=self.lease_ttl,
        )
        self._is_leader = bool(acquired)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - release leadership if held."""
        if self._is_leader:
            await self._release_lock()


class LeaderOnlyTask:
    """Decorator/context for tasks that should only run on the leader.

    Example:
        @leader_only("cleanup")
        async def cleanup_task():
            # Only runs on leader
            await do_cleanup()

        # Or as context manager
        async with LeaderOnlyTask("aggregation") as task:
            if task.should_run:
                await aggregate_data()
    """

    def __init__(self, name: str, lease_ttl: int = DEFAULT_LEASE_TTL):
        self.name = name
        self.lease_ttl = lease_ttl
        self._election: LeaderElection | None = None

    @property
    def should_run(self) -> bool:
        """Check if the task should run (we are leader)."""
        return self._election is not None and self._election.is_leader

    async def __aenter__(self) -> "LeaderOnlyTask":
        self._election = LeaderElection(self.name, lease_ttl=self.lease_ttl)
        await self._election.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._election:
            await self._election.__aexit__(exc_type, exc_val, exc_tb)


P = ParamSpec("P")
R = TypeVar("R")


def leader_only(
    name: str, lease_ttl: int = DEFAULT_LEASE_TTL
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
    """Decorator that makes a function only run on the leader instance.

    Args:
        name: Name of the leadership role
        lease_ttl: Lock TTL in seconds

    Example:
        @leader_only("daily-report")
        async def generate_daily_report():
            # Only runs on the leader instance
            ...
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            async with LeaderElection(name, lease_ttl=lease_ttl) as election:
                if election.is_leader:
                    return await func(*args, **kwargs)
                else:
                    logger.debug(f"Skipping {func.__name__} - not leader for '{name}'")
                    return None

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator

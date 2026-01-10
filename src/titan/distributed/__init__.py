"""Distributed coordination primitives for Titan-AAS.

Provides infrastructure for horizontal scaling:
- Leader election for singleton workers
- Distributed locking (via leader module)

Example:
    from titan.distributed import LeaderElection, leader_only

    # Continuous leader election
    election = LeaderElection("my-worker")
    await election.start()

    # Or as decorator
    @leader_only("cleanup")
    async def cleanup_task():
        ...
"""

from titan.distributed.leader import (
    LeaderElection,
    LeaderOnlyTask,
    leader_only,
)

__all__ = [
    "LeaderElection",
    "LeaderOnlyTask",
    "leader_only",
]

# ADR-0004: Redis-Based Leader Election

## Status

Accepted

## Context

Titan-AAS runs as multiple replicas for high availability. Certain tasks should run on only one instance at a time:

1. **Scheduled cleanup jobs**: Deleting expired sessions, orphaned blobs.
2. **Periodic aggregation**: Computing metrics, generating reports.
3. **External integrations**: Polling external systems (avoid duplicate requests).
4. **Database migrations**: Schema changes (must be single-writer).

Requirements:
- **Single leader**: Exactly one instance runs the task at any time.
- **Automatic failover**: If leader dies, another takes over quickly.
- **Graceful handoff**: Leader can voluntarily release leadership.
- **No split-brain**: Network partitions don't create multiple leaders.

Options considered:
- **Kubernetes leader election**: Ties us to Kubernetes.
- **etcd/Consul**: Additional infrastructure dependency.
- **PostgreSQL advisory locks**: Works but requires active DB connection.
- **Redis distributed lock**: Simple, we already have Redis.

## Decision

Implement **Redis-based leader election** using `SET NX EX` with periodic renewal.

### Algorithm

```
1. Acquire lock: SET leader:{role} {instance_id} NX EX 30
   - NX: Only set if not exists (atomic)
   - EX 30: Expire in 30 seconds (lease TTL)

2. If acquired (lock didn't exist):
   - We are the leader
   - Start renewal loop: every 10s, EXPIRE leader:{role} 30

3. If not acquired (lock exists):
   - We are a follower
   - Retry acquisition every 10s

4. On shutdown:
   - Release lock atomically (only if we own it)
   - Lua script: if GET == our_id then DEL
```

### Implementation

```python
class LeaderElection:
    async def _acquire_lock(self) -> bool:
        """Try to acquire the leader lock."""
        acquired = await self.redis.set(
            self._lock_key,
            self.instance_id,
            nx=True,   # Only set if not exists
            ex=self.lease_ttl,  # 30 second TTL
        )
        return bool(acquired)

    async def _renew_lock(self) -> bool:
        """Renew the lock if we own it."""
        current = await self.redis.get(self._lock_key)
        if current != self.instance_id:
            return False  # Someone else has it
        await self.redis.expire(self._lock_key, self.lease_ttl)
        return True

    async def _release_lock(self) -> bool:
        """Release lock atomically if we own it."""
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        return await self.redis.eval(script, 1, self._lock_key, self.instance_id)
```

### Usage Patterns

```python
# Continuous election (background workers)
election = LeaderElection("cleanup-worker")
await election.start()

while running:
    if election.is_leader:
        await do_cleanup()
    await asyncio.sleep(60)

await election.stop()

# One-shot election (cron jobs)
async with LeaderElection("daily-report") as election:
    if election.is_leader:
        await generate_report()

# Decorator pattern
@leader_only("aggregation")
async def aggregate_metrics():
    # Only runs on leader
    ...
```

## Consequences

### Positive

- **Simple implementation**: ~100 lines of code.
- **Fast failover**: New leader elected within lease TTL (30s max).
- **No additional dependencies**: Uses existing Redis.
- **Graceful shutdown**: Leader releases lock immediately.

### Negative

- **Redis SPOF**: If Redis is unavailable, no leader election.
- **Clock skew sensitivity**: Large clock differences could cause issues.
- **Lease overhead**: Renewal traffic (small but continuous).

### Neutral

- **At most one leader**: Guaranteed by Redis single-threaded execution.
- **Leadership gaps**: Brief period between leader death and new election.
- **Debugging**: Leadership state visible via Redis CLI.

### Failure Scenarios

| Scenario | Behavior |
|----------|----------|
| Leader crashes | Lock expires after TTL, new leader elected |
| Network partition | Partitioned leader loses lock after TTL |
| Redis unavailable | All instances become followers, tasks pause |
| Graceful shutdown | Immediate lock release, fast failover |

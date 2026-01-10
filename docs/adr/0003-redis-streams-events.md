# ADR-0003: Redis Streams for Distributed Event Processing

## Status

Accepted

## Context

Titan-AAS needs to process events across multiple instances:

1. **Cache invalidation**: When one instance updates data, others must invalidate their caches.
2. **WebSocket notifications**: Real-time updates to connected clients.
3. **MQTT publishing**: External event broadcasting.
4. **Audit logging**: Capturing all write operations.

Requirements for the event system:
- **Durability**: Events must not be lost during processing.
- **At-least-once delivery**: Every event must be processed.
- **Horizontal scaling**: Multiple consumers can share the load.
- **Ordering**: Events should be processed in order per entity.

Options considered:
- **In-memory queue**: Fast but not durable, single-instance only.
- **PostgreSQL LISTEN/NOTIFY**: Durable but limited throughput.
- **Kafka**: Excellent durability but operational complexity.
- **Redis Streams**: Good balance of durability, performance, and simplicity.

## Decision

Use **Redis Streams** with consumer groups for distributed event processing.

### Stream Structure

```
Stream: titan:events:aas
├── Event 1: {id: "1-0", data: {action: "created", aas_id: "..."}}
├── Event 2: {id: "2-0", data: {action: "updated", aas_id: "..."}}
└── Event 3: {id: "3-0", data: {action: "deleted", aas_id: "..."}}

Consumer Group: titan-workers
├── Consumer: worker-1 (processes events 1, 3)
└── Consumer: worker-2 (processes event 2)
```

### Implementation

```python
class RedisStreamEventBus:
    async def publish(self, event: AasEvent) -> str:
        """Publish event to Redis Stream."""
        event_id = await self.redis.xadd(
            self.stream_key,
            event.to_dict(),
            maxlen=self.max_len,  # Trim old events
        )
        return event_id

    async def consume(self) -> AsyncIterator[AasEvent]:
        """Consume events from stream via consumer group."""
        while True:
            events = await self.redis.xreadgroup(
                groupname=self.group,
                consumername=self.consumer_id,
                streams={self.stream_key: ">"},
                count=self.batch_size,
                block=self.block_ms,
            )
            for stream, messages in events:
                for msg_id, data in messages:
                    yield AasEvent.from_dict(data)
                    await self.redis.xack(
                        self.stream_key, self.group, msg_id
                    )
```

### Dead Letter Queue

Unprocessable events are moved to a DLQ after max retries:

```python
async def claim_pending(self):
    """Claim messages stuck with crashed consumers."""
    pending = await self.redis.xpending_range(
        self.stream_key,
        self.group,
        min="-",
        max="+",
        count=100,
    )
    for msg in pending:
        if msg.idle_time > self.claim_timeout:
            if msg.delivery_count > self.max_retries:
                await self.move_to_dlq(msg)
            else:
                await self.redis.xclaim(...)
```

## Consequences

### Positive

- **Durability**: Events persist until acknowledged.
- **Horizontal scaling**: Consumer groups distribute load automatically.
- **Automatic rebalancing**: Failed consumer's work is claimed by others.
- **Backpressure**: Slow consumers don't block producers.
- **Observability**: Stream length and pending count indicate health.

### Negative

- **Redis dependency**: Requires Redis with Streams support (5.0+).
- **Memory usage**: Events consume Redis memory until trimmed.
- **Complexity**: Consumer groups add operational overhead.

### Neutral

- **At-least-once semantics**: Event handlers must be idempotent.
- **Ordering per stream**: Global ordering requires single stream.

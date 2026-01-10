# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for Titan-AAS.

ADRs document significant architectural decisions made during the development of the project. Each ADR describes a decision, its context, and its consequences.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0000](0000-template.md) | ADR Template | Template |
| [0001](0001-dual-storage-pattern.md) | Dual Storage Pattern (JSONB + Bytes) | Accepted |
| [0002](0002-fast-slow-path-routing.md) | Fast/Slow Path Request Routing | Accepted |
| [0003](0003-redis-streams-events.md) | Redis Streams for Distributed Event Processing | Accepted |
| [0004](0004-redis-leader-election.md) | Redis-Based Leader Election | Accepted |

## Creating a New ADR

1. Copy the template: `cp 0000-template.md NNNN-title.md`
2. Fill in the sections
3. Update this index
4. Submit a pull request

## ADR Format

Each ADR follows this structure:

- **Status**: Proposed, Accepted, Deprecated, or Superseded
- **Context**: The issue or situation that prompted the decision
- **Decision**: What was decided
- **Consequences**: Trade-offs and implications (positive, negative, neutral)

## References

- [ADR GitHub Organization](https://adr.github.io/)
- [Michael Nygard's ADR Template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)

"""Dashboard database endpoints - PostgreSQL layer visualization.

Provides visibility into:
- Connection pool status
- Query performance metrics
- Table statistics
- Slow query analysis
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan.persistence.db import get_session
from titan.persistence.tables import (
    AasTable,
    AasxPackageTable,
    ConceptDescriptionTable,
    SubmodelTable,
)
from titan.security.deps import require_permission
from titan.security.rbac import Permission

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/database", tags=["Dashboard - Database"])


class PoolStats(BaseModel):
    """Database connection pool statistics."""

    pool_size: int
    checked_out: int
    overflow: int
    checked_in: int


class TableStats(BaseModel):
    """Statistics for a single database table."""

    name: str
    row_count: int
    estimated_size: str | None = None


class QueryStats(BaseModel):
    """Query performance statistics."""

    total_queries: int
    avg_duration_ms: float | None = None
    p50_duration_ms: float | None = None
    p95_duration_ms: float | None = None
    p99_duration_ms: float | None = None


class SlowQuery(BaseModel):
    """Slow query information from pg_stat_statements."""

    query: str
    calls: int
    total_time_ms: float
    mean_time_ms: float
    rows: int


class DatabaseStats(BaseModel):
    """Complete database statistics."""

    timestamp: datetime
    pool: PoolStats
    tables: list[TableStats]
    query_stats: QueryStats | None = None


@router.get(
    "/stats",
    response_model=DatabaseStats,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_database_stats(
    session: AsyncSession = Depends(get_session),
) -> DatabaseStats:
    """Get comprehensive database statistics.

    Returns:
    - Connection pool status (size, checked out, overflow)
    - Table row counts
    - Query performance metrics (if pg_stat_statements enabled)
    """
    # Get pool stats from engine
    bind = session.get_bind()
    pool = bind.pool  # type: ignore[union-attr]

    pool_size = max(pool.size(), 0)  # type: ignore[union-attr]
    checked_out = max(pool.checkedout(), 0)  # type: ignore[union-attr]
    checked_in = max(pool.checkedin(), 0)  # type: ignore[union-attr]
    overflow = max(pool.overflow(), 0)  # type: ignore[union-attr]

    pool_stats = PoolStats(
        pool_size=pool_size,
        checked_out=checked_out,
        overflow=overflow,
        checked_in=checked_in,
    )

    # Get table row counts
    tables: list[TableStats] = []

    aas_count = (await session.execute(select(func.count()).select_from(AasTable))).scalar() or 0
    tables.append(TableStats(name="aas", row_count=aas_count))

    sm_stmt = select(func.count()).select_from(SubmodelTable)
    sm_count = (await session.execute(sm_stmt)).scalar() or 0
    tables.append(TableStats(name="submodels", row_count=sm_count))

    cd_count = (
        await session.execute(select(func.count()).select_from(ConceptDescriptionTable))
    ).scalar() or 0
    tables.append(TableStats(name="concept_descriptions", row_count=cd_count))

    pkg_count = (
        await session.execute(select(func.count()).select_from(AasxPackageTable))
    ).scalar() or 0
    tables.append(TableStats(name="aasx_packages", row_count=pkg_count))

    # Try to get table sizes
    try:
        size_query = text("""
            SELECT
                relname as table_name,
                pg_size_pretty(pg_total_relation_size(relid)) as size
            FROM pg_catalog.pg_statio_user_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(relid) DESC
        """)
        size_result = await session.execute(size_query)
        size_map = {row[0]: row[1] for row in size_result.fetchall()}

        for table in tables:
            if table.name in size_map:
                table.estimated_size = size_map[table.name]
    except Exception:
        pass  # Size info not critical

    # Try to get query stats from pg_stat_statements
    query_stats = None
    try:
        stats_query = text("""
            SELECT
                COUNT(*) as total_queries,
                AVG(mean_exec_time) as avg_duration,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY mean_exec_time) as p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY mean_exec_time) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY mean_exec_time) as p99
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
        """)
        stats_result = await session.execute(stats_query)
        row = stats_result.fetchone()
        if row:
            query_stats = QueryStats(
                total_queries=row[0] or 0,
                avg_duration_ms=round(row[1], 2) if row[1] else None,
                p50_duration_ms=round(row[2], 2) if row[2] else None,
                p95_duration_ms=round(row[3], 2) if row[3] else None,
                p99_duration_ms=round(row[4], 2) if row[4] else None,
            )
    except Exception:
        pass  # pg_stat_statements may not be enabled

    return DatabaseStats(
        timestamp=datetime.utcnow(),
        pool=pool_stats,
        tables=tables,
        query_stats=query_stats,
    )


@router.get(
    "/tables",
    response_model=list[TableStats],
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_table_stats(
    session: AsyncSession = Depends(get_session),
) -> list[TableStats]:
    """Get detailed table statistics."""
    stats = await get_database_stats(session)
    return stats.tables


@router.get(
    "/slow-queries",
    response_model=list[SlowQuery],
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_slow_queries(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, le=100, description="Maximum number of queries to return"),
    min_calls: int = Query(default=1, description="Minimum call count to include"),
) -> list[SlowQuery]:
    """Get slow queries from pg_stat_statements.

    Returns the slowest queries by mean execution time.
    Requires pg_stat_statements extension to be enabled.
    """
    try:
        query = text("""
            SELECT
                query,
                calls,
                total_exec_time as total_time_ms,
                mean_exec_time as mean_time_ms,
                rows
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
              AND calls >= :min_calls
            ORDER BY mean_exec_time DESC
            LIMIT :limit
        """)
        result = await session.execute(query, {"limit": limit, "min_calls": min_calls})
        rows = result.fetchall()

        return [
            SlowQuery(
                query=row[0][:500],  # Truncate long queries
                calls=row[1],
                total_time_ms=round(row[2], 2),
                mean_time_ms=round(row[3], 2),
                rows=row[4],
            )
            for row in rows
        ]
    except Exception:
        # pg_stat_statements not enabled
        return []

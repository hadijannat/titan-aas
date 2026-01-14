"""Dashboard observability endpoints - Logging and tracing control.

Provides:
- Runtime log level adjustment
- Recent trace spans
- Metrics export
- Profiling data
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from titan.security.deps import require_permission
from titan.security.rbac import Permission

router = APIRouter(prefix="/observability", tags=["Dashboard - Observability"])

# Keep track of log level changes
_original_log_levels: dict[str, int] = {}


class LoggerInfo(BaseModel):
    """Information about a logger."""

    name: str
    level: str
    effective_level: str
    handlers: list[str]


class LogLevelChange(BaseModel):
    """Request to change a logger's level."""

    logger: str
    level: str


class LogLevelResult(BaseModel):
    """Result of a log level change."""

    logger: str
    previous_level: str
    new_level: str
    timestamp: datetime


class TraceSpan(BaseModel):
    """A single trace span."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    operation_name: str
    service_name: str
    start_time: datetime
    duration_ms: float
    status: str
    attributes: dict[str, Any] | None = None


class TracesResponse(BaseModel):
    """Response containing trace spans."""

    spans: list[TraceSpan]
    total: int


class ProfilingStats(BaseModel):
    """Profiling statistics."""

    timestamp: datetime
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_mb: float | None = None
    open_files: int | None = None
    threads: int | None = None
    async_tasks: int | None = None


# Log level mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _level_name(level: int) -> str:
    """Convert log level int to name."""
    for name, lvl in LOG_LEVELS.items():
        if lvl == level:
            return name
    return str(level)


@router.get(
    "/loggers",
    response_model=list[LoggerInfo],
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def list_loggers(
    prefix: str = Query(default="titan", description="Logger name prefix to filter"),
) -> list[LoggerInfo]:
    """List all loggers matching the prefix.

    Returns logger name, current level, and handlers.
    """
    loggers: list[LoggerInfo] = []

    # Get all logger names
    manager = logging.Logger.manager
    logger_dict = manager.loggerDict

    for name in sorted(logger_dict.keys()):
        if not name.startswith(prefix):
            continue

        logger = logging.getLogger(name)
        handlers = [type(h).__name__ for h in logger.handlers]

        loggers.append(
            LoggerInfo(
                name=name,
                level=_level_name(logger.level),
                effective_level=_level_name(logger.getEffectiveLevel()),
                handlers=handlers,
            )
        )

    # Also add the root titan logger
    titan_logger = logging.getLogger("titan")
    if titan_logger not in [logging.getLogger(lg.name) for lg in loggers]:
        loggers.insert(
            0,
            LoggerInfo(
                name="titan",
                level=_level_name(titan_logger.level),
                effective_level=_level_name(titan_logger.getEffectiveLevel()),
                handlers=[type(h).__name__ for h in titan_logger.handlers],
            ),
        )

    return loggers


@router.put(
    "/log-level",
    response_model=LogLevelResult,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def set_log_level(change: LogLevelChange) -> LogLevelResult:
    """Change the log level for a logger at runtime.

    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    level_upper = change.level.upper()
    if level_upper not in LOG_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid log level: {change.level}. Valid levels: {list(LOG_LEVELS.keys())}",
        )

    logger = logging.getLogger(change.logger)
    previous_level = logger.level

    # Store original level if not already stored
    if change.logger not in _original_log_levels:
        _original_log_levels[change.logger] = previous_level

    # Set new level
    new_level = LOG_LEVELS[level_upper]
    logger.setLevel(new_level)

    return LogLevelResult(
        logger=change.logger,
        previous_level=_level_name(previous_level),
        new_level=level_upper,
        timestamp=datetime.utcnow(),
    )


@router.post(
    "/log-level/reset",
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def reset_log_levels() -> dict[str, Any]:
    """Reset all log levels to their original values."""
    reset_count = 0

    for logger_name, original_level in _original_log_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(original_level)
        reset_count += 1

    _original_log_levels.clear()

    return {
        "success": True,
        "reset_count": reset_count,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get(
    "/traces",
    response_model=TracesResponse,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_recent_traces(
    limit: int = Query(default=50, le=200, description="Maximum traces to return"),
    service: str | None = Query(None, description="Filter by service name"),
    operation: str | None = Query(None, description="Filter by operation name"),
    min_duration_ms: float | None = Query(None, description="Minimum duration in ms"),
) -> TracesResponse:
    """Get recent trace spans.

    Note: This is a placeholder. Full implementation would query
    an OpenTelemetry collector or trace storage backend.
    """
    # In a real implementation, this would query the OTLP collector
    # For now, return an empty list
    return TracesResponse(
        spans=[],
        total=0,
    )


@router.get(
    "/profiling",
    response_model=ProfilingStats,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_profiling_stats() -> ProfilingStats:
    """Get current process profiling statistics.

    Returns CPU, memory, and async task information.
    """
    stats = ProfilingStats(timestamp=datetime.utcnow())

    try:
        import psutil  # type: ignore[import-untyped]

        process = psutil.Process()
        stats.cpu_percent = process.cpu_percent()
        stats.memory_percent = process.memory_percent()
        stats.memory_mb = process.memory_info().rss / (1024 * 1024)
        stats.open_files = len(process.open_files())
        stats.threads = process.num_threads()
    except ImportError:
        # psutil not installed
        pass
    except Exception:
        pass

    # Count async tasks
    try:
        import asyncio

        tasks = asyncio.all_tasks()
        stats.async_tasks = len(tasks)
    except Exception:
        pass

    return stats


@router.get(
    "/health-history",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_health_history(
    limit: int = Query(default=100, le=500, description="Maximum entries to return"),
) -> dict[str, Any]:
    """Get health check history.

    Note: This is a placeholder. Full implementation would track
    health check results over time.
    """
    return {
        "entries": [],
        "total": 0,
        "message": "Health history tracking not yet implemented",
    }


@router.get(
    "/metrics/summary",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_metrics_summary() -> dict[str, Any]:
    """Get a summary of key metrics.

    Provides a quick overview of important metrics without
    full Prometheus scrape.
    """
    try:
        from titan.observability.metrics import get_metrics

        metrics = get_metrics()

        # Extract key counters
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "http_requests_total": _get_counter_value(metrics, "http_requests_total"),
            "http_request_duration_p50": _get_histogram_percentile(
                metrics, "http_request_duration_seconds", 0.5
            ),
            "http_request_duration_p99": _get_histogram_percentile(
                metrics, "http_request_duration_seconds", 0.99
            ),
            "db_queries_total": _get_counter_value(metrics, "db_queries_total"),
            "cache_hits_total": _get_counter_value(metrics, "cache_hits_total"),
            "cache_misses_total": _get_counter_value(metrics, "cache_misses_total"),
        }

        return summary
    except Exception as e:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
        }


def _get_counter_value(metrics: Any, name: str) -> float | None:
    """Extract counter value from metrics registry."""
    try:
        # This is a simplified extraction - actual implementation
        # depends on metrics library structure
        return None
    except Exception:
        return None


def _get_histogram_percentile(metrics: Any, name: str, percentile: float) -> float | None:
    """Extract histogram percentile from metrics registry."""
    try:
        return None
    except Exception:
        return None

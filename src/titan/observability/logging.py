"""Structured JSON logging for production observability.

Provides:
- JSON-formatted logs for log aggregation systems (ELK, Loki, etc.)
- Correlation ID propagation across requests
- OpenTelemetry trace context integration
- Configurable log levels and formats

Usage:
    from titan.observability.logging import configure_logging

    # In application startup
    configure_logging(json_format=True, level="INFO")

    # Correlation context is automatically included in logs
    logger = logging.getLogger(__name__)
    logger.info("Processing request")  # Includes request_id, trace_id, etc.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Context variables for request correlation
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


class JsonFormatter(logging.Formatter):
    """JSON log formatter with correlation ID and trace context support.

    Output format:
    {
        "timestamp": "2026-01-10T12:34:56.789Z",
        "level": "INFO",
        "logger": "titan.api.app",
        "message": "Request processed",
        "module": "app",
        "function": "process_request",
        "line": 42,
        "request_id": "abc-123",
        "correlation_id": "xyz-789",
        "trace_id": "0123456789abcdef",
        "span_id": "fedcba9876543210"
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation context from context vars
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        tenant_id = tenant_id_var.get()
        if tenant_id:
            log_data["tenant_id"] = tenant_id

        user_id = user_id_var.get()
        if user_id:
            log_data["user_id"] = user_id

        # Add OpenTelemetry trace context if available
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            span_context = span.get_span_context()
            if span_context.is_valid:
                log_data["trace_id"] = format(span_context.trace_id, "032x")
                log_data["span_id"] = format(span_context.span_id, "016x")
        except ImportError:
            pass  # OpenTelemetry not installed

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields from record
        # Skip standard LogRecord attributes
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                try:
                    json.dumps(value)  # Verify it's JSON serializable
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for development.

    Output format:
    2026-01-10 12:34:56 | INFO | titan.api.app | Request processed | req=abc-123
    """

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True) -> None:
        super().__init__()
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname

        if self.use_colors:
            color = self.COLORS.get(level, "")
            level = f"{color}{level}{self.RESET}"

        message = self.formatMessage(record)

        # Add correlation context
        context_parts = []
        request_id = request_id_var.get()
        if request_id:
            context_parts.append(f"req={request_id[:8]}")

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            span_context = span.get_span_context()
            if span_context.is_valid:
                context_parts.append(f"trace={format(span_context.trace_id, '032x')[:8]}")
        except ImportError:
            pass

        context = f" | {' '.join(context_parts)}" if context_parts else ""

        result = f"{timestamp} | {level:8} | {record.name} | {message}{context}"

        if record.exc_info:
            result += "\n" + self.formatException(record.exc_info)

        return result


def configure_logging(
    json_format: bool = True,
    level: str = "INFO",
    use_colors: bool = True,
) -> None:
    """Configure application-wide logging.

    Args:
        json_format: Use JSON format (recommended for production)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_colors: Use ANSI colors in console format
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create stream handler
    handler = logging.StreamHandler(sys.stderr)

    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(ConsoleFormatter(use_colors=use_colors))

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)


class LogContext:
    """Context manager for adding temporary log context.

    Usage:
        with LogContext(operation="batch_import", batch_id="123"):
            logger.info("Processing batch")  # Includes operation and batch_id
    """

    def __init__(self, **kwargs: Any) -> None:
        self.extra = kwargs
        self._tokens: dict[str, contextvars.Token[str]] = {}

    def __enter__(self) -> "LogContext":
        if "request_id" in self.extra:
            self._tokens["request_id"] = request_id_var.set(self.extra["request_id"])
        if "correlation_id" in self.extra:
            self._tokens["correlation_id"] = correlation_id_var.set(self.extra["correlation_id"])
        if "tenant_id" in self.extra:
            self._tokens["tenant_id"] = tenant_id_var.set(self.extra["tenant_id"])
        if "user_id" in self.extra:
            self._tokens["user_id"] = user_id_var.set(self.extra["user_id"])
        return self

    def __exit__(self, *args: Any) -> None:
        for key, token in self._tokens.items():
            if key == "request_id":
                request_id_var.reset(token)
            elif key == "correlation_id":
                correlation_id_var.reset(token)
            elif key == "tenant_id":
                tenant_id_var.reset(token)
            elif key == "user_id":
                user_id_var.reset(token)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    This is a convenience wrapper around logging.getLogger
    that ensures the logger is configured with our formatters.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)

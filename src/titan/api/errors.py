"""IDTA-compliant error responses for Titan-AAS.

Implements the Result/Message structure from IDTA-01002 Part 2
for consistent error handling across all API endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Type of message in error response."""

    ERROR = "Error"
    WARNING = "Warning"
    INFO = "Info"
    EXCEPTION = "Exception"


class Message(BaseModel):
    """IDTA-compliant error message."""

    model_config = {"extra": "forbid", "populate_by_name": True}

    code: str
    message_type: MessageType = Field(alias="messageType")
    text: str
    timestamp: str | None = None


class Result(BaseModel):
    """IDTA-compliant result wrapper for errors."""

    model_config = {"extra": "forbid"}

    messages: list[Message]


class AasApiError(HTTPException):
    """Base exception for AAS API errors."""

    def __init__(
        self,
        status_code: int,
        code: str,
        text: str,
        message_type: MessageType = MessageType.ERROR,
    ):
        self.code = code
        self.text = text
        self.message_type = message_type
        super().__init__(status_code=status_code, detail=text)

    def to_result(self) -> Result:
        """Convert to IDTA Result format."""
        return Result(
            messages=[
                Message(
                    code=self.code,
                    messageType=self.message_type,
                    text=self.text,
                    timestamp=datetime.now(UTC).isoformat(),
                )
            ]
        )


class NotFoundError(AasApiError):
    """Resource not found (404)."""

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(
            status_code=404,
            code="NotFound",
            text=f"{resource_type} with identifier '{identifier}' not found",
        )


class ConflictError(AasApiError):
    """Resource already exists (409)."""

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(
            status_code=409,
            code="Conflict",
            text=f"{resource_type} with identifier '{identifier}' already exists",
        )


class BadRequestError(AasApiError):
    """Invalid request (400)."""

    def __init__(self, text: str):
        super().__init__(
            status_code=400,
            code="BadRequest",
            text=text,
        )


class InvalidBase64UrlError(AasApiError):
    """Invalid Base64URL identifier (400)."""

    def __init__(self, identifier: str):
        super().__init__(
            status_code=400,
            code="InvalidBase64Url",
            text=f"Invalid Base64URL encoded identifier: '{identifier}'",
        )


class PreconditionFailedError(AasApiError):
    """ETag precondition failed (412)."""

    def __init__(self) -> None:
        super().__init__(
            status_code=412,
            code="PreconditionFailed",
            text="The resource was modified since the specified ETag",
        )


class InternalServerError(AasApiError):
    """Internal server error (500)."""

    def __init__(self, text: str = "An unexpected error occurred"):
        super().__init__(
            status_code=500,
            code="InternalServerError",
            text=text,
            message_type=MessageType.EXCEPTION,
        )


async def aas_api_exception_handler(request: Request, exc: AasApiError) -> JSONResponse:
    """Exception handler for AAS API errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_result().model_dump(by_alias=True),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Exception handler for unexpected errors."""
    return JSONResponse(
        status_code=500,
        content=Result(
            messages=[
                Message(
                    code="InternalServerError",
                    messageType=MessageType.EXCEPTION,
                    text="An unexpected error occurred",
                    timestamp=datetime.now(UTC).isoformat(),
                )
            ]
        ).model_dump(by_alias=True),
    )

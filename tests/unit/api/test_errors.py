"""Tests for IDTA-compliant error responses."""

from titan.api.errors import (
    BadRequestError,
    ConflictError,
    InternalServerError,
    InvalidBase64UrlError,
    Message,
    MessageType,
    NotFoundError,
    PreconditionFailedError,
    Result,
)


class TestMessageType:
    """Test MessageType enum."""

    def test_message_types(self) -> None:
        """All required message types exist."""
        assert MessageType.ERROR.value == "Error"
        assert MessageType.WARNING.value == "Warning"
        assert MessageType.INFO.value == "Info"
        assert MessageType.EXCEPTION.value == "Exception"


class TestMessage:
    """Test Message model."""

    def test_basic_message(self) -> None:
        """Message with required fields."""
        msg = Message(code="NotFound", message_type=MessageType.ERROR, text="Resource not found")
        assert msg.code == "NotFound"
        assert msg.message_type == MessageType.ERROR
        assert msg.text == "Resource not found"

    def test_message_with_timestamp(self) -> None:
        """Message with optional timestamp."""
        msg = Message(
            code="Error",
            message_type=MessageType.ERROR,
            text="Test",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert msg.timestamp == "2024-01-01T00:00:00Z"


class TestResult:
    """Test Result wrapper."""

    def test_result_with_messages(self) -> None:
        """Result contains list of messages."""
        result = Result(
            messages=[
                Message(code="E1", message_type=MessageType.ERROR, text="First"),
                Message(code="E2", message_type=MessageType.WARNING, text="Second"),
            ]
        )
        assert len(result.messages) == 2


class TestNotFoundError:
    """Test NotFoundError."""

    def test_not_found_error(self) -> None:
        """NotFoundError has correct status and message."""
        error = NotFoundError("Submodel", "urn:example:submodel:1")
        assert error.status_code == 404
        assert error.code == "NotFound"
        assert "Submodel" in error.text
        assert "urn:example:submodel:1" in error.text

    def test_not_found_to_result(self) -> None:
        """NotFoundError converts to IDTA Result."""
        error = NotFoundError("AAS", "test-id")
        result = error.to_result()
        assert len(result.messages) == 1
        assert result.messages[0].code == "NotFound"
        assert result.messages[0].message_type == MessageType.ERROR


class TestConflictError:
    """Test ConflictError."""

    def test_conflict_error(self) -> None:
        """ConflictError has correct status and message."""
        error = ConflictError("AssetAdministrationShell", "urn:example:aas:1")
        assert error.status_code == 409
        assert error.code == "Conflict"
        assert "already exists" in error.text


class TestBadRequestError:
    """Test BadRequestError."""

    def test_bad_request_error(self) -> None:
        """BadRequestError has correct status."""
        error = BadRequestError("Invalid JSON payload")
        assert error.status_code == 400
        assert error.code == "BadRequest"
        assert error.text == "Invalid JSON payload"


class TestInvalidBase64UrlError:
    """Test InvalidBase64UrlError."""

    def test_invalid_base64url_error(self) -> None:
        """InvalidBase64UrlError has correct status and message."""
        error = InvalidBase64UrlError("invalid!!!")
        assert error.status_code == 400
        assert error.code == "InvalidBase64Url"
        assert "invalid!!!" in error.text


class TestPreconditionFailedError:
    """Test PreconditionFailedError."""

    def test_precondition_failed_error(self) -> None:
        """PreconditionFailedError has correct status."""
        error = PreconditionFailedError()
        assert error.status_code == 412
        assert error.code == "PreconditionFailed"
        assert "ETag" in error.text


class TestInternalServerError:
    """Test InternalServerError."""

    def test_internal_server_error(self) -> None:
        """InternalServerError has correct status and type."""
        error = InternalServerError("Database connection failed")
        assert error.status_code == 500
        assert error.code == "InternalServerError"
        assert error.message_type == MessageType.EXCEPTION

    def test_internal_server_error_default_message(self) -> None:
        """InternalServerError has default message."""
        error = InternalServerError()
        assert "unexpected error" in error.text

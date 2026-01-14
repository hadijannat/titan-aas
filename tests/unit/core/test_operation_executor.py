"""Tests for operation executor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from titan.core.operation_executor import (
    InvokeOperationRequest,
    OperationArgument,
    OperationExecutor,
    OperationValidationError,
)
from titan.events.schemas import OperationExecutionState


def make_operation(
    input_variables: list[dict] | None = None,
    output_variables: list[dict] | None = None,
    inoutput_variables: list[dict] | None = None,
) -> MagicMock:
    """Create a mock Operation element."""
    operation = MagicMock()
    operation.input_variables = input_variables
    operation.output_variables = output_variables
    operation.inoutput_variables = inoutput_variables
    return operation


def make_operation_variable(id_short: str) -> MagicMock:
    """Create a mock OperationVariable."""
    var = MagicMock()
    var.value = MagicMock()
    var.value.id_short = id_short
    return var


class TestOperationArgument:
    """Test OperationArgument model."""

    def test_create_argument_with_alias(self) -> None:
        """Create argument using camelCase alias."""
        arg = OperationArgument.model_validate({"idShort": "speed", "value": 100})
        assert arg.id_short == "speed"
        assert arg.value == 100
        assert arg.value_type is None

    def test_create_argument_with_value_type(self) -> None:
        """Create argument with valueType."""
        arg = OperationArgument.model_validate(
            {"idShort": "temp", "value": 23.5, "valueType": "xs:double"}
        )
        assert arg.id_short == "temp"
        assert arg.value == 23.5
        assert arg.value_type == "xs:double"

    def test_argument_model_dump(self) -> None:
        """Argument serializes with aliases."""
        arg = OperationArgument.model_validate(
            {"idShort": "speed", "value": 100, "valueType": "xs:int"}
        )
        dumped = arg.model_dump(by_alias=True)
        assert dumped["idShort"] == "speed"
        assert dumped["value"] == 100
        assert dumped["valueType"] == "xs:int"


class TestInvokeOperationRequest:
    """Test InvokeOperationRequest model."""

    def test_empty_request(self) -> None:
        """Create request with no arguments."""
        request = InvokeOperationRequest.model_validate({})
        assert request.input_arguments is None
        assert request.inoutput_arguments is None
        assert request.timeout is None

    def test_request_with_input_arguments(self) -> None:
        """Create request with input arguments."""
        request = InvokeOperationRequest.model_validate(
            {
                "inputArguments": [
                    {"idShort": "speed", "value": 100},
                    {"idShort": "direction", "value": "forward"},
                ]
            }
        )
        assert request.input_arguments is not None
        assert len(request.input_arguments) == 2
        assert request.input_arguments[0].id_short == "speed"
        assert request.input_arguments[0].value == 100

    def test_request_with_timeout(self) -> None:
        """Create request with timeout."""
        request = InvokeOperationRequest.model_validate({"timeout": 5000})
        assert request.timeout == 5000

    def test_timeout_validation_max(self) -> None:
        """Timeout cannot exceed 1 hour."""
        with pytest.raises(Exception):  # ValidationError
            InvokeOperationRequest.model_validate({"timeout": 4000000})


class TestOperationExecutor:
    """Test OperationExecutor class."""

    @pytest.mark.asyncio
    async def test_invoke_emits_event(self) -> None:
        """Invoke emits OperationInvocationEvent."""
        event_bus = AsyncMock()
        executor = OperationExecutor(event_bus)

        # Operation with no input variables
        operation = make_operation()
        request = InvokeOperationRequest()

        result = await executor.invoke(
            submodel_id="urn:test:submodel:1",
            id_short_path="StartPump",
            operation=operation,
            request=request,
            requested_by="test@example.com",
        )

        assert result.invocation_id is not None
        assert result.execution_state == OperationExecutionState.PENDING
        assert event_bus.publish.called

    @pytest.mark.asyncio
    async def test_invoke_with_valid_inputs(self) -> None:
        """Invoke with valid input arguments."""
        event_bus = AsyncMock()
        executor = OperationExecutor(event_bus)

        # Operation with declared input variable
        operation = make_operation(input_variables=[make_operation_variable("speed")])
        request = InvokeOperationRequest.model_validate(
            {"inputArguments": [{"idShort": "speed", "value": 100}]}
        )

        result = await executor.invoke(
            submodel_id="urn:test:submodel:1",
            id_short_path="StartPump",
            operation=operation,
            request=request,
        )

        assert result.invocation_id is not None
        assert result.execution_state == OperationExecutionState.PENDING

    @pytest.mark.asyncio
    async def test_invoke_rejects_unknown_input(self) -> None:
        """Invoke rejects unknown input arguments."""
        event_bus = AsyncMock()
        executor = OperationExecutor(event_bus)

        # Operation with declared input variable
        operation = make_operation(input_variables=[make_operation_variable("speed")])
        # Request with unknown argument
        request = InvokeOperationRequest.model_validate(
            {"inputArguments": [{"idShort": "unknown_param", "value": 100}]}
        )

        with pytest.raises(OperationValidationError) as exc_info:
            await executor.invoke(
                submodel_id="urn:test:submodel:1",
                id_short_path="StartPump",
                operation=operation,
                request=request,
            )

        assert "Unknown input argument" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_invoke_rejects_inputs_when_none_declared(self) -> None:
        """Invoke rejects inputs when operation has no input variables."""
        event_bus = AsyncMock()
        executor = OperationExecutor(event_bus)

        # Operation with no input variables
        operation = make_operation(input_variables=None)
        request = InvokeOperationRequest.model_validate(
            {"inputArguments": [{"idShort": "speed", "value": 100}]}
        )

        with pytest.raises(OperationValidationError) as exc_info:
            await executor.invoke(
                submodel_id="urn:test:submodel:1",
                id_short_path="StartPump",
                operation=operation,
                request=request,
            )

        assert "does not accept input arguments" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_invoke_with_inoutput_arguments(self) -> None:
        """Invoke with in-out arguments."""
        event_bus = AsyncMock()
        executor = OperationExecutor(event_bus)

        # Operation with declared inoutput variable
        operation = make_operation(inoutput_variables=[make_operation_variable("counter")])
        request = InvokeOperationRequest.model_validate(
            {"inoutputArguments": [{"idShort": "counter", "value": 5}]}
        )

        result = await executor.invoke(
            submodel_id="urn:test:submodel:1",
            id_short_path="IncrementCounter",
            operation=operation,
            request=request,
        )

        assert result.invocation_id is not None
        assert result.execution_state == OperationExecutionState.PENDING


class TestOperationValidationError:
    """Test OperationValidationError exception."""

    def test_error_with_message(self) -> None:
        """Error stores message."""
        error = OperationValidationError("Invalid input")
        assert error.message == "Invalid input"
        assert error.field is None

    def test_error_with_field(self) -> None:
        """Error stores field path."""
        error = OperationValidationError("Invalid input", field="inputArguments.speed")
        assert error.message == "Invalid input"
        assert error.field == "inputArguments.speed"

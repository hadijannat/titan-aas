"""Operation executor for invoking AAS Operation elements.

Handles validation of input arguments against declared input variables
and emits OperationInvocationEvents for downstream connectors to execute.

Example:
    from titan.core.operation_executor import OperationExecutor

    executor = OperationExecutor(event_bus)

    # Invoke an operation
    result = await executor.invoke(
        submodel_id="urn:example:submodel:1",
        id_short_path="StartPump",
        operation=operation_element,
        input_arguments=[{"idShort": "speed", "value": 100}],
        requested_by="user@example.com",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from titan.core.ids import encode_id_to_b64url
from titan.events.publisher import publish_operation_invoked
from titan.events.schemas import OperationExecutionState

if TYPE_CHECKING:
    from titan.core.model.submodel_elements import Operation, OperationVariable
    from titan.events.bus import EventBus


class OperationArgument(BaseModel):
    """A single argument value for an operation invocation."""

    id_short: str = Field(alias="idShort", description="The idShort of the variable")
    value: Any = Field(description="The value to pass")
    value_type: str | None = Field(
        default=None, alias="valueType", description="Optional XSD type hint"
    )


class InvokeOperationRequest(BaseModel):
    """Request body for invoking an operation."""

    input_arguments: list[OperationArgument] | None = Field(
        default=None,
        alias="inputArguments",
        description="Input argument values",
    )
    inoutput_arguments: list[OperationArgument] | None = Field(
        default=None,
        alias="inoutputArguments",
        description="In-out argument values",
    )
    timeout: int | None = Field(
        default=None,
        ge=0,
        le=3600000,  # Max 1 hour
        description="Timeout in milliseconds for async execution",
    )


@dataclass
class InvokeOperationResult:
    """Result of an operation invocation request."""

    invocation_id: str
    execution_state: OperationExecutionState
    output_arguments: list[dict[str, Any]] | None = None
    inoutput_arguments: list[dict[str, Any]] | None = None
    error_message: str | None = None
    error_code: str | None = None


class OperationValidationError(Exception):
    """Raised when operation input validation fails."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class OperationExecutor:
    """Executor for AAS Operation element invocations.

    Validates input arguments against declared input variables and
    emits events for downstream connectors to execute.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    async def invoke(
        self,
        submodel_id: str,
        id_short_path: str,
        operation: Operation,
        request: InvokeOperationRequest,
        requested_by: str | None = None,
        correlation_id: str | None = None,
    ) -> InvokeOperationResult:
        """Invoke an operation and emit an event for execution.

        This method validates input arguments, generates an invocation ID,
        and publishes an OperationInvocationEvent. Downstream connectors
        (OPC-UA, Modbus, HTTP) subscribe to these events and handle execution.

        Args:
            submodel_id: ID of the submodel containing the operation
            id_short_path: Path to the Operation element
            operation: The Operation submodel element definition
            request: The invocation request with input arguments
            requested_by: User/service invoking the operation
            correlation_id: Optional ID for mapping to external systems

        Returns:
            InvokeOperationResult with invocation ID and initial state

        Raises:
            OperationValidationError: If input arguments are invalid
        """
        # Validate input arguments against declared variables
        self._validate_input_arguments(operation, request.input_arguments)
        self._validate_inoutput_arguments(operation, request.inoutput_arguments)

        # Generate invocation ID
        invocation_id = str(uuid4())
        submodel_id_b64 = encode_id_to_b64url(submodel_id)

        # Convert arguments to dicts for event serialization
        input_args = (
            [arg.model_dump(by_alias=True) for arg in request.input_arguments]
            if request.input_arguments
            else None
        )
        inoutput_args = (
            [arg.model_dump(by_alias=True) for arg in request.inoutput_arguments]
            if request.inoutput_arguments
            else None
        )

        # Publish invocation event
        await publish_operation_invoked(
            event_bus=self.event_bus,
            invocation_id=invocation_id,
            submodel_id=submodel_id,
            submodel_id_b64=submodel_id_b64,
            id_short_path=id_short_path,
            input_arguments=input_args,
            inoutput_arguments=inoutput_args,
            correlation_id=correlation_id,
            timeout_ms=request.timeout,
            requested_by=requested_by,
        )

        return InvokeOperationResult(
            invocation_id=invocation_id,
            execution_state=OperationExecutionState.PENDING,
        )

    def _validate_input_arguments(
        self,
        operation: Operation,
        input_arguments: list[OperationArgument] | None,
    ) -> None:
        """Validate input arguments against declared input variables.

        Args:
            operation: The Operation element definition
            input_arguments: Input argument values from the request

        Raises:
            OperationValidationError: If validation fails
        """
        declared_inputs = operation.input_variables or []

        if not declared_inputs and input_arguments:
            raise OperationValidationError(
                "Operation does not accept input arguments",
                field="inputArguments",
            )

        if not input_arguments:
            # Check if any inputs are required (we assume all are optional for now)
            return

        # Build a map of declared variable idShorts
        declared_map = self._build_variable_map(declared_inputs)

        # Validate each provided argument
        for arg in input_arguments:
            if arg.id_short not in declared_map:
                raise OperationValidationError(
                    f"Unknown input argument: {arg.id_short}",
                    field=f"inputArguments.{arg.id_short}",
                )

            # Type validation could be added here based on the declared variable's valueType

    def _validate_inoutput_arguments(
        self,
        operation: Operation,
        inoutput_arguments: list[OperationArgument] | None,
    ) -> None:
        """Validate in-out arguments against declared inoutput variables.

        Args:
            operation: The Operation element definition
            inoutput_arguments: In-out argument values from the request

        Raises:
            OperationValidationError: If validation fails
        """
        declared_inoutputs = operation.inoutput_variables or []

        if not declared_inoutputs and inoutput_arguments:
            raise OperationValidationError(
                "Operation does not accept in-out arguments",
                field="inoutputArguments",
            )

        if not inoutput_arguments:
            return

        # Build a map of declared variable idShorts
        declared_map = self._build_variable_map(declared_inoutputs)

        # Validate each provided argument
        for arg in inoutput_arguments:
            if arg.id_short not in declared_map:
                raise OperationValidationError(
                    f"Unknown in-out argument: {arg.id_short}",
                    field=f"inoutputArguments.{arg.id_short}",
                )

    def _build_variable_map(
        self, variables: list[OperationVariable]
    ) -> dict[str, OperationVariable]:
        """Build a map of variable idShort to variable definition.

        Args:
            variables: List of OperationVariable definitions

        Returns:
            Dict mapping idShort to OperationVariable
        """
        result: dict[str, OperationVariable] = {}
        for var in variables:
            # The value field contains the SubmodelElement describing the variable
            element = var.value
            if hasattr(element, "id_short") and element.id_short:
                result[element.id_short] = var
        return result

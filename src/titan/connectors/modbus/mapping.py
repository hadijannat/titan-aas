"""Modbus register mapping system.

Maps AAS submodel elements to Modbus registers with support for data type
conversion and scaling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RegisterMapping:
    """Mapping between AAS element and Modbus register.

    Attributes:
        submodel_id: AAS submodel identifier
        element_path: Path to element within submodel (e.g., "Temperature")
        register_address: Modbus register address (0-based)
        register_type: Type of register (coil, discrete_input, holding_register, input_register)
        data_type: Target data type (bool, int, float, string)
        scale_factor: Multiplier for register value (e.g., 0.1 for tenths)
        offset: Value to add after scaling (e.g., for temperature offset)
        direction: Data flow direction (read, write, both)
        description: Human-readable description
    """

    submodel_id: str
    element_path: str
    register_address: int
    register_type: str
    data_type: str = "int"
    scale_factor: float = 1.0
    offset: float = 0.0
    direction: str = "read"  # read, write, both
    description: str = ""

    def __post_init__(self) -> None:
        """Validate mapping configuration."""
        # Validate register type
        valid_register_types = {
            "coil",
            "discrete_input",
            "holding_register",
            "input_register",
        }
        if self.register_type not in valid_register_types:
            raise ValueError(
                f"Invalid register_type: {self.register_type}. "
                f"Must be one of {valid_register_types}"
            )

        # Validate data type
        valid_data_types = {"bool", "int", "float", "string"}
        if self.data_type not in valid_data_types:
            raise ValueError(
                f"Invalid data_type: {self.data_type}. Must be one of {valid_data_types}"
            )

        # Validate direction
        valid_directions = {"read", "write", "both"}
        if self.direction not in valid_directions:
            raise ValueError(
                f"Invalid direction: {self.direction}. Must be one of {valid_directions}"
            )

        # Validate register type vs data type compatibility
        if self.register_type in ("coil", "discrete_input") and self.data_type != "bool":
            raise ValueError(
                f"Register type {self.register_type} requires data_type='bool', "
                f"got '{self.data_type}'"
            )

        # Validate write operations
        if self.direction in ("write", "both"):
            if self.register_type in ("discrete_input", "input_register"):
                raise ValueError(
                    f"Cannot write to read-only register type: {self.register_type}"
                )

    @property
    def can_read(self) -> bool:
        """Check if this mapping supports read operations."""
        return self.direction in ("read", "both")

    @property
    def can_write(self) -> bool:
        """Check if this mapping supports write operations."""
        return self.direction in ("write", "both")

    def register_to_value(self, register_value: int | bool) -> Any:
        """Convert raw register value to AAS element value.

        Args:
            register_value: Raw value from Modbus register

        Returns:
            Converted value for AAS element
        """
        if self.data_type == "bool":
            return bool(register_value)

        if self.data_type == "int":
            if isinstance(register_value, bool):
                return int(register_value)
            # Apply scaling and offset
            return int(register_value * self.scale_factor + self.offset)

        if self.data_type == "float":
            if isinstance(register_value, bool):
                return float(register_value)
            # Apply scaling and offset
            return float(register_value * self.scale_factor + self.offset)

        if self.data_type == "string":
            # String encoding is handled separately (multiple registers)
            return str(register_value)

        return register_value

    def value_to_register(self, value: Any) -> int | bool:
        """Convert AAS element value to raw register value.

        Args:
            value: AAS element value

        Returns:
            Raw value for Modbus register

        Raises:
            ValueError: If value cannot be converted
        """
        if self.data_type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "on", "yes")
            return bool(value)

        if self.data_type in ("int", "float"):
            # Convert to numeric
            if isinstance(value, str):
                numeric_value = float(value)
            else:
                numeric_value = float(value)

            # Remove offset and reverse scaling
            register_value = (numeric_value - self.offset) / self.scale_factor

            # Validate range for holding registers (0-65535)
            if self.register_type == "holding_register":
                if not 0 <= register_value <= 65535:
                    raise ValueError(
                        f"Value {register_value} out of range for holding register (0-65535)"
                    )

            return int(register_value)

        if self.data_type == "string":
            # String encoding is handled separately
            raise NotImplementedError("String encoding requires multiple registers")

        raise ValueError(f"Cannot convert value to register: {value}")


class ModbusMapper:
    """Manages mappings between AAS elements and Modbus registers.

    Provides lookup and conversion utilities for bidirectional mapping.
    """

    def __init__(self, mappings: list[RegisterMapping] | None = None):
        """Initialize mapper.

        Args:
            mappings: List of register mappings
        """
        self.mappings = mappings or []
        self._by_element: dict[tuple[str, str], RegisterMapping] = {}
        self._by_register: dict[tuple[str, int], RegisterMapping] = {}
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """Rebuild lookup indexes for fast access."""
        self._by_element.clear()
        self._by_register.clear()

        for mapping in self.mappings:
            # Index by (submodel_id, element_path)
            element_key = (mapping.submodel_id, mapping.element_path)
            self._by_element[element_key] = mapping

            # Index by (register_type, register_address)
            register_key = (mapping.register_type, mapping.register_address)
            self._by_register[register_key] = mapping

    def add_mapping(self, mapping: RegisterMapping) -> None:
        """Add a new mapping.

        Args:
            mapping: Register mapping to add
        """
        self.mappings.append(mapping)
        self._rebuild_indexes()
        logger.info(
            f"Added mapping: {mapping.submodel_id}/{mapping.element_path} <-> "
            f"{mapping.register_type}:{mapping.register_address}"
        )

    def get_by_element(self, submodel_id: str, element_path: str) -> RegisterMapping | None:
        """Find mapping by AAS element.

        Args:
            submodel_id: Submodel identifier
            element_path: Element path within submodel

        Returns:
            RegisterMapping if found, None otherwise
        """
        return self._by_element.get((submodel_id, element_path))

    def get_by_register(
        self, register_type: str, register_address: int
    ) -> RegisterMapping | None:
        """Find mapping by Modbus register.

        Args:
            register_type: Type of register
            register_address: Register address

        Returns:
            RegisterMapping if found, None otherwise
        """
        return self._by_register.get((register_type, register_address))

    def get_readable_mappings(self) -> list[RegisterMapping]:
        """Get all mappings that support read operations.

        Returns:
            List of mappings with read direction
        """
        return [m for m in self.mappings if m.can_read]

    def get_writable_mappings(self) -> list[RegisterMapping]:
        """Get all mappings that support write operations.

        Returns:
            List of mappings with write direction
        """
        return [m for m in self.mappings if m.can_write]

    def clear(self) -> None:
        """Remove all mappings."""
        self.mappings.clear()
        self._rebuild_indexes()
        logger.info("Cleared all mappings")

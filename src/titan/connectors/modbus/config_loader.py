"""Modbus mapping configuration loader.

Loads register mapping configuration from JSON files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from titan.connectors.modbus.mapping import ModbusMapper, RegisterMapping

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


class ModbusConfigLoader:
    """Loads Modbus register mappings from JSON configuration files.

    Expected JSON structure:
    {
        "mappings": [
            {
                "submodel_id": "urn:example:submodel:sensors:1",
                "element_path": "Temperature",
                "register_address": 100,
                "register_type": "holding_register",
                "data_type": "float",
                "scale_factor": 0.1,
                "offset": 0.0,
                "direction": "read",
                "description": "Temperature sensor in tenths of degrees C"
            }
        ]
    }
    """

    @staticmethod
    def load_from_file(file_path: str | Path) -> ModbusMapper:
        """Load mappings from JSON file.

        Args:
            file_path: Path to JSON configuration file

        Returns:
            ModbusMapper with loaded mappings

        Raises:
            FileNotFoundError: If file does not exist
            ConfigValidationError: If configuration is invalid
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        logger.info(f"Loading Modbus mappings from {file_path}")

        try:
            with path.open("r") as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Invalid JSON in {file_path}: {e}") from e

        return ModbusConfigLoader.load_from_dict(config_data)

    @staticmethod
    def load_from_dict(config_data: dict[str, Any]) -> ModbusMapper:
        """Load mappings from dictionary.

        Args:
            config_data: Configuration dictionary

        Returns:
            ModbusMapper with loaded mappings

        Raises:
            ConfigValidationError: If configuration is invalid
        """
        # Validate top-level structure
        if not isinstance(config_data, dict):
            raise ConfigValidationError("Configuration must be a JSON object")

        if "mappings" not in config_data:
            raise ConfigValidationError("Configuration must contain 'mappings' key")

        mappings_list = config_data["mappings"]
        if not isinstance(mappings_list, list):
            raise ConfigValidationError("'mappings' must be a list")

        # Parse each mapping
        mappings: list[RegisterMapping] = []
        for i, mapping_dict in enumerate(mappings_list):
            try:
                mapping = ModbusConfigLoader._parse_mapping(mapping_dict)
                mappings.append(mapping)
            except (ValueError, TypeError, KeyError) as e:
                raise ConfigValidationError(f"Invalid mapping at index {i}: {e}") from e

        logger.info(f"Loaded {len(mappings)} Modbus mappings")
        return ModbusMapper(mappings)

    @staticmethod
    def _parse_mapping(mapping_dict: dict[str, Any]) -> RegisterMapping:
        """Parse a single mapping from dictionary.

        Args:
            mapping_dict: Mapping dictionary

        Returns:
            RegisterMapping object

        Raises:
            ValueError: If mapping is invalid
            KeyError: If required field is missing
        """
        # Required fields
        submodel_id = mapping_dict["submodel_id"]
        element_path = mapping_dict["element_path"]
        register_address = mapping_dict["register_address"]
        register_type = mapping_dict["register_type"]

        # Optional fields with defaults
        data_type = mapping_dict.get("data_type", "int")
        scale_factor = mapping_dict.get("scale_factor", 1.0)
        offset = mapping_dict.get("offset", 0.0)
        direction = mapping_dict.get("direction", "read")
        description = mapping_dict.get("description", "")

        # Validate types
        if not isinstance(submodel_id, str):
            raise ValueError("submodel_id must be a string")
        if not isinstance(element_path, str):
            raise ValueError("element_path must be a string")
        if not isinstance(register_address, int):
            raise ValueError("register_address must be an integer")
        if not isinstance(register_type, str):
            raise ValueError("register_type must be a string")
        if not isinstance(data_type, str):
            raise ValueError("data_type must be a string")
        if not isinstance(scale_factor, (int, float)):
            raise ValueError("scale_factor must be a number")
        if not isinstance(offset, (int, float)):
            raise ValueError("offset must be a number")
        if not isinstance(direction, str):
            raise ValueError("direction must be a string")
        if not isinstance(description, str):
            raise ValueError("description must be a string")

        # Validate register address range
        if not 0 <= register_address <= 65535:
            raise ValueError(f"register_address must be 0-65535, got {register_address}")

        # Create mapping (validation happens in __post_init__)
        return RegisterMapping(
            submodel_id=submodel_id,
            element_path=element_path,
            register_address=register_address,
            register_type=register_type,
            data_type=data_type,
            scale_factor=scale_factor,
            offset=offset,
            direction=direction,
            description=description,
        )

    @staticmethod
    def save_to_file(mapper: ModbusMapper, file_path: str | Path) -> None:
        """Save mappings to JSON file.

        Args:
            mapper: ModbusMapper to save
            file_path: Path to output JSON file
        """
        path = Path(file_path)

        # Convert mappings to dictionaries
        mappings_list = []
        for mapping in mapper.mappings:
            mapping_dict = {
                "submodel_id": mapping.submodel_id,
                "element_path": mapping.element_path,
                "register_address": mapping.register_address,
                "register_type": mapping.register_type,
                "data_type": mapping.data_type,
                "scale_factor": mapping.scale_factor,
                "offset": mapping.offset,
                "direction": mapping.direction,
                "description": mapping.description,
            }
            mappings_list.append(mapping_dict)

        config_data = {"mappings": mappings_list}

        # Write to file
        with path.open("w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Saved {len(mappings_list)} Modbus mappings to {file_path}")

"""Configuration loader for OPC-UA node mappings.

Loads JSON configuration files that define mappings between AAS elements
and OPC-UA nodes for bidirectional synchronization.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from titan.connectors.opcua.mapping import AasOpcUaMapper, NodeMapping

logger = logging.getLogger(__name__)


class OpcUaMappingConfig:
    """Configuration for OPC-UA node mappings."""

    def __init__(self, config_path: str | Path | None = None):
        """Initialize mapping configuration.

        Args:
            config_path: Path to JSON configuration file
        """
        self.config_path = Path(config_path) if config_path else None
        self.mappings: list[dict[str, Any]] = []
        self._mapper: AasOpcUaMapper | None = None

    def load(self) -> AasOpcUaMapper:
        """Load configuration from JSON file.

        Returns:
            Configured AasOpcUaMapper instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        if not self.config_path:
            logger.info("No OPC-UA mapping config path provided, using empty mapper")
            return AasOpcUaMapper()

        if not self.config_path.exists():
            raise FileNotFoundError(f"OPC-UA mapping config not found: {self.config_path}")

        try:
            with open(self.config_path) as f:
                config_data = json.load(f)

            # Validate config structure
            if not isinstance(config_data, dict):
                raise ValueError("Config must be a JSON object")

            if "mappings" not in config_data:
                raise ValueError("Config must contain 'mappings' key")

            if not isinstance(config_data["mappings"], list):
                raise ValueError("'mappings' must be a list")

            self.mappings = config_data["mappings"]

            # Create mapper and add mappings
            mapper = AasOpcUaMapper()
            for mapping_dict in self.mappings:
                try:
                    mapping = self._parse_mapping(mapping_dict)
                    mapper.add_mapping(mapping)
                except Exception as e:
                    logger.warning(f"Skipping invalid mapping: {e}")
                    continue

            logger.info(f"Loaded {len(self.mappings)} OPC-UA mappings from {self.config_path}")
            self._mapper = mapper
            return mapper

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            logger.error(f"Failed to load OPC-UA mapping config: {e}")
            raise

    def _parse_mapping(self, mapping_dict: dict[str, Any]) -> NodeMapping:
        """Parse a mapping dictionary into a NodeMapping object.

        Args:
            mapping_dict: Dictionary with mapping configuration

        Returns:
            NodeMapping object

        Raises:
            ValueError: If required fields are missing
        """
        required_fields = ["submodel_id", "element_path", "node_id"]
        for field in required_fields:
            if field not in mapping_dict:
                raise ValueError(f"Missing required field: {field}")

        return NodeMapping(
            id_short_path=mapping_dict["element_path"],
            node_id=mapping_dict["node_id"],
            submodel_id=mapping_dict["submodel_id"],
            data_type=mapping_dict.get("data_type"),
            direction=mapping_dict.get("direction", "bidirectional"),
        )

    def get_mapper(self) -> AasOpcUaMapper:
        """Get the configured mapper instance.

        Returns:
            AasOpcUaMapper instance

        Raises:
            RuntimeError: If load() hasn't been called yet
        """
        if self._mapper is None:
            raise RuntimeError("Mapper not loaded. Call load() first.")
        return self._mapper

    def get_read_mappings(self) -> list[dict[str, Any]]:
        """Get mappings configured for reading (OPC-UA → AAS).

        Returns:
            List of mapping configurations with direction="read" or "bidirectional"
        """
        return [m for m in self.mappings if m.get("direction") in ("read", "bidirectional")]

    def get_write_mappings(self) -> list[dict[str, Any]]:
        """Get mappings configured for writing (AAS → OPC-UA).

        Returns:
            List of mapping configurations with direction="write" or "bidirectional"
        """
        return [m for m in self.mappings if m.get("direction") in ("write", "bidirectional")]


def load_mapping_config(config_path: str | Path | None = None) -> AasOpcUaMapper:
    """Load OPC-UA mapping configuration from file.

    Convenience function for loading mappings.

    Args:
        config_path: Path to JSON configuration file

    Returns:
        Configured AasOpcUaMapper instance
    """
    config = OpcUaMappingConfig(config_path)
    return config.load()

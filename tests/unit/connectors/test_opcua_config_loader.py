"""Tests for OPC-UA configuration loader."""

import json
from pathlib import Path

import pytest

from titan.connectors.opcua.config_loader import OpcUaMappingConfig, load_mapping_config


class TestOpcUaMappingConfig:
    """Test OPC-UA mapping configuration loader."""

    @pytest.fixture
    def valid_config_data(self) -> dict:
        """Create valid configuration data."""
        return {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:1",
                    "element_path": "Temperature",
                    "node_id": "ns=2;s=Temperature",
                    "data_type": "xs:double",
                    "direction": "bidirectional",
                },
                {
                    "submodel_id": "urn:example:submodel:1",
                    "element_path": "Pressure",
                    "node_id": "ns=2;s=Pressure",
                    "direction": "read",
                },
            ]
        }

    @pytest.fixture
    def config_file(self, valid_config_data: dict, tmp_path: Path) -> Path:
        """Create temporary config file."""
        config_path = tmp_path / "opcua_mappings.json"
        with open(config_path, "w") as f:
            json.dump(valid_config_data, f)
        return config_path

    def test_load_with_no_config_path(self) -> None:
        """Loading without config path returns empty mapper."""
        config = OpcUaMappingConfig(None)
        mapper = config.load()

        assert mapper is not None
        assert len(config.mappings) == 0

    def test_load_with_nonexistent_file(self, tmp_path: Path) -> None:
        """Loading nonexistent file raises FileNotFoundError."""
        config_path = tmp_path / "nonexistent.json"
        config = OpcUaMappingConfig(config_path)

        with pytest.raises(FileNotFoundError):
            config.load()

    def test_load_valid_config(self, config_file: Path) -> None:
        """Load valid configuration successfully."""
        config = OpcUaMappingConfig(config_file)
        mapper = config.load()

        assert mapper is not None
        assert len(config.mappings) == 2

        # Verify first mapping
        node_id = mapper.get_node_id("urn:example:submodel:1", "Temperature")
        assert node_id == "ns=2;s=Temperature"

        # Verify second mapping
        node_id = mapper.get_node_id("urn:example:submodel:1", "Pressure")
        assert node_id == "ns=2;s=Pressure"

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Loading invalid JSON raises ValueError."""
        config_path = tmp_path / "invalid.json"
        with open(config_path, "w") as f:
            f.write("{ invalid json }")

        config = OpcUaMappingConfig(config_path)

        with pytest.raises(ValueError, match="Invalid JSON"):
            config.load()

    def test_load_missing_mappings_key(self, tmp_path: Path) -> None:
        """Loading config without 'mappings' key raises ValueError."""
        config_path = tmp_path / "no_mappings.json"
        with open(config_path, "w") as f:
            json.dump({"other_key": []}, f)

        config = OpcUaMappingConfig(config_path)

        with pytest.raises(ValueError, match="must contain 'mappings' key"):
            config.load()

    def test_load_mappings_not_list(self, tmp_path: Path) -> None:
        """Loading config with non-list mappings raises ValueError."""
        config_path = tmp_path / "bad_mappings.json"
        with open(config_path, "w") as f:
            json.dump({"mappings": "not a list"}, f)

        config = OpcUaMappingConfig(config_path)

        with pytest.raises(ValueError, match="'mappings' must be a list"):
            config.load()

    def test_parse_mapping_missing_fields(self, config_file: Path) -> None:
        """Mappings with missing required fields are skipped."""
        config = OpcUaMappingConfig(config_file)

        # Add invalid mapping
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:1",
                    # Missing element_path and node_id
                }
            ]
        }

        # Temporarily replace config file
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        _mapper = config.load()

        # Invalid mapping should be skipped
        assert len(config.mappings) == 1  # Still in raw list
        # But not added to mapper (no valid mappings)

    def test_get_read_mappings(self, config_file: Path) -> None:
        """Get mappings configured for reading."""
        config = OpcUaMappingConfig(config_file)
        config.load()

        read_mappings = config.get_read_mappings()

        assert len(read_mappings) == 2  # bidirectional + read
        directions = [m["direction"] for m in read_mappings]
        assert "bidirectional" in directions
        assert "read" in directions

    def test_get_write_mappings(self, config_file: Path) -> None:
        """Get mappings configured for writing."""
        config = OpcUaMappingConfig(config_file)
        config.load()

        write_mappings = config.get_write_mappings()

        assert len(write_mappings) == 1  # Only bidirectional
        assert write_mappings[0]["direction"] == "bidirectional"

    def test_get_mapper_before_load(self) -> None:
        """Getting mapper before load raises RuntimeError."""
        config = OpcUaMappingConfig(None)

        with pytest.raises(RuntimeError, match="Mapper not loaded"):
            config.get_mapper()

    def test_get_mapper_after_load(self, config_file: Path) -> None:
        """Getting mapper after load returns configured mapper."""
        config = OpcUaMappingConfig(config_file)
        mapper1 = config.load()
        mapper2 = config.get_mapper()

        assert mapper1 is mapper2


class TestLoadMappingConfigConvenience:
    """Test convenience function for loading mappings."""

    def test_load_mapping_config(self, tmp_path: Path) -> None:
        """Convenience function loads configuration."""
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:1",
                    "element_path": "Temperature",
                    "node_id": "ns=2;s=Temperature",
                }
            ]
        }

        config_path = tmp_path / "test.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        mapper = load_mapping_config(config_path)

        assert mapper is not None
        node_id = mapper.get_node_id("urn:example:submodel:1", "Temperature")
        assert node_id == "ns=2;s=Temperature"

    def test_load_mapping_config_none(self) -> None:
        """Convenience function with None returns empty mapper."""
        mapper = load_mapping_config(None)

        assert mapper is not None

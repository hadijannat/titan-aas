"""Unit tests for Modbus configuration loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from titan.connectors.modbus.config_loader import ConfigValidationError, ModbusConfigLoader
from titan.connectors.modbus.mapping import ModbusMapper, RegisterMapping


class TestModbusConfigLoader:
    """Test ModbusConfigLoader class."""

    def test_load_from_dict_valid_config(self) -> None:
        """Load mappings from valid dictionary."""
        config_data = {
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
                    "description": "Temperature sensor",
                }
            ]
        }

        mapper = ModbusConfigLoader.load_from_dict(config_data)

        assert isinstance(mapper, ModbusMapper)
        assert len(mapper.mappings) == 1

        mapping = mapper.mappings[0]
        assert mapping.submodel_id == "urn:example:submodel:sensors:1"
        assert mapping.element_path == "Temperature"
        assert mapping.register_address == 100
        assert mapping.register_type == "holding_register"
        assert mapping.data_type == "float"
        assert mapping.scale_factor == 0.1
        assert mapping.direction == "read"

    def test_load_from_dict_minimal_config(self) -> None:
        """Load mappings with minimal required fields."""
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:sensors:1",
                    "element_path": "Count",
                    "register_address": 200,
                    "register_type": "input_register",
                }
            ]
        }

        mapper = ModbusConfigLoader.load_from_dict(config_data)

        assert len(mapper.mappings) == 1
        mapping = mapper.mappings[0]

        # Check defaults
        assert mapping.data_type == "int"
        assert mapping.scale_factor == 1.0
        assert mapping.offset == 0.0
        assert mapping.direction == "read"
        assert mapping.description == ""

    def test_load_from_dict_not_a_dict(self) -> None:
        """Loading non-dict raises ConfigValidationError."""
        with pytest.raises(ConfigValidationError, match="must be a JSON object"):
            ModbusConfigLoader.load_from_dict([])  # type: ignore

    def test_load_from_dict_missing_mappings_key(self) -> None:
        """Missing 'mappings' key raises ConfigValidationError."""
        config_data = {"other_key": []}

        with pytest.raises(ConfigValidationError, match="must contain 'mappings' key"):
            ModbusConfigLoader.load_from_dict(config_data)

    def test_load_from_dict_mappings_not_list(self) -> None:
        """'mappings' not a list raises ConfigValidationError."""
        config_data = {"mappings": "not a list"}

        with pytest.raises(ConfigValidationError, match="'mappings' must be a list"):
            ModbusConfigLoader.load_from_dict(config_data)

    def test_load_from_dict_invalid_mapping(self) -> None:
        """Invalid mapping raises ConfigValidationError."""
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:sensors:1",
                    "element_path": "Temperature",
                    "register_address": "not_an_int",  # Invalid type
                    "register_type": "holding_register",
                }
            ]
        }

        with pytest.raises(ConfigValidationError, match="Invalid mapping at index 0"):
            ModbusConfigLoader.load_from_dict(config_data)

    def test_load_from_dict_missing_required_field(self) -> None:
        """Missing required field raises ConfigValidationError."""
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:sensors:1",
                    # Missing element_path
                    "register_address": 100,
                    "register_type": "holding_register",
                }
            ]
        }

        with pytest.raises(ConfigValidationError, match="Invalid mapping at index 0"):
            ModbusConfigLoader.load_from_dict(config_data)

    def test_load_from_dict_multiple_mappings(self) -> None:
        """Load multiple mappings."""
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:sensors:1",
                    "element_path": "Temperature",
                    "register_address": 100,
                    "register_type": "holding_register",
                },
                {
                    "submodel_id": "urn:example:submodel:sensors:1",
                    "element_path": "Pressure",
                    "register_address": 200,
                    "register_type": "input_register",
                },
            ]
        }

        mapper = ModbusConfigLoader.load_from_dict(config_data)
        assert len(mapper.mappings) == 2

    def test_parse_mapping_valid_types(self) -> None:
        """Parse mapping with valid field types."""
        mapping_dict = {
            "submodel_id": "urn:example:submodel:sensors:1",
            "element_path": "Temperature",
            "register_address": 100,
            "register_type": "holding_register",
            "data_type": "float",
            "scale_factor": 0.1,
            "offset": 0.0,
            "direction": "read",
            "description": "Test",
        }

        mapping = ModbusConfigLoader._parse_mapping(mapping_dict)

        assert isinstance(mapping, RegisterMapping)
        assert mapping.submodel_id == "urn:example:submodel:sensors:1"

    def test_parse_mapping_invalid_submodel_id_type(self) -> None:
        """Invalid submodel_id type raises ValueError."""
        mapping_dict = {
            "submodel_id": 123,  # Should be string
            "element_path": "Temperature",
            "register_address": 100,
            "register_type": "holding_register",
        }

        with pytest.raises(ValueError, match="submodel_id must be a string"):
            ModbusConfigLoader._parse_mapping(mapping_dict)

    def test_parse_mapping_invalid_register_address_type(self) -> None:
        """Invalid register_address type raises ValueError."""
        mapping_dict = {
            "submodel_id": "urn:example:submodel:sensors:1",
            "element_path": "Temperature",
            "register_address": "100",  # Should be int
            "register_type": "holding_register",
        }

        with pytest.raises(ValueError, match="register_address must be an integer"):
            ModbusConfigLoader._parse_mapping(mapping_dict)

    def test_parse_mapping_register_address_out_of_range(self) -> None:
        """Register address out of range raises ValueError."""
        mapping_dict = {
            "submodel_id": "urn:example:submodel:sensors:1",
            "element_path": "Temperature",
            "register_address": 70000,  # Max is 65535
            "register_type": "holding_register",
        }

        with pytest.raises(ValueError, match="register_address must be 0-65535"):
            ModbusConfigLoader._parse_mapping(mapping_dict)

    def test_load_from_file_success(self, tmp_path: Path) -> None:
        """Load mappings from JSON file."""
        config_data = {
            "mappings": [
                {
                    "submodel_id": "urn:example:submodel:sensors:1",
                    "element_path": "Temperature",
                    "register_address": 100,
                    "register_type": "holding_register",
                }
            ]
        }

        # Write to temporary file
        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        mapper = ModbusConfigLoader.load_from_file(config_file)

        assert len(mapper.mappings) == 1
        assert mapper.mappings[0].element_path == "Temperature"

    def test_load_from_file_not_found(self) -> None:
        """Loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            ModbusConfigLoader.load_from_file("/nonexistent/file.json")

    def test_load_from_file_invalid_json(self, tmp_path: Path) -> None:
        """Loading invalid JSON raises ConfigValidationError."""
        config_file = tmp_path / "invalid.json"
        with open(config_file, "w") as f:
            f.write("{ invalid json }")

        with pytest.raises(ConfigValidationError, match="Invalid JSON"):
            ModbusConfigLoader.load_from_file(config_file)

    def test_save_to_file(self, tmp_path: Path) -> None:
        """Save mappings to JSON file."""
        mappings = [
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
                data_type="float",
                scale_factor=0.1,
                direction="read",
                description="Test sensor",
            ),
        ]

        mapper = ModbusMapper(mappings)
        output_file = tmp_path / "output.json"

        ModbusConfigLoader.save_to_file(mapper, output_file)

        # Verify file was created
        assert output_file.exists()

        # Load and verify content
        with open(output_file) as f:
            saved_data = json.load(f)

        assert "mappings" in saved_data
        assert len(saved_data["mappings"]) == 1

        saved_mapping = saved_data["mappings"][0]
        assert saved_mapping["submodel_id"] == "urn:example:submodel:sensors:1"
        assert saved_mapping["element_path"] == "Temperature"
        assert saved_mapping["register_address"] == 100
        assert saved_mapping["data_type"] == "float"
        assert saved_mapping["scale_factor"] == 0.1

    def test_round_trip_save_and_load(self, tmp_path: Path) -> None:
        """Save and load mappings round-trip."""
        original_mappings = [
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
                data_type="float",
                scale_factor=0.1,
                offset=5.0,
                direction="both",
                description="Temperature sensor",
            ),
            RegisterMapping(
                submodel_id="urn:example:submodel:actuators:1",
                element_path="MotorRunning",
                register_address=10,
                register_type="coil",
                data_type="bool",
                direction="write",
                description="Motor control",
            ),
        ]

        mapper = ModbusMapper(original_mappings)
        config_file = tmp_path / "config.json"

        # Save
        ModbusConfigLoader.save_to_file(mapper, config_file)

        # Load
        loaded_mapper = ModbusConfigLoader.load_from_file(config_file)

        # Verify
        assert len(loaded_mapper.mappings) == len(original_mappings)

        for original, loaded in zip(original_mappings, loaded_mapper.mappings, strict=True):
            assert loaded.submodel_id == original.submodel_id
            assert loaded.element_path == original.element_path
            assert loaded.register_address == original.register_address
            assert loaded.register_type == original.register_type
            assert loaded.data_type == original.data_type
            assert loaded.scale_factor == original.scale_factor
            assert loaded.offset == original.offset
            assert loaded.direction == original.direction
            assert loaded.description == original.description

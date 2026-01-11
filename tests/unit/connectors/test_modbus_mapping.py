"""Unit tests for Modbus register mapping."""

from __future__ import annotations

import pytest

from titan.connectors.modbus.mapping import ModbusMapper, RegisterMapping


class TestRegisterMapping:
    """Test RegisterMapping dataclass."""

    def test_create_valid_mapping(self) -> None:
        """Create a valid register mapping."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
            data_type="float",
            scale_factor=0.1,
            offset=0.0,
            direction="read",
            description="Temperature sensor",
        )

        assert mapping.submodel_id == "urn:example:submodel:sensors:1"
        assert mapping.element_path == "Temperature"
        assert mapping.register_address == 100
        assert mapping.register_type == "holding_register"
        assert mapping.data_type == "float"
        assert mapping.scale_factor == 0.1
        assert mapping.can_read is True
        assert mapping.can_write is False

    def test_invalid_register_type(self) -> None:
        """Invalid register type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid register_type"):
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="invalid_type",
            )

    def test_invalid_data_type(self) -> None:
        """Invalid data type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid data_type"):
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
                data_type="invalid",
            )

    def test_invalid_direction(self) -> None:
        """Invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction"):
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
                direction="invalid",
            )

    def test_coil_requires_bool_data_type(self) -> None:
        """Coil register type requires bool data type."""
        with pytest.raises(ValueError, match="requires data_type='bool'"):
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="MotorRunning",
                register_address=10,
                register_type="coil",
                data_type="int",
            )

    def test_cannot_write_to_read_only_register(self) -> None:
        """Cannot write to read-only register types."""
        with pytest.raises(ValueError, match="Cannot write to read-only"):
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="input_register",
                direction="write",
            )

    def test_can_read_property(self) -> None:
        """Test can_read property."""
        read_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
            direction="read",
        )
        assert read_mapping.can_read is True
        assert read_mapping.can_write is False

        both_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Setpoint",
            register_address=200,
            register_type="holding_register",
            direction="both",
        )
        assert both_mapping.can_read is True
        assert both_mapping.can_write is True

    def test_register_to_value_bool(self) -> None:
        """Convert bool register value to AAS value."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="MotorRunning",
            register_address=10,
            register_type="coil",
            data_type="bool",
        )

        assert mapping.register_to_value(True) is True
        assert mapping.register_to_value(False) is False

    def test_register_to_value_int(self) -> None:
        """Convert int register value to AAS value."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Count",
            register_address=100,
            register_type="holding_register",
            data_type="int",
        )

        assert mapping.register_to_value(42) == 42

    def test_register_to_value_float_with_scaling(self) -> None:
        """Convert float register value with scaling."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
            data_type="float",
            scale_factor=0.1,
            offset=0.0,
        )

        # Register value 235 -> 23.5°C
        assert mapping.register_to_value(235) == 23.5

    def test_register_to_value_float_with_offset(self) -> None:
        """Convert float register value with offset."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
            data_type="float",
            scale_factor=1.0,
            offset=-273.15,  # Convert Kelvin to Celsius
        )

        # Register value 300K -> 26.85°C
        assert mapping.register_to_value(300) == pytest.approx(26.85)

    def test_value_to_register_bool(self) -> None:
        """Convert AAS bool value to register value."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="MotorRunning",
            register_address=10,
            register_type="coil",
            data_type="bool",
            direction="write",
        )

        assert mapping.value_to_register(True) is True
        assert mapping.value_to_register(False) is False
        assert mapping.value_to_register("true") is True
        assert mapping.value_to_register("false") is False
        assert mapping.value_to_register(1) is True
        assert mapping.value_to_register(0) is False

    def test_value_to_register_int(self) -> None:
        """Convert AAS int value to register value."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Count",
            register_address=100,
            register_type="holding_register",
            data_type="int",
            direction="write",
        )

        assert mapping.value_to_register(42) == 42
        assert mapping.value_to_register("42") == 42

    def test_value_to_register_float_with_scaling(self) -> None:
        """Convert AAS float value to register with reverse scaling."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Setpoint",
            register_address=200,
            register_type="holding_register",
            data_type="float",
            scale_factor=0.1,
            direction="write",
        )

        # AAS value 23.5°C -> register value 235
        assert mapping.value_to_register(23.5) == 235

    def test_value_to_register_out_of_range(self) -> None:
        """Value out of range for holding register raises ValueError."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Value",
            register_address=100,
            register_type="holding_register",
            data_type="int",
            direction="write",
        )

        with pytest.raises(ValueError, match="out of range"):
            mapping.value_to_register(70000)  # Max is 65535

    def test_value_to_register_string_raises_not_implemented(self) -> None:
        """String conversion raises NotImplementedError."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Name",
            register_address=100,
            register_type="holding_register",
            data_type="string",
            direction="write",
        )

        with pytest.raises(NotImplementedError, match="String encoding"):
            mapping.value_to_register("test")


class TestModbusMapper:
    """Test ModbusMapper class."""

    def test_create_empty_mapper(self) -> None:
        """Create empty mapper."""
        mapper = ModbusMapper()
        assert len(mapper.mappings) == 0

    def test_create_mapper_with_mappings(self) -> None:
        """Create mapper with initial mappings."""
        mappings = [
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
            ),
        ]

        mapper = ModbusMapper(mappings)
        assert len(mapper.mappings) == 1

    def test_add_mapping(self) -> None:
        """Add mapping to mapper."""
        mapper = ModbusMapper()

        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
        )

        mapper.add_mapping(mapping)
        assert len(mapper.mappings) == 1

    def test_get_by_element(self) -> None:
        """Find mapping by AAS element."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
        )

        mapper = ModbusMapper([mapping])

        found = mapper.get_by_element("urn:example:submodel:sensors:1", "Temperature")
        assert found == mapping

        not_found = mapper.get_by_element("urn:example:submodel:sensors:1", "Pressure")
        assert not_found is None

    def test_get_by_register(self) -> None:
        """Find mapping by Modbus register."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
        )

        mapper = ModbusMapper([mapping])

        found = mapper.get_by_register("holding_register", 100)
        assert found == mapping

        not_found = mapper.get_by_register("holding_register", 200)
        assert not_found is None

    def test_get_readable_mappings(self) -> None:
        """Get all readable mappings."""
        read_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
            direction="read",
        )

        write_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Setpoint",
            register_address=200,
            register_type="holding_register",
            direction="write",
        )

        both_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Control",
            register_address=300,
            register_type="holding_register",
            direction="both",
        )

        mapper = ModbusMapper([read_mapping, write_mapping, both_mapping])

        readable = mapper.get_readable_mappings()
        assert len(readable) == 2  # read and both
        assert read_mapping in readable
        assert both_mapping in readable
        assert write_mapping not in readable

    def test_get_writable_mappings(self) -> None:
        """Get all writable mappings."""
        read_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
            direction="read",
        )

        write_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Setpoint",
            register_address=200,
            register_type="holding_register",
            direction="write",
        )

        both_mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Control",
            register_address=300,
            register_type="holding_register",
            direction="both",
        )

        mapper = ModbusMapper([read_mapping, write_mapping, both_mapping])

        writable = mapper.get_writable_mappings()
        assert len(writable) == 2  # write and both
        assert write_mapping in writable
        assert both_mapping in writable
        assert read_mapping not in writable

    def test_clear_mappings(self) -> None:
        """Clear all mappings."""
        mapping = RegisterMapping(
            submodel_id="urn:example:submodel:sensors:1",
            element_path="Temperature",
            register_address=100,
            register_type="holding_register",
        )

        mapper = ModbusMapper([mapping])
        assert len(mapper.mappings) == 1

        mapper.clear()
        assert len(mapper.mappings) == 0
        assert mapper.get_by_element("urn:example:submodel:sensors:1", "Temperature") is None

"""Modbus Event Handler for routing AAS events to Modbus writes.

Subscribes to the event bus and writes AAS/Submodel changes to Modbus registers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from titan.connectors.modbus.client import ModbusClient
from titan.connectors.modbus.mapping import ModbusMapper
from titan.connectors.modbus.poller import ModbusPoller, PollConfig
from titan.events import SubmodelElementEvent

logger = logging.getLogger(__name__)


class ModbusEventHandler:
    """Event handler that writes AAS/Submodel changes to Modbus registers.

    Routes events from the event bus to Modbus register writes based on configured mappings.
    """

    def __init__(
        self,
        client: ModbusClient,
        mapper: ModbusMapper | None = None,
    ):
        """Initialize event handler.

        Args:
            client: ModbusClient for writing to registers
            mapper: Register mapper for AAS ↔ Modbus mapping
        """
        self.client = client
        self.mapper = mapper or ModbusMapper()

    async def handle_element_event(self, event: SubmodelElementEvent) -> None:
        """Handle SubmodelElement event by writing value to Modbus register.

        Maps the SubmodelElement to a Modbus register and writes the new value.

        Args:
            event: The SubmodelElement event to handle
        """
        try:
            # Map SubmodelElement path to Modbus register
            mapping = self.mapper.get_by_element(
                submodel_id=event.submodel_identifier,
                element_path=event.id_short_path,
            )

            if mapping is None:
                logger.debug(
                    f"No Modbus mapping for {event.submodel_identifier}/{event.id_short_path}"
                )
                return

            # Check if this mapping supports writes
            if not mapping.can_write:
                logger.debug(f"Mapping for {event.id_short_path} is read-only, skipping write")
                return

            # Deserialize value from event
            if event.value_bytes is None:
                logger.debug(f"No value in event for {event.id_short_path}")
                return

            # Parse value from JSON bytes
            value = json.loads(event.value_bytes.decode("utf-8"))

            # Convert AAS value to register value
            register_value = mapping.value_to_register(value)

            # Write to Modbus register
            success = False
            if mapping.register_type == "coil":
                if isinstance(register_value, bool):
                    success = await self.client.write_coil(mapping.register_address, register_value)
            elif mapping.register_type == "holding_register":
                if isinstance(register_value, int):
                    success = await self.client.write_register(
                        mapping.register_address, register_value
                    )

            if success:
                logger.info(
                    f"Wrote to Modbus {mapping.register_type}:{mapping.register_address} "
                    f"= {register_value} (from {event.id_short_path})"
                )
            else:
                logger.error(
                    f"Failed to write to Modbus {mapping.register_type}:{mapping.register_address}"
                )

        except ValueError as e:
            logger.error(f"Value conversion error for {event.id_short_path}: {e}")
        except Exception as e:
            logger.error(f"Error handling element event: {e}")


class ModbusValueSyncHandler:
    """Bidirectional value sync handler between Modbus and AAS.

    Polls Modbus register values and publishes them as AAS events.
    This enables real-time sync from Modbus devices to AAS submodel elements.
    """

    def __init__(
        self,
        client: ModbusClient,
        mapper: ModbusMapper | None = None,
        event_publisher: Callable[[str, str, Any], None] | None = None,
    ):
        """Initialize sync handler.

        Args:
            client: ModbusClient for reading registers
            mapper: Register mapper for Modbus ↔ AAS mapping
            event_publisher: Callback to publish AAS events (submodel_id, element_path, value)
        """
        self.client = client
        self.mapper = mapper or ModbusMapper()
        self.event_publisher = event_publisher
        self.poller = ModbusPoller(client)

    async def start_sync(self, polling_interval: float = 1.0) -> None:
        """Start bidirectional sync for all readable mappings.

        Args:
            polling_interval: Polling interval in seconds (default: 1.0)
        """
        # Get all mappings that support reading (Modbus -> AAS)
        readable_mappings = self.mapper.get_readable_mappings()

        if not readable_mappings:
            logger.warning("No readable Modbus mappings configured")
            return

        logger.info(f"Starting Modbus sync for {len(readable_mappings)} mappings")

        # Start polling for each readable mapping
        for mapping in readable_mappings:
            poll_config = PollConfig(
                register_address=mapping.register_address,
                register_type=mapping.register_type,
                count=1,
                interval=polling_interval,
                debounce_count=2,  # Require 2 consecutive changes to avoid noise
            )

            # Create callback that publishes AAS events
            def create_callback(
                submodel_id: str, element_path: str, mapper_mapping: Any
            ) -> Callable[[int, list[int] | list[bool]], None]:
                def on_value_change(address: int, values: list[int] | list[bool]) -> None:
                    """Callback when Modbus register value changes."""
                    if not values:
                        return

                    # Convert raw register value to AAS value
                    raw_value = values[0]
                    aas_value = mapper_mapping.register_to_value(raw_value)

                    logger.info(
                        f"Modbus value changed: {mapper_mapping.register_type}:"
                        f"{address} = {raw_value} -> {element_path} = {aas_value}"
                    )

                    # Publish AAS event
                    if self.event_publisher:
                        self.event_publisher(submodel_id, element_path, aas_value)

                return on_value_change

            callback = create_callback(mapping.submodel_id, mapping.element_path, mapping)

            poll_id = self.poller.start_polling(poll_config, callback)
            logger.info(
                f"Started polling {mapping.register_type}:{mapping.register_address} "
                f"for {mapping.submodel_id}/{mapping.element_path} (poll_id: {poll_id})"
            )

    async def stop_sync(self) -> None:
        """Stop all active polling."""
        logger.info("Stopping Modbus sync")
        self.poller.stop_all()

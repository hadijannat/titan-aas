"""OPC-UA Event Handler for routing AAS events to OPC-UA writes.

Subscribes to the event bus and writes AAS/Submodel changes to OPC-UA nodes.
"""

from __future__ import annotations

import logging
from typing import Any

from titan.connectors.opcua.connection import OpcUaConnectionManager
from titan.connectors.opcua.mapping import AasOpcUaMapper
from titan.events import AasEvent, SubmodelElementEvent, SubmodelEvent
from titan.observability.metrics import record_opcua_write_error

logger = logging.getLogger(__name__)


class OpcUaEventHandler:
    """Event handler that writes AAS/Submodel changes to OPC-UA nodes.

    Routes events from the event bus to OPC-UA node writes based on configured mappings.
    """

    def __init__(
        self,
        connection_manager: OpcUaConnectionManager,
        mapper: AasOpcUaMapper | None = None,
    ):
        self.connection_manager = connection_manager
        self.mapper = mapper or AasOpcUaMapper()

    async def handle_aas_event(self, event: AasEvent) -> None:
        """Handle AAS event.

        Currently logs the event. Full implementation would map AAS properties
        to OPC-UA nodes and write values.

        Args:
            event: The AAS event to handle
        """
        logger.debug(f"Received AAS event: {event.event_type} for {event.identifier}")
        # Future: Map AAS properties to OPC-UA nodes and write

    async def handle_submodel_event(self, event: SubmodelEvent) -> None:
        """Handle Submodel event.

        Currently logs the event. Full implementation would map Submodel properties
        to OPC-UA nodes and write values.

        Args:
            event: The Submodel event to handle
        """
        logger.debug(f"Received Submodel event: {event.event_type} for {event.identifier}")
        # Future: Map Submodel properties to OPC-UA nodes and write

    async def handle_element_event(self, event: SubmodelElementEvent) -> None:
        """Handle SubmodelElement event by writing value to OPC-UA node.

        Maps the SubmodelElement to an OPC-UA NodeId and writes the new value.

        Note: Full implementation would deserialize value_bytes and write to OPC-UA.
        Currently logs events for demonstration.

        Args:
            event: The SubmodelElement event to handle
        """
        try:
            # Map SubmodelElement path to OPC-UA NodeId
            node_id = self.mapper.get_node_id(
                submodel_id=event.submodel_identifier,
                id_short_path=event.id_short_path,
            )

            if node_id is None:
                logger.debug(
                    f"No OPC-UA mapping for {event.submodel_identifier}/{event.id_short_path}"
                )
                return

            # Future: Deserialize value_bytes to get actual value
            if event.value_bytes is None:
                logger.debug(f"No value in event for {event.id_short_path}")
                return

            logger.info(f"Would write to OPC-UA node {node_id} for element {event.id_short_path}")

        except Exception as e:
            record_opcua_write_error(self.connection_manager.config.endpoint_url)
            logger.error(f"Error handling element event: {e}")


class OpcUaValueSyncHandler:
    """Bidirectional value sync handler between OPC-UA and AAS.

    Subscribes to OPC-UA node value changes and publishes them as AAS events.
    This enables real-time sync from OPC-UA devices to AAS submodel elements.
    """

    def __init__(
        self,
        connection_manager: OpcUaConnectionManager,
        mapper: AasOpcUaMapper | None = None,
    ):
        self.connection_manager = connection_manager
        self.mapper = mapper or AasOpcUaMapper()
        self._subscriptions: dict[str, str] = {}  # node_id -> subscription_id

    async def start_sync(self, mappings: list[dict[str, Any]]) -> None:
        """Start bidirectional sync for configured mappings.

        Args:
            mappings: List of mapping configurations with:
                - submodel_id: AAS Submodel identifier
                - element_path: idShortPath to element
                - node_id: OPC-UA NodeId
                - direction: "read", "write", or "bidirectional"
        """
        client = await self.connection_manager.ensure_connected()

        # Subscribe to nodes for reading (OPC-UA -> AAS)
        read_mappings = [m for m in mappings if m.get("direction") in ("read", "bidirectional")]

        if read_mappings:
            node_ids = [m["node_id"] for m in read_mappings]

            def on_value_change(node_id: str, value: Any) -> None:
                """Callback when OPC-UA node value changes."""
                logger.info(f"OPC-UA value changed: {node_id} = {value}")
                # Future: Publish as AAS SubmodelElementEvent to event bus

            subscription_id = await client.subscribe(node_ids, on_value_change)
            if subscription_id:
                logger.info(f"Started OPC-UA sync for {len(node_ids)} nodes: {subscription_id}")
                for node_id in node_ids:
                    self._subscriptions[node_id] = subscription_id

    async def stop_sync(self) -> None:
        """Stop all active subscriptions."""
        client = await self.connection_manager.ensure_connected()

        # Unsubscribe from all nodes
        subscription_ids = set(self._subscriptions.values())
        for subscription_id in subscription_ids:
            await client.unsubscribe(subscription_id)
            logger.info(f"Stopped OPC-UA subscription: {subscription_id}")

        self._subscriptions.clear()

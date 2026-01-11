"""OPC UA client for AAS data exchange.

Enables reading and writing AAS data from/to OPC UA servers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OpcUaSecurityMode(str, Enum):
    """OPC UA security modes."""

    NONE = "None"
    SIGN = "Sign"
    SIGN_AND_ENCRYPT = "SignAndEncrypt"


@dataclass
class OpcUaConfig:
    """Configuration for OPC UA connection."""

    endpoint_url: str
    security_mode: OpcUaSecurityMode = OpcUaSecurityMode.NONE
    security_policy: str | None = None
    username: str | None = None
    password: str | None = None
    certificate_path: str | None = None
    private_key_path: str | None = None
    application_uri: str = "urn:titan:opcua:client"
    timeout: float = 10.0
    reconnect_interval: int = 5


@dataclass
class OpcUaNodeValue:
    """Value read from an OPC UA node."""

    node_id: str
    value: Any
    data_type: str
    timestamp: str | None = None
    status: str = "Good"


class OpcUaClient:
    """Client for connecting to OPC UA servers.

    This is a scaffold that can be extended with asyncua when available.
    """

    def __init__(self, config: OpcUaConfig) -> None:
        """Initialize OPC UA client.

        Args:
            config: Connection configuration
        """
        self.config = config
        self._connected = False
        self._subscriptions: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._connected

    async def connect(self) -> bool:
        """Connect to the OPC UA server.

        Returns:
            True if connected successfully
        """
        logger.info(f"Connecting to OPC UA server: {self.config.endpoint_url}")

        try:
            from asyncua import Client as AsyncUaClient
            from asyncua import ua

            # Create asyncua client
            self._client = AsyncUaClient(url=self.config.endpoint_url)

            # Set security if configured
            if self.config.security_mode != OpcUaSecurityMode.NONE:
                logger.info(f"Setting security mode: {self.config.security_mode}")
                # For now, log warning that advanced security requires certificates
                if not self.config.certificate_path or not self.config.private_key_path:
                    logger.warning(
                        "Security mode set but no certificates provided. "
                        "Using security mode None instead."
                    )
                else:
                    # Set security with certificates
                    await self._client.set_security_string(
                        f"{self.config.security_mode.value},"
                        f"Basic256Sha256,"
                        f"{self.config.certificate_path},"
                        f"{self.config.private_key_path}"
                    )

            # Set credentials if configured
            if self.config.username and self.config.password:
                logger.info(f"Setting username authentication: {self.config.username}")
                self._client.set_user(self.config.username)
                self._client.set_password(self.config.password)

            # Connect with timeout
            import asyncio

            await asyncio.wait_for(self._client.connect(), timeout=self.config.timeout)

            self._connected = True
            logger.info(f"Successfully connected to OPC UA server: {self.config.endpoint_url}")
            return True

        except asyncio.TimeoutError:
            logger.error(
                f"Connection timeout after {self.config.timeout}s: {self.config.endpoint_url}"
            )
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Failed to connect to OPC UA server: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the OPC UA server."""
        if self._connected and self._client:
            try:
                # Clean up subscriptions first
                if self._subscriptions:
                    logger.info(f"Cleaning up {len(self._subscriptions)} subscriptions")
                    self._subscriptions.clear()

                # Disconnect from server
                await self._client.disconnect()
                self._connected = False
                self._client = None
                logger.info("OPC UA client disconnected")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
                self._connected = False
                self._client = None

    async def read_node(self, node_id: str) -> OpcUaNodeValue | None:
        """Read a value from an OPC UA node.

        Args:
            node_id: The OPC UA NodeId string (e.g., "ns=2;s=MyVariable")

        Returns:
            The node value or None if failed
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to OPC UA server")
            return None

        try:
            from asyncua import ua

            # Get node object
            node = self._client.get_node(node_id)

            # Read value
            value = await node.read_value()

            # Read data type
            data_type_node = await node.read_data_type()
            data_type = str(data_type_node)

            # Read status
            data_value = await node.read_data_value()
            status = "Good" if data_value.StatusCode.is_good() else str(data_value.StatusCode)

            logger.debug(f"Read node {node_id}: value={value}, type={data_type}")

            return OpcUaNodeValue(
                node_id=node_id,
                value=value,
                data_type=data_type,
                status=status,
            )

        except Exception as e:
            logger.error(f"Failed to read node {node_id}: {e}")
            return None

    async def write_node(self, node_id: str, value: Any) -> bool:
        """Write a value to an OPC UA node.

        Args:
            node_id: The OPC UA NodeId string
            value: The value to write

        Returns:
            True if successful
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to OPC UA server")
            return False

        try:
            # Get node object
            node = self._client.get_node(node_id)

            # Write value to node
            await node.write_value(value)

            logger.debug(f"Write node {node_id}: value={value}")
            return True

        except Exception as e:
            logger.error(f"Failed to write node {node_id}: {e}")
            return False

    async def subscribe(
        self,
        node_ids: list[str],
        callback: Any,
        interval: float = 1.0,
    ) -> str | None:
        """Subscribe to value changes on nodes.

        Args:
            node_ids: List of NodeIds to monitor
            callback: Function to call on value change
            interval: Sampling interval in seconds

        Returns:
            Subscription ID or None if failed
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to OPC UA server")
            return None

        try:
            from asyncua import ua

            # Create subscription handler
            class SubscriptionHandler:
                """Handler for OPC UA subscription data change notifications."""

                def __init__(self, callback_fn: Any) -> None:
                    self.callback_fn = callback_fn

                def datachange_notification(self, node: Any, val: Any, data: Any) -> None:
                    """Called when subscribed node value changes."""
                    try:
                        # Extract node_id from node
                        node_id = str(node)
                        # Invoke user callback with node_id and value
                        if self.callback_fn:
                            self.callback_fn(node_id, val)
                    except Exception as e:
                        logger.error(f"Error in subscription callback: {e}")

            # Create subscription handler instance
            handler = SubscriptionHandler(callback)

            # Create subscription with interval (in milliseconds)
            subscription = await self._client.create_subscription(
                period=interval * 1000, handler=handler
            )

            # Subscribe to all nodes
            handles = []
            for node_id in node_ids:
                node = self._client.get_node(node_id)
                handle = await subscription.subscribe_data_change(node)
                handles.append(handle)

            # Store subscription info
            subscription_id = f"sub_{len(self._subscriptions)}"
            self._subscriptions[subscription_id] = {
                "subscription": subscription,
                "handler": handler,
                "nodes": node_ids,
                "handles": handles,
                "callback": callback,
                "interval": interval,
            }

            logger.info(f"Created subscription {subscription_id} for {len(node_ids)} nodes")
            return subscription_id

        except Exception as e:
            logger.error(f"Failed to create subscription: {e}")
            return None

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from value changes.

        Args:
            subscription_id: The subscription to cancel

        Returns:
            True if successful
        """
        if subscription_id not in self._subscriptions:
            logger.warning(f"Subscription {subscription_id} not found")
            return False

        try:
            subscription_info = self._subscriptions[subscription_id]
            subscription = subscription_info.get("subscription")

            # Delete the asyncua subscription
            if subscription:
                await subscription.delete()

            # Remove from tracking
            del self._subscriptions[subscription_id]
            logger.info(f"Removed subscription {subscription_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe {subscription_id}: {e}")
            # Still remove from tracking even if delete failed
            if subscription_id in self._subscriptions:
                del self._subscriptions[subscription_id]
            return False

    async def browse(self, node_id: str = "i=84") -> list[dict[str, Any]]:
        """Browse child nodes of a node.

        Args:
            node_id: Parent node ID (default: Objects folder)

        Returns:
            List of child node info
        """
        if not self._connected:
            return []

        try:
            # Placeholder - would browse using asyncua
            # node = self._client.get_node(node_id)
            # children = await node.get_children()

            logger.debug(f"Browse node: {node_id}")
            return []  # Would return actual children

        except Exception as e:
            logger.error(f"Failed to browse node {node_id}: {e}")
            return []

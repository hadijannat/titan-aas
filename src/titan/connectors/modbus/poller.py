"""Modbus register polling mechanism.

Polls Modbus registers at configurable intervals and triggers callbacks on value changes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from titan.connectors.modbus.client import ModbusClient

logger = logging.getLogger(__name__)


@dataclass
class PollConfig:
    """Configuration for polling a specific register."""

    register_address: int
    register_type: str  # coil, discrete_input, holding_register, input_register
    count: int = 1
    interval: float = 1.0  # Polling interval in seconds
    debounce_count: int = 1  # Number of consecutive changes before triggering callback


class ModbusPoller:
    """Polls Modbus registers and triggers callbacks on value changes.

    Supports polling multiple registers with different intervals and debouncing
    to avoid event spam from noisy sensors.
    """

    def __init__(self, client: ModbusClient):
        """Initialize poller.

        Args:
            client: ModbusClient instance to use for reading
        """
        self.client = client
        self._poll_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_values: dict[str, list[int] | list[bool]] = {}
        self._callbacks: dict[str, Callable[[int, list[int] | list[bool]], None]] = {}
        self._running = False

    def start_polling(
        self,
        config: PollConfig,
        callback: Callable[[int, list[int] | list[bool]], None],
    ) -> str:
        """Start polling a register.

        Args:
            config: Polling configuration
            callback: Function to call when value changes (address, new_values)

        Returns:
            Poll ID for stopping later
        """
        poll_id = f"{config.register_type}:{config.register_address}"

        if poll_id in self._poll_tasks:
            logger.warning(f"Already polling {poll_id}")
            return poll_id

        self._callbacks[poll_id] = callback
        self._poll_tasks[poll_id] = asyncio.create_task(self._poll_loop(config, poll_id))
        self._running = True

        logger.info(
            f"Started polling {config.register_type} at address {config.register_address} "
            f"every {config.interval}s"
        )
        return poll_id

    def stop_polling(self, poll_id: str) -> bool:
        """Stop polling a register.

        Args:
            poll_id: Poll ID returned from start_polling()

        Returns:
            True if stopped, False if not found
        """
        if poll_id not in self._poll_tasks:
            logger.warning(f"Poll ID {poll_id} not found")
            return False

        task = self._poll_tasks[poll_id]
        task.cancel()
        del self._poll_tasks[poll_id]
        del self._callbacks[poll_id]
        if poll_id in self._last_values:
            del self._last_values[poll_id]

        logger.info(f"Stopped polling {poll_id}")

        if not self._poll_tasks:
            self._running = False

        return True

    def stop_all(self) -> None:
        """Stop all polling tasks."""
        for poll_id in list(self._poll_tasks.keys()):
            self.stop_polling(poll_id)

    @property
    def is_running(self) -> bool:
        """Check if any polling tasks are running."""
        return self._running

    async def _poll_loop(self, config: PollConfig, poll_id: str) -> None:
        """Background polling loop for a single register.

        Args:
            config: Polling configuration
            poll_id: Unique poll identifier
        """
        debounce_counter = 0
        pending_value: list[int] | list[bool] | None = None

        while True:
            try:
                # Read the register
                current_value = await self._read_register(config)

                if current_value is None:
                    logger.warning(f"Failed to read {poll_id}")
                    await asyncio.sleep(config.interval)
                    continue

                # Check for value change
                if poll_id in self._last_values:
                    if current_value != self._last_values[poll_id]:
                        # Value changed
                        if pending_value is None or pending_value != current_value:
                            # New change detected, reset debounce
                            pending_value = current_value
                            debounce_counter = 1
                        else:
                            # Same change confirmed
                            debounce_counter += 1

                        # Trigger callback if debounce threshold met
                        if debounce_counter >= config.debounce_count:
                            logger.debug(
                                f"Value changed for {poll_id}: "
                                f"{self._last_values[poll_id]} -> {current_value}"
                            )
                            self._last_values[poll_id] = current_value
                            callback = self._callbacks.get(poll_id)
                            if callback:
                                try:
                                    callback(config.register_address, current_value)
                                except Exception as e:
                                    logger.error(f"Error in poll callback for {poll_id}: {e}")
                            # Reset debounce
                            debounce_counter = 0
                            pending_value = None
                    else:
                        # Value stable, reset debounce
                        debounce_counter = 0
                        pending_value = None
                else:
                    # First read, store value
                    self._last_values[poll_id] = current_value
                    logger.debug(f"Initial value for {poll_id}: {current_value}")

                # Wait for next poll interval
                await asyncio.sleep(config.interval)

            except asyncio.CancelledError:
                logger.debug(f"Polling cancelled for {poll_id}")
                break
            except Exception as e:
                logger.error(f"Error polling {poll_id}: {e}")
                await asyncio.sleep(config.interval)

    async def _read_register(self, config: PollConfig) -> list[int] | list[bool] | None:
        """Read a register based on type.

        Args:
            config: Polling configuration

        Returns:
            Register values or None on error
        """
        if config.register_type == "coil":
            return await self.client.read_coils(config.register_address, config.count)
        elif config.register_type == "discrete_input":
            return await self.client.read_discrete_inputs(config.register_address, config.count)
        elif config.register_type == "holding_register":
            return await self.client.read_holding_registers(config.register_address, config.count)
        elif config.register_type == "input_register":
            return await self.client.read_input_registers(config.register_address, config.count)
        else:
            logger.error(f"Invalid register type: {config.register_type}")
            return None

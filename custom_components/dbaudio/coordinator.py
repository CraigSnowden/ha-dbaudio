"""Coordinator for d&b audiotechnik amplifier integration."""
from __future__ import annotations

import asyncio
import copy
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .aes70.device import DBAudioDevice

_LOGGER = logging.getLogger(__name__)

RECONNECT_INTERVAL = 10  # seconds
POWER_HOURS_INTERVAL = timedelta(seconds=10)


class DBAudioCoordinator:
    """Manages the AES70 connection and pushes state to HA entities."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, model: str) -> None:
        self.hass = hass
        self.data: dict[str, Any] = {"available": False}

        self._device = DBAudioDevice(
            host=host,
            port=port,
            model=model,
            loop=hass.loop,
        )
        self._device.on_state_updated = self._on_state_updated
        self._device.on_disconnected = self._on_disconnected

        self._listeners: list[Callable[[], None]] = []
        self._reconnect_task: asyncio.Task | None = None
        self._power_hours_unsub: Callable | None = None
        self._available = False

    # --- Public API ---

    @property
    def available(self) -> bool:
        return self._available

    def register_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def _unregister() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unregister

    async def async_setup(self) -> None:
        await self._connect()

    async def async_unload(self) -> None:
        if self._reconnect_task:
            self._reconnect_task.cancel()
        self._stop_power_hours_poll()
        await self.hass.async_add_executor_job(self._device.disconnect)

    # --- Connection management ---

    async def _connect(self) -> None:
        try:
            await self.hass.async_add_executor_job(self._device.connect_blocking)
            await self._device.initialize()
            self._available = True
            self.data = copy.deepcopy(self._device.state)
            self.data["available"] = True
            self._notify_listeners()
            self._start_power_hours_poll()
            _LOGGER.info("Connected to d&b amp %s", self._device.state.get("amp_name") or "unknown")
        except Exception as exc:
            _LOGGER.warning("Could not connect to d&b amp: %s", exc)
            self._available = False
            self.data["available"] = False
            self._schedule_reconnect()

    @callback
    def _on_state_updated(self) -> None:
        self.data = copy.deepcopy(self._device.state)
        self.data["available"] = True
        self._notify_listeners()

    @callback
    def _on_disconnected(self) -> None:
        _LOGGER.warning("d&b amp disconnected; will retry in %ds", RECONNECT_INTERVAL)
        self._available = False
        self.data["available"] = False
        self._stop_power_hours_poll()
        self._notify_listeners()
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self.hass.loop.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        while True:
            await asyncio.sleep(RECONNECT_INTERVAL)
            _LOGGER.debug("Attempting reconnect to d&b amp")
            try:
                await self.hass.async_add_executor_job(self._device.connect_blocking)
                await self._device.initialize()
                self._available = True
                self.data = copy.deepcopy(self._device.state)
                self.data["available"] = True
                self._notify_listeners()
                self._start_power_hours_poll()
                _LOGGER.info("Reconnected to d&b amp")
                return
            except Exception as exc:
                _LOGGER.debug("Reconnect failed: %s", exc)

    # --- Listeners ---

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    # --- Power hours polling ---

    def _start_power_hours_poll(self) -> None:
        if self._power_hours_unsub:
            return
        self._power_hours_unsub = async_track_time_interval(
            self.hass, self._poll_power_hours, POWER_HOURS_INTERVAL
        )

    def _stop_power_hours_poll(self) -> None:
        if self._power_hours_unsub:
            self._power_hours_unsub()
            self._power_hours_unsub = None

    async def _poll_power_hours(self, _now: Any = None) -> None:
        if not self._available:
            return
        try:
            hours = await self._device.read_power_hours()
            if self.data.get("power_hours") != hours:
                self.data["power_hours"] = hours
                self._notify_listeners()
        except Exception as exc:
            _LOGGER.debug("Power hours poll failed: %s", exc)

    # --- Commands (called by entities) ---

    async def set_power(self, on: bool) -> None:
        await self._device.set_power(on)

    async def set_mute(self, ch: int, muted: bool) -> None:
        await self._device.set_mute(ch, muted)

    async def set_level(self, ch: int, db: float) -> None:
        await self._device.set_level(ch, db)

    async def set_delay(self, ch: int, ms: float) -> None:
        await self._device.set_delay(ch, ms)

    async def set_delay_enable(self, ch: int, enabled: bool) -> None:
        await self._device.set_delay_enable(ch, enabled)

    async def set_eq_bypass(self, ch: int, eq_idx: int, bypassed: bool) -> None:
        await self._device.set_eq_bypass(ch, eq_idx, bypassed)

    async def set_input_gain_enable(self, enabled: bool) -> None:
        await self._device.set_input_gain_enable(enabled)

    async def recall_preset(self, index: int) -> None:
        await self._device.recall_preset(index)

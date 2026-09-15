"""Base entity for d&b audiotechnik integration."""
from __future__ import annotations

from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import DBAudioCoordinator


class DBAudioEntity(RestoreEntity):
    """Base class for all d&b audiotechnik entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._unregister: Callable | None = None

    @property
    def available(self) -> bool:
        return self.coordinator.data.get("available", False)

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=data.get("amp_name") or self._entry.title,
            manufacturer="d&b audiotechnik",
            model=data.get("amp_type") or self._entry.data.get("model", ""),
            sw_version=data.get("amp_firmware") or None,
        )

    async def async_added_to_hass(self) -> None:
        self._unregister = self.coordinator.register_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister:
            self._unregister()

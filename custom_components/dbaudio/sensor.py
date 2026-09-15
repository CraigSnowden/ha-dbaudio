"""Sensor entities for d&b audiotechnik amplifiers."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHANNEL_COUNT, CHANNEL_LABELS, DOMAIN, SPEAKER_NAMES
from .coordinator import DBAudioCoordinator
from .entity import DBAudioEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DBAudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[DBAudioEntity] = [DBAudioPowerHoursSensor(coordinator, entry)]

    for ch in range(CHANNEL_COUNT):
        entities.append(DBAudioSpeakerSensor(coordinator, entry, ch, CHANNEL_LABELS[ch]))

    async_add_entities(entities)


class DBAudioPowerHoursSensor(DBAudioEntity, SensorEntity):
    _attr_name = "Power Hours"
    _attr_native_unit_of_measurement = "h"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_power_hours"

    @property
    def native_value(self) -> float | None:
        val = self.coordinator.data.get("power_hours")
        return float(val) if val is not None else None


class DBAudioSpeakerSensor(DBAudioEntity, SensorEntity):
    _attr_icon = "mdi:speaker"

    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_speaker_ch_{ch}"
        self._attr_name = f"Speaker Ch {label}"

    @property
    def native_value(self) -> str | None:
        ids = self.coordinator.data.get("speaker_id", [])
        if self._ch >= len(ids):
            return None
        idx = int(ids[self._ch])
        if 0 < idx <= len(SPEAKER_NAMES):
            return SPEAKER_NAMES[idx - 1]
        return str(idx) if idx else None

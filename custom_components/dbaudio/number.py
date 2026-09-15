"""Number entities for d&b audiotechnik amplifiers."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHANNEL_COUNT, CHANNEL_LABELS, DOMAIN
from .coordinator import DBAudioCoordinator
from .entity import DBAudioEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DBAudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[DBAudioEntity] = []

    for ch in range(CHANNEL_COUNT):
        label = CHANNEL_LABELS[ch]
        entities.append(DBAudioLevelNumber(coordinator, entry, ch, label))
        entities.append(DBAudioDelayNumber(coordinator, entry, ch, label))

    async_add_entities(entities)


class DBAudioLevelNumber(DBAudioEntity, NumberEntity):
    _attr_native_min_value = -57.5
    _attr_native_max_value = 6.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_level_ch_{ch}"
        self._attr_name = f"Level Ch {label}"

    @property
    def native_value(self) -> float | None:
        levels = self.coordinator.data.get("level", [])
        return float(levels[self._ch]) if self._ch < len(levels) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.set_level(self._ch, value)


class DBAudioDelayNumber(DBAudioEntity, NumberEntity):
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "ms"
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_delay_ch_{ch}"
        self._attr_name = f"Delay Ch {label}"

    @property
    def native_value(self) -> float | None:
        delays = self.coordinator.data.get("delay", [])
        return float(delays[self._ch]) if self._ch < len(delays) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.set_delay(self._ch, value)

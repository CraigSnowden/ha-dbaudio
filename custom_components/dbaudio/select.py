"""Select entity for d&b audiotechnik preset recall."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PRESET_COUNT
from .coordinator import DBAudioCoordinator
from .entity import DBAudioEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    model = entry.data.get("model", "")
    if model == "5D":
        return  # 5D has no presets

    coordinator: DBAudioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DBAudioPresetSelect(coordinator, entry)])


class DBAudioPresetSelect(DBAudioEntity, SelectEntity):
    _attr_name = "Preset"

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_preset"

    @property
    def options(self) -> list[str]:
        names = self.coordinator.data.get("preset_names", [])
        return [name for name in names if name]

    @property
    def current_option(self) -> str | None:
        last = self.coordinator.data.get("preset_last")
        if last is None:
            return None
        names = self.coordinator.data.get("preset_names", [])
        idx = last - 1
        if 0 <= idx < len(names) and names[idx]:
            return names[idx]
        return None

    async def async_select_option(self, option: str) -> None:
        names = self.coordinator.data.get("preset_names", [])
        try:
            # 1-based index
            index = names.index(option) + 1
        except ValueError:
            return
        await self.coordinator.recall_preset(index)

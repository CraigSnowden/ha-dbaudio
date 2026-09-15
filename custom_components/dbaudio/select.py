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
    coordinator: DBAudioCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[DBAudioEntity] = []

    if model != "5D":
        entities.append(DBAudioPresetSelect(coordinator, entry))

    entities.append(DBAudioInputOverrideModeSelect(coordinator, entry))
    entities.append(DBAudioInputOverrideSourceSelect(coordinator, entry))

    async_add_entities(entities)


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


class DBAudioInputOverrideModeSelect(DBAudioEntity, SelectEntity):
    """Off/Manual/Auto — Manual must be selected for the input override source to take effect."""

    _attr_name = "Input Override Mode"

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_input_override_mode"

    @property
    def options(self) -> list[str]:
        return self.coordinator.data.get("input_override_mode_options", [])

    @property
    def current_option(self) -> str | None:
        options = self.options
        idx = self.coordinator.data.get("input_override_mode", 0)
        return options[idx] if 0 <= idx < len(options) else None

    async def async_select_option(self, option: str) -> None:
        try:
            index = self.options.index(option)
        except ValueError:
            return
        await self.coordinator.set_input_override_mode(index)


class DBAudioInputOverrideSourceSelect(DBAudioEntity, SelectEntity):
    """Manually forces the amp's input to one of its analog/AES3/Milan sources (A1-A4/D1-D4/M1-M8)."""

    _attr_name = "Input Override Source"

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_input_override_source"

    @property
    def options(self) -> list[str]:
        return self.coordinator.data.get("input_override_source_options", [])

    @property
    def current_option(self) -> str | None:
        options = self.options
        idx = self.coordinator.data.get("input_override_source", 0)
        return options[idx] if 0 <= idx < len(options) else None

    async def async_select_option(self, option: str) -> None:
        try:
            index = self.options.index(option)
        except ValueError:
            return
        await self.coordinator.set_input_override_source(index)

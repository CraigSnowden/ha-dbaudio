"""Switch entities for d&b audiotechnik amplifiers."""
from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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
    model = entry.data.get("model", "")
    eq_count = 1 if model == "5D" else 2

    entities: list[DBAudioEntity] = [DBAudioPowerSwitch(coordinator, entry)]

    for ch in range(CHANNEL_COUNT):
        label = CHANNEL_LABELS[ch]
        entities.append(DBAudioMuteSwitch(coordinator, entry, ch, label))
        entities.append(DBAudioDelayEnableSwitch(coordinator, entry, ch, label))
        for eq in range(eq_count):
            entities.append(DBAudioEQBypassSwitch(coordinator, entry, ch, eq, label))
        entities.append(DBAudioCutSwitch(coordinator, entry, ch, label))
        entities.append(DBAudioHFASwitch(coordinator, entry, ch, label))

    entities.append(DBAudioInputGainSwitch(coordinator, entry))

    for source in coordinator.data.get("input_enable_sources", []):
        for ch in range(CHANNEL_COUNT):
            entities.append(
                DBAudioInputEnableSwitch(coordinator, entry, source, ch, CHANNEL_LABELS[ch])
            )

    async_add_entities(entities)


class DBAudioPowerSwitch(DBAudioEntity, SwitchEntity):
    _attr_device_class = SwitchDeviceClass.OUTLET
    _attr_name = "Power"

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_power"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("power", False))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_power(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_power(False)


class DBAudioMuteSwitch(DBAudioEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_mute_ch_{ch}"
        self._attr_name = f"Mute Ch {label}"

    @property
    def is_on(self) -> bool:
        mute = self.coordinator.data.get("mute", [])
        return bool(mute[self._ch]) if self._ch < len(mute) else False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_mute(self._ch, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_mute(self._ch, False)


class DBAudioDelayEnableSwitch(DBAudioEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_delay_enable_ch_{ch}"
        self._attr_name = f"Delay Enable Ch {label}"

    @property
    def is_on(self) -> bool:
        delay_enable = self.coordinator.data.get("delay_enable", [])
        return bool(delay_enable[self._ch]) if self._ch < len(delay_enable) else False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_delay_enable(self._ch, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_delay_enable(self._ch, False)


class DBAudioEQBypassSwitch(DBAudioEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        eq_idx: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._eq_idx = eq_idx
        self._attr_unique_id = f"{entry.entry_id}_eq{eq_idx + 1}_bypass_ch_{ch}"
        self._attr_name = f"EQ{eq_idx + 1} Bypass Ch {label}"

    @property
    def is_on(self) -> bool:
        eq_bypass = self.coordinator.data.get("eq_bypass", [])
        if self._ch >= len(eq_bypass):
            return False
        row = eq_bypass[self._ch]
        return bool(row[self._eq_idx]) if self._eq_idx < len(row) else False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_eq_bypass(self._ch, self._eq_idx, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_eq_bypass(self._ch, self._eq_idx, False)


class DBAudioCutSwitch(DBAudioEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_cut_ch_{ch}"
        self._attr_name = f"CUT Ch {label}"

    @property
    def is_on(self) -> bool:
        values = self.coordinator.data.get("cut_enable", [])
        return bool(values[self._ch]) if self._ch < len(values) else False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_cut_enable(self._ch, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_cut_enable(self._ch, False)


class DBAudioHFASwitch(DBAudioEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_hfa_ch_{ch}"
        self._attr_name = f"HFA Ch {label}"

    @property
    def is_on(self) -> bool:
        values = self.coordinator.data.get("hfa_enable", [])
        return bool(values[self._ch]) if self._ch < len(values) else False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_hfa_enable(self._ch, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_hfa_enable(self._ch, False)


class DBAudioInputGainSwitch(DBAudioEntity, SwitchEntity):
    _attr_name = "Input Gain Enable"

    def __init__(self, coordinator: DBAudioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_input_gain_enable"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("input_gain_enable", False))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_input_gain_enable(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_input_gain_enable(False)


class DBAudioInputEnableSwitch(DBAudioEntity, SwitchEntity):
    """Whether a given input source (e.g. A1, D2) is routed into a given output channel."""

    def __init__(
        self,
        coordinator: DBAudioCoordinator,
        entry: ConfigEntry,
        source: str,
        ch: int,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._source = source
        self._ch = ch
        self._attr_unique_id = f"{entry.entry_id}_input_enable_{source}_ch_{ch}"
        self._attr_name = f"Input {source} Enable Ch {label}"

    @property
    def is_on(self) -> bool:
        key = f"{self._source}_{self._ch}"
        return bool(self.coordinator.data.get("input_enable", {}).get(key, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_input_enable(self._source, self._ch, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_input_enable(self._source, self._ch, False)

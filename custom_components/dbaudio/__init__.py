"""d&b audiotechnik amplifier integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, DOMAIN, MODEL_PORT, PLATFORMS
from .coordinator import DBAudioCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.options.get(CONF_HOST, entry.data[CONF_HOST])
    model = entry.data[CONF_MODEL]
    port = entry.options.get(
        CONF_PORT,
        entry.data.get(CONF_PORT, MODEL_PORT.get(model, 30013)),
    )

    coordinator = DBAudioCoordinator(hass, host=host, port=port, model=model)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: DBAudioCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)

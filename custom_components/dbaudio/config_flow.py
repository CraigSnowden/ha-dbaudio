"""Config flow for d&b audiotechnik amplifier integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_MODEL, DOMAIN, MODEL_PORT, MODELS


def _port_for(model: str, custom_port: int | None) -> int:
    if model == "custom" and custom_port:
        return int(custom_port)
    return MODEL_PORT.get(model, 30013)


class DBAudioConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            model = user_input[CONF_MODEL]
            port = _port_for(model, user_input.get(CONF_PORT))

            try:
                name = await self._try_connect(host, port)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{host}_{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name or host,
                    data={CONF_HOST: host, CONF_MODEL: model, CONF_PORT: port},
                )

        model_choices = {m: m for m in MODELS}

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="169.254.0.1"): str,
                vol.Required(CONF_MODEL, default="D20"): vol.In(model_choices),
                vol.Optional(CONF_PORT, default=30013): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _try_connect(self, host: str, port: int) -> str:
        """Attempt connection and return device name. Raises on failure."""
        loop = self.hass.loop

        def _connect():
            from aes70.controller import tcp_connection
            from aes70.controller.remote_device import RemoteDevice

            conn = tcp_connection.connect(host=host, port=port)
            dev = RemoteDevice(conn)
            dev.set_keepalive_interval(1)
            return dev

        device = await self.hass.async_add_executor_job(_connect)

        try:
            name = await device.DeviceManager.GetDeviceName()
            return str(name).strip()
        finally:
            try:
                device.close()
            except Exception:
                pass

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DBAudioOptionsFlow(config_entry)


class DBAudioOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            model = self._entry.data.get(CONF_MODEL, "D20")
            port = _port_for(model, user_input.get(CONF_PORT))

            try:
                await self._try_connect(host, port)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="",
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        current_host = self._entry.options.get(
            CONF_HOST, self._entry.data.get(CONF_HOST, "169.254.0.1")
        )
        current_port = self._entry.options.get(
            CONF_PORT, self._entry.data.get(CONF_PORT, 30013)
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_host): str,
                vol.Required(CONF_PORT, default=current_port): int,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _try_connect(self, host: str, port: int) -> None:
        def _connect():
            from aes70.controller import tcp_connection

            conn = tcp_connection.connect(host=host, port=port)
            try:
                from aes70.controller.remote_device import RemoteDevice
                dev = RemoteDevice(conn)
                dev.close()
            except Exception:
                pass

        await self.hass.async_add_executor_job(_connect)

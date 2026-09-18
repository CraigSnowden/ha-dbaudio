"""AES70/OCA device interface for d&b audiotechnik amplifiers."""
from __future__ import annotations

import asyncio
import logging
import re
import struct
from typing import Any, Callable, Optional

_LOGGER = logging.getLogger(__name__)

DELAY_5D_BASE_ONO = 268469258
DELAY_5D_OFFSET = 32768
CHANNEL_COUNT = 4
PRESET_COUNT = 15

_PRESETS_ROLE = "AmpPresets"

# Only expose the analog (A1-A4) and AES3/digital (D1-D4) input-enable sources as
# switches; Milan (M1-M8) and C1/C2 sources are discovered but skipped by default.
_INPUT_ENABLE_LABEL_RE = re.compile(r"^Input ([AD])(\d+)$")


def _extract(result: Any) -> Any:
    """Return the first value from an aes70py Arguments object or the value itself."""
    if hasattr(result, "item"):
        return result.item(0)
    if hasattr(result, "values") and isinstance(result.values, (list, tuple)):
        return result.values[0]
    return result


def _extract_values(result: Any) -> list:
    """Return all values ([position, min, max]) from an OcaSwitch-style GetPosition() result."""
    if hasattr(result, "values") and isinstance(result.values, (list, tuple)):
        return list(result.values)
    if hasattr(result, "item"):
        return [result.item(0)]
    if isinstance(result, (list, tuple)):
        return list(result)
    return [result]


class DBAudioDevice:
    """High-level interface to a d&b audiotechnik amplifier via AES70/OCA."""

    def __init__(
        self,
        host: str,
        port: int,
        model: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._host = host
        self._port = port
        self._model = model
        self._loop = loop

        self._connection = None
        self._device = None
        self._role_map: dict = {}
        self._unsubscribers: list[Callable] = []

        eq_count = self._eq_count()
        self.state: dict[str, Any] = {
            "power": False,
            "mute": [False] * CHANNEL_COUNT,
            "level": [0.0] * CHANNEL_COUNT,
            "delay": [0.0] * CHANNEL_COUNT,
            "delay_enable": [False] * CHANNEL_COUNT,
            "eq_bypass": [[False] * eq_count for _ in range(CHANNEL_COUNT)],
            "cut_enable": [False] * CHANNEL_COUNT,
            "hfa_enable": [False] * CHANNEL_COUNT,
            "input_gain_enable": False,
            "input_override_mode": 0,
            "input_override_mode_options": [],
            "input_override_source": 0,
            "input_override_source_options": [],
            "input_enable_sources": [],  # source labels discovered at connect, e.g. ["A1", "D2"]
            "input_enable": {},  # "{source_label}_{ch}" -> bool
            "preset_names": [],
            "preset_last": None,
            "power_hours": 0.0,
            "speaker_id": [0] * CHANNEL_COUNT,
            "amp_type": model,
            "amp_name": "",
            "amp_firmware": "",
        }

        # Callbacks called from the asyncio event loop
        self.on_state_updated: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

        # OCA object references
        self._power_obj = None
        self._mute_objs: list = []
        self._level_objs: list = []
        self._delay_objs: list = []
        self._delay_enable_objs: list = []
        self._eq_objs: list[list] = []
        self._cut_objs: list = []
        self._hfa_objs: list = []
        self._input_gain_obj = None
        self._input_override_mode_obj = None
        self._input_override_mode_min = 0
        self._input_override_source_obj = None
        self._input_override_source_min = 0
        self._input_enable_objs: dict[tuple[str, int], Any] = {}
        self._preset_obj = None
        self._preset_name_objs: list = []
        self._preset_last_objs: list = []
        self._power_hours_obj = None
        self._speaker_objs: list = []

    # --- Model helpers ---

    def _is_5d(self) -> bool:
        return self._model == "5D"

    def _config_path(self) -> str:
        return "Config_Box" if self._is_5d() else "Config"

    def _settings_path(self) -> str:
        return "Settings_Box" if self._is_5d() else "Settings"

    def _eq_count(self) -> int:
        return 1 if self._model == "5D" else 2

    def _has_presets(self) -> bool:
        return self._model != "5D"

    # --- Connection lifecycle ---

    def connect_blocking(self) -> None:
        """Blocking TCP connect. Must be run in an executor."""
        from aes70.controller import tcp_connection
        from aes70.controller.remote_device import RemoteDevice

        self._connection = tcp_connection.connect(host=self._host, port=self._port)
        self._device = RemoteDevice(self._connection)
        self._device.set_keepalive_interval(1)

    def disconnect(self) -> None:
        """Close connection and release subscriptions. Thread-safe."""
        self._cleanup_subscriptions()
        try:
            if self._device:
                self._device.close()
        except Exception:
            pass

    async def initialize(self) -> None:
        """Complete async initialization. Must be called after connect_blocking()."""
        from aes70.controller.control_classes.ocamute import OcaMute
        from aes70.types.ocamutestate import OcaMuteState

        self._device.on("close", self._on_close)
        self._device.on("error", self._on_error)

        # Device info
        try:
            desc = await self._device.DeviceManager.GetModelDescription()
            if hasattr(desc, "Name"):
                self.state["amp_type"] = str(desc.Name).strip() or self._model
            if hasattr(desc, "Version"):
                self.state["amp_firmware"] = str(desc.Version).strip()
        except Exception:
            _LOGGER.debug("Could not read ModelDescription")

        try:
            name = await self._device.DeviceManager.GetDeviceName()
            self.state["amp_name"] = str(name).strip()
        except Exception:
            _LOGGER.debug("Could not read DeviceName")

        self._role_map = await self._device.get_role_map()
        input_roles = [path for path in self._role_map if "Input" in path]
        if input_roles:
            _LOGGER.debug("Role map paths containing 'Input': %s", input_roles)

        await self._init_power()
        await self._init_mute(OcaMute, OcaMuteState)
        await self._init_levels()
        await self._init_delays()
        await self._init_delay_enables()
        await self._init_eq()
        await self._init_cut_hfa()
        await self._init_input_gain()
        await self._init_input_override()
        await self._init_input_enable_matrix()
        await self._init_speaker_ids()
        await self._init_power_hours()
        if self._has_presets():
            await self._init_presets()

    # --- Event loop helpers ---

    def _dispatch(self, fn: Callable, *args: Any) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(fn, *args)

    def _notify_update(self) -> None:
        if self.on_state_updated:
            self._dispatch(self.on_state_updated)

    def _on_close(self) -> None:
        _LOGGER.warning("d&b amp %s:%s disconnected", self._host, self._port)
        self._cleanup_subscriptions()
        if self.on_disconnected:
            self._dispatch(self.on_disconnected)

    def _on_error(self, error: Any) -> None:
        _LOGGER.warning("d&b amp %s:%s error: %s", self._host, self._port, error)
        self._cleanup_subscriptions()
        if self.on_disconnected:
            self._dispatch(self.on_disconnected)

    def _cleanup_subscriptions(self) -> None:
        for unsub in self._unsubscribers:
            try:
                unsub()
            except Exception:
                pass
        self._unsubscribers.clear()

    def _subscribe(self, event: Any, callback: Callable[[Any], None]) -> None:
        def _wrapper(value: Any, change_type: Any = None, prop_id: Any = None) -> None:
            callback(value)

        def _err(error: Any) -> None:
            _LOGGER.debug("Subscription error on %s: %s", self._host, error)

        try:
            unsub = event.subscribe(_wrapper, _err)
            self._unsubscribers.append(unsub)
        except Exception as exc:
            _LOGGER.debug("Could not subscribe to event: %s", exc)

    # --- Power ---

    async def _init_power(self) -> None:
        path = f"{self._settings_path()}/Settings_PwrOn"
        obj = self._role_map.get(path)
        if obj is None:
            _LOGGER.debug("Power object not found at %s", path)
            return
        self._power_obj = obj

        try:
            result = await obj.GetPosition()
            pos = int(_extract(result))
            self.state["power"] = self._pos_to_power(pos)
        except Exception as exc:
            _LOGGER.debug("Could not read power state: %s", exc)

        def _on_power(val: Any) -> None:
            self.state["power"] = self._pos_to_power(int(val))
            self._notify_update()

        self._subscribe(obj.OnPositionChanged, _on_power)

    def _pos_to_power(self, pos: int) -> bool:
        return pos == 0 if self._is_5d() else pos == 1

    async def set_power(self, on: bool) -> None:
        if self._power_obj is None:
            return
        pos = (0 if on else 1) if self._is_5d() else (1 if on else 0)
        try:
            await self._power_obj.SetPosition(pos)
        except Exception as exc:
            _LOGGER.warning("set_power failed: %s", exc)

    # --- Mute ---

    async def _init_mute(self, OcaMute: type, OcaMuteState: Any) -> None:
        tree = await self._device.get_device_tree()
        self._mute_objs = []

        def _walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk(item)
            elif isinstance(node, OcaMute):
                self._mute_objs.append(node)

        _walk(tree)

        for i, obj in enumerate(self._mute_objs[:CHANNEL_COUNT]):
            try:
                state = await obj.GetState()
                self.state["mute"][i] = state == OcaMuteState.Muted
            except Exception as exc:
                _LOGGER.debug("Could not read mute state ch %d: %s", i, exc)

            ch = i

            def _on_mute(val: Any, _ch: int = ch, _ms: Any = OcaMuteState) -> None:
                self.state["mute"][_ch] = val == _ms.Muted
                self._notify_update()

            self._subscribe(obj.OnStateChanged, _on_mute)

    async def set_mute(self, ch: int, muted: bool) -> None:
        from aes70.types.ocamutestate import OcaMuteState

        if ch >= len(self._mute_objs):
            return
        try:
            state = OcaMuteState.Muted if muted else OcaMuteState.Unmuted
            await self._mute_objs[ch].SetState(state)
        except Exception as exc:
            _LOGGER.warning("set_mute ch%d failed: %s", ch, exc)

    # --- Channel level ---

    async def _init_levels(self) -> None:
        self._level_objs = []
        for i in range(1, CHANNEL_COUNT + 1):
            path = f"{self._config_path()}/Config_PotiLevel{i}"
            obj = self._role_map.get(path)
            self._level_objs.append(obj)
            if obj is None:
                continue

            try:
                result = await obj.GetGain()
                self.state["level"][i - 1] = float(_extract(result))
            except Exception as exc:
                _LOGGER.debug("Could not read level ch%d: %s", i - 1, exc)

            ch = i - 1

            def _on_level(val: Any, _ch: int = ch) -> None:
                self.state["level"][_ch] = float(val)
                self._notify_update()

            self._subscribe(obj.OnGainChanged, _on_level)

    async def set_level(self, ch: int, db: float) -> None:
        if ch >= len(self._level_objs) or self._level_objs[ch] is None:
            return
        try:
            await self._level_objs[ch].SetGain(db)
        except Exception as exc:
            _LOGGER.warning("set_level ch%d failed: %s", ch, exc)

    # --- Delay ---

    async def _init_delays(self) -> None:
        self._delay_objs = []

        if self._is_5d():
            from aes70.controller.control_classes.ocadelay import OcaDelay

            for i in range(CHANNEL_COUNT):
                ono = DELAY_5D_BASE_ONO + i * DELAY_5D_OFFSET
                obj = OcaDelay(ono, self._device)
                self._delay_objs.append(obj)

                try:
                    result = await obj.GetDelayTime()
                    self.state["delay"][i] = round(float(_extract(result)) * 1000, 2)
                except Exception as exc:
                    _LOGGER.debug("Could not read 5D delay ch%d: %s", i, exc)

                def _on_delay_5d(val: Any, _i: int = i) -> None:
                    self.state["delay"][_i] = round(float(val) * 1000, 2)
                    self._notify_update()

                self._subscribe(obj.OnDelayTimeChanged, _on_delay_5d)
        else:
            for i in range(1, CHANNEL_COUNT + 1):
                path = f"{self._config_path()}/Config_Delay{i}"
                obj = self._role_map.get(path)
                self._delay_objs.append(obj)
                if obj is None:
                    continue

                try:
                    result = await obj.GetSetting()
                    self.state["delay"][i - 1] = round(float(_extract(result)), 2)
                except Exception as exc:
                    _LOGGER.debug("Could not read delay ch%d: %s", i - 1, exc)

                ch = i - 1

                def _on_delay(val: Any, _ch: int = ch) -> None:
                    self.state["delay"][_ch] = round(float(val), 2)
                    self._notify_update()

                self._subscribe(obj.OnSettingChanged, _on_delay)

    async def set_delay(self, ch: int, ms: float) -> None:
        if ch >= len(self._delay_objs) or self._delay_objs[ch] is None:
            return
        try:
            if self._is_5d():
                await self._delay_objs[ch].SetDelayTime(ms / 1000.0)
            else:
                await self._delay_objs[ch].SetSetting(ms)
        except Exception as exc:
            _LOGGER.warning("set_delay ch%d failed: %s", ch, exc)

    # --- Delay enable ---

    async def _init_delay_enables(self) -> None:
        self._delay_enable_objs = []
        for i in range(1, CHANNEL_COUNT + 1):
            path = f"{self._config_path()}/Config_DelayOn{i}"
            obj = self._role_map.get(path)
            self._delay_enable_objs.append(obj)
            if obj is None:
                continue

            try:
                result = await obj.GetPosition()
                self.state["delay_enable"][i - 1] = int(_extract(result)) == 1
            except Exception as exc:
                _LOGGER.debug("Could not read delay_enable ch%d: %s", i - 1, exc)

            ch = i - 1

            def _on_delay_enable(val: Any, _ch: int = ch) -> None:
                self.state["delay_enable"][_ch] = int(val) == 1
                self._notify_update()

            self._subscribe(obj.OnPositionChanged, _on_delay_enable)

    async def set_delay_enable(self, ch: int, enabled: bool) -> None:
        if ch >= len(self._delay_enable_objs) or self._delay_enable_objs[ch] is None:
            return
        try:
            await self._delay_enable_objs[ch].SetPosition(1 if enabled else 0)
        except Exception as exc:
            _LOGGER.warning("set_delay_enable ch%d failed: %s", ch, exc)

    # --- EQ bypass ---

    async def _init_eq(self) -> None:
        self._eq_objs = []
        eq_count = self._eq_count()

        for ch in range(CHANNEL_COUNT):
            eq_set: list = []
            for eq_idx in range(eq_count):
                path = f"{self._config_path()}/Config_Eq{eq_idx + 1}Enable{ch + 1}"
                obj = self._role_map.get(path)
                eq_set.append(obj)
                if obj is None:
                    continue

                try:
                    result = await obj.GetPosition()
                    self.state["eq_bypass"][ch][eq_idx] = int(_extract(result)) == 0
                except Exception as exc:
                    _LOGGER.debug("Could not read eq_bypass ch%d eq%d: %s", ch, eq_idx, exc)

                def _on_eq(val: Any, _ch: int = ch, _eq: int = eq_idx) -> None:
                    self.state["eq_bypass"][_ch][_eq] = int(val) == 0
                    self._notify_update()

                self._subscribe(obj.OnPositionChanged, _on_eq)

            self._eq_objs.append(eq_set)

    async def set_eq_bypass(self, ch: int, eq_idx: int, bypassed: bool) -> None:
        if ch >= len(self._eq_objs) or eq_idx >= len(self._eq_objs[ch]):
            return
        obj = self._eq_objs[ch][eq_idx]
        if obj is None:
            return
        try:
            await obj.SetPosition(0 if bypassed else 1)
        except Exception as exc:
            _LOGGER.warning("set_eq_bypass ch%d eq%d failed: %s", ch, eq_idx, exc)

    # --- CUT / HFA filter enable ---
    # Config_Filter1{ch} = "CUT", Config_Filter2{ch} = "HFA" (per the device's own
    # ChStatus_Filter*Name label: "Name of filter (CUT, HFA,..)"). Same On/Off switch
    # shape as EQ bypass above.

    async def _init_cut_hfa(self) -> None:
        self._cut_objs = []
        self._hfa_objs = []

        for i in range(1, CHANNEL_COUNT + 1):
            ch = i - 1

            cut_obj = self._role_map.get(f"{self._config_path()}/Config_Filter1{i}")
            self._cut_objs.append(cut_obj)
            if cut_obj is not None:
                try:
                    result = await cut_obj.GetPosition()
                    self.state["cut_enable"][ch] = int(_extract(result)) == 1
                except Exception as exc:
                    _LOGGER.debug("Could not read cut_enable ch%d: %s", ch, exc)

                def _on_cut(val: Any, _ch: int = ch) -> None:
                    self.state["cut_enable"][_ch] = int(val) == 1
                    self._notify_update()

                self._subscribe(cut_obj.OnPositionChanged, _on_cut)

            hfa_obj = self._role_map.get(f"{self._config_path()}/Config_Filter2{i}")
            self._hfa_objs.append(hfa_obj)
            if hfa_obj is not None:
                try:
                    result = await hfa_obj.GetPosition()
                    self.state["hfa_enable"][ch] = int(_extract(result)) == 1
                except Exception as exc:
                    _LOGGER.debug("Could not read hfa_enable ch%d: %s", ch, exc)

                def _on_hfa(val: Any, _ch: int = ch) -> None:
                    self.state["hfa_enable"][_ch] = int(val) == 1
                    self._notify_update()

                self._subscribe(hfa_obj.OnPositionChanged, _on_hfa)

    async def set_cut_enable(self, ch: int, enabled: bool) -> None:
        if ch >= len(self._cut_objs) or self._cut_objs[ch] is None:
            return
        try:
            await self._cut_objs[ch].SetPosition(1 if enabled else 0)
        except Exception as exc:
            _LOGGER.warning("set_cut_enable ch%d failed: %s", ch, exc)

    async def set_hfa_enable(self, ch: int, enabled: bool) -> None:
        if ch >= len(self._hfa_objs) or self._hfa_objs[ch] is None:
            return
        try:
            await self._hfa_objs[ch].SetPosition(1 if enabled else 0)
        except Exception as exc:
            _LOGGER.warning("set_hfa_enable ch%d failed: %s", ch, exc)

    # --- Input gain enable ---

    async def _init_input_gain(self) -> None:
        path = f"{self._settings_path()}/Settings_InputGainEnable"
        obj = self._role_map.get(path)
        if obj is None:
            return
        self._input_gain_obj = obj

        try:
            result = await obj.GetPosition()
            self.state["input_gain_enable"] = int(_extract(result)) == 1
        except Exception as exc:
            _LOGGER.debug("Could not read input_gain_enable: %s", exc)

        def _on_input_gain(val: Any) -> None:
            self.state["input_gain_enable"] = int(val) == 1
            self._notify_update()

        self._subscribe(obj.OnPositionChanged, _on_input_gain)

    async def set_input_gain_enable(self, enabled: bool) -> None:
        if self._input_gain_obj is None:
            return
        try:
            await self._input_gain_obj.SetPosition(1 if enabled else 0)
        except Exception as exc:
            _LOGGER.warning("set_input_gain_enable failed: %s", exc)

    # --- Input override (manual input source selection) ---

    async def _init_enum_switch(
        self, path: str, state_key: str, options_key: str
    ) -> tuple[Any, int]:
        """Init an OcaSwitch-style object exposing GetPosition()->[pos,min,max] and GetPositionNames().

        Returns (obj, min_value) so callers can convert a 0-based option index back to a
        device position with `index + min_value`.
        """
        obj = self._role_map.get(path)
        if obj is None:
            _LOGGER.debug("Enum switch object not found at %s", path)
            return None, 0

        try:
            names = await obj.GetPositionNames()
            self.state[options_key] = list(names)
        except Exception as exc:
            _LOGGER.debug("Could not read position names for %s: %s", path, exc)

        min_value = 0
        try:
            position, min_value, _max = _extract_values(await obj.GetPosition())
            self.state[state_key] = int(position) - int(min_value)
        except Exception as exc:
            _LOGGER.debug("Could not read position for %s: %s", path, exc)

        def _on_change(val: Any, _key: str = state_key, _min: int = min_value) -> None:
            self.state[_key] = int(val) - _min
            self._notify_update()

        self._subscribe(obj.OnPositionChanged, _on_change)
        return obj, min_value

    async def _init_input_override(self) -> None:
        self._input_override_mode_obj, self._input_override_mode_min = (
            await self._init_enum_switch(
                f"{self._settings_path()}/Settings_InputOverrideMode",
                "input_override_mode",
                "input_override_mode_options",
            )
        )
        self._input_override_source_obj, self._input_override_source_min = (
            await self._init_enum_switch(
                f"{self._settings_path()}/Settings_InputOverrideSource",
                "input_override_source",
                "input_override_source_options",
            )
        )

    async def set_input_override_mode(self, index: int) -> None:
        if self._input_override_mode_obj is None:
            return
        try:
            await self._input_override_mode_obj.SetPosition(
                index + self._input_override_mode_min
            )
        except Exception as exc:
            _LOGGER.warning("set_input_override_mode failed: %s", exc)

    async def set_input_override_source(self, index: int) -> None:
        if self._input_override_source_obj is None:
            return
        try:
            await self._input_override_source_obj.SetPosition(
                index + self._input_override_source_min
            )
        except Exception as exc:
            _LOGGER.warning("set_input_override_source failed: %s", exc)

    # --- Input enable matrix (per-channel routing gates for analog/AES3 sources) ---

    async def _init_input_enable_matrix(self) -> None:
        """Discover Config_InputEnable objects and group them by source and channel.

        Each source (e.g. "A1", "D2") has CHANNEL_COUNT instances in the role map with
        no fixed path naming, but each instance's `ono` increases by a fixed stride per
        channel (same pattern as DELAY_5D_OFFSET) - sorting by ono recovers channel order.
        """
        groups: dict[str, list[tuple[int, Any]]] = {}

        for path, obj in self._role_map.items():
            if "InputEnable" not in path:
                continue
            try:
                label = await obj.GetLabel()
            except Exception:
                continue
            match = _INPUT_ENABLE_LABEL_RE.match(label)
            if match is None:
                continue
            source = match.group(1) + match.group(2)
            groups.setdefault(source, []).append((obj.ono, obj))

        sources: list[str] = []
        for source in sorted(groups, key=lambda s: (s[0], int(s[1:]))):
            instances = sorted(groups[source], key=lambda t: t[0])
            if len(instances) < CHANNEL_COUNT:
                _LOGGER.debug(
                    "Expected %d input_enable instances for %s, found %d",
                    CHANNEL_COUNT, source, len(instances),
                )
                continue
            sources.append(source)

            for ch, (_, obj) in enumerate(instances[:CHANNEL_COUNT]):
                self._input_enable_objs[(source, ch)] = obj
                key = f"{source}_{ch}"

                try:
                    result = await obj.GetPosition()
                    self.state["input_enable"][key] = int(_extract(result)) == 1
                except Exception as exc:
                    _LOGGER.debug("Could not read input_enable %s: %s", key, exc)

                def _on_change(val: Any, _key: str = key) -> None:
                    self.state["input_enable"][_key] = int(val) == 1
                    self._notify_update()

                self._subscribe(obj.OnPositionChanged, _on_change)

        self.state["input_enable_sources"] = sources

    async def set_input_enable(self, source: str, ch: int, enabled: bool) -> None:
        obj = self._input_enable_objs.get((source, ch))
        if obj is None:
            return
        try:
            await obj.SetPosition(1 if enabled else 0)
        except Exception as exc:
            _LOGGER.warning("set_input_enable %s ch%d failed: %s", source, ch, exc)

    # --- Speaker IDs ---

    async def _init_speaker_ids(self) -> None:
        self._speaker_objs = []
        for i in range(1, CHANNEL_COUNT + 1):
            path = f"{self._config_path()}/Config_SpeakerId{i}"
            obj = self._role_map.get(path)
            self._speaker_objs.append(obj)
            if obj is None:
                continue

            try:
                if self._is_5d():
                    result = await obj.GetReading()
                else:
                    result = await obj.GetPosition()
                self.state["speaker_id"][i - 1] = int(_extract(result))
            except Exception as exc:
                _LOGGER.debug("Could not read speaker_id ch%d: %s", i - 1, exc)

            ch = i - 1

            def _on_speaker(val: Any, _ch: int = ch) -> None:
                self.state["speaker_id"][_ch] = int(val)
                self._notify_update()

            event = obj.OnReadingChanged if self._is_5d() else obj.OnPositionChanged
            self._subscribe(event, _on_speaker)

    # --- Power hours (polled by coordinator) ---

    async def _init_power_hours(self) -> None:
        path = "Log_Box/Log_PowerOnHours" if self._is_5d() else "Log/Log_PowerOnHours"
        self._power_hours_obj = self._role_map.get(path)

    async def read_power_hours(self) -> float:
        if self._power_hours_obj is None:
            return 0.0
        try:
            result = await self._power_hours_obj.GetReading()
            return float(_extract(result))
        except Exception:
            return 0.0

    # --- Presets ---

    async def _init_presets(self) -> None:
        self.state["preset_names"] = [""] * PRESET_COUNT
        self._preset_name_objs = []
        for i in range(1, PRESET_COUNT + 1):
            path = f"Preset/Preset_PresetName{i}"
            obj = self._role_map.get(path)
            self._preset_name_objs.append(obj)
            if obj is None:
                continue

            try:
                result = await obj.GetSetting()
                # String settings return directly (single return type)
                self.state["preset_names"][i - 1] = str(result) if result else ""
            except Exception as exc:
                _LOGGER.debug("Could not read preset name %d: %s", i, exc)

            def _on_preset_name(val: Any, _i: int = i) -> None:
                self.state["preset_names"][_i - 1] = str(val) if val else ""
                self._notify_update()

            self._subscribe(obj.OnSettingChanged, _on_preset_name)

        # Last recalled preset
        self._preset_last_objs = []
        for i in range(1, PRESET_COUNT + 1):
            path = f"Preset/Preset_LastPreset{i}"
            obj = self._role_map.get(path)
            self._preset_last_objs.append(obj)

        await self._read_preset_last()

        # AmpPresets control agent
        self._preset_obj = self._role_map.get(_PRESETS_ROLE)
        if self._preset_obj is None:
            _LOGGER.debug("AmpPresets agent not in role map")

    async def _read_preset_last(self) -> None:
        last: int | None = None
        for i, obj in enumerate(self._preset_last_objs, 1):
            if obj is None:
                continue
            try:
                result = await obj.GetReading()
                val = _extract(result)
                if float(val) > 0:
                    last = i
            except Exception:
                pass
        self.state["preset_last"] = last

    async def recall_preset(self, index: int) -> None:
        """Recall preset by 1-based index (1–15)."""
        if self._preset_obj is None:
            _LOGGER.warning("Cannot recall preset: AmpPresets agent not found")
            return

        if hasattr(self._preset_obj, "SetPreset"):
            try:
                await self._preset_obj.SetPreset(index)
                return
            except Exception as exc:
                _LOGGER.warning("SetPreset failed, trying raw command: %s", exc)

        # Fallback: send the OCA command as raw bytes.
        # SetPreset is method level=3, index=3, single OcaInt8 parameter.
        await self._recall_preset_raw(index)

    async def _recall_preset_raw(self, index: int) -> None:
        try:
            from aes70.ocp1.commandrrq import CommandRrq

            params = bytearray(1)
            struct.pack_into("!b", params, 0, index)
            cmd = CommandRrq(self._preset_obj.ono, 3, 3, 1, params)
            await self._device.send_command(cmd, [])
        except Exception as exc:
            _LOGGER.warning("Raw preset recall failed: %s", exc)

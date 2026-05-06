"""Tapo light-effect Remote entity.

One per LightEffect-capable device. The effect names (Aurora, Sunset,
Bubbling Cauldron, ...) are exposed as ``simple_commands`` so users can
either pick them from the Web Configurator dropdown when editing a button,
or type the effect name as a custom command via the Send-Command path.
Either route lands in ``_handle_command`` and ends up calling
``device.cmd_set_effect(name)``.

Effect names go in verbatim (`"Sunset"`, `"Bubbling Cauldron"`,
`"Grandma's Christmas Lights"`) because that's what users see in the Tapo
app and what they'd think to type. The handler is lenient and also
accepts case-insensitive matches so `"sunset"` works too.

Power on/off / brightness / colour live on the Light entity for the same
device. The Remote entity is purely a command surface for effects, so it
declares only ``SEND_CMD`` features and ships with no UI pages or
button-mapping defaults; users compose their own.
"""

import logging
from typing import Any

from ucapi import remote, StatusCodes
from ucapi_framework import RemoteEntity

from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState
from uc_intg_tapo.device import TapoDevice

_LOG = logging.getLogger(__name__)


class TapoEffectRemote(RemoteEntity):
    def __init__(self, device_config: TapoDeviceConfig, device: TapoDevice) -> None:
        self._device = device
        # Element 0 is python-kasa's OFF sentinel — keep it in simple_commands
        # so users can also bind a "stop the effect" button if they want.
        self._effect_names: list[str] = list(device_config.effect_names or [])
        # Case-insensitive lookup so the user typing "sunset" or "SUNSET"
        # still resolves to the canonical "Sunset" before we hit kasa.
        self._lookup = {e.lower(): e for e in self._effect_names}

        entity_id = f"remote.tapo_{device_config.identifier}_effect"
        name = f"{device_config.name} Effects"

        super().__init__(
            entity_id,
            name,
            features=[remote.Features.SEND_CMD],
            attributes={remote.Attributes.STATE: remote.States.UNKNOWN},
            simple_commands=list(self._effect_names),
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == DeviceState.UNAVAILABLE:
            self.update({remote.Attributes.STATE: remote.States.UNAVAILABLE})
            return
        # The Light entity owns on/off; this Remote is purely a command
        # surface, so report ON whenever the device is reachable.
        self.update({remote.Attributes.STATE: remote.States.ON})

    async def _handle_command(
        self,
        entity: remote.Remote,
        cmd_id: str,
        params: dict[str, Any] | None,
    ) -> StatusCodes:
        _LOG.debug("[%s] Command: %s params=%s", self.id, cmd_id, params)

        if cmd_id == remote.Commands.SEND_CMD:
            command = (params or {}).get("command", "") or ""
            return await self._apply_effect(command)

        if cmd_id == remote.Commands.SEND_CMD_SEQUENCE:
            sequence = (params or {}).get("sequence", []) or []
            for cmd in sequence:
                rc = await self._apply_effect(cmd)
                if rc != StatusCodes.OK:
                    return rc
            return StatusCodes.OK

        # Direct simple-command invocation (button mapped to an effect name
        # without going through SEND_CMD).
        if cmd_id in self._effect_names or cmd_id.lower() in self._lookup:
            return await self._apply_effect(cmd_id)

        _LOG.warning("[%s] Unknown command: %r", self.id, cmd_id)
        return StatusCodes.NOT_IMPLEMENTED

    async def _apply_effect(self, name: str) -> StatusCodes:
        if not name:
            return StatusCodes.BAD_REQUEST
        # Case-insensitive resolution to the canonical effect name kasa expects.
        canonical = self._lookup.get(name.lower())
        if canonical is None:
            _LOG.warning(
                "[%s] Effect not in this device's catalogue: %r (valid: %s)",
                self.id, name, self._effect_names,
            )
            return StatusCodes.BAD_REQUEST
        ok = await self._device.cmd_set_effect(canonical)
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

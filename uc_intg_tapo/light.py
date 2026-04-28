"""Tapo Light entity. Phase 1 advertises ON_OFF only."""

import logging
from typing import Any

from ucapi import light, StatusCodes
from ucapi_framework import LightEntity

from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState
from uc_intg_tapo.device import TapoDevice

_LOG = logging.getLogger(__name__)

FEATURES = [light.Features.ON_OFF]


class TapoLight(LightEntity):
    def __init__(self, device_config: TapoDeviceConfig, device: TapoDevice) -> None:
        self._device = device
        entity_id = f"light.tapo_{device_config.identifier}"

        super().__init__(
            entity_id,
            device_config.name,
            features=FEATURES,
            attributes={
                light.Attributes.STATE: light.States.UNAVAILABLE,
            },
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == DeviceState.UNAVAILABLE:
            self.update({light.Attributes.STATE: light.States.UNAVAILABLE})
            return
        state = light.States.ON if self._device.is_on else light.States.OFF
        self.update({light.Attributes.STATE: state})

    async def _handle_command(
        self,
        entity: light.Light,
        cmd_id: str,
        params: dict[str, Any] | None,
    ) -> StatusCodes:
        _LOG.debug("[%s] Command: %s", self.id, cmd_id)
        if cmd_id == light.Commands.ON:
            ok = await self._device.cmd_turn_on()
        elif cmd_id == light.Commands.OFF:
            ok = await self._device.cmd_turn_off()
        elif cmd_id == light.Commands.TOGGLE:
            ok = await self._device.cmd_toggle()
        else:
            return StatusCodes.NOT_IMPLEMENTED
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

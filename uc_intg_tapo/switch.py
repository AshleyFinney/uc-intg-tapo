"""Tapo Switch entity for plugs (P100 / P110). Advertises ON_OFF + TOGGLE."""

import logging
from typing import Any

from ucapi import switch, StatusCodes
from ucapi_framework import SwitchEntity

from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState
from uc_intg_tapo.device import TapoDevice

_LOG = logging.getLogger(__name__)

FEATURES = [switch.Features.ON_OFF, switch.Features.TOGGLE]


class TapoSwitch(SwitchEntity):
    def __init__(self, device_config: TapoDeviceConfig, device: TapoDevice) -> None:
        self._device = device
        entity_id = f"switch.tapo_{device_config.identifier}"

        super().__init__(
            entity_id,
            device_config.name,
            features=FEATURES,
            attributes={
                switch.Attributes.STATE: switch.States.UNAVAILABLE,
            },
            device_class=switch.DeviceClasses.OUTLET,
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == DeviceState.UNAVAILABLE:
            self.update({switch.Attributes.STATE: switch.States.UNAVAILABLE})
            return
        state = switch.States.ON if self._device.is_on else switch.States.OFF
        self.update({switch.Attributes.STATE: state})

    async def _handle_command(
        self,
        entity: switch.Switch,
        cmd_id: str,
        params: dict[str, Any] | None,
    ) -> StatusCodes:
        _LOG.debug("[%s] Command: %s", self.id, cmd_id)
        if cmd_id == switch.Commands.ON:
            ok = await self._device.cmd_turn_on()
        elif cmd_id == switch.Commands.OFF:
            ok = await self._device.cmd_turn_off()
        elif cmd_id == switch.Commands.TOGGLE:
            ok = await self._device.cmd_toggle()
        else:
            return StatusCodes.NOT_IMPLEMENTED
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

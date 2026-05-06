"""Tapo light-effect Select entity.

Exposes the per-device built-in effect list (Aurora, Sunrise, Party, etc) as
a single dropdown including an OFF sentinel as element 0. Picking an option
calls the kasa LightEffect / LightStripEffect module's set_effect.

Critically: never call ucapi-framework's set_attributes / set_state /
set_current_option helpers — those mutate self.attributes before the
framework's update filter runs, the filter then sees nothing changed and
silently skips the wire push, and the dropdown never populates on the
Remote. This is documented in CLAUDE.md as the SelectEntity bug. Always
use ``self.update({...fresh dict...})`` instead.
"""

import logging
from typing import Any

from ucapi import select, StatusCodes
from ucapi_framework import SelectEntity

from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState
from uc_intg_tapo.device import TapoDevice

_LOG = logging.getLogger(__name__)


class TapoLightEffect(SelectEntity):
    def __init__(self, device_config: TapoDeviceConfig, device: TapoDevice) -> None:
        self._device = device
        self._options = list(device_config.effect_names or [])
        entity_id = f"select.tapo_{device_config.identifier}_effect"
        name = f"{device_config.name} Effect"

        super().__init__(
            entity_id,
            name,
            attributes={
                select.Attributes.STATE: select.States.UNAVAILABLE,
                select.Attributes.OPTIONS: self._options,
                select.Attributes.CURRENT_OPTION: "",
            },
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == DeviceState.UNAVAILABLE:
            self.update({select.Attributes.STATE: select.States.UNAVAILABLE})
            return
        current = self._device.current_effect or ""
        # Always pass a fresh dict — see module docstring for the framework
        # filter bug this works around.
        self.update({
            select.Attributes.STATE: select.States.ON,
            select.Attributes.OPTIONS: self._options,
            select.Attributes.CURRENT_OPTION: current,
        })

    async def _handle_command(
        self,
        entity: select.Select,
        cmd_id: str,
        params: dict[str, Any] | None,
    ) -> StatusCodes:
        if cmd_id != select.Commands.SELECT_OPTION:
            return StatusCodes.NOT_IMPLEMENTED
        option = (params or {}).get("option") or ""
        if option not in self._options:
            _LOG.warning(
                "[%s] Unknown effect option: %r (valid: %s)",
                self.id, option, self._options,
            )
            return StatusCodes.BAD_REQUEST
        ok = await self._device.cmd_set_effect(option)
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

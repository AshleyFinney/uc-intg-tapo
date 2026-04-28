"""Tapo device backed by python-kasa, polled via the framework's PollingDevice."""

import logging
from typing import Any

from ucapi_framework import DeviceEvents, PollingDevice

from uc_intg_tapo.client import TapoClient
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState, TAPO_POLL_INTERVAL

_LOG = logging.getLogger(__name__)


class TapoDevice(PollingDevice):
    def __init__(self, device_config: TapoDeviceConfig, **kwargs: Any) -> None:
        super().__init__(device_config, poll_interval=TAPO_POLL_INTERVAL, **kwargs)
        self._device_config = device_config
        self._client: TapoClient | None = None
        self._state: DeviceState = DeviceState.UNAVAILABLE

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str | None:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"{self.name} ({self.address})"

    @property
    def state(self) -> DeviceState:
        return self._state

    @property
    def is_on(self) -> bool:
        return self._state == DeviceState.ON

    async def establish_connection(self) -> None:
        if self.driver is None or self.driver.account is None:
            raise ConnectionError("No Tapo account credentials available, complete setup first")

        client = TapoClient(
            self._device_config.host,
            self.driver.account.username,
            self.driver.account.password,
        )
        if not await client.connect():
            raise ConnectionError(f"Cannot reach {self._device_config.host}")
        self._client = client
        self._state = DeviceState.ON if client.is_on else DeviceState.OFF
        self.events.emit(DeviceEvents.UPDATE, self.identifier)

    async def poll_device(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.update()
        except Exception as err:
            _LOG.warning("[%s] Poll failed: %s", self.log_id, err)
            return
        new_state = DeviceState.ON if self._client.is_on else DeviceState.OFF
        if new_state != self._state:
            self._state = new_state
            self.events.emit(DeviceEvents.UPDATE, self.identifier)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
        self._state = DeviceState.UNAVAILABLE
        await super().disconnect()

    async def cmd_turn_on(self) -> bool:
        if self._client is None:
            return False
        ok = await self._client.turn_on()
        if ok:
            self._state = DeviceState.ON
            self.events.emit(DeviceEvents.UPDATE, self.identifier)
        return ok

    async def cmd_turn_off(self) -> bool:
        if self._client is None:
            return False
        ok = await self._client.turn_off()
        if ok:
            self._state = DeviceState.OFF
            self.events.emit(DeviceEvents.UPDATE, self.identifier)
        return ok

    async def cmd_toggle(self) -> bool:
        return await (self.cmd_turn_off() if self.is_on else self.cmd_turn_on())

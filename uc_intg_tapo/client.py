"""Thin wrapper around python-kasa exposing only the operations the integration needs."""

import logging

from kasa import Credentials, Discover, SmartDevice

_LOG = logging.getLogger(__name__)


class TapoClient:
    def __init__(self, host: str, username: str, password: str) -> None:
        self._host = host
        self._creds = Credentials(username=username, password=password)
        self._device: SmartDevice | None = None

    async def connect(self) -> bool:
        try:
            self._device = await Discover.discover_single(
                host=self._host, credentials=self._creds
            )
            await self._device.update()
            return True
        except Exception as err:
            _LOG.warning("Failed to connect to %s: %s", self._host, err)
            self._device = None
            return False

    async def disconnect(self) -> None:
        if self._device is None:
            return
        try:
            await self._device.disconnect()
        except Exception as err:
            _LOG.debug("Disconnect of %s raised: %s", self._host, err)
        finally:
            self._device = None

    async def update(self) -> None:
        if self._device is None:
            raise ConnectionError("not connected")
        await self._device.update()

    @property
    def is_on(self) -> bool:
        return bool(self._device and self._device.is_on)

    @property
    def alias(self) -> str | None:
        return self._device.alias if self._device else None

    @property
    def model(self) -> str | None:
        return self._device.model if self._device else None

    @property
    def mac(self) -> str | None:
        return self._device.mac if self._device else None

    async def turn_on(self) -> bool:
        if self._device is None:
            return False
        try:
            await self._device.turn_on()
            return True
        except Exception as err:
            _LOG.warning("turn_on failed for %s: %s", self._host, err)
            return False

    async def turn_off(self) -> bool:
        if self._device is None:
            return False
        try:
            await self._device.turn_off()
            return True
        except Exception as err:
            _LOG.warning("turn_off failed for %s: %s", self._host, err)
            return False

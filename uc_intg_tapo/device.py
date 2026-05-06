"""Tapo device backed by python-kasa, polled via the framework's PollingDevice."""

import asyncio
import logging
from typing import Any

from kasa import Credentials, Discover
from kasa.interfaces.light import HSV
from ucapi_framework import DeviceEvents, PollingDevice

from uc_intg_tapo.client import TapoClient
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState, TAPO_DISCOVERY_TIMEOUT, TAPO_POLL_INTERVAL

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

    @property
    def brightness_percent(self) -> int | None:
        return self._client.brightness_percent if self._client else None

    @property
    def hsv(self) -> HSV | None:
        return self._client.hsv if self._client else None

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._client.color_temp_kelvin if self._client else None

    @property
    def current_effect(self) -> str | None:
        return self._client.current_effect if self._client else None

    @property
    def power_w(self) -> float | None:
        return self._client.power_w if self._client else None

    @property
    def energy_today_kwh(self) -> float | None:
        return self._client.energy_today_kwh if self._client else None

    @property
    def energy_this_month_kwh(self) -> float | None:
        return self._client.energy_this_month_kwh if self._client else None

    @property
    def voltage_v(self) -> float | None:
        return self._client.voltage_v if self._client else None

    @property
    def current_a(self) -> float | None:
        return self._client.current_a if self._client else None

    async def establish_connection(self) -> None:
        if self.driver is None or self.driver.account is None:
            raise ConnectionError("No Tapo account credentials available, complete setup first")

        username = self.driver.account.username
        password = self.driver.account.password

        client = TapoClient(self._device_config.host, username, password)
        if await client.connect():
            self._client = client
            self._state = DeviceState.ON if client.is_on else DeviceState.OFF
            self.events.emit(DeviceEvents.UPDATE)
            return

        # Direct probe failed. The device may still be online but reachable at a
        # different IP after a DHCP lease change. Broadcast-discover the network
        # and match by MAC (the config's identifier) before giving up.
        new_host = await self._rediscover_by_mac(Credentials(username=username, password=password))
        if new_host is None or new_host == self._device_config.host:
            raise ConnectionError(f"Cannot reach {self._device_config.host}")

        _LOG.info(
            "[%s] IP changed from %s to %s, updating config",
            self.log_id, self._device_config.host, new_host,
        )
        self.update_config(host=new_host)

        client = TapoClient(new_host, username, password)
        if not await client.connect():
            raise ConnectionError(f"Cannot reach {new_host} after rediscovery")
        self._client = client
        self._state = DeviceState.ON if client.is_on else DeviceState.OFF
        self.events.emit(DeviceEvents.UPDATE)

    async def _rediscover_by_mac(self, creds: Credentials) -> str | None:
        target_mac = self._device_config.identifier
        if not target_mac:
            return None
        try:
            found = await asyncio.wait_for(
                Discover.discover(credentials=creds, discovery_timeout=TAPO_DISCOVERY_TIMEOUT),
                timeout=TAPO_DISCOVERY_TIMEOUT + 5,
            )
        except Exception as err:
            _LOG.debug("[%s] Rediscovery scan failed: %s", self.log_id, err)
            return None

        try:
            for ip, dev in found.items():
                mac_normalized = (dev.mac or "").replace(":", "").replace("-", "").upper()
                if mac_normalized == target_mac:
                    return ip
            return None
        finally:
            # Close every probe session so its background poll loop doesn't
            # collide with the real session we open in establish_connection.
            # Same reason as setup_flow's _close_kasa_device helper.
            for dev in found.values():
                try:
                    await dev.disconnect()
                except Exception:
                    pass

    async def poll_device(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.update()
        except Exception as err:
            _LOG.warning("[%s] Poll failed: %s", self.log_id, err)
            return
        # Always emit on a successful poll so brightness/colour/colour-temp
        # changes propagate through to entity sync_state, not just on/off
        # changes. The framework's update filter will dedupe wire pushes when
        # nothing has actually changed.
        self._state = DeviceState.ON if self._client.is_on else DeviceState.OFF
        self.events.emit(DeviceEvents.UPDATE)

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
            self.events.emit(DeviceEvents.UPDATE)
        return ok

    async def cmd_turn_off(self) -> bool:
        if self._client is None:
            return False
        ok = await self._client.turn_off()
        if ok:
            self._state = DeviceState.OFF
            self.events.emit(DeviceEvents.UPDATE)
        return ok

    async def cmd_toggle(self) -> bool:
        return await (self.cmd_turn_off() if self.is_on else self.cmd_turn_on())

    async def cmd_set_effect(self, name: str) -> bool:
        """Apply a built-in light effect by name. Pass the OFF sentinel to stop."""
        if self._client is None:
            return False
        ok = await self._client.set_effect(name)
        if ok:
            self._state = DeviceState.ON
            try:
                # Refresh kasa's local cache so the entity's sync_state reads
                # the post-set effect value, same reasoning as cmd_set_light_state.
                await self._client.update()
            except Exception as err:
                _LOG.debug("[%s] Post-effect refresh failed: %s", self.log_id, err)
            self.events.emit(DeviceEvents.UPDATE)
        return ok

    async def cmd_set_light_state(
        self,
        *,
        brightness_percent: int | None = None,
        hue: int | None = None,
        saturation_percent: int | None = None,
        color_temp_kelvin: int | None = None,
    ) -> bool:
        """Apply brightness/HSV/colour-temp changes; the light is turned on as a side effect."""
        if self._client is None:
            return False
        ok = await self._client.set_light_state(
            brightness_percent=brightness_percent,
            hue=hue,
            saturation_percent=saturation_percent,
            color_temp_kelvin=color_temp_kelvin,
        )
        if ok:
            self._state = DeviceState.ON
            # Refresh python-kasa's local cache so the entity's sync_state
            # reads the post-set values, not the pre-set ones. Without this,
            # the slider on the Remote snaps back to the previous value as
            # soon as you release it because we report stale state.
            try:
                await self._client.update()
            except Exception as err:
                _LOG.debug("[%s] Post-set refresh failed: %s", self.log_id, err)
            self.events.emit(DeviceEvents.UPDATE)
        return ok

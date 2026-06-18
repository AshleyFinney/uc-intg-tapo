"""Thin wrapper around python-kasa exposing only the operations the integration needs."""

import logging

from kasa import Credentials, Discover, Module, SmartDevice
from kasa.interfaces.light import HSV, LightState

_LOG = logging.getLogger(__name__)


def _normalize_mac(mac: str | None) -> str:
    """Strip separators and upper-case a MAC. Matches the identifier scheme
    used at pairing time (setup_flow) and for config identifiers."""
    return (mac or "").replace(":", "").replace("-", "").upper()


class TapoClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        expected_mac: str | None = None,
    ) -> None:
        self._host = host
        self._creds = Credentials(username=username, password=password)
        self._device: SmartDevice | None = None
        # Normalised MAC we paired against (device_config.identifier). When set,
        # connect() verifies the device answering at _host actually has this MAC
        # and rejects it otherwise. None disables the check (e.g. ad-hoc probes).
        self._expected_mac = _normalize_mac(expected_mac) or None

    async def connect(self) -> bool:
        try:
            self._device = await Discover.discover_single(
                host=self._host, credentials=self._creds
            )
            await self._device.update()
        except Exception as err:
            _LOG.warning("Failed to connect to %s: %s", self._host, err)
            self._device = None
            return False

        # Verify identity. After a DHCP reshuffle a *different* Tapo device may
        # now hold the saved IP. Without this check we'd bind to whoever answers
        # and send commands to the wrong device (a plug action toggling a light
        # strip, etc). The MAC is the stable identity we paired against; reject a
        # mismatch so establish_connection falls through to MAC-based rediscovery
        # and re-pins the correct IP.
        if self._expected_mac is not None:
            actual = _normalize_mac(self.mac)
            if actual != self._expected_mac:
                _LOG.warning(
                    "Connected to %s but it is MAC %s, expected %s - not our "
                    "device, rejecting so rediscovery can re-pin by MAC",
                    self._host, actual or "<unknown>", self._expected_mac,
                )
                await self.disconnect()
                return False

        return True

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

    # ----- Light-specific access ----------------------------------------

    @property
    def _light(self):
        """Return the python-kasa Light module if the device has one, else None."""
        if self._device is None:
            return None
        return self._device.modules.get(Module.Light)

    @property
    def has_light(self) -> bool:
        return self._light is not None

    @property
    def has_brightness(self) -> bool:
        return self._device is not None and Module.Brightness in self._device.modules

    @property
    def has_color(self) -> bool:
        return self._device is not None and Module.Color in self._device.modules

    @property
    def has_color_temp(self) -> bool:
        return (
            self._device is not None
            and Module.ColorTemperature in self._device.modules
        )

    @property
    def color_temp_range(self) -> tuple[int, int] | None:
        """Return (min, max) Kelvin range, or None if not supported."""
        if self._device is None:
            return None
        ct_module = self._device.modules.get(Module.ColorTemperature)
        if ct_module is None:
            return None
        rng = ct_module.valid_temperature_range
        return (rng.min, rng.max)

    @property
    def brightness_percent(self) -> int | None:
        """Current brightness in 0..100 percent, or None if not supported / offline."""
        light = self._light
        if light is None or not self.has_brightness:
            return None
        try:
            return int(light.brightness)
        except Exception as err:
            _LOG.debug("Reading brightness failed for %s: %s", self._host, err)
            return None

    @property
    def hsv(self) -> HSV | None:
        """Current HSV (hue 0..360, saturation 0..100, value 0..100), or None."""
        light = self._light
        if light is None or not self.has_color:
            return None
        try:
            return light.hsv
        except Exception as err:
            _LOG.debug("Reading hsv failed for %s: %s", self._host, err)
            return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Current colour temperature in Kelvin, or None."""
        light = self._light
        if light is None or not self.has_color_temp:
            return None
        try:
            return int(light.color_temp)
        except Exception as err:
            _LOG.debug("Reading color_temp failed for %s: %s", self._host, err)
            return None

    # ----- Light-effect access (L920 strips, L530 bulbs etc.) ---------

    @property
    def _light_effect(self):
        """Return the python-kasa LightEffect module if present, else None."""
        if self._device is None:
            return None
        return self._device.modules.get(Module.LightEffect)

    @property
    def has_light_effect(self) -> bool:
        return self._light_effect is not None

    @property
    def effect_names(self) -> list[str]:
        """Effect names including the OFF sentinel as element 0."""
        eff = self._light_effect
        try:
            return list(eff.effect_list) if eff is not None else []
        except Exception as err:
            _LOG.debug("Reading effect_list failed for %s: %s", self._host, err)
            return []

    @property
    def current_effect(self) -> str | None:
        """Active effect name, or the OFF sentinel string when nothing's running."""
        eff = self._light_effect
        if eff is None:
            return None
        try:
            return eff.effect
        except Exception as err:
            _LOG.debug("Reading current effect failed for %s: %s", self._host, err)
            return None

    async def set_effect(self, name: str) -> bool:
        """Apply an effect by name. Pass the OFF sentinel string to stop the running effect."""
        eff = self._light_effect
        if eff is None:
            _LOG.warning("set_effect called on non-light-effect device %s", self._host)
            return False
        try:
            await eff.set_effect(name)
            return True
        except Exception as err:
            _LOG.warning("set_effect(%s) failed for %s: %s", name, self._host, err)
            return False

    # ----- Energy-specific access (P110 plugs, etc) ---------------------

    @property
    def _energy(self):
        """Return the python-kasa Energy module if present, else None."""
        if self._device is None:
            return None
        return self._device.modules.get(Module.Energy)

    @property
    def has_energy(self) -> bool:
        return self._energy is not None

    @property
    def power_w(self) -> float | None:
        """Current power draw in watts."""
        energy = self._energy
        if energy is None:
            return None
        try:
            return energy.current_consumption
        except Exception as err:
            _LOG.debug("Reading power for %s failed: %s", self._host, err)
            return None

    @property
    def energy_today_kwh(self) -> float | None:
        energy = self._energy
        if energy is None:
            return None
        try:
            return energy.consumption_today
        except Exception as err:
            _LOG.debug("Reading today's energy for %s failed: %s", self._host, err)
            return None

    @property
    def energy_this_month_kwh(self) -> float | None:
        energy = self._energy
        if energy is None:
            return None
        try:
            return energy.consumption_this_month
        except Exception as err:
            _LOG.debug("Reading month's energy for %s failed: %s", self._host, err)
            return None

    @property
    def voltage_v(self) -> float | None:
        energy = self._energy
        if energy is None:
            return None
        try:
            return energy.voltage
        except Exception as err:
            _LOG.debug("Reading voltage for %s failed: %s", self._host, err)
            return None

    @property
    def current_a(self) -> float | None:
        energy = self._energy
        if energy is None:
            return None
        try:
            return energy.current
        except Exception as err:
            _LOG.debug("Reading current for %s failed: %s", self._host, err)
            return None

    async def set_light_state(
        self,
        *,
        brightness_percent: int | None = None,
        hue: int | None = None,
        saturation_percent: int | None = None,
        color_temp_kelvin: int | None = None,
    ) -> bool:
        """Apply a partial light-state change, atomically turning the light on.

        Any None value is left untouched. Brightness and saturation are in
        python-kasa's percentage units, hue is in degrees, colour temperature
        is in Kelvin.
        """
        light = self._light
        if light is None:
            _LOG.warning("set_light_state called on non-light device %s", self._host)
            return False

        # Build a LightState; light_on=True ensures the light comes on if it
        # isn't already (matches ucapi's "on with brightness/colour params"
        # semantic). Pre-fill hue/saturation from current state when only one
        # of them is provided, since python-kasa's set_state requires both
        # fields together for HSV updates.
        state = LightState(light_on=True)

        if brightness_percent is not None:
            state.brightness = max(1, min(100, brightness_percent))

        hue_provided = hue is not None
        sat_provided = saturation_percent is not None
        if hue_provided or sat_provided:
            current = self.hsv
            new_hue = hue if hue_provided else (current.hue if current else 0)
            new_sat = (
                saturation_percent
                if sat_provided
                else (current.saturation if current else 100)
            )
            state.hue = max(0, min(360, new_hue))
            state.saturation = max(0, min(100, new_sat))
            # Tapo bulbs use color_temp=0 as the explicit "switch to colour
            # mode" signal. Without this, sending hue/saturation while the
            # bulb is in white mode is silently ignored. python-kasa's
            # set_hsv() includes this implicitly (see kasa/smart/modules/
            # color.py:91), but set_state() does not, so we have to do it.
            state.color_temp = 0

        if color_temp_kelvin is not None:
            rng = self.color_temp_range
            if rng is not None:
                state.color_temp = max(rng[0], min(rng[1], color_temp_kelvin))
            else:
                state.color_temp = color_temp_kelvin

        try:
            await light.set_state(state)
            return True
        except Exception as err:
            _LOG.warning("set_light_state failed for %s: %s", self._host, err)
            return False

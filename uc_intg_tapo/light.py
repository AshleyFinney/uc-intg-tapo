"""Tapo Light entity.

Phase 4: brightness, HSV colour, and colour temperature, capability-detected
per device at pairing time.

Unit conversions between ucapi and python-kasa:
- brightness:  ucapi 0..255  <->  kasa 0..100 percent
- hue:         ucapi 0..360 degrees == kasa 0..360 degrees, no scaling
- saturation:  ucapi 0..255  <->  kasa 0..100 percent
- colour_temp: ucapi 0..100 (% warm, 0=coldest, 100=warmest)
               <->  kasa Kelvin in the bulb-reported [min, max] range,
               where lower Kelvin == warmer
"""

import logging
from typing import Any

from ucapi import light, StatusCodes
from ucapi_framework import LightEntity

from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState
from uc_intg_tapo.device import TapoDevice

_LOG = logging.getLogger(__name__)


def _build_features(config: TapoDeviceConfig) -> list[light.Features]:
    features: list[light.Features] = [light.Features.ON_OFF, light.Features.TOGGLE]
    if config.has_brightness:
        features.append(light.Features.DIM)
    if config.has_color:
        features.append(light.Features.COLOR)
    if config.has_color_temp:
        features.append(light.Features.COLOR_TEMPERATURE)
    return features


def _initial_attributes(config: TapoDeviceConfig) -> dict[str, Any]:
    attrs: dict[str, Any] = {light.Attributes.STATE: light.States.UNAVAILABLE}
    if config.has_brightness:
        attrs[light.Attributes.BRIGHTNESS] = 0
    if config.has_color:
        attrs[light.Attributes.HUE] = 0
        attrs[light.Attributes.SATURATION] = 0
    if config.has_color_temp:
        attrs[light.Attributes.COLOR_TEMPERATURE] = 0
    return attrs


def _ucapi_to_kasa_brightness(value: int) -> int:
    """Map ucapi brightness (0..255) to kasa percent (1..100).

    kasa treats brightness=0 as 'turn off', so we clamp to a minimum of 1
    when the ucapi value is non-zero.
    """
    if value <= 0:
        return 1
    return max(1, min(100, round(value * 100 / 255)))


def _kasa_to_ucapi_brightness(percent: int) -> int:
    return max(0, min(255, round(percent * 255 / 100)))


def _ucapi_to_kasa_saturation(value: int) -> int:
    return max(0, min(100, round(value * 100 / 255)))


def _kasa_to_ucapi_saturation(percent: int) -> int:
    return max(0, min(255, round(percent * 255 / 100)))


def _ucapi_percent_to_kelvin(percent: int, min_k: int, max_k: int) -> int:
    """Map ucapi colour-temp percent (0=coldest, 100=warmest) to Kelvin.

    Lower Kelvin is warmer, so 0% maps to max_k and 100% maps to min_k.
    """
    if max_k <= min_k:
        return min_k or max_k
    pct = max(0, min(100, percent))
    return round(max_k - (pct / 100) * (max_k - min_k))


def _kelvin_to_ucapi_percent(kelvin: int, min_k: int, max_k: int) -> int:
    if max_k <= min_k:
        return 0
    pct = (max_k - kelvin) / (max_k - min_k) * 100
    return max(0, min(100, round(pct)))


class TapoLight(LightEntity):
    def __init__(self, device_config: TapoDeviceConfig, device: TapoDevice) -> None:
        self._device = device
        self._device_config = device_config
        entity_id = f"light.tapo_{device_config.identifier}"

        super().__init__(
            entity_id,
            device_config.name,
            features=_build_features(device_config),
            attributes=_initial_attributes(device_config),
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == DeviceState.UNAVAILABLE:
            self.update({light.Attributes.STATE: light.States.UNAVAILABLE})
            return

        new_attrs: dict[str, Any] = {
            light.Attributes.STATE: (
                light.States.ON if self._device.is_on else light.States.OFF
            )
        }

        if self._device_config.has_brightness:
            kasa_pct = self._device.brightness_percent
            if kasa_pct is not None:
                new_attrs[light.Attributes.BRIGHTNESS] = _kasa_to_ucapi_brightness(kasa_pct)

        if self._device_config.has_color:
            hsv = self._device.hsv
            if hsv is not None:
                new_attrs[light.Attributes.HUE] = max(0, min(360, int(hsv.hue)))
                new_attrs[light.Attributes.SATURATION] = _kasa_to_ucapi_saturation(
                    int(hsv.saturation)
                )

        if self._device_config.has_color_temp:
            kelvin = self._device.color_temp_kelvin
            if kelvin is not None:
                new_attrs[light.Attributes.COLOR_TEMPERATURE] = _kelvin_to_ucapi_percent(
                    kelvin,
                    self._device_config.color_temp_min_kelvin,
                    self._device_config.color_temp_max_kelvin,
                )

        self.update(new_attrs)

    async def _handle_command(
        self,
        entity: light.Light,
        cmd_id: str,
        params: dict[str, Any] | None,
    ) -> StatusCodes:
        _LOG.debug("[%s] Command: %s, params=%s", self.id, cmd_id, params)

        if cmd_id == light.Commands.OFF:
            ok = await self._device.cmd_turn_off()
            return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

        if cmd_id == light.Commands.TOGGLE:
            ok = await self._device.cmd_toggle()
            return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

        if cmd_id != light.Commands.ON:
            return StatusCodes.NOT_IMPLEMENTED

        # cmd_id == "on": with no params just turn on, otherwise apply the
        # brightness/colour/colour-temp changes (which also turns the light on
        # as a side effect of set_light_state).
        params = params or {}
        if not params:
            ok = await self._device.cmd_turn_on()
            return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

        kasa_brightness: int | None = None
        if "brightness" in params and self._device_config.has_brightness:
            kasa_brightness = _ucapi_to_kasa_brightness(int(params["brightness"]))

        hue: int | None = None
        kasa_saturation: int | None = None
        if self._device_config.has_color:
            if "hue" in params:
                hue = max(0, min(360, int(params["hue"])))
            if "saturation" in params:
                kasa_saturation = _ucapi_to_kasa_saturation(int(params["saturation"]))

        kasa_color_temp_k: int | None = None
        if "color_temperature" in params and self._device_config.has_color_temp:
            kasa_color_temp_k = _ucapi_percent_to_kelvin(
                int(params["color_temperature"]),
                self._device_config.color_temp_min_kelvin,
                self._device_config.color_temp_max_kelvin,
            )

        # If the user sent ON with params we don't support, fall back to a
        # plain turn_on rather than silently no-op. Avoids the light staying
        # off because we filtered everything out.
        if (
            kasa_brightness is None
            and hue is None
            and kasa_saturation is None
            and kasa_color_temp_k is None
        ):
            ok = await self._device.cmd_turn_on()
            return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

        _LOG.debug(
            "[%s] Sending to kasa: brightness=%s%% hue=%s saturation=%s%% color_temp=%sK",
            self.id, kasa_brightness, hue, kasa_saturation, kasa_color_temp_k,
        )
        ok = await self._device.cmd_set_light_state(
            brightness_percent=kasa_brightness,
            hue=hue,
            saturation_percent=kasa_saturation,
            color_temp_kelvin=kasa_color_temp_k,
        )
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

"""Tapo Energy sensor entity.

Phase 3: surfaces P110 emeter readings as ucapi Sensor entities. One Python
class handles all five energy-related sensor kinds, parameterised by a
KINDS table that maps each kind to its ucapi device class, unit, decimals,
and value-getter on TapoDevice.
"""

from dataclasses import dataclass
from typing import Any, Callable

from ucapi import sensor
from ucapi_framework import SensorEntity

from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import DeviceState
from uc_intg_tapo.device import TapoDevice


@dataclass(frozen=True)
class _SensorKind:
    suffix: str          # entity-id suffix and friendly-name suffix
    label: str           # human-readable name fragment
    device_class: sensor.DeviceClasses
    unit: str
    decimals: int
    value_getter: Callable[[TapoDevice], float | None]
    requires_voltage_current: bool = False


KINDS: dict[str, _SensorKind] = {
    "power": _SensorKind(
        suffix="power",
        label="power",
        device_class=sensor.DeviceClasses.POWER,
        unit="W",
        decimals=1,
        value_getter=lambda d: d.power_w,
    ),
    "energy_today": _SensorKind(
        suffix="energy_today",
        label="energy today",
        device_class=sensor.DeviceClasses.ENERGY,
        unit="kWh",
        decimals=3,
        value_getter=lambda d: d.energy_today_kwh,
    ),
    "energy_this_month": _SensorKind(
        suffix="energy_this_month",
        label="energy this month",
        device_class=sensor.DeviceClasses.ENERGY,
        unit="kWh",
        decimals=3,
        value_getter=lambda d: d.energy_this_month_kwh,
    ),
    "voltage": _SensorKind(
        suffix="voltage",
        label="voltage",
        device_class=sensor.DeviceClasses.VOLTAGE,
        unit="V",
        decimals=1,
        value_getter=lambda d: d.voltage_v,
        requires_voltage_current=True,
    ),
    "current": _SensorKind(
        suffix="current",
        label="current",
        device_class=sensor.DeviceClasses.CURRENT,
        unit="A",
        decimals=2,
        value_getter=lambda d: d.current_a,
        requires_voltage_current=True,
    ),
}


def kinds_for(device_config: TapoDeviceConfig) -> list[str]:
    """Return the energy-sensor kinds appropriate for this device's flags."""
    if not device_config.has_energy:
        return []
    out = ["power", "energy_today", "energy_this_month"]
    if device_config.has_voltage_current:
        out += ["voltage", "current"]
    return out


class TapoEnergySensor(SensorEntity):
    def __init__(
        self,
        kind: str,
        device_config: TapoDeviceConfig,
        device: TapoDevice,
    ) -> None:
        self._device = device
        self._device_config = device_config
        self._kind = KINDS[kind]

        entity_id = f"sensor.tapo_{device_config.identifier}_{self._kind.suffix}"
        name = f"{device_config.name} {self._kind.label}"

        super().__init__(
            entity_id,
            name,
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.UNAVAILABLE,
                sensor.Attributes.VALUE: 0,
                sensor.Attributes.UNIT: self._kind.unit,
            },
            device_class=self._kind.device_class,
            options={sensor.Options.DECIMALS: self._kind.decimals},
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if self._device.state == DeviceState.UNAVAILABLE:
            self.update({sensor.Attributes.STATE: sensor.States.UNAVAILABLE})
            return

        value = self._kind.value_getter(self._device)
        if value is None:
            # Reading hasn't come back yet (offline, or first poll pending).
            # Keep the existing value but mark UNKNOWN so the Remote shows
            # the sensor isn't currently providing data.
            self.update({sensor.Attributes.STATE: sensor.States.UNKNOWN})
            return

        self.update({
            sensor.Attributes.STATE: sensor.States.ON,
            sensor.Attributes.VALUE: value,
            sensor.Attributes.UNIT: self._kind.unit,
        })

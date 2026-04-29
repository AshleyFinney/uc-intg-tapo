"""Tapo device configuration dataclass."""

from dataclasses import dataclass


@dataclass
class TapoDeviceConfig:
    identifier: str
    name: str
    host: str
    mac: str
    model: str
    # python-kasa DeviceType enum value as string (e.g. "bulb", "plug",
    # "lightstrip"). Always lowercase, matches DeviceType.Bulb.value etc.
    # Default keeps existing on-disk configs from before this field existed
    # loadable, bulbs were the only supported type at the time.
    device_type: str = "bulb"
    # Capability flags, populated at pairing time from python-kasa's modules.
    # Sentinel default of None means "never probed"; the startup migration in
    # __init__.py (see capabilities.needs_migration) then re-probes the live
    # device and writes True/False back to the config. After migration these
    # only ever hold True/False/ints.
    has_brightness: bool | None = None
    has_color: bool | None = None
    has_color_temp: bool | None = None
    color_temp_min_kelvin: int | None = None
    color_temp_max_kelvin: int | None = None
    has_energy: bool | None = None
    has_voltage_current: bool | None = None

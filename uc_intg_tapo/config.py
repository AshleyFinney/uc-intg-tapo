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
    # Built-in dynamic light effects (LightEffect / LightStripEffect modules).
    # None means "never probed", triggers migration on next startup.
    has_light_effect: bool | None = None
    # Cached effect name list as python-kasa exposes it: ['Off', 'Aurora', ...]
    # for strips; ['Off', 'Party', 'Relax'] for L530-style bulbs. Element 0 is
    # the OFF sentinel; the remainder are the named effects users get buttons
    # for. Stored at pairing-time so the entity factory can emit one Button per
    # named effect without needing the kasa device live at registration time.
    effect_names: list[str] | None = None

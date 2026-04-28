"""Tapo device configuration dataclass."""

from dataclasses import dataclass


@dataclass
class TapoDeviceConfig:
    identifier: str
    name: str
    host: str
    mac: str
    model: str
    # python-kasa DeviceType enum value as string (e.g. "Bulb", "Plug",
    # "LightStrip"). Default keeps existing on-disk configs from before this
    # field existed loadable, "Bulb" was the only supported type at the time.
    device_type: str = "Bulb"

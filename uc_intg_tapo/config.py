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

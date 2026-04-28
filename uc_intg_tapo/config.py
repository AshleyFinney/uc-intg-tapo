"""Tapo device configuration dataclass."""

from dataclasses import dataclass


@dataclass
class TapoDeviceConfig:
    identifier: str
    name: str
    host: str
    mac: str
    model: str
    username: str
    password: str

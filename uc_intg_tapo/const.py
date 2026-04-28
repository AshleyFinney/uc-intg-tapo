"""Constants for the Tapo integration."""

from enum import StrEnum


class DeviceState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    ON = "ON"
    OFF = "OFF"


TAPO_POLL_INTERVAL = 30
TAPO_DISCOVERY_TIMEOUT = 5
TAPO_CONNECT_RETRIES = 3
TAPO_CONNECT_RETRY_DELAY = 2

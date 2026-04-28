"""Setup flow: capture TP-Link credentials and a device IP, validate, persist."""

import asyncio
import logging
from typing import Any

from kasa import Credentials, Discover
from ucapi.api_definitions import RequestUserInput
from ucapi_framework import BaseSetupFlow

from uc_intg_tapo.config import TapoDeviceConfig

_LOG = logging.getLogger(__name__)


class TapoSetupFlow(BaseSetupFlow[TapoDeviceConfig]):
    """Phase 1 manual setup. One device per setup run, captured by IP."""

    def get_manual_entry_form(self) -> RequestUserInput:
        return RequestUserInput(
            {"en": "Tapo Device Setup"},
            [
                {
                    "id": "username",
                    "label": {"en": "TP-Link account email"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "password",
                    "label": {"en": "TP-Link account password"},
                    "field": {"password": {"value": ""}},
                },
                {
                    "id": "host",
                    "label": {"en": "Device IP address"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "name",
                    "label": {"en": "Friendly name (optional, defaults to device alias)"},
                    "field": {"text": {"value": ""}},
                },
            ],
        )

    async def query_device(self, input_values: dict[str, Any]) -> TapoDeviceConfig:
        username = (input_values.get("username") or "").strip()
        password = (input_values.get("password") or "").strip()
        host = (input_values.get("host") or "").strip()
        name_override = (input_values.get("name") or "").strip()

        if not username or not password or not host:
            raise ValueError("Email, password and IP address are all required.")

        creds = Credentials(username=username, password=password)
        try:
            dev = await asyncio.wait_for(
                Discover.discover_single(host=host, credentials=creds),
                timeout=10.0,
            )
            await dev.update()
        except asyncio.TimeoutError as err:
            raise ValueError(f"Connection to {host} timed out.") from err
        except Exception as err:
            raise ValueError(f"Failed to connect to {host}: {err}") from err

        mac_normalized = (dev.mac or "").replace(":", "").replace("-", "").upper()
        if not mac_normalized:
            mac_normalized = host.replace(".", "_")

        name = name_override or dev.alias or f"Tapo {dev.model}"

        return TapoDeviceConfig(
            identifier=mac_normalized,
            name=name,
            host=host,
            mac=dev.mac or "",
            model=dev.model or "",
            username=username,
            password=password,
        )

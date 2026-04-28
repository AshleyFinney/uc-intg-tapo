"""Setup flow.

Credentials live at integration level (one TP-Link account per integration), so
the pre-discovery screen only appears the first time. Subsequent runs (adding
more devices) reuse the stored account silently.

Discovery scans the LAN with the stored credentials via python-kasa, filters to
light-shaped devices (Phase 1: bulbs and light strips only), and presents them
to the user. Picking one runs query_device, which validates the connection and
persists a config keyed by MAC address. Manual entry stays as a fallback when
discovery finds nothing.
"""

import asyncio
import logging
from typing import Any

from kasa import Credentials, DeviceType, Discover
from ucapi.api_definitions import RequestUserInput
from ucapi_framework import BaseSetupFlow, DiscoveredDevice

from uc_intg_tapo.account import TapoAccount, save_account
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import TAPO_DISCOVERY_TIMEOUT

_LOG = logging.getLogger(__name__)

# Phase 1 supports lights only. Plugs (P100/P110), hubs (H100), and the like
# are filtered out of discovery so users can't add them and have them silently
# fail. Widen this set as more entity types land.
_SUPPORTED_DEVICE_TYPES = {DeviceType.Bulb, DeviceType.LightStrip}


class TapoSetupFlow(BaseSetupFlow[TapoDeviceConfig]):
    async def get_pre_discovery_screen(self) -> RequestUserInput | None:
        if self.driver.account is not None:
            _LOG.debug("Account already configured, skipping pre-discovery screen")
            return None

        return RequestUserInput(
            {"en": "TP-Link account"},
            [
                {
                    "id": "info",
                    "label": {"en": ""},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Enter the email and password of the TP-Link "
                                    "account your Tapo devices are linked to. "
                                    "These are needed both to discover devices "
                                    "on your network and to control them."
                                )
                            }
                        }
                    },
                },
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
            ],
        )

    def _get_active_credentials(self) -> tuple[str, str]:
        """Return (username, password) from the saved account if present, else from the just-entered pre-discovery data."""
        if self.driver.account is not None:
            return self.driver.account.username, self.driver.account.password
        return (
            (self._pre_discovery_data.get("username") or "").strip(),
            (self._pre_discovery_data.get("password") or "").strip(),
        )

    async def discover_devices(self) -> list[DiscoveredDevice]:
        username, password = self._get_active_credentials()
        if not username or not password:
            _LOG.warning("Missing credentials on discovery, skipping scan")
            return []

        creds = Credentials(username=username, password=password)
        try:
            found = await asyncio.wait_for(
                Discover.discover(credentials=creds, discovery_timeout=TAPO_DISCOVERY_TIMEOUT),
                timeout=TAPO_DISCOVERY_TIMEOUT + 5,
            )
        except asyncio.TimeoutError:
            _LOG.warning("Discovery timed out")
            return []
        except Exception as err:
            _LOG.warning("Discovery failed: %s", err)
            return []

        results: list[DiscoveredDevice] = []
        for ip, dev in found.items():
            try:
                await dev.update()
            except Exception as err:
                _LOG.debug("Skipping %s, update failed: %s", ip, err)
                continue

            if dev.device_type not in _SUPPORTED_DEVICE_TYPES:
                continue

            mac_normalized = (dev.mac or "").replace(":", "").replace("-", "").upper()
            if not mac_normalized:
                _LOG.debug("Skipping %s, no MAC available", ip)
                continue

            label = dev.alias or f"Tapo {dev.model}"
            results.append(
                DiscoveredDevice(
                    identifier=mac_normalized,
                    name=label,
                    address=ip,
                    extra_data={
                        "model": dev.model or "",
                        "mac": dev.mac or "",
                    },
                )
            )

        _LOG.info("Discovery found %d supported device(s)", len(results))
        # Default discover_devices() in the framework writes the list back to
        # self.discovery._discovered_devices so later get_discovered_devices(id)
        # lookups can resolve user picks. Our override has to do the same or
        # picking from the list silently falls through to manual entry.
        if self.discovery is not None:
            self.discovery._discovered_devices = results
        return results

    def format_discovered_device_label(self, device: DiscoveredDevice) -> str:
        model = (device.extra_data or {}).get("model") or "Tapo"
        return f"{device.name} ({model} at {device.address})"

    async def prepare_input_from_discovery(
        self,
        discovered: DiscoveredDevice,
        additional_input: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "host": discovered.address,
            "name": discovered.name,
        }

    def get_manual_entry_form(self) -> RequestUserInput:
        return RequestUserInput(
            {"en": "Add Tapo device manually"},
            [
                {
                    "id": "info",
                    "label": {"en": ""},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "If discovery missed the device, enter its IP "
                                    "address here. The credentials you supplied on "
                                    "the previous screen will be reused."
                                )
                            }
                        }
                    },
                },
                {
                    "id": "host",
                    "label": {"en": "Device IP address"},
                    "field": {"text": {"value": ""}},
                },
                {
                    "id": "name",
                    "label": {"en": "Friendly name (optional)"},
                    "field": {"text": {"value": ""}},
                },
            ],
        )

    async def query_device(self, input_values: dict[str, Any]) -> TapoDeviceConfig:
        username, password = self._get_active_credentials()
        host = (input_values.get("host") or "").strip()
        name_override = (input_values.get("name") or "").strip()

        if not username or not password:
            raise ValueError("Missing TP-Link credentials, restart setup.")
        if not host:
            raise ValueError("IP address is required.")

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

        # First successful connection proves the credentials. Persist them as
        # the integration-level account so future setup runs skip the prompt.
        if self.driver.account is None and self.driver.account_dir:
            account = TapoAccount(username=username, password=password)
            save_account(self.driver.account_dir, account)
            self.driver.account = account

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
        )

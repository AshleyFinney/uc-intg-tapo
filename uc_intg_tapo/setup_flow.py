"""Setup flow.

Credentials live at integration level (one TP-Link account per integration), so
the pre-discovery screen only appears the first time. Subsequent runs (adding
more devices) reuse the stored account silently.

Discovery scans the LAN with the stored credentials via python-kasa, filters to
supported device types and to devices not already configured, and presents the
remainder as a multi-checkbox screen so the user can pair several at once.
Submitting the screen with no boxes ticked drops to manual entry (a single-IP
form). Each picked device runs query_device to validate the connection and
build a config keyed by MAC address; failures during the batch are logged but
don't abort the rest.
"""

import asyncio
import logging
from typing import Any

from kasa import Credentials, DeviceType, Discover
from ucapi.api_definitions import (
    IntegrationSetupError,
    RequestUserInput,
    SetupComplete,
    SetupError,
)
from ucapi_framework import BaseSetupFlow, DiscoveredDevice, SetupSteps

from uc_intg_tapo.account import TapoAccount, save_account
from uc_intg_tapo.capabilities import detect_capabilities
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.const import TAPO_DISCOVERY_TIMEOUT

_LOG = logging.getLogger(__name__)

# Phase 2 supports lights and plugs. Hubs (H100) and the like are still
# filtered out so users can't add them and have them silently fail. Widen
# this set as more entity types land.
_SUPPORTED_DEVICE_TYPES = {
    DeviceType.Bulb,
    DeviceType.LightStrip,
    DeviceType.Plug,
}


async def _close_kasa_device(dev) -> None:
    """Best-effort tear-down of a kasa device's underlying transport.

    Without this the kasa device's background tasks and aiohttp session leak,
    asyncio later complains about ``Unclosed client session`` and the leaked
    session keeps polling its target generating 403 errors against our active
    session for the same host. Always wrap the close so we never raise out of
    cleanup.
    """
    try:
        await dev.disconnect()
    except Exception:
        pass


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
            finally:
                # Discovery returns kasa devices with live aiohttp sessions
                # we need to close, otherwise their background poll tasks keep
                # running and step on the real (post-pairing) connection's
                # session token, producing kasa 403 errors against our active
                # session.
                await _close_kasa_device(dev)

        # Filter out devices that are already configured so the multi-pick
        # screen only offers things the user can actually add. Devices in
        # self.config are already paired; re-pairing them isn't useful here
        # and would just pad the list. The framework's _finalize_device_setup
        # would also reject duplicates downstream.
        already_paired = {r.identifier for r in results if self.config.contains(r.identifier)}
        if already_paired:
            _LOG.debug(
                "Filtering %d already-paired device(s) from discovery: %s",
                len(already_paired), sorted(already_paired),
            )
        results = [r for r in results if r.identifier not in already_paired]

        _LOG.info("Discovery found %d device(s) available to add", len(results))
        # Default discover_devices() in the framework writes the list back to
        # self.discovery._discovered_devices so later get_discovered_devices(id)
        # lookups can resolve user picks. Our override has to do the same or
        # picking from the list silently falls through to manual entry.
        if self.discovery is not None:
            self.discovery._discovered_devices = results
        return results

    async def get_discovered_devices_screen(
        self, devices: list[DiscoveredDevice]
    ) -> RequestUserInput:
        """Multi-checkbox picker for discovered devices.

        Each device is its own checkbox so the user can pick any subset in
        a single screen. The framework's default screen uses a single-pick
        dropdown which means re-running setup once per device, painful when
        seeding a new install with many Tapo devices.

        No "choice" field is included; our override of
        ``_handle_user_data_response`` detects the multi-checkbox shape and
        routes to ``_handle_multi_pick``. Submitting with no boxes ticked
        falls through to manual entry, communicated in the screen text.
        """
        fields: list[dict[str, Any]] = [
            {
                "id": "info",
                "label": {"en": ""},
                "field": {
                    "label": {
                        "value": {
                            "en": (
                                "Tick the devices you want to add. To add a "
                                "device by IP address manually instead, submit "
                                "this screen with all boxes unticked."
                            )
                        }
                    }
                },
            }
        ]
        for device in devices:
            fields.append(
                {
                    "id": device.identifier,
                    "label": {"en": self.format_discovered_device_label(device)},
                    "field": {"checkbox": {"value": False}},
                }
            )
        return RequestUserInput({"en": "Discovered Devices"}, fields)

    async def _handle_user_data_response(self, msg):
        """Intercept multi-checkbox responses from our discovery screen.

        The framework's dispatcher routes DISCOVER-step responses to
        ``_handle_device_selection`` only when ``"choice"`` is in the
        input. Our screen omits ``choice`` and uses one checkbox per
        device, so without this override the dispatcher would fall
        through and error. Detect the multi-checkbox shape and route to
        our handler before delegating to super() for everything else.
        """
        if (
            self._setup_step == SetupSteps.DISCOVER
            and "choice" not in msg.input_values
            and self._pending_device_config is None
        ):
            return await self._handle_multi_pick(msg)
        return await super()._handle_user_data_response(msg)

    async def _handle_multi_pick(self, msg):
        """Pair every device the user ticked on the multi-pick screen.

        Empty selection routes to manual entry (per the screen's hint).
        Otherwise we loop through the picked devices, run query_device
        on each, save the resulting config. Failures are logged but
        don't abort the batch; we return SetupComplete if at least one
        device was added.
        """
        discovered_list = (
            self.discovery._discovered_devices if self.discovery is not None else []
        )

        # Checkbox values come back as strings on the wire ("true" / "false"),
        # not Python booleans. ucapi-framework reads them with the same
        # str(...).strip().lower() == "true" pattern (see ucapi_framework/
        # setup.py:1360). A naive truthy check on the raw value would treat
        # the literal string "false" as truthy and pick every device.
        def _ticked(identifier: str) -> bool:
            return str(msg.input_values.get(identifier, False)).strip().lower() == "true"

        _LOG.info(
            "Multi-pick: handler entered with %d cached discovered, %d input keys",
            len(discovered_list), len(msg.input_values),
        )
        picks = [d for d in discovered_list if _ticked(d.identifier)]
        _LOG.info(
            "Multi-pick: %d device(s) ticked: %s",
            len(picks), [p.identifier for p in picks],
        )

        if not picks:
            _LOG.info("Multi-pick: no devices ticked, dropping to manual entry")
            return await self._handle_manual_entry()

        _LOG.info("Multi-pick: pairing %d device(s)", len(picks))
        succeeded: list[str] = []
        failed: list[str] = []
        for device in picks:
            try:
                input_values = await self.prepare_input_from_discovery(
                    device, msg.input_values
                )
                result = await self.query_device(input_values)
                if isinstance(result, (SetupError, RequestUserInput)):
                    _LOG.warning(
                        "Multi-pick: %s yielded a non-config result, skipping",
                        device.identifier,
                    )
                    failed.append(device.identifier)
                    continue
                self.config.add_or_update(result)
                succeeded.append(device.identifier)
            except Exception as err:
                _LOG.warning(
                    "Multi-pick: failed to pair %s (%s): %s",
                    device.identifier, device.address, err,
                )
                failed.append(device.identifier)

        if failed:
            _LOG.info(
                "Multi-pick complete: %d added, %d failed (%s)",
                len(succeeded), len(failed), failed,
            )
        else:
            _LOG.info("Multi-pick complete: %d added", len(succeeded))

        if not succeeded:
            return SetupError(error_type=IntegrationSetupError.NOT_FOUND)
        return SetupComplete()

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

        try:
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

            device_type = dev.device_type.value if dev.device_type else "Unknown"

            # Capability detection lives in capabilities.detect_capabilities so
            # both pairing (here) and startup migration use the same probe. Plugs
            # / switches return False for the light-shaped flags, which is fine:
            # TapoSwitch ignores them. The Light/Sensor entities check the flags
            # they care about.
            caps = detect_capabilities(dev)

            return TapoDeviceConfig(
                identifier=mac_normalized,
                name=name,
                host=host,
                mac=dev.mac or "",
                model=dev.model or "",
                device_type=device_type,
                **caps,
            )
        finally:
            # Close the probe session so its background tasks don't linger
            # and step on the real polling connection that establish_connection
            # opens shortly after pairing.
            await _close_kasa_device(dev)

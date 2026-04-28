"""Tapo Integration Driver."""

import logging

from kasa import DeviceType
from ucapi_framework import BaseIntegrationDriver, Entity

from uc_intg_tapo.account import TapoAccount
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.device import TapoDevice
from uc_intg_tapo.light import TapoLight
from uc_intg_tapo.switch import TapoSwitch

_LOG = logging.getLogger(__name__)

_LIGHT_TYPES = {DeviceType.Bulb.value, DeviceType.LightStrip.value}
_SWITCH_TYPES = {DeviceType.Plug.value}


def _entity_factory(
    device_config: TapoDeviceConfig, device: TapoDevice
) -> list[Entity]:
    """Pick the right ucapi entity type for the device's python-kasa DeviceType.

    Light-shaped devices (bulbs, strips) become Light entities; plugs become
    Switch entities. Anything else returns no entities, which surfaces as the
    device being added but exposing no controls. The supported-type filter in
    the setup flow should keep us from reaching that branch in normal use.
    """
    dt = device_config.device_type
    if dt in _LIGHT_TYPES:
        return [TapoLight(device_config, device)]
    if dt in _SWITCH_TYPES:
        return [TapoSwitch(device_config, device)]
    _LOG.warning(
        "[%s] No entity type handles device_type=%r, device will have no controls",
        device_config.identifier,
        dt,
    )
    return []


class TapoDriver(BaseIntegrationDriver[TapoDevice, TapoDeviceConfig]):
    def __init__(self) -> None:
        super().__init__(
            device_class=TapoDevice,
            entity_classes=[_entity_factory],
            driver_id="uc_intg_tapo",
            require_connection_before_registry=False,
        )
        self.account: TapoAccount | None = None
        self.account_dir: str | None = None

    def device_from_entity_id(self, entity_id: str) -> str | None:
        """Strip the entity-type prefix and our own ``tapo_`` prefix to recover the device identifier.

        Our entity IDs are shaped ``light.tapo_<MAC>`` or ``switch.tapo_<MAC>``,
        but the device config identifier is just ``<MAC>``. Without this
        override the framework's default split-on-dot would hand back
        ``tapo_<MAC>`` and the device-config lookup would miss, logging a
        spurious "no device config found" warning on every entity subscribe.
        """
        if not entity_id or "." not in entity_id:
            return None
        parts = entity_id.split(".", 2)
        if len(parts) < 2:
            return None
        return parts[1].removeprefix("tapo_")

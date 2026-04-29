"""Tapo Integration Driver."""

import logging

from kasa import DeviceType
from ucapi_framework import BaseIntegrationDriver, Entity

from uc_intg_tapo.account import TapoAccount
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.device import TapoDevice
from uc_intg_tapo.light import TapoLight
from uc_intg_tapo.sensor import TapoEnergySensor, kinds_for as energy_sensor_kinds
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
    dt = (device_config.device_type or "").lower()
    entities: list[Entity] = []
    if dt in _LIGHT_TYPES:
        entities.append(TapoLight(device_config, device))
    elif dt in _SWITCH_TYPES:
        entities.append(TapoSwitch(device_config, device))
    else:
        _LOG.warning(
            "[%s] No entity type handles device_type=%r, device will have no controls",
            device_config.identifier,
            dt,
        )
        return []

    # Energy sensors apply to any device that exposes the python-kasa Energy
    # module. In practice that's P110 plugs today, but we don't gate on
    # device_type so we'd pick up future emeter-capable devices for free.
    for kind in energy_sensor_kinds(device_config):
        entities.append(TapoEnergySensor(kind, device_config, device))

    return entities


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
        """Strip the entity-type prefix, our ``tapo_`` prefix, and any
        sensor-kind suffix to recover the device identifier.

        Entity ID shapes:
          - ``light.tapo_<MAC>``                  (12-char MAC)
          - ``switch.tapo_<MAC>``                 (12-char MAC)
          - ``sensor.tapo_<MAC>_<kind>``          (kind = power, voltage, etc)

        The device config identifier is just ``<MAC>``. The MAC is always
        a fixed 12-character upper-case hex string, so we slice on that.
        """
        if not entity_id or "." not in entity_id:
            return None
        parts = entity_id.split(".", 2)
        if len(parts) < 2:
            return None
        after_prefix = parts[1].removeprefix("tapo_")
        # Sensor IDs append "_<kind>" after the MAC; lights/switches don't.
        # MAC is always 12 chars, so trim there if there's a "_" boundary.
        if len(after_prefix) > 12 and after_prefix[12] == "_":
            return after_prefix[:12]
        return after_prefix

"""Capability detection from a live python-kasa device.

Single source of truth for what flags we read off a kasa device. Used both
at pairing (in setup_flow) and at startup migration (in __init__) so the
canonical set lives in one place.
"""

from typing import Any

from kasa import Module
from kasa.interfaces.energy import Energy as EnergyInterface


_CAPABILITY_FIELDS = (
    "has_brightness",
    "has_color",
    "has_color_temp",
    "color_temp_min_kelvin",
    "color_temp_max_kelvin",
    "has_energy",
    "has_voltage_current",
    "has_light_effect",
    "effect_names",
)


def detect_capabilities(kasa_dev: Any) -> dict[str, Any]:
    """Return the canonical capability dict for a connected kasa device.

    The device must already have had ``await dev.update()`` called so its
    module list is populated.
    """
    caps: dict[str, Any] = {
        "has_brightness": Module.Brightness in kasa_dev.modules,
        "has_color": Module.Color in kasa_dev.modules,
        "has_color_temp": Module.ColorTemperature in kasa_dev.modules,
        "color_temp_min_kelvin": 0,
        "color_temp_max_kelvin": 0,
        "has_energy": Module.Energy in kasa_dev.modules,
        "has_voltage_current": False,
        "has_light_effect": Module.LightEffect in kasa_dev.modules,
        "effect_names": [],
    }

    if caps["has_color_temp"]:
        try:
            rng = kasa_dev.modules[Module.ColorTemperature].valid_temperature_range
            caps["color_temp_min_kelvin"] = int(rng.min)
            caps["color_temp_max_kelvin"] = int(rng.max)
        except Exception:
            # Bulb claimed colour-temp support but range is unreadable.
            # Treat as not supported rather than wire up a slider with
            # bogus min/max.
            caps["has_color_temp"] = False

    if caps["has_energy"]:
        energy = kasa_dev.modules[Module.Energy]
        caps["has_voltage_current"] = energy.supports(
            EnergyInterface.ModuleFeature.VOLTAGE_CURRENT
        )

    if caps["has_light_effect"]:
        # python-kasa's LightEffect (bulbs) and LightStripEffect (strips) both
        # register as Module.LightEffect with a common interface. effect_list
        # is a list of names with the OFF sentinel as element 0; remaining
        # entries are the named effects (Aurora, Sunrise, Party, Relax, etc).
        try:
            light_effect = kasa_dev.modules[Module.LightEffect]
            caps["effect_names"] = list(light_effect.effect_list)
        except Exception:
            # Module present but list is unreadable — treat as not supported
            # rather than wire up an empty Select / no Buttons.
            caps["has_light_effect"] = False
            caps["effect_names"] = []

    return caps


def needs_migration(config: Any) -> bool:
    """True if any capability field is still at its sentinel (None) default.

    Used to decide which devices to re-probe at startup. Newly paired devices
    have explicit True/False/int values from setup_flow.query_device, so they
    don't trigger migration. Devices paired before a capability field existed
    load with that field as None.
    """
    return any(getattr(config, name, None) is None for name in _CAPABILITY_FIELDS)

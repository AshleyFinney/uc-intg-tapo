"""Tapo integration for Unfolded Circle Remote 2/3."""

import asyncio
import json
import logging
import os
from pathlib import Path

from kasa import Credentials, Discover
from ucapi import DeviceStates
from ucapi_framework import BaseConfigManager, get_config_path

from uc_intg_tapo.account import load_account
from uc_intg_tapo.capabilities import detect_capabilities, needs_migration
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.discovery import TapoDiscovery
from uc_intg_tapo.driver import TapoDriver
from uc_intg_tapo.logging_filter import install as install_credential_scrubber
from uc_intg_tapo.setup_flow import TapoSetupFlow

try:
    _driver_path = Path(__file__).parent.parent / "driver.json"
    with open(_driver_path, "r", encoding="utf-8") as _f:
        __version__ = json.load(_f).get("version", "0.0.0")
except (FileNotFoundError, json.JSONDecodeError):
    __version__ = "0.0.0"

_LOG = logging.getLogger(__name__)


async def _migrate_one_device(cfg: TapoDeviceConfig, creds) -> tuple[TapoDeviceConfig, bool]:
    """Probe a single device, apply any updated capability flags to cfg.

    Returns (cfg, changed) where changed is True if the probe succeeded and
    we should persist the cfg via config_manager.update(). Time-boxed at 10s
    so an offline device can't stall startup.
    """
    try:
        dev = await asyncio.wait_for(
            Discover.discover_single(host=cfg.host, credentials=creds),
            timeout=10.0,
        )
        await dev.update()
    except Exception as err:
        _LOG.warning(
            "Capability migration probe failed for %s (%s): %s; "
            "will retry next startup",
            cfg.identifier, cfg.host, err,
        )
        return cfg, False

    try:
        caps = detect_capabilities(dev)
        for key, value in caps.items():
            setattr(cfg, key, value)
        return cfg, True
    finally:
        try:
            await dev.disconnect()
        except Exception:
            pass


async def _migrate_device_configs(config_manager: BaseConfigManager, account) -> None:
    """Probe live devices and fill in capability fields for any config that has
    sentinel (None) values left over from before those fields existed.

    Probes run in parallel to keep startup time bounded by a single device's
    timeout, not the total. If a probe fails the config is left as-is; the
    migration retries on the next startup.
    """
    if account is None:
        return

    creds = Credentials(username=account.username, password=account.password)
    pending = [c for c in config_manager.all() if needs_migration(c)]
    if not pending:
        return

    _LOG.info("Migrating capability flags for %d device(s)", len(pending))
    results = await asyncio.gather(
        *(_migrate_one_device(cfg, creds) for cfg in pending),
        return_exceptions=False,
    )
    for cfg, changed in results:
        if not changed:
            continue
        config_manager.update(cfg)
        _LOG.info(
            "Migrated %s (%s): has_brightness=%s has_color=%s "
            "has_color_temp=%s has_energy=%s has_voltage_current=%s",
            cfg.identifier, cfg.host,
            cfg.has_brightness, cfg.has_color, cfg.has_color_temp,
            cfg.has_energy, cfg.has_voltage_current,
        )


async def main() -> None:
    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        force=True,
    )
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
    # ucapi's api/entity/entities loggers emit DEBUG for every WebSocket
    # frame and entity update, which buries the integration's own logs.
    # Clamp to INFO unless UC_LOG_LEVEL_FRAMEWORK is set to override
    # (useful when debugging a ucapi-side issue).
    framework_level = os.getenv("UC_LOG_LEVEL_FRAMEWORK", "INFO").upper()
    framework_level_int = getattr(logging, framework_level, logging.INFO)
    for name in ("ucapi.api", "ucapi.entities", "ucapi.entity"):
        logging.getLogger(name).setLevel(framework_level_int)
    install_credential_scrubber()

    _LOG.info("Starting Tapo Integration v%s", __version__)

    driver = TapoDriver()

    config_path = get_config_path(driver.api.config_dir_path or "")
    config_manager = BaseConfigManager(
        config_path,
        add_handler=driver.on_device_added,
        remove_handler=driver.on_device_removed,
        config_class=TapoDeviceConfig,
    )
    driver.config_manager = config_manager

    driver.account_dir = config_path
    driver.account = load_account(config_path)
    if driver.account:
        _LOG.info("Loaded existing Tapo account from %s", config_path)

    setup_handler = TapoSetupFlow.create_handler(driver, discovery=TapoDiscovery())

    driver_json_path = os.path.join(os.path.dirname(__file__), "..", "driver.json")
    await driver.api.init(os.path.abspath(driver_json_path), setup_handler)

    # Migrate any device configs that predate the current capability schema.
    # Done before register_all_device_instances so entity factories see the
    # post-migration flags and register the right Light / Sensor entities.
    await _migrate_device_configs(config_manager, driver.account)

    await driver.register_all_device_instances(connect=False)

    device_count = len(list(config_manager.all()))
    await driver.api.set_device_state(
        DeviceStates.CONNECTED if device_count > 0 else DeviceStates.DISCONNECTED
    )

    _LOG.info("Tapo Integration started, %d device(s) configured", device_count)
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

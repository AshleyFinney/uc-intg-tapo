"""Tapo Integration Driver."""

import logging

from ucapi_framework import BaseIntegrationDriver

from uc_intg_tapo.account import TapoAccount
from uc_intg_tapo.config import TapoDeviceConfig
from uc_intg_tapo.device import TapoDevice
from uc_intg_tapo.light import TapoLight

_LOG = logging.getLogger(__name__)


class TapoDriver(BaseIntegrationDriver[TapoDevice, TapoDeviceConfig]):
    def __init__(self) -> None:
        super().__init__(
            device_class=TapoDevice,
            entity_classes=[TapoLight],
            driver_id="uc_intg_tapo",
            require_connection_before_registry=False,
        )
        self.account: TapoAccount | None = None
        self.account_dir: str | None = None

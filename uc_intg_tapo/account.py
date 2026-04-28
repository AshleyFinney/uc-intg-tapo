"""TP-Link account credentials, persisted at integration level.

Tapo devices all live under one TP-Link cloud account, so storing the credentials
once at the integration level (this file) rather than once per device keeps the
setup flow leaner and avoids prompting the user every time they add another bulb.

Plaintext on disk by design, same posture as ucapi-framework's per-device config
persistence. Both files live in the integration's config dir which is gitignored.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

_LOG = logging.getLogger(__name__)

_ACCOUNT_FILENAME = "account.json"


@dataclass
class TapoAccount:
    username: str
    password: str


def _account_file(config_dir: str) -> Path:
    return Path(config_dir) / _ACCOUNT_FILENAME


def load_account(config_dir: str) -> TapoAccount | None:
    path = _account_file(config_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TapoAccount(
            username=data.get("username", ""),
            password=data.get("password", ""),
        )
    except (OSError, json.JSONDecodeError) as err:
        _LOG.warning("Failed to load account from %s: %s", path, err)
        return None


def save_account(config_dir: str, account: TapoAccount) -> None:
    path = _account_file(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"username": account.username, "password": account.password}, f)
    _LOG.info("Saved Tapo account to %s", path)

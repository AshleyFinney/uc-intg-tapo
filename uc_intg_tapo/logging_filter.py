"""Logging filter that scrubs credentials from log records before output.

ucapi's WebSocket-frame DEBUG logs dump the full message payload, which
includes any setup-flow user input. Without scrubbing, a single DEBUG run
during a fresh setup writes the user's TP-Link password and email to the
log file in plaintext. Logs travel (uploaded for support, pasted in bug
reports, backed up by the OS) so we mask known sensitive keys at
log-record time.
"""

import logging
import re

_REDACTED = "<REDACTED>"

_SENSITIVE_KEYS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "auth_token",
    "credentials",
    # ucapi setup-flow user input keys we use for the TP-Link account.
    # "username" is the email field, treat it as sensitive.
    "username",
    "email",
)


def _make_rule(key: str):
    """Build a (compiled-regex, replace-callback) pair for a single sensitive key."""
    pattern = re.compile(
        rf'(["\']){re.escape(key)}\1(\s*:\s*)(["\']).*?\3',
        re.IGNORECASE,
    )

    def replace(match: re.Match) -> str:
        key_q = match.group(1)
        sep = match.group(2)
        val_q = match.group(3)
        return f"{key_q}{key}{key_q}{sep}{val_q}{_REDACTED}{val_q}"

    return pattern, replace


_RULES = [_make_rule(key) for key in _SENSITIVE_KEYS]


class CredentialScrubber(logging.Filter):
    """Mask values of sensitive keys in any log record's formatted message.

    Handles JSON-shaped (`"password": "value"`) and Python-repr-shaped
    (`'password': 'value'`) payloads, since ucapi.api logs incoming frames
    as JSON strings and outgoing dicts via Python repr.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        scrubbed = msg
        for pattern, replace in _RULES:
            scrubbed = pattern.sub(replace, scrubbed)

        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()

        return True


def install() -> None:
    """Attach the scrubber to every handler on the root logger.

    Filters added to a logger only apply to records logged directly through
    that logger, child-logger records propagating up don't trip them. The
    handlers, however, see every record on its way out, so attaching the
    scrubber there catches output from ucapi.api and any other library logger.
    Call this AFTER ``logging.basicConfig`` has set up the handlers.
    """
    scrubber = CredentialScrubber()
    for handler in logging.getLogger().handlers:
        handler.addFilter(scrubber)

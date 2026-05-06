"""Logging filters for the Tapo integration.

Two concerns:

1. CredentialScrubber. ucapi's WebSocket-frame DEBUG logs dump the full
   message payload, which includes any setup-flow user input. Without
   scrubbing, a single DEBUG run during a fresh setup writes the user's
   TP-Link password and email to the log file in plaintext. Logs travel
   (uploaded for support, pasted in bug reports, backed up by the OS) so
   we mask known sensitive keys at log-record time.

2. KasaTransientNoiseFilter. python-kasa's klaptransport logs at ERROR
   every time it has to retry after a Tapo session-token quirk. The
   retries succeed automatically and the devices are functionally fine,
   but to a reading user the wall of red looks like the integration is
   broken. We drop only the specific patterns we've positively identified
   as cosmetic/transient. Genuinely-failing operations still surface
   through our own client.py / device.py error handling, which is
   unaffected.
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


_KASA_TRANSIENT_PATTERNS = (
    # 403 "Query failed after successful authentication" — fires during startup
    # bursts when many plugs (esp. >10 P110s) authenticate simultaneously and
    # something else (Tapo phone app, another integration) races our token.
    # python-kasa re-authenticates and retries; recovers within ~60 s of the
    # initial connect. Validated 2026-05-06 by a community user with 14 plugs.
    re.compile(r"Query failed after successful authentication.*Response status is 403"),
    # 400 "to handshake2" on first connect of a P110 — Tapo session-token
    # quirk that recovers in ~250 ms.
    re.compile(r"400 to handshake2"),
)


class KasaTransientNoiseFilter(logging.Filter):
    """Drop kasa transport ERROR records matching known-transient patterns.

    Attached directly to the ``kasa.transports.klaptransport`` logger so it
    only sees records from that source. Returns False for matching messages
    (record is dropped). Returns True for everything else, so any new or
    unrecognised pattern still surfaces at its original level.

    Safety: real connection / poll failures don't depend on the transport
    logger to surface. If kasa's retry chain ultimately fails, the exception
    propagates up to ``client.update()`` and our ``device.poll_device()``
    catches it and logs at WARNING. The transport-level ERROR is a symptom
    of a retry attempt; our integration logs the *outcome*. Filtering the
    symptom while preserving the outcome-log is the safe choice.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for pattern in _KASA_TRANSIENT_PATTERNS:
            if pattern.search(msg):
                return False
        return True


def install() -> None:
    """Attach the credential scrubber to every handler on the root logger,
    and the kasa-transient-noise filter to the kasa.transports.klaptransport
    logger.

    Filters added to a logger only apply to records logged directly through
    that logger, child-logger records propagating up don't trip them. The
    handlers, however, see every record on its way out, so attaching the
    scrubber there catches output from ucapi.api and any other library logger.

    The kasa-noise filter is attached to its specific logger rather than to
    a handler, so it only evaluates kasa-transport records. This narrows the
    blast radius and keeps per-record cost negligible for everything else.

    Call this AFTER ``logging.basicConfig`` has set up the handlers.
    """
    scrubber = CredentialScrubber()
    for handler in logging.getLogger().handlers:
        handler.addFilter(scrubber)

    kasa_logger = logging.getLogger("kasa.transports.klaptransport")
    kasa_logger.addFilter(KasaTransientNoiseFilter())

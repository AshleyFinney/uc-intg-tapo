"""Discovery class. Stub-only.

The framework's setup flow checks ``self.discovery is not None`` to decide whether
to run discovery at all. We need that check to pass, but the real discovery work
needs the user's TP-Link credentials (collected on the pre-discovery screen) so
it lives in :meth:`TapoSetupFlow.discover_devices` instead. This class exists
purely so we can hand the framework a non-None discovery instance.
"""

from ucapi_framework import BaseDiscovery, DiscoveredDevice


class TapoDiscovery(BaseDiscovery):
    async def discover(self) -> list[DiscoveredDevice]:
        return []

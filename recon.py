"""Recon: enumerate Tapo / Kasa devices on the LAN without auth.

This won't fully control authenticated devices (Tapo / KLAP-protected),
but it should at least see them on the network and report what python-kasa
identifies them as. That tells us if the L530 (and the rest) are reachable.
"""

import asyncio
from kasa import Discover


async def main():
    print("Scanning local network for Tapo / Kasa devices (5s)...")
    devices = await Discover.discover(discovery_timeout=5)

    if not devices:
        print("No devices discovered.")
        return

    print(f"\nFound {len(devices)} device(s):\n")
    for ip, dev in devices.items():
        print(f"  {ip}")
        print(f"    type:  {type(dev).__name__}")
        print(f"    model: {getattr(dev, 'model', '?')}")
        print(f"    mac:   {getattr(dev, 'mac', '?')}")
        print(f"    alias: {getattr(dev, 'alias', '?')}")
        device_type = getattr(dev, "device_type", None)
        if device_type:
            print(f"    device_type: {device_type}")
        hw_info = getattr(dev, "hw_info", None)
        if hw_info:
            print(f"    hw_info: {hw_info}")
        print()


if __name__ == "__main__":
    asyncio.run(main())

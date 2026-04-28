"""Authenticated discovery + on/off test against an L530.

Run, paste credentials when prompted, pick an L530 from the list, watch it
toggle. Credentials live in memory only, never written to disk.
"""

import asyncio

from kasa import Credentials, Discover


async def discover_with_creds(creds: Credentials):
    print("\nScanning local network with credentials (5s)...")
    devices = await Discover.discover(credentials=creds, discovery_timeout=5)

    if not devices:
        print("No devices discovered.")
        return []

    print(f"\nFound {len(devices)} device(s). Fetching details...\n")
    results = []
    for ip, dev in devices.items():
        try:
            await dev.update()
            alias = dev.alias or "(no alias)"
            print(f"  [{len(results)}] {ip:18}  {dev.model:8}  {dev.device_type.value:14}  {alias}")
            results.append((ip, dev))
        except Exception as ex:
            print(f"  ??  {ip:18}  {dev.model:8}  failed to fetch details: {ex}")

    return results


def pick_l530(devices):
    """Filter to L530s and ask the user which one to test."""
    candidates = [(ip, dev) for ip, dev in devices if "L530" in dev.model]
    if not candidates:
        print("\nNo L530 bulbs found.")
        return None
    if len(candidates) == 1:
        ip, dev = candidates[0]
        print(f"\nOnly one L530 found, using it: {ip} ({dev.alias})")
        return dev

    print("\nL530 bulbs:")
    for i, (ip, dev) in enumerate(candidates):
        print(f"  [{i}] {ip:18}  {dev.model:8}  {dev.alias or '(no alias)'}")

    while True:
        choice = input("Pick which L530 to test (number, blank to abort): ").strip()
        if not choice:
            return None
        try:
            return candidates[int(choice)][1]
        except (ValueError, IndexError):
            print("  Invalid choice.")


async def toggle_test(dev):
    print(f"\nTesting {dev.alias} ({dev.model} at {dev.host})...")
    print(f"  Current state: {'ON' if dev.is_on else 'OFF'}")
    starting_state = dev.is_on

    target_off = starting_state
    print(f"  Turning {'OFF' if target_off else 'ON'}...")
    if target_off:
        await dev.turn_off()
    else:
        await dev.turn_on()
    await asyncio.sleep(2)
    await dev.update()
    print(f"  State now: {'ON' if dev.is_on else 'OFF'}")

    print("  Sleeping 12s (long enough to clear a 10s fade-off)...")
    await asyncio.sleep(12)

    print(f"  Restoring to {'ON' if starting_state else 'OFF'}...")
    if starting_state:
        await dev.turn_on()
    else:
        await dev.turn_off()
    await asyncio.sleep(1)
    await dev.update()
    print(f"  Final state: {'ON' if dev.is_on else 'OFF'}")
    print("\nDone.")


async def main():
    print("TP-Link Tapo authentication test")
    print("Note: password input is visible (one-off recon, fine for personal machine).")
    print("Credentials are kept in memory only, never written to disk.\n")
    username = input("TP-Link account email: ").strip()
    password = input("TP-Link account password: ").strip()
    creds = Credentials(username=username, password=password)

    devices = await discover_with_creds(creds)
    if not devices:
        return

    target = pick_l530(devices)
    if target is None:
        print("Nothing selected, exiting.")
        return

    await toggle_test(target)


if __name__ == "__main__":
    asyncio.run(main())

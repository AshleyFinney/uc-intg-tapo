# Tapo Integration for Unfolded Circle Remote 2/3

Control your TP-Link Tapo smart bulbs, light strips, and plugs from your Unfolded Circle Remote 2 or Remote 3. Brightness, colour, colour temperature, on/off, and live energy readings for plugs that support them, all over your local network using your TP-Link account credentials.

![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)

---

## ⚠️ Experimental — please read before installing

This integration is **early-access software**. It works for the maintainer's own devices but has had only light testing. By installing it you accept that:

- You use it at your own risk. Misbehaviour, lost configuration, devices that need re-pairing, or anything else that goes wrong is your responsibility, not the maintainer's.
- Future versions may include breaking changes. Entity IDs, configuration schema, or feature behaviour might shift between releases. Effort will be made to limit this, but no guarantees.
- **Your TP-Link account credentials are stored as plaintext on the Remote.** There's no practical way to encrypt them: any decryption key would have to live on the same device, which is security theatre. If storing your TP-Link account password in plaintext on the Remote bothers you, please don't install this integration.
- Some features behave the way they do because of Tapo bulb firmware, Remote 3 firmware, or python-kasa library decisions. Those aren't always fixable from inside this integration.

If any of that puts you off, wait for a later, more stable release.

---

## Features

Per-device entities are created automatically based on what each device reports as supported.

### Lights (bulbs and light strips)

- **On / off / toggle** — for every supported light.
- **Brightness** — for any bulb that reports dimming support.
- **Colour (HSV)** — for full-colour bulbs.
- **Colour temperature** — for tunable-white bulbs.

### Plugs (switches)

- **On / off / toggle** — for every supported plug.

### Energy sensors (P110 and similar)

For plugs that expose energy monitoring, five sensor entities are created alongside the switch:

- **Current power** in watts
- **Today's energy** in kWh
- **This month's energy** in kWh
- **Voltage** in volts
- **Current** in amps

Voltage and current sensors only appear on devices that report those readings.

### Other

- **Touch slider** on the Remote 3 controls brightness for any light entity in an activity.
- **Capability migration** at startup, so devices paired before a feature was added pick it up automatically once you upgrade.

---

## Tested devices

Briefly tested on:

- **L430C** colour bulb (full colour, brightness, colour temperature)
- **P100** smart plug (on/off only, no energy monitoring)
- **P110** smart plug (on/off, plus all five energy sensors)

Other Tapo bulbs (e.g. L530, L900, L920 light strip) and other plug variants (e.g. P115) **may** work, since the integration relies on python-kasa's device-class detection and capability flags rather than hard-coded model lists, but they haven't been verified by the maintainer. If you try one and it works, or doesn't, the maintainer would appreciate a note.

Out of scope:

- The H100 hub and its child sensors (T315 temperature/humidity etc.). These are deferred to a much later release.
- Tapo cameras. Not supported.

---

## Installation

1. Download the latest `uc-intg-tapo-<version>-aarch64.tar.gz` from the [Releases page](https://github.com/AshleyFinney/uc-intg-tapo/releases).
2. On your Remote 2 or Remote 3, open the web configurator (Settings → Integrations → Add Integration → Upload from file).
3. Upload the `.tar.gz`. The Remote will install the integration and restart it.
4. Continue to setup, below.

---

## Setup

### 1. Account credentials

When you first add the integration, you'll be asked for the email and password of the **TP-Link account that your Tapo devices are linked to**. The same credentials that work in the Tapo phone app.

The credentials are stored on the Remote alongside the integration's other configuration. They never leave your local network. They're also masked from any log output the integration produces.

### 2. Discover devices

After the credentials screen, the integration scans your LAN for Tapo devices. Bulbs, strips, and plugs that respond appear in a dropdown. Pick one, give it a friendly name (or accept the alias the device reports), and confirm. Repeat for each device you want to control.

If a device doesn't appear in the list, you can fall back to manual entry by IP. This is also the path for devices on a different VLAN to your Remote.

### 3. Add devices to activities

Once paired, each device shows up as one or more entities in your Remote's entity list. Add them to activities the same way you would any other entity.

The **Remote 3's touch slider** can be bound to brightness, hue, saturation, or colour temperature in the activity settings. Open Devices → tap the bulb to get the standalone entity view with brightness slider, colour wheel, and colour-temperature slider auto-rendered.

---

## Known limitations and quirks

Things that aren't bugs as such but are worth knowing about:

- **Colour vs white mode.** Tapo colour bulbs operate in either colour mode or white mode, never both at once. Setting a colour temperature switches the bulb to white mode; setting a hue/saturation switches it back to colour mode. The Remote's UI reflects the bulb's current mode, so if you've just set a colour temperature you may need to pick a colour again to get back into the colour wheel.
- **Brightness perception isn't linear.** At low brightness values, small slider movements feel like big changes; at the top end, a large slider movement feels subtle. This is the bulb's hardware response curve, not the slider mapping.
- **Touch slider granularity.** On the Remote 3's physical touch slider, each swipe moves brightness by roughly 10% of full range. There's no integration-level control over the swipe sensitivity.
- **Sensor "show label" toggle.** In the configurator, toggling "show label" on a sensor entity shows the device-class label ("Power", "Voltage" etc.) in the configurator preview, but doesn't propagate to the actual Remote display. Workaround: edit the sensor's title manually, that shows in both places.
- **First connection on some plugs may briefly fail and retry.** You may see one quick "cannot reach" log line for a plug at startup, followed by a successful connection a fraction of a second later. This is a Tapo session-token quirk and recovers on its own.

---

## Credits and licence

- Built on [python-kasa](https://github.com/python-kasa/python-kasa) for device communication.
- Built on [ucapi-framework](https://github.com/jackjpowell/ucapi-framework) wrapping Unfolded Circle's [integration-python-library](https://github.com/unfoldedcircle/integration-python-library).
- Distributed under the [Mozilla Public License 2.0](LICENSE).

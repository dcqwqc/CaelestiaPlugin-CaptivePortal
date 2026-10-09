# CaelestiaPlugin-CaptivePortal

Adds a **Sign in to Wi-Fi** action to Caelestia's network flyout only when a connected Wi-Fi interface looks like it is behind a captive portal.

## Behaviour

- Verifies that a real Wi-Fi device is connected before showing anything.
- Binds connectivity probes to that Wi-Fi interface so Tailscale/other interfaces cannot create false state.
- Checks several OS connectivity endpoints, but never trusts them alone because captive Wi-Fi can whitelist them.
- Requires a real HTTPS connection before declaring Internet access fully available.
- Detects RFC 8910/RFC 8908 captive-portal advertisements when NetworkManager exposes them.
- Treats HTTP redirects, HTTP 511, or replaced connectivity-check content as a captive portal.
- Stores and opens the portal's actual HTTP Location when the network provides one.
- If a portal injects login HTML instead of redirecting, opens the original plain-HTTP connectivity URL so the network can intercept it again.
- Treats DNS failures/timeouts as offline/unknown, not as a captive portal.
- Revalidates the active connection after every probe so stale results do not survive SSID changes/disconnects.
- Limited-connectivity fallback visibility is disabled by default to prevent phantom sign-in buttons.
- Never uses NeverSSL as the login destination.

- Portal checks run in parallel so detection finishes in a few seconds even when several endpoints time out.
- Clicking an unknown portal retries discovery in the background and never opens example.com, NeverSSL, or a connectivity-test page as a fallback.

- Portal clicks use Zen directly on Mirai, log their result, and use REWE's own plain-HTTP site as the REWE-specific browser trigger if no direct redirect is exposed.

## Install

    git clone https://github.com/dcqwqc/CaelestiaPlugin-CaptivePortal.git
    cd CaelestiaPlugin-CaptivePortal
    ./install.sh

The companion Caelestia shell integration consumes the plugin entry point with slot networkPortal inside modules/bar/popouts/Network.qml.

## Wi-Fi-bound sign-in browser (0.5.2)

When the sign-in button is clicked, the existing detector still discovers a **fresh** login URL from the connected Wi-Fi. The opener now prefers a separate Zen/Firefox browser profile (Chromium fallback) with a temporary localhost proxy whose outbound sockets and DNS queries are **bound to that Wi-Fi interface**. This is especially important when USB tethering or Ethernet has the working default route.

- No NetworkManager profile changes, no privileged route edits, no disruption of tethering, and no changes to the user's normal browser tabs or proxy preferences.
- The isolated browser works with Mirai's Zen Flatpak (temporary profile permission) as well as host-installed Zen/Firefox/Chromium.
- If an HTTP redirect isn't discoverable, the opener can use the Wi-Fi DHCP gateway as a safe local fallback. An old portal challenge is only a final fallback, never the first choice.
- The isolated proxy only listens on 127.0.0.1 and is shut down when the sign-in browser closes or after ten minutes. HTTPS is tunneled end-to-end without TLS interception.
- If the isolated browser cannot start, the previous Zen/GIO launcher remains available as a fallback.

**Read-only diagnostics**, while connected to the Wi-Fi network:

```bash
python3 ~/.local/share/caelestia/plugins/captive-portal/portal_helper.py diagnose
```

The output distinguishes Wi-Fi DHCP failures, unreachable gateways, detected captive redirects, and missing public connectivity. It may contain your login-session URL and device identifiers; redact these before sharing logs.

**Run offline tests** from the plugin repository:

```bash
python3 -m unittest discover -s tests -v
```

A failed onboard hotspot or a train with no uplink cannot be repaired by the plugin; the isolated browser only ensures the sign-in traffic uses the intended Wi-Fi network.

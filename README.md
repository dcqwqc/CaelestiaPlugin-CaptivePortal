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

## Install

    git clone https://github.com/dcqwqc/CaelestiaPlugin-CaptivePortal.git
    cd CaelestiaPlugin-CaptivePortal
    ./install.sh

The companion Caelestia shell integration consumes the plugin entry point with slot networkPortal inside modules/bar/popouts/Network.qml.

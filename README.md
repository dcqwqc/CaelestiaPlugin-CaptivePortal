# CaelestiaPlugin-CaptivePortal

Adds a **Sign in to Wi-Fi** action to Caelestia's network flyout when NetworkManager reports a captive portal or limited Wi-Fi connection.

## Behaviour

- Checks `nmcli networking connectivity check` while the network flyout is mounted.
- Shows the action for `portal` connectivity.
- By default also shows it for `limited`, because some captive networks are reported that way.
- Opens a plain HTTP endpoint so the captive network can redirect the browser to its login/accept-terms page.
- Includes plugin settings for limited-connectivity visibility, always-visible mode, and probe interval.

## Install

```bash
git clone https://github.com/dcqwqc/CaelestiaPlugin-CaptivePortal.git
cd CaelestiaPlugin-CaptivePortal
./install.sh
```

The companion Caelestia shell integration consumes the plugin entry point with slot `networkPortal` inside `modules/bar/popouts/Network.qml`.

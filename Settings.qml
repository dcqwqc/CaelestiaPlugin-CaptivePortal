import Caelestia.Plugins

SettingsObject {
    property bool showWhenLimited: false
    SettingMeta on showWhenLimited {
        label: "Show on ambiguous limited Wi-Fi"
        description: "Optional fallback for networks that report limited connectivity without a confirmed captive-portal redirect. Off by default to avoid false sign-in prompts."
        icon: "signal_wifi_bad"
        inputType: SettingMeta.Switch
    }

    property bool alwaysShow: false
    SettingMeta on alwaysShow {
        label: "Always show action"
        description: "Keep the Wi-Fi sign-in action visible whenever a Wi-Fi network is connected, even without a detected portal."
        icon: "visibility"
        inputType: SettingMeta.Switch
    }

    property int checkIntervalSeconds: 3
    SettingMeta on checkIntervalSeconds {
        label: "Portal check interval"
        description: "Seconds between captive-portal checks while the network flyout is open."
        icon: "timer"
        inputType: SettingMeta.SpinBox
        min: 2
        max: 60
        step: 1
    }
}

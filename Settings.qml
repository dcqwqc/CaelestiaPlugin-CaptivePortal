import Caelestia.Plugins

SettingsObject {
    property bool showWhenLimited: true
    SettingMeta on showWhenLimited {
        label: "Show on limited Wi-Fi"
        description: "Also show the sign-in action when NetworkManager reports limited connectivity instead of an explicit captive portal."
        icon: "signal_wifi_bad"
        inputType: SettingMeta.Switch
    }

    property bool alwaysShow: false
    SettingMeta on alwaysShow {
        label: "Always show action"
        description: "Keep the Wi-Fi sign-in action visible whenever a Wi-Fi network is connected."
        icon: "visibility"
        inputType: SettingMeta.Switch
    }

    property int checkIntervalSeconds: 5
    SettingMeta on checkIntervalSeconds {
        label: "Portal check interval"
        description: "Seconds between NetworkManager captive-portal checks while the network flyout is open."
        icon: "timer"
        inputType: SettingMeta.SpinBox
        min: 2
        max: 60
        step: 1
    }
}

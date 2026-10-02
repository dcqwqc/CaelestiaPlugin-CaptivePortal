pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services

StyledRect {
    id: root

    required property var settings

    property string connectivity: "unknown"

    readonly property bool mounted: width > 1
    readonly property bool activeWifi: Nmcli.wifiEnabled && [...Nmcli.networks].some(network => network.active)
    readonly property bool showWhenLimited: settings ? settings.showWhenLimited : true
    readonly property bool alwaysShow: settings ? settings.alwaysShow : false
    readonly property int checkIntervalSeconds: settings ? settings.checkIntervalSeconds : 5
    readonly property bool shouldShow: activeWifi && (
        connectivity === "portal"
        || (showWhenLimited && connectivity === "limited")
        || alwaysShow
    )

    implicitWidth: 260
    implicitHeight: shouldShow ? buttonContent.implicitHeight + Tokens.padding.small : 0
    visible: shouldShow

    radius: Tokens.rounding.full
    color: Colours.palette.m3primaryContainer

    function checkNow(): void {
        if (!mounted || !activeWifi) {
            connectivity = "none";
            return;
        }

        if (!connectivityCheck.running)
            connectivityCheck.running = true;
    }

    function openPortal(): void {
        // Deliberately plain HTTP so a captive network can redirect to its login page.
        Quickshell.execDetached(["xdg-open", "http://neverssl.com"]);
        checkDelay.restart();
    }

    StateLayer {
        anchors.fill: parent
        color: Colours.palette.m3onPrimaryContainer
        onClicked: root.openPortal()
    }

    RowLayout {
        id: buttonContent

        anchors.centerIn: parent
        spacing: Tokens.spacing.small

        MaterialIcon {
            id: signInIcon
            Layout.topMargin: Math.round(fontInfo.pointSize * 0.0575)
            text: "wifi_password"
            color: Colours.palette.m3onPrimaryContainer
        }

        StyledText {
            Layout.topMargin: -Math.round(signInIcon.fontInfo.pointSize * 0.0575)
            text: qsTr("Sign in to Wi-Fi")
            color: Colours.palette.m3onPrimaryContainer
            font: Tokens.font.body.builders.medium.weight(Font.Medium).build()
        }

        MaterialIcon {
            text: "open_in_new"
            fontStyle: Tokens.font.icon.small
            color: Colours.palette.m3onPrimaryContainer
        }
    }

    Process {
        id: connectivityCheck

        // Forcing a NetworkManager connectivity recheck may require Polkit.
        // Use an unprivileged HTTP 204 probe and cached NetworkManager state as fallback.
        command: ["sh", "-c",
            "if command -v curl >/dev/null 2>&1; then " +
            "code=$(curl -sS --connect-timeout 2 --max-time 4 -o /dev/null -w '%{http_code}' http://connectivitycheck.gstatic.com/generate_204 2>/dev/null || true); " +
            "case $code in 204) printf full;; 000|'') nmcli networking connectivity 2>/dev/null || printf unknown;; *) printf portal;; esac; " +
            "else nmcli networking connectivity 2>/dev/null || printf unknown; fi"]

        stdout: StdioCollector {
            onStreamFinished: {
                const state = text.trim().toLowerCase();
                root.connectivity = ["none", "portal", "limited", "full", "unknown"].includes(state)
                    ? state
                    : "unknown";
            }
        }
    }

    Timer {
        interval: Math.max(2, root.checkIntervalSeconds) * 1000
        repeat: true
        triggeredOnStart: true
        running: root.mounted && root.activeWifi
        onTriggered: root.checkNow()
    }

    Timer {
        id: checkDelay
        interval: 2500
        repeat: false
        onTriggered: root.checkNow()
    }

    Connections {
        target: Nmcli
        function onNetworksChanged(): void {
            root.checkNow();
        }
        function onWifiEnabledChanged(): void {
            root.checkNow();
        }
    }
}

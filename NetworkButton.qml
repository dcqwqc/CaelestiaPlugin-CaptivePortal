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
        command: ["nmcli", "networking", "connectivity", "check"]

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

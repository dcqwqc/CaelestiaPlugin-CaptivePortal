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

    property string connectivity: "none"
    property string portalUrl: ""
    property bool wifiConnected: false

    readonly property bool mounted: width > 1
    readonly property bool showWhenLimited: settings ? settings.showWhenLimited : false
    readonly property bool alwaysShow: settings ? settings.alwaysShow : false
    readonly property int checkIntervalSeconds: settings ? settings.checkIntervalSeconds : 5
    readonly property bool shouldShow: wifiConnected && (
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
        if (!mounted) {
            connectivity = "none";
            portalUrl = "";
            wifiConnected = false;
            return;
        }

        if (!connectivityCheck.running)
            connectivityCheck.running = true;
    }

    function openPortal(): void {
        if (!wifiConnected)
            return;

        const target = portalUrl.length > 0
            ? portalUrl
            : "http://example.com/";

        Quickshell.execDetached(["xdg-open", target]);
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
        }

        MaterialIcon {
            text: "open_in_new"
            fontStyle: Tokens.font.icon.small
            color: Colours.palette.m3onPrimaryContainer
        }
    }

    Process {
        id: connectivityCheck

        command: ["sh", "-c",
            "$HOME/.local/share/caelestia/plugins/captive-portal/scripts/captive-portal-check"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                const raw = text.trim();
                const fields = raw.split("\t");
                const state = fields[0] || "unknown";
                const valid = ["none", "portal", "limited", "full", "offline", "unknown"];

                root.connectivity = valid.includes(state) ? state : "unknown";
                root.wifiConnected = root.connectivity !== "none";
                root.portalUrl = root.connectivity === "portal" && fields.length > 1
                    ? fields.slice(1).join("\t").trim()
                    : "";
            }
        }
    }

    Timer {
        interval: Math.max(2, root.checkIntervalSeconds) * 1000
        repeat: true
        triggeredOnStart: true
        running: root.mounted
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

    onMountedChanged: {
        if (mounted)
            checkNow();
        else {
            connectivity = "none";
            portalUrl = "";
            wifiConnected = false;
        }
    }
}

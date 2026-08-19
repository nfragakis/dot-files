import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

// A focused, screen-centered variant of Omarchy's KeyboardPanel. Still is a
// deliberate interruption rather than a widget settings popout, so its card
// belongs in the center of the active display instead of beside the bar icon.
PanelWindow {
    id: root

    required property Item anchorItem
    required property QtObject bar
    property var owner: null
    property bool open: false
    property Item focusTarget: null
    property int padding: Style.spacing.popupPadding
    property int margin: Style.gapsOut
    property int contentWidth: Style.space(420)
    property int contentHeight: Style.space(520)
    property var borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
    property bool focusPrimed: false

    default property alias panelContent: contentHolder.children

    readonly property var coordinatorKey: owner || root
    readonly property var anchorWindow: anchorItem ? anchorItem.QsWindow.window : null
    readonly property real screenWidth: screen ? screen.width : 0
    readonly property real screenHeight: screen ? screen.height : 0
    readonly property real availableCardWidth: Math.max(120, screenWidth - margin * 2)
    readonly property real availableCardHeight: Math.max(120, screenHeight - margin * 2)
    readonly property real verticalContentInset: padding * 2 + Border.top(borderSpec) + Border.bottom(borderSpec)

    function fittedContentWidth(width, cap) {
        var desired = Math.max(1, Number(width) || 1);
        var maximum = availableCardWidth > 0 ? availableCardWidth : desired;
        if (cap !== undefined && Number(cap) > 0)
            maximum = Math.min(maximum, Number(cap));

        return Math.round(Math.min(desired, maximum));
    }

    function fittedContentHeight(implicitHeight, cap) {
        var desired = Math.max(verticalContentInset, (Number(implicitHeight) || 0) + verticalContentInset);
        var maximum = availableCardHeight > 0 ? availableCardHeight : desired;
        if (cap !== undefined && Number(cap) > 0)
            maximum = Math.min(maximum, Number(cap));

        return Math.round(Math.min(desired, maximum));
    }

    function close() {
        if (owner && "close" in owner)
            owner.close();
        else
            open = false;
    }

    screen: anchorWindow ? anchorWindow.screen : null
    visible: open || card.opacity > 0
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore

    WlrLayershell.namespace: "still-centered-panel"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: open
        ? (focusPrimed ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.Exclusive)
        : WlrKeyboardFocus.None

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    onOpenChanged: {
        if (open) {
            focusPrimed = false;
            focusPrimeTimer.restart();
            if (bar)
                bar.requestPopout(coordinatorKey);
            if (focusTarget)
                Qt.callLater(function() {
                    if (root.open && root.focusTarget)
                        root.focusTarget.forceActiveFocus();
                });
        } else {
            focusPrimeTimer.stop();
            focusPrimed = false;
            if (bar && bar.activePopout === coordinatorKey)
                bar.releasePopout(coordinatorKey);
        }
    }

    Timer {
        id: focusPrimeTimer

        interval: 75
        onTriggered: if (root.open)
            root.focusPrimed = true
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.open
        acceptedButtons: Qt.AllButtons
        onClicked: root.close()
    }

    BorderSurface {
        id: card

        x: Math.round((root.screenWidth - width) / 2)
        y: Math.round((root.screenHeight - height) / 2)
        width: root.contentWidth
        height: root.contentHeight
        color: Color.popups.background
        borderSpec: root.borderSpec
        padding: root.padding
        radius: Style.cornerRadius
        opacity: root.open ? 1 : 0

        Behavior on opacity {
            NumberAnimation {
                duration: 140
                easing.type: Easing.OutCubic
            }
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
        }

        Item {
            id: contentHolder

            anchors.fill: parent
            anchors.topMargin: card.contentTopInset
            anchors.rightMargin: card.contentRightInset
            anchors.bottomMargin: card.contentBottomInset
            anchors.leftMargin: card.contentLeftInset
        }
    }
}

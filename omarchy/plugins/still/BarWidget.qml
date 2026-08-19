import "Protocols.js" as Protocols
import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
    id: root

    readonly property var session: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
    readonly property string sessionState: session ? session.sessionState : "idle"
    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
    readonly property bool popoutSwitchClosing: panelLoader.item
        ? panelLoader.item.popoutSwitchClosing === true
        : false

    function phasePrefix() {
        if (!session)
            return ""
        if (sessionState === "countdown")
            return "READY " + session.countdownNumber
        if (sessionState === "paused")
            return "PAUSED"
        if (sessionState === "complete")
            return "DONE"
        if (sessionState !== "running")
            return ""
        return Protocols.phaseShortLabel(session.phaseType) + " " + session.phaseSecondsRemaining
    }

    function injectPanel() {
        var target = panelLoader.item
        if (!target)
            return

        target.bar = root.bar
        target.settings = root.settings
        target.anchorItem = button
        target.hostWidget = root
        target.session = root.session
    }

    function open() {
        if (panelLoader.item)
            panelLoader.item.open()
    }

    function close() {
        if (panelLoader.item)
            panelLoader.item.close()
    }

    function togglePanel() {
        if (panelLoader.item)
            panelLoader.item.toggle()
    }

    function closeForPopoutSwitch() {
        if (panelLoader.item)
            panelLoader.item.closeForPopoutSwitch()
    }

    moduleName: "still"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    onBarChanged: injectPanel()
    onSettingsChanged: injectPanel()
    onSessionChanged: injectPanel()

    Binding {
        target: root.session
        property: "settings"
        value: root.settings
        when: root.session !== null
    }

    Loader {
        id: panelLoader

        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: {
            root.injectPanel()
            Qt.callLater(root.injectPanel)
        }
    }

    TextMetrics {
        id: phaseLabelMetrics

        font: phaseLabel.font
        text: "READY 00"
    }

    WidgetButton {
        id: button

        anchors.fill: parent
        bar: root.bar
        labelVisible: false
        hasVisualContent: true
        fixedWidth: root.vertical
            ? root.barSize
            : (root.sessionState === "idle" ? root.barSize : markRow.implicitWidth + Style.space(12))
        tooltipText: root.sessionState === "idle"
            ? "Still · start a breathing session"
            : (root.sessionState === "complete" ? "Still · session complete" : "Still · " + root.phasePrefix())
        active: root.opened
        useActiveColor: false
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.LeftButton)
                root.togglePanel()
        }

        Row {
            id: markRow

            anchors.centerIn: parent
            spacing: Style.space(5)

            BreathBloom {
                width: Style.bar.iconCanvas
                height: width
                anchors.verticalCenter: parent.verticalCenter
                level: root.session
                    ? (root.sessionState === "idle" ? 0.36 : root.session.breathLevel)
                    : 0.36
                active: root.sessionState === "running"
                reducedMotion: root.session ? root.session.reducedMotion : false
                visualScale: 1.25
                phaseType: root.session ? root.session.phaseType : "normal"
                accent: root.bar ? root.bar.barForeground : Color.accent
                foreground: root.bar ? root.bar.barForeground : Color.foreground
                muted: root.bar ? root.bar.barForeground : Color.muted
            }

            Text {
                id: phaseLabel

                visible: !root.vertical && root.sessionState !== "idle"
                anchors.verticalCenter: parent.verticalCenter
                width: phaseLabelMetrics.advanceWidth
                text: root.phasePrefix()
                color: root.sessionState === "complete"
                    ? Color.accent
                    : (root.bar ? root.bar.barForeground : Color.foreground)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                font.weight: root.sessionState === "running" ? Font.DemiBold : Font.Normal
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}

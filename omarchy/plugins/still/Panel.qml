import "Protocols.js" as Protocols
import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

Panel {
    id: root

    property var anchorItem: null
    property var hostWidget: null
    readonly property var barIdentity: hostWidget || root
    property string screen: "setup" // setup | warning | running | done
    property string intent: "calm"
    property int difficulty: 0
    property int durationIndex: 1
    property var phases: []
    property int phaseIndex: 0
    property double phaseStartedAt: 0
    property double sessionStartedAt: 0
    property int phaseElapsedMs: 0
    property int sessionElapsedMs: 0
    property bool paused: false
    property double pausedAt: 0
    property int pauseAccumulatedMs: 0
    property real orbScale: 0.18
    readonly property int durationSec: Protocols.DURATIONS[durationIndex]
    readonly property var activePreset: Protocols.preset(intent, difficulty)
    readonly property var activePhase: phases.length ? phases[Math.min(phaseIndex, phases.length - 1)] : ["inhale", 4]
    readonly property string phaseType: activePhase[0]
    readonly property real phaseSeconds: activePhase[1]
    readonly property int phaseRemaining: Math.max(1, Math.ceil(phaseSeconds - phaseElapsedMs / 1000))
    readonly property int sessionRemaining: Math.max(0, durationSec - Math.floor(sessionElapsedMs / 1000))
    readonly property color foreground: bar ? bar.foreground : Color.foreground
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

    function open() {
        screen = "setup";
        controller.show();
    }

    function close() {
        stopSession();
        controller.hide();
    }

    function toggle() {
        if (opened)
            close();
        else
            open();
    }

    function switchPanel(direction) {
        if (bar && typeof bar.switchPanelFrom === "function")
            return bar.switchPanelFrom(barIdentity, direction);

        return false;
    }

    function requestStart() {
        if (activePreset.advanced)
            screen = "warning";
        else
            startSession();
    }

    function startSession() {
        phases = Protocols.phasesFor(intent, difficulty, durationSec);
        phaseIndex = 0;
        pauseAccumulatedMs = 0;
        paused = false;
        sessionStartedAt = Date.now();
        phaseStartedAt = sessionStartedAt;
        screen = "running";
        enterPhase();
        ticker.start();
    }

    function enterPhase() {
        phaseStartedAt = Date.now();
        phaseElapsedMs = 0;
        var target = Protocols.phaseScale(phaseType);
        if (target >= 0)
            orbScale = target;

        playCue(phaseType);
    }

    function playCue(type) {
        if (setting("sound", true) !== true || !bar)
            return ;

        var source = type === "exhale" || type === "retain" ? "out.ogg" : "in.ogg";
        var base = Qt.resolvedUrl("sounds/" + source).toString().replace(/^file:\/\//, "");
        bar.run("pw-play " + shellQuote(base));
    }

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function advancePhase() {
        phaseIndex++;
        if (phaseIndex >= phases.length) {
            if (activePreset.power) {
                finishSession();
                return ;
            }
            phaseIndex = 0;
        }
        enterPhase();
    }

    function tick() {
        if (paused)
            return ;

        var now = Date.now();
        phaseElapsedMs = now - phaseStartedAt;
        sessionElapsedMs = now - sessionStartedAt - pauseAccumulatedMs;
        if (!activePreset.power && sessionElapsedMs >= durationSec * 1000) {
            finishSession();
            return ;
        }
        if (phaseElapsedMs >= phaseSeconds * 1000)
            advancePhase();

    }

    function togglePause() {
        if (paused) {
            var delta = Date.now() - pausedAt;
            phaseStartedAt += delta;
            pauseAccumulatedMs += delta;
            paused = false;
        } else {
            pausedAt = Date.now();
            paused = true;
        }
    }

    function stopSession() {
        ticker.stop();
        paused = false;
        screen = "setup";
    }

    function finishSession() {
        ticker.stop();
        paused = false;
        screen = "done";
        orbScale = 0.18;
    }

    moduleName: "still"
    ipcTarget: "still"
    manageIpc: false

    Timer {
        id: ticker

        interval: 50
        repeat: true
        onTriggered: root.tick()
    }

    KeyboardPanel {
        id: panel

        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: panel.fittedContentWidth(Style.space(390))
        contentHeight: panel.fittedContentHeight(Style.space(540), Style.space(620))

        PanelKeyCatcher {
            id: keyCatcher

            anchors.fill: parent
            onCloseRequested: root.close()
            onTabRequested: function(direction) {
                root.switchPanel(direction);
            }
            onActivateRequested: {
                if (root.screen === "setup")
                    root.requestStart();
                else if (root.screen === "warning")
                    root.startSession();
                else if (root.screen === "running")
                    root.togglePause();
                else
                    root.screen = "setup";
            }

            Column {
                anchors.fill: parent
                spacing: Style.space(14)

                Row {
                    width: parent.width

                    Text {
                        text: "still"
                        color: root.foreground
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.heading
                        font.weight: Font.Medium
                    }

                    Item {
                        width: parent.width - 74
                        height: 1
                    }

                    Text {
                        text: root.screen === "running" ? "×" : ""
                        color: root.foreground
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.heading

                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -8
                            onClicked: root.stopSession()
                        }

                    }

                }

                Item {
                    width: parent.width
                    height: Style.space(292)

                    Column {
                        visible: root.screen === "setup"
                        anchors.fill: parent
                        spacing: Style.space(14)

                        Text {
                            text: "How do you want to feel?"
                            color: root.foreground
                            opacity: 0.62
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Row {
                            width: parent.width
                            spacing: Style.space(6)

                            Repeater {
                                model: Protocols.INTENTIONS

                                Rectangle {
                                    required property var modelData

                                    width: (parent.width - Style.space(18)) / 4
                                    height: Style.space(38)
                                    radius: Style.cornerRadius
                                    color: root.intent === modelData.id ? Color.accent : "transparent"
                                    border.width: 1
                                    border.color: root.intent === modelData.id ? Color.accent : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.18)

                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.label
                                        color: root.intent === modelData.id ? Color.background : root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: root.intent = modelData.id
                                    }

                                }

                            }

                        }

                        Column {
                            width: parent.width
                            spacing: Style.space(3)

                            Text {
                                text: root.activePreset.name
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.title
                            }

                            Text {
                                text: root.activePreset.detail
                                color: root.foreground
                                opacity: 0.5
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.bodySmall
                            }

                        }

                        Row {
                            spacing: Style.space(6)

                            Repeater {
                                model: Protocols.DIFFICULTIES

                                Rectangle {
                                    required property string modelData
                                    required property int index

                                    width: Style.space(92)
                                    height: Style.space(34)
                                    radius: Style.cornerRadius
                                    color: root.difficulty === index ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.18) : "transparent"
                                    border.width: 1
                                    border.color: root.difficulty === index ? Color.accent : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)

                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: root.difficulty = index
                                    }

                                }

                            }

                        }

                        Row {
                            spacing: Style.space(6)

                            Repeater {
                                model: ["30 sec", "2 min", "5 min"]

                                Rectangle {
                                    required property string modelData
                                    required property int index

                                    visible: !(root.intent === "energy" && root.difficulty === 2 && index === 0)
                                    width: Style.space(92)
                                    height: Style.space(34)
                                    radius: Style.cornerRadius
                                    color: root.durationIndex === index ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.18) : "transparent"
                                    border.width: 1
                                    border.color: root.durationIndex === index ? Color.accent : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.14)

                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData
                                        color: root.foreground
                                        font.family: root.fontFamily
                                        font.pixelSize: Style.font.bodySmall
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: root.durationIndex = index
                                    }

                                }

                            }

                        }

                    }

                    Column {
                        visible: root.screen === "warning"
                        anchors.centerIn: parent
                        width: parent.width
                        spacing: Style.space(12)

                        Text {
                            width: parent.width
                            text: "Power breathing"
                            horizontalAlignment: Text.AlignHCenter
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.title
                        }

                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            horizontalAlignment: Text.AlignHCenter
                            text: "Sit or lie down. Never practice while driving, standing, or in or near water. Stop if you feel unwell. Retention is never a contest."
                            color: root.foreground
                            opacity: 0.7
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.body
                        }

                        Text {
                            width: parent.width
                            text: "Press Enter or click below to continue"
                            horizontalAlignment: Text.AlignHCenter
                            color: root.foreground
                            opacity: 0.45
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                    }

                    Item {
                        visible: root.screen === "running"
                        anchors.fill: parent

                        Rectangle {
                            id: halo

                            anchors.centerIn: parent
                            width: Style.space(190)
                            height: width
                            radius: width / 2
                            scale: root.orbScale
                            color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.12)
                            border.width: Style.space(2)
                            border.color: Color.accent

                            Behavior on scale {
                                NumberAnimation {
                                    duration: Math.max(180, root.phaseSeconds * 1000)
                                    easing.type: Easing.InOutSine
                                }

                            }

                        }

                        Column {
                            anchors.centerIn: parent
                            spacing: Style.space(4)

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: Protocols.phaseLabel(root.phaseType)
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.title
                            }

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: root.phaseRemaining
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.displayLarge
                            }

                        }

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            text: root.activePreset.power ? ("round sequence · " + (root.phaseIndex + 1) + "/" + root.phases.length) : (Math.floor(root.sessionRemaining / 60) + ":" + String(root.sessionRemaining % 60).padStart(2, "0"))
                            color: root.foreground
                            opacity: 0.52
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.body
                        }

                    }

                    Column {
                        visible: root.screen === "done"
                        anchors.centerIn: parent
                        spacing: Style.space(8)

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "return gently"
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.title
                        }

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: root.activePreset.name
                            color: root.foreground
                            opacity: 0.45
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                    }

                }

                Rectangle {
                    width: parent.width
                    height: Style.space(44)
                    radius: Style.cornerRadius
                    color: Color.accent

                    Text {
                        anchors.centerIn: parent
                        text: root.screen === "setup" ? "Begin" : root.screen === "warning" ? "I’m seated — continue" : root.screen === "running" ? (root.paused ? "Resume" : "Pause") : "Again"
                        color: Color.background
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.body
                        font.weight: Font.Medium
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (root.screen === "setup")
                                root.requestStart();
                            else if (root.screen === "warning")
                                root.startSession();
                            else if (root.screen === "running")
                                root.togglePause();
                            else
                                root.screen = "setup";
                        }
                    }

                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.screen === "setup" ? "enter to begin · esc to close" : "esc to close"
                    color: root.foreground
                    opacity: 0.35
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                }

            }

        }

    }

}

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
    property string screen: "setup" // setup | running | done
    property string intent: "calm"
    property int difficulty: 1
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
    readonly property var activePhase: phases.length ? phases[Math.min(phaseIndex, phases.length - 1)] : ({ type: "inhale", seconds: 4 })
    readonly property string phaseType: activePhase.type
    readonly property real phaseSeconds: activePhase.seconds
    readonly property bool holding: Protocols.isHoldPhase(phaseType)
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

    function startSession() {
        phases = activePreset.phases;
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

        var sound = Protocols.phaseSound(type);
        if (sound === "none")
            return ;

        var source = sound + ".ogg";
        var base = Qt.resolvedUrl("sounds/" + source).toString().replace(/^file:\/\//, "");
        bar.run("pw-play " + shellQuote(base));
    }

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function advancePhase() {
        phaseIndex++;
        if (phaseIndex >= phases.length) {
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
        if (sessionElapsedMs >= durationSec * 1000) {
            finishSession();
            return ;
        }
        if (phaseElapsedMs >= phaseSeconds * 1000)
            advancePhase();

    }

    function togglePause() {
        if (paused) {
            var delta = Date.now() - pausedAt;
            pauseAccumulatedMs += delta;
            paused = false;
            phaseIndex = 0;
            enterPhase();
        } else {
            pausedAt = Date.now();
            paused = true;
            orbScale = 0.18;
        }
    }

    function primarySessionAction() {
        if (holding && !paused)
            advancePhase();
        else
            togglePause();
    }

    function stopSession() {
        ticker.stop();
        paused = false;
        screen = "setup";
        orbScale = 0.18;
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

    CenteredKeyboardPanel {
        id: panel

        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: panel.fittedContentWidth(Style.space(520))
        contentHeight: panel.fittedContentHeight(Style.space(600), Style.space(700))

        PanelKeyCatcher {
            id: keyCatcher

            anchors.fill: parent
            onCloseRequested: root.close()
            onTabRequested: function(direction) {
                root.switchPanel(direction);
            }
            onActivateRequested: {
                if (root.screen === "setup")
                    root.startSession();
                else if (root.screen === "running")
                    root.primarySessionAction();
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
                    height: Style.space(350)

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

                                    width: (parent.width - Style.space(6) * (Protocols.INTENTIONS.length - 1)) / Protocols.INTENTIONS.length
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
                                width: parent.width
                                text: root.activePreset.basis
                                color: Color.accent
                                opacity: 0.78
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                                font.weight: Font.Medium
                                elide: Text.ElideRight
                            }

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

                            Text {
                                width: parent.width
                                text: root.activePreset.benefit
                                color: root.foreground
                                opacity: 0.68
                                wrapMode: Text.WordWrap
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.bodySmall
                            }

                            Text {
                                width: parent.width
                                text: root.activePreset.cue
                                color: root.foreground
                                opacity: 0.45
                                wrapMode: Text.WordWrap
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
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
                                text: Protocols.phaseLabel(root.paused ? "normal" : root.phaseType)
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.title
                            }

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: root.paused ? "·" : root.phaseRemaining
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.displayLarge
                            }

                            Text {
                                width: Style.space(360)
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: root.paused ? "Resume starts again with an inhale." : root.activePreset.cue
                                color: root.foreground
                                opacity: 0.45
                                wrapMode: Text.WordWrap
                                horizontalAlignment: Text.AlignHCenter
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                        }

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            text: Math.floor(root.sessionRemaining / 60) + ":" + String(root.sessionRemaining % 60).padStart(2, "0")
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
                            text: "breathe normally"
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.title
                        }

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: root.activePreset.name + " · session complete"
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
                        text: root.screen === "setup"
                            ? "Begin"
                            : (root.screen === "running"
                                ? (root.paused ? "Resume" : (root.holding ? "Skip hold · breathe normally" : "Pause · breathe normally"))
                                : "Again")
                        color: Color.background
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.body
                        font.weight: Font.Medium
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (root.screen === "setup")
                                root.startSession();
                            else if (root.screen === "running")
                                root.primarySessionAction();
                            else
                                root.screen = "setup";
                        }
                    }

                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.screen === "setup"
                        ? "wellness only · breathe gently · stop for dizziness, tingling, breathlessness, pain, or panic"
                        : "esc to close"
                    wrapMode: Text.WordWrap
                    color: root.foreground
                    opacity: 0.35
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                }

            }

        }

    }

}

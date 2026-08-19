pragma ComponentBehavior: Bound

import "Protocols.js" as Protocols
import QtQuick
import qs.Commons
import qs.Ui

Panel {
    id: root

    property var anchorItem: null
    property var hostWidget: null
    property var session: null
    property int cursorSection: 2
    property int completeAction: 0

    readonly property var barIdentity: hostWidget || root
    readonly property string viewState: session ? session.sessionState : "idle"
    readonly property bool configuring: viewState === "idle"
    readonly property bool countingDown: viewState === "countdown"
    readonly property bool breathing: viewState === "running" || viewState === "paused"
    readonly property bool paused: viewState === "paused"
    readonly property bool complete: viewState === "complete"
    readonly property var visiblePreset: session
        ? (configuring ? session.selectedPreset : session.activePreset)
        : Protocols.technique("coherent")
    readonly property color foreground: Color.popups.text
    readonly property color accent: Color.accent
    readonly property color muted: Color.muted
    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

    function open() {
        controller.show()
    }

    function close() {
        controller.hide()
    }

    function toggle() {
        opened ? close() : open()
    }

    function switchPanel(direction) {
        if (bar && typeof bar.switchPanelFrom === "function")
            return bar.switchPanelFrom(barIdentity, direction)
        return false
    }

    function wrap(index, count) {
        return (index % count + count) % count
    }

    function moveCursor(dx, dy) {
        if (configuring && session) {
            if (dy !== 0) {
                cursorSection = wrap(cursorSection + (dy > 0 ? 1 : -1), 3)
                return
            }
            if (dx === 0 || cursorSection === 2)
                return

            var direction = dx > 0 ? 1 : -1
            if (cursorSection === 0) {
                var selectedTechnique = Protocols.techniqueIndex(session.selectedTechniqueId)
                var nextTechnique = wrap(selectedTechnique + direction, Protocols.TECHNIQUES.length)
                session.selectTechnique(Protocols.TECHNIQUES[nextTechnique].id)
            } else if (cursorSection === 1) {
                session.selectDuration(Protocols.DURATIONS[wrap(session.selectedDurationIndex + direction, Protocols.DURATIONS.length)])
            }
            return
        }

        if (complete && dx !== 0)
            completeAction = wrap(completeAction + (dx > 0 ? 1 : -1), 2)
    }

    function activateCursor() {
        if (!session)
            return

        if (configuring) {
            if (cursorSection === 2)
                session.startSession()
            else
                cursorSection++
            return
        }

        if (countingDown) {
            session.cancelCountdown()
            return
        }

        if (breathing) {
            session.primaryAction()
            return
        }

        if (complete) {
            if (completeAction === 0)
                session.repeatSession()
            else {
                session.endSession()
                close()
            }
        }
    }

    function handleTextKey(text) {
        if (!session)
            return

        var key = String(text || "").toLowerCase()
        if (key === "s" && configuring)
            session.startSession()
        else if (key === "p" && breathing)
            session.togglePause()
        else if (key === "e" && (countingDown || breathing))
            session.endSession()
        else if (key === "r" && complete)
            session.repeatSession()
    }

    moduleName: "still"
    ipcTarget: "still"
    manageIpc: false

    onViewStateChanged: {
        if (configuring)
            cursorSection = 2
        if (complete)
            completeAction = 0
    }

    CenteredKeyboardPanel {
        id: panel

        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: panel.fittedContentWidth(Style.space(540))
        contentHeight: panel.fittedContentHeight(Style.space(620), Style.space(720))

        PanelKeyCatcher {
            id: keyCatcher

            anchors.fill: parent
            onCloseRequested: root.close()
            onTabRequested: function(direction) {
                root.switchPanel(direction)
            }
            onMoveRequested: function(dx, dy) {
                root.moveCursor(dx, dy)
            }
            onActivateRequested: root.activateCursor()
            onTextKey: function(text) {
                root.handleTextKey(text)
            }

            Column {
                anchors.fill: parent
                spacing: Style.space(12)

                Item {
                    width: parent.width
                    height: Style.space(28)

                    Text {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "still"
                        color: root.foreground
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.heading
                        font.weight: Font.Medium
                    }

                    Text {
                        anchors.right: closeMark.left
                        anchors.rightMargin: Style.space(14)
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.countingDown ? "get ready"
                            : (root.breathing ? (root.paused ? "paused" : root.visiblePreset.name) : "")
                        color: root.muted
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                    }

                    Text {
                        id: closeMark

                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: "×"
                        color: root.foreground
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.heading

                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -Style.space(8)
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.close()
                        }
                    }
                }

                Item {
                    width: parent.width
                    height: Style.space(420)

                    Column {
                        anchors.fill: parent
                        visible: root.configuring
                        spacing: Style.space(11)

                        Text {
                            text: "Choose a breathing pattern"
                            color: root.foreground
                            opacity: 0.62
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                        }

                        Row {
                            id: techniqueRow

                            width: parent.width
                            height: Style.space(38)
                            spacing: Style.space(6)

                            Repeater {
                                model: Protocols.TECHNIQUES

                                delegate: Button {
                                    required property var modelData
                                    required property int index

                                    width: (techniqueRow.width - techniqueRow.spacing * (Protocols.TECHNIQUES.length - 1)) / Protocols.TECHNIQUES.length
                                    height: techniqueRow.height
                                    text: modelData.shortName
                                    foreground: root.foreground
                                    accent: root.accent
                                    fontFamily: root.fontFamily
                                    fontSize: Style.font.bodySmall
                                    selected: root.session ? root.session.selectedTechniqueId === modelData.id : index === 0
                                    hasCursor: root.cursorSection === 0 && selected
                                    bordered: true
                                    onClicked: if (root.session) root.session.selectTechnique(modelData.id)
                                    onHovered: function(hovered) {
                                        if (hovered) root.cursorSection = 0
                                    }
                                }
                            }
                        }

                        Row {
                            width: parent.width
                            height: Style.space(210)
                            spacing: Style.space(16)

                            Item {
                                width: Style.space(185)
                                height: parent.height

                                BreathBloom {
                                    anchors.centerIn: parent
                                    width: Math.min(parent.width, parent.height)
                                    height: width
                                    preview: true
                                    reducedMotion: root.session ? root.session.reducedMotion : false
                                    accent: root.accent
                                    foreground: root.foreground
                                    muted: root.muted
                                }
                            }

                            Column {
                                width: parent.width - Style.space(201)
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: Style.space(4)

                                Text {
                                    width: parent.width
                                    text: root.visiblePreset.basis
                                    color: root.accent
                                    opacity: 0.82
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.caption
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: root.visiblePreset.name
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.title
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: root.visiblePreset.detail
                                    color: root.foreground
                                    opacity: 0.5
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.bodySmall
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: root.visiblePreset.benefit
                                    color: root.foreground
                                    opacity: 0.7
                                    wrapMode: Text.WordWrap
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.bodySmall
                                }

                                Text {
                                    width: parent.width
                                    text: root.visiblePreset.cue
                                    color: root.foreground
                                    opacity: 0.45
                                    wrapMode: Text.WordWrap
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.caption
                                }
                            }
                        }

                        Row {
                            id: durationRow

                            width: parent.width
                            height: Style.space(36)
                            spacing: Style.space(6)

                            Text {
                                width: Style.space(54)
                                anchors.verticalCenter: parent.verticalCenter
                                text: "time"
                                color: root.muted
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.caption
                            }

                            Repeater {
                                model: Protocols.DURATIONS

                                delegate: Button {
                                    required property int modelData
                                    required property int index

                                    width: (durationRow.width - Style.space(54) - durationRow.spacing * Protocols.DURATIONS.length) / Protocols.DURATIONS.length
                                    height: durationRow.height
                                    text: Protocols.durationLabel(index)
                                    foreground: root.foreground
                                    accent: root.accent
                                    fontFamily: root.fontFamily
                                    fontSize: Style.font.bodySmall
                                    selected: root.session ? root.session.selectedDurationIndex === index : index === 1
                                    hasCursor: root.cursorSection === 1 && selected
                                    bordered: true
                                    onClicked: if (root.session) root.session.selectDuration(modelData)
                                    onHovered: function(hovered) {
                                        if (hovered) root.cursorSection = 1
                                    }
                                }
                            }
                        }
                    }

                    Column {
                        anchors.centerIn: parent
                        width: parent.width
                        visible: root.countingDown
                        spacing: Style.space(12)

                        Text {
                            width: parent.width
                            text: root.visiblePreset.name.toUpperCase()
                            color: root.muted
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            font.letterSpacing: Style.spaceReal(1)
                            horizontalAlignment: Text.AlignHCenter
                        }

                        Item {
                            width: parent.width
                            height: Style.space(285)

                            BreathBloom {
                                anchors.centerIn: parent
                                width: Math.min(parent.width, parent.height)
                                height: width
                                level: root.session ? root.session.breathLevel : 0.18
                                active: true
                                reducedMotion: root.session ? root.session.reducedMotion : false
                                phaseType: "normal"
                                accent: root.accent
                                foreground: root.foreground
                                muted: root.muted
                            }

                            Text {
                                anchors.centerIn: parent
                                text: root.session ? String(root.session.countdownNumber) : "3"
                                color: root.foreground
                                font.family: root.fontFamily
                                font.pixelSize: Style.font.displayLarge * 1.7
                                font.weight: Font.DemiBold

                                Behavior on opacity {
                                    NumberAnimation {
                                        duration: 120
                                    }
                                }
                            }
                        }

                        Text {
                            width: parent.width
                            text: "GET READY"
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.heading
                            font.weight: Font.Medium
                            font.letterSpacing: Style.spaceReal(1)
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    Item {
                        anchors.fill: parent
                        visible: root.breathing

                        Text {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            width: parent.width * 0.72
                            text: root.visiblePreset.name.toUpperCase()
                            color: root.muted
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                            font.letterSpacing: Style.spaceReal(0.8)
                            elide: Text.ElideRight
                        }

                        Text {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            text: root.session ? root.session.sessionRemainingText : "0:00"
                            color: root.muted
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.caption
                        }

                        Item {
                            anchors.top: parent.top
                            anchors.topMargin: Style.space(24)
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: parent.width
                            height: Style.space(330)
                            clip: true

                            BreathBloom {
                                anchors.centerIn: parent
                                width: Math.min(parent.width, parent.height)
                                height: width
                                level: root.session ? root.session.breathLevel : 0.18
                                active: root.viewState === "running"
                                reducedMotion: root.session ? root.session.reducedMotion : false
                                phaseType: root.session ? root.session.phaseType : "normal"
                                accent: root.accent
                                foreground: root.foreground
                                muted: root.muted
                            }

                            Column {
                                anchors.centerIn: parent
                                width: Math.min(parent.width - Style.space(80), Style.space(360))
                                spacing: Style.space(3)

                                Text {
                                    width: parent.width
                                    text: root.paused ? "breathe normally" : (root.session ? root.session.phaseLabel : "")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.title
                                    font.weight: Font.Medium
                                    horizontalAlignment: Text.AlignHCenter
                                }

                                Text {
                                    width: parent.width
                                    text: root.paused ? "·" : (root.session ? root.session.phaseSecondsRemaining : "")
                                    color: root.foreground
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.displayLarge
                                    horizontalAlignment: Text.AlignHCenter
                                }

                                Text {
                                    width: parent.width
                                    text: root.paused ? "Resume begins again with an inhale." : root.visiblePreset.cue
                                    color: root.foreground
                                    opacity: 0.48
                                    wrapMode: Text.WordWrap
                                    horizontalAlignment: Text.AlignHCenter
                                    font.family: root.fontFamily
                                    font.pixelSize: Style.font.caption
                                }
                            }
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: Style.space(3)
                            radius: height / 2
                            color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.1)

                            Rectangle {
                                width: parent.width * (root.session ? root.session.sessionProgress : 0)
                                height: parent.height
                                radius: parent.radius
                                color: root.accent

                                Behavior on width {
                                    NumberAnimation {
                                        duration: 90
                                        easing.type: Easing.OutSine
                                    }
                                }
                            }
                        }
                    }

                    Column {
                        anchors.centerIn: parent
                        width: parent.width
                        visible: root.complete
                        spacing: Style.space(12)

                        Item {
                            width: parent.width
                            height: Style.space(280)

                            BreathBloom {
                                anchors.centerIn: parent
                                width: Math.min(parent.width, parent.height)
                                height: width
                                level: 0.46
                                reducedMotion: root.session ? root.session.reducedMotion : false
                                accent: root.accent
                                foreground: root.foreground
                                muted: root.muted
                            }
                        }

                        Text {
                            width: parent.width
                            text: "breathe normally"
                            color: root.foreground
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.title
                            font.weight: Font.Medium
                            horizontalAlignment: Text.AlignHCenter
                        }

                        Text {
                            width: parent.width
                            text: root.visiblePreset.name + " · "
                                + (root.session ? root.session.sessionElapsedText : "0:00")
                                + " · session complete"
                            color: root.muted
                            font.family: root.fontFamily
                            font.pixelSize: Style.font.bodySmall
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }

                Item {
                    width: parent.width
                    height: Style.space(44)

                    Button {
                        anchors.fill: parent
                        visible: root.configuring
                        text: "BEGIN"
                        iconText: ">"
                        foreground: root.foreground
                        accent: root.accent
                        fontFamily: root.fontFamily
                        selected: true
                        hasCursor: root.cursorSection === 2
                        bordered: true
                        onClicked: if (root.session) root.session.startSession()
                        onHovered: function(hovered) {
                            if (hovered) root.cursorSection = 2
                        }
                    }

                    Button {
                        anchors.fill: parent
                        visible: root.countingDown
                        text: "CANCEL"
                        foreground: root.foreground
                        accent: root.accent
                        fontFamily: root.fontFamily
                        bordered: true
                        onClicked: if (root.session) root.session.cancelCountdown()
                    }

                    Row {
                        id: runningActions

                        anchors.fill: parent
                        visible: root.breathing
                        spacing: Style.space(8)

                        Button {
                            id: primaryActionButton

                            width: runningActions.width * 0.72
                            height: runningActions.height
                            text: root.paused ? "RESUME"
                                : (root.session && root.session.holding
                                    ? (root.session.phaseType === "pauseOut"
                                        ? "SKIP PAUSE · BREATHE NORMALLY"
                                        : "SKIP HOLD · BREATHE NORMALLY")
                                    : "PAUSE · BREATHE NORMALLY")
                            foreground: root.foreground
                            accent: root.accent
                            fontFamily: root.fontFamily
                            fontSize: Style.font.bodySmall
                            selected: true
                            hasCursor: true
                            bordered: true
                            onClicked: if (root.session) root.session.primaryAction()
                        }

                        Button {
                            width: runningActions.width - primaryActionButton.width - runningActions.spacing
                            height: runningActions.height
                            text: "END"
                            foreground: root.foreground
                            accent: root.accent
                            fontFamily: root.fontFamily
                            bordered: true
                            onClicked: if (root.session) root.session.endSession()
                        }
                    }

                    Row {
                        id: completeActions

                        anchors.fill: parent
                        visible: root.complete
                        spacing: Style.space(8)

                        Button {
                            id: againButton

                            width: (completeActions.width - completeActions.spacing) * 0.65
                            height: completeActions.height
                            text: "AGAIN"
                            foreground: root.foreground
                            accent: root.accent
                            fontFamily: root.fontFamily
                            selected: true
                            hasCursor: root.completeAction === 0
                            bordered: true
                            onClicked: if (root.session) root.session.repeatSession()
                            onHovered: function(hovered) {
                                if (hovered) root.completeAction = 0
                            }
                        }

                        Button {
                            width: completeActions.width - againButton.width - completeActions.spacing
                            height: completeActions.height
                            text: "DONE"
                            foreground: root.foreground
                            accent: root.accent
                            fontFamily: root.fontFamily
                            hasCursor: root.completeAction === 1
                            bordered: true
                            onClicked: {
                                if (root.session) root.session.endSession()
                                root.close()
                            }
                            onHovered: function(hovered) {
                                if (hovered) root.completeAction = 1
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.configuring
                        ? "wellness only · pauses are optional · stop for dizziness, tingling, breathlessness, pain, or panic"
                        : (root.countingDown
                            ? "3 · 2 · 1 · session time begins with the first inhale"
                            : (root.breathing
                                ? "p pause/resume · e end · esc hides while the session continues"
                                : "breathe normally before continuing"))
                    wrapMode: Text.WordWrap
                    color: root.foreground
                    opacity: 0.36
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                }
            }
        }
    }
}

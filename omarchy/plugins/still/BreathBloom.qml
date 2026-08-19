pragma ComponentBehavior: Bound

import QtQuick
import qs.Commons

Item {
    id: root

    property real level: 0.18
    property bool active: false
    property bool preview: false
    property bool reducedMotion: false
    property real visualScale: 1
    property string phaseType: "normal"
    property color accent: Color.accent
    property color foreground: Color.foreground
    property color muted: Color.muted

    property real previewLevel: 0.28
    property real holdPulse: 0

    readonly property bool holding: phaseType === "holdIn" || phaseType === "holdOut"
    readonly property real displayLevel: Math.max(0.18, Math.min(1, preview ? previewLevel : level))
    readonly property real pulseAmount: reducedMotion || !holding ? 0 : holdPulse * 0.01
    readonly property real bloomScale: reducedMotion
        ? 0.86 + displayLevel * 0.08
        : 0.72 + displayLevel * 0.24 + pulseAmount
    readonly property real bloomRotation: reducedMotion ? 0 : -7 + displayLevel * 14 + (holding ? holdPulse : 0)
    readonly property real side: Math.min(width, height)

    SequentialAnimation on previewLevel {
        running: root.preview && root.visible && !root.reducedMotion
        loops: Animation.Infinite

        NumberAnimation {
            from: 0.18
            to: 1
            duration: 5450
            easing.type: Easing.InOutSine
        }

        NumberAnimation {
            from: 1
            to: 0.18
            duration: 5450
            easing.type: Easing.InOutSine
        }
    }

    SequentialAnimation on holdPulse {
        running: root.active && root.visible && root.holding && !root.reducedMotion
        loops: Animation.Infinite

        NumberAnimation {
            from: 0
            to: 1
            duration: 1300
            easing.type: Easing.InOutSine
        }

        NumberAnimation {
            from: 1
            to: 0
            duration: 1300
            easing.type: Easing.InOutSine
        }
    }

    Item {
        id: bloom

        anchors.centerIn: parent
        width: root.side
        height: root.side
        scale: root.bloomScale * root.visualScale
        rotation: root.bloomRotation

        Behavior on scale {
            enabled: root.reducedMotion

            NumberAnimation {
                duration: 420
                easing.type: Easing.InOutSine
            }
        }

        Rectangle {
            anchors.centerIn: parent
            width: parent.width * (0.26 + root.displayLevel * 0.08)
            height: width
            radius: width / 2
            color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.08)
            scale: 1.12
        }

        Repeater {
            model: 10

            delegate: Item {
                id: outerPetal

                required property int index

                anchors.fill: parent
                rotation: index * 36

                Rectangle {
                    readonly property real orbit: root.reducedMotion
                        ? bloom.width * 0.075
                        : bloom.width * (0.018 + root.displayLevel * 0.14)

                    x: bloom.width / 2 - width / 2
                    y: bloom.height / 2 - height / 2 - orbit
                    width: bloom.width * 0.205
                    height: bloom.width * (0.42 - root.displayLevel * 0.045)
                    radius: width / 2
                    color: outerPetal.index % 3 === 0 ? root.foreground : root.accent
                    opacity: outerPetal.index % 2 === 0 ? 0.17 : 0.12
                    scale: 0.86 + root.displayLevel * 0.14
                    transformOrigin: Item.Center
                }
            }
        }

        Item {
            anchors.fill: parent
            rotation: 18 - root.bloomRotation * 0.42
            scale: 0.8 + root.displayLevel * 0.08

            Repeater {
                model: 10

                delegate: Item {
                    id: innerPetal

                    required property int index

                    anchors.fill: parent
                    rotation: index * 36

                    Rectangle {
                        readonly property real orbit: root.reducedMotion
                            ? bloom.width * 0.06
                            : bloom.width * (0.012 + root.displayLevel * 0.105)

                        x: bloom.width / 2 - width / 2
                        y: bloom.height / 2 - height / 2 - orbit
                        width: bloom.width * 0.17
                        height: bloom.width * 0.35
                        radius: width / 2
                        color: innerPetal.index % 2 === 0 ? root.muted : root.accent
                        opacity: innerPetal.index % 2 === 0 ? 0.13 : 0.1
                    }
                }
            }
        }

        Rectangle {
            anchors.centerIn: parent
            width: parent.width * (0.1 + root.displayLevel * 0.035)
            height: width
            radius: width / 2
            color: root.foreground
            opacity: 0.32

            Rectangle {
                anchors.centerIn: parent
                width: parent.width * 0.54
                height: width
                radius: width / 2
                color: root.accent
                opacity: 0.86
            }
        }
    }
}

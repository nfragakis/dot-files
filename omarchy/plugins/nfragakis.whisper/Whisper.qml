import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire
import Quickshell.Wayland
import qs.Commons
import qs.Ui

Item {
  id: root

  property string mode: "idle"
  property string backendAction: ""
  property string configuredSourceName: ""
  property var samples: []
  property double recordingStartedAt: 0
  property int elapsedSeconds: 0

  readonly property int sampleCount: 42
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME")
    || Quickshell.env("HOME") + "/.config"
  readonly property var nodes: Pipewire.nodes ? Pipewire.nodes.values : []
  readonly property var audioSources: {
    var result = []
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i]
      if (node && !node.isSink && !node.isStream) result.push(node)
    }
    return result
  }
  readonly property var captureSource: {
    if (configuredSourceName !== "") {
      for (var i = 0; i < audioSources.length; i++) {
        if (String(audioSources[i].name || "") === configuredSourceName)
          return audioSources[i]
      }
    }
    return Pipewire.defaultAudioSource
  }
  readonly property string backendPath: Qt.resolvedUrl("toggle-recording.sh")
    .toString().replace(/^file:\/\//, "")
  readonly property string elapsedLabel: {
    var minutes = Math.floor(elapsedSeconds / 60)
    var seconds = elapsedSeconds % 60
    return minutes + ":" + (seconds < 10 ? "0" : "") + seconds
  }

  function resetWaveform() {
    var quiet = []
    for (var i = 0; i < sampleCount; i++) quiet.push(0.035)
    samples = quiet
  }

  function sampleMicrophone() {
    var raw = Math.max(0, Math.min(1, Number(peakMonitor.peak) || 0))
    // Compress the meter slightly so ordinary speech remains visible without
    // flattening the difference between quiet and emphatic words.
    var visual = Math.max(0.035, Math.min(1, Math.sqrt(raw)))
    var next = samples.slice(Math.max(0, samples.length - sampleCount + 1))
    next.push(visual)
    samples = next
  }

  function beginRecording() {
    if (backend.running || mode === "recording") return false
    resetWaveform()
    elapsedSeconds = 0
    recordingStartedAt = Date.now()
    mode = "recording"
    runBackend("start")
    return true
  }

  function finishRecording() {
    if (backend.running || mode !== "recording") return false
    mode = "transcribing"
    runBackend("stop")
    return true
  }

  function toggleRecording() {
    if (mode === "recording") return finishRecording()
    if (mode === "idle") return beginRecording()
    return false
  }

  function runBackend(action) {
    backendAction = action
    backend.command = [backendPath, action]
    backend.running = true
  }

  function applyBackendStatus(status) {
    var next = String(status || "").trim()
    if (next === "recording") {
      if (mode !== "recording") {
        resetWaveform()
        elapsedSeconds = 0
        recordingStartedAt = Date.now()
      }
      mode = "recording"
    } else if (!backend.running) {
      mode = "idle"
    }
  }

  Component.onCompleted: {
    resetWaveform()
    statusProbe.running = true
  }

  PwObjectTracker { objects: root.audioSources }

  PwNodePeakMonitor {
    id: peakMonitor
    node: root.captureSource
    enabled: root.mode === "recording" && !!root.captureSource
  }

  FileView {
    id: sourceConfig
    path: root.configHome + "/whisper-stt/audio_device"
    watchChanges: true
    printErrors: false
    onLoaded: root.configuredSourceName = String(text()).trim()
    onLoadFailed: root.configuredSourceName = ""
    onFileChanged: reload()
  }

  Process {
    id: statusProbe
    command: [root.backendPath, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyBackendStatus(text)
    }
  }

  Process {
    id: backend
    onExited: function(exitCode) {
      if (root.backendAction === "start" && exitCode === 0) {
        root.mode = "recording"
      } else {
        root.mode = "idle"
      }
      root.backendAction = ""
    }
  }

  Timer {
    interval: 55
    running: root.mode === "recording"
    repeat: true
    onTriggered: root.sampleMicrophone()
  }

  Timer {
    interval: 250
    running: root.mode === "recording"
    repeat: true
    onTriggered: root.elapsedSeconds = Math.floor((Date.now() - root.recordingStartedAt) / 1000)
  }

  IpcHandler {
    target: "whisper-stt"

    function toggle(): string {
      return root.toggleRecording() ? root.mode : "busy"
    }

    function start(): string {
      return root.beginRecording() ? "recording" : root.mode
    }

    function stop(): string {
      return root.finishRecording() ? "transcribing" : root.mode
    }

    function status(): string {
      return root.mode
    }
  }

  PanelWindow {
    id: panel
    visible: root.mode !== "idle"
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "nfragakis-whisper"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    BorderSurface {
      id: card
      width: Math.min(parent.width - Style.space(32), Style.space(430))
      height: card.borderTop + Style.space(16) + content.implicitHeight
        + Style.space(16) + card.borderBottom
      anchors.horizontalCenter: parent.horizontalCenter
      anchors.bottom: parent.bottom
      anchors.bottomMargin: Style.space(67)
      color: Util.alpha(Color.background, 0.96)
      borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border,
        Math.max(1, Style.space(2)))
      radius: Style.cornerRadius
      opacity: root.mode !== "idle" ? 1 : 0
      scale: root.mode !== "idle" ? 1 : 0.96

      Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
      Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutBack } }

      Column {
        id: content
        anchors.fill: parent
        anchors.margins: Style.space(16)
        spacing: Style.space(9)

        Item {
          width: parent.width
          height: Style.font.title + Style.space(4)

          Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.mode === "recording" ? "Listening" : "Transcribing…"
            textFormat: Text.PlainText
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.mode === "recording" ? root.elapsedLabel : ""
            textFormat: Text.PlainText
            color: Util.alpha(Color.popups.text, 0.72)
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            font.bold: true
          }
        }

        Item {
          id: waveform
          width: parent.width
          height: Style.space(46)

          Row {
            anchors.centerIn: parent
            spacing: Style.space(4)

            Repeater {
              model: root.sampleCount

              Rectangle {
                required property int index
                readonly property real level: Number(root.samples[index] || 0.035)
                width: Math.max(2, Style.space(3))
                height: Math.max(width, waveform.height * level)
                anchors.verticalCenter: parent.verticalCenter
                radius: width / 2
                color: Color.accent
                opacity: root.mode === "recording"
                  ? 0.48 + 0.52 * level
                  : 0.28

                Behavior on height {
                  NumberAnimation { duration: 70; easing.type: Easing.OutCubic }
                }
                Behavior on opacity { NumberAnimation { duration: 120 } }
              }
            }
          }

          Rectangle {
            visible: root.mode === "transcribing"
            width: Style.space(7)
            height: width
            radius: width / 2
            anchors.centerIn: parent
            color: Color.accent

            SequentialAnimation on opacity {
              running: root.mode === "transcribing"
              loops: Animation.Infinite
              NumberAnimation { from: 0.25; to: 1; duration: 500; easing.type: Easing.InOutSine }
              NumberAnimation { from: 1; to: 0.25; duration: 500; easing.type: Easing.InOutSine }
            }
          }
        }

        Text {
          width: parent.width
          horizontalAlignment: Text.AlignHCenter
          text: root.mode === "recording"
            ? "Press Super + Shift + L to finish"
            : "Your transcript will be pasted at the cursor"
          textFormat: Text.PlainText
          color: Util.alpha(Color.popups.text, 0.62)
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}

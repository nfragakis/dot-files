import QtQuick
import Quickshell
import Quickshell.Io

// Keeps the SuperGrok record consumed by the generic Omarchy agents panel fresh.
Item {
  id: root

  visible: false
  width: 0
  height: 0

  property var shell: null
  property var manifest: null
  property int intervalSeconds: 720
  property int retrySeconds: 60
  property int maxRetries: 3
  property int retriesUsed: 0
  property bool collectQueued: false

  readonly property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("collect-grok.py"))
    .toString().replace(/^file:\/\//, ""))

  function collect() {
    if (runner.running) {
      collectQueued = true
      return
    }
    runner.command = ["/usr/bin/python3", collectorPath]
    runner.running = true
  }

  Process {
    id: runner
    running: false

    stdout: StdioCollector {
      waitForEnd: true
    }

    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("grok", text.trim())
    }

    onExited: (exitCode) => {
      if (root.collectQueued) {
        root.collectQueued = false
        root.collect()
        return
      }
      if (exitCode === 0) {
        root.retriesUsed = 0
        return
      }
      if (root.retriesUsed >= root.maxRetries) return
      root.retriesUsed += 1
      retry.restart()
    }
  }

  Timer {
    id: retry
    interval: root.retrySeconds * 1000
    repeat: false
    onTriggered: root.collect()
  }

  Timer {
    interval: root.intervalSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      root.retriesUsed = 0
      root.collect()
    }
  }
}

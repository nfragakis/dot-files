import QtQuick
import Quickshell
import Quickshell.Io

// Keeps the OpenCode Go usage record the agents panel displays fresh.
//
// The panel draws whatever records appear in the usage directory, whoever
// wrote them, and `omarchy-agent-usage-update` only runs the collectors
// packaged under $OMARCHY_PATH/bin. So this service owns one record of its
// own: on a timer it runs the collector beside this file, which writes
// ~/.local/state/omarchy/agents/usage/opencode-go.json. Nothing here talks to
// the panel, and nothing about a future Omarchy update needs to know this
// exists.
Item {
  id: root

  visible: false
  width: 0
  height: 0

  // Injected by the shell when it constructs the service singleton.
  property var shell: null
  property var manifest: null

  // Twelve minutes. The Go allowance refills on a 5-hour, weekly, and monthly
  // cadence, so there is nothing to learn from polling harder, and the
  // collector reuses a cached local scan for 15 minutes regardless — a run is
  // one HTTPS GET plus a file write.
  property int intervalSeconds: 720
  // A run that cannot reach the endpoint (exit code 2) or cannot write the
  // record (exit code 1) is retried a few times before the next full interval
  // is waited out — long enough to cover a laptop resuming before the network
  // is up, short of turning a broken endpoint into a permanent poll.
  property int retrySeconds: 60
  property int maxRetries: 3
  property int retriesUsed: 0
  property bool collectQueued: false

  readonly property string collectorPath: decodeURIComponent(String(Qt.resolvedUrl("collect-opencode-go.py"))
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

    // The collector prints the record it wrote. The file is the artifact the
    // panel reads, so stdout is swallowed rather than mirrored into the
    // shell's log; stderr carries the real complaints.
    stdout: StdioCollector {
      waitForEnd: true
    }

    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("opencode-go", text.trim())
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

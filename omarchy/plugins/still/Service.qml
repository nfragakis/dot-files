import "Protocols.js" as Protocols
import QtQuick
import Quickshell
import Quickshell.Io

StillSession {
    id: root

    property var shell: null
    property var manifest: null

    onPhaseCue: function(phaseType) {
        var sound = Protocols.phaseSound(phaseType)
        if (sound === "none")
            return
        var path = Qt.resolvedUrl("sounds/" + sound + ".ogg").toString().replace(/^file:\/\//, "")
        Quickshell.execDetached(["pw-play", path])
    }

    onReminderDue: {
        Quickshell.execDetached(["notify-send", "-a", "Still", "Take a breath", "Open Still when you have a moment."])
    }

    IpcHandler {
        target: "still"

        function start(): string {
            root.startSession()
            return "ok"
        }

        function pause(): string {
            return root.pauseSession() ? "ok" : "unhandled"
        }

        function resume(): string {
            return root.resumeSession() ? "ok" : "unhandled"
        }

        function skipHold(): string {
            return root.skipHold() ? "ok" : "unhandled"
        }

        function stop(): string {
            root.endSession()
            return "ok"
        }

        function status(): string {
            return JSON.stringify({
                state: root.sessionState,
                techniqueId: root.activeTechniqueId,
                preset: root.activePreset.name,
                phase: root.phaseType,
                phaseSecondsRemaining: root.phaseSecondsRemaining,
                elapsedMs: root.sessionElapsedMs,
                remainingMs: root.sessionRemainingMs,
                progress: root.sessionProgress
            })
        }
    }
}

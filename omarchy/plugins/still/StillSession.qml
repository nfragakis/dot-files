import "Protocols.js" as Protocols
import "SessionModel.js" as SessionModel
import QtQuick

Item {
    id: root

    property var settings: ({})

    signal phaseCue(string phaseType)
    signal reminderDue()

    readonly property string idleState: "idle"
    readonly property string countdownState: "countdown"
    readonly property string runningState: "running"
    readonly property string pausedState: "paused"
    readonly property string completeState: "complete"

    property string sessionState: idleState
    property string selectedTechniqueId: "coherent"
    property int selectedDurationIndex: 1
    readonly property var selectedPreset: Protocols.technique(selectedTechniqueId)

    property string activeTechniqueId: "coherent"
    property int activeDurationIndex: 1
    property var activePreset: Protocols.technique("coherent")
    property var activePhases: []
    property int targetDurationMs: 120000

    property int sessionElapsedMs: 0
    property int sessionRemainingMs: targetDurationMs
    property real sessionProgress: 0
    property int patternElapsedMs: 0
    property string phaseType: "normal"
    property string phaseLabel: Protocols.phaseLabel("normal")
    property int phaseIndex: 0
    property int phaseRemainingMs: 0
    property int phaseSecondsRemaining: 0
    property real phaseProgress: 0
    property real breathLevel: SessionModel.REST_LEVEL
    property int countdownNumber: 3

    property double countdownStartedAtMs: 0
    property double runStartedAtMs: 0
    property int accumulatedSessionMs: 0
    property int accumulatedPatternMs: 0
    property int completionPatternMs: -1
    property string lastCueKey: ""
    property string lastReminderKey: ""

    readonly property bool sessionActive: sessionState === countdownState
        || sessionState === runningState
        || sessionState === pausedState
    readonly property bool canConfigure: sessionState === idleState || sessionState === completeState
    readonly property bool paused: sessionState === pausedState
    readonly property bool holding: sessionState === runningState && Protocols.isHoldPhase(phaseType)
    readonly property bool reducedMotion: setting("reducedMotion", false) === true
    readonly property bool soundEnabled: setting("sound", true) === true
    readonly property bool remindersEnabled: setting("reminders", false) === true
    readonly property string reminderTimes: String(setting("reminderTimes", "10:00,15:00"))
    readonly property string sessionRemainingText: SessionModel.formatClock(sessionRemainingMs)
    readonly property string sessionElapsedText: SessionModel.formatClock(sessionElapsedMs)

    function setting(name, fallback) {
        var value = settings ? settings[name] : undefined
        return value === undefined || value === null ? fallback : value
    }

    function syncDefaults() {
        if (!canConfigure)
            return

        selectedTechniqueId = Protocols.technique(setting("defaultTechnique", "Coherent breathing")).id
        selectedDurationIndex = Protocols.durationIndex(setting("defaultDuration", "2 min"))
    }

    function selectTechnique(value) {
        if (canConfigure)
            selectedTechniqueId = Protocols.technique(value).id
    }

    function selectDuration(value) {
        if (canConfigure)
            selectedDurationIndex = Protocols.durationIndex(value)
    }

    function startSession() {
        activeTechniqueId = selectedTechniqueId
        activeDurationIndex = selectedDurationIndex
        activePreset = Protocols.technique(activeTechniqueId)
        activePhases = activePreset.phases
        targetDurationMs = Protocols.DURATIONS[activeDurationIndex] * 1000
        sessionElapsedMs = 0
        sessionRemainingMs = targetDurationMs
        sessionProgress = 0
        patternElapsedMs = 0
        accumulatedSessionMs = 0
        accumulatedPatternMs = 0
        completionPatternMs = -1
        phaseType = "normal"
        phaseLabel = "get ready"
        phaseIndex = 0
        phaseRemainingMs = SessionModel.COUNTDOWN_DURATION_MS
        phaseSecondsRemaining = 3
        phaseProgress = 0
        breathLevel = 0.34
        countdownNumber = 3
        lastCueKey = ""
        countdownStartedAtMs = Date.now()
        sessionState = countdownState
        ticker.start()
    }

    function beginBreathing(now) {
        accumulatedSessionMs = 0
        accumulatedPatternMs = 0
        runStartedAtMs = now
        lastCueKey = ""
        sessionState = runningState
        applyRunningSnapshot(0, 0, 0, false)
    }

    function applyRunningSnapshot(elapsedMs, nextPatternMs, previousPatternMs, allowCompletion) {
        var previousSessionMs = sessionElapsedMs
        sessionElapsedMs = Math.max(0, Math.round(elapsedMs))
        patternElapsedMs = Math.max(0, Math.round(nextPatternMs))
        sessionRemainingMs = Math.max(0, targetDurationMs - sessionElapsedMs)
        sessionProgress = SessionModel.sessionProgress(sessionElapsedMs, targetDurationMs)

        if (allowCompletion && sessionElapsedMs >= targetDurationMs) {
            if (completionPatternMs < 0) {
                completionPatternMs = SessionModel.completionBoundaryMs(
                    previousSessionMs, previousPatternMs, targetDurationMs, activePhases)
            }
            if (patternElapsedMs >= completionPatternMs) {
                finishSession()
                return false
            }
        }

        var snapshot = SessionModel.phaseAt(activePhases, patternElapsedMs)
        phaseType = snapshot.phaseType
        phaseLabel = Protocols.phaseLabel(phaseType)
        phaseIndex = snapshot.phaseIndex
        phaseRemainingMs = Math.round(snapshot.phaseRemainingMs)
        phaseSecondsRemaining = Math.max(1, Math.ceil(snapshot.phaseRemainingMs / 1000))
        phaseProgress = snapshot.phaseProgress
        breathLevel = snapshot.breathLevel

        var cueKey = snapshot.cycleIndex + ":" + snapshot.phaseIndex
        if (cueKey !== lastCueKey) {
            lastCueKey = cueKey
            playCue(phaseType)
        }
        return true
    }

    function update(now) {
        var current = Number(now)
        if (!isFinite(current))
            current = Date.now()

        if (sessionState === countdownState) {
            var countdown = SessionModel.countdownAt(current - countdownStartedAtMs)
            countdownNumber = countdown.number
            phaseRemainingMs = Math.round(countdown.remainingMs)
            phaseSecondsRemaining = countdown.number
            phaseProgress = countdown.progress
            breathLevel = countdown.breathLevel
            if (countdown.complete)
                beginBreathing(current)
            return
        }

        if (sessionState !== runningState)
            return

        var delta = Math.max(0, current - runStartedAtMs)
        var elapsed = accumulatedSessionMs + delta
        var nextPattern = accumulatedPatternMs + delta
        applyRunningSnapshot(elapsed, nextPattern, patternElapsedMs, true)
    }

    function pauseSession() {
        if (sessionState !== runningState)
            return false

        update(Date.now())
        if (sessionState !== runningState)
            return false

        accumulatedSessionMs = sessionElapsedMs
        accumulatedPatternMs = 0
        completionPatternMs = -1
        patternElapsedMs = 0
        sessionState = pausedState
        phaseType = "normal"
        phaseLabel = Protocols.phaseLabel("normal")
        phaseIndex = 0
        phaseRemainingMs = 0
        phaseSecondsRemaining = 0
        phaseProgress = 0
        breathLevel = SessionModel.REST_LEVEL
        lastCueKey = ""
        ticker.stop()
        return true
    }

    function resumeSession() {
        if (sessionState !== pausedState)
            return false

        accumulatedPatternMs = 0
        patternElapsedMs = 0
        completionPatternMs = -1
        runStartedAtMs = Date.now()
        lastCueKey = ""
        sessionState = runningState
        applyRunningSnapshot(accumulatedSessionMs, 0, 0, false)
        ticker.start()
        return true
    }

    function togglePause() {
        if (sessionState === pausedState)
            return resumeSession()
        return pauseSession()
    }

    function skipHold() {
        if (sessionState !== runningState)
            return false

        var now = Date.now()
        update(now)
        if (sessionState !== runningState || !holding)
            return false

        var previousPattern = patternElapsedMs
        var nextPattern = patternElapsedMs + phaseRemainingMs
        accumulatedSessionMs = sessionElapsedMs
        accumulatedPatternMs = nextPattern
        runStartedAtMs = now
        applyRunningSnapshot(sessionElapsedMs, nextPattern, previousPattern, true)
        return true
    }

    function primaryAction() {
        if (holding)
            return skipHold()
        return togglePause()
    }

    function cancelCountdown() {
        if (sessionState === countdownState)
            endSession()
    }

    function endSession() {
        ticker.stop()
        sessionState = idleState
        sessionElapsedMs = 0
        sessionRemainingMs = targetDurationMs
        sessionProgress = 0
        patternElapsedMs = 0
        accumulatedSessionMs = 0
        accumulatedPatternMs = 0
        completionPatternMs = -1
        phaseType = "normal"
        phaseLabel = Protocols.phaseLabel("normal")
        phaseIndex = 0
        phaseRemainingMs = 0
        phaseSecondsRemaining = 0
        phaseProgress = 0
        breathLevel = SessionModel.REST_LEVEL
        countdownNumber = 3
        lastCueKey = ""
    }

    function finishSession() {
        ticker.stop()
        sessionState = completeState
        sessionRemainingMs = 0
        sessionProgress = 1
        phaseType = "normal"
        phaseLabel = Protocols.phaseLabel("normal")
        phaseRemainingMs = 0
        phaseSecondsRemaining = 0
        phaseProgress = 1
        breathLevel = SessionModel.REST_LEVEL
        completionPatternMs = -1
        lastCueKey = ""
    }

    function repeatSession() {
        selectedTechniqueId = activeTechniqueId
        selectedDurationIndex = activeDurationIndex
        startSession()
    }

    function playCue(type) {
        if (!soundEnabled)
            return

        var sound = Protocols.phaseSound(type)
        if (sound === "none")
            return
        phaseCue(type)
    }

    function checkReminders() {
        if (!remindersEnabled)
            return

        var now = new Date()
        var hh = String(now.getHours()).padStart(2, "0")
        var mm = String(now.getMinutes()).padStart(2, "0")
        var time = hh + ":" + mm
        var key = Qt.formatDate(now, "yyyy-MM-dd") + "T" + time
        var configured = reminderTimes.split(",")
        for (var i = 0; i < configured.length; i++) {
            if (configured[i].trim() === time && lastReminderKey !== key) {
                lastReminderKey = key
                reminderDue()
                return
            }
        }
    }

    visible: false
    onSettingsChanged: syncDefaults()

    Timer {
        id: ticker

        interval: 33
        repeat: true
        onTriggered: root.update(Date.now())
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.checkReminders()
    }

    Component.onCompleted: syncDefaults()
}

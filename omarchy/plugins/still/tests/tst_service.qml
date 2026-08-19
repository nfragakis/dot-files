import QtQuick
import QtTest
import ".." as Still

TestCase {
    id: testCase

    name: "SessionService"
    property var session: null

    Component {
        id: sessionFactory

        Still.StillSession {
            settings: ({
                "sound": false,
                "reminders": false
            })
        }
    }

    function init() {
        session = createTemporaryObject(sessionFactory, testCase)
        verify(session !== null)
        compare(session.sessionState, session.idleState)
    }

    function cleanup() {
        if (session)
            session.endSession()
        session = null
    }

    function beginImmediately() {
        session.startSession()
        session.countdownStartedAtMs = Date.now() - 3000
        session.update(Date.now())
        compare(session.sessionState, session.runningState)
        compare(session.phaseType, "inhale")
    }

    function moveToBoxHold() {
        session.selectTechnique("box")
        beginImmediately()
        session.accumulatedSessionMs = 4000
        session.accumulatedPatternMs = 4000
        session.runStartedAtMs = Date.now()
        session.update(session.runStartedAtMs)
        compare(session.phaseType, "holdIn")
        verify(session.holding)
    }

    function test_countdownTransitionsIntoFirstInhale() {
        session.startSession()
        var startedAt = session.countdownStartedAtMs
        compare(session.sessionState, session.countdownState)
        compare(session.countdownNumber, 3)

        session.update(startedAt + 999)
        compare(session.countdownNumber, 3)
        session.update(startedAt + 1000)
        compare(session.countdownNumber, 2)
        session.update(startedAt + 2000)
        compare(session.countdownNumber, 1)
        session.update(startedAt + 3000)
        compare(session.sessionState, session.runningState)
        compare(session.phaseType, "inhale")
        compare(session.sessionElapsedMs, 0)
    }

    function test_pauseMeansNormalAndResumeBeginsWithInhale() {
        moveToBoxHold()
        verify(session.pauseSession())
        compare(session.sessionState, session.pausedState)
        compare(session.phaseType, "normal")
        compare(session.phaseLabel, "breathe normally")
        compare(session.breathLevel, 0.18)

        verify(session.resumeSession())
        compare(session.sessionState, session.runningState)
        compare(session.phaseType, "inhale")
        compare(session.phaseIndex, 0)
    }

    function test_skipHoldDoesNotCreditUnbreathedTime() {
        moveToBoxHold()
        var elapsedBefore = session.sessionElapsedMs
        verify(session.skipHold())
        compare(session.phaseType, "exhale")
        verify(session.sessionElapsedMs >= elapsedBefore)
        verify(session.sessionElapsedMs - elapsedBefore < 100)
    }

    function test_sessionCompletesOnCycleBoundary() {
        session.selectTechnique("coherent")
        session.selectDuration(30)
        beginImmediately()
        var breathingStartedAt = session.runStartedAtMs

        session.update(breathingStartedAt + 30000)
        compare(session.sessionState, session.runningState)
        compare(session.sessionRemainingMs, 0)

        session.update(breathingStartedAt + 32699)
        compare(session.sessionState, session.runningState)
        session.update(breathingStartedAt + 32700)
        compare(session.sessionState, session.completeState)
        compare(session.phaseType, "normal")
    }
}

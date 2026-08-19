import QtQuick
import QtTest
import "../Protocols.js" as Protocols
import "../SessionModel.js" as SessionModel

TestCase {
    name: "SessionModel"

    function near(actual, expected, tolerance) {
        verify(Math.abs(actual - expected) <= tolerance,
            "expected " + actual + " to be within " + tolerance + " of " + expected)
    }

    function test_protocolsAreSmallCompleteAndPositive() {
        compare(Protocols.TECHNIQUES.length, 5)
        compare(Protocols.TECHNIQUES[0].id, "coherent")
        compare(Protocols.TECHNIQUES[3].id, "buteyko-quiet")
        compare(Protocols.TECHNIQUES[4].id, "buteyko-reduced")

        var techniquesWithPauses = 0
        for (var i = 0; i < Protocols.TECHNIQUES.length; i++) {
            var technique = Protocols.TECHNIQUES[i]
            verify(technique.name.length > 0)
            verify(technique.phases.length > 0)
            verify(SessionModel.cycleDurationMs(technique.phases) > 0)

            var hasPause = false
            for (var phaseIndex = 0; phaseIndex < technique.phases.length; phaseIndex++) {
                var phase = technique.phases[phaseIndex]
                verify(phase.seconds > 0)
                verify(phase.fromLevel >= SessionModel.REST_LEVEL && phase.fromLevel <= 1)
                verify(phase.toLevel >= SessionModel.REST_LEVEL && phase.toLevel <= 1)
                verify(Protocols.phaseLabel(phase.type).length > 0)
                hasPause = hasPause || Protocols.isHoldPhase(phase.type)
            }
            if (hasPause) techniquesWithPauses++
        }
        compare(techniquesWithPauses, 3)
    }

    function test_settingNormalization() {
        compare(Protocols.technique("Box breathing").id, "box")
        compare(Protocols.technique("buteyko").id, "buteyko-reduced")
        compare(Protocols.technique("Quiet nasal").id, "buteyko-quiet")
        compare(Protocols.technique("unknown").id, "coherent")
        compare(Protocols.techniqueIndex("downshift"), 2)
        compare(Protocols.durationIndex("30 sec"), 0)
        compare(Protocols.durationIndex(120), 1)
        compare(Protocols.durationIndex("5 min"), 2)
        compare(Protocols.durationIndex("unknown"), 1)
    }

    function test_exactBoxBoundaries() {
        var phases = Protocols.technique("box").phases
        compare(SessionModel.cycleDurationMs(phases), 16000)

        var start = SessionModel.phaseAt(phases, 0)
        compare(start.phaseType, "inhale")
        compare(start.phaseRemainingMs, 4000)
        compare(start.breathLevel, SessionModel.REST_LEVEL)

        var holdFull = SessionModel.phaseAt(phases, 4000)
        compare(holdFull.phaseType, "holdIn")
        compare(holdFull.breathLevel, 1)

        var exhale = SessionModel.phaseAt(phases, 8000)
        compare(exhale.phaseType, "exhale")
        compare(exhale.breathLevel, 1)

        var holdEmpty = SessionModel.phaseAt(phases, 12000)
        compare(holdEmpty.phaseType, "holdOut")
        compare(holdEmpty.breathLevel, SessionModel.REST_LEVEL)

        var nextCycle = SessionModel.phaseAt(phases, 16000)
        compare(nextCycle.phaseType, "inhale")
        compare(nextCycle.cycleIndex, 1)
        compare(nextCycle.cycleElapsedMs, 0)
    }

    function test_breathLevelUsesSmoothInterpolation() {
        var phases = Protocols.technique("coherent").phases
        var inhaleMidpoint = SessionModel.phaseAt(phases, 2725)
        near(inhaleMidpoint.breathLevel, 0.59, 0.0001)

        var exhaleMidpoint = SessionModel.phaseAt(phases, 8175)
        near(exhaleMidpoint.breathLevel, 0.59, 0.0001)
    }

    function test_reducedBreathingUsesQuietNasalBreathsAndNaturalPause() {
        var phases = Protocols.technique("buteyko-reduced").phases
        compare(SessionModel.cycleDurationMs(phases), 6000)
        compare(SessionModel.phaseAt(phases, 0).phaseType, "inhaleNasal")
        compare(SessionModel.phaseAt(phases, 2000).phaseType, "exhaleNasal")
        compare(SessionModel.phaseAt(phases, 5000).phaseType, "pauseOut")
        compare(SessionModel.phaseAt(phases, 6000).phaseType, "inhaleNasal")
    }

    function test_quietNasalBreathingHasNoProgrammedHold() {
        var phases = Protocols.technique("buteyko-quiet").phases
        compare(SessionModel.cycleDurationMs(phases), 5000)
        compare(SessionModel.phaseAt(phases, 0).phaseType, "inhaleNasal")
        compare(SessionModel.phaseAt(phases, 2000).phaseType, "exhaleNasal")
        for (var i = 0; i < phases.length; i++)
            verify(!Protocols.isHoldPhase(phases[i].type))
    }

    function test_countdownIsThreeTwoOne() {
        compare(SessionModel.countdownAt(0).number, 3)
        compare(SessionModel.countdownAt(999).number, 3)
        compare(SessionModel.countdownAt(1000).number, 2)
        compare(SessionModel.countdownAt(1999).number, 2)
        compare(SessionModel.countdownAt(2000).number, 1)
        compare(SessionModel.countdownAt(2999).number, 1)
        compare(SessionModel.countdownAt(3000).number, 0)
        verify(SessionModel.countdownAt(3000).complete)
    }

    function test_completionBoundaryIsAtOrAfterTarget() {
        var coherent = Protocols.technique("coherent").phases
        compare(SessionModel.completionBoundaryMs(0, 0, 30000, coherent), 32700)

        var reduced = Protocols.technique("buteyko-reduced").phases
        compare(SessionModel.completionBoundaryMs(0, 0, 30000, reduced), 30000)

        var box = Protocols.technique("box").phases
        compare(SessionModel.completionBoundaryMs(31000, 0, 30000, box), 16000)
    }

    function test_progressAndClockFormatting() {
        compare(SessionModel.sessionProgress(-1, 100), 0)
        compare(SessionModel.sessionProgress(50, 100), 0.5)
        compare(SessionModel.sessionProgress(101, 100), 1)
        compare(SessionModel.formatClock(0), "0:00")
        compare(SessionModel.formatClock(1000), "0:01")
        compare(SessionModel.formatClock(61000), "1:01")
    }
}

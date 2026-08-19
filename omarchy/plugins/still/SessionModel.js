.pragma library

var REST_LEVEL = 0.18
var COUNTDOWN_DURATION_MS = 3000

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value))
}

function phaseDurationMs(phase) {
  return Math.max(0, Number(phase && phase.seconds) || 0) * 1000
}

function cycleDurationMs(phases) {
  var total = 0
  for (var i = 0; phases && i < phases.length; i++)
    total += phaseDurationMs(phases[i])
  return total
}

function easedProgress(progress) {
  var t = clamp(Number(progress) || 0, 0, 1)
  return 0.5 - Math.cos(Math.PI * t) / 2
}

function phaseAt(phases, elapsedMs) {
  var cycleMs = cycleDurationMs(phases)
  if (!phases || phases.length === 0 || cycleMs <= 0) {
    return {
      phaseIndex: 0,
      phaseType: "normal",
      phaseElapsedMs: 0,
      phaseRemainingMs: 0,
      phaseProgress: 0,
      breathLevel: REST_LEVEL,
      cycleIndex: 0,
      cycleElapsedMs: 0,
      cycleDurationMs: 0
    }
  }

  var elapsed = Math.max(0, Number(elapsedMs) || 0)
  var cycleIndex = Math.floor(elapsed / cycleMs)
  var cycleElapsedMs = elapsed % cycleMs
  var phaseStartMs = 0
  var phaseIndex = 0
  var selected = phases[0]

  for (var i = 0; i < phases.length; i++) {
    var endMs = phaseStartMs + phaseDurationMs(phases[i])
    if (cycleElapsedMs < endMs) {
      phaseIndex = i
      selected = phases[i]
      break
    }
    phaseStartMs = endMs
  }

  var durationMs = phaseDurationMs(selected)
  var phaseElapsedMs = cycleElapsedMs - phaseStartMs
  var progress = durationMs > 0 ? phaseElapsedMs / durationMs : 1
  var eased = easedProgress(progress)
  var fromLevel = Number(selected.fromLevel)
  var toLevel = Number(selected.toLevel)
  if (!isFinite(fromLevel)) fromLevel = REST_LEVEL
  if (!isFinite(toLevel)) toLevel = REST_LEVEL

  return {
    phaseIndex: phaseIndex,
    phaseType: selected.type,
    phaseElapsedMs: phaseElapsedMs,
    phaseRemainingMs: Math.max(0, durationMs - phaseElapsedMs),
    phaseProgress: clamp(progress, 0, 1),
    breathLevel: clamp(fromLevel + (toLevel - fromLevel) * eased, REST_LEVEL, 1),
    cycleIndex: cycleIndex,
    cycleElapsedMs: cycleElapsedMs,
    cycleDurationMs: cycleMs
  }
}

function completionBoundaryMs(previousSessionMs, previousPatternMs, targetMs, phases) {
  var cycleMs = cycleDurationMs(phases)
  if (cycleMs <= 0) return 0

  var sessionElapsed = Math.max(0, Number(previousSessionMs) || 0)
  var patternElapsed = Math.max(0, Number(previousPatternMs) || 0)
  var target = Math.max(0, Number(targetMs) || 0)
  if (sessionElapsed >= target)
    return (Math.floor(patternElapsed / cycleMs) + 1) * cycleMs

  var patternAtTarget = patternElapsed + target - sessionElapsed
  return Math.ceil(patternAtTarget / cycleMs) * cycleMs
}

function countdownAt(elapsedMs) {
  var elapsed = clamp(Number(elapsedMs) || 0, 0, COUNTDOWN_DURATION_MS)
  var remainingMs = Math.max(0, COUNTDOWN_DURATION_MS - elapsed)
  var number = remainingMs > 0 ? Math.ceil(remainingMs / 1000) : 0
  var stepElapsedMs = elapsed >= COUNTDOWN_DURATION_MS ? 1000 : elapsed % 1000
  var stepProgress = clamp(stepElapsedMs / 1000, 0, 1)

  return {
    complete: elapsed >= COUNTDOWN_DURATION_MS,
    number: number,
    remainingMs: remainingMs,
    progress: elapsed / COUNTDOWN_DURATION_MS,
    breathLevel: 0.34 - 0.16 * easedProgress(stepProgress)
  }
}

function sessionProgress(elapsedMs, targetMs) {
  return clamp((Number(elapsedMs) || 0) / Math.max(1, Number(targetMs) || 1), 0, 1)
}

function formatClock(ms) {
  var seconds = Math.max(0, Math.ceil((Number(ms) || 0) / 1000))
  var minutes = Math.floor(seconds / 60)
  var remainder = seconds % 60
  return minutes + ":" + (remainder < 10 ? "0" : "") + remainder
}

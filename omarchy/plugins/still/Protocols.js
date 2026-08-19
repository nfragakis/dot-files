.pragma library

var DURATIONS = [30, 120, 300]

var PHASE_METADATA = {
  normal: { label: "breathe normally", shortLabel: "NORMAL", fromLevel: 0.18, toLevel: 0.18, sound: "none", isHold: false },
  inhale: { label: "inhale", shortLabel: "IN", fromLevel: 0.18, toLevel: 1.0, sound: "in", isHold: false },
  inhaleNasal: { label: "soft nasal inhale", shortLabel: "IN", fromLevel: 0.18, toLevel: 0.82, sound: "in", isHold: false },
  holdIn: { label: "hold after inhale", shortLabel: "HOLD", fromLevel: 1.0, toLevel: 1.0, sound: "none", isHold: true },
  exhale: { label: "exhale", shortLabel: "OUT", fromLevel: 1.0, toLevel: 0.18, sound: "out", isHold: false },
  exhaleNasal: { label: "soft nasal exhale", shortLabel: "OUT", fromLevel: 0.82, toLevel: 0.18, sound: "out", isHold: false },
  holdOut: { label: "hold after exhale", shortLabel: "HOLD", fromLevel: 0.18, toLevel: 0.18, sound: "none", isHold: true },
  pauseOut: { label: "soft pause", shortLabel: "PAUSE", fromLevel: 0.18, toLevel: 0.18, sound: "none", isHold: true }
}

function phase(type, seconds, fromLevel, toLevel) {
  var metadata = PHASE_METADATA[type]
  if (!metadata) throw new Error("Unknown breathing phase: " + type)
  return {
    type: type,
    seconds: seconds,
    fromLevel: fromLevel === undefined ? metadata.fromLevel : fromLevel,
    toLevel: toLevel === undefined ? metadata.toLevel : toLevel
  }
}

// Five deliberately distinct choices replace the former intention-by-pace
// matrix. The Buteyko timings are conservative app adaptations: the defining
// instruction is small, quiet nasal breathing and an easy post-exhale pause,
// not a fixed volume, maximum hold, or treatment dose.
var TECHNIQUES = [
  {
    id: "coherent",
    shortName: "Coherent",
    name: "Coherent breathing",
    detail: "5.5 in · 5.5 out",
    basis: "STEADY BREATH · NO HOLD",
    benefit: "A simple balanced rhythm associated with acute relaxation and breathing-linked HRV.",
    cue: "Breathe quietly and evenly, smaller than a full lungful.",
    phases: [phase("inhale", 5.45), phase("exhale", 5.45)]
  },
  {
    id: "box",
    shortName: "Box",
    name: "Box breathing",
    detail: "4 in · 4 hold · 4 out · 4 hold",
    basis: "STRUCTURED BREATH · TWO HOLDS",
    benefit: "Four equal sides provide a clear attention anchor with a pause after both inhale and exhale.",
    cue: "Both holds are optional. Skip immediately at the first hint of strain.",
    phases: [phase("inhale", 4), phase("holdIn", 4), phase("exhale", 4), phase("holdOut", 4)]
  },
  {
    id: "downshift",
    shortName: "Downshift",
    name: "Downshift",
    detail: "4 in · 2 hold · 6 out · 2 pause",
    basis: "LONG EXHALE · SHORT PAUSES",
    benefit: "A longer, easy exhale with brief pauses creates a slower and more spacious rhythm.",
    cue: "Keep both pauses comfortable; skip either one rather than chasing the count.",
    phases: [phase("inhale", 4), phase("holdIn", 2), phase("exhale", 6), phase("holdOut", 2)]
  },
  {
    id: "buteyko-quiet",
    shortName: "Quiet nasal",
    name: "Quiet nasal breathing",
    detail: "small, silent nasal breaths · no hold",
    basis: "BUTEYKO-INSPIRED · RELAXED BREATHING",
    benefit: "A gentle nasal-breathing practice for noticing a quieter, smaller breath without a programmed hold.",
    cue: "Relax the jaw, shoulders, and lower ribs. Let the breath stay light and unforced.",
    phases: [phase("inhaleNasal", 2), phase("exhaleNasal", 3)]
  },
  {
    id: "buteyko-reduced",
    shortName: "Reduced",
    name: "Reduced breathing",
    detail: "small nasal breath · 1-second natural pause",
    basis: "BUTEYKO-INSPIRED · REDUCED BREATHING",
    benefit: "An app-paced introduction to quieter, lower-volume nasal breathing—not a complete Buteyko course or treatment.",
    cue: "Keep the breath small and silent. The natural pause is optional; never strain or chase air hunger.",
    phases: [phase("inhaleNasal", 2), phase("exhaleNasal", 3), phase("pauseOut", 1)]
  }
]

function normalizedKey(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "-")
}

function technique(value) {
  var key = normalizedKey(value)
  if (key === "calm") key = "coherent"
  else if (key === "focus") key = "box"
  else if (key === "recover") key = "downshift"
  else if (key === "buteyko" || key === "reduced") key = "buteyko-reduced"
  else if (key === "quiet" || key === "quiet-nasal") key = "buteyko-quiet"

  for (var i = 0; i < TECHNIQUES.length; i++) {
    var item = TECHNIQUES[i]
    if (key === normalizedKey(item.id)
        || key === normalizedKey(item.name)
        || key === normalizedKey(item.shortName)) return item
  }
  return TECHNIQUES[0]
}

function techniqueIndex(value) {
  var selected = technique(value)
  for (var i = 0; i < TECHNIQUES.length; i++)
    if (TECHNIQUES[i].id === selected.id) return i
  return 0
}

function durationIndex(value) {
  var key = String(value || "").trim().toLowerCase()
  var seconds = Number(value)
  for (var i = 0; i < DURATIONS.length; i++) {
    if (seconds === DURATIONS[i]) return i
    if (key === durationLabel(i).toLowerCase()) return i
  }
  return 1
}

function durationLabel(index) {
  var seconds = DURATIONS[Math.max(0, Math.min(DURATIONS.length - 1, Number(index) || 0))]
  return seconds < 60 ? seconds + " sec" : (seconds / 60) + " min"
}

function phaseMetadata(type) {
  return PHASE_METADATA[type] || PHASE_METADATA.normal
}

function isHoldPhase(type) {
  return phaseMetadata(type).isHold
}

function phaseLabel(type) {
  return phaseMetadata(type).label
}

function phaseShortLabel(type) {
  return phaseMetadata(type).shortLabel
}

function phaseSound(type) {
  return phaseMetadata(type).sound
}

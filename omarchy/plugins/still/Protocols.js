.pragma library

var INTENTIONS = [
  { id: "calm", label: "Calm", note: "settle the noise" },
  { id: "focus", label: "Focus", note: "steady attention" },
  { id: "energy", label: "Energy", note: "wake the system" },
  { id: "recover", label: "Recover", note: "long, easy release" }
]

var DIFFICULTIES = ["Easy", "Medium", "Hard"]
var DURATIONS = [30, 120, 300]

// phase types: inhale, sip, holdIn, exhale, holdOut, power, retain, recover
// A preset is deliberately just a sequence of primitives. The player loops
// `phases`, except power sessions, whose complete multi-round sequence is
// generated here.
var PRESETS = {
  calm: [
    { name: "Long exhale", detail: "4 in · 6 out", phases: [["inhale", 4], ["exhale", 6]] },
    { name: "Resonance", detail: "5 in · 5 out", phases: [["inhale", 5], ["exhale", 5]] },
    { name: "Cyclic sigh", detail: "inhale · sip · long exhale", phases: [["inhale", 2.5], ["sip", 1], ["exhale", 6.5]] }
  ],
  focus: [
    { name: "Even breath", detail: "4 in · 4 out", phases: [["inhale", 4], ["exhale", 4]] },
    { name: "Box", detail: "4 · 4 · 4 · 4", phases: [["inhale", 4], ["holdIn", 4], ["exhale", 4], ["holdOut", 4]] },
    { name: "Deep box", detail: "5 · 5 · 5 · 5", phases: [["inhale", 5], ["holdIn", 5], ["exhale", 5], ["holdOut", 5]] }
  ],
  energy: [
    { name: "Bright breath", detail: "4 in · 2 out", phases: [["inhale", 4], ["exhale", 2]] },
    { name: "Charge", detail: "3 in · 1 out", phases: [["inhale", 3], ["exhale", 1]] },
    { name: "Power rounds", detail: "30 breaths · retention", advanced: true, power: true }
  ],
  recover: [
    { name: "Release", detail: "4 in · 6 out", phases: [["inhale", 4], ["exhale", 6]] },
    { name: "Downshift", detail: "4 in · 2 hold · 8 out", phases: [["inhale", 4], ["holdIn", 2], ["exhale", 8]] },
    { name: "Deep release", detail: "4 · 4 · 8 · 4", phases: [["inhale", 4], ["holdIn", 4], ["exhale", 8], ["holdOut", 4]] }
  ]
}

function preset(intent, difficulty) {
  var group = PRESETS[intent] || PRESETS.calm
  return group[Math.max(0, Math.min(2, difficulty))]
}

function powerPhases(rounds) {
  var result = []
  var count = Math.max(1, rounds || 1)
  for (var r = 0; r < count; r++) {
    for (var i = 0; i < 30; i++) {
      result.push(["power", 1.5])
      result.push(["exhale", 1.0])
    }
    result.push(["retain", 30 + r * 15])
    result.push(["recover", 15])
  }
  return result
}

function phasesFor(intent, difficulty, durationSec) {
  var p = preset(intent, difficulty)
  if (!p.power) return p.phases
  // Power rounds are round-based: 2 minutes gets one round; 5 gets two.
  return powerPhases(durationSec >= 300 ? 2 : 1)
}

function phaseLabel(type) {
  if (type === "inhale") return "inhale"
  if (type === "sip") return "sip in"
  if (type === "holdIn" || type === "holdOut") return "hold"
  if (type === "power") return "breathe in"
  if (type === "retain") return "hold after exhale"
  if (type === "recover") return "inhale & hold"
  return "exhale"
}

function phaseScale(type) {
  if (type === "inhale" || type === "sip" || type === "power" || type === "recover") return 1.0
  if (type === "exhale") return 0.18
  if (type === "retain") return 0.12
  return -1
}

.pragma library

var INTENTIONS = [
  { id: "calm", label: "Calm", note: "settle the noise" },
  { id: "focus", label: "Focus", note: "steady attention" },
  { id: "energy", label: "Energy", note: "a brighter rhythm" },
  { id: "recover", label: "Recover", note: "long, easy release" },
  { id: "tradition", label: "Tradition", note: "breath as ritual" }
]

var DIFFICULTIES = ["Easy", "Medium", "Explore"]
var DURATIONS = [30, 120, 300]

var PHASE_METADATA = {
  normal: { label: "breathe normally", scale: -1, sound: "none", isHold: false },
  inhale: { label: "inhale", scale: 1.0, sound: "in", isHold: false },
  sip: { label: "sip in", scale: 1.0, sound: "in", isHold: false },
  holdIn: { label: "hold", scale: -1, sound: "none", isHold: true },
  holdOut: { label: "hold", scale: -1, sound: "none", isHold: true },
  exhale: { label: "exhale", scale: 0.18, sound: "out", isHold: false },
  inhaleLeft: { label: "inhale left", scale: 1.0, sound: "in", isHold: false },
  inhaleRight: { label: "inhale right", scale: 1.0, sound: "in", isHold: false },
  exhaleLeft: { label: "exhale left", scale: 0.18, sound: "out", isHold: false },
  exhaleRight: { label: "exhale right", scale: 0.18, sound: "out", isHold: false },
  pursedExhale: { label: "pursed-lip exhale", scale: 0.18, sound: "out", isHold: false },
  hum: { label: "hum out", scale: 0.18, sound: "out", isHold: false },
  ujjayiOut: { label: "ocean exhale", scale: 0.18, sound: "out", isHold: false },
  sitaliIn: { label: "inhale through tongue", scale: 1.0, sound: "in", isHold: false }
}

function phase(type, seconds) {
  if (!PHASE_METADATA[type]) throw new Error("Unknown breathing phase: " + type)
  return { type: type, seconds: seconds }
}

// A preset is deliberately just a sequence of phase primitives plus concise,
// calibrated copy. Timing is a comfortable app adaptation, not a claim that
// every source used this exact ratio or that two minutes is a treatment dose.
var PRESETS = {
  calm: [
    {
      name: "Long exhale",
      detail: "4 in · 6 out",
      basis: "SLOW-BREATH RESEARCH",
      benefit: "A gentle longer exhale may help you settle without demanding a hold.",
      cue: "Keep the inhale light and the exhale smooth, never forced.",
      phases: [phase("inhale", 4), phase("exhale", 6)]
    },
    {
      name: "Coherent",
      detail: "5.5 in · 5.5 out",
      basis: "TWO-MINUTE PHYSIOLOGY STUDY",
      benefit: "About 5.5 breaths a minute was associated with acute relaxation and breathing-linked HRV.",
      cue: "Breathe quietly and evenly, smaller than a full lungful.",
      phases: [phase("inhale", 5.45), phase("exhale", 5.45)]
    },
    {
      name: "Cyclic sigh",
      detail: "inhale · small sip · long exhale",
      basis: "RANDOMIZED BREATHWORK TRIAL",
      benefit: "A double inhale and long exhale showed promising mood effects with repeated five-minute practice.",
      cue: "Make the second sip small; do not strain for a maximum breath.",
      phases: [phase("inhale", 2.5), phase("sip", 1), phase("exhale", 6.5)]
    }
  ],
  focus: [
    {
      name: "Even breath",
      detail: "4 in · 4 out",
      basis: "GENTLE PACING",
      benefit: "A simple count gives attention one quiet, repeatable task.",
      cue: "Let the lower ribs move while the shoulders stay easy.",
      phases: [phase("inhale", 4), phase("exhale", 4)]
    },
    {
      name: "Box",
      detail: "4 · 4 · 4 · 4",
      basis: "CONTROLLED BREATHWORK STUDIES",
      benefit: "Four equal sides can provide a structured attention anchor and may lower acute arousal.",
      cue: "Shorten or skip either hold at the first hint of strain.",
      phases: [phase("inhale", 4), phase("holdIn", 4), phase("exhale", 4), phase("holdOut", 4)]
    },
    {
      name: "Alternate nostril",
      detail: "4 in · 6 out · switch sides",
      basis: "YOGA TRADITION · LIMITED STUDIES",
      benefit: "Nadi shodhana combines slow breathing with hand coordination to steady attention.",
      cue: "Begin on the left; skip this when either nostril is blocked or irritated.",
      phases: [phase("inhaleLeft", 4), phase("exhaleRight", 6), phase("inhaleRight", 4), phase("exhaleLeft", 6)]
    }
  ],
  energy: [
    {
      name: "Bright even",
      detail: "4 in · 4 out",
      basis: "EXPERIENTIAL PACING",
      benefit: "A slightly quicker rhythm can make a pause feel more awake; an energy effect is not established.",
      cue: "Keep each breath light rather than deep.",
      phases: [phase("inhale", 4), phase("exhale", 4)]
    },
    {
      name: "Active even",
      detail: "3 in · 3 out",
      basis: "EXPERIENTIAL PACING",
      benefit: "A brisk, even count offers a wakeful attention reset without breath retention.",
      cue: "Use small breaths and return to normal breathing if you feel tingly or light-headed.",
      phases: [phase("inhale", 3), phase("exhale", 3)]
    },
    {
      name: "Quick light",
      detail: "2.5 in · 2.5 out",
      basis: "EXPERIENTIAL · NO HEALTH CLAIM",
      benefit: "The quickest Still rhythm is offered for sensation and focus, not as a proven energy intervention.",
      cue: "Light and quiet only; stop immediately for dizziness, tingling, or panic.",
      phases: [phase("inhale", 2.5), phase("exhale", 2.5)]
    }
  ],
  recover: [
    {
      name: "Pursed-lip ease",
      detail: "2 in · 4 out through pursed lips",
      basis: "CLINICAL BREATHING TECHNIQUE",
      benefit: "A slow pursed-lip exhale is commonly taught to make breathing feel more controlled.",
      cue: "Follow your own care plan if you use this for a lung condition.",
      phases: [phase("inhale", 2), phase("pursedExhale", 4)]
    },
    {
      name: "Release",
      detail: "4 in · 6 out",
      basis: "SLOW-BREATH RESEARCH",
      benefit: "An unforced longer exhale offers a simple way to downshift after effort.",
      cue: "Let the exhale trail away naturally; do not empty completely.",
      phases: [phase("inhale", 4), phase("exhale", 6)]
    },
    {
      name: "Downshift",
      detail: "4 in · 2 hold · 8 out",
      basis: "TRADITIONAL COUNT · LIMITED EVIDENCE",
      benefit: "A brief optional pause and long release make this the most spacious recovery pattern.",
      cue: "Skip the hold or shorten the exhale whenever air hunger appears.",
      phases: [phase("inhale", 4), phase("holdIn", 2), phase("exhale", 8)]
    }
  ],
  tradition: [
    {
      name: "Bhramari",
      detail: "4 in · 6 humming out",
      basis: "YOGA · HUMMING-BEE BREATH",
      benefit: "A gentle humming exhale gives the mind sound and vibration to rest on.",
      cue: "Use an easy closed-mouth hum; skip it if ear or sinus symptoms worsen.",
      phases: [phase("inhale", 4), phase("hum", 6)]
    },
    {
      name: "Ujjayi",
      detail: "5 in · 5 ocean-like out",
      basis: "YOGA · ATTENTION PRACTICE",
      benefit: "A soft ocean-like exhale makes attention tangible; it has not outperformed ordinary slow breathing.",
      cue: "Narrow the throat only enough for a quiet whisper, never a forceful closure.",
      phases: [phase("inhale", 5), phase("ujjayiOut", 5)]
    },
    {
      name: "Sitali",
      detail: "4 in through curled tongue · 6 nasal out",
      basis: "YOGA · TRADITIONALLY ‘COOLING’",
      benefit: "A sensory mouth-inhale practice traditionally associated with coolness and composure.",
      cue: "Skip in cold, smoky, or dry air, or if the mouth inhale feels irritating.",
      phases: [phase("sitaliIn", 4), phase("exhale", 6)]
    }
  ]
}

function preset(intent, difficulty) {
  var group = PRESETS[intent] || PRESETS.calm
  return group[Math.max(0, Math.min(2, difficulty))]
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

function phaseScale(type) {
  return phaseMetadata(type).scale
}

function phaseSound(type) {
  return phaseMetadata(type).sound
}

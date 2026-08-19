# Still

Still is a centered breathing and meditation panel for the Omarchy bar. It
offers five deliberately distinct techniques—Coherent, Box, Downshift,
Quiet Nasal Breathing, and Reduced Breathing. It stores no session history or
health data.

Sessions begin with a 3–2–1 countdown and follow a theme-aware procedural
bloom. The bar shows the live phase and remaining seconds. Closing the panel
only hides it; the synchronized session continues and can be reopened from any
monitor.

## Install

From the root of this dot-files repository, run `./install-omarchy.sh`. The
installer safely links the plugin and shell configuration into
`~/.config/omarchy`, backing up conflicts before replacing them.

## Settings

Still exposes its defaults through Omarchy's bar settings. For example:

```bash
omarchy bar set still defaultTechnique "Coherent breathing"
omarchy bar set still defaultDuration "2 min"
omarchy bar set still sound true --json
omarchy bar set still reducedMotion true --json
```

Reduced motion keeps the bloom nearly still while retaining phase text,
countdowns, and sound cues.

## Reminders

Reminders are intentionally opt-in. Add settings to the `still` entry in
`~/.config/omarchy/shell.json`:

```json
{
  "id": "still",
  "reminders": true,
  "reminderTimes": "10:00,15:00",
  "sound": true
}
```

Times use the local 24-hour clock. Reminders only send a notification; they
never open the panel or interrupt the active application.

The same values can be changed with:

```bash
omarchy bar set still reminders true --json
omarchy bar set still reminderTimes "10:00,15:00"
```

## Keyboard and scripts

- Arrow keys or `h/j/k/l` move through setup controls.
- `Enter` or `Space` activates the selected control.
- `S` starts, `P` pauses or resumes, `E` ends, and `R` repeats a completed
  session.
- `Escape` hides the panel without stopping an active session.

Still can also be controlled from scripts or keybindings:

```bash
omarchy-shell still start
omarchy-shell still pause
omarchy-shell still resume
omarchy-shell still skipHold
omarchy-shell still stop
omarchy-shell still status
```

## Protocol notes

- **Coherent** is the no-hold baseline: `5.5 in · 5.5 out`.
- **Box** uses equal `4 · 4 · 4 · 4` phases, including holds after inhale and
  exhale.
- **Downshift** combines a longer exhale with two short optional pauses:
  `4 in · 2 hold · 6 out · 2 pause`.
- **Quiet Nasal Breathing** introduces the relaxed, low-volume nasal-breathing
  element of Buteyko without a programmed hold.
- **Reduced Breathing** adds one optional one-second natural pause after a
  small nasal exhale.

Pause always means “breathe normally” and resume begins again with an inhale.
Every hold can be skipped immediately. Breathe gently rather than maximally;
stop and return to normal breathing for dizziness, tingling, unusual
breathlessness, pain, faintness, or panic. This plugin is a wellness pacing
tool, not medical advice or treatment.

The two Buteyko-inspired choices are conservative app adaptations, not a full
Buteyko course. They do not include Mini Pause sets, Control Pause scores,
maximum or extended holds, mouth taping, symptom treatment, or medication
guidance. Do not use Still to manage an asthma attack, delay prescribed rescue
treatment, or change medication.

## Sources

- [Lin, Tai & Fan (2014)](https://pubmed.ncbi.nlm.nih.gov/24380741/), a
  two-minute comparison of slow-breath pacing ratios.
- [Balban et al. (2023)](https://doi.org/10.1016/j.xcrm.2022.100895), a
  randomized trial that included five-minute daily box breathing.
- [Buteyko Breathing Association practice guide](https://www.buteykobreathing.org/wp-content/uploads/2017/10/Buteyko-Breathing-Practice-Diary.pdf),
  for reduced breathing, the natural pause, and the beginner Mini Pause
  sequence.
- [Vagedes et al. (2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10782792/),
  a teacher-led, multi-week asthma trial illustrating how much broader formal
  Buteyko training is than an app pacer.

Detailed evidence, limitations, implementation notes, and safety sources are
kept in [`research/`](research/).

The shared-session and procedural-bloom direction was informed by
[Kalm for Omarchy](https://github.com/ctl0v0/kalm-omarchy-plugin). Still's
implementation, protocol selection, centered interaction, and safety behavior
remain its own.

## License

MIT

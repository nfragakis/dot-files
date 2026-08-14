# Still

Still is a compact breathing and meditation panel for the Omarchy bar. It
offers four intentions—Calm, Focus, Energy, and Recover—with three levels of
paced breathing. It stores no session history or health data.

## Install

```bash
omarchy plugin add https://github.com/YOUR-USER/still.git --enable --yes
```

For local development, copy or link this directory to
`~/.config/omarchy/plugins/still`, then rescan the shell plugins.

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

## Protocol notes

- Calm uses extended-exhale, resonance-paced, and cyclic-sigh patterns.
- Focus uses even breathing and equal-phase box breathing.
- Energy uses inhale-emphasized patterns. Its Hard preset is an advanced
  power-breathing sequence: 30 rhythmic breaths, an exhale retention, and a
  15-second recovery hold.
- Recover uses progressively longer exhales and optional pauses.

The advanced sequence can cause light-headedness or, rarely, loss of
consciousness. Practice seated or lying down, never driving, standing, or in
or near water. Stop and return to normal breathing if you feel unwell. This
plugin is a pacing tool, not medical advice.

## Sources

- Balban et al., *Cell Reports Medicine* (2023), structured five-minute
  cyclic sighing, box breathing, and cyclic hyperventilation with retention.
- Zaccaro et al., *Frontiers in Human Neuroscience* (2018), systematic review
  of slow breathing below 10 breaths per minute.
- Wim Hof Method, official basic breathing instructions and safety guidance.

## License

MIT

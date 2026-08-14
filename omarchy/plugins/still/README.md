# Still

Still is a centered breathing and meditation panel for the Omarchy bar. It
offers five intentions—Calm, Focus, Energy, Recover, and Tradition—with three
levels of paced breathing. It stores no session history or health data.

## Install

From the root of this dot-files repository, run `./install-omarchy.sh`. The
installer safely links the plugin and shell configuration into
`~/.config/omarchy`, backing up conflicts before replacing them.

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

- Calm includes extended-exhale, coherent 5.5-breath/minute, and cyclic-sigh
  patterns. Calm / Medium / 2 minutes is the default.
- Focus includes even breathing, skippable-hold box breathing, and no-hold
  alternate-nostril breathing.
- Energy uses light, even rhythms without retention. Its copy is explicitly
  experiential because an acute “energy” effect is not established.
- Recover includes pursed-lip breathing, extended exhale, and one optional
  short-hold pattern.
- Tradition includes Bhramari humming, gentle exhale-only Ujjayi, and Sitali.
  The panel distinguishes traditional framing from measured effects.

Pause always means “breathe normally” and resume begins again with an inhale.
Every hold can be skipped immediately. Breathe gently rather than maximally;
stop and return to normal breathing for dizziness, tingling, unusual
breathlessness, pain, faintness, or panic. This plugin is a wellness pacing
tool, not medical advice or treatment.

## Sources

- [Lin, Tai & Fan (2014)](https://pubmed.ncbi.nlm.nih.gov/24380741/), a
  two-minute comparison of slow-breath pacing ratios.
- [Balban et al. (2023)](https://doi.org/10.1016/j.xcrm.2022.100895), a
  randomized trial of five-minute daily cyclic sighing and box breathing.
- [Mason et al. (2013)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3655580/), a
  comparison of ordinary slow breathing and Ujjayi variants.
- [Telles et al. (2017)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5755948/),
  an alternate-nostril breathing crossover study.
- [Haṭha Yoga Pradīpikā, chapter 2](https://en.wikisource.org/wiki/Hatha_Yoga_Pradipika/2),
  for the traditional framing of Nadi Shodhana, Bhramari, Ujjayi, and Sitali.

Detailed evidence, limitations, implementation notes, and safety sources are
kept in [`research/`](research/).

## License

MIT

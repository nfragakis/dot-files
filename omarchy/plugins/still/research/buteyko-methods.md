# Buteyko-inspired breathing for Still

Research note, 2026-08-19. This is a conservative product-safety adaptation for
an unsupervised desktop wellness pacer, not a clinical Buteyko course, asthma
treatment, or medical advice.

## Recommendation in brief

Offer only two closely bounded Buteyko-inspired choices in the ordinary Still
rotation:

1. **Quiet nasal breathing:** small, silent nasal breaths with no programmed
   hold.
2. **Reduced breathing:** the same quiet nasal scaffold with one optional,
   immediately skippable one-second natural pause after exhale.

Both should be seated, hands-free, and deliberately gentle:

- invite quiet nasal breathing and relaxed shoulders, jaw, and lower ribs;
- let the breath be smaller than a full breath, but never force suppression,
  maximal emptying, or air hunger;
- provide an immediate return to normal breathing and stop action; and
- describe the result as an app adaptation, not as the Buteyko Method or a
  validated treatment dose.

Still uses `2 in · 3 out` as a **product timing scaffold** so the cue suggests a
small breath rather than a long, deep one. Reduced Breathing adds the optional
one-second natural pause described in the Association's progressive material.
Neither count is a canonical Buteyko ratio or validated dose. The original
trials and professional training material describe reduced volume, nasal
breathing, relaxation, and individualized pauses; they do not establish a
universal inhale/exhale ratio for a beginner. The UI therefore labels both as
**Buteyko-inspired** app adaptations.

Do not implement a control-pause stopwatch, progress score, personal best,
competitive hold, extended pause, maximum pause, walking hold, or hold after a
full inhalation. If a future expert-reviewed mode ever includes a Buteyko
control pause, it belongs **after a normal, gentle exhalation**, ends at the
first clear urge to breathe, and is followed by an easy nasal breath. There is
no evidence-based universal number of seconds that an unscreened app should
target.

## What the method actually contains

### 1. Quiet nasal breathing and reduced volume

The common clinical description is not “take deep breaths.” In the Eucapnic
Buteyko arm of a randomized asthma trial, participants were taught exercises to
reduce the **frequency and depth** of breathing. The intervention was delivered
in five two-hour teaching sessions, followed by at least 15 minutes of practice
twice daily for six months; it also included breath-hold recording, night-time
mouth taping, and lifestyle advice. That is a structured, taught program, not a
two-minute desktop sequence. [Cooper et al., 2003][cooper]

The 2024 randomized trial likewise described deliberate hypoventilation or
“reduced breathing,” usually sitting, with attention to the participant’s own
breathing pattern. The same study included extended and maximum pauses and a
walking exercise, but those components were taught in a five-day course with a
booster session and 20 minutes of home practice twice daily. [Vagedes et al.,
2024][vagedes]

The Buteyko Breathing Association’s beginner diary describes the practical
cue more specifically: sit comfortably, breathe smoothly and quietly through
the nose, relax the body, minimize unnecessary upper-chest movement, and
continue gentle breathing. It also offers a separate ten-minute relaxed set
with no breath holding. This is useful training material, not evidence that a
two-minute app session has the same effect. [Buteyko Breathing Association
Practice Diary][diary] [Buteyko Breathing Association beginner sets][beginners]

For Still, “reduced” must mean **less effort and less volume while remaining
comfortable**, not shallow, starved, or mechanically suppressed breathing.
Users should be free to breathe normally, open the mouth, shorten a cue, or
stop whenever nasal breathing is blocked or the pattern feels uncomfortable.

### 2. The control pause is a post-exhalation test, not a pacing ratio

The control pause (CP) is consistently described as a breath hold after a
normal or gentle exhalation at ordinary end-expiratory volume:

1. breathe normally through the nose;
2. take a normal, gentle breath in and out (not a maximal breath);
3. gently close the nose and hold only until the first definite urge or air
   hunger; and
4. release the nose and resume a normal, gentle nasal breath immediately.

The 2024 trial explicitly says the pause should be extended only long enough to
allow normal nasal breathing immediately afterward. The professional diary
gives the same post-exhalation sequence and says that needing force or a large
recovery breath means the pause was too long. [Vagedes et al., 2024][vagedes]
[Buteyko Breathing Association Practice Diary][diary]

Therefore, if a later supervised feature ever needs a CP cue, it is **after
exhalation, not after inhalation**. A hold after a full inhalation is a
different breath-hold stimulus and should not be silently substituted for CP.
The cited Buteyko sources do not establish an inhale hold as a core element.

The professional literature describes two stopping conventions: first
recognizable difficulty/urge to breathe, or the first involuntary respiratory
movement. Those are measurement conventions for trained assessment, not a
reason for a consumer app to make users wait for involuntary movement.
[Courtney & Cohen, 2008][courtney]

### 3. The natural pause is not the control pause

The Association’s progressive diary describes noticing the natural pause
between breaths and, in a later week, resting for about one second between
small breaths. It also says to let breathing return to normal without taking a
deep breath. This is an optional teacher-led progression, not a validated
one-second beginner prescription and not the same thing as timing a CP.
[Buteyko Breathing Association Practice Diary][diary]

For an unsupervised pacer, a visible or audible **normal-breath recovery** is
preferable to a programmed hold. If a micro-pause is ever added, it should be
immediately skippable and described as a natural pause, never as a target to
extend.

## Timing: what is and is not supported

| Element | Timing found in sources | Still decision |
|---|---|---|
| Relaxed/reduced breathing | The Association offers a 10-minute no-hold set; its diary describes a couple of minutes settling followed by about three minutes of gentle breathing before returning to normal. | A two-minute session may be an approachable adaptation, but no study validates it as a Buteyko dose. |
| Full taught program | Cooper et al.: at least 15 minutes twice daily after five two-hour lessons. Vagedes et al.: 20 minutes twice daily after five 90-minute lessons and a booster. | Do not present Still’s short session as equivalent to either program. |
| Natural pause | About one second between breaths appears in the Association’s week-two progression. | Do not make it a required beginner hold or a scored metric. |
| Control pause | Individual duration until first clear urge/air hunger after a normal exhalation; no universal beginner seconds. | Omit from the unsupervised default. If ever used, make it optional, post-exhale, immediately skippable, and non-competitive. |
| Extended pause | The Association’s teacher-led diary describes an extra 5–10 seconds beyond a person’s CP and warns users with high blood pressure, heart conditions, epilepsy, diabetes, or other health problems to consult a teacher first. | Do not implement in the desktop plugin. |
| Maximum pause | The 2024 trial defined this as holding as long as possible until moderate discomfort. | Do not implement, record, reward, or progressively lengthen it. |

The precise seconds in `4 in · 6 out` should therefore be described as an app
adaptation inherited from Still’s gentle slow-breath pacing, not as a Buteyko
protocol. The source-supported beginner behavior is “quiet, relaxed, nasal,
smaller if comfortable, and no strain,” not a count that every user must
complete.

## Assessment of the two proposed app adaptations

### `2 in · 3 out · 1 natural pause`

**Defensible only as a gentle, explicitly labeled app adaptation.** The
Association’s progressive material does describe a roughly one-second natural
pause between small breaths, so a one-second pause after the exhale is closer
to Buteyko training language than a hold after the inhale. However, the
`2-second inhale · 3-second exhale` timing is not a Buteyko trial protocol, and
the source describes the pause as something to notice and relax into—not a
breath-hold target. The six-second cycle is about 10 breaths/minute; that rate
is not itself evidence of hyperventilation, but the user must keep the breaths
small and quiet.

If retained, use it only with these constraints:

- label the phase **“natural pause”**, not “hold” or “control pause”;
- show no air-hunger or CO₂ claim, and never require completion of the count;
- make the pause immediately skippable and let the user breathe normally at any
  point; and
- keep the copy “small and quiet if comfortable,” not “breathe less” as a
  command.

The safer default remains no pause. If the implementation cannot distinguish a
soft natural pause from a scored hold, remove the one-second phase.

### `1–2–3–2–1` mini pauses

**Not defensible as an unsupervised symptom-relief feature in its current
framing.** The Association’s diary does give this exact post-exhale sequence,
with one-, two-, three-, two-, and one-count pauses, and says it may be
repeated for up to five minutes. But it presents the exercise for the first
sign of breathlessness and tells asthma readers to try it *instead of* using a
rescue inhaler, then use the inhaler if still breathless. That medical
substitution is inappropriate for Still and conflicts with current asthma
guidance. [Buteyko Breathing Association Practice Diary][diary] [NHS asthma
guidance][nhs-asthma]

Prefer to omit this sequence from the normal rotation. If product scope
requires retaining it, it must be renamed something like **“post-exhale pause
ladder”**, be an opt-in seated wellness experiment with no breathlessness,
asthma, CO₂, or rescue-medication language, run for one short cycle rather
than a five-minute repeat, and provide an always-visible skip/normal-breath
action. It should never be presented as more advanced, more effective, or a
way to build hold time. Even with those changes, it is less defensible than
the `2/3/1` adaptation because it deliberately escalates the pause to three
seconds.

## What the evidence does—and does not—show

The best-known primary studies are condition-specific and substantially more
intensive than Still:

- In Cooper et al.’s 90-person asthma trial, the Buteyko group had lower
  symptoms and bronchodilator use after six months, but no difference in
  methacholine bronchial responsiveness, FEV1, exacerbations, or ability to
  reduce inhaled corticosteroids. Participants had screened asthma and
  practitioner teaching. [Cooper et al., 2003][cooper]
- Vagedes et al.’s randomized trial enrolled adults with asthma, taught the
  method on five consecutive days plus a booster, and used 20-minute home
  sessions twice daily for three months. It reported improved CP and some
  asthma-control measures, but the sample was small, the intervention bundled
  reduced breathing with extended and maximum pauses, and it was not a study
  of healthy desktop users or two-minute sessions. One participant in the usual
  treatment group was hospitalized for sinusitis/otitis; no other adverse event
  was reported in that trial. [Vagedes et al., 2024][vagedes]
- Courtney and Cohen tested the underlying CP claim in 83 adults. Breath-hold
  time performed according to Buteyko protocols did **not** predict resting
  end-tidal CO₂; the weak significant relationship they found was in the
  opposite direction from the Buteyko prediction. A CP number must not be
  presented as a user’s CO₂ level, oxygenation, health status, or diagnosis.
  [Courtney & Cohen, 2008][courtney]
- GINA’s 2026 asthma strategy treats breathing exercises as a possible adjunct
  for symptoms and quality of life, while noting no consistent lung-function
  effect and no reduction in exacerbation risk. This supports modest adjunctive
  wording, not “cures asthma,” “normalizes CO₂,” or medication changes.
  [GINA 2026 Strategy Report][gina]

Repeated or maximal breath holding also has a performance-training effect. In
a primary physiology study, the initial no-sensation period after an
end-expiratory hold was less affected by repeated trials than total maximum
hold time, which improved with successive attempts. That makes “beat your CP”
mechanics particularly unsuitable: the app would reward tolerance of discomfort
rather than comfortable breathing. [Nishino et al., 1996][nishino]

In healthy volunteers, simple 20-second breath holds increased arterial
pressure by about 11 mmHg and sympathetic nerve activity to more than three
times baseline. Deep inspiratory clinical breath holds can also produce large
blood-pressure rises. These studies do not show that a brief, comfortable CP
is dangerous for every person; they do show why an unscreened app should not
target long or maximal apnea, add a “personal best,” or imply that discomfort is
progress. [Morgan et al., 1993][morgan] [Parkes et al., 2014][parkes]

## Do not implement in Still

1. **No CP/BOLT health score.** Do not show thresholds such as “under 10 is
   unhealthy,” map seconds to CO₂, infer hyperventilation, or store a baseline.
   CP is not validated as a consumer diagnostic or physiological readout.
2. **No maximum or extended pause.** Do not ask users to hold “a little longer
   than comfortable,” wait for involuntary respiratory movement, or hold until
   moderate discomfort. Do not add escalating holds, streaks, leaderboards,
   badges, or personal-best language.
3. **No inhale hold.** Do not turn Buteyko into box breathing by inserting a
   hold after a full inhale. The Buteyko CP is post-exhalation; the app’s
   default should have no hold at all.
4. **No pre-hold hyperventilation or deep breathing.** Do not combine rapid or
   maximal breaths with a retention. Do not cue “fill the lungs,” “empty
   completely,” “push through,” or “tolerate the air hunger.”
5. **No exercise or hazardous context.** Do not add walking/standing breath
   holds, or suggest use while driving, bathing, swimming, in water, at
   heights, or during physical exertion. The source programs’ walking drills
   were taught progressively; they are not suitable for a desktop general-
   wellness default.
6. **No mouth taping or nose pinching as a default feature.** The trials and
   Association material used mouth taping only as part of a taught program.
   Still can cue voluntary nasal breathing while awake; it should never force
   the mouth closed, and a blocked nose must be an immediate reason to return
   to normal breathing or stop.
7. **No medical substitution.** Do not tell users to reduce, skip, or replace
   asthma/COPD medication, or to use a Buteyko cue during an acute attack.
   GINA says breathing exercises are adjunctive; the NHS directs people having
   an asthma attack to sit upright, follow their reliever/action plan, and seek
   urgent help when symptoms worsen or do not improve. [GINA 2026 Strategy
   Report][gina] [NHS asthma guidance][nhs-asthma]

## Suggested product copy

### Preset card

> **Buteyko-inspired · quiet nasal breathing**
>
> A gentle, smaller-breath practice for noticing relaxed nasal breathing.
> This short timer is an app adaptation, not a clinical Buteyko course or
> treatment.

### Setup cue

> Sit comfortably. If nasal breathing feels easy, breathe quietly through your
> nose and let the breath stay light and unforced. Smaller breaths are fine;
> never force, empty your lungs, or chase air hunger. There is no hold in this
> version.

### During-session cue

> Keep the jaw, shoulders, and lower ribs relaxed. Shorten the count or breathe
> normally whenever the rhythm feels strained. Stop for dizziness, tingling,
> unusual breathlessness, chest pain, faintness, or panic.

### Stop/recovery action

> **Breathe normally** — end this session

The stop action should be available throughout the session and should leave the
user in a normal-breath recovery state, never on a hold frame.

### Medical boundary

> Wellness only. This does not diagnose or treat asthma, COPD, anxiety, or
> breathing problems, and it does not replace prescribed medication or an
> asthma action plan. Seek urgent medical help for severe or persistent
> breathing difficulty, chest pain, fainting, blue lips, or confusion.

If a future expert-reviewed advanced mode is ever added, its warning should be
separate and blocking:

> **Advanced breath hold**
>
> This is not part of the gentle default. Hold only after a normal, gentle
> exhale; stop at the first clear urge to breathe and return to normal nasal
> breathing. Never hold to discomfort or a personal best. Practice seated in a
> safe place—never driving, standing, bathing, swimming, or in/near water. Skip
> this mode if pregnant, prone to fainting or seizures, or if you have heart,
> blood-pressure, lung, or other conditions without clinician guidance.

## Sources

- [Cooper S. et al. “Effect of two breathing exercises (Buteyko and pranayama)
  in asthma: a randomised controlled trial.” *Thorax* (2003).][cooper]
- [Vagedes K. et al. “Effect of Buteyko breathing technique on clinical and
  functional parameters in adult patients with asthma: a randomized, controlled
  study.” *European Journal of Medical Research* (2024).][vagedes]
- [Courtney R., Cohen M. “Investigating the claims of Konstantin Buteyko… the
  relationship of breath holding time to end tidal CO₂.” *Journal of Alternative
  and Complementary Medicine* (2008).][courtney]
- [Nishino T. et al. “Changes in the period of no respiratory sensation and total
  breath-holding time in successive breath-holding trials.” *Clinical Science*
  (1996).][nishino]
- [Morgan B. J. et al. “Neurocirculatory consequences of negative intrathoracic
  pressure vs. asphyxia during voluntary apnea.” *Journal of Applied Physiology*
  (1993).][morgan]
- [Parkes M. J. et al. “Assessing and ensuring patient safety during
  breath-holding for radiotherapy.” *British Journal of Radiology* (2014).][parkes]
- [Buteyko Breathing Association, *Buteyko Practice Diary and Quick Reference
  Guide*.][diary]
- [Buteyko Breathing Association, “Buteyko for Beginners.”][beginners]
- [Global Initiative for Asthma, *2026 Strategy Report*, non-pharmacological
  strategies.][gina]
- [NHS, “Asthma.”][nhs-asthma]

[cooper]: https://pmc.ncbi.nlm.nih.gov/articles/PMC1746772/
[vagedes]: https://pmc.ncbi.nlm.nih.gov/articles/PMC10782792/
[courtney]: https://pubmed.ncbi.nlm.nih.gov/18315509/
[nishino]: https://pubmed.ncbi.nlm.nih.gov/8976812/
[morgan]: https://pubmed.ncbi.nlm.nih.gov/8365996/
[parkes]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4207152/
[diary]: https://www.buteykobreathing.org/wp-content/uploads/2017/10/Buteyko-Breathing-Practice-Diary.pdf
[beginners]: https://www.buteykobreathing.org/videos/buteyko-for-beginners/
[gina]: https://ginasthma.org/wp-content/uploads/2026/05/GINA-2026-Strategy-Report-WMS.pdf
[nhs-asthma]: https://www.nhs.uk/conditions/asthma/

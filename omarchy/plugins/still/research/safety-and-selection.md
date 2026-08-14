# Still breathwork: safety and protocol selection

Research date: 2026-08-14

This is a product-safety review for a general-wellness pacing tool, not medical advice or a clinical protocol.

## Executive recommendation

- A **comfortable, no-hold slow breath** is the best default for an unsupervised two-minute session. Still's proposed default of **Calm / Medium / 2 minutes** maps to `5 in · 5 out` (six breaths/minute) and is reasonable if the UI says to breathe lightly and shorten the count whenever it feels strained. `4 in · 6 out` is an equally strong alternative with a gentler exhale emphasis.
- Describe two minutes as a **brief reset or practice starter**, not a validated treatment dose. The most directly relevant randomized trial used five minutes daily for 28 days, and a systematic review found that effective stress/anxiety interventions generally did not use sessions shorter than five minutes. Two minutes can still be a good product default because it is approachable; the health claims must remain modest. [Balban et al. 2023][balban] [Bentley et al. 2023][implementation-review]
- Put **rapid/deep breathing plus retention in a separate advanced class**, never in the default or normal random rotation. Evidence reviews specifically call for more safety research and adverse-event reporting for fast-paced breathwork. [Fincham et al. 2023][fincham]
- Do not use one alarming warning for every technique. Use a small global reminder for all sessions and a specific, blocking warning for advanced rapid-breath/retention sessions.
- Prefer cultural context over mystical physiological claims. It is appropriate to call *nadi shodhana* an alternate-nostril yogic practice or *bhramari* a humming yogic practice. Do not claim that a particular nostril uniquely “activates” or “calms” the nervous system: a 2024 randomized crossover study found no nostril-specific difference in oxygen consumption. [Singh et al. 2024][nostril-oxygen]

## What “safe pacing” means in this app

There is no single medically certified inhale/hold/exhale count that is safe for every person. The safest product rules are behavioral:

1. **Comfortable, not maximal.** Hyperventilation is ventilation beyond metabolic need, so it can result from breathing too deeply as well as too quickly. Its hypocapnia/respiratory alkalosis can produce breathlessness, chest discomfort, tingling, hand/face stiffness, dizziness, near-fainting, or fainting. [Merck Manual Professional][merck-hyperventilation]
2. **No strain and no contest.** A user should be told to shorten a phase, skip a hold, or return to normal breathing at the first urge to strain. The Stanford box-breathing trial gave the same reduce-the-count-if-straining instruction, and it studied screened adults rather than the general population. [Balban et al. 2023][balban]
3. **Default to no holds.** Short comfortable holds are used in box breathing, but maximal or prolonged apnea is a different stimulus. Studies in healthy volunteers show that voluntary apnea can raise sympathetic activity and blood pressure; maximal inspiratory holds produced pronounced blood-pressure rises in a small radiotherapy-safety study. This does not prove that a four-second box hold is dangerous, but it supports keeping holds optional and non-default for a mass-market unsupervised tool. [Morgan et al. 1993][apnea-sympathetic] [Parkes et al. 2014][apnea-bp]
4. **Never combine advanced breathwork with hazardous context.** Pre-hold hyperventilation suppresses the carbon-dioxide urge to breathe without adding much oxygen, allowing oxygen to fall to loss-of-consciousness levels before the usual warning. This is especially lethal in water. [Divers Alert Network][dan-hypoxia] The official Wim Hof guidance likewise says rapid/deep breathing with retention can cause light-headedness or fainting and must not be done while driving or in/near water. [Wim Hof Method safety/FAQ][whm-faq]
5. **Symptoms override the pacer.** The correct response to dizziness, tingling, unusual breathlessness, chest pain, palpitations, panic, visual changes, or feeling faint is to stop the exercise and breathe normally—not to “push through.” Merck lists these as possible manifestations of hyperventilation, while the American Heart Association advises stopping a breathing technique when dizziness/light-headedness occurs. [Merck Manual Professional][merck-hyperventilation] [American Heart Association][aha-breathing]

### Holds

- There is no evidence-based universal “safe maximum” hold for an unscreened app user. Avoid presenting a fixed retention as a target to conquer.
- Default protocols should have no holds. In non-advanced options, keep holds short, optional, and immediately skippable; never require a user to complete the countdown.
- Do not preserve a hold across pause. “Pause” must mean **breathe normally now**. Resume should begin from a normal-breath or inhale phase rather than continue the remaining hold.
- Never place an empty-lung retention directly after rapid breathing without the advanced gate and contextual warning.

### Pregnancy and health conditions

The cautions should be proportionate to the protocol:

- **Pregnancy is not a blanket contraindication to gentle breathing.** ACOG includes focused breathing within modified prenatal yoga, while advising pregnant people to discuss appropriate activity with their obstetric clinician and to stop for dizziness, faintness, chest pain, or concerning shortness of breath. [ACOG][acog-pregnancy]
- **Rapid breathing plus retention should not be offered during pregnancy without clinician approval.** The Stanford breathwork trial excluded pregnancy and heart disease, glaucoma, seizure history, and other moderate/severe conditions; it therefore cannot establish safety for those groups. The official Wim Hof guidance advises against its method during pregnancy and for epilepsy, and directs people with cardiovascular/oxygen/blood-pressure issues to a medical professional. [Balban et al. 2023][balban] [Wim Hof Method safety/FAQ][whm-faq]
- **Heart, blood-pressure, and lung conditions need a clinician check before advanced practice.** The American Heart Association explicitly advises people with heart or lung conditions to consult a health professional before its paced-breathing techniques. The American Lung Association recommends condition-specific breathing exercises and working with the health-care team for lung disease; a generic app should not imply that its pattern treats asthma, COPD, or unexplained breathlessness. [American Heart Association][aha-breathing] [American Lung Association][ala-breathing]
- **Seizure/fainting history and panic vulnerability warrant an advanced-protocol skip.** Official Wim Hof guidance excludes epilepsy and acknowledges rare fainting; hyperventilation overlaps substantially with panic symptoms and can itself provoke fear, dizziness, chest discomfort, and tingling. [Wim Hof Method safety/FAQ][whm-faq] [Merck Manual Professional][merck-hyperventilation]

These cautions apply most strongly to fast/deep breathing, long holds, or retention after hyperventilation. They should not imply that an ordinary comfortable 5:5 breath is inherently hazardous.

## Current Still implementation audit

> Resolution note: the implementation completed alongside this audit removed
> Power rounds, changed pause to a normal-breath recovery state that restarts
> at an inhale, made every remaining hold immediately skippable, and added
> specific stop-symptom copy. The findings below describe the pre-change
> `0.1.0` behavior and document why those changes were made.

### High priority

1. **Pause can lengthen a hold indefinitely.** In [`Panel.qml`](../Panel.qml), pause stops elapsed time while leaving the current phase displayed. If paused during `holdIn`, `holdOut`, `retain`, or `recover`, a compliant user may continue holding while the timer is frozen. Pausing must exit to “breathe normally”; resume should restart safely rather than continue a hold.
2. **Power rounds do not match the cited trial.** [`Protocols.js`](../Protocols.js) generates 30 breaths at 24 cycles/minute, then a 30-second empty-lung retention (45 seconds in round two), then a 15-second full-lung recovery hold. The Balban study's cyclic-hyperventilation arm used 30 deep/passive breaths followed by a **15-second** empty-lung hold, repeated for three rounds; it did not use Still's 30–45 second empty hold plus 15-second recovery hold. The paper also excluded several higher-risk groups. Still must not cite that trial as validation of the current Power sequence. [Balban et al. 2023][balban]
3. **The advanced acknowledgement is too narrow.** “I'm seated — continue” confirms position but not pregnancy, seizure/fainting history, or heart/lung/blood-pressure cautions. The warning should name light-headedness/fainting and the relevant skip/clinician-check groups.

### Medium priority

4. **“Stop if you feel unwell” is too vague.** Name dizziness, tingling, unusual breathlessness, chest pain/palpitations, panic, or feeling faint, and say “return to normal breathing.”
5. **The inhale-emphasized energy patterns need a “light, not deep” cue.** `4 in · 2 out` is 10 breaths/minute and `3 in · 1 out` is 15. Rate alone does not define hyperventilation; large repeated inhalations can still over-ventilate. These should not imply maximum lung filling or promise a safe energy boost.
6. **Closing/stopping needs an explicit recovery state.** After any hold or rapid pattern, the orb and copy should say “breathe normally” for several breaths. Do not end on a retention frame.
7. **No competitive mechanics.** Do not add hold records, streaks based on retention time, “personal best,” or escalating automatic retentions. The app should reward session completion, never physiological extremity.

## Candidate techniques ranked for a default two-minute session

“Suitability” combines likely physical tolerability, simplicity without a teacher, hands-free desktop UX, and whether two minutes plausibly preserves the technique. It does **not** mean that two minutes has been proven to deliver a clinical benefit.

| Rank | Candidate | Default suitability | What Still may accurately say | Safety/UX note |
|---:|---|---|---|---|
| 1 | **Extended exhale / *visama vritti*** (`4 in · 6 out`) | Excellent | A slow, exhale-emphasized calming pattern; longer-exhale breathing is used in both clinical education and breathwork research. | No hold, six cycles/minute, hands-free. Cue “gentle inhale, easy longer exhale,” not “empty completely.” [American Lung Association][ala-breathing] [Balban et al. 2023][balban] |
| 2 | **Resonance/even slow breath / *sama vritti*** (`5 in · 5 out`, or `4 · 4`) | Excellent | A simple slow rhythm intended to steady attention and breathing. Slow-paced breathing has a small-to-medium aggregate association with reduced stress, but individual benefit and ideal frequency vary. | No hold. `5:5` is a reasonable Calm/Medium default. Let users shorten it; do not claim everyone has a six-breath/minute “resonance.” [Fincham et al. 2023][fincham] |
| 3 | **Gentle cyclic sigh** (inhale, small top-up, long exhale) | Very good | In one remote randomized trial, five minutes daily for 28 days improved positive affect and reduced respiratory rate more than mindfulness meditation; this is promising, not definitive. | Use a comfortable first inhale and small second sip—not repeated forced maximal inflation. Evidence is for five, not two, minutes and screened adults. [Balban et al. 2023][balban] |
| 4 | **Bhramari** (humming exhale, “bee breath”) | Good optional | A traditional yogic humming practice. A five-minute randomized trial in treated hypertension found an acute HRV change but no significant blood-pressure reduction versus slow breathing. | No hold and naturally lengthens exhale, but it requires sound/privacy and evidence does not support strong benefit claims. [Ghati et al. 2021][bhramari] |
| 5 | **Nadi shodhana** (alternate-nostril, no hold) | Fair optional | A traditional alternate-nostril yogic practice that combines slow breathing with focused hand coordination. | Not hands-free; congestion and mobility can interfere. Most studies use much longer sessions. Do not claim left/right nostril-specific calming or energizing. [Singh et al. 2024][nostril-oxygen] |
| 6 | **Pursed-lip breathing** (`2 in · 4+ out`) | Fair, context-specific | A clinical breathing-control technique taught for asthma/COPD-related shortness of breath. | Appropriate as an explicitly educational “easy exhale” option, not a treatment promise; users with lung disease should follow their care plan. [American Lung Association][ala-breathing] |
| 7 | **Box breathing** (`4 · 4 · 4 · 4`) | Optional, not the universal default | A structured focus pattern with equal inhale, hold, exhale, hold. A screened-adult trial studied it for five minutes daily. | Holds can create air hunger. Add “skip/shorten any hold”; never preserve a hold through pause. Avoid “Deep box” as an automatic progression. [Balban et al. 2023][balban] [American Heart Association][aha-breathing] |
| 8 | **4-7-8 breathing** | Poor default; advanced/optional | A counted relaxation pattern popularized in wellness contexts. | The seven-count hold dominates a two-minute beginner session. AHA advises only three to five cycles for first-time users and stopping for dizziness/light-headedness. [American Heart Association][aha-breathing] |
| 9 | **Kapalabhati / bhastrika** (rapid yogic breaths) | Do not default | Traditional rapid practices sometimes translated as “skull-shining” or “bellows” breath. | Technique-sensitive, easy to over-ventilate, and not supported as a two-minute unsupervised default. Reviews find more adverse events with fast than slow pranayama and call for better fast-breath safety evidence. [Mütze et al. 2025][pranayama-review] [Fincham et al. 2023][fincham] |
| 10 | **Power/WHM-like hyperventilation + retention** | Exclude from default; preferably remove pending expert review | An advanced arousal/retention practice—not a general relaxation technique. | Can cause tingling, motor-control changes, dizziness, and fainting. Current Still timing lacks direct validation and needs the full advanced gate, a skip-hold control, seated/lying context, and contraindication copy. [Wim Hof Method safety/FAQ][whm-faq] [Merck Manual Professional][merck-hyperventilation] |

## Recommended in-app copy

Use layers so the ordinary slow-breath experience stays calm while the advanced risk is unmistakable.

### Global setup/footer copy

> Wellness only. Breathe gently—never force or chase a hold. Stop and breathe normally if dizzy, tingly, breathless, or unwell.

### Blocking copy for any rapid-breathing or retention-after-hyperventilation protocol

> **Advanced breathing**
>
> Rapid breathing and holds can cause dizziness or fainting. Practice seated or lying down—never standing, driving, or in or near water. Skip this if pregnant, prone to fainting or seizures, or if you have a heart, blood-pressure, lung/respiratory, or serious psychological condition unless your clinician says it is safe. Stop immediately for dizziness, tingling, unusual breathlessness, chest pain, palpitations, panic, or visual changes.

Suggested acknowledgement: **“I understand — start seated”**. Keep **“Choose a gentle pattern”** beside it as the equal-weight safe exit; do not make Enter automatically accept the warning.

### During-session safety action

> **Breathe normally** — end this hold/session

This action should always be visible during a hold and should be the default keyboard response to pause/escape from a hold.

### Urgent-symptom footer/help copy

> Chest pain, fainting, or severe/persistent breathing difficulty: stop and seek urgent medical care.

The American Lung Association treats shortness of breath with chest pain/pressure or fainting as an emergency warning, rather than something to self-treat with a pacer. [American Lung Association][ala-dyspnea]

## Benefit-language guardrails

- Prefer: “may help you settle,” “studied for stress regulation,” “a traditional focus practice,” or “some people find…”
- Avoid: “activates the vagus nerve,” “balances hemispheres,” “detoxes,” “oxygenates the blood,” “boosts immunity,” “treats anxiety,” or condition-specific therapeutic promises. Slow breathing changes respiratory and cardiovascular signals, but popular mechanism claims often outrun the evidence.
- For cyclic sighing, say the evidence is from one five-minute/day trial and avoid silently transferring its results to a two-minute version.
- For rapid methods, light-headedness and tingling are not proof that the method is working; they are reasons to scale back or stop.

## Sources

- [Balban M. Y. et al. “Brief structured respiration practices enhance mood and reduce physiological arousal.” *Cell Reports Medicine* (2023).][balban]
- [Fincham G. W. et al. “Effect of breathwork on stress and mental health: A meta-analysis of randomised-controlled trials.” *Scientific Reports* (2023).][fincham]
- [Bentley T. G. K. et al. “Breathing Practices for Stress and Anxiety Reduction: Conceptual Framework of Implementation Guidelines Based on a Systematic Review.” *Brain Sciences* (2023).][implementation-review]
- [Merck Manual Professional: Hyperventilation Syndrome.][merck-hyperventilation]
- [Divers Alert Network: Hypoxia in Breath-Hold Diving.][dan-hypoxia]
- [American Heart Association: Stress Management — Deep Breathing.][aha-breathing]
- [American Lung Association: Breathing Exercises.][ala-breathing]
- [American Lung Association: Shortness of Breath.][ala-dyspnea]
- [American College of Obstetricians and Gynecologists: Exercise During Pregnancy.][acog-pregnancy]
- [Wim Hof Method: official FAQ and safety cautions.][whm-faq]
- [Parkes M. J. et al. “Assessing and ensuring patient safety during breath-holding for radiotherapy.” *British Journal of Radiology* (2014).][apnea-bp]
- [Morgan B. J. et al. “Neurocirculatory consequences of negative intrathoracic pressure vs. asphyxia during voluntary apnea.” *Journal of Applied Physiology* (1993).][apnea-sympathetic]
- [Ghati N. et al. “A randomized trial of the immediate effect of Bee-Humming Breathing exercise…” *Explore* (2021).][bhramari]
- [Singh A. et al. “Traditional Nostril Yoga Breathing Practices and Oxygen Consumption.” *International Journal of Yoga* (2024).][nostril-oxygen]
- [Mütze K. et al. “Effectiveness of pranayama for mental disorders: a systematic review and meta-analysis…” *Frontiers in Psychiatry* (2025).][pranayama-review]

[balban]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9873947/
[fincham]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9828383/
[implementation-review]: https://pubmed.ncbi.nlm.nih.gov/38137060/
[merck-hyperventilation]: https://www.merckmanuals.com/professional/pulmonary-disorders/symptoms-of-pulmonary-disorders/hyperventilation-syndrome
[dan-hypoxia]: https://dan.org/alert-diver/article/hypoxia-in-breath-hold-diving/
[aha-breathing]: https://www.heart.org/en/healthy-living/healthy-lifestyle/stress-management
[ala-breathing]: https://www.lung.org/lung-health-diseases/wellness/breathing-exercises
[ala-dyspnea]: https://www.lung.org/lung-health-diseases/warning-signs-of-lung-disease/shortness-of-breath
[acog-pregnancy]: https://www.acog.org/womens-health/faqs/exercise-during-pregnancy
[whm-faq]: https://www.wimhofmethod.com/faq
[apnea-bp]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4207152/
[apnea-sympathetic]: https://pubmed.ncbi.nlm.nih.gov/8365996/
[bhramari]: https://pubmed.ncbi.nlm.nih.gov/32620379/
[nostril-oxygen]: https://pubmed.ncbi.nlm.nih.gov/38899139/
[pranayama-review]: https://pubmed.ncbi.nlm.nih.gov/40896223/

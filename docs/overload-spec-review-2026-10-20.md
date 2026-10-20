# Review: progressive overload spec (2026-10-20)

Source: `docs/overload-module-spec.md` (the user's spec, Czech). It revises E33 (targets v1), which is built and
verified on dev (`services/overload.py`, migration 0019) but **not deployed**. **Accepted 2026-10-20 (E35): the user took
every recommendation below.**

## Verdict
The spec is sound and fits the project's rules: deterministic, explainable rules, unknown ≠ 0, history never
rewritten, RIR treated as a soft signal. Its straight-sets rule (§6.1) fits the user's data much better than E33 (see
the facts below). Its problems:
1. It relies on **stored targets** ("if the user met the last target", "what was recommended vs. done"), but never
   says to store them. Today the target only lives in the phone's pre-filled inputs.
2. Several **thresholds are left open**: what counts as a significant drop, how many sessions make a stall, when a
   jump is too big, and what makes a previous exercise "unusually demanding".
3. It **contradicts two choices of E33** that the user made or approved: adding sets automatically and the automatic
   deload.
4. §5 assumes context we don't record (machine settings, range of motion, rest). §7 and §8 are separate features
   rather than part of the targets.

## Facts from the data (dev copy of prod, last 12 months)
- 639 exercise sessions: 557 at one weight; 52 with a heavier first set followed by lighter ones (the top + back-off
  shape: Chest Fly, Pull Up, Squat, Reverse Fly); 30 ramping up (lighter sets first, logged as normal sets).
- Of the 557 one-weight sessions, 481 have falling reps and 64 equal reps. The user trains close to failure, so E33's
  "every set at the top of the range" would keep the weight far too long. §6.1's first / middle / last rule matches.
- 0 of 2,361 sets carry RPE, and the warm-up / drop / failure set types were never used.

## Conflicts with E33
| E33 (dev) | Spec | Proposal |
|---|---|---|
| Adds a set up to 3 before adding reps (user request, 2026-10-19) | §3, §13: never change the set count during normal progress | Off by default; `sets_max` becomes an opt-in per exercise (empty = never) |
| Automatic deload target after 3 stalled sessions | §9: only a suggestion the user confirms | Warning + "Použít dnes" suggestion (this workout only) |
| Weight goes up when every set reaches the top | §6.1: first set at the top, middle sets ≥ min, last set ≥ min − 1 | Adopt §6.1 |
| +1 rep on the weakest set | §6.1: the first set first, then the first later set under its bound | Adopt §6.1 |
| One step lighter as soon as the best set is below the range | §6.3: no auto-drop after a single session | One session = "Prověřit propad"; two comparable sessions in a row = one step lighter |
| Block = the most frequent weight of the session | §3: roles must be explicit, never guessed from weights | Strategy on the exercise, role stored on each logged set; the heuristic only bootstraps history without roles |
| ~10 % lighter after a break of more than 21 days | Not covered | Keep it as §11's "safe default" (label *Po pauze*) |

## Gaps → proposed defaults
- **Stored targets:** `planned_weight_kg` / `planned_reps` on each logged set. Missing (old sets, AI dictation, the
  workout editor) = no plan; the last actual result then counts as met.
- **Significant drop** (§6.3, scenarios 3–4): a working set below rep_min **and** ≥ 2 reps under its target (or under
  the same set in the last comparable session). For example, 10, 5, 5 after 10, 6, 5 is a weak set (+1 on set 2),
  while 10, 4, 4 after 10, 7, 6 is a drop.
- **Repeated drop** (scenario 5): drops in 2 comparable sessions in a row → one weight step lighter (*Snížit váhu*).
  The reps come from the user's own sets at that weight where they exist.
- **Stall** (§9, scenario 12): 4 comparable sessions at the same planned weight without beating the block's best total
  reps → info only (*Možné zpomalení*). Totals falling over 3 sessions → *Opakovaný pokles* plus a deload suggestion
  (−10 % weight or −1 set, this workout only).
- **Jump too big** (§6.2): the estimated first-set reps at the new weight fall below rep_min → warning on the label.
- **Low confidence** (§11, scenario 13): fewer than 2 comparable sessions, or the last session's roles don't match the
  current strategy → label *Málo dat*, repeat the last known weights / reps.
- **RIR:** the spec says the target RIR "affects expected effort", but no rule uses it. v1 only stores and shows RIR.
  - Confirmed RIR goes into the existing `rpe` column (RIR-based RPE: 0 → 10, 1 → 9, 2 → 8, 3+ → 7). Null =
    not confirmed, and set type *failure* = a confirmed 0.
  - The target RIR is shown as guidance. No decision depends on RIR until there is data.
- **Back-off rep range:** not specified → the exercise's own range in v1.
- **Set count from the template:** workouts also start empty or gain exercises on the fly. So: the template's count
  when started from one, otherwise the last session's count. The endpoint takes `sets=N`.
- **Not covered by the spec:**
  - warm-up and drop sets: copied from last time, outside the progression;
  - bodyweight without a load: reps only, no cap;
  - time / distance exercises: no target;
  - long breaks: see above.
- **Comparability (§5):**
  - variants are already separate exercises, and the equipment is an exercise attribute;
  - machine settings and range of motion aren't recorded;
  - rest could be approximated from `completed_at` gaps, but sets are often ticked late, so it is not used in v1;
  - an unplanned weight change is derived (actual ≠ planned);
  - "unusual session" is a new toggle.
- **Sources (§14):** not re-checked here. The spec itself says the thresholds are product decisions, so they don't
  change the design.

## Mapping onto the current model
| Spec concept | Today | Change |
|---|---|---|
| Rep range, weight step | `exercises.rep_min/rep_max/weight_step` (0019, dev) | keep |
| Working sets count | template JSONB sets / last session | none; `sets=N` on the target request |
| Automatic set increase | `exercises.sets_max` (0019), default 3 | default null = never (opt-in) |
| Target RIR | – | `exercises.target_rir` smallint null (null = 1, 0 = to failure) |
| Strategy | – | `exercises.strategy`: `straight` (default) / `top_backoff` |
| Role of a set | `set_type` normal / warmup / drop / failure | `workout_sets.role`: `straight` / `top` / `backoff`, null = no plan. Set when the workout is planned and kept, so the history isn't reinterpreted after a strategy change |
| Recommended target | only in the phone's inputs | `workout_sets.planned_weight_kg`, `planned_reps` |
| Confirmed RIR | `workout_sets.rpe` (never used) | reuse (see above) |
| Unusual exposure | – | `workout_sets.unusual` bool on that exercise's sets in the workout, sent with the existing per-set PUT (offline queue unchanged) |
| Unplanned weight change | – | derived: `weight_kg ≠ planned_weight_kg` |
| "Use this change next time" | – | rewrite that session's `planned_*` to the actual (same PUT) |
| Target + reasons + warnings | `LastPerformance.target` (E33) | `ProgressionTarget` gains per-set `role`, `reason` (plus_rep, weight_up, backoff_progress, return_up, hold, check_drop, lower, comeback) and `priority`, exercise-level `warnings` (stall, decline, big_jump, low_confidence), optional `suggestion` (deload variant); query key → v3 |
| Fatigue between exercises (§7) | `muscle_group`, `exercise_order` | v1: a hint in the *Prověřit propad* text when an earlier exercise in the same session trained the same group; targets never change |
| Muscle-group overview (§8) | per-exercise `exercise_progression`, Partie charts | later: per-exercise trend labels grouped by muscle group in Grafy |
| Determinism (§11) | computed on read from history + settings | keep; `planned_*` and `role` snapshots keep old sessions interpretable |
| Templates | JSONB `{exercise_id, sets: [{set_type, weight_kg, reps}]}` | no schema change; their kg × reps only fill exercises without history |

New columns go into a new migration (0021): 0019 can't be rewritten any more, because E34's 0020 (races, another
session) already builds on it. None of 0019–0021 is on prod yet, and deploying dev ships them in order.

## Rules v2 (proposal)
Blocks: *straight* = every working set; *top_backoff* = the first working set (top) and the rest (back-off). Each block
progresses on its own; a back-off set never follows the top set automatically. Per block, from the last comparable
session, the first rule that matches wins:
1. No comparable data → repeat the last known weights / reps (*Málo dat*).
2. Break > 21 days → ~10 % lighter (*Po pauze*).
3. Drop (see above) → repeat the target (*Prověřit propad*). The second one in a row → one step lighter (*Snížit
   váhu*).
4. Target missed by 1 rep → repeat it (*Udržet cíl*).
5. First set ≥ max, middle sets ≥ min, last set ≥ min − 1 (a one-set block: first ≥ max) → + step (*Zvýšení váhy*;
   for a back-off block *Back-off progres*, or *Návrat na vyšší váhu* when it climbs back to a weight it was dropped
   from).
   - Reps at the new weight: the user's own sets at that weight if there are any. Otherwise Epley for the first set
     and the session's own drop-off ratios for the rest.
   - Warning when the first set lands below min.
6. Otherwise +1 rep (*+1 opakování*): the first set while it is below max, then the first later set under its bound
   (middle: min, last: min − 1). The priority set is marked. Opt-in: add a set first while below `sets_max`.
7. Stall / decline → warnings and a confirmable deload suggestion, never automatic.

## UI (v1)
- The target line per exercise stays, with the reason per block. The priority set's row is marked.
- After a set is ticked, the target is shown next to the actual value when they differ.
- RIR: a slim 0 / 1 / 2 / 3+ row appears under a ticked set. Nothing selected = not confirmed (the target RIR shows
  greyed). It is never required.
- Weight change:
  - a chip offers "Propsat 37,5 kg do sérií 3–4", with undo;
  - it never touches ticked sets or another role;
  - a second option, "i příště", makes the change part of the plan.
- A "Neobvyklý průběh" toggle on each exercise in the active workout. Suggestions apply to this workout only
  ("Použít dnes").
- The exercise sheet gains the strategy (Straight / Top + back-off) and the target RIR.

## Phasing
- **A** (backend): migration, rules v2, API, behaviour tests for scenarios 1–9 and 12–14.
- **B** (UI): everything in *UI (v1)*.
- **C** (later): §7 beyond the hint, §8 overview (scenario 11), rest-based comparability.
- E33 as built is not deployed; deploy after A + B.

## Decisions needed
1. Set count: default never, opt-in per exercise (recommended), or keep adding sets as in E33.
2. The defaults above (drop, repeated drop, stall, big jump, low confidence, RIR in `rpe`, back-off range = the
   exercise's, strategy per exercise rather than per template entry): accept as a whole.
3. Comeback after a break: keep the −10 % pre-fill (recommended) or make it a suggestion only.
4. Scope and timing: A + B now, C later, deploy after B (recommended).

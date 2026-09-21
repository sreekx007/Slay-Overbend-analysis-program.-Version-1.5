# T5 — L6 Solve · **MILESTONE M1 BLOCKED**

**Status:** solver BUILT 21 Sep 2026 (`slay/solve/{contact,passage}.py`,
`rebuild/tests/test_passage.py`, 14 tests). **M1 NOT VALIDATED — its target
could not be reproduced from the reference code.** Decision needed; see §4.

---

## 1. What was built

`solve(problem, state_in=None) -> (Result, state_out)`, ported from
`_solve_state_sliding` and **not** from `_solve_state`. The node-snapped path
is retired: it constrains one node's `uy` per roller, which fights the 2.07 m
of tangential slide a material point makes over the rollers by SR6 (R = 85)
and was measured producing ~2.4% spurious strain concentration against ~0.29%
pure-arc bending.

| piece | where |
|---|---|
| general linear constraint, rank-1 `pen·aaᵀ` | `solve/penalty.apply_linear` |
| contact slots and the active set | `solve/contact.py` |
| Problem → kernel mesh | `solve/kernel.mesh_of_problem` |
| adaptive Newton, cutback, freeze/commit | `solve/passage.py` |

**The four things the loop owes its caller**, all present: adaptive cutback
(½ down to 1/64, ×1.4 back), divergence detection (NaN, |U| > 100 m,
|dU| > 1 m in one step), plastic freeze and commit per increment, and the
active set re-decided *between* Newton passes rather than inside them.

**The two active-set tests are not the same test.** Release is
reaction-based (`pen·r < −1 N`), re-contact is gap-based (`r ≥ −1e-9 m`). An
active penalty constraint sits at |r| ~ 1e-10 m, so a gap threshold could
never fire on it — the *sign* of that tiny residual is what encodes push
against pull. An inactive one is not enforced, so its gap is real.
`one_sided` decides who may release, as an **exempt set**: "may not release"
is a property of the roller, not of the current reaction.

---

## 2. What is proven

**The contact formulation is exact.** On the pure-arc case — every roller
bidirectional, no gravity, no tension — all eight targets are met to
**1e-13 m**, including an **8.897 m** normal displacement at SR6 on a pipe
that starts straight:

| | VR2 | VR1 | SR1 | SR2 | SR3 | SR4 | SR5 | SR6 |
|---|---|---|---|---|---|---|---|---|
| target (m) | 0 | 0 | 0 | −0.3756 | −1.4926 | −3.3210 | −5.8118 | −8.8971 |
| miss (m) | 3e-14 | 9e-14 | 2e-14 | 6e-14 | 1e-15 | 2e-14 | 3e-13 | 3e-13 |

Mean strain through the arc region is **0.28–0.31%** against pure bending
onto R of 0.2391% — more than pure bending and not a multiple of it, which is
what discrete supports at 8 m spacing should give. Past the last roller the
pipe carries **zero** strain, correctly: nothing constrains or loads it there.

The active-set decisions, the release bar within an increment, the ramp from
the entry state, the bounded loops and the J2 freeze/commit are unit-tested.

---

## 3. What is NOT proven

**M1.** Nothing here has been checked against a reference result, because the
reference result could not be generated.

---

## 4. M1's real benchmark — resolved 21 Sep 2026

The source paper was supplied: *Towards AI-Assisted Concept Design of ILS*
(IJRASET Vol. 14 Issue VII, July 2026). **The benchmark is an Abaqus model**,
and §VI Study 1 / TABLE X is the plain-pipe case M1 gates on.

### The benchmark as the paper states it

| | |
|---|---|
| pipeline | 16 in, **406 mm OD x 21 mm WT** — matches `config` |
| elements | B31 beam, mesh **2 x OD** |
| rollers | rigid R3D4 surface, **300 mm radius** — matches `config` |
| **roller spacing** | **9 m c/c** — `config` has **8.0 m** |
| tension | **120 MT** |
| contact | **single-roller model**, stated conservative |
| steps | pretension, bend, gravity, lay tension, translate |

**TABLE X** (plain pipe, T = 120 MT): **0.46%** at R = 70 m, **0.38%** at
R = 85 m, **0.32%** at R = 105 m, all Phase 1.

Note the paper is internally inconsistent about Config C: TABLE X says
R = 105 m, §VII TABLE XIII says R = 100 m.

### Three sets of numbers, not two

| R | **paper (Abaqus)** | repo §6 table | old program, 8 m | old program, 9 m |
|---|---|---|---|---|
| 70 m | **0.46** | 0.494 | 0.4800 | 0.5081 |
| 85 m | **0.38** | 0.384 | 0.3626 | 0.3777 |
| 100 m | — | 0.316 | 0.2847 | 0.2932 |
| 105 m | **0.32** | — | 0.2665 | 0.2733 |

The repo's §6 regression row is **not** the paper's benchmark. It is a Python
result, at a configuration that sits near but not on either spacing.

### Where the old program and Abaqus diverge

TABLE XI (R = 70 m, diameter x tension) is the cleanest comparison — the
zero-tension rows have an independent analytical check, `eps = D/2R`:

| OD | T | paper | analytic | paper vs analytic | old prog (8 m) | **old vs paper** |
|---|---|---|---|---|---|---|
| 168 mm | 0 | 0.13 | 0.12 | +8% | 0.1415 | **+8.8%** |
| 406 mm | 0 | 0.33 | 0.29 | +14% | 0.3603 | **+9.2%** |
| 508 mm | 0 | 0.42 | 0.36 | +17% | 0.4556 | **+8.5%** |
| 168 mm | 100 | 0.29 | — | | 0.3200 | **+10.3%** |
| 406 mm | 100 | 0.42 | — | | 0.4626 | **+10.1%** |
| 508 mm | 100 | 0.54 | — | | 0.5560 | **+3.0%** |

**At R = 70 the old program runs a uniform +8.5 to +10% above Abaqus**, held
across a 3x diameter range and two tension levels. A stable offset of that
kind is a modelling difference, not an error — the single-roller idealisation
the paper itself flags as conservative, and point contact against a finite
300 mm roller surface, both push the same way.

**The divergence is in the R-trend, and it is the actual finding.**
Amplification over the analytical `D/2R`:

| | R = 70 | R = 85 | R = 105 |
|---|---|---|---|
| paper (Abaqus) | +58% | +59% | **+65%** |
| old program, 8 m | +65% | +52% | **+38%** |

The paper's amplification **rises** with stinger radius; the old program's
**falls**. They cross near R = 80 m, which is why R = 85 agrees to a few
percent and R = 105 is 15% apart. This is not a scale factor and no single
setting reconciles it — it is a difference in how the two models respond to
stinger radius, and it is the thing to chase.

### Consequences for M1

1. **M1's target is the paper's, at the paper's configuration**: 0.46 / 0.38
   / 0.32 at R = 70 / 85 / 105, T = 120 MT, **9 m roller spacing**, 406 x 21.
2. **`config.ROLLER_SPACING` is 8.0 m and the benchmark is 9 m.** The whole
   Python toolchain uses 8; the Abaqus benchmark uses 9. Not changed here —
   it moves every number in the project and is a decision, not a typo.
3. **The repo's §6 plain-pipe row should be retired or re-labelled.** It
   matches neither the paper nor a reproducible configuration, and it is the
   row that sent this investigation down a blind alley — including a
   well-evidenced but wrong hypothesis that the benchmark was a 22 in pipe
   (the 1.375x ratio is exactly 22/16, and a 22 in run reproduces R = 70 to
   0.3%; the paper says 406 mm, so it is a coincidence).
4. **Agreement should be judged against Abaqus with a stated tolerance**, not
   as equality. The old program is +9% at R = 70 and -15% at R = 105; a
   rebuild landing in that band has reproduced the old program's behaviour,
   which is what §6 is for.

## 5. First run against the benchmark — 21 Sep 2026

`config.ROLLER_SPACING` moved **8.0 m -> 9.0 m** to match the benchmark.

### The repo already contained the evidence, and had explained it away

`test_arc_vs_rectangular_divergence` recorded 1.460 m and 2.142 m with this
note: *"Tracker item 16 quotes 2.07 m and 3.04 m, which reproduce only at 9 m
spacing -- a test written from those numbers fails against the real default
and invites the conclusion that the code is wrong."* At 9 m the measured
figures are **2.0728** and **3.0361** against item 16's **2.07** and **3.04**.

A mismatch between a tracker figure and the config was read as a quirk of the
tracker. It was evidence about the config.

### Result: the tension cases do not converge

| R | paper (120 MT) | rebuild | status |
|---|---|---|---|
| 70 m | 0.46% | — | **CUTBACK EXHAUSTED**, 0 increments |
| 85 m | 0.38% | — | **CUTBACK EXHAUSTED**, 0 increments |
| 105 m | 0.32% | — | **CUTBACK EXHAUSTED**, 0 increments |

It fails on the **first increment**, at **30 MT** as readily as at 120. It
reports the failure rather than returning 0.0 silently, which is the one
thing the documented failure signature demands.

What does converge, at R = 85: no gravity and no tension (the pure-arc case),
and gravity alone.

| R | rebuild, gravity only | analytical `D/2R` | over | rollers active |
|---|---|---|---|---|
| 70 m | 0.2617% | 0.2903% | −9.8% | 4/10 |
| 85 m | 0.2704% | 0.2391% | +13.1% | 4/10 |
| 105 m | 0.2428% | 0.1935% | +25.5% | 5/10 |

**Those are not a near-miss of the benchmark; they are a different problem.**
Absolute strain barely moves with R (0.24–0.27%) when it should fall, and
only four or five of ten rollers carry. With no tension the one-sided stinger
rollers cannot pull the pipe onto the arc — they only push — so the pipe sags
between whatever it touches and the stinger radius stops governing. That is
*why* the benchmark applies 120 MT.

### The diagnosis: the load path is staged, and ours is proportional

The paper's §V.D runs five steps:

1. pretension at the catenary end, **vessel end fixed**
2. **rotation** at the catenary end to bend the pipe along the stinger
3. gravity
4. lay tension at the catenary end
5. translation at the vessel end

`passage.solve` ramps **everything together** — contact targets, gravity and
tension all scale with one `lam`. So at the first increment it applies a
fraction of 1.18 MN at the tip of a 9 m overhang hanging past SR6 on a pipe
that is still straight and anchored 99 m away. There is nothing to react it,
and Newton diverges before the geometry exists that would carry the load.

Step 2 is also **displacement**-controlled — a rotation imposed at the end —
where ours is contact-target-driven throughout. Both differences point the
same way: the benchmark builds the deformed shape first and loads it second.

**Next task: staged load steps.** `solve` needs to take a sequence of steps,
each ramping its own subset (geometry, then gravity, then tension), carrying
state between them — which is what `SolveState` already exists to do. This is
a well-defined piece of work, not a search.

---

## 5. Known case-construction gaps

Separate from the baseline question, and to be settled before any M1 number
is quoted:

- **The scene's extent runs to the LOAD station (SR7, s = +48)**, 8 m past
  the last contact roller. With `tension = 0` that leaves an unsupported
  cantilever the reference model does not have. The reference mesh ends at
  SR6.
- **Station counts differ.** Our `n_vr` includes its terminal (VR*n* is the
  fixed anchor); the reference's `n_vr=3` means VR0..VR3 with a separate
  `std_ux` anchor. Comparable cases have to be built deliberately.
- **`Problem.elastic_zones` is carried and not yet applied.** The forced-
  elastic end zones exist to keep a restraint artefact out of the reported
  result; the solver does not read them yet.

---

## Action log

| Date | Action |
|---|---|
| 21 Sep 2026 | T5 solver built and its machinery verified — contact targets met to 1e-13 m including 8.897 m at SR6, active set unit-tested, loops bounded, J2 state carried. M1 **blocked**: the §6 plain-pipe baseline does not reproduce from the reference code under any of 12 configurations, and no plain-pipe sliding reference exists at all. Raised as decision D5 with three options and a recommendation. Three case-construction gaps recorded. |

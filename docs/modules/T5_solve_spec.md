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

It fails on the **first increment**, and it reports the failure rather than
returning 0.0 silently, which is the one thing the documented failure
signature demands.

**The ceiling is between 15 and 16 MT** (R = 85, gravity, bisected
21 Sep 2026): 15 MT converges, 16 MT gives `CUTBACK EXHAUSTED at
lam=0.0000`. That is **13% of the benchmark's 120 MT**, and the cliff is
sharp rather than a gradual loss of robustness — consistent with the load
path being wrong rather than the solver being fragile.

What the 15 MT case buys is worth recording, because it points the same way:
SR5 re-engages (6 of 10 rollers carry, against 5 at zero tension) and every
engaged station's arc miss collapses to **millimetres** — SR2 through SR5
land within 1.2 mm of their own arc point, against 0.39 m at SR5 with no
tension. Tension is doing exactly what the benchmark applies it for; there is
simply not enough of it.

What else converges at R = 85: no gravity and no tension (the pure-arc case),
and gravity alone.

| R | rebuild, gravity only | analytical `D/2R` | over | rollers active |
|---|---|---|---|---|
| 70 m | 0.2617% | 0.2903% | −9.8% | 4/10 |
| 85 m | 0.2704% | 0.2391% | +13.1% | 4/10 |
| 105 m | 0.2428% | 0.1935% | +25.5% | 5/10 |

> **SUPERSEDED by §5b.** Those figures carried defect L048. The corrected
> run is 0.3365 / 0.2751 / 0.2099, which does fall with R. The paragraph
> below was right that they were "a different problem" and wrong about which
> one.

**Those are not a near-miss of the benchmark; they are a different problem.**
Absolute strain barely moves with R (0.24–0.27%) when it should fall, and
only four or five of ten rollers carry. With no tension the one-sided stinger
rollers cannot pull the pipe onto the arc — they only push — so the pipe sags
between whatever it touches and the stinger radius stops governing. That is
*why* the benchmark applies 120 MT.

### The diagnosis — WRONG, and corrected 21 Sep 2026

The first diagnosis written here was that the paper's §V.D runs five staged
steps while `passage.solve` "ramps everything together — contact targets,
gravity and tension all scale with one `lam`", so the first increment applies
a fraction of 1.18 MN to a straight pipe.

**`passage.solve` does not ramp the loads, and neither does the reference.**
`nlfea_v4.assemble` accepts `lam` and never applies it to `dist_loads` or
`joint_loads` (`nlfea_v4.py:1419-1429`); only the wrapper `assemble_at` at
line 1693 scales them, and neither solver calls it. Both `passage.solve` and
`_solve_state_sliding` pass raw `dist` and `jl` straight through. **Gravity
and tension are at FULL value on the first Newton iteration of the first
increment in both programs**; `lam` ramps the contact targets and nothing
else.

That also explains the failure signature, which the old diagnosis did not.
`CUTBACK EXHAUSTED at lam=0.0000` means the first increment failed at the
smallest step — and cutback cannot help, because the thing diverging is not
scaled by `lam`. Measured, R = 85, 120 MT, first-iteration `max|dU|`:

| tension applied at | lam = 1/40 | lam = 1/2560 (64x cutback) |
|---|---|---|
| SR7, the free tip | **3.674 m** | **3.232 m** |
| SR6, the last contact roller | 0.525 m | 0.082 m |

Threshold is 1.0 m. Sixty-four-fold cutback moves the free-tip step by 12%.

### The real cause: WHERE the tension is applied

Our SR7 is a **LOAD station with no contact constraint** — the model runs
9 m past the last roller and the tension goes on that free cantilever tip,
on a pipe that is still straight and unstressed. The first Newton step is
3.2 m and trips `DIVERGENCE_DU`.

The reference has no such tip. `slay_sliding_v0_4.py:541-544` applies the
joint load at the LAST MESH NODE, at angle `(n_sr_total - 1) * dtheta` —
the last SR station — and that station is a contact slot which
`exempt_set = {len(slot_names) - 1}` makes **permanently active**. The
tension lands on a node whose normal DOF is held.

Moving our tension to SR6, the last contact roller, changes nothing else and
the benchmark converges at every radius:

| R | ours, tension at SR6, 9 m | reference `run_slay`, 8 m | paper (Abaqus) |
|---|---|---|---|
| 70 m | 0.5467% | 0.5274% | 0.46% |
| 85 m | **0.3985%** | 0.3882% | 0.38% |
| 105 m | 0.2845% | 0.2790% | 0.32% |

Within 2-4% of the reference program at every radius, with the peak in the
same span (ours s = 8.99, SR2; the reference x = -8.38, SR2-SR3). Note the
two columns are at different spacings, so this is agreement in behaviour,
not a like-for-like reproduction yet.

**§6's "known case-construction gaps" already listed this**: *"The scene's
extent runs to the LOAD station (SR7), 8 m past the last contact roller...
The reference mesh ends at SR6."* It was recorded as a gap to settle before
quoting an M1 number. It was in fact the M1 blocker.

**NOT CHANGED HERE.** Whether SR7 should become a contact station, or the
model should end at SR6, or the tension should simply move, is a modelling
decision that moves every number in the project. Raised as decision D6.

### The staged load step was tried, and it is worse

Asked to stage the sequence explicitly — tension and gravity settled first,
then `lam` ramping the contact targets — 21 Sep 2026. Two results:

**1. It is already the sequence.** `passage.solve` matches the reference
exactly. Neither ramps loads; both ramp targets alone. Nothing to change.

**2. An explicit load-settling step 0 diverges.** Holding every contact
target at its anchor and converging tension + gravity alone, R = 85:

| T | with the divergence guard | guard removed |
|---|---|---|
| 15 MT | converges, max\|U\| = 0.403 m | same |
| 30 MT | trips at iteration 3 | **NaN**, kernel matrix exactly singular |
| 60 MT | trips at iteration 1 | max\|U\| = **2e215** |
| 120 MT | trips at iteration 1 | **NaN** |

So the guard is not being over-cautious: without it the configuration runs
away. A straight, unstressed pipe has no geometric stiffness to react a load
at a free tip, and no amount of sequencing creates one. The sequence was
never the problem.

### The reference mesh has no tip to load — measured

`run_slay` at R = 85, 120 MT: station x values run `32.0 ... -38.54`, and
the mesh node range is `32.0 -> -38.54`. **The mesh ends exactly at the last
stinger roller.** The tension goes on `nn`, that same last node
(`slay_overbend_v1_50.py`, `run_slay`), which is a `radial` contact slot.

Ours runs `s = -45 -> +54` (world `x = +45 -> -54`) with the last contact
roller SR6 at `x = -42.93` and **9 m of free pipe beyond it** to SR7.

That is D6, and it is now measured from both reference entry points rather
than inferred.

### Two smaller differences from `run_slay`, for the record

  * **No divergence guard and no cutback.** Its Newton loop is
    `for it in range(30)` with `U += dU` and a residual break — no
    `|dU| > 1.0` trip, no failure path. `_solve_state_sliding` *does* carry
    the same guard we do, so this is a difference from the plain-pipe
    runner only.
  * **Newton tolerance `1e-3`**, against our `1e-8`.

Neither causes the divergence — the step-0 table above shows the
configuration failing without any guard at all — but both belong in any
like-for-like comparison.

## 5d. D6 TAKEN — the terminal station is a contact slot, 21 Sep 2026

**Decision D6, option B**: SR7 keeps its place and becomes a permanently
active (bidirectional) contact slot while remaining the tension point. This
matches the structure of the sliding reference, which `passage.solve` is a
port of: `slay_sliding_v0_4.py` builds SR1..SR{n_sr+1} as slots with
`exempt_set = {last}` and applies the joint load there.

`bears_tension` is a new Station attribute, **orthogonal to `role`** — the
station is CONTACT and carries the tension, and `load_station` selects on
the attribute. A role test for LOAD would now match nothing and
`lay_tension` would silently apply no load, which is the failure this
separation exists to prevent.

### The blocker is gone

**120 MT converges at every radius**, first time in this project. Panel B of
`stinger_pipe.png` now runs the benchmark case rather than a 15 MT stand-in.

### It does not yet reproduce the reference, and the gap is structural

Like for like at the reference's own 8 m spacing, 120 MT, plain pipe:

| R | ours, 8 m | ours, 9 m | reference `run_slay`, 8 m | paper |
|---|---|---|---|---|
| 70 m | 0.6390% | 0.6674% | 0.5274% | 0.46% |
| 85 m | 0.4571% | 0.4700% | 0.3882% | 0.38% |
| 105 m | 0.3216% | 0.3287% | 0.2790% | 0.32% |

**+15 to +21% above the reference at matched spacing**, and the peak has
moved: ours is at SR6 (`s = 39.6` at 8 m, `s = 44.8` at 9 m), the
reference's at the SR2-SR3 span (`x = -8.38`).

The cause is §6's SECOND gap, not this one. **`run_slay` at `n_sr=6` builds
six stinger stations; ours builds seven.** Its `allc` runs
`32.0 ... -38.54` — four deck stations and SR1..SR6 — and the tension goes
on the last of those. Ours adds SR7 beyond SR6 and now constrains it to the
arc, which bends the pipe further round than the reference ever does and
concentrates strain in the SR6-SR7 span.

So D6 removed the divergence and exposed the count rule underneath it. The
sliding reference (7 slots, last exempt) and `run_slay` (6 slots, tension on
the last) are **different configurations**, and only the second has plain-pipe
numbers to compare against. Settling which the rebuild should match is the
next task, and it is §6's "station counts differ" item, now with measured
consequences.

**M1 IS NOT CLAIMED.** Converging is not reproducing.

### For the record: the variant that did reproduce

Keeping SR7 unconstrained and moving only the tension to SR6 — option C,
not taken — gave 0.5467 / 0.3985 / 0.2845% at 9 m, within 2-4% of the
reference at every radius with the peak in the same span. It leaves the
free cantilever in the model, which is why it was not the chosen option,
but it is the measurement that says the station count is what matters.

---

## 5b. The pipe was not sitting on the stinger — found and FIXED, 21 Sep 2026

`tools/plot_stinger.py`, `docs/diagrams/stinger_pipe.png`. The first figure
in this project that draws the SOLVED pipe. `draw_layout.py` renders the
Scene and deliberately draws no pipe, because tracker item 27 forbids a
drawing that derives the pipe's shape from the arc formula. Every coordinate
here is a solved displacement, so the rule is satisfied and the figure is
allowed — and the first thing it showed was a defect.

### Two facts that could not both be comfortable

Every contact target was met to **1e-13 m** — and the material point that
should sit at SR6 ended up **5.18 m** from the arc. Under arc-length node positioning the material point at arc
`s` must land at `path.position(s)`: bending is inextensible to first order,
which is item 16's whole argument. Every row of that table should be zero.

Pure-arc case, R = 85 m, 9 m spacing, all rollers bidirectional, no gravity,
no tension. Miss = distance from the material point to its own arc point:

| station | s | miss BEFORE | miss AFTER |
|---|---|---|---|
| VR1 | −9 | 0.0011 | 0.0001 |
| SR1 | 0 | 0.0012 | 0.0003 |
| SR2 | 9 | 0.0043 | 0.0012 |
| SR3 | 18 | 0.0599 | 0.0005 |
| SR4 | 27 | 0.3364 | 0.0008 |
| SR5 | 36 | 1.3230 | 0.0005 |
| SR6 | 45 | **5.1797** | **0.0023** |

(The `arc_table` the tool now prints. At the 8 m spacing the test fixture
uses, the same case reads 2.212 m at SR6 before and 0.0027 m after.)

### The cause: a world vector used as model coefficients

`scene` speaks WORLD — `+x` toward the vessel. `model`, `physics` and `solve`
speak MODEL — `s` toward the stinger, `x_world = -(s + u_s)`.
`LayPath.normal` returns a world vector, correctly for a Scene quantity, and
`contact_targets` handed it straight to the solver as the coefficients
multiplying `(u_s, u_y)`. **The `s` component had the wrong sign.**

The reference program has no such boundary to cross: its nodal coordinate IS
world `x` (`slay_sliding_v0_4.py:235`, *"decreasing with node id"*), so its
`nx = -sin(theta)` is right there. Copied across the frame change, it is
wrong here.

**Why it survived every check until this one.** `dn` is invariant under the
error — flipping both `u_s` and `n_s` leaves the dot product alone — so the
target was right, and a constraint enforcing the *wrong* normal to 1e-13 m
looks exactly like a constraint enforcing the right one. The residual reports
on the constrained direction and nothing else. Only a statement the
constraint does not supply could catch it, and the arc position is that
statement.

The first diagnosis written in this section was **wrong**: it read the miss
as tangential indeterminacy for want of lay tension, and argued the boundary
conditions were incomplete. The fix carries no tension and the miss drops to
2.7 mm. Recorded as L047 (the check) and L048 (the defect).

Fix: `physics.contact.to_model_frame`, the one named place a world vector
becomes a model coefficient. Guarded by
`test_the_material_point_lands_on_its_own_arc_station`, which fails by
0.037 m at SR2 with the conversion removed.

### What the figure shows now

Panel A — all rollers bidirectional, no gravity, no tension — the solved pipe
lies on the roller-centreline locus, covering it. Panel B — the ruled
one-sided set with gravity and no tension — VR2, VR1, SR1, SR5 and SR6 lift
off, and **every nonzero miss in panel B is at a released roller**. That is
consistent physics rather than a defect: a one-sided roller cannot pull, so
with no tension the pipe hangs inside the arc past SR4. It is also the second
half of §5's argument for why the benchmark applies 120 MT.

### What it changed in the numbers

Gravity only, no tension, 9 m spacing, peak Phase-1 strain:

| R | BEFORE | AFTER | analytic `D/2R` | AFTER over analytic |
|---|---|---|---|---|
| 70 m | 0.2617% | **0.3365%** | 0.2903% | +15.9% |
| 85 m | 0.2704% | **0.2751%** | 0.2391% | +15.1% |
| 105 m | 0.2428% | **0.2099%** | 0.1935% | +8.5% |

Before the fix, absolute strain barely moved with stinger radius and the
amplification ran −9.8 / +13.1 / +25.5% — §5 called that "not a near-miss of
the benchmark; a different problem", and it was. **After the fix strain falls
with R as it must**, and the amplification is +16 / +15 / +9%, in the band
the old program occupies against Abaqus (§4).

The tension cases still fail on the first increment. §5's load-path finding
stands untouched and is still the next task.

---

## 5c. The same defect at the tension load — L049, 21 Sep 2026

Asked directly which way the tension points, and the answer was: the wrong
way. `physics.frame` existing is what made the question cheap — `grep` for
`path.tangent` and `path.normal` outside `scene` returns exactly two sites,
and only one of them had been converted.

`lay_tension` took `path.tangent(s)` — a **world** vector — and used it as a
model-frame `(fx, fy)`. Measured through the solve at R = 85, 10 MT:

| | deck axial strain | deck axial force |
|---|---|---|
| as built | −9.683e−06 | **−5.27 MT (compression)** |
| converted | +1.698e−05 | **+9.25 MT (tension)** |

Frictionless rollers apply normal forces only, so the axial force is carried
the length of the pipe and the straight deck run is the clean place to read
it. As built, 10 MT of declared *lay tension* compressed the overbend against
its own anchor. Peak strain at 10 MT: 0.2595% as built, 0.2904% corrected.

**The test that should have caught it ratified it.** It asserted
`fx == T * tx` against the same world tangent the implementation used — a
restatement of the code, which cannot fail with the code. Replaced by a
statement of the physics: tension pulls the cut end away from the vessel and
downward, so `fx > 0` and `fy > 0` in model components, and the deck carries
tension.

**This does NOT unblock the 120 MT benchmark.** Both signs fail identically —
`CUTBACK EXHAUSTED at lam=0.0000` at R = 70, 85 and 105 — so §5's load-path
finding stands unchanged and staged load steps are still the next task. What
the correction buys is that the tension cases which *do* converge are now
solving the intended problem: below about 10 MT the difference between the
two signs is 12% of peak strain, and it was pointing the wrong way.

---

## 6. Known case-construction gaps

Separate from the baseline question, and to be settled before any M1 number
is quoted:

- **The scene's extent runs to the LOAD station (SR7, s = +54)**, 9 m past
  the last contact roller. With `tension = 0` that leaves an unsupported
  cantilever the reference model does not have. The reference mesh ends at
  its last SR station, which is itself a permanently-active contact slot.
  **THIS WAS THE M1 BLOCKER** — see §5. Open as decision D6.
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
| 21 Sep 2026 | **L048 found and fixed.** `tools/plot_stinger.py` drew the solved pipe for the first time; the material point that should sit at SR6 was 5.18 m off its own arc point while every contact target was met to 1e-13 m. Cause: `LayPath.normal` is a WORLD vector and `contact_targets` used it as coefficients on MODEL DOFs, so the `s` component had the wrong sign; `dn` is invariant under that error, which is why every existing check passed. Fixed with `physics.contact.to_model_frame` and guarded by `test_the_material_point_lands_on_its_own_arc_station`. Gravity-only peak strain now falls with stinger radius — 0.3365 / 0.2751 / 0.2099% at R = 70 / 85 / 105 against 0.2617 / 0.2704 / 0.2428% before — and the amplification over `D/2R` sits at +16 / +15 / +9%. The §5b diagnosis written earlier the same day (tangential indeterminacy for want of tension) was wrong and is marked as such. Tension cases still fail on the first increment; staged load steps remain the next task. |
| 21 Sep 2026 | **L049 found and fixed**, prompted by the question "what is the direction of applied pipeline tension?". `lay_tension` used `path.tangent` — a world vector — as a model-frame `(fx, fy)`, so 10 MT of declared lay tension drove 5.27 MT of **compression** through the deck. The existing test asserted `fx == T*tx` against the same world tangent and so ratified the defect. `to_model_frame` extracted into `slay/physics/frame.py`, both crossing sites routed through it, and the test rewritten to state the physics: `fx > 0`, `fy > 0`, deck in tension. Does not unblock the 120 MT benchmark — both signs fail identically at `lam=0` — so staged load steps remain the next task. |
| 21 Sep 2026 | **The M1 blocker found; §5's diagnosis was wrong.** `nlfea_v4.assemble` never scales `dist_loads`/`joint_loads` by `lam`, so neither solver ramps its loads and cutback cannot reduce them — 64x cutback moved the first Newton step from 3.674 m to 3.232 m against a 1.0 m threshold. The real cause is WHERE the tension is applied: our SR7 is a LOAD station with no contact constraint, 9 m of free cantilever, while the reference puts its joint load on the last SR station, which `exempt_set` makes a permanently active contact slot. Moving our tension to SR6 converges at 120 MT at every radius — 0.5467 / 0.3985 / 0.2845% at R = 70 / 85 / 105, against the reference program's 0.5274 / 0.3882 / 0.2790% and the paper's 0.46 / 0.38 / 0.32%, with the peak in the same span. Not changed in the model: raised as decision D6. Recorded as L050 and L051; the reference `run_slay` was confirmed runnable in this repo. |
| 21 Sep 2026 | **D6 taken (option B): the terminal stinger station is a contact slot.** SR7 keeps its place, becomes bidirectional so it never releases, and still bears the tension via a new `bears_tension` attribute orthogonal to `role`. **120 MT converges at every radius for the first time** — the divergence blocker is gone. It does not reproduce: at the reference's own 8 m spacing ours reads 0.6390 / 0.4571 / 0.3216% at R = 70 / 85 / 105 against `run_slay`'s 0.5274 / 0.3882 / 0.2790%, +15 to +21%, with the peak displaced to SR6 from the reference's SR2–SR3 span. Traced to §6's station-count gap: `run_slay` at `n_sr=6` builds six stinger stations, ours builds seven. M1 not claimed. 12 tests restated. |

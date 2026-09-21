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

## 4. The blocker — M1's target does not reproduce

`run_slay(thick_component=None)` in `slay_overbend_v1_50.py` is the
plain-pipe baseline. Run today at its own defaults:

| R | `run_slay` defaults | §6 baseline table | ratio |
|---|---|---|---|
| 70 m | 0.3603% | **0.494%** | 1.371 |
| 85 m | 0.2819% | **0.384%** | 1.362 |
| 100 m | 0.2347% | **0.316%** | 1.346 |

Twelve configurations were tried against the table. None reproduces it:

| variant | R=70 | R=85 | R=100 |
|---|---|---|---|
| defaults | 0.3603 | 0.2819 | 0.2347 |
| `one_sided=True` | 0.2931 | 0.2399 | 0.2029 |
| `tension_mt=100` | 0.4626 | 0.3480 | 0.2748 |
| `tension_mt=120` | 0.4800 | 0.3626 | 0.2847 |
| **`tension_mt=150`** | **0.5052** | **0.3845** | **0.3008** |
| `tension_mt=200` | 0.5458 | 0.4200 | 0.3298 |
| `material='J2'` | 0.3604 | 0.2903 | 0.2353 |
| `section='fibre'` | 0.3535 | 0.2847 | 0.2361 |
| `self_weight=False` | 0.3517 | 0.2784 | 0.2324 |
| `T=120, J2` | 0.4800 | 0.3679 | 0.2954 |
| `T=120, one_sided` | 0.5274 | 0.3882 | 0.3002 |
| target | 0.494 | 0.384 | 0.316 |

`tension_mt=150` matches **R = 85 almost exactly** (0.3845 against 0.384) and
then misses R = 70 by +2.3% and R = 100 by −4.8%. The R-dependence of the
target does not match the R-dependence of any configuration tried, so it is
not one knob away.

**There is also no plain-pipe sliding reference at all.**
`run_passage_sliding` raises without a component, so the only plain-pipe
number the old code can produce comes from the **node-snapped** path — the
one T5 is specified to retire. Expecting the sliding formulation to reproduce
a node-snapped figure to three significant figures is not sound in any case;
tracker item 16 records the two differing by about 5% on another case.

This is decision **D5** — "which source governs the milestone ladder?" —
now spot-checked and confirmed disagreeing on the plain-pipe case.

### Options

1. **Re-baseline against live reference runs.** Record `run_slay` defaults
   (0.3603 / 0.2819 / 0.2347 at R = 70/85/100) as M1, with its full
   configuration written down. Reproducible today; but it gates a sliding
   solver on a node-snapped number.
2. **Find the original configuration.** If the provenance of 0.494 / 0.384 /
   0.316 is recoverable, use it. Nothing in the repo records it.
3. **Re-gate M1 on a physical check** rather than a legacy number — the pure
   arc, where the answer is known independently. Weakest as a regression
   guard, strongest as a statement of correctness.

**Recommendation: 1, with 3 kept as the standing sanity bound.** A baseline
whose generating configuration is unrecorded cannot discriminate a rebuild
defect from a legacy deviation, which is exactly what D5 warns about.

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

# T4 — L5 Physics

**Status:** BUILT 15 Sep 2026. `slay/physics/{sections,contact,loads,problem}.py`,
`rebuild/tests/test_physics.py` (31 tests). DONE WHEN clause passing.

**Precondition:** T3 complete (stages 1–3, 14 Sep 2026).

---

## 1. What this layer is for

T3 emitted geometry and **declarations**: an element carries a `Section`, or a
`stiffness_ratio`, or the rule name `'section_at'`, or nothing. T4 resolves
every declaration into numbers and poses one lay position as a `Problem`.

The value of the artifact is mostly in what it **refuses** to carry.

---

## 2. Sections — four rules, not interchangeable

| declaration | resolution |
|---|---|
| `Section` | used verbatim — a component states its own OD and wall |
| `stiffness_ratio` | **same section at `ratio × E`.** EA and EI scale together, which is what "a multiple of a plain pipe element of the same length" means. Reporting it as a thicker pipe would put the wrong fibre distance on every stress derived from it. GD-ST and GD-SB both use 2.5 |
| `'section_at'` | resolved **per element**, at the element's own midpoint, by asking the assembly. A taper changes along its length, so one answer per line would be wrong — and the assembly is the single source (tracker item 18) |
| none | plain pipeline |

Measured across the published set: `pipe` everywhere; `declared` on ILS-TP,
ILS-TT, ILS-SHTP, ILS-ILT; `ratio` on ILS-EAST (18), ILS-EASB (20), ILS-ILT
(18); `section_at` on ILS-TT (4). All four paths are exercised.

**The frame conversion lives here and nowhere else.** `build_model` placed the
ILS with `s = s_centre − x_local`, so going back is `x_local = s_centre − s`.
Asking `assembly.section_at` with a model `s` silently samples the wrong
station — and on a symmetric archetype it would even look right.

ILS-TT's taper resolves to 0.4284 / 0.4724 m thickening inward, mirrored at
both ends, between the pipe's 0.4064 and the body's 0.4944. **Two distinct
ODs across four elements is symmetry, not one-answer-per-line** — what would
say the resolution had gone per-line is all four being equal.

**Connectors are not sectioned at all.** Their stiffness is prescribed by
pass 4's rule, so there is nothing to bind.

---

## 3. Contact targets — the formula item 16 pairs with node positioning

    dn = R · (1 − cos θ − θ · sin θ)

**Derived, not copied.** Node reference positions are set by arc length, so
the straight reference pipe continues along the deck line and the material
point at arc `s` must travel to `path.position(s)`:

```
u = (Rθ − R sin θ,  R(1 − cos θ))
n = (−sin θ, −cos θ)
dn = u · n = R(1 − cos θ − θ sin θ)
```

`arc_target_by_projection` computes the same number as the projection it *is*,
and the two agree to 1e-15 at every station. The closed form is **checked**,
not trusted — if they ever disagree, the closed form is the derived one and
therefore the wrong one.

**`dn` is negative on the arc**, and that is right: `n` points from the roller
toward the pipe (upward, −y) while the arc falls away below the deck line.
At R = 85: SR2 −0.3756, SR3 −1.4926, SR4 −3.3210, SR5 −5.8118, SR6 −8.8971 m.
The deck stations are exactly 0.

### Keeping the old formula would be metres wrong

`dn = arc_y · ny` is the same projection with the `ux·nx` term silently zero —
true only under **rectangular** node positioning. Under arc-length positioning
`ux` reaches 2.07 m at SR6 and the term returns. Measured error if node
positions moved and the old `dn` were kept:

| R | SR2 | SR3 | SR4 | SR5 | SR6 |
|---|---|---|---|---|---|
| 70 | 0.002 | 0.031 | 0.157 | 0.487 | **1.158** |
| 85 | 0.001 | 0.018 | 0.088 | 0.276 | **0.662** |
| 100 | 0.001 | 0.011 | 0.055 | 0.171 | **0.412** |

Tracker item 16 records 0.03 / 0.14 / 0.44 / 1.05 at SR3–SR6 without stating
R. That is the **R = 70** row in shape and magnitude, about 10% below our
figures; the difference is unexplained and the tracker's R is not recorded.
Ours are reproducible from `arc_target`.

### The contact surface is additive, from one source

    lift = contact_at(x).y − OD_pipe/2

zero for plain pipe, positive where a deeper surface holds the centreline
higher, and `dn = dn_arc + lift`. Combination is the assembly's **lowest
surface** rule, not a sum: where a thick body and a shroud overlap, only the
deeper one is touched and adding them double-counts. `envelope_at` computed
the same thing in parallel in the old code; item 18's rule is that it becomes
a call into the assembly and never a second implementation.

### Interpolation

Two bracketing header nodes, **linear** weights summing to 1 and reproducing
the station's own arc position. `header_nodes` reads the pipeline's *own
elements*, not every node at y = 0 — on ILS-EASB the structure's top chord
lies on the centreline too, and a connector's `C-P` node sits exactly on the
pipe, coincident and deliberately distinct.

---

## 4. Loads and restraints

**Weight acts in +y**, because y is positive-down. Nothing negates it, and a
negative `Fy` arriving here is real: a cantilevered branch can put its point
mass in uplift and that case still solves. Total checked against `ρ·A·g·L`
over the whole model.

Lumping is **half-half**, which is what the old implementation did and what M1
must reproduce. Consistent lumping would also put end moments on each element;
the difference is second order in element length against a load itself small
beside the lay tension. Stated, not assumed.

**Tension acts at the LOAD station along that station's own tangent.** SR7
exists for exactly this: applying tension at the tip with SR6's tangent put a
spurious transverse force on the end and reported 2.46% strain at SR6 against
a ~0.83% reference — a 3× error. The test asserts the two tangents genuinely
differ, so it would fail if SR7 collapsed onto SR6.

**Point masses** come from the ILS, resolved. An unresolved id **refuses**
here rather than being dropped — by this layer there is nowhere left to report
it to, and a mass silently excluded from the load path is worse than one
reported missing.

**Restraints** are the FIXED station and nothing else, all DOF, and it must
have a node under it. `role` is what says a station is an anchor: a list read
through `one_sided` alone cannot tell a bidirectional roller from a station
that touches nothing.

---

## 5. The `Problem` artifact

Complete, inert, serialisable. **Three things it must not contain**, all of
which leaked in the old code:

- a **shift index** — `shift` is an argument, never a field on the result
- a **sweep length** — how many positions get analysed is the study layer's
- a mutated **Scene** — two Problems come from the same Scene object unchanged

### DONE WHEN — `differs_only_in_contact(a, b)`

Two Problems built at different shifts share every node, element, section,
connector, association, load, restraint and elastic zone, and differ in their
contact targets alone. Asserted mechanically on plain pipe and on ILS-TP,
ILS-TT, ILS-EAST, ILS-EASB and ILS-ILT — because "same nodes, same elements"
is exactly the sort of thing that stays true by inspection right up until it
does not.

`to_json` round-trips and contains neither `'shift'` nor `'sweep'`, which is
also what proves there is nothing live inside: no Scene, no assembly, no
solver state.

---

## 6. Open items — raised, not resolved

**1. `R_eff` versus centreline mode.** `LayPath.R` is measured to the roller
**centreline**, so the pipe centreline really rides at `R + r_roller + r_pipe`
from the arc centre. What is implemented drives the pipe **centreline onto the
R arc**, which is v0.4's behaviour and what the card's VERIFY clause specifies;
v0.5 added the offset form. Both are defensible and they differ. Every target
carries `radius` so the decision can be made with a number rather than a
preference. **Not chosen here.**

**2. Hermite interpolation.** The weights are linear in the two bracketing
nodes — the old behaviour, and what M1 must reproduce. A beam's transverse
displacement between its nodes is really cubic; the gap is about `L²κ/8`,
roughly 1 mm at 0.8 m elements and R = 85. Whether that matters is a T5
question, once there is a solved answer to compare against.

**3. Roller stations are not mesh nodes.** They fall between nodes and are
interpolated, which is *required* — the sweep moves them continuously. The old
code put nodes at the rollers. Whether the interpolation costs anything
measurable is for M1 to say.

**4. The sweep ceiling.** `build_scene(margin=...)` still defaults to zero and
the reachable-sweep rule is still open (see `scene.py`). T4 does not need it;
the study layer will.

---

## Action log

| Date | Action |
|---|---|
| 15 Sep 2026 | T4 built. Sections, contact targets, loads and `Problem`, with the DONE WHEN clause passing on plain pipe and five archetypes. `dn` derived rather than copied and checked against its own projection at every station; the old `arc_y·ny` form measured at 0.662 m error at SR6 (R = 85). Four open items recorded rather than resolved by default: `R_eff`, Hermite interpolation, roller-station interpolation, the sweep ceiling. One defect found on the way — `arc_target` takes an ANGLE and was first called with an arc length, returning −1485 m at a station whose target is exactly zero. |

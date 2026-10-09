# T10 — The simplified ILS model: physics

**Status:** BUILT 8 Oct 2026. `slay/define/{simple,simplify}.py`,
`tools/{simplify_ils,stiffness_rig,study_simple,plot_simple_ils}.py`,
`rebuild/tests/{test_simple_component,test_simplify}.py` (56 tests).
Fifteen cases reduced and swept across three component families.

**Precondition:** T4 (physics) and T5 (solve) complete. The simplified model
is posed and solved by exactly the same machinery as a real one.

**Results:** `docs/validation/VALIDATION_v3.0_2026-10-06.md` §6;
`docs/simple/RESULTS_*.txt`.

---

## 1. The question this answers

A real inline structure is a specific piece of hardware: a wall thickness, a
bore, an outside diameter, a taper, sometimes a frame of a dozen members. In
conceptual design none of that exists yet, and most of it never reaches the
overbend answer.

The overbend is a **displacement-controlled bending** problem. The pipe is
pushed onto an arc of fixed radius by rollers; the strain that results is set
by how much curvature the pipe is forced into and how the component changes
that. Three properties of a component govern it:

| | symbol | why it matters |
|---|---|---|
| **how stiff** it is | `EI` | sets how the curvature redistributes between the component and the pipe beside it |
| **how long** it is | `L` | sets over what length the redistribution happens |
| **how far it holds the pipe off** the rollers | lift | sets the curvature imposed in the first place |

**GD-Simple states those three directly and nothing else.** It is a bounded
length of pipe carrying the **pipeline's own section**, whose elastic modulus
is the free parameter and which **never yields**, optionally riding an offset
shroud that takes the roller contact.

    real layout                 measured                 ILS-SIMPLE
    ------------------------    --------------------     ---------------------
    GD-TP, t 53 mm, 20 D        EI/EI_pipe  3.248        body: pipeline
    OD_comp 470.4 mm            L     8.128 m            section at E 682 GPa,
                                depth 235.2 mm           fully elastic
                                                         shroud: V 235.2 mm

---

## 2. Why a modulus and not a section

The stand-in must reproduce `EI`. Two ways exist and only one of them is
right here.

**Change the section.** Give the body a heavier wall until `E_steel · I_comp`
matches. That reproduces the original exactly — because it *is* the original.
It is not a simplification.

**Change the modulus.** Keep the pipeline section and set

$$E_{eq} = E_{steel}\,\frac{I_{comp}}{I_{pipe}}$$

so that `E_eq · I_pipe = E_steel · I_comp` identically. The section, the
extreme-fibre distance, the mass per metre and the contact geometry all stay
the pipeline's, and **stiffness becomes the only thing that moved**. That is
what makes the model simple and what makes its errors attributable.

### Why not `stiffness_ratio`

`slay.physics.sections` already has a mechanism that scales `EA` and `EI`
together — `stiffness_ratio`, used by GD-ST and GD-SB frame members. It is
the wrong lever here, and the distinction is physical rather than stylistic.

A ratio scales stiffness **on an unchanged yield surface**. Correct for a
structural member that is only ever a stiffness; wrong for a body whose
modulus moves while its steel keeps its strength, because the yield *strain*
`σ_y/E` would move with it. A body at 917 GPa with a 360 MPa yield would
first yield at 0.039% strain instead of 0.171%, which is not a material
anybody specified.

**GD-Simple is sound only because it is also forced elastic.** With no yield
surface there is nothing for the scaled modulus to be inconsistent with. The
two halves arrive together or not at all, and supplying both a ratio and an
explicit modulus for one body is refused outright rather than multiplied.

Mechanically:

* the modulus is a per-owner override, `E_by_owner`, in `physics.sections`;
* the constitutive law comes from `Problem.elastic_spans`;
* `solve.kernel` already keys materials by `(E, elastic)`, so **no kernel
  change was needed** and G6 stands.

---

## 3. What is matched, and what cannot be

| quantity | matched? | how |
|---|---|---|
| **length** | exact | the body spans what the original spanned |
| **depth / lift** | exact | the shroud's bottom flat goes where the original's contact surface was |
| **bending `EI`** | exact | `E_eq = E_steel · I_comp/I_pipe` |
| **axial `EA`** | **no** | `E_eq · A_pipe ≠ E_steel · A_comp` |

### The axial error is arithmetic, not a defect

One modulus on a fixed section cannot satisfy two stiffnesses at once,
because `A_comp/A_pipe` and `I_comp/I_pipe` are different ratios. Setting one
fixes the other:

$$\frac{EA_{eq}}{EA} = \frac{I_{comp}/I_{pipe}}{A_{comp}/A_{pipe}}$$

| wall | `I_comp/I_pipe` | `A_comp/A_pipe` | `EA` error |
|---|---|---|---|
| 32 mm | 1.664 | 1.567 | **+6.2%** |
| 42 mm | 2.363 | 2.109 | +12.0% |
| 53 mm | 3.248 | 2.733 | **+18.8%** |
| 65 mm | 4.366 | 3.449 | **+26.6%** |

It grows with the wall, because area grows faster than the second moment that
sets `E_eq`. **`EI` is the one chosen because the overbend is
displacement-controlled bending**, and the error is carried on the result
(`EA_error`) rather than left to be discovered.

### Two further differences are deliberate

* The stand-in keeps the **pipeline's** extreme-fibre distance (203.2 mm, not
  `OD_comp/2`), so the same curvature gives a lower strain than the original's
  section would.
* The body is **elastic**; the original is J2.

Both are what make stiffness the only variable. Neither is an approximation
that could be removed without removing the point of the model.

---

## 4. Two routes to `EI`, and which applies when

The reduction is not one method with a wide input. It is **two**, and which
one applies is a fact about where the component keeps its stiffness.

### 4.1 Read it — a component that changes the pipe wall

`GD-TP`, and anything else whose stiffness is in the section. `section_at`
returns `OD_comp` and `t_comp` over the span, so `I_comp` follows in closed
form and `slay.define.simplify.equivalent` reads it off.

**Everything is measured off the built assembly, never read from the spec** —
`section_at` for the section and its owner, `contact_at` for the surface a
roller would touch. This is the rule `report.regions` already follows and for
the same reason: `ils_builder` is the author of what a component *is* (G7),
so a reduction computed from the definition would describe the component we
asked for rather than the one the builder made.

The payoff is concrete: **the depth rule needs no formula.** `contact_at`
returns 235.2 mm for the 53 mm wall, which *is* `OD_comp/2`, without the
module ever writing that down.

### 4.2 Measure it — a component whose stiffness is in a frame

`GD-ST`, `GD-SB`. Their stiffness is in a frame tied to the pipe at discrete
connectors; `section_at` returns the plain pipeline everywhere along them.
**There is no section to read**, and `simplify.equivalent` refuses them by
name rather than guessing.

`tools/stiffness_rig.py` measures it instead. A **pure-bending test** over the
span between the two pipeline-side connector nodes:

* equal and opposite token moments at the two nodes,
* rigid-body restraint only, so the supports carry no force,
* gravity off, no lay tension, everything linear elastic.

The span then carries **constant** `M`, so

$$EI_{eq} = \frac{M L}{\Delta\theta}$$

**in closed form.** No search loop, and none is written: one that stopped when
the rotation "almost" matched would be choosing its own tolerance where an
exact inverse exists.

#### Three checks, printed, never assumed

| check | what it would catch | measured |
|---|---|---|
| **linearity** — `EI` at `2M` against `EI` at `M` | connectors slipping or lifting, making a single `E` a fiction | −0.03 to +0.03% |
| **boundary** — a clamped end against the self-equilibrating pair | local restraint the lay does not have, not decaying over a short span | −0.000% |
| **control** — plain pipe through the same rig against analytic `E·I` | the rig measuring itself | +0.0002% |

A rig that cannot reproduce a known answer proves nothing about an unknown
one.

#### The quadrature is not the default, and the obvious correction is wrong

`solve`'s default `polar` scheme — the B31-equivalent angular integration the
reference runs use — reads the plain-pipe control **0.2955% low**, a fixed
bias independent of length and mesh.

**Self-calibrating it away over-corrects.** Taking the ILS stiffness as a
ratio to the rig's own plain-pipe figure gives 8.436 where the truth is 8.415,
because the frame members are not the pipe section and do not carry the same
bias. *A bias cancels in a ratio only when it is common to both terms.* The
extraction uses `polar=False, n_fibres=20`, the converged Cartesian scheme.

---

## 5. The shroud, and when there is not one

A shroud reproduces **lift**, and only a component that lifts needs one.
Measured per family, not assumed:

| family | `contact_at` over the component | shroud? |
|---|---|---|
| **GD-TP** | its own `OD_comp/2` — it *is* the contact surface | yes |
| **EA-ST** (top structure) | plain pipe 0.2032 m, owner `pipe` | **no** |
| **EA-SB** (base structure) | `P_v` with owner `GD-SB` | yes |

A top structure sits *on* the pipe and changes nothing a roller touches. A
shroud put there anyway would need `V = OD/2` for zero lift — a component
doing nothing while still owning contact. So `V`, `L1` and `L2` are
**all-three-or-none**: two of them is a half-stated component, and defaulting
the third would invent geometry nobody asked for.

### `L2 = 0` is unbuildable

The exact equivalent of a `GD-TP`'s abrupt step is a shroud with **no taper**,
and the mirrored `OffsetShroud.validate` refuses it — *"GD-SH: V, L1 and L2
must be positive"*. Checked against the mirror directly: `L2 = 0` raises,
`L2 = 1e-9` is accepted. `TAPER_MIN` is **0.1 mm**, reusing
`regions.FLAT_TOL` rather than choosing a second number for the same job.

**A sharp taper raises no contact problem**, and this was measured rather than
argued. The contact normal comes from the **station** — the roller's arc
normal — and the component contributes only a scalar `lift = contact_at(x).y −
OD/2` to the target. `ContactAdvice`, the declaration that says a taper's
normal tilts, has **no consumers anywhere in the codebase**. Across the 0.1 mm
taper the lift ramps linearly and continuously, and the `GD-TP` it replaces is
**sharper still** — a true step, 32 mm at the end and 0 mm one micron later.

### Matching rule

For a component whose lifted footprint and stiffened span coincide (`GD-TP`),
`L1 + 2·L2 = L` matches the shroud **total** to the body, so the lifted
surface starts and stops where the original's did.

Where they are genuinely independent (`EA-SB`: stiffened span 5–10 D, lifted
footprint 13.7–18.7 D) the shroud is reproduced **as measured** and
`body_covers_shroud` reports False — the first time that flag fired on real
geometry.

---

## 6. Regions — Xb and Xe

Two regions, and the boundary is the **body's** extent:

* **Xb** — inside the body: the elastic span at the body modulus.
* **Xe** — outside it: the pipeline either side. **Two spans, not one** — it
  is the complement of Xb, so no single interval names it and `region_peaks`
  carries both in `spans`.

Drawn on the body because `L_body` and the shroud's `L1`/`L2` are independent
by construction; keying Xb on the shroud would report the elastic span as
whatever the shroud happened to be.

`SimpleGeometry` subclasses `OffsetGeometry` so the inherited `s_*` fields
stay the **shroud** footprint that `body_peaks` and `peak_on_shroud` already
read. Without a shroud they are set to the **body**, deliberately: those
consumers read them as "the component's footprint", and for a body-only
GD-Simple the body is the whole footprint.

**Comparisons in §6 of the ledger are peak-against-peak**, not region against
region. The simplified model's overall peak is its Xe in every case run, so
the comparison does not depend on the partition at all — which matters,
because a real component's region scheme (X1–X5, or X_c/X_i/X_e) is drawn on
features the stand-in does not have.

---

## 7. The control, and why the obvious control is wrong

At `E = E_steel` the body differs from plain pipe in exactly one way — it
cannot yield — so **where nothing yields it must be indistinguishable**.

Measured at R = 250 m: **Xb 0.2031% against Xe 0.2031%, ratio 1.000.** That
single figure verifies the whole chain at once: the modulus override landed,
the elastic law landed, and the region boundary is where the body is.

**The same case at R = 85 m is not a control.** It gives Xb 0.3161% against Xe
1.1110%, ratio 0.285 — and that is a **result**. The pipe either side is
plastic at 1.1% with its tangent collapsed to `E·H/(E+H)`; the body cannot
yield, stays on the full 210 GPa, becomes the far stiffer member and sheds
curvature outboard while taking more moment. Against a bare shroud of the same
geometry, which peaks at 0.8223%, inserting a **non-yielding body of the
pipeline's own section** makes the adjacent pipe **35% worse**.

That asymmetry is the component's actual mechanism. It also means `Xb < Xe` is
the normal reading once the line is plastic.

---

## 8. What fifteen cases established

| family | shroud? | n | mean Δ on peak | band | one sign? |
|---|---|---|---|---|---|
| **GD-TP** | yes, `covers=True` | 9 | **−2.17%** | −3.3 to −1.0 | **yes** |
| **EA-ST** | **no** | 2 | +1.50% | −0.8 to +3.8 | no |
| **EA-SB** | yes, `covers=False` | 3 | **+8.37%** | +6.5 to +10.2 | **yes** |

**Moment is reproduced within 1.0% on all ten GD-TP cases**, over 1188 to
3253 kN·m, three moduli, four lengths and three radii. That is the one
equivalence the reduction claims to hold exactly, and it holds everywhere it
has been asked. The moment scatters about zero (mean +0.05%, six high four
low) — the signature of a quantity being *reproduced*.

**Accuracy does not degrade with stiffness ratio.** Over a factor of seven in
`EI` — 1.66× to 12.17× — the peak error stays inside ±4% for GD-TP and EA-ST.
That was the obvious thing to fear of a one-parameter reduction and it is not
happening.

**Each family has its own signature and they do not share a cause.** A tight
one-signed band *within* a family says there is one mechanism in that family;
it says nothing about which, and nothing that carries across.

### A refuted hypothesis, kept because the refutation is the useful part

It was proposed that GD-TP's −2% came from the shroud — *matched depth is not
matched contact geometry*, a flat standing in for a cylinder — on the evidence
that the two shroud-less EA-ST cases straddled zero.

**EA-SB has a shroud and biases +8.4%, the opposite way from GD-TP's −2.2%.**
One mechanism in the shroud cannot be negative in one family and positive in
another. The hypothesis is dead (L113 `withdrawn`, L114).

Two candidates remain, **both untested and neither to be cited as a cause**:

1. **The load path**, which differs only for EA-SB. The real roller bears on
   the **frame** and reaches the pipe only at the two connectors; the
   stand-in's shroud is clamped to the pipe and transfers roller load
   **continuously** over 13.7 D. No counterpart in the GD-TP family, where the
   body *is* the pipe and transfer is continuous in both.
2. **The stiffened span.** The reduction stiffens only between the connectors
   — right for a structure attached at two points, unestablished for a base
   bearing along its whole length.

---

## 9. What the model is not

1. **Not validation.** Neither paper defines a GD-Simple. Every comparison is
   against this build's own full-model rows.
2. **Not axially equivalent.** +6.2 to +26.6%, reported on every reduction.
3. **Not a single correction.** The usable output is **per-family** and the
   two known ones go opposite ways: GD-TP ~2% low, EA-SB ~8% high, EA-ST
   none. It must not be generalised to a family that has not been run.
4. **Not general across layouts.** Four classes are refused by name with the
   missing rule stated: a tapered body (GD-TT carries 1005 diameters over its
   span, and which average is right depends on where the curvature is); two
   section-owning bodies; a layout with no section owner *and* no frame; and a
   body owning a section but no contact.
5. **Not a new component.** `component_spec.py`, `ils_builder.py` *and*
   `fixtures/standard_ils_layouts.json` are mirrored and hashed (G7).
   GD-Simple is a **composite** declared in `slay/define/simple.py` from two
   codes the mirror already has — a neutral `GD-TP` (`t_comp == t_pipe`, legal
   since the 5 Sep 2026 relaxation) over a `GD-SH` — handed to the mirrored
   builder, which stays the author of what a component is.

---

## Action log

| Date | What |
|---|---|
| 8 Oct 2026 | GD-Simple built; modulus override and elastic span; Xb/Xe scheme; control at R = 250 gives 1.000 (L109, L110) |
| 8 Oct 2026 | `simplify` reduces a GD-TP by reading `section_at`/`contact_at`; ten cases, moment within 1.0% (L111) |
| 8 Oct 2026 | `stiffness_rig` measures an EA structure's `EI`; body-only variant for a top structure; EA-ST F2 (L112, L113) |
| 8 Oct 2026 | EA-SB F2, the first combined reduction; the shroud hypothesis refuted (L114) |

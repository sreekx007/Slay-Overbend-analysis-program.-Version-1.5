# SLAY Overbend — Validation ledger v3.0

> ## L100 — a roller could not bear on an in-line component. Now fixed.
>
> **6 Oct 2026.** `contact.header_nodes` chose the nodes a roller may bear
> on by `owner == 'pipeline'`, and a thick component's elements carry
> `owner='TP'`. The node chain had a hole exactly where the body sat,
> `_bracket` spanned it, and the body's interior nodes were held by **no
> contact constraint at all** — 19 of 21 nodes on the 40 D case. The
> component could not engage a roller it was sitting on.
>
> Keyed on `line_id` instead (an in-line body *is* the pipeline there), the
> affected cases were re-run. **Every result below is post-fix.** What it
> moved, against Paper 1:
>
> | | before | after |
> |---|---|---|
> | TABLE XX/XXI moment (9 cases, ≈2.5 D) | −2.4 … +6.7% | **−2.4 … +6.7%** (unchanged) |
> | TABLE XXIII/XXIV moment (6 cases, 2.5–40 D) | −2.3 … **−47.3%** | **−7.7 … +12.8%** |
> | TABLE XXIII/XXIV strain | +8.6 … **+62.2%** | **−31.6 … +8.6%** |
> | TABLE XXXIX moment | −6.5, −12.1% | **−5.3, −3.2%** |
>
> **The short-component table did not move at all**, and that is the
> strongest check on the diagnosis rather than a disappointment: at 2.5 D the
> old bracket was 1.25× an element, so there was almost nothing to fix. The
> error scaled with length — 20× an element at 40 D — and so did the
> correction.
>
> Two conclusions recorded here earlier are **withdrawn**: that
> long-component moments read 28–47% low (they read −7.7 to +12.8%), and the
> 608 mm bridging reading and the figures drawn from it. A third is
> **substantially changed** — see the saturation discussion in §2.
>
> `VALIDATION_v1.0` and `v2.0` are untouched and still carry the pre-fix
> numbers for comparison.

**The rebuild against the published results, table by table.**

Organised on the **papers' own table numbering**, so a row here can be
checked against the source without translation. One table per published
table: the paper's value and ours side by side, with the delta.

Peak strain **and peak bending moment** are reported for every case we have
run, whether or not the paper publishes a moment for it.

*6 Oct 2026. Branch `claude/program-rebuild-status-bya72s`. Supersedes
`VALIDATION_v2.0_2026-10-06.md`, which carried the same results spread over
more tables and mixed in two comparisons that are not rebuild-against-paper:
the original `run_slay` toolchain, and v1.0's superseded numbers. Both are
still in their own files.*

---

## How to read this

**Configuration is part of every number.** Unless a table says otherwise:
406.4 × 21 mm pipe, **9 m roller spacing** (the paper's, stated once in its
model description), 2 × OD element length (the paper's mesh), J2 plasticity,
and the pipe centreline riding at `R + r_roller + OD/2` — the physical
contact surface, with `r_roller` = 0.3 m.

**The steel is DNV Grade 450**, API 5L X65-equivalent: SMYS 450 MPa,
certificate 448 MPa, E = 207 GPa, Ramberg-Osgood n = 20.59. We run its
incremental J2 form, a table from 360 to 530 MPa over 0 to 5.26% plastic
strain at E = 210 GPa. The 360 MPa is where the round-house curve leaves the
elastic line — 0.800 × 450 — **not** a grade SMYS.

**We report a passage envelope; the papers report a single analysis.** An
envelope is a maximum over the whole travel and cannot be *below* a single
position of the same case, so this offset explains us reading high and never
low. Measured directly on a thick-pipe case: the envelope is **24.6% above**
a single-position solve at the start.

**Two known offsets besides that**, both documented and neither a bug:

* *The R-trend divergence.* Abaqus amplification rises with stinger radius
  and the Python toolchain's falls; they cross near R = 80 m. A delta that
  is high at R = 70 and low at R = 105 is the signature, not noise.
* *Mesh.* No component case is converged at 2 × OD, and refinement moves the
  answer. Where a region holds one or two elements the figure is reporting a
  mesh rather than a strain field, and the element count is given.

**A dash means not measured, never zero.** A region that holds no elements
at a given mesh is shown `—`.

---

## 1. Plain pipe — Paper 1 TABLE X and XI

### TABLE X — peak strain by stinger configuration

*16 in pipeline, 120 MT. Paper's governing phase: Phase 1.*

| Config | R | Paper 1 strain | ours | Δ | ours BM | Paper BM |
|---|---|---|---|---|---|---|
| A | 70 m | 0.46% | 0.5373% | **+16.8%** | 1254 kN·m | not published |
| B | 85 m | 0.38% | 0.4032% | **+6.1%** | 1182 kN·m | not published |
| C | 105 m | 0.32% | 0.2954% | **−7.7%** | 1070 kN·m | not published |

Monotonic high-to-low across the radii — the R-trend divergence, crossing
between 85 and 105 m, with best agreement at R = 85 where the two curves
cross.

### TABLE XI — diameter and tension at R = 70

*`tools/study_table_xi.py`. **All six converged**, zero-tension rows
included — the stated risk that a one-sided roller cannot pull did not
materialise.*

| Pipe | T | Paper FEA | ours | Δ | `D/2R` | ours vs `D/2R` | **paper vs `D/2R`** | ours BM |
|---|---|---|---|---|---|---|---|---|
| 6" (168 × 21) | 0 MT | 0.13% | 0.1428% | +9.9% | 0.120% | **+18.8%** | **+8%** | 94 kN·m |
| 6" | 100 MT | 0.29% | 0.3391% | +16.9% | — | — | — | 137 kN·m |
| 16" (406 × 21) | 0 MT | 0.33% | 0.3536% | **+7.2%** | 0.290% | **+21.8%** | **+14%** | 1207 kN·m |
| 16" | 100 MT | 0.42% | 0.5280% | +25.7% | — | — | — | 1258 kN·m |
| 20" (508 × 21) | 0 MT | 0.42% | 0.4888% | +16.4% | 0.363% | **+34.7%** | **+17%** | 2033 kN·m |
| 20" | 100 MT | 0.54% | 0.6352% | +17.6% | — | — | — | 2075 kN·m |

**This is the only block in either paper that checks against something other
than an FEA.** At zero tension the pipe is bent to the stinger arc and
nothing else, so `ε = D/2R` is exact with no solver in it. Our closed form
reproduces the paper's own analytical column to under 1% at all three
diameters (0.120 / 0.290 / 0.363 against its 0.12 / 0.29 / 0.36), which pins
the reference axis before any result is read against it.

**The qualitative finding is reproduced: the FEA-to-analytical gap widens
with diameter.** Paper 1 reports +8 → +14 → +17%; we read +18.8 → +21.8 →
+34.7%. Both rise monotonically, so the mechanism the paper identifies —
discrete roller supports concentrating curvature above the pure-bending
value, more so as the pipe stiffens — is present in our model too.

**But our gap is roughly double the paper's at every diameter, and that is
the most load-bearing disagreement in this file.** Everywhere else a
disagreement could be a shared modelling choice cancelling differently on
the two sides. Here one side is arithmetic. Our excess over pure bending is
+18.8 / +21.8 / +34.7% where Abaqus reads +8 / +14 / +17%, so we concentrate
roughly twice as much strain at a roller as the benchmark does, measured
against a reference neither model can argue with.

That is consistent with — and independent evidence for — the two offsets
already recorded: the envelope-versus-single-position offset (we take a
maximum over the travel and cannot read low), and extreme-fibre strain
against the papers' nominal strain at integration points. Both inflate a
local peak at a contact point without touching the section force, and §2's
bending moments agreeing to a few percent while strains disagree by 10–17%
is the same pattern.

**Bending moment is unpublished for this table**, so these are predictions.
They scale as expected: 94 → 1207 → 2033 kN·m at zero tension, close to the
`I/c` ratio of the three sections.

---

## 2. Thick pipe — Paper 1 TABLE XX, XXI, XXIII, XXIV, XXVI

### TABLE XX and XXI — wall thickness variation

*L = 1000 mm (≈2.5 D), 100 MT. Constant bore, `OD_comp = ID + 2t` — the
paper's own convention; our 53 mm case computes OD 470.4 mm and I/Ip = 3.248
against its stated 471 mm and ~3.2×. Paper's peak location: pipe-to-component
junction at the 2nd stinger roller, Phase 1.*

**Bending moment is read ON THE COMPONENT BODY**, which is where TABLE XXI
reports it — its location column says "near component midspan, at the
instant a roller is below midspan". The pipeline's own maximum is given
beside it because the two are close and it is the quantity an unqualified
"peak moment" would return.

| Case | t | R | Paper strain | ours | Δ | Paper BM | ours, body | Δ | ours, pipe |
|---|---|---|---|---|---|---|---|---|---|
| A1 | 32 mm | 70 m | 0.562% | 0.6298% | +12.1% | 1311 kN·m | 1298 kN·m | **−1.0%** | 1289 |
| A1 | | 85 m | 0.473% | 0.4815% | **+1.8%** | 1251 kN·m | 1242 kN·m | **−0.7%** | 1238 |
| A1 | | 100 m | 0.339% | 0.3779% | +11.5% | 1131 kN·m | 1177 kN·m | +4.1% | 1175 |
| A2 | 42 mm | 70 m | 0.647% | 0.7002% | +8.2% | 1347 kN·m | 1317 kN·m | −2.2% | 1306 |
| A2 | | 85 m | 0.508% | 0.5476% | +7.8% | 1288 kN·m | 1270 kN·m | **−1.4%** | 1264 |
| A2 | | 100 m | 0.358% | 0.4188% | +17.0% | 1144 kN·m | 1209 kN·m | +5.7% | 1205 |
| A3 | 53 mm | 70 m | 0.727% | 0.7709% | **+6.0%** | 1366 kN·m | 1333 kN·m | −2.4% | 1320 |
| A3 | | 85 m | 0.556% | 0.6153% | +10.7% | 1311 kN·m | 1293 kN·m | **−1.4%** | 1284 |
| A3 | | 100 m | 0.425% | 0.4489% | **+5.6%** | 1150 kN·m | 1228 kN·m | +6.7% | 1221 |

**Bending moment agrees far better than strain: −2.4% to +6.7%, against
+1.8% to +17.0%.** That is the most useful single result in this file.

Moment is a section force — an integral over the section, set by the
curvature the rollers impose. Strain is a local extreme-fibre quantity read
off one element, and it carries the envelope offset, the mesh, and wherever
the peak happens to land. The two agreeing to different degrees says the
**global mechanics are right and the local strain reporting is where the
disagreement lives**, which is a much narrower place to look than "the model
reads high".

The moment delta also flips sign with radius — negative at R = 70 and 85,
positive at R = 100 — which is the R-trend divergence again, visible in a
quantity that is otherwise in good agreement.

*The component body carries 0.3 to 1.0% more moment than the pipeline
either side of it, consistently, which is what a locally stiffer section in
a displacement-controlled bend should do. The distinction is small here and
is kept because it is not small everywhere: on the long components of
TABLE XXIII it is the difference between answering the paper's question and
a different one.*

### TABLE XXIII and XXIV — component length

*`tools/study_table_xxiii.py`. 100 MT. **The wall thickness is not constant
across radii** — TABLE XXII specifies 65 mm (3.1×) at R = 70 and 53 mm
(2.5×) at R = 85, so the two radii are different components, not one
component at two radii. All six converged.*

*Moment on the **component body**, as TABLE XXIV reports it ("component
midspan / roller below midspan"), with the pipeline's own maximum beside it.*

| R | Length | t | Paper strain | ours | Δ | Paper BM | ours, body | Δ | ours, pipe |
|---|---|---|---|---|---|---|---|---|---|
| 70 m | 2.5 D | 65 mm | 0.780% | 0.8471% | **+8.6%** | 1384 kN·m | 1352 kN·m | **−2.3%** | 1333 |
| 70 m | 10 D | 65 mm | 1.499% | 1.4161% | **−5.5%** | 1650 kN·m | 1604 kN·m | **−2.8%** | 1393 |
| 70 m | 20 D | 65 mm | 2.514% | 1.9763% | −21.4% | 2223 kN·m | 2053 kN·m | **−7.7%** | 1428 |
| 85 m | 10 D | 53 mm | 1.104% | 0.9267% | −16.1% | 1581 kN·m | 1494 kN·m | **−5.5%** | 1344 |
| 85 m | 20 D | 53 mm | 1.861% | 1.2728% | −31.6% | 1977 kN·m | 1848 kN·m | **−6.5%** | 1382 |
| 85 m | 40 D | 53 mm | 1.914% | 1.6413% | −14.2% | 2883 kN·m | 3253 kN·m | +12.8% | 1409 |

*Figures redrawn 6 Oct at profile schema 1.4.0, which put the reported pipe
on the roller TOPS rather than through the axles (L099). The strain and
moment are unchanged — the lift is a rigid translation — and so is every
`off_arc` figure below, which was always measured relative to contact.*

**Drawn at the governing step**, both cases, from the profile artifacts:
`docs/diagrams/tp_L20D_R85_maxBM.png` and `tp_L40D_R85_maxBM.png` — the step
at which the **component body** carries its maximum moment, which is what
TABLE XXIV reports. *Post-L100; the governing step itself moved, from 9 to
15 and from 43 to 49.*

| | 20 D, step 15 | 40 D, step 49 |
|---|---|---|
| shift | 5.283 m | 18.256 m |
| body moment | 1848 kN·m | 3253 kN·m |
| pipeline moment at that step | 1196 kN·m | 1350 kN·m |
| **body / pipeline** | **+54.5%** | **+141.0%** |
| component spans | x −13.3 … −5.2 | x −26.0 … −10.1 |
| lift outboard of its catenary end | 133 mm | 254 mm |
| lift on the component | 31 … 122 mm | 2 … 240 mm |
| its deflection off its own chord | −44 mm | −292 mm |

**The body now takes the load into itself, and that is the whole finding.**
Before L100 the component carried 1–3% more moment than the pipeline either
side of it; it now carries 54% and 141% more. That is a stiffer section doing
what a stiffer section should in a displacement-controlled bend, and it could
not happen while the body's interior nodes were held by no contact.

**So the reading recorded here before is withdrawn, and it was exactly
backwards.** The 1–3% separation was offered as "the first positive evidence"
that our component never engaged a second roller the way the reference's
does. It was evidence of the defect that prevented it. The 608 mm bridging
figure goes with it: the leading-end lift is now 254 mm at 40 D, and the
component's own deflection — 292 mm off its chord, which the old drawing
could not show at all — is most of what that number was measuring.

*What the figures are good for now:* the component visibly bends, rests on
the rollers it spans, and separates from the pipeline in moment. What they
are not: a settled account of the remaining strain shortfall, which is
−14.2% at 40 D and −31.6% at 20 D with the moments inside 7.7%.

the component were doing what the paper's saturation describes — spanning
two rollers and taking the extra stiffness into its own section — the body
would be pulling away from the pipeline as it lengthens, far more than this.
It barely separates, which is the same story the moment deltas tell from the
other side.

> ### The double-roller saturation — now half reproduced
>
> The paper's finding is that past a certain length the component spans two
> rollers, so extra stiffness is carried by a second support rather than by
> curvature in the pipe: **strain flattens while the moment keeps climbing**.
>
> | R = 85, 20 D → 40 D | strain | moment |
> |---|---|---|
> | Paper 1 | **+2.8%** | **+45.8%** |
> | ours, before L100 | +121.5% | +7.4% |
> | ours, after L100 | **+29.0%** | **+76.0%** |
>
> **Before the fix we produced the opposite of both halves.** Strain rose
> seventeen times faster than moment; the paper has moment rising sixteen
> times faster than strain. That inversion is now gone: moment climbs 2.6×
> faster than strain, which is the paper's qualitative behaviour and not
> ours.
>
> That it moved this way is a result in itself. The paper attributes the
> saturation to a component **engaging a second roller** — precisely the
> mechanism `header_nodes` denied the model. Fixing the cause moved the
> symptom, which is the kind of agreement between diagnosis and correction
> that a tuned parameter cannot produce.
>
> **It is reproduced in character, not in degree.** Our strain still rises
> 29% where the paper's rises 2.8%, so the plateau is softer than published.
> What remains is a real disagreement, no longer an inverted one.
>
> *The moment now overshoots* at 40 D — +12.8% against the paper, where
> every other length reads 2.3 to 7.7% low. 40 D is 16.3 m against a 9 m
> roller spacing, so the body spans nearly two full bays; whether the
> overshoot is the contact now engaging too readily, or the paper's own
> model letting go, is not settled here.

**Moment now agrees across the whole length range** — −7.7% to +12.8%,
against −2.3% to −47.3% before the fix. The claim recorded here earlier,
that TABLE XXI's good moment agreement was *specific to short components*,
is withdrawn: it was specific to components whose contact worked.

**Strain still falls away with length**, −5.5% at 10 D to −31.6% at 20 D,
and that is now the clean statement of what is left. It is one-sided LOW,
which is the opposite direction to every other strain disagreement in this
file, and it cannot be the envelope offset — an envelope cannot read low.

That it is strain-only, with the moments right, points back at §7's
local-strain-recovery question rather than away from it. A section force
that is correct while the extreme-fibre strain derived from it is 20–30% low
over long stiff bodies is what a recovery convention mismatch looks like —
and it is now the single open item that would explain the most rows.

### TABLE XXVI — two components, spacing — NOT RUN

| Case | Spacing | Paper strain | Paper BM | ours |
|---|---|---|---|---|
| C1 | 2.5 D | 0.771% | 1384 kN·m | — |
| C2 | 10 D | 0.760% | 1371 kN·m | — |
| C3 | 20 D | 0.751% | 1365 kN·m | — |

Spacing changes strain by 2.6% over an eightfold range — the paper's own
conclusion is that it is negligible. Low value, and it needs a two-component
assembly we have not built.

---

## 3. Shroud — Paper 1 TABLE XXXI, XXXIV, XXXII, XXXIII

Strain is reported by **region**, after TABLE XXIX: X1 catenary taper and
the pipe beyond it, X2/X3/X4 the deep section in thirds from the catenary
side, X5 the vessel taper and beyond. X2 is the paper's peak in every case
it ran. The five are a partition, so every element belongs to exactly one.

### TABLE XXXI and XXXIV — offset depth V

*All cases Phase 2 in the paper. `n` is the number of elements in X2 at this
mesh.*

| Config | V | Paper X2 | ours X2 | Δ | Paper X3 | ours X3 | Paper X4 | ours X4 | ours BM | n |
|---|---|---|---|---|---|---|---|---|---|---|
| R=85, 100 MT | 0.75 D | 0.62% | 0.5241% | −15.5% | 0.42% | 0.4775% | 0.35% | 0.4445% | 1248 kN·m | 1 |
| L1=10D, L2=2.5D | 1.00 D | 0.70% | 0.5976% | −14.6% | 0.55% | 0.5170% | 0.43% | 0.4586% | 1274 kN·m | 1 |
| | 1.50 D | 0.95% | 0.7336% | −22.8% | 0.75% | 0.5914% | 0.58% | 0.5068% | 1303 kN·m | 1 |
| | 2.00 D | 1.20% | 0.8824% | −26.5% | 0.88% | 0.6669% | 0.58% | 0.5562% | 1329 kN·m | 1 |
| | 2.50 D | 1.51% | 1.0034% | −33.6% | 1.07% | 0.4538% | 0.62% | 0.2451% | 1352 kN·m | 1 |
| | 3.00 D | 1.80% | 1.1577% | −35.7% | 1.20% | 0.4840% | 0.67% | 0.2501% | 1369 kN·m | 1 |
| R=70, 120 MT | 1.00 D | 0.808% | 0.8481% | **+5.0%** | — | — | — | 0.6800% | 1333 kN·m | 1 |
| L1=5D, L2=2.5D | 1.50 D | 0.970% | 0.9672% | **−0.3%** | — | — | — | 0.7375% | 1358 kN·m | 1 |
| | 2.00 D | 1.15% | 1.1415% | **−0.7%** | — | — | — | 0.5958% | 1373 kN·m | 1 |
| R=70, 100 MT | 1.00 D | 0.76% | 0.4569% | −39.9% | — | 0.2470% | — | 0.2151% | 1318 kN·m | 2 |
| L1=10D, L2=5D | 1.50 D | 1.03% | 0.8190% | −20.5% | — | 0.3252% | — | 0.2525% | 1335 kN·m | 2 |
| | 2.00 D | 1.23% | 0.3276% | −73.4% | — | 0.2190% | — | 0.1949% | 1339 kN·m | 2 |

*X3 and X4 are published only for the R = 85 configuration (TABLE XXXIV).
The `—` in our X3 column at R = 70 / 120 MT is a region holding **no
elements**: L1 = 5 D makes each third 0.677 m against an 0.813 m element.*

**Reproduced: X2 rises monotonically with V in every configuration.** Offset
depth is the dominant parameter, which is this study's finding.

**Not reproduced: the amplification rate.** At R = 85 our X2 rises at a
constant 0.35% per diameter while the paper's rate climbs (0.32 → 0.62), so
the delta fans out from −15.5% to −35.7%. This is the clearest structural
disagreement in the file and it survived the contact-surface change
untouched.

**Read the element count before the delta.** X2 holds **one element** in
nine of these twelve cases. The closest agreement here — the R = 70 / 120 MT
rows at +5.0 / −0.3 / −0.7% — is also single-element, and whether it is
physics or two coarse-mesh errors cancelling is not established.

**Bending moment is remarkably flat** — 1248 to 1373 kN·m across a fourfold
range of offset depth, 10% from end to end, while X2 more than doubles. The
rollers impose the curvature and the shroud redistributes *where* the strain
appears without much changing the section force. The paper publishes no
moment for these cases, so this is a prediction rather than a comparison.

**X3 and X4 collapse past a depth threshold.** Between V = 1.5 D and 2.5 D at
R = 85, X3 goes 0.5914 → 0.4538% and X4 0.5068 → 0.2451%, where the paper has
X3 *rising* and X4 *plateauing*. A plateau and a collapse are different
mechanisms, and the paper's X4 plateau is one of its stated design insights.

> **One hypothesis would account for the rate, the collapse, and the peak
> migrating onto the taper at R = 70, all at once**: beyond a threshold depth
> our deep section lifts clear of the rollers, so the midspan and vessel
> thirds unload while the catenary-side edge takes everything. **Unverified.**
> The check is the station contact state at V = 1.5 D against V = 2.0 D, and
> the profile artifacts already hold it.

### Mesh — the dimensionally-matched case

*V = 1.0 D, L1 = 10 D, L2 = 2.5 D, R = 85, 100 MT. The `ILS-SH` archetype is
exactly this published case, so it is the one point where dimensions match
without re-dimensioning anything.*

| Mesh | Paper X2 0.70% | Δ | Paper X3 0.55% | Δ | Paper X4 0.43% | Δ | BM |
|---|---|---|---|---|---|---|---|
| 2 × OD | 0.5976% | −14.6% | 0.5170% | −6.0% | 0.4586% | +6.7% | 1274 kN·m |
| 1 × OD | 0.6668% | −4.7% | 0.5513% | **+0.2%** | 0.4778% | +11.1% | 1300 kN·m |
| 0.5 × OD | 0.7271% | **+3.9%** | 0.5381% | −2.2% | 0.5092% | +18.4% | 1315 kN·m |

**Refinement carries X2 through the published value**, crossing it between
1 × OD and 0.5 × OD, and **X3 agrees to 0.2%** at 1 × OD. X4 stays 7–18% high
and drifts *up* with refinement — the opposite of converging — and X4 is the
region the paper says plateaus.

**The X3/X2 ratio, settled from the source.** The paper's prose generalises
it as "typically 65–75%" (TABLE XXIX) and "approximately 65–70%", but its own
TABLE XXXIV gives 79% for this case and 68 / 79 / 79 / 73 / 71 / 67% across
the six — the generalisation does not contain its own V = 1.0 D entry. Ours
is 76.6% at the finest mesh, **−3.0%** against the case value. *Compare case
against case, never case against the prose summarising a spread of cases.*

### TABLE XXXII and XXXIII — deep-section and taper length — NOT RUN

TABLE XXXII finds two regimes: L1 from 2.5 D to 10 D at V = 1 D changes
strain by under 5%, then at **L1 ≥ 25 D** a dramatic reduction as the shroud
shifts from single- to double-roller contact. TABLE XXXIII finds taper length
worth under 4%. The L1 ≥ 25 D regime is the same mechanism as TABLE XXIV's
length saturation and is the part worth running.

---

## 4. Shroud with a thick pipe inside it — Paper 1 TABLE XXXIX and XLI

*R = 85, 100 MT. Shroud fixed at L1 = 10 D, L2 = 2.5 D, V = 1 D; the thick
pipe's length varies. Compared against the shroud-only baseline, which is the
`V = 1.0 D` row of §3 — the same geometry, so X2 means the same steel in
both.*

### TABLE XXXIX — thick pipe length

| Case | Thick pipe | Paper peak | ours | Δ | where ours peaks | Paper BM | ours, body | Δ |
|---|---|---|---|---|---|---|---|---|
| baseline | shroud only | 0.70% | 0.5976% | −14.6% | X2 | — | — | — |
| 1 | 5 D | 0.952% | 0.8225% | **−13.6%** | X2 | 1405 kN·m | 1331 kN·m | **−5.3%** |
| 2 | 10 D | 1.26% | 1.2057% | **−4.3%** | **X1** | 1555 kN·m | 1506 kN·m | **−3.2%** |

*Post-L100. The moments improved from −6.5% and −12.1%; the strains moved
under 1.5%. The shroud-only baseline is unaffected by L100 — it steps no
section — so the amplification below is a changed numerator over an
unchanged denominator.*

**Case 2 needs its region label read carefully, and the paper's own wording
is the reason.** It calls Case 2's peak the "pipe-to-component junction at
X2". At 10 D the thick body is exactly as long as the deep section, so its
catenary-side junction sits at s = 6.983 — **precisely our X1/X2 boundary**.
Our peak lands 0.4 m outboard of it at s = 7.39, which our partition counts
as X1 and the paper counts as X2. It is the same piece of pipe and the same
mechanical feature; only the boundary convention differs, so 1.2204% against
1.26% is the like-for-like comparison and the X2-column value for that case
(0.1085%) is not. Case 1's 5 D body puts its junction inside X2 and needs no
such care.

That X2 column reading 0.1085% is itself informative rather than wrong: at
10 D the body fills the whole deep section, so X2, X3 and X4 all sit on stiff
pipe and read 0.10–0.11%. The strain leaves the deep section entirely and
concentrates at the junctions.

**The amplification over the shroud-only baseline is what this study is
about**, and it is reproduced in both cases:

| Case | Paper vs baseline | ours vs baseline |
|---|---|---|
| 1 (5 D) | +36.0% | **+37.6%** |
| 2 (10 D) | +80.0% | **+101.8%** |

Case 1 lands within 2 points of the published amplification. Case 2
overstates it, and the arithmetic says why: our absolute values agree far
better at the junction (−3.1%) than at the shroud-only baseline (−14.6%), so
the ratio between them inherits the baseline's shortfall.

Bending moment rises 1274 → 1314 → 1367 kN·m against the paper's
— / 1405 / 1555: the direction is reproduced and the magnitude understated,
by −6.5% and −12.1%.

### TABLE XLI — thick pipe location — NOT RUN

| Case | Thick pipe at | Paper X2 | Paper X4 | Paper BM | ours |
|---|---|---|---|---|---|
| baseline | shroud only | 0.70% | 0.35% | — | 0.5976% / 0.4586% |
| 1 | X2, catenary third | 0.901% | 0.49% | 1362 kN·m | — |
| 2 | X3, midspan | 0.744% | 0.59% | 1310 kN·m | — |
| 3 | X4, vessel third | 0.744% | 0.57% | 1271 kN·m | — |

A 2.5 D body moved along the deep section. The paper's finding is that peak
strain stays at X2 wherever the body sits, and that putting it *at* X2 is the
worst case because the stiffness discontinuity lands where curvature is
highest. Three runs, and the archetype already supports an off-centre
component.

---

## 5. External attached structures — Paper 2

*R = 85 m, 120 MT. Strain reported by fastening, after Paper 2's Fig. 38:
**X_c** within 2 × pipe OD either side of a connector, **X_i** the interior
between two connectors, **X_e** outboard from X_c to the far field. F1 has
one connector and therefore no interior, and the paper tabulates none.*

| Case | Paper X_c | ours | Δ | Paper X_i | ours | Δ | Paper X_e | ours | Δ |
|---|---|---|---|---|---|---|---|---|---|
| EA-ST F2 Case 1 | 0.936% | 0.904% | **−3.5%** | 0.043% | 0.075% | +75.0% | 0.732% | 0.533% | −27.2% |
| EA-ST F2 Case 2 | 1.410% | 1.601% | +13.6% | 0.075% | 0.124% | +65.2% | 1.021% | 0.683% | −33.1% |
| EA-SB F1 Case 1 | 2.30% | 0.941% | −59.1% | — | — | — | 1.41% | 1.118% | −20.7% |
| EA-SB F2 Case 1 | 2.24% | 1.291% | −42.3% | 0.086% | 0.137% | +59.1% | 1.45% | 1.270% | −12.4% |
| EA-SB F2 Case 2 | 2.40% | 2.170% | **−9.6%** | 0.086% | 0.122% | +42.1% | 1.52% | 0.854% | −43.8% |
| EA-SB F2 Case 3 | 2.53% | 1.509% | −40.4% | 0.085% | 0.127% | +49.4% | 1.60% | 1.394% | −12.9% |

**Reproduced: the ordering X_c > X_e ≫ X_i, in all six cases.** That is
Paper 2's actual finding and the reason the scheme exists — a frame bolted on
at points concentrates strain at its fastenings, leaves the pipe between them
almost unstrained, and the pipe outboard reads the plain overbend.

**Not reproduced: the magnitudes.** EA-ST agrees on X_c to −3.5% and +13.6%.
**EA-SB reads low**, −9.6% to −59.1%, and an envelope cannot be below a
single position of the same case — so the envelope offset is *eliminated* as
the explanation rather than left open. X_c is the quantity most sensitive to
connector placement, which is the thread to pull. X_i is high by 42–75%
everywhere; it is an order of magnitude below X_c so it moves no design
conclusion, but the sign is consistent across all five cases that have one,
which says one cause and not five.

**X_e is parked by instruction.** Its boundary follows Paper 2's *figures*,
not its prose: the text says "pipeline outside the structures" while Figs 27
and 38 draw X_e running up to where X_c begins. Implementing the prose moved
X_e from −10% to −45%.

**F1D and F2D are refused, not approximated.** A `D` connector is a deadband
and needs an active set as well as a co-rotating frame; with the frame alone
it would behave as an always-shut `S`, a different joint silently answering a
different question.

**PS layouts are prediction, not validation** — Paper 2 publishes F1 and F2
only. On the shipped archetypes, EA-ST reads X_c 0.601 / 0.357% for F2 / PS:
a pin and a roller relieve the connector and remove the shielding, X_c
falling 41% while X_i rises to **equal** X_c. EA-SB truncates at 20% of its
travel on the current contact surface and its values are lower bounds.

---

## 6. Scorecard

| Published table | Cases | Status |
|---|---|---|
| **X** plain pipe by stinger config | 3 | **done** — +16.8 / +6.1 / −7.7% |
| **XI** diameter and tension | 6 | **done** — strain +7.2 to +25.7%; *gap over `D/2R` roughly 2× the paper's* |
| **XX / XXI** thick pipe wall thickness | 9 | **done** — strain +1.8 to +17.0%, **BM −2.4 to +6.7%** (component body) |
| **XXIII / XXIV** thick pipe length | 6 | **done** — moment −7.7 … +12.8% across all lengths; saturation reproduced in character, strain still −32% at 20 D |
| **XXVI** two components, spacing | 3 | not run — paper finds the effect negligible |
| **XXXI / XXXIV** shroud offset depth | 12 | **done** — X2 monotonic in V; rate under-amplified |
| **XXXII / XXXIII** shroud L1 and L2 | — | not run — L1 ≥ 25 D regime change is the part worth having |
| **XXXIX** shroud + thick pipe length | 2 | **done** — amplification +37.9% against the paper's +36% |
| **XLI** shroud + thick pipe location | 3 | not run — three runs, archetype already supports it |
| **Paper 2** EA F1 / F2 | 6 | **done** — ordering reproduced in all six |
| **Paper 2** EA F1D / F2D | — | refused under G9, needs the `D` active set |

**44 of 50 published cases have a rebuild number.**

## 7. What is not settled

1. **Paper 2 has no citation in this repo.** Its case tables and region
   definitions were transcribed from supplied figures, so every number in §5
   is checked against a transcription rather than a source — which matters
   most for the EA-SB rows 40–60% out, where a transcription error would read
   exactly like a physics disagreement.
2. **We report extreme-fibre strain per element; the papers report "nominal
   strains at element integration points."** Expected to coincide for a B31
   beam in pure bending, **never checked against the kernel**. This is now
   the single most promising open item, because three independent lines
   point at it: §2's bending moments agree to a few percent while its
   strains disagree by 10–17% on the same nine runs; §1's TABLE XI shows our excess over pure
   bending running at roughly twice Abaqus's, measured against arithmetic
   rather than another model; and every strain disagreement in this file is
   one-sided high. All three are what a local-peak reporting offset would
   produce, and none of them would move the section force.
3. **The lift-off hypothesis in §3 is unverified** and would explain three
   disagreements at once.
4. **Whether our envelope and the paper's "Phase 2" are the same mechanical
   state** is unsettled, and sits under every shroud and combined row.
   Phase 2 carries residual plastic curvature from Phase 1 over the
   mid-stinger rollers; our envelope is a maximum over the travel we solve.
5. **`ILS-EASB` truncates at 20% of its passage** on the current contact
   surface, where it ran the full travel on the superseded one. The only
   capability regression from that change, undiagnosed.
6. **X2 holds one element at 2 × OD** in most shroud cases, including the
   closest agreements in §3.
7. **The double-roller saturation is reproduced in character but not in
   degree** (§2): moment now climbs 2.6× faster than strain where the paper
   has 16×. The inversion is gone; the plateau is still softer than
   published.
8. **Strain falls away with component length while the moment does not** —
   −5.5% at 10 D to −31.6% at 20 D with moments inside 7.7%. One-sided LOW,
   so it cannot be the envelope offset, and it is the clearest remaining
   pointer at gap 2.
9. **The 40 D moment overshoots** at +12.8% where every other length reads
   low. That body spans nearly two full roller bays, and whether the
   overshoot is our contact engaging too readily or the reference's letting
   go is unsettled.

---

## Version history

| Version | Date | What |
|---|---|---|
| **3.0** | 6 Oct 2026 | Restructured on the papers' own table numbering. Rebuild against the papers only. **Bending moment added for every case.** Shroud + thick pipe run for the first time |
| 2.0 | 6 Oct 2026 | Re-measured on the physical contact surface after L095–L098 |
| 1.0 | 6 Oct 2026 | First consolidated ledger, all results on the superseded contact surface |

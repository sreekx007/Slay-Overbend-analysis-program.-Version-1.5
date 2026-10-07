# SLAY Overbend — Validation ledger v3.0

> ## 7 Oct 2026 — four sweep defects fixed, and the whole ledger re-run
>
> Between them, L101, L105, L106 and the strain guard changed what a passage
> *is*, so every number below was re-run. The four, in the order they were
> found:
>
> | | |
> |---|---|
> | **L101** | five of seven TABLE XXXII passages had been truncating between 6.3% and 38.4% of their travel, and were compared to the paper anyway. Nothing in the artifact said so. |
> | **L105** | `lay_tension` took no `shift`, so the lay tension stayed bolted to one piece of steel for a whole passage while the terminal contact walked inboard — a free cantilever of travel-length with 100 MT on its unsupported tip. |
> | **L106** | nothing cut back the TRAVEL between positions. `solve` cuts back `lam`, which scales contact targets alone, so a formed plastic hinge stopped four of six shroud cases. |
> | **guard** | with the travel cutback in, S2-8 converged to a 96.7% strain and reported COMPLETE. A converged position whose strain runs past the end of the material table is now refused. |
>
> **What moved, and what did not.** The blast radius is narrower than the
> defect list suggests, and the reason is worth stating: where a passage
> converged all the way, the frozen lay tension acted at the **stinger tip**,
> which `report.passage.zone` already cuts out of the reporting band. The
> reported peaks never saw it. It is the cases that **truncated** that moved.
>
> | table | verdict |
> |---|---|
> | **XI** diameter and tension | unchanged to four decimals; all six now confirmed at 100% of travel |
> | **XXIII / XXIV** component length | unchanged to four decimals (0.8470 against 0.8471, and so on); all six at 100% |
> | **XX / XXI** component wall | unchanged — strains under 1% of themselves, moments under 6 kN·m; all nine at 100% |
> | **X** stinger configuration | **moved**, +1.8% on config A — the only 120 MT table, and the highest tension in Paper 1 |
> | **XXXI / XXXIV** shroud offset V | **moved hard** in configuration C: −39.9 … −73.4% became −5.4 … −22.1%. Configuration A's X3/X4 at the deep offsets had been *falling* with V, which is the wrong direction; they are now monotonic |
> | **XXXII / XXXIII** shroud L1 and L2 | **moved hard** — five of seven had been truncating; the dual-roller trend changed sign |
>
> Two things were found by the re-run itself, not by the fixes. `slide.passage`
> sweeps plain pipe over `4 × OD` with **no lead clearance**, while
> `completion`'s default is `L_comp + 1 + 1`; four study tools used the
> default, and a 20 in passage that had swept every metre reported **102%**
> and voided all six TABLE XI rows. `completion` now takes an explicit total
> and `slide.passage` returns the one it used. A **false VOID is as damaging
> as a false result**, and this ledger would have carried six of them.

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

*`tools/study_table_x.py`. All three sweep 100% of their travel.*

| Config | R | Paper 1 strain | ours | Δ | ours BM | Paper BM |
|---|---|---|---|---|---|---|
| A | 70 m | 0.46% | 0.5468% | **+18.9%** | 1258 kN·m | not published |
| B | 85 m | 0.38% | 0.4070% | **+7.1%** | 1185 kN·m | not published |
| C | 105 m | 0.32% | 0.2965% | **−7.3%** | 1072 kN·m | not published |

*Re-run 7 Oct. This is the only table in Paper 1 at **120 MT**, and the only
one whose values moved: config A from 0.5373% to 0.5468%, about +1.8%. B and
C moved under 1%. Whether that is L105 or the step size this runner uses is
not established — the earlier numbers were produced ad hoc and the step was
not recorded — so it is reported as a change, not attributed.*

Monotonic high-to-low across the radii — the R-trend divergence, crossing
between 85 and 105 m, with best agreement at R = 85 where the two curves
cross.

### TABLE XI — diameter and tension at R = 70

*`tools/study_table_xi.py`. Re-run 7 Oct: **unchanged to four decimals**, and all six now confirmed at 100% of their travel (they first came back VOID on a false completion check — see the banner). **All six converged**, zero-tension rows
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

*`tools/study_table_xx.py`. Re-run 7 Oct; all nine sweep 100% of their
travel.*

| Case | t | R | Paper strain | ours | Δ | Paper BM | ours, body | Δ | ours, pipe |
|---|---|---|---|---|---|---|---|---|---|
| A1 | 32 mm | 70 m | 0.562% | 0.6358% | +13.1% | 1311 kN·m | 1299.2 kN·m | **−0.9%** | 1284.6 |
| A1 | | 85 m | 0.473% | 0.4804% | **+1.6%** | 1251 kN·m | 1247.1 | **−0.3%** | 1236.0 |
| A1 | | 100 m | 0.339% | 0.3771% | +11.2% | 1131 kN·m | 1182.7 | +4.6% | 1174.5 |
| A2 | 42 mm | 70 m | 0.647% | 0.7015% | +8.4% | 1347 kN·m | 1320.6 | **−2.0%** | 1304.4 |
| A2 | | 85 m | 0.508% | 0.5452% | +7.3% | 1288 kN·m | 1276.1 | **−0.9%** | 1263.0 |
| A2 | | 100 m | 0.358% | 0.4183% | +16.8% | 1144 kN·m | 1212.7 | +6.0% | 1204.3 |
| A3 | 53 mm | 70 m | 0.727% | 0.7701% | **+5.9%** | 1366 kN·m | 1337.5 | **−2.1%** | 1320.0 |
| A3 | | 85 m | 0.556% | 0.6127% | +10.2% | 1311 kN·m | 1297.0 | **−1.1%** | 1284.0 |
| A3 | | 100 m | 0.395% | 0.4487% | +13.6% | 1184 kN·m | 1230.8 | +4.0% | 1220.9 |

*Essentially unchanged by the re-run — strains moved under 1% of themselves
(0.6298 → 0.6358, 0.4815 → 0.4804, and so on) and the body moments by under
6 kN·m. These are 2.5 D components whose passages already completed, so they
are in the same class as TABLE XXIII/XXIV: the frozen lay tension acted at
the stinger tip, outside the reporting band.*

**The moment agreement is the strongest in the ledger** — eight of nine
within 6%, six of nine within 2.1% — and it is one-sided by radius: negative
at R = 70 and 85, positive at R = 100. The strain is high against the paper
in every one of the nine.
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

**Re-run 7 Oct after L105 and L106, and nothing material changed** — 0.8470
against 0.8471, 1.4156 against 1.4161, 1.9757 against 1.9763, 0.9265 against
0.9267, 1.2724 against 1.2728, 1.6418 against 1.6413; the 40 D moment moved
from +12.8% to +13.0%. All six are now confirmed at 100% of their travel
(11/11, 18/18, 29/29, 18/18, 30/30, 50/50 positions).

*That is a result, not a non-event.* It is what bounds the blast radius of
those two defects to passages that **truncated**: where one converged all
the way, the frozen lay tension acted at the stinger tip, which
`report.passage.zone` already cuts out of the reporting band. The saturation
reading is unchanged too — ours +29.0% strain and +76.3% moment from 20 D to
40 D, against the paper's +2.8% and +45.8%.

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

### TABLE XXVI — two components, spacing

*`tools/study_table_xxvi.py`. Two 2.5 D bodies at 65 mm wall, R = 70 m,
100 MT. All three sweep 100% of their travel.*

| Case | Spacing | assembly span | Paper strain | ours | Δ | Paper BM | ours, body | Δ |
|---|---|---|---|---|---|---|---|---|
| C1 | 2.5 D | 3.048 m | 0.771% | 0.9253% | +20.0% | 1384 kN·m | 1369.8 kN·m | **−1.0%** |
| C2 | 10 D | 6.096 m | 0.760% | 0.8671% | +14.1% | 1371 kN·m | 1382.4 | **+0.8%** |
| C3 | 20 D | 10.160 m | 0.751% | 0.8362% | +11.3% | 1365 kN·m | 1352.1 | **−0.9%** |

**The sign agrees and the magnitude does not.** Both fall with spacing — the
paper 0.771 → 0.751%, a spread of 2.6%, and ours 0.9253 → 0.8362%, a spread
of 9.6%. The paper's conclusion is that the spacing is *negligible*; at 3.7×
its spread, ours is not. The moment is within 1% on all three, which is the
tightest agreement anywhere in this ledger.

**The configuration is inferred, and the inference is stated rather than
buried.** TABLE XXVI names no radius, tension or component. But its C1 row
reads 0.771% and **1384 kN·m**, and TABLE XXIII's B1 — R = 70 m, 100 MT, a
2.5 D body at 65 mm — reads 0.780% and the **same 1384 kN·m**. A shared
moment to four figures across two tables is not a coincidence, so C1 is read
as B1 with a second body added. If that reading is wrong the three rows move
together and the *trend*, which is what the table is about, survives it.

*The earlier note here — "it needs a two-component assembly we have not
built" — was wrong. `ils_builder` takes a list of components and has always
iterated over it; what was missing was a spec with two entries in it, which
is data. Checked before the runner was written: the archetype with a second
GD-TP at a distinct `id` and `centre_x` builds at all three spacings and
reports the spans those gaps imply.*

---

## 3. Shroud — Paper 1 TABLE XXXI, XXXIV, XXXII, XXXIII

Strain is reported by **region**, after TABLE XXIX: X1 catenary taper and
the pipe beyond it, X2/X3/X4 the deep section in thirds from the catenary
side, X5 the vessel taper and beyond. X2 is the paper's peak in every case
it ran. The five are a partition, so every element belongs to exactly one.

### TABLE XXXI and XXXIV — offset depth V

*All cases Phase 2 in the paper. `n` is the number of elements in X2 at this
mesh.*

*`tools/study_table_xxxi.py`. Re-run 7 Oct; all twelve sweep 100% of their
travel.*

| Config | V | Paper X2 | ours X2 | Δ | Paper X3 | ours X3 | Paper X4 | ours X4 | ours BM |
|---|---|---|---|---|---|---|---|---|---|
| R=85, 100 MT | 0.75 D | 0.62% | 0.5239% | −15.5% | 0.42% | 0.4773% | 0.35% | 0.4443% | 1247.5 kN·m |
| L1=10D, L2=2.5D | 1.00 D | 0.70% | 0.5973% | −14.7% | 0.55% | 0.5167% | 0.43% | 0.4584% | 1274.0 |
| | 1.50 D | 0.95% | 0.7332% | −22.8% | 0.75% | 0.5912% | 0.58% | 0.5066% | 1303.3 |
| | 2.00 D | 1.20% | 0.8820% | −26.5% | 0.88% | 0.6667% | 0.58% | 0.5560% | 1329.0 |
| | 2.50 D | 1.51% | 1.0338% | −31.5% | 1.07% | 0.7387% | 0.62% | 0.6043% | 1351.6 |
| | 3.00 D | 1.80% | 1.1852% | −34.2% | 1.20% | 0.8118% | 0.67% | 0.6391% | 1368.9 |
| R=70, 120 MT | 1.00 D | 0.808% | 0.8685% | **+7.5%** | — | — | — | 0.6675% | 1332.9 |
| L1=5D, L2=2.5D | 1.50 D | 0.970% | 0.9822% | **+1.3%** | — | — | — | 0.7308% | 1358.0 |
| | 2.00 D | 1.15% | 1.1410% | **−0.8%** | — | — | — | 0.8378% | 1372.3 |
| R=70, 100 MT | 1.00 D | 0.76% | 0.7187% | **−5.4%** | — | 0.5567% | — | 0.5386% | 1317.6 |
| L1=10D, L2=5D | 1.50 D | 1.03% | 0.8389% | −18.6% | — | 0.6084% | — | 0.5874% | 1335.0 |
| | 2.00 D | 1.23% | 0.9580% | −22.1% | — | 0.6699% | — | 0.6403% | 1352.6 |

**Configuration C is where the sweep defects were hiding**, and the change is
the largest in the ledger:

| V | before | after |
|---|---|---|
| 1.00 D | −39.9% | **−5.4%** |
| 1.50 D | −20.5% | −18.6% |
| 2.00 D | −73.4% | **−22.1%** |

Those three rows are the same geometry as TABLE XXXII's S2-3 and S2-6, run by
a different tool, and the two agree to four decimals — 0.7187% and 0.9580%
from both. That cross-check is kept deliberately: two tools, one answer.

**Configuration A's X3 and X4 moved at the deep offsets.** At V = 2.50 D and
3.00 D they had read 0.4538 / 0.4840% and 0.2451 / 0.2501% — *lower* than the
shallower offsets, which is the wrong direction and was visible in the old
table as a non-monotonicity nobody chased. They now read 0.7387 / 0.8118% and
0.6043 / 0.6391%, monotonic in V like every other column. The X2 column barely
moved (−33.6 → −31.5%, −35.7 → −34.2%), so this was a truncation eating the
deep-section tail, not a change in the peak.

**What did not change is the finding.** X2 is still monotonic in V and the
rate is still under-amplified against the paper in configuration A — −15.5%
at 0.75 D widening to −34.2% at 3.00 D. Configuration B, the shortest shroud
at the highest tension, agrees within 7.5%.

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

### TABLE XXXII and XXXIII — deep-section and taper length

*R = 70 m, 100 MT, 9 m spacing. S2-4 is TABLE XXXIII; the rest are XXXII.
Strain is the X2 region peak, the quantity the paper tabulates.*

| case | L1 | L2 | V | rebuild X2 | paper | Δ | peak region | BM kN·m |
|------|-----|-----|-----|-----------|-------|-----|-----|---------|
| S2-1 | 2.5 D | 2.0 D | 1.0 D | 0.8911% | 0.78% | **+14.2%** | X2 | 1327.1 |
| S2-2 | 4.0 D | 5.0 D | 1.0 D | 0.7353% | 0.75% | **−2.0%** | X1 | 1317.5 |
| S2-3 | 10.0 D | 5.0 D | 1.0 D | 0.7187% | 0.76% | **−5.4%** | X1 | 1317.6 |
| S2-4 | 10.0 D | 1.0 D | 1.0 D | 0.9089% | 0.79% | **+15.1%** | X2 | 1345.1 |
| S2-6 | 10.0 D | 5.0 D | 2.0 D | 0.9580% | 1.23% | **−22.1%** | X1 | 1352.6 |
| S2-7 | 25.0 D | 2.0 D | 2.0 D | 1.0960% | 0.66% | **+66.1%** | X2 | 1342.4 |
| S2-8 | 50.0 D | 2.0 D | 2.0 D | 0.8553% | 0.59% | **+45.0%** | X1 | 1336.1 |

All seven sweep their full travel. Bending moment sits in a 2.7% band
(1317.5 – 1352.6 kN·m) across a 20-fold change in L1, which is its own
result: the moment is set by the stinger, not by the shroud.

**The two trends.**

*Control, V = 1 D, L1 2.5 → 10 D.* The paper finds this flat — 0.78 / 0.75 /
0.76, a spread of 3.8%. The rebuild gives 0.891 / 0.735 / 0.719, a spread of
19.4%. Not flat, and the disagreement is concentrated in S2-1, the shortest
shroud, which is also the only one of the three whose peak sits in X2 rather
than X1.

*Dual-roller, V = 2 D, L1 10 → 25 → 50 D.* The paper finds a 52% drop as the
shroud grows long enough to span two roller bays. The rebuild gives 0.958 /
1.096 / 0.855 — a drop of 10.7% from 10 D to 50 D. **The direction is now
reproduced**; the magnitude is not. Before the sweep defects below were
fixed, the same comparison read **+160%**, i.e. the opposite sign, so this is
the first version of this table in which the mechanism appears at all.

**Read this table against what it cost to get.** Every number here is
post-L101 and post-L105/L106, and the history is the reason to treat the two
remaining outliers (S2-7 +66.1%, S2-1 +14.2%) as open questions rather than
settled disagreements:

| | |
|---|---|
| L101 | five of the seven passages had been truncating between 6.3% and 38.4% of their travel, and were tabulated against the paper anyway |
| L105 | the lay tension stayed bolted to one piece of steel for a whole passage, leaving a free cantilever of travel-length with 100 MT on its tip |
| L106 | nothing cut back the TRAVEL between positions, so a formed plastic hinge stopped four of six cases |
| guard | with the travel cutback in, S2-8 converged to a 96.7% strain and reported COMPLETE; a converged position whose strain runs off the material table is now refused |

S2-8 is the clearest illustration: it has read 0.8511% (truncated at 10% of
travel), 22.4324% (complete, and nonsense), and 0.8553% (complete, guarded)
within a day. Only the last is a result.

---

## 4. Shroud with a thick pipe inside it — Paper 1 TABLE XXXIX and XLI

*R = 85, 100 MT. Shroud fixed at L1 = 10 D, L2 = 2.5 D, V = 1 D; the thick
pipe's length varies. Compared against the shroud-only baseline, which is the
`V = 1.0 D` row of §3 — the same geometry, so X2 means the same steel in
both.*

### TABLE XXXIX — thick pipe length

*`tools/study_table_xxxix.py`. Re-run 7 Oct; all three sweep 100% of their
travel.*

| Case | Thick pipe | Paper peak | ours X2 | overall | Δ | where ours peaks | Paper BM | ours, body | Δ |
|---|---|---|---|---|---|---|---|---|---|
| baseline | shroud only | 0.70% | 0.5973% | 0.6525% | −14.7% | **X1** | — | 1274.0 kN·m | — |
| 1 | 5 D | 0.952% | 0.8220% | 0.8220% | **−13.7%** | X2 | 1405 kN·m | 1314.1 | **−6.5%** |
| 2 | 10 D | 1.26% | *empty* | 1.2052% | **−4.3%** | **X1** | 1555 kN·m | 1365.0 | −12.2% |

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

### TABLE XLI — thick pipe location

*A 2.5 D body moved along the deep section. `tools/study_table_xxxix.py
--table XLI`; all four sweep 100% of their travel.*

| Case | Thick pipe at | Paper X2 | ours X2 | overall | Δ | Paper X4 | ours X4 | Paper BM | ours, body | Δ |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | shroud only | 0.70% | 0.5973% | 0.6525% | −14.7% | 0.35% | 0.4584% | — | 1274.0 kN·m | — |
| 1 | X2, catenary third | 0.901% | *empty* | 0.8132% | **−9.7%** | 0.49% | 0.4838% | 1362 kN·m | 1307.5 | **−4.0%** |
| 2 | X3, midspan | 0.744% | 0.6714% | 0.6714% | **−9.8%** | 0.59% | 0.5483% | 1310 kN·m | 1302.9 | **−0.5%** |
| 3 | X4, vessel third | 0.744% | 0.6811% | 0.6811% | **−8.4%** | 0.57% | *empty* | 1271 kN·m | 1287.5 | **+1.3%** |

**The paper's finding is reproduced.** It says peak strain stays at X2
wherever the body sits, and that putting the body *at* X2 is the worst case
because the stiffness discontinuity lands where curvature is highest. Our
overall peaks are 0.8132 / 0.6714 / 0.6811% — the catenary third is the worst
by 19%, and the other two are within 1.5% of each other, exactly as the paper
has them identical at 0.744%.

The strain is low by 8.4–9.8% across all three and the **moment is within 4%**,
tightening to −0.5% and +1.3% for the two mid-and-vessel positions.

*Two rows have an **empty** X2 or X4, and that is a partition boundary rather
than a measurement.* Where the thick body's junction lands within a
centimetre of one of our region boundaries, the region on the far side holds
no elements at this mesh. The difference is then taken on the **overall
peak** — the same steel and the same mechanical feature, counted into a
different region by a boundary that falls elsewhere. This is the same
ambiguity TABLE XXXIX's 10 D case carries, and the reason the region a peak
is *labelled* with is reported beside its value rather than instead of it.

---

## 5. External attached structures — Paper 2

*R = 85 m, 120 MT. Strain reported by fastening, after Paper 2's Fig. 38:
**X_c** within 2 × pipe OD either side of a connector, **X_i** the interior
between two connectors, **X_e** outboard from X_c to the far field. F1 has
one connector and therefore no interior, and the paper tabulates none.*

*Re-run 7 Oct after L105 and L106. **All six sweep 100% of their travel**,
and the values are unchanged to the third decimal — the same verdict as
Paper 1's completing tables, and for the same reason.*

| Case | Paper X_c | ours | Δ | Paper X_i | ours | Δ | Paper X_e | ours | Δ |
|---|---|---|---|---|---|---|---|---|---|
| EA-ST F2 Case 1 | 0.936% | 0.904% | **−3.5%** | 0.043% | 0.075% | +74.9% | 0.732% | 0.533% | −27.3% |
| EA-ST F2 Case 2 | 1.410% | 1.601% | +13.5% | 0.075% | 0.124% | +65.1% | 1.021% | 0.683% | −33.1% |
| EA-SB F1 Case 1 | 2.30% | 0.941% | −59.1% | — | — | — | 1.41% | 1.117% | −20.8% |
| EA-SB F2 Case 1 | 2.24% | 1.291% | −42.4% | 0.086% | 0.137% | +59.0% | 1.45% | 1.270% | −12.4% |
| EA-SB F2 Case 2 | 2.40% | 2.169% | **−9.6%** | 0.086% | 0.122% | +42.1% | 1.52% | 0.854% | −43.8% |
| EA-SB F2 Case 3 | 2.53% | 1.508% | −40.4% | 0.085% | 0.127% | +49.3% | 1.60% | 1.394% | −12.9% |

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

### PS layouts — prediction, not validation

**Paper 2 publishes F1 and F2 only**, so nothing below has a published
counterpart. `PS` is `(None, 'P', None, 'S', None)` — a pin at slot 2 and a
*skewed* roller at slot 4 — and these are the **same case dimensions** as the
F2 rows above, so the honest comparison is against our own F2 numbers.

*Run 7 Oct; all six sweep 100% of their travel. The earlier note that EA-SB
"truncates at 20% of its travel and its values are lower bounds" no longer
holds — that was L105 and L106, and both are fixed.*

| Case | X_c, F2 | X_c, PS | | X_i, F2 | X_i, PS |
|---|---|---|---|---|---|
| EA-ST Case 1 | 0.904% | 0.367% | **−59%** | 0.075% | **0.365%** |
| EA-ST Case 2 | 1.601% | 0.371% | **−77%** | 0.124% | **0.371%** |
| EA-SB F1 Case 1 | 0.941% | 1.098% | +17% | — | — |
| EA-SB F2 Case 1 | 1.291% | 0.951% | −26% | 0.137% | **0.647%** |
| EA-SB F2 Case 2 | 2.169% | 1.113% | −49% | 0.122% | **0.751%** |
| EA-SB F2 Case 3 | 1.508% | 0.959% | −36% | 0.127% | **0.623%** |

**One mechanism, in both archetypes.** A pin and a skewed roller cannot carry
the moment an F connector carries, so they *relieve the fastening* — X_c
falls, by 26–77% in five of the six cases. What they cannot do is shield the
pipe between them, so the interior stops being quiet: X_i rises by a factor
of 5 in both EA-SB F2 cases and, in EA-ST, rises to **exactly equal X_c**
(0.367 against 0.365%, and 0.371 against 0.371%).

That second half is the part worth noticing. Under F2 the design question is
"how bad is it at the fastening"; under PS the peak is no longer at the
fastening at all, and the X_c/X_i/X_e partition — which exists because the
paper found X_c ≫ X_i — stops carrying the information it was built to
carry. EA-SB F1 is the one case where X_c *rises*, and it has a single
connector, so there is no interior for the load to move into.

**The earlier figures recorded here, X_c 0.601 / 0.357% for F2 / PS, are
withdrawn.** They came from truncated passages on a frozen lay tension. The
qualitative reading they supported — the connector is relieved and the
shielding is lost — survives, and is now stronger: a 41% fall became 59–77%,
and "X_i rises to equal X_c" is now exact rather than approximate.

**F1D and F2D are refused, not approximated.** A `D` connector is a deadband
and needs an active set as well as a co-rotating frame; with the frame alone
it would behave as an always-shut `S`, a different joint silently answering a
different question.

*The `S` in a PS layout is itself refused by the mesher under G9 and is
emitted only through `emit_unenforced_conn_types={'S'}` — the narrow opt-in
where the mesher emits the joint and the caller takes on enforcing it.
Checked before these runs rather than assumed: one skewed row is resolved and
one applied, every Newton iteration, in a co-rotating frame. Had it resolved
none, the opt-in would have deleted the constraint and these numbers would be
a G9 violation routed around rather than respected.*

---

## 6. Scorecard

| Published table | Cases | Status |
|---|---|---|
| **X** plain pipe by stinger config | 3 | **re-run 7 Oct** — +18.9 / +7.1 / −7.3%; moved ~1.8% on config A |
| **XI** diameter and tension | 6 | **re-run 7 Oct, unchanged** — strain +7.2 to +25.7%; *gap over `D/2R` roughly 2× the paper's* |
| **XX / XXI** thick pipe wall thickness | 9 | **re-run 7 Oct, unchanged** — strain +1.6 to +16.8%, **BM −2.1 to +6.0%** (component body) |
| **XXIII / XXIV** thick pipe length | 6 | **re-run 7 Oct, unchanged** — moment −7.7 … +13.0%; saturation still not reproduced, strain −31.6% at 20 D |
| **XXVI** two components, spacing | 3 | **run 7 Oct** — strain +11.3 to +20.0%, **BM within 1%**; the fall with spacing agrees in sign, 3.7× in magnitude |
| **XXXI / XXXIV** shroud offset depth | 12 | **re-run 7 Oct** — config C from −39.9 … −73.4% to −5.4 … −22.1%, the largest change in the ledger; A's X3/X4 now monotonic in V; X2 still under-amplified |
| **XXXII / XXXIII** shroud L1 and L2 | 7 | **run, all seven complete** — −22.1% to +66.1%; the dual-roller drop is reproduced in direction (−10.7% against the paper's −52%) for the first time |
| **XXXIX** shroud + thick pipe length | 2 | **re-run 7 Oct** — strain −13.7% and −4.3%; BM −6.5% and −12.2% |
| **XLI** shroud + thick pipe location | 3 | **run 7 Oct** — strain −8.4 to −9.8%, **BM −4.0 to +1.3%**; the paper's worst-case position is reproduced |
| **Paper 2** EA F1 / F2 | 6 | **re-run 7 Oct, unchanged** — ordering reproduced in all six; all at 100% of travel |
| **Paper 2** EA F1D / F2D | — | refused under G9, needs the `D` active set |

**50 of 50 published cases have a rebuild number, and every one of them was produced by the current program.** Paper 1 and Paper 2 are both complete. Six PS cases are run as prediction, having no published counterpart; F1D and F2D remain refused under G9.

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

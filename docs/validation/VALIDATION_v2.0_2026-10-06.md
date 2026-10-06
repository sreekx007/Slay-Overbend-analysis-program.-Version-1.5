# SLAY Overbend — Validation ledger v2.0

**Every published case we have a number for, in one table.**

One row per published case. Each row says which program produced our
number, because that is not uniform — some cases the rebuild has run, some
only the original toolchain has, and some neither.

*Version 2.0, 6 Oct 2026. Branch `claude/program-rebuild-status-bya72s`.
Supersedes `VALIDATION_v1.0_2026-10-06.md`.*

> ## What changed from v1.0, and why every number was re-run
>
> **The default contact surface.** v1.0's rebuild results were all computed
> with `contact_surface='centreline'` — the pipe centreline driven onto the
> `R` arc. `R` is measured to the roller **centreline**; the roller top is
> `r_roller` above that and the pipe's bottom surface rests on it, so the
> pipe centreline really rides at `R + r_roller + OD/2`. That is now the
> default (`DEFAULT_SURFACE = 'bottom'`), and it is the geometry the rig has.
>
> It is a 0.59% change in radius and it would be reasonable to expect a
> 0.59% change in strain. **It is not that simple**, which is the reason for
> a full re-run rather than a scaling factor: the contact slots move
> outboard by `(R_eff − R)·θ` — 0.32 m at SR7 — so **the peak moves with
> them**, and the before and after numbers are the peak of a field sampled
> in different places. On plain pipe the net effect is −0.91% to +0.45%,
> smaller than the radius change and not even consistent in sign.
>
> Two defects surfaced when the default moved, both unreachable before it
> because `s_material` equalled `s_arc` under 'centreline':
>
> * **L095** — the terminal slot fell 0.32 m off the end of the mesh and the
>   bracket clamped it silently, on the station that bears the lay tension.
> * **L096** — the margin that fixes L095 is a hard pair with the OD, and
>   *too much* room is worse than too little: the surplus is unconstrained
>   pipe past the last contact, which is the free cantilever D6 removed. A
>   6 in passage given a 16 in margin went from 7/7 converged to failing at
>   `lam=0.0000`.
>
> So v1.0's numbers are not merely on the wrong surface; some were computed
> with a clamped terminal slot. Both files are kept so the comparison
> between them is available, and v1.0 is unedited for that reason.

---

## The two sources

| | What it covers | Citation |
|---|---|---|
| **Paper 1** | Plain pipe (Study 1 / TABLE X, XI), thick pipe GD-TP (Series 3 / TABLE XIX–XXVI), shroud GD-SH (Series 4 / TABLE XXVIII–XXXIV), the two combined (Series 5 / TABLE XXXVIII–XXXIX) | Sivaraman & Reddy, *Toward AI-Assisted Conceptual Design of Subsea Inline Structures*, IJRASET Vol. 14 Issue VII, July 2026, doi 10.22214/ijraset.2026.84268. Benchmark is an **Abaqus** B31 beam model. **Read in full 6 Oct 2026** — 52 pp |
| **Paper 2** | External attached structures — EA-ST (stand-off) and EA-SB (sledge base) on F1 and F2 connections, and the X_c / X_i / X_e reporting scheme (its Figs 27 and 38) | **Not recorded in this repo.** Supplied as figures only; the case tables and region definitions were transcribed from them. See *Gaps* |

**Paper 1's transcriptions are verified against the source** (6 Oct 2026):
TABLE X, XX, XXXI and XXXIX are all exactly as recorded in this repo. Three
configuration facts the transcriptions lacked:

1. **Roller spacing is 9 m c/c throughout**, stated once in the model
   description and never repeated per study.
2. **Every Series 4 and Series 5 case is governed by Phase 2**, not Phase 1.
   Phase 1 is plastic bending over the first two rollers from a straight,
   stress-free pipe; Phase 2 is the elastic bend-unload cycle over the
   mid-stinger rollers, offset by the residual plastic curvature Phase 1
   left. Plain pipe and Series 3 are Phase 1.
3. **TABLE XXXIV** gives X3 and X4 absolutes for all six offset depths, so
   the shroud comparison is three regions wide.

### A third comparison that is not a paper

`run_slay` — the **original validated Python toolchain** in this repo. For
the rebuild it is a *stronger* target than either paper, because it can be
run here at exactly our configuration and a disagreement with it is
unambiguously our defect. **It runs 'centreline'**, so the like-for-like
comparison in §A.1 is made on that surface deliberately: a like-for-like
comparison follows the reference, not our default.

### How to read a delta

A paper delta is **not** an error bar. Known offsets, all documented:

* **The R-trend divergence.** Abaqus amplification rises with stinger radius
  and the Python toolchain's falls; they cross near R = 80 m. A delta high
  at R = 70 and low at R = 105, flipping sign across the table, is the
  *signature* and not noise (`T5_solve_spec.md` §4).
* **Mesh.** At the ruled 2 × OD density (G10) no component case is
  converged, and refinement moves the answer. Every component row states
  its mesh.
* **Envelope vs single position.** We report a peak across the whole
  passage; the papers report a single analysis. An envelope cannot be
  *below* a single position of the same case, so this only ever explains us
  reading **high**.
* **Contact surface.** New in v2.0 and not a simple scaling, per the box
  above. Where a v1.0 number is quoted for comparison it is labelled.

---

## A. Paper 1, Study 1 — plain pipe

406.4 × 21 mm (16" × 21 mm seamless), 120 MT, J2 plasticity.
**The steel is DNV Grade 450**, API 5L X65-equivalent, named in
`nlfea_v4.py`: SMYS 450 MPa, certificate 448 MPa, E = 207 GPa,
Ramberg-Osgood n = 20.59. `material('j2')` is its incremental form, a table
from **360 to 530 MPa** over 0 to 5.26% plastic strain at E = 210 GPa; the
360 MPa is where this steel's round-house curve leaves the elastic line
(exactly 0.800 × 450 MPa), **not** a grade SMYS. Every result in this file
used `material('j2')`.

### A.1 Rebuild against `run_slay` — like-for-like, J2 against J2, 'centreline'

*8 m spacing (the reference program's own), staged four-step sequence,
`tools/stage_run.py`. Peak in the SR2–SR3 span on both sides. Run on
'centreline' because that is the surface `run_slay` runs — **this table is
not affected by the v2.0 change** and carries over from v1.0 unchanged.*

| R | rebuild | `run_slay` | delta |
|---|---|---|---|
| 70 m | 0.5179% | 0.5271% | **−1.7%** |
| 85 m | 0.3884% | 0.3937% | **−1.3%** |
| 105 m | 0.2879% | 0.2903% | **−0.8%** |

**The rebuild reproduces the original toolchain within 1.7% at every
radius, with the peak in the same span.** The strongest validation result in
the repo. The single proportional solve of the same case is +15 to +21% with
the peak displaced to SR6 — the staging is what buys the agreement (L053).

On the new default the same cases read 0.5197 / 0.3885 / 0.2877%, so this
agreement is unchanged either way (at R = 85 the two surfaces differ by
0.02%).

### A.2 Rebuild against Paper 1 — the paper's own configuration

*9 m spacing, 120 MT, as TABLE X states. Default contact surface.*

| R | rebuild | Paper 1 (Abaqus) | delta | v1.0 ('centreline') |
|---|---|---|---|---|
| 70 m | 0.5373% | 0.46% | **+16.8%** | 0.5423% (+17.9%) |
| 85 m | 0.4032% | 0.38% | **+6.1%** | 0.4014% (+5.6%) |
| 105 m | 0.2954% | 0.32% | **−7.7%** | 0.2942% (−8.1%) |

Monotonic high-to-low across the radii — the R-trend divergence, crossing
between 85 and 105 m. Agreement is best at R = 85, where the two curves
cross.

### A.3 Paper 1 TABLE XI — diameter and tension, R = 70 — NOT RUN

| Pipe | Tension | Paper 1 FEA | Paper 1 analytical `D/2R` | ours |
|---|---|---|---|---|
| 6" (168 × 21) | 0 MT | 0.13% | 0.12% (+8%) | — |
| 6" | 100 MT | 0.29% | — | — |
| 16" (406 × 21) | 0 MT | 0.33% | 0.29% (+14%) | — |
| 16" | 100 MT | 0.42% | — | — |
| 20" (508 × 21) | 0 MT | 0.42% | 0.36% (+17%) | — |
| 20" | 100 MT | 0.54% | — | — |

**These are the only rows in Paper 1 carrying an independent analytical
check**, which makes them the most valuable unrun cases in the file. The
zero-tension rows are the risk: with no tension the one-sided rollers have
nothing pulling the pipe onto the stinger, so convergence is not assumed.

---

## B. Paper 1, Series 3 — thick pipe GD-TP

*100 MT, 1000 mm component, **9 m spacing** (the paper's own), shift 0 for
the paper. Constant bore, `OD_comp = ID + 2t` — the paper's own convention
(our 53 mm case computes OD 470.4 mm and I/Ip = 3.248 against the paper's
stated 471 mm and ~3.2×). Peak at the pipe-to-component junction at SR2,
Phase 1.*

### B.1 `run_slay` against Paper 1 — ORIGINAL program, 8 m, 'centreline'

*Carried over from v1.0 unchanged: these are the original toolchain's
numbers and the v2.0 change does not touch them. Note the spacing — 8 m
against the paper's 9 m, so this is **not** like-for-like against Paper 1
and must not be read as a toolchain divergence.*

| Case | t | OD_comp | R = 70 | R = 85 | R = 100 |
|---|---|---|---|---|---|
| A1 | 32 mm | 428.4 mm | 0.7086% | 0.4876% | 0.3478% |
| A2 | 42 mm | 448.4 mm | 0.7877% | 0.5308% | 0.3782% |
| A3 | 53 mm | 470.4 mm | 0.8650% | 0.5715% | 0.4074% |
| | | **Paper 1** | 0.562 / 0.647 / 0.727% | 0.473 / 0.508 / 0.556% | 0.339 / 0.358 / 0.425% |

### B.2 Rebuild against Series 3 — all nine values, at the paper's configuration

*Re-measured 6 Oct 2026 on the default contact surface. R = 70 / 85 / 100 m,
100 MT, 9 m spacing, L = 1000 mm, 2 × OD mesh (the paper's own density).
Passage envelope with edge crossings.*

| Case | t | R | rebuild | Paper 1 | delta | v1.0 | vs v1.0 |
|---|---|---|---|---|---|---|---|
| A1 | 32 mm | 70 m | 0.6298% | 0.562% | **+12.1%** | 0.6421% | −1.9% |
| A1 | | 85 m | 0.4815% | 0.473% | **+1.8%** | 0.4875% | −1.2% |
| A1 | | 100 m | 0.3779% | 0.339% | +11.5% | 0.3815% | −0.9% |
| A2 | 42 mm | 70 m | 0.7002% | 0.647% | +8.2% | 0.7132% | −1.8% |
| A2 | | 85 m | 0.5476% | 0.508% | +7.8% | 0.5546% | −1.3% |
| A2 | | 100 m | 0.4188% | 0.358% | +17.0% | 0.4214% | −0.6% |
| A3 | 53 mm | 70 m | 0.7709% | 0.727% | **+6.0%** | 0.7857% | −1.9% |
| A3 | | 85 m | 0.6153% | 0.556% | +10.7% | 0.6237% | −1.3% |
| A3 | | 100 m | 0.4489% | 0.425% | **+5.6%** | 0.4519% | −0.7% |

**All nine within +1.8% to +17.0%, mean about +9%, every one high.** The
envelope offset predicts exactly that one-sidedness: we take a peak across
the passage, the paper reports a single analysis, so we cannot read low. Our
own sliding study (§B.3) reads 24.6% above a single-position solve of the
same case, which is the same effect measured directly.

**The R-trend divergence is absent here**, as it was in v1.0: these deltas
do not flip sign across the radii the way plain pipe's +16.8 / +6.1 / −7.7%
does. §B.1's `run_slay` column does flip, and the difference between the two
is the spacing — 8 m against the paper's 9 m. So the "+19 to +26% at R = 70"
this repo carried for GD-TP was partly a spacing mismatch, not toolchain
divergence.

**The contact surface moved every value by −0.6% to −1.9%**, consistently
down and much more uniformly than on plain pipe. Unlike plain pipe the peak
does not jump between elements here — it is pinned to the pipe-to-component
junction, a fixed material feature — so the R_eff change comes through
almost cleanly. Plain pipe's scatter and this column's consistency are the
same effect seen with and without a feature to pin the peak to.

### B.3 Sliding — what Series 3 cannot show

Series 3's figures are single-position. The rebuild's own sliding study at
R = 85 / 9 m / 120 MT, 'centreline' (**not re-run on the new default**):

| Step | Positions | Envelope with edge crossings |
|---|---|---|
| 2.0 element | 5 | **0.5731%** |
| 1.0 element | 7 | 0.5727% |
| 0.5 element | 11 | 0.5722% |
| 0.25 element | 18 | 0.5689% |

Converged to **0.7% spread**, every run placing the envelope at the travel
where the component's leading edge sits exactly on SR2. **A single-position
solve at the start reads 0.4597% — 24.6% below the envelope.** Series 3's
numbers are single-position, so the paper's own figures are a lower bound on
the case it describes.

### B.4 Series 3 Studies 2 and 3 — NOT RUN

| Study | Case | Paper 1 | ours |
|---|---|---|---|
| 2, length (TABLE XXIII) | R=70, L=2.5 D | 0.780% | — |
| | R=70, L=10 D | 1.499% | — |
| | R=70, L=20 D | 2.514% | — |
| | R=85, L=10 D | 1.104% | — |
| | R=85, L=20 D | 1.861% | — |
| | R=85, L=40 D | 1.914% | — |
| 3, spacing (TABLE XXVI) | two components, R=70 | see paper | — |

Study 2 is the most interesting unrun block in the file: peak strain
**saturates** between 20 D and 40 D (1.861 → 1.914%) as the component grows
long enough to span two rollers. That is a behaviour change rather than a
number, and the same class of thing as §C.1's X3/X4 collapse.

---

## C. Paper 1, Series 4 — shroud GD-SH

*R = 85 m / R = 70 m, 9 m spacing. Peak at region X2 (deep section,
catenary-side third) in every case the paper ran.*

The `ILS-SH` archetype is **exactly** the paper's R = 85 / V = 1.0 D entry:
V = 0.4064 m (1.0 D), L1 = 4.064 m (10 D), L2 = 1.016 m (2.5 D), published
X2 = **0.70%** — a dimensionally-matched comparison.

### C.0 Three regions, against TABLE XXXIV

*V = 1.0 D, R = 85, 100 MT, L1 = 10 D, L2 = 2.5 D.*

| region | Paper 1 | 2 × OD | 1 × OD | 0.5 × OD | v1.0 at 0.5 × OD |
|---|---|---|---|---|---|
| **X2** catenary third | 0.70% | 0.5976% (−14.6%) | 0.6668% (−4.7%) | 0.7271% (**+3.9%**) | 0.7164% (+2.3%) |
| **X3** midspan third | 0.55% | 0.5170% (−6.0%) | 0.5513% (**+0.2%**) | 0.5381% (−2.2%) | 0.5491% (−0.2%) |
| **X4** vessel third | 0.43% | 0.4586% (+6.7%) | 0.4778% (+11.1%) | 0.5092% (+18.4%) | 0.5117% (+19.0%) |

**Refinement carries X2 through the published value**, −14.6% → −4.7% →
+3.9%, crossing 0.70% between 1 × OD and 0.5 × OD — the same bracketing v1.0
found, displaced down by the contact surface. **X3 agrees to 0.2% at
1 × OD.** X4 stays 7–18% high and drifts *up* with refinement, which is the
opposite of converging: X4 is the region Paper 1 says **plateaus** beyond
V ≈ 1.5 D, and a plateau is a behaviour a coarsely-resolved region cannot
reproduce.

**At the ruled 2 × OD density X2 holds ONE element** in this configuration.
A single-element region does not have a strain field; it has a number. Every
2 × OD figure in §C.1 carries that caveat and the element count is given
with it.

**The X3/X2 "band", settled from the source.** The repo twice compared
X3/X2 against the paper's **prose generalisation** — TABLE XXIX says
"typically 65–75%", the text above TABLE XXXIV says "approximately 65–70%" —
and recorded first agreement then disagreement with it. The paper's own
tabulated value for the case we match dimensionally is **79%**, and its six
cases run 68 / 79 / 79 / 73 / 71 / 67%, so the generalisation does not
contain its own V = 1.0 D entry. *Compare case against case, never case
against the prose summarising a spread of cases.*

### C.1 The whole V sweep — all 12 published cases, TABLE XXXI

*9 m spacing, 2 × OD mesh (the paper's own density).*

*Element count in X2 is given because it is decisive: where it is 1, the
"region peak" is one element's strain and not a field.*

| Config | V | X2 | Paper 1 | delta | X1 | X3 | X4 | n(X2) | v1.0 X2 |
|---|---|---|---|---|---|---|---|---|---|
| R=85, T=100 MT | 0.75 D | 0.5241% | 0.62% | −15.5% | 0.5493% | 0.4775% | 0.4445% | 1 | 0.5347% |
| L1=10D, L2=2.5D | 1.00 D | 0.5976% | 0.70% | −14.6% | 0.6527% | 0.5170% | 0.4586% | 1 | 0.6318% |
| | 1.50 D | 0.7336% | 0.95% | −22.8% | 0.8226% | 0.5914% | 0.5068% | 1 | 0.7917% |
| | 2.00 D | 0.8824% | 1.20% | −26.5% | 1.0002% | 0.6669% | 0.5562% | 1 | 0.9636% |
| | 2.50 D | 1.0034% | 1.51% | −33.6% | 1.1833% | 0.4538% | 0.2451% | 1 | 1.1421% |
| | 3.00 D | 1.1577% | 1.80% | −35.7% | 1.3672% | 0.4840% | 0.2501% | 1 | 1.3163% |
| R=70, T=120 MT | 1.00 D | 0.8481% | 0.808% | **+5.0%** | 0.8663% | — | 0.6800% | 1 | 0.8466% |
| L1=5D, L2=2.5D | 1.50 D | 0.9672% | 0.970% | **−0.3%** | 1.0641% | — | 0.7375% | 1 | 1.0015% |
| | 2.00 D | 1.1415% | 1.15% | **−0.7%** | 1.2211% | — | 0.5958% | 1 | 0.8592% |
| R=70, T=100 MT | 1.00 D | 0.4569% | 0.76% | −39.9% | 0.7482% | 0.2470% | 0.2151% | 2 | 0.7399% |
| L1=10D, L2=5D | 1.50 D | 0.8190% | 1.03% | −20.5% | 0.8781% | 0.3252% | 0.2525% | 2 | 0.6704% |
| | 2.00 D | 0.3276% | 1.23% | −73.4% | 0.8694% | 0.2190% | 0.1949% | 2 | 0.3276% |

**Reproduced: X2 rises monotonically with V** in every configuration. Offset
depth is the dominant parameter, which is Series 4's whole finding.

**X1 now exceeds X2 in all 12 cases**, where in v1.0 it did so in 6. So at
the ruled mesh our peak is on the **taper**, not the deep section, and Paper
1 says X2 governs in every case it ran.

**But that finding does not survive refinement, and §C.0 is the evidence.**
At the dimensionally-matched case, X2 overtakes X1 at 1 × OD and stays ahead
at 0.5 × OD. **X2 holds ONE element at 2 × OD in nine of these twelve
cases** — so "X1 > X2" is substantially a statement about the mesh. Reported
as measured, with the element count beside it, because the paper's own mesh
is 2 × OD and this is what that mesh gives.

**Three regions hold no elements at all** and are shown as `—`, not 0.0%.
The R = 70 / T = 120 MT configuration has L1 = 5 D, so each third is 0.677 m
against an 0.813 m element and X3 contains no element midpoint. v1.0 printed
those as `0.0000%`; that was a reporting defect and is fixed (L097).

**The agreement pattern is now the opposite of v1.0's** and it is the most
interesting thing in this re-run. The R = 85 series, which v1.0 had at −9.7%
to −26.9%, is now −14.6% to −35.6% — worse, and still fanning out with
depth. But the R = 70 / T = 120 MT series lands at **+5.0 / −0.3 / −0.7%**,
which is the closest agreement with Paper 1 anywhere in this file. Those
three cases have the shortest deep section (L1 = 5 D) and the highest tension
(120 MT). Whether that is physics or the compensation of two coarse-mesh
errors is **not established**, and the one-element X2 is reason for caution.

*The under-amplification with depth persists.* At R = 85 our X2 still rises
more slowly than the paper's: the delta grows monotonically from −15.5% at
0.75 D to −35.7% at 3.0 D. That was v1.0's clearest structural disagreement
and the contact surface did not touch it.

*And X3/X4 still collapse past a depth threshold* — X3 0.5914 → 0.4538% and
X4 0.5068 → 0.2451% between V = 1.5 D and 2.5 D at R = 85, where the paper
has X3 rising and X4 plateauing. The lift-off hypothesis from v1.0 stands
unverified: beyond a threshold depth the deep section may lift clear of the
rollers, so the midspan and vessel thirds unload while the catenary edge
takes everything. The station contact states are in the profile artifacts.

*Caveat on all 12.* The paper marks every Series 4 case **Ph2**. Our
envelope lands at step 4–6 of the passage. Whether those are the same
mechanical state is open and sits under this whole section.

### C.2 Series 4's L1 and L2 studies — NOT RUN

TABLE XXXII (deep-section length, two regimes — negligible effect from
2.5 D to 10 D at V = 1 D, then a dramatic reduction at L1 ≥ 25 D as the
shroud shifts from single- to double-roller contact) and TABLE XXXIII
(taper length, less than 4% effect). The L1 ≥ 25 D regime change is the
same double-roller mechanism as §B.4's length saturation.

---

## D. Paper 1, Series 5 — GD-TP + GD-SH combined

| Case | Thick pipe | Paper 1 X2 | vs baseline | Peak location | ours |
|---|---|---|---|---|---|
| B1 ref | shroud only | 0.70% | — | — | §C.0 |
| 1 | 5 D | 0.952% | +36.0% | pipeline body at X2 | — |
| 2 | 10 D | 1.26% | +80.0% | pipe-to-component junction at X2 | — |

`ILS-SHTP` builds, meshes and solves, but **gets junction reporting and no
region columns**, so it produces no X2 and cannot be compared. The blocker
is reporting, not physics.

---

## E. Paper 2 — external attached structures, F1 and F2

*R = 85 m, 9 m spacing, 120 MT. `tools/study_f2.py` (EA-ST) and
`tools/study_easb_cases.py` (EA-SB). Dimensions are the paper's own.
Regions are Fig. 38's:*

* **X_c** — within 2 × pipe OD either side of a connector. The peak.
* **X_i** — the interior, between two connectors. F1 has one connector and
  therefore no interior, and the paper tabulates none for it.
* **X_e** — outboard, from X_c out to the far field.

| Case | X_c | P2 | Δ | X_i | P2 | Δ | X_e | P2 | Δ | v1.0 X_c |
|---|---|---|---|---|---|---|---|---|---|---|
| EA-ST F2 Case 1 | 0.904% | 0.936% | **−3.5%** | 0.075% | 0.043% | +75.0% | 0.533% | 0.732% | −27.2% | 0.923% |
| EA-ST F2 Case 2 | 1.601% | 1.410% | +13.6% | 0.124% | 0.075% | +65.2% | 0.683% | 1.021% | −33.1% | 1.615% |
| EA-SB F1 Case 1 | 0.941% | 2.30% | −59.1% | — | — | — | 1.118% | 1.41% | −20.7% | 0.950% |
| EA-SB F2 Case 1 | 1.291% | 2.24% | −42.3% | 0.137% | 0.086% | +59.1% | 1.270% | 1.45% | −12.4% | 1.261% |
| EA-SB F2 Case 2 | 2.170% | 2.40% | **−9.6%** | 0.122% | 0.086% | +42.1% | 0.854% | 1.52% | −43.8% | 2.238% |
| EA-SB F2 Case 3 | 1.509% | 2.53% | −40.4% | 0.127% | 0.085% | +49.4% | 1.394% | 1.60% | −12.9% | 1.473% |

*All six converge over the full passage — EA-ST 19/19 positions, EA-SB full.*

**The contact surface barely moved these at all**: X_c changes by −2.1% to
+2.4% against v1.0, and every qualitative conclusion is unchanged. That is
worth stating plainly, because it means the EA disagreements are **not** an
artefact of the contact surface and the re-run has eliminated one candidate
explanation rather than fixing anything.

**Reproduced: the ordering X_c > X_e ≫ X_i, in all six cases.** That is
Paper 2's actual finding and the reason the region scheme exists — a frame
bolted on at points concentrates strain at its fastenings, leaves the pipe
between them almost unstrained, and the pipe outboard reads the plain
overbend.

**Not reproduced: the magnitudes, and this stays open.**

* **EA-ST** agrees on X_c to −3.5% and +13.6%. Case 2 reading high is
  consistent with the envelope offset.
* **EA-SB** reads **low** on X_c, −9.6% to −59.1%. An envelope cannot be
  below a single position of the same case, so the envelope offset is
  *eliminated* as the explanation rather than left as a possibility. The
  disagreement is real. X_c is also the quantity most sensitive to connector
  placement, which is the thread to pull next.
* **X_i** is high by 42–75% everywhere. It is an order of magnitude below
  X_c so it moves no design conclusion, but the sign is consistent across
  all five cases that have an X_i, which says one cause and not five.
* **X_e** is low by 12–44%. **Parked by instruction** — not an oversight.

**X_e is parked by instruction** — not an oversight. Its boundary follows
Paper 2's *figures*, not its prose: the text says "pipeline outside the
structures" while Figs 27 and 38 draw X_e running up to where X_c begins.
Implementing the prose moved X_e from −10% to −45%.

### E.1 The D layouts — F1D / F2D, NOT RUN

Blocked by **G9**, deliberately. A `D` connector is a deadband and needs an
*active set* as well as a co-rotating frame; with the frame alone it would
behave as an always-shut `S` — a different joint, silently answering a
different question. The solver refuses it rather than approximating it.

### E.2 PS connections — PREDICTION, not validation

**Paper 2 publishes F1 and F2 only, so there is no reference value for any
of these and no delta can be computed.** Recorded so the ledger is not
mistaken for complete.

| Archetype | System | X_c | X_i | X_e | Positions | v1.0 positions |
|---|---|---|---|---|---|---|
| ILS-EAST | F2 | 0.601% | 0.062% | 0.478% | 24/24 | 24/24 |
| ILS-EAST | **PS** | 0.357% | 0.355% | 0.419% | 24/24 | 24/24 |
| ILS-EASB | F2 | **0.328%** ⚠ | **0.086%** ⚠ | **1.599%** ⚠ | **7/8** | 30/30 |
| ILS-EASB | **PS** | **0.311%** ⚠ | **0.208%** ⚠ | **1.551%** ⚠ | **7/8** | 9/10 |

**EA-ST is a clean re-measurement**: 24/24 both times, and every value within
1% of v1.0 (F2 0.607 / 0.062 / 0.483 → 0.601 / 0.062 / 0.478; PS 0.360 /
0.358 / 0.420 → 0.357 / 0.355 / 0.419). PS still relieves the connector and
removes the shielding — X_c falls 41%, and X_i rises from an order of
magnitude below X_c to **equal** it, because with the slot free to slide the
frame can no longer hold the pipe it spans. Unchanged by the contact surface.

> ### ⚠ EA-SB does not survive the contact surface change
>
> **`ILS-EASB` ran 30/30 positions on 'centreline' and truncates at position
> 7 on 'bottom'**, failing with `CUTBACK EXHAUSTED at lam=0.0000` at
> shift 2.032 m of a 10.128 m travel. It covers **20% of the passage**, so
> its three region values are lower bounds over a fifth of the travel and
> are **not comparable to v1.0's**, which covered all of it. Marked ⚠ for
> that reason, not because the solver reported anything wrong about the seven
> positions it did solve.
>
> This is the one place the surface change costs capability rather than
> accuracy, and it is the most severe geometry in the repo: `ILS-EASB` ships
> `P_v = 1.6256 m`, **4 D**, a 3.5 D lift. Both connection systems truncate
> at the same position, which says the cause is the structure's geometry and
> not the joint.
>
> **Not diagnosed.** The candidate worth trying first is the staged seeding
> that rescued the R = 60/70 corner (shape before loads), since this fails at
> the first increment of a position the previous one reached comfortably.

**These are the archetypes at their SHIPPED dimensions, not the paper's case
dimensions**, which is why the F2 rows here do not match §E's. The F2 column
is present only as the control the PS column is read against. For `ILS-EASB`
the difference is severe: 4 D of offset against every published case's 2 D.
**No row of this table may be read against a published value.**

**These are the archetypes at their SHIPPED dimensions, not the paper's case
dimensions**, which is why the F2 rows here will not match the F2 rows in
§E. The F2 column is present only as the control the PS column is read
against. For `ILS-EASB` the difference is severe: it ships `P_v = 1.6256 m`,
**4 D** and a 3.5 D lift, where every published case is 2 D and a 1.5 D
lift. **No row of this table may be read against a published value.**

v1.0's finding: PS relieves the connector and removes the shielding, which
is what a pin and a roller should do — X_c fell 41% on EA-ST and 59% on
EA-SB, and X_i rose to **equal** X_c on EA-ST.

---

## F. Scorecard

*Filled as the re-runs land.*

| Comparison | Status |
|---|---|
| Rebuild vs `run_slay`, plain pipe, 3 radii | **Within 1.7%** — unaffected by v2.0 |
| Rebuild vs Paper 1, plain pipe, 3 radii | +16.8 / +6.1 / −7.7% |
| Rebuild vs Paper 1, plain pipe TABLE XI | **0 of 6** — never run |
| `run_slay` vs Paper 1, GD-TP, 9 values | Within 6% at R = 85/100; +19–26% at R = 70, partly an 8 m vs 9 m mismatch |
| Rebuild vs Paper 1, GD-TP Study 1 | **9 of 9**, +1.8% to +17.0%, all high |
| Rebuild vs Paper 1, GD-TP Studies 2–3 | **0 of 7** — never run |
| Rebuild vs Paper 1, GD-SH V sweep | **12 of 12**, −73.4% to +5.0%; X2 monotonic in V as published, X1 governs at the ruled mesh |
| Rebuild vs Paper 1, GD-SH L1/L2 studies | **0** — never run |
| Rebuild vs Paper 1, Series 5 | **0 of 2** — no region columns for `ILS-SHTP` |
| Rebuild vs Paper 2, EA F1/F2 | **6 of 6**, ordering reproduced in all; X_c −59.1% to +13.6% |
| Rebuild vs Paper 2, EA F1D/F2D | Refused under G9 |
| PS layouts | Prediction only; Paper 2 publishes no PS case. EA-ST clean at 24/24; **EA-SB truncates at 20% of its travel on the new contact surface** |

## G. Gaps

1. **Paper 2 has no citation in this repo.** Its case tables and region
   definitions were transcribed from supplied figures, so every number in
   §E is checked against a transcription, not a source — which matters most
   for the EA-SB rows 40–60% out, where a transcription error would read
   exactly like a physics disagreement.
2. **Always state R, tension, spacing, mesh AND contact surface.** The rule
   was R-and-tension-and-spacing until 6 Oct, and an unlabelled 120 MT run
   was read against a 100 MT target, reversing a recorded conclusion. The
   contact surface is now a fifth thing a number is meaningless without,
   and this file's whole v1.0→v2.0 transition is the demonstration.
3. **Large blocks never run:** Paper 1 TABLE XI (6 values, and the only ones
   with an independent analytical check), Series 3 Studies 2 and 3 (7),
   Series 4's L1/L2 studies, Series 5 (2).
4. **We report extreme-fibre strain per element; the papers report "nominal
   strains at element integration points."** Expected to coincide for a B31
   beam in pure bending, **never checked against the kernel**. A systematic
   offset candidate under *every* row of this file.
5. **The deep-section lift-off hypothesis (§C.1) is unverified** and would
   account for three separate disagreements at once. The station contact
   states are already in the profile artifacts, so the check is cheap.
6. **Whether our envelope and the paper's "Ph2" are the same mechanical
   state** is unsettled, and sits under every Series 4 and Series 5 row.
7. **§B.3's sliding study has not been re-run** on the new default.
8. **`ILS-EASB` truncates at 20% of its passage on the default contact
   surface** (§E.2), where it ran the full travel on 'centreline'. The only
   capability regression from that change, undiagnosed, and it affects the
   most severe geometry in the repo.

---

## Version history

| Version | Date | What |
|---|---|---|
| **2.0** | 6 Oct 2026 | Re-measured on `contact_surface='bottom'`, the physical surface, after L095 and L096. Paper 1 read in full and its transcriptions verified |
| 1.0 | 6 Oct 2026 | First consolidated ledger. All rebuild results on `'centreline'`. `VALIDATION_v1.0_2026-10-06.md`, superseded but kept unedited |

## Where each row came from

| Table | Working record |
|---|---|
| §A | `RESULTS.md` §1.1, `T5_solve_spec.md` §5e, `TRIAL_LOG` T039 |
| §B | `RESULTS.md` §3, §5.2; `T9_components_spec.md` §6b, §6c; `TRIAL_LOG` T037 |
| §C | `T9_components_spec.md` §4; `T9_physics_sequence.md`; `TRIAL_LOG` T036, T038 |
| §D | `T9_components_spec.md` §5 |
| §E | `T9_physics_sequence.md`; `tools/study_f2.py`, `tools/study_easb_cases.py` |

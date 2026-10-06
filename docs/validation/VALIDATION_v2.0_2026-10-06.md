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

| Case | t | R | rebuild | Paper 1 | delta | v1.0 ('centreline') |
|---|---|---|---|---|---|---|
| A1 | 32 mm | 70 m | *pending* | 0.562% | | 0.6421% (+14.3%) |
| A1 | | 85 m | *pending* | 0.473% | | 0.4875% (+3.1%) |
| A1 | | 100 m | *pending* | 0.339% | | 0.3815% (+12.5%) |
| A2 | 42 mm | 70 m | *pending* | 0.647% | | 0.7132% (+10.2%) |
| A2 | | 85 m | *pending* | 0.508% | | 0.5546% (+9.2%) |
| A2 | | 100 m | *pending* | 0.358% | | 0.4214% (+17.7%) |
| A3 | 53 mm | 70 m | *pending* | 0.727% | | 0.7857% (+8.1%) |
| A3 | | 85 m | *pending* | 0.556% | | 0.6237% (+12.2%) |
| A3 | | 100 m | *pending* | 0.425% | | 0.4519% (+6.3%) |

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

| region | Paper 1 | ours, 2 × OD | ours, 1 × OD | ours, 0.5 × OD | v1.0 at 0.5 × OD |
|---|---|---|---|---|---|
| **X2** catenary third | 0.70% | *pending* | *pending* | *pending* | 0.7164% (+2.3%) |
| **X3** midspan third | 0.55% | *pending* | *pending* | *pending* | 0.5491% (−0.2%) |
| **X4** vessel third | 0.43% | *pending* | *pending* | *pending* | 0.5117% (+19.0%) |

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

| Config | V | ours X2 | Paper 1 | delta | peak region | v1.0 X2 |
|---|---|---|---|---|---|---|
| R=85, T=100 MT | 0.75 D | *pending* | 0.62% | | | 0.5347% |
| L1=10D, L2=2.5D | 1.00 D | *pending* | 0.70% | | | 0.6318% |
| | 1.50 D | *pending* | 0.95% | | | 0.7917% |
| | 2.00 D | *pending* | 1.20% | | | 0.9636% |
| | 2.50 D | *pending* | 1.51% | | | 1.1421% |
| | 3.00 D | *pending* | 1.80% | | | 1.3163% |
| R=70, T=120 MT | 1.00 D | *pending* | 0.808% | | | 0.8466% |
| L1=5D, L2=2.5D | 1.50 D | *pending* | 0.970% | | | 1.0015% |
| | 2.00 D | *pending* | 1.15% | | | 0.8592% |
| R=70, T=100 MT | 1.00 D | *pending* | 0.76% | | | 0.7399% |
| L1=10D, L2=5D | 1.50 D | *pending* | 1.03% | | | 0.6704% |
| | 2.00 D | *pending* | 1.23% | | | 0.7510% |

**What v1.0 found, to be confirmed or overturned by the re-run.** X2 rose
monotonically with V and X2 governed at R = 85 — Series 4's actual finding.
Against that, three structural disagreements: we under-amplified with depth
(our slope constant at 0.35% per diameter, the paper's rising 0.32 → 0.62);
at R = 70 the peak sat on the **taper** (X1) rather than the deep section;
and X3/X4 **collapsed** past V ≈ 1.5–2.0 D where the paper has X3 rising and
X4 plateauing. One hypothesis covers all three — beyond a threshold depth
the deep section lifts clear of the rollers, so the midspan and vessel
thirds unload while the catenary edge takes everything — and it is
**unverified**. The station contact states are in the profile artifacts.

*Caveat on all 12.* The paper marks every Series 4 case **Ph2**. Our
envelope lands at step 3–5 of the passage. Whether those are the same
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

| Case | X_c ours | X_c P2 | X_i ours | X_i P2 | X_e ours | X_e P2 |
|---|---|---|---|---|---|---|
| EA-ST F2 Case 1 | *pending* | 0.936% | *pending* | 0.043% | *pending* | 0.732% |
| EA-ST F2 Case 2 | *pending* | 1.410% | *pending* | 0.075% | *pending* | 1.021% |
| EA-SB F1 Case 1 | *pending* | 2.30% | — | — | *pending* | 1.41% |
| EA-SB F2 Case 1 | *pending* | 2.24% | *pending* | 0.086% | *pending* | 1.45% |
| EA-SB F2 Case 2 | *pending* | 2.40% | *pending* | 0.086% | *pending* | 1.52% |
| EA-SB F2 Case 3 | *pending* | 2.53% | *pending* | 0.085% | *pending* | 1.60% |

v1.0's X_c, for comparison once the re-run lands: 0.923 / 1.615 / 0.950 /
1.261 / 2.238 / 1.473%, i.e. −1.4 / +14.5 / −58.7 / −43.7 / −6.8 / −41.8%.

**What v1.0 established, and what it did not.** The ordering
X_c > X_e ≫ X_i was reproduced in all six cases — Paper 2's actual finding,
and the reason the region scheme exists. The magnitudes were not, and the
EA-SB disagreement is open: those read **low**, and an envelope cannot be
below a single position, so the envelope offset is *eliminated* as the
explanation rather than left as a possibility. X_c is the most sensitive
quantity to connector placement, which is the thread to pull.

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

| Archetype | System | X_c | X_i | X_e | Positions |
|---|---|---|---|---|---|
| ILS-EAST | F2 | *pending* | *pending* | *pending* | |
| ILS-EAST | **PS** | *pending* | *pending* | *pending* | |
| ILS-EASB | F2 | *pending* | *pending* | *pending* | |
| ILS-EASB | **PS** | *pending* | *pending* | *pending* | |

v1.0, for comparison: EA-ST F2 0.607 / 0.062 / 0.483 and PS 0.360 / 0.358 /
0.420; EA-SB F2 1.185 / 0.142 / 2.082 and PS 0.481 / 0.243 / 1.986, the last
truncating at 9/10 positions so that envelope is a lower bound.

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
| Rebuild vs Paper 1, GD-TP Study 1 | 9 of 9 — *re-running* |
| Rebuild vs Paper 1, GD-TP Studies 2–3 | **0 of 7** — never run |
| Rebuild vs Paper 1, GD-SH V sweep | 12 of 12 — *re-running* |
| Rebuild vs Paper 1, GD-SH L1/L2 studies | **0** — never run |
| Rebuild vs Paper 1, Series 5 | **0 of 2** — no region columns for `ILS-SHTP` |
| Rebuild vs Paper 2, EA F1/F2 | 6 cases — *re-running* |
| Rebuild vs Paper 2, EA F1D/F2D | Refused under G9 |
| PS layouts | Prediction only; Paper 2 publishes no PS case |

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

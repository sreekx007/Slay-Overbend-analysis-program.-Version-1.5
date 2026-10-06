# SLAY Overbend — Validation ledger

**Every published case we have a number for, in one table.**

This file exists because the answer to "how do we compare against the
papers?" was spread across four documents and two tools that printed to
stdout and persisted nothing. Each of those is still the *working* record
for its own study; this is the **consolidated comparison**, and the one
place to look first.

One row per published case. Each row says which program produced our
number, because that is not uniform — some cases the rebuild has run, some
only the original toolchain has, and some neither.

*Created 6 Oct 2026. Branch `claude/program-rebuild-status-bya72s`, commit
`2816b8b`. 634 tests passing, layer linter clean at 36 modules.*

---

## The two sources

| | What it covers | Citation |
|---|---|---|
| **Paper 1** | Plain pipe (Study 1 / TABLE X, XI), thick pipe GD-TP (Series 3 / TABLE XIX–XXVI), shroud GD-SH (Series 4 / TABLE XXVIII–XXXIV), the two combined (Series 5 / TABLE XXXVIII–XXXIX) | Sivaraman & Reddy, *Toward AI-Assisted Conceptual Design of Subsea Inline Structures*, IJRASET Vol. 14 Issue VII, July 2026, pp. 1127–…, doi 10.22214/ijraset.2026.84268. Benchmark is an **Abaqus** B31 beam model. **Read in full 6 Oct 2026** — 52 pp |
| **Paper 2** | External attached structures — EA-ST (stand-off) and EA-SB (sledge base) on F1 and F2 connections, and the X_c / X_i / X_e reporting scheme (its Figs 27 and 38) | **Not recorded in this repo.** Supplied as figures only; the case tables and region definitions were transcribed from them. See *Gaps* below |

**Paper 1 is the source of every TABLE-numbered target in
`T9_components_spec.md`; Paper 2 is the source of every EA case.** Before
this file the repo called both "the reference" and distinguished them
nowhere, which is the first thing the ledger fixes.

### Paper 1's transcriptions are now verified against the source

The PDF was supplied and read on 6 Oct. **Every target value transcribed
into this repo checks out** — TABLE X (0.46 / 0.38 / 0.32), TABLE XX (the
nine GD-TP values), TABLE XXXI (the twelve shroud X2 values) and TABLE
XXXIX (0.70 / 0.952 / 1.26) are all exactly as recorded. Three things the
transcriptions had wrong or missing, all configuration rather than results:

1. **Roller spacing is 9 m c/c throughout the paper**, stated once in the
   model description ("Rollers are spaced out at length of 9m c/c") and
   never repeated per study. Our GD-TP comparison in §B.1 was run at **8 m**
   — a configuration mismatch, not a like-for-like delta. Flagged in §B.
2. **Every Series 4 and Series 5 case is governed by Phase 2**, not Phase 1.
   Phase 1 is plastic bending over the first two rollers from a straight,
   stress-free pipe; Phase 2 is the elastic bend-unload cycle over the
   mid-stinger rollers, *offset by the residual plastic curvature Phase 1
   left behind*. Plain pipe and Series 3 are Phase 1. This is a real
   difference in what is being reported and is discussed in §C.
3. **TABLE XXXIV exists and we did not have it.** It gives X3 and X4
   absolutes for all six offset depths, so the shroud comparison is three
   regions wide rather than one. See §C.

### A third comparison that is not a paper

`run_slay` — the **original validated Python toolchain** in this repo. For
the rebuild it is a *stronger* target than either paper, because it can be
run here on demand at exactly our configuration, and a disagreement with it
is unambiguously our defect. Rows that compare rebuild against `run_slay`
are marked **like-for-like**; rows against a paper are not, and carry the
reasons under each table.

### How to read a delta

A paper delta is **not** an error bar. Three known offsets sit between us
and Paper 1, all documented, none of them bugs:

* **The R-trend divergence.** Abaqus amplification rises with stinger
  radius and the Python toolchain's falls; they cross near R = 80 m. So a
  delta at R = 70 is expected to be high and at R = 105 low, and the sign
  flip across the table is the *signature*, not noise. Reproduced
  independently on plain pipe and on a component case, which is the
  evidence it is a property of the toolchain rather than of one
  configuration (`T5_solve_spec.md` §4, `T9_components_spec.md` §6b).
* **Mesh.** At the ruled 2 × OD density (G10) the answer is not converged
  for any component case, and refinement moves it *up* by 10–16%.
  Agreement at 2 × OD partly reflects both sides being under-resolved.
  Every component row therefore states its mesh.
* **Envelope vs single position.** We report a peak across the whole
  passage; the papers report a single analysis. An envelope cannot be
  *below* a single position of the same case, so this offset only ever
  explains us reading **high** — which is why it is eliminated as the
  explanation for the EA-SB rows, where we read low.

---

## A. Paper 1, Study 1 — plain pipe

406.4 × 21 mm (16" × 21 mm seamless), 120 MT, J2 plasticity
(`material('j2')`). The case M1 gates on.

**The steel is DNV Grade 450**, API 5L X65-equivalent, named in
`nlfea_v4.py`: SMYS 450 MPa, certificate value 448 MPa, E = 207 GPa,
Ramberg-Osgood n = 20.59. We carry it in two forms — `material('ro')` at
E = 207 GPa / σ_ys = 450 MPa / n = 20.59 / α_dnv = 1.300, and
`material('j2')` as an incremental table from **360 to 530 MPa** over 0 to
5.26% plastic strain at E = 210 GPa.

*The J2 table's 360 MPa is **not** a grade SMYS and must not be read as one.*
It is where this steel's round-house curve leaves the elastic line —
exactly 0.800 × 450 MPa — and it is pinned to the project's own Abaqus
benchmark BM_Test_B (360 MPa first yield, not the 385 MPa of a
similarly-shaped table that exists elsewhere). Both forms are the same
450 MPa steel; a reader seeing 360 MPa and inferring a lower grade would be
making the mistake this paragraph exists to stop.

### A.1 Rebuild against `run_slay` — like-for-like, J2 against J2

*8 m spacing (the reference program's own), staged four-step sequence,
`tools/stage_run.py`. Peak in the SR2–SR3 span on both sides.*

| R | rebuild | `run_slay` | delta |
|---|---|---|---|
| 70 m | 0.5179% | 0.5271% | **−1.7%** |
| 85 m | 0.3884% | 0.3937% | **−1.3%** |
| 105 m | 0.2879% | 0.2903% | **−0.8%** |

**The rebuild reproduces the original toolchain within 1.7% at every
radius, with the peak in the same span.** This is the strongest validation
result in the repo. The single proportional solve of the same case is +15
to +21% with the peak displaced to SR6 — the staging is what buys the
agreement, not an incidental choice (L053).

### A.2 Rebuild against Paper 1 — the paper's own configuration

*9 m spacing, 120 MT, as TABLE X states.*

| R | rebuild | Paper 1 (Abaqus) | delta |
|---|---|---|---|
| 70 m | 0.5423% | 0.46% | **+17.9%** |
| 85 m | 0.4014% | 0.38% | **+5.6%** |
| 105 m | 0.2942% | 0.32% | **−8.1%** |

Monotonic high-to-low across the radii — the R-trend divergence, crossing
between 85 and 105 m. Agreement is best at R = 85, which is where the two
curves cross.

---

## B. Paper 1, Series 3 — thick pipe GD-TP

*100 MT, 1000 mm component, 8 m spacing, shift 0. Constant bore,
`OD_comp = ID + 2t` — the paper's own convention (confirmed to match: our
53 mm case computes OD 470.4 mm and I/Ip = 3.248 against the paper's stated
471 mm and ~3.2×). Peak at the pipe-to-component junction at SR2.*

### B.1 `run_slay` against Paper 1 — ORIGINAL program

| Case | t | OD_comp | R = 70 | R = 85 | R = 100 |
|---|---|---|---|---|---|
| A1 | 32 mm | 428.4 mm | 0.7086% | 0.4876% | 0.3478% |
| A2 | 42 mm | 448.4 mm | 0.7877% | 0.5308% | 0.3782% |
| A3 | 53 mm | 470.4 mm | 0.8650% | 0.5715% | 0.4074% |
| | | **Paper 1** | 0.562 / 0.647 / 0.727% | 0.473 / 0.508 / 0.556% | 0.339 / 0.358 / 0.425% |
| | | **delta A1** | +26.1% | +3.1% | +2.6% |
| | | **delta A2** | +21.7% | +4.5% | +5.6% |
| | | **delta A3** | +19.0% | +2.8% | **−4.1%** |

Within 6% at R = 85 and R = 100; +19 to +26% at R = 70. Same R-trend
divergence as §A.2, now in a component case.

### B.2 Rebuild against Series 3 — **NOT RUN at the paper's configuration**

The rebuild has run GD-TP, but at R = 85 / 9 m / 120 MT — not Series 3's
100 MT / 8 m — so **no row of §B.1 has a rebuild number beside it.** What
the rebuild has measured on GD-TP is the *sliding* behaviour Series 3 cannot
show, and it is the more important finding:

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

**Closing B.2 is the single highest-value validation run outstanding** — it
would put a rebuild column against nine published values.

---

## C. Paper 1, Series 4 — shroud GD-SH

*R = 85 m, T = 100 MT, 9 m spacing. Peak at region X2 (deep section,
catenary-side third) in every case the paper ran, which we reproduce.*

The `ILS-SH` archetype is **exactly** the paper's second R = 85 entry:
V = 0.4064 m (1.0 D), L1 = 4.064 m (10 D), L2 = 1.016 m (2.5 D), published
X2 = **0.70%**. That is a direct, dimensionally-matched comparison and it
had never been made.

| Mesh | our X2 | Paper 1 | delta | X3/X2 | X4/X2 | elements in X2 |
|---|---|---|---|---|---|---|
| 2 × OD (ruled, G10) | 0.6318% | 0.70% | **−9.7%** | 0.800 | 0.720 | 2 |
| 1 × OD | 0.6625% | 0.70% | **−5.4%** | 0.770 | 0.733 | 4 |
| 0.5 × OD | 0.7164% | 0.70% | **+2.3%** | 0.767 | 0.714 | 7 |

*Measured 6 Oct 2026, `tools/emit_profile.py --archetype ILS-SH --R 85
--spacing 9 --tension 100 [--mesh …]`.*

**Refinement carries X2 through the published value**, −9.7% → −5.4% →
+2.3%, crossing 0.70% between 1 × OD and 0.5 × OD. For the one Series 4
case we can compare dimensionally, our converging trend **brackets** the
paper's number instead of running away from it — which is not what the
thick-body case does, where refinement moves ~16% away from both the paper
and the original toolchain.

Note that from 1 × OD the X2 peak is no longer the *model* peak: X1 reads
0.6754% (1.019 × X2) at 1 × OD and 0.7380% (1.030 ×) at 0.5 × OD, because
the peak moves onto the catenary-side **taper**, 0.395 m outboard of the
deep section, where the lift gradient is steepest. Paper 1 calls X1
"governed by the plain-pipe catenary", which holds at 2 × OD and does not
hold refined — so the region scheme's own recorded caution reproduces at the
paper's tension as well, and each region peak carries whether it landed on
the shroud footprint so the two things X1 lumps together can be told apart.

### C.0 Three regions, against TABLE XXXIV

Reading Paper 1 in full produced a table we did not have: **TABLE XXXIV**
gives X3 and X4 absolutes for every offset depth at this exact
configuration, so the comparison is three regions wide. At our finest mesh:

| region | Paper 1 (TABLE XXXIV, V = 1.0 D) | ours, 0.5 × OD | delta |
|---|---|---|---|
| **X2** catenary third | 0.70% | 0.7164% | **+2.3%** |
| **X3** midspan third | 0.55% | 0.5491% | **−0.2%** |
| **X4** vessel third | 0.43% | 0.5117% | +19.0% |
| X3/X2 | 79% | 76.6% | −3.0% |
| X4/X2 | 61% | 71.4% | +16.4% |

**X2 and X3 agree to within 2.5%.** X4 is 19% high, and X4 is the region
the paper says *plateaus* beyond V ≈ 1.5 D — a plateau is exactly the
behaviour a one-element region cannot resolve, and X4 holds 1 element at
2 × OD and 6 at 0.5 × OD against X2's 7.

**The X3/X2 "band" question, settled from the source.** This has now moved
twice, so here is the whole of it. The repo recorded X3/X2 converging to
0.744 and called that "inside the reference's 65–75% band". Re-run at the
paper's own 100 MT it converges to 0.767, which I then recorded as *outside*
that band. Both readings were comparing against the paper's **prose
generalisation** — TABLE XXIX says "typically 65–75%" and the text above
TABLE XXXIV says "approximately 65–70%". The paper's own tabulated value
for the case we match dimensionally is **79%**, and its own six cases run
68 / 79 / 79 / 73 / 71 / 67%, so the generalisation does not even contain
its own V = 1.0 D entry. Against the case value our 76.6% is **−3.0%**.

*Compare case against case, never case against the prose summarising a
spread of cases* — the band was never the right target, and two successive
"corrections" against it were both beside the point.

**One real correction stands.** `T9_physics_sequence.md`'s mesh table
(X2 = 0.6868 / 0.7286 / 0.7951%) is at **120 MT**, not Series 4's 100 MT,
and carried no tension label. Those are not Series 4 numbers and must not
be read against 0.70%.

### C.1 The rest of Series 4 — NOT RUN

| Config | V | L1 | L2 | Paper 1 X2 | ours |
|---|---|---|---|---|---|
| R=70, T=120 MT | 1.0 / 1.5 / 2.0 D | 5 D | 2.5 D | 0.808 / 0.970 / 1.15% | — |
| R=70, T=100 MT | 1.0 / 1.5 / 2.0 D | 10 D | 5 D | 0.76 / 1.03 / 1.23% | — |
| R=85, T=100 MT | 0.75 D | 10 D | 2.5 D | 0.62% | — |
| R=85, T=100 MT | **1.0 D** | **10 D** | **2.5 D** | **0.70%** | **0.6318%** (§C) |
| R=85, T=100 MT | 1.5 / 2.0 / 2.5 / 3.0 D | 10 D | 2.5 D | 0.95 / 1.20 / 1.51 / 1.80% | — |

This is the **cheapest** outstanding validation in the ledger, and the V
series is the one that would show whether we track the paper's *trend* and
not just its one point. It is not quite free: `emit_profile.py` passes
EA-SB's dimensions through (`P_l1`, `P_l2`, `P_v`, `kB_ratio`) but **not the
shroud's `V`, `L1`, `L2`**, so three names have to join that passthrough
first. The mechanism is already there and already edits the archetype's own
definition rather than constructing geometry (G7) — it is a list to extend,
then a sweep.

---

## D. Paper 1, Series 5 — GD-TP + GD-SH combined

| Case | Thick pipe | Paper 1 X2 | vs baseline | Peak location | ours |
|---|---|---|---|---|---|
| B1 ref | shroud only | 0.70% | — | — | 0.6318% (§C) |
| 1 | 5 D | 0.952% | +36.0% | pipeline body at X2 | — |
| 2 | 10 D | 1.26% | +80.0% | pipe-to-component junction at X2 | — |

`ILS-SHTP` builds, meshes and solves, but **gets junction reporting and no
region columns**, so it produces no X2 and cannot be compared. The
blocker is reporting, not physics.

---

## E. Paper 2 — external attached structures, F1 and F2

*R = 85 m, 9 m spacing, 120 MT. Rebuild, `tools/study_f2.py` (EA-ST) and
`tools/study_easb_cases.py` (EA-SB). Dimensions are the paper's own, under
the names `component_spec` gives them. Regions are Fig. 38's:*

* **X_c** — within 2 × pipe OD either side of a connector. The peak.
* **X_i** — the interior, between two connectors. F1 has one connector and
  therefore no interior, and the paper tabulates none for it.
* **X_e** — outboard, from X_c out to the far field.

| Case | X_c ours | X_c P2 | Δ | X_i ours | X_i P2 | Δ | X_e ours | X_e P2 | Δ |
|---|---|---|---|---|---|---|---|---|---|
| EA-ST F2 Case 1 | 0.923% | 0.936% | **−1.4%** | 0.075% | 0.043% | +74.4% | 0.537% | 0.732% | −26.6% |
| EA-ST F2 Case 2 | 1.615% | 1.410% | +14.5% | 0.124% | 0.075% | +65.3% | 0.679% | 1.021% | −33.5% |
| EA-SB F1 Case 1 | 0.950% | 2.30% | **−58.7%** | — | — | — | 1.136% | 1.41% | −19.4% |
| EA-SB F2 Case 1 | 1.261% | 2.24% | −43.7% | 0.137% | 0.086% | +59.3% | 1.304% | 1.45% | −10.1% |
| EA-SB F2 Case 2 | 2.238% | 2.40% | **−6.8%** | 0.123% | 0.086% | +43.0% | 0.836% | 1.52% | −45.0% |
| EA-SB F2 Case 3 | 1.473% | 2.53% | −41.8% | 0.127% | 0.085% | +49.4% | 1.432% | 1.60% | −10.5% |

**What is reproduced: the ordering X_c > X_e ≫ X_i, in all six cases.**
That ordering is Paper 2's actual finding and the reason the region scheme
exists — a frame bolted on at points concentrates strain at its fastenings,
leaves the pipe between them almost unstrained, and the pipe outboard reads
the plain overbend.

**What is not reproduced: the magnitudes, and this is open.**

* **EA-ST** agrees on X_c to −1.4% and +14.5%. Case 2 reading high is
  consistent with the envelope-vs-single-position offset.
* **EA-SB** reads **low** on X_c, from −6.8% to −58.7%, and an envelope
  cannot be below a single position — so that offset is *eliminated* as the
  explanation, rather than left as a possibility. The disagreement is real.
  X_c is also the most sensitive quantity to connector placement, which is
  the thread to pull next.
* **X_i** is high by 43–74% everywhere. It is an order of magnitude below
  X_c, so this moves no design conclusion, but the consistency of the sign
  across all five cases says it is one cause, not five.
* **X_e** is low by 10–45%. **Parked by explicit instruction** — not an
  oversight. Note the X_e boundary follows Paper 2's *figures*, not its
  prose: the text says "pipeline outside the structures" while Figs 27 and
  38 draw X_e running up to where X_c begins. Implementing the prose moved
  X_e from −10% to −45%, so the figures are what we follow (three cases
  settle it; the fourth has its connectors on the body's own edges and
  cannot).

### E.1 The D layouts — F1D / F2D, NOT RUN

Blocked by **G9**, deliberately. A `D` connector is a deadband and needs an
*active set* as well as a co-rotating frame; with the frame alone it would
behave as an always-shut `S` — a different joint, silently answering a
different question. The solver refuses it rather than approximating it.
These cases cannot be compared until the active set is built.

### E.2 PS connections — PREDICTION, not validation

Added 6 Oct with the co-rotating frame. **Paper 2 publishes F1 and F2 only,
so there is no reference value for any of these and no delta can be
computed.** Recorded here so the ledger is not mistaken for complete.

| Archetype | System | X_c | X_i | X_e | Positions |
|---|---|---|---|---|---|
| ILS-EAST | F2 | 0.607% | 0.062% | 0.483% | 24/24 |
| ILS-EAST | **PS** | 0.360% | 0.358% | 0.420% | 24/24 |
| ILS-EASB | F2 | 1.185% | 0.142% | 2.082% | 30/30 |
| ILS-EASB | **PS** | 0.481% | 0.243% | 1.986% | 9/10 |

**These are the archetypes at their SHIPPED dimensions, not the paper's case
dimensions**, which is why the F2 rows here do not match the F2 rows in the
table above — EA-ST reads X_c 0.607% here against 0.923% as Case 1. The F2
column is present only as the control the PS column is read against, and the
pair is internally consistent. For `ILS-EASB` the difference is severe, not
cosmetic: it ships `P_v = 1.6256 m`, which is **4 D** and a 3.5 D lift,
where every published case is 2 D and a 1.5 D lift. Run as shipped it is a
much harsher case than anything Paper 2 published, and `X_e = 2.082%` says
so. **No row of this table may be read against a published value.**

PS relieves the connector and removes the shielding, which is what a pin and
a roller should do: X_c falls 41% on EA-ST and 59% on EA-SB, and X_i rises
to **equal** X_c on EA-ST — with the slot free to slide, the frame can no
longer hold the pipe it spans. `ILS-EASB` PS truncates at 9/10 positions, so
that envelope is a **lower bound**.

---

## F. Scorecard

| Comparison | Status |
|---|---|
| Rebuild vs `run_slay`, plain pipe, 3 radii | **Within 1.7%** — strongest result in the repo |
| Rebuild vs Paper 1, plain pipe, 3 radii | +17.9 / +5.6 / −8.1%, R-trend divergence, documented |
| `run_slay` vs Paper 1, GD-TP, 9 values | Within 6% at R = 85/100; +19–26% at R = 70 |
| Rebuild vs Paper 1, GD-TP | **No comparison exists** — never run at 100 MT / 8 m |
| Rebuild vs Paper 1, GD-SH | **1 of 13 cases** — −9.7% / −5.4% / **+2.3%** as the mesh refines, bracketing the published value |
| Rebuild vs Paper 1, Series 5 | **No comparison exists** — no region columns for `ILS-SHTP` |
| Rebuild vs Paper 2, EA F1/F2 | 6 cases. **Ordering reproduced in all 6**; magnitudes open |
| Rebuild vs Paper 2, EA F1D/F2D | Refused under G9 — needs the `D` active set |
| PS layouts | Prediction only; Paper 2 publishes no PS case |

## G. Gaps this ledger exposes

Written down rather than fixed, so the next session starts from them.

1. **Paper 2 has no citation in this repo.** Its case tables and region
   definitions were transcribed from supplied figures. Every number in §E
   is checked against a transcription, not a source — so a transcription
   error would read exactly like a physics disagreement, which matters most
   for the EA-SB rows that are 40–60% out.
2. **The Series 4 mesh table was run at the wrong tension and unlabelled,
   and a published conclusion rested on it** (§C). The X3/X2 ratio was
   recorded as converging *inside* the paper's 65–75% band; at the paper's
   own tension it converges just *outside*. Corrected here. Any other table
   in the repo stating a strain without its tension, radius and spacing
   should be treated the same way until checked — the standing rule is
   *always state R and tension and spacing*, and this is the second time it
   has been broken. The lesson is sharper than the rule: an unlabelled
   configuration does not merely leave a reader guessing, it silently
   recruits the wrong run into a comparison and the comparison still reads
   plausibly.
3. **Three published series have no rebuild column at all** (Series 3 at
   the paper's configuration, 12 of 13 Series 4 cases, both Series 5
   cases). Series 4's V sweep is the cheapest — three names added to
   `emit_profile.py`'s dimension passthrough, then a sweep; Series 3 is the
   highest-value, at nine published values.
4. **We report extreme-fibre strain per element; the papers report
   "nominal strains at element integration points."** These are expected to
   coincide for a B31 beam in pure bending but this has **never been
   checked against the kernel**. It is a systematic offset candidate
   sitting under *every* row of this file.

---

## Where each row came from

| Table | Working record |
|---|---|
| §A | `RESULTS.md` §1.1, `T5_solve_spec.md` §5e |
| §B | `RESULTS.md` §3, §5.2; `T9_components_spec.md` §6b, §6c |
| §C | `T9_components_spec.md` §4; `T9_physics_sequence.md` (mesh); measured here 6 Oct |
| §D | `T9_components_spec.md` §5 |
| §E | `T9_physics_sequence.md`; `tools/study_f2.py`, `tools/study_easb_cases.py` |
| §E.2 | commit `2816b8b` |

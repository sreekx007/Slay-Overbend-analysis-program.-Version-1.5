# Plain-pipelay surrogate dataset v3 — plan of action

> **Status: plan, for review. Nothing has been run from it.**
> Written 10 October 2026. Supersedes the design in
> `PLAN_plain_surrogate_dataset.md`, which produced the 525-case run now in
> `plain_dataset.csv`. That run stays as it is; this is a different, larger
> and differently-shaped dataset, not a correction of it.

**Goal.** A dataset from which a machine-learning surrogate can predict
plain-pipelay overbend response at the three governing stinger rollers from
five lay parameters. Plain pipe only — no in-line structure of any kind.

---

## 1. What changed, and why the shape is better

The axes are the user's. Four edits were applied to the v2 proposal:

| | v2 proposal | v3 | effect |
|---|---|---|---|
| OD | 8 NPS | **5** — 8, 12 and 20 in removed | 24 → 15 sections |
| Stinger radius | 70 … 145 m, 6 values | **5** — 70 m removed | tightest radius is now 85 m |
| Tension | 0 … 240 MT, 5 values | **4** — 0 MT removed | see §6, this one costs something |
| Wall per NPS | 4 schedules | **3** | 32 → 24 → 15 sections |

**OD and wall are nested, which is the structural improvement over the
525-case run.** There, OD and WT were independent axes with a
`10 ≤ D/t ≤ 60` window and a redraw on rejection; the redraw kept R, spacing
and tension exactly stratified but left the coupled columns lopsided — 168.3
mm appeared 38 times against 323.9 mm's 89, because the extremes are what
gets rejected (L120). Three real walls nested inside each NPS means **every
cell of the factorial is a real pipe**: no window, no rejection, exact
balance on all four axes, and no sampling design to argue about.

---

## 2. The axes

| Axis | Values | n |
|---|---|---|
| Stinger radius `R` | 85, 100, 115, 130, 145 m | 5 |
| Roller spacing | 4, 6, 8, 10, 12 m | 5 |
| Pipe section | 5 NPS × 3 schedules (below) | 15 |
| Lay tension | 60, 120, 180, 240 MT | 4 |

### The 15 sections

Three walls per NPS, chosen to span each pipe's layable range with a
near-geometric middle in `D/t` — not three adjacent schedules, which would
cluster.

| NPS | OD mm | wall 1 | wall 2 | wall 3 |
|---|---|---|---|---|
| 6 | 168.3 | Sch 40/STD 7.11 — **23.7** | Sch 80/XS 10.97 — **15.3** | Sch 120 14.27 — **11.8** |
| 10 | 273.1 | Sch 40/STD 9.27 — **29.5** | Sch 60/XS 12.70 — **21.5** | Sch 100 18.26 — **15.0** |
| 16 | 406.4 | Sch 30/STD 9.53 — **42.6** | Sch 40/XS 12.70 — **32.0** | Sch 80 21.44 — **19.0** |
| 24 | 609.6 | Sch 30 14.27 — **42.7** | Sch 60 24.61 — **24.8** | Sch 80 30.96 — **19.7** |
| 32 | 812.8 | Sch 40 17.48 — **46.5** | API 5L 25.40 — **32.0** | API 5L 31.75 — **25.6** |

*(schedule, wall in mm, **`D/t`**.)*

`D/t` spans **11.8 to 46.5** across the set. `D/2R` spans **0.0580%** (NPS 6
at 145 m) to **0.4781%** (NPS 32 at 85 m).

**NPS 32 leaves the schedule table and the substitution is flagged in every
row.** ASME B36.10M stops at Sch 40 (17.48 mm) for 32 in; its only other
walls are 7.92, 9.53 and 12.70 mm — `D/t` 102.6, 85.3 and 64.0, which nobody
lays. Walls 2 and 3 are API 5L linepipe walls instead, carried as `5L` in the
`sch` column rather than given a schedule name they do not have.

---

## 3. The case list

`CASES_plain_v3_proposed.txt`, 1584 rows.

| block | n | what |
|---|---|---|
| **F** | **1500** | the factorial: 5 R × 5 spacing × 15 sections × 4 tension |
| **A** | 9 | the published anchors — Paper 1 TABLE X and XI |
| **Z** | 75 | *proposed* zero-tension block: 15 sections × 5 spacings at R = 85 |

**Block A is a gate, not data.** All nine anchors now fall **outside** the
factorial — they sit at R = 70 m, at 0 or 100 MT, and on a 21 mm wall that is
not one of the 15 sections (the nearest schedule to 406.4 × 21 is Sch 80 at
21.44). They are run anyway and first, because they are the only tie between
this dataset and `docs/validation/`: all nine reproduced the ledger to four
decimals on the 525-case run, and if they stop doing so the program has moved
and this plan is stale. Nothing is written if block A fails.

**Block Z is a proposal and needs a decision.** See §6.

No train/test split is baked in. The factorial is exactly balanced, so any
split — random, or held-out by axis value for an extrapolation test — can be
chosen afterwards without the design having pre-empted it. That is a change
from the 525-case run, where a random hold-out block had to be reserved
before the first case because the sample was not balanced.

---

## 4. Features — settled

| | feature | unit | note |
|---|---|---|---|
| **raw (5)** | `R` | m | the lay parameter, measured to the roller centreline |
| | `spacing` | m | |
| | `OD` | m | |
| | `t_wall` | m | |
| | `tension_mt` | MT | **absolute**, not a fraction of capacity — see §7 |
| **derived (10)** | `D_over_t` | — | |
| | `curvature` | 1/m | `1/R`; outranked every raw feature on the 525-case run (ρ = +0.767) |
| | `I`, `A` | m⁴, m² | |
| | `EI`, `EA` | N·m², N | |
| | `eps_pure_bend` | — | `D/2R`, the exact zero-tension strain |
| | `spacing_over_OD` | — | earned nothing last time (ρ = −0.059); kept so its absence is not a silent choice |
| | `sigma_axial` | Pa | `tension_mt × 9806.65 / A` |
| | `axial_over_yield` | — | against `j2` σ_y0 = 360 MPa |
| **categorical (2)** | `NPS`, `schedule` | label | the section's name, so a row is identifiable as a real pipe |

---

## 5. Target variables — six, and one of them needs new library code

**Peak strain and bending moment at SR1, SR2 and SR3.**

| target | unit |
|---|---|
| `eps_SR1`, `eps_SR2`, `eps_SR3` | — (fraction) |
| `M_SR1`, `M_SR2`, `M_SR3` | N·m |

### How a per-station value is defined

**The worst the station saw at any position of the passage**, where a
station's value at one position is the worst element within **half a roller
spacing** of it, looked up in **station coordinates** so the same key means
the same place on the stinger at every position.

That is not a new rule: it is exactly what `slay.report.passage`'s
`station_strains` already does, and what every published §1 table in the
ledger is measured with. Moment takes **|M|**, as `_moment_rows` already
does, because sagging between rollers puts the moment through zero and a
signed maximum would report the largest hogging moment and silently miss a
larger sagging one.

### The three rollers are all inside the scored zone

SR1, SR2 and SR3 sit inboard of `DROP_AT_TIP = 3`, so none of them is a tip
roller. **That removes the worst caveat of the 525-case dataset** — there,
`peak_strain` was the zone-restricted envelope while the per-station columns
carried all twelve stations, and in 510 of 518 rows an excluded tip roller
(SR6) read higher than the scored peak. These six targets have no such
mismatch. `peak_strain` and `peak_moment` over the whole zone are still
recorded, as **context columns, not targets**.

### What has to be built

`station_strains` exists. **`station_moments` does not.** The library carries
`band_peak_moment` (worst in the zone) and `_moment_rows` (per element) but
nothing that reduces moment per station. It has to be added to
`slay.report.passage` as the exact analogue of `station_strains` — same
window, same coordinates, same "absent rather than zero" behaviour when a
station has no element near it — with a test, before any case is run. It is a
`report`-layer function, not runner code, because the measurement rule has to
be the same one the validated tables use.

### One known bias in the window rule, to decide on

The window is **half a roller spacing in metres** while the mesh is ruled at
**2 × OD**, so the number of elements a station's maximum is taken over
varies by a factor of **14** across this design:

| NPS | element 2 × OD | sp 4 m | 6 m | 8 m | 10 m | 12 m |
|---|---|---|---|---|---|---|
| 6 | 0.337 m | 11.9 | 17.8 | 23.8 | 29.7 | 35.7 |
| 10 | 0.546 m | 7.3 | 11.0 | 14.6 | 18.3 | 22.0 |
| 16 | 0.813 m | 4.9 | 7.4 | 9.8 | 12.3 | 14.8 |
| 24 | 1.219 m | 3.3 | 4.9 | 6.6 | 8.2 | 9.8 |
| 32 | 1.626 m | 2.5 | 3.7 | 4.9 | 6.2 | 7.4 |

A maximum over more elements tends to read higher, so NPS 6 at 12 m spacing
and NPS 32 at 4 m spacing are not measured on the same footing — and both OD
and spacing are features, so the bias is **correlated with the inputs**,
which is the kind a model will happily learn as physics.

Three ways out:

1. **Keep the half-spacing window** — consistent with every validated number
   in the ledger — **and record `n_elems_SR1..3` beside each target** so the
   bias is visible and testable rather than hidden. *Recommended.*
2. Define the window in diameters instead. Consistent element count, but no
   longer the rule any published table was measured with.
3. Take the single nearest element. Cleanest, most mesh-sensitive, and
   throws away the roller's physical footprint.

Option 1 costs three extra columns and settles nothing by assumption.

---

## 6. What removing 0 MT costs, and block Z

**Zero tension is the only condition in either paper with an answer that has
no solver in it.** With no lay tension the pipe is bent to the stinger arc
and nothing else, so `ε = D/2R` is exact. The 525-case run carried 76 such
cases and they produced its single most useful finding: **the excess over
pure bending is ordered by roller spacing** — +7.5% at 6 m rising
monotonically to +35.7% at 14 m, ρ = +0.731, and ρ = +0.811 within a single
diameter (L120). That is also the open lead on §1's largest disagreement with
Paper 1.

Dropping 0 MT removes that check entirely. **Block Z** puts a minimum of it
back: 15 sections × 5 spacings at R = 85 m, **75 cases**, outside the
factorial so it does not unbalance anything. It is the cheapest possible
version of the one measurement in this project that an FEA cannot argue with.

**Decision needed: include block Z (1584 cases) or not (1509).**

---

## 7. Three things to decide or accept

**Two sections exceed yield in pure membrane at 240 MT.** `sigma_axial = T/A`
against `j2`'s σ_y0 = 360 MPa:

| section | `D/t` | σ at 240 MT | × yield | cases |
|---|---|---|---|---|
| NPS 6 Sch 40/STD 7.11 | 23.7 | 654 MPa | **1.82** | 25 |
| NPS 6 Sch 80/XS 10.97 | 15.3 | 434 MPa | **1.21** | 25 |

50 of the 1500. On the 525-case run that corner is where all seven failures
sat, and the one case that converged there read 2.04% strain at the *mildest*
radius in the set while carrying the *lowest* bending moment — because a
section at its membrane capacity has nothing left to carry bending with, so
the two targets invert. Keeping them records where the solver stops
answering; capping tension per section removes the regime break from the
dataset. **Either is defensible; it has to be chosen, not defaulted.**

**Two corners have never been run.** OD 812.8 mm, where the largest to date
is 609.6, and 4 m roller spacing, tighter than anything yet. **One smoke case
each, before the matrix**, and the result reported before the time is
committed.

**Cost.** The 525-case run was 9.6 s per case, mean, on a lighter set. This
one has a 33% larger maximum diameter and a tighter minimum spacing, both of
which add elements. Estimate **4 to 7 hours** for 1584 cases. Checkpointed
after every case and resumable, so an interrupted run leaves a complete file.

---

## 8. Settings held from the validated path

| Setting | Value | Why |
|---|---|---|
| Entry point | `tools/slide.py::passage(arch_id='none', …)` | the same one `study_table_x.py` and `study_table_xi.py` use for the published §1 tables |
| Mode | `A`, sequential | a real lay carries plastic strain forward |
| Material | `j2` | what every §1 table was run on |
| Step | **2 × OD** | a half-element step buys the slot-interpolation jitter `slide.py --verify` measures at 4.40% on SR1 — numerical, no trend, and a surrogate would learn it as noise. Plain pipe has no edge-crossing envelope to undersample, so the rule is the opposite of a component case's |
| Travel | 4 × OD | `slide.passage`'s plain-pipe sweep |
| Mesh | ruled, 2 × OD | G10 |
| Contact surface | library default (`centreline`) | every validated ledger number uses it |
| Zone | `SR5 and beyond excluded` | `DROP_AT_TIP = 3` |

---

## 9. Rules the run is held to

**Failures are data.** A case that diverges or is refused is recorded with
its status and its reason and the run moves on. A dataset containing only the
cases that converged is biased toward the easy corner and says nothing about
where the method stops working — which is exactly what a surrogate's user
needs to know.

**Checkpointed after every case**, one JSON object appended, so an
interrupted run leaves a complete, usable file.

**The CSV is generated from the results document**, not by the runner
(L122). One column list, parsed, refusing in both directions.

**"It ran" is not verification (G8).** Block A is the gate. The results
document must report the anchor reproduction, the completion rate, the
failure list, the monotonicity of each marginal curve against the direction
physics requires, and the station-window element counts from §5.

**Nothing in the mirror or the kernel is touched.** G6 and G7 hold. The one
library addition is `station_moments` in the `report` layer, with a test.

---

## 10. Open decisions, collected

| | decision |
|---|---|
| 1 | Block Z — include the 75 zero-tension cases for the analytical check, or drop it with 0 MT? |
| 2 | The 50 cases above membrane yield at 240 MT — keep as regime data, or cap tension per section? |
| 3 | Station window — half-spacing plus `n_elems` columns (recommended), in diameters, or nearest element? |
| 4 | Smoke-test NPS 32 and 4 m spacing before committing 4–7 h? |

---

## Action log

| | |
|---|---|
| 10 Oct 2026 | Plan written against the user's axes. Case list generated to `CASES_plain_v3_proposed.txt` (F 1500, A 9, Z 75). Features settled. Targets settled as six — strain and moment at SR1/SR2/SR3 — and `station_moments` identified as missing from the library. Four decisions open. Nothing run. |

> **Superseded by `PLAN_plain_surrogate_v4.md` (10 Oct 2026).** This was
> the review draft; its targets, window rule and sweep travel were all
> changed in review. Left unedited as the record of what was proposed.

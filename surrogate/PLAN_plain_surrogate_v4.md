# Plain-pipelay surrogate dataset v4 — plan of action

> **Status: the plan to be executed.** Written 10 October 2026, after review.
> Supersedes `PLAN_plain_surrogate_v3.md`, which was the review draft and is
> left unedited. The 525-case run in `plain_dataset.csv` stays as it is: this
> is a different dataset with different targets, not a correction of it.

**Goal.** A dataset from which a machine-learning surrogate can predict
plain-pipelay overbend response at the three governing stinger rollers —
total strain, bending moment and roller reaction — from five lay parameters.
Plain pipe only.

---

## 1. The axes

| Axis | Values | n |
|---|---|---|
| Stinger radius `R` | 85, 100, 115, 130, 145 m | 5 |
| Stinger roller spacing | 4, 6, 8, 10, 12 m | 5 |
| Pipe section | 5 NPS × 3 schedules | 15 |
| Lay tension | 60, 120, 180, 240 MT | 4 |

**5 × 5 × 15 × 4 = 1500**, plus block A (below) = **1518 cases**.

### The 15 sections

Three walls per NPS, spanning each pipe's layable range with a
near-geometric middle in `D/t`.

| NPS | OD mm | wall 1 | wall 2 | wall 3 |
|---|---|---|---|---|
| 6 | 168.3 | Sch 40/STD 7.11 — **23.7** | Sch 80/XS 10.97 — **15.3** | Sch 120 14.27 — **11.8** |
| 10 | 273.1 | Sch 40/STD 9.27 — **29.5** | Sch 60/XS 12.70 — **21.5** | Sch 100 18.26 — **15.0** |
| 16 | 406.4 | Sch 30/STD 9.53 — **42.6** | Sch 40/XS 12.70 — **32.0** | Sch 80 21.44 — **19.0** |
| 24 | 609.6 | Sch 30 14.27 — **42.7** | Sch 60 24.61 — **24.8** | Sch 80 30.96 — **19.7** |
| 32 | 812.8 | Sch 40 17.48 — **46.5** | API 5L 25.40 — **32.0** | API 5L 31.75 — **25.6** |

*(schedule, wall mm, **`D/t`**.)* `D/t` spans **11.8 to 46.5**.

**NPS 32 leaves the schedule table and every row says so.** ASME B36.10M
stops at Sch 40 (17.48 mm) for 32 in; its other walls are `D/t` 102.6, 85.3
and 64.0, which nobody lays. Walls 2 and 3 are API 5L linepipe walls,
carried as `5L` in the `sch` column rather than given a schedule name they do
not have.

**OD and wall are nested.** Every cell of the factorial is a real pipe — no
feasibility window, no rejection, exact balance on all four axes, and no
train/test split baked in. That is the structural fix for L120, where
independent OD and WT axes with a `D/t` window left the coupled columns
lopsided because the extremes are what got rejected.

---

## 2. Layout — the stinger grows when the spacing shrinks

**The stinger span must not fall below 40 m.** Stinger roller count is
`n_sr = max(6, ceil(40 / spacing))`, and `n_sr` **excludes** the terminal
tension station, so the scene carries `n_sr + 1` stinger stations.

| spacing | `n_sr` | stations | span | scored zone | θ stinger at R = 85 … 145 |
|---|---|---|---|---|---|
| 4 m | 10 | SR1–SR11 | **40.0 m** | SR1–SR8 | 27.0° … 15.8° |
| 6 m | 7 | SR1–SR8 | **42.0 m** | SR1–SR5 | 28.3° … 16.6° |
| 8 m | 6 | SR1–SR7 | 48.0 m | SR1–SR4 | 32.4° … 19.0° |
| 10 m | 6 | SR1–SR7 | 60.0 m | SR1–SR4 | 40.4° … 23.7° |
| 12 m | 6 | SR1–SR7 | 72.0 m | SR1–SR4 | 48.5° … 28.5° |

Without the rule the two tightest spacings would be a 24 m and a 36 m
stinger — a stub, not a lay. With it, span runs 40 to 72 m instead of 24 to
72, so **spacing and stinger length are partly decoupled** rather than
locked together.

**Three consequences, all checked:**

`config.one_sided_rollers(n_sr)` **re-resolves for the count being built**,
so at `n_sr = 10` it returns SR1…SR10 one-sided with SR11 bidirectional and
bearing the tension — verified. The library was written against exactly this
staleness (using the import-time constant at a larger `n_sr` would leave the
extra rollers bidirectional) and `roller_stations` already comes through the
resolver.

**The scored zone moves with the spacing.** `report.passage.zone` drops the
last three stinger rollers off the *actual* station list, so the zone is
SR1–SR8 at 4 m and SR1–SR4 at 8–12 m. `peak_strain` over the zone therefore
means a different span per spacing and is kept as a **context column, not a
target**. The three targets are named rollers and are unaffected — which is
the strongest argument for naming them.

**Cost rises at the tight end**: 11 slots and a 40 m stinger meshed at
2 × OD. The 4 m cases are the slow ones.

**Vessel rollers are fixed at 9 m, 5 stations, independent of the stinger
spacing.** 9 m is what every validated number and all nine anchors were run
at, so the vessel side is held constant while the stinger side is the
experiment.

---

## 3. Settings

| Setting | Value | Why |
|---|---|---|
| Entry point | `tools/slide.py::passage(arch_id='none', …)` | the same one `study_table_x.py` and `study_table_xi.py` use for the published §1 tables |
| Mode | `A`, sequential | a real lay carries plastic strain forward |
| Material | `j2` — E 210 GPa, σ_y0 360 MPa | what every §1 table was run on |
| **Sweep travel** | **5 × OD** | passed per call |
| Step | 2 × OD | |
| Mesh | ruled, 2 × OD | G10 |
| Contact surface | library default (`centreline`) | every validated ledger number uses it |
| Vessel spacing | 9 m, `n_vr = 5` | held |

**Travel is passed per call and `PLAIN_TRAVEL_OD = 4.0` is left alone.** That
constant is the default for both published §1 runners and for
`slide.py --verify`; moving it would move published numbers. The dataset
passes `clear_after = 5 × OD` instead.

**5 × OD at a 2 × OD step gives shifts 0, 2, 4, 5 × OD — the last is half an
element, and that is harmless for a maximum.** `slide.py --verify` measures
the half-element effect on plain pipe and it reads **low**: 0.1863 against
0.1947 at SR2, alternating with no trend, because a contact point
interpolated to mid-element is softer than one on a node. A position that
reads low cannot raise an envelope. The step stays at 2 × OD for the same
measurement's sake — a half-element step would put that jitter on every
position, worth 0.83% at SR2 and 4.40% at SR1, and a surrogate would learn it
as noise. Plain pipe has no edge crossing to undersample, so the rule is the
opposite of a component case's.

---

## 4. Features

| | feature | unit | note |
|---|---|---|---|
| **raw (5)** | `R` | m | to the roller centreline |
| | `spacing` | m | stinger spacing; vessel is fixed at 9 m |
| | `OD` | m | |
| | `t_wall` | m | |
| | `tension_mt` | MT | **absolute**, not a fraction of capacity |
| **geometry** | `curvature` | 1/m | `1/R`. Outranked every raw feature on the 525-case run, ρ = +0.767 |
| | `pitch_angle` | rad | `spacing / R` — the turn the pipe makes between two supports |
| | `theta_stinger` | rad | `n_sr × spacing / R`, from the **actual** `n_sr`, never assumed 6 |
| | `arc_stinger` | m | `n_sr × spacing` |
| | `n_sr` | — | the roller count this case was built with |
| | `eps_pure_bend` | — | `D/2R` |
| **section** | `D_over_t` | — | |
| | `I`, `A` | m⁴, m² | |
| | `EI`, `EA` | N·m², N | |
| | `spacing_over_OD` | — | earned nothing last time (ρ = −0.059); kept so its absence is not a silent choice |
| | `w_per_m` | N/m | `ρ_steel · A · g`, ρ = 7850, g = 9.81 |
| | `sag_over_OD` | — | `w · spacing⁴ / (384 · EI · OD)` — the group coupling spacing, section and weight |
| **loading** | `sigma_axial` | Pa | `tension_mt × 9806.65 / A` |
| | `axial_over_yield` | — | `sigma_axial / σ_y0` |
| | `eps_axial_nominal` | — | `sigma_axial / E` — **nominal**, see §5 |
| | `eps_yield` | — | `σ_y0 / E` = 0.00171429, constant |
| | `bend_over_yield` | — | `eps_pure_bend / eps_yield` |
| **categorical** | `NPS`, `schedule` | label | so a row is identifiable as a real pipe |

`E`, `σ_y0`, `ρ_steel`, `g`, roller radius and the vessel spacing are
constants of this dataset and are recorded as metadata, not features.

---

## 5. Targets — nine, and the strain is already total

### The three quantities, at SR1, SR2 and SR3

| target | unit | note |
|---|---|---|
| `eps_total_SR1/2/3` | — (fraction) | extreme-fibre strain, **membrane + bending** |
| `M_SR1/2/3` | N·m | magnitude, not signed — see below |
| `react_SR1/2/3` | N | roller reaction, push positive |

Moment is taken as a **magnitude**, as `report.passage._moment_rows` already
does, because sagging between rollers puts the moment through zero and a
signed maximum would report the largest hogging moment and silently miss a
larger sagging one.

SR4 is out by decision; it governed 6 of 518 rows on the 525-case run, which
is recorded here so the choice is visible rather than forgotten.

### Why no axial strain is added to the bending strain

**Because it is already there.** `nlfea_v4.get_element_strains` computes the
extreme fibre as

```
eps_top = eps_axial + r_o * kappa
```

and `solve/passage.py` carries `eps_max = max(|eps_top|, |eps_bot|)` from that
same dict. The strain this program reports has always been total. Adding a
membrane term again would double-count it.

Measured, so this is not an argument from reading: 406.4 × 21 at R = 70 reads
**0.3536%** at 0 MT and **0.5280%** at 100 MT. The nominal membrane strain at
100 MT is `T·g/(A·E)` = **0.0184%**, while the jump is 0.1744 points — so
roughly 90% of what tension does is **geometric**, pulling the pipe harder
onto the rollers, not membrane. A surrogate handed a summed quantity would be
fitting a number that is not what the solver computed.

**The decomposition is recorded instead, and it is free.** The kernel's dict
already carries `eps_axial` and `kappa` beside `eps_max`; the library throws
them away. Carrying them gives, per station:

| | |
|---|---|
| `eps_total_SRn` | the target |
| `eps_membrane_SRn` | the measured `eps_axial` at that station |
| `kappa_SRn` | curvature, 1/m |

so `eps_total − eps_membrane` is the bending part and nothing has to be
re-derived. `eps_axial_nominal` in §4 is the **feature** version — `T·g/(A·E)`
from the inputs alone, computable before any solve — and is deliberately
named apart from `eps_membrane_SRn`, which is **measured**.

### "Near the roller" — ±2 elements, capped so windows cannot overlap

A station's value at one position is the worst element within

```
half-width = min(2 elements, stinger spacing / 2)      element = 2 x OD
```

of the station, in **station coordinates**, so the same name means the same
place on the stinger at every position. The station's value for the case is
the worst it saw **at any position** of the passage.

A fixed element count is the point: the previous dataset's half-spacing
window held between 2.5 and 35.7 elements depending on OD and spacing — a
factor of 14, correlated with two of the features, which is the kind of bias
a model learns as physics. ±2 elements is 5 elements everywhere the cap does
not bite.

**The cap replaces excluding cells, and it costs almost nothing.** Two
elements is `4 × OD`, so adjacent windows would overlap where `8 × OD >
spacing`. It bites in three cells of seventy-five:

| | sp 4 m | sp 6 m | sp 8–12 m |
|---|---|---|---|
| NPS 6, 10, 16 | ±2.0 el | ±2.0 el | ±2.0 el |
| NPS 24 | **±1.6 el** | ±2.0 el | ±2.0 el |
| NPS 32 | **±1.2 el** | **±1.8 el** | ±2.0 el |

Excluding those cells instead would drop 9 section-spacing combinations ×
5 R × 4 T = **180 of 1500 cases**. The cap keeps them, keeps every window
centred on its roller, and never lets two rollers claim the same element.
Recorded as a change from the review's "exclude", reversible on request.

### Roller reaction — where the number comes from

`solve/contact.py::update_active_set` already computes `pen * r` per slot to
decide release, and `newton.py` documents that quantity as *"the physical
reaction in kN — well conditioned, where the raw separation is not"* (at
convergence the violation is ~1e-9 m against a penalty of ~1e15, so the
product is physical and the separation is not). `ContactTarget` carries
`station`, so slot-to-name needs no new bookkeeping.

**It is penalty-scaled, so it gets a global equilibrium gate before any row
is written:** the sum of all vertical reactions must equal the total
self-weight plus the vertical component of the applied tension. That check is
free and it is the only thing that distinguishes a correct reaction from a
plausible one.

Sign convention: **push positive**. A one-sided roller releases when its
reaction goes below `−RELEASE_N`, so an active one should push; the terminal
station is bidirectional and may pull.

### Per-station diagnostics, recorded beside each target

`n_elems_SRn` (how many elements the window held — the bias audit),
`shift_eps_SRn`, `shift_M_SRn`, `shift_react_SRn` (the travel at which each
envelope occurred), `active_SRn` (was the slot active at that position),
`yielded_SRn` (`eps_total > eps_yield`).

### Context columns, not targets

`peak_strain` and `peak_moment` over the scored zone, with their locations
and stations, plus `start_strain`. The zone changes with spacing (§2), which
is exactly why they are not targets.

---

## 6. Library work, with the silent failures each one risks

Five changes. None touches the mirror (G7) or the kernel (G6). Each lands
with a test before any case runs.

| | change | the silent failure it risks |
|---|---|---|
| 1 | `scene.roller_stations` and `scene.build_scene` take `spacing_vr` beside `spacing` | **`scene.bidirectional()` rebuilds the stations from `scene.spacing` alone** (`scene.py:192`). Left alone it would re-space the vessel rollers at the *stinger* spacing inside the seed state — the step that builds the geometry every lay tension is reacted by, and nothing downstream would complain. Fixed in the same change. |
| 2 | `tools/slide.py::passage` gains `n_sr` / `n_vr` pass-through | `scene_for(**kw)` already forwards to `build_scene`, so without this the runner would have to bypass `slide.passage` and stop being the entry point the §1 tables use |
| 3 | `solve.contact.slot_forces()`, carried onto the result, read by `report.passage.station_reactions()` | a reaction that is plausible and wrong. Gated on global vertical equilibrium |
| 4 | `solve.passage._strains` carries `eps_axial` and `kappa` beside `eps_max` | nothing — it is additive. But without it the decomposition in §5 would have to be re-derived from `M` and the section, which is a second answer to something already computed |
| 5 | `report.passage.station_window()` (±2 elements, capped) and `station_moments()` | a window that silently differs from the one the targets are documented with. `station_strains` stays as it is, because every validated §1 number is measured with it |

---

## 7. Block A — the gate, run twice

The nine published plain-pipe cases, Paper 1 TABLE X and XI. All nine fall
**outside** the factorial: R = 70 m, 0 or 100 MT, and a 21 mm wall that is not
one of the 15 sections.

They are run **at both travels**:

| | travel | purpose | must give |
|---|---|---|---|
| A4 | 4 × OD | the ledger gate | 0.5468 / 0.4070 / 0.2965 / 0.1428 / 0.3391 / 0.3536 / 0.5280 / 0.4888 / 0.6352% |
| A5 | 5 × OD | a dataset row at the dataset's own settings | — |

18 cases. **If A4 fails to reproduce the ledger, nothing is written**: the
program has moved and this plan is stale. The A5 rows also measure what the
extra diameter of travel is worth, which is the only place in this dataset
where that is isolated.

---

## 8. Rules the run is held to

**Failures are data.** A case that diverges or is refused is recorded with
its status and its reason and the run moves on. A dataset holding only the
cases that converged is biased toward the easy corner and says nothing about
where the method stops working — which is what a surrogate's user most needs.
Two sections exceed membrane yield at 240 MT (NPS 6 Sch 40 at **1.82 ×**,
Sch 80 at 1.21 ×, 50 of 1500 cases) and they are kept deliberately: it
happens practically, and on the 525-case run that corner held every failure.

**Checkpointed after every case**, one JSON object appended, so an
interrupted run leaves a complete, usable file.

**The CSV is generated from the results document** (L122), by a parser that
refuses in both directions.

**"It ran" is not verification (G8).** Block A4 is the gate. The results
document must report: the anchor reproduction, the equilibrium check on the
reactions, the completion rate, the failure list, the window element counts,
and the monotonicity of each marginal curve against the direction physics
requires.

---

## 9. Known limitations, stated up front

**Weight is in-air steel only** — `RHO_STEEL = 7850`, `g = 9.81`, no
buoyancy and no content. A real lay is submerged. The surrogate learns
dry-weight sag.

**Rollers are one-sided** on the stinger — they push and cannot pull — and
the terminal station is bidirectional because it stands for the catenary
continuation rather than a real roller.

**This is not validation.** Nine of 1518 cases are anchors against published
values; the rest are predictions, and the dataset carries the known offsets
of the program it was run on: §1 of the ledger reads +18.9 / +7.1 / −7.3%
against Paper 1's TABLE X, and about double the paper's own excess over pure
bending on TABLE XI. A surrogate fitted here reproduces **this program** —
which is the right target, since a surrogate exists to be cheaper than the
solver it imitates, not more right than it.

**Zero tension is not sampled**, by decision, so the dataset contains no
case with an answer that has no solver in it. The 525-case run's 76
zero-tension rows and the spacing finding they produced (L120) remain the
only such evidence in the project.

**Cost.** 6 to 10 hours for 1518 cases. The 525-case run was 9.6 s per case
on a lighter set; this one has a 33% larger maximum diameter, a 25% longer
sweep, and up to 11 contact slots at the tight spacings.

---

## 10. Order of work

1. The five library changes of §6, each with its test. The suite must be
   green and `check_layers` clean before any case runs.
2. The reaction equilibrium check, on one case, reported.
3. Block A4 — the nine anchors at 4 × OD against the ledger. **Stop if it
   fails.**
4. Block A5, then the 1500-case factorial, checkpointed.
5. Results document, then the CSV generated from it.

---

## Action log

| | |
|---|---|
| 10 Oct 2026 | Plan written after review. Axes, features and the nine targets settled. Five library changes identified with the silent failure each risks — the `bidirectional()` vessel re-spacing being the one that would not have complained. Window rule changed from excluding overlapped cells to capping the half-width, keeping 180 cases. Travel 5 × OD passed per call so `PLAIN_TRAVEL_OD` and the published §1 numbers are untouched. Nothing run. |

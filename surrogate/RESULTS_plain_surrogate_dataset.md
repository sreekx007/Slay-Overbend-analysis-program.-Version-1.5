# Plain-pipelay surrogate dataset — results

**525 cases run, 518 with a result, 1.41 h of solving.**

| | |
|---|---|
| Produced | 10 October 2026 |
| Branch | `claude/program-rebuild-status-bya72s` |
| Program | sha `3921baa` |
| Runner | `make_plain_dataset.py`, schema `2.0.0`, seed `20261010` |
| Raw | `plain_runs.jsonl`, one JSON object per case, 68 fields |
| Plan | `PLAN_plain_surrogate_dataset.md` — design, axes and the reason for every setting |

Row = one case = one complete passage of plain pipe through the stinger,
solved at every scheduled position, mode A, material `j2`, step 2 × OD, mesh
ruled 2 × OD, zone `SR5 and beyond excluded`.

**This document is the source for the CSV.** The runner deliberately does not
emit one: the order is run, write down, then tabulate, so the table is
generated from this file rather than beside it. Section 10 lists the columns
and the three that have to be computed in that step.

---

## 1. Did it do what the plan said

| | planned | run |
|---|---|---|
| Block A — anchors | 9 | **9** |
| Block B — one factor at a time | ≈ 31 | **28** |
| Block C — joint sample, training | 400 | **392** |
| Block D — joint sample, held out | 100 | **96** |
| **Total** | ≈ 540 | **525** |

The three shortfalls are all **deduplication on the five inputs**, which the
plan specifies and which removes a case that an earlier block already ran:
block B's baseline and three of its axis endpoints are block A anchors, and
the joint blocks each redrew a handful of combinations already present.
Nothing was dropped for any other reason, and no case ran twice.

| | |
|---|---|
| `status = ok` | 518 (98.7%) |
| `status = failed` | 7 (1.3%) |
| partial passages | **0** |
| swept 100% of travel | 518 of 518 that converged |
| inside the papers' envelope | 16 |

**Zero partial passages**, which is the result `L101` was written about: six of
the 85 rows in the superseded 30 September dataset carried
`status = partial 1/2`, and on this program nothing truncates. Every case
either swept its whole travel or failed outright at the first position.

Solve cost: **mean 9.6 s**, median 6.5 s, range 1.4 – 46.7 s. The expensive
end is large diameter on a tight radius with wide spacing — the slowest was
`C0198`, 508 × 12.7 mm at R = 60 m, 14 m spacing, 250 MT, at 46.7 s.

---

## 2. The gate — block A against the validation ledger

All nine of Paper 1's plain-pipe cases, run through this dataset's own path
and settings, against `docs/validation/VALIDATION_v3.0_2026-10-06.md`:

| Table | R (m) | OD (mm) | T (MT) | ledger | this run | Δ | our BM (kN·m) |
|---|---|---|---|---|---|---|---|
| X | 70 | 406.4 | 120 | 0.5468% | **0.5468%** | −0.005% | 1258 |
| X | 85 | 406.4 | 120 | 0.4070% | **0.4070%** | +0.008% | 1185 |
| X | 105 | 406.4 | 120 | 0.2965% | **0.2965%** | +0.004% | 1072 |
| XI | 70 | 168.3 | 0 | 0.1428% | **0.1428%** | +0.015% | 94 |
| XI | 70 | 168.3 | 100 | 0.3391% | **0.3391%** | −0.004% | 134 |
| XI | 70 | 406.4 | 0 | 0.3536% | **0.3536%** | +0.012% | 1207 |
| XI | 70 | 406.4 | 100 | 0.5280% | **0.5280%** | +0.002% | 1258 |
| XI | 70 | 508.0 | 0 | 0.4888% | **0.4888%** | +0.006% | 2033 |
| XI | 70 | 508.0 | 100 | 0.6352% | **0.6352%** | −0.000% | 2074 |

**Nine of nine, to four decimals, worst disagreement 0.015%** — which is
rounding in the ledger's own printed figures, not a difference in the solve.
The gate is green, so the rest of the dataset is written down.

---

## 3. What the targets span

| | min | p25 | median | p75 | max |
|---|---|---|---|---|---|
| peak strain | 0.0551% | 0.1809% | 0.3002% | 0.5277% | **2.7249%** |
| peak moment | 2 kN·m | — | 543 kN·m | — | 4505 kN·m |

**A factor of 49 in strain.** The published plain-pipe cases span 0.1428% to
0.6352% — a factor of 4.5 — so the dataset is about an order of magnitude
wider in target than the material it is anchored to, in both directions.

**The moment range is not a range of the same kind and is not quoted as a
ratio.** Its minimum, 2.2 kN·m, is `C0118` — the axially-yielded case of
section 8, which reads 2.0406% strain. The five lowest moments in the dataset
are the five most axially-overloaded cases, and that inversion is real
physics: a section at its membrane capacity has nothing left to carry bending
with, so moment *collapses* while strain is at its largest. Outside that
corner the two targets rise together.

| | case | inputs |
|---|---|---|
| worst | `C0198` **2.7249%** | R 60, sp 14.0, 508 × 12.7, 250 MT |
| | `D0449` 2.5989% | R 60, sp 14.0, 273.1 × 15.9, 200 MT |
| | `C0330` 2.5145% | R 60, sp 14.0, 273.1 × 12.7, 160 MT |
| mildest | `D0430` **0.0551%** | R 250, sp 10.5, 219.1 × 11.0, 0 MT |
| | `C0281` 0.0572% | R 250, sp 12.0, 219.1 × 12.7, 0 MT |

**SR2 governs almost everywhere: 488 of 518 (94.2%).** The remainder are
SR3 (15), SR5 (9) and SR4 (6). The second stinger roller is the governing
station across essentially the whole five-dimensional box, not only at the
published points — which is a result about the layout, since nothing in the
design favours it.

---

## 4. The five marginal curves (block B)

Each axis swept alone from the baseline R = 85 m, 9 m spacing,
406.4 × 21.0 mm, 120 MT. **All five move monotonically in the direction
physics requires**, which is the cheapest sanity check the dataset admits and
it passes on every axis.

| Stinger radius R (m) | strain | moment (kN·m) |
|---|---|---|
| 60 | 0.6845% | 1299 |
| 70 | 0.5468% | 1258 |
| 85 | 0.4070% | 1185 |
| 105 | 0.2965% | 1072 |
| 120 | 0.2401% | 981 |
| 150 | 0.1902% | 805 |
| 200 | 0.1467% | 607 |
| 250 | 0.1219% | 487 |

Falling, **5.61×** across the range. The strongest axis in the dataset.

| Roller spacing (m) | strain | moment (kN·m) |
|---|---|---|
| 6.0 | 0.3225% | 1106 |
| 7.5 | 0.3828% | 1168 |
| 9.0 | 0.4070% | 1185 |
| 10.5 | 0.4279% | 1198 |
| 12.0 | 0.4706% | 1225 |
| 14.0 | 0.5340% | 1250 |

Rising, **1.66×**. Wider spacing means a longer unsupported span and more
curvature concentrated at the roller that does bear.

| Pipe OD (mm) | strain | moment (kN·m) |
|---|---|---|
| 219.1 | 0.2726% | 233 |
| 273.1 | 0.2875% | 424 |
| 323.9 | 0.3268% | 653 |
| 406.4 | 0.4070% | 1185 |
| 508.0 | 0.5083% | 2003 |
| 609.6 | 0.6234% | 3027 |

Rising, **2.29×** in strain and **13×** in moment. Six points, not seven:
168.3 mm at the baseline 21 mm wall is `D/t = 8.0`, outside the sampling
window, so the small-diameter end of this one curve is covered by block C
instead. Stated in the plan, not discovered here.

| Pipe WT (mm) | strain | moment (kN·m) |
|---|---|---|
| 8.0 | 0.5453% | 467 |
| 11.0 | 0.4881% | 647 |
| 12.7 | 0.4665% | 745 |
| 15.9 | 0.4379% | 921 |
| 19.1 | 0.4167% | 1089 |
| 21.0 | 0.4070% | 1185 |
| 25.4 | 0.3897% | 1397 |
| 31.8 | 0.3720% | 1682 |

**This curve is the new content of the dataset and it goes the opposite way
from the moment.** Strain *falls* 1.47× as the wall thickens while moment
*rises* 3.6×: a heavier wall carries more section force at the same imposed
geometry and reaches a lower extreme-fibre strain doing it. The 30 September
dataset could not show this at all, because it tied wall thickness to
diameter.

| Lay tension (MT) | strain | moment (kN·m) |
|---|---|---|
| 0 | 0.2532% | 1105 |
| 40 | 0.3314% | 1173 |
| 80 | 0.3759% | **1187** |
| 120 | 0.4070% | 1185 |
| 160 | 0.4389% | 1180 |
| 200 | 0.4685% | 1171 |
| 250 | 0.5054% | 1156 |

Strain rising, **2.00×**. **The moment is the one non-monotone target in the
whole block**: it peaks at 80 MT (1187 kN·m) and falls to 1156 kN·m at
250 MT while the strain keeps climbing. Tension adds membrane strain
directly and at the same time straightens the pipe between rollers, which
takes curvature — and therefore moment — out. Past about 80 MT the second
effect wins on moment and never wins on strain. **A surrogate fitted on
strain alone would not reveal this, and a designer reading moment as a proxy
for strain would be wrong above 80 MT.**

---

## 5. Which inputs matter (blocks C + D, n = 481)

Spearman rank correlation against peak strain:

| feature | ρ | p |
|---|---|---|
| **curvature 1/R** | **+0.767** | 1.5 × 10⁻⁹⁴ |
| *(R itself)* | −0.767 | — |
| `eps_pure_bend` = D/2R | +0.702 | 1.1 × 10⁻⁷² |
| lay tension | +0.416 | 1.6 × 10⁻²¹ |
| D/t | +0.268 | 2.2 × 10⁻⁹ |
| OD | +0.197 | 1.4 × 10⁻⁵ |
| roller spacing | +0.158 | 5.0 × 10⁻⁴ |
| wall thickness | −0.145 | 1.4 × 10⁻³ |
| EI | +0.143 | 1.7 × 10⁻³ |
| spacing / OD | −0.059 | 0.20 |

**Read this beside section 4, not instead of it.** Roller spacing ranks
seventh here with ρ = +0.158, and block B shows it moving the target 1.66×
cleanly and monotonically. Both are true: in a joint sample the radius
varies over a 4.2× range and swamps everything else in a *rank* statistic,
so a marginal correlation understates any axis that is real but weaker. That
is precisely why the design carries an OFAT spine as well as a hypercube,
and it is the one place where reading only the correlation table would give
a wrong answer about the physics.

`spacing / OD` is the one derived feature that earns nothing (ρ = −0.059,
p = 0.20). It is kept in the schema because its absence would be a silent
choice, and flagged here as uninformative.

---

## 6. The analytical check — 76 zero-tension cases

At zero lay tension the pipe is bent to the stinger arc and nothing else, so
`ε = D/2R` is exact with no solver in it. The dataset contains **76** such
cases, against the papers' three, and each one is a comparison against
arithmetic rather than against another FEA.

| | excess over D/2R |
|---|---|
| mean | **+19.0%** |
| median | +16.8% |
| range | +1.5% to +58.4% |

The sign is the paper's own finding reproduced 76 times over: discrete roller
supports concentrate curvature above the pure-bending value, always.

### And the excess is ordered by roller spacing

| spacing (m) | n | mean excess | median | mean OD (mm) | mean R (m) |
|---|---|---|---|---|---|
| 6.0 | 12 | **+7.5%** | +6.0% | 442 | 115 |
| 7.5 | 14 | +10.8% | +6.9% | 414 | 140 |
| 9.0 | 13 | +15.8% | +17.0% | 364 | 112 |
| 10.5 | 15 | +22.1% | +16.7% | 428 | 129 |
| 12.0 | 12 | +25.6% | +23.9% | 294 | 147 |
| 14.0 | 10 | **+35.7%** | +34.1% | 359 | 118 |

**Monotone across all six groups, a factor of 4.8 from end to end**, and it
is spacing and not something riding along with it:

| excess vs | ρ | p |
|---|---|---|
| **spacing** | **+0.731** | 6.4 × 10⁻¹⁴ |
| R | −0.326 | 4.0 × 10⁻³ |
| OD | −0.304 | 7.5 × 10⁻³ |
| wall | −0.299 | 8.7 × 10⁻³ |
| D/t | −0.047 | 0.69 |
| `eps_pure_bend` | +0.033 | 0.78 |

Mean OD and mean R are comparable across the six groups, and within the
**single** diameter 406.4 mm — 17 cases, diameter held exactly — spacing
still orders it at **ρ = +0.811**. The confounder that would matter runs the
wrong way: excess correlates *negatively* with OD, and the narrow-spacing
groups carry the *larger* mean diameters, so the trend is if anything
understated.

### A lead for §8 of the ledger, stated as a lead

`§1` of the validation ledger records the most load-bearing disagreement in
the file: on TABLE XI our excess over pure bending reads
**+18.8 / +21.8 / +34.7%** where Paper 1's own Abaqus column reads
**+8 / +14 / +17%** — "roughly twice as much strain at a roller as the
benchmark does, measured against a reference neither model can argue with."

Those three cases were run at **9 m spacing**. This table says the excess at
**6 m spacing averages +7.5%**, which is where Paper 1's +8% sits.

**So part of that doubling may be a roller-spacing mismatch rather than a
model difference** — and the repository is not internally consistent about
what the paper's spacing is: `tools/study_table_x.py` and
`tools/study_table_xi.py` default to **9 m**, while `tools/slide_plain.py`
documents and defaults to **8 m**. Paper 1's stated spacing for TABLE XI was
**not** confirmed from the paper in producing this dataset, so this is a
checkable lead and nothing more. It is not a correction to §1 and no ledger
number is changed on the strength of it.

---

## 7. The seven failures

All seven are `no position converged` — the first position diverged and the
passage stopped. None is a partial, none is a silent drop, and all seven are
rows in the dataset with their inputs and their reason.

| case | R | sp | OD × WT | T | D/t | σ axial | × yield |
|---|---|---|---|---|---|---|---|
| `C0139` | 85 | 7.5 | 168.3 × 8.0 | 250 | 21.0 | 609 MPa | **1.69** |
| `C0329` | 120 | 7.5 | 168.3 × 8.0 | 250 | 21.0 | 609 MPa | **1.69** |
| `C0140` | 60 | 12.0 | 168.3 × 8.0 | 200 | 21.0 | 487 MPa | **1.35** |
| `D0450` | 60 | 14.0 | 219.1 × 8.0 | 200 | 27.4 | 370 MPa | **1.03** |
| `C0255` | 60 | 14.0 | 168.3 × 15.9 | 200 | 10.6 | 258 MPa | 0.72 |
| `C0242` | 70 | 14.0 | 273.1 × 11.0 | 200 | 24.8 | 217 MPa | 0.60 |
| `C0076` | 70 | 14.0 | 168.3 × 11.0 | 120 | 15.3 | 216 MPa | 0.60 |

*(σ axial = T / A against `j2`'s σ_y0 = 360 MPa.)*

**Four of the seven are asking for a pipe that cannot hold the tension at
all** — up to 1.69 × yield in pure membrane, before the stinger bends it. A
solver that converged on those would be the thing to worry about. The other
three are thin wall at the widest spacing on a tight-to-middling radius, and
they are the genuine edge of the method.

The failures are not scattered: **every one has OD ≤ 273.1 mm and
T ≥ 120 MT.** That corner of the design holds 102 cases and 7 of them failed
— a **7% failure rate inside it against 0% everywhere else**. Mean over the
failures against mean over the successes: σ axial 395 against 80 MPa,
spacing 11.9 against 9.7 m, OD 191 against 381 mm.

**That boundary is a usable output of the dataset**, not a defect in it. A
surrogate's user needs to know where the solver it imitates stops answering,
and the answer is: small diameter, thin wall, high absolute tension, wide
spacing.

---

## 8. Three things a consumer of this data must know

### The tension axis is absolute, so at small diameters it changes regime

Lay tension is an axis in MT, not in a fraction of capacity. The same 200 MT
that is routine on a 24 in pipe is past yield on a 6 in one. Among the 518
cases with a result, **6 are above `j2`'s σ_y0 in pure membrane and 11 more
are between 0.8 and 1.0 of it.** σ axial runs 0 to 487 MPa, median 59 MPa.

The clearest case is `C0118` — 168.3 × 8.0 mm at 200 MT — which reads
**2.0406%**, among the largest strains in the set, **at R = 250 m, the
mildest radius sampled**. Nothing about the stinger produced that number; the
section was yielded in tension before it arrived.

And `C0118` carries the **lowest peak moment in the whole dataset**, 2.2 kN·m,
beside that 2.04% strain. The five lowest moments are the five most axially
overloaded cases. **In this corner the usual relation between the two targets
inverts**, because a section at its membrane capacity has nothing left to
carry bending with — so a surrogate fitted on moment and read as a proxy for
strain fails here in the worst possible direction: it reports the mildest case
in the set exactly where the strain is among the highest.

Those rows are legitimate and are kept, but they are a different regime, and
the CSV must carry `sigma_axial` and an above-yield flag so a model is not
fitted across the boundary without anyone noticing.

### The per-station columns include stations outside the scored zone

`peak_strain` is the envelope over the scored zone — `DROP_AT_TIP = 3`, so
SR5, SR6 and SR7 are excluded, the same rule every §1 table uses. The
per-station columns carry **all twelve** stations, so they are not on the
same footing as the target.

**In 510 of 518 rows (98%) an excluded tip roller reads higher than the
scored peak** — almost always SR6, by a mean of +14.9% and up to +67.5%. On
the baseline case SR6 reads 0.4668% against the scored 0.4070% at SR2. Using
`eps_SR5_env`, `eps_SR6_env` or `eps_SR7_env` as a feature for `peak_strain`
is not leakage of the target, but it is a comparison across two different
zone rules and it will mislead.

### Blocks C and D are drawn from the same distribution, and that is the point

| block | n | min | median | max |
|---|---|---|---|---|
| C (training) | 386 | 0.0572% | 0.2876% | 2.7249% |
| D (held out) | 95 | 0.0551% | 0.2807% | 2.5989% |

Medians 2.5% apart over a 49× target range, and the ranges nest. Block D is
a *random* held-out set, reserved before any case ran, and it measures
interpolation inside the sampled box. **It is not an extrapolation test.**
A surrogate scored only on block D says nothing about R below 60 m, spacing
above 14 m, or `D/t` outside 10–60.

---

## 9. Coverage, and where the stratification was spent

Blocks C + D, value counts per axis:

| axis | counts |
|---|---|
| R (m) | 60:62 70:62 85:60 105:60 120:61 150:60 200:62 250:61 |
| spacing (m) | 6:82 7.5:83 9:82 10.5:82 12:79 14:80 |
| OD (mm) | 168.3:38 219.1:55 273.1:74 323.9:89 406.4:82 508:79 609.6:71 |
| WT (mm) | 8:55 11:76 12.7:70 15.9:74 19.1:63 21:58 25.4:52 31.8:40 |
| tension (MT) | 0:72 40:72 80:67 120:67 160:70 200:70 250:70 |
| D/t | min 10.2, median 21.3, max 55.4 |

**R, spacing and tension are flat to within a few counts — the stratification
held. OD and WT are not, and the reason is the `D/t` rejection.** When a draw
lands on an infeasible section the plan redraws the OD and WT *pair*, which
restores feasibility and keeps the other three axes exactly stratified, but
it breaks the uniformity of those two columns: 168.3 mm appears 38 times
against 323.9 mm's 89, and 31.8 mm wall 40 times against 11.0 mm's 76. The
extremes of the two coupled axes are the ones that get rejected, so they end
up under-represented by roughly a factor of two.

**The cost is real and is where the design paid for decoupling OD from WT.**
A model fitted here sees the 6 in and the 32 mm-wall corners about half as
often as the middle. If that matters, the fix is a stratified sample over the
47 *feasible pairs* as a single axis rather than over two axes with
rejection — which is a different design, and this one is recorded as it ran.

---

## 10. Columns, for the CSV step

**This section is the contract the CSV is generated from.**
`make_csv.py` parses the two tables below and emits exactly what they say; it
carries no column list of its own, because two lists drift and then this
document becomes a story about a table nobody produced from it. It refuses
rather than guesses: a name here that no row carries, a key in
`plain_runs.jsonl` that is not named here, or a computed column it does not
implement, each stops the CSV from being written.

The group table lists **69** names. `plain_runs.jsonl` carries **68** of
them: `traceback` is written only when a case raises an exception, and no
case did, so it is emitted as an empty column rather than dropped — a reader
diffing the document against the file has to find every name. With the three
computed columns appended, `plain_dataset.csv` is **525 rows × 72
columns**.

| group | fields |
|---|---|
| identity | `schema_version`, `case_id`, `family`, `block`, `design`, `git_sha`, `produced_at` |
| **inputs (5)** | `R`, `spacing`, `OD`, `t_wall`, `tension_mt` |
| settings | `step`, `mode`, `material`, `zone_label` |
| derived features (8) | `D_over_t`, `curvature`, `I`, `A`, `EI`, `EA`, `eps_pure_bend`, `spacing_over_OD` |
| reference | `ref_table`, `ref_strain_pct`, `within_paper_box` |
| **targets** | `peak_strain`, `peak_strain_station`, `peak_strain_s_station`, `peak_strain_s_material`, `peak_strain_shift`, `peak_moment`, `peak_moment_s_station`, `peak_moment_shift`, `start_strain` |
| per station (24) | `eps_SR1_env` … `eps_VR5_env`, `s_SR1` … `s_VR5` |
| diagnostics | `status`, `error`, `n_positions`, `n_converged`, `complete`, `seconds`, `n_active`, `n_slots`, `traceback` |

**Three columns are to be added in the CSV step**, all arithmetic on fields
already present, all because this document found a reason for them:

| column | definition | why |
|---|---|---|
| `sigma_axial` | `tension_mt × 9806.65 / A` | section 8: the tension axis changes regime at small diameter |
| `axial_over_yield` | `sigma_axial / 360e6` | 6 rows above 1.0, 11 more above 0.8 |
| `tip_exceeds_peak` | `max(eps_SR5..SR7) > peak_strain` | section 8: true in 98% of rows, and the columns are on a different zone rule |

They are **appended** after everything the run wrote, in the run's own order,
so the CSV header diffs cleanly against the raw file. Two notes on reading
them:

`sigma_axial` and `axial_over_yield` are arithmetic on inputs alone, so they
are computed for **all 525 rows including the seven failures** — which is why
counting `axial_over_yield > 1` in the CSV gives **10** where section 8 says
6. Six of those are among the 518 cases with a result; the other four are
failures, and section 7 lists them at 1.03 to 1.69 × yield. Both numbers are
right and they are counting different populations.

`tip_exceeds_peak` is empty for the seven failures, because there is no
scored peak to exceed.

### The one unit trap

**`peak_strain`, `start_strain`, `eps_*_env` and `eps_pure_bend` are
FRACTIONS. `ref_strain_pct` is a PERCENT**, because it is transcribed from
the papers' own tables, which print percent. Subtracting one from the other
gives nonsense that looks plausible — 0.4070 against 0.4070% is a factor of
100 — and this is the third time that family of slip has appeared in this
project. Both are flagged in `plain_dataset.csv.schema.json` with the word
FRACTION or PERCENT in the `quantity` field.

`start_strain` is worth one note of its own. **In 331 of 518 rows it equals
`peak_strain` exactly**, mean gain over the passage +0.26%, median 0.00%, max
+5.16%. For plain pipe at a whole-element step that is the expected answer
and it is the step choice being confirmed from the other side: station-space
strain is invariant under a whole-element shift, so a passage adds almost
nothing over a single position **for plain pipe**. It adds 16% on a component
case, which is why the two get opposite step rules.

---

## 11. What this dataset is not

**Not validation.** Nine rows are anchors against published values; the other
516 are predictions, and only 16 cases have all five inputs inside the
papers' envelope. `within_paper_box` is in every row so a consumer can tell
the difference without reading this file.

**Not component lay.** Plain pipe only. GD-TP, the shroud archetypes, EA-ST,
EA-SB and the GD-Simple reductions of ledger §6 are out of scope and have
their own apparatus.

**Not the papers, and not the sea.** The dataset carries the known offsets of
the program it was run on, and they are not small: §1 of the ledger reads
+18.9 / +7.1 / −7.3% against Paper 1's TABLE X and about double the paper's
own excess over pure bending on TABLE XI. A surrogate fitted here reproduces
**this program**. That is the correct target — a surrogate exists to be
cheaper than the solver it imitates, not more right than it — and section 6
is the one place where this dataset may have something to say back to the
ledger about why the gap is as large as it is.

---

## Action log

| | |
|---|---|
| 10 Oct 2026 | `plain_dataset.csv` generated from section 10 of this document: 525 rows × 72 columns, with `plain_dataset.csv.schema.json` beside it. Round trip verified exact over all 525 rows and all 68 run-written columns, computed columns recomputed independently and exact, and all six of the generator's refusal paths exercised. |
| 10 Oct 2026 | 525 cases run, 1.41 h. Block A green 9/9 to four decimals. Zero partial passages. Seven failures, all in one corner, all recorded. Three columns identified for the CSV step. One lead raised for ledger §8 — the excess over pure bending is ordered by roller spacing, ρ = +0.731 over 76 zero-tension cases, and at 6 m spacing it lands on Paper 1's own figure. |

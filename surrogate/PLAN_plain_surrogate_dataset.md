# Plain-pipelay surrogate dataset — plan of action

> **Status: plan.** Written 10 October 2026, before any case was run. The
> companion `RESULTS_plain_surrogate_dataset.md` records what the run
> actually produced, including every way it departed from this document.

**Goal.** A dataset from which a machine-learning surrogate can predict
plain-pipelay overbend response from five lay parameters: stinger radius,
roller spacing, pipe outside diameter, pipe wall thickness and lay tension.
Plain pipe only — no in-line structure, no component of any kind.

---

## 1. What already exists, and why it is not the answer

`docs/dataset/dataset_plain.csv` is an 85-row plain-pipe matrix produced on
30 September 2026 by `tools/dataset.py`, over four axes that are nearly the
ones asked for here. It is not reused, for two independent reasons.

**It predates the 7 October campaign and every number in it is void.** Four
defects in what a passage *is* landed that day — `L101` (passages
truncating between 6.3% and 38.4% of their travel and being compared to the
paper anyway), `L105` (`lay_tension` taking no `shift`, so the lay tension
stayed bolted to one piece of steel for a whole passage), `L106` (nothing
cutting back the travel between positions) and the strain guard — plus
`L107`, a wrong lay tension on every Paper 2 case. The validation ledger
re-ran all fifty published cases in response. **The dataset was not
re-run.** Measured on the baseline case, same five inputs, same 2 × OD step:

| | peak strain | positions |
|---|---|---|
| `dataset_plain.csv` `P000`, 30 Sep, sha `1dea2ee` | 0.4085% | 3 |
| this program, 10 Oct, sha `3921baa` | 0.4070% | 3 |

0.37% on the easiest case in the set. That is not the number that matters —
**six of the 85 rows carry `status = partial 1/2`**, which is an `L101`
truncation recorded as a status, and those are the rows where the old
program and this one have no reason to agree at all.

**Outside diameter and wall thickness were not independent.** The old design
varies a single `pipe` axis of seven *(OD, WT)* pairs — 168.3 × 11,
219.1 × 12.7, … 610 × 28.6 — so `D/t` runs 15.3 to 21.3 and the dataset
contains no information about wall thickness at fixed diameter. A surrogate
fitted on it cannot answer "same pipe, heavier wall", which is one of the
five questions asked here. **Decoupling OD from WT is the substantive new
content of this dataset**, not the re-run.

Nothing in `docs/dataset/` is deleted or edited. It stays as the 30 September
artifact it is, and this folder is a separate, later dataset.

---

## 2. Where the work lives

```
surrogate/
  PLAN_plain_surrogate_dataset.md      this file
  RESULTS_plain_surrogate_dataset.md   what the run produced
  make_plain_dataset.py                the runner
  plain_runs.jsonl                     one JSON object per case, append-only
```

The CSV is **not** produced by the runner. It is generated from the results
MD in a later step, which is the order asked for: run, write down, then
tabulate. The JSONL is the checkpoint, not the deliverable.

---

## 3. What one case is

One **case** is one complete passage: plain pipe swept through the stinger,
solved at every scheduled position, carrying state forward (mode A). One
case becomes one row.

The solve goes through `tools/slide.py::passage(arch_id='none', …)`, which is
the same entry point `tools/study_table_x.py` and `tools/study_table_xi.py`
use for the published §1 plain-pipe tables. Nothing new is written in the
physics path for this dataset; if it were, the dataset would be measuring
code that nothing has validated.

| Setting | Value | Why |
|---|---|---|
| Mode | `A`, sequential | a real lay is sequential and carries plastic strain forward; mode B is the check, not the dataset |
| Material | `j2` | the same elastic-plastic material every §1 table was run on |
| Step | **2 × OD** | see below |
| Travel | 4 × OD | `slide.passage`'s plain-pipe sweep; there is no component to size it from |
| Mesh | ruled, 2 × OD | G10 |
| Contact surface | library default (`centreline`) | every validated number in the ledger was computed with it |
| Zone | `SR5 and beyond excluded` | `DROP_AT_TIP = 3`, the physics sequence's own rule |

**The step is 2 × OD and that is a deliberate choice against 1 × OD.**
`slide.py --verify` measures the sliding on plain pipe in the linear-elastic
case, where station-space strain *must* be invariant under a shift because
the rollers impose the same geometry at every position. At a whole-element
step (2 × OD) the spread is 0.03–0.08% — exact. At a half-element step it is
0.83% at SR2 and **4.40% at SR1**, because a contact point interpolated to
the middle of an element is softer than one on a node: the slot
coefficients are linear in the two bracketing nodes. That jitter is
numerical, it has no trend, and a surrogate fitted through it would learn it
as noise in the target.

The usual argument for refining the step — undersampling the envelope, worth
16% on a component case — **does not apply to plain pipe**, because the
plain-pipe envelope is not at an edge crossing. There is no edge. So the
choice here is the opposite of the choice for a component case, and for a
stated reason rather than by inheritance.

---

## 4. The axes

| Axis | Values | n | Baseline |
|---|---|---|---|
| Stinger radius `R` (m) | 60, 70, 85, 105, 120, 150, 200, 250 | 8 | **85** |
| Roller spacing (m) | 6, 7.5, 9, 10.5, 12, 14 | 6 | **9** |
| Pipe OD (m) | 0.1683, 0.2191, 0.2731, 0.3239, 0.4064, 0.5080, 0.6096 | 7 | **0.4064** |
| Pipe WT (m) | 0.0080, 0.0110, 0.0127, 0.0159, 0.0191, 0.0210, 0.0254, 0.0318 | 8 | **0.0210** |
| Lay tension (MT) | 0, 40, 80, 120, 160, 200, 250 | 7 | **120** |

The baseline is Paper 1 TABLE X configuration B, so the centre of the design
is a case whose value is published and already in the ledger.

**Ranges are chosen to contain the papers and then extend past them.** The
papers use R = 70/85/105, spacing 8–9 m, three diameters at 21 mm wall, and
0/100/120 MT. Everything outside that is extrapolation and the dataset says
so per row: a `within_paper_box` flag marks the cases whose five inputs all
fall inside the published envelope.

**`R = 250` and `tension = 0` are both deliberate.** 250 m is the control
radius §6 uses for a nearly-unbent pipe, and zero tension is the one
condition in either paper that has an **independent analytical answer**:
with no lay tension the pipe is bent to the stinger arc and nothing else, so
`ε = D/2R` is exact with no solver in it. Every zero-tension row therefore
carries a third column that is not an FEA at all, and §1 of the ledger shows
our closed form reproducing the paper's own analytical column to under 1%.

### Feasibility — `D/t`

OD and WT are varied **independently**, so the product grid contains
sections that are not pipe: 168.3 × 31.8 mm is `D/t = 5.3`. A window of

```
10 <= D/t <= 60
```

is applied, which keeps **47 of the 56** OD × WT combinations:

| OD (mm) | walls kept | `D/t` range |
|---|---|---|
| 168.3 | 4 of 8 | 10.6 – 21.0 |
| 219.1 | 6 of 8 | 10.4 – 27.4 |
| 273.1 | 7 of 8 | 10.8 – 34.1 |
| 323.9 | 8 of 8 | 10.2 – 40.5 |
| 406.4 | 8 of 8 | 12.8 – 50.8 |
| 508.0 | 7 of 8 | 16.0 – 46.2 |
| 609.6 | 7 of 8 | 19.2 – 55.4 |

The full feasible grid is 8 × 6 × 47 × 7 = **15 792** cases. At the measured
cost below that is about 44 hours, so the grid is sampled, not enumerated.

**The window governs sampling, not physics, and block A is exempt.** 6 in ×
21 mm is `D/t = 8.0` and is a real pipe — it is TABLE XI's own first row.
The window exists to stop the independent OD × WT product from generating
sections nobody lays; it is not a claim that a thicker wall is impossible.
Block A runs the papers' cases as published, `D/t` window or not, and the
three 6 in anchors sit outside it deliberately.

---

## 5. The design — four blocks

Measured first: one plain passage costs **3.3 to 19.7 s**, mean about 8.5 s,
on six anchor cases. Zero tension is the expensive end. The budget below is
about 540 cases ≈ 1.5 h of solving, doubled for safety.

### Block A — anchors (9 cases)

The published plain-pipe cases, run through this dataset's own path at this
dataset's own settings, so the dataset contains rows whose values can be
checked against `docs/validation/` without re-running anything.

| | cases |
|---|---|
| TABLE X — 16 in, 120 MT, R = 70 / 85 / 105 | 3 |
| TABLE XI — 6 / 16 / 20 in at 21 mm, R = 70, T = 0 and 100 MT | 6 |

**These are a gate, not decoration.** All six were run before this plan was
written and all six reproduce the ledger to the printed digits:

| anchor | ledger | this run |
|---|---|---|
| TABLE X A (R 70) | 0.5468% | 0.5468% |
| TABLE X B (R 85) | 0.4070% | 0.4070% |
| TABLE X C (R 105) | 0.2965% | 0.2965% |
| TABLE XI 16 in, 0 MT | 0.3536% | 0.3536% |
| TABLE XI 6 in, 100 MT | 0.3391% | 0.3393% |
| TABLE XI 20 in, 100 MT | 0.6352% | 0.6352% |

*(The 6 in row differs in the fourth decimal because this check used
OD = 0.168 and the axis value is 0.1683. The dataset uses 0.1683.)*

If a later run of block A fails to reproduce these, the dataset is not
written — the program moved and the plan is stale.

### Block B — one factor at a time (≈ 31 cases)

Baseline, then each axis swept alone with the other four held. This is what
makes the dataset *readable*: five marginal curves a person can look at and
sanity-check against physics before any model is fitted.

One restriction is forced by `D/t`: the OD axis is swept at the baseline
wall of 21 mm, and `168.3 / 21 = 8.0` is outside the window, so **the OD
axis has 6 of its 7 values** and the small-diameter end of that one curve is
covered by block C instead. Recorded, not worked around.

OFAT alone is not enough and is not relied on: a model trained on OFAT data
learns that the axes are independent, and they are not. Hence block C.

### Block C — joint sample, training (400 cases)

A stratified sample over all five axes at once — the discrete analogue of a
Latin hypercube, the same `lhs` scheme `tools/dataset.py` uses: each axis's
value list is repeated to length *n* and shuffled independently, so every
value appears as near equally as *n* allows and the axes are combined
without correlation. Infeasible `D/t` draws are rejected and redrawn.

Seeded, and the seed is in the file: `SEED = 20261010`.

### Block D — joint sample, held out (100 cases)

A second stratified draw from the same axes with a **different seed**
(`SEED + 1`), marked `block = D` in every row.

**Block D exists to be kept out of fitting.** A surrogate scored on points
it was fitted through reports its own interpolation error, not its accuracy.
Reserving the held-out block at generation time — rather than splitting the
rows afterwards — means the split cannot be chosen after seeing which points
the model finds hard.

---

## 6. What each row records

### Inputs (5)
`R`, `spacing`, `OD`, `t_wall`, `tension_mt`.

### Derived features (8)
Quantities the surrogate may use that are arithmetic on the inputs, computed
once here so that every consumer uses the same definition:
`D_over_t`, `curvature` (1/R), `I` and `A` of the section, `EI`, `EA`,
`eps_pure_bend` (`D/2R`, the zero-tension analytical strain), and
`spacing_over_OD`.

They are **features, not targets**, and they are labelled as such in the
results MD. A model given `eps_pure_bend` is being handed the physics of the
zero-tension limit for free, which is legitimate and must be visible.

### Targets (6 + 24)
`peak_strain` and where it is — `peak_strain_station`,
`peak_strain_s_station`, `peak_strain_s_material`, `peak_strain_shift` —
plus `peak_moment` and its location, `start_strain` (the first position,
which is what a single-position solve would have reported), and the
per-station envelope strain and position for all twelve stations
(`eps_SR1_env` … `eps_VR5_env`, `s_SR1` … `s_VR5`).

Column names follow `docs/dataset/dataset_plain.csv` wherever the quantity
is the same, so the two datasets can be compared row for row.

### Status and provenance (12)
`status`, `error`, `n_positions`, `n_converged`, `complete`, `seconds`,
`step`, `mode`, `material`, `zone_label`, `git_sha`, `produced_at`,
plus `case_id`, `block`, `design`, `within_paper_box`, `schema_version`.

---

## 7. Rules the run is held to

**Failures are data.** A case that diverges, truncates, or is refused by the
strain guard is recorded with its status and its reason, and the run moves
on. It is never silently dropped. A dataset that quietly contains only the
cases that converged is biased toward the easy corner of the parameter space
and says nothing about where the method stops working — and *where it stops
working* is exactly what a surrogate's user needs to know. The results MD
states the failure rate and lists the failures.

**Checkpointed after every case.** One JSON object appended per case, so an
interrupted run leaves a complete, usable file rather than nothing.

**"It ran" is not verification (G8).** Block A is the gate. Beyond it, the
results MD is required to report: the anchor reproduction, the completion
rate, the failure list, the monotonicity of each OFAT curve against the
direction physics requires, and any case whose peak strain runs past the
material table.

**Nothing in the mirror or the kernel is touched.** G6 (`nlfea_v4.py` frozen)
and G7 (`component_spec.py`, `ils_builder.py`,
`fixtures/standard_ils_layouts.json` never edited) hold. This dataset adds
one script in a new folder and two documents; it changes no physics.

---

## 8. What this dataset is not

It is **plain pipe only**. Every in-line-structure family — GD-TP, the
shroud archetypes, EA-ST, EA-SB, the GD-Simple reductions of §6 — is out of
scope here and has its own apparatus.

It is **not validation**. Nine rows are anchors against published values and
the rest are predictions, most of them well outside the papers' envelope.
The `within_paper_box` flag is there so a consumer can tell the difference
without reading this file.

It carries the **known offsets of the program it was run on**, and they are
not small: §1 of the ledger reads +18.9 / +7.1 / −7.3% against Paper 1's
TABLE X, and about **double the paper's own excess over pure bending** on
TABLE XI. A surrogate fitted here reproduces *this program*, not the
papers and not the sea. That is the correct target — a surrogate exists to
be cheaper than the solver it imitates, not more right than it — but it has
to be said out loud.

---

## Action log

| | |
|---|---|
| 10 Oct 2026 | Plan written. Six anchor cases run first and all six reproduce the ledger, so the plan's gate is already green before the matrix starts. |

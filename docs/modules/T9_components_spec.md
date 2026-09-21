# T9 — Inline components: GD-TP, GD-SH, GD-TP + GD-SH

**Target set 21 Sep 2026**, immediately after M1 (plain pipe) was closed.
This document is the TARGET REGISTER: the paper's cases, their numbers, and
what the rebuild must do to reach them. It exists because M1 cost a day to
working out which of three number sets was the benchmark, and that must not
happen a second time.

---

## 1. The mapping — paper series to repo component

The paper never uses the codes `GD-TP` or `GD-SH`; those are this project's.
The mapping is by MECHANISM, and it is:

| Paper series | Paper type | Repo code | Repo class | Status |
|---|---|---|---|---|
| 1 | — | — | plain pipe | ✅ M1 closed |
| 2 | A1, thick pipe **with transition** | `GD-TT` | `TaperedThickBody` | not in this target |
| 3 | A1, thick pipe **body only** | **`GD-TP`** | `ThickPipeBody` | **target** |
| 4 | B1, **offset element** | **`GD-SH`** | `OffsetShroud` | **target** |
| 5 | C1, **offset + thick pipe** | **`GD-TP` + `GD-SH`** | archetype `ILS-SHTP` | **target** |

`ILS-TP`, `ILS-SH` and `ILS-SHTP` already exist as EDAS archetypes, are
geometry-verified by `test_edas_archetypes.py`, and **all three build a
model, build a Problem and solve step 1 today** (probed 21 Sep 2026: 124 /
123 / 124 nodes, 11 contacts each, status ok). The machinery is not the
obstacle.

---

## 2. THE TWO TARGETS ARE NOT EQUALLY REACHABLE — read this first

The paper labels every result with the PHASE it occurs in (TABLE VIII):

  * **Phase 1** — plastic bending at the tensioner and first roller boxes,
    completing within the first two. Peak strains for plain pipe.
  * **Phase 2** — elastic bending as the pipe **slides over** the
    mid-stinger rollers, a repeating bend-unload cycle.
  * **Phase 3** — free departure beyond the last roller.

| Series | Component | Paper's results are | Needs |
|---|---|---|---|
| 3 | GD-TP | **Phase 1** | a single lay position — **what T5 already does** |
| 4 | GD-SH | **Phase 2**, every row | **the sliding sweep** — T6 / L7 / M5, NOT BUILT |
| 5 | GD-TP + GD-SH | **Phase 2**, every row | as Series 4 |

**So GD-TP is reachable now and the other two are not.** Series 4 and 5 are
gated on the study layer, which does not exist yet. Attempting them from a
single-position solve would produce a Phase 1 number and compare it against
a Phase 2 target — a wrong answer that converges, which is the exact failure
mode G8 exists for.

Recommended order: **GD-TP first**, then T6 (the sweep), then GD-SH and the
combination.

---

## 3. Targets — Series 3, GD-TP (TABLE XIX, TABLE XX)

Pipeline 406.4 mm OD × 21 mm WT. Thick section length **1000 mm (~2.5D)**.
Tension **100 MT** — NOT the 120 MT of the plain-pipe benchmark. Peak occurs
at the **pipe-to-component junction**, Phase 1, 2nd stinger roller.

| Case | WT | ratio | R = 70 m | R = 85 m | R = 100 m |
|---|---|---|---|---|---|
| A1 | 32 mm | 1.5× | 0.562% | 0.473% | 0.339% |
| A2 | 42 mm | 2.0× | 0.647% | 0.508% | 0.358% |
| A3 | 53 mm | 2.5× | 0.727% | 0.556% | 0.425% |
| — | plain | 1.0× | 0.46% | 0.38% | 0.32% |

Note the radii are 70 / 85 / **100**, not 105. The paper is internally
inconsistent about this (§4 of the T5 spec records the same conflict).

## 4. Targets — Series 4, GD-SH (TABLE XXXI), all Phase 2, peak at region X2

| Config | V | L1 | L2 | X2 strain |
|---|---|---|---|---|
| R=70, T=120 MT | 1.0D / 1.5D / 2.0D | 5D | 2.5D | 0.808 / 0.970 / 1.15% |
| R=70, T=100 MT | 1.0D / 1.5D / 2.0D | 10D | 5D | 0.76 / 1.03 / 1.23% |
| R=85, T=100 MT | 0.75D … 3.0D | 10D | 2.5D | 0.62 / 0.70 / 0.95 / 1.20 / 1.51 / 1.80% |

Regions (TABLE XXIX): X1 upstream taper, **X2 deep section catenary-side
third — peak in every case**, X3 midspan (65–75% of X2), X4 vessel side, X5
downstream taper.

## 5. Targets — Series 5, GD-TP + GD-SH (TABLE XXXIX), Phase 2

Fixed: shroud L1 = 10D, L2 = 2.5D, V = 1D; R = 85 m, T = 100 MT.

| Case | Thick pipe | X2 strain | vs baseline | Peak location |
|---|---|---|---|---|
| B1 ref | shroud only | 0.70% | — | — |
| 1 | 5D | 0.952% | +36% | pipeline body at X2 |
| 2 | 10D | 1.26% | +80% | pipe-to-component junction at X2 |

---

## 6. BLOCKER FOUND BEFORE ANY RUN — the paper thickens INWARD, we thicken OUTWARD

TABLE XIX holds **OD at 406.4 mm for all three cases** and varies WT, so the
paper's thick section keeps its outside diameter and loses bore.

`component_spec.ThickPipeBody` does the opposite, and does it deliberately:
Sec.1.3 makes **constant bore** the governing rule, `t_comp` the free
variable and `OD_comp = ID + 2·t_comp` a read-only consequence — passing
`OD_comp` is a `TypeError`. Second moment of area, computed 21 Sep 2026:

| Case | t | paper: OD fixed | ours: bore fixed | I ours / I paper |
|---|---|---|---|---|
| A1 | 32 mm | I/Ip = 1.403 | I/Ip = 1.664 | **1.186** |
| A2 | 42 mm | I/Ip = 1.708 | I/Ip = 2.363 | **1.384** |
| A3 | 53 mm | I/Ip = 1.984 | I/Ip = 3.248 | **1.637** |

**Our component is 19 / 38 / 64% stiffer than the paper's at the same
nominal wall.** These are different components, and the whole of Series 3 is
a study of exactly that stiffness. Running GD-TP against TABLE XX as it
stands would disagree for a reason that has nothing to do with the solver.

A larger OD also lifts the pipe centreline off the roller — the GD-SH
mechanism leaking into a GD-TP case, which Series 3 is specifically designed
to isolate from.

### Three routes, none taken here

1. **Declared section.** `bind_sections`' `'declared'` rule already takes an
   element section verbatim (`e.section.OD`, `e.section.t`), so a
   constant-OD thick span can be modelled without a component at all and
   without touching the mirror. Cheapest, and it reproduces the paper.
   Loses the component's own geometry, contact surface and provenance.
2. **Upstream change** to `component_spec.py` adding a constant-OD mode.
   `component_spec.py` is MIRRORED and must never be edited here (G7), so
   this is a PR against Slay-ILS-Designer-V1.0, like CUN-001 and the GD-SB
   fix. Correct, and slow.
3. **Accept the difference** and compare trends rather than values. Honest
   only if stated on every number, and it abandons TABLE XX as a benchmark.

**Not chosen.** It changes what the component IS, which is a modelling
decision.

---

## 7. What is already in place

  * `ThickPipeBody` and `OffsetShroud` exist, parameterised, in the mirror.
  * `ILS-TP` / `ILS-SH` / `ILS-SHTP` archetypes build, mesh and solve.
  * T4 carries both mechanisms: `bind_sections` handles the section step,
    and `contact_targets` already computes the shroud's centreline `lift`
    from `assembly.contact_at`, combined by the assembly's LOWEST-surface
    rule rather than summed (tracker item 18).
  * The staged four-step sequence (L053) reproduces the reference program
    on plain pipe and is the sequence these cases should use.

## 8. What is missing

  * The paper's parametric cases are not the EDAS archetypes. The
    archetypes are geometry fixtures at their own dimensions; Series 3 needs
    components built to 32 / 42 / 53 mm × 1000 mm.
  * Component PLACEMENT along the stinger is not settled here. The
    reference put the component centre at `x_sr2 + L_comp/2`; the paper says
    the peak is at the 2nd stinger roller. Position sensitivity is itself
    one of the paper's parameters.
  * **The sweep does not exist.** T6 / L7 / M5. Series 4 and 5 are gated on
    it.

---

## Action log

| Date | Action |
|---|---|
| 21 Sep 2026 | Target register written. Paper series mapped to repo codes by mechanism. Series 3 (GD-TP) is Phase 1 and reachable with T5 as built; Series 4 and 5 are Phase 2 in every row and gated on the unbuilt sweep. All three archetypes confirmed to build, mesh and solve step 1. One blocker found before any run: the paper holds OD constant and thickens inward while `ThickPipeBody` holds bore constant and thickens outward, making our component 19–64% stiffer at the same nominal wall. Three routes recorded, none chosen. |

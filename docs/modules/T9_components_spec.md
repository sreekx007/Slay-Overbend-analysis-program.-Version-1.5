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

## 6. Geometry convention — CONFIRMED TO MATCH, no blocker

A blocker was raised here and **withdrawn the same day, before any run**.
The reading was that TABLE XIX's `OD (mm) = 406.4` column is the
COMPONENT's outside diameter, making the paper's thick section thicken
INWARD while `ThickPipeBody` thickens OUTWARD. It is not: **406.4 mm is the
PIPELINE's OD**, repeated in every case row as a fixed parameter — TABLE
XVII states it as "Pipeline 406.4 mm OD (16 in) × 21 mm WT" and lists the
thick section's wall and length separately as "Varies".

The paper is explicit, and agrees with the component spec:

> "…WT = 53 mm, OD = 471 mm **at constant ID = 364 mm**. The 2.54× wall
> thickness increase is **entirely outward**; it raises the roller contact
> elevation by 32 mm and increases bending stiffness by approximately
> **3.2×**" — Fig. 17

> "for the same ID and material, EI ∝ OD⁴ − ID⁴, giving approximately 3.2×
> the pipeline stiffness" — §III

`component_spec.ThickPipeBody` Sec.1.3 makes constant bore the governing
rule, `t_comp` free and `OD_comp = ID + 2·t_comp` a read-only consequence.
**That is the paper's convention exactly.** Our constant-bore computation
for the 53 mm case gives `OD = 470.4 mm` and `I/Ip = 3.248` against the
paper's 471 mm and ~3.2×.

| Case | t | OD (ours) | I/Ip (ours) | paper |
|---|---|---|---|---|
| A1 | 32 mm | 428.4 mm | 1.664 | — |
| A2 | 42 mm | 448.4 mm | 2.363 | — |
| A3 | 53 mm | 470.4 mm | **3.248** | **471 mm, ~3.2×** |

**GD-TP is unblocked.** No decision on geometry convention is required, and
the declared-section workaround is not needed.

Recorded as L054 — kept as a process lesson rather than deleted, because the
number that disproved the conflict (3.248) was sitting in the comparison
table as the supposed error. A derived quantity should be checked against
the source's own stated derived value before it is called a discrepancy.

Note the second consequence the paper draws and we must carry: the outward
growth **raises the roller contact elevation by V = OD_comp/2 − OD_pipe/2**
— 32 mm for the 53 mm case. That is the same centreline-lift mechanism
`contact_targets` computes from `assembly.contact_at`, so a GD-TP case has a
contact-surface effect as well as a stiffness effect, and they are not
separable in the geometry.

## 6b. The sliding-contact method, read off the original program

Answered from `slay_sliding_v0_4.run_passage_sliding`, run directly here on
21 Sep 2026. Everything below is measured or quoted from that code, not
inferred.

### Where the component starts

    ref_centre_x = x_sr2 + L_comp / 2          # slay_sliding_v0_4.py:479
    c1_lo, c1_hi = c1_centre -/+ L_comp / 2

`+x` is toward the vessel, so `c1_lo = x_sr2` is the **catenary-side edge**.
**At shift 0 the component's stinger-side edge sits exactly on SR2 and its
body extends back toward the vessel.** Measured for a 1.000 m component at
R = 85, 8 m spacing: `ref_centre_x = -7.4882` against `x_sr2 = -7.99`.
Overridable by passing `ref_centre_x`.

### What a shift IS, and how far it goes

Shifts are in **element units**, not metres, and are floats since v0.4:

    p = bn - shift                             # reference-grid node index
    travel_m = shift * elem_len_sr2
    elem_len_sr2 = |x_sr2 - x_sr1| / epe
    epe = round(spacing / elem_len),  elem_len default = 2 x OD

At 8 m spacing and 406.4 mm OD: `epe = 10`, **`elem_len_sr2 = 0.7988 m` per
shift unit**. Default schedule `d_shift=1.0, n_shifts=4` gives five steps,
0 → 3.195 m.

`p = bn - shift` lowers the ROLLER's target node index, so the **PIPE
advances toward the stinger**. Step 0 is special — `n_increments_step0=40`
and `pen_step0=1e8` against 20 and `1e4` for every later step — and each step
continues from the previous state.

### The ceiling, and why `n_vr` alone does not lift it

`make_slots` raises on `p < 2.0` ("shift pushes VR1 past the anchor"). The
module docstring states the limit plainly: *"the achievable sweep range is
bounded at roughly one roller-spacing no matter what n_vr is set to. Getting
more range requires sizing the vessel-side buffer itself, not just n_vr —
not implemented."* Sliding runs use `n_vr=10` against `run_slay`'s 3 purely
to buy that room. **This is the same open sweep-ceiling item T4 §6.4
records.**

### NEGATIVE SHIFTS ARE INVALID — and they fail silently

Sweeping backwards to find a worse position returns **status `ok`** with a
**6.3–6.8% peak at `x = -42.01`**, beyond SR6, in the free-tip region — a
converged-but-wrong state that then contaminates every later step, because
the sweep carries state forward and `status != 'ok'` never trips. The same
`shift = 0` reads 0.5715% from a cold start and 6.3032% after a backward
step. Forward only, from a cold start.

### For Series 3 the sweep's worst case IS the start position

A3 (53 mm), R = 85, T = 100 MT, forward sweep:

| shift | travel | peak | at x |
|---|---|---|---|
| 0 | 0.000 m | **0.5715%** | −7.99 (SR2) |
| 1 | 0.799 m | 0.5530% | −7.99 |
| 2 | 1.598 m | 0.5273% | −7.99 |
| 3 | 2.396 m | 0.5168% | −7.99 |
| 4 | 3.195 m | 0.5074% | −7.99 |

Monotonically decreasing: the component is moving away from SR2, and SR2 is
where the peak lives in every step — which is the paper's own statement
(*"Phase 1, 2nd stinger roller"*). **So Series 3 needs no sweep at all: the
governing case is the default placement at shift 0**, and that is why these
cases are reachable before T6 exists.

### Reference matrix — the original program at shift 0, 100 MT, 8 m spacing

Constant bore, `OD_comp = ID + 2t`, `L = 1.000 m`. Peak at x ≈ −7.98 (SR2)
in every case.

| Case | t | OD_comp | R = 70 | R = 85 | R = 100 |
|---|---|---|---|---|---|
| A1 | 32 mm | 428.4 mm | 0.7086% | 0.4876% | 0.3478% |
| A2 | 42 mm | 448.4 mm | 0.7877% | 0.5308% | 0.3782% |
| A3 | 53 mm | 470.4 mm | 0.8650% | 0.5715% | 0.4074% |
| | | paper | +19 to +26% | +2.8 to +4.5% | −4.1 to +5.7% |

**At R = 85 and R = 100 the original is within 6% of the paper; at R = 70 it
is 19–26% high.** That is the same R-trend divergence T5 §4 documents for
plain pipe — Abaqus amplification rises with stinger radius, the Python
toolchain's falls, and they cross near R = 80. Reproduced here in a
component case, which is evidence it is a property of the toolchain and not
of the plain-pipe configuration.

**So the rebuild's target for Series 3 is the ORIGINAL's column**, with the
paper as the secondary comparison carrying a known and documented offset —
exactly the M1 arrangement.

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
| 21 Sep 2026 | **Correction, same day:** the geometry-convention blocker below was WITHDRAWN. TABLE XIX's `OD = 406.4` is the pipeline's, not the component's; the paper thickens outward at constant bore, which is `ThickPipeBody`'s own rule. Our 53 mm case computes OD 470.4 mm and I/Ip 3.248 against the paper's stated 471 mm and ~3.2x. GD-TP unblocked; no convention decision needed. L054 rewritten as a process lesson. |
| 21 Sep 2026 | Target register written. Paper series mapped to repo codes by mechanism. Series 3 (GD-TP) is Phase 1 and reachable with T5 as built; Series 4 and 5 are Phase 2 in every row and gated on the unbuilt sweep. All three archetypes confirmed to build, mesh and solve step 1. One blocker found before any run: the paper holds OD constant and thickens inward while `ThickPipeBody` holds bore constant and thickens outward, making our component 19–64% stiffer at the same nominal wall. Three routes recorded, none chosen. |

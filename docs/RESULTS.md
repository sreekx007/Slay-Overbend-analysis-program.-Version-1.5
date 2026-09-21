# SLAY Overbend — Results

**All measured results, with the program that produced each one.**

Every number here was produced by running code in this repository on the
date shown. Nothing is quoted from memory. Where a number is taken from the
source paper it is labelled as such and is a TARGET, not a result.

---

## Provenance

| | |
|---|---|
| **Date** | 21 September 2026 |
| Repository | `Slay-Overbend-analysis-program.-Version-1.5` |
| Branch | `claude/program-rebuild-status-bya72s` |
| Commit at time of writing | `5e67a7a` (63 commits) |
| Rebuild status | T0–T5 complete; T6 (study/sweep) not built; T9 scoped |
| Test suite | 425 passing, layer linter clean |
| Registers | `BUILD_LESSONS.yaml` 58 entries · `TRIAL_LOG.yaml` 15 entries |

### Which program produced which result

The rebuild has **no sweep driver** — `slay/solve/passage.py` is the port of
the reference's per-position solver only. So:

| Section | Produced by |
|---|---|
| §1 plain pipe, single position | **REBUILD** — `tools/stage_run.py` |
| §2 plain pipe, sequential sliding | **ORIGINAL** — `slay_sliding_v0_4.py` via `tools/slide_plain.py` |
| §3 thick component (GD-TP) | **ORIGINAL** — `slay_sliding_v0_4.py`, `slay_overbend_v1_50.py` |

Reference programs, unmodified (G6): `nlfea_v4.py` (frozen kernel),
`slay_overbend_v1_50.py` (`run_slay`, single position),
`slay_sliding_v0_4.py` (`run_passage_sliding`, sliding).

### Standing configuration

406.4 mm OD × 21 mm WT unless stated · roller radius 300 mm · mesh
2 × OD unless stated · `config.ROLLER_SPACING = 9.0 m` (the paper's), but
**every comparison against the reference program is run at 8 m**, which is
the reference's own `SO.SPACING`. Spacing is stated on every table below.

---

## 1. Plain pipe, single position — REBUILD

### 1.1 The staged four-step sequence vs the reference program

`tools/stage_run.py`. Steps: displacements (elastic, all rollers
bidirectional) → gravity (lift-off active) → 120 MT tension → J2. Results
exclude SR5/SR6/SR7. **8 m spacing, J2 both sides.**

| R | rebuild, staged | `run_slay` | delta | peak |
|---|---|---|---|---|
| 70 m | 0.5179% | 0.5271% | **−1.7%** | SR2–SR3 span, both |
| 85 m | **0.3884%** | **0.3937%** | **−1.3%** | same |
| 105 m | 0.2879% | 0.2903% | **−0.8%** | same |

**Within 1.7% at every radius.** This is M1's question — does the rebuild
behave like the old program — and it is answered.

At the paper's 9 m spacing: 0.5423 / 0.4014 / 0.2942% against the paper's
0.46 / 0.38 / 0.32 (+18 / +6 / −8%), which reproduces the documented
Python-vs-Abaqus R-trend divergence rather than removing it.

### 1.2 Single proportional solve, for contrast

Same case, no staging, D6 end condition, 8 m: 0.6390 / 0.4571 / 0.3216% —
**+15 to +21%** above the reference with the peak displaced to SR6. Staging
is what closes that gap.

### 1.3 Gravity only, before and after the contact-normal fix (L048)

No tension, 9 m spacing. The defect left strain nearly independent of
stinger radius:

| R | before | after | analytic `D/2R` | after, over analytic |
|---|---|---|---|---|
| 70 m | 0.2617% | **0.3365%** | 0.2903% | +15.9% |
| 85 m | 0.2704% | **0.2751%** | 0.2391% | +15.1% |
| 105 m | 0.2428% | **0.2099%** | 0.1935% | +8.5% |

After the fix strain falls with R, as `D/2R` requires.

---

## 2. Plain pipe, sequential sliding — ORIGINAL

Step 6 of the physics sequence. Travel **4 × OD** in **1 × OD** steps, five
positions, each continuing from the last. 8 m spacing, J2. Plain pipe
reaches this entry point through a **neutral component** (OD and wall equal
to the pipe's), because `run_passage_sliding` refuses a plain-pipe case.

### 2.1 By stinger radius — 406.4 × 21, 120 MT

Travel 1.6256 m in 0.4064 m steps.

| R | pos 0 | pos 1 | pos 2 | pos 3 | pos 4 | passage peak | at |
|---|---|---|---|---|---|---|---|
| 70 m | **0.5269%** | 0.5192 | 0.5088 | 0.5003 | 0.4923 | **0.5269%** | SR2 |
| 85 m | **0.3962%** | 0.3900 | 0.3815 | 0.3740 | 0.3678 | **0.3962%** | SR2 |
| 105 m | **0.2920%** | 0.2871 | 0.2831 | 0.2793 | 0.2827 | **0.2920%** | SR2 |

**Cross-check — two entry points agree.** Position 0 against `run_slay`
(J2, same case, `n_vr` 10 vs 3): −0.04 / +0.6 / +0.6%. That validates the
neutral-component device.

R = 105 **turns up** at the last position (0.2793 → 0.2827) with the peak
moving one node along — the only non-monotonic point in this block.

### 2.2 By pipe diameter — R = 70 m, 100 MT (paper TABLE XI)

All 21 mm wall. Travel and step scale with each pipe's own OD, so the
passage is 4 × OD for every pipe: 0.672 / 1.626 / 2.032 m. Mesh scales too,
giving 24 / 10 / 8 elements per roller span.

| Pipe | pos 0 | pos 1 | pos 2 | pos 3 | pos 4 | passage peak | at pos | paper | delta |
|---|---|---|---|---|---|---|---|---|---|
| 6 in (168) | 0.3397% | 0.3420 | **0.3448** | 0.3301 | 0.3254 | **0.3448%** | **2** | 0.29% | +18.9% |
| 16 in (406.4) | **0.5120%** | 0.5051 | 0.4958 | 0.4879 | 0.4808 | **0.5120%** | 0 | 0.42% | +21.9% |
| 20 in (508) | **0.6233%** | 0.6162 | 0.6064 | 0.6008 | 0.5921 | **0.6233%** | 0 | 0.54% | +15.4% |

Peak at SR2 throughout. **The 6 in pipe rises for two steps before falling**
— the only case so far whose worst position is not the start, and the reason
Step 6 exists. It is also the finest-meshed case, so physics and resolution
are not yet separated on that point.

### 2.3 By pipe diameter — R = 70 m, 0 MT

**PENDING.** These are the only rows in the paper carrying an independent
analytical check (`ε = D/2R`, gap widening with diameter: +8 / +14 / +17%).
With no tension the one-sided rollers have nothing pulling the pipe onto the
stinger, so convergence is not assumed. Result to be recorded here either
way.

---

## 3. Thick pipe component, GD-TP — ORIGINAL ONLY

The rebuild has not run these. Targets are paper Series 3 (TABLE XX);
100 MT, 1000 mm component, 8 m spacing, peak at the pipe-to-component
junction at SR2.

### 3.1 Reference program at the start position

Constant bore, `OD_comp = ID + 2t` — the paper's own convention (Fig. 17:
*"WT = 53 mm, OD = 471 mm at constant ID = 364 mm … entirely outward …
approximately 3.2×"*; our 53 mm case computes 470.4 mm and I/Ip = 3.248).

| Case | t | OD_comp | R = 70 | R = 85 | R = 100 |
|---|---|---|---|---|---|
| A1 | 32 mm | 428.4 mm | 0.7086% | 0.4876% | 0.3478% |
| A2 | 42 mm | 448.4 mm | 0.7877% | 0.5308% | 0.3782% |
| A3 | 53 mm | 470.4 mm | 0.8650% | 0.5715% | 0.4074% |
| **paper target** | | | 0.562 / 0.647 / 0.727% | 0.473 / 0.508 / 0.556% | 0.339 / 0.358 / 0.425% |
| **delta** | | | +19 to +26% | +2.8 to +4.5% | −4.1 to +5.7% |

Within 6% at R = 85 and 100; +19 to +26% at R = 70 — the same R-trend
divergence seen on plain pipe, now reproduced in a component case.

### 3.2 Sliding behaviour (A3, R = 85, 100 MT)

| shift | travel | peak |
|---|---|---|
| 0 | 0.000 m | **0.5715%** |
| 1 | 0.799 m | 0.5530% |
| 2 | 1.598 m | 0.5273% |
| 3 | 2.396 m | 0.5168% |
| 4 | 3.195 m | 0.5074% |

Reach is 3.195 m of a 7.988 m spacing — **40%**. The program refuses a shift
large enough to reach SR3, so this monotonic fall is not a maximum.

### 3.3 Mesh sensitivity (A3, R = 85, 100 MT, shift 0)

| elements across component | element length | peak |
|---|---|---|
| 1 | 0.799 m (2 × OD) | 0.5715% |
| **2** | **0.499 m (1.23 × OD)** | **0.6118%** ← ruled |
| 3 | 0.296 m | 0.6458% |
| 5 | 0.200 m | 0.6640% |
| 7 | 0.151 m | 0.6739% |

Monotonic and still climbing at 7. **The ruled 2-element mesh reads roughly
10% below where the trend is heading** — accepted deliberately. These
numbers compare cases against each other; they are not converged strain
predictions.

---

## 4. Defects found and fixed, with the numbers

| ID | Defect | Evidence | Effect of fix |
|---|---|---|---|
| L048 | Contact normals were WORLD vectors on MODEL DOFs | material point 5.18 m off its own arc while every target met to 1e-13 m | miss → 2.3 mm; strain finally falls with R |
| L049 | Lay tension pointed back toward the vessel | 10 MT of declared tension drove **5.27 MT of compression** through the deck | → +9.25 MT tension |
| L050 | `assemble` never scales loads by `lam` | 64× cutback moved the first Newton step 3.674 → 3.232 m (threshold 1.0) | wrong load-path diagnosis retracted |
| L051 | 120 MT applied to a free 9 m cantilever tip | first Newton step 3.2 m; every tension case failed at `lam=0.0000` | D6; benchmark reachable |
| L054 | *(withdrawn)* misread TABLE XIX's OD column | conventions in fact match | kept as a process lesson |
| L056 | Backward sliding returns `ok` with 6.3–6.8% at x = −42 | contaminates every later step | forward-only ruled |
| L058 | Component meshed as ONE element at 2 × OD | +16% and rising under refinement | 2-element mesh ruled |

---

## Action log

| Date | Action |
|---|---|
| 21 Sep 2026 | Document created. All results from the 21 Sep session recorded with the program that produced each. §2.3 (0 MT diameters) left explicitly pending rather than omitted. |

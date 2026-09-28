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
| Commit at time of writing | `5e67a7a` (63 commits); §5 added at `2302897`+ (28 Sep) |
| Rebuild status | T0–T5 complete; **L7 sweep and L8 passage report built and verified (28 Sep)**; T9 scoped |
| Test suite | 425 passing at creation; **481 passing at 28 Sep**, layer linter clean |
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
behave like the old program — and it is answered. A single proportional
solve reaches the same numbers (§1.2); the staging is what makes the
free-tip configuration converge at all, not what makes it accurate.

At the paper's 9 m spacing: 0.5423 / 0.4014 / 0.2942% against the paper's
0.46 / 0.38 / 0.32 (+18 / +6 / −8%), which reproduces the documented
Python-vs-Abaqus R-trend divergence rather than removing it.

### 1.2 Single proportional solve — **agrees with the staged sequence**

**CORRECTED 22 Sep 2026.** This section previously read "0.6390 / 0.4571 /
0.3216%, +15 to +21% above the reference with the peak displaced to SR6.
Staging is what closes that gap." That compared the single solve's
WHOLE-MODEL peak against the staged sequence's BAND peak — two different
quantities (L062).

At matched metrics, 8 m, 120 MT, J2:

| R | single, band | staged, band | diff | single, **whole model** | `run_slay` |
|---|---|---|---|---|---|
| 70 m | 0.5165% | 0.5179% | −0.3% | 0.6290% @ s=39.6 | 0.5271% |
| 85 m | 0.3876% | 0.3884% | −0.2% | 0.4590% @ s=39.6 | 0.3937% |
| 105 m | 0.2879% | 0.2879% | −0.0% | 0.3320% @ s=39.6 | 0.2903% |

The two sequences give the same answer. **Staging is a convergence aid, not
an accuracy gain** — it mattered when 120 MT sat on a free cantilever tip
and diverged on the first Newton iteration (L050, L051); once D6 gave the
terminal station a contact slot, the cold single solve converges too and
lands in the same place.

The whole-model column is D6's tip artefact at SR6, and it is exactly what
the reporting band exists to exclude.

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

## 5. Sequential sliding — REBUILD

*28 September 2026. `tools/slide.py`, driving `slay.study.sweep` (L7) and
`slay.report.passage` (L8). Mode A (state carried between positions), J2
plasticity, R = 85 m, 9 m spacing, 120 MT, 406.4 × 21 unless stated.*

### 5.1 The sliding is exact — plain pipe, LINEAR ELASTIC

The check that licenses everything below. The rollers impose the same
geometry at every position, so a plain elastic pipe must read the same strain
at the same **station** however far it has slid.

| Step | SR1 | SR2 | SR3 | SR4 |
|---|---|---|---|---|
| **2 × OD (one element)** | **0.079%** | **0.031%** | **0.044%** | **0.032%** |
| 1 × OD (half an element) | 4.40% | 0.83% | 0.26% | 0.04% |

*(spread = (max − min)/max across the passage)*

At a whole-element step the passage is invariant to **0.08%**. At half an
element SR1 alternates `0.1947, 0.1863, 0.1947, 0.1863, 0.1948%` — period
two, **no trend** — which is the LINEAR contact slot being softer when the
interpolated contact point falls mid-element. That closes the Hermite open
item in the T4 spec with a number: **4.4% at SR1, 0.83% at SR2** (L065).

### 5.2 GD-TP across SR2 — the envelope is step-independent

| Step | Positions | Envelope, no edge crossings | Positions | Envelope, **with** edge crossings |
|---|---|---|---|---|
| 2.0 element | 3 | 0.4715% | 5 | **0.5731%** |
| 1.0 element | 5 | 0.4772% | 7 | **0.5727%** |
| 0.5 element | 9 | 0.5482% | 11 | **0.5722%** |
| 0.25 element | 16 | 0.5678% | 18 | **0.5689%** |
| | | spread **20%** | | spread **0.7%** |

Every edge-crossing run puts the envelope at shift 1.000 m, where the
component's **leading edge sits exactly on SR2** (lead 9.000 against
s_arc 9.000). `study.sweep.critical_shifts` adds those travels to every
schedule, which is what turns a step-dependent number into a converged one —
and it finds it in 5 positions where blind refinement needed 16 (L064).

**A single-position solve at the start reads 0.4597% — 24.6% below the
envelope.** That is the argument for sliding, in one number.

### 5.3 Plain pipe by diameter — REBUILD, no component at all

*Travel 4 × OD, step 0.8128 m.*

| OD | Envelope | At station | At position | Trend after |
|---|---|---|---|---|
| 168.3 mm | 0.2916% | 8.98 m | 0 | 0.2831% by pos 1 |
| 406.4 mm | 0.4085% | 9.26 m | 0 | 0.3945 → 0.3807% |
| 508.0 mm | 0.5134% | 9.09 m | 0 | 0.5053 → 0.4942 → 0.4887% |

Peak at SR2 in all three. **Plain pipe needs no sweep for its envelope** —
there is no edge to cross, so the start position *is* the envelope. This is a
genuine bare-pipe baseline with no component present; the neutral-component
device `tools/slide_plain.py` needs for the reference program is not needed
here.

### 5.4 The monotonic fall after position 0 is not a defect

A 13%-over-4 m decay in the plain-pipe J2 passage read as a solver defect.
Four hypotheses tested and eliminated:

| Hypothesis | Test | Result |
|---|---|---|
| Lay tension not sliding with the material | re-seat it on the material under the load station | identical to 4 decimals |
| Chained penalty too soft (1e4 vs 1e8) | run at 1e4, 1e6, 1e8 | identical; targets met to 2e-9 / 2e-11 / 2e-13 |
| Terminal slot clamping onto the tip node | add a stinger-side margin so it interpolates | decay survives |
| Carried active set | reset it each position | identical; VR1, VR2 released either way |
| **Carried plastic state** | **reset it each position** | **passage flattens** — 0.4023/0.4096/0.4123/0.3964 vs 0.4023/0.3799/0.3684/0.3489 |

It is accumulated plastic strain travelling with the material as it traverses
the stinger — the effect sequential sliding exists to capture. What made it
look like a defect was reading the passage in **material** coordinates, where
the peak appears frozen at one element (s = 9.28) while its value decays.
Every number in §5 is in **station** coordinates (L063).

### 5.5 Contact surface — `R_eff`, opt-in, and what adopting it would cost

*`--contact-surface bottom`. `LayPath.R` is to the roller **centreline**, so
the pipe centreline really rides at `R + r_roller + OD/2` = 85.5032 m at
R = 85, **+0.592%**. Default stays `centreline`; every number above is
unaffected.*

Geometry, before any solve:

| | |
|---|---|
| Deck targets (θ = 0) | **exactly 0.00000** — enters through curvature, never as a translation |
| Arc targets | deepen by exactly `R_eff/R` at every station |
| Material correction `(R_eff−R)·θ` | 0 on the deck → **0.3197 m at SR7** |
| Closed form vs projection on an `R_eff` path | agree to **5e-15** |

Solved delta:

| Case | centreline | bottom | delta |
|---|---|---|---|
| Plain J2, R = 70 | 0.5531% | 0.5474% | **−1.04%** |
| Plain J2, R = 85 | 0.4086% | 0.4046% | **−0.98%** |
| Plain J2, R = 105 | 0.2978% | 0.2957% | **−0.72%** |
| Plain elastic, R = 70 / 85 / 105 | 0.3773 / 0.3161 / 0.2599% | 0.3756 / 0.3146 / 0.2589% | −0.46 / −0.50 / −0.39% |
| GD-TP envelope | 0.5727% | 0.5649% | **−1.36%** |
| GD-TP start position | 0.4597% | 0.4542% | −1.20% |

Adopting it lowers every strain by **0.4–1.4%, one-directional** — small, but
systematic, which is why it is a deliberate decision rather than a default
change.

**The first measurement said −14.51%, and that was a bug I introduced**, not
physics. `sweep.critical_shifts` was still crossing edges at the station's
`s_arc` while the slots had moved to `s_arc + (R_eff−R)·θ`, so under `bottom`
the schedule solved travels the contact never saw and the leading-edge peak
was never sampled — the envelope fell back to the trailing-edge crossing at
shift 2.000. Both now read `physics.contact.station_material`, and the
envelope lands at shift **1.053 = 1.000 + 0.053**, the SR2 correction exactly
(L066).

### 5.6 Junction extraction — GD-TP, at the passage envelope

*28 Sep 2026. `slay.report.junction`, on ILS-TP (L = 1.000 m, OD 448.4 mm on
a constant 364.4 mm bore — wall 42 mm against the pipe's 21). R = 85 m, 9 m
spacing, 120 MT, J2, mode A, at the envelope position (shift 1.000 m, leading
edge on SR2).*

**`I_comp / I_pipe` = 2.3631.**

| Location | Strain | Moment (kNm) | |
|---|---|---|---|
| Body peak (component) | **0.1336%** | 1274.7 | |
| Junction 0 (trailing), component side | 0.1265% | 1201.7 | clamped |
| Junction 0 (trailing), pipe side | 0.3297% | 1111.5 | clamped |
| −2 / −4 / −6 × OD (pipe) | 0.2927 / 0.2383 / 0.2097% | 1060.5 / 963.1 / 875.5 | |
| **Junction 1 (leading), component side** | **0.1336%** | **1274.7** | clamped |
| **Junction 1 (leading), pipe side** | **0.5727%** | **1265.7** | clamped |
| +2 / +4 / +6 × OD (pipe) | 0.5122 / 0.4157 / 0.3512% | 1224.1 / 1149.3 / 1089.7 | |

Two things fall out, and both are the reason the extraction exists:

**Moment is continuous across the junction, strain is not.** 1274.7 vs
1265.7 kNm (0.7% apart) against 0.1336% vs 0.5727% — a factor of **4.3**.
Elastic theory predicts 2.14× from the section moduli alone; the rest is
plasticity, the pipe side being well past yield (0.22%) while the component
side stays elastic.

**The governing strain is the pipe just outboard of the leading edge**, and
`j1_at_pipe = 0.5727%` *is* the passage envelope of §5.2. Recording the
component body peak alone would understate the design value **4.3×**.

Probes are interpolated within a body and never across the step; `clamped`
marks a probe the run ended before, and `s_elem` always says where the number
came from (L067).

### 5.7 Bending moment — recovery and verification

The rebuild had no moment recovery; `Result` now carries `moments` on the
same element grid as `strains`. Verified two independent ways on a plain
elastic passage:

| Check | Result |
|---|---|
| `M` against `EI/R` on the arc | oscillates 0.94–1.11 about 1.0 — real sag between discrete rollers |
| `eps_reported − κ·OD/2` along a uniform run | constant at 0.0192–0.0195% — the membrane term from tension |

The second is the stronger one: the kernel's fibre-strain recovery and this
module's fibre-moment recovery are separate code paths, and they agree
through the curvature to 1.6%.

Each Gauss point is paired with **its own** curvature and **its own** plastic
state. The reference tool carries a v1.48 fix for exactly this — pairing the
element-mean curvature with the GP0-only plastic state produced a spurious
single-element moment collapse, ~500 kNm where ~1330 kNm was right. Checked
absent here: J2 moments run 879.8 → 1187.7 kNm smoothly into the SR2 peak,
largest element-to-element jump 101.3 kNm against a 30 kNm median (L068).

---

## Action log

| Date | Action |
|---|---|
| 22 Sep 2026 | **§1.2 corrected.** The single-solve-vs-staged comparison mixed a whole-model peak with a band peak; at matched metrics the two agree within 0.3%. Recorded as L062, with L052 and L053 amended. |
| 28 Sep 2026 | **§5.6–5.7 added.** Junction extraction and bending-moment recovery. Moment continuous across a junction, strain 4.3× discontinuous; the governing strain is the pipe outboard of the leading edge, and it IS the passage envelope. L067, L068, T021. |
| 28 Sep 2026 | **§5.5 added.** `R_eff` wired in as opt-in and measured: −0.4 to −1.4% one-directional, default unchanged. A −14.51% first reading was L066, a sweep scheduling bug, not physics. T020. |
| 28 Sep 2026 | **§5 added.** Sequential sliding in the rebuild: the sliding verified exact (0.08% at a whole-element step), the GD-TP envelope made step-independent by solving the edge crossings, three plain-pipe diameters, and the passage decay traced to carried plastic state rather than a defect. L063–L065, T016–T019. |
| 21 Sep 2026 | Document created. All results from the 21 Sep session recorded with the program that produced each. §2.3 (0 MT diameters) left explicitly pending rather than omitted. |

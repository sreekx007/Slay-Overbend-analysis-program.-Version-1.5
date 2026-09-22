# SLAY — toolchain and design workflow

**What exists, what runs what, and in what order.** Written 22 Sep 2026
because the project had a build instruction, module specs and two registers,
but nothing that said "here is the chain from a component definition to a
number".

This document names things and points at them. It does not restate the
guardrails (`SLAY_BUILD_INSTRUCTION.md` §4, G1–G12) or the task cards.

---

## 1. Two codebases, and the difference matters

### The reference programs — repository root, unmodified

| File | What it is |
|---|---|
| `nlfea_v4.py` | the FE kernel. **Frozen** (G6). Beam elements, contact, R-O and J2 plasticity. |
| `slay_overbend_v1_50.py` | `run_slay` (single lay position), `run_passage`, `run_passage_v2` |
| `slay_sliding_v0_4.py` | `run_passage_sliding` (the **only** sliding implementation in the repo), `_solve_state_sliding` |
| `slay_landing_v0_1.py` | landing checks and sweeps |
| `dnv_lcc_strain_calc.py` | DNV local buckling / strain check |

These are the validation reference. Every rebuild number is compared
against them, and they are never edited.

### The rebuild — `rebuild/slay/`, eight layers

    data → define → scene → model → physics → solve → study → report → entry

A module in layer *n* may import only from layers ≤ *n*. The rule is
declared in `slay/_layers.py` and **enforced** by `tools/check_layers.py`,
which is why it is a test rather than a convention.

### The mirror — `rebuild/`, flat, never edited (G7)

`component_spec.py` and `ils_builder.py` are snapshots of
`Slay-ILS-Designer-V1.0`. They stay flat so they remain diffable, they are
hashed against `fixtures/mirror_provenance.json`, and a local edit fails a
test rather than desyncing silently. `config.py` / `slay_config.yaml` came
OUT of the mirror and **are** ours.

`ils_plotter.py` and `component_plotter.py` are **not** mirrored — they live
only in the reference clone. Plotting an ILS needs that clone on `sys.path`.

---

## 2. The design workflow, end to end

    component definition (JSON)
        │
        ├─ ils_builder.build_ils()          MIRROR — assembly, header, CoG, mass
        │      ils.extent      component footprint  (NOT the header)
        │      ils.header      the header it carries, e.g. (-6.0, +6.0)
        │      assembly.section_at(x)   OD and wall at x   → EI, EA
        │      assembly.contact_at(x)   deepest surface    → roller lift
        │
        ├─ slay.model.mesh                  L4 — discretise structural lines
        │      polyline_of / stations_of / segments_of / mesh_line
        │      mesh_component(c, line_id, target_len)   one component, standalone
        │
        ├─ slay.scene                       L3 — stinger arc, roller stations
        │      build_scene(R, spacing, n_sr, n_vr, margin, margin_vessel,
        │                  elastic_length)
        │
        ├─ slay.model.assemble.build_model(scene, ils, s_centre, target_len)
        │      L4 — header + component, four-pass merge, global numbering
        │
        ├─ slay.physics                     L5 — sections, contact targets,
        │      build_problem(model, scene, assembly, ils, shift, tension, …)
        │      loads, BCs → Problem
        │
        ├─ slay.solve.passage.solve(problem, state_in) → (Result, SolveState)
        │      L6 — Newton, contact active set, increments, cutback
        │
        ├─ slay.study.sweep                 L7 — the passage sweep
        │      sweep_length(L_comp, clear_before, clear_after)
        │      scene_for(...)  Scene with its buffer sized for the passage
        │      run(scene, ils, L_comp, step, mode='A'|'B')
        │
        └─ slay.report                      L8 — strains, peaks, DNV, plots, IO

**The frame changes twice along that chain, and both crossings are one-way
gates:**

  * ILS-local `x` (toward the vessel) → model `s` (toward the stinger):
    `s = s_centre − x_local`, in `build_model`.
  * world `(x, y)` → model `(s, y)`: `physics.frame.to_model_frame`, the
    single conversion point. Getting this wrong cost a day — see L048, L049.

---

## 3. Tools — `tools/`

### Gate

| Tool | What it does |
|---|---|
| `run_checks.sh` | **the gate**: layer linter + full test suite. Every task card passes this before it is DONE. |
| `check_layers.py` | enforces the layer dependency rule; exits non-zero on a violation |

### Model and mesh

| Tool | What it does |
|---|---|
| `run_mesher_rig.py` | **the mesher rig.** Each archetype centred on a bare beam with 6 m of plain pipe beyond each end, both ends fixed, point load at the body centre, prismatic section so the closed form is exact. Proves the mesher is invisible in the result. `--plot`. |
| `spike_mesher_rig.py` | the earlier hand-built spike the rig was validated against |

**There is no tool that meshes an ILS onto a LAY layout and shows it.** The
rig is a bare beam by design. Building that view is an open gap.

### Drawing

| Tool | What it does |
|---|---|
| `draw_layout.py` | the Scene to scale as SVG — roller stations, arc, deck. Deliberately draws **no pipe** (tracker item 27). |
| `plot_stinger.py` | the **solved** pipe on the stinger. Every coordinate a solved displacement. Peak strain marked; one-sided rollers arrowed. |

Neither draws a component. That gap is why the GD-TP placement mismatch
went unnoticed.

### Analysis

| Tool | What it does |
|---|---|
| `stage_run.py` | **the four-step staged sequence** — displacements (all rollers held) → gravity (lift-off active) → tension → J2. Runs on the REBUILD. Reproduces `run_slay` within 1.7%. |
| `slide_plain.py` | sequential sliding for plain pipe. Runs on the **ORIGINAL**. Predates `slay.study.sweep`; kept as the cross-check against it. Uses a neutral component to pass `run_passage_sliding`'s guard. |

### Archetype studies

`study_connectors.py`, `study_ea_st.py`, `study_easb.py`,
`study_east_deadband.py`, `study_east_full.py` — connector and frame
studies (GD-ST layouts, deadband gaps, ILS-EAST/EASB). **Not lay-position
sweeps.**

---

## 4. Registers — the project's memory

| File | Holds | Guarded by |
|---|---|---|
| `BUILD_LESSONS.yaml` | what was **learned** — defects, findings, rulings | `test_build_lessons.py` |
| `TRIAL_LOG.yaml` | what was **tried**, failures included | `test_trial_log.py` |
| `RESULTS.md` | every measured result, with the program that produced it | — |

Both YAML registers are schema-checked, their cross-references must resolve
and their named tests must exist. A failed trial is never deleted.

---

## 5. Mesh density — two rules, and they are not in conflict

**G10 says the pipeline mesh is 2×OD**, matching the paper's basis, and
warns against "improving" it without changing the comparison basis too.

**A component needs its own density.** A 1.000 m body at 2×OD is ONE
element, which cannot represent bending within the component, and refining
raises the peak by 16% and more (L058). The ruling of 21 Sep 2026 is **2
elements across the component, element length not below 1×OD**.

These coexist only if the two densities are set separately — the component
by the component, the pipeline by the pipeline, meeting at the junctions.
A single global `target_len` cannot satisfy both, which is the reason for
the build order in §2.

---

## 6. Known gaps

| Gap | Consequence |
|---|---|
| ~~`slay/study/` is empty~~ | **CLOSED 22 Sep 2026** — `slay/study/sweep.py` |
| ~~`build_scene(margin=)` defaults to 0~~ | **CLOSED 22 Sep 2026** — `margin_vessel` sizes the vessel-side buffer from the sweep length |
| No component-on-stinger plot | component placement cannot be checked by eye |
| `Problem.elastic_zones` carried, never read | forced-elastic end zones do not exist in practice |
| `S` / `D` connectors refused (G9) | only `F`, `W`, `P` assemble |
| GD-SH has no `pipeline` polyline | `mesh_component(c, 'pipeline')` raises; the shroud meshes on its own line |

---

## Action log

| Date | Action |
|---|---|
| 22 Sep 2026 | Created. Names the two codebases, the eight layers, the end-to-end chain from a component definition to a number, every tool, the registers, and the six known gaps. Records that G10's 2×OD and the component's 2-element ruling coexist only if the two densities are set separately. |

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
| `emit_profile.py` | **generator.** Solves a passage and writes it down as a profile artifact (three CSVs + sidecars). Draws nothing. |
| `plot_from_schema.py` | **reader.** Draws case rows, or `--profile <stem>` for the five-panel stinger figure. Imports nothing from `slay`. |
| `plot_stinger.py` | the older combined tool: solves *and* draws. Superseded for figures by the pair above (G13); kept for its solve helpers, which `emit_profile.py` uses. |

**Generating and drawing are separate programs (G13).** A figure that
re-runs the analysis cannot be checked against the run it claims to show,
cannot be pointed at an older result, and has no way to fail loudly. The
split is:

```
emit_profile.py  --archetype ILS-SH            # solve -> docs/profiles/<case_id>.*.csv
plot_from_schema.py --profile docs/profiles/<case_id>    # read -> figure
```

A quantity a figure needs and no contract carries is a **missing column**,
added to `slay.report.profile_schema` — never a solver call added to the
plotter.

### Analysis

| Tool | What it does |
|---|---|
| `stage_run.py` | **CLI** for the four-step staged sequence — displacements (all rollers held) → gravity (lift-off active) → tension → J2. The sequence itself is **`slay.study.staged`** (Mode S); this is argument parsing and printing. Reproduces `run_slay` within 1.7%. |
| `slide_plain.py` | sequential sliding for plain pipe. Runs on the **ORIGINAL**. Predates `slay.study.sweep`; kept as the cross-check against it. Uses a neutral component to pass `run_passage_sliding`'s guard. |

### Archetype studies

`study_connectors.py`, `study_ea_st.py`, `study_easb.py`,
`study_east_deadband.py`, `study_east_full.py` — connector and frame
studies (GD-ST layouts, deadband gaps, ILS-EAST/EASB). **Not lay-position
sweeps.**

`study_simple.py` — **GD-Simple**, and this one *is* a lay-position sweep.
No published counterpart: neither paper defines the component, so every
number it prints is a prediction and the useful comparisons are internal.

### GD-Simple — a composite, not a mirrored component

An elastic pipe body of the pipeline's own section, with a free modulus,
riding an offset shroud. Declared in **`slay/define/simple.py`** out of two
codes the mirror already has — a neutral `GD-TP` (`t_comp == t_pipe`, so no
section step) over a `GD-SH` — and handed to the mirrored builder.

**There is no `GD-Simple` class and there must not be one here.**
`component_spec.py`, `ils_builder.py` *and*
`fixtures/standard_ils_layouts.json` are all mirrored and hashed (G7), and
the fixture being mirrored **data** is the part easy to miss: adding an
archetype there looks like configuration rather than code, and is still a
violation. Needed upstream → raise it, don't patch.

The two things the mirror cannot carry live in our layers:

| Need | Where | Why not `stiffness_ratio` |
|---|---|---|
| a free modulus | `physics.sections`, `E_by_owner` | a ratio scales EA and EI on an **unchanged yield surface**, so the yield *strain* would move with E |
| no plasticity | `Problem.elastic_spans` | already existed, for the feedstock buffer |

The kernel already keys materials by `(E, elastic)`, so **no kernel change
was needed** and G6 stands. Regions are `Xb` (inside the body) and `Xe`
(outside it, two spans) — drawn on the **body**, never the shroud, because
their lengths are independent.

### Simplified models — reducing a layout to a GD-Simple

**Physics:** `docs/modules/T10_simplified_model_physics.md` — what is being
abstracted and why, the two routes to `EI`, what is matched and what cannot
be, the control, and what fifteen cases across three families established.


`simplify_ils.py` measures a real ILS and builds the GD-Simple that stands
in for it; `plot_simple_ils.py` draws the two together. The reduction logic
is `slay/define/simplify.py`.

```
simplify_ils.py                     # reduce -> docs/simple/<case>.json
plot_simple_ils.py                  # read   -> docs/diagrams/simple_<case>.png
```

Same split as the generator/plotter pair above (G13): the reduction is
written down, and the figure reads it.

| Equivalence | Holds? |
|---|---|
| **Length** | exact |
| **Depth** (and so the roller lift) | exact |
| **Bending** `EI` | exact — `E = E_steel · I_comp/I_pipe` on the pipeline section |
| **Axial** `EA` | **no.** One modulus cannot match both; the error is reported, +6.2% at 32 mm to +26.6% at 65 mm |

Everything is measured off the **built assembly** (`section_at`,
`contact_at`), never read from the spec — so the depth rule needs no
formula, and the same code reduces whatever the builder actually made.
Scope today is GD-TP; a tapered body, two bodies, a layout with no section
owner, and a body that owns no contact surface are each **refused by name**
with the missing rule stated.

**`L2 = 0` is unbuildable** — the exact equivalent of a GD-TP's abrupt step
is a shroud with no taper, and the mirrored `OffsetShroud.validate` refuses
it. `TAPER_MIN` is 0.1 mm, reusing `regions.FLAT_TOL`. See L111.

**An EA structure keeps its stiffness in a frame, not in the pipe wall**, so
there is no section to read it off and `simplify` refuses it by name.
`stiffness_rig.py` measures it instead — pure bending between the connector
nodes, `EI_eq = M·L/Δθ` in closed form, with linearity, boundary and
plain-pipe-control checks printed on every run. See L112 and T10.

**The control is `--E 210 --R 250`, not `--E 210`.** Where nothing yields a
non-yielding body at the pipeline's modulus must vanish, and does: Xb
0.2031% against Xe 0.2031%. The same case at R = 85 gives 0.3161% against
1.1110% — a result, not a defect. See L110.

---

## 4. Registers — the project's memory

| File | Holds | Guarded by |
|---|---|---|
| `BUILD_LESSONS.yaml` | what was **learned** — defects, findings, rulings | `test_build_lessons.py` |
| `TRIAL_LOG.yaml` | what was **tried**, failures included | `test_trial_log.py` |
| `RESULTS.md` | every measured result, with the program that produced it | — |
| `validation/VALIDATION_v<ver>_<date>.md` | the **consolidated comparison** against both source papers and the original toolchain, one row per published case. Versioned and dated, because a configuration ruling changes every number at once; `validation/README.md` names the current one and superseded files are never edited | — |

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

# S-Lay Overbend FEA Tool — Architecture and Restructuring Plan

**Version:** 1.0
**Date:** 12 Aug 2026
**Status:** Planning — not yet started

---

## 1. Purpose and Scope

The S-Lay overbend toolchain currently lives in three files that grew by accretion rather
than design:

| File | Lines | Contains |
|---|---|---|
| `slay_overbend_v1_50.py` | 3,641 | geometry, node-based solve/contact, strain/moment recovery, plotting, `run_slay`, `run_passage_v2` |
| `slay_sliding_v0_5.py` | 1,129 | a second, independently-written solve/contact loop for interpolated (sliding) contact, plus EA-ST support built this session |
| `slay_case.py` | 426 | declarative case validation — already modular, built for exactly this purpose |

`nlfea_v4.py` (2,120 lines) is the FE engine underneath both — element formulation, J2
plasticity, the tangent-stiffness assembly. It is out of scope for this restructuring:
validated independently, never edited, and every change in this plan works around it, not
in it.

This plan restructures the first three files into a layered package. The goal is not line
count — it's that a change to one concern (contact recognition, say) has one place to be
made and one place to be reviewed, and that a case run today stays reproducible after the
move.

**Objectives:**

| Objective | What it means concretely here |
|---|---|
| Single responsibility per module | Geometry code cannot call the solver; the solver cannot know about plotting |
| Bounded change impact | Fixing the contact-envelope rule should touch one file, not two (it currently touches two, and the second copy still has the bug the first copy's fix corrected) |
| Reviewable in isolation | A module small enough that a reviewer — human or AI — can hold its whole contract in mind |
| Reproducibility | Every case validated to date stays reproducible, with the actual numbers to prove it, not just "tests pass" |
| Traceability | A result traces back to the exact inputs and code state that produced it |
| Extensibility | EA-SB, P/S/D connectors, and taper geometry can be added without reopening modules that have nothing to do with them |

---

## 2. Architecture

### 2.1 Five layers

```
LAYER 5   CLI / Orchestration        slay_cli.py
LAYER 4   Problem Specification      slay_spec.py
LAYER 3   Analysis Orchestration     slay_passage.py, slay_single.py, slay_landing.py
LAYER 2   Solver Core                slay_solver.py, slay_contact.py
LAYER 1   FEA Foundation             nlfea_v4.py  (external, read-only)
```

Each layer may depend only on the layer(s) below it. Layer 3 may call Layer 2; Layer 2 may
call Layer 1; nothing calls upward. This is the actual shape of the dependency already
present in the code — the restructuring makes it enforceable rather than incidental.

### 2.2 Sidecar modules (cross-cutting, not layer-bound)

| Module | Responsibility |
|---|---|
| `slay_geometry.py` | Mesh/roller geometry, component geometry, mesh topology (§2.3) |
| `slay_postprocess.py` | Strain/moment/curvature extraction |
| `slay_plot.py` | All plotting |
| `slay_io.py` | Checkpointing, save/load |
| `config.py` | Constants and defaults |

### 2.3 Mesh topology — the one new architectural object

Every function that walks the mesh currently assumes it is a single continuous chain of
nodes. EA-ST breaks that assumption — the frame is a second chain sharing the mesh — and
four independent places had to be patched for it this session, each with its own
locally-invented answer to the same question:

- strain recovery needed a pipe-only variant (a shape mismatch — the routine emits one
  entry per node-*and*-section, not per node — was the first symptom)
- the sliding-contact coefficient routine needed the pipe's own node list, not the full
  mesh's, because it assumes node id order matches decreasing-x position
- the existing plotting routine walks elements assuming one chain and drew a spurious
  line across the whole model when a second chain was present; proxying its mesh object
  failed because it also reads precomputed per-element arrays that aren't intercepted by a
  proxy
- the frame construction itself needed nodes placed to avoid an *unintended* merge with the
  pipe (`MeshedStructure` deduplicates nodes by coordinate — this is what makes an F
  connector free, sharing a node at the connector *is* the rigid tie — but every frame node
  landing on a pipe x-coordinate merges the whole frame into the pipe, silently turning a
  two-point attachment into a continuous stiffener)

One object closes all four:

```python
@dataclass(frozen=True)
class MeshTopology:
    """Which chain each node/element belongs to, built once alongside the mesh
    and threaded through every function that walks it. Chain 0 is always the
    pipe. A single-chain (no EA-ST) run has one chain and every check below
    reduces to a no-op -- this costs nothing for the common case.
    """
    n_pipe_nodes: int
    n_pipe_elems: int
    chain_of_node: dict     # mesh-node-index -> chain id
    chain_of_elem: dict     # mesh-elem-index -> chain id

    def pipe_node_mask(self, mesh) -> np.ndarray: ...
    def pipe_elem_mask(self, mesh) -> np.ndarray: ...
```

Built in `slay_geometry.py` alongside the mesh; consumed by `slay_contact.py`,
`slay_solver.py`, `slay_postprocess.py`, and `slay_plot.py`. No function downstream of
geometry construction is permitted to build its own chain mask — if `MeshTopology` doesn't
cover a case, that's a gap in `MeshTopology` to fix centrally, not a local workaround.

---

## 3. Decision required before Phase 2: solver unification

Two solve loops exist today — `_solve_state` (node-snapped contact) and
`_solve_state_sliding` (interpolated contact). They are not simple duplicates: their slot
formats differ in shape (one constrains a single node, the other up to two, with
interpolation coefficients), and `_solve_state` carries a `k_spring` bilateral-spring
option that was deliberately *not* carried into the sliding version, after being tested and
rejected for a shroud contact-release case that produced NaN.

| | Unify into one solver | Keep two, share only what's proven identical |
|---|---|---|
| What it fixes | A fix applied once reaches both contact modes. This already failed once in practice: the contact-envelope max-vs-sum fix went into the sliding file; the node-based file still has the bug it fixes. | Duplication risk remains, managed by making the shared piece the one with the most consequence (contact recognition/release — the actual source of the historical NaN failures) rather than the whole solve loop. |
| Cost | A real design decision on `k_spring`'s fate, a rewrite of every node-based caller onto the more general (interpolated) slot format, and re-validation of both the node-based and sliding validated case sets against the merged function. | Low — extract the one function already confirmed identical (the contact-recognition/reaction test) into a shared helper; each solve loop keeps its own assembly loop around it. |

**This plan does not choose.** Record the decision in `AGENTS.md` (§7) before Phase 2
begins, dated, so a later module can't silently re-decide it. Absent a decision, Phase 2
proceeds with the lower-cost option: shared contact-recognition helper, two solve loops.

---

## 4. Target file structure

```
slay_overbend/
├── __init__.py                 public API
├── config.py                   constants, defaults
├── core/
│   ├── __init__.py
│   ├── slay_geometry.py        build_geometry, shroud_offset_at,
│   │                            EA-ST frame construction, MeshTopology
│   ├── slay_contact.py         slot construction, penalty assembly,
│   │                            envelope_at (max/sum, single source)
│   └── slay_solver.py          solve loop(s) -- shape per §3 decision
├── analysis/
│   ├── __init__.py
│   ├── slay_passage.py         run_passage_v2, run_passage_sliding
│   ├── slay_single.py          run_slay
│   └── slay_landing.py         run_landing_sweep
├── postprocess/
│   ├── __init__.py
│   ├── slay_postprocess.py     strain / moment / curvature extraction
│   └── slay_plot.py            plot_step_deformed, plot_east_step, plot_passage
├── io/
│   ├── __init__.py
│   ├── slay_io.py              checkpointing, save/load
│   └── slay_spec.py            case validation (= slay_case.py, moved)
├── cli/
│   ├── __init__.py
│   └── slay_cli.py             argparse entry point
└── AGENTS.md

nlfea_v4.py                     sibling to the package, unchanged, imported
                                 by core/slay_solver.py only

archive/
├── slay_overbend_v1_50.py      retained, not imported by anything once
├── slay_sliding_v0_5.py         slay_spec.py and the package are live
└── slay_case.py
```

Nothing else. No batch-runner, no separate plasticity module — neither is built by any
task in §5 below, so neither appears here; add either only as a deliberate scope decision,
not a name inherited from an earlier sketch.

---

## 5. Phased execution plan

### Phase 0 — Cross-cutting design (before any extraction)

| # | Task |
|---|---|
| 0.1 | Read `run_passage_sliding` end to end, unmodified, specifically to enumerate every place a chain/topology mask is currently invented ad hoc |
| 0.2 | Design `MeshTopology` (§2.3); confirm it covers every case found in 0.1 |
| 0.3 | Resolve the solver-unification decision (§3); record it in `AGENTS.md` |
| 0.4 | Adopt the regression baseline table (§6) as the only authoritative source for "did this still work" checks |
| 0.5 | Create the directory structure, `__init__.py` files, `AGENTS.md` skeleton |

### Phase 1 — Core module extraction

| # | Task |
|---|---|
| 1.1 | Extract `config.py` — every constant and default, no logic |
| 1.2 | Extract `slay_geometry.py` — `build_geometry`, `_build_geometry`, `shroud_offset_at`, the EA-ST frame-construction logic (currently inline in `run_passage_sliding`), and `MeshTopology` construction |
| 1.3 | Validate: identical output for both a plain-pipe case and an EA-ST case, before and after extraction |
| 1.4 | Extract `slay_contact.py` — slot construction, penalty assembly, `envelope_at()` with `envelope_rule` explicit (default `'max'`; `'sum'` retained only for reproducing pre-fix numbers, never silently) |
| 1.5 | Validate: regression against stored reference outputs, bit-identical under legacy settings |

### Phase 2 — Solver extraction

| # | Task |
|---|---|
| 2.1 | Per the §3 decision: extract either the shared contact-recognition helper, or the fully unified solver — not a default, the recorded decision |
| 2.2 | Extract the Newton loop, adaptive increment cutting, divergence detection |
| 2.3 | Extract plastic-state freeze/commit handling |
| 2.4 | Validate against §6 |

### Phase 3 — Analysis orchestration

| # | Task |
|---|---|
| 3.1 | Extract `slay_passage.py` — `run_passage_v2`, `run_passage_sliding` |
| 3.2 | Extract `slay_single.py` — `run_slay` |
| 3.3 | Extract `slay_landing.py` — `run_landing_sweep` |
| 3.4 | Validate the node-based and sliding benchmark cases in §6 |
| 3.5 | Validate the three EA-ST cases in §6 |

### Phase 4 — Post-process extraction

| # | Task |
|---|---|
| 4.1 | Extract `slay_postprocess.py` — strain/moment/curvature, all taking `MeshTopology` |
| 4.2 | Extract `slay_plot.py` — required to use `MeshTopology` directly rather than reintroduce a bespoke EA-ST view; that bespoke rewrite was the direct consequence of the plotting routine not having this concept available |
| 4.3 | Validate: regenerate the plots in §6, visual check plus peak-value check |

### Phase 5 — IO and specification

| # | Task |
|---|---|
| 5.1 | Move `slay_case.py` to `io/slay_spec.py` |
| 5.2 | Add YAML case loading |
| 5.3 | Extract `slay_io.py` — checkpointing, save/load |
| 5.4 | Add per-position checkpointing for long sweeps |
| 5.5 | Validate: a long sweep with checkpointing, resumed mid-run, matches an uninterrupted run |

### Phase 6 — CLI and integration

| # | Task |
|---|---|
| 6.1 | `slay_cli.py` with `argparse` |
| 6.2 | `--case`, `--batch`, `--mode` options |
| 6.3 | `--checkpoint` support |
| 6.4 | Validate: every case in §6, run via CLI, matches its reference value |

### Phase 7 — Documentation and cleanup

| # | Task |
|---|---|
| 7.1 | Finalize `AGENTS.md` |
| 7.2 | `README.md` with quick-start |
| 7.3 | Move the three original files to `archive/` — kept, not deleted |
| 7.4 | Final pass: every case in §6 matches, fresh-solved, not cache-replayed |

---

## 6. Regression baseline table

The only authoritative source for "did this change break anything." Every number below has
a documented origin; none is copied from a session log without checking whether it was
later superseded.

| Case | Expected | Notes |
|---|---|---|
| A1, R=70m | 0.874% | Stable across repeated re-verification |
| A1, R=85m | 0.540% | Requires ≥3 elements across the component length (1×OD mesh) — at the coarser 2×OD default this drops out almost entirely, since the wall-thickness effect needs at least that much resolution to show up. Check the element count inside the component before trusting this number, not just that the run completes. |
| B1, S2-4 (shroud only) | 1.0764% | Structurally guaranteed regardless of unrelated changes — verify after every edit as a cheap canary |
| B1, SR5 (sliding) | **1.4028%**, full sweep (9/9 steps), peak at shift 1.50 | The sliding result — this is the number that supersedes an earlier node-based result which stopped 2 steps short of the true peak and under-reported it by about 5%. If a future check reports something near the old, lower figure, that's a sign the sweep is truncating early again, not a sign the physics changed. |
| Plain pipe | 0.494% at R=70m / 0.384% at R=85m / 0.316% at R=100m | Three distinct values, not interchangeable — always state R alongside this number |
| EA-ST F1, kT=2.52×EI | **0.385%**, bit-identical to plain pipe | Expected equality, not approximate agreement: a single shared connector node adds no bending continuity to the pipe, so F1 and plain pipe should be the same run in every respect that matters |
| EA-ST F2, P_c1=10D, kT=2.22×EI | X_c=0.624%, X_i=0.112%, X_e=0.437% | Contact taken at the assembly's bottom surface, roller-centreline-corrected radius. Runs 33–40% below the equivalent Abaqus reference on X_c/X_e and correspondingly high on X_i — open, attributed to the frame currently being modelled as a straight collinear beam rather than a portal with legs, so it carries no axial (truss) stiffness |
| EA-ST F2, P_c1=20D, kT=2.85×EI | X_c=0.848%, X_i=0.145%, X_e=0.483% | Same caveat. Additionally: this connector span (8.13m) sits within 5% of the roller spacing (8.0m), so both connectors land on adjacent rollers — a special configuration, not representative of generic F2 behaviour |

---

## 7. `AGENTS.md` — standing rules for anyone (human or AI) working in this package

```markdown
# S-Lay Overbend FEA Tool — AI Assistant Guidelines

## Module responsibilities

| Module | Owns | Excludes |
|---|---|---|
| slay_geometry.py    | mesh/geometry, MeshTopology         | solver, physics, postprocess |
| slay_contact.py     | slot construction, penalty assembly,
                        active set, envelope_at              | geometry construction, Newton loop |
| slay_solver.py       | Newton loop, increment cutting,
                        divergence detection                 | contact geometry, postprocess |
| slay_passage.py      | orchestration, state chaining        | mesh building, Newton internals |
| slay_postprocess.py  | strain/moment extraction, curvature   | plot rendering, IO |
| slay_plot.py         | plot generation                       | strain/moment computation |
| slay_io.py           | checkpointing, save/load              | any solver code |
| slay_spec.py         | case validation, provenance           | any physics |

## Standing rules

### Mesh topology
- Any function walking mesh nodes/elements takes a MeshTopology, or is
  provably single-chain and says so in its own docstring.
- Do not invent a new pipe/frame mask locally. If MeshTopology doesn't
  cover a case, fix MeshTopology -- that is a central gap, not a local one.

### Solver unification
- The Phase 0.3 decision (see plan §3) is recorded here once made, with a
  date. Do not let a later change silently re-decide it.

### Regression baselines
- Plan §6 is the only authoritative baseline table. A number from a
  session log or a comment is not authoritative on its own -- check
  whether §6 has superseded it (this happened once already: an earlier
  sliding-contact result was later found to have stopped short of the
  true peak, and §6 records the corrected value).

### Review requirement
- No module change is complete on a passing structural check alone.
  Every change requires an actual before/after number on a named §6
  case, freshly solved -- not replayed from a cached result, and not a
  bare pass/fail. A "the solve ran without error" check is not
  sufficient: this codebase has a documented silent-failure mode
  (phase1_peak=0.0, no exception raised) that such a check would not
  catch.

### General
- All imports at module top; no circular imports.
- Type hints and docstrings on every public function.
- No `import slay_overbend_v1_50` inside any module in this package --
  that file is archived, not a dependency.
- All constants come from config.py.
- No global state, except an explicit, isolated debug flag.
```

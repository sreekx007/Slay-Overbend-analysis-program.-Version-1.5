# rebuild/

The S-lay overbend program's new architecture, replacing the monolithic
`slay_overbend_v1_50.py` / `slay_sliding_v0_4.py` / `nlfea_v4.py` at the repo
root (kept as reference, untouched).

## What lives here vs. what doesn't

`component_spec.py`, `config.py`, `slay_config.yaml`, and `ils_builder.py`
are **mirrored** from
[`sreekx007/Slay-ILS-Designer-V1.0`](https://github.com/sreekx007/Slay-ILS-Designer-V1.0)
(`plotters/`), at commit `200667052e52a6f8b1b51fe4d2b2862946c65387`
(2026-09-10). That repo owns the ILS/component geometry model, an
assembly-validation layer, and a much larger RAG/knowledge-graph design
framework (EDPR/EDES/EDAS/EDIKB) built on top of it -- none of which is
duplicated here.

`ils_plotter.py` / `component_plotter.py` (the drawing layer) were left in
the source repo, not mirrored -- nothing here needs them yet.

`slay/model/mesh.py` is NOT mirrored -- it's this repo's own, recovered after
being thought lost (built 20-27 Aug 2026, found again 10 Sep 2026 via chat
history rather than any backup). It discretises a component's structural
lines into beam elements: arc-length coordinates throughout (never x/y
projection, which silently zeroed or foreshortened sloped/vertical members
in an earlier draft), snap-before-grade ordering, and per-segment
`MeshAdvice` honoured exactly (a taper asking for `min_elements=2` gets 2,
never averaged against the rest of the component). Verified against the
current `component_spec.py`: GD-TT's taper grading, GD-ST's closed-loop
frame, and GD-VLV's branching stem all mesh correctly with no changes
needed.

This repo's own job, per `ils_plotter.py`'s own stated scope boundary in the
source repo ("does NOT draw the lay pipeline, the stinger, the rollers, or a
passage sequence -- those belong to a SLAY-tier plotter"), is the layer the
other repo deliberately does not own: **stinger geometry, roller contact,
mesh generation, and the nonlinear solver** -- consuming `component_spec` /
`ils_builder` output rather than reimplementing it.

## Staying in sync

These four files are a snapshot, not a live dependency -- update by re-diffing
against the source repo's `plotters/` directory when it moves, not by editing
them here directly unless the change is genuinely specific to this repo's use
of them.

## The solver-side architecture plan (recovered 11 Sep 2026)

`docs/SLAY_ARCHITECTURE_AND_RESTRUCTURING_PLAN.md`, `docs/SLAY_FRESH_BUILD_SPEC.md`
and `docs/SLAY_FRESH_BUILD_TASKLIST.md` are the actual planning documents for
exactly this repo's job -- dated 12 Aug 2026, so they predate `component_spec.py`
(13 Aug onward) and were written before the ILS/solver split became explicit,
but the architecture they define IS this repo's side of that split. Read
`SLAY_FRESH_BUILD_SPEC.md` first.

**Resolved decisions worth knowing before writing more code here:**
- Solver rebuilds from `_solve_state_sliding` only (interpolated/sliding
  contact); the node-snapped path is retired, not reproduced.
- Two sweep modes, not the old code's three: **Mode A** (`slay_passage.py`,
  chained passage, plastic state carried step to step, J2 only -- "what does
  the component actually experience along one continuous path") and **Mode B**
  (`slay_check.py`, independent position check, no history, J2 or RO, full
  exhaustive sweep -- "what is the worst position anywhere, regardless of
  whether a real lay would ever traverse it"). `slay_landing.py` is a thin
  wrapper over Mode B.
- The solver only implements F-type EA-ST connectors (F1/F2). P/S/D are
  defined in `component_spec.py`'s `ConnectionSystem` but the solver isn't
  built for them yet -- `docs/reference/slay_case.py` refuses those cases
  explicitly rather than silently substituting F.
- `docs/SLAY_ARCHITECTURE_AND_RESTRUCTURING_PLAN.md` §6 has a **real
  regression baseline table** (A1/B1/plain-pipe/EA-ST F1/F2 cases with actual
  expected strain percentages) -- the authoritative target once a solver
  exists here to check against.

**Already satisfied by files already in this directory:**
- `config.py`'s spec (`docs/modules/config_py_spec_FINAL.docx`,
  `docs/diagrams/slay_config_loader_flow.mermaid`) is fully met by the
  mirrored `config.py`/`slay_config.yaml` above -- same loader algorithm,
  same one-sided-roller rule, same `n_vr=3`/`alpha_DNV=1.300` corrections.
  Stage 1.1 of the task list is done.
- `docs/reference/slay_case.py` is real, working case-validation code (not a
  stub) and is meant to become `slay_spec.py` per the task list's Stage 5.1
  -- deliberately left un-renamed and un-integrated for now, matching its own
  upload map's instruction not to mix reference code into the built package
  before its stage comes up.

**One thing to reconcile, not yet decided:** the plan's `MeshTopology`
(§2.3 of the architecture doc -- a single chain-of-node/chain-of-element
dict distinguishing the pipe chain from an EA-ST frame chain) predates
`slay_mesh.py`, which solves the same problem differently: each structural
line meshes independently (`LineMesh` per `line_id`, `MeshElement.owner`
already tracks which component an element belongs to) and lines are joined
only at explicitly declared `junctions()`. This may make a literal
`MeshTopology` object redundant rather than a prerequisite -- worth deciding
before `slay_geometry.py`/`slay_contact.py` are written, not after.

## What's next

Per the task list, `slay_geometry.py` is next (Stage 1.2): stinger/roller
reference geometry, arc-length node placement (tracker item 16), and
per-roller contact offset resolved by ownership -- feeding `slay_mesh.py`
rather than reinventing meshing inside it. After that: `slay_contact.py` and
`slay_solver.py` (Stage 2), built from `_solve_state_sliding` in
`slay_sliding_v0_4.py`, then `slay_passage.py`/`slay_check.py` (Stage 3).

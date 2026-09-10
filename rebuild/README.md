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

## What's next

No mesher or solver exists yet on this architecture, in either repo. That is
the actual next piece of work: stinger arc geometry, arc-length node
placement (tracker item 16), the sliding-contact penalty formulation, and a
mesh that honours each component's `MeshAdvice`/`ContactAdvice`.

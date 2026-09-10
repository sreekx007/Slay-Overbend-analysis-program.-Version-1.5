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

`slay_mesh.py` is NOT mirrored -- it's this repo's own, recovered after
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

## What's next

The mesher (`slay_mesh.py`) exists and works, but it meshes one component's
own structural line in isolation -- it has no notion of the stinger, rollers,
or a full assembly's contact envelope. No solver exists yet on this
architecture, in either repo. The next piece of work is stitching an
`Assembly`'s components onto one full pipeline mesh (stinger side +
vessel side), stinger arc-length node placement (tracker item 16), and the
sliding-contact penalty formulation feeding off `Assembly.contact_at()`.

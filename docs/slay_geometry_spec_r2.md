# Module: slay_geometry.py -- Specification (Round 2)

**Status:** DRAFT -- for review, not yet agreed
**Supersedes:** slay_geometry_spec_r1.md
**Date:** 13 Aug 2026
**Companion to:** SLAY_ARCHITECTURE_AND_RESTRUCTURING_PLAN.md §2.3 (MeshTopology),
SLAY_FRESH_BUILD_SPEC.md (Layer 2 script list), Phase 0.1 enumeration,
`component_spec.py`, `COMPONENT_GEOMETRY_DEFINITIONS.md` v5.0

---

## What changed since Round 1

Round 1 was written without having read `component_spec.py`. That was a
mistake in sequencing -- `component_spec.py` already solves a problem Round 1
was about to solve badly a second time. This round narrows `slay_geometry.py`'s
job considerably and adds EA-SB (Base Structure) and EA-O (Offset Shroud) to
its scope, because both are already fully defined, geometrically, in
`component_spec.py` -- there is no reason to wait on them.

### The single biggest change: contact ownership is not this module's job

Round 1 had this module deciding, itself, "which surface does a roller
touch, given a shroud and a thick body might overlap." That logic already
exists, is already correct, and is already tested conceptually: it's
`Assembly.contact_at()` in `component_spec.py`, with an explicit, named
choice between two ownership policies (`LOWEST` -- deepest surface wins;
`STRICT` -- refuse to guess if more than one component claims a station).
`slay_geometry.py` must **consume** an `Assembly`, not reimplement any part
of what it does. Concretely: this module asks the assembly "what's the
contact surface at x" and "what's the pipe section at x" for every station
it needs, and builds mesh/nodes/elements from the answers. It does not carry
its own copy of the max-vs-sum overlap logic that `run_passage_sliding`
currently has inline (that inline logic is the thing being retired here).

This also directly resolves what "components with bottom surfaces below
other components" means, functionally: it's exactly `Assembly.contact_at()`
choosing the deepest (most negative `y`) claim among however many components
overlap a given x. EA-SB's bottom surface, EA-O's deep section, and a future
overlapping component all go through the same one mechanism -- there is
still only one envelope rule in the whole toolchain, but it now lives in
`component_spec.py`, and `slay_geometry.py` is one of (potentially several)
callers of it, not its owner.

## What this module owns (revised)

1. **The reference roller-station geometry** -- unchanged from Round 1:
   where every VR/SR station is, before any snapping. Pure function of
   radius, roller counts, spacing.

2. **The actual mesh** -- nodes and elements, built by subdividing the
   reference geometry, with forced exact nodes at component boundaries
   (unchanged rationale from Round 1: without this a component's modelled
   length rounds to the nearest whole element).

   **Component boundaries** for this purpose now come from the `Assembly`'s
   own components (each `Component.extent` and, where relevant, its
   `x_deep`/`x_flat` sub-boundaries) rather than being passed in as a bare
   list of numbers by the caller. The caller supplies an `Assembly`; this
   module reads out of it what needs to be exact nodes.

3. **Per-station contact geometry for the SOLVER, not the component** -- for
   every roller station, this module still needs to hand `slay_contact.py`
   the roller's own physical facts: its outward push direction, its radius.
   That is genuinely a roller fact, independent of what pipe-side component
   geometry exists at that x. Separately, and by calling the `Assembly`,
   this module resolves what elevation/offset the pipe centreline sits at,
   for every roller station, given whatever components are present --
   *that* is the `Assembly`'s answer, merely being read out at specific x
   positions (the roller stations) rather than everywhere.

4. **The shroud elevation profile as a raw function of x** -- this now
   already exists correctly as `OffsetShroud.contact_at()` in
   `component_spec.py`. **`slay_geometry.py` does not reimplement it.** Round
   1 was wrong to plan for that. If a standalone function-of-x is still
   useful for some caller that doesn't want to build a whole `Component`,
   that's a thin convenience wrapper at most, not a second implementation.

5. **The EA-ST frame** -- unchanged in substance from Round 1: builds the
   frame's own node/element chain, staggered so interior nodes never
   coincide with a pipe node's x-position, sharing nodes only at the exact
   connector positions. Connector positions themselves (`P_c1`, `P_c2`,
   system F1/F2) are read from the `TopStructure` component inside the
   `Assembly`, not from a separately-passed dict.

6. **The EA-SB frame -- new in this round.** `BaseStructure` in
   `component_spec.py` is fully defined geometrically (trapezoid below the
   pipe, `P_l1`/`P_l2`/`P_v`, `contact_at()` already returns the right
   surface with `LoadPath.CONNECTOR`), but nothing yet builds its structural
   mesh. This is new work, not a port. It needs its own frame chain, the
   same node-sharing-at-connectors mechanism as EA-ST, and -- this is the
   part EA-ST didn't need -- because `BaseStructure.contact_at()` returns
   `LoadPath.CONNECTOR`, the *reaction* has a real moment arm (`P_vt + P_v`)
   that must reach the pipe through the connector, not through a pipe
   element directly. Building the frame geometry (this module's job) is
   simpler than carrying that reaction correctly (a `slay_contact.py` /
   solver job) -- this module's job is just to place the frame body and
   expose its connector node positions and the arm distance; it does not
   decide how the arm is applied as a constraint.

7. **`MeshTopology`** -- extended from Round 1's binary pipe/frame split.
   With EA-SB now in scope in the same build, there can be *two* non-pipe
   chains present in one mesh (an EA-ST frame and an EA-SB frame both
   attached to the same pipe span is a real, expected case per the paper's
   own combined studies). This settles Round 1's open question 2:
   **`MeshTopology` uses named chains from the start** (`'pipe'`, `'ea_st'`,
   `'ea_sb'`, ...), not a numeric binary flag, because the binary version
   would need revisiting the moment EA-SB landed -- which is this same
   round. A named-chain scheme costs nothing extra now and avoids a second
   revisit.

8. **Per-roller radius lookup** -- unchanged from Round 1: keyed by roller
   name, optional override dict, falls back to `config.ROLLER_RADIUS_DEF`.
   Resolves Round 1's open question 1: the override dict is the simplest
   option and matches the existing `roller_offsets` shape; this module's own
   canonical roller-name list is still the thing the dict is keyed against.

## What this module explicitly does NOT own (revised)

- Contact ownership / overlap resolution between components (now
  `component_spec.Assembly`'s job, consumed not duplicated)
- The shroud elevation formula itself (now `OffsetShroud.contact_at()`)
- Deciding whether a roller is currently in contact, or one-sided vs.
  bilateral (`slay_contact.py`, unchanged from Round 1)
- The Newton solve, plasticity, force/stiffness calculation (unchanged)
- Plotting (unchanged)
- P/S/D connector types for EA-ST or EA-SB (F1/F2 only this round, for both
  structures now -- unchanged scope decision, just now stated for both)
- **Reading geometry parameters out of a schematic plot** -- see below.
  This module is expected to eventually support that, but it is explicitly
  NOT built in this round. It is mentioned here only so this round's design
  doesn't accidentally close the door on it.

## Forward compatibility: reading geometry from a schematic (not built now)

The eventual capability: given a standard schematic plot (as produced by
`schematic_lib.py`/`plot_schematic.py`), extract the component geometry
parameters that were used to draw it, rather than requiring them to be
typed in separately. This is explicitly future work, not built in this
round. What this round needs to do is avoid designing `slay_geometry.py` in
a way that would have to be reworked when that capability arrives.

Concretely, the thing that makes this tractable later is already true of
`component_spec.py`'s design, and this module should inherit the same
property: **components are data** (frozen dataclasses with named fields),
and drawing (`schematic_lib.py`) is a one-directional consumer of that data,
not the source of truth. A future schematic-reading capability would most
naturally live as its own module that produces a `Component`/`Assembly`
(reading a plot and inferring/reconstructing the parameters that would draw
it), which `slay_geometry.py` then consumes exactly like any other
`Assembly` -- no different code path. So the concrete design commitment
this round makes is: **`slay_geometry.py`'s inputs are `Assembly` objects,
never raw component parameter dicts passed around ad hoc.** That's the seam
a future schematic-reader plugs into. Nothing else needs to change.

## Inputs and outputs (revised)

**Inputs, roughly:**
- Stinger radius, pipe OD, roller spacing, roller counts (vessel + stinger)
- Element length target (default from `config.py`)
- An `Assembly` (from `component_spec.py`) -- may contain zero or more
  components (a bare pipe with no components is a valid, empty assembly)
- Optional per-roller radius overrides

**Outputs, roughly:**
- Mesh nodes and elements (pipe, plus any EA-ST/EA-SB frames the assembly's
  components require)
- The reference (unsnapped) station list, for shift-semantics purposes
- A per-station table of roller contact geometry: push direction, radius,
  name, and the assembly-resolved centreline offset at that station
- `MeshTopology`, with named chains (`'pipe'`, `'ea_st'`, `'ea_sb'`)
- For each frame present, its connector node positions and (for EA-SB) the
  reaction moment arm -- handed to `slay_contact.py`, not resolved here

## Open questions for this round

1. **EA-ST + EA-SB simultaneously present, at overlapping x** -- is this a
   real case to design for now (the paper does discuss combined structures),
   or can this module assume at most one of each is ever built into a
   single `Assembly` for the current phase, with a clear error if the
   caller tries two of the same kind? Leaning toward: allow one `TopStructure`
   and one `BaseStructure` at once (they don't compete for the same contact
   surface -- ST is above, SB is below -- so nothing about `MeshTopology`
   needs to change to allow both), but raise clearly if the caller supplies
   two `TopStructure`s or two `BaseStructure`s, since nothing here has
   worked out what that would even mean yet.

2. **EA-SB connector locations vs. mesh snapping** -- EA-ST's F2 connector
   positions (`P_c1` either side of centre) were already forced as exact
   nodes (Round 1). EA-SB's `x_flat` boundaries (`P_l1`/2 either side of
   centre) are a second, independent pair of positions that plausibly also
   need forcing, so the trapezoid's flat-to-slope transition lands on a
   node rather than rounding. Confirm this should be forced the same way,
   through the same snap-list mechanism, sourced from `Assembly` the same
   way as item 2 above.

3. **STRICT vs. LOWEST ownership, as this module's default** -- `Assembly`
   defaults to `STRICT` (refuse to guess). Does `slay_geometry.py` simply
   pass through whatever `ownership=` the caller set on their `Assembly`
   (no opinion of its own), or does it need a documented position on which
   default is appropriate for FEA mesh-building specifically? Leaning
   toward: no opinion -- the `Assembly` the caller constructs already
   carries this choice, `slay_geometry.py` has no reason to override it.

---

Round 1's open question 3 (F1 connector: shared node counts as plain 'pipe'
chain membership, no separate frame chain) still stands and is unaffected by
this round's changes -- restating for final confirmation alongside the new
items above.

Once this round is agreed, next step is the mermaid flowchart, covering:
build reference geometry -> read component extents/boundaries from Assembly
for snapping -> build actual (snapped) mesh -> build EA-ST frame if present
-> build EA-SB frame if present -> assign named-chain MeshTopology -> resolve
per-station contact geometry via Assembly -> expose outputs. Code follows
only after that.

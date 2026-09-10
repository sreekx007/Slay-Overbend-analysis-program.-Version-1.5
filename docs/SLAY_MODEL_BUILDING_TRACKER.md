# SLAY Model Building -- Open Items Tracker

Tracks unresolved questions and pending decisions from the model building
rebuild. Referenced from `SLAY_MODEL_BUILDING.md`. An item moves to
Resolved once settled, with the outcome recorded and the date.

---

## Open

### 28. Coordinate system is LEFT-HANDED (x right, y down) -- consequences for the solver

- **Raised:** 22 Aug 2026, 13:47 +05:30
- **Related step:** item 26 (the y-down decision itself); solver design
- **Status:** Question raised, assessment below. NOT a blocker, but the
  specific risk areas must be checked when the solver is written.

With x positive to the RIGHT and y positive DOWN, `x_hat cross y_hat` points
INTO the page, so this is a LEFT-HANDED frame in the usual convention.

**Assessment: not a problem for 2D beam FEA, PROVIDED it is consistent.**
Local element stiffness matrices are derived in each element's OWN local
frame, and the local->global transform is built from direction cosines
computed from actual node coordinates -- both work regardless of global
handedness. Strong empirical support: the OLD code already worked in
y-down (`slay_overbend_v1_50.py` L494) and its results were validated
against Abaqus.

**Where it DOES bite -- check these explicitly when writing the solver:**
1. **Rotation / moment sign.** Positive rotation about +z now appears
   CLOCKWISE on screen rather than counter-clockwise. Any DOF ordering
   (ux, uy, theta) must state which sense theta is positive in.
2. **Borrowed formulas.** Any expression lifted from a textbook or paper
   assuming right-handed axes needs its signs checked, not copied.
3. **Cross-product-derived quantities.** Curvature sign, and anything
   using a 90-degree rotation such as `n = (-t_y, t_x)`, flips sense.
   NOTE this is already live: the outward normal used on the stinger is
   `n_hat = (-sin th, -cos th)`, which gives (0,-1) = toward the surface
   at th=0 -- correct ONLY because the tangent is taken pointing toward
   the stinger tip. Reverse the tangent and the normal silently inverts.
4. **Strain/stress extreme-fibre sign.** Which fibre is "top" flips.

**Mitigation:** state the rotation sense in the solver's own glossary
(item 17 already requires a glossary per module), and add a sign
regression test -- e.g. a simply-supported beam under known load, checking
the sag direction and moment sign come out as expected.

### 27. Plotter must consume model data, never generate geometry

- **Raised:** 22 Aug 2026, 13:47 +05:30
- **Related step:** the unified plotter; items 22/26
- **Status:** PRINCIPLE AGREED. Plotter rewrite deferred until more
  components are migrated.

**The rule:** the plotter takes NODAL COORDINATES, STRUCTURAL LINES and
GEOMETRY LINES from the modeller or solver and draws them. It does NOT
compute geometry of its own.

**The failure this rule exists to prevent, found 22 Aug 2026.**
`plot_stinger.py` drew the "pipe centreline" using the STINGER ARC
FORMULA (`-R*sin(th)`, `R*(1-cos(th))`) -- i.e. it ASSUMED the pipe
conforms perfectly to the arc and drew that. Nothing computed that shape:
there is no mesh and no solver yet. Worse, even a real analysis would not
give it, because the pipe spans BETWEEN rollers -- it bridges, sags and
lifts off, touching the arc only at contact points. Deviation between
supports is precisely what the model exists to capture. The same figure
also rotated GD-ST onto the local arc tangent, which is its
POST-DEFORMATION orientation, not its as-built one.

`build_geometry_model.py` had this right (straight model on an arc-length
axis, with the draped view explicitly labelled context); `plot_stinger.py`
is where the line was crossed.

**At the geometry stage the honest content is:** stinger arc = geometric
INPUT (roller locus); roller positions = known; pipeline UNDEFORMED =
straight; pipeline DEFORMED = UNKNOWN until the solver runs.

- **To do at rewrite:** relabel the arc as the roller locus / target
  configuration, keep the pipe straight, stop pre-rotating components onto
  the arc, and drive everything from `geometry_nodes()` /
  `structural_nodes()` / `geometry_lines()` / `structural_lines()` rather
  than from formulas held in the plotter.

### 26. SIGN CONVENTION CONFLICT -- component_spec was built y-UP, everything else is y-DOWN

- **Raised / decided:** 22 Aug 2026, 12:34 +05:30
- **Related step:** every component; the plotter; eventually the solver
- **Status:** DECIDED -- adopt y-POSITIVE-DOWN throughout. Fix
  `component_spec.py` to match, not the other way round.

**The conflict, verified before deciding:**

| source | convention |
|---|---|
| `SLAY_PLOT_STYLE_v2.md` (Coordinate System, CRITICAL) | y positive = DOWN (toward seabed) |
| `slay_overbend_v1_50.py` L494 | y positive = DOWN ("X positive LEFT; Y positive DOWN") |
| `component_spec.py` AS BUILT | y positive = UP |

Concretely: `OffsetShroud.contact_at().y = -0.4064` and
`BaseStructure.y_bottom = -0.72` -- both NEGATIVE for surfaces BELOW the
pipe. Under the plot-style convention those must be POSITIVE.

**Provenance -- this was an assistant error, not an inherited one.** The
y-UP convention was introduced in the GD-TP glossary early in the
dataclass work and carried through GD-TT, GD-SH and GD-ST without being
checked against the existing analysis code -- even though L494 had already
been read earlier in the same session, while unsuccessfully trying to
derive the `dn` formula. That failed derivation is plausibly connected.

**DECISION: y-positive-DOWN wins.** Reasons: it is what the validated
analysis code and all existing plotting infrastructure already use; it is
one file to change rather than two plus a document; and depth increasing
downward is natural for a stinger.

**ALSO DECIDED: build the stinger geometry directly in the target
coordinate system** rather than analysing in one system and flipping for
plots. The plot-style doc contains a worked example of why analyse-then-
flip is dangerous: a whole CRITICAL section warning that `roller_offsets`
must be NEGATIVE for a shroud, because the radial normal points mostly
downward so a positive offset pushes the pipe DOWN THROUGH the roller.
That warning exists only because a sign has to be reasoned about at the
point of use instead of falling out of the geometry.

**Scope of the change:** inverts `contact_at().y`, `y_near`/`y_far`,
`y_top`/`y_bottom`, the geometry-node y values, every glossary sign note,
and `render_geometry_line`'s overlay. Cheap now, at four components
migrated; expensive once the mesher and solver sit on top.

- **Blocks:** GD-ST merge; any further component migration; the unified
  plotter (a plotter cannot reconcile two opposite conventions -- the
  convention must be settled first, then the plotter simply draws it).

### 25. Named connection systems (F1/F2/F1D/F2D/PS/PSD) -- confirmed patterns + slot parameters

- **Raised / confirmed:** 22 Aug 2026, 11:58 +05:30
- **Related step:** item 11 (per-side connector lists), item 8 (connector
  stiffness), GD-ST and GD-SB dataclasses
- **Status:** Patterns CONFIRMED by user. Slot-position parameters agreed.
  Implemented in `connection_systems_proposal.py` (proposal, not merged).

**Slot order (Set 2):** 1 = outer-L, 2 = inner-L, 3 = centre,
4 = inner-R, 5 = outer-R.

| system | slot 1 | slot 2 | slot 3 | slot 4 | slot 5 | connectors |
|---|---|---|---|---|---|---|
| F1  | -- | -- | F | -- | -- | 1 |
| F2  | -- | F  | -- | F | -- | 2 |
| F1D | D  | -- | F | -- | D | 3 |
| F2D | D  | F  | -- | F | D | 4 |
| PS  | -- | P  | -- | S | -- | 2 |
| PSD | D  | P  | -- | S | D | 4 |

**Note on the D variants:** "D" adds TWO connectors, one at each OUTER
slot -- not one. So F1->F1D goes 1->3 connectors and F2->F2D goes 2->4.
That is a larger structural difference than the naming suggests, and F2D
has NOTHING at slot 3.

**Connector elements are 2-NODE elements.** The PIPE-side node is ALWAYS
Fixed. The EA-side node carries the type (F / P / S / D).

**Slot positions come from TWO parameters:**
- `P_c1` -- span between slot 2 and slot 4 (the interior pair)
- `P_c2` -- offset from slot 2 out to slot 1 (and slot 4 out to slot 5)

Slot 3 is the centre by definition; slots 1/5 are placed RELATIVE to 2/4
rather than independently, so symmetry holds by construction instead of
depending on the user entering four numbers that happen to be symmetric.

Defaults tied to frame width so they scale: `P_c1 = L_top/3`,
`P_c2 = L_top/6`. VERIFIED these reproduce item 11's
evenly-spaced-excluding-endpoints layout EXACTLY (identical to 1e-12), so
the named-system parameters and item 11's explicit list agree by default
and diverge only if deliberately set apart.

**CORRECTION recorded -- a false lead worth not repeating.** Before the
patterns were confirmed, `GDSB_DEFAULT_CONNECTION_SYSTEM =
(None,'P','S',None,None)` was read as evidence that it WAS the PS system.
It is not: real PS puts S at slot 4, GDSB_DEFAULT puts it at slot 3.
`GDSB_DEFAULT` is genuinely not one of the named systems -- exactly as its
own docstring already stated. The docstring should have been trusted over
the apparent pattern match.

**EA-SB USES THE SAME CONNECTOR CONVENTIONS** (user, 22 Aug 2026). The
table above, the 2-node element rule, and the `P_c1`/`P_c2` slot
parameters all apply to `BaseStructure` as well as `TopStructure`. NOT YET
APPLIED to EA-SB -- to be corrected when GD-SB is migrated. `GDSB_DEFAULT`
should be revisited at the same time, being an informal pattern that
predates these confirmed systems.

- **Blocks:** GD-ST merge (needs these systems wired in place of
  `ConnectorLocations`/`ConnectionSystem`); GD-SB migration.

### 23. Taper meshing needs GRADING -- and the graded zone does NOT fit inside the component

- **Raised / decided:** 21 Aug 2026, 17:23 +05:30
- **Related step:** mesher design; GD-TT dataclass
- **Status:** Mesh grading AGREED as the solution. The overrun finding
  below is quantified and must be honoured by the mesher.

**The problem, quantified.** GD-TT default: `L_taper = n*dr = 0.126 m`
against a default element of `2*OD = 0.8128 m`.

| t_comp | n | L_taper | vs elem | L/OD |
|---|---|---|---|---|
| 30 mm | 4 | 0.036 m | 0.04x | 0.08 |
| 52.5 mm (DEFAULT) | 4 | 0.126 m | 0.16x | 0.27 |
| 75 mm | 4 | 0.216 m | 0.27x | 0.42 |
| 100 mm | 8 | 0.632 m | 0.78x | 1.12 |

EVERY case in the range is shorter than one default element. The DEFAULT
case (0.126 m) sits BELOW the 0.184 m sliver the old code documents as
having "made one case fail to converge entirely, and shifted another
case's peak strain by +30% from pure numerical artefact".

Three distinct problems, not one:
1. Transverse stiffness scales as `EI/L^3`, so a 6.45:1 length ratio
   becomes a 268:1 stiffness ratio between adjacent elements. Standard
   grading guidance caps adjacent size ratios at 1.5-2.0.
2. At `L/OD = 0.27` the element is ~4x stubbier than the pipe is wide --
   well outside Euler-Bernoulli slenderness.
3. Worst exactly where accuracy matters most: `L_taper = n*dr`, so a THIN
   component at the MINIMUM code taper gives the SHORTEST taper, and the
   taper is the geometry the strain-concentration argument is about.

**Honest provenance:** this is partly CREATED by the rebuild being more
rigorous than the old code. Forcing mandatory nodes at all six GD-TT
stations is what produces the sliver; the old code snapped fewer points
and got coarser-but-better-conditioned elements. A trade-off surfaced by
the rebuild, not a pre-existing bug.

**DECISION: mesh grading.** Step element sizes gradually (<= 2x per step)
approaching the taper rather than dropping one short element between two
long ones.

**CRITICAL CONSEQUENCE -- the graded zone does not fit.** Grading from a
0.063 m taper element back to 0.813 m global at 2x per step needs
0.882 m of run-up PER SIDE (`0.063 -> 0.126 -> 0.252 -> 0.504 -> 0.813`):

| side | available | needed | result |
|---|---|---|---|
| outboard (NIB) | 0.250 m | 0.882 m | overruns 0.632 m PAST THE WELD into plain pipe |
| inboard (body half) | 0.508 m | 0.882 m | overruns 0.374 m PAST BODY CENTRE |

Total grading + taper zone = 2.016 m against a component only 1.768 m
long. The graded region NECESSARILY spills outside the component both
ways, and the two inboard zones overlap through the body centre -- so in
practice the whole GD-TT span plus ~0.63 m of plain pipe beyond each weld
ends up refined. That is acceptable (refining a whole component is normal
practice; element count stays small) but it means:

**THE MESHER MUST BE PERMITTED TO GRADE OUTSIDE A COMPONENT'S OWN
EXTENT.** A mesher treating component boundaries as hard limits on
refinement cannot satisfy both `min_elements` and `max_size_ratio`, and
will silently pick one -- reintroducing the sliver or smearing the taper,
with no error raised either way.

- **Blocks:** mesher design; the element-length policy when any tapered
  component is present.

### 24. Components carry MeshAdvice and ContactAdvice for the mesher/solver

- **Raised / agreed:** 21 Aug 2026, 17:23 +05:30
- **Related step:** item 23 (the case that motivated it), item 22
  (dataclass framework)
- **Status:** AGREED, implemented in
  `mesh_contact_advice_proposal.py` (proposal, not yet merged).

Components carry ADVISORY structures FOR the mesher and contact solver.
Advisory, not prescriptive -- `component_spec` still does not mesh
anything (the boundary held throughout this rebuild). The component
declares what it knows about ITSELF that the mesher would otherwise have
to infer or guess.

**`MeshAdvice`:** `min_elements`, `max_size_ratio` (default 2.0),
`target_elem_len`, `note`. The mesher may override any of it but SHOULD
LOG when it does -- silently ignoring a `min_elements` request is exactly
how item 23's taper problem reappears unnoticed.

**`ContactAdvice`:**
- `normal_is_collinear_with_offset` -- item 21's discriminator. Recorded
  as position-dependent WITHIN a component (GD-SH: True on the flat,
  False on the tapers), so it cannot be a single per-component constant.
- `requires_node_at_contact` -- almost always False, see below.
- `arm` is STILL RETURNED even when the moment is zero. User decision
  (21 Aug 2026): keep it unused for now, because if ROLLER FRICTION is
  added later the contact force is no longer purely normal, the
  collinearity argument breaks, and the arm becomes load-bearing.

**`NodePriority` (MANDATORY / PREFERRED) -- and the useful negative
finding behind it:** CONTACT DOES NOT REQUIRE A NODE AT THE CONTACT
POINT. The sliding formulation places contact at a VIRTUAL PARAMETRIC
POINT inside an element (`slide_coeffs_x`) and distributes the constraint
to the two bracketing nodes by shape functions, so a roller may sit
anywhere along an element and forcing a node there buys nothing.

Node placement is therefore driven ONLY by SECTION/SLOPE
DISCONTINUITIES, never by contact -- consistent with item 4 (only
section-changing components need snapping; a shroud does not, because its
contact offset is evaluated continuously).

- **Blocks:** nothing -- ready to fold into the dataclasses.

### 22. Node/line interface: DERIVED from parameters, not stored -- plus the per-component line table

- **Raised / agreed:** 21 Aug 2026, 14:48 +05:30
- **Related step:** supersedes/clarifies item 20's storage rule wording;
  implements item 15's four-list framework; feeds directly into the
  dataclass work
- **Status:** AGREED. Ready to build dataclass details against.

**CORE DECISION: parameters stay authoritative; nodes and lines are
DERIVED ACCESSORS, not stored fields.**

    component.geometry_nodes()      # derived from V/L1/L2, or OD_comp, ...
    component.structural_lines()    # derived, possibly multi-segment

Every consumer -- mesher, plotter, contact resolution -- sees the uniform
node/line interface. Change `t_comp` and the nodes change automatically,
with no possibility of drift.

Reason storing nodes as fields was rejected -- it would break four things
already established:
- **Validation:** `n >= 4`, `L_NIB >= NIB_min`, `V >= OD_pipe/2` are
  parameter-level rules. A raw node list cannot express them, so they
  would stop being enforceable at construction.
- **`default_for(pipe)`:** `2.5 * t_pipe` scales to a different pipe; a
  hardcoded node list does not.
- **FREE/DERIVED discipline:** nodes are coordinates, not design
  variables. Storing both allows `t_comp` and the node list to disagree.
- **Single source of truth:** the exact failure class eliminated three
  times already this rebuild (`STD_PIPELINE` vs `config.py`,
  `envelope_at` vs `contact_at`, item 20's geometry-line rule).

**CustomComponent -- the one genuine exception, as a SEPARATE CLASS.**
Where there are no parameters to derive from, nodes ARE the definition:

    class CustomComponent(Component):
        geometry_nodes: list[tuple[float, float]]   # STORED -- is the definition
        geometry_lines: list[...]                   # STORED
        structural_lines: list[...]                 # STORED

Kept a separate class rather than a mode/flag on the existing ones, so the
six GD- components never lose validation and scaling, while custom shapes
are fully supported. The type itself states which contract applies.

**Item 20 wording clarification.** Item 20's rule ("store a geometry line
only when the contacting shape is not concentric") is loose in light of
the above. More precisely: geometry lines are ALWAYS derived from
parameters. What varies is whether a component has its OWN DISTINCT
geometry line (GD-SH, GD-ST, GD-SB, from their own parameters) or SHARES
THE PIPELINE'S (GD-TP, GD-TT, GD-PIP, derived from the section already
stored). Intent unchanged; the wording should not imply GD-SH stores raw
coordinates.

**AGREED PER-COMPONENT TABLE:**

| component | geometry line | structural line | geom line owns contact? |
|---|---|---|---|
| Pipeline | own | own | yes |
| GD-TP / GD-TT / GD-PIP | shares pipeline's | shares pipeline's | yes (via pipeline) |
| GD-SH | OWN | PIPELINE'S | yes |
| GD-ST | own | own | NO -- shape only |
| GD-SB | own | own | yes (via connector) |
| CustomComponent | stored placeholders | stored placeholders | declared |

**Two corrections applied to the first draft of this table, both
important:**

1. **GD-SH is not "no structural line" -- it is "no structural line OF ITS
   OWN".** Its `structural_line_id` must be set EXPLICITLY to `pipeline`,
   not left empty/null. If null, the solver must ask "is this a shroud?
   then use the pipeline" -- reintroducing exactly the branching item 19
   exists to remove. Set explicitly, the shroud stops being a special
   case: three components (GD-TP/TT/PIP, GD-SH, GD-ST/SB) resolve through
   one uniform lookup with no conditionals.

2. **GD-ST's geometry line never owns contact.** Geometry lines serve TWO
   distinct purposes -- (a) bounding surface / drawing the shape, and
   (b) contact surface identification. GD-ST's rectangle serves only (a);
   `contact_at()` returns None always (Sec.6.3 -- it sits above the pipe).
   So GD-ST and GD-SB both HAVE geometry lines but they do different
   JOBS. This must be a QUERYABLE PROPERTY, not folklore -- otherwise
   something will eventually iterate all geometry lines looking for
   contact candidates and wrongly include GD-ST's.

- **Blocks:** nothing -- this is the agreed basis for the dataclass work.

### 21. Moment arm arises from NORMAL-vs-OFFSET collinearity, not from component type

- **Raised / reasoned:** 21 Aug 2026, 10:38 +05:30
- **Related step:** revises item 19's open sub-question about `load_path`;
  affects contact-load transfer for every component
- **Status:** FIRST-PRINCIPLES REASONING, NOT VERIFIED AGAINST WORKING
  CODE. See the caveat below before relying on this.

**IMPORTANT CAVEAT.** `arm` is computed for every component in
`component_spec.py` (`arm=abs(y)`, at L394, L496, L587, L859, L920) but is
CONSUMED NOWHERE -- grep of `slay_sliding_v0_5.py` finds only one mention,
inside a prose comment (L855). It is currently metadata only. So there is
no working implementation to check the reasoning below against; it is
design-stage analysis, not observed behaviour.

**The distinction that matters: geometric offset is NOT the same as a
moment.** A moment arises only when the contact force's LINE OF ACTION
does not pass through the structural line's neutral axis at that section.
If the force is collinear with the offset, `r x F = 0` and the moment is
zero regardless of how large the offset is.

**Why GD-TP / GD-TT need no arm (and adding one would be WRONG):** the
section is concentric, so the contact normal is radial -- along the line
from roller centre through pipe centre. That line passes THROUGH the
neutral axis. Geometric arm is `OD_comp/2`; moment is ZERO. Group 1 is
not "no arm because we ignore it", it is "no moment because the physics
gives zero". Second, independent reason for pipe-shaped components: the
beam element IS the pipe, and standard beam theory already accounts for
load at the outer fibre via the section properties -- an explicit arm
would double-count.

**Correction to an earlier statement made in the same session:** GD-SH was
described as uniformly "offset surface, arm applied at the pipe element".
That is too broad. On the shroud's FLAT deep section the same
collinearity argument applies (normal perpendicular to the flat bottom,
offset vertical, force passes through the centreline) -- so the moment is
zero there too. The genuinely non-zero case is the TAPERS, where the
surface is inclined, the normal tilts away from radial/vertical, the line
of action misses the neutral axis, and a real moment appears. GD-SH is
therefore position-dependent WITHIN one component: zero on the flat,
non-zero on the tapers.

**Where the arm is unavoidable -- GD-SB (and GD-ST):** force enters at the
trapezoid bottom and must route through connectors at discrete x
positions, offset by `P_vt + P_v`. There is no collinearity to cancel it.
This is the case `LoadPath.CONNECTOR` exists for, and where dropping the
arm loses the elevation effect the component exists to produce.

**Restated by CAUSE rather than by component:**

| situation | moment | examples |
|---|---|---|
| force collinear with offset | zero | pipeline, GD-TP, GD-TT, GD-PIP, GD-SH flat section |
| surface inclined, normal tilts | non-zero | GD-SH tapers |
| force routed through a connector | non-zero, mandatory | GD-ST, GD-SB |

**Consequence for item 19's open sub-question.** The discriminator for
whether an arm applies is NOT the component type, and NOT `load_path` as
currently valued -- it is whether the contact normal is collinear with the
offset AT THAT x. `load_path` cannot express this on its own, because
GD-SH is `PIPE_ELEMENT` throughout yet needs a moment on its tapers and
none on its flat. Any design that keys "apply arm?" off `load_path` alone
will get GD-SH wrong in one direction or the other.

- **Needs verification before coding:** the collinearity claims above are
  geometric reasoning, not measured. Worth a numerical check (e.g.
  compare a GD-TP case solved with and without an explicit arm -- if the
  reasoning holds, results should be identical, not merely close) before
  this is built into the rebuild.
- **Blocks:** the contact-load transfer rule; item 19's `load_path`
  decision.

### 20. GD-PIP outer pipe: concentric, with its own input parameters (closes the Sec.5.8 gap)

- **Raised / agreed:** 21 Aug 2026, 09:56 +05:30
- **Related step:** item 19 (contact ownership), item 15 (geometry vs
  structural lines), and the geometry-line storage rule agreed alongside
  this item (see below)
- **Status:** Agreed in principle, not yet coded.

**GEOMETRY-LINE STORAGE RULE agreed in the same discussion (applies to
ALL components, logged here as it is where it was settled):**

> Store an explicit geometry line ONLY when the contacting shape is not
> concentric with its structural line. Otherwise derive it.

| component | shape vs structural line | geometry line |
|---|---|---|
| Pipeline, GD-TP, GD-TT | concentric circle, radius `OD_comp/2` | DERIVED |
| GD-PIP (inner AND outer, per this item) | concentric | DERIVED |
| GD-SH | offset surface, own V/L1/L2 | STORED |
| GD-ST | own rectangle footprint | STORED |
| GD-SB | own trapezoid | STORED |

Rationale: for pipe-shaped components the outer surface is FULLY
determined by the section already stored (`y = -OD_comp/2`, and
`OD_comp` itself derives from `t_comp`). Storing a geometry line would be
storing a derivable quantity -- a second source of truth that drifts the
moment `t_comp` changes. GD-TT makes it concrete: its OD varies along the
tapers, so a stored line would have to track `n`, `dr`, `L_taper`, all
already stored. Storage differs by component; the INTERFACE does not --
`contact_at(x)` already answers uniformly for both kinds, so consumers
never branch. This also resolves item 15's Q3: not a shorthand flag for
"same", just ABSENCE, with the interface filling the gap.

**GD-PIP DECISION: the outer pipe IS concentric with the inner pipe.**
This closes the gap documented at Sec.5.8 (and recorded in
`component_spec_reference.md`) that the outer pipe's radial extent was
undefined and therefore could not claim contact ownership. Being
concentric, its geometry line is DERIVED like any other pipe-shaped
component -- no explicit storage needed.

**New input parameters required on `PipBulkhead`:**

| parameter | notes |
|---|---|
| outer pipe OD | new -- nothing equivalent exists today |
| outer pipe WT | new -- nothing equivalent exists today |
| outer pipe length | REPLACES the current derived `L_outer` |
| origin location | maps to existing `x_interior_R` / `x_interior_L` |
| direction | vessel side / catenary side / bi-directional |

**Changes to existing code this implies (verified against
`component_spec.py` L603-638):**
- `L_outer` is currently a DERIVED property fixed at `pipe.OD_pipe` (1D,
  Sec.5.2). It becomes a FREE input. This is a real behaviour change, not
  a rename -- any case relying on the fixed 1D length changes.
- `variant` is currently DERIVED ('R'/'L'/'B') from which of
  `x_interior_R`/`x_interior_L` is set. Direction now becomes an explicit
  input parameter, and should use the semantic names (vessel side /
  catenary side / bi-directional) rather than geometric R/L -- consistent
  with item 17's naming principle.
- Once `OD_outer` exists, the outer pipe CAN own contact where it is
  present (its surface at `-OD_outer/2` is deeper than the inner pipe's
  `-OD_comp/2`), so `contact_at()` must account for it. Today
  `PipBulkhead.contact_at()` covers the inner pipe only.

**UNVERIFIED -- needs confirmation before coding.** The mapping from the
existing R/L naming to the new semantic naming is INFERRED, not
confirmed: from `slay_overbend_v1_50.py` L493-494 ("Stinger on LEFT,
vessel deck on RIGHT", "X positive LEFT"), vessel rollers sit at positive
x and stinger/catenary at negative x, and `x_structural_R = centre_x +
x_interior + L_outer` advances positive. That implies R = vessel side,
L = catenary side. Confirm before relying on it -- a silent swap here
would place the outer pipe on the wrong side.

- **Blocks:** `PipBulkhead`'s field set; `PipBulkhead.contact_at()`
  extension to cover the outer pipe; regeneration of `detail_gd_pip-r.png`
  once coded.

### 19. Contact-point ownership must resolve to a STRUCTURAL LINE, not just a component

- **Raised / agreed:** 20 Aug 2026, 17:20 +05:30
- **Related step:** extends item 18 (envelope_at -> Assembly.contact_at);
  resolves part of item 15's Q1 (geometry<->structural line
  correspondence)
- **Status:** Design agreed, not yet coded.

**The gap.** `Contact` (verified, `component_spec.py` L211-222) already
carries:
- `y` -- offset from pipe C/L
- `owner` -- item code owning the surface (e.g. 'GD-SH', 'GD-TP', 'pipe')
- `load_path` -- PIPE_ELEMENT or CONNECTOR
- `arm` -- moment arm about the pipe C/L

So COMPONENT-level ownership already exists. What item 15's four-list
framework now additionally requires is the next level down: WHICH
GEOMETRY LINE of that component presents the surface, and WHICH
STRUCTURAL LINE that geometry line is paired to -- i.e. which structural
element actually receives the contact penalty. With multiple components
assembled at the same station and only one being lowest, "the pipe" is no
longer a sufficient answer.

**Where it belongs -- three questions, and they do NOT all share an
owner:**

| # | question | owner | status |
|---|---|---|---|
| 1 | which COMPONENT owns the surface at x? | `Assembly.contact_at()` | already done (`owner`) |
| 2 | which GEOMETRY LINE, and which STRUCTURAL LINE does it pair to? | same call -- component-internal fact | THE GAP |
| 3 | which mesh ELEMENT / DOFs at that x? | the mesher | correctly excluded |

**DECIDED: Q1 and Q2 together in the envelope/contact module; Q3 stays
out.**

Reason Q1+Q2 must stay together: both need the same ownership
resolution. Splitting them means two modules independently working out
"which component is lowest here" -- the exact duplication item 18 exists
to eliminate. Q2's answer is one lookup away from Q1's once the owner is
known.

Reason Q3 stays out: it needs mesh knowledge (element indices, DOF
numbering), and `component_spec.py`'s stated boundary is that it owns no
mesh or FEA-facing geometry. Putting element resolution there would
breach the separation held throughout this rebuild.

**PLANNED UPDATE to the envelope/contact module:** extend `Contact` with
two fields --

    geometry_line_id: str      # which geometry line of `owner` presents
                                # this surface
    structural_line_id: str    # which structural line receives its load
                                # (item 15 pairing)

Handoff then becomes clean: `contact_at(x)` answers WHAT surface, WHOSE,
WHICH STRUCTURAL LINE, WHAT ARM -- and the mesher takes
`structural_line_id` + x and resolves it to actual element DOFs, exactly
as `slide_coeffs_x` already does for the pipe today.

**Open sub-question this raises:** `load_path` becomes partly redundant
once the line pairing exists -- PIPE_ELEMENT would mean "structural line
IS the pipeline's own", CONNECTOR would mean "structural line belongs to
a component, reached via a connector". Decide whether `load_path` stays
as a convenience flag or is derived from the pairing. Not resolved.

- **Blocks:** `Contact`'s final field set; the mesher's contact-application
  interface; item 15's Q1 (this resolves the "how is correspondence
  stored" half -- explicit IDs on the Contact record, not parallel-indexed
  lists).

### 18. envelope_at should become a call into Assembly.contact_at(), not a parallel implementation

- **Raised:** 20 Aug 2026, 16:56 +05:30
- **Related step:** contact/penalty target assembly; relates to items 15
  (geometry vs structural lines) and 17 (naming)
- **Status:** Identified, not yet acted on.

**What `envelope_at` is (verified, `slay_sliding_v0_5.py` L1028-1041):**
returns the CENTRELINE LIFT above the plain-pipe-on-roller baseline at a
given material position -- a scalar OFFSET, not an absolute elevation.
The actual target only exists once added to the arc term:
`normal_disp_target_arc + envelope_at(...)`.

Contributions:
- thick body: flat `CL_thick = (OD_tc - D_o)/2`, only when `in_comp`
- shroud: `shroud_offset_at(...)` -- continuous profile including tapers
- EA-ST: contributes NOTHING (code cross-references `component_spec`'s
  `contact_at()` returning None -- the same rule derived independently
  in this rebuild)

**Sign convention note:** model y is +down (`slay_overbend_v1_50.py` L494:
"SR1 at origin (0,0); X positive LEFT; Y positive DOWN"), so a DEEPER
component bottom pushes the centreline HIGHER -- i.e. `max(contrib)` is
the LOWEST contact surface. Same rule as `Assembly.contact_at()`'s
`LOWEST` ownership policy.

**Version history, confirmed by direct comparison:**
- `slay_overbend_v1_50.py`: `envelope_at` does not exist at all
- `slay_sliding_v0_4.py` L592: no `envelope_at`; done inline and
  ADDITIVELY -- `dn + (CL_thick if in_comp else 0.0) + dn_sh`
- `slay_sliding_v0_5.py` L1028: extracted into `envelope_at`, default rule
  changed to `max` (labelled physical); `sum` retained ONLY to reproduce
  v0.4 for back-comparison

The extraction was not cosmetic -- inline, the `+` did the combining
implicitly and there was nowhere to state a rule at all. Additive
double-counts: where a thick body and shroud overlap, only the deeper
surface actually touches the roller.

**Also absent from v0.4:** any contact-surface treatment. Its `slot_geom`
(L562) is `(nx, ny, allc[s][1]*ny)` -- no `r_contact`, no
`R_eff = R + r_roller + r_pipe`. So v0.4 is implicitly always
'centreline' mode (pipe centreline driven onto the arc, not bottom
surface onto roller top). That whole treatment is a v0.5 addition.

**COORDINATE FRAME -- important, and easy to get wrong:** `x_mat` is a
REFERENCE/MATERIAL coordinate, NOT a deformed global position.
`x_mat = (1-s)*nodes[n_lo-1].x + s*nodes[n_hi-1].x`, and `nodes[].x` are
fixed at mesh construction, never updated during the solve (displacement
lives separately in `U`). It IS "global" in the sense of pipeline-wide
rather than component-local (`shroud_offset_at` takes both `x_mat` and
`ref_centre_x`, converting internally). It is NOT "global" in the sense of
current deformed position. This is the correct choice: the component
travels WITH the material, so "which component is at this point" must be
asked in material coordinates -- asking in deformed coordinates would
return the wrong component as the pipe slides.

**Design wart to fix in the rebuild:** `envelope_at(x_mat, in_comp)` takes
two arguments, but `in_comp` is derived from `x_mat` by the CALLER
(`in_comp = any(lo <= x_mat <= hi for (lo, hi) in ranges_eps)`). So it is
not purely a function of position, and the in-component test lives
outside the function that needs it. `Assembly.contact_at(x)` in
`component_spec.py` already does this properly -- one argument, ownership
resolved internally.

**ACTION:** in the rebuild, `envelope_at` should be a CALL INTO
`Assembly.contact_at()`, not a second implementation of the same physics.
Both currently implement the same lowest-surface-wins ownership rule,
arrived at independently in two places -- exactly the duplication the
single-source-of-truth approach exists to collapse. Carry forward
deliberately: (a) max, not sum; (b) effective radius, not per-target
offset (item 16 records the measured 10.5% artefact from offsetting
targets directly).

- **Blocks:** contact-target assembly in the rebuild; final scope of
  `component_spec.Assembly.contact_at()`.

### 17. Variable naming convention + program glossary

- **Raised / agreed:** 20 Aug 2026, 15:22 +05:30
- **Related step:** all -- applies across the rebuild
- **Status:** Names agreed, not yet applied (nothing coded uses these yet).

**Naming principle (the general rule, more important than any single
name): put the UNIT or FRAME in the name whenever a variable could
plausibly be confused for a different unit.** The sharpest example found
in the old code: `p` (fractional NODE-INDEX units) and `x_t` (METRES,
reference frame) both describe "where the contact is", and nothing in
either name distinguishes them. Renaming to `contact_ref_index` vs
`contact_x_ref` makes the mix-up impossible.

Same reasoning applies to item 16: if arc-length and rectangular
positions both exist in the rebuild, they must be named so they can never
be silently swapped -- e.g. `x_arc` vs `x_rect`, NEVER a bare `x`.

**Collision found in the old code, worth fixing regardless of any
rename:** `s` is used for two unrelated things in the same file --
`_build_geometry` L1861 `for s in range(nsp)` is a station/span INDEX
(int), while `slide_coeffs_x` L241 `s = (x_lo - x_target)/seg` is a
PARAMETRIC position (0-1 float). Same letter, different type, different
meaning.

**SECOND collision found (20 Aug 2026), same class:** `dn` also means two
different quantities depending on where you read it --
- `slot_geom` L997: `allc[s][1]*ny + r_contact` -- ARC GEOMETRY ONLY
- the solver's slot format (L318 docstring, unpacked as `_dn` at L332):
  ARC + COMPONENT LIFT, because `make_slots` passes
  `dn + envelope_at(x_mat, in_comp)`

One quantity is a component of the other, under the same name. Needs two
distinct names -- see solver table below.

**Agreed renames -- sliding / contact chain:**

| old | new | note |
|---|---|---|
| `bn` | `roller_base_node` | integer node index at zero shift |
| `p` | `contact_ref_index` | fractional node-index units, NOT metres |
| `x_t` | `contact_x_ref` | metres, reference frame |
| `s` | `elem_frac` | 0-1 within one element |
| `a` | `contact_coeffs` | shape-function x normal, per DOF |
| `x_mat` | `contact_x_material` | which material point is under the roller |

**Agreed renames -- solver / penalty:**

| old | new | note |
|---|---|---|
| `u_out` | `normal_disp` | current displacement, projected onto the normal |
| `dn` (solver / total) | `normal_disp_target` | the value `normal_disp` must reach -- arc PLUS component lift |
| `dn` (slot_geom / base) | `normal_disp_target_arc` | arc geometry alone, before component lift |
| `rn` | `normal_gap` | `target - current`; >=0 contact, <0 tension |
| `lam` | `load_factor` |  |
| `pen` | `penalty_stiffness` |  |
| `nx`, `ny` | `normal_x`, `normal_y` |  |

**Revision note (20 Aug 2026):** the first three supersede the earlier
`normal_target` / `disp_along_normal` suggestions in this item. Reasons:
(a) a shared `normal_*` prefix makes the trio's relationship visible at a
glance, since they are always used together as `gap = target - current`;
(b) bare "target" is ambiguous -- target POSITION? target FORCE? It is
neither, it is a DISPLACEMENT, so `_disp_` is load-bearing, not padding;
(c) the base/total split resolves the `dn` collision noted above.

With these names the assembly line in `make_slots` reads:

    normal_disp_target = normal_disp_target_arc + envelope_at(
                             contact_x_material, in_comp)

which states plainly what is currently implicit -- the solver's target is
the arc target plus the component's lift at whatever material point is
presently under that roller.

**Agreed renames -- mesh building:**

| old | new |
|---|---|
| `epe` | `elems_per_span` |
| `nsp` | `n_spans` |
| `s` (station loop) | `span_idx` |
| `rnid` | `roller_node_id` |
| `xs_span` | `span_node_xs` |
| `snaps` | `mandatory_xs` |
| `mi` | `mesh_idx` |
| `allc` | `roller_stations` (already agreed, tracker item resolved) |

**ALSO AGREED: every program module carries a GLOSSARY in its header
comments** -- listing each non-obvious variable with its meaning AND its
units/frame. Rationale: the renames above help at the point of use, but a
reader opening a module cold still needs one place that states, e.g.,
that `contact_ref_index` is in fractional node-index units while
`contact_x_ref` is in metres. The old code documented reasoning
extensively in prose comments but had no single variable reference, which
is why tracing `p`/`s`/`a`/`dn` in this session required reading several
functions in full.

- **Blocks:** nothing -- to be applied as each module is written.

### 16. Node positions on the straight pipeline: use ARC LENGTH, not rectangular x

- **Raised / decided:** 20 Aug 2026, 13:41 +05:30
- **Related step:** Step 2 (pipeline modelling); affects Step 1's output use
- **Status:** DECIDED in principle (arc length + free sliding), specifics
  below verified. Not yet coded.

**What the old code does (verified, `slay_overbend_v1_50.py` L1853-1867):**
stinger station x comes from `-R*sin(theta)` (rectangular), and mesh nodes
are interpolated between those rectangular values. No arc-length
conversion exists anywhere in the file.

**This was deliberate, not an oversight** -- two comments document it:
- L2801: "by SR6 the tangent is ~33 deg and material points slide ~1-2 m
  tangentially over the rollers (arc length vs chord); a uy-only
  constraint fights that slide and was measured in first validation to
  create a spurious ~2.4% strain concentration at SR6 (vs ~0.29%
  pure-arc bending)."
- L223: "the mesh is NOT uniform in x: element lengths here span
  0.62-0.82 m because SR-span chords shrink along the arc."

The old solution: keep rectangular positions, and let the
normal-direction-only penalty (free tangential slide) redistribute
material during the solve.

**Independently quantified (matches the code's own documented figures):**

| quantity | computed | code states |
|---|---|---|
| element length range (R=70) | 0.685-0.818 m | "0.62-0.82 m" |
| tangential slide at SR6 | 2.07 m (R=85), 3.04 m (R=70) | "~1-2 m" |

SR1->SR6 straight-mesh material = 42.93 m vs true arc 45.0 m -- short by
2.07 m at R=85 (3.04 m at R=70). Shortfall grows monotonically down the
stinger; zero at SR1.

**DECISION: arc length + free sliding.** Node reference positions on the
straight pipeline are set by arc length (`s_i = R*theta_i`, i.e. simply
`i * spacing` since spacing is already defined along the arc), NOT by
rectangular `-R*sin(theta)`. Free tangential sliding is RETAINED -- the
two are complementary, not alternatives.

Rationale: bending is inextensible to first order, so a material point
keeps its distance-along-pipe. Arc length is the quantity preserved
between straight and curved configurations; rectangular x is not.
Benefits: uniform element length everywhere (0.818 m) instead of
0.62-0.82 m varying down the stinger, so strain resolution is comparable
across rollers; material length correct by construction (no 2-3 m
shortfall to slide in); node<->material correspondence stays tight
(sliding becomes a small residual, not 3-4 elements of drift); free
sliding remains as the physical safety valve. Also strengthens the
invariant `slide_coeffs_x` depends on -- uniform node COUNT per span
becomes uniform count AND uniform length.

**HARD DEPENDENCY -- `dn` must change with it. Do not move node
positions without this.** The existing target formula
`dn = sr[sl][1] * ny` (i.e. `arc_y * ny`) is NOT a general projection --
it works only because rectangular positioning makes `ux = 0` at the
target, silently killing the `ux*nx` term of `u_out = ux*nx + uy*ny`.
(This also explains why that formula looked like an unexplained "multiply
y by ny" when first traced -- it is a full projection with one term
coincidentally zero.)

Under arc-length positioning `ux` is no longer zero (2.07 m at SR6), so
the term returns. Corrected target, verified in closed form against the
direct projection:

    dn = R * (1 - cos(theta) - theta * sin(theta))

Error if node positions were changed but the old `dn` kept:

| roller | SR3 | SR4 | SR5 | SR6 |
|---|---|---|---|---|
| target error | 0.03 m | 0.14 m | 0.44 m | 1.05 m |

A ~1 m target error at SR6 would produce plausible-looking but wrong
strains -- the silent-failure class this rebuild exists to eliminate.

**Vessel rollers unaffected:** the deck is straight, so arc length and
rectangular x coincide. This distinction only applies stinger-side.

- **Consequence, accepted:** all 53 previously validated cases were run on
  rectangular positioning; results will change (most at SR5/SR6, least at
  SR1). User confirmed 20 Aug 2026 this is acceptable -- the program is
  being rebuilt and all validation cases will be re-run later regardless.
- **Blocks:** Step 2's node-position formula; the penalty-target formula
  wherever it lands in the rebuild.

### 15. Universal geometry/structural node-and-line framework (generalizes item 9)

- **Raised:** 18 Aug 2026, 23:53 +05:30 (note: timezone differs from
  earlier entries in this file, which used +08:00 -- logged exactly as
  the time tool reported it, not corrected to match)
- **Related step:** generalizes item 9 (component Line entity, previously
  scoped to EA-ST/EA-SB only); also touches item 8 (connector stiffness)
  and item 12 (kT/kB per-element rule)
- **Status:** Proposed, not yet agreed in detail (four open questions
  below block finalizing it). Every component gets four lists, not just
  EA-ST/EA-SB:
  1. Geometry nodes
  2. Structural nodes
  3. Geometry lines
  4. Structural lines

  **Geometry** lines/nodes: find bounding surfaces, draw the component's
  shape, identify contact surfaces. **Structural** lines/nodes: used for
  FEA meshing with beam elements. Existing FREE/DERIVED parameters are
  unchanged -- this is additive, not a replacement. Node coordinates are
  parametric (defined in terms of the component's own dimensions, not
  absolute numbers), and every component's default origin is its own
  centre.

  Contact load on a geometry line transfers to its corresponding
  structural line -- this transfer itself needs calculating and
  assigning, not just the two line sets existing side by side. Structural
  line stiffness may be derived (from real section properties, like item
  13's GD-TP rule) or assigned (like item 12's kT/kB convention) depending
  on the component.

  **Likely resolves, pending confirmation:** item 9's open question about
  whether EA-SB's shape needs multiple line segments (the trapezoid can't
  be one straight line) -- under this framework the natural answer is
  yes, a structural line can be more than one segment (e.g. left slope /
  flat bottom / right slope for EA-SB), each with its own stiffness. Not
  yet explicitly confirmed as the intended reading.

- **Open questions, blocking finalization:**
  1. **How is the geometry-line <-> structural-line correspondence
     stored?** Parallel-indexed lists (index i in each list always
     corresponds)? Explicit ID references on each line? Always strictly
     1-to-1, or could one geometry line's contact load ever need
     splitting across more than one structural line (e.g. a contact patch
     straddling a structural node)?
  2. **The load-transfer rule needs to be general, not just GD-SB's
     specific case.** GD-SB's version is already worked out (force +
     moment, arm = `P_vt + P_v`, because the geometry line sits below the
     structural line -- tracker item covering `BaseStructure`'s
     `load_path=CONNECTOR`). Under this new universal rule, does GD-SH
     (currently zero structural effect -- `section_at` returns `None`)
     now also need its own transfer-to-the-pipe's-structural-line
     calculation? Leaning yes, but this is new physics to work out, not
     just new bookkeeping, if so.
  3. **Components where the two lines coincide exactly (GD-TP: geometry
     line = structural line = the 2-node pipe centreline from item 13)**
     -- stored as two genuinely redundant identical lists, or is there a
     shorthand/flag meaning "same, no transfer needed"?
  4. **Stiffness should likely be assigned per LINE, not per component**
     (given question 1's likely multi-segment answer for components like
     EA-SB) -- not yet explicitly stated as a rule, should be if
     confirmed.

- **Blocks:** any further `component_spec.py` Line-entity work (item 9);
  finalizing items 8/12's stiffness conventions as special cases of this
  more general rule, if this is adopted.

### 14. GD-SH L2 default correction (2.5D -> 5D)

- **Raised:** [timestamp tool failed, not logged]
- **Related step:** none directly -- straightforward parameter correction
- **Status:** Agreed, not yet coded (and deliberately kept that way --
  an earlier attempt in this same discussion edited `component_spec.py`
  directly before documentation was confirmed; that edit was reverted).
  `L2`'s multiplier changes from `2.5 x pipe.OD_pipe` to `5 x pipe.OD_pipe`
  -- a genuine doubling, confirmed by direct calculation: 1.016 m ->
  2.032 m at `STD_PIPELINE`. `V` (`1D`) and `L1` (`10D`) were
  re-confirmed in the same discussion and are unchanged.
- **Blocks:** `component_spec.py` code change to `OffsetShroud`
  (`L2`'s literal default and `default_for()`'s `L2` multiplier);
  regenerating `detail_gd_sh.png`, currently showing the old `1.016 m`
  value.

### 13. GD-TP defaults, shape line, and stiffness rule

- **Raised:** [timestamp tool failed, not logged]
- **Related step:** item 9 (component Line entity), item 12 (stiffness
  rules)
- **Status:** Agreed in words, not yet coded. Four pieces:
  1. `ID_comp = pipe.ID` -- confirmed already correct in current code, no
     change needed, just documented clearly.
  2. `t_comp` default changes to `2.5 * pipe.t_pipe` via a new
     `default_for(pipe)` classmethod (matching the established
     `OffsetShroud`/`TopStructure`/`BaseStructure` pattern). **Genuine
     numeric change, confirmed by direct calculation:** 0.0525 m at
     `STD_PIPELINE`, not the current hardcoded 0.065 m.
  3. `L_comp` default changes to `2.5 * pipe.OD_pipe`, same pattern.
     **Also a genuine numeric change:** 1.016 m at `STD_PIPELINE`, not the
     current hardcoded 1.2 m.
  4. Stiffness for the meshing module = real section-property `EI`
     (`E * pi/64 * (OD_comp**4 - ID_comp**4)`), same formula
     `BasePipeline.EI` already uses, just with this component's own
     `OD_comp`/`ID_comp`. No element-length floor needed, unlike `kT`
     (item 12) -- a real cross-sectional property isn't mesh-dependent.
  5. Shape line: 2 end nodes at `extent[0]`/`extent[1]`, both `y=0`
     (on the pipe centreline, no offset) -- matches the pipeline's own
     2-node convention (item 10), not EA-ST/EA-SB's 4-corner rectangle.
     Resolves part of item 9's open scope question: IW components DO get
     a Line concept, and it's this simple version.
- **Not yet decided:** whether `default_for()` for `t_comp`/`L_comp`
  should live on `ThickPipeBody` itself or be inherited by `TaperedThickBody`
  (which extends it) -- not addressed yet, `TaperedThickBody` still has its
  own separate fields (`n`, `L_NIB`) this doesn't touch.
- **Blocks:** `component_spec.py` code changes to `ThickPipeBody`
  (`default_for()` addition, defaults changing from literals to
  pipe-relative); regenerating the stale `detail_gd_tp.png` schematic once
  the code changes land.

### 12. Frame-line element stiffness (kT/kB) moves from a stored value to a mesher-applied rule

- **Raised:** 16 Aug 2026, 01:28 +08:00
- **Related step:** item 9 (component Line entity), item 8 (connector
  stiffness, distinct but related)
- **Status:** Agreed in words, not yet formalized as code or a numeric
  procedure. `kT` (and by the same principle, `kB` for EA-SB, and any
  future stiffness term a frame-line element carries) is no longer a
  single fixed value describing the whole frame. Once the load frame line
  is meshed, each element gets its own bending stiffness: 2.5x the
  bending stiffness of an equivalent-length section of the plain
  pipeline, using the element's own meshed length -- UNLESS that length
  is 1x pipe OD or shorter, in which case 1x pipe OD is used as the
  length instead (a floor, to avoid an artificially huge or
  ill-conditioned stiffness for very short elements).
- **Distinct from item 8:** item 8 (connector stiffness = preset, never
  length-derived) concerns the short/zero-length connector member. This
  item concerns the frame line's own elements, which have real, nonzero,
  mesh-dependent lengths -- a different structural role, not a
  contradiction.
- **Not yet decided:** the actual numeric procedure isn't specified here
  by design -- element length isn't known until the mesher runs, so this
  can only be resolved once meshing exists. Also open: whether
  `component_spec.py` keeps a `kT` field at all going forward (perhaps
  holding just the policy -- multiplier 2.5, floor 1xOD -- rather than a
  number), or whether this moves entirely into the meshing module with no
  trace left in `component_spec.py`.
- **Blocks:** finalizing `TopStructure`/`BaseStructure`'s stiffness
  fields; the meshing module's design once it exists.

### 2. Sweep buffer must be factored into pipeline length

- **Raised:** [timestamp tool failed, not logged]
- **Related step:** Step 2 (Pipeline modelling), X-extent decision
- **Status:** Confirmed from old code: `n_sr_total = n_sr + 1` (stinger side)
  plus a generously-sized `n_vr` (vessel side, later clipped for plotting)
  give a component's reference position room to shift across a sweep
  without running off the mesh edge. User has confirmed this must be
  factored into the fresh build's pipeline length decision.
- **Not yet decided:** the exact sizing rule (how much buffer, based on
  what), and whether this logic lives inside geometry-building itself or
  is a caller-supplied larger `n_sr`/`n_vr`.
- **Blocks:** finalizing Step 2's X-extent definition.

### 3. Roller diameter is missing from the contact-target calculation

- **Raised:** [timestamp tool failed, not logged]
- **Related step:** Step 2 (Pipeline modelling), deciding pipeline Y
- **Status:** Confirmed from old code: the `dn`/`CL_lift` formula that
  drives roller contact targets never includes roller radius anywhere
  (every use of `r_roller` in the file is plotting-only). This was
  harmless there because roller diameter was implicitly uniform across
  all rollers -- a uniform offset is a pure rigid-body shift that doesn't
  change bending strain. It stops being harmless now that Step 1 tracks
  per-roller diameter: different-sized rollers need different local
  standoff to stay physically tangent, and the old formula can't
  represent that.
- **Not yet decided:** two different ways to fix this --
  (A) keep initial node y=0 as a plain solver seed, fix only the per-roller
  penalty target formula to include roller radius + pipe/component radius;
  or (B) compute a genuine reference Y per station from contact-surface
  requirements (roller radius + pipe/component contact offset) before
  building nodes, so the starting geometry itself already respects roller
  elevation. Item 5's geometry-first architecture proposal (14 Aug 2026)
  operationalizes (B) directly ("determine the bottom contact surface...
  then decide the pipeline Y based on it") -- leaning strongly toward (B)
  now, but not yet formally closed out since item 5 itself is still under
  discussion.
- **Blocks:** finalizing Step 2's Y definition.

### 4. Mesh snapping is only needed for section-changing components

- **Raised:** [timestamp tool failed, not logged]
- **Related step:** Step 2 (Pipeline modelling); also affects
  `slay_geometry.py`'s already-agreed spec (Round 2)
- **Status:** Confirmed from old code: the snapped mesh rebuild only runs
  `if tc is not None` (thick/tapered component present). A shroud needs no
  snapping -- its comment states contact offset is evaluated continuously
  at any x, not tied to a discrete per-element section id. This means
  `slay_geometry.py`'s Round 2 spec, which said every component's extent
  should be forced as an exact node, is too broad and needs correcting:
  only components whose `section_at()` returns non-None need this.
- **Blocks:** correcting the already-agreed `slay_geometry.py` spec.
- **Related:** item 5's IW-split-vs-EA-connector distinction is the same
  rule restated as a geometry-construction choice, not just a
  mesh-snapping one.

### 5. Geometry-first architecture -- separate geometry from mesh

- **Raised:** 14 Aug 2026
- **Related step:** reshapes Steps 1-2 and introduces new steps; supersedes
  the "build nodes directly" approach traced from the old code
- **Status:** User-proposed sequence, reviewed, broadly agreed in
  principle: geometry (lines/nodes/shape, with bottom-surface definition
  per line) built first and separately from mesh (FEA discretization).
  Sequence: pipeline line (2 end nodes, length from roller drape + sweep
  buffer) -> component line(s), positioned per sweep target -> connector
  node identification -> IW components split the pipeline line in; EA-ST/
  EA-SB attach via connector lines instead. Full assembly then placed at
  the user-specified or default location.
- **Not yet decided:** item 9 (component Line entity) remains open below.
  Items 6-8, 10 (originally opened alongside this) are now resolved.
- **Blocks:** formalizing any of this into `SLAY_MODEL_BUILDING.md`.

### 9. Component "Line" entity needed for EA-ST/EA-SB in component_spec.py

- **Raised:** 14 Aug 2026
- **Refined:** 15 Aug 2026, 00:17 +08:00
- **Refined again:** [timestamp tool failed, not logged]
- **Related step:** item 5
- **Status:** Two distinct lines are needed, not one -- confirmed by
  discussion, correcting an earlier assumption (see below):
  - **Shape line** -- the structure's own physical footprint/outline.
    Genuinely new; nothing in `component_spec.py` currently returns this.
    EA-ST is straightforward (single straight line, `L_top` wide). EA-SB
    is NOT -- the trapezoid (flat bottom + two sloped sides) can't be a
    single straight line; needs either multiple segments or a deliberate
    simplification decision, not yet made.
  - **Load frame line** -- represents the actual structural load path.
    **Correction:** first guessed this was fully derivable from
    `ConnectorLocations.xs()` filtered to active `ConnectionSystem.types`
    slots (i.e. no new stored data needed). This was wrong -- the load
    frame line can extend beyond connector-to-connector, into other parts
    of the structure (supporting piping, connectors, etc.), so it is ALSO
    genuinely new geometry needing its own definition, not derivable from
    existing connector data alone.
- **Not yet decided:** EA-SB's shape-line segment structure; how the load
  frame line's "other parts" (supporting piping, connectors) get
  parameterized and stored; whether shape line and load frame line share
  any node numbering or are fully independent.
- **Scope note (carried from prior refinement, still standing):** both
  lines are scoped to EA-ST/EA-SB only. IW components (thick body, tapered
  transition) don't need either -- they become part of/replace a portion
  of the pipeline's own line via splitting rather than attaching
  alongside it. Not yet confirmed whether IW needs no Line concept at all
  or a different/simpler one.
- **Blocks:** designing the component Line representation before item 5's
  sequence can be built.

---

## Resolved

### 11. Connector node placement -- replaces the fixed 5-slot P_c1/P_c2 scheme

- **Raised:** 16 Aug 2026, 00:51 +08:00
- **Resolved:** 16 Aug 2026, 00:51 +08:00
- **Related step:** item 9 (component Line entity)
- **Supersedes:** `ConnectorLocations`'s `P_c1`/`P_c2` fixed 5-slot pattern
  (bottom edge only) as currently built in `component_spec.py`. That
  scheme, and `ConnectionSystem.types` (a tuple of exactly 5, one per
  slot), are both built assuming a fixed count -- both need reworking, not
  just extending.
- **Outcome:**
  - Connector nodes get their own explicit position list, per side of the
    shape line (bottom, top, left, right) -- e.g. `bottom_connector_x:
    list[float]`, and similarly for the other three sides.
  - Count is never stored as its own field once the list exists --
    `len(list)` is the only source of truth, so count and positions can
    never disagree. A connector-count input is used only at construction
    time, to size the placeholder list.
  - Default placeholder positions: evenly spaced along that side,
    EXCLUDING the exact endpoints/corners -- chosen specifically to avoid
    two adjacent sides both generating a placeholder at the same shared
    corner (a duplicate-node problem, not just cosmetic).
  - Default counts: bottom = 5, top = 1, left = 1, right = 1.
  - **Explicitly flagged and confirmed:** bottom's default 5 positions do
    NOT numerically match the old `P_c1`/`P_c2` pattern. Old scheme:
    `P_c1=0.5*L_top` (interior span), `P_c2=0.2*L_top` (interior-to-outer)
    -- a non-uniform arrangement. New scheme: 5 points evenly spaced
    excluding endpoints = 1/6, 2/6, 3/6, 4/6, 5/6 of the side's length --
    uniform. Same count, different positions -- confirmed this is
    intended, not an oversight.
  - For n=1 (top/left/right defaults): evenly spaced excluding endpoints
    with a single point = the midpoint of that side.
- **Also affected, not yet done:** `gdst_frame_connectors.png` and
  `gdst_frame_xy.png` (generated earlier this session) show the OLD
  5-slot bottom-only pattern with `P_c1`/`P_c2` lettered as E/F -- stale
  relative to this decision. Regenerate before reusing either.
- **Blocks:** `component_spec.py` code changes to `ConnectorLocations`/
  `ConnectionSystem` (not yet made -- this is a documented decision, not
  an implemented one); completing item 9's Line entity design now that
  node placement on all four sides has a rule.

### 10. Confirm "2 nodes at ends only" means endpoint positioning, not splitting

- **Raised:** 14 Aug 2026
- **Resolved:** 15 Aug 2026, 00:17 +08:00
- **Outcome:** Confirmed -- end nodes, positioning only.

### 6. GD-SH (shroud) has no assigned category in item 5's sequence

- **Raised:** 14 Aug 2026
- **Resolved:** 15 Aug 2026, 00:17 +08:00
- **Outcome:** Confirmed as a third case: no topology change, just an
  override on the pipeline line's own bottom-surface definition over the
  shroud's extent.

### 7. VR buffer sizing rule doesn't generalize past one spacing

- **Raised:** 14 Aug 2026
- **Resolved:** 15 Aug 2026, 00:17 +08:00
- **Outcome:** Confirmed: `ceil(sweep_length / spacing)` extra VRs.

### 8. Connector line length -- zero-length shared node, or real length?

- **Raised:** 14 Aug 2026
- **Resolved:** 15 Aug 2026, 00:17 +08:00
- **Outcome:** Both are valid -- a connector line can be zero-length or a
  specific length, context-dependent. Separate, important standing rule
  attached to this: **connector stiffness must never be derived from the
  connector's own member length** (i.e. no EA/L or 12EI/L^3-style
  formula) -- it has to be a preset stiff value, matching the existing
  `kT`/`kB` convention already in `component_spec.py` (fixed values, not
  computed from any member geometry). Worth remembering specifically when
  connector lines get implemented, since a length-based stiffness formula
  is the natural default a general FEA connector element would use.

### 1. Step 1 output -- what does `y` represent? (in the OLD code)

- **Raised:** 14 Aug 2026
- **Resolved:** 14 Aug 2026
- **Outcome:** Traced end-to-end. `dn_map` (built from this `y`) is
  confirmed dead -- written once, never read again anywhere in the file
  except inside a plotting comment. Separately confirmed: mesh nodes are
  always created with `y=0.0`, regardless of station. So in the OLD code,
  `y` in the station data was never actually used to position anything.
  Superseded by items 2-4 above, which cover how the FRESH build should
  handle pipeline Y and X -- this old-code finding is historical
  background for that decision, not the fresh build's answer.

### `allc` needs a proper name

- **Raised:** 13 Aug 2026
- **Resolved:** 14 Aug 2026
- **Outcome:** renamed to `roller_stations`.

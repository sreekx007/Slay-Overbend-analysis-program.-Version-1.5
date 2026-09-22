# Model building, assembly and meshing — the sequence

Step by step, in the order the code runs. Entry point:
`slay.model.assemble.build_model(scene, ils, s_centre, target_len)`.

---

## A. Inputs

**A1. Component definition (JSON) → `ils_builder.build_ils()`** *(mirror, never edited)*
Returns the ILS assembly: `ils.extent` (component footprint), `ils.header`,
`assembly.section_at(x)` (OD, wall → EI, EA), `assembly.contact_at(x)`
(deepest surface → roller lift), mass, CoG.

**A2. Lay configuration → `slay.scene.build_scene(R, spacing, n_sr, n_vr, margin, elastic_length)`**
Returns the Scene: stinger arc, roller stations, `extent` (s_lo, s_hi) and
the forced-elastic zone boundaries. `margin` defaults to **0** — no buffer
beyond the outermost stations.

**A3. Frame change.** ILS-local `x` (toward the vessel) → model `s` (toward
the stinger): `s = s_centre − x_local`. One line, in `build_model`.

---

## B. Part layer — named nodes, connectivity by identity

A *part node* is a named point that means something: a weld, a body station,
a connector end. Connectivity is carried by identity, never by position.

**Merge rule** — within a pass, coincident part nodes merge at
`MERGE_TOL = 0.01 m`. **Across passes they never merge**, except a DECLARED
junction (`component.junctions()`), which is intent rather than coincidence.

| Pass | Constant | Registers |
|---|---|---|
| **0** | — | *positions only*: connector pipe-side stations, declared junctions. Collected before meshing because a connector transfers force at a node, so the node must exist first. |
| **1** | `PASS_HEADER = 1` | header ends `PIPE-LO`/`PIPE-HI` at the Scene extent; elastic-zone boundaries; the pass-0 stations; `extra_stations`; IW primary lines |
| **1b** | `PASS_IW_SEC = 2` | IW secondary lines — PIP outer, VLV stem, GD-B branch |
| **2** | `PASS_EA = 3` | external structures (GD-ST, GD-SB) around their own arc |
| **3 / 4** | `PASS_CONN_P = 4`, `PASS_CONN_E = 5` | connector end nodes, pipe/IW side and EA side; connector elements; `Association` records (type, tie pattern, gap, skewed) |

Connector stiffness is that of a **1×OD pipeline element** — never derived
from the connector's own length.

---

## C. Meshing — one line at a time

Part elements are grouped by `line_id`; connector elements are excluded (each
is a single element and is not subdivided).

**C1. Chain → `Polyline`** — ordered `node_ids`, `xs`, `ys`, cumulative
`arcs`, and whether the chain is closed.

**C2. Stations.** Every part node becomes a **MANDATORY** station
(`NodeReason.SECTION`). A mandatory station is never dropped (G4).

**C3. Segments.** Every part element becomes a `Segment` carrying
`min_elements`, `target_elem_len`, `owner`, `section`, `stiffness_rule`,
`stiffness_ratio` — so a component can set its own density over its own span.

**C4. `mesh_line(polyline, stations, target_len, segments, max_ratio=2.0)`**
Owns sizing, grading and snapping. Works in **arc length along the line**,
never a projection onto an axis (G2) — so horizontal, vertical, sloped and
closed members take one code path. Default `target_len = OD_MULTIPLE × OD` =
**2×OD** (G10). Adjacent element lengths are limited by `max_ratio`.

Nothing here takes a roller argument: contact never drives node placement
(G1). A sliding contact sits at a virtual point inside an element and
distributes to the bracketing nodes.

---

## D. Numbering — part nodes to mesh nodes

**D1.** A mesh node landing on a part node **reuses that part node's number**.
This is how two lines meeting at a declared junction stay joined.

**D2.** Interior subdivision nodes are new and belong to their element alone.

**D3.** Zero-length connector ends are materialised explicitly — they carry
no element, but the penalty tie needs a DOF row at each end.

**D4.** Part nodes carrying neither an element nor an association are
dropped, and recorded in `Model.warnings`.

**D5.** `Model.assert_no_accidental_sharing()` — two mesh nodes at the same
coordinate are harmless unless something *declared* them tied.

---

## E. Output

`Model(nodes, elements, part_nodes, part_elements, associations, warnings)`.
Each element carries `line_id`, `owner`, `section`, `stiffness_rule`,
`stiffness_ratio`, `connector`.

Downstream: `physics.build_problem(model, scene, assembly, ils, shift, …)`
→ `solve.passage.solve(problem, state_in)`.

---

## F. Checks

| Check | Where |
|---|---|
| layer dependency rule | `tools/check_layers.py` |
| mesher invisible in the result | `tools/run_mesher_rig.py` — archetype on a bare beam, prismatic section, closed form exact |
| archetype geometry | `test_edas_archetypes.py` — mass, span, extent against recorded figures |
| gate | `tools/run_checks.sh` |

---

## G. Known gaps in this sequence

* `build_scene(margin=)` is **0** — no vessel-side buffer, so a sweep is
  capped at ~90% of one roller spacing.
* One global `target_len` is passed to every line. A component needing its
  own density (2 elements, ≥1×OD — L058) and a pipeline held at 2×OD (G10)
  cannot both be served by it. Component-first assembly is the fix.
* No tool draws a component on the stinger, so placement cannot be checked
  by eye.
* GD-SH has no `pipeline` polyline — it meshes on its own geometry line.

---

## Action log

| Date | Action |
|---|---|
| 22 Sep 2026 | Written from the code: passes 0–4 and their constants, the two-half merge rule, the station/segment handoff into `mesh_line`, the part-to-mesh numbering rule, and the four checks. Four gaps recorded. |

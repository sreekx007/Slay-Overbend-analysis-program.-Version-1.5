# T3 — Model · specification for review

**Status:** DRAFT — §3 step 1 (plain-language algorithm). Awaiting your review.
**Card:** `docs/SLAY_BUILD_INSTRUCTION.md` §6 T3
**Layer:** `model` (L4) · **Workflow:** algorithmic only

> Step 1 of the per-module process. No code until steps 2–4 are done.
> §4 contains one finding that changes how this layer must be built, and §7
> answers decision D2.

---

## 1. What Model is for

`slay/model/mesh.py` already turns **one** structural line into beam
elements, correctly and with the grading rules honoured. What it cannot do
is produce a model: a real analysis needs the whole pipeline, the components
welded into it, the structures attached beside it, and the connectors
joining them — as one set of nodes and elements with consistent numbering.

T3 is that assembly step. It takes a Scene, optionally an ILS, and emits the
**Model**: flat node and element arrays, each element knowing which line it
belongs to and which component owns it.

## 2. Where Model stops

**No physics.** No sections bound to materials, no contact targets, no
loads, no boundary conditions. An element here knows its length and which
line it is part of. What it is *worth* is the physics layer's answer.

**No sweep.** The mesh is built once and does not change as the ILS travels.
That is not an optimisation, it is a consequence of the ILS being welded
into the pipe: component boundaries are fixed in material coordinates, so
only *which material point sits under each roller* changes. T3 is where that
claim becomes checkable rather than asserted.

**No contact.** Rollers do not appear here at all. Contact sits at a virtual
point inside an element and distributes to the bracketing nodes by shape
functions, so a roller never earns a node (G1). This exclusion is what makes
the mesh shift-invariant.

## 3. The reference configuration — the thing most likely to be got wrong

**The meshed pipe is STRAIGHT.** It is not built on the stinger arc.

The model's reference configuration is the undeformed, stress-free pipe,
laid out along its own length. Bending it onto the arc is precisely what the
solver computes, and the strain that results is the answer we are after. A
mesh built pre-curved onto the arc would start with the deformation already
applied and produce no bending strain at all.

So **Model coordinates are `(s, y_offset)`**, not the world `(x, y)` Scene
works in:

| | meaning |
|---|---|
| `s` | arc length along the undeformed pipe, the same coordinate Scene gives its stations |
| `y_offset` | transverse offset from the pipe centreline — 0 for the pipe, negative for a structure above it, positive for one below |

Scene's world `(x, y)` describes where the *rollers* are. The two frames
meet at the physics layer, where the contact target says how far each roller
must pull the pipe off its straight reference to reach the arc. Under
arc-length positioning that target is `R(1 − cos θ − θ sin θ)`, **not** the
old `arc_y · n_y` — keeping the old form here gives a 1.05 m target error at
SR6 (tracker item 16). That is L5's arithmetic, but it is the reason this
layer must stay straight.

This also matches the old implementation, which created every mesh node at
`y = 0.0` regardless of station. The change from it is the *spacing* — arc
length rather than rectangular x — not the straightness.

## 4. FINDING — the frozen kernel merges nodes by coordinate

`nlfea_v4.MeshedStructure._mesh()`:

```python
def get_or_add(x, y):
    key = (round(x, 10), round(y, 10))
    if key not in node_coords:
        node_coords[key] = len(self.mesh_nodes)
        self.mesh_nodes.append((x, y))
    return node_coords[key]
```

Any two nodes at the same coordinate, to 10 decimal places, **become one
node**. Unconditionally, inside a file we may not edit (G6).

**This inverts the rule I wrote into the T3 card.** "Merge only where a
junction is declared, never by coordinate coincidence" is not something this
layer can enforce downstream — the kernel will merge coincident nodes
whatever we declare. The 12 Aug architecture plan records what that costs:

> every frame node landing on a pipe x-coordinate merges the whole frame
> into the pipe, silently turning a two-point attachment into a continuous
> stiffener

**So the rule has to be restated as an obligation on the Model rather than a
promise about the mesher:**

> **Coordinate coincidence and intended merging must agree.** Two nodes
> share a coordinate **if and only if** a junction declares them merged.

That is checkable, and checking it is the single most valuable thing T3 can
do. Stated as an integrity assertion on the emitted Model, it catches the
documented failure before the solver ever runs, rather than leaving it to
show up as a stiffness that is quietly too high.

Two cases it has to get right:

- **A zero-length connector is a real shared node.** `Connector` allows
  `y_struct = 0`, and its own docstring says so: at zero length the pipe-side
  and structure-side nodes coincide and the tie *is* the shared node. Here
  coincidence is the intent, and the junction declaration agrees.
- **A structure member must never coincide unintentionally.** A GD-ST frame
  sits at negative `y_offset` and a GD-SB straddles the pipe, so neither has
  a node at `y = 0` by construction — but that is a property of today's
  defaults, not a guarantee, which is exactly why it gets asserted.

## 5. A second consequence: who owns subdivision

`MeshedStructure` also subdivides each user element into `seed` pieces. If
we hand it elements with `seed > 1` it re-meshes underneath us, and the
grading rules `slay/model/mesh.py` enforces would be silently overridden.

**Model emits final elements, one `UserElement` each, `seed = 1`.** Our
mesher owns discretisation; the kernel does assembly. That is the layer
contract, and `seed` is where it would leak.

## 6. What Model produces

One artifact, `Model`, holding:

**Nodes** — a flat, indexed list of `(s, y_offset)`, each carrying the
declared node id it came from so loads and restraints can be attached by
name at L5 rather than by index.

**Elements** — a flat list, each with its two node indices, its arc extent,
its `line_id`, and its `owner` (the component code, or the pipeline). The
last two come through unchanged from `slay/model/mesh.py`, which already
carries them.

**Lines** — which elements belong to which structural line, so a consumer
can ask for the pipeline's elements without inspecting geometry.

**Junctions** — the resolved list: which node index is shared by which lines.

## 7. D2 — is `MeshTopology` needed? I propose not, and T3 proves it

The 12 Aug plan specifies a `MeshTopology` object holding
`chain_of_node` / `chain_of_elem` maps. It was invented because four places
had each improvised their own pipe-versus-frame mask. Taking them in turn
against what this design already carries:

| # | What needed a mask | Covered by |
|---|---|---|
| 1 | strain recovery needed a pipe-only variant | `[e for e in elements if e.line_id == 'pipeline']` |
| 2 | sliding-contact coefficients needed the pipe's own node list | the pipeline line's element node indices |
| 3 | plotting walked elements assuming one chain | iterate per `line_id` |
| 4 | frame nodes merging into the pipe by coordinate | **§4's integrity assertion** |

The first three are queries, and `line_id` / `owner` answer them without a
separate object. The fourth is not a query at all — it is the coordinate
dedup, and a mask would not have prevented it. §4 removes the cause instead
of masking the symptom.

**So: no `MeshTopology`.** T3's verification includes recovering the chain
partition from `line_id` alone, on a model with a GD-ST attached, which is
what turns this from an argument into evidence. If that check fails, the
object goes back in.

## 8. How it is built

**The header line.** A straight polyline from the Scene extent's low end to
its high end at `y_offset = 0`. Mandatory stations on it:

- the two extent ends;
- the two elastic-zone boundaries, because a material discontinuity must not
  be smeared across an element any more than a section change may be — the
  fourth MANDATORY reason, which `component_spec`'s `NodePriority` does not
  list and which Scene therefore declares;
- every structural node of every inline component, mapped from ILS-local
  position into `s`.

**Components with their own lines** — a GD-ST frame, a GD-SB trapezoid, a
GD-VLV stem, a GD-B branch — are meshed separately by the existing
`mesh_component`, in their own `(s, y_offset)` coordinates, and appended.

**Junctions** are then resolved: each `(node_id, target_line)` pair
declared by a component becomes a shared node index, and the §4 assertion
confirms nothing else shares coordinates.

**Connectors** are emitted as single 2-node elements, never subdivided.

**Global numbering** is assigned last, once every node exists.

## 9. What I would verify

| # | Check | Expected |
|---|---|---|
| 1 | Plain-pipe header meshes over the full extent | ~109 elements at 2×OD over 88 m, exact count recorded |
| 2 | Elastic-zone boundaries are nodes | exact nodes at s = −24 and +32 |
| 3 | **Coincidence ⟺ declared junction** | asserted on every model built, including all 7 EDAS archetypes |
| 4 | **Chain partition from `line_id` alone** | pipeline and GD-ST frame separable with no topology object (D2) |
| 5 | **Shift invariance** | two models built with the ILS at different `s` have identical element *counts and lengths*; only positions differ |
| 6 | Every mandatory station survives | component stations all present as nodes (G4) |
| 7 | Zero-length connector | its two nodes coincide, and the junction declares it |
| 8 | All 7 EDAS archetypes mesh | zero warnings on each |

Check 3 is the one that matters most: it is the guard against the
documented "two-point attachment became a continuous stiffener" failure, and
it is cheap.

Check 5 is where §2.5's claim stops being an assertion.

## 10. Questions for you

**1. ILS placement direction.** To map ILS-local positions into `s` I need
to know which way the ILS faces. I propose **local +x aligns with +s**, i.e.
toward the stinger, so `s = s_centre + x_local`. The alternative aligns it
with world +x, toward the vessel, and the two differ by a reflection — an
ILS with an asymmetric component (a GD-TT with unequal NIBs, a GD-B branch)
would be installed back-to-front under the wrong one. No default is safe
here, so I would rather have it stated.

**2. Scope of this card.** The milestone ladder needs only a plain-pipe
header for M1, but we have 7 EDAS archetypes that already build, and
exercising the splice and junction machinery against them now costs little
and de-risks T9 considerably. I propose building the full machinery and
verifying against the archetypes, while leaving component *contact
ownership* to T9 as planned. Say if you would rather keep T3 to plain pipe
only.

**3. Flowchart.** Unlike Scene, this module has real control flow —
chaining, station collection, junction resolution, numbering. A mermaid
flowchart looks worth drawing here. Agree?

---

## Action log

| Date | Action |
|---|---|
| 12 Sep 2026 | Draft written. §4 finding (kernel merges by coordinate) restates the card's junction rule as a Model integrity assertion. D2 answered in §7: no MeshTopology, with check 4 as the evidence. |

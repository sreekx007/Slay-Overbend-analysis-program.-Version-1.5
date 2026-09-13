# T3 — assembly specification

**Status:** RULED 13 Sep 2026. This supersedes `T3_model_spec.md` §8 and
answers **G6**.
**Card:** `docs/SLAY_BUILD_INSTRUCTION.md` §6 T3 · **Layer:** `model` (L4)

> How the pipeline, the components, the external structures and the
> connectors become one set of nodes and elements. The ruling is a four-pass
> build with an explicit merge tolerance, and a **two-layer node identity**
> that separates *what a node is* from *what number it gets*.

---

## 1. The principle

**Merging is the mesher's job, done deliberately, in a controlled order.
The solver takes what it is given and changes nothing.**

Today it is the other way round: the mesher declares nothing and the kernel
merges anything that happens to share a coordinate. That is why ILS-EASB's
straddle silently welds itself to the pipe (§6).

Two rules follow, and between them they replace coincidence-as-identity with
intent-as-identity:

1. **Within a pass**, coincident nodes merge — deliberately, with a stated
   tolerance of **0.01 m**.
2. **Across passes**, coincident nodes do *not* merge. They get separate
   numbers, separate rows in the stiffness matrix, and are joined only where
   a connector says so — through penalty constraints on the degrees of
   freedom that connector actually restrains.

> **Physical connectivity is ensured only where required.**

The 0.01 m tolerance exists to avoid slivers, not to define connectivity.
Two nodes 5 mm apart would otherwise produce a 5 mm element beside 800 mm
neighbours — a conditioning problem and a grading violation for no physical
gain.

**Verified, not assumed.** The closest *distinct* pair of structural nodes
anywhere in the published set is **0.176 m** (anchor `TT-1to4`, the
shallowest taper, `taperL` to `bodyL`), across all 7 archetypes and all 35
buildable anchors. The tolerance has a **17.6× margin** before it could
destroy a real feature.

| set | tightest distinct spacing | margin over 0.01 m |
|---|---|---|
| 7 archetypes | 0.200 m (`TT/weldL` .. `TT/taperL`) | 20× |
| 35 anchors | 0.176 m (`TT-1to4`) | 17.6× |

## 2. Two layers of node identity

| layer | what it is | example |
|---|---|---|
| **part node** | a *named* point that means something physically — a weld, a body station, a connector end | `W-TT-L`, `GDTT1-taperL`, `C3-P` |
| **mesh node** | an integer index in the assembled model, produced by subdividing each part element | `417` |

Part nodes are assigned in passes 1–4 below. **Then each part element is
meshed on its own**, and the mesher issues the final integer node and element
numbers.

Because connectivity is carried by the part layer and by the recorded
associations — never by position — two mesh nodes landing on the same spot is
harmless. They occupy separate rows of the stiffness matrix and are tied only
if something declares them tied.

## 3. Pass 1 — pipeline header and the in-wall components

Scan the ILS header line end to end. Merge coincident part nodes (0.01 m) and
assign IDs.

**In scope:** the pipeline header plus every **IW** component — the
`iw_ea_class` taxonomy already in `component_spec` names them, so this is a
query, not a list to maintain:

| class | codes |
|---|---|
| IW-A | GD-TP, GD-TT, GD-PIP |
| IW-P | GD-TP, GD-TT, GD-VLV, GD-HdPipe, GD-BrPipe |
| IW-B | GD-B |

**Primary line only in this pass:**

- **GD-PIP** — the **inner pipe** only. The outer pipe is a separate line and
  waits for pass 1b.
- **GD-VLV** — the nodes on the **body** only. The stem waits for pass 1b.

**Not in scope:** GD-ST and GD-SB (EA-ST, EA-SB). They are untouched here.
They may hold nodes coincident with pipeline or IW nodes — **they stay
separate.** This is the pass boundary that fixes §6.

### Node ID scheme

| prefix | meaning |
|---|---|
| `W-…` | a **weld** — an intersection between two components, or between a component and the header |
| `<COMP><n>-…` | a node on a component **body**, carrying the component's short code and instance number: `GDTT1-taperL`, `GDPIP2-conMid` |
| `C<n>-P` / `C<n>-E` | a **connector** end node — pipe/IW side and EA side (pass 3) |

Every part element carries a **line ID** and the IDs of its **two end nodes**.

## 4. Pass 1b — secondary lines of in-wall components

Component by component, take the lines attached to the main header line and
not yet processed:

- GD-PIP's **outer pipe**
- GD-VLV's **stem**
- GD-B's **branch** (its tee into the header is a declared junction, so the
  tee node is a weld — `W-…` — and merges)

Coincident nodes merge and are assigned IDs on the same rules as pass 1.

## 5. Pass 2 — the external structures

GD-ST and GD-SB. **Travel around the arc** — both are closed loops, which
`Polyline` already supports (`closed=True`) — assigning node and element IDs
exactly as in pass 1.

Merging happens **within this pass only**. A GD-SB node sitting at `y = 0`
does not see the pipeline nodes at all.

## 6. Why the pass structure is the fix — the ILS-EASB case

This is not hypothetical. `GD-SB` in the published set uses `P_vt = 0`, and at
`P_vt = 0` **seven of its nodes lie exactly on the pipe centreline**:

```
scTL   x = -4.0640  y = 0.0000
sslot1 x = -2.1675  y = 0.0000
sslot2 x = -1.0837  y = 0.0000
sslot3 x =  0.0000  y = 0.0000     <-- and x = 0 is the rig's load point
sslot4 x = +1.0837  y = 0.0000
sslot5 x = +2.1675  y = 0.0000
scTR   x = +4.0640  y = 0.0000
```

Under today's kernel, `sslot3` welds itself to the pipe's load node. Measured
across element sizes 4 × OD → 0.5 × OD and pad lengths 5 → 8 m: it merges
every time. The other six escape only because 1.0837 m does not happen to
divide into the 0.8128 m mesh spacing — arithmetic luck, not design.

**Under the pass structure it cannot happen at all.** GD-SB is a pass-2
component; the pipeline is pass 1; the two never see each other's
coordinates. The bolted slot connection stays a bolted slot connection,
attached through pass-3 connectors on the DOF it actually restrains.

Note the tolerance does *not* fix this and was never meant to — a larger
tolerance would make it worse. **The pass boundary is the fix.**

## 7. Pass 3 — connectors

For each connector on the header line and on the branch line, take its
length, then:

1. Add **two part nodes**, one at each end: `C<n>-P` (pipe/IW side) and
   `C<n>-E` (EA side).
2. These are **coincident with existing nodes by construction, and that is
   fine** — they are separate nodes with separate matrix rows.
3. **Record the associations**: `C<n>-P` ↔ the pipeline/IW node, `C<n>-E` ↔
   the EA component node. These are enforced later as **penalty constraints**.

### Which DOF each association ties

The pipe-side association is always **W** or **F** — **all three DOF tied**.

The EA-side association varies by connector type. `component_spec`'s
`CONNECTOR_OAM_CLASS` already fixes the kinematics; this is that map written
out as DOF:

| type | OAM class | ux | uy | rz | notes |
|---|---|---|---|---|---|
| `W` | FixedConnection | tied | tied | tied | girth weld |
| `F` | FixedConnection | tied | tied | tied | fixed attachment |
| `P` | MovableConnection | tied | tied | **free** | revolute — a pin |
| `S` | MovableConnection | ? | ? | tied | prismatic — **see Q1** |
| `D` | IntermittentConnection | gap-dependent | | | deadband `P_gap`, **nonlinear** |

`D` is genuinely a separate module, as you anticipated. It is an active-set
problem — engaged or free depending on a gap — which is **the same machinery
as roller contact**, and should reuse that rather than grow a second copy.

**G9 still stands until this lands.** "Never substitute F for P/S/D — the
solver implements F only; a P/S/D case must be refused, not approximated."
This design is the route to lifting G9, not an exemption from it. All seven
archetypes use `F` (`connection_system = 'F2'`), so **Group B can be built and
run on F alone first**, with P/S/D following.

## 8. Pass 4 — connector stiffness

> **Connector stiffness shall NOT be derived from its length. It shall equal
> the stiffness of a 1 × OD length of pipeline.**

`component_spec`'s `Connector` docstring reaches the same rule independently
and for the same reason: *"stiffness is an OVERRIDE and must never be derived
from length: a derivation would be undefined at exactly this legal case"* —
the legal case being a zero-length connector.

For the reference pipe (OD 0.4064 m, t 0.021 m, E 2.1 × 10¹¹ Pa), `L₀ = OD`:

| term | value |
|---|---|
| axial `EA/L₀` | 1.3139 × 10¹⁰ N/m |
| rotational `4EI/L₀` | 9.7865 × 10⁸ N·m/rad |
| shear `12EI/L₀³` | 1.7776 × 10¹⁰ N/m |

### Two consequences worth stating

**(a) It supersedes the mirrored presets.** `Connector.k_axial`, `k_shear`
and `k_rot` all default to `1.0e9`. That matches the rotational figure almost
exactly (1.02×) but is **13× soft in axial and 18× soft in shear**. Those
fields live in mirrored code (**G7** — never edited locally), so we do not
change them: **our physics layer derives connector stiffness from the rule
and ignores the presets.** If the presets should change, that is an upstream
request, not a local patch.

**(b) A zero-length connector is not an element at all.** The kernel computes
element stiffness as `EA/L₀` and `EI/L₀` from the *geometric* length, so a
connector of real length `L` gets the rule's stiffness by scaling its section:

    A_used = A_pipe × L / OD          I_used = I_pipe × L / OD

which gives `EA_used/L = EA_pipe/OD` exactly, with no kernel change. At
`L = 0` that scaling is undefined and the element is degenerate — and `L = 0`
is the **default**, and is what ILS-EASB actually uses (`P_vt = 0` ⇒
`y_struct = 0` ⇒ `L_conn = 0`). So:

> **If `L_conn = 0` there is no connector element — only the penalty tie
> between `C<n>-P` and `C<n>-E`. If `L_conn > 0` there is a beam element with
> the scaled section, plus a penalty tie at each end.**

## 9. What this settles about G6

**The kernel must identify nodes by ID, not by position** — my option (a),
now correct because the merging it used to do has moved into the mesher where
it is deliberate, ordered and bounded.

The amended guardrail:

> **G6 (amended).** `nlfea_v4.py` is frozen against *convenience* changes. A
> change is permitted only where the kernel's behaviour is provably wrong for
> a model this program must build, and only with (a) a failing test written
> first, (b) the change scoped as narrowly as the defect, and (c) the
> validated case set re-run and recorded.

**Scope of the edit:** `MeshedStructure._mesh()` keys `get_or_add` on the
user node id; `user_node_to_mesh` is built by identity rather than by
coordinate lookup. With `seed = 1` on every element we emit (T3 spec §5),
there are no interior nodes, so the mesh node set becomes exactly the user
node set, in order.

**Regression cost, stated plainly:** any existing model that relied on
coordinate coincidence to weld two lines will come apart. That is the
intended behaviour change and the reason clause (c) exists — the validated
set must be re-run and recorded, not assumed. Our own rig is unaffected: it
already asserts `n_nodes == len(nodes)` and passes.

**Not a G5 problem.** G5 forbids `k_spring` — a *contact* spring at a roller,
rejected 12 Aug 2026 after producing NaN on a shroud contact-release case.
Penalty enforcement of a *constraint* is a different mechanism and the kernel
already uses it for boundary conditions (`apply_bcs_sparse`). The lesson that
carries over is conditioning: **penalty stiffness must be scaled against the
structural stiffness, never set as an absolute constant** — which is exactly
what pass 4 does.

## 10. Build order

```
pass 1   pipeline header + IW components, primary lines      merge within
pass 1b  IW secondary lines (PIP outer, VLV stem, GD-B)      merge within
pass 2   EA-ST / EA-SB, around the arc                       merge within
pass 3   connector part nodes + recorded associations        never merge
pass 4   connector stiffness from the 1 x OD rule
---
then     mesh each part element separately
         assign final integer node and element numbers
```

## 11. Questions

**1. The `S` (prismatic) connector — which translation slides?** The map
fixes `rz` as tied and one translation as free, but not which. For a
connector running transverse to the pipe, "slides along its own axis" (axial
free, shear tied) and "slides along the pipe" (shear free, axial tied) are
both defensible and they are different joints. No safe default.

**2. Penalty stiffness magnitude.** Pass 4 sets the *connector element*
stiffness. The *penalty* that enforces each association is a separate number.
Proposal: 10³ × the local structural stiffness — stiff enough to tie, soft
enough to keep the matrix conditioned. Worth pinning by experiment on the
first EA case rather than by assertion.

**3. `D` connectors.** Confirm these follow the roller-contact active-set
module rather than a second implementation, and that they are out of scope
until that module exists.

---

## Action log

| Date | Action |
|---|---|
| 13 Sep 2026 | Assembly ruled: four-pass build, 0.01 m merge tolerance within a pass and never across, two-layer node identity, connectors as recorded associations enforced by penalty constraints, connector stiffness from a 1 × OD length of pipeline. Merge tolerance verified against all 7 archetypes and 35 anchors — tightest distinct spacing 0.176 m, a 17.6× margin. G6 answered: the kernel keys nodes by ID, since deliberate merging now lives in the mesher. |

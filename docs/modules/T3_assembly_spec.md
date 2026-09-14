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

### The frame the constraints live in

Every DOF rule below is stated in the **EA component's local frame**, not in
global axes:

| axis | direction |
|---|---|
| **local x** | along the **slope of the pipeline / IW the connector attaches to** — the tangential direction |
| **local y** | perpendicular to that — which is the connector's own axis |
| **rz** | rotation, frame-independent |

**This frame co-rotates, and that is not optional.** The pipe slope runs from
0° at SR1 to **32.4° at SR7** on the default R = 85 m stinger:

| | SR1 | SR2 | SR3 | SR4 | SR5 | SR6 | SR7 |
|---|---|---|---|---|---|---|---|
| slope | 0.00° | 5.39° | 10.79° | 16.18° | 21.57° | 26.96° | 32.36° |

A constraint written against a fixed global direction would be **up to 32°
wrong** by the time the ILS reaches the stinger tip — and the mesh's reference
configuration is straight (`T3_model_spec.md` §3), so it starts at 0° and
rotates as the solve proceeds. A sliding joint that slides in the wrong
direction is not an approximation of the right one; it restrains the thing it
was meant to release.

**Consequence for implementation.** `apply_bcs_sparse` applies penalties to
**global DOF indices**. A constraint aligned with a co-rotating local axis is
a *skewed* constraint and is not expressible that way. Any connector whose
rule below is not "all DOF tied" therefore needs the separate module — the
skew is what makes it separate, as much as the nonlinearity.

### Which DOF each association ties

The **pipe-side** association (`C<n>-P` ↔ pipeline/IW node) is always **W** or
**F**: all three DOF tied. Frame does not matter when everything is tied.

The **EA-side** association (`C<n>-E` ↔ EA node) varies by joint type.
`component_spec`'s `CONNECTOR_OAM_CLASS` fixes the kinematics; this writes
them out as DOF in the local frame above:

| type | OAM class | local x (along slope) | local y (perpendicular) | rz | skewed? |
|---|---|---|---|---|---|
| `W` | FixedConnection | tied | tied | tied | no |
| `F` | FixedConnection | tied | tied | tied | no |
| `P` | MovableConnection | tied | tied | **free** | no — rz is frame-free |
| `S` | MovableConnection | **free — slides along the slope** | tied | tied | **yes** |
| `D` | IntermittentConnection | **free, always** | **deadband ±`P_gap`** | **free, always** | **yes** |

**`S` — RULED 13 Sep 2026.** Free to slide along the **local x axis of the
EA-ST**, i.e. along the slope direction of the pipeline/IW it attaches to.
Not along its own axis. This was the open question and it is the answer that
makes physical sense for a slotted support: the frame is free to travel with
the pipe as the pipe stretches and rotates beneath it, while still carrying
load across the gap.

**`D` — RULED 13 Sep 2026, and it is a deadband, not a contact gap.**

A `D` connector is a **bidirectional support**. It engages only once the
displacement **perpendicular to the EA component slope** — the local y
direction, the connector's own axis — exceeds `P_gap`.

This corrects the shape I proposed earlier. Roller contact is **unilateral**:
the gap closes in one direction and uplift is simply free. A `D` connector is
a **symmetric deadband**: free within ±`P_gap`, engaged beyond it **in either
direction**.

```
        engaged          free          engaged
    <---------------|--------------|--------------->
                 -P_gap     0     +P_gap        local y
```

It is a **pure support**: local x and rz are **never** restrained, in either
state. A `D` carries load across its own axis once the deadband closes, and
does nothing else — it never restrains sliding, and it never restrains
rotation.

So it shares the **machinery** with roller contact — an active set, re-solved
as the state changes — but not the **rule**. They differ by one condition,
and the module should take the condition as a parameter rather than grow two
implementations. That is the reuse worth having; "same as contact" would have
been wrong.

### The rule a pure support forces: layout adequacy

A `D` that restrains nothing while open cannot hold a structure up on its
own. So the connector layout as a whole must restrain all three planar
rigid-body DOF of the EA structure — **and must do so in the weakest state,
with every deadband open**, or the first solve increment meets a singular
matrix.

Restraint in the EA local frame, per joint type:

| | local x | local y | rz |
|---|---|---|---|
| `F`, `W` | ✓ | ✓ | ✓ |
| `P` | ✓ | ✓ | — (revolute) |
| `S` | — (slides) | ✓ | ✓ |
| `D` open | — | — | — |
| `D` shut | — | ✓ | — |

Rotation also counts as restrained when **two or more connectors tie local y
at different x** — a couple.

**Checked against all six named systems, with every `D` gap open:**

| system | layout | gap open | gap shut |
|---|---|---|---|
| `F1` | –/–/F/–/– | OK | OK |
| `F2` | –/F/–/F/– | OK | OK |
| `F1D` | D/–/F/–/D | OK | OK |
| `F2D` | D/F/–/F/D | OK | OK |
| `PS` | –/P/–/S/– | OK | OK |
| `PSD` | D/P/–/S/D | OK | OK |

Every published layout is adequate in its weakest state, so ruling `D` a pure
support introduces no mechanism anywhere in the confirmed set. `PS` is worth
reading once: `P` supplies local x, `S` supplies `rz`, and each supplies
local y — neither is sufficient alone and together they are exactly
determinate.

**But `ConnectionSystem` accepts any 5-tuple**, so an adequate layout is not
guaranteed by construction:

    D / - / - / - / D     open:  x ✗  y ✗  rz ✗      shut:  x ✗  y ✓  rz ✓

Singular in both states, and in **local x** even when both gaps are shut.
Legal to build, impossible to solve.

> **Validation rule for the physics layer:** a connector layout must restrain
> local x, local y and rz with every `D` treated as open. Refuse the layout
> otherwise — refuse, per **G9**, never quietly stiffen something to rescue
> it.

This is a generic check on the tuple, not a whitelist of the six systems, so
a user-defined layout is judged on the same terms as a published one.

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

### The rule is absolute, and that is the point

**Every connector's stiffness is that of a 1 × OD length of pipeline,
whatever the connector's own length is.** Length never enters the stiffness
at all. `ConnectorSpec.length` is carried for geometry and reporting, never
for stiffness.

**So a zero-length connector is not a special case.** It carries the same
stiffness as every other connector, and it is a real element like every other
connector. This is the whole reason the rule is not length-derived: zero
length is legal, it is the *default*, and ILS-EASB uses it -- so a
length-derived stiffness would be undefined exactly where the default lands.

An earlier draft of this spec said a zero-length connector was "not an
element at all -- only the penalty tie". **That was wrong** and the
implementation inherited the error. It treated the legal default as a
degenerate case needing an exception, which is the opposite of what the rule
is for.

### It supersedes the mirrored presets

`Connector.k_axial`, `k_shear` and `k_rot` all default to `1.0e9`. That
matches the rotational figure almost exactly (1.02×) but is **13× soft in
axial and 18× soft in shear**. Those fields live in mirrored code (**G7** --
never edited locally), so we do not change them: **our physics layer derives
connector stiffness from the rule and ignores the presets.** If the presets
should change, that is an upstream request, not a local patch.

### What L5 has to build, and it is not optional

The rule means the connector element's stiffness is **prescribed**, not
derived from its geometry. `nlfea_v4`'s corotational element builds `EA/L0`
and `EI/L0` from the node coordinates and divides by the deformed length
`Ld`, so a zero-length element makes it divide by zero.

**Observed, not predicted.** Assembling ILS-EASB and calling `assemble()`
gives `RuntimeWarning: divide by zero` at `nlfea_v4.py:1216` and a stiffness
matrix carrying `inf`.

Two approaches that do *not* work:

- **Scale the section by `L/OD`** (`A_used = A_pipe·L/OD`,
  `I_used = I_pipe·L/OD`). This reproduces the local terms exactly for a
  non-zero length -- but it is still a derivation from length, and it breaks
  at `L = 0`, which is the default. It also leaves the transverse term
  `12EI/L³` following the real length rather than `OD`, so it does not even
  give a 1 × OD element for the non-zero cases.
- **Skip the element and keep only the penalty tie.** That is the error this
  section corrects: it deletes stiffness the rule says is there.

What works is a **prescribed-stiffness element**: form the 6 × 6 of a 1 × OD
pipe element once and use it for every connector, oriented in the EA local
frame (§7) rather than from the element's own geometry -- which a zero-length
element does not have. That frame is already needed for `S` and `D`, so it is
one mechanism serving both.

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

## 11. Open items

Every question of 13 Sep is answered. What is left is one thing to measure
and one module to scope — no open decisions.

**1. Penalty stiffness magnitude — RULED: measure it.** Pass 4 sets the
*connector element* stiffness; the *penalty* enforcing each association is a
separate number. Starting point 10³ × the local structural stiffness, then
pinned by experiment on the first EA case. G5's lesson applies —
conditioning, not magnitude, is what failed before — so the experiment
records the residual and the condition number, not just whether it ran.

**2. The skewed-constraint module.** `S` and `D` both need constraints
aligned with a co-rotating local axis, which `apply_bcs_sparse` cannot
express (§7). Scoping that module is its own card. Nothing above it is
blocked: **`F` needs none of it**, and all seven archetypes use `F`.

### Staging

| stage | needs | unblocks |
|---|---|---|
| **1** | passes 1–4, `F`/`W` only, all DOF tied | all 7 archetypes, Group A and Group B |
| **2** | penalty experiment | the stiffness number, measured |
| **3** | skewed constraints, co-rotating | `P` (rz free — no skew, could come earlier), then `S` |
| **4** | active set with a deadband condition | `D` |

**G9 stands until stage 3–4 land.** A `P`/`S`/`D` case is refused, never
approximated by `F`.

---

## Penalty constraints — measured 13 Sep 2026

`tools/study_connectors.py` ties the GD-ST frame to fixed nodes through real
connectors, on all five named layouts. First working penalty constraints, and
the first prescribed-stiffness connector element.

**The rig.** Bottom node fixed in all DOF (where the pipe will be) → connector
element 0.5 × OD long → top node → penalty tie to the frame slot node, with
the DOF pattern set by the joint type. Load 20/200 kN at the top-chord centre.

### Regularisation — the working penalty was measured, not chosen

`nlfea_v4.apply_bcs_sparse` scales its penalty to `K.diagonal().max() * 1e8`
— the **global** maximum. A frame matrix's translational and rotational
diagonals differ by orders of magnitude, so a global scale makes the condition
number carry that whole spread on top of the penalty. Scaling to the **local**
diagonals each constraint ties, `k_pen = α · max(K[a,a], K[b,b])`, makes
conditioning grow with α alone. Sweeping α on F2 at 200 kN:

| α | δ (mm) | violation (mm) | cond(K) |
|---|---|---|---|
| 10² | 2.701813 | 4.8 × 10⁻⁴ | 3.9 × 10⁷ |
| 10³ | 2.701169 | 4.8 × 10⁻⁵ | 3.9 × 10⁹ |
| 10⁴ | 2.701105 | 4.8 × 10⁻⁶ | 3.9 × 10¹¹ |
| **10⁵** | **2.701098** | **4.8 × 10⁻⁷** | **3.9 × 10¹³** |
| 10⁶ | 2.701098 | 4.8 × 10⁻⁸ | 3.9 × 10¹⁵ |
| 10⁹ | 2.701098 | 4.8 × 10⁻¹¹ | 2.0 × 10²¹ |
| 10¹² | 2.701098 | 4.8 × 10⁻¹⁴ | 2.0 × 10²⁷ |

**α = 10⁵.** The displacement has converged to six figures, the violation is
half a nanometre, and conditioning sits two decades below what double
precision carries. Everything past it buys precision nobody needs and pays for
it in conditioning.

### Results, in the order asked for

| layout | slots | δ at 200 kN | ΣR |
|---|---|---|---|
| F1 | F @ 0 | 3.71422 mm | 200.000 kN |
| F2 | F @ ±1.084 | 2.70110 mm | 200.000 kN |
| PS | P @ +1.084, S @ −1.084 | 2.93552 mm | 200.000 kN |
| PSD | + D @ ±2.167 | 2.93552 mm | 200.000 kN |
| F2D | + D @ ±2.167 | 2.70110 mm | 200.000 kN |

F1 is softest — one support point against two. PS is 8.7 % softer than F2 on
the same two slots, because `P` frees rotation at one and `S` frees sliding at
the other. **PSD and F2D are bit-identical to PS and F2**, because a `D`
restrains nothing while open and none of them closes: the largest separation
across a `D` is 0.61 mm against a 1 mm deadband.

### An engaged deadband holds AT the gap, not at zero

This was wrong first time and the failure is worth keeping. Enforcing
`u_a − u_b = 0` on an engaged `D` drags the node back to coincidence, which
drops the separation below the gap, which releases the connector, which lets
it separate again. The active set chattered — four flips, never settling, and
the reported state disagreed with the returned displacement.

The signature has to be **`u_a − u_b = ± P_gap`**, and release has to test the
**force direction**, not the separation: at engagement the separation sits at
the gap by construction, so testing it again releases every time.

Shrinking the gap on PSD at 200 kN, with that fixed:

| `P_gap` | engaged | flips | δ (mm) |
|---|---|---|---|
| 1.000 mm | – – – – | 0 | 2.93552 |
| 0.600 mm | − . . . | 1 | 2.92808 |
| 0.500 mm | − . . . | 1 | 2.84427 |
| 0.300 mm | − . . − | 1 | 2.49554 |
| 0.100 mm | − . . − | 1 | 2.14434 |
| 0.030 mm | − . . − | 1 | 2.02142 |

Monotone, settles in one flip, and approaches the rigid-support limit as the
gap closes. At 0.6 mm only the `D` with 0.609 mm of separation engages, which
matches the measured separations exactly.

**Without this sweep the D rows above would be indistinguishable from a D
that does not work.** Engagement has to be seen changing the answer.

### Still owed

The constraints here are applied in **global axes**. The frame is horizontal
in this study, so EA-ST local x *is* global s and the rotations are ~10⁻⁴ rad
— exact at the reference configuration and negligible beyond it. It is not
the co-rotating form the stinger needs, where the local axis turns up to
32.4°. `S` and `D` are the types that would notice.

---

## ILS-EAST complete — 14 Sep 2026

`tools/study_east_full.py`. The first Group B case solved end to end, with
everything from `build_model`: 45 nodes, 42 elements (22 pipeline, 18 frame,
2 connector), 4 associations. Both ties applied as penalty constraints, so
the load path closes:

    pipe node  ~~W~~  C-P  --[ connector ]--  C-E  ~~F~~  frame slot

Fixed at both pipeline ends, loaded at the layout midpoint on the header.

| P | δ pipe | δ frame | ΣR | violation | σ pipe | σ frame |
|---|---|---|---|---|---|---|
| 20 kN | 5.04466 mm | 4.95436 mm | 20.000 kN | 3.7 × 10⁻⁷ mm | 18.1 MPa | 1.6 MPa |
| 200 kN | 50.49254 mm | 49.54476 mm | 200.000 kN | 3.6 × 10⁻⁶ mm | 180.5 MPa | 18.0 MPa |

### The comparison is the result

A **bare pipe of the same span** deflects 6.63578 mm at 20 kN. With the ILS on
it: **5.04466 mm — 24 % stiffer.** The frame is not scenery; it takes load
back into the pipe through the connectors.

And the stress diagram says where. Between the two connector stations the
pipe's peak stress **drops from 170 MPa to 64 MPa** — the frame bridges that
span and shields it — with the concentrations sitting just *outside* the
connectors. A model whose connectors did nothing would show a plain
fixed-fixed diagram peaking at midspan instead. That contrast is what
`test_pipe_is_shielded_between_the_connectors` asserts.

The frame rides down with the pipe (0.09 mm apart over a 0.61 m connector),
which is what all-DOF ties should do.

### The connector length here is 0.6096 m, not 0.5 × OD

The 0.5 × OD of the standalone study was a stand-in when there was no pipe to
span to. Now the geometry sets it: pipe centreline at `y = 0`, frame bottom
chord at `y = −0.6096`. **The stiffness is identical either way**, which is
pass 4's whole point.

### One bug, and it is a trap worth naming

`MeshedStructure._mesh` assigns mesh indices in **element-encounter order**,
so `user_node_to_mesh` is a *permutation* of our node ids and **not the
identity**. Writing connector stiffness at `3 * node_id` put it on the wrong
rows and left four frame nodes with empty ones — twelve zero diagonals and an
exactly singular matrix.

`test_kernel_leaves_the_model_intact` asserts the map is a **bijection**, and
a bijection is all it asserts. **Every caller has to go through it.**
`test_node_map_is_not_the_identity` pins that it really is a permutation
here, so the indirection cannot later look redundant and be removed.

The earlier studies escaped it by construction — their elements referenced
nodes in id order — which is exactly why it surfaced only on the first model
with a frame reached late.

### Group B's blocker test is not contradicted

`test_group_b_cannot_yet_be_solved` still asserts ILS-EAST's own elements are
singular. That remains true and remains the right thing to assert: it says the
associations are **declared and not yet enforced anywhere in the package**.
This study enforces them from `tools/`. The two flip together when the penalty
module moves into `slay/solve/`.

---

## Action log

| Date | Action |
|---|---|
| 13 Sep 2026 | Connector stiffness rule restated as ABSOLUTE: every connector carries the stiffness of a 1 × OD length of pipeline whatever its own length, so a zero-length one is an ordinary case and an ordinary element. Corrects an earlier claim in this spec that a zero-length connector was no element at all — the legal default was being treated as a degenerate case needing an exception, which is the opposite of what the rule is for. Implementation follows: all three Group B archetypes now carry connector elements, ILS-EASB's at length 0. Confirms L5 needs a prescribed-stiffness element type: the corotational kernel divides by the deformed length and returns inf for a zero-length element, observed at `nlfea_v4.py:1216`. |
| 13 Sep 2026 | `D` ruled a **pure support**: local x and rz never restrained, in either state; only the perpendicular deadband. That forces a layout-adequacy rule, since a support that holds nothing while open cannot restrain a structure alone — checked against all six named systems with every gap open, and all six are adequate (`PS` exactly so: `P` gives local x, `S` gives rz). `ConnectionSystem` accepts any 5-tuple though, and `D/-/-/-/D` is legal to build and singular in both states, so the check is generic on the tuple rather than a whitelist. |
| 13 Sep 2026 | Connector kinematics ruled. `S` slides along the EA-ST **local x** — the slope direction of the pipeline/IW it attaches to, not its own axis. `D` is a **symmetric ±`P_gap` deadband** on the perpendicular (local y) direction, bidirectional — which corrects the earlier claim that it is the same rule as roller contact: it shares the active-set machinery but not the condition, one being unilateral and the other a deadband. Both constraints live in a **co-rotating local frame**: the pipe slope runs 0° to 32.4° across the stinger at R = 85 m, so a globally-aligned constraint would be up to 32° wrong, and `apply_bcs_sparse` cannot express a skewed constraint — that, as much as the nonlinearity, is what makes the separate module necessary. Staging recorded: `F`-only first, which needs none of it. |
| 13 Sep 2026 | Assembly ruled: four-pass build, 0.01 m merge tolerance within a pass and never across, two-layer node identity, connectors as recorded associations enforced by penalty constraints, connector stiffness from a 1 × OD length of pipeline. Merge tolerance verified against all 7 archetypes and 35 anchors — tightest distinct spacing 0.176 m, a 17.6× margin. G6 answered: the kernel keys nodes by ID, since deliberate merging now lives in the mesher. |

---

## Implementation notes — 13 Sep 2026

Stage 1 is built: `rebuild/slay/model/parts.py` (part layer, merge registry,
joint kinematics) and `rebuild/slay/model/assemble.py` (the four passes),
with 62 tests in `rebuild/tests/test_model.py`.

**All seven archetypes assemble.** Plain pipe gives 110 nodes / 109 elements
over the 88 m extent at 2 × OD, which is the figure `T3_model_spec.md` §9
predicted.

| archetype | nodes | elements | associations | lines |
|---|---|---|---|---|
| ILS-TP | 111 | 110 | 0 | 1 |
| ILS-TT | 119 | 118 | 0 | 1 |
| ILS-SH | 110 | 109 | 0 | 1 |
| ILS-SHTP | 111 | 110 | 0 | 1 |
| ILS-EAST | 132 | 129 | 4 | 4 |
| ILS-EASB | 134 | **131** | 4 | 2 |
| ILS-ILT | 138 | 135 | 4 | 5 |

ILS-EASB gained two elements on 13 Sep when the stiffness rule was restated:
its zero-length connectors are ordinary connectors and carry ordinary
elements.

### Three things the build found

**1. A declared junction needs a station, and the declaration is what creates
it.** ILS-ILT would not assemble: GD-B declares a tee onto the pipeline, but
GD-B has no line *on* the pipeline, so pass 1 never registered a header node
there and pass 1b had nothing to resolve into. Junction targets are now
collected in pass 0 alongside the connector stations — same reasoning, same
place: the position is known up front, the tie is still built later.

**2. The two ends of a connector are separate populations.** A zero-length
connector puts `C<n>-P` and `C<n>-E` at the same point, and the within-pass
merge promptly fused them — which would have deleted the connector by
collapsing the very pair the penalty tie joins. They now occupy passes 4 and
5. The pass mechanism that keeps the straddle off the pipe is the same one
that keeps a connector from eating itself.

**3. A connector never goes through the line mesher.** It is one element by
definition — never subdivided — and a zero-length one has no arc coordinate
for the mesher to work in. Connector elements are emitted straight through,
which is what lets the stiffness rule stay independent of length. Every part
node named by an association is also materialised whether or not an element
touches it, since the penalty tie needs a DOF row at each end.

### The EASB case, now verified

At slot 2 (`s = 1.0837`, `y = 0`) **four distinct model nodes** now stack: the
header station, GD-SB's own `sslot2`, and both ends of the zero-length
connector. Under the old kernel that was **one** node. None of GD-SB's seven
centreline nodes is a pass-1 node, so the straddle cannot weld itself into the
pipe wall regardless of element size.

### Shift invariance, corrected

`T3_model_spec.md` §9 check 5 claimed whole-model invariance. Measured, that
is too strong and the correction is worth keeping:

- **The ILS's own element lengths are bit-identical** at `s_centre` = 0, +6
  and −11.5 m, on all seven archetypes.
- **The plain-pipe filler cannot be.** The extent is fixed while the ILS moves
  within it, so the gaps either side change length and their
  `round(L / target)` subdivision changes too — a 6 m shift is 7.38 elements.
  One gap gains one, the other loses one.

The component's discretisation is the one that matters: that is where strain
is reported, and that is what the mesher must not perturb.

### G6 clause (c) — the validated set, re-run

`tools/spike_mesher_rig.py` before and after the kernel change: **every
numerical figure is bit-identical.** The only differences are timing jitter
and the coincident-node probe, which now reports 4 mesh nodes from 4 declared
rather than 3, and "kept separate" rather than "MERGED" — the change itself.

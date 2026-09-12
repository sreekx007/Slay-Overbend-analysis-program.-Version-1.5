# T3 — mesher test plan

**Status:** DRAFT for review. Companion to `docs/modules/T3_model_spec.md`.
**Card:** `docs/SLAY_BUILD_INSTRUCTION.md` §6 T3 · **Layer:** `model` (L4)
**Every number below was produced by a working spike**, not estimated. What
the spike is and how to re-run it is in §11.

> Four findings came out of building this plan. Two of them reach outside
> T3: §7 amends **G6** and needs your ruling before any kernel line is
> touched; §8 changes how the solver must be called in every card that
> follows, and needs no ruling but does need reading.

---

## 1. The rig you specified

| | |
|---|---|
| source of geometry | EDAS archetype → `ils_builder.build_ils()` → `ILS.assembly` |
| pipeline | 6 m of plain pipe beyond **each end of the component extent** |
| ILS placement | component extent centred on the model; load point at ILS-local `x = 0` |
| section | **the pipeline section, applied to every element** |
| restraint | both pipeline ends, all three DOF |
| load | 200 kN point load at the component body centre |
| solver | `nlfea_v4.solve_step` |
| kernel rule | the solver must not merge or renumber the nodes it is given |

Model length is therefore `L = span + 12 m` and the load sits at
`a = |extent_lo| + 6 m` from the low end.

## 2. The instruction that does the work

**"Apply pipeline section to all components"** is not a simplification for
convenience — it is what makes the rig a *mesher* test rather than another
whole-program test.

With one section everywhere the beam is **prismatic**. A prismatic
Euler–Bernoulli beam loaded only at nodes has an exact solution that is
piecewise cubic, and the element's shape functions are cubic, so the exact
solution *lies inside the finite-element space*. The discretisation
contributes nothing. Change the number of elements, change where the interior
nodes sit, change their order — the answer does not move. (That is a *linear*
argument, and §3 measures how far the specified rig sits from linear.)

That is the whole test. **Anything the mesher does must be invisible in the
result.** When the answer moves, the mesher moved it, and nothing else can
be blamed: not the section, not the material, not the contact model, none of
which is present.

It also keeps the rig honest about what it is *not* testing. Section
transitions, shrouds, plasticity and contact are all deliberately switched
off here. They get their own cards.

## 3. Two regimes, and only one of them is exact

The kernel is a **corotational** beam (`assemble()` in `nlfea_v4.py`:
element-local axial stretch plus two relative end rotations, rotated into the
deformed frame). It is geometrically nonlinear, and both ends of the rig are
axially restrained, so the beam picks up **membrane stiffening** as it
deflects. The §2 exactness argument is a *linear* argument; it survives only
while the nonlinear terms are negligible.

The spike measures exactly how far from linear the specified rig is:

| P | ILS-TP | ILS-TT | ILS-SH | ILS-SHTP |
|---|---|---|---|---|
| **20 kN** | −0.002 % | −0.004 % | −0.012 % | −0.012 % |
| **200 kN** | −0.164 % | −0.361 % | −1.175 % | −1.178 % |

(FE deflection against the linear closed form; negative = FE is stiffer.)

The 200 kN rig is **1.2 % away from linear** on the longest case. That is
real physics and the solver is right to report it — a Rayleigh estimate of
the membrane term, `P = kδ(1 + δ²/16r²)` with `r = √(I/A) = 0.1365 m`,
predicts 0.18 / 0.38 / 1.25 %, matching every measurement to within 8 %.
But it is 400× larger than the mesh sensitivity we are trying to see, so
**the 200 kN rig cannot resolve a meshing error by comparison with a closed
form.** It can only resolve one by comparison with *another mesh* — and even
then only once the solver is called properly (§8).

So the plan runs the rig at two loads:

- **20 kN — the analytical regime.** Nonlinearity is 1.2 × 10⁻⁴, itself
  predicted to within 8 % by the same formula, so the closed form is usable
  as an absolute reference — and a 15× refinement moves the answer by only
  5.5 × 10⁻⁶, so the mesh really is invisible here. This is where "the mesher
  built the right beam" gets checked.
- **200 kN — the specified regime.** Absolute values are whatever the
  nonlinear solver says. Here the exact invariances still hold — translation
  and node ordering are good to 10⁻¹⁴ however nonlinear the response — and
  the *residual* mesh sensitivity, 2.95 × 10⁻⁵, becomes a pinned figure
  rather than a bound (§8).

Adding the 20 kN run costs one extra solve per case and buys the only
absolute check in the plan. The 200 kN run stays exactly as you specified it.

## 4. The case set splits in two, and the evidence says where

Reading the archetypes' structural lines:

| archetype | lines on the pipeline axis | own lines | junctions declared |
|---|---|---|---|
| ILS-TP | `pipeline` | — | — |
| ILS-TT | `pipeline` | — | — |
| ILS-SH | — (GD-SH declares **no** structural lines) | — | — |
| ILS-SHTP | `pipeline` (the GD-TP) | — | — |
| ILS-EAST | — | `GD-ST@+0.0000:frame` | **none** |
| ILS-EASB | — | `GD-SB@+0.0000:frame` | **none** |
| ILS-ILT | — | `GD-ST@+1.2192:frame`, `GD-BL@+0.0000:branch` | branch → `pipeline` |

**Group A — prismatic (ILS-TP, ILS-TT, ILS-SH, ILS-SHTP).** Everything these
archetypes contribute lives on the pipeline axis, and with the pipeline
section applied everywhere they reduce to a uniform beam. They are the
mesher cases: fully analytical, and they run today.

**Group B — attached (ILS-EAST, ILS-EASB, ILS-ILT).** These carry a frame on
its own line, and **that line declares no junction to the pipeline**. The
attachment is made at the ILS level by `ILS.connectors_of()`, which returns
an axial station and a *moment arm* — no node, no second line, no geometry.
Assembled naively, the frame floats: rigid-body modes, singular stiffness
matrix, no solution.

That is a genuine design question about how a connector becomes elements,
and it is not the mesher's question. **Group B is deferred to the card that
settles connector modelling**, with one test written now (B0 below) that
pins the blocker so it cannot be forgotten.

**The pair that matters most is already in Group A.** ILS-SH and ILS-SHTP
have identical extents (±3.048 m) and therefore identical length and load
position — but ILS-SHTP's GD-TP adds mandatory stations at ±0.508 m, so the
mesher produces **22 uniform 0.8225 m elements for one and 24 graded
0.508–0.776 m elements for the other**. Same beam, same load, two different
meshes. They must agree, and that comparison needs no closed form at all.

## 5. Expected values

Pipe: OD 0.4064 m, t 0.021 m, E 2.100 × 10¹¹ Pa
→ `I = 4.734802e-04 m⁴`, `A = 0.025426 m²`, `EI = 9.943085e+07 N·m²`,
`Z = I/c = 2.330119e-03 m³`, `r = √(I/A) = 0.13646 m`.

Fixed–fixed, point load at `a` from the low end, `b = L − a`:
`δ = Pa³b³/3EI·L³`, `M_lo = Pab²/L²`, `M_hi = Pa²b/L²`,
`M_load = 2Pa²b²/L³`. Group A is symmetric, so all three moments coincide.

**Group A, mesh produced by `mesh_line` at 2 × OD:**

| archetype | L (m) | a (m) | elements | element length | max adj. ratio |
|---|---|---|---|---|---|
| ILS-TP | 13.000 | 6.500 | 16 | 0.500 – 0.857 | 1.714 |
| ILS-TT | 14.808 | 7.404 | 26 | 0.200 – 0.857 | 2.000 |
| ILS-SH | 18.096 | 9.048 | 22 | 0.8225 uniform | 1.000 |
| ILS-SHTP | 18.096 | 9.048 | 24 | 0.508 – 0.776 | 1.528 |

**At 20 kN — the analytical reference:**

| archetype | δ closed form | δ solved | diff | M_max | σ_max |
|---|---|---|---|---|---|
| ILS-TP | 2.30164 mm | 2.30160 mm | −0.002 % | 32.5 kN·m | 13.9 MPa |
| ILS-TT | 3.40171 mm | 3.40158 mm | −0.004 % | 37.0 kN·m | 15.9 MPa |
| ILS-SH | 6.20805 mm | 6.20730 mm | −0.012 % | 45.2 kN·m | 19.4 MPa |
| ILS-SHTP | 6.20805 mm | 6.20729 mm | −0.012 % | 45.2 kN·m | 19.4 MPa |

**At 200 kN — the rig as specified:**

| archetype | δ closed form | δ solved | measured | predicted | M_max | σ_max |
|---|---|---|---|---|---|---|
| ILS-TP | 23.0164 mm | 22.9787 mm | 0.164 % | 0.177 % | 325.0 kN·m | 139.5 MPa |
| ILS-TT | 34.0171 mm | 33.8943 mm | 0.361 % | 0.384 % | 370.2 kN·m | 158.9 MPa |
| ILS-SH | 62.0805 mm | 61.3508 mm | 1.175 % | 1.246 % | 452.4 kN·m | 194.2 MPa |
| ILS-SHTP | 62.0805 mm | 61.3490 mm | 1.178 % | 1.246 % | 452.4 kN·m | 194.2 MPa |

The last two columns are the membrane stiffening measured and the Rayleigh
estimate of it — agreement to within 8 % on every case, which is what turns
"the solver is stiffer than the closed form" into a quantity worth asserting.

All solved figures above were measured at `tol = 1e-6`, `n_increments = 20`
(§8), with a linear-elastic `Material` (§9). Those settings are part of the
expected value and change it if changed.

**Every case stays elastic.** The worst fibre stress is 194 MPa against a
360 MPa first yield (`slay/data/materials.py`) — 46 % margin. That is
deliberate: with no plasticity anywhere in the rig, the material model cannot
absorb a meshing error and hide it.

## 6. The test schedule

### Tier 1 — mesher alone, no solver

Cheap, exact, and they fail first when something breaks.

| # | Check | Expected |
|---|---|---|
| 1.1 | element counts and lengths | the §5 table, pinned |
| 1.2 | every mandatory station is a node | zero `not snapped` warnings on all 7 archetypes |
| 1.3 | a node exists at the load point | required — `JointLoad` names a node id, so without one the rig cannot be built at all |
| 1.4 | adjacent length ratio | ≤ 2.0 on every line |
| 1.5 | no warnings | `LineMesh.warnings == []` on all 7 |
| 1.6 | coincidence ⟺ declared junction | T3 spec §4, asserted on every model |

### Tier 2 — analytical, 20 kN, Group A

| # | Check | Expected |
|---|---|---|
| 2.1 | δ against the closed form | FE **stiffer** by the predicted membrane term ±10 %: 2.2 × 10⁻⁵ (TP), 3.8 × 10⁻⁵ (TT), 1.23 × 10⁻⁴ (SH, SHTP) — a band, not a bound |
| 2.2 | end moments | `Pab²/L²` and `Pa²b/L²` to 1 × 10⁻⁴ relative |
| 2.3 | reactions sum | `ΣF_y = −P` to 1 × 10⁻⁹ |
| 2.4 | symmetry | δ(s) = δ(L−s) to 1 × 10⁻¹⁰ on the three symmetric cases |

2.1 is stated as a *band*, not a bound. An open "within 1 %" bound would pass
happily on a mesher that had lost a station; requiring the residual to equal
the predicted nonlinearity means anything else fails.

### Tier 3 — mesh invariance, 20 kN

The core of the plan. Each check varies the mesh and holds the geometry.

| # | Check | Measured | Tolerance |
|---|---|---|---|
| 3.1 | **ILS-SH vs ILS-SHTP** — same beam, 22 vs 24 elements | 3.12 × 10⁻⁷ | 1 × 10⁻⁶ |
| 3.2 | refinement 4 × OD → 0.25 × OD (12 → 178 elements) | 5.5 × 10⁻⁶, monotone | 1 × 10⁻⁵ |
| 3.3 | rigid translation of the whole model, ±50 m | 2.1 × 10⁻¹⁵ | 1 × 10⁻¹² |
| 3.4 | node ordering reversed | 1.2 × 10⁻¹³ | 1 × 10⁻¹² |

3.3 and 3.4 are exact by construction — coordinates enter the formulation
only through differences, and nothing depends on node order — so they are the
invariances that can be asserted at machine precision at *either* load. 3.3
is the same shift-invariance claim T3 spec §9 check 5 makes.

### Tier 4 — the rig as specified, 200 kN

| # | Check | Expected |
|---|---|---|
| 4.1 | all four Group A cases solve | converged, no warnings |
| 4.2 | membrane stiffening present and correct | §5 table, each within 10 % of the Rayleigh prediction (measured: 8 % worst) |
| 4.3 | translation and ordering invariance | 1 × 10⁻¹² (measured 2.6 × 10⁻¹⁴ both) |
| 4.4 | ILS-SH vs ILS-SHTP | **2.95 × 10⁻⁵ ± 20 %** — genuine mesh sensitivity, confirmed tolerance-independent (§8) |
| 4.5 | peak stress below first yield | < 360 MPa, recorded per case (worst 194.2 MPa) |
| 4.6 | **every solve returns within a few seconds** | a stalled solve never returns and is never reported (§8); the harness times out, the kernel will not |

### Tier 5 — Group B, deferred

| # | Check | Expected |
|---|---|---|
| B0 | EAST/EASB assembled with no connector elements | **singular or unconverged** — pinned now as the blocker, so the gap cannot be mistaken for a passing test |
| B1..B3 | the three cases, once connectors are modelled | regression-pinned; plus the bracket `δ_attached ≤ δ_plain`, since an attachment can only stiffen |

---

## 7. FINDING 1 — the kernel does merge nodes, and G6 has to give

Your instruction: *"Nlfea solver shouldn't merge nodes or edit them. If
that's the case, nlfea must be updated."*

**It is the case.** Four user nodes, two of them deliberately coincident:

```
declared:  Node(0, 0.0, 0.0)  Node(1, 1.0, 0.0)  Node(2, 1.0, 0.0)  Node(3, 2.0, 0.0)
elements:  (0→1)  (2→3)                    # two separate bars, touching
built:     3 mesh nodes
mapping:   {0: 0, 1: 1, 2: 1, 3: 2}        # nodes 1 and 2 became one
```

`MeshedStructure._mesh()` keys every node on `(round(x,10), round(y,10))`, so
two bars that merely touch are welded into one continuous member. The 12 Aug
architecture note recorded the consequence in the field: *"every frame node
landing on a pipe x-coordinate merges the whole frame into the pipe, silently
turning a two-point attachment into a continuous stiffener."* The stiffness
comes out too high and nothing reports it.

`user_node_to_mesh` is built by the same coordinate lookup, so a boundary
condition or a load applied to either node lands on the merged one.

**This conflicts with G6** ("never edit `nlfea_v4.py` — frozen, independently
validated"). Your ruling overrides it, and the guardrail should be amended
rather than quietly ignored:

> **G6 (amended).** `nlfea_v4.py` is frozen against *convenience* changes.
> A change is permitted only where the kernel's behaviour is provably wrong
> for a model this program must build, and only with (a) a failing test
> written first, (b) the default behaviour preserved for every existing
> caller, and (c) the validated case set re-run and recorded.

Clause (c) is the real cost and is worth saying out loud: the file is frozen
*because* it carries independent validation evidence. Editing it means that
evidence has to be re-established, not assumed.

### Three ways to make the change

| | Change | Regression risk | Verdict |
|---|---|---|---|
| **(a)** | key `get_or_add` on the **user node id** instead of the coordinate | every existing model changes: one that relied on coincidence to weld two lines comes apart | correct in principle, but silently redefines the frozen file's contract |
| **(b)** | add `Model.merge_coincident: bool = True`; our layer passes `False` | **none** — default path is bit-identical to today | **recommended** |
| **(c)** | leave `_mesh()` alone; assert that no merge would occur | zero | necessary anyway, but does not satisfy the instruction on its own |

**Recommended: (b) plus (c).** (b) is the smallest edit that satisfies the
instruction while keeping every validated result reproducible on the default
path — which is precisely what clause (c) of the amended G6 demands. (c) goes
in regardless, because a detector that fires in our own layer is cheaper than
one that fires inside the kernel.

Under the no-merge path, `MeshedStructure` must also build
`user_node_to_mesh` by identity rather than by coordinate, or the map still
collapses even though the nodes did not.

### "…or edit them"

The other half of the instruction. The kernel does two things to nodes beyond
merging: it **subdivides** (`UserElement.seed`) and it **renumbers** (mesh
index ≠ user id). T3 spec §5 already fixes `seed = 1` for every element we
emit, so no node is created. Renumbering is internal and unavoidable, but
with `seed = 1` and no merging it becomes a **bijection**, which is testable:

```
len(ms.mesh_nodes) == len(model.nodes)
set(ms.user_node_to_mesh.values()) == set(range(ms.n_nodes))
ms.mesh_nodes[ms.user_node_to_mesh[uid]] == (node.x, node.y)   # exactly
```

**That triple is the operational meaning of "must not merge or edit nodes",
and it is asserted on every model the rig builds.** Test 1.6 and this
assertion are the same guarantee seen from the two sides of the layer
boundary.

## 8. FINDING 2 — the solver tolerance has a floor, a plateau, and a cliff

The rig must say what tolerance it solves at, because all three regions of
that setting are reachable from the default and two of them are wrong.

**The default `tol = 5e-4` is under-converged.** ILS-SH refined to 1 × OD
(44 elements), varying nothing but the tolerance:

| `tol` | δ at 20 kN | δ at 200 kN | time |
|---|---|---|---|
| 5 × 10⁻⁴ (default) | 6.20730053 mm | 61.35427263 mm | 0.02 s |
| 1 × 10⁻⁵ | 6.20728880 mm | 61.34352734 mm | 0.02 s |
| 1 × 10⁻⁶ | 6.20728880 mm | 61.34352734 mm | 0.02 s |
| 1 × 10⁻⁷ | 6.20728880 mm | 61.34352734 mm | 0.02 s |

The default answer is 1.8 × 10⁻⁴ away from the converged one at 200 kN —
**six times the mesh sensitivity the plan is trying to measure** — and it
costs nothing to fix. It also drifts with the increment count, on a model
where nothing physical depends on it:

```
tol = 5e-4    n_inc  5 / 20 / 80:  61.35083626  61.35083499  61.35398639   spread 5.1e-5
tol = 1e-6    n_inc  5 / 20 / 80:  61.35083626  61.35083499  61.35083420   spread 3.4e-8
```

**From 10⁻⁵ to 10⁻⁷ is a flat plateau** — identical to eight significant
figures, at the same cost. Anywhere in it is a defensible setting.

**Past the plateau there is a cliff, and it is silent.** At `tol = 1e-8` the
residual is not always reachable, and `solve_step`'s response to
non-convergence is to halve the increment and retry (`inc_size *= 0.5`),
re-growing it by 1.5 on the next success. Nothing is raised, nothing is
logged without `verbose`, and the return value is a plausible number. On
22 elements 10⁻⁸ still converges in 0.03 s; on 44 it took 2.4 s; **on 90 it
had not finished in fifteen minutes.** A 0.02 s solve becomes unbounded, and
the only symptom is that it is still running.

Two details make it worse than it sounds. The retry loop has no iteration or
wall-clock budget at all — only `inc_size < 1e-6` ends a stall, and a
successful increment resets the ratchet. And the solve is wrapped in a bare
`except Exception: break`, which swallows anything raised from inside,
including the alarm this spike used to try to bound the run.

**So: every solve in this plan runs at `tol = 1e-6`, never the default.**
Solver settings are part of each expected value and are recorded with it.
A rig case that has not returned in a few seconds has stalled, not slowed,
and the test harness must time out rather than wait — the kernel will not
tell it.

### The separate question: is the 200 kN mesh difference real?

ILS-SH vs ILS-SHTP at 200 kN, across the whole range:

```
tol = 5e-4   61.350834989 / 61.349027672   rel 2.95e-05
tol = 1e-5   61.350834989 / 61.349027672   rel 2.95e-05
tol = 1e-6   61.350834989 / 61.349027672   rel 2.95e-05
tol = 1e-7   61.350834989 / 61.349027672   rel 2.95e-05
```

**Unmoved to three significant figures at every tolerance.** It is not Newton
noise. It is genuine mesh sensitivity: once the response is geometrically
nonlinear the corotational element is no longer exact — each element carries
its own rigid rotation — and a 22-element mesh really does answer differently
from a 24-element one. Refinement shows the same thing converging:

| target | elements | δ at 20 kN | δ at 200 kN |
|---|---|---|---|
| 4 × OD | 12 | 6.20732057 mm | 61.37315973 mm |
| 2 × OD | 22 | 6.20729664 mm | 61.35083499 mm |
| 1 × OD | 44 | 6.20728880 mm | 61.34352734 mm |
| 0.5 × OD | 90 | 6.20728679 mm | 61.34165717 mm |
| 0.25 × OD | 178 | 6.20728632 mm | 61.34121913 mm |

At 20 kN the whole 15× refinement moves the answer by 5.5 × 10⁻⁶ — the
element is essentially exact and the mesh is invisible, exactly as §2 argues.
At 200 kN it moves by 5.2 × 10⁻⁴, monotonically, which is ordinary
discretisation convergence of a nonlinear element.

That is why the tight invariance bounds live at 20 kN (Tier 3) and the 200 kN
checks assert *measured* sensitivities rather than bounds (Tier 4). Had the
default tolerance been left in place, its 5 × 10⁻⁵ of drift would have sat on
top of both and neither would have been readable.

This is a calling convention, not a kernel defect — no G6 question here. The
silent stall arguably is one, but the rig avoids it rather than fixing it.

## 9. FINDING 3 — why the rig uses an elastic material, not the J2 one

Every Group A case peaks at 194 MPa against 360 MPa first yield, so a J2
material would never yield and looks like a harmless choice. It is not.

For `IncrementalIsotropic` and `RambergOsgood` elements the kernel integrates
the section over fibres rather than using the analytic `I`. Integrating
`PipeSection.fibre_geometry()` for our pipe:

| `n_fibres` | A error | **I error** |
|---|---|---|
| 20 (default) | −0.17 % | **+0.40 %** |
| 30 | +3.53 % | **+6.59 %** |
| 40 | −0.14 % | +0.007 % |
| 60 | −0.11 % | −0.06 % |
| 100 | −0.07 % | −0.06 % |

The strips are equal-width across the full outer diameter, and the annulus
has square-root edges at both `r_i` and `r_o`, so the quadrature error is
erratic rather than monotone in `n_fibres`. **At 30 fibres the effective `EI`
is 6.6 % high** — and `PipeSection`'s own docstring recommends *"30+ for high
n"*.

Nothing here is the mesher's doing, but a 6.6 % stiffness error would land in
a mesher test result and be indistinguishable from a lost station. So:

- **the rig binds a linear-elastic `Material`**, for which the kernel uses the
  analytic `A` and `I` and the closed form is exact;
- the fibre-count question is logged for **T5 (physics/solve)**, where the
  choice of `n_fibres` is actually made.

## 10. FINDING 4 — `NodeReason` cannot say "a load is applied here"

`NodeReason` offers `SECTION`, `SLOPE`, `JUNCTION`, `MASS`, `EXTENT`. The rig
needs a mandatory node at the load point — mandatory in the strongest sense,
since `JointLoad` names a node id and the model cannot be built without one —
and no member says so.

T3 spec §8 already found one gap of the same kind: the elastic-zone boundary
is a fourth MANDATORY reason that `component_spec`'s `NodePriority` does not
list. The load point is a fifth. Both are *external* reasons — the scene or
the analysis requires a node, not the component's own geometry.

Proposal: add `NodeReason.BOUNDARY` (restraint or material-zone edge) and
`NodeReason.LOAD` (an applied load acts here). Neither changes any behaviour;
they stop external stations from being filed under a geometric reason that is
not true, which is what test 1.2's diagnostics read.

## 11. The spike

Everything above was measured, not estimated. `tools/spike_mesher_rig.py`
builds the header polyline, meshes it with `slay.model.mesh.mesh_line`,
assembles an `nlfea_v4.Model` by hand and solves. It is committed, so every
figure in this plan can be re-measured rather than believed — G8 applied to a
planning document.

It is a **spike, not a module**: it imports model, solve and the mirrored L2
builder in one file, which `tools/check_layers.py` permits under `tools/` and
would reject inside `rebuild/slay/`. It assembles the kernel model by hand
because `build_model()` does not exist yet.

It matters for two reasons. It shows the rig **runs today** on Group A, with
no T3 code yet written — so the plan is describing tests that can actually be
made to pass, not tests that depend on the thing they are testing. And it is
what turned assumptions into findings: the node merge (§7) was a guess until
the probe printed `3`, and the load-point station (§10) only became visible
when `Station` needed a `reason` and none fitted.

§8 took three passes, and the two wrong ones are worth recording because
both were plausible. First: the 200 kN SH-vs-SHTP difference and the
increment drift came out the same size, and the obvious reading — both are
Newton noise — went into a draft. Sweeping the tolerance showed the drift
moves with it and the difference does not, so they are two different effects
that happen to coincide in magnitude. Second: the fix for the drift was
written up as `tol = 1e-8`, which is past what the kernel can reach; the
90-element case then ran for fifteen minutes without returning, and the only
reason that was caught is that the spike was being timed. The recommendation
is `1e-6`, in the middle of a measured plateau.

The lesson generalises past this card. Below about 10⁻⁴ in a nonlinear solve,
a difference has to be attributed by experiment rather than argument — and a
solver setting has to be shown reachable, not merely tighter.

When T3 is implemented the tests are rewritten against the real
`build_model()` and the spike is deleted — it exists to plan the tests, not
to become them.

## 12. Questions for you

**1. Which "6 m"?** EDAS pins `header.half_length` — 6.0 m for five
archetypes, 6.164 m for EASB and ILT — measured **from the ILS centre**. Your
instruction reads 6 m **beyond each end of the component**. For ILS-SH
(6.096 m span) those are very different models: EDAS's header leaves 2.95 m
of plain pipe each side, yours leaves 6 m. I have built yours.

One consequence to accept with it: the rig's pipeline is longer than the
archetype's pinned header, so the fixture's recorded `mass_kg` and `cog_m` do
not describe the rig model. The existing geometry tests keep the pinned
header; the mesher tests use the rig's. The two must not be compared.

**2. "Component body centre" on ILS-ILT.** Its extent is asymmetric
(−1.626 … +4.064 m). The ILS-local origin `x = 0` is the GD-B branch centre;
the extent midpoint is `x = +1.219 m`. I have taken `x = 0`, the assembly's
own datum, which makes ILT the one off-centre case in the set. Only ILT is
affected and it sits in deferred Group B, so this can wait — but it needs
deciding before Group B runs.

**3. The 20 kN run.** Not in your specification. It is the only absolute
check in the plan (§3), and it costs one extra solve per case. Confirm you
want it, or the plan drops to invariances only.

**4. Group B deferral.** EAST, EASB and ILT need connector modelling that
does not exist yet (§4), and that is a physics-layer design question rather
than a mesher one. Confirm it belongs on a later card, with test B0 pinning
the blocker in the meantime.

**5. G6.** §7 recommends option (b) — a `merge_coincident` flag defaulting to
today's behaviour — plus the amended wording. Confirm before any line of
`nlfea_v4.py` is touched.

---

## Action log

| Date | Action |
|---|---|
| 12 Sep 2026 | Plan written against the specified rig. Four findings: the kernel merges coincident nodes (§7, amends G6); the solver tolerance has an under-converged default, a usable plateau at 10⁻⁵–10⁻⁷ and a silent non-terminating cliff past it (§8); fibre integration is 6.6 % stiff at 30 fibres (§9); `NodeReason` has no member for a load point (§10). Case set split into prismatic Group A (runs today) and attached Group B (blocked on connector modelling). Every figure measured by `tools/spike_mesher_rig.py`. |

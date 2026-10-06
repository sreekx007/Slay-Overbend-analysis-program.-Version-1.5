# Series 3 — the physics sequence, in plain English

**Written before running anything**, so that what the simulation is supposed
to represent is settled independently of what it produces. Agreed 21 Sep
2026.

This describes the PHYSICS. Where a step is a modelling device rather than
something that happens offshore, it says so.

---

## What is being represented

A length of pipeline leaving a lay vessel. It runs along the deck, over a
line of rollers, and down the curved stinger into the sea. Somewhere in that
length is an inline component. Take it below to be a thick-walled body — a
forged section with the same bore as the pipe and a heavier wall, so it is
stiffer than the pipe and its outside surface stands proud of it. That is
one of three kinds we model; another is a shroud, which adds no stiffness
and works purely by lifting, and the third is a structure bolted to the pipe
at points. **Three kinds of component** near the end sets
out the difference, and the sequence below applies to both.

We want the worst strain the pipe suffers as this component goes over the
stinger.

The model is a slice of that: from a point well back on the deck, to just
past the last stinger roller. Beyond that the pipe continues down to the
seabed as a free-hanging catenary, which we do not model — we replace it
with a pull at the end.

## The geometry, fixed before anything is loaded

* The **deck** is straight and level. The **stinger** is a circular arc of
  radius R below it. The rollers sit on that line.
* **SR1** is where the arc begins — the last flat point. **SR2** is the
  first roller genuinely on the curve, and it is where the pipe is bent
  hardest.
* The **component's catenary-side edge starts exactly on SR2**, with its
  body extending back toward the vessel. This is the reference program's
  placement. It is the START of the passage, not the answer to it — the
  pipeline slides on from here in Step 6.
* The pipe starts **perfectly straight and completely unstressed**. It has
  never been bent. This matters for the order of everything below.

## The sequence

### Step 1 — Bend the pipe down onto the rollers

Take the straight pipe and push it down onto the line of rollers until it
follows the stinger curve. Nothing else acts: no weight, no pull. The steel
stays springy — if we let go it would straighten out completely.

**Every roller grips the pipe in this step**, top and bottom. That is a
deliberate fiddle, not reality: a real roller can only push up, it cannot
hold the pipe down. But with nothing yet pulling the pipe onto the stinger,
rollers that can only push would simply let go, and the pipe would never
reach the curve at all. So we hold it there first and hand the rollers their
real behaviour in the next step.

*What this step creates is the shape.* Everything afterwards depends on the
pipe already being curved, for the reason given under Step 3.

### Step 2 — Let go of the rollers and turn on gravity

Now the rollers behave properly: they can push the pipe up, but if the pipe
lifts away from one, it lifts away and that roller stops carrying anything.

At the same time the pipe is given its own weight — steel in air, no
contents, no buoyancy, about 200 kg per metre.

The pipe settles. It presses down on some rollers and comes off others. Near
the vessel it tends to lift, because the far end is being pulled down around
the curve. Still springy steel.

### Step 3 — Pull the lay tension

The pipeline does not stop at the last roller; it carries on down to the
seabed. That hanging length pulls on the pipe, away from the vessel and
downwards along the line of the pipe. That pull is the lay tension, and here
it is 100 tonnes applied at the end of the model.

This pull is what holds the whole thing taut against the stinger — without
it the pipe simply sags between whatever it happens to touch.

**Why the pull comes third, and cannot come first.** A straight pipe has no
resistance to being pulled sideways at its end — think of pulling on a
slack rope. The stiffness that carries this load only exists once the pipe
is bent and lying on the rollers. Apply the tension to the straight pipe and
the calculation has nothing to push back with and falls over. Bend first,
then pull. This is not a numerical trick; it is the same reason a real
vessel tensions a pipe that is already on the stinger.

### Step 4 — Allow the steel to yield

Up to here the steel has been perfectly springy. Now it is given its real
behaviour: past a certain stress it yields and takes a permanent set, and it
remembers that it has done so.

This is last because yielding depends on the whole history — how the pipe
got to its shape, not just what shape it is in. The steel must be walked
through the loading in order for the permanent stretch to land in the right
places.

The strains go up in this step. That is expected: once material near the
component starts to give, the load it can no longer carry is pushed into the
neighbouring pipe.

### Step 5 — Read the first answer: the pipe at its starting position

At this point the component is sitting on SR2 with the pipe fully bent,
loaded and yielded. That is a real condition the pipeline passes through,
and it is the one the paper calls **Phase 1** — the plastic bending that
happens in the first couple of roller boxes, where a plain pipe takes its
highest strain.

Record the largest strain in the pipe here. For this kind of component it
sits at the junction between the pipe and the thick body.

### Step 6 — Slide the pipeline forward, step by step

The vessel moves ahead and pipe is paid out, so the whole pipeline creeps
along the stinger. The component that was sitting on SR2 travels on down the
curve, and every roller in turn finds itself bearing on a different piece of
pipe.

This is simulated as a sequence of positions. At each one the pipeline has
advanced a short distance — a fraction of a metre — and the model is solved
again. **Each position starts from the state the last one ended in**, so the
permanent set the steel took in Step 4, and at every position since, is
carried forward. The pipe does not get a fresh start; it remembers
everything that has been done to it. That is the whole reason the steps have
to be walked in order.

Two things are re-decided at every position:

* **Which rollers are touching.** As the shape changes the pipe lifts off
  some rollers and settles back onto others.
* **Where on the pipe each roller bears.** The rollers are bolted to the
  stinger and do not move; it is the pipe that slides under them. So the
  piece of steel in contact with a given roller changes continuously — it is
  not a matter of handing the roller to the next node along. The contact
  point is a material point that travels smoothly through each element and
  on into the next.

Physically this covers the paper's **Phase 2** — the repeated bend-and-
unload cycle as a length of pipe passes over the mid-stinger rollers — and,
if the run goes far enough, **Phase 3**, where it slides off the last roller
and hangs free.

### Step 7 — Read the answer over the whole passage

The number that matters is the worst strain any part of the pipe suffers at
any point during the passage, not the strain at one position. So the peak is
taken across every sliding position as well as the starting one.

The last three stinger rollers are excluded from the reading. The very end
of the model is where we cut the pipe off and replaced the hanging catenary
with a pull, and that substitution is crude — the numbers there describe our
boundary, not the pipeline. This exclusion is not cosmetic: the strain there
can be higher than the number we report, so it travels with every figure we
quote.

## How far the sliding goes, and what limits it

The reference program moves the pipeline in steps measured in element
lengths. At the standard spacing one step is about 0.8 m, and its default
schedule runs five positions covering roughly 3.2 m — **about 40% of one
roller spacing**. The component therefore starts on SR2 and ends a few
metres past it, without reaching SR3.

There is a hard ceiling. The program refuses a shift large enough to push
the first vessel roller past the anchor, which lands at roughly one roller
spacing however many vessel rollers are configured. Its own documentation
says lifting that limit needs the vessel-side buffer sized properly and that
this is not implemented.

**So the passage that can currently be simulated is a partial one.** Over
the stretch that can be covered, the peak was observed to fall steadily away
from the starting position. Whether it rises again as the component
approaches the next roller has never been seen, because the run cannot get
that far. That is a limitation to state with the results, not a finding.

## What we do NOT do

**We do not model the seabed, the vessel motion, or the waves.** The
pipeline is moved forward in still water and solved statically at each
position.

## Step 6 in the rebuild — built and verified

*This section said the sweep driver was not ported. It was written before
22 Sep and left stale for a week; corrected 29 Sep.*

Both halves now exist. `slay/solve/passage.py` is the rebuild's version of
the reference's `_solve_state_sliding` and carries displacement, rotation,
plastic state and the contact active set from one solve to the next.
`slay/study/sweep.py` is the outer loop — the placement rule, the shift
schedule, and the re-computation of where each roller bears at each
position.

It is verified rather than merely running. On a plain **linear elastic**
passage the strain at a given station must not change as the pipe slides,
because the rollers impose the same geometry at every position. Stepped a
whole element it holds to **0.03–0.08%** at SR1–SR4. That is the check that
says the sliding is right; anything left over is discretisation.

**One thing the sweep must do that is easy to miss.** The worst position of
a passage is where a component EDGE crosses a roller, and that is not a step
boundary. Sampling on a fixed step alone made the answer depend on the step
over a 20% range. The schedule now always includes the edge crossings, which
makes the envelope step-independent — 0.5731 / 0.5727 / 0.5722 / 0.5689%
across a fourfold range of step, found in 5 positions where blind refinement
needed 16.

## Three kinds of component, and they are not the same physics

*Added 29 Sep for the first two; a third added 6 Oct. Everything above was
written for a thick-walled body. The others behave differently — one
oppositely, one by a different mechanism entirely — and the sequence
applies to all three.*

**A stiffening body (GD-TP, GD-TT).** A forged section with the same bore
and a heavier wall. It is stiffer than the pipe, so it resists being bent
and pushes the curvature it will not take into the pipe on either side of
it. Its outside surface also stands proud, so it lifts the pipe slightly
where it passes a roller.

**A lifting body (GD-SH).** A shroud wrapped round the pipe. It adds **no
bending stiffness at all** — the pipe's own section runs right through it —
and its entire effect is that the roller now touches the shroud's outer
surface instead of the pipe, holding the pipe *off* the arc by

        lift = V − OD_pipe/2

where `V` is measured from the pipe **centreline**, not from the pipe's
outside. Using `V` itself over-elevates by half a diameter — 33% too much
at V = 2D — and inflates every strain to match.

The two act in **opposite senses** on local curvature. Measured at the
envelope position on an 85 m stinger:

| | stiffness ratio | radius over the body | radius in the pipe beside it |
|---|---|---|---|
| GD-TP | 2.36 | 67.1 m | 47.4 m |
| GD-TT | 4.37 | **85.5 m** | **28.3 m** |
| GD-SH | 1.00 | **33.8 m** | 45.5 m |

A stiff body stays flatter than the pipe beside it and dumps the curvature
on its neighbour — GD-TT at 4.37 rides essentially the stinger's own radius
while forcing a 28.3 m bend into the adjacent pipe, three times tighter than
the stinger itself. A shroud does the reverse: with nothing to resist
bending, the lift forces curvature into the component region.

**An attached structure (EA-ST, EA-SB).** *Added 6 Oct, with the EA sweep
cases.* Neither of the above. A frame — a portal standing over the pipe
(EA-ST) or a body it rides on (EA-SB) — is **fastened to the pipeline at
discrete points**, and that is the whole of how it acts. Between those
points it is a separate structure spanning over the pipe, carrying its own
share of the bending in its own members, with a stiffness `kT` (ST) or `kB`
(SB) quoted as a multiple of the pipeline's.

So its load path is nothing like a body threaded onto the pipe:

* **The pipe is bent hard AT a fastening**, because that is the only place
  the structure can push or pull on it.
* **The pipe BETWEEN two fastenings is the quietest in the model** — an
  order of magnitude below the fastenings. The frame spans over it and
  takes the curvature instead. *A two-point attachment does not load the
  pipe it spans; it loads its own ends.*
* Outboard of the structure the pipe returns to the plain stinger overbend.

EA-SB is **both kinds at once**, which is easy to miss: as well as being
fastened down, its body lifts the pipe off the arc by `P_v − OD/2`, exactly
as a shroud does. Our archetype ships `P_v = 4 D` (a 3.5 D lift) while every
published case is `2 D` (1.5 D); the difference is severe enough to stop
passages converging, so the shipped default is not a case anyone has
published.

**Only one joint type is modelled.** A fastening is type **F** — fully
tied. The `P`, `S` and `D` joints in the reference release selected degrees
of freedom (`D` is a deadband that opens and shuts), and the solver refuses
them rather than approximating them with an F. Substituting F ties every
DOF and silently answers a different question, which is what guardrail G9
forbids.

**Why this matters for reading results.** For a stiffening body the worst
strain is in the pipe at the junction, not on the body — measured across the
dataset, a median 4.5× the body peak. For a shroud there is no junction at
all, because no section steps; the lift is the whole of it, and a result
file that does not record the lift cannot tell a shroud case from bare pipe.

## Where an offset body's strain is read — the five regions

*Added 30 Sep, following the reference's Series 4 / Type B1 scheme.*

A stiffening body announces where to look: the section steps, so there is a
**junction**, and we report at it and at ±2, 4, 6 diameters either side.
A shroud steps nothing, so there is no point to probe **at** — its effect is
spread over its whole length. The reporting unit has to be a **region**.

The shroud has three geometric parameters: a deep section of length `L1` at
full depth, a taper of length `L2` at each end, and the depth `V`. The pipe
is divided into five:

```
   catenary side  <--                                       -->  vessel side

   |     X1     |    X2    |    X3    |    X4    |     X5     |
   | taper +    | deep 1/3 | deep 1/3 | deep 1/3 | taper +    |
   | beyond     | catenary | midspan  |  vessel  | beyond     |
```

| | Where | What it reads |
|---|---|---|
| **X1** | catenary-side taper, and the pipe beyond it | nominally the plain-pipe catenary — but see the caution below |
| **X2** | deep section, catenary-side third | **the peak, and the region that governs design** |
| **X3** | deep section, midspan third | intermediate — the reference puts it at 65–75% of X2 |
| **X4** | deep section, vessel-side third | lowest of the three; plateaus once `V` exceeds about 1.5 OD |
| **X5** | vessel-side taper, and the pipe beyond it | plain-pipe catenary |

The five are a **partition** — X1 and X5 run out to the ends of the model —
so every element belongs to exactly one, and the pipe either side of the
shroud is reported rather than dropped. The boundaries are fixed in
**material** coordinates, so a region is the same piece of steel at every
position of the passage; in station coordinates they would slide with the
shift and a per-region peak would be comparing different pipe at each step.

**Which end is which is the thing that must not be wrong.** Reverse it and
the scheme still produces five tidy regions, still partitions the pipe, and
reports the quietest region as the one that governs. `s` increases toward
the stinger and the catenary hangs off its tip, so the catenary side is
**high `s`**. This is not taken on the frame algebra alone: our own ILS-SH
peak sits at `s_material` 6.833, which lands in the catenary-side third,
exactly where the reference says the peak is in every case it ran.

**Two cautions, both recorded in the data rather than in anyone's memory.**

*The thirds are thinner than the mesh.* At the ruled 2×OD density (G10) a
third of the deep section is 1.354 m and an element is 0.813 m, so X2 and X3
hold **two** elements each and X4 holds **one**. A ratio between them is
partly reporting the mesh, which is why every region carries its element
count. Refined, the ratios move and then settle:

*R = 85 m, 9 m spacing, **120 MT** — NOT Series 4's 100 MT, so these X2
values are not comparable to the published 0.70%. See the note below.*

| mesh | X2 | X3/X2 | X4/X2 |
|---|---|---|---|
| 2×OD (ruled) | 0.6868% | 0.784 | 0.702 |
| 1×OD | 0.7286% | 0.749 | 0.712 |
| 0.5×OD | 0.7951% | 0.744 | 0.691 |

X3/X2 converges to 0.744 at this tension, and the ratio converges rather
than drifting — the strong mesh dependence at the ruled density is mesh, not
physics.

**The tension was missing from this table until 6 Oct, and it reversed a
conclusion drawn from it.** These rows are at 120 MT; Series 4 — the source
of both the 65–75% band and the 0.70% that `ILS-SH`'s dimensions match
exactly — is at **100 MT**. Re-run at the paper's own tension, X3/X2
converges to **0.767, just OUTSIDE the band**, not 0.744 inside it:

| mesh | X3/X2 at 100 MT (Series 4) | X3/X2 at 120 MT (above) |
|---|---|---|
| 2×OD | 0.800 | 0.784 |
| 1×OD | 0.770 | 0.749 |
| 0.5×OD | **0.767** | **0.744** |

At the ruled mesh the two tensions look interchangeable (0.800 against
0.784), which is why the substitution went unnoticed; the gap survives
refinement and 0.75 is where the band's edge sits, so they settle on
opposite sides of it. **The earlier claim of agreement with the band was an
artefact of reading a 120 MT run against a 100 MT target.** The absolute X2
column here is likewise not a Series 4 number. The comparison at the
paper's own configuration — and the X2 trend, which brackets 0.70% under
refinement — is in `docs/VALIDATION.md` §C.

The standing rule, state R *and* tension *and* spacing beside every strain,
was written after the same mistake in T5 §4; this is the second time it has
been broken, and the first time it cost a conclusion rather than just
clarity. (X2 itself keeps climbing with refinement, the same
non-convergence the Mesh section below records for a thick body.)

*X1 is two different things.* It lumps the catenary-side taper together with
the plain pipe beyond it, and the reference calls both "governed by the
plain-pipe catenary". At 2×OD that holds. Refined it does not: the model
peak moves **onto the taper**, 0.395 m outboard of the deep section, at
1.022× the X2 peak — the taper is where the lift gradient is steepest, so
curvature concentrates there. Each region peak therefore also records
whether it landed on the shroud footprint, so a reader can tell which of the
two an X1 peak happened on.

## Where an attached structure's strain is read — X_c, X_i, X_e

*Added 6 Oct, with the EA sweep cases. A different scheme again, and for a
different reason: an offset body is divided by its own geometry, an attached
structure by where it is FASTENED.*

A body threaded onto the pipe is reported at its junctions or by its deep
section. Neither applies to a frame bolted on at points, so the reference
divides the pipe by the fastenings instead:

| | Where | What it reads |
|---|---|---|
| **X_c** | within **2 × pipe OD** either side of a connector | **the peak, and what governs** |
| **X_i** | the interior, between two connectors | the quietest pipe in the model — an order of magnitude below X_c |
| **X_e** | outboard, from X_c out to the far field | the plain stinger overbend |
| *X_i2* | a second interior, in the F1D/F2D layouts | not implemented — those need the `D` joint the solver refuses |

A single fastening (F1) has no interior at all, so it has **no X_i** — and
the reference tabulates none for it.

**Two things about this convention were got wrong and are worth keeping.**
X_c was first implemented 1.5 diameters either side, a band sized to be
about two elements at the ruled mesh rather than read from the source, which
says 2 × pipe OD. It changed no number — every peak already sat inside
1.5 D — which is exactly why it would have survived indefinitely.

And **the reference's prose and its own figures disagree** about where X_e
stops. The text says X_e is "pipeline outside the structures"; Figs 27 and
38 draw X_e running right up to where X_c begins, which *includes* pipe
lying under the structure but outboard of its connectors — for EA-SB, the
taper, where strain concentrates. Implementing the prose moved X_e from
−10% to −45% against the reference's own numbers, so the figure is what we
follow. Three cases settle it; the fourth cannot, because its connectors sit
on the body's own edges and leave no under-structure pipe to argue over.

### What the EA cases say so far

Measured at R = 85 m, 9 m spacing, 120 MT, against the reference's values.
*These six rows also appear in `docs/VALIDATION.md` §E, beside every other
published case and with the deltas computed.*

| case | X_c ours / ref | X_i ours / ref | X_e ours / ref |
|---|---|---|---|
| EA-ST F2 Case 1 | 0.923 / 0.936 (**−1.4%**) | 0.075 / 0.043 | 0.537 / 0.732 |
| EA-ST F2 Case 2 | 1.615 / 1.410 (+14.5%) | 0.124 / 0.075 | 0.679 / 1.021 |
| EA-SB F1 Case 1 | 0.950 / 2.30 (−58.7%) | — | 1.136 / 1.41 |
| EA-SB F2 Case 1 | 1.261 / 2.24 (−43.7%) | 0.137 / 0.086 | 1.304 / 1.45 |
| EA-SB F2 Case 2 | 2.238 / 2.40 (**−6.8%**) | 0.123 / 0.086 | 0.836 / 1.52 |
| EA-SB F2 Case 3 | 1.473 / 2.53 (−41.8%) | 0.127 / 0.085 | 1.432 / 1.60 |

**The ordering X_c > X_e ≫ X_i is reproduced in every case**, which is the
reference's actual finding and the thing the scheme exists to show. The
magnitudes are another matter and the disagreement is not yet explained.

One candidate is eliminated rather than left open: on EA-SB we read **low**
while taking a passage *envelope*, and an envelope cannot be below a single
position — so unlike EA-ST Case 2 this cannot be the unlike-comparison
artefact of reporting a sweep against a single analysis. What the numbers do
show is that our model is far more sensitive to connector **placement** than
the reference's: EA-SB F2 Case 2, the one case whose connectors sit exactly
on the body's edges, is the only one that lands close, while the two with
connectors 2.5 D inboard both read about −42%.

## Mesh

The pipe is chopped into short straight pieces, 2 diameters long away from
anything interesting. The component is **2 pieces long**, each about 0.5 m,
which is 1.23 times the pipe diameter — the smallest we will go.

Be aware of what this costs. Chopping the component finer keeps raising the
answer: 1 piece gives 0.5715%, 2 gives 0.6118%, 3 gives 0.6458%, 5 gives
0.6640%, 7 gives 0.6739%, and it is still creeping up. **Two pieces reads
roughly 10% below where the trend is heading.** That is an accepted cost,
taken deliberately, and it means these numbers are for comparing cases
against each other rather than for quoting as the strain in a real pipe.

---

## Action log

| Date | Action |
|---|---|
| 6 Oct 2026 | **Added: a third kind of component.** An externally attached structure (EA-ST, EA-SB) is fastened to the pipe at DISCRETE POINTS and spans over everything between them, so the pipe is bent hard at a fastening and is quietest between two — a two-point attachment loads its own ends, not the pipe it spans. EA-SB is both kinds at once: it is also an offset body, lifting by `P_v − OD/2`. Only the type F joint is modelled; P, S and D are refused rather than approximated (G9). |
| 6 Oct 2026 | **Added: the X_c / X_i / X_e regions**, the reporting scheme for an attached structure, with the six EA case results measured against the reference. The ordering is reproduced in every case; the magnitudes are not, and one explanation — a sweep envelope read against a single analysis — is eliminated because we read LOW. Two convention errors recorded with it: X_c sized to the mesh rather than to the stated 2 × OD, and an X_e boundary where the reference's prose and its own figures disagree. |
| 30 Sep 2026 | **Added: the five strain regions of a shroud.** A body that steps no section has no junction to probe, so its reporting unit is a region, after the reference's Series 4 / Type B1 scheme: X1 catenary taper and beyond, X2/X3/X4 the deep section in thirds from the catenary side, X5 vessel taper and beyond. Orientation pinned against the measured peak. Two cautions recorded with it: at the ruled mesh the deep thirds hold 2, 2 and 1 elements, and X1 lumps a taper together with plain pipe. |
| 29 Sep 2026 | **Corrected: Step 6 is built.** The section claiming the sweep driver was not ported had been stale since 22 Sep. Replaced with what exists and how it is verified, including the edge-crossing rule that makes the passage envelope independent of the sweep step. |
| 29 Sep 2026 | **Added: two kinds of component.** Everything here was written for a thick-walled stiffening body. A shroud adds no stiffness and acts entirely by lifting the pipe off the rollers (`lift = V − OD/2`, `V` from the CENTRELINE), and the two act in opposite senses on local curvature — measured and tabulated. |
| 21 Sep 2026 | **Corrected: sliding added.** An earlier version of this file stopped at the starting position and argued no sliding was needed, on the strength of a sweep that covers only 40% of a roller spacing. Sequential sliding is Step 6 and the reading moves to Step 7, taken across the whole passage. |
| 21 Sep 2026 | Sequence written and agreed before any Series 3 run. Five steps: bend onto the rollers with every roller gripping; release the rollers and apply weight; pull the lay tension; allow yielding; read the peak excluding the last three stinger rollers. Mesh set to 2 elements across the component (0.4993 m, 1.23×OD), with the measured mesh sensitivity recorded so the ~10% shortfall against the converging trend is a stated cost rather than a surprise. |

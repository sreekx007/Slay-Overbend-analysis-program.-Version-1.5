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
length is a thick-walled inline component — a forged body with the same bore
as the pipe and a heavier wall, so it is stiffer than the pipe and its
outside surface stands proud of it.

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

## What the rebuild still needs for Step 6

The per-position solver is already ported: `slay/solve/passage.py` is the
rebuild's version of the reference's `_solve_state_sliding`, and it carries
displacement, rotation, plastic state and the contact active set from one
solve to the next, which is what Step 6 needs.

**The sweep driver is not ported.** In the reference that is the outer loop
of `run_passage_sliding` — the placement rule, the shift schedule, and the
re-computation of where each roller bears at each position. That belongs to
the study layer (T6 / L7), which is not built. Step 6 cannot run in the
rebuild until it is.

## Mesh

The pipe is chopped into short straight pieces. The component is **2 pieces
long**, each about 0.5 m, which is 1.23 times the pipe diameter — the
smallest we will go.

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
| 21 Sep 2026 | **Corrected: sliding added.** An earlier version of this file stopped at the starting position and argued no sliding was needed, on the strength of a sweep that covers only 40% of a roller spacing. Sequential sliding is Step 6 and the reading moves to Step 7, taken across the whole passage. |
| 21 Sep 2026 | Sequence written and agreed before any Series 3 run. Five steps: bend onto the rollers with every roller gripping; release the rollers and apply weight; pull the lay tension; allow yielding; read the peak excluding the last three stinger rollers. Mesh set to 2 elements across the component (0.4993 m, 1.23×OD), with the measured mesh sensitivity recorded so the ~10% shortfall against the converging trend is a stated cost rather than a surprise. |

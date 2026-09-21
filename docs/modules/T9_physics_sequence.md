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
  placement and it is also the worst one: the strain peaks at SR2, so the
  component sitting right on it is the governing case.
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

### Step 5 — Read the answer

The number we want is the **largest strain anywhere in the pipe**, which
for this kind of component sits at the junction between the pipe and the
thick body, right at SR2.

The last three stinger rollers are excluded from the reading. The very end
of the model is where we cut the pipe off and replaced the hanging catenary
with a pull, and that substitution is crude — the numbers there describe our
boundary, not the pipeline. This exclusion is not cosmetic: the strain there
can be higher than the number we report, so it travels with every figure we
quote.

## What we do NOT do, and why

**We do not slide the component along.** The reference program can walk the
pipe forward past the rollers, and for some components that matters. For
this one it does not: the strain peaks at SR2, the component starts on SR2,
and moving it anywhere else only makes things milder. Measured over the
reference program's full sweep, the peak falls steadily from the start
position — 0.5715% down to 0.5074% — so the first position is the answer.

**We do not model the seabed, the vessel motion, or the waves.** This is a
static snapshot of the worst moment.

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
| 21 Sep 2026 | Sequence written and agreed before any Series 3 run. Five steps: bend onto the rollers with every roller gripping; release the rollers and apply weight; pull the lay tension; allow yielding; read the peak excluding the last three stinger rollers. Mesh set to 2 elements across the component (0.4993 m, 1.23×OD), with the measured mesh sensitivity recorded so the ~10% shortfall against the converging trend is a stated cost rather than a surprise. |

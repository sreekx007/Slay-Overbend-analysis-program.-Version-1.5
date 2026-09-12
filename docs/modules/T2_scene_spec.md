# T2 — Scene · specification for review

**Status:** DRAFT — §3 step 1 (plain-language algorithm). Awaiting your review.
**Card:** `docs/SLAY_BUILD_INSTRUCTION.md` §6 T2
**Layer:** `scene` (L3) · **Workflow:** none permitted

> This is step 1 of the per-module process: the algorithm in plain language,
> for comment. No code is written until steps 2–4 are done. Three findings
> below (§3) need your decision before I can write anything — one of them
> would silently invert the contact behaviour of two rollers out of three.

---

## 1. What Scene is for

Everything built so far describes a component in its own local terms: a
GD-TT knows its taper is 0.126 m long, a GD-ST knows its frame is 6.5 m
wide, and `ils_builder` knows how they fit together — but all of it is
measured from the ILS's own reference point. None of it knows there is a
stinger, and none of it knows where along that stinger the assembly sits.

Scene is the layer that answers *where*. It takes a lay configuration — a
stinger radius, a roller count and spacing, roller diameters — and produces
the physical arrangement those numbers describe: where each roller sits,
how far along the pipe's path that is, which direction the pipe is pushed
at each one, and how much pipe there has to be for the whole sweep to fit.

It is the first layer in a world frame. Everything below it was local.

## 2. Where Scene stops

Three boundaries matter, and all three are the kind that erode quietly.

**Scene does not know where the pipe is.** It knows where the *rollers*
are. The pipe's position is what the solver computes; it is not a fact
about the lay configuration. This is the same line tracker item 27 drew for
the plotter after a figure drew the "pipe centreline" from the stinger arc
formula — asserting a shape that nothing had solved for. A roller station
is a known input; a pipe position is an output, and Scene emits none.

**Scene builds no nodes and no elements.** Meshing is L4's job and already
works. Scene hands it geometry, not discretisation.

**Scene does not sweep.** It describes one arrangement. The sweep is L7,
and the per-position contact mapping is L5. Scene has no loop over shifts
and no argument named `shift`.

## 3. Findings that need your decision

Before writing code I went to the validated old implementation to settle
the coordinate conventions rather than infer them. Three things came back,
and two of them contradict documents we are currently treating as current.

### 3.1 Which way is +x — settled, recording it

`slay_overbend_v1_50.py` builds its stations like this:

```python
vr = [(+(n_vr + 1 - j) * spacing, 0.0) for j in range(0, n_vr + 1)]   # VR0..VR3
sr = [(-R*sin((i-1)*dtheta), R*(1-cos((i-1)*dtheta))) for i in range(1, n_sr+1)]
```

So **vessel rollers sit at positive x, stinger rollers at negative x, and
SR1 is the origin.** The plot axis label agrees: `← stinger tip / catenary
… vessel →`.

That same file's own header comment says *"Stinger on LEFT, vessel deck on
RIGHT; X positive LEFT"*, which would put the stinger at **positive** x —
the opposite of what the code does. The comment is stale. Tracker item 20
read the code correctly and then flagged its own conclusion as unverified;
it can now be marked verified.

The recovered prototype (`docs/reference/build_geometry_model_STALE.py`)
gets this half right and half wrong: its stinger x is correctly negative,
but it puts vessel rollers at negative x too, so VR1 and SR2 land on top of
each other at x ≈ −8. Another reason not to copy it.

**No decision needed — just confirming I will use: vessel +x, stinger −x,
SR1 at the origin, y positive down.**

### 3.2 Vessel roller numbering runs the opposite way in config and in the old code

This is the one that matters.

**The old code numbers vessel rollers from the anchor inward.** At the
defaults (n_vr = 3, spacing 8 m):

| | VR0 | VR1 | VR2 | VR3 | SR1 |
|---|---|---|---|---|---|
| x (m) | +32 | +24 | +16 | +8 | 0 |
| role | fixed anchor | bilateral | one-sided | one-sided | stinger tangency |

VR1 is *furthest* from the stinger. The code marks it never-released
(`never_release = [f'VR{i}' for i in range(1, n_vr-1)]` → `['VR1']`), which
is physically sensible: it sits next to the anchor where the pipe is held
down regardless.

**`slay_config.yaml` assumes the opposite.** Its one-sided rule reads:

```yaml
vessel: [VR1, VR2]   # nearest the stinger -- also one-sided.
                     # every OTHER vessel roller (VR3 onward) is bilateral.
```

That only makes sense if VR1 is *nearest* the stinger and numbering
increases toward the vessel interior — the reverse of the old code.

**Why this is dangerous rather than cosmetic.** If Scene positions vessel
rollers using the old code's formula but resolves the one-sided set from
`config`'s names, the flags land on exactly the wrong rollers: the roller
beside the anchor becomes releasable and the one beside the stinger becomes
bilateral. Two of three vessel rollers get inverted contact behaviour. The
model still assembles, still converges, and returns a plausible number.

**Recommendation: adopt `config`'s convention — VR1 nearest the stinger,
numbering increasing toward the vessel.** Reasons:

- `config.py` and `slay_config.yaml` are mirrored files. Changing them to
  match the old code would be editing a mirror (G7), and the rule there is
  raise-don't-patch.
- The physics is then identical to the validated code. Under the new
  numbering the one-sided pair {VR1, VR2} sits at x = +8 and +16. Under the
  old numbering the one-sided pair {VR3, VR2} sits at x = +8 and +16. **The
  same two physical rollers.** Only the labels move.
- That gives a precise acceptance test, stated in §6.

**The anchor needs a name that does not depend on this.** Under the old
scheme it was `VR0`, the furthest station. Under the new numbering, calling
the furthest station `VR0` is actively misleading. I propose naming it
`ANCHOR` outright. It is not a contact slot in any case — the old code
excludes it from the slot list and treats it as a fixed node.

**Decision needed: adopt config's numbering (recommended), or keep the old
code's and raise a change against the mirror?**

### 3.3 Tracker item 16's quoted figures were computed at 9 m spacing

My own build instruction tells T2 to verify that arc and rectangular
positions diverge by "2.07 m at R=85, 3.04 m at R=70", citing tracker item
16. Computed at the configured 8 m spacing, the actual figures are **1.460 m
and 2.142 m**.

The tracker's numbers reproduce exactly at **9 m** spacing:

```
R=85:  45.0 − 85·sin(45/85) = 45.0 − 42.931 = 2.069   ("42.93 m vs 45.0 m")
R=70:  45.0 − 70·sin(45/70) = 45.0 − 41.958 = 3.042
```

`slay_config.yaml` says `spacing_m: 8.0`, and the old code's own remark that
"by SR6 the tangent is ~33 deg" matches 8 m at R=70 (32.74°), not 9 m. So
8 m is the right default and the tracker's figures are from a different
study.

**No decision needed — I will verify against 1.460 m / 2.142 m and correct
the T2 VERIFY clause in the build instruction.** Recording it because a
future session reading item 16 would otherwise write a failing test and
assume the code was wrong.

## 4. What Scene produces

One artifact, `Scene`, holding four things.

**The arc.** The stinger's roller-centre locus: radius R, starting at the
origin, tangent to the deck there, curving down. Askable for position,
tangent and outward normal at any arc length. R is measured to the roller
*centreline*, not to the pipe — so the arc is where roller centres sit, and
nothing on it is a pipe position.

**The stations.** One entry per roller, each carrying its name, its arc
length along the pipe path, its world position, its radius, whether it is
one-sided, and the direction it pushes. Vessel stations lie on the straight
deck; stinger stations on the arc. The anchor is a station too, flagged as
not a contact slot.

**The deck.** The straight run the vessel rollers sit on — the tangent to
the arc at its start, which is simply y = 0 in this frame.

**The extent.** How much pipe the model needs: the span from beyond the
anchor to beyond the last stinger roller, including the buffer the sweep
consumes.

Plus, once an ILS is placed, the offset that maps ILS-local positions into
scene arc length.

## 5. How each piece is built

**Arc length is the spine.** Each roller gets an arc position `s`, measured
along the pipe's path with SR1 at `s = 0`. Vessel rollers are at negative
`s`, stinger rollers positive. This is tracker item 16's decision: node
positions follow arc length, because bending is inextensible to first order
and a material point keeps its distance along the pipe. Rectangular x is
where a station physically sits; it is not where the undeformed pipe's
material lands.

Both are stored. They coincide on the deck and diverge on the arc, by the
1.46 m of §3.3 at the default configuration. Keeping both, under names that
cannot be confused (`s_arc` versus `x`), is item 17's naming rule applied to
the exact pair that caused trouble before.

**Stinger stations** step by a constant arc increment, `dtheta = spacing/R`
per span. Station *i* sits at angle `(i−1)·dtheta`, arc `R·theta`, world
position `(−R·sin θ, R·(1−cos θ))`.

**Vessel stations** sit on the deck at `x = +j·spacing` under the
recommended numbering, `y = 0`, arc `s = −j·spacing`. Arc and x agree in
magnitude here because the deck is straight — the distinction only bites on
the arc.

**The outward normal** at a stinger station is the direction the roller
pushes the pipe: away from the arc centre, toward the sea surface. At
θ = 0 that is straight up, which under y-positive-down is `(0, −1)`. The
old code states this as `n̂ = (−sin θ, −cos θ)`. Tracker item 28 warns that
this expression is correct *only* if the tangent is taken pointing toward
the stinger tip — reverse the tangent and the normal silently inverts — so
the tangent direction will be asserted in a test rather than assumed. On the
deck the normal is `(0, −1)` everywhere.

**One-sided flags** come from `config.ONE_SIDED_ROLLERS_DEFAULT`, which
resolves the stored *rule* (all SR, plus the named vessel pair) into
concrete names using `n_sr`. Scene never hardcodes the list; that is the
whole reason it is a rule.

**Roller radius** is per station, defaulting to `config.ROLLER_RADIUS_DEF`
and overridable per name. The fresh-build spec's decision 1 is explicit
that roller OD is not assumed uniform, and that a single global constant
cannot express it. Scene stores the radius; it does not compute a contact
offset from it — that needs the contact surface, which is L5's business.

**Extent** runs from beyond the anchor to beyond the last stinger station,
with buffer on both sides so the assembly can travel the full sweep without
running off the mesh. Item 7 settled the vessel-side rule as
`ceil(sweep_length / spacing)` extra vessel rollers.

**Placement** of the ILS is a single offset, applied once. `ils_builder`
says so explicitly: its definitions are ILS-local precisely so that the same
design at two locations is not two unrelated sets of node ids, and the
placement offset is applied by the SLAY builder — which is this layer.

## 6. What I would verify

| # | Check | Expected |
|---|---|---|
| 1 | Arc and x diverge on the stinger, agree on the deck | arc − \|x\| over SR1→SR6 = **1.460 m** at R=85, **2.142 m** at R=70 (8 m spacing) |
| 2 | Station geometry at R=85 | SR6 at θ = 26.96°, s = 40.0, x = −38.540, y = 9.239 |
| 3 | **One-sided set lands on the right physical rollers** | the one-sided vessel pair resolves to x = **+8 and +16**, matching the old code regardless of which naming we adopt |
| 4 | The rule scales | change `n_sr`, and every SR is still one-sided with no edit |
| 5 | Normal direction | `(0, −1)` at SR1 and on the deck; tangent asserted to point toward the tip, per item 28 |
| 6 | Vessel and stinger do not overlap in x | the defect present in the stale prototype |
| 7 | Anchor is not a contact slot | excluded from the station list the contact layer reads |

Check 3 is the important one: it is the same assertion under either naming
decision, and it is what makes §3.2 safe to resolve either way.

## 7. On the flowchart (step 3)

Scene is straight-line construction — build the arc, walk out the stations,
place the ILS, size the extent. There is no branching worth a flowchart, and
one would mostly restate §5 in boxes.

What *would* earn its place is a **coordinate-layout diagram**: a picture
showing +x toward the vessel, the arc curving to −x, y increasing downward,
and where VR1 versus VR3 actually sit. That is the thing §3.2 shows is easy
to get wrong, and a picture kills the ambiguity better than prose does.

**Proposal: substitute a coordinate-layout diagram for the flowchart.**
Your call, and the §3 exemption is stated rather than assumed either way.

## 8. Questions for you

1. **Vessel roller numbering (§3.2)** — adopt `config`'s convention (VR1
   nearest the stinger), which is my recommendation, or keep the old code's
   and raise a change against the mirrored file?
2. **Anchor naming** — `ANCHOR` rather than `VR0`, so it cannot be read as
   part of the numbering sequence?
3. **The extra stinger roller.** The old code carries `n_sr_total = n_sr + 1`
   and a corresponding slot, giving the sweep somewhere to go on the stinger
   side. Should Scene emit that extra station, or is the stinger-side buffer
   purely a matter of extent? I lean toward emitting it, so the buffer is a
   real station rather than an implicit assumption, but the old code's intent
   is not fully clear to me here.
4. **Diagram substitution (§7)** — coordinate layout instead of a flowchart?

---

## Action log

| Date | Action |
|---|---|
| 12 Sep 2026 | Draft written. Three convention findings raised; §3.2 (VR numbering inversion) blocks coding. |

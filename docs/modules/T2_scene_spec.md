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

**RESOLVED 12 Sep 2026 — config's numbering is correct.** Ruling:

> SR1 is the first stinger roller, still on the horizontal line. SR2 is the
> first roller on the curve. VR1 is the first roller inboard of SR1 on the
> straight line itself.

So vessel numbering increases *inboard*, away from the stinger, and the old
code's numbering is superseded rather than reconciled. The acceptance test
in §6 holds and is now confirmed from both directions: the one-sided pair
sits at x = +8 and +16 under the new naming, which is exactly where the old
code's releasable pair sat. The physics is unchanged; only the labels moved.

SR1 at θ = 0 on the deck tangent line is unchanged from the old code and
needed no ruling — recording it because the spec had not stated it
explicitly and a reader could otherwise assume SR1 is the first *curved*
station.

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

### 3.4 The vessel roller count changes, and it is a mirrored file — BLOCKING

Ruling, 12 Sep 2026:

> 5 vessel rollers VR1–VR5 is default, with possibility to increase based on
> component length. VR5 has all DOF fixed. VR1–VR4 are involved in the
> contact constraints. VR1–VR2 are unidirectional rollers (uplift allowed);
> VR3 onwards are bidirectional.

This is the layout it describes, at R = 85 and 8 m spacing:

| station | role | s_arc | x | y |
|---|---|---|---|---|
| VR5 | **fixed, all DOF** | −40.0 | +40.0 | 0 |
| VR4 | bidirectional | −32.0 | +32.0 | 0 |
| VR3 | bidirectional | −24.0 | +24.0 | 0 |
| VR2 | one-sided, uplift allowed | −16.0 | +16.0 | 0 |
| VR1 | one-sided, uplift allowed | −8.0 | +8.0 | 0 |
| SR1 | tangency, on the deck line | 0 | 0 | 0 |
| SR2 | first curved station | +8.0 | −7.988 | 0.376 |
| … | | | | |
| SR6 | | +40.0 | −38.540 | 9.239 |

**Two things follow that the spec did not previously account for.**

**The anchor moves inside the VR series.** The old code kept a separate
`VR0` at the far end. Under the ruling the fixed station is `VR5` — the
*last* vessel roller, not a zeroth one. So the rule is "the anchor is
`VR{n_vr}`", and my earlier proposal to name it `ANCHOR` is withdrawn: it
has a real name now. It is still excluded from the contact slot list.

**`n_vr` conflicts with the mirrored config, and its meaning changes too.**

| | value | what it counts |
|---|---|---|
| `slay_config.yaml` (mirrored) | `n_vr: 3` | contact rollers, with a separate anchor station in addition |
| This ruling | 5 | **all** vessel stations, the fixed one included (4 contact + 1 fixed) |

Both the number and the semantic differ. Under the old meaning the ruling
would be `n_vr = 4`; under the new meaning it is 5. Getting this wrong is a
silent off-by-one in the number of supports.

`slay_config.yaml` is a **mirrored file (G7)** — it belongs to
Slay-ILS-Designer-V1.0 and is not editable here. So this cannot be
implemented by patching config; it has to be raised against the source
repo. Until it is, Scene would have to either read a value it knows to be
wrong or carry a local override, and a local override in a layer whose
whole job is to read config is exactly the second-source-of-truth failure
this project keeps eliminating.

**RESOLVED 12 Sep 2026 — this repo now owns the config.** The mirror
argument turned out to be weaker than stated above. Checking what the
mirrored ILS-tier code actually reads from config gives five constants and
no more: `component_spec.py` uses OD_PIPE_DEF, T_WALL_DEF, STEEL_E and G;
`ils_builder.py` uses RHO_STEEL. It reads none of the stinger, roller,
solver, material, mesh or section blocks.

So `n_vr` is a SLAY-tier parameter that happened to share a file, and
seeking upstream approval to change a value the other repo never reads was
friction without benefit. `config.py` and `slay_config.yaml` moved out of
the mirror; `component_spec.py` and `ils_builder.py` stay in it.

`n_vr` is now 5, with the semantic written into the YAML alongside it.
`tests/test_config_ownership.py` guards the five shared constants and also
asserts the premise — if a re-sync ever brings down a `component_spec.py`
that reads something else from config, the split stops being safe and the
test says so. **Scene is unblocked.**

### 3.5 Two consequences to check, not yet resolved

**The sweep-ceiling reasoning is written against the old numbering.**
`docs/reference/slay_case.py` computes the reachable sweep as
`ceiling_elems = max(1, floor(spacing/elem_len) - 1)`, justified by "VR1
sits exactly one roller spacing from the fixed VR0 anchor BY CONSTRUCTION,
so the achievable sweep is bounded at ~one spacing REGARDLESS of n_vr",
citing tech-ref §14.4's finding that raising n_vr 10→20 "had no effect".

Under the new numbering the roller adjacent to the anchor is **VR4**, not
VR1, and the deck run grows from 32 m to 40 m. The physical constraint (the
anchor bounds the slide) is unchanged, but the sentence describing it is
now wrong, and whether the *ceiling itself* changes needs checking rather
than assuming. This is an L5/L7 concern, so it does not block Scene — but
it must be settled before T4.

**The §6 baselines were produced at the old count.** Adding a fourth
contact roller at x = +32 changes the vessel-side restraint. Tech-ref §14.4
implies this is insensitive — the extra supports sit on straight, already
supported deck far from the bending — which would mean the baselines still
reproduce. Plausible, but it is an assumption and should be verified at T5
rather than discovered at T9.

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

**Vessel stations** sit on the deck at `x = +j·spacing`, `y = 0`, arc
`s = −j·spacing`, with VR1 one spacing inboard of SR1. Arc and x agree in
magnitude here because the deck is straight — the distinction only bites on
the arc.

`VR{n_vr}` is the fixed station: all DOF restrained, and not a contact slot.
Scene emits it as a station because it is a real support the model needs,
flagged so the contact layer skips it. Every other vessel station is a
contact roller.

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
whole reason it is a rule. One-sided means uplift is allowed — the roller
pushes the pipe but cannot hold it down, so the pipe may leave the roller.
VR1 and VR2 are one-sided, VR3 and VR4 bidirectional, and `VR{n_vr}` is
outside this classification entirely because it is fixed rather than
contacting.

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
| 7 | `VR{n_vr}` is not a contact slot | excluded from the list the contact layer reads; all DOF fixed |
| 8 | SR1 is on the deck line | `y = 0`, `θ = 0`; SR2 is the first station with `y > 0` |
| 9 | VR1 is one spacing inboard of SR1 | x = +8 at 8 m spacing, and adjacent to SR1 with nothing between |
| 10 | Station count | `n_vr` vessel stations of which one is fixed, `n_sr` stinger stations of which one is the tangency |

Check 3 was the important one while §3.2 was open: it is the same assertion
under either naming, which is what made that decision safe to take either
way. It now doubles as the regression lock proving the renumbering did not
move any physical roller.

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

**1. ~~`n_vr` and the mirror~~ — RESOLVED.** Config ownership moved to
this repo; `n_vr` is 5. See §3.4.

**2. What does `n_vr` count?** I have implemented `n_vr = 5` as meaning
*all* vessel stations including the fixed one, giving four contact rollers
plus VR5. The old code's `n_vr` counted contact rollers only, with the
anchor extra — under which the same layout would be `n_vr = 4`. The YAML
comment and `test_config_ownership.py` both state the new meaning
explicitly, but **please confirm**, because it is a silent off-by-one in the
number of supports if I have read it the wrong way.

**3. The extra stinger roller.** The old code carries
`n_sr_total = n_sr + 1` and a matching slot, giving the sweep somewhere to
go on the stinger side. Should Scene emit that extra station, or is the
stinger-side buffer purely a matter of extent? I lean toward emitting it, so
the buffer is a real station rather than an implicit assumption — but the
old code's intent is not fully clear to me, and the vessel side now has its
buffer expressed as real stations, which argues for symmetry.

**4. Diagram substitution (§7)** — coordinate layout instead of a flowchart?
§3.4's table is most of it already; the picture would add where the fixed
station sits and which direction each roller can push.

---

## Action log

| Date | Action |
|---|---|
| 12 Sep 2026 | Draft written. Three convention findings raised; §3.2 (VR numbering inversion) blocks coding. |
| 12 Sep 2026 | Rulings received. §3.2 RESOLVED — config's numbering stands, old code's superseded; one-sided pair verified unmoved at x = +8/+16. New §3.4: n_vr 3→5 with the fixed station moving inside the series as VR{n_vr} — conflicts with a mirrored file, now the blocking item. New §3.5: sweep-ceiling wording and §6 baseline sensitivity both need checking before T4/T5. |

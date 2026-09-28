"""slay.physics.contact -- where each roller wants the pipe, and how hard.

A contact target says: at this station, the pipe's normal displacement should
be `dn`, interpolated from these two nodes, and the roller may push only
(one-sided) or also hold down.

THE TARGET FORMULA, and it is the one place tracker item 16 says not to get
wrong:

    dn = R * (1 - cos(theta) - theta * sin(theta))

DERIVED, not copied. Node reference positions are set by ARC LENGTH (item
16's ruling), so the straight reference pipe continues along the deck line
and the material point at arc `s` must travel to `path.position(s)`:

    u = (-(R*theta - R*sin(theta)),  R*(1 - cos(theta)))
    n = (sin(theta), -cos(theta))
    dn = u . n = R*(1 - cos - theta*sin)

BOTH VECTORS ARE IN THE MODEL FRAME, and that is the whole of lesson L048.
`scene` speaks WORLD (`x` toward the vessel); `model`, `physics` and `solve`
speak MODEL (`s` toward the stinger, `x_world = -(s + u_s)`). A normal read
off the Scene is a world vector, and these coefficients multiply MODEL DOFs,
so the `s` component flips sign and `y` does not -- `physics.frame`, the
single place it happens. The reference program had no such boundary: its
nodal coordinate IS world `x` (`slay_sliding_v0_4.py:235`, "decreasing with
node id"), so its `nx = -sin(theta)` was right there and is wrong here. `dn`
is unchanged either way -- flipping both `u_s` and `n_s` leaves the product
alone -- which is exactly why the error survived a target that matched to
machine precision.

The old formula `dn = arc_y * ny` is NOT a general projection. It is the same
dot product with the `ux*nx` term silently zero, which held only because
RECTANGULAR node positioning made `ux = 0` at the target. Under arc-length
positioning `ux` reaches 2.07 m at SR6 (R = 85), the term returns, and
keeping the old form gives a target error of 1.05 m at SR6 -- a wrong model
that still converges. `dn` and node positioning are a HARD PAIR; neither
moves without the other.

`dn` IS NEGATIVE ON THE ARC, and that is right. `n` points from the roller
toward the pipe -- upward, `-y` -- while the arc falls away below the deck
line the straight pipe continues along. So the pipe must move DOWN onto the
arc, against the normal.

THE CONTACT SURFACE IS ADDITIVE, and it comes from ONE place. What a roller
meets is `assembly.contact_at(x)`, and its contribution to the target is the
CENTRELINE LIFT above the plain-pipe baseline:

    lift = contact.y - OD_pipe/2

zero for plain pipe, positive where a deeper surface -- a thick body, a
shroud -- holds the centreline higher. `envelope_at` in the old code computed
the same thing in parallel; tracker item 18's rule is that it becomes a call
into the assembly and never a second implementation. Combination is the
assembly's LOWEST-surface rule, not a sum: where a thick body and a shroud
overlap, only the deeper one is touched, and adding them double-counts.

THE CONTACT SURFACE, `contact_surface`, and it is OPT-IN.

`LayPath.R` is measured to the ROLLER CENTRELINE. The roller top is
`r_roller` above that and the pipe's bottom surface rests on it, so the pipe
CENTRELINE really rides at `R + r_roller + r_pipe` from the arc centre:

    'centreline'  the pipe centreline is driven onto the R arc. What every
                  validated number in `docs/RESULTS.md` was computed with,
                  and the default, so adopting this option moves nothing
                  until a caller asks for it.
    'bottom'      the physical one: `R_eff = R + r_roller + OD/2`.

IT ENTERS THROUGH THE RADIUS, NEVER AS AN OFFSET ON EACH TARGET, and that is
not a stylistic choice. A uniform normal offset is physically meaningful only
through the curvature it produces; along the straight deck it is a rigid
translation with no strain effect at all. Offsetting the targets was tried in
the reference toolchain and is WRONG -- the anchor pins its node to ZERO
displacement, so lifting every roller while the anchor stays put forces a
spurious kink, and the measured plain-pipe peak jumped from x = -38 m (on the
stinger, correct) to x = +79 m (the anchor) and rose 10.5%. The closed form
already has this property: `arc_target(R_eff, 0) = 0`, so the deck sees
nothing and only the curved region moves.

AND THE MATERIAL POSITION MOVES WITH IT -- the hard pair again. Nodes here
are placed by ARC LENGTH, and the pipe does not stretch, so the material
touching the roller at angle `theta` lies at pipe-arc `R_eff * theta`, not at
the station's own `s_arc = R * theta`. The correction

    s_ref = s_arc + (R_eff - R) * theta

is zero on the deck (`theta = 0`) and grows along the arc, reaching 0.32 m at
SR7 for R = 85. Change `dn` without it and the target is right but applied to
the wrong material; that is the same class of error as L048 and it would
converge just as happily.

WHAT IS DELIBERATELY NOT HERE -- see `docs/modules/T4_physics_spec.md`:

  * HERMITE interpolation. The coefficients below are LINEAR in the two
    bracketing nodes, which is what the old code did and what M1 must
    reproduce. A beam's transverse displacement between its nodes is really
    cubic; the gap is about `L^2*kappa/8` ~ 1 mm at 0.8 m elements and
    R = 85. Raised, measured, not silently changed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import config

from slay.physics.frame import to_model_frame
from slay.scene.rollers import StationRole


@dataclass(frozen=True)
class ContactTarget:
    """One roller's demand on the pipe, in MATERIAL terms.

    `n_lo`/`n_hi` are model node indices bracketing the material position;
    `w_lo`/`w_hi` are the shape-function weights that interpolate between
    them and sum to 1.
    """
    station: str
    s_material: float          # m, arc position on the pipe
    theta: float               # rad, turn angle at the station
    normal: tuple              # unit vector, roller -> pipe, MODEL frame
    dn: float                  # m, target normal displacement
    dn_arc: float              # m, the arc term alone
    lift: float                # m, centreline lift from the contact surface
    surface_owner: str
    n_lo: int
    n_hi: int
    w_lo: float
    w_hi: float
    one_sided: bool
    radius: float              # m, the roller's own radius
    R_eff: float = 0.0         # m, radius the pipe centreline rides at
    s_station: float = 0.0     # m, the station's own arc position

    @property
    def weights(self) -> dict:
        return {self.n_lo: self.w_lo, self.n_hi: self.w_hi}


SURFACES = ('centreline', 'bottom')


def effective_radius(R: float, r_roller: float, OD: float,
                     contact_surface: str = 'centreline') -> float:
    """Radius the pipe CENTRELINE rides at.

    `R` for 'centreline'; `R + r_roller + OD/2` for 'bottom', because `R` is
    measured to the roller centreline and the pipe's bottom rests on the
    roller's top.
    """
    if contact_surface not in SURFACES:
        raise ValueError(f'contact_surface must be one of {SURFACES}, '
                         f'got {contact_surface!r}')
    if contact_surface == 'centreline':
        return R
    return R + r_roller + OD / 2.0


def arc_target(R: float, theta: float) -> float:
    """`R (1 - cos t - t sin t)`. Zero on the deck, negative on the arc."""
    return R * (1.0 - math.cos(theta) - theta * math.sin(theta))


def arc_target_by_projection(path, s: float) -> float:
    """The same number, computed as the projection it IS.

    Kept so the closed form is CHECKED rather than trusted: the two must
    agree to machine precision at every station, and if they ever stop
    agreeing the closed form is what is wrong.
    """
    if s <= 0.0:
        return 0.0
    x, y = path.position(s)
    # MODEL frame, deliberately -- this checks the vector the solver is
    # handed, not a world-frame twin of it that agrees by cancellation.
    ux, uy = -(x - (-s)), y - 0.0       # straight reference along the deck
    nx, ny = to_model_frame(path.normal(s))
    return ux * nx + uy * ny


def _bracket(nodes_s, s: float):
    """(i_lo, i_hi, w_lo, w_hi) for a material position among sorted nodes."""
    lo, hi = 0, len(nodes_s) - 1
    if s <= nodes_s[0][1]:
        return nodes_s[0][0], nodes_s[0][0], 1.0, 0.0
    if s >= nodes_s[hi][1]:
        return nodes_s[hi][0], nodes_s[hi][0], 1.0, 0.0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if nodes_s[mid][1] <= s:
            lo = mid
        else:
            hi = mid
    (i_lo, s_lo), (i_hi, s_hi) = nodes_s[lo], nodes_s[hi]
    span = s_hi - s_lo
    if span <= 0:
        return i_lo, i_lo, 1.0, 0.0
    w = (s - s_lo) / span
    return i_lo, i_hi, 1.0 - w, w


def header_nodes(model):
    """(index, s) for the pipeline's own nodes, ascending in s.

    The HEADER, not every node at y = 0. On ILS-EASB the structure's top
    chord lies on the centreline too, and a connector's `C-P` node sits
    exactly on the pipe -- coincident and deliberately distinct. A roller
    bears on the pipe, so the pipe's own elements are what say which node
    that is.
    """
    at = {n.index: n for n in model.nodes}
    ids = {i for e in model.elements if e.owner == 'pipeline'
           for i in (e.n1, e.n2)}
    return sorted(((i, at[i].s) for i in ids), key=lambda p: p[1])


def station_material(scene, contact_surface: str = 'centreline',
                     OD: float = None) -> dict:
    """{station name: pipe-arc position of the material under it at shift 0}.

    THE ONE PLACE THIS MAPPING LIVES. `contact_targets` needs it to bracket
    the right nodes and `study.sweep.critical_shifts` needs it to know when a
    component edge reaches a roller, and those two must agree or the sweep
    samples travels the contact does not see. Measured when they did not: the
    GD-TP envelope read 14.5% low and moved to the wrong position, because
    the schedule was still crossing edges at `s_arc` while the slots had moved
    to `s_arc + (R_eff - R) * theta`.

    Equals `s_arc` under 'centreline', and on the deck under either.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    out = {}
    for st in scene.stations:
        if st.role is not StationRole.CONTACT:
            continue
        theta = scene.path.theta(st.s_arc)
        R_eff = effective_radius(scene.path.R, st.radius, OD, contact_surface)
        out[st.name] = st.s_arc + (R_eff - scene.path.R) * theta
    return out


def contact_targets(model, scene, assembly=None, shift: float = 0.0,
                    s_centre: float = 0.0, OD: float = None,
                    contact_surface: str = 'centreline') -> list:
    """One `ContactTarget` per CONTACT station, in station order.

    `shift` is the arc distance the pipeline has advanced toward the stinger.
    The model's `s` is a MATERIAL coordinate, so the material point now under
    a station at arc `s_arc` started at `s_arc - shift`. It is an ARGUMENT,
    never a range: there is no loop over shifts here and no sweep index on
    anything this returns. Two Problems built at different shifts must differ
    in these targets and in nothing else, which is what T4's DONE WHEN
    clause asserts.

    Stations that do no contact -- the FIXED anchor, the LOAD station -- are
    not contact slots and get no target. That distinction is `role`'s job;
    reading it off `one_sided` cannot tell a bidirectional roller from a
    station that touches nothing.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    nodes_s = header_nodes(model)
    if not nodes_s:
        raise ValueError('no pipeline nodes to bear on')
    s_ref_of = station_material(scene, contact_surface, OD)

    out = []
    for st in scene.stations:
        if st.role is not StationRole.CONTACT:
            continue
        # `arc_target` takes an ANGLE. Passing `s_arc` straight in reads an
        # arc length as radians and returns metres of nonsense -- caught the
        # first time it ran, at -1485 m, and only because the magnitude was
        # absurd. A wrong-but-plausible number here is a wrong model that
        # converges.
        #
        # The ANGLE is the station's own, off the roller arc, and it does not
        # depend on the contact surface: concentric arcs share their angles.
        theta = scene.path.theta(st.s_arc)
        R_eff = effective_radius(scene.path.R, st.radius, OD, contact_surface)
        dn_arc = arc_target(R_eff, theta)
        # Arc length is preserved, so a pipe riding further out reaches the
        # same ANGLE at a greater pipe-arc. Zero on the deck, where theta is.
        # `station_material` owns this, because the sweep reads it too.
        s_mat = s_ref_of[st.name] - shift

        lift, owner = 0.0, 'pipe'
        if assembly is not None:
            c = assembly.contact_at(s_centre - s_mat)
            lift, owner = c.y - OD / 2.0, c.owner

        i_lo, i_hi, w_lo, w_hi = _bracket(nodes_s, s_mat)
        out.append(ContactTarget(
            station=st.name, s_material=s_mat, theta=theta,
            normal=to_model_frame(st.normal), dn=dn_arc + lift,
            dn_arc=dn_arc, lift=lift,
            surface_owner=owner, n_lo=i_lo, n_hi=i_hi, w_lo=w_lo, w_hi=w_hi,
            one_sided=st.one_sided, radius=st.radius, R_eff=R_eff,
            s_station=st.s_arc))
    return out

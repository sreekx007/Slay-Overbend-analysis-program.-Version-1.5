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

    u = (R*theta - R*sin(theta),  R*(1 - cos(theta)))
    n = (-sin(theta), -cos(theta))
    dn = u . n = R*(1 - cos - theta*sin)

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

WHAT IS DELIBERATELY NOT HERE -- see `docs/modules/T4_physics_spec.md`:

  * `R_eff = R + r_roller + r_pipe`. `LayPath.R` is to the ROLLER CENTRELINE,
    so the pipe centreline really rides at `R + r_roller + r_pipe` from the
    arc centre. Driving the pipe CENTRELINE onto the R arc -- what the
    formula above does -- is v0.4's "centreline mode". v0.5 added the offset
    form. Both are defensible and they differ; the station's `radius` is
    carried on every target so the decision can be made with a number, and
    it is raised as an open item rather than chosen here by default.

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
    normal: tuple              # unit vector, roller -> pipe
    dn: float                  # m, target normal displacement
    dn_arc: float              # m, the arc term alone
    lift: float                # m, centreline lift from the contact surface
    surface_owner: str
    n_lo: int
    n_hi: int
    w_lo: float
    w_hi: float
    one_sided: bool
    radius: float              # m, the roller's own radius -- carried, unused

    @property
    def weights(self) -> dict:
        return {self.n_lo: self.w_lo, self.n_hi: self.w_hi}


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
    ux, uy = x - (-s), y - 0.0          # straight reference along the deck
    nx, ny = path.normal(s)
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


def contact_targets(model, scene, assembly=None, shift: float = 0.0,
                    s_centre: float = 0.0, OD: float = None) -> list:
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

    out = []
    for st in scene.stations:
        if st.role is not StationRole.CONTACT:
            continue
        s_mat = st.s_arc - shift
        # `arc_target` takes an ANGLE. Passing `s_arc` straight in reads an
        # arc length as radians and returns metres of nonsense -- caught the
        # first time it ran, at -1485 m, and only because the magnitude was
        # absurd. A wrong-but-plausible number here is a wrong model that
        # converges.
        theta = scene.path.theta(st.s_arc)
        dn_arc = arc_target(scene.path.R, theta)

        lift, owner = 0.0, 'pipe'
        if assembly is not None:
            c = assembly.contact_at(s_centre - s_mat)
            lift, owner = c.y - OD / 2.0, c.owner

        i_lo, i_hi, w_lo, w_hi = _bracket(nodes_s, s_mat)
        out.append(ContactTarget(
            station=st.name, s_material=s_mat, theta=theta,
            normal=st.normal, dn=dn_arc + lift, dn_arc=dn_arc, lift=lift,
            surface_owner=owner, n_lo=i_lo, n_hi=i_hi, w_lo=w_lo, w_hi=w_hi,
            one_sided=st.one_sided, radius=st.radius))
    return out

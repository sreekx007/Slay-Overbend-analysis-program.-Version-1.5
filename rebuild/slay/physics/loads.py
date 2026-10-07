"""slay.physics.loads -- self weight, lay tension, and the restraints.

WEIGHT ACTS IN +y, because y is positive-DOWN (tracker item 26). Nothing in
this module negates it, and a NEGATIVE `Fy` that arrives here is real: a
cantilevered branch can put its point mass in uplift, and that case still
solves. Flipping the sign to "fix" it would hide a 3 mT load path.

TENSION ACTS AT THE LOAD STATION, ALONG THAT STATION'S OWN TANGENT. SR7
exists for exactly this. Applying tension at the tip with SR6's tangent put
a spurious transverse force on the end and reported 2.46% strain at SR6
against a ~0.83% reference -- a 3x error, and the reason the station count
rules differ at the two ends.

POINT MASSES COME FROM THE ILS, RESOLVED. `component.point_masses()` returns
`(node_id, mass)` with no coordinates, and an id that fails to resolve is
returned separately rather than dropped -- a mass silently excluded is worse
than one reported missing. This module refuses on a missing one, because by
the time a Problem is built there is nowhere left for it to be reported to.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import config

from slay.physics.contact import (DEFAULT_SURFACE, _bracket,
                                  header_nodes, station_material)
from slay.physics.frame import to_model_frame
from slay.scene.rollers import StationRole


@dataclass(frozen=True)
class NodalLoad:
    node: int
    fx: float = 0.0
    fy: float = 0.0
    mz: float = 0.0
    source: str = ''


@dataclass(frozen=True)
class Restraint:
    node: int
    ux: bool = True
    uy: bool = True
    rz: bool = True
    source: str = ''

    @property
    def components(self) -> tuple:
        return tuple(k for k, on in enumerate((self.ux, self.uy, self.rz))
                     if on)


def self_weight(model, sections, rho: float = None, g: float = None) -> list:
    """Distributed element weight, lumped half to each end node.

    Consistent lumping would also put end moments on each element; half-half
    is what the old implementation did and what M1 must reproduce, and the
    difference is second order in element length against a load that is
    itself small beside the lay tension. Stated, not assumed.
    """
    rho = config.RHO_STEEL if rho is None else rho
    g = config.G if g is None else g
    at = {n.index: n for n in model.nodes}

    fy = {}
    for e in model.elements:
        if e.connector is not None:
            continue                  # a connector has no length to weigh
        sec = sections[e.index]
        a, b = at[e.n1], at[e.n2]
        L = math.hypot(b.s - a.s, b.y - a.y)
        w = rho * sec.A * g * L / 2.0
        fy[e.n1] = fy.get(e.n1, 0.0) + w
        fy[e.n2] = fy.get(e.n2, 0.0) + w
    return [NodalLoad(node=i, fy=v, source='self_weight')
            for i, v in sorted(fy.items())]


def point_mass_loads(model, ils, s_centre: float = 0.0,
                     g: float = None, tol: float = 1e-6) -> list:
    """Declared point masses, placed on the model node at their position.

    Refuses on a mass whose node id does not resolve, and on one that lands
    where the model has no node: both mean the CoG and the load path
    disagree with each other, and by this layer there is no one left to warn.
    """
    g = config.G if g is None else g
    located, missing = ils.located_point_masses()
    if missing:
        raise ValueError(
            f'point masses declared at unresolved nodes {sorted(missing)}. '
            f'They would be excluded from both mass and load path.')
    at = {n.index: n for n in model.nodes}
    out = []
    for (nid, m, x, y) in located:
        s = s_centre - x
        hits = [i for i, n in at.items()
                if abs(n.s - s) <= tol and abs(n.y - y) <= tol]
        if not hits:
            raise ValueError(
                f'point mass {nid!r} ({m:.1f} kg) sits at '
                f'(s={s:.4f}, y={y:.4f}) where the model has no node')
        out.append(NodalLoad(node=min(hits), fy=m * g,
                             source=f'point_mass:{nid}'))
    return out


def lay_tension(model, scene, tension: float, shift: float = 0.0,
                contact_surface: str = DEFAULT_SURFACE,
                OD: float = None) -> list:
    """Tension at the LOAD station, along that station's own tangent.

    Applied at the header node nearest THE MATERIAL UNDER THAT STATION at
    this shift: the station is the end of the model, so there is nothing to
    interpolate between and a bracketing pair would be one-sided anyway.

    THE DIRECTION IS AWAY FROM THE VESSEL, down the catenary -- the tangent
    of INCREASING s. The model is cut at the stinger tip and the suspended
    span below pulls on that cut; the tensioner's hold is the reaction at the
    FIXED station at the vessel end. Pull the tip the other way and the
    overbend carries COMPRESSION, which is lesson L049: `path.tangent` is a
    WORLD vector and this is a model-frame `(fx, fy)`, so it crosses
    `physics.frame`. Measured as built: 10 MT of "lay tension" put 5.27 MT of
    COMPRESSION through the deck. Converted, it puts 9.25 MT of tension.

    `shift` IS NOT OPTIONAL IN THE SENSE THAT A DEFAULT SUGGESTS -- it is
    the whole of L105. This function used to take none, and picked its node
    by `|n.s - st.s_arc|` in MATERIAL coordinates, so the lay tension stayed
    bolted to the same piece of steel for an entire passage while the
    terminal contact walked inboard by the travel. From the first position
    onward the model carried a free cantilever of length `shift` with 100 MT
    on its unsupported tip, pointing in a fixed direction, and past about
    2.4 m of travel that configuration has no equilibrium: every shroud and
    long-component sweep died there with CUTBACK EXHAUSTED at lam=0.0000,
    and the Newton correction that blew up was always the LAST NODE'S.

    The suspended span leaves the pipe where the pipe leaves the stinger,
    not where it left the stinger an hour ago. So the material point is
    `station_material(...)[LOAD] - shift`, the same mapping `contact_targets`
    brackets its slots with and `study.sweep.critical_shifts` reads -- there
    is one answer to "what steel is under this station now" and all three
    ask it the same way. At shift 0 this picks the node it always picked, so
    no single-position result moves.
    """
    if tension == 0.0:
        return []
    st = scene.load
    s_ref = station_material(scene, contact_surface, OD).get(st.name,
                                                             st.s_arc)
    s_mat = s_ref - shift
    tx, ty = to_model_frame(scene.path.tangent(st.s_arc))
    # INTERPOLATED BETWEEN THE BRACKETING NODES, not snapped to the nearest.
    #
    # Snapping was the second half of L105 and it only shows in a CHAINED
    # sweep. `solve.passage` ramps the contact targets by `lam` and applies
    # the loads at FULL VALUE from the first Newton iteration -- "cutback
    # cannot reduce a load", as its own docstring says. So a tension that
    # jumps from one node to the next between positions moves 100 MT a whole
    # element in one unrampable step, and the chained solve has no way to
    # take it: mode B (every position from virgin state) swept the full
    # 10.128 m while mode A still died at 2.4384 on the identical problem.
    #
    # Interpolating makes the transfer continuous in `shift`: the load slides
    # across the element the way the contact slot above it does, and for the
    # same reason. `_bracket` and `header_nodes` are imported rather than
    # reimplemented because there must be ONE bracketing rule -- two is how
    # L048 and L095 happened.
    i_lo, i_hi, w_lo, w_hi = _bracket(header_nodes(model), s_mat)
    out = []
    for node, w in ((i_lo, w_lo), (i_hi, w_hi)):
        if w == 0.0:
            continue          # a slot exactly on a node gets one load, as before
        out.append(NodalLoad(node=node, fx=tension * tx * w,
                             fy=tension * ty * w,
                             source=f'tension:{st.name}'))
    return out


def boundary_conditions(model, scene, tol: float = 1e-6,
                        vertical_at=()) -> list:
    """All DOF at the FIXED station, plus any VERTICAL-only supports asked
    for.

    `vertical_at` is a list of arc positions to restrain in `uy` alone. It
    exists for the sweep buffer: spare pipe added at the vessel end to feed
    the passage would otherwise hang off the back of the anchor as a bare
    cantilever, and at 20 m of feedstock that is a real bending stress on a
    length whose only job is to be there. A vertical support stands for the
    deck rollers the pipe actually rests on behind the tensioner. It holds
    `uy` only -- the pipe must still be free to move along its own axis and
    to rotate, or the support would fight the feed it exists to allow.

    The FIXED station is the model's anchor and it is NOT a contact slot --
    `role` is what says so. A station list read through `one_sided` alone
    cannot tell an anchor from a bidirectional roller, because neither is in
    it.
    """
    fixed = [st for st in scene.stations if st.role is StationRole.FIXED]
    if not fixed:
        raise ValueError('no FIXED station: the model has no anchor')
    at = {n.index: n for n in model.nodes}
    ids = {i for e in model.elements if e.owner == 'pipeline'
           for i in (e.n1, e.n2)}
    out = []
    for st in fixed:
        node = min(ids, key=lambda i: abs(at[i].s - st.s_arc))
        if abs(at[node].s - st.s_arc) > tol:
            raise ValueError(
                f'{st.name} is at s={st.s_arc:.4f} and the nearest header '
                f'node is at {at[node].s:.4f}. A restraint needs a node '
                f'under it -- ask the model for the station.')
        out.append(Restraint(node=node, source=st.name))

    for s_v in vertical_at:
        node = min(ids, key=lambda i: abs(at[i].s - s_v))
        if abs(at[node].s - s_v) > tol:
            raise ValueError(
                f'vertical support asked for at s={s_v:.4f} and the nearest '
                f'header node is at {at[node].s:.4f}. A support needs a node '
                f'under it -- ask the model for the station.')
        out.append(Restraint(node=node, ux=False, uy=True, rz=False,
                             source=f'vertical@{s_v:+.3f}'))
    return out

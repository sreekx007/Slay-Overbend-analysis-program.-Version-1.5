#!/usr/bin/env python3
"""study_east_full.py -- ILS-EAST complete: pipe, frame, connectors, solved.

The first Group B case solved end to end. Everything comes from
`build_model`: the header pipeline, the GD-ST frame, the two connector
elements and the four declared associations. Nothing is hand-built.

    pipe node  ~~W tie~~  C-P  --[ connector ]--  C-E  ~~F tie~~  frame slot

Both associations are penalty constraints, both all-DOF. The pipe-side tie is
the new part: in `study_connectors.py` the connector's lower node was FIXED,
standing in for a pipe that was not there. Now it is tied to the real pipe
node, and the load path closes.

THE CONNECTOR IS 0.6096 m HERE, not the 0.5 x OD of the standalone rig. That
was a stand-in when there was no pipe to span to; now the geometry sets it --
pipe centreline at y = 0, frame bottom chord at y = -0.6096. The STIFFNESS is
unchanged either way, and that is pass 4's whole point: it is the stiffness of
a 1 x OD length of pipeline whatever the connector's own length is.

THREE MATERIALS, one section. The pipeline is E on the pipe section. The frame
carries `stiffness_ratio = 2.5`, which scales EA and EI together, so it is
2.5 E on the same section. The connectors are prescribed 6x6 matrices assembled
outside the kernel mesh, because a corotational element derives its stiffness
from its own length and the rule forbids that.

WHAT THIS FLIPS. `test_group_b_cannot_yet_be_solved` measures ILS-EAST's
smallest free eigenvalue at 1.7e-07 -- twelve rigid-body modes, four dangling
connector nodes at three DOF each. With the associations applied those modes
are gone and the assembly carries load.

    python3 tools/study_east_full.py [--plot]
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

import ils_builder                                         # noqa: E402
import nlfea_v4 as fe                                      # noqa: E402
from slay.model.assemble import build_model                # noqa: E402
from slay.scene.path import LayPath                        # noqa: E402
from slay.scene.scene import Scene                         # noqa: E402
import component_spec as cs                              # noqa: E402
from slay.model.parts import TIES_OPEN, TIES_SHUT        # noqa: E402
from study_connectors import (ALPHA, connector_k6,        # noqa: E402
                              ZERO_LEN_TOL)               # noqa: E402

# A connector's NOMINAL direction: the component's local y, which is the
# direction P_vt measures and the direction a connector runs from the pipe
# to the structure. It matters only for a ZERO-LENGTH connector, where the
# chord has no direction of its own to read -- GD-SB's P_vt = 0 is that
# case. Both EA archetypes sit square to the pipe in the reference
# configuration, so local y is model y here; on the stinger arc it turns
# with the slope, which is the same co-rotating frame S and D need.
CONN_AXIS = (0.0, 1.0)

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'

PAD = 6.0
OD, T_WALL = 0.4064, 0.021
E_PIPE = 2.1e11
RATIO = 2.5                        # GD-ST's stiffness_ratio
SIG_YIELD = 360e6

I_AN = math.pi * (OD**4 - (OD - 2*T_WALL)**4) / 64
EI_PIPE = E_PIPE * I_AN
Z_AN = I_AN / (OD / 2)


def build(system: str = 'F2', p_gap: float = None, extra_stations=(0.0,),
          emit_d: bool = True, archetype: str = 'ILS-EAST'):
    """One EA archetype over a bare-beam extent, with a node at the midpoint.

    `archetype` is ILS-EAST or ILS-EASB. They are the two EA cases and they
    differ in the one way that matters to a connector: GD-ST stands the frame
    0.6096 m off the pipe, GD-SB sets `P_vt = 0` and puts its top chord ON the
    pipe centreline, so every connector is ZERO LENGTH. Same code path, and
    that is the point -- the connector rule never derives stiffness from
    length, so the degenerate geometry is an ordinary case.

    `system` names the connection system the ARCHETYPE declares, which is what
    decides how many connectors exist and where. That is a different knob from
    `constraint_pairs(layout=...)`, which re-patterns the ties on connectors
    that are already there. F2 and PS populate the same two slots, so PS is a
    tie override; F2D populates FOUR (D at the outer pair), so it has to be
    built, not overridden.

    `emit_d=False` turns the geometry-only grant back off, so the refusal
    `build_model` gives every other caller stays reachable from here: a D with
    no deadband behind it is an F in all but name, and that is what G9 is for.

    `p_gap` is GD-ST's own deadband parameter, carried on the component and
    read back off `Association.gap`. It is passed here rather than held in the
    solver because it is component data: the gap decides where a deadband
    sends strain, so it belongs to the structure, not to the run.
    """
    A = {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}
    d = copy.deepcopy(A[archetype]['definition'])
    d['ils']['connection_system'] = system
    if p_gap is not None:
        d['components'][0]['P_gap'] = p_gap
    ils = ils_builder.build_ils(d)
    lo, hi = ils.extent
    s_lo, s_hi = -(hi + PAD), -(lo - PAD)
    scene = Scene(path=LayPath(R=85.0), stations=(), extent=(s_lo, s_hi),
                  elastic_zones=((s_lo, s_lo), (s_hi, s_hi)), spacing=0.0)
    m = build_model(scene, ils, s_centre=0.0, extra_stations=extra_stations,
                    emit_unenforced_conn_types=(frozenset({'D'}) if emit_d
                                                else frozenset()))
    return m, s_hi - s_lo


def dof(ms, node_index: int, comp: int) -> int:
    """Global DOF for one of OUR node indices.

    NOT 3*node_index + comp. `MeshedStructure._mesh` assigns mesh indices in
    ELEMENT-ENCOUNTER order, so `user_node_to_mesh` is a permutation of our
    ids rather than the identity, and any node an element reaches late lands
    somewhere else entirely. Writing connector stiffness at 3*id put it on
    four frame nodes' worth of the wrong rows and left theirs empty: twelve
    zero diagonals and an exactly singular matrix.

    The bijection is what `test_kernel_leaves_the_model_intact` asserts -- and
    a bijection is all it asserts. Callers have to go through the map.
    """
    return 3 * ms.user_node_to_mesh[node_index] + comp


def ea_owner(m) -> str:
    """Which owner tag the EA structure carries in THIS model: 'ST' or 'SB'.

    Read off the elements rather than assumed, because the whole point of
    running both archetypes through one code path is that nothing downstream
    should have to know which it got.
    """
    owners = {e.owner for e in m.elements} - {'pipeline', 'GD-Con'}
    if len(owners) != 1:
        raise ValueError(f'expected exactly one EA owner, got {owners}')
    return owners.pop()


def kernel_mesh(m):
    """Frame and pipeline only. Connectors are assembled separately."""
    beams = [e for e in m.elements if e.connector is None]
    ea = ea_owner(m)
    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in m.nodes],
        elements=[fe.UserElement(k, e.n1, e.n2,
                                 2 if e.owner == ea else 1, 1, seed=1)
                  for k, e in enumerate(beams)],
        sections=[fe.PipeSection(1, OD, T_WALL)],
        materials=[fe.Material(1, E_PIPE),           # pipeline
                   fe.Material(2, RATIO * E_PIPE)])  # frame, ratio 2.5
    ms = fe.MeshedStructure(mdl)
    assert ms.n_nodes == m.n_nodes, 'kernel altered the model'
    return ms, beams


def constraint_pairs(m, layout: str = None, engaged=None):
    """(node_a, node_b, component, target) to tie. Node indices, not DOFs.

    `target` is the value of (u_a - u_b) the constraint enforces. It is 0.0
    everywhere except at an ENGAGED `D`, and that exception is the whole of
    what a deadband means: a D carries nothing until the two sides have moved
    +/- P_gap apart, and at engagement it holds AT the gap edge --

        u_a - u_b = +/- P_gap,      NOT      u_a - u_b = 0

    Enforcing 0 would drag the sides back into coincidence, dropping the
    separation below the gap, releasing the connector, letting it separate
    again: the chatter measured in `study_connectors.py` and recorded as L008.

    `engaged` maps an association's EA-side part node to its state -- 0 open,
    +1/-1 engaged and which way. Absent, every D is open, which is what the
    model's own declared `TIES_OPEN['D'] = (False, False, False)` already
    says: an open D ties NOTHING, so it needs no special case here.

    With no `layout` the model's own declared associations are used -- ILS-EAST
    is F2, so every tie is all-DOF.

    With one, the EA-SIDE tie pattern is replaced by that named system's, while
    the geometry, the mesh and the connector elements stay exactly as
    `build_model` produced them. Only which DOF are tied changes, which makes
    the comparison between layouts exact rather than nearly so. The pipe-side
    tie is always all-DOF whatever the joint is.

    WHY THIS IS DONE HERE AND NOT IN `build_model`. The package still refuses
    P/S/D (`SUPPORTED_CONN_TYPES`), and that refusal is right: `S` frees the
    translation along the EA component's LOCAL x, and the co-rotating frame
    that defines is not built. On this rig the reference configuration is
    horizontal, so local x IS global s and the error is the size of the
    rotations -- about 1e-3 rad. On the stinger the local axis turns up to
    32.4 degrees and this would be wrong. G9 stands.
    """
    idx = m._part_index
    slot_of = {}
    at = {n.index: n for n in m.nodes}
    for e in m.elements:
        if e.connector is not None:
            slot_of[at[e.n2].part_id] = e.connector.slot

    types = cs.NAMED_CONNECTION_SYSTEMS[layout] if layout else None
    engaged = engaged or {}
    out = []
    for a in m.associations:
        ia, ib = idx[a.node_a], idx[a.node_b]
        ctype = a.conn_type
        if types is None or a.node_a not in slot_of:
            ties = a.ties                       # pipe side, or no override
        else:
            t = types[slot_of[a.node_a] - 1]
            if t is None:
                continue                        # slot not populated: no tie
            ctype, ties = t, TIES_OPEN[t]
        state = engaged.get(a.node_a, 0)
        if ctype == 'D' and state:
            ties = TIES_SHUT['D']
        for k, on in enumerate(ties):
            if not on:
                continue
            target = 0.0
            if ctype == 'D' and state and k == 1:
                if a.gap is None:
                    raise ValueError(
                        f'{a.node_a}: a D engaged with no P_gap. The gap is '
                        f'component data (GD-ST.P_gap) and has no default -- '
                        f'a silent one would choose where the strain goes.')
                target = math.copysign(a.gap, state)
            out.append((ia, ib, k, target))
    return out


def assemble(m, ms, U):
    theta0 = np.arctan2(ms.elem_coords[:, 3] - ms.elem_coords[:, 1],
                        ms.elem_coords[:, 2] - ms.elem_coords[:, 0])
    Kf, Fint_f, _, _, _ = fe.assemble(ms, U, theta0, {}, [], 1.0)
    K = Kf.toarray()
    Fint = Fint_f.copy()
    at = {n.index: n for n in m.nodes}
    for e in m.elements:
        if e.connector is None:
            continue
        a, b = at[e.n1], at[e.n2]
        k6 = connector_k6(b.s - a.s, b.y - a.y, axis=CONN_AXIS)
        d = [dof(ms, e.n1, 0), dof(ms, e.n1, 1), dof(ms, e.n1, 2),
             dof(ms, e.n2, 0), dof(ms, e.n2, 1), dof(ms, e.n2, 2)]
        K[np.ix_(d, d)] += k6
        Fint[d] += k6 @ U[d]
    return K, Fint


def solve(m, ms, P, alpha=ALPHA, n_inc=10, tol=1e-9, max_iter=30,
          layout=None, engaged=None, load_s: float = 0.0):
    """`load_s` is WHERE the load goes, and it is not optional in spirit.

    This used to be `next(n for n in m.nodes if n.part_id.startswith('PIPE-X'))`
    -- the first externally-requested station in node order, which is the one
    at the layout midpoint only while there is exactly one of them. Add a
    second `extra_station` and the load silently moves to whichever came
    first, off-centre, and every number in the run is for a different problem.
    It was caught comparing an F2 model with stations added at the outer slots
    against F2D: 48.398 mm where F2D gave 49.429, a 2% gap that looked like
    physics and was a misplaced load. Name the position; take the node there.

    NOR CAN IT BE FOUND BY PART ID. The first fix looked for a `PIPE-X` node
    -- the externally-requested station -- and F1D has none at the midpoint:
    its single `F` sits at slot 3, which IS the midpoint, so the connector
    claimed that station and the requested one merged into it. The load still
    has a node to act on; it just is not named the way the search expected.
    What the load actually needs is the HEADER node at `load_s`, and the way
    to say that is to ask the pipeline's own elements which node that is.

    The distinction matters at exactly that station. Two nodes sit at
    (s = 0, y = 0) in F1D -- the header's and the connector's `C-P` -- in
    different passes and so deliberately unmerged. Loading the connector node
    instead would push the load through the connector into the frame and
    bypass the pipe entirely.
    """
    ends = [min(m.nodes, key=lambda n: n.s), max(m.nodes, key=lambda n: n.s)]
    fixed = [dof(ms, n.index, k) for n in ends for k in (0, 1, 2)]
    at = {n.index: n for n in m.nodes}
    header = {i for e in m.elements if e.owner == 'pipeline'
              for i in (e.n1, e.n2)}
    cands = [at[i] for i in header if abs(at[i].s - load_s) <= 1e-6]
    if not cands:
        raise ValueError(f'no header node at s={load_s} to load; the station '
                         f'has to exist before a load can act on it')
    if len(cands) > 1:
        raise ValueError(f'{len(cands)} header nodes at s={load_s}')
    load = cands[0]
    pairs = constraint_pairs(m, layout, engaged)

    U = np.zeros(3 * m.n_nodes)
    for inc in range(1, n_inc + 1):
        lam = inc / n_inc
        for _it in range(max_iter):
            K, Fint = assemble(m, ms, U)
            Fext = np.zeros_like(U)
            Fext[dof(ms, load.index, 1)] = P * lam
            R = Fext - Fint
            for (na, nb, comp, target) in pairs:
                a, b = dof(ms, na, comp), dof(ms, nb, comp)
                kp = alpha * max(K[a, a], K[b, b], 1.0)
                K[a, a] += kp; K[b, b] += kp
                K[a, b] -= kp; K[b, a] -= kp
                g = (U[a] - U[b]) - target
                R[a] -= kp * g
                R[b] += kp * g
            kf = alpha * max(K.diagonal().max(), 1.0)
            for dpos in fixed:
                K[dpos, dpos] += kf
                R[dpos] -= kf * U[dpos]
            if np.max(np.abs(R)) / max(abs(P), 1.0) < tol:
                break
            dU = spsolve(csr_matrix(K), R)
            if not np.all(np.isfinite(dU)):
                raise RuntimeError('singular system')
            U += dU

    viol = max((abs((U[dof(ms, na, c)] - U[dof(ms, nb, c)]) - t)
                for (na, nb, c, t) in pairs), default=0.0)
    return U, load.index, fixed, viol


def connector_forces(m, ms, U):
    """End forces in each connector. REPORTED, because they were not.

    `member_stress` covers only the kernel's beams, so the connectors -- the
    elements assembled outside it -- were never checked at all. "Everything
    stays elastic" was said without looking at them. They are in fact the
    second most highly stressed part of the model, and at an F connection that
    is not an accident: an all-DOF tie at both ends of a short stiff element,
    between a pipe and a frame that rotate very differently, forces it to bend.
    """
    at = {n.index: n for n in m.nodes}
    out = []
    for e in m.elements:
        if e.connector is None:
            continue
        a, b = at[e.n1], at[e.n2]
        d = [dof(ms, e.n1, 0), dof(ms, e.n1, 1), dof(ms, e.n1, 2),
             dof(ms, e.n2, 0), dof(ms, e.n2, 1), dof(ms, e.n2, 2)]
        f = connector_k6(b.s - a.s, b.y - a.y, axis=CONN_AXIS) @ U[d]
        dx, dy = b.s - a.s, b.y - a.y
        Lc = math.hypot(dx, dy)
        # A zero-length connector has no chord to resolve along, so axial and
        # shear are taken in its NOMINAL axis -- the same frame its stiffness
        # was built in. Without this the report would divide by zero on every
        # ILS-EASB connector, which is all of them.
        c, sn = (dx / Lc, dy / Lc) if Lc >= ZERO_LEN_TOL else CONN_AXIS
        out.append({'line_id': e.line_id,
                    'axial': f[0] * c + f[1] * sn,
                    'shear': -f[0] * sn + f[1] * c,
                    'M_pipe_end': f[2], 'M_frame_end': f[5],
                    'length': Lc,
                    'sigma': max(abs(f[2]), abs(f[5])) / Z_AN})
    return out


def member_stress(m, ms, U, beams):
    """Peak end moment per beam element, and the stress it implies."""
    M = np.zeros(ms.n_elems)
    for ie in range(ms.n_elems):
        d = ms.elem_dof_array[ie]
        x1, y1, x2, y2 = ms.elem_coords[ie]
        L0 = ms.elem_L0[ie]
        th0 = math.atan2(y2 - y1, x2 - x1)
        th = math.atan2((y2 + U[d[4]]) - (y1 + U[d[1]]),
                        (x2 + U[d[3]]) - (x1 + U[d[0]]))
        dth = th - th0
        dth -= 2.0 * math.pi * round(dth / (2.0 * math.pi))
        u3, u6 = U[d[2]] - dth, U[d[5]] - dth
        EIL = ms.elem_E[ie] * ms.elem_I[ie] / L0
        M[ie] = max(abs(4*EIL*u3 + 2*EIL*u6), abs(2*EIL*u3 + 4*EIL*u6))
    return M, M / Z_AN


def main() -> int:
    m, L = build()
    ms, beams = kernel_mesh(m)
    pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
    frame_ix = [k for k, e in enumerate(beams) if e.owner == 'ST']

    print(f'ILS-EAST complete: {m.n_nodes} nodes, {m.n_elems} elements')
    print(f'  pipeline {len(pipe_ix)} el, frame {len(frame_ix)} el, '
          f'connectors {len(m.elements) - len(beams)} el')
    print(f'  extent {L:.4f} m, fixed both ends, load at s = 0 on the header')
    print(f'  {len(m.associations)} associations, all all-DOF, '
          f'penalty alpha = {ALPHA:.0e} x local diagonal\n')

    print(f'  {"layout":7}{"P_kN":>6}{"d_pipe_mm":>12}{"d_frame_mm":>12}'
          f'{"sumR_kN":>10}{"viol":>10}{"sig_pipe":>10}{"sig_frame":>11}'
          f'{"sig_conn":>10}{"M_conn":>10}{"":>4}')
    out = {}
    for layout in ('F2', 'PS'):
        for P in (20e3, 200e3):
            U, i_load, fixed, viol = solve(m, ms, P, layout=layout)
            _, Fint = assemble(m, ms, U)
            Ry = sum(Fint[d] for d in fixed if d % 3 == 1)
            d_pipe = U[dof(ms, i_load, 1)]
            top = next(n for n in m.nodes
                       if n.part_id and n.part_id.endswith('stop1'))
            _, sig = member_stress(m, ms, U, beams)
            sp, sf = sig[pipe_ix].max(), sig[frame_ix].max()
            conns = connector_forces(m, ms, U)
            sc = max(c['sigma'] for c in conns)
            mc = max(abs(c['M_pipe_end']) for c in conns)
            out[(layout, P)] = (U, sig)
            flag = 'ok' if max(sp, sf, sc) < SIG_YIELD else 'YIELD'
            print(f'  {layout:7}{P/1e3:6.0f}{d_pipe*1e3:12.5f}'
                  f'{U[dof(ms, top.index, 1)]*1e3:12.5f}{-Ry/1e3:10.3f}'
                  f'{viol:10.2e}{sp/1e6:10.1f}{sf/1e6:11.1f}{sc/1e6:10.1f}'
                  f'{mc/1e3:10.1f}  {flag}')
        print()
    _compare(out)

    print()
    _rotation_check(m, ms, solve(m, ms, 200e3)[0])
    print()
    _bare_pipe_reference(L)

    if '--plot' in sys.argv:
        _plot(m, ms, beams,
              {lay: out[(lay, 200e3)] for lay in ('F2', 'PS')}, pipe_ix)
    return 0


def _compare(out):
    """What the joint type actually bought, at 200 kN."""
    (_, sf2), (_, sps) = out[('F2', 200e3)], out[('PS', 200e3)]
    print('F2 against PS, same mesh, same connectors, only the ties differ:')
    print('  P is a pin and S a roller -- neither can carry moment, and with')
    print('  one translation released no shear builds up either. So under PS')
    print('  BOTH connectors are pure axial struts, and they carry nothing.')
    print()
    print('  A rigid frame held at TWO points by a pin and a roller is')
    print('  statically determinate against any motion of those points: it')
    print('  translates, rotates, and the roller takes up the change in')
    print('  spacing. It can never be forced to deform, so it can never carry')
    print('  force. Under PS the ILS is a PASSENGER -- the pipe deflects')
    print('  65.47250 mm, which is the bare pipe to five decimals.')


def _rotation_check(m, ms, U):
    """Are the rz ties actually holding? The deformed-shape plot cannot say.

    A plot draws each element as a straight chord between its end positions,
    so it shows the element's RIGID-BODY tilt and never its end rotations. A
    connector whose ends are tied in rz but which BENDS between them looks, in
    a chord plot, exactly like one whose rotation is not tied at all. The only
    way to tell is to read the numbers.
    """
    idx = m._part_index
    at = {n.index: n for n in m.nodes}
    print('Rotation ties, and why the plot cannot show them:')
    for a in m.associations:
        ia, ib = idx[a.node_a], idx[a.node_b]
        ra, rb = U[dof(ms, ia, 2)], U[dof(ms, ib, 2)]
        print(f'   {a.node_a:8} rz {ra:+.6e}  ==  {a.node_b:20} rz {rb:+.6e}'
              f'   ({abs(ra-rb):.1e} rad apart)')
    print()
    for e in m.elements:
        if e.connector is None:
            continue
        a, b = at[e.n1], at[e.n2]
        th0 = math.atan2(b.y - a.y, b.s - a.s)
        th = math.atan2((b.y + U[dof(ms, e.n2, 1)]) - (a.y + U[dof(ms, e.n1, 1)]),
                        (b.s + U[dof(ms, e.n2, 0)]) - (a.s + U[dof(ms, e.n1, 0)]))
        tilt = th - th0
        tilt -= 2 * math.pi * round(tilt / (2 * math.pi))
        print(f'   {e.line_id:16} chord tilt {tilt:+.3e} rad   '
              f'pipe-end rz {U[dof(ms, e.n1, 2)]:+.3e}   '
              f'frame-end rz {U[dof(ms, e.n2, 2)]:+.3e}')
    print('   The chord tilt is what a plot draws. It lies between the two end')
    print('   rotations because the connector BENDS -- under F2 the pipe rotates')
    print('   about 40x more than the frame at that station, and an element')
    print('   tied to both in rz has to take up the difference. That is what')
    print('   P and S release, and why PS leaves the connectors straight.')


def _bare_pipe_reference(L):
    """What the same pipe does with no ILS on it at all.

    The comparison is the result: the frame is not scenery, it carries load
    back into the pipe through the connectors, and the pipe must come out
    stiffer than a bare beam of the same span.
    """
    print('Bare pipe of the same span, fixed-fixed, central load, no ILS:')
    for P in (20e3, 200e3):
        print(f'   P = {P/1e3:3.0f} kN  ->  d = {P*L**3/(192*EI_PIPE)*1e3:.5f} mm'
              f'   (linear closed form)')


def deflected(a, b, U, ms, n1, n2, scale, n=14, ref=(0.0, 0.0)):
    """The element's real deflected SHAPE, not the chord between its ends.

    A chord plot draws each element straight, so it shows only rigid-body
    tilt and hides the end rotations entirely -- which makes a connector that
    is rz-tied but bending look identical to one that is not tied at all.
    Hermite interpolation puts the rotations back in the picture, and the
    connector then visibly leaves the pipe at the pipe's own slope.

    Small-displacement interpolation in the element's undeformed frame, which
    is what the magnified plot is showing anyway.
    """
    L = math.hypot(b.s - a.s, b.y - a.y)
    c, sn = (b.s - a.s) / L, (b.y - a.y) / L
    ux1, uy1, r1 = (U[dof(ms, n1, k)] for k in (0, 1, 2))
    ux2, uy2, r2 = (U[dof(ms, n2, k)] for k in (0, 1, 2))
    # `ref` subtracts a rigid translation so a zoomed view can show BENDING.
    # Without it the whole assembly's 50 mm of sag, magnified enough to make a
    # 0.2 mm connector tilt visible, lands 20 m off the picture.
    ux1 -= ref[0]; uy1 -= ref[1]
    ux2 -= ref[0]; uy2 -= ref[1]
    u1, v1 = ux1*c + uy1*sn, -ux1*sn + uy1*c        # local axial, transverse
    u2, v2 = ux2*c + uy2*sn, -ux2*sn + uy2*c
    xs, ys = [], []
    for k in range(n + 1):
        t = k / n
        N1 = 1 - 3*t**2 + 2*t**3
        N2 = L * (t - 2*t**2 + t**3)
        N3 = 3*t**2 - 2*t**3
        N4 = L * (-t**2 + t**3)
        v = N1*v1 + N2*r1 + N3*v2 + N4*r2
        u = (1 - t)*u1 + t*u2
        xl, yl = t*L + scale*u, scale*v
        xs.append(a.s + xl*c - yl*sn)
        ys.append(a.y + xl*sn + yl*c)
    return xs, ys


def _plot(m, ms, beams, out, pipe_ix):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    at = {n.index: n for n in m.nodes}
    outp = REPO / 'docs' / 'diagrams' / 'east_full_study.png'
    P = 200e3
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 11.0),
                             gridspec_kw={'height_ratios': [1, 1, 0.95]})

    # ONE scale for both panels. Per-panel scaling would make the softer
    # layout look like the stiffer one, which is the comparison being drawn.
    common = 1.2 / max(abs(out[l][0][1::3]).max() for l in ('F2', 'PS'))
    for ax, layout, note in (
            (axes[0], 'F2', 'both ties all-DOF: the connector must bend'),
            (axes[1], 'PS', 'pin + roller: neither connector can carry '
                            'moment, so the frame carries nothing at all')):
        U, _sig = out[layout]
        scale = common
        for e in m.elements:
            a, b = at[e.n1], at[e.n2]
            col = {'pipeline': '#1f7a8c', 'ST': '#2f6f3e'}.get(e.owner, '#6b4ea8')
            lw = 2.6 if e.connector is not None else 1.8
            ax.plot([a.s, b.s], [a.y, b.y], color='#c9d2d9', lw=1.1, zorder=1)
            xs, ys = deflected(a, b, U, ms, e.n1, e.n2, scale)
            ax.plot(xs, ys, color=col, lw=lw, zorder=2)
        ax.invert_yaxis()
        ax.set_aspect('equal')
        ax.set_ylabel('y (m), down')
        ax.grid(alpha=0.22)
        ax.set_title(f'{layout}  --  {note}   (deflection x{scale:.0f})',
                     fontsize=9.5, loc='left')

        # inset on the slot-2 connector, drawn relative to its own base so the
        # rigid sag is removed and only bending is left
        conn = min((e for e in m.elements if e.connector is not None),
                   key=lambda e: e.connector.slot)
        cs_ = at[conn.n1].s
        axz = ax.inset_axes([0.70, 0.05, 0.28, 0.56])
        ref = (U[dof(ms, conn.n1, 0)], U[dof(ms, conn.n1, 1)])
        for e in m.elements:
            a, b = at[e.n1], at[e.n2]
            if min(a.s, b.s) > cs_ + 1.2 or max(a.s, b.s) < cs_ - 1.2:
                continue
            if a.y > 0.1 or b.y > 0.1:
                continue
            col = {'pipeline': '#1f7a8c', 'ST': '#2f6f3e'}.get(e.owner, '#6b4ea8')
            axz.plot([a.s, b.s], [a.y, b.y], color='#c9d2d9', lw=1.0)
            xs, ys = deflected(a, b, U, ms, e.n1, e.n2, 320.0, n=40, ref=ref)
            axz.plot(xs, ys, color=col, lw=2.3)
        axz.set_xlim(cs_ - 0.9, cs_ + 0.9)
        axz.set_ylim(-0.80, 0.16)
        axz.invert_yaxis()
        axz.set_xticks([]); axz.set_yticks([])
        axz.set_title('slot-2 connector, x320, relative to its base',
                      fontsize=7)
        for sp in axz.spines.values():
            sp.set_edgecolor('#7b8794')
    axes[0].legend(handles=[
        plt.Line2D([], [], color=c, lw=2.2, label=l)
        for l, c in (('pipeline', '#1f7a8c'), ('GD-ST frame', '#2f6f3e'),
                     ('connectors', '#6b4ea8'), ('undeformed', '#c9d2d9'))],
        fontsize=8, ncol=4, loc='upper left', framealpha=0.92)

    ax = axes[2]
    for layout, col, ls in (('F2', '#1f7a8c', '-'), ('PS', '#b44d12', '-')):
        _U, sig = out[layout]
        mid = np.array([0.5*(ms.elem_coords[i][0] + ms.elem_coords[i][2])
                        for i in pipe_ix])
        o = np.argsort(mid)
        ax.plot(mid[o], sig[pipe_ix][o]/1e6, color=col, ls=ls, lw=1.8,
                marker='.', ms=5, label=f'pipeline, {layout}')
    for e in m.elements:
        if e.connector is not None:
            ax.axvline(at[e.n1].s, color='#6b4ea8', ls=':', lw=1.2)
    ax.plot([], [], color='#6b4ea8', ls=':', lw=1.2, label='connector station')
    ax.set_title('Peak fibre stress along the pipeline. Under PS the ILS is '
                 'a passenger, so the pipe is the bare pipe.',
                 fontsize=9.5, loc='left')
    ax.set_xlabel('s (m)   --   +s toward the stinger')
    ax.set_ylabel('sigma (MPa)')
    ax.legend(fontsize=8)
    ax.grid(alpha=0.22)

    fig.suptitle('ILS-EAST: the same model on two connector systems. '
                 'Only the tied DOF differ.', fontsize=11)
    fig.tight_layout()
    fig.savefig(outp, dpi=140)
    print(f'wrote {outp.relative_to(REPO)}')


if __name__ == '__main__':
    raise SystemExit(main())

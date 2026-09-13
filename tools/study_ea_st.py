#!/usr/bin/env python3
"""study_ea_st.py -- the GD-ST frame on its own, fixed at its connector slots.

The EA structure isolated from the pipe. Fixing the frame AT slots 2 and 4
replaces the connectors with real restraints, so neither Group B blocker
applies: no penalty constraints are needed, and no zero-length connector
element has to be formed. What is left is the question worth asking first --
does the frame itself mesh and solve correctly?

THE FRAME. A closed rectangular portal, 6.5024 m wide by 1.6256 m tall, its
bottom chord at y = -0.6096 (above the pipe centreline, y positive DOWN) and
its top chord at y = -2.2352. Twelve segments, `stiffness_ratio = 2.5`
throughout -- K_member(L) = 2.5 x K_pipe(L), which scales EA and EI together,
so it is applied here as a material of 2.5 E on the pipe section.

TWO LOAD POINTS, AND THE DIFFERENCE IS THE POINT. Fixing slots 2 and 4 cuts
the frame into two independent parts:

    sslot3   the bottom-chord centre, BETWEEN the two fixed nodes. The rest
             of the frame hangs off fixed points and carries nothing, so this
             is a 2.167 m fixed-fixed beam with a central load and a closed
             form. It is the CONTROL: it validates the rig, not the frame.

    stop1    the top-chord centre, OUTSIDE the fixed span. The load must
             travel the top chord, down both legs, along the outer bottom
             chord and into the slots. This is the case that exercises the
             whole frame, and it has no closed form.

Running only the first would look like a frame test and be a beam test.

    python3 tools/study_ea_st.py [--plot]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))

import ils_builder                                         # noqa: E402
import nlfea_v4 as fe                                      # noqa: E402
from slay.model.assemble import build_model                # noqa: E402
from slay.scene.path import LayPath                        # noqa: E402
from slay.scene.scene import Scene                         # noqa: E402

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'

OD, T_WALL = 0.4064, 0.021
E_PIPE = 2.1e11
RATIO = 2.5                       # GD-ST's stiffness_ratio
TOL, N_INC = 1e-6, 20

I_AN = math.pi * (OD**4 - (OD - 2*T_WALL)**4) / 64
EI_EFF = RATIO * E_PIPE * I_AN
Z_AN = I_AN / (OD / 2)


def frame_model():
    """The GD-ST frame alone, lifted out of a full ILS-EAST assembly.

    Built through `build_model` rather than meshed standalone, so this
    exercises pass 2 -- the pass whose boundary keeps the frame off the pipe.
    The pipeline elements are then dropped and the frame renumbered.
    """
    A = {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}
    ils = ils_builder.build_ils(A['ILS-EAST']['definition'])
    scene = Scene(path=LayPath(R=85.0), stations=(), extent=(-12.0, 12.0),
                  elastic_zones=((-12.0, -12.0), (12.0, 12.0)), spacing=0.0)
    m = build_model(scene, ils, s_centre=0.0)

    # The FRAME line only. `startswith('ST:')` also matches 'ST:connector2',
    # which would drag in the two connector elements -- and their pipe-side
    # ends are tied to the pipe by a penalty that nothing applies yet, so they
    # dangle. Four dangling nodes at three DOF each is exactly the 12
    # zero-energy modes measured for ILS-EAST in the Group B blocker test.
    frame = [e for e in m.elements
             if e.line_id.endswith(':frame') and e.connector is None]
    keep, renum = [], {}
    for e in frame:
        for g in (e.n1, e.n2):
            if g not in renum:
                renum[g] = len(keep)
                keep.append(m.nodes[g])
    return m, frame, keep, renum


def part_node(m, keep, renum, tail: str) -> int:
    """Local index of a named part node, e.g. 'sslot3'."""
    for n in m.nodes:
        if n.part_id and n.part_id.endswith(tail) and n.index in renum:
            return renum[n.index]
    raise KeyError(tail)


def solve(keep, frame, renum, fixed_locals, load_local, P):
    mdl = fe.Model(
        nodes=[fe.Node(i, n.s, n.y) for i, n in enumerate(keep)],
        elements=[fe.UserElement(k, renum[e.n1], renum[e.n2], 1, 1, seed=1)
                  for k, e in enumerate(frame)],
        sections=[fe.PipeSection(1, OD, T_WALL)],
        # K_member = 2.5 x K_pipe scales EA and EI together, so a material of
        # 2.5 E on the pipe section is the ratio exactly -- not an analogy.
        materials=[fe.Material(1, RATIO * E_PIPE)])
    ms = fe.MeshedStructure(mdl)
    assert ms.n_nodes == len(keep)

    bc = [3 * ms.user_node_to_mesh[i] + k for i in fixed_locals for k in (0, 1, 2)]
    U, _, _ = fe.solve_step(
        ms, np.zeros(ms.n_dofs),
        {'joint_init': [fe.JointLoad(1, load_local, 0.0, P, 0.0)]},
        bc, [0.0] * len(bc), n_increments=N_INC, tol=TOL, max_iter=60)
    return U, ms, bc


def reactions(U, ms):
    """Internal force vector at the converged state.

    `theta_states` is seeded with each element's UNDEFORMED angle rather than
    NaN. NaN disables the De Souza unwrap inside `assemble`, and for any
    element whose chain runs in -s that makes theta0 = pi read against a
    deformed angle of ~-pi: a 2 pi phantom rotation, an enormous moment, and
    reactions that do not balance. Rotations here are small, so unwrapping
    against theta0 is exact.

    The solve itself is unaffected -- `solve_step` carries a real theta_state
    across increments. This only bites post-processing that re-assembles.
    """
    theta0 = np.arctan2(ms.elem_coords[:, 3] - ms.elem_coords[:, 1],
                        ms.elem_coords[:, 2] - ms.elem_coords[:, 0])
    _, Fint, _, _, _ = fe.assemble(ms, U, theta0, {}, [], 1.0)
    return Fint


def member_forces(U, ms):
    """Axial force and peak end moment per element, corotational."""
    N = np.zeros(ms.n_elems)
    M = np.zeros(ms.n_elems)
    for ie in range(ms.n_elems):
        d = ms.elem_dof_array[ie]
        x1, y1, x2, y2 = ms.elem_coords[ie]
        L0 = ms.elem_L0[ie]
        xd1, yd1 = x1 + U[d[0]], y1 + U[d[1]]
        xd2, yd2 = x2 + U[d[3]], y2 + U[d[4]]
        th0 = math.atan2(y2 - y1, x2 - x1)
        th = math.atan2(yd2 - yd1, xd2 - xd1)
        # De Souza unwrap, the same one `assemble()` does. Without it an
        # element whose chain runs in -s has th0 = pi, atan2 returns ~-pi for
        # the deformed angle, and dth comes out ~-2pi -- giving a moment of
        # 4EI/L x 2pi that is enormous and IDENTICAL for every load, because
        # it is measuring the wrap rather than the deformation. The pipeline
        # rig never saw it: its elements all run one way, so th0 = 0.
        dth = th - th0
        dth -= 2.0 * math.pi * round(dth / (2.0 * math.pi))
        u4 = math.hypot(xd2 - xd1, yd2 - yd1) - L0
        u3, u6 = U[d[2]] - dth, U[d[5]] - dth
        N[ie] = ms.elem_E[ie] * ms.elem_A[ie] / L0 * u4
        EIL = ms.elem_E[ie] * ms.elem_I[ie] / L0
        M[ie] = max(abs(4*EIL*u3 + 2*EIL*u6), abs(2*EIL*u3 + 4*EIL*u6))
    return N, M


def main() -> int:
    m, frame, keep, renum = frame_model()
    s2 = part_node(m, keep, renum, 'sslot2')
    s4 = part_node(m, keep, renum, 'sslot4')
    s3 = part_node(m, keep, renum, 'sslot3')
    top = part_node(m, keep, renum, 'stop1')

    print(f'GD-ST frame alone: {len(keep)} nodes, {len(frame)} elements')
    print(f'  stiffness_ratio {RATIO}  ->  EI_eff = {EI_EFF:.4e} N.m^2')
    print(f'  fixed at sslot2 (s={keep[s2].s:+.4f}) and '
          f'sslot4 (s={keep[s4].s:+.4f}), all DOF')
    print(f'  span between supports: {abs(keep[s2].s - keep[s4].s):.4f} m\n')

    cases = [
        ('sslot3  bottom-chord centre, BETWEEN the supports', s3, True),
        ('stop1   top-chord centre, OUTSIDE the fixed span', top, False),
    ]
    for label, node, has_cf in cases:
        print(f'== load at {label}')
        print(f'   node at (s={keep[node].s:+.4f}, y={keep[node].y:+.4f})')
        print(f'   {"P_kN":>7}{"d_mm":>12}{"sum_Ry_kN":>12}{"N_max_kN":>11}'
              f'{"M_max_kNm":>12}{"sig_MPa":>10}')
        for P in (20e3, 200e3):
            U, ms, bc = solve(keep, frame, renum, (s2, s4), node, P)
            d = U[3 * ms.user_node_to_mesh[node] + 1]
            N, M = member_forces(U, ms)
            Ry = sum(reactions(U, ms)[3 * ms.user_node_to_mesh[i] + 1]
                     for i in (s2, s4))
            print(f'   {P/1e3:7.0f}{d*1e3:12.5f}{Ry/1e3:12.3f}'
                  f'{np.abs(N).max()/1e3:11.1f}{M.max()/1e3:12.2f}'
                  f'{M.max()/Z_AN/1e6:10.1f}')
        if has_cf:
            L = abs(keep[s2].s - keep[s4].s)
            for P in (20e3, 200e3):
                print(f'   closed form, fixed-fixed L={L:.4f} m, P={P/1e3:.0f} kN:'
                      f'  d = {P*L**3/(192*EI_EFF)*1e3:.5f} mm')
        print()

    print('The control is the point of comparison: the bottom-chord case has a')
    print('closed form because fixing slots 2 and 4 decouples everything else.')
    print('The top-chord case does not, and is the one that loads the frame.')

    if '--plot' in sys.argv:
        _plot(m, frame, keep, renum, s2, s4, s3, top)
    return 0


def _plot(m, frame, keep, renum, s2, s4, s3, top):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    out = REPO / 'docs' / 'diagrams' / 'ea_st_frame_study.png'
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, (node, label) in zip(axes, ((s3, 'load at sslot3 (between supports)'),
                                        (top, 'load at stop1 (top chord)'))):
        P = 200e3
        U, ms, _ = solve(keep, frame, renum, (s2, s4), node, P)
        scale = 0.25 / max(abs(U[1::3]).max(), 1e-12)
        for e in frame:
            a, b = renum[e.n1], renum[e.n2]
            ax.plot([keep[a].s, keep[b].s], [keep[a].y, keep[b].y],
                    color='#b0bcc6', lw=1.4, zorder=1)
            ax.plot([keep[a].s + scale*U[3*a], keep[b].s + scale*U[3*b]],
                    [keep[a].y + scale*U[3*a+1], keep[b].y + scale*U[3*b+1]],
                    color='#1f7a8c', lw=2.0, zorder=2)
        for i, c, mk in ((s2, '#8b2f3f', 's'), (s4, '#8b2f3f', 's'),
                         (node, '#6b4ea8', 'o')):
            ax.plot(keep[i].s, keep[i].y, mk, color=c, ms=8, zorder=3)
        ax.invert_yaxis()
        ax.set_aspect('equal')
        ax.set_title(f'{label}\nP = 200 kN, deflection x{scale:.0f}', fontsize=9)
        ax.set_xlabel('s (m)')
        ax.grid(alpha=0.25)
    axes[0].set_ylabel('y (m), positive DOWN')
    fig.suptitle('GD-ST frame, fixed at slots 2 and 4 (red). '
                 'Grey = undeformed, blue = deformed.', fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    print(f'\nwrote {out.relative_to(REPO)}')


if __name__ == '__main__':
    raise SystemExit(main())

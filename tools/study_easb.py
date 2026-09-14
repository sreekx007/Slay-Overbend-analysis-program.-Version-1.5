#!/usr/bin/env python3
"""study_easb.py -- ILS-EASB: the zero-length connector, and the same systems.

EA-SB is the other EA component, and it is the one the connector rule was
written for. GD-ST stands its frame 0.6096 m off the pipe. GD-SB sets
`P_vt = 0`, which puts its TOP CHORD ON THE PIPE CENTRELINE, so every one of
its connectors is ZERO LENGTH:

    ILS-EAST      pipe  ----[ 0.6096 m connector ]----  frame, below the pipe
    ILS-EASB      pipe  ----[   0 m connector    ]----  frame, ON the pipe

That is not a degenerate case to be special-cased around. It is the DEFAULT
for this archetype, it is what the whole "stiffness of a 1 x OD length of
pipeline, never derived from length" rule exists to make ordinary, and it is
the case an earlier length-derived stiffness would have left undefined exactly
where it was most needed.

WHAT RUNS THROUGH UNCHANGED. Every system EA-ST was taken through -- F2, PS,
F1D, F2D -- runs on EA-SB through the same code path, with the archetype as a
parameter and nothing else switched. The deadband sweeps live in
`study_east_deadband.py --archetype ILS-EASB`; this file carries what is
specific to EA-SB.

THREE THINGS ARE PARTICULAR TO IT.

1. THE CONNECTORS ARE ZERO LENGTH, so the corotational basis that works for
   EA-ST cannot be used -- it divides by the chord length. The element becomes
   a relative-DOF spring, and the three stiffnesses come from the rule rather
   than from geometry. See `study_connectors._zero_length_k6`.

2. SEVEN NODE PAIRS ARE COINCIDENT AND MUST STAY DISTINCT. GD-SB's slot nodes
   sit exactly on the pipe centreline, so pipe nodes, connector nodes and
   structure nodes land on the same point. This is the case that found the
   kernel's coordinate-keyed node merge (L001): `sslot3` welded itself to the
   pipe's load node at every element size and every pad length tried. Passes
   keep them apart; the kernel now keys on node id; the count is asserted.

3. THE FRAME ACTS COMPOSITELY, not as a thing hanging below. Its top chord is
   coincident with the pipe and its body is below, so the pair behaves as one
   deep section: the connectors carry a HORIZONTAL force couple and moment,
   and no vertical force at all.

    python3 tools/study_easb.py [--plot]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

import study_east_full as east                             # noqa: E402
import study_east_deadband as db                           # noqa: E402
from study_connectors import (ALPHA, connector_k6,         # noqa: E402
                              ZERO_LEN_TOL, OD, E_PIPE,
                              A_PIPE, I_PIPE)

ARCH = 'ILS-EASB'
MERGE_TOL = 0.01


def coincident_pairs(m, tol=MERGE_TOL):
    """(pipe node, structure node) pairs closer than the merge tolerance.

    They are legal, they are the default on this archetype, and they must be
    DISTINCT nodes. Physical connectivity comes from elements and penalty
    ties, never from two things happening to occupy the same coordinate.
    """
    at = {n.index: n for n in m.nodes}
    pipe = {i for e in m.elements if e.owner == 'pipeline'
            for i in (e.n1, e.n2)}
    other = {i for e in m.elements if e.owner != 'pipeline'
             for i in (e.n1, e.n2)}
    out = []
    for i in sorted(pipe):
        for j in sorted(other - {i}):
            a, b = at[i], at[j]
            if abs(a.s - b.s) < tol and abs(a.y - b.y) < tol:
                out.append((i, j, a.s, a.y))
    return out


def _bare(L, P):
    return P * L**3 / (192 * east.EI_PIPE)


def main() -> int:
    m, L = east.build(archetype=ARCH, system='F2')
    ms, beams = east.kernel_mesh(m)
    ea = east.ea_owner(m)
    pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
    frame_ix = [k for k, e in enumerate(beams) if e.owner == ea]
    conns = [e for e in m.elements if e.connector is not None]

    print(f'{ARCH} complete: {m.n_nodes} nodes, {m.n_elems} elements')
    print(f'  pipeline {len(pipe_ix)} el, frame {len(frame_ix)} el ({ea}), '
          f'connectors {len(conns)} el')
    print(f'  extent {L:.4f} m, fixed both ends, load at s = 0 on the header')
    print(f'  penalty alpha = {ALPHA:.0e} x local diagonal\n')

    _zero_length(m, conns)
    print()
    _coincidence(m)
    print()
    _systems(L)
    print()
    _composite(m, ms)
    print()
    _against_east()

    if '--plot' in sys.argv:
        _plot(L)
    return 0


def _zero_length(m, conns):
    """Every connector on this archetype has no length, and it does not
    matter -- which is the rule, demonstrated rather than asserted."""
    print('Connector lengths, and the rule that makes them irrelevant:')
    for e in sorted(conns, key=lambda e: e.connector.slot):
        print(f'   {e.line_id:18} slot {e.connector.slot}  '
              f'length {e.connector.length:.4f} m  '
              f'stiffness rule {e.connector.stiffness!r}')

    K = connector_k6(0.0, 0.0)
    w = np.linalg.eigvalsh(K)
    zero = int(np.sum(np.abs(w) < 1e-6 * np.abs(w).max()))
    print()
    print('   The 6x6 of a zero-length connector:')
    print(f'      symmetric            {np.allclose(K, K.T)}')
    print(f'      rigid-body modes     {zero}  (must be 3)')
    for name, u in (('translate along s', [1, 0, 0, 1, 0, 0]),
                    ('translate along y', [0, 1, 0, 0, 1, 0]),
                    ('rotate about it  ', [0, 0, 1, 0, 0, 1])):
        f = K @ np.array(u, float)
        print(f'      {name}    max |f| = {np.abs(f).max():.2e}')
    EA_, EI_ = E_PIPE * A_PIPE, E_PIPE * I_PIPE
    print(f'      k_axial      EA/L0     = {EA_/OD:.4e} N/m')
    print(f'      k_transverse 12EI/L0^3 = {12*EI_/OD**3:.4e} N/m')
    print(f'      k_rotation   EI/L0     = {EI_/OD:.4e} N.m/rad')
    print('   All three at L0 = OD, none at the connector\'s own length --')
    print('   which is zero, and which is why the rule is not length-derived.')


def _coincidence(m):
    pairs = coincident_pairs(m)
    print(f'Coincident nodes, kept distinct: {len(pairs)} pairs within '
          f'{MERGE_TOL} m')
    for (i, j, s, y) in pairs:
        print(f'   node {i:3d} and node {j:3d} both at '
              f'(s = {s:+.4f}, y = {y:+.4f})')
    print('   GD-SB\'s slot nodes sit ON the pipe centreline, so this is the')
    print('   archetype that found the kernel keying mesh nodes by rounded')
    print('   COORDINATE (L001): sslot3 welded itself to the pipe\'s load node')
    print('   at every element size and pad length tried. Merging happens')
    print('   within a pass and never across; the kernel keys on node id.')


def _systems(L):
    """Every system EA-ST was taken through, on EA-SB. Same code path."""
    print('The same connection systems as EA-ST, on EA-SB:')
    print(f'  {"system":8}{"conns":>6}{"nodes":>7}{"elems":>7}'
          f'{"d20_mm":>10}{"d200_mm":>11}{"vs bare":>10}'
          f'{"sig_pipe":>10}{"sig_frame":>11}{"sig_conn":>10}')
    rows = {}
    for name, build_kw, layout in (
            ('F2', dict(system='F2'), None),
            ('PS', dict(system='F2'), 'PS'),
            ('F1D open', dict(system='F1D', p_gap=16e-3), None),
            ('F1D shut', dict(system='F1D', p_gap=0.8e-3), None),
            ('F2D open', dict(system='F2D', p_gap=6e-3), None),
            ('F2D shut', dict(system='F2D', p_gap=0.3e-3), None)):
        mm, LL = east.build(archetype=ARCH, **build_kw)
        mss, bb = east.kernel_mesh(mm)
        ea = east.ea_owner(mm)
        p_ix = [k for k, e in enumerate(bb) if e.owner == 'pipeline']
        f_ix = [k for k, e in enumerate(bb) if e.owner == ea]
        ds = {}
        for P in (20e3, 200e3):
            if 'D' in name:
                U, i_load, _f, _info = db.solve_deadband(mm, mss, P)
            else:
                U, i_load, _f, _v = east.solve(mm, mss, P, layout=layout)
            ds[P] = (U, i_load)
        U, i_load = ds[200e3]
        _M, sig = east.member_stress(mm, mss, U, bb)
        cf = east.connector_forces(mm, mss, U)
        d200 = U[east.dof(mss, i_load, 1)]
        d20 = ds[20e3][0][east.dof(mss, ds[20e3][1], 1)]
        rows[name] = (mm, mss, bb, U, d200)
        n_conn = len([e for e in mm.elements if e.connector is not None])
        print(f'  {name:8}{n_conn:6d}{mm.n_nodes:7d}{mm.n_elems:7d}'
              f'{d20*1e3:10.5f}{d200*1e3:11.5f}'
              f'{d200/_bare(LL, 200e3)*100:9.1f}%'
              f'{sig[p_ix].max()/1e6:10.1f}{sig[f_ix].max()/1e6:11.1f}'
              f'{max(c["sigma"] for c in cf)/1e6:10.1f}')
    print()
    print(f'  Bare pipe of the same span, closed form: '
          f'{_bare(L, 20e3)*1e3:.5f} / {_bare(L, 200e3)*1e3:.5f} mm')
    print('  PS is a passenger here too -- a rigid frame held by a pin and a')
    print('  roller is statically determinate against any motion of those')
    print('  points, so it can never be forced to deform. The zero-length')
    print('  connector changes none of that: the joint TYPE is what decides')
    print('  whether the frame works, not the connector\'s geometry.')
    return rows


def _composite(m, ms):
    """What the connectors actually carry, and why it is not vertical."""
    print('What an EA-SB connector carries, at 200 kN on F2:')
    U, _i, _f, _v = east.solve(m, ms, 200e3)
    print(f'   {"connector":18}{"len_m":>8}{"axial_kN":>11}{"shear_kN":>11}'
          f'{"M_pipe_kNm":>13}{"M_frame_kNm":>14}')
    for c in east.connector_forces(m, ms, U):
        print(f'   {c["line_id"]:18}{c["length"]:8.4f}{c["axial"]/1e3:11.3f}'
              f'{c["shear"]/1e3:11.3f}{c["M_pipe_end"]/1e3:13.3f}'
              f'{c["M_frame_end"]/1e3:14.3f}')
    print('   Axial here is the connector\'s NOMINAL axis -- the P_vt')
    print('   direction, perpendicular to the pipe -- because a zero-length')
    print('   chord has no direction of its own to resolve along.')
    print()
    print('   Zero vertical force, equal and opposite horizontal force, equal')
    print('   and opposite moment. That is COMPOSITE ACTION, not a frame')
    print('   hanging off the pipe: GD-SB\'s top chord is coincident with the')
    print('   pipe and its body is below, so the two bend as one deep section')
    print('   and the connectors transfer the interface shear. The vertical')
    print('   force is zero for the same reason it is on EA-ST F2 -- two')
    print('   mirror-image connectors that must sum to zero are each zero.')


def _against_east():
    """EA-ST and EA-SB on the same systems. Different spans, so the fraction
    of the bare pipe is the only fair comparison."""
    print('EA-ST against EA-SB, each as a fraction of ITS OWN bare pipe:')
    print(f'  {"system":10}{"EAST_mm":>10}{"of bare":>10}'
          f'{"EASB_mm":>11}{"of bare":>10}')
    for name, kw, layout in (('F2', dict(system='F2'), None),
                             ('PS', dict(system='F2'), 'PS'),
                             ('F1D open', dict(system='F1D', p_gap=99e-3), None),
                             ('F2D open', dict(system='F2D', p_gap=99e-3), None)):
        cells = []
        for arch in ('ILS-EAST', 'ILS-EASB'):
            mm, LL = east.build(archetype=arch, **kw)
            mss, _bb = east.kernel_mesh(mm)
            U, i_load, _f, _v = east.solve(mm, mss, 200e3, layout=layout)
            d = U[east.dof(mss, i_load, 1)]
            cells.append((d * 1e3, d / _bare(LL, 200e3) * 100))
        print(f'  {name:10}{cells[0][0]:10.4f}{cells[0][1]:9.1f}%'
              f'{cells[1][0]:11.4f}{cells[1][1]:9.1f}%')
    print()
    print('  EA-SB shields its pipe LESS than EA-ST does on F2 (82% of bare')
    print('  against 74%), and the reason is the geometry the zero-length')
    print('  connector comes from: GD-ST stands its frame off the pipe on a')
    print('  0.61 m lever, GD-SB lies along it. The lever is what turns a')
    print('  frame into a second flange.')


def _plot(L):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    outp = REPO / 'docs' / 'diagrams' / 'easb_study.png'
    cases = (('F2', dict(system='F2'), None),
             ('PS', dict(system='F2'), 'PS'),
             ('F2D, gap 0.30 mm (both D shut)',
              dict(system='F2D', p_gap=0.3e-3), None))
    fig, axes = plt.subplots(len(cases) + 1, 1, figsize=(11.5, 13.0),
                             gridspec_kw={'height_ratios': [1, 1, 1, 1.15]})

    built = []
    for name, kw, layout in cases:
        mm, LL = east.build(archetype=ARCH, **kw)
        mss, bb = east.kernel_mesh(mm)
        if 'F2D' in name:
            U, i_load, _f, _info = db.solve_deadband(mm, mss, 200e3)
        else:
            U, i_load, _f, _v = east.solve(mm, mss, 200e3, layout=layout)
        built.append((name, mm, mss, bb, U, U[east.dof(mss, i_load, 1)]))

    common = 1.0 / max(abs(b[4][1::3]).max() for b in built)
    for ax, (name, mm, mss, bb, U, d) in zip(axes, built):
        at = {n.index: n for n in mm.nodes}
        ea = east.ea_owner(mm)
        for e in mm.elements:
            a, b = at[e.n1], at[e.n2]
            if e.connector is not None:
                # A zero-length connector has nothing to draw. Mark where it
                # is instead of pretending it has extent.
                ax.plot([a.s + U[east.dof(mss, e.n1, 0)] * common],
                        [a.y + U[east.dof(mss, e.n1, 1)] * common],
                        marker='D', ms=7,
                        color='#b44d12' if e.connector.conn_type == 'D'
                        else '#6b4ea8', zorder=4)
                continue
            col = '#1f7a8c' if e.owner == 'pipeline' else '#2f6f3e'
            ax.plot([a.s, b.s], [a.y, b.y], color='#c9d2d9', lw=1.0, zorder=1)
            xs, ys = east.deflected(a, b, U, mss, e.n1, e.n2, common)
            ax.plot(xs, ys, color=col, lw=1.9, zorder=2)
        ax.invert_yaxis(); ax.set_aspect('equal'); ax.grid(alpha=0.22)
        ax.set_ylabel('y (m), down')
        ax.set_title(f'{name}   --   d = {d*1e3:.3f} mm '
                     f'({d/_bare(L, 200e3)*100:.0f}% of the bare pipe)   '
                     f'(x{common:.0f})', fontsize=9.5, loc='left')
    axes[0].legend(handles=[
        plt.Line2D([], [], color=c, lw=2.0, ls=ls, marker=mk, ms=6, label=lb)
        for lb, c, ls, mk in (('pipeline', '#1f7a8c', '-', ''),
                              ('GD-SB frame', '#2f6f3e', '-', ''),
                              ('F connector (zero length)', '#6b4ea8',
                               'none', 'D'),
                              ('D connector (zero length)', '#b44d12',
                               'none', 'D'),
                              ('undeformed', '#c9d2d9', '-', ''))],
        fontsize=7.5, ncol=2, loc='lower right', framealpha=0.92)

    ax = axes[-1]
    for (name, mm, mss, bb, U, _d), col in zip(built, ('#1f7a8c', '#b44d12',
                                                       '#7a4bb8')):
        _M, sig = east.member_stress(mm, mss, U, bb)
        ix = [k for k, e in enumerate(bb) if e.owner == 'pipeline']
        mid = np.array([0.5 * (mss.elem_coords[i][0] + mss.elem_coords[i][2])
                        for i in ix])
        o = np.argsort(mid)
        ax.plot(mid[o], sig[ix][o] / 1e6, color=col, lw=1.8, marker='.', ms=5,
                label=f'pipeline, {name}')
    at = {n.index: n for n in built[0][1].nodes}
    for e in built[0][1].elements:
        if e.connector is not None:
            ax.axvline(at[e.n1].s, color='#6b4ea8', ls=':', lw=1.2)
    ax.plot([], [], color='#6b4ea8', ls=':', lw=1.2, label='connector station')
    ax.set_title('Peak fibre stress along the pipeline. Under PS the frame is '
                 'a passenger, so the pipe is the bare pipe.',
                 fontsize=9.5, loc='left')
    ax.set_xlabel('s (m)   --   +s toward the stinger')
    ax.set_ylabel('sigma (MPa)')
    ax.legend(fontsize=8); ax.grid(alpha=0.22)

    fig.suptitle('ILS-EASB: every connector is zero length, and the joint '
                 'type is still the only thing that decides the answer.',
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(outp, dpi=140)
    print(f'\nwrote {outp.relative_to(REPO)}')


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""study_east_f2d.py -- ILS-EAST on F2D, and what the deadband gap does.

F2D is the first system whose GEOMETRY differs. F2 and PS populate the same
two slots, so PS was a tie override on an F2 model -- same nodes, same
elements, only which DOF are tied. F2D populates FOUR:

    slot   1        2        3        4        5
    F2    ---       F       ---       F       ---
    F2D    D        F       ---       F        D

so it has to be BUILT, not overridden. The two extra connectors at the outer
slots are `D`: pure supports, restraining the perpendicular translation only,
and only once the two sides have moved P_gap apart. A D ties nothing at all
while its gap is open -- not sliding, not rotation, not even the direction it
supports.

WHAT THE GAP IS. `P_gap` is GD-ST's own parameter and it has NO DEFAULT, on
purpose: a deadband REDISTRIBUTES strain rather than removing it, and the gap
decides where the strain goes. So it is carried on the component, flows
through `ils.connectors_of` into `Association.gap`, and is read back off the
association at solve time. It is component data, never a solver knob.

THE EXPERIMENT the gap sweep runs. At 200 kN the outer slots move 3.004 mm
relative to the frame with every D open. So a gap above that can never close
and F2D must reproduce F2 EXACTLY; a gap below it closes, the outer supports
pick up load, and the assembly stiffens toward the limit where the D is a
rigid roller. Five gaps straddle the threshold, and the 20 kN column shows the
other half of the point: engagement is a property of the gap AND the load, not
of the gap alone.

G9, and how this file stays inside it. `build_model` refuses `D` --
`SUPPORTED_CONN_TYPES` is {F, W}. The refusal is right and it still stands:
the package has no deadband and no co-rotating frame, so a D it "supported"
would be an F in all but name. What it grants here is
`emit_unenforced_conn_types={'D'}`: the nodes, the element and the declared
Association -- type, ties, gap, skewed flag -- and nothing else, with a
warning on the model saying so. The ENFORCEMENT is in this file, and the
tables below report the engaged state of every D at every gap, which is what
makes the claim checkable rather than asserted.

The frame is horizontal here, so the EA-ST local y is the global y and the
deadband is measured in global axes. That is exact at the reference
configuration. On the stinger the local axis turns up to 32.4 degrees and a D
is one of the two types that would notice.

    python3 tools/study_east_f2d.py [--plot]
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
from study_connectors import ALPHA                         # noqa: E402

SIG_YIELD = east.SIG_YIELD

# Five gaps, straddling the 3.004 mm the outer slots move at 200 kN with
# every D open. Two above it, three below. Not round numbers for their own
# sake -- 3.5 and 2.5 mm bracket the threshold as tightly as the sweep can
# without landing on it, which is where a deadband is worth watching.
GAPS = (5.0e-3, 3.5e-3, 2.5e-3, 1.0e-3, 0.25e-3)

MAX_PASSES = 12
F_TOL = 1e-6                      # release tolerance, as a fraction of P


def d_associations(m):
    """The D associations, in slot order. EA side only -- the pipe side of a
    D connector is a W tie like every other, all-DOF, always on."""
    return [a for a in m.associations if a.conn_type == 'D']


def solve_deadband(m, ms, P, alpha=ALPHA, n_inc=10, tol=1e-9, max_iter=30):
    """Newton with an ACTIVE SET over the D connectors.

    Two decisions, and they are not the same test:

    ENGAGE on separation. An open D is not there at all, so the only thing
    that can close it is the two sides moving |P_gap| apart.

    RELEASE on FORCE. Once engaged the separation sits AT the gap edge by
    construction -- that is what the +/-P_gap target means -- so testing
    separation again would say "still at the gap" forever and the support
    could never let go. What tells you it should is the sign of the force it
    is carrying: a support pushes, and when the constraint would have to PULL
    to hold the gap, the sides are coming back inside it and the D is open.

        engaged at +gap  ->  the tie must act in -,  and vice versa

    This is the correction recorded as L008. The earlier version enforced
    u_a - u_b = 0 on an engaged D, which dragged it back to coincidence,
    released it, let it separate, and never settled: four flips and a reported
    state that disagreed with the displacement it returned.
    """
    assoc = d_associations(m)
    idx = m._part_index
    engaged = {a.node_a: 0 for a in assoc}
    info = {'flips': 0, 'passes': 0, 'forces': {}}

    for _p in range(MAX_PASSES):
        info['passes'] += 1
        U, i_load, fixed, viol = east.solve(m, ms, P, alpha=alpha,
                                            n_inc=n_inc, tol=tol,
                                            max_iter=max_iter,
                                            engaged=engaged)
        K, _Fint = east.assemble(m, ms, U)
        new = {}
        forces = {}
        for a in assoc:
            ia, ib = idx[a.node_a], idx[a.node_b]
            da, db = east.dof(ms, ia, 1), east.dof(ms, ib, 1)
            sep = U[da] - U[db]
            state = engaged[a.node_a]
            kp = alpha * max(K[da, da], K[db, db], 1.0)
            if not state:
                forces[a.node_a] = 0.0
                new[a.node_a] = (int(math.copysign(1, sep))
                                 if abs(sep) > a.gap else 0)
                continue
            g = sep - math.copysign(a.gap, state)
            f_on_a = -kp * g            # what the tie does to the C-E node
            forces[a.node_a] = f_on_a
            # a support pushes against the direction it engaged; if it would
            # have to pull that way instead, the gap has reopened
            new[a.node_a] = 0 if f_on_a * state > F_TOL * abs(P) else state
        info['forces'] = forces
        if new == engaged:
            break
        info['flips'] += 1
        engaged = new

    info['engaged'] = dict(engaged)
    info['violation'] = viol
    return U, i_load, fixed, info


def free_separation(m, ms, P):
    """How far the outer slots move apart with every D open.

    This is the threshold the sweep straddles, and measuring it is the only
    honest way to choose the gaps: a sweep picked by eye can miss the
    transition entirely and report five rows of the same number.
    """
    U, _i, _f, _v = east.solve(m, ms, P)
    idx = m._part_index
    out = {}
    for a in d_associations(m):
        ia, ib = idx[a.node_a], idx[a.node_b]
        out[a.node_a] = U[east.dof(ms, ia, 1)] - U[east.dof(ms, ib, 1)]
    return out


def _row(m, ms, beams, pipe_ix, frame_ix, U, i_load, fixed, info):
    _, Fint = east.assemble(m, ms, U)
    Ry = sum(Fint[d] for d in fixed if d % 3 == 1)
    _, sig = east.member_stress(m, ms, U, beams)
    conns = {c['line_id']: c for c in east.connector_forces(m, ms, U)}
    d_slots = [e.connector.slot for e in m.elements
               if e.connector is not None and e.connector.conn_type == 'D']
    f_slots = [e.connector.slot for e in m.elements
               if e.connector is not None and e.connector.conn_type == 'F']
    return {
        'd_pipe': U[east.dof(ms, i_load, 1)],
        'sumR': -Ry,
        'sig_pipe': sig[pipe_ix].max(),
        'sig_frame': sig[frame_ix].max(),
        'M_F': max(abs(conns[f'ST:connector{s}']['M_frame_end'])
                   for s in f_slots),
        'V_D': max(abs(conns[f'ST:connector{s}']['axial']) for s in d_slots),
        'sig_conn': max(c['sigma'] for c in conns.values()),
        'state': ''.join({0: '.', 1: '+', -1: '-'}[v]
                         for v in info['engaged'].values()),
        'flips': info['flips'],
        'viol': info['violation'],
    }


def main() -> int:
    m, L = east.build(system='F2D', p_gap=GAPS[0])
    ms, beams = east.kernel_mesh(m)
    pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
    frame_ix = [k for k, e in enumerate(beams) if e.owner == 'ST']
    n_conn = len([e for e in m.elements if e.connector is not None])

    print(f'ILS-EAST on F2D: {m.n_nodes} nodes, {m.n_elems} elements')
    print(f'  pipeline {len(pipe_ix)} el, frame {len(frame_ix)} el, '
          f'connectors {n_conn} el  (F2 has 2; the D pair is the difference)')
    print(f'  extent {L:.4f} m, fixed both ends, load at s = 0 on the header')
    print(f'  penalty alpha = {ALPHA:.0e} x local diagonal\n')
    for w in m.warnings:
        print(f'  build_model warning: {w}')
    print()

    print('Free separation at the outer slots, every D open '
          '(this is the threshold):')
    thresholds = {}
    for P in (20e3, 200e3):
        sep = free_separation(m, ms, P)
        thresholds[P] = sep
        txt = '  '.join(f'{k} {v*1e3:+.4f} mm' for k, v in sep.items())
        print(f'   P = {P/1e3:3.0f} kN   {txt}')
    print()

    print('== F2D, five deadband gaps, two loads ==')
    print(f'  {"P_gap_mm":>9}{"P_kN":>6}{"D":>5}{"d_pipe_mm":>12}'
          f'{"sumR_kN":>10}{"F_D_kN":>10}{"M_F_kNm":>10}{"sig_pipe":>10}'
          f'{"sig_frame":>11}{"sig_conn":>10}{"flips":>7}{"viol":>10}')
    table = {}
    for gap in GAPS:
        mg, _L = east.build(system='F2D', p_gap=gap)
        msg, beamsg = east.kernel_mesh(mg)
        for P in (20e3, 200e3):
            U, i_load, fixed, info = solve_deadband(mg, msg, P)
            r = _row(mg, msg, beamsg, pipe_ix, frame_ix, U, i_load, fixed,
                     info)
            table[(gap, P)] = (U, r, mg, msg, beamsg)
            flag = '' if max(r['sig_pipe'], r['sig_frame'],
                             r['sig_conn']) < SIG_YIELD else '  YIELD'
            print(f'  {gap*1e3:9.2f}{P/1e3:6.0f}{r["state"]:>5}'
                  f'{r["d_pipe"]*1e3:12.5f}{r["sumR"]/1e3:10.3f}'
                  f'{r["V_D"]/1e3:10.3f}{r["M_F"]/1e3:10.2f}'
                  f'{r["sig_pipe"]/1e6:10.1f}{r["sig_frame"]/1e6:11.1f}'
                  f'{r["sig_conn"]/1e6:10.1f}{r["flips"]:7d}'
                  f'{r["viol"]:10.2e}{flag}')
        print()

    print("  D column: '+'/'-' engaged and which way, '.' open.")
    print()
    _against_f2(table)
    print()
    _rigid_limit(m, ms, beams, pipe_ix, frame_ix)

    if '--plot' in sys.argv:
        _plot(table, pipe_ix, thresholds)
    return 0


def _against_f2(table):
    """The claim that has to hold EXACTLY, and the one that has to hold
    monotonically.

    The exact one needs a three-way comparison, and the middle term is the
    whole of it. F2D with every gap open comes out 3.79e-04 mm off plain F2 --
    small, but not nothing, and "close enough" is not a result. It is not the
    open D carrying load: a D connector forces a header STATION at its slot,
    so the F2D pipeline is meshed at +/-2.1675 m where F2's is not. Give plain
    F2 the same two stations and the two agree to the last digit printed.
    """
    X = 2.1674666666666664           # the outer slot, |s| = |x|
    mf2, _L = east.build(system='F2')
    msf2, bf2 = east.kernel_mesh(mf2)
    mst, _L2 = east.build(system='F2', extra_stations=(0.0, -X, X))
    msst, bst = east.kernel_mesh(mst)

    print('F2D with every D open, against F2:')
    print(f'  {"P_kN":>6}{"F2":>16}{"F2 + outer stns":>18}'
          f'{"F2D, gap open":>16}   mm')
    for P in (20e3, 200e3):
        U1, i1, _f, _v = east.solve(mf2, msf2, P)
        U2, i2, _f, _v = east.solve(mst, msst, P)
        d1 = U1[east.dof(msf2, i1, 1)] * 1e3
        d2 = U2[east.dof(msst, i2, 1)] * 1e3
        d3 = table[(max(GAPS), P)][1]['d_pipe'] * 1e3
        print(f'  {P/1e3:6.0f}{d1:16.8f}{d2:18.8f}{d3:16.8f}'
              f'   ({abs(d3-d2)*1e6:.1f} nm apart)')
    print('   An open D restrains NOTHING -- not the perpendicular, not')
    print('   sliding, not rotation -- so an F2D with no engagement is not')
    print('   "close to" F2, it is the same structure. The 3.79e-04 mm')
    print('   against plain F2 is not the D: a connector forces a header')
    print('   station at its slot, so F2D meshes the pipeline at +/-2.1675 m')
    print('   where F2 does not. Give F2 those two stations and the answers')
    print('   agree to every digit printed.')
    print()
    ds = [table[(g, 200e3)][1]['d_pipe'] * 1e3 for g in GAPS]
    print('   200 kN deflection against gap: '
          + ' -> '.join(f'{d:.4f}' for d in ds))
    mono = all(b <= a + 1e-9 for a, b in zip(ds, ds[1:]))
    print(f'   monotone decreasing: {mono}. A tighter gap engages the outer')
    print('   supports sooner, the frame spans more of the load, the pipe')
    print('   sags less -- approaching the rigid-roller limit below.')


def _rigid_limit(m, ms, beams, pipe_ix, frame_ix):
    """What the deadband is approaching as the gap closes.

    NOT F2D with F at the outer slots. A shut D ties the perpendicular and
    NOTHING else -- it is a rigid ROLLER there, free to slide and free to
    turn. `component_spec` is explicit that a zero gap is not an F: 'a zero
    gap is a FIXED connector, which is a different system, not a D that
    happens to shut immediately'. So the limit is taken from below.
    """
    print('The limit the gap sweep approaches, at 200 kN:')
    for gap in (1e-4, 1e-5, 1e-6):
        mg, _L = east.build(system='F2D', p_gap=gap)
        msg, beamsg = east.kernel_mesh(mg)
        U, i_load, _f, info = solve_deadband(mg, msg, 200e3)
        print(f'   P_gap = {gap*1e3:7.4f} mm   '
              f'd = {U[east.dof(msg, i_load, 1)]*1e3:10.5f} mm   '
              f'D {info["engaged"] and "".join({0: ".", 1: "+", -1: "-"}[v] for v in info["engaged"].values())}')
    print('   A shut D is a rigid ROLLER, not a fixed connection: it ties')
    print('   the perpendicular and nothing else. The zero-gap case is')
    print('   refused by the component itself -- a zero gap is an F, which')
    print('   is a different connection system, not a D that shuts at once.')


def _plot(table, pipe_ix, thresholds):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    outp = REPO / 'docs' / 'diagrams' / 'east_f2d_study.png'
    open_gap, shut_gap = GAPS[0], GAPS[-1]
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 11.4),
                             gridspec_kw={'height_ratios': [1, 1, 0.95]})

    common = 1.2 / max(abs(table[(g, 200e3)][0][1::3]).max()
                       for g in (open_gap, shut_gap))
    for ax, gap, note in (
            (axes[0], open_gap,
             'gap 5.00 mm -- never closes at 200 kN, so this IS F2'),
            (axes[1], shut_gap,
             'gap 0.25 mm -- both outer D engaged, the frame spans wider')):
        U, r, mg, msg, _b = table[(gap, 200e3)]
        at = {n.index: n for n in mg.nodes}
        for e in mg.elements:
            a, b = at[e.n1], at[e.n2]
            ctype = e.connector.conn_type if e.connector is not None else None
            col = {'pipeline': '#1f7a8c', 'ST': '#2f6f3e'}.get(e.owner,
                                                              '#6b4ea8')
            if ctype == 'D':
                col = '#b44d12'
            lw = 2.6 if e.connector is not None else 1.8
            ax.plot([a.s, b.s], [a.y, b.y], color='#c9d2d9', lw=1.1, zorder=1)
            xs, ys = east.deflected(a, b, U, msg, e.n1, e.n2, common)
            ax.plot(xs, ys, color=col, lw=lw,
                    ls=':' if (ctype == 'D' and '.' in r['state']) else '-',
                    zorder=2)
        ax.invert_yaxis(); ax.set_aspect('equal')
        ax.set_ylabel('y (m), down'); ax.grid(alpha=0.22)
        ax.set_title(f'F2D, {note}   '
                     f'(d = {r["d_pipe"]*1e3:.3f} mm, x{common:.0f})',
                     fontsize=9.5, loc='left')
    axes[0].legend(handles=[
        plt.Line2D([], [], color=c, lw=2.2, ls=s, label=l)
        for l, c, s in (('pipeline', '#1f7a8c', '-'),
                        ('GD-ST frame', '#2f6f3e', '-'),
                        ('F connectors', '#6b4ea8', '-'),
                        ('D connectors (dotted = open)', '#b44d12', ':'),
                        ('undeformed', '#c9d2d9', '-'))],
        fontsize=7.5, ncol=2, loc='upper right', framealpha=0.92)

    ax = axes[2]
    gaps_mm = [g * 1e3 for g in GAPS]
    # the measured threshold, which is what makes this a prediction and not a
    # curve: a gap wider than the free separation cannot close, at that load
    for P, col in ((20e3, '#1f7a8c'), (200e3, '#b44d12')):
        thr = abs(next(iter(thresholds[P].values()))) * 1e3
        ax.axvline(thr, color=col, ls=':', lw=1.4)
        ax.annotate(f'free separation\nat {P/1e3:.0f} kN: {thr:.3f} mm',
                    xy=(thr, 0.995), xycoords=('data', 'axes fraction'),
                    fontsize=7.5, color=col, ha='right', va='top',
                    rotation=90)
    for P, col in ((20e3, '#1f7a8c'), (200e3, '#b44d12')):
        d = [table[(g, P)][1]['d_pipe'] * 1e3 for g in GAPS]
        d0 = d[0]
        ax.plot(gaps_mm, [x / d0 for x in d], color=col, marker='o', lw=1.9,
                label=f'{P/1e3:.0f} kN')
        for g, x in zip(GAPS, d):
            if '.' not in table[(g, P)][1]['state']:
                ax.plot([g * 1e3], [x / d0], marker='o', ms=11, mfc='none',
                        mec=col, lw=1.4)
    ax.axhline(1.0, color='#7b8794', ls='--', lw=1.0)
    ax.set_xscale('log')
    ax.invert_xaxis()
    ax.set_xticks(gaps_mm)
    ax.set_xticklabels([f'{g:g}' for g in gaps_mm])
    ax.minorticks_off()
    ax.set_xlabel('P_gap (mm)   --   tighter to the right')
    ax.set_ylabel('deflection / its own open-gap value')
    ax.set_title('Ringed markers are gaps where BOTH D engaged. Above the '
                 'threshold the deadband changes nothing at all.',
                 fontsize=9.5, loc='left')
    ax.legend(fontsize=8); ax.grid(alpha=0.22, which='both')

    fig.suptitle('ILS-EAST on F2D: the deadband gap is the only variable.',
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(outp, dpi=140)
    print(f'wrote {outp.relative_to(REPO)}')


if __name__ == '__main__':
    raise SystemExit(main())

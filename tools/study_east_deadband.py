#!/usr/bin/env python3
"""study_east_deadband.py -- ILS-EAST on F2D and F1D: what the gap does.

These are the two named systems with deadbands, and the first whose GEOMETRY
differs rather than only their ties. F2 and PS populate the same two slots, so
PS was a tie override on an F2 model; these have to be built.

    slot    1     2     3     4     5        connectors
    F1     ---   ---    F    ---   ---           1
    F2     ---    F    ---    F    ---           2
    F1D     D    ---    F    ---    D            3
    F2D     D     F    ---    F     D            4

A `D` is a pure support: it restrains the perpendicular translation and
NOTHING else -- not sliding, not rotation -- and only once the two sides have
moved P_gap apart. Open, it restrains nothing at all, so each system with
every gap open must BE its base system, not resemble it.

WHY BOTH, AND WHY THEY ARE NOT THE SAME EXPERIMENT. Their bases differ in kind,
so the deadband has a different job in each:

  F2 holds the frame at two points and carries moment across the span between
  them, so F2D's outer supports EXTEND a frame that is already working.

  F1 holds it at one point. At the midspan of a symmetric fixed-fixed beam the
  rotation is zero, so an F tied there transmits no moment and the frame is a
  PASSENGER -- F1 leaves the pipe at its bare-beam deflection, the same result
  PS gives for a different reason. F1D's outer supports are therefore the only
  thing that makes the frame carry anything at all, and the step when they
  close is correspondingly larger.

WHAT THE GAP IS. `P_gap` is GD-ST's own parameter and it has NO DEFAULT, on
purpose: a deadband REDISTRIBUTES strain rather than removing it, and the gap
decides where the strain goes. So it is carried on the component, flows
through `ils.connectors_of` into `Association.gap`, and is read back off the
association at solve time. It is component data, never a solver knob. (Nothing
upstream enforces that it is set -- raised as CUN-001 against
`Slay-ILS-Designer-V1.0`, still open -- so every consumer checks it here.)

THE MEASUREMENT THAT COMES FIRST. With every D open the outer slots move a
definite distance, and that distance is the threshold: a gap wider than it
cannot close, a narrower one must. Measured here:

    F2D   0.3002 mm at 20 kN    3.0041 mm at 200 kN
    F1D   0.9220 mm at 20 kN    9.1049 mm at 200 kN

three times as far on F1D, because nothing holds the frame down at the inner
slots. Each system's five gaps straddle its OWN threshold; the sweep is then a
prediction to check rather than a curve to describe.

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

    python3 tools/study_east_deadband.py [--plot]
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
from study_connectors import ALPHA, ZERO_LEN_TOL           # noqa: E402

SIG_YIELD = east.SIG_YIELD

# Each system's five gaps straddle ITS OWN measured free separation at
# 200 kN -- 3.004 mm on F2D, 9.105 mm on F1D. Two above, three below, with
# the middle pair bracketing the threshold as tightly as the sweep can
# without landing on it, which is where a deadband is worth watching. A
# shared gap set would put both sweeps on one side of one of the thresholds
# and measure nothing there.
SYSTEMS = {
    'F2D': {'base': 'F2', 'slots': (1, 2, 4, 5),
            'gaps': {'ILS-EAST': (5.0e-3, 3.5e-3, 2.5e-3, 1.0e-3, 0.25e-3),
                     'ILS-EASB': (6.0e-3, 4.5e-3, 3.0e-3, 1.2e-3, 0.30e-3)}},
    'F1D': {'base': 'F1', 'slots': (1, 3, 5),
            'gaps': {'ILS-EAST': (15.0e-3, 10.0e-3, 7.5e-3, 3.0e-3, 0.75e-3),
                     'ILS-EASB': (16.0e-3, 12.0e-3, 8.0e-3, 3.5e-3, 0.80e-3)}},
}

# ILS-EASB's frame is longer and hangs BELOW the pipe from a top chord on the
# centreline, so its outer slots travel further before they touch: 9.975 mm
# against ILS-EAST's 9.105 on F1D, 3.667 against 3.004 on F2D. Same shape,
# different numbers, and each archetype is swept against its own.
DEFAULT_ARCHETYPE = 'ILS-EAST'


def gaps_for(name: str, archetype: str = DEFAULT_ARCHETYPE):
    return SYSTEMS[name]['gaps'][archetype]

# The outer slot, |s| = |x|. Both systems put a D there, and both therefore
# force a header station there that their base system does not have.
X_OUTER = 2.1674666666666664

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
    # Keyed by the ELEMENT's own line_id, never by a reconstructed
    # 'ST:connector<n>'. The owner tag is 'ST' on ILS-EAST and 'SB' on
    # ILS-EASB, so a rebuilt string works on one archetype and raises a
    # KeyError on the other.
    by_type = {'F': [], 'D': []}
    for e in m.elements:
        if e.connector is not None:
            by_type[e.connector.conn_type].append(conns[e.line_id])
    return {
        'd_pipe': U[east.dof(ms, i_load, 1)],
        'sumR': -Ry,
        'sig_pipe': sig[pipe_ix].max(),
        'sig_frame': sig[frame_ix].max(),
        'M_F': max(abs(c['M_frame_end']) for c in by_type['F']),
        # axial in BOTH classes. Without the F column an F1D table reads as
        # all zeros in every connector column -- its single F sits at the
        # midspan, where symmetry gives zero relative rotation and so zero
        # moment, and a table showing only moment cannot tell that apart
        # from a connector doing nothing at all.
        'N_F': max(abs(c['axial']) for c in by_type['F']),
        'N_D': max(abs(c['axial']) for c in by_type['D']),
        'sig_conn': max(c['sigma'] for c in conns.values()),
        'state': ''.join({0: '.', 1: '+', -1: '-'}[v]
                         for v in info['engaged'].values()),
        'flips': info['flips'],
        'viol': info['violation'],
    }


def sweep(name: str, archetype: str = DEFAULT_ARCHETYPE):
    """Every gap of one system, both loads. Each gap is a REBUILD, because
    P_gap is component data and rides on the component, not on the solver."""
    out = {}
    for gap in gaps_for(name, archetype):
        m, _L = east.build(system=name, p_gap=gap, archetype=archetype)
        ms, beams = east.kernel_mesh(m)
        ea = east.ea_owner(m)
        pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
        frame_ix = [k for k, e in enumerate(beams) if e.owner == ea]
        for P in (20e3, 200e3):
            U, i_load, fixed, info = solve_deadband(m, ms, P)
            r = _row(m, ms, beams, pipe_ix, frame_ix, U, i_load, fixed, info)
            out[(gap, P)] = (U, r, m, ms, beams)
    return out


def main() -> int:
    archetype = DEFAULT_ARCHETYPE
    if '--archetype' in sys.argv:
        archetype = sys.argv[sys.argv.index('--archetype') + 1]
    tables, thresholds = {}, {}
    for name in ('F2D', 'F1D'):
        tables[name], thresholds[name] = _one_system(name, archetype)

    print()
    _compare_systems(tables, thresholds, archetype)

    if '--plot' in sys.argv:
        _plot(tables, thresholds, archetype)
    return 0


def _one_system(name: str, archetype: str = DEFAULT_ARCHETYPE):
    gaps = gaps_for(name, archetype)
    m, L = east.build(system=name, p_gap=gaps[0], archetype=archetype)
    ms, beams = east.kernel_mesh(m)
    pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
    ea = east.ea_owner(m)
    frame_ix = [k for k, e in enumerate(beams) if e.owner == ea]
    conns = sorted((e for e in m.elements if e.connector is not None),
                   key=lambda e: e.connector.slot)
    layout = ' '.join(f'{e.connector.conn_type}@{e.connector.slot}'
                      for e in conns)

    print(f'=========  {archetype} on {name}  =========')
    print(f'  {m.n_nodes} nodes, {m.n_elems} elements, '
          f'{len(conns)} connectors: {layout}')
    print(f'  pipeline {len(pipe_ix)} el, frame {len(frame_ix)} el, '
          f'{len(m.associations)} associations')
    print(f'  extent {L:.4f} m, fixed both ends, load at s = 0 on the header')
    print(f'  penalty alpha = {ALPHA:.0e} x local diagonal')
    for w in m.warnings:
        print(f'  build_model warning: {w}')
    print()

    print('Free separation at the outer slots, every D open '
          '(this is the threshold):')
    thr = {}
    for P in (20e3, 200e3):
        sep = free_separation(m, ms, P)
        thr[P] = sep
        txt = '  '.join(f'{k} {v*1e3:+.4f} mm' for k, v in sep.items())
        print(f'   P = {P/1e3:3.0f} kN   {txt}')
    print()

    print(f'== {name}, five deadband gaps, two loads ==')
    print(f'  {"P_gap_mm":>9}{"P_kN":>6}{"D":>5}{"d_pipe_mm":>12}'
          f'{"sumR_kN":>10}{"N_D_kN":>9}{"N_F_kN":>9}{"M_F_kNm":>10}'
          f'{"sig_pipe":>10}'
          f'{"sig_frame":>11}{"sig_conn":>10}{"flips":>7}{"viol":>10}')
    table = sweep(name, archetype)
    for gap in gaps:
        for P in (20e3, 200e3):
            r = table[(gap, P)][1]
            flag = '' if max(r['sig_pipe'], r['sig_frame'],
                             r['sig_conn']) < SIG_YIELD else '  YIELD'
            print(f'  {gap*1e3:9.2f}{P/1e3:6.0f}{r["state"]:>5}'
                  f'{r["d_pipe"]*1e3:12.5f}{r["sumR"]/1e3:10.3f}'
                  f'{r["N_D"]/1e3:9.3f}{r["N_F"]/1e3:9.3f}'
                  f'{r["M_F"]/1e3:10.2f}'
                  f'{r["sig_pipe"]/1e6:10.1f}{r["sig_frame"]/1e6:11.1f}'
                  f'{r["sig_conn"]/1e6:10.1f}{r["flips"]:7d}'
                  f'{r["viol"]:10.2e}{flag}')
        print()
    print("  D column: '+'/'-' engaged and which way, '.' open.")
    print()
    _against_base(name, table, archetype)
    print()
    _rigid_limit(name, archetype)
    print()
    return table, thr


def _against_base(name: str, table, archetype=DEFAULT_ARCHETYPE):
    """The claim that has to hold EXACTLY, and the one that has to hold
    monotonically.

    The exact one needs a three-way comparison, and the middle term is the
    whole of it. A system with every gap open comes out a few 1e-04 mm off its
    base -- small, but not nothing, and "close enough" is not a result. It is
    not the open D carrying load: a D connector forces a header STATION at its
    slot, so the D system's pipeline is meshed at +/-2.1675 m where the base
    system's is not. Give the base those two stations and the two agree to the
    last digit printed.
    """
    base = SYSTEMS[name]['base']
    mb, _L = east.build(system=base, archetype=archetype)
    msb, _bb = east.kernel_mesh(mb)
    mst, _L2 = east.build(system=base, archetype=archetype,
                          extra_stations=(0.0, -X_OUTER, X_OUTER))
    msst, _bs = east.kernel_mesh(mst)

    print(f'{name} with every D open, against {base}:')
    print(f'  {"P_kN":>6}{base:>16}{base + " + outer stns":>20}'
          f'{name + ", gap open":>18}   mm')
    for P in (20e3, 200e3):
        U1, i1, _f, _v = east.solve(mb, msb, P)
        U2, i2, _f, _v = east.solve(mst, msst, P)
        d1 = U1[east.dof(msb, i1, 1)] * 1e3
        d2 = U2[east.dof(msst, i2, 1)] * 1e3
        d3 = table[(max(gaps_for(name, archetype)), P)][1]['d_pipe'] * 1e3
        print(f'  {P/1e3:6.0f}{d1:16.8f}{d2:20.8f}{d3:18.8f}'
              f'   ({abs(d3-d2)*1e6:.1f} nm apart)')
    print('   An open D restrains NOTHING -- not the perpendicular, not')
    print(f'   sliding, not rotation -- so {name} with no engagement is not')
    print(f'   "close to" {base}, it is the same structure. The residual')
    print(f'   against plain {base} is not the D: a connector forces a header')
    print('   station at its slot, so the D system meshes the pipeline at')
    print(f'   +/-2.1675 m where {base} does not. Give {base} those two')
    print('   stations and the answers agree to every digit printed.')
    print()
    ds = [table[(g, 200e3)][1]['d_pipe'] * 1e3
          for g in gaps_for(name, archetype)]
    print('   200 kN deflection against gap: '
          + ' -> '.join(f'{d:.4f}' for d in ds))
    mono = all(b <= a + 1e-9 for a, b in zip(ds, ds[1:]))
    print(f'   monotone decreasing: {mono}, {(1 - ds[-1]/ds[0])*100:.1f}% '
          f'from the open end to the tightest gap.')


def _rigid_limit(name: str, archetype=DEFAULT_ARCHETYPE):
    """What the deadband is approaching as the gap closes.

    NOT the same system with F at the outer slots. A shut D ties the
    perpendicular and NOTHING else -- it is a rigid ROLLER there, free to
    slide and free to turn. `component_spec` is explicit that a zero gap is
    not an F: "a zero gap is a FIXED connector, which is a different system,
    not a D that happens to shut immediately". So the limit is taken from
    below.
    """
    print(f'The limit {name} approaches as the gap closes, at 200 kN:')
    for gap in (1e-4, 1e-5, 1e-6):
        mg, _L = east.build(system=name, p_gap=gap, archetype=archetype)
        msg, _bg = east.kernel_mesh(mg)
        U, i_load, _f, info = solve_deadband(mg, msg, 200e3)
        state = ''.join({0: '.', 1: '+', -1: '-'}[v]
                        for v in info['engaged'].values())
        print(f'   P_gap = {gap*1e3:7.4f} mm   '
              f'd = {U[east.dof(msg, i_load, 1)]*1e3:10.5f} mm   D {state}')
    print('   A shut D is a rigid ROLLER, not a fixed connection: it ties')
    print('   the perpendicular and nothing else. The zero-gap case is')
    print('   refused by the component itself -- a zero gap is an F, which')
    print('   is a different connection system, not a D that shuts at once.')


def _compare_systems(tables, thresholds, archetype=DEFAULT_ARCHETYPE):
    """F1D against F2D. Same frame, same connectors, same gap rule -- the
    only difference is how much work the BASE system was already doing."""
    print(f'=========  F1D against F2D on {archetype}  =========')
    print()
    print('At 200 kN, each system open and at its tightest gap:')
    print(f'  {"system":8}{"base":6}{"conns":7}{"open_mm":>10}'
          f'{"tight_mm":>10}{"drop":>8}{"threshold_mm":>14}')
    for name in ('F2D', 'F1D'):
        gaps = gaps_for(name, archetype)
        t = tables[name]
        d_open = t[(gaps[0], 200e3)][1]['d_pipe'] * 1e3
        d_tight = t[(gaps[-1], 200e3)][1]['d_pipe'] * 1e3
        thr = abs(next(iter(thresholds[name][200e3].values()))) * 1e3
        print(f'  {name:8}{SYSTEMS[name]["base"]:6}'
              f'{len(SYSTEMS[name]["slots"]):<7}{d_open:10.4f}{d_tight:10.4f}'
              f'{(1-d_tight/d_open)*100:7.1f}%{thr:14.4f}')
    print()
    print('  F1 is a PASSENGER and F2 is not, which is the whole difference.')
    print('  At the midspan of a symmetric fixed-fixed beam the rotation is')
    print('  zero, so an F tied there transmits no moment: F1 leaves the pipe')
    print('  at its bare-beam deflection. F2 holds the frame at two points and')
    print('  carries moment across the span between them, so it already')
    print('  shields the pipe before any deadband closes.')
    print()
    print('  So F1D starts softer, its frame has to travel three times as far')
    print('  before the outer supports touch, and when they do they are the')
    print('  ONLY thing making the frame work -- a bigger step from a worse')
    print('  starting point. F2D starts stiffer and gains less.')
    print()
    print('  Where they end up is the test of that reading:')
    for name in ('F2D', 'F1D'):
        gaps = gaps_for(name, archetype)
        d = tables[name][(gaps[-1], 200e3)][1]['d_pipe'] * 1e3
        print(f'    {name} at {gaps[-1]*1e3:.2f} mm gap -> {d:.4f} mm')


def _plot(tables, thresholds, archetype=DEFAULT_ARCHETYPE):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    tag = 'east' if archetype == 'ILS-EAST' else 'easb'
    outp = REPO / 'docs' / 'diagrams' / f'{tag}_deadband_study.png'
    fig, axes = plt.subplots(3, 2, figsize=(14.0, 11.8),
                             gridspec_kw={'height_ratios': [1, 1, 1.25]})

    # ONE magnification across all four shape panels. Per-panel scaling would
    # make the softest layout look like the stiffest, which is the comparison.
    common = 1.6 / max(
        abs(tables[n][(g, 200e3)][0][1::3]).max()
        for n in ('F2D', 'F1D')
        for g in (gaps_for(n, archetype)[0], gaps_for(n, archetype)[-1]))

    for col, name in enumerate(('F2D', 'F1D')):
        gaps = gaps_for(name, archetype)
        for row, gap in enumerate((gaps[0], gaps[-1])):
            ax = axes[row][col]
            U, r, mg, msg, _b = tables[name][(gap, 200e3)]
            at = {n.index: n for n in mg.nodes}
            for e in mg.elements:
                a, b = at[e.n1], at[e.n2]
                ctype = (e.connector.conn_type
                         if e.connector is not None else None)
                col_ = {'pipeline': '#1f7a8c'}.get(
                    e.owner, '#2f6f3e' if e.connector is None else '#6b4ea8')
                if ctype == 'D':
                    col_ = '#b44d12'
                if (e.connector is not None
                        and math.hypot(b.s - a.s, b.y - a.y) < ZERO_LEN_TOL):
                    # ILS-EASB's connectors have no length, so there is no
                    # chord to draw and `deflected` would divide by it. Mark
                    # where the connector is rather than invent extent for it.
                    ax.plot([a.s + U[east.dof(msg, e.n1, 0)] * common],
                            [a.y + U[east.dof(msg, e.n1, 1)] * common],
                            marker='D', ms=7,
                            mfc='none' if (ctype == 'D'
                                           and '.' in r['state']) else col_,
                            mec=col_, zorder=4)
                    continue
                ax.plot([a.s, b.s], [a.y, b.y], color='#c9d2d9', lw=1.0,
                        zorder=1)
                xs, ys = east.deflected(a, b, U, msg, e.n1, e.n2, common)
                ax.plot(xs, ys, color=col_,
                        lw=2.6 if e.connector is not None else 1.7,
                        ls=':' if (ctype == 'D' and '.' in r['state']) else '-',
                        zorder=2)
            # ZOOMED TO THE ILS. The pipe runs to +/-9.25 m and the tails
            # carry no connector, so an equal-aspect panel over the whole
            # span spends nine tenths of its width on the part with nothing
            # to see -- and squashes the frame, the connectors and the
            # engaged/open distinction into a few pixels.
            ax.set_xlim(-4.2, 4.2)
            ax.invert_yaxis(); ax.set_aspect('equal'); ax.grid(alpha=0.22)
            ax.set_xlabel('s (m)', fontsize=8)
            if col == 0:
                ax.set_ylabel('y (m), down')
            state = 'all D open -- this IS ' + SYSTEMS[name]['base'] \
                if '.' in r['state'] else 'both outer D engaged'
            ax.set_title(f'{name}, gap {gap*1e3:.2f} mm -- {state}\n'
                         f'd = {r["d_pipe"]*1e3:.3f} mm   (x{common:.0f})',
                         fontsize=9, loc='left')
    axes[0][0].legend(handles=[
        plt.Line2D([], [], color=c, lw=2.2, ls=st, label=l)
        for l, c, st in (('pipeline', '#1f7a8c', '-'),
                         (f'GD-{"ST" if archetype == "ILS-EAST" else "SB"} '
                          f'frame', '#2f6f3e', '-'),
                         ('F connectors', '#6b4ea8', '-'),
                         ('D (dotted = open)', '#b44d12', ':'),
                         ('undeformed', '#c9d2d9', '-'))],
        fontsize=7, ncol=2, loc='lower left', framealpha=0.92)

    gs = axes[2][0].get_gridspec()
    for a in axes[2]:
        a.remove()
    ax = fig.add_subplot(gs[2, :])
    style = {('F2D', 20e3): ('#1f7a8c', '--'), ('F2D', 200e3): ('#b44d12', '-'),
             ('F1D', 20e3): ('#4c8c2b', '--'), ('F1D', 200e3): ('#7a4bb8', '-')}
    for name in ('F2D', 'F1D'):
        gaps = gaps_for(name, archetype)
        for P in (20e3, 200e3):
            col_, ls = style[(name, P)]
            d = [tables[name][(g, P)][1]['d_pipe'] * 1e3 for g in gaps]
            x = [g * 1e3 / (abs(next(iter(thresholds[name][P].values())))
                            * 1e3) for g in gaps]
            ax.plot(x, [v / d[0] for v in d], color=col_, ls=ls, marker='o',
                    lw=1.9, label=f'{name}, {P/1e3:.0f} kN')
            for xi, v, g in zip(x, d, gaps):
                if '.' not in tables[name][(g, P)][1]['state']:
                    ax.plot([xi], [v / d[0]], marker='o', ms=11, mfc='none',
                            mec=col_, lw=1.4)
    ax.axvline(1.0, color='#7b8794', ls=':', lw=1.6)
    ax.annotate('gap = the measured free separation',
                xy=(1.0, 0.04), xycoords=('data', 'axes fraction'),
                xytext=(-6, 0), textcoords='offset points',
                fontsize=8.5, color='#57606a', ha='right', va='bottom')
    ax.axhline(1.0, color='#7b8794', ls='--', lw=1.0)
    ax.set_xscale('log'); ax.invert_xaxis()
    ax.set_xlabel('P_gap / that case\'s own free separation   '
                  '--   tighter to the right')
    ax.set_ylabel('deflection / its own open-gap value')
    ax.set_title('Every curve breaks away from 1.00 at the same place, '
                 'because the threshold is what decides engagement. Ringed '
                 'markers are gaps where both D engaged.',
                 fontsize=9.5, loc='left')
    ax.legend(fontsize=8, ncol=2); ax.grid(alpha=0.22, which='both')

    fig.suptitle(f'{archetype} on F2D and F1D: the deadband gap is the only '
                 'variable, and each system is swept against its own '
                 'threshold.', fontsize=11)
    fig.tight_layout()
    fig.savefig(outp, dpi=140)
    print(f'\nwrote {outp.relative_to(REPO)}')


if __name__ == '__main__':
    raise SystemExit(main())

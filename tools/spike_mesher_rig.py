#!/usr/bin/env python3
"""spike_mesher_rig.py -- the measuring instrument behind the mesher test plan.

Every number in `docs/modules/T3_mesher_test_plan.md` came out of this file.
It is committed so the plan can be re-measured rather than believed, which is
G8 applied to a planning document: a document that asserts 2.95e-05 without a
way to reproduce it is no better than one that asserts "small".

THIS IS A SPIKE, NOT A MODULE. It lives in tools/ and imports across layer
boundaries freely -- model, solve and the mirrored L2 builder all at once --
which `tools/check_layers.py` permits here and would reject inside
`rebuild/slay/`. It builds the header polyline and the nlfea Model BY HAND
because T3 does not exist yet; the moment `build_model()` lands, the tests
are written against that and this file is deleted.

What it measures, in order:

  1. Group A meshes (element counts, lengths, grading ratio)
  2. deflection against the fixed-fixed closed form at 20 kN and 200 kN
  3. mesh invariance -- SH vs SHTP, refinement, translation, node ordering
  4. solver tolerance: the reachable plateau, and the silent stall past it
  5. the coincident-node probe -- the kernel merge that amends G6
  6. fibre-integration error vs analytic I, by fibre count

    python3 tools/spike_mesher_rig.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))

import ils_builder                                            # noqa: E402
import nlfea_v4 as fe                                         # noqa: E402
from slay.model.mesh import (Polyline, Station, NodeReason,   # noqa: E402
                             mesh_line, polyline_of, stations_of)

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'

PAD = 6.0                 # m of plain pipe beyond EACH end of the component
OD, T_WALL = 0.4064, 0.021
E = 2.1e11
# NOT the solver default of 5e-4, which is under-converged, and NOT tighter
# than 1e-7, which the kernel cannot always reach: on an unreachable tolerance
# solve_step halves the increment and retries forever with no error raised.
# 1e-5..1e-7 is a flat plateau giving identical answers in 0.03 s. See the
# plan, section 8.
TOL = 1e-6
N_INC = 20

I_AN = math.pi * (OD**4 - (OD - 2*T_WALL)**4) / 64
A_AN = math.pi * (OD**2 - (OD - 2*T_WALL)**2) / 4
EI = E * I_AN
R_GYR = math.sqrt(I_AN / A_AN)

GROUP_A = ('ILS-TP', 'ILS-TT', 'ILS-SH', 'ILS-SHTP')

# `Station` demands a reason and none of SECTION/SLOPE/JUNCTION/MASS/EXTENT
# means "a load acts here" -- finding 4 in the plan. EXTENT is the least
# wrong of the five and is used under protest.
RIG_REASON = NodeReason.EXTENT


def archetypes() -> dict:
    return {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}


# ---------------------------------------------------------------------------
# the rig
# ---------------------------------------------------------------------------

def build_mesh(arch_id: str, target_len: float = 2 * OD):
    """The header line for one archetype, meshed. Returns (mesh, L, a_load).

    `a_load` is the arc position of the load: the ILS-local origin x = 0,
    which is the assembly's own datum. For the six archetypes with symmetric
    extents that is also the midspan; ILS-ILT is asymmetric and the two
    readings differ (question 2 in the plan).
    """
    ils = ils_builder.build_ils(archetypes()[arch_id]['definition'])
    lo, hi = ils.extent
    x0, x1 = lo - PAD, hi + PAD
    L = x1 - x0

    pl = Polyline('pipeline', ['LO', 'HI'], [x0, x1], [0.0, 0.0], [0.0, L])
    stations = [Station(0.0, True, RIG_REASON, 'rig', 'END_LO'),
                Station(L,   True, RIG_REASON, 'rig', 'END_HI'),
                Station(-x0, True, RIG_REASON, 'rig', 'LOAD')]

    for c in ils.components:
        if not [s for s in c.structural_lines() if s.line_id == 'pipeline']:
            continue                       # GD-SH and the EA frames: no line
        cpl = polyline_of(c, 'pipeline')
        for s in stations_of(c, cpl):
            stations.append(Station(cpl.at(s.arc_len)[0] - x0, s.mandatory,
                                    s.reason, s.owner, s.node_id))

    return mesh_line(pl, stations, target_len), L, -x0


def solve_arcs(arcs, a_load, P, tol=TOL, n_inc=N_INC) -> float:
    """Assemble and solve. Returns the deflection at the load point.

    Elastic `Material`, not a J2 one: for inelastic elements the kernel
    integrates the section over fibres, and that quadrature is 0.4% off the
    analytic I at 20 fibres and 6.6% off at 30 (measured below). A stiffness
    error of that size in a mesher test is indistinguishable from a lost
    station.
    """
    mdl = fe.Model(
        nodes=[fe.Node(i, x, 0.0) for i, x in enumerate(arcs)],
        elements=[fe.UserElement(i, i, i + 1, 1, 1, seed=1)
                  for i in range(len(arcs) - 1)],
        sections=[fe.PipeSection(1, OD, T_WALL)],
        materials=[fe.Material(1, E)])
    ms = fe.MeshedStructure(mdl)

    # The plan's operational reading of "must not merge or edit nodes".
    assert ms.n_nodes == len(arcs), f'kernel merged: {ms.n_nodes}/{len(arcs)}'
    assert set(ms.user_node_to_mesh.values()) == set(range(ms.n_nodes))

    i_load = min(range(len(arcs)), key=lambda k: abs(arcs[k] - a_load))
    assert abs(arcs[i_load] - a_load) < 1e-9, 'no node at the load point'

    bc = [3 * ms.user_node_to_mesh[n] + k
          for n in (0, len(arcs) - 1) for k in (0, 1, 2)]
    U, _, _ = fe.solve_step(ms, np.zeros(ms.n_dofs),
                            {'joint_init': [fe.JointLoad(1, i_load, 0.0, P, 0.0)]},
                            bc, [0.0] * len(bc),
                            n_increments=n_inc, tol=tol, max_iter=60)
    return U[3 * ms.user_node_to_mesh[i_load] + 1]


def run(arch_id, P, tol=TOL, n_inc=N_INC, target_len=2 * OD):
    m, L, a = build_mesh(arch_id, target_len)
    return solve_arcs([n.arc_len for n in m.nodes], a, P, tol, n_inc), m, L, a


def closed_form(P, L, a):
    """Fixed-fixed, point load at `a`. (delta, M_lo, M_hi, M_load)."""
    b = L - a
    return (P * a**3 * b**3 / (3 * EI * L**3),
            P * a * b**2 / L**2,
            P * a**2 * b / L**2,
            2 * P * a**2 * b**2 / L**3)


def membrane_estimate(P, L, a):
    """Rayleigh estimate of the axially-restrained response, P = kd(1+d^2/16r^2)."""
    d0 = closed_form(P, L, a)[0]
    k, d = P / d0, d0
    for _ in range(60):
        d -= (k*d*(1 + d*d/(16*R_GYR**2)) - P) / (k*(1 + 3*d*d/(16*R_GYR**2)))
    return d


# ---------------------------------------------------------------------------
# measurements
# ---------------------------------------------------------------------------

def section_meshes():
    print('\n== 1. Group A meshes at 2 x OD ==')
    print(f'{"archetype":10}{"L":>9}{"a":>9}{"nodes":>7}{"elems":>7}'
          f'{"len_min":>9}{"len_max":>9}{"ratio":>8}{"warn":>6}')
    for aid in GROUP_A:
        m, L, a = build_mesh(aid)
        print(f'{aid:10}{L:9.3f}{a:9.3f}{len(m.nodes):7d}{m.n_elems:7d}'
              f'{min(m.lengths):9.4f}{max(m.lengths):9.4f}'
              f'{m.max_adjacent_ratio:8.3f}{len(m.warnings):6d}')


def section_closed_form():
    print('\n== 2. deflection vs the fixed-fixed closed form ==')
    for P in (20e3, 200e3):
        print(f'  -- P = {P/1e3:.0f} kN')
        print(f'    {"archetype":10}{"d_FE_mm":>12}{"d_linear_mm":>13}'
              f'{"diff%":>9}{"predicted%":>12}{"M_max_kNm":>11}{"sig_MPa":>9}')
        for aid in GROUP_A:
            d_fe, m, L, a = run(aid, P)
            d_lin, m_lo, m_hi, m_ld = closed_form(P, L, a)
            pred = 100 * (membrane_estimate(P, L, a) / d_lin - 1)
            m_max = max(m_lo, m_hi, m_ld)
            print(f'    {aid:10}{d_fe*1e3:12.5f}{d_lin*1e3:13.5f}'
                  f'{100*(d_fe/d_lin-1):9.3f}{pred:12.3f}'
                  f'{m_max/1e3:11.1f}{m_max*(OD/2)/I_AN/1e6:9.1f}')


def section_invariance():
    print('\n== 3. mesh invariance ==')
    for P in (20e3, 200e3):
        d1, m1, _, _ = run('ILS-SH', P)
        d2, m2, _, _ = run('ILS-SHTP', P)
        print(f'  SH({m1.n_elems} el) vs SHTP({m2.n_elems} el) at {P/1e3:5.0f} kN: '
              f'{d1*1e3:.9f} / {d2*1e3:.9f} mm   rel {abs(d1/d2-1):.2e}')

    print('  refinement, ILS-SH:')
    for k in (4.0, 2.0, 1.0, 0.5, 0.25):
        for P in (20e3, 200e3):
            d_fe, m, L, a = run('ILS-SH', P, target_len=k * OD)
            print(f'    {k:5.2f} x OD  {m.n_elems:4d} el  P={P/1e3:5.0f} kN  '
                  f'{d_fe*1e3:13.8f} mm  vs closed form '
                  f'{100*(d_fe/closed_form(P, L, a)[0]-1):+8.4f}%')

    m, L, a = build_mesh('ILS-SH')
    arcs = [n.arc_len for n in m.nodes]
    print('  rigid translation and node-order reversal, ILS-SH:')
    for P in (20e3, 200e3):
        base = solve_arcs(arcs, a, P)
        for shift in (50.0, -50.0, 500.0):
            v = solve_arcs([x + shift for x in arcs], a + shift, P)
            print(f'    P={P/1e3:5.0f} kN  shift {shift:+7.1f} m   '
                  f'rel {abs(v/base-1):.2e}')
        rev = solve_arcs(list(reversed(arcs)), a, P)
        print(f'    P={P/1e3:5.0f} kN  order reversed     '
              f'rel {abs(rev/base-1):.2e}')


def section_tolerance():
    print('\n== 4. solver tolerance: noise vs real mesh sensitivity ==')
    print('  SH vs SHTP at 200 kN -- does the difference move with tol?')
    for tol in (5e-4, 1e-5, 1e-6, 1e-7):
        d1 = run('ILS-SH', 200e3, tol=tol)[0]
        d2 = run('ILS-SHTP', 200e3, tol=tol)[0]
        print(f'    tol={tol:8.0e}  {d1*1e3:.9f} / {d2*1e3:.9f}  '
              f'rel {abs(d1/d2-1):.2e}')
    print('  the reachable plateau, ILS-SH at 1 x OD (44 elements):')
    for P in (20e3, 200e3):
        for tol in (5e-4, 1e-5, 1e-6, 1e-7):
            t0 = time.time()
            d = run('ILS-SH', P, tol=tol, target_len=1.0 * OD)[0]
            print(f'    P={P/1e3:5.0f} kN  tol={tol:8.0e}  {d*1e3:13.8f} mm  '
                  f'{time.time()-t0:6.2f} s')
    print('    tol=1e-8 is NOT probed here: on the 44- and 90-element meshes it')
    print('    is unreachable, and solve_step then halves the increment and')
    print('    retries without bound -- 90 elements did not finish in 15 min.')
    print('  increment spread, ILS-SH at 200 kN:')
    for tol in (5e-4, TOL):
        v = [run('ILS-SH', 200e3, tol=tol, n_inc=k)[0] for k in (5, 20, 80)]
        print(f'    tol={tol:8.0e}  ' + ' '.join(f'{x*1e3:.8f}' for x in v)
              + f'   spread {max(v)/min(v)-1:.2e}')


def section_merge_probe():
    print('\n== 5. coincident-node probe -- the kernel merge (G6) ==')
    mdl = fe.Model(
        nodes=[fe.Node(0, 0.0, 0.0), fe.Node(1, 1.0, 0.0),
               fe.Node(2, 1.0, 0.0), fe.Node(3, 2.0, 0.0)],
        elements=[fe.UserElement(0, 0, 1, 1, 1), fe.UserElement(1, 2, 3, 1, 1)],
        sections=[fe.PipeSection(1, OD, T_WALL)], materials=[fe.Material(1, E)])
    ms = fe.MeshedStructure(mdl)
    print(f'    declared 4 nodes, two bars merely touching -> '
          f'{ms.n_nodes} mesh nodes')
    print(f'    user_node_to_mesh = {ms.user_node_to_mesh}')
    print('    -> MERGED' if ms.n_nodes < 4 else '    -> kept separate')


def section_fibres():
    print('\n== 6. fibre integration vs analytic I ==')
    print(f'    {"n_fibres":>9}{"A error":>12}{"I error":>12}')
    for nf in (20, 30, 40, 60, 100):
        y, a_f = fe.PipeSection(1, OD, T_WALL, n_fibres=nf).fibre_geometry()
        print(f'    {nf:9d}{100*(a_f.sum()/A_AN-1):+11.3f}%'
              f'{100*((a_f*y**2).sum()/I_AN-1):+11.3f}%')


def main() -> int:
    print(f'pipe OD {OD} m, t {T_WALL} m, E {E:.3e} Pa')
    print(f'I = {I_AN:.6e} m^4   A = {A_AN:.6f} m^2   EI = {EI:.6e} N.m^2   '
          f'r_gyr = {R_GYR:.5f} m')
    print(f'solver: tol = {TOL:.0e}, n_increments = {N_INC} '
          f'(NOT the defaults -- see the plan, section 8)')
    section_meshes()
    section_closed_form()
    section_invariance()
    section_tolerance()
    section_merge_probe()
    section_fibres()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

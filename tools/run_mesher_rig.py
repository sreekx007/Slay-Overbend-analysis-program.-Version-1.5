#!/usr/bin/env python3
"""run_mesher_rig.py -- the mesher test rig, run through build_model.

`docs/modules/T3_mesher_test_plan.md`, executed against the real assembly
rather than the hand-built spike. The spike proved the rig was buildable
before T3 existed; this proves T3 builds it.

THE RIG (ruled 13 Sep 2026):
  * each archetype centred, with 6 m of plain pipe beyond EACH component end
  * the PIPELINE section applied to every element -- which is what makes the
    beam prismatic, so the closed form is exact and anything the mesher does
    must be invisible in the result
  * both ends fixed, all three DOF
  * a point load at the component body centre: 20 kN (analytical regime) and
    200 kN (the specified rig)
  * peak stress and strain plotted per component

WHY A RIG SCENE. The lay Scene spans 88 m between rollers; this needs a bare
beam of `span + 12 m` with no forced-elastic zones. Both are Scenes -- extent
plus zone boundaries is the whole of what the model layer reads -- so the rig
builds one directly rather than bending `build_scene` into a shape it does
not mean.

SOLVER SETTINGS ARE PART OF THE FIXTURE. tol = 1e-6, never the default 5e-4
(under-converged) and never tighter than 1e-7 (unreachable -- solve_step then
halves the increment and retries without bound, raising nothing).

    python3 tools/run_mesher_rig.py [--plot]
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

PAD = 6.0
OD, T_WALL = 0.4064, 0.021
E = 2.1e11
TOL, N_INC = 1e-6, 20
SIG_YIELD = 360e6

I_AN = math.pi * (OD**4 - (OD - 2*T_WALL)**4) / 64
A_AN = math.pi * (OD**2 - (OD - 2*T_WALL)**2) / 4
EI = E * I_AN
Z_AN = I_AN / (OD / 2)

# Group A: everything these archetypes contribute lives on the pipeline axis,
# so with one section throughout they reduce to a uniform beam. Group B
# (EAST/EASB/ILT) carries frames held on by connectors, which are penalty
# constraints the solver does not yet apply -- stage 3 work.
GROUP_A = ('ILS-TP', 'ILS-TT', 'ILS-SH', 'ILS-SHTP')


def archetypes() -> dict:
    return {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}


def rig_scene(s_lo: float, s_hi: float) -> Scene:
    """A bare beam as a Scene. No rollers, no forced-elastic zones."""
    return Scene(path=LayPath(R=85.0), stations=(), extent=(s_lo, s_hi),
                 elastic_zones=((s_lo, s_lo), (s_hi, s_hi)), spacing=0.0)


def build(arch_id: str, target_len: float = 2 * OD):
    """The rig model for one archetype. Returns (model, L, s_load)."""
    ils = ils_builder.build_ils(archetypes()[arch_id]['definition'])
    lo, hi = ils.extent
    # s = s_centre - x_local, with s_centre = 0: local +x (vessel) maps to -s.
    s_lo, s_hi = -(hi + PAD), -(lo - PAD)
    m = build_model(rig_scene(s_lo, s_hi), ils, s_centre=0.0,
                    target_len=target_len, extra_stations=(0.0,))
    return m, s_hi - s_lo, 0.0


def solve(m, s_load: float, P: float, tol: float = TOL, n_inc: int = N_INC):
    """Fix both ends in all DOF, load the body centre, solve.

    Every element gets the PIPELINE section -- the rig's own instruction, and
    what makes the closed form exact. A linear-elastic Material, not a J2 one:
    the kernel integrates inelastic sections over fibres and that quadrature
    is 0.4% off the analytic I at 20 fibres and 6.6% off at 30, which in a
    mesher test is indistinguishable from a lost station.
    """
    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in m.nodes],
        elements=[fe.UserElement(e.index, e.n1, e.n2, 1, 1, seed=1)
                  for e in m.elements],
        sections=[fe.PipeSection(1, OD, T_WALL)],
        materials=[fe.Material(1, E)])
    ms = fe.MeshedStructure(mdl)
    assert ms.n_nodes == m.n_nodes, 'kernel altered the model'

    ends = [min(m.nodes, key=lambda n: n.s), max(m.nodes, key=lambda n: n.s)]
    bc = [3 * ms.user_node_to_mesh[n.index] + k for n in ends for k in (0, 1, 2)]

    i_load = min(m.nodes, key=lambda n: (abs(n.s - s_load), abs(n.y)))
    assert abs(i_load.s - s_load) < 1e-9, 'no node at the load point'

    U, _, _ = fe.solve_step(
        ms, np.zeros(ms.n_dofs),
        {'joint_init': [fe.JointLoad(1, i_load.index, 0.0, P, 0.0)]},
        bc, [0.0] * len(bc), n_increments=n_inc, tol=tol, max_iter=60)
    return U, ms, i_load.index


def recover(U, ms) -> tuple:
    """Per-element end moments, from the corotational local rotations.

    The same kinematics `assemble()` uses: rotate into the deformed frame,
    take the relative end rotations, and apply the 4EI/L, 2EI/L pair. Peak
    stress is sigma = M/Z and peak strain is sigma/E, both elastic here by
    construction (the rig never yields -- 194 MPa against 360 MPa).
    """
    M = np.zeros(ms.n_elems)
    for ie in range(ms.n_elems):
        d = ms.elem_dof_array[ie]
        x1, y1, x2, y2 = ms.elem_coords[ie]
        L0 = ms.elem_L0[ie]
        th0 = math.atan2(y2 - y1, x2 - x1)
        th = math.atan2((y2 + U[d[4]]) - (y1 + U[d[1]]),
                        (x2 + U[d[3]]) - (x1 + U[d[0]]))
        # De Souza unwrap, the same one `assemble()` does. Without it an
        # element whose chain runs in -s has th0 = pi, atan2 returns ~-pi for
        # the deformed angle, and dth comes out ~-2pi -- giving a moment of
        # 4EI/L x 2pi that is enormous and IDENTICAL for every load, because
        # it is measuring the wrap rather than the deformation. The pipeline
        # rig never saw it: its elements all run one way, so th0 = 0.
        dth = th - th0
        dth -= 2.0 * math.pi * round(dth / (2.0 * math.pi))
        u3, u6 = U[d[2]] - dth, U[d[5]] - dth
        EIL = ms.elem_E[ie] * ms.elem_I[ie] / L0
        M[ie] = max(abs(4*EIL*u3 + 2*EIL*u6), abs(2*EIL*u3 + 4*EIL*u6))
    sig = M / Z_AN
    return M, sig, sig / E


def closed_form(P, L, a):
    b = L - a
    return (P * a**3 * b**3 / (3 * EI * L**3),
            max(P * a * b**2 / L**2, P * a**2 * b / L**2,
                2 * P * a**2 * b**2 / L**3))


def main() -> int:
    want_plot = '--plot' in sys.argv
    print(f'pipe OD {OD} m, t {T_WALL} m, E {E:.3e} Pa')
    print(f'I = {I_AN:.6e} m^4   Z = {Z_AN:.6e} m^3   EI = {EI:.6e} N.m^2')
    print(f'solver: tol = {TOL:.0e}, n_increments = {N_INC}\n')

    results = {}
    for P in (20e3, 200e3):
        print(f'== P = {P/1e3:.0f} kN ==')
        print(f'  {"archetype":10}{"el":>5}{"L":>9}{"d_FE_mm":>12}'
              f'{"d_closed":>11}{"diff%":>9}{"sig_MPa":>10}{"eps_%":>9}{"":>4}')
        for aid in GROUP_A:
            m, L, s_load = build(aid)
            U, ms, i_load = solve(m, s_load, P)
            d_fe = U[3 * ms.user_node_to_mesh[i_load] + 1]
            d_cf, M_cf = closed_form(P, L, L / 2 if _symmetric(aid) else None)
            _, sig, eps = recover(U, ms)
            results[(aid, P)] = (m, U, ms, sig, eps)
            elastic = 'ok' if sig.max() < SIG_YIELD else 'YIELD'
            print(f'  {aid:10}{m.n_elems:5d}{L:9.3f}{d_fe*1e3:12.5f}'
                  f'{d_cf*1e3:11.5f}{100*(d_fe/d_cf-1):9.3f}'
                  f'{sig.max()/1e6:10.1f}{eps.max()*100:9.4f}  {elastic}')
        print()

    print('== mesh invariance: ILS-SH vs ILS-SHTP, same beam, different mesh ==')
    for P in (20e3, 200e3):
        d = []
        for aid in ('ILS-SH', 'ILS-SHTP'):
            m, L, s_load = build(aid)
            U, ms, i = solve(m, s_load, P)
            d.append((U[3 * ms.user_node_to_mesh[i] + 1], m.n_elems))
        (d1, n1), (d2, n2) = d
        print(f'  P={P/1e3:5.0f} kN   SH({n1} el) {d1*1e3:.9f} mm   '
              f'SHTP({n2} el) {d2*1e3:.9f} mm   rel {abs(d1/d2-1):.2e}')

    if want_plot:
        _plot(results)
    return 0


def _symmetric(aid: str) -> bool:
    ils = ils_builder.build_ils(archetypes()[aid]['definition'])
    lo, hi = ils.extent
    return abs(lo + hi) < 1e-9


def _plot(results) -> None:
    """Peak stress and strain along the pipe, per component, per load."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    out = REPO / 'docs' / 'diagrams' / 'mesher_rig_stress.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.0))
    for ax, P in zip(axes, (20e3, 200e3)):
        peak = 0.0
        for aid in GROUP_A:
            m, U, ms, sig, eps = results[(aid, P)]
            mid = [0.5 * (ms.elem_coords[i][0] + ms.elem_coords[i][2])
                   for i in range(ms.n_elems)]
            order = np.argsort(mid)
            ax.plot(np.array(mid)[order], sig[order] / 1e6, lw=1.5,
                    marker='.', ms=4, alpha=0.85,
                    label=f'{aid} ({m.n_elems} el)')
            peak = max(peak, sig.max() / 1e6)
        # The yield line is annotated rather than drawn: at 20 kN it is 19x
        # the peak and would flatten the curve it is meant to put in context.
        ax.set_ylim(0, peak * 1.35)
        ax.text(0.995, 0.035, f'peak {peak:.1f} MPa  --  '
                f'{100*peak/(SIG_YIELD/1e6):.0f}% of the 360 MPa first yield',
                transform=ax.transAxes, ha='right', va='bottom',
                fontsize=8.5, color='#8b2f3f')
        ax.set_title(f'P = {P/1e3:.0f} kN', fontsize=10, loc='left')
        ax.set_ylabel('peak fibre stress (MPa)')
        ax.grid(alpha=0.22)
        ax.legend(fontsize=7.5, ncol=4, loc='upper center', framealpha=0.9)
    axes[-1].set_xlabel('s (m)   --   +s toward the stinger')
    fig.text(0.5, 0.005,
             'SH and SHTP coincide everywhere the two meshes share a node; '
             'they differ only in WHERE they sample the same moment diagram, '
             'which is most visible near the contraflexure points.',
             ha='center', fontsize=8, color='#7b8794')
    fig.suptitle('Mesher rig: ILS-SH (22 elements) and ILS-SHTP (24) are the '
                 'same beam,\nand the mesh is invisible in the answer',
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(out, dpi=140)
    print(f'\nwrote {out.relative_to(REPO)}')


if __name__ == '__main__':
    raise SystemExit(main())

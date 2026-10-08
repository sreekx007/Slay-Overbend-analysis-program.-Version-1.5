#!/usr/bin/env python3
"""stiffness_rig.py -- the equivalent bending stiffness of an ILS, measured.

    python3 tools/stiffness_rig.py                 # EA-ST F2 cases 1 and 2
    python3 tools/stiffness_rig.py --control       # plain pipe only

WHY A RIG AND NOT A FORMULA. A GD-TP carries its stiffness in the PIPE WALL,
so `slay.define.simplify` reads `EI = E * I_comp` straight off `section_at`.
An EA structure does not: its stiffness is in a FRAME tied to the pipe at two
discrete connectors, and `section_at` returns the plain pipeline everywhere
along it. There is no section to read, so the stiffness has to be MEASURED --
which is what this does, and why `simplify.equivalent` refuses an EA-ST by
name rather than guessing.

THE TEST is a pure-bending one on the span between the two connectors:
equal and opposite moments at the two PIPELINE-side connector nodes, with
only rigid-body restraint, gravity off, no lay tension, everything linear
elastic. The span then carries constant M, so

    EI_eq = M * L / dtheta

in closed form. NO SEARCH IS NEEDED and none is done: a loop that stopped
when the rotation "almost" matched would be choosing its own tolerance where
an exact inverse is available.

THREE THINGS ARE CHECKED RATHER THAN ASSUMED, and all three are printed:

  LINEARITY      two token moments. If EI moves with M the connectors are
                 slipping or lifting and a single equivalent E is a fiction.
  BOUNDARY       the same span clamped at one end instead. Fixing all three
                 DOF at a connector imposes a local restraint the lay does
                 not have, and over a 10 D span the St-Venant disturbance
                 might not decay. The two must agree.
  CONTROL        plain pipe, same rig, must give back E * I_pipe.

THE QUADRATURE IS NOT THE DEFAULT, and that is the one real finding here.
`solve`'s default `polar` scheme (the B31-equivalent angular integration the
reference runs use) reads the plain-pipe control **0.2955% LOW**, a fixed
bias independent of length and mesh. Self-calibrating it away -- taking the
ILS stiffness as a ratio to the rig's own plain-pipe figure -- OVER-corrects,
giving 8.436 where the truth is 8.415, because the frame members are not the
pipe section and so do not carry the same bias. The fix is to use the
converged Cartesian scheme instead: `polar=False, n_fibres=20` reads the
control to +0.0002%.
"""
from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import config                                               # noqa: E402
from slay.model.assemble import build_model                 # noqa: E402
from slay.physics.loads import NodalLoad, Restraint         # noqa: E402
from slay.physics.problem import build_problem              # noqa: E402
from slay.scene.path import LayPath                         # noqa: E402
from slay.scene.rollers import Station, StationRole         # noqa: E402
from slay.scene.scene import Scene                          # noqa: E402
from slay.solve.kernel import dof, mesh_of_problem          # noqa: E402
from slay.solve.passage import solve                        # noqa: E402

D = 0.4064
PAD = 6.0
M_TOKEN = 1.0e5                       # N.m

# THE CONVERGED SCHEME, not the default. See the module docstring.
SOLVE_KW = dict(polar=False, n_fibres=20)

I_PIPE = math.pi / 64.0 * (0.4064 ** 4 - 0.3644 ** 4)
EI_PIPE = config.STEEL_E * I_PIPE


def _scene(s_lo: float, s_hi: float) -> Scene:
    """A bare beam. ONE FIXED station because `boundary_conditions` refuses a
    model with no anchor -- rightly, since a lay model without one is a free
    body. The restraints it makes are replaced by the test's own; a FIXED
    station is not a CONTACT one and attracts no target."""
    anchor = Station(name='RIG', s_arc=s_lo, x=-s_lo, y=0.0, radius=0.3,
                     normal=(0.0, -1.0), role=StationRole.FIXED)
    return Scene(path=LayPath(R=85.0), stations=(anchor,),
                 extent=(s_lo, s_hi),
                 elastic_zones=((s_lo, s_lo), (s_hi, s_hi)), spacing=0.0)


def _EI(model, scene, ils, n_lo, n_hi, L, M=M_TOKEN, mode='free'):
    """EI_eq over the span (n_lo, n_hi). `mode` picks the boundary."""
    p = build_problem(model, scene,
                      assembly=None if ils is None else ils.assembly,
                      ils=ils, s_centre=0.0, tension=0.0, gravity=False,
                      elastic_spans=(scene.extent,))
    if mode == 'clamp':
        res = (Restraint(node=n_lo, ux=True, uy=True, rz=True, source='rig'),)
        lds = (NodalLoad(node=n_hi, mz=M, source='rig'),)
    else:
        # SELF-EQUILIBRATING: +M and -M, so the supports carry no force and
        # impose no local restraint. The span is in constant moment.
        res = (Restraint(node=n_lo, ux=True, uy=True, rz=False, source='rig'),
               Restraint(node=n_hi, ux=False, uy=True, rz=False, source='rig'))
        lds = (NodalLoad(node=n_hi, mz=+M, source='rig'),
               NodalLoad(node=n_lo, mz=-M, source='rig'))
    p = dataclasses.replace(p, loads=lds, restraints=res)
    r, _ = solve(p, **SOLVE_KW)
    ms = mesh_of_problem(p)[0]
    dth = r.U[dof(ms, n_hi, 2)] - r.U[dof(ms, n_lo, 2)]
    return M * L / dth, r.status


def plain(L: float, M=M_TOKEN, mode='free', target_len=2 * D):
    """THE CONTROL. Plain pipe must give back E * I_pipe."""
    sc = _scene(-(L / 2 + PAD), (L / 2 + PAD))
    m = build_model(sc, None, s_centre=0.0, target_len=target_len,
                    extra_stations=(-L / 2, L / 2, 0.0))
    pick = lambda s: min(m.nodes,                            # noqa: E731
                         key=lambda n: (abs(n.s - s), abs(n.y))).index
    return _EI(m, sc, None, pick(-L / 2), pick(L / 2), L, M, mode)


def connector_span(ils):
    """`(model, scene, n_lo, n_hi, L)` for the span between the two
    PIPELINE-side connector nodes. Refuses anything but exactly two."""
    lo, hi = ils.extent
    sc = _scene(-(hi + PAD), -(lo - PAD))
    m = build_model(sc, ils, s_centre=0.0, extra_stations=(0.0,),
                    emit_unenforced_conn_types=frozenset({'S'}))
    at = {n.index: n for n in m.nodes}
    ns = []
    for e in m.elements:
        if e.connector is not None:
            a, b = at[e.n1], at[e.n2]
            # The PIPELINE side is the node nearer the centreline; the other
            # belongs to the structure.
            ns.append(a.index if abs(a.y) < abs(b.y) else b.index)
    ns = sorted(set(ns), key=lambda i: at[i].s)
    if len(ns) != 2:
        raise SystemExit(
            f'this layout has {len(ns)} pipeline-side connector nodes, not 2. '
            f'An equivalent stiffness "between the connectors" is only '
            f'defined for two; more needs a rule for which span is meant.')
    n_lo, n_hi = ns
    return m, sc, n_lo, n_hi, abs(at[n_hi].s - at[n_lo].s)


def measure(ils, label=''):
    """Measure one ILS, with all three checks. Returns a dict."""
    m, sc, n_lo, n_hi, L = connector_span(ils)
    ei1, st = _EI(m, sc, ils, n_lo, n_hi, L, M_TOKEN, 'free')
    ei2, _ = _EI(m, sc, ils, n_lo, n_hi, L, 2 * M_TOKEN, 'free')
    ei3, _ = _EI(m, sc, ils, n_lo, n_hi, L, M_TOKEN, 'clamp')
    ctrl, _ = plain(L)
    return dict(label=label, L=L, EI=ei1, status=st,
                lin_err=ei2 / ei1 - 1.0,
                bnd_err=ei3 / ei1 - 1.0,
                ctrl_err=ctrl / EI_PIPE - 1.0,
                ratio=ei1 / EI_PIPE, E_eq=config.STEEL_E * ei1 / EI_PIPE)


def main() -> int:
    def arg(flag, cast, default):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    if '--control' in sys.argv:
        print(f'E*I of the pipeline = {EI_PIPE / 1e6:.4f} MN.m2')
        for L in (4.064, 8.128):
            for tl in (2 * D, 0.5 * D):
                got, _ = plain(L, target_len=tl)
                print(f'  plain pipe L {L:.3f} m, mesh {tl / D:.2f} x OD -> '
                      f'{got / 1e6:9.4f} MN.m2   {100 * (got / EI_PIPE - 1):+.4f}%')
        return 0

    from study_f2 import build as build_f2
    L_top = arg('--L-top', float, 22.0)
    cases = [('F2 case 1', 10.0, 2.22), ('F2 case 2', 20.0, 2.85)]
    print(f'EA-ST F2 -- equivalent bending stiffness between the connectors.')
    print(f'  pure bending, token M = {M_TOKEN / 1e3:.0f} kN.m, gravity off, '
          f'no lay tension, linear elastic,\n  Cartesian fibre quadrature '
          f'(n = 20) -- NOT the polar default, which reads the control '
          f'0.30% low.')
    print()
    print(f'{"case":10s}{"P_c1":>6s}{"kT":>6s}{"L":>8s}{"EI_eq":>12s}'
          f'{"EI/EIp":>8s}{"E_eq":>8s} | {"lin":>8s}{"bnd":>8s}{"ctrl":>9s}')
    for lab, pc1, kT in cases:
        r = measure(build_f2(pc1, kT, L_top, 'F2'), lab)
        print(f'{lab:10s}{pc1:5.0f}D{kT:6.2f}{r["L"]:8.4f}'
              f'{r["EI"] / 1e6:11.2f}M{r["ratio"]:8.3f}'
              f'{r["E_eq"] / 1e9:7.0f}G | '
              f'{100 * r["lin_err"]:+7.3f}%{100 * r["bnd_err"]:+7.3f}%'
              f'{100 * r["ctrl_err"]:+8.4f}%')
    print('\n  lin  = EI at 2M against EI at M -- connectors slipping shows here')
    print('  bnd  = clamped-end boundary against the self-equilibrating one')
    print('  ctrl = plain pipe through the same rig against analytic E*I')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

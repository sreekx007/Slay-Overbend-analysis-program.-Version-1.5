#!/usr/bin/env python3
"""study_table_xxiii.py -- Paper 1 TABLE XXIII and XXIV: component length.

    python3 tools/study_table_xxiii.py [--spacing 9] [--step-OD 1] [--case B3]

Strain (TABLE XXIII) and bending moment (TABLE XXIV) come from the SAME six
runs, so they are one study and one tool.

WHAT MAKES THIS BLOCK WORTH RUNNING. Length is the dominant driver of peak
strain for a thick component, and across this range the paper's own numbers
stop behaving like a trend:

    R = 85    10 D  1.104 pct   1581 kN.m
              20 D  1.861 pct   1977 kN.m
              40 D  1.914 pct   2883 kN.m

Strain rises 69 pct from 10 D to 20 D and then only 2.8 pct from 20 D to
40 D, while the moment keeps climbing 46 pct over the same step. The paper
attributes the plateau to the component growing long enough to span TWO
ROLLERS: past that length the extra stiffness is carried by a second support
rather than by curvature in the pipe. A quantity that saturates while its
driver does not is a behaviour change, and reproducing a behaviour change is
a stronger result than matching any single number -- it cannot be had by
tuning.

The 40 D case is the one that decides it, and it is also the most expensive:
16.256 m of component, which is nearly two roller spans.

THE WALL THICKNESS IS NOT CONSTANT ACROSS RADII, and missing that would make
the comparison meaningless while looking fine. TABLE XXII specifies 65 mm
(3.1x) at R = 70 and 53 mm (2.5x) at R = 85, so the two radii are different
components and not the same one at two radii.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import plot_stinger as gen                                 # noqa: E402
import slide                                               # noqa: E402
from slay.report import passage as rp                      # noqa: E402

D = 0.4064
T_PIPE = 0.021

# TABLE XXII inputs with TABLE XXIII / XXIV targets.
CASES = (
    dict(case='B1', R=70.0, L_OD=2.5,  t_mm=65, eps=0.780, bm=1384),
    dict(case='B2', R=70.0, L_OD=10.0, t_mm=65, eps=1.499, bm=1650),
    dict(case='B3', R=70.0, L_OD=20.0, t_mm=65, eps=2.514, bm=2223),
    dict(case='B2', R=85.0, L_OD=10.0, t_mm=53, eps=1.104, bm=1581),
    dict(case='B3', R=85.0, L_OD=20.0, t_mm=53, eps=1.861, bm=1977),
    dict(case='B4', R=85.0, L_OD=40.0, t_mm=53, eps=1.914, bm=2883),
)


def run_case(c, spacing, step_OD):
    ils = gen.build_component_ils('ILS-TP', L_OD=c['L_OD'],
                                  t_ratio=c['t_mm'] / 1000.0 / T_PIPE)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sc, L_comp, _recs, _junc, _probs, positions = slide.passage(
            arch_id='none', ils=ils, R=c['R'], spacing=spacing,
            tension_mt=100.0, step=step_OD * D, verbose=False)
    s_max, _label = rp.zone(sc)
    peak, at_s, bm, n_ok = 0.0, None, 0.0, 0
    for pos in positions:
        if not pos.converged:
            continue
        n_ok += 1
        for (_i, s, e) in pos.result.strains:
            if s + pos.shift < s_max and abs(e) > peak:
                peak, at_s = abs(e), s + pos.shift
        for (_i, s, m) in getattr(pos.result, 'moments', ()):
            if s + pos.shift < s_max:
                bm = max(bm, abs(m))
    return dict(c=c, peak=peak, at_s=at_s, bm=bm, L=L_comp,
                n_ok=n_ok, n=len(positions))


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    spacing = arg('--spacing', float, 9.0)
    step_OD = arg('--step-OD', float, 1.0)
    only = arg('--case', str, None)

    print(f'Paper 1 TABLE XXIII and XXIV -- component length, 100 MT, '
          f'{spacing:.0f} m spacing\n')
    print(f'{"case":5s} {"R":>4s} {"L":>6s} {"t":>5s}  '
          f'{"ours eps":>9s} {"paper":>7s} {"d%":>7s}   '
          f'{"ours BM":>8s} {"paper":>7s} {"d%":>7s}  {"at s":>6s}  conv')
    out = []
    for c in CASES:
        if only and c['case'] != only:
            continue
        r = run_case(c, spacing, step_OD)
        out.append(r)
        eps = 100 * r['peak']
        de = f'{100 * (eps / c["eps"] - 1):+6.1f}%' if r['n_ok'] else '    --'
        bmk = r['bm'] / 1000.0
        dm = f'{100 * (bmk / c["bm"] - 1):+6.1f}%' if r['n_ok'] else '    --'
        at = '    --' if r['at_s'] is None else f'{r["at_s"]:6.2f}'
        print(f'{c["case"]:5s} {c["R"]:4.0f} {c["L_OD"]:5.0f}D {c["t_mm"]:4d}mm  '
              f'{eps:8.4f}% {c["eps"]:6.3f}% {de}   '
              f'{bmk:8.1f} {c["bm"]:7d} {dm}  {at}  '
              f'{r["n_ok"]}/{r["n"]}', flush=True)

    # THE SATURATION IS THE RESULT, so it is computed rather than left to a
    # reader comparing two rows by eye.
    at85 = {r['c']['L_OD']: r for r in out
            if r['c']['R'] == 85.0 and r['n_ok']}
    if {20.0, 40.0} <= set(at85):
        a, b = at85[20.0], at85[40.0]
        de = 100 * (b['peak'] / a['peak'] - 1)
        dm = 100 * (b['bm'] / a['bm'] - 1)
        print(f'\n  R = 85, 20 D -> 40 D:  strain {de:+.1f}%  moment {dm:+.1f}%')
        print(f'  paper:                 strain +2.8%  moment +45.8%')
        print('  The paper\'s finding is that strain SATURATES while the '
              'moment does not,\n  because the component grows long enough '
              'to span two rollers.')
        if de < 15.0 < dm:
            print('  REPRODUCED: strain flattens, moment keeps climbing.')
        else:
            print('  NOT reproduced as published -- see the two deltas above.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

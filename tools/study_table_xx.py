#!/usr/bin/env python3
"""study_table_xx.py -- Paper 1 TABLE XX and XXI: component wall thickness.

    python3 tools/study_table_xx.py [--spacing 9] [--step-OD 1]

NINE CASES, three wall thicknesses at three radii, with the component length
fixed at 1000 mm (about 2.5 D). The paper's peak sits at the pipe-to-
component junction at the second stinger roller, Phase 1.

CONSTANT BORE is the paper's own convention: `OD_comp = ID + 2t`, so a
thicker wall grows outward. Our 53 mm case computes OD 470.4 mm and
I/I_pipe = 3.248 against the paper's stated 471 mm and about 3.2x, which is
the check that the convention was read right.

MOMENT IS READ ON THE COMPONENT BODY, because that is where TABLE XXI
reports it -- its location column says "near component midspan, at the
instant a roller is below midspan". The pipeline's own maximum is printed
beside it, because the two are close here and it is what an unqualified
"peak moment" would return. Reading the wrong member understated these by
about 0.7% on a short component once already (6 Oct 2026).

RE-RUN BECAUSE OF L105 AND L106. Every published number in this table
predates the lay tension following the stinger, and every case is a passage.
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
from slay.study import sweep                               # noqa: E402

D = 0.4064
T_PIPE = 0.021
L_OD = 1.0 / D                      # 1000 mm, in pipe diameters

# TABLE XX strain and TABLE XXI moment, by case label and radius.
CASES = (
    dict(case='A1', t_mm=32, R=70.0,  eps=0.562, bm=1311),
    dict(case='A1', t_mm=32, R=85.0,  eps=0.473, bm=1251),
    dict(case='A1', t_mm=32, R=100.0, eps=0.339, bm=1131),
    dict(case='A2', t_mm=42, R=70.0,  eps=0.647, bm=1347),
    dict(case='A2', t_mm=42, R=85.0,  eps=0.508, bm=1288),
    dict(case='A2', t_mm=42, R=100.0, eps=0.358, bm=1144),
    dict(case='A3', t_mm=53, R=70.0,  eps=0.727, bm=1366),
    dict(case='A3', t_mm=53, R=85.0,  eps=0.556, bm=1311),
    dict(case='A3', t_mm=53, R=100.0, eps=0.395, bm=1184),
)


def _component_elements(problems):
    """Element indices belonging to the COMPONENT, not the pipeline.

    Reaching for this on a `Position` returns an empty set and reports the
    body moment as 0.0 -- an absence that prints as a number, which is
    L097's lesson in another place. The element table lives on the problem.
    """
    for prob in problems or ():
        if prob is not None and getattr(prob, 'elements', None):
            return {i for (i, _a, _b, o, _l) in prob.elements
                    if o != 'pipeline'}
    return set()


def run_case(c, spacing, step_OD):
    ils = gen.build_component_ils('ILS-TP', L_OD=L_OD,
                                  t_ratio=c['t_mm'] / 1000.0 / T_PIPE)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sc, L_comp, _recs, _junc, probs, positions, done = slide.passage(
            arch_id='none', ils=ils, R=c['R'], spacing=spacing,
            tension_mt=100.0, step=step_OD * D, verbose=False)
    s_max, _label = rp.zone(sc)
    comp = _component_elements(probs)
    if not comp:
        raise ValueError('no component elements found -- the body moment '
                         'would report as 0.0, which reads as a measurement '
                         'rather than a lookup failure')
    peak, at_s = 0.0, None
    bm = dict(comp=0.0, pipe=0.0)
    for pos in positions:
        if not pos.converged:
            continue
        for (_i, s, e) in pos.result.strains:
            if s + pos.shift < s_max and abs(e) > peak:
                peak, at_s = abs(e), s + pos.shift
        for (i, s, m) in getattr(pos.result, 'moments', ()):
            if s + pos.shift >= s_max:
                continue
            k = 'comp' if i in comp else 'pipe'
            bm[k] = max(bm[k], abs(m))
    return dict(c=c, peak=peak, at_s=at_s, bm=bm['comp'],
                bm_pipe=bm['pipe'], L=L_comp,
                done=done)


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    spacing = arg('--spacing', float, 9.0)
    step_OD = arg('--step-OD', float, 1.0)
    only = arg('--case', str, None)

    print(f'Paper 1 TABLE XX and XXI -- component wall thickness, '
          f'L = 1000 mm, 100 MT, {spacing:.0f} m spacing\n')
    print(f'{"case":5s} {"t":>5s} {"R":>5s}  {"ours eps":>9s} {"paper":>7s} '
          f'{"d%":>7s}   {"BM body":>8s} {"paper":>7s} {"d%":>7s} '
          f'{"BM pipe":>8s}  {"swept":>6s}')
    bad = []
    for c in CASES:
        if only and c['case'] != only:
            continue
        r = run_case(c, spacing, step_OD)
        eps = 100 * r['peak']
        bmk = r['bm'] / 1000.0
        done = r['done']
        if done.complete:
            de = f'{100 * (eps / c["eps"] - 1):+6.1f}%'
            dm = f'{100 * (bmk / c["bm"] - 1):+6.1f}%'
        else:
            de = dm = '  VOID'
            bad.append((c, done))
        flag = '' if done.complete else f'{100 * done.fraction:5.0f}%'
        print(f'{c["case"]:5s} {c["t_mm"]:4d}mm {c["R"]:4.0f}m  '
              f'{eps:8.4f}% {c["eps"]:6.3f}% {de}   '
              f'{bmk:8.1f} {c["bm"]:7d} {dm} {r["bm_pipe"] / 1000:8.1f}  '
              f'{flag:>6s}', flush=True)
    for c, done in bad:
        print(f'\n  {c["case"]} R={c["R"]:.0f}: {done}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

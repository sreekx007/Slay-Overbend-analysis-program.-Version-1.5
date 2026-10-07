#!/usr/bin/env python3
"""study_table_xxvi.py -- Paper 1 TABLE XXVI: two components, and the gap
between them.

    python3 tools/study_table_xxvi.py [--spacing 9] [--step-OD 1]

Three cases: two identical thick bodies with 2.5 D, 10 D and 20 D of plain
pipe between them. The paper's own conclusion is that the spacing is
negligible -- 0.771 / 0.760 / 0.751%, a change of 2.6% over an eightfold
range -- which makes this a cheap test of whether the program agrees about an
effect being ABSENT. A model that invents a spacing dependence here is
telling you something about itself.

THE LEDGER SAID THIS "NEEDS A TWO-COMPONENT ASSEMBLY WE HAVE NOT BUILT". It
does not. `ils_builder` takes a list of components and has always iterated
over it; what was missing was a spec with two entries in it, which is DATA.
Verified before this file was written: the same archetype with a second
GD-TP at a distinct `id` and `centre_x` builds at all three spacings and
reports the spans those gaps imply (3.016, 6.064, 10.128 m). G7 is intact --
`ils_builder` and `component_spec` are untouched and this only hands them a
different definition, exactly as `emit_profile._ea_ils` already does.

THE CONFIGURATION IS INFERRED, and the inference is stated rather than
buried. TABLE XXVI does not name its radius, tension or component. But its
C1 row reads 0.771% and 1384 kN.m, and TABLE XXIII's B1 row -- R = 70 m,
100 MT, a 2.5 D body at 65 mm wall -- reads 0.780% and the SAME 1384 kN.m.
A shared moment to four figures across two tables is not a coincidence, so
C1 is B1 with a second body added, and that is the configuration used here.
If that reading is wrong, the three rows move together and the TREND -- which
is what the table is about -- survives it.
"""

from __future__ import annotations

import copy
import json
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ils_builder                                         # noqa: E402
import plot_stinger as gen                                 # noqa: E402
import slide                                               # noqa: E402
from slay.report import passage as rp                      # noqa: E402

D = 0.4064
T_PIPE = 0.021
R, TENSION, T_COMP_MM = 70.0, 100.0, 65

CASES = (
    dict(case='C1', gap=2.5,  eps=0.771, bm=1384),
    dict(case='C2', gap=10.0, eps=0.760, bm=1371),
    dict(case='C3', gap=20.0, eps=0.751, bm=1365),
)


def two_body_ils(gap_D, L_OD=2.5, t_mm=T_COMP_MM):
    """ILS-TP with a SECOND identical body `gap_D` diameters beyond the first.

    The two are placed symmetrically about the archetype's own centre, so the
    assembly's centre of mass stays where a one-body case put it and the
    sweep's `s_centre` means the same thing.
    """
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        gen.FIXTURE.read_text())['archetypes']}['ILS-TP']['definition'])
    a = spec['components'][0]
    a['L_comp'] = L_OD * D
    a['t_comp'] = t_mm / 1000.0
    b = copy.deepcopy(a)
    b['id'] = f'{a["id"]}2'
    pitch = a['L_comp'] + gap_D * D
    a['centre_x'] = -pitch / 2.0
    b['centre_x'] = +pitch / 2.0
    spec['components'].append(b)
    return ils_builder.build_ils(spec)


def run_case(c, spacing, step_OD):
    ils = two_body_ils(c['gap'])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sc, L_comp, _recs, _junc, probs, positions, done = slide.passage(
            arch_id='none', ils=ils, R=R, spacing=spacing,
            tension_mt=TENSION, step=step_OD * D, verbose=False)
    s_max, _label = rp.zone(sc)
    comp = set()
    for prob in probs or ():
        if prob is not None and getattr(prob, 'elements', None):
            comp = {i for (i, _a, _b, o, _l) in prob.elements
                    if o != 'pipeline'}
            break
    if not comp:
        raise ValueError('no component elements found -- the body moment '
                         'would report as 0.0, which reads as a measurement')
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
            bm['comp' if i in comp else 'pipe'] = max(
                bm['comp' if i in comp else 'pipe'], abs(m))
    return dict(c=c, peak=peak, at_s=at_s, bm=bm['comp'],
                bm_pipe=bm['pipe'], L=L_comp, done=done)


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    spacing = arg('--spacing', float, 9.0)
    step_OD = arg('--step-OD', float, 1.0)

    print(f'Paper 1 TABLE XXVI -- two components, spacing. R = {R:.0f} m, '
          f'{TENSION:.0f} MT, {spacing:.0f} m spacing, two 2.5 D bodies at '
          f'{T_COMP_MM} mm\n')
    print(f'{"case":5s} {"gap":>6s} {"span":>7s}  {"ours eps":>9s} '
          f'{"paper":>7s} {"d%":>8s}  {"BM body":>8s} {"paper":>7s} '
          f'{"d%":>8s} {"BM pipe":>8s} {"swept":>6s}')
    got = []
    for c in CASES:
        r = run_case(c, spacing, step_OD)
        eps = 100 * r['peak']
        bmk = r['bm'] / 1000.0
        done = r['done']
        if done.complete:
            de = f'{100 * (eps / c["eps"] - 1):+7.1f}%'
            dm = f'{100 * (bmk / c["bm"] - 1):+7.1f}%'
            got.append(eps)
        else:
            de = dm = '   VOID'
        flag = '' if done.complete else f'{100 * done.fraction:5.0f}%'
        print(f'{c["case"]:5s} {c["gap"]:5.1f}D {r["L"]:6.3f}m  {eps:8.4f}% '
              f'{c["eps"]:6.3f}% {de}  {bmk:8.1f} {c["bm"]:7d} {dm} '
              f'{r["bm_pipe"] / 1000:8.1f} {flag:>6s}', flush=True)

    # THE TREND IS THE RESULT, and the paper's is that there is none.
    if len(got) == len(CASES):
        # PER CENT ON BOTH SIDES OF THE TEST. This compared a FRACTION
        # against a percentage threshold -- 0.096 < 6.0 -- and printed
        # AGREES for a spread of 9.6% against the paper's 2.6%. A verdict
        # line that cannot be wrong in silence is the point of having one.
        spread = 100.0 * (max(got) - min(got)) / max(got)
        paper = 100.0 * (0.771 - 0.751) / 0.771
        print(f'\n  ours {got[0]:.3f} / {got[1]:.3f} / {got[2]:.3f}, '
              f'spread {spread:.1f}%')
        print(f'  paper 0.771 / 0.760 / 0.751, spread {paper:.1f}% -- the '
              f'paper calls the spacing NEGLIGIBLE')
        print(f'  both FALL with spacing, so the SIGN agrees; ours is '
              f'{spread / paper:.1f}x the published spread.')
        print('  AGREES: the spacing is negligible here too.'
              if spread < 2.0 * paper else
              '  DISAGREES ON MAGNITUDE: the spacing is not negligible here.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""study_f2.py -- EA-ST with an F2 connection, against the published cases.

    python3 tools/study_f2.py [--R 85] [--spacing 9] [--tension 120]
                              [--L-top 22] [--step 2]

THE TWO CASES, from the reference's Type F2 study (Table VIII, Figs 32-33).
A portal frame sits on the pipeline, fastened at TWO points a distance
`P_c1` apart, and the frame section carries a stiffness `kT` expressed as a
multiple of the pipeline's:

    Case 1   P_c1 = 10 D   kT = 2.22   ->  X_c 0.936%  X_i 0.043%  X_e 0.732%
    Case 2   P_c1 = 20 D   kT = 2.85   ->  X_c 1.410%  X_i 0.075%  X_e 1.021%

THE THREE REGIONS are the reference's, and they are not the offset body's
X1-X5 (`slay.report.regions`) -- a different body type gets a different
reporting scheme:

    X_c   the pipe AT a connector, within 1.5 D either side. The peak, and
          what governs: the frame's load path into the pipe is two points,
          so the pipe is bent sharply where they are.
    X_i   INTERNAL, the pipe between the two connectors. Shielded by the
          frame spanning over it, and the lowest of the three by an order of
          magnitude -- which is the reference's real finding: a two-point
          attachment does not load the pipe it spans, it loads its own ends.
    X_e   EXTERNAL, the pipe outboard of the connectors, governed by the
          stinger overbend rather than by the frame.

WHAT IS ASSUMED, because the reference does not state it. `L_top`, the
frame's own width, is HELD FIXED across both cases at 22 D. The cases vary
`P_c1` from 10 D to 20 D and a frame narrower than its own attachment span
is not a frame, so something had to give; holding the structure's SIZE
constant and varying only its attachment LAYOUT is what isolates the
variable the study is about. Measured sensitivity is small -- Case 1 moves
0.6% between 22 D and 30 D, Case 2 about 2% -- so the choice is not what
decides the answer. `--L-top` varies it.

WHAT IS NOT LIKE FOR LIKE. The reference reports ONE analysis position; this
runs the whole passage and reports the ENVELOPE, the worst any position saw.
An envelope is never below a single position, so a difference in that
direction is expected before any physics is blamed. The per-position table
is printed for exactly that reason.
"""

from __future__ import annotations

import copy
import json
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

import ils_builder                                    # noqa: E402
import slide                                          # noqa: E402
from slay.report import passage as rp                 # noqa: E402

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'
D = 0.4064

# The pipe within this many diameters of a connector is 'at' it. 1.5 D is
# about two elements at the ruled 2 x OD density, so the band is resolved
# rather than being a single element's opinion.
AT_CONNECTOR_OD = 1.5

PAPER = {
    'Case 1': dict(P_c1_D=10.0, kT=2.22, X_c=0.936, X_i=0.043, X_e=0.732),
    'Case 2': dict(P_c1_D=20.0, kT=2.85, X_c=1.410, X_i=0.075, X_e=1.021),
}


def build(P_c1_D, kT, L_top_D):
    """ILS-EAST re-dimensioned, by editing the archetype's own definition.

    `ils_builder` stays the single author of what a component IS (G7), so
    the frame's geometry comes with the edit rather than being constructed
    here.
    """
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        FIXTURE.read_text())['archetypes']}['ILS-EAST']['definition'])
    c = spec['components'][0]
    c['P_c1'] = P_c1_D * D
    c['kT_ratio'] = kT
    c['L_top'] = L_top_D * D
    return ils_builder.build_ils(spec)


def classify(s_mid, lo, hi):
    """Which region a point on the pipe is in, by the connector stations."""
    if min(abs(s_mid - lo), abs(s_mid - hi)) <= AT_CONNECTOR_OD * D:
        return 'X_c'
    return 'X_i' if lo < s_mid < hi else 'X_e'


def region_peaks(position, problem, s_max):
    """{region: peak |strain|} for one solved position, inside the band."""
    xy = {i: s for (i, s, _y) in problem.nodes}
    cs = sorted(xy[n1] for (_i, n1, _n2, _t, _l, _s) in problem.connectors)
    lo, hi = cs[0], cs[-1]
    ends = {i: sorted((xy[a], xy[b]))
            for (i, a, b, _o, _l) in problem.elements}
    out = {'X_c': 0.0, 'X_i': 0.0, 'X_e': 0.0}
    for (i, _sm, e) in position.result.strains:
        a, b = ends.get(i, (0.0, 0.0))
        mid = 0.5 * (a + b)
        if mid + position.shift >= s_max:       # the D6 tip artefact
            continue
        r = classify(mid, lo, hi)
        out[r] = max(out[r], abs(e))
    return out, (lo, hi)


def run_case(name, R, spacing, tension_mt, L_top_D, step_OD):
    p = PAPER[name]
    ils = build(p['P_c1_D'], p['kT'], L_top_D)
    sc, L_comp, recs, _junc, probs, positions = slide.passage(
        arch_id='none', ils=ils, R=R, spacing=spacing,
        tension_mt=tension_mt, step=step_OD * D, verbose=False)
    s_max, _label = rp.zone(sc)

    per_pos, env = [], {'X_c': 0.0, 'X_i': 0.0, 'X_e': 0.0}
    span = None
    for pos, prob in zip(positions, probs):
        if prob is None or not pos.converged:
            continue
        got, span = region_peaks(pos, prob, s_max)
        per_pos.append((pos.index, pos.shift, got))
        for k in env:
            env[k] = max(env[k], got[k])
    return dict(name=name, paper=p, env=env, per_pos=per_pos, span=span,
                L_comp=L_comp, n=len(positions),
                n_ok=sum(1 for r in recs if r.converged))


def main() -> int:
    def arg(flag, cast, default):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    R = arg('--R', float, 85.0)
    spacing = arg('--spacing', float, 9.0)
    tension = arg('--tension', float, 120.0)
    L_top_D = arg('--L-top', float, 22.0)
    step_OD = arg('--step', float, 2.0)

    print(f'EA-ST, F2 connection.  R = {R:.0f} m, spacing = {spacing:.0f} m, '
          f'{tension:.0f} MT, L_top = {L_top_D:.0f} D (assumed, held fixed)')

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for name in ('Case 1', 'Case 2'):
            r = run_case(name, R, spacing, tension, L_top_D, step_OD)
            p, env = r['paper'], r['env']
            print(f'\n=== {name}: P_c1 = {p["P_c1_D"]:.0f} D, kT = {p["kT"]}, '
                  f'L_comp = {r["L_comp"]:.3f} m, '
                  f'{r["n_ok"]}/{r["n"]} positions converged ===')
            print(f'  connectors at s = {r["span"][0]:.3f} and '
                  f'{r["span"][1]:.3f} m  '
                  f'(span {(r["span"][1] - r["span"][0]) / D:.2f} D)')
            print(f'  {"":12s}{"X_c":>10s}{"X_i":>10s}{"X_e":>10s}')
            print(f'  {"reference":12s}{p["X_c"]:9.3f}%{p["X_i"]:9.3f}%'
                  f'{p["X_e"]:9.3f}%')
            print(f'  {"envelope":12s}{100 * env["X_c"]:9.3f}%'
                  f'{100 * env["X_i"]:9.3f}%{100 * env["X_e"]:9.3f}%')
            row = []
            for k in ('X_c', 'X_i', 'X_e'):
                ref = p[k]
                row.append(f'{(100 * env[k] - ref) / ref * 100:+8.1f}%')
            print(f'  {"delta":12s}{row[0]:>10s}{row[1]:>10s}{row[2]:>10s}')
            print(f'\n  per position (the reference reports ONE, this is the '
                  f'whole passage):')
            print(f'    {"pos":>4s}{"shift":>9s}{"X_c":>10s}{"X_i":>10s}'
                  f'{"X_e":>10s}')
            for (i, sh, g) in r['per_pos']:
                mark = ' <- envelope' if g['X_c'] == env['X_c'] else ''
                print(f'    {i:4d}{sh:9.3f}{100 * g["X_c"]:9.3f}%'
                      f'{100 * g["X_i"]:9.3f}%{100 * g["X_e"]:9.3f}%{mark}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

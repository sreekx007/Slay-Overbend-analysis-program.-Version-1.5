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
from slay.study import sweep                          # noqa: E402

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'
D = 0.4064

# THE REFERENCE'S OWN NUMBER, not a convenient one. Sections VII.B and
# VIII.B both say X_c is "2 x Pipe OD on either side of the connector
# point". An earlier 1.5 D here was chosen to be about two elements wide at
# the ruled mesh -- defensible as a band, wrong as this band.
AT_CONNECTOR_OD = 2.0

PAPER = {
    'Case 1': dict(P_c1_D=10.0, kT=2.22, X_c=0.936, X_i=0.043, X_e=0.732),
    'Case 2': dict(P_c1_D=20.0, kT=2.85, X_c=1.410, X_i=0.075, X_e=1.021),
}


def build(P_c1_D, kT, L_top_D, system='F2'):
    """ILS-EAST re-dimensioned, by editing the archetype's own definition.

    `ils_builder` stays the single author of what a component IS (G7), so
    the frame's geometry comes with the edit rather than being constructed
    here.

    `system` NAMES A PUBLISHED LAYOUT and nothing is approximated to fit it.
    PS is `(None, 'P', None, 'S', None)` -- a pin at slot 2 and a SKEWED
    roller at slot 4 -- and the mesher refuses an 'S' by default, under G9.
    It is emitted only through `emit_unenforced_conn_types={'S'}`, the narrow
    opt-in where the mesher emits the joint and the CALLER takes on enforcing
    it; `solve.passage` discharges that by rebuilding the tie's co-rotating
    frame every Newton iteration. Checked before this was used rather than
    assumed: with the opt-in, one skewed row is resolved and one is applied,
    so the constraint is enforced and not quietly dropped.
    """
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        FIXTURE.read_text())['archetypes']}['ILS-EAST']['definition'])
    spec['ils']['connection_system'] = system
    c = spec['components'][0]
    c['P_c1'] = P_c1_D * D
    c['kT_ratio'] = kT
    c['L_top'] = L_top_D * D
    return ils_builder.build_ils(spec)


REGIONS = ('X_c', 'X_i', 'X_e')


def classify(s_mid, conn, body=None):
    """Which region a point on the pipe is in. The reference's definitions:

        X_c   "Region near the connector. 2 x Pipe OD on either side of the
              connector point."
        X_i   an INTERIOR region -- between two connectors.
        X_e   "refers to pipeline OUTSIDE THE STRUCTURES."

    X_e'S BOUNDARY: THE PROSE AND THE FIGURE DISAGREE, and the figure wins.
    Taken literally, "outside the structures" would exclude the pipe that
    lies under a structure but outboard of its connectors -- which for
    EA-SB is the TAPER, where strain concentrates. Figs 27 and 38 show
    X_e's arrow running right up to where X_c begins, so that pipe is
    inside X_e.

    MEASURED, not assumed. Bucketing the under-structure pipe separately
    and comparing both readings against the reference's own X_e:

        case        X_e abutting X_c      X_e outside the body
        F1 Case 1   1.136%  (-19.4%)      0.728%  (-48.4%)
        F2 Case 1   1.304%  (-10.1%)      0.808%  (-44.3%)
        F2 Case 3   1.432%  (-10.5%)      0.881%  (-45.0%)

    Three cases agree far better with the abutting reading, and the fourth
    cannot tell them apart -- F2 Case 2 puts its connectors at the body's
    own edges, so there is no under-structure pipe to argue over. `body` is
    accepted and ignored, kept so the alternative stays easy to re-measure.
    """
    if min(abs(s_mid - c) for c in conn) <= AT_CONNECTOR_OD * D:
        return 'X_c'
    if len(conn) > 1 and min(conn) < s_mid < max(conn):
        return 'X_i'
    return 'X_e'


def region_peaks(position, problem, s_max, body=None):
    """{region: peak |strain|} for one solved position, inside the band."""
    xy = {i: s for (i, s, _y) in problem.nodes}
    conn = sorted(xy[n1] for (_i, n1, _n2, _t, _l, _s) in problem.connectors)
    ends = {i: sorted((xy[a], xy[b]))
            for (i, a, b, _o, _l) in problem.elements}
    out = {r: 0.0 for r in REGIONS}
    for (i, _sm, e) in position.result.strains:
        a, b = ends.get(i, (0.0, 0.0))
        mid = 0.5 * (a + b)
        if mid + position.shift >= s_max:       # the D6 tip artefact
            continue
        out[classify(mid, conn, body)] = max(
            out[classify(mid, conn, body)], abs(e))
    return out, (conn[0], conn[-1])


def run_case(name, R, spacing, tension_mt, L_top_D, step_OD,
             system='F2'):
    p = PAPER[name]
    ils = build(p['P_c1_D'], p['kT'], L_top_D, system)
    sc, L_comp, recs, _junc, probs, positions, done = slide.passage(
        arch_id='none', ils=ils, R=R, spacing=spacing,
        tension_mt=tension_mt, step=step_OD * D, verbose=False,
        # The S in a PS layout is emitted only under this opt-in --
        # G9's narrow route, with `solve.passage` enforcing the tie.
        emit_unenforced_conn_types=frozenset({'S'}))
    s_max, _label = rp.zone(sc)
    # The STRUCTURE's material span, which is what X_e is keyed on.
    s_centre = sweep.start_centre(sc, L_comp)
    body = (s_centre - L_comp / 2.0, s_centre + L_comp / 2.0)

    per_pos, env = [], {r: 0.0 for r in REGIONS}
    span = None
    for pos, prob in zip(positions, probs):
        if prob is None or not pos.converged:
            continue
        got, span = region_peaks(pos, prob, s_max, body)
        per_pos.append((pos.index, pos.shift, got))
        for k in env:
            env[k] = max(env[k], got[k])
    return dict(name=name, paper=p, env=env, per_pos=per_pos, span=span,
                done=done,
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
    system = arg('--system', str, 'F2')

    print(f'EA-ST, {system} connection.  R = {R:.0f} m, '
          f'spacing = {spacing:.0f} m, {tension:.0f} MT, '
          f'L_top = {L_top_D:.0f} D (assumed, held fixed)')
    if system != 'F2':
        print(f'  *** Paper 2 publishes F1 and F2 ONLY. {system} has no '
              f'published values, so the\n      columns below are a '
              f'PREDICTION and the differences are against F2\'s numbers '
              f'for\n      the same geometry, which is a comparison between '
              f'two of OUR runs -- not validation.')

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for name in ('Case 1', 'Case 2'):
            r = run_case(name, R, spacing, tension, L_top_D, step_OD,
                         system)
            p, env = r['paper'], r['env']
            print(f'\n=== {name}: P_c1 = {p["P_c1_D"]:.0f} D, kT = {p["kT"]}, '
                  f'L_comp = {r["L_comp"]:.3f} m, '
                  f'{r["n_ok"]}/{r["n"]} positions converged, '
                  f'{100 * r["done"].fraction:.0f}% of travel ===')
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
                      f'{100 * g["X_i"]:9.3f}%{100 * g["X_e"]:9.3f}%'
                      f'{mark}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

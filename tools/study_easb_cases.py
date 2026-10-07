#!/usr/bin/env python3
"""study_easb_cases.py -- EA-SB against the published F1 and F2 cases.

NOT `study_easb.py`, which is a different study -- that one takes ILS-EASB
through every connection system to exercise the ZERO-LENGTH connector. This
file runs the reference's four dimensioned cases and compares the numbers.

    python3 tools/study_easb_cases.py [--R 85] [--spacing 9] [--tension 120]
                                [--step 1] [--case "F2 Case 2"]

EA-SB is a structure the pipe rides ON: it holds the pipe off the rollers by
`P_v` and is fastened down by connectors. Its parameters are the reference's
own, and `component_spec.BaseStructure` carries them under the same names:

    P_l1   length of the deep section
    P_l2   taper length at each end
    P_v    offset depth -- how far the contact surface sits below the pipe
           CENTRELINE, so the pipe is held off the arc by `P_v - OD/2`
    P_c1   span between the two connectors (F2 only; F1 has one, centred)
    kB     the frame's stiffness as a multiple of the pipeline's

THE DEFAULT IS NOT THE PAPER'S. `BaseStructure` ships `P_v = 1.6256 m`,
which is 4 D and gives a 3.5 D lift; every case below is 2 D, a 1.5 D lift.
Running the archetype as-shipped is a different, much more severe case than
anything the reference published, and the strains say so.

THE THREE REGIONS are Fig. 38's, and the same ones EA-ST uses -- the
classifier is imported from `study_f2` rather than restated, so the two
studies cannot drift apart on what X_c means:

    X_c   the pipe AT a connector. The peak.
    X_i   between the two connectors, shielded by the frame spanning over
          it. F1 has a single connector, so it has no X_i and the reference
          does not tabulate one.
    X_e   outboard of the connectors.

WHAT IS NOT HERE. The F1D and F2D systems add `D` connectors -- a deadband
that opens and shuts -- and the passage solver implements type F only. G9
says a D case is REFUSED rather than approximated by an F, because the joint
type selects which DOF is tied and substituting F ties all of them, silently
answering a different question. `kernel.problem_connectors` raises on any
non-F type, so those cases cannot be run here by accident.
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
from study_f2 import REGIONS, region_peaks            # noqa: E402

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'
D = 0.4064

# Table values are in DIAMETERS; kB is dimensionless. `X_i` is None where
# the reference does not tabulate one -- F1 has a single connector, so there
# is no 'between' to report.
CASES = {
    'F1 Case 1': dict(system='F1', P_l1=5.0, P_l2=2.5, P_v=2.0, kB=3.2,
                      P_c1=None, X_c=2.30, X_i=None, X_e=1.41),
    'F2 Case 1': dict(system='F2', P_l1=10.0, P_l2=2.5, P_v=2.0, kB=2.5,
                      P_c1=5.0, X_c=2.24, X_i=0.086, X_e=1.45),
    'F2 Case 2': dict(system='F2', P_l1=10.0, P_l2=2.5, P_v=2.0, kB=3.1,
                      P_c1=10.0, X_c=2.40, X_i=0.086, X_e=1.52),
    'F2 Case 3': dict(system='F2', P_l1=15.0, P_l2=2.5, P_v=2.0, kB=3.1,
                      P_c1=10.0, X_c=2.53, X_i=0.085, X_e=1.60),
}


def build(c, system=None):
    """ILS-EASB re-dimensioned, by editing the archetype's own definition."""
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        FIXTURE.read_text())['archetypes']}['ILS-EASB']['definition'])
    # A `--system` override replaces the case's own layout. Paper 2
    # publishes F1 and F2 only, so anything else is PREDICTION and the tool
    # says so rather than printing a difference that looks like validation.
    spec['ils']['connection_system'] = system or c['system']
    comp = spec['components'][0]
    comp['P_l1'] = c['P_l1'] * D
    comp['P_l2'] = c['P_l2'] * D
    comp['P_v'] = c['P_v'] * D
    comp['kB_ratio'] = c['kB']
    if c['P_c1'] is not None:
        comp['P_c1'] = c['P_c1'] * D
    return ils_builder.build_ils(spec)


def run_case(name, R, spacing, tension_mt, step_OD, system=None):
    c = CASES[name]
    ils = build(c, system)
    sc, L_comp, recs, _junc, probs, positions, done = slide.passage(
        arch_id='none', ils=ils, R=R, spacing=spacing,
        tension_mt=tension_mt, step=step_OD * D, verbose=False,
        # A PS layout puts a SKEWED 'S' at slot 4, which the mesher refuses
        # by default under G9. This is the narrow opt-in: the mesher emits
        # the joint and `solve.passage` enforces it, rebuilding its
        # co-rotating frame every Newton iteration. Verified before use --
        # one skewed row resolved, one applied -- so the tie is enforced and
        # not quietly dropped.
        emit_unenforced_conn_types=frozenset({'S'}))
    s_max, _lbl = rp.zone(sc)
    s_centre = sweep.start_centre(sc, L_comp)
    body = (s_centre - L_comp / 2.0, s_centre + L_comp / 2.0)

    env, span, per_pos = {r: 0.0 for r in REGIONS}, None, []
    for pos, prob in zip(positions, probs):
        if prob is None or not pos.converged:
            continue
        got, span = region_peaks(pos, prob, s_max, body)
        per_pos.append((pos.index, pos.shift, got))
        for k in env:
            env[k] = max(env[k], got[k])
    n_ok = sum(1 for r in recs if r.converged)
    reach = max((r.shift for r in recs if r.converged), default=0.0)
    return dict(name=name, case=c, done=done, env=env, span=span, L_comp=L_comp,
                n=len(positions), n_ok=n_ok, reach=reach, per_pos=per_pos,
                full=(n_ok == len(positions)))


def main() -> int:
    def arg(flag, cast, default):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    R = arg('--R', float, 85.0)
    spacing = arg('--spacing', float, 9.0)
    # 100 mT, NOT 120. Paper 2 states `Pipeline Tension 100 mT` in all three
    # of its parameter blocks -- EA-ST (Sec. VII.A, TABLE IX), EA-SB
    # (Sec. VIII.A) and the branch study -- and every Paper 2 number in the
    # ledger before 7 Oct 2026 was run at 120, a fifth too much. Found by
    # reading the paper once it was supplied, never by a check, because
    # nothing in the repo knew what the right value was.
    tension = arg('--tension', float, 100.0)
    step_OD = arg('--step', float, 1.0)
    only = arg('--case', str, None)
    system = arg('--system', str, None)
    names = [only] if only else list(CASES)

    print(f'EA-SB.  R = {R:.0f} m, spacing = {spacing:.0f} m, '
          f'{tension:.0f} MT, sweep step = {step_OD:g} x OD'
          + (f', system OVERRIDDEN to {system}' if system else ''))
    if system:
        print(f'  *** Paper 2 publishes F1 and F2 ONLY. {system} has no '
              f'published values, so the X_c / X_i / X_e\n      columns are '
              f'a PREDICTION; the paper columns below belong to the case\'s '
              f'OWN system\n      and the differences against them are NOT '
              f'validation.')
    print(f'\n{"case":11s}{"sys":>5s}{"P_l1":>6s}{"P_l2":>6s}{"P_c1":>6s}'
          f'{"P_v":>5s}{"kB":>6s}   {"X_c":>17s}{"X_i":>17s}{"X_e":>17s}'
          f'   passage')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for name in names:
            r = run_case(name, R, spacing, tension, step_OD, system)
            c, env = r['case'], r['env']

            def cell(key):
                ref = c[key]
                got = 100 * env[key]
                if ref is None:
                    # L097. An F1 layout has ONE connector, so there is no
                    # interior between two of them -- the region does not
                    # exist, which is also why the paper tabulates none. The
                    # envelope over an empty region comes back 0.0, and
                    # printing that as `0.000%` reads as a MEASURED zero
                    # strain. A dash means not measured; it never means zero.
                    return f'{"--":>8s}  (n/a)'
                return f'{got:8.3f}%{(got - ref) / ref * 100:+7.1f}%'

            pc1 = f'{c["P_c1"]:.0f}D' if c['P_c1'] else '--'
            reach = ('full' if r['full']
                     else f'{r["reach"]:.1f}/{r["reach"] + 0.0:.0f}m'
                     if False else f'{r["n_ok"]}/{r["n"]}')
            print(f'{name:11s}{c["system"]:>5s}{c["P_l1"]:5.0f}D'
                  f'{c["P_l2"]:5.1f}D{pc1:>6s}{c["P_v"]:4.0f}D{c["kB"]:6.2f}'
                  f'   {cell("X_c"):>17s}{cell("X_i"):>17s}'
                  f'{cell("X_e"):>17s}   {reach}')
            if not r['full']:
                print(f'{"":11s}reference X_c {c["X_c"]}%  X_i '
                      f'{c["X_i"] if c["X_i"] is not None else "--"}  X_e '
                      f'{c["X_e"]}%   -- PASSAGE TRUNCATED at shift '
                      f'{r["reach"]:.3f} m, so the envelope is a LOWER BOUND')
            else:
                print(f'{"":11s}reference X_c {c["X_c"]}%  X_i '
                      f'{c["X_i"] if c["X_i"] is not None else "--"}  X_e '
                      f'{c["X_e"]}%')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

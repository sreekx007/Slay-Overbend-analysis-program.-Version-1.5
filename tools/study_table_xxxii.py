#!/usr/bin/env python3
"""study_table_xxxii.py -- Paper 1 TABLE XXXII and XXXIII: shroud L1 and L2.

    python3 tools/study_table_xxxii.py [--R 70] [--tension 100] [--case S2-7]

WHY THIS IS THE TABLE WORTH RUNNING NEXT. It contains a SECOND dual-roller
transition, and a cleaner one than TABLE XXIII's:

    S2-6   L1 = 10 D   V = 2 D   1.23 pct    single-roller contact
    S2-7   L1 = 25 D   V = 2 D   0.66 / 0.55 single -> DUAL during passage
    S2-8   L1 = 50 D   V = 2 D   0.59 pct    always dual-roller

Peak strain HALVES as the shroud grows long enough to span two roller bays.
Same mechanism the paper credits for TABLE XXIII's saturation, which this
program reproduces in character but not in degree.

AND IT ISOLATES THAT MECHANISM FROM L100. A shroud steps no section -- the
pipe section runs straight through one, which is why it gets regions rather
than junctions -- so its elements are `owner='pipeline'` throughout and the
contact chain never had the hole that L100 fixed. If the drop reproduces
here, the residual TABLE XXIII gap is about something else. If it does not,
the two failures share a cause that is NOT L100.

S2-1/2/3 are the control: L1 from 2.5 D to 10 D at V = 1 D, where the paper
finds strain FLAT (0.78 / 0.75 / 0.76). A trend that should not move is as
informative as one that should, and it is cheap.

THE CONFIGURATION IS NOT STATED IN THE TABLE and is taken by cross-reference
rather than assumed: S2-3 (10D, 5D, 1.0D) reads 0.76 pct and S2-6 (10D, 5D,
2.0D) reads 1.23, which are exactly TABLE XXXI's R = 70 m / 100 MT rows at
V = 1.0 D and 2.0 D. So TABLE XXXII is that configuration.

TWO OF THESE ARE ALREADY MEASURED. S2-3 and S2-6 are the R=70/T=100 V=1.0D
and V=2.0D rows of the V sweep, where we read -39.9 and -73.4 pct -- the
worst agreement anywhere in the shroud study. They are re-run here anyway so
the L1 trend is one consistent set.
"""

from __future__ import annotations

import collections
import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))

from profile_status import status            # noqa: E402
D = 0.4064

# TABLE XXXII, plus S2-4 from TABLE XXXIII. `dual` is the paper's second
# value where it reports one for the double-roller part of the passage.
CASES = (
    dict(case='S2-1', L1=2.5,  L2=2.0, V=1.0, x2=0.78, dual=None, table='XXXII'),
    dict(case='S2-2', L1=4.0,  L2=5.0, V=1.0, x2=0.75, dual=None, table='XXXII'),
    dict(case='S2-3', L1=10.0, L2=5.0, V=1.0, x2=0.76, dual=None, table='XXXII'),
    dict(case='S2-4', L1=10.0, L2=1.0, V=1.0, x2=0.79, dual=None, table='XXXIII'),
    dict(case='S2-6', L1=10.0, L2=5.0, V=2.0, x2=1.23, dual=None, table='XXXII'),
    dict(case='S2-7', L1=25.0, L2=2.0, V=2.0, x2=0.66, dual=0.55, table='XXXII'),
    dict(case='S2-8', L1=50.0, L2=2.0, V=2.0, x2=0.59, dual=None, table='XXXII'),
)


def emit(c, R, tension, spacing, out):
    stem = out / f'xxxii_{c["case"]}'
    cmd = [sys.executable, str(REPO / 'tools' / 'emit_profile.py'),
           '--archetype', 'ILS-SH', '--R', str(R), '--spacing', str(spacing),
           '--tension', str(tension),
           '--V', f'{c["V"] * D:.6f}', '--L1', f'{c["L1"] * D:.6f}',
           '--L2', f'{c["L2"] * D:.6f}',
           '--out', str(out), '--case-id', stem.name]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    return stem, r


def read(stem):
    """Per-region peak and the body moment, from the artifact.

    THE SECTIONS TABLE CANNOT TELL YOU WHETHER THE PASSAGE FINISHED, and the
    filter below is why: a diverged position is the one row carrying
    `in_band` false and `converged` false, so reading the peaks drops exactly
    the evidence that the peaks are partial. The case context on the
    geometry table carries it instead, and `status` is where that is read
    (L101).
    """
    f = Path(str(stem) + '.sections.csv')
    if not f.exists():
        return None
    pk = collections.defaultdict(float)
    el = collections.defaultdict(set)
    bm = 0.0
    for r in csv.DictReader(open(f)):
        if r['owner'] != 'pipeline' or r['in_band'] not in ('1', 'True', 'true'):
            continue
        if r.get('moment'):
            bm = max(bm, abs(float(r['moment'])))
        g = r['region']
        if g:
            pk[g] = max(pk[g], abs(float(r['strain'])))
            el[g].add(r['element'])
    return dict(peak=pk, el=el, bm=bm, status=status(stem))


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    R = arg('--R', float, 70.0)
    tension = arg('--tension', float, 100.0)
    spacing = arg('--spacing', float, 9.0)
    only = arg('--case', str, None)
    out = Path(arg('--out', str, str(REPO / 'docs' / 'profiles')))
    out.mkdir(parents=True, exist_ok=True)

    print(f'Paper 1 TABLE XXXII and XXXIII -- shroud L1 and L2, '
          f'R = {R:.0f} m, {tension:.0f} MT, {spacing:.0f} m spacing\n')
    print(f'{"case":6s} {"L1":>6s} {"L2":>5s} {"V":>5s}  {"ours X2":>9s} '
          f'{"paper":>7s} {"d%":>8s}  {"n(X2)":>5s} {"peak":>5s} '
          f'{"BM kN.m":>8s} {"swept":>6s}')
    got, incomplete = {}, []
    for c in CASES:
        if only and c['case'] != only:
            continue
        stem, proc = emit(c, R, tension, spacing, out)
        d = read(stem)
        if d is None:
            tail = (proc.stderr or proc.stdout or '').strip().splitlines()
            print(f'{c["case"]:6s} FAILED: {tail[-1][:70] if tail else "?"}')
            continue
        x2 = 100 * d['peak'].get('X2', 0.0)
        n = len(d['el'].get('X2', ()))
        top = max(d['peak'], key=d['peak'].get) if d['peak'] else '-'
        st = d['status']
        # A PARTIAL TRAVERSE GETS NO PERCENTAGE. The number is not a worse
        # estimate of the paper's quantity, it is a different quantity --
        # the worst strain over the part of the passage that solved -- and
        # printing a difference against the paper for it is what let five of
        # these cases be read as results (L101).
        if st.complete is True:
            got[c['case']] = x2
            delta = f'{100 * (x2 / c["x2"] - 1):+7.1f}%' if n else '      --'
        else:
            delta = '   VOID'
        print(f'{c["case"]:6s} {c["L1"]:5.1f}D {c["L2"]:4.1f}D {c["V"]:4.1f}D  '
              f'{x2:8.4f}% {c["x2"]:6.2f}% {delta}  {n:5d} {top:>5s} '
              f'{d["bm"] / 1000:8.1f} {st.flag():>6s}', flush=True)
        if st.complete is not True:
            incomplete.append(st)

    # THE TWO TRENDS ARE THE RESULT, so they are computed and not left to a
    # reader lining up rows by eye.
    print()
    if incomplete:
        print(f'  {len(incomplete)} of {len(CASES)} PASSAGES DID NOT FINISH. '
              f'Their rows above are a maximum over part of the traverse and '
              f'carry no difference against the paper:')
        for st in incomplete:
            print(f'    {st}')
        print('  The trends below are computed from the COMPLETE cases only, '
              'and a trend missing cases is not the trend.\n')
    flat = [got.get(k) for k in ('S2-1', 'S2-2', 'S2-3')]
    if all(flat):
        spread = (max(flat) - min(flat)) / max(flat)
        print(f'  V = 1 D, L1 2.5 -> 10 D : ours {flat[0]:.3f} / {flat[1]:.3f} '
              f'/ {flat[2]:.3f}, spread {100 * spread:.1f}%')
        print(f'                            paper 0.78 / 0.75 / 0.76, '
              f'spread 3.8%  -- FLAT, and should stay flat')
    dual = [got.get(k) for k in ('S2-6', 'S2-7', 'S2-8')]
    if all(dual):
        print(f'\n  V = 2 D, L1 10 -> 25 -> 50 D : ours {dual[0]:.3f} / '
              f'{dual[1]:.3f} / {dual[2]:.3f}')
        print(f'                                paper 1.23 / 0.66 / 0.59')
        drop = 100 * (dual[2] / dual[0] - 1)
        print(f'  ours drops {drop:+.1f}% from 10 D to 50 D; '
              f'paper drops {100 * (0.59 / 1.23 - 1):+.1f}%')
        if drop < -25.0:
            print('  THE DUAL-ROLLER DROP IS REPRODUCED.')
        elif drop < -5.0:
            print('  A drop, but much weaker than published.')
        else:
            print('  NOT reproduced -- strain does not fall as the shroud '
                  'spans two bays.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

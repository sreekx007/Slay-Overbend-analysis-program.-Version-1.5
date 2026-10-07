#!/usr/bin/env python3
"""study_table_xxxi.py -- Paper 1 TABLE XXXI and XXXIV: shroud offset depth V.

    python3 tools/study_table_xxxi.py [--out DIR] [--config A]

TWELVE CASES ACROSS THREE CONFIGURATIONS, each sweeping V. This is the
shroud's own parameter -- how far its surface stands below the pipe -- and
the paper's strain rises monotonically with it in every configuration.

    A   R = 85, 100 MT, L1 = 10 D, L2 = 2.5 D    V = 0.75 .. 3.00 D (6)
    B   R = 70, 120 MT, L1 = 5 D,  L2 = 2.5 D    V = 1.00 .. 2.00 D (3)
    C   R = 70, 100 MT, L1 = 10 D, L2 = 5 D      V = 1.00 .. 2.00 D (3)

STRAIN IS REPORTED BY REGION, after TABLE XXIX: X1 is the catenary taper and
the pipe beyond it, X2/X3/X4 the deep section in thirds from the catenary
side, X5 the vessel taper and beyond. X2 is the paper's peak in every case
it ran. X3 and X4 are published only for configuration A, which is TABLE
XXXIV.

CONFIGURATION C IS ALSO TABLE XXXII's S2-3 AND S2-6, deliberately: the same
geometry appears in both tables and must give the same number from both
tools, which is a cross-check that costs nothing to keep.

RE-RUN BECAUSE OF L105 AND L106.
"""

from __future__ import annotations

import collections
import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))

from profile_status import status                          # noqa: E402

D = 0.4064

CONFIGS = {
    'A': dict(R=85.0, tension=100.0, L1=10.0, L2=2.5, table='XXXI/XXXIV',
              cases=((0.75, 0.62, 0.42, 0.35), (1.00, 0.70, 0.55, 0.43),
                     (1.50, 0.95, 0.75, 0.58), (2.00, 1.20, 0.88, 0.58),
                     (2.50, 1.51, 1.07, 0.62), (3.00, 1.80, 1.20, 0.67))),
    'B': dict(R=70.0, tension=120.0, L1=5.0, L2=2.5, table='XXXI',
              cases=((1.00, 0.808, None, None), (1.50, 0.970, None, None),
                     (2.00, 1.15, None, None))),
    'C': dict(R=70.0, tension=100.0, L1=10.0, L2=5.0, table='XXXI',
              cases=((1.00, 0.76, None, None), (1.50, 1.03, None, None),
                     (2.00, 1.23, None, None))),
}


def emit(cfg, V, out, stem):
    cmd = [sys.executable, str(REPO / 'tools' / 'emit_profile.py'),
           '--archetype', 'ILS-SH', '--R', str(cfg['R']),
           '--spacing', '9.0', '--tension', str(cfg['tension']),
           '--V', f'{V * D:.6f}', '--L1', f'{cfg["L1"] * D:.6f}',
           '--L2', f'{cfg["L2"] * D:.6f}',
           '--out', str(out), '--case-id', stem]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))


def read(stem):
    """Per-region peak and the body moment, from the artifact.

    The sections table cannot say whether the passage finished -- the
    diverged position is the one row `in_band` drops -- so completion is
    read from the case context instead (L101).
    """
    f = Path(str(stem) + '.sections.csv')
    if not f.exists():
        return None
    pk = collections.defaultdict(float)
    el = collections.defaultdict(set)
    bm = 0.0
    for r in csv.DictReader(open(f)):
        if r['owner'] != 'pipeline' or r['in_band'] not in ('1', 'True',
                                                            'true'):
            continue
        if r.get('moment'):
            bm = max(bm, abs(float(r['moment'])))
        if r['region']:
            pk[r['region']] = max(pk[r['region']], abs(float(r['strain'])))
            el[r['region']].add(r['element'])
    # L097: a region that holds NO ELEMENTS at this mesh must not print
    # 0.0000, which reads as a measurement of zero strain rather than as the
    # absence of anything to measure. Config B's L1 = 5 D divides into
    # thirds of 0.677 m against an element of 0.813 m, so X3 is empty.
    return dict(peak=pk, el=el, bm=bm, status=status(stem))


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    out = Path(arg('--out', str, str(REPO / 'docs' / 'profiles')))
    only = arg('--config', str, None)
    out.mkdir(parents=True, exist_ok=True)

    print('Paper 1 TABLE XXXI and XXXIV -- shroud offset depth V, '
          '9 m spacing\n')
    bad = []
    for name, cfg in CONFIGS.items():
        if only and name != only:
            continue
        print(f'--- config {name}: R = {cfg["R"]:.0f} m, '
              f'{cfg["tension"]:.0f} MT, L1 = {cfg["L1"]:.1f} D, '
              f'L2 = {cfg["L2"]:.1f} D   ({cfg["table"]})')
        print(f'{"V":>6s}  {"ours X2":>9s} {"paper":>7s} {"d%":>8s}  '
              f'{"ours X3":>9s} {"paper":>7s}  {"ours X4":>9s} '
              f'{"paper":>7s}  {"BM kN.m":>8s} {"swept":>6s}')
        for V, p2, p3, p4 in cfg['cases']:
            stem = out / f'xxxi_{name}_V{V:.2f}'
            proc = emit(cfg, V, out, stem.name)
            d = read(stem)
            if d is None:
                tail = (proc.stderr or proc.stdout or '').strip().splitlines()
                print(f'{V:5.2f}D  FAILED: {tail[-1][:60] if tail else "?"}')
                continue
            st = d['status']
            def _cell(g):
                n = len(d['el'].get(g, ()))
                return ('      --' if n == 0
                        else f'{100 * d["peak"].get(g, 0.0):8.4f}%')
            x2 = 100 * d['peak'].get('X2', 0.0)
            c3, c4 = _cell('X3'), _cell('X4')
            # No difference against the paper for a partial traverse (L101).
            delta = (f'{100 * (x2 / p2 - 1):+7.1f}%' if st.complete is True
                     else '   VOID')
            f3 = f'{p3:6.2f}%' if p3 is not None else '     --'
            f4 = f'{p4:6.2f}%' if p4 is not None else '     --'
            print(f'{V:5.2f}D  {x2:8.4f}% {p2:6.3f}% {delta}  '
                  f'{c3:>9s} {f3}  {c4:>9s} {f4}  '
                  f'{d["bm"] / 1000:8.1f} {st.flag():>6s}', flush=True)
            if st.complete is not True:
                bad.append((name, V, st))
        print()
    for name, V, st in bad:
        print(f'  config {name} V={V:.2f}D: {st}')
    if bad:
        print(f'\n  {len(bad)} PASSAGE(S) DID NOT FINISH -- those rows are a '
              f'maximum over part of the traverse and carry no difference '
              f'against the paper.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

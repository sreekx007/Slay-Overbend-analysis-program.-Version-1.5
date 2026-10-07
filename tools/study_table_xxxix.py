#!/usr/bin/env python3
"""study_table_xxxix.py -- Paper 1 TABLE XXXIX and XLI: a thick pipe inside
the shroud.

    python3 tools/study_table_xxxix.py [--out DIR] [--table XXXIX]

R = 85 m, 100 MT. The shroud is fixed at L1 = 10 D, L2 = 2.5 D, V = 1 D in
both tables, and the thick pipe inside it is what varies:

    XXXIX   its LENGTH -- 5 D and 10 D, against the shroud-only baseline
    XLI     its POSITION -- a 2.5 D body at the catenary third, the midspan
            and the vessel third of the deep section

BOTH BODIES LIVE IN ONE ARCHETYPE, which is why this needed the dotted
dimension names `emit_profile` now takes: `--tp-l-comp` and `--tp-centre-x`
reach GD-TP, while `--v`, `--l1` and `--l2` reach GD-SH. Editing
`components[0]` would have silently re-dimensioned the shroud and produced a
plausible number for a geometry nobody asked for.

READ XLI's REGION LABELS WITH CARE. The paper's finding is that the peak
stays at X2 wherever the body sits, and that putting it AT X2 is the worst
case because the stiffness discontinuity lands where curvature is highest.
Our X1/X2 boundary and the paper's are not guaranteed to agree to the
centimetre -- at 10 D the thick body's junction falls exactly on ours, which
is the ambiguity TABLE XXXIX Case 2 already carries -- so the region a peak
is LABELLED with is reported alongside its value rather than instead of it.
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
R, TENSION = 85.0, 100.0
SH = dict(V=1.0, L1=10.0, L2=2.5)        # the shroud, fixed, in diameters

# (label, thick length in D, thick centre offset in D, paper X2, paper X4,
#  paper BM kN.m). `None` length means shroud only.
TABLES = {
    'XXXIX': (
        ('baseline', None, 0.0, 0.70,  0.43, None),
        ('5 D',      5.0,  0.0, 0.952, None, 1405),
        ('10 D',     10.0, 0.0, 1.26,  None, 1555),
    ),
    'XLI': (
        ('baseline',          None, 0.0,            0.70,  0.35, None),
        ('X2 catenary third', 2.5,  -SH['L1'] / 3,  0.901, 0.49, 1362),
        ('X3 midspan',        2.5,  0.0,            0.744, 0.59, 1310),
        ('X4 vessel third',   2.5,  +SH['L1'] / 3,  0.744, 0.57, 1271),
    ),
}


def emit(L_tp, dx, out, stem):
    arch = 'ILS-SH' if L_tp is None else 'ILS-SHTP'
    cmd = [sys.executable, str(REPO / 'tools' / 'emit_profile.py'),
           '--archetype', arch, '--R', str(R), '--spacing', '9.0',
           '--tension', str(TENSION),
           '--V', f'{SH["V"] * D:.6f}', '--L1', f'{SH["L1"] * D:.6f}',
           '--L2', f'{SH["L2"] * D:.6f}',
           '--out', str(out), '--case-id', stem]
    if L_tp is not None:
        cmd += ['--tp-l-comp', f'{L_tp * D:.6f}',
                '--tp-centre-x', f'{dx * D:.6f}']
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))


def read(stem):
    """Per-region peak, overall peak and its region, and the body moment."""
    f = Path(str(stem) + '.sections.csv')
    if not f.exists():
        return None
    pk = collections.defaultdict(float)
    el = collections.defaultdict(set)
    top = (0.0, '-')
    bm = dict(body=0.0, pipe=0.0)
    for r in csv.DictReader(open(f)):
        if r['in_band'] not in ('1', 'True', 'true'):
            continue
        if r['owner'] != 'pipeline':
            continue
        eps = abs(float(r['strain']))
        # THE MOMENT IS READ ON THE THICK BODY, as TABLE XXXIX reports it.
        # A shroud owns a contact surface and no section, so `section_owner`
        # is what tells the thick pipe apart -- `owner` would not.
        key = 'pipe' if r.get('section_owner', 'pipe') == 'pipe' else 'body'
        if r.get('moment'):
            bm[key] = max(bm[key], abs(float(r['moment'])))
        if r['region']:
            pk[r['region']] = max(pk[r['region']], eps)
            el[r['region']].add(r['element'])
            if eps > top[0]:
                top = (eps, r['region'])
    return dict(peak=pk, el=el, top=top, bm=bm, status=status(stem))


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    out = Path(arg('--out', str, str(REPO / 'docs' / 'profiles')))
    only = arg('--table', str, None)
    out.mkdir(parents=True, exist_ok=True)

    for name, cases in TABLES.items():
        if only and name != only:
            continue
        print(f'\nPaper 1 TABLE {name} -- thick pipe inside the shroud, '
              f'R = {R:.0f} m, {TENSION:.0f} MT, 9 m spacing')
        print(f'shroud fixed at L1 = {SH["L1"]:.1f} D, L2 = {SH["L2"]:.1f} D, '
              f'V = {SH["V"]:.1f} D\n')
        print(f'{"case":20s} {"ours X2":>9s} {"paper":>7s} {"d%":>8s}  '
              f'{"overall":>9s} {"in":>4s}  {"ours X4":>9s} {"paper":>7s}  '
              f'{"BM body":>8s} {"paper":>7s} {"d%":>8s} {"swept":>6s}')
        starred = False
        for label, L_tp, dx, p2, p4, pbm in cases:
            stem = out / f'{name.lower()}_{label.split()[0].lower()}'
            proc = emit(L_tp, dx, out, stem.name)
            d = read(stem)
            if d is None:
                tail = (proc.stderr or proc.stdout or '').strip().splitlines()
                print(f'{label:20s} FAILED: {tail[-1][:60] if tail else "?"}')
                continue
            st = d['status']
            # L097: a region holding no elements must not print 0.0000,
            # which reads as a measurement of zero strain. At 10 D the thick
            # body's junction lands on our X1/X2 boundary and X2 empties.
            def _cell(g):
                return ('      --' if not d['el'].get(g)
                        else f'{100 * d["peak"].get(g, 0.0):8.4f}%')
            x2 = 100 * d['peak'].get('X2', 0.0)
            has2 = bool(d['el'].get('X2'))
            c2, c4 = _cell('X2'), _cell('X4')
            # No difference against the paper for a partial traverse (L101).
            # WHERE OUR X2 IS EMPTY the paper's X2 value has no counterpart
            # in our partition, and the OVERALL peak is the like-for-like
            # number -- the same piece of pipe and the same mechanical
            # feature, counted into a different region by a boundary that
            # falls a few centimetres elsewhere. Compared on that, and said.
            ref = x2 if has2 else 100 * d['top'][0]
            dd = (f'{100 * (ref / p2 - 1):+7.1f}%' if st.complete is True
                  else '   VOID')
            if not has2 and st.complete is True:
                dd += '*'
                starred = True
            body = d['bm']['body'] or d['bm']['pipe']
            dm = (f'{100 * (body / 1000.0 / pbm - 1):+7.1f}%'
                  if pbm and st.complete is True else '      --')
            f4 = f'{p4:6.2f}%' if p4 is not None else '     --'
            fbm = f'{pbm:7d}' if pbm else '     --'
            print(f'{label:20s} {c2:>9s} {p2:6.3f}% {dd:>9s}  '
                  f'{100 * d["top"][0]:8.4f}% {d["top"][1]:>4s}  '
                  f'{c4:>9s} {f4}  {body / 1000:8.1f} {fbm} {dm} '
                  f'{st.flag():>6s}', flush=True)
        if starred:
            print('\n  * our X2 holds NO ELEMENTS in that row, so the paper\'s '
                  'X2 has no counterpart in our\n    partition and the '
                  'difference is taken on the OVERALL peak instead. Same '
                  'steel,\n    same feature; a boundary a few centimetres '
                  'elsewhere.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

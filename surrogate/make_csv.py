#!/usr/bin/env python3
"""make_csv.py -- the CSV, generated FROM the results document.

    python3 surrogate/make_csv.py

THE DOCUMENT IS THE CONTRACT, NOT THIS FILE. Section 10 of
`RESULTS_plain_surrogate_dataset.md` lists the columns, in groups and in
order, and names the three that have to be computed. This script PARSES that
section and emits exactly what it says. It does not carry its own column
list, because two lists drift and then the document is a story about a table
nobody produced from it.

So it refuses rather than guesses:

  a name in the document that no row carries, and that the document has not
  marked as never-written, is an ERROR;
  a key in `plain_runs.jsonl` that the document does not list is an ERROR --
  a column cannot be dropped silently;
  a computed column the document names that this script does not implement
  is an ERROR, and so is the reverse.

THE ONE UNIT TRAP, and it is the same family as two already in the register.
`peak_strain`, `start_strain` and `eps_*_env` are FRACTIONS. `ref_strain_pct`
is a PERCENT, because it is transcribed from the papers' own tables, which
print percent. Subtracting one from the other gives nonsense that looks
plausible. Both are flagged in the sidecar and the document says so.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD = HERE / 'RESULTS_plain_surrogate_dataset.md'
JSONL = HERE / 'plain_runs.jsonl'
CSV_OUT = HERE / 'plain_dataset.csv'
SCHEMA_OUT = HERE / 'plain_dataset.csv.schema.json'

SECTION = '## 10. Columns, for the CSV step'
STATIONS = ('SR1', 'SR2', 'SR3', 'SR4', 'SR5', 'SR6', 'SR7',
            'VR1', 'VR2', 'VR3', 'VR4', 'VR5')

G = 9806.65              # N per metric tonne force, as the runner uses
SIGMA_Y0 = 360e6         # `j2` first yield, Pa

# Names the document lists that the runner writes only on an exception. No
# case raised one, so the column is emitted empty rather than dropped: a
# reader comparing the document to the file must find every name.
NEVER_WRITTEN = {'traceback'}


# ---------------------------------------------------------------------------
# reading the contract out of the document
# ---------------------------------------------------------------------------

def _section(text: str, head: str) -> str:
    """The named section, or a refusal in this script's own words.

    `str.index` would raise a bare `ValueError: substring not found`, which
    tells a reader nothing about which document was wrong or what it was
    missing. The section heading is the contract's address; losing it is the
    one failure this script cannot work around.
    """
    i = text.find(head)
    if i == -1:
        raise SystemExit(f'no section "{head}" in the results document. The '
                         f'CSV is generated from that section, so there is '
                         f'nothing to generate from.')
    j = text.find('\n## ', i + len(head))
    return text[i:j if j != -1 else len(text)]


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip('|').split('|')]


def contract(md_text: str):
    """`(ordered column names, {group: [names]}, {computed name: definition})`.

    The per-station row is written with an ellipsis in the document because
    twenty-four names in one table cell is unreadable. It is expanded from
    `STATIONS`, and the count the document states in the group label is
    CHECKED against the expansion rather than trusted.
    """
    sec = _section(md_text, SECTION)
    groups, order, computed = {}, [], {}
    for line in sec.splitlines():
        if not line.startswith('|') or set(line) <= set('|- '):
            continue
        cells = _cells(line)
        if cells[0] in ('group', 'column'):
            continue
        names = re.findall(r'`([A-Za-z_][\w]*)`', cells[1])
        label = re.sub(r'\*\*', '', cells[0])
        if len(cells) == 3:                    # the computed-columns table
            computed[re.sub(r'\*\*|`', '', cells[0])] = cells[1]
            continue
        if '…' in cells[1] or '...' in cells[1]:
            names = ([f'eps_{s}_env' for s in STATIONS]
                     + [f's_{s}' for s in STATIONS])
        stated = re.search(r'\((\d+)\)', label)
        if stated and int(stated.group(1)) != len(names):
            raise SystemExit(
                f'group "{label}" states {stated.group(1)} fields and lists '
                f'{len(names)}. The document and its own count disagree; fix '
                f'the document, not this script.')
        groups[label] = names
        order += names
    if not order:
        raise SystemExit(f'no column table found under "{SECTION}"')
    # The computed columns are APPENDED, and that is the whole point of the
    # second table: the document says they are "added in the CSV step", so
    # they go after everything the run wrote rather than being interleaved
    # with it. A reader diffing the CSV header against `plain_runs.jsonl`
    # sees the run's own fields first, in the run's own order.
    if computed:
        groups['computed (3)' if len(computed) == 3
               else f'computed ({len(computed)})'] = list(computed)
        order += list(computed)
    dupes = [n for n in set(order) if order.count(n) > 1]
    if dupes:
        raise SystemExit(f'the document lists these columns twice: {dupes}')
    return order, groups, computed


# ---------------------------------------------------------------------------
# the computed columns. One function per name the document asks for.
# ---------------------------------------------------------------------------

def _sigma_axial(r):
    """`tension_mt x 9806.65 / A` -- membrane stress from lay tension alone.

    Section 8: the tension axis is absolute, so the same 200 MT that is
    routine on a 24 in pipe is past yield on a 6 in one."""
    return r['tension_mt'] * G / r['A']


def _axial_over_yield(r):
    return _sigma_axial(r) / SIGMA_Y0


def _tip_exceeds_peak(r):
    """Does an EXCLUDED tip roller read higher than the scored peak?

    `peak_strain` is the zone-restricted envelope (`DROP_AT_TIP = 3`, SR5 and
    beyond excluded); the per-station columns carry all twelve. True in 98%
    of rows, so the two are not on the same footing and a reader has to be
    told which rows they are."""
    if r.get('peak_strain') is None:
        return None
    tip = [r.get(f'eps_{s}_env') for s in ('SR5', 'SR6', 'SR7')]
    tip = [v for v in tip if v is not None]
    return max(tip) > r['peak_strain'] if tip else None


COMPUTED = {'sigma_axial': _sigma_axial,
            'axial_over_yield': _axial_over_yield,
            'tip_exceeds_peak': _tip_exceeds_peak}


# ---------------------------------------------------------------------------
# the sidecar
# ---------------------------------------------------------------------------

UNITS = {
    'R': ('m', 'length', 'input'), 'spacing': ('m', 'length', 'input'),
    'OD': ('m', 'length', 'input'), 't_wall': ('m', 'length', 'input'),
    'tension_mt': ('MT', 'force', 'input'),
    'step': ('m', 'length', 'setting'),
    'D_over_t': ('-', 'ratio', 'feature'),
    'curvature': ('1/m', 'curvature', 'feature'),
    'I': ('m4', 'second moment', 'feature'),
    'A': ('m2', 'area', 'feature'),
    'EI': ('N.m2', 'bending stiffness', 'feature'),
    'EA': ('N', 'axial stiffness', 'feature'),
    'eps_pure_bend': ('-', 'strain (fraction)', 'feature'),
    'spacing_over_OD': ('-', 'ratio', 'feature'),
    'peak_strain': ('-', 'strain (FRACTION)', 'target'),
    'start_strain': ('-', 'strain (FRACTION)', 'target'),
    'peak_moment': ('N.m', 'bending moment', 'target'),
    'ref_strain_pct': ('%', 'strain (PERCENT)', 'reference'),
    'sigma_axial': ('Pa', 'stress', 'feature'),
    'axial_over_yield': ('-', 'ratio', 'feature'),
    'tip_exceeds_peak': ('bool', 'flag', 'diagnostic'),
    'seconds': ('s', 'time', 'diagnostic'),
}

ABOUT = {
    'peak_strain': 'ZONE-RESTRICTED envelope over the passage, a FRACTION '
                   'not a percent. Compare with ref_strain_pct only after '
                   'multiplying by 100.',
    'ref_strain_pct': 'the validation ledger value for a block-A anchor, in '
                      'PERCENT as the papers print it. Empty for every '
                      'non-anchor row.',
    'start_strain': 'the first position -- what a single-position solve '
                    'would have reported. Equal to peak_strain in 331 of '
                    '518 rows.',
    'tip_exceeds_peak': 'an excluded tip roller (SR5-SR7) reads higher than '
                        'peak_strain. True in 510 of 518 rows.',
    'sigma_axial': 'membrane stress from lay tension alone. 6 rows exceed '
                   'j2 sigma_y0 = 360 MPa, 11 more sit above 0.8 of it.',
    'within_paper_box': 'all five inputs inside the papers published '
                        'envelope. True for 16 of 525 rows; everything else '
                        'is prediction.',
    'block': 'A anchors, B one-factor-at-a-time, C joint sample (training), '
             'D joint sample HELD OUT -- reserved before any case ran.',
    'status': "'ok', or 'failed' with a reason in `error`. Failures are "
              'rows, not omissions.',
    'traceback': 'written only when a case raises. No case did, so this '
                 'column is empty in every row.',
}


def _dtype(name, rows):
    vals = [r.get(name) for r in rows if r.get(name) is not None]
    if not vals:
        return 'str'
    v = vals[0]
    return ('bool' if isinstance(v, bool) else
            'int' if isinstance(v, int) else
            'float' if isinstance(v, float) else 'str')


def sidecar(order, groups, computed, rows, present):
    by_group = {n: g for g, names in groups.items() for n in names}
    fields = []
    for n in order:
        unit, qty, role = UNITS.get(n, ('-', 'name', 'identifier'))
        g = by_group.get(n, 'computed')
        if n in computed:
            role, g = role if n in UNITS else 'feature', 'computed'
        fields.append(dict(
            name=n, dtype=_dtype(n, rows), unit=unit, quantity=qty,
            role=role, group=g, source='computed' if n in computed else 'run',
            definition=computed.get(n), present=bool(present.get(n, True)),
            about=ABOUT.get(n)))
    return dict(schema_version=rows[0]['schema_version'],
                generated_from=MD.name, raw=JSONL.name,
                n_rows=len(rows), n_columns=len(order), fields=fields)


# ---------------------------------------------------------------------------

def fmt(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, float):
        return '' if math.isnan(v) else repr(v)
    return str(v)


def main() -> int:
    order, groups, computed = contract(MD.read_text())
    rows = [json.loads(l) for l in JSONL.read_text().splitlines() if l.strip()]
    if not rows:
        raise SystemExit(f'{JSONL.name} is empty')

    if set(computed) != set(COMPUTED):
        raise SystemExit(
            f'the document asks for computed columns {sorted(computed)} and '
            f'this script implements {sorted(COMPUTED)}. One of the two is '
            f'out of date and the CSV is not written.')

    have = set()
    for r in rows:
        have |= set(r)
    declared = set(order)
    missing = sorted(declared - have - set(computed) - NEVER_WRITTEN)
    extra = sorted(have - declared)
    if missing:
        raise SystemExit(f'the document lists columns no row carries: '
                         f'{missing}')
    if extra:
        raise SystemExit(f'the run wrote columns the document does not list, '
                         f'and a column is not dropped silently: {extra}')

    # `present` is about what the RUN wrote, so it is read before the
    # computed columns are filled in -- and the computed ones are then marked
    # present explicitly, because they are about to be. Without that they
    # report as "never written", which is true of the run and false of the
    # file, and the printed summary would say the opposite of the truth.
    present = {n: (n in have) for n in order}
    for r in rows:
        for n, f in COMPUTED.items():
            r[n] = f(r)
    present.update({n: True for n in COMPUTED})

    with CSV_OUT.open('w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(order)
        for r in rows:
            w.writerow([fmt(r.get(n)) for n in order])

    SCHEMA_OUT.write_text(json.dumps(
        sidecar(order, groups, computed, rows, present), indent=1) + '\n')

    ok = sum(1 for r in rows if r['status'] == 'ok')
    print(f'{CSV_OUT.name}: {len(rows)} rows x {len(order)} columns  '
          f'({ok} ok, {len(rows) - ok} failed)')
    print(f'  groups: ' + ', '.join(f'{g} {len(n)}'
                                    for g, n in groups.items()))
    print(f'  computed: {", ".join(sorted(computed))}')
    empty = [n for n, p in present.items() if not p]
    if empty:
        print(f'  emitted empty (never written by the run): {empty}')
    print(f'{SCHEMA_OUT.name}: {len(order)} field descriptions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""plot_from_schema.py -- plot a result file using NOTHING but the file.

    python3 tools/plot_from_schema.py docs/dataset/dataset_components.csv

THE POINT IS WHAT THIS FILE MAY NOT DO. It imports nothing from `slay`, so
it cannot solve, cannot reach a Scene, cannot ask the model where a roller
is, and cannot fall back on anything a reader of the source happens to know.
Stdlib and matplotlib only. Whatever it draws, it drew from the CSV and the
`.schema.json` beside it -- which is the only honest test of whether that
contract is sufficient.

UNITS AND LABELS COME FROM THE SCHEMA, not from this file. `unit_of` looks a
column up in the declared fields, falling back to the declared PATTERNS, and
the axis label is built from what it finds. Nothing here knows that
`peak_moment` is N.m or that strain is a fraction; if the schema is wrong or
silent, the plot says so rather than guessing.

WHAT IT CANNOT DRAW, and this is the useful finding rather than a limitation
to apologise for. A case row is one line per passage: it carries every PEAK
with its location and step, per-station envelopes, and the junction probes.
It does NOT carry a profile -- strain against position along the pipe -- so
no trace can be drawn from it. That is by design: a profile is thousands of
numbers per position and belongs in a per-position artifact, not in a
dataset row. It is stated here so nobody concludes the schema is broken when
a trace does not appear.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# reading -- the file, and only the file
# ---------------------------------------------------------------------------

def load(path):
    """(rows, schema). The schema is read from `<path>.schema.json`.

    Refuses rather than guesses if the sidecar is missing: a result file
    whose contract is absent cannot be interpreted, and inventing units is
    how `0.0074` becomes `0.0074%`.
    """
    path = Path(path)
    side = Path(str(path) + '.schema.json')
    if not side.exists():
        raise SystemExit(f'no schema beside {path.name}; expected '
                         f'{side.name}. This tool interprets nothing on its '
                         f'own.')
    schema = json.loads(side.read_text())
    with open(path, newline='') as fh:
        rows = list(csv.DictReader(fh))
    return rows, schema


def field_of(schema, column):
    """The declared field for a column: exact first, then patterns."""
    for f in schema['fields']:
        if f['name'] == column:
            return f
    for p in schema['patterns']:
        if re.fullmatch(p['name'], column):
            return p
    return None


def unit_of(schema, column):
    f = field_of(schema, column)
    return f['unit'] if f else '?'


def axis_label(schema, column, fallback=''):
    """Built from the schema, never spelled here."""
    f = field_of(schema, column)
    if not f:
        return fallback or column
    q, u = f['quantity'], f['unit']
    if u == '-':
        return f'{q} (dimensionless)'
    return f'{q} ({u})'


def num(row, column):
    v = row.get(column, '')
    if v in ('', None):
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# finding things, by the schema's declared shapes
# ---------------------------------------------------------------------------

def peak_groups(schema, row):
    """Every peak the file carries, as {prefix: {...}}.

    Found by the schema's own rule -- a value column with a `_step` sibling --
    so a schema that grows a fifth peak needs no change here.
    """
    names = {f['name'] for f in schema['fields']}
    out = {}
    for f in schema['fields']:
        p = f['name']
        if f['role'] != 'value' or f'{p}_step' not in names:
            continue
        v = num(row, p)
        if v is None:
            continue
        out[p] = dict(value=v, unit=f['unit'], quantity=f['quantity'],
                      s_station=num(row, f'{p}_s_station'),
                      station=row.get(f'{p}_station', ''),
                      offset=num(row, f'{p}_station_offset'),
                      step=num(row, f'{p}_step'),
                      shift=num(row, f'{p}_shift'))
    return out


_PROBE = re.compile(r'^(j\d+)_(.+?)_(strain|moment|s)$')


def junction_probes(row):
    """{junction: [(s, strain, moment, tag)]}, sorted by s.

    Columns are PAIRED BY NAME, which a flat CSV leaves no alternative to --
    but the position comes from the declared `_s` column rather than from
    parsing `m2OD` back into a number, so no semantics are re-derived here.
    """
    acc = {}
    for col in row:
        mt = _PROBE.match(col)
        if not mt or col.endswith('_env'):
            continue
        j, tag, kind = mt.groups()
        acc.setdefault(j, {}).setdefault(tag, {})[kind] = num(row, col)
    out = {}
    for j, tags in acc.items():
        pts = [(d['s'], d.get('strain'), d.get('moment'), tag)
               for tag, d in tags.items() if d.get('s') is not None]
        if pts:
            out[j] = sorted(pts)
    return out


def station_envelopes(row):
    """{station: strain}, from the declared `eps_*_env` pattern."""
    out = {}
    for col, v in row.items():
        mt = re.fullmatch(r'eps_([A-Za-z]+\d*)_env', col)
        if mt and num(row, col) is not None:
            out[mt.group(1)] = num(row, col)
    return out


# ---------------------------------------------------------------------------
# plotting
# ---------------------------------------------------------------------------

def plot_case(row, schema, ax_j, ax_s):
    probes = junction_probes(row)
    stations = station_envelopes(row)
    peaks = peak_groups(schema, row)
    cid = row.get('case_id', '?')
    fam = row.get('family', '?')

    # -- junction profiles, in the units the schema declares ---------------
    if probes:
        ax2 = ax_j.twinx()
        for k, (j, pts) in enumerate(sorted(probes.items())):
            s = [p[0] for p in pts]
            e = [p[1] for p in pts]
            m = [p[2] for p in pts]
            ls = '-' if k == 0 else '--'
            if any(v is not None for v in e):
                ax_j.plot(s, [100.0 * v if v is not None else None for v in e],
                          ls, marker='o', ms=4, color='#1f7a8c',
                          label=f'{j} strain')
            if any(v is not None for v in m):
                ax2.plot(s, [v / 1e3 if v is not None else None for v in m],
                         ls, marker='s', ms=3.5, color='#8a5a00', alpha=0.8,
                         label=f'{j} moment')
        ax_j.set_ylabel(axis_label(schema, 'peak_strain') + '  [shown as %]')
        ax2.set_ylabel(axis_label(schema, 'peak_moment') + '  [shown as kN.m]')
        ax_j.set_xlabel('material coordinate s (' +
                        unit_of(schema, 'j0_at_pipe_s') + ')')
        h1, l1 = ax_j.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax_j.legend(h1 + h2, l1 + l2, fontsize=7, ncol=2, loc='upper left')
        ax_j.set_title(f'{cid}  {fam}  --  junction probes '
                       f'(I/Ip = {row.get("stiffness_ratio", "?")[:6]}, '
                       f'{row.get("n_junctions", "?")} junctions)',
                       fontsize=9.5, loc='left')
    else:
        ax_j.text(0.5, 0.5, f'{cid}  {fam}\nno junctions in this case\n'
                            f'(stiffness ratio '
                            f'{row.get("stiffness_ratio", "?")[:6]} -- the '
                            f'body steps no section)',
                  ha='center', va='center', fontsize=10, color='#5a6068',
                  transform=ax_j.transAxes)
        ax_j.set_xticks([])
        ax_j.set_yticks([])
    ax_j.grid(alpha=0.2)

    # -- station envelopes, and every peak with its step -------------------
    if stations:
        order = sorted(stations, key=lambda n: (n[:2], int(n[2:] or 0)))
        ax_s.bar(range(len(order)), [100 * stations[n] for n in order],
                 color='#9fb8c4', edgecolor='#1f7a8c')
        ax_s.set_xticks(range(len(order)))
        ax_s.set_xticklabels(order, fontsize=7.5, rotation=45)
    ax_s.set_ylabel(axis_label(schema, 'peak_strain') + '  [shown as %]')
    ax_s.grid(alpha=0.2, axis='y')

    lines = []
    for p, d in sorted(peaks.items()):
        if d['quantity'] != 'strain' or not d['value']:
            continue
        ax_s.axhline(100 * d['value'], color='#c1121f', lw=0.9, ls=':')
        lines.append(f'{p} = {100 * d["value"]:.4f}%  at {d["station"]}'
                     f'{d["offset"]:+.2f} m, step {int(d["step"])} '
                     f'(shift {d["shift"]:.3f} m)')
    for p, d in sorted(peaks.items()):
        if d['quantity'] != 'moment' or not d['value']:
            continue
        lines.append(f'{p} = {d["value"] / 1e3:.1f} kN.m  at {d["station"]}'
                     f'{d["offset"]:+.2f} m, step {int(d["step"])} '
                     f'(shift {d["shift"]:.3f} m)')
    ax_s.set_title('station envelopes, and every peak with its step',
                   fontsize=9.5, loc='left')
    if lines:
        ax_s.text(0.995, 0.97, '\n'.join(lines), transform=ax_s.transAxes,
                  ha='right', va='top', fontsize=7.5, family='monospace',
                  bbox=dict(boxstyle='round,pad=0.35', fc='white',
                            ec='#c1121f', lw=0.8, alpha=0.93))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    src = args[0] if args else str(REPO / 'docs' / 'dataset'
                                   / 'dataset_components.csv')
    out = (sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv
           else str(REPO / 'docs' / 'diagrams' / 'from_schema.png'))
    only = (sys.argv[sys.argv.index('--case') + 1] if '--case' in sys.argv
            else None)

    rows, schema = load(src)
    if only:
        rows = [r for r in rows
                if only in (r.get('case_id'), r.get('family'))]
    if not rows:
        raise SystemExit(f'no rows selected from {src}')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(rows), 2, figsize=(15.0, 4.4 * len(rows)),
                             squeeze=False)
    for r, (ax_j, ax_s) in zip(rows, axes):
        plot_case(r, schema, ax_j, ax_s)

    v = schema.get('schema_version', '?')
    sha = rows[0].get('git_sha', '?')
    when = rows[0].get('produced_at', '?')
    fig.suptitle(
        f'Plotted from {Path(src).name} and its schema alone -- no solver, '
        f'no model, nothing imported from slay.\n'
        f'schema {v}   git {sha}   produced {when}', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=140)
    print(f'wrote {out}')
    for r in rows:
        print(f'  {r.get("case_id"):6s} {r.get("family"):8s} '
              f'{r.get("status")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

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

TWO KINDS OF FILE, because there are two kinds of question.

  A CASE ROW (`slay.report.schema`) is one line per passage: every PEAK with
  its location and step, per-station envelopes, the junction probes. It does
  NOT carry a profile, by design -- a profile is thousands of numbers per
  position and has no business in a dataset row. Default mode reads these.

  A PROFILE (`slay.report.profile_schema`) is three tables for ONE case:
  geometry per sample per position, sections per element per position, and
  the rollers. `--profile <stem>` reads these and draws the five-panel
  stinger figure.

    python3 tools/plot_from_schema.py --profile docs/profiles/<case_id>

THAT SECOND MODE IS WHY THE CONTRACT EXISTS. Before it, the only way to draw
the pipe on the stinger was a tool that re-solved the passage on every run --
a figure that cannot be checked, cannot be pointed at last week's result, and
has no way to fail loudly. Now a wrong figure is either a wrong file, which
the writer's own checks refuse, or a wrong plotter, which a reader can see.
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


_PROBE = re.compile(r'^(j\d+)_(.+?)_(strain|moment|s|side)$')


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
        v = row.get(col) if kind == 'side' else num(row, col)
        acc.setdefault(j, {}).setdefault(tag, {})[kind] = v
    out = {}
    for j, tags in acc.items():
        pts = [(d['s'], d.get('strain'), d.get('moment'), tag,
                d.get('side') or '')
               for tag, d in tags.items() if d.get('s') is not None]
        if pts:
            out[j] = sorted(pts)
    return out


def by_body(pts):
    """Split a junction's probes into runs of one BODY.

    Strain STEPS at a section change, so a line drawn through it asserts a
    gradient the model does not have. Before schema 1.1.0 the file carried
    no `side`, so this could not be done from the file at all and the first
    version of this plot joined points across the discontinuity.
    """
    runs, cur = [], []
    for p in pts:
        if cur and p[4] != cur[-1][4]:
            runs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        runs.append(cur)
    return runs


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
        done = set()
        for k, (j, pts) in enumerate(sorted(probes.items())):
            ls = '-' if k % 2 == 0 else '--'
            for run in by_body(pts):
                s = [p[0] for p in run]
                e = [p[1] for p in run]
                m = [p[2] for p in run]
                lab_e = f'{j} strain' if j not in done else None
                lab_m = f'{j} moment' if j not in done else None
                done.add(j)
                if any(v is not None for v in e):
                    ax_j.plot(s, [100.0 * v if v is not None else None
                                  for v in e], ls, marker='o', ms=4,
                              color='#1f7a8c', label=lab_e)
                if any(v is not None for v in m):
                    ax2.plot(s, [v / 1e3 if v is not None else None
                                 for v in m], ls, marker='s', ms=3.5,
                             color='#8a5a00', alpha=0.8, label=lab_m)
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
        # NO SECTION STEP does not mean no component. A shroud lifts the pipe
        # without stiffening it, so the LIFT is the whole of it -- and before
        # schema 1.1.0 this file said nothing about that, leaving the case
        # indistinguishable from bare pipe.
        lift = num(row, 'contact_lift_max')
        u = unit_of(schema, 'contact_lift_max')
        extra = ('' if lift is None else
                 f'\n\ncontact_lift_max = {lift:.5f} {u}'
                 f'\nat {row.get("contact_lift_station", "?")}, '
                 f'step {row.get("contact_lift_step", "?")}'
                 f'\n\nthe body lifts the pipe without stiffening it:\n'
                 f'that lift IS the component')
        ax_j.text(0.5, 0.5, f'{cid}  {fam}\nno section step '
                            f'(stiffness ratio '
                            f'{row.get("stiffness_ratio", "?")[:6]}){extra}',
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


# ---------------------------------------------------------------------------
# the PROFILE artifact -- the five-panel figure, from three CSVs and nothing
# ---------------------------------------------------------------------------
#
# WHAT CHANGED, AND WHY IT MATTERS. Until the profile artifact existed, this
# figure could only be drawn by a program that re-solved the passage. Every
# coordinate below now comes off a file: the pipe from `geometry.x/y`, the
# rollers from `stations`, the strain staircase from `sections`, the body
# outlines from `OD_section` and `y_contact`. Nothing here knows what a
# stinger is.
#
# The ONE thing this code computes rather than reads is the offset of a
# polyline along its own normal, used to turn a centreline into a wall. That
# is pure geometry on numbers the file gives it -- no physics, no scene, no
# convention that could be got wrong silently.

TABLES = ('geometry', 'sections', 'stations')
OPTIONAL_TABLES = ('members',)      # present only for an EA case


def load_profile(stem):
    """{table: (rows, schema)} for a profile artifact written at `stem`."""
    stem = Path(stem)
    out = {}
    for t in TABLES:
        p = Path(f'{stem}.{t}.csv')
        if not p.exists():
            raise SystemExit(
                f'no {t} table at {p}. A profile is three tables plus an '
                f'optional `members`; emit one with '
                f'`python3 tools/emit_profile.py`.')
        out[t] = load(p)
    # OPTIONAL, and its absence means something: no attached structure. A
    # case with no EA frame writes no members table at all, so demanding one
    # would refuse every ordinary case.
    for t in OPTIONAL_TABLES:
        p = Path(f'{stem}.{t}.csv')
        if p.exists():
            out[t] = load(p)
    v = {out[t][1].get('profile_schema_version') for t in out}
    if len(v) > 1:
        raise SystemExit(f'the three tables disagree on schema version: {v}')
    return out


def at_step(rows, step):
    return [r for r in rows if int(float(r['step'])) == step]


def col(rows, name, cast=float):
    return [cast(r[name]) for r in rows]


def truth(v):
    return str(v).strip().lower() in ('true', '1', 'yes')


def offset_polyline(px, py, dist):
    """Offset a polyline along its LOCAL NORMAL, which here points DOWN.

    NOT a vertical offset. The pipe is bent to a 33-85 m radius and its
    tangent turns through 0.64 rad over the stinger, so a wall drawn by
    adding OD/2 to `y` would be up to 20% too narrow at the last roller and
    perpendicular to the pipe nowhere on the arc. `dist` may be a scalar or
    one value per point, which is what lets a tapered body be drawn.

    Node order runs in -x (x = -(s + shift)), so the tangent on the deck is
    (-1, 0) and the normal (t_y, -t_x) comes out (0, +1) -- down, the side
    the rollers are on.
    """
    import numpy as np
    px, py = np.asarray(px, float), np.asarray(py, float)
    d = (np.full(len(px), float(dist)) if np.isscalar(dist)
         else np.asarray(dist, float))
    tx, ty = np.gradient(px), np.gradient(py)
    n = np.hypot(tx, ty)
    n[n == 0] = 1.0
    tx, ty = tx / n, ty / n
    return px + d * ty, py - d * tx


def ring(px, py, d_lo, d_hi):
    """A closed band between two offsets of the same centreline."""
    import numpy as np
    ax, ay = offset_polyline(px, py, d_lo)
    bx, by = offset_polyline(px, py, d_hi)
    return (np.concatenate([ax, bx[::-1]]), np.concatenate([ay, by[::-1]]))


def owner_span(rows, key):
    """(lo, hi) row indices where `key` is not 'pipe', or None.

    This is how the figure finds the component WITHOUT being told where it
    is: the assembly's own answer, sampled into the file.
    """
    idx = [k for k, r in enumerate(rows) if r[key] not in ('pipe', '')]
    return (min(idx), max(idx)) if idx else None


REGION_FILL = {'X1': '#eef3f7', 'X2': '#f7d9d5', 'X3': '#f7ecd5',
               'X4': '#e8f0e2', 'X5': '#eef3f7'}


def region_spans(rows):
    """[(name, x_lo, x_hi)] in world x, from the sampled `region` column.

    Read off the file rather than recomputed: the regions are fixed on the
    STEEL, and the writer measured them once off the assembly. Re-deriving
    them here from L1 and L2 would be a second opinion about where X2 is.
    """
    out, cur, lo = [], None, None
    for r in rows:
        g = r.get('region', '')
        if g != cur:
            if cur:
                out.append((cur, lo, float(r['x'])))
            cur, lo = g, float(r['x'])
    if cur:
        out.append((cur, lo, float(rows[-1]['x'])))
    return [(n, min(a, b), max(a, b)) for n, a, b in out if n]


def junction_x(rows):
    """World x of every section step, read off the sampled section owner.

    A junction is where `OD_section` changes -- the schema says so, and it
    says why the strain trace must break there rather than be drawn through.
    """
    out = []
    for a, b in zip(rows, rows[1:]):
        if abs(float(a['OD_section']) - float(b['OD_section'])) > 1e-9:
            out.append(0.5 * (float(a['x']) + float(b['x'])))
    return out


def strain_runs(rows):
    """[[(x, strain), ...], ...] -- one staircase run per section.

    BROKEN AT EVERY JUNCTION, and that is not decoration. Strain steps
    across a section change (the same moment on two section moduli), so a
    line drawn through it asserts a gradient the model does not have. Each
    element is drawn over its OWN EXTENT rather than as a point at its
    midpoint: joining midpoints interpolates, and leaves a half-element gap
    against the junction that reads as missing data instead of as the step.
    """
    rows = sorted(rows, key=lambda r: float(r['s_material_0']))
    runs, cur, last = [], [], None
    for r in rows:
        od = float(r['OD_section'])
        if last is not None and abs(od - last) > 1e-9:
            runs.append(cur)
            cur = []
        e = float(r['strain'])
        cur += [(float(r['x_0']), e), (float(r['x_1']), e)]
        last = od
    if cur:
        runs.append(cur)
    return runs


def draw_members(panel, mem, lw_struct=2.0, lw_conn=3.0):
    """Draw the attached structure and its connectors on one axis.

    Each member is a straight segment between two SOLVED points, so nothing
    here needs to know what a portal frame is -- it draws what the file
    says. Connectors are drawn heavier and in the body colour because they
    are the load path into the pipe.
    """
    for r in mem:
        x0, y0 = float(r['x_0']), float(r['y_0'])
        x1, y1 = float(r['x_1']), float(r['y_1'])
        if r['kind'] == 'connector':
            panel.plot([x0, x1], [y0, y1], color='#8a5a00', lw=lw_conn,
                       solid_capstyle='round', zorder=7)
            panel.plot([x0], [y0], marker='s', ms=lw_conn + 1.5,
                       color='#8a5a00', zorder=8)
        else:
            panel.plot([x0, x1], [y0, y1], color='#2f6f3e', lw=lw_struct,
                       solid_capstyle='round', zorder=6, alpha=0.95)


def plot_profile(prof, out, step=None):
    """The five-panel figure, drawn from the three tables and nothing else."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Circle

    geo_all, geo_s = prof['geometry']
    sec_all, sec_s = prof['sections']
    sta, sta_s = prof['stations']
    mem_all = prof['members'][0] if 'members' in prof else []

    c = geo_all[0]
    if step is None:
        step = int(float(c['envelope_step']))
    g = sorted(at_step(geo_all, step), key=lambda r: int(r['sample']))
    sc = at_step(sec_all, step)
    mem = at_step(mem_all, step) if mem_all else []
    # THE TRACE IS THE PIPELINE'S. An attached structure's members solve on
    # the same axis and carry the pipe's section, so a staircase drawn over
    # every element interleaves two structures into one zig-zagging line.
    # Older profiles have no `owner` column; those are pipeline-only anyway.
    sc = [r for r in sc if r.get('owner', 'pipeline') == 'pipeline'] or sc
    conn_x = sorted(0.5 * (float(r['x_0']) + float(r['x_1']))
                    for r in mem if r['kind'] == 'connector')
    if not g or not sc:
        raise SystemExit(f'step {step} is not in this profile')

    OD, tw = float(c['OD']), float(c['t_wall'])
    shift = float(g[0]['shift'])
    px, py = np.array(col(g, 'x')), np.array(col(g, 'y'))
    fig, (ax, ex, dx, bx, cx) = plt.subplots(
        5, 1, figsize=(13.5, 18.4),
        gridspec_kw=dict(height_ratios=[1.0, 1.15, 0.8, 0.85, 0.9],
                         hspace=0.33))
    bx.sharex(ax)
    dx.sharex(ax)

    # ---- panel 1: the whole stinger ---------------------------------------
    ax.plot(col(g, 'arc_x'), col(g, 'arc_y'), color='#b9c2cb', lw=1.0,
            ls='--', zorder=1)
    for r in sta:
        one = truth(r['one_sided'])
        colr = ('#2f6f3e' if r['role'] == 'CONTACT'
                else '#111111' if r['role'] == 'FIXED' else '#6b4ea8')
        ax.add_patch(Circle((float(r['x']), float(r['y'])),
                            float(r['radius']), facecolor='none',
                            edgecolor=colr, lw=1.6, zorder=4))
        ax.annotate(r['station'], (float(r['x']), float(r['y'])),
                    textcoords='offset points', xytext=(0, -14), ha='center',
                    fontsize=7, color=colr)
        if one:
            ax.annotate('', xy=(float(r['x']), float(r['y']) - 1.6),
                        xytext=(float(r['x']), float(r['y']) - 0.35),
                        arrowprops=dict(arrowstyle='-|>', lw=1.1, color=colr,
                                        shrinkA=0, shrinkB=0), zorder=4)
    ax.plot(px, py, color='#1f7a8c', lw=2.2, zorder=5)

    # THE ATTACHED STRUCTURE. A figure of an EA case that draws only the
    # pipe omits the thing bending it. Members come off the `members` table
    # as solved segments; the connectors are drawn heavier because they are
    # the load path, and the pipe is only bent where they are.
    draw_members(ax, mem, lw_struct=2.0, lw_conn=3.0)

    sp_sec = owner_span(g, 'section_owner')
    sp_con = owner_span(g, 'contact_owner')
    sp = sp_sec or sp_con
    if sp:
        a, b = sp
        ax.plot(px[a:b + 1], py[a:b + 1], color='#8a5a00', lw=6.5,
                solid_capstyle='butt', zorder=6, alpha=0.9)
    jx = junction_x(g)
    regs = region_spans(g)
    for panel in (ax, bx, cx):
        if regs:
            # THE REGION SCHEME, shaded. An offset body steps no section, so
            # it has no junction to mark; the regions ARE its reporting
            # units and a figure that does not show them cannot be checked
            # against the region table.
            for name, x_lo, x_hi in regs:
                panel.axvspan(x_lo, x_hi, color=REGION_FILL.get(name, 'none'),
                              alpha=0.75, zorder=0)
        elif sp:
            panel.axvspan(px[sp[1]], px[sp[0]], color='#f2e3c4', alpha=0.55,
                          zorder=0)
        for xj in jx:
            panel.axvline(xj, color='#c1121f', lw=1.1, ls=(0, (4, 2)),
                          alpha=0.8, zorder=2)
        # WHERE THE FRAME IS FASTENED DOWN. For an EA case this is X_c, the
        # region that governs: a two-point attachment loads its own ends,
        # not the pipe it spans, so the peak sits at a connector and the
        # pipe BETWEEN them is the quietest part of the model.
        for xc in conn_x:
            panel.axvline(xc, color='#8a5a00', lw=1.3, ls=(0, (6, 2)),
                          alpha=0.9, zorder=2)
    if regs:
        for name, x_lo, x_hi in regs:
            if name in ('X2', 'X3', 'X4') or x_hi - x_lo > 1.0:
                cx.annotate(name, (0.5 * (x_lo + x_hi), 0.965),
                            xycoords=('data', 'axes fraction'), ha='center',
                            va='top', fontsize=9, color='#5a6672',
                            fontweight='bold')
    ax.set_aspect('equal')
    ax.invert_yaxis()
    ax.grid(alpha=0.2)
    ax.set_ylabel('y (m), down')
    ax.set_title(
        f'{c["family"]} on the stinger  --  R = {float(c["R"]):.0f} m, '
        f'spacing {float(c["spacing"]):.0f} m, '
        f'{float(c["tension_mt"]):.0f} MT, L = {float(c["L_comp"]):.3f} m '
        f'({float(c["L_comp"]) / OD:.2g} x OD), '
        f'I_comp/I_pipe = {float(c["stiffness_ratio"]):.3f}'
        + (f', frame kT = {max(float(r["stiffness_ratio"]) for r in mem):.2f}'
           f' x pipe, {len(conn_x)} connectors spanning '
           f'{abs(conn_x[-1] - conn_x[0]) / OD:.1f} D' if conn_x else '')
        + '\n'
        f'step {step} of {c["n_positions"]}, shift {shift:.3f} m'
        f'{"  <- envelope" if step == int(float(c["envelope_step"])) else ""}',
        fontsize=10, loc='left')

    # ---- panel 2: the close-up, 2D bodies ---------------------------------
    # TRUE SCALE CANNOT SHOW THIS. The stinger's curvature is 1/85 per metre,
    # so over a 20 m window the pipe departs from a straight line by ~0.6 m
    # and a component changes that by a few centimetres. Equal-aspect, that
    # is a couple of pixels: honest and useless. The vertical is stretched
    # and the factor is STATED, so nobody reads a radius off the picture.
    # THE WINDOW IS SET IN METRES, not in samples. A component may be 1 m or
    # 15 m long, and a window of "so many samples either side" gives the
    # short one a 3 m view with no roller in it -- the local curvature change
    # is only legible against the rollers that cause it.
    # An EA frame steps neither the section nor the contact, so `sp` is
    # None and there is no component span to centre on. Its CONNECTORS are
    # the equivalent: they are where it acts on the pipe.
    if sp is None and conn_x:
        lo_x, hi_x = min(conn_x), max(conn_x)
        keep = [k for k in range(len(g))
                if lo_x - 2.0 <= px[k] <= hi_x + 2.0]
        if keep:
            sp = (min(keep), max(keep))
    if sp:
        a, b = sp
        half = max(1.0 * float(c['spacing']), 2.0 * abs(px[b] - px[a]))
        mid = 0.5 * (px[a] + px[b])
        keep = [k for k in range(len(g)) if abs(px[k] - mid) <= half]
        lo, hi = (min(keep), max(keep)) if keep else (0, len(g) - 1)
    else:
        lo, hi = 0, len(g) - 1
    qx, qy = px[lo:hi + 1], py[lo:hi + 1]
    ex.fill(*ring(qx, qy, -OD / 2.0, OD / 2.0), facecolor='#dff1f5',
            edgecolor='#1f7a8c', lw=1.0, zorder=3, label='pipeline wall')
    ex.fill(*ring(qx, qy, -(OD / 2.0 - tw), OD / 2.0 - tw),
            facecolor='white', edgecolor='#9fc8d3', lw=0.7, zorder=4,
            label='bore')
    ex.plot(qx, qy, color='#1f7a8c', lw=0.9, ls='--', zorder=5,
            label='pipe centreline, SOLVED')
    ex.plot(col(g, 'arc_x')[lo:hi + 1], col(g, 'arc_y')[lo:hi + 1],
            color='#b9c2cb', lw=1.0, ls='--', zorder=1,
            label='roller-centreline locus')

    if sp_sec:                       # a body that REPLACES the pipe section
        a, b = sp_sec
        half = np.array(col(g, 'OD_section')[a:b + 1]) / 2.0
        ex.fill(*ring(px[a:b + 1], py[a:b + 1], -half, half),
                facecolor='#e0b062', edgecolor='#8a5a00', lw=1.2, zorder=6,
                alpha=0.95, label='component (thicker section)')
    if sp_con and not sp_sec:        # a SHROUD: contact only, no section
        a, b = sp_con
        deep = np.array(col(g, 'y_contact')[a:b + 1])
        ex.fill(*ring(px[a:b + 1], py[a:b + 1],
                      np.full(len(deep), OD / 2.0), deep),
                facecolor='#e0b062', edgecolor='#8a5a00', lw=1.2, zorder=6,
                alpha=0.95, label='shroud (contact surface only)')
    # ABOVE the wall fill (zorder 3-6), or the roller is drawn and then
    # painted over -- which looked exactly like "no roller in this window".
    draw_members(ex, mem, lw_struct=1.6, lw_conn=2.6)
    for r in sta:
        rx, ry = float(r['x']), float(r['y'])
        if qx.min() <= rx <= qx.max():
            ex.add_patch(Circle((rx, ry), float(r['radius']),
                                facecolor='none', edgecolor='#2f6f3e',
                                lw=1.4, zorder=8))
            ex.annotate(r['station'], (rx, ry), textcoords='offset points',
                        xytext=(0, 9), ha='center', fontsize=7,
                        color='#2f6f3e', zorder=8)
    # ASCENDING, like every other panel. Reversed here, the close-up read as
    # a mirror image of the figure above it and still looked plausible --
    # the same class of error as getting the world sign backwards.
    ex.set_xlim(qx.min(), qx.max())
    ymid = 0.5 * (qy.min() + qy.max())
    span = max(qy.max() - qy.min(), 1e-6)
    ex.set_ylim(ymid + 0.62 * span + OD, ymid - 0.62 * span - OD)
    ex.set_aspect('auto')
    ex.set_title('CLOSE-UP -- the vertical is EXAGGERATED, so the rollers '
                 'draw as ellipses and no radius may be read off this panel',
                 fontsize=9.5, loc='left')
    ex.set_ylabel('y (m), down')
    ex.grid(alpha=0.18)
    ex.legend(fontsize=7.5, ncol=3, loc='lower right', framealpha=0.9)

    # ---- panel 3: off the arc ---------------------------------------------
    dx.plot(px, np.array(col(g, 'off_arc')) * 1e3, color='#1f7a8c', lw=1.6)
    dx.axhline(0.0, color='#9aa5b1', lw=0.9, ls='--')
    if sp_con:
        lift = max(col(g, 'y_contact')) - OD / 2.0
        if lift > 1e-6:
            dx.axhline(lift * 1e3, color='#8a5a00', lw=0.9, ls=':')
            dx.annotate(f'contact lift at a roller: {lift * 1e3:.1f} mm',
                        (px.min(), lift * 1e3), textcoords='offset points',
                        xytext=(8, -12), fontsize=8, color='#8a5a00',
                        ha='left')
    for r in sta:
        dx.axvline(float(r['x']), color='#cfd8dc', lw=0.7, zorder=0)
    dx.set_ylabel('off the arc (mm)')
    dx.set_title('THE DEFORMED SHAPE, measured normal to the '
                 'roller-centreline locus -- zero means sitting on the '
                 'rollers, positive means held off them',
                 fontsize=9.5, loc='left')
    dx.grid(alpha=0.2)

    # ---- panels 4 and 5: the strain staircase -----------------------------
    out_band = [r for r in sc if not truth(r['in_band'])]
    for panel, zoom in ((bx, False), (cx, True)):
        for run in strain_runs(sc):
            panel.plot([q[0] for q in run], [100 * q[1] for q in run],
                       color='#1f7a8c', lw=1.5, solid_joinstyle='miter')
        if out_band:
            xs = [float(r['x_0']) for r in out_band] + \
                 [float(r['x_1']) for r in out_band]
            panel.axvspan(min(xs), max(xs), color='#d7dde3', alpha=0.5,
                          zorder=0)
        panel.set_ylabel('extreme-fibre strain (%)')
        panel.grid(alpha=0.2)
    peak = max(float(r['strain']) for r in sc if truth(r['in_band']))
    bx.axhline(100 * peak, color='#c1121f', lw=0.8, ls=':')
    bx.annotate(f'peak in band, this step: {100 * peak:.4f}%',
                (px.min(), 100 * peak), textcoords='offset points',
                xytext=(8, -12), fontsize=8, color='#c1121f', ha='left')
    bx.set_title('strain, the whole model', fontsize=9.5, loc='left')
    if sp:
        a, b = sp
        w = max(3.0, 1.6 * abs(px[b] - px[a]))
        x_lo, x_hi = min(px[a], px[b]) - w, max(px[a], px[b]) + w
        cx.set_xlim(x_lo, x_hi)              # ascending, like every panel
        inw = [float(r['strain']) for r in sc
               if x_lo <= float(r['x_0']) <= x_hi]
        if inw:
            cx.set_ylim(0, 100 * max(inw) * 1.22)
    cx.set_title(
        'zoom on the component -- '
        + ('X_c at each CONNECTOR, X_i between them, X_e outside: a '
           'two-point attachment loads its own ends, not the pipe it spans'
           if conn_x else
           'the junction STEP, at a scale where it can be read' if jx else
           f'the {c.get("region_scheme", "")} regions: no section step, so '
           'no strain discontinuity -- the rise is the LIFT bending the '
           'pipe' if regs else
           'no section step, so no strain discontinuity: the rise is the '
           'LIFT bending the pipe, not a change of section'),
        fontsize=9.5, loc='left')
    cx.set_xlabel('x (m)  --  +x toward the vessel, so the stinger is on '
                  'the LEFT (starboard view, no flip)')

    v = geo_s.get('profile_schema_version', '?')
    fig.suptitle(
        f'Drawn from the PROFILE ARTIFACT of case {c["case_id"]} and its '
        f'schema alone -- no solver, no Scene, nothing imported from slay.\n'
        f'profile schema {v}   {len(geo_all)} geometry rows, '
        f'{len(sec_all)} section rows, {len(sta)} stations', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(out, dpi=140)
    return dict(step=step, shift=shift, peak=peak, junctions=len(jx),
                fig=fig, panels=dict(stinger=ax, closeup=ex, off_arc=dx,
                                     strain=bx, zoom=cx))


def main() -> int:
    if '--profile' in sys.argv:
        stem = sys.argv[sys.argv.index('--profile') + 1]
        out = (sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv
               else str(REPO / 'docs' / 'diagrams'
                        / f'{Path(stem).name}_profile.png'))
        step = (int(sys.argv[sys.argv.index('--step') + 1])
                if '--step' in sys.argv else None)
        prof = load_profile(stem)
        r = plot_profile(prof, out, step=step)
        print(f'wrote {out}')
        print(f'  step {r["step"]}  shift {r["shift"]:.3f} m  '
              f'peak in band {100 * r["peak"]:.4f}%  '
              f'junctions {r["junctions"]}')
        return 0

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

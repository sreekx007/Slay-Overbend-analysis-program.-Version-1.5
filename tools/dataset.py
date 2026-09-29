#!/usr/bin/env python3
"""dataset.py -- the ML case matrix: run every case, record every outcome.

    python3 tools/dataset.py --out docs/dataset [--budget 21600]

WHAT A ROW IS. One CASE -- one complete passage, solved at many positions --
reduced to one line. The target columns come in two readings, because they
answer different questions and only one is what a reader assumes:

    bare name   the SNAPSHOT at the envelope position: one real instant
    `_env`      the worst that location saw at ANY position

They differ by 40% at a location that does not govern (`report.junction`
carries the measurement). Both fall out of the same solve, so both are kept.

THE DESIGN IS OFAT PLUS LATIN HYPERCUBE, and neither alone would do. The
one-factor-at-a-time spine varies a single axis from the baseline and gives
marginal trends a person can read straight off. The hypercube block samples
the axes jointly and is what a model needs to see interactions -- pure OFAT
teaches a model that the axes are independent, which they are not. A full
factorial over these axes is about ten thousand cases.

FAILURES ARE DATA. A case that diverges is recorded with its status and its
reason and the run moves to the next one; it is never silently dropped, and
the report states the failure rate. A dataset that quietly contains only the
cases that converged is biased toward the easy corner of the parameter space
and says nothing about where the method stops working.

CHECKPOINTED AFTER EVERY CASE. Both CSVs and the report are rewritten each
time a case finishes, so an interrupted run leaves complete, usable files
rather than nothing.
"""

from __future__ import annotations

import copy
import json
import math
import random
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

import ils_builder                                            # noqa: E402

from slay.report import junction as jr                        # noqa: E402
from slay.report import passage as rp                         # noqa: E402
from slay.report import schema as sch                         # noqa: E402

import slide                                                  # noqa: E402

SEED = 20260928
FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'

# -- the axes --------------------------------------------------------------
R_VALUES = (60.0, 70.0, 85.0, 105.0, 120.0, 150.0)
SPACING_VALUES = (6.0, 7.5, 9.0, 10.5, 12.0)
PIPE_VALUES = ((0.1683, 0.0110), (0.2191, 0.0127), (0.2731, 0.0159),
               (0.3239, 0.0175), (0.4064, 0.0210), (0.5080, 0.0254),
               (0.6100, 0.0286))
TENSION_VALUES = (40.0, 80.0, 120.0, 160.0, 200.0)
L_OD_VALUES = (1.0, 2.5, 5.0, 10.0)          # component length, x OD
T_RATIO_VALUES = (1.5, 2.0, 3.0, 4.0)        # component wall, x pipe wall

BASE = dict(R=85.0, spacing=9.0, pipe=(0.4064, 0.0210), tension_mt=120.0,
            L_OD=2.5, t_ratio=2.0)

N_LHS_PLAIN = 65
N_LHS_COMP = 89


def lhs(axes: dict, n: int, rng) -> list:
    """Stratified sample over DISCRETE axes.

    Each axis's value list is repeated to length `n` and shuffled
    independently, so every value appears as near equally as `n` allows and
    the axes are combined without correlation. The discrete analogue of a
    Latin hypercube, and reproducible: one seeded `rng`.
    """
    cols = {}
    for name, vals in axes.items():
        col = [vals[i % len(vals)] for i in range(n)]
        rng.shuffle(col)
        cols[name] = col
    return [{k: cols[k][i] for k in cols} for i in range(n)]


def ofat(axes: dict, base: dict) -> list:
    """Baseline, then each axis varied alone. Deduplicated."""
    out, seen = [], set()

    def add(case):
        key = tuple(sorted(case.items()))
        if key not in seen:
            seen.add(key)
            out.append(case)

    add(dict(base))
    for name, vals in axes.items():
        for v in vals:
            c = dict(base)
            c[name] = v
            add(c)
    return out


def plain_cases() -> list:
    rng = random.Random(SEED)
    axes = dict(R=R_VALUES, spacing=SPACING_VALUES, pipe=PIPE_VALUES,
                tension_mt=TENSION_VALUES)
    base = {k: BASE[k] for k in axes}
    cases = [dict(c, design='ofat') for c in ofat(axes, base)]
    cases += [dict(c, design='lhs') for c in lhs(axes, N_LHS_PLAIN, rng)]
    for i, c in enumerate(cases):
        c['case_id'] = f'P{i:03d}'
        c['family'] = 'plain'
    return cases


def comp_cases() -> list:
    rng = random.Random(SEED + 1)
    axes = dict(R=R_VALUES, spacing=SPACING_VALUES, pipe=PIPE_VALUES,
                tension_mt=TENSION_VALUES, L_OD=L_OD_VALUES,
                t_ratio=T_RATIO_VALUES)
    base = {k: BASE[k] for k in axes}
    cases = [dict(c, design='ofat') for c in ofat(axes, base)]
    cases += [dict(c, design='lhs') for c in lhs(axes, N_LHS_COMP, rng)]
    for i, c in enumerate(cases):
        c['case_id'] = f'T{i:03d}'
        c['family'] = 'gd-tp'
    return cases


def build_component(OD: float, t_wall: float, L_OD: float, t_ratio: float):
    """A GD-TP of the requested length and wall, on the requested pipe.

    Built by editing the archetype's own definition rather than by
    constructing geometry here: `ils_builder` stays the single author of what
    a component IS (G7), and the constant-bore outward growth that gives
    `OD_comp = OD + 2*(t_comp - t_wall)` comes with it.
    """
    spec = copy.deepcopy(_ils_tp_definition())
    spec['pipeline']['OD_pipe'] = OD
    spec['pipeline']['t_pipe'] = t_wall
    spec['components'][0]['L_comp'] = L_OD * OD
    spec['components'][0]['t_comp'] = t_ratio * t_wall
    return ils_builder.build_ils(spec)


_DEF_CACHE = {}


def _ils_tp_definition():
    if 'd' not in _DEF_CACHE:
        d = json.loads(FIXTURE.read_text())
        _DEF_CACHE['d'] = {a['id']: a
                           for a in d['archetypes']}['ILS-TP']['definition']
    return _DEF_CACHE['d']


def run_case(case: dict, git_sha: str = '', stamp: str = '') -> dict:
    """Solve one case. Returns a flat row against the schema; never raises."""
    OD, t_wall = case['pipe']
    row = {'schema_version': sch.SCHEMA_VERSION,
           'case_id': case['case_id'], 'family': case['family'],
           'design': case['design'], 'git_sha': git_sha,
           'produced_at': stamp,
           'R': case['R'],
           'spacing': case['spacing'], 'OD': OD, 't_wall': t_wall,
           'tension_mt': case['tension_mt'],
           'L_OD': case.get('L_OD', 0.0),
           't_ratio': case.get('t_ratio', 0.0),
           'contact_surface': 'centreline', 'mode': 'A', 'material': 'j2',
           'step': 2.0 * OD}
    t0 = time.time()
    try:
        ils = None
        if case['family'] == 'gd-tp':
            ils = build_component(OD, t_wall, case['L_OD'], case['t_ratio'])
        elif case['family'] != 'plain':
            # Any other family is an ARCHETYPE ID, taken as built. Its length
            # and wall are the archetype's own, so `L_OD` and `t_ratio` are
            # read back off it rather than driving it.
            ils = slide.archetype(case['family'])
        sc, L_comp, recs, junc = slide.passage(
            arch_id='none', R=case['R'], spacing=case['spacing'],
            tension_mt=case['tension_mt'], OD=OD, t_wall=t_wall,
            step=2.0 * OD, ils=ils, verbose=False)
        row['L_comp'] = L_comp
        if case['family'] not in ('plain', 'gd-tp'):
            row['L_OD'] = L_comp / OD if OD else 0.0
        row['n_positions'] = len(recs)
        row['n_converged'] = sum(1 for r in recs if r.converged)
        env = rp.envelope(recs)
        # EVERY PEAK WITH ITS LOCATION AND ITS STEP -- the schema's peak
        # groups, filled. Strain and moment peak at DIFFERENT positions in
        # general, so each carries its own step rather than sharing one.
        row.update(rp.peaks(recs, sc))
        row.update(rp.body_peaks(recs, sc, junc))
        row.update(
            start_strain=recs[0].peak_strain if recs[0].converged else '',
            zone_s_max=env.zone_s_max, zone_label=env.zone_label,
            n_active=env.n_active, n_slots=env.n_slots)
        for name, eps in rp.station_envelope(recs).items():
            row[f'eps_{name}_env'] = eps
        row.update(jr.case_row(junc, env.index))
        # Gated on WHETHER A COMPONENT WAS SOLVED, not on the family name.
        # Gating on `family == 'gd-tp'` hardcoded 1.0 and 0 for every other
        # archetype: ILS-TT reported I = 1.000 with no junctions when the
        # model it had just solved carried 6 junctions and a ratio of 4.366.
        # The solve was right; only the row lied.
        d = junc[env.index] if junc and junc[env.index] else {}
        row['stiffness_ratio'] = d.get('stiffness_ratio', 1.0)
        row['n_junctions'] = d.get('n_junctions', 0)
        row['status'] = ('ok' if row['n_converged'] == row['n_positions']
                         else f'partial {row["n_converged"]}/{row["n_positions"]}')
        row['error'] = ''
    except Exception as exc:                       # noqa: BLE001
        row['status'] = 'FAILED'
        row['error'] = f'{type(exc).__name__}: {exc}'[:300]
        row['traceback'] = traceback.format_exc()[-400:]
    row['seconds'] = round(time.time() - t0, 1)
    return row


def write_csv(rows, path):
    """Through the schema, which refuses a column it does not describe."""
    if not rows:
        return
    clean = [{k: v for k, v in r.items() if k != 'traceback'} for r in rows]
    rp.write_case_csv(clean, path)


def _pct(a, b):
    return f'{100.0 * a / b:.0f}%' if b else '-'


def write_report(plain, comp, path, started, done, total, budget_hit=False):
    ok = [r for r in plain + comp if r.get('status') == 'ok']
    part = [r for r in plain + comp if str(r.get('status', '')).startswith('partial')]
    bad = [r for r in plain + comp if r.get('status') == 'FAILED']
    el = time.time() - started
    L = []
    A = L.append
    A('# SLAY Overbend — ML case matrix')
    A('')
    A(f'**{done} of {total} cases run** in {el / 3600.0:.2f} h'
      + ('  — **stopped on the time budget**' if budget_hit else ''))
    A('')
    A('| | |')
    A('|---|---|')
    A(f'| Date | 28 September 2026 |')
    A(f'| Branch | `claude/program-rebuild-status-bya72s` |')
    A(f'| Runner | `tools/dataset.py`, seed {SEED} |')
    A(f'| Converged fully | {len(ok)} ({_pct(len(ok), done)}) |')
    A(f'| Converged partly | {len(part)} ({_pct(len(part), done)}) |')
    A(f'| Failed | {len(bad)} ({_pct(len(bad), done)}) |')
    A('')
    A('Row = one case = one complete passage. Target columns come in two '
      'readings: the bare name is the **snapshot** at the envelope position, '
      '`_env` is the worst that location saw at **any** position. Both come '
      'from the same solve.')
    A('')
    A('## Files')
    A('')
    A('| File | Rows | Contents |')
    A('|---|---|---|')
    A(f'| `dataset_plain.csv` | {len(plain)} | plain pipe, no component |')
    A(f'| `dataset_gdtp.csv` | {len(comp)} | GD-TP thick component |')
    A('')
    A('## Axes')
    A('')
    A('| Axis | Values | Baseline |')
    A('|---|---|---|')
    A(f'| Stinger radius R (m) | {", ".join(f"{v:g}" for v in R_VALUES)} | 85 |')
    A(f'| Roller spacing (m) | {", ".join(f"{v:g}" for v in SPACING_VALUES)} | 9 |')
    A('| Pipe OD x WT (mm) | '
      + ', '.join(f'{a * 1000:g}x{b * 1000:g}' for a, b in PIPE_VALUES)
      + ' | 406.4x21 |')
    A(f'| Tension (MT) | {", ".join(f"{v:g}" for v in TENSION_VALUES)} | 120 |')
    A(f'| Component length (xOD) | {", ".join(f"{v:g}" for v in L_OD_VALUES)} | 2.5 |')
    A(f'| Component wall (x pipe) | {", ".join(f"{v:g}" for v in T_RATIO_VALUES)} | 2.0 |')
    A('')
    for title, rows in (('Plain pipe', plain), ('GD-TP', comp)):
        if not rows:
            continue
        A(f'## {title} — every case')
        A('')
        head = ('| case | design | R | sp | OD×WT | T | L/OD | t/t | '
                'envelope | at shift | I ratio | s | status |')
        A(head)
        A('|---' * 13 + '|')
        for r in rows:
            e = r.get('envelope_strain')
            es = f'{100 * e:.4f}%' if isinstance(e, float) else '—'
            sh = r.get('envelope_shift')
            shs = f'{sh:.3f}' if isinstance(sh, float) else '—'
            sr = r.get('stiffness_ratio')
            srs = f'{sr:.3f}' if isinstance(sr, float) else '—'
            A(f'| {r["case_id"]} | {r["design"]} | {r["R"]:g} | '
              f'{r["spacing"]:g} | {r["OD"] * 1000:g}×{r["t_wall"] * 1000:g} | '
              f'{r["tension_mt"]:g} | {r.get("L_OD", 0):g} | '
              f'{r.get("t_ratio", 0):g} | {es} | {shs} | {srs} | '
              f'{r.get("seconds", 0):g}s | {r.get("status", "?")} |')
        A('')
    if bad or part:
        A('## Cases that did not fully converge')
        A('')
        A('Recorded, not dropped. A dataset holding only the cases that '
          'converged is biased toward the easy corner of the parameter space '
          'and says nothing about where the method stops working.')
        A('')
        A('| case | R | sp | OD×WT | T | L/OD | t/t | status | reason |')
        A('|---|---|---|---|---|---|---|---|---|')
        for r in part + bad:
            A(f'| {r["case_id"]} | {r["R"]:g} | {r["spacing"]:g} | '
              f'{r["OD"] * 1000:g}×{r["t_wall"] * 1000:g} | '
              f'{r["tension_mt"]:g} | {r.get("L_OD", 0):g} | '
              f'{r.get("t_ratio", 0):g} | {r.get("status")} | '
              f'{(r.get("error") or "positions diverged").replace("|", "/")} |')
        A('')
    Path(path).write_text('\n'.join(L) + '\n')


def main() -> int:
    a = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    out = Path(opt('--out', str(REPO / 'docs' / 'dataset')))
    out.mkdir(parents=True, exist_ok=True)
    budget = opt('--budget', 21600.0, float)          # 6 h, leaving margin
    limit = opt('--limit', None, int)

    cases = plain_cases() + comp_cases()
    if limit:
        cases = cases[:limit]
    total = len(cases)
    print(f'{total} cases; budget {budget / 3600.0:.1f} h; writing to {out}')

    import subprocess
    try:
        git_sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                                 cwd=str(REPO), capture_output=True,
                                 text=True, timeout=10).stdout.strip()
    except Exception:                                   # noqa: BLE001
        git_sha = ''
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    print(f'schema {sch.SCHEMA_VERSION}, git {git_sha or "?"}, {stamp}')

    started, plain, comp = time.time(), [], []
    budget_hit = False
    for i, case in enumerate(cases, 1):
        if time.time() - started > budget:
            print(f'budget reached after {i - 1} cases')
            budget_hit = True
            break
        row = run_case(case, git_sha, stamp)
        (plain if row['family'] == 'plain' else comp).append(row)
        print(f'[{i:3d}/{total}] {row["case_id"]:5s} {row["status"]:22s} '
              f'{row.get("seconds", 0):6.1f}s', flush=True)
        write_csv(plain, out / 'dataset_plain.csv')
        write_csv(comp, out / 'dataset_gdtp.csv')
        write_report(plain, comp, out / 'DATASET.md', started, i, total)
    write_report(plain, comp, out / 'DATASET.md', started,
                 len(plain) + len(comp), total, budget_hit)
    print(f'done: {len(plain)} plain, {len(comp)} gd-tp, '
          f'{(time.time() - started) / 3600.0:.2f} h')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

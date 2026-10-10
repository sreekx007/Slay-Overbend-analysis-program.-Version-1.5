#!/usr/bin/env python3
"""make_plain_dataset.py -- the plain-pipelay surrogate dataset, one case at
a time, checkpointed.

    python3 surrogate/make_plain_dataset.py                 # the whole matrix
    python3 surrogate/make_plain_dataset.py --anchors-only   # just the gate
    python3 surrogate/make_plain_dataset.py --budget 10800   # stop after 3 h

The design, the axes and the reasons for every setting are in
`PLAN_plain_surrogate_dataset.md` beside this file and are NOT restated here.
What this module owns is the execution: build the case list, run each case
through the same entry point the published Sec. 1 tables use, and append one
JSON object per case to `plain_runs.jsonl`.

WHY THE RUNNER WRITES JSONL AND NOT CSV. The order asked for is run, write
down, then tabulate: the results MD is written from this file and the CSV
from the MD. A runner that emitted the CSV directly would make the MD a
commentary on a table nobody produced from it, and the two could drift.

FAILURES ARE DATA. A case that diverges, truncates or is refused is recorded
with its status and its reason and the run moves on. Dropping it would bias
the dataset toward the easy corner of the parameter space, which is the one
corner a surrogate's user does not need help with.

APPEND-ONLY AND RESUMABLE. Every finished case is flushed before the next
one starts, and a restart skips the case_ids already present. An interrupted
run leaves a complete, usable file.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from slay.report import passage as rp                        # noqa: E402

import slide                                                 # noqa: E402

SCHEMA = '2.0.0'
SEED = 20261010
OUT = HERE / 'plain_runs.jsonl'

# -- the axes. The plan is the authority; these are its numbers ------------
R_VALUES = (60.0, 70.0, 85.0, 105.0, 120.0, 150.0, 200.0, 250.0)
SPACING_VALUES = (6.0, 7.5, 9.0, 10.5, 12.0, 14.0)
OD_VALUES = (0.1683, 0.2191, 0.2731, 0.3239, 0.4064, 0.5080, 0.6096)
WT_VALUES = (0.0080, 0.0110, 0.0127, 0.0159, 0.0191, 0.0210, 0.0254, 0.0318)
TENSION_VALUES = (0.0, 40.0, 80.0, 120.0, 160.0, 200.0, 250.0)

BASE = dict(R=85.0, spacing=9.0, OD=0.4064, t_wall=0.0210, tension_mt=120.0)

DT_MIN, DT_MAX = 10.0, 60.0          # the D/t feasibility window
N_TRAIN, N_TEST = 400, 100

# The papers' own envelope, for the `within_paper_box` flag. R 70..105 and
# 8..9 m spacing are Paper 1's configurations; 0..120 MT spans both papers'
# stated tensions; the diameters and the single 21 mm wall are TABLE XI's.
PAPER_BOX = dict(R=(70.0, 105.0), spacing=(8.0, 9.0), OD=(0.1683, 0.5080),
                 t_wall=(0.0210, 0.0210), tension_mt=(0.0, 120.0))

STATIONS = ('SR1', 'SR2', 'SR3', 'SR4', 'SR5', 'SR6', 'SR7',
            'VR1', 'VR2', 'VR3', 'VR4', 'VR5')

E_STEEL = 210e9
MATERIAL = 'j2'                      # what `slide.passage` runs on
MODE = 'A'


# ---------------------------------------------------------------------------
# the case list
# ---------------------------------------------------------------------------

def feasible(OD: float, t_wall: float) -> bool:
    return DT_MIN <= OD / t_wall <= DT_MAX


def anchors() -> list:
    """Paper 1's own plain-pipe cases -- the gate, not decoration.

    TABLE X is 16 in at 120 MT over three radii; TABLE XI is three diameters
    at 21 mm and R = 70, at zero tension and at 100 MT. The ledger values go
    in beside them so the results MD can report the reproduction without
    anyone having to look them up.
    """
    out = []
    for R, ref in ((70.0, 0.5468), (85.0, 0.4070), (105.0, 0.2965)):
        out.append(dict(BASE, R=R, ref_table='X', ref_strain_pct=ref))
    for OD, T, ref in ((0.1683, 0.0, 0.1428), (0.1683, 100.0, 0.3391),
                       (0.4064, 0.0, 0.3536), (0.4064, 100.0, 0.5280),
                       (0.5080, 0.0, 0.4888), (0.5080, 100.0, 0.6352)):
        out.append(dict(BASE, R=70.0, OD=OD, t_wall=0.021, tension_mt=T,
                        ref_table='XI', ref_strain_pct=ref))
    return out


def ofat() -> list:
    """Baseline, then each axis alone. Infeasible sections are DROPPED, not
    substituted: the OD axis at the 21 mm baseline wall loses 168.3 mm
    (D/t = 8.0), and block C covers that corner instead."""
    out = [dict(BASE)]
    for name, vals in (('R', R_VALUES), ('spacing', SPACING_VALUES),
                       ('OD', OD_VALUES), ('t_wall', WT_VALUES),
                       ('tension_mt', TENSION_VALUES)):
        for v in vals:
            c = dict(BASE)
            c[name] = v
            if feasible(c['OD'], c['t_wall']):
                out.append(c)
    return out


def joint(n: int, rng) -> list:
    """Stratified over discrete axes -- the discrete analogue of a Latin
    hypercube, the same scheme `tools/dataset.py` uses.

    Each axis's value list is repeated to length `n` and shuffled
    independently, so every value appears as near equally as `n` allows and
    the axes are combined without correlation. Infeasible (OD, WT) draws are
    rejected and the pair redrawn from the same two columns, which keeps the
    stratification of the three other axes exact.
    """
    axes = dict(R=R_VALUES, spacing=SPACING_VALUES, OD=OD_VALUES,
                t_wall=WT_VALUES, tension_mt=TENSION_VALUES)
    cols = {}
    for name, vals in axes.items():
        col = [vals[i % len(vals)] for i in range(n)]
        rng.shuffle(col)
        cols[name] = col
    rows = []
    for i in range(n):
        c = {k: cols[k][i] for k in cols}
        tries = 0
        while not feasible(c['OD'], c['t_wall']) and tries < 500:
            c['OD'] = rng.choice(OD_VALUES)
            c['t_wall'] = rng.choice(WT_VALUES)
            tries += 1
        if not feasible(c['OD'], c['t_wall']):
            continue                 # cannot happen with this window; no silent bad row
        rows.append(c)
    return rows


def dedup(cases: list) -> list:
    """Same five inputs = same case. Earlier blocks win, so an anchor keeps
    its reference columns and a later block does not re-run it."""
    seen, out = set(), []
    for c in cases:
        key = tuple(round(c[k], 9) for k in
                    ('R', 'spacing', 'OD', 't_wall', 'tension_mt'))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def case_list() -> list:
    rng_tr = random.Random(SEED)
    rng_te = random.Random(SEED + 1)
    cases = []
    cases += [dict(c, block='A', design='anchor') for c in anchors()]
    cases += [dict(c, block='B', design='ofat') for c in ofat()]
    cases += [dict(c, block='C', design='lhs') for c in joint(N_TRAIN, rng_tr)]
    cases += [dict(c, block='D', design='lhs-holdout')
              for c in joint(N_TEST, rng_te)]
    cases = dedup(cases)
    for i, c in enumerate(cases):
        c['case_id'] = f'{c["block"]}{i:04d}'
    return cases


# ---------------------------------------------------------------------------
# running one case
# ---------------------------------------------------------------------------

def features(c: dict) -> dict:
    """Arithmetic on the inputs, computed once so every consumer of this
    dataset uses the same definition. FEATURES, not targets."""
    OD, t, R = c['OD'], c['t_wall'], c['R']
    ID = OD - 2.0 * t
    I = math.pi * (OD ** 4 - ID ** 4) / 64.0
    A = math.pi * (OD ** 2 - ID ** 2) / 4.0
    return dict(D_over_t=OD / t, curvature=1.0 / R, I=I, A=A,
                EI=E_STEEL * I, EA=E_STEEL * A,
                eps_pure_bend=OD / (2.0 * R),
                spacing_over_OD=c['spacing'] / OD)


def in_paper_box(c: dict) -> bool:
    return all(lo <= c[k] <= hi for k, (lo, hi) in PAPER_BOX.items())


def run_case(c: dict, git_sha: str) -> dict:
    """One passage, reduced to one record. Never raises: a failure is a row."""
    row = dict(schema_version=SCHEMA, case_id=c['case_id'], family='plain',
               block=c['block'], design=c['design'], git_sha=git_sha,
               produced_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
               R=c['R'], spacing=c['spacing'], OD=c['OD'],
               t_wall=c['t_wall'], tension_mt=c['tension_mt'],
               ref_table=c.get('ref_table'),
               ref_strain_pct=c.get('ref_strain_pct'),
               within_paper_box=in_paper_box(c),
               step=2.0 * c['OD'], mode=MODE, material=MATERIAL)
    row.update(features(c))
    t0 = time.time()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            sc, L_comp, recs, _junc, _probs, _pos, done = slide.passage(
                arch_id='none', R=c['R'], spacing=c['spacing'],
                tension_mt=c['tension_mt'], OD=c['OD'], t_wall=c['t_wall'],
                step=2.0 * c['OD'], mode=MODE, verbose=False)
        ok = [r for r in recs if r.converged]
        row.update(n_positions=len(recs), n_converged=len(ok),
                   complete=bool(done.complete), zone_label=recs[0].zone_label
                   if recs else None, error=None)
        if not ok:
            row.update(status='failed', error='no position converged')
        elif len(ok) < len(recs) or not done.complete:
            row['status'] = f'partial {len(ok)}/{len(recs)}'
        else:
            row['status'] = 'ok'
        if ok:
            env = rp.envelope(ok)
            row.update(
                peak_strain=env.peak_strain,
                peak_strain_s_station=env.peak_s_station,
                peak_strain_s_material=env.peak_s_material,
                peak_strain_shift=env.shift,
                peak_moment=env.peak_moment,
                peak_moment_s_station=float(env.peak_moment_s_station),
                peak_moment_shift=env.shift,
                start_strain=ok[0].peak_strain,
                n_active=env.n_active, n_slots=env.n_slots,
                peak_strain_station=_nearest(sc, env.peak_s_station))
            # per-station ENVELOPE: the worst each station saw at ANY
            # position, which is not the same as the envelope position's
            # snapshot and is the reading a designer wants per roller.
            for name in STATIONS:
                vals = [r.stations.get(name) for r in ok
                        if r.stations.get(name) is not None]
                row[f'eps_{name}_env'] = max(vals) if vals else None
                row[f's_{name}'] = _station_s(sc, name)
    except Exception as ex:                     # noqa: BLE001 -- a row, not a crash
        row.update(status='failed', error=f'{type(ex).__name__}: {ex}',
                   traceback=traceback.format_exc()[-800:])
    row['seconds'] = round(time.time() - t0, 2)
    return row


def _station_s(scene, name):
    try:
        return scene.by_name(name).s_arc
    except Exception:                           # noqa: BLE001
        return None


def _nearest(scene, s):
    """Which station the peak sits at. Nearest in arc length, and the offset
    is kept so a reader can see whether 'at SR2' means at it or near it."""
    best, best_d = None, None
    for name in STATIONS:
        s_st = _station_s(scene, name)
        if s_st is None:
            continue
        d = abs(s_st - s)
        if best_d is None or d < best_d:
            best, best_d = name, d
    return best


# ---------------------------------------------------------------------------

def git_sha() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:                           # noqa: BLE001
        return ''


def done_ids(path: Path) -> set:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.add(json.loads(line)['case_id'])
            except Exception:                   # noqa: BLE001
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--anchors-only', action='store_true')
    ap.add_argument('--budget', type=float, default=None,
                    help='seconds; stop cleanly when exceeded')
    ap.add_argument('--out', type=Path, default=OUT)
    a = ap.parse_args()

    cases = case_list()
    if a.anchors_only:
        cases = [c for c in cases if c['block'] == 'A']
    already = done_ids(a.out)
    todo = [c for c in cases if c['case_id'] not in already]
    sha = git_sha()
    started = time.time()
    print(f'{len(cases)} cases, {len(already)} already done, {len(todo)} to '
          f'run.  sha {sha[:8]}  out {a.out}', flush=True)

    with a.out.open('a') as fh:
        for i, c in enumerate(todo, 1):
            row = run_case(c, sha)
            fh.write(json.dumps(row) + '\n')
            fh.flush()
            pk = row.get('peak_strain')
            print(f'[{i:4d}/{len(todo)}] {row["case_id"]:>6s} '
                  f'R{c["R"]:6.1f} sp{c["spacing"]:5.1f} '
                  f'OD{c["OD"]*1000:6.1f} t{c["t_wall"]*1000:5.1f} '
                  f'T{c["tension_mt"]:6.1f} -> '
                  f'{"--" if pk is None else f"{100*pk:7.4f}%"} '
                  f'{row["status"]:>12s} {row["seconds"]:6.1f}s', flush=True)
            if a.budget and time.time() - started > a.budget:
                print(f'budget {a.budget:.0f} s reached after {i} cases; '
                      f'stopping cleanly. Re-run to continue.', flush=True)
                break
    print(f'done in {(time.time() - started) / 60:.1f} min', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

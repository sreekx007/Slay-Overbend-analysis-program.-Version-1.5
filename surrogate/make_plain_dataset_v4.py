#!/usr/bin/env python3
"""make_plain_dataset_v4.py -- the v4 plain-pipelay dataset, case by case.

    python3 surrogate/make_plain_dataset_v4.py --anchors-only   # the gate
    python3 surrogate/make_plain_dataset_v4.py                  # everything
    python3 surrogate/make_plain_dataset_v4.py --budget 10800    # stop at 3 h

The design and the reason for every setting are in
`PLAN_plain_surrogate_v4.md` beside this file and are NOT restated here.
What this module owns is execution: build the case list, solve each case
through the entry point the published Sec. 1 tables use, read the nine
targets through the `report` layer, and append one JSON object per case.

WHY NOT `make_plain_dataset.py`. That runner produced the 525-case dataset
and has no notion of five things this one needs: a nested OD-and-wall
factorial rather than independent axes with a `D/t` window; the roller-count
rule that keeps the stinger at or above 40 m; a vessel pitch held apart from
the stinger pitch; a sweep travel passed per call; and per-station targets on
an element-counted window, with the strain decomposition and the roller
reactions, none of which the library carried when it was written. It is left
alone, with its dataset.

BLOCK A IS A STOP-GATE, NOT DECORATION. The nine published anchors run FIRST
and at the library's own 4 x OD travel, with no roller-count or vessel-pitch
argument at all -- the call the ledger's own numbers were produced by. If any
of the nine moves off its recorded value, `--anchors-only` says so and the
factorial is not started: the program has moved and the plan is stale.

FAILURES ARE DATA. A diverged or refused case is a row with its status and
its reason. A dataset holding only what converged is biased toward the easy
corner and says nothing about where the method stops working, which is what
a surrogate's user most needs to know.

CHECKPOINTED AFTER EVERY CASE and resumable by `case_id`, so an interrupted
run leaves a complete, usable file.
"""

from __future__ import annotations

import argparse
import json
import math
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

import config                                                # noqa: E402
from slay.report import passage as rp                         # noqa: E402

import slide                                                 # noqa: E402

SCHEMA = '4.0.0'
OUT = HERE / 'plain_runs_v4.jsonl'

TARGETS = ('SR1', 'SR2', 'SR3')

# -- the axes. The plan is the authority; these are its numbers ------------
R_VALUES = (85.0, 100.0, 115.0, 130.0, 145.0)
SPACING_VALUES = (4.0, 6.0, 8.0, 10.0, 12.0)
TENSION_VALUES = (60.0, 120.0, 180.0, 240.0)

# (NPS, OD m, [(schedule, wall m), ...]) -- three walls per NPS, spanning
# each pipe's layable range with a near-geometric middle in D/t. '5L' is an
# API 5L linepipe wall: ASME B36.10M stops at Sch 40 for NPS 32 and its
# other walls are D/t 102.6, 85.3 and 64.0, which nobody lays.
SECTIONS = (
    (6,  0.1683, (('40/STD', 0.00711), ('80/XS', 0.01097), ('120', 0.01427))),
    (10, 0.2731, (('40/STD', 0.00927), ('60/XS', 0.01270), ('100', 0.01826))),
    (16, 0.4064, (('30/STD', 0.00953), ('40/XS', 0.01270), ('80', 0.02144))),
    (24, 0.6096, (('30', 0.01427), ('60', 0.02461), ('80', 0.03096))),
    (32, 0.8128, (('40', 0.01748), ('5L', 0.02540), ('5L', 0.03175))),
)

MIN_STINGER_M = 40.0        # the stinger span floor; see `n_sr_for`
N_SR_FLOOR = 6              # the layout's own default gap count
SPACING_VR = 9.0            # the vessel pitch, held
N_VR = 5
TRAVEL_OD = 5.0             # the dataset's sweep travel, in diameters
STEP_OD = 2.0               # whole elements; see the plan on why not 1
LEDGER_TRAVEL_OD = 4.0      # `slide.PLAIN_TRAVEL_OD`, for block A4

G = 9.81                    # config.G, named here for the features
TON = 9806.65
E_STEEL = config.MATERIAL_J2_E
SIGMA_Y0 = config.MATERIAL_J2_TABLE[0][0]
RHO_STEEL = config.RHO_STEEL

# The nine published plain-pipe cases: Paper 1 TABLE X and XI, with the
# ledger value beside each so the gate needs nothing looked up.
ANCHORS = (
    ('X',  70.0, 0.4064, 0.021, 120.0, 0.5468),
    ('X',  85.0, 0.4064, 0.021, 120.0, 0.4070),
    ('X', 105.0, 0.4064, 0.021, 120.0, 0.2965),
    ('XI', 70.0, 0.1683, 0.021,   0.0, 0.1428),
    ('XI', 70.0, 0.1683, 0.021, 100.0, 0.3391),
    ('XI', 70.0, 0.4064, 0.021,   0.0, 0.3536),
    ('XI', 70.0, 0.4064, 0.021, 100.0, 0.5280),
    ('XI', 70.0, 0.5080, 0.021,   0.0, 0.4888),
    ('XI', 70.0, 0.5080, 0.021, 100.0, 0.6352),
)
ANCHOR_SPACING = 9.0
ANCHOR_TOL = 5e-5           # the ledger prints four decimals of a percent


def n_sr_for(spacing: float) -> int:
    """Stinger gaps, so the span never falls below `MIN_STINGER_M`.

    `n_sr` EXCLUDES the terminal tension station, so the scene carries
    `n_sr + 1` stinger stations and the span is `n_sr * spacing`. At the
    floor of 6 gaps a 4 m pitch would be a 24 m stinger -- a stub, not a lay
    -- so the count rises instead and the span runs 40, 42, 48, 60, 72 m
    across the spacing axis.
    """
    return max(N_SR_FLOOR, math.ceil(MIN_STINGER_M / spacing))


# ---------------------------------------------------------------------------
# the case list
# ---------------------------------------------------------------------------

def case_list() -> list:
    """Block A at both travels, then the factorial. Order is the plan's."""
    cases = []
    for travel, block in ((LEDGER_TRAVEL_OD, 'A4'), (TRAVEL_OD, 'A5')):
        for tab, R, OD, t, T, ref in ANCHORS:
            cases.append(dict(
                block=block, design='anchor', ref_table=tab,
                ref_strain_pct=ref, R=R, spacing=ANCHOR_SPACING, OD=OD,
                t_wall=t, tension_mt=T, travel_OD=travel,
                # NOTHING ELSE. The ledger's numbers came from a call with no
                # roller-count and no vessel-pitch argument, so block A makes
                # that call and the defaults stand.
                n_sr=None, spacing_vr=None, NPS=None, schedule='paper'))
    for nps, OD, walls in SECTIONS:
        for sch, t in walls:
            for R in R_VALUES:
                for spacing in SPACING_VALUES:
                    for T in TENSION_VALUES:
                        cases.append(dict(
                            block='F', design='factorial', ref_table=None,
                            ref_strain_pct=None, R=R, spacing=spacing, OD=OD,
                            t_wall=t, tension_mt=T, travel_OD=TRAVEL_OD,
                            n_sr=n_sr_for(spacing), spacing_vr=SPACING_VR,
                            NPS=nps, schedule=sch))
    for i, c in enumerate(cases):
        c['case_id'] = f'{c["block"]}{i:05d}'
    return cases


# ---------------------------------------------------------------------------
# features -- arithmetic on the inputs, computed once
# ---------------------------------------------------------------------------

def features(c: dict) -> dict:
    OD, t, R, sp = c['OD'], c['t_wall'], c['R'], c['spacing']
    ID = OD - 2.0 * t
    I = math.pi * (OD ** 4 - ID ** 4) / 64.0
    A = math.pi * (OD ** 2 - ID ** 2) / 4.0
    EI, EA = E_STEEL * I, E_STEEL * A
    n_sr = c['n_sr'] if c['n_sr'] is not None else N_SR_FLOOR
    sigma_axial = c['tension_mt'] * TON / A
    w = RHO_STEEL * A * G
    return dict(
        D_over_t=OD / t, curvature=1.0 / R,
        I=I, A=A, EI=EI, EA=EA,
        eps_pure_bend=OD / (2.0 * R),
        spacing_over_OD=sp / OD,
        pitch_angle=sp / R,
        arc_stinger=n_sr * sp,
        theta_stinger=n_sr * sp / R,
        n_sr_used=n_sr,
        w_per_m=w,
        sag_over_OD=w * sp ** 4 / (384.0 * EI * OD),
        sigma_axial=sigma_axial,
        axial_over_yield=sigma_axial / SIGMA_Y0,
        eps_axial_nominal=sigma_axial / E_STEEL,
        eps_yield=SIGMA_Y0 / E_STEEL,
        bend_over_yield=(OD / (2.0 * R)) / (SIGMA_Y0 / E_STEEL),
    )


# ---------------------------------------------------------------------------
# running one case
# ---------------------------------------------------------------------------

def _equilibrium(problem, result, scene) -> float:
    """|residual| / |applied|, vertical. The reaction target's own gate.

    Over the contact slots AND the FIXED station: the anchor is not a slot,
    so a sum over slots alone does not balance and a check that forgot it
    would fail by whatever the anchor carries. Recorded per row rather than
    once, so a case whose reactions are not trustworthy says so itself.
    """
    applied = sum(l.fy for l in problem.loads)
    slots = sum(f * scene.by_name(n).normal[1]
                for (n, f, _a) in result.reactions)
    anchor = sum(f for d, f in result.anchor_reactions if d % 3 == 1)
    if abs(applied) < 1.0:
        return float('nan')
    return abs(slots + anchor + applied) / abs(applied)


def run_case(c: dict, git_sha: str) -> dict:
    """One passage, reduced to one row. Never raises: a failure is a row."""
    row = dict(schema_version=SCHEMA, case_id=c['case_id'], family='plain',
               block=c['block'], design=c['design'], git_sha=git_sha,
               produced_at=datetime.now(timezone.utc)
               .isoformat(timespec='seconds'),
               R=c['R'], spacing=c['spacing'], OD=c['OD'],
               t_wall=c['t_wall'], tension_mt=c['tension_mt'],
               NPS=c['NPS'], schedule=c['schedule'],
               ref_table=c['ref_table'], ref_strain_pct=c['ref_strain_pct'],
               travel_OD=c['travel_OD'], step_OD=STEP_OD,
               spacing_vr=c['spacing_vr'] if c['spacing_vr'] is not None
               else c['spacing'],
               mode='A', material='j2', error=None)
    row.update(features(c))
    t0 = time.time()
    try:
        kw = {k: v for k, v in (('n_sr', c['n_sr']), ('n_vr', N_VR),
                                ('spacing_vr', c['spacing_vr']))
              if v is not None}
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            sc, _L, recs, _j, probs, pos, done = slide.passage(
                arch_id='none', R=c['R'], spacing=c['spacing'],
                tension_mt=c['tension_mt'], OD=c['OD'], t_wall=c['t_wall'],
                step=STEP_OD * c['OD'],
                clear_after=c['travel_OD'] * c['OD'],
                mode='A', verbose=False, **kw)

        ok_pos = [p for p in pos if p.converged]
        row.update(n_positions=len(pos), n_converged=len(ok_pos),
                   complete=bool(done.complete),
                   zone_label=recs[0].zone_label if recs else None,
                   n_sr_built=len([s for s in sc.stations
                                   if s.name.startswith('SR')]) - 1,
                   window_half_m=rp.station_window(sc, c['OD']))
        if not ok_pos:
            row.update(status='failed', error='no position converged')
        elif len(ok_pos) < len(pos) or not done.complete:
            row['status'] = f'partial {len(ok_pos)}/{len(pos)}'
        else:
            row['status'] = 'ok'

        if ok_pos:
            row.update(_targets(ok_pos, sc, probs, c['OD']))
            env = rp.envelope([r for r in recs if r.converged])
            first = ok_pos[0].result.strains
            row.update(peak_strain=env.peak_strain,
                       peak_moment=env.peak_moment,
                       peak_strain_station=env.peak_s_station,
                       # what a single-position solve would have reported
                       start_strain=(max(e for (_i, _s, e) in first)
                                     if first else None))
    except Exception as ex:                     # noqa: BLE001 -- a row, not a crash
        row.update(status='failed', error=f'{type(ex).__name__}: {ex}',
                   trace=traceback.format_exc()[-800:])
    row['seconds'] = round(time.time() - t0, 2)
    return row


def _targets(ok_pos, scene, problems, OD) -> dict:
    """The nine targets and their diagnostics, enveloped over the passage.

    EACH TARGET IS ENVELOPED INDEPENDENTLY. The position where a station sees
    its worst strain is not always where it sees its worst moment or its
    worst reaction, and a designer wants the worst of each -- so each carries
    its own `shift`. The decomposition and the element count travel with the
    STRAIN envelope, because they describe that element.
    """
    half = rp.station_window(scene, OD)
    best = {n: {} for n in TARGETS}
    released = {n: 0 for n in TARGETS}
    for p in ok_pos:
        vals = rp.station_values(p, scene, half, TARGETS)
        rx = rp.station_reactions(p, scene, TARGETS)
        for n in TARGETS:
            b = best[n]
            if n in vals:
                eps, m, ea, ka, n_el = vals[n]
                if 'eps' not in b or eps > b['eps']:
                    b.update(eps=eps, eps_shift=p.shift, eps_membrane=ea,
                             kappa=ka, n_elems=n_el)
                if not (math.isnan(m)) and ('M' not in b or m > b['M']):
                    b.update(M=m, M_shift=p.shift)
            if n in rx:
                f, act = rx[n]
                if not act:
                    released[n] += 1
                if 'react' not in b or f > b['react']:
                    b.update(react=f, react_shift=p.shift, react_active=act)
    out = {}
    for n in TARGETS:
        b = best[n]
        out[f'eps_total_{n}'] = b.get('eps')
        out[f'M_{n}'] = b.get('M')
        out[f'react_{n}'] = b.get('react')
        out[f'eps_membrane_{n}'] = b.get('eps_membrane')
        out[f'kappa_{n}'] = b.get('kappa')
        out[f'n_elems_{n}'] = b.get('n_elems')
        out[f'shift_eps_{n}'] = b.get('eps_shift')
        out[f'shift_M_{n}'] = b.get('M_shift')
        out[f'shift_react_{n}'] = b.get('react_shift')
        out[f'active_{n}'] = b.get('react_active')
        out[f'n_released_{n}'] = released[n]
        eps = b.get('eps')
        out[f'yielded_{n}'] = (None if eps is None
                               else bool(eps > SIGMA_Y0 / E_STEEL))
    # THE EQUILIBRIUM GATE, PER ROW, at the position that governs SR2's
    # strain -- the one the targets mostly come from, so the check is on the
    # state being reported rather than on an arbitrary position.
    gov = max(ok_pos, key=lambda q: _sr2_eps(q, scene, half))
    prob = problems[gov.index] if gov.index < len(problems) else None
    out['equil_resid_frac'] = (float('nan') if prob is None
                               else _equilibrium(prob, gov.result, scene))
    out['equil_at_shift'] = gov.shift
    return out


def _sr2_eps(position, scene, half) -> float:
    """SR2's strain at one position, or 0.0 if it has no element in window.

    Used only to pick the position the equilibrium check runs on, which is
    why a station with nothing near it sorts to the bottom rather than
    raising: the pick must never be the thing that fails a case.
    """
    v = rp.station_values(position, scene, half, ('SR2',))
    return v['SR2'][0] if 'SR2' in v else 0.0


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
        if line.strip():
            try:
                out.add(json.loads(line)['case_id'])
            except Exception:                   # noqa: BLE001
                pass
    return out


def check_anchors(rows) -> tuple:
    """`(ok, lines)` -- did block A4 reproduce the ledger?

    THE GATE. A4 is the ledger's own call, so any disagreement beyond the
    four decimals it prints means the program has moved under the plan.
    """
    lines, ok = [], True
    for r in rows:
        if r['block'] != 'A4' or r.get('peak_strain') is None:
            continue
        got, ref = 100.0 * r['peak_strain'], r['ref_strain_pct']
        d = got - ref
        good = abs(d) <= ANCHOR_TOL
        ok &= good
        lines.append(f'  TABLE {r["ref_table"]:2s} R{r["R"]:5.0f} '
                     f'OD{r["OD"]*1000:6.1f} T{r["tension_mt"]:5.0f}  '
                     f'got {got:.4f}%  ledger {ref:.4f}%  '
                     f'{"OK" if good else "*** MOVED ***"}')
    return ok, lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--anchors-only', action='store_true',
                    help='block A only -- the gate')
    ap.add_argument('--budget', type=float, default=None,
                    help='seconds; stop cleanly when exceeded')
    ap.add_argument('--out', type=Path, default=OUT)
    a = ap.parse_args()

    cases = case_list()
    if a.anchors_only:
        cases = [c for c in cases if c['block'].startswith('A')]
    already = done_ids(a.out)
    todo = [c for c in cases if c['case_id'] not in already]
    sha = git_sha()
    started = time.time()
    print(f'{len(cases)} cases, {len(already)} done, {len(todo)} to run.  '
          f'sha {sha[:8]}  out {a.out.name}', flush=True)

    written = []
    with a.out.open('a') as fh:
        for i, c in enumerate(todo, 1):
            row = run_case(c, sha)
            fh.write(json.dumps(row) + '\n')
            fh.flush()
            written.append(row)
            e2 = row.get('eps_total_SR2')
            print(f'[{i:5d}/{len(todo)}] {row["case_id"]:>7s} '
                  f'R{c["R"]:6.1f} sp{c["spacing"]:5.1f} '
                  f'OD{c["OD"]*1000:6.1f} t{c["t_wall"]*1000:5.2f} '
                  f'T{c["tension_mt"]:5.0f} -> SR2 '
                  f'{"--" if e2 is None else f"{100*e2:7.4f}%"} '
                  f'{row["status"]:>12s} {row["seconds"]:6.1f}s', flush=True)
            if a.budget and time.time() - started > a.budget:
                print(f'budget {a.budget:.0f} s reached after {i} cases; '
                      f'stopping cleanly. Re-run to continue.', flush=True)
                break

    gate_rows = [r for r in written if r['block'] == 'A4'] or \
        [json.loads(l) for l in a.out.read_text().splitlines()
         if l.strip() and json.loads(l)['block'] == 'A4']
    if gate_rows:
        ok, lines = check_anchors(gate_rows)
        print('\nBLOCK A4 -- the ledger gate')
        print('\n'.join(lines))
        print(f'  {"GREEN -- all nine reproduce" if ok else "RED"}')
        if not ok:
            print('  The factorial must NOT be run: the program has moved '
                  'and the plan is stale.')
            return 1
    print(f'\ndone in {(time.time() - started) / 60:.1f} min', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

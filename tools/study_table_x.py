#!/usr/bin/env python3
"""study_table_x.py -- Paper 1 TABLE X: peak strain by stinger configuration.

    python3 tools/study_table_x.py [--spacing 9] [--step-OD 2]

THE SIMPLEST TABLE IN THE PAPER, and the one that says most about the
R-trend. Three plain-pipe cases, 16 in pipeline at 120 MT, differing only in
stinger radius. The paper's governing phase is Phase 1, which is what
`report.passage.zone` cuts to.

WHY IT HAD TO BE RE-RUN. Every number in it predates L105 -- the lay tension
stayed bolted to one piece of steel for the whole passage, leaving a free
cantilever of travel-length with 120 MT on its unsupported tip -- and L106,
which is why passages stopped early. Nothing about plain pipe exempts it:
`sweep_length(0)` is still 2 m of travel, and the tension was wrong for all
of it.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import slide                                               # noqa: E402
from slay.report import passage as rp                      # noqa: E402
from slay.study import sweep                               # noqa: E402

OD = 0.4064
T_WALL = 0.021

# Config, radius, and the paper's Phase-1 peak strain. It publishes no
# moment for this table, so the moment column is ours alone.
CASES = (
    dict(config='A', R=70.0, fea=0.46),
    dict(config='B', R=85.0, fea=0.38),
    dict(config='C', R=105.0, fea=0.32),
)


def run_case(c, spacing, step_OD):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sc, L_comp, _recs, _junc, _probs, positions, done = slide.passage(
            arch_id='none', R=c['R'], spacing=spacing, tension_mt=120.0,
            OD=OD, t_wall=T_WALL, step=step_OD * OD, verbose=False)
    s_max, _label = rp.zone(sc)
    peak, at_s, bm = 0.0, None, 0.0
    for pos in positions:
        if not pos.converged:
            continue
        for (_i, s, e) in pos.result.strains:
            if s + pos.shift < s_max and abs(e) > peak:
                peak, at_s = abs(e), s + pos.shift
        for (_i, s, m) in getattr(pos.result, 'moments', ()):
            if s + pos.shift < s_max:
                bm = max(bm, abs(m))
    return dict(c=c, peak=peak, at_s=at_s, bm=bm,
                done=done)


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    spacing = arg('--spacing', float, 9.0)
    step_OD = arg('--step-OD', float, 2.0)

    print(f'Paper 1 TABLE X -- stinger configuration, 16 in, 120 MT, '
          f'{spacing:.0f} m spacing\n')
    print(f'{"cfg":4s} {"R":>5s} {"ours":>9s} {"paper":>7s} {"d%":>8s} '
          f'{"BM kN.m":>8s} {"at s":>7s} {"swept":>6s}')
    bad = []
    for c in CASES:
        r = run_case(c, spacing, step_OD)
        eps = 100 * r['peak']
        done = r['done']
        # A partial traverse carries no difference against the paper (L101).
        d = f'{100 * (eps / c["fea"] - 1):+7.1f}%' if done.complete else '   VOID'
        at = '     --' if r['at_s'] is None else f'{r["at_s"]:7.2f}'
        flag = '' if done.complete else f'{100 * done.fraction:5.0f}%'
        print(f'{c["config"]:4s} {c["R"]:4.0f}m {eps:8.4f}% {c["fea"]:6.2f}% '
              f'{d} {r["bm"] / 1000:8.1f} {at} {flag:>6s}', flush=True)
        if not done.complete:
            bad.append((c['config'], done))
    for cfg, done in bad:
        print(f'\n  {cfg}: {done}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

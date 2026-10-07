#!/usr/bin/env python3
"""study_table_xi.py -- Paper 1 TABLE XI: pipe diameter and tension at R = 70.

    python3 tools/study_table_xi.py [--R 70] [--spacing 9] [--step-OD 2]

WHY THIS TABLE IS WORTH MORE THAN ITS SIX ROWS. Every other comparison in
the ledger is one FEA against another FEA, so a shared modelling assumption
would cancel out of both sides and never show. TABLE XI is the only block in
Paper 1 carrying an INDEPENDENT ANALYTICAL CHECK: at zero tension the pipe is
bent to the stinger arc and nothing else, so the extreme-fibre strain is

    eps = D / 2R

with no solver in it at all. The paper reports its FEA against that closed
form and finds the gap WIDENS with diameter -- +8 pct at 6 in, +14 at 16 in,
+17 at 20 in -- which is itself a claim this program can check rather than
inherit.

So each zero-tension row is read three ways here: against the paper's FEA,
against the closed form, and -- the actual test -- against the paper's own
FEA-to-analytical gap. Reproducing the gap is a stronger result than
reproducing either number, because it is the part that cannot come from
having made the same modelling choice twice.

THE ZERO-TENSION ROWS MAY NOT CONVERGE, and that is a stated risk rather
than a surprise. A one-sided roller cannot pull: with no lay tension there
is nothing holding the pipe down onto the stinger, and the overbend is held
only by the pipe's own weight. The staged sequence exists for exactly this
(bend onto the arc with every roller gripping, THEN release), and a failure
here is a result to record, not a run to retry with different numbers.

PLAIN PIPE NEEDS NO SWEEP FOR ITS ENVELOPE -- there is no component edge to
cross, so the start position IS the envelope (RESULTS section 5.3). The
passage is run anyway, briefly, because that is also what makes the claim
checkable.
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

TON = 9806.65

# TABLE XI as published. `fea` is the paper's Abaqus value, `ana` its
# analytical D/2R where it gives one, `gap` the paper's own stated spread.
CASES = (
    dict(label='6 in',  OD=0.1683, t=0.021, T=0,   fea=0.13, ana=0.12, gap=8),
    dict(label='6 in',  OD=0.1683, t=0.021, T=100, fea=0.29, ana=None, gap=None),
    dict(label='16 in', OD=0.4064, t=0.021, T=0,   fea=0.33, ana=0.29, gap=14),
    dict(label='16 in', OD=0.4064, t=0.021, T=100, fea=0.42, ana=None, gap=None),
    dict(label='20 in', OD=0.508,  t=0.021, T=0,   fea=0.42, ana=0.36, gap=17),
    dict(label='20 in', OD=0.508,  t=0.021, T=100, fea=0.54, ana=None, gap=None),
)


def analytical(OD, R):
    """`eps = D / 2R`, the paper's own closed form.

    OD, not the mean diameter: this is the EXTREME FIBRE of a pipe bent to
    radius R, so the lever arm is OD/2 and the strain OD/(2R). The paper's
    own numbers confirm the reading -- 0.4064 / 170 = 0.239 pct against its
    stated 0.29 pct for 16 in would be a 19 pct discrepancy, while
    0.4064 / 140 = 0.290 pct matches to three figures at R = 70.
    """
    return OD / (2.0 * R)


def run_case(case, R, spacing, step_OD):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sc, L_comp, recs, _junc, _probs, positions = slide.passage(
            arch_id='none', R=R, spacing=spacing,
            tension_mt=float(case['T']), OD=case['OD'], t_wall=case['t'],
            step=step_OD * case['OD'], verbose=False)
    s_max, _label = rp.zone(sc)
    peak, at_s, bm = 0.0, None, 0.0
    n_ok = 0
    for pos in positions:
        if not pos.converged:
            continue
        n_ok += 1
        for (_i, s, e) in pos.result.strains:
            if s + pos.shift < s_max and abs(e) > peak:
                peak, at_s = abs(e), s + pos.shift
        for (_i, s, m) in getattr(pos.result, 'moments', ()):
            if s + pos.shift < s_max:
                bm = max(bm, abs(m))
    # `n_ok == n` is NOT "the passage finished". It says no position
    # diverged, which a schedule that ended short of the sweep length also
    # satisfies, and it says nothing about how much travel those positions
    # covered. `sweep.completion` measures the travel, which is the question
    # (L101). Plain pipe has L_comp = 0, so its sweep is the two clearances
    # and the distinction is small here -- it is kept uniform anyway, because
    # a tool that reports completion only for some cases is a tool a reader
    # has to check before trusting.
    return dict(case=case, peak=peak, at_s=at_s, bm=bm,
                n_ok=n_ok, n=len(positions),
                done=sweep.completion(positions, L_comp),
                status=('ok' if n_ok == len(positions)
                        else f'{n_ok}/{len(positions)}'))


def main() -> int:
    def arg(flag, cast=float, default=None):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    R = arg('--R', float, 70.0)
    spacing = arg('--spacing', float, 9.0)
    step_OD = arg('--step-OD', float, 2.0)

    print(f'Paper 1 TABLE XI -- diameter and tension at R = {R:.0f} m, '
          f'{spacing:.0f} m spacing\n')
    print(f'{"pipe":7s} {"T":>5s} {"ours":>9s} {"paper":>7s} {"d%":>7s}  '
          f'{"D/2R":>7s} {"ours/ana":>9s} {"paper/ana":>10s}  '
          f'{"BM kN.m":>8s}  {"at s":>6s}  conv')
    rows = []
    for c in CASES:
        r = run_case(c, R, spacing, step_OD)
        rows.append(r)
        eps = 100 * r['peak']
        # A partial traverse gets no difference against the paper (L101).
        d = (f'{100 * (eps / c["fea"] - 1):+6.1f}%' if r['done'].complete
             else '  VOID')
        if c['ana'] is not None and r['done'].complete:
            ana = 100 * analytical(c['OD'], R)
            ours_gap = f'{100 * (eps / ana - 1):+8.1f}%'
            pap_gap = f'{c["gap"]:+9d}%'
            anas = f'{ana:6.3f}%'
        else:
            anas, ours_gap, pap_gap = '     --', '       --', '        --'
        at = '    --' if r['at_s'] is None else f'{r["at_s"]:6.2f}'
        print(f'{c["label"]:7s} {c["T"]:4d}  {eps:8.4f}% {c["fea"]:6.2f}% {d}  '
              f'{anas} {ours_gap} {pap_gap}  {r["bm"] / 1000:8.1f}  '
              f'{at}  {r["status"]} {100 * r["done"].fraction:5.0f}%',
              flush=True)

    done = [r for r in rows if r['done'].complete]
    print(f'\n  {len(done)}/{len(CASES)} cases swept the full passage.')
    for r in rows:
        if not r['done'].complete:
            print(f'    {r["case"]["label"]} {r["case"]["T"]} MT: '
                  f'{r["done"]}')
    zero = [r for r in rows if r['case']['T'] == 0 and r['done'].complete]
    if len(zero) == 3:
        print('  The analytical check is available on all three diameters: '
              'the FEA-to-closed-form gap is what Paper 1 claims widens with '
              'diameter, and it is the one comparison here that does not rest '
              'on both sides having made the same modelling choice.')
    elif zero:
        print(f'  Only {len(zero)} of 3 zero-tension cases converged, so the '
              f'analytical trend is partial.')
    else:
        print('  NO zero-tension case converged, so the analytical check -- '
              'the whole reason this table is worth running -- is not '
              'available. A one-sided roller cannot pull.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

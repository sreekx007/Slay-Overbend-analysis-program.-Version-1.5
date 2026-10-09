#!/usr/bin/env python3
"""stage_run.py -- the four-step staged analysis, from the command line.

    python3 tools/stage_run.py [--R 85] [--tension 120] [--spacing 9]

THE SEQUENCE ITSELF IS `slay.study.staged` and the reporting window is
`slay.report.passage.zone`. This file is the CLI and the printing, and
nothing else.

It was not always. Until 9 Oct 2026 the workflow lived here, where
`check_layers` did not police it and nothing but this script could call it,
and it carried THREE copies of library code to make that work:
`all_bidirectional` (which `scene.scene` already had, and which `sweep`
already imported), the reporting window, and `DROP_AT_TIP`. The copies were
not equivalent -- `report.passage.zone` RAISES on a scene with too few
stinger rollers where the copy here silently indexed `sr[-3]` -- so the
weaker of each pair was the one in use.

WHAT STAYED HERE, and why that is the whole of a tool's job: argument
parsing, the choice of what to print, and the station profile, which is a
presentation of `result.strains` rather than a measurement of it.

REPORTING ZONE. Strains at the last three stinger rollers are excluded, the
21 Sep ruling. That is also what makes D6's terminal contact slot harmless:
it over-constrains the tip and concentrates strain at SR6, and the tip is
exactly the region excluded. The zone is printed beside every number so no
reader has to infer it.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))

from slay.report.passage import zone                        # noqa: E402
from slay.study.staged import run                           # noqa: E402


def peak_in_zone(result, s_max):
    """The worst strain strictly inboard of the reporting window."""
    rows = [(s, e) for (_i, s, e) in result.strains if s < s_max]
    return max(rows, key=lambda r: r[1]) if rows else (0.0, 0.0)


def station_profile(scene, result):
    """{station -> worst strain within half a bay of it}. PRESENTATION:
    it bins `result.strains` for a reader, and measures nothing."""
    out = {}
    for st in scene.stations:
        near = [e for (_i, s, e) in result.strains
                if abs(s - st.s_arc) < scene.spacing / 2.0]
        if near:
            out[st.name] = max(near)
    return out


def report(scene, stages, verbose=True):
    """Print the run. Returns `(s_max, s_peak, eps_peak)`."""
    s_max, label = zone(scene)
    if verbose:
        print(f'  zone: s < {s_max:.1f} m ({label})')
        print(f'  {"step":38s}{"status":>24}{"act":>7}'
              f'{"peak in zone":>14}{"at s":>8}')
        for st in stages:
            s_pk, e = peak_in_zone(st.result, s_max)
            tag = (f'{100 * e:13.4f}%{s_pk:8.2f}' if st.converged
                   else f'{"--":>14}{"":>8}')
            print(f'  {st.label:38s}{st.result.status:>24}'
                  f'{sum(st.result.active):3d}/{len(st.result.active):<3d}{tag}')
    s_pk, e = peak_in_zone(stages[-1].result, s_max)
    return s_max, s_pk, e


def main() -> int:
    def arg(flag, default):
        return (type(default)(sys.argv[sys.argv.index(flag) + 1])
                if flag in sys.argv else default)
    R = arg('--R', 85.0)
    T = arg('--tension', 120.0)
    spacing = arg('--spacing', 0.0) or None

    sc, stages, _state = run(R=R, tension_mt=T, spacing=spacing)
    print(f'R = {R:.0f} m   T = {T:.0f} MT   spacing = {sc.spacing:.0f} m')
    s_max, s_pk, eps = report(sc, stages)

    last = stages[-1]
    if not last.converged:
        print(f'\n  NO RESULT -- {last.label.strip()} did not converge')
        return 1

    print(f'\n  strain by station at the end of step 4 '
          f'(* = excluded from the result):')
    for name, e in station_profile(sc, last.result).items():
        st = sc.by_name(name)
        mark = ' *' if st.s_arc >= s_max else '  '
        print(f'   {mark}{name:>5}  s={st.s_arc:6.1f}   {100 * e:.4f}%')
    print(f'\n  RESULT  peak {100 * eps:.4f}% at s = {s_pk:.2f} m   '
          f'(* excluded: the last stinger rollers, per report.passage.zone)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

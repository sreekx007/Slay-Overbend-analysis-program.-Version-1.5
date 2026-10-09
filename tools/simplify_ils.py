#!/usr/bin/env python3
"""simplify_ils.py -- build a simplified ILS-SIMPLE for any layout.

    python3 tools/simplify_ils.py                      # the five GD-TP cases
    python3 tools/simplify_ils.py --case B3
    python3 tools/simplify_ils.py --archetype ILS-TP --L-OD 20 --t-mm 53
    python3 tools/simplify_ils.py --match flat --L2 0.5     # L2 in DIAMETERS

WHAT IT DOES. Measures a real ILS -- its stiffness, its length, how far it
holds the pipe off the rollers -- and builds the GD-Simple + GD-SH that
stands in for it: an elastic body of the PIPELINE's own section at an
equivalent modulus, on a shroud at the original's own depth and footprint.
The measuring and the arithmetic live in `slay.define.simplify`; this file
is the command line, the case list, and the artifact writer.

IT WRITES AN ARTIFACT AND DRAWS NOTHING (G13). `docs/simple/<case>.json`
carries the reduction, the five parameters, and what was reduced from.
`tools/plot_simple_ils.py` reads that file. A figure that re-derived the
reduction could not be checked against the reduction it claims to show.

SCOPE TODAY: GD-TP. Everything else is refused by name rather than
approximated -- a tapered body, two bodies, a frame carrying its stiffness
outside the pipe wall. The refusals are in `slay.define.simplify` and they
say what rule is missing, not just that it failed.

THE FIVE CASES are the GD-TP set selected for the GD-Simple comparison:
Paper 1 TABLE XXIII's B1/B2/B3/B4 and TABLE XX's A1. `R` and the lay
tension are recorded but NOT used by the reduction -- a reduction is a
statement about the hardware, not about the lay -- and are carried so the
sweep that follows does not have to look them up again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from slay.define.archetypes import (FIXTURE,            # noqa: E402
                                    build_component_ils)
from slay.define import simplify as sx                      # noqa: E402

D = 0.4064
OUT = REPO / 'docs' / 'simple'

# (table, R, tension_mt, L_OD, t_mm, paper strain %, our GD-TP strain %,
#  our GD-TP BODY moment kN.m)
#
# THE LAST TWO COLUMNS ARE OURS, NOT THE PAPER'S, and the moment is read on
# the COMPONENT BODY, which is where TABLE XXI and XXIV report it. They are
# Sec. 2's own rows, so a GD-Simple result is quoted against this build and
# never against a published figure it has no counterpart for.
#
# THE FIRST FIVE KEYS ARE HISTORICAL and their names do not carry the
# radius, because at the time only one radius of each was in play. The five
# added 8 Oct spell the radius out. Renaming the originals would orphan
# `docs/simple/simple_<case>.json` and the figures drawn from them, so the
# inconsistency is recorded here rather than tidied away: `B2` is R = 70 at
# 10 D / 65 mm while `B2_R85` is R = 85 at 10 D / 53 mm -- different wall as
# well as different radius, because TABLE XXII specifies 65 mm at R = 70 and
# 53 mm at R = 85, so the two radii are different components.
CASES = {
    # -- run 8 Oct, first five ------------------------------------------
    'A1':     ('XX',    100.0, 100.0,  2.5, 32, 0.339, 0.3771, 1182.7),
    'B1':     ('XXIII',  70.0, 100.0,  2.5, 65, 0.780, 0.8471, 1352.0),
    'B2':     ('XXIII',  70.0, 100.0, 10.0, 65, 1.499, 1.4161, 1604.0),
    'B3':     ('XXIII',  85.0, 100.0, 20.0, 53, 1.861, 1.2728, 1848.0),
    'B4':     ('XXIII',  85.0, 100.0, 40.0, 53, 1.914, 1.6413, 3253.0),
    # -- added 8 Oct, completing two length sweeps and one radius sweep --
    # A1 at 70 / 85 joins A1 at 100 above: the RADIUS axis at a fixed
    # 32 mm wall and 2.5 D length.
    'A1_R70': ('XX',     70.0, 100.0,  2.5, 32, 0.562, 0.6358, 1299.2),
    'A1_R85': ('XX',     85.0, 100.0,  2.5, 32, 0.473, 0.4804, 1247.1),
    # A3 at 85 gives a second WALL at that radius and length, against
    # A1_R85.
    'A3_R85': ('XX',     85.0, 100.0,  2.5, 53, 0.556, 0.6127, 1297.0),
    # B3_R70 completes R = 70 / 65 mm: 2.5 D (B1), 10 D (B2), 20 D here.
    # It is also the worst GD-TP disagreement against the paper, -21.4%.
    'B3_R70': ('XXIII',  70.0, 100.0, 20.0, 65, 2.514, 1.9763, 2053.0),
    # B2_R85 completes R = 85 / 53 mm: 2.5 D (A3_R85), 10 D here, 20 D
    # (B3), 40 D (B4).
    'B2_R85': ('XXIII',  85.0, 100.0, 10.0, 53, 1.104, 0.9267, 1494.0),
}


def reduce_case(name, L2_D, match):
    """One case: build the real GD-TP, reduce it, build the stand-in."""
    table, R, tension, L_OD, t_mm, eps_paper, eps_ours, bm_ours = CASES[name]
    ils = build_component_ils('ILS-TP', L_OD=L_OD, t_ratio=t_mm / 21.0)
    sm, eq = sx.simplify(ils, L2=L2_D * D if L2_D else sx.TAPER_MIN,
                         match=match)
    return dict(
        case=name, table=table, R=R, tension_mt=tension,
        source=dict(archetype='ILS-TP', code=eq.code, L_OD=L_OD, t_mm=t_mm,
                    OD_comp=eq.OD_comp, t_comp=eq.t_comp,
                    OD_pipe=eq.OD_pipe, t_pipe=eq.t_pipe),
        reference=dict(paper_strain_pct=eps_paper, gdtp_strain_pct=eps_ours,
                       gdtp_body_moment_kNm=bm_ours),
        equivalent=dict(L=eq.L, L_D=eq.L / D, depth=eq.depth,
                        depth_D=eq.depth / D, lift=eq.lift,
                        EI=eq.EI, EI_ratio=eq.EI_ratio,
                        E_equiv=eq.E_equiv, E_steel=eq.E_steel,
                        EA=eq.EA, EA_equiv=eq.EA_equiv,
                        EA_error=eq.EA_error),
        simple=dict(E=sm.E, L_body=sm.L_body, V=sm.V, L1=sm.L1, L2=sm.L2,
                    centre_x=sm.centre_x, match=match,
                    extent=list(sm.extent)),
        notes=[
            'EI is reproduced EXACTLY on the pipeline section; EA is not, '
            'and cannot be -- one modulus cannot match two stiffnesses. '
            f'Axial stiffness is {100 * eq.EA_error:+.1f}% out.',
            'The extreme-fibre distance stays the PIPELINE half-OD, so the '
            'same curvature gives a lower strain than the original did.',
            'The body is fully ELASTIC; the original is J2. That is the '
            'largest difference once the line yields.',
            f'L2 = {sm.L2:g} m, not 0: a GD-TP steps abruptly and '
            '`OffsetShroud.validate` refuses a zero taper in a MIRRORED '
            'file (G7).',
        ])


def main() -> int:
    def arg(flag, cast, default):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    match = arg('--match', str, 'total')
    L2_D = arg('--L2', float, 0.0)          # 0 => TAPER_MIN
    only = arg('--case', str, '')
    arch = arg('--archetype', str, '')

    if arch:
        ils = build_component_ils(
            arch, L_OD=arg('--L-OD', float, None),
            t_ratio=(arg('--t-mm', float, 0.0) / 21.0) or None)
        sm, eq = sx.simplify(ils, L2=L2_D * D if L2_D else sx.TAPER_MIN,
                             match=match)
        print(f'{arch} -> ILS-SIMPLE: E {eq.E_equiv / 1e9:.0f} GPa, '
              f'L_body {sm.L_body:.4f} m, V {sm.V:.4f} m, L1 {sm.L1:.4f} m, '
              f'L2 {sm.L2:g} m  (EA {100 * eq.EA_error:+.1f}%)')
        return 0

    names = [only] if only else list(CASES)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f'ILS-SIMPLE from GD-TP.  match = {match}, '
          f'L2 = {L2_D:g} D' if L2_D else
          f'ILS-SIMPLE from GD-TP.  match = {match}, '
          f'L2 = TAPER_MIN ({sx.TAPER_MIN:g} m)')
    print('  *** a REDUCTION, not a result. EI is matched exactly; EA is '
          'not, the fibre\n      distance is the pipeline\'s, and the body '
          'cannot yield. See the notes in each file.')
    print()
    print(f'{"case":5s}{"src":>12s}{"L/D":>7s}{"V/D":>7s}{"lift":>8s}'
          f'{"EI/EI_p":>9s}{"E equiv":>9s}{"EA err":>8s}{"L1/D":>9s}')
    rows = []
    for name in names:
        r = reduce_case(name, L2_D, match)
        rows.append(r)
        e, s_ = r['equivalent'], r['simple']
        path = OUT / f'simple_{name.lower()}.json'
        path.write_text(json.dumps(r, indent=2, sort_keys=True) + '\n')
        print(f'{name:5s}{r["source"]["t_mm"]:>7d}mm'
              f'{e["L_D"]:7.2f}{e["depth_D"]:7.3f}'
              f'{1000 * e["lift"]:7.1f}m{e["EI_ratio"]:9.3f}'
              f'{e["E_equiv"] / 1e9:8.0f}G{100 * e["EA_error"]:+7.1f}%'
              f'{s_["L1"] / D:9.4f}')
    print()
    for r in rows:
        print(f'  wrote docs/simple/simple_{r["case"].lower()}.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

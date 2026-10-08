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

import plot_stinger as gen                                  # noqa: E402
from slay.define import simplify as sx                      # noqa: E402

D = 0.4064
OUT = REPO / 'docs' / 'simple'

# (case, table, R, tension_mt, L_OD, t_mm, paper strain, our GD-TP strain)
CASES = {
    'A1': ('XX',    100.0, 100.0,  2.5, 32, 0.339, 0.3771),
    'B1': ('XXIII',  70.0, 100.0,  2.5, 65, 0.780, 0.8471),
    'B2': ('XXIII',  70.0, 100.0, 10.0, 65, 1.499, 1.4161),
    'B3': ('XXIII',  85.0, 100.0, 20.0, 53, 1.861, 1.2728),
    'B4': ('XXIII',  85.0, 100.0, 40.0, 53, 1.914, 1.6413),
}


def reduce_case(name, L2_D, match):
    """One case: build the real GD-TP, reduce it, build the stand-in."""
    table, R, tension, L_OD, t_mm, eps_paper, eps_ours = CASES[name]
    ils = gen.build_component_ils('ILS-TP', L_OD=L_OD, t_ratio=t_mm / 21.0)
    sm, eq = sx.simplify(ils, L2=L2_D * D if L2_D else sx.TAPER_MIN,
                         match=match)
    return dict(
        case=name, table=table, R=R, tension_mt=tension,
        source=dict(archetype='ILS-TP', code=eq.code, L_OD=L_OD, t_mm=t_mm,
                    OD_comp=eq.OD_comp, t_comp=eq.t_comp,
                    OD_pipe=eq.OD_pipe, t_pipe=eq.t_pipe),
        reference=dict(paper_strain_pct=eps_paper, gdtp_strain_pct=eps_ours),
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
        ils = gen.build_component_ils(
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

#!/usr/bin/env python3
"""slide_plain.py -- sequential sliding for PLAIN pipeline.

Step 6 of the physics sequence (`docs/modules/T9_physics_sequence.md`), run
on plain pipe before any component case: slide the pipeline a stated number
of diameters in stated steps, solving at each position and carrying state
forward.

WHY THE ORIGINAL AND NOT THE REBUILD. The rebuild has the per-position
solver (`slay/solve/passage.py`, the port of `_solve_state_sliding`) but NOT
the sweep driver -- the placement rule, the shift schedule and the
re-computation of where each roller bears. That is T6 / L7 and is unbuilt,
so sliding runs through `slay_sliding_v0_4.run_passage_sliding` for now.

THE NEUTRAL COMPONENT, and it is a device, not a model. That entry point
refuses a plain-pipe case outright ("need shroud_component and/or
thick_component"), which is the gap trial T008 recorded. Passing a component
whose OD and wall EQUAL the pipe's gets past the guard and is physically
plain pipe: `SEC2` is then identical to `SEC1`, and the contact lift
`CL_thick = (OD_tc - D_o)/2` is exactly zero. Checked at R = 85, 120 MT:
0.3962% against `run_slay`'s 0.3937% for the same case through a different
entry point. Nothing is edited in the reference program (G6).

SHIFTS ARE ELEMENT UNITS, travel is metres. `travel = shift *
elem_len_sr2`, so a travel specified in diameters becomes a FRACTIONAL
shift -- which v0.4 supports deliberately: "Because `shift` is now a float,
the sweep is no longer locked to 0.8 m".

    python3 tools/slide_plain.py [--R 70,85,105] [--tension 120]
                                 [--od-travel 4] [--od-step 1] [--spacing 8]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import slay_sliding_v0_4 as SL                       # noqa: E402

OD_DEF = 0.4064
WT_DEF = 0.021
DROP_AT_TIP = 3          # SR5, SR6, SR7 excluded, per the physics sequence

# TABLE XI of the paper: three diameters, ALL at 21 mm wall, R = 70 m.
# Travel and step are each pipeline's OWN diameter, so the passage is the
# same in pipe-diameters for every pipe and different in metres.
PAPER_PIPES = ((0.168, 0.021, '6 in'),
               (0.4064, 0.021, '16 in'),
               (0.508, 0.021, '20 in'))


def neutral_component(od, wt):
    """Identical to the pipe: same OD, same wall. See the module docstring."""
    return {'OD': od, 't': wt, 'length': 1.000}


def slide(R, od=OD_DEF, wt=WT_DEF, tension_mt=120.0, spacing=8.0,
          od_travel=4.0, od_step=1.0, n_sr=6, n_vr=10, elem_len=None):
    """One sliding passage. Returns (result dict, shifts, step_m)."""
    kw = dict(R=R, D_o=od, t=wt, thick_component=neutral_component(od, wt),
              tension_mt=tension_mt, n_sr=n_sr, n_vr=n_vr, spacing=spacing,
              elem_len=elem_len, verbose=False)
    elem = SL.run_passage_sliding(shifts=[0.0], **kw)['elem_len_sr2']

    step_m = od_step * od
    n_steps = int(round(od_travel / od_step))
    shifts = [i * step_m / elem for i in range(n_steps + 1)]
    return SL.run_passage_sliding(shifts=shifts, **kw), shifts, step_m


def zone(res):
    """(x_tip_cut, x_vr1) -- the reporting band of Step 7.

    Excluded at the stinger end: the last `DROP_AT_TIP` stations, because
    that is where the model cuts the pipe and substitutes a pull for the
    catenary. Excluded at the deck end: everything vessel-side of VR1, which
    is the reference program's own mask (`xm < x_vr1`) and keeps the
    restraint artefact out.
    """
    allc = [c[0] for c in res['allc']]
    return allc[len(allc) - DROP_AT_TIP], allc[1]


def peak_in_zone(step, cut, x_vr1):
    """Largest strain in the band, from the stored profile.

    Reading `peak_NE` instead would report the WHOLE-model peak and, when
    that lands in the excluded tip, say nothing about the band at all --
    which is what the first version of this tool did.
    """
    xs, ne = step['x_profile'], step['NE_profile']
    rows = [(float(e), float(x)) for x, e in zip(xs, ne)
            if cut < x < x_vr1]
    return max(rows) if rows else (0.0, 0.0)


def main() -> int:
    def arg(flag, default):
        return (type(default)(sys.argv[sys.argv.index(flag) + 1])
                if flag in sys.argv else default)
    radii = [float(v) for v in arg('--R', '70,85,105').split(',')]
    T = arg('--tension', 120.0)
    spacing = arg('--spacing', 8.0)
    od_travel = arg('--od-travel', 4.0)
    od_step = arg('--od-step', 1.0)
    # --pipes runs the paper's three diameters instead of one; --od/--wt
    # runs a single named pipe.
    if '--pipes' in sys.argv:
        pipes = list(PAPER_PIPES)
    else:
        pipes = [(arg('--od', OD_DEF), arg('--wt', WT_DEF), 'pipe')]

    print(f'PLAIN PIPELINE, sequential sliding.  T = {T:.0f} MT,  '
          f'spacing {spacing:.0f} m')
    print(f'travel {od_travel:g} x OD   step {od_step:g} x OD   '
          f'({int(round(od_travel / od_step))} steps after the start) '
          f'-- both scale with EACH pipe\'s own diameter\n')

    for od, wt, label in pipes:
      for R in radii:
        res, shifts, step_m = slide(R, od=od, wt=wt, tension_mt=T,
                                    spacing=spacing, od_travel=od_travel,
                                    od_step=od_step)
        cut, x_vr1 = zone(res)
        print(f'--- {label}  OD {od * 1000:.1f} x {wt * 1000:.0f} mm   '
              f'R = {R:.0f} m   travel {od_travel * od:.4f} m in '
              f'{step_m:.4f} m steps')
        print(f'    (1 shift unit = {res["elem_len_sr2"]:.4f} m,  band '
              f'{cut:.2f} < x < {x_vr1:.2f})')
        print(f'  {"pos":>4}{"shift":>9}{"travel":>10}'
              f'{"peak in band":>14}{"at x":>9}'
              f'{"whole-model":>13}{"at x":>9}  status')
        band = []
        for i, st in enumerate(res['steps']):
            e, x = peak_in_zone(st, cut, x_vr1)
            band.append((100 * e, x))
            print(f'  {i:>4}{st["shift"]:9.4f}{st["travel_m"]:9.4f}m'
                  f'{100 * e:13.4f}%{x:9.2f}'
                  f'{100 * st["peak_NE"]:12.4f}%{st["peak_x"]:9.2f}'
                  f'  {st["status"]}')
        worst = max(band)
        print(f'  PASSAGE PEAK {worst[0]:.4f}% at x = {worst[1]:.2f}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""study_simple.py -- GD-Simple: an elastic pipe body over an offset shroud.

    python3 tools/study_simple.py [--R 85] [--spacing 9] [--tension 100]
                                  [--E 210] [--L-body 10] [--V 1.5]
                                  [--L1 10] [--L2 2.5] [--step 2]
                                  [--E-sweep 50,100,210,400]

Every length flag is in PIPE DIAMETERS; `--E` and `--E-sweep` are in GPa.
`--tension` is in MT. The conversions happen once, here, because
`slay.define.simple` works in metres and pascals and does not know what a
diameter is.

WHAT IT REPORTS. Two regions, per `slay.report.regions`:

    Xb   inside the body of the component
    Xe   outside it, the pipeline either side -- TWO spans, not one

and `Xb/Xe` as the ratio, which is the question the scheme is drawn to
answer: does the component carry more strain than the pipe it displaces, or
less.

NO PUBLISHED COUNTERPART. Neither paper defines a GD-Simple, so nothing
here is validation and no column is a delta against a reference. The
comparison that means something is INTERNAL -- one modulus against another,
or Xb against Xe at the same modulus -- which is also why `--E-sweep`
exists.

THE CONTROL CASE IS `--E 210 --R 250`, and it is worth running first. At
the pipeline's own modulus the body differs from plain pipe in exactly one
way -- it cannot yield -- so where nothing yields anyway it must be
indistinguishable from pipe. Measured 8 Oct 2026: Xb 0.2031% against Xe
0.2031%, ratio **1.000**. That is the whole chain verified at once: the
modulus override landed, the elastic law landed, and the region boundary is
where the body is.

`--E 210` AT A LAY RADIUS THAT YIELDS IS NOT A CONTROL, and reading it as
one would be a mistake worth naming. At R = 85 the same case gives Xb
0.3161% against Xe 1.1110%, a ratio of 0.285 -- and that is a RESULT, not a
defect. The pipe either side is plastic at 1.1%, where its tangent modulus
has collapsed to E*H/(E+H); the body cannot yield, so it stays on the full
210 GPa, becomes by far the stiffer member, and sheds curvature into its
softer neighbours while taking more moment (1451 against 1361 kN.m). The
effect is large: a bare shroud of the same V, L1 and L2 peaks at 0.8223%,
so inserting a non-yielding body of its own pipeline section makes the
adjacent pipe **35% worse**.

That asymmetry is the component's actual mechanism and the reason to run it.
It also means Xb < Xe is the NORMAL reading once the line is plastic, and
Xb/Xe is a measure of how much strain the body is pushing outboard rather
than a measure of how hard the body is working.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from slay.data.materials import material                    # noqa: E402
from slay.define import simple as sp                        # noqa: E402
import json                                                 # noqa: E402
from slay.model.assemble import build_model                 # noqa: E402
from slay.physics.problem import build_problem              # noqa: E402
from slay.report import passage as rp                       # noqa: E402
from slay.report import regions as rg                       # noqa: E402
from slay.study import sweep                                # noqa: E402

D = 0.4064
TON = 9.80665e3


def run_reduction(rec, spacing, step_OD, mesh_OD=None):
    """Sweep one ILS-SIMPLE built from a reduction artifact.

    THE SOLVED CASE IS THE ONE THAT WAS WRITTEN DOWN AND DRAWN. The five
    parameters come out of `docs/simple/<case>.json` verbatim rather than
    being recomputed here, so the figure, the artifact and this result
    cannot describe three slightly different components.
    """
    s_, e_ = rec['simple'], rec['equivalent']
    sm = sp.build(E=s_['E'], L_body=s_['L_body'], V=s_['V'], L1=s_['L1'],
                  L2=s_['L2'], centre_x=s_['centre_x'])
    return (_sweep(sm, rec['R'], spacing, rec['tension_mt'], step_OD,
                   mesh_OD), sm, e_)


def _sweep(sm, R, spacing, tension_mt, step_OD, mesh_OD=None):
    """Solve the passage and measure it. Pure; prints nothing.

    `mesh_OD` is the ELEMENT LENGTH in diameters, not the sweep advance.
    The two are independent and are easy to confuse: `step_OD` is how far
    the pipe moves between positions, `mesh_OD` is how finely it is cut up.
    None leaves the mesher on its ruled density (G10, 2 x OD).
    """
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=R, spacing=spacing, L_comp=L)
    s_centre = sweep.start_centre(scene, L)
    pkw = dict(elastic_spans=sm.elastic_spans(s_centre),
               E_by_owner=sm.E_by_owner())
    mkw = {} if mesh_OD is None else dict(target_len=mesh_OD * D)
    positions = sweep.run(scene, sm.ils, L_comp=L, step=step_OD * D,
                          tension=tension_mt * TON, material=material('j2'),
                          **pkw, **mkw)
    recs = rp.measure(positions, scene, L_comp=L)
    env = rp.envelope(recs)
    model = build_model(scene, sm.ils, s_centre=s_centre,
                        extra_stations=sweep._required_stations(scene),
                        **mkw)
    p0 = build_problem(
        model, scene, shift=positions[env.index].shift, s_centre=s_centre,
        tension=tension_mt * TON, material=material('j2'),
        **sweep.with_buffer(scene, pkw, assembly=sm.ils.assembly,
                            ils=sm.ils))
    geom = rg.simple_geometry(sm.ils, s_centre)
    if geom is None:
        raise SystemExit('simple_geometry did not recognise this assembly')
    return dict(geom=geom,
                peaks=rg.region_peaks(positions, p0, geom, env.zone_s_max),
                done=sweep.completion(positions, L, clear_before=1.0,
                                      clear_after=1.0),
                env=env, n=len(positions),
                n_ok=sum(1 for r in recs if r.converged))


def run_case(E_GPa, L_body_D, V_D, L1_D, L2_D, R, spacing, tension_mt,
             step_OD):
    """Solve one GD-Simple passage and measure it. Pure; prints nothing."""
    sm = sp.build(E=E_GPa * 1.0e9, L_body=L_body_D * D, V=V_D * D,
                  L1=L1_D * D, L2=L2_D * D)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=R, spacing=spacing, L_comp=L)
    s_centre = sweep.start_centre(scene, L)

    # ONE dict for the solve and for the re-pose. `E_by_owner` gives the body
    # its modulus; the elastic span stops it yielding. Both must reach BOTH
    # calls or `differs_only_in_contact` is right to say they are not the
    # same problem -- and `with_buffer` is what keeps the feedstock buffer's
    # own elastic span from being replaced by the body's (L109).
    pkw = dict(elastic_spans=sm.elastic_spans(s_centre),
               E_by_owner=sm.E_by_owner())

    positions = sweep.run(scene, sm.ils, L_comp=L, step=step_OD * D,
                          tension=tension_mt * TON, material=material('j2'),
                          **pkw)
    recs = rp.measure(positions, scene, L_comp=L)
    env = rp.envelope(recs)

    model = build_model(scene, sm.ils, s_centre=s_centre,
                        extra_stations=sweep._required_stations(scene))
    p0 = build_problem(
        model, scene, shift=positions[env.index].shift, s_centre=s_centre,
        tension=tension_mt * TON, material=material('j2'),
        **sweep.with_buffer(scene, pkw, assembly=sm.ils.assembly,
                            ils=sm.ils))

    geom = rg.simple_geometry(sm.ils, s_centre)
    if geom is None:
        raise SystemExit(
            'simple_geometry did not recognise this assembly as a '
            'GD-Simple. That is a defect, not a result -- the scheme keys on '
            'the shape (a neutral body owning a span over a shroud that '
            'owns contact) and one of those two facts is not true of what '
            'was built.')
    peaks = rg.region_peaks(positions, p0, geom, env.zone_s_max)
    done = sweep.completion(positions, L, clear_before=1.0, clear_after=1.0)
    return dict(simple=sm, geom=geom, peaks=peaks, done=done,
                n=len(positions),
                n_ok=sum(1 for r in recs if r.converged))


def _cell(r):
    """A region's peak, or `--` when the region holds no elements.

    L097: an unmeasured region printed as `0.0000%` reads as a measured zero
    strain, and nobody checks a quiet number.
    """
    if not r['measured']:
        return f'{"--":>9s}'
    return f'{100 * r["peak_strain"]:8.4f}%'


def main() -> int:
    def arg(flag, cast, default):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    # --FROM-ARTIFACTS: sweep the reductions `simplify_ils.py` wrote.
    if '--from-artifacts' in sys.argv:
        src = REPO / 'docs' / 'simple'
        only = arg('--case', str, '')
        files = ([src / f'simple_{only.lower()}.json'] if only
                 else sorted(src.glob('simple_*.json')))
        spacing = arg('--spacing', float, 9.0)
        # 1 x OD, matching `study_table_xxiii.py`'s own default. The GD-TP
        # numbers these are compared against were swept at that advance, and
        # a different one would change the envelope before any physics did.
        step_OD = arg('--step-OD', float, 1.0)
        mesh_OD = arg('--mesh-OD', float, 0.0) or None
        print(f'ILS-SIMPLE swept from the reductions in docs/simple/.  '
              f'spacing {spacing:.0f} m, step {step_OD:g} x OD, mesh '
              f'{"ruled 2 x OD" if mesh_OD is None else f"{mesh_OD:g} x OD"}')
        print('  *** PREDICTION, no published counterpart. The GD-TP column '
              'is OUR OWN earlier\n      result for the layout each case '
              'was reduced from -- not a reference value.')
        print()
        # Xe AGAINST THE GD-TP PEAK, not Xb. A GD-TP's governing strain
        # sits at the PIPE-TO-COMPONENT JUNCTION -- the ledger's TABLE XX
        # note says so in as many words -- which is outboard of the body
        # and therefore in Xe's territory, not Xb's. Quoting Xb against it
        # compares two different pieces of steel and reads as a 90%
        # shortfall that is really a change of location.
        print(f'{"case":5s}{"R":>5s}{"E/GPa":>7s}{"Xb":>10s}{"Xe":>10s}'
              f'{"Xb/Xe":>7s}{"GD-TP":>9s}{"Xe/GDTP":>9s}'
              f'{"Xb M":>9s}{"dM":>7s}{"el b/e":>9s}  passage')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for f in files:
                rec = json.loads(f.read_text())
                r, sm, e_ = run_reduction(rec, spacing, step_OD, mesh_OD)
                xb, xe = r['peaks']['Xb'], r['peaks']['Xe']
                gdtp = rec['reference']['gdtp_strain_pct']
                bm = rec['reference']['gdtp_body_moment_kNm']
                ratio = (xb['peak_strain'] / xe['peak_strain']
                         if xe['measured'] and xe['peak_strain'] > 0 else 0.0)
                print(f'{rec["case"]:5s}{rec["R"]:5.0f}'
                      f'{e_["E_equiv"] / 1e9:7.0f}'
                      f'{_cell(xb):>10s}{_cell(xe):>10s}{ratio:7.3f}'
                      f'{gdtp:8.4f}%'
                      # BOTH SIDES IN PER CENT. `peak_strain` is a
                      # FRACTION and the recorded GD-TP figure is a per
                      # cent, so dividing them raw under-reports by 100 --
                      # this printed 0.4% for what is 41.8%.
                      f'{100.0 * (100.0 * xe["peak_strain"]) / gdtp:8.1f}%'
                      f'{xb["peak_moment"] / 1e3:8.0f}k'
                      # Against the GD-TP BODY moment, which is where
                      # TABLE XXI and XXIV report it and what Sec. 2 records.
                      f'{100.0 * (xb["peak_moment"] / 1e3 / bm - 1.0):+6.1f}%'
                      f'{xb["n_elements"]:4d}/{xe["n_elements"]:<4d} '
                      f'{"full" if r["done"].complete else str(r["done"])}')
        return 0

    R = arg('--R', float, 85.0)
    spacing = arg('--spacing', float, 9.0)
    tension = arg('--tension', float, 100.0)
    L_body = arg('--L-body', float, 10.0)
    V = arg('--V', float, 1.5)
    L1 = arg('--L1', float, 10.0)
    L2 = arg('--L2', float, 2.5)
    step = arg('--step', float, 2.0)
    sweep_E = arg('--E-sweep', str, '')
    Es = ([float(x) for x in sweep_E.split(',')] if sweep_E
          else [arg('--E', float, 210.0)])

    print(f'GD-Simple.  R = {R:.0f} m, spacing = {spacing:.0f} m, '
          f'{tension:.0f} MT, step = {step:g} x OD')
    print(f'  body  L = {L_body:g} D, fully ELASTIC, pipeline section')
    print(f'  shroud  V = {V:g} D (pipe C/L to bottom flat), '
          f'L1 = {L1:g} D, L2 = {L2:g} D')
    print('  *** NO PUBLISHED COUNTERPART. Neither paper defines a '
          'GD-Simple, so every\n      number below is a PREDICTION and the '
          'comparisons are internal only.')
    print()
    print(f'{"E/GPa":>7s} {"Xb (body)":>10s} {"Xe (pipe)":>10s} '
          f'{"Xb/Xe":>7s} {"Xb M":>9s} {"Xe M":>9s} '
          f'{"el b/e":>8s}  passage')

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for E in Es:
            r = run_case(E, L_body, V, L1, L2, R, spacing, tension, step)
            xb, xe = r['peaks']['Xb'], r['peaks']['Xe']
            ratio = (xb['peak_strain'] / xe['peak_strain']
                     if xe['measured'] and xe['peak_strain'] > 0 else 0.0)
            print(f'{E:7.0f} {_cell(xb):>10s} {_cell(xe):>10s} '
                  f'{ratio:7.3f} '
                  f'{xb["peak_moment"] / 1e3:8.0f}k {xe["peak_moment"] / 1e3:8.0f}k '
                  f'{xb["n_elements"]:3d}/{xe["n_elements"]:<4d} '
                  f'{"full" if r["done"].complete else str(r["done"])}')
            g = r['geom']
            if not g.body_covers_shroud:
                print(f'{"":7s}   note: the body ({g.L_body / D:.2f} D) does '
                      f'NOT cover the shroud ({g.L_total / D:.2f} D), so part '
                      f'of the lift is in Xe\n{"":7s}         and Xe is not '
                      f'plain unlifted pipe.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

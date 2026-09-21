#!/usr/bin/env python3
"""stage_run.py -- the four-step staged analysis, as specified 21 Sep 2026.

    1  displacements   contact targets ramped 0 -> 1. ELASTIC, and EVERY
                       roller BIDIRECTIONAL -- nothing may lift off, so the
                       pipe is driven onto the arc with no active set to
                       chatter and no load fighting it.
    2  gravity         gravity on, ELASTIC, and LIFT-OFF ACTIVATED: the ruled
                       one-sided set takes effect and rollers may release.
    3  tension         lay tension at SR7. ELASTIC.
    4  plasticity      material switched to J2, everything else held.

WHY THIS ORDER WORKS where a single proportional solve does not. The blocker
this project spent the day on is that 120 MT on a straight, unstressed pipe
has nothing to react it: no geometric stiffness exists yet, the first Newton
step is 3.2 m against a 1.0 m threshold, and it diverges (L050, L051). Here
the pipe is already bent to the arc and already carrying its own weight
before the tension arrives, so the stiffness that reacts it is there by the
time it is needed.

Step 1's all-bidirectional set matters for the same reason from the other
side: a one-sided roller cannot pull, so with no tension yet applied the
stinger rollers would release and the pipe would never reach the arc at all
(panel B of `stinger_pipe.png` at zero tension is that picture). Holding
every roller through step 1 builds the geometry; step 2 then hands the
active set its real rule and lets whatever wants to lift off, lift off.

MATERIAL. `build_problem(material=None)` is the kernel's LINEAR ELASTIC path
(`_kernel_material` returns a bare `fe.Material`); 'j2' is incremental
plasticity, path-dependent, which is what "activate plasticity" means. 'ro'
is Ramberg-Osgood -- nonlinear but path-INDEPENDENT -- so it is not used
here, though it is what the reference `run_slay` runs by default.

REPORTING ZONE. Strains at the last three stinger rollers (SR5, SR6, SR7)
are excluded, as instructed. That is also what makes D6's terminal contact
slot harmless: it over-constrains the tip and concentrates strain at SR6
(spec section 5d), and the tip is exactly the region excluded here. The zone
is printed beside every number so no reader has to infer it.

    python3 tools/stage_run.py [--R 85] [--tension 120] [--spacing 9]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))

from slay.data.materials import material                   # noqa: E402
from slay.model.assemble import build_model                # noqa: E402
from slay.physics.problem import build_problem             # noqa: E402
from slay.scene.rollers import roller_stations             # noqa: E402
from slay.scene.scene import Scene, build_scene            # noqa: E402
from slay.solve.passage import solve                       # noqa: E402

TON = 9806.65
DROP_AT_TIP = 3                     # SR5, SR6, SR7 -- excluded from results


def all_bidirectional(scene):
    """The same Scene with no roller permitted to lift off.

    GEOMETRICALLY IDENTICAL -- same path, same stations, same extent and
    elastic zones -- so the model built from either meshes the same way and
    a displacement field carries between them. Only `one_sided` differs,
    which is a property of the contact slots and of nothing else.
    """
    st = roller_stations(scene.path, n_sr=len(
        [s for s in scene.stations if s.name.startswith('SR')]) - 1,
        n_vr=len([s for s in scene.stations if s.name.startswith('VR')]),
        spacing=scene.spacing, one_sided=frozenset())
    return Scene(path=scene.path, stations=tuple(st), extent=scene.extent,
                 elastic_zones=scene.elastic_zones, spacing=scene.spacing)


def report_zone(scene):
    """(s_max, label) -- everything strictly inboard of the last 3 rollers."""
    sr = sorted((s for s in scene.stations if s.name.startswith('SR')),
                key=lambda t: t.s_arc)
    cut = sr[-DROP_AT_TIP]
    return cut.s_arc, f'{cut.name} and beyond excluded'


def peak_in_zone(result, s_max):
    rows = [(s, e) for (_i, s, e) in result.strains if s < s_max]
    return max(rows, key=lambda r: r[1]) if rows else (0.0, 0.0)


def station_profile(scene, result):
    out = {}
    for st in scene.stations:
        near = [e for (_i, s, e) in result.strains
                if abs(s - st.s_arc) < scene.spacing / 2.0]
        if near:
            out[st.name] = max(near)
    return out


def run(R=85.0, tension_mt=120.0, spacing=None, elastic=16.0, verbose=True):
    """The four steps. Returns (scene, [(label, Problem, Result)], state)."""
    sc = build_scene(R=R, spacing=spacing, elastic_length=elastic)
    held = all_bidirectional(sc)
    m = build_model(sc)
    T = tension_mt * TON

    steps = [
        # Every roller held, elastic, nothing but the targets acting.
        ('1  displacements, elastic, all held',
         build_problem(m, held, material=None, gravity=False, tension=0.0)),
        # The ruled one-sided set takes over AND gravity arrives. Both
        # belong to this step: lift-off is what gravity is resisted by.
        ('2  + gravity, lift-off active',
         build_problem(m, sc, material=None, gravity=True, tension=0.0)),
        # Full tension on iteration 1 -- the kernel does not scale loads by
        # `lam` (L050), so "apply tension" is a step, not a ramp.
        ('3  + tension at SR7',
         build_problem(m, sc, material=None, gravity=True, tension=T)),
        ('4  + plasticity (J2)',
         build_problem(m, sc, material=material('j2'), gravity=True,
                       tension=T)),
    ]

    s_max, zone = report_zone(sc)
    if verbose:
        print(f'R = {R:.0f} m   T = {tension_mt:.0f} MT   '
              f'spacing = {sc.spacing:.0f} m   zone: s < {s_max:.1f} m '
              f'({zone})')
        print(f'  {"step":38s}{"status":>24}{"act":>7}'
              f'{"peak in zone":>14}{"at s":>8}')

    out, state = [], None
    for label, p in steps:
        r, state = solve(p, state_in=state)
        out.append((label, p, r))
        if verbose:
            s_pk, e = peak_in_zone(r, s_max)
            tag = (f'{100 * e:13.4f}%{s_pk:8.2f}' if r.converged
                   else f'{"--":>14}{"":>8}')
            print(f'  {label:38s}{r.status:>24}'
                  f'{sum(r.active):3d}/{len(r.active):<3d}{tag}')
    return sc, out, state


def main() -> int:
    def arg(flag, default):
        return (type(default)(sys.argv[sys.argv.index(flag) + 1])
                if flag in sys.argv else default)
    R = arg('--R', 85.0)
    T = arg('--tension', 120.0)
    spacing = arg('--spacing', 0.0) or None

    sc, out, _state = run(R=R, tension_mt=T, spacing=spacing)
    s_max, _zone = report_zone(sc)
    label, _p, final = out[-1]
    if not final.converged:
        print(f'\n  NO RESULT -- {label.strip()} did not converge')
        return 1

    print(f'\n  strain by station at the end of step 4 '
          f'(* = excluded from the result):')
    for name, e in station_profile(sc, final).items():
        st = sc.by_name(name)
        mark = ' *' if st.s_arc >= s_max else '  '
        print(f'   {mark}{name:>5}  s={st.s_arc:6.1f}   {100 * e:.4f}%')
    s_pk, e = peak_in_zone(final, s_max)
    print(f'\n  RESULT  peak {100 * e:.4f}% at s = {s_pk:.2f} m   '
          f'(* excluded: the last {DROP_AT_TIP} stinger rollers)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

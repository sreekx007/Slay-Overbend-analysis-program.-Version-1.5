#!/usr/bin/env python3
"""emit_profile.py -- solve a passage and WRITE IT DOWN as a profile artifact.

    python3 tools/emit_profile.py --archetype ILS-TP [--R 85] [--out DIR]
    python3 tools/emit_profile.py --archetype ILS-SH --samples 2000

This is the GENERATOR half of the split. It is allowed to import the solver,
build a Scene and sweep a passage, because that is what generating a result
IS. What it is not allowed to do is draw: it emits

    <out>/<case_id>.geometry.csv     + .schema.json
    <out>/<case_id>.sections.csv     + .schema.json
    <out>/<case_id>.stations.csv     + .schema.json

and stops. `tools/plot_from_schema.py --profile <out>/<case_id>` draws them
without importing `slay` at all.

WHY THE SPLIT IS WORTH A TOOL OF ITS OWN. A figure drawn by a program that
re-solves on every run cannot be checked, cannot be pointed at last week's
result, and has no way to fail loudly -- it just draws whatever it computed.
Once the result is an artifact with a contract, a wrong figure is either a
wrong file (which the writer's own checks refuse) or a wrong plotter (which
a reader can see), and the two can be told apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

from slay.report import profile as rprof            # noqa: E402
from slay.report import passage as rp               # noqa: E402
from slay.data.materials import material            # noqa: E402
from slay.model.assemble import build_model         # noqa: E402
from slay.physics.problem import build_problem      # noqa: E402
from slay.solve.kernel import mesh_of_problem       # noqa: E402
from slay.study import sweep                        # noqa: E402

import plot_stinger as gen                          # noqa: E402

TON = gen.TON


def emit(arch_id='ILS-TP', R=85.0, spacing=9.0, tension_mt=120.0,
         L_OD=None, t_ratio=None, step=None, out=None, samples=None,
         case_id=None):
    """Solve the passage and write the three tables. Returns the summary."""
    ils = gen.build_component_ils(arch_id, L_OD=L_OD, t_ratio=t_ratio)
    OD = ils.assembly.pipe.OD_pipe
    t_wall = ils.assembly.pipe.t_pipe
    L = ils.extent[1] - ils.extent[0]
    step = 2.0 * OD if step is None else step

    sc = sweep.scene_for(R=R, spacing=spacing, L_comp=L)
    s_centre = sweep.start_centre(sc, L)
    positions = sweep.run(sc, ils, L_comp=L, step=step,
                          tension=tension_mt * TON, material=material('j2'))
    recs = rp.measure(positions, sc, L_comp=L)
    env = rp.envelope(recs)

    # ONE model for the whole passage. The mesh does not change as the pipe
    # slides -- the material does -- so rebuilding it per position would be
    # both slower and a chance for two positions to disagree about what an
    # element index means, which the sections table would then carry.
    m = build_model(sc, ils, s_centre=s_centre,
                    extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)

    built = {}

    def model_of(pos):
        if pos.shift not in built:
            p = build_problem(m, sc, shift=pos.shift, assembly=ils.assembly,
                              ils=ils, s_centre=s_centre,
                              tension=tension_mt * TON,
                              material=material('j2'), vertical_at=(lo,),
                              elastic_spans=((lo, hi),))
            ms, _mdl, _ix = mesh_of_problem(p)
            built[pos.shift] = (m, ms, pos.result.U, p)
        return built[pos.shift]

    _m, _ms, _U, p0 = model_of(positions[env.index])
    cid = case_id or f'{arch_id.lower()}_R{R:g}_sp{spacing:g}_T{tension_mt:g}'
    ctx = rprof.case_context(
        case_id=cid, family=arch_id, scene=sc, problem=p0, OD=OD,
        t_wall=t_wall, tension_mt=tension_mt, L_comp=L, s_centre=s_centre,
        zone_s_max=env.zone_s_max, n_positions=len(positions),
        envelope_step=env.index)

    out = Path(out or (REPO / 'docs' / 'profiles'))
    kw = {} if samples is None else dict(n=samples)
    summary = rprof.write(out / cid, sc, positions, model_of, ils, s_centre,
                          OD, ctx, env.zone_s_max, **kw)
    return dict(summary=summary, case_id=cid, envelope=env, records=recs,
                stem=str(out / cid))


def main() -> int:
    def arg(flag, cast=float, default=None):
        if flag in sys.argv:
            return cast(sys.argv[sys.argv.index(flag) + 1])
        return default

    aid = arg('--archetype', str, 'ILS-TP')
    res = emit(aid, R=arg('--R', float, 85.0),
               spacing=arg('--spacing', float, 9.0),
               tension_mt=arg('--tension', float, 120.0),
               L_OD=arg('--L-OD'), t_ratio=arg('--t-ratio'),
               step=arg('--step'), out=arg('--out', str),
               samples=arg('--samples', int))
    env = res['envelope']
    print(f'\n=== {aid} -> profile artifact ===')
    for t, s in res['summary'].items():
        print(f'  {t:9s} {s["rows"]:6d} rows x {s["columns"]:2d} cols  '
              f'{gen._rel(Path(s["path"]))}')
    print(f'  envelope: step {env.index}, shift {env.shift:.3f} m, '
          f'peak {100 * env.peak_strain:.4f}%')
    print(f'\n  plot it with:\n    python3 tools/plot_from_schema.py '
          f'--profile {gen._rel(Path(res["stem"]))}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

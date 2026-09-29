#!/usr/bin/env python3
"""plot_stinger.py -- the pipeline as it actually sits on the stinger.

THE FIGURE THIS PROJECT DID NOT HAVE. `draw_layout.py` renders the Scene --
roller stations, to scale, from `slay.scene` -- and deliberately draws NO
pipe, because tracker item 27's rule is that a drawing which derives the
pipe's shape from the arc formula "asserts a shape nothing solved for".

That rule is exactly why this figure is now allowed: every pipe coordinate
here comes from a SOLVED displacement field. Nothing is interpolated onto
the arc, and where the pipe is off the rollers the picture says so.

THE FRAME MAPPING, which is the one thing to get right. The model solves in
`(s, y)`: `s` is arc length, increasing toward the stinger, and the
undeformed pipe is a straight line along `y = 0`. The WORLD has `+x` toward
the vessel, so `ds/dx = -1` and

    x_world = -(s + u_s)        y_world = y + u_y

The minus sign lives here and in `slay.scene.path`, nowhere else. Get it
backwards and the pipe is drawn as a mirror image that still looks
plausible -- a straight line on a deck and an arc are both symmetric.

    python3 tools/plot_stinger.py [--R 85] [--out FILE]
    python3 tools/plot_stinger.py --archetype ILS-TP [--shift 1.0]
                                  [--L-OD 2.5] [--t-ratio 2.0]

THE COMPONENT FIGURE (`--archetype`) is the one this project went longest
without, and its absence is why a GD-TP placement mismatch survived a run
whose numbers all agreed: there was no way to SEE where the component was.
It draws the solved passage at its ENVELOPE position by default -- the worst
position of the sweep, which is where the leading edge crosses SR2 -- with

  * the component's own span drawn heavier on the pipe, and shaded, so the
    section change is visible rather than inferred;
  * every junction marked, in the world coordinate of the SOLVED pipe;
  * a second panel of strain against the same axis, carrying the junction
    probes and the +/-2/4/6 x OD sample points.

The second panel is the picture of the result in RESULTS.md 5.6: moment is
continuous across a junction and strain is not, so the strain trace STEPS
there. Over the dataset the leading-junction pipe strain is a median 4.54x
the component body peak, and the panel shows why -- the component body sits
in a trough of the trace, not on a peak.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))

from slay.data.materials import material                   # noqa: E402
from slay.model.assemble import build_model                # noqa: E402
from slay.physics.problem import build_problem             # noqa: E402
from slay.scene.path import LayPath                        # noqa: E402
from slay.scene.rollers import StationRole, roller_stations  # noqa: E402
from slay.scene.scene import Scene, build_scene            # noqa: E402
from slay.solve import contact as ctc                      # noqa: E402
from slay.solve.kernel import dof, mesh_of_problem         # noqa: E402
from slay.solve.passage import solve                       # noqa: E402

TON = 9806.65                       # 1 MT of force, N
UPLIFT_ARROW = 1.6                  # m, the 'may lift off' arrow's length

# THE BENCHMARK'S OWN TENSION, reachable since decision D6 made the terminal
# stinger station a contact slot. Before that it was 15 MT -- 16 gave
# `CUTBACK EXHAUSTED at lam=0.0000` -- because 120 MT sat on the tip of a 9 m
# free cantilever and the first Newton step was 3.2 m against a 1.0 m
# threshold. See section 5 of `docs/modules/T5_solve_spec.md`.
TENSION_MT = 120.0

FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'
OFFSET_COL = '#6b4ea8'
JUNC_COL = '#c1121f'
COMP_FILL = '#f2e3c4'


def world(s, y, us, uy):
    """Model (s, y) + displacement -> world (x, y). See the module docstring."""
    return -(s + us), y + uy


def case(R=85.0, one_sided=None, gravity=True, tension_mt=0.0, elastic=16.0):
    """Build, solve, and return everything the figure needs."""
    if one_sided is None:
        sc = build_scene(R=R, elastic_length=elastic)
    else:
        path = LayPath(R=R)
        st = roller_stations(path, one_sided=one_sided)
        lo, hi = min(x.s_arc for x in st), max(x.s_arc for x in st)
        sc = Scene(path=path, stations=tuple(st), extent=(lo, hi),
                   elastic_zones=((lo, lo + elastic), (hi - elastic, hi)),
                   spacing=9.0)
    m = build_model(sc)
    p = build_problem(m, sc, material=material('ro'), gravity=gravity,
                      tension=tension_mt * TON)
    r, _state = solve(p)
    ms, _mdl, _ix = mesh_of_problem(p)
    slots = ctc.slots_from_targets(p.contacts, ms)
    return sc, m, p, r, ms, slots


def build_component_ils(arch_id='ILS-TP', OD=None, t_wall=None,
                        L_OD=None, t_ratio=None):
    """The archetype, optionally re-dimensioned.

    Edits the archetype's own definition rather than constructing geometry
    here, so `ils_builder` stays the single author of what a component IS
    (G7) and the constant-bore outward growth comes with it.
    """
    import copy
    import json

    import ils_builder
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        FIXTURE.read_text())['archetypes']}[arch_id]['definition'])
    if OD is not None:
        spec['pipeline']['OD_pipe'] = OD
    if t_wall is not None:
        spec['pipeline']['t_pipe'] = t_wall
    od = spec['pipeline']['OD_pipe']
    tw = spec['pipeline']['t_pipe']
    if L_OD is not None and spec.get('components'):
        spec['components'][0]['L_comp'] = L_OD * od
    if t_ratio is not None and spec.get('components'):
        spec['components'][0]['t_comp'] = t_ratio * tw
    return ils_builder.build_ils(spec)


def passage_cases(arch_id='ILS-TP', R=85.0, spacing=9.0,
                  tension_mt=TENSION_MT, L_OD=None, t_ratio=None, step=None):
    """EVERY solved position of the passage, not just the envelope.

    One sweep, one list. The component's whole traverse is the thing being
    looked at, so re-solving per position would be both slow and a chance
    for two figures to disagree about what was run.
    """
    from slay.report import passage as rp
    from slay.study import sweep

    ils = build_component_ils(arch_id, L_OD=L_OD, t_ratio=t_ratio)
    OD = ils.assembly.pipe.OD_pipe
    L = ils.extent[1] - ils.extent[0]
    step = 2.0 * OD if step is None else step
    sc = sweep.scene_for(R=R, spacing=spacing, L_comp=L)
    s_centre = sweep.start_centre(sc, L)
    positions = sweep.run(sc, ils, L_comp=L, step=step,
                          tension=tension_mt * TON, material=material('j2'))
    recs = rp.measure(positions, sc, L_comp=L)
    env = rp.envelope(recs)
    lo, hi = sweep.buffer_span(sc)
    m = build_model(sc, ils, s_centre=s_centre,
                    extra_stations=sweep._required_stations(sc))
    out = []
    for pos in positions:
        if not pos.converged:
            out.append(None)
            continue
        pr = build_problem(m, sc, shift=pos.shift, assembly=ils.assembly,
                           ils=ils, s_centre=s_centre,
                           tension=tension_mt * TON, material=material('j2'),
                           vertical_at=(lo,), elastic_spans=((lo, hi),))
        ms, _mdl, _ix = mesh_of_problem(pr)
        out.append(dict(problem=pr, ms=ms, position=pos))
    return dict(scene=sc, model=m, steps=out, records=recs, envelope=env,
                s_centre=s_centre, L_comp=L, OD=OD, arch_id=arch_id,
                tension_mt=tension_mt)


def component_case(arch_id='ILS-TP', R=85.0, spacing=9.0,
                   tension_mt=TENSION_MT, shift=None, L_OD=None,
                   t_ratio=None, step=None):
    """Solve the passage; return the position asked for, or the ENVELOPE.

    The envelope is the default because it is the position the design is
    governed by and the only one that does not have to be justified. A
    `--shift` is honoured by taking the solved position nearest it, never by
    solving a position the sweep did not -- the schedule includes the edge
    crossings on purpose (`study.sweep.critical_shifts`).
    """
    from slay.report import passage as rp
    from slay.study import sweep

    ils = build_component_ils(arch_id, L_OD=L_OD, t_ratio=t_ratio)
    OD = ils.assembly.pipe.OD_pipe
    L = ils.extent[1] - ils.extent[0]
    step = 2.0 * OD if step is None else step
    sc = sweep.scene_for(R=R, spacing=spacing, L_comp=L)
    s_centre = sweep.start_centre(sc, L)
    positions = sweep.run(sc, ils, L_comp=L, step=step,
                          tension=tension_mt * TON, material=material('j2'))
    recs = rp.measure(positions, sc, L_comp=L)
    env = rp.envelope(recs)
    if shift is None:
        pos = positions[env.index]
        note = 'envelope position'
    else:
        ok = [p_ for p_ in positions if p_.converged]
        pos = min(ok, key=lambda p_: abs(p_.shift - shift))
        note = f'nearest solved position to shift {shift:.3f} m'

    m = build_model(sc, ils, s_centre=s_centre,
                    extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)
    p = build_problem(m, sc, shift=pos.shift, assembly=ils.assembly, ils=ils,
                      s_centre=s_centre, tension=tension_mt * TON,
                      material=material('j2'), vertical_at=(lo,),
                      elastic_spans=((lo, hi),))
    ms, _mdl, _ix = mesh_of_problem(p)
    slots = ctc.slots_from_targets(p.contacts, ms)
    return dict(scene=sc, model=m, problem=p, result=pos.result, ms=ms,
                slots=slots, s_centre=s_centre, L_comp=L, OD=OD,
                position=pos, records=recs, envelope=env, note=note,
                n_positions=len(positions))


def s_to_x(m, ms, U, shift=0.0):
    """Interpolator: material `s` -> world `x` on the SOLVED pipe.

    THE SHIFT BELONGS HERE, and leaving it out drew the pipe a whole `shift`
    short of the rollers it is sitting on. The solver never applies the
    rigid-body translation of a pipeline advancing down the stinger, and it
    is right not to: sliding a pipe along its own axis produces no strain, so
    nothing in the model drives it. The shape and the strain are therefore
    correct without it. But the PICTURE is in world coordinates, where that
    translation is exactly what puts the material under its roller.

    Measured before the fix, at shift = 1.000 m: SR2 sits at x = -8.983 and
    the material it constrains was drawn at -7.998, every station off by the
    shift. The component then appeared a metre short of the roller it had
    already reached.

        x_world = -(s + shift + u_s)
    """
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    sv = np.array([at[i].s for i in ids])
    xv = np.array([world(at[i].s + shift, at[i].y,
                         U[dof(ms, i, 0)], U[dof(ms, i, 1)])[0] for i in ids])
    return lambda q: np.interp(q, sv, xv)


def pipe_xy(m, ms, U, shift=0.0):
    """World polyline of the DEFORMED pipe, in node order along the header.

    `shift` is the passage translation the solver omits -- see `s_to_x`.
    """
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    xs, ys = [], []
    for i in ids:
        n = at[i]
        x, y = world(n.s + shift, n.y, U[dof(ms, i, 0)], U[dof(ms, i, 1)])
        xs.append(x); ys.append(y)
    return np.array(xs), np.array(ys), ids


def undeformed_xy(m):
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    return (np.array([-at[i].s for i in ids]),
            np.array([at[i].y for i in ids]))


def peak_on_pipe(m, ms, U, r, s_min=None):
    """(x, y, s, eps) of the worst element, placed on the SOLVED pipe.

    `Result.strains` carries `s_mid` -- a MATERIAL coordinate -- so the mark
    has to be interpolated onto the deformed shape rather than dropped at the
    undeformed station. The pipe slides metres over the rollers; a mark
    placed by undeformed `s` would sit next to the pipe, not on it.
    """
    s_pk, eps = r.peak_strain(s_min=s_min)
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    k = max(0, min(len(ids) - 2,
                   next((j for j in range(len(ids) - 1)
                         if at[ids[j + 1]].s >= s_pk), len(ids) - 2)))
    a, b = ids[k], ids[k + 1]
    span = at[b].s - at[a].s
    w = 0.0 if span <= 0 else (s_pk - at[a].s) / span
    xa, ya = world(at[a].s, at[a].y, U[dof(ms, a, 0)], U[dof(ms, a, 1)])
    xb, yb = world(at[b].s, at[b].y, U[dof(ms, b, 0)], U[dof(ms, b, 1)])
    return (xa + w * (xb - xa), ya + w * (yb - ya), s_pk, eps)


def nearest_station(sc, s_pk):
    st = min(sc.stations, key=lambda t: abs(t.s_arc - s_pk))
    return st.name, s_pk - st.s_arc


def report(sc, p, r, slots, ms):
    """The numbers behind the picture -- printed, because a plot cannot be
    checked by eye and the question being asked is whether it is right."""
    print(f'  status {r.status}   increments {r.increments}   '
          f'cutbacks {r.cutbacks}   active {sum(r.active)}/{len(r.active)}')
    print(f'  {"station":>8}{"role":>9}{"1-sided":>9}{"target_dn":>11}'
          f'{"achieved":>11}{"miss":>11}{"active":>8}')
    for i, s_ in enumerate(slots):
        t = p.contacts[i]
        got = s_.u_out(r.U)
        print(f'  {s_.name:>8}{"contact":>9}{str(t.one_sided):>9}'
              f'{s_.dn:11.4f}{got:11.4f}{s_.dn - got:11.2e}'
              f'{str(r.active[i]):>8}')
    for st in sc.stations:
        if st.role is not StationRole.CONTACT:
            print(f'  {st.name:>8}{st.role.value:>9}'
                  f'{"":>9}{"":>11}{"":>11}{"":>11}{"":>8}')
    arc_table(sc, p, r, ms)
    s_pk, eps = r.peak_strain()
    name, off = nearest_station(sc, s_pk)
    print(f'\n  peak strain {100 * eps:.4f}% at s = {s_pk:.2f} m '
          f'({name}{off:+.2f} m)')


def arc_table(sc, p, r, ms):
    """THE INDEPENDENT CHECK (L047). Node reference positions are set by arc
    length, so the material point at arc `s` must land at `path.position(s)`.
    That statement owes nothing to the contact residual, which reports on the
    normal direction alone -- which is exactly how a mirrored normal (L048)
    hid behind targets met to 1e-13 m."""
    print(f'\n  {"station":>8}{"s_mat":>9}{"arc_x":>10}{"arc_y":>10}'
          f'{"pipe_x":>10}{"pipe_y":>10}{"miss":>9}')
    for t in p.contacts:
        us = sum(w * r.U[dof(ms, i, 0)]
                 for i, w in ((t.n_lo, t.w_lo), (t.n_hi, t.w_hi)))
        uy = sum(w * r.U[dof(ms, i, 1)]
                 for i, w in ((t.n_lo, t.w_lo), (t.n_hi, t.w_hi)))
        x, y = world(t.s_material, 0.0, us, uy)
        ax, ay = sc.path.position(t.s_material)
        print(f'  {t.station:>8}{t.s_material:9.2f}{ax:10.3f}{ay:10.3f}'
              f'{x:10.3f}{y:10.3f}{math.hypot(x - ax, y - ay):9.4f}')


def plot(cases, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, axes = plt.subplots(len(cases), 1, figsize=(13.0, 4.6 * len(cases)))
    if len(cases) == 1:
        axes = [axes]

    for ax, (title, (sc, m, p, r, ms, slots)) in zip(axes, cases):
        path = sc.path
        # the roller-centreline locus, from the Scene's own path
        ss = np.linspace(min(s.s_arc for s in sc.stations),
                         max(s.s_arc for s in sc.stations), 400)
        lx, ly = zip(*(path.position(v) for v in ss))
        ax.plot(lx, ly, color='#b9c2cb', lw=1.0, ls='--', zorder=1,
                label='roller-centreline locus')

        ux, uy = undeformed_xy(m)
        ax.plot(ux, uy, color='#d7dde3', lw=2.0, zorder=2,
                label='pipe, undeformed (straight)')

        active = {s_.name: a for s_, a in zip(slots, r.active)}
        for st in sc.stations:
            if st.role is StationRole.CONTACT:
                on = active.get(st.name, True)
                col = '#2f6f3e' if on else '#b44d12'
            elif st.role is StationRole.FIXED:
                col = '#111111'
            else:
                col = '#6b4ea8'
            ax.add_patch(Circle((st.x, st.y), st.radius, facecolor='none',
                                edgecolor=col, lw=1.6, zorder=4))
            ax.annotate(st.name, (st.x, st.y), textcoords='offset points',
                        xytext=(0, -14), ha='center', fontsize=7, color=col)
            # ONE-SIDED = the roller may only PUSH, so the pipe is free to
            # lift off it. That is a property of the ROLLER, fixed before the
            # solve; the colour above is the solved STATE. Keep them apart:
            # a bidirectional roller never lifts however tensile its reaction
            # goes, and a one-sided one that happens to stay loaded still
            # allows uplift. The arrow points the way the pipe may leave --
            # up the screen, which is -y.
            if st.bears_tension:
                ax.add_patch(Circle((st.x, st.y), st.radius * 3.2,
                                    facecolor='none', edgecolor='#6b4ea8',
                                    lw=1.3, ls=(0, (2, 1.6)), zorder=4))
            if st.role is StationRole.CONTACT and st.one_sided:
                ax.annotate('', xy=(st.x, st.y - UPLIFT_ARROW),
                            xytext=(st.x, st.y - 0.35),
                            arrowprops=dict(arrowstyle='-|>', lw=1.1,
                                            color=col, shrinkA=0, shrinkB=0),
                            zorder=4)

        px, py, _ids = pipe_xy(m, ms, r.U)
        ax.plot(px, py, color='#1f7a8c', lw=2.4, zorder=5,
                label='pipe, SOLVED')

        # THE PEAK, placed on the deformed pipe and labelled with the
        # station it falls nearest. The offset is printed because the peak
        # is an ELEMENT midpoint and rarely lands on a station exactly;
        # rounding it to the station name alone would invent a coincidence.
        kx, ky, s_pk, eps = peak_on_pipe(m, ms, r.U, r)
        name, off = nearest_station(sc, s_pk)
        ax.plot([kx], [ky], marker='D', ms=6.5, mfc='#c1121f',
                mec='white', mew=1.2, zorder=7)
        x0, x1 = ax.get_xlim()
        left = (kx - min(x0, x1)) / abs(x1 - x0) < 0.35
        dx, ha = (22, 'left') if left else (-18, 'right')
        where = (f'at {name}' if abs(off) < 0.05
                 else f'{abs(off):.1f} m {"past" if off > 0 else "short of"} '
                      f'{name}')
        ax.annotate(f'peak {100 * eps:.3f}%\ns = {s_pk:.1f} m, {where}',
                    (kx, ky), textcoords='offset points', xytext=(dx, 20),
                    ha=ha, va='center', fontsize=8.5, color='#8d0801',
                    zorder=7,
                    bbox=dict(boxstyle='round,pad=0.32', fc='white',
                              ec='#c1121f', lw=0.9, alpha=0.93),
                    arrowprops=dict(arrowstyle='-', color='#c1121f',
                                    lw=0.9, shrinkA=0, shrinkB=3))

        ax.set_aspect('equal')
        ax.invert_yaxis()
        # HEADROOM FOR THE UPLIFT ARROWS. The deck rollers sit at y = 0, so
        # on the default limits their arrows fall off the top of the axes --
        # and those are exactly the ones the reader needs, because SR1, VR1
        # and VR2 are where panel B lifts off. An annotation that is clipped
        # is an annotation that is not there.
        lo = min(list(ly) + list(py) + [s_.y for s_ in sc.stations])
        hi = max(list(ly) + list(py) + [s_.y for s_ in sc.stations])
        ax.set_ylim(hi + 1.5, lo - (UPLIFT_ARROW + 1.2))
        ax.grid(alpha=0.2)
        ax.set_ylabel('y (m), down')
        ax.set_title(title, fontsize=10, loc='left')

    handles = [plt.Line2D([], [], color=c, lw=lw, ls=ls, label=lb)
               for lb, c, lw, ls in (
                   ('pipe, SOLVED', '#1f7a8c', 2.4, '-'),
                   ('pipe, undeformed', '#d7dde3', 2.0, '-'),
                   ('roller-centreline locus', '#b9c2cb', 1.0, '--'),
                   ('roller, in contact', '#2f6f3e', 1.6, '-'),
                   ('roller, lifted off', '#b44d12', 1.6, '-'))]
    handles.append(plt.Line2D([], [], ls='none', marker='D', ms=6.5,
                              mfc='#c1121f', mec='white', mew=1.2,
                              label='peak strain'))
    handles += [plt.Line2D([], [], color=c, lw=lw, ls=ls, label=lb)
                for lb, c, lw, ls in (
                    ('arrow: one-sided, may lift off', '#6b737b', 1.1, '-'),
                    ('unmarked: bidirectional, held down',
                     '#6b737b', 0.0, 'none'),
                    ('FIXED station', '#111111', 1.6, '-'),
                    ('ring: bears the lay tension', '#6b4ea8', 1.3, '--'))]
    axes[0].legend(handles=handles, fontsize=8, ncol=2, loc='lower right',
                   framealpha=0.93)
    axes[-1].set_xlabel('x (m)   --   +x toward the vessel, so the stinger '
                        'is on the LEFT (starboard view, no flip)')

    fig.suptitle('Pipeline on the stinger. Every pipe coordinate is a SOLVED '
                 'displacement, never interpolated onto the arc (tracker '
                 'item 27).\nColour is the SOLVED state (in contact / lifted '
                 'off); the arrow is the ROLLER, marking the ones that allow '
                 'uplift.', fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    print(f'\nwrote {Path(out).relative_to(REPO)}')


def plot_component(c, out):
    """Two panels on one axis: the solved geometry, and the strain trace.

    SHARED X, and that is the point of the figure. The strain step at a
    junction sits directly under the section change that causes it, so the
    reader does not have to correlate two plots by eye.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    from slay.report import junction as jr

    sc, m, p, r = c['scene'], c['model'], c['problem'], c['result']
    ms, U, OD = c['ms'], c['result'].U, c['OD']
    L, s_c, pos = c['L_comp'], c['s_centre'], c['position']
    sh = pos.shift
    fx = s_to_x(m, ms, U, sh)

    # THREE PANELS, because one cannot do this job. The component is about a
    # metre on a hundred-metre stinger, so a single shared axis either shows
    # where it sits or shows what happens there, never both. Panels 1 and 2
    # share x and answer "where"; panel 3 has its own window and answers
    # "what", at a scale where the junction step is legible.
    fig, (ax, bx, cx) = plt.subplots(
        3, 1, figsize=(13.5, 12.4),
        gridspec_kw=dict(height_ratios=[1.25, 1.0, 1.0], hspace=0.28))
    bx.sharex(ax)

    # ---- panel 1: geometry ------------------------------------------------
    ss = np.linspace(min(t.s_arc for t in sc.stations),
                     max(t.s_arc for t in sc.stations), 400)
    lx, ly = zip(*(sc.path.position(v) for v in ss))
    ax.plot(lx, ly, color='#b9c2cb', lw=1.0, ls='--', zorder=1)

    active = {s_.name: a for s_, a in zip(c['slots'], r.active)}
    for st in sc.stations:
        if st.role is StationRole.CONTACT:
            col = '#2f6f3e' if active.get(st.name, True) else '#b44d12'
        elif st.role is StationRole.FIXED:
            col = '#111111'
        else:
            col = OFFSET_COL
        ax.add_patch(Circle((st.x, st.y), st.radius, facecolor='none',
                            edgecolor=col, lw=1.6, zorder=4))
        ax.annotate(st.name, (st.x, st.y), textcoords='offset points',
                    xytext=(0, -14), ha='center', fontsize=7, color=col)
        if st.role is StationRole.CONTACT and st.one_sided:
            ax.annotate('', xy=(st.x, st.y - UPLIFT_ARROW),
                        xytext=(st.x, st.y - 0.35),
                        arrowprops=dict(arrowstyle='-|>', lw=1.1, color=col,
                                        shrinkA=0, shrinkB=0), zorder=4)

    px, py, _ids = pipe_xy(m, ms, U, sh)
    ax.plot(px, py, color='#1f7a8c', lw=2.2, zorder=5)

    # THE COMPONENT, drawn from the SOLVED pipe over its own material span --
    # not as a box at a nominal position. This is the check that was missing.
    s_lo, s_hi = s_c - L / 2.0, s_c + L / 2.0
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    seg = [i for i in ids if s_lo - 1e-9 <= at[i].s <= s_hi + 1e-9]
    if seg:
        sx = [world(at[i].s + sh, at[i].y,
                    U[dof(ms, i, 0)], U[dof(ms, i, 1)])[0] for i in seg]
        sy = [world(at[i].s + sh, at[i].y,
                    U[dof(ms, i, 0)], U[dof(ms, i, 1)])[1] for i in seg]
        ax.plot(sx, sy, color='#8a5a00', lw=6.5, solid_capstyle='butt',
                zorder=6, alpha=0.9)

    juncs = jr.junctions(p)
    for panel in (ax, bx, cx):
        panel.axvspan(fx(s_hi), fx(s_lo), color=COMP_FILL, alpha=0.55,
                      zorder=0)
        for j in juncs:
            panel.axvline(fx(j.s), color=JUNC_COL, lw=1.1, ls=(0, (4, 2)),
                          alpha=0.8, zorder=2)

    ax.set_aspect('equal')
    ax.invert_yaxis()
    lo_y = min(list(ly) + list(py) + [t.y for t in sc.stations])
    hi_y = max(list(ly) + list(py) + [t.y for t in sc.stations])
    ax.set_ylim(hi_y + 1.5, lo_y - (UPLIFT_ARROW + 1.2))
    ax.grid(alpha=0.2)
    ax.set_ylabel('y (m), down')
    ratio = jr.stiffness_ratio(p)
    ax.set_title(
        f'{c["arch_id"]} on the stinger  --  R = {sc.path.R:.0f} m, '
        f'spacing {sc.spacing:.0f} m, {c["tension_mt"]:.0f} MT, '
        f'L = {L:.3f} m ({L / OD:.2g} x OD), I_comp/I_pipe = {ratio:.3f}\n'
        f'shift {pos.shift:.3f} m of {c["n_positions"]} solved positions '
        f'({c["note"]}); lead at station {pos.s_lead:.3f} m',
        fontsize=10, loc='left')

    # ---- panel 2: strain, on the same axis --------------------------------
    # THE TRACE IS BROKEN AT EVERY JUNCTION, and that is not decoration.
    # Strain STEPS across a section change -- the same moment on two section
    # moduli -- so a line drawn through it asserts a gradient the model does
    # not have, and would read as a smooth ramp into the component. It is the
    # same refusal `report.junction` makes when it declines to interpolate
    # across the step; the figure must not do what the extraction forbids.
    # STRAIN IS PIECEWISE CONSTANT PER ELEMENT, so each element is drawn over
    # its OWN EXTENT rather than as a point at its midpoint. Joining midpoints
    # already interpolates -- and it left a half-element GAP between the last
    # element of a run and the junction, which read as missing data rather
    # than as a step. Drawn over extents, adjacent runs meet exactly at the
    # junction and the only gap left is the vertical jump, which is the
    # discontinuity itself.
    secs = {q.index: q for q in p.sections}
    s_of = {i: sv for (i, sv, _y) in p.nodes}
    ends = {idx: sorted((s_of[n1], s_of[n2]))
            for (idx, n1, n2, _o, _l) in p.elements}
    runs, cur, last_od = [], [], None
    for (idx, q, e) in sorted(r.strains, key=lambda t: t[1]):
        od = secs[idx].OD if idx in secs else last_od
        if last_od is not None and od is not None and abs(od - last_od) > 1e-9:
            runs.append(cur)
            cur = []
        lo_s, hi_s = ends.get(idx, (q, q))
        cur.append((lo_s, hi_s, e))
        last_od = od
    if cur:
        runs.append(cur)
    sm = np.array([q for (_i, q, _e) in r.strains])
    ev = np.array([e for (_i, _q, e) in r.strains])
    probes = jr.measure(pos, p, OD)
    e_body, _mb, s_body = jr.body_peak(pos, p)
    env = c['envelope']

    # THE EXCLUDED ZONE, shaded on both. Without it the tip spike -- D6's
    # terminal contact slot over-constraining the last three rollers -- is
    # the tallest thing on the plot and reads as the answer. It is exactly
    # what the reporting band exists to remove.
    s_cut = env.zone_s_max
    x_cut = fx(s_cut - sh)
    for panel in (bx, cx):
        for run in runs:
            if not run:
                continue
            qs, es = [], []
            for lo_s, hi_s, e in run:
                qs += [lo_s, hi_s]
                es += [e, e]
            panel.plot(fx(np.array(qs)), 100.0 * np.array(es),
                       color='#1f7a8c', lw=1.7, zorder=5)
        panel.axhline(100 * env.peak_strain, color='#c1121f', lw=0.8,
                      ls=':', alpha=0.75)
        for q in probes:
            if not q.in_model:
                continue
            xq = fx(q.s)
            if q.offset_OD == 0.0:
                panel.plot([xq], [100 * q.strain], marker='o', ms=7.0,
                           mfc=JUNC_COL, mec='white', mew=1.2, zorder=8)
            else:
                panel.plot([xq], [100 * q.strain], marker='s', ms=5.0,
                           mfc='white', mec=OFFSET_COL, mew=1.3, zorder=7)
        if e_body > 0:
            panel.plot([fx(s_body)], [100 * e_body], marker='v', ms=7.0,
                       mfc='#8a5a00', mec='white', mew=1.1, zorder=8)
    x0 = min(fx(sm)) - 2.0
    bx.axvspan(x0, x_cut, color='#c9ccd1', alpha=0.38, zorder=1)
    bx.annotate('excluded from the reporting band\n(last 3 stinger rollers,\n'
                'D6 tip artefact)', (0.5 * (x0 + x_cut), 0.94),
                xycoords=('data', 'axes fraction'), ha='center', va='top',
                fontsize=7.5, color='#5a6068', zorder=6)

    # Panel 3: the component neighbourhood, where the step is legible.
    half = max(8.0 * OD, 1.2 * L)
    cx.set_xlim(fx(s_c + L / 2.0 + half), fx(s_c - L / 2.0 - half))
    near = [100 * e for (q, e) in zip(sm, ev)
            if s_c - L / 2 - half <= q <= s_c + L / 2 + half]
    if near:
        cx.set_ylim(0.0, 1.18 * max(near))
    for q in probes:
        if not q.in_model or q.offset_OD == 0.0:
            continue
        cx.annotate(f'{q.offset_OD:+g}xOD', (fx(q.s), 100 * q.strain),
                    textcoords='offset points', xytext=(0, 9), ha='center',
                    fontsize=7.5, color=OFFSET_COL, zorder=9)
    if e_body > 0:
        cx.annotate(f'body peak {100 * e_body:.3f}%',
                    (fx(s_body), 100 * e_body), textcoords='offset points',
                    xytext=(0, -22), ha='center', fontsize=8.5,
                    color='#8a5a00', zorder=9)
    cx.set_ylabel('extreme-fibre strain (%)')
    cx.set_xlabel('x (m)   --   +x toward the vessel, so the stinger is on '
                  'the LEFT (starboard view, no flip)')
    cx.grid(alpha=0.2)
    cx.set_title('zoom on the component -- the junction step, at a scale '
                 'where it can be read', fontsize=9.5, loc='left')
    lead = [q for q in probes
            if q.offset_OD == 0.0 and q.side == 'pipe'
            and abs(q.s - max(j.s for j in juncs)) < 1e-6]
    if lead:
        q = lead[0]
        ratio_txt = (f'  =  {q.strain / e_body:.2f} x the body peak'
                     if e_body > 0 else '')
        cx.annotate(f'junction, pipe side: {100 * q.strain:.3f}%{ratio_txt}',
                    (fx(q.s), 100 * q.strain), textcoords='offset points',
                    xytext=(26, 16), ha='left', fontsize=9.5, color='#8d0801',
                    zorder=10,
                    bbox=dict(boxstyle='round,pad=0.32', fc='white',
                              ec=JUNC_COL, lw=0.9, alpha=0.95),
                    arrowprops=dict(arrowstyle='-', color=JUNC_COL, lw=0.9,
                                    shrinkA=0, shrinkB=3))
    bx.set_ylabel('extreme-fibre strain (%)')
    bx.grid(alpha=0.2)
    bx.set_ylim(bottom=0.0)
    bx.set_title('the whole model', fontsize=9.5, loc='left')

    handles = [plt.Line2D([], [], color='#1f7a8c', lw=2.2,
                          label='pipe / strain, SOLVED'),
               plt.Line2D([], [], color='#8a5a00', lw=6.5,
                          label='component span, on the solved pipe'),
               plt.Line2D([], [], color=JUNC_COL, lw=1.1, ls=(0, (4, 2)),
                          label='junction (section step)'),
               plt.Line2D([], [], ls='none', marker='o', ms=7, mfc=JUNC_COL,
                          mec='white', mew=1.2, label='junction probe'),
               plt.Line2D([], [], ls='none', marker='s', ms=5, mfc='white',
                          mec=OFFSET_COL, mew=1.3,
                          label='+/- 2, 4, 6 x OD probe'),
               plt.Line2D([], [], ls='none', marker='v', ms=7, mfc='#8a5a00',
                          mec='white', mew=1.1, label='component body peak'),
               plt.Line2D([], [], color='#c1121f', lw=0.8, ls=':',
                          label='passage envelope')]
    handles.append(plt.Line2D([], [], color='#c9ccd1', lw=8,
                              label='outside the reporting band'))
    bx.legend(handles=handles, fontsize=7.5, ncol=2, loc='upper right',
              framealpha=0.94)

    fig.suptitle(
        'Component on the stinger, at the passage envelope. Every pipe and '
        'strain coordinate is a SOLVED value placed by MATERIAL position on '
        'the deformed pipe.\nMoment is continuous across a junction and '
        'strain is not -- so the trace STEPS there, and the component body '
        'sits in a trough rather than on a peak.', fontsize=11)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.925, bottom=0.055)
    fig.savefig(out, dpi=140)
    print(f'\nwrote {Path(out).relative_to(REPO)}')


def plot_passage(c, out):
    """Every step of the sweep, on one figure, plus a zoom that follows the
    component across its whole traverse.

    COLOUR IS THE POSITION, and the envelope is drawn heavier than the rest.
    The question the figure answers is where in the passage the worst case
    falls -- so every step has to be visible at once, and the one that wins
    has to be findable without counting.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    from slay.report import junction as jr

    sc, m, L, s_c = c['scene'], c['model'], c['L_comp'], c['s_centre']
    OD, steps, env = c['OD'], c['steps'], c['envelope']
    live = [st for st in steps if st]

    fig, (ax, bx, cx) = plt.subplots(
        3, 1, figsize=(14.0, 13.0),
        gridspec_kw=dict(height_ratios=[1.2, 1.0, 1.15], hspace=0.30))
    spans = []
    cmap = plt.get_cmap('viridis')
    n = max(1, len(live) - 1)
    col = {st['position'].index: cmap(0.08 + 0.84 * i / n)
           for i, st in enumerate(live)}

    # ---- panel 1: the stinger, with the component at every position -------
    ss = np.linspace(min(t.s_arc for t in sc.stations),
                     max(t.s_arc for t in sc.stations), 400)
    lx, ly = zip(*(sc.path.position(v) for v in ss))
    ax.plot(lx, ly, color='#b9c2cb', lw=1.0, ls='--', zorder=1)
    for st_ in sc.stations:
        c_ = ('#111111' if st_.role is StationRole.FIXED
              else '#2f6f3e' if st_.role is StationRole.CONTACT else OFFSET_COL)
        ax.add_patch(Circle((st_.x, st_.y), st_.radius, facecolor='none',
                            edgecolor=c_, lw=1.4, zorder=4))
        ax.annotate(st_.name, (st_.x, st_.y), textcoords='offset points',
                    xytext=(0, -13), ha='center', fontsize=7, color=c_)

    at = {nd.index: nd for nd in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    seg = [i for i in ids if s_c - L / 2 - 1e-9 <= at[i].s <= s_c + L / 2 + 1e-9]
    for st in live:
        pos, ms = st['position'], st['ms']
        U, sh = pos.result.U, pos.shift
        px, py, _ = pipe_xy(m, ms, U, sh)
        is_env = pos.index == env.index
        ax.plot(px, py, color=col[pos.index], lw=2.2 if is_env else 0.8,
                alpha=1.0 if is_env else 0.45, zorder=6 if is_env else 3)
        if seg:
            sx = [world(at[i].s + sh, at[i].y,
                        U[dof(ms, i, 0)], U[dof(ms, i, 1)])[0] for i in seg]
            sy = [world(at[i].s + sh, at[i].y,
                        U[dof(ms, i, 0)], U[dof(ms, i, 1)])[1] for i in seg]
            ax.plot(sx, sy, color=col[pos.index], lw=7.0,
                    solid_capstyle='butt', zorder=7, alpha=0.95)
    ax.set_aspect('equal')
    ax.invert_yaxis()
    ax.grid(alpha=0.2)
    ax.set_ylabel('y (m), down')
    ax.set_title(
        f'{c["arch_id"]}  --  R = {sc.path.R:.0f} m, spacing '
        f'{sc.spacing:.0f} m, {c["tension_mt"]:.0f} MT, L = {L:.3f} m '
        f'({L / OD:.2g} x OD)\nall {len(live)} solved positions; the thick '
        f'band is the component, the heavy pipe is the envelope position',
        fontsize=10, loc='left')

    # ---- panels 2 and 3: strain at every position -------------------------
    for st in live:
        pos, pr, ms = st['position'], st['problem'], st['ms']
        fx = s_to_x(m, ms, pos.result.U, pos.shift)
        secs = {q.index: q for q in pr.sections}
        s_of = {i: sv for (i, sv, _y) in pr.nodes}
        ends = {idx: sorted((s_of[n1], s_of[n2]))
                for (idx, n1, n2, _o, _l) in pr.elements}
        runs, cur, last_od = [], [], None
        for (idx, q, e) in sorted(pos.result.strains, key=lambda t: t[1]):
            od = secs[idx].OD if idx in secs else last_od
            if last_od is not None and od is not None \
                    and abs(od - last_od) > 1e-9:
                runs.append(cur)
                cur = []
            lo_s, hi_s = ends.get(idx, (q, q))
            cur.append((lo_s, hi_s, e))
            last_od = od
        if cur:
            runs.append(cur)
        is_env = pos.index == env.index
        for panel in (bx, cx):
            for run in runs:
                if not run:
                    continue
                qs, es = [], []
                for lo_s, hi_s, e in run:
                    qs += [lo_s, hi_s]
                    es += [e, e]
                panel.plot(fx(np.array(qs)), 100.0 * np.array(es),
                           color=col[pos.index], lw=2.0 if is_env else 0.9,
                           alpha=1.0 if is_env else 0.55,
                           zorder=7 if is_env else 4)
        # The component's span at this position is recorded for the ladder
        # drawn under the zoom axis. Nine translucent axvspans stacked on top
        # of each other made the panel unreadable and hid the traces they
        # were meant to locate.
        spans.append((pos.index, fx(s_c + L / 2), fx(s_c - L / 2),
                      pos.shift))

    # THE EXCLUDED BAND IS THE STINGER END. The zone drops the last three
    # stinger rollers, which are HIGH `s` and therefore the most NEGATIVE
    # world x. Shading from `min(s)` instead covered the entire vessel side --
    # the opposite half of the model, and the half that is in the band.
    s_cut = env.zone_s_max
    p0 = live[0]['position']
    fx_env = s_to_x(m, live[0]['ms'], p0.result.U, p0.shift)
    x_cut = fx_env(s_cut - p0.shift)
    x_tip = min(fx_env(q) for (_i, q, _e) in p0.result.strains) - 1.0
    bx.axvspan(x_tip, x_cut, color='#c9ccd1', alpha=0.40, zorder=1)
    bx.annotate('outside the reporting band\n(last 3 stinger rollers)',
                (0.5 * (x_tip + x_cut), 0.95),
                xycoords=('data', 'axes fraction'), ha='center', va='top',
                fontsize=7.5, color='#5a6068', zorder=6)
    bx.axhline(100 * env.peak_strain, color='#c1121f', lw=0.8, ls=':',
               alpha=0.8)
    bx.set_ylabel('extreme-fibre strain (%)')
    bx.set_ylim(bottom=0.0)
    bx.grid(alpha=0.2)
    bx.set_title('the whole model, every position (grey = outside the '
                 'reporting band)', fontsize=9.5, loc='left')

    # zoom: the component's WHOLE TRAVERSE, not one position's neighbourhood
    first, last = live[0], live[-1]
    fx_a = s_to_x(m, first['ms'], first['position'].result.U,
                  first['position'].shift)
    fx_b = s_to_x(m, last['ms'], last['position'].result.U,
                  last['position'].shift)
    pad = max(4.0 * OD, 0.6 * L)
    cx.set_xlim(fx_b(s_c + L / 2) - pad, fx_a(s_c - L / 2) + pad)
    lo_x, hi_x = cx.get_xlim()
    vals = []
    for st in live:
        fx = s_to_x(m, st['ms'], st['position'].result.U, st['position'].shift)
        for (_i, q, e) in st['position'].result.strains:
            if lo_x <= fx(q) <= hi_x:
                vals.append(100 * e)
    top = 1.12 * max(vals) if vals else 1.0
    lad_hi, lad_lo = -0.02 * top, -0.26 * top
    cx.set_ylim(lad_lo - 0.02 * top, top)
    cx.axhline(0.0, color='#555b61', lw=0.8, alpha=0.6)
    # THE TRAVERSE LADDER: one rung per position, showing where the component
    # sat. Read down the rungs and the component walks across the rollers.
    for k, (idx, xa, xb, sh) in enumerate(spans):
        y = lad_hi - (lad_hi - lad_lo) * (k + 0.5) / max(1, len(spans))
        heavy = idx == env.index
        cx.plot([xa, xb], [y, y], color=col[idx], lw=5.0 if heavy else 3.2,
                solid_capstyle='butt', alpha=1.0 if heavy else 0.75,
                zorder=6)
        if heavy:
            cx.annotate(f'envelope, shift {sh:.3f} m', (0.5 * (xa + xb), y),
                        textcoords='offset points', xytext=(0, -11),
                        ha='center', va='top', fontsize=7.5,
                        color='#8d0801', zorder=8)
    cx.annotate('component position, by step', (0.004, 0.13),
                xycoords='axes fraction', ha='left', va='center',
                fontsize=8, color='#5a6068')
    cx.axhline(100 * env.peak_strain, color='#c1121f', lw=0.8, ls=':',
               alpha=0.8)
    for st_ in sc.stations:
        if lo_x <= st_.x <= hi_x:
            cx.axvline(st_.x, color='#2f6f3e', lw=1.0, alpha=0.5)
            cx.annotate(st_.name, (st_.x, 0.97), xycoords=('data', 'axes fraction'),
                        ha='center', va='top', fontsize=8, color='#2f6f3e')
    cx.set_ylabel('extreme-fibre strain (%)')
    cx.set_xlabel('x (m)   --   +x toward the vessel, so the stinger is on '
                  'the LEFT (starboard view, no flip)')
    cx.grid(alpha=0.2)
    cx.set_title('zoom: the component across its whole traverse -- the '
                 'ladder below the axis is where it sat at each step',
                 fontsize=9.5, loc='left')

    sm = plt.cm.ScalarMappable(
        cmap=cmap, norm=plt.Normalize(0.0, live[-1]['position'].shift))
    sm.set_array([])
    cax = fig.add_axes((0.915, 0.08, 0.013, 0.42))
    cbar = fig.colorbar(sm, cax=cax)
    cbar.set_label('travel along the passage (m)', fontsize=8.5)
    cbar.ax.tick_params(labelsize=7.5)

    fig.suptitle(
        f'{c["arch_id"]} through the whole passage. Envelope '
        f'{100 * env.peak_strain:.4f}% at position {env.index} '
        f'(shift {env.shift:.3f} m); the start position reads '
        f'{100 * c["records"][0].peak_strain:.4f}%.\n'
        'Every coordinate is a SOLVED value placed by material position on '
        'the deformed pipe; traces break at each section step because strain '
        'is discontinuous there.', fontsize=11)
    fig.subplots_adjust(left=0.065, right=0.895, top=0.925, bottom=0.05)
    fig.savefig(out, dpi=140)
    print(f'\nwrote {Path(out).relative_to(REPO)}')


def report_component(c):
    from slay.report import junction as jr
    p, pos = c['problem'], c['position']
    print(f'  {c["note"]}: shift {pos.shift:.3f} m, '
          f'lead {pos.s_lead:.3f}, trail {pos.s_trail:.3f}')
    print(f'  I_comp/I_pipe = {jr.stiffness_ratio(p):.4f}   '
          f'junctions {len(jr.junctions(p))}')
    e, mo, sb = jr.body_peak(pos, p)
    print(f'  body peak {100 * e:.4f}%  {mo / 1e3:.1f} kNm  at s = {sb:.2f}')
    print(f'  {"probe":>18}{"s":>9}{"strain":>10}{"moment kNm":>12}  side')
    for q in jr.measure(pos, p, c['OD']):
        if not q.in_model:
            print(f'  {"j%d %+gOD" % (q.junction, q.offset_OD):>18}'
                  f'{q.s:9.3f}{"--":>10}{"--":>12}  off model')
            continue
        tag = (f'j{q.junction} at {q.side}' if q.offset_OD == 0.0
               else f'j{q.junction} {q.offset_OD:+g}OD')
        print(f'  {tag:>18}{q.s:9.3f}{100 * q.strain:9.4f}%'
              f'{q.moment / 1e3:12.1f}  {q.side}'
              f'{"  clamped" if q.clamped else ""}')


def main() -> int:
    R = 85.0
    if '--R' in sys.argv:
        R = float(sys.argv[sys.argv.index('--R') + 1])
    out = (REPO / 'docs' / 'diagrams' / 'stinger_pipe.png')
    if '--out' in sys.argv:
        out = Path(sys.argv[sys.argv.index('--out') + 1])

    def arg(flag, cast=float, default=None):
        if flag in sys.argv:
            return cast(sys.argv[sys.argv.index(flag) + 1])
        return default

    if '--archetype' in sys.argv:
        aid = sys.argv[sys.argv.index('--archetype') + 1]
        tension = arg('--tension', float, TENSION_MT)
        if '--all-steps' in sys.argv:
            if '--out' not in sys.argv:
                out = (REPO / 'docs' / 'diagrams'
                       / f'passage_{aid.lower()}.png')
            print(f'\n=== {aid}, every step of the passage '
                  f'(R = {R:.0f} m) ===')
            c = passage_cases(aid, R=R, spacing=arg('--spacing', float, 9.0),
                              tension_mt=tension, L_OD=arg('--L-OD'),
                              t_ratio=arg('--t-ratio'), step=arg('--step'))
            for st, rec in zip(c['steps'], c['records']):
                mark = ' <- envelope' if rec.index == c['envelope'].index else ''
                print(f'  pos {rec.index:2d}  shift {rec.shift:7.3f} m  '
                      f'{rec.status:>10}  peak {100 * rec.peak_strain:7.4f}%  '
                      f'lead {rec.s_lead:7.3f}{mark}')
            plot_passage(c, out)
            return 0
        if '--out' not in sys.argv:
            out = REPO / 'docs' / 'diagrams' / f'stinger_{aid.lower()}.png'
        print(f'\n=== {aid} on the stinger (R = {R:.0f} m) ===')
        c = component_case(aid, R=R, spacing=arg('--spacing', float, 9.0),
                           tension_mt=tension, shift=arg('--shift'),
                           L_OD=arg('--L-OD'), t_ratio=arg('--t-ratio'))
        c['arch_id'], c['tension_mt'] = aid, tension
        report_component(c)
        plot_component(c, out)
        return 0

    built = []
    for title, kw in (
            (f'A. every roller bidirectional, no gravity, no tension '
             f'(R = {R:.0f} m) -- the pipe is DRIVEN onto the arc',
             dict(one_sided=frozenset(), gravity=False)),
            (f'B. the ruled one-sided set, gravity, {TENSION_MT:.0f} MT lay '
             f'tension (R = {R:.0f} m) -- the benchmark case, reachable '
             f'since D6',
             dict(gravity=True, tension_mt=TENSION_MT)),
    ):
        print(f'\n=== {title} ===')
        c = case(R=R, **kw)
        report(c[0], c[2], c[3], c[5], c[4])
        built.append((title, c))
    plot(built, out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

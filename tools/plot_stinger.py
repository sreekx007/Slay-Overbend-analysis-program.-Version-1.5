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


def pipe_xy(m, ms, U):
    """World polyline of the DEFORMED pipe, in node order along the header."""
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    xs, ys = [], []
    for i in ids:
        n = at[i]
        x, y = world(n.s, n.y, U[dof(ms, i, 0)], U[dof(ms, i, 1)])
        xs.append(x); ys.append(y)
    return np.array(xs), np.array(ys), ids


def undeformed_xy(m):
    at = {n.index: n for n in m.nodes}
    ids = sorted({i for e in m.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    return (np.array([-at[i].s for i in ids]),
            np.array([at[i].y for i in ids]))


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

        px, py, _ids = pipe_xy(m, ms, r.U)
        ax.plot(px, py, color='#1f7a8c', lw=2.4, zorder=5,
                label='pipe, SOLVED')

        ax.set_aspect('equal')
        ax.invert_yaxis()
        ax.grid(alpha=0.2)
        ax.set_ylabel('y (m), down')
        ax.set_title(title, fontsize=10, loc='left')

    axes[0].legend(handles=[
        plt.Line2D([], [], color=c, lw=lw, ls=ls, label=lb)
        for lb, c, lw, ls in (
            ('pipe, SOLVED', '#1f7a8c', 2.4, '-'),
            ('pipe, undeformed', '#d7dde3', 2.0, '-'),
            ('roller-centreline locus', '#b9c2cb', 1.0, '--'),
            ('roller, in contact', '#2f6f3e', 1.6, '-'),
            ('roller, lifted off', '#b44d12', 1.6, '-'),
            ('FIXED station', '#111111', 1.6, '-'),
            ('LOAD station', '#6b4ea8', 1.6, '-'))],
        fontsize=8, ncol=2, loc='lower right', framealpha=0.93)
    axes[-1].set_xlabel('x (m)   --   +x toward the vessel, so the stinger '
                        'is on the LEFT (starboard view, no flip)')

    fig.suptitle('Pipeline on the stinger. Every pipe coordinate is a SOLVED '
                 'displacement, never interpolated onto the arc '
                 '(tracker item 27).', fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    print(f'\nwrote {Path(out).relative_to(REPO)}')


def main() -> int:
    R = 85.0
    if '--R' in sys.argv:
        R = float(sys.argv[sys.argv.index('--R') + 1])
    out = (REPO / 'docs' / 'diagrams' / 'stinger_pipe.png')
    if '--out' in sys.argv:
        out = Path(sys.argv[sys.argv.index('--out') + 1])

    built = []
    for title, kw in (
            (f'A. every roller bidirectional, no gravity, no tension '
             f'(R = {R:.0f} m) -- the pipe is DRIVEN onto the arc',
             dict(one_sided=frozenset(), gravity=False)),
            (f'B. the ruled one-sided set, gravity, no tension '
             f'(R = {R:.0f} m) -- nothing holds the pipe down',
             dict(gravity=True)),
    ):
        print(f'\n=== {title} ===')
        c = case(R=R, **kw)
        report(c[0], c[2], c[3], c[5], c[4])
        built.append((title, c))
    plot(built, out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""draw_layout.py -- render the lay layout to SVG, to scale, FROM Scene.

Every coordinate in the output comes from `slay.scene`. Nothing here
recomputes a station position from a formula, which is tracker item 27's
rule applied to a documentation figure: a drawing that derives geometry of
its own can assert a shape the model does not have. The first ASCII sketch
of this layout did exactly that -- it drew SR1 to SR2 as horizontal when
SR2 has already dropped 0.376 m -- so the figure is generated, not drawn.

SVG rather than mermaid, deviating from the docs/diagrams/*.mermaid
convention. Mermaid is a node-graph tool and cannot place anything to
scale; the whole value of this figure is that the proportions are real.

THE PROJECTION IS THE IDENTITY, which is the point worth noticing. SVG's y
axis already increases downward, and the model's +y is down, so y maps
straight through. The model's +x is toward the vessel and SVG's +x is
rightward, so the stinger (negative x) lands on the left and the vessel on
the right: the starboard view, with no flip and no negation anywhere.

    python3 tools/draw_layout.py [output.svg]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))

import config                                          # noqa: E402
from slay.scene import build_scene                     # noqa: E402
from slay.scene.rollers import StationRole             # noqa: E402

PX_PER_M = 11.0
PAD_L, PAD_R, PAD_T, PAD_B = 70, 70, 76, 168

INK = '#1f2933'
MUTED = '#7b8794'
DECK = '#334e68'
ARC = '#334e68'
ZONE = '#b44d12'
ONE_SIDED = '#1f7a8c'
BIDIR = '#2f6f3e'
FIXED = '#8b2f3f'
LOAD = '#6b4ea8'

ROLE_STYLE = {
    'one_sided': (ONE_SIDED, 'one-sided (uplift allowed)'),
    'bidir': (BIDIR, 'bidirectional'),
    'fixed': (FIXED, 'fixed, all DOF'),
    'load': (LOAD, 'tension applied, no contact'),
}


def classify(st):
    if st.role is StationRole.FIXED:
        return 'fixed'
    if st.role is StationRole.LOAD:
        return 'load'
    return 'one_sided' if st.one_sided else 'bidir'


def render(scene) -> str:
    xs = [st.x for st in scene.stations]
    ys = [st.y for st in scene.stations]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    W = PAD_L + PAD_R + (x_max - x_min) * PX_PER_M
    H = PAD_T + PAD_B + (y_max - y_min) * PX_PER_M

    def px(x):                      # +x right: vessel right, stinger left
        return PAD_L + (x - x_min) * PX_PER_M

    def py(y):                      # +y down maps straight to SVG's own +y
        return PAD_T + (y - y_min) * PX_PER_M

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
         f'width="{W:.0f}" height="{H:.0f}" font-family="ui-sans-serif,system-ui,sans-serif">',
         f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fdfdfc"/>']

    # -- the lay path, sampled from Scene's own path object ---------------
    s_lo = min(st.s_arc for st in scene.stations)
    s_hi = max(st.s_arc for st in scene.stations)
    pts, n = [], 400
    for k in range(n + 1):
        s = s_lo + (s_hi - s_lo) * k / n
        x, y = scene.path.position(s)
        pts.append(f'{px(x):.2f},{py(y):.2f}')
    o.append(f'<polyline points="{" ".join(pts)}" fill="none" '
             f'stroke="{ARC}" stroke-width="2.4"/>')

    # -- elastic end zones, highlighted along the path --------------------
    for (za, zb) in scene.elastic_zones:
        zp = []
        for k in range(61):
            s = za + (zb - za) * k / 60
            x, y = scene.path.position(s)
            zp.append(f'{px(x):.2f},{py(y):.2f}')
        o.append(f'<polyline points="{" ".join(zp)}" fill="none" '
                 f'stroke="{ZONE}" stroke-width="7" stroke-opacity="0.28" '
                 f'stroke-linecap="round"/>')

    # -- stations ---------------------------------------------------------
    for st in scene.stations:
        kind = classify(st)
        colour, _ = ROLE_STYLE[kind]
        cx, cy = px(st.x), py(st.y)
        filled = kind != 'load'
        o.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="5.4" '
                 f'fill="{colour if filled else "#fdfdfc"}" '
                 f'stroke="{colour}" stroke-width="2"/>')
        # push direction
        nx, ny = st.normal
        if st.is_contact:
            o.append(f'<line x1="{cx:.2f}" y1="{cy:.2f}" '
                     f'x2="{cx + nx * 19:.2f}" y2="{cy + ny * 19:.2f}" '
                     f'stroke="{colour}" stroke-width="1.8" '
                     f'marker-end="url(#tip)"/>')
        dy = -15 if st.name.startswith('VR') else 20
        o.append(f'<text x="{cx:.2f}" y="{cy + dy:.2f}" font-size="11.5" '
                 f'fill="{INK}" text-anchor="middle" font-weight="600">'
                 f'{st.name}</text>')

    o.insert(2, f'<defs><marker id="tip" viewBox="0 0 10 10" refX="8" refY="5" '
                f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
                f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{INK}"/></marker></defs>')

    # -- frame annotation -------------------------------------------------
    ax, ay = PAD_L - 34, PAD_T - 40
    o += [f'<line x1="{ax}" y1="{ay}" x2="{ax + 42}" y2="{ay}" stroke="{MUTED}" '
          f'stroke-width="1.6" marker-end="url(#tip)"/>',
          f'<text x="{ax + 48}" y="{ay + 4}" font-size="11" fill="{MUTED}">+x</text>',
          f'<line x1="{ax}" y1="{ay}" x2="{ax}" y2="{ay + 34}" stroke="{MUTED}" '
          f'stroke-width="1.6" marker-end="url(#tip)"/>',
          f'<text x="{ax - 22}" y="{ay + 34}" font-size="11" fill="{MUTED}">+y</text>',
          f'<text x="{ax + 78}" y="{ay + 4}" font-size="11" fill="{MUTED}">'
          f'+z into the page — right-handed; positive rotation reads clockwise</text>']

    o.append(f'<text x="{PAD_L}" y="{H - PAD_B + 54:.0f}" font-size="12.5" '
             f'fill="{MUTED}">&#8592; stinger / catenary</text>')
    o.append(f'<text x="{W - PAD_R:.0f}" y="{H - PAD_B + 54:.0f}" font-size="12.5" '
             f'fill="{MUTED}" text-anchor="end">vessel interior &#8594;</text>')

    # -- legend -----------------------------------------------------------
    ly = H - PAD_B + 78
    lx = PAD_L
    for kind in ('one_sided', 'bidir', 'fixed', 'load'):
        colour, label = ROLE_STYLE[kind]
        filled = kind != 'load'
        o.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" '
                 f'fill="{colour if filled else "#fdfdfc"}" stroke="{colour}" '
                 f'stroke-width="2"/>')
        o.append(f'<text x="{lx + 16}" y="{ly}" font-size="11.5" fill="{INK}">'
                 f'{label}</text>')
        lx += 24 + len(label) * 6.2
    o.append(f'<text x="{PAD_L}" y="{ly + 21}" font-size="11.5" fill="{ZONE}">'
             f'&#9644; forced-elastic end zone, {config.ELASTIC_END_ZONE_M:.0f} m '
             f'at each end</text>')

    # -- caption ----------------------------------------------------------
    sr2 = scene.by_name('SR2')
    o.append(f'<text x="{PAD_L}" y="{PAD_T - 12}" font-size="12.5" fill="{INK}" '
             f'font-weight="600">S-lay overbend layout — R = '
             f'{scene.path.R:.0f} m, spacing {scene.spacing:.0f} m, to scale</text>')
    o.append(f'<text x="{PAD_L}" y="{ly + 40}" font-size="11" fill="{MUTED}">'
             f'SR1 is the last station on the deck line; SR2 has already '
             f'dropped {sr2.y:.3f} m. Arrows show the direction each roller '
             f'pushes the pipe.</text>')
    o.append(f'<text x="{PAD_L}" y="{ly + 57}" font-size="11" fill="{MUTED}">'
             f'Generated from slay.scene by tools/draw_layout.py — no geometry '
             f'is recomputed here.</text>')

    o.append('</svg>')
    return '\n'.join(o)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        REPO / 'docs' / 'diagrams' / 'slay_lay_layout.svg')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(build_scene()) + '\n')
    print(f'wrote {out.relative_to(REPO)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

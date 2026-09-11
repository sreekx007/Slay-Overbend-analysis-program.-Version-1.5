"""
build_geometry_model.py -- PROTOTYPE. First end-to-end geometry assembly:
roller stations + pipeline line + EA-ST placed between SR1 and SR2.

NO MESHING. This builds and draws GEOMETRY only -- lines and nodes, no
elements. The mesher does not exist yet.

Conventions applied (tracker):
  16  node positions on the straight pipeline use ARC LENGTH, not
      rectangular x. Stinger station i sits at s = i * spacing along the
      pipe, NOT at -R*sin(theta). The rectangular position is where that
      material point ENDS UP once draped; the straight (undeformed) model
      is laid out in arc length so material length is right by
      construction.
  22  geometry vs structural lines; nodes DERIVED from parameters.
  25  named connection systems; 2-node connectors, pipe side always Fixed.
   1  P_vt = 1.5D, L_top = 16D, H_top = 4D for EA-ST.
"""
import sys; sys.path.insert(0, '.')
import numpy as np
import config
import component_spec as cs
from gdst_dataclass_proposal import TopStructure
from connection_systems_proposal import NAMED_SYSTEMS, slot_xs, default_spans

D = cs.STD_PIPELINE.OD_pipe


# ---------------------------------------------------------------- step 1
def roller_stations(R=None, n_sr=None, n_vr=None, spacing=None):
    """(name, s_arc, x_rect, y_rect, dia) per station.

    s_arc  -- arc length from SR1. THIS is the straight-pipeline node
              position (item 16).
    x_rect/y_rect -- where the station physically sits in space. Used for
              drawing the stinger and for contact targets, NOT for laying
              out the undeformed pipe.
    """
    R = R or config.R_STINGER_DEF
    n_sr = n_sr or config.N_SR
    n_vr = n_vr or config.N_VR
    spacing = spacing or config.ROLLER_SPACING
    dia = 2 * config.ROLLER_RADIUS_DEF
    dtheta = spacing / R
    out = []
    for j in range(n_vr, 0, -1):            # vessel side: straight deck
        s = -j * spacing
        out.append((f'VR{j}', s, s, 0.0, dia))
    for i in range(1, n_sr + 1):            # stinger side: on the arc
        th = (i - 1) * dtheta
        out.append((f'SR{i}', R * th, -R * np.sin(th), R * (1 - np.cos(th)), dia))
    return out


# ---------------------------------------------------------------- step 2
def pipeline_line(stations, margin=2.0):
    """Straight undeformed pipeline: 2 end nodes in ARC-LENGTH space."""
    s0 = min(st[1] for st in stations) - margin
    s1 = max(st[1] for st in stations) + margin
    return dict(nodes=[('PIPE:start', s0, 0.0), ('PIPE:end', s1, 0.0)],
                 line=('pipeline', ('PIPE:start', 'PIPE:end')))


# ---------------------------------------------------------------- step 3
def place_east(between=('SR1', 'SR2'), system='F2D', stations=None):
    """Centre an EA-ST midway between two named stations, in ARC LENGTH."""
    pos = {n: s for n, s, *_ in stations}
    s_lo, s_hi = pos[between[0]], pos[between[1]]
    centre = 0.5 * (s_lo + s_hi)
    st = TopStructure(pipe=cs.STD_PIPELINE, centre_x=centre)
    spans = default_spans(st.L_top)
    xs = slot_xs(centre, **spans)
    types = NAMED_SYSTEMS[system]
    conns = [(i + 1, x, t) for i, (x, t) in enumerate(zip(xs, types))
             if t is not None]
    return st, conns, spans, (s_lo, s_hi)


def build(system='F2D'):
    stations = roller_stations()
    pipe = pipeline_line(stations)
    east, conns, spans, span_pair = place_east(system=system, stations=stations)
    return dict(stations=stations, pipe=pipe, east=east, conns=conns,
                 spans=spans, span_pair=span_pair, system=system)


if __name__ == '__main__':
    m = build('F2D')
    print('ROLLER STATIONS  (s_arc = straight-pipe node position)')
    for n, s, xr, yr, d in m['stations']:
        print(f'  {n:5} s_arc={s:8.3f}   rect=({xr:8.3f},{yr:6.3f})   '
              f'{"[arc != rect]" if abs(s-xr) > 1e-9 else ""}')
    e = m['east']
    print(f"\nPIPELINE line: s {m['pipe']['nodes'][0][1]:.3f} -> "
          f"{m['pipe']['nodes'][1][1]:.3f} m  (2 end nodes, straight)")
    print(f"\nEA-ST '{m['system']}' centred at s={e.centre_x:.3f} "
          f"(midway between SR1={m['span_pair'][0]:.1f} and SR2={m['span_pair'][1]:.1f})")
    print(f"  L_top {e.L_top:.4f}  H_top {e.H_top:.4f}  P_vt {e.P_vt:.4f}")
    print(f"  extent s = {e.extent[0]:.3f} .. {e.extent[1]:.3f}")
    print(f"  geometry nodes {len(e.geometry_nodes())}, "
          f"structural members {len(e.structural_lines())}")
    print(f"  P_c1 {m['spans']['P_c1']:.4f}  P_c2 {m['spans']['P_c2']:.4f}")
    print(f"  connectors ({len(m['conns'])}):")
    for slot, x, t in m['conns']:
        print(f'    slot {slot}  s={x:8.3f}  type {t}   '
              f'pipe-node FIXED -> EA-node {t}')

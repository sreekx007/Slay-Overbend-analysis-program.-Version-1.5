#!/usr/bin/env python3
"""plot_simple_ils.py -- draw an ILS-SIMPLE against the layout it replaces.

    python3 tools/plot_simple_ils.py                 # every docs/simple/*.json
    python3 tools/plot_simple_ils.py --case B3
    python3 tools/plot_simple_ils.py --out docs/diagrams

READER, NOT GENERATOR (G13). Everything drawn comes from
`docs/simple/<case>.json`, written by `tools/simplify_ils.py`. This file
re-instantiates the two ILS definitions from the parameters recorded there
and asks each assembly for its own geometry -- `section_at` for a wall,
`contact_at` for a surface a roller would touch. It computes no reduction
of its own, so the figure can be checked against the reduction it claims to
show. Instantiating a definition is not running an analysis: there is no
scene, no mesh, no solve, and nothing here is deformed.

THE LOCAL FRAME, UNDEFORMED. x is ILS-local, measured from the component
centre; the stinger does not appear. +y is DOWN, as everywhere in this
project, so the axis is inverted and the roller datum sits at the bottom of
the panel where a reader expects it.

WHAT THE FIGURE IS FOR. A simplification is a claim that two different
pieces of hardware present the same thing to the rollers. The claim is
visual: the dashed outline is the original GD-TP, the filled one is the
stand-in, and they must start and stop together and reach the same depth.
What they must NOT share is the wall -- the stand-in carries the pipeline's
own section and makes up the stiffness with its modulus, which is why the
body is annotated with E rather than with a thickness.
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
from slay.define.simple import build                        # noqa: E402

D = 0.4064
SRC = REPO / 'docs' / 'simple'
DEFAULT_OUT = REPO / 'docs' / 'diagrams'

INK = '#1f2933'
MUTED = '#7b8794'
PIPE = '#cbd2d9'
BORE = '#ffffff'
BODY = '#6b4ea8'
SHROUD = '#1f7a8c'
ORIG = '#8b2f3f'
DATUM = '#334e68'


def _profile(assembly, lo, hi, n=1600):
    """[(x, OD_at_x, contact_y_at_x)] -- asked, never derived."""
    out = []
    for k in range(n):
        x = lo + (hi - lo) * k / (n - 1)
        sec = assembly.section_at(x)
        con = assembly.contact_at(x)
        out.append((x,
                    getattr(sec, 'OD', None) if sec is not None else None,
                    getattr(con, 'y', None) if con is not None else None))
    return out


def draw(rec, out_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    s_, e_, src = rec['simple'], rec['equivalent'], rec['source']
    sm = build(E=s_['E'], L_body=s_['L_body'], V=s_['V'],
               L1=s_['L1'], L2=s_['L2'], centre_x=s_['centre_x'])
    orig = gen.build_component_ils('ILS-TP', L_OD=src['L_OD'],
                                   t_ratio=src['t_mm'] / 21.0)

    OD_p = src['OD_pipe']
    half = OD_p / 2.0
    lo = min(sm.extent[0], orig.extent[0]) - 1.2 * D
    hi = max(sm.extent[1], orig.extent[1]) + 1.2 * D

    fig, ax = plt.subplots(figsize=(13.4, 5.2))

    # ---- the pipeline, running the whole panel -------------------------
    ax.fill_between([lo, hi], [-half, -half], [half, half],
                    color=PIPE, zorder=1)
    ax.fill_between([lo, hi], [-half + src['t_pipe']] * 2,
                    [half - src['t_pipe']] * 2, color=BORE, zorder=2)

    # ---- the ORIGINAL GD-TP, dashed ------------------------------------
    po = _profile(orig.assembly, orig.extent[0], orig.extent[1])
    xs_o = [r[0] for r in po]
    od_o = [(r[1] or OD_p) / 2.0 for r in po]
    ax.plot(xs_o, od_o, color=ORIG, lw=2.0, ls='--', zorder=7)
    ax.plot(xs_o, [-v for v in od_o], color=ORIG, lw=2.0, ls='--', zorder=7)
    for x, v in ((orig.extent[0], od_o[0]), (orig.extent[1], od_o[-1])):
        ax.plot([x, x], [-v, v], color=ORIG, lw=2.0, ls='--', zorder=7)

    # ---- the STAND-IN: elastic body on the pipeline section ------------
    bl, bh = sm.body_extent
    ax.fill_between([bl, bh], [-half, -half], [half, half],
                    color=BODY, alpha=0.32, zorder=3)
    ax.fill_between([bl, bh], [-half + src['t_pipe']] * 2,
                    [half - src['t_pipe']] * 2, color=BORE, zorder=4)
    for x in (bl, bh):
        ax.plot([x, x], [-half, half], color=BODY, lw=2.4, zorder=5)

    # ---- the shroud, from the pipe's own bottom down to contact --------
    ps = _profile(sm.ils.assembly, sm.extent[0], sm.extent[1])
    xs_s = [r[0] for r in ps if r[2] is not None and r[2] > half + 1e-9]
    ys_s = [r[2] for r in ps if r[2] is not None and r[2] > half + 1e-9]
    if xs_s:
        ax.fill_between(xs_s, [half] * len(xs_s), ys_s,
                        color=SHROUD, alpha=0.60, zorder=5)
        ax.plot(xs_s, ys_s, color=SHROUD, lw=2.2, zorder=6)

    # ---- the roller datum ----------------------------------------------
    V = s_['V']
    ax.axhline(V, color=DATUM, lw=1.3, ls=':', zorder=2)
    ax.axhline(half, color=MUTED, lw=1.0, ls=':', zorder=2)
    x_lift = lo + 0.52 * (hi - lo)
    ax.annotate('', xy=(x_lift, V), xytext=(x_lift, half),
                arrowprops=dict(arrowstyle='<->', color=DATUM, lw=1.3))
    ax.text(x_lift, -0.30 * D,
            f'lift {1000 * e_["lift"]:.1f} mm\nthe GD-TP bottom and the '
            f'shroud flat are the SAME line',
            color=DATUM, fontsize=8.5, va='center', ha='center', zorder=9,
            bbox=dict(boxstyle='round,pad=0.30', fc='white', ec=DATUM,
                      lw=0.8, alpha=0.93))

    # ---- the length dimension ------------------------------------------
    y_dim = V + 0.30 * D
    ax.annotate('', xy=(bl, y_dim), xytext=(bh, y_dim),
                arrowprops=dict(arrowstyle='<->', color=INK, lw=1.3))
    ax.text(0.5 * (bl + bh), y_dim + 0.09 * D,
            f'L = {e_["L"]:.4f} m = {e_["L_D"]:.4g} D   '
            f'— body and shroud footprint, both matched to the original',
            ha='center', va='top', fontsize=8.5, color=INK)

    ax.set_xlim(lo, hi)
    y_hi, y_lo = V + 0.46 * D, -0.80 * D
    ax.set_ylim(y_hi, y_lo)                      # +y DOWN

    # NOT TO EQUAL SCALE, and the factor is stated rather than left to be
    # discovered. A 406 mm pipe on a 40 D body is 1:40; drawn true the
    # geometry is a hairline and the figure says nothing. The exaggeration
    # is vertical only, so every HORIZONTAL dimension on the panel is true
    # and the two outlines still start and stop together where they must.
    ax.set_xlabel('ILS-local x  [m]   (catenary side is negative x)')
    ax.set_ylabel('y, down  [m]')
    ax.grid(alpha=0.18, lw=0.6)

    ax.set_title(
        f'{rec["case"]} — ILS-SIMPLE for GD-TP '
        f'{src["t_mm"]} mm x {src["L_OD"]:g} D   '
        f'(TABLE {rec["table"]}, R = {rec["R"]:g} m, '
        f'{rec["tension_mt"]:g} MT)\n'
        f'EI/EI_pipe = {e_["EI_ratio"]:.3f}  ->  body E = '
        f'{e_["E_equiv"] / 1e9:.0f} GPa on the PIPELINE section, fully '
        f'elastic   |   axial stiffness {100 * e_["EA_error"]:+.1f}%, '
        f'which one modulus cannot match as well', fontsize=10)

    ax.legend(handles=[
        Patch(facecolor='none', edgecolor=ORIG, ls='--', lw=2.0,
              label=f'GD-TP as built — OD {1000 * src["OD_comp"]:.1f} mm, '
                    f't {1000 * src["t_comp"]:.0f} mm, J2 steel'),
        Patch(facecolor=BODY, alpha=0.32, edgecolor=BODY,
              label=f'GD-Simple body — PIPELINE section (OD '
                    f'{1000 * OD_p:.1f} mm), E '
                    f'{e_["E_equiv"] / 1e9:.0f} GPa, fully elastic'),
        Patch(facecolor=SHROUD, alpha=0.60, edgecolor=SHROUD,
              label=f'GD-SH — V {s_["V"]:.4f} m = {s_["V"] / D:.3f} D to '
                    f'the bottom flat, L1 {s_["L1"]:.4f} m, '
                    f'L2 {s_["L2"]:g} m'),
    ], loc='upper center', bbox_to_anchor=(0.5, -0.20), ncol=1,
        fontsize=8.5, framealpha=0.96)

    fig.tight_layout()

    # MEASURED AFTER THE LAYOUT IS FINAL, because the axes box is what sets
    # it and `tight_layout` moves that box. Computed before, this came out
    # as its own reciprocal and printed "x0" -- a figure stating its own
    # scale wrongly is worse than one not stating it.
    #
    # True scale is one metre of x covering the same paper as one metre of
    # y. The factor is how much taller than true the y axis is drawn.
    w_in, h_in = fig.get_size_inches()
    bb = ax.get_position()
    per_m_x = (w_in * bb.width) / (hi - lo)
    per_m_y = (h_in * bb.height) / abs(y_hi - y_lo)
    # "EXAGGERATION" ONLY READS RIGHT ABOVE 1, and on the 2.5 D cases this
    # comes out at 0.6 -- the vertical is COMPRESSED, because a short body
    # needs little x. Stated as a scale ratio, which is true either way.
    ax.text(0.995, 0.04,
            f'vertical scale x{per_m_y / per_m_x:.1f} of horizontal '
            f'(true scale = x1.0)',
            transform=ax.transAxes, ha='right', va='bottom',
            fontsize=8, color=MUTED, style='italic')

    out = Path(out_dir) / f'simple_{rec["case"].lower()}.png'
    fig.savefig(out, dpi=135)
    plt.close(fig)
    return out


def main() -> int:
    def arg(flag, cast, default):
        return cast(sys.argv[sys.argv.index(flag) + 1]) \
            if flag in sys.argv else default

    only = arg('--case', str, '')
    out_dir = Path(arg('--out', str, str(DEFAULT_OUT)))
    out_dir.mkdir(parents=True, exist_ok=True)

    files = ([SRC / f'simple_{only.lower()}.json'] if only
             else sorted(SRC.glob('simple_*.json')))
    if not files or not all(f.exists() for f in files):
        print(f'no reduction artifacts in {SRC}. Run '
              f'`python3 tools/simplify_ils.py` first -- this tool reads '
              f'what that one writes and derives nothing itself (G13).')
        return 1
    for f in files:
        rec = json.loads(f.read_text())
        print(f'  {f.name} -> {draw(rec, out_dir).relative_to(REPO)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

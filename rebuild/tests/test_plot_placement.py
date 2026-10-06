"""The figure must put the material under the roller that is holding it.

L070: the component-on-stinger plot drew the pipe a full `shift` short of
the rollers, so the peak strain appeared to occur BEFORE the component
reached SR2. It was spotted by eye and by nothing else -- the residuals, the
contact misses and every strain check are all blind to it, because the
solver is RIGHT to omit the translation: sliding a pipe along its own axis
produces no strain, so nothing drives it and the shape is correct without
it. The world mapping is where it belongs, and only a drawing shows it.
"""

import pytest

pytest.importorskip('numpy')
pytest.importorskip('matplotlib')

import plot_stinger as ps                                    # noqa: E402

from slay.scene.path import LayPath # noqa: E402
from slay.model.assemble import build_model                  # noqa: E402
from slay.physics.problem import build_problem               # noqa: E402
from slay.solve.kernel import mesh_of_problem                # noqa: E402
from slay.study import sweep                                 # noqa: E402

TON = 9806.65
OD = 0.4064


@pytest.fixture(scope='module')
def swept():
    """A solved plain-pipe position at a NONZERO shift. Elastic, so it is
    cheap -- the defect is geometric and does not need plasticity."""
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0,
                         clear_before=0.0, clear_after=2 * OD)
    pos = sweep.run(sc, None, L_comp=0.0, clear_before=0.0,
                    clear_after=2 * OD, step=2 * OD,
                    tension=120 * TON, material=None)
    last = [p for p in pos if p.converged][-1]
    assert last.shift > 0.5, 'this test needs a real shift'
    m = build_model(sc, None, s_centre=0.0,
                    extra_stations=sweep._required_stations(sc))
    p = build_problem(m, sc, shift=last.shift, tension=120 * TON,
                      material=None)
    ms, _mdl, _ix = mesh_of_problem(p)
    return sc, m, p, last, ms


def test_the_drawn_material_sits_under_its_own_roller(swept):
    """THE REGRESSION. Each contact station holds a material point; drawn in
    world coordinates that point must be at the roller, not a shift away.

    THE REFERENCE IS THE PIPE'S OWN ARC, not the roller centreline arc.
    `scene.path` has radius R, measured to the roller centres; the pipe
    CENTRELINE rides at `R + r_roller + OD/2` under the default contact
    surface, and a point on a larger arc at the same angle is further along
    in x -- 0.053 m at SR2 rising to 0.299 m at SR7. Compared against the
    roller centre instead, this reads 0.319 m and looks exactly like the
    missing-shift bug it was written to catch. It is geometry (6 Oct 2026).

    The regression it guards is unaffected: a dropped shift is 0.8 m here,
    which `test_omitting_the_shift_is_what_breaks_it` still demonstrates.
    """
    from slay.physics.contact import station_material
    sc, m, p, pos, ms = swept
    fx = ps.s_to_x(m, ms, pos.result.U, pos.shift)
    slot = station_material(sc)          # shift-independent, like s_station
    worst = 0.0
    for t in p.contacts:
        if not t.station.startswith('SR'):
            continue
        # The STATION's own place on the arc the pipe rides. `t.s_material`
        # is that minus the shift -- which material is there now -- so the
        # reference has to be the slot, or the shift is counted twice and
        # this reads as the very bug it guards.
        here = LayPath(R=t.R_eff).position(slot[t.station])[0]
        worst = max(worst, abs(fx(t.s_material) - here))
    assert worst < 0.15, (
        f'the drawn pipe is {worst:.3f} m from the rollers holding it; '
        f'the shift ({pos.shift:.3f} m) is missing from the world mapping')


def test_omitting_the_shift_is_what_breaks_it(swept):
    """The same check WITHOUT the shift must fail, or the test above would
    pass for a reason that has nothing to do with the defect."""
    sc, m, p, pos, ms = swept
    fx = ps.s_to_x(m, ms, pos.result.U)          # no shift -- the old mapping
    worst = max(abs(fx(t.s_material) - sc.path.position(t.s_station)[0])
                for t in p.contacts if t.station.startswith('SR'))
    assert worst == pytest.approx(pos.shift, abs=0.05), \
        "the error the old mapping makes IS the shift, to within the pipe's " \
        'own tangential displacement'


def test_the_pipe_polyline_carries_the_shift_too(swept):
    """`pipe_xy` draws the line itself and must agree with `s_to_x`."""
    _sc, m, _p, pos, ms = swept
    a, _ya, _ids = ps.pipe_xy(m, ms, pos.result.U, pos.shift)
    b, _yb, _ids2 = ps.pipe_xy(m, ms, pos.result.U)
    assert (b - a).min() == pytest.approx(pos.shift, abs=1e-9)
    assert (b - a).max() == pytest.approx(pos.shift, abs=1e-9)


def test_the_excluded_band_covers_the_stinger_end_not_the_vessel_end(swept):
    """L072. The zone drops the last three STINGER rollers -- high station
    `s`, which the world mapping sends to the most NEGATIVE x. Taking
    `fx(min(s))` rather than `min(fx(s))` shaded from the vessel end and
    covered the half of the model that is IN the band.
    """
    sc, m, p, pos, ms = swept
    fx = ps.s_to_x(m, ms, pos.result.U, pos.shift)
    s_mats = [q for (_i, q, _e) in pos.result.strains]
    s_cut = max(t.s_arc for t in sc.stations if t.name.startswith('SR')) - 18.0
    lo, hi = ps.excluded_span(fx, s_mats, s_cut, pos.shift)
    assert lo < hi, 'a span, low to high'
    xs = [fx(q) for q in s_mats]
    assert lo <= min(xs), 'it reaches the stinger tip'
    assert hi < 0.0, 'and stops on the stinger side of the deck, not past it'
    # The vessel end must be OUTSIDE the shaded band -- the defect put it in.
    assert max(xs) > hi, 'the vessel end is in the reporting band'


# -- drawing the bodies ----------------------------------------------------

def test_the_offset_is_perpendicular_not_vertical():
    """The pipe turns through 0.64 rad over the stinger, so a wall drawn by
    adding OD/2 to `y` would be up to 20% narrow at SR7 and perpendicular to
    the pipe nowhere on the arc."""
    import math
    t = [i * 0.1 for i in range(40)]
    px = [q for q in t]
    py = [q for q in t]                       # a 45 degree line
    ox, oy = ps.offset_polyline(px, py, 1.0)
    mid = len(t) // 2
    dx, dy = ox[mid] - px[mid], oy[mid] - py[mid]
    assert math.hypot(dx, dy) == pytest.approx(1.0, abs=1e-6), \
        'the offset distance is the distance asked for'
    assert dx * 1.0 + dy * 1.0 == pytest.approx(0.0, abs=1e-6), \
        'and it is perpendicular to the line, not vertical'


def test_the_offset_points_toward_the_rollers():
    """Node order runs in -x, so the normal must come out +y (down), the
    side the rollers are on. The opposite sign would hang every component
    above the pipe."""
    px = [-q for q in range(20)]
    py = [0.0] * 20
    _ox, oy = ps.offset_polyline(px, py, 0.2)
    assert oy[5] > 0.0


_RING_CACHE = {}


def _rings(aid):
    """Cached: `component_case` solves a WHOLE PASSAGE, and five tests asking
    for it separately added about two minutes to the suite for no extra
    coverage."""
    if aid not in _RING_CACHE:
        c = ps.component_case(aid)
        _RING_CACHE[aid] = (c, ps.body_outlines(
            c['model'], c['ms'], c['result'].U, c['ils'], c['s_centre'],
            c['OD'], c['position'].shift))
    return _RING_CACHE[aid]


def _thickness(ring):
    import numpy as np
    rx, ry = ring
    n = len(rx) // 2
    return np.hypot(rx[n:][::-1] - rx[:n], ry[n:][::-1] - ry[:n])


def test_the_pipe_is_drawn_with_its_own_wall_thickness():
    _c, r = _rings('ILS-TP')
    t = _thickness((r['pipe'][0], r['pipe'][1]))
    bore = _thickness(r['bore'])
    assert t.min() == pytest.approx(0.4064, abs=1e-6)
    assert (t - bore).min() / 2.0 == pytest.approx(0.021, abs=1e-6)


def test_a_section_changing_body_is_drawn_at_its_own_OD():
    """GD-TP replaces the pipe wall over its span, so it is drawn at
    `section_at(x).OD` and is CONSTANT -- a plain thick pipe does not
    taper."""
    _c, r = _rings('ILS-TP')
    assert r['body'] is not None and r['shroud'] is None
    t = _thickness(r['body'])
    assert t.min() == pytest.approx(0.4484, abs=1e-4)
    assert t.max() == pytest.approx(t.min(), abs=1e-6), 'constant, no taper'


def test_a_contact_only_body_is_NOT_drawn_at_a_section_OD():
    """THE DISTINCTION THIS ENCODES. `section_at` returns the PIPE section
    right through a shroud, because a shroud adds no bending stiffness.
    Drawing it at a section OD would invent a stiffness the model does not
    have -- and its `stiffness_ratio` is 1.0, which says so."""
    _c, r = _rings('ILS-SH')
    assert r['shroud'] is not None and r['body'] is None
    t = _thickness(r['shroud'])
    assert t.max() == pytest.approx(0.2032, abs=1e-3), 'V - OD/2 at the plateau'
    assert t.min() < 0.01, 'and it goes to zero at the taper ends'


def test_the_outline_is_resampled_off_the_component_not_the_mesh():
    """At the ruled 2xOD density a 6 m shroud spans seven NODES and its
    taper ends fall between them, which drew a 95 mm step where the geometry
    goes to zero."""
    _c, r = _rings('ILS-SH')
    assert len(r['shroud'][0]) // 2 > 40, 'far more points than mesh nodes'


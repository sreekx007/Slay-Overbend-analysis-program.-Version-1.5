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
    world coordinates that point must be at the roller, not a shift away."""
    sc, m, p, pos, ms = swept
    fx = ps.s_to_x(m, ms, pos.result.U, pos.shift)
    worst = 0.0
    for t in p.contacts:
        if not t.station.startswith('SR'):
            continue
        roller_x = sc.path.position(t.s_station)[0]
        worst = max(worst, abs(fx(t.s_material) - roller_x))
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

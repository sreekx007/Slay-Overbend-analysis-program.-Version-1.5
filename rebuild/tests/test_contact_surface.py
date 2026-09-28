"""L4 -- the contact surface option, and the pairing it cannot break.

WHAT THIS PINS. 'centreline' is the default and reproduces every validated
number bit for bit; 'bottom' rides the pipe centreline at `R + r_roller +
OD/2`; the offset enters through the RADIUS and never as a translation, so
the deck is untouched; and the material position moves with the target,
because nodes here are placed by arc length and the pipe does not stretch.
"""

import math

import pytest

pytest.importorskip('numpy')

from slay.model.assemble import build_model                   # noqa: E402
from slay.physics.contact import (arc_target,                 # noqa: E402
                                  arc_target_by_projection,
                                  contact_targets,
                                  effective_radius)
from slay.physics.problem import build_problem, differs_only_in_contact  # noqa: E402
from slay.scene.path import LayPath                           # noqa: E402
from slay.scene.scene import build_scene                      # noqa: E402

OD = 0.4064
R_ROLLER = 0.30


@pytest.fixture(scope='module')
def scene():
    return build_scene(R=85.0, spacing=9.0)


@pytest.fixture(scope='module')
def model(scene):
    return build_model(scene)


def _sr(targets):
    return [t for t in targets if t.station.startswith('SR')]


# -- the radius ------------------------------------------------------------

def test_the_effective_radius_is_the_roller_and_pipe_radii():
    """`R` is to the roller CENTRELINE; the pipe's bottom rests on the
    roller's top, so the centreline rides `r_roller + OD/2` further out."""
    assert effective_radius(85.0, R_ROLLER, OD) == 85.0, 'centreline default'
    assert effective_radius(85.0, R_ROLLER, OD, 'bottom') == \
        pytest.approx(85.0 + 0.30 + 0.2032)


def test_an_unknown_surface_is_refused():
    """A typo must not silently select the legacy mode."""
    with pytest.raises(ValueError, match='contact_surface'):
        effective_radius(85.0, R_ROLLER, OD, 'botom')


# -- the default moves nothing --------------------------------------------

def test_the_default_reproduces_the_validated_targets_exactly(model, scene):
    """Every number in docs/RESULTS.md was computed on 'centreline'. The
    option is worthless if adopting it moves them, so the default is bitwise
    identical -- not approximately."""
    base = contact_targets(model, scene)
    named = contact_targets(model, scene, contact_surface='centreline')
    for a, b in zip(base, named):
        assert a.dn == b.dn and a.s_material == b.s_material
        assert a.R_eff == scene.path.R


# -- it enters through the radius, never as a translation ------------------

def test_the_straight_deck_is_untouched(model, scene):
    """THE FAILURE THIS AVOIDS, measured in the reference toolchain: lifting
    every roller while the anchor stays pinned at zero forces a spurious kink
    and moved the plain-pipe peak from x = -38 m onto the anchor at x = +79 m,
    raising it 10.5%. A uniform normal offset matters only through the
    curvature it produces, and on the deck there is none."""
    bot = contact_targets(model, scene, contact_surface='bottom')
    for t in bot:
        if t.theta == 0.0:
            assert t.dn == 0.0, f'{t.station} on the deck must not be lifted'
            assert t.s_material == pytest.approx(t.s_station), \
                'and its material must not move either'
    assert any(t.theta == 0.0 for t in bot), 'the scene has deck stations'


def test_the_arc_targets_deepen_by_the_radius_ratio(model, scene):
    """`dn` is proportional to the radius at fixed angle, so every arc
    station must deepen by exactly `R_eff / R` -- one number, not seven."""
    cl = {t.station: t for t in _sr(contact_targets(model, scene))}
    bot = {t.station: t for t in
           _sr(contact_targets(model, scene, contact_surface='bottom'))}
    ratio = effective_radius(85.0, R_ROLLER, OD, 'bottom') / 85.0
    on_arc = [n for n in cl if cl[n].theta > 0.0]
    assert on_arc
    for n in on_arc:
        assert bot[n].dn == pytest.approx(cl[n].dn * ratio, rel=1e-12), n
    assert ratio == pytest.approx(1.00592, abs=1e-5), 'about +0.6%'


# -- dn and the material position are a HARD PAIR -------------------------

def test_the_material_position_moves_with_the_target(model, scene):
    """Nodes are placed by ARC LENGTH and the pipe does not stretch, so the
    material touching the roller at angle `theta` lies at pipe-arc
    `R_eff * theta`, not at the station's `s_arc = R * theta`. Move `dn`
    without this and the right target is applied to the wrong material --
    the same class of error as L048, and it converges just as happily."""
    R = scene.path.R
    R_eff = effective_radius(R, R_ROLLER, OD, 'bottom')
    for t in _sr(contact_targets(model, scene, contact_surface='bottom')):
        assert t.s_material == pytest.approx(
            t.s_station + (R_eff - R) * t.theta), t.station
        if t.theta > 0.0:
            assert t.s_material == pytest.approx(R_eff * t.theta), t.station


def test_the_correction_reaches_a_third_of_a_metre_at_the_tip(model, scene):
    """It is not a rounding term: big enough to change which element the
    slot brackets."""
    tip = max(_sr(contact_targets(model, scene, contact_surface='bottom')),
              key=lambda t: t.s_station)
    assert tip.s_material - tip.s_station == pytest.approx(0.32, abs=0.01)


def test_the_shift_still_carries_the_material_past_the_station(model, scene):
    """The sweep's contract is untouched: a shift moves the material read,
    whatever the contact surface."""
    a = _sr(contact_targets(model, scene, contact_surface='bottom'))
    b = _sr(contact_targets(model, scene, shift=2.0, contact_surface='bottom'))
    for x, y in zip(a, b):
        assert y.s_material == pytest.approx(x.s_material - 2.0)


# -- the closed form is still the projection it claims to be --------------

def test_the_closed_form_at_R_eff_is_still_a_projection(model, scene):
    """`arc_target` is DERIVED, and the derivation must survive the swap.
    Checked against the existing projection routine on a path of radius
    R_eff -- reusing verified machinery rather than restating the algebra."""
    R_eff = effective_radius(scene.path.R, R_ROLLER, OD, 'bottom')
    path = LayPath(R=R_eff)
    for t in _sr(contact_targets(model, scene, contact_surface='bottom')):
        assert t.dn_arc == pytest.approx(
            arc_target_by_projection(path, R_eff * t.theta), abs=1e-12), \
            t.station


def test_zero_angle_gives_zero_whatever_the_radius():
    """Why the deck is safe, stated as the property it rests on."""
    for R in (70.0, 85.0, 105.0, 85.5032):
        assert arc_target(R, 0.0) == 0.0


# -- it is a contact property and nothing else ----------------------------

def test_two_problems_differing_only_in_surface_differ_only_in_contact(model, scene):
    """T4's DONE WHEN clause still holds, so a sweep may vary it freely."""
    a = build_problem(model, scene, tension=1.0e6)
    b = build_problem(model, scene, tension=1.0e6, contact_surface='bottom')
    assert differs_only_in_contact(a, b)
    assert a.contacts != b.contacts, 'and it really did change something'


def test_the_roller_radius_is_now_read_not_merely_carried(model, scene):
    """It was written onto every target and read nowhere. Vary it and the
    effective radius must follow, or the option is not using it."""
    wide = build_scene(R=85.0, spacing=9.0, radii={'SR3': 0.50})
    t = [x for x in contact_targets(build_model(wide), wide,
                                    contact_surface='bottom')
         if x.station == 'SR3'][0]
    assert t.radius == pytest.approx(0.50)
    assert t.R_eff == pytest.approx(85.0 + 0.50 + OD / 2.0)


# -- the schedule and the slots must agree --------------------------------

def test_the_edge_crossings_follow_the_contact_surface(scene):
    """THE BUG THIS PINS, found by measuring rather than by reading.

    `study.sweep.critical_shifts` puts the edge crossings into the schedule.
    It computed them from the station's own `s_arc` while the slots had moved
    to `s_arc + (R_eff - R) * theta`, so under 'bottom' the sweep solved
    travels the contact never saw: the GD-TP envelope came out 14.5% low and
    on the wrong position. Both now read `physics.contact.station_material`.
    """
    from slay.physics.contact import station_material
    from slay.study import sweep

    L, c = 1.0, 7.5
    cl = sweep.critical_shifts(scene, L, c)
    bot = sweep.critical_shifts(scene, L, c, 'bottom')
    assert cl != bot, 'the surface must move the crossings'

    lead = c + L / 2.0
    for surf in ('centreline', 'bottom'):
        got = sweep.critical_shifts(scene, L, c, surf)
        mat = station_material(scene, surf)
        want = mat['SR2'] - lead
        assert pytest.approx(want) in got, \
            f'{surf}: the leading edge must cross SR2 where the SLOT is'


def test_the_crossing_offset_is_the_material_correction(scene):
    """And it is the same correction, not a coincidentally similar one."""
    from slay.physics.contact import station_material
    from slay.study import sweep
    L, c = 1.0, 7.5
    mat_cl = station_material(scene, 'centreline')
    mat_bot = station_material(scene, 'bottom')
    a = sweep.critical_shifts(scene, L, c)
    b = sweep.critical_shifts(scene, L, c, 'bottom')
    # SR2's leading-edge crossing, in each
    lead = c + L / 2.0
    ia = mat_cl['SR2'] - lead
    ib = mat_bot['SR2'] - lead
    assert ib - ia == pytest.approx(mat_bot['SR2'] - mat_cl['SR2'])
    assert ia in [pytest.approx(v) for v in a]
    assert ib in [pytest.approx(v) for v in b]


def test_a_plain_pipe_passage_has_no_crossings_under_either_surface(scene):
    """No edges, so nothing to cross, whatever radius the pipe rides."""
    from slay.study import sweep
    assert sweep.critical_shifts(scene, 0.0, 0.0) == ()
    assert sweep.critical_shifts(scene, 0.0, 0.0, 'bottom') == ()

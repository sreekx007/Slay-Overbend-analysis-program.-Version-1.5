"""T2 -- slay.scene.

The VERIFY table in docs/modules/T2_scene_spec.md section 6 is checks 1-10
below. The rest cover the coordinate frame and the two rulings, because
those are where this module's errors would be plausible rather than loud.
"""

import math

import pytest

import config
from slay.scene import LayPath, StationRole, build_scene, roller_stations


# --------------------------------------------------------------------------
# Check 1 -- arc length and x diverge on the stinger, agree on the deck
# --------------------------------------------------------------------------

@pytest.mark.parametrize('R, expected', [(85.0, 1.460), (70.0, 2.142)])
def test_arc_vs_rectangular_divergence(R, expected):
    """The whole reason node positions follow arc length (tracker item 16).

    NOTE these are the figures at the configured 8 m spacing. Tracker item
    16 quotes 2.07 m and 3.04 m, which reproduce only at 9 m spacing -- a
    test written from those numbers fails against the real default and
    invites the conclusion that the code is wrong.
    """
    sc = build_scene(R=R)
    sr1, sr6 = sc.by_name('SR1'), sc.by_name('SR6')
    arc = sr6.s_arc - sr1.s_arc
    dx = abs(sr6.x - sr1.x)
    assert arc == pytest.approx(40.0)
    assert (arc - dx) == pytest.approx(expected, abs=1e-3)


def test_arc_and_x_agree_on_the_deck():
    """The deck is straight, so the distinction only bites on the arc."""
    sc = build_scene()
    for st in sc.stations:
        if st.name.startswith('VR'):
            assert abs(st.s_arc) == pytest.approx(st.x)
            assert st.y == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Check 2 -- station geometry
# --------------------------------------------------------------------------

def test_sr6_geometry():
    sc = build_scene(R=85.0)
    sr6 = sc.by_name('SR6')
    assert sr6.s_arc == pytest.approx(40.0)
    assert sr6.x == pytest.approx(-38.540, abs=1e-3)
    assert sr6.y == pytest.approx(9.239, abs=1e-3)
    assert math.degrees(sc.path.theta(sr6.s_arc)) == pytest.approx(26.96, abs=0.01)


def test_stations_ascend_in_arc_length():
    sc = build_scene()
    s = [st.s_arc for st in sc.stations]
    assert s == sorted(s)


# --------------------------------------------------------------------------
# Check 3 -- THE REGRESSION LOCK on the renumbering
# --------------------------------------------------------------------------

def test_one_sided_vessel_pair_sits_where_the_old_code_put_it():
    """The ruling renamed the vessel rollers; it must not have moved any.

    The old implementation's releasable vessel pair sat at x = +8 and +16
    under different names. If the renumbering had been applied to the labels
    without the positions following, these flags would land on the rollers
    beside the fixed station instead -- inverting the contact behaviour of
    two rollers in a model that still converges and still looks plausible.
    """
    sc = build_scene()
    xs = sorted(st.x for st in sc.stations
                if st.name.startswith('VR') and st.one_sided)
    assert xs == [8.0, 16.0]


def test_vessel_one_sided_split():
    sc = build_scene()
    assert sc.by_name('VR1').one_sided and sc.by_name('VR2').one_sided
    assert not sc.by_name('VR3').one_sided
    assert not sc.by_name('VR4').one_sided


def test_every_stinger_roller_is_one_sided():
    """A roller riding the arc can push the pipe along it but never hold it
    down against it."""
    sc = build_scene()
    for st in sc.contact:
        if st.name.startswith('SR'):
            assert st.one_sided, f'{st.name} should be one-sided'


# --------------------------------------------------------------------------
# Check 4 -- the rule scales
# --------------------------------------------------------------------------

@pytest.mark.parametrize('n_sr', [4, 6, 9])
def test_one_sided_rule_scales_with_n_sr(n_sr):
    sc = build_scene(n_sr=n_sr)
    sr_contact = [st for st in sc.contact if st.name.startswith('SR')]
    assert len(sr_contact) == n_sr
    assert all(st.one_sided for st in sr_contact)
    assert sc.load.name == f'SR{n_sr + 1}'


@pytest.mark.parametrize('n_vr', [3, 5, 8])
def test_vessel_count_scales(n_vr):
    sc = build_scene(n_vr=n_vr)
    vr = [st for st in sc.stations if st.name.startswith('VR')]
    assert len(vr) == n_vr
    assert sc.fixed.name == f'VR{n_vr}'
    assert len([st for st in vr if st.is_contact]) == n_vr - 1


# --------------------------------------------------------------------------
# Check 5 -- normal and tangent direction
# --------------------------------------------------------------------------

def test_normal_points_from_roller_toward_pipe():
    """At SR1 and everywhere on the deck the roller pushes straight up, and
    up is -y because +y is down."""
    sc = build_scene()
    assert sc.by_name('SR1').normal == pytest.approx((0.0, -1.0), abs=1e-12)
    for st in sc.stations:
        if st.name.startswith('VR'):
            assert st.normal == pytest.approx((0.0, -1.0), abs=1e-12)


def test_tangent_points_toward_the_stinger_tip():
    """Tracker item 28: the normal formula is correct ONLY because the
    tangent is taken toward the tip. Reverse it and the normal silently
    inverts, so the direction is asserted rather than assumed."""
    p = LayPath(R=85.0)
    for s in (-20.0, 0.0, 8.0, 40.0):
        tx, _ = p.tangent(s)
        assert tx < 0, f'tangent at s={s} must point toward -x (the tip)'


def test_normal_is_the_tangent_rotated_and_perpendicular():
    p = LayPath(R=85.0)
    for s in (-10.0, 0.0, 5.0, 25.0, 48.0):
        t, n = p.tangent(s), p.normal(s)
        assert t[0] * n[0] + t[1] * n[1] == pytest.approx(0.0, abs=1e-12)
        assert math.hypot(*n) == pytest.approx(1.0, abs=1e-12)
        assert math.hypot(*t) == pytest.approx(1.0, abs=1e-12)


def test_normal_matches_the_old_implementations_formula():
    """The old code states n = (-sin theta, -cos theta). Same vector."""
    p = LayPath(R=85.0)
    for s in (0.0, 8.0, 24.0, 40.0):
        th = p.theta(s)
        assert p.normal(s) == pytest.approx((-math.sin(th), -math.cos(th)), abs=1e-12)


def test_frame_is_right_handed_with_z_into_the_page():
    """x_hat cross y_hat = z_hat, right -> down -> into the page.

    The 2D cross product of (1,0) and (0,1) is +1, meaning +z is into the
    page under this frame's own declaration. Positive rotation about it
    therefore appears CLOCKWISE, which is the one thing a reader's intuition
    gets wrong.
    """
    x_hat, y_hat = (1.0, 0.0), (0.0, 1.0)
    cross_z = x_hat[0] * y_hat[1] - x_hat[1] * y_hat[0]
    assert cross_z == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Check 6 -- vessel and stinger do not overlap
# --------------------------------------------------------------------------

def test_vessel_and_stinger_occupy_opposite_sides():
    """The defect present in the stale prototype, which put both families at
    negative x and landed VR1 and SR2 on each other at x = -8."""
    sc = build_scene()
    vr_x = [st.x for st in sc.stations if st.name.startswith('VR')]
    sr_x = [st.x for st in sc.stations if st.name.startswith('SR')]
    assert all(x > 0 for x in vr_x), 'vessel rollers sit at +x'
    assert all(x <= 1e-12 for x in sr_x), 'stinger stations sit at -x (SR1 at 0)'
    assert min(vr_x) > max(sr_x)


def test_stinger_appears_left_and_vessel_right_without_an_axis_flip():
    """Plot x rightward and the starboard view is correct by construction."""
    sc = build_scene()
    assert sc.by_name('SR6').x < sc.by_name('SR1').x < sc.by_name('VR1').x


# --------------------------------------------------------------------------
# Checks 7-10 -- roles, the deck line, spacing, counts
# --------------------------------------------------------------------------

def test_fixed_station_is_not_a_contact_slot():
    sc = build_scene()
    assert sc.fixed.name == 'VR5'
    assert sc.fixed.role is StationRole.FIXED
    assert not sc.fixed.is_contact
    assert not sc.fixed.one_sided


def test_load_station_is_not_a_contact_slot():
    """SR7 carries tension only -- no roller acts there."""
    sc = build_scene()
    assert sc.load.name == 'SR7'
    assert sc.load.role is StationRole.LOAD
    assert not sc.load.is_contact
    assert not sc.load.one_sided


def test_sr1_is_on_the_deck_line_and_sr2_is_on_the_curve():
    """The correction to the first sketch: only SR1 is on the tangent line.

    SR2 has already dropped 0.376 m at R=85 -- a 2.7% grade, shallow enough
    to look flat and steep enough to matter.
    """
    sc = build_scene(R=85.0)
    assert sc.by_name('SR1').y == pytest.approx(0.0, abs=1e-12)
    assert sc.by_name('SR2').y == pytest.approx(0.376, abs=1e-3)
    assert sc.by_name('SR2').y > 0


def test_vr1_is_one_spacing_inboard_of_sr1():
    sc = build_scene()
    assert sc.by_name('VR1').x == pytest.approx(config.ROLLER_SPACING)
    inboard = sorted((st.x for st in sc.stations if st.x > 0))
    assert inboard[0] == pytest.approx(sc.by_name('VR1').x), 'nothing between'


def test_station_counts():
    sc = build_scene()
    assert len(sc.stations) == config.N_VR + config.N_SR + 1 == 12
    assert len(sc.contact) == (config.N_VR - 1) + config.N_SR == 10


# --------------------------------------------------------------------------
# Roller radius
# --------------------------------------------------------------------------

def test_default_radius_applies_to_every_roller():
    sc = build_scene()
    assert all(st.radius == 0.30 for st in sc.stations)


def test_radius_overrides_by_name():
    sc = build_scene(radii={'SR3': 0.35, 'VR2': 0.25})
    assert sc.by_name('SR3').radius == 0.35
    assert sc.by_name('VR2').radius == 0.25
    assert sc.by_name('SR4').radius == 0.30


# --------------------------------------------------------------------------
# Elastic end zones
# --------------------------------------------------------------------------

def test_elastic_zones_at_both_ends():
    sc = build_scene()
    lo, hi = sc.extent
    (a_lo, a_hi), (b_lo, b_hi) = sc.elastic_zones
    assert (a_lo, a_hi) == pytest.approx((lo, lo + 16.0))
    assert (b_lo, b_hi) == pytest.approx((hi - 16.0, hi))


def test_elastic_zone_membership():
    sc = build_scene()
    lo, hi = sc.extent
    assert sc.in_elastic_zone(lo)
    assert sc.in_elastic_zone(hi)
    assert sc.in_elastic_zone(lo + 1.0)
    assert not sc.in_elastic_zone(0.0), 'SR1 is mid-model, not in a zone'


def test_elastic_zones_that_would_overlap_are_refused():
    """Two 16 m zones cannot fit in a model shorter than 32 m -- they would
    leave no region where plasticity is permitted at all."""
    with pytest.raises(ValueError, match='overlap'):
        build_scene(n_sr=1, n_vr=2)


def test_zone_boundaries_are_the_interior_edges():
    sc = build_scene()
    assert sc.elastic_zone_boundaries == pytest.approx((-24.0, 32.0))


# --------------------------------------------------------------------------
# Refusals and workflow audit
# --------------------------------------------------------------------------

def test_negative_radius_refused():
    with pytest.raises(ValueError, match='positive'):
        LayPath(R=-85.0)


def test_too_few_vessel_stations_refused():
    with pytest.raises(ValueError, match='n_vr must be at least 2'):
        roller_stations(LayPath(R=85.0), n_vr=1)


def test_unknown_station_name_names_the_known_ones():
    sc = build_scene()
    with pytest.raises(KeyError, match='VR1'):
        sc.by_name('VR99')


def test_scene_takes_no_sweep_position():
    """G11 -- the scene layer describes ONE arrangement.

    Checked on SIGNATURES rather than source text: prose in a docstring
    saying "no argument named shift" is not a shift argument, and a test
    that cannot tell the difference fails on its own documentation.
    """
    import inspect
    from slay.scene import path, rollers, scene

    banned = {'shift', 'step', 'position_index'}
    for mod in (path, rollers, scene):
        for name, obj in vars(mod).items():
            if name.startswith('_') or getattr(obj, '__module__', None) != mod.__name__:
                continue
            if not (inspect.isfunction(obj) or inspect.isclass(obj)):
                continue
            try:
                params = set(inspect.signature(obj).parameters)
            except (TypeError, ValueError):
                continue
            assert not (params & banned), (
                f'{mod.__name__}.{name} takes {sorted(params & banned)} -- '
                f'sweep position has reached an inner layer')

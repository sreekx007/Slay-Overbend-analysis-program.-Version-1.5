"""L7 -- the passage sweep driver, and the buffer it needs.

WHAT THIS PINS. The sweep length is DERIVED from the component and its
intended start and finish, not chosen; the swept length is added at the
VESSEL end and nowhere else; and a sweep the model cannot feed is refused
rather than run.

The heavy end-to-end passage lives in `tools/`; these are the rules.
"""

import pytest

pytest.importorskip('numpy')

from slay.scene.rollers import StationRole              # noqa: E402
from slay.scene.scene import build_scene                # noqa: E402
from slay.study import sweep                            # noqa: E402


@pytest.fixture(scope='module')
def plain():
    return build_scene(R=85.0, spacing=8.0, elastic_length=16.0)


# -- the length is derived -------------------------------------------------

def test_sweep_length_is_the_component_plus_both_clearances():
    """`L + before + after`. It GROWS with the component, which is the
    point: a 20D body needs a longer passage than a 2.5D one to make the
    same traverse past the same roller."""
    assert sweep.sweep_length(1.0) == pytest.approx(3.0)
    assert sweep.sweep_length(8.128) == pytest.approx(10.128)
    assert sweep.sweep_length(1.0, 0.5, 2.0) == pytest.approx(3.5)
    assert (sweep.sweep_length(4.0) - sweep.sweep_length(1.0)
            == pytest.approx(3.0)), 'travel tracks length one for one'
    for bad in (dict(L_comp=-1.0), dict(L_comp=1.0, clear_before=-0.1),
                dict(L_comp=1.0, clear_after=-0.1)):
        with pytest.raises(ValueError):
            sweep.sweep_length(**bad)


def test_the_passage_starts_and_finishes_where_it_says(plain):
    """The whole derivation, checked on the geometry rather than restated.

    At shift 0 the LEADING edge is `clear_before` short of SR2; at the end
    of the sweep the TRAILING edge is `clear_after` past it.
    """
    L, sr2 = 1.0, plain.by_name('SR2').s_arc
    c = sweep.start_centre(plain, L)
    lead, trail = c + L / 2.0, c - L / 2.0
    assert sr2 - lead == pytest.approx(sweep.CLEAR_BEFORE)
    total = sweep.sweep_length(L)
    assert (trail + total) - sr2 == pytest.approx(sweep.CLEAR_AFTER)


def test_schedule_always_includes_the_total():
    """The final position is the one the sweep was SIZED for, so it is
    never dropped for failing to land on a step boundary."""
    assert sweep.schedule(3.0, 1.0) == (0.0, 1.0, 2.0, 3.0)
    ragged = sweep.schedule(3.0, 0.8)
    assert ragged[0] == 0.0 and ragged[-1] == pytest.approx(3.0)
    assert len(ragged) == 5
    with pytest.raises(ValueError):
        sweep.schedule(3.0, 0.0)


# -- the buffer ------------------------------------------------------------

def test_the_swept_length_is_added_at_the_vessel_end_only(plain):
    """Material LEAVES the model at the stinger end and needs nothing
    there; it is the vessel end that runs dry."""
    L = 4.0
    buffered = sweep.scene_for(R=85.0, spacing=8.0, L_comp=L,
                               elastic_length=16.0)
    total = sweep.sweep_length(L)
    assert plain.extent[0] - buffered.extent[0] == pytest.approx(total)
    assert buffered.extent[1] == pytest.approx(plain.extent[1])
    assert [s.s_arc for s in buffered.stations] == \
        [s.s_arc for s in plain.stations], 'stations do not move'


def test_a_sweep_the_model_cannot_feed_is_refused(plain):
    """At travel `sigma` the innermost contact station reads material from
    `s_arc - sigma`. Past the vessel end there is no pipe to read, and the
    run would report a number for a station bearing on nothing.

    The unbuffered scene tolerates a short sweep -- the innermost CONTACT
    station is one spacing inboard of the model end -- so the test brackets
    the real limit rather than assuming every sweep needs a buffer.
    """
    inner = min(s.s_arc for s in plain.stations
                if s.role is StationRole.CONTACT)
    headroom = inner - plain.extent[0]
    assert headroom == pytest.approx(8.0)

    sweep.check_reach(plain, headroom - 0.1)
    with pytest.raises(ValueError, match='off the vessel end'):
        sweep.check_reach(plain, headroom + 0.1)

    # The refusal must advise the SHORTFALL, not the whole sweep. It once
    # said 18.128 m where 2.128 m suffices -- advice that over-sizes by the
    # headroom it forgot to count.
    big = sweep.sweep_length(8.128)
    short = big - headroom
    with pytest.raises(ValueError, match=rf'margin_vessel >= {short:.3f} m'):
        sweep.check_reach(plain, big)
    sweep.check_reach(
        build_scene(R=85.0, spacing=8.0, margin_vessel=short,
                    elastic_length=16.0), big)
    with pytest.raises(ValueError):
        sweep.check_reach(
            build_scene(R=85.0, spacing=8.0, margin_vessel=short - 0.1,
                        elastic_length=16.0), big)

    big = sweep.sweep_length(8.128)
    assert big > headroom
    sweep.check_reach(sweep.scene_for(R=85.0, spacing=8.0, L_comp=8.128,
                                      elastic_length=16.0), big)


def test_the_anchor_keeps_a_node_once_the_end_moves(plain):
    """WHY `_required_stations` EXISTS. `boundary_conditions` refuses a
    restraint with no node within 1e-6 m. At `margin_vessel = 0` the
    model's vessel end coincided with the FIXED station, so the anchor had
    a node by COINCIDENCE. Push the end back and the mesh grid no longer
    lands on it."""
    fixed = [s for s in plain.stations if s.role is StationRole.FIXED]
    assert len(fixed) == 1
    assert sweep._required_stations(plain) == (fixed[0].s_arc,)
    assert plain.extent[0] == pytest.approx(fixed[0].s_arc), \
        'unbuffered, the anchor IS the model end -- the coincidence'
    buffered = sweep.scene_for(R=85.0, spacing=8.0, L_comp=1.0,
                               elastic_length=16.0)
    assert buffered.extent[0] < fixed[0].s_arc, 'buffered, it is not'


def test_mode_must_be_a_or_b(plain):
    with pytest.raises(ValueError, match="mode must be"):
        sweep.run(plain, None, L_comp=1.0, mode='C')

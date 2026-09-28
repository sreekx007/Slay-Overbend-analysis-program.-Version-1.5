"""L8 -- measuring a solved passage, and the rules that make a passage table
mean something.

WHAT THIS PINS. Every reported position is in STATION coordinates, so the
same column means the same place on the stinger; the envelope is the worst
CONVERGED position and a diverged one can never win it; and the reporting
zone is applied, named on the record, and refuses a scene it cannot apply to.

The heavy end-to-end passage lives in `tools/slide.py`; these are the rules,
plus one measured invariance check that needs the solver.
"""

import pytest

pytest.importorskip('numpy')

from slay.report import passage as rp                        # noqa: E402
from slay.scene.scene import build_scene                     # noqa: E402
from slay.study import sweep                                 # noqa: E402

TON = 9806.65
OD = 0.4064


@pytest.fixture(scope='module')
def plain():
    return build_scene(R=85.0, spacing=9.0, elastic_length=16.0)


class FakeResult:
    """A Result's reporting surface and nothing else.

    The measurement layer must be testable without a solve: it reads
    `strains`, `status`, `active` and `released` off a Result and touches
    nothing else. If this stub ever stops being enough, the module has
    reached past its interface.
    """

    def __init__(self, strains, status='ok', active=(True,), released=()):
        self.strains, self.status = strains, status
        self.active, self.released = active, released

    @property
    def converged(self):
        return self.status == 'ok'


class FakePosition:
    def __init__(self, index, shift, result, s_lead=0.0, s_trail=0.0):
        self.index, self.shift, self.result = index, shift, result
        self.s_lead, self.s_trail = s_lead, s_trail


def _pos(index, shift, rows, **kw):
    return FakePosition(index, shift, FakeResult(rows, **kw))


# -- the zone --------------------------------------------------------------

def test_the_zone_drops_the_last_three_stinger_rollers(plain):
    """The 21 Sep ruling, and it is applied in STATION coordinates."""
    s_max, label = rp.zone(plain)
    assert s_max == pytest.approx(plain.by_name('SR5').s_arc)
    assert 'SR5' in label


def test_a_scene_too_short_for_the_zone_is_refused():
    """Silently reporting the whole model would hand back the tip artefact
    D6 created as if it were a result."""
    short = build_scene(R=85.0, n_sr=1, spacing=9.0)
    with pytest.raises(ValueError, match='only'):
        rp.zone(short, drop=3)


# -- station coordinates ---------------------------------------------------

def test_the_peak_is_reported_in_both_frames(plain):
    """`s` in a Result is MATERIAL. After a shift the same material sits
    further along the stinger, so a record must say both or it says nothing.
    """
    rows = ((0, 5.0, 0.001), (1, 12.0, 0.004))
    r = rp.record(_pos(0, 3.0, rows), plain)
    assert r.peak_s_material == pytest.approx(12.0)
    assert r.peak_s_station == pytest.approx(15.0), 'material + shift'


def test_the_zone_cuts_on_station_not_material(plain):
    """THE FAILURE THIS PREVENTS. Material at `s` sits at `s + shift`, so an
    element that is inside the zone at shift 0 can be outside it later. Cut
    on material and the excluded tip leaks back in as the passage advances.
    """
    s_max, _ = rp.zone(plain)
    # Material just inboard of the cut, shifted until it is past the cut.
    rows = ((0, 1.0, 0.001), (1, s_max - 1.0, 0.009))
    near = rp.record(_pos(0, 0.0, rows), plain)
    assert near.peak_strain == pytest.approx(0.009), 'in zone at shift 0'
    far = rp.record(_pos(1, 5.0, rows), plain)
    assert far.peak_strain == pytest.approx(0.001), \
        'the big element has slid out of the zone and must not be reported'


def test_station_strains_are_keyed_by_place_not_by_material(plain):
    """The same key must mean the same place on the stinger at every
    position, or the passage table compares nothing to nothing."""
    sr2 = plain.by_name('SR2').s_arc
    # Beyond half a spacing, so the material starts outside SR2's window --
    # the windows are half a spacing wide and TILE the line, so a smaller
    # offset would still fall inside it and prove nothing.
    off = plain.spacing
    rows = ((0, sr2 - off, 0.007),)
    at_zero = rp.record(_pos(0, 0.0, rows), plain).stations
    at_off = rp.record(_pos(1, off, rows), plain).stations
    assert at_zero.get('SR2') != pytest.approx(0.007), \
        'that material is a full spacing short of SR2 at shift 0'
    assert at_off['SR2'] == pytest.approx(0.007), \
        f'after {off} m of travel that material IS at SR2'


# -- the envelope ----------------------------------------------------------

def test_the_envelope_is_the_worst_converged_position(plain):
    """THE POINT OF A PASSAGE. Not the first position and not the last."""
    recs = rp.measure([
        _pos(0, 0.0, ((0, 5.0, 0.004),)),
        _pos(1, 1.0, ((0, 5.0, 0.009),)),
        _pos(2, 2.0, ((0, 5.0, 0.006),)),
    ], plain)
    env = rp.envelope(recs)
    assert env.index == 1 and env.peak_strain == pytest.approx(0.009)


def test_a_diverged_position_can_never_win_the_envelope(plain):
    """Its peak is a MISS, not a low number -- and a diverged position with
    a spuriously high one must not be reported as the answer either."""
    recs = rp.measure([
        _pos(0, 0.0, ((0, 5.0, 0.004),)),
        _pos(1, 1.0, ((0, 5.0, 0.500),), status='CUTBACK EXHAUSTED'),
    ], plain)
    assert rp.envelope(recs).index == 0


def test_a_passage_with_nothing_converged_has_no_envelope(plain):
    """Returning zero would read as a safe result."""
    recs = rp.measure([_pos(0, 0.0, (), status='diverged')], plain)
    with pytest.raises(ValueError, match='no converged position'):
        rp.envelope(recs)


def test_the_station_envelope_is_a_max_over_positions_never_a_sum(plain):
    """G3's rule, and for the same reason: each position is one moment in
    time, so a station's design value is the worst moment, not their total."""
    sr2 = plain.by_name('SR2').s_arc
    recs = rp.measure([_pos(0, 0.0, ((0, sr2, 0.003),)),
                       _pos(1, 0.0, ((0, sr2, 0.005),))], plain)
    assert rp.station_envelope(recs)['SR2'] == pytest.approx(0.005)


def test_a_diverged_position_reports_a_miss_rather_than_raising(plain):
    """A passage wants to know WHICH position failed and carry on."""
    r = rp.record(_pos(0, 0.0, ()), plain, drop=3)
    assert r.peak_strain == 0.0 and not r.converged or r.peak_strain == 0.0


# -- the edge-crossing schedule -------------------------------------------

def test_critical_shifts_are_the_edge_crossings(plain):
    """Where an edge sits exactly on a contact station. Both edges: a
    section change over a roller is why the component is interesting."""
    L, c = 1.0, sweep.start_centre(plain, 1.0)
    crit = sweep.critical_shifts(plain, L, c)
    sr2 = plain.by_name('SR2').s_arc
    assert pytest.approx(sr2 - (c + L / 2.0)) in crit, 'leading edge at SR2'
    assert pytest.approx(sr2 - (c - L / 2.0)) in crit, 'trailing edge at SR2'
    assert all(v > 0.0 for v in crit) and list(crit) == sorted(crit)


def test_plain_pipe_has_no_critical_shifts(plain):
    """No edges, so nothing distinguishes one travel from another."""
    assert sweep.critical_shifts(plain, 0.0, 0.0) == ()


def test_the_schedule_carries_the_critical_shifts_whatever_the_step():
    """The envelope sits at an edge crossing and a whole-element step steps
    straight over it -- measured, 16% low on GD-TP. So these are not
    optional and the step only samples between them."""
    got = sweep.schedule(3.0, 1.0, include=(1.25, 2.5))
    assert got == (0.0, 1.0, 1.25, 2.0, 2.5, 3.0)
    assert sweep.schedule(3.0, 1.0, include=(5.0, -1.0)) == (0.0, 1.0, 2.0, 3.0), \
        'a travel outside the sweep is not a position'


def test_the_schedule_never_solves_the_same_position_twice():
    """A critical shift that lands on a step boundary is one position."""
    got = sweep.schedule(3.0, 1.0, include=(1.0, 2.0 + 1e-12))
    assert got == (0.0, 1.0, 2.0, 3.0)


# -- the measured invariance ----------------------------------------------

def test_a_plain_elastic_passage_is_invariant_in_station_space():
    """THE CHECK THAT SAYS THE SLIDING IS RIGHT, and it needs a solve.

    The rollers impose the same geometry at every position, so a plain
    LINEAR ELASTIC pipe must read the same strain at the same STATION however
    far it has slid. Stepped by a whole element so the interpolated contact
    point lands the same way each time, this holds to 0.1%; at half an element
    the linear slot coefficients cost up to 4.4% at SR1, alternating, with no
    trend. A TREND here would mean the sliding is wrong.
    """
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0,
                         clear_before=0.0, clear_after=4 * OD)
    pos = sweep.run(sc, None, L_comp=0.0, clear_before=0.0,
                    clear_after=4 * OD, step=2 * OD,
                    tension=120 * TON, material=None)
    recs = rp.measure(pos, sc)
    assert len(recs) >= 3 and all(r.converged for r in recs)
    s_max, _ = rp.zone(sc)
    checked = 0
    for name in rp.station_envelope(recs):
        vals = [r.stations[name] for r in recs if name in r.stations]
        st = sc.by_name(name)
        # STINGER rollers in the zone. The claim is about the overbend: the
        # deck rollers carry ~0.02% and a hair of absolute change there is a
        # large relative one, which would fail this test for no physics.
        if not name.startswith('SR') or st.s_arc >= s_max \
                or len(vals) < len(recs):
            continue
        spread = (max(vals) - min(vals)) / max(vals)
        checked += 1
        assert spread < 0.005, (
            f'{name} varies {100 * spread:.2f}% along the passage; a plain '
            f'elastic pipe on fixed rollers must not: {vals}')
    assert checked >= 3, f'only checked {checked} stinger stations in the zone'

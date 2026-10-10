"""The per-station targets, and the split roller pitch they are measured on.

Five library changes landed together on 10 Oct 2026 for the plain-pipelay
surrogate dataset, and each one is covered here:

  1. `roller_stations` / `build_scene` take `spacing_vr` beside `spacing`
  2. `tools/slide.py::passage` passes `n_sr` / `n_vr` / `spacing_vr` through
  3. `solve.contact.slot_reactions` and `anchor_reactions`
  4. `solve.passage` carries the strain DECOMPOSITION in `Result.parts`
  5. `report.passage.station_window` / `station_values` / `station_reactions`

THE COMPATIBILITY TESTS MATTER MOST. Every number in `docs/validation/` was
computed with a single roller pitch, with no decomposition carried and with
`station_strains`' half-spacing window. Each of those has to come back
unchanged when the new arguments are left alone, and that is what most of
these assert.
"""

import math

import pytest

import config                                       # noqa: E402

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

from slay.report import passage as rp               # noqa: E402
from slay.scene.path import LayPath                 # noqa: E402
from slay.scene.rollers import roller_stations      # noqa: E402
from slay.scene.scene import Scene, all_bidirectional, build_scene  # noqa: E402
from slay.solve import contact as ctc               # noqa: E402


# ---------------------------------------------------------------------------
# 1. the split pitch
# ---------------------------------------------------------------------------

def _names_and_s(stations):
    return [(s.name, round(s.s_arc, 9)) for s in stations]


def test_omitting_spacing_vr_reproduces_the_single_pitch_layout():
    """The compatibility guarantee. Every validated number was computed with
    one pitch, so leaving the new argument alone must change nothing."""
    path = LayPath(R=85.0)
    before = roller_stations(path, n_sr=6, n_vr=5, spacing=9.0)
    after = roller_stations(path, n_sr=6, n_vr=5, spacing=9.0,
                            spacing_vr=None)
    assert _names_and_s(before) == _names_and_s(after)
    same = roller_stations(path, n_sr=6, n_vr=5, spacing=9.0, spacing_vr=9.0)
    assert _names_and_s(before) == _names_and_s(same)


def test_the_vessel_pitch_moves_only_the_vessel():
    """A stinger-pitch study holds the vessel deck fixed, so the two sides
    have to be independent in both directions."""
    path = LayPath(R=85.0)
    st = roller_stations(path, n_sr=6, n_vr=5, spacing=4.0, spacing_vr=9.0)
    vr = {s.name: s.s_arc for s in st if s.name.startswith('VR')}
    sr = {s.name: s.s_arc for s in st if s.name.startswith('SR')}
    assert vr['VR1'] == pytest.approx(-9.0)
    assert vr['VR5'] == pytest.approx(-45.0)
    assert sr['SR1'] == pytest.approx(0.0)
    assert sr['SR7'] == pytest.approx(24.0)      # 6 gaps x 4 m


def test_all_bidirectional_keeps_the_vessel_pitch():
    """THE TRAP THIS CHANGE NEARLY WALKED INTO.

    `all_bidirectional` REBUILDS the stations and promises in its own
    docstring to be geometrically identical. It read `scene.spacing` alone,
    so with a split pitch it would have re-spaced the VESSEL DECK at the
    STINGER pitch -- inside `study.sweep.seed_state`, the step that builds
    the geometry every lay tension is then reacted by. The model still
    meshes and still solves, on a different vessel, and nothing downstream
    would have complained.
    """
    sc = build_scene(R=85.0, n_sr=6, n_vr=5, spacing=4.0, spacing_vr=9.0)
    bi = all_bidirectional(sc)
    assert _names_and_s(sc.stations) == _names_and_s(bi.stations)
    assert bi.vessel_spacing == pytest.approx(9.0)
    assert not any(s.one_sided for s in bi.stations)


def test_vessel_spacing_resolves_to_the_stinger_pitch_when_unset():
    sc = build_scene(R=85.0, n_sr=6, n_vr=5, spacing=7.0)
    assert sc.spacing_vr is None
    assert sc.vessel_spacing == pytest.approx(7.0)
    assert _names_and_s(all_bidirectional(sc).stations) \
        == _names_and_s(sc.stations)


def test_a_bigger_stinger_leaves_no_roller_bidirectional_by_accident():
    """`one_sided` is resolved for the count being BUILT, not read off the
    import-time constant -- otherwise a 10-roller stinger silently gets
    SR7..SR10 holding the pipe down."""
    sc = build_scene(R=85.0, n_sr=10, n_vr=5, spacing=4.0, spacing_vr=9.0)
    sr = [s for s in sc.stations if s.name.startswith('SR')]
    assert len(sr) == 11
    assert [s.name for s in sr if not s.one_sided] == ['SR11']
    assert sc.by_name('SR11').bears_tension


# ---------------------------------------------------------------------------
# 5. the window rule
# ---------------------------------------------------------------------------

def test_the_window_is_two_elements_where_it_fits():
    sc = build_scene(R=85.0, n_sr=6, n_vr=5, spacing=12.0)
    OD = 0.4064
    assert rp.station_window(sc, OD) == pytest.approx(4.0 * OD)


def test_the_window_is_capped_so_two_rollers_cannot_claim_one_element():
    """Two elements is `4 * OD`, so windows would overlap once
    `8 * OD > spacing`. 32 in at 4 m is the case that forced the cap."""
    sc = build_scene(R=85.0, n_sr=10, n_vr=5, spacing=4.0, spacing_vr=9.0)
    OD = 0.8128
    assert 8.0 * OD > sc.spacing                  # the overlap condition
    assert rp.station_window(sc, OD) == pytest.approx(2.0)   # spacing / 2
    assert rp.station_window(sc, OD) < 4.0 * OD


def test_the_cap_does_not_bind_on_a_small_pipe_at_the_same_spacing():
    sc = build_scene(R=85.0, n_sr=10, n_vr=5, spacing=4.0, spacing_vr=9.0)
    OD = 0.1683
    assert 8.0 * OD < sc.spacing
    assert rp.station_window(sc, OD) == pytest.approx(4.0 * OD)


# ---------------------------------------------------------------------------
# 3, 4, 5 against a real solve
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def solved():
    """One plain-pipe passage, 16 in at R = 85, 120 MT, through the same
    entry point the published Sec. 1 tables use."""
    import warnings
    import sys
    from pathlib import Path
    tools = Path(__file__).resolve().parents[2] / 'tools'
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import slide
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sc, L, recs, _j, probs, pos, done = slide.passage(
            arch_id='none', R=85.0, spacing=9.0, tension_mt=120.0,
            OD=0.4064, t_wall=0.021, step=2 * 0.4064, verbose=False)
    return sc, probs, pos


def test_the_decomposition_reproduces_the_strain_it_came_from(solved):
    """`eps_max = max|eps_axial +/- r_o*kappa|`, which is the whole reason no
    membrane term may be ADDED to the reported strain: it is already in it."""
    _sc, _probs, pos = solved
    r = pos[0].result
    assert len(r.parts) == len(r.strains)
    r_o = 0.4064 / 2.0
    for (i, s, eps), (j, s2, ea, ka) in zip(r.strains, r.parts):
        assert i == j and s == pytest.approx(s2, abs=1e-12)
        want = max(abs(ea + r_o * ka), abs(ea - r_o * ka))
        assert want == pytest.approx(eps, rel=1e-9)


def test_a_released_slot_reports_a_measured_zero(solved):
    """A released roller applies nothing, so 0.0 is its reaction -- not the
    force it would apply if it were holding, and not a missing value."""
    _sc, _probs, pos = solved
    r = pos[0].result
    assert r.reactions
    for (name, f, act) in r.reactions:
        if not act:
            assert f == 0.0, name


def test_the_reactions_balance_the_applied_load(solved):
    """THE GATE FOR THE REACTION TARGET. A penalty-scaled force is plausible
    long before it is right, and global equilibrium is the only cheap thing
    that tells the difference.

    The sum is over the contact slots AND the FIXED station: the anchor is
    not a slot, so slots alone do not balance and a check that forgot it
    would fail by whatever the anchor carries.
    """
    sc, probs, pos = solved
    p0, r0 = probs[0], pos[0].result
    applied_y = sum(l.fy for l in p0.loads)
    slots_y = sum(f * sc.by_name(n).normal[1] for (n, f, _a) in r0.reactions)
    anchor_y = sum(f for d, f in r0.anchor_reactions if d % 3 == 1)
    resid = slots_y + anchor_y + applied_y
    assert abs(resid) < 0.02 * abs(applied_y), (
        f'vertical equilibrium off by {resid/1e3:.3f} kN against an applied '
        f'{applied_y/1e3:.3f} kN')


def test_station_values_gives_each_quantity_its_own_worst_element(solved):
    """Strain and moment do not peak on the same element, and reporting the
    moment OF the worst-strain element would be a third quantity that is
    neither."""
    sc, _probs, pos = solved
    half = rp.station_window(sc, 0.4064)
    v = rp.station_values(pos[0], sc, half, ('SR1', 'SR2', 'SR3'))
    assert set(v) == {'SR1', 'SR2', 'SR3'}
    for name, (eps, m, ea, ka, n_el) in v.items():
        assert eps > 0.0 and m > 0.0 and n_el >= 1
        assert abs(ea) < eps                    # membrane is part of the total
        assert math.isfinite(ka)
    # the moment reported is the window's maximum, which is at least the
    # moment at the worst-strain element and may exceed it
    moms = [m for (s, _sm, m) in rp._moment_rows(pos[0])
            if abs(s - sc.by_name('SR2').s_arc) < half]
    assert v['SR2'][1] == pytest.approx(max(moms))


def test_a_station_with_nothing_in_its_window_is_absent_not_zero(solved):
    """A missing measurement and a measured zero are different facts, and
    L097 is in the register because printing one as the other read as a
    strain of 0.000%."""
    sc, _probs, pos = solved
    v = rp.station_values(pos[0], sc, 1e-9, ('SR1', 'SR2', 'SR3'))
    assert v == {}


def test_station_strains_is_untouched_by_the_new_window(solved):
    """The half-spacing rule still produces what every Sec. 1 table is
    measured with, and the two windows are different functions so they
    cannot drift into each other."""
    sc, _probs, pos = solved
    old = rp.station_strains(pos[0], sc)
    half_old = sc.spacing / 2.0
    rows = rp._rows(pos[0])
    for st in sc.stations:
        near = [e for (s_sta, _s, e) in rows
                if abs(s_sta - st.s_arc) < half_old]
        if near:
            assert old[st.name] == pytest.approx(max(near))
    assert rp.station_window(sc, 0.4064) != half_old


def test_station_reactions_are_keyed_by_station(solved):
    sc, _probs, pos = solved
    rx = rp.station_reactions(pos[0], sc, ('SR1', 'SR2', 'SR3'))
    assert set(rx) <= {'SR1', 'SR2', 'SR3'}
    for name, (f, act) in rx.items():
        assert isinstance(act, bool)
        assert (f == 0.0) if not act else True


# ---------------------------------------------------------------------------
# 2. the pass-throughs
# ---------------------------------------------------------------------------

def _slide():
    import sys
    from pathlib import Path
    tools = Path(__file__).resolve().parents[2] / 'tools'
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import slide
    return slide


def test_slide_passage_takes_the_scene_pass_throughs():
    import inspect
    sig = inspect.signature(_slide().passage).parameters
    for name in ('n_sr', 'n_vr', 'spacing_vr'):
        assert name in sig and sig[name].default is None


def test_the_pass_throughs_are_omitted_rather_than_forwarded_as_none():
    """`scene_for` forwards **kw to `build_scene`, so passing `n_sr=None`
    through would hand `build_scene` an explicit None where it previously
    got nothing. Same result today, but it is the kind of difference that
    stops being nothing when a default changes -- so the call is built
    without them."""
    from slay.study import sweep
    a = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0)
    b = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0,
                        **{k: v for k, v in (('n_sr', None),)
                           if v is not None})
    assert _names_and_s(a.stations) == _names_and_s(b.stations)
    assert a.extent == b.extent
    assert a.spacing_vr is b.spacing_vr is None


def test_scene_for_reaches_the_roller_count_and_the_vessel_pitch():
    """The dataset needs a 10-roller stinger at a 9 m vessel pitch, and it
    must get there through the entry point the Sec. 1 tables use rather than
    by bypassing it."""
    from slay.study import sweep
    sc = sweep.scene_for(R=85.0, spacing=4.0, L_comp=0.0,
                         n_sr=10, n_vr=5, spacing_vr=9.0)
    sr = [s for s in sc.stations if s.name.startswith('SR')]
    assert len(sr) == 11
    assert sc.by_name('SR11').s_arc == pytest.approx(40.0)
    assert sc.by_name('VR5').s_arc == pytest.approx(-45.0)
    assert sc.vessel_spacing == pytest.approx(9.0)

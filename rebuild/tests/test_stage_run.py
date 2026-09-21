"""The four-step staged analysis, and what it reproduces.

`tools/stage_run.py` is a TOOL, not a package module: it reaches across
layers freely (scene, physics, solve in one file), which `check_layers`
permits there and rejects inside `slay/`. Importing it from a test exercises
the rig, exactly as `test_mesher_rig.py` does.

WHAT THIS PINS. The staged sequence reproduces the reference program
`slay_overbend_v1_50.run_slay` to within 1.7% at every stinger radius, with
the peak in the same span -- against +15 to +21% for a single proportional
solve of the same case (spec section 5d). The reference is not run here (it
takes minutes and lives outside the package); its numbers are quoted from
the comparison recorded in section 5e, and OUR side of that comparison is
what these tests hold still.
"""

import pytest

pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import stage_run                                    # noqa: E402  (tools/)

# run_slay, 8 m spacing, 120 MT, J2, one_sided -- quoted, not recomputed.
REFERENCE_J2 = {70.0: 0.5271, 85.0: 0.3937, 105.0: 0.2903}


@pytest.fixture(scope='module')
def staged():
    """R = 85 at the REFERENCE's own 8 m spacing, so the comparison is like
    for like. `slay_config.yaml` ships 9 m, which is the paper's."""
    return stage_run.run(R=85.0, tension_mt=120.0, spacing=8.0, verbose=False)


def test_every_step_converges(staged):
    """The claim the sequence exists to make. A single proportional solve of
    this case diverged on the first Newton iteration at every radius."""
    _sc, out, _state = staged
    assert len(out) == 4
    for label, _p, r in out:
        assert r.converged, f'{label}: {r.status}'


def test_step_one_holds_every_roller(staged):
    """All bidirectional, by construction. A one-sided roller cannot pull,
    so with no tension yet the stinger rollers would release and the pipe
    would never reach the arc."""
    _sc, out, _state = staged
    _label, _p, first = out[0]
    assert all(first.active) and not first.released


def test_lift_off_activates_at_step_two(staged):
    """Step 2 hands the active set its real rule, and rollers do release --
    which is the difference between step 1's scene and every later one."""
    _sc, out, _state = staged
    assert sum(out[1][2].active) < sum(out[0][2].active)


def test_it_reproduces_the_reference_program(staged):
    """M1's actual question: does the rebuild behave like the old program?

    0.3884% against `run_slay`'s 0.3937% at R = 85, J2, 8 m -- 1.3% apart.
    The tolerance here is on OUR number; the reference's is a constant.
    """
    sc, out, _state = staged
    s_max, _zone = stage_run.report_zone(sc)
    s_pk, eps = stage_run.peak_in_zone(out[-1][2], s_max)
    assert 100 * eps == pytest.approx(0.38839, abs=5e-5)
    assert abs(100 * eps / REFERENCE_J2[85.0] - 1.0) < 0.02
    assert sc.by_name('SR2').s_arc == pytest.approx(8.0)
    assert 8.0 <= s_pk < 16.0, 'the peak is in the SR2-SR3 span, as it is ' \
                               'in the reference'


def test_the_excluded_zone_is_load_bearing(staged):
    """SAY IT OUT LOUD: the result DEPENDS on dropping the last three
    rollers. SR6 carries more strain than the reported peak, because D6's
    terminal contact slot over-constrains the tip (spec section 5d). A
    reader who takes the headline number without the zone gets a different
    answer, so the zone travels with the number everywhere it is printed.
    """
    sc, out, _state = staged
    s_max, _zone = stage_run.report_zone(sc)
    _s_pk, eps = stage_run.peak_in_zone(out[-1][2], s_max)
    profile = stage_run.station_profile(sc, out[-1][2])

    assert s_max == pytest.approx(sc.by_name('SR5').s_arc)
    assert profile['SR6'] > eps, 'the excluded tip is the higher number'
    whole_model = max(e for (_i, _s, e) in out[-1][2].strains)
    assert whole_model > eps

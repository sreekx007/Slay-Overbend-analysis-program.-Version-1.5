"""The four-step staged analysis, and what it reproduces.

THE SEQUENCE IS `slay.study.staged`, a workflow in the package and policed
by `check_layers` like any other. It moved there on 9 Oct 2026 from
`tools/stage_run.py`, where nothing but that script could call it and where
it carried three copies of library code to work -- `all_bidirectional`
(which `scene.scene` already had and `sweep` already imported), the
reporting window, and `DROP_AT_TIP`. The copies were not equivalent: the
library's `report.passage.zone` raises on a scene with too few stinger
rollers where the copy silently indexed `sr[-3]`.

What is still imported from `tools/stage_run.py` is what a tool is for --
`peak_in_zone` and `station_profile`, which present `result.strains` for a
reader rather than measuring anything.

EVERY NUMBER BELOW IS UNCHANGED BY THAT MOVE, and was checked bit-identical
at R = 70, 85 and 105 before the tests were repointed.

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
from slay.report.passage import zone                # noqa: E402
from slay.study.staged import run as staged_run     # noqa: E402

# run_slay, 8 m spacing, 120 MT, J2, one_sided -- quoted, not recomputed.
REFERENCE_J2 = {70.0: 0.5271, 85.0: 0.3937, 105.0: 0.2903}


@pytest.fixture(scope='module')
def staged():
    """R = 85 at the REFERENCE's own 8 m spacing, so the comparison is like
    for like. `slay_config.yaml` ships 9 m, which is the paper's."""
    return staged_run(R=85.0, tension_mt=120.0, spacing=8.0)


def test_every_step_converges(staged):
    """The claim the sequence exists to make. A single proportional solve of
    this case diverged on the first Newton iteration at every radius."""
    _sc, out, _state = staged
    assert len(out) == 4
    for st in out:
        assert st.converged, f'{st.label}: {st.result.status}'


def test_step_one_holds_every_roller(staged):
    """All bidirectional, by construction. A one-sided roller cannot pull,
    so with no tension yet the stinger rollers would release and the pipe
    would never reach the arc."""
    _sc, out, _state = staged
    first = out[0].result
    assert all(first.active) and not first.released


def test_lift_off_activates_at_step_two(staged):
    """Step 2 hands the active set its real rule, and rollers do release --
    which is the difference between step 1's scene and every later one."""
    _sc, out, _state = staged
    assert sum(out[1].result.active) < sum(out[0].result.active)


def test_it_reproduces_the_reference_program(staged):
    """M1's actual question: does the rebuild behave like the old program?

    0.3884% against `run_slay`'s 0.3937% at R = 85, J2, 8 m -- 1.3% apart.
    The tolerance here is on OUR number; the reference's is a constant.

    ON THE SURFACE THE REFERENCE RUNS. `run_slay` drives the pipe CENTRELINE
    onto the R arc, so the like-for-like comparison is made there explicitly
    rather than inheriting whatever this repo's default happens to be. The
    default moved to 'bottom' on 6 Oct 2026 and the number barely followed --
    0.38848 against 0.38839, 0.02% -- which is itself worth pinning, because
    the radius changes by 0.59% and a reader would reasonably expect more.
    The reason is that the peak MOVES with the slots: it sits at s = 8.06 m
    under 'centreline' and 8.22 m under 'bottom', so the two numbers are the
    peak of a field sampled in slightly different places, not the same
    quantity scaled.
    """
    sc, out, _state = staged
    s_max, _zone = zone(sc)
    s_pk, eps = stage_run.peak_in_zone(out[-1].result, s_max)
    assert 100 * eps == pytest.approx(0.38848, abs=5e-5)

    lsc, lout, _ls = staged_run(R=85.0, tension_mt=120.0, spacing=8.0,
                                contact_surface='centreline')
    _lpk, leps = stage_run.peak_in_zone(lout[-1].result, zone(lsc)[0])
    assert 100 * leps == pytest.approx(0.38839, abs=5e-5)
    assert abs(100 * leps / REFERENCE_J2[85.0] - 1.0) < 0.02
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
    s_max, _zone = zone(sc)
    _s_pk, eps = stage_run.peak_in_zone(out[-1].result, s_max)
    profile = stage_run.station_profile(sc, out[-1].result)

    assert s_max == pytest.approx(sc.by_name('SR5').s_arc)
    assert profile['SR6'] > eps, 'the excluded tip is the higher number'
    whole_model = max(e for (_i, _s, e) in out[-1].result.strains)
    assert whole_model > eps


def test_staged_and_single_solve_agree_at_the_same_metric(staged):
    """L062, pinned. These were once recorded as 15-21% apart, with staging
    credited for closing the gap. They are not apart at all.

    The old comparison put the single solve's WHOLE-MODEL peak -- which
    lands at s=39.60, inside the tip that D6's terminal contact slot
    over-constrains -- against the staged sequence's BAND peak. Two
    different quantities, differing by exactly the artefact the band exists
    to remove.

    So this asserts BOTH halves: the two sequences agree where the metric
    matches, AND the two metrics genuinely differ, so nobody re-reads the
    gap as physics.
    """
    from slay.data.materials import material
    from slay.model.assemble import build_model
    from slay.physics.problem import build_problem
    from slay.solve.passage import solve
    from slay.scene.scene import build_scene

    from slay.physics.contact import material_margin
    # The stinger end must hold the terminal slot and no more -- see
    # `sweep.run`'s hard-pair check for what a mismatch costs.
    _probe = build_scene(R=85.0, spacing=8.0, elastic_length=16.0)
    sc = build_scene(R=85.0, spacing=8.0, elastic_length=16.0,
                     margin_stinger=material_margin(_probe))
    r, _state = solve(build_problem(
        build_model(sc, None), sc, material=material('j2'),
        gravity=True, tension=120.0 * 9806.65))
    assert r.converged, r.status

    s_max, _zone = zone(sc)
    _s, single_band = stage_run.peak_in_zone(r, s_max)
    _ws, single_whole = r.peak_strain()

    _sc, out, _st = staged
    _ss, staged_band = stage_run.peak_in_zone(out[-1].result, s_max)

    assert single_band == pytest.approx(staged_band, rel=0.01), \
        'staging is a CONVERGENCE aid, not an accuracy gain'
    assert single_whole > 1.15 * single_band, \
        'the two metrics must stay visibly different, or the mix-up returns'

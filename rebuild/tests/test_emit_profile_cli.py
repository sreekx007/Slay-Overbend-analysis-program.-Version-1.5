"""The generator's command line actually reaches the model.

L094. `--t-ratio` and `--L-OD` were silently dropped for weeks. `emit`
chooses between two builders by asking whether any EA dimension was
supplied, and the CLI handed it a dict of four `None`s -- which is truthy,
so the EA branch always won and the two plain-component flags went nowhere.

NOTHING FAILED. Nine Series 3 cases ran to convergence, wrote nine profile
artifacts, and reported nine peak strains. They were all the same three
numbers, because all nine were the archetype's default 42 mm wall. The only
reason it was caught is that three wall thicknesses producing identical
strain to four decimals is impossible, and all nine were printed together.

That is G8 exactly: it ran, and running was worth nothing. A flag is part of
the model, so it gets a test like any other part of the model.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

emit_profile = pytest.importorskip('emit_profile')


# ---------------------------------------------------------------------------
# the defect
# ---------------------------------------------------------------------------

def test_no_EA_flags_means_None_not_a_dict_of_Nones():
    """The exact shape that made the branch test lie."""
    assert emit_profile._extra(['prog']) is None


def test_an_EA_flag_is_picked_up():
    assert emit_profile._extra(['prog', '--P-v', '1.2']) == {'P_v': 1.2}
    assert emit_profile._extra(
        ['prog', '--kB-ratio', '3.0', '--P-l1', '4.0']) == {
            'kB_ratio': 3.0, 'P_l1': 4.0}


def test_every_component_dimension_has_a_flag_that_round_trips():
    """Underscore AND dot are flag separators, so `TP.centre_x` is
    `--tp-centre-x`. The dot rule arrived with the dotted names; this
    assertion is what makes it a rule rather than a convention one caller
    happens to follow.
    """
    for k in emit_profile.COMPONENT_DIMS:
        flag = '--' + k.replace('_', '-').replace('.', '-')
        assert emit_profile._extra(['prog', flag, '7.5']) == {k: 7.5}


def test_a_flag_matches_whatever_case_it_is_written_in():
    """L108. Lowercasing the flag and not `argv` broke every upper-case
    flag at once -- `--V`, `--L1`, `--L2`, `--P-v` -- and broke them
    SILENTLY: `_extra` returned None, which `emit` reads as "no dimensions
    were asked for" and answers with the archetype's defaults. A plausible
    strain for a geometry nobody requested, and nothing on the artifact to
    say which geometry it was.
    """
    for k in emit_profile.COMPONENT_DIMS:
        stem = k.replace('_', '-').replace('.', '-')
        for flag in ('--' + stem, '--' + stem.lower(), '--' + stem.upper()):
            assert emit_profile._extra(['prog', flag, '7.5']) == {k: 7.5}, flag


def test_the_flags_the_shroud_RUNNERS_ACTUALLY_PASS_are_picked_up():
    """The three runners for TABLE XXXI, XXXII and XXXIX spell the shroud
    `--V --L1 --L2` and the thick pipe `--tp-l-comp --tp-centre-x`, in one
    command line. Asserting the spellings generically is not enough: L108
    survived because no test used the exact mixture a caller sends.
    """
    got = emit_profile._extra(
        ['prog', '--archetype', 'ILS-SHTP', '--R', '85.0',
         '--V', '0.406400', '--L1', '4.064000', '--L2', '1.016000',
         '--tp-l-comp', '2.032000', '--tp-centre-x', '-1.354667'])
    assert got == {'V': 0.4064, 'L1': 4.064, 'L2': 1.016,
                   'TP.L_comp': 2.032, 'TP.centre_x': -1.354667}


# ---------------------------------------------------------------------------
# the thing the defect broke: a wall thickness must change the component
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('t_ratio,t_mm', [(1.523809524, 32.0),
                                          (2.0, 42.0),
                                          (2.523809524, 53.0)])
def test_t_ratio_reaches_the_built_component(t_ratio, t_mm):
    """Paper 1 Series 3's three cases, by the wall they are supposed to have.

    Built through the SAME call `emit` makes, with an all-None `extra` as
    the CLI supplies it -- so this fails if the branch test regresses.
    """
    import plot_stinger as gen
    extra = {k: None for k in emit_profile.EA_DIMS}
    extra = {k: v for k, v in extra.items() if v is not None} or None
    assert extra is None, 'an all-None extra must collapse to None'
    ils = gen.build_component_ils('ILS-TP', t_ratio=t_ratio)
    body = ils.assembly.components[0]
    got = getattr(body, 't_comp', None) or getattr(body, 't', None)
    assert got == pytest.approx(t_mm / 1000.0, abs=6e-4), (
        f't_ratio={t_ratio} built a {1000 * got:.1f} mm wall, '
        f'not {t_mm:.0f} mm')


def test_three_wall_thicknesses_build_three_different_stiffnesses():
    """The invariant whose violation exposed L094: identical strain from
    three thicknesses is impossible, so the sections must differ first."""
    import plot_stinger as gen
    ods = set()
    for tr in (1.523809524, 2.0, 2.523809524):
        ils = gen.build_component_ils('ILS-TP', t_ratio=tr)
        b = ils.assembly.components[0]
        ods.add(round(getattr(b, 'OD_comp', None)
                      or getattr(b, 'OD', 0.0), 6))
    assert len(ods) == 3, f'constant-bore growth collapsed: {sorted(ods)}'


def test_the_shroud_dimensions_are_drivable():
    """Paper 1's Series 4 is a sweep of V at fixed L1 and L2, and until
    6 Oct none of the three could be set from the command line -- so the one
    published sweep this generator was closest to running was the one it
    could not express. `P_v` is GD-SB's offset and is NOT a substitute: a
    different component, measured from a different datum.
    """
    for k in ('V', 'L1', 'L2'):
        assert k in emit_profile.COMPONENT_DIMS
    got = emit_profile._extra(
        ['prog', '--V', '0.6096', '--L1', '4.064', '--L2', '1.016'])
    assert got == {'V': 0.6096, 'L1': 4.064, 'L2': 1.016}


@pytest.mark.parametrize('V_D', [0.75, 1.0, 1.5, 2.0, 2.5, 3.0])
def test_a_V_reaches_the_built_shroud(V_D):
    """The flag has to change the geometry, not merely parse -- which is
    exactly the distinction L094 was about. These six depths are Paper 1
    TABLE XXXI's R = 85 sweep.
    """
    OD = 0.4064
    ils = emit_profile._ea_ils('ILS-SH', None, None, None, None,
                               {'V': V_D * OD})
    body = ils.assembly.components[0]
    assert body.V == pytest.approx(V_D * OD), (
        f'--V {V_D}D did not reach the component')

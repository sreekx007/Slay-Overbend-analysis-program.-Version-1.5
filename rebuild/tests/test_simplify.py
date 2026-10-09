"""Reducing a real layout to an equivalent GD-Simple.

A reduction is a CLAIM that two different pieces of hardware present the
same thing to the rollers. Three of these tests check the claim where it
holds (length, depth, bending stiffness) and three check that it is refused
where it does not -- a tapered body, two bodies, nothing to reduce. The
remaining one checks the claim this module makes about its own limits: that
the axial stiffness is wrong, by how much, and that it says so.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import config                                               # noqa: E402
from slay.define.archetypes import (FIXTURE,            # noqa: E402
                                    build_component_ils)
from slay.define import simplify as sx                      # noqa: E402

D = 0.4064
OD_P, T_P = 0.4064, 0.021


def tp(L_OD=20.0, t_mm=53):
    return build_component_ils('ILS-TP', L_OD=L_OD, t_ratio=t_mm / 21.0)


# ---------------------------------------------------------------------------
# what the reduction reproduces exactly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('L_OD', [2.5, 10.0, 20.0, 40.0])
def test_length_is_reproduced(L_OD):
    sm, eq = sx.simplify(tp(L_OD=L_OD))
    assert eq.L == pytest.approx(L_OD * D, abs=5e-3)
    assert sm.L_body == pytest.approx(L_OD * D, abs=5e-3)
    # and the shroud occupies the SAME footprint, not a longer one
    assert sm.L1 + 2 * sm.L2 == pytest.approx(eq.L, abs=1e-9)


@pytest.mark.parametrize('t_mm', [32, 42, 53, 65])
def test_depth_is_the_bodys_OWN_contact_surface(t_mm):
    """Read from `contact_at`, not computed from a formula -- but it must
    still come out at OD_comp/2, which is what the formula would give."""
    sm, eq = sx.simplify(tp(t_mm=t_mm))
    OD_comp = (OD_P - 2 * T_P) + 2 * t_mm / 1000.0
    assert eq.depth == pytest.approx(OD_comp / 2.0, abs=1e-6)
    assert sm.V == pytest.approx(OD_comp / 2.0, abs=1e-6)
    # the roller sees the same lift either way
    assert eq.lift == pytest.approx((OD_comp - OD_P) / 2.0, abs=1e-6)


@pytest.mark.parametrize('t_mm,E_GPa', [(32, 349), (42, 496), (53, 682),
                                        (65, 917)])
def test_bending_stiffness_is_reproduced_exactly(t_mm, E_GPa):
    _sm, eq = sx.simplify(tp(t_mm=t_mm))
    I = lambda od: math.pi / 64 * (od ** 4 - (OD_P - 2 * T_P) ** 4)  # noqa
    OD_comp = (OD_P - 2 * T_P) + 2 * t_mm / 1000.0
    assert eq.EI_ratio == pytest.approx(I(OD_comp) / I(OD_P), rel=1e-12)
    # E_equiv on the PIPELINE section gives back the original EI exactly
    assert eq.E_equiv * I(OD_P) == pytest.approx(eq.EI, rel=1e-12)
    assert eq.E_equiv / 1e9 == pytest.approx(E_GPa, abs=0.5)


# ---------------------------------------------------------------------------
# what it cannot reproduce, and must say so
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('t_mm,err_pct', [(32, 6.2), (42, 12.0), (53, 18.8),
                                          (65, 26.6)])
def test_axial_stiffness_is_WRONG_and_reported(t_mm, err_pct):
    """One modulus cannot match EA and EI at once. The error is a property
    of the method, so it is carried on the result rather than discovered."""
    _sm, eq = sx.simplify(tp(t_mm=t_mm))
    assert 100 * eq.EA_error == pytest.approx(err_pct, abs=0.1)
    assert eq.EA_error > 0, 'the stand-in is axially STIFFER, not softer'


def test_the_axial_error_grows_with_the_wall():
    """Area grows faster than the second moment that sets E_equiv, so a
    thicker original is reduced worse. Stated in the docstring; checked."""
    errs = [sx.simplify(tp(t_mm=t))[1].EA_error for t in (32, 42, 53, 65)]
    assert errs == sorted(errs)


# ---------------------------------------------------------------------------
# what it refuses
# ---------------------------------------------------------------------------

def test_a_tapered_body_is_refused_not_averaged():
    with pytest.raises(sx.ReductionError, match='tapered|constant section'):
        sx.equivalent(build_component_ils('ILS-TT'))


def test_a_layout_with_nothing_to_reduce_is_refused():
    """A bare shroud owns contact but no section: there is no stiffness."""
    with pytest.raises(sx.ReductionError, match='owns a section'):
        sx.equivalent(build_component_ils('ILS-SH'))


def test_a_body_that_owns_no_contact_is_refused():
    """ILS-SHTP's thick body sits INSIDE a shroud, which holds contact. Its
    depth is therefore not the thing a roller would touch, and reducing it
    as though it were would put the stand-in at the wrong elevation."""
    with pytest.raises(sx.ReductionError, match='owns no contact'):
        sx.equivalent(build_component_ils('ILS-SHTP'))


def test_a_zero_taper_is_refused_with_the_reason():
    """L2 = 0 is the EXACT equivalent of a GD-TP step, and the mirrored
    `OffsetShroud.validate` forbids it. The refusal has to say that, or the
    next reader will try it again."""
    eq = sx.equivalent(tp())
    with pytest.raises(sx.ReductionError, match='MIRRORED|positive'):
        sx.parameters(eq, L2=0.0)


def test_a_taper_too_long_for_the_body_is_refused():
    eq = sx.equivalent(tp(L_OD=2.5))
    with pytest.raises(sx.ReductionError, match='cannot carry two'):
        sx.parameters(eq, L2=2.5 * D)


# ---------------------------------------------------------------------------
# the built product
# ---------------------------------------------------------------------------

def test_the_stand_in_carries_the_PIPELINE_section_not_the_originals():
    """The whole point: stiffness moves to the modulus so the section, the
    fibre distance and the mass stay the pipeline's."""
    sm, eq = sx.simplify(tp(t_mm=65))
    body = [c for c in sm.ils.assembly.components if c.code == 'GD-TP'][0]
    assert body.OD_comp == pytest.approx(OD_P, abs=1e-12)
    assert body.OD_comp != pytest.approx(eq.OD_comp, abs=1e-6)
    assert sm.E > config.STEEL_E


def test_match_flat_puts_the_tapers_OUTSIDE_the_body():
    """The other matching rule, and it makes a LONGER lifted zone than the
    original had -- which is why it is not the default."""
    eq = sx.equivalent(tp(L_OD=10.0))
    total = sx.parameters(eq, match='total')
    flat = sx.parameters(eq, match='flat')
    assert total['L1'] + 2 * total['L2'] == pytest.approx(eq.L)
    assert flat['L1'] == pytest.approx(eq.L)
    assert flat['L1'] + 2 * flat['L2'] > eq.L


def test_the_reduction_checks_itself_against_what_it_built():
    """`simplify` re-measures its own product. Breaking the build should
    surface there, not in a result -- so a deliberately wrong depth fails."""
    eq = sx.equivalent(tp())
    good = sx.parameters(eq)
    assert good['V'] == pytest.approx(eq.depth)
    from slay.define.simple import build
    sm = build(**{**good, 'V': good['V'] + 0.05})
    got = sx.equivalent_of_simple(sm)
    assert abs(got['depth'] - eq.depth) > sx.FLAT_TOL


# ---------------------------------------------------------------------------
# the archetype builder, now in `define` rather than in a figure module
# ---------------------------------------------------------------------------

def test_every_published_archetype_builds():
    from slay.define.archetypes import definitions
    for arch in definitions():
        ils = build_component_ils(arch)
        assert ils.extent[1] > ils.extent[0], arch
        assert ils.assembly.pipe.OD_pipe > 0, arch


def test_a_dimension_goes_to_the_component_that_HAS_it():
    """ILS-SHTP is a shroud with a thick body inside it, and the shroud is
    components[0]. `L_comp` must reach the BODY, not the first component."""
    ils = build_component_ils('ILS-SHTP', L_OD=5.0)
    body = [c for c in ils.assembly.components if c.code == 'GD-TP'][0]
    assert body.L_comp == pytest.approx(5.0 * ils.assembly.pipe.OD_pipe)


def test_a_dimension_no_component_carries_is_refused():
    """A bare shroud has no `L_comp`. Silently re-dimensioning the wrong
    body is the failure this refusal exists to prevent."""
    with pytest.raises(ValueError, match='no component of this archetype'):
        build_component_ils('ILS-SH', L_OD=1.0)


def test_relative_dimensions_follow_the_pipe_they_are_given():
    """`L_OD` and `t_ratio` are RELATIVE, so changing the pipeline changes
    what they mean -- which is why they are applied after OD and t_wall."""
    a = build_component_ils('ILS-TP', L_OD=10.0)
    b = build_component_ils('ILS-TP', OD=0.3239, t_wall=0.0127, L_OD=10.0)
    ca = [c for c in a.assembly.components if c.code == 'GD-TP'][0]
    cb = [c for c in b.assembly.components if c.code == 'GD-TP'][0]
    assert ca.L_comp == pytest.approx(10.0 * 0.4064)
    assert cb.L_comp == pytest.approx(10.0 * 0.3239)


def test_the_fixture_is_read_per_call_not_cached():
    """Mirrored data (G7). A cache would hold a stale copy across a re-sync,
    which is the silent drift the guardrail exists to prevent."""
    from slay.define import archetypes
    assert archetypes.definitions() is not archetypes.definitions()
    assert archetypes.definitions() == archetypes.definitions()

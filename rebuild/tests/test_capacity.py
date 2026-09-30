"""Telling a case that cannot be solved from one that should not be asked.

Both arrive as `CUTBACK EXHAUSTED at lam=0.0000`. One is a defect to fix and
the other is a pipe that would tear in half, so the distinction cannot be
left to the status string -- it has to be computed.

THE SILENCE IS THE LOAD-BEARING HALF. `explain_failure` returning '' means
the loads were comfortable and the failure is the solver's, which keeps a
real defect visible as one. A screen that explained every failure would be
worse than none: it would retire the three frame archetypes as physics when
they are a mechanism in the model (L082).
"""

from __future__ import annotations

import math

import pytest

import config
from slay.data.materials import material
from slay.physics import capacity as cap

SY = material('j2').sigma_y0            # 360 MPa
TON = 9806.65

# The corner. 160 MT of lay tension on 6-inch pipe.
HARD = dict(OD=0.1683, t_wall=0.0110, tension=160.0 * TON)
# What the matrix is mostly made of.
EASY = dict(OD=0.4064, t_wall=0.0210, tension=120.0 * TON)


def test_area_is_the_wall_not_the_bore():
    OD, t = 0.4064, 0.0210
    got = cap.steel_area(OD, t)
    assert got == pytest.approx(math.pi * (OD - t) * t, rel=2e-3)
    # The bore is NOT steel: using the outside diameter alone would give a
    # section four times too big and every utilisation four times too low.
    assert got < math.pi / 4.0 * OD ** 2 / 3.0


def test_an_impossible_section_is_refused():
    with pytest.raises(ValueError):
        cap.steel_area(0.1683, 0.0)
    with pytest.raises(ValueError):
        cap.steel_area(0.020, 0.011)        # wall thicker than the radius


def test_the_hard_corner_spends_most_of_the_section_on_tension_alone():
    u = cap.utilisation(sigma_y=SY, R=60.0, **HARD)
    assert u['membrane'] == pytest.approx(0.802, abs=0.005)
    assert u['membrane_stress'] == pytest.approx(289e6, rel=0.01)
    # Add the bending a 60 m radius imposes and it cannot stay elastic.
    assert u['combined'] > 1.5


def test_the_baseline_is_nowhere_near():
    u = cap.utilisation(sigma_y=SY, R=85.0, **EASY)
    assert u['membrane'] == pytest.approx(0.129, abs=0.005)
    assert u['membrane'] < cap.HIGH_UTILISATION


def test_the_threshold_separates_the_matrix_as_it_actually_ran():
    """Not an arbitrary number: it has to sit between the two."""
    hard = cap.utilisation(sigma_y=SY, **HARD)['membrane']
    easy = cap.utilisation(sigma_y=SY, **EASY)['membrane']
    assert easy < cap.HIGH_UTILISATION < hard


def test_bending_stress_is_the_elastic_prediction():
    OD, R = 0.4064, 85.0
    assert cap.bending_stress(OD, R) == pytest.approx(
        config.STEEL_E * (OD / 2.0) / R)
    # Tighter radius, more stress -- and the sign of the trend matters more
    # than the value, because past yield it is a demand, not a stress.
    assert cap.bending_stress(OD, 60.0) > cap.bending_stress(OD, 120.0)


def test_a_zero_or_negative_radius_is_refused():
    with pytest.raises(ValueError):
        cap.bending_stress(0.4064, 0.0)


# ---------------------------------------------------------------------------
# explain_failure -- and its silence
# ---------------------------------------------------------------------------

def test_the_hard_corner_gets_a_physical_explanation():
    msg = cap.explain_failure(sigma_y=SY, R=60.0, **HARD)
    assert 'BEYOND SECTION CAPACITY' in msg
    assert '80.2%' in msg
    assert 'Not a convergence defect' in msg


def test_a_comfortable_case_gets_NOTHING():
    """THE IMPORTANT ONE. The three frame archetypes fail at the baseline
    load, where the section is at 12.9% of yield. If this returned a
    message they would be retired as physics when they are a mechanism in
    the model (L082)."""
    assert cap.explain_failure(sigma_y=SY, R=85.0, **EASY) == ''


def test_explain_never_raises_on_a_nonsense_section():
    """It annotates a failure; it must not become one."""
    assert cap.explain_failure(0.020, 0.011, 1e6, SY, 85.0) == ''
    assert cap.explain_failure(0.4064, 0.0, 1e6, SY) == ''


def test_a_radius_is_optional():
    msg = cap.explain_failure(sigma_y=SY, **HARD)
    assert 'BEYOND SECTION CAPACITY' in msg
    assert 'radius' not in msg


def test_utilisation_refuses_a_nonsense_yield():
    with pytest.raises(ValueError):
        cap.utilisation(0.4064, 0.021, 1e6, 0.0)

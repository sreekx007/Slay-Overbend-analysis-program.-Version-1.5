"""T1 -- slay.data.materials.

The VERIFY clause of card T1 is the first two tests. The rest lock the two
transposition hazards the module exists to close, because both produce
numbers that look reasonable rather than errors that stop a run.
"""

import pytest

import config
from slay.data import J2Material, RambergOsgoodMaterial, material


# --------------------------------------------------------------------------
# T1 VERIFY
# --------------------------------------------------------------------------

def test_j2_table():
    """31 points, first point 360 MPa at zero plastic strain."""
    m = material('j2')
    assert isinstance(m, J2Material)
    assert m.n_points == 31
    assert m.yield_stress[0] == 360.0e6
    assert m.plastic_strain[0] == 0.0
    assert m.sigma_y0 == 360.0e6


def test_ro_alpha_is_dnv_convention():
    """alpha_DNV is 1.300, not the 2.278 the kernel's docstring states."""
    m = material('ro')
    assert isinstance(m, RambergOsgoodMaterial)
    assert m.alpha_dnv == 1.300


# --------------------------------------------------------------------------
# Hazard 1 -- table column order
# --------------------------------------------------------------------------

def test_columns_not_transposed():
    """Stress in the stress column, strain in the strain column.

    slay_config.yaml stores [stress, strain]; nlfea_v4 takes eps_p_table
    BEFORE sigma_y_table. A swap anywhere along that path puts 360e6 where
    a strain belongs -- which does not raise, it just solves something else.
    """
    m = material('j2')
    assert all(s > 1e6 for s in m.yield_stress), 'stress column holds Pa'
    assert all(0.0 <= e < 1.0 for e in m.plastic_strain), 'strain is dimensionless'
    assert m.yield_stress[-1] == 530.0e6
    assert m.plastic_strain[-1] == pytest.approx(0.052585)


def test_table_is_monotonic():
    m = material('j2')
    for col in (m.yield_stress, m.plastic_strain):
        assert all(b > a for a, b in zip(col, col[1:]))


def test_transposed_table_is_rejected():
    """Constructing with the columns swapped must fail, not silently accept."""
    t = config.MATERIAL_J2_TABLE
    with pytest.raises(ValueError, match='transposed|ascending|zero plastic'):
        J2Material(
            E=config.MATERIAL_J2_E,
            sigma_y0=t[0][1],
            yield_stress=tuple(r[1] for r in t),
            plastic_strain=tuple(r[0] for r in t),
        )


def test_sigma_y0_must_match_table():
    """Two sources for one quantity is the failure class this project keeps
    eliminating; catch it at construction."""
    t = config.MATERIAL_J2_TABLE
    with pytest.raises(ValueError, match='disagrees'):
        J2Material(
            E=config.MATERIAL_J2_E,
            sigma_y0=385.0e6,
            yield_stress=tuple(r[0] for r in t),
            plastic_strain=tuple(r[1] for r in t),
        )


# --------------------------------------------------------------------------
# Hazard 2 -- which alpha convention
# --------------------------------------------------------------------------

def test_alpha_matches_the_dnv_formula():
    """Independent check against the formula, not against the stored value.

        alpha_DNV = (0.005 - sig_ys/E) * E / sig_ys

    This is verification, not derivation -- the module still reads the
    number from config and never computes it (G1 for T1).
    """
    m = material('ro')
    expected = (0.005 - m.sig_ys / m.E) * m.E / m.sig_ys
    assert expected == pytest.approx(1.300, abs=1e-4)
    assert m.alpha_dnv == pytest.approx(expected, abs=1e-4)


def test_alpha_is_not_the_api1104_value():
    """API 1104's alpha = 0.005*E/sig_ys gives 2.300 here. Distinct enough
    from the DNV 1.300 that a mix-up changes the hardening substantially."""
    m = material('ro')
    api = 0.005 * m.E / m.sig_ys
    assert api == pytest.approx(2.300, abs=1e-3)
    assert m.alpha_dnv != pytest.approx(api, abs=0.1)


def test_ro_parameters():
    m = material('ro')
    assert m.E == 207.0e9
    assert m.sig_ys == 450.0e6
    assert m.n_ro == 20.59
    assert m.eps_y == pytest.approx(450.0e6 / 207.0e9)


# --------------------------------------------------------------------------
# Refusal
# --------------------------------------------------------------------------

def test_unknown_material_refuses():
    with pytest.raises(ValueError, match='unknown material'):
        material('j3')


def test_refusal_names_the_valid_set():
    with pytest.raises(ValueError) as exc:
        material('steel')
    assert 'j2' in str(exc.value) and 'ro' in str(exc.value)


def test_case_and_whitespace_tolerated():
    assert material(' J2 ').kind == 'j2'
    assert material('RO').kind == 'ro'


# --------------------------------------------------------------------------
# Layer hygiene
# --------------------------------------------------------------------------

def test_materials_does_not_import_the_kernel():
    """The data layer must not reach into the solver. The linter enforces
    this across the package; asserting it here names the specific reason so
    a future edit sees why before the linter tells it off."""
    src = (__import__('pathlib').Path(__file__).parents[1]
           / 'slay' / 'data' / 'materials.py').read_text()
    assert 'import nlfea_v4' not in src
    assert 'from nlfea_v4' not in src

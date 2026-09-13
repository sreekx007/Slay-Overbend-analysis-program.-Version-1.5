"""The mesher test rig, solved -- `docs/modules/T3_mesher_test_plan.md`.

These are the first tests in the suite that RUN THE SOLVER on something
`build_model` produced. Everything in `test_model.py` checks the model's
shape; this checks that the shape gives the right answer.

WHY THAT IS A DIFFERENT QUESTION. A mesh can be structurally perfect --
every station present, nothing merged, counts pinned -- and still be wrong:
a node in the wrong place, a span double-counted, a length subtly off. None
of that shows up in a count. It shows up in a deflection.

THE RIG'S ONE IDEA: with the pipeline section applied to every element the
beam is prismatic, so the exact solution is piecewise cubic and lies inside
the element space. The discretisation contributes nothing, and anything the
mesher does must therefore be invisible in the result.

Expected values are pinned from `T3_mesher_test_plan.md` section 5, which
were measured independently by `tools/spike_mesher_rig.py` on a HAND-BUILT
mesh before `build_model` existed. Two independent construction paths
agreeing to nine significant figures is the evidence; either alone would not
be.
"""

import math

import pytest

np = pytest.importorskip('numpy')
fe = pytest.importorskip('nlfea_v4')

import run_mesher_rig as rig            # noqa: E402  (tools/, via conftest)

# T3_mesher_test_plan.md section 5, at tol = 1e-6, n_increments = 20.
EXPECTED = {
    #                L        20 kN mm      200 kN mm   elements
    'ILS-TP':   (13.000,  2.30160,  22.97868, 16),
    'ILS-TT':   (14.808,  3.40158,  33.89434, 26),
    'ILS-SH':   (18.096,  6.20730,  61.35083, 22),
    'ILS-SHTP': (18.096,  6.20729,  61.34903, 24),
}

SIG_YIELD = 360e6


@pytest.fixture(scope='module')
def solved():
    out = {}
    for aid in rig.GROUP_A:
        m, L, s_load = rig.build(aid)
        for P in (20e3, 200e3):
            U, ms, i_load = rig.solve(m, s_load, P)
            d = U[3 * ms.user_node_to_mesh[i_load] + 1]
            _, sig, eps = rig.recover(U, ms)
            out[(aid, P)] = (m, L, d, sig, eps)
    return out


@pytest.mark.parametrize('arch_id', sorted(EXPECTED))
def test_rig_geometry_matches_the_plan(solved, arch_id):
    L_exp, _, _, n_exp = EXPECTED[arch_id]
    m, L, _, _, _ = solved[(arch_id, 20e3)]
    assert L == pytest.approx(L_exp, abs=1e-3)
    assert m.n_elems == n_exp


@pytest.mark.parametrize('arch_id', sorted(EXPECTED))
def test_deflection_reproduces_the_spike(solved, arch_id):
    """build_model and the hand-built spike agree to nine significant figures."""
    _, d20, d200, _ = EXPECTED[arch_id][0], *EXPECTED[arch_id][1:]
    for P, want in ((20e3, EXPECTED[arch_id][1]), (200e3, EXPECTED[arch_id][2])):
        _, _, d, _, _ = solved[(arch_id, P)]
        assert d * 1e3 == pytest.approx(want, abs=5e-5), f'{arch_id} at {P/1e3} kN'


@pytest.mark.parametrize('arch_id', sorted(EXPECTED))
def test_matches_the_closed_form_in_the_analytical_regime(solved, arch_id):
    """At 20 kN the solver must land on the fixed-fixed closed form, and be
    STIFFER by the predicted membrane term -- a band, not an open bound. An
    open 'within 1%' would pass happily on a mesher that had lost a station."""
    _, L, d, _, _ = solved[(arch_id, 20e3)]
    d_cf, _ = rig.closed_form(20e3, L, L / 2)
    err = d / d_cf - 1
    assert -2.0e-4 < err < 0.0, f'{arch_id}: {err:.2e} outside the membrane band'


@pytest.mark.parametrize('arch_id', sorted(EXPECTED))
def test_membrane_stiffening_is_present_at_200kN(solved, arch_id):
    """The specified rig is 0.16% to 1.18% away from linear. That is physics,
    not a mesher defect, and asserting it stops the nonlinearity being
    mistaken for one later."""
    _, L, d, _, _ = solved[(arch_id, 200e3)]
    d_cf, _ = rig.closed_form(200e3, L, L / 2)
    assert -1.3e-2 < d / d_cf - 1 < -1.0e-3


def test_sh_and_shtp_are_the_same_beam(solved):
    """The sharpest check in the plan, and it needs no closed form. Identical
    extents, identical load point, 22 uniform elements against 24 graded."""
    d_sh = solved[('ILS-SH', 20e3)][2]
    d_shtp = solved[('ILS-SHTP', 20e3)][2]
    assert abs(d_sh / d_shtp - 1) < 1e-6

    # At 200 kN a real difference appears -- the corotational element is no
    # longer exact once the response is geometrically nonlinear. It is pinned
    # at its measured value rather than bounded: a one-sided bound would pass
    # on a mesher that had grown far more sensitive.
    d_sh = solved[('ILS-SH', 200e3)][2]
    d_shtp = solved[('ILS-SHTP', 200e3)][2]
    assert abs(d_sh / d_shtp - 1) == pytest.approx(2.95e-5, rel=0.2)


@pytest.mark.parametrize('arch_id', sorted(EXPECTED))
def test_every_case_stays_elastic(solved, arch_id):
    """With no plasticity anywhere, the material model cannot absorb a meshing
    error and hide it. Worst case is 192 MPa against a 360 MPa first yield."""
    for P in (20e3, 200e3):
        _, _, _, sig, _ = solved[(arch_id, P)]
        assert sig.max() < SIG_YIELD


def test_peak_stress_lands_where_the_moment_diagram_says(solved):
    """Fixed-fixed with a central point load peaks at the two ends and at the
    load, and is zero at the two contraflexure points. Plotted rather than
    asserted tightly: a peak is a maximum over elements, which is exactly the
    quantity that moves when a node moves."""
    m, L, _, sig, _ = solved[('ILS-SH', 200e3)]
    at = {n.index: n for n in m.nodes}
    mid = np.array([0.5 * (at[e.n1].s + at[e.n2].s) for e in m.elements])
    hot = mid[np.argsort(sig)[-3:]]
    assert max(abs(hot)) > 0.4 * L / 2, 'no peak near an end'
    assert min(abs(hot)) < 0.1 * L / 2, 'no peak at the load point'


def test_strain_is_stress_over_E(solved):
    _, _, _, sig, eps = solved[('ILS-SH', 200e3)]
    assert np.allclose(eps, sig / rig.E)

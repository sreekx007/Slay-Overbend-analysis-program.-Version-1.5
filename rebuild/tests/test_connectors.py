"""Penalty-tied connectors on the GD-ST frame, five layouts.

The first working penalty constraints. These guard three things that were
wrong before they were measured:

1. THE PENALTY IS SCALED TO THE LOCAL DIAGONAL, not the global maximum the
   kernel uses. In a frame matrix the translational and rotational diagonals
   differ by orders of magnitude, so a global scale makes conditioning carry
   the whole spread instead of just the penalty factor.

2. THE WORKING ALPHA WAS MEASURED. At 1e5 the displacement has converged to
   six figures and cond(K) = 3.9e13. Beyond it the violation keeps falling
   and buys nothing while conditioning runs away -- 2e21 at 1e9.

3. AN ENGAGED DEADBAND HOLDS AT THE GAP EDGE, not at zero. Enforcing zero
   drags the node back to coincidence, the separation drops below the gap,
   the connector releases, and it separates again -- the active set chatters
   and never converges. It did, at four flips and no settled state.
"""

import math

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import study_connectors as conn        # noqa: E402  (tools/, via conftest)

LAYOUTS = ('F1', 'F2', 'PS', 'PSD', 'F2D')


@pytest.fixture(scope='module')
def rigs():
    return {name: conn.Rig(name) for name in LAYOUTS}


@pytest.mark.parametrize('name', LAYOUTS)
def test_layout_solves(rigs, name):
    U, info = conn.solve(rigs[name], 200e3)
    assert np.all(np.isfinite(U))
    assert info['cond'] < 1e16, 'conditioning past what double precision holds'


@pytest.mark.parametrize('name', LAYOUTS)
def test_reactions_balance(rigs, name):
    """Every layout must carry the whole applied load into the fixed bottom
    nodes -- the ones that will be the pipe."""
    rig = rigs[name]
    U, _ = conn.solve(rig, 200e3)
    _, Fint = rig.assemble(U)
    Ry = sum(Fint[3*i_bot + 1] for (_t, i_bot, _it, _if_) in rig.conns)
    assert -Ry == pytest.approx(200e3, rel=1e-4)


@pytest.mark.parametrize('name', LAYOUTS)
def test_constraints_are_satisfied(rigs, name):
    U, info = conn.solve(rigs[name], 200e3)
    assert info['violation'] < 1e-8, 'penalty is not holding the tie'


@pytest.mark.parametrize('name', LAYOUTS)
def test_response_is_linear_at_these_loads(rigs, name):
    """Ten times the load, ten times the displacement. Deflections are
    ~3 mm on a 6.5 m frame, so anything else means a spurious nonlinearity."""
    rig = rigs[name]
    d20 = conn.solve(rig, 20e3)[0][3 * rig.top_node + 1]
    d200 = conn.solve(rig, 200e3)[0][3 * rig.top_node + 1]
    assert d200 / d20 == pytest.approx(10.0, rel=1e-3)


def test_single_connector_is_softest(rigs):
    """F1 puts one connector at the centre; F2 puts two under the load path.
    One support point must be softer than two."""
    d = {n: conn.solve(rigs[n], 200e3)[0][3 * rigs[n].top_node + 1]
         for n in ('F1', 'F2')}
    assert d['F1'] > d['F2']


def test_ps_is_softer_than_f2(rigs):
    """Same two slots, less restraint: P frees rotation at one, S frees
    sliding at the other. It must show up as a softer frame."""
    d_f2 = conn.solve(rigs['F2'], 200e3)[0][3 * rigs['F2'].top_node + 1]
    d_ps = conn.solve(rigs['PS'], 200e3)[0][3 * rigs['PS'].top_node + 1]
    assert d_ps > d_f2
    assert d_ps / d_f2 == pytest.approx(1.087, rel=0.02)


@pytest.mark.parametrize('base,with_d', (('PS', 'PSD'), ('F2', 'F2D')))
def test_open_deadbands_change_nothing(rigs, base, with_d):
    """A D restrains nothing while open, so adding two of them must be
    EXACTLY a no-op -- not nearly one."""
    d_a = conn.solve(rigs[base], 200e3)[0][3 * rigs[base].top_node + 1]
    d_b = conn.solve(rigs[with_d], 200e3)[0][3 * rigs[with_d].top_node + 1]
    assert d_a == pytest.approx(d_b, rel=1e-9)


def test_deadband_engages_and_stiffens(rigs):
    """The check that separates 'D is open' from 'D is broken'.

    Shrink the gap until the outer supports engage. The frame must stiffen,
    monotonically, and the active set must SETTLE -- chatter is what the
    hold-at-the-gap-edge signature exists to prevent.
    """
    rig = rigs['PSD']
    keep = conn.P_GAP
    try:
        out = []
        for gap in (1e-3, 5e-4, 3e-4, 1e-4, 3e-5):
            conn.P_GAP = gap
            U, info = conn.solve(rig, 200e3)
            out.append((gap, U[3 * rig.top_node + 1], info))
            assert info['active_flips'] <= 2, (
                f'active set chattered at gap {gap}: '
                f'{info["active_flips"]} flips')
    finally:
        conn.P_GAP = keep

    d = [v for _g, v, _i in out]
    assert d == sorted(d, reverse=True), 'tighter gap must not soften the frame'
    assert d[0] / d[-1] > 1.4, 'engagement barely changed anything'
    assert any(e for _g, _v, i in out for e in i['engaged']), 'nothing engaged'


def test_connector_stiffness_ignores_its_own_length():
    """Pass 4's rule, in the one place it could be violated. The 6x6 is formed
    at L0 = OD; the geometry supplies orientation and nothing else. Two
    connectors of different length must have the same stiffness magnitude."""
    k_short = conn.connector_k6(0.0, 0.5 * conn.OD)
    k_long = conn.connector_k6(0.0, 5.0 * conn.OD)
    assert np.allclose(k_short, k_long)
    k_zero = conn.connector_k6(0.0, 0.0)
    assert np.all(np.isfinite(k_zero)), 'zero length must not be a special case'
    assert np.allclose(np.abs(k_zero), np.abs(k_short))

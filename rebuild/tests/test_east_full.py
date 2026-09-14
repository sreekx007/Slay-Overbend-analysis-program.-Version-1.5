"""ILS-EAST complete: pipe, frame and connectors solved as one model.

The first Group B case that carries load. Everything comes from
`build_model` -- the header, the frame, the connector elements and the four
declared associations -- and the associations are applied as penalty
constraints, closing the load path:

    pipe node  ~~W~~  C-P  --[ connector ]--  C-E  ~~F~~  frame slot

THE RESULT THAT MATTERS is not the deflection, it is the comparison. A bare
pipe of the same span deflects 6.636 mm at 20 kN; with the ILS on it, 5.045.
The frame is not scenery -- it carries moment across the span between its
connectors and shields the pipe there.

ONE BUG THESE GUARD. `MeshedStructure._mesh` assigns mesh indices in
ELEMENT-ENCOUNTER order, so `user_node_to_mesh` is a permutation of our node
ids and not the identity. Writing connector stiffness at `3*id` put it on the
wrong rows and left four frame nodes with empty ones: twelve zero diagonals
and an exactly singular matrix. `test_kernel_leaves_the_model_intact` asserts
the map is a BIJECTION -- and a bijection is all it asserts. Callers have to
go through it.
"""

import math

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import study_east_full as east        # noqa: E402  (tools/, via conftest)


@pytest.fixture(scope='module')
def built():
    m, L = east.build()
    ms, beams = east.kernel_mesh(m)
    return m, L, ms, beams


@pytest.fixture(scope='module')
def solved(built):
    m, L, ms, beams = built
    return {P: east.solve(m, ms, P) for P in (20e3, 200e3)}


def test_assembly_is_what_build_model_produced(built):
    m, L, ms, beams = built
    assert (m.n_nodes, m.n_elems) == (45, 42)
    assert len([e for e in m.elements if e.connector is not None]) == 2
    assert len([e for e in m.elements if e.owner == 'pipeline']) == 22
    assert len([e for e in m.elements if e.owner == 'ST']) == 18
    assert len(m.associations) == 4


def test_node_map_is_not_the_identity(built):
    """The bug, pinned. If this ever became the identity the `dof()` indirection
    would look redundant and get removed -- and the next model with a late
    element would silently go singular again."""
    m, L, ms, beams = built
    assert set(ms.user_node_to_mesh.values()) == set(range(ms.n_nodes))
    assert any(ms.user_node_to_mesh[i] != i for i in range(m.n_nodes)), (
        'the map happens to be the identity here; the indirection is still '
        'required and this test needs a model where it is not')


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_it_solves(solved, P):
    U, _i, _f, viol = solved[P]
    assert np.all(np.isfinite(U))
    assert viol < 1e-8, 'penalty is not holding the ties'


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_reactions_balance(built, solved, P):
    m, L, ms, beams = built
    U, _i, fixed, _v = solved[P]
    _, Fint = east.assemble(m, ms, U)
    Ry = sum(Fint[d] for d in fixed if d % 3 == 1)
    assert -Ry == pytest.approx(P, rel=1e-4)


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_the_ils_stiffens_the_pipe(built, solved, P):
    """The comparison IS the result. A frame tied on through connectors must
    take load, so the pipe has to come out stiffer than a bare beam of the
    same span. Anything else means the connectors are not transmitting."""
    m, L, ms, beams = built
    U, i_load, _f, _v = solved[P]
    d = U[east.dof(ms, i_load, 1)]
    bare = P * L**3 / (192 * east.EI_PIPE)
    assert d < bare, 'the ILS made no difference -- connectors not carrying'
    assert d / bare == pytest.approx(0.760, rel=0.02)


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_frame_follows_the_pipe(built, solved, P):
    """All-DOF ties over a 0.61 m connector: the frame rides down with the
    pipe rather than deforming much on its own."""
    m, L, ms, beams = built
    U, i_load, _f, _v = solved[P]
    top = next(n for n in m.nodes if n.part_id and n.part_id.endswith('stop1'))
    d_pipe = U[east.dof(ms, i_load, 1)]
    d_frame = U[east.dof(ms, top.index, 1)]
    assert d_frame == pytest.approx(d_pipe, rel=0.03)


def test_response_is_linear(built, solved):
    m, L, ms, beams = built
    d20 = solved[20e3][0][east.dof(ms, solved[20e3][1], 1)]
    d200 = solved[200e3][0][east.dof(ms, solved[200e3][1], 1)]
    assert d200 / d20 == pytest.approx(10.0, rel=1e-3)


def test_pipe_is_shielded_between_the_connectors(built, solved):
    """The engineering result. The frame bridges the span between its two
    connection points, so the pipe's stress DROPS there and peaks just
    outside. A model where the connectors did nothing would show a plain
    fixed-fixed diagram with its maximum at midspan instead."""
    m, L, ms, beams = built
    U, _i, _f, _v = solved[200e3]
    _, sig = east.member_stress(m, ms, U, beams)
    pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
    at = {n.index: n for n in m.nodes}
    mid = np.array([0.5 * (at[beams[k].n1].s + at[beams[k].n2].s)
                    for k in pipe_ix])
    s_conn = 1.0837333333333332

    inner = sig[pipe_ix][np.abs(mid) < 0.8 * s_conn]
    outside = sig[pipe_ix][(np.abs(mid) > 1.2 * s_conn)
                           & (np.abs(mid) < 2.5 * s_conn)]
    assert inner.max() < outside.max(), (
        'no shielding: the pipe is not being relieved between the connectors')
    assert outside.max() / inner.max() > 2.0


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_everything_stays_elastic(built, solved, P):
    m, L, ms, beams = built
    U, _i, _f, _v = solved[P]
    _, sig = east.member_stress(m, ms, U, beams)
    assert sig.max() < east.SIG_YIELD

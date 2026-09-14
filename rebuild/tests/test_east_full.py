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
    assert d / bare == pytest.approx(0.745, rel=0.02)


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


# ---------------------------------------------------------------------------
# rotation ties -- the thing a deformed-shape plot cannot show
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('P', (20e3, 200e3))
def test_rotations_are_tied_not_just_translations(built, solved, P):
    """An F/W tie is all-DOF, and rz is the component a picture cannot check.

    A plot draws each element as a chord between its end positions, so it
    shows RIGID-BODY tilt and never end rotation. A connector that is rz-tied
    but bending looks, in a chord plot, exactly like one whose rotation is not
    tied at all. Only the numbers distinguish them.
    """
    m, L, ms, beams = built
    U, _i, _f, _v = solved[P]
    idx = m._part_index
    for a in m.associations:
        ia, ib = idx[a.node_a], idx[a.node_b]
        ra = U[east.dof(ms, ia, 2)]
        rb = U[east.dof(ms, ib, 2)]
        assert abs(ra - rb) < 1e-7, f'{a.node_a} rz not tied to {a.node_b}'
        assert abs(ra) > 1e-9, 'nothing rotated -- the check is vacuous'


def test_connector_bends_because_pipe_and_frame_rotate_differently(built, solved):
    """Why the connector does not simply tilt with the pipe.

    Its lower end matches the PIPE's rotation and its upper end the FRAME's,
    and at the connector station those differ by about 5.6x -- the frame is a
    stiff closed portal and stays nearly flat while the pipe bends under it.
    A 0.61 m element tied to both has to take up the difference, so its chord
    tilt lies BETWEEN the two end rotations rather than matching either.
    """
    m, L, ms, beams = built
    U, _i, _f, _v = solved[200e3]
    at = {n.index: n for n in m.nodes}
    conns = [e for e in m.elements if e.connector is not None]
    assert conns
    for e in conns:
        a, b = at[e.n1], at[e.n2]
        th0 = math.atan2(b.y - a.y, b.s - a.s)
        th = math.atan2(
            (b.y + U[east.dof(ms, e.n2, 1)]) - (a.y + U[east.dof(ms, e.n1, 1)]),
            (b.s + U[east.dof(ms, e.n2, 0)]) - (a.s + U[east.dof(ms, e.n1, 0)]))
        tilt = th - th0
        tilt -= 2 * math.pi * round(tilt / (2 * math.pi))
        r_pipe = U[east.dof(ms, e.n1, 2)]
        r_frame = U[east.dof(ms, e.n2, 2)]
        assert abs(r_pipe) > 3 * abs(r_frame), (
            'pipe and frame rotate alike here, so the case being described '
            'has changed shape')
        lo, hi = sorted((r_pipe, r_frame))
        assert lo < tilt < hi, 'chord tilt is not between the end rotations'


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_connector_stress_is_reported_and_elastic(built, solved, P):
    """The gap this closed. `member_stress` covers only the kernel's beams, so
    the connectors -- assembled outside it -- were never checked at all, and
    "everything stays elastic" was said without looking at them.

    They are the second most stressed part of the model, and at an F
    connection that is no accident: an all-DOF tie at both ends of a short
    stiff element between members that rotate differently forces it to bend.
    """
    m, L, ms, beams = built
    U, _i, _f, _v = solved[P]
    conns = east.connector_forces(m, ms, U)
    assert len(conns) == 2
    for c in conns:
        assert c['sigma'] < east.SIG_YIELD
        assert abs(c['M_pipe_end']) > abs(c['M_frame_end']), (
            'the pipe end should carry the larger moment -- it is the end '
            'forced to follow the more sharply rotating member')
    assert max(c['sigma'] for c in conns) > 0.5 * 152.1e6 * (P / 200e3)


# ---------------------------------------------------------------------------
# PS -- the joint type is the only thing that changes
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def bare_pipe(built):
    """The same pipe, same mesh, same BCs, with no ILS attached."""
    import nlfea_v4 as fe
    m, L, ms, beams = built
    pipe = [e for e in m.elements if e.owner == 'pipeline']
    keep, ren = [], {}
    for e in pipe:
        for g in (e.n1, e.n2):
            if g not in ren:
                ren[g] = len(keep)
                keep.append(m.nodes[g])
    mdl = fe.Model(
        nodes=[fe.Node(i, n.s, n.y) for i, n in enumerate(keep)],
        elements=[fe.UserElement(k, ren[e.n1], ren[e.n2], 1, 1, seed=1)
                  for k, e in enumerate(pipe)],
        sections=[fe.PipeSection(1, east.OD, east.T_WALL)],
        materials=[fe.Material(1, east.E_PIPE)])
    b = fe.MeshedStructure(mdl)
    ends = [min(range(len(keep)), key=lambda i: keep[i].s),
            max(range(len(keep)), key=lambda i: keep[i].s)]
    bc = [3 * b.user_node_to_mesh[i] + k for i in ends for k in (0, 1, 2)]
    il = min(range(len(keep)), key=lambda i: abs(keep[i].s))
    U, _, _ = fe.solve_step(
        b, np.zeros(b.n_dofs),
        {'joint_init': [fe.JointLoad(1, il, 0.0, 200e3, 0.0)]},
        bc, [0.0] * len(bc), n_increments=20, tol=1e-6, max_iter=60)
    return U[3 * b.user_node_to_mesh[il] + 1]


@pytest.fixture(scope='module')
def ps(built):
    m, L, ms, beams = built
    return {P: east.solve(m, ms, P, layout='PS') for P in (20e3, 200e3)}


def test_ps_ties_are_what_ps_means(built):
    """P frees rotation, S frees sliding along the frame. Same model, same
    mesh, same connector elements -- only which DOF are tied."""
    m, L, ms, beams = built
    at = {n.index: n for n in m.nodes}
    slot = {at[e.n2].part_id: e.connector.slot
            for e in m.elements if e.connector is not None}
    idx = m._part_index
    pairs = east.constraint_pairs(m, 'PS')
    tied = {}
    for name, sl in slot.items():
        tied[sl] = sorted(c for (na, nb, c, _t) in pairs if na == idx[name])
    assert tied[2] == [0, 1], 'P is a pin: both translations tied, rz free'
    assert tied[4] == [1], 'S is a roller: only the perpendicular is tied'


def test_p_connector_carries_no_moment(built, ps):
    """A revolute is a revolute. Freeing rz at the EA end makes the whole
    connector a two-force member -- zero moment at BOTH ends, not just the
    released one."""
    m, L, ms, beams = built
    U, _i, _f, _v = ps[200e3]
    conns = {c['line_id']: c for c in east.connector_forces(m, ms, U)}
    p_conn = conns['ST:connector2']
    assert abs(p_conn['M_pipe_end']) < 1e3
    assert abs(p_conn['M_frame_end']) < 1e3


def test_ps_connectors_carry_neither_moment_nor_shear(built, ps):
    """The correction, pinned. PS must leave the connectors as pure struts.

    They did not, until 14 Sep: with S tying rz the slot-4 connector carried
    338.79 kN.m with exactly zero shear -- a PURE COUPLE, which a bolt in a
    slot has no way to provide. P and S are a pin and a roller; neither can
    transmit moment, and with one translation released no shear can build up
    either.
    """
    m, L, ms, beams = built
    U, _i, _f, _v = ps[200e3]
    for c in east.connector_forces(m, ms, U):
        assert abs(c['M_pipe_end']) < 1.0, c['line_id']
        assert abs(c['M_frame_end']) < 1.0, c['line_id']
        assert abs(c['shear']) < 1.0, c['line_id']


def test_f2_connectors_carry_far_more_than_ps(built, solved, ps):
    """F2 locks rotation at both ends of a short stiff element between members
    that rotate differently, so it must bend hard. PS releases exactly that."""
    m, L, ms, beams = built
    f2 = east.connector_forces(m, ms, solved[200e3][0])
    p_s = east.connector_forces(m, ms, ps[200e3][0])
    assert max(abs(c['M_pipe_end']) for c in f2) > 300e3
    assert max(abs(c['shear']) for c in f2) > 500e3
    assert max(abs(c['M_pipe_end']) for c in p_s) < 1.0
    assert max(abs(c['shear']) for c in p_s) < 1.0


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_ps_reactions_balance(built, ps, P):
    m, L, ms, beams = built
    U, _i, fixed, _v = ps[P]
    _, Fint = east.assemble(m, ms, U)
    assert -sum(Fint[d] for d in fixed if d % 3 == 1) == pytest.approx(P,
                                                                      rel=1e-4)


def test_ps_makes_the_ils_a_passenger(built, solved, ps, bare_pipe):
    """The result, and it is exact rather than approximate.

    A rigid frame held at TWO points by a pin and a roller is statically
    determinate against any motion of those points: it translates, rotates,
    and the roller absorbs the change in spacing. It can never be forced to
    deform, so it can never carry force. The pipe therefore behaves exactly as
    if the ILS were not there -- not nearly, exactly.
    """
    m, L, ms, beams = built
    d_ps = ps[200e3][0][east.dof(ms, ps[200e3][1], 1)]
    assert d_ps == pytest.approx(bare_pipe, rel=1e-6)

    frame_ix = [k for k, e in enumerate(beams) if e.owner == 'ST']
    s_ps = east.member_stress(m, ms, ps[200e3][0], beams)[1][frame_ix].max()
    assert s_ps < 1e3, 'the frame should carry no bending at all'


def test_f2_stiffens_where_ps_does_not(built, solved, ps, bare_pipe):
    """The engineering comparison, against a bare pipe solved the same way."""
    m, L, ms, beams = built
    d_f2 = solved[200e3][0][east.dof(ms, solved[200e3][1], 1)]
    d_ps = ps[200e3][0][east.dof(ms, ps[200e3][1], 1)]
    assert 1 - d_f2 / bare_pipe == pytest.approx(0.245, abs=0.01)
    assert 1 - d_ps / bare_pipe == pytest.approx(0.0, abs=1e-5)
    assert d_ps > d_f2


def test_ps_does_not_shield_the_pipe_at_all(built, solved, ps):
    """The result that matters for the program's purpose. F2 drops the pipe's
    stress sharply between its connectors; PS leaves it on the plain
    fixed-fixed diagram. Same geometry, same mesh, same connector stiffness --
    the difference is the joint type alone."""
    m, L, ms, beams = built
    pipe_ix = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
    at = {n.index: n for n in m.nodes}
    mid = np.array([0.5 * (at[beams[k].n1].s + at[beams[k].n2].s)
                    for k in pipe_ix])
    inner = np.abs(mid) < 0.8 * 1.0837333333333332

    s_f2 = east.member_stress(m, ms, solved[200e3][0], beams)[1][pipe_ix][inner]
    s_ps = east.member_stress(m, ms, ps[200e3][0], beams)[1][pipe_ix][inner]
    assert s_ps.max() > 2.0 * s_f2.max(), (
        'PS is shielding the pipe as much as F2 -- the released DOF are not '
        'being released')

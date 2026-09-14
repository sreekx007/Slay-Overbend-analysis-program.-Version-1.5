"""ILS-EAST on F2D: the deadband gap, measured both sides of its threshold.

F2D is the first system whose GEOMETRY differs rather than only its ties. F2
and PS populate the same two slots, so PS was a tie override on an F2 model;
F2D populates four, with a `D` at each outer slot, so it has to be built.

WHAT A D IS, and these guard every word of it. A pure support: it restrains
the perpendicular translation and NOTHING else -- not sliding, not rotation --
and only once the two sides have moved P_gap apart. Open, it restrains
nothing at all, so F2D with no engagement must BE F2, not resemble it.

THE THRESHOLD IS MEASURED, NOT ASSUMED. With every D open the outer slots
move 3.004 mm at 200 kN and 0.300 mm at 20 kN. Those two numbers predict
every engaged/open cell in the sweep, at both loads, and the tests below
check the prediction rather than the curve.
"""

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import study_east_full as east      # noqa: E402  (tools/, via conftest)
import study_east_f2d as f2d        # noqa: E402

X_OUTER = 2.1674666666666664        # the outer slot, |s| = |x|


@pytest.fixture(scope='module')
def built():
    m, L = east.build(system='F2D', p_gap=max(f2d.GAPS))
    ms, beams = east.kernel_mesh(m)
    return m, L, ms, beams


@pytest.fixture(scope='module')
def swept():
    """Every gap, both loads. Each gap is a REBUILD, because P_gap is
    component data and rides on the component, not on the solver."""
    out = {}
    for gap in f2d.GAPS:
        m, _L = east.build(system='F2D', p_gap=gap)
        ms, beams = east.kernel_mesh(m)
        for P in (20e3, 200e3):
            U, i_load, fixed, info = f2d.solve_deadband(m, ms, P)
            out[(gap, P)] = (m, ms, beams, U, i_load, fixed, info)
    return out


def _d(rec):
    m, ms, beams, U, i_load, fixed, info = rec
    return U[east.dof(ms, i_load, 1)]


# -- the assembly ---------------------------------------------------------

def test_f2d_adds_two_connectors_and_two_stations(built):
    """F2 has two connectors; F2D has four, at the outer pair. Each forces a
    header station at its slot, which is the ONLY way F2D's pipeline mesh
    differs from F2's."""
    m, L, ms, beams = built
    conns = [e for e in m.elements if e.connector is not None]
    assert len(conns) == 4
    assert sorted(e.connector.slot for e in conns) == [1, 2, 4, 5]
    assert sorted(e.connector.conn_type for e in conns) == ['D', 'D', 'F', 'F']
    assert (m.n_nodes, m.n_elems) == (49, 44)
    assert len(m.associations) == 8
    at = {n.index: n for n in m.nodes}
    pipe_s = {round(at[i].s, 6) for e in m.elements if e.owner == 'pipeline'
              for i in (e.n1, e.n2)}
    assert round(X_OUTER, 6) in pipe_s and round(-X_OUTER, 6) in pipe_s


def test_the_d_geometry_is_opt_in_and_says_so(built):
    """G9 has not been widened. `build_model` still refuses D by default; the
    study asks for the GEOMETRY only, and every connector it gets that way is
    recorded on the model as unenforced."""
    from slay.model.assemble import build_model, AssemblyError, \
        SUPPORTED_CONN_TYPES
    m, L, ms, beams = built
    assert 'D' not in SUPPORTED_CONN_TYPES
    assert len(m.warnings) == 2
    assert all('GEOMETRY ONLY' in w for w in m.warnings)
    with pytest.raises(AssemblyError, match=r"'D'.*not implemented"):
        east.build(system='F2D', p_gap=1e-3, emit_d=False)


def test_the_gap_is_component_data(built):
    """P_gap rides on GD-ST and arrives on the association. It is not a
    solver setting, and it has no default -- a deadband REDISTRIBUTES strain
    and the gap chooses where, so a silent default would make an engineering
    decision on its own."""
    m, L, ms, beams = built
    gaps = {a.node_a: a.gap for a in m.associations if a.conn_type == 'D'}
    assert len(gaps) == 2
    assert all(g == pytest.approx(max(f2d.GAPS)) for g in gaps.values())
    assert all(a.gap is None for a in m.associations if a.conn_type != 'D')
    m2, _L = east.build(system='F2D', p_gap=1e-3)
    assert all(a.gap == pytest.approx(1e-3)
               for a in m2.associations if a.conn_type == 'D')


def test_an_open_d_has_no_ties_at_all(built):
    """Not 'few'. None. A D is a pure support: open, it restrains neither
    translation nor rotation, so it contributes no constraint rows."""
    m, L, ms, beams = built
    idx = m._part_index
    d_nodes = {idx[a.node_a] for a in m.associations if a.conn_type == 'D'}
    pairs = east.constraint_pairs(m)
    assert not [p for p in pairs if p[0] in d_nodes]


def test_an_engaged_d_ties_the_perpendicular_only(built):
    """And at the gap edge, not at zero -- that target IS the deadband."""
    m, L, ms, beams = built
    idx = m._part_index
    d_assoc = f2d.d_associations(m)
    engaged = {a.node_a: +1 for a in d_assoc}
    pairs = east.constraint_pairs(m, engaged=engaged)
    for a in d_assoc:
        mine = [p for p in pairs if p[0] == idx[a.node_a]]
        assert [p[2] for p in mine] == [1], 'perpendicular only: no x, no rz'
        assert mine[0][3] == pytest.approx(a.gap)
    back = east.constraint_pairs(m, engaged={a.node_a: -1 for a in d_assoc})
    for a in d_assoc:
        mine = [p for p in back if p[0] == idx[a.node_a]]
        assert mine[0][3] == pytest.approx(-a.gap)


# -- the threshold --------------------------------------------------------

def test_free_separation_is_symmetric_and_scales(built):
    """Two equal supports on a symmetric structure, in the linear regime."""
    m, L, ms, beams = built
    s20 = f2d.free_separation(m, ms, 20e3)
    s200 = f2d.free_separation(m, ms, 200e3)
    assert len(s20) == 2
    a, b = s20.values()
    assert a == pytest.approx(b, rel=1e-9), 'symmetric rig, symmetric load'
    for k in s20:
        assert s200[k] / s20[k] == pytest.approx(10.0, rel=2e-3)
    assert abs(a) == pytest.approx(0.3002e-3, rel=1e-2)


def test_the_threshold_predicts_every_cell(built, swept):
    """The measured free separation decides engagement, at BOTH loads.

    This is the test that makes the sweep a prediction. A gap wider than the
    separation cannot close; a narrower one must. That the same two numbers
    call all ten cells is what says the active set is doing what it claims.
    """
    m, L, ms, beams = built
    thr = {P: abs(next(iter(f2d.free_separation(m, ms, P).values())))
           for P in (20e3, 200e3)}
    for (gap, P), rec in swept.items():
        info = rec[-1]
        shut = all(v != 0 for v in info['engaged'].values())
        assert shut == (gap < thr[P]), (gap, P, info['engaged'])


def test_engagement_is_load_dependent(swept):
    """A 1 mm gap is open at 20 kN and shut at 200 kN. The deadband is a
    property of the gap AND the load, never of the gap alone."""
    assert all(v == 0 for v in swept[(1.0e-3, 20e3)][-1]['engaged'].values())
    assert all(v != 0 for v in swept[(1.0e-3, 200e3)][-1]['engaged'].values())


# -- what engagement does -------------------------------------------------

def test_open_f2d_is_f2_exactly(swept):
    """Not 'close to'. An open D restrains nothing, so the structure IS F2 --
    once F2 is given the two header stations the D connectors force into the
    mesh. Without them the two differ by 3.8e-04 mm, which is the mesh, not
    the joint; the three-way comparison is what separates the two.
    """
    m_st, _L = east.build(system='F2', extra_stations=(0.0, -X_OUTER, X_OUTER))
    ms_st, _b = east.kernel_mesh(m_st)
    for P in (20e3, 200e3):
        U, i_load, _f, _v = east.solve(m_st, ms_st, P)
        d_f2 = U[east.dof(ms_st, i_load, 1)]
        for gap in (5.0e-3, 3.5e-3):            # both above the threshold
            assert _d(swept[(gap, P)]) == pytest.approx(d_f2, rel=1e-12)


def test_open_d_carries_no_force(swept):
    """It cannot. Whatever the connector element's stiffness, an EA end tied
    to nothing leaves it hanging off the pipe with no second load path."""
    m, ms, beams, U, _i, _f, info = swept[(5.0e-3, 200e3)]
    conns = {c['line_id']: c for c in east.connector_forces(m, ms, U)}
    for slot in (1, 5):
        c = conns[f'ST:connector{slot}']
        assert abs(c['axial']) < 1.0
        assert abs(c['shear']) < 1.0
        assert abs(c['M_pipe_end']) < 1.0 and abs(c['M_frame_end']) < 1.0


def test_engagement_stiffens_monotonically(swept):
    """Tighter gap -> the outer supports engage sooner -> the frame spans
    more of the load -> the pipe sags less. Strictly, once past the
    threshold."""
    d = [_d(swept[(g, 200e3)]) for g in f2d.GAPS]
    assert all(b <= a + 1e-12 for a, b in zip(d, d[1:]))
    assert d[0] == pytest.approx(d[1], rel=1e-12), 'both above threshold'
    assert d[-1] < 0.79 * d[0], 'a 0.25 mm gap is worth >20%'


def test_engagement_moves_load_into_the_frame(swept):
    """The deadband REDISTRIBUTES. What leaves the pipe arrives in the frame,
    and that is why the gap is an engineering choice and not a tolerance."""
    _open = swept[(5.0e-3, 200e3)]
    shut = swept[(0.25e-3, 200e3)]
    for rec, expect in ((_open, False), (shut, True)):
        m, ms, beams, U, _i, _f, _info = rec
        _M, sig = east.member_stress(m, ms, U, beams)
        frame = [k for k, e in enumerate(beams) if e.owner == 'ST']
        pipe = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
        if expect:
            assert sig[frame].max() > 100e6
            assert sig[pipe].max() < 170e6
        else:
            assert sig[frame].max() < 5e6
            assert sig[pipe].max() > 175e6


def test_reactions_balance_at_every_gap(swept):
    """Including the engaged ones -- an active set that leaks force would
    show up here first."""
    for (gap, P), rec in swept.items():
        m, ms, beams, U, _i, fixed, _info = rec
        _K, Fint = east.assemble(m, ms, U)
        Ry = sum(Fint[d] for d in fixed if d % 3 == 1)
        assert -Ry == pytest.approx(P, rel=1e-6), (gap, P)


def test_everything_stays_elastic(swept):
    """Connectors included. They are the second most stressed part of the
    model and were once left out of exactly this claim (L010)."""
    for (gap, P), rec in swept.items():
        m, ms, beams, U, _i, _f, _info = rec
        _M, sig = east.member_stress(m, ms, U, beams)
        conn = max(c['sigma'] for c in east.connector_forces(m, ms, U))
        assert max(sig.max(), conn) < east.SIG_YIELD, (gap, P)


def test_the_active_set_settles_without_chatter(swept):
    """L008, pinned. Enforcing u_a - u_b = 0 on an engaged D dragged it back
    to coincidence, released it, and never settled: four flips and a reported
    state that disagreed with the displacement returned. Holding at +/-P_gap
    and releasing on FORCE settles in one."""
    for (gap, P), rec in swept.items():
        info = rec[-1]
        assert info['flips'] <= 1, (gap, P, info['flips'])
        assert info['passes'] <= 2
        assert info['violation'] < 1e-8


def test_constraints_are_satisfied_at_the_gap_edge(swept):
    """An engaged D holds the two sides P_gap apart -- not together."""
    m, ms, beams, U, _i, _f, info = swept[(0.25e-3, 200e3)]
    idx = m._part_index
    for a in f2d.d_associations(m):
        state = info['engaged'][a.node_a]
        assert state != 0
        sep = (U[east.dof(ms, idx[a.node_a], 1)]
               - U[east.dof(ms, idx[a.node_b], 1)])
        assert sep == pytest.approx(state * a.gap, abs=1e-8)


def test_a_shut_d_is_a_roller_not_a_fixed_connection(swept):
    """It ties the perpendicular and nothing else, so it can carry no moment
    at its EA end however tight the gap is. A zero gap would be an F, which
    the component refuses as a different connection system."""
    m, ms, beams, U, _i, _f, _info = swept[(0.25e-3, 200e3)]
    conns = {c['line_id']: c for c in east.connector_forces(m, ms, U)}
    for slot in (1, 5):
        assert abs(conns[f'ST:connector{slot}']['M_frame_end']) < 1e3
        assert abs(conns[f'ST:connector{slot}']['axial']) > 1e3

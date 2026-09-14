"""ILS-EAST on F2D and F1D: the deadband gap, measured both sides of its
threshold, on the two named systems that have one.

These are the first systems whose GEOMETRY differs rather than only their
ties. F2 and PS populate the same two slots, so PS was a tie override on an
F2 model; these have to be built.

WHAT A D IS, and these guard every word of it. A pure support: it restrains
the perpendicular translation and NOTHING else -- not sliding, not rotation --
and only once the two sides have moved P_gap apart. Open, it restrains nothing
at all, so each system with no engagement must BE its base system, not
resemble it.

WHY TWO SYSTEMS AND NOT ONE. Their bases differ in kind. F2 holds the frame at
two points and carries moment between them; F1 holds it at one, at the midspan
of a symmetric fixed-fixed beam where the rotation is zero, so the F transmits
no moment and the frame is a PASSENGER. The deadband therefore does a
different job in each, and the two load paths are different shapes:

    F2D   4 connectors, frame equilibrium over 2 D + 2 F   ->  N_F == N_D
    F1D   3 connectors, frame equilibrium over 2 D + 1 F   ->  N_F == 2 * N_D

THE THRESHOLD IS MEASURED, NOT ASSUMED. With every D open the outer slots move
0.3002 / 3.0041 mm on F2D and 0.9220 / 9.1049 mm on F1D at 20 / 200 kN. Those
numbers predict every engaged/open cell of both sweeps, at both loads, and the
tests below check the prediction rather than the curve.
"""

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import study_east_full as east          # noqa: E402  (tools/, via conftest)
import study_east_deadband as db        # noqa: E402

SYSTEMS = ('F2D', 'F1D')
X_OUTER = db.X_OUTER


@pytest.fixture(scope='module')
def built():
    out = {}
    for name in SYSTEMS:
        m, L = east.build(system=name, p_gap=max(db.gaps_for(name)))
        ms, beams = east.kernel_mesh(m)
        out[name] = (m, L, ms, beams)
    return out


@pytest.fixture(scope='module')
def swept():
    """Every gap of every system, both loads. Each gap is a REBUILD, because
    P_gap is component data and rides on the component, not on the solver."""
    return {name: db.sweep(name) for name in SYSTEMS}


def _d(rec):
    return rec[1]['d_pipe']


def _open_gap(name):
    return max(db.gaps_for(name))


def _tight_gap(name):
    return min(db.gaps_for(name))


# -- the assembly ---------------------------------------------------------

@pytest.mark.parametrize('name,slots,types,counts', [
    ('F2D', [1, 2, 4, 5], ['D', 'D', 'F', 'F'], (49, 44, 8)),
    ('F1D', [1, 3, 5], ['D', 'D', 'F'], (49, 45, 6)),
])
def test_each_system_builds_the_slots_it_names(built, name, slots, types,
                                               counts):
    """A D adds TWO connectors, one at each OUTER slot: F2 -> F2D is 2 -> 4
    and F1 -> F1D is 1 -> 3. F2D has nothing at slot 3; F1D has nothing at
    2 or 4."""
    m, L, ms, beams = built[name]
    conns = [e for e in m.elements if e.connector is not None]
    assert sorted(e.connector.slot for e in conns) == slots
    assert sorted(e.connector.conn_type for e in conns) == types
    n_nodes, n_elems, n_assoc = counts
    assert (m.n_nodes, m.n_elems) == (n_nodes, n_elems)
    assert len(m.associations) == n_assoc


@pytest.mark.parametrize('name', SYSTEMS)
def test_the_outer_slots_force_header_stations(built, name):
    """Both systems put a D at the outer pair, so both mesh the pipeline
    there -- which is the ONLY way their header differs from the base's."""
    m, L, ms, beams = built[name]
    at = {n.index: n for n in m.nodes}
    pipe_s = {round(at[i].s, 6) for e in m.elements if e.owner == 'pipeline'
              for i in (e.n1, e.n2)}
    assert round(X_OUTER, 6) in pipe_s and round(-X_OUTER, 6) in pipe_s


@pytest.mark.parametrize('name', SYSTEMS)
def test_the_d_geometry_is_opt_in_and_says_so(built, name):
    """G9 has not been widened. `build_model` still refuses D by default; the
    study asks for the GEOMETRY only, and every connector it gets that way is
    recorded on the model as unenforced."""
    from slay.model.assemble import AssemblyError, SUPPORTED_CONN_TYPES
    m, L, ms, beams = built[name]
    assert 'D' not in SUPPORTED_CONN_TYPES
    assert len(m.warnings) == 2
    assert all('GEOMETRY ONLY' in w for w in m.warnings)
    with pytest.raises(AssemblyError, match=r"'D'.*not implemented"):
        east.build(system=name, p_gap=1e-3, emit_d=False)


@pytest.mark.parametrize('name', SYSTEMS)
def test_the_gap_is_component_data(built, name):
    """P_gap rides on GD-ST and arrives on the association. It is not a
    solver setting, and it has no default -- a deadband REDISTRIBUTES strain
    and the gap chooses where, so a silent default would make an engineering
    decision on its own. Nothing upstream enforces it (CUN-001, open), so
    every consumer checks it here."""
    m, L, ms, beams = built[name]
    gaps = {a.node_a: a.gap for a in m.associations if a.conn_type == 'D'}
    assert len(gaps) == 2
    assert all(g == pytest.approx(_open_gap(name)) for g in gaps.values())
    assert all(a.gap is None for a in m.associations if a.conn_type != 'D')
    m2, _L = east.build(system=name, p_gap=1e-3)
    assert all(a.gap == pytest.approx(1e-3)
               for a in m2.associations if a.conn_type == 'D')


@pytest.mark.parametrize('name', SYSTEMS)
def test_an_open_d_has_no_ties_at_all(built, name):
    """Not 'few'. None. A D is a pure support: open, it restrains neither
    translation nor rotation, so it contributes no constraint rows."""
    m, L, ms, beams = built[name]
    idx = m._part_index
    d_nodes = {idx[a.node_a] for a in m.associations if a.conn_type == 'D'}
    assert not [p for p in east.constraint_pairs(m) if p[0] in d_nodes]


@pytest.mark.parametrize('name', SYSTEMS)
def test_an_engaged_d_ties_the_perpendicular_only(built, name):
    """And at the gap edge, not at zero -- that target IS the deadband."""
    m, L, ms, beams = built[name]
    idx = m._part_index
    d_assoc = db.d_associations(m)
    pairs = east.constraint_pairs(m, engaged={a.node_a: +1 for a in d_assoc})
    for a in d_assoc:
        mine = [p for p in pairs if p[0] == idx[a.node_a]]
        assert [p[2] for p in mine] == [1], 'perpendicular only: no x, no rz'
        assert mine[0][3] == pytest.approx(a.gap)
    back = east.constraint_pairs(m, engaged={a.node_a: -1 for a in d_assoc})
    for a in d_assoc:
        assert [p for p in back
                if p[0] == idx[a.node_a]][0][3] == pytest.approx(-a.gap)


def test_the_load_lands_on_the_header_not_the_connector():
    """F1D's single F sits at slot 3, which IS the layout midpoint, so the
    connector claims that station. Two nodes then sit at (s=0, y=0) in
    different passes, deliberately unmerged -- the header's and the
    connector's C-P. Loading the wrong one would push the load straight into
    the frame and bypass the pipe."""
    m, _L = east.build(system='F1D', p_gap=1e-3)
    at = {n.index: n for n in m.nodes}
    here = [n for n in m.nodes if abs(n.s) < 1e-9 and abs(n.y) < 1e-9]
    assert len(here) == 2, 'the header node and the connector C-P node'
    header = {i for e in m.elements if e.owner == 'pipeline'
              for i in (e.n1, e.n2)}
    assert len([n for n in here if n.index in header]) == 1
    ms, _b = east.kernel_mesh(m)
    _U, i_load, _f, _v = east.solve(m, ms, 20e3)
    assert i_load in header
    assert at[i_load].part_id != 'CST3-P'


# -- the threshold --------------------------------------------------------

@pytest.mark.parametrize('name,expect_mm', [('F2D', 0.3002), ('F1D', 0.9220)])
def test_free_separation_is_symmetric_and_the_right_size(built, name,
                                                         expect_mm):
    """Two equal supports on a symmetric structure. F1D's frame travels three
    times as far: nothing holds it at the inner slots, so the outer pair has
    further to go before it touches."""
    m, L, ms, beams = built[name]
    a, b = db.free_separation(m, ms, 20e3).values()
    assert a == pytest.approx(b, rel=1e-9), 'symmetric rig, symmetric load'
    assert abs(a) * 1e3 == pytest.approx(expect_mm, rel=1e-3)


def test_f1d_is_the_one_that_is_measurably_nonlinear(built):
    """A 10x load does NOT give 10x separation on F1D, and that is the right
    answer rather than a tolerance to widen.

    F1D sags 65.47 mm at 200 kN against F2D's 49.43 -- a third further -- and
    the membrane term goes as the deflection, so the softer system is the one
    far enough out for it to show. Separation tracks deflection in both, which
    is what says the shortfall is the pipe stiffening and not the supports
    doing something. Pinned because a future change that quietly linearised
    the solve would make F1D read 10.000 and look like an improvement.
    """
    ratios = {}
    for name in SYSTEMS:
        m, L, ms, beams = built[name]
        s20 = db.free_separation(m, ms, 20e3)
        s200 = db.free_separation(m, ms, 200e3)
        k = next(iter(s20))
        U20, i, _f, _v = east.solve(m, ms, 20e3)
        U200, _i, _f, _v = east.solve(m, ms, 200e3)
        ratios[name] = (s200[k] / s20[k],
                        U200[east.dof(ms, i, 1)] / U20[east.dof(ms, i, 1)])

    assert ratios['F2D'][0] == pytest.approx(10.0, rel=1e-3), 'F2D is linear'
    assert ratios['F2D'][1] == pytest.approx(10.0, rel=1e-3)
    assert 9.8 < ratios['F1D'][0] < 9.95, 'F1D stiffens, ~1.3% short of 10x'
    assert 9.8 < ratios['F1D'][1] < 9.95
    for name in SYSTEMS:
        sep, defl = ratios[name]
        assert sep == pytest.approx(defl, rel=2e-3), 'separation tracks sag'
    assert ratios['F1D'][1] < ratios['F2D'][1], 'the softer one bends more'


@pytest.mark.parametrize('name', SYSTEMS)
def test_the_threshold_predicts_every_cell(built, swept, name):
    """The measured free separation decides engagement, at BOTH loads.

    This is the test that makes the sweep a prediction. A gap wider than the
    separation cannot close; a narrower one must. That the same two numbers
    call all ten cells of a system is what says the active set is doing what
    it claims.
    """
    m, L, ms, beams = built[name]
    thr = {P: abs(next(iter(db.free_separation(m, ms, P).values())))
           for P in (20e3, 200e3)}
    for (gap, P), rec in swept[name].items():
        info = rec[1]
        shut = '.' not in info['state']
        assert shut == (gap < thr[P]), (name, gap, P, info['state'])


@pytest.mark.parametrize('name,gap', [('F2D', 1.0e-3), ('F1D', 3.0e-3)])
def test_engagement_is_load_dependent(swept, name, gap):
    """One gap, open at 20 kN and shut at 200 kN. The deadband is a property
    of the gap AND the load, never of the gap alone."""
    assert '.' in swept[name][(gap, 20e3)][1]['state']
    assert '.' not in swept[name][(gap, 200e3)][1]['state']


# -- what engagement does -------------------------------------------------

@pytest.mark.parametrize('name,base', [('F2D', 'F2'), ('F1D', 'F1')])
def test_open_is_the_base_system_exactly(swept, name, base):
    """Not 'close to'. An open D restrains nothing, so the structure IS the
    base -- once the base is given the two header stations the D connectors
    force into the mesh. Without them they differ by a few 1e-04 mm, which is
    the mesh, not the joint; the three-way comparison is what separates them.
    """
    m_st, _L = east.build(system=base,
                          extra_stations=(0.0, -X_OUTER, X_OUTER))
    ms_st, _b = east.kernel_mesh(m_st)
    gaps = db.gaps_for(name)
    for P in (20e3, 200e3):
        U, i_load, _f, _v = east.solve(m_st, ms_st, P)
        d_base = U[east.dof(ms_st, i_load, 1)]
        for gap in gaps[:2]:                     # both above the threshold
            assert _d(swept[name][(gap, P)]) == pytest.approx(d_base,
                                                              rel=1e-12)


@pytest.mark.parametrize('name', SYSTEMS)
def test_open_d_carries_no_force(swept, name):
    """It cannot. Whatever the connector element's stiffness, an EA end tied
    to nothing leaves it hanging off the pipe with no second load path."""
    U, r, m, ms, _b = swept[name][(_open_gap(name), 200e3)]
    conns = {c['line_id']: c for c in east.connector_forces(m, ms, U)}
    for e in m.elements:
        if e.connector is None or e.connector.conn_type != 'D':
            continue
        c = conns[e.line_id]
        for k in ('axial', 'shear', 'M_pipe_end', 'M_frame_end'):
            assert abs(c[k]) < 1.0, (name, e.line_id, k)


@pytest.mark.parametrize('name', SYSTEMS)
def test_engagement_stiffens_monotonically(swept, name):
    """Tighter gap -> the outer supports engage sooner -> the frame spans
    more of the load -> the pipe sags less. Flat above the threshold."""
    gaps = db.gaps_for(name)
    d = [_d(swept[name][(g, 200e3)]) for g in gaps]
    assert all(b <= a + 1e-12 for a, b in zip(d, d[1:]))
    assert d[0] == pytest.approx(d[1], rel=1e-12), 'both above threshold'


def test_f1d_starts_softer_and_gains_more(swept):
    """The comparison, and the reason for it. F1 is a passenger: at the
    midspan of a symmetric fixed-fixed beam the rotation is zero, so its
    single F transmits no moment and the pipe is at its bare-beam value. F2
    already shields the pipe before any deadband closes. So F1D starts
    softer, has three times as far to travel before its supports touch, and
    when they do they are the only thing making its frame work at all."""
    o2, t2 = [_d(swept['F2D'][(g, 200e3)]) * 1e3
              for g in (_open_gap('F2D'), _tight_gap('F2D'))]
    o1, t1 = [_d(swept['F1D'][(g, 200e3)]) * 1e3
              for g in (_open_gap('F1D'), _tight_gap('F1D'))]
    assert o1 > o2, 'F1D starts softer'
    assert (1 - t1/o1) > (1 - t2/o2), 'and the deadband buys it more'
    assert t1 > t2, 'but it does not overtake F2D'


def test_f1_is_a_passenger_and_every_f1d_connector_is_a_strut(swept):
    """Zero moment in EVERY F1D connector at EVERY gap. The two D are rollers
    by construction; the single F is at the symmetric midspan, where the
    relative rotation is zero, so it cannot build a moment either."""
    for (gap, P), rec in swept['F1D'].items():
        U, _r, m, ms, _b = rec
        for c in east.connector_forces(m, ms, U):
            assert abs(c['M_pipe_end']) < 1.0, (gap, P, c['line_id'])
            assert abs(c['M_frame_end']) < 1.0, (gap, P, c['line_id'])
            assert abs(c['shear']) < 1.0, (gap, P, c['line_id'])


def test_the_load_path_has_the_shape_the_layout_implies(swept):
    """Vertical equilibrium of the frame, read off the connector axials.

    F2D hangs it on 2 D and 2 F, symmetric, so each F carries what each D
    does. F1D hangs it on 2 D and ONE F, so that F carries both. This is the
    cheapest statement that the load actually goes where the layout says, and
    it differs between the two systems, so it cannot pass by accident.
    """
    for name, ratio in (('F2D', 1.0), ('F1D', 2.0)):
        for P in (20e3, 200e3):
            r = swept[name][(_tight_gap(name), P)][1]
            assert r['N_D'] > 1e3, (name, P)
            assert r['N_F'] / r['N_D'] == pytest.approx(ratio, rel=1e-6)


@pytest.mark.parametrize('name', SYSTEMS)
def test_engagement_moves_load_into_the_frame(swept, name):
    """The deadband REDISTRIBUTES. What leaves the pipe arrives in the frame,
    and that is why the gap is an engineering choice and not a tolerance."""
    for gap, engaged in ((_open_gap(name), False), (_tight_gap(name), True)):
        U, _r, m, ms, beams = swept[name][(gap, 200e3)]
        _M, sig = east.member_stress(m, ms, U, beams)
        frame = [k for k, e in enumerate(beams) if e.owner == 'ST']
        pipe = [k for k, e in enumerate(beams) if e.owner == 'pipeline']
        if engaged:
            assert sig[frame].max() > 100e6
            assert sig[pipe].max() < 175e6
        else:
            assert sig[frame].max() < 5e6
            assert sig[pipe].max() > 175e6


@pytest.mark.parametrize('name', SYSTEMS)
def test_reactions_balance_at_every_gap(swept, name):
    """Including the engaged ones -- an active set that leaks force would
    show up here first."""
    for (gap, P), rec in swept[name].items():
        U, _r, m, ms, _b = rec
        _K, Fint = east.assemble(m, ms, U)
        # the restraint set, not a throwaway solve. `east.solve(..., 
        # max_iter=1)` used to be the way to get it, which worked only while
        # a loop that ran out of iterations stayed silent about it.
        fixed, _load = east._restraints(m, ms)
        Ry = sum(Fint[d] for d in fixed if d % 3 == 1)
        assert -Ry == pytest.approx(P, rel=1e-6), (name, gap, P)


@pytest.mark.parametrize('name', SYSTEMS)
def test_everything_stays_elastic(swept, name):
    """Connectors included. They are the second most stressed part of the
    model and were once left out of exactly this claim (L010)."""
    for (gap, P), rec in swept[name].items():
        U, _r, m, ms, beams = rec
        _M, sig = east.member_stress(m, ms, U, beams)
        conn = max(c['sigma'] for c in east.connector_forces(m, ms, U))
        assert max(sig.max(), conn) < east.SIG_YIELD, (name, gap, P)


@pytest.mark.parametrize('name', SYSTEMS)
def test_the_active_set_settles_without_chatter(swept, name):
    """L008, pinned. Enforcing u_a - u_b = 0 on an engaged D dragged it back
    to coincidence, released it, and never settled: four flips and a reported
    state that disagreed with the displacement returned. Holding at +/-P_gap
    and releasing on FORCE settles in one."""
    for (gap, P), rec in swept[name].items():
        r = rec[1]
        assert r['flips'] <= 1, (name, gap, P, r['flips'])
        assert r['viol'] < 1e-8


@pytest.mark.parametrize('name', SYSTEMS)
def test_constraints_are_satisfied_at_the_gap_edge(swept, name):
    """An engaged D holds the two sides P_gap apart -- not together."""
    U, r, m, ms, _b = swept[name][(_tight_gap(name), 200e3)]
    idx = m._part_index
    state = {k: v for k, v in zip(
        [a.node_a for a in db.d_associations(m)],
        [{'+': 1, '-': -1, '.': 0}[ch] for ch in r['state']])}
    for a in db.d_associations(m):
        assert state[a.node_a] != 0
        sep = (U[east.dof(ms, idx[a.node_a], 1)]
               - U[east.dof(ms, idx[a.node_b], 1)])
        assert sep == pytest.approx(state[a.node_a] * a.gap, abs=1e-8)


@pytest.mark.parametrize('name', SYSTEMS)
def test_a_shut_d_is_a_roller_not_a_fixed_connection(swept, name):
    """It ties the perpendicular and nothing else, so it can carry no moment
    at its EA end however tight the gap is. A zero gap would be an F, which
    the component refuses as a different connection system."""
    U, _r, m, ms, _b = swept[name][(_tight_gap(name), 200e3)]
    conns = {c['line_id']: c for c in east.connector_forces(m, ms, U)}
    for e in m.elements:
        if e.connector is None or e.connector.conn_type != 'D':
            continue
        assert abs(conns[e.line_id]['M_frame_end']) < 1e3
        assert abs(conns[e.line_id]['axial']) > 1e3

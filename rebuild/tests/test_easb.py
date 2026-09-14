"""ILS-EASB: the zero-length connector, and the same systems as EA-ST.

EA-SB is the archetype the connector rule was written for. GD-ST stands its
frame 0.6096 m off the pipe; GD-SB sets `P_vt = 0`, putting its top chord ON
the pipe centreline, so EVERY connector is zero length. That is the default
here, not an edge case, and the rule -- stiffness of a 1 x OD length of
pipeline, never derived from length -- is what makes it ordinary.

WHAT THESE GUARD, beyond "it runs":

  the zero-length element is a relative-DOF spring, exactly three rigid-body
  modes, and its three stiffnesses come from the rule rather than from a
  geometry it does not have;

  seven node pairs are coincident and stay DISTINCT -- this is the archetype
  that found the kernel's coordinate-keyed merge (L001);

  the frame acts COMPOSITELY: zero vertical force in the connectors, equal
  and opposite horizontal force and moment;

  every system EA-ST was taken through runs here on the same code path, and
  the joint TYPE still decides the answer, not the connector's geometry.
"""

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import study_east_full as east          # noqa: E402  (tools/, via conftest)
import study_east_deadband as db        # noqa: E402
import study_easb as sb                 # noqa: E402
from study_connectors import (connector_k6, ZERO_LEN_TOL,   # noqa: E402
                              OD, E_PIPE, A_PIPE, I_PIPE)

ARCH = 'ILS-EASB'


@pytest.fixture(scope='module')
def built():
    m, L = east.build(archetype=ARCH, system='F2')
    ms, beams = east.kernel_mesh(m)
    return m, L, ms, beams


@pytest.fixture(scope='module')
def solved(built):
    m, L, ms, beams = built
    return {P: east.solve(m, ms, P) for P in (20e3, 200e3)}


# -- the zero-length connector element ------------------------------------

def test_the_zero_length_element_is_a_relative_dof_spring():
    """Equal translation and equal rotation must both cost nothing. Coincident
    nodes have no moment arm, so a rigid rotation moves neither of them -- the
    thing that makes all three relative freedoms genuine deformations."""
    K = connector_k6(0.0, 0.0)
    assert np.allclose(K, K.T)
    for u in ([1, 0, 0, 1, 0, 0], [0, 1, 0, 0, 1, 0], [0, 0, 1, 0, 0, 1]):
        assert np.abs(K @ np.array(u, float)).max() == 0.0
    w = np.linalg.eigvalsh(K)
    assert int(np.sum(np.abs(w) < 1e-6 * np.abs(w).max())) == 3


def test_the_three_stiffnesses_come_from_the_rule(): 
    """Pass 4's rule fixes the magnitude at a 1 x OD length of pipeline. The
    element has no length of its own to derive anything from -- that is the
    whole reason the rule is not length-derived."""
    K = connector_k6(0.0, 0.0)
    EA, EI = E_PIPE * A_PIPE, E_PIPE * I_PIPE
    k_ax, k_tr, k_rot = EA / OD, 12 * EI / OD**3, EI / OD
    # nominal axis is +y, so axial acts on the y row and transverse on s
    assert K[1, 1] == pytest.approx(k_ax, rel=1e-12)
    assert K[0, 0] == pytest.approx(k_tr, rel=1e-12)
    assert K[2, 2] == pytest.approx(k_rot, rel=1e-12)
    assert K[0, 3] == pytest.approx(-k_tr, rel=1e-12)
    assert K[1, 4] == pytest.approx(-k_ax, rel=1e-12)
    assert K[2, 5] == pytest.approx(-k_rot, rel=1e-12)


def test_the_rotation_stiffness_is_the_relative_mode_not_one_end():
    """EI/L0, not 4EI/L0. With both ends' translations held and a relative
    rotation phi imposed as (-phi/2, +phi/2), the strain energy of a beam is
    (EI/L0) phi^2 / 2. 4EI/L0 is the stiffness against ONE end's rotation
    with the other held, which is not a relative mode and would make a
    zero-length connector four times too stiff in bending."""
    K = connector_k6(0.0, 0.0)
    EI = E_PIPE * I_PIPE
    u = np.array([0, 0, -0.5, 0, 0, 0.5], float)      # relative rotation of 1
    energy = 0.5 * u @ K @ u
    assert energy == pytest.approx(0.5 * EI / OD, rel=1e-12)
    assert K[2, 2] != pytest.approx(4 * EI / OD, rel=1e-3)


def test_the_axis_is_the_pvt_direction_and_its_sign_does_not_matter():
    """A connector runs from the pipe to the structure -- the direction P_vt
    measures. P_vt = 0 means the structure sits ON the centreline, not that
    the connector points somewhere else."""
    up, down = connector_k6(0.0, 0.0, axis=(0.0, 1.0)), \
        connector_k6(0.0, 0.0, axis=(0.0, -1.0))
    assert np.allclose(up, down)
    along = connector_k6(0.0, 0.0, axis=(1.0, 0.0))
    assert not np.allclose(up, along), 'the axis is not decorative'
    with pytest.raises(ValueError, match='nominal axis'):
        connector_k6(0.0, 0.0, axis=(0.0, 0.0))


def test_a_nonzero_connector_still_takes_the_corotational_form():
    """The zero-length branch is a branch, not a replacement. EA-ST is
    unaffected, and its published numbers are the proof elsewhere."""
    K = connector_k6(0.0, 0.6096)
    w = np.linalg.eigvalsh(K)
    assert int(np.sum(np.abs(w) < 1e-6 * np.abs(w).max())) == 3
    assert not np.allclose(K, connector_k6(0.0, 0.0))


# -- the assembly ---------------------------------------------------------

def test_the_archetype_assembles_and_every_connector_is_zero_length(built):
    m, L, ms, beams = built
    assert east.ea_owner(m) == 'SB'
    assert (m.n_nodes, m.n_elems) == (49, 46)
    conns = [e for e in m.elements if e.connector is not None]
    assert len(conns) == 2
    assert all(e.connector.length == 0.0 for e in conns)
    assert all(e.connector.stiffness == '1xOD_pipeline' for e in conns)
    assert len(m.associations) == 4
    assert L == pytest.approx(20.1280, abs=1e-4)


def test_seven_node_pairs_are_coincident_and_all_stay_distinct(built):
    """L001, on the archetype that found it. GD-SB's slot nodes sit on the
    pipe centreline, so pipe, connector and structure nodes land on the same
    point. Coincidence is legal; welding is not."""
    m, L, ms, beams = built
    pairs = sb.coincident_pairs(m)
    assert len(pairs) == 7
    assert all(i != j for (i, j, _s, _y) in pairs)
    assert len({n.index for n in m.nodes}) == m.n_nodes
    assert ms.n_nodes == m.n_nodes, 'the kernel must not merge them either'
    assert sorted(east.dof(ms, i, 0) for i in range(m.n_nodes)) == \
        sorted(3 * k for k in range(m.n_nodes))


def test_no_warnings_on_the_plain_archetype(built):
    """F2 needs no geometry-only grant -- it is F and W only."""
    m, L, ms, beams = built
    assert m.warnings == []


# -- it carries load ------------------------------------------------------

def test_it_solves_and_reactions_balance(built, solved):
    m, L, ms, beams = built
    for P in (20e3, 200e3):
        U, _i, fixed, viol = solved[P]
        _K, Fint = east.assemble(m, ms, U)
        Ry = sum(Fint[d] for d in fixed if d % 3 == 1)
        assert -Ry == pytest.approx(P, rel=1e-6)
        assert viol < 1e-8


def test_the_ils_stiffens_the_pipe(built, solved):
    """The comparison is the result. If a zero-length connector transferred
    nothing, the pipe would sit at its bare value."""
    m, L, ms, beams = built
    bare = sb._bare(L, 200e3)
    U, i_load, _f, _v = solved[200e3]
    d = U[east.dof(ms, i_load, 1)]
    assert d == pytest.approx(70.39454e-3, rel=1e-6)
    assert d < 0.85 * bare


def test_everything_stays_elastic(built, solved):
    m, L, ms, beams = built
    for P in (20e3, 200e3):
        U, _i, _f, _v = solved[P]
        _M, sig = east.member_stress(m, ms, U, beams)
        conn = max(c['sigma'] for c in east.connector_forces(m, ms, U))
        assert max(sig.max(), conn) < east.SIG_YIELD


def test_the_connectors_act_compositely(built, solved):
    """Zero vertical force, equal and opposite horizontal force and moment.

    GD-SB's top chord is coincident with the pipe and its body is below, so
    the two bend as one deep section and the connectors transfer the interface
    shear. The vertical force is zero for the same reason it is on EA-ST F2 --
    two mirror-image connectors that must sum to zero are each zero.
    """
    m, L, ms, beams = built
    U, _i, _f, _v = solved[200e3]
    cf = sorted(east.connector_forces(m, ms, U), key=lambda c: c['line_id'])
    assert len(cf) == 2
    for c in cf:
        assert c['length'] == 0.0
        assert abs(c['axial']) < 1.0, 'no vertical force'
    assert cf[0]['shear'] == pytest.approx(-cf[1]['shear'], rel=1e-9)
    assert abs(cf[0]['shear']) == pytest.approx(112.343e3, rel=1e-4)
    assert cf[0]['M_frame_end'] == pytest.approx(-cf[1]['M_frame_end'],
                                                 rel=1e-9)
    assert abs(cf[0]['M_frame_end']) == pytest.approx(281.528e3, rel=1e-4)


def test_ps_is_a_passenger_here_too(built):
    """The joint TYPE decides whether the frame works, not the connector's
    geometry. A pin and a roller hold a rigid frame statically determinately
    against any motion of those points, so it can never be forced to deform --
    zero length or not."""
    m, L, ms, beams = built
    U, i_load, _f, _v = east.solve(m, ms, 200e3, layout='PS')
    d = U[east.dof(ms, i_load, 1)]
    assert d == pytest.approx(sb._bare(L, 200e3), rel=0.03)
    ea = east.ea_owner(m)
    _M, sig = east.member_stress(m, ms, U, beams)
    frame = [k for k, e in enumerate(beams) if e.owner == ea]
    assert sig[frame].max() < 1e6, 'the frame carries nothing'
    for c in east.connector_forces(m, ms, U):
        assert abs(c['M_pipe_end']) < 1e3 and abs(c['M_frame_end']) < 1e3


# -- the deadband systems, on this archetype ------------------------------

@pytest.fixture(scope='module')
def swept():
    return {name: db.sweep(name, ARCH) for name in ('F2D', 'F1D')}


@pytest.mark.parametrize('name,base,counts', [
    ('F2D', 'F2', (53, 48, 8)),
    ('F1D', 'F1', (53, 49, 6)),
])
def test_the_deadband_systems_build_here(name, base, counts):
    gaps = db.gaps_for(name, ARCH)
    m, _L = east.build(archetype=ARCH, system=name, p_gap=max(gaps))
    assert (m.n_nodes, m.n_elems, len(m.associations)) == counts
    assert all(e.connector.length == 0.0
               for e in m.elements if e.connector is not None)
    assert len(m.warnings) == 2 and all('GEOMETRY ONLY' in w
                                        for w in m.warnings)


@pytest.mark.parametrize('name,expect', [('F2D', 3.6669), ('F1D', 9.9751)])
def test_the_thresholds_are_bigger_than_ea_st(name, expect):
    """EA-SB's frame is longer and hangs below a top chord on the centreline,
    so its outer slots travel further before they touch."""
    gaps = db.gaps_for(name, ARCH)
    m, _L = east.build(archetype=ARCH, system=name, p_gap=max(gaps))
    ms, _b = east.kernel_mesh(m)
    sep = db.free_separation(m, ms, 200e3)
    a, b = sep.values()
    assert a == pytest.approx(b, rel=1e-9)
    assert abs(a) * 1e3 == pytest.approx(expect, rel=1e-3)
    m2, _L2 = east.build(archetype='ILS-EAST', system=name, p_gap=max(gaps))
    ms2, _b2 = east.kernel_mesh(m2)
    east_sep = abs(next(iter(db.free_separation(m2, ms2, 200e3).values())))
    assert abs(a) > east_sep


@pytest.mark.parametrize('name', ('F2D', 'F1D'))
def test_the_threshold_predicts_every_cell(swept, name):
    gaps = db.gaps_for(name, ARCH)
    m, _L = east.build(archetype=ARCH, system=name, p_gap=max(gaps))
    ms, _b = east.kernel_mesh(m)
    thr = {P: abs(next(iter(db.free_separation(m, ms, P).values())))
           for P in (20e3, 200e3)}
    for (gap, P), rec in swept[name].items():
        assert ('.' not in rec[1]['state']) == (gap < thr[P]), (gap, P)


@pytest.mark.parametrize('name,base', [('F2D', 'F2'), ('F1D', 'F1')])
def test_open_is_the_base_system_exactly(swept, name, base):
    """An open D restrains nothing, so the structure IS the base -- once the
    base is given the two header stations the D connectors force into the
    mesh.

    The bound is 0.1 nm, not zero. The D system carries four more DOF (two
    coincident node pairs joined by a zero-length spring), so Newton walks a
    slightly different path to the same answer and the two agree at the
    solver's own tolerance rather than bit for bit -- measured at 0.002 nm on
    a 7 mm deflection. Anything above the nanometre would be a load path.
    """
    X = db.X_OUTER
    m_st, _L = east.build(archetype=ARCH, system=base,
                          extra_stations=(0.0, -X, X))
    ms_st, _b = east.kernel_mesh(m_st)
    gaps = db.gaps_for(name, ARCH)
    for P in (20e3, 200e3):
        U, i_load, _f, _v = east.solve(m_st, ms_st, P)
        d_base = U[east.dof(ms_st, i_load, 1)]
        for gap in gaps[:2]:
            assert swept[name][(gap, P)][1]['d_pipe'] == \
                pytest.approx(d_base, abs=1e-10)


@pytest.mark.parametrize('name,ratio', [('F2D', 1.0), ('F1D', 2.0)])
def test_the_load_path_has_the_shape_the_layout_implies(swept, name, ratio):
    """Same statement as on EA-ST, and it must survive the geometry change:
    F2D hangs the frame on 2 D + 2 F, F1D on 2 D + 1 F."""
    gap = min(db.gaps_for(name, ARCH))
    for P in (20e3, 200e3):
        r = swept[name][(gap, P)][1]
        assert r['N_D'] > 1e3
        assert r['N_F'] / r['N_D'] == pytest.approx(ratio, rel=1e-6)


@pytest.mark.parametrize('name', ('F2D', 'F1D'))
def test_engagement_stiffens_monotonically_and_settles(swept, name):
    gaps = db.gaps_for(name, ARCH)
    d = [swept[name][(g, 200e3)][1]['d_pipe'] for g in gaps]
    assert all(b <= a + 1e-12 for a, b in zip(d, d[1:]))
    assert d[0] == pytest.approx(d[1], rel=1e-12)
    for (_gap, _P), rec in swept[name].items():
        assert rec[1]['flips'] <= 1
        assert rec[1]['viol'] < 1e-8


def test_the_deadband_relieves_the_f_connectors_here(swept):
    """The opposite of EA-ST, and worth pinning because it is a sign flip.

    On EA-ST F2D the F connectors' moment RISES as the D engage (9.29 ->
    179.30 kN.m): the outer supports extend a frame that works by bending.
    On EA-SB it FALLS (281.53 -> 20.40): the two F connectors were carrying
    the whole composite interface on their own, and the D pair takes that
    over. Same system, same rule, opposite trend -- because the geometry the
    zero-length connector comes from is a different load path.
    """
    gaps = db.gaps_for('F2D', ARCH)
    m_open = swept['F2D'][(gaps[0], 200e3)][1]
    m_shut = swept['F2D'][(gaps[-1], 200e3)][1]
    assert m_open['M_F'] == pytest.approx(281.528e3, rel=1e-4)
    assert m_shut['M_F'] < 0.1 * m_open['M_F']

    east_open = db.sweep('F2D', 'ILS-EAST')[(5.0e-3, 200e3)][1]
    east_shut = db.sweep('F2D', 'ILS-EAST')[(0.25e-3, 200e3)][1]
    assert east_shut['M_F'] > 10 * east_open['M_F'], 'EA-ST goes the other way'


# -- against EA-ST --------------------------------------------------------

def test_ea_sb_shields_its_pipe_less_than_ea_st():
    """Different spans, so the fraction of each one's OWN bare pipe is the
    only fair comparison. GD-ST stands its frame off the pipe on a 0.61 m
    lever; GD-SB lies along it. The lever is what turns a frame into a second
    flange."""
    frac = {}
    for arch in ('ILS-EAST', ARCH):
        m, L = east.build(archetype=arch, system='F2')
        ms, _b = east.kernel_mesh(m)
        U, i_load, _f, _v = east.solve(m, ms, 200e3)
        frac[arch] = U[east.dof(ms, i_load, 1)] / sb._bare(L, 200e3)
    assert frac['ILS-EAST'] == pytest.approx(0.745, abs=0.01)
    assert frac[ARCH] == pytest.approx(0.824, abs=0.01)
    assert frac[ARCH] > frac['ILS-EAST']

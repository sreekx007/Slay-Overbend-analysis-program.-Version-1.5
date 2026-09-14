"""slay.solve -- the machinery that was measured in tools/, now in the package.

Every number these assert was FIRST produced by a study under `tools/` and is
reproduced here through `slay.physics.connector`, `slay.solve.constraints`,
`slay.solve.penalty`, `slay.solve.kernel` and `slay.solve.newton`. That is
the point of the module: there is one implementation, and a package
regression now fails a test instead of only changing a figure nobody reruns.

WHAT LANDED, and what did not. The penalty MPC assembler, the
prescribed-stiffness connector element (both branches), the deadband active
set, and a bounded Newton loop. NOT `solve(problem)` -- `Problem` is T4's
artifact and does not exist yet, so this takes a `Model`, a load and a
restraint set directly. T5 wraps it.
"""

import math

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

import component_spec as cs                      # noqa: E402
import study_east_full as east                   # noqa: E402  (tools/, rig)
from slay.model.parts import TIES_OPEN, TIES_SHUT  # noqa: E402
from slay.physics.connector import (              # noqa: E402
    connector_k6, section_properties, ZERO_LEN_TOL, NOMINAL_AXIS)
from slay.solve import constraints as cons        # noqa: E402
from slay.solve import kernel as kern             # noqa: E402
from slay.solve import newton                     # noqa: E402
from slay.solve import penalty as pen             # noqa: E402

import config                                     # noqa: E402


# ---------------------------------------------------------------------------
# a rig, built the way T4 will build one
# ---------------------------------------------------------------------------

def rig(model, P, layout=None, load_s=0.0, **kw):
    """Fixed at both pipe ends, loaded at one header station. Returns the
    deflection under the load and the full result."""
    ms, _beams = kern.mesh(model)
    ends = [min(model.nodes, key=lambda n: n.s),
            max(model.nodes, key=lambda n: n.s)]
    fixed = [kern.dof(ms, n.index, k) for n in ends for k in (0, 1, 2)]
    at = {n.index: n for n in model.nodes}
    header = {i for e in model.elements if e.owner == 'pipeline'
              for i in (e.n1, e.n2)}
    here = [i for i in header if abs(at[i].s - load_s) <= 1e-6]
    assert len(here) == 1, f'{len(here)} header nodes at s={load_s}'
    load = here[0]

    override = None
    if layout:
        slot_of = {at[e.n2].part_id: e.connector.slot
                   for e in model.elements if e.connector is not None}
        override = cons.layout_ties(cs.NAMED_CONNECTION_SYSTEMS[layout],
                                    slot_of)
    r = newton.solve(model, ms, {kern.dof(ms, load, 1): P}, fixed,
                     ties_override=override, **kw)
    return r.U[kern.dof(ms, load, 1)], r, ms, fixed


# ---------------------------------------------------------------------------
# the connector element
# ---------------------------------------------------------------------------

def test_stiffness_never_comes_from_length():
    """Pass 4's rule, in the one place it could be violated."""
    A, I = section_properties()
    EA, EI = config.STEEL_E * A, config.STEEL_E * I
    OD = config.OD_PIPE_DEF
    for L in (0.5 * OD, OD, 5.0 * OD):
        K = connector_k6(0.0, L)
        assert K[1, 1] == pytest.approx(EA / OD, rel=1e-9)
        assert K[2, 2] == pytest.approx(4 * EI / OD, rel=1e-9)


@pytest.mark.parametrize('dx,dy', [(0.0, 0.6096), (0.0, 0.0), (0.2032, 0.0)])
def test_every_connector_is_self_equilibrating(dx, dy):
    """Exactly three rigid-body modes and no force from any of them. The
    first version failed this: built at L = OD while spanning L_real, it left
    ILS-EAST 146 kN.m short of moment equilibrium (L012)."""
    K = connector_k6(dx, dy)
    assert np.allclose(K, K.T)
    w = np.linalg.eigvalsh(K)
    assert int(np.sum(np.abs(w) < 1e-6 * np.abs(w).max())) == 3
    L = math.hypot(dx, dy)
    for rigid in (np.array([1, 0, 0, 1, 0, 0.]),
                  np.array([0, 1, 0, 0, 1, 0.]),
                  np.array([0, 0, 1, -dy, dx, 1.])):
        assert np.abs(K @ rigid).max() < 1e-6 * max(L, 1.0) * abs(K).max()


def test_the_zero_length_branch_is_the_rule_in_a_different_form():
    """A beam's transverse stiffness is entirely a moment arm, and at L = 0
    there is none -- so the element is a relative-DOF spring, with the three
    stiffnesses still taken at L0 = OD."""
    A, I = section_properties()
    EA, EI = config.STEEL_E * A, config.STEEL_E * I
    OD = config.OD_PIPE_DEF
    K = connector_k6(0.0, 0.0)
    assert K[1, 1] == pytest.approx(EA / OD, rel=1e-12)         # nominal axis
    assert K[0, 0] == pytest.approx(12 * EI / OD**3, rel=1e-12)
    assert K[2, 2] == pytest.approx(EI / OD, rel=1e-12)
    u = np.array([0, 0, -0.5, 0, 0, 0.5], float)                # relative rz
    assert 0.5 * u @ K @ u == pytest.approx(0.5 * EI / OD, rel=1e-12)
    assert np.allclose(K, connector_k6(0.0, 0.0, axis=(0.0, -1.0)))
    with pytest.raises(ValueError, match='nominal axis'):
        connector_k6(0.0, 0.0, axis=(0.0, 0.0))


# ---------------------------------------------------------------------------
# constraint rows
# ---------------------------------------------------------------------------

def test_rows_follow_the_declared_ties():
    m, _L = east.build(archetype='ILS-EAST', system='F2')
    idx = m._part_index
    rows = cons.constraint_rows(m)
    assert len(rows) == 4 * 3, 'four all-DOF associations'
    assert all(t == 0.0 for (_a, _b, _c, t) in rows)
    ps = cons.layout_ties(cs.NAMED_CONNECTION_SYSTEMS['PS'],
                          {a.node_a: s for a, s in
                           zip([a for a in m.associations
                                if a.conn_type == 'F'], (2, 4))})
    tied = {}
    for (na, _nb, comp, _t) in cons.constraint_rows(m, ties_override=ps):
        tied.setdefault(na, []).append(comp)
    ea = [idx[a.node_a] for a in m.associations if a.conn_type == 'F']
    assert sorted(tied[ea[0]]) == [0, 1], 'P is a pin'
    assert sorted(tied[ea[1]]) == [1], 'S is a roller'


def test_an_open_d_ties_nothing_and_a_shut_one_ties_the_gap():
    m, _L = east.build(archetype='ILS-EAST', system='F2D', p_gap=1e-3)
    idx = m._part_index
    d_nodes = {idx[a.node_a] for a in cons.deadband_associations(m)}
    assert not [r for r in cons.constraint_rows(m) if r[0] in d_nodes]
    for sign in (+1, -1):
        rows = [r for r in cons.constraint_rows(
            m, engaged={a.node_a: sign
                        for a in cons.deadband_associations(m)})
            if r[0] in d_nodes]
        assert {r[2] for r in rows} == {1}, 'perpendicular only'
        assert all(r[3] == pytest.approx(sign * 1e-3) for r in rows)


def test_an_engaged_d_without_a_gap_refuses():
    """P_gap has no default and nothing upstream enforces it (CUN-001)."""
    m, _L = east.build(archetype='ILS-EAST', system='F2D')   # no p_gap
    assert all(a.gap is None for a in cons.deadband_associations(m))
    with pytest.raises(ValueError, match='P_gap'):
        cons.constraint_rows(m, engaged={a.node_a: 1
                                         for a in cons.deadband_associations(m)})


def test_release_is_on_force_and_engage_is_on_separation():
    """L008, as a unit. The two decisions are not the same test: an engaged D
    sits AT the gap by construction, so separation can never release it."""
    m, _L = east.build(archetype='ILS-EAST', system='F2D', p_gap=1e-3)
    d = cons.deadband_associations(m)
    open_state = {a.node_a: 0 for a in d}

    shut = cons.update_active_set(m, open_state, sep_of=lambda a: 2e-3,
                                  force_of=lambda a, s: 0.0, P=1e5)
    assert set(shut.values()) == {+1}, 'separation beyond the gap engages it'
    stay = cons.update_active_set(m, open_state, sep_of=lambda a: 0.5e-3,
                                  force_of=lambda a, s: 0.0, P=1e5)
    assert set(stay.values()) == {0}, 'inside the gap it stays open'

    engaged = {a.node_a: +1 for a in d}
    held = cons.update_active_set(m, engaged, sep_of=lambda a: 1e-3,
                                  force_of=lambda a, s: -5e3, P=1e5)
    assert set(held.values()) == {+1}, 'pushing: still in contact'
    let_go = cons.update_active_set(m, engaged, sep_of=lambda a: 1e-3,
                                    force_of=lambda a, s: +5e3, P=1e5)
    assert set(let_go.values()) == {0}, 'pulling: the gap has reopened'


# ---------------------------------------------------------------------------
# the solver, against every number the studies measured
# ---------------------------------------------------------------------------

STUDY = [
    ('ILS-EAST', 'F2',  None, None,     'F2',  49.42884390),
    ('ILS-EAST', 'F2',  None, 'PS',     'PS',  65.47250),
    ('ILS-EASB', 'F2',  None, None,     'F2',  70.39454),
    ('ILS-EASB', 'F2',  None, 'PS',     'PS',  83.58240),
    ('ILS-EAST', 'F2D', 5.0e-3,  None,  'open', 49.42922334),
    ('ILS-EAST', 'F2D', 0.25e-3, None,  'shut', 38.95016),
    ('ILS-EAST', 'F1D', 0.75e-3, None,  'shut', 44.56484),
    ('ILS-EASB', 'F2D', 0.30e-3, None,  'shut', 55.97199),
    ('ILS-EASB', 'F1D', 0.80e-3, None,  'shut', 59.60873),
]


@pytest.mark.parametrize('arch,system,gap,layout,tag,expect', STUDY)
def test_the_package_reproduces_the_studies(arch, system, gap, layout, tag,
                                            expect):
    """The verification that matters. Each figure was produced first by a
    study in tools/ and must come back out of the package unchanged -- both
    archetypes, both deadband systems, engaged and open, and the tie-override
    path as well as the declared one."""
    kw = dict(archetype=arch, system=system)
    if gap is not None:
        kw['p_gap'] = gap
    m, _L = east.build(**kw)
    d, r, _ms, _fixed = rig(m, 200e3, layout)
    assert d * 1e3 == pytest.approx(expect, rel=2e-5), tag
    assert r.violation < 1e-8
    assert r.settled and r.flips <= 1


@pytest.mark.parametrize('arch', ['ILS-EAST', 'ILS-EASB'])
def test_reactions_balance_through_the_package(arch):
    m, _L = east.build(archetype=arch, system='F2')
    for P in (20e3, 200e3):
        _d, r, ms, fixed = rig(m, P)
        _K, Fint = kern.assemble(m, ms, r.U)
        assert -sum(Fint[k] for k in fixed if k % 3 == 1) == \
            pytest.approx(P, rel=1e-6)


def test_the_penalty_floor_is_reported_not_hidden():
    """An engaged deadband stagnates at ~2.5e-09 because k_pen is ~1e15 and
    round-off in U cannot go below it. The loop says so rather than raising,
    and rather than pretending it converged. The study loops it replaces ran
    30 iterations and fell out of the `for` with no `else`."""
    m, _L = east.build(archetype='ILS-EAST', system='F2D', p_gap=0.25e-3)
    _d, r, _ms, _f = rig(m, 200e3)
    assert r.stalled, 'an engaged D cannot reach 1e-8 on this formulation'
    assert r.residual < newton.STALL_BAND
    assert r.violation < 1e-8, 'and the constraint is still satisfied'

    m2, _L2 = east.build(archetype='ILS-EAST', system='F2')
    _d2, r2, _ms2, _f2 = rig(m2, 200e3)
    assert not r2.stalled, 'F and W alone reach the tolerance outright'


def test_a_non_converging_case_raises_rather_than_spinning():
    """L015: `nlfea_v4.solve_step` halves the increment and retries WITHOUT
    bound, raising nothing -- a 0.02 s solve ran 15 minutes. Every loop here
    is bounded."""
    m, _L = east.build(archetype='ILS-EAST', system='F2')
    with pytest.raises(RuntimeError, match='did not converge'):
        rig(m, 200e3, tol=1e-18, max_iter=4)


def test_alpha_is_the_measured_value():
    assert pen.ALPHA == 1e5


def test_the_kernel_map_is_still_a_permutation():
    """L009. If this ever became the identity the `dof()` indirection would
    look redundant and get removed."""
    m, _L = east.build(archetype='ILS-EAST', system='F2')
    ms, _b = kern.mesh(m)
    mapping = [ms.user_node_to_mesh[i] for i in range(m.n_nodes)]
    assert sorted(mapping) == list(range(m.n_nodes)), 'a bijection'
    assert mapping != list(range(m.n_nodes)), 'and not the identity'


@pytest.mark.parametrize('arch,owner', [('ILS-EAST', 'ST'), ('ILS-EASB', 'SB')])
def test_the_ea_owner_is_read_not_assumed(arch, owner):
    """L036: a hardcoded 'ST' is three separate crashes on ILS-EASB."""
    m, _L = east.build(archetype=arch, system='F2')
    assert kern.ea_owner(m) == owner
    assert kern.structural_ratio(m) == pytest.approx(2.5)

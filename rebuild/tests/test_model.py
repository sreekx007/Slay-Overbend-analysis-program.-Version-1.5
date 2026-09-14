"""T3 -- the Model layer: the four-pass assembly.

WHAT THESE TESTS ARE FOR. The mesher's job is to be invisible. Every check
here asks one of two questions: did a node that had to exist survive, and did
a node that must stay separate stay separate. Nothing here checks physics --
there is no material bound, no contact, no load. That is L5's, and conflating
them is what `docs/SLAY_BUILD_INSTRUCTION.md` section 7 warns against.

THE ONE THAT MATTERS MOST is `test_easb_straddle_does_not_weld_into_the_pipe`.
ILS-EASB's GD-SB sits at P_vt = 0 with seven nodes exactly on the pipe
centreline, and under the old kernel its centre slot welded itself to the
pipe's load node on every element size and pad length measured. It is the
documented "two-point attachment became a continuous stiffener" failure,
caught in a published archetype rather than a contrived one.
"""

import json
from pathlib import Path

import pytest

import ils_builder

from slay.model.assemble import build_model
from slay.model.parts import (
    AssemblyError,
    MERGE_TOL,
    TIES_OPEN,
    TIES_SHUT,
    layout_is_adequate,
)
from slay.scene import build_scene

FIXTURE = Path(__file__).parents[1] / 'fixtures' / 'standard_ils_layouts.json'


def _archetypes():
    return {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}


ARCHETYPE_IDS = sorted(_archetypes())


@pytest.fixture(scope='module')
def scene():
    return build_scene()


def _model(scene, arch_id, **kw):
    ils = ils_builder.build_ils(_archetypes()[arch_id]['definition'])
    return build_model(scene, ils, **kw)


# ---------------------------------------------------------------------------
# plain pipe -- the M1 case
# ---------------------------------------------------------------------------

def test_plain_pipe_spans_the_whole_extent(scene):
    m = build_model(scene)
    s_lo, s_hi = scene.extent
    assert min(n.s for n in m.nodes) == pytest.approx(s_lo)
    assert max(n.s for n in m.nodes) == pytest.approx(s_hi)
    assert m.line_ids() == ['pipeline']


def test_plain_pipe_element_count_is_recorded(scene):
    """109 elements at 2 x OD over the 88 m extent. Pinned, per G8 -- 'it ran
    without error' is not verification, so the number goes in the test."""
    m = build_model(scene)
    assert (m.n_nodes, m.n_elems) == (110, 109)
    assert m.warnings == []


def test_elastic_zone_boundaries_are_nodes(scene):
    """A material discontinuity must not be smeared across an element any more
    than a section change may be."""
    m = build_model(scene)
    s_of = {round(n.s, 6) for n in m.nodes}
    for s_b in scene.elastic_zone_boundaries:
        assert round(s_b, 6) in s_of, f'no node at elastic boundary s={s_b}'


# ---------------------------------------------------------------------------
# every archetype
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_archetype_assembles(scene, arch_id):
    m = _model(scene, arch_id)
    assert m.n_elems > 0
    assert m.n_nodes == len({n.index for n in m.nodes})


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_every_mandatory_station_survives(scene, arch_id):
    """G4 -- never drop a MANDATORY station. Every part node must appear as a
    model node, because a part node is a physical thing: a weld, a section
    change, a connector end."""
    m = _model(scene, arch_id)
    got = {n.part_id for n in m.nodes if n.part_id}
    missing = set(m.part_nodes) - got
    assert not missing, f'{arch_id}: part nodes lost in meshing: {sorted(missing)}'


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_no_warnings_beyond_zero_length_connectors(scene, arch_id):
    m = _model(scene, arch_id)
    unexpected = [w for w in m.warnings if 'zero-length' not in w]
    assert not unexpected, f'{arch_id}: {unexpected}'


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_elements_reference_real_nodes(scene, arch_id):
    m = _model(scene, arch_id)
    n = m.n_nodes
    for e in m.elements:
        assert 0 <= e.n1 < n and 0 <= e.n2 < n
        assert e.n1 != e.n2, f'{arch_id}: element {e.index} is degenerate'


# ---------------------------------------------------------------------------
# the pass boundary -- what this whole design exists for
# ---------------------------------------------------------------------------

def test_easb_straddle_does_not_weld_into_the_pipe(scene):
    """GD-SB at P_vt = 0 has seven nodes on the pipe centreline. Not one may
    become a header node."""
    m = _model(scene, 'ILS-EASB')
    on_cl = [n for n in m.part_nodes.values()
             if abs(n.y) < 1e-12 and 'SB' in n.owners]
    assert len(on_cl) >= 7, 'the case being guarded has changed shape'
    welded = [n.part_id for n in on_cl if n.pass_no == 1]
    assert not welded, f'GD-SB nodes merged into the header: {welded}'


def test_coincident_nodes_across_passes_stay_distinct(scene):
    """Four model nodes at one position, on purpose.

    ILS-EASB's slot 2 stacks the header station, the straddle's own sslot2,
    and both ends of a zero-length connector at (s = 1.0837, y = 0). Under the
    old kernel that was one node. It is now four, each with its own row in the
    stiffness matrix, joined only by the declared associations.
    """
    m = _model(scene, 'ILS-EASB')
    stack = [n for n in m.nodes
             if abs(n.s - 1.0837333333333332) < 1e-9 and abs(n.y) < 1e-9]
    assert len(stack) == 4, [n.part_id for n in stack]
    assert len({n.index for n in stack}) == 4
    kinds = {n.part_id for n in stack}
    assert any(p.startswith('PIPE-') for p in kinds)
    assert any(p.startswith('GDSB-') for p in kinds)
    assert {'CSB2-P', 'CSB2-E'} <= kinds


def test_declared_junction_does_cross_the_pass_boundary(scene):
    """The one exception, and it is intent rather than coincidence: GD-B's tee
    declares a tie to the header, so it resolves into the header node."""
    m = _model(scene, 'ILS-ILT')
    tee = [n for n in m.part_nodes.values()
           if abs(n.x) < 1e-9 and abs(n.y) < 1e-9 and n.pass_no == 1]
    assert tee, 'GD-B tee did not resolve into a header node'
    assert any('B' in n.owners for n in tee)


def test_part_node_produces_exactly_one_model_node(scene):
    for arch_id in ARCHETYPE_IDS:
        _model(scene, arch_id).assert_no_accidental_sharing()


# ---------------------------------------------------------------------------
# chain identity -- D2's evidence
# ---------------------------------------------------------------------------

def test_chain_partition_recoverable_from_line_id(scene):
    """D2: no MeshTopology object. The pipeline and a GD-ST frame separate on
    `line_id` alone, which is what turns section 7's argument into evidence."""
    m = _model(scene, 'ILS-EAST')
    pipe = m.elements_of('pipeline')
    frame = [e for e in m.elements if e.line_id.startswith('ST:')]
    assert pipe and frame
    assert not ({e.index for e in pipe} & {e.index for e in frame})
    assert len(pipe) + len(frame) <= m.n_elems


def test_owner_identifies_the_component(scene):
    m = _model(scene, 'ILS-TT')
    assert 'TT' in m.owners()
    assert 'pipeline' in m.owners()


# ---------------------------------------------------------------------------
# shift invariance -- section 2.5's claim, made checkable
# ---------------------------------------------------------------------------

def _component_lengths(m):
    import math
    at = {n.index: n for n in m.nodes}
    return sorted(round(math.dist((at[e.n1].s, at[e.n1].y),
                                  (at[e.n2].s, at[e.n2].y)), 12)
                  for e in m.elements if e.owner != 'pipeline')


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_ils_discretisation_is_shift_invariant(scene, arch_id):
    """The ILS is welded into the pipe, so moving it along the lay path changes
    WHICH material point sits under each roller and nothing else. Its own
    element lengths must be bit-identical wherever it sits.

    SCOPED TO THE COMPONENTS, and the scope is the finding. The plain-pipe
    filler either side cannot be invariant: the model extent is fixed while
    the ILS moves inside it, so the two gaps change length and their
    round(L / target) subdivision changes with them -- a 6 m shift is 7.38
    elements, not a whole number of them. One gap gains an element, the other
    loses one. The invariance that matters is the component's, because that is
    where strain is reported and that is what the mesher must not perturb.
    """
    lengths = [_component_lengths(_model(scene, arch_id, s_centre=c))
               for c in (0.0, 6.0, -11.5)]
    assert lengths[0] == lengths[1] == lengths[2]


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_plain_pipe_filler_absorbs_the_shift(scene, arch_id):
    """The other half of the same fact, asserted rather than left implicit:
    only the filler moves, and it moves by at most one element."""
    a = _model(scene, arch_id, s_centre=0.0)
    b = _model(scene, arch_id, s_centre=6.0)
    fill = lambda m: len([e for e in m.elements if e.owner == 'pipeline'])
    assert abs(fill(a) - fill(b)) <= 1


# ---------------------------------------------------------------------------
# connectors
# ---------------------------------------------------------------------------

def test_connector_associations_are_recorded(scene):
    """Two per connector: one to the pipe (always all-DOF) and one to the EA
    structure (per joint type)."""
    m = _model(scene, 'ILS-EAST')
    assert len(m.associations) == 4          # F2 -> two connectors
    pipe_side = [a for a in m.associations if a.node_a.endswith('-P')]
    ea_side = [a for a in m.associations if a.node_a.endswith('-E')]
    assert len(pipe_side) == len(ea_side) == 2
    for a in pipe_side:
        assert a.ties == (True, True, True) and a.conn_type == 'W'
    for a in ea_side:
        assert a.conn_type == 'F' and a.ties == (True, True, True)
        assert not a.skewed, 'F needs no co-rotating frame'


def test_zero_length_connector_is_still_an_element(scene):
    """Zero length is LEGAL, is the DEFAULT, and is not a special case.

    ILS-EASB's connectors are zero-length and still carry the full connector
    stiffness -- that of a 1 x OD length of pipeline, the same as every other
    connector. The rule is absolute precisely so that this case needs no
    exception: a length-derived stiffness would be undefined exactly where the
    default lands.
    """
    m = _model(scene, 'ILS-EASB')
    conns = [e for e in m.elements if e.connector is not None]
    assert len(conns) == 2
    for e in conns:
        assert e.connector.length == 0.0
        assert e.connector.stiffness == '1xOD_pipeline'
    assert len(m.associations) == 4
    assert m.warnings == []


def test_connector_stiffness_is_independent_of_length(scene):
    """Three archetypes, three different connector lengths, one stiffness
    rule. If the rule ever became length-derived this is what would catch
    it."""
    lengths = {}
    for arch_id in ('ILS-EASB', 'ILS-ILT', 'ILS-EAST'):
        m = _model(scene, arch_id)
        conns = [e for e in m.elements if e.connector is not None]
        assert conns, arch_id
        assert {e.connector.stiffness for e in conns} == {'1xOD_pipeline'}
        lengths[arch_id] = conns[0].connector.length
    assert lengths['ILS-EASB'] == 0.0
    assert lengths['ILS-ILT'] == pytest.approx(0.2032)
    assert lengths['ILS-EAST'] == pytest.approx(0.6096)
    assert len(set(lengths.values())) == 3, 'the lengths really do differ'


def test_nonzero_connector_becomes_an_element(scene):
    m = _model(scene, 'ILS-EAST')
    conns = [e for e in m.elements if e.connector is not None]
    assert conns, 'ILS-EAST has a 0.6096 m offset, so real elements'
    for e in conns:
        assert e.connector.stiffness == '1xOD_pipeline'
        assert e.connector.length == pytest.approx(0.6096)
        assert e.owner == 'GD-Con'


def test_connector_stiffness_is_a_rule_not_a_number(scene):
    """T3 emits no physics. What the connector IS is recorded; what it is
    worth is L5's answer."""
    m = _model(scene, 'ILS-EAST')
    e = next(e for e in m.elements if e.connector is not None)
    assert isinstance(e.connector.stiffness, str)
    assert e.section is None and e.stiffness_ratio is None


# ---------------------------------------------------------------------------
# joint kinematics and layout adequacy
# ---------------------------------------------------------------------------

def test_d_is_a_pure_support():
    """Local x and rz are restrained in NEITHER state; local y only once the
    deadband closes."""
    assert TIES_OPEN['D'] == (False, False, False)
    assert TIES_SHUT['D'] == (False, True, False)


def test_s_slides_along_the_slope_not_its_own_axis():
    assert TIES_OPEN['S'] == (False, True, True)


def test_p_frees_only_rotation():
    assert TIES_OPEN['P'] == (True, True, False)


def test_every_named_system_is_adequate_with_all_gaps_open():
    """A `D` that holds nothing while open cannot hold a structure up alone, so
    the layout as a whole must restrain all three planar rigid-body DOF in the
    WEAKEST state -- which is the one the first solve increment meets."""
    import component_spec as cs
    slots = cs.connector_slot_xs(0.0, 3.2512, 0.4064)
    for name, types in cs.NAMED_CONNECTION_SYSTEMS.items():
        assert all(layout_is_adequate(types, slots)), \
            f'{name} has a rigid-body mode with every D gap open'


def test_a_support_only_layout_is_a_mechanism():
    """Legal to construct, impossible to solve -- singular in BOTH states, and
    in local x even once both gaps shut. The check is generic on the tuple, so
    a user-defined layout is judged on the same terms as a published one."""
    import component_spec as cs
    slots = cs.connector_slot_xs(0.0, 3.2512, 0.4064)
    bad = ('D', None, None, None, 'D')
    assert layout_is_adequate(bad, slots) == (False, False, False)
    assert layout_is_adequate(bad, slots, TIES_SHUT) == (False, True, True)


def test_unsupported_connector_type_is_refused(scene, monkeypatch):
    """G9 -- a P/S/D case is refused, never approximated by F. Refusing is the
    whole point: approximating would silently answer a different question."""
    ils = ils_builder.build_ils(_archetypes()['ILS-EAST']['definition'])
    real = ils.connectors_of

    def as_ps(component):
        out = real(component)
        return [(s, x, t, a, e) for (s, x, _t, a, e), t
                in zip(out, ('P', 'S'))] if out else out

    monkeypatch.setattr(ils, 'connectors_of', as_ps)
    with pytest.raises(AssemblyError, match='G9'):
        build_model(scene, ils)


# ---------------------------------------------------------------------------
# the merge tolerance
# ---------------------------------------------------------------------------

def test_merge_tolerance_has_margin_over_the_published_set():
    """The closest DISTINCT pair of structural nodes anywhere in the published
    set is 0.176 m (anchor TT-1to4, the shallowest taper). The tolerance must
    stay well under that or it would destroy a real feature."""
    import math
    layouts = json.loads(FIXTURE.read_text())
    tightest = math.inf
    for a in layouts['archetypes']:
        ils = ils_builder.build_ils(a['definition'])
        pts = [(n.x, n.y) for c in ils.components for n in c.structural_nodes()]
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                r = math.dist(pts[i], pts[j])
                if r > 1e-12:
                    tightest = min(tightest, r)
    assert tightest > 10 * MERGE_TOL, (
        f'closest distinct spacing {tightest:.4f} m leaves less than a 10x '
        f'margin over the {MERGE_TOL} m merge tolerance')


# ---------------------------------------------------------------------------
# the layer boundary -- what the kernel does with what we hand it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_kernel_leaves_the_model_intact(scene, arch_id):
    """"Must not merge or edit nodes", made operational.

    With `seed = 1` on every element we emit and no coordinate keying left in
    the kernel, the mapping from our nodes to its nodes is a BIJECTION -- and
    that triple is the whole guarantee, seen from the far side of the layer
    boundary. Before the change, ILS-EASB came back one node short.
    """
    np = pytest.importorskip('numpy')
    fe = pytest.importorskip('nlfea_v4')

    m = _model(scene, arch_id)
    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in m.nodes],
        elements=[fe.UserElement(e.index, e.n1, e.n2, 1, 1, seed=1)
                  for e in m.elements],
        sections=[fe.PipeSection(1, 0.4064, 0.021)],
        materials=[fe.Material(1, 2.1e11)])
    ms = fe.MeshedStructure(mdl)

    assert ms.n_nodes == m.n_nodes, f'{arch_id}: kernel merged nodes'
    assert ms.n_elems == m.n_elems
    assert set(ms.user_node_to_mesh.values()) == set(range(ms.n_nodes))
    for n in m.nodes:
        assert ms.mesh_nodes[ms.user_node_to_mesh[n.index]] == (n.s, n.y)


# ---------------------------------------------------------------------------
# Group B -- the blocker, pinned (test plan "B0")
# ---------------------------------------------------------------------------

GROUP_B = ('ILS-EAST', 'ILS-EASB', 'ILS-ILT')


@pytest.mark.parametrize('arch_id', GROUP_B)
def test_group_b_cannot_yet_be_solved(scene, arch_id):
    """Group B assembles correctly and CANNOT YET BE SOLVED, on purpose.

    Pinned rather than left implicit, so the gap cannot be mistaken later for
    a passing test. There are two distinct blockers and both are real:

    1. NO PENALTY CONSTRAINTS. The EA structure is held to the pipe by
       connectors, and a connector is a recorded association enforced by a
       penalty. The model declares the associations; nothing applies them, so
       the frame floats. Measured on the free stiffness matrix with both pipe
       ends fixed, the smallest |eigenvalue| is 1.7e-07 (EAST) and 2.8e-07
       (ILT) against 6.7e+02 and 5.6e+02 for Group A -- nine orders of
       magnitude, so it is not a threshold judgement.

    2. A ZERO-LENGTH CONNECTOR IS NOT A COROTATIONAL ELEMENT. Every connector
       carries the stiffness of a 1 x OD length of pipeline whatever its own
       length, so a zero-length one is an ordinary case -- but `nlfea_v4`
       divides by the deformed length and returns inf/NaN for it. ILS-EASB's
       connectors are zero-length, which is the DEFAULT, so this is the
       common case rather than an edge one. It needs a prescribed-stiffness
       element type, not a workaround.

    NOT CONTRADICTED by `test_east_full.py`, which solves ILS-EAST. That
    study APPLIES the associations as penalty constraints; this asserts the
    model's own elements are singular WITHOUT them, which is what says the
    associations are declared and not yet enforced anywhere in the package.
    The two flip together only when the penalty module moves out of tools/.
    """
    np = pytest.importorskip('numpy')
    fe = pytest.importorskip('nlfea_v4')

    m = _model(scene, arch_id)
    assert m.associations, 'the ties are declared even though nothing applies them'
    assert [e for e in m.elements if e.connector is not None], 'connectors exist'

    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in m.nodes],
        elements=[fe.UserElement(e.index, e.n1, e.n2, 1, 1, seed=1)
                  for e in m.elements],
        sections=[fe.PipeSection(1, 0.4064, 0.021)],
        materials=[fe.Material(1, 2.1e11)])
    ms = fe.MeshedStructure(mdl)
    with np.errstate(divide='ignore', invalid='ignore'):
        K, *_ = fe.assemble(ms, np.zeros(ms.n_dofs),
                            np.full(ms.n_elems, np.nan), {}, [], 1.0)
    Kd = K.toarray()

    zero_len = [e for e in m.elements
                if e.connector is not None and e.connector.length == 0.0]
    if zero_len:
        # Blocker 2. The kernel cannot form this element at all.
        assert not np.isfinite(Kd).all(), (
            f'{arch_id}: the kernel now forms a zero-length connector. If a '
            f'prescribed-stiffness element has landed, invert this test.')
        return

    # Blocker 1. The matrix is finite but singular -- the frame floats.
    assert np.isfinite(Kd).all()
    ends = [min(m.nodes, key=lambda n: n.s), max(m.nodes, key=lambda n: n.s)]
    free = np.ones(ms.n_dofs, bool)
    for n in ends:
        for k in (0, 1, 2):
            free[3 * ms.user_node_to_mesh[n.index] + k] = False
    Kf = Kd[np.ix_(free, free)]
    smallest = np.abs(np.linalg.eigvalsh((Kf + Kf.T) / 2)).min()
    assert smallest < 1.0, (
        f'{arch_id}: smallest |eigenvalue| is {smallest:.3e}. If the penalty '
        f'module has landed, this test has done its job -- invert it.')


@pytest.mark.parametrize('arch_id', ('ILS-SH', 'ILS-TT'))
def test_group_a_is_not_singular(scene, arch_id):
    """The control. Without it, the test above would pass on a build that had
    simply stopped assembling anything."""
    np = pytest.importorskip('numpy')
    fe = pytest.importorskip('nlfea_v4')

    m = _model(scene, arch_id)
    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in m.nodes],
        elements=[fe.UserElement(e.index, e.n1, e.n2, 1, 1, seed=1)
                  for e in m.elements],
        sections=[fe.PipeSection(1, 0.4064, 0.021)],
        materials=[fe.Material(1, 2.1e11)])
    ms = fe.MeshedStructure(mdl)
    K, *_ = fe.assemble(ms, np.zeros(ms.n_dofs),
                        np.full(ms.n_elems, np.nan), {}, [], 1.0)
    ends = [min(m.nodes, key=lambda n: n.s), max(m.nodes, key=lambda n: n.s)]
    free = np.ones(ms.n_dofs, bool)
    for n in ends:
        for k in (0, 1, 2):
            free[3 * ms.user_node_to_mesh[n.index] + k] = False
    Kf = K.toarray()[np.ix_(free, free)]
    assert np.abs(np.linalg.eigvalsh((Kf + Kf.T) / 2)).min() > 100.0

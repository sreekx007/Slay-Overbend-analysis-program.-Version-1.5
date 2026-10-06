"""The EA frame, fastened to the pipe in the PASSAGE solver.

WHAT WAS WRONG, and it was two things stacked, either of which alone is
fatal and both of which look identical from outside -- `CUTBACK EXHAUSTED at
lam=0.0000` with the kernel warning "Matrix is exactly singular".

  1. `Problem` splits connectors out of `elements` into `connectors`, and
     `mesh_of_problem` builds the kernel mesh from `elements` alone. That is
     correct -- a corotational beam would take its stiffness from its own
     length and a connector's length is geometry, not stiffness -- but
     nothing put the connectors back, so their 6x6 was never assembled.

  2. A connector element has its OWN two nodes, one at the pipe and one at
     the structure, and ASSOCIATIONS are what fasten those to the real
     pipeline and frame nodes. `solve.newton` applies them; `solve.passage`
     never did. `newton` even names the symptom: "a Group B model with its
     associations unapplied looks exactly like this".

Between them the EA frame was assembled as 18 elements attached to nothing
at all: a rigid-body mechanism, and no lay position of any EA archetype had
ever converged.

THE OTHER HALF OF THE FIX IS THAT NOTHING ELSE MOVED. Every model without an
EA structure has no connectors and no associations, so both additions are
empty and the load path is untouched.
"""

from __future__ import annotations

import warnings

import pytest

from slay.data.materials import material
from slay.model.assemble import build_model
from slay.physics.problem import build_problem
from slay.scene.scene import all_bidirectional
from slay.solve import constraints as cons
from slay.solve.kernel import mesh_of_problem, problem_connectors
from slay.solve.passage import solve
from slay.study import sweep

TON = 9806.65
_CACHE = {}


def _archetype(aid):
    import json
    import copy
    import ils_builder
    from pathlib import Path
    fx = Path(__file__).resolve().parents[1] / 'fixtures' / \
        'standard_ils_layouts.json'
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        fx.read_text())['archetypes']}[aid]['definition'])
    return ils_builder.build_ils(spec)


def _posed(aid='ILS-EAST', held=True, gravity=False, tension=0.0, mat=None):
    """(problem, ms) for one EA archetype at the start position."""
    key = (aid, held, gravity, tension, mat is not None)
    if key in _CACHE:
        return _CACHE[key]
    ils = _archetype(aid)
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_c = sweep.start_centre(sc, L)
    m = build_model(sc, ils, s_centre=s_c,
                    extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)
    p = build_problem(m, all_bidirectional(sc) if held else sc, shift=0.0,
                      assembly=ils.assembly, ils=ils, s_centre=s_c,
                      material=mat, gravity=gravity, tension=tension,
                      vertical_at=(lo,), elastic_spans=((lo, hi),))
    ms, _mdl, _ix = mesh_of_problem(p)
    _CACHE[key] = (p, ms)
    return _CACHE[key]


# ---------------------------------------------------------------------------
# the defect, described exactly
# ---------------------------------------------------------------------------

def test_the_connectors_are_not_in_the_element_list():
    """Not a bug -- the reason the fix is needed, pinned so it stays true."""
    p, _ms = _posed()
    owners = {o for (_i, _a, _b, o, _l) in p.elements}
    assert 'GD-Con' not in owners
    assert len(p.connectors) == 2, 'ILS-EAST is an F2 layout: two connectors'


def test_a_connector_bridges_its_OWN_nodes_not_the_pipe_and_frame():
    """The thing that makes associations load-bearing rather than cosmetic."""
    p, _ms = _posed()
    frame = {n for (_i, a, b, o, _l) in p.elements if o == 'ST'
             for n in (a, b)}
    pipe = {n for (_i, a, b, o, _l) in p.elements if o == 'pipeline'
            for n in (a, b)}
    ends = {n for (_i, a, b, _c, _l, _s) in p.connectors for n in (a, b)}
    assert ends and not (ends & frame) and not (ends & pipe), (
        'a connector end that already WAS a pipe or frame node would need no '
        'association, and this test would be guarding nothing')


def test_the_ties_exist_and_reach_both_bodies():
    p, _ms = _posed()
    rows = cons.constraint_rows_from(p.associations, p.part_index)
    assert rows, 'no ties resolved: the frame would be held by nothing'
    tied = {na for (na, _nb, _k, _t) in rows} | \
           {nb for (_na, nb, _k, _t) in rows}
    frame = {n for (_i, a, b, o, _l) in p.elements if o == 'ST'
             for n in (a, b)}
    pipe = {n for (_i, a, b, o, _l) in p.elements if o == 'pipeline'
            for n in (a, b)}
    assert tied & frame, 'nothing ties the structure'
    assert tied & pipe, 'nothing ties the pipeline'


def test_the_problem_carries_the_part_index():
    """Without it a Problem cannot resolve its own associations into DOFs."""
    p, _ms = _posed()
    assert p.part_index, 'associations name part nodes; the index resolves them'
    for a in p.associations:
        assert a.node_a in p.part_index and a.node_b in p.part_index


# ---------------------------------------------------------------------------
# the fix
# ---------------------------------------------------------------------------

def test_connector_stiffness_is_assembled():
    p, ms = _posed()
    conn = problem_connectors(p, ms)
    assert len(conn) == 2
    for dofs, k6 in conn:
        assert len(dofs) == 6 and len(set(dofs)) == 6
        assert k6.shape == (6, 6)
        assert abs(k6).max() > 0.0


def test_G9_an_unimplemented_connector_is_refused_not_approximated():
    """The joint type selects which DOF is tied; substituting another ties
    the wrong ones and silently answers a different question.

    `P` and `S` were added when the co-rotating frame landed, so the example
    here is `D` -- a deadband, which needs an ACTIVE SET as well as a frame
    and would otherwise behave as an always-shut S.
    """
    p, ms = _posed()
    bad = p.__class__(**{**p.__dict__,
                         'connectors': tuple(
                             (i, a, b, 'D', ln, s)
                             for (i, a, b, _c, ln, s) in p.connectors)})
    with pytest.raises(ValueError, match='G9'):
        problem_connectors(bad, ms)


@pytest.mark.parametrize('aid', ['ILS-EAST', 'ILS-EASB', 'ILS-ILT'])
def test_every_EA_archetype_now_solves_its_first_position(aid):
    """Before this, no lay position of any of them had ever converged."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        p, _ms = _posed(aid)
        r, _state = solve(p)
    assert r.converged, f'{aid}: {r.status}'


def test_the_staged_sequence_runs_end_to_end():
    """Shape, then gravity, then tension, then plasticity -- on a frame."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        state = None
        for held, gravity, tension, mat in (
                (True, False, 0.0, None),
                (False, True, 0.0, None),
                (False, True, 120.0 * TON, None),
                (False, True, 120.0 * TON, material('j2'))):
            p, _ms = _posed('ILS-EAST', held, gravity, tension, mat)
            r, state = solve(p, state_in=state)
            assert r.converged, r.status
    eps = max(abs(e) for (_i, _s, e) in r.strains)
    assert 0.0005 < eps < 0.05, f'implausible peak strain {eps}'


# ---------------------------------------------------------------------------
# and nothing else moved
# ---------------------------------------------------------------------------

def test_a_model_without_a_frame_has_neither_connectors_nor_ties():
    """Which is why the load path of every other case is untouched."""
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0)
    m = build_model(sc, None, s_centre=sweep.start_centre(sc, 0.0),
                    extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)
    p = build_problem(m, sc, shift=0.0, material=None, gravity=True,
                      tension=0.0, vertical_at=(lo,),
                      elastic_spans=((lo, hi),))
    ms, _mdl, _ix = mesh_of_problem(p)
    assert problem_connectors(p, ms) == []
    assert cons.constraint_rows_from(p.associations, p.part_index or {}) == []


def test_the_penalty_is_scaled_on_the_BEAM_stiffness():
    """L085. A connector's 6x6 is built at 1 x OD, so its diagonal is ~1.3e10
    against the beams' ~3e6. Scaling the penalty on the connector-augmented
    matrix multiplies it by four orders of magnitude; the first residual
    comes out at 1e18 and the solve returns NaN.

    `penalty.py`'s multiplier was tuned by sweep against the beam stiffness,
    so changing what it multiplies changes the constant. Checked on the
    SOURCE because the quantity is internal to one Newton iteration, and
    behaviourally by the EA solves above, which NaN if this regresses.
    """
    import inspect

    from slay.solve import passage as sp
    src = inspect.getsource(sp.solve)
    scale_at = src.index('p_scale = float(K.diagonal().max())')
    conn_at = src.index('for _d, _k6 in conn:')
    assert scale_at < conn_at, (
        'p_scale must be taken BEFORE the connectors are added to Kl')


def test_constraint_rows_agree_between_the_model_and_problem_paths():
    """One rule, read once. The static solver resolves ties from a Model and
    the passage solver from a Problem; if those two disagreed, two solvers
    would be enforcing different joints on the same geometry."""
    ils = _archetype('ILS-EAST')
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_c = sweep.start_centre(sc, L)
    m = build_model(sc, ils, s_centre=s_c,
                    extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)
    p = build_problem(m, sc, shift=0.0, assembly=ils.assembly, ils=ils,
                      s_centre=s_c, material=None, gravity=False, tension=0.0,
                      vertical_at=(lo,), elastic_spans=((lo, hi),))
    assert (cons.constraint_rows(m)
            == cons.constraint_rows_from(p.associations, p.part_index))

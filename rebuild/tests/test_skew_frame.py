"""The co-rotating frame, without which a PS layout cannot be solved here.

WHAT AN `S` IS. A bolt in a slot. It SLIDES along the slot and TURNS in it,
and restrains only the direction ACROSS the slot. `TIES_OPEN['S']` is
(False, True, False): local y held, local x and rz free.

WHY IT NEEDS A FRAME AND `F` DOES NOT. F and W tie all three DOF, so no
rotation of the axes changes what they tie; P frees rz alone, which is
frame-independent. An S ties ONE direction and releases the perpendicular
one, so its row is `n . (u_a - u_b) = 0` with `n` the local normal -- and
that cannot be written as a set of per-component rows at all. On the stinger
the pipe turns, so `n` turns with it: measured over the EA structures' own
travel the lay path runs 1.0 to 9.5 degrees, and 30 by the last roller.

`slay.solve.constraints` carried this as a KNOWN ABSENCE for weeks -- "every
rig solved so far is horizontal, where local IS global exactly" -- and G9
kept S out of the mesher's supported set until it landed.
"""

from __future__ import annotations

import copy
import json
import math
import warnings
from pathlib import Path

import pytest

from slay.data.materials import material
from slay.model.assemble import build_model
from slay.model.parts import SKEWED, TIES_OPEN
from slay.physics.problem import build_problem
from slay.solve import constraints as cons
from slay.solve.kernel import mesh_of_problem, problem_connectors
from slay.solve.passage import skew_constraints, skew_rows_now, solve
from slay.study import sweep

TON = 9806.65
D = 0.4064
REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / 'fixtures' / 'standard_ils_layouts.json'
_CACHE = {}


def _ils(aid, system):
    import ils_builder
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        FIXTURE.read_text())['archetypes']}[aid]['definition'])
    spec['ils']['connection_system'] = system
    return ils_builder.build_ils(spec)


def _posed(aid='ILS-EAST', system='PS', shift=0.0, solved=False):
    key = (aid, system, shift, solved)
    if key in _CACHE:
        return _CACHE[key]
    ils = _ils(aid, system)
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_c = sweep.start_centre(sc, L)
    m = build_model(sc, ils, s_centre=s_c,
                    extra_stations=sweep._required_stations(sc),
                    emit_unenforced_conn_types=frozenset({'S'}))
    lo, hi = sweep.buffer_span(sc)
    p = build_problem(m, sc, shift=shift, assembly=ils.assembly, ils=ils,
                      s_centre=s_c,
                      material=material('j2') if solved else None,
                      gravity=solved, tension=120.0 * TON if solved else 0.0,
                      vertical_at=(lo,), elastic_spans=((lo, hi),))
    ms, _mdl, _ix = mesh_of_problem(p)
    res = None
    if solved:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            res, _st = solve(p)
    _CACHE[key] = (p, ms, res)
    return _CACHE[key]


# ---------------------------------------------------------------------------
# which joints need the frame at all
# ---------------------------------------------------------------------------

def test_only_the_joints_that_release_one_translation_are_skewed():
    assert SKEWED['F'] is False and SKEWED['W'] is False
    assert SKEWED['P'] is False, 'P frees rz alone, which no rotation changes'
    assert SKEWED['S'] is True and SKEWED['D'] is True
    assert TIES_OPEN['S'] == (False, True, False)


def test_a_PS_layout_is_a_P_and_an_S():
    p, _ms, _r = _posed()
    kinds = sorted((t, slot) for (_i, _a, _b, t, _l, slot) in p.connectors)
    assert kinds == [('P', 2), ('S', 4)]


def test_the_skewed_tie_is_one_row_not_three():
    """A per-component flattening of an S is exactly the error the frame
    exists to prevent, so the two kinds of row are produced separately."""
    p, ms, _r = _posed()
    plain = cons.constraint_rows_from(
        cons.plain_associations(p.associations), p.part_index)
    skew = skew_constraints(p, ms)
    assert len(skew) == 1, 'one S connector, one skewed row'
    assert skew_constraints(p, ms) and len(skew_rows_now(skew, _zeros(ms))) == 1
    # and the S is NOT also in the per-component rows
    idx = p.part_index
    s_nodes = {idx[a.node_a] for a in p.associations
               if getattr(a, 'skewed', False)}
    assert not (s_nodes & {na for (na, _nb, _k, _t) in plain})


def _zeros(ms):
    import numpy as np
    return np.zeros(ms.n_dofs)


def test_a_model_with_no_slot_builds_no_skewed_rows():
    """Which is why this costs nothing on every F2 case already run."""
    p, ms, _r = _posed(system='F2')
    assert skew_constraints(p, ms) == []


# ---------------------------------------------------------------------------
# the frame itself
# ---------------------------------------------------------------------------

def test_the_normal_is_perpendicular_and_antisymmetric():
    p, ms, _r = _posed()
    for dofs, co in skew_rows_now(skew_constraints(p, ms), _zeros(ms)):
        assert len(dofs) == 4 and len(co) == 4
        assert co[0] == pytest.approx(-co[2])
        assert co[1] == pytest.approx(-co[3])
        assert math.hypot(co[0], co[1]) == pytest.approx(1.0)


def test_the_frame_follows_the_displacement():
    """CO-rotating, not rotated once. Perturbing the chord that supplies the
    axis must turn the row; a frame fixed at the first iteration would be
    wrong by however far the pipe then bent."""
    import numpy as np
    p, ms, _r = _posed()
    skew = skew_constraints(p, ms)
    flat = skew_rows_now(skew, _zeros(ms))[0][1]
    U = _zeros(ms)
    U[skew[0]['hi'][1]] = 0.5          # lift one end of the chord
    bent = skew_rows_now(skew, U)[0][1]
    assert not np.allclose(flat, bent), 'the frame ignored the displacement'


def test_the_slot_slides_along_and_is_held_across():
    """THE PHYSICAL CHECK, and the one that caught the earlier error: an S
    that tied rz carried a pure couple with zero shear, which a slotted
    connection cannot do. Held across the slot, free along it."""
    import numpy as np
    p, ms, r = _posed(solved=True)
    assert r is not None and r.converged, r.status if r else 'no result'
    rows = skew_rows_now(skew_constraints(p, ms), r.U)
    assert rows
    for dofs, co in rows:
        d = np.array([r.U[dofs[0]] - r.U[dofs[2]],
                      r.U[dofs[1]] - r.U[dofs[3]]])
        n = np.array([co[0], co[1]])
        t = np.array([-n[1], n[0]])
        assert abs(n @ d) < 1e-9, f'the slot is carrying {n @ d:.3e} m across it'
        assert abs(t @ d) > 1e-4, 'the slot did not slide at all'


def test_the_slot_axis_is_global_only_while_the_pipe_is_straight():
    """The model solves in (s, y) with the UNDEFORMED pipe straight along
    y = 0, so at zero displacement local IS global and the frame is the
    identity. The slope is something the solution creates by bending the
    pipe onto the arc -- which is why the frame has to co-rotate rather than
    be computed once from the mesh.
    """
    p, ms, r = _posed(solved=True)

    def axis(U):
        co = skew_rows_now(skew_constraints(p, ms), U)[0][1]
        off = abs(math.degrees(math.atan2(-co[0], co[1])))
        return min(off, 180.0 - off)

    assert axis(_zeros(ms)) == pytest.approx(0.0, abs=1e-9)
    bent = axis(r.U)
    assert bent > 1.0, (
        f'the solved slot sits {bent:.2f} deg off horizontal; below about a '
        f'degree this rig could not tell a frame from none')


# ---------------------------------------------------------------------------
# G9 still holds for the joint that is NOT implemented
# ---------------------------------------------------------------------------

def test_a_deadband_is_still_refused():
    """D needs an ACTIVE SET as well as a frame. Letting it through with the
    frame alone would make it an always-shut S -- a different joint."""
    p, ms, _r = _posed()
    bad = p.__class__(**{**p.__dict__,
                         'connectors': tuple(
                             (i, a, b, 'D', ln, s)
                             for (i, a, b, _c, ln, s) in p.connectors)})
    with pytest.raises(ValueError, match='G9'):
        problem_connectors(bad, ms)


def test_an_unknown_skew_pattern_is_refused_not_guessed():
    p, ms, _r = _posed()
    rows = cons.skewed_rows(p.associations, p.part_index)
    assert rows and tuple(rows[0][3]) == (False, True, False)

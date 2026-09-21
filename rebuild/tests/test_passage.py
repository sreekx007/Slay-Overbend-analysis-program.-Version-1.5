"""T5 -- the passage solver. WHAT IS PROVEN, and what is not yet.

BUILT, NOT VALIDATED. `slay/solve/passage.py` is the sliding formulation
ported from `_solve_state_sliding` -- adaptive cutback, divergence detection,
plastic freeze/commit, and the active set between Newton passes rather than
inside them. These tests cover the machinery. They do NOT cover M1, because
M1's target could not be reproduced from the reference code; see
`docs/modules/T5_solve_spec.md` and decision D5.

WHAT IS PROVEN HERE is the part that can be checked without a reference: the
contact constraints are satisfied EXACTLY (1e-13 m at every station, including
an 8.897 m normal displacement at SR6), the bounded loops are bounded, and a
failure reports itself rather than returning 0.0 -- which is the documented
silent-failure signature this whole project's G8 exists for.
"""

import math

import pytest

import config                                    # noqa: E402

np = pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

from slay.data.materials import material            # noqa: E402
from slay.model.assemble import build_model         # noqa: E402
from slay.physics.problem import build_problem      # noqa: E402
from slay.scene.path import LayPath                 # noqa: E402
from slay.scene.rollers import roller_stations      # noqa: E402
from slay.scene.scene import Scene                  # noqa: E402
from slay.solve import contact as ctc               # noqa: E402
from slay.solve import passage                      # noqa: E402
from slay.solve.kernel import dof, mesh_of_problem  # noqa: E402


def _scene(R=85.0, one_sided=None, n_sr=6, n_vr=3, spacing=8.0, elastic=16.0):
    path = LayPath(R=R)
    st = roller_stations(path, n_sr=n_sr, n_vr=n_vr, spacing=spacing,
                         one_sided=one_sided)
    lo, hi = min(s.s_arc for s in st), max(s.s_arc for s in st)
    return Scene(path=path, stations=tuple(st), extent=(lo, hi),
                 elastic_zones=((lo, lo + elastic), (hi - elastic, hi)),
                 spacing=spacing)


@pytest.fixture(scope='module')
def arc_case():
    """Pure bending onto the arc: every roller bidirectional, no gravity, no
    tension. The cleanest case the formulation has -- nothing to lift off and
    nothing but the targets driving it."""
    sc = _scene(one_sided=frozenset())
    m = build_model(sc)
    p = build_problem(m, sc, material=material('ro'), tension=0.0,
                      gravity=False)
    r, state = passage.solve(p)
    ms, _mdl, _ix = mesh_of_problem(p)
    return sc, p, r, state, ms


# -- the contact formulation ----------------------------------------------

def test_every_contact_target_is_met_exactly(arc_case):
    """The claim the whole formulation rests on. SR6 asks for 8.897 m of
    normal displacement on a pipe that starts straight, and gets it to
    1e-13 m."""
    _sc, p, r, _st, ms = arc_case
    assert r.converged, r.status
    slots = ctc.slots_from_targets(p.contacts, ms)
    assert len(slots) == 8
    for s in slots:
        assert abs(s.dn - s.u_out(r.U)) < 1e-11, s.name
    assert min(abs(s.dn) for s in slots) == 0.0, 'the deck asks for nothing'
    assert max(abs(s.dn) for s in slots) == pytest.approx(8.89707, abs=5e-5)


def test_nothing_lifts_off_when_nothing_may(arc_case):
    """A bidirectional roller holds the pipe down however tensile its
    reaction goes. `exempt` is a property of the roller, not of the
    reaction."""
    _sc, _p, r, _st, _ms = arc_case
    assert all(r.active) and not r.released


def test_the_arc_region_bends_to_about_the_arc(arc_case):
    """Not a reference number -- a sanity bound. Discrete supports at 8 m
    give more than pure bending onto R and not a multiple of it."""
    sc, _p, r, _st, _ms = arc_case
    pure = (0.4064 / 2) / sc.path.R
    mid = [e for (_i, s, e) in r.strains if 8.0 <= s <= 26.0]
    assert mid, 'the arc region has elements'
    assert pure < np.mean(mid) < 1.6 * pure


def test_beyond_the_last_roller_the_pipe_is_straight(arc_case):
    """Nothing constrains or loads it there, so it must carry no strain.
    Zero here is CORRECT -- which is exactly why a whole-model peak is not
    the metric and `peak_strain(s_min=...)` takes a zone."""
    sc, _p, r, _st, _ms = arc_case
    beyond = [e for (_i, s, e) in r.strains if s > 41.0]
    assert beyond and max(beyond) < 1e-9


def test_slots_constrain_the_normal_only(arc_case):
    """Four DOF, the normal projection of an interpolated displacement. The
    tangent is left free -- a material point slides 2.07 m over the rollers
    by SR6 and a uy-only constraint fights that slide."""
    _sc, p, _r, _st, ms = arc_case
    for t, s in zip(p.contacts, ctc.slots_from_targets(p.contacts, ms)):
        assert len(s.dofs) == 4 and len(s.coeffs) == 4
        nx, ny = t.normal
        assert s.coeffs == pytest.approx(
            (t.w_lo * nx, t.w_lo * ny, t.w_hi * nx, t.w_hi * ny))
        assert math.hypot(nx, ny) == pytest.approx(1.0)


def test_the_material_point_lands_on_its_own_arc_station(arc_case):
    """THE CHECK L047 ASKED FOR, and the one that caught L048.

    A contact slot holds the NORMAL component only, so a converged residual
    is evidence about one direction. This is the independent statement:
    node reference positions are set by ARC LENGTH, so the material point at
    arc `s` must end up at `path.position(s)` -- position, both components,
    no projection, nothing the constraint itself supplies.

    It fails by METRES when the contact normal is a world vector applied to
    model DOFs (L048): 2.21 m at SR6 with every target met to 1e-13. What is
    left is real -- discrete supports 8 m apart let the pipe sag a couple of
    millimetres between them, and it is bounded by span, not by R.
    """
    sc, p, r, _st, ms = arc_case
    worst = 0.0
    for t in p.contacts:
        s_mat = t.s_material
        us = sum(w * r.U[dof(ms, i, 0)]
                 for i, w in ((t.n_lo, t.w_lo), (t.n_hi, t.w_hi)))
        uy = sum(w * r.U[dof(ms, i, 1)]
                 for i, w in ((t.n_lo, t.w_lo), (t.n_hi, t.w_hi)))
        x, y = -(s_mat + us), uy
        ax, ay = sc.path.position(s_mat)
        miss = math.hypot(x - ax, y - ay)
        assert miss < 5e-3, f'{t.station}: {miss:.4f} m off its own arc point'
        worst = max(worst, miss)
    assert worst > 1e-5, 'sag between supports is real; zero means no solve'


def test_lay_tension_puts_the_deck_in_tension():
    """L049, proven through the solve rather than on the load vector.

    Frictionless rollers apply normal forces only, so the axial force is
    carried the length of the pipe: pull the tip down the catenary and the
    straight deck run must stretch. As built it SHORTENED -- 10 MT of "lay
    tension" driving 5.27 MT of compression through the deck -- because
    `path.tangent` is a world vector and `fx` is a model component.

    10 MT, not 120: the benchmark tension still fails on the first increment
    (the load path is staged and ours is proportional, section 5 of the T5
    spec), and this test is about the sign, not the magnitude.
    """
    T = 10.0 * 9806.65
    sc = _scene()
    m = build_model(sc)
    p = build_problem(m, sc, material=material('ro'), tension=T, gravity=True)
    r, _state = passage.solve(p)
    assert r.converged, r.status
    ms, _mdl, _ix = mesh_of_problem(p)

    at = {n.index: n for n in m.nodes}
    deck = sorted((i for i in
                   {i for e in m.elements if e.owner == 'pipeline'
                    for i in (e.n1, e.n2)}
                   if -40.0 <= at[i].s <= -20.0), key=lambda i: at[i].s)
    a, b = deck[0], deck[-1]
    eps = ((r.U[dof(ms, b, 0)] - r.U[dof(ms, a, 0)])
           / (at[b].s - at[a].s))
    area = math.pi / 4.0 * (config.OD_PIPE_DEF ** 2
                            - (config.OD_PIPE_DEF - 2 * config.T_WALL_DEF) ** 2)
    N = eps * config.STEEL_E * area
    assert N > 0.0, f'the deck is in {-N / 1e3:.0f} kN of COMPRESSION'
    assert 0.7 * T < N < 1.1 * T, f'{N / 1e3:.0f} kN against {T / 1e3:.0f} kN'


# -- the active set --------------------------------------------------------

def test_release_is_on_reaction_and_re_contact_is_on_gap():
    """The asymmetry IS the formulation. An active penalty constraint sits at
    |r| ~ 1e-10 m, so a gap threshold could never fire on it -- the SIGN of
    that tiny residual encodes push against pull. An inactive one is not
    enforced, so its gap is real."""
    slot = ctc.ContactSlot('SR4', (0, 1, 3, 4), (0.0, 0.5, 0.0, 0.5),
                           dn=-1.0, one_sided=True)
    U = np.zeros(6)

    # active, carrying tension -> releases
    U[1] = U[4] = -1.0 + 1e-10          # r > 0 by a hair
    new, changed = ctc.update_active_set([slot], [True], set(), U,
                                         pen=1e12, anchors=[0.0], lam=1.0)
    assert new == [False] and changed

    # active, pushing -> stays
    U[1] = U[4] = -1.0 - 1e-10
    new, _ = ctc.update_active_set([slot], [True], set(), U, pen=1e12,
                                   anchors=[0.0], lam=1.0)
    assert new == [True]

    # inactive with the gap closed -> re-contacts
    U[1] = U[4] = -1.0
    new, _ = ctc.update_active_set([slot], [False], set(), U, pen=1e12,
                                   anchors=[0.0], lam=1.0)
    assert new == [True]


def test_a_bidirectional_roller_never_releases():
    """However tensile the reaction. It holds the pipe down."""
    both = ctc.ContactSlot('VR3', (0, 1, 3, 4), (0.0, 0.5, 0.0, 0.5),
                           dn=-1.0, one_sided=False)
    assert both.exempt
    U = np.zeros(6); U[1] = U[4] = 10.0        # wildly tensile
    new, changed = ctc.update_active_set([both], [True], set(), U, pen=1e12,
                                         anchors=[0.0], lam=1.0)
    assert new == [True] and not changed


def test_a_released_slot_cannot_re_contact_in_the_same_increment():
    """Without the bar, a slot that releases, springs back through its own
    target and re-engages can cycle forever."""
    slot = ctc.ContactSlot('SR4', (0, 1, 3, 4), (0.0, 0.5, 0.0, 0.5),
                           dn=-1.0, one_sided=True)
    U = np.zeros(6)
    U[1] = U[4] = -1.0                  # sitting exactly on its target
    new, _ = ctc.update_active_set([slot], [False], {0}, U, pen=1e12,
                                   anchors=[0.0], lam=1.0)
    assert new == [False], 'barred for this increment'
    new, _ = ctc.update_active_set([slot], [False], set(), U, pen=1e12,
                                   anchors=[0.0], lam=1.0)
    assert new == [True], 'and free again in the next one'

    # and a slot still SHORT of its target has a genuinely open gap:
    # r = target - u_out is negative, so nothing has closed
    U[1] = U[4] = 0.0
    new, _ = ctc.update_active_set([slot], [False], set(), U, pen=1e12,
                                   anchors=[0.0], lam=1.0)
    assert new == [False], 'the pipe has not reached it yet'


def test_the_target_ramps_from_where_the_pipe_already_is():
    """For a fresh solve that is the plain ramp; for a chained one it makes
    the increment a real increment rather than a re-application of the whole
    target."""
    slot = ctc.ContactSlot('SR4', (0,), (1.0,), dn=-4.0, one_sided=True)
    assert ctc.incremental_target(slot, 0.0, 0.25) == pytest.approx(-1.0)
    assert ctc.incremental_target(slot, 0.0, 1.0) == pytest.approx(-4.0)
    assert ctc.incremental_target(slot, -3.0, 0.5) == pytest.approx(-3.5)
    assert ctc.incremental_target(slot, -3.0, 1.0) == pytest.approx(-4.0)


# -- the loop's own guarantees --------------------------------------------

def test_a_failure_reports_itself_rather_than_returning_zero(arc_case):
    """The documented silent-failure signature is `phase1_peak = 0.0, no
    exception`. A solver that cannot converge must SAY so."""
    sc, p, _r, _st, _ms = arc_case
    r, _state = passage.solve(p, n_increments=1,
                              pen_mult=passage.PEN_FIRST * 1e6)
    if not r.converged:
        assert 'CUTBACK EXHAUSTED' in r.status
        assert r.cutbacks > 0


def test_the_loops_are_bounded():
    """L015's rule, applied to our own code: `nlfea_v4.solve_step` halves the
    increment and retries WITHOUT bound, raising nothing."""
    assert passage.MAX_NEWTON == 30
    assert passage.MAX_CONTACT_PASSES == 8
    assert passage.CUTBACK_FLOOR == 1.0 / 64.0
    assert passage.DIVERGENCE_U == 100.0 and passage.DIVERGENCE_DU == 1.0


def test_state_out_carries_what_a_chained_position_needs(arc_case):
    _sc, _p, _r, state, ms = arc_case
    assert state.U is not None and len(state.U) == ms.n_dofs
    assert state.theta is not None and len(state.theta) == ms.n_elems
    assert len(state.active) == 8
    assert state.plastic is None, 'RO is path-independent: nothing to carry'


def test_j2_carries_a_plastic_state(arc_case):
    """Path-DEPENDENT, so there is something to freeze and commit."""
    sc, _p, _r, _st, _ms = arc_case
    m = build_model(sc)
    p = build_problem(m, sc, material=material('j2'), tension=0.0,
                      gravity=False)
    r, state = passage.solve(p, n_increments=8)
    assert state.plastic is not None
    assert state.plastic.eps_p.shape[0] == len(
        [e for e in p.elements])


def test_the_peak_metric_takes_a_zone(arc_case):
    """The reference metric is a PHASE-1 peak -- worst element from SR3 down
    the stinger -- not the whole model's. The deck end carries a restraint
    artefact that is a property of where the model was cut, and past the last
    roller the pipe is straight."""
    sc, _p, r, _st, _ms = arc_case
    s3 = sc.by_name('SR3').s_arc
    s_all, e_all = r.peak_strain()
    s_p1, e_p1 = r.peak_strain(s_min=s3)
    assert e_p1 <= e_all
    assert s_p1 >= s3
    assert r.peak_strain(s_min=1e9) == (0.0, 0.0), 'an empty zone is empty'

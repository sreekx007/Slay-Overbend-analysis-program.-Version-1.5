"""The staged seed, and the promise that it changes nothing else.

WHAT THIS FIXES. `solve` ramps the contact targets by `lam` but hands over
tension and gravity at FULL VALUE from Newton iteration 1 -- the kernel does
not scale loads and that is deliberate (L050). A cutback therefore shrinks
the targets and nothing else, so when the load itself is beyond reach the
solver reports `CUTBACK EXHAUSTED at lam=0.0000` and there is nothing
further for it to try. Three cases in the 200-case matrix died that way,
all in one corner: 168.3 mm pipe, 12 m spacing, 160 MT, R = 60-70 m.

THE FIX IS AN ORDER, AND THE OPPOSITE ORDER IS A KNOWN DEAD END. Settling
the loads first with the targets held diverges above about 15 MT
(`T5_solve_spec.md` 5). Bending the pipe onto the rollers FIRST and only
then loading it works, because the geometric stiffness that reacts a lay
tension is a property of the bent shape and does not exist before it.

THE PROMISE THAT MATTERS AS MUCH AS THE FIX is that seeding is a FALLBACK.
A case that converged before must converge to the SAME NUMBER afterwards,
bit for bit, or the fix has quietly moved results that were already right.
`test_a_case_that_converges_directly_is_untouched` is that promise.
"""

from __future__ import annotations

import pytest

from slay.data.materials import material
from slay.model.assemble import build_model
from slay.physics.problem import build_problem
from slay.scene.scene import all_bidirectional
from slay.scene.rollers import StationRole
from slay.solve.passage import solve
from slay.study import sweep

TON = 9806.65

# The corner that failed: smallest pipe, widest spacing, highest tension,
# tightest radius. Every one of those pushes the same way.
HARD = dict(R=70.0, spacing=12.0, tension_mt=160.0, OD=0.1683, t_wall=0.0110)
EASY = dict(R=85.0, spacing=9.0, tension_mt=120.0, OD=0.4064, t_wall=0.0210)

_CACHE = {}


def _passage(**kw):
    """A plain-pipe passage, cached: each of these is a real solve."""
    key = tuple(sorted(kw.items()))
    if key not in _CACHE:
        OD = kw['OD']
        sc = sweep.scene_for(R=kw['R'], spacing=kw['spacing'], L_comp=0.0)
        _CACHE[key] = sweep.run(
            sc, None, L_comp=0.0, step=2.0 * OD,
            tension=kw['tension_mt'] * TON, material=material('j2'),
            OD=OD, t_wall=kw['t_wall'], **kw.get('extra', {}))
    return _CACHE[key]


# ---------------------------------------------------------------------------
# all_bidirectional -- step 1 of the sequence
# ---------------------------------------------------------------------------

def test_holding_every_roller_changes_only_one_sidedness():
    """Geometrically identical, or a displacement field could not carry."""
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0)
    held = all_bidirectional(sc)
    assert held.extent == sc.extent
    assert held.spacing == sc.spacing
    assert held.elastic_zones == sc.elastic_zones
    assert [s.name for s in held.stations] == [s.name for s in sc.stations]
    for a, b in zip(held.stations, sc.stations):
        assert a.s_arc == pytest.approx(b.s_arc)
        assert (a.x, a.y) == pytest.approx((b.x, b.y))
    # ... and that the ONE difference is actually there.
    assert any(s.one_sided for s in sc.stations
               if s.role is StationRole.CONTACT)
    assert not any(s.one_sided for s in held.stations)


# ---------------------------------------------------------------------------
# the failure, and the fix
# ---------------------------------------------------------------------------

def test_the_hard_corner_fails_without_a_seed():
    """The defect, pinned. If this ever passes, the corner moved and the
    rest of this file is testing something that no longer happens."""
    OD = HARD['OD']
    sc = sweep.scene_for(R=HARD['R'], spacing=HARD['spacing'], L_comp=0.0)
    out = sweep.run(sc, None, L_comp=0.0, step=2.0 * OD, seed=False,
                    tension=HARD['tension_mt'] * TON, material=material('j2'),
                    OD=OD, t_wall=HARD['t_wall'])
    assert not out[0].converged
    assert 'lam=0.0000' in out[0].result.status, (
        'the first increment must be the one that fails -- a later lam '
        'would mean cutback was doing something and the diagnosis differs')


def test_the_hard_corner_converges_with_a_seed():
    out = _passage(**HARD)
    assert all(p.converged for p in out), [p.result.status for p in out]
    assert out[0].seeded, 'position 0 should have needed the seed'
    peak = max(abs(e) for p in out for (_i, _s, e) in p.result.strains)
    assert 0.005 < peak < 0.05, f'implausible peak strain {peak}'


def test_only_the_first_position_needs_seeding():
    """A later position starts from a pipe that is already bent, so the
    stiffness the seed exists to create is already there."""
    out = _passage(**HARD)
    assert [p.seeded for p in out][1:] == [False] * (len(out) - 1)


def test_a_case_that_converges_directly_is_untouched():
    """THE PROMISE. Seeding is a fallback, so an easy case must take the
    same path and reach the same number to the last bit."""
    OD = EASY['OD']
    sc = sweep.scene_for(R=EASY['R'], spacing=EASY['spacing'], L_comp=0.0)
    common = dict(L_comp=0.0, step=2.0 * OD, OD=OD, t_wall=EASY['t_wall'],
                  tension=EASY['tension_mt'] * TON, material=material('j2'))
    with_seed = sweep.run(sc, None, seed=True, **common)
    without = sweep.run(sc, None, seed=False, **common)
    assert not any(p.seeded for p in with_seed)
    assert len(with_seed) == len(without)
    for a, b in zip(with_seed, without):
        ea = [e for (_i, _s, e) in a.result.strains]
        eb = [e for (_i, _s, e) in b.result.strains]
        assert ea == eb, 'seeding changed a case that did not need it'


# ---------------------------------------------------------------------------
# seed_state itself
# ---------------------------------------------------------------------------

def test_seed_state_returns_a_usable_state():
    OD = HARD['OD']
    sc = sweep.scene_for(R=HARD['R'], spacing=HARD['spacing'], L_comp=0.0)
    s_centre = sweep.start_centre(sc, 0.0)
    m = build_model(sc, None, s_centre=s_centre,
                    extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)
    kw = dict(shift=0.0, s_centre=s_centre, OD=OD, t_wall=HARD['t_wall'],
              tension=HARD['tension_mt'] * TON, vertical_at=(lo,),
              elastic_spans=((lo, hi),))
    state, note = sweep.seed_state(m, sc, kw)
    assert state is not None and note == 'seeded'

    # The real solve, chained onto it, is the one that would have failed.
    p = build_problem(m, sc, material=material('j2'), gravity=True, **kw)
    direct, _ = solve(p)
    assert not direct.converged
    chained, _ = solve(p, state_in=state)
    assert chained.converged, chained.status


def test_the_seed_is_elastic_throughout():
    """J2 is incremental and path-dependent, so yielding during seeding
    would write a plastic history the real load path never went through.

    Checked on the SOURCE, because the alternative is comparing plastic
    states and that is exactly the thing this guards against being subtle.
    """
    import inspect
    src = inspect.getsource(sweep.seed_state)
    assert 'material=None' in src, (
        'seed_state must force the elastic material; passing the case '
        "material through would accumulate plasticity on a path the real "
        'solve never takes')

"""`slay.study.staged` -- the sequence as a workflow, not a script.

`test_stage_run.py` holds the NUMBERS the sequence produces and what they
reproduce. This file holds the things that became checkable once it was a
module: that it poses what it says it poses, that it owns no copy of library
code, and that it reports nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

pytest.importorskip('numpy')
pytest.importorskip('nlfea_v4')

from slay.model.assemble import build_model                 # noqa: E402
from slay.physics.problem import differs_only_in_contact    # noqa: E402
from slay.scene.scene import all_bidirectional              # noqa: E402
from slay.study import staged                               # noqa: E402


@pytest.fixture(scope='module')
def posed():
    """The four Problems, POSED AND NOT SOLVED -- which is itself the point
    of `problems` being separate from `run`."""
    sc = staged.scene_for(R=85.0, spacing=8.0)
    return sc, build_model(sc), staged.problems(build_model(sc), sc)


# ---------------------------------------------------------------------------
# it poses what it says it poses
# ---------------------------------------------------------------------------

def test_the_sequence_is_four_steps_in_the_ruled_order(posed):
    _sc, _m, ps = posed
    assert len(ps) == 4
    assert [lab.split()[0] for lab, _p in ps] == ['1', '2', '3', '4']


def test_only_step_one_holds_every_roller(posed):
    """Step 1 runs on the all-bidirectional scene; every later step runs on
    the real one. Checked on the POSED contacts, so it does not depend on a
    solve having gone a particular way."""
    sc, _m, ps = posed
    held = {c.station for c in ps[0][1].contacts if not c.one_sided}
    real = {c.station for c in ps[1][1].contacts if not c.one_sided}
    assert len(held) > len(real), 'step 1 must hold more than step 2'
    assert all(not c.one_sided for c in ps[0][1].contacts)
    assert any(c.one_sided for c in ps[1][1].contacts)


def test_gravity_and_tension_arrive_when_the_sequence_says(posed):
    _sc, _m, ps = posed

    def has(p, prefix):
        return any(str(getattr(l, 'source', '')).startswith(prefix)
                   for l in p.loads)

    assert not has(ps[0][1], 'self_weight') and not has(ps[0][1], 'tension')
    assert has(ps[1][1], 'self_weight') and not has(ps[1][1], 'tension')
    assert has(ps[2][1], 'self_weight') and has(ps[2][1], 'tension')
    assert has(ps[3][1], 'self_weight') and has(ps[3][1], 'tension')


def test_plasticity_arrives_only_at_step_four(posed):
    """Steps 1-3 are the kernel's LINEAR ELASTIC path (`material=None`);
    step 4 is incremental J2, which is what "activate plasticity" means."""
    _sc, _m, ps = posed
    assert [p.material for _l, p in ps[:3]] == [None, None, None]
    assert ps[3][1].material is not None


def test_steps_three_and_four_differ_ONLY_in_the_material(posed):
    """"everything else held" is a claim, so it is asserted. The two
    Problems must agree on nodes, elements, sections, contacts and loads."""
    _sc, _m, ps = posed
    a, b = ps[2][1], ps[3][1]
    assert a.material is None and b.material is not None
    for field in ('nodes', 'elements', 'connectors', 'contacts', 'loads',
                  'restraints', 'elastic_spans', 'R'):
        assert getattr(a, field) == getattr(b, field), field


def test_steps_two_and_three_differ_only_by_the_tension(posed):
    _sc, _m, ps = posed
    a, b = ps[1][1], ps[2][1]
    assert a.contacts == b.contacts and a.nodes == b.nodes
    assert len(b.loads) > len(a.loads)


# ---------------------------------------------------------------------------
# it owns no copy of library code, and reports nothing
# ---------------------------------------------------------------------------

def test_it_uses_the_LIBRARY_all_bidirectional(posed):
    """There were three copies of this before the move. The scene step 1 is
    posed on must be exactly what `scene.scene.all_bidirectional` returns."""
    sc, m, ps = posed
    from slay.physics.problem import build_problem
    mine = build_problem(m, all_bidirectional(sc), material=None,
                         gravity=False, tension=0.0)
    assert ps[0][1].contacts == mine.contacts


def test_the_module_reports_nothing():
    """`report` is ABOVE `study` in the layer order, so this module could
    not call `report.passage.zone` even if it wanted to. That is the rule
    working: the duplicate window could be DELETED rather than moved,
    because it was never this layer's to own."""
    # CODE, not prose: the docstring names both on purpose, to say why they
    # are absent. Grepping the whole file would fail on its own explanation.
    src = (REPO / 'rebuild' / 'slay' / 'study' / 'staged.py').read_text()
    code = [l for l in src.splitlines()
            if l.startswith(('import ', 'from '))]
    assert not any('report' in l for l in code), code
    assert not hasattr(staged, 'report_zone')
    assert not hasattr(staged, 'peak_in_zone')
    assert not hasattr(staged, 'DROP_AT_TIP')
    assert not hasattr(staged, 'station_profile')


def test_the_steps_are_data_a_caller_can_read():
    """`STEPS` is a tuple, not a function body, so a caller can see what is
    about to run without tracing code."""
    assert len(staged.STEPS) == 4
    labels = [s[0] for s in staged.STEPS]
    assert all(isinstance(l, str) and l for l in labels)
    # held only on step 1; material only on step 4
    assert [s[1] for s in staged.STEPS] == [True, False, False, False]
    assert [s[4] for s in staged.STEPS] == [None, None, None, 'j2']


# ---------------------------------------------------------------------------
# the run loop
# ---------------------------------------------------------------------------

def test_a_run_chains_state_and_returns_Stages():
    """State is chained step to step -- step 4's plasticity acts on the
    stress state steps 1-3 built, not on a virgin pipe."""
    sc, stages, state = staged.run(R=85.0, tension_mt=120.0, spacing=8.0)
    assert len(stages) == 4 and state is not None
    assert [s.index for s in stages] == [0, 1, 2, 3]
    assert all(s.converged for s in stages)
    assert all(s.problem is not None and s.result is not None for s in stages)
    assert sc.spacing == pytest.approx(8.0)

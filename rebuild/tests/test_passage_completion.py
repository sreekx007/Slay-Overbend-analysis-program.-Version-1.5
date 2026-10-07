"""A truncated passage must be IMPOSSIBLE to mistake for a complete one.

L101: five of the seven TABLE XXXII / XXXIII shroud cases were tabulated
against Paper 1 having swept between 6.3% and 38.4% of the travel they
needed, and the numbers looked entirely ordinary -- same columns, same
magnitudes, bending moments inside a 2.1% band across all seven. Nothing
anywhere said the component had not reached the roller.

Three gaps let that through and each one gets a test here:

  * `sweep.run` returned a truncated list indistinguishable from a full one
  * `report.profile` wrote an artifact with nothing in it saying so
  * the study tool filtered the sections table on `in_band`, which drops the
    single row the diverged position wrote

The fix is one measurement -- travel reached against travel required --
computed in `sweep.completion`, carried in the profile's case context, and
read back through `tools/profile_status`. These tests pin all three links,
because the chain is only as good as the weakest and the weakest is where
the bug lived.
"""

import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO / 'tools') not in sys.path:
    sys.path.insert(0, str(REPO / 'tools'))

from slay.study import sweep                                    # noqa: E402
import profile_status                                           # noqa: E402


class _Result:
    def __init__(self, converged, status=''):
        self.converged = converged
        self.status = status or ('ok' if converged else 'CUTBACK EXHAUSTED')


class _Pos:
    """Just enough of a `Position` for `completion`: shift and converged."""
    def __init__(self, index, shift, converged=True, status=''):
        self.index, self.shift = index, shift
        self.result = _Result(converged, status)

    @property
    def converged(self):
        return self.result.converged


def _passage(shifts, fail_from=None):
    return [_Pos(i, s, converged=(fail_from is None or i < fail_from))
            for i, s in enumerate(shifts)]


# ---------------------------------------------------------------------------
# the measurement itself
# ---------------------------------------------------------------------------

def test_a_passage_that_reaches_the_sweep_length_is_complete():
    L = 8.128
    total = sweep.sweep_length(L)
    c = sweep.completion(_passage([0.0, 4.0, total]), L)
    assert c.complete
    assert c.ran == pytest.approx(total)
    assert c.fraction == pytest.approx(1.0)
    assert c.failed_at is None


def test_a_passage_that_stops_at_a_diverged_position_is_not_complete():
    """S2-6's real shape: five converged positions, the sixth diverged."""
    L = 8.128
    shifts = [0.0, 0.128, 0.8128, 1.0647, 1.6256, 2.4384]
    c = sweep.completion(_passage(shifts, fail_from=5), L)
    assert not c.complete
    assert c.ran == pytest.approx(1.6256)
    assert c.total == pytest.approx(10.128)
    assert c.failed_at == pytest.approx(2.4384)
    assert c.fraction == pytest.approx(1.6256 / 10.128)
    assert 'CUTBACK' in c.status


def test_every_position_converging_is_not_enough():
    """THE TRAP THE OLD n_ok/n CHECK FELL INTO. No position diverged and the
    passage still did not happen -- the schedule ended short. Counting
    converged positions cannot see this; measuring travel can."""
    L = 8.128
    c = sweep.completion(_passage([0.0, 1.0, 2.0]), L)
    assert c.n_converged == c.n_positions == 3
    assert not c.complete
    assert 'short' in c.status


def test_the_fraction_is_of_travel_not_of_positions():
    """Nine positions of ten is not 90% of anything: the schedule's steps are
    uneven, because `critical_shifts` inserts the edge crossings."""
    L = 8.128
    shifts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 10.128]
    c = sweep.completion(_passage(shifts, fail_from=9), L)
    assert c.n_converged == 9 and c.n_positions == 10
    assert c.fraction == pytest.approx(0.8 / 10.128)


def test_an_empty_passage_is_not_complete():
    assert not sweep.completion([], 8.128).complete


# ---------------------------------------------------------------------------
# the artifact carries it, and the reader reads it back
# ---------------------------------------------------------------------------

def _write_geometry(tmp_path, **ctx):
    """A minimal two-row geometry table -- only the context is under test."""
    stem = tmp_path / 'case'
    cols = ['profile_schema_version', 'case_id', 'table', 'passage_complete',
            'sweep_total', 'sweep_ran', 'sample']
    with open(str(stem) + '.geometry.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for i in (0, 1):
            row = dict(profile_schema_version='1.5.0', case_id='case',
                       table='geometry', sample=i)
            row.update(ctx)
            w.writerow(row)
    return stem


def test_the_reader_reports_a_complete_passage_as_complete(tmp_path):
    stem = _write_geometry(tmp_path, passage_complete='True',
                           sweep_total=10.128, sweep_ran=10.128)
    st = profile_status.status(stem)
    assert st.complete is True
    assert st.flag() == ''
    assert profile_status.require_complete(stem) is not None


def test_the_reader_reports_a_truncated_passage_and_refuses_comparison(tmp_path):
    stem = _write_geometry(tmp_path, passage_complete='False',
                           sweep_total=10.128, sweep_ran=1.6256)
    st = profile_status.status(stem)
    assert st.complete is False
    assert st.fraction == pytest.approx(1.6256 / 10.128)
    assert '16%' in st.flag()
    with pytest.raises(ValueError, match='refusing to compare'):
        profile_status.require_complete(stem)


def test_a_file_from_before_the_columns_existed_reads_UNKNOWN_not_complete(
        tmp_path):
    """An old artifact is evidence of NOTHING about its passage. Reading an
    absent column as True is the whole failure wearing a different hat."""
    stem = tmp_path / 'old'
    with open(str(stem) + '.geometry.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, ['profile_schema_version', 'case_id', 'table'])
        w.writeheader()
        w.writerow(dict(profile_schema_version='1.4.0', case_id='old',
                        table='geometry'))
    st = profile_status.status(stem)
    assert st.complete is None
    assert not st.known
    assert st.flag().strip() == '?'
    with pytest.raises(ValueError, match='UNKNOWN'):
        profile_status.require_complete(stem)


def test_the_schema_declares_the_three_status_columns():
    from slay.report import profile_schema as ps
    names = {f.name for f in ps.CONTEXT}
    assert {'passage_complete', 'sweep_total', 'sweep_ran'} <= names
    assert ps.PROFILE_SCHEMA_VERSION >= '1.5.0'
    for f in ps.CONTEXT:
        if f.name in ('passage_complete', 'sweep_total', 'sweep_ran'):
            assert f.per == 'case'


def test_case_context_without_a_completion_writes_empty_not_true():
    """`completion=None` must not read back as a complete passage."""
    from slay.report import profile as rprof
    import inspect
    sig = inspect.signature(rprof.case_context)
    assert sig.parameters['completion'].default is None


# ---------------------------------------------------------------------------
# L105 -- the lay tension follows the LOAD STATION, not the steel
# ---------------------------------------------------------------------------
#
# `lay_tension` took no `shift` and chose its node by `|n.s - st.s_arc|` in
# MATERIAL coordinates, so the 100 MT stayed on the same piece of pipe for a
# whole passage while the terminal contact walked inboard by the travel. From
# the first position onward the model carried a free cantilever of length
# `shift` with the full lay tension on its unsupported tip, and past about
# 2.4 m of travel it had no equilibrium -- which is the cliff L102 recorded
# and could not explain.

from slay.data.materials import material                        # noqa: E402
from slay.model.assemble import build_model                     # noqa: E402
from slay.physics.problem import build_problem                  # noqa: E402

TON = 9806.65
_D = 0.4064


def _plain(R=70.0, spacing=9.0, L_comp=8.128):
    sc = sweep.scene_for(R=R, spacing=spacing, L_comp=L_comp)
    model = build_model(sc, None, s_centre=sweep.start_centre(sc, L_comp),
                        extra_stations=sweep._required_stations(sc))
    lo, hi = sweep.buffer_span(sc)
    return sc, model, dict(tension=100.0 * TON, material=material('j2'),
                           vertical_at=(lo,), elastic_spans=((lo, hi),))


def _tension_at(pr, s_of):
    """Where the lay tension ACTS, as the material position of its centroid.

    The load is interpolated across the two bracketing nodes, so there are
    one or two of them and the single meaningful position is the weighted
    mean -- the same quantity a contact slot's `s_material` names.
    """
    ld = [l for l in pr.loads
          if str(getattr(l, 'source', '')).startswith('tension:')]
    assert 1 <= len(ld) <= 2, f'one or two lay-tension loads, got {len(ld)}'
    tot = sum(abs(l.fx) + abs(l.fy) for l in ld)
    return sum(s_of[l.node] * (abs(l.fx) + abs(l.fy)) for l in ld) / tot


def _tension_resultant(pr):
    ld = [l for l in pr.loads
          if str(getattr(l, 'source', '')).startswith('tension:')]
    return (sum(l.fx for l in ld), sum(l.fy for l in ld))


def _s_of(model):
    return {n.index: n.s for n in model.nodes}


def test_the_tension_node_moves_with_the_sweep():
    """The load acts where the pipe leaves the stinger NOW."""
    sc, model, kw = _plain()
    s_of = _s_of(model)
    seen = [_tension_at(build_problem(model, sc, shift=sh, **kw), s_of)
            for sh in (0.0, 2.0, 4.0, 6.0)]
    # it walks inboard, one metre of material per metre of travel
    assert seen == sorted(seen, reverse=True), seen
    assert seen[0] - seen[-1] == pytest.approx(6.0, abs=0.05), seen


def test_the_tension_slides_between_nodes_instead_of_jumping():
    """The second half of L105, and it only bites in a CHAINED sweep.

    `solve.passage` applies loads at full value from the first Newton
    iteration -- cutback scales the contact targets and cannot touch a load
    -- so a tension that SNAPS from one node to the next moves 100 MT a
    whole element in one unrampable step. Interpolated, the transfer is
    continuous in `shift` and the resultant never changes.
    """
    sc, model, kw = _plain()
    s_of = _s_of(model)
    el = sorted(s_of.values())
    el = el[1] - el[0]
    prev = None
    want = _tension_resultant(build_problem(model, sc, shift=0.0, **kw))
    for k in range(25):
        sh = k * el / 8.0
        pr = build_problem(model, sc, shift=sh, **kw)
        at = _tension_at(pr, s_of)
        assert _tension_resultant(pr) == pytest.approx(want, rel=1e-12)
        if prev is not None:
            step = abs(at - prev)
            assert step < 0.6 * el, (
                f'the lay tension jumped {step:.3f} m -- more than half an '
                f'element -- between shift {sh - el / 8:.3f} and {sh:.3f}')
        prev = at


def test_at_shift_zero_the_tension_lands_where_it_always_did():
    """The fix must not move a single-position result. At shift 0 the
    material under the LOAD station IS the node the old code picked."""
    sc, model, kw = _plain()
    s_of = _s_of(model)
    pr = build_problem(model, sc, shift=0.0, **kw)
    assert _tension_at(pr, s_of) == pytest.approx(max(s_of.values()))


def test_the_tension_lands_on_the_terminal_contact_not_past_it():
    """THE DEFECT, as the geometry it was. The load must never sit outboard
    of the last contact: pipe past the terminal slot is unconstrained, and
    100 MT on the tip of an unconstrained cantilever is what diverged."""
    sc, model, kw = _plain()
    s_of = _s_of(model)
    for sh in (0.0, 1.0, 2.4, 4.0, 8.0, 10.128):
        pr = build_problem(model, sc, shift=sh, **kw)
        slot = max(c.s_material for c in pr.contacts)
        over = _tension_at(pr, s_of) - slot
        assert abs(over) < 1.0, (
            f'at shift {sh} the lay tension sits {over:.3f} m outboard of '
            f'the terminal contact, on unconstrained pipe')


def test_the_passage_no_longer_dies_at_two_and_a_half_metres():
    """The cliff itself, as a solve. Before L105 every one of these
    diverged; the first converged travel beyond 2.4 m is the whole claim."""
    from slay.solve.passage import solve
    sc, model, kw = _plain()
    for sh in (2.4, 4.0, 8.0):
        r, _ = solve(build_problem(model, sc, shift=sh, **kw))
        assert r.converged, f'shift {sh}: {r.status}'

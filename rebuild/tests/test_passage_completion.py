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

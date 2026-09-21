"""The trial log is machine reference, so a machine checks it.

`docs/TRIAL_LOG.yaml` records what was TRIED, failures included, so a later
session does not re-run a dead end and every number in a spec can be traced
to the trial that produced it. It is only worth anything if its `lesson`
pointers still resolve and its `refs` still exist -- a dangling pointer turns
a trial into a rumour.

WHY FAILURES ARE CHECKED HARDEST. A successful trial gets re-run and
re-verified by ordinary work; a failed one is read once, believed, and never
revisited. `test_failures_carry_numbers` is there because "it diverged" is
worth nothing to the next session and "NaN at 30 MT, singular matrix" is
worth an afternoon.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip('yaml')

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / 'docs' / 'TRIAL_LOG.yaml'
REGISTER = REPO / 'docs' / 'BUILD_LESSONS.yaml'

OUTCOMES = {'success', 'failure', 'partial', 'measurement'}
REQUIRED = {'id', 'date', 'goal', 'action', 'case', 'outcome', 'evidence',
            'verdict', 'lesson', 'refs'}
DIGITS = set('0123456789')


@pytest.fixture(scope='module')
def trials():
    return yaml.safe_load(LOG.read_text())


@pytest.fixture(scope='module')
def lesson_ids():
    return {e['id'] for e in yaml.safe_load(REGISTER.read_text())}


def _lessons(trial):
    if trial['lesson'] == '-':
        return []
    return [x.strip() for x in str(trial['lesson']).split(',')]


def test_schema(trials):
    assert trials, 'the log is not empty'
    for t in trials:
        assert set(t) == REQUIRED, (t.get('id'), set(t) ^ REQUIRED)
        assert t['outcome'] in OUTCOMES, (t['id'], t['outcome'])
        assert isinstance(t['refs'], list) and t['refs'], t['id']


def test_ids_are_unique_and_ordered(trials):
    ids = [t['id'] for t in trials]
    assert len(set(ids)) == len(ids), 'a reused id points at two trials'
    for i in ids:
        assert i.startswith('T') and len(i) == 4 and set(i[1:]) <= DIGITS, i
    assert ids == sorted(ids), 'the log is chronological; append, do not insert'


def test_every_lesson_pointer_resolves(trials, lesson_ids):
    """A trial that produced a lesson names it, and the lesson exists."""
    dangling = [(t['id'], ref) for t in trials for ref in _lessons(t)
                if ref not in lesson_ids]
    assert not dangling, dangling


def test_every_ref_exists(trials):
    missing = [(t['id'], r) for t in trials for r in t['refs']
               if not (REPO / r.split('::')[0]).exists()]
    assert not missing, missing


def test_failures_carry_numbers(trials):
    """A failure recorded without measurements is a failure that will be
    re-run. Every non-success says what was observed, in digits."""
    vague = [t['id'] for t in trials
             if t['outcome'] in ('failure', 'partial')
             and not (set(str(t['evidence'])) & DIGITS)]
    assert not vague, vague


def test_the_header_count_matches(trials):
    """The header states how many entries there are. Appending without
    updating it is how a register starts drifting from its own summary."""
    head = LOG.read_text().split('\n- id:')[0]
    stated = [ln for ln in head.splitlines() if ln.startswith('# entries:')]
    assert stated, 'the header states an entry count'
    assert int(stated[0].split(':')[1]) == len(trials)

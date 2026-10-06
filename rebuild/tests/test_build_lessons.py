"""The lessons register is machine reference, so a machine checks it.

`docs/BUILD_LESSONS.yaml` is only useful if its `detect` field still names
tests that exist. A renamed test silently turns a lesson into a story about
something that used to be caught -- which is exactly the failure mode the
register was written to stop (G8).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip('yaml')

REPO = Path(__file__).resolve().parents[2]
REGISTER = REPO / 'docs' / 'BUILD_LESSONS.yaml'
TESTS = Path(__file__).resolve().parent

AREAS = {'kernel', 'model', 'physics', 'solve', 'joint', 'plot',
         'process', 'measure'}
CLASSES = {'defect', 'finding', 'ruling'}
REQUIRED = {'id', 'area', 'class', 'symptom', 'cause', 'rule', 'detect',
            'refs', 'date'}


@pytest.fixture(scope='module')
def entries():
    return yaml.safe_load(REGISTER.read_text())


def _detect_names(entry):
    """Local test names only.

    A name may be prefixed `upstream:` when the guarding test lives in
    `Slay-ILS-Designer-V1.0` rather than here -- L037's does, because the
    defect is in a mirrored file we are forbidden to edit (G7). Those are
    recorded so the pointer is not lost, but this repo cannot check them.
    """
    if entry['detect'] == '-':
        return []
    return [t.strip() for t in entry['detect'].split(',')
            if not t.strip().startswith('upstream:')]


def _all_detect(entry):
    if entry['detect'] == '-':
        return []
    return [t.strip() for t in entry['detect'].split(',')]


def test_register_exists_and_parses(entries):
    assert isinstance(entries, list) and entries


def test_schema_holds(entries):
    for e in entries:
        assert REQUIRED <= set(e), (e.get('id'), REQUIRED - set(e))
        assert e['area'] in AREAS, e['id']
        assert e['class'] in CLASSES, e['id']
        assert re.fullmatch(r'L\d{3}', e['id']), e['id']


def test_the_header_count_matches(entries):
    """The header states how many entries there are, and until 6 Oct it said
    62 against 93 -- a register drifting from its own summary, which is the
    whole failure mode this file exists to stop (L093). `test_trial_log` has
    carried this check since it was written; this one did not, so the drift
    accumulated silently for 31 entries.
    """
    head = REGISTER.read_text().split('\n- id:')[0]
    stated = [ln for ln in head.splitlines() if ln.startswith('# entries:')]
    assert stated, 'the header states an entry count'
    assert int(stated[0].split(':')[1]) == len(entries)


def test_ids_are_unique_and_never_reused(entries):
    ids = [e['id'] for e in entries]
    assert len(set(ids)) == len(ids)


def test_every_named_test_still_exists(entries):
    have = set()
    for path in TESTS.glob('test_*.py'):
        have |= set(re.findall(r'^def (test_\w+)', path.read_text(), re.M))
    missing = [(e['id'], t) for e in entries
               for t in _detect_names(e) if t not in have]
    assert not missing, f'renamed or deleted: {missing}'


def test_every_referenced_file_still_exists(entries):
    missing = [(e['id'], r) for e in entries for r in e['refs']
               if not (REPO / r.split('::')[0].split(':')[0]).exists()]
    assert not missing, missing


def test_upstream_pointers_are_well_formed(entries):
    """An `upstream:` name is a pointer this repo cannot follow, so the
    least it can do is be shaped like a test name."""
    for e in entries:
        for t in _all_detect(e):
            if t.startswith('upstream:'):
                assert re.fullmatch(r'upstream:test_\w+', t), (e['id'], t)


def test_every_defect_is_detectable(entries):
    """A finding may be unguarded. A defect that once produced wrong numbers
    may not -- it names the test that fails if it comes back."""
    undetected = [e['id'] for e in entries
                  if e['class'] == 'defect' and not _all_detect(e)
                  and e['area'] != 'process']
    assert not undetected, undetected

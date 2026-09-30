"""The PROFILE contract, and the checks that make writing a wrong one fail.

These tests are fast on purpose. The expensive question -- does a profile
emitted from a real passage draw the same figure the generating plotter drew
-- is answered once, by hand, and recorded in TRIAL_LOG. The question HERE is
narrower and needs answering on every commit: does the contract describe what
it claims, and does the writer refuse a file that breaks it?

G8 applies: "it wrote a file" is not verification. Every test below asserts a
NUMBER or a REFUSAL.
"""

from __future__ import annotations

import csv
import json

import pytest

from slay.report import profile as rprof
from slay.report import profile_schema as ps

DTYPES = {'float', 'int', 'str', 'bool'}
PER = {'case', 'position', 'sample'}


# ---------------------------------------------------------------------------
# the contract describes itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('table', sorted(ps.TABLES))
def test_columns_are_unique(table):
    h = ps.header(table)
    assert len(h) == len(set(h)), f'{table} declares a column twice'


@pytest.mark.parametrize('table', sorted(ps.TABLES))
def test_every_field_is_fully_declared(table):
    for f in ps.TABLES[table]:
        assert f.dtype in DTYPES, f'{table}.{f.name} dtype {f.dtype!r}'
        assert f.per in PER, f'{table}.{f.name} per {f.per!r}'
        assert f.unit, f'{table}.{f.name} has no unit; "-" means genuinely '\
                       'dimensionless and is different from silence'
        # Present and not a placeholder. Not a length contest: 'roller
        # spacing' says everything there is to say about `spacing`.
        assert len(f.about.strip()) > 5, f'{table}.{f.name} has no about'


@pytest.mark.parametrize('table', sorted(ps.TABLES))
def test_identity_is_on_every_table(table):
    h = ps.header(table)
    for c in ('profile_schema_version', 'case_id', 'table'):
        assert c in h, f'{table} is anonymous without {c}'


def test_grains_are_what_they_claim():
    # geometry and sections vary per position; stations do not, because
    # rollers do not move when the pipe does.
    assert 'step' in ps.header('geometry')
    assert 'step' in ps.header('sections')
    assert 'step' not in ps.header('stations')


def test_section_and_contact_owner_are_separate_columns():
    """The one distinction a shroud depends on.

    `section_at` answers what carries the BENDING, `contact_at` what a roller
    TOUCHES. A shroud moves the second and not the first, so collapsing them
    into one column would make GD-SH indistinguishable from a stiffener --
    and would have it drawn at a section OD the model does not have (L073).
    """
    h = ps.header('geometry')
    assert 'section_owner' in h and 'contact_owner' in h
    assert 'OD_section' in h and 'y_contact' in h


def test_sections_carries_both_element_ends():
    """Not a midpoint (L071)."""
    h = ps.header('sections')
    for c in ('s_material_0', 's_material_1', 'x_0', 'x_1'):
        assert c in h


def test_unknown_refuses_a_typo():
    assert ps.unknown('geometry', ['x', 'y']) == []
    assert ps.unknown('geometry', ['x', 'OD_sektion']) == ['OD_sektion']


def test_unknown_table_says_so():
    with pytest.raises(KeyError):
        ps.header('nodes')


@pytest.mark.parametrize('table', sorted(ps.TABLES))
def test_as_dict_is_serialisable_and_complete(table):
    d = ps.as_dict(table)
    round_trip = json.loads(json.dumps(d))
    assert round_trip['table'] == table
    assert round_trip['profile_schema_version'] == ps.PROFILE_SCHEMA_VERSION
    assert [f['name'] for f in round_trip['fields']] == ps.header(table)
    assert all('per' in f for f in round_trip['fields'])


def test_constants_and_positions_partition_sensibly():
    con = set(ps.constants('geometry'))
    pos = set(ps.per_position('geometry'))
    assert 'R' in con and 'OD' in con and 'case_id' in con
    assert 'step' in pos and 'shift' in pos
    assert not (con & pos)
    assert 's_material' not in con and 's_material' not in pos


def test_profile_version_is_independent_of_the_case_version():
    from slay.report import schema as cs
    assert ps.PROFILE_SCHEMA_VERSION != '' and cs.SCHEMA_VERSION != ''
    # They are separate strings, not the same object re-exported: the two
    # artifacts move for different reasons and a reader of one must not be
    # told to distrust it because the other changed.
    assert ps.PROFILE_SCHEMA_VERSION is not cs.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# the writer refuses what the contract forbids
# ---------------------------------------------------------------------------

def _stations(n=3, **over):
    rows = []
    for k in range(n):
        r = dict(profile_schema_version=ps.PROFILE_SCHEMA_VERSION,
                 case_id='c1', table='stations', station=f'SR{k}',
                 role='CONTACT', s_station=9.0 * k, x=-9.0 * k, y=0.4 * k,
                 radius=0.2, one_sided=True)
        r.update(over)
        rows.append(r)
    return rows


def test_write_round_trips(tmp_path):
    rows = _stations()
    p = tmp_path / 'c1.stations.csv'
    got = rprof.write_table('stations', rows, p)
    assert got['rows'] == 3
    back = list(csv.DictReader(p.open()))
    assert [r['station'] for r in back] == ['SR0', 'SR1', 'SR2']
    assert back[1]['s_station'] == '9.0'
    assert back[0]['one_sided'] == 'true'       # not 'True': CSV, not Python
    side = json.loads((tmp_path / 'c1.stations.csv.schema.json').read_text())
    assert side['table'] == 'stations'
    assert ps.unknown('stations', back[0].keys()) == []


def test_write_refuses_an_undeclared_column(tmp_path):
    rows = _stations()
    for r in rows:
        r['colour'] = 'red'
    with pytest.raises(ValueError, match='undeclared'):
        rprof.write_table('stations', rows, tmp_path / 'x.csv')


def test_write_refuses_a_missing_declared_column(tmp_path):
    rows = _stations()
    for r in rows:
        del r['radius']
    with pytest.raises(ValueError, match='missing declared'):
        rprof.write_table('stations', rows, tmp_path / 'x.csv')


def test_write_refuses_a_case_column_that_moves(tmp_path):
    """The failure this check exists for.

    `case_id` is declared per=case. A writer that let a per-row value leak
    into it would produce a file whose three tables describe different cases
    -- and nothing downstream would notice, because every row would still
    parse.
    """
    rows = _stations()
    rows[1]['case_id'] = 'c2'
    with pytest.raises(ValueError, match='per=case'):
        rprof.write_table('stations', rows, tmp_path / 'x.csv')


def test_write_refuses_an_empty_table(tmp_path):
    with pytest.raises(ValueError, match='empty'):
        rprof.write_table('stations', [], tmp_path / 'x.csv')


def _sections(steps=(0, 1), n=3, **over):
    rows = []
    for st in steps:
        for k in range(n):
            r = dict(profile_schema_version=ps.PROFILE_SCHEMA_VERSION,
                     case_id='c1', table='sections', step=st, shift=1.5 * st,
                     converged=True, element=k,
                     s_material_0=float(k), s_material_1=float(k + 1),
                     s_station_0=float(k) + 1.5 * st,
                     s_station_1=float(k + 1) + 1.5 * st,
                     x_0=-float(k), x_1=-float(k + 1),
                     strain=0.001 * (k + 1), moment=1.0e5 * (k + 1),
                     OD_section=0.4064, section_owner='pipe', region='',
                     in_band=True)
            r.update(over)
            rows.append(r)
    return rows


def test_write_refuses_a_position_column_that_moves_within_a_step(tmp_path):
    """Two positions merged into one, which no plot would show.

    `shift` is declared per=position. If one step carried two shifts, the
    geometry and the staircase would be drawn at different places on the
    same axis and the figure would look entirely plausible.
    """
    rows = _sections()
    rows[1]['shift'] = 99.0
    with pytest.raises(ValueError, match='per=position'):
        rprof.write_table('sections', rows, tmp_path / 'x.csv')


def test_a_valid_multi_step_table_is_accepted(tmp_path):
    p = tmp_path / 'c1.sections.csv'
    got = rprof.write_table('sections', _sections(), p)
    assert got['rows'] == 6
    back = list(csv.DictReader(p.open()))
    assert {r['step'] for r in back} == {'0', '1'}
    assert {r['shift'] for r in back} == {'0.0', '1.5'}

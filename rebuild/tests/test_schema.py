"""L8 -- the declared output contract, and the producers that must obey it.

WHAT THIS PINS. Every column a result file can carry is described, with a
unit; the open sets (stations, junctions) are declared as PATTERNS so a new
junction passes and a typo does not; every peak carries its location AND the
step it occurred at; and the names the schema generates are the names the
producer fills, asserted rather than inspected.

That last one is the whole reason the module exists. A contract that agrees
with its producer only by inspection is exactly the kind of convention this
project has been bitten by four times.
"""

import re

import pytest

pytest.importorskip('numpy')

from slay.report import passage as rp                         # noqa: E402
from slay.report import schema as sc                          # noqa: E402
from slay.scene.scene import build_scene                      # noqa: E402


@pytest.fixture(scope='module')
def scene():
    return build_scene(R=85.0, spacing=9.0, elastic_length=16.0)


# -- the contract itself ---------------------------------------------------

def test_every_field_declares_a_unit_and_a_meaning():
    """`-` means genuinely dimensionless. An empty unit means nobody
    decided, which is the state this module exists to end."""
    for f in sc.FIXED + sc.PATTERNS:
        assert f.unit, f.name
        assert f.about and len(f.about) > 10, f.name
        assert f.dtype in ('float', 'int', 'str', 'bool'), f.name


def test_no_column_is_declared_twice():
    names = [f.name for f in sc.FIXED]
    assert len(names) == len(set(names))


def test_strain_is_declared_dimensionless_and_moment_is_not():
    """The specific confusion this prevents: `envelope_strain = 0.0074` is a
    FRACTION, 0.74%, and a moment of 1309242 is N.m."""
    for f in sc.select(quantity='strain'):
        assert f.unit == sc.NONE, f.name
    for f in sc.select(quantity='moment'):
        assert f.unit == sc.NM, f.name


def test_the_version_is_a_real_version():
    assert re.fullmatch(r'\d+\.\d+\.\d+', sc.SCHEMA_VERSION)
    assert 'schema_version' in sc.header(), 'and it travels in every file'


# -- open sets are declared, not enumerated -------------------------------

def test_a_patterned_column_is_recognised():
    """Stations and junctions depend on the layout, so they cannot be listed
    in advance -- but the openness is declared."""
    for col in ('eps_SR2_env', 'j0_at_pipe_strain', 'j1_at_component_moment',
                'j0_m2OD_strain', 'j1_p6OD_moment_env', 'j0_p2OD_clamped'):
        assert sc.describe(col) is not None, col


def test_a_misspelt_column_is_refused():
    """The other half. An open column set is only checkable if the openness
    has a shape."""
    for col in ('eps_SR2_envelope', 'j0_at_pipe_strian', 'jX_m2OD_strain',
                'peak_strian', 'junk'):
        assert sc.describe(col) is None, col
    assert sc.unknown(['R', 'junk', 'eps_SR1_env']) == ['junk']


def test_a_patterned_column_carries_its_unit():
    assert sc.describe('j0_at_pipe_moment').unit == sc.NM
    assert sc.describe('j0_at_pipe_strain').unit == sc.NONE
    assert sc.describe('j0_m4OD_s').unit == sc.M


# -- every peak is queryable ----------------------------------------------

def test_every_peak_carries_its_location_and_its_step():
    """A value with no step cannot be checked, found again, or plotted --
    and the whole argument for sweeping is that the winning step is not one
    anybody would have picked in advance."""
    assert sc.peak_names(), 'there is at least one peak group'
    for prefix in sc.peak_names():
        g = sc.group(prefix)
        for key in ('s_material', 's_station', 'station', 'station_offset',
                    'step', 'shift'):
            assert sc.describe(g[key]) is not None, f'{prefix}:{key}'
        assert sc.describe(g['step']).dtype == 'int'
        assert sc.describe(g['s_station']).unit == sc.M


def test_strain_and_moment_peaks_are_both_present():
    """The question asked of the file is 'peak strain AND peak bending
    moment, with location and step'."""
    names = sc.peak_names()
    assert 'peak_strain' in names and 'peak_moment' in names
    assert 'body_peak_strain' in names and 'body_peak_moment' in names


def test_group_refuses_a_prefix_that_is_not_a_peak():
    with pytest.raises(KeyError):
        sc.group('R')


# -- the producer fills exactly what the contract declares ----------------

class FakeResult:
    def __init__(self, strains, moments, status='ok'):
        self.strains, self.moments, self.status = strains, moments, status
        self.active, self.released = (True,), ()

    @property
    def converged(self):
        return self.status == 'ok'


class FakePosition:
    def __init__(self, index, shift, result):
        self.index, self.shift, self.result = index, shift, result
        self.s_lead = self.s_trail = 0.0


def _passage(scene):
    """Two positions; the SECOND holds the worse strain, the FIRST the worse
    moment -- so a producer that reports the wrong step cannot pass."""
    a = FakePosition(0, 0.0, FakeResult(((0, 5.0, 0.002),),
                                        ((0, 5.0, 9.0e5),)))
    b = FakePosition(1, 3.0, FakeResult(((0, 6.0, 0.008),),
                                        ((0, 6.0, 1.0e5),)))
    return rp.measure([a, b], scene)


def test_the_producer_fills_exactly_the_declared_peak_columns(scene):
    """SCHEMA AND PRODUCER, ASSERTED TOGETHER. If `peak_group` grows a column
    and `peaks()` does not, this fails -- which is the failure mode a
    contract agreed by inspection always eventually has."""
    got = rp.peaks(_passage(scene), scene)
    want = set()
    for prefix in ('peak_strain', 'peak_moment'):
        want |= set(sc.group(prefix).values())
    assert set(got) == want


def test_the_peak_reports_the_step_it_actually_occurred_at(scene):
    """Strain peaks at position 1, moment at position 0. A producer that
    took both from the same position, or from the last, fails here."""
    got = rp.peaks(_passage(scene), scene)
    assert got['peak_strain'] == pytest.approx(0.008)
    assert got['peak_strain_step'] == 1
    assert got['peak_strain_shift'] == pytest.approx(3.0)
    assert got['peak_moment'] == pytest.approx(9.0e5)
    assert got['peak_moment_step'] == 0
    assert got['peak_moment_shift'] == pytest.approx(0.0)


def test_the_peak_location_names_a_roller(scene):
    """`s_station = 9.6` means nothing to a reader; 'SR2 +0.6 m' does."""
    got = rp.peaks(_passage(scene), scene)
    assert got['peak_strain_station'] == 'SR2'
    assert got['peak_strain_s_station'] == pytest.approx(9.0)
    assert got['peak_strain_station_offset'] == pytest.approx(0.0)


def test_moment_peaks_on_MAGNITUDE_not_on_sign(scene):
    """Sagging between rollers puts the moment through zero; a signed max
    would report the largest hogging and ignore a larger sagging one."""
    a = FakePosition(0, 0.0, FakeResult(((0, 5.0, 0.002),),
                                        ((0, 5.0, -2.0e6),)))
    got = rp.peaks(rp.measure([a], scene), scene)
    assert got['peak_moment'] == pytest.approx(2.0e6)


def test_a_passage_with_nothing_converged_still_fills_the_columns(scene):
    """A failed case is RECORDED, never dropped, so its row must be the same
    shape as every other."""
    a = FakePosition(0, 0.0, FakeResult((), (), status='diverged'))
    got = rp.peaks(rp.measure([a], scene), scene)
    assert set(got) == set(sc.group('peak_strain').values()) \
        | set(sc.group('peak_moment').values())
    assert got['peak_strain_step'] == -1, 'no step, said explicitly'


# -- writing ---------------------------------------------------------------

def test_writing_refuses_a_column_the_schema_does_not_know(tmp_path):
    rows = [{'case_id': 'X', 'R': 85.0, 'nonsense_column': 1.0}]
    with pytest.raises(ValueError, match='schema does not describe'):
        rp.write_case_csv(rows, tmp_path / 'out.csv')


def test_writing_emits_the_schema_beside_the_data(tmp_path):
    """So a reader never needs this source to interpret a file."""
    import json
    rows = [{'schema_version': sc.SCHEMA_VERSION, 'case_id': 'X', 'R': 85.0,
             'eps_SR2_env': 0.004, 'j0_at_pipe_strain': 0.003}]
    out = tmp_path / 'out.csv'
    rp.write_case_csv(rows, out)
    meta = json.loads((tmp_path / 'out.csv.schema.json').read_text())
    assert meta['schema_version'] == sc.SCHEMA_VERSION
    assert meta['n_rows'] == 1 and meta['unknown_columns'] == []
    units = {f['name']: f['unit'] for f in meta['fields']}
    assert units['R'] == sc.M and units['peak_moment'] == sc.NM
    assert any(p['pattern'] for p in meta['patterns'])


def test_declared_columns_come_first_and_in_declared_order(tmp_path):
    """Two files then sort their shared columns the same way, which is what
    makes them joinable."""
    rows = [{'eps_SR2_env': 0.004, 'R': 85.0, 'case_id': 'X',
             'schema_version': sc.SCHEMA_VERSION}]
    out = tmp_path / 'out.csv'
    rp.write_case_csv(rows, out)
    head = out.read_text().splitlines()[0].split(',')
    assert head[:3] == ['schema_version', 'case_id', 'R']
    assert head[-1] == 'eps_SR2_env', 'patterned columns after the fixed ones'


# -- 1.1.0: the five gaps found by plotting from the file alone -----------

def test_the_contact_lift_is_a_column():
    """FOR A SHROUD THE LIFT IS THE COMPONENT. GD-SH adds no bending
    stiffness, so without this a reader cannot tell its case from bare pipe
    and every other number still looks plausible."""
    f = sc.describe('contact_lift_max')
    assert f is not None and f.unit == sc.M
    for c in ('contact_lift_station', 'contact_lift_step'):
        assert sc.describe(c) is not None, c
    assert sc.describe('contact_lift_step').dtype == 'int'


def test_the_component_position_is_a_column():
    """`L_comp` gives a length, never a location."""
    for c in ('comp_s_lead', 'comp_s_trail'):
        assert sc.describe(c) is not None and sc.describe(c).unit == sc.M


def test_station_positions_are_declared():
    """Without them a consumer has `eps_SR2_env` and no way to place SR2."""
    for c in ('s_SR1', 's_SR7', 's_VR3'):
        f = sc.describe(c)
        assert f is not None and f.unit == sc.M, c
    assert sc.describe('s_notastation!') is None


def test_probes_declare_which_body_they_landed_in():
    """A profile drawn from the file must not join points across a section
    step, and without this a consumer cannot see where the step is."""
    for c in ('j0_at_pipe_side', 'j1_m2OD_side', 'j0_p6OD_owner'):
        assert sc.describe(c) is not None, c


def test_the_junction_snapshot_declares_its_step():
    """The bare `j*` columns are one position; the `_env` ones are all of
    them. Which position was left to inference before."""
    for c in ('junction_snapshot_step', 'junction_snapshot_shift'):
        assert sc.describe(c) is not None, c


def test_the_version_moved_with_the_columns():
    """Adding columns without moving the version is how a consumer ends up
    unable to tell two incompatible files apart."""
    assert sc.SCHEMA_VERSION != '1.0.0'

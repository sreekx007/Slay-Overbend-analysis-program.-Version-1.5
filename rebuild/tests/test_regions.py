"""The five strain regions of an offset (shroud) body.

THE ONE THING THAT MUST NOT BE WRONG is which end is the catenary side.
Reverse it and the scheme still produces five tidy regions, still partitions
the pipe, still tabulates -- and reports the quietest region as the one that
governs design. No test of shape or completeness would catch that, so there
is a test here that pins the orientation against a MEASURED result.

Nothing in this file solves a passage. The geometry comes off the assembly
and the peak location comes off the committed dataset row, so the whole file
runs in well under a second.
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import pytest

from slay.report import regions as rg
from slay.report import schema as cs

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'
DATASET = REPO / 'docs' / 'dataset' / 'dataset_components.csv'


def _ils(arch_id):
    import ils_builder
    spec = copy.deepcopy({a['id']: a for a in json.loads(
        FIXTURE.read_text())['archetypes']}[arch_id]['definition'])
    return ils_builder.build_ils(spec)


@pytest.fixture(scope='module')
def sh():
    """ILS-SH and the s_centre a passage would place it at. No solve."""
    from slay.study import sweep
    ils = _ils('ILS-SH')
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_centre = sweep.start_centre(sc, L)
    return ils, s_centre, rg.offset_geometry(ils, s_centre)


# ---------------------------------------------------------------------------
# the geometry is MEASURED, and it measures right
# ---------------------------------------------------------------------------

def test_the_deep_section_and_tapers_are_recovered(sh):
    """Against the archetype's own L1, L2 and V -- which this code never reads.

    The definition says L1 = 4.064, L2 = 1.016, V = 0.4064. `offset_geometry`
    asks the assembly where the contact surface is deep instead, so agreement
    is a check rather than a tautology. The tolerance is the sampling pitch,
    6.096 m / 4000.
    """
    _ils_, _s_c, g = sh
    pitch = 6.096 / rg.N_SAMPLES
    assert g is not None
    assert g.L1 == pytest.approx(4.064, abs=2 * pitch)
    assert g.L2_cat == pytest.approx(1.016, abs=2 * pitch)
    assert g.L2_ves == pytest.approx(1.016, abs=2 * pitch)
    assert g.symmetric
    assert g.V == pytest.approx(0.4064, abs=1e-9)
    # The lift is V - OD/2, NOT V. Using V over-elevates by half a diameter.
    assert g.lift_max == pytest.approx(0.4064 - 0.4064 / 2.0, abs=1e-9)
    assert g.L_total == pytest.approx(6.096, abs=4 * pitch)
    assert g.owner == 'GD-SH'


def test_a_section_changing_body_has_no_regions():
    """GD-TP is reported at its junctions; giving it regions too would put
    the same strain in two schemes and invite them to disagree."""
    from slay.study import sweep
    ils = _ils('ILS-TP')
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    assert rg.offset_geometry(ils, sweep.start_centre(sc, L)) is None


def test_plain_pipe_has_no_regions():
    assert rg.offset_geometry(None, 10.0) is None


# ---------------------------------------------------------------------------
# the orientation -- the test this module exists to keep honest
# ---------------------------------------------------------------------------

def test_the_catenary_side_is_high_s(sh):
    """`s` increases toward the stinger, and the catenary hangs off its tip."""
    _ils_, _s_c, g = sh
    assert g.s_cat_end > g.s_deep_cat > g.s_deep_ves > g.s_ves_end


def test_regions_run_catenary_to_vessel(sh):
    _ils_, _s_c, g = sh
    b = rg.bounds(g)
    assert [n for n, _lo, _hi in b] == list(rg.REGIONS)
    # Each region sits entirely vessel-ward of the one before it.
    for (_n0, lo0, _h0), (_n1, _l1, hi1) in zip(b, b[1:]):
        assert hi1 <= lo0


def test_the_peak_lands_in_X2(sh):
    """THE ORIENTATION CHECK, against a measured result.

    The reference says X2 -- the catenary-side third of the deep section --
    is the peak location in every case it ran. Our own ILS-SH envelope peak
    is recorded in the committed dataset at s_material 6.833. If the
    catenary/vessel mapping were reversed that point would classify as X4,
    the quietest region, and every other test here would still pass.
    """
    _ils_, _s_c, g = sh
    rows = {r['family']: r for r in csv.DictReader(DATASET.open())}
    row = rows.get('ILS-SH')
    assert row, 'ILS-SH is not in the committed dataset'
    s_peak = float(row['peak_strain_s_material'])
    assert rg.classify(s_peak, g) == 'X2', (
        f'peak at s_material {s_peak} classified as '
        f'{rg.classify(s_peak, g)}, not X2 -- the catenary/vessel mapping '
        f'is reversed')


# ---------------------------------------------------------------------------
# the scheme is a partition
# ---------------------------------------------------------------------------

def test_every_point_is_in_exactly_one_region(sh):
    _ils_, _s_c, g = sh
    lo, hi = g.s_ves_end - 30.0, g.s_cat_end + 30.0
    for k in range(2000):
        s = lo + (hi - lo) * k / 1999.0
        hits = [n for n, a, b in rg.bounds(g) if a <= s < b]
        assert len(hits) == 1, (s, hits)
        assert rg.classify(s, g) == hits[0]


def test_the_deep_thirds_are_equal_and_adjacent(sh):
    _ils_, _s_c, g = sh
    spans = {n: hi - lo for n, lo, hi in rg.bounds(g)
             if n in ('X2', 'X3', 'X4')}
    assert set(spans) == {'X2', 'X3', 'X4'}
    for v in spans.values():
        assert v == pytest.approx(g.L1 / 3.0, rel=1e-12)
    assert sum(spans.values()) == pytest.approx(g.L1, rel=1e-12)


def test_classify_is_empty_without_a_body():
    assert rg.classify(5.0, None) == ''
    assert rg.region_of_element(4.0, 5.0, None) == ''
    assert rg.bounds(None) == []


def test_an_element_is_assigned_whole_by_its_midpoint(sh):
    """Strain is piecewise constant per element; splitting one across a
    boundary would invent two values where the model has one."""
    _ils_, _s_c, g = sh
    edge = g.s_deep_cat
    assert rg.region_of_element(edge - 0.4, edge + 0.3, g) == 'X2'
    assert rg.region_of_element(edge - 0.3, edge + 0.4, g) == 'X1'


# ---------------------------------------------------------------------------
# the columns it writes are ones the case schema declares
# ---------------------------------------------------------------------------

def test_case_columns_are_all_declared(sh):
    """Every column regions.py emits must be describable by the contract --
    the same rule the dataset writer enforces."""
    _ils_, _s_c, g = sh
    peaks = {n: dict(peak_strain=0.1, peak_moment=2.0, s_material=1.0,
                     s_station=2.0, step=3, shift=0.5, n_elements=4,
                     s_lo=lo, s_hi=hi, frac_of_x2=0.8, peak_on_shroud=True)
             for n, lo, hi in rg.bounds(g)}
    cols = rg.case_columns(g, peaks)
    assert cs.unknown(cols.keys()) == []
    assert cols['region_scheme'] == 'X1-X5/offset'
    assert cols['offset_V'] == pytest.approx(0.4064)
    for n in rg.REGIONS:
        assert f'{n.lower()}_peak_strain' in cols
        assert f'{n.lower()}_frac_of_x2' in cols


def test_case_columns_are_empty_without_a_body():
    """Blank, not zero. A zero would pool into an average as if measured."""
    assert rg.case_columns(None, {}) == {}


def test_unbounded_edges_are_written_blank(sh):
    _ils_, _s_c, g = sh
    peaks = {n: dict(peak_strain=0.0, peak_moment=0.0, s_material=0.0,
                     s_station=0.0, step=-1, shift=0.0, n_elements=0,
                     s_lo=lo, s_hi=hi, frac_of_x2=0.0, peak_on_shroud=False)
             for n, lo, hi in rg.bounds(g)}
    cols = rg.case_columns(g, peaks)
    assert cols['x1_s_hi'] == ''      # X1 runs out toward the stinger tip
    assert cols['x5_s_lo'] == ''      # X5 runs back toward the vessel
    assert isinstance(cols['x2_s_lo'], float)

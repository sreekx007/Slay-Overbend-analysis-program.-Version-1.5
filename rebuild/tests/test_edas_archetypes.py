"""L2 fixtures from EDAS -- the ILS layouts, built and checked.

`knowledge/edas/standard_ils_layouts.json` in Slay-ILS-Designer-V1.0 carries
seven ILS archetypes, each holding a complete `ils_builder` definition AND
the geometry it is expected to produce. That makes them self-verifying: build
the definition, compare against the recorded figures.

WHAT THESE TESTS ARE FOR. L2 is mirrored code -- `component_spec.py` and
`ils_builder.py` are snapshots of another repository and are never edited
here (G7). The risk with a mirror is not that it breaks, it is that it is
re-synced upstream and something moves without anyone noticing. These
fixtures are the tripwire: seven assemblies whose mass, span and extent are
recorded independently of the code that computes them.

WHAT THEY ARE NOT. These check GEOMETRY, not physics. Peak strain needs a
solver and belongs to the M1..M5 ladder. The two are complementary and must
not be conflated -- see docs/SLAY_BUILD_INSTRUCTION.md section 7.

The fixture is vendored into `rebuild/fixtures/` rather than read from a
sibling clone, so the suite runs in a fresh checkout. It is mirrored data:
re-copy it when the source moves, never hand-edit it.
"""

import json
from pathlib import Path

import pytest

import ils_builder

FIXTURE = Path(__file__).parents[1] / 'fixtures' / 'standard_ils_layouts.json'

TOL_MASS_KG = 0.05
TOL_LEN_M = 1e-3


def _layouts():
    return json.loads(FIXTURE.read_text())


def _archetypes():
    return {a['id']: a for a in _layouts()['archetypes']}


ARCHETYPE_IDS = sorted(_archetypes())


def test_fixture_present_and_versioned():
    d = _layouts()
    assert d['schema_version'] == 2
    assert len(d['archetypes']) == 7
    assert len(d['anchors']) == 39


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_archetype_builds(arch_id):
    """Every archetype is accepted by the mirrored builder."""
    ils = ils_builder.build_ils(_archetypes()[arch_id]['definition'])
    assert ils.codes, f'{arch_id} built with no components'


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_archetype_matches_recorded_geometry(arch_id):
    """Mass, span and extent reproduce the figures recorded with the layout.

    Mass is the sensitive one: it includes header pipe steel, so it moves if
    the header length changes. Each archetype pins its own header for exactly
    that reason -- when the builder default went from a 12 m to a 14 m joint,
    every recorded mass would otherwise have shifted by +399.2 kg while span
    and CoG stayed put.
    """
    a = _archetypes()[arch_id]
    ils = ils_builder.build_ils(a['definition'])
    exp = a['expected']
    lo, hi = ils.extent

    assert ils.mass == pytest.approx(exp['mass_kg'], abs=TOL_MASS_KG)
    assert (hi - lo) == pytest.approx(exp['span_m'], abs=TOL_LEN_M)
    assert lo == pytest.approx(exp['extent_lo_m'], abs=TOL_LEN_M)
    assert hi == pytest.approx(exp['extent_hi_m'], abs=TOL_LEN_M)


@pytest.mark.parametrize('arch_id', ARCHETYPE_IDS)
def test_archetype_validates(arch_id):
    """The builder's own cross-component validation passes on every archetype."""
    ils = ils_builder.build_ils(_archetypes()[arch_id]['definition'])
    ils.validate()


def test_archetypes_cover_the_component_range():
    """The seven archetypes span the cases the milestone ladder needs."""
    ids = set(ARCHETYPE_IDS)
    assert {'ILS-TP', 'ILS-TT'} <= ids, 'thick body and tapered transition'
    assert 'ILS-SH' in ids, 'shroud -- the offset contact surface case'
    assert 'ILS-SHTP' in ids, 'shroud over a thick body -- the max-vs-sum case (G3)'
    assert {'ILS-EAST', 'ILS-EASB'} <= ids, 'externally attached structures'
    assert 'ILS-ILT' in ids, 'branched inline tee'


# --------------------------------------------------------------------------
# Anchors -- published validation cases
# --------------------------------------------------------------------------

def test_anchors_reference_real_archetypes():
    d = _layouts()
    known = set(_archetypes())
    for x in d['anchors']:
        assert x['archetype'] in known, f"{x['id']} names unknown {x['archetype']}"


def _target_index(components: list, ref) -> int:
    """Resolve an anchor's `component` reference to a list index.

    The field is an integer index on 34 anchors and a component ID string
    ('TP') on five. The string form is not decoration: it appears exactly
    where an index would be ambiguous. ILS-SHTP holds ['SH', 'TP'], so
    reading 'TP' as index 0 would apply a wall-thickness override to the
    SHROUD instead of the thick body -- a different model that still builds
    and still returns a number.
    """
    if isinstance(ref, int):
        return ref
    matches = [i for i, c in enumerate(components) if c.get('id') == ref]
    if len(matches) != 1:
        raise AssertionError(
            f'component reference {ref!r} matched {len(matches)} components '
            f'{[c.get("id") for c in components]} -- must be exactly one')
    return matches[0]


def test_component_reference_resolves_to_the_intended_component():
    """The ambiguous case, pinned: on ILS-SHTP, 'TP' is index 1, not 0."""
    comps = _archetypes()['ILS-SHTP']['definition']['components']
    assert [c['id'] for c in comps] == ['SH', 'TP']
    assert _target_index(comps, 'TP') == 1
    assert _target_index(comps, 0) == 0


def test_anchors_build_with_their_overrides():
    """An anchor is an archetype plus parameter overrides. Every one must
    still build -- an override that violates a component rule would be a
    defect in the recorded case, not in the builder."""
    d = _layouts()
    arch = _archetypes()
    built = 0
    for x in d['anchors']:
        defn = json.loads(json.dumps(arch[x['archetype']]['definition']))
        if x['overrides']:
            i = _target_index(defn['components'], x['component'])
            defn['components'][i].update(x['overrides'])
        ils_builder.build_ils(defn)
        built += 1
    assert built == 39


def test_published_results_are_well_formed():
    """24 of the 39 anchors carry published numbers; the rest are defined
    configurations awaiting them. Check the ones that do are usable."""
    d = _layouts()
    pairs = [(x['id'], p) for x in d['anchors'] for p in x.get('published', [])]
    assert len(pairs) == 24

    for anchor_id, p in pairs:
        assert p['lay']['R_m'] in (70, 85, 100), anchor_id
        assert p['lay']['tension_MT'] in (100, 120), anchor_id
        assert p['results'], anchor_id

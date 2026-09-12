"""Config is ours now -- these tests police the boundary that remains.

DECISION, 12 Sep 2026. `slay_config.yaml` and `config.py` moved OUT of the
mirror and are owned by this repository. The reason is that the mirrored
ILS-tier code reads only five constants from config -- `component_spec.py`
takes OD_PIPE_DEF, T_WALL_DEF, STEEL_E and G; `ils_builder.py` takes
RHO_STEEL -- and none of the stinger, roller, solver, material, mesh or
section blocks. Those are SLAY-tier parameters that happened to live in a
shared file, and asking the other repo's permission to change a value it
never reads was friction without benefit.

`component_spec.py` and `ils_builder.py` remain mirrored. They are actively
developed upstream and are genuinely that repo's work.

What this leaves is a smaller, sharper obligation: five values that must
stay in step. `fixtures/upstream_shared_constants.json` records them with
the commit they were taken from, and the first test below is the guard.

LIMIT OF THE GUARD, stated plainly. It catches US changing a shared
constant. It cannot detect UPSTREAM changing one, because nothing local
sees upstream. That is a re-sync-time check: when re-copying
component_spec.py or ils_builder.py, refresh the fixture too, and this test
reports whether a shared value moved underneath us.
"""

import json
from pathlib import Path

import pytest

import config

FIXTURE = Path(__file__).parents[1] / 'fixtures' / 'upstream_shared_constants.json'


def _shared():
    return json.loads(FIXTURE.read_text())


def test_shared_constants_still_agree_with_upstream():
    """The five values the mirrored ILS-tier code reads.

    A mismatch means either we edited a value the other repo depends on, or
    a re-sync brought a changed one down. Either way it needs a decision,
    not a silent pass.
    """
    recorded = _shared()['constants']
    live = {
        'OD_PIPE_DEF': config.OD_PIPE_DEF,
        'T_WALL_DEF': config.T_WALL_DEF,
        'STEEL_E': config.STEEL_E,
        'G': config.G,
        'RHO_STEEL': config.RHO_STEEL,
    }
    assert live == recorded, (
        'a constant shared with Slay-ILS-Designer-V1.0 has moved. These five '
        'are read by the mirrored component_spec.py / ils_builder.py, so a '
        'change here changes their behaviour too.')


def test_fixture_records_its_provenance():
    d = _shared()
    assert d['source_commit']
    assert d['source_repo'] == 'sreekx007/Slay-ILS-Designer-V1.0'


def test_mirrored_code_reads_nothing_else_from_config():
    """The premise of the ownership split, asserted rather than assumed.

    If a future re-sync brings down a `component_spec.py` that reads, say,
    N_VR, the split stops being safe and this test says so. The check is
    textual because importing is not enough -- a constant read inside a
    rarely-taken branch would not show up at import time.
    """
    import re
    allowed = {'OD_PIPE_DEF', 'T_WALL_DEF', 'STEEL_E', 'G', 'RHO_STEEL'}
    root = Path(__file__).parents[1]

    for name in ('component_spec.py', 'ils_builder.py'):
        src = (root / name).read_text()
        used = set(re.findall(r'config\.([A-Z_][A-Z_0-9]*)', src))
        extra = used - allowed
        assert not extra, (
            f'{name} now reads {sorted(extra)} from config. Those blocks are '
            f'owned by this repo and changed independently -- the ownership '
            f'split in test docstring above assumes the mirrored code touches '
            f'only {sorted(allowed)}.')


# --------------------------------------------------------------------------
# The roller layout ruling
# --------------------------------------------------------------------------

def test_vessel_roller_count():
    """n_vr counts ALL vessel stations, the fixed one included.

    Five stations: VR1..VR4 contacting, VR5 with all DOF fixed. Under the
    old meaning -- contact rollers only, with a separate VR0 outside the
    count -- the same physical layout reads 4. Mixing the two is a silent
    off-by-one in the number of supports.
    """
    assert config.N_VR == 5


def test_stinger_roller_count():
    """n_sr counts SR1 (the tangency station) but EXCLUDES the tip station.

    So n_sr=6 means SR1..SR6 plus a further SR7 that this count does not
    include. SR7 is a contact slot and is where lay tension is applied,
    using its own tangent -- taking that tangent from SR6 instead reported
    2.46% strain there against a ~0.83% reference.
    """
    assert config.N_SR == 6


def test_terminal_station_counting_is_asymmetric_and_that_is_deliberate():
    """The one rule most likely to be mis-generalised, pinned.

        n_vr INCLUDES its terminal station (fixed VR5)
        n_sr EXCLUDES its terminal station (tip SR7)

    So the defaults describe 5 vessel stations and 7 stinger stations.
    Neither count means "stations" and neither means "contact slots" —
    reading one from the other is an off-by-one in the model's supports.
    """
    n_vessel_stations = config.N_VR
    n_stinger_stations = config.N_SR + 1
    assert (n_vessel_stations, n_stinger_stations) == (5, 7)

    vessel_contact = config.N_VR - 1        # VR5 is fixed, not contacting
    stinger_contact = config.N_SR + 1       # the tip IS a contact slot
    assert (vessel_contact, stinger_contact) == (4, 7)


def test_elastic_end_zone():
    """Both model ends are forced fully elastic to keep boundary-restraint
    artefacts out of the reported strain.

    NEW behaviour -- the old implementation has no end-zone treatment and no
    per-element material assignment at all. Recorded here so the value has a
    single home before the physics layer exists to consume it.
    """
    assert config.ELASTIC_END_ZONE_M == 16.0


def test_one_sided_set_matches_the_ruling():
    """VR1-VR2 unidirectional (uplift allowed), VR3 onward bidirectional,
    every stinger roller unidirectional."""
    s = config.ONE_SIDED_ROLLERS_DEFAULT
    assert {f'SR{i}' for i in range(1, config.N_SR + 1)} <= s
    assert {'VR1', 'VR2'} <= s
    assert not ({'VR3', 'VR4'} & s), 'VR3 onward is bidirectional'


def test_fixed_station_is_not_one_sided():
    """VR5 is fixed, not a contact roller, so it is outside the one-sided
    classification entirely -- it is neither one-sided nor bidirectional.

    Note the one-sided set alone cannot distinguish 'bidirectional contact'
    from 'fixed, no contact': both are simply absent. The scene layer is
    what flags VR{n_vr} as fixed.
    """
    assert f'VR{config.N_VR}' not in config.ONE_SIDED_ROLLERS_DEFAULT


def test_one_sided_rule_scales_with_n_sr():
    """Stored as a rule, not a list, so it cannot go stale."""
    from config import _resolve_one_sided_rollers
    rule = {'stinger': 'all', 'vessel': ['VR1', 'VR2']}
    for n in (4, 6, 9):
        s = _resolve_one_sided_rollers(rule, n)
        assert {f'SR{i}' for i in range(1, n + 1)} <= s
        assert f'SR{n + 1}' not in s


def test_physical_layout_of_the_one_sided_pair():
    """THE REGRESSION LOCK on the renumbering.

    The ruling renamed the vessel rollers but must not have moved any. Under
    the new numbering VR1 and VR2 -- the one-sided pair -- sit one and two
    spacings inboard of SR1. The old code's releasable pair sat at those same
    two positions under different names.
    """
    spacing = config.ROLLER_SPACING
    x_of = lambda j: j * spacing
    one_sided_x = sorted(x_of(int(n[2:])) for n in config.ONE_SIDED_ROLLERS_DEFAULT
                         if n.startswith('VR'))
    assert one_sided_x == [spacing, 2 * spacing] == [8.0, 16.0]

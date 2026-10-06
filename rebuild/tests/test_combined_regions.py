"""A shroud with a thick body inside it reports in BOTH schemes.

WHAT WAS WRONG. `offset_geometry` returned None as soon as ANY section
stepped, which is right for a thick pipe on its own -- it has no offset to
divide into thirds and belongs to junction reporting -- but it also took
`ILS-SHTP` out of region reporting entirely. That is Paper 1's TABLE XXXIX
and TABLE XLI, and the paper reports those cases in both schemes at once:
Case 2's peak is at "pipe-to-component junction at X2". With no X2 the case
could not be compared at all, and the ledger carried it as "blocked on
reporting, not physics" for weeks.

WHAT DECIDES IS THE DEEPEST CONTACT, not whether a section steps somewhere.
A thick body makes the lift positive by itself -- its OD is larger, so its
bottom surface IS lower -- which is a consequence of its wall and not a
deliberate elevation. On the combined assembly the shroud is deeper by
construction (V = 1 D against the thick body's 0.58 D), so the deepest
contact is the shroud's and the regions are the shroud's.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip('numpy')

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from slay.report import regions as rg                       # noqa: E402
from slay.study import sweep                                # noqa: E402

gen = pytest.importorskip('plot_stinger')
D = 0.4064


def _geom(aid, **kw):
    ils = gen.build_component_ils(aid, **kw)
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    return ils, rg.offset_geometry(ils, sweep.start_centre(sc, L),
                                   ils.assembly.pipe.OD_pipe)


# ---------------------------------------------------------------------------
# which assemblies get regions, and which must not
# ---------------------------------------------------------------------------

def test_a_thick_pipe_alone_still_gets_no_regions():
    """The rule that must survive the fix. A body that only steps the
    section has no offset to divide, and giving it thirds would put the same
    strain in two schemes and invite them to disagree."""
    _ils, g = _geom('ILS-TP')
    assert g is None


def test_a_shroud_gets_regions():
    _ils, g = _geom('ILS-SH')
    assert g is not None and g.owner == 'GD-SH'


def test_a_shroud_with_a_thick_body_gets_the_SHROUD_s_regions():
    """THE FIX. Both bodies are present; the regions belong to the deeper."""
    _ils, g = _geom('ILS-SHTP')
    assert g is not None
    assert g.owner == 'GD-SH', (
        'the thick body is not what divides the pipe into thirds')


def test_the_combined_regions_match_the_shroud_alone():
    """Adding a thick body inside the shroud must not move the region
    boundaries -- they are the shroud's geometry, and it did not change.
    If they moved, X2 would mean different steel in the two cases and
    TABLE XXXIX's comparison against its own shroud-only baseline would be
    between different measurements."""
    _a, sh = _geom('ILS-SH')
    _b, both = _geom('ILS-SHTP')
    for f in ('s_cat_end', 's_deep_cat', 's_deep_ves', 's_ves_end', 'V'):
        assert getattr(both, f) == pytest.approx(getattr(sh, f)), f


@pytest.mark.parametrize('L_OD', [5.0, 10.0])
def test_the_thick_body_is_the_one_re_dimensioned(L_OD):
    """`--L-OD` must reach the thick body, not the shroud.

    Paper 1's TABLE XXXIX varies the thick pipe's length at a FIXED shroud.
    Writing L_comp onto components[0] raised `OffsetShroud.__init__() got an
    unexpected keyword argument 'L_comp'` -- loud, but on a component that
    happened to accept the key it would have re-dimensioned the wrong body
    in silence.
    """
    ils = gen.build_component_ils('ILS-SHTP', L_OD=L_OD)
    by = {getattr(c, 'code', ''): c for c in ils.assembly.components}
    assert by['GD-TP'].L_comp == pytest.approx(L_OD * D)
    assert by['GD-SH'].L1 == pytest.approx(10.0 * D), 'the shroud is fixed'


def test_a_dimension_no_component_carries_is_refused():
    """Rather than silently doing nothing, which is how the wrong body gets
    re-dimensioned without anyone noticing."""
    with pytest.raises(ValueError, match='L_comp'):
        gen.build_component_ils('ILS-SH', L_OD=5.0)


def test_a_thick_body_FILLING_the_deep_section_still_gets_regions():
    """THE TIE CASE, and the one that broke the first fix.

    At 10 D the thick body is exactly as long as the shroud's deep section,
    so every sample at full lift ALSO sits on a stepped section. A rule
    phrased as "does any section step at the deepest sample" answered yes
    here and no at 5 D -- the same assembly, the same shroud, a different
    answer depending on which tied sample won. The rule compares two OWNERS
    instead: the body holding the pipe up (GD-SH) is not the body stepping
    its section (GD-TP), so the regions are the shroud's either way.
    """
    for L_OD in (5.0, 10.0):
        _ils, g = _geom('ILS-SHTP', L_OD=L_OD)
        assert g is not None, f'{L_OD} D lost its regions'
        assert g.owner == 'GD-SH'


def test_the_rule_is_owner_vs_owner_not_a_step_flag():
    """Stated on the source, because the distinction is invisible in the
    result until an assembly happens to tie -- and then it is a silently
    missing comparison rather than a failure."""
    import inspect
    src = inspect.getsource(rg.offset_geometry)
    assert 'owner == steps[k_deep]' in src, (
        'the deepest contact owner must be compared against the SECTION '
        'owner there, not against a boolean "something stepped"')

"""The centreline lift each component applies, checked against the ORIGINAL.

WHY THIS IS WORTH A TEST OF ITS OWN. For GD-SH the lift IS the component:
a shroud adds no bending stiffness (`stiffness_ratio` 1.0, no section step),
so if the lift were dropped the case would be indistinguishable from bare
pipe and every number would still look plausible. Nothing else in the suite
would notice.

The check is against `slay_overbend_v1_50.shroud_offset_at` directly -- the
original implementation, not a restatement of it here -- so this is a
cross-program comparison rather than the rebuild agreeing with itself.

THE CONVENTION, which the original's docstring records as a Session 23
correction: `V` is measured from the PIPE CENTRELINE, not from the pipe OD,
so the elevation actually applied is

    CL_lift = V - OD_pipe/2

and not `V`. Applying the full `V` over-elevated the pipe by OD/2 everywhere
under the deep section -- 33% over-lift at V = 2D -- and inflated strains to
match.
"""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip('numpy')

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import ils_builder                                            # noqa: E402

from slay.model.assemble import build_model                   # noqa: E402
from slay.physics.contact import contact_targets              # noqa: E402
from slay.study import sweep                                  # noqa: E402

OD = 0.4064
FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'


def _arch(aid):
    d = json.loads(FIXTURE.read_text())
    return {a['id']: a for a in d['archetypes']}[aid]['definition']


def _ils(aid):
    return ils_builder.build_ils(_arch(aid))


def lift_at(ils, x):
    """Centreline lift above the plain-pipe baseline, as physics reads it."""
    return ils.assembly.contact_at(x).y - OD / 2.0


# -- GD-SH, against the original implementation ---------------------------

def test_the_shroud_lift_matches_the_original_across_its_whole_profile():
    """Plateau, both tapers and the clear pipe either side -- not just the
    centre, where a constant would also pass."""
    ref = pytest.importorskip('slay_overbend_v1_50')
    spec = _arch('ILS-SH')['components'][0]
    V, L1, L2 = spec['V'], spec['L1'], spec['L2']
    ils = _ils('ILS-SH')
    worst = 0.0
    for i in range(-40, 41):
        x = i * 0.1
        ours = lift_at(ils, x)
        theirs = ref.shroud_offset_at(x, 0.0, L1, L2, V, OD, taper='linear')
        worst = max(worst, abs(ours - theirs))
    assert worst < 1e-9, f'worst difference {worst:.3e} m'


def test_the_shroud_lift_is_V_minus_half_the_pipe_OD():
    """The Session 23 convention, stated as a number. Applying the full `V`
    would over-elevate by OD/2 everywhere under the deep section."""
    spec = _arch('ILS-SH')['components'][0]
    ils = _ils('ILS-SH')
    assert lift_at(ils, 0.0) == pytest.approx(spec['V'] - OD / 2.0)
    assert lift_at(ils, 0.0) == pytest.approx(0.2032, abs=1e-6)


def test_the_shroud_taper_reaches_zero_at_its_outer_end():
    """The taper terminates flush with the pipe OD -- it must not end on a
    finite step, or the shroud would have a face the roller could catch."""
    spec = _arch('ILS-SH')['components'][0]
    ils = _ils('ILS-SH')
    outer = spec['L1'] / 2.0 + spec['L2']
    assert lift_at(ils, outer) == pytest.approx(0.0, abs=1e-9)
    assert lift_at(ils, outer + 0.5) == pytest.approx(0.0, abs=1e-9)
    mid = spec['L1'] / 2.0 + spec['L2'] / 2.0
    assert lift_at(ils, mid) == pytest.approx(
        (spec['V'] - OD / 2.0) / 2.0, rel=1e-6), 'linear, so half way is half'


# -- GD-TT, the OD-driven question ----------------------------------------

def test_the_thick_taper_lift_is_driven_by_the_COMPONENT_OD():
    """On the body the lift must be (OD_comp - OD_pipe)/2, with the
    component OD following a CONSTANT BORE: OD_c = OD_p + 2(t_c - t_p).
    A lift derived from anything else -- the wall alone, say -- would be
    plausible and wrong."""
    spec = _arch('ILS-TT')['components'][0]
    t_c, t_p = spec['t_comp'], 0.021
    OD_c = OD + 2.0 * (t_c - t_p)
    ils = _ils('ILS-TT')
    want = (OD_c - OD) / 2.0
    assert want == pytest.approx(0.0440, abs=1e-6)
    for x in (-0.4, -0.2, 0.0, 0.2, 0.4):
        assert lift_at(ils, x) == pytest.approx(want, abs=1e-9), x


def test_the_thick_taper_lift_ramps_to_zero_and_not_beyond():
    ils = _ils('ILS-TT')
    lo, hi = ils.extent
    assert lift_at(ils, hi) == pytest.approx(0.0, abs=1e-9)
    assert lift_at(ils, hi + 0.5) == pytest.approx(0.0, abs=1e-9)
    assert lift_at(ils, lo) == pytest.approx(0.0, abs=1e-9)
    inner = [lift_at(ils, x) for x in (0.6, 0.8, 1.0, 1.2)]
    assert inner == sorted(inner, reverse=True), 'monotonic down the taper'


def test_the_plain_thick_body_does_not_taper():
    """GD-TP is a plain thick pipe: the lift steps, it does not ramp. That
    is what the original does too -- `envelope_at` appends a CONSTANT
    CL_thick over the component range and nothing outside it."""
    ils = _ils('ILS-TP')
    lo, hi = ils.extent
    inside = lift_at(ils, 0.5 * (lo + hi))
    assert inside == pytest.approx(0.0210, abs=1e-6)
    assert lift_at(ils, hi + 0.01) == pytest.approx(0.0, abs=1e-9)
    assert lift_at(ils, hi - 0.01) == pytest.approx(inside, abs=1e-9), \
        'constant right up to the edge'


# -- and it must reach the solver -----------------------------------------

@pytest.mark.parametrize('aid,want', [('ILS-SH', 0.2032), ('ILS-TT', 0.0440),
                                      ('ILS-TP', 0.0210)])
def test_the_lift_reaches_a_contact_target_during_the_passage(aid, want):
    """THE CHECK THAT MATTERS. A lift the geometry knows about but the
    solver never sees is not applied at all. Swept, because at the leading
    EDGE the lift is correctly zero -- a taper terminates flush -- so a
    single position proves nothing.
    """
    ils = _ils(aid)
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    centre = sweep.start_centre(sc, L)
    m = build_model(sc, ils, s_centre=centre,
                    extra_stations=sweep._required_stations(sc))
    total = sweep.sweep_length(L)
    sched = sweep.schedule(total, 2 * OD,
                           include=sweep.critical_shifts(sc, L, centre))
    seen = 0.0
    for shv in sched:
        for t in contact_targets(m, sc, assembly=ils.assembly, shift=shv,
                                 s_centre=centre):
            seen = max(seen, abs(t.lift))
    assert seen == pytest.approx(want, abs=1e-6), (
        f'{aid}: the deepest lift any station saw over the whole passage was '
        f'{seen:.5f} m, against a plateau of {want:.5f} m')


def test_the_lift_raises_the_pipe_rather_than_lowering_it():
    """Sign. `dn` is negative down onto the arc, so a lift must make it LESS
    negative -- the deeper surface holds the centreline higher."""
    ils = _ils('ILS-TP')
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    centre = sweep.start_centre(sc, L)
    m = build_model(sc, ils, s_centre=centre,
                    extra_stations=sweep._required_stations(sc))
    lifted = [t for t in contact_targets(m, sc, assembly=ils.assembly,
                                         shift=9.0 - centre, s_centre=centre)
              if abs(t.lift) > 1e-9]
    assert lifted, 'the sweep puts a station under the body'
    for t in lifted:
        assert t.lift > 0.0
        assert t.dn == pytest.approx(t.dn_arc + t.lift)
        assert t.dn > t.dn_arc, 'less negative: the pipe sits higher'

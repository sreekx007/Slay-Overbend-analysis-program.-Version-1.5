"""The reported pipe rides on the roller TOPS, not through the axles.

L099. `LayPath.R` is measured to the roller CENTRELINE, so `path.position`
is where the axles are. The profile writer compared the solved centreline
against that locus and called the difference `off_arc` -- so a pipe sitting
correctly on every roller reported about 0 mm off the arc, and the figures
drew it passing through the rollers.

THE ANALYSIS WAS NEVER WRONG. Contact targets deepen by exactly
R_eff / R = 1.00592, so the roller radius enters through the curvature as
`physics.contact` documents and intends. What was missing was the datum the
RESULT is reported against, which is why this is fixed in reporting and the
solve is untouched.

WHY THAT IS EXACT AND NOT AN APPROXIMATION. Every station carries the same
roller radius -- a deck roller holds the pipe up by exactly as much as a
stinger roller -- so lifting the whole reported pipe by `r_roller + OD/2` is
a RIGID TRANSLATION, and a rigid translation produces no strain. It stops
being one the moment the radii differ, so that is checked rather than
assumed.

AND ONLY A PICTURE COULD HAVE FOUND IT. No numeric test in this repo
compares an elevation against anything; every one of them is a strain, a
moment or a ratio, and all of those were right.
"""
from __future__ import annotations

import pytest

pytest.importorskip('numpy')

from slay.model.assemble import build_model                   # noqa: E402
from slay.physics import contact as ct                        # noqa: E402
from slay.report import profile as rprof                      # noqa: E402
from slay.report import profile_schema as ps                  # noqa: E402
from slay.scene.scene import build_scene                      # noqa: E402

OD = 0.4064
R_ROLLER = 0.30
OFFSET = R_ROLLER + OD / 2.0          # 0.5032 m


def test_the_offset_is_the_roller_radius_plus_the_pipe_radius():
    """Stated as the arithmetic it is, so a reader need not trust a name."""
    assert OFFSET == pytest.approx(0.5032)


def test_the_schema_declares_the_contact_offset():
    """Carried per sample because a plotter cannot ask the Scene for the
    roller radius, and without it `off_arc` reads half a metre everywhere
    and contact cannot be told from lift-off."""
    assert 'contact_offset' in ps.header('geometry')
    assert ps.PROFILE_SCHEMA_VERSION >= '1.4.0'


def test_the_arc_columns_are_documented_as_the_AXLE_locus():
    """The column did not change meaning -- the description did, because it
    was being read as 'where the pipe sits' and it never was."""
    arc = ps.describe('geometry', 'arc_x').about.lower()
    off = ps.describe('geometry', 'off_arc').about.lower()
    assert 'axle' in arc and 'not where the pipe sits' in arc
    assert 'contact locus' in off


def test_differing_roller_radii_are_refused_not_averaged():
    """With one radius the lift is a rigid translation. With two it is a
    bend, and applying a single value would silently deform the reported
    pipe -- which is the defect this test's own file is named for, in a new
    place."""
    sc = build_scene(R=85.0, spacing=9.0, radii={'SR3': 0.50})
    m = build_model(sc)
    with pytest.raises(ValueError, match='radii'):
        rprof.geometry_rows(sc, m, None, None, None, 0.0, OD, 0.0,
                            step=0, converged=True, context={})


def test_the_contact_targets_still_carry_the_radius_through_curvature():
    """The half of this that was already right, pinned so the reporting fix
    cannot be mistaken for the physics fix. If this ever reads 1.0, the
    roller radius has fallen out of the solve and the lift above would be
    papering over it."""
    probe = build_scene(R=85.0, spacing=9.0)
    sc = build_scene(R=85.0, spacing=9.0,
                     margin_stinger=ct.material_margin(probe))
    m = build_model(sc)
    cl = {t.station: t for t in
          ct.contact_targets(m, sc, contact_surface='centreline')}
    bo = {t.station: t for t in ct.contact_targets(m, sc)}
    for n in ('SR2', 'SR4', 'SR6'):
        assert bo[n].dn / cl[n].dn == pytest.approx(85.5032 / 85.0, rel=1e-9)
        assert bo[n].R_eff == pytest.approx(85.5032)

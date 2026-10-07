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

L099 GOT THE DIRECTION WRONG, and the tests below it did not notice for a
day. The lift was applied as `contact_offset * n`, along the LOCAL normal.
On the deck n = (0, -1) and that is the vertical, so every check that
looked at the deck passed. On the arc the normal swings round with theta
and the lift carries the pipe PAST the roller top by
`contact_offset * (1 - cos theta)` -- 0 at SR1, 142 mm at SR7 on a 70 m
stinger -- so `off_arc` reported the pipe lifting off every stinger roller
in turn, 17 mm at SR3 rising to 126 mm at SR7,
while the solver's own residual at those same slots was 0.00 mm.

THE RIGHT LIFT IS VERTICAL, and it is exact for the same reason the
magnitude is. `arc_target(R_eff, theta)` is the normal offset from a
straight reference at arc length `R_eff * theta`, so the solved shape is a
circle of radius R_eff TANGENT TO THE DECK, centre (0, R_eff). The
roller-top locus is a circle of the same radius concentric with the AXLE
arc, centre (0, R). Those differ by (0, R - R_eff) at every angle and by
nothing else. So the tests here are written at a station ON THE ARC, where
the two candidate lifts disagree, and not only on the deck, where they
cannot.
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


# ---------------------------------------------------------------------------
# the DIRECTION of the lift -- tested where the two candidates disagree
# ---------------------------------------------------------------------------

def _solved_circle(theta, R, offset):
    """Where the SOLVE puts the centreline: radius R+offset, tangent to the
    deck. This is `arc_target(R_eff, theta)` read as the geometry it is."""
    import math
    Reff = R + offset
    return (-Reff * math.sin(theta), Reff * (1.0 - math.cos(theta)))


def _roller_top(theta, R, offset):
    """Where the pipe PHYSICALLY sits: concentric with the axle arc."""
    import math
    Reff = R + offset
    return (-Reff * math.sin(theta), R - Reff * math.cos(theta))


@pytest.mark.parametrize('theta', [0.0, 0.129, 0.386, 0.771])
def test_the_two_circles_differ_by_a_VERTICAL_translation(theta):
    """The whole justification, as arithmetic rather than as prose.

    If this held only approximately, lifting the reported pipe would bend
    it, and the strain would no longer be the solve's.
    """
    R = 70.0
    sx, sy = _solved_circle(theta, R, OFFSET)
    tx, ty = _roller_top(theta, R, OFFSET)
    assert tx - sx == pytest.approx(0.0, abs=1e-12)
    assert ty - sy == pytest.approx(-OFFSET, abs=1e-12)


@pytest.mark.parametrize('theta', [0.129, 0.386, 0.771])
def test_a_lift_along_the_LOCAL_NORMAL_overshoots_the_roller_top(theta):
    """The defect, stated as the number it is.

    Along the normal the old lift carries the pipe PAST the roller top by
    `contact_offset * (1 - cos theta)` -- 142 mm at SR7 on a 70 m stinger --
    which is why `off_arc` read positive, as lift-off, and the figure drew
    the pipe hovering above every stinger roller.

    This is the test that was missing: every earlier check sat at theta = 0,
    where `contact_offset * n` and the vertical are the same vector.
    """
    import math
    R = 70.0
    sx, sy = _solved_circle(theta, R, OFFSET)
    tx, ty = _roller_top(theta, R, OFFSET)
    nx, ny = -math.sin(theta), -math.cos(theta)       # LayPath.normal
    lx, ly = sx + OFFSET * nx, sy + OFFSET * ny       # the OLD lift
    over = (lx - tx) * nx + (ly - ty) * ny
    assert over == pytest.approx(OFFSET * (1.0 - math.cos(theta)), abs=1e-9)
    assert over > 1e-3, 'the two lifts must differ off the deck'


def test_at_theta_zero_the_two_lifts_agree():
    """Which is exactly why the deck-only checks passed."""
    import math
    R = 70.0
    sx, sy = _solved_circle(0.0, R, OFFSET)
    nx, ny = -math.sin(0.0), -math.cos(0.0)
    assert (sx + OFFSET * nx, sy + OFFSET * ny) == pytest.approx(
        (sx, sy - OFFSET), abs=1e-12)


def test_the_writer_lifts_vertically_not_along_the_normal():
    """Read off the EMITTED ROWS, so the contract is checked, not the source.

    With a zero displacement field the solved centreline is the straight
    deck reference, and the reported centreline must be that reference
    lifted VERTICALLY by the contact offset -- y = -offset at every sample,
    including the samples whose station is far up the arc, where a lift
    along the local normal would instead give y = -offset * cos(theta) and
    x = -(s) - offset * sin(theta).
    """
    import numpy as np
    sc = build_scene(R=70.0, spacing=9.0,
                     margin_stinger=ct.material_margin(build_scene(
                         R=70.0, spacing=9.0)))
    m = build_model(sc)
    ms, _mdl, _ix = _mesh(m, sc)
    U = np.zeros(3 * (max(n.index for n in m.nodes) + 1))
    rows = rprof.geometry_rows(sc, m, ms, U, None, 0.0, OD, 0.0, 0, True,
                               {}, n=60)
    assert rows, 'no samples emitted'
    for r in rows:
        assert r['y'] == pytest.approx(-OFFSET, abs=1e-9)
        assert r['x'] == pytest.approx(-r['s_material'], abs=1e-9)
    # and the samples really do reach up the arc, or the test proves nothing
    assert max(abs(float(r['normal_x'])) for r in rows) > 0.5


def _mesh(model, scene):
    """The kernel mesh for a model, so `dof` numbering matches the writer."""
    from slay.physics.problem import build_problem
    from slay.solve.kernel import mesh_of_problem
    from slay.data.materials import material
    pr = build_problem(model, scene, shift=0.0, tension=0.0,
                       material=material('j2'))
    return mesh_of_problem(pr)

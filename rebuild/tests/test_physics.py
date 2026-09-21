"""T4 -- the physics layer: sections, contact targets, loads, and `Problem`.

WHAT T4 IS FOR. T3 emitted geometry and DECLARATIONS. This layer resolves
every declaration into numbers and poses one lay position as a `Problem`
that is complete and inert. The value of the artifact is mostly in what it
REFUSES to carry: no shift index, no sweep length, no live Scene.

THE CARD'S DONE WHEN CLAUSE is `differs_only_in_contact`. Two Problems built
at different shifts must share every node, element, section, load and
restraint and differ in their contact targets alone -- asserted mechanically,
because "same nodes, same elements" is exactly the sort of thing that stays
true by inspection right up until it does not.

THE ONE FORMULA THAT MUST NOT BE WRONG is the contact target. Tracker item 16
pairs it with arc-length node positioning as a HARD dependency: the old
`dn = arc_y * ny` is the same projection with the `ux*nx` term silently zero,
true only under rectangular positioning. These check the closed form against
the projection it is, at every station, rather than against itself.
"""

import json
import math

import pytest

np = pytest.importorskip('numpy')

import config                                      # noqa: E402
import ils_builder                                 # noqa: E402
from slay.model.assemble import build_model        # noqa: E402
from slay.physics import contact as ct             # noqa: E402
from slay.physics import loads as ld
from slay.physics.frame import to_model_frame               # noqa: E402
from slay.physics.problem import (                 # noqa: E402
    build_problem, differs_only_in_contact)
from slay.physics.sections import bind_sections    # noqa: E402
from slay.scene import build_scene                 # noqa: E402
from slay.scene.rollers import StationRole         # noqa: E402

from tests.test_edas_archetypes import _archetypes  # noqa: E402


@pytest.fixture(scope='module')
def scene():
    return build_scene(R=85.0)


@pytest.fixture(scope='module')
def plain(scene):
    return build_model(scene)


def _ils(arch_id):
    return ils_builder.build_ils(_archetypes()[arch_id]['definition'])


def _with(scene, arch_id):
    ils = _ils(arch_id)
    return build_model(scene, ils, s_centre=0.0), ils


# ---------------------------------------------------------------------------
# sections -- the four rules
# ---------------------------------------------------------------------------

def test_plain_pipe_elements_take_the_pipeline_section(plain):
    secs = bind_sections(plain)
    assert len(secs) == plain.n_elems
    assert {s.rule for s in secs.values()} == {'pipe'}
    one = next(iter(secs.values()))
    assert one.OD == config.OD_PIPE_DEF and one.t == config.T_WALL_DEF
    assert one.E == config.STEEL_E


def test_a_declared_section_is_used_verbatim(scene):
    m, _ils = _with(scene, 'ILS-TP')
    secs = bind_sections(m)
    declared = [s for s in secs.values() if s.rule == 'declared']
    assert len(declared) == 2, 'the thick body'
    assert all(s.OD > config.OD_PIPE_DEF for s in declared)
    assert all(s.owner == 'GD-TP' for s in declared)


def test_a_stiffness_ratio_scales_the_modulus_not_the_section(scene):
    """EA and EI scale TOGETHER, which is what "a multiple of a plain pipe
    element of the same length" means. Reporting it as a thicker pipe would
    put the wrong fibre distance on every stress derived from it."""
    m, _ils = _with(scene, 'ILS-EAST')
    secs = bind_sections(m)
    ratio = [s for s in secs.values() if s.rule == 'ratio']
    assert len(ratio) == 18
    plain_sec = next(s for s in secs.values() if s.rule == 'pipe')
    for s in ratio:
        assert s.ratio == pytest.approx(2.5)
        assert (s.OD, s.t) == (plain_sec.OD, plain_sec.t), 'same section'
        assert s.E == pytest.approx(2.5 * plain_sec.E)
        assert s.EA / plain_sec.EA == pytest.approx(2.5)
        assert s.EI / plain_sec.EI == pytest.approx(2.5)


def test_section_at_is_resolved_per_element_at_its_own_midpoint(scene):
    """A taper changes along its length, so one answer per LINE would be
    wrong. The assembly is the single source (tracker item 18) and the
    conversion back to ILS-local x is `x = s_centre - s`."""
    m, ils = _with(scene, 'ILS-TT')
    secs = bind_sections(m, assembly=ils.assembly, s_centre=0.0)
    at = {n.index: n for n in m.nodes}
    taper = sorted(
        ((0.5 * (at[e.n1].s + at[e.n2].s), secs[e.index]) for e in m.elements
         if e.stiffness_rule == 'section_at'), key=lambda r: r[0])
    assert len(taper) == 4, 'two tapers, two elements each'

    # It THICKENS toward the body and the two tapers mirror each other. Two
    # distinct ODs across four elements is symmetry, not one answer per line
    # -- what would say the resolution is per-line is all four being equal.
    ods = [s.OD for _mid, s in taper]
    assert ods[0] < ods[1] and ods[3] < ods[2], 'thickens inward'
    assert ods[0] == pytest.approx(ods[3]) and ods[1] == pytest.approx(ods[2])
    body = max(s.OD for s in secs.values() if s.rule == 'declared')
    assert all(config.OD_PIPE_DEF < od < body for od in ods)

    for e in m.elements:
        if e.stiffness_rule != 'section_at':
            continue
        mid = 0.5 * (at[e.n1].s + at[e.n2].s)
        expect = ils.assembly.section_at(0.0 - mid)
        assert secs[e.index].OD == pytest.approx(expect.OD)
        assert secs[e.index].t == pytest.approx(expect.t)


def test_section_at_with_no_assembly_refuses(scene):
    """There is no local fallback for it, and inventing one would answer a
    different question quietly."""
    m, _ils = _with(scene, 'ILS-TT')
    with pytest.raises(ValueError, match='single source'):
        bind_sections(m)


def test_connectors_are_not_sectioned(scene):
    """Their stiffness is PRESCRIBED by pass 4's rule -- a 1 x OD length of
    pipeline whatever their own length -- so there is nothing to bind."""
    m, _ils = _with(scene, 'ILS-EAST')
    secs = bind_sections(m)
    conn = [e.index for e in m.elements if e.connector is not None]
    assert conn and not [k for k in conn if k in secs]


# ---------------------------------------------------------------------------
# contact targets -- the formula tracker item 16 pairs with node positioning
# ---------------------------------------------------------------------------

def test_the_closed_form_is_the_projection_it_claims_to_be(scene):
    """Checked, not trusted. If these ever disagree the closed form is what
    is wrong -- it is the derived one."""
    for s in (0.0, 4.0, 8.0, 16.0, 24.0, 32.0, 40.0, 48.0):
        th = scene.path.theta(s)
        assert ct.arc_target(scene.path.R, th) == pytest.approx(
            ct.arc_target_by_projection(scene.path, s), abs=1e-12)


def test_targets_match_the_closed_form_at_every_station(scene, plain):
    """The card's VERIFY clause, at R = 85."""
    targets = ct.contact_targets(plain, scene)
    assert [c.station for c in targets] == \
        ['VR4', 'VR3', 'VR2', 'VR1', 'SR1', 'SR2', 'SR3', 'SR4', 'SR5',
         'SR6', 'SR7']
    for c in targets:
        assert c.dn == pytest.approx(
            ct.arc_target(scene.path.R, c.theta), abs=1e-12)
        assert c.lift == 0.0, 'plain pipe lifts the centreline nowhere'


def test_the_deck_asks_for_nothing_and_the_arc_asks_downward(scene, plain):
    """dn is NEGATIVE on the arc and that is right: the normal points from
    the roller toward the pipe -- upward -- and the arc falls away below the
    deck line the straight reference pipe continues along."""
    targets = {c.station: c for c in ct.contact_targets(plain, scene)}
    for name in ('VR4', 'VR3', 'VR2', 'VR1', 'SR1'):
        assert targets[name].dn == 0.0 and targets[name].theta == 0.0
    arc = [targets[f'SR{i}'].dn for i in range(2, 7)]
    assert all(v < 0 for v in arc)
    assert arc == sorted(arc, reverse=True), 'monotone down the stinger'
    assert targets['SR6'].dn == pytest.approx(-11.09002, abs=5e-5)


def test_the_target_takes_an_angle_not_an_arc_length(scene):
    """Pinned, because it was written the wrong way round the first time and
    only the absurd magnitude caught it: -1485 m at VR4, on a station whose
    target is exactly zero. A wrong-but-plausible number here is a wrong
    model that converges."""
    # s = 40 m is a fixed arc position, NOT a station -- so this figure is
    # independent of roller spacing and survived the move to 9 m untouched.
    s = 40.0
    assert ct.arc_target(scene.path.R, scene.path.theta(s)) == \
        pytest.approx(-8.89707, abs=5e-6)
    assert abs(ct.arc_target(scene.path.R, s)) > 1000.0, \
        'reading an arc length as radians is off by three orders'


def test_keeping_the_old_formula_would_be_metres_wrong(scene):
    """Tracker item 16's hard pair, measured here rather than quoted.

    `dn = arc_y * ny` is the same projection with the `ux*nx` term zero --
    true only under RECTANGULAR node positioning. Under arc-length
    positioning the term returns.
    """
    err = {}
    for i in range(2, 7):
        th = scene.path.theta(8.0 * (i - 1))
        old = scene.path.R * (1 - math.cos(th)) * (-math.cos(th))
        err[f'SR{i}'] = abs(ct.arc_target(scene.path.R, th) - old)
    assert err['SR6'] == pytest.approx(0.662, abs=5e-3)
    assert err['SR2'] < 0.01, 'negligible near the tangency'
    assert list(err.values()) == sorted(err.values()), 'grows down the arc'


def test_only_contact_stations_get_targets(scene, plain):
    """The FIXED anchor is not a contact slot. `role` is what says so -- a
    list read through `one_sided` alone cannot tell a bidirectional roller
    from a station that touches nothing.

    SR7 IS one since D6, and it is bidirectional, so it is exactly the case
    `one_sided` cannot see: absent from that set for the opposite reason to
    VR5.
    """
    names = {c.station for c in ct.contact_targets(plain, scene)}
    for st in scene.stations:
        assert (st.name in names) == (st.role is StationRole.CONTACT)
    assert 'VR5' not in names, 'the anchor bears no contact'
    assert 'SR7' in names and not scene.by_name('SR7').one_sided


def test_weights_interpolate_the_station_position(scene, plain):
    """Two bracketing nodes, weights summing to one, and reproducing the
    station's own arc position -- which is the only thing that says the
    bracket is the right pair."""
    at = {n.index: n for n in plain.nodes}
    for c in ct.contact_targets(plain, scene):
        assert c.w_lo + c.w_hi == pytest.approx(1.0)
        assert 0.0 <= c.w_lo <= 1.0 and 0.0 <= c.w_hi <= 1.0
        assert c.w_lo * at[c.n_lo].s + c.w_hi * at[c.n_hi].s == \
            pytest.approx(c.s_material, abs=1e-9)


def test_one_sided_flags_ride_through(scene, plain):
    by = {c.station: c for c in ct.contact_targets(plain, scene)}
    assert by['VR4'].one_sided is False and by['VR3'].one_sided is False
    assert all(by[f'SR{i}'].one_sided for i in range(1, 7))
    assert by['VR2'].one_sided and by['VR1'].one_sided
    assert all(c.radius > 0 for c in by.values()), 'carried for the R_eff call'


def test_a_shift_moves_the_material_position_and_nothing_else(scene, plain):
    a = {c.station: c for c in ct.contact_targets(plain, scene)}
    b = {c.station: c for c in ct.contact_targets(plain, scene, shift=2.0)}
    for name in a:
        assert b[name].s_material == pytest.approx(a[name].s_material - 2.0)
        assert b[name].dn == a[name].dn, 'the roller did not move'
        assert b[name].one_sided == a[name].one_sided


def test_a_contact_surface_lifts_the_centreline(scene):
    """The surface contribution is ADDITIVE on the arc term, and it comes
    from `assembly.contact_at` -- one source, never a second implementation
    (tracker item 18)."""
    m, ils = _with(scene, 'ILS-TP')
    targets = ct.contact_targets(m, scene, assembly=ils.assembly,
                                 s_centre=0.0)
    lifted = [c for c in targets if c.lift != 0.0]
    assert lifted, 'the thick body sits under at least one roller'
    for c in lifted:
        expect = ils.assembly.contact_at(0.0 - c.s_material)
        assert c.lift == pytest.approx(expect.y - config.OD_PIPE_DEF / 2)
        assert c.surface_owner == expect.owner
        assert c.dn == pytest.approx(c.dn_arc + c.lift)
        assert c.lift > 0, 'a deeper surface holds the centreline higher'


# ---------------------------------------------------------------------------
# loads and restraints
# ---------------------------------------------------------------------------

def test_self_weight_acts_down_and_totals_rho_A_g_L(plain):
    secs = bind_sections(plain)
    w = ld.self_weight(plain, secs)
    assert all(v.fy > 0 for v in w), 'y is positive-DOWN'
    total = sum(v.fy for v in w)
    at = {n.index: n for n in plain.nodes}
    length = sum(math.hypot(at[e.n2].s - at[e.n1].s, at[e.n2].y - at[e.n1].y)
                 for e in plain.elements)
    A = next(iter(secs.values())).A
    assert total == pytest.approx(config.RHO_STEEL * A * config.G * length)


def test_a_thicker_element_weighs_more(scene):
    m, _ils = _with(scene, 'ILS-TP')
    secs = bind_sections(m)
    w = {v.node: v.fy for v in ld.self_weight(m, secs)}
    at = {n.index: n for n in m.nodes}
    thick = [e for e in m.elements if secs.get(e.index)
             and secs[e.index].rule == 'declared']
    for e in thick:
        L = abs(at[e.n2].s - at[e.n1].s)
        share = config.RHO_STEEL * secs[e.index].A * config.G * L / 2
        assert w[e.n1] >= share and w[e.n2] >= share


def test_tension_acts_at_the_load_station_along_its_own_tangent(scene, plain):
    """SR7 exists for this. Applying tension at the tip with SR6's tangent
    put a spurious transverse force on the end and reported 2.46% strain at
    SR6 against a ~0.83% reference -- a 3x error."""
    T = 120e3
    out = ld.lay_tension(plain, scene, T)
    assert len(out) == 1
    st = scene.load
    assert st.name == 'SR7'
    tx, ty = to_model_frame(scene.path.tangent(st.s_arc))
    assert out[0].fx == pytest.approx(T * tx)
    assert out[0].fy == pytest.approx(T * ty)
    assert math.hypot(out[0].fx, out[0].fy) == pytest.approx(T)

    tx6, ty6 = scene.path.tangent(scene.by_name('SR6').s_arc)
    assert (tx, ty) != to_model_frame((tx6, ty6)), \
        'the two tangents genuinely differ'
    assert ld.lay_tension(plain, scene, 0.0) == []


def test_tension_pulls_the_tip_away_from_the_vessel(scene, plain):
    """THE SIGN, stated as physics rather than as a formula (L049).

    The model is cut at the stinger tip and the suspended span below pulls on
    that cut, away from the vessel and downward; the tensioner's hold is the
    reaction at the FIXED station. In model components that is `fx > 0` --
    `s` increases toward the stinger -- and `fy > 0`, because `y` is down.

    The earlier version of this test asserted `fx == T * tx` against the
    WORLD tangent, so it ratified the defect instead of catching it. A test
    that restates the implementation cannot fail with it; this one names the
    direction the pipe is pulled.
    """
    out = ld.lay_tension(plain, scene, 120e3)
    assert out[0].fx > 0.0, 'tension must pull the tip toward the stinger'
    assert out[0].fy > 0.0, 'and downward, along the catenary'


def test_restraints_are_the_fixed_station_and_nothing_else(scene, plain):
    r = ld.boundary_conditions(plain, scene)
    assert len(r) == 1 and r[0].source == 'VR5'
    assert r[0].components == (0, 1, 2), 'all DOF'
    at = {n.index: n for n in plain.nodes}
    assert at[r[0].node].s == pytest.approx(scene.by_name('VR5').s_arc)


def test_point_masses_resolve_or_refuse(scene):
    m, ils = _with(scene, 'ILS-EAST')
    out = ld.point_mass_loads(m, ils, s_centre=0.0)
    located, missing = ils.located_point_masses()
    assert not missing
    assert len(out) == len(located)
    for v, (_nid, mass, _x, _y) in zip(out, located):
        assert v.fy == pytest.approx(mass * config.G)


# ---------------------------------------------------------------------------
# the Problem artifact
# ---------------------------------------------------------------------------

def test_two_shifts_differ_only_in_contact(scene, plain):
    """T4's DONE WHEN clause."""
    a = build_problem(plain, scene, tension=120e3)
    b = build_problem(plain, scene, tension=120e3, shift=3.5)
    assert differs_only_in_contact(a, b)
    assert a.contacts != b.contacts, 'and they DO differ there'


@pytest.mark.parametrize('arch_id', ['ILS-TP', 'ILS-TT', 'ILS-EAST',
                                     'ILS-EASB', 'ILS-ILT'])
def test_two_shifts_differ_only_in_contact_with_an_ils(scene, arch_id):
    m, ils = _with(scene, arch_id)
    kw = dict(assembly=ils.assembly, ils=ils, s_centre=0.0, tension=120e3)
    a = build_problem(m, scene, shift=0.0, **kw)
    b = build_problem(m, scene, shift=2.25, **kw)
    assert differs_only_in_contact(a, b)


def test_the_problem_carries_no_shift_no_sweep_and_no_scene(scene, plain):
    """The three that leaked in the old code. A Problem that remembers which
    sweep step made it invites a loop that mutates it in place."""
    p = build_problem(plain, scene, shift=7.0, tension=120e3)
    fields = set(p.__dataclass_fields__)
    assert not {f for f in fields if 'shift' in f or 'sweep' in f}
    assert 'scene' not in fields and 'assembly' not in fields
    assert 'ils' not in fields
    text = p.to_json()
    assert json.loads(text)
    assert 'shift' not in text and 'sweep' not in text


def test_the_scene_is_not_mutated(scene, plain):
    before = (scene.stations, scene.extent, scene.elastic_zones, scene.spacing)
    build_problem(plain, scene, shift=5.0, tension=120e3)
    assert (scene.stations, scene.extent, scene.elastic_zones,
            scene.spacing) == before


def test_the_problem_is_complete(scene):
    m, ils = _with(scene, 'ILS-EAST')
    p = build_problem(m, scene, assembly=ils.assembly, ils=ils, s_centre=0.0,
                      tension=120e3)
    assert p.n_nodes == m.n_nodes
    assert p.n_elems == len([e for e in m.elements if e.connector is None])
    assert len(p.sections) == p.n_elems
    assert len(p.connectors) == 2
    assert len(p.associations) == 4
    assert len(p.contacts) == 11
    assert p.restraints and p.loads
    assert p.elastic_zones == scene.elastic_zones
    assert p.R == pytest.approx(85.0)
    assert any(v.source.startswith('tension') for v in p.loads)
    assert any(v.source == 'self_weight' for v in p.loads)


def test_gravity_can_be_switched_off(scene, plain):
    p = build_problem(plain, scene, gravity=False, tension=120e3)
    assert not [v for v in p.loads if v.source == 'self_weight']
    assert [v for v in p.loads if v.source.startswith('tension')]

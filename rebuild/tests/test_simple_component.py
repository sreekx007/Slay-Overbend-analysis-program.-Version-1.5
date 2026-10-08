"""GD-Simple: an elastic pipe body over an offset shroud.

THREE THINGS CAN GO WRONG SILENTLY HERE, and each has a test below rather
than a comment:

  1. The body is not actually neutral, so GD-Simple is a thick-pipe study
     wearing a different name.
  2. The modulus override misses -- a renamed `id`, a typo -- and the body
     runs at the pipeline's E. That is a plausible number for a case nobody
     asked for, which is the L097/L108 failure mode exactly.
  3. The body's elastic span REPLACES the buffer's instead of joining it, so
     feedstock yields and mode A carries the hinge forward (L109). Nothing
     fails; a number downstream just moves.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / 'rebuild', REPO, REPO / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import config                                               # noqa: E402
import ils_builder                                          # noqa: E402
from slay.data.materials import material                    # noqa: E402
from slay.define import simple as sp                        # noqa: E402
from slay.model import assemble                             # noqa: E402
from slay.physics.problem import build_problem              # noqa: E402
from slay.physics.sections import bind_sections             # noqa: E402
from slay.report import regions as rg                       # noqa: E402
from slay.solve.kernel import mesh_of_problem               # noqa: E402
from slay.study import sweep                                # noqa: E402

D = 0.4064
TON = 9.80665e3
FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'


def _posed(E=100e9, L_body=10 * D, V=1.5 * D, L1=10 * D, L2=2.5 * D,
           shift=0.0):
    """One GD-Simple, built and posed. Returns (simple, scene, s_centre, p)."""
    sm = sp.build(E=E, L_body=L_body, V=V, L1=L1, L2=L2)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_centre = sweep.start_centre(scene, L)
    model = assemble.build_model(
        scene, sm.ils, s_centre=s_centre,
        extra_stations=sweep._required_stations(scene))
    kw = sweep.with_buffer(scene, assembly=sm.ils.assembly, ils=sm.ils,
                           elastic_spans=sm.elastic_spans(s_centre),
                           E_by_owner=sm.E_by_owner())
    p = build_problem(model, scene, shift=shift, s_centre=s_centre,
                      tension=100 * TON, material=material('j2'), **kw)
    return sm, scene, s_centre, model, p


# ---------------------------------------------------------------------------
# 1. the body is neutral
# ---------------------------------------------------------------------------

def test_the_body_carries_the_PIPELINE_section_and_steps_nothing():
    """`t_comp == t_pipe` is what makes GD-Simple GD-Simple. A step would
    make it a GD-TP study, reported at junctions instead of in regions."""
    sm = sp.build(E=100e9, L_body=10 * D, V=1.5 * D, L1=10 * D, L2=2.5 * D)
    pipe = sm.ils.assembly.pipe
    body = [c for c in sm.ils.assembly.components if c.code == 'GD-TP'][0]
    assert body.t_comp == pytest.approx(pipe.t_pipe, abs=0.0)
    assert body.OD_comp == pytest.approx(pipe.OD_pipe, abs=1e-12)
    assert body.wt_ratio == pytest.approx(1.0)
    assert body.V == pytest.approx(0.0, abs=1e-12)   # no roller rise of its own


def test_the_shroud_V_is_measured_to_its_BOTTOM_FLAT():
    """The offset the caller states is pipe centreline down to the flat the
    roller touches, which is what `contact_at` returns on the deep section.
    Measured off the built component, not asserted from the spec."""
    V = 1.5 * D
    sm = sp.build(E=100e9, L_body=10 * D, V=V, L1=10 * D, L2=2.5 * D)
    shroud = [c for c in sm.ils.assembly.components if c.code == 'GD-SH'][0]
    assert shroud.contact_at(0.0).y == pytest.approx(V)
    # And the pipe is held off the roller by V - OD/2, not by V.
    assert shroud.CL_lift == pytest.approx(V - sm.ils.assembly.pipe.OD_pipe / 2)


def test_body_and_shroud_lengths_are_independent():
    """Either may be the longer, and the assembly extent follows whichever."""
    long_body = sp.build(E=1e11, L_body=30 * D, V=1.5 * D, L1=10 * D,
                         L2=2.5 * D)
    long_shroud = sp.build(E=1e11, L_body=2 * D, V=1.5 * D, L1=10 * D,
                           L2=2.5 * D)
    assert long_body.extent == pytest.approx((-15 * D, 15 * D))
    # L1 + 2*L2 = 15 D
    assert long_shroud.extent == pytest.approx((-7.5 * D, 7.5 * D))


@pytest.mark.parametrize('kw, word', [
    (dict(E=0.0), 'positive'),
    (dict(E=-1.0), 'positive'),
    (dict(L_body=0.0), 'positive'),
    (dict(L1=-1.0), 'positive'),
    (dict(V=0.1 * D), 'BOTTOM FLAT'),
])
def test_a_GD_Simple_that_is_not_one_is_refused(kw, word):
    base = dict(E=1e11, L_body=10 * D, V=1.5 * D, L1=10 * D, L2=2.5 * D)
    with pytest.raises(sp.SimpleRuleError, match=word):
        sp.build(**{**base, **kw})


# ---------------------------------------------------------------------------
# 2. the modulus lands on the body and nowhere else
# ---------------------------------------------------------------------------

def test_the_body_gets_its_own_modulus_and_the_pipeline_keeps_its_own():
    _sm, _sc, _c, _m, p = _posed(E=100e9)
    by_E = {}
    for sec in p.sections:
        by_E.setdefault(round(sec.E, 3), 0)
        by_E[round(sec.E, 3)] += 1
    assert set(by_E) == {100e9, float(config.STEEL_E)}
    # The body is 10 D of pipe at the ruled 2 x OD mesh.
    assert by_E[100e9] == 4
    assert by_E[float(config.STEEL_E)] > 100


def test_an_override_that_matches_no_element_is_REFUSED_not_ignored():
    """The whole failure mode: a renamed `id` leaves the body on the
    pipeline modulus and reports a number for the wrong material."""
    _sm, _sc, _c, model, _p = _posed()
    with pytest.raises(ValueError, match='matches nothing|no element'):
        bind_sections(model, E_by_owner={'NOT-A-BODY': 1e11})


def test_the_error_names_what_the_model_actually_holds():
    _sm, _sc, _c, model, _p = _posed()
    with pytest.raises(ValueError) as e:
        bind_sections(model, E_by_owner={'typo': 1e11})
    assert sp.BODY_ID in str(e.value) and 'pipeline' in str(e.value)


def test_a_modulus_and_a_stiffness_ratio_on_one_body_is_refused():
    """Two ways of saying the same thing; multiplying them would be a guess.
    Driven through a real EA archetype, which is where ratios come from."""
    arch = {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}
    ils = ils_builder.build_ils(
        copy.deepcopy(arch['ILS-EASB']['definition']))
    L = ils.extent[1] - ils.extent[0]
    scene = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    model = assemble.build_model(
        scene, ils, s_centre=sweep.start_centre(scene, L),
        extra_stations=sweep._required_stations(scene),
        emit_unenforced_conn_types=frozenset({'S'}))
    ratio_owners = {e.owner for e in model.elements
                    if e.connector is None and e.stiffness_ratio is not None}
    assert ratio_owners, 'ILS-EASB should carry stiffness_ratio members'
    with pytest.raises(ValueError, match='Pick one'):
        bind_sections(model, E_by_owner={ratio_owners.pop(): 1e11})


@pytest.mark.parametrize('bad', [0.0, -1.0])
def test_a_non_positive_modulus_is_refused(bad):
    _sm, _sc, _c, model, _p = _posed()
    with pytest.raises(ValueError, match='must be positive'):
        bind_sections(model, E_by_owner={sp.BODY_ID: bad})


# ---------------------------------------------------------------------------
# 3. the buffer keeps its elastic span -- L109
# ---------------------------------------------------------------------------

def test_with_buffer_ADDS_the_buffer_span_instead_of_replacing_it():
    sm = sp.build(E=1e11, L_body=10 * D, V=1.5 * D, L1=10 * D, L2=2.5 * D)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_centre = sweep.start_centre(scene, L)
    body = sm.elastic_spans(s_centre)
    got = sweep.with_buffer(scene, elastic_spans=body)['elastic_spans']
    assert body[0] in got, 'the caller span was dropped'
    assert sweep.buffer_span(scene) in got, 'the BUFFER span was dropped'
    assert len(got) == 2


def test_with_buffer_is_idempotent_and_order_free():
    sm = sp.build(E=1e11, L_body=10 * D, V=1.5 * D, L1=10 * D, L2=2.5 * D)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    once = sweep.with_buffer(scene, elastic_spans=sm.elastic_spans(
        sweep.start_centre(scene, L)))
    twice = sweep.with_buffer(scene, once)
    assert once['elastic_spans'] == twice['elastic_spans']
    assert once['vertical_at'] == twice['vertical_at']


def test_the_kernel_gets_THREE_materials_the_body_elastic_at_its_own_E():
    """The end of the chain, and the only test that proves the two halves
    arrive together: an elastic law AND a separate modulus. A J2 body at
    100 GPa would yield at the same stress and a different strain, which is
    not a material anybody specified."""
    _sm, _sc, _c, _m, p = _posed(E=100e9)
    ms, _mdl, _ix = mesh_of_problem(p)
    seen = sorted((type(m).__name__, round(getattr(m, 'E', 0.0) / 1e9, 1))
                  for m in ms.material_map.values())
    assert seen == [('IncrementalIsotropic', 210.0),   # the J2 pipeline
                    ('Material', 100.0),               # GD-Simple's body
                    ('Material', 210.0)]               # the feedstock buffer


# ---------------------------------------------------------------------------
# 4. the Xb/Xe scheme
# ---------------------------------------------------------------------------

def test_simple_geometry_measures_the_BODY_not_the_shroud():
    sm, _sc, s_centre, _m, _p = _posed(L_body=10 * D)
    g = rg.simple_geometry(sm.ils, s_centre)
    assert isinstance(g, rg.SimpleGeometry)
    assert g.L_body == pytest.approx(10 * D, abs=5e-3)
    # the shroud is 15 D overall, so the body does NOT cover it
    assert g.L_total == pytest.approx(15 * D, abs=5e-3)
    assert g.body_covers_shroud is False


def test_a_body_longer_than_its_shroud_covers_it():
    sm, _sc, s_centre, _m, _p = _posed(L_body=30 * D)
    g = rg.simple_geometry(sm.ils, s_centre)
    assert g.body_covers_shroud is True


def test_Xb_Xe_partition_every_element_exactly_once():
    sm, _sc, s_centre, _m, p = _posed()
    g = rg.simple_geometry(sm.ils, s_centre)
    s_of = {i: sv for (i, sv, _y) in p.nodes}
    names = [rg.region_of_element(s_of[n1], s_of[n2], g)
             for (_i, n1, n2, _o, _l) in p.elements]
    assert set(names) == set(rg.SIMPLE_REGIONS)
    assert all(n in rg.SIMPLE_REGIONS for n in names)
    assert len(names) == len(p.elements)       # none unassigned, none double


def test_Xe_is_TWO_spans_and_says_so():
    """Xe is the complement of Xb, so no single interval names it. A row
    claiming one would be a lie about which steel it measured."""
    sm, _sc, s_centre, _m, p = _posed()
    g = rg.simple_geometry(sm.ils, s_centre)
    b = rg.bounds(g)
    assert [n for n, _lo, _hi in b] == ['Xe', 'Xb', 'Xe']
    peaks = rg.region_peaks([], p, g, float('inf'))
    assert len(peaks['Xe']['spans']) == 2
    assert len(peaks['Xb']['spans']) == 1
    assert peaks['Xe']['s_lo'] == float('-inf')
    assert peaks['Xe']['s_hi'] == float('inf')


def test_classify_is_total_over_the_simple_scheme():
    """It must never answer 'X5' for a case that has no X5."""
    sm, _sc, s_centre, _m, _p = _posed()
    g = rg.simple_geometry(sm.ils, s_centre)
    for s in (-1e9, g.s_body_ves - 1.0, g.s_body_ves, 0.5 * (g.s_body_ves
              + g.s_body_cat), g.s_body_cat, g.s_body_cat + 1.0, 1e9,
              float('-inf')):
        assert rg.classify(s, g) in rg.SIMPLE_REGIONS


def test_a_shroud_with_a_THICK_body_in_it_is_not_a_GD_Simple():
    """ILS-SHTP steps the section, so it has junctions and the five-region
    scheme. Handing it Xb/Xe as well would put one strain in two schemes."""
    arch = {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}
    ils = ils_builder.build_ils(copy.deepcopy(arch['ILS-SHTP']['definition']))
    L = ils.extent[1] - ils.extent[0]
    s_centre = sweep.start_centre(
        sweep.scene_for(R=85.0, spacing=9.0, L_comp=L), L)
    assert rg.simple_geometry(ils, s_centre) is None
    # ...and it still gets the five-region scheme it is entitled to.
    assert rg.offset_geometry(ils, s_centre) is not None


def test_plain_pipe_and_a_bare_shroud_are_not_GD_Simples():
    arch = {a['id']: a for a in json.loads(FIXTURE.read_text())['archetypes']}
    ils = ils_builder.build_ils(copy.deepcopy(arch['ILS-SH']['definition']))
    L = ils.extent[1] - ils.extent[0]
    s_centre = sweep.start_centre(
        sweep.scene_for(R=85.0, spacing=9.0, L_comp=L), L)
    assert rg.simple_geometry(ils, s_centre) is None
    assert rg.simple_geometry(None, 0.0) is None


def test_the_simple_scheme_declares_every_column_it_emits():
    """The same contract the dataset writer enforces, for the new scheme."""
    from slay.report import schema
    sm, _sc, s_centre, _m, p = _posed()
    g = rg.simple_geometry(sm.ils, s_centre)
    cols = rg.case_columns(g, rg.region_peaks([], p, g, float('inf')))
    assert cols['region_scheme'] == 'Xb-Xe/simple'
    undeclared = [c for c in cols if schema.describe(c) is None]
    assert undeclared == []
    # The denominator is named for the region it IS, not for X2.
    assert 'xb_frac_of_xb' in cols and 'xe_frac_of_xb' in cols
    assert not any(c.endswith('_frac_of_x2') for c in cols)


# ---------------------------------------------------------------------------
# 5. the control: an elastic body at the pipeline's own modulus, where
#    nothing yields, must be indistinguishable from pipeline
# ---------------------------------------------------------------------------

def test_at_E_equal_to_the_pipeline_and_no_yielding_the_body_vanishes():
    """THE control, and the only test that exercises the whole chain.

    At E = STEEL_E the body differs from plain pipe in one way: it cannot
    yield. Run it at a lay radius where nothing yields anyway and it must
    therefore be indistinguishable -- Xb == Xe. If the modulus override
    missed, or the elastic span landed on the wrong elements, or Xb is drawn
    somewhere other than the body, this is what catches it.

    Slow (one full passage) and worth it: every cheap test above checks a
    piece in isolation, and the pieces agreeing with each other is not the
    same as the answer being right.
    """
    sm = sp.build(E=config.STEEL_E, L_body=10 * D, V=1.5 * D, L1=10 * D,
                  L2=2.5 * D)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=250.0, spacing=9.0, L_comp=L)
    s_centre = sweep.start_centre(scene, L)
    pkw = dict(elastic_spans=sm.elastic_spans(s_centre),
               E_by_owner=sm.E_by_owner())
    positions = sweep.run(scene, sm.ils, L_comp=L, step=2.0 * D,
                          tension=100 * TON, material=material('j2'), **pkw)
    from slay.report import passage as rp
    recs = rp.measure(positions, scene, L_comp=L)
    assert all(r.converged for r in recs)
    env = rp.envelope(recs)

    model = assemble.build_model(
        scene, sm.ils, s_centre=s_centre,
        extra_stations=sweep._required_stations(scene))
    p0 = build_problem(
        model, scene, shift=positions[env.index].shift, s_centre=s_centre,
        tension=100 * TON, material=material('j2'),
        **sweep.with_buffer(scene, pkw, assembly=sm.ils.assembly,
                            ils=sm.ils))
    g = rg.simple_geometry(sm.ils, s_centre)
    pk = rg.region_peaks(positions, p0, g, env.zone_s_max)
    xb, xe = pk['Xb']['peak_strain'], pk['Xe']['peak_strain']
    assert pk['Xb']['measured'] and pk['Xe']['measured']
    # Measured 8 Oct 2026: 0.2031% both sides. Held to 1% of each other --
    # loose enough for the mesh, far tighter than any defect would survive.
    assert xb == pytest.approx(xe, rel=0.01), f'Xb {xb} vs Xe {xe}'


# ---------------------------------------------------------------------------
# 6. a GD-Simple with NO shroud -- what an EA-ST reduces to
# ---------------------------------------------------------------------------

def test_a_top_structure_changes_nothing_a_roller_touches():
    """The measurement the body-only variant exists for. If this ever comes
    back with a lift, EA-ST needs a shroud after all and the reduction is
    wrong, not the test."""
    import plot_stinger as gen
    ils = gen.build_component_ils('ILS-EAST')
    half = ils.assembly.pipe.OD_pipe / 2.0
    for x in (-5.0, -2.0, 0.0, 2.0, 5.0):
        c = ils.assembly.contact_at(x)
        assert c is not None and c.y == pytest.approx(half, abs=1e-12)
        assert getattr(c, 'owner', 'pipe') == 'pipe'


def test_a_body_only_GD_Simple_builds_and_has_no_shroud():
    sm = sp.build(E=1767e9, L_body=10 * D)
    assert sm.has_shroud is False
    codes = [c.code for c in sm.ils.assembly.components]
    assert codes == ['GD-TP'], f'expected the body alone, got {codes}'
    assert sm.extent == pytest.approx((-5 * D, 5 * D))
    # and it still carries the pipeline section
    body = sm.ils.assembly.components[0]
    assert body.OD_comp == pytest.approx(sm.ils.assembly.pipe.OD_pipe)


def test_a_half_stated_shroud_is_refused():
    """Two of V/L1/L2 is not a component; defaulting the third would invent
    geometry nobody asked for."""
    for kw in (dict(V=0.25), dict(V=0.25, L1=1.0), dict(L1=1.0, L2=0.1)):
        with pytest.raises(sp.SimpleRuleError, match='together'):
            sp.build(E=1e11, L_body=4.0, **kw)


def test_the_body_only_case_still_gets_Xb_and_Xe():
    """`offset_geometry` returns None without a shroud, and the Xb/Xe
    partition does not need one -- it is drawn on the BODY."""
    sm = sp.build(E=1767e9, L_body=10 * D)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_centre = sweep.start_centre(scene, L)
    assert rg.offset_geometry(sm.ils, s_centre) is None
    g = rg.simple_geometry(sm.ils, s_centre)
    assert isinstance(g, rg.SimpleGeometry)
    assert g.lift_max == pytest.approx(0.0, abs=1e-12)
    assert g.L_body == pytest.approx(10 * D, abs=5e-3)
    assert [n for n, _lo, _hi in rg.bounds(g)] == ['Xe', 'Xb', 'Xe']


def test_without_a_shroud_the_footprint_fields_mean_the_BODY():
    """`body_peaks` and `peak_on_shroud` read the inherited s_* fields as
    'the component's footprint'. With no shroud the body IS the footprint,
    so they are set to it deliberately rather than left at zero."""
    sm = sp.build(E=1767e9, L_body=10 * D)
    L = sm.extent[1] - sm.extent[0]
    scene = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    g = rg.simple_geometry(sm.ils, sweep.start_centre(scene, L))
    assert g.s_cat_end == pytest.approx(g.s_body_cat)
    assert g.s_ves_end == pytest.approx(g.s_body_ves)
    assert g.body_covers_shroud is True

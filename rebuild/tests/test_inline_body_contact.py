"""A roller bears on an in-line body's OWN nodes, not across it.

L100, and it is the most consequential defect found in this rebuild.

`contact.header_nodes` chose the nodes a roller may bear on by
`e.owner == 'pipeline'`. A thick component REPLACES a length of pipe: its
elements carry `owner='TP'` because the SECTION differs, but they are the
pipeline there -- the run is continuous through them, which the model
records as `line_id='pipeline'`. Filtered on owner, the returned chain had a
HOLE in it exactly where the component sat, and `_bracket` spanned the hole.

WHAT THAT DID, measured on a 20 D thick pipe at R = 85:

  * SR2 bearing at s_material 6.208 was bracketed by the component's END
    nodes, 8.128 m apart, so its contact target was applied as a weighted
    blend of two points four metres either side of the roller.
  * The body's nine interior nodes were held by NO CONTACT CONSTRAINT AT
    ALL.

So a component could not engage a roller it was sitting on. It bridged.

WHY THIS MATTERS BEYOND ITS OWN CORRECTNESS. Paper 1's TABLE XXIII reports
peak strain SATURATING once a component is long enough to span two rollers,
and we could not reproduce it. That mechanism was structurally unavailable
to this model. The error also scales with length -- a 2.5 D body spans about
one element and brackets almost correctly, a 40 D body spans twenty -- which
is exactly the pattern in the ledger: short components agreed to a few
percent, long ones did not.

A frame or a connector has its own `line_id` and is excluded either way,
which is what `header_nodes` always meant to do and said in its docstring.
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

from slay.model.assemble import build_model                   # noqa: E402
from slay.physics import contact as ct                        # noqa: E402
from slay.study import sweep                                  # noqa: E402

gen = pytest.importorskip('plot_stinger')
D = 0.4064


def _built(aid='ILS-TP', **kw):
    ils = gen.build_component_ils(aid, **kw)
    L = ils.extent[1] - ils.extent[0]
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=L)
    s_c = sweep.start_centre(sc, L)
    m = build_model(sc, ils, s_centre=s_c,
                    extra_stations=sweep._required_stations(sc))
    return ils, sc, s_c, m


def _span(model, owner):
    at = {n.index: n for n in model.nodes}
    s = [at[i].s for e in model.elements if e.owner == owner
         for i in (e.n1, e.n2)]
    return (min(s), max(s)) if s else None


# ---------------------------------------------------------------------------
# the chain has no hole
# ---------------------------------------------------------------------------

# (length, elements at the ruled 2 x OD mesh, interior nodes). Measured.
# THE SECOND COLUMN IS WHY THE LEDGER LOOKS THE WAY IT DOES: the old bracket
# was the WHOLE body, so the error over one element's worth scaled with
# length -- 1.25x at 2.5 D, 20x at 40 D. Paper 1's short components agreed
# with us to a few percent and its long ones did not, monotonically.
BODIES = [(2.5, 2, 1), (10.0, 4, 3), (20.0, 10, 9), (40.0, 20, 19)]


@pytest.mark.parametrize('L_OD,n_el,n_in', BODIES)
def test_the_header_chain_runs_through_an_in_line_body(L_OD, n_el, n_in):
    """Its interior nodes are header nodes, because they ARE the pipeline.

    The counts are asserted rather than just "more than none", because the
    number of nodes a roller could not see IS the size of the defect and a
    change in meshing that quietly reduced it would make this test pass
    while telling a reader something false.
    """
    _ils, _sc, _s_c, m = _built(L_OD=L_OD, t_ratio=0.053 / 0.021)
    lo, hi = _span(m, 'TP')
    inside = [s for _i, s in ct.header_nodes(m) if lo < s < hi]
    assert inside, (
        f'a {L_OD} D component contributes no header nodes, so a roller on '
        f'it would bracket across the whole body')
    assert len(inside) == n_in, (
        f'{L_OD} D: {len(inside)} interior header nodes, expected {n_in} '
        f'for {n_el} elements')


def test_no_bracket_spans_more_than_an_element():
    """THE DEFECT, stated as the invariant it broke. A contact target is
    interpolated between two bracketing nodes; if they are not adjacent, the
    roller's demand is applied to pipe it is nowhere near."""
    ils, sc, s_c, m = _built(L_OD=20.0, t_ratio=0.053 / 0.021)
    at = {n.index: n for n in m.nodes}
    worst = 0.0
    for shift in (0.0, 2.845, 5.0):
        for t in ct.contact_targets(m, sc, assembly=ils.assembly,
                                    shift=shift, s_centre=s_c):
            worst = max(worst, abs(at[t.n_hi].s - at[t.n_lo].s))
    assert worst < 1.0, (
        f'a contact slot is bracketed across {worst:.3f} m -- longer than an '
        f'element, so it is applied to the wrong pipe')


def test_a_roller_ON_the_body_brackets_within_the_body():
    """Not merely a short bracket -- the right one."""
    ils, sc, s_c, m = _built(L_OD=20.0, t_ratio=0.053 / 0.021)
    at = {n.index: n for n in m.nodes}
    lo, hi = _span(m, 'TP')
    found = 0
    for t in ct.contact_targets(m, sc, assembly=ils.assembly, shift=2.845,
                                s_centre=s_c):
        if lo <= t.s_material <= hi:
            found += 1
            assert lo <= at[t.n_lo].s <= hi and lo <= at[t.n_hi].s <= hi
    assert found, 'no roller lands on the body at this shift -- weak test'


# ---------------------------------------------------------------------------
# and the exclusions `header_nodes` always meant still hold
# ---------------------------------------------------------------------------

def test_a_frame_and_its_connectors_are_still_excluded():
    """EA-SB's top chord lies on the centreline and a connector's pipe-side
    node sits exactly on the pipe. Coincident, deliberately distinct, and a
    roller bears on neither."""
    _ils, _sc, _s_c, m = _built('ILS-EASB')
    header = {i for i, _s in ct.header_nodes(m)}
    for owner in ('SB', 'GD-Con'):
        theirs = {i for e in m.elements if e.owner == owner
                  for i in (e.n1, e.n2)}
        if not theirs:
            continue
        own_only = theirs - {i for e in m.elements
                             if getattr(e, 'line_id', '') == 'pipeline'
                             for i in (e.n1, e.n2)}
        assert not (own_only & header), f'{owner} nodes leaked into the header'


def test_plain_pipe_is_unchanged():
    """Nothing but a component has a line_id that differs from its owner, so
    every plain-pipe model answers exactly as before."""
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0)
    m = build_model(sc, None, s_centre=sweep.start_centre(sc, 0.0),
                    extra_stations=sweep._required_stations(sc))
    by_owner = sorted({i for e in m.elements if e.owner == 'pipeline'
                       for i in (e.n1, e.n2)})
    assert [i for i, _s in ct.header_nodes(m)] == sorted(
        by_owner, key=lambda i: {n.index: n for n in m.nodes}[i].s)

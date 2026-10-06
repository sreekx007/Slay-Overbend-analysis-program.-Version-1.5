"""A region with no elements is NOT a region with zero strain.

THE DEFECT, measured. Paper 1's Series 4 includes an R = 70 / T = 120 MT
configuration at L1 = 5 D. That is 2.032 m of deep section, so each of the
three reporting thirds is 0.677 m -- SHORTER THAN ONE ELEMENT at the ruled
2 x OD density (0.813 m). No element midpoint lands in X3, and
`region_peaks` reported `peak_strain = 0.0`, which went into a comparison
table as 0.0000% while X2 and X4 either side read 0.85% and 0.68%.

This is `body_peaks`' defect in a second place, and its docstring already
names the reason it matters: "a zero reads as 'nothing happening here'", and
nobody checks a quiet number. The fix is not to invent a value -- there is
no measurement to be had at that mesh -- but to say so, so a reader cannot
mistake the absence for a reading.
"""
from __future__ import annotations

import pytest

pytest.importorskip('numpy')

from slay.report import regions as rg                       # noqa: E402


class _Pos:
    def __init__(self, shift, strains):
        self.shift = shift
        self.result = type('R', (), {'strains': strains, 'moments': ()})()


class _Problem:
    """Two elements, placed so one reporting third gets neither."""

    def __init__(self, nodes, elements):
        self.nodes = nodes
        self.elements = elements


def test_the_thirds_can_be_shorter_than_one_element():
    """The arithmetic that makes the defect reachable, stated plainly."""
    OD, L1 = 0.4064, 5 * 0.4064          # Paper 1 Series 4, R=70 / 120 MT
    third, element = L1 / 3.0, 2.0 * OD
    assert third < element, (
        f'a third is {third:.3f} m and an element {element:.3f} m -- if this '
        f'ever reverses, the empty-region case stops being reachable here')


def test_an_unmeasured_region_is_flagged_not_zeroed():
    """`measured` is False where no element landed, and callers must read it
    instead of the zero beside it."""
    # L1 = 5 D deep section centred on 0, 2.5 D tapers either side.
    geom = rg.OffsetGeometry(
        owner='GD-SH', OD=0.4064, V=0.4064, lift_max=0.2032,
        s_deep_cat=1.016, s_deep_ves=-1.016,
        s_cat_end=2.032, s_ves_end=-2.032)
    # one element in each of X2 and X4, none in X3
    nodes = [(0, 1.016, 0.0), (1, 0.339, 0.0), (2, -1.016, 0.0),
             (3, -0.339, 0.0)]
    elements = [(0, 0, 1, 'pipeline', 0.677), (1, 2, 3, 'pipeline', 0.677)]
    p = _Problem(nodes, elements)
    pos = [_Pos(0.0, ((0, 0.677, 0.0085), (1, -0.677, 0.0068)))]

    out = rg.region_peaks(pos, p, geom, zone_s_max=100.0)
    assert out['X3']['n_elements'] == 0
    assert out['X3']['measured'] is False, (
        'X3 holds no elements, so its 0.0 is an absence and must say so')
    assert out['X3']['peak_strain'] == 0.0, (
        'the numeric column may still be 0.0 -- `measured` is what a reader '
        'must consult, and inventing a value would be worse')


def test_frac_of_x2_is_not_computed_against_an_unmeasured_X2():
    """A ratio against an absence is meaningless, and 0.0 would read as
    'this region is quiet' rather than 'X2 was never measured'."""
    # L1 = 5 D deep section centred on 0, 2.5 D tapers either side.
    geom = rg.OffsetGeometry(
        owner='GD-SH', OD=0.4064, V=0.4064, lift_max=0.2032,
        s_deep_cat=1.016, s_deep_ves=-1.016,
        s_cat_end=2.032, s_ves_end=-2.032)
    nodes = [(0, 8.0, 0.0), (1, 8.7, 0.0)]
    elements = [(0, 0, 1, 'pipeline', 0.7)]        # out past the body, X1
    p = _Problem(nodes, elements)
    out = rg.region_peaks([_Pos(0.0, ((0, 8.35, 0.009),))], p, geom,
                          zone_s_max=100.0)
    assert out['X2']['measured'] is False
    assert all(r['frac_of_x2'] == 0.0 for r in out.values())

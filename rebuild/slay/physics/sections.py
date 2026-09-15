"""slay.physics.sections -- what each element is made of, and how thick.

T3 emitted geometry and DECLARATIONS: an element carries either a `Section`,
or a `stiffness_ratio`, or the rule name `'section_at'`, or nothing at all.
This module resolves every one of those into the numbers a solver needs, and
it is the only place that does.

THE FOUR CASES, and they are not interchangeable:

    Section          a component states its own OD and wall directly.
    stiffness_ratio  a STRUCTURE member. Its stiffness is a multiple of a
                     plain pipe element OF THE SAME LENGTH -- EA and EI scale
                     together, so it is the same section at `ratio * E`, not
                     a different section. GD-ST and GD-SB both use 2.5.
    'section_at'     resolve PER ELEMENT by asking the assembly what the
                     section is at the element's own midpoint. A tapered body
                     changes along its length, so one answer per line would
                     be wrong; tracker item 18's rule is that the assembly is
                     the single source and nothing reimplements it.
    none             plain pipeline.

CONNECTORS ARE NOT IN HERE AT ALL. Their stiffness is PRESCRIBED by pass 4's
rule -- a 1 x OD length of pipeline whatever their own length -- so they have
no section to bind and `slay.physics.connector` owns them end to end.

THE FRAME CONVERSION lives here because this is where it is needed and
nowhere else. `build_model` placed the ILS with `s = s_centre - x_local`, so
going back is `x_local = s_centre - s`. Asking `assembly.section_at` with a
model `s` instead of an ILS-local `x` silently samples the wrong station --
and on a symmetric archetype it would even look right.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import config


@dataclass(frozen=True)
class ElementSection:
    """The resolved section of one element, and where it came from."""
    index: int
    OD: float
    t: float
    E: float
    owner: str
    rule: str                 # 'declared' | 'ratio' | 'section_at' | 'pipe'
    ratio: Optional[float] = None

    @property
    def A(self) -> float:
        ID = self.OD - 2.0 * self.t
        return math.pi / 4.0 * (self.OD**2 - ID**2)

    @property
    def I(self) -> float:
        ID = self.OD - 2.0 * self.t
        return math.pi / 64.0 * (self.OD**4 - ID**4)

    @property
    def EA(self) -> float:
        return self.E * self.A

    @property
    def EI(self) -> float:
        return self.E * self.I


def bind_sections(model, assembly=None, s_centre: float = 0.0,
                  OD: float = None, t_wall: float = None,
                  E: float = None) -> dict:
    """{element index -> ElementSection} for every non-connector element.

    `assembly` is needed only where an element declares `'section_at'`; a
    model with no such element resolves without one.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    t_wall = config.T_WALL_DEF if t_wall is None else t_wall
    E = config.STEEL_E if E is None else E

    at = {n.index: n for n in model.nodes}
    out = {}
    for e in model.elements:
        if e.connector is not None:
            continue                       # prescribed, not sectioned
        if e.section is not None:
            out[e.index] = ElementSection(
                e.index, e.section.OD, e.section.t, E,
                getattr(e.section, 'owner', e.owner), 'declared')
        elif e.stiffness_ratio is not None:
            # Same section, scaled modulus. EA and EI scale together, which
            # is what "a multiple of a plain pipe element of the same length"
            # means -- so it is NOT a thicker pipe, and reporting it as one
            # would put the wrong fibre distance on every stress it produces.
            out[e.index] = ElementSection(
                e.index, OD, t_wall, e.stiffness_ratio * E, e.owner,
                'ratio', ratio=e.stiffness_ratio)
        elif e.stiffness_rule == 'section_at':
            if assembly is None:
                raise ValueError(
                    f"element {e.index} ({e.line_id}) declares "
                    f"stiffness_rule='section_at' and no assembly was given "
                    f"to ask. The assembly is the single source for this "
                    f"(tracker item 18); there is no local fallback.")
            a, b = at[e.n1], at[e.n2]
            x_local = s_centre - 0.5 * (a.s + b.s)
            sec = assembly.section_at(x_local)
            out[e.index] = ElementSection(
                e.index, sec.OD, sec.t, E, sec.owner, 'section_at')
        else:
            out[e.index] = ElementSection(e.index, OD, t_wall, E, 'pipe',
                                          'pipe')
    return out


def bind_material(model, material):
    """The material every element is made of.

    ONE material for the whole model, deliberately. `stiffness_ratio` is a
    stiffness statement, not a material one -- it scales E on the same
    section -- and nothing in the published set gives two components
    different steels. A second material would be a real modelling change and
    should look like one, not arrive as a default.
    """
    return material

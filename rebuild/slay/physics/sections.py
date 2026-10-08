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
                  E: float = None, E_by_owner=None) -> dict:
    """{element index -> ElementSection} for every non-connector element.

    `assembly` is needed only where an element declares `'section_at'`; a
    model with no such element resolves without one.

    `E_by_owner` GIVES ONE BODY ITS OWN MODULUS, keyed on the element
    `owner` tag, and leaves every other element on the base `E`. GD-Simple
    is what needs it: a bounded span carrying the PIPELINE's section whose
    modulus is the free parameter of the study, so there is no section
    difference to carry the stiffness and nothing else in this module that
    could. A declared section states OD and wall and says nothing about
    what it is made of.

    IT IS NOT `stiffness_ratio`, and the distinction is the whole reason
    this argument exists rather than reusing that one. A ratio scales EA and
    EI together on an unchanged YIELD SURFACE -- fine for a structural
    member that is only ever a stiffness, wrong for a body whose modulus
    moves while its steel stays the same strength, because the yield strain
    would move with it. GD-Simple is sound only because it is also forced
    elastic (`Problem.elastic_spans`), where there is no yield surface left
    to be inconsistent with. Supplying an override for an element that
    carries a ratio is therefore refused outright rather than multiplied.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    t_wall = config.T_WALL_DEF if t_wall is None else t_wall
    E = config.STEEL_E if E is None else E
    E_by_owner = dict(E_by_owner or {})
    for owner, E_own in E_by_owner.items():
        if not E_own > 0.0:
            raise ValueError(
                f'E_by_owner[{owner!r}] = {E_own!r}: a modulus must be '
                'positive.')

    at = {n.index: n for n in model.nodes}
    # EVERY OVERRIDE MUST LAND ON SOMETHING. A key that matches no element
    # is a typo, a renamed component `id`, or a body that did not make it
    # into this model -- and all three fail by giving the body the
    # pipeline's modulus, which is a plausible answer to a question nobody
    # asked. Collected here and refused below, after the loop, so the error
    # can name what the model actually holds.
    used = set()

    def modulus(owner, e) -> float:
        if owner not in E_by_owner:
            return E
        if e.stiffness_ratio is not None:
            raise ValueError(
                f'element {e.index} ({e.line_id}) is owned by {owner!r}, '
                f'which E_by_owner gives an explicit modulus, AND declares '
                f'stiffness_ratio={e.stiffness_ratio}. Those are two ways '
                f'of saying the same thing and multiplying them would be a '
                f'guess -- a ratio is a stiffness relative to plain pipe, '
                f'an explicit E is a material property. Pick one.')
        used.add(owner)
        return E_by_owner[owner]

    out = {}
    for e in model.elements:
        if e.connector is not None:
            continue                       # prescribed, not sectioned
        if e.section is not None:
            owner = getattr(e.section, 'owner', e.owner)
            # KEYED ON THE ELEMENT's owner, not the section's. A declared
            # section may carry its own owner tag for reporting, but the
            # modulus belongs to the body that owns the STEEL, which is the
            # element. They agree for GD-Simple; where they do not, the
            # element is the one the override is written against.
            out[e.index] = ElementSection(
                e.index, e.section.OD, e.section.t,
                modulus(e.owner, e), owner, 'declared')
        elif e.stiffness_ratio is not None:
            # Same section, scaled modulus. EA and EI scale together, which
            # is what "a multiple of a plain pipe element of the same length"
            # means -- so it is NOT a thicker pipe, and reporting it as one
            # would put the wrong fibre distance on every stress it produces.
            out[e.index] = ElementSection(
                e.index, OD, t_wall,
                e.stiffness_ratio * modulus(e.owner, e), e.owner,
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
                e.index, sec.OD, sec.t, modulus(e.owner, e), sec.owner,
                'section_at')
        else:
            out[e.index] = ElementSection(e.index, OD, t_wall,
                                          modulus(e.owner, e), 'pipe',
                                          'pipe')

    missed = sorted(set(E_by_owner) - used)
    if missed:
        have = sorted({e.owner for e in model.elements
                       if e.connector is None})
        raise ValueError(
            f'E_by_owner names {missed} and no element is owned by any of '
            f'them. This model holds {have}. An override that matches '
            f'nothing leaves the body on the pipeline modulus and reports '
            f'a number for the wrong material, so it is refused rather '
            f'than ignored.')
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

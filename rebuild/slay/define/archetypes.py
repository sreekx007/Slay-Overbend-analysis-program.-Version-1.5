"""slay.define.archetypes -- the published layouts, optionally re-dimensioned.

WHAT THIS IS. `fixtures/standard_ils_layouts.json` holds seven archetype
DEFINITIONS -- ILS-TP, ILS-TT, ILS-SH, ILS-SHTP, ILS-EAST, ILS-EASB,
ILS-ILT. This builds one, with the pipeline or a component dimension
optionally changed, and hands the spec to the mirrored `ils_builder`.

IT EDITS THE ARCHETYPE'S OWN DEFINITION rather than constructing geometry
here, so `ils_builder` stays the single author of what a component IS (G7)
and the constant-bore outward growth comes with it.

WHY IT LIVES HERE NOW. Until 9 Oct 2026 this was in `tools/plot_stinger.py`
-- a 1349-line figure module documented as SUPERSEDED for drawing and "kept
for its solve helpers". Eleven files imported it, and the whole of what they
imported was this function (17 uses), `FIXTURE` (2) and two incidentals. Six
tools and four tests were parsing 1349 lines and pulling in numpy to get one
builder that needs neither.

It belongs in `define` on its own merits, not just for tidiness: "the
archetype, optionally re-dimensioned" is a statement about what a component
IS, which is this layer's whole subject, and it sits beside `simple.py` and
`simplify.py`, which both compose archetypes the same way. `plot_stinger`
imports it back, so nothing that used it there had to change at once.

Workflow: none -- pure transforms.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import ils_builder

#: The mirrored archetype fixture (G7 -- hashed in `mirror_provenance.json`).
FIXTURE = (Path(__file__).resolve().parents[2]
           / 'fixtures' / 'standard_ils_layouts.json')


def definitions() -> dict:
    """`{archetype id -> definition}`, freshly read.

    Read per call rather than cached: the fixture is mirrored data and a
    cache would hold a stale copy across a re-sync, which is exactly the
    silent-drift G7 exists to prevent.
    """
    return {a['id']: a['definition']
            for a in json.loads(FIXTURE.read_text())['archetypes']}


def build_component_ils(arch_id: str = 'ILS-TP', OD=None, t_wall=None,
                        L_OD=None, t_ratio=None):
    """The archetype, optionally re-dimensioned.

    `L_OD` and `t_ratio` are RELATIVE -- a component length in pipe
    diameters and a component wall as a multiple of the pipe's -- so they
    follow `OD` and `t_wall` when those are given too.
    """
    spec = copy.deepcopy(definitions()[arch_id])
    if OD is not None:
        spec['pipeline']['OD_pipe'] = OD
    if t_wall is not None:
        spec['pipeline']['t_pipe'] = t_wall
    od = spec['pipeline']['OD_pipe']
    tw = spec['pipeline']['t_pipe']

    # APPLY A DIMENSION TO THE COMPONENT THAT HAS IT, not to the first one.
    # `ILS-SHTP` is a shroud (GD-SH: V, L1, L2) with a thick body inside it
    # (GD-TP: t_comp, L_comp), and the shroud is components[0]. Writing
    # L_comp onto it raised `OffsetShroud.__init__() got an unexpected
    # keyword argument 'L_comp'` -- which at least failed loudly; on a
    # component that happened to accept the key it would have re-dimensioned
    # the wrong body silently (6 Oct 2026).
    def _set(key, value):
        if value is None or not spec.get('components'):
            return
        owners = [c for c in spec['components'] if key in c]
        if not owners:
            raise ValueError(
                f'no component of this archetype carries {key!r} -- '
                f'components are '
                f'{[c.get("code") for c in spec["components"]]}')
        if len(owners) > 1:
            raise ValueError(
                f'{len(owners)} components carry {key!r}; which one is meant '
                f'is not something this flag can express')
        owners[0][key] = value

    _set('L_comp', None if L_OD is None else L_OD * od)
    _set('t_comp', None if t_ratio is None else t_ratio * tw)
    return ils_builder.build_ils(spec)

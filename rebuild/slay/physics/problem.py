"""slay.physics.problem -- the Problem artifact: complete, inert, and honest
about what it does not contain.

A Problem is everything a solver needs and nothing about how it will be run.
It is the boundary between "what is being asked" and "how it gets answered",
and the value of that boundary is entirely in what it REFUSES to carry.

THREE THINGS IT MUST NOT CONTAIN, all of which leaked in the old code:

  * a SHIFT INDEX. `shift` is an argument to `build_problem`, never a field
    on the result. A Problem that remembers which sweep step made it invites
    a loop that mutates it in place.
  * a SWEEP LENGTH. How many positions get analysed is the study layer's
    question and nothing here may depend on the answer.
  * a mutated SCENE. Scene describes ONE arrangement. Two Problems built at
    different shifts must come from the same Scene object, unchanged.

THE ASSERTION THAT MAKES IT REAL is `differs_only_in_contact(a, b)`: two
Problems built at different shifts share every node, every element, every
section, every load and every restraint, and differ in their contact targets
alone. T4's DONE WHEN clause is that assertion passing -- not the code
running.

WHAT IS STILL MISSING, deliberately. The contact targets carry each roller's
`one_sided` flag and its radius, but no penalty stiffness and no active set:
those are the solver's, and `slay/solve/` already has them. A Problem states
the demand, not the enforcement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

import config

from slay.physics.contact import contact_targets
from slay.physics.loads import (boundary_conditions, lay_tension,
                                point_mass_loads, self_weight)
from slay.physics.sections import bind_material, bind_sections


@dataclass(frozen=True)
class Problem:
    """One lay position, posed. Serialisable, and inert."""
    nodes: tuple                # (index, s, y)
    elements: tuple             # (index, n1, n2, owner, line_id)
    sections: tuple             # ElementSection, by element index
    connectors: tuple           # (index, n1, n2, conn_type, length, slot)
    associations: tuple         # the declared ties, verbatim from the model
    contacts: tuple             # ContactTarget
    loads: tuple                # NodalLoad
    restraints: tuple           # Restraint
    elastic_zones: tuple
    elastic_spans: tuple = ()   # arc spans FORCED elastic, applied by solve
    material: object = None
    R: float = 0.0

    # -- queries ----------------------------------------------------------
    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_elems(self) -> int:
        return len(self.elements)

    def contact_by_station(self, name: str):
        for c in self.contacts:
            if c.station == name:
                return c
        raise KeyError(f'no contact target at {name!r}')

    def to_json(self) -> str:
        """Round-trippable text. Proves there is nothing live in here --
        no Scene, no assembly, no solver state, no numpy."""
        def clean(x):
            return [asdict(v) if hasattr(v, '__dataclass_fields__') else v
                    for v in x]
        return json.dumps({
            'nodes': [list(n) for n in self.nodes],
            'elements': [list(e) for e in self.elements],
            'sections': clean(self.sections),
            'connectors': [list(c) for c in self.connectors],
            'contacts': clean(self.contacts),
            'loads': clean(self.loads),
            'restraints': clean(self.restraints),
            'elastic_zones': [list(z) for z in self.elastic_zones],
            'R': self.R,
        }, sort_keys=True)


def build_problem(model, scene, *, assembly=None, ils=None, shift: float = 0.0,
                  s_centre: float = 0.0, tension: float = 0.0,
                  material=None, gravity: bool = True,
                  OD: float = None, t_wall: float = None,
                  E: float = None, vertical_at=(),
                  elastic_spans=()) -> Problem:
    """Pose one lay position.

    `shift` is an ARGUMENT, not a range. There is no loop over shifts in this
    module and no field on the result that remembers which one this was.

    `vertical_at` adds uy-only supports (see `boundary_conditions`).

    `elastic_spans` names arc spans whose elements take a LINEAR ELASTIC
    material whatever `material` says. Distinct from `elastic_zones`, which
    this layer still only carries: applying those would change every
    validated number, and the two should be unified deliberately rather
    than by a rename. The sweep uses this for its buffer pipe, which is
    feedstock and must never be allowed to yield.
    """
    sections = bind_sections(model, assembly=assembly, s_centre=s_centre,
                             OD=OD, t_wall=t_wall, E=E)
    loads = list(self_weight(model, sections)) if gravity else []
    if ils is not None and gravity:
        loads += point_mass_loads(model, ils, s_centre=s_centre)
    loads += lay_tension(model, scene, tension)

    return Problem(
        nodes=tuple((n.index, n.s, n.y) for n in model.nodes),
        elements=tuple((e.index, e.n1, e.n2, e.owner, e.line_id)
                       for e in model.elements if e.connector is None),
        sections=tuple(sections[k] for k in sorted(sections)),
        connectors=tuple((e.index, e.n1, e.n2, e.connector.conn_type,
                          e.connector.length, e.connector.slot)
                         for e in model.elements if e.connector is not None),
        associations=tuple(model.associations),
        contacts=tuple(contact_targets(model, scene, assembly=assembly,
                                       shift=shift, s_centre=s_centre,
                                       OD=OD)),
        loads=tuple(loads),
        restraints=tuple(boundary_conditions(model, scene,
                                             vertical_at=vertical_at)),
        elastic_zones=tuple(scene.elastic_zones),
        elastic_spans=tuple(tuple(z) for z in elastic_spans),
        material=bind_material(model, material),
        R=scene.path.R,
    )


def differs_only_in_contact(a: Problem, b: Problem) -> bool:
    """T4's DONE WHEN clause, as a function rather than a claim.

    Every field except `contacts` must be identical. Mechanical on purpose:
    "same nodes, same elements, same sections" is exactly the sort of thing
    that stays true by inspection right up until it does not.
    """
    for name in ('nodes', 'elements', 'sections', 'connectors',
                 'associations', 'loads', 'restraints', 'elastic_zones',
                 'elastic_spans', 'R'):
        if getattr(a, name) != getattr(b, name):
            return False
    return True

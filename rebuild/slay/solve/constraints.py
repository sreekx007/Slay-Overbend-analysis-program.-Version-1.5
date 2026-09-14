"""slay.solve.constraints -- associations into penalty constraints, and the
deadband active set.

A connector is a recorded `Association` (T3 §7) enforced by a penalty
constraint. This module turns the declaration into the rows a solver applies,
and carries the one joint type whose rows depend on the current displacement.

THE ACTIVE SET, and the two decisions are NOT the same test:

  ENGAGE on SEPARATION. An open `D` is not there at all -- it restrains
  neither translation nor rotation -- so the only thing that can close it is
  the two sides moving |P_gap| apart.

  RELEASE on FORCE. Once engaged the separation sits AT the gap edge by
  construction, so testing separation again would say "still at the gap"
  forever and the support could never let go. What tells you it should is the
  sign of the force it carries: a support PUSHES, and when the constraint
  would have to PULL in the direction it engaged, the sides are coming back
  inside the gap.

That asymmetry is the whole of L008. The earlier version enforced
`u_a - u_b = 0` on an engaged `D`, which dragged it back to coincidence,
released it, let it separate, and never settled: four flips and a reported
state that disagreed with the displacement it returned.

WHAT IS NOT HERE. The co-rotating frame. `S` and `D` restrain one translation
and not the other, so their rows belong in an axis that turns with the pipe
slope; every rig solved so far is horizontal, where local IS global exactly.
`Association.skewed` says which associations would notice. G9 keeps `S` and
`D` out of `build_model`'s supported set until that lands.
"""

from __future__ import annotations

import math

from slay.model.parts import TIES_OPEN, TIES_SHUT

# Release tolerance as a fraction of the applied load. The constraint force
# is O(kN) while the violation it comes from is O(1e-9 m), so the force is
# the well-conditioned thing to test -- but it is still a difference, so it
# gets a band rather than a bare sign test.
RELEASE_FTOL = 1e-6


def constraint_rows(model, engaged=None, ties_override=None):
    """(node_a, node_b, component, target) for every tie to enforce.

    Node INDICES, not DOFs -- mapping to DOFs needs the kernel's numbering
    and belongs with it (`slay.solve.kernel.dof`).

    `target` is the value of `(u_a - u_b)` the constraint enforces. It is 0.0
    everywhere except at an ENGAGED `D`, and that exception is the whole of
    what a deadband means: it holds AT the gap edge,

        u_a - u_b = +/- P_gap,      NOT      u_a - u_b = 0

    `engaged` maps an association's EA-side part node to its state -- 0 open,
    +1/-1 engaged and which way. Absent, every `D` is open, which needs no
    special case: `TIES_OPEN['D']` is already (False, False, False).

    `ties_override` maps a part node to a (bool, bool, bool) tie pattern,
    for studying a named system on a model built for another. The geometry,
    the mesh and the connector elements stay exactly as `build_model`
    produced them, so a comparison between joint types is exact rather than
    nearly so.
    """
    idx = model._part_index
    engaged = engaged or {}
    ties_override = ties_override or {}
    out = []
    for a in model.associations:
        ctype, ties = a.conn_type, a.ties
        if a.node_a in ties_override:
            ties = ties_override[a.node_a]
            if ties is None:
                continue                  # slot not populated: no tie at all
        state = engaged.get(a.node_a, 0)
        if ctype == 'D' and state:
            ties = TIES_SHUT['D']
        for k, on in enumerate(ties):
            if not on:
                continue
            target = 0.0
            if ctype == 'D' and state and k == 1:
                if a.gap is None:
                    raise ValueError(
                        f'{a.node_a}: a D engaged with no P_gap. The gap is '
                        f'component data (GD-ST/GD-SB P_gap) and has no '
                        f'default -- a silent one would choose where the '
                        f'redistributed strain goes. Nothing upstream '
                        f'enforces it either (CUN-001), so it is checked '
                        f'here.')
                target = math.copysign(a.gap, state)
            out.append((idx[a.node_a], idx[a.node_b], k, target))
    return out


def deadband_associations(model):
    """The `D` associations, in declaration order."""
    return [a for a in model.associations if a.conn_type == 'D']


def update_active_set(model, engaged, sep_of, force_of, P):
    """One active-set pass. Returns the new state map.

    `sep_of(assoc)` gives the current `(u_a - u_b)` in the restrained
    direction; `force_of(assoc, state)` the constraint force on the EA-side
    node. Passing them in keeps this free of the kernel's DOF numbering, so
    the decision rule can be tested on its own.
    """
    new = {}
    for a in deadband_associations(model):
        if a.gap is None:
            raise ValueError(f'{a.node_a}: a D connector with no P_gap')
        state = engaged.get(a.node_a, 0)
        if not state:
            sep = sep_of(a)
            new[a.node_a] = (int(math.copysign(1, sep))
                             if abs(sep) > a.gap else 0)
            continue
        # a support pushes against the direction it engaged; if it would have
        # to pull that way instead, the gap has reopened
        f = force_of(a, state)
        new[a.node_a] = 0 if f * state > RELEASE_FTOL * abs(P) else state
    return new


def layout_ties(system_types, slot_of):
    """`ties_override` for a named connection system on an existing model.

    `system_types` is a 5-tuple from `component_spec.NAMED_CONNECTION_SYSTEMS`;
    `slot_of` maps an EA-side part node to its slot number. A slot the system
    leaves empty maps to None, which `constraint_rows` reads as "no tie".
    """
    return {node: (None if system_types[slot - 1] is None
                   else TIES_OPEN[system_types[slot - 1]])
            for node, slot in slot_of.items()}

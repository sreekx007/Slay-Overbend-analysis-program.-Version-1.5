"""slay.solve.kernel -- the boundary with `nlfea_v4`, and the one indirection
every caller owes it.

The kernel is FROZEN (G6) and it numbers its own mesh. This module is the
only place in the package that touches it, so the numbering rule lives in
exactly one spot.

THE INDIRECTION, and it is not optional. `MeshedStructure._mesh` assigns mesh
indices in ELEMENT-ENCOUNTER order, so `user_node_to_mesh` is a PERMUTATION
of our node ids and not the identity. Writing connector stiffness at
`3*node_id` put it on four frame nodes' worth of the wrong rows and left
theirs empty: twelve zero diagonals and an exactly singular matrix (L009).
The map is a bijection, and a bijection is all it is.

CONNECTORS ARE ASSEMBLED OUTSIDE THE KERNEL MESH. A corotational beam derives
its stiffness from its own length and the rule forbids that, so the kernel
gets the pipeline and the structure only, and `slay.physics.connector`
supplies the rest.
"""

from __future__ import annotations

import numpy as np

import config
import nlfea_v4 as fe
from slay.physics.connector import connector_k6, NOMINAL_AXIS

# The EA structure carries a `stiffness_ratio`, which scales EA and EI
# together -- so it is the same section at `ratio * E`, not a different
# section. Two kernel materials is all that needs.
MAT_PIPE, MAT_STRUCT = 1, 2


def ea_owner(model) -> str:
    """Which owner tag the EA structure carries in THIS model: 'ST' or 'SB'.

    Read off the elements rather than assumed. Both EA archetypes go through
    one code path, and nothing downstream should have to know which it got --
    a hardcoded 'ST' is three separate crashes on ILS-EASB (L036).
    """
    owners = {e.owner for e in model.elements} - {'pipeline', 'GD-Con'}
    if len(owners) != 1:
        raise ValueError(f'expected exactly one EA owner, got {sorted(owners)}')
    return owners.pop()


def structural_ratio(model) -> float:
    """The EA structure's `stiffness_ratio`, read off its elements."""
    ratios = {e.stiffness_ratio for e in model.elements
              if e.stiffness_ratio is not None}
    if not ratios:
        return 1.0
    if len(ratios) != 1:
        raise ValueError(f'expected one stiffness_ratio, got {sorted(ratios)}')
    return ratios.pop()


def mesh(model, OD: float = None, t_wall: float = None, E: float = None):
    """`MeshedStructure` for the beams only, plus the beam list behind it.

    Asserts the kernel did not alter the model. It used to: mesh nodes were
    keyed by rounded COORDINATE, so ILS-EASB's seven coincident pairs welded
    into each other (L001). The kernel keys on node id now, and this is the
    check that says so at every call rather than once in a test.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    t_wall = config.T_WALL_DEF if t_wall is None else t_wall
    E = config.STEEL_E if E is None else E

    beams = [e for e in model.elements if e.connector is None]
    ea = ea_owner(model)
    ratio = structural_ratio(model)
    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in model.nodes],
        elements=[fe.UserElement(k, e.n1, e.n2,
                                 MAT_STRUCT if e.owner == ea else MAT_PIPE,
                                 1, seed=1)
                  for k, e in enumerate(beams)],
        sections=[fe.PipeSection(1, OD, t_wall)],
        materials=[fe.Material(MAT_PIPE, E),
                   fe.Material(MAT_STRUCT, ratio * E)])
    ms = fe.MeshedStructure(mdl)
    if ms.n_nodes != model.n_nodes:
        raise AssertionError(
            f'the kernel altered the model: {model.n_nodes} nodes in, '
            f'{ms.n_nodes} out. Coincident nodes are legal and must stay '
            f'distinct -- see G6 and L001.')
    return ms, beams


def dof(ms, node_index: int, comp: int) -> int:
    """Global DOF for one of OUR node indices. NOT `3*node_index + comp`."""
    return 3 * ms.user_node_to_mesh[node_index] + comp


def connector_elements(model):
    """(element, n1, n2, dx, dy) for each connector, chord pipe-side first."""
    at = {n.index: n for n in model.nodes}
    out = []
    for e in model.elements:
        if e.connector is None:
            continue
        a, b = at[e.n1], at[e.n2]
        out.append((e, e.n1, e.n2, b.s - a.s, b.y - a.y))
    return out


def assemble(model, ms, U, axis=NOMINAL_AXIS, OD=None, t_wall=None, E=None):
    """Tangent stiffness and internal force for beams AND connectors."""
    theta0 = np.arctan2(ms.elem_coords[:, 3] - ms.elem_coords[:, 1],
                        ms.elem_coords[:, 2] - ms.elem_coords[:, 0])
    Kf, Fint_f, _, _, _ = fe.assemble(ms, U, theta0, {}, [], 1.0)
    K = Kf.toarray()
    Fint = Fint_f.copy()
    for (_e, n1, n2, dx, dy) in connector_elements(model):
        k6 = connector_k6(dx, dy, axis=axis, OD=OD, t_wall=t_wall, E=E)
        d = [dof(ms, n1, 0), dof(ms, n1, 1), dof(ms, n1, 2),
             dof(ms, n2, 0), dof(ms, n2, 1), dof(ms, n2, 2)]
        K[np.ix_(d, d)] += k6
        Fint[d] += k6 @ U[d]
    return K, Fint

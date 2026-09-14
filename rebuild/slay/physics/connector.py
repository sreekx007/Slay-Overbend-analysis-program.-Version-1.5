"""slay.physics.connector -- the prescribed-stiffness connector element.

Pass 4's rule, and it is ABSOLUTE:

    every connector carries the stiffness of a 1 x OD length of pipeline,
    whatever the connector's own length is

so length never enters the stiffness. This module is where that becomes a
6x6, and it exists as its own element type because `nlfea_v4`'s corotational
beam cannot express the rule: it derives EA/L0 and EI/L0 from the node
coordinates and divides by the deformed length, so it is wrong for any
connector whose length is not OD and undefined for one whose length is zero.

ZERO LENGTH IS THE DEFAULT, NOT AN EDGE CASE. ILS-EASB's GD-SB sets
`P_vt = 0`, which puts its top chord on the pipe centreline, so every one of
its connectors has no length at all. A length-derived stiffness would be
undefined precisely where it is most needed; this one is not.

TWO FORMS, one rule. Which applies is decided by the geometry, not by a flag:

    L > 0    constitutive law at L0 = OD, KINEMATICS at the real length,
             in the 3-DOF corotational basis
    L = 0    a relative-DOF spring, because a beam's transverse stiffness is
             entirely a moment arm and there is none

Both are self-equilibrating by construction. The history of why that matters
is in `_corotational_k6`.

Layer: `physics`. It may not import the kernel -- `nlfea_v4` is declared
`solve` in `slay/_layers.py` -- and it does not need to: a prescribed
stiffness is prescribed.
"""

from __future__ import annotations

import math

import numpy as np

import config

# A connector is zero-length when the two ends are the same point. The
# tolerance is numerical, not physical: there is no such thing as a 1 nm
# connector, so anything this close is the degenerate case.
ZERO_LEN_TOL = 1e-9

# The connector's NOMINAL direction when it has no chord of its own to read:
# the component's local y, which is the direction `P_vt` measures and the
# direction a connector runs from the pipe to the structure. Both EA
# archetypes sit square to the pipe in the reference configuration, so local
# y is model y here. On the stinger arc it turns with the slope, which is the
# same co-rotating frame `S` and `D` need.
NOMINAL_AXIS = (0.0, 1.0)


def section_properties(OD: float = None, t_wall: float = None):
    """(A, I) of the pipeline section the rule refers to."""
    OD = config.OD_PIPE_DEF if OD is None else OD
    t_wall = config.T_WALL_DEF if t_wall is None else t_wall
    ID = OD - 2.0 * t_wall
    return (math.pi / 4.0 * (OD**2 - ID**2),
            math.pi / 64.0 * (OD**4 - ID**4))


def connector_k6(dx: float, dy: float, axis=NOMINAL_AXIS,
                 OD: float = None, t_wall: float = None,
                 E: float = None) -> np.ndarray:
    """The 6x6 of one connector, in global (s, y, rz) at both ends.

    `dx, dy` are the chord from the pipe-side node to the EA-side node. They
    supply ORIENTATION and LENGTH; they never supply stiffness.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    E = config.STEEL_E if E is None else E
    A, I = section_properties(OD, t_wall)
    if math.hypot(dx, dy) < ZERO_LEN_TOL:
        return _zero_length_k6(axis, E * A, E * I, OD)
    return _corotational_k6(dx, dy, E * A, E * I, OD)


def _corotational_k6(dx, dy, EA, EI, L0) -> np.ndarray:
    """A connector with length: 1 x OD stiffness, REAL geometry, in balance.

    THE FIRST VERSION OF THIS WAS WRONG and the error is worth keeping. It
    built the textbook beam matrix with L = OD throughout. A beam matrix is
    self-equilibrating only when the L in its terms is the L of its own
    geometry: a rigid rotation theta about end 1 moves end 2 by L_real*theta,
    while a matrix built at L_OD has zero force only for L_OD*theta. With
    L_real = 0.6096 and OD = 0.4064 the 0.2032*theta mismatch produced
    spurious shear, and ILS-EAST's connectors came out 146 kN.m short of
    moment equilibrium under F2.

    Nor can a section scale fix it, because a beam's terms scale differently
    with length -- matching EA/L and 4EI/L leaves 12EI/L^3 at 0.444x, and
    matching 12EI/L^3 leaves 4EI/L at 2.25x.

    THE FORM THAT WORKS separates the two. Constitutive law at L0 = OD, which
    is the rule; KINEMATICS at the real length, which is equilibrium. The
    3-DOF corotational local basis -- axial elongation and the two end
    rotations measured from the chord -- annihilates rigid-body motion by
    construction, so `T.T @ k @ T` is self-equilibrating whatever L is used
    inside `k`. It is the same basis `nlfea_v4.assemble` uses.

    What this costs, stated: the axial and rotational stiffnesses are those
    of a 1 x OD pipe exactly; the transverse stiffness follows from the real
    geometry, as it must for the element to be an element at all.
    """
    L_real = math.hypot(dx, dy)
    c, sn = dx / L_real, dy / L_real

    k = np.array([[EA / L0, 0.0, 0.0],
                  [0.0, 4 * EI / L0, 2 * EI / L0],
                  [0.0, 2 * EI / L0, 4 * EI / L0]])

    T = np.zeros((3, 6))
    T[0, 0] = -c;            T[0, 1] = -sn
    T[0, 3] = c;             T[0, 4] = sn
    T[1, 0] = -sn / L_real;  T[1, 1] = c / L_real;  T[1, 2] = 1.0
    T[1, 3] = sn / L_real;   T[1, 4] = -c / L_real
    T[2, 0] = -sn / L_real;  T[2, 1] = c / L_real;  T[2, 5] = 1.0
    T[2, 3] = sn / L_real;   T[2, 4] = -c / L_real
    return T.T @ k @ T


def _zero_length_k6(axis, EA, EI, L0) -> np.ndarray:
    """A connector whose two ends are the same point.

    A ZERO-LENGTH CONNECTOR IS NOT THE LIMIT OF A BEAM, and pretending it is
    is what makes this need a decision rather than a default. A beam's
    transverse stiffness is entirely a moment arm: a rigid rotation of a beam
    of length L moves its ends L*phi apart, so `Delta_transverse` is not a
    deformation of a beam at all, only `Delta_transverse - L*phi` is. Drive
    L to zero and the corotational basis divides by it -- the 1/L_real terms
    above -- because the mode it is measuring has ceased to exist.

    At L = 0 the arithmetic changes shape. A rigid rotation of two COINCIDENT
    nodes moves neither of them, so all three relative freedoms

        (Delta u_axial, Delta u_transverse, Delta rz)

    are genuine deformations, and the element is a relative-DOF spring:

        K = [[k, -k], [-k, k]]

    which annihilates both rigid-body modes by construction -- equal
    translation gives Delta u = 0, equal rotation gives Delta rz = 0 -- so it
    is self-equilibrating however k is chosen.

    WHICH THREE NUMBERS, and this is the judgement call, stated rather than
    buried. Pass 4's rule fixes the magnitude: the stiffness of a 1 x OD
    length of pipeline. A beam's three relative modes are coupled, so three
    independent numbers can only be had by taking each mode's own stiffness
    with the other two relative freedoms restrained:

        k_axial      = EA / L0            elongation
        k_transverse = 12 EI / L0^3       shear with no relative rotation
        k_rotation   = EI / L0            antisymmetric bending, chord fixed

    all at L0 = OD. The last is EI/L0 and NOT 4EI/L0: with both ends' ends
    held and a relative rotation phi imposed as (-phi/2, +phi/2), the strain
    energy is (EI/L0) phi^2 / 2, so the stiffness against phi is EI/L0.
    4EI/L0 is the stiffness against ONE end's rotation with the other held,
    which is not a relative mode.

    THE AXIS IS THE P_vt DIRECTION. `k_axial` and `k_transverse` differ by a
    factor of 1.35, so which global direction each acts in has to be said. A
    connector runs from the pipe to the structure -- the direction P_vt
    measures -- and P_vt = 0 means the structure sits ON the centreline, not
    that the connector points somewhere else. So the axis is the component's
    local y whatever P_vt's magnitude, and the zero-length case keeps the
    same axis convention as every other connector rather than inventing one.
    Its SIGN is irrelevant: the stiffness is even in the axis.
    """
    ax, ay = axis
    n = math.hypot(ax, ay)
    if n < ZERO_LEN_TOL:
        raise ValueError(
            'a zero-length connector needs a nominal axis: its chord has no '
            'direction, so nothing else says which way it acts')
    c, sn = ax / n, ay / n

    k_local = np.diag([EA / L0, 12 * EI / L0**3, EI / L0])
    R = np.array([[c, sn, 0.0],          # global -> local
                  [-sn, c, 0.0],
                  [0.0, 0.0, 1.0]])
    k = R.T @ k_local @ R

    K = np.zeros((6, 6))
    K[:3, :3] = k;   K[3:, 3:] = k
    K[:3, 3:] = -k;  K[3:, :3] = -k
    return K


def is_zero_length(dx: float, dy: float) -> bool:
    return math.hypot(dx, dy) < ZERO_LEN_TOL

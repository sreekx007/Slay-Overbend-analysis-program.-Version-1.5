"""slay.solve.penalty -- penalty-enforced multi-point constraints.

REGULARISATION IS THE SUBJECT, not magnitude. `nlfea_v4.apply_bcs_sparse`
sets `penalty = K.diagonal().max() * 1e8` -- scaled to the GLOBAL maximum. In
a frame matrix the translational and rotational diagonals differ by orders of
magnitude, so a global scale over-penalises the small ones and the condition
number carries the whole spread. Here each constraint is scaled to the LOCAL
diagonals it ties:

    k_pen = alpha * max(K[a, a], K[b, b], 1.0)

so conditioning grows with `alpha` alone.

ALPHA WAS MEASURED, NOT CHOSEN. Swept over decades on ILS-EAST F2 at 200 kN:
at 1e5 the displacement has converged to six figures, the constraint
violation is 4.8e-07 mm (half a nanometre), and cond(K) = 3.9e13 -- two
decades below what double precision can carry. Beyond it violation keeps
falling and buys nothing while conditioning runs away: 2.0e21 at 1e9, 2.0e27
at 1e12. G5's lesson is why that is recorded as a measurement: conditioning,
not magnitude, is what failed before.
"""

from __future__ import annotations

import numpy as np

# Chosen by sweep. See the module docstring; `tools/study_connectors.py
# --sweep` reproduces it.
ALPHA = 1e5


def apply_constraints(K, R, U, rows, dof_of, alpha=ALPHA):
    """Add penalty terms for each `(node_a, node_b, comp, target)` row.

    `dof_of(node_index, comp)` maps to a global DOF. Modifies `K` and `R` in
    place and returns the penalty stiffness used per row, which the active
    set needs to read a constraint force back out.
    """
    kps = []
    for (na, nb, comp, target) in rows:
        a, b = dof_of(na, comp), dof_of(nb, comp)
        kp = alpha * max(K[a, a], K[b, b], 1.0)
        K[a, a] += kp; K[b, b] += kp
        K[a, b] -= kp; K[b, a] -= kp
        g = (U[a] - U[b]) - target
        R[a] -= kp * g
        R[b] += kp * g
        kps.append(kp)
    return kps


def apply_fixed(K, R, U, dofs, alpha=ALPHA):
    """Penalty-enforced zero displacement, same convention as the MPCs."""
    if not dofs:
        return 0.0
    kf = alpha * max(K.diagonal().max(), 1.0)
    for d in dofs:
        K[d, d] += kf
        R[d] -= kf * U[d]
    return kf


def violation(U, rows, dof_of):
    """Worst |(u_a - u_b) - target| over the rows. The number that says
    whether the penalty was stiff enough, and the one a run reports."""
    return max((abs((U[dof_of(na, comp)] - U[dof_of(nb, comp)]) - target)
                for (na, nb, comp, target) in rows), default=0.0)


def condition_number(K, rows, dof_of, fixed=(), alpha=ALPHA):
    """cond(K) with the penalties applied. Dense and O(n^3) -- for measuring
    the regularisation tradeoff, not for a production run."""
    Kp = np.array(K, dtype=float, copy=True)
    R = np.zeros(Kp.shape[0])
    apply_constraints(Kp, R, np.zeros(Kp.shape[0]), rows, dof_of, alpha)
    apply_fixed(Kp, R, np.zeros(Kp.shape[0]), list(fixed), alpha)
    return np.linalg.cond(Kp)

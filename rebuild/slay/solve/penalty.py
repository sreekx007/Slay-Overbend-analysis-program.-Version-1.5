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


# ---------------------------------------------------------------------------
# general linear constraints -- what a contact slot needs
# ---------------------------------------------------------------------------
#
# A connector tie is one DOF against another, same component. A CONTACT slot
# is not: it constrains the NORMAL component of a displacement interpolated
# between two nodes, so it spans four DOF with mixed components and mixed
# signs,
#
#     sum_k c_k U[d_k] = target,    c = (w_lo*nx, w_lo*ny, w_hi*nx, w_hi*ny)
#
# and only that combination. The tangential direction is left free, which is
# the whole point: a material point slides 2.07 m over the rollers by SR6
# (R = 85), and a uy-only constraint fights that slide -- measured at ~2.4%
# spurious strain concentration against ~0.29% pure-arc bending.
#
# THE PENALTY SCALE IS GLOBAL HERE, not local-diagonal. "The local diagonal"
# has no single meaning for a constraint spanning four DOF of two different
# components; the validated formulation scales one `pen` off K's global
# maximum and the release threshold below is calibrated against it. Connector
# ties keep the local scaling measured in this module's docstring -- the two
# are different constraints, not an inconsistency.


def global_penalty(K, mult: float) -> float:
    """`max(diag(K)) * mult` -- the validated contact scaling."""
    return float(K.diagonal().max() if hasattr(K, 'diagonal')
                 else np.max(np.diag(K))) * mult


def apply_linear(K, R, U, dofs, coeffs, target, pen) -> float:
    """Add `pen` * (c.U - target)^2 / 2 as a rank-1 outer product.

    Returns the scalar residual `r = target - c.U`, which is what the active
    set reads: `pen * r` is the constraint force, and its SIGN is push versus
    pull. At convergence `r` itself is ~1e-10 m -- far too small for a gap
    threshold to mean anything, and the reason release is reaction-based.
    """
    r = target - float(sum(c * U[d] for c, d in zip(coeffs, dofs)))
    for j, (dj, cj) in enumerate(zip(dofs, coeffs)):
        if cj == 0.0:
            continue
        R[dj] += pen * cj * r
        for dk, ck in zip(dofs, coeffs):
            if ck != 0.0:
                K[dj, dk] += pen * cj * ck
    return r


def regularise(K, mult: float, scale: float) -> None:
    """Add `mult * scale` to every diagonal. The validated stabiliser --
    retained, off by default, and applied to the WHOLE diagonal rather than
    to the constrained rows, which is what makes it a regulariser rather than
    a second penalty."""
    if mult <= 0.0:
        return
    n = K.shape[0]
    K[range(n), range(n)] += mult * scale

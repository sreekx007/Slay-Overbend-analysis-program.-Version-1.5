"""slay.solve.newton -- incremental Newton with penalty MPCs and a deadband
active set.

This is the loop the EA studies were built around, in the package where the
rest of the pipeline can reach it. It is deliberately NOT `solve(problem)`:
`Problem` is T4's artifact and does not exist yet, so this takes a `Model`,
a load and a restraint set directly. T5 wraps it; it does not replace it.

TOLERANCE IS A FIXTURE, not a preference. Measured on the mesher rig: the
kernel's default 5e-4 UNDER-CONVERGES, 1e-5..1e-7 is a flat plateau, and
below that is unreachable -- `nlfea_v4.solve_step` halves the increment and
retries WITHOUT BOUND, raising nothing, so a 0.02 s solve ran 15 minutes
(L015). Every loop here is bounded and raises.

A PENALTY FORMULATION HAS ITS OWN FLOOR, and it is lower than the tolerance
the F-only cases reach. `k_pen` is ~1e15, so round-off in U at ~1e-2 m puts a
fraction of a newton into the residual that no further iteration can remove.
Measured on ILS-EAST F2D with both deadbands engaged: Newton converges
quadratically -- 2.3e-01, 4.9e-06, 4.3e-08 -- and then STAGNATES at 2.5e-09
for as many iterations as it is given.

So the loop converges on `tol` OR on stagnation below `STALL_BAND`, and it
records which. A fixed `tol` alone forces a choice between raising on a case
that is converged to machine limits and loosening until nothing is checked.
The study loops this replaces had neither: they ran 30 iterations and fell
out of the `for` with no `else`, so an engaged deadband silently exhausted
its iteration budget every time. The numbers were right -- stagnation at the
floor is still the answer -- but nothing said so.

THE ACTIVE SET IS AN OUTER LOOP. Each pass solves to convergence with a fixed
state, then re-decides. It settles in one flip on every case measured; the
bound exists so a case that does not settle says so instead of spinning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

from slay.physics.connector import NOMINAL_AXIS
from slay.solve import constraints as cons
from slay.solve import kernel as kern
from slay.solve import penalty as pen

MAX_ACTIVE_SET_PASSES = 12

# Default residual tolerance, as a fraction of the applied load. The
# F-and-W cases reach 1e-9; an engaged deadband floors at 2.5e-09, so the
# default sits a little above it and stagnation covers the rest.
TOL = 1e-8

# Stagnation is only ever ACCEPTED below this. Above it, a residual that has
# stopped improving is a failure to converge and says so.
STALL_BAND = 1e-6

# Two consecutive iterations that fail to improve the residual by this factor
STALL_RATIO = 0.5
STALL_STREAK = 2


@dataclass
class SolveResult:
    U: np.ndarray
    engaged: dict = field(default_factory=dict)
    violation: float = 0.0
    flips: int = 0
    passes: int = 0
    iterations: int = 0
    residual: float = 0.0        # worst increment's final residual
    stalled: bool = False        # any increment ended at the penalty floor

    @property
    def settled(self) -> bool:
        return self.passes < MAX_ACTIVE_SET_PASSES


def solve(model, ms, loads, fixed_dofs, *, ties_override=None,
          alpha=pen.ALPHA, n_increments=10, tol=TOL, max_iter=30,
          axis=NOMINAL_AXIS, scale=None, engaged=None):
    """Solve one model.

    `loads` maps a global DOF to its final applied value; `fixed_dofs` are
    penalty-restrained to zero. `scale` is the magnitude the residual is
    judged against -- the applied load, by default.

    `engaged` PINS the deadband state instead of letting the active set find
    it: one pass, no flips. It exists so a study can ask what a given state
    costs -- and so the active set's decisions can be tested against a state
    chosen by hand rather than only against itself.
    """
    ndof = 3 * model.n_nodes
    scale = max(abs(v) for v in loads.values()) if scale is None else scale
    scale = max(abs(scale), 1.0)

    def dof_of(node, comp):
        return kern.dof(ms, node, comp)

    pinned = engaged is not None
    engaged = dict(engaged) if pinned else {
        a.node_a: 0 for a in cons.deadband_associations(model)}
    result = SolveResult(U=np.zeros(ndof), engaged=dict(engaged))

    for _pass in range(MAX_ACTIVE_SET_PASSES):
        result.passes += 1
        rows = cons.constraint_rows(model, engaged, ties_override)
        U = np.zeros(ndof)
        for inc in range(1, n_increments + 1):
            lam = inc / n_increments
            prev, stalls, res = np.inf, 0, np.inf
            for _it in range(max_iter):
                K, Fint = kern.assemble(model, ms, U, axis=axis)
                R = -Fint
                for d, v in loads.items():
                    R[d] += v * lam
                pen.apply_constraints(K, R, U, rows, dof_of, alpha)
                pen.apply_fixed(K, R, U, list(fixed_dofs), alpha)
                res = np.max(np.abs(R)) / scale
                if res < tol:
                    break
                stalls = stalls + 1 if res > STALL_RATIO * prev else 0
                if res < STALL_BAND and stalls >= STALL_STREAK:
                    result.stalled = True      # at the penalty floor
                    break
                prev = res
                dU = spsolve(csr_matrix(K), R)
                if not np.all(np.isfinite(dU)):
                    raise RuntimeError(
                        'singular system: the solver returned a non-finite '
                        'increment. A Group B model with its associations '
                        'unapplied looks exactly like this.')
                U += dU
                result.iterations += 1
            else:
                raise RuntimeError(
                    f'increment {inc}/{n_increments} did not converge in '
                    f'{max_iter} iterations (residual {res:.3e} against '
                    f'{tol:.0e}, and it was still improving or above '
                    f'{STALL_BAND:.0e}). Bounded deliberately -- the kernel '
                    f'would halve and retry forever.')
            result.residual = max(result.residual, res)

        result.U = U
        if pinned or not engaged:
            break
        K, _Fint = kern.assemble(model, ms, U, axis=axis)
        new = cons.update_active_set(
            model, engaged,
            sep_of=lambda a: _separation(model, ms, a, U),
            force_of=lambda a, st: _constraint_force(model, ms, a, U, st,
                                                     K, alpha),
            P=scale)
        if new == engaged:
            break
        result.flips += 1
        engaged = new

    result.engaged = dict(engaged)
    result.violation = pen.violation(
        result.U, cons.constraint_rows(model, engaged, ties_override), dof_of)
    return result


def _separation(model, ms, assoc, U):
    idx = model._part_index
    return (U[kern.dof(ms, idx[assoc.node_a], 1)]
            - U[kern.dof(ms, idx[assoc.node_b], 1)])


def _constraint_force(model, ms, assoc, U, state, K, alpha):
    """The tie's action on the EA-side node, in the restrained direction.

    Read from the PENALTY FORCE rather than from the separation. At
    convergence the violation is ~1e-9 m while `kp` is ~1e15, so the product
    is the physical reaction in kN -- well conditioned, where the raw
    separation is not.
    """
    import math
    idx = model._part_index
    a = kern.dof(ms, idx[assoc.node_a], 1)
    b = kern.dof(ms, idx[assoc.node_b], 1)
    kp = alpha * max(K[a, a], K[b, b], 1.0)
    g = (U[a] - U[b]) - math.copysign(assoc.gap, state)
    return -kp * g

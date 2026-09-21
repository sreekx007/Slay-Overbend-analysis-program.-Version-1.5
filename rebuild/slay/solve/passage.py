"""slay.solve.passage -- `solve(problem, state_in) -> (Result, state_out)`.

The T5 entry point. It takes a `Problem` -- flat, inert, nothing live in it --
and returns a `Result` plus the state a chained next position needs.

PORTED FROM `_solve_state_sliding`, NOT from `_solve_state`. The node-snapped
path is retired: it constrains a single node's `uy` per roller, which fights
the 2.07 m of tangential slide a material point makes over the rollers by SR6
(R = 85) and was measured producing ~2.4% spurious strain concentration
against ~0.29% pure-arc bending. The sliding formulation constrains the
NORMAL component of an interpolated displacement and leaves the tangent free.

FOUR THINGS THE LOOP OWES ITS CALLER, and the old code had all four:

  ADAPTIVE CUTBACK. An increment that diverges is rolled back and retried at
  half the step, down to 1/64 of nominal, growing back by 1.4x on success.
  Exhausting it RETURNS A STATUS, it does not raise -- a sweep wants to know
  which position failed and carry on.

  DIVERGENCE DETECTION. NaN, |U| > 100 m, or a single increment |dU| > 1 m.
  Without it a diverging Newton wanders for its full iteration budget and
  returns a converged-looking answer built on nonsense.

  PLASTIC FREEZE AND COMMIT. The committed state is frozen for the duration
  of an increment's Newton iterations and only replaced when that increment
  SUCCEEDS. A cutback that discarded carried-forward plastic state would
  silently un-yield the pipe -- the v1.45 bug.

  THE ACTIVE SET BETWEEN ITERATIONS, not inside them. Each contact pass
  solves to convergence with a fixed set, then re-decides; at most 8 passes.

WHAT IT DOES NOT DO. It does not sweep. `Problem` is one position and
`state_out` is what the next one starts from; the loop over positions is the
study layer's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import spsolve

import nlfea_v4 as fe

from slay.solve import contact as ctc
from slay.solve import penalty as pen
from slay.solve.kernel import mesh_of_problem

# Penalty multiplier on K's global diagonal maximum. 1e8 is the validated
# value for a first (unchained) solve; a continued one uses less, because it
# starts near its target and an enormous penalty there only harms
# conditioning.
PEN_FIRST = 1e8
PEN_CHAINED = 1e4

N_INCREMENTS_FIRST = 40
N_INCREMENTS_CHAINED = 20

MAX_CONTACT_PASSES = 8
MAX_NEWTON = 30
NEWTON_TOL = 1e-3          # on max|residual| / max(max|Fint|, 1), DOF 3+

CUTBACK_FLOOR = 1.0 / 64.0
CUTBACK_GROWTH = 1.4

DIVERGENCE_U = 100.0       # m
DIVERGENCE_DU = 1.0        # m, in one Newton step


@dataclass
class SolveState:
    """What a chained next position needs, and nothing else."""
    U: np.ndarray = None
    theta: np.ndarray = None
    plastic: object = None
    active: tuple = ()


@dataclass
class Result:
    U: np.ndarray
    status: str = 'ok'
    active: tuple = ()
    released: tuple = ()
    increments: int = 0
    iterations: int = 0
    cutbacks: int = 0
    contact_passes: int = 0
    residual: float = 0.0
    strains: tuple = ()        # (element index, s_mid, eps_max)
    runner: object = field(default=None, repr=False)

    @property
    def converged(self) -> bool:
        return self.status == 'ok'

    def peak_strain(self, s_min: float = None) -> tuple:
        """(s, eps) of the worst element, optionally only for s >= s_min.

        The zone matters. The reference metric is a PHASE-1 peak -- the worst
        element from SR3 down the stinger -- not the whole model's, because
        the deck end carries a restraint artefact that is a property of where
        the model was cut.
        """
        rows = [(s, e) for (_i, s, e) in self.strains
                if s_min is None or s >= s_min]
        if not rows:
            return (0.0, 0.0)
        return max(rows, key=lambda r: r[1])


def solve(problem, state_in: SolveState = None, *,
          pen_mult: float = None, n_increments: int = None,
          reg_mult: float = 0.0, n_points_polar: int = 8,
          n_fibres: int = 20, polar: bool = True,
          verbose: bool = False):
    """Solve one lay position. Returns `(Result, state_out)`."""
    chained = state_in is not None
    pen_mult = (PEN_CHAINED if chained else PEN_FIRST) \
        if pen_mult is None else pen_mult
    n_increments = (N_INCREMENTS_CHAINED if chained else N_INCREMENTS_FIRST) \
        if n_increments is None else n_increments

    ms, mdl, index_of = mesh_of_problem(
        problem, n_points_polar=n_points_polar, n_fibres=n_fibres,
        polar=polar)
    ndof = ms.n_dofs

    slots = ctc.slots_from_targets(problem.contacts, ms)
    anchor_dofs = _anchor_dofs(problem, ms)
    dist, joint = _loads(problem, ms, index_of)

    U = np.zeros(ndof) if state_in is None or state_in.U is None \
        else state_in.U.copy()
    th = np.full(ms.n_elems, np.nan) if state_in is None \
        or state_in.theta is None else state_in.theta.copy()
    ps = _plastic_state(ms, problem, state_in,
                        n_points_polar if polar else n_fibres)
    active = list(state_in.active) if chained and state_in.active \
        else [True] * len(slots)

    # The targets ramp FROM where the pipe already is, not from zero. For a
    # fresh solve that is the plain ramp; for a chained one it makes the
    # increment a real increment rather than a re-application.
    anchors = [s.u_out(U) for s in slots]

    res = Result(U=U, active=tuple(active))
    lam_done, dlam = 0.0, 1.0 / n_increments
    dlam_min = dlam * CUTBACK_FLOOR
    rc = 0.0

    while lam_done < 1.0 - 1e-12:
        lam = min(1.0, lam_done + dlam)
        U_snap, th_snap = U.copy(), th.copy()
        ps_snap = ps.copy() if ps is not None else None
        active_snap = list(active)
        ps_inc_start = ps.copy() if ps is not None else None
        ps_trial = ps_inc_start
        released, failed = set(), False

        for _cpass in range(MAX_CONTACT_PASSES):
            res.contact_passes += 1
            for it in range(MAX_NEWTON):
                K, Fint, Fext, th, ps_trial = fe.assemble(
                    ms, U, th, dist, joint, lam, plastic_state=ps_inc_start)
                p_scale = float(K.diagonal().max())
                p_val = p_scale * pen_mult
                Kl = lil_matrix(K)
                R = Fext - Fint

                for d in anchor_dofs:
                    Kl[d, d] += p_val
                    R[d] += p_val * (0.0 - U[d])
                for i, slot in enumerate(slots):
                    if not active[i]:
                        continue
                    te = ctc.incremental_target(slot, anchors[i], lam)
                    pen.apply_linear(Kl, R, U, slot.dofs, slot.coeffs, te,
                                     p_val)

                Ks = Kl.tocsr()
                if reg_mult > 0.0:
                    Ks.setdiag(Ks.diagonal() + reg_mult * p_scale)
                dU = spsolve(Ks, R)
                fm = max(float(np.max(np.abs(Fint))), 1.0)
                rc = float(np.max(np.abs(R[3:]))) / fm
                U += dU
                res.iterations += 1
                if (np.isnan(U).any()
                        or np.max(np.abs(U)) > DIVERGENCE_U
                        or float(np.max(np.abs(dU))) > DIVERGENCE_DU):
                    failed = True
                    break
                if it > 0 and rc < NEWTON_TOL:
                    break
            if failed:
                break
            active, changed = ctc.update_active_set(
                slots, active, released, U, p_val, anchors, lam)
            if not changed:
                break

        if failed:
            U, th = U_snap, th_snap
            ps, active = ps_snap, active_snap
            dlam *= 0.5
            res.cutbacks += 1
            if dlam < dlam_min:
                res.status = f'CUTBACK EXHAUSTED at lam={lam_done:.4f}'
                res.U, res.residual = U, rc
                res.active = tuple(active)
                return res, SolveState(U=U, theta=th, plastic=ps,
                                       active=tuple(active))
            if verbose:
                print(f'  cutback -> dlam={dlam:.3e}')
            continue

        ps = ps_trial
        lam_done = lam
        res.increments += 1
        dlam = min(1.0 / n_increments, dlam * CUTBACK_GROWTH)

    res.U, res.residual = U, rc
    res.active, res.released = tuple(active), tuple(sorted(released))
    res.strains, res.runner = _strains(problem, ms, mdl, U, ps, index_of)
    return res, SolveState(U=U, theta=th, plastic=ps, active=tuple(active))


# ---------------------------------------------------------------------------
# problem -> kernel inputs
# ---------------------------------------------------------------------------

def _anchor_dofs(problem, ms):
    from slay.solve.kernel import dof
    out = []
    for r in problem.restraints:
        for comp in r.components:
            out.append(dof(ms, r.node, comp))
    return out


def _loads(problem, ms, index_of):
    """Nodal loads, as the kernel's `assemble` actually reads them.

    It indexes `jl[0..3]` and uses `jl[0]` directly as `3*ni`, so a joint
    load is a TUPLE of `(mesh node index, Fx, Fy, Mz)` -- not the
    `JointLoad` dataclass of the same name, and not one of OUR node indices.
    The map is a permutation (L009), so the conversion is mandatory.

    Self weight arrives here already lumped to nodes by T4, so it is a joint
    load too. The kernel's distributed-load path would re-derive the weight
    from its own section and silently disagree with the sections T4
    resolved -- including the `section_at` ones it has no way to know about.
    """
    joint = [(int(ms.user_node_to_mesh[v.node]), v.fx, v.fy, v.mz)
             for v in problem.loads]
    return {}, joint


def _plastic_state(ms, problem, state_in, n_fib):
    """The fibre count is a SOLVER input, not a mesh property.

    `n_points_polar` under the B31-equivalent angular scheme,
    `n_fibres` under Cartesian through-wall integration -- the
    reference calls it `n_fib_active` for exactly that reason.
    Reading it off the mesh would have to guess which scheme
    produced it.
    """
    from slay.data.materials import J2Material
    if not isinstance(problem.material, J2Material):
        return None
    ps = fe.PlasticState(ms.n_elems, n_fib)
    if state_in is not None and state_in.plastic is not None:
        old = state_in.plastic
        if old.n_elems == ms.n_elems and old.n_fibres == n_fib:
            ps.eps_p[:] = old.eps_p
            ps.kap[:] = old.kap
    return ps


def _strains(problem, ms, mdl, U, ps, index_of):
    """(element index, s at the midpoint, eps_max) per element, plus the
    runner the kernel needs to produce them."""
    r = fe.FEARunner(mdl)
    r.U = U.copy()
    r.U_steps = [U.copy()]
    r.results = [[{'lambda': 1.0, 'iterations': 0, 'residual': 0.0,
                   'U': U.copy()}]]
    r.plastic_state = ps
    s_of = {i: s for (i, s, _y) in problem.nodes}
    rows = []
    for (idx, n1, n2, _owner, _line) in problem.elements:
        eid = index_of[idx]
        try:
            st = r.get_element_strains(eid)
        except Exception:
            continue
        rows.append((idx, 0.5 * (s_of[n1] + s_of[n2]), float(st['eps_max'])))
    return tuple(rows), r

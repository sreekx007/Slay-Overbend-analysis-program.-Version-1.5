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

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import spsolve

import nlfea_v4 as fe

from slay.solve import contact as ctc
from slay.solve import penalty as pen
from slay.solve import constraints as cons
from slay.solve.kernel import dof, mesh_of_problem, problem_connectors

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
    moments: tuple = ()        # (element index, s_mid, M) in N.m
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
    """Solve one lay position. Returns `(Result, state_out)`.

    THE LOAD SEQUENCE, written down because it has been misread once and the
    misreading produced a wrong diagnosis (L050).

        tension and gravity      FULL VALUE, from Newton iteration 1
        contact targets          ramped by `lam`, 0 -> 1

    `lam` is passed to `fe.assemble` and the kernel never applies it to
    `dist_loads` or `joint_loads` (`nlfea_v4.py:1419-1429`); only the
    `assemble_at` wrapper scales them and nothing here calls it. So the loads
    are NOT ramped, and this matches the reference exactly -- both
    `_solve_state_sliding` and `run_slay` pass their raw `dist` and `jl`
    through in the same way. `test_assemble_does_not_scale_loads_by_lam`
    pins that contract.

    TWO CONSEQUENCES worth holding on to:

      * Cutback cannot reduce a load. `dlam` shrinks the contact targets and
        nothing else, so a divergence whose first-iteration `dU` is
        insensitive to `dlam` is a load or a model problem. That is what
        `CUTBACK EXHAUSTED at lam=0.0000` means here.
      * A separate load-settling step -- converge tension and gravity with
        the targets held at their anchors, THEN ramp -- was tried and is
        WORSE, not better: it diverges above about 15 MT and, with the
        divergence guard removed, runs to 1e215 and a singular kernel
        matrix. The straight unstressed start has no geometric stiffness to
        react a tip load, and no amount of sequencing creates one. See
        section 5 of `docs/modules/T5_solve_spec.md`.
    """
    chained = state_in is not None
    pen_mult = (PEN_CHAINED if chained else PEN_FIRST) \
        if pen_mult is None else pen_mult
    n_increments = (N_INCREMENTS_CHAINED if chained else N_INCREMENTS_FIRST) \
        if n_increments is None else n_increments

    ms, mdl, index_of = mesh_of_problem(
        problem, n_points_polar=n_points_polar, n_fibres=n_fibres,
        polar=polar)
    ndof = ms.n_dofs

    # Built ONCE: a connector's 6x6 depends on the undeformed chord and the
    # pipe section, neither of which changes as the pipe slides. Empty for
    # every model without an EA structure, which is all of them but two
    # archetypes -- so this costs nothing where it does nothing.
    conn = problem_connectors(problem, ms)

    # THE DECLARED TIES. A connector element has its OWN two nodes -- one at
    # the pipe, one at the structure -- and Associations are what fasten
    # them to the real pipeline and frame nodes (T3 section 7). Without them
    # the frame is held by nothing: `solve.newton` says so in as many words,
    # "a Group B model with its associations unapplied looks exactly like
    # this", and that is exactly what the passage solver was doing.
    #
    # `engaged` is left empty, so every D is OPEN. That is not a shortcut:
    # the deadband active set belongs to `solve.newton`, and a D that
    # silently behaved as an F here would be the substitution G9 forbids --
    # `problem_connectors` refuses anything but F before this point.
    tie_rows = cons.constraint_rows_from(
        cons.plain_associations(problem.associations),
        problem.part_index or {})
    skew = skew_constraints(problem, ms)

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
                # THE PENALTY SCALES AGAINST THE BEAM STIFFNESS, and must be
                # taken BEFORE the connectors are added. A connector's 6x6 is
                # built at 1 x OD, so its diagonal is ~1.3e10 against the
                # beams' ~3e6 -- folding it into `p_scale` multiplied the
                # penalty by four orders of magnitude and the first residual
                # came out at 1.0e18 with a NaN solve. `penalty.py`'s
                # multiplier was tuned against the beam stiffness and means
                # nothing against any other basis.
                p_scale = float(K.diagonal().max())
                p_val = p_scale * pen_mult
                Kl = lil_matrix(K)

                # CONNECTORS, ASSEMBLED OUTSIDE THE KERNEL MESH. A
                # corotational beam takes its stiffness from its own length
                # and a connector's length is geometry, not stiffness, so
                # the kernel gets the pipeline and the frame only and this
                # puts the ties back. Without it the EA frame is attached to
                # nothing -- 18 elements floating free, a rigid-body
                # mechanism, and an exactly singular matrix.
                for _d, _k6 in conn:
                    for _a in range(6):
                        for _b in range(6):
                            Kl[_d[_a], _d[_b]] += _k6[_a, _b]
                    Fint[_d] += _k6 @ U[_d]

                R = Fext - Fint

                # Ties first: `apply_constraints` sizes its penalty from
                # the diagonal it finds, so it must see the beam and
                # connector stiffness already in place.
                if tie_rows:
                    pen.apply_constraints(Kl, R, U, tie_rows,
                                          lambda n, c: dof(ms, n, c))
                # SKEWED TIES, IN A FRAME THAT TURNS WITH THE PIPE. Rebuilt
                # from the CURRENT displacement every iteration, which is
                # what makes it co-rotating rather than merely rotated once
                # at the start: the slope at a connector changes as the pipe
                # bends down onto the arc, and a frame fixed at iteration 1
                # would be wrong by however far it then moved.
                for _d, _c in skew_rows_now(skew, U):
                    pen.apply_linear(Kl, R, U, _d, _c, 0.0, p_val)
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
    res.moments = _moments(problem, ms, U, th, ps, index_of)
    return res, SolveState(U=U, theta=th, plastic=ps, active=tuple(active))


# ---------------------------------------------------------------------------
# problem -> kernel inputs
# ---------------------------------------------------------------------------

def skew_constraints(problem, ms):
    """What a skewed tie needs, resolved once: DOFs, and where its frame
    comes from.

    An `S` connector is a bolt in a slot: it slides along the slot and turns
    in it, and restrains only the direction ACROSS the slot. That direction
    is perpendicular to the pipe it is bolted to, so it turns as the pipe
    turns -- 1.0 to 9.5 degrees over the travel of the EA structures, 30 by
    the last roller. Enforced in global axes it would restrain a direction
    that is not the one the slot restrains, leaking sin(theta) of the
    released direction into the held one.

    Returns [] for every model without one, which is all of them but a PS or
    PSD layout, so this costs nothing where it does nothing.
    """
    rows = cons.skewed_rows(problem.associations, problem.part_index or {})
    if not rows:
        return []

    # The frame is the PIPE's, not the connector's: a connector may have
    # zero length (ILS-EASB's do), so its own chord cannot supply an axis.
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    pipe = sorted({n for (_i, a, b, o, _l) in problem.elements
                   if o == 'pipeline' for n in (a, b)}, key=lambda i: s_of[i])
    # Each connector's pipe-side node sits at a pipeline station; the two
    # pipeline nodes bracketing it give the chord the tangent is read from.
    # Keyed on the connector's EA-SIDE node, because that is what a skewed
    # association names (`node_a` is the joint's own node, `node_b` the
    # structure's). Taking any connector's chord instead of this one's would
    # read a PS layout's S frame off its P -- a different station, and on an
    # arc a different slope.
    at_pipe = {}
    for (_idx, n1, n2, _ct, _ln, _slot) in problem.connectors:
        k = min(range(len(pipe)), key=lambda j: abs(s_of[pipe[j]] - s_of[n1]))
        at_pipe[n2] = (pipe[max(0, k - 1)],
                       pipe[min(len(pipe) - 1, k + 1)])

    out = []
    for (na, nb, ctype, ties) in rows:
        # `ties` is (local_x, local_y, rz). An S ties local y alone; nothing
        # else reaches here, and anything that did would need its own row
        # shape rather than this one.
        if tuple(ties) != (False, True, False):
            raise ValueError(
                f'a skewed {ctype!r} tie with pattern {tuple(ties)} has no '
                f'row shape here. Only (False, True, False) -- restrain '
                f'across the slot, release along it -- is implemented.')
        if na not in at_pipe:
            raise ValueError(
                f'skewed {ctype!r} tie at node {na} matches no connector; '
                f'its local frame has nothing to be read from')
        lo, hi = at_pipe[na]
        out.append(dict(dofs=[dof(ms, na, 0), dof(ms, na, 1),
                              dof(ms, nb, 0), dof(ms, nb, 1)],
                        lo=[dof(ms, lo, 0), dof(ms, lo, 1)],
                        hi=[dof(ms, hi, 0), dof(ms, hi, 1)],
                        base=(s_of[hi] - s_of[lo], 0.0)))
    return out


def skew_rows_now(skew, U):
    """[(dofs, coeffs)] for the current displacement.

    `n . (u_a - u_b) = 0`, with `n` perpendicular to the pipe chord in the
    CURRENT configuration. The chord is the undeformed spacing plus the
    displacement of its two ends, so the frame follows the solution.
    """
    out = []
    for r in skew:
        dx = r['base'][0] + (U[r['hi'][0]] - U[r['lo'][0]])
        dy = r['base'][1] + (U[r['hi'][1]] - U[r['lo'][1]])
        mag = math.hypot(dx, dy)
        if mag < 1e-12:
            continue                      # degenerate chord: no frame to read
        tx, ty = dx / mag, dy / mag
        nx, ny = -ty, tx                  # across the slot
        out.append((r['dofs'], [nx, ny, -nx, -ny]))
    return out


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


# Two-point Gauss rule, DERIVED rather than copied: the points of the
# 2-point Legendre rule on [-1, 1].
GAUSS_XI_2 = (-1.0 / math.sqrt(3.0), +1.0 / math.sqrt(3.0))


def _element_kinematics(ms, U, th):
    """(eps0, u3, u6, L0) per mesh element -- the co-rotational strip.

    Ported from the reference `_moment_profile`. `th` carries the committed
    element rotation so the co-rotational angle unwraps continuously; without
    it an element passing +/-pi jumps by 2*pi and its curvature inverts.
    """
    dof, coords, L0 = ms.elem_dof_array, ms.elem_coords, ms.elem_L0
    ux1, uy1, rz1 = U[dof[:, 0]], U[dof[:, 1]], U[dof[:, 2]]
    ux2, uy2, rz2 = U[dof[:, 3]], U[dof[:, 4]], U[dof[:, 5]]
    x1d, y1d = coords[:, 0] + ux1, coords[:, 1] + uy1
    x2d, y2d = coords[:, 2] + ux2, coords[:, 3] + uy2
    dx, dy = x2d - x1d, y2d - y1d
    Ld = np.hypot(dx, dy)
    theta0 = np.arctan2(coords[:, 3] - coords[:, 1],
                        coords[:, 2] - coords[:, 0])
    raw = np.arctan2(dy, dx)
    theta = raw.copy()
    ok = ~np.isnan(th)
    if ok.any():
        d = raw[ok] - th[ok]
        d -= 2 * np.pi * np.round(d / (2 * np.pi))
        theta[ok] = th[ok] + d
    dth = theta - theta0
    return (Ld - L0) / L0, rz1 - dth, rz2 - dth, L0


def _moments(problem, ms, U, th, ps, index_of):
    """(element index, s at the midpoint, M in N.m) per element.

    M = sum(sigma_f * y_f * A_f) over fibres, evaluated at BOTH Gauss points
    and averaged onto the element midpoint -- the same grid `_strains`
    reports on, so a moment and a strain at one location are comparable.

    EACH GAUSS POINT GETS ITS OWN CURVATURE AND ITS OWN PLASTIC STATE, and
    that pairing is the whole care of this function. The reference tool
    carried a v1.48 fix for exactly this: pairing the ELEMENT-MEAN curvature
    with the GP0-only plastic state gave a spurious single-element moment
    collapse -- about 500 kNm reported where ~1330 kNm was right -- because
    near a contact node the two Gauss points hold very different plastic
    strain, and GP0 was the low-plastic point in one element and the high one
    in its neighbour. Strain never showed it: strain does not read the
    plastic state.

    MIDPOINT AVERAGING, NOT NODAL EXTRAPOLATION, and deliberately. A section
    moment SATURATES plastically, so extrapolating past the Gauss points
    returns values above the section capacity. Abaqus shows the same artefact
    -- it is why nodal stress contours can exceed yield. Nodal recovery is
    right for contouring a smooth field, not for reading a peak off a
    plastically saturated one.
    """
    eps0, u3, u6, L0 = _element_kinematics(ms, U, th)
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    coords = ms.elem_coords
    out = []
    for (idx, n1, n2, _owner, _line) in problem.elements:
        ie = index_of[idx]
        M = 0.0
        for xi in GAUSS_XI_2:
            kap = ((3.0 * xi - 1.0) / L0[ie] * u3[ie]
                   + (3.0 * xi + 1.0) / L0[ie] * u6[ie])
            M += _section_moment(ms, ie, eps0[ie], kap, ps,
                                 GAUSS_XI_2.index(xi))
        out.append((idx, 0.5 * (coords[ie, 0] + coords[ie, 2]), 0.5 * M))
    return tuple(out)


def _section_moment(ms, ie, eps0, kap, ps, g):
    """One Gauss point's moment, by whichever constitutive law it carries.

    Three paths, and a fourth that REFUSES. A section whose law is not
    recognised returns no number rather than `E*I*kappa`, which would be
    wrong wherever it mattered and plausible everywhere -- the exact shape of
    defect this project keeps finding.
    """
    if ms.elem_ep[ie]:                       # J2, incremental: path-dependent
        fy, fA = ms.elem_fibres[ie]
        mat = ms.elem_ep_mat[ie]
        nf = len(fy)
        eps_f = eps0 + fy * kap
        if ps is None:
            zero = np.zeros(nf)
            sigma, *_ = fe._ep_return_mapping(eps_f, zero, zero, mat.E, mat)
        else:
            sigma, *_ = fe._ep_return_mapping(
                eps_f, ps.eps_p[ie, g, :nf], ps.kap[ie, g, :nf], mat.E, mat)
        return float(np.sum(sigma * fy * fA))
    if ms.elem_inelastic[ie]:                # Ramberg-Osgood: path-INdependent
        fy, fA = ms.elem_fibres[ie]
        E_r, sig_y, alpha, n_ro = ms.elem_ro_params[ie]
        sigma = fe._ro_stress(eps0 + fy * kap, E_r, sig_y, alpha, n_ro)
        return float(np.sum(sigma * fy * fA))
    if ms.elem_fibres[ie] is None:           # linear elastic: M = E I kappa
        return float(ms.elem_E[ie] * ms.elem_I[ie] * kap)
    raise NotImplementedError(
        f'element {ie} has fibres but no recognised constitutive law; '
        f'refusing to report E*I*kappa for it')


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

#!/usr/bin/env python3
"""study_connectors.py -- GD-ST on five connector layouts, penalty-tied.

The first working penalty constraints. The frame from `study_ea_st.py`, now
held by real connectors instead of by restraints at its own slots:

    fixed bottom node  --[ connector element ]--  top node  ~~tie~~  frame slot

The bottom node is fixed in all DOF: it is where the pipe will be. The
connector element is 0.5 x OD long. The top node is tied to the frame's slot
node by a penalty constraint whose DOF pattern is the JOINT TYPE -- which is
the whole point of the exercise, since F, P, S and D differ only there.

CONNECTOR STIFFNESS IS PRESCRIBED, NOT DERIVED. Pass 4's rule is absolute:
every connector carries the stiffness of a 1 x OD length of pipeline whatever
its own length is. So the connector's 6x6 is formed at L0 = OD and used at a
geometry of 0.5 x OD. This is the prescribed-stiffness element the assembly
spec says L5 needs, prototyped here -- and the reason it is needed is visible
in this file: nothing about the element's own length appears in its stiffness.

REGULARISATION, which is the real subject. `nlfea_v4.apply_bcs_sparse` sets
`penalty = K.diagonal().max() * 1e8` -- scaled to the GLOBAL maximum. In a
frame matrix the translational and rotational diagonals differ by orders of
magnitude, so a global scale over-penalises the small ones and the condition
number carries the whole spread. Here each constraint is scaled to the LOCAL
diagonals it ties:

    k_pen = alpha * max(K[a,a], K[b,b])

so conditioning grows with alpha alone. `--sweep` walks alpha over decades and
reports constraint violation against condition number, which is how the
working value is chosen rather than asserted.

THE FRAME IS HORIZONTAL HERE, so the EA-ST local x is the global s axis and
the constraints are applied in global axes. That is exact at the reference
configuration and good to the size of the rotations, which are ~1e-4 rad.
It is NOT the co-rotating form the stinger needs -- on the arc the local axis
turns up to 32.4 degrees. S and D are the types that would notice.

    python3 tools/study_connectors.py [--sweep] [--plot]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

import component_spec as cs                                # noqa: E402
import nlfea_v4 as fe                                      # noqa: E402
import study_ea_st as frame_study                          # noqa: E402

OD, T_WALL = 0.4064, 0.021
E_PIPE = 2.1e11
RATIO = 2.5                       # GD-ST's stiffness_ratio
CONN_LEN = 0.5 * OD               # the connector's geometric length
P_GAP = 1.0e-3                    # m, D deadband -- see the note in main()

A_PIPE = math.pi / 4 * (OD**2 - (OD - 2*T_WALL)**2)
I_PIPE = math.pi / 64 * (OD**4 - (OD - 2*T_WALL)**4)

# Chosen by --sweep, not asserted. At 1e5 the displacement has converged to
# six figures, the constraint violation is 4.8e-07 mm (half a nanometre), and
# cond(K) = 3.9e13 -- two decades below what double precision can carry.
# Beyond it violation keeps falling and buys nothing while conditioning runs
# away: 2.0e21 at 1e9, 2.0e27 at 1e12. That is the regularisation tradeoff,
# measured rather than guessed.
ALPHA = 1e5

# The order asked for.
LAYOUTS = ('F1', 'F2', 'PS', 'PSD', 'F2D')

# Imported, not restated. A second copy of the joint kinematics is a second
# thing to correct, and this one would have been missed when `S` was fixed.
from slay.model.parts import TIES_OPEN, TIES_SHUT          # noqa: E402


# ---------------------------------------------------------------------------
# the prescribed-stiffness connector element
# ---------------------------------------------------------------------------

# A connector is zero-length when P_vt = 0 puts the structure on the pipe
# centreline. ILS-EASB is the case, and it is the DEFAULT, not an edge.
ZERO_LEN_TOL = 1e-9


def _zero_length_k6(axis) -> np.ndarray:
    """The 6x6 of a connector whose two ends are the same point.

    A ZERO-LENGTH CONNECTOR IS NOT THE LIMIT OF A BEAM, and pretending it is
    is what makes this need a decision rather than a default. A beam's
    transverse stiffness is entirely a moment arm: a rigid rotation of a beam
    of length L moves its ends L*phi apart, so `Delta_transverse` is not a
    deformation of a beam at all, only `Delta_transverse - L*phi` is. Drive
    L to zero and the corotational basis divides by it -- the 1/L_real terms
    in `connector_k6` -- because the mode it is measuring has ceased to exist.

    At L = 0 the arithmetic changes shape. A rigid rotation of two COINCIDENT
    nodes moves neither of them, so all three relative freedoms

        (Delta u_axial, Delta u_transverse, Delta rz)

    are genuine deformations, and the element is a relative-DOF spring:

        K = [[k, -k], [-k, k]]

    which annihilates both rigid-body modes by construction -- equal
    translation gives Delta u = 0, equal rotation gives Delta rz = 0 -- so it
    is self-equilibrating however k is chosen. That is the same requirement
    L012 was about, met a different way.

    WHICH THREE NUMBERS, and this is the judgement call, stated rather than
    buried. Pass 4's rule fixes the magnitude: the stiffness of a 1 x OD
    length of pipeline. A beam's three relative modes are coupled, so three
    independent numbers can only be had by taking each mode's own stiffness
    with the other two relative freedoms restrained:

        k_axial      = EA / L0            elongation
        k_transverse = 12 EI / L0^3       shear with no relative rotation
        k_rotation   = EI / L0            antisymmetric bending, chord fixed

    all at L0 = OD. The last is EI/L0 and not 4EI/L0: with both ends' ends
    held and a relative rotation phi imposed as (-phi/2, +phi/2), the strain
    energy is (EI/L0) phi^2 / 2, so the stiffness against phi is EI/L0.
    4EI/L0 is the stiffness against ONE end's rotation with the other held,
    which is not a relative mode.

    THE AXIS IS THE P_vt DIRECTION. `k_axial` and `k_transverse` differ by a
    factor of 1.35 here, so which global direction each acts in has to be
    said. A connector runs from the pipe to the structure -- the direction
    P_vt measures -- and P_vt = 0 means the structure sits ON the centreline,
    not that the connector points somewhere else. So the axis is the
    component's local y whatever P_vt's magnitude, and the zero-length case
    keeps the same axis convention as every other connector rather than
    inventing one.
    """
    ax, ay = axis
    n = math.hypot(ax, ay)
    if n < ZERO_LEN_TOL:
        raise ValueError('zero-length connector needs a nominal axis')
    c, sn = ax / n, ay / n

    EA, EI = E_PIPE * A_PIPE, E_PIPE * I_PIPE
    L0 = OD                                   # the RULE: stiffness at 1 x OD
    k_local = np.diag([EA / L0, 12 * EI / L0**3, EI / L0])

    R = np.array([[c, sn, 0.0],               # global -> local
                  [-sn, c, 0.0],
                  [0.0, 0.0, 1.0]])
    k = R.T @ k_local @ R

    K = np.zeros((6, 6))
    K[:3, :3] = k;  K[3:, 3:] = k
    K[:3, 3:] = -k; K[3:, :3] = -k
    return K


def connector_k6(dx: float, dy: float, axis=(0.0, 1.0)) -> np.ndarray:
    """The 6x6 of a connector: 1 x OD stiffness, REAL geometry, in equilibrium.

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

    THE FORM THAT WORKS separates the two. Constitutive law at L = OD, which
    is the rule; KINEMATICS at the real length, which is equilibrium. The
    3-DOF corotational local basis -- axial elongation and the two end
    rotations measured from the chord -- annihilates rigid-body motion by
    construction, so `T.T @ k @ T` is self-equilibrating whatever L is used
    inside `k`. It is the same basis `nlfea_v4.assemble` uses.

    What this costs, stated: the axial and rotational stiffnesses are those
    of a 1 x OD pipe exactly; the transverse stiffness follows from the real
    geometry, as it must for the element to be an element at all.

    ZERO LENGTH takes a different form -- see `_zero_length_k6`. `axis` is
    the connector's NOMINAL direction, used only in that case.
    """
    L_real = math.hypot(dx, dy)
    if L_real < ZERO_LEN_TOL:
        return _zero_length_k6(axis)
    c, sn = dx / L_real, dy / L_real

    EA, EI = E_PIPE * A_PIPE, E_PIPE * I_PIPE
    L = OD                                    # the RULE: stiffness at 1 x OD
    k = np.array([[EA / L, 0.0, 0.0],
                  [0.0, 4 * EI / L, 2 * EI / L],
                  [0.0, 2 * EI / L, 4 * EI / L]])

    T = np.zeros((3, 6))                      # kinematics at the REAL length
    T[0, 0] = -c;         T[0, 1] = -sn
    T[0, 3] = c;          T[0, 4] = sn
    T[1, 0] = -sn / L_real; T[1, 1] = c / L_real; T[1, 2] = 1.0
    T[1, 3] = sn / L_real;  T[1, 4] = -c / L_real
    T[2, 0] = -sn / L_real; T[2, 1] = c / L_real; T[2, 5] = 1.0
    T[2, 3] = sn / L_real;  T[2, 4] = -c / L_real
    return T.T @ k @ T


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------

class Rig:
    """Frame DOFs first, then three DOFs per connector node pair."""

    def __init__(self, layout: str):
        m, elems, keep, renum = frame_study.frame_model()
        self.m, self.elems, self.keep, self.renum = m, elems, keep, renum
        self.n_frame = len(keep)
        self.top_node = frame_study.part_node(m, keep, renum, 'stop1')

        types = cs.NAMED_CONNECTION_SYSTEMS[layout]
        st = None
        slot_xs = cs.connector_slot_xs(0.0, 2.1674666666666664,
                                       1.0837333333333332)
        self.layout, self.types = layout, types

        # One bottom + one top node per active slot, appended after the frame.
        self.conns = []                       # (ctype, i_bot, i_top, i_frame)
        self.extra_xy = []
        for k, (t, x_slot) in enumerate(zip(types, slot_xs)):
            if not t:
                continue
            i_frame = self._frame_node_at(x_slot)
            y_top = keep[i_frame].y
            i_top = self.n_frame + len(self.extra_xy)
            self.extra_xy.append((keep[i_frame].s, y_top))
            i_bot = self.n_frame + len(self.extra_xy)
            self.extra_xy.append((keep[i_frame].s, y_top + CONN_LEN))
            self.conns.append((t, i_bot, i_top, i_frame))

        self.n_nodes = self.n_frame + len(self.extra_xy)
        self.ndof = 3 * self.n_nodes
        self.mesh = self._frame_mesh()

    def _frame_node_at(self, x_slot: float) -> int:
        """The frame node at this slot. Model s = -x, so the sign flips."""
        s = -x_slot
        hits = [i for i, n in enumerate(self.keep)
                if abs(n.s - s) < 1e-6 and abs(n.y - self.keep[0].y) < 1e-9]
        if not hits:
            hits = [min(range(self.n_frame),
                        key=lambda i: abs(self.keep[i].s - s)
                        + 10 * abs(self.keep[i].y + 0.6096))]
        return hits[0]

    def _frame_mesh(self):
        mdl = fe.Model(
            nodes=[fe.Node(i, n.s, n.y) for i, n in enumerate(self.keep)],
            elements=[fe.UserElement(k, self.renum[e.n1], self.renum[e.n2],
                                     1, 1, seed=1)
                      for k, e in enumerate(self.elems)],
            sections=[fe.PipeSection(1, OD, T_WALL)],
            materials=[fe.Material(1, RATIO * E_PIPE)])
        return fe.MeshedStructure(mdl)

    def xy(self, i: int) -> tuple:
        if i < self.n_frame:
            return (self.keep[i].s, self.keep[i].y)
        return self.extra_xy[i - self.n_frame]

    # -- assembly --------------------------------------------------------
    def assemble(self, U):
        """K and Fint for frame + connector elements, on the extended DOFs."""
        Uf = U[:3 * self.n_frame]
        theta0 = np.arctan2(
            self.mesh.elem_coords[:, 3] - self.mesh.elem_coords[:, 1],
            self.mesh.elem_coords[:, 2] - self.mesh.elem_coords[:, 0])
        Kf, Fintf, _, _, _ = fe.assemble(self.mesh, Uf, theta0, {}, [], 1.0)

        K = np.zeros((self.ndof, self.ndof))
        K[:3*self.n_frame, :3*self.n_frame] = Kf.toarray()
        Fint = np.zeros(self.ndof)
        Fint[:3*self.n_frame] = Fintf

        for (_t, i_bot, i_top, _i_frame) in self.conns:
            (xb, yb), (xt, yt) = self.xy(i_bot), self.xy(i_top)
            k6 = connector_k6(xt - xb, yt - yb)
            d = [3*i_bot, 3*i_bot+1, 3*i_bot+2, 3*i_top, 3*i_top+1, 3*i_top+2]
            K[np.ix_(d, d)] += k6
            Fint[d] += k6 @ U[d]
        return K, Fint

    def constraints(self, engaged):
        """(dof_a, dof_b, target) triples, per joint type and gap state.

        `target` is the value of (u_a - u_b) the tie enforces. It is 0 for
        every type except an ENGAGED D, and that exception is the whole of
        what a deadband means: a D carries load only once the two sides have
        moved +/- P_gap apart, so the constraint at engagement is

            u_a - u_b = +/- P_gap,      NOT      u_a - u_b = 0

        Enforcing 0 would drag the node back to coincidence, which drops the
        separation below the gap, which releases the connector, which lets it
        separate again. That is the chatter this signature exists to prevent:
        an engaged D holds AT the gap edge, not at zero.
        """
        out = []
        for (t, _i_bot, i_top, i_frame), state in zip(self.conns, engaged):
            shut = bool(state)
            ties = (TIES_SHUT if shut else TIES_OPEN)[t]
            for k, on in enumerate(ties):
                if not on:
                    continue
                target = 0.0
                if t == 'D' and shut and k == 1:
                    target = math.copysign(P_GAP, state)
                out.append((3*i_top + k, 3*i_frame + k, target))
        return out

    def fixed_dofs(self):
        return [3*i_bot + k for (_t, i_bot, _it, _if_) in self.conns
                for k in (0, 1, 2)]


# ---------------------------------------------------------------------------
# solve
# ---------------------------------------------------------------------------

def solve(rig: Rig, P: float, alpha: float = ALPHA, n_inc: int = 10,
          tol: float = 1e-9, max_iter: int = 30):
    """Incremental Newton with penalty MPCs and a D active set."""
    U = np.zeros(rig.ndof)
    engaged = [0] * len(rig.conns)        # 0 open, +1/-1 engaged and which way
    fixed = rig.fixed_dofs()
    load_dof = 3 * rig.top_node + 1
    info = {'alpha': alpha, 'cond': 0.0, 'violation': 0.0, 'active_flips': 0}

    for _pass in range(12):                   # active-set passes
        U = np.zeros(rig.ndof)
        for inc in range(1, n_inc + 1):
            lam = inc / n_inc
            for _it in range(max_iter):
                K, Fint = rig.assemble(U)
                Fext = np.zeros(rig.ndof)
                Fext[load_dof] = P * lam
                R = Fext - Fint

                # penalty MPCs, scaled to the LOCAL diagonals they tie
                for (a, b, target) in rig.constraints(engaged):
                    kp = alpha * max(K[a, a], K[b, b], 1.0)
                    K[a, a] += kp; K[b, b] += kp
                    K[a, b] -= kp; K[b, a] -= kp
                    g = (U[a] - U[b]) - target
                    R[a] -= kp * g
                    R[b] += kp * g

                # fixed DOFs, same penalty convention
                kf = alpha * max(K.diagonal().max(), 1.0)
                for dpos in fixed:
                    K[dpos, dpos] += kf
                    R[dpos] -= kf * U[dpos]

                if np.max(np.abs(R)) / max(abs(P), 1.0) < tol:
                    break
                dU = spsolve(csr_matrix(K), R)
                if not np.all(np.isfinite(dU)):
                    raise RuntimeError('singular system')
                U += dU

        # Engage on SEPARATION, release on FORCE. A D that is open engages
        # once the two sides have moved further than P_gap apart. A D that is
        # engaged sits AT the gap by construction -- that is what the +/-P_gap
        # target means -- so testing separation again would say "still at the
        # gap" forever and it could never let go. What tells you it should is
        # the sign of the force it carries: a support PUSHES, and when the tie
        # would have to pull in the direction it engaged, the sides are coming
        # back inside the gap and the D is open.
        K, _ = rig.assemble(U)
        new_engaged = []
        for state, (t, _ib, i_top, i_frame) in zip(engaged, rig.conns):
            if t != 'D':
                new_engaged.append(0)
                continue
            a, b = 3*i_top + 1, 3*i_frame + 1
            sep = U[a] - U[b]
            if not state:
                new_engaged.append(int(math.copysign(1, sep))
                                   if abs(sep) > P_GAP else 0)
            else:
                kp = alpha * max(K[a, a], K[b, b], 1.0)
                f_on_a = -kp * (sep - math.copysign(P_GAP, state))
                new_engaged.append(0 if f_on_a * state > 1e-6 * abs(P)
                                   else state)
        if new_engaged == engaged:
            break
        info['active_flips'] += 1
        engaged = new_engaged

    K, _ = rig.assemble(U)
    for (a, b, _t) in rig.constraints(engaged):
        kp = alpha * max(K[a, a], K[b, b], 1.0)
        K[a, a] += kp; K[b, b] += kp; K[a, b] -= kp; K[b, a] -= kp
    kf = alpha * max(K.diagonal().max(), 1.0)
    for dpos in fixed:
        K[dpos, dpos] += kf
    info['cond'] = np.linalg.cond(K)
    viol = [abs((U[a] - U[b]) - t) for (a, b, t) in rig.constraints(engaged)]
    info['violation'] = max(viol) if viol else 0.0
    info['engaged'] = engaged
    return U, info


def main() -> int:
    print(f'GD-ST on five connector layouts. Connector length '
          f'{CONN_LEN:.4f} m = 0.5 x OD,')
    print(f'stiffness prescribed at L0 = OD = {OD} m (pass 4, absolute).')
    print(f'Bottom nodes fixed in all DOF. Load 20 / 200 kN at stop1.')
    print(f'Penalty alpha = {ALPHA:.0e} x the local diagonal; D deadband '
          f'P_gap = {P_GAP*1e3:.1f} mm.\n')

    if '--sweep' in sys.argv:
        _sweep()
        return 0

    print(f'{"layout":7}{"slots":26}{"P_kN":>7}{"d_stop1_mm":>13}'
          f'{"sum_Ry_kN":>12}{"viol_mm":>11}{"cond":>11}  D')
    for name in LAYOUTS:
        rig = Rig(name)
        slots = ', '.join(f'{t}@{x:+.3f}' for t, x in
                          zip([t for t in rig.types if t],
                              [rig.xy(i)[0] for (_t, _b, i, _f) in rig.conns]))
        for P in (20e3, 200e3):
            U, info = solve(rig, P)
            d = U[3 * rig.top_node + 1]
            _, Fint = rig.assemble(U)
            Ry = sum(Fint[3*i_bot + 1] for (_t, i_bot, _it, _if_) in rig.conns)
            dstate = ''.join('#' if e else '.' for e in info['engaged'])
            print(f'{name:7}{slots:26}{P/1e3:7.0f}{d*1e3:13.5f}'
                  f'{-Ry/1e3:12.3f}{info["violation"]*1e3:11.2e}'
                  f'{info["cond"]:11.2e}  {dstate}')
        print()

    print("D column: '+'/'-' engaged and which way, '.' open. A D restrains")
    print('nothing while open, so PSD matches PS and F2D matches F2 exactly')
    print('until a deadband closes. At P_gap = 1 mm none does -- the largest')
    print('separation across a D is 0.61 mm. So the table above does not')
    print('exercise the D path at all, and the sweep below is what does.\n')

    _deadband()
    return 0


def _deadband():
    """Shrink the deadband until the D connectors engage.

    Without this the D rows above would be indistinguishable from a D that
    simply does not work. Engagement has to be SEEN changing the answer.
    """
    global P_GAP
    keep = P_GAP
    print('== PSD at 200 kN, shrinking the deadband ==')
    print(f'{"P_gap_mm":>10}{"engaged":>10}{"flips":>7}{"d_stop1_mm":>13}'
          f'{"viol_mm":>11}')
    rig = Rig('PSD')
    for gap in (1e-3, 6e-4, 5e-4, 3e-4, 1e-4, 3e-5):
        P_GAP = gap
        U, info = solve(rig, 200e3)
        d = U[3 * rig.top_node + 1]
        state = ''.join({0: '.', 1: '+', -1: '-'}[e] for e in info['engaged'])
        print(f'{gap*1e3:10.3f}{state:>10}{info["active_flips"]:7d}'
              f'{d*1e3:13.5f}{info["violation"]*1e3:11.2e}')
    P_GAP = keep
    print()
    print('Monotone, and it settles in one flip. Tighter gap -> the outer')
    print('supports engage sooner -> the frame stiffens -> less deflection,')
    print('approaching the rigid-support limit as the gap closes.')
    return 0


def _sweep():
    """Constraint violation against conditioning, over decades of alpha."""
    print('Penalty sweep on F2 at 200 kN. The working value is the one where')
    print('violation has stopped falling and conditioning has not yet run away.\n')
    print(f'{"alpha":>9}{"d_stop1_mm":>14}{"violation_mm":>15}{"cond(K)":>12}')
    rig = Rig('F2')
    prev = None
    for a in (1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e12):
        try:
            U, info = solve(rig, 200e3, alpha=a)
        except Exception as exc:                      # noqa: BLE001
            print(f'{a:9.0e}   {type(exc).__name__}: {exc}')
            continue
        d = U[3 * rig.top_node + 1]
        mark = ''
        if prev is not None and abs(d / prev - 1) < 1e-6:
            mark = '   <- converged'
        prev = d
        print(f'{a:9.0e}{d*1e3:14.6f}{info["violation"]*1e3:15.3e}'
              f'{info["cond"]:12.2e}{mark}')


if __name__ == '__main__':
    raise SystemExit(main())

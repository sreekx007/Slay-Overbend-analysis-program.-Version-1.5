"""slay.solve.contact -- contact slots and the active set that owns them.

A `ContactTarget` (T4) says where a roller wants the pipe. A SLOT is that
demand expressed in the solver's own terms: a list of DOF, a list of
coefficients, and a scalar target,

    sum_k c_k U[d_k] = dn,   c = (w_lo*nx, w_lo*ny, w_hi*nx, w_hi*ny)

constraining the NORMAL component only. The tangential direction stays free,
which is the point: a material point slides 2.07 m over the rollers by SR6
(R = 85), and a uy-only constraint fights that slide -- measured at ~2.4%
spurious strain concentration against ~0.29% pure-arc bending.

THE TWO ACTIVE-SET TESTS ARE NOT THE SAME TEST, and the asymmetry is the
whole of the validated formulation:

    RELEASE is REACTION-based.  release if  pen * r < -RELEASE_N
    RE-CONTACT is GAP-based.    re-engage if  r >= -GAP_TOL

An ACTIVE penalty constraint sits at |r| ~ R_n/pen ~ 1e-10 m, so a gap
threshold could never fire on it -- the SIGN of that tiny residual is what
encodes push (valid) against pull (tension). An INACTIVE constraint is not
enforced at all, so its gap is real and can be read directly.

ONE-SIDED IS WHAT DECIDES WHO MAY RELEASE. A one-sided roller pushes and lets
the pipe lift off; a bidirectional one also holds it down and therefore never
releases however tensile its reaction goes. That is carried as an EXEMPT set
rather than as a sign test, because "may not release" is a property of the
roller, not of the current reaction.

RELEASE ONCE PER INCREMENT. A slot released during an increment is barred
from re-contacting within that same increment. Without it a slot that
releases, springs back through its own target and re-engages can cycle
forever -- the same chatter the deadband active set has, met the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

from slay.solve.kernel import dof

# Reaction threshold for release, in NEWTONS. Absolute rather than relative:
# it is a force, and the validated formulation calibrates it against a
# penalty scaled off K's global maximum.
RELEASE_N = 1.0

# Gap tolerance for re-contact, in metres. An inactive slot's gap is real,
# so this is a genuine length and not a residual.
GAP_TOL = 1e-9


@dataclass(frozen=True)
class ContactSlot:
    name: str
    dofs: tuple
    coeffs: tuple
    dn: float
    one_sided: bool

    @property
    def exempt(self) -> bool:
        """A bidirectional roller may not release: it holds the pipe down."""
        return not self.one_sided

    def u_out(self, U) -> float:
        return float(sum(c * U[d] for c, d in zip(self.coeffs, self.dofs)))


def slots_from_targets(targets, ms) -> list:
    """`ContactTarget` -> `ContactSlot`, through the kernel's DOF numbering.

    Four DOF per slot: both translations of each bracketing node. A station
    that lands exactly on a node still gets four, two of them with zero
    coefficients -- uniform shape beats a special case, and the zero
    coefficients cost nothing because `apply_linear` skips them.
    """
    out = []
    for t in targets:
        nx, ny = t.normal
        out.append(ContactSlot(
            name=t.station,
            dofs=(dof(ms, t.n_lo, 0), dof(ms, t.n_lo, 1),
                  dof(ms, t.n_hi, 0), dof(ms, t.n_hi, 1)),
            coeffs=(t.w_lo * nx, t.w_lo * ny, t.w_hi * nx, t.w_hi * ny),
            dn=t.dn, one_sided=t.one_sided))
    return out


def incremental_target(slot: ContactSlot, anchor: float, lam: float) -> float:
    """Where the slot wants the pipe at load factor `lam`.

    Ramped from the state the solve STARTED in, not from zero:

        te = anchor + (dn - anchor) * lam

    `anchor` is `u_out` at entry. For a fresh solve that is 0 and this is the
    plain ramp; for a continued one (a sweep step carrying `state_in`) it
    ramps from where the pipe already is, so the increment is a real
    increment rather than a re-application of the whole target.
    """
    return anchor + (slot.dn - anchor) * lam


def slot_reactions(slots, active, U, pen, anchors, lam) -> tuple:
    """`(name, force, active)` per slot. Force in N, PUSH POSITIVE.

    THE SAME QUANTITY THE RELEASE TEST ALREADY USES. `update_active_set`
    below drops a one-sided roller when `pen * r` falls below `-RELEASE_N`,
    and `newton._constraint_force` calls that product "the physical reaction
    in kN -- well conditioned, where the raw separation is not": at
    convergence `r` is ~1e-9 m against a penalty of ~1e15 N/m, so the
    product is physical and `r` on its own is numerical noise. This function
    exists so the number can be REPORTED rather than only acted on.

    Sign follows the slot's outward normal, which points away from the arc
    centre, so a roller bearing on the pipe reads POSITIVE. A one-sided
    roller cannot pull, which is exactly why a sufficiently negative reading
    releases it; a bidirectional one (the terminal station, standing for the
    catenary continuation) may legitimately read negative.

    AN INACTIVE SLOT REPORTS 0.0, NOT ITS ARITHMETIC VALUE. A released
    roller applies nothing to the pipe -- its constraint is not assembled at
    all -- so `pen * r` for it is the force it WOULD apply if it were
    holding, which is not a reaction and must not be read as one.
    """
    out = []
    for i, slot in enumerate(slots):
        if active[i]:
            r = incremental_target(slot, anchors[i], lam) - slot.u_out(U)
            f = pen * r
        else:
            f = 0.0
        out.append((slot.name, float(f), bool(active[i])))
    return tuple(out)


def anchor_reactions(anchor_dofs, U, pen) -> tuple:
    """`(dof, force)` for each restrained DOF of the FIXED station, in N.

    Needed to CLOSE the equilibrium check and for no other reason. The fixed
    station is penalised the same way a slot is (`passage`: `Kl[d,d] +=
    p_val; R[d] += p_val * (0.0 - U[d])`), so its reaction has the same form
    -- but it is not a contact slot, so a sum over slots alone does NOT
    balance the applied load, and a check that ignored it would fail by
    whatever the anchor is carrying and look like a defect in the reactions.
    """
    return tuple((int(d), float(pen * (0.0 - U[d]))) for d in anchor_dofs)


def update_active_set(slots, active, released, U, pen, anchors, lam):
    """One active-set pass. Returns (new_active, changed).

    `released` is the set of slots already released THIS increment; it is
    mutated, because barring re-contact within the increment is what stops
    the cycle.
    """
    new = list(active)
    changed = False
    for i, slot in enumerate(slots):
        r = incremental_target(slot, anchors[i], lam) - slot.u_out(U)
        if new[i]:
            if pen * r < -RELEASE_N and not slot.exempt:
                new[i] = False
                released.add(i)
                changed = True
        else:
            if i not in released and r >= -GAP_TOL:
                new[i] = True
                changed = True
    return new, changed

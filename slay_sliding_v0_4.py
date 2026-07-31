"""
slay_sliding_v0_1.py -- EXPERIMENTAL sliding-contact passage sweep
==================================================================

################################################################################
##  STANDING RULE -- same as slay_overbend_v1_50.py's header, binds this
##  file equally. The authoritative source for component geometry (thick
##  pipe, shroud, taper, bulkhead) is COMPONENT_GEOMETRY_DEFINITIONS.md.
##  Before touching shroud_offset_at, the thick-component OD/CL_thick logic
##  in run_passage_sliding, or slide_coeffs: read that document's relevant
##  section first. If it is not available in the current session, STOP and
##  ask the user for it rather than deriving geometry from the paper or from
##  first principles -- this module imports its geometry functions from
##  slay_overbend_v1_50.py directly, so a geometry fix made there (checked
##  against the document) propagates here automatically; do not re-implement
##  geometry logic locally without the same check.
################################################################################

STATUS: experimental. Separate module BY DESIGN -- slay_overbend_v1_50.py
is NOT modified by this file, so the validated toolchain and every result
in SHROUD_VALIDATION_RESULTS.md remain reproducible. This module imports
what it needs from it.

VERSION: 0.4  (Session 26, 30 Jul 2026)
Changes from v0.3:
  + component_spacing and thick_offset_x added, mirroring
    slay_overbend_v1_50.py's run_passage_v2() implementation exactly (same
    comp_ranges convention: a list of (lo,hi) tuples, generalized from the
    start there but only ever populated with one un-offset tuple here
    until now). Closes two gaps found while building the Mode A results
    for the paper-validation results document:
    - Type A1 Study 3 (two-component spacing, 3 cases) needed
      component_spacing -- was entirely unsupported (not in the function
      signature at all, not just unused).
    - Type C1 Series 2 (thick-component position within the shroud, 3
      cases) needed thick_offset_x -- the thick component was always
      centred exactly on ref_centre_x with no way to move it.
    Both were surgical fixes: sec_ids assignment, self-weight
    distribution, and the roller-contact in_comp/CL_lift logic already
    iterated generically over comp_ranges (never assumed exactly one
    range), so only comp_ranges' own construction (and the mesh-snap
    point list, which was hardcoded to the single old c1 tuple) needed to
    change. Verified two ways before trusting: (1) a regression check
    with the new parameters left at their defaults reproduces the exact
    pre-v0.4 result (1.332447...%, matching to the last printed digit);
    (2) both new parameters cross-checked against run_passage_v2 called
    with identical arguments -- agreement to 10+ significant figures for
    both thick_offset_x and component_spacing. Error path (component_
    spacing without thick_component) confirmed to raise the same message
    as run_passage_v2's.
  + NOT done this pass: the per-position checkpointing gap in
    slay_landing_v0_1.py's run_landing_sweep() (only saves after the
    whole sweep completes, not per-position -- caused two silent restart-
    from-scratch incidents during the B1 S2-8 Mode B/landing run, tech-
    ref Session 25, before being caught and worked around with a manual
    per-position checkpoint script for that one case). Different module;
    flagged, not fixed here.

VERSION: 0.3  (Session 24 continued, 29 Jul 2026)
Changes from v0.2: none functional in this file -- re-pointed to import
from slay_overbend_v1_50.py (three plot-rendering fixes there: roller-
corner clearance, curvature-peak marker, X1-X5/shading deformed-x
mapping -- see that file's own v1.50 changelog). Since this module
imports its geometry/plotting functions directly, those fixes apply
here automatically.

VERSION: 0.2  (Session 24, 29 Jul 2026)
Changes from v0.1:
  + Vessel-roller contact convention changed to match the Abaqus reference
    model, identical change and identical mechanism to the one made in
    slay_overbend_v1_50.py v1.49 this session: by default only the 2
    vessel rollers nearest SR1 remain one-sided/releasable; every other
    VR is bidirectional (bilateral, no-uplift, permanently active) via
    an auto-default on the existing never_release parameter. An explicit
    never_release argument still overrides this default.
  + _moment_profile_nodal added to the import list, and record() now also
    computes/stores NE_nodal/x_nodal (true Abaqus-extrapolation nodal
    strain) and M_nodal/xM_nodal (same-convention nodal moment) alongside
    the existing "primary" B31-nodal-strain / element-mean-moment fields.
    DIAGNOSTIC ONLY -- built to test whether putting strain and moment on
    identical grids/conventions would close the peak-strain-vs-peak-moment
    location gap found this session. Confirmed it closes part of it
    (1.20m -> 0.80m for the case tested) but both nodal fields overshoot
    severely once the section plastifies (+56% moment, +106% strain vs.
    the primary convention) -- same overshoot mechanism already documented
    for _moment_profile_nodal's docstring, now confirmed empirically here
    too. NOT recommended as a replacement for the primary peak-extraction
    convention; kept as supplementary fields for this kind of diagnosis.
  + Confirmed (not fixed) this session: run_passage_sliding has NO
    auto-sizing of n_shifts against shroud length (unlike run_passage_v2's
    round(L_comp/elem_len_sr2) default) -- a caller must size the sweep
    explicitly. Also confirmed the "shift pushes VR1 past the anchor"
    ceiling (tech-ref 13.10 first found this for the B4/40D case) is
    independent of n_vr -- VR1 is always exactly one roller-spacing from
    the fixed anchor VR0 regardless of how many more VR stations exist
    further out, so the achievable sweep range is bounded at roughly one
    roller-spacing no matter what n_vr is set to. Getting more range
    requires sizing the vessel-side buffer itself, not just n_vr -- not
    implemented.

PURPOSE
-------
Test whether a genuine sliding contact clears the passage "walls" root-
caused in tech-ref 13.10: `lam` ramps the roller TARGET but not the
constraint SET, so at each integer shift the previously-held node is
released at full strength in one go, dumping its reaction and leaving a
residual independent of lam (immune to reg_mult, to finer increments, and
to cutback). A two-BC fade-in/fade-out ramp was tried and REJECTED
(tech-ref 13.12): two rank-1 penalties pulling adjacent nodes to the same
roller target sum to a rank-2 operator, which pins relative position i.e.
the element ROTATION, and the divergence simply moved to the rotation DOFs.

APPROACH
--------
Physically the roller sits still and the PIPE SLIDES OVER IT. The contact
point is fixed in space but corresponds to a MATERIAL POINT that moves
continuously along the pipe. So instead of "node j sits on the roller",
the constraint is "the material point at parametric station s inside the
element sits on the roller", with s advancing smoothly. When s reaches 1
it becomes s=0 of the next element -- continuously, with no event.

The constraint stays a SINGLE scalar per roller, so its penalty is a
rank-1 outer product `pen * a a^T` no matter where s sits, and it can
therefore never acquire the spurious rotational stiffness that killed the
two-BC ramp.

    u_out(s) = sum_k a_k d_k
    r        = dn - u_out
    F_k     += pen * a_k * r
    K_jk    += pen * a_j * a_k          (rank-1, 6x6 block)

STAGE 1 (this file): CHORD interpolation -- rotation coefficients zero.

    a = [ (1-s)nx, (1-s)ny, 0, s*nx, s*ny, 0 ]

Continuous (the property under test), trivially valid in the global frame,
and it avoids the local-frame subtlety of Hermite interpolation (Hermite
is strictly valid in the element's corotated local frame, whereas the
constraint uses global nodal displacements -- exact at a node, not
strictly so at an interior point). Discretisation error is the sagitta,
~L^2*kappa/8 ~ 4 mm at kappa=0.05, about 2% of the OD/2 standoff. Good
enough to answer "does sliding contact clear the wall?" before investing
in Stage 2.

STAGE 2 (not implemented): full cubic-Hermite,
    N1 = 1-3s^2+2s^3, N2 = L(s-2s^2+s^3), N3 = 3s^2-2s^3, N4 = L(-s^2+s^3)
    a  = [ nx(1-s), ny*N1, ny*N2, nx*s, ny*N3, ny*N4 ]
Still rank-1, but `a` then has nonzero entries in the theta slots, so the
single constraint DOES legitimately couple to rotation. Given how the
two-BC attempt failed, those DOFs need watching.

AT s = 0 this reduces EXACTLY to the current formulation (a = [nx,ny,0,...]),
which is the hard regression gate: integer shifts must reproduce
run_passage_v2 bit-for-bit.

APPROXIMATION, stated explicitly
--------------------------------
Which material point each roller contacts is PRESCRIBED from pay-out
kinematics (p = bn - shift), not SEARCHED for by minimising the gap to the
roller's spatial position. This is NOT a new approximation -- the existing
model already assumes roller i contacts node bn-shift. A gap-minimising
search is deliberately omitted: it introduces a nonlinear sub-problem and
would confound the test of whether sliding contact alone fixes the wall.

BONUS
-----
Because `shift` is now a float, the sweep is no longer locked to 0.8 m
granularity -- which independently addresses Batch 3's coverage problem
(S2-8 needed 28+ integer shifts to traverse its footprint). It also lets
release events happen where they actually belong rather than being
compressed into one 0.8 m step; whether that helps convergence is a
HYPOTHESIS, not established.
"""

import numpy as np
import slay_overbend_v1_50 as SO
from slay_overbend_v1_50 import (
    _build_geometry, shroud_offset_at,
    _strain_profile, _strain_profile_b31, _strain_profile_nodal,
    _moment_profile, _moment_profile_nodal,
)

spsolve = SO.spsolve
assemble = SO.assemble
Model = SO.Model
UserElement = SO.UserElement
PipeSection = SO.PipeSection
PipeSectionPolar = SO.PipeSectionPolar
MeshedStructure = SO.MeshedStructure
IncrementalIsotropic = SO.IncrementalIsotropic
RHO_STEEL = SO.RHO_STEEL
G = SO.G


# =============================================================================
# SLIDING CONSTRAINT COEFFICIENTS
# =============================================================================

def _x_at_ref_index(p, x_ref):
    """Reference x at fractional UNSNAPPED user-node index p (1-based).

    This is the *semantics* of a shift: exactly the position the old
    node-index scheme targeted. Kept on the unsnapped reference grid so
    snapping cannot change what a given shift MEANS.
    """
    n_lo = int(np.floor(p + 1e-9))
    frac = float(p - n_lo)
    if frac < 1e-9:
        frac = 0.0
    i_lo = max(0, min(n_lo - 1, len(x_ref) - 1))
    i_hi = min(i_lo + 1, len(x_ref) - 1)
    return (1.0 - frac)*x_ref[i_lo] + frac*x_ref[i_hi]


def slide_coeffs_x(x_target, nx, ny, mesh, nodes, hermite=False):
    """Sliding-contact coefficients at REFERENCE x = x_target, located on
    the ACTUAL (possibly snapped, non-uniform) mesh.

    Why this exists (this session): the original slide_coeffs indexes by
    user-node NUMBER, `p = bn - shift`. That relies on a topological
    invariant -- every span carries exactly `epe` nodes, so shifting by
    `epe` moves a roller exactly one station. (Note the mesh is NOT
    uniform in x: element lengths here span 0.62-0.82 m because SR-span
    chords shrink along the arc. Uniform NODE COUNT, not uniform length,
    is what the scheme actually depends on.) Boundary-snapping breaks
    that invariant by giving one span an extra node, which desyncs every
    downstream station -- observed as spurious releases at rollers
    nowhere near the component.

    Fix: keep the shift semantics on the UNSNAPPED reference grid (so a
    given shift targets exactly the same physical position it always
    did), then locate that position on the ACTUAL mesh by x. Identical
    results on an unsnapped mesh; correct on a snapped one.
    """
    xs = np.array([n.x for n in nodes])          # decreasing with node id
    k = int(np.searchsorted(-xs, -x_target, side='right')) - 1
    k = max(0, min(k, len(xs) - 2))
    x_lo, x_hi = xs[k], xs[k + 1]
    seg = x_lo - x_hi
    s = 0.0 if seg <= 1e-12 else float((x_lo - x_target)/seg)
    s = min(max(s, 0.0), 1.0)
    n_lo = k + 1                                  # user node id (1-based)
    n_hi = n_lo + 1
    if s < 1e-9:
        s = 0.0
    if s == 0.0 or n_hi not in mesh.user_node_to_mesh:
        n_hi = n_lo
        s = 0.0
    mi_lo = mesh.user_node_to_mesh[n_lo]
    mi_hi = mesh.user_node_to_mesh[n_hi]
    dofs = [3*mi_lo, 3*mi_lo + 1, 3*mi_lo + 2,
            3*mi_hi, 3*mi_hi + 1, 3*mi_hi + 2]
    x_mat = (1.0 - s)*nodes[n_lo - 1].x + s*nodes[n_hi - 1].x
    if not hermite:
        a = [(1.0 - s)*nx, (1.0 - s)*ny, 0.0, s*nx, s*ny, 0.0]
    else:
        L_e = abs(nodes[n_hi - 1].x - nodes[n_lo - 1].x) or 1.0
        N1 = 1 - 3*s*s + 2*s**3
        N2 = L_e*(s - 2*s*s + s**3)
        N3 = 3*s*s - 2*s**3
        N4 = L_e*(-s*s + s**3)
        a = [nx*(1.0 - s), ny*N1, ny*N2, nx*s, ny*N3, ny*N4]
    return dofs, a, x_mat


def slide_coeffs(p, nx, ny, mesh, nodes, hermite=False, L_elem=None):
    """Coefficients of the sliding contact constraint at material
    coordinate `p` (a FLOAT in user-node units: p = 3.5 means halfway
    between user nodes 3 and 4).

    Returns (dofs6, coeffs6, x_mat)
      dofs6   : global DOF indices [ux,uy,rz] of the lower node then upper
      coeffs6 : a_k such that u_out = sum(a_k * U[dofs6[k]])
      x_mat   : REFERENCE x of the material point (for shroud evaluation)

    At s = 0 this returns exactly a = [nx, ny, 0, 0, 0, 0] -- identical to
    the current node-based formulation.
    """
    n_lo = int(np.floor(p + 1e-9))
    s = float(p - n_lo)
    if s < 1e-9:
        s = 0.0
    n_hi = n_lo + 1
    if s == 0.0 or n_hi not in mesh.user_node_to_mesh:
        n_hi = n_lo                      # degenerate: all weight on n_lo
        s = 0.0
    mi_lo = mesh.user_node_to_mesh[n_lo]
    mi_hi = mesh.user_node_to_mesh[n_hi]
    dofs = [3*mi_lo, 3*mi_lo + 1, 3*mi_lo + 2,
            3*mi_hi, 3*mi_hi + 1, 3*mi_hi + 2]
    x_lo = nodes[n_lo - 1].x
    x_hi = nodes[n_hi - 1].x
    x_mat = (1.0 - s)*x_lo + s*x_hi

    if not hermite:
        # Stage 1: chord / linear interpolation of position
        a = [(1.0 - s)*nx, (1.0 - s)*ny, 0.0, s*nx, s*ny, 0.0]
    else:
        # Stage 2: full cubic-Hermite (NOT validated)
        if L_elem is None:
            L_elem = abs(x_hi - x_lo) or 1.0
        N1 = 1 - 3*s*s + 2*s**3
        N2 = L_elem*(s - 2*s*s + s**3)
        N3 = 3*s*s - 2*s**3
        N4 = L_elem*(-s*s + s**3)
        a = [nx*(1.0 - s), ny*N1, ny*N2, nx*s, ny*N3, ny*N4]
    return dofs, a, x_mat


# =============================================================================
# SOLVER (sliding variant of _solve_state)
# =============================================================================

def _solve_state_sliding(mesh, U, th, ps, dist, jl, anchor_dofs, slots, active,
                          n_increments, pen_mult, exempt_set, verbose, tag,
                          reg_mult=0.0):
    """Slot format here: (name, dofs6, coeffs6, dn).

    Contact recognition is UNCHANGED from the validated formulation -- both
    tests are on the scalar residual r = dn - u_out, which generalises
    directly (u_out is now a 6-term sum instead of 2).
      * RELEASE is reaction-based: R_n = pen*r, release if R_n < -1.0.
        An active penalty constraint sits at |r| ~ R/pen ~ 1e-10 m, so a
        gap threshold could never fire; the SIGN of that tiny residual is
        what encodes push (valid) vs pull (tension). See tech-ref.
      * RE-CONTACT is gap-based (r >= -1e-9): an inactive constraint is not
        enforced, so its gap is real.
    Adaptive cutback + divergence detection ported from v1.48.
    """
    def u_out(si):
        _, dofs, a, _dn = slots[si]
        return float(sum(a[k]*U[dofs[k]] for k in range(6)))

    anchor_vals = np.array([u_out(si) for si in range(len(slots))])
    status = 'ok'

    lam_done = 0.0
    dlam = 1.0 / n_increments
    dlam_min = dlam / 64.0
    attempt = 0
    while lam_done < 1.0 - 1e-12:
        attempt += 1
        lam = min(1.0, lam_done + dlam)
        U_snap = U.copy(); th_snap = th.copy()
        ps_snap = ps.copy() if ps is not None else None
        active_snap = list(active)
        ps_inc_start = ps.copy() if ps is not None else None
        ps_trial = ps_inc_start
        released = set()
        failed = False

        for cpass in range(8):
            rc = np.inf
            for it in range(30):
                K, Fint, Fext, th, ps_trial = assemble(
                    mesh, U, th, dist, jl, lam, plastic_state=ps_inc_start)
                Kd = float(K.diagonal().max())
                pen = Kd * pen_mult
                Kl = K.tolil(); Fp = Fext - Fint

                for d in anchor_dofs:
                    Kl[d, d] += pen; Fp[d] += pen * (0.0 - U[d])

                for si, (name, dofs, a, dn) in enumerate(slots):
                    if not active[si]:
                        continue
                    te = anchor_vals[si] + (dn - anchor_vals[si]) * lam
                    r = te - u_out(si)
                    # rank-1 outer product pen * a a^T  (and pen * a * r)
                    for j in range(6):
                        aj = a[j]
                        if aj == 0.0:
                            continue
                        Fp[dofs[j]] += pen * aj * r
                        for k in range(6):
                            ak = a[k]
                            if ak != 0.0:
                                Kl[dofs[j], dofs[k]] += pen * aj * ak

                Ks = Kl.tocsr()
                if reg_mult > 0.0:
                    Ks.setdiag(Ks.diagonal() + reg_mult * Kd)
                dU = spsolve(Ks, Fp)
                fm = max(float(np.max(np.abs(Fint))), 1.0)
                rc = float(np.max(np.abs(Fp[3:]))) / fm
                U += dU
                if (np.isnan(U).any() or np.max(np.abs(U)) > 100.0
                        or float(np.max(np.abs(dU))) > 1.0):
                    failed = True
                    break
                if it > 0 and rc < 1e-3:
                    break
            if failed:
                break

            changed = False
            for si, (name, dofs, a, dn) in enumerate(slots):
                te = anchor_vals[si] + (dn - anchor_vals[si]) * lam
                r_eff = te - u_out(si)
                if active[si]:
                    if pen * r_eff < -1.0 and si not in exempt_set:
                        active[si] = False; released.add(si); changed = True
                        if verbose:
                            print(f"    [{tag}] {name} released")
                else:
                    if si not in released and r_eff >= -1e-9:
                        active[si] = True; changed = True
                        if verbose:
                            print(f"    [{tag}] {name} re-contacted")
            if not changed:
                break

        if failed:
            U = U_snap; th = th_snap; ps = ps_snap; active = active_snap
            dlam *= 0.5
            if dlam < dlam_min:
                return U, th, ps, active, (
                    f'CUTBACK EXHAUSTED at lam={lam_done:.4f}')
            if verbose:
                print(f"    [{tag}] cutback -> dlam={dlam:.3e}")
            continue

        ps = ps_trial
        lam_done = lam
        dlam = min(1.0 / n_increments, dlam * 1.4)

    return U, th, ps, active, status


# =============================================================================
# DRIVER
# =============================================================================

def run_passage_sliding(R=70.0, D_o=0.4064, t=0.021,
                        shroud_component=None, thick_component=None,
                        component_spacing=None, thick_offset_x=0.0,
                        tension_mt=100.0, n_sr=6, n_vr=10, spacing=8.0,
                        shifts=None, n_shifts=4, d_shift=1.0,
                        n_increments_step0=40, n_increments_shift=20,
                        pen_step0=1e8, pen_shift=1e4,
                        section='polar', n_points_polar=8, n_fibres=20,
                        ref_centre_x=None, elem_len=None, reg_mult=0.0,
                        self_weight=True, never_release=None,
                        hermite=False, verbose=True):
    """Sliding-contact passage sweep. `shifts` may be an explicit list of
    FLOATS (in element units); otherwise d_shift*[0..n_shifts] is used.
    shifts=[0,1,2,...] with d_shift=1.0 must reproduce run_passage_v2.

    component_spacing (Study 3, v0.4): when set, builds a SECOND identical
    thick_component, its leading edge `component_spacing` beyond the
    first's trailing edge -- mirrors run_passage_v2's implementation
    exactly (same comp_ranges convention). thick_component-only; not
    wired to shroud_component-only calls (matches run_passage_v2).

    thick_offset_x (Type C1 studies, v0.4): when both thick_component and
    shroud_component are supplied, offsets the thick component's own
    centre from ref_centre_x (which continues to anchor the shroud's own
    CL_lift profile) -- e.g. -sc['L1']/3 centres it in the shroud's X2
    (catenary-side) third. Default 0.0 is fully backward-compatible
    (thick component centred on ref_centre_x, as before).
    """
    sc = shroud_component; tc = thick_component
    if sc is None and tc is None:
        raise ValueError("need shroud_component and/or thick_component")
    if component_spacing is not None and tc is None:
        raise ValueError("component_spacing (2-component sweep) requires "
                          "thick_component; not yet wired to shroud_component-only calls")
    two_comp = component_spacing is not None

    n_sr_total = n_sr + 1
    # REFERENCE grid -- unsnapped. Defines what a `shift` MEANS (and so
    # preserves every validated result exactly); never used as the mesh.
    nodes_ref, rnid_ref, dn_map, dtheta, nid_ref, allc = _build_geometry(
        R, n_sr_total, n_vr, spacing, D_o, elem_len=elem_len)
    nodes, rnid, nid = nodes_ref, rnid_ref, nid_ref
    x_sr2 = allc[n_vr + 2][0]
    L_comp = tc['length'] if tc is not None else (sc['L1'] + 2.0*sc['L2'])
    if ref_centre_x is None:
        ref_centre_x = x_sr2 + L_comp/2.0
    c1_centre = ref_centre_x + thick_offset_x
    c1_lo, c1_hi = c1_centre - L_comp/2.0, c1_centre + L_comp/2.0
    comp_ranges = [(c1_lo, c1_hi)] if tc is not None else []
    if two_comp:
        c2_lo = c1_hi + component_spacing
        c2_hi = c2_lo + L_comp
        comp_ranges.append((c2_lo, c2_hi))

    # ACTUAL mesh: snapped so each thick-component boundary is an exact
    # node (tech-ref 13.25/13.26 -- without this a 2.5D component
    # realizes only ~81% of its nominal length). Safe here now that the
    # shift semantics live on nodes_ref above and slots are located by x
    # rather than by node number.
    if tc is not None:
        snap_pts = [b for rng in comp_ranges for b in rng]
        nodes, rnid, dn_map, dtheta, nid, _allc_s = _build_geometry(
            R, n_sr_total, n_vr, spacing, D_o, elem_len=elem_len,
            snap_x=snap_pts)

    # Mesh-extent check (fail loudly, matching run_passage_v2's design
    # goal, rather than silently building an incomplete component 2).
    x_mesh_max = max(n.x for n in nodes)
    if two_comp and comp_ranges[-1][1] > x_mesh_max:
        raise ValueError(
            f"component_spacing={component_spacing} pushes the 2nd "
            f"component's trailing edge to x={comp_ranges[-1][1]:.2f}, "
            f"beyond the mesh extent (x_max={x_mesh_max:.2f}). Increase "
            f"n_vr or reduce component_spacing.")

    elem_len_sr2 = abs(allc[n_vr+2][0] - allc[n_vr+1][0]) / max(
        1, int(round(spacing / (elem_len if elem_len is not None else 2.0*D_o))))

    xn = np.array([n.x for n in nodes])
    x_mids = 0.5*(xn[:-1] + xn[1:])
    sec_ids = [2 if any(lo <= xm <= hi for (lo, hi) in comp_ranges) else 1
               for xm in x_mids]
    OD_tc = tc['OD'] if tc is not None else D_o
    t_tc = tc['t'] if tc is not None else t
    MAT = IncrementalIsotropic.abaqus_steel_nl_verified(id=1)
    if section == 'polar':
        SEC1 = PipeSectionPolar(id=1, D_o=D_o, t=t, n_fibres=n_points_polar)
        SEC2 = PipeSectionPolar(id=2, D_o=OD_tc, t=t_tc, n_fibres=n_points_polar)
        n_fib_active = n_points_polar
    else:
        SEC1 = PipeSection(id=1, D_o=D_o, t=t, n_fibres=n_fibres)
        SEC2 = PipeSection(id=2, D_o=OD_tc, t=t_tc, n_fibres=n_fibres)
        n_fib_active = n_fibres
    els = [UserElement(i, i, i+1, 1, sec_ids[i-1]) for i in range(1, nid)]
    mesh = MeshedStructure(Model(nodes=nodes, elements=els,
                                  sections=[SEC1, SEC2], materials=[MAT]))

    A_pl = np.pi/4*(D_o**2 - (D_o - 2*t)**2)
    A_th = np.pi/4*(OD_tc**2 - (OD_tc - 2*t_tc)**2)
    w_pl = RHO_STEEL*A_pl*G; w_th = RHO_STEEL*A_th*G
    dist = {}
    if self_weight:
        for e in els:
            mi = mesh.user_elem_to_mesh[e.id][0]
            dist[mi] = (0.0, w_th if sec_ids[e.id-1] == 2 else w_pl)
    jl = []
    if tension_mt > 0:
        T_N = tension_mt*1e3*G
        th_n = (n_sr_total - 1)*dtheta
        jl = [(mesh.user_node_to_mesh[nid], -T_N*np.cos(th_n),
               +T_N*np.sin(th_n), 0.0)]
    anchor_dofs = [3*mesh.user_node_to_mesh[1] + k for k in range(3)]
    r_o_elem = np.array([(OD_tc/2 if mesh.mesh_elems[ie][3] == 2 else D_o/2)
                          for ie in range(mesh.n_elems)])
    x_vr1 = allc[1][0]

    slot_names = ([f'VR{j}' for j in range(1, n_vr+1)] + ['SR1'] +
                  [f'SR{i}' for i in range(2, n_sr_total+1)])
    base_nodes = [rnid_ref[s] for s in range(1, len(allc))]
    x_ref = np.array([n.x for n in nodes_ref])
    slot_geom = []
    for s in range(1, len(allc)):
        if s <= n_vr + 1:
            slot_geom.append((0.0, -1.0, 0.0))
        else:
            k = s - n_vr
            th_k = (k - 1)*dtheta
            nx = -np.sin(th_k); ny = -np.cos(th_k)
            slot_geom.append((nx, ny, allc[s][1]*ny))
    exempt_set = {len(slot_names) - 1}
    if never_release is None:
        # v1.49 (Session 24, Sreekanth): match Abaqus reference model --
        # only the 2 vessel rollers nearest SR1 (VR{n_vr-1}, VR{n_vr}) are
        # genuine one-sided (unidirectional) contact and may release; every
        # OTHER vessel roller (VR1..VR{n_vr-2}) is bidirectional/bilateral
        # (no-uplift support) -- permanently active, never released.
        never_release = [f'VR{i}' for i in range(1, n_vr - 1)]
    if never_release:
        exempt_set |= {slot_names.index(nm) for nm in never_release}

    CL_thick = (OD_tc - D_o)/2.0 if tc is not None else 0.0
    ranges_eps = [(lo - 1e-6, hi + 1e-6) for (lo, hi) in comp_ranges]

    def make_slots(shift):
        out = []
        for name, bn, (nx, ny, dn) in zip(slot_names, base_nodes, slot_geom):
            p = bn - shift              # FLOAT coord in REFERENCE-grid units
            if p < 2.0:
                raise ValueError(f"shift {shift} pushes {name} past the anchor")
            x_t = _x_at_ref_index(p, x_ref)      # what this shift targets
            dofs, a, x_mat = slide_coeffs_x(x_t, nx, ny, mesh, nodes,
                                             hermite=hermite)
            in_comp = any(lo <= x_mat <= hi for (lo, hi) in ranges_eps)
            dn_sh = (shroud_offset_at(x_mat, ref_centre_x, sc['L1'], sc['L2'],
                                       sc['V'], D_o,
                                       taper=sc.get('taper', 'linear'))
                     if sc is not None else 0.0)
            out.append((name, dofs, a,
                        dn + (CL_thick if in_comp else 0.0) + dn_sh))
        return out

    def record(idx, shift, U, th, ps, active, slots, status):
        NE, xm = _strain_profile_b31(mesh, U, th, r_o_elem)
        NE_el, xm_el = _strain_profile(mesh, U, th, r_o_elem)
        M, xM = _moment_profile(mesh, U, th, ps)
        NE_nod, x_nod = _strain_profile_nodal(mesh, U, th, r_o_elem)
        M_nod, xM_nod = _moment_profile_nodal(mesh, U, th, ps)
        mask = xm < x_vr1 - 1e-6
        pk = int(np.argmax(NE*mask))
        rp = {}
        if sc is not None:
            lo, hi = ref_centre_x - sc['L1']/2.0, ref_centre_x + sc['L1']/2.0
            thd = sc['L1']/3.0; L2 = sc['L2']
            for nm, (a_, b_) in {'X1': (lo-L2, lo), 'X2': (lo, lo+thd),
                                  'X3': (lo+thd, hi-thd), 'X4': (hi-thd, hi),
                                  'X5': (hi, hi+L2)}.items():
                m = (xm >= a_) & (xm <= b_)
                rp[nm] = ({'peak_NE': float(np.max(NE*m)),
                           'peak_x': float(xm[int(np.argmax(NE*m))])}
                          if m.any() else {'peak_NE': None, 'peak_x': None})
        return {'index': idx, 'shift': float(shift),
                'travel_m': float(shift)*elem_len_sr2,
                'peak_NE': float(NE[pk]), 'peak_x': float(xm[pk]),
                'peak_NE_elem': float(np.max(NE_el*(xm_el < x_vr1 - 1e-6))),
                'NE_profile': NE.copy(), 'x_profile': xm.copy(),
                'M_profile': M.copy(), 'xM_profile': xM.copy(),
                'NE_nodal': NE_nod.copy(), 'x_nodal': x_nod.copy(),
                'M_nodal': M_nod.copy(), 'xM_nodal': xM_nod.copy(),
                'region_peaks': rp, 'status': status,
                'active': [slot_names[i] for i, v in enumerate(active) if v],
                'inactive': [slot_names[i] for i, v in enumerate(active) if not v],
                'slot_info': [{'name': slots[i][0],
                               'mi': slots[i][1][0]//3,
                               'nx': slot_geom[i][0], 'nys': slot_geom[i][1],
                               'dn': slots[i][3], 'active': bool(active[i])}
                              for i in range(len(slots))],
                'U': U.copy()}

    if shifts is None:
        shifts = [d_shift*i for i in range(n_shifts + 1)]

    U = np.zeros(mesh.n_dofs)
    th = np.full(mesh.n_elems, np.nan)
    ps = SO.PlasticState(mesh.n_elems, n_fib_active)
    active = [True]*len(slot_names)
    steps = []

    for idx, sh in enumerate(shifts):
        slots = make_slots(sh)
        n_inc = n_increments_step0 if idx == 0 else n_increments_shift
        pen_m = pen_step0 if idx == 0 else pen_shift
        if verbose:
            print(f"--- sliding step {idx}: shift={sh:.4f} elem "
                  f"({sh*elem_len_sr2:.3f} m) ---")
        U, th, ps, active, status = _solve_state_sliding(
            mesh, U, th, ps, dist, jl, anchor_dofs, slots, active,
            n_inc, pen_m, exempt_set, verbose, f'step{idx}', reg_mult=reg_mult)
        rec = record(idx, sh, U, th, ps, active, slots, status)
        steps.append(rec)
        if verbose:
            print(f"    peak={rec['peak_NE']*100:.4f}%  [{status}]")
        if status != 'ok':
            break

    return {'steps': steps, 'mesh': mesh, 'sec_ids': sec_ids, 'allc': allc,
            'ref_centre_x': ref_centre_x, 'elem_len_sr2': elem_len_sr2}

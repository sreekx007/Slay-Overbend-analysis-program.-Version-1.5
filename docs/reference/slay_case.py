"""
slay_case.py -- declarative case schema + validator for the S-Lay toolchain.

PURPOSE
-------
Remove judgement from the EXECUTION path. `run_passage_sliding` takes 28
parameters, nearly all with defaults, so a case can be silently wrong in a
dozen ways and still return plausible numbers. This module sits IN FRONT of
it and either

  * produces a fully-specified, provenance-stamped kwargs set, or
  * refuses, naming exactly what is missing or ambiguous.

It contains NO physics and touches NO solver code. It is a gate, not a model.

DESIGN RULES (these are the point -- do not relax them)
------------------------------------------------------
R1  NEVER guess a physical quantity. A missing kT is an ERROR, not a
    default. Only CONVENTIONS may default (contact_surface, envelope_rule,
    mesh density), and every one is stamped with its source.
R2  Anything previously improvised becomes a NAMED MODE. `plain_pipe` is a
    real case type, so nobody hand-builds a degenerate zero-length shroud
    to fake a baseline again (that was done in this project, and it worked
    only by accident of V - OD/2 = 0).
R3  DERIVE what should not be chosen by hand -- above all the sweep length,
    which was previously picked by eye (4, then 8, then 12; 12 crashed).
R4  Every emitted value carries provenance: 'user' | 'default:<why>' |
    'derived:<how>'. A result is then traceable to its inputs.
R5  Post-run CHECKS are computed by code and REPORTED as fields, never
    eyeballed. Specifically the tech-ref's turned-over test (below).

DOCUMENTED PROJECT RULES ENCODED HERE (with tech-ref citations)
--------------------------------------------------------------
* Sweep ceiling (tech-ref §13.10, §14.4): VR1 sits exactly one roller
  spacing from the fixed VR0 anchor BY CONSTRUCTION, so the achievable
  sweep is bounded at ~one spacing REGARDLESS of n_vr. §14.4 confirms
  raising n_vr 10->20 "had no effect". A sweep is therefore CAPPED, and
  then the turned-over check decides whether the capped result is valid.
* Turned-over check (tech-ref §13.10 precedent, restated §14.4): if the
  peak has risen and started to decrease within the reachable range, the
  peak is real despite not covering the nominal footprint. If it has not
  turned over, the result is genuinely INCOMPLETE and must be reported as
  such. This module computes that; it is not a judgement call.
* Mesh (tech-ref §13.17): standard 2xOD element length. The paper's own
  reference numbers were computed at 2xOD with an abrupt section change;
  refining to 1xOD moved AWAY from apples-to-apples and was reverted.
  Matching it dropped Study 1 from a 23-30% over-prediction band to 5.0%
  mean |diff| (§13.18). Do not "improve" this without a matching change to
  the comparison basis.
* EA-ST P_vt=0 (Paper 2 Sec.VII.J): the paper's own EA-ST studies place
  connectors on the pipe centreline and list the offset as a limitation.
  Non-zero P_vt is NOT a supported case here (the solver would need an
  offset-link tie), so it is rejected rather than silently ignored.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


class CaseError(ValueError):
    """Raised when a case is under-specified, ambiguous, or unsupported.

    Deliberately a hard failure. The entire purpose of this module is that
    an ambiguous case does NOT run.
    """


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

@dataclass
class Prov:
    """One resolved value plus where it came from."""
    value: object
    source: str          # 'user' | 'default:<why>' | 'derived:<how>'

    def __repr__(self):
        return f"{self.value!r} [{self.source}]"


# ---------------------------------------------------------------------------
# Project constants (conventions, not physics -- each cites its basis)
# ---------------------------------------------------------------------------

MESH_OD_MULTIPLE   = 2.0     # tech-ref §13.17: standard 2xOD, matches paper
ROLLER_RADIUS_M    = 0.30    # tech-ref §2.3 / §14.2; R is to roller CENTRELINE
CONTACT_SURFACE    = 'bottom'
ENVELOPE_RULE      = 'max'   # lowest surface owns contact; 'sum' double-counts
DEFAULT_SPACING_M  = 8.0
DEFAULT_N_SR       = 6
DEFAULT_N_VR       = 10

# Connector systems the SOLVER actually implements. P/S/D need tie slots
# (DOF-selective) and gap activation -- not built. Listing them here as
# known-but-unsupported means a user asking for PS gets a clear refusal
# rather than a silent substitution of F.
SUPPORTED_EAST_SYSTEMS   = ('F1', 'F2')
UNSUPPORTED_EAST_SYSTEMS = ('F1D', 'F2D', 'PS', 'PSD')


def _len(v, D_o, what):
    """Parse a length given either as metres (float) or as '<n>D' diameters.

    'D' notation is used throughout Paper 2 (P_c1=10D etc), so accepting it
    directly removes a hand-conversion step -- one of the places a silent
    factor-of-D error could enter.
    """
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().upper()
        if s.endswith('D'):
            try:
                return float(s[:-1]) * D_o
            except ValueError:
                pass
    raise CaseError(f"{what}: expected metres (number) or '<n>D' (e.g. '10D'), got {v!r}")


# ---------------------------------------------------------------------------
# The validator
# ---------------------------------------------------------------------------

def validate_case(case: dict) -> dict:
    """Validate a declarative case; return resolved kwargs + provenance.

    Returns
    -------
    dict with:
      'case_id'  : str
      'kwargs'   : dict -- ready to splat into run_passage_sliding(**kwargs)
      'prov'     : dict[str, Prov] -- every value, with its source
      'notes'    : list[str] -- non-fatal advisories the RUNNER should print
      'sweep'    : dict -- footprint/ceiling/coverage bookkeeping

    Raises
    ------
    CaseError -- on anything missing, ambiguous, or unsupported. Never
    substitutes a plausible value for a physical quantity (rule R1).
    """
    prov, notes = {}, []

    def take(name, value, source):
        prov[name] = Prov(value, source)
        return value

    if not isinstance(case, dict):
        raise CaseError("case must be a dict")
    case_id = case.get('case_id')
    if not case_id:
        raise CaseError("case_id is required (it names the result artefacts)")

    # ---- pipeline: ALL physical, so ALL required (R1) ---------------------
    pl = case.get('pipeline')
    if not isinstance(pl, dict):
        raise CaseError("'pipeline' block is required")
    for k in ('OD', 't', 'R', 'tension'):
        if k not in pl:
            raise CaseError(
                f"pipeline.{k} is required -- no default exists for a physical "
                f"quantity (rule R1). Paper 2 Sec.VI uses OD=406.4 t=21.0 "
                f"R=85.0 tension=100.0, but that must be stated, not assumed.")
    D_o = take('D_o', float(pl['OD'])/1000.0, 'user')     # mm -> m
    t_w = take('t',   float(pl['t'])/1000.0,  'user')
    R   = take('R',   float(pl['R']),         'user')
    T   = take('tension_mt', float(pl['tension']), 'user')
    if D_o <= 0 or t_w <= 0:
        raise CaseError("pipeline OD and t must be positive")
    if t_w >= D_o/2:
        raise CaseError(f"pipeline t ({t_w*1000:.1f} mm) >= OD/2 -- not an annulus")

    # ---- stinger conventions ---------------------------------------------
    st = case.get('stinger', {}) or {}
    spacing = take('spacing', float(st.get('spacing', DEFAULT_SPACING_M)),
                    'user' if 'spacing' in st else 'default:project_standard_8m')
    n_sr = take('n_sr', int(st.get('n_sr', DEFAULT_N_SR)),
                 'user' if 'n_sr' in st else 'default:project_standard')
    n_vr = take('n_vr', int(st.get('n_vr', DEFAULT_N_VR)),
                 'user' if 'n_vr' in st else 'default:project_standard')
    r_roller = take('r_roller', float(st.get('r_roller', ROLLER_RADIUS_M)),
                     'user' if 'r_roller' in st else 'default:tech-ref_2.3_roller_centreline')

    # ---- element length: DERIVED, not chosen (R3, tech-ref §13.17) -------
    elem_len = take('elem_len', MESH_OD_MULTIPLE * D_o,
                     'derived:2xOD_tech-ref_13.17_matches_paper_mesh')

    # ---- conventions (may default, but are stamped) ----------------------
    conv = case.get('conventions', {}) or {}
    contact_surface = take(
        'contact_surface', conv.get('contact_surface', CONTACT_SURFACE),
        'user' if 'contact_surface' in conv else 'default:bottom_R_is_roller_centreline')
    if contact_surface not in ('bottom', 'centreline'):
        raise CaseError("conventions.contact_surface must be 'bottom' or 'centreline'")
    envelope_rule = take(
        'envelope_rule', conv.get('envelope_rule', ENVELOPE_RULE),
        'user' if 'envelope_rule' in conv else 'default:max_lowest_surface_owns_contact')
    if envelope_rule not in ('max', 'sum'):
        raise CaseError("conventions.envelope_rule must be 'max' or 'sum'")
    if envelope_rule == 'sum':
        notes.append(
            "envelope_rule='sum' is LEGACY: it double-counts where a thick "
            "component and a shroud overlap (measured +7.9%). Use only to "
            "reproduce a pre-v0.5 combined-case number.")
    if contact_surface == 'centreline':
        notes.append(
            "contact_surface='centreline' is LEGACY (pipe centreline driven "
            "onto the roller arc, ignoring r_roller + r_pipe). Use only to "
            "reproduce pre-v0.5 numbers.")

    # ---- component: the named-mode gate (R2) -----------------------------
    comp = case.get('component')
    if not isinstance(comp, dict) or 'type' not in comp:
        raise CaseError(
            "'component' block with a 'type' is required. Supported types: "
            "plain_pipe, thick, shroud, EA-ST.")
    ctype = str(comp['type']).strip()

    kw_comp = dict(thick_component=None, shroud_component=None,
                   structure_component=None)
    footprint = 0.0

    if ctype == 'plain_pipe':
        # R2: a REAL mode. Previously faked with a zero-length shroud whose
        # V happened to cancel (V - OD/2 = 0) -- correct by accident, opaque
        # to any reader, and silently wrong if V were ever edited.
        take('component', 'plain_pipe', 'user')
        kw_comp['allow_plain_pipe'] = True   # genuine bare-pipe mode (R2)
        footprint = 0.0

    elif ctype == 'thick':
        for k in ('OD', 't', 'length'):
            if k not in comp:
                raise CaseError(f"component.{k} is required for type 'thick'")
        OD_tc = float(comp['OD'])/1000.0
        t_tc  = float(comp['t'])/1000.0
        L_tc  = _len(comp['length'], D_o, 'component.length')
        if OD_tc <= D_o:
            raise CaseError(
                f"thick component OD ({OD_tc*1000:.1f} mm) must EXCEED pipe OD "
                f"({D_o*1000:.1f} mm) -- a thinner body is a different component "
                f"with the opposite strain mechanism.")
        kw_comp['thick_component'] = dict(OD=OD_tc, t=t_tc, length=L_tc)
        take('component', f'thick OD={OD_tc*1000:.1f} L={L_tc:.3f}', 'user')
        footprint = L_tc

    elif ctype == 'shroud':
        for k in ('V', 'L1', 'L2'):
            if k not in comp:
                raise CaseError(f"component.{k} is required for type 'shroud'")
        V  = _len(comp['V'],  D_o, 'component.V')
        L1 = _len(comp['L1'], D_o, 'component.L1')
        L2 = _len(comp['L2'], D_o, 'component.L2')
        if V < D_o/2:
            raise CaseError(
                f"shroud V ({V*1000:.1f} mm) < pipe radius ({D_o/2*1000:.1f} mm) "
                f"-- the shroud cannot sit inside the pipe.")
        kw_comp['shroud_component'] = dict(V=V, L1=L1, L2=L2)
        take('component', f'shroud V={V:.4f} L1={L1:.3f} L2={L2:.3f}', 'user')
        footprint = L1 + 2*L2

    elif ctype in ('EA-ST', 'EAST', 'top_structure'):
        sysname = str(comp.get('system', '')).strip().upper()
        if not sysname:
            raise CaseError(
                "component.system is required for EA-ST (F1 or F2). "
                "Connection system governs the result -- it is never assumed.")
        if sysname in UNSUPPORTED_EAST_SYSTEMS:
            raise CaseError(
                f"EA-ST system '{sysname}' is defined in Paper 2 but NOT "
                f"implemented in the solver: P/S connectors need DOF-selective "
                f"tie slots and D needs gap activation. Supported: "
                f"{', '.join(SUPPORTED_EAST_SYSTEMS)}. Refusing rather than "
                f"substituting F, which would silently answer a different question.")
        if sysname not in SUPPORTED_EAST_SYSTEMS:
            raise CaseError(f"unknown EA-ST system '{sysname}'")
        if 'kT' not in comp:
            raise CaseError(
                "component.kT is required for EA-ST -- no default (rule R1). "
                "Paper 2 Sec.VII uses 2.22-2.85 x pipeline EI, but the value "
                "must be stated.")
        kT = float(comp['kT'])
        if kT <= 0:
            raise CaseError("component.kT must be > 0")
        P_vt = _len(comp.get('P_vt', 0.0), D_o, 'component.P_vt')
        if abs(P_vt) > 1e-12:
            raise CaseError(
                "component.P_vt != 0 is not supported: a real standoff makes "
                "the connector an offset link needing a tie slot with a moment "
                "arm, which is not implemented. Paper 2 Sec.VII.J lists this "
                "same limitation for its own studies.")
        sc = dict(system=sysname, kT=kT, P_vt=0.0)
        if sysname == 'F2':
            if 'P_c1' not in comp:
                raise CaseError("component.P_c1 is required for EA-ST system F2")
            P_c1 = _len(comp['P_c1'], D_o, 'component.P_c1')
            if P_c1 <= 0:
                raise CaseError("component.P_c1 must be > 0")
            sc['P_c1'] = P_c1
            footprint = P_c1
            # Advisory, NOT an error: a connector span within 5% of the roller
            # spacing puts BOTH connectors on adjacent rollers, where the pipe
            # is already restrained. Physically legitimate, but a special
            # configuration whose result should not be read as generic.
            if abs(P_c1 - spacing) / spacing < 0.05:
                notes.append(
                    f"P_c1={P_c1:.3f} m is within 5% of roller spacing "
                    f"({spacing:.2f} m): both connectors land on ADJACENT "
                    f"rollers. Legitimate, but a special case -- do not read "
                    f"the result as generic F2 behaviour.")
        else:
            footprint = 0.0
        kw_comp['structure_component'] = sc
        take('component', f'EA-ST {sysname} kT={kT} P_vt=0', 'user')

    else:
        raise CaseError(
            f"unknown component.type '{ctype}'. Supported: plain_pipe, thick, "
            f"shroud, EA-ST.")

    for k, v in kw_comp.items():
        prov[k] = Prov(v, 'derived:from_component_block')

    # ---- sweep: DERIVED and CAPPED (R3; tech-ref §13.10/§14.4) -----------
    sw = case.get('sweep', {}) or {}
    mode = str(sw.get('mode', 'auto_footprint'))

    # Ceiling: VR1 is ONE spacing from the VR0 anchor by construction, so the
    # reachable sweep is ~one spacing REGARDLESS of n_vr (§14.4 confirmed
    # n_vr 10->20 had no effect). Expressed in ELEMENTS, matching the solver's
    # own `p = bn - shift; if p < 2.0: raise`.
    ceiling_elems = max(1, int(math.floor(spacing/elem_len)) - 1)

    if mode == 'auto_footprint':
        want = max(1, int(math.ceil(footprint/elem_len))) if footprint > 0 else 4
        n_shifts = min(want, ceiling_elems)
        src = (f'derived:ceil(footprint/elem_len)={want}'
               + (f' CAPPED to anchor ceiling {ceiling_elems} '
                  f'(tech-ref 13.10/14.4)' if n_shifts < want else ''))
        if n_shifts < want:
            notes.append(
                f"Sweep CAPPED: footprint needs {want} shifts, anchor ceiling "
                f"allows {ceiling_elems} (VR1 is one spacing from VR0 by "
                f"construction; raising n_vr does NOT help -- tech-ref §14.4). "
                f"The turned-over check decides whether the capped result is "
                f"valid; see check_sweep_coverage().")
    elif mode == 'explicit':
        if 'n_shifts' not in sw:
            raise CaseError("sweep.mode='explicit' requires sweep.n_shifts")
        want = int(sw['n_shifts'])
        n_shifts = min(want, ceiling_elems)
        src = 'user' + ('' if n_shifts == want else f' CAPPED to {ceiling_elems}')
        if n_shifts < want:
            notes.append(
                f"Requested n_shifts={want} exceeds the anchor ceiling "
                f"{ceiling_elems}; capped (tech-ref §14.4).")
    else:
        raise CaseError("sweep.mode must be 'auto_footprint' or 'explicit'")
    take('n_shifts', n_shifts, src)
    take('d_shift', float(sw.get('d_shift', 1.0)),
          'user' if 'd_shift' in sw else 'default:1_element_per_shift')

    kwargs = dict(
        R=R, D_o=D_o, t=t_w, tension_mt=T,
        spacing=spacing, n_sr=n_sr, n_vr=n_vr, elem_len=elem_len,
        contact_surface=contact_surface, r_roller=r_roller,
        envelope_rule=envelope_rule,
        n_shifts=n_shifts, d_shift=prov['d_shift'].value,
        verbose=False, **kw_comp)

    return dict(case_id=case_id, kwargs=kwargs, prov=prov, notes=notes,
                sweep=dict(footprint_m=footprint, elem_len_m=elem_len,
                            ceiling_elems=ceiling_elems, n_shifts=n_shifts,
                            capped=bool(n_shifts < locals().get('want', n_shifts))))


# ---------------------------------------------------------------------------
# Post-run check -- computed, not eyeballed (R5)
# ---------------------------------------------------------------------------

def check_sweep_coverage(result) -> dict:
    """Turned-over check (tech-ref §13.10 precedent, restated §14.4).

    If the peak strain rose and then began to FALL within the swept range,
    the maximum is real even though the sweep may not have covered the
    nominal footprint. If it is still rising at the last shift, the result
    is genuinely INCOMPLETE.

    This replaces reading it off a plot. In this project's own history that
    judgement was made by eye ("the curve decreases monotonically after its
    max, so the peak is captured") -- correct that time, but exactly the
    kind of call that should be mechanical.
    """
    pk = [s['peak_NE'] for s in result['steps']]
    i = max(range(len(pk)), key=lambda k: pk[k])
    turned_over = (i < len(pk) - 1)
    return dict(
        n_steps=len(pk), peak_index=i, peak_NE=pk[i],
        peak_at_last_shift=(i == len(pk) - 1),
        turned_over=turned_over,
        verdict=('peak captured (turned over within swept range)' if turned_over
                 else 'INCOMPLETE: still rising at the last shift -- peak NOT '
                      'captured; the true maximum is beyond the reachable sweep'),
        peaks=pk)


def format_provenance(v: dict) -> str:
    """Human-readable provenance table for the run log / report."""
    out = [f"CASE: {v['case_id']}", "-"*66,
           f"{'PARAMETER':<20}{'VALUE':<26}SOURCE"]
    for k, p in v['prov'].items():
        val = p.value
        s = (f"{val:.6g}" if isinstance(val, float)
             else ('None' if val is None else str(val)))
        out.append(f"{k:<20}{s[:25]:<26}{p.source}")
    if v['notes']:
        out.append("-"*66)
        for n in v['notes']:
            out.append("NOTE: " + n)
    sw = v['sweep']
    out.append("-"*66)
    out.append(f"sweep: footprint={sw['footprint_m']:.3f} m  "
               f"elem_len={sw['elem_len_m']:.4f} m  "
               f"ceiling={sw['ceiling_elems']}  n_shifts={sw['n_shifts']}"
               f"{'  [CAPPED]' if sw['capped'] else ''}")
    return "\n".join(out)

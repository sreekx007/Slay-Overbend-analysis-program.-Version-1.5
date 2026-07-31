"""
S-Lay Landing Check -- Mode B Analysis
========================================

################################################################################
##  slay_landing_v0_1.py
##
##  Mode B analysis: single-point Anchor/Landing Check.
##
##  STANDING RULE -- same as slay_sliding_v0_x.py's header, binds this file
##  too: geometry (roller layout, shroud_offset_at, thick-component
##  auto-elevation, section models) is defined ONCE in
##  slay_overbend_v1_50.py and MUST NOT be re-implemented here. This module
##  imports what it needs from it directly, so a geometry fix made there
##  (checked against COMPONENT_GEOMETRY_DEFINITIONS.md) propagates here
##  automatically.
##
##  STATUS: new this session (Session 25). Separate module BY DESIGN, same
##  rationale as slay_sliding -- so this file's own iteration/debugging can
##  never risk corrupting the validated slay_overbend or slay_sliding
##  toolchains. See SLAY_OVERBEND_ACTION_PLAN.md for the two-mode program
##  design this implements one half of.
################################################################################

VERSION: 0.1  (Session 25, 29 Jul 2026)
Initial build. Implements Mode B as defined in SLAY_OVERBEND_ACTION_PLAN.md
sec3: evaluate a component sitting at a given position relative to a named
anchor roller, as an INDEPENDENT check -- fresh (virgin) plastic state
every time, no chaining in or out. Contrast with Mode A
(slay_sliding_v0_3.py's run_passage_sliding(), and run_passage_v2() itself
-- both confirmed CHAINED this session, see tech-ref Session 24 sec re:
correcting that assumption).

DESIGN CHOICE: rather than write a parallel solve loop, run_landing_check()
reuses run_passage_v2()'s own "virgin step 0" pathway directly -- that
step already IS a from-scratch, fresh-PlasticState solve (a new
PlasticState is instantiated immediately before it, every call). Calling
run_passage_v2(..., n_shifts=0) at a chosen ref_centre_x, once per
position, with NO state passed between calls, gives an independent
landing check while reusing 100% already-validated mesh-building,
roller-slot, and _solve_state machinery. No new solver code in this file
at all -- only position bookkeeping and result packaging.

################################################################################
"""

import time
import numpy as np
import slay_overbend_v1_50 as SO
from slay_overbend_v1_50 import _build_geometry


def landing_anchor_x(station, R=70.0, D_o=0.4064, n_sr=6, n_vr=3, spacing=8.0):
    """Resolve a named roller station ('SR1'..'SRn', 'VR0'..'VRn_vr') to its
    reference x position, using the identical convention run_passage_v2()
    and run_passage_sliding() already use internally (rnid: 0=VR0, 1=VR1,
    ..., n_vr=VR{n_vr}, n_vr+1=SR1, n_vr+2=SR2, ...). Matches the ad hoc
    `anchor_x()` helper used repeatedly during Session 24 -- now a proper,
    reusable utility instead of being rebuilt inline each time.
    """
    station = station.strip().upper()
    kind = station[:2]
    k = int(station[2:])
    if kind == 'SR':
        idx = n_vr + k
    elif kind == 'VR':
        idx = k
    else:
        raise ValueError(f"station must look like 'SR3' or 'VR2', got {station!r}")
    n_sr_total = n_sr + 1
    nodes, rnid, dn_map, dtheta, nid, allc = _build_geometry(
        R, n_sr_total, n_vr, spacing, D_o)
    if idx < 0 or idx >= len(allc):
        raise ValueError(f"station {station!r} (index {idx}) is out of range "
                          f"for n_sr={n_sr}, n_vr={n_vr}")
    return allc[idx][0]


def run_landing_check(ref_centre_x, R=70.0, D_o=0.4064, t=0.021,
                       thick_component=None, shroud_component=None,
                       component_spacing=None,
                       material='J2', tension_mt=100.0, self_weight=True,
                       n_sr=6, n_vr=3, spacing=8.0,
                       n_increments=40,
                       section='polar', n_points_polar=8, n_fibres=20,
                       verbose=False, never_release=None,
                       k_spring=0.0, reg_mult=0.0, elem_len=None,
                       pen=1e8, thick_offset_x=0.0):
    """Mode B, single position: evaluate the component centred at
    `ref_centre_x`, from a FRESH (virgin) plastic state -- no history
    carried in from any other position, no history carried out.

    Returns the SAME shape as one run_passage_v2() call
    ({'steps': [rec], 'mesh', 'sec_ids', 'allc'}) so plot_step_deformed()
    and every other results-analysis helper built for run_passage_v2/
    run_passage_sliding work on it completely unchanged -- rec['step'] is
    already 0 (no key-aliasing needed, unlike sliding-module results).

    n_increments here maps to run_passage_v2's n_increments_step0 (the
    virgin-drape increment count) -- appropriate since every landing
    check IS a virgin-drape solve, never a continuation.
    """
    res = SO.run_passage_v2(
        R=R, D_o=D_o, t=t,
        thick_component=thick_component, shroud_component=shroud_component,
        component_spacing=component_spacing,
        n_shifts=0,                     # single virgin solve, no shift loop
        material=material, tension_mt=tension_mt, self_weight=self_weight,
        n_sr=n_sr, n_vr=n_vr, spacing=spacing,
        n_increments_step0=n_increments, n_increments_shift=n_increments,
        section=section, n_points_polar=n_points_polar, n_fibres=n_fibres,
        ref_centre_x=ref_centre_x, verbose=verbose, never_release=never_release,
        k_spring=k_spring, reg_mult=reg_mult, elem_len=elem_len,
        pen_step0=pen, pen_shift=pen, thick_offset_x=thick_offset_x)
    res['ref_centre_x'] = ref_centre_x
    if res['steps']:
        res['steps'][0]['mode'] = 'landing'
    return res


def run_landing_sweep(anchor_station, R=70.0, D_o=0.4064, t=0.021,
                       thick_component=None, shroud_component=None,
                       component_spacing=None, n_positions=None,
                       material='J2', tension_mt=100.0, self_weight=True,
                       n_sr=6, n_vr=3, spacing=8.0, n_increments=40,
                       section='polar', n_points_polar=8, n_fibres=20,
                       verbose=False, never_release=None,
                       k_spring=0.0, reg_mult=0.0, elem_len=None,
                       pen=1e8, thick_offset_x=0.0):
    """Mode B, swept: independent landing checks at `n_positions` points
    spanning leading-edge-at-anchor through trailing-edge-at-anchor --
    the SAME physical range Mode A's default sweep covers (matching
    run_passage_v2's own auto n_shifts sizing:
    round(L_comp/elem_len_sr2)), for direct comparability -- but each
    position solved independently (Mode B; no chaining), rather than
    Mode A's continuous chained walk through that same range.

    anchor_station: e.g. 'SR2', 'SR5', 'VR1' -- resolved via
    landing_anchor_x() using the SAME R/D_o/n_sr/n_vr/spacing passed here.

    Returns: list of per-position result dicts (each independently
    plot_step_deformed()-compatible), plus a summary dict with the
    envelope (max-over-positions) peak strain/moment and each call's
    wall-clock time, for the Mode A vs Mode B runtime comparison.
    """
    tc = thick_component; sc = shroud_component
    if tc is not None and sc is not None:
        L_comp = max(tc['length'], sc['L1'] + 2.0*sc['L2'])
    elif tc is not None:
        L_comp = tc['length'] if component_spacing is None else \
                 (2.0*tc['length'] + component_spacing)
    elif sc is not None:
        L_comp = sc['L1'] + 2.0*sc['L2']
    else:
        raise ValueError("run_landing_sweep needs thick_component and/or "
                          "shroud_component")

    x_anchor = landing_anchor_x(anchor_station, R=R, D_o=D_o, n_sr=n_sr,
                                 n_vr=n_vr, spacing=spacing)

    if n_positions is None:
        # match run_passage_v2's own auto n_shifts sizing exactly, so a
        # Mode A vs Mode B comparison sweeps the same number of positions
        n_sr_total = n_sr + 1
        nodes, rnid, dn_map, dtheta, nid, allc = _build_geometry(
            R, n_sr_total, n_vr, spacing, D_o)
        elem_len_sr2 = abs(allc[n_vr + 2][0] - allc[n_vr + 1][0]) / max(
            1, round(spacing / (elem_len if elem_len is not None else 2.0*D_o)))
        n_positions = max(2, int(round(L_comp / elem_len_sr2))) + 1

    # leading edge at anchor (position 0) -> trailing edge at anchor (last)
    # centre = x_anchor + L_comp/2 (leading edge at anchor)
    #       -> x_anchor - L_comp/2 (trailing edge at anchor)
    centres = np.linspace(x_anchor + L_comp/2.0, x_anchor - L_comp/2.0, n_positions)

    results = []
    times = []
    for i, cx in enumerate(centres):
        if verbose:
            print(f"--- landing check {i+1}/{n_positions}  ref_centre_x={cx:.3f} ---")
        t0 = time.time()
        res = run_landing_check(
            float(cx), R=R, D_o=D_o, t=t,
            thick_component=thick_component, shroud_component=shroud_component,
            component_spacing=component_spacing,
            material=material, tension_mt=tension_mt, self_weight=self_weight,
            n_sr=n_sr, n_vr=n_vr, spacing=spacing, n_increments=n_increments,
            section=section, n_points_polar=n_points_polar, n_fibres=n_fibres,
            verbose=False, never_release=never_release,
            k_spring=k_spring, reg_mult=reg_mult, elem_len=elem_len,
            pen=pen, thick_offset_x=thick_offset_x)
        dt = time.time() - t0
        times.append(dt)
        if res['steps']:
            res['steps'][0]['index'] = i
            res['steps'][0]['solve_time_s'] = dt
        results.append(res)
        if verbose and res['steps']:
            s = res['steps'][0]
            print(f"    peak={s['peak_NE']*100:.4f}%  status={s['status']}  {dt:.1f}s")

    ok_peaks = [(i, r['steps'][0]['peak_NE']) for i, r in enumerate(results)
                if r['steps'] and r['steps'][0]['status'] == 'ok']
    if ok_peaks:
        i_env, peak_env = max(ok_peaks, key=lambda p: p[1])
    else:
        i_env, peak_env = None, None

    summary = dict(
        anchor_station=anchor_station, x_anchor=x_anchor, L_comp=L_comp,
        n_positions=n_positions, centres=list(centres),
        envelope_peak_NE=peak_env, envelope_index=i_env,
        n_converged=sum(1 for r in results if r['steps'] and r['steps'][0]['status'] == 'ok'),
        total_time_s=sum(times), mean_time_s=float(np.mean(times)) if times else None,
        times_s=times,
    )
    return results, summary

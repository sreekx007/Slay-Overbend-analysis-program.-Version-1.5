"""
S-Lay Overbend Simplified FEA Model
=====================================

################################################################################
##  STANDING RULE -- READ BEFORE TOUCHING ANY COMPONENT GEOMETRY
##
##  The authoritative source for EVERY component's geometry -- what grows,
##  what stays fixed, where a boundary is abrupt vs tapered, how it must be
##  drawn -- is COMPONENT_GEOMETRY_DEFINITIONS.md, not this file's comments,
##  not the companion paper, and not first-principles re-derivation. That
##  document exists specifically because natural-language specs are
##  geometrically ambiguous (its own words: "1.5x wall thickness" doesn't say
##  whether ID or OD is held constant, and the difference changes the
##  strain-amplification mechanism predicted) and because it has been
##  cross-model tested (Grok, Copilot, a separate Claude instance) through
##  eight documented rounds of real rendering bugs -- diagonal connectors
##  between top/bottom surfaces, mirrored curves, unbounded segments,
##  placeholder zeros, undocumented markers -- each one found, fixed, and
##  written up as an explicit rule so it cannot recur silently.
##
##  BEFORE modifying or extending ANY component geometry function
##  (shroud_offset_at, thick-component OD/CL_thick logic, plot_step_deformed's
##  wall/fill/marker drawing, or adding a new component type):
##    1. Locate COMPONENT_GEOMETRY_DEFINITIONS.md in the current session.
##    2. Read the relevant section's Rules table (not just skim the YAML)
##       before writing or changing a single line of geometry code.
##    3. If the document is NOT available in the current session -- STOP.
##       Do not guess, do not re-derive from the paper, do not assume the
##       previous session's implementation was already checked against it.
##       Ask the user to provide the document before proceeding.
##  This applies to every sub-script that touches this geometry too
##  (slay_sliding_v0_1.py and any future variant) -- the rule lives here
##  once, centrally, rather than being restated per file, but binds all of
##  them equally.
##
##  Session 23 case study in why this matters: a bug was found (peak strain
##  displaced a full element from a thick-component's true material
##  boundary, tech-ref 13.24) DURING a check the user specifically requested
##  after re-reading this document -- i.e. the document caught something a
##  from-scratch geometric derivation, and one prior "fix" pass, both missed.
################################################################################

VERSION: 1.50  (Session 24 continued, 29 Jul 2026)
Changes from v1.49 (all found by direct user review of shared plots,
same pattern as v1.49's own fixes -- root-caused numerically each time,
not just patched to match what the picture "should" look like):
  + Roller-marker penetrating the shroud near a sharp taper/plateau
    corner: the roller's drawn clearance was computed from the shroud
    depth at a SINGLE point (its own node), which can be locally tangent
    yet still have the finite-radius drawn circle overlap a neighbouring,
    deeper part of the curve just past a sharp corner. Confirmed
    numerically (min distance from roller centre to the true contact
    curve was 0.24m against a 0.30m roller radius -- a real overlap).
    Fixed by taking the MAX shroud depth over a window of +/-1.5*r_roller
    around the roller's own position, not just its own point -- clears
    the nearby corner in every case checked. Visualization-only; the
    real contact solve operates on points and was never affected.
  + New _curvature_peak() helper + plot marker: locates and marks the
    integration point of true maximum |curvature|, distinct from the
    existing peak-strain marker (the two need not coincide, and often
    don't by a small amount near a sharp geometric feature). Caveat
    documented in the function's own docstring: this is a POST-HOC
    reconstruction from the saved U alone, without the solve's own
    angle-continuity state (`th`) -- an element whose REFERENCE
    orientation sits at the arctan2 branch cut (+/-pi) can otherwise
    show a spurious ~2*pi jump. Caught this exact artifact while
    building the feature (a fake ~27 rad/m spike against a ~0.014 rad/m
    nominal design curvature) and fixed it with a branch-wrap correction
    -- reasonable for this application, not a general substitute for
    real `th` tracking. Diagnostic only, wrapped in try/except so it can
    never break a plot.
  + B1 X1-X5 region markers and shroud-extent shading now correctly
    track the DEFORMED shroud location, not just its reference (unde-
    formed) position. Root cause (user-caught: "due to slope of the
    pipeline" -- exactly right): the shroud polygon itself is drawn in
    DEFORMED coordinates (correct -- that's the true physical shape),
    but the X1-X5 edges and extent shading were computed and drawn
    directly in REFERENCE x (matching the model's own internal
    region_peaks/comp_ranges convention, which is unchanged and still
    correct for the underlying data). Wherever the pipe has accumulated
    real rotation/curvature between the anchor and the shroud, those two
    diverge -- confirmed substantial for the case that surfaced it
    (0.79m shift at the taper/plateau kink, clearly visible at the zoom
    levels these plots are meant to be read at). Fixed by mapping each
    reference-x boundary through the SAME reference->deformed
    interpolation the shroud polygon itself already uses, before
    drawing. NOTE: the peak-strain marker, the strain/BM curves
    themselves, and the thick_component boundary markers all have the
    same underlying reference-x-vs-deformed-x character and were NOT
    touched this pass (out of scope this session -- strain-calculation
    exploration paused by user instruction; flagging here so it isn't
    mistaken for an oversight if it surfaces later).


Changes from v1.48:
  + plot_step_deformed() geometry-rendering fixes, found by direct user
    review of zoomed plots (three independent bugs, all visualization-
    layer only -- none touch the solver/physics, so no prior peak_NE/
    peak_x numbers are affected):
    - C1 shroud-over-thick-component double-counting: the shroud's
      roller-contact curve (x_sh/y_sh) was offset using r_local (the
      LOCALLY thick-inflated pipe radius wherever a thick_component
      underlies the shroud) instead of the constant base r_pipe. Per
      COMPONENT_GEOMETRY_DEFINITIONS.md sec2.4, the shroud's own contact
      surface is offset from the pipe CENTRELINE by a fixed amount,
      independent of any local OD growth -- using r_local double-counted
      the thick component's own radius growth on top of the shroud's
      already-correct CL_lift. Confirmed numerically: excess depth was
      exactly r_thick - r_pipe (44mm in the case that surfaced it). Fixed
      in TWO places that both had the same bug independently: the shroud
      fill-polygon contact curve, and the separate roller-marker "off"
      offset calculation in the slot-drawing loop (the second one was
      missed on the first pass -- caught only because the user noticed
      the roller marker still didn't touch the (by-then-corrected) shroud
      body). The roller-marker fix is conditional: only suppress the
      thick_component elevation bump for a roller when that roller ALSO
      falls within the shroud's own span (in_shroud_here check) -- a
      roller under a thick_component with NO shroud overlapping it (the
      A1 case) must still get the full thick-elevated target.
    - B1 shroud taper kinked/truncated: the taper's fill-polygon and its
      axvspan extent-shading were both sampled only at the coarse
      structural FEA mesh nodes -- as few as 1 node landed inside a given
      L2 taper span, which (a) kinked what is actually a single clean
      linear ramp (shroud_offset_at() itself verified correct
      numerically) into an apparent multi-slope shape, (b) truncated the
      taper short of its true flush (V=0) point at the outer edge instead
      of tapering smoothly to zero, and (c) made the shroud-extent
      shading visibly stop before the shroud's true edge. Fixed by
      resampling both on a dense (200-point) grid interpolated against
      the solved reference-x array, independent of structural mesh
      coarseness; the axvspan now uses the analytic ref_centre_x +/- half
      bound directly (same convention already used for the X1-X5
      boundary guideline lines) rather than the coarse mesh extent.
    - A1 roller-elevation: NOT a library bug -- plot_step_deformed's
      roller-marker elevation logic (r_pipe_loc bump for thick_component)
      was already correct; a calling script had left ref_centre_x=None
      for thick-only (no-shroud) cases, which silently disabled it.
      Documented here since it looks like the same class of bug as the
      two above and was investigated as one before being ruled out.
  + Vessel-roller contact convention changed to match the Abaqus
    reference model (user instruction, this session): by default, only
    the 2 vessel rollers nearest SR1 (VR{n_vr-1}, VR{n_vr}) remain
    genuine one-sided (unidirectional) contact, free to release; every
    OTHER vessel roller (VR1..VR{n_vr-2}) is now bidirectional/bilateral
    (no-uplift support) by default -- permanently active, never released.
    Implemented as an auto-default for the existing never_release
    parameter (mechanically: adds those VR names to exempt_set, the same
    mechanism that already existed for the permanently-exempt buffer SR).
    An explicit never_release argument from the caller still overrides
    this default entirely, so no prior call sites break. VR0 (the fixed
    anchor node) is unaffected -- it was never part of the slots/contact
    list to begin with.
  + Anchor/sweep-range investigation (this session, not yet re-validated
    against the paper -- see tech-ref Session 24 section): confirmed
    run_passage_v2's existing SR2-anchor default ("leading edge at SR2")
    is correct and unchanged; confirmed its auto n_shifts sizing
    (round(L_comp/elem_len_sr2)) already implements "sweep until trailing
    edge clears the anchor" with no code change needed. run_passage_
    sliding has NO equivalent auto-sizing (fixed n_shifts=4 regardless of
    shroud length) -- still open, not fixed this session.


Changes from v1.47:
  + PRIMARY STRAIN CONVENTION CHANGED to Abaqus B31-equivalent nodal
    recovery (_strain_profile_b31): element value = mean of our two
    Gauss points, then nodal value = mean of adjacent element values.
    Abaqus B31 has ONE integration point along the axis, so its
    nodal/contour output is IP -> constant extrapolation -> averaging
    over elements sharing the node; the companion paper quotes those
    contour maxima, so this is the like-for-like basis. It reproduces
    the paper to ~4% mean over Batch 1 AND places the peak ON the
    roller node, where Abaqus shows it -- the raw element-centroid
    measure put it half an element away (L/2 = 0.4 m) because a
    per-element value can only be reported at the element midpoint.
    Cubic-Hermite nodal extrapolation was RULED OUT as the paper's
    convention (~88% high); it is kept as peak_NE_nodal, an UPPER
    bracket on the true continuum peak (B31-nodal brackets from below,
    since averaging with a lower neighbour smooths a point-support
    peak). Element-mean retained as peak_NE_elem for continuity with
    all pre-Session-23 reference numbers.
    CONSEQUENCE: the "X1 (taper) governs" finding of earlier Session 23
    was an ARTEFACT of the element-centroid convention. Under B31-nodal
    the peak lands on the roller inside the deep section and X2 governs
    (S2-4 step1: X1=0.666%, X2=0.803%), agreeing with the paper's
    Table XXIX. All X1-X5 findings recorded before this change are
    superseded and must be regenerated.
  + k_spring parameter added to run_passage_v2()/_solve_state(): optional
    low-stiffness BILATERAL spring (N/m, default 0.0 = no change) applied
    at any roller slot currently inactive, along the same normal
    direction/target as the contact formulation but far weaker.
    Regularizes against the singular-tangent-stiffness NaN failure mode
    observed when several rollers release simultaneously during a
    shroud_component sweep (heavy contact release + deep local
    plasticity -- same §12.6 H=0-tangent family as previously
    documented). Magnitude check: 1e7 N/m (10,000 kN/m) sits ~500x below
    typical real beam translational stiffness (~1e9-1e10 N/m) and
    ~7-11 orders of magnitude below the existing contact penalty
    (~1e14-1e18), so it should be negligible wherever contact behaves
    normally -- NOT YET CONFIRMED insensitive at the specific cases that
    triggered the NaN; a k_spring sensitivity sweep is required before
    treating spring-stabilized results as validated (see standing rule:
    verified findings vs. hypotheses kept separate).
  + Type B1 (EA-O offset/shroud) capability added to run_passage_v2() via
    a new `shroud_component` parameter: dict {'V','L1','L2'} (depth,
    deep-section length, taper length -- IJRASET companion paper's Fig.
    44 geometry). PURELY GEOMETRIC: unlike thick_component, the shroud
    does NOT change pipe section (sec_ids stay 1 everywhere) -- it only
    elevates the roller CONTACT TARGET by a trapezoidal profile
    (shroud_offset_at(): full V within |x-centre|<=L1/2, linear ramp to
    0 across each L2, zero beyond). This generalises the existing
    thick-pipe \u00a79.34 CL_lift mechanism (previously coupled 1:1 to an
    OD change) into a free, independent V. Additive with thick_component
    (Type C1, offset+thick pipe) -- CL_lift = thick contribution (if node
    inside thick range) + shroud_offset_at(node_x) (continuous), both
    evaluated per shift so the profile travels with the roller pattern
    exactly like the existing thick-component sweep.
    Which rollers fall inside the flat/ramp zones -- and therefore
    whether contact is single- or dual-roller -- emerges automatically
    from geometry vs. the fixed 8m roller spacing; this is the mechanism
    behind the paper's L1=25D/50D single-to-dual-roller strain-reduction
    finding (Table XXXII) and is NOT special-cased.
  + record() gains region-resolved peak strain (X2/X3/X4, Fig. 45
    convention: X2 = catenary/tip-side third of the deep section, X3 =
    midspan third, X4 = vessel-side third) whenever shroud_component is
    active, evaluated against the CURRENT (shift-adjusted) shroud centre
    -- reported alongside the existing global peak_NE/peak_NE_sr2 fields,
    not replacing them. Requires validation against the paper before
    being treated as load-bearing (see standing rule: verified findings
    vs. hypotheses kept separate).
  + thick_component is now OPTIONAL in run_passage_v2() (shroud_component
    alone is a valid call, e.g. pure Type B1 studies); at least one of
    the two must be provided. component_spacing (2-component Study-3-
    style sweeps) remains thick_component-only for now -- not yet wired
    to shroud_component.
  + SHIFT-DIRECTION INVESTIGATION (Session 23) -- RESOLVED, NO CORE
    CHANGE. A deformed-plot review raised the concern that the component
    travelled the wrong way along the stinger. Re-derived from
    _build_geometry: stations run VR0 (highest x) -> SR_last (most
    negative x) and nodes are numbered along them, so node id increases
    as reference x DECREASES. Under the existing `node = bn - shift`,
    each roller's CONTACT NODE therefore moves toward the VESSEL (+x) in
    the mesh frame -- i.e. in the pipeline's own frame the rollers travel
    vessel-ward / right and the component travels tip-ward / left
    relative to them, which is the correct pay-out sense. Verified
    numerically (SR2 contact node: -7.98 -> -7.18 -> -6.39 -> -5.59 ->
    -4.79 over shifts 0-4). `bn - shift` is CORRECT and is retained.
    An interim attempt to flip this to `bn + shift` was WRONG and has
    been fully reverted (buffer side, exempt_set, x_sr2_now tracking and
    the n_tip_pad experiment all reverted with it); post-revert
    regression on S2-6 reproduces the pre-change numbers exactly
    (0.5056/0.9779/1.2217/1.1829/1.1420). The real defect was in
    plot_step_deformed(), which drew roller markers at their FIXED
    spatial stations rather than at the node each currently constrains,
    so no relative travel was visible at all. Lesson recorded: the
    passage mechanism's direction is invisible in thick_component
    studies (their peak sits at a fixed section-junction kink and is
    direction-invariant), so deformed plots -- not peak numbers -- are
    the only check that exercises it.
  + plot_step_deformed() rebuilt against SLAY_PLOT_STYLE_v2.md with four
    geometry corrections: (1) pipe sits ON the rollers -- centreline
    offset r_pipe (and r_pipe+V under a shroud) along the model normal,
    which the solver targets do NOT include; (2) rollers drawn at the
    node they currently constrain, at uniform 600 mm OD; (3) full pipe
    tube drawn everywhere including under the shroud, simply lifted by
    V; (4) shroud BOTTOM surface (the line actually touching the
    rollers) drawn distinctly from the pipe wall above it. Verified
    numerically: pipe centre above roller centre at every contact,
    centre-to-centre gap = r_pipe + r_roller + V, pipe bottom = contact
    point + V.
  + Divergence guard hardened in _solve_state(): the existing np.isnan(U)
    check is joined by a magnitude check (max|U| > 100m). Found necessary
    (Session 23) when the S2-1 batch run (short shroud footprint, forced
    n_shifts too large for its natural travel) diverged to ~6e24% strain
    while still reporting status='ok' -- a finite-but-insane U passes
    np.isnan() cleanly, so this was a SILENT corruption risk, not just a
    missed NaN. Now reported as 'DIVERGED at inc=... (max|U|=...)',
    correctly failing the status=='ok' check downstream. Lesson: use
    each case's own natural default n_shifts (do not force a uniform
    n_shifts across cases with very different shroud footprints).
  + region_peaks (record()) extended from X2/X3/X4 (plateau thirds) to
    also cover X1/X5 (the taper zones themselves, width L2). Added after
    the S2-6 validation run (Session 23) showed the model's actual
    overall peak strain sits in the taper, not the plateau (x=-6.785 vs.
    plateau boundary at -5.951) -- the same junction-kink mechanism
    already documented for thick components (§9.34): a sharp linear-
    taper/plateau corner concentrates curvature there. This is a live
    open question, not yet resolved: does the real (paper) shroud
    geometry use a smoother taper transition, making our sharp corner an
    artifact that inflates the peak vs. real behaviour? Flagged for
    follow-up (candidate fix: blend/fillet the shroud_offset_at() corner
    instead of a sharp linear-to-flat transition) -- not yet attempted.

VERSION: 1.47  (Session 20, 22 Jul 2026)
Changes from v1.45:
  + MERGED IN: the validated fixed-mesh CHAINED passage sweep
    (slay_passage_v2.py v2.00) as run_passage_v2() + private helpers,
    appended at the end of this file. Tech reference \u00a712.7-12.9 have
    the full architecture, validation-caught bugs, and results.
    J2-only; U/theta/PlasticState/active-set form one continuous chain;
    nlfea_v4 untouched.
  + _moment_profile() added: fibre-stress-integrated bending moment per
    element, matching get_moment_profile()'s own convention (GP index 0,
    _ep_return_mapping). record() reports peak_M / peak_M_x alongside
    peak_NE. Validated across Study 1/2/3 vs the published paper: moment
    agrees within ~3-10% throughout; strain deviates far more (+21.8%
    down to -36.6%), worst at R=70 and growing with component length --
    consistent with strain being more locally sensitive to modelling
    differences than the more-integrated moment (\u00a712.8).
  + component_spacing parameter added to run_passage_v2() (\u00a712.9):
    builds a 2nd identical component with a clear gap beyond the 1st,
    for two-component (Study 3) sweeps. Straight generalisation of the
    existing single-component machinery (sec_ids, self-weight, \u00a79.34
    roller offset all now accept multiple component ranges); mesh-extent
    check fails loudly rather than truncating silently. Regression-
    checked: single-component calls unaffected, bit-for-bit.
  + The OLD run_passage() (independent unchained solves) is retained
    unchanged. run_slay()'s experimental initial_* chaining parameters
    remain but are NOT the supported chaining path -- use
    run_passage_v2() for chained sweeps.

VERSION: 1.45  (Session 20, 21 Jul 2026)  -- PARTIAL: see status below
Changes from v1.44:
  + Plastic-state chaining across run_passage() sweep positions -- STARTED
    but NOT completed/working this session. See technical reference §12.6
    for the full debugging record. Status:
      - Root problem correctly diagnosed: each sweep position was an
        independent monotonic solve from virgin (zero) plastic strain,
        confirmed (not assumed) by inspecting run_slay()'s PlasticState
        instantiation. Likely a real contributor to the systematic
        length-dependent strain under-prediction vs. the IJRASET paper
        (technical reference §12.2-12.3).
      - New run_slay() parameters initial_plastic_state, initial_sec_ids
        implemented and VERIFIED WORKING (via debug trace) for warm-
        starting J2 plastic state, with masking against element
        section-type flips (plain<->thick) done safely INSIDE run_slay()
        right after sec_ids is computed (zero risk of external/predicted-
        sec_ids misalignment).
      - TWO real pre-existing bugs found and fixed along the way:
        initial_plastic_state/initial_sec_ids/initial_U were all silently
        DROPPED by the elastic_first=True two-step dispatch (Step 2 never
        forwarded them to the recursive run_slay() call). This means
        warm_start=True in run_passage has been silently non-functional
        this ENTIRE session (elastic_first defaults True), independent of
        the new chaining work. Now fixed.
      - UNRESOLVED: even with both initial_U and initial_plastic_state
        correctly reaching the solve, seeding a nonzero starting plastic
        state produces a SINGULAR tangent stiffness matrix at increment 1
        and the solve fails SILENTLY (phase1_peak=0.0, no exception).
        Root cause not identified -- likely something in how the
        elastic-trial-stress / contact-penalty interaction handles a
        nonzero eps_p baseline, but not confirmed.
      - chain_plastic_state parameter added to run_passage() but DEFAULTS
        TO FALSE for this reason -- do not set True until the singularity
        is fixed. All Session 20 sweep results (Study 1, Study 2) were
        run WITHOUT chaining (chain_plastic_state=False / not yet existing)
        and remain valid; nothing already reported is affected by this
        unresolved item.
  + Planned follow-up: a temporary v1.45T branch dedicated to resolving
    the singularity, kept separate from this stable v1.45 baseline.
  + UPDATE (same session, continued debugging): root cause #1 identified
    and fixed -- the load ramp restarting from near-zero while U is
    warm-started to a fully-loaded state created a massive Fint/Fext
    imbalance. Fix: single full-load (lam=1.0) "continuation" step used
    automatically whenever both initial_U and initial_plastic_state are
    supplied, instead of the normal incremental ramp. This is real and
    kept. HOWEVER a second, distinct root cause remains: the tangent
    stiffness matrix is already near-singular (one DOF's diagonal ~3.7e-24)
    at the very FIRST assemble() call, before any Newton iteration --
    not a divergence artifact. A hardening-table-plateau hypothesis was
    checked and ruled out (table slope never drops below ~638 MPa). See
    technical reference §12.6a for full detail and next-session leads.
    chain_plastic_state still defaults to False.

VERSION: 1.44  (Session 20, 21 Jul 2026)
Changes from v1.43:
  + run_passage() default sweep convention changed AGAIN this session
    (superseding the v1.43 SR1-to-SR2/SR3-midspan default, which was
    itself only briefly the default). New default: component centre
    sweeps from [SR2 + L/2] (leading edge reaches SR2) to [SR2 - L/2]
    (trailing edge leaves SR2) -- i.e. sweep span = component length,
    centred on SR2. This isolates the actual roller-component contact
    interaction rather than a large low-signal region, and is both
    faster and better targeted than the SR1-to-midspan default.
  + New `step_size` parameter (default 0.5 m) controls sweep resolution
    directly; n_steps is now optional and computed from step_size and
    the x_start/x_end span if not given explicitly. x_start/x_end can
    still be overridden for a custom-range sweep, or set equal (with
    n_steps=1) for a single-position study.

VERSION: 1.43  (Session 20, 21 Jul 2026)
Changes from v1.42:
  + Self-weight fix: self_weight=True now applies per-element weight based
    on the section actually assigned to that element (sec_ids) instead of
    plain-pipe cross-sectional area for every element. Thick-component
    elements previously carried plain-pipe self-weight, understating the
    load driving heavy/long thick sections onto their rollers. Fixed in
    both load-assembly blocks (the Model-level body_forces list and the
    main-solve dist dict).
  + New get_moment_profile(res) function: computes bending moment M(x) per
    user element via full fibre-stress integration at the committed
    plastic state, M = sum(sigma_i * y_i * A_i). More accurate than a
    linear-elastic EI*kappa estimate for J2/RO inelastic elements. Not
    called automatically by run_slay() (extra cost); call explicitly on a
    result dict. Merged from the standalone moment_profile.py helper.
  + Confirmed (not fixed): run_passage() / repeated run_slay() calls at
    different centre_x do NOT chain plastic state between positions --
    each sweep position is an independent monotonic solve from zero
    plastic strain. warm_start=True only carries the displacement vector
    U, never PlasticState. Flagged as the likely dominant cause of
    systematic under-prediction vs. Abaqus sliding-passage results for
    long (>=10D) thick components -- see technical reference §12.2-12.3.

VERSION: 1.42  (Session 19, 15 Jul 2026)
Changes from v1.41:
  + New `section` parameter: 'polar' (DEFAULT) or 'fibre'.
    'polar' -- PipeSectionPolar, Abaqus-aligned thin-wall angular
    integration, n_points_polar points (default 8 = Abaqus B31/PIPE
    default section). Use this to compare against Abaqus results run
    with the default PIPE section (the common case in practice).
    'fibre' -- PipeSection, converged Cartesian through-wall fibre
    integration (n_fibres points, default 20; was the only option and
    the implicit default through v1.41). More accurate vs. an S4R shell
    reference in deep plasticity, but does not reproduce Abaqus's
    default-PIPE under-integration behaviour.
    n_points_polar is independent of n_fibres -- conflating the two
    would either mis-size the J2 PlasticState array or silently use the
    wrong point count for the Abaqus comparison this option exists for.
  + Depends on the nlfea_v4.py fix (same session) to
    FEARunner.get_element_strains(): the extreme-fibre radius r_o was
    previously reconstructed from fibre spacing (exact for the
    Cartesian fibre model by construction, but silently ~28% too large
    for the polar/angular model, whose fibre y-values are r_mid*sin(theta)
    and never reach the true r_o). Fixed to use sec.r_o directly
    (section-type-agnostic, reproduces the old fibre-model value exactly,
    corrects the polar-model value). This slay_overbend version REQUIRES
    the patched nlfea_v4.py -- running section='polar' against the
    unpatched nlfea_v4.py will silently over-report strain by ~28%.

v1.41 changes (Session 19, 15 Jul 2026), retained below:
  + Switched from nlfea_v3 to nlfea_v4. Adds material='J2' option:
    IncrementalIsotropic.abaqus_steel_nl_verified() -- the 360 MPa,
    31-point true-stress/true-plastic-strain table transcribed directly
    from the *PLASTIC block of the verified Abaqus source model (see
    "AI-Assisted Extension of a Nonlinear FEA Program to Material
    Plasticity", IJRASET Vol.14 Issue VII, July 2026). Replaces the old
    'RO' path (FFS 579-1 Ramberg-Osgood, 450 MPa SMYS deformation
    plasticity) for any run where accumulated/path-dependent plastic
    strain or a direct comparison against the verified Abaqus material
    is required. 'RO' and 'elastic' options are unchanged and remain
    available (material='RO' is still the default for existing callers).
  + Plastic state (nlfea_v4.PlasticState) is threaded through the
    bespoke Newton + one-sided-contact solve loop: frozen at the start
    of each load increment (across all active-set passes at that
    increment), committed only once the increment's contact state has
    converged. This mirrors nlfea_v4.solve_step()'s commit discipline.
    The tensile-lift-off cascade (which restarts the increment loop
    from U=0 with a reduced active roller set) resets and re-accumulates
    plastic state from zero on each restart, consistent with it being a
    full re-solve of the same monotonic load path.
  + assemble() now returns a 5-tuple (K, Fint, Fext, theta, plastic_state)
    in nlfea_v4, vs. the 4-tuple in nlfea_v3. All internal call sites
    updated accordingly.
  + run_slay() result dict gains 'plastic_state' (nlfea_v4.PlasticState,
    None for 'RO'/'elastic') and 'material' keys. Plastic state is NOT
    currently chained between run_passage() steps -- each passage
    position is still an independent monotonic solve from zero plastic
    strain (matching the Abaqus static/Phase-1 benchmark tables this
    version was built to compare against). True moving-support history
    chaining (as in the plasticity paper's Benchmark 3) is a possible
    future extension, not implemented here.
  + elastic_first two-step dispatch: Step 2 now uses the requested
    `material` (was hardcoded to 'RO' in v1.40, silently ignoring a
    caller-supplied 'J2'). Docstring's claim of raising ValueError for
    material != 'RO' did not match the v1.40 implementation; corrected.

v1.40 changes (Session 17g, 10 Jun 2026), retained below:
  + §9.34 contact BC correction for thick pipe sections.
    V convention: V = OD/2 (CL to contact surface, downward).
    Plain pipe:  V = D_o/2  → CL_lift = 0.
    Thick pipe:  V = OD_thick/2  → CL_lift = OD_thick/2 - D_o/2 > 0.
    Auto-applied to all stinger radial rollers (SR2+) and vessel rollers
    (VR1-VR3, SR1) whose x-position falls within the thick component span.
    User-provided roller_offsets / vessel_offsets take priority.
    Previously: CL_lift = 0 for all rollers unless explicitly set →
    thick pipe section was forced to same contact level as plain pipe (WRONG).

v1.39 functionality is unchanged.

Uses nlfea_v3 (CR-TL + Ramberg-Osgood + PipeSection + 2-point Gauss).

Modelling convention v1.0 (see NLFEA SKILL.md for full details):
  - Stinger on LEFT, vessel deck on RIGHT
  - SR1 at origin (0,0); X positive LEFT; Y positive DOWN
  - 6 stinger rollers (SR1-SR6) + 3 vessel rollers (VR1-VR3), 8m arc spacing
  - Vessel rollers:  uy = 0 (perpendicular to deck)
  - Stinger rollers: RADIAL constraint, OUTWARD normal n_hat = (-sinθ, -cosθ)
                     pointing TOWARD sea surface (away from arc centre).
                     Contact when pipe is at or below roller surface.
                     Lift-off when pipe rises above roller surface.
  - Model terminates at SR6 (no catenary)
  - Report Phase 1 strains only (VR1..SR3); ignore boundary zone beyond SR3

Key principle (Session 13):
  This is a kinematic prescribed-displacement model, not a gravity-driven
  contact model. Conclusions must follow from the model's actual behaviour,
  verified independently — not forced to match Abaqus results.

Self-weight (Session 15):
  self_weight=True is the correct default for S-Lay overbend analysis.
  In-air pipe weight drives the pipe onto the rollers and is essential for
  physically correct contact distribution. Without self-weight, contact is
  driven by geometry and tension alone, giving incorrect reaction signs
  (tensile reactions at vessel rollers that should be in compression).

VR0 anchor node (v1.37, Session 15):
  A fixed anchor node VR0 is placed one roller spacing inboard of VR1, deep
  inside the vessel. All three DOFs (ux, uy, rz) are fixed at VR0. This
  represents the pipeline clamped/fixed on the vessel deck, well inboard of
  the active roller region. With this true structural anchor in place:
  - VR1, VR2, VR3, SR1 are ALL pure contact rollers with no fixed DOFs.
  - All vessel rollers including VR1 can lift off freely based on physics.
  - The 'last active vessel roller' safeguard is no longer needed.
  Physical principle: the pipeline is anchored on the vessel, not at VR1.
  Forcing VR1 to stay active was an artificial constraint; in reality the
  pipe is continuous and the anchor is the tensioner/vessel deck, not VR1.

roller_offsets V convention (v1.35, Session 13 confirmed):
  V_abaqus = distance from pipeline C/L DOWNWARD to roller contact surface.
  Baseline (no shroud): V_abaqus = D_o/2 (pipe C/L is OD/2 above roller).
  Code converts: CL_lift = V_abaqus - D_o/2.
  Examples for 16" pipe (D_o=406.4mm):
    V=D_o   (406mm) → CL_lift=203mm=0.5D
    V=1.5D  (610mm) → CL_lift=406mm=1.0D
    V=2D    (813mm) → CL_lift=610mm=1.5D

Contact model corrections in v1.30:
  1. Normal direction: OUTWARD n_hat = (-sinθ, -cosθ), toward sea surface.
     Physical: stinger rollers push pipe toward surface (outward), not inward.
     Bilateral strain results unchanged (bilateral is direction-invariant).
  2. One-sided condition: physical convention.
     Contact ACTIVE  when rn = dn*lam - u_out >= 0  (pipe at or below roller surface).
     LIFT-OFF        when rn < -threshold             (pipe above roller surface).
     RE-CONTACT      when rn >= 0                     (pipe returns to roller level).
     Re-activation is checked every active-set pass, even after previous deactivation.
  3. Shroud dn: target y = arc_y - V (correct vertical lift).
     Old: extra was radial offset (dn_old = arc_y*cosθ - V_radial).
     New: dn = (arc_y - V)*(-cosθ) — accurate for any V including V > arc_y.
     Large V (V > arc_y): pipe above vessel deck level — physically correct
     (shroud sticks above deck). Contact established from increment 1.

Default case: R=85m, 16"x21mm DNV 450, no tension, no self-weight.

KEY NUMERICS:
  - Two-point Gauss integration with independent EI_t per Gauss point.
    This regularises strain localisation (essential for softening R-O).
    Without it, peak strain diverges with mesh refinement.
  - Newton-Raphson incremental solver (NOT Riks - this is displacement
    controlled, Riks reference load is dominated by penalty forces).
"""

import os
import numpy as np
from scipy.sparse.linalg import spsolve
from nlfea_v4 import (Model, Node, PipeSection, PipeSectionPolar, Section,
                       RambergOsgood, Material, IncrementalIsotropic, PlasticState,
                       UserElement, BoundaryCondition,
                       BodyForce, JointLoad, FEARunner,
                       MeshedStructure, assemble,
                       _ep_return_mapping, _ro_stress)

# ---- Defaults ----
G          = 9.81
RHO_STEEL  = 7850.0
D_O_DEF    = 0.4064     # 16"
T_W_DEF    = 0.021      # 21 mm
R_DEF      = 85.0       # stinger radius
SPACING    = 8.0        # arc spacing
N_SR       = 6          # stinger rollers (default 6)
N_VR       = 3          # vessel rollers VR1-VR3 (contact only, no fixed DOFs)
# VR0 is added automatically as anchor node (1 spacing inboard of VR1, all DOFs fixed)
EPE_DEF    = 4          # elements per span
EPS_RD     = 0.01543    # DNV DCC Medium SC


def build_geometry(R, n_sr=N_SR, n_vr=N_VR, spacing=SPACING, epe=None, D_o=D_O_DEF):
    """Return roller coords, node list, roller node-id map.

    Mesh density: if epe is None, element length defaults to 2 x pipe OD.
    Elements per span = round(spacing / (2 * D_o)).

    Node layout (left to right = stinger to vessel):
      VR0 — anchor node, 1 spacing inboard of VR1, all DOFs fixed (v1.37)
      VR1, VR2, VR3 — vessel contact rollers, can lift off
      SR1 — first stinger roller (contact, vertical)
      SR2..SR_n — stinger radial rollers
    rnid keys: 0=VR0, 1=VR1, 2=VR2, 3=VR3, 4=SR1, 5=SR2, ...
    """
    if epe is None:
        elem_len = 2.0 * D_o
        epe = max(1, int(round(spacing / elem_len)))
    dtheta = spacing / R
    # VR0 is one spacing further inboard than VR1
    vr0 = [(+(4 - j) * spacing, 0.0) for j in range(0, n_vr + 1)]  # VR0..VR3
    sr  = [(-R * np.sin((i - 1) * dtheta),
             R * (1 - np.cos((i - 1) * dtheta))) for i in range(1, n_sr + 1)]
    allc = vr0 + sr   # VR0, VR1, VR2, VR3, SR1, SR2, ...
    nsp = len(allc) - 1

    nodes = []; nid = 1; rnid = {}
    for s in range(nsp):
        x0, y0 = allc[s]; x1, y1 = allc[s + 1]
        for k in range(epe):
            f = k / epe
            nodes.append(Node(nid, x0 + f * (x1 - x0), 0.0))
            if k == 0:
                rnid[s] = nid
            nid += 1
    nodes.append(Node(nid, allc[-1][0], 0.0))
    rnid[nsp] = nid
    # rnid[0]=VR0, rnid[1]=VR1, ..., rnid[n_vr]=VR3, rnid[n_vr+1]=SR1, rnid[n_vr+2]=SR2 ...
    return allc, sr, nodes, rnid, nsp, nid, dtheta


def run_slay(R=R_DEF, D_o=D_O_DEF, t=T_W_DEF, n_sr=N_SR, epe=None,
             material='RO', tension_mt=0.0, self_weight=True,
             one_sided=False, n_increments=40, n_fibres=20, verbose=True,
             roller_offsets=None, thick_component=None,
             initial_U=None, elastic_first=False,
             _elastic_lifted_seed=None,
             vessel_offsets=None,
             section='polar', n_points_polar=8,
             initial_plastic_state=None, initial_sec_ids=None):
    """
    Run the S-Lay overbend model.

    material        : 'RO' (Ramberg-Osgood, FFS 579-1, 450 MPa SMYS, deformation
                      plasticity -- path-independent), 'J2' (IncrementalIsotropic,
                      verified 360 MPa 31-point tabular material, incremental
                      plasticity -- path-dependent, freezes plastic strain on
                      unloading), or 'elastic'.
    section         : 'polar' (default, v1.41) -- PipeSectionPolar, thin-wall
                      angular integration at r_mid, n_points_polar points
                      (default 8 = Abaqus B31/PIPE default section). Use this
                      to compare against Abaqus results run with the default
                      PIPE section, which is the common case in practice.
                      'fibre' -- PipeSection, converged Cartesian through-wall
                      fibre integration (n_fibres points, default 20). More
                      accurate vs. an S4R shell reference (see the companion
                      plasticity paper), but does NOT reproduce Abaqus's
                      default-PIPE under-integration behaviour in deep
                      plasticity. Applies to both the plain pipe and any
                      thick_component section.
    n_points_polar  : angular integration points for section='polar' (default
                      8, matching Abaqus B31/PIPE default). Independent of
                      n_fibres, which only applies when section='fibre'.
                      Increasing this converges toward the fibre-model answer
                      (16-64 points; see plasticity paper Table 1/Table 2) --
                      use n_points_polar=64 to approximate a "well-resolved
                      PIPE section" rather than Abaqus's coarse default.
    tension_mt      : lay tension in metric tonnes (0 = none)
    self_weight     : include in-air self weight (default True — required for
                      correct contact distribution; see module header physics note)
    one_sided       : if True, stinger rollers are one-sided contact (lift-off
                      allowed). Active-set iteration deactivates any roller
                      whose reaction turns tensile. If False, bilateral.
    epe             : elements per 8m span (default: element length = 2*OD)
    vessel_offsets  : dict — elevated V_abaqus at vessel/SR1 rollers.
                      Keys: 'VR1','VR2','VR3','SR1'. Values: V_abaqus_m.
                      CL_lift = V_abaqus - D_o/2. Default: all zero (natural deck level).
                      Used for shroud-spanning assemblies where the shroud elevates
                      the contact surface at SR1 (and optionally VR rollers).
    roller_offsets  : dict {sl: V_abaqus_m} — Abaqus V at stinger roller sl.
                      sl=1=SR2, sl=2=SR3, ...
                      V_abaqus = distance from pipeline C/L downward to roller
                      contact surface (confirmed Abaqus convention).
                      Baseline (no shroud): V_abaqus = D_o/2.
                      Internally: CL_lift = V_abaqus - D_o/2.
                      Absent = normal contact (CL_lift = 0).
    thick_component : dict defining an inline thick component, or None.
    initial_U       : np.ndarray — warm-start displacement vector. When provided
                      the incremental solve begins from this state. Used by
                      elastic_first mode (Step 2 starts from elastic solution).
    initial_plastic_state : PlasticState — v1.45, Session 20. Warm-start the
                      J2 plastic state (eps_p, kap per fibre) from a PRIOR
                      run_slay() call, for chaining plastic strain history
                      across a passage sweep (physically: the pipe carries
                      residual plastic strain from earlier rollers into its
                      interaction with later ones). Only valid for
                      material='J2'; ignored otherwise. The mesh node grid is
                      fixed regardless of thick_component position (only
                      sec_ids per element changes), so element-index-wise
                      carryover is exact wherever an element's section type
                      (plain vs thick) is unchanged between the two calls.
                      Caller (run_passage) is responsible for masking to zero
                      any element whose section type changed, since fibre
                      geometry differs between plain and thick sections.
    elastic_first   : bool — two-step method:
                        Step 1: run with 'elastic' material → contact topology
                        Step 2: from elastic U, switch to 'RO', converge material
                      Returns result dict with extra keys:
                        'step1' : elastic result dict
                        'step2' : nonlinear result dict (same as top-level return)
                      Step 2 uses whatever `material` was passed in ('RO' or
                      'J2'); Step 1 (contact-topology pass) always uses
                      'elastic' regardless of the requested Step 2 material.

    Returns dict with displacements, strain profile, peak Phase-1 strain,
    and thick_elems list (user element IDs in thick zone, empty if None).
    """
    # ── elastic_first two-step dispatch ───────────────────────────────────
    # Step 1: elastic one-sided solve → determines contact state (which rollers lift off).
    # Step 2: RO solve from U=0 but with those rollers SEEDED as inactive from the start.
    # Benefit: no Newton iterations ever visit the wrong contact topology, so no
    # spurious plasticity accumulates during the initial deformation build-up.
    if elastic_first:
        r1 = run_slay(R=R, D_o=D_o, t=t, n_sr=n_sr, epe=epe,
                      material='elastic', tension_mt=tension_mt,
                      self_weight=self_weight, one_sided=True,
                      n_increments=n_increments, n_fibres=n_fibres,
                      verbose=False, roller_offsets=roller_offsets,
                      thick_component=thick_component,
                      vessel_offsets=vessel_offsets,
                      section=section, n_points_polar=n_points_polar)
        elastic_lifted = set(r1['inactive_rollers'])
        if verbose:
            print(f"  [elastic_first] Step 1 (elastic): "
                  f"peak={r1['phase1_peak']*100:.4f}%  lifted={r1['inactive_rollers']}")
        r2 = run_slay(R=R, D_o=D_o, t=t, n_sr=n_sr, epe=epe,
                      material=material, tension_mt=tension_mt,
                      self_weight=self_weight, one_sided=one_sided,
                      n_increments=n_increments, n_fibres=n_fibres,
                      verbose=False, roller_offsets=roller_offsets,
                      thick_component=thick_component,
                      vessel_offsets=vessel_offsets,
                      section=section, n_points_polar=n_points_polar,
                      _elastic_lifted_seed=elastic_lifted,
                      initial_plastic_state=initial_plastic_state,
                      initial_sec_ids=initial_sec_ids,
                      initial_U=initial_U)
        if verbose:
            print(f"  [elastic_first] Step 2 (RO, seeded): "
                  f"peak={r2['phase1_peak']*100:.4f}%  lifted={r2['inactive_rollers']}")
        r2['step1'] = r1
        return r2

    allc, sr, nodes, rnid, nsp, nn, dtheta = build_geometry(
        R, n_sr, N_VR, SPACING, epe, D_o)
    # resolve actual epe used (for strain profile indexing)
    epe = (nn - 1) // nsp

    is_ep = (material == 'J2')

    # v1.41: PipeSection (converged Cartesian fibre) vs PipeSectionPolar
    # (Abaqus-aligned thin-wall angular, default 8pt). n_fib_active is the
    # ACTUAL number of section integration points in use -- used to size
    # PlasticState correctly. This is NOT the same as n_fibres when
    # section='polar' (n_points_polar governs instead); conflating the two
    # would either mis-size PlasticState or silently use the wrong point
    # count for the Abaqus comparison this option exists for.
    if section == 'polar':
        n_fib_active = n_points_polar
        def _make_pipe_section(sid, OD, WT):
            return PipeSectionPolar(id=sid, D_o=OD, t=WT, n_fibres=n_points_polar)
    else:
        n_fib_active = n_fibres
        def _make_pipe_section(sid, OD, WT):
            return PipeSection(id=sid, D_o=OD, t=WT, n_fibres=n_fibres)

    if material == 'RO':
        SEC = _make_pipe_section(1, D_o, t)
        MAT = RambergOsgood.from_ffs579(id=1, E=207e9, sig_ys=450e6)
    elif material == 'J2':
        # Verified 360 MPa, 31-point true-stress/true-plastic-strain table,
        # transcribed directly from the source Abaqus *PLASTIC block.
        # Incremental (path-dependent) J2 plasticity -- see nlfea_v4
        # IncrementalIsotropic.abaqus_steel_nl_verified() docstring.
        SEC = _make_pipe_section(1, D_o, t)
        MAT = IncrementalIsotropic.abaqus_steel_nl_verified(id=1)
    else:
        A = np.pi/4*(D_o**2 - (D_o-2*t)**2)
        I = np.pi/64*(D_o**4 - (D_o-2*t)**4)
        d_eq = np.sqrt(12*I/A); b_eq = A/d_eq
        SEC = Section(id=1, b=b_eq, d=d_eq)
        MAT = Material(id=1, E=207e9)

    # ── Thick component section (optional) ───────────────────────────────
    sections = [SEC]
    thick_elems = []
    if thick_component is not None:
        tc = thick_component
        cx  = tc['centre_x']
        lc  = tc['length']
        if material in ('RO', 'J2'):
            SEC2 = _make_pipe_section(2, tc['OD'], tc['t'])
        else:
            A2 = np.pi/4*(tc['OD']**2-(tc['OD']-2*tc['t'])**2)
            I2 = np.pi/64*(tc['OD']**4-(tc['OD']-2*tc['t'])**4)
            d2 = np.sqrt(12*I2/A2); b2 = A2/d2
            SEC2 = Section(id=2, b=b2, d=d2)
        sections.append(SEC2)

    # Assign section id per element
    xn     = np.array([n.x for n in nodes])
    x_mids_arr = 0.5*(xn[:-1]+xn[1:])
    sec_ids = []
    for ex in x_mids_arr:
        if thick_component is not None and abs(ex - cx) <= lc/2:
            sec_ids.append(2)
        else:
            sec_ids.append(1)

    # Collect thick element user IDs
    if thick_component is not None:
        thick_elems = [i+1 for i, sid in enumerate(sec_ids) if sid == 2]

    # v1.45 (Session 20): mask the carried-forward plastic state against
    # THIS solve's authoritative sec_ids. Done here (not by the caller)
    # so there is zero risk of misalignment between the sec_ids array used
    # for masking and the one actually assigned to elements below -- both
    # come from the exact same array in the exact same order.
    if initial_plastic_state is not None and initial_sec_ids is not None:
        sec_ids_arr = np.array(sec_ids)
        prev_arr    = np.array(initial_sec_ids)
        if len(sec_ids_arr) == len(prev_arr):
            flip_mask = (sec_ids_arr != prev_arr)
            if flip_mask.any():
                initial_plastic_state = initial_plastic_state.copy()
                initial_plastic_state.eps_p[flip_mask, :, :] = 0.0
                initial_plastic_state.kap[flip_mask, :, :]   = 0.0
        # else: length mismatch (different mesh) -- carryover not meaningful,
        # fall through to run_slay's own zero-init of ps_committed.

    els = [UserElement(i, i, i+1, 1, sec_ids[i-1]) for i in range(1, nn)]

    # BCs: VR0 anchor — all three DOFs fixed (ux, uy, rz).
    # This is the vessel deck anchor, well inboard of all contact rollers.
    # VR1-VR3 and SR1 have NO fixed BCs — they are pure contact constraints only.
    # All vessel rollers including VR1 can lift off freely (v1.37).
    bcs = []; bid = 1
    bcs.append(BoundaryCondition(bid, rnid[0], 1, 0.0, 1, 1)); bid += 1   # VR0 ux=0
    bcs.append(BoundaryCondition(bid, rnid[0], 2, 0.0, 1, 1)); bid += 1   # VR0 uy=0
    bcs.append(BoundaryCondition(bid, rnid[0], 3, 0.0, 1, 1)); bid += 1   # VR0 rz=0

    body_forces = []
    if self_weight:
        # v1.43 fix: per-element self-weight based on the section actually
        # assigned to that element (sec_ids), not the plain-pipe area for
        # every element. Thick-component elements previously carried
        # plain-pipe weight, understating the load driving the (larger,
        # heavier) thick section onto its rollers.
        A_plain = np.pi/4*(D_o**2 - (D_o-2*t)**2)
        w_plain = RHO_STEEL * A_plain * G
        if thick_component is not None:
            A_thick = np.pi/4*(tc['OD']**2 - (tc['OD']-2*tc['t'])**2)
            w_thick = RHO_STEEL * A_thick * G
        else:
            w_thick = w_plain
        body_forces = [
            BodyForce(e.id, e.id, 0.0,
                      (w_thick if sec_ids[e.id-1] == 2 else w_plain), 1, 1)
            for e in els
        ]

    joint_loads = []
    if tension_mt > 0:
        T_N = tension_mt * 1e3 * G
        theta_n = (n_sr - 1) * dtheta
        joint_loads = [JointLoad(1, nn, Fx=-T_N*np.cos(theta_n),
                                  Fy=+T_N*np.sin(theta_n), Mz=0.0,
                                  step_start=1, step_end=1)]

    model = Model(nodes=nodes, elements=els, sections=sections, materials=[MAT],
                  joint_loads=joint_loads, body_forces=body_forces,
                  bcs=bcs, n_steps=1)
    mesh = MeshedStructure(model)

    # §9.34 correction (v1.40): auto-elevate roller contact for thick pipe sections.
    # V convention: V_abaqus = CL to roller contact surface (downward, m).
    # Plain pipe:  V_abaqus = D_o/2  → CL_lift = 0  (CL on natural stinger arc).
    # Thick pipe:  V_abaqus = OD_thick/2  → CL_lift = OD_thick/2 - D_o/2 > 0.
    # For any roller whose x-position falls within the thick component span,
    # the contact BC must use OD_thick/2 (not D_o/2).
    # User-provided roller_offsets take priority over auto-computed values.
    # Formula: V = OD/2 = (ID + 2*WT)/2 = 182 + WT  [mm]  for ID=364mm.
    _ro = dict(roller_offsets or {})
    if thick_component is not None:
        _tc_OD = tc['OD']
        for _sl in range(1, n_sr):          # SR2..SR_n (sr[_sl] gives SR_{_sl+1})
            if _sl not in _ro:
                _rx = sr[_sl][0]            # x-coord of stinger roller
                if abs(_rx - cx) <= lc / 2:
                    _ro[_sl] = _tc_OD / 2  # V_abaqus = OD_thick/2

    # Radial BCs for SR2..SR_nsr
    # rnid keys: 0=VR0, 1=VR1, 2=VR2, 3=VR3, 4=SR1, 5=SR2, 6=SR3, ...
    # SR1 is at rnid[N_VR+1], SR2 at rnid[N_VR+2], SR_sl at rnid[N_VR+sl+1]
    # (N_VR=3, so SR1=rnid[4], SR2=rnid[5], ...)
    radial = []
    for sl in range(1, n_sr):
        theta = sl * dtheta
        nx = -np.sin(theta)
        ny = -np.cos(theta)
        V_abaqus = _ro.get(sl, None)        # uses auto-corrected _ro (§9.34)
        if V_abaqus is not None:
            CL_lift = V_abaqus - D_o / 2
        else:
            CL_lift = 0.0
        dn = sr[sl][1] * ny + CL_lift
        mi = mesh.user_node_to_mesh[rnid[N_VR + sl + 1]]   # +1 for VR0 offset
        radial.append((3*mi, 3*mi+1, nx, ny, dn, sl))

    # Vessel rollers VR1-VR3 + SR1 — vertical upward contact (one-sided).
    # rnid: VR1=rnid[1], VR2=rnid[2], VR3=rnid[3], SR1=rnid[4]
    # All are pure contact constraints. No fixed BCs on any of these.
    # All can lift off freely via tensile check (v1.37).
    # vessel_offsets: keys 'VR1','VR2','VR3','SR1' → V_abaqus (CL to contact surface)
    # dn_vessel = CL_lift = V_abaqus - D_o/2 (positive = contact surface above natural y=0)
    # §9.34: auto-elevate vessel roller contact for thick sections (same logic as _ro above).
    _vo = dict(vessel_offsets or {})
    if thick_component is not None:
        _tc_OD = tc['OD']
        _vnames_xcoords = [
            ('VR1', allc[1][0]),
            ('VR2', allc[2][0]),
            ('VR3', allc[3][0]),
            ('SR1', allc[N_VR + 1][0]),
        ]
        for _vname, _vx in _vnames_xcoords:
            if _vname not in _vo:
                if abs(_vx - cx) <= lc / 2:
                    _vo[_vname] = _tc_OD / 2
    _vr_names = ['VR1','VR2','VR3']
    vessel = []
    for vi in range(1, N_VR + 1):   # VR1=1, VR2=2, VR3=3
        mi_v = mesh.user_node_to_mesh[rnid[vi]]
        V_vr = _vo.get(_vr_names[vi-1], D_o/2)
        dn_vr = V_vr - D_o/2   # CL lift; 0.0 for natural position
        vessel.append((3*mi_v+1, 0.0, -1.0, dn_vr))
    # SR1 — rnid[N_VR+1] = rnid[4]
    mi_sr1 = mesh.user_node_to_mesh[rnid[N_VR + 1]]
    V_sr1 = _vo.get('SR1', D_o/2)
    dn_sr1 = V_sr1 - D_o/2
    vessel.append((3*mi_sr1+1, 0.0, -1.0, dn_sr1))

    std = []
    for bc in bcs:
        mi2 = mesh.user_node_to_mesh[bc.node_id]
        std.append((3*mi2 + (bc.dof - 1), bc.value))

    # Prepare load dicts for assemble
    dist = {}
    if self_weight:
        # v1.43 fix: per-element weight from the section actually assigned
        # to that element (sec_ids) — thick component elements now carry
        # their own (larger) self-weight instead of the plain-pipe value.
        A_plain = np.pi/4*(D_o**2 - (D_o-2*t)**2)
        w_plain = RHO_STEEL * A_plain * G
        if thick_component is not None:
            A_thick = np.pi/4*(tc['OD']**2 - (tc['OD']-2*tc['t'])**2)
            w_thick = RHO_STEEL * A_thick * G
        else:
            w_thick = w_plain
        for e in els:
            w_e = w_thick if sec_ids[e.id-1] == 2 else w_plain
            dist[mesh.user_elem_to_mesh[e.id][0] if hasattr(mesh,'user_elem_to_mesh') else e.id-1] = (0.0, w_e)
    jl_list = []
    if tension_mt > 0:
        T_N = tension_mt * 1e3 * G
        theta_n = (n_sr - 1) * dtheta
        mi = mesh.user_node_to_mesh[nn]
        jl_list = [(mi, -T_N*np.cos(theta_n), +T_N*np.sin(theta_n), 0.0)]

    # Incremental Newton solve with radial penalty BCs.
    # One-sided contact — PHYSICAL convention:
    #   Stinger rollers: push OUTWARD (toward surface). Contact when pipe is at
    #     or below roller surface (rn = dn*lam - u_out >= 0). Lift-off when
    #     rn < -threshold (pipe has risen above roller). Re-contact when rn >= 0.
    #   Vessel rollers: push pipe UP (-Y). Contact when pipe is at/below deck
    #     (uy >= 0). Lift-off when pipe rises above deck (uy < -threshold).
    #   Note: without self-weight, tension at free end drives pipe toward rollers.
    #         For zero-tension runs, all rollers remain bilateral (one_sided has no effect).
    U = np.zeros(mesh.n_dofs)
    if initial_U is not None:
        # Warm-start: begin from a pre-computed displacement (e.g. elastic solution).
        # If sizes match, copy directly; if mesh differs (different epe), zero-fill.
        if len(initial_U) == mesh.n_dofs:
            U[:] = initial_U
        # else: silently fall back to zero-start (different mesh)
    th = np.full(mesh.n_elems, np.nan)

    # v1.41: J2 incremental plasticity state. None for 'RO'/'elastic' (assemble()
    # then takes the v3-compatible path and returns ps_new=None, unchanged).
    # For 'J2': committed at the START of each increment (frozen across all
    # active-set passes at that increment); committed forward only once the
    # increment's contact state and Newton iterations have both converged.
    ps_committed = PlasticState(mesh.n_elems, n_fib_active) if is_ep else None
    if is_ep and initial_plastic_state is not None:
        # v1.45: warm-start plastic state (chained sweep). Copy directly if
        # shapes match (same mesh, same n_fibres); otherwise leave zero-init
        # (silently -- mismatched shapes mean a different discretisation and
        # carryover is not meaningful).
        # KNOWN ISSUE (Session 20, unresolved): seeding a nonzero starting
        # plastic state here reliably produces a singular tangent stiffness
        # matrix during the increment-1 Newton solve, even when initial_U
        # is also warm-started consistently. Root cause not yet identified.
        # See technical reference §12.6. DO NOT enable
        # chain_plastic_state=True in run_passage() until this is resolved
        # -- the solve currently fails silently (phase1_peak=0.0, no
        # exception raised) rather than erroring loudly.
        ips = initial_plastic_state
        if (ips.n_elems == mesh.n_elems) and (ips.n_fibres == n_fib_active):
            ps_committed.eps_p[:] = ips.eps_p
            ps_committed.kap[:]   = ips.kap

    # active_r[k]: stinger radial roller SR2..SR6 in contact
    active_r = [True] * len(radial)
    lift_off_log = []
    # Pre-seed contact state from elastic_first Step 1 if provided.
    if _elastic_lifted_seed:
        for kk, (dux, duy, nx, ny, dn, sl) in enumerate(radial):
            if f'SR{sl+1}' in _elastic_lifted_seed:
                active_r[kk] = False
                lift_off_log.append((0, f'SR{sl+1}', 'pre-seeded inactive from elastic pass'))
    # active_v[k]: vessel/SR1 vertical rollers in contact
    active_v = [True] * len(vessel)
    std_ux  = list(std)   # all VR0 anchor DOFs: ux=0, uy=0, rz=0 (v1.37)

    # v1.45T: continuation-mode lam schedule. When BOTH a warm-started U
    # and a warm-started plastic state are provided (chained sweep), U is
    # already consistent with a FULLY loaded (lam=1) configuration from the
    # previous position. Re-ramping lam from 1/n_increments up to 1 in this
    # case creates a massive Fint/Fext imbalance at the first increment --
    # Fint reflects the full-load U+eps_p state while Fext reflects a
    # near-zero external load -- which blows up the Newton correction and
    # produces a singular tangent stiffness matrix (root-caused Session 20,
    # confirmed via debug trace: Fp residual ~1e19 at increment 1). Since
    # the new position is a small geometric perturbation of the old one,
    # the new equilibrium is close to the old one and a single full-load
    # (lam=1) continuation step, starting from the warm-started guess,
    # should converge via ordinary Newton iteration without incremental
    # ramping. Only used for chained continuation; the normal (first-
    # position, virgin-state) ramp is unchanged.
    _continuation = (is_ep and initial_U is not None and
                      initial_plastic_state is not None)
    if _continuation:
        lam_schedule = [1.0]
    else:
        lam_schedule = [inc / n_increments for inc in range(1, n_increments + 1)]

    for inc, lam in enumerate(lam_schedule, start=1):
        # Freeze plastic state at the committed value from the END of the
        # previous increment. Every Newton iteration and every active-set
        # pass within this increment reads this SAME frozen state (matches
        # nlfea_v4.solve_step()'s discipline) -- it is not re-frozen per pass.
        ps_inc_start = ps_committed.copy() if ps_committed is not None else None
        ps_trial     = ps_inc_start

        for active_set_pass in range(len(radial) + len(vessel) + 2):
            # --- Newton solve with current active set ---
            for it in range(30):
                K, Fint, Fext, th, ps_trial = assemble(
                    mesh, U, th, dist, jl_list, lam, plastic_state=ps_inc_start)
                pen = float(K.diagonal().max()) * 1e8
                Kl = K.tolil(); Fp = Fext - Fint

                # ux anchor — always active
                for (d, v) in std_ux:
                    Kl[d, d] += pen; Fp[d] += pen * (v - U[d])

                # Vessel / SR1 vertical rollers — n_hat=(0,-1), one-sided upward.
                # Force: Fp[duy] += pen*(-1)*rn where rn = dn*lam - u_out = 0 - (-uy) = uy
                #       = -pen*uy  (upward when uy>0 = pipe below deck) ✓
                for kk, (duy, nxv, nyv, dnv) in enumerate(vessel):
                    if not one_sided or active_v[kk]:
                        u_out_v = U[duy] * nyv          # = -uy (outward disp in -y)
                        rn_v    = dnv * lam - u_out_v   # = 0 - (-uy) = uy
                        Kl[duy, duy] += pen * nyv*nyv   # = pen (nyv=-1, nyv²=1)
                        Fp[duy]      += pen * nyv * rn_v  # = -pen*uy (upward)

                # Stinger radial rollers — one-sided toward arc centre
                for kk, (dux, duy, nx, ny, dn, sl) in enumerate(radial):
                    if not one_sided or active_r[kk]:
                        dl = dn * lam
                        Kl[dux, dux] += pen*nx*nx; Kl[duy, duy] += pen*ny*ny
                        Kl[dux, duy] += pen*nx*ny; Kl[duy, dux] += pen*nx*ny
                        rn = dl - (U[dux]*nx + U[duy]*ny)
                        Fp[dux] += pen*nx*rn; Fp[duy] += pen*ny*rn

                dU = spsolve(Kl.tocsr(), Fp)
                fm = max(float(np.max(np.abs(Fint))), 1.0)
                rc = float(np.max(np.abs(Fp[3:]))) / fm
                U += dU
                if it > 0 and rc < 1e-3:
                    break

            if not one_sided:
                break

            # --- Contact check ---
            # Compare full active state before/after to detect chattering.
            prev_state = (tuple(active_v), tuple(active_r))
            changed = False

            # Vessel / SR1 rollers — physical one-sided vertical upward.
            # n_hat = (0,-1). rn_v = 0 - (-uy) = uy.
            # Contact when uy >= 0 (pipe at/below deck). Lift-off when uy < 0.
            for kk, (duy, nxv, nyv, dnv) in enumerate(vessel):
                uy_cur = U[duy]
                rn_v   = dnv * lam - uy_cur * nyv   # = 0 - (-uy) = uy
                thr_v  = 1e-3
                if active_v[kk] and rn_v < -thr_v:
                    active_v[kk] = False; changed = True
                    vname = ['VR1','VR2','VR3','SR1'][kk] if kk < 4 else f'VR{kk+1}'
                    lift_off_log.append((inc, vname, 'lift-off'))
                elif not active_v[kk] and rn_v >= 0.0:
                    active_v[kk] = True; changed = True
                    vname = ['VR1','VR2','VR3','SR1'][kk] if kk < 4 else f'VR{kk+1}'
                    lift_off_log.append((inc, vname, 're-contact'))

            # Stinger radial rollers — physical one-sided (outward normal convention).
            # rn = dn*lam - u_out: positive when pipe is BELOW roller surface (contact).
            # Lift-off when rn < -threshold (pipe has risen above roller surface).
            # Re-contact when rn >= 0 (pipe returned to or below roller surface).
            # Re-activation is checked every pass even after previous deactivation.
            for kk, (dux, duy, nx, ny, dn, sl) in enumerate(radial):
                u_out = U[dux]*nx + U[duy]*ny
                rn    = dn*lam - u_out
                thr   = 1e-3 * abs(dn*lam + 1e-9)
                if active_r[kk] and rn < -thr:
                    active_r[kk] = False; changed = True
                    lift_off_log.append((inc, f'SR{sl+1}', 'lift-off'))
                elif not active_r[kk] and rn >= 0.0:
                    active_r[kk] = True; changed = True
                    lift_off_log.append((inc, f'SR{sl+1}', 're-contact'))

            if not changed:
                break
            # Stop if state is same as before this pass (chattering suppressed)
            if (tuple(active_v), tuple(active_r)) == prev_state:
                break

        # Increment converged (Newton + active-set) -- commit plastic state.
        if ps_trial is not None:
            ps_committed = ps_trial

    # ── v1.36: Two-pass tensile-reaction lift-off — ALL rollers except last stinger ─
    # PHYSICAL PRINCIPLE: No roller except the last stinger roller shall sustain a
    # tensile reaction. A tensile reaction means the roller is pulling the pipe —
    # physically impossible for a contact-only (push) constraint. The last stinger
    # roller (sl == n_sr-1) is excluded because it carries the tension termination
    # load and can show a boundary artefact.
    #
    # Prior to v1.36: only interior stinger rollers (SR2..SR_{N-1}) were checked.
    # Vessel rollers (VR1-VR3) and SR1 were NOT checked, allowing them to sustain
    # tensile reactions when SR2 is elevated by a shroud offset. This is physically
    # wrong and was identified as a cause of over-prediction at high V values.
    # Correction (Session 15, 5 Jun 2026): extend check to ALL active rollers.
    #
    # Reaction convention:
    #   Vessel/SR1 (vertical): F_contact = (Fint-Fext)[duy]. Negative = upward =
    #     compression (pipe is being pushed up by roller) = valid contact.
    #     Positive = downward = tension (roller pulling pipe down) = lift off.
    #     Note sign: Fy positive = downward (Y-down convention), so tensile reaction
    #     is Fy > +TENS_THR → lift off.
    #   Stinger radial: Fp_out = (Fint-Fext)·n_hat_out. Positive = compression
    #     (outward force = roller pushing pipe toward surface) = valid.
    #     Negative = tension = lift off.
    if one_sided:
        TENS_THR = 10e3   # 10 kN threshold
        for _outer in range(8):   # up to 8 passes to handle cascading lift-offs
            # Read-only reaction check at the converged state (lam=1.0) --
            # uses the final committed plastic state, does not advance it.
            Kc, Fintc, Fextc, th, _ = assemble(
                mesh, U, th, dist, jl_list, 1.0, plastic_state=ps_committed)
            changed_outer = False

            # Vessel rollers VR1-VR3 + SR1 — all can lift off freely (v1.37).
            # VR0 anchor ensures the structure remains constrained even if all
            # vessel contact rollers lift off. No 'last active' safeguard needed.
            for kk, (duy, nxv, nyv, dnv) in enumerate(vessel):
                if not active_v[kk]: continue
                Fy_contact = float(Fintc[duy] - Fextc[duy])
                if Fy_contact > TENS_THR:
                    active_v[kk] = False; changed_outer = True
                    vname = ['VR1','VR2','VR3','SR1'][kk] if kk < 4 else f'VR{kk+1}'
                    lift_off_log.append((f'pass{_outer}', vname,
                        f'tensile lift-off (Fy={Fy_contact/1e3:.0f}kN)'))

            # Stinger radial rollers SR2..SR_{N-1}
            for kk, (dux, duy, nx, ny, dn, sl) in enumerate(radial):
                if not active_r[kk]: continue
                if sl >= n_sr - 1: continue   # exclude last stinger roller
                Fp_out = (Fintc[dux]-Fextc[dux])*nx + (Fintc[duy]-Fextc[duy])*ny
                if Fp_out < -TENS_THR:
                    active_r[kk] = False; changed_outer = True
                    lift_off_log.append((f'pass{_outer}', f'SR{sl+1}',
                        f'tensile lift-off (Fpen_out={Fp_out/1e3:.0f}kN)'))

            if not changed_outer:
                break

            # Full re-solve with the reduced active set: this is a fresh
            # monotonic load path from zero for THIS solve's own increments,
            # but if a chained initial_plastic_state was provided (sweep
            # carryover), that history must survive this internal re-solve
            # too -- otherwise a lift-off event mid-solve silently discards
            # the carried-forward plastic state (v1.45 fix, Session 20).
            U[:] = 0.0; th[:] = np.nan
            if is_ep:
                ps_committed = PlasticState(mesh.n_elems, n_fib_active)
                if initial_plastic_state is not None:
                    ips = initial_plastic_state
                    if (ips.n_elems == mesh.n_elems) and (ips.n_fibres == n_fib_active):
                        ps_committed.eps_p[:] = ips.eps_p
                        ps_committed.kap[:]   = ips.kap
            for inc in range(1, n_increments + 1):
                lam = inc / n_increments
                ps_inc_start = ps_committed.copy() if ps_committed is not None else None
                ps_trial     = ps_inc_start
                for it in range(30):
                    K, Fint, Fext, th, ps_trial = assemble(
                        mesh, U, th, dist, jl_list, lam, plastic_state=ps_inc_start)
                    pen = float(K.diagonal().max()) * 1e8
                    Kl = K.tolil(); Fp = Fext - Fint
                    for (d, v) in std_ux:
                        Kl[d,d] += pen; Fp[d] += pen*(v-U[d])
                    for kk2, (duy2,nxv2,nyv2,dnv2) in enumerate(vessel):
                        if active_v[kk2]:
                            u_o2=U[duy2]*nyv2; rn2=dnv2*lam-u_o2
                            Kl[duy2,duy2]+=pen*nyv2*nyv2; Fp[duy2]+=pen*nyv2*rn2
                    for kk2,(dux2,duy2,nx2,ny2,dn2,sl2) in enumerate(radial):
                        if active_r[kk2]:
                            dl2=dn2*lam; rn2=dl2-(U[dux2]*nx2+U[duy2]*ny2)
                            Kl[dux2,dux2]+=pen*nx2*nx2; Kl[duy2,duy2]+=pen*ny2*ny2
                            Kl[dux2,duy2]+=pen*nx2*ny2; Kl[duy2,dux2]+=pen*nx2*ny2
                            Fp[dux2]+=pen*nx2*rn2; Fp[duy2]+=pen*ny2*rn2
                    try: dU = spsolve(Kl.tocsr(), Fp)
                    except Exception: break
                    fm = max(float(np.max(np.abs(Fint))),1.0)
                    U += dU
                    if it>0 and float(np.max(np.abs(Fp[3:])))/fm < 1e-3: break
                if ps_trial is not None:
                    ps_committed = ps_trial

    # Build a runner to extract strains
    r = FEARunner(model)
    r.U = U.copy(); r.U_steps = [U.copy()]
    r.results = [[{'lambda': 1.0, 'iterations': it+1, 'residual': rc, 'U': U.copy()}]]
    r.plastic_state = ps_committed   # v1.41: needed for sigma_top/bot on EP elements
                                      # (eps_max is purely kinematic -- unaffected)

    # Strain profile
    span_labels = (['VR0-VR1', 'VR1-VR2', 'VR2-VR3', 'VR3-SR1'] +
                   [f'SR{i}-SR{i+1}' for i in range(1, n_sr)])
    x_sr3 = sr[2][0]
    xm = []; ev = []; sn = []
    for s in range(nsp):
        x0r = allc[s][0]; x1r = allc[s+1][0]
        for k in range(epe):
            eid = s*epe + k + 1
            if eid < nn:
                st = r.get_element_strains(eid)
                xm.append(x0r + (k+0.5)/epe*(x1r-x0r))
                ev.append(st['eps_max'])
                sn.append(span_labels[s] if s < len(span_labels) else f'span{s}')

    ph1 = [(x, e, s) for x, e, s in zip(xm, ev, sn) if x >= x_sr3]
    pk = max(ph1, key=lambda q: q[1]) if ph1 else (0, 0, '-')

    # Roller labels for active-set reporting
    vr_labels = ['VR1', 'VR2', 'VR3', 'SR1'][:len(vessel)]
    sr_labels  = [f'SR{i}' for i in range(2, n_sr+1)]
    active_rollers   = ([vr_labels[k] for k in range(len(vessel))  if active_v[k]] +
                        [sr_labels[k] for k in range(len(radial)) if active_r[k]])
    inactive_rollers = ([vr_labels[k] for k in range(len(vessel))  if not active_v[k]] +
                        [sr_labels[k] for k in range(len(radial)) if not active_r[k]])

    # is_thick flag per element in strain profile (same order as xm/ev)
    thick_set = set(thick_elems)
    is_thick_profile = []
    for s in range(nsp):
        for k in range(epe):
            eid = s*epe + k + 1
            if eid < nn:
                is_thick_profile.append(eid in thick_set)

    result = {
        'U': U, 'runner': r, 'mesh': mesh, 'rnid': rnid, 'allc': allc,
        'sr': sr, 'x_mids': xm, 'eps': ev, 'span_names': sn,
        'is_thick': is_thick_profile,
        'thick_elems': thick_elems,
        'sec_ids': sec_ids,
        'x_sr3': x_sr3, 'phase1_peak': pk[1], 'phase1_peak_x': pk[0],
        'phase1_peak_span': pk[2], 'dtheta': dtheta, 'nsp': nsp,
        'n_sr': n_sr, 'epe': epe, 'one_sided': one_sided,
        'active_r': active_r, 'active_v': active_v,
        'active_rollers': active_rollers,
        'inactive_rollers': inactive_rollers, 'lift_off_log': lift_off_log,
        'material': material, 'plastic_state': ps_committed,
        'section': section, 'n_points_polar': n_points_polar,
        'n_fib_active': n_fib_active,
    }

    # v1.32: SR3-type interior lift-off now resolved via two-pass tensile-reaction
    # check above (see comment block after the main solve loop).

    if verbose:
        sec_label = f"{section}({n_points_polar}pt)" if section == 'polar' else f"{section}({n_fibres})"
        print(f"S-Lay Overbend | {material} | {sec_label} | R={R}m | {n_sr} SR | "
              f"T={tension_mt}MT | self_weight={self_weight} | "
              f"one_sided={one_sided}")
        if thick_component is not None:
            import math
            ei_plain = 207e9 * math.pi/64*(D_o**4-(D_o-2*t)**4)
            ei_thick = 207e9 * math.pi/64*(tc['OD']**4-(tc['OD']-2*tc['t'])**4)
            print(f"  Thick component: OD={tc['OD']*1000:.1f}mm  t={tc['t']*1000:.1f}mm  "
                  f"L={tc['length']:.2f}m  cx={tc['centre_x']:.3f}m  "
                  f"EI ratio={ei_thick/ei_plain:.2f}x  "
                  f"elements={thick_elems}")
        if vessel_offsets:
            print(f"  Vessel offsets:  { {k:f'{v*1000:.1f}mm' for k,v in vessel_offsets.items()} }")
        if roller_offsets:
            print(f"  Roller offsets:  { {f'SR{k+1}':f'{v*1000:.1f}mm' for k,v in roller_offsets.items()} }")
        print(f"  Phase 1 peak strain = {pk[1]*100:.4f}%  [{pk[2]}  X={pk[0]:.2f}m]")
        print(f"  Utilisation = {pk[1]/EPS_RD*100:.1f}% of DCC ({EPS_RD*100:.3f}%)")
        if one_sided:
            print(f"  Active rollers:   {', '.join(active_rollers)}")
            if inactive_rollers:
                print(f"  Lifted off:       {', '.join(inactive_rollers)}")
            else:
                print(f"  Lifted off:       none (all in contact)")

    return result


# =============================================================================
# v1.43  BENDING MOMENT PROFILE (Session 20, 21 Jul 2026)
# =============================================================================
# Merged from the standalone moment_profile.py helper (Session 20). No
# built-in bending-moment output existed before this. Computes M(x) per
# user element via full fibre-stress integration at the committed plastic
# state, M = sum(sigma_i * y_i * A_i) over all fibres -- correctly reflects
# the plasticized moment-curvature relationship for J2/RO inelastic
# elements (unlike a linear-elastic EI*kappa estimate). Not called
# automatically by run_slay() (extra cost); call explicitly on a result.
#
# Usage:
#   res = run_slay(..., thick_component=tc)
#   x_mids, M, is_thick = get_moment_profile(res)
#   idx = np.argmax(np.abs(M))
#   print(f"Peak |M| = {M[idx]/1e3:.1f} kN.m at x={x_mids[idx]:.2f}m")
# =============================================================================

def get_moment_profile(res):
    """
    Compute bending moment M(x) [N.m] for every user element in a run_slay
    result, via full fibre-stress integration at the committed plastic
    state (post-solve): M = sum(sigma_i * y_i * A_i) over all fibres.

    For purely elastic elements, falls back to M = E*I*kappa.

    Parameters
    ----------
    res : dict
        The return value of run_slay() (must contain 'runner', 'U',
        'is_thick', 'x_mids').

    Returns
    -------
    x_mids   : (n_elem,) ndarray -- element midpoint x-coordinates (undeformed)
    M        : (n_elem,) ndarray -- bending moment, N.m
    is_thick : (n_elem,) ndarray[bool]
    """
    runner = res['runner']
    mesh = runner.mesh
    U = res['U']
    is_thick_elem = np.array(res['is_thick'])
    xm = np.array(res['x_mids'])

    M_arr = np.zeros(len(xm))
    user_ids = sorted(mesh.user_elem_to_mesh.keys())

    for k, elem_id in enumerate(user_ids):
        mesh_indices = mesh.user_elem_to_mesh[elem_id]
        M_sub = []
        for ie in mesh_indices:
            dofs = mesh.elem_dof_array[ie]
            ux1, uy1, rz1 = U[dofs[0]], U[dofs[1]], U[dofs[2]]
            ux2, uy2, rz2 = U[dofs[3]], U[dofs[4]], U[dofs[5]]
            coords = mesh.elem_coords[ie]
            L0_e = mesh.elem_L0[ie]
            x1d = coords[0] + ux1; y1d = coords[1] + uy1
            x2d = coords[2] + ux2; y2d = coords[3] + uy2
            Ld_e = float(np.hypot(x2d - x1d, y2d - y1d))
            theta0_e = float(np.arctan2(coords[3]-coords[1], coords[2]-coords[0]))
            theta_e = float(np.arctan2(y2d - y1d, x2d - x1d))
            dth_e = theta_e - theta0_e
            u4_e = Ld_e - L0_e
            u3_e = rz1 - dth_e
            u6_e = rz2 - dth_e
            eps0_e = u4_e / L0_e
            kappa_e = (u6_e - u3_e) / L0_e

            if not (mesh.elem_inelastic[ie] or mesh.elem_ep[ie]):
                # Purely elastic element -- fall back to EI*kappa
                sec_id = mesh.mesh_elems[ie][3]
                sec = mesh.section_map[sec_id]
                E_e = mesh.elem_E[ie]
                I_e = getattr(sec, 'I', None)
                if I_e is None:
                    d = getattr(sec, 'd', None); b = getattr(sec, 'b', None)
                    I_e = b*d**3/12 if (b is not None and d is not None) else 0.0
                M_sub.append(E_e * I_e * kappa_e)
                continue

            fy, fA = mesh.elem_fibres[ie]
            eps_fib = eps0_e + fy * kappa_e

            if mesh.elem_ep[ie]:
                # J2 incremental plasticity -- use committed plastic state
                mat_ep = mesh.elem_ep_mat[ie]
                if getattr(runner, 'plastic_state', None) is not None:
                    nf = len(fy)
                    ep_c = runner.plastic_state.eps_p[ie, 0, :nf]
                    ka_c = runner.plastic_state.kap[ie, 0, :nf]
                    sigma, *_ = _ep_return_mapping(eps_fib, ep_c, ka_c, mat_ep.E, mat_ep)
                else:
                    sigma = mat_ep.E * eps_fib
            else:
                # RO deformation plasticity (fibre model)
                E_r, sig_y, alpha, n_ro = mesh.elem_ro_params[ie]
                sigma = _ro_stress(eps_fib, E_r, sig_y, alpha, n_ro)

            M_e = float(np.sum(sigma * fy * fA))
            M_sub.append(M_e)

        # worst (max |M|) among mesh sub-elements for this user element
        M_arr[k] = max(M_sub, key=abs) if M_sub else 0.0

    return xm, M_arr, is_thick_elem



# =============================================================================
# v1.39  PASSAGE SIMULATION
# =============================================================================

def run_passage(R=R_DEF, D_o=D_O_DEF, t=T_W_DEF,
                thick_component_base=None,
                n_steps=None, step_size=0.5, x_start=None, x_end=None,
                material='RO', tension_mt=0.0, self_weight=True,
                one_sided=True, elastic_first=True,
                n_sr=N_SR, n_fibres=20, n_increments=20, verbose=True,
                roller_offsets=None, vessel_offsets=None,
                warm_start=False,
                section='polar', n_points_polar=8,
                chain_plastic_state=False):
    """
    Simulate full component passage over the stinger (v1.39).

    Sweeps thick_component centre_x from x_start to x_end in n_steps,
    running run_slay() at each position.  Equivalent to the pipeline moving
    from the flat vessel deck onto and across the stinger, capturing the
    Phase 1 → Phase 2 quasi-static transition in a single call.

    Model coordinate reminder:
        SR1 at x=0.  X positive → vessel (RIGHT).  X negative → stinger tip (LEFT).

    Passage stages (default sweep, v1.44 / Session 20 convention #2):
        x_start = SR2 + L_comp/2  (leading edge of component reaches SR2)
        x_end   = SR2 - L_comp/2  (trailing edge of component leaves SR2)
        step_size = 0.5 m (default; total positions = span/step_size + 1)
        This isolates the window where the component body is actually in
        the vicinity of / passing over SR2 -- the governing contact event
        for most cases -- rather than sweeping a large low-signal region.
        Superseded the earlier SR1-to-SR2/SR3-midspan default (same
        session) once comparison work showed this SR2-centred window is
        both faster (much narrower) and better targeted.

    Parameters
    ----------
    thick_component_base : dict with keys 'OD', 't', 'length'.
                           'centre_x' is NOT required — set by sweep.
                           If None, runs plain pipe passage (baseline check).
    n_steps    : passage positions. Default None -> computed from step_size
                 and the x_start/x_end span. Set explicitly to override.
    step_size  : default sweep step, metres (default 0.5). Only used when
                 n_steps is None.
    x_start    : default = SR2 + L_comp/2 (leading edge at SR2).
    x_end      : default = SR2 - L_comp/2 (trailing edge at SR2).
                 Override both for a custom start/end sweep, or set both
                 equal (with n_steps=1) for a single-position study.
    warm_start : pass previous U as initial_U.  No effect on R-O result
                 (path-independent material) but may ease convergence.
    chain_plastic_state : bool (default FALSE, v1.45, Session 20 — EXPERIMENTAL,
                 DO NOT ENABLE). Intended to carry the committed plastic
                 state (eps_p, kap per fibre) from each sweep position into
                 the next as initial_plastic_state, so the pipe's plasticity
                 history accumulates along the physical passage instead of
                 each position solving from virgin material state. Element-
                 index-wise carryover is exact wherever an element's
                 section type (plain vs thick) is unchanged between
                 consecutive positions; elements whose section type flips
                 (component edge sweeping past them) are reset to zero
                 plastic strain for that element only, since fibre geometry
                 differs between plain and thick sections and a direct
                 carryover would not be physically meaningful. No effect
                 for material != 'J2' (RO/elastic have no PlasticState).
                 KNOWN BROKEN (Session 20): seeding a nonzero starting
                 plastic state reliably produces a singular tangent
                 stiffness matrix at increment 1, even with initial_U also
                 warm-started consistently. The solve fails SILENTLY
                 (phase1_peak=0.0, no exception) rather than erroring
                 loudly -- do not trust any result produced with this flag
                 True until the root cause is found and fixed. Default
                 changed to False for this reason. See technical reference
                 §12.6 for the debugging session record. Planned follow-up:
                 a temporary v1.45T branch dedicated to resolving this.
    n_increments : load increments per run_slay call (default 20 — half the
                   run_slay default of 40; passage runs are sequential and
                   well-conditioned, so fewer increments suffice).
    All other params: identical to run_slay().

    Returns
    -------
    dict:
        x_centre         (n,)  component centre x-positions (m)
        eps_peak         (n,)  global peak strain excl. VR0-VR1 boundary span
        eps_phase1       (n,)  Phase 1 zone peak (x >= x_SR3) per run_slay metric
        active_rollers   list(n)  active roller names per step
        inactive_rollers list(n)  inactive roller names per step
        results          list(n)  full run_slay() dicts
        roller_x         dict {name: x_coord}  all roller x-positions
        L_component      float  component length (m)
        D_o, R, t        scalars
        baseline_eps     float  plain pipe phase1_peak (fraction)
    """
    # ── Geometry — roller x-positions ──────────────────────────────────────
    allc, sr_coords, _n, _rn, _ns, _nn, _dt = build_geometry(
        R, n_sr, N_VR, SPACING, None, D_o)

    roller_x = {}
    for j in range(N_VR + 1):              # VR0 .. VR3
        roller_x['VR0' if j == 0 else f'VR{j}'] = allc[j][0]
    for i in range(n_sr):                   # SR1 .. SR_n
        roller_x[f'SR{i+1}'] = allc[N_VR + 1 + i][0]

    L_comp = thick_component_base['length'] if thick_component_base is not None else 0.0

    # ── Default sweep range (v1.44, Session 20 convention #2) ──────────────
    # Component centre_x: Start = leading edge of component at SR2 (i.e.
    # centre_x = x_SR2 + L/2). End = trailing edge of component at SR2
    # (centre_x = x_SR2 - L/2). This brackets exactly the window in which
    # the component body is in the vicinity of / passing over SR2 -- the
    # single most useful default because it isolates the actual
    # roller-component contact interaction instead of a large low-signal
    # region. Total sweep range = L_comp, centred on SR2.
    # Superseded the SR1-to-mid(SR2,SR3) default (also this session) once
    # comparison work showed that range was both slower (much wider) and
    # less targeted than sweeping exactly across the SR2 contact event.
    # Step size (not step count) is the primary control: default 0.5m.
    x_sr2 = roller_x['SR2'] if n_sr >= 2 else roller_x[f'SR{n_sr}']

    if x_start is None:
        x_start = x_sr2 + L_comp / 2.0      # leading edge reaches SR2
    if x_end is None:
        x_end = x_sr2 - L_comp / 2.0        # trailing edge leaves SR2

    if n_steps is None:
        span = abs(x_end - x_start)
        n_steps = max(int(round(span / step_size)) + 1, 2)

    x_positions   = np.linspace(x_start, x_end, n_steps)
    step_dx       = abs(x_end - x_start) / max(n_steps - 1, 1)

    # ── Print header ────────────────────────────────────────────────────────
    if verbose:
        print("\nPassage Simulation v1.39")
        print(f"  R={R}m | D_o={D_o*1000:.0f}mm | t={t*1000:.0f}mm | "
              f"T={tension_mt}MT | sw={self_weight} | mat={material}")
        if thick_component_base is not None:
            OD_tc = thick_component_base['OD']
            t_tc  = thick_component_base['t']
            import math
            EI_pl = 207e9 * math.pi / 64 * (D_o**4 - (D_o - 2*t)**4)
            EI_tc = 207e9 * math.pi / 64 * (OD_tc**4 - (OD_tc - 2*t_tc)**4)
            print(f"  Component: OD={OD_tc*1000:.0f}mm  t={t_tc*1000:.0f}mm  "
                  f"L={L_comp:.2f}m ({L_comp/D_o:.1f}D)  "
                  f"EI={EI_tc/EI_pl:.2f}x pipeline")
        else:
            print("  Component: NONE (plain pipe passage)")
        print(f"  Sweep:  {x_start:+.2f}m → {x_end:+.2f}m  "
              f"({n_steps} steps, Δx={step_dx:.3f}m = {step_dx/D_o:.2f}D)")
        print()

    # ── Passage loop ─────────────────────────────────────────────────────────
    eps_peak_arr   = np.zeros(n_steps)
    eps_phase1_arr = np.zeros(n_steps)
    active_list    = []
    inactive_list  = []
    results_list   = []
    U_prev         = None
    ps_prev        = None    # committed PlasticState from previous position
    sec_ids_prev   = None    # section-id array from previous position
    do_chain       = chain_plastic_state and (material == 'J2')

    for i, cx in enumerate(x_positions):
        # Build component spec for this position
        tc = None
        if thick_component_base is not None:
            tc = dict(thick_component_base)
            tc['centre_x'] = float(cx)

        kw = dict(R=R, D_o=D_o, t=t, n_sr=n_sr, epe=None,
                  material=material, tension_mt=tension_mt,
                  self_weight=self_weight, one_sided=one_sided,
                  elastic_first=elastic_first,
                  n_increments=n_increments,
                  n_fibres=n_fibres, verbose=False,
                  roller_offsets=roller_offsets,
                  vessel_offsets=vessel_offsets,
                  thick_component=tc,
                  section=section, n_points_polar=n_points_polar)
        if warm_start and U_prev is not None:
            kw['initial_U'] = U_prev

        if do_chain and ps_prev is not None:
            kw['initial_plastic_state'] = ps_prev
            kw['initial_sec_ids']       = sec_ids_prev

        res = run_slay(**kw)

        # Global peak — exclude VR0-VR1 boundary span (fixed anchor region)
        eps_no_bdy = [e for e, s in zip(res['eps'], res['span_names'])
                      if s != 'VR0-VR1']
        eps_global = max(eps_no_bdy) if eps_no_bdy else 0.0

        eps_peak_arr[i]   = eps_global
        eps_phase1_arr[i] = res['phase1_peak']
        active_list.append(res['active_rollers'])
        inactive_list.append(res['inactive_rollers'])
        results_list.append(res)

        if warm_start:
            U_prev = res['U'].copy()

        if do_chain:
            sec_ids_prev = res['sec_ids']
            ps_prev      = res['runner'].plastic_state

        if verbose:
            pct  = (i + 1) / n_steps * 100
            lo   = res['inactive_rollers'] if res['inactive_rollers'] else ['none']
            print(f"  [{pct:5.1f}%] cx={cx:+7.2f}m  eps_pk={eps_global*100:.4f}%  "
                  f"ph1={res['phase1_peak']*100:.4f}%  "
                  f"lifted=[{', '.join(lo)}]")

    # ── Baseline: plain pipe (no component) ────────────────────────────────
    res_base = run_slay(R=R, D_o=D_o, t=t, n_sr=n_sr,
                        material=material, tension_mt=tension_mt,
                        self_weight=self_weight, one_sided=one_sided,
                        elastic_first=elastic_first,
                        n_increments=n_increments,
                        n_fibres=n_fibres,
                        verbose=False, thick_component=None,
                        roller_offsets=roller_offsets, vessel_offsets=vessel_offsets,
                        section=section, n_points_polar=n_points_polar)
    baseline = res_base['phase1_peak']

    worst_i = int(np.argmax(eps_peak_arr))
    if verbose:
        print(f"\n  Baseline (plain pipe):  {baseline*100:.4f}%")
        print(f"  Passage peak:           {eps_peak_arr[worst_i]*100:.4f}%  "
              f"at cx={x_positions[worst_i]:+.2f}m")
        print(f"  Amplification:          {eps_peak_arr[worst_i]/max(baseline, 1e-9):.2f}×  "
              f"DNV util {eps_peak_arr[worst_i]/EPS_RD*100:.1f}%")

    return {
        'x_centre':          x_positions,
        'eps_peak':          eps_peak_arr,
        'eps_phase1':        eps_phase1_arr,
        'active_rollers':    active_list,
        'inactive_rollers':  inactive_list,
        'results':           results_list,
        'roller_x':          roller_x,
        'L_component':       L_comp,
        'D_o':               D_o,
        'R':                 R,
        't':                 t,
        'baseline_eps':      baseline,
    }


def plot_passage(passage_result, save_path=None, title=None):
    """
    Plot passage simulation results.

    Shows global peak strain and Phase 1 zone peak vs component centre x,
    with vertical markers at every roller position and a shaded band showing
    the component extent at its worst (peak) position.

    Parameters
    ----------
    passage_result : dict returned by run_passage().
    save_path      : file path to save PNG (optional).
    title          : custom title (auto-generated if None).

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.pyplot as plt

    pr   = passage_result
    x    = pr['x_centre']
    eps  = pr['eps_peak']   * 100       # %
    ph1  = pr['eps_phase1'] * 100       # %
    base = pr['baseline_eps'] * 100     # %
    L    = pr['L_component']
    D_o  = pr['D_o']

    fig, ax = plt.subplots(figsize=(13, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')
    for sp in ax.spines.values():
        sp.set_edgecolor('#444466')

    # ── Strain curves ──────────────────────────────────────────────────────
    ax.plot(x, eps, 'o-',  color='#e94560', lw=2.0, ms=4,
            label='Global peak (excl. boundary)')
    ax.plot(x, ph1, 's--', color='#f5a623', lw=1.5, ms=3,
            label='Phase 1 zone peak (x ≥ SR3)')
    ax.axhline(base,       color='#00d4ff', ls=':', lw=1.5,
               label=f'Plain pipe baseline  {base:.4f}%')
    ax.axhline(EPS_RD*100, color='#ff4444', ls='--', lw=1.0, alpha=0.7,
               label=f'DNV DCC limit  {EPS_RD*100:.3f}%')

    # ── Roller verticals ───────────────────────────────────────────────────
    vessel_col  = '#88ff88'
    stinger_col = '#ffaa44'
    sr1_col     = '#ffee22'
    for rname, rx in sorted(pr['roller_x'].items(), key=lambda kv: kv[1], reverse=True):
        if rname == 'VR0':
            continue
        col = (vessel_col if rname.startswith('V')
               else sr1_col if rname == 'SR1'
               else stinger_col)
        ax.axvline(rx, color=col, ls=':', lw=0.8, alpha=0.55)
        ax.text(rx, 0.98, rname,
                transform=ax.get_xaxis_transform(),
                color=col, fontsize=7, ha='center', va='top', rotation=90)

    # ── Component extent at peak position ──────────────────────────────────
    worst_i  = int(np.argmax(pr['eps_peak']))
    cx_worst = x[worst_i]
    if L > 0:
        ax.axvspan(cx_worst - L/2, cx_worst + L/2,
                   alpha=0.12, color='#e94560',
                   label=f'Component extent at peak  cx={cx_worst:+.1f}m')
        ax.annotate(f"Peak {eps[worst_i]:.4f}%",
                    xy=(cx_worst, eps[worst_i]),
                    xytext=(cx_worst + max(3, L), eps[worst_i] * 1.06 + 0.02),
                    color='#e94560', fontsize=8,
                    arrowprops=dict(arrowstyle='->', color='#e94560', lw=1))

    # ── Phase 1 entry marker (leading end at SR1) ──────────────────────────
    x_ph1_entry = 0.0 + L / 2   # centre_x when leading end is at SR1
    if x[-1] < x_ph1_entry < x[0]:
        ax.axvline(x_ph1_entry, color='#cc44ff', ls='-.', lw=1.2, alpha=0.7)
        ax.text(x_ph1_entry, 0.88, 'Ph1 entry\n(lead end\nat SR1)',
                transform=ax.get_xaxis_transform(),
                color='#cc44ff', fontsize=7, ha='center', va='top')

    # ── Axes formatting ────────────────────────────────────────────────────
    ax.set_xlabel("Component centre  x (m)          vessel deck →     ← stinger tip",
                  color='#cccccc', fontsize=10)
    ax.set_ylabel("Peak strain (%)", color='#cccccc', fontsize=10)
    ax.tick_params(colors='#cccccc')
    ax.grid(True, alpha=0.20, color='#444466')
    ax.yaxis.set_inverted(False)   # strain positive upward (normal orientation)

    # ── Passage direction arrow ────────────────────────────────────────────
    ax.annotate("← passage direction",
                xy=(0.97, 0.04), xycoords='axes fraction', ha='right',
                color='#888899', fontsize=8)

    if title is None:
        title = (f"Passage Simulation v1.39   R={pr['R']}m   "
                 f"D_o={pr['D_o']*1000:.0f}mm   "
                 f"L={L:.1f}m ({L/D_o:.1f}D)   T={0}MT")
    ax.set_title(title, color='white', fontsize=11, pad=10)

    ax.legend(fontsize=8, facecolor='#1a1a2e', edgecolor='#444466',
              labelcolor='white', loc='upper right')

    ax.set_xlim(x[-1] - 3.0, x[0] + 3.0)   # tight limits: passage range + 3m margin
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight',
                    facecolor='#1a1a2e')
        print(f"  Saved: {save_path}")
    plt.show()
    return fig


# #############################################################################
# ##  CHAINED FIXED-MESH PASSAGE SWEEP (merged from slay_passage_v2.py v2.00)
# ##  Session 20 rebuild -- see module docstring v1.47 entry and tech ref
# ##  \u00a712.7-12.9. Uses this file's existing imports (nlfea_v4 read-only,
# ##  spsolve, numpy) and constants (G, RHO_STEEL). J2-only by design.
# #############################################################################
# =============================================================================
# GEOMETRY (replicates slay_overbend build_geometry -- flat y=0 node line,
# roller heights live in the BC targets, not the node coordinates)
# =============================================================================

def _build_geometry(R, n_sr, n_vr, spacing, D_o, elem_len=None, snap_x=None):
    """Nodes on y=0; roller stations; per-station arc heights.

    elem_len : v1.48 -- override the default 2*D_o element length (e.g.
               for a mesh-convergence check). None = unchanged (2*D_o,
               matching the paper's own "standard mesh" convention).
    snap_x   : v1.48, this session -- optional list of REFERENCE x
               positions that MUST appear as an exact node, in addition
               to the regular uniform subdivision. Fixes a real finding
               (tech-ref 13.25): without this, a component's sec_id is
               assigned by testing each element's MIDPOINT against the
               nominal boundary, and since L_comp is rarely an exact
               multiple of elem_len, the realized modeled length rounds
               to the nearest whole element -- 81% of nominal for a 2.5D
               component at the standard 2xOD mesh, confirmed. Abaqus's
               own adaptive meshing snaps to geometric feature boundaries
               by default; this reproduces that behaviour. A span that
               already contains no snap point is completely unaffected --
               this is purely additive, never removes or moves an
               existing node.

    Returns
    -------
    nodes    : list[Node] (user ids 1..nid)
    rnid     : {station_index: user_node_id}, station order
               0=VR0, 1=VR1, 2=VR2, 3=VR3, 4=SR1, 5=SR2, ...
    dn_map   : {station_index: uy target (arc height, 0 for deck)}
    dtheta   : arc angle per roller span
    nid      : last user node id
    allc     : [(x, y_station)] per station (for reporting)
    """
    elem_len = elem_len if elem_len is not None else 2.0 * D_o
    epe = max(1, int(round(spacing / elem_len)))
    dtheta = spacing / R
    vr = [(+(n_vr + 1 - j) * spacing, 0.0) for j in range(0, n_vr + 1)]   # VR0..VR3
    sr = [(-R * np.sin((i - 1) * dtheta),
            R * (1 - np.cos((i - 1) * dtheta))) for i in range(1, n_sr + 1)]
    allc = vr + sr
    nsp = len(allc) - 1

    snaps = sorted(float(s) for s in snap_x) if snap_x else []

    nodes = []; nid = 1; rnid = {}
    for s in range(nsp):
        x0, _ = allc[s]; x1, _ = allc[s + 1]
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        # regular uniform subdivision x-positions for this span (station
        # x1 itself excluded here -- it is emitted as station s+1's k=0
        # node on the next iteration, exactly as before)
        xs_span = [x0 + (k/epe)*(x1-x0) for k in range(epe)]
        # v1.48 correction (this turn): a snap point that coincides with
        # this span's OWN boundary (lo or hi) is ALREADY guaranteed to be
        # a node -- lo via this span's own k=0 emission, hi via the NEXT
        # span's k=0 emission on the following iteration. Including it
        # here too creates a second, near-duplicate Node at (numerically)
        # the same x, i.e. a zero-length element -- confirmed this turn:
        # produced NaN throughout the solve (division by ~0 length in
        # stiffness). Coincidence is common, not an edge case: a
        # component's boundary is very often defined relative to a
        # station position (e.g. ref_centre_x = x_sr2 + L_comp/2 puts the
        # leading edge exactly at x_sr2). Tolerance here (1e-6) is
        # "same station", deliberately much larger than the 1e-9 span-
        # membership test above, which only needs to reject points
        # clearly outside the span.
        in_span = [v for v in snaps
                   if lo - 1e-9 < v < hi + 1e-9
                   and abs(v - lo) > 1e-6 and abs(v - hi) > 1e-6]
        if in_span:
            # v1.48 correction (this turn): naively merging snap points
            # into the regular subdivision creates SLIVER elements where
            # a snap lands near an existing node -- measured 0.184 m
            # (0.45xOD) for the standard A1 case, far below the L/D~1
            # formulation floor (tech-ref 13.7). Consequences were real
            # and immediate: A2/R70 failed to converge at all (0 of 5
            # steps), and A1/R70's peak jumped +30% on a local sliver
            # artefact rather than physics.
            # Fix: a snap node WINS over a nearby regular node -- drop
            # any interior regular node within half a local element of a
            # snap. This is exactly what Abaqus does when you partition
            # an edge and re-seed it: the partition boundary is honoured
            # and the seed adapts, rather than both being kept. The
            # span's own k=0 node is never dropped (rnid[s] depends on
            # it for station identification).
            dxr = abs(x1 - x0)/epe
            keep = [xs_span[0]] + [v for v in xs_span[1:]
                                    if all(abs(v - w) > 0.5*dxr
                                           for w in in_span)]
            merged = sorted(set(round(v, 9) for v in keep + in_span),
                             key=(lambda v: v) if x1 >= x0 else (lambda v: -v))
        else:
            merged = xs_span
        for k, xv in enumerate(merged):
            nodes.append(Node(nid, xv, 0.0))
            if k == 0:
                rnid[s] = nid
            nid += 1
    nodes.append(Node(nid, allc[-1][0], 0.0))
    rnid[nsp] = nid

    dn_map = {}
    for s in range(len(allc)):
        dn_map[s] = allc[s][1]      # 0.0 for VR0..SR1, arc height for SR2+
    return nodes, rnid, dn_map, dtheta, nid, allc


# =============================================================================
# STRAIN EXTRACTION (CR kinematics replicated read-only from nlfea formulae)
# =============================================================================

def _strain_profile(mesh, U, th, r_o_elem):
    """Nominal extreme-fibre strain per mesh element.

    NE_e = |u4/L0| + r_o * max_gauss |kappa|, with the De Souza unwrap
    applied against the carried theta_states th (all valid post-solve).
    """
    dof = mesh.elem_dof_array
    coords = mesh.elem_coords
    L0 = mesh.elem_L0

    ux1 = U[dof[:, 0]]; uy1 = U[dof[:, 1]]; rz1 = U[dof[:, 2]]
    ux2 = U[dof[:, 3]]; uy2 = U[dof[:, 4]]; rz2 = U[dof[:, 5]]
    x1d = coords[:, 0] + ux1; y1d = coords[:, 1] + uy1
    x2d = coords[:, 2] + ux2; y2d = coords[:, 3] + uy2
    dx = x2d - x1d; dy = y2d - y1d
    Ld = np.hypot(dx, dy)

    theta0 = np.arctan2(coords[:, 3] - coords[:, 1], coords[:, 2] - coords[:, 0])
    thetaRaw = np.arctan2(dy, dx)
    theta = thetaRaw.copy()
    valid = ~np.isnan(th)
    if valid.any():
        d = thetaRaw[valid] - th[valid]
        d -= 2*np.pi*np.round(d/(2*np.pi))
        theta[valid] = th[valid] + d

    dth = theta - theta0
    u3 = rz1 - dth
    u6 = rz2 - dth
    u4 = Ld - L0
    eps0 = u4 / L0

    # Element-mean curvature (u6-u3)/L0 -- the EXACT measure used by
    # nlfea's get_element_strains(), hence by every reference
    # phase1_peak number this tool is validated against. (A max-over-
    # Gauss-points measure reads slightly higher; using it here would
    # make comparisons against the references apples-to-oranges.)
    kappa = (u6 - u3) / L0

    NE = np.abs(eps0) + r_o_elem * np.abs(kappa)
    x_mid = 0.5*(coords[:, 0] + coords[:, 2])
    return NE, x_mid


def _strain_profile_nodal(mesh, U, th, r_o_elem):
    """Abaqus-convention nodal strain: evaluate at each Gauss point with
    that point's own curvature kappa(xi_g), extrapolate to the element
    nodes, average across elements sharing a node.

    SUPPLEMENTARY, NOT a replacement for _strain_profile(). The element-
    mean measure there is the one every validated reference number in this
    toolchain was produced with (it matches nlfea's get_element_strains()),
    so it remains the primary peak_NE. This nodal version exists so strain
    and bending moment can be plotted on the SAME grid with the SAME
    recovery convention -- comparing an element-centroid strain against a
    nodal moment is what made the two peaks appear one node apart.
    Expect the nodal peak to read slightly HIGHER than the element-mean
    one, since extrapolation recovers the curvature peak the element
    average smooths out.
    """
    dof = mesh.elem_dof_array
    coords = mesh.elem_coords
    L0 = mesh.elem_L0
    ux1 = U[dof[:, 0]]; uy1 = U[dof[:, 1]]; rz1 = U[dof[:, 2]]
    ux2 = U[dof[:, 3]]; uy2 = U[dof[:, 4]]; rz2 = U[dof[:, 5]]
    dx = (coords[:, 2] + ux2) - (coords[:, 0] + ux1)
    dy = (coords[:, 3] + uy2) - (coords[:, 1] + uy1)
    Ld = np.hypot(dx, dy)
    theta0 = np.arctan2(coords[:, 3] - coords[:, 1], coords[:, 2] - coords[:, 0])
    thetaRaw = np.arctan2(dy, dx)
    theta = thetaRaw.copy()
    valid = ~np.isnan(th)
    if valid.any():
        d = thetaRaw[valid] - th[valid]
        d -= 2*np.pi*np.round(d/(2*np.pi))
        theta[valid] = th[valid] + d
    dth = theta - theta0
    u3 = rz1 - dth; u6 = rz2 - dth
    eps0 = (Ld - L0) / L0
    NE_gp = np.zeros((mesh.n_elems, 2))
    for g, xi in enumerate(GAUSS_XI_2):
        B3 = (3.0*xi - 1.0) / L0
        B6 = (3.0*xi + 1.0) / L0
        kap_gp = B3*u3 + B6*u6
        NE_gp[:, g] = np.abs(eps0) + r_o_elem * np.abs(kap_gp)
    return _gp_to_nodal(mesh, NE_gp)



# --- Abaqus-convention integration-point -> nodal recovery -------------------
# nlfea evaluates section response at 2 Gauss points, xi = -+1/sqrt(3), with
# curvature kappa(xi) = B3(xi)*u3 + B6(xi)*u6, B3=(3xi-1)/L0, B6=(3xi+1)/L0
# (nlfea_v4 ~line 1217). Plastic state is stored PER GAUSS POINT.
# Abaqus practice: extrapolate the integration-point values to the element
# nodes using the shape functions, then average contributions from every
# element sharing a node. For 2-point Gauss in 1D the extrapolation factors
# are 1 + sqrt(3)/2 = 1.36603 and sqrt(3)/2 - 1/2 = 0.36603.
GAUSS_XI_2 = np.array([-1.0/np.sqrt(3.0), +1.0/np.sqrt(3.0)])
_EX_A = 1.0 + np.sqrt(3.0)/2.0      # 1.36603
_EX_B = np.sqrt(3.0)/2.0 - 0.5      # 0.36603


def _gp_to_nodal(mesh, val_gp):
    """Extrapolate a per-element, per-Gauss-point quantity to nodes and
    average across elements sharing each node (Abaqus convention).

    val_gp : (n_elems, 2) array.
    Returns (val_nodal, x_nodal) ordered by ascending reference x.
    """
    n1 = _EX_A*val_gp[:, 0] - _EX_B*val_gp[:, 1]      # node at xi=-1
    n2 = -_EX_B*val_gp[:, 0] + _EX_A*val_gp[:, 1]     # node at xi=+1
    acc = {}
    for ie in range(mesh.n_elems):
        a, b = mesh.mesh_elems[ie][1], mesh.mesh_elems[ie][2]
        acc.setdefault(a, []).append(n1[ie])
        acc.setdefault(b, []).append(n2[ie])
    nodes = sorted(acc.keys(), key=lambda m: mesh.mesh_nodes[m][0])
    xs = np.array([mesh.mesh_nodes[m][0] for m in nodes])
    vs = np.array([float(np.mean(acc[m])) for m in nodes])
    return vs, xs



def _strain_profile_b31(mesh, U, th, r_o_elem):
    """Abaqus B31-EQUIVALENT nodal strain recovery.

    Rationale (Sreekanth, Session 23): Abaqus B31 is a 2-node linear beam
    with ONE integration point along the axis. Its nodal/contour output is
    therefore: IP value -> extrapolate to the element's nodes (CONSTANT,
    there being only one point) -> average over all elements sharing the
    node. For an interior node that reduces to mean(E_left, E_right).
    The companion paper's quoted maxima are Abaqus contour values, so this
    is the like-for-like basis for comparing against it.

    Chain implemented here:
      1. element value = mean of OUR two Gauss points (collapses our
         linear-kappa element to a single B31-style constant value);
      2. nodal value  = mean of the adjacent element values -- EXCEPT
         across a SECTION boundary (v1.48, this session). Averaging
         directly across a stiffness/material discontinuity is wrong and
         was found to displace the reported peak a full element off a
         thick-component junction (Sreekanth, re-checked against
         COMPONENT_GEOMETRY_DEFINITIONS.md): the boundary node's value
         gets diluted by the low-strain thick-side element, so a node one
         step further into plain pipe -- undiluted -- reads higher than
         the true boundary, and the peak search finds THAT instead. This
         is not a code quirk; Abaqus itself does not average nodal
         contour values across elements with different SECTION
         assignments by default (a section/material boundary is a
         genuine field discontinuity, not smooth data to blend). A node
         at a section boundary is therefore reported TWICE here -- once
         per side, from that side's own element only -- exactly the
         doubled-node convention Abaqus uses at such a boundary, rather
         than emitting one diluted value. This matches the shroud
         (smooth curvature field, no section change) exactly as before;
         it only changes behaviour where sec_ids actually differ.

    IMPORTANT -- this is a COMPARISON CONVENTION, not an accuracy
    improvement. It deliberately discards the within-element curvature
    variation our cubic-Hermite element genuinely resolves, in order to
    match a cruder element's output. Away from a section boundary, step 2
    is a smoothing: it averages the peak element with a lower neighbour,
    so at a point support it UNDER-reports the true peak and converges to
    it from below as h->0. The cubic-Hermite nodal value
    (_strain_profile_nodal) is the better estimate of the true continuum
    peak and converges from above; the two bracket it. Neither removes
    the mesh non-convergence documented in tech-ref 13.8.
    """
    dof = mesh.elem_dof_array
    coords = mesh.elem_coords
    L0 = mesh.elem_L0
    ux1 = U[dof[:, 0]]; uy1 = U[dof[:, 1]]; rz1 = U[dof[:, 2]]
    ux2 = U[dof[:, 3]]; uy2 = U[dof[:, 4]]; rz2 = U[dof[:, 5]]
    dx = (coords[:, 2] + ux2) - (coords[:, 0] + ux1)
    dy = (coords[:, 3] + uy2) - (coords[:, 1] + uy1)
    Ld = np.hypot(dx, dy)
    theta0 = np.arctan2(coords[:, 3] - coords[:, 1], coords[:, 2] - coords[:, 0])
    thetaRaw = np.arctan2(dy, dx)
    theta = thetaRaw.copy()
    valid = ~np.isnan(th)
    if valid.any():
        d = thetaRaw[valid] - th[valid]
        d -= 2*np.pi*np.round(d/(2*np.pi))
        theta[valid] = th[valid] + d
    dth = theta - theta0
    u3 = rz1 - dth; u6 = rz2 - dth
    eps0 = (Ld - L0) / L0
    # step 1: element value = mean over the two Gauss points
    NE_gp = np.zeros((mesh.n_elems, 2))
    for g, xi in enumerate(GAUSS_XI_2):
        kap_gp = ((3.0*xi - 1.0)/L0)*u3 + ((3.0*xi + 1.0)/L0)*u6
        NE_gp[:, g] = np.abs(eps0) + r_o_elem*np.abs(kap_gp)
    NE_el = 0.5*(NE_gp[:, 0] + NE_gp[:, 1])
    # step 2: nodal value = mean of SAME-SECTION adjacent elements only.
    # A node bordering a section change is emitted twice (once per side,
    # each from only that side's own element) instead of once, diluted.
    sec = np.array([mesh.mesh_elems[ie][3] for ie in range(mesh.n_elems)])
    n1 = dof[:, 0]//3; n2 = dof[:, 3]//3
    acc = {}   # (node, section) -> [values]
    for ie in range(mesh.n_elems):
        acc.setdefault((int(n1[ie]), int(sec[ie])), []).append(NE_el[ie])
        acc.setdefault((int(n2[ie]), int(sec[ie])), []).append(NE_el[ie])
    keys = sorted(acc.keys(), key=lambda k: (mesh.mesh_nodes[k[0]][0], k[1]))
    xs = np.array([mesh.mesh_nodes[k[0]][0] for k in keys])
    vs = np.array([float(np.mean(acc[k])) for k in keys])
    return vs, xs


def _curvature_peak(mesh, U, x_exclude_above=None):
    """Locate the integration point of maximum |curvature| from a solved
    U alone (post-hoc, no `th` continuity state available -- this is NOT
    called from inside the solve loop). Returns (kappa_at_peak, x_at_peak).

    IMPORTANT: without the solve's own accumulated `th` (element-orientation
    continuity, carried step-to-step specifically to avoid this), any
    element whose REFERENCE orientation sits at the arctan2 branch cut
    (theta0 = +/-pi -- e.g. a flat-deck element pointing in -x) can show a
    spurious ~2*pi jump in dth, corrupting u3/u6 and producing a fake
    curvature spike orders of magnitude above anything physical. Confirmed
    this session: a flat-deck element gave a raw dth ~ -2*pi and a fake
    kappa ~27 rad/m (nominal design curvature here is ~0.014 rad/m) --
    caught by comparing against 1/R as a sanity check, not by inspection.
    Fix used here: wrap dth to its nearest representative in (-pi, pi]
    before use, on the assumption that the TRUE incremental rotation from
    reference to current deformed state is the small/moderate one, not a
    near-2*pi one -- reasonable for this application (a gently-curved
    stinger passage), not a general-purpose substitute for real `th`
    tracking. Do not reuse this function inside the live solve loop.
    """
    dof = mesh.elem_dof_array
    coords = mesh.elem_coords
    L0 = mesh.elem_L0
    ux1 = U[dof[:, 0]]; uy1 = U[dof[:, 1]]; rz1 = U[dof[:, 2]]
    ux2 = U[dof[:, 3]]; uy2 = U[dof[:, 4]]; rz2 = U[dof[:, 5]]
    dx = (coords[:, 2] + ux2) - (coords[:, 0] + ux1)
    dy = (coords[:, 3] + uy2) - (coords[:, 1] + uy1)
    theta0 = np.arctan2(coords[:, 3] - coords[:, 1], coords[:, 2] - coords[:, 0])
    thetaRaw = np.arctan2(dy, dx)
    dth = thetaRaw - theta0
    dth -= 2*np.pi*np.round(dth/(2*np.pi))       # branch-cut fix, see above
    u3 = rz1 - dth; u6 = rz2 - dth

    kap_best = -1.0; x_best = None; kap_val = None
    for xi in GAUSS_XI_2:
        B3 = (3.0*xi - 1.0)/L0; B6 = (3.0*xi + 1.0)/L0
        kap_gp = B3*u3 + B6*u6
        x_gp = 0.5*(1 - xi)*coords[:, 0] + 0.5*(1 + xi)*coords[:, 2]
        mask = (x_gp < x_exclude_above - 1e-6) if x_exclude_above is not None \
               else np.ones_like(x_gp, dtype=bool)
        kap_masked = np.where(mask, np.abs(kap_gp), -1.0)
        i = int(np.argmax(kap_masked))
        if kap_masked[i] > kap_best:
            kap_best = kap_masked[i]; x_best = float(x_gp[i]); kap_val = float(kap_gp[i])
    return kap_val, x_best


def _moment_profile(mesh, U, th, ps, _return_gp=None):
    """Bending moment M(x) [N.m] per element, via fibre-stress integration
    at the COMMITTED plastic state -- matches get_moment_profile()'s
    convention exactly (J2 only; uses Gauss point index 0 as the
    representative committed state per element, same simplification the
    reference tool already uses, for direct comparability).

    M = sum(sigma_i * y_i * A_i) over fibres, sigma from
    _ep_return_mapping(eps_fib, eps_p_committed, kap_committed, E, mat).
    """
    dof = mesh.elem_dof_array
    coords = mesh.elem_coords
    L0 = mesh.elem_L0
    ux1 = U[dof[:, 0]]; uy1 = U[dof[:, 1]]; rz1 = U[dof[:, 2]]
    ux2 = U[dof[:, 3]]; uy2 = U[dof[:, 4]]; rz2 = U[dof[:, 5]]
    x1d = coords[:, 0] + ux1; y1d = coords[:, 1] + uy1
    x2d = coords[:, 2] + ux2; y2d = coords[:, 3] + uy2
    dx = x2d - x1d; dy = y2d - y1d
    Ld = np.hypot(dx, dy)
    theta0 = np.arctan2(coords[:, 3] - coords[:, 1], coords[:, 2] - coords[:, 0])
    thetaRaw = np.arctan2(dy, dx)
    theta = thetaRaw.copy()
    valid = ~np.isnan(th)
    if valid.any():
        d = thetaRaw[valid] - th[valid]
        d -= 2*np.pi*np.round(d/(2*np.pi))
        theta[valid] = th[valid] + d
    dth = theta - theta0
    u3 = rz1 - dth; u6 = rz2 - dth
    eps0_e = (Ld - L0) / L0
    kappa_e = (u6 - u3) / L0

    # v1.48 FIX (Session 23): evaluate at BOTH Gauss points, each with its
    # OWN curvature kappa(xi_g) and its OWN stored plastic state. The
    # previous version paired the ELEMENT-MEAN curvature (kappa at xi=0)
    # with the GP0-ONLY plastic state. Near a contact node the two Gauss
    # points carry very different plastic strain (the GP closest to the
    # node yields far more), so GP0 happened to be the LOW-plastic point in
    # one element and the HIGH-plastic point in its neighbour. That gave a
    # spurious single-element moment collapse (~500 kNm where ~Mp=1330 kNm
    # was correct) at whichever element had its GP0 next to the contact.
    # Strain was never affected -- it does not use the plastic state.
    M_gp = np.zeros((mesh.n_elems, 2))
    for ie in range(mesh.n_elems):
        fy, fA = mesh.elem_fibres[ie]
        mat_ep = mesh.elem_ep_mat[ie]
        nf = len(fy)
        for g, xi in enumerate(GAUSS_XI_2):
            B3 = (3.0*xi - 1.0) / L0[ie]
            B6 = (3.0*xi + 1.0) / L0[ie]
            kap_gp = B3*u3[ie] + B6*u6[ie]
            eps_fib = eps0_e[ie] + fy * kap_gp
            sigma, *_ = _ep_return_mapping(eps_fib, ps.eps_p[ie, g, :nf],
                                            ps.kap[ie, g, :nf], mat_ep.E, mat_ep)
            M_gp[ie, g] = float(np.sum(sigma * fy * fA))
    # PRIMARY: element value = mean of the two self-consistent Gauss-point
    # moments, reported at the element midpoint -- the SAME grid and the
    # same averaging philosophy as the element-mean strain in
    # _strain_profile(), so the two are directly comparable.
    #
    # Deliberately NOT the Abaqus nodal extrapolation for the primary
    # output. Extrapolating to nodes (available via _moment_profile_nodal)
    # overshoots a BOUNDED quantity: the section moment saturates
    # plastically, so linear extrapolation past the Gauss points returns
    # values above the section capacity (~2060 kNm against Mp~1330 kNm in
    # the S2-4 check). Abaqus shows the same artefact -- it is why nodal
    # stress contours can exceed yield. Nodal recovery is the right
    # convention for CONTOURING a smooth field, not for reading a peak
    # off a plastically saturated one.
    if _return_gp is not None:
        _return_gp['M_gp'] = M_gp
    x_mid = 0.5*(coords[:, 0] + coords[:, 2])
    return 0.5*(M_gp[:, 0] + M_gp[:, 1]), x_mid


def _moment_profile_nodal(mesh, U, th, ps):
    """Abaqus-convention nodal-averaged moment. SUPPLEMENTARY -- see the
    overshoot caveat in _moment_profile(). Useful for contour-style
    presentation, not for peak extraction under plasticity."""
    _M_gp_holder = {}
    M_elem, _ = _moment_profile(mesh, U, th, ps, _return_gp=_M_gp_holder)
    return _gp_to_nodal(mesh, _M_gp_holder['M_gp'])


# =============================================================================
# CORE SOLVER: one quasi-static state (step 0 or one shift), own Newton loop
# =============================================================================

def _solve_state(mesh, U, th, ps, dist, jl, anchor_dofs, slots, active,
                 n_increments, pen_mult, exempt_set, verbose, tag,
                 k_spring=0.0, reg_mult=0.0, slots_prev=None):
    """Solve to equilibrium with anchored-ramp roller targets.

    slots  : list of (name, dof_ux, dof_uy, nx, ny, dn) -- normal-
             direction contact slots for THIS step's node correspondence
             (u_out = ux*nx + uy*ny; target dn along n_hat).
    active : list[bool] per slot, carried in/out (chained across steps).
    U, th, ps : the continuous state chain -- modified in place / returned.

    Target ramp (user's staged strategy + solve_step Bug-B principle):
        target_eff(lam) = anchor_val + (dn - anchor_val)*lam
    with anchor_val = the node's current OUTWARD-NORMAL position u_out at
    step entry. A slot already at its target holds still; a slot whose
    node correspondence just shifted ramps gradually from where the pipe
    currently is to the roller surface.
    Loads (self-weight, tension) are constant at full amplitude in every
    assemble() call (assemble ignores lam internally -- tech ref §3).
    Contact release/re-contact checks use the SAME target_eff and the
    same rn convention as the Newton loop (the v1.46 contact-check
    inconsistency is thereby structurally impossible here).

    k_spring : v1.48 -- optional low-stiffness BILATERAL spring (N/m)
               applied at any slot currently INACTIVE (lifted off), along
               the SAME normal direction and toward the SAME ramped
               target as the contact formulation above, just far weaker.
               TESTED AND REJECTED for the shroud-passage NaN case
               (Session 23): because contact-release ordering feeds back
               into path-dependent J2 plasticity, even very low k_spring
               materially changes converged peak strain (non-monotonic
               with k_spring, no window found that is both stable and
               non-contaminating -- see session log). Kept for reference
               / other use cases but NOT the recommended fix; prefer
               reg_mult below. k_spring=0.0 (default) reproduces
               pre-v1.48 behaviour exactly.
    reg_mult : v1.48 (Session 23) -- Tikhonov regularization of the
               LINEAR SOLVE ONLY: adds reg_mult*K.diagonal().max() to
               every diagonal entry of Kl for the spsolve() call, with
               NO corresponding change to Fp (the force balance). This
               differs fundamentally from k_spring: it does not add a
               real force anywhere, so it cannot pull the structure away
               from true equilibrium -- it only conditions the Newton
               STEP direction at ill-conditioned iterates. Where Newton
               converges (rc<1e-3, i.e. Fp~0 at the true K), the
               regularization should be invisible in the converged
               answer, since the equilibrium condition Fint=Fext it
               converged to does not itself contain the regularization
               term. Where the true tangent K has an exact zero
               eigenvalue with zero corresponding force (a genuine
               neutral/indifferent direction -- e.g. rigid motion of an
               unsupported bridging span), reg_mult picks a definite
               (minimum-norm-step) path through it, which should not
               affect physically-meaningful quantities like peak strain.
               reg_mult=0.0 (default) reproduces pre-v1.48 behaviour
               exactly. NOT YET VALIDATED for insensitivity -- run a
               sweep before trusting results (same standing rule as
               k_spring).
    """
    anchor_vals = np.array([U[dux]*nx + U[duy]*ny
                             for (_, dux, duy, nx, ny, _dn) in slots])
    status = 'ok'
    if _DBG['on']:
        for si, (nm, dux, duy, nx, ny, dn) in enumerate(slots):
            _DBG['entry'].append(dict(tag=tag, slot=nm, active=bool(active[si]),
                                       anchor=float(anchor_vals[si]), dn=float(dn),
                                       jump=float(dn - anchor_vals[si])))

    # ---- ADAPTIVE INCREMENT LOOP (v1.48, Session 23) ----------------------
    # Was a fixed `for inc in range(1, n_increments+1)` march. Root cause of
    # the passage "walls" (tech-ref 13.3, and every Phase-2 anchor): Newton
    # genuinely DIVERGES at certain shifts -- |dU| grows ~10x per iteration
    # -- but the convergence measure rc = max|Fp|/max|Fint| is structurally
    # incapable of detecting it: as U blows up, Fint blows up with it, so
    # Fp ~ -Fint and rc PINS TO EXACTLY 1.000. The test never fires, the
    # loop runs all 30 iterations getting worse, and the step is lost.
    # Fix = what Abaqus does on a convergence failure: detect divergence
    # from |dU| growth, roll the state back to the start of the increment,
    # HALVE the increment, and retry. A false positive costs only time
    # (the smaller increment still solves correctly), so the detector is
    # deliberately allowed to be trigger-happy.
    # Converged paths are unaffected: dlam is capped at its original value,
    # so when nothing diverges the lam schedule is the old one.
    lam_done = 0.0
    dlam = 1.0 / n_increments
    dlam_min = dlam / 64.0          # allows 6 halvings before giving up
    inc = 0
    while lam_done < 1.0 - 1e-12:
        inc += 1
        lam = min(1.0, lam_done + dlam)
        U_snap = U.copy()
        th_snap = th.copy()
        ps_snap = ps.copy() if ps is not None else None
        active_snap = list(active)
        ps_inc_start = ps.copy() if ps is not None else None
        ps_trial = ps_inc_start
        released_this_inc = set()
        inc_failed = False

        for cpass in range(8):
            rc = np.inf
            for it in range(30):
                K, Fint, Fext, th, ps_trial = assemble(
                    mesh, U, th, dist, jl, lam, plastic_state=ps_inc_start)
                K_diag_max = float(K.diagonal().max())
                pen = K_diag_max * pen_mult
                Kl = K.tolil(); Fp = Fext - Fint

                for d in anchor_dofs:
                    Kl[d, d] += pen; Fp[d] += pen * (0.0 - U[d])

                # v1.48 (Session 23): CONSTRAINT-TRANSITION RAMP.
                # Root cause of the passage walls (tech-ref 13.10) was that
                # `lam` ramped the roller TARGET but not the constraint SET:
                # at a shift the previously-held node was released at full
                # strength in one go, dumping its reaction and leaving a
                # residual independent of lam (hence immune to cutback and
                # to reg_mult). Fix: when slots_prev is supplied, fade the
                # OLD node's constraint out as pen*(1-lam) while the NEW
                # node's fades in as pen*lam, so the reaction transfers
                # continuously. Total penalty stiffness per roller is
                # conserved. slots_prev=None reproduces the old behaviour
                # exactly (w_new=1, no old contribution) -- used for step 0.
                if slots_prev is None:
                    w_new, w_old = 1.0, 0.0
                else:
                    w_new, w_old = lam, 1.0 - lam

                for si, (name, dux, duy, nx, ny, dn) in enumerate(slots):
                    te = anchor_vals[si] + (dn - anchor_vals[si]) * lam
                    rn = te - (U[dux]*nx + U[duy]*ny)
                    if active[si]:
                        pn = pen * w_new
                        Kl[dux, dux] += pn*nx*nx; Kl[duy, duy] += pn*ny*ny
                        Kl[dux, duy] += pn*nx*ny; Kl[duy, dux] += pn*nx*ny
                        Fp[dux] += pn*nx*rn; Fp[duy] += pn*ny*rn
                    elif k_spring > 0.0:
                        Kl[dux, dux] += k_spring*nx*nx; Kl[duy, duy] += k_spring*ny*ny
                        Kl[dux, duy] += k_spring*nx*ny; Kl[duy, dux] += k_spring*nx*ny
                        Fp[dux] += k_spring*nx*rn; Fp[duy] += k_spring*ny*rn

                # OLD node correspondence, faded out over the increment.
                # Its target is its OWN previous target dn_p -- the node is
                # already sitting there from the converged previous step, so
                # at lam=0 this contributes zero force and equilibrium is
                # preserved exactly.
                if slots_prev is not None and w_old > 1e-12:
                    for si, (nm_p, dux_p, duy_p, nx_p, ny_p, dn_p) in enumerate(slots_prev):
                        if not active[si]:
                            continue
                        po = pen * w_old
                        rn_p = dn_p - (U[dux_p]*nx_p + U[duy_p]*ny_p)
                        Kl[dux_p, dux_p] += po*nx_p*nx_p
                        Kl[duy_p, duy_p] += po*ny_p*ny_p
                        Kl[dux_p, duy_p] += po*nx_p*ny_p
                        Kl[duy_p, dux_p] += po*nx_p*ny_p
                        Fp[dux_p] += po*nx_p*rn_p
                        Fp[duy_p] += po*ny_p*rn_p

                # v1.48: optional Tikhonov regularization of the linear
                # solve ONLY -- added to Kl's diagonal here, deliberately
                # NOT to Fp, so it conditions the Newton step direction
                # without injecting any force. reg_mult is scaled by the
                # RAW beam stiffness (K_diag_max, pre-pen_mult), not the
                # penalty, since it is meant to be tiny relative to real
                # structural stiffness. See _solve_state docstring.
                if reg_mult > 0.0:
                    Kl_solve = Kl.tocsr()
                    Kl_solve.setdiag(Kl_solve.diagonal() + reg_mult * K_diag_max)
                else:
                    Kl_solve = Kl.tocsr()
                dU = spsolve(Kl_solve, Fp)
                fm = max(float(np.max(np.abs(Fint))), 1.0)
                rc = float(np.max(np.abs(Fp[3:]))) / fm
                U += dU
                # v1.48: catch BOTH outright NaN and silent divergence to
                # absurd-but-finite values (Session 23 -- S2-1 step3 hit
                # ~6e24% strain with status='ok' because a finite-but-
                # insane U passes np.isnan() cleanly). 100 m is a
                # generously loose bound -- the whole stinger model is
                # ~50m long, so any nodal displacement beyond that is
                # unambiguously divergence, not a real solution.
                if _DBG['on']:
                    _DBG['iter'].append(dict(tag=tag, inc=inc, cpass=cpass, it=it,
                                              rc=float(rc), dUmax=float(np.max(np.abs(dU))),
                                              dUdof=int(np.argmax(np.abs(dU))),
                                              nactive=int(sum(active))))
                # Divergence detector. |dU| > 1 m is ~3x the largest
                # legitimate step ever observed in a healthy solve (~0.35 m
                # at a shift entry) and ~1.2 element lengths, so it fires
                # early in a runaway while leaving good solves alone.
                if (np.isnan(U).any() or np.max(np.abs(U)) > 100.0
                        or float(np.max(np.abs(dU))) > 1.0):
                    inc_failed = True
                    break
                if it > 0 and rc < 1e-3:
                    break

            if inc_failed:
                break

            # --- contact check at this increment's converged state ---
            # Same anchored target_eff and rn convention as the Newton
            # loop above. RELEASE test is on the REACTION (pen*rn), not
            # the gap: an ACTIVE penalty constraint holds |rn| ~ R/pen
            # (~1e-10 m) at convergence, so a gap threshold can never
            # fire -- the SIGN of that tiny residual gap is what encodes
            # push (rn>0, valid) vs pull (rn<0, tension). Caught in
            # validation: with a gap test nothing ever released, unlike
            # every reference solve (VR1-VR3 lift in all of them).
            # RE-CONTACT test for an inactive slot IS gap-based (the
            # constraint isn't enforced, so the gap is real).
            changed = False
            for si, (name, dux, duy, nx, ny, dn) in enumerate(slots):
                te = anchor_vals[si] + (dn - anchor_vals[si]) * lam
                rn_eff = te - (U[dux]*nx + U[duy]*ny)
                if active[si]:
                    R_n = pen * rn_eff        # + = pushing outward (valid)
                    if R_n < -1.0 and si not in exempt_set:
                        active[si] = False
                        released_this_inc.add(si)
                        changed = True
                        if verbose:
                            print(f"    [{tag}] inc {inc}: {name} released "
                                  f"(tensile R={R_n:.3e} N)")
                else:
                    if si not in released_this_inc and rn_eff >= -1e-9:
                        active[si] = True
                        changed = True
                        if verbose:
                            print(f"    [{tag}] inc {inc}: {name} re-contacted")
            if not changed:
                break

        if inc_failed:
            # roll back to the start of this increment and try a smaller one
            U = U_snap
            th = th_snap
            ps = ps_snap
            active = active_snap
            dlam *= 0.5
            if dlam < dlam_min:
                return U, th, ps, active, (
                    f'CUTBACK EXHAUSTED at lam={lam_done:.4f} '
                    f'(dlam {dlam:.2e} < min {dlam_min:.2e})')
            if verbose:
                print(f"    [{tag}] attempt {inc}: Newton diverging at "
                      f"lam={lam:.4f} -> cutback to dlam={dlam:.4e}")
            continue

        ps = ps_trial   # commit once, after Newton + contact settle
        lam_done = lam
        dlam = min(1.0 / n_increments, dlam * 1.4)    # cautious re-growth

    return U, th, ps, active, status


# =============================================================================
# DRIVER
# =============================================================================

_DBG = {'on': False, 'entry': [], 'iter': [], 'contact': []}


def shroud_offset_at(x, centre_x, L1, L2, V, D_o, taper='linear'):
    """CL_lift profile of a Type B1 shroud/offset element (EA-O), per
    COMPONENT_GEOMETRY_DEFINITIONS.md §2.4-2.6.

    CRITICAL CONVENTION (corrected Session 23): `V` is the offset depth
    measured from the PIPE CENTRELINE, not from the pipe OD. The pipe
    already rests OD/2 above the roller in the plain-pipe baseline, so
    the elevation the model must actually apply is

        CL_lift = V - OD_pipe/2                       (doc §2.6)

    NOT V itself. Applying the full V (the pre-correction behaviour)
    over-elevated the pipe by OD/2 everywhere under the deep section --
    a 33% over-lift at V=2D -- and inflated strains accordingly.

    Shape, symmetric about centre_x (doc §2.6 explicit formula, with the
    pipe centreline at y=0 and the contact curve below it):
      deep section |d| <= L1/2      : contact at y = -V      -> lift = V - OD/2
      taper  L1/2 < |d| <= L1/2+L2  : contact ramps linearly from y = -V
                                       (inner) to y = -OD/2 (outer)
                                       -> lift ramps (V-OD/2) -> 0
      outside  |d| > L1/2+L2        : no shroud; contact at y = -OD/2
                                       -> lift = 0
    Because the taper terminates flush with the pipe OD, the shroud's own
    thickness goes to ZERO at each taper outer end -- it must not end on
    a finite step/flat face (doc §2.4 taper-outer-boundary rule).

    V < OD/2 is geometrically invalid (the contact surface would lie
    inside the pipe wall); V == OD/2 degenerates to a zero-thickness
    wrap with no elevation effect.
    """
    lift = V - D_o / 2.0
    if lift < -1e-12:
        raise ValueError(f"shroud V={V:.4f} m is less than OD/2={D_o/2:.4f} m -- "
                          "V is measured from the pipe CENTRELINE "
                          "(COMPONENT_GEOMETRY_DEFINITIONS.md §2.4), so V < OD/2 "
                          "would place the contact surface inside the pipe wall")
    d = abs(x - centre_x)
    if d <= L1 / 2.0:
        return lift
    if L2 > 0.0 and d <= L1 / 2.0 + L2:
        frac = (d - L1 / 2.0) / L2       # 0 at plateau edge -> 1 at taper outer end
        if taper == 'cosine':
            return lift * (0.5 + 0.5 * np.cos(np.pi * frac))
        return lift * (1.0 - frac)
    return 0.0


def run_passage_v2(R=70.0, D_o=0.4064, t=0.021,
                   thick_component=None,       # dict: OD, t, length
                   shroud_component=None,      # dict: V, L1, L2 (Type B1, v1.48)
                   component_spacing=None,     # clear gap to a 2nd identical
                                                # component (Study 3); None =
                                                # single-component (Study 1/2)
                   n_shifts=None,
                   material='J2', tension_mt=100.0, self_weight=True,
                   n_sr=6, n_vr=3, spacing=8.0,
                   n_increments_step0=40, n_increments_shift=20,
                   section='polar', n_points_polar=8, n_fibres=20,
                   ref_centre_x=None, verbose=True, never_release=None,
                   k_spring=0.0, reg_mult=0.0, elem_len=None,
                   pen_step0=1e8, pen_shift=1e4, thick_offset_x=0.0):
    """Fixed-mesh passage sweep with full state chaining.

    Default sweep (memory rule #30 equivalent, element-driven): component
    reference centre at [SR2 + L/2] (leading edge at SR2); each shift
    moves the roller pattern one element toward the vessel, i.e. the
    component advances ~one element toward the tip relative to the
    rollers; default n_shifts makes total travel ~= component length
    (trailing edge at SR2).

    component_spacing (Study 3): when set, builds a SECOND component,
    identical spec to `thick_component`, positioned with a clear gap of
    `component_spacing` beyond the first component's trailing edge
    (toward +x / the vessel side). Both regions get sec_id=2 permanently
    (never flip, same as the single-component case). The FIRST
    (tip-side) component keeps the standard leading-edge-at-SR2
    convention; the sweep/shift mechanics are otherwise unchanged.
    NOTE: component_spacing is thick_component-only; not yet wired to
    shroud_component.

    shroud_component (Type B1, v1.48): dict {'V','L1','L2'} -- a purely
    GEOMETRIC roller-contact elevation (see shroud_offset_at()), the
    IJRASET companion paper's EA-O offset/shroud element. Unlike
    thick_component, this does NOT change sec_ids or pipe section
    anywhere -- the pipe stays plain-pipe stiffness/section throughout;
    only the roller dn target is lifted. Uses the SAME leading-edge-at-
    SR2 / per-shift-travel convention as thick_component, with L_comp
    taken as L1+2*L2 (full footprint including both tapers) when
    thick_component is absent. May be combined with thick_component
    (Type C1, offset element over a thick-pipe body): CL_lift is then
    additive (thick contribution when a roller's node falls inside the
    thick component's fixed range, PLUS the continuous shroud
    contribution at that node's x) -- in that combined case L_comp is
    taken from thick_component (matching the existing convention) and
    shroud_component's centre tracks the same reference position unless
    ref_centre_x is overridden. At least one of thick_component /
    shroud_component must be provided.

    k_spring (v1.48): optional low-stiffness bilateral spring (N/m)
    applied at any roller slot currently inactive (lifted off) -- see
    _solve_state() docstring for the full rationale. Default 0.0
    reproduces pre-v1.48 behaviour exactly (no change to any existing
    call). Introduced specifically to regularize against the singular-K
    NaN failure mode seen when several rollers release simultaneously
    under a shroud_component sweep; NOT YET VALIDATED as insensitive to
    its own value -- run a sensitivity sweep before trusting results
    obtained with k_spring>0.

    k_spring (v1.48): see _solve_state() docstring -- TESTED AND REJECTED
    for the shroud-passage NaN case; kept for reference, not recommended.

    reg_mult (v1.48): Tikhonov regularization of the linear solve only
    (see _solve_state() docstring) -- the RECOMMENDED stabilizer for the
    shroud-passage NaN failure mode. Default 0.0 reproduces pre-v1.48
    behaviour exactly. NOT YET VALIDATED as insensitive to its own
    value -- run a sensitivity sweep before trusting results.

    Returns dict: steps (list of per-step records), mesh, sec_ids, allc.
    """
    if material != 'J2':
        raise ValueError("run_passage_v2 is J2-only (chaining is its purpose; "
                          "RO is banned for passage studies per standing rule)")
    tc = thick_component
    sc = shroud_component
    if tc is None and sc is None:
        raise ValueError("at least one of thick_component (OD, t, length) or "
                          "shroud_component (V, L1, L2) is required")
    if component_spacing is not None and tc is None:
        raise ValueError("component_spacing (2-component sweep) requires "
                          "thick_component; not yet wired to shroud_component-only calls")
    two_comp = component_spacing is not None

    # ---- fixed geometry (n_sr + 1 buffer span so shifted associations
    #      have room; the buffer roller is exempt from release) ----
    #      Buffer is on the VESSEL side (n_vr): under the bn-shift
    #      convention the binding limit is running past the anchor
    #      (node < 2), so long sweeps need generous n_vr.
    n_sr_total = n_sr + 1
    nodes, rnid, dn_map, dtheta, nid, allc = _build_geometry(
        R, n_sr_total, n_vr, spacing, D_o, elem_len=elem_len)
    nodes_ref, rnid_ref = nodes, rnid      # reference grid (shift semantics)
    x_sr2 = allc[n_vr + 2][0]
    # L_comp: thick_component's own length if present (existing convention,
    # unaffected by adding a shroud on top of it); otherwise the shroud's
    # full footprint (deep section + both tapers) for a shroud-only call.
    L_comp = tc['length'] if tc is not None else (sc['L1'] + 2.0 * sc['L2'])
    if ref_centre_x is None:
        ref_centre_x = x_sr2 + L_comp / 2.0     # leading edge at SR2

    # Component 1 (tip-side, leading): [ref_centre_x - L/2, + L/2], offset
    # by thick_offset_x (v1.48 addition, C1 studies). When BOTH tc and sc
    # are supplied, thick_offset_x lets the thick component's own centre
    # sit anywhere within (or outside) the shroud's deep section without
    # moving the shroud's own reference point / CL_lift profile. Default
    # 0.0 is fully backward-compatible (thick component centred on
    # ref_centre_x, as before -- verified by regression, tech-ref 13.19).
    # comp_ranges drives sec_ids / self-weight and is only meaningful when
    # a thick_component is present (shroud never changes section); an
    # empty list is safe (no element gets sec_id=2) for shroud-only calls.
    c1_centre = ref_centre_x + thick_offset_x
    c1_lo, c1_hi = c1_centre - L_comp/2.0, c1_centre + L_comp/2.0
    comp_ranges = [(c1_lo, c1_hi)] if tc is not None else []
    if two_comp:
        # Component 2 (vessel-side, trailing): starts `component_spacing`
        # beyond component 1's trailing edge.
        c2_lo = c1_hi + component_spacing
        c2_hi = c2_lo + L_comp
        comp_ranges.append((c2_lo, c2_hi))

    # v1.48 correction (this turn, tech-ref 13.25): _build_geometry's
    # snap_x capability existed but was never wired up here, so every
    # thick_component boundary was silently rounded to the nearest whole
    # element on a UNIFORM grid -- 81% of nominal length realized for a
    # 2.5D component at the standard 2xOD mesh (confirmed). Rebuild the
    # mesh now that comp_ranges is known, snapping a node exactly onto
    # each thick-component boundary -- the SAME thing Abaqus's own
    # adaptive mesher does by default. Cheap (pure geometry, no solve) so
    # a second _build_geometry call is negligible cost. shroud_component
    # alone needs no snapping: V is evaluated continuously at any x via
    # shroud_offset_at, not tied to a binary per-element section the way
    # thick_component's sec_id is.
    if tc is not None:
        snap_pts = [b for rng in comp_ranges for b in rng]
        nodes, rnid, dn_map, dtheta, nid, allc = _build_geometry(
            R, n_sr_total, n_vr, spacing, D_o, elem_len=elem_len,
            snap_x=snap_pts)   # nodes_ref / rnid_ref intentionally kept

    # Mesh-extent check (fail loudly, matching §12.7's design goal,
    # rather than silently building an incomplete component 2).
    x_mesh_max = max(n.x for n in nodes)
    if two_comp and comp_ranges[-1][1] > x_mesh_max:
        raise ValueError(
            f"component_spacing={component_spacing} pushes the 2nd "
            f"component's trailing edge to x={comp_ranges[-1][1]:.2f}, "
            f"beyond the mesh extent (x_max={x_mesh_max:.2f}). Increase "
            f"n_vr or reduce component_spacing.")

    # element length local to SR2 span (for travel reporting / default shifts)
    elem_len_sr2 = abs(allc[n_vr + 2][0] - allc[n_vr + 1][0]) / max(
        1, int(round(spacing / (elem_len if elem_len is not None else 2.0 * D_o))))
    if n_shifts is None:
        n_shifts = max(2, int(round(L_comp / elem_len_sr2)))

    # ---- permanent sections ----
    xn = np.array([n.x for n in nodes])
    x_mids = 0.5*(xn[:-1] + xn[1:])
    sec_ids = [2 if any(lo <= xm <= hi for (lo, hi) in comp_ranges) else 1
               for xm in x_mids]

    # SEC2 / thick section props: only meaningful when a thick_component is
    # present (sec_ids never take value 2 for a shroud-only call, so these
    # are never actually sampled in that case -- but SEC2 must still exist
    # as a valid section object for the model, hence the plain-pipe fallback).
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
    model = Model(nodes=nodes, elements=els, sections=[SEC1, SEC2],
                  materials=[MAT])
    mesh = MeshedStructure(model)

    # ---- constant loads (full amplitude, every call, all steps) ----
    A_plain = np.pi/4*(D_o**2 - (D_o - 2*t)**2)
    A_thick = np.pi/4*(OD_tc**2 - (OD_tc - 2*t_tc)**2)
    w_plain = RHO_STEEL * A_plain * G
    w_thick = RHO_STEEL * A_thick * G
    dist = {}
    if self_weight:
        for e in els:
            mi = mesh.user_elem_to_mesh[e.id][0]
            dist[mi] = (0.0, w_thick if sec_ids[e.id-1] == 2 else w_plain)

    jl = []
    if tension_mt > 0:
        T_N = tension_mt * 1e3 * G
        # Departure angle at the ACTUAL tip node, which sits at the last
        # (buffer) station SR{n_sr_total} -- using n_sr here instead was a
        # bug caught in first validation: tension applied at the SR7-tip
        # node with SR6's tangent creates a spurious transverse tip force
        # and a false strain concentration at SR6 (2.46% vs ~0.83% ref).
        theta_n = (n_sr_total - 1) * dtheta
        jl = [(mesh.user_node_to_mesh[nid], -T_N*np.cos(theta_n),
               +T_N*np.sin(theta_n), 0.0)]

    anchor_dofs = [3*mesh.user_node_to_mesh[1] + k for k in range(3)]

    # r_o per mesh element (for strain extraction)
    r_o_elem = np.array([ (OD_tc/2 if mesh.mesh_elems[ie][3] == 2 else D_o/2)
                           for ie in range(mesh.n_elems) ])
    x_vr1 = allc[1][0]

    # ---- roller slot table builder (per shift) ----
    # Each slot is a NORMAL-DIRECTION contact constraint (the validated
    # run_slay radial formulation): penalty acts only along the roller's
    # normal n_hat, leaving tangential slide FREE. This is essential at
    # steep stinger stations: by SR6 the tangent is ~33 deg and material
    # points slide ~1-2 m tangentially over the rollers (arc length vs
    # chord); a uy-only constraint fights that slide and was measured in
    # first validation to create a spurious ~2.4% strain concentration
    # at SR6 (vs ~0.29% pure-arc bending). Deck stations use
    # n_hat=(0,-1), which reduces the same formulas to the uy-only case.
    #   u_out = ux*nx + uy*ny ; rn = target - u_out
    #   contact valid: rn >= 0 (roller pushing outward), tension: rn < 0.
    slot_names = ([f'VR{j}' for j in range(1, n_vr+1)] + ['SR1'] +
                  [f'SR{i}' for i in range(2, n_sr_total+1)])
    # v1.48 (this turn): base_nodes / the shift->node mapping must use the
    # REFERENCE (unsnapped) grid. Snapping inserts extra nodes in one
    # span, so `bn - shift` on the SNAPPED numbering advances a roller by
    # a SHORTER physical distance near the component than elsewhere --
    # i.e. adding the snap silently changed what a shift MEANS, and
    # node-based/sliding diverged past step 1 (1.131% vs 0.809% at step2,
    # observed). Keep the semantics on the reference grid, then map the
    # resulting reference position onto the nearest ACTUAL node.
    base_nodes = [rnid_ref[s] for s in range(1, len(allc))]
    _x_ref_arr = np.array([n.x for n in nodes_ref])
    _x_act_arr = np.array([n.x for n in nodes])

    def _ref_to_actual_node(p_ref):
        i = max(0, min(int(round(p_ref)) - 1, len(_x_ref_arr) - 1))
        x_t = _x_ref_arr[i]
        return int(np.argmin(np.abs(_x_act_arr - x_t))) + 1     # stations 1..end
    slot_geom = []                                            # (nx, ny, dn)
    for s in range(1, len(allc)):
        if s <= n_vr + 1:                                     # VR1..VR3, SR1
            slot_geom.append((0.0, -1.0, 0.0))
        else:                                                 # SR2..SR{total}
            k = s - n_vr                                      # SR index (2..)
            theta_k = (k - 1) * dtheta
            nx = -np.sin(theta_k); ny = -np.cos(theta_k)
            slot_geom.append((nx, ny, allc[s][1] * ny))
    exempt_set = {len(slot_names) - 1}                        # last (buffer) SR
    if never_release is None:
        # v1.49 (Session 24, Sreekanth): match Abaqus reference model --
        # only the 2 vessel rollers nearest SR1 (VR{n_vr-1}, VR{n_vr}) are
        # genuine one-sided (unidirectional) contact and may release; every
        # OTHER vessel roller (VR1..VR{n_vr-2}) is bidirectional/bilateral
        # (no-uplift support) -- permanently active, never released. VR0
        # is the separate fixed anchor node, not in this slots list at all.
        never_release = [f'VR{i}' for i in range(1, n_vr - 1)]
    if never_release:
        exempt_set |= {slot_names.index(nm) for nm in never_release}

    def make_slots(shift):
        # §9.34 (v1.40) thick-pipe roller contact offset: a roller whose
        # CURRENT contact node lies within a (fixed) component extent
        # contacts that component's larger outer surface, so its target is
        # offset outward by CL_lift = (OD_thick - OD_plain)/2 along n_hat
        # (exact replication of run_slay's dn = y*ny + CL_lift with
        # V = OD_thick/2). Evaluated PER SHIFT because the roller-node
        # correspondence moves while the component(s) do not. Missing this
        # was caught in validation: without it the component rides on the
        # plain-pipe arc line and the local kink into the adjacent plain
        # pipe -- the governing effect at the junction -- is absent
        # (0.686% vs 0.827-0.887% references). Generalized to comp_ranges
        # (Study 3): a roller lands the offset if it falls within EITHER
        # component's extent.
        #
        # v1.48: shroud_component (Type B1) adds a SECOND, continuous
        # contribution -- shroud_offset_at() -- evaluated at each node's
        # actual x. Both comp_ranges and the shroud centre are FIXED in
        # space (built once from ref_centre_x, outside this function); it
        # is the roller-slot-to-node correspondence (bn - shift) that
        # moves per shift, so nx_node already reflects the correct
        # "current" position without re-deriving a travelled centre here.
        # Additive with the thick CL_lift so Type C1 (offset over thick
        # pipe) falls out of the same mechanism with no special-casing.
        CL_lift_thick = (tc['OD'] - D_o) / 2.0 if tc is not None else 0.0
        ranges_eps = [(lo - 1e-6, hi + 1e-6) for (lo, hi) in comp_ranges]
        out = []
        for si, (name, bn, (nx, ny, dn)) in enumerate(zip(slot_names, base_nodes, slot_geom)):
            # DIRECTION CONVENTION (re-derived from scratch, Session 23,
            # after a shroud deformed-plot review raised a concern that
            # the component was travelling the wrong way):
            #   node id increases  =>  reference x DECREASES (toward tip),
            #   because _build_geometry lays stations VR0 (highest x) ->
            #   SR_last (most negative x) and numbers nodes along them.
            # So bn - shift assigns roller `name` a node that is
            # progressively further toward the VESSEL (+x) in the MESH
            # frame -- i.e. in the pipeline's own frame (which is what
            # the deformed plot shows), the ROLLERS travel toward the
            # vessel / right, and the component (fixed in mesh coords)
            # therefore travels toward the tip / left relative to them.
            # That is the correct pay-out sense, so bn - shift is RIGHT
            # and is retained.
            # A Session-23 attempt to "fix" this to bn + shift was WRONG
            # and has been reverted: the reported symptom was a PLOTTING
            # bug (roller markers were drawn at their fixed spatial allc
            # station positions instead of at the mesh position of the
            # node they currently constrain, so no relative travel was
            # visible at all), not a mechanism bug. See plot_step_deformed.
            node = _ref_to_actual_node(bn - shift)             # toward vessel
            if node < 2:
                raise ValueError(f"shift {shift} pushes {name} past the anchor "
                                  f"(increase n_vr for more vessel-side buffer)")
            nx_node = nodes[node - 1].x
            in_comp = any(lo <= nx_node <= hi for (lo, hi) in ranges_eps)
            dn_shroud = (shroud_offset_at(nx_node, ref_centre_x, sc['L1'], sc['L2'],
                                           sc['V'], D_o,
                                           taper=sc.get('taper', 'linear'))
                         if sc is not None else 0.0)
            dn_eff = dn + (CL_lift_thick if in_comp else 0.0) + dn_shroud
            mi = mesh.user_node_to_mesh[node]
            out.append((name, 3*mi, 3*mi + 1, nx, ny, dn_eff))
        return out

    def record(step_idx, shift, U, th, ps, active, slots, status):
        # PRIMARY STRAIN CONVENTION (v1.48, Session 23): Abaqus
        # B31-equivalent nodal recovery -- see _strain_profile_b31().
        # The companion paper's maxima are Abaqus B31 contour values, so
        # this is the like-for-like basis: it reproduces them to ~4%
        # mean, AND it places the peak ON the roller node (where Abaqus
        # shows it) instead of half an element away, which the raw
        # element-centroid measure could not do.
        # Cubic-Hermite nodal extrapolation was ruled OUT as the paper's
        # convention: it overshoots by ~88% (it resolves a genuinely
        # higher true peak that a B31 mesh cannot represent).
        # The element-mean measure is retained as NE_elem/peak_NE_elem
        # for continuity with all pre-Session-23 reference numbers.
        NE_el, xm_el = _strain_profile(mesh, U, th, r_o_elem)
        NE_n, x_n = _strain_profile_nodal(mesh, U, th, r_o_elem)
        NE, xm = _strain_profile_b31(mesh, U, th, r_o_elem)   # <- primary
        mask = xm < x_vr1 - 1e-6           # exclude VR0-VR1 anchor span
        pk_i = int(np.argmax(NE * mask))
        # SR2-local peak: the component-passage region of interest. The
        # ROLLER pattern's node correspondence has shifted by `shift`
        # elements toward the vessel, so the mesh point currently under
        # "SR2" sits ~shift*elem_len further +x than its reference
        # station -- centre the local window there.
        x_sr2_now = x_sr2 + shift * elem_len_sr2
        loc = np.abs(xm - x_sr2_now) < 4.0
        pk_l = int(np.argmax(NE * loc)) if loc.any() else pk_i

        # Bending moment: paper's own convention (Table XXI/XXIV) is peak
        # moment near COMPONENT MIDSPAN, not the junction -- a physically
        # different location from the strain peak. Search over the
        # component's own (fixed) element range for max |M|.
        M, xm_M = _moment_profile(mesh, U, th, ps)
        comp_mask = np.array(sec_ids) == 2
        if comp_mask.any():
            pk_m = int(np.argmax(np.abs(M) * comp_mask))
            peak_M = float(M[pk_m]); peak_M_x = float(xm_M[pk_m])
        else:
            peak_M = float(M[np.argmax(np.abs(M))])
            peak_M_x = float(xm_M[np.argmax(np.abs(M))])

        # v1.48: shroud region-resolved peaks (Fig. 45 convention). The
        # deep section [centre-L1/2, centre+L1/2] is split into thirds;
        # x increases toward the vessel in this geometry (SR index
        # increases toward the tip / touchdown, i.e. decreasing x), so
        # X2 = catenary/tip-side third (lower x), X3 = midspan,
        # X4 = vessel-side third (upper x). X1/X5 (v1.48, this session)
        # = the taper zones themselves (width L2 each), tip-side and
        # vessel-side of the plateau respectively -- added after finding
        # the model's actual overall peak sits in the taper, NOT the
        # plateau, for the S2-6 validation case (same junction-kink
        # mechanism as the existing thick-component §9.34 finding: a
        # sharp linear-taper/plateau corner concentrates curvature at
        # the corner). Table XXIX's own X1/X5 description ("taper +
        # outside shroud, governed by plain-pipe catenary") assumes the
        # taper itself is NOT where the peak occurs -- our X1/X5 here is
        # the taper zone specifically, so a high X1/X5 reading is itself
        # the signal that this assumption may not hold for our (sharp-
        # corner) shroud geometry. NOT YET VALIDATED against the paper
        # -- treat as hypothesis until checked against Table XXXIV.
        region_peaks = {}
        if sc is not None:
            lo, hi = ref_centre_x - sc['L1']/2.0, ref_centre_x + sc['L1']/2.0
            third = sc['L1'] / 3.0
            L2 = sc['L2']
            bounds = {'X1': (lo - L2, lo),
                      'X2': (lo, lo + third),
                      'X3': (lo + third, hi - third),
                      'X4': (hi - third, hi),
                      'X5': (hi, hi + L2)}
            for rname, (rlo, rhi) in bounds.items():
                rmask = (xm >= rlo) & (xm <= rhi)
                if rmask.any():
                    pk_r = int(np.argmax(NE * rmask))
                    region_peaks[rname] = {'peak_NE': float(NE[pk_r]),
                                            'peak_x': float(xm[pk_r])}
                else:
                    region_peaks[rname] = {'peak_NE': None, 'peak_x': None}

        return {
            'step': step_idx, 'shift_elements': shift,
            'travel_m': shift * elem_len_sr2,
            # v1.48: per-slot contact info for plotting. `mi` is the MESH
            # node this roller currently constrains -- which is what moves
            # with `shift` (the roller's own spatial station is fixed).
            # Drawing rollers at allc (the fixed station) instead of here
            # was the Session-23 plotting bug that made it look like the
            # component travelled the wrong way.
            'slot_info': [{'name': nm, 'mi': dux // 3, 'nx': nxs, 'nys': nys,
                            'dn': dnv, 'active': bool(active[i])}
                           for i, (nm, dux, duy, nxs, nys, dnv) in enumerate(slots)],
            # v1.48: full profiles retained so plots can show strain and
            # bending-moment panels without re-deriving r_o_elem.
            # PRIMARY (B31-equivalent nodal) -- what peak_NE/peak_x use
            'NE_profile': NE.copy(), 'x_profile': xm.copy(),
            'M_profile': M.copy(), 'xM_profile': xm_M.copy(),
            # element-mean, retained for continuity with pre-Session-23 refs
            'NE_elem': NE_el.copy(), 'x_elem': xm_el.copy(),
            'peak_NE_elem': float(np.max(NE_el*(xm_el < x_vr1 - 1e-6))),
            # cubic-Hermite nodal -- UPPER bracket on the true peak
            'NE_nodal': NE_n.copy(), 'x_nodal': x_n.copy(),
            'peak_NE_nodal': float(np.max(NE_n)),
            'peak_x_nodal': float(x_n[int(np.argmax(NE_n))]),
            'peak_NE': float(NE[pk_i]), 'peak_x': float(xm[pk_i]),
            'peak_NE_sr2': float(NE[pk_l]), 'peak_x_sr2': float(xm[pk_l]),
            'region_peaks': region_peaks,
            'peak_M': peak_M, 'peak_M_x': peak_M_x,
            'kap_max': float(ps.kap.max()) if ps is not None else None,
            'active': [slots[i][0] for i in range(len(slots)) if active[i]],
            'inactive': [slots[i][0] for i in range(len(slots)) if not active[i]],
            'status': status, 'U': U.copy(),
        }

    # ---- state chain ----
    U  = np.zeros(mesh.n_dofs)
    th = np.full(mesh.n_elems, np.nan)      # nan ONCE, at exact U=0 (safe)
    ps = PlasticState(mesh.n_elems, n_fib_active)
    active = [True] * len(slot_names)
    steps = []

    # ---- STEP 0: virgin drape at reference position ----
    if verbose:
        print(f"--- step 0 (virgin drape, ref_centre_x={ref_centre_x:.3f}, "
              f"leading edge at SR2) ---")
    slots0 = make_slots(0)
    U, th, ps, active, status = _solve_state(
        mesh, U, th, ps, dist, jl, anchor_dofs, slots0, active,
        n_increments_step0, pen_step0, exempt_set, verbose, 'step0',
        k_spring=k_spring, reg_mult=reg_mult)
    rec = record(0, 0, U, th, ps, active, slots0, status)
    steps.append(rec)
    if verbose:
        print(f"  step 0: peak NE={rec['peak_NE']*100:.4f}% at x={rec['peak_x']:.2f}  "
              f"peak M={rec['peak_M']/1e3:.1f} kNm at x={rec['peak_M_x']:.2f}  "
              f"kap_max={rec['kap_max']:.4e}  inactive={rec['inactive']}  [{status}]")
    if status != 'ok':
        return {'steps': steps, 'mesh': mesh, 'sec_ids': sec_ids, 'allc': allc}

    # ---- SHIFTS ----
    for s in range(1, n_shifts + 1):
        if verbose:
            print(f"--- shift {s} (roller pattern -{s} element(s); component "
                  f"~{s*elem_len_sr2:.3f} m past SR2-relative start) ---")
        slots = make_slots(s)
        U, th, ps, active, status = _solve_state(
            mesh, U, th, ps, dist, jl, anchor_dofs, slots, active,
            n_increments_shift, pen_shift, exempt_set, verbose, f'shift{s}',
            k_spring=k_spring, reg_mult=reg_mult)
        # NOTE: slots_prev=make_slots(s-1) would activate the
        # constraint-transition ramp in _solve_state. DISABLED -- it was
        # implemented and TESTED, and it makes things WORSE (tech-ref
        # 13.12). Kept in _solve_state for reference only.
        rec = record(s, s, U, th, ps, active, slots, status)
        steps.append(rec)
        if verbose:
            print(f"  shift {s}: peak NE={rec['peak_NE']*100:.4f}% at "
                  f"x={rec['peak_x']:.2f}  peak M={rec['peak_M']/1e3:.1f} kNm at "
                  f"x={rec['peak_M_x']:.2f}  kap_max={rec['kap_max']:.4e}  "
                  f"inactive={rec['inactive']}  [{status}]")
        if status != 'ok':
            break

    return {'steps': steps, 'mesh': mesh, 'sec_ids': sec_ids, 'allc': allc}


# #############################################################################
# #############################################################################
# ##  v1.48 (Session 23): deformed-shape plot for a single run_passage_v2()
# ##  step -- for visual sanity-checking of the shroud/roller mechanics.
# ##  Rebuilt against SLAY_PLOT_STYLE_v2.md (user-supplied, Session 23) after
# ##  the first version was found to violate several of that spec's FIXED
# ##  rules: true 1:1 scale, y-axis inverted (pipeline curves downward), and
# ##  -- the important physical one -- the pipe CENTRELINE must be drawn
# ##  OD/2 further from the arc centre than the roller line (dn_map is the
# ##  roller-line target; it has no OD/2 standoff built in), or the pipe
# ##  visually (and, per the style doc's own S12 decision log, matches a
# ##  previously-seen real issue) appears to pass through the rollers.
# #############################################################################

# #############################################################################
# ##  SLAY PLOT STYLE  (v1.48, Session 23)
# ##
# ##  Canonical style + geometry conventions for slay_overbend deformed-shape
# ##  figures. plot_step_deformed() reads its defaults from _PS below, so
# ##  editing this block restyles every figure. Written up here so the
# ##  conventions -- and the errors that produced them -- survive into the
# ##  next session instead of being rediscovered.
# ##
# ##  ------------------------------------------------------------------
# ##  HARD GEOMETRY RULES (each one was a real bug at some point; do not
# ##  "simplify" any of them away)
# ##  ------------------------------------------------------------------
# ##  G1. The solved DOF line IS the deformed pipe CENTRELINE.
# ##      The roller target `dn` is the pipe-on-roller baseline for the
# ##      beam neutral axis, and the solver has already added CL_lift to
# ##      it. Add NOTHING to the DOF line when drawing.
# ##        - Adding V on top double-counts the lift and makes the pipe
# ##          trace the analytic trapezoid ("upside-down shroud" outline)
# ##          instead of its bending-smoothed FEA shape.
# ##        - Treating the DOF line as the pipe's LOWER surface puts the
# ##          centreline half a diameter too high.
# ##      Check: max|2nd difference| of the drawn pipe over the shroud zone
# ##      must be MUCH smaller than that of the analytic profile (measured
# ##      0.036 vs 0.319 -- roughly 9x smoother -- when correct).
# ##
# ##  G2. V is measured from the pipe CENTRELINE, not the pipe OD
# ##      (COMPONENT_GEOMETRY_DEFINITIONS.md 2.4). The elevation actually
# ##      applied is CL_lift = V - OD/2, so the contact curve sits
# ##      r_pipe + CL_lift below the centreline == exactly V below it.
# ##      V < OD/2 is geometrically invalid; V == OD/2 is a zero-thickness
# ##      wrap with no elevation effect.
# ##
# ##  G3. The taper ramps to the PIPE OD, not to the centreline, so the
# ##      shroud body closes to ZERO thickness at each taper outer end.
# ##      A finite step there is the "flat face" artefact.
# ##
# ##  G4. Draw the shroud as a FILLED BODY between the pipe's lower wall
# ##      and the contact curve -- never as a bare line at pipe diameter.
# ##      Fill across the whole footprint so it tapers to a point.
# ##      Only the underside is shrouded: the pipe's top wall is the
# ##      unmodified OD/2 baseline everywhere (no mirrored top curve --
# ##      that produces the hourglass/bowtie artefact).
# ##
# ##  G5. Rollers are FIXED HARDWARE. Draw each at
# ##          (node it currently constrains)  in x   -- gives the travel
# ##          own target height                in y   -- gives the gap
# ##      i.e. offset gap + r_pipe + CL_lift + r_roller along -n, with
# ##      gap = u_out - dn_eff. Measuring only (r_pipe + CL_lift) pins the
# ##      roller to the pipe, so RELEASED rollers get drawn still touching
# ##      it. Check: gap == 0 for every active slot, > 0 for every
# ##      inactive one.
# ##
# ##  G6. Under the bn-shift convention a roller's contact node moves
# ##      toward the VESSEL (+x) as shift grows, so in the pipeline frame
# ##      the rollers travel vessel-ward / right and the component travels
# ##      tip-ward / left. Drawing rollers at their fixed spatial station
# ##      shows no relative travel at all and hides this entirely.
# ##
# ##  G7. All rollers are 600 mm OD (r = 0.30 m), SR and VR alike.
# ##
# ##  ------------------------------------------------------------------
# ##  PRESENTATION RULES
# ##  ------------------------------------------------------------------
# ##  P1. TRUE 1:1 scale on the geometry panel. Achieved by sizing the
# ##      axes BOX to the data aspect (not set_aspect), which also avoids
# ##      matplotlib's "Ignoring fixed x limits" warning.
# ##  P2. y is positive DOWNWARD; invert_yaxis() so the stinger curves
# ##      down the page.
# ##  P3. Two panels, 68% geometry / 32% strain+moment, x-axes matched.
# ##  P4. Clip the idle vessel-side buffer rollers. With n_vr=10 the
# ##      stations reach x ~ +90 m, which collapses the 406 mm pipe to a
# ##      hairline and empties the right half of the figure.
# ##  P5. Vertical guidelines on BOTH panels at matching x: roller
# ##      stations (colour-coded by contact state), shroud/X1-X5
# ##      boundaries, and the peak-strain location.
# ##  P6. At full-stinger span the pipe is inevitably thin -- judge
# ##      shroud geometry from a zoomed window, global behaviour from the
# ##      full view. Both are true scale, so they are comparable.
# #############################################################################

_PS = {
    # canvas
    'fig_w': 16.0, 'dpi': 200, 'panel_geom': 0.68, 'panel_data': 0.32,
    'bg_geom': '#F0F4F8', 'bg_data': '#FAFAFA', 'grid': '#E0E0E0',
    'box_edge': '#BDBDBD',
    # pipe
    'pipe_fill': '#BBDEFB', 'pipe_edge': '#1565C0', 'pipe_cl': '#0D47A1',
    # shroud
    'shroud_fill': '#FFCC80', 'shroud_edge': '#E65100',
    # rollers
    'r_roller': 0.30, 'roller_line': '#B0BEC5', 'anchor': '#78909C',
    'roller_on': '#2E7D32', 'roller_on_face': '#E8F5E9',
    # accent_red serves double duty: released rollers AND the strain trace
    'accent_red': '#C62828', 'limit': '#B71C1C',
    # data panel
    'eps_limit': 0.02,
}


def shroud_offset_at_safe(x, centre_x, L1, L2, V, D_o, taper='linear'):
    """Non-raising wrapper around shroud_offset_at for plotting. Returns
    CL_lift (elevation above the plain-pipe baseline), not V."""
    if centre_x is None:
        return 0.0
    return shroud_offset_at(x, centre_x, L1, L2, V, D_o, taper=taper)


def plot_step_deformed(result, step_idx, D_o=0.4064, shroud_component=None,
                        thick_component=None, thick_offset_x=0.0,
                        ref_centre_x=None, x_window=None, save_path=None,
                        title=None, R=None, tension_mt=None, r_roller=None,
                        eps_limit=None, guidelines=True, show_eps_limit=True):
    """Deformed-shape + strain/bending-moment plot for one step of a
    run_passage_v2() result, per SLAY_PLOT_STYLE_v2.md.

    Panels: stinger geometry (68%, TRUE 1:1 scale) over strain +
    bending moment (32%), x-axes matched.

    Geometry conventions (Session 23 review):
     1. Pipe sits ON the rollers. Model y is +DOWN, so the pipe is at
        SMALLER y than the roller line. The solver's roller target
        carries no pipe-radius standoff -- the constrained node's own
        position IS the contact point -- so the pipe centreline is drawn
        r_pipe (plus V under a shroud) along the local normal, which is
        forced PER POINT to point away from the rollers (ny<=0).
     2. Rollers are drawn at the node each CURRENTLY constrains (which
        moves vessel-ward with shift), not at their fixed station.
     3. Pipe is a full-depth tube everywhere, including through the
        shroud, where the whole tube is simply lifted by V.
     4. The SHROUD is drawn as its own filled trapezoidal body between
        the roller-contact line (its bottom, which is what the rollers
        actually touch) and the pipe's lower wall -- not as a bare line
        at pipe diameter.

    Default x_window clips the redundant vessel-side buffer rollers
    (which otherwise stretch x to ~+90 m, collapsing the 406 mm pipe to
    a hairline and leaving the right half of the figure empty).
    """
    import matplotlib.pyplot as plt
    import matplotlib as mpl
    r_roller = _PS['r_roller'] if r_roller is None else r_roller
    eps_limit = _PS['eps_limit'] if eps_limit is None else eps_limit
    mpl.rcParams.update({'font.family': 'sans-serif', 'axes.linewidth': 0.8})

    mesh = result['mesh']; allc = result['allc']
    rec = next((s for s in result['steps'] if s['step'] == step_idx), None)
    if rec is None:
        raise ValueError(f"step {step_idx} not found")
    U = rec['U']

    xy0 = np.array(mesh.mesh_nodes); order = np.argsort(xy0[:, 0])
    x0 = xy0[order, 0]
    xd = xy0[order, 0] + np.array([U[3*i] for i in order])
    yd = xy0[order, 1] + np.array([U[3*i + 1] for i in order])

    # local normal, forced PER POINT to point away from the rollers
    dxs = np.gradient(xd); dys = np.gradient(yd)
    tl = np.hypot(dxs, dys); tl[tl == 0] = 1.0
    nx_, ny_ = dys/tl, -dxs/tl
    flip = ny_ > 0                      # model y is +down => "up" is ny<0
    nx_[flip] *= -1.0; ny_[flip] *= -1.0

    r_pipe = D_o/2.0
    sc = shroud_component
    if sc is not None and ref_centre_x is not None:
        # evaluated at REFERENCE x, exactly as make_slots() does.
        # NB this is CL_lift (= V - OD/2 at the plateau), not V.
        V = np.array([shroud_offset_at_safe(x, ref_centre_x, sc['L1'], sc['L2'],
                                             sc['V'], D_o, taper=sc.get('taper', 'linear'))
                       for x in x0])
    else:
        V = np.zeros_like(xd)

    # GEOMETRY (COMPONENT_GEOMETRY_DEFINITIONS.md §2.4-2.6, corrected
    # Session 23). The model's roller target `dn` is the PIPE-ON-ROLLER
    # BASELINE for the pipe CENTRELINE (the beam node is the neutral
    # axis), and the solver has already added CL_lift to it. So the
    # solved DOF line IS the deformed pipe centreline -- nothing may be
    # added to it here. (Two earlier errors, both now fixed: adding V on
    # top double-counted the lift and made the pipe trace the analytic
    # trapezoid; treating the DOF line as the pipe's lower surface put
    # the centreline half a diameter too high.)
    #   pipe centreline  : the solved line
    #   pipe walls       : +/- r_pipe about it
    #   contact curve    : V below the CENTRELINE, i.e. r_pipe + CL_lift
    #                      below it -- which is exactly the pipe's own
    #                      lower wall wherever CL_lift = 0, so the shroud
    #                      body closes to ZERO thickness at each taper
    #                      outer end instead of ending on a flat face.
    #   pipe centreline  : the solved line
    #   pipe walls       : +/- r_LOCAL about it (v1.48 fix, this turn --
    #                      thick_component changes the pipe's OWN OD
    #                      within its range, per Fig.17 of the companion
    #                      paper: constant ID, OD grows outward. The
    #                      solved centreline already reflects this
    #                      correctly (CL_thick = (OD_tc-D_o)/2 is exactly
    #                      the concentric-growth elevation), so drawing
    #                      needs ONLY a position-dependent wall radius,
    #                      not a back-correction of the centreline.
    #                      Previously every wall used the constant base
    #                      r_pipe, so a thick section was drawn as a
    #                      normal-diameter tube that had merely been
    #                      lifted (like a shroud) -- visually
    #                      indistinguishable from plain pipe.
    #   contact curve    : V below the LOCAL wall, i.e. r_LOCAL + CL_lift
    #                      below the centreline -- which is exactly the
    #                      pipe's own lower wall wherever CL_lift = 0
    # RE-DERIVED FROM THE ELEMENT MESH (this turn) -- not from a separate
    # node-position test. The earlier version tested each NODE's
    # reference x against [tc_centre-half, tc_centre+half] independently
    # of the solve, but run_passage_v2 assigns sec_id PER ELEMENT by
    # ELEMENT MIDPOINT (see sec_ids construction there). Since L_comp is
    # not generally an exact multiple of elem_len, those two boundary
    # tests can disagree by up to half an element -- confirmed this
    # session: the leading edge happened to align (ref_centre_x is
    # defined from a station position that lands exactly on a node), the
    # trailing edge did not, so only one of the two boundaries drew
    # correctly.
    #
    # Fix: read sec_id directly from mesh.mesh_elems (the SAME array
    # run_passage_v2 itself assigned), and build the drawn geometry by
    # walking ELEMENTS, emitting each element's own two endpoint node
    # positions tagged with THAT element's own radius -- two points per
    # element. Two same-section elements sharing a node naturally emit
    # two identical points there (collapses to one visible point,
    # unchanged from before). Two different-section elements sharing a
    # node emit two points at the SAME physical position with DIFFERENT
    # radii -- the sharp step, now positioned exactly where the solve
    # itself put the boundary, not re-derived independently.
    sec_arr = np.array([mesh.mesh_elems[ie][3] for ie in range(mesh.n_elems)])
    r_of_sec = {1: r_pipe, 2: (thick_component['OD']/2.0 if thick_component else r_pipe)}
    # v1.48 correction (this turn): mesh.mesh_elems[ie][1]/[2] do NOT give
    # usable per-element node indices here -- checked directly, [2] came
    # back as the same constant (anchor node) for every element. Use the
    # dof-array mapping instead (dof[:,0]//3, dof[:,3]//3), which is the
    # SAME pattern _strain_profile_b31 already uses successfully for this
    # exact purpose (confirmed correct at both boundaries there).
    dof = mesh.elem_dof_array
    mi_a = dof[:, 0] // 3
    mi_b = dof[:, 3] // 3
    pos_of_mi = {int(order[k]): k for k in range(len(order))}   # mesh-node
                                                                 # idx -> its
                                                                 # position in
                                                                 # the sorted
                                                                 # arrays below
    idx_a = np.array([pos_of_mi[int(m)] for m in mi_a])
    idx_b = np.array([pos_of_mi[int(m)] for m in mi_b])
    r_elem = np.array([r_of_sec.get(int(s), r_pipe) for s in sec_arr])

    n2 = 2 * mesh.n_elems
    xd2  = np.empty(n2); yd2 = np.empty(n2)
    nx2  = np.empty(n2); ny2 = np.empty(n2)
    x02  = np.empty(n2); V2  = np.empty(n2)
    r2   = np.empty(n2)
    xd2[0::2], xd2[1::2] = xd[idx_a],  xd[idx_b]
    yd2[0::2], yd2[1::2] = yd[idx_a],  yd[idx_b]
    nx2[0::2], nx2[1::2] = nx_[idx_a], nx_[idx_b]
    ny2[0::2], ny2[1::2] = ny_[idx_a], ny_[idx_b]
    x02[0::2], x02[1::2] = x0[idx_a],  x0[idx_b]
    V2[0::2],  V2[1::2]  = V[idx_a],   V[idx_b]
    r2[0::2],  r2[1::2]  = r_elem,     r_elem
    # sort into ascending x (robust regardless of mesh_elems storage order;
    # a stable sort preserves left-then-right within an element and, at a
    # shared node, preserves element order -- i.e. still emits the outer
    # element's point immediately before the inner element's, which is
    # exactly the "old radius, then new radius" sequence the step needs)
    # v1.48 correction (this turn): sorting by x02 with a stable tiebreak
    # is WRONG at a shared node -- ties break by original array-
    # construction order, which follows element STORAGE order, not which
    # side of the boundary each point belongs to. Confirmed this produced
    # [thick, plain] then [plain, thick] at the two boundaries -- exactly
    # reversed from the required [plain, thick] then [thick, plain] -- so
    # the "thick plateau" never actually forms; it draws two brief
    # up-then-down spikes instead of a sustained wide step (visible as
    # reduced OD, reduced length, and a taper-like point rather than a
    # flat-topped step).
    # Fix: do not re-sort by coordinate at all. Elements form a connected
    # chain by construction (verified: elem[ie]'s right node == elem[ie+1]'s
    # left node for every ie), so natural element order (0..n_elems-1) is
    # already geometrically ordered -- just confirm/fix its overall
    # direction once (ascending vs descending x) rather than resolving
    # order pointwise per tie.
    if x02[-1] < x02[0]:
        xd2, yd2, nx2, ny2, x02, V2, r2 = (
            a[::-1] for a in (xd2, yd2, nx2, ny2, x02, V2, r2))
    xd, yd, nx_, ny_, x0, V, r_local = xd2, yd2, nx2, ny2, x02, V2, r2

    xc, yc = xd.copy(), yd.copy()                                # centreline
    x_far = xd + nx_*r_local;  y_far = yd + ny_*r_local          # upper wall
    x_low = xd - nx_*r_local;  y_low = yd - ny_*r_local          # lower wall
    x_sh = xd - nx_*(r_pipe + V); y_sh = yd - ny_*(r_pipe + V)  # contact curve
    # NOTE: r_pipe (constant base OD/2), not r_local -- the shroud's own
    # contact surface is offset from the pipe CENTRELINE by a fixed amount
    # (COMPONENT_GEOMETRY_DEFINITIONS.md sec2.4), independent of any local
    # OD growth from an underlying thick_component. Using r_local here
    # double-counted the thick_component's own radius growth on top of
    # the shroud's already-correct CL_lift (Session 24 C1 bug -- confirmed
    # numerically equal to r_thick - r_pipe of erroneous extra depth).

    # ---- window (clip idle vessel-side buffer rollers) ----
    sp = abs(allc[1][0] - allc[2][0]) if len(allc) > 2 else 8.0
    if x_window is None:
        x_window = (min(a[0] for a in allc) - 2.0, 2.0*sp + 2.0)
    xlo, xhi = x_window
    m = (xd >= xlo) & (xd <= xhi)
    if not m.any():
        m = np.ones_like(xd, dtype=bool)
    yv = np.concatenate([y_far[m], y_low[m], y_sh[m]])
    ylo, yhi = yv.min() - 1.2, yv.max() + 1.2

    # ---- true-scale sizing: axes box ratio == data ratio ----
    fig_w = _PS['fig_w']; L, Wf = 0.06, 0.92
    ax_w_in = fig_w*Wf
    st_h = max(ax_w_in*(yhi - ylo)/(xhi - xlo), 3.0)
    sn_h = max(st_h*_PS['panel_data']/_PS['panel_geom'], 2.2)
    bm, gap, tm = 0.85, 0.75, 0.75
    tot_h = bm + sn_h + gap + st_h + tm
    fig = plt.figure(figsize=(fig_w, tot_h)); fig.patch.set_facecolor('white')
    ax = fig.add_axes([L, (bm + sn_h + gap)/tot_h, Wf, st_h/tot_h])
    axs = fig.add_axes([L, bm/tot_h, Wf, sn_h/tot_h])
    ax.set_facecolor(_PS['bg_geom']); axs.set_facecolor(_PS['bg_data'])

    ax.plot([a[0] for a in allc], [a[1] for a in allc], ':', color=_PS['roller_line'],
            lw=1.0, zorder=1, label='Roller station line (fixed in space)')

    if sc is not None and ref_centre_x is not None:
        half = sc['L1']/2.0 + sc['L2']
        ins = np.abs(x0 - ref_centre_x) <= half + 1e-9
    else:
        ins = np.zeros_like(x0, dtype=bool)
    if ins.any():
        # Item 4: shroud as a filled body between its bottom (on the
        # rollers) and the pipe's lower wall. Dense, independent resample
        # (not the coarse structural mesh nodes -- as few as 1 node can
        # fall inside a single taper span, which kinks the taper into an
        # apparent multi-slope shape and truncates it short of the true
        # flush V=0 point at each taper's outer edge; see fix note above).
        n_dense = 200
        x0_d = np.linspace(ref_centre_x - half, ref_centre_x + half, n_dense)
        # interpolate the SOLVED deformed geometry against reference x
        # (x0 here is already the ascending, element-chain-ordered array)
        xd_d = np.interp(x0_d, x0, xd);  yd_d = np.interp(x0_d, x0, yd)
        nx_d = np.interp(x0_d, x0, nx_); ny_d = np.interp(x0_d, x0, ny_)
        rl_d = np.interp(x0_d, x0, r_local)   # pipe-wall side may still
                                               # be locally thick (C1)
        V_d = np.array([shroud_offset_at_safe(x, ref_centre_x, sc['L1'], sc['L2'],
                                               sc['V'], D_o, taper=sc.get('taper', 'linear'))
                         for x in x0_d])
        x_sh_d = xd_d - nx_d*(r_pipe + V_d); y_sh_d = yd_d - ny_d*(r_pipe + V_d)
        x_low_d = xd_d - nx_d*rl_d;          y_low_d = yd_d - ny_d*rl_d
        xs = np.concatenate([x_sh_d, x_low_d[::-1]])
        ys = np.concatenate([y_sh_d, y_low_d[::-1]])
        ax.fill(xs, ys, facecolor=_PS['shroud_fill'], edgecolor=_PS['shroud_edge'],
                linewidth=1.4, alpha=0.95, zorder=2,
                label='Shroud body (rides on rollers)')

    ax.fill(np.concatenate([x_far, x_low[::-1]]),
            np.concatenate([y_far, y_low[::-1]]),
            facecolor=_PS['pipe_fill'], edgecolor=_PS['pipe_edge'], linewidth=1.1,
            alpha=0.95, zorder=3, label='Pipe (true OD)')
    ax.plot(xc, yc, '-', color=_PS['pipe_cl'], lw=0.7, alpha=0.5, zorder=4)

    for sl in rec.get('slot_info', []):
        mi = sl['mi']
        cx = mesh.mesh_nodes[mi][0] + U[3*mi]
        cy = mesh.mesh_nodes[mi][1] + U[3*mi + 1]
        if not (xlo - 2 <= cx <= xhi + 2):
            continue
        # Windowed max, not a single-point sample: near a sharp taper/
        # plateau corner (the piecewise-linear taper's slope-discontinuity
        # point), a point evaluated only at this roller's own node can be
        # tangent locally yet still have the FINITE-RADIUS drawn circle
        # geometrically overlap a neighbouring, deeper part of the curve
        # just the other side of the corner -- confirmed numerically
        # (Session 24: min distance from roller centre to the dense
        # contact curve was 0.24m against a 0.30m roller radius, i.e. a
        # real overlap, not a rendering coincidence). The real contact
        # solve operates on points and is unaffected either way; this is
        # a visualization-only fix. Sampling +/- 1.5*r_roller and taking
        # the max V found clears the nearby corner in every case checked.
        if sc is not None and ref_centre_x is not None:
            _win = 1.5 * r_roller
            _xs_win = np.linspace(mesh.mesh_nodes[mi][0] - _win,
                                   mesh.mesh_nodes[mi][0] + _win, 9)
            Vn = max(shroud_offset_at_safe(_x, ref_centre_x, sc['L1'], sc['L2'],
                                            sc['V'], D_o, taper=sc.get('taper', 'linear'))
                      for _x in _xs_win)
        else:
            Vn = 0.0
        # The roller is FIXED hardware: its surface sits at its own target
        # height, dn_eff - (r_pipe + CL_lift), regardless of where the pipe
        # currently is. Measuring down from the node by only
        # (r_pipe + CL_lift) -- as an earlier version did -- pinned every
        # roller to the pipe, so RELEASED rollers were still drawn touching
        # it and contact/lift-off contradicted each other. The gap term
        # below is zero for a roller in contact and positive once the pipe
        # lifts off, which is exactly what makes release visible.
        u_out = U[3*mi]*sl['nx'] + U[3*mi + 1]*sl['nys']
        gap = u_out - sl['dn']                 # >0 => pipe has lifted clear
        r_pipe_loc = r_pipe
        in_shroud_here = (sc is not None and ref_centre_x is not None and
                           abs(mesh.mesh_nodes[mi][0] - ref_centre_x) <= sc['L1']/2.0 + sc['L2'] + 1e-9)
        if thick_component is not None and ref_centre_x is not None and not in_shroud_here:
            if abs(mesh.mesh_nodes[mi][0] - (ref_centre_x + thick_offset_x)) <= thick_component['length']/2.0 + 1e-9:
                r_pipe_loc = thick_component['OD']/2.0
        off = gap + r_pipe_loc + Vn + r_roller
        rx = cx - sl['nx']*off; ry = cy - sl['nys']*off
        act = sl['active']; col = _PS['roller_on'] if act else _PS['accent_red']
        ax.add_patch(plt.Circle((rx, ry), r_roller,
                                 facecolor=_PS['roller_on_face'] if act else 'white',
                                 edgecolor=col, lw=1.4, zorder=7))
        if not act:
            ax.plot([rx], [ry], 'x', color=col, ms=6, mew=1.6, zorder=8)
        ax.text(rx, ry + r_roller*1.5, sl['name'], fontsize=6.5, color=col,
                ha='center', va='top', rotation=90)

    # ---- vertical reference guidelines, drawn on BOTH panels at the same
    #      x so features in the strain/BM trace can be read straight down
    #      to their location on the stinger ----
    if guidelines:
        # (a) roller stations, at the mesh position each CURRENTLY constrains,
        #     colour-coded by contact state
        for sl in rec.get('slot_info', []):
            gx = mesh.mesh_nodes[sl['mi']][0] + U[3*sl['mi']]
            if not (xlo <= gx <= xhi):
                continue
            c = _PS['roller_on'] if sl['active'] else _PS['accent_red']
            for a in (ax, axs):
                a.axvline(gx, color=c, ls=':', lw=0.7, alpha=0.40, zorder=0)
        # (b) shroud geometry + X1-X5 region boundaries. Defined in
        #     REFERENCE x (matching the model's own internal region_peaks/
        #     comp_ranges convention -- deliberately unchanged, so these
        #     markers stay consistent with what the solver itself searched
        #     over), then mapped through the SAME reference->deformed
        #     interpolation the shroud polygon itself uses (x0/xd, already
        #     built above) before drawing -- otherwise the markers are
        #     correct in an idealized undeformed sense but visibly miss the
        #     actual (deformed) shroud body wherever the pipe has
        #     accumulated real rotation/curvature between the anchor and
        #     the shroud (Session 24, user-caught: "due to slope of the
        #     pipeline" -- exactly right).
        if sc is not None and ref_centre_x is not None:
            h1 = sc['L1']/2.0; h2 = h1 + sc['L2']; th = sc['L1']/3.0
            edges_ref = [ref_centre_x - h2, ref_centre_x - h1,
                         ref_centre_x - h1 + th, ref_centre_x - h1 + 2*th,
                         ref_centre_x + h1, ref_centre_x + h2]
            edges = list(np.interp(edges_ref, x0, xd))
            styles = ['--', '-', ':', ':', '-', '--']
            for gx, st in zip(edges, styles):
                if not (xlo <= gx <= xhi):
                    continue
                for a in (ax, axs):
                    a.axvline(gx, color=_PS['shroud_edge'], ls=st, lw=1.0, alpha=0.6, zorder=1)
            for nm, a_, b_ in zip(['X1', 'X2', 'X3', 'X4', 'X5'], edges[:-1], edges[1:]):
                xmid = 0.5*(a_ + b_)
                if xlo <= xmid <= xhi:
                    ax.text(xmid, ylo + 0.05*(yhi - ylo), nm, fontsize=8.5,
                            color=_PS['shroud_edge'], ha='center', va='top', fontweight='bold')
        # (c) thick_component boundaries (OD is unchanged, so this is the
        #     ONLY visual marker of where a thick section sits -- unlike a
        #     shroud there is no geometric bump to see)
        if thick_component is not None and ref_centre_x is not None:
            half_tc = thick_component['length'] / 2.0
            tc_centre = ref_centre_x + thick_offset_x
            for gx in (tc_centre - half_tc, tc_centre + half_tc):
                if xlo <= gx <= xhi:
                    for a in (ax, axs):
                        a.axvline(gx, color='#6A1B9A', ls='-', lw=1.3,
                                  alpha=0.7, zorder=1)
            if xlo <= tc_centre <= xhi:
                ax.text(tc_centre, ylo + 0.05*(yhi - ylo),
                        f"WT={thick_component['t']*1000:.0f}mm  "
                        f"OD={thick_component['OD']*1000:.0f}mm  "
                        f"L={thick_component['length']/D_o:.0f}D",
                        fontsize=8.5, color='#6A1B9A', ha='center',
                        va='top', fontweight='bold')
            for a in (ax, axs):
                a.axvspan(tc_centre - half_tc, tc_centre + half_tc,
                          color='#6A1B9A', alpha=0.06, zorder=0)

        # (c2) peak-strain location
        for a in (ax, axs):
            a.axvline(rec['peak_x'], color=_PS['accent_red'], ls='-.', lw=1.3,
                      alpha=0.85, zorder=1)

        # (c3) max-curvature integration point (distinct from peak strain --
        # see _curvature_peak() docstring; the two need not coincide, and
        # empirically often don't by a small amount near a sharp geometric
        # feature). Guarded in a try/except: this is a post-hoc U-only
        # reconstruction without the solve's own `th` continuity state, so
        # it is diagnostic, not load-bearing -- must never break the plot.
        try:
            x_vr1_bound = allc[1][0]
            _, kap_x = _curvature_peak(mesh, U, x_exclude_above=x_vr1_bound)
            if kap_x is not None and xlo <= kap_x <= xhi:
                for a in (ax, axs):
                    a.axvline(kap_x, color='#00838F', ls='-.', lw=1.3,
                              alpha=0.85, zorder=1)
                ax.text(kap_x, ylo + 0.12*(yhi - ylo), ' peak |curvature|',
                        color='#00838F', fontsize=7.5, ha='left', va='top',
                        rotation=90)
        except Exception:
            pass

    ax.set_xlim(xlo, xhi); ax.set_ylim(ylo, yhi); ax.invert_yaxis()
    ax.set_ylabel('y (m)  (+down)', fontsize=10)
    ax.grid(True, alpha=0.25, color=_PS['grid'])
    ax.legend(fontsize=8, loc='lower left', framealpha=0.9)
    ann = []
    if R is not None: ann.append(f"R = {R:.0f} m")
    if tension_mt is not None: ann.append(f"T = {tension_mt:.0f} MT")
    ann.append(f"shift = {rec['shift_elements']} ({rec['travel_m']:.2f} m)")
    ax.text(0.985, 0.05, '\n'.join(ann), transform=ax.transAxes, ha='right',
            va='bottom', fontsize=9,
            bbox=dict(boxstyle='round', fc='white', ec=_PS['box_edge']))
    ax.set_title(title or
                 f"Deformed shape (true 1:1 scale) — step {step_idx}   "
                 f"peak NE={rec['peak_NE']*100:.3f}% @ x={rec['peak_x']:.2f} m   "
                 f"[{rec['status']}]", fontsize=11)

    # ---- strain + bending moment panel ----
    xp = rec.get('x_profile'); NE = rec.get('NE_profile')
    if xp is not None:
        axs.plot(xp, NE*100.0, '-', color=_PS['accent_red'], lw=1.8, label='Strain |NE| (%)')
        if show_eps_limit:
            axs.axhline(eps_limit*100.0, color=_PS['limit'], ls='--', lw=1.2,
                        label=f'DNV DCC limit {eps_limit*100:.1f}%')
        axs.plot([rec['peak_x']], [rec['peak_NE']*100.0], 'o', color=_PS['accent_red'], ms=6)
        axs.annotate(f"{rec['peak_NE']*100:.3f}%", xy=(rec['peak_x'], rec['peak_NE']*100),
                     xytext=(6, 8), textcoords='offset points', fontsize=8, color=_PS['accent_red'])
    axm = axs.twinx()
    xM = rec.get('xM_profile'); M = rec.get('M_profile')
    if xM is not None:
        axm.plot(xM, M/1e3, '-', color=_PS['pipe_edge'], lw=1.2, alpha=0.75)
        axm.set_ylabel('Bending moment (kNm)', fontsize=9, color=_PS['pipe_edge'])
        axm.tick_params(axis='y', labelcolor=_PS['pipe_edge'], labelsize=8)
    if sc is not None and ref_centre_x is not None:
        half_shroud = sc['L1']/2.0 + sc['L2']
        xlo_sh, xhi_sh = np.interp([ref_centre_x - half_shroud, ref_centre_x + half_shroud], x0, xd)
        for a in (ax, axs):
            a.axvspan(xlo_sh, xhi_sh, color=_PS['shroud_edge'], alpha=0.08, zorder=0)
    axs.set_xlim(xlo, xhi)
    axs.set_xlabel('x (m)      ←  stinger tip / catenary            vessel  →', fontsize=10)
    axs.set_ylabel('Strain (%)', fontsize=10, color=_PS['accent_red'])
    axs.tick_params(axis='y', labelcolor=_PS['accent_red'])
    axs.grid(True, alpha=0.25, color=_PS['grid'])
    axs.legend(fontsize=8, loc='upper left', framealpha=0.9)

    if save_path:
        plt.savefig(save_path, dpi=_PS['dpi'], bbox_inches='tight', facecolor='white')
        print(f"  Saved: {save_path}")
    plt.close(fig)
    return fig

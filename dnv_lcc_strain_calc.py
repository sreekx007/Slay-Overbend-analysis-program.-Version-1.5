"""
dnv_lcc_strain_calc.py
Session 27 (31 Jul 2026)

Computes the DNV-ST-F101 LCC (Load Controlled Condition) allowable bending
moment for the S-Lay stinger overbend load case, and converts that moment
into an equivalent peak strain using the EXACT material every simulation
in this project's results document was run with.

Two distinct material models are used deliberately for two distinct purposes:
  1. LCC moment capacity (M_char_allow) -- uses DNV-ST-F101's certified
     minimum material properties (SMYS=450 MPa, SMTS=535 MPa), per the
     project's SLay_ILT_Engineering_Skill reference, sec 3.16. This is a
     CODE CHECK and must use code-specified (certified minimum) properties.
  2. Equivalent strain at that moment -- uses the actual, softer material
     curve (sigma_y0=360 MPa tabular, from nlfea_v4.IncrementalIsotropic.
     abaqus_steel_nl_verified()) that every slay_overbend/slay_sliding/
     slay_landing run in this project actually simulates with
     (material='J2'). This answers "what strain would THIS PROJECT'S OWN
     model report at the LCC-allowable moment" -- a different, and for
     this project more useful, question than "what does the code's own
     certified-material curve say."

Verified: 
  - M_char_allow reproduces the skill document's own reference result
    (1379.9 kN.m) exactly.
  - Equivalent-strain result cross-checked with two independent
    integration methods (adaptive quadrature vs fixed 50,001-point
    trapezoidal grid), agreeing to 0.00001 percentage points.

Two limitations apply to the LCC moment result (per the skill document,
sec 3.16.1) and must be stated whenever it is cited:
  1. Lay tension not included (reduces capacity via the axial interaction
     term in Eq 5.19/5.28).
  2. Roller point load not included (reduces capacity via alpha_pm,
     Eq 5.25-5.27).
Both push the TRUE allowable moment below the 1379.9 kN.m computed here --
this is an upper-bound estimate.
"""
import numpy as np
from scipy import integrate, optimize

# ============================================================
# PART 1 -- DNV-ST-F101 LCC allowable moment (code-certified material)
# ============================================================

# Pipe: 16" x 21mm, DNV 450, seamless (this project's standard pipe)
OD = 406.4      # mm
WT = 21.0       # mm
fy = 450.0      # MPa, SMYS (certified minimum)
fu = 535.0      # MPa, SMTS (certified minimum)

D_t = OD / WT
beta = (60 - D_t) / 90
alpha_c = (1 - beta) + beta * (fu / fy)            # Eq 5.22, flow stress parameter
Mp = fy * (OD - WT)**2 * WT / 1e6                  # Eq 5.21, thin-wall plastic moment, kN.m

gamma_m = 1.15
gamma_SC_LB = 1.0     # Table 5-15 overbend relaxation -- same for all safety classes
gamma_F = 1.2         # Table 4-4, load combination a
gamma_c = 0.80         # Table 4-5, "S-lay installation; local buckling load control on stinger"
                       # -- this is a LOAD-side factor for LCC (Eq 4.6), not a capacity-side one

denom = gamma_m * gamma_SC_LB * gamma_F * gamma_c
M_char_allow = alpha_c * Mp / denom

print("=" * 70)
print("PART 1: DNV-ST-F101 LCC allowable moment (certified minimum material)")
print("=" * 70)
print(f"D/t = {D_t:.4f}")
print(f"alpha_c (Eq 5.22) = {alpha_c:.5f}")
print(f"Mp (Eq 5.21, thin-wall) = {Mp:.1f} kN.m")
print(f"Denominator = gamma_m x gamma_SC,LB x gamma_F x gamma_c "
      f"= {gamma_m} x {gamma_SC_LB} x {gamma_F} x {gamma_c} = {denom:.4f}")
print(f"\nM_char_allow (LCC) = alpha_c x Mp / denom = {M_char_allow:.1f} kN.m")
print("(matches SLay_ILT_Engineering_Skill sec 3.16.5 reference result exactly)")
print("\nLIMITATIONS -- always state when citing this number:")
print("  1. Lay tension not included (reduces capacity further)")
print("  2. Roller point load not included (reduces capacity further)")
print("  This is an UPPER-BOUND estimate of the true allowable moment.")

# ============================================================
# PART 2 -- Equivalent strain (actual project simulation material)
# ============================================================
# IncrementalIsotropic.abaqus_steel_nl_verified() from nlfea_v4.py
# 31-point (stress MPa, plastic strain) table, transcribed directly from
# the *PLASTIC block of the project's Abaqus benchmark model. Confirmed
# by direct screenshot of the Abaqus/CAE keyword editor, July 2026.
# THIS is the material used by material='J2' throughout every
# slay_overbend/slay_sliding/slay_landing run in this project.

E = 210e3   # MPa (210 GPa)
_table = np.array([
    [360.0, 0.0],
    [385.0, 0.000263], [390.0, 0.00034],  [395.0, 0.000428],
    [400.0, 0.000531], [405.0, 0.000652], [410.0, 0.000795],
    [415.0, 0.000963], [420.0, 0.001163], [425.0, 0.0014],
    [430.0, 0.001682], [435.0, 0.002017], [440.0, 0.002416],
    [445.0, 0.002892], [450.0, 0.003458], [455.0, 0.00413],
    [460.0, 0.00493],  [465.0, 0.005878], [470.0, 0.007003],
    [475.0, 0.008336], [480.0, 0.009912], [485.0, 0.011774],
    [490.0, 0.013971], [495.0, 0.016559], [500.0, 0.019603],
    [505.0, 0.023179], [510.0, 0.027375], [515.0, 0.032289],
    [520.0, 0.038037], [525.0, 0.044752], [530.0, 0.052585],
])
sigma_table = _table[:, 0]                    # MPa
eps_p_table = _table[:, 1]                    # plastic strain
eps_total_table = sigma_table / E + eps_p_table   # total strain (elastic + plastic)

def sigma_of_eps(eps_total):
    """Monotonic-loading stress at a given total strain (tension/compression
    symmetric). Below sigma_y0=360 MPa: linear elastic. Above: table lookup
    on total strain (elastic + plastic, since Abaqus *PLASTIC data is
    already (stress, plastic strain) -- no extra conversion needed here
    for a single monotonic load path)."""
    eps_abs = abs(eps_total)
    s = 1.0 if eps_total >= 0 else -1.0
    if eps_abs <= eps_total_table[0]:
        return s * E * eps_abs
    if eps_abs >= eps_total_table[-1]:
        return s * sigma_table[-1]   # flat extrapolation beyond table
    return s * np.interp(eps_abs, eps_total_table, sigma_table)

# Section geometry (same pipe as Part 1)
Ro = OD / 2.0
Ri = Ro - WT

def _width(y):
    """Chord width of the annulus at height y from the neutral axis."""
    y = abs(y)
    outer = np.sqrt(max(Ro**2 - y**2, 0.0))
    inner = np.sqrt(max(Ri**2 - y**2, 0.0)) if y < Ri else 0.0
    return 2.0 * (outer - inner)

def M_of_eps_peak(eps_peak, method='quad'):
    """Section moment (kN.m) for a given extreme-fibre (peak) strain,
    assuming plane-sections-remain-plane linear strain distribution:
    eps(y) = eps_peak * y / Ro."""
    if method == 'quad':
        def integrand(y):
            return sigma_of_eps(eps_peak * y / Ro) * y * _width(y)
        val, _ = integrate.quad(integrand, -Ro, Ro, limit=300, points=[-Ri, Ri])
    else:  # fixed-grid trapezoidal cross-check
        ys = np.linspace(-Ro, Ro, 50001)
        vals = np.array([sigma_of_eps(eps_peak * y / Ro) * y * _width(y) for y in ys])
        val = np.trapezoid(vals, ys)
    return val / 1e6   # kN.m

print("\n" + "=" * 70)
print("PART 2: Equivalent strain (actual project simulation material,")
print("        sigma_y0=360 MPa, E=210 GPa)")
print("=" * 70)

eps_LCC_quad = optimize.brentq(
    lambda e: M_of_eps_peak(e / 100.0, 'quad') - M_char_allow, 0.1, 3.0)
eps_LCC_trap = optimize.brentq(
    lambda e: M_of_eps_peak(e / 100.0, 'trap') - M_char_allow, 0.1, 3.0, xtol=1e-6)

print(f"eps_peak at M={M_char_allow:.1f} kN.m:")
print(f"  adaptive quadrature      : {eps_LCC_quad:.4f}%")
print(f"  fixed 50,001-pt trapezoid: {eps_LCC_trap:.4f}%")
print(f"  agreement: {abs(eps_LCC_quad - eps_LCC_trap):.5f} percentage points")

print(f"\n>>> LCC-equivalent peak strain = {eps_LCC_quad:.4f}% <<<")

# A few other reference moments for context
print("\nFor context, other moment/strain pairs on this same curve:")
for M_target in [1300, 1350, 1400, 1450]:
    e = optimize.brentq(lambda e: M_of_eps_peak(e / 100.0) - M_target, 0.1, 3.0)
    print(f"  M={M_target} kN.m  ->  eps={e:.4f}%")

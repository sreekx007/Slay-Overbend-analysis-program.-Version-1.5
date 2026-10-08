"""slay.define.simplify -- reduce any ILS layout to an equivalent GD-Simple.

WHAT A SIMPLIFIED MODEL IS FOR. A real ILS is a specific piece of hardware:
a wall thickness, a bore, an outside diameter, a taper, a frame. Most of
that detail does not reach the overbend answer, which responds to three
things only -- how STIFF the assembly is, how LONG it is, and how far it
holds the pipe OFF the rollers. A simplified model states those three
directly and nothing else, so a layout can be explored before its hardware
exists.

    real layout            ->   measured          ->   ILS-SIMPLE
    --------------------        ----------------       ---------------------
    GD-TP, t 53 mm, 20 D        EI  / EI_pipe          body: E, L, pipe section
    OD_comp 470.4 mm            L   = 8.128 m          shroud: V, L1, L2
                                depth 235.2 mm

EVERYTHING IS MEASURED OFF THE BUILT ASSEMBLY, never read from the spec --
the same rule `report.regions` follows and for the same reason. `ils_builder`
is the single author of what a component IS (G7), so a reduction computed
from the definition would describe the component we asked for rather than the
one the builder made. `section_at` gives the section and its owner at any
station; `contact_at` gives the surface a roller would touch. Both are asked.

THE THREE EQUIVALENCES, and the third is the one that does not hold.

  1. LENGTH is exact. The body spans what the original spanned.
  2. DEPTH is exact. The shroud's bottom flat is put where the original's
     own contact surface was, so the roller sees the same elevation. For a
     GD-TP that is `OD_comp/2` -- and this module does not compute that
     formula, it reads `contact_at`, which returns 235.2 mm for the 53 mm
     wall whether or not anyone remembered the formula.
  3. STIFFNESS is exact in BENDING and WRONG IN AXIAL, unavoidably. One
     modulus on a fixed section cannot match two stiffnesses at once:
     setting `E = E_steel * I_comp / I_pipe` reproduces EI exactly and then
     EA comes out as `E * A_pipe`, which is not `E_steel * A_comp` because
     `A_comp/A_pipe` and `I_comp/I_pipe` are different ratios. EI is matched
     because the overbend is displacement-controlled bending; the axial
     error is REPORTED (`EA_error`) rather than hidden. Measured on the
     published GD-TP walls: +6.2% at 32 mm, +18.8% at 53 mm, +26.6% at
     65 mm -- it grows with the wall, because a thicker body gains area
     faster than it gains the second moment that sets `E_equiv`.

WHY NOT MATCH THE SECTION INSTEAD. Because then it would not be a
simplified model -- it would be the original. GD-Simple carries the
PIPELINE's section by definition, which is what keeps the extreme-fibre
distance, the mass per metre and the contact geometry out of the comparison
and leaves stiffness as the only thing that moved.

Workflow: none -- pure transforms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import config
from slay.define.simple import Simple, SimpleRuleError, build

# The flat/taper tolerance `report.regions` uses: "far below any geometry we
# model and far above float noise". Reused rather than re-chosen so the two
# modules cannot disagree about what counts as flat.
FLAT_TOL = 1.0e-4

N_SAMPLES = 4000

# THE SHORTEST TAPER THAT CAN BE BUILT, and why it is not zero. A GD-TP
# steps abruptly, so the exact equivalent shroud has L2 = 0 -- and
# `OffsetShroud.validate` refuses it: "GD-SH: V, L1 and L2 must be
# positive". That file is MIRRORED (G7), so the floor cannot be moved here;
# a shroud with no taper needs raising upstream. 1e-4 m is the smallest
# length this codebase already declares meaningful (FLAT_TOL above), which
# makes it a step at every scale the model works at without fishing in
# float noise. `region.simple_geometry` measures such a shroud as all-flat,
# which is the intent.
TAPER_MIN = FLAT_TOL


class ReductionError(ValueError):
    """An assembly this module cannot honestly reduce."""


def _I(OD: float, t: float) -> float:
    ID = OD - 2.0 * t
    return math.pi / 64.0 * (OD ** 4 - ID ** 4)


def _A(OD: float, t: float) -> float:
    ID = OD - 2.0 * t
    return math.pi / 4.0 * (OD ** 2 - ID ** 2)


@dataclass(frozen=True)
class Equivalent:
    """One layout, reduced to what GD-Simple can express.

    Carries the errors as well as the values. A reduction that reported only
    what it matched would be stating a half-truth: `EA_error` is large and
    is a property of the method, not of a mistake.
    """
    code: str                 # the component reduced, e.g. 'GD-TP'
    owner: str                # its owner tag in the assembly
    L: float                  # m, the span it occupies
    depth: float              # m, its contact surface below the pipe C/L
    OD_comp: float            # m, as built
    t_comp: float             # m, as built
    OD_pipe: float
    t_pipe: float
    E_steel: float

    # -- what the body must be given ------------------------------------
    @property
    def I_comp(self) -> float:
        return _I(self.OD_comp, self.t_comp)

    @property
    def I_pipe(self) -> float:
        return _I(self.OD_pipe, self.t_pipe)

    @property
    def EI(self) -> float:
        """The original's bending stiffness."""
        return self.E_steel * self.I_comp

    @property
    def EI_ratio(self) -> float:
        return self.I_comp / self.I_pipe

    @property
    def E_equiv(self) -> float:
        """The modulus that reproduces EI on the PIPELINE section. Exact."""
        return self.E_steel * self.EI_ratio

    # -- what it cannot reproduce ---------------------------------------
    @property
    def EA(self) -> float:
        return self.E_steel * _A(self.OD_comp, self.t_comp)

    @property
    def EA_equiv(self) -> float:
        return self.E_equiv * _A(self.OD_pipe, self.t_pipe)

    @property
    def EA_error(self) -> float:
        """Fractional error in AXIAL stiffness. Not a defect -- see module
        docstring. One modulus cannot match EA and EI at once."""
        return self.EA_equiv / self.EA - 1.0

    @property
    def lift(self) -> float:
        """What the roller actually sees: the pipe held off its own bottom."""
        return self.depth - self.OD_pipe / 2.0


def equivalent(ils, OD=None, t_wall=None, n=N_SAMPLES) -> Equivalent:
    """Measure one ILS and reduce it. Refuses what it cannot do honestly.

    Implemented for a layout whose stiffness comes from ONE body of CONSTANT
    section -- GD-TP. A tapered body (GD-TT, GD-PIP), two bodies, or a
    structure carrying its stiffness in a frame rather than in the pipe wall
    are each refused by name rather than averaged into a single number that
    would look like an answer.
    """
    if ils is None:
        raise ReductionError('no ILS to reduce')
    lo_x, hi_x = ils.extent
    pipe = ils.assembly.pipe
    OD_pipe = pipe.OD_pipe if OD is None else float(OD)
    t_pipe = pipe.t_pipe if t_wall is None else float(t_wall)

    xs = [lo_x + (hi_x - lo_x) * k / (n - 1) for k in range(n)]
    owned = {}                      # owner -> [(x, OD, t)]
    depth_of = {}                   # owner -> max contact y
    for x in xs:
        sec = ils.assembly.section_at(x)
        own = getattr(sec, 'owner', 'pipe') if sec is not None else 'pipe'
        if own != 'pipe':
            owned.setdefault(own, []).append(
                (x, getattr(sec, 'OD', OD_pipe), getattr(sec, 't', t_pipe)))
        con = ils.assembly.contact_at(x)
        if con is not None:
            c_own = getattr(con, 'owner', 'pipe')
            depth_of[c_own] = max(depth_of.get(c_own, 0.0), con.y)

    if not owned:
        raise ReductionError(
            'nothing in this assembly owns a section, so there is no '
            'stiffness to reduce. Plain pipe, or a contact-only body such '
            'as a bare GD-SH, is already as simple as GD-Simple gets.')
    if len(owned) > 1:
        raise ReductionError(
            f'this assembly has {len(owned)} section-owning bodies '
            f'{sorted(owned)}, and a single GD-Simple has one. Reducing '
            f'them to one equivalent needs a rule for combining stiffnesses '
            f'in series along the pipe, which is not implemented -- and '
            f'guessing one would produce a number indistinguishable from a '
            f'measured equivalent.')

    owner, rows = next(iter(owned.items()))
    ODs = {round(r[1], 9) for r in rows}
    ts = {round(r[2], 9) for r in rows}
    if len(ODs) > 1 or len(ts) > 1:
        raise ReductionError(
            f'{owner} does not have a constant section -- it carries '
            f'{len(ODs)} diameters and {len(ts)} walls over its span, so it '
            f'is tapered (GD-TT / GD-PIP). One equivalent modulus would '
            f'have to stand for a varying EI, and which average is right '
            f'depends on where the curvature is. Not implemented.')

    xs_on = [r[0] for r in rows]
    L = max(xs_on) - min(xs_on)
    if L <= FLAT_TOL:
        raise ReductionError(f'{owner} spans {L:.6f} m -- nothing to reduce')

    # THE DEPTH IS THE BODY'S OWN CONTACT SURFACE, read rather than derived.
    # For a GD-TP this comes back as OD_comp/2 without this module ever
    # writing that formula down, which is the point: the same code reduces
    # whatever the builder actually made.
    depth = depth_of.get(owner)
    if depth is None:
        raise ReductionError(
            f'{owner} owns a section but owns no contact surface, so there '
            f'is no depth to reproduce. Contact is held by '
            f'{sorted(depth_of)}.')

    code = owner
    for c in ils.assembly.components:
        if getattr(c, 'code', None) and owner in (
                getattr(c, 'code', ''), getattr(c, 'id', '')):
            code = c.code
            break

    # SAMPLING COSTS A LITTLE LENGTH, and it is recorded rather than
    # corrected: the span is measured on `n` samples over the extent, so the
    # two end samples sit up to one interval inside the true ends. At 4000
    # samples over a 20 D body that is 4 mm, or 0.05%.
    return Equivalent(code=code, owner=owner, L=L, depth=depth,
                      OD_comp=rows[0][1], t_comp=rows[0][2],
                      OD_pipe=OD_pipe, t_pipe=t_pipe,
                      E_steel=float(config.STEEL_E))


def parameters(eq: Equivalent, L2: float = TAPER_MIN,
               match: str = 'total') -> dict:
    """The GD-Simple + GD-SH parameters that reproduce `eq`. SI units.

    `match` says what the shroud's length is matched to:

      'total'  L1 + 2*L2 = L. The shroud occupies the SAME FOOTPRINT as the
               body it stands in for, which is what matching a GD-TP means
               -- its lifted surface starts and stops where the original's
               did. The default.
      'flat'   L1 = L. The deep section matches and the tapers hang OUTSIDE
               the body, so the lifted zone is longer than the original and
               part of the lift falls outboard of the elastic span.

    `L2` is the taper. A GD-TP has none; `TAPER_MIN` is as close to none as
    the mirrored shroud will accept.
    """
    if match not in ('total', 'flat'):
        raise ReductionError(f'match must be total or flat, not {match!r}')
    if not L2 > 0.0:
        raise ReductionError(
            f'L2 = {L2!r}. A zero taper is the exact equivalent of a '
            f'GD-TP step and `OffsetShroud.validate` refuses it -- "GD-SH: '
            f'V, L1 and L2 must be positive" -- in a MIRRORED file (G7). '
            f'Use TAPER_MIN ({TAPER_MIN:g} m), or raise the floor upstream.')

    L1 = eq.L - 2.0 * L2 if match == 'total' else eq.L
    if L1 <= 0.0:
        raise ReductionError(
            f'a {eq.L:.4f} m body cannot carry two {L2:.4f} m tapers and '
            f'still have a deep section ({L1:.4f} m). Shorten L2, or use '
            f'match="flat" and accept a lifted zone longer than the body.')
    return dict(E=eq.E_equiv, L_body=eq.L, V=eq.depth, L1=L1, L2=L2)


def simplify(ils, L2: float = TAPER_MIN, match: str = 'total',
             OD=None, t_wall=None) -> tuple:
    """`(Simple, Equivalent)` -- measure one layout and build its stand-in.

    The whole chain in one call: measure the built assembly, derive the five
    parameters, and hand them to `define.simple.build`, which hands a spec
    to the mirrored `ils_builder`. No mirrored file is touched and no
    geometry is constructed here.
    """
    eq = equivalent(ils, OD=OD, t_wall=t_wall)
    sm = build(**parameters(eq, L2=L2, match=match))

    # THE REDUCTION IS CHECKED AGAINST THE THING IT BUILT, not against the
    # parameters it sent. `build` already refuses a body that is not
    # neutral; this adds the two equivalences this module claims are exact,
    # so a silent drift in either would fail here rather than in a result.
    got = equivalent_of_simple(sm)
    if abs(got['depth'] - eq.depth) > FLAT_TOL:
        raise ReductionError(
            f'depth not reproduced: asked {eq.depth:.6f} m, built '
            f'{got["depth"]:.6f} m')
    # THE TOLERANCE HAS TO CARRY THE MEASUREMENT'S OWN RESOLUTION, which is
    # what this check got wrong when first written: it allowed the two
    # tapers and FLAT_TOL but not the sampling grid, and then refused a
    # correct 2.5 D build that came back 0.508 mm short. Both ends of a
    # sampled span sit up to one interval inside the true edge, so the
    # floor is two intervals -- 0.254 mm each at 4000 samples over a
    # 1.016 m extent -- and the check was tighter than the instrument.
    lo_x, hi_x = sm.ils.extent
    dx = (hi_x - lo_x) / (N_SAMPLES - 1)
    budget = 2.0 * L2 + 2.0 * dx + FLAT_TOL
    if abs(got['L_lifted'] - eq.L) > budget:
        raise ReductionError(
            f'lifted length not reproduced: asked {eq.L:.6f} m, built '
            f'{got["L_lifted"]:.6f} m (budget {budget:.6f} m = two '
            f'{L2:g} m tapers + two {dx:.6f} m samples + {FLAT_TOL:g})')
    return sm, eq


def equivalent_of_simple(sm: Simple, n: int = N_SAMPLES) -> dict:
    """What a built GD-Simple actually offers, measured the same way.

    Used to check a reduction against its own product, and useful on its
    own: it answers "what did I build" without reading the parameters back.
    """
    lo_x, hi_x = sm.ils.extent
    half = sm.ils.assembly.pipe.OD_pipe / 2.0
    xs = [lo_x + (hi_x - lo_x) * k / (n - 1) for k in range(n)]
    depth, on = 0.0, []
    for k, x in enumerate(xs):
        con = sm.ils.assembly.contact_at(x)
        if con is not None and con.y > half + FLAT_TOL:
            depth = max(depth, con.y)
            on.append(k)
    return dict(depth=depth,
                L_lifted=(xs[max(on)] - xs[min(on)]) if on else 0.0,
                L_body=sm.L_body, E=sm.E)

"""
component_spec.py -- THE DATA MODEL for COMPONENT_GEOMETRY_DEFINITIONS.md

This layer owns every geometric fact. Nothing else defines geometry:
`schematic_lib.py` renders a spec, and (in future) the FEA deck writer
consumes the same spec. Neither can drift from the other, because neither
holds numbers of its own.

WHY THIS EXISTS
---------------
v5.0 made the DRAWING single-source (one renderer per component). But the
numbers still lived as module-level constants inside the plotting driver
(GDTT_OD_comp = 0.560, ...), so an FEA generator reading them would have
recreated the exact split v5.0 closed, one level up. This is the pyDEXPI
lesson: data model first, rendering as one export among several.

THREE THINGS THIS LAYER ENFORCES THAT PROSE COULD NOT
-----------------------------------------------------
1. FREE vs DERIVED vs INHERITED. Free parameters are constructor
   arguments; derived quantities are read-only properties (so passing one
   is a TypeError, not a silent override); inherited quantities come from
   the BasePipeline and are never redeclared per component.

2. VALIDITY RULES AS CODE. The document's governing rules (OD grows not
   shrinks, constant bore, n >= 4, L_NIB >= 4*l_e) are checked at
   construction. An AI proposing assemblies WILL violate these; prose
   cannot stop it and a plot will happily draw an invalid component.

3. PROVENANCE. Every value in the document today is labelled
   "(illustrative)" -- chosen for figure legibility, not design. Specs
   carry that flag explicitly so a deck writer can refuse to run FEA on
   decorative numbers. `Provenance.ILLUSTRATIVE` is the default precisely
   because it is the safe direction to be wrong in.

UNITS: SI, metres, internally and in every constructor. The document
tabulates many parameters in mm; conversion happens at display only.
Mixed units inside a geometry layer is a class of bug not worth having.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field
from enum import Enum
from math import sqrt, pi, ceil
from typing import Optional, Sequence

import config


# ===========================================================================
# Provenance and errors
# ===========================================================================

class Provenance(Enum):
    """Where a spec's numbers came from.

    ILLUSTRATIVE -- chosen for figure legibility (every worked example in
        the document as it stands). Safe to plot. NOT safe to analyse.
    DESIGN       -- real project values, intended for FEA.
    PAPER        -- reproduces a published case, for validation runs.
    """
    ILLUSTRATIVE = 'illustrative'
    DESIGN = 'design'
    PAPER = 'paper'


class GeometryRuleError(ValueError):
    """A document rule (Section 1.3/1.4, 2.4, 3.3/3.4, ...) was violated.

    Deliberately a hard error, not a warning: these are the rules that make
    a component the thing it claims to be. A ThickPipeBody whose OD shrinks
    is not a badly-parameterised ThickPipeBody, it is a different (and
    wrong) component.
    """


class ContactAmbiguityError(ValueError):
    """Two components claim the contact surface at the same x, and the
    assembly's ownership policy refuses to guess between them."""


# ===========================================================================
# Section 0.1 -- Base Pipeline Parameters (inherited by every component)
# ===========================================================================

@dataclass(frozen=True)
class BasePipeline:
    """Project-level pipeline spec. Sits ABOVE the three-tier structure
    (Sec.0.1): supplied once, inherited by every component, derived by
    none of them.

    OD_pipe, t_pipe and E have no bare literal defaults here -- per the
    config.py scope rule (pipeline geometry + basic pipe-wide parameters
    live in config.py; a GD- component's own dimensions do not), the
    module-level STD_PIPELINE below is what supplies real numbers, built
    from config.py. A caller wanting a non-standard pipe still passes
    OD_pipe/t_pipe/E explicitly -- this class itself asserts no opinion on
    what "the" pipe is.
    """
    OD_pipe: float                  # m
    t_pipe: float                   # m
    nu: float = 0.3                  # Poisson's ratio, steel (Sec.3.6) --
                                       # stays a bare literal: config.py
                                       # doesn't model per-material Poisson's
                                       # ratio, and this isn't pipeline
                                       # geometry in the config.py sense.
    E: float = config.STEEL_E          # Pa, Young's modulus, steel.
                                         # Sourced from config.py, not
                                         # restated -- see config.py's
                                         # STEEL_E for why this is its own
                                         # constant rather than either of
                                         # MATERIAL_J2_E/MATERIAL_RO_E (207
                                         # vs 210 GPa: those genuinely
                                         # disagree, so BasePipeline.E picks
                                         # STEEL_E as the pipe-wide answer
                                         # that predates any material-
                                         # nonlinearity choice).
    provenance: Provenance = Provenance.ILLUSTRATIVE

    def __post_init__(self):
        if self.OD_pipe <= 0 or self.t_pipe <= 0:
            raise GeometryRuleError('OD_pipe and t_pipe must be positive')
        if self.t_pipe >= self.OD_pipe / 2:
            raise GeometryRuleError(
                f't_pipe ({self.t_pipe*1000:.1f} mm) leaves no bore in a '
                f'{self.OD_pipe*1000:.1f} mm pipe')

    @property
    def ID(self) -> float:
        """Sec.0.1 -- the one quantity nearly every component holds
        constant (pig passage / code-split boundary)."""
        return self.OD_pipe - 2 * self.t_pipe

    @property
    def r_mean(self) -> float:
        return (self.OD_pipe - self.t_pipe) / 2

    @property
    def l_e(self) -> float:
        """Elastic shell decay length (Sec.3.6).
        Verified: 406.4/21 pipe -> 49.4 mm, matching the document."""
        return sqrt(self.r_mean * self.t_pipe) / (3 * (1 - self.nu ** 2)) ** 0.25

    @property
    def NIB_dnv(self) -> float:
        """RAW DNV-ST-F101 Sec.5.6.1.7 value, = 4*l_e (Sec.3.3).

        Kept separate from `NIB_min` so the code formula stays traceable
        after the 30 Aug 2026 rounding decision below. This is the number
        the standard gives; `NIB_min` is the buildable length derived from
        it, and they are no longer the same.
        """
        return 4 * self.l_e

    @property
    def NIB_min(self) -> float:
        """The ENFORCED floor: `NIB_dnv` rounded to the NEAREST 50 mm.

        SETTLED 30 Aug 2026, and this is a deliberate change of meaning.
        NIB_min was previously the raw 4*l_e and `NIB_default` rounded UP
        away from it. The decision is that a NIB is calculated to the DNV
        spec and then rounded to the nearest 50 mm, and that rounded value
        is the default AND the minimum unless the caller supplies its own.

        CONSEQUENCE, STATED PLAINLY. Rounding to nearest goes BELOW the raw
        4*l_e for eight of nine common line sizes:

            12.75 in  154.0 -> 150 mm   ( -4.0 mm)
            16 in     198.0 -> 200 mm   ( +2.0 mm)
            18 in     210.6 -> 200 mm   (-10.6 mm)
            20 in     222.5 -> 200 mm   (-22.5 mm)   <- largest shortfall
            24 in     268.0 -> 250 mm   (-18.0 mm)
            28 in     264.9 -> 250 mm   (-14.9 mm)
            30 in     301.0 -> 300 mm   ( -1.0 mm)
            32 in     311.2 -> 300 mm   (-11.2 mm)
            36 in     368.6 -> 350 mm   (-18.6 mm)

        The floor is therefore the ROUNDED value, not 4*l_e -- validating
        against the raw number would reject this module's own default for
        those eight sizes. `NIB_dnv` remains available for anyone who needs
        to show the underlying code number.
        """
        return round(self.NIB_dnv / 0.05) * 0.05

    @property
    def NIB_default(self) -> float:
        """Same value as `NIB_min` -- the rounded, buildable length.

        Default and minimum COINCIDE by the 30 Aug 2026 decision: the DNV
        calculation rounded to the nearest 50 mm is what a NIB is, unless
        the caller supplies something else. Both names are kept because
        they answer different questions -- "what do I get if I say nothing"
        and "what is the least I may say" -- and a caller reading one
        should not have to know it is also the other.

        50 mm because a NIB is a machined land on a forging: specified and
        inspected to a round number, not to the 198.0 mm the formula gives.

        Scales with the pipe, unlike the fixed 0.25 m it replaced, which
        was fine at 16 in and unbuildable above about 25 in.
        """
        return self.NIB_min

    @property
    def I_pipe(self) -> float:
        return self.OD_pipe ** 4 - self.ID ** 4      # to a common factor

    @property
    def I_true(self) -> float:
        """Real second moment of area, m^4 (includes the pi/64 factor
        I_pipe deliberately omits, since I_pipe exists only for RATIO
        comparisons like GD-TP's I_ratio, where the missing constant
        cancels out). Use this one whenever an actual m^4 value is needed."""
        return pi / 64 * (self.OD_pipe ** 4 - self.ID ** 4)

    @property
    def EI(self) -> float:
        """Real bending stiffness, N*m^2 (= Pa*m^4)."""
        return self.E * self.I_true


# Sec.0.1's standard illustrative pipeline, used by every worked example.
# OD_pipe/t_pipe sourced from config.py (config.OD_PIPE_DEF/T_WALL_DEF), not
# restated -- this was a real duplication bug until 13 Aug 2026: two
# independent sources of the same numbers, exactly the class of bug the
# fresh-build rebuild exists to remove. E is inherited from BasePipeline's
# own default (config.STEEL_E), not repeated a third time here.
STD_PIPELINE = BasePipeline(OD_pipe=config.OD_PIPE_DEF, t_pipe=config.T_WALL_DEF)


# ===========================================================================
# Profile query results
# ===========================================================================

@dataclass(frozen=True)
class Section:
    """The pipe's own beam section at an axial station."""
    OD: float
    t: float
    owner: str                       # item code that set it

    @property
    def ID(self) -> float:
        return self.OD - 2 * self.t

    @property
    def I(self) -> float:
        return self.OD ** 4 - self.ID ** 4


class LoadPath(Enum):
    """How a contact reaction reaches the pipeline's own nodes.

    PIPE_ELEMENT -- the contacting surface IS the pipe's outer surface, so
        the reaction is already on the element carrying it. No transfer.
    CONNECTOR    -- the contacting surface belongs to an externally-attached
        body (Sec.0.5). The reaction travels contact point -> structure
        member -> F/P/S/D connector -> pipe node, and MUST carry the moment
        arm; dropping it loses R * arm, which for GD-SB at its default depth
        is the elevation effect the component exists to produce.
    """
    PIPE_ELEMENT = 'pipe_element'
    CONNECTOR = 'connector'


@dataclass(frozen=True)
class Contact:
    """The lowest surface at an axial station -- what a roller actually
    touches, and where its reaction has to go."""
    y: float                         # m, offset from pipe C/L. y is
                                      # POSITIVE-DOWN (item 26), so a
                                      # surface BELOW the pipe has y > 0.
    owner: str                       # item code owning the surface
    load_path: LoadPath
    arm: float                       # m, |y|; moment arm about the pipe C/L

    @property
    def depth(self) -> float:
        return self.y


# ===========================================================================
# Mesh / contact advisories and the node/line framework
#   Tracker items 15 (four lists), 19 (structural_line_id), 21 (moment arm),
#   22 (DERIVED not stored), 23 (taper grading), 24 (advisories).
#
# These are DECLARATIVE DATA ABOUT A COMPONENT, not meshing logic. The
# component states facts about itself ("my taper is 0.126 m and needs at
# least 2 elements"); the MESHER owns the algorithm that turns those facts
# into an actual node distribution. component_spec still meshes nothing.
# ===========================================================================

class NodePriority(Enum):
    """Whether a declared node MUST become an exact mesh node.

    MANDATORY only at a SECTION or SLOPE DISCONTINUITY -- an element
    straddling one gets a single averaged section and smears the feature.

    ALSO MANDATORY at a TOPOLOGICAL JUNCTION -- a point where a second
    structural line joins this one (a Tee: GD-VLV's stem root, GD-B's Tee
    on the header). Added 23 Aug 2026; the rule previously read "only at a
    section or slope discontinuity", which is a statement about the
    SECTION and silently omitted CONNECTIVITY. A branch line cannot attach
    to the interior of an element: unlike contact, which distributes to the
    bracketing nodes by shape functions, a shared structural node either
    exists or the two lines are not connected at all. GD-VLV happened to
    satisfy this by accident -- its Tee coincides with a run station that
    is mandatory for section reasons -- which is exactly why the rule
    needed stating rather than being left to coincidence.

    NEVER driven by contact. The sliding formulation places contact at a
    VIRTUAL PARAMETRIC POINT inside an element (`slide_coeffs_x`) and
    distributes the constraint to the two bracketing nodes by shape
    functions, so a roller may sit anywhere along an element and forcing a
    node there buys nothing. Consistent with the finding that only
    section-changing components need mesh snapping; a shroud does not,
    because its contact offset is evaluated continuously.
    """
    MANDATORY = 'mandatory'
    PREFERRED = 'preferred'


@dataclass(frozen=True)
class MeshAdvice:
    """What a component knows about how its own span should be meshed.

    ADVISORY. The mesher may override any of it, but SHOULD LOG when it
    does -- silently ignoring a min_elements request is exactly how the
    short-taper sliver problem reappears unnoticed.

    min_elements    count  fewest elements on this segment. 1 = no opinion.
    max_size_ratio  --     largest permitted length ratio against an
                            ADJACENT segment. FEA grading guidance is
                            1.5-2.0.
    target_elem_len m      suggested element length for THIS segment,
                            overriding the global default. None = no opinion.
    """
    min_elements: int = 1
    max_size_ratio: float = 2.0
    target_elem_len: Optional[float] = None
    note: str = ''

    def __post_init__(self):
        if self.min_elements < 1:
            raise ValueError('min_elements must be >= 1')
        if self.max_size_ratio < 1.0:
            raise ValueError('max_size_ratio must be >= 1.0')


@dataclass(frozen=True)
class ContactAdvice:
    """How contact on a component's surface should be APPLIED once it
    lands. Complements GeometryLine's `structural_line_id` (WHERE the load
    goes) and `owns_contact` (WHETHER this line is a candidate at all).

    normal_is_collinear_with_offset
        True  -> the contact normal passes through the structural line's
                 neutral axis, so r x F = 0 and the moment is ZERO no
                 matter how large the geometric offset (pipeline, GD-TP,
                 GD-TT, GD-PIP, and GD-SH's FLAT span).
        False -> the normal tilts away from the offset and a genuine
                 moment arises (GD-SH's TAPERS; GD-ST/GD-SB via connectors).

        POSITION-DEPENDENT WITHIN A COMPONENT: GD-SH is True on its flat
        section and False on its tapers, so this cannot be a single
        per-component constant in the general case.

        `Contact.arm` is STILL RETURNED when this is True and the moment is
        therefore zero. Deliberate: if ROLLER FRICTION is added later the
        force is no longer purely normal, the collinearity argument breaks,
        and the arm becomes load-bearing.

    requires_node_at_contact
        Almost always False -- see NodePriority.
    """
    normal_is_collinear_with_offset: bool = True
    requires_node_at_contact: bool = False
    note: str = ''


@dataclass(frozen=True)
class GeometryNode:
    """A point on a geometry line. Geometry lines answer 'what shape is
    here / what surface could a roller touch', NOT 'what carries load'."""
    node_id: str
    x: float                    # m, REFERENCE frame, absolute
    y: float                    # m, from pipe C/L; POSITIVE = below (item 26)
    priority: 'NodePriority' = NodePriority.PREFERRED


@dataclass(frozen=True)
class StructuralNode:
    """A point on a structural line -- becomes an FEA beam node."""
    node_id: str
    x: float                    # m, REFERENCE frame, absolute
    y: float                    # m, from pipe C/L; POSITIVE = below (item 26)
    priority: 'NodePriority' = NodePriority.PREFERRED


@dataclass(frozen=True)
class GeometryLine:
    """A bounding/contact surface segment.

    owns_contact -- queryable, so no consumer needs to know which component
    types are which. GD-ST's rectangle is SHAPE ONLY (it sits above the
    pipe, contact_at returns None) and must never be picked up by anything
    iterating geometry lines for contact candidates.

    structural_line_id -- where a contact load landing on THIS surface gets
    transferred to. ALWAYS POPULATED, NEVER NULL: GD-SH sets it to the
    pipeline's line precisely so the solver never has to ask 'is this a
    shroud?'.
    """
    line_id: str
    node_ids: tuple
    structural_line_id: str
    owns_contact: bool
    contact_advice: ContactAdvice = field(default_factory=ContactAdvice)


@dataclass(frozen=True)
class StructuralLine:
    """A load-carrying segment -- becomes beam elements when meshed.

    Stiffness is expressed exactly ONE of THREE ways, never more:

      * `section` present -> stiffness DERIVES from real section properties
        (pipeline, GD-TP, GD-TT, GD-PIP, GD-VLV). Mesh-INDEPENDENT: a real
        cross-section does not change with discretisation.

      * `stiffness_ratio` present -> the member's element stiffness matrix
        is that ratio times a PLAIN PIPE ELEMENT OF THE SAME LENGTH:

              K_member(L) = stiffness_ratio * K_pipe(L)

        Used where the component has no genuine pipe-like cross-section to
        derive from (GD-ST's frame, GD-SB's structure).

      * `stiffness_rule` present -> the section VARIES along the segment, so
        no single value can be stored and the mesher must query
        `section_at(x)` PER ELEMENT. Currently only GD-TT's two tapers,
        where OD ramps continuously between the NIB and body zones.

    WHY A RATIO, NOT A SINGLE STIFFNESS NUMBER. A 2D beam element's
    stiffness matrix contains terms scaling as EA/L, 12EI/L^3, 6EI/L^2,
    4EI/L and 2EI/L -- no single scalar can stand in for all of them. A
    dimensionless multiplier on the whole matrix scales every term
    consistently and leaves ALL length-dependence to the pipe element
    formula, which the solver already has. Equivalent to scaling both EA
    and EI by the same factor.

    NOTE ON THE OLD 1x-OD FLOOR. An earlier formulation floored the
    effective length at one pipe OD, to avoid "artificially huge stiffness
    for very short elements". Under the ratio that floor is UNNECESSARY and
    would be HARMFUL: if L is small, K_pipe(L) is already large and the
    member should be proportionally large too. Flooring it would make the
    member artificially SOFT at short lengths and break the fixed
    proportion that makes the ratio meaningful. Short-element conditioning
    is a MESHING concern (mesh grading), not a stiffness-definition one --
    `mesh_advice` governs discretisation, `stiffness_ratio` governs
    stiffness, and the two must not be conflated.
    """
    line_id: str
    node_ids: tuple
    section: Optional[Section] = None
    stiffness_rule: Optional[str] = None
    stiffness_ratio: Optional[float] = None
    mesh_advice: MeshAdvice = field(default_factory=MeshAdvice)


def _s_id(node_id: str) -> str:
    """Geometry node id -> its structural twin, ONE uniform rule.

    Every component tag is `CODE@+X.XXXX` and contains no colon, so the
    FIRST colon always separates tag from local name: `GD-ST@+0.0000:cBL`
    -> `GD-ST@+0.0000:scBL`. Introduced 23 Aug 2026 to replace per-name
    literal substitutions, which silently missed any node name added after
    the substitution list was written (GD-ST's top/left/right edge nodes
    were exactly that failure).
    """
    tag, _, local = node_id.partition(':')
    return f'{tag}:s{local}'


PIPELINE_GEOMETRY_LINE_ID = 'pipeline'
PIPELINE_STRUCTURAL_LINE_ID = 'pipeline'


# ===========================================================================
# Component base
# ===========================================================================

@dataclass(frozen=True)
class Component:
    """Base for every GD- component.

    Subclasses declare FREE parameters as fields and DERIVED quantities as
    properties. `validate()` is called once at construction.

    Two profile functions are the entire interface to the FEA layer, and
    they are deliberately INDEPENDENT of each other:

      section_at(x) -> Section | None   the pipe's own beam section
      contact_at(x) -> Contact | None   the surface a roller touches

    GD-SH is why they must stay independent: Sec.2.4 states the shroud adds
    no material to the pipe cross-section, so it returns None from
    section_at and a real surface from contact_at. Any implementation that
    derives one from the other cannot represent it.

    `code` and `iw_ea_class` are two deliberately separate naming systems
    (COMPONENT_GEOMETRY_DEFINITIONS.md §0.4), never to be confused:
    `code` (GD-xx) is this document's own internal registry -- shorthand
    for a specific MODELLING decision (e.g. GD-TT means "thick body welded
    to a tapered transition, both combined" -- a scope choice, not a
    physical description on its own). `iw_ea_class` is the PUBLISHED
    PAPER's physical taxonomy (IW-A/IW-P, EA-O, EA-ST, EA-SB, ...) -- what
    kind of real-world thing this is. The relationship is many-to-one in
    one direction only: several GD- codes can share one iw_ea_class (GD-TP
    and GD-TT both touch IW-A/IW-P), but a given GD- code's own
    iw_ea_class is fixed, not a set the caller chooses from. This module
    must never mint a competing code namespace for anything the published
    taxonomy already owns (§0.4's own stated reason connection systems
    F1/F2/PS/PSD have no GD- code).
    """
    pipe: BasePipeline
    centre_x: float = 0.0
    provenance: Provenance = Provenance.ILLUSTRATIVE

    code: str = field(init=False, default='GD-??')
    iw_ea_class: tuple = field(init=False, default=())

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        pass

    @property
    def extent(self) -> tuple[float, float]:
        raise NotImplementedError

    def owns(self, x: float) -> bool:
        x0, x1 = self.extent
        return x0 - 1e-12 <= x <= x1 + 1e-12

    def section_at(self, x: float) -> Optional[Section]:
        return None

    def contact_at(self, x: float) -> Optional[Contact]:
        return None

    def junctions(self) -> list:
        """(node_id, target_line_id) -- nodes that MUST merge onto another
        structural line. Empty for most components.

        WHY THIS EXISTS. The mesher's merge rule is "merge only where a
        junction is DECLARED, never by coordinate coincidence" -- because
        coincidence gets it wrong in both directions and silently: GD-B's
        tee must merge, its valve node must not; a GD-ST F connector must
        merge, a GD-ST frame node that happens to land on a pipe x must
        not (that last one already turned a two-point attachment into a
        continuous stiffener once).

        A rule like that needs something to read. Before this accessor the
        SAME fact was declared three different ways across three
        components: GD-SH named 'pipeline' on its GEOMETRY lines, GD-VLV
        returned 'pipeline' as one of its STRUCTURAL lines, and GD-B
        declared it NOWHERE AT ALL -- the tee's obligation to join the
        header existed only in prose. A mesher cannot act on prose, and
        would have left the branch floating while the model still
        assembled and still converged.

        NOT the same question as "which line do my elements belong to",
        which `structural_lines()` already answers. A junction is about
        the IDENTITY of a node across two lines. GD-VLV shows the
        difference: it returns real `pipeline` line segments because its
        run IS the pipe over its extent, AND its stem root is a junction
        because the stem is a second line meeting the run there.

        Returns [] by default. Components attaching through CONNECTOR
        ELEMENTS rather than shared nodes (GD-ST, GD-SB) are deliberately
        NOT junctions -- a 2-node connector is a distinct mechanism, still
        open under items 8/9/25, and folding it in here would decide that
        by accident."""
        return []

    def _require_design(self, what: str) -> None:
        if self.provenance is Provenance.ILLUSTRATIVE:
            raise GeometryRuleError(
                f'{self.code}: {what} refused -- provenance is ILLUSTRATIVE. '
                'These values were chosen for figure legibility, not design. '
                'Set provenance=Provenance.DESIGN (or PAPER) once the numbers '
                'are real.')


# ===========================================================================
# Section 1 -- Thick Pipe Body [GD-TP]
# ===========================================================================

@dataclass(frozen=True)
class ThickPipeBody(Component):
    """Sec.1. Section Modifier: a bounded span of the pipe's own elements
    with a heavier wall.

    NOTE WHICH PARAMETER IS FREE. Sec.1.6 derives `OD_comp = ID + 2*t_comp`
    -- constant bore is the governing rule (Sec.1.3), so wall thickness is
    the design variable and OD is its consequence. `OD_comp` is therefore a
    read-only property here, and passing it is a TypeError. This is the
    exact error Sec.1.8 says the section exists to prevent, now unavailable
    rather than merely warned against.

    t_comp/L_comp defaults corrected 16 Aug 2026: now pipe-relative
    (2.5*t_pipe, 2.5*OD_pipe) rather than fixed literals unrelated to the
    pipe in force. This changed the actual numbers at STD_PIPELINE (was
    0.065/1.2, now 0.0525/1.016) -- unlike OffsetShroud/TopStructure/
    BaseStructure's default_for() additions, which reproduced their
    existing literal exactly, this one does not: it is a genuine
    correction, not just a re-sourcing of the same value.
    """
    t_comp: float = 0.0525            # m, FREE (Sec.1.5) -- 2.5*STD_PIPELINE.t_pipe
    L_comp: float = 1.016              # m, FREE (Sec.1.5) -- 2.5*STD_PIPELINE.OD_pipe
    t_comp_min: Optional[float] = None   # m, code floor if known (Sec.1.4)

    code: str = field(init=False, default='GD-TP')
    iw_ea_class: tuple = field(init=False, default=('IW-A', 'IW-P'))

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """Pipe-relative defaults for t_comp/L_comp -- the SINGLE place
        this relationship is computed, matching the pattern already used
        by OffsetShroud/TopStructure/BaseStructure. t_comp/L_comp's
        dataclass defaults above are literals equal to this formula's
        output for STD_PIPELINE; any caller building this component
        against a DIFFERENT pipe should use this method rather than
        recomputing 2.5*t_pipe / 2.5*OD_pipe itself."""
        return {'t_comp': 2.5 * pipe.t_pipe,
                'L_comp': 2.5 * pipe.OD_pipe}

    def validate(self) -> None:
        if self.t_comp <= 0 or self.L_comp <= 0:
            raise GeometryRuleError(f'{self.code}: t_comp and L_comp must be positive')
        if self.t_comp < self.pipe.t_pipe:
            raise GeometryRuleError(
                f'{self.code}: t_comp ({self.t_comp*1000:.1f} mm) must be at '
                f'least t_pipe ({self.pipe.t_pipe*1000:.1f} mm) -- Sec.1.3, the '
                'OD grows or stays, it does not shrink. A thinner "thick pipe '
                'body" is a different component with the opposite strain '
                'mechanism.')
        # RELAXED from > to >= on 5 Sep 2026. EQUAL is now legal and means a
        # NEUTRAL section: OD_comp == OD_pipe, V == 0, wt_ratio == 1. The
        # component is geometrically indistinguishable from the header pipe
        # but is still a distinct artifact that owns the section over its span
        # and carries a conMid attachment station.
        #
        # WHY. A connector may not attach to plain line pipe (DNV: it is line
        # pipe, not a structural member), so the header must be split and a
        # GD-TP introduced wherever a connector lands. Under the old strict
        # rule that unavoidably added a stiffness step, even when the thick
        # section was there only to carry the attachment and the study was
        # about the connection rather than about a thick pipe. Equality lets
        # the attachment be represented without that step.
        #
        # It does NOT license a thinner section: the strain mechanism of a
        # thinned run is the opposite one, and that is still rejected.
        if self.t_comp_min is not None and self.t_comp < self.t_comp_min:
            raise GeometryRuleError(
                f'{self.code}: t_comp ({self.t_comp*1000:.1f} mm) is below the '
                f'code floor ({self.t_comp_min*1000:.1f} mm) -- Sec.1.4, '
                'ASME VIII Div.2 / B16.34 minimum wall.')

    # --- derived (Sec.1.6) -------------------------------------------------
    @property
    def ID_comp(self) -> float:
        return self.pipe.ID                       # constant bore, Sec.1.4

    @property
    def OD_comp(self) -> float:
        return self.pipe.ID + 2 * self.t_comp     # Sec.1.6

    @property
    def V(self) -> float:
        """Roller elevation rise (Sec.1.6) -- the secondary Type-B-like
        effect. Note this is a CONSEQUENCE of the section here, unlike
        GD-SH where V is the free parameter."""
        return (self.OD_comp - self.pipe.OD_pipe) / 2

    @property
    def I_ratio(self) -> float:
        return (self.OD_comp ** 4 - self.ID_comp ** 4) / self.pipe.I_pipe

    @property
    def wt_ratio(self) -> float:
        return self.t_comp / self.pipe.t_pipe

    @property
    def extent(self) -> tuple[float, float]:
        return (self.centre_x - self.L_comp / 2, self.centre_x + self.L_comp / 2)

    @property
    def EI_comp(self) -> float:
        """Real section bending stiffness. Same formula as BasePipeline.EI,
        evaluated with THIS component's OD/ID. Mesh-INDEPENDENT, unlike
        GD-ST's kT: a real cross-sectional property does not change with
        discretisation, so there is no element-length floor to guard."""
        I_true = pi / 64 * (self.OD_comp ** 4 - self.ID_comp ** 4)
        return self.pipe.E * I_true

    # --- node/line accessors: DERIVED, never stored ------------------------
    @property
    def _node_id_lo(self) -> str:
        """Left girth-weld end. Emitted as ':weldL' since 4 Sep 2026.

        Was ':lo' -- generic min/max naming that said nothing about the
        joint being a girth weld, and the only inline component in the
        library that did not use the ':weldL'/':weldR' convention its
        siblings (TaperedThickBody, Valve, PipBulkhead) already followed.
        The Python property keeps its `_lo` name so nothing internal
        changes; only the emitted node id moves.
        """
        return f'{self.code}@{self.centre_x:+.4f}:weldL'

    @property
    def _node_id_hi(self) -> str:
        """Right girth-weld end. Was ':hi' -- see `_node_id_lo`."""
        return f'{self.code}@{self.centre_x:+.4f}:weldR'

    @property
    def _node_id_mid(self) -> str:
        """Mid-body connector station. Added 1 Sep 2026.

        WHY IT EXISTS. This is the attachment point for a FIXED (type F)
        structural connector on the thickened body -- the mechanism the
        component previously lacked, which is why Func2 was recorded as
        unrealisable here and why F was excluded from the permitted set.
        The exclusion rested on there being 'no lever arm in a plain wall
        to react a moment without local overstress'; that argument is
        about a PLAIN wall, and this component is a thickened one, which
        is precisely the wall the objection said was missing. F remains
        excluded on the plain run either side -- the permission is scoped
        to THIS station, not to the component.

        NOT a section discontinuity, unlike :lo and :hi. It is MANDATORY
        anyway, for a different reason: a connector node the mesher merged
        away or moved would silently delete the connection it carries. Same
        reasoning as GD-B's valve node, which is likewise MANDATORY without
        being a section change.
        """
        return f'{self.code}@{self.centre_x:+.4f}:conMid'

    def geometry_nodes(self) -> list:
        """Three nodes ON THE CONTACT SURFACE (y = -OD_comp/2), NOT on the
        centreline. A geometry line represents the bounding/contact
        surface; the centreline is what the STRUCTURAL line represents.
        Keeping these distinct is the whole point of having two line sets.

        The middle node is the connector station (see `_node_id_mid`); the
        outer two are the section-step boundaries.
        """
        x_lo, x_hi = self.extent
        y = self.OD_comp / 2
        return [GeometryNode(self._node_id_lo, x_lo, y, NodePriority.MANDATORY),
                GeometryNode(self._node_id_mid, self.centre_x, y, NodePriority.MANDATORY),
                GeometryNode(self._node_id_hi, x_hi, y, NodePriority.MANDATORY)]

    def structural_nodes(self) -> list:
        """MANDATORY: GD-TP is an abrupt section step (no taper), so an
        element straddling either boundary would average two sections. The
        middle node is MANDATORY for the separate reason given in
        `_node_id_mid` -- it carries a connector, not a section change."""
        x_lo, x_hi = self.extent
        return [StructuralNode(self._node_id_lo, x_lo, 0.0, NodePriority.MANDATORY),
                StructuralNode(self._node_id_mid, self.centre_x, 0.0, NodePriority.MANDATORY),
                StructuralNode(self._node_id_hi, x_hi, 0.0, NodePriority.MANDATORY)]

    def geometry_lines(self) -> list:
        """TWO segments, SHARED with the pipeline, both owning contact --
        the thickened OD is genuinely what a roller touches over this span.

        Subdivided at the mid connector station rather than running lo->hi
        as one segment. A node that is not an element boundary carries no
        load: a connector attached to the interior of an element has
        nothing to attach TO. Same rule GD-ST applies when subdividing each
        frame edge at every connector slot. The two segments are otherwise
        identical -- same line id, same section, same contact advice --
        so this changes discretisation, not physics.
        """
        adv = ContactAdvice(
            normal_is_collinear_with_offset=True,
            requires_node_at_contact=False,
            note='Concentric section: normal is radial and passes '
                  'through the neutral axis, so the moment is zero. '
                  'Applying an arm would also double-count, since the '
                  'beam element IS the pipe and section properties '
                  'already carry outer-fibre load.')
        ids = (self._node_id_lo, self._node_id_mid, self._node_id_hi)
        return [GeometryLine(
            line_id=PIPELINE_GEOMETRY_LINE_ID,
            node_ids=(a, b),
            structural_line_id=PIPELINE_STRUCTURAL_LINE_ID,
            owns_contact=True,
            contact_advice=adv) for a, b in zip(ids, ids[1:])]

    def structural_lines(self) -> list:
        """TWO segments, SHARED with the pipeline, each carrying THIS
        component's section. `section` present (not `stiffness_rule`)
        because stiffness derives from real geometry. Subdivided at the
        mid connector station for the reason given in `geometry_lines`."""
        sec = Section(OD=self.OD_comp, t=self.t_comp, owner=self.code)
        ids = (self._node_id_lo, self._node_id_mid, self._node_id_hi)
        return [StructuralLine(
            line_id=PIPELINE_STRUCTURAL_LINE_ID,
            node_ids=(a, b),
            section=sec) for a, b in zip(ids, ids[1:])]

    def section_at(self, x: float) -> Optional[Section]:
        if not self.owns(x):
            return None
        return Section(OD=self.OD_comp, t=self.t_comp, owner=self.code)

    def contact_at(self, x: float) -> Optional[Contact]:
        if not self.owns(x):
            return None
        y = self.OD_comp / 2
        return Contact(y=y, owner=self.code, load_path=LoadPath.PIPE_ELEMENT,
                        arm=abs(y))


# ===========================================================================
# Sections 1+3 -- Thick Pipe Body + Tapered Transition [GD-TT]
# ===========================================================================

@dataclass(frozen=True)
class TaperedThickBody(ThickPipeBody):
    """Sec.1 + Sec.3. The common real-world case: a thick body with a
    symmetric tapered transition and NIB at each girth-welded end.

    `L_taper` is NOT free -- Sec.3.6 derives it as `n * dr`. This is the
    same correction v5.0 applied to GD-PIP's 0.45 m; making it a property
    means it cannot be reintroduced.
    """
    n: float = 4.0                    # taper ratio 1:n, FREE (Sec.3.5)
    L_NIB: Optional[float] = None      # m, FREE (Sec.3.5); None -> derived

    code: str = field(init=False, default='GD-TT')
    iw_ea_class: tuple = field(init=False, default=('IW-A', 'IW-P'))

    def __post_init__(self):
        """Resolve `L_NIB` from the PIPE when omitted, BEFORE
        `super().__post_init__()` runs `validate()` -- the same ordering
        `P_b3`, `P_bv` and `P_c1`/`P_c2` use.

        It was a fixed 0.25 m, which does not scale. The NIB is the
        undisturbed run between the girth weld and the taper toe, and the
        length it must have is set by how far the weld's local bending
        takes to die away: `l_e = sqrt(r t) / (3(1-nu^2))^(1/4)`, with the
        floor at 4 of them (1.8% remaining). Both r and t are the PARENT
        pipe's, so the floor grows with diameter while a constant does
        not, and 0.25 m stopped clearing it at about 25 in.

        An EXPLICIT value is still honoured untouched -- `validate()` then
        checks it against the same floor, so a hand-set NIB can be larger
        than the derived one but never smaller.
        """
        if self.L_NIB is None:
            object.__setattr__(self, 'L_NIB', self.pipe.NIB_default)
        super().__post_init__()

    def validate(self) -> None:
        super().validate()
        # STRICTER than the parent here, deliberately. ThickPipeBody was
        # relaxed to t_comp >= t_pipe on 5 Sep 2026 so a neutral section can
        # carry a connector without adding a stiffness step. That relaxation
        # CANNOT extend to this class: the taper length is n*dr, and dr is
        # (OD_comp - OD_pipe)/2, so an equal wall gives a taper of zero
        # length. The stations then coincide -- taperL with bodyL, bodyR with
        # taperR -- producing two zero-length segments, which is the
        # degenerate case the rest of this module guards against everywhere
        # else.
        #
        # A tapered body with no taper is not a tapered body; it IS a
        # ThickPipeBody. So the caller is sent there rather than given a
        # component whose defining feature has vanished.
        if self.t_comp <= self.pipe.t_pipe:
            raise GeometryRuleError(
                f'{self.code}: t_comp ({self.t_comp*1000:.1f} mm) must EXCEED '
                f't_pipe ({self.pipe.t_pipe*1000:.1f} mm), not merely equal it. '
                'This component is defined by its taper, and taper length is '
                'n*dr with dr = (OD_comp - OD_pipe)/2 -- an equal wall gives a '
                'zero-length taper and two zero-length segments. For a NEUTRAL '
                'section that carries a connector without a stiffness step, '
                'use GD-TP with t_comp = t_pipe, which is legal.')
        if self.n < 4:
            raise GeometryRuleError(
                f'{self.code}: n = {self.n} violates the DNV-ST-F101 Sec.5.6 '
                'minimum taper slope of 1:4 (Sec.3.4).')
        if self.L_NIB < self.pipe.NIB_min - 1e-12:
            raise GeometryRuleError(
                f'{self.code}: L_NIB ({self.L_NIB*1000:.1f} mm) is below '
                f'NIB_min = {self.pipe.NIB_min*1000:.0f} mm '
                f'(4*l_e = {self.pipe.NIB_dnv*1000:.1f} mm, to nearest 50) '
                '(DNV-ST-F101 Sec.5.6.1.7, Sec.3.3).')

    # --- derived (Sec.3.6) -------------------------------------------------
    @property
    def dr(self) -> float:
        return (self.OD_comp - self.pipe.OD_pipe) / 2

    @property
    def L_taper(self) -> float:
        return self.n * self.dr

    @property
    def L_transition(self) -> float:
        return self.L_NIB + self.L_taper

    @property
    def L_total(self) -> float:
        return self.L_comp + 2 * self.L_transition

    # --- station positions, outward from the body centre -------------------
    @property
    def x_body(self) -> tuple[float, float]:
        return (self.centre_x - self.L_comp / 2, self.centre_x + self.L_comp / 2)

    @property
    def x_taper(self) -> tuple[float, float]:
        bL, bR = self.x_body
        return (bL - self.L_taper, bR + self.L_taper)

    @property
    def x_weld(self) -> tuple[float, float]:
        tL, tR = self.x_taper
        return (tL - self.L_NIB, tR + self.L_NIB)

    @property
    def extent(self) -> tuple[float, float]:
        return self.x_weld

    def OD_at(self, x: float) -> Optional[float]:
        """Outer diameter profile -- the genuine wedge, not a flat span.
        This single function is what both the schematic's taper polygon and
        the FEA section assignment read."""
        if not self.owns(x):
            return None
        bL, bR = self.x_body
        tL, tR = self.x_taper
        if bL <= x <= bR:
            return self.OD_comp
        if tL <= x < bL:
            f = (x - tL) / self.L_taper          # 0 at taper start -> 1 at body
            return self.pipe.OD_pipe + f * 2 * self.dr
        if bR < x <= tR:
            f = (tR - x) / self.L_taper
            return self.pipe.OD_pipe + f * 2 * self.dr
        return self.pipe.OD_pipe                  # NIB: plain-pipe land (Sec.3.1)

    def section_at(self, x: float) -> Optional[Section]:
        OD = self.OD_at(x)
        if OD is None:
            return None
        # Constant bore throughout (Sec.1.4) -- the taper is an OD change,
        # so wall thickness follows OD, not the other way round.
        return Section(OD=OD, t=(OD - self.pipe.ID) / 2, owner=self.code)

    # --- node/line accessors: DERIVED, never stored ------------------------
    @property
    def _station_xs(self) -> list:
        """Seven boundary stations, left to right, each with a stable id.

        `conMid` added 1 Sep 2026: the mid-body attachment point for a
        FIXED (type F) structural connector -- see ThickPipeBody._node_id_mid
        for why the F exclusion does not apply at this station. It sits
        INSIDE the constant-OD body (between bodyL and bodyR) and never on a
        taper: a fixed connector on a tapering wall would sit on a varying
        section, which is the condition the taper exists to smooth away.

        The other six are OD-profile discontinuities; conMid is not. Every
        accessor below derives from this list, so adding the station here is
        the only change needed -- nodes, lines and their counts all follow.
        NOTE this list is inherited by PipBulkhead, which appends its outer
        stations to whatever this returns, so GD-PIP gains conMid too.
        """
        wL, wR = self.x_weld
        tL, tR = self.x_taper
        bL, bR = self.x_body
        tag = f'{self.code}@{self.centre_x:+.4f}'
        return [(f'{tag}:weldL', wL), (f'{tag}:taperL', tL),
                (f'{tag}:bodyL', bL),
                (f'{tag}:conMid', self.centre_x),
                (f'{tag}:bodyR', bR),
                (f'{tag}:taperR', tR), (f'{tag}:weldR', wR)]

    def geometry_nodes(self) -> list:
        """Six nodes ON THE CONTACT SURFACE (y = -OD_at(x)/2), NOT on the
        centreline -- so the line steps down through each taper and runs
        flat across the body. The STRUCTURAL nodes stay at y=0 (the beam
        centreline); that difference is exactly what the two line sets are
        for."""
        return [GeometryNode(nid, x, self.OD_at(x) / 2, NodePriority.MANDATORY)
                for nid, x in self._station_xs]

    def structural_nodes(self) -> list:
        """ALL SIX MANDATORY: every station is a slope or section
        discontinuity in the OD profile. An element straddling one gets a
        single averaged section and smears the feature."""
        return [StructuralNode(nid, x, 0.0, NodePriority.MANDATORY)
                for nid, x in self._station_xs]

    def geometry_lines(self) -> list:
        """One segment between each consecutive pair of stations, all SHARED
        with the pipeline, all owning contact.

        Count DERIVED from `_station_xs`, not hard-coded. It was
        `range(5)` until 1 Sep 2026, which silently stopped covering the
        component the moment a seventh station (conMid) was added: seven
        nodes still produced five segments, leaving the last two stations
        unlinked. Deriving the count means a future station insertion needs
        no change here.
        """
        st = self._station_xs
        adv = ContactAdvice(
            normal_is_collinear_with_offset=True,
            requires_node_at_contact=False,
            note='Concentric EVEN ACROSS THE TAPERS: OD changes but the '
                  'section stays concentric, so the normal still points at '
                  'the centreline. Contrast GD-SH, whose taper is an OFFSET '
                  'surface and therefore does tilt the normal.')
        return [GeometryLine(line_id=PIPELINE_GEOMETRY_LINE_ID,
                              node_ids=(st[i][0], st[i + 1][0]),
                              structural_line_id=PIPELINE_STRUCTURAL_LINE_ID,
                              owns_contact=True, contact_advice=adv)
                for i in range(len(st) - 1)]

    def structural_lines(self) -> list:
        """Five segments. NIB and body are CONSTANT section (declared
        directly); the two tapers VARY, so they declare no fixed section and
        set stiffness_rule='section_at' -- the mesher must query
        section_at(x) per element rather than assume one value."""
        st = self._station_xs
        plain = Section(OD=self.pipe.OD_pipe, t=self.pipe.t_pipe,
                        owner=self.code)
        body = Section(OD=self.OD_comp, t=self.t_comp, owner=self.code)
        # One entry per SEGMENT, DERIVED from the OD profile rather than
        # written as a literal. For each consecutive station pair, the OD at
        # the two ends is compared: equal means the section is constant over
        # that segment and can be declared directly; unequal means it varies
        # and the mesher must query section_at(x) per element.
        #
        # This replaced a 5-entry literal on 1 Sep 2026. The literal encoded
        # both the NUMBER of segments and their order, so it silently became
        # wrong the moment a station was inserted -- and it made any
        # subclass that changes the station list (PipBulkhead, which drops
        # conMid) impossible without editing this method too. Deriving it
        # means the zone mapping follows the stations automatically, however
        # many there are.
        zones = []
        for i in range(len(st) - 1):
            od_a = self.OD_at(st[i][1])
            od_b = self.OD_at(st[i + 1][1])
            if od_a is None or od_b is None or abs(od_a - od_b) > 1e-12:
                zones.append(None)                       # varies across it
            elif abs(od_a - self.OD_comp) <= 1e-12:
                zones.append(body)                       # constant, body OD
            else:
                zones.append(plain)                      # constant, plain OD
        # Grading figures are COMPUTED, never literal. They were once
        # hard-coded as '~268:1' and '~0.88 m per side' -- correct only for
        # STD_PIPELINE at every default. At t_comp=0.042/n=4 the true ratio
        # is 906:1 (understated 3.4x); at the catalogue's own t_comp=0.065/
        # n=16 case it is 1.54:1 (overstated ~175x, crying wolf where
        # grading barely matters). A confidently specific wrong number is
        # worse than a vague warning, because the precision invites trust.
        L_elem = 2.0 * self.pipe.OD_pipe            # the 2*OD default
        k_ratio = (L_elem / self.L_taper) ** 3      # transverse k ~ EI/L^3
        # Intermediate elements needed to climb from L_taper to L_elem at
        # max_size_ratio=2. If ONE doubling already reaches L_elem, the
        # default element may sit straight against the taper and no run-up
        # is needed at all -- k = 0, not 1.
        k = max(0, math.ceil(math.log(max(L_elem / self.L_taper, 1.0), 2.0)) - 1)
        run_up = self.L_taper * (2.0 ** (k + 1) - 2.0)   # geometric sum
        fits = run_up <= min(self.L_NIB, self.L_comp / 2.0)
        taper_adv = MeshAdvice(
            min_elements=2, max_size_ratio=2.0,
            target_elem_len=self.L_taper / 2.0,
            note=(f'Taper is {self.L_taper:.3f} m vs a {L_elem:.3f} m '
                  f'(2*OD) default element. GRADE adjacent elements down to '
                  f'reach this segment -- do NOT drop one short element '
                  f'between two long ones (transverse k ~ EI/L^3, so an '
                  f'ungraded jump gives a ~{k_ratio:.0f}:1 stiffness ratio '
                  f'and risks a sliver convergence failure). The graded '
                  f'run-up at max_size_ratio=2 needs ~{run_up:.2f} m per '
                  f'side against {self.L_NIB:.2f} m of NIB and '
                  f'{self.L_comp/2:.2f} m of body half, so it '
                  f'{"FITS inside the component" if fits else "does NOT fit: THE MESHER MUST BE ALLOWED TO GRADE OUTSIDE THE COMPONENT EXTENT, past the weld into plain pipe"}.'))
        plain_adv = MeshAdvice(min_elements=1, max_size_ratio=2.0,
                                note='Constant section; grade into the '
                                     'adjacent taper.')
        return [StructuralLine(
                    line_id=PIPELINE_STRUCTURAL_LINE_ID,
                    node_ids=(st[i][0], st[i + 1][0]),
                    section=sec,
                    stiffness_rule=None if sec is not None else 'section_at',
                    mesh_advice=taper_adv if sec is None else plain_adv)
                for i, sec in enumerate(zones)]

    def contact_at(self, x: float) -> Optional[Contact]:
        OD = self.OD_at(x)
        if OD is None:
            return None
        y = OD / 2
        return Contact(y=y, owner=self.code, load_path=LoadPath.PIPE_ELEMENT,
                        arm=abs(y))


# ===========================================================================
# Section 2 -- Offset Element / Shroud [GD-SH]
# ===========================================================================

@dataclass(frozen=True)
class OffsetShroud(Component):
    """Sec.2. Roller Modifier: an external clamp-on collar that changes
    where the roller contacts, and NOTHING about the pipe's own section
    (Sec.2.4 -- "adds no material to the pipe cross-section").

    This component is the reason section_at and contact_at must be
    independent functions. It returns None from one and a real surface from
    the other. Note also that V here is FREE and the elevation is its
    consequence -- the exact inverse of GD-TP, where the section is free and
    V is derived. Same symbol, opposite role; worth keeping straight.
    """
    V: float = 0.4064                 # m, FREE -- depth below pipe C/L (Sec.2.5)
    L1: float = 4.064                  # m, FREE -- deep section length
    L2: float = 2.032                   # m, FREE -- taper length each side.
                                         # Item 14 (16 Aug 2026): corrected
                                         # from 2.5*OD (1.016) to 5*OD.

    code: str = field(init=False, default='GD-SH')
    iw_ea_class: tuple = field(init=False, default=('EA-O',))

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """Pipe-relative defaults (Sec.2.5's own stated ratios: 1D deep
        depth, 10D deep-section length, 5D taper length each side --
        L2's multiplier corrected 16 Aug 2026 from 2.5D; V and L1
        unchanged) --
        the SINGLE place this relationship is computed. V/L1/L2's dataclass
        defaults above are fixed literals that happen to equal this
        formula's output for STD_PIPELINE; any caller building this
        component against a DIFFERENT pipe (including plot_schematic.py)
        should use this method rather than recomputing the ratio itself,
        so the 1D/10D/5D rule is defined once and traceable to this
        class, not duplicated in a plotting driver.
        """
        return {'V': 1.0 * pipe.OD_pipe,
                'L1': 10.0 * pipe.OD_pipe,
                'L2': 5.0 * pipe.OD_pipe}

    def validate(self) -> None:
        if min(self.V, self.L1, self.L2) <= 0:
            raise GeometryRuleError(f'{self.code}: V, L1 and L2 must be positive')
        if self.V < self.pipe.OD_pipe / 2:
            raise GeometryRuleError(
                f'{self.code}: V ({self.V*1000:.1f} mm) is shallower than the '
                f'pipe radius ({self.pipe.OD_pipe/2*1000:.1f} mm), giving a '
                'negative CL_lift -- the shroud would sit inside the pipe.')

    @property
    def CL_lift(self) -> float:
        """Sec.2.6 -- elevation above the baseline pipe-on-roller condition."""
        return self.V - self.pipe.OD_pipe / 2

    @property
    def L_total(self) -> float:
        return self.L1 + 2 * self.L2

    @property
    def x_deep(self) -> tuple[float, float]:
        return (self.centre_x - self.L1 / 2, self.centre_x + self.L1 / 2)

    @property
    def extent(self) -> tuple[float, float]:
        dL, dR = self.x_deep
        return (dL - self.L2, dR + self.L2)

    # --- node/line accessors: DERIVED, never stored ------------------------
    @property
    def _station_xs(self) -> list:
        """Four stations: outer taper tip, deep start, deep end, outer tip."""
        xL, xR = self.extent
        dL, dR = self.x_deep
        tag = f'{self.code}@{self.centre_x:+.4f}'
        return [(f'{tag}:tipL', xL), (f'{tag}:deepL', dL),
                (f'{tag}:deepR', dR), (f'{tag}:tipR', xR)]

    def _y_at(self, x: float) -> Optional[float]:
        """Contact surface elevation -- the same formula contact_at uses,
        factored out so the node accessors and the profile query cannot
        drift apart."""
        c = self.contact_at(x)
        return None if c is None else c.y

    def geometry_nodes(self) -> list:
        """Four nodes on the SHROUD's OWN surface (y != 0) -- unlike
        GD-TP/GD-TT, whose nodes sit on the pipe centreline.

        PREFERRED, not MANDATORY: a shroud needs no mesh snapping, because
        its contact offset is evaluated CONTINUOUSLY at any x rather than
        being tied to a discrete per-element section. This makes explicit
        what was an unwritten special case in the old code, where only
        thick components triggered the snapped mesh rebuild.
        """
        return [GeometryNode(nid, x, self._y_at(x), NodePriority.PREFERRED)
                for nid, x in self._station_xs]

    def structural_nodes(self) -> list:
        """EMPTY -- owns no structural line, so contributes no structural
        nodes. Clamped to the pipe (Sec.2.7); rides the pipeline's nodes."""
        return []

    def geometry_lines(self) -> list:
        """Three segments -- taper / flat / taper -- each pointing at the
        PIPELINE's structural line.

        Contact advice DIFFERS BY SEGMENT: the tapers are inclined so the
        normal tilts away from the offset and a real moment arises, while
        the flat deep section has normal and offset both vertical, hence
        collinear and zero moment. This per-segment variation is exactly
        why ContactAdvice lives on GeometryLine rather than on the
        component as a whole.
        """
        st = self._station_xs
        taper_adv = ContactAdvice(
            normal_is_collinear_with_offset=False,
            requires_node_at_contact=False,
            note='Taper surface is INCLINED, so the contact normal tilts '
                  'away from the vertical offset: the line of action misses '
                  'the neutral axis and a genuine moment arises. Contrast '
                  'GD-TT, whose taper stays CONCENTRIC and so keeps the '
                  'normal pointing at the centreline.')
        flat_adv = ContactAdvice(
            normal_is_collinear_with_offset=True,
            requires_node_at_contact=False,
            note='Flat deep section: normal vertical, offset vertical, '
                  'collinear -> moment is zero here even though V is large.')
        advs = [taper_adv, flat_adv, taper_adv]
        return [GeometryLine(
                    line_id=f'{self.code}@{self.centre_x:+.4f}:surface',
                    node_ids=(st[i][0], st[i + 1][0]),
                    structural_line_id=PIPELINE_STRUCTURAL_LINE_ID,
                    owns_contact=True,
                    contact_advice=advs[i])
                for i in range(3)]

    def structural_lines(self) -> list:
        """EMPTY -- owns none. Its geometry lines point at the pipeline's
        structural line via structural_line_id instead."""
        return []

    def section_at(self, x: float) -> Optional[Section]:
        return None                    # Sec.2.4 -- pipe section is untouched

    def contact_at(self, x: float) -> Optional[Contact]:
        """Sec.2.6's explicit coordinate formula: -V across the deep
        section, a straight ramp to -OD_pipe/2 at each taper's outer end."""
        if not self.owns(x):
            return None
        dL, dR = self.x_deep
        y_out = self.pipe.OD_pipe / 2
        if dL <= x <= dR:
            y = self.V
        elif x < dL:
            f = (x - (dL - self.L2)) / self.L2       # 0 outer -> 1 inner
            y = y_out + f * (self.V - y_out)
        else:
            f = ((dR + self.L2) - x) / self.L2
            y = y_out + f * (self.V - y_out)
        # The shroud is clamped to the pipe with no new nodes (Sec.2.7), so
        # its reaction is carried by the pipe element beneath it -- but at a
        # genuine offset, hence arm != pipe radius.
        return Contact(y=y, owner=self.code, load_path=LoadPath.PIPE_ELEMENT,
                        arm=abs(y))


# ===========================================================================
# Section 5 -- PiP Bulkhead [GD-PIP-R / -L / -B]
# ===========================================================================

@dataclass(frozen=True)
class PipBulkhead(TaperedThickBody):
    """Sec.5. Inner pipe IS GD-TT (Sec.5.2), so this subclasses it rather
    than redeclaring anything -- which is the type-system version of the
    statement Sec.5.2 has made in prose since v2.0.

    The outer/structural pipe is new: one straight beam member per side,
    fixed axial length 1D, CANTILEVERING off a junction on the inner pipe.

    OUTER PIPE, added 30 Aug 2026. Previously the outer pipe existed only
    as the coordinates `x_structural_R/L` -- no line, no nodes, no section,
    no contact. A GD-PIP therefore built the same FE model as the plain
    GD-TT of the same parameters, and `contact_at` returned the INNER
    pipe's surface across the outer pipe's span while its own docstring
    said it declined to. Three facts settled that gap:

      1. CONCENTRIC. The outer pipe shares the pipeline centreline, so its
         structural line sits at y=0 like the inner one, and its contact
         surface is its own bottom OD at y = +OD_outer/2. One radial
         parameter (OD_outer), not two.
      2. INTEGRAL, NOT WELDED, at the junction. The outer pipe is
         manufactured integrally with the inline-welded GD-TT, so the
         junction node carries NO weld. It needs no NIB, no taper and no
         weld-driven mesh refinement -- unlike the girth welds at x_weld.
         The only weld on this component's outer pipe is at its END node,
         where a Boss may be attached.
      3. CANTILEVER. The member is fixed at the junction and free at the
         end node. Nothing restrains the far end in this model.

    `extent` now spans the outer pipe as well, so `owns()` covers the
    cantilever. `OD_at` is re-guarded on the INNER span (x_weld) so that
    `section_at` still answers only for the inner pipe -- the two spans
    are deliberately different questions.

    STILL OUT OF SCOPE: the Boss (a structural pipe welded to an end node,
    carrying the connector element). See the notes on that in EDES.
    """
    x_interior_R: Optional[float] = None    # m, from body centre (Sec.5.3)
    x_interior_L: Optional[float] = None
    OD_outer: Optional[float] = None        # m, outer pipe OD (Sec.5.2)
    t_outer: Optional[float] = None         # m, outer pipe wall

    code: str = field(init=False, default='GD-PIP')
    iw_ea_class: tuple = field(init=False, default=('IW-A',))

    def validate(self) -> None:
        super().validate()
        if self.x_interior_R is None and self.x_interior_L is None:
            raise GeometryRuleError(
                'GD-PIP: at least one interior node is required -- R, L or B.')
        for name, xi in (('x_interior_R', self.x_interior_R),
                          ('x_interior_L', self.x_interior_L)):
            if xi is None:
                continue
            if abs(xi) > self.L_comp / 2 + 1e-12:
                raise GeometryRuleError(
                    f'GD-PIP: {name} = {xi:+.3f} m lies outside the thick body '
                    f'(+/-{self.L_comp/2:.3f} m). Sec.5.2 requires the interior '
                    'node to sit on the inner-pipe region.')
        if (self.x_interior_R is not None and self.x_interior_L is not None
                and abs(self.x_interior_R - self.x_interior_L) <= 1e-9):
            raise GeometryRuleError(
                f'GD-PIP: a B variant needs two DISTINCT junctions, but both '
                f'interior nodes are at {self.x_interior_R:+.4f} m. Coincident '
                'x mints two structural node ids at one point (:outRJn and '
                ':outLJn), and nothing downstream detects the duplicate. If '
                'both outer pipes genuinely spring from one station, that is '
                'ONE shared node, which this class does not yet model.')
        # --- outer pipe (Sec.5.2) -----------------------------------------
        # OD_outer NOW DEFAULTS, t_outer STILL DOES NOT.
        #
        # This block previously required both, on the stated grounds that no
        # basis existed for a pipe-relative default and inventing one would
        # put a guessed diameter into every contact result. That reasoning was
        # correct while no basis existed. One was supplied on 5 Sep 2026: the
        # sleeve is FOUR NOMINAL SIZES larger than the line. That is a rule,
        # not a guess, so the objection no longer applies -- and note it is
        # four sizes larger, NOT OD + 4 inches, which is a different number
        # for every line below NPS 14 (see nps_step_up).
        #
        # t_outer keeps no default because nothing analogous was supplied for
        # it: a wall thickness does not follow from a diameter.
        if self.OD_outer is None:
            object.__setattr__(self, 'OD_outer', nps_step_up(self.pipe.OD_pipe, 4))
        for name, v in (('OD_outer', self.OD_outer), ('t_outer', self.t_outer)):
            if v is None:
                raise GeometryRuleError(
                    f'GD-PIP: {name} is required. The outer pipe is a real '
                    'structural member with a contact surface, so it cannot be '
                    'built from the inner pipe alone (Sec.5.2). Note OD_outer '
                    'now defaults to four nominal sizes above the line; '
                    't_outer does not, because a wall does not follow from a '
                    'diameter.')
            if v <= 0:
                raise GeometryRuleError(f'GD-PIP: {name} must be positive.')
        if self.t_outer >= self.OD_outer / 2:
            raise GeometryRuleError(
                f'GD-PIP: t_outer = {self.t_outer:.4f} m leaves no bore in a '
                f'{self.OD_outer:.4f} m outer pipe.')
        if self.ID_outer <= self.OD_comp + 1e-12:
            raise GeometryRuleError(
                f'GD-PIP: outer pipe bore {self.ID_outer:.4f} m does not clear '
                f'the thick body OD {self.OD_comp:.4f} m. The outer pipe is '
                'concentric and overlaps the body axially, so it must pass '
                'over it (Sec.5.2).')

    @property
    def variant(self) -> str:
        if self.x_interior_R is not None and self.x_interior_L is not None:
            return 'B'
        return 'R' if self.x_interior_R is not None else 'L'

    @property
    def L_outer(self) -> float:
        return self.pipe.OD_pipe              # fixed 1D (Sec.5.2)

    @property
    def ID_outer(self) -> Optional[float]:
        if self.OD_outer is None or self.t_outer is None:
            return None
        return self.OD_outer - 2 * self.t_outer

    @property
    def y_outer_contact(self) -> Optional[float]:
        """Bottom OD of the outer pipe. POSITIVE-DOWN (item 26).

        Concentric with the pipeline, so this is simply OD_outer/2 -- no
        offset term. It is BELOW the inner pipe's surface by construction,
        since validate() requires the bore to clear the thick body.
        """
        if self.OD_outer is None:
            return None
        return self.OD_outer / 2

    @property
    def x_structural_R(self) -> Optional[float]:
        if self.x_interior_R is None:
            return None
        return self.centre_x + self.x_interior_R + self.L_outer

    @property
    def x_structural_L(self) -> Optional[float]:
        if self.x_interior_L is None:
            return None
        return self.centre_x + self.x_interior_L - self.L_outer

    @property
    def _outer_spans(self) -> list:
        """(side, x_junction, x_end) per outer member, root first."""
        out = []
        if self.x_interior_R is not None:
            out.append(('R', self.centre_x + self.x_interior_R,
                        self.x_structural_R))
        if self.x_interior_L is not None:
            out.append(('L', self.centre_x + self.x_interior_L,
                        self.x_structural_L))
        return out

    def _on_outer(self, x: float) -> bool:
        for _, xj, xe in self._outer_spans:
            lo, hi = (xj, xe) if xj <= xe else (xe, xj)
            if lo - 1e-12 <= x <= hi + 1e-12:
                return True
        return False

    # --- extent: inner span vs whole component -----------------------------
    @property
    def x_inner_extent(self) -> tuple:
        """Weld-to-weld span of the inner pipe -- what GD-TT calls `extent`.

        Kept separate because `section_at` must answer for the inner pipe
        only, while `owns()` has to cover the cantilever too.
        """
        return self.x_weld

    @property
    def extent(self) -> tuple[float, float]:
        """Inner span UNION the outer cantilevers.

        Fixes the defect where x_structural_R could fall outside the
        component's own extent for interior positions validate() allows:
        the escape happened whenever OD_pipe > L_transition, which is true
        at every common line size. The outer pipe's reach is part of this
        component, so the span has to say so -- and the end node is where a
        Boss attaches, which makes undefined ownership there worse than
        untidy.
        """
        lo, hi = self.x_weld
        for _, _, xe in self._outer_spans:
            lo = min(lo, xe)
            hi = max(hi, xe)
        return (lo, hi)

    def OD_at(self, x: float) -> Optional[float]:
        """INNER pipe profile only, guarded on the inner span.

        Overridden because `extent` now includes the cantilever: the
        inherited version guards on `owns()`, which would hand back plain
        OD_pipe out along the outer member where this component has no
        inner-pipe section at all.
        """
        lo, hi = self.x_inner_extent
        if not (lo - 1e-12 <= x <= hi + 1e-12):
            return None
        return super().OD_at(x)

    def contact_at(self, x: float) -> Optional[Contact]:
        """Lowest surface at x -- the OUTER pipe wherever it exists.

        The outer pipe is concentric and its bore clears the thick body, so
        wherever the two overlap axially the outer surface is strictly the
        lower one. `Contact` is defined as the lowest surface at a station,
        so the outer pipe wins there; the inner pipe answers everywhere
        else inside the weld-to-weld span.

        The reaction lands on the outer member itself, and the geometry
        line naming that member as its `structural_line_id` is what routes
        it. PIPE_ELEMENT is therefore correct in the sense its docstring
        means -- the contacting surface IS that pipe's own outer surface,
        already on the element carrying it -- with the arm collinear
        because the section is concentric. What is NOT captured is that the
        member reaches the pipeline through a JUNCTION rather than by being
        the pipeline: see the LoadPath note in EDES.
        """
        if self._on_outer(x):
            y = self.y_outer_contact
            return Contact(y=y, owner=self.code,
                            load_path=LoadPath.PIPE_ELEMENT, arm=abs(y))
        return super().contact_at(x)

    # --- node / line accessors --------------------------------------------
    @property
    def _station_xs(self) -> list:
        """Inherited stations MINUS the mid-body connector station.

        TaperedThickBody gained a `conMid` station on 1 Sep 2026 -- a
        mid-body attachment point for a fixed structural connector. GD-PIP
        inherits that list, so it arrived here as a side effect of a change
        made for GD-TP/GD-TT, taking this component from 8 nodes to 9
        without being separately assessed. It is dropped again here: a PiP
        bulkhead already has its attachment point, the outer member's free
        end (`outEnd`), which is where a Boss attaches. A second, competing
        attachment mid-body is not part of this component's definition and
        was never asked for.

        Filtered by id rather than by position so that reordering or adding
        stations upstream cannot silently re-admit it or drop the wrong one.
        """
        return [(nid, x) for nid, x in super()._station_xs
                if not nid.endswith(':conMid')]

    @property
    def _tag(self) -> str:
        """Same convention the inherited `_station_xs` builds inline."""
        return f'{self.code}@{self.centre_x:+.4f}'

    def _outer_node_ids(self, side: str) -> tuple:
        t = self._tag
        return (f'{t}:out{side}Jn', f'{t}:out{side}End')

    def geometry_nodes(self) -> list:
        """Inner-pipe stations (inherited) plus the outer pipe's own two.

        Outer nodes sit on the CONTACT SURFACE at +OD_outer/2 -- below the
        inner pipe's surface, which is the whole reason they own contact
        there. Both MANDATORY: the junction is a member root and a section
        discontinuity in the contact profile, and the end node is where a
        Boss attaches.
        """
        out = super().geometry_nodes()
        y = self.y_outer_contact
        for side, xj, xe in self._outer_spans:
            nj, ne = self._outer_node_ids(side)
            out.append(GeometryNode(nj, xj, y, NodePriority.MANDATORY))
            out.append(GeometryNode(ne, xe, y, NodePriority.MANDATORY))
        return out

    def structural_nodes(self) -> list:
        """Inner stations plus the outer member's root and tip, both at y=0.

        CONCENTRIC, so the outer pipe's neutral axis coincides with the
        pipeline's. The root is the junction; the tip is the free end of
        the cantilever and the Boss attachment point.
        """
        out = super().structural_nodes()
        for side, xj, xe in self._outer_spans:
            nj, ne = self._outer_node_ids(side)
            out.append(StructuralNode(nj, xj, 0.0, NodePriority.MANDATORY))
            out.append(StructuralNode(ne, xe, 0.0, NodePriority.MANDATORY))
        return out

    def geometry_lines(self) -> list:
        """Five inner segments (inherited) plus one outer member per side.

        The outer member OWNS CONTACT over its span: its bottom OD is the
        lowest surface there. Concentric, so the normal passes through its
        own neutral axis and the moment is zero -- same advice as the inner
        run, for the same reason.
        """
        out = super().geometry_lines()
        adv = ContactAdvice(
            normal_is_collinear_with_offset=True, requires_node_at_contact=False,
            note='Concentric outer pipe: normal is radial through its own '
                  'neutral axis, so the moment about that axis is zero. The '
                  'member is offset from nothing -- it shares the pipeline '
                  'centreline.')
        t = self._tag
        for side, _, _ in self._outer_spans:
            nj, ne = self._outer_node_ids(side)
            out.append(GeometryLine(line_id=f'{t}:outer{side}',
                                     node_ids=(nj, ne),
                                     structural_line_id=f'{t}:outer{side}',
                                     owns_contact=True, contact_advice=adv))
        return out

    def structural_lines(self) -> list:
        """Five inner segments (inherited) plus one cantilever per side.

        Each outer member carries a real Section, so its stiffness is a
        section property and mesh-independent. It is its OWN line, not the
        pipeline line: a second member meeting the pipe at a node, which is
        precisely what makes the root a junction.
        """
        out = super().structural_lines()
        t = self._tag
        sec = Section(OD=self.OD_outer, t=self.t_outer, owner=self.code)
        adv = MeshAdvice(
            min_elements=2, max_size_ratio=2.0, target_elem_len=None,
            note='Cantilever off the junction, free at the end node. At least '
                  'two elements so the tip rotation is not carried by a single '
                  'element. NO WELD at the root -- integral with the inner '
                  'pipe (Sec.5.2) -- so no weld-driven refinement is needed '
                  'there, unlike the girth welds at x_weld. A Boss, when '
                  'added, welds at the END node and may impose its own.')
        for side, _, _ in self._outer_spans:
            nj, ne = self._outer_node_ids(side)
            out.append(StructuralLine(line_id=f'{t}:outer{side}',
                                       node_ids=(nj, ne),
                                       section=sec, mesh_advice=adv))
        return out

    @property
    def outer_load_path(self) -> str:
        """How an EXTERNAL load applied to the outer pipe reaches the line.

        Stated because neither `LoadPath` value describes it. PIPE_ELEMENT
        means the reaction is already on the element carrying it -- true of
        the outer pipe with respect to ITSELF, which is why `contact_at`
        uses it -- but it says nothing about the member reaching the
        pipeline through a JUNCTION rather than BEING the pipeline.
        CONNECTOR is wrong too: there is no connector, the joint is
        integral.

        THE RULE. An external load anywhere on the outer pipe transfers to
        that member's OWN END NODES -- the junction node at the root and
        the free end node -- distributed structurally, i.e. by the member's
        stiffness, which for a beam element is what its shape functions
        already do. At the junction node the load then partitions between
        the outer member and the pipeline structural line in the ratio of
        their stiffnesses, per the shared distribution factor. The free end
        carries no restraint of its own until a Boss is attached there.

        So the path is two hops, not one: load -> outer pipe end nodes ->
        (at the junction) pipeline. Anything reading `contact_at`'s
        PIPE_ELEMENT as "already on the pipeline" skips the first hop and
        puts a roller reaction straight onto the line, missing the
        cantilever moment the offset generates.
        """
        return ('external load -> outer pipe end nodes (structural '
                'distribution) -> junction -> pipeline structural line')

    def junctions(self) -> list:
        """Each outer member's ROOT joins the pipeline structural line.

        Declared, not inferred. The root x is an arbitrary caller-supplied
        position (x_interior_R/L), so it is NOT one of the six inherited
        mandatory stations and there is no coordinate coincidence for a
        mesher to notice -- exactly the case this accessor's docstring
        warns about, where the obligation to join would otherwise exist
        only in prose and the cantilever would be left floating while the
        model still assembled and still converged.

        The joint is INTEGRAL, not welded (Sec.5.2). That matters for
        fatigue and for weld-driven meshing, not for the merge itself: the
        node identity is the same either way.

        ID CONVENTION -- CONFIRM AGAINST THE MESHER. Returned UNPREFIXED,
        matching the inherited `structural_nodes`, which stores raw ids and
        leaves `_s_id` to the mesher. GD-VLV's `junctions` returns a
        PREFIXED id (`:smid`) because its `structural_nodes` still does the
        old per-name `.replace(':', ':s')` that `_s_id` was introduced on
        23 Aug 2026 to retire. One of the two is wrong; GD-VLV looks like
        the unmigrated one, so this follows GD-TT.
        """
        return [(self._outer_node_ids(side)[0], PIPELINE_STRUCTURAL_LINE_ID)
                for side, _, _ in self._outer_spans]


# ===========================================================================
# Valve [GD-VLV] -- IW-A
#
# FIRST BRANCHED COMPONENT. Every component above has a single along-pipe
# run, so its structural line is a CHAIN. GD-VLV adds a STEM rising from
# the body midpoint, making its structural line a TEE: the ':smid' node
# carries THREE members (two run segments plus the stem). Anything that
# walks the structural graph assuming a sequence will break here.
# ===========================================================================

@dataclass(frozen=True)
class Valve(Component):
    """GD-VLV. Inline valve: thick body, one constant-section transition
    each side, and a stem rising from the body midpoint.

    Defaults are pipe-relative (see default_for): body L=2.5D, OD=2D,
    WT=3.5t; transition L=1.2D, WT=2t with ID = the pipeline's, so its OD
    is DERIVED; stem L=2.5D upward, OD=1D, WT=2t.

    NO TAPERS anywhere: constant ID and constant WT give a constant OD per
    zone, so the profile steps abruptly pipe -> transition -> body. If DNV
    taper rules should apply at the welds (as they do for GD-TT), that is
    NOT represented here.

    Body bore is a CONSEQUENCE, not an input: OD and WT are both given, so
    ID_body = OD_body - 2*t_body works out ~1.8x the pipeline bore. That is
    physically reasonable for a valve cavity but is derived, not stated.
    """
    L_body: float = 1.0160            # m, FREE -- 2.5 D
    OD_body: float = 0.8128            # m, FREE -- 2 D
    t_body: float = 0.0735              # m, FREE -- 3.5 t
    L_trans: float = 0.48768             # m, FREE -- 1.2 D
    t_trans: float = 0.042                # m, FREE -- 2 t
    L_stem: float = 1.0160                 # m, FREE -- 2.5 D, UPWARD
    OD_stem: float = 0.4064                 # m, FREE -- 1 D
    t_stem: float = 0.042                    # m, FREE -- 2 t
    m_extra: Optional[float] = None           # kg, FREE -- see point_masses()

    code: str = field(init=False, default='GD-VLV')
    # IW-P, not IW-A: Table II of the paper puts a valve under 'Piping
    # Components (Valve, Flange, TEE etc)'. IW-A is 'Anchoring Components'
    # -- hardware that PROVIDES a connection point for EA-SB/ST. Corrected
    # 23 Aug 2026; was coded IW-A.
    iw_ea_class: tuple = field(init=False, default=('IW-P',))

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """The SINGLE place these ratios are computed."""
        D, t = pipe.OD_pipe, pipe.t_pipe
        return {'L_body': 2.5 * D, 'OD_body': 2.0 * D, 't_body': 3.5 * t,
                'L_trans': 1.2 * D, 't_trans': 2.0 * t,
                'L_stem': 2.5 * D, 'OD_stem': 1.0 * D, 't_stem': 2.0 * t}

    def validate(self) -> None:
        if min(self.L_body, self.L_trans, self.L_stem) <= 0:
            raise GeometryRuleError(f'{self.code}: lengths must be positive')
        if self.OD_trans <= self.pipe.OD_pipe:
            raise GeometryRuleError(
                f'{self.code}: transition OD ({self.OD_trans:.4f} m) must exceed '
                f'pipe OD ({self.pipe.OD_pipe:.4f} m) -- OD only grows')
        if self.OD_body <= self.OD_trans:
            raise GeometryRuleError(
                f'{self.code}: body OD must exceed transition OD')
        if self.t_body >= self.OD_body / 2:
            raise GeometryRuleError(f'{self.code}: t_body leaves no bore')
        if self.m_extra is not None and self.m_extra < 0:
            raise GeometryRuleError(f'{self.code}: m_extra must not be negative')

    # --- derived -----------------------------------------------------------
    @property
    def OD_trans(self) -> float:
        """DERIVED, not free: the transition's ID is the pipeline's, so its
        OD follows from the wall thickness."""
        return self.pipe.ID + 2 * self.t_trans

    @property
    def ID_body(self) -> float:
        return self.OD_body - 2 * self.t_body

    @property
    def L_total(self) -> float:
        return self.L_body + 2 * self.L_trans

    @property
    def x_body(self) -> tuple[float, float]:
        return (self.centre_x - self.L_body / 2, self.centre_x + self.L_body / 2)

    @property
    def x_weld(self) -> tuple[float, float]:
        bL, bR = self.x_body
        return (bL - self.L_trans, bR + self.L_trans)

    @property
    def extent(self) -> tuple[float, float]:
        return self.x_weld

    @property
    def y_stem_tip(self) -> float:
        """Stem rises, so NEGATIVE y under the positive-down convention."""
        return -self.L_stem

    def owns(self, x: float) -> bool:
        lo, hi = self.extent
        return lo <= x <= hi

    def OD_at(self, x: float) -> Optional[float]:
        if not self.owns(x):
            return None
        bL, bR = self.x_body
        return self.OD_body if bL <= x <= bR else self.OD_trans

    def _wt_at(self, x: float) -> Optional[float]:
        if not self.owns(x):
            return None
        bL, bR = self.x_body
        return self.t_body if bL <= x <= bR else self.t_trans

    # --- nodes / lines -----------------------------------------------------
    @property
    def _tag(self) -> str:
        return f'{self.code}@{self.centre_x:+.4f}'

    @property
    def _run_stations(self) -> list:
        wL, wR = self.x_weld
        bL, bR = self.x_body
        t = self._tag
        return [(f'{t}:weldL', wL), (f'{t}:bodyL', bL),
                (f'{t}:mid', self.centre_x),
                (f'{t}:bodyR', bR), (f'{t}:weldR', wR)]

    @property
    def can_pass_rollers(self) -> bool:
        """FALSE. The valve body has NO taper, so the step from transition
        to body is a square shoulder facing the direction of travel.

        THIS IS A SNAGGING GEOMETRY. A square shoulder standing
        {proud} proud of the transition cannot ride up onto a roller -- it
        catches on it. GD-TT exists precisely to avoid this on a thick-wall
        component, and a valve has no equivalent: the body is a forging
        with flanged or welded ends, not a machined transition.

        CONSEQUENCE FOR INSTALLATION. A GD-VLV cannot be passed over a
        stinger roller box in the ordinary way. Whatever an analysis says
        about strain at the body, the passage itself is not a passage. Any
        S-lay study that sweeps a GD-VLV along a roster of rollers is
        modelling something that does not happen, and the number it returns
        is not wrong so much as answering a question that was never asked.

        `contact_at` still reports the lowest surface, because that is what
        the accessor means and a static bearing case is real. This flag is
        the separate statement, and it is the one a passage study must
        read.
        """
        return False

    @property
    def shoulder_proud(self) -> float:
        """Radial height of the square shoulder, per side -- what a roller
        would have to climb. (OD_body - OD_trans)/2."""
        return (self.OD_body - self.OD_trans) / 2.0

    @property
    def _profile_stations(self) -> list:
        """Geometry stations for the OUTER PROFILE, which is NOT the same
        list as `_run_stations`.

        A square step is multivalued in y at one x, and a single node
        cannot hold two y values. Before 30 Aug 2026 the step boundary had
        ONE node placed at the BODY surface, so the geometry line from the
        weld ramped diagonally across the whole transition while
        `section_at` and `contact_at` were flat -- a drawn taper on a
        component whose own docstring says it has none, wrong by 0.164 m
        (73% of the surface offset) at the worst station.

        The fix is a COINCIDENT PAIR at each step, joined by a vertical
        riser line. The riser is the shoulder itself, which is the feature
        `can_pass_rollers` is about, so it is now something the geometry
        can actually show.
        """
        wL, wR = self.x_weld
        bL, bR = self.x_body
        t = self._tag
        rt, rb = self.OD_trans / 2.0, self.OD_body / 2.0
        return [(f'{t}:weldL', wL, rt), (f'{t}:bodyL', bL, rt),
                (f'{t}:bodyLs', bL, rb), (f'{t}:mid', self.centre_x, rb),
                (f'{t}:bodyRs', bR, rb), (f'{t}:bodyR', bR, rt),
                (f'{t}:weldR', wR, rt)]

    def geometry_nodes(self) -> list:
        """Profile nodes on the CONTACT SURFACE, including a COINCIDENT
        PAIR at each square shoulder; the stem tip sits ABOVE at negative y.

        All profile nodes are MANDATORY -- each is a section step or the
        edge of one. The stem tip is PREFERRED: it owns no contact and
        forces nothing on the pipeline mesh.
        """
        out = [GeometryNode(nid, x, y, NodePriority.MANDATORY)
               for nid, x, y in self._profile_stations]
        out.append(GeometryNode(f'{self._tag}:stemTip', self.centre_x,
                                 self.y_stem_tip, NodePriority.PREFERRED))
        return out

    def structural_nodes(self) -> list:
        """Run nodes on the pipe centreline (y=0), plus the stem tip.

        ':smid' is the TEE JUNCTION -- three members meet there.

        ID RULE CONVERGED 30 Aug 2026: was the retired per-name
        `.replace(':', ':s')`; now `_s_id()`, matching GD-TP/TT/PIP. VERIFIED
        NO-OP on every current name here (none contain an internal colon,
        so partition-on-first-colon and replace-all-colons agree) -- this is
        purely removing a second, needlessly different mechanism for a job
        one function already does everywhere else, not a behaviour change.

        NODE COUNT DELIBERATELY DIFFERS FROM `geometry_nodes()` (6 here vs 8
        there) -- NOT the same defect class. `geometry_nodes()` carries a
        coincident pair at each square shoulder (bodyL/bodyLs, bodyR/bodyRs)
        because the CONTACT SURFACE needs two y-values at one x to draw a
        step (VLV-D1). The STRUCTURAL centreline never bifurcates -- y=0 on
        both sides of a section change -- so ONE node per step is sufficient
        for a beam element to switch from the transition Section to the
        body Section there. Forcing 1:1 node-count parity between the two
        lists would be wrong, not a fix; verified structural_lines() has no
        dangling references against this shorter list.
        """
        out = [StructuralNode(_s_id(nid), x, 0.0, NodePriority.MANDATORY)
               for nid, x in self._run_stations]
        out.append(StructuralNode(_s_id(f'{self._tag}:stemTip'),
                                   self.centre_x, self.y_stem_tip,
                                   NodePriority.PREFERRED))
        return out

    def geometry_lines(self) -> list:
        """Four run segments (owns_contact=True) plus the stem
        (owns_contact=False).

        FIRST MIXED CASE: GD-ST is shape-only ENTIRELY, GD-TP/TT own
        contact entirely. GD-VLV is both -- the run is contacted, the stem
        rises AWAY from the rollers and never can be."""
        t = self._tag
        run_adv = ContactAdvice(
            normal_is_collinear_with_offset=True, requires_node_at_contact=False,
            note='Concentric run section: normal is radial and passes through '
                  'the neutral axis, so the moment is zero.')
        stem_adv = ContactAdvice(
            normal_is_collinear_with_offset=True, requires_node_at_contact=False,
            note='SHAPE ONLY -- the stem rises AWAY from the rollers and can '
                  'never be contacted; owns_contact is the field that matters.')
        riser_adv = ContactAdvice(
            normal_is_collinear_with_offset=False, requires_node_at_contact=False,
            note='SQUARE SHOULDER. This face is VERTICAL, so its normal is '
                  'AXIAL, not radial -- the one geometry line in this '
                  'component whose normal does not pass through the neutral '
                  'axis. It is the face a roller would catch on; see '
                  'can_pass_rollers.')
        st = self._profile_stations
        out = []
        for i in range(6):
            is_riser = abs(st[i + 1][1] - st[i][1]) < 1e-12
            out.append(GeometryLine(
                line_id=PIPELINE_GEOMETRY_LINE_ID,
                node_ids=(st[i][0], st[i + 1][0]),
                structural_line_id=PIPELINE_STRUCTURAL_LINE_ID,
                owns_contact=True,
                contact_advice=riser_adv if is_riser else run_adv))
        out.append(GeometryLine(line_id=f'{t}:stem',
                                 node_ids=(f'{t}:mid', f'{t}:stemTip'),
                                 structural_line_id=f'{t}:stem',
                                 owns_contact=False, contact_advice=stem_adv))
        return out

    def junctions(self) -> list:
        """The STEM ROOT joins the run. Note GD-VLV already returned
        'pipeline' among its `structural_lines()` -- because its run IS
        the pipe over its extent -- but that is a statement about which
        line its ELEMENTS belong to, not about a node shared between two
        lines. `smid` is both: the run's centre station AND the stem's
        base. Only the second fact is a junction, and only this accessor
        states it.

        NodePriority's docstring notes GD-VLV satisfied the junction rule
        BY ACCIDENT -- `smid` is already MANDATORY for section reasons --
        which is exactly why the junction has to be declared rather than
        inferred from priority."""
        return [(f'{self._tag}:smid', 'pipeline')]

    def structural_lines(self) -> list:
        """Four run members SHARED with the pipeline, plus the stem branch.

        All carry a real Section (not a stiffness_rule): the valve is
        genuine pipe-like structure, so its stiffness is a section property
        and mesh-independent -- unlike GD-ST's kT."""
        t = self._tag
        st = self._run_stations
        adv = MeshAdvice(min_elements=1, max_size_ratio=2.0,
                          note='Constant section within each zone; grade into '
                               'the adjacent abrupt step.')
        trans = Section(OD=self.OD_trans, t=self.t_trans, owner=self.code)
        body = Section(OD=self.OD_body, t=self.t_body, owner=self.code)
        secs = [trans, body, body, trans]
        out = [StructuralLine(line_id=PIPELINE_STRUCTURAL_LINE_ID,
                               node_ids=(st[i][0].replace(':', ':s'),
                                          st[i + 1][0].replace(':', ':s')),
                               section=secs[i], mesh_advice=adv)
               for i in range(4)]
        out.append(StructuralLine(
            line_id=f'{t}:stem',
            node_ids=(f'{t}:smid', f'{t}:sstemTip'),
            section=Section(OD=self.OD_stem, t=self.t_stem, owner=self.code),
            mesh_advice=MeshAdvice(min_elements=1, max_size_ratio=2.0,
                                    note='Stem branch off the TEE at :smid.')))
        return out

    # --- profile queries ---------------------------------------------------
    def section_at(self, x: float) -> Optional[Section]:
        OD = self.OD_at(x)
        if OD is None:
            return None
        return Section(OD=OD, t=self._wt_at(x), owner=self.code)

    def contact_at(self, x: float) -> Optional[Contact]:
        OD = self.OD_at(x)
        if OD is None:
            return None
        y = OD / 2                       # positive-down: below the C/L
        return Contact(y=y, owner=self.code,
                        load_path=LoadPath.PIPE_ELEMENT, arm=abs(y))

    def point_masses(self) -> list:
        """Concentrated mass at the valve's COG, DEFAULTED TO MID OF BODY.

        Returns [] when `m_extra` is None, which is the default: a mass
        this module invented would be worse than none, since a valve's
        weight comes from the vendor, not from a diameter.

        WHAT IT MUST NOT INCLUDE. The four run members already carry REAL
        Sections -- transition, body, body, transition -- and the stem
        carries one too, so the steel in those walls is ALREADY in any
        assembled model as distributed element mass. `m_extra` is the mass
        that is NOT in those walls: actuator, gearbox, bonnet, trim, seats,
        stem packing. Passing the valve's full dry weight here counts the
        body twice.

        COG AT `:smid`. That node is the mid of the body and is already
        MANDATORY (it is the run's centre station and the stem's junction),
        so the mass never forces a node that would not exist anyway. A COG
        elsewhere -- and a real valve's is usually offset toward the
        actuator, ABOVE the pipe axis -- has no node to attach to and is
        not representable here. That is a genuine limitation, not an
        omission: `point_masses` returns (node_id, mass) with no
        coordinates, so an offset COG needs a node before it needs a mass.
        """
        if self.m_extra is None:
            return []
        return [(f'{self._tag}:smid', float(self.m_extra))]



# ===========================================================================
# Section 7 -- Branch piping [GD-B], L / Z variants
#   Merged from gdb_dataclass_proposal.py, 23 Aug 2026.
# ===========================================================================

# Tolerance for 'these two components merely TOUCH rather than overlap'.
# Set to the precision a layout is realistically WRITTEN in (6 decimal
# places = 1 micron), NOT the precision floats are computed in. Was 1e-9
# until 5 Sep 2026, which was tighter than any emitted layout can hold: a
# definition rounded to 6 dp leaves ~5e-7 residuals at every join, so a
# correctly-tiled header chain read as a genuine section overlap and was
# rejected. ils_builder.ADJACENCY_TOL is the same value for the same
# reason -- the two must agree, or a layout can satisfy one and fail the
# other.
ABUTMENT_TOL = 1e-6

# --- nominal pipe size table ------------------------------------------------
# NPS -> outside diameter in metres, ASME B36.10M. Needed because a component
# sized "n inches larger than the line" means n larger in NOMINAL SIZE, not
# OD + n inches: below NPS 14 the nominal size is not the OD at all (NPS 6 is
# 168.3 mm, not 152.4), so the two readings diverge for most line sizes. They
# coincide only at and above NPS 14, where OD does equal the nominal.
NPS_OD = {
    2: 0.0603,  3: 0.0889,  4: 0.1143,  6: 0.1683,  8: 0.2191,
    10: 0.2731, 12: 0.3239, 14: 0.3556, 16: 0.4064, 18: 0.4572,
    20: 0.5080, 24: 0.6096, 28: 0.7112, 30: 0.7620, 32: 0.8128,
    36: 0.9144, 40: 1.0160, 42: 1.0668, 48: 1.2192,
}


def nps_of(od: float, tol: float = 1e-4):
    """NPS whose OD matches `od`, or None if it is not a standard size."""
    for nps, d in NPS_OD.items():
        if abs(d - od) <= tol:
            return nps
    return None


def nps_step_up(od: float, steps: int = 4) -> float:
    """OD of the pipe `steps` NOMINAL SIZES larger than the one with OD `od`.

    Raises if `od` is not a standard size, or if stepping up runs off the
    table -- guessing either would produce a plausible wrong diameter, and a
    sleeve diameter that is quietly wrong is not something a later check
    would catch.
    """
    n = nps_of(od)
    if n is None:
        raise GeometryRuleError(
            f'OD {od*1000:.1f} mm is not a standard NPS size, so "{steps} in '
            'larger" has no defined meaning. Supply the sleeve OD explicitly.')
    sizes = sorted(NPS_OD)
    i = sizes.index(n)
    target = n + steps
    if target not in NPS_OD:
        raise GeometryRuleError(
            f'NPS {n} + {steps} = NPS {target} is not in the size table. '
            'Supply the sleeve OD explicitly.')
    return NPS_OD[target]


VALID_BRANCH_VARIANTS = {'L', 'Z'}

# --- connector types --------------------------------------------------------
# W (girth weld) added 1 Sep 2026. Note this map is NOT injective: F and W
# both realise OAM's FixedConnection, because OAM classifies by kinematic
# behaviour (all DOF restrained) while these types distinguish the JOINT.
# They cannot be merged: DNV prohibits welding a structural attachment onto
# line pipe (an F), while requiring the girth welds (W) that make a pipeline
# at all, so the two carry opposite permissions on the same component.
#
# NAME COLLISION, DELIBERATELY AVOIDED. There is a separate constant further
# down this module, VALID_CONNECTOR_TYPES = {None, 'F', 'P', 'S', 'D'}, used
# by ConnectionSystem to validate the named EA layouts (F1/F2/PS/PSD). It is
# a DIFFERENT set for a different job: it admits None (an unpopulated slot in
# a five-slot layout) and excludes W (a girth weld is not part of an EA
# connector layout). Defining a second constant of that name here shadowed
# nothing and was silently shadowed BY it -- Connector.validate then rejected
# 'W' as invalid. The types a Connector artifact may take are therefore read
# off CONNECTOR_OAM_CLASS directly rather than from a second named set.
CONNECTOR_OAM_CLASS = {
    'F': 'FixedConnection',
    'W': 'FixedConnection',
    'P': 'MovableConnection',        # revolute pair
    'S': 'MovableConnection',        # prismatic pair
    'D': 'IntermittentConnection',
}



@dataclass(frozen=True)
class BranchPiping(Component):
    """GD-B. Branch piping teed off the header, ending at a connector that
    is supported by the Top Structure.

    Like GD-VLV's stem this is a BRANCH -- the Tee node is a TEE junction
    on the header's structural line. Unlike the stem it is multi-segment
    and terminates at a connector rather than free.

    Its geometry line OWNS NO CONTACT: the branch rises away from the
    rollers and can never be touched by one.
    """
    variant: str = 'L'                  # 'L' or 'Z'
    P_b1: float = 4.064                  # m, FREE -- horizontal run, 10 D
    P_b2: float = 0.8128                  # m, FREE -- TOTAL vertical rise
    P_bc: float = 1.016                    # m, FREE -- Tee -> nearest EA-ST
                                            # connection point, 2.5 D
    P_b3: Optional[float] = None            # m, FREE, Z ONLY -- elevation of
                                             # the horizontal run. NOT GIVEN
                                             # IN THE PAPER; defaults to
                                             # P_b2/2. See note below.
    P_bv: Optional[float] = None            # m, FREE -- valve position,
                                             # measured ALONG THE HORIZONTAL
                                             # RUN from the elbow at its
                                             # start. Defaults to P_b1/2
                                             # (mid-run). NOT GIVEN IN THE
                                             # PAPER either; same treatment
                                             # as P_b3 -- an Optional that
                                             # __post_init__ fills, so the
                                             # default is visible as a
                                             # derivation rather than baked
                                             # in as a literal.
    OD_branch: float = 0.2731               # m, FREE -- Table XII
    t_branch: float = 0.0159                 # m, FREE -- Table XII
    mass_valve: float = 3000.0                # kg, FREE -- 3 mT (figures)
    mass_connector: float = 3000.0             # kg, FREE -- 3 mT (figures)
    support_connector: str = 'F'                # FREE -- connector type tying
                                                 # the branch END to the EA-ST
                                                 # structural node. 'F' fixed
                                                 # (default) or 'S' slotted;
                                                 # the paper's -FT- / -ST-
                                                 # support taxonomy.

    code: str = field(init=False, default='GD-B')
    iw_ea_class: tuple = field(init=False, default=('IW-B',))

    @classmethod
    def default_for(cls, pipe: BasePipeline, variant: str = 'L') -> dict:
        """Pipe-relative defaults. P_b2 differs by variant: the paper uses
        2 D for the L-branch and 3.5 D for the Z-branch."""
        D = pipe.OD_pipe
        return {'P_b1': 10.0 * D,
                'P_b2': (2.0 if variant == 'L' else 3.5) * D,
                'P_bc': (2.5 if variant == 'L' else 1.25) * D}

    def __post_init__(self):
        if self.P_b3 is None and self.variant == 'Z':
            # NOT SPECIFIED IN THE PAPER. Fig 24 shows the Z's horizontal
            # run at an intermediate height but gives no parameter for it;
            # P_b2 is dimensioned to the CONNECTOR, not to the run. Half
            # the total rise is a placeholder, flagged rather than hidden.
            object.__setattr__(self, 'P_b3', self.P_b2 / 2.0)
        if self.P_bv is None:
            # Mid-run. Must be resolved BEFORE super().__post_init__() runs
            # validate(), which now checks it against P_b1.
            object.__setattr__(self, 'P_bv', self.P_b1 / 2.0)
        super().__post_init__()

    def validate(self) -> None:
        if self.variant not in VALID_BRANCH_VARIANTS:
            raise GeometryRuleError(
                f'{self.code}: variant must be one of '
                f'{sorted(VALID_BRANCH_VARIANTS)}, got {self.variant!r}')
        if min(self.P_b1, self.P_b2) <= 0:
            raise GeometryRuleError(f'{self.code}: P_b1 and P_b2 must be > 0')
        if self.variant == 'Z' and not (0 < self.P_b3 < self.P_b2):
            raise GeometryRuleError(
                f'{self.code}-Z: P_b3 ({self.P_b3:.4f}) must lie strictly '
                f'between 0 and P_b2 ({self.P_b2:.4f}) -- the horizontal run '
                f'sits between the header and the connector')
        if not (0 < self.P_bv < self.P_b1):
            raise GeometryRuleError(
                f'{self.code}: P_bv ({self.P_bv:.4f}) must lie strictly '
                f'between 0 and P_b1 ({self.P_b1:.4f}) -- the valve sits '
                f'ON the horizontal run. STRICT at both ends deliberately: '
                f'at 0 or P_b1 the valve node would land on top of an elbow '
                f'node, giving `path` two entries at one coordinate and a '
                f'zero-length element. Put the mass on the elbow by editing '
                f'point_masses, not by driving P_bv onto it.')
        if self.support_connector not in ('F', 'S'):
            raise GeometryRuleError(
                f'{self.code}: support_connector must be F or S, got '
                f'{self.support_connector!r}')
        if self.OD_branch >= self.pipe.OD_pipe:
            raise GeometryRuleError(
                f'{self.code}: branch OD ({self.OD_branch:.4f}) should be '
                f'smaller than the header OD ({self.pipe.OD_pipe:.4f})')

    # --- derived -----------------------------------------------------------
    @property
    def code_full(self) -> str:
        return f'{self.code}{self.variant}'          # GD-BL / GD-BZ

    @property
    def _tag(self) -> str:
        return f'{self.code_full}@{self.centre_x:+.4f}'

    @property
    def path(self) -> list:
        """(node_suffix, x, y) polyline from the Tee to the connector.

        y NEGATIVE = rising above the header (positive-down convention).
        L: tee -> riser -> VALVE -> horizontal end
        Z: tee -> riser -> VALVE -> horizontal -> second riser -> end

        THE VALVE IS A REAL NODE ON THIS POLYLINE, not a station reported
        alongside it. It carries no section or slope change -- the run is
        continuous pipe straight through it -- so it exists for one reason:
        an inertia element attaches to a NODE, and P_bv is meaningless
        unless one is there. Splitting the run here also means every
        consumer of `path` (geometry_lines, structural_lines, the plotter)
        gets the split for free rather than each reconstructing it.
        """
        x0 = self.centre_x
        xv = x0 + self.P_bv
        if self.variant == 'L':
            return [('tee', x0, 0.0),
                    ('elbow', x0, -self.P_b2),
                    ('valve', xv, -self.P_b2),
                    ('end', x0 + self.P_b1, -self.P_b2)]
        return [('tee', x0, 0.0),
                ('elbow1', x0, -self.P_b3),
                ('valve', xv, -self.P_b3),
                ('elbow2', x0 + self.P_b1, -self.P_b3),
                ('end', x0 + self.P_b1, -self.P_b2)]

    @property
    def extent(self) -> tuple:
        """Axial footprint on the HEADER. The branch teed off at centre_x
        and runs to +P_b1, so it shadows that span."""
        return (self.centre_x, self.centre_x + self.P_b1)

    @property
    def connector_axis(self) -> str:
        """HORIZONTAL for L (sliding guide), VERTICAL for Z (rigid to the
        EA-ST top plate) -- Table II / Fig 15."""
        return 'horizontal' if self.variant == 'L' else 'vertical'

    def owns(self, x: float) -> bool:
        return False        # teed off the header; owns no span of it

    # --- nodes / lines -----------------------------------------------------
    def _priority(self, name: str) -> NodePriority:
        """The TEE is MANDATORY; everything else on the branch is PREFERRED.

        CORRECTED 23 Aug 2026 -- the first draft made every branch node
        PREFERRED, reasoning that the branch adds no section change to the
        header so it forces no header mesh node. That is correct about the
        SECTION and wrong about CONNECTIVITY. The Tee is where the branch's
        structural line JOINS the header's, and a beam line cannot attach to
        the interior of an element: unlike contact, which is placed at a
        virtual parametric point and distributed to the bracketing nodes by
        shape functions, a shared structural node either exists or the two
        lines are simply not connected. If the mesher declines to snap here,
        the branch is left floating -- and the model would still assemble and
        still converge, which is the failure mode worth spending a
        MANDATORY on. See NodePriority's third reason.

        THE VALVE IS ALSO MANDATORY (added with P_bv). This is a FOURTH
        reason, not yet written into NodePriority's own docstring, and it
        is worth stating because the obvious answer is PREFERRED: a lumped
        mass CAN be distributed to the two bracketing nodes by shape
        functions, exactly as contact is, and that argument is what makes
        contact never drive a node anywhere else in this module.

        It fails here on this component's OWN mesh_advice, which sets
        min_elements=1. One element across the horizontal run means the
        bracketing nodes ARE the elbow and the end -- so a PREFERRED valve
        node lets the mesher put the 3 mT straight back onto the elbows,
        which is exactly the placement P_bv was added to stop. P_bv would
        still read P_b1/2 in the table, still validate, and change nothing:
        a parameter that is displayed and silently ignored. MANDATORY is
        what makes it mean anything.
        """
        return (NodePriority.MANDATORY if name in ('tee', 'valve')
                else NodePriority.PREFERRED)

    def geometry_nodes(self) -> list:
        """Tee MANDATORY (topological junction on the header), the rest
        PREFERRED -- the branch introduces no section change on the header,
        so nothing else here forces a header mesh node."""
        t = self._tag
        return [GeometryNode(f'{t}:{n}', x, y, self._priority(n))
                for n, x, y in self.path]

    def structural_nodes(self) -> list:
        """SHARES COORDINATES with geometry_nodes -- the branch pipe's
        centreline IS its structural line, and its surface offset is
        carried by the Section rather than by a separate line. Priority is
        mirrored, so the Tee is MANDATORY on this list too: it is the
        STRUCTURAL list where the junction actually has to exist."""
        t = self._tag
        return [StructuralNode(f'{t}:s{n}', x, y, self._priority(n))
                for n, x, y in self.path]

    def geometry_lines(self) -> list:
        """owns_contact=False on EVERY segment: the branch rises AWAY from
        the rollers and can never be contacted."""
        t = self._tag
        adv = ContactAdvice(
            normal_is_collinear_with_offset=True,
            requires_node_at_contact=False,
            note='SHAPE ONLY -- branch piping rises away from the rollers '
                  'and is never contacted. owns_contact is the field that '
                  'matters here.')
        p = self.path
        return [GeometryLine(line_id=f'{t}:branch',
                              node_ids=(f'{t}:{p[i][0]}', f'{t}:{p[i+1][0]}'),
                              structural_line_id=f'{t}:branch',
                              owns_contact=False, contact_advice=adv)
                for i in range(len(p) - 1)]

    def structural_lines(self) -> list:
        """Real Section throughout -- the branch is genuine pipe, so its
        stiffness is a section property and mesh-independent (contrast
        GD-ST's stiffness_ratio)."""
        t = self._tag
        sec = Section(OD=self.OD_branch, t=self.t_branch, owner=self.code_full)
        adv = MeshAdvice(min_elements=1, max_size_ratio=2.0,
                          note='Branch pipe run; grade into the Tee junction.')
        p = self.path
        return [StructuralLine(line_id=f'{t}:branch',
                                node_ids=(f'{t}:s{p[i][0]}', f'{t}:s{p[i+1][0]}'),
                                section=sec, mesh_advice=adv)
                for i in range(len(p) - 1)]

    @property
    def support_code(self) -> str:
        """Paper's support-layout code fragment: L-FT- / L-ST- / Z-FT- ..."""
        return f'{self.variant}-{"FT" if self.support_connector == "F" else "ST"}'

    def junctions(self) -> list:
        """The TEE joins the header. This is the declaration the mesher
        merges on -- previously the obligation lived only in `_priority`'s
        prose, so nothing downstream could act on it."""
        return [(f'{self._tag}:stee', 'pipeline')]

    def point_masses(self) -> list:
        """(node_id, mass_kg) -- Inertia elements per the paper.

        PLACEMENT IS AN ASSUMPTION: the paper says masses sit 'at their
        spool positions' and the figures show the valve on the horizontal
        run and the connector at the end, but no parameter locates the
        valve. P_bv supplies one, defaulting to mid-run.

        CORRECTED with P_bv. This previously returned the ELBOW node --
        'elbow' for the L and 'elbow2' for the Z -- while its own docstring
        said mid-run. Those are not the same point and were never close:
        at the L default the valve sat at x = 0.000 and at the Z default at
        x = 4.064, against a true mid-run of 2.032 m. For a 3 mT mass on a
        cantilevered branch that is the whole moment arm, wrong by half the
        run in one direction or the other depending on variant.

        SIGN: masses are returned as POSITIVE kg, direction-free. Weight
        acts in +Y -- see point_loads(), which is where that becomes a
        number."""
        t = self._tag
        end = self.path[-1][0]
        return [(f'{t}:svalve', self.mass_valve),
                (f'{t}:s{end}', self.mass_connector)]

    def point_loads(self, g: float = config.G) -> list:
        """(node_id, Fx_N, Fy_N) -- self-weight of the point masses.

        Fy IS POSITIVE. This module's y is positive-DOWN (Sec. item 26), so
        a downward gravity load is a POSITIVE Fy, and both the valve and
        the connector pull the branch down onto the structure supporting
        it. No node on this component carries a negative Fy.

        Stated as a method returning signed numbers rather than as a
        docstring note on point_masses, because a sign convention recorded
        only in prose is one a consumer can get wrong for free: y-positive-
        down is unusual enough that the natural mistake -- writing
        Fy = -m*g out of ordinary habit -- flips a 3 mT load into 3 mT of
        uplift and still solves.

        This is the ONE place gravity enters an otherwise purely geometric
        module, so g is an argument (defaulting to config.G) rather than a
        constant reached for internally -- a caller running a different
        acceleration case supplies it and nothing here has an opinion."""
        return [(nid, 0.0, m * g) for nid, m in self.point_masses()]

    # --- profile queries ---------------------------------------------------
    def section_at(self, x: float) -> Optional[Section]:
        return None      # teed off; adds no section to the header itself

    def contact_at(self, x: float) -> Optional[Contact]:
        return None      # rises away from the rollers

# ===========================================================================
# Sections 0.5/6 -- Externally-Attached structures [GD-ST / GD-SB]
# ===========================================================================

# ConnectorLocations REMOVED 23 Aug 2026. It held its own fixed P_c1=1.0 /
# P_c2=0.4 literals, which no longer scaled with either component's width,
# and it was the last surviving route by which a consumer could compute
# connector positions from something OTHER than the component itself.
# `plot_schematic.py` had in fact drifted onto its own formula (P_c1=0.5*B,
# P_c2=0.2*B) while component_spec used default_connector_spans (B/3, B/6),
# so the drawn slots and the modelled slots were in different places. The
# single route is now: component.connector_xs -> connector_slot_xs(...,
# **default_connector_spans(width)).

VALID_CONNECTOR_TYPES = {None, 'F', 'P', 'S', 'D'}


@dataclass(frozen=True)
class ConnectionSystem:
    """Sec.0.5 -- which of a component's 5 candidate slots (Set 2, in
    connector_slot_xs()'s order -- outer-L, inner-L, centre, inner-R,
    outer-R) carry an active connector, and what type each is.

    The TWO CHOICES stay separate on purpose. A component's candidate
    LOCATIONS are its own geometric fact (`connector_xs`, derived from its
    own width); which of them are populated, and with what type, is the
    connection system's separate choice. The same physical structure can be
    tested with F1, F2, PS and so on without its shape changing at all.

    `name` is a label; `named_connection_system()` is the way to get one of
    the six confirmed systems."""
    name: str
    types: tuple   # 5 entries, each None or one of 'F'/'P'/'S'/'D'

    def __post_init__(self):
        if len(self.types) != 5:
            raise GeometryRuleError(
                f'ConnectionSystem "{self.name}": types must have exactly 5 entries '
                f'(one per Set-2 slot: outer-L, inner-L, centre, inner-R, outer-R), '
                f'got {len(self.types)}.')
        bad = [t for t in self.types if t not in VALID_CONNECTOR_TYPES]
        if bad:
            raise GeometryRuleError(
                f'ConnectionSystem "{self.name}": invalid connector type(s) {bad} -- '
                f'each entry must be None or one of F/P/S/D.')


# Working defaults for the two EA components' own standalone figures --
# informal (not one of the document's named F1/F2/PS/PSD systems), and
# each component's own choice of what its default figure should show.
# ---------------------------------------------------------------------------
# Named connection systems (confirmed 22 Aug 2026). Slot order is
# connector_slot_xs()'s: 1=outer-L, 2=inner-L, 3=centre, 4=inner-R,
# 5=outer-R. NOTE "D" adds TWO connectors, one at each OUTER slot -- so
# F1->F1D is 1->3 connectors and F2->F2D is 2->4, and F2D has NOTHING at
# slot 3. These apply to BOTH GD-ST and GD-SB.
# ---------------------------------------------------------------------------
NAMED_CONNECTION_SYSTEMS = {
    'F1':  (None, None, 'F', None, None),
    'F2':  (None, 'F',  None, 'F', None),
    'F1D': ('D',  None, 'F', None, 'D'),
    'F2D': ('D',  'F',  None, 'F', 'D'),
    'PS':  (None, 'P',  None, 'S', None),
    'PSD': ('D',  'P',  None, 'S', 'D'),
}


def named_connection_system(name: str) -> 'ConnectionSystem':
    """Build a validated ConnectionSystem from a confirmed named pattern."""
    if name not in NAMED_CONNECTION_SYSTEMS:
        raise GeometryRuleError(
            f'unknown connection system {name!r}; known: '
            f'{sorted(NAMED_CONNECTION_SYSTEMS)}')
    return ConnectionSystem(name=name, types=NAMED_CONNECTION_SYSTEMS[name])


def connector_slot_xs(centre_x: float, P_c1: float, P_c2: float) -> tuple:
    """Five slot x-positions from TWO span parameters.

    P_c1 -- span between slot 2 and slot 4 (the interior pair)
    P_c2 -- offset from slot 2 out to slot 1 (and slot 4 out to slot 5)

    Slot 3 is the centre by definition; slots 1/5 are placed RELATIVE to
    2/4, so symmetry holds by construction rather than depending on the
    caller entering four numbers that happen to be symmetric.
    """
    inL, inR = centre_x - P_c1 / 2, centre_x + P_c1 / 2
    return (inL - P_c2, inL, centre_x, inR, inR + P_c2)


def default_connector_spans(width: float) -> dict:
    """Defaults tied to component width so they scale with it. Chosen to
    reproduce the evenly-spaced-excluding-endpoints layout exactly: five
    points at 1/6..5/6 of the width give interior span width/3 and outer
    offset width/6 (verified identical)."""
    return {'P_c1': width / 3.0, 'P_c2': width / 6.0}


# GDST_DEFAULT_CONNECTION_SYSTEM / GDSB_DEFAULT_CONNECTION_SYSTEM REMOVED
# 23 Aug 2026. Both predated the confirmed named systems and neither was
# one of them -- GD-SB's put 'S' at slot 3 where the real PS system puts it
# at slot 4, which had already been misread once as evidence that it WAS
# PS. A figure default that is nearly a named system is worse than no
# default. Callers now name a real system: active_connectors('F2') for
# GD-ST, active_connectors('PS') for GD-SB.


@dataclass(frozen=True)
class ExternalStructure(Component):
    """Common base for EA components (Sec.0.5).

    P_vt is the SIGNED POSITION of the NEAR surface in the pipe's own
    y-positive-DOWN frame -- NEGATIVE above the centreline, POSITIVE below.
    The body's OWN depth is a genuinely independent parameter; the FAR
    surface position is derived from P_vt and that depth. That ordering is
    v4.7's correction and is enforced here rather than restated.

    UNIFIED 23 Aug 2026. P_vt previously meant a POSITIVE STANDOFF DISTANCE
    on GD-ST (negated in y_near) and a SIGNED POSITION on GD-SB. One symbol,
    two meanings, on two classes sharing this base -- and the conflict was
    live: TopStructure.default_for() returned -1.5*OD, which the old
    P_vt >= 0 rule below REJECTED, so default_for() could not build the
    component it was written for. Both are now positions, both default
    NEGATIVE (structure above the centreline), and the >= 0 rule is gone:
    it is not meaningful for a signed position. Each subclass states its own
    geometric rule instead.
    """
    P_vt: float = 0.0                 # m, SIGNED position of the near surface
                                        # in y-positive-down (Sec.0.5)
    P_c1: Optional[float] = None      # m, FREE -- span between the interior
                                        # connector slots (2 and 4)
    P_c2: Optional[float] = None      # m, FREE -- offset from slot 2 out to
                                        # slot 1 (and 4 out to 5)
    # DEADBAND GAP -- the free travel a 'D' connector allows before it
    # closes and begins restraining (Fig 16: Ty free while < GAP,
    # restrained at >= GAP). REQUIRED whenever the active connection system
    # contains a D, and meaningless otherwise, so it defaults to None
    # rather than to a number: the design knowledge base calls this a
    # CRITICAL tuning parameter, because a deadband REDISTRIBUTES strain
    # rather than removing it and the gap decides WHERE it goes. A silent
    # default would make that choice for the engineer.
    #
    # The component cannot enforce "required when D" itself -- the
    # connection system is an ILS-LEVEL choice supplied at query time -- so
    # that check lives in ils_builder.validate().
    P_gap: Optional[float] = None     # m, FREE -- deadband free travel

    # PROMOTED TO FREE 24 Aug 2026. Both were DERIVED from the component's
    # own width via default_connector_spans (P_c1 = w/3, P_c2 = w/6), which
    # made the connector layout a function of the structure's size.
    #
    # Table VIII lists P_c1 and P_c2 as ENGINEERING PARAMETERS of EA-ST and
    # EA-SB, alongside kT and P_vt -- not as consequences of L_top. The
    # published F2 study varies P_c1 (10 D, then 20 D) while treating the
    # structure's size as a separate matter, and the whole finding of that
    # study is that ATTACHMENT LAYOUT rather than size governs the strain.
    # Deriving P_c1 from width welds together exactly the two things the
    # paper separates.
    #
    # It also could not reproduce the cases. P_c1 = L_top/3 means F2 Case 1
    # (P_c1 = 10 D) needs L_top = 30 D and Case 2 (20 D) needs 60 D, against
    # a stated practical range of ten to thirty diameters. Case 2 was not
    # reachable at all.
    #
    # Default stays the width-derived value, so nothing that omits them
    # changes.

    def _resolve_spans(self, width: float) -> None:
        d = default_connector_spans(width)
        if self.P_c1 is None:
            object.__setattr__(self, 'P_c1', d['P_c1'])
        if self.P_c2 is None:
            object.__setattr__(self, 'P_c2', d['P_c2'])

    def validate(self) -> None:
        """No shared rule for P_vt: it is a signed position, so there is no
        sign constraint common to both subclasses. Each states its own.

        P_c1/P_c2 ARE shared: a non-positive span would put slot 2 on or
        past slot 4, and the five slots would stop being ordered."""
        if self.P_c1 is not None and self.P_c1 <= 0:
            raise GeometryRuleError(
                f'{self.code}: P_c1 ({self.P_c1:.4f}) must be positive -- it '
                f'is the span between interior connector slots 2 and 4.')
        if self.P_c2 is not None and self.P_c2 <= 0:
            raise GeometryRuleError(
                f'{self.code}: P_c2 ({self.P_c2:.4f}) must be positive.')
        if self.P_gap is not None and self.P_gap <= 0:
            raise GeometryRuleError(
                f'{self.code}: P_gap ({self.P_gap * 1000:.1f} mm) must be '
                f'positive -- it is the free travel before a deadband '
                f'closes. A zero gap is a FIXED connector, which is a '
                f'different system (F), not a D that happens to shut '
                f'immediately.')

    def section_at(self, x: float) -> Optional[Section]:
        return None                    # EA components are not part of the pipe section


@dataclass(frozen=True)
class TopStructure(ExternalStructure):
    """Sec.6 / EA-ST. Sits ABOVE the pipe, so it never owns a contact
    surface -- contact_at inherits the base None. Stated rather than left
    implicit, since "returns None" should be a decision, not an omission."""
    # P_vt overridden HERE, not on ExternalStructure, because that base is
    # shared with GD-SB whose own default is still unresolved (the "offset
    # upwards for both" question). Changing the base would silently move
    # GD-SB too.
    P_vt: float = -0.6096             # m, FREE -- SIGNED POSITION of the frame
                                        # UNDERSIDE, y-positive-down, so NEGATIVE
                                        # = ABOVE the pipe C/L. Magnitude 1.5 x
                                        # pipe OD. Sign corrected 23 Aug 2026:
                                        # was +0.6096 with y_near = -P_vt, i.e.
                                        # a standoff DISTANCE. The rendered
                                        # geometry is UNCHANGED (y_near is still
                                        # -0.6096 m); what changed is that the
                                        # PARAMETER now carries the sign instead
                                        # of a negation buried in the accessor,
                                        # matching GD-SB and making
                                        # default_for()'s -1.5*OD usable.
    # Edge node positions, all PARAMETRIC (item 11). None -> defaults built
    # in __post_init__, which need L_top/H_top and so cannot be dataclass
    # defaults. Top and side edges default to ONE node at the MIDDLE of
    # that edge; when a branch is present these move to meet the branch's
    # connector -- see top_structure_for_branch().
    top_connector_x: Optional[tuple] = None
    left_connector_y: Optional[tuple] = None
    right_connector_y: Optional[tuple] = None
    L_top: float = 6.5024             # m, FREE -- 16 x pipe OD (was 2.0)
    H_top: float = 1.6256              # m, FREE -- the body's OWN depth,
                                        # 4 x pipe OD (was 0.60)
    kT_ratio: float = 2.5               # --, FREE. DIMENSIONLESS multiplier on
                                          # a plain pipe element of the SAME
                                          # length: K_frame(L) = kT_ratio *
                                          # K_pipe(L). Replaces the old scalar
                                          # `kT = 248577112.83 N*m^2` (22 Aug
                                          # 2026), which could only express ONE
                                          # term of a stiffness matrix that
                                          # actually has EA/L, 12EI/L^3,
                                          # 6EI/L^2, 4EI/L and 2EI/L. Being
                                          # dimensionless it is also pipe-
                                          # independent, so it needs no
                                          # default_for() entry.

    code: str = field(init=False, default='GD-ST')
    iw_ea_class: tuple = field(init=False, default=('EA-ST',))

    def __post_init__(self):
        """Fill the top/side edge-node defaults: ONE node at the MIDDLE of
        each edge. Done here, not as dataclass defaults, because they
        depend on L_top / H_top / P_vt, which are not known until
        construction."""
        if self.top_connector_x is None:
            object.__setattr__(self, 'top_connector_x', (self.centre_x,))
        y_mid = self.P_vt - self.H_top / 2.0     # P_vt is now a signed position
        if self.left_connector_y is None:
            object.__setattr__(self, 'left_connector_y', (y_mid,))
        if self.right_connector_y is None:
            object.__setattr__(self, 'right_connector_y', (y_mid,))
        # P_c1/P_c2 resolved HERE, not lazily inside connector_spans, and
        # BEFORE super().__post_init__() runs validate() -- same ordering
        # requirement as BranchPiping's P_b3/P_bv.
        #
        # The defect being fixed: resolution used to happen on first read of
        # connector_spans, so a FROZEN field changed value on read -- None
        # immediately after construction, a float once anything had touched
        # connector_xs. Any consumer reading the attribute directly saw a
        # value that depended on what else had run first.
        #
        # SCOPE, verified 26 Aug 2026 rather than assumed. `ILS.to_json()`
        # was NOT affected: it emits the verbatim definition dict and never
        # reads component state, so an omitted P_c1 stayed omitted either
        # way. `build_ils` also masked the flip, because ILS.validate()
        # reads active_connectors() before returning. The exposed surfaces
        # were DIRECT construction and anything reading the field off the
        # object afterwards -- `ILS.parameters()` above all, which is the
        # optimisation/ML feature vector and would emit None or a float for
        # the same design depending on call order.
        #
        # Resolved against L_top, matching connector_spans below.
        self._resolve_spans(self.L_top)
        super().__post_init__()

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """Pipe-relative default for kT (2.5*pipe.EI) -- the SINGLE place
        this relationship is computed. kT's dataclass default above is a
        fixed literal that happens to equal this formula's output for
        STD_PIPELINE; any caller building this component against a
        DIFFERENT pipe (including plot_schematic.py) should use this
        method rather than recomputing 2.5*EI itself."""
        # kT_ratio is DIMENSIONLESS and pipe-independent, so it is
        # deliberately absent here -- nothing to scale.
        return {'L_top': 16.0 * pipe.OD_pipe,
                'H_top': 4.0 * pipe.OD_pipe,
                'P_vt': -1.5 * pipe.OD_pipe}   # NEGATIVE: top ABOVE the C/L

    def validate(self) -> None:
        super().validate()
        if self.L_top <= 0 or self.H_top <= 0:
            raise GeometryRuleError(f'{self.code}: L_top and H_top must be positive')
        # Own rule, replacing the retired shared P_vt >= 0 check: GD-ST sits
        # ABOVE the pipe, so its UNDERSIDE must be above the centreline.
        # A frame whose underside is at or below y=0 would intersect the
        # pipe it is meant to straddle.
        if self.P_vt >= 0:
            raise GeometryRuleError(
                f'{self.code}: P_vt ({self.P_vt:.4f} m) is the SIGNED position '
                'of the frame underside in y-positive-down, and GD-ST sits '
                'ABOVE the pipe -- so it must be NEGATIVE.')

    @property
    def y_near(self) -> float:
        """Frame underside -- IS P_vt, no negation. P_vt is the signed
        position (23 Aug 2026), so this accessor no longer flips a sign the
        parameter did not carry."""
        return self.P_vt

    @property
    def y_far(self) -> float:
        """Frame top -- further above the pipe, so MORE negative. H_top is
        the body's OWN depth, so the top is one depth further from the
        centreline than the underside."""
        return self.P_vt - self.H_top

    @property
    def extent(self) -> tuple[float, float]:
        return (self.centre_x - self.L_top / 2, self.centre_x + self.L_top / 2)

    # --- node/line accessors: DERIVED, never stored ------------------------
    @property
    def _tag(self) -> str:
        return f'{self.code}@{self.centre_x:+.4f}'

    @property
    def connector_spans(self) -> dict:
        """P_c1/P_c2, resolved in __post_init__ (defaulting to L_top/3 and
        L_top/6 when the caller gave neither, so an omitted layout is
        unchanged). No longer resolves here -- see __post_init__ for why
        lazy resolution on first read was wrong."""
        return {'P_c1': self.P_c1, 'P_c2': self.P_c2}

    @property
    def connector_xs(self) -> tuple:
        return connector_slot_xs(self.centre_x, **self.connector_spans)

    def geometry_nodes(self) -> list:
        """Four corners plus the five connector slots on the underside.

        y is NEGATIVE here: GD-ST sits ABOVE the pipe and y is
        positive-DOWN (item 26).

        PREFERRED, never MANDATORY -- GD-ST owns no contact surface, so
        nothing here forces a pipeline mesh node."""
        xL, xR = self.extent
        yB, yT = self.y_near, self.y_far
        t = self._tag
        out = [GeometryNode(f'{t}:cBL', xL, yB, NodePriority.PREFERRED),
               GeometryNode(f'{t}:cBR', xR, yB, NodePriority.PREFERRED),
               GeometryNode(f'{t}:cTR', xR, yT, NodePriority.PREFERRED),
               GeometryNode(f'{t}:cTL', xL, yT, NodePriority.PREFERRED)]
        for i, x in enumerate(self.connector_xs, start=1):
            out.append(GeometryNode(f'{t}:slot{i}', x, yB, NodePriority.PREFERRED))
        for i, x in enumerate(self.top_connector_x, start=1):
            out.append(GeometryNode(f'{t}:top{i}', x, yT, NodePriority.PREFERRED))
        for i, y in enumerate(self.left_connector_y, start=1):
            out.append(GeometryNode(f'{t}:left{i}', xL, y, NodePriority.PREFERRED))
        for i, y in enumerate(self.right_connector_y, start=1):
            out.append(GeometryNode(f'{t}:right{i}', xR, y, NodePriority.PREFERRED))
        return out

    def structural_nodes(self) -> list:
        """SHARES COORDINATES with geometry_nodes: one structural node per
        geometry node at the SAME (x, y), so the structural lines overlap
        the geometry lines exactly. The frame is a CLOSED FRAME of four
        members round the perimeter, not a beam on a computed neutral
        axis.

        BUG FIXED 23 Aug 2026. The id map was two literal substitutions,
        ':c'->':sc' and ':slot'->':sslot', which covered the corners and the
        bottom slots but NOT the top/left/right edge nodes added later. Those
        three kept their geometry ids while structural_lines() referenced
        ':stop1'/':sleft1'/':sright1' -- so three of twelve members pointed
        at nodes that did not exist, and three declared nodes were endpoints
        of nothing. Now one uniform map (`_s_id`) covers every node whatever
        it is named. PRIORITY is mirrored too, rather than being forced to
        PREFERRED: a slope discontinuity is one on both lines."""
        return [StructuralNode(_s_id(g.node_id), g.x, g.y, g.priority)
                for g in self.geometry_nodes()]

    def _edge_chains(self) -> list:
        """(node_a, node_b) pairs walking the perimeter, PASSING THROUGH
        every edge node rather than jumping corner to corner.

        Previously each edge was a single corner-to-corner segment, so the
        bottom slot nodes sat ON a line without subdividing it -- a node
        that is not an element boundary carries no load, which defeats the
        point of having it. Each edge is now a CHAIN.
        """
        b = sorted(range(1, len(self.connector_xs) + 1),
                   key=lambda i: self.connector_xs[i - 1])
        r = sorted(range(1, len(self.right_connector_y) + 1),
                   key=lambda i: -self.right_connector_y[i - 1])
        tp = sorted(range(1, len(self.top_connector_x) + 1),
                    key=lambda i: -self.top_connector_x[i - 1])
        lf = sorted(range(1, len(self.left_connector_y) + 1),
                    key=lambda i: self.left_connector_y[i - 1])
        seq = (['cBL'] + [f'slot{i}' for i in b] + ['cBR']
               + [f'right{i}' for i in r] + ['cTR']
               + [f'top{i}' for i in tp] + ['cTL']
               + [f'left{i}' for i in lf] + ['cBL'])
        return [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]

    def geometry_lines(self) -> list:
        """Perimeter CHAIN through every edge node. owns_contact=False on
        every segment -- GD-ST sits above the pipe and never owns a contact
        surface (Sec.6.3). Queryable, so nothing iterating geometry lines
        for contact candidates needs to special-case GD-ST."""
        t = self._tag
        adv = ContactAdvice(
            normal_is_collinear_with_offset=True,
            requires_node_at_contact=False,
            note='SHAPE ONLY -- sits above the pipe, contact_at returns None '
                  '(Sec.6.3). owns_contact is the field that matters here.')
        return [GeometryLine(line_id=f'{t}:footprint',
                              node_ids=(f'{t}:{a}', f'{t}:{b}'),
                              structural_line_id=f'{t}:frame',
                              owns_contact=False, contact_advice=adv)
                for a, b in self._edge_chains()]

    def structural_lines(self) -> list:
        """Four frame members, node-for-node with the geometry loop.

        stiffness_rule, NOT a Section: kT is a MESHER-APPLIED PER-ELEMENT
        rule, so it cannot be a number here. Contrast GD-TP/GD-TT, whose
        stiffness IS a real section property, mesh-independent."""
        t = self._tag
        adv = MeshAdvice(min_elements=1, max_size_ratio=2.0,
                          note='Frame member. Stiffness from the kT rule, not '
                               'a section, so element length affects STIFFNESS '
                               'as well as resolution.')
        return [StructuralLine(line_id=f'{t}:frame',
                                node_ids=(f'{t}:s{a}', f'{t}:s{b}'),
                                section=None,
                                stiffness_ratio=self.kT_ratio,
                                mesh_advice=adv)
                for a, b in self._edge_chains()]

    def active_connectors(self, system: str = 'F2') -> list:
        """(slot, x, type, arm, gap) per ACTIVE connector of a named system.

        `gap` is P_gap on a 'D' connector and None on every other type.
        Carried HERE rather than left on the component because a consumer
        walking the connectors -- a mesher writing contact definitions --
        meets the D and needs its gap at that moment; making it reach back
        to the component is how a gap gets dropped. `arm` sets the
        precedent, being a per-component value too.

        WIDENED FROM 4 TO 5 ELEMENTS, 28 Aug 2026. A consumer unpacking
        four now raises -- deliberately. Silently ignoring a fifth value
        would mean meshing a deadband as though it had none.

        NAMED `active_connectors`, not `connectors`: the retired
        `connectors` FIELD once occupied that name on ExternalStructure, and
        a method shadowing a field makes the field uncallable and the method
        unreachable. The field is gone (23 Aug 2026) but the name stays --
        `active_connectors` says more anyway, since it returns only the
        POPULATED slots, not all five candidates.

        2-NODE elements: PIPE-side node always Fixed, EA-side node carries
        the type. `arm` is the MAGNITUDE of the pipe C/L to frame underside
        distance, |P_vt| -- a magnitude, not a signed position, and the same
        convention GD-SB uses (both report a positive arm for a structure on
        their own side of the pipe).

        Item 8: connector STIFFNESS must be a preset stiff value, NEVER
        derived from this length -- P_vt = 0 is legal and makes the
        connector genuinely zero-length."""
        types = named_connection_system(system).types
        return [(i, x, t, abs(self.P_vt), self.P_gap if t == 'D' else None)
                for i, (x, t) in enumerate(zip(self.connector_xs, types), start=1)
                if t is not None]


def top_structure_for_branch(pipe, branch, centre_x=None, **kw):
    """Build a GD-ST whose TOP or SIDE edge node lands exactly on the
    branch's end connector, so the branch can be tied to a real structural
    node rather than to an arbitrary point on an edge.

    Which edge depends on the branch's connector axis (Table II / Fig 15):
      L-branch, HORIZONTAL connector -> moves the RIGHT-side node to the
        connector's elevation
      Z-branch, VERTICAL connector   -> moves the TOP node to the
        connector's x

    Default GD-ST geometry otherwise, so a branch is always presented on a
    workable structure that the user can then modify.
    """
    if centre_x is None:
        centre_x = branch.centre_x + branch.P_b1 / 2.0
    end_x, end_y = branch.path[-1][1], branch.path[-1][2]
    # (a TopStructure was built here and immediately discarded -- removed
    #  23 Aug 2026; the only one that matters is the one returned below.)
    if branch.connector_axis == 'vertical':
        kw2 = dict(top_connector_x=(end_x,))
    else:
        kw2 = dict(right_connector_y=(end_y,))
    return TopStructure(pipe=pipe, centre_x=centre_x, **{**kw, **kw2})


@dataclass(frozen=True)
class BaseStructure(ExternalStructure):
    """Sec.0.5 / EA-SB. Trapezoid below the pipe -- and in an assembly, the
    body whose BOTTOM SURFACE is the contact surface.

    Its reaction does NOT act on the pipe element beneath it. The path is
    contact point -> structure member -> F/P/S/D connector -> pipe node, so
    contact_at returns LoadPath.CONNECTOR and an arm of (P_vt + P_v). At the
    default P_vt=0 with P_v=0.72 m that arm is 0.72 m: applying the reaction
    at the pipe node without it silently discards a moment of R * 0.72,
    which is the elevation effect this component exists to produce.
    """
    # Defaults made PIPE-RELATIVE and aligned with GD-ST (22 Aug 2026).
    # P_l1 mirrors L_top (16D) and P_v mirrors H_top (4D); P_l2 is set to
    # 2D. Previous absolute values were 4.0 / 0.55 / 0.72 m, i.e. 9.84D /
    # 1.35D / 1.77D -- so this is a GENUINE SIZE CHANGE, not a re-expression.
    P_l1: float = 6.5024              # m, FREE -- flat-bottom width, 16 D
    P_l2: float = 0.8128               # m, FREE -- sloped-side run, 2 D
    P_v: float = 1.6256                 # m, FREE -- the body's OWN depth, 4 D
    P_vt: float = -0.6096                # m, FREE -- POSITION of the structure TOP
                                          # relative to the pipe C/L, in y-positive-DOWN.
                                          # NEGATIVE = ABOVE the centreline (rule 22 Aug
                                          # 2026), so the structure STRADDLES the pipe:
                                          # side walls rise past the C/L and the pipe
                                          # nests inside. Magnitude 1.5 D, matching GD-ST.
                                          # NOTE this is a POSITION here, not a DISTANCE --
                                          # GD-ST's P_vt is a positive standoff that negates
                                          # in y_near. Same symbol, opposite role, as with
                                          # GD-TP's derived V vs GD-SH's free V.
                                          # Overridden here (not on
                                          # ExternalStructure) so GD-ST keeps
                                          # its own. POSITIVE = BELOW the pipe
                                          # under y-positive-down: the base
                                          # structure hangs beneath, mirroring
                                          # GD-ST's negative-y position above.
    kB_ratio: float = 2.5               # --, FREE. DIMENSIONLESS multiplier on
                                          # a plain pipe element of the SAME
                                          # length: K_member(L) = kB_ratio *
                                          # K_pipe(L). Replaces the old scalar
                                          # `kB = 248577112.83 N*m^2`, which
                                          # could only express ONE term of a
                                          # matrix that actually has EA/L,
                                          # 12EI/L^3, 6EI/L^2, 4EI/L, 2EI/L.
                                          # Dimensionless => pipe-independent,
                                          # so no default_for entry.

    code: str = field(init=False, default='GD-SB')
    iw_ea_class: tuple = field(init=False, default=('EA-SB',))

    def __post_init__(self):
        """P_c1/P_c2 resolved HERE, not lazily inside connector_spans, and
        BEFORE super().__post_init__() runs validate() -- mirrors
        TopStructure, same reasoning and same verified scope (see the note
        in TopStructure.__post_init__): a frozen field must not change
        value on first read.

        Resolved against P_l1, matching connector_spans below -- the
        flat-bottom width the connectors actually have to work with, not
        L_top.

        NOTE this class's validate() does NOT call super().validate(), so
        the inherited P_c1/P_c2 positivity checks do not run for GD-SB.
        That is a separate live defect, not introduced here -- see
        validate() below."""
        self._resolve_spans(self.P_l1)
        super().__post_init__()

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """Pipe-relative default for kB (2.5*pipe.EI) -- the SINGLE place
        this relationship is computed, mirroring TopStructure.default_for.
        kB's dataclass default above is a fixed literal that happens to
        equal this formula's output for STD_PIPELINE; any caller building
        this component against a DIFFERENT pipe (including
        plot_schematic.py) should use this method rather than
        recomputing 2.5*EI itself."""
        # kB_ratio is DIMENSIONLESS and pipe-independent -- nothing to
        # scale, so it is deliberately absent here.
        return {'P_l1': 16.0 * pipe.OD_pipe,
                'P_l2': 2.0 * pipe.OD_pipe,
                'P_v': 4.0 * pipe.OD_pipe,
                'P_vt': -1.5 * pipe.OD_pipe}   # NEGATIVE: top ABOVE the C/L

    def validate(self) -> None:
        # NOT super().validate() -- and the original reason for that is now
        # STALE. It was skipped because ExternalStructure required
        # P_vt >= 0, right for GD-ST (then a standoff DISTANCE) but wrong
        # here, where P_vt is a POSITION, negative by default so the
        # structure straddles the pipe. That rule was RETIRED on
        # 23 Aug 2026 when P_vt was unified as a signed position, so
        # ExternalStructure.validate() no longer checks P_vt at all.
        #
        # LIVE CONSEQUENCE, unresolved as of 26 Aug 2026: what the skip now
        # discards is the inherited P_c1/P_c2 POSITIVITY check, which is
        # the only thing left in ExternalStructure.validate(). GD-SB
        # therefore accepts a negative P_c1 and builds crossed, unordered
        # connector slots -- e.g. P_c1 = -1.0 yields
        # (-0.584, +0.5, 0.0, -0.5, +0.584), slot 2 past slot 4. This went
        # live when P_c1/P_c2 were promoted to FREE (24 Aug 2026): while
        # they were derived from a positive width they could not go
        # negative, so nothing could reach the check.
        #
        # FIX is one line -- call super().validate() below -- but it is left
        # as a DECISION rather than applied silently, since the skip was
        # once deliberate. GD-ST is unaffected: it calls super().
        #
        # The check that IS meaningful here is that the BOTTOM still lies
        # below the centreline -- otherwise no roller could ever contact it.
        if self.P_vt + self.P_v <= 0:
            raise GeometryRuleError(
                f'{self.code}: structure bottom (P_vt + P_v = '
                f'{self.P_vt + self.P_v:.4f} m) must lie BELOW the pipe '
                f'centreline, or no roller can ever contact it')
        if min(self.P_l1, self.P_v) <= 0 or self.P_l2 < 0:
            raise GeometryRuleError(
                f'{self.code}: P_l1 and P_v must be positive, P_l2 >= 0')

    @property
    def y_top(self) -> float:
        return self.P_vt

    @property
    def y_bottom(self) -> float:
        """Sec.0.5 -- DERIVED, = P_vt + P_v. P_v is the body's own depth,
        not a position (v4.7's correction). POSITIVE because y is
        positive-DOWN (item 26): the base structure hangs BELOW the pipe."""
        return self.P_vt + self.P_v

    @property
    def x_flat(self) -> tuple[float, float]:
        return (self.centre_x - self.P_l1 / 2, self.centre_x + self.P_l1 / 2)

    @property
    def extent(self) -> tuple[float, float]:
        fL, fR = self.x_flat
        return (fL - self.P_l2, fR + self.P_l2)

    # --- node/line accessors: DERIVED, never stored ------------------------
    @property
    def _tag(self) -> str:
        return f'{self.code}@{self.centre_x:+.4f}'

    @property
    def connector_spans(self) -> dict:
        """P_c1/P_c2, resolved in __post_init__ against the FLAT-BOTTOM
        width P_l1 -- the span the connectors actually have to work with,
        mirroring GD-ST's use of L_top. No longer resolves here -- see
        __post_init__ for why lazy resolution on first read was wrong."""
        return {'P_c1': self.P_c1, 'P_c2': self.P_c2}

    @property
    def connector_xs(self) -> tuple:
        return connector_slot_xs(self.centre_x, **self.connector_spans)

    def geometry_nodes(self) -> list:
        """Four trapezoid corners plus the five connector slots on the TOP
        surface (the face towards the pipe).

        SIGNS, at the current defaults: the BOTTOM is at positive y (below
        the C/L, y_bottom = +1.016 m) but the TOP is at NEGATIVE y
        (y_top = P_vt = -0.6096 m). The structure STRADDLES the pipe -- its
        side walls rise past the centreline and the pipe nests inside. An
        earlier version of this docstring claimed all y are positive; that
        was true only when P_vt defaulted to zero.

        Corner nodes are MANDATORY: the bottom corners are slope
        discontinuities in the contact surface, which is a real feature a
        roller can cross. Connector slots are PREFERRED -- they sit on the
        top face and constrain nothing about contact."""
        xL, xR = self.extent
        fL, fR = self.x_flat
        yT, yB = self.y_top, self.y_bottom
        t = self._tag
        out = [GeometryNode(f'{t}:cTL', xL, yT, NodePriority.MANDATORY),
               GeometryNode(f'{t}:cBL', fL, yB, NodePriority.MANDATORY),
               GeometryNode(f'{t}:cBR', fR, yB, NodePriority.MANDATORY),
               GeometryNode(f'{t}:cTR', xR, yT, NodePriority.MANDATORY)]
        for i, x in enumerate(self.connector_xs, start=1):
            out.append(GeometryNode(f'{t}:slot{i}', x, yT,
                                     NodePriority.PREFERRED))
        return out

    def structural_nodes(self) -> list:
        """SHARES COORDINATES with geometry_nodes (the GD-ST rule): one
        structural node per geometry node at the SAME (x, y), so the
        structural lines overlap the geometry lines exactly. The structure
        is a CLOSED FRAME of four members round the trapezoid."""
        return [StructuralNode(_s_id(g.node_id), g.x, g.y, g.priority)
                for g in self.geometry_nodes()]

    def _edge_chains(self) -> list:
        """(node_a, node_b, kind, owns_contact) walking the closed outline,
        PASSING THROUGH every connector slot on the top face rather than
        jumping corner to corner.

        Added 23 Aug 2026, matching what GD-ST already did. Before this the
        outline was four corner-to-corner segments while nine nodes were
        declared, so the five slot nodes sat ON the top line without
        subdividing it -- and a node that is not an element boundary
        carries no load, which is the whole reason for declaring it. The
        integrity check now reports zero orphan nodes for GD-SB.

        Walk order: left slope down, flat bottom, right slope up, then the
        top face right-to-left, so the slots are traversed in DESCENDING x.
        """
        order = sorted(range(1, len(self.connector_xs) + 1),
                       key=lambda i: -self.connector_xs[i - 1])
        top_seq = ['cTR'] + [f'slot{i}' for i in order] + ['cTL']
        segs = [('cTL', 'cBL', 'slope', True),      # left slope
                ('cBL', 'cBR', 'flat', True),        # flat bottom
                ('cBR', 'cTR', 'slope', True)]       # right slope
        segs += [(top_seq[i], top_seq[i + 1], 'top', False)
                 for i in range(len(top_seq) - 1)]
        return segs

    def geometry_lines(self) -> list:
        """The closed trapezoid outline: left slope, flat bottom, right
        slope, then the top face CHAINED through the connector slots.

        MIXED owns_contact -- and the first component where the SHAPE
        itself splits the two cases:
          bottom  -> owns_contact TRUE. This is the surface a roller meets.
          slopes  -> TRUE. Inclined, so the normal TILTS away from the
                     offset and a real moment arises (contrast GD-TT's
                     concentric taper, where it does not).
          top     -> FALSE. Faces the pipe, away from the rollers; it can
                     never be contacted.
        GD-ST is shape-only entirely; GD-TP/TT own contact entirely; GD-VLV
        splits by member. GD-SB splits by FACE of one closed outline."""
        t = self._tag
        flat_adv = ContactAdvice(
            normal_is_collinear_with_offset=True, requires_node_at_contact=False,
            note='Flat bottom: normal vertical, offset vertical, collinear -> '
                  'no moment from the offset itself. The CONNECTOR arm is a '
                  'separate matter -- see contact_at load_path=CONNECTOR.')
        slope_adv = ContactAdvice(
            normal_is_collinear_with_offset=False, requires_node_at_contact=False,
            note='Sloped side: INCLINED surface, so the normal tilts away from '
                  'the vertical offset and a genuine moment arises.')
        top_adv = ContactAdvice(
            normal_is_collinear_with_offset=True, requires_node_at_contact=False,
            note='SHAPE ONLY -- the top face looks toward the pipe, away from '
                  'the rollers, and can never be contacted.')
        adv_for = {'slope': slope_adv, 'flat': flat_adv, 'top': top_adv}
        return [GeometryLine(line_id=f'{t}:outline',
                              node_ids=(f'{t}:{a}', f'{t}:{b}'),
                              structural_line_id=f'{t}:frame',
                              owns_contact=oc, contact_advice=adv_for[kind])
                for a, b, kind, oc in self._edge_chains()]

    def structural_lines(self) -> list:
        """Four members round the trapezoid, node-for-node with the
        geometry outline.

        `stiffness_ratio`, NOT a Section: the structure has no genuine
        pipe-like cross-section to derive from, so its element stiffness is
        expressed as a multiple of a plain pipe element of the SAME length
        (see StructuralLine's docstring for why a ratio rather than a single
        stiffness number)."""
        t = self._tag
        adv = MeshAdvice(min_elements=1, max_size_ratio=2.0,
                          note='Structure member. Stiffness is a RATIO to a '
                               'plain pipe element of the same length.')
        return [StructuralLine(line_id=f'{t}:frame',
                                node_ids=(f'{t}:s{a}', f'{t}:s{b}'),
                                section=None,
                                stiffness_ratio=self.kB_ratio,
                                mesh_advice=adv)
                for a, b, _kind, _oc in self._edge_chains()]

    def active_connectors(self, system: str = 'PS') -> list:
        """(slot, x, type, arm, gap) per ACTIVE connector of a named system.

        `gap` is P_gap on a 'D' connector and None on every other type.
        Carried HERE rather than left on the component because a consumer
        walking the connectors -- a mesher writing contact definitions --
        meets the D and needs its gap at that moment; making it reach back
        to the component is how a gap gets dropped. `arm` sets the
        precedent, being a per-component value too.

        WIDENED FROM 4 TO 5 ELEMENTS, 28 Aug 2026. A consumer unpacking
        four now raises -- deliberately. Silently ignoring a fifth value
        would mean meshing a deadband as though it had none.

        2-NODE elements: the PIPE-side node is always Fixed; the EA-side
        node carries the type. `arm` is |P_vt|, the MAGNITUDE of the pipe
        C/L to the structure's TOP face -- same convention as GD-ST.

        Default 'PS' rather than GD-ST's 'F2': the retired GD-SB figure
        default was historically P+S, though at slot 3 rather than the
        confirmed slot 4 -- so it was never actually the named PS system.
        This uses the CONFIRMED pattern.

        Connector STIFFNESS must be a preset stiff value, NEVER derived
        from this length."""
        types = named_connection_system(system).types
        return [(i, x, ty, abs(self.P_vt), self.P_gap if ty == 'D' else None)
                for i, (x, ty) in enumerate(zip(self.connector_xs, types), start=1)
                if ty is not None]

    def contact_at(self, x: float) -> Optional[Contact]:
        if not self.owns(x):
            return None
        fL, fR = self.x_flat
        if fL <= x <= fR:
            y = self.y_bottom
        elif x < fL:
            f = (x - (fL - self.P_l2)) / self.P_l2 if self.P_l2 else 1.0
            y = self.y_top + f * (self.y_bottom - self.y_top)
        else:
            f = ((fR + self.P_l2) - x) / self.P_l2 if self.P_l2 else 1.0
            y = self.y_top + f * (self.y_bottom - self.y_top)
        return Contact(y=y, owner=self.code, load_path=LoadPath.CONNECTOR,
                        arm=abs(y))


# ===========================================================================
# Assembly -- composition and the contact envelope
# ===========================================================================

class OwnershipPolicy(Enum):
    """How the assembly resolves two components claiming contact at one x.

    LOWEST -- deepest surface wins. Physically the obvious reading, and
        wrong silently when it is wrong.
    STRICT -- raise unless exactly one component claims contact. The right
        default for AI-generated assemblies: a plausible-looking assembly
        with the wrong contact envelope produces an FEA run that converges
        and reports a believable strain, which is the worst failure mode
        available. Better to refuse to build it.
    """
    LOWEST = 'lowest'
    STRICT = 'strict'


@dataclass
class Assembly:
    """Several independently-defined components on one shared pipeline axis."""
    pipe: BasePipeline
    components: Sequence[Component]
    ownership: OwnershipPolicy = OwnershipPolicy.STRICT

    def __post_init__(self):
        for c in self.components:
            if c.pipe != self.pipe:
                raise GeometryRuleError(
                    f'{c.code} was built against a different BasePipeline. '
                    'Sec.0.1 parameters are inherited once, per assembly.')

    @property
    def provenance(self) -> Provenance:
        """An assembly is only as trustworthy as its least-trustworthy part."""
        if any(c.provenance is Provenance.ILLUSTRATIVE for c in self.components):
            return Provenance.ILLUSTRATIVE
        if any(c.provenance is Provenance.PAPER for c in self.components):
            return Provenance.PAPER
        return Provenance.DESIGN

    def section_at(self, x: float) -> Section:
        claimed = [(c, c.section_at(x)) for c in self.components]
        claimed = [(c, s) for c, s in claimed if s]
        claims = [s for _, s in claimed]
        if not claims:
            return Section(OD=self.pipe.OD_pipe, t=self.pipe.t_pipe, owner='pipe')
        if len(claims) > 1:
            # ABUTMENT IS NOT AMBIGUITY -- see the same reasoning in
            # contact_at. Two components welded end to end share exactly one
            # station and both legitimately claim it; that is a join, not a
            # conflict. Only extents overlapping over a LENGTH are a real
            # double-claim. Without this, every flush join in a chained
            # header is a coin flip on whether the sampler lands on it.
            tol = ABUTMENT_TOL
            genuine = False
            for i in range(len(claimed)):
                for j in range(i + 1, len(claimed)):
                    a0, a1 = claimed[i][0].extent
                    b0, b1 = claimed[j][0].extent
                    if min(a1, b1) - max(a0, b0) > tol:
                        genuine = True
                        break
                if genuine:
                    break
            if genuine:
                raise ContactAmbiguityError(
                    f'x={x:.3f}: overlapping section claims from '
                    f'{[s.owner for s in claims]}. Two components cannot both '
                    'set the pipe section at one station.')
            # At a weld the thicker section governs: a step cannot be
            # averaged away, and the stiffer side is what the station carries.
            return max(claims, key=lambda s: s.OD)
        return claims[0]

    def contact_at(self, x: float) -> Contact:
        """The surface a roller MEETS at x -- the LOWEST one present.

        THE PIPE IS A PARTICIPANT, NOT A FALLBACK (fixed 28 Aug 2026).
        It used to be consulted only when NO component claimed the station,
        so a claiming component won outright even where its own surface sat
        ABOVE the pipe. That is not what a roller does.

        The case that exposed it: a GD-SB at the published P_vt = 0 has its
        sloped wall starting level with the pipe CENTRELINE, so for the
        first 0.25 D inside its extent the wall is up to 203 mm ABOVE the
        pipe bottom. Ownership passed to the structure at its extent edge,
        but contact really TRANSFERS where the descending wall crosses the
        pipe bottom:

            x_transfer = x_start + P_l2 * (OD_pipe/2) / P_v

        Between those two stations the old answer named a surface no roller
        could reach. Harmless in a drawing, NOT harmless in a mesh -- this
        feeds contact definition for FEA, and a contact plane 203 mm off
        the real one is a wrong model that still converges.

        OWNERSHIP AND ELEVATION ARE SEPARATE QUESTIONS, and the order
        matters. Ambiguity is resolved FIRST, among COMPONENTS only: the
        pipe never creates a clash, because it is always present and
        claims nothing. STRICT still refuses to guess between two
        components. Only then is the winner compared against the pipe --
        which is geometry, not a guess, so it applies under STRICT too.
        """
        pipe_y = self.pipe.OD_pipe / 2
        pipe_c = Contact(y=pipe_y, owner='pipe',
                         load_path=LoadPath.PIPE_ELEMENT, arm=abs(pipe_y))
        claimed = [(comp, comp.contact_at(x)) for comp in self.components]
        claimed = [(comp, c) for comp, c in claimed if c]
        claims = [c for _, c in claimed]
        if not claims:
            return pipe_c

        # ABUTMENT IS NOT AMBIGUITY. Two components that merely TOUCH share
        # exactly one point, and both legitimately own it -- extents are
        # closed intervals because the boundary really is shared. That is a
        # weld, not an overlap, and it must not be reported as a conflict.
        #
        # This mattered little while headers were continuous and flush joins
        # were rare. It matters completely once a header is a CHAIN, where
        # every boundary is a flush join: measured on correct 3-part chains,
        # ~7% raised here purely on whether the contact sampler happened to
        # land on a join, and the rate rises with the number of joins.
        #
        # The distinction is interval overlap, not point coincidence: two
        # extents that overlap over a LENGTH are a real conflict; two that
        # meet at a point are joined. Resolving this here, rather than by
        # making extents half-open, keeps the geometry honest -- the shared
        # boundary is a real feature of the geometry, and turning it into a
        # gap to satisfy a sampling artefact would corrupt the model to serve
        # the mesher. Coincident nodes are the MESHER's to resolve.
        if len(claims) > 1:
            tol = ABUTMENT_TOL
            genuine_overlap = False
            for i in range(len(claimed)):
                for j in range(i + 1, len(claimed)):
                    a0, a1 = claimed[i][0].extent
                    b0, b1 = claimed[j][0].extent
                    if min(a1, b1) - max(a0, b0) > tol:
                        genuine_overlap = True
                        break
                if genuine_overlap:
                    break
            if not genuine_overlap:
                # A step at a weld: the deeper surface is what a roller meets,
                # since it cannot pass through the shoulder.
                best = max(claims, key=lambda c: c.y)
                return best if best.y >= pipe_y else pipe_c

        if len(claims) == 1:
            # y positive-DOWN: the winner only wins if it is at or BELOW
            # the pipe. A tie goes to the component, where they coincide.
            return claims[0] if claims[0].y >= pipe_y else pipe_c
        if self.ownership is OwnershipPolicy.LOWEST:
            # y is positive-DOWN (item 26), so the DEEPEST surface is the
            # one with the LARGEST y -- not the smallest. This line was
            # min() under the old y-up convention; flipping the convention
            # without flipping this would silently pick the SHALLOWEST
            # surface as the contact owner.
            best = max(claims, key=lambda c: c.y)
            return best if best.y >= pipe_y else pipe_c
        raise ContactAmbiguityError(
            f'x={x:.3f}: {len(claims)} components claim the contact surface '
            f'({[(c.owner, round(c.y, 3)) for c in claims]}). Under STRICT '
            'ownership the assembly will not guess. Either separate them, or '
            'set ownership=OwnershipPolicy.LOWEST having checked that the '
            'deepest surface is genuinely the contacting one.')

    def sample(self, x0: float, x1: float, n: int = 401):
        """Both profiles over a range -- the arrays a schematic plots and an
        FEA deck writer consumes, from one call, so they cannot disagree."""
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        return xs, [self.section_at(x) for x in xs], [self.contact_at(x) for x in xs]

    def unsampled_features(self, roller_xs: Sequence[float]) -> list[str]:
        """Sec.2.8's fidelity gap, promoted to a validity check on results.

        A perfectly-defined contact envelope proves nothing if no roller
        ever touches its features: roller spacing is 8-9 m, while GD-SH's
        deep section at the paper's reference case is ~4 m. Reports every
        component whose extent contains no roller station.
        """
        missed = []
        for c in self.components:
            x0, x1 = c.extent
            if not any(x0 <= rx <= x1 for rx in roller_xs):
                missed.append(
                    f'{c.code} @ x={c.centre_x:+.2f} m (extent '
                    f'{x0:+.2f}..{x1:+.2f} m) -- no roller station falls inside')
        return missed


# ===========================================================================
# Plain pipe segments [GD-HdPipe / GD-BrPipe]
# ===========================================================================

@dataclass(frozen=True)
class HeaderPipeSegment(Component):
    """A plain length of the header's own pipe, between two components.

    WHY IT EXISTS. Component SPACING is a real studied design variable, but
    until now it was only an emergent consequence of two `centre_x` values
    with nothing representing the gap itself. This component makes the gap
    an object with its own length parameter.

    ADDS NOTHING. Same OD, same wall, same material as the pipe it sits in:
    no section change, no stiffness step, no elevation, no added mass. That
    is the defining property, not an omission -- a segment differing in any
    of these would be a ThickPipeBody. It follows that this component IS
    the plain-pipe baseline every other component's behaviour is measured
    against, made explicit.

    OPTIONAL, NOT COMPULSORY. Two inline components may mate directly; the
    girth weld exists at that point either way. Use this only when a spacer
    is a design decision worth recording.

    NO DEFAULT LENGTH. Every other component here has pipe-relative
    defaults, because a wall thickness or a taper length has a natural
    ratio to the pipe. A spacer's length does not -- it is set by the
    layout, not by the diameter. `L_pipe` therefore defaults to 0.0, which
    validate() rejects: the caller must supply one. That is deliberate, not
    an oversight, and `default_for` returns nothing for the same reason.
    """
    L_pipe: float = 0.0                # m, FREE -- no natural default

    code: str = field(init=False, default='GD-HdPipe')
    iw_ea_class: tuple = field(init=False, default=('IW-P',))

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """Deliberately empty -- see class docstring. Present so callers can
        treat every component uniformly rather than special-casing this one,
        but it supplies nothing because there is nothing to supply."""
        return {}

    def validate(self) -> None:
        if self.L_pipe <= 0:
            raise GeometryRuleError(
                f'{self.code}: L_pipe must be positive (got {self.L_pipe}). '
                'There is no natural default for a spacer length -- it is set '
                'by the layout, not by the pipe diameter -- so one must be '
                'supplied. A zero-length segment is not a short spacer; it is '
                'the direct mate it was written to replace.')

    @property
    def extent(self) -> tuple[float, float]:
        return (self.centre_x - self.L_pipe / 2, self.centre_x + self.L_pipe / 2)

    @property
    def _section(self) -> 'Section':
        """The pipe's OWN section, unmodified. Not a computed variant."""
        return Section(OD=self.pipe.OD_pipe, t=self.pipe.t_pipe, owner=self.code)

    @property
    def _node_ids(self) -> tuple:
        t = f'{self.code}@{self.centre_x:+.4f}'
        return (f'{t}:weldL', f'{t}:weldR')

    @property
    def _owns_contact(self) -> bool:
        """True here; overridden False on the branch subclass."""
        return True

    def geometry_nodes(self) -> list:
        x_lo, x_hi = self.extent
        y = self.pipe.OD_pipe / 2
        nL, nR = self._node_ids
        return [GeometryNode(nL, x_lo, y, NodePriority.MANDATORY),
                GeometryNode(nR, x_hi, y, NodePriority.MANDATORY)]

    def structural_nodes(self) -> list:
        """MANDATORY at both ends: these are girth welds, and if a
        neighbouring component's section differs they are also section
        discontinuities the mesher must not smear."""
        x_lo, x_hi = self.extent
        nL, nR = self._node_ids
        return [StructuralNode(nL, x_lo, 0.0, NodePriority.MANDATORY),
                StructuralNode(nR, x_hi, 0.0, NodePriority.MANDATORY)]

    def geometry_lines(self) -> list:
        return [GeometryLine(
            line_id=PIPELINE_GEOMETRY_LINE_ID,
            node_ids=self._node_ids,
            structural_line_id=PIPELINE_STRUCTURAL_LINE_ID,
            owns_contact=self._owns_contact,
            contact_advice=ContactAdvice(
                normal_is_collinear_with_offset=True,
                requires_node_at_contact=False,
                note='Plain pipe: concentric, normal radial through the '
                      'neutral axis, moment zero. This is the baseline '
                      'contact case every other component is compared to.'))]

    def structural_lines(self) -> list:
        return [StructuralLine(
            line_id=PIPELINE_STRUCTURAL_LINE_ID,
            node_ids=self._node_ids,
            section=self._section)]

    def section_at(self, x: float) -> Optional['Section']:
        if not self.owns(x):
            return None
        return self._section

    def contact_at(self, x: float) -> Optional['Contact']:
        if not self.owns(x) or not self._owns_contact:
            return None
        y = self.pipe.OD_pipe / 2
        return Contact(y=y, owner=self.code, load_path=LoadPath.PIPE_ELEMENT,
                        arm=abs(y))


@dataclass(frozen=True)
class BranchPipeSegment(HeaderPipeSegment):
    """A plain length of BRANCH pipe. Identical to HeaderPipeSegment in
    every respect except that it never owns roller contact.

    SUBCLASSED RATHER THAN DUPLICATED, deliberately. The two differ in
    exactly one behaviour, and that difference is arguably a fact about
    which LINE the segment sits on rather than about the segment itself --
    a branch rises away from the rollers, so nothing on it can be touched.
    Expressing that as a one-property override makes the relationship
    visible; two parallel classes would hide it.

    The pipe's OD/wall come from the `pipe` argument as always, so a branch
    segment is built by passing the BRANCH's BasePipeline, not the header's.
    """
    code: str = field(init=False, default='GD-BrPipe')

    @property
    def _owns_contact(self) -> bool:
        """False: the branch rises away from the rollers. Same categorical
        reason BranchPiping's own segments report owns_contact=False."""
        return False


# ===========================================================================
# Connector [GD-Con]
# ===========================================================================

@dataclass(frozen=True)
class Connector(Component):
    """The two-node element a connection is physically made BY.

    Previously implicit: the element existed only as a 5-tuple emitted by
    TopStructure/BaseStructure.active_connectors() and assembled by whoever
    consumed it, which made it look like a property of the structure. It is
    not -- it belongs to neither end.

    ZERO LENGTH IS LEGAL, and is the default. A connector at y_struct=0 is
    genuinely zero-length and still transfers force with a real DOF
    signature; it simply has no extent. This is why stiffness is an
    OVERRIDE and must never be derived from length: a derivation would be
    undefined at exactly this legal case.

    SIGN CONVENTION. `y_struct` is the SIGNED position of the structure-side
    node in y-positive-down, matching TopStructure/BaseStructure's P_vt --
    negative is above the pipe centreline, positive below. The magnitude
    |y_struct| is the connector's length, exposed as `L_conn`. Length is
    derived from position rather than the reverse because a bare magnitude
    could not say which side of the pipe the structure is on, and both
    sides are real (GD-ST above, GD-SB below).
    """
    conn_type: str = 'F'                 # F / P / S / D / W
    y_struct: float = 0.0                # m, SIGNED, y-positive-down
    k_axial: float = 1.0e9               # N/m,     preset stiff
    k_shear: float = 1.0e9               # N/m,     preset stiff
    k_rot: float = 1.0e9                 # N.m/rad, preset stiff
    P_gap: Optional[float] = None        # m, D only -- deadband free travel

    code: str = field(init=False, default='GD-Con')
    iw_ea_class: tuple = field(init=False, default=('EA-O',))

    @classmethod
    def default_for(cls, pipe: BasePipeline) -> dict:
        """Empty: nothing about a connector scales with pipe size. The
        stiffnesses are absolute presets, not ratios, and the length is set
        by the structure it serves."""
        return {}

    def validate(self) -> None:
        if self.conn_type not in CONNECTOR_OAM_CLASS:
            # Read off the OAM class map, NOT the similarly-named
            # VALID_CONNECTOR_TYPES -- see the note at CONNECTOR_OAM_CLASS.
            raise GeometryRuleError(
                f'{self.code}: conn_type must be one of '
                f'{sorted(CONNECTOR_OAM_CLASS)}, got {self.conn_type!r}')
        if self.P_gap is not None:
            if self.conn_type != 'D':
                raise GeometryRuleError(
                    f'{self.code}: P_gap is only meaningful for a D '
                    f'(intermittent) connector, but conn_type is '
                    f'{self.conn_type!r}. A deadband on a connector that is '
                    'always engaged would be silently ignored.')
            if self.P_gap <= 0:
                raise GeometryRuleError(
                    f'{self.code}: P_gap must be positive if set -- a zero '
                    'gap is a FIXED connector, which is a different type '
                    '(F), not a D that happens to shut immediately.')
        if self.conn_type == 'D' and self.P_gap is None:
            raise GeometryRuleError(
                f'{self.code}: a D connector requires P_gap -- the deadband '
                'is what makes it intermittent. Without it the connector '
                'would mesh as though always engaged, which is an F.')
        if min(self.k_axial, self.k_shear, self.k_rot) <= 0:
            raise GeometryRuleError(
                f'{self.code}: stiffnesses must be positive.')

    # --- derived -----------------------------------------------------------
    @property
    def L_conn(self) -> float:
        """Connector length: the MAGNITUDE of the structure-side offset.
        Zero is legal -- see class docstring."""
        return abs(self.y_struct)

    @property
    def oam_class(self) -> str:
        """The OAM ArtifactAssociation subclass this connector realises.
        F and W both map to FixedConnection -- they share a DOF signature
        but are different joints (a fixed attachment versus a girth weld),
        which is why they are separate connector types here."""
        return CONNECTOR_OAM_CLASS[self.conn_type]

    @property
    def extent(self) -> tuple[float, float]:
        """A connector occupies no span along the pipeline: it is a
        transverse element at a single station."""
        return (self.centre_x, self.centre_x)

    @property
    def _node_ids(self) -> tuple:
        t = f'{self.code}@{self.centre_x:+.4f}'
        return (f'{t}:pipeEnd', f'{t}:structEnd')

    def geometry_nodes(self) -> list:
        """Both MANDATORY. Not because either is a section discontinuity --
        neither is -- but because a connector node the mesher merged away
        or moved would silently delete the connection it carries."""
        nP, nS = self._node_ids
        return [GeometryNode(nP, self.centre_x, 0.0, NodePriority.MANDATORY),
                GeometryNode(nS, self.centre_x, self.y_struct,
                              NodePriority.MANDATORY)]

    def structural_nodes(self) -> list:
        nP, nS = self._node_ids
        return [StructuralNode(nP, self.centre_x, 0.0, NodePriority.MANDATORY),
                StructuralNode(nS, self.centre_x, self.y_struct,
                                NodePriority.MANDATORY)]

    def geometry_lines(self) -> list:
        """Owns NO contact: a connector is not a roller-bearing surface
        under any configuration."""
        t = f'{self.code}@{self.centre_x:+.4f}'
        return [GeometryLine(
            line_id=f'{t}:conn',
            node_ids=self._node_ids,
            structural_line_id=f'{t}:conn',
            owns_contact=False,
            contact_advice=ContactAdvice(
                normal_is_collinear_with_offset=True,
                requires_node_at_contact=False,
                note='Connector element -- not a contact surface.'))]

    def structural_lines(self) -> list:
        """Its OWN line, not the pipeline's: a second member meeting the
        pipe at a node, which is what makes the pipe-side node a junction.

        Carries no Section and no stiffness_ratio. Its stiffness is an
        absolute override (k_axial/k_shear/k_rot), unlike GD-ST/GD-SB whose
        stiffness_ratio is a multiple of a plain pipe's -- there is no pipe
        here to take a ratio of.
        """
        t = f'{self.code}@{self.centre_x:+.4f}'
        return [StructuralLine(
            line_id=f'{t}:conn',
            node_ids=self._node_ids,
            section=None,
            stiffness_rule='connector_override',
            mesh_advice=MeshAdvice(
                min_elements=1, max_size_ratio=1.0,
                note='ONE element, never subdivided. The connector is a '
                      'discrete two-node spring, not a continuum to be '
                      'refined; and at y_struct=0 it is zero-length, where '
                      'subdivision is undefined.'))]

    def junctions(self) -> list:
        """The pipe-side node MUST merge onto the pipeline structural line.
        Declared, not left to coordinate coincidence -- the same rule every
        other junction in this module follows."""
        nP, _ = self._node_ids
        return [(nP, PIPELINE_STRUCTURAL_LINE_ID)]

    def section_at(self, x: float) -> Optional['Section']:
        """None always: a connector adds nothing to the pipe's section."""
        return None

    def contact_at(self, x: float) -> Optional['Contact']:
        """None always: never a contact surface."""
        return None

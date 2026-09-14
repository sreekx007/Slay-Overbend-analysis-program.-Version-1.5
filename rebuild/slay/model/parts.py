"""slay.model.parts -- the PART layer: named nodes that mean something.

The first of the two layers of node identity ruled in
`docs/modules/T3_assembly_spec.md` §2. A part node is a *named* point with a
physical meaning -- a weld, a body station, a connector end. A mesh node is
an integer index produced later by subdividing part elements.

WHY THE SPLIT EXISTS. Connectivity is carried here, by identity, and never by
position. Once that is true, two mesh nodes landing on the same spot are
harmless: they occupy separate rows of the stiffness matrix and are tied only
if something declares them tied. That is what lets `D/-/-/-/D` be rejected as
a mechanism rather than silently rescued by a coordinate coincidence.

THE MERGE RULE, in two halves:

  * WITHIN a pass, coincident part nodes merge, at `MERGE_TOL` = 0.01 m.
    The tolerance is there to avoid slivers -- a 5 mm element beside 800 mm
    neighbours is a conditioning problem and a grading violation for no
    physical gain. It is NOT what defines connectivity.

  * ACROSS passes, they never merge. The one exception is a DECLARED
    junction (`component.junctions()`), which is intent rather than
    coincidence -- GD-B's tee into the header is a real shared node and says
    so.

Verified before adoption: the closest DISTINCT pair of structural nodes
anywhere in the published set is 0.176 m (anchor TT-1to4, the shallowest
taper), across all 7 archetypes and all 35 buildable anchors. The tolerance
has a 17.6x margin before it could destroy a real feature.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

MERGE_TOL = 0.01          # m -- see the module docstring


class AssemblyError(Exception):
    """The parts do not describe a buildable model."""


# ---------------------------------------------------------------------------
# Part-level artifacts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PartNode:
    """A named point. `part_id` is the identity; position is description."""
    part_id: str
    x: float
    y: float
    pass_no: int              # 1, 2 or 3 -- which pass created it
    owners: tuple             # every component that claims this point
    is_weld: bool = False     # two or more owners met here

    @property
    def xy(self) -> tuple:
        return (self.x, self.y)


@dataclass(frozen=True)
class PartElement:
    """One segment between two part nodes, carrying its stiffness DESCRIPTION.

    The description, not the resolved numbers. Binding a section to a
    material is L5's work (`T3_model_spec.md` §2); this layer records which
    of the three forms `StructuralLine` allows was used, and passes it on.
    """
    line_id: str
    n1: str                   # part node id
    n2: str
    owner: str
    section: object = None
    stiffness_rule: Optional[str] = None
    stiffness_ratio: Optional[float] = None
    min_elements: int = 1
    target_elem_len: Optional[float] = None
    # connectors only -- see T3_assembly_spec.md section 8
    connector: Optional['ConnectorSpec'] = None


@dataclass(frozen=True)
class ConnectorSpec:
    """What a connector IS, for L5 to turn into stiffness.

    `stiffness` is deliberately a rule name rather than a number: T3 emits
    no physics. The rule is pass 4's, and it is ABSOLUTE --

        every connector's stiffness is that of a 1 x OD length of
        pipeline, whatever the connector's own length is

    -- so length never enters the stiffness at all. `length` is carried
    for geometry and reporting, never for stiffness.

    THIS IS WHY ZERO LENGTH IS NOT A SPECIAL CASE. A connector at
    y_struct = 0 is genuinely zero-length, is legal, and is the DEFAULT --
    ILS-EASB uses it. Under a length-derived stiffness that case would be
    undefined exactly where it is most needed; under this rule it is the
    same as every other connector.

    NOTE FOR L5, and it is not optional. The rule means the element's
    stiffness is PRESCRIBED, not derived from its geometry. `nlfea_v4`'s
    corotational element builds EA/L0 and EI/L0 from the node coordinates
    and divides by the deformed length, so a zero-length element makes it
    divide by zero -- observed, not predicted. Scaling the section by
    L/OD reproduces the rule for a non-zero length but is still a
    derivation and still breaks at the legal default, so it is not the
    answer. A prescribed-stiffness element type is.
    """
    conn_type: str            # F / W / P / S / D
    length: float             # m, |y_struct|; 0.0 is legal AND the default
    slot: int                 # which of the five Set-2 slots
    stiffness: str = '1xOD_pipeline'   # absolute: never length-derived


@dataclass(frozen=True)
class Association:
    """A declared tie between two part nodes, enforced by penalty constraint.

    `ties` is (local_x, local_y, rz) in the EA component's LOCAL frame --
    local x along the slope of the pipeline/IW the connector attaches to,
    local y perpendicular to it. The frame CO-ROTATES: the pipe slope runs
    0 deg to 32.4 deg across the stinger, so a globally-aligned constraint
    would end up 32 degrees wrong.

    `skewed` says whether this association needs the co-rotating frame at
    all. F and W tie everything, so their frame does not matter and they
    need none of the skewed-constraint machinery -- which is why F-only is
    buildable today.
    """
    node_a: str               # C<n>-P or C<n>-E
    node_b: str               # the pipeline/IW node, or the EA node
    conn_type: str
    ties: tuple               # (bool, bool, bool)
    gap: Optional[float] = None      # D only: the +/- deadband
    skewed: bool = False


# ---------------------------------------------------------------------------
# Joint kinematics -- T3_assembly_spec.md section 7
# ---------------------------------------------------------------------------

# (local x along the slope, local y perpendicular, rz). A `D` is a PURE
# SUPPORT: it restrains local x and rz in NEITHER state, and local y only
# once its deadband closes.
TIES_OPEN = {
    'F': (True,  True,  True),
    'W': (True,  True,  True),
    'P': (True,  True,  False),      # revolute -- rz free
    'S': (False, True,  False),      # slides along the slope, AND rz free
    'D': (False, False, False),      # pure support, gap open
}

# WHY `S` FREES rz -- corrected 14 Sep 2026, and the correction matters.
#
# It tied rz until an ILS-EAST run on PS showed the S connector carrying a
# PURE COUPLE: 338.79 kN.m with exactly zero shear. A slotted connection
# cannot do that. A bolt in a slot slides AND turns; restraining its rotation
# would need a moment couple the slot has no way to provide.
#
# So P and S are a PIN and a ROLLER -- both moment-free, differing only in
# whether the translation along the slot is released. PS is then the classic
# simply-supported pair and carries no moment in either connector, which is
# what a bolted structure should give.
#
# This reads against `component_spec`'s comment calling S a "prismatic pair",
# which in strict kinematics does lock rotation. That file is mirrored (G7),
# so the disagreement is noted rather than edited there.
#
# Adequacy survives it: under PS neither joint ties rz, so rotation is
# restrained by the COUPLE of two local-y ties at different x -- which is
# exactly how a pin and a roller restrain a beam. Checked against all six
# named systems.
TIES_SHUT = dict(TIES_OPEN, D=(False, True, False))

# F and W tie all three, so no local frame is needed. P frees only rz, which
# is frame-independent. S and D restrain one translation and not the other,
# which is the case that needs the co-rotating frame.
SKEWED = {'F': False, 'W': False, 'P': False, 'S': True, 'D': True}


def layout_is_adequate(types, slot_xs, ties=None) -> tuple:
    """Do these connectors restrain all three planar rigid-body DOF?

    Evaluated with every `D` treated as OPEN, which is the weakest state and
    the one the first solve increment meets. A support that holds nothing
    while open cannot hold a structure up on its own, so this is not a
    formality: `D/-/-/-/D` is legal to construct and singular in both states.

    Rotation counts as restrained either by a joint that ties rz, or by two
    or more joints tying local y at different x -- a couple.

    Returns (local_x, local_y, rz) as booleans.
    """
    ties = TIES_OPEN if ties is None else ties
    live = [(t, x) for t, x in zip(types, slot_xs) if t]
    tx = any(ties[t][0] for t, _ in live)
    ty = any(ties[t][1] for t, _ in live)
    rz = any(ties[t][2] for t, _ in live)
    if not rz:
        xs = {round(x, 6) for t, x in live if ties[t][1]}
        rz = len(xs) >= 2
    return (tx, ty, rz)


# ---------------------------------------------------------------------------
# The merge
# ---------------------------------------------------------------------------

class PartRegistry:
    """Part nodes, grouped by position WITHIN a pass and never across one.

    Each pass gets its own coordinate bucket. `add` in pass 2 cannot see
    pass 1's positions, which is the whole reason ILS-EASB's straddle stops
    welding itself to the pipe: GD-SB is a pass-2 component and the pipeline
    is pass 1, so the two never compare coordinates at all.
    """

    def __init__(self, tol: float = MERGE_TOL):
        self.tol = tol
        self._nodes: dict = {}          # part_id -> PartNode
        self._by_pass: dict = {}        # pass_no -> list[(x, y, part_id)]

    # -- lookup ----------------------------------------------------------
    def __len__(self):
        return len(self._nodes)

    def __contains__(self, part_id):
        return part_id in self._nodes

    def __getitem__(self, part_id) -> PartNode:
        return self._nodes[part_id]

    @property
    def nodes(self) -> dict:
        return dict(self._nodes)

    def find(self, x: float, y: float, pass_no: int) -> Optional[str]:
        """The part id at this position in this pass, or None."""
        best, best_r = None, self.tol
        for (px, py, pid) in self._by_pass.get(pass_no, ()):
            r = math.hypot(px - x, py - y)
            if r <= best_r:
                best, best_r = pid, r
        return best

    # -- construction ----------------------------------------------------
    def add(self, part_id: str, x: float, y: float, pass_no: int,
            owner: str) -> str:
        """Register a point, merging into an existing one if within tol.

        A group claimed by two or more owners is a WELD and is renamed to
        say so -- 'nodes at intersection of the components are welds', which
        falls out of the merge rather than needing a separate rule.
        """
        hit = self.find(x, y, pass_no)
        if hit is None:
            self._nodes[part_id] = PartNode(part_id, x, y, pass_no, (owner,))
            self._by_pass.setdefault(pass_no, []).append((x, y, part_id))
            return part_id

        old = self._nodes[hit]
        if owner in old.owners:
            return hit
        owners = old.owners + (owner,)
        merged = PartNode(old.part_id, old.x, old.y, old.pass_no, owners,
                          is_weld=True)
        self._nodes[hit] = merged
        return hit

    def rename_welds(self) -> dict:
        """Give every multi-owner node a W- id. Returns {old_id: new_id}."""
        remap = {}
        for pid, n in list(self._nodes.items()):
            if not n.is_weld or pid.startswith('W-'):
                continue
            new = 'W-' + pid.split('-', 1)[-1] if '-' in pid else 'W-' + pid
            while new in self._nodes or new in remap.values():
                new += "'"
            remap[pid] = new
        for old, new in remap.items():
            n = self._nodes.pop(old)
            self._nodes[new] = PartNode(new, n.x, n.y, n.pass_no, n.owners,
                                        n.is_weld)
            lst = self._by_pass[n.pass_no]
            for i, (x, y, pid) in enumerate(lst):
                if pid == old:
                    lst[i] = (x, y, new)
        return remap

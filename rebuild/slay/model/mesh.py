"""slay_mesh.py -- discretisation of structural lines into beam elements.

SCOPE. Turns a CONTINUOUS structural line plus a list of required stations
into NODES and ELEMENTS. Owns element sizing, grading and snapping. Owns
no geometry: every coordinate arrives as an argument or comes from a
`component_spec` accessor. Owns no stiffness: it reports what an element
IS (length, section, stiffness rule and ratio) and never what an element
is WORTH. `nlfea_v4` owns element formulation and stays the single source.

THE COORDINATE IS ARC LENGTH, `arc_len`. Distance along the polyline from
its first node, in metres, following the path. NOT a projection onto any
axis. The first draft of this module was parameterised on x and failed
three ways, all silently:

    GD-VLV stem       vertical   ->  0 elements, no error raised
    GD-BL riser       vertical   ->  0.8128 m of pipe vanished
    GD-SB frame sides SLOPED     ->  44.7% of true length, per side

The sloped case is the instructive one. Vertical members project to zero
and are at least obvious on inspection; a sloped member comes back
foreshortened, which is a plausible wrong number. Across the whole GD-SB
frame that was 11.0% of the structure quietly missing. In arc length
there is no orientation branch anywhere in this file: horizontal,
vertical, sloped and closed-loop members take the identical code path.

NAMING (item 17 -- frame in the name). `arc_*` ALWAYS means arc length
along THIS structural line, from its own first node. Position along the
STINGER arc -- item 16's R = 85 m locus -- is a different quantity and
always carries `stinger` in the name. The two coincide for the pipeline
and diverge for every component line: a GD-ST frame has an arc length of
its own that has nothing to do with the stinger.

WHAT IS DELIBERATELY ABSENT: ROLLERS. The old `_build_geometry` seeded
`epe` elements PER ROLLER SPAN, making contact geometry decide node
positions. Item 24 settled that contact never drives node placement --
sliding contact sits at a virtual point inside an element and distributes
to the bracketing nodes. Nothing here takes a roller argument, and that
is a design statement, not an omission.

GLOSSARY:
    arc_len, arc_lo, arc_hi   m. Position / element ends along the line.
    node_arcs                 m. Ascending arc positions of a line's nodes.
    target_len                m. Default element length where no segment
                              claims the interval.
    max_ratio                 dimensionless. Cap on ADJACENT element length
                              ratio. Closed loops check across the seam.
    min_len                   m. REPORTING threshold only. Item 12's 1 x OD
                              is a floor on the length used in the
                              STIFFNESS FORMULA, not on geometry, so this
                              module never refuses or merges a short
                              element -- it warns and moves on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import config


class NodeReason(str, Enum):
    """WHY a station is required. Not the same as NodePriority, which says
    WHETHER. The mesher needs both: it snaps on priority and MERGES ONLY ON
    JUNCTION. Coordinate coincidence is never a reason for anything."""
    SECTION = 'section'
    SLOPE = 'slope'
    JUNCTION = 'junction'
    MASS = 'mass'
    EXTENT = 'extent'


class PolylineError(Exception):
    pass


# ---------------------------------------------------------------------------
# Polyline -- the geometric input, one per structural line
# ---------------------------------------------------------------------------

@dataclass
class Polyline:
    """An ordered path through 2D, with cumulative arc length.

    `node_ids[i]` sits at `(xs[i], ys[i])` with `arcs[i]` of path behind
    it. For a CLOSED loop the first node is listed once and `total`
    includes the closing segment back to it.
    """
    line_id: str
    node_ids: list
    xs: list
    ys: list
    arcs: list
    closed: bool = False

    @property
    def total(self) -> float:
        return self.arcs[-1]

    def at(self, arc: float) -> tuple:
        """(x, y) at an arc position. Linear within the containing segment,
        which is exact -- every segment of every current component line is
        straight."""
        if self.closed:
            arc = arc % self.arcs[-1]
        arc = min(max(arc, self.arcs[0]), self.arcs[-1])
        for k in range(len(self.arcs) - 1):
            a0, a1 = self.arcs[k], self.arcs[k + 1]
            if a0 - 1e-12 <= arc <= a1 + 1e-12:
                t = 0.0 if a1 - a0 < 1e-15 else (arc - a0) / (a1 - a0)
                k1 = (k + 1) % len(self.xs)
                return (self.xs[k] + t * (self.xs[k1] - self.xs[k]),
                        self.ys[k] + t * (self.ys[k1] - self.ys[k]))
        return (self.xs[-1], self.ys[-1])


def polyline_of(component, line_id: str) -> Polyline:
    """Chain one component's segments for `line_id` into a Polyline.

    Contiguity and non-branching are ASSERTED, not assumed. Both hold for
    every component today -- verified across GD-TT, GD-ST, GD-SB, GD-VLV
    and GD-B -- but that is a property of the current code, not a promise
    the accessor makes. A branching line has no single arc coordinate at
    all, so it must fail loudly rather than produce a path that silently
    omits a limb."""
    coord = {n.node_id: (n.x, n.y) for n in component.structural_nodes()}
    segs = [tuple(sl.node_ids) for sl in component.structural_lines()
            if sl.line_id == line_id]
    if not segs:
        raise PolylineError(f'{component.code}: no segments for {line_id!r}')

    deg = {}
    for a, b in segs:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    branch = sorted(n for n, d in deg.items() if d > 2)
    if branch:
        raise PolylineError(
            f'{component.code}/{line_id}: node(s) {branch} have degree > 2. '
            f'A branching line has no single arc-length coordinate; split it '
            f'into separate line_ids joined by junctions().')
    for i in range(len(segs) - 1):
        if segs[i][1] != segs[i + 1][0]:
            raise PolylineError(
                f'{component.code}/{line_id}: segments are not listed in '
                f'contiguous order at index {i} ({segs[i][1]} != '
                f'{segs[i+1][0]}). Chaining by listed order would build a '
                f'path through the wrong nodes.')

    ids = [segs[0][0]] + [b for _, b in segs]
    closed = ids[0] == ids[-1]
    if closed:
        ids = ids[:-1]

    xs = [coord[i][0] for i in ids]
    ys = [coord[i][1] for i in ids]
    walk = list(zip(xs, ys)) + ([(xs[0], ys[0])] if closed else [])
    arcs, running = [0.0], 0.0
    for (x0, y0), (x1, y1) in zip(walk[:-1], walk[1:]):
        running += math.hypot(x1 - x0, y1 - y0)
        arcs.append(running)
    return Polyline(line_id=line_id, node_ids=ids, xs=xs, ys=ys,
                     arcs=arcs, closed=closed)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Station:
    arc_len: float
    mandatory: bool
    reason: NodeReason
    owner: str = ''
    node_id: str = ''


@dataclass(frozen=True)
class Segment:
    """One interval of a line, with the advice and attributes governing it.

    THE SEGMENT, NOT THE COMPONENT, CARRIES MESH ADVICE.
    `StructuralLine.mesh_advice` is per segment already, and GD-TT is why:
    its five segments ask for three different things -- min_elements=2 at
    0.063 m on each taper, no opinion on the NIB stubs or the body. A
    per-COMPONENT target cannot express that, and an earlier draft taking
    one global target silently produced ONE element across a taper that
    had explicitly asked for two. Silently ignoring min_elements is the
    failure item 24 exists to prevent.
    """
    arc_lo: float
    arc_hi: float
    min_elements: int = 1
    target_elem_len: Optional[float] = None
    owner: str = ''
    section: object = None
    stiffness_rule: Optional[str] = None
    stiffness_ratio: Optional[float] = None

    @property
    def length(self) -> float:
        return self.arc_hi - self.arc_lo


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class MeshNode:
    index: int
    arc_len: float
    x: float
    y: float
    station: Optional[Station] = None


@dataclass
class MeshElement:
    index: int
    line_id: str
    n_lo: int
    n_hi: int
    arc_lo: float
    arc_hi: float
    section: object = None
    stiffness_rule: Optional[str] = None
    stiffness_ratio: Optional[float] = None
    owner: str = ''

    @property
    def length(self) -> float:
        """TRUE geometric length. Item 12's 1 x OD floor is NOT applied
        here -- that floor governs the length substituted into the
        stiffness formula, and applying it to geometry would move nodes."""
        return self.arc_hi - self.arc_lo


@dataclass
class LineMesh:
    line_id: str
    polyline: Polyline
    nodes: list = field(default_factory=list)
    elements: list = field(default_factory=list)
    snapped: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    @property
    def node_arcs(self) -> list:
        """Ascending arc positions -- the array contact lookup binary
        searches. Replaces node-id arithmetic: with EA components there is
        no global ordering to be monotonic in, since a GD-ST portal doubles
        back in x and a GD-B branch leaves the pipe entirely."""
        return [n.arc_len for n in self.nodes]

    @property
    def lengths(self) -> list:
        return [e.length for e in self.elements]

    @property
    def n_elems(self) -> int:
        return len(self.elements)

    @property
    def max_adjacent_ratio(self) -> float:
        L = self.lengths
        if len(L) < 2:
            return 1.0
        pairs = list(zip(L[:-1], L[1:]))
        if self.polyline.closed:
            pairs.append((L[-1], L[0]))       # the seam is a real adjacency
        return max(max(a, b) / min(a, b) for a, b in pairs)

    def element_at(self, arc: float) -> Optional[MeshElement]:
        """The element containing an arc position. Contact uses this, then
        reads `n_lo`/`n_hi` off the connectivity -- so node NUMBERING is
        never load-bearing."""
        if self.polyline.closed:
            arc = arc % self.polyline.total
        for e in self.elements:
            if e.arc_lo - 1e-12 <= arc <= e.arc_hi + 1e-12:
                return e
        return None


# ---------------------------------------------------------------------------
# Meshing
# ---------------------------------------------------------------------------

def _dedupe(vals: list, tol: float) -> list:
    out = []
    for v in sorted(vals):
        if not out or abs(v - out[-1]) > tol:
            out.append(v)
    return out


def mesh_line(polyline: Polyline,
              stations: list,
              target_len: float,
              segments: Optional[list] = None,
              max_ratio: float = 2.0,
              min_len: Optional[float] = None,
              tol: float = 1e-6) -> LineMesh:
    """Seed, snap, then grade one structural line.

    ORDER MATTERS AND IS NOT ARBITRARY. Snapping happens BEFORE grading,
    because a mandatory station is a hard constraint and the graded sizes
    must be built around wherever it lands. Grading first and snapping into
    the result reproduces the old code's sliver: a snap point landing near
    an already-placed node leaves a 0.184 m fragment, documented as having
    made A2/R70 fail to converge outright and shifted A1/R70's peak by
    +30% on pure numerical artefact.

    The old fix was "snap wins, drop any regular node within half an
    element". That removes the sliver but leaves the SIZE JUMP -- the
    reason item 23 asked for grading instead. Here each interval between
    consecutive mandatory stations is meshed on its own terms, so no
    regular node is ever dropped: there are none until the mandatory ones
    are placed.
    """
    segments = segments or []
    warnings = []
    total = polyline.total

    hard = [s.arc_len for s in stations if s.mandatory]
    hard = [a for a in hard if -tol <= a <= total + tol]
    if polyline.closed:
        # arc 0 IS the seam node; total maps back onto it and must not
        # become a second node at the same place.
        hard = _dedupe([0.0] + [a % total for a in hard], tol)
        bounds = hard + [total]
    else:
        hard = _dedupe([0.0, total] + hard, tol)
        bounds = list(hard)

    for a, b in zip(bounds[:-1], bounds[1:]):
        if min_len is not None and b - a < min_len - tol:
            warnings.append(
                f'MANDATORY stations {a:.4f} and {b:.4f} are {b-a:.4f} m '
                f'apart, below min_len {min_len:.4f} m. Kept as-is -- the '
                f'mesher does not delete required nodes.')

    arcs = [bounds[0]]
    claims = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        seg = _claiming_segment(segments, a, b, tol, warnings)
        if seg is None:
            n = max(1, int(round((b - a) / target_len)))
        else:
            want = seg.target_elem_len or target_len
            n = max(seg.min_elements, int(round((b - a) / want)))
        for i in range(1, n + 1):
            arcs.append(a + i * (b - a) / n)
        claims.append((a, b, seg))

    arcs = _dedupe(arcs, tol)
    if polyline.closed:
        arcs = [a for a in arcs if a < total - tol]
    arcs = _grade(arcs, hard, total, polyline.closed, max_ratio, tol,
                   warnings)

    mesh = LineMesh(line_id=polyline.line_id, polyline=polyline,
                     warnings=warnings)
    _emit(mesh, arcs, total, polyline, claims, tol)

    for s in stations:
        if not s.mandatory:
            continue
        a = s.arc_len % total if polyline.closed else s.arc_len
        hit = [n.index for n in mesh.nodes if abs(n.arc_len - a) <= tol]
        if hit:
            mesh.snapped[round(s.arc_len, 9)] = hit[0]
            mesh.nodes[hit[0]].station = s
        elif -tol <= a <= total + tol:
            mesh.warnings.append(
                f'MANDATORY station arc {s.arc_len:.6f} ({s.node_id}) not '
                f'snapped')
    return mesh


def _claiming_segment(segments, a, b, tol, warnings):
    """The segment containing interval [a, b].

    Containment, not overlap: intervals run between consecutive MANDATORY
    stations and a segment's own ends are mandatory, so partial overlap
    means a station went missing. MULTIPLE claimants are REPORTED rather
    than resolved by list order -- an earlier draft returned the first
    match, so listing a GD-TP segment ahead of a GD-TT taper claim silently
    discarded the taper refinement.
    """
    hits = [s for s in segments if s.arc_lo - tol <= a and b <= s.arc_hi + tol]
    if len(hits) > 1:
        distinct = {(s.min_elements, s.target_elem_len) for s in hits}
        if len(distinct) > 1:
            warnings.append(
                f'interval {a:.4f}-{b:.4f} claimed by {len(hits)} segments '
                f'{sorted({s.owner for s in hits})} with differing advice; '
                f'using the most refined')
        hits = sorted(hits, key=lambda s: (s.target_elem_len or float('inf'),
                                            -s.min_elements))
    return hits[0] if hits else None


def _grade(arcs, hard, total, closed, max_ratio, tol, warnings):
    """Insert nodes until no ADJACENT pair exceeds `max_ratio`.

    GRADING MAY CROSS A MANDATORY STATION, which is the point of item 23.
    At GD-TT's defaults the graded run-up needs 0.882 m per side against
    0.250 m of NIB and 0.508 m of body half -- 2.016 m of graded zone
    against a 1.768 m component. It does not fit, so treating component
    boundaries as limits on REFINEMENT cannot satisfy min_elements and
    max_size_ratio together, and silently picks one.

    A mandatory station limits node REMOVAL, never node ADDITION. Nothing
    here can delete one: `hard` is re-inserted every pass.
    """
    for _ in range(200):
        edges = arcs + ([total] if closed else [])
        L = [b - a for a, b in zip(edges[:-1], edges[1:])]
        if len(L) < 2:
            return arcs
        pairs = [(i, L[i], L[i + 1]) for i in range(len(L) - 1)]
        if closed:
            pairs.append((len(L) - 1, L[-1], L[0]))
        worst, at, first_longer = 1.0, None, True
        for i, p, q in pairs:
            r = max(p, q) / min(p, q)
            if r > worst:
                worst, at, first_longer = r, i, p > q
        if worst <= max_ratio + 1e-9 or at is None:
            return arcs
        j = at if first_longer else (at + 1) % len(L)
        lo, hi = edges[j], edges[j + 1]
        arcs = _dedupe(arcs + [0.5 * (lo + hi)] + hard, tol)
        if closed:
            arcs = [a for a in arcs if a < total - tol]
    warnings.append('grading did not converge in 200 passes')
    return arcs


def _emit(mesh, arcs, total, polyline, claims, tol):
    for i, a in enumerate(arcs):
        x, y = polyline.at(a)
        mesh.nodes.append(MeshNode(index=i, arc_len=a, x=x, y=y))
    pairs = [(i, i + 1) for i in range(len(arcs) - 1)]
    ends = [arcs[i + 1] for i in range(len(arcs) - 1)]
    if polyline.closed:
        pairs.append((len(arcs) - 1, 0))     # seam element closes the loop
        ends.append(total)
    for k, ((lo_i, hi_i), arc_hi) in enumerate(zip(pairs, ends)):
        arc_lo = arcs[lo_i]
        mid = 0.5 * (arc_lo + arc_hi)
        seg = next((s for a, b, s in claims
                    if s is not None and a - tol <= mid <= b + tol), None)
        mesh.elements.append(MeshElement(
            index=k, line_id=polyline.line_id, n_lo=lo_i, n_hi=hi_i,
            arc_lo=arc_lo, arc_hi=arc_hi,
            section=getattr(seg, 'section', None),
            stiffness_rule=getattr(seg, 'stiffness_rule', None),
            stiffness_ratio=getattr(seg, 'stiffness_ratio', None),
            owner=getattr(seg, 'owner', '')))


# ---------------------------------------------------------------------------
# Collection -- the only place this module reads component_spec
# ---------------------------------------------------------------------------

def _arc_of(polyline: Polyline, node_id: str) -> Optional[float]:
    try:
        return polyline.arcs[polyline.node_ids.index(node_id)]
    except ValueError:
        return None


def stations_of(component, polyline: Polyline) -> list:
    """Required stations for one component on one line, in arc length.

    Reason inference is EXPLICIT rather than clever. A junction is whatever
    `junctions()` declares -- never a coordinate match.
    """
    from component_spec import NodePriority
    jn = {nid for nid, tgt in component.junctions()
          if tgt == polyline.line_id}
    out = []
    for n in component.structural_nodes():
        arc = _arc_of(polyline, n.node_id)
        if arc is None:
            continue
        if n.node_id in jn:
            reason = NodeReason.JUNCTION
        elif component.section_at(n.x) is not None:
            reason = NodeReason.SECTION
        else:
            reason = NodeReason.SLOPE
        out.append(Station(arc_len=arc,
                            mandatory=n.priority is NodePriority.MANDATORY,
                            reason=reason, owner=component.code,
                            node_id=n.node_id))
    return out


def segments_of(component, polyline: Polyline) -> list:
    """Per-segment MeshAdvice and attributes, in arc length."""
    out = []
    for sl in component.structural_lines():
        if sl.line_id != polyline.line_id:
            continue
        a, b = (_arc_of(polyline, i) for i in sl.node_ids)
        if a is None or b is None:
            continue
        lo, hi = (a, b) if a <= b else (b, a)
        adv = sl.mesh_advice
        out.append(Segment(arc_lo=lo, arc_hi=hi,
                            min_elements=adv.min_elements,
                            target_elem_len=adv.target_elem_len,
                            owner=component.code, section=sl.section,
                            stiffness_rule=sl.stiffness_rule,
                            stiffness_ratio=sl.stiffness_ratio))
    return out


def mesh_component(component, line_id: str, target_len: float,
                    max_ratio: float = 2.0,
                    min_len: Optional[float] = None) -> LineMesh:
    """Convenience: mesh ONE component's own line, standalone."""
    pl = polyline_of(component, line_id)
    return mesh_line(pl, stations_of(component, pl), target_len,
                      segments=segments_of(component, pl),
                      max_ratio=max_ratio, min_len=min_len)

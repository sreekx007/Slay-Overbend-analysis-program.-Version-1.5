"""slay.model.assemble -- the four-pass build. Scene (+ ILS) -> Model.

Implements `docs/modules/T3_assembly_spec.md`. Stage 1: F and W connectors,
which tie all three DOF and therefore need none of the co-rotating skewed
constraint machinery. Every one of the seven EDAS archetypes uses F.

THE COORDINATE FRAME. Model coordinates are `(s, y_offset)` and the meshed
pipe is STRAIGHT -- bending it onto the arc is what the solver computes
(`T3_model_spec.md` section 3). The ILS places with its local +x toward the
VESSEL, and `s` increases toward the STINGER, so

    s = s_centre - x_local          y_offset = y_local

which is the whole of the placement: a translation and the one sign flip that
already lives in `slay.scene.path`. There is no reflection to get wrong
because ILS-local +y is down and model +y_offset is down.

THE PASS STRUCTURE IS THE POINT. Merging happens WITHIN a pass and never
across one, which is what stops ILS-EASB's GD-SB -- seven of whose nodes sit
exactly on the pipe centreline at P_vt = 0 -- from silently welding itself
into the pipe wall. A tolerance could not have fixed that; a larger one makes
it worse.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Optional

import component_spec as cs
import config

from slay.model.mesh import (
    LineMesh,
    Polyline,
    Segment,
    Station,
    NodeReason,
    mesh_line,
)
from slay.model.parts import (
    Association,
    AssemblyError,
    ConnectorSpec,
    MERGE_TOL,
    PartElement,
    PartRegistry,
    SKEWED,
    TIES_OPEN,
    layout_is_adequate,
)

# Passes. Named rather than numbered at call sites so the boundary that
# matters -- 1/1b versus 2 -- is legible where it is relied on.
PASS_HEADER = 1        # pipeline + IW primary lines
PASS_IW_SEC = 2        # IW secondary lines (PIP outer, VLV stem, GD-B branch)
PASS_EA = 3            # GD-ST / GD-SB, around their arc
# The two connector ends are SEPARATE populations, not one. A zero-length
# connector puts both at the same point -- ILS-EASB's does -- and they must
# still be two nodes, because one associates with the pipe and the other with
# the EA structure and the penalty tie between them IS the connector. Giving
# them their own passes is what keeps them apart.
PASS_CONN_P = 4        # connector end nodes, pipe/IW side
PASS_CONN_E = 5        # connector end nodes, EA side

IW_CLASSES = {'IW-A', 'IW-P', 'IW-B'}
EA_CLASSES = {'EA-ST', 'EA-SB'}

# Stage 3 (14 Sep 2026): `P` joins `F`/`W`. A revolute frees rz and rz
# alone, which is FRAME-INDEPENDENT -- so P needs none of the co-rotating
# machinery `S` and `D` do, and the T3 staging table said so ("P (rz free --
# no skew, could come earlier)"). `slay/solve/` now applies the associations,
# so a P emitted here is a P enforced.
#
# `S` and `D` stay out. Both restrain ONE translation and not the other, so
# their rows belong in an axis that turns with the pipe slope -- 0 deg to
# 32.4 deg across the stinger. Every rig solved so far is horizontal, where
# local IS global exactly; that is a property of the rig, not of the code.
# G9 stands for them: refused, never approximated by F.
SUPPORTED_CONN_TYPES = {'F', 'W', 'P'}


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelNode:
    """A final, integer-indexed node. `part_id` is set when it came from one."""
    index: int
    s: float
    y: float
    part_id: Optional[str] = None


@dataclass(frozen=True)
class ModelElement:
    index: int
    n1: int
    n2: int
    line_id: str
    owner: str
    section: object = None
    stiffness_rule: Optional[str] = None
    stiffness_ratio: Optional[float] = None
    connector: Optional[ConnectorSpec] = None


@dataclass
class Model:
    """Flat nodes and elements, plus the declarations that join them."""
    nodes: list
    elements: list
    part_nodes: dict
    part_elements: list
    associations: list
    warnings: list = field(default_factory=list)

    # -- queries ---------------------------------------------------------
    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_elems(self) -> int:
        return len(self.elements)

    def line_ids(self) -> list:
        seen, out = set(), []
        for e in self.elements:
            if e.line_id not in seen:
                seen.add(e.line_id)
                out.append(e.line_id)
        return out

    def elements_of(self, line_id: str) -> list:
        return [e for e in self.elements if e.line_id == line_id]

    def owners(self) -> set:
        return {e.owner for e in self.elements}

    def node_of_part(self, part_id: str) -> int:
        return self._part_index[part_id]

    # -- integrity -------------------------------------------------------
    def assert_no_accidental_sharing(self) -> None:
        """Two nodes share an index only if one part node produced them.

        The other half of the old rule -- that coincidence must imply a
        declared junction -- is gone, and deliberately: coincidence now
        carries no meaning at all. What remains worth asserting is that
        every node index traces back to exactly one part node or to one
        element's own subdivision.
        """
        seen = {}
        for n in self.nodes:
            if n.part_id is None:
                continue
            if n.part_id in seen:
                raise AssemblyError(
                    f'part node {n.part_id!r} produced two model nodes '
                    f'({seen[n.part_id]} and {n.index})')
            seen[n.part_id] = n.index


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _short(code: str) -> str:
    """'GD-TT' -> 'GDTT'."""
    return code.replace('-', '').upper()


def _tag(code: str, cid: str) -> str:
    """The body-node prefix: short code plus the ILS's instance id.

    Verbose where the ILS names an instance after its own type ('GDTT-TT'),
    but unambiguous when it does not ('GDTP-TP2'), and the code stays visible
    either way -- a node id should say what it is part of without a lookup.
    """
    return f'{_short(code)}-{cid}'


def _chains(elements) -> list:
    """Order part elements of one line into walkable chains.

    Returns [(node_id_sequence, closed)]. A GD-ST frame is one closed loop; a
    header is one open chain. Anything branched raises, matching
    `polyline_of`'s assertion: a branched line has no single arc coordinate,
    so it must fail loudly rather than silently omit a limb.
    """
    adj: dict = {}
    for k, e in enumerate(elements):
        adj.setdefault(e.n1, []).append((e.n2, k))
        adj.setdefault(e.n2, []).append((e.n1, k))
    branched = sorted(n for n, v in adj.items() if len(v) > 2)
    if branched:
        raise AssemblyError(
            f'line {elements[0].line_id!r}: node(s) {branched} have degree > 2. '
            'Split into separate line_ids joined by a declared junction.')

    out, used = [], set()

    def walk(start):
        seq, cur = [start], start
        while True:
            nxt = [(n, k) for n, k in adj[cur] if k not in used]
            if not nxt:
                return seq
            n, k = nxt[0]
            used.add(k)
            seq.append(n)
            cur = n
            if cur == start:
                return seq

    for start in [n for n, v in adj.items() if len(v) == 1]:
        if any(k not in used for _, k in adj[start]):
            seq = walk(start)
            if len(seq) > 1:
                out.append((seq, False))
    for start in list(adj):                       # whatever is left is a loop
        if any(k not in used for _, k in adj[start]):
            seq = walk(start)
            closed = len(seq) > 2 and seq[0] == seq[-1]
            if len(seq) > 1:
                out.append((seq[:-1] if closed else seq, closed))
    if len(used) != len(elements):
        raise AssemblyError(
            f'line {elements[0].line_id!r}: {len(elements) - len(used)} '
            'element(s) could not be chained')
    return out


# ---------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------

def build_model(scene,
                ils=None,
                s_centre: float = 0.0,
                target_len: float = None,
                max_ratio: float = 2.0,
                merge_tol: float = MERGE_TOL,
                extra_stations=(),
                emit_unenforced_conn_types=frozenset()) -> Model:
    """Assemble one Model. See `docs/modules/T3_assembly_spec.md`.

    `scene` supplies the extent and the forced-elastic zone boundaries; `ils`
    is optional -- without one the result is plain pipe over the extent, which
    is the M1 case.

    `extra_stations` are arc positions an OUTSIDE layer requires a node at.
    Three of the four MANDATORY reasons are geometric and come from the
    component itself; the rest are external -- the elastic-zone boundary that
    Scene declares, and the point where a load or restraint acts, which the
    analysis declares. `nlfea_v4.JointLoad` names a node id, so a load with no
    node under it cannot be applied at all. `NodeReason` has no member for
    either (finding 4 of the test plan), so they arrive here as bare arc
    positions until it does.

    `emit_unenforced_conn_types` is a NARROW, OPT-IN widening of
    `SUPPORTED_CONN_TYPES`, and it is not a way around G9. What it buys is
    GEOMETRY ONLY: the connector nodes, the connector element and the
    declared `Association` -- its type, its tie pattern, its gap, its
    `skewed` flag. It buys no enforcement whatever, and every connector it
    lets through is recorded in `Model.warnings` saying so, because a
    caller that assembles the result with no deadband machinery and no
    co-rotating frame gets an F in all but name -- the exact substitution
    G9 forbids.

    So the caller takes the enforcement on, in full, and has to be able to
    show it did: the study that turns this on for `D` carries an active-set
    deadband and reports the engaged state of every D at every gap it runs.
    Default empty, so no existing caller's refusal changes.
    """
    target_len = (config.OD_MULTIPLE * config.OD_PIPE_DEF
                  if target_len is None else target_len)
    reg = PartRegistry(tol=merge_tol)
    part_elems: list = []
    assocs: list = []
    warnings: list = []

    comps = list(zip(ils.ids, ils.components)) if ils is not None else []

    def s_of(x_local: float) -> float:
        """ILS-local x (toward the vessel) -> model s (toward the stinger)."""
        return s_centre - x_local

    iw = [(cid, c) for cid, c in comps if set(c.iw_ea_class) & IW_CLASSES]
    ea = [(cid, c) for cid, c in comps if set(c.iw_ea_class) & EA_CLASSES]

    # -- pass 0: connector stations are known up front ---------------------
    # The connector ELEMENTS and associations are pass 3, but their pipe-side
    # stations must exist as header nodes before pass 1 meshes: a connector
    # transfers force into the pipe there, and a force must act at a node.
    # Collecting positions early is not the same as building connectors early.
    conn_stations = []
    for cid, c in ea:
        for (slot, x_slot, ctype, arm, _extra) in (ils.connectors_of(c) or []):
            conn_stations.append((s_of(x_slot), cid, slot))

    # Same reasoning for a DECLARED junction onto the header: GD-B's tee says
    # it shares a node with the pipeline, so the pipeline must have one there.
    # The declaration is what creates the station -- pass 1b then resolves the
    # tie into it, which is the one place a pass boundary is crossed.
    junc_stations = []
    for cid, c in iw:
        coord = {n.node_id: (n.x, n.y) for n in c.structural_nodes()}
        for nid, target in c.junctions():
            if target != 'pipeline' or nid not in coord:
                continue
            x, y = coord[nid]
            junc_stations.append((s_of(x), y, cid, _tail(nid)))

    # -- pass 1: header + IW primary lines ---------------------------------
    s_lo, s_hi = scene.extent
    reg.add('PIPE-LO', s_lo, 0.0, PASS_HEADER, 'pipeline')
    reg.add('PIPE-HI', s_hi, 0.0, PASS_HEADER, 'pipeline')
    for s_b in scene.elastic_zone_boundaries:
        reg.add(f'PIPE-EZ{s_b:+.3f}', s_b, 0.0, PASS_HEADER, 'pipeline')
    for (s_c, cid, slot) in conn_stations:
        reg.add(f'PIPE-C{cid}{slot}', s_c, 0.0, PASS_HEADER, 'pipeline')
    for (s_j, y_j, cid, tag) in junc_stations:
        reg.add(f'{cid}-{tag}', s_j, y_j, PASS_HEADER, cid)
    for k, s_x in enumerate(extra_stations):
        reg.add(f'PIPE-X{k}', float(s_x), 0.0, PASS_HEADER, 'pipeline')

    # Register every IW point on the header BEFORE building any element, so
    # welds are known by the time an element names an id.
    claimed = []
    for cid, c in iw:
        coord = {n.node_id: (n.x, n.y) for n in c.structural_nodes()}
        for sl in c.structural_lines():
            if sl.line_id != 'pipeline':
                continue
            ids = [reg.add(f'{_tag(c.code, cid)}-{_tail(nid)}',
                           s_of(coord[nid][0]), coord[nid][1],
                           PASS_HEADER, cid)
                   for nid in sl.node_ids]
            claimed.append((ids, sl, cid))
            part_elems.append(PartElement(
                line_id='pipeline', n1=ids[0], n2=ids[1], owner=cid,
                section=sl.section, stiffness_rule=sl.stiffness_rule,
                stiffness_ratio=sl.stiffness_ratio,
                min_elements=sl.mesh_advice.min_elements,
                target_elem_len=sl.mesh_advice.target_elem_len))

    # Plain pipe fills every gap between the claimed spans and the extent ends.
    covered = [(min(reg[a].x, reg[b].x), max(reg[a].x, reg[b].x))
               for ids, _, _ in claimed for a, b in [ids]]
    header_nodes = sorted(
        (n for n in reg.nodes.values() if n.pass_no == PASS_HEADER),
        key=lambda n: n.x)
    for a, b in zip(header_nodes[:-1], header_nodes[1:]):
        mid = 0.5 * (a.x + b.x)
        if any(lo - 1e-9 <= mid <= hi + 1e-9 for lo, hi in covered):
            continue
        part_elems.append(PartElement(line_id='pipeline', n1=a.part_id,
                                      n2=b.part_id, owner='pipeline'))

    # -- pass 1b: IW secondary lines ---------------------------------------
    for cid, c in iw:
        coord = {n.node_id: (n.x, n.y) for n in c.structural_nodes()}
        junc = {nid for nid, _tgt in c.junctions()}
        for sl in c.structural_lines():
            if sl.line_id == 'pipeline':
                continue
            ids = []
            for nid in sl.node_ids:
                x, y = coord[nid]
                if nid in junc:
                    # A DECLARED junction -- intent, not coincidence. The one
                    # place a pass boundary is crossed, and it is crossed
                    # because something said so.
                    hit = reg.find(s_of(x), y, PASS_HEADER)
                    if hit is None:
                        raise AssemblyError(
                            f'{cid}: junction {nid!r} declares a tie to the '
                            f'header at s={s_of(x):.4f}, but no header node '
                            f'lies within {merge_tol} m of it')
                    ids.append(hit)
                else:
                    ids.append(reg.add(f'{_tag(c.code, cid)}-{_tail(nid)}',
                                       s_of(x), y, PASS_IW_SEC, cid))
            part_elems.append(PartElement(
                line_id=f'{cid}:{sl.line_id}', n1=ids[0], n2=ids[1], owner=cid,
                section=sl.section, stiffness_rule=sl.stiffness_rule,
                stiffness_ratio=sl.stiffness_ratio,
                min_elements=sl.mesh_advice.min_elements,
                target_elem_len=sl.mesh_advice.target_elem_len))

    # -- pass 2: the external structures -----------------------------------
    for cid, c in ea:
        coord = {n.node_id: (n.x, n.y) for n in c.structural_nodes()}
        for sl in c.structural_lines():
            ids = [reg.add(f'{_tag(c.code, cid)}-{_tail(nid)}',
                           s_of(coord[nid][0]), coord[nid][1], PASS_EA, cid)
                   for nid in sl.node_ids]
            part_elems.append(PartElement(
                line_id=f'{cid}:{sl.line_id}', n1=ids[0], n2=ids[1], owner=cid,
                section=sl.section, stiffness_rule=sl.stiffness_rule,
                stiffness_ratio=sl.stiffness_ratio,
                min_elements=sl.mesh_advice.min_elements,
                target_elem_len=sl.mesh_advice.target_elem_len))

    # -- passes 3 and 4: connectors ----------------------------------------
    for cid, c in ea:
        conns = ils.connectors_of(c) or []
        if not conns:
            continue
        _check_layout(cid, [t for (_s, _x, t, _a, _e) in conns],
                      [x for (_s, x, _t, _a, _e) in conns])

        for (slot, x_slot, ctype, arm, gap) in conns:
            if ctype not in SUPPORTED_CONN_TYPES:
                if ctype not in emit_unenforced_conn_types:
                    raise AssemblyError(
                        f'{cid}: connector type {ctype!r} at slot {slot} '
                        f'is not implemented. G9 -- a P/S/D case is '
                        f'refused, never approximated by F. Supported: '
                        f'{sorted(SUPPORTED_CONN_TYPES)}')
                warnings.append(
                    f'{cid} slot {slot}: {ctype!r} emitted as GEOMETRY '
                    f'ONLY (emit_unenforced_conn_types). This layer does '
                    f'not enforce it -- the caller must, or it is an F in '
                    f'all but name, which is what G9 forbids.')
            s_c = s_of(x_slot)
            y_struct = _y_struct(c, arm)

            pipe_node = reg.find(s_c, 0.0, PASS_HEADER)
            ea_node = reg.find(s_c, y_struct, PASS_EA)
            if pipe_node is None:
                raise AssemblyError(
                    f'{cid} slot {slot}: no header node at s={s_c:.4f}')
            if ea_node is None:
                raise AssemblyError(
                    f'{cid} slot {slot}: no {cid} node at '
                    f'(s={s_c:.4f}, y={y_struct:.4f})')

            p_id = reg.add(f'C{cid}{slot}-P', s_c, 0.0, PASS_CONN_P, cid)
            e_id = reg.add(f'C{cid}{slot}-E', s_c, y_struct, PASS_CONN_E, cid)

            # The pipe side is always all-DOF, whatever the joint type is.
            assocs.append(Association(p_id, pipe_node, 'W', (True, True, True)))
            assocs.append(Association(e_id, ea_node, ctype, TIES_OPEN[ctype],
                                      gap=gap, skewed=SKEWED[ctype]))

            # ALWAYS an element, zero length included. Its stiffness is that
            # of a 1 x OD length of pipeline whatever its own length is, so
            # length never enters the stiffness at all and there is nothing
            # for a zero-length case to be undefined about. That is the whole
            # reason pass 4's rule is not length-derived -- zero length is
            # legal and is the DEFAULT, and ILS-EASB uses it.
            part_elems.append(PartElement(
                line_id=f'{cid}:connector{slot}', n1=p_id, n2=e_id,
                owner='GD-Con',
                connector=ConnectorSpec(conn_type=ctype,
                                        length=abs(y_struct), slot=slot)))

    # -- welds, named last -------------------------------------------------
    # A point claimed by two or more owners is a weld. Renaming happens once,
    # after every pass, so no element can hold a stale id.
    remap = reg.rename_welds()
    if remap:
        part_elems = [_remap_elem(e, remap) for e in part_elems]
        assocs = [_remap_assoc(a, remap) for a in assocs]

    # -- mesh each part element, then issue the final numbers ---------------
    return _mesh_and_number(reg, part_elems, assocs, warnings,
                            target_len, max_ratio)


def _remap_elem(e, remap):
    if e.n1 not in remap and e.n2 not in remap:
        return e
    return dataclasses.replace(e, n1=remap.get(e.n1, e.n1),
                               n2=remap.get(e.n2, e.n2))


def _remap_assoc(a, remap):
    if a.node_a not in remap and a.node_b not in remap:
        return a
    return dataclasses.replace(a, node_a=remap.get(a.node_a, a.node_a),
                               node_b=remap.get(a.node_b, a.node_b))


def _tail(node_id: str) -> str:
    """'GD-ST@+1.2192:sslot3' -> 'sslot3'."""
    return node_id.split(':')[-1]


def _y_struct(component, arm: float) -> float:
    """Signed structure-side offset. `arm` is a magnitude; P_vt carries sign."""
    p_vt = getattr(component, 'P_vt', None)
    if p_vt is None or abs(p_vt) < 1e-12:
        return 0.0 if abs(arm) < 1e-12 else math.copysign(arm, -1.0)
    return math.copysign(abs(arm), p_vt)


def _check_layout(cid: str, types, slot_xs) -> None:
    """A connector layout must restrain all three planar rigid-body DOF.

    Evaluated with every `D` OPEN -- the weakest state, and the one the first
    solve increment meets. Refused, not rescued: quietly stiffening an
    inadequate layout would answer a different question, which is what G9
    exists to prevent.
    """
    tx, ty, rz = layout_is_adequate(types, slot_xs)
    if tx and ty and rz:
        return
    missing = [n for n, ok in (('local x', tx), ('local y', ty), ('rz', rz))
               if not ok]
    raise AssemblyError(
        f'{cid}: connector layout {"/".join(t or "-" for t in types)} leaves '
        f'{", ".join(missing)} unrestrained with every D gap open. The '
        f'structure has a rigid-body mode and the first increment would meet '
        f'a singular matrix. Refused, not stiffened (G9).')


def _mesh_and_number(reg, part_elems, assocs, warnings, target_len, max_ratio):
    """Mesh each part element, then issue the final integer numbers."""
    nodes: list = []
    elements: list = []
    part_index: dict = {}

    def node_for_part(pid: str) -> int:
        if pid not in part_index:
            n = reg[pid]
            part_index[pid] = len(nodes)
            nodes.append(ModelNode(len(nodes), n.x, n.y, pid))
        return part_index[pid]

    # A connector NEVER goes through the line mesher. It is one element by
    # definition -- never subdivided -- and a zero-length one has no arc
    # coordinate for the mesher to work in. Routing it straight through is
    # what lets the stiffness rule stay independent of length.
    for e in (e for e in part_elems if e.connector is not None):
        elements.append(ModelElement(
            index=len(elements),
            n1=node_for_part(e.n1), n2=node_for_part(e.n2),
            line_id=e.line_id, owner=e.owner, connector=e.connector))

    by_line: dict = {}
    for e in part_elems:
        if e.connector is not None:
            continue
        by_line.setdefault(e.line_id, []).append(e)

    for line_id, elems in by_line.items():
        spec = {(e.n1, e.n2): e for e in elems}
        for seq, closed in _chains(elems):
            pl = Polyline(
                line_id=line_id,
                node_ids=list(seq),
                xs=[reg[p].x for p in seq],
                ys=[reg[p].y for p in seq],
                arcs=_cumulative(reg, seq, closed),
                closed=closed)
            stations = [Station(arc_len=a, mandatory=True,
                                reason=NodeReason.SECTION, owner='part',
                                node_id=p)
                        for p, a in zip(seq, pl.arcs)]
            segments = []
            walk = list(zip(seq, seq[1:] + ([seq[0]] if closed else [])))
            for k, (p, q) in enumerate(walk):
                e = spec.get((p, q)) or spec.get((q, p))
                if e is None:
                    continue
                segments.append(Segment(
                    arc_lo=pl.arcs[k], arc_hi=pl.arcs[k + 1],
                    min_elements=e.min_elements,
                    target_elem_len=e.target_elem_len,
                    owner=e.owner, section=e.section,
                    stiffness_rule=e.stiffness_rule,
                    stiffness_ratio=e.stiffness_ratio))

            lm = mesh_line(pl, stations, target_len, segments=segments,
                           max_ratio=max_ratio)
            warnings.extend(f'{line_id}: {w}' for w in lm.warnings)

            # Map the line mesh back onto final numbers. A node that IS a part
            # node reuses that part node's number -- which is how two lines
            # meeting at a declared junction stay joined. Interior subdivision
            # nodes are new and belong to this element alone.
            idx: dict = {}
            arc_of_part = {p: a for p, a in zip(seq, pl.arcs)}
            for mn in lm.nodes:
                hit = [p for p, a in arc_of_part.items()
                       if abs(a - mn.arc_len) <= 1e-9]
                if hit:
                    idx[mn.index] = node_for_part(hit[0])
                else:
                    idx[mn.index] = len(nodes)
                    x, y = pl.at(mn.arc_len)
                    nodes.append(ModelNode(len(nodes), x, y, None))
            for me in lm.elements:
                e = _owning(spec, seq, pl, me, closed)
                elements.append(ModelElement(
                    index=len(elements),
                    n1=idx[me.n_lo], n2=idx[me.n_hi],
                    line_id=line_id,
                    owner=e.owner if e else 'pipeline',
                    section=e.section if e else None,
                    stiffness_rule=e.stiffness_rule if e else None,
                    stiffness_ratio=e.stiffness_ratio if e else None,
                    connector=e.connector if e else None))

    # A zero-length connector contributes no element, so its two end nodes
    # would never be reached by the meshing loop -- but the penalty tie needs
    # a DOF row at each end, so they are real nodes and must be materialised.
    for a in assocs:
        node_for_part(a.node_a)
        node_for_part(a.node_b)

    orphans = sorted(set(reg.nodes) - set(part_index))
    if orphans:
        warnings.append(
            f'{len(orphans)} part node(s) carry neither an element nor an '
            f'association and were dropped: {orphans[:5]}')

    m = Model(nodes=nodes, elements=elements, part_nodes=reg.nodes,
              part_elements=part_elems, associations=assocs,
              warnings=warnings)
    m._part_index = part_index
    m.assert_no_accidental_sharing()
    return m


def _cumulative(reg, seq, closed) -> list:
    arcs, run = [0.0], 0.0
    walk = list(seq) + ([seq[0]] if closed else [])
    for a, b in zip(walk[:-1], walk[1:]):
        run += math.hypot(reg[b].x - reg[a].x, reg[b].y - reg[a].y)
        arcs.append(run)
    return arcs


def _owning(spec, seq, pl, me, closed):
    """Which part element contains this mesh element."""
    mid = 0.5 * (me.arc_lo + me.arc_hi)
    walk = list(zip(seq, seq[1:] + ([seq[0]] if closed else [])))
    for k, (p, q) in enumerate(walk):
        if pl.arcs[k] - 1e-9 <= mid <= pl.arcs[k + 1] + 1e-9:
            return spec.get((p, q)) or spec.get((q, p))
    return None

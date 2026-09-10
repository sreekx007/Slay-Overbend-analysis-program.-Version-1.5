"""ils_builder.py -- the design layer above component_spec.

Takes a structured ILS definition and produces validated `component_spec`
objects plus a canonical, round-trippable record of what was asked for.

WHAT THIS OWNS that no component can:
  * cross-component validation (a component validates its own numbers; only
    an assembly can check one component's number against another's)
  * aggregate properties (mass, CoG, extent)
  * the ILS-level connection system
  * the header pipeline the IW components need in order to exist at all
  * contact ownership policy

WHAT IT DOES NOT OWN: stingers, rollers, vessels, meshes, loads, solvers.
That ignorance is the point -- an ILS built here can be reviewed, plotted,
diffed, stored and optimised before any of those exist.

FRAME: ILS-LOCAL x, origin at the ILS reference point. `centre_x` in a
definition is measured from that origin, never from anything on a stinger.
The reason is `Component._tag`, which is f'{code}@{centre_x:+.4f}' -- node
identity encodes position, so under a global frame the same design at two
locations is two unrelated sets of node ids and nothing keyed on a node
survives being moved. SLAY Builder applies one offset at placement.

y is unaffected: positive-DOWN throughout (tracker item 26).

OMISSION IS LOAD-BEARING. A parameter absent from a definition tracks
`default_for` forever; a parameter written explicitly is pinned at that
value. These are different states and `to_json()` MUST preserve the
difference -- which is why the raw definition is kept verbatim rather than
reconstructed from the built objects. Rebuilding it would resolve every
default and silently pin the whole design.
"""

from __future__ import annotations

import dataclasses as dc
import json
import math
from dataclasses import dataclass, field
from typing import Optional

import config
import component_spec as cs

SCHEMA_VERSION = 1

CLS = {'GD-TP': cs.ThickPipeBody, 'GD-TT': cs.TaperedThickBody,
       'GD-SH': cs.OffsetShroud, 'GD-ST': cs.TopStructure,
       'GD-SB': cs.BaseStructure, 'GD-VLV': cs.Valve,
       'GD-B': cs.BranchPiping,
       # Added 1 Sep 2026. GD-PIP existed in component_spec and was
       # classified in EDES but was never registered here, so any
       # layout containing one was unbuildable -- not a validation
       # failure, an outright KeyError on lookup.
       'GD-PIP': cs.PipBulkhead,
       'GD-HdPipe': cs.HeaderPipeSegment,
       'GD-BrPipe': cs.BranchPipeSegment,
       'GD-Con': cs.Connector}

# Fields whose value is a name, not a number.
STR_FIELDS = {'variant', 'support_connector', 'provenance',
              # Added 1 Sep 2026 with GD-Con. Without it the float() coercion
              # below turns conn_type='F' into a ValueError, making the
              # connector unbuildable from a definition -- the same failure
              # mode SEQ_FIELDS was created to fix, for the same reason.
              'conn_type'}

# Component fields holding a SEQUENCE of positions rather than one number.
# Coercing every value with float() silently made these unreachable from a
# definition: `top_connector_x` is how a GD-ST says WHERE on its top edge a
# branch attaches, and an ILT cannot be written without it. JSON has no
# tuple, so a list arrives and is converted here -- the dataclass wants a
# tuple, and a list would compare unequal on round-trip.
SEQ_FIELDS = {'top_connector_x', 'left_connector_y', 'right_connector_y'}

# Components that take the ILS connection system. `active_connectors` is a
# METHOD taking the system as an argument -- nothing stores it -- so the
# ILS holds it and supplies it at query time. There is no second copy to
# drift, which is why this is better than passing it at construction.
EA_CODES = {'GD-ST', 'GD-SB'}

# Connection types an association may declare. Mirrors component_spec's
# CONNECTOR_OAM_CLASS keys; W (girth weld) is what an inline chain join is.
CONNECTOR_TYPES_EMITTABLE = {'F', 'P', 'S', 'D', 'W'}

# Components that expose a conMid attachment station a connector may land on.
# GD-HdPipe is deliberately ABSENT: it is plain line pipe and has no conMid,
# which is the whole reason a header must be split at every connection point.
CONNECTOR_HOST_CODES = {'GD-TP', 'GD-TT', 'GD-PIP', 'GD-BOSS'}

# Tolerance for 'these two parts touch'. Set to the precision a layout is
# realistically WRITTEN in (6 decimal places = 1e-6 m = 1 micron), not the
# precision floats are computed in. Used by weld_chain, unmated_gaps and the
# association coincidence check so all three agree -- when they disagreed, a
# layout could sit in the gap between them and pass every check while having
# no welds at all.
ADJACENCY_TOL = 1e-6

DEFAULT_HEADER_HALF = 7.0        # m -- one 14 m pipe joint, centred.
# Changed from 6.0 (a 12 m header) on 4 Sep 2026 by project decision: the
# header is a PIPE JOINT, and 14 m is the standard joint length, so the
# default should be one joint rather than a round number that matches no
# real deliverable.
HEADER_CLEAR_EACH_SIDE = 3.0     # m of plain pipe wanted beyond the widest
                                 # component, each side, before the header is
                                 # extended. Replaces a 2.1 m placeholder.


class ILSDefinitionError(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    severity: str                 # 'error' | 'warning' | 'info'
    where: str
    message: str

    def __str__(self):
        return f'[{self.severity.upper()}] {self.where}: {self.message}'


# ---------------------------------------------------------------------------
# Schema -- auto-derived, so it cannot drift from the dataclasses
# ---------------------------------------------------------------------------

def ils_schema() -> dict:
    """What a definition may contain. Derived from the dataclasses, never
    hand-maintained, so a new component field appears here the moment it
    exists. A parser reads THIS and imports nothing."""
    comps = {}
    for code, cls in CLS.items():
        props = {}
        for f in dc.fields(cls):
            if not f.init or f.name == 'pipe':
                continue
            props[f.name] = ('str' if f.name in STR_FIELDS
                             else 'array' if f.name in SEQ_FIELDS
                             else 'float')
        comps[code] = {'properties': props, 'required': ['centre_x']}
    return {
        'schema_version': SCHEMA_VERSION,
        'ils': {'name': 'str', 'frame': 'local',
                'connection_system': sorted(cs.NAMED_CONNECTION_SYSTEMS),
                'ownership': ['strict', 'lowest']},
        'header': {'half_length': 'float (omit for auto)'},
        'pipeline': {f.name: 'float' for f in dc.fields(cs.BasePipeline)
                      if f.init and f.name != 'provenance'} |
                     {'provenance': [p.name for p in cs.Provenance]},
        'components': comps,
    }


def defaults_for(code: str, pipe: cs.BasePipeline,
                  variant: str = 'L') -> dict:
    """READ-ONLY. For a caller whose input is relative ('20% thicker than
    standard') and therefore needs the default to compute against. The
    result must be written as an ABSOLUTE value, which correctly PINS it --
    'thicker than standard' does mean pin it.

    A parser must NOT call this to fill in values it was not asked to
    change. Doing so makes omission impossible to express and silently pins
    every parameter in the design."""
    cls = CLS[code]
    try:
        return dict(cls.default_for(pipe, variant) if code == 'GD-B'
                    else cls.default_for(pipe))
    except TypeError:
        return {}


# ---------------------------------------------------------------------------
# The ILS
# ---------------------------------------------------------------------------

@dataclass
class ILS:
    definition: dict                       # VERBATIM, omissions intact
    pipe: cs.BasePipeline
    components: list
    codes: list
    ids: list
    header_half: float
    header_auto: bool
    connection_system: Optional[str]
    ownership: cs.OwnershipPolicy
    findings: list = field(default_factory=list)

    # -- geometry -----------------------------------------------------
    @property
    def header(self) -> tuple:
        return (-self.header_half, self.header_half)

    @property
    def extent(self) -> tuple:
        if not self.components:
            return self.header
        return (min(c.extent[0] for c in self.components),
                max(c.extent[1] for c in self.components))

    @property
    def assembly(self) -> cs.Assembly:
        return cs.Assembly(pipe=self.pipe, components=self.components,
                            ownership=self.ownership)

    def connectors_of(self, component):
        """Active connectors under the ILS-LEVEL system.

        Never `component.active_connectors()` with its own default -- that
        is how a definition asking for F2 got drawn as F2D: the caller
        supplied a system the definition never named."""
        if component.code not in EA_CODES:
            return []
        if self.connection_system:
            return component.active_connectors(self.connection_system)
        return component.active_connectors()

    # -- validation ---------------------------------------------------
    def validate(self) -> list:
        """Cross-component checks. Each of these needs to see more than one
        component, which is why none of them can live in `component_spec`."""
        out = []
        lo, hi = self.header
        for cid, c in zip(self.ids, self.components):
            a, b = c.extent
            if a < lo - 1e-9 or b > hi + 1e-9:
                out.append(Finding('error', f'{cid}/{c.code}',
                    f'extent {a:.4f}..{b:.4f} m falls outside the header '
                    f'{lo:.4f}..{hi:.4f} m'))

        # GD-B's P_bc is documented as reaching the NEAREST EA-ST connection
        # point. BranchPiping validates it as a number and cannot know
        # whether such a point exists -- only an assembly can.
        sts = [c for c in self.components if c.code == 'GD-ST']
        for cid, c in zip(self.ids, self.components):
            if c.code != 'GD-B':
                continue
            if not sts:
                out.append(Finding('warning', f'{cid}/GD-B',
                    f'P_bc = {c.P_bc:.4f} m is defined as the distance to '
                    f'the nearest EA-ST connection point, but this ILS has '
                    f'no GD-ST'))
                continue
            # P_bc is a DISTANCE from the Tee to the NEAREST connection
            # point (Table V), not a signed offset in +x. The first version
            # of this check computed `centre_x + P_bc` and compared
            # positions, so a branch whose nearest connector lies to its
            # LEFT -- the normal layout in Fig. 25, where the Tee sits
            # between the two F connectors -- was reported as missing by
            # the full span. Compare distances.
            tee = c.centre_x
            slots = [x for st in sts
                     for _, x, _, _, _ in self.connectors_of(st)]
            if not slots:
                continue
            near = min(slots, key=lambda x: abs(x - tee))
            miss = abs(abs(near - tee) - c.P_bc)
            if miss > 1e-6:
                out.append(Finding(
                    'warning' if miss < 0.25 else 'error', f'{cid}/GD-B',
                    f'P_bc = {c.P_bc:.4f} m, but the nearest active GD-ST '
                    f'connector is {abs(near-tee):.4f} m from the Tee at '
                    f'x = {tee:.4f} (connector at {near:.4f}) -- out by '
                    f'{miss*1000:.0f} mm'))

        # Contact ambiguity and section overlap, surfaced HERE rather than
        # left to whoever first touches `.assembly`. Both raise from
        # component_spec, and raising at first-use means an ILS can be
        # built, reported and stored while carrying a fault that only
        # appears when something downstream happens to sample the wrong x.
        # A stored layout that raises on use is worse than one that refuses
        # to validate.
        lo_s, hi_s = self.extent
        n = 241
        for i in range(n):
            x = lo_s + (hi_s - lo_s) * i / (n - 1)
            try:
                self.assembly.contact_at(x)
            except Exception as e:
                out.append(Finding('error', 'contact',
                    f'{type(e).__name__} at x = {x:.4f}: {str(e).split(chr(10))[0][:200]}'))
                break
            try:
                self.assembly.section_at(x)
            except Exception as e:
                out.append(Finding('error', 'section',
                    f'{type(e).__name__} at x = {x:.4f}: {str(e).split(chr(10))[0][:200]}'))
                break

        # ACTIVE connectors must lie within their own component's extent.
        # This is an ASSEMBLY check, not a component one, and deliberately
        # so: P_c1/P_c2 place all five candidate slots, but WHICH are active
        # is the ILS-level connection system's choice, so a component
        # cannot know whether its overhanging slot is used. F2 leaves slots
        # 1 and 5 empty, so slots reaching past the ends are harmless there
        # and fatal under F2D.
        #
        # Live case: with P_c1 promoted to free, EA-ST F2 Case 2 (P_c1 =
        # 20 D) puts its two F connectors at +/-4.064 m on a structure
        # extending to +/-3.251 m -- attached 0.813 m beyond the frame that
        # is supposed to carry them. It built silently.
        for cid, c in zip(self.ids, self.components):
            if c.code not in EA_CODES:
                continue
            a, b = c.extent
            for slot, cx, ctype, _, _ in self.connectors_of(c):
                if a - 1e-9 <= cx <= b + 1e-9:
                    continue
                out.append(Finding('error', f'{cid}/{c.code}',
                    f'active {ctype} connector at slot {slot}, x = {cx:.4f} m '
                    f'lies OUTSIDE the component extent {a:.4f}..{b:.4f} m. '
                    f'Widen the structure or reduce P_c1/P_c2.'))

        # Every declared point mass must land on a node that exists.
        # `point_masses()` returns (node_id, mass) and nothing verifies the
        # id, so a renamed or mistyped node silently drops the mass from
        # any CoG computed over it -- and a CoG that quietly ignores 3 mT
        # on a cantilevered branch still looks like a CoG.
        _, missing = self.located_point_masses()
        for nid in missing:
            out.append(Finding('error', 'mass',
                f'point mass declared at node {nid!r}, which is not among '
                f'that component\'s structural nodes -- it would be '
                f'excluded from mass and CoG'))

        out.extend(self._check_associations())
        out.extend(self._check_header_chain())
        out.extend(self._check_connectors_modelled())
        out.extend(self._check_connector_landing())

        provs = {c.provenance for c in self.components} | {self.pipe.provenance}
        if len(provs) > 1:
            out.append(Finding('info', 'ils',
                'mixed provenance: ' +
                ', '.join(sorted(p.name for p in provs)) +
                ' -- the assembly is only as trustworthy as its weakest part'))
        return out


    # -- associations --------------------------------------------------
    def feature_xy(self, cid, feature):
        """(x, y) of a named AssemblyFeature on the component with this id.

        Features are resolved from the component's own geometry nodes by the
        suffix after the last ':' -- the same names EDES records in
        assemblyFeatures.slots (weldL, weldR, conMid, tee, end, pipeEnd,
        structEnd, slot1..slot5). Resolving from the live nodes rather than
        from a hard-coded table means a feature that does not actually exist
        cannot be referenced, however plausible its name.

        Returns None if the id or the feature is unknown; the caller reports
        it, because the two cases need different messages.
        """
        if cid not in self.ids:
            return None
        c = self.components[self.ids.index(cid)]
        # STRUCTURAL nodes, not geometry nodes. A geometry node sits on the
        # component's own contact SURFACE, so two inline components welded at
        # the same station legitimately differ in y by the section step --
        # comparing surface positions would report every real weld between
        # different ODs as a mismatch. The structural node is on the
        # centreline, which is where the members actually join.
        # Match the EDES-documented feature name against the live node id,
        # tolerating the 's' prefix some components put on structural nodes.
        # component_spec is INCONSISTENT here: ThickPipeBody/TaperedThickBody/
        # HeaderPipeSegment emit ':weldL', while Valve/TopStructure/
        # BranchPiping route theirs through _s_id() and emit ':sweldL',
        # ':stee', ':sright1'. EDES documents the unprefixed name in every
        # case, so a producer following EDES would fail to resolve a feature
        # on half the corpus. Accepting both makes the DOCUMENTED name
        # authoritative, which is the right way round -- the underlying
        # inconsistency should still be unified in component_spec.
        for n in c.structural_nodes():
            tail = n.node_id.rsplit(':', 1)[-1]
            if tail == feature or tail == 's' + feature:
                return (n.x, n.y)
        # GD-SH has no structural nodes at all (it owns no structural line),
        # so fall back to geometry for surface-only components.
        for n in c.geometry_nodes():
            if n.node_id.rsplit(':', 1)[-1] == feature:
                return (n.x, n.y)
        return None

    def features_of(self, cid):
        """Every feature name the component with this id actually exposes."""
        if cid not in self.ids:
            return []
        c = self.components[self.ids.index(cid)]
        names = [n.node_id.rsplit(':', 1)[-1] for n in c.structural_nodes()]
        names = names or [n.node_id.rsplit(':', 1)[-1] for n in c.geometry_nodes()]
        # Report the EDES-documented (unprefixed) form, so the error message
        # names what a producer should actually have written.
        return sorted({n[1:] if n.startswith('s') and len(n) > 1 else n
                        for n in names})

    def _check_associations(self) -> list:
        """Validate the definition's `associations` list, if it has one.

        WHY THIS EXISTS. Until 4 Sep 2026 a definition listed only its
        components; nothing recorded which feature mates to which. That left
        one failure completely silent: components placed too far apart build
        cleanly, because the gap is simply header pipe and no rule is broken.
        Overlap raised ContactAmbiguityError, so the error was only half
        caught -- crowding was loud, spacing was invisible.

        A declared Connection asserts that two features are AT THE SAME
        POINT, which is exactly the statement a gap violates. So checking
        coincidence turns the silent half into an error.

        Associations are OPTIONAL. A definition without them behaves as
        before -- this cannot retroactively invalidate the archetype
        library. But a definition that declares them gets them enforced.
        """
        out = []
        assocs = self.definition.get('associations')
        if not assocs:
            return out

        for i, a in enumerate(assocs):
            tag = f'associations[{i}]'
            kind = a.get('type')

            if kind == 'PositionOrientation':
                # Artifacts NOT physically connected -- a positional
                # constraint only, so there is no coincidence to check.
                # Verify the endpoints resolve and the datum is one we know.
                cid = (a.get('from') or {}).get('component')
                if cid not in self.ids:
                    out.append(Finding('error', tag,
                        f'unknown component id {cid!r}'))
                    continue
                datum = (a.get('to') or {}).get('datum')
                if datum != 'pipeline_centreline':
                    out.append(Finding('error', tag,
                        f'unsupported datum {datum!r} -- only '
                        "'pipeline_centreline' is defined"))
                continue

            if kind != 'Connection':
                out.append(Finding('error', tag,
                    f'unknown association type {kind!r} -- expected '
                    "'Connection' or 'PositionOrientation'"))
                continue

            ends = []
            bad = False
            for side in ('from', 'to'):
                ref = a.get(side) or {}
                cid, feat = ref.get('component'), ref.get('feature')
                if cid not in self.ids:
                    out.append(Finding('error', tag,
                        f'{side}: unknown component id {cid!r}'))
                    bad = True
                    continue
                xy = self.feature_xy(cid, feat)
                if xy is None:
                    out.append(Finding('error', tag,
                        f'{side}: component {cid!r} has no feature {feat!r} '
                        f'-- it exposes {sorted(set(self.features_of(cid)))}'))
                    bad = True
                    continue
                ends.append((cid, feat, xy))
            if bad or len(ends) != 2:
                continue

            (cid_a, fa, (xa, ya)), (cid_b, fb, (xb, yb)) = ends
            dx, dy = xb - xa, yb - ya
            if abs(dx) > ADJACENCY_TOL or abs(dy) > ADJACENCY_TOL:
                out.append(Finding('error', tag,
                    f'{cid_a}.{fa} and {cid_b}.{fb} are declared connected '
                    f'but do not coincide: they are {dx:+.4f} m apart in x '
                    f'and {dy:+.4f} m in y. A declared Connection asserts '
                    'the two features are at the same point.'))

            ctype = a.get('connection')
            if ctype is not None and ctype not in CONNECTOR_TYPES_EMITTABLE:
                out.append(Finding('error', tag,
                    f'connection type {ctype!r} is not one of '
                    f'{sorted(CONNECTOR_TYPES_EMITTABLE)}'))
        return out

    def unmated_gaps(self, tol=None) -> list:
        """Gaps AND small overlaps between consecutive INLINE component extents.

        Reported separately from validate() because a gap is not always
        wrong -- two components genuinely can sit apart with plain header
        pipe between them. It is only wrong when the layout MEANT them to be
        adjacent, and only a declared association can say that. This is the
        diagnostic for a caller who has not declared associations and wants
        to check placement anyway.
        """
        tol = ADJACENCY_TOL if tol is None else tol
        # INLINE components only. Everything else legitimately overlaps the
        # chain and must not be reported: edes:GD-SH nests OVER the run (it
        # claims contact but no section), and GD-ST/GD-SB/GD-Con/GD-B sit off
        # the pipeline axis. Including them reported a shroud spanning a
        # header segment as a 6 m 'overlap', which is exactly the arrangement
        # the shroud exists to make -- see edas:shared#/sectionVersusContact.
        spans = sorted((c.extent[0], c.extent[1], cid)
                        for cid, c in zip(self.ids, self.components)
                        if c.code in INLINE_CODES)
        out = []
        for (a0, a1, ida), (b0, b1, idb) in zip(spans, spans[1:]):
            g = b0 - a1
            # Report BOTH signs. A negative g is a small overlap, which was
            # previously invisible here: only positive gaps were listed, so a
            # rounding-induced overlap passed silently unless the contact
            # sampler happened to land in it. Both are placement errors and
            # both are worth naming.
            if abs(g) > tol:
                out.append((ida, idb, round(g, 9)))
        return out


    def _check_header_chain(self) -> list:
        """In CHAIN mode, the inline components ARE the header, so the run
        they cover must be continuous.

        WHY THIS EXISTS. Without it, declaring the header as GD-HdPipe
        segments changes nothing: the implicit header backfills any hole
        with plain pipe (owner='pipe'), so a gap between segments is valid,
        contributes mass, and raises nothing. VERIFIED 5Sep26 -- two
        segments with a deliberate 2 m hole built with zero findings and
        section_at returned the plain pipe section in the middle. That made
        GD-HdPipe decorative: it declared ownership of pipe that existed
        regardless, and the OAM 'cut and remove' argument was not honoured.

        In chain mode a hole is MISSING MATERIAL and is reported as an
        error. This is the whole difference between the two models, and it
        is why the mode is worth declaring rather than inferring: a layout
        that uses one GD-HdPipe as a spacer between two components is not
        claiming to tile the entire run, and should not be forced to.
        """
        out = []
        if (self.definition.get('ils', {}).get('header_model')
                or 'continuous') != 'chain':
            return out

        spans = sorted((c.extent[0], c.extent[1], cid)
                        for cid, c in zip(self.ids, self.components)
                        if c.code in INLINE_CODES)
        if not spans:
            out.append(Finding('error', 'header',
                "header_model='chain' but the layout has no inline components. "
                'In chain mode the inline components ARE the header; with none '
                'there is nothing to be the header.'))
            return out

        for (a0, a1, ida), (b0, b1, idb) in zip(spans, spans[1:]):
            gap = b0 - a1
            if gap > ADJACENCY_TOL:
                out.append(Finding('error', 'header',
                    f'{ida} ends at {a1:+.4f} and {idb} starts at {b0:+.4f}, '
                    f'leaving {gap:.4f} m of the run uncovered. Under '
                    "header_model='chain' the inline components ARE the "
                    'header, so an uncovered span is missing material, not '
                    'plain pipe. Insert a GD-HdPipe segment to close it, or '
                    "use header_model='continuous' if a continuous header "
                    'underneath is what was meant.'))
        return out


    def _check_connectors_modelled(self) -> list:
        """Warn when a structure declares connectors that nothing models.

        Setting ils.connection_system DECLARES which slots are populated; it
        does NOT create the connection. A GD-ST with connection_system='F2'
        and no GD-Con anywhere reports two active connectors that touch
        nothing -- they hang above a continuous header, and until 5 Sep 2026
        the layout built, plotted and validated with zero findings.

        OBSERVED that day: asked for EA-ST layouts across five connection
        systems, a model produced structures with no connectors at all and
        reported success. The reading was reasonable -- every archetype in
        standard_ils_layouts.json uses that simplified form, because they
        mirror published analysis models where the connector is a beam
        element rather than a modelled part.

        So this is a WARNING, not an error: the simplified form is legitimate
        for reproducing those studies. But it should never be silent, because
        the difference between 'connectors modelled' and 'connectors declared
        and floating' is invisible in every other output.
        """
        out = []
        system = self.definition.get('ils', {}).get('connection_system')
        if not system:
            return out
        n_con = sum(1 for c in self.components if c.code == 'GD-Con')
        declared = 0
        for c in self.components:
            if hasattr(c, 'active_connectors'):
                try:
                    declared += len(self.connectors_of(c))
                except Exception:
                    pass
        if declared and n_con == 0:
            out.append(Finding('warning', 'connectors',
                f"connection_system='{system}' populates {declared} slot(s), but the "
                'layout contains NO GD-Con parts, so nothing models where those '
                'connections meet the pipe. This is the SIMPLIFIED form used by the '
                'archetype library; a complete layout places a GD-Con at each slot, '
                'landing on a GD-TP, with associations at both ends -- see '
                'edas:shared#/connectorAttachment.twoModellingLevels.'))
        elif declared and n_con < declared:
            out.append(Finding('warning', 'connectors',
                f"connection_system='{system}' populates {declared} slot(s) but only "
                f'{n_con} GD-Con part(s) are present -- {declared - n_con} declared '
                'connection(s) are not modelled.'))
        return out


    def _check_connector_landing(self) -> list:
        """A connector's pipe end must land on a component that can take it.

        DNV prohibits welding a structural attachment onto line pipe, so a
        GD-Con's pipeEnd must coincide with a conMid feature on a thickened
        section (GD-TP / GD-TT / GD-PIP / GD-BOSS), never on plain header
        pipe or on a GD-HdPipe segment -- which deliberately has no conMid.

        WHY THIS EXISTS. The earlier connector check counts GD-Con parts
        against declared slots, so a layout with the right NUMBER of
        connectors satisfies it regardless of where they land. VERIFIED
        5Sep26: a GD-Con welded straight onto plain header pipe, with its
        structure association declared and no GD-TP anywhere, built with
        ZERO errors and ZERO warnings. The rule was stated in edas:shared
        and enforced nowhere, which is the prose-only failure mode this
        project keeps rediscovering.

        Reported as an ERROR, not a warning: unlike the simplified
        connection form (legitimate for reproducing published cases), there
        is no reading under which a structural attachment on bare line pipe
        is correct.
        """
        out = []
        cons = [(cid, c) for cid, c in zip(self.ids, self.components)
                if c.code == 'GD-Con']
        if not cons:
            return out
        hosts = {}
        for cid, c in zip(self.ids, self.components):
            if c.code in CONNECTOR_HOST_CODES:
                xy = self.feature_xy(cid, 'conMid')
                if xy is not None:
                    hosts[round(xy[0], 6)] = (cid, c.code)
        for cid, c in cons:
            x = round(c.centre_x, 6)
            hit = next((h for hx, h in hosts.items()
                        if abs(hx - x) <= ADJACENCY_TOL), None)
            if hit is None:
                out.append(Finding('error', 'connectors',
                    f'{cid} lands at x = {c.centre_x:+.4f} where no thickened '
                    'section offers a conMid feature. A connector may not '
                    'attach to plain line pipe: split the header there and '
                    'introduce a GD-TP (neutral, t_comp = t_pipe) centred on '
                    'the connection point, then declare '
                    f'TP.conMid --F-- {cid}.pipeEnd. See '
                    'edas:shared#/connectorAttachment.'))
        return out

    # -- aggregates ---------------------------------------------------
    def point_masses(self) -> list:
        out = []
        for c in self.components:
            if hasattr(c, 'point_masses'):
                out.extend(c.point_masses())
        return out

    @property
    def lumped_mass(self) -> float:
        return sum(m for _, m in self.point_masses())

    def located_point_masses(self) -> tuple:
        """((node_id, mass_kg, x, y), ...), (unresolved_node_id, ...)

        `point_masses()` returns (node_id, mass) and NO coordinates, so a
        CoG is impossible without resolving each id against the declaring
        component's own structural nodes. Anything that fails to resolve is
        returned separately rather than dropped -- a mass silently excluded
        from a CoG is worse than one reported as missing."""
        located, missing = [], []
        for c in self.components:
            if not hasattr(c, 'point_masses'):
                continue
            coords = {n.node_id: (n.x, n.y) for n in c.structural_nodes()}
            for nid, m in c.point_masses():
                if nid in coords:
                    x, y = coords[nid]
                    located.append((nid, m, x, y))
                else:
                    missing.append(nid)
        return tuple(located), tuple(missing)

    @staticmethod
    def _steel_area(sec) -> float:
        """A = pi/4 (OD^2 - ID^2). `Section` carries OD and t only and has
        no area property, so this is computed here rather than assumed to
        exist."""
        ID = sec.OD - 2.0 * sec.t
        return math.pi / 4.0 * (sec.OD ** 2 - ID ** 2)

    def _section_stations(self) -> list:
        """Integration breakpoints: header ends, every component extent
        bound, and every declared node station inside the header.

        `Assembly.section_at` is PIECEWISE and steps discontinuously at a
        component boundary (GD-TP's default jumps the wall from 21.0 to
        52.5 mm). Integrating across one would average the step and smear
        it. Surplus breakpoints cost only time -- each sub-interval is
        integrated exactly -- so every declared station is included rather
        than trying to guess which ones move the section."""
        lo, hi = self.header
        xs = {lo, hi}
        for c in self.components:
            for x in c.extent:
                if lo < x < hi:
                    xs.add(x)
            for getter in ('structural_nodes', 'geometry_nodes'):
                fn = getattr(c, getter, None)
                if fn is None:
                    continue
                for n in fn():
                    x = getattr(n, 'x', None)
                    if x is not None and lo < x < hi:
                        xs.add(x)
        return sorted(xs)

    def _distributed_steel(self, n_sub: int = 8) -> tuple:
        """(mass_kg, first moment about x=0) of the PIPE'S OWN steel across
        the header, integrated from `Assembly.section_at`.

        Density is `config.RHO_STEEL`, sourced not restated -- config.py
        owns it and a second literal here would be exactly the drift the
        file format rules exist to prevent.

        SIMPSON, and it is EXACT here rather than approximate. With
        ID = OD - 2t the area reduces to pi(OD*t - t^2); OD and t are each
        at worst LINEAR in x across a taper, so A(x) is at worst QUADRATIC,
        which Simpson integrates without error. Accuracy therefore comes
        from the breakpoints in `_section_stations`, not from n_sub.

        Endpoints are inset by eps so a sample never lands exactly on a
        boundary where two components could both claim the station. The
        discarded sliver is ~rho*A*2e-9 kg, i.e. below a microgram."""
        asm = self.assembly
        rho = config.RHO_STEEL
        eps = 1e-9
        stations = self._section_stations()
        n = n_sub + (n_sub % 2)                 # Simpson needs an even count
        mass = moment = 0.0
        for a, b in zip(stations[:-1], stations[1:]):
            if b - a <= 2 * eps:
                continue
            a2, b2 = a + eps, b - eps
            h = (b2 - a2) / n
            s_m = s_x = 0.0
            for i in range(n + 1):
                x = a2 + i * h
                w = 1 if i in (0, n) else (4 if i % 2 else 2)
                A = self._steel_area(asm.section_at(x))
                s_m += w * A
                s_x += w * A * x
            mass += s_m * h / 3.0 * rho
            moment += s_x * h / 3.0 * rho
        return mass, moment

    @property
    def mass(self) -> float:
        """Total REPRESENTABLE mass, kg. Read `mass_exclusions()` beside
        it: several components carry no mass parameter at all, so this is a
        floor, not the structure's real weight."""
        d, _ = self._distributed_steel()
        return d + self.lumped_mass

    @property
    def mass_breakdown(self) -> dict:
        d, _ = self._distributed_steel()
        return {'pipe_steel_kg': d, 'point_masses_kg': self.lumped_mass,
                'total_kg': d + self.lumped_mass}

    @property
    def cog(self) -> tuple:
        """(x, y) in ILS-LOCAL coordinates, y positive-DOWN.

        The pipe's own steel sits on the centreline and contributes y = 0,
        so any non-zero y comes entirely from located point masses. With no
        mass on GD-ST or GD-SB, a CoG for an ILS carrying one is the CoG of
        the PIPEWORK, not of the assembly -- which is why this must be read
        with `mass_exclusions()`."""
        d_m, d_mx = self._distributed_steel()
        located, _ = self.located_point_masses()
        m = d_m + sum(p[1] for p in located)
        if m <= 0:
            return (0.0, 0.0)
        mx = d_mx + sum(p[1] * p[2] for p in located)
        my = sum(p[1] * p[3] for p in located)      # pipe steel: y = 0
        return (mx / m, my / m)

    def mass_exclusions(self) -> list:
        """What the mass total CANNOT see, derived from what is actually
        present. Stated rather than defaulted away: a total that silently
        omits a top structure looks like a total."""
        out = []
        for cid, c in zip(self.ids, self.components):
            if c.code in EA_CODES:
                out.append(
                    f'{cid}/{c.code}: no mass parameter exists on this '
                    f'component, so its structural steel is NOT counted. It '
                    f'carries geometry and a stiffness RATIO only.')
            if c.code == 'GD-SH':
                out.append(
                    f'{cid}/GD-SH: section_at returns None by design '
                    f'(Sec.2.4 -- the shroud adds no material to the pipe '
                    f'cross-section), so shroud material is NOT counted.')
        out.append(
            'An ILS cannot express a mass belonging to no component, so a '
            'bare inertia on the header is not representable.')
        return out

    def modelling_boundaries(self) -> list:
        """Deliberate modelling choices that look like omissions to someone
        reading the JSON later. Both papers state them; neither is visible
        in the parameters themselves."""
        out = []
        ea = [c for c in self.components if c.code in EA_CODES]
        iwa = sorted({c.code for c in self.components
                      if c.code in ('GD-TP', 'GD-TT')})
        if ea:
            if iwa:
                out.append(
                    'IW-A PRESENT (' + ', '.join(iwa) + ') alongside an EA '
                    'structure. The published studies excluded bulkheads '
                    'deliberately, so the connection-layout effect could be '
                    'seen alone -- results here are NOT comparable with '
                    'those benchmarks.')
            else:
                out.append(
                    'No IW-A bulkhead present, matching the published '
                    'studies, which excluded them deliberately so the '
                    'connection-layout effect could be seen alone. Adding a '
                    'GD-TP or GD-TT at a connection point would invalidate '
                    'comparison with them.')
            out.append(
                'Connectors attach ON THE PIPE CENTRELINE: '
                'active_connectors() returns an axial station and a moment '
                'arm, carrying no offset from the pipe axis. Listed under '
                'Limitations in both studies.')
            for cid, c in zip(self.ids, self.components):
                if c.code == 'GD-SB':
                    out.append(
                        f'{cid}/GD-SB: P_vt = {c.P_vt:+.4f} m (signed '
                        f'position, y positive DOWN). The published EA-SB '
                        f'set used P_vt = 0 THROUGHOUT, against a non-zero '
                        f'default here -- so a defaulted GD-SB does not '
                        f'reproduce that set.')
                elif c.code == 'GD-ST':
                    out.append(
                        f'{cid}/GD-ST: P_vt = {c.P_vt:+.4f} m (signed '
                        f'position of the frame underside, y positive '
                        f'DOWN, negative = above the pipe centreline).')
        out.append(
            'Strain reported downstream from this layout is for RELATIVE '
            'comparison between arrangements, not absolute code compliance.')
        return out


    # -- artifacts ----------------------------------------------------
    def to_json(self, indent: int = 2) -> str:
        """The CANONICAL definition. Free parameters only, omissions intact.

        Emitted from `self.definition`, NOT rebuilt from the components --
        rebuilding resolves every default and pins the design at today's
        values."""
        doc = {'schema_version': SCHEMA_VERSION}
        doc.update(self.definition)
        return json.dumps(doc, indent=indent, sort_keys=False)

    def report(self) -> dict:
        """DERIVED values, for a human or an agent to read. Never consumed
        by any module -- keeping mass and CoG out of the definition is what
        stops them becoming a second source for something component_spec
        computes.

        `mass_exclusions` and `modelling_boundaries` travel WITH the
        numbers deliberately. A mass total that omits the top structure,
        or a benchmark layout whose missing bulkheads are load-bearing,
        is misread the moment it is separated from the statement of what
        it leaves out."""
        lo, hi = self.extent
        cx, cy = self.cog
        _, missing = self.located_point_masses()
        return {
            'name': self.definition.get('ils', {}).get('name'),
            'n_components': len(self.components),
            'codes': list(self.codes),
            'iw_ea_classes': sorted({k for c in self.components
                                      for k in c.iw_ea_class}),
            'header_m': list(self.header),
            'header_auto_sized': self.header_auto,
            'extent_m': [lo, hi],
            'span_m': hi - lo,
            'connection_system': self.connection_system,
            'ownership': self.ownership.value,
            'mass_kg': self.mass,
            'mass_breakdown_kg': self.mass_breakdown,
            'mass_is_a_floor': True,
            'mass_exclusions': self.mass_exclusions(),
            'unresolved_point_masses': list(missing),
            'cog_m': {'x': cx, 'y': cy, 'frame': 'ILS-local, y positive DOWN'},
            'lumped_mass_kg': self.lumped_mass,
            'modelling_boundaries': self.modelling_boundaries(),
            'findings': [str(f) for f in self.findings],
        }

    def parameters(self) -> list:
        """(owner, name, value) for every FREE parameter actually set.
        The optimisation / ML surface: a feature vector, not a figure."""
        out = []
        for cid, c in zip(self.ids, self.components):
            for f in dc.fields(c):
                if not f.init or f.name in ('pipe', 'provenance'):
                    continue
                out.append((f'{cid}/{c.code}', f.name, getattr(c, f.name)))
        return out

    def plot(self, path=None, **kw):
        """Lazy import -- an agent proposing designs headlessly must not
        drag in matplotlib to do it.

        Draws the ILS on its header only. Stinger, rollers and passage are
        SLAY-tier and belong to a SLAY-tier plotter: they are properties of
        a lay configuration, and an ILS exists so a design can be reviewed
        before one is chosen."""
        import ils_plotter
        return ils_plotter.plot_ils(self, path=path, **kw)

    def plot_component(self, which, path=None, **kw):
        """Detail view of ONE component, by index or by id.

        Supplies the ILS-level connection system, which a component
        plotted standalone would otherwise fall back to guessing."""
        import component_plotter
        comp = (self.components[which] if isinstance(which, int)
                else self.components[self.ids.index(which)])
        return component_plotter.plot_component(
            comp, system=self.connection_system, path=path, **kw)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_ils(spec: dict) -> ILS:
    if not isinstance(spec, dict):
        raise ILSDefinitionError('build_ils takes a dict. Natural language '
                                  'and file IO belong in a wrapper that '
                                  'emits one.')
    definition = json.loads(json.dumps(spec))      # deep copy, verbatim
    definition.pop('schema_version', None)
    findings = []

    ils_meta = definition.get('ils', {})
    if ils_meta.get('frame', 'local') != 'local':
        raise ILSDefinitionError("frame must be 'local'")

    system = ils_meta.get('connection_system')
    if system is not None:
        cs.named_connection_system(system)          # validates or raises

    own = str(ils_meta.get('ownership', 'strict')).lower()
    ownership = (cs.OwnershipPolicy.STRICT if own == 'strict'
                 else cs.OwnershipPolicy.LOWEST)

    pk = dict(definition.get('pipeline', {}))
    prov = pk.pop('provenance', 'ILLUSTRATIVE')
    pipe = cs.BasePipeline(provenance=cs.Provenance[prov],
                            **{k: float(v) for k, v in pk.items()})

    comps, codes, ids = [], [], []
    for entry in definition.get('components', []):
        code = entry['code']
        if code not in CLS:
            raise ILSDefinitionError(f'unknown component code {code!r}')
        cid = entry.get('id', f'C{len(comps)+1}')
        params = {k: v for k, v in entry.items() if k not in ('code', 'id')}
        variant = params.pop('variant', None)
        kw = {}
        if variant:
            kw['variant'] = variant
        if 'provenance' in params:
            kw['provenance'] = cs.Provenance[params.pop('provenance')]
        base = defaults_for(code, pipe, variant or 'L')
        for k, v in params.items():
            if k in STR_FIELDS:
                base[k] = v
            elif k in SEQ_FIELDS:
                base[k] = tuple(float(x) for x in v)
            else:
                base[k] = float(v)
        if code in EA_CODES and system is None:
            findings.append(Finding('info', f'{cid}/{code}',
                'no ILS connection_system named; this component will use '
                'its own default when queried'))
        comps.append(CLS[code](pipe=pipe, **base, **kw))
        codes.append(code)
        ids.append(cid)

    half, auto = _size_header(definition, comps, findings)

    ils = ILS(definition=definition, pipe=pipe, components=comps, codes=codes,
               ids=ids, header_half=half, header_auto=auto,
               connection_system=system, ownership=ownership,
               findings=findings)
    ils.findings.extend(ils.validate())
    return ils



# ---------------------------------------------------------------------------
# Layout construction helpers
# ---------------------------------------------------------------------------
# The build sequence is: arrange the PARTS without overlap, name them, THEN
# declare the connections. These helpers cover the two mechanical steps in
# that sequence so they are not hand-typed -- ids that are typed by hand drift
# from the codes they name, and weld associations that are typed by hand get
# missed exactly where a chain is longest.

ID_STEM = {
    'GD-HdPipe': 'hdpipe', 'GD-BrPipe': 'brpipe',
    'GD-TP': 'tp', 'GD-TT': 'tt', 'GD-PIP': 'pip', 'GD-VLV': 'vlv',
    'GD-SH': 'sh', 'GD-ST': 'st', 'GD-SB': 'sb',
    'GD-B': 'branch', 'GD-Con': 'con',
}

# Components that sit ON the header line and therefore form the weld chain.
# GD-SH is excluded deliberately: it owns no structural line and is positioned
# against the centreline rather than welded into the run (a PositionOrientation
# association, not a Connection). GD-ST/GD-SB/GD-Con are off-line by nature.
INLINE_CODES = {'GD-HdPipe', 'GD-TP', 'GD-TT', 'GD-PIP', 'GD-VLV'}


def assign_ids(components) -> list:
    """Give every component an id derived from its code, numbered in x order.

    GD-HdPipe -> hdpipe1, hdpipe2 ...;  GD-ST -> st1;  GD-Con -> con1, con2.
    Numbering runs left to right so the ids read in the order the parts sit
    on the pipeline, which makes a layout legible without a diagram.

    Mutates nothing: returns a new list of component dicts with 'id' set.
    An id already present is LEFT ALONE, so a hand-named part keeps its name
    and only the unnamed ones are filled in.
    """
    out = [dict(c) for c in components]
    order = sorted(range(len(out)), key=lambda i: (out[i].get('centre_x', 0.0),
                                                    out[i].get('code', '')))
    counts = {}
    for i in order:
        c = out[i]
        if c.get('id'):
            continue
        stem = ID_STEM.get(c.get('code'), (c.get('code') or 'part').lower())
        counts[stem] = counts.get(stem, 0) + 1
        c['id'] = f'{stem}{counts[stem]}'
    return out


def weld_chain(ils) -> list:
    """W (girth weld) associations for every adjacent pair of INLINE parts.

    Built from the assembled ILS rather than from the definition, because
    adjacency is a fact about EXTENTS -- which depend on each component's own
    parameters -- not about the order someone happened to list them in.

    Only pairs that actually touch get an association. A pair separated by a
    real gap is NOT welded together, and silently emitting a weld across the
    gap would assert a join that does not exist -- and would then be reported
    as a coincidence failure, which is the correct outcome but the wrong
    reason. The gap is reported by `unmated_gaps()` instead.
    """
    inline = [(c.extent[0], c.extent[1], cid, c)
              for cid, c in zip(ils.ids, ils.components)
              if c.code in INLINE_CODES]
    inline.sort()
    out = []
    for (a0, a1, ida, ca), (b0, b1, idb, cb) in zip(inline, inline[1:]):
        # ADJACENCY TOLERANCE must match the precision a layout is WRITTEN in,
        # not the precision floats are computed in. A producer emitting
        # centre_x and lengths rounded to 6 dp introduces discrepancies around
        # 5e-7 at every join. At the old 1e-9 this silently found NO adjacent
        # pairs, so a correctly-built chain got zero weld associations and
        # looked association-free rather than wrong -- and 5e-7 also slipped
        # under unmated_gaps' 1e-6, so nothing reported it either. The layout
        # fell between the two tolerances and passed everything.
        if abs(b0 - a1) > ADJACENCY_TOL:
            continue                      # not adjacent -- see docstring
        out.append({
            'type': 'Connection', 'connection': 'W',
            'from': {'component': ida, 'feature': 'weldR'},
            'to':   {'component': idb, 'feature': 'weldL'},
        })
    return out

def _size_header(definition, comps, findings) -> tuple:
    """Default 12 m centred, extended when the components need it.

    12 m does not always clear the grading. At default sizing the widest
    component half-span is 4.064 m (GD-SH, GD-SB, GD-B), leaving 1.936 m
    against GD-TT's 2.016 m graded run-up. It does not fit, and that is
    with everything centred.

    Rule as of 4 Sep 2026:
        half = max(7.0, widest_reach + 3.0)
    i.e. one 14 m joint minimum, extended when a component needs it, with
    3 m of plain pipe clear each side. Still a constant rather than a
    function of each component's mesh_advice and the target element length
    (tracker item 5), but now a stated engineering choice rather than a
    placeholder number.
    """
    given = definition.get('header', {}).get('half_length')
    if given is not None:
        return float(given), False
    if not comps:
        return DEFAULT_HEADER_HALF, False

    # CHAIN MODE: the inline components ARE the header, so the header does
    # not extend past them. Sizing it to max(one joint, reach + clearance)
    # would put plain pipe either side of a run that is supposed to BE the
    # run, which is the continuous model wearing the chain model's name.
    if definition.get('ils', {}).get('header_model') == 'chain':
        inline = [c for c in comps if c.code in INLINE_CODES]
        if inline:
            half = max(max(abs(c.extent[0]), abs(c.extent[1])) for c in inline)
            return half, False
    reach = max(max(abs(c.extent[0]), abs(c.extent[1])) for c in comps)
    # half = max(one joint, widest reach + clearance each side). MAX, not min:
    # the header must be AT LEAST a joint and LONGER when the components need
    # it. Taking the minimum would return a 14 m header for a 20 m assembly,
    # which is the opposite of the intent.
    need = max(DEFAULT_HEADER_HALF, reach + HEADER_CLEAR_EACH_SIDE)
    if need <= DEFAULT_HEADER_HALF:
        return DEFAULT_HEADER_HALF, False
    findings.append(Finding('info', 'header',
        f'auto-extended to +/-{need:.3f} m: widest component reaches '
        f'{reach:.3f} m and the default +/-{DEFAULT_HEADER_HALF:.1f} m '
        f'leaves only {DEFAULT_HEADER_HALF-reach:.3f} m for grading'))
    return need, True

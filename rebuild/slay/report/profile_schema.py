"""slay.report.profile_schema -- the declared contract for a PROFILE. L8.

WHY A SECOND CONTRACT, AND NOT MORE COLUMNS ON THE FIRST. `slay.report.schema`
declares a CASE row: one line per passage, carrying every peak with its
location and step. That contract was designed to EXCLUDE a profile, and its
own consumer says so:

    A case row ... does NOT carry a profile -- strain against position along
    the pipe -- so no trace can be drawn from it. That is by design: a
    profile is thousands of numbers per position and belongs in a
    per-position artifact, not in a dataset row.

The gap that left was not theoretical. Asked for a figure of the deformed
shape, the only route was to re-solve the whole passage in a tool that
imports the solver -- which is the generating path the schema was built to
retire. The figure came out right and the route was wrong, and the scalars
quoted beside it were re-solved a third time when they were already sitting
in the case CSV. THIS module is what closes that: a profile is an artifact
with a declared contract, so a plotter can read one without a solver.

THREE TABLES, BECAUSE THERE ARE THREE GRAINS. Forcing them into one file
would mean either a discriminator column (a table pretending to be three) or
duplicating a node's coordinates on every element that touches it. Each
grain gets a table, each table gets a sidecar:

  `<stem>.geometry.csv`   one row per SAMPLE per position. The solved
                          centreline in world coordinates, what the assembly
                          is at that material point, and how far off the arc
                          the pipe sits. Panels 1-3 come from this alone.

  `<stem>.sections.csv`   one row per ELEMENT per position. Strain and
                          moment, over the element's OWN EXTENT. Panels 4-5.

  `<stem>.stations.csv`   one row per ROLLER. Fixed for the case -- rollers
                          do not move when the pipe does.

SAMPLES ARE NOT NODES, and that is deliberate (L074). The structural mesh is
ruled at 2xOD (G10) and is the right density to SOLVE on; it is not a
drawing grid. A 6 m shroud spans seven nodes, its taper ends fall between
them, and an outline sampled on the mesh came out with a 95 mm step where
the real geometry goes smoothly to zero. The geometry table therefore
carries a resampled centreline with the assembly queried at every sample --
the same resampling the figure already did, moved into the artifact so the
plotter inherits it instead of re-deriving it.

WHAT THE PLOTTER MAY THEN DO, and it is worth being precise, because the
point of the contract is the line between the two. It may offset the
centreline along its own normal to draw a wall, a bore, a body or a shroud:
that is pure geometry on numbers the file gives it. It may NOT ask where a
roller is, what section owns a point, or what the arc radius is -- those are
columns, and if one is missing the file is wrong rather than the plotter.

VERSIONING is separate from the case schema's. The two artifacts change for
different reasons and a reader of one should not be told to distrust it
because the other moved.
"""

from __future__ import annotations

import re

from slay.report.schema import IDX, M, NM, NONE, Field

PROFILE_SCHEMA_VERSION = '1.3.0'
# 1.3.0  `owner` on the sections table: which BODY the element belongs to,
#        as distinct from `section_owner`, which is whose SECTION it
#        carries. An EA frame's elements carry the pipe's section but are
#        not the pipe, and a strain trace that cannot tell them apart
#        interleaves two structures into one zig-zagging line.
# 1.2.0  a `members` table: the structural elements that are NOT the
#        pipeline -- an EA frame and the connectors that fasten it. Without
#        it a figure of an EA case draws the pipe and omits the thing
#        acting on it.
# 1.1.0  `region` on the geometry and sections tables, and `region_scheme`
#        in the case context: the five-region scheme for an offset body
#        (`slay.report.regions`). Empty for a case that has no offset body.
# 1.0.0  first contract.

TABLE_SUFFIX = {
    'geometry': '.geometry.csv',
    'sections': '.sections.csv',
    'stations': '.stations.csv',
    'members': '.members.csv',
}


def _identity(table: str) -> list:
    """The two columns every table carries, so no file is anonymous."""
    return [
        Field('profile_schema_version', 'str', NONE, 'name', 'identifier',
              'version of THIS contract. Separate from the case schema: the '
              'two artifacts move for different reasons', per='case'),
        Field('case_id', 'str', NONE, 'name', 'identifier',
              'the case this profile belongs to. JOINS TO THE CASE ROW of '
              'the same name in a dataset written to `slay.report.schema`, '
              'which is where the peaks and their locations live -- a '
              'profile deliberately does not repeat them', per='case'),
        Field('table', 'str', NONE, 'name', 'identifier',
              f"always {table!r}; present so a file separated from its name "
              f'still says what grain it is', per='case'),
    ]


# ---------------------------------------------------------------------------
# case-level context, repeated on every geometry row
# ---------------------------------------------------------------------------
#
# Denormalised rather than put in a fourth file. These are eight scalars a
# figure needs for its titles and its reporting band, they never vary within
# a profile, and `per='case'` makes that claim CHECKABLE -- `profile.write`
# refuses a file where one of them moves.

CONTEXT = [
    Field('family', 'str', NONE, 'name', 'identifier',
          "'plain' or the component archetype", per='case'),
    Field('R', 'float', M, 'length', 'input',
          'stinger radius, to the ROLLER CENTRELINE', per='case'),
    Field('spacing', 'float', M, 'length', 'input', 'roller spacing',
          per='case'),
    Field('OD', 'float', M, 'length', 'input',
          'pipeline outside diameter -- the PIPE, not any component',
          per='case'),
    Field('t_wall', 'float', M, 'length', 'input', 'pipeline wall thickness',
          per='case'),
    Field('tension_mt', 'float', 'MT', 'force', 'input',
          'lay tension in METRIC TONNES (the solver works in newtons)',
          per='case'),
    Field('L_comp', 'float', M, 'length', 'input',
          'component length; 0 for plain pipe', per='case'),
    Field('s_centre', 'float', M, 'length', 'input',
          'station coordinate the component was centred on at zero shift. '
          'The ILS-local to model mapping is `s = s_centre - x_local`',
          per='case'),
    Field('zone_s_max', 'float', M, 'length', 'derived',
          'reporting band cut in STATION coordinates; at or beyond it is '
          'excluded (the D6 tip artefact). A figure that does not shade this '
          'shows the tip spike as though it were the answer', per='case'),
    Field('n_positions', 'int', NONE, 'count', 'derived',
          'positions in the passage', per='case'),
    Field('stiffness_ratio', 'float', NONE, 'ratio', 'derived',
          'component second moment over pipeline second moment, off the '
          'SOLVED sections; 1.0 when nothing steps. Carried so a figure can '
          'title itself without joining to the case row', per='case'),
    Field('n_junctions', 'int', NONE, 'count', 'derived',
          'section steps in the model; 0 for plain pipe AND for a shroud, '
          'which shares the pipe section', per='case'),
    Field('region_scheme', 'str', NONE, 'name', 'derived',
          "which region scheme the `region` column follows, or empty when "
          "the case has none. 'X1-X5/offset' divides the pipe into the "
          'catenary-side taper and beyond, the deep section in thirds, and '
          'the vessel-side taper and beyond', per='case'),
    Field('envelope_step', 'int', IDX, 'count', 'derived',
          'position index of the passage envelope -- the worst position, and '
          'the one a single-figure plot should default to', per='case'),
]

POSITION = [
    Field('step', 'int', IDX, 'count', 'step',
          'passage position index, 0-based in schedule order', per='position'),
    Field('shift', 'float', M, 'length', 'step',
          'travel along the passage at this position. THE PLOTTER NEEDS IT: '
          'the solver omits the rigid-body translation of a pipe advancing '
          'down the stinger (sliding along its own axis strains nothing), so '
          'world x is `-(s_material + shift + u_s)` and a figure that drops '
          'the shift draws the pipe a whole shift short of its rollers '
          '(L070)', per='position'),
    Field('converged', 'bool', NONE, 'flag', 'status',
          'this position converged. A position that did not is WRITTEN, not '
          'dropped, so a reader can see the hole', per='position'),
]


# ---------------------------------------------------------------------------
# table 1 -- geometry, one row per sample per position
# ---------------------------------------------------------------------------

GEOMETRY = _identity('geometry') + CONTEXT + POSITION + [
    Field('sample', 'int', IDX, 'count', 'identifier',
          'index along the resampled centreline, 0 at the VESSEL end and '
          'increasing toward the stinger (increasing s_material)',
          per='sample'),
    Field('s_material', 'float', M, 'length', 'location',
          'material coordinate -- labels a point on the PIPE and travels '
          'with it', per='sample'),
    Field('s_station', 'float', M, 'length', 'location',
          'station coordinate = s_material + shift -- where on the STINGER, '
          'and the coordinate to compare across positions', per='sample'),
    Field('x', 'float', M, 'length', 'value',
          'WORLD x of the solved centreline. +x points toward the vessel, so '
          'the stinger is at negative x and `x = -(s_material + shift + '
          'u_s)`. Every value here is SOLVED, never placed on the arc '
          'formula', per='sample'),
    Field('y', 'float', M, 'length', 'value',
          'WORLD y of the solved centreline, +y DOWN', per='sample'),
    Field('arc_x', 'float', M, 'length', 'value',
          'WORLD x of the roller-centreline locus at this s_station -- where '
          'the pipe would sit if it lay on every roller', per='sample'),
    Field('arc_y', 'float', M, 'length', 'value',
          'WORLD y of that locus', per='sample'),
    Field('normal_x', 'float', NONE, 'direction', 'value',
          'unit normal of the LOCUS at this s_station, world frame. Carried '
          'because a plotter cannot ask the Scene for it', per='sample'),
    Field('normal_y', 'float', NONE, 'direction', 'value',
          'unit normal of the locus, world frame', per='sample'),
    Field('off_arc', 'float', M, 'length', 'value',
          'signed distance of the solved centreline off the locus, ALONG '
          'THE NORMAL: 0 means sitting on the rollers, positive means held '
          'off them. Not a vertical gap -- the two differ by cos(theta), '
          'which is 20% at SR7. THIS IS THE ONLY PANEL A SHROUD IS VISIBLE '
          'ON: GD-SH lifts the pipe 203 mm and adds no stiffness, which on a '
          'panel spanning 20 m of stinger drop is a third of a pixel',
          per='sample'),
    Field('OD_section', 'float', M, 'length', 'value',
          'outside diameter of the STRUCTURAL section at this material '
          'point. A shroud does NOT change it -- the pipe section runs right '
          'through one -- so drawing a shroud from this column would invent '
          'a stiffness the model does not have (L073)', per='sample'),
    Field('t_section', 'float', M, 'length', 'value',
          'wall thickness of the structural section here', per='sample'),
    Field('y_contact', 'float', M, 'length', 'value',
          'depth of the CONTACT SURFACE below the centreline at this '
          'material point, i.e. what a roller touches. OD/2 on bare pipe; '
          'larger under a shroud. This is the column a shroud is drawn from',
          per='sample'),
    Field('section_owner', 'str', NONE, 'name', 'location',
          "which body owns the STRUCTURAL section here -- 'pipe' or the "
          'component id. Where this is not `pipe`, the body is drawn at '
          '`OD_section` about the centreline and REPLACES the pipe wall',
          per='sample'),
    Field('contact_owner', 'str', NONE, 'name', 'location',
          "which body owns the CONTACT SURFACE here. Where this is not "
          '`pipe` while `section_owner` still is, the body is a SHROUD and '
          'is drawn from the pipe bottom down to `y_contact` (L073)',
          per='sample'),
    Field('region', 'str', NONE, 'name', 'location',
          "the offset body's strain region at this material point -- X1..X5 "
          'from the catenary side, or EMPTY when the case has no offset '
          'body. A shroud steps no section and so has no junction to probe; '
          'the region is its reporting unit. Fixed on the steel, so the same '
          'region names the same pipe at every position', per='sample'),
]


# ---------------------------------------------------------------------------
# table 2 -- sections, one row per element per position
# ---------------------------------------------------------------------------
#
# STRAIN IS PIECEWISE CONSTANT PER ELEMENT and this table says so by carrying
# both ends rather than a midpoint. Joining midpoints interpolates a gradient
# the model does not have, and it leaves a half-element GAP between the last
# element of a section run and the junction, which reads as missing data
# rather than as the step it is (L071).

SECTIONS = _identity('sections') + POSITION + [
    Field('element', 'int', IDX, 'count', 'identifier',
          'element index in the solved problem', per='sample'),
    Field('s_material_0', 'float', M, 'length', 'location',
          'material coordinate of the element end nearer the VESSEL',
          per='sample'),
    Field('s_material_1', 'float', M, 'length', 'location',
          'material coordinate of the end nearer the STINGER', per='sample'),
    Field('s_station_0', 'float', M, 'length', 'location',
          'station coordinate of the vessel-side end', per='sample'),
    Field('s_station_1', 'float', M, 'length', 'location',
          'station coordinate of the stinger-side end', per='sample'),
    Field('x_0', 'float', M, 'length', 'value',
          'WORLD x of the vessel-side end, on the solved pipe, so the '
          'staircase can be drawn against the same axis as the geometry '
          'without re-deriving the mapping', per='sample'),
    Field('x_1', 'float', M, 'length', 'value',
          'WORLD x of the stinger-side end', per='sample'),
    Field('strain', 'float', NONE, 'strain', 'value',
          'extreme-fibre strain in this element, a FRACTION: 0.0074 is '
          '0.74%', per='sample'),
    Field('moment', 'float', NM, 'moment', 'value',
          'SIGNED bending moment. The case schema records peak |M| because a '
          'passage envelope is about how hard the pipe is bent, but a '
          'profile keeps the sign: sagging between rollers puts the moment '
          'through zero, and a trace of magnitudes shows a cusp where the '
          'pipe is simply straight', per='sample'),
    Field('OD_section', 'float', M, 'length', 'value',
          'outside diameter of this element\'s section. A CHANGE in it '
          'between consecutive elements is a junction, and the trace must '
          'BREAK there rather than be drawn through', per='sample'),
    Field('section_owner', 'str', NONE, 'name', 'location',
          "'pipe' or the component id", per='sample'),
    Field('owner', 'str', NONE, 'name', 'location',
          "which BODY this element belongs to -- 'pipeline', or an attached "
          "structure such as 'ST'. NOT the same as `section_owner`, which "
          'says whose SECTION it carries: an EA frame member carries the '
          "pipe's section and is not the pipe. A strain trace must filter on "
          'THIS, or it draws two structures as one line', per='sample'),
    Field('region', 'str', NONE, 'name', 'location',
          "the offset body's strain region this element belongs to, by its "
          'MIDPOINT -- X1..X5 from the catenary side, or empty. An element '
          'straddling a boundary is assigned whole, because strain is '
          'piecewise constant per element and splitting it would invent two '
          'values where the model has one', per='sample'),
    Field('in_band', 'bool', NONE, 'flag', 'status',
          'this element is inside the reporting band (s_station < '
          'zone_s_max). Elements outside are WRITTEN, so a figure can shade '
          'them rather than silently omit them', per='sample'),
]


# ---------------------------------------------------------------------------
# table 3 -- stations, one row per roller
# ---------------------------------------------------------------------------

STATIONS = _identity('stations') + [
    Field('station', 'str', NONE, 'name', 'identifier',
          "roller name, e.g. 'SR2' or 'VR1'", per='sample'),
    Field('role', 'str', NONE, 'name', 'identifier',
          'the station role the Scene gives it', per='sample'),
    Field('s_station', 'float', M, 'length', 'location',
          'ARC POSITION along the stinger. Fixed: rollers do not move when '
          'the pipe does, which is why this table has no `step`',
          per='sample'),
    Field('x', 'float', M, 'length', 'value', 'WORLD x of the roller',
          per='sample'),
    Field('y', 'float', M, 'length', 'value', 'WORLD y of the roller',
          per='sample'),
    Field('radius', 'float', M, 'length', 'value',
          'roller radius, so a figure draws the roller at its true size '
          'rather than as a marker', per='sample'),
    Field('one_sided', 'bool', NONE, 'flag', 'status',
          'the contact here is one-sided, so the pipe may LIFT OFF. A figure '
          'draws an uplift arrow on these', per='sample'),
]


# ---------------------------------------------------------------------------
# table 4 -- members, one row per NON-PIPELINE element per position
# ---------------------------------------------------------------------------
#
# WHAT THIS IS FOR. An externally-attached structure -- EA-ST's portal frame,
# EA-SB's -- is not part of the pipeline and appears nowhere in the geometry
# or sections tables, which sample the pipe. A figure built from those alone
# draws the pipe correctly and omits the thing bending it. This table
# carries the frame's own members and the connectors that fasten them down,
# each as a straight segment in world coordinates, which is all a drawing
# needs.
#
# CONNECTORS ARE MEMBERS HERE, marked by `kind`. They are separate from the
# frame in the model -- a connector's stiffness comes from the pipe section
# and not from its own length -- but on a drawing they are both lines
# between two solved points, and keeping them in one table means a figure
# cannot draw the frame while silently omitting what holds it on.

MEMBERS = _identity('members') + POSITION + [
    Field('element', 'int', IDX, 'count', 'identifier',
          'element index in the solved problem, or the connector index',
          per='sample'),
    Field('kind', 'str', NONE, 'name', 'identifier',
          "'structure' for a member of the attached structure, 'connector' "
          'for a tie down to the pipe', per='sample'),
    Field('owner', 'str', NONE, 'name', 'location',
          "which body it belongs to -- 'ST', 'SB', 'GD-Con'", per='sample'),
    Field('x_0', 'float', M, 'length', 'value',
          'WORLD x of one end, on the SOLVED structure', per='sample'),
    Field('y_0', 'float', M, 'length', 'value', 'WORLD y of that end, +y down',
          per='sample'),
    Field('x_1', 'float', M, 'length', 'value', 'WORLD x of the other end',
          per='sample'),
    Field('y_1', 'float', M, 'length', 'value', 'WORLD y of the other end',
          per='sample'),
    Field('s_material_0', 'float', M, 'length', 'location',
          'material coordinate of the first end', per='sample'),
    Field('s_material_1', 'float', M, 'length', 'location',
          'material coordinate of the second end', per='sample'),
    Field('stiffness_ratio', 'float', NONE, 'ratio', 'value',
          "the member's modulus over the pipeline's -- EA-ST's kT. 1.0 where "
          'nothing scales it', per='sample'),
    Field('conn_type', 'str', NONE, 'name', 'identifier',
          "joint type for a connector ('F'), empty for a structural member. "
          'The solver implements F only and refuses the rest (G9)',
          per='sample'),
    Field('slot', 'int', IDX, 'count', 'identifier',
          'connector slot number, or -1 for a structural member',
          per='sample'),
]


TABLES = {
    'geometry': GEOMETRY,
    'sections': SECTIONS,
    'stations': STATIONS,
    'members': MEMBERS,
}

PATTERNS: list = []     # no open column sets here: every grain is enumerable


# ---------------------------------------------------------------------------
# queries -- the same shape as `slay.report.schema`, per table
# ---------------------------------------------------------------------------

def header(table: str) -> list:
    """Every column of a table, in declared order."""
    return [f.name for f in _table(table)]


def _table(table: str) -> list:
    try:
        return TABLES[table]
    except KeyError:
        raise KeyError(
            f'{table!r} is not a profile table; have {sorted(TABLES)}') from None


def describe(table: str, column: str):
    """The `Field` for a column, or None if this contract does not know it."""
    for f in _table(table):
        if f.name == column:
            return f
    return None


def unknown(table: str, columns) -> list:
    """Columns the contract does not describe. The point of the module."""
    return [c for c in columns if describe(table, c) is None]


def select(table: str, quantity: str = None, role: str = None,
           per: str = None) -> list:
    """Fields of a table matching all the given criteria.

    What a consumer asks instead of hardcoding names -- "every column that
    varies per sample", "every location" -- so adding one does not require
    editing the plotter.
    """
    out = []
    for f in _table(table):
        if quantity is not None and f.quantity != quantity:
            continue
        if role is not None and f.role != role:
            continue
        if per is not None and f.per != per:
            continue
        out.append(f)
    return out


def constants(table: str) -> list:
    """Columns declared constant through the file (`per='case'`).

    `profile.write` asserts every one of these really is constant. A writer
    that leaks a per-row value into a case column is then caught by the file
    rather than by a reader noticing the title looks wrong.
    """
    return [f.name for f in _table(table) if f.per == 'case']


def per_position(table: str) -> list:
    """Columns constant within one passage step."""
    return [f.name for f in _table(table) if f.per == 'position']


def as_dict(table: str) -> dict:
    """One table's whole contract, serialisable -- written beside the file so
    a reader never needs this source to interpret one."""
    def row(f):
        return dict(name=f.name, dtype=f.dtype, unit=f.unit,
                    quantity=f.quantity, role=f.role, about=f.about,
                    pattern=f.pattern, per=f.per)
    return dict(profile_schema_version=PROFILE_SCHEMA_VERSION,
                table=table,
                grain=_GRAIN[table],
                fields=[row(f) for f in _table(table)],
                patterns=[])


_GRAIN = {
    'geometry': 'one row per sample per passage position',
    'sections': 'one row per element per passage position',
    'stations': 'one row per roller; fixed for the case',
    'members': 'one row per non-pipeline element per passage position',
}

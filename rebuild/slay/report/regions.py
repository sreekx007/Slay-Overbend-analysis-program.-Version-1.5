"""slay.report.regions -- the five strain regions of an offset (shroud) body. L8.

WHY A SHROUD NEEDS REGIONS AT ALL. A section-changing body (GD-TP, GD-TT)
announces itself: the section steps, so there is a JUNCTION, and `report.
junction` reports at it and at fixed offsets either side. A shroud steps
nothing -- its `stiffness_ratio` is 1.000 and it has zero junctions -- so
that whole reporting machinery returns an empty table for it, and
`body_peak_strain` comes out 0.0 for the case whose pipe is the most highly
strained in the dataset. There is nothing to probe AT, because the thing a
shroud does is spread over its whole length.

So the reporting unit is a REGION, not a point. This module implements the
scheme of the reference paper (Series 4, Type B1, Table XXIX), which divides
the pipe into five:

    catenary side  <--                                  --> vessel side

    |   X1   |    X2    |    X3    |    X4    |   X5   |
    | taper  | deep 1/3 | deep 1/3 | deep 1/3 | taper  |
    | +beyond|  catenary|  midspan |  vessel  | +beyond|

  X1  taper on the CATENARY side and the pipe beyond it -- governed by the
      plain-pipe catenary rather than by the shroud
  X2  catenary-side third of the deep section -- THE PEAK, in every case the
      paper ran and in ours; this is the region that governs design
  X3  midspan third -- intermediate, the paper puts it at 65-75% of X2
  X4  vessel-side third -- the lowest of the three, and the one that
      plateaus once V exceeds about 1.5 D
  X5  taper on the VESSEL side and the pipe beyond it

WHICH END IS WHICH, since getting it backwards would silently swap the
governing region with the quietest one. The model solves in `s` increasing
toward the stinger, and the catenary hangs off the stinger tip, so the
CATENARY side is HIGH `s`. The ILS-local frame runs the other way
(`s = s_centre - x_local`), so the catenary side is NEGATIVE local x. This
is not asserted from the frame algebra alone: measured on ILS-SH at its
envelope position, the peak sits at `s_material` 6.833, which is local
x = -1.881 -- inside the catenary-side third, exactly where the paper says
the peak is. `test_the_peak_lands_in_X2` keeps that honest.

MEASURED FROM THE CONTACT PROFILE, NOT FROM THE SPEC. `L1`, `L2` and `V` are
in the archetype definition and it would be shorter to read them from there.
This module asks the assembly instead -- where the contact surface is deep,
where it tapers, how deep it gets -- because `ils_builder` is the single
author of what a component IS (G7) and a region scheme derived from the spec
would describe the component we asked for rather than the one we solved.
"""

from __future__ import annotations

from dataclasses import dataclass

# The deep section is where the lift is at its maximum. A tolerance is needed
# because the profile is sampled, not symbolic; 0.1 mm is far below any
# geometry we model and far above float noise.
FLAT_TOL = 1.0e-4

N_SAMPLES = 4000

REGIONS = ('X1', 'X2', 'X3', 'X4', 'X5')

# GD-Simple's scheme. TWO regions, and the boundary is the BODY's end --
# not the shroud's deep section, because the body and the shroud are
# independently sized and either may be the longer. See `SimpleGeometry`.
SIMPLE_REGIONS = ('Xe', 'Xb')

ABOUT = {
    'Xb': 'INSIDE the body of the component -- the elastic span, carrying '
          'the pipeline section at the body modulus',
    'Xe': 'OUTSIDE the body, both sides -- plain pipeline on the case '
          'material. NOT an interval: it is the complement of Xb, so its '
          'bounds read as the whole model and its `spans` names the two '
          'pieces',
    'X1': 'taper on the CATENARY side, and the pipe beyond the body -- '
          'governed by the plain-pipe catenary, not by the body',
    'X2': 'deep section, CATENARY-side third -- the peak strain location, '
          'and the region that governs design',
    'X3': 'deep section, midspan third -- intermediate strain',
    'X4': 'deep section, VESSEL-side third -- the lowest of the three; '
          'plateaus once V exceeds about 1.5 x OD',
    'X5': 'taper on the VESSEL side, and the pipe beyond the body',
}


@dataclass(frozen=True)
class OffsetGeometry:
    """Where the deep section and the tapers are, in MATERIAL coordinates.

    Material, not station: the regions travel with the pipe, so a region
    boundary is a fixed point on the steel and the same `s_material` names it
    at every position of the passage. In station coordinates every boundary
    would move with the shift, and a per-region peak taken over the passage
    would be comparing different pieces of pipe at different steps.
    """
    s_cat_end: float        # shroud end, catenary side (highest s)
    s_deep_cat: float       # deep section starts, catenary side
    s_deep_ves: float       # deep section ends, vessel side
    s_ves_end: float        # shroud end, vessel side (lowest s)
    V: float                # offset depth below the pipe CENTRELINE
    lift_max: float         # V - OD/2: what the pipe is actually held off by
    OD: float
    owner: str

    @property
    def L1(self) -> float:
        """Deep section length."""
        return self.s_deep_cat - self.s_deep_ves

    @property
    def L2_cat(self) -> float:
        return self.s_cat_end - self.s_deep_cat

    @property
    def L2_ves(self) -> float:
        return self.s_deep_ves - self.s_ves_end

    @property
    def L_total(self) -> float:
        return self.s_cat_end - self.s_ves_end

    @property
    def symmetric(self) -> bool:
        return abs(self.L2_cat - self.L2_ves) < FLAT_TOL


@dataclass(frozen=True)
class SimpleGeometry(OffsetGeometry):
    """GD-Simple: an offset shroud PLUS the pipe body sitting on it.

    Subclasses `OffsetGeometry` on purpose rather than standing alongside
    it. The inherited four `s_*` fields are the SHROUD's footprint, which is
    exactly what `body_peaks` and the `peak_on_shroud` column already read,
    so both keep working unchanged. The two new fields are the BODY's
    extent, and they are what `bounds` partitions on.

    THEY ARE NOT THE SAME SPAN and must not be conflated. `L_body` and the
    shroud's `L1`/`L2` are independent by decision, so the body may be
    longer than the shroud it rides (then Xb contains the whole shroud and
    some plain-contact pipe either side) or shorter (then part of the
    elevated zone is in Xe). Keying Xb on the shroud would report the
    elastic span as whatever the shroud happened to be.
    """
    s_body_cat: float = 0.0     # body end, catenary side (highest s)
    s_body_ves: float = 0.0     # body end, vessel side (lowest s)
    body_owner: str = ''

    @property
    def L_body(self) -> float:
        return self.s_body_cat - self.s_body_ves

    @property
    def body_covers_shroud(self) -> bool:
        """Does Xb contain the whole elevated zone? When False, some of the
        lift is in Xe and the two regions are not "component" and "pipe"."""
        return (self.s_body_cat >= self.s_cat_end - FLAT_TOL
                and self.s_body_ves <= self.s_ves_end + FLAT_TOL)


def simple_geometry(ils, s_centre, OD=None, n=N_SAMPLES):
    """Measure a GD-Simple, or None if this assembly is not one.

    A GD-Simple is recognised by its SHAPE and never by an archetype name:
    a body that owns the section over a span while changing it by nothing,
    sitting on a different body that owns the contact. That is a pair of
    facts about the built assembly, which is the same rule
    `offset_geometry` follows and for the same reason -- `ils_builder` is
    the author of what a component IS (G7), so a scheme read off the spec
    would describe the component we asked for rather than the one we
    solved.

    Returns None for anything else, INCLUDING a shroud with a genuinely
    thick body inside it. That case steps the section, so it has junctions
    to report at and `offset_geometry`'s five regions to go with them;
    giving it Xb/Xe as well would put one strain in two schemes and invite
    them to disagree.
    """
    base = offset_geometry(ils, s_centre, OD=OD, n=n)
    if base is None:
        return None
    lo_x, hi_x = ils.extent
    OD_pipe = ils.assembly.pipe.OD_pipe if OD is None else OD

    # WHERE DOES A BODY OWN THE SECTION WITHOUT CHANGING IT? Sampled, not
    # read from the spec. `section_at` names the owner at every station and
    # the OD it carries there; a neutral body is the span where the owner is
    # not the bare pipe and the OD has not moved.
    xs = [lo_x + (hi_x - lo_x) * k / (n - 1) for k in range(n)]
    on = []
    owners = set()
    for k, x in enumerate(xs):
        sec = ils.assembly.section_at(x)
        if sec is None:
            continue
        own = getattr(sec, 'owner', 'pipe')
        if own == 'pipe' or own == base.owner:
            continue                 # bare pipe, or the shroud itself
        if abs(getattr(sec, 'OD', OD_pipe) - OD_pipe) > 1.0e-9:
            return None              # a STEP. That is a junction case.
        on.append(k)
        owners.add(own)
    if not on or len(owners) != 1:
        return None

    # s = s_centre - x, so the lowest index is the highest s.
    s_cat = s_centre - xs[min(on)]
    s_ves = s_centre - xs[max(on)]
    if s_cat - s_ves <= FLAT_TOL:
        return None
    return SimpleGeometry(
        s_cat_end=base.s_cat_end, s_deep_cat=base.s_deep_cat,
        s_deep_ves=base.s_deep_ves, s_ves_end=base.s_ves_end,
        V=base.V, lift_max=base.lift_max, OD=base.OD, owner=base.owner,
        s_body_cat=s_cat, s_body_ves=s_ves, body_owner=owners.pop())


def offset_geometry(ils, s_centre, OD=None, n=N_SAMPLES):
    """Measure the offset body's shape, or None if there is not one.

    Returns None for plain pipe and for a component that ONLY steps the
    section: a thick body is reported at its junctions, and giving it regions
    as well would put the same strain in two schemes and invite them to
    disagree.

    A COMBINED ASSEMBLY GETS BOTH, and that is not a relaxation of the rule
    above. Until 6 Oct this returned None as soon as any section stepped,
    which took `ILS-SHTP` -- a shroud with a thick body inside it -- out of
    region reporting entirely and left it uncomparable against Paper 1's
    TABLE XXXIX. But the paper reports that case in BOTH schemes at once, and
    says so in as many words: Case 2's peak is at "pipe-to-component junction
    at X2".

    The two schemes answer different questions and do not compete. The
    regions say WHERE ALONG THE OFFSET the strain is -- which third of the
    deep section -- and the junctions say WHICH FEATURE it is on. Reporting
    only junctions loses the first; reporting only regions loses the second.
    What the original rule rightly forbids is giving a body regions it has no
    offset to define, which is still what happens for a thick pipe alone.
    """
    if ils is None:
        return None
    lo_x, hi_x = ils.extent
    OD = ils.assembly.pipe.OD_pipe if OD is None else OD
    half = OD / 2.0

    xs = [lo_x + (hi_x - lo_x) * k / (n - 1) for k in range(n)]
    lift, owners, steps = [], [], []
    for x in xs:
        con = ils.assembly.contact_at(x)
        sec = ils.assembly.section_at(x)
        y = getattr(con, 'y', half) if con else half
        own = getattr(con, 'owner', 'pipe') if con else 'pipe'
        lift.append(y - half)
        owners.append(own)
        steps.append(getattr(sec, 'owner', 'pipe') if sec is not None
                     else 'pipe')

    # DOES THE BODY HOLDING THE PIPE UP ALSO STEP ITS SECTION THERE?
    #
    # That is the whole test, and it is a comparison of two OWNERS rather
    # than a flag, because the flag version does not survive the case it was
    # written for. A thick pipe alone makes `lift` positive by itself -- its
    # OD is larger, so its bottom surface IS lower -- but that is a
    # consequence of its wall, not a deliberate elevation, and it has no deep
    # section to divide into thirds: there the contact owner and the section
    # owner are the SAME body, and the answer is no regions.
    #
    # On a shroud with a thick pipe inside it they are DIFFERENT bodies --
    # the shroud holds the pipe up, the thick body stiffens it -- and Paper 1
    # reports exactly that case in both schemes at once ("pipe-to-component
    # junction at X2", TABLE XXXIX).
    #
    # Keyed instead on "does any section step at the deepest sample", this
    # worked at a 5 D thick body and returned None at 10 D, because at 10 D
    # the body fills the whole deep section and the deepest sample lands on
    # it. Which sample wins a tie is not something the answer may depend on
    # (6 Oct 2026).
    k_deep = max(range(len(lift)), key=lambda k: lift[k])
    owner = owners[k_deep]
    if owner == 'pipe' or owner == steps[k_deep]:
        return None
    lift_max = max(lift)
    if lift_max <= FLAT_TOL:
        return None

    on = [k for k, v in enumerate(lift) if v > FLAT_TOL]
    deep = [k for k, v in enumerate(lift) if v >= lift_max - FLAT_TOL]
    if not on or not deep:
        return None

    def s_of(k):
        return s_centre - xs[k]

    # s = s_centre - x, so the LOWEST index (most negative x) is the HIGHEST
    # s -- the catenary side. Reversing these two lines swaps the governing
    # region with the quietest one and nothing else changes.
    return OffsetGeometry(
        s_cat_end=s_of(min(on)), s_deep_cat=s_of(min(deep)),
        s_deep_ves=s_of(max(deep)), s_ves_end=s_of(max(on)),
        V=lift_max + half, lift_max=lift_max, OD=OD, owner=owner)


def bounds(geom):
    """[(name, s_lo, s_hi)] in catenary-to-vessel order, a PARTITION.

    The two outer regions are unbounded -- X1 runs from the deep section out
    to the stinger tip and X5 back to the vessel -- so every element of the
    model belongs to exactly one region and none belongs to two. A scheme
    that only covered the shroud would leave the pipe on either side of it
    unreported, which is the half of the answer the paper calls "governed by
    the plain-pipe catenary".
    """
    if geom is None:
        return []
    if isinstance(geom, SimpleGeometry):
        # GD-Simple. Xe appears TWICE, once each side, and that is not a
        # bug to be tidied into one row: Xe is the complement of Xb, so it
        # is two disjoint pieces of pipe and any single interval naming it
        # would be a lie. `region_peaks` merges them under one name and
        # keeps both intervals in `spans`.
        return [
            ('Xe', geom.s_body_cat, float('inf')),
            ('Xb', geom.s_body_ves, geom.s_body_cat),
            ('Xe', float('-inf'), geom.s_body_ves),
        ]
    third = geom.L1 / 3.0
    return [
        ('X1', geom.s_deep_cat, float('inf')),
        ('X2', geom.s_deep_cat - third, geom.s_deep_cat),
        ('X3', geom.s_deep_cat - 2.0 * third, geom.s_deep_cat - third),
        ('X4', geom.s_deep_ves, geom.s_deep_cat - 2.0 * third),
        ('X5', float('-inf'), geom.s_deep_ves),
    ]


def classify(s_material, geom) -> str:
    """Which region a material point is in. '' when the case has no regions.

    Half-open [lo, hi) downward from X1, so a point exactly on a boundary
    lands in the region nearer the vessel and never in both.
    """
    if geom is None:
        return ''
    for name, lo, hi in bounds(geom):
        if lo <= s_material < hi:
            return name
    # Only reachable at exactly -inf; keeps the function total. The name has
    # to come from the SCHEME -- returning 'X5' for a GD-Simple would put a
    # strain in a region that case does not have.
    return 'Xe' if isinstance(geom, SimpleGeometry) else 'X5'


def region_of_element(s0, s1, geom) -> str:
    """The region an ELEMENT belongs to, by its midpoint.

    An element that straddles a boundary is assigned whole rather than split:
    strain is piecewise constant per element, so splitting would invent two
    values where the model has one. At the ruled 2xOD mesh an element is
    0.81 m against a 1.35 m third of the deep section, so at most one element
    per boundary is ambiguous -- recorded rather than hidden.
    """
    return classify(0.5 * (s0 + s1), geom)


def region_peaks(positions, problem, geom, zone_s_max, shift_of=None) -> dict:
    """{region: {...}} -- the worst strain and moment in each region, over the
    WHOLE passage, with where and when.

    MAX OVER POSITIONS, never a sum (G3), and taken in MATERIAL coordinates
    so a region is the same piece of steel at every step.
    """
    if geom is None:
        return {}
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    ends = {idx: sorted((s_of[n1], s_of[n2]))
            for (idx, n1, n2, _o, _l) in problem.elements}

    # BUILT BY MERGING, because a region may be more than one interval:
    # GD-Simple's Xe is the pipe either side of the body, two disjoint
    # pieces under one name. `spans` keeps them exactly; `s_lo`/`s_hi` are
    # the outer envelope, which for Xe is the whole model and is written
    # EMPTY by `case_columns` rather than as a misleading pair of numbers.
    out = {}
    for name, lo, hi in bounds(geom):
        r = out.setdefault(name, dict(
            peak_strain=0.0, peak_moment=0.0, s_material=0.0,
            s_station=0.0, step=-1, shift=0.0, n_elements=0, spans=()))
        r['spans'] = r['spans'] + ((lo, hi),)
    for r in out.values():
        r['s_lo'] = min(lo for lo, _hi in r['spans'])
        r['s_hi'] = max(hi for _lo, hi in r['spans'])
    # Element counts come off the GEOMETRY, once. Counting them inside the
    # position loop would count an element as often as it is inside the
    # band, which varies with the shift and is not a property of the region.
    for (lo, hi) in ends.values():
        name = region_of_element(lo, hi, geom)
        if name:
            out[name]['n_elements'] += 1

    for step, pos in enumerate(positions):
        shift = pos.shift if shift_of is None else shift_of(pos)
        moments = {i: m for (i, _s, m) in getattr(pos.result, 'moments', ())}
        for (idx, _s_mid, eps) in getattr(pos.result, 'strains', ()):
            lo, hi = ends.get(idx, (0.0, 0.0))
            if hi + shift >= zone_s_max:        # outside the reporting band
                continue
            name = region_of_element(lo, hi, geom)
            if not name:
                continue
            r = out[name]
            if abs(eps) > r['peak_strain']:
                r.update(peak_strain=abs(eps), s_material=0.5 * (lo + hi),
                         s_station=0.5 * (lo + hi) + shift, step=step,
                         shift=shift)
            m = abs(moments.get(idx, 0.0))
            if m > r['peak_moment']:
                r['peak_moment'] = m
    # A REGION WITH NO ELEMENTS REPORTED 0.0000%, which is the same defect
    # `body_peaks` was written to fix, in a different place: a zero reads as
    # "nothing happening here" and nobody checks a quiet number.
    #
    # It is reachable whenever a third of the deep section is SHORTER THAN
    # ONE ELEMENT, so no element midpoint lands in it. Measured at Paper 1's
    # Series 4 R = 70 / T = 120 MT config: L1 = 5 D = 2.032 m, thirds of
    # 0.677 m, elements of 0.813 m at the ruled 2 x OD density -- X3 held
    # ZERO elements and read 0.0000% while X2 and X4 either side read 0.85%
    # and 0.68% (6 Oct 2026).
    #
    # `peak_strain` is left at 0.0 because the caller may be writing a
    # numeric column, but `measured` says whether that zero is a
    # measurement, and `n_elements` says why it is not. Readers must not
    # print an unmeasured region as a number.
    for r in out.values():
        r['measured'] = r['n_elements'] > 0 and r['step'] >= 0

    # THE GOVERNING REGION, whose peak every other region is quoted against.
    # X2 in the five-region scheme; Xb in GD-Simple's, where the body is the
    # whole point of the component and the pipe outside it is the reference
    # condition. Named per scheme rather than hard-coded, because quoting a
    # GD-Simple against a region it has no X2 for would divide by zero and
    # report 0.0 for every region at once.
    ref_name = 'Xb' if isinstance(geom, SimpleGeometry) else 'X2'
    refr = out.get(ref_name, {})
    ref = refr.get('peak_strain', 0.0) if refr.get('measured') else 0.0
    for r in out.values():
        # KEY NAMED FOR THE FIVE-REGION SCHEME, VALUE GOVERNED BY WHICHEVER
        # SCHEME IS IN FORCE. The key stays `frac_of_x2` because it is part
        # of this dict's contract and callers build the shape by hand; what
        # `ref_name` changes is the DENOMINATOR, and `case_columns` emits it
        # under a column named for the region it divided by.
        r['frac_of_x2'] = (r['peak_strain'] / ref) if ref > 0 else 0.0
        # X1 and X5 each lump together a TAPER and the plain pipe beyond it.
        # The reference calls both "governed by the plain-pipe catenary",
        # and at its own 2xOD mesh that holds. Refined, it does not: the
        # peak migrates onto the catenary-side taper, 0.395 m outboard of
        # the deep section, where the lift gradient is steepest. Without
        # this column a reader has X1's peak and no way to tell which of the
        # two things it happened on.
        r['peak_on_shroud'] = bool(
            geom.s_ves_end <= r['s_material'] <= geom.s_cat_end
            and r['step'] >= 0)
    return out


def body_peaks(positions, problem, geom, scene, zone_s_max) -> dict:
    """The `body_peak_*` groups for an OFFSET body. {} when there is none.

    'Offset body' is wider than 'shroud'. GD-SH is one; so is GD-SB, which
    lifts the pipe 1.4224 m -- 3.5 x OD -- while ALSO carrying a frame and
    connectors. The scheme keys on what the geometry does (the contact
    surface moves, the section does not), never on the component's name.

    THE DEFECT THIS FIXES. `report.passage.body_peaks` asks the junction
    rows which elements are on the body, because for a section-changing
    component that is a question about SECTIONS. A shroud steps no section,
    so the answer is "none", and `body_peak_strain` came out 0.0 with
    `step: -1` and a blank station -- for the case whose pipe carries the
    highest strain in the dataset. It parsed, it plotted, and it was wrong
    in the one direction nobody checks: a zero reads as "nothing happening
    here".

    For an offset body the body is its FOOTPRINT: everything the shroud
    covers, tapers included. Measured that way GD-SH reports 0.6868% rather
    than 0.0.
    """
    if geom is None:
        return {}
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    ends = {idx: sorted((s_of[n1], s_of[n2]))
            for (idx, n1, n2, _o, _l) in problem.elements}
    on_body = {idx for idx, (lo, hi) in ends.items()
               if geom.s_ves_end <= 0.5 * (lo + hi) <= geom.s_cat_end}

    from slay.report.passage import nearest_station

    out = {}
    for prefix, attr in (('body_peak_strain', 'strains'),
                         ('body_peak_moment', 'moments')):
        best = (0.0, 0.0, -1, 0.0)          # value, s_material, step, shift
        for step, pos in enumerate(positions):
            if not getattr(pos, 'converged', True):
                continue
            for (idx, _s_mid, v) in getattr(pos.result, attr, ()):
                if idx not in on_body:
                    continue
                lo, hi = ends[idx]
                if hi + pos.shift >= zone_s_max:
                    continue
                if abs(v) > best[0]:
                    best = (abs(v), 0.5 * (lo + hi), step, pos.shift)
        val, s_mat, step, shift = best
        s_sta = s_mat + shift
        sta, off = nearest_station(scene, s_sta) if step >= 0 else ('', 0.0)
        out[prefix] = val
        out.update({f'{prefix}_s_material': s_mat,
                    f'{prefix}_s_station': s_sta if step >= 0 else 0.0,
                    f'{prefix}_station': sta,
                    f'{prefix}_station_offset': off,
                    f'{prefix}_step': step,
                    f'{prefix}_shift': shift})
    return out


def case_columns(geom, peaks) -> dict:
    """The flat columns a case row carries, per `slay.report.schema`.

    Empty when the case has no offset body, so a dataset mixing families
    simply leaves them blank rather than writing zeros that would pool into
    an average as though they were measurements.
    """
    if geom is None:
        return {}
    simple = isinstance(geom, SimpleGeometry)
    out = dict(region_scheme='Xb-Xe/simple' if simple else 'X1-X5/offset',
               offset_L1=geom.L1,
               offset_L2=0.5 * (geom.L2_cat + geom.L2_ves),
               offset_L2_cat=geom.L2_cat, offset_L2_ves=geom.L2_ves,
               offset_V=geom.V, offset_owner=geom.owner)
    if simple:
        # The SHROUD columns above still describe the shroud. These describe
        # the body, which is a different span and the one Xb is drawn on.
        out.update(body_L=geom.L_body, body_owner=geom.body_owner,
                   body_s_cat=geom.s_body_cat, body_s_ves=geom.s_body_ves,
                   body_covers_shroud=geom.body_covers_shroud)
    for name, r in peaks.items():
        k = name.lower()
        out[f'{k}_peak_strain'] = r['peak_strain']
        out[f'{k}_peak_strain_s_material'] = r['s_material']
        out[f'{k}_peak_strain_s_station'] = r['s_station']
        out[f'{k}_peak_strain_step'] = r['step']
        out[f'{k}_peak_strain_shift'] = r['shift']
        out[f'{k}_peak_moment'] = r['peak_moment']
        # `frac_of_x2` only where there IS an X2. GD-Simple quotes against
        # Xb, and writing that under a column named for X2 would mislabel
        # the denominator in the artifact itself.
        if simple:
            out[f'{k}_frac_of_xb'] = r['frac_of_x2']
        else:
            out[f'{k}_frac_of_x2'] = r['frac_of_x2']
        out[f'{k}_peak_on_shroud'] = r['peak_on_shroud']
        # X1 and X5 are unbounded on their outer side. Written EMPTY rather
        # than as `inf`: a blank is a value a reader will not average, and
        # `inf` in a float column is exactly the sort of thing that survives
        # into a mean and turns a summary into nan.
        out[f'{k}_s_lo'] = '' if r['s_lo'] == float('-inf') else r['s_lo']
        out[f'{k}_s_hi'] = '' if r['s_hi'] == float('inf') else r['s_hi']
        out[f'{k}_n_elements'] = r['n_elements']
    return out

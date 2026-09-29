"""slay.report.junction -- strain and moment at a component/pipe junction,
and at fixed offsets either side of it. L8.

WHY A JUNCTION IS THE INTERESTING PLACE. A thick component does not fail on
its own body, where it is stiffest; it concentrates demand where its section
ENDS. The step in second moment forces a curvature discontinuity, and the
pipe just outboard of the weld carries it. Recording the body peak alone
misses the number the design is governed by.

JUNCTIONS ARE READ OFF THE MODEL, NOT OFF THE COMPONENT. They are the
element boundaries where the resolved SECTION changes -- exactly what the FE
sees, and therefore where the discontinuity actually is. Deriving them from
the ILS extent instead would be a second answer to the same question, and it
would drift the moment the mesher snapped a boundary anywhere but where the
geometry nominally put it. A component that shares its section with the pipe
(a neutral body) has no junction here, and that is correct: nothing steps.

SAMPLING INTERPOLATES WITHIN A BODY AND NEVER ACROSS THE STEP. Strain is
DISCONTINUOUS at a junction -- the same moment on two section moduli gives
two strains -- so interpolating through it manufactures a value that exists
nowhere. Within one body it is smooth, and there interpolation is not only
safe but necessary:

    AT THE RULED 2xOD MESH NO ELEMENT CENTRE EVER SITS AT 2, 4 OR 6 x OD FROM
    A JUNCTION. Element midpoints land at ODD multiples of 1xOD from it, so
    the requested offsets fall exactly between two of them. Taking "the
    element containing the point" put the -2xOD sample on the element centred
    1xOD away -- a row labelled 2xOD carrying the 1xOD number. Measured
    before the fix: the -2xOD probe and the junction probe returned the same
    element and therefore identical values.

So each probe interpolates between the two nearest element midpoints INSIDE
its own contiguous section run. Where the target lies beyond the last
midpoint of that run -- which is always true at the junction itself, and true
for any offset that overshoots a short component -- the probe CLAMPS to that
midpoint and says so in `clamped`. A clamped row is honest about being the
nearest available datum rather than the requested one; `s_elem` always says
where the number really came from.

THE JUNCTION ITSELF IS TWO SAMPLES, not one, for the same reason: the
element inboard (the component) and the element outboard (the pipe). Moment
is continuous across the step and the two should agree closely; strain is not
and the two should not. That difference is a RESULT, not a defect, and
collapsing it to one number would hide it.

SIGN CONVENTION. Offsets are signed in model `s`, which increases toward the
stinger. `-2` is two diameters toward the VESSEL from the junction, `+2` two
toward the stinger. `side` names it in body terms -- 'component' or 'pipe' --
read off the element the probe landed in, so it stays right whichever
junction is being measured and whichever way the component was placed.
"""

from __future__ import annotations

from dataclasses import dataclass

OFFSETS_OD = (-6.0, -4.0, -2.0, 2.0, 4.0, 6.0)


@dataclass(frozen=True)
class Junction:
    """A section step in the solved model."""
    index: int                 # 0, 1, ... in increasing s
    s: float                   # model s of the boundary
    OD_in: float               # section on the low-s side
    OD_out: float              # section on the high-s side
    owner_in: str
    owner_out: str

    @property
    def s_station(self) -> float:
        raise AttributeError('a Junction is MATERIAL; add the shift yourself')


@dataclass(frozen=True)
class Probe:
    """One sampled location."""
    junction: int              # which junction it is measured from
    offset_OD: float           # signed, in pipe diameters (0.0 at the junction)
    s: float                   # model s asked for
    s_station: float           # where that sat on the stinger
    s_elem: float              # midpoint of the element that answered
    strain: float
    moment: float              # N.m
    OD: float
    owner: str
    side: str                  # 'component' | 'pipe'
    in_model: bool
    clamped: bool = False      # the run ended before the requested offset


def junctions(problem, tol: float = 1e-9) -> tuple:
    """Every section step in the model, in increasing `s`.

    A step is an adjacent pair of elements whose resolved OD differs. The
    boundary is the node they share, and `problem.elements` is in `s` order
    because the mesher emits it that way.
    """
    secs = {s.index: s for s in problem.sections}
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    els = [(idx, n1, n2) for (idx, n1, n2, _o, _l) in problem.elements
           if idx in secs]
    els.sort(key=lambda e: 0.5 * (s_of[e[1]] + s_of[e[2]]))
    out = []
    for (a, b) in zip(els, els[1:]):
        sa, sb = secs[a[0]], secs[b[0]]
        if abs(sa.OD - sb.OD) <= tol:
            continue
        shared = {a[1], a[2]} & {b[1], b[2]}
        s_j = (s_of[shared.pop()] if shared
               else 0.5 * (s_of[a[2]] + s_of[b[1]]))
        out.append(Junction(index=len(out), s=s_j, OD_in=sa.OD, OD_out=sb.OD,
                            owner_in=sa.owner, owner_out=sb.owner))
    return tuple(out)


def _element_table(position, problem):
    """[(s_lo, s_hi, s_mid, eps, M, OD, owner)] in increasing s.

    Strain and moment are reported per element on the SAME grid by
    `solve.passage`, so they join on the element index without a lookup that
    could mis-pair them.
    """
    r = position.result
    secs = {s.index: s for s in problem.sections}
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    eps_of = {i: e for (i, _s, e) in r.strains}
    m_of = {i: m for (i, _s, m) in r.moments}
    rows = []
    for (idx, n1, n2, _o, _l) in problem.elements:
        if idx not in secs or idx not in eps_of:
            continue
        lo, hi = sorted((s_of[n1], s_of[n2]))
        rows.append((lo, hi, 0.5 * (lo + hi), eps_of[idx],
                     m_of.get(idx, float('nan')), secs[idx].OD,
                     secs[idx].owner))
    rows.sort()
    return rows


def _runs(rows):
    """Contiguous groups of elements sharing one section. The bodies."""
    out, cur = [], []
    for row in rows:
        if cur and (abs(cur[-1][5] - row[5]) > 1e-9 or cur[-1][6] != row[6]):
            out.append(cur)
            cur = []
        cur.append(row)
    if cur:
        out.append(cur)
    return out


def _containing(rows, s, prefer=0.0):
    """Index of the element containing `s`, or None.

    `prefer` breaks the tie when `s` lands exactly on a shared boundary:
    negative takes the lower element, positive the upper. Without it the
    answer depends on iteration order, which is not a physical rule.
    """
    hits = [i for i, r in enumerate(rows) if r[0] - 1e-9 <= s <= r[1] + 1e-9]
    if not hits:
        return None
    return hits[0] if prefer < 0 else hits[-1]


def _interp_in_run(run, s):
    """(strain, moment, s_used, clamped) from one body's element midpoints.

    Linear in the midpoints, which is the finest honest statement the element
    grid supports. Outside the run's midpoint range it clamps to the end and
    says so, rather than extrapolating a plastically saturated quantity past
    the data.
    """
    mids = [r[2] for r in run]
    if len(run) == 1 or s <= mids[0]:
        return (run[0][3], run[0][4], mids[0], s < mids[0] - 1e-9)
    if s >= mids[-1]:
        return (run[-1][3], run[-1][4], mids[-1], s > mids[-1] + 1e-9)
    for a, b in zip(run, run[1:]):
        if a[2] <= s <= b[2]:
            w = (s - a[2]) / (b[2] - a[2])
            return (a[3] + w * (b[3] - a[3]),
                    a[4] + w * (b[4] - a[4]), s, False)
    return (run[-1][3], run[-1][4], mids[-1], True)


def _side(owner: str) -> str:
    return 'pipe' if owner == 'pipe' else 'component'


def probes(position, problem, junction: Junction, OD: float,
           offsets=OFFSETS_OD) -> list:
    """Samples for one junction: both sides of it, then each offset.

    Offsets are in multiples of `OD` -- the PIPELINE diameter, not the
    component's. The component's own OD varies case to case, so measuring in
    it would make two rows of the dataset incomparable; the pipe's is the
    fixed ruler.
    """
    rows = _element_table(position, problem)
    runs = _runs(rows)
    out = []
    # The junction itself, from each side: the run on each side, clamped to
    # its end midpoint. Both are reported because strain steps here.
    for sgn in (-1.0, +1.0):
        out.append(_probe(junction, 0.0, junction.s, rows, runs, position,
                          prefer=sgn))
    for k in offsets:
        out.append(_probe(junction, k, junction.s + k * OD, rows, runs,
                          position, prefer=k))
    return out


def _probe(junction, k, s, rows, runs, position, prefer=0.0):
    i = _containing(rows, s, prefer)
    if i is None:
        return Probe(junction=junction.index, offset_OD=k, s=s,
                     s_station=s + position.shift, s_elem=float('nan'),
                     strain=float('nan'), moment=float('nan'),
                     OD=float('nan'), owner='', side='', in_model=False)
    row = rows[i]
    run = next(r for r in runs if row in r)
    eps, M, s_used, clamped = _interp_in_run(run, s)
    return Probe(junction=junction.index, offset_OD=k, s=s,
                 s_station=s + position.shift, s_elem=s_used,
                 strain=eps, moment=M, OD=row[5], owner=row[6],
                 side=_side(row[6]), in_model=True, clamped=clamped)


def body_peak(position, problem) -> tuple:
    """(strain, moment, s) of the worst element ON the component body.

    Empty-safe: a model with no component returns zeros rather than raising,
    because a plain-pipe row in the same dataset must still have the column.
    """
    rows = [r for r in _element_table(position, problem) if r[6] != 'pipe']
    if not rows:
        return (0.0, 0.0, 0.0)
    _lo, _hi, s_mid, eps, M, _od, _ow = max(rows, key=lambda r: r[3])
    return (eps, M, s_mid)


def stiffness_ratio(problem) -> float:
    """Component `I` over pipeline `I`, from the SOLVED sections.

    1.0 when nothing steps. Read off the model rather than recomputed from a
    component definition, so it describes what was actually solved --
    including any section the mesher resolved differently from the nominal.
    """
    secs = list(problem.sections)
    if not secs:
        return 1.0
    pipe = [s for s in secs if s.owner == 'pipe']
    comp = [s for s in secs if s.owner != 'pipe']
    if not pipe or not comp:
        return 1.0
    I_pipe = max(p.I for p in pipe)
    I_comp = max(c.I for c in comp)
    return I_comp / I_pipe if I_pipe > 0 else 1.0


def measure(position, problem, OD: float, offsets=OFFSETS_OD) -> list:
    """Every junction in the model, each with its full set of probes."""
    return [p for j in junctions(problem)
            for p in probes(position, problem, j, OD, offsets)]


def row(position, problem, OD: float, offsets=OFFSETS_OD) -> dict:
    """One flat dict per position: the dataset row this module exists for.

    Column names carry the junction index and the SIGNED offset, so
    `j1_p2OD_strain` is unambiguous about which junction and which side. A
    plain-pipe case has no junctions and gets the derived columns anyway --
    `stiffness_ratio` 1.0, empty body peak -- because a dataset whose columns
    depend on the row is not a dataset.
    """
    e_body, m_body, s_body = body_peak(position, problem)
    out = {'stiffness_ratio': stiffness_ratio(problem),
           'n_junctions': len(junctions(problem)),
           'body_peak_strain': e_body, 'body_peak_moment': m_body,
           'body_peak_s': s_body}
    # These three are PER-POSITION and are consumed as such -- by the
    # console table, and by `passage.body_peaks`, which reduces them to one
    # case-level answer WITH its step. `case_row` therefore drops them: at
    # case level `body_peak_strain` belongs to the peak group that carries a
    # step, and two modules writing one column silently overwrote it.
    for p in measure(position, problem, OD, offsets):
        tag = ('j%d_%s%gOD' % (p.junction, 'm' if p.offset_OD < 0 else 'p',
                               abs(p.offset_OD)))
        if p.offset_OD == 0.0:
            tag = 'j%d_at_%s' % (p.junction, p.side or 'na')
        out[tag + '_strain'] = p.strain
        out[tag + '_moment'] = p.moment
        out[tag + '_s'] = p.s
        out[tag + '_clamped'] = p.clamped
        # WHICH BODY THE PROBE LANDED IN. `Probe` has carried these since it
        # was written and `row` dropped them, so a consumer reading the file
        # could not tell which side of a section step a sample was on -- and
        # a profile drawn from it joined points across a discontinuity that
        # strain genuinely has.
        out[tag + '_side'] = p.side
        out[tag + '_owner'] = p.owner
    return out


def case_row(rows, env_index: int) -> dict:
    """One dataset row per CASE, from every position's `row()`.

    TWO READINGS OF THE SAME PASSAGE, because they answer different
    questions and only one of them is what a reader usually assumes:

      SNAPSHOT (bare column names) -- every value as it stood at the
        envelope position. Self-consistent: one real instant of one lay.
      PER-LOCATION ENVELOPE (`_env`) -- the worst each location saw at ANY
        position. Not one instant; a design envelope assembled from several.

    They differ, and by a lot at any location that does not govern. Measured
    on GD-TP: the trailing junction reads 0.3297% at the envelope position
    but 0.4620% at its own worst, when the trailing edge sits on SR2 -- the
    snapshot understates it by 40%. A model trained on the snapshot alone
    would learn that the trailing junction is mild; it is not, it merely
    peaks somewhere else.

    Both come from the same solve, so carrying both costs nothing but
    columns. `_s` and `_clamped` stay snapshot-only: a location and a
    clamping flag are properties of a position, and maxing them would be
    meaningless.
    """
    live = [r for r in rows if r]
    if not live:
        return {}
    # See `row`: the per-position body peak is reduced by
    # `passage.body_peaks`, which owns the case-level column and its step.
    drop = ('body_peak_strain', 'body_peak_moment', 'body_peak_s')
    snap = {k: v for k, v in (rows[env_index] or live[0]).items()
            if k not in drop}
    out = dict(snap)
    for k in snap:
        if not (k.endswith('_strain') or k.endswith('_moment')):
            continue
        vals = [r[k] for r in live if k in r and r[k] == r[k]]   # drop NaN
        out[k + '_env'] = max(vals) if vals else float('nan')
    return out

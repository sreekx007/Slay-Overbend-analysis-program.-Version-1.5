"""slay.report.passage -- measuring a solved passage. L8.

WHAT A PASSAGE MEASUREMENT IS FOR. A sweep returns one `Result` per lay
position and a `Result` knows nothing about the sweep it came from. This
module turns that list into rows a reader can compare, and its whole reason
for existing is the ENVELOPE: the worst value over the passage, which is not
in general the value at any position you would have picked in advance.

Measured on the reference GD-TP case (R = 85 m, 9 m spacing, 120 MT): the
start position reports 0.4597% and the worst position 0.5482%, at the shift
where the component's leading edge crosses SR2. A single-position solve at
the start is 19% LOW. That number is the argument for sliding.

STATION COORDINATES, NOT MATERIAL ONES, and this is the thing to get right.
`s` in a Problem is a MATERIAL coordinate: it labels a point on the pipe and
travels with it. After the pipeline advances by `shift`, material `s` sits at
station position `s + shift`. So a strain reported at material `s` is at a
DIFFERENT PLACE ON THE STINGER at every position, and a table of material-`s`
peaks down a passage compares nothing to nothing.

Every row here therefore carries both, and the reporting ZONE is applied in
station coordinates. The failure this prevents was observed: read in material
coordinates a plain-pipe passage appears to have its peak frozen at one
element while the value decays, which looks like a solver defect and is not.

THE ZONE. Strains at the last three stinger rollers are excluded, as ruled on
21 Sep 2026. D6 made the terminal station a contact slot, which over-
constrains the tip and concentrates strain there; the exclusion is what makes
that harmless. The zone is carried on every record so no reader has to infer
which one was used.

WHAT THIS MODULE DOES NOT DO. It does not solve, it does not sweep, and it
computes no geometry of its own -- a report that derives a shape asserts a
result nothing solved for. Every number here is read off a `Result` or off
the `Scene` that was solved.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field

DROP_AT_TIP = 3            # SR5, SR6, SR7 excluded -- the 21 Sep ruling


def zone(scene, drop: int = DROP_AT_TIP) -> tuple:
    """(s_max, label) -- the reporting window, in STATION coordinates.

    Everything strictly inboard of the last `drop` stinger rollers. Raises
    rather than silently reporting the whole model if the scene has too few
    stinger stations to drop that many.
    """
    sr = sorted((s for s in scene.stations if s.name.startswith('SR')),
                key=lambda t: t.s_arc)
    if drop <= 0:
        return (float('inf'), 'whole model')
    if len(sr) <= drop:
        raise ValueError(
            f'cannot drop the last {drop} stinger rollers: the scene has '
            f'only {len(sr)}')
    cut = sr[-drop]
    return cut.s_arc, f'{cut.name} and beyond excluded'


def _rows(position, scene=None):
    """(s_station, s_material, eps) per element, in station coordinates."""
    return [(s + position.shift, s, e) for (_i, s, e) in position.result.strains]


def _moment_rows(position):
    """(s_station, s_material, |M|) per element.

    MAGNITUDE, because a passage envelope is about how hard the pipe is bent
    and sagging between rollers puts the moment through zero and out the
    other side. Taking the signed maximum would report the largest hogging
    moment and silently ignore a larger sagging one.
    """
    return [(s + position.shift, s, abs(m))
            for (_i, s, m) in getattr(position.result, 'moments', ())]


def band_peak_moment(position, s_max: float) -> tuple:
    """(|M|, s_station, s_material) of the worst element inside the zone."""
    rows = [r for r in _moment_rows(position) if r[0] < s_max]
    if not rows:
        return (0.0, 0.0, 0.0)
    s_sta, s_mat, m = max(rows, key=lambda r: r[2])
    return (m, s_sta, s_mat)


def band_peak(position, s_max: float) -> tuple:
    """(eps, s_station, s_material) of the worst element inside the zone.

    (0.0, 0.0, 0.0) when the position has no strains at all -- a diverged
    position reports a miss, it does not raise. A passage wants to know which
    position failed and carry on, and that is also true of measuring one.
    """
    rows = [r for r in _rows(position) if r[0] < s_max]
    if not rows:
        return (0.0, 0.0, 0.0)
    s_sta, s_mat, eps = max(rows, key=lambda r: r[2])
    return (eps, s_sta, s_mat)


def station_strains(position, scene) -> dict:
    """Worst strain within half a roller spacing of each station.

    Keyed by station name and looked up in STATION coordinates, so the same
    key means the same place on the stinger at every position -- which is the
    only way a passage table reads.
    """
    out, half = {}, scene.spacing / 2.0
    rows = _rows(position)
    for st in scene.stations:
        near = [e for (s_sta, _s_mat, e) in rows if abs(s_sta - st.s_arc) < half]
        if near:
            out[st.name] = max(near)
    return out


def component_span(position, L_comp: float) -> tuple:
    """(lead, trail) station coordinates of the component at this position.

    Read off the `Position`, which the sweep driver already computed from the
    placement it used. Not recomputed here: two answers to where the
    component is would be one too many.
    """
    if L_comp <= 0.0:
        return (None, None)
    return (position.s_lead, position.s_trail)


@dataclass(frozen=True)
class PositionRecord:
    """One measured lay position. Flat, so it writes straight to CSV."""
    index: int
    shift: float               # m the pipeline has advanced
    status: str
    converged: bool
    peak_strain: float         # in the zone
    peak_s_station: float      # where on the stinger
    peak_s_material: float     # which material point
    peak_moment: float = 0.0           # N.m, |M|, in the zone
    peak_moment_s_station: float = 0.0
    peak_moment_s_material: float = 0.0
    s_lead: float = None       # component leading edge, station coords
    s_trail: float = None
    zone_s_max: float = 0.0
    zone_label: str = ''
    n_active: int = 0
    n_slots: int = 0
    released: tuple = ()
    stations: dict = field(default_factory=dict)


def record(position, scene, L_comp: float = 0.0,
           drop: int = DROP_AT_TIP) -> PositionRecord:
    """Measure one solved position."""
    s_max, label = zone(scene, drop)
    eps, s_sta, s_mat = band_peak(position, s_max)
    mom, m_sta, m_mat = band_peak_moment(position, s_max)
    lead, trail = component_span(position, L_comp)
    r = position.result
    return PositionRecord(
        index=position.index, shift=position.shift, status=r.status,
        converged=r.converged, peak_strain=eps, peak_s_station=s_sta,
        peak_s_material=s_mat, peak_moment=mom,
        peak_moment_s_station=m_sta, peak_moment_s_material=m_mat,
        s_lead=lead, s_trail=trail,
        zone_s_max=s_max, zone_label=label,
        n_active=int(sum(r.active)), n_slots=len(r.active),
        released=tuple(r.released), stations=station_strains(position, scene))


def measure(positions, scene, L_comp: float = 0.0,
            drop: int = DROP_AT_TIP) -> list:
    """Measure a whole passage. One record per position, in order."""
    return [record(p, scene, L_comp, drop) for p in positions]


def envelope(records) -> PositionRecord:
    """The worst CONVERGED position of the passage.

    THE POINT OF THE WHOLE EXERCISE. Diverged positions are excluded because
    their peak is a miss, not a low number, and letting one win the max would
    report the failure as the answer. Raises if nothing converged -- a
    passage with no converged position has no envelope, and returning a zero
    would read as a safe result.
    """
    ok = [r for r in records if r.converged]
    if not ok:
        raise ValueError('no converged position in this passage: '
                         + ', '.join(f'{r.index}:{r.status}' for r in records))
    return max(ok, key=lambda r: r.peak_strain)


def station_envelope(records) -> dict:
    """Worst strain seen at each station over the whole passage.

    MAX over positions, never a sum -- the same rule as the contact surface
    (G3). Each position is one moment in time; a station's design value is
    the worst moment, not an accumulation over them.
    """
    out = {}
    for r in records:
        if not r.converged:
            continue
        for name, eps in r.stations.items():
            out[name] = max(out.get(name, 0.0), eps)
    return out


def write_case_csv(rows, path, strict: bool = True) -> dict:
    """Write case rows against the declared schema, and the schema beside it.

    THE CONTRACT IS ENFORCED, NOT DOCUMENTED. `strict` refuses to write a
    column `report.schema` does not describe, which is the whole point: the
    column set is open -- stations and junctions depend on the layout -- but
    the OPENNESS is declared as patterns, so a new junction passes and a
    misspelt one is caught. Before this, columns were the union of whatever
    dicts were passed in and nothing could tell the two apart.

    Writes `<path>` and `<path>.schema.json`, so a reader never needs this
    source to interpret a file: units, dtypes and descriptions travel with
    the data.
    """
    import json
    from pathlib import Path

    from slay.report import schema as sc

    if not rows:
        raise ValueError('no rows to write')
    seen, cols = set(), []
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    bad = sc.unknown(cols)
    if bad and strict:
        raise ValueError(
            f'{len(bad)} column(s) the schema does not describe: '
            f'{bad[:8]}{" ..." if len(bad) > 8 else ""}. Add a Field or a '
            f'pattern to slay.report.schema, or fix the name.')
    # Declared order first, then anything patterned, so a file is readable
    # left to right and two files sort their shared columns the same way.
    fixed = [c for c in sc.header() if c in seen]
    rest = sorted(c for c in cols if c not in set(fixed))
    order = fixed + rest
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=order, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: _flat(v) for k, v in r.items()})
    meta = sc.as_dict()
    meta['columns'] = order
    meta['n_rows'] = len(rows)
    meta['unknown_columns'] = bad
    Path(str(path) + '.schema.json').write_text(json.dumps(meta, indent=1))
    return meta


def to_csv(records, path, extra: dict = None, per_row=None) -> None:
    """Write the passage as one row per position.

    `extra` holds the case parameters -- R, spacing, tension, component --
    repeated on every row. A results file that does not say which case it is
    cannot be joined to anything later, and this dataset is meant to be.

    `per_row` is one dict per record, merged in as its own columns: the
    junction measurements, which differ position by position. THE COLUMN SET
    IS THE UNION over every row IN THIS FILE, and missing keys are written
    blank, so the file is rectangular even when a component enters or leaves
    the model mid-passage. Separate files still differ from each other -- a
    plain-pipe run genuinely has no junction columns, and the derived
    columns (`stiffness_ratio` 1.0, `n_junctions` 0) are what make the two
    joinable.
    """
    extra = dict(extra or {})
    per_row = list(per_row or [{}] * len(records))
    if len(per_row) != len(records):
        raise ValueError(f'per_row has {len(per_row)} entries for '
                         f'{len(records)} records')
    names = sorted({n for r in records for n in r.stations})
    extras = sorted({k for d in per_row for k in d})
    head = ([k for k in extra]
            + [f.name for f in _fields(records[0]) if f.name != 'stations']
            + [f'eps_{n}' for n in names] + extras)
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(head)
        for r, px in zip(records, per_row):
            d = asdict(r)
            sta = d.pop('stations')
            w.writerow(list(extra.values())
                       + [_flat(d[f.name]) for f in _fields(r)
                          if f.name != 'stations']
                       + [sta.get(n, '') for n in names]
                       + [px.get(k, '') for k in extras])


def _fields(rec):
    from dataclasses import fields
    return fields(rec)


def _flat(v):
    return ';'.join(map(str, v)) if isinstance(v, tuple) else v


def nearest_station(scene, s_station: float) -> tuple:
    """(name, signed offset) of the roller nearest a STATION coordinate.

    The human-readable half of a location. `s_station = 9.62` means nothing
    to a reader; 'SR2 +0.62 m' means the leading edge has just crossed the
    second stinger roller.
    """
    if not scene.stations:
        return ('', 0.0)
    st = min(scene.stations, key=lambda t: abs(t.s_arc - s_station))
    return (st.name, s_station - st.s_arc)


def _peak_over(records, value, s_sta, s_mat, scene) -> dict:
    """The seven columns of one peak group, from per-position records.

    MAX OVER POSITIONS AS WELL AS OVER THE MODEL, and the step that won is
    carried out with it. A peak with no step cannot be checked, found again,
    or plotted -- and the whole argument for sweeping is that the winning
    step is not one anybody would have picked.
    """
    live = [r for r in records if r.converged]
    if not live:
        return dict(value=0.0, s_material=0.0, s_station=0.0, station='',
                    station_offset=0.0, step=-1, shift=0.0)
    best = max(live, key=lambda r: getattr(r, value))
    sta, off = nearest_station(scene, getattr(best, s_sta))
    return dict(value=getattr(best, value),
                s_material=getattr(best, s_mat),
                s_station=getattr(best, s_sta),
                station=sta, station_offset=off,
                step=best.index, shift=best.shift)


def peaks(records, scene) -> dict:
    """Flat columns for every peak group the schema declares.

    `report.schema.peak_group` generates the seven column names; this fills
    them. The two must agree, and `test_schema` asserts that they do rather
    than leaving it to inspection -- which is exactly the failure the schema
    exists to end.
    """
    out = {}
    for prefix, value, s_sta, s_mat in (
            ('peak_strain', 'peak_strain', 'peak_s_station', 'peak_s_material'),
            ('peak_moment', 'peak_moment', 'peak_moment_s_station',
             'peak_moment_s_material')):
        got = _peak_over(records, value, s_sta, s_mat, scene)
        out[prefix] = got.pop('value')
        out.update({f'{prefix}_{k}': v for k, v in got.items()})
    return out


def contact_lift(positions, problems, OD: float) -> dict:
    """Deepest centreline lift any station saw, and where and when.

    WHY IT IS A COLUMN AT ALL. For a shroud the lift IS the component: GD-SH
    adds no bending stiffness, so a file without this cannot tell its case
    from bare pipe, and every other number would still look plausible.

    Swept, not sampled: at the LEADING EDGE of a tapered component the lift
    is correctly ZERO -- the taper terminates flush with the pipe OD -- so
    one position proves nothing.
    """
    best = (0.0, '', -1)
    for pos, pr in zip(positions, problems):
        if pr is None or not pos.converged:
            continue
        for t in pr.contacts:
            if abs(t.lift) > best[0]:
                best = (abs(t.lift), t.station, pos.index)
    return {'contact_lift_max': best[0], 'contact_lift_station': best[1],
            'contact_lift_step': best[2]}


def station_positions(scene) -> dict:
    """{`s_<name>`: arc position} for every station.

    Without these a consumer has `eps_SR2_env` and no way to place SR2;
    deriving it from `spacing` assumes a layout the file never states.
    """
    return {f's_{st.name}': st.s_arc for st in scene.stations}


def body_peaks(records, scene, junction_rows) -> dict:
    """The same seven columns for the peaks ON THE COMPONENT BODY.

    Taken from the per-position junction rows, because which elements belong
    to the body is a question about SECTIONS and only `report.junction` binds
    those. Zeroed for a case with no component, so a plain-pipe row still
    carries the columns -- a dataset whose columns depend on the row is not a
    dataset.
    """
    out = {}
    for prefix, key in (('body_peak_strain', 'body_peak_strain'),
                        ('body_peak_moment', 'body_peak_moment')):
        best_i, best_v, best_s = -1, 0.0, 0.0
        for i, (rec, jr_) in enumerate(zip(records, junction_rows)):
            if not rec.converged or not jr_:
                continue
            v = abs(jr_.get(key) or 0.0)
            if v > best_v:
                best_i, best_v, best_s = i, v, jr_.get('body_peak_s', 0.0)
        if best_i < 0:
            out[prefix] = 0.0
            out.update({f'{prefix}_{k}': z for k, z in
                        (('s_material', 0.0), ('s_station', 0.0),
                         ('station', ''), ('station_offset', 0.0),
                         ('step', -1), ('shift', 0.0))})
            continue
        rec = records[best_i]
        s_station = best_s + rec.shift
        sta, off = nearest_station(scene, s_station)
        out[prefix] = best_v
        out.update({f'{prefix}_s_material': best_s,
                    f'{prefix}_s_station': s_station,
                    f'{prefix}_station': sta,
                    f'{prefix}_station_offset': off,
                    f'{prefix}_step': rec.index,
                    f'{prefix}_shift': rec.shift})
    return out

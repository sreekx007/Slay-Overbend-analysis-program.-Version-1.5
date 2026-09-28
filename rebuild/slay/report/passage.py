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
    lead, trail = component_span(position, L_comp)
    r = position.result
    return PositionRecord(
        index=position.index, shift=position.shift, status=r.status,
        converged=r.converged, peak_strain=eps, peak_s_station=s_sta,
        peak_s_material=s_mat, s_lead=lead, s_trail=trail,
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


def to_csv(records, path, extra: dict = None) -> None:
    """Write the passage as one row per position.

    `extra` holds the case parameters -- R, spacing, tension, component --
    repeated on every row. A results file that does not say which case it is
    cannot be joined to anything later, and this dataset is meant to be.
    """
    extra = dict(extra or {})
    names = sorted({n for r in records for n in r.stations})
    head = ([k for k in extra]
            + [f.name for f in _fields(records[0]) if f.name != 'stations']
            + [f'eps_{n}' for n in names])
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(head)
        for r in records:
            d = asdict(r)
            sta = d.pop('stations')
            w.writerow(list(extra.values())
                       + [_flat(d[f.name]) for f in _fields(r)
                          if f.name != 'stations']
                       + [sta.get(n, '') for n in names])


def _fields(rec):
    from dataclasses import fields
    return fields(rec)


def _flat(v):
    return ';'.join(map(str, v)) if isinstance(v, tuple) else v

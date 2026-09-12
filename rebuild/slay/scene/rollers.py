"""slay.scene.rollers -- the roller stations, in order along the lay path.

A station is a place where something is done to the pipe. Three kinds, and
the distinction is not cosmetic -- each is handled by a different mechanism
downstream:

    CONTACT   a roller bears on the pipe. One-sided ones push only and let
              the pipe lift off; bidirectional ones also hold it down.
    FIXED     all DOF restrained. The model's anchor. Not a contact slot.
    LOAD      lay tension is applied here, along this station's OWN tangent.
              No roller acts here at all.

LAYOUT (ruled 12 Sep 2026), at the defaults n_vr=5, n_sr=6, spacing 8 m:

    name   role          s_arc      x       y    note
    VR5    FIXED         -40.0   +40.0     0    all DOF restrained
    VR4    CONTACT       -32.0   +32.0     0    bidirectional
    VR3    CONTACT       -24.0   +24.0     0    bidirectional
    VR2    CONTACT       -16.0   +16.0     0    one-sided, uplift allowed
    VR1    CONTACT        -8.0    +8.0     0    one-sided, first inboard of SR1
    SR1    CONTACT         0.0      0.0    0    tangency, on the deck line
    SR2    CONTACT        +8.0   -7.988  0.376  first station on the curve
    ...
    SR6    CONTACT       +40.0  -38.540  9.239
    SR7    LOAD          +48.0  -45.489 13.197  tension only, no contact

THE TWO COUNTS FOLLOW DIFFERENT RULES, DELIBERATELY. Each end has exactly
one terminal station bearing no contact -- VR5 restrains, SR7 is loaded --
but `n_vr` INCLUDES its terminal and `n_sr` EXCLUDES its terminal. So the
defaults describe 5 vessel stations (4 contact) and 7 stinger stations
(6 contact). Reading one count's rule from the other is an off-by-one in
the model's supports; `slay_config.yaml` states both beside their values.

WHY SR7 EXISTS. Tension must be applied at the true departure point, using
that point's own tangent. Applying it at the SR7 node with SR6's tangent
put a spurious transverse force on the tip and reported 2.46% strain at SR6
against a ~0.83% reference -- a 3x error, caught in first validation of the
old implementation.

GLOSSARY
    s_arc       m. Arc length from SR1 along the lay path. Negative on the
                deck, positive on the stinger.
    x, y        m. World position. +x toward the vessel, +y down.
    normal      unit vector from the roller toward the pipe.
    radius      m. Roller radius. R is measured to the roller CENTRELINE, so
                this is what stands between that locus and the pipe.
    one_sided   True where the roller may push but not hold down. Meaningful
                only for CONTACT stations; `role` is what decides behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import config

from slay.scene.path import LayPath


class StationRole(str, Enum):
    """What is done to the pipe at a station.

    Kept distinct from `one_sided` on purpose: the one-sided set alone
    cannot tell a bidirectional contact roller from a station that does no
    contact at all, because both are simply absent from it.
    """
    CONTACT = 'contact'
    FIXED = 'fixed'
    LOAD = 'load'


@dataclass(frozen=True)
class Station:
    name: str
    s_arc: float
    x: float
    y: float
    radius: float
    normal: tuple
    role: StationRole
    one_sided: bool = False

    @property
    def is_contact(self) -> bool:
        return self.role is StationRole.CONTACT


def _vessel_names(n_vr: int) -> list:
    """VR1 nearest the stinger, numbering increasing inboard."""
    return [f'VR{j}' for j in range(1, n_vr + 1)]


def _stinger_names(n_sr: int) -> list:
    """SR1 at the tangency, through SR{n_sr}, plus the tension station."""
    return [f'SR{i}' for i in range(1, n_sr + 2)]


def roller_stations(path: LayPath,
                    n_sr: int = None,
                    n_vr: int = None,
                    spacing: float = None,
                    radii: dict = None,
                    one_sided: frozenset = None) -> list:
    """Every station, ordered by ascending arc length (vessel to stinger tip).

    `radii` overrides individual rollers by name, e.g. {'SR3': 0.35}. Any
    station not named takes `config.ROLLER_RADIUS_DEF`, which applies to
    every roller, stinger and vessel alike.

    `one_sided` defaults to the stored RULE -- every SR, plus the named
    vessel pair -- resolved against THIS call's n_sr via
    `config.one_sided_rollers`. Not the pre-resolved constant: that is fixed
    at import against config's own n_sr, so building a scene with a larger
    n_sr would silently leave the extra stinger rollers bidirectional.
    """
    n_sr = config.N_SR if n_sr is None else n_sr
    n_vr = config.N_VR if n_vr is None else n_vr
    spacing = config.ROLLER_SPACING if spacing is None else spacing
    radii = radii or {}
    if one_sided is None:
        # RESOLVED FOR THE REQUESTED n_sr, not read off the pre-resolved
        # constant. That constant is fixed at import against config's own
        # n_sr, so at n_sr=9 it would leave SR7..SR9 bidirectional -- the
        # staleness the rule form exists to prevent, reintroduced by reading
        # the resolution instead of the rule.
        one_sided = config.one_sided_rollers(n_sr)

    if n_vr < 2:
        raise ValueError(
            f'n_vr must be at least 2 (got {n_vr}): one fixed station plus at '
            f'least one contact roller. n_vr counts ALL vessel stations, the '
            f'fixed one included.')
    if n_sr < 1:
        raise ValueError(f'n_sr must be at least 1, got {n_sr}')

    def radius_of(name):
        return float(radii.get(name, config.ROLLER_RADIUS_DEF))

    out = []

    # Vessel side, furthest first so the list ascends in s.
    for j in range(n_vr, 0, -1):
        name = f'VR{j}'
        s = -j * spacing
        x, y = path.position(s)
        out.append(Station(
            name=name, s_arc=s, x=x, y=y,
            radius=radius_of(name), normal=path.normal(s),
            role=StationRole.FIXED if j == n_vr else StationRole.CONTACT,
            one_sided=(j != n_vr and name in one_sided)))

    # Stinger side. The last name is the tension station, not a roller.
    names = _stinger_names(n_sr)
    for i, name in enumerate(names):
        s = i * spacing
        x, y = path.position(s)
        is_tension = (i == len(names) - 1)
        out.append(Station(
            name=name, s_arc=s, x=x, y=y,
            radius=radius_of(name), normal=path.normal(s),
            role=StationRole.LOAD if is_tension else StationRole.CONTACT,
            one_sided=(not is_tension and name in one_sided)))

    return out


def fixed_station(stations: list) -> Station:
    """The single all-DOF-restrained station."""
    found = [s for s in stations if s.role is StationRole.FIXED]
    if len(found) != 1:
        raise ValueError(f'expected exactly one FIXED station, got {len(found)}')
    return found[0]


def load_station(stations: list) -> Station:
    """The single tension-application station."""
    found = [s for s in stations if s.role is StationRole.LOAD]
    if len(found) != 1:
        raise ValueError(f'expected exactly one LOAD station, got {len(found)}')
    return found[0]


def contact_stations(stations: list) -> list:
    """Only the stations a roller actually bears on."""
    return [s for s in stations if s.is_contact]

"""slay.physics.capacity -- how much of the section a load has already spent. L5.

WHY THIS EXISTS. Three cases in the 200-case matrix failed with
`CUTBACK EXHAUSTED at lam=0.0000`, which says where the solver gave up and
nothing about why. Two were reachable and are fixed by seeding (L081). The
third is not reachable at all, and no amount of solver work will make it so:
at 160 MT on 168.3 mm pipe the LAY TENSION ALONE consumes 80.2% of the
section's yield capacity, before a single degree of bending. Add the bending
a 60 m radius imposes and the elastic prediction is 162% of yield -- the
section is fully plastic, its bending tangent stiffness has collapsed, and
there is nothing left to react the load with.

That is plastic collapse, a physical limit. A solver that reported it as a
convergence failure was telling the truth in a language nobody could act on.

THE POINT IS TO TELL THE TWO APART. A case that fails because the load path
was badly sequenced is a defect to fix. A case that fails because the pipe
would tear in half is a case that should not have been asked. They arrive
with identical status strings, so the distinction has to be computed.

THIS IS A SCREEN, NOT A CODE CHECK. It is first-yield arithmetic on the
nominal section -- no partial safety factors, no ovalisation, no DNV
utilisation. It exists to explain a failure, never to qualify a design.
"""

from __future__ import annotations

import math

import config

# Above this the membrane stress has eaten most of the section and the
# bending capacity that is left is small and softening. Chosen as the level
# at which the matrix's own failures start rather than from any code: the
# reachable cases sit at 12.9% and the unreachable one at 80.2%, so anything
# between them separates the two. It is a reporting threshold and nothing
# downstream is gated on it.
HIGH_UTILISATION = 0.5


def steel_area(OD: float, t_wall: float) -> float:
    """Cross-sectional area of the pipe wall, m^2."""
    if t_wall <= 0 or OD <= 2 * t_wall:
        raise ValueError(f'a {OD} m pipe cannot have a {t_wall} m wall')
    return math.pi / 4.0 * (OD ** 2 - (OD - 2.0 * t_wall) ** 2)


def membrane_stress(OD: float, t_wall: float, tension: float) -> float:
    """Axial stress from the lay tension alone, Pa. `tension` in NEWTONS."""
    return tension / steel_area(OD, t_wall)


def bending_stress(OD: float, R: float) -> float:
    """Elastic extreme-fibre bending stress at radius `R`, Pa.

    ELASTIC PREDICTION, deliberately. Past yield it is not what the pipe
    carries -- it is what the pipe would have to carry if it stayed elastic,
    which is exactly the number that says whether it can.
    """
    if R <= 0:
        raise ValueError(f'stinger radius must be positive, got {R}')
    return config.STEEL_E * (OD / 2.0) / R


def utilisation(OD: float, t_wall: float, tension: float, sigma_y: float,
                R: float = None) -> dict:
    """What fraction of first yield the loads have spent.

    `membrane` is tension alone. `combined` adds the elastic bending a
    radius `R` would impose, when one is given. Over 1.0 means the section
    cannot stay elastic; well over 1.0 with a high `membrane` means it has
    no bending capacity left at all.
    """
    if sigma_y <= 0:
        raise ValueError(f'yield stress must be positive, got {sigma_y}')
    sm = membrane_stress(OD, t_wall, tension)
    out = dict(area=steel_area(OD, t_wall), membrane_stress=sm,
               membrane=sm / sigma_y, sigma_y=sigma_y)
    if R is not None:
        sb = bending_stress(OD, R)
        out.update(bending_stress=sb, combined=(sm + sb) / sigma_y)
    return out


def explain_failure(OD: float, t_wall: float, tension: float, sigma_y: float,
                    R: float = None) -> str:
    """A physical reason for a failure, or '' when the loads do not give one.

    Empty is the important half: a case whose loads are comfortable and that
    still failed is a SOLVER problem, and saying nothing here keeps it
    visible as one rather than dressing it up as physics.
    """
    try:
        u = utilisation(OD, t_wall, tension, sigma_y, R)
    except ValueError:
        return ''
    if u['membrane'] < HIGH_UTILISATION:
        return ''
    msg = (f'BEYOND SECTION CAPACITY: lay tension alone is '
           f'{100 * u["membrane"]:.1f}% of first yield '
           f'({u["membrane_stress"] / 1e6:.0f} of {sigma_y / 1e6:.0f} MPa) '
           f'on a {1000 * OD:.1f} x {1000 * t_wall:.1f} mm section')
    if 'combined' in u:
        msg += (f'; with the bending a {R:.0f} m radius imposes the elastic '
                f'demand is {100 * u["combined"]:.0f}% of yield, so the '
                f'section is fully plastic and has no bending stiffness '
                f'left to react the load')
    return msg + '. Not a convergence defect.'

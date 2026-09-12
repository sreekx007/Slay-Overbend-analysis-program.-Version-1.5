"""slay.scene.path -- the geometric spine: where the pipe's path goes.

The lay path is ONE continuous curve through the world, covering both the
straight vessel deck and the curved stinger. It is parameterised on ARC
LENGTH `s`, measured from SR1:

    s < 0   the deck, straight, toward the vessel interior
    s = 0   SR1, the tangency station
    s > 0   the stinger arc, curving down toward the seabed

One object rather than a deck object and an arc object, because every
consumer wants "where is the path at s" and a two-object split invites
asking the wrong one near s = 0. The dispatch happens here, once.

WHAT THIS IS NOT. This is the locus of ROLLER CENTRES -- the geometry the
lay configuration defines. It is NOT where the pipe is. The pipe bridges
between rollers, sags, and lifts off; its position is what the solver
computes. A figure that draws "the pipe" from these formulas asserts a
shape nothing solved for, which is the error tracker item 27 records.

COORDINATE FRAME (confirmed 12 Sep 2026)
----------------------------------------
    +x  toward the VESSEL          +y  DOWN, toward the seabed
    +z  INTO the page

This is RIGHT-handed: x_hat cross y_hat = z_hat, right -> down -> into the
page. Tracker item 28 calls the frame left-handed, which is true only under
the unstated assumption that +z comes out of the page; declaring +z inward
makes it ordinary and every standard vector identity applies unchanged.

THE ONE CONSEQUENCE WORTH REMEMBERING: positive rotation about +z appears
CLOCKWISE to a viewer. Right-hand rule with the thumb into the screen curls
from +x toward +y, i.e. right toward down. So positive moment, positive
nodal rotation and positive curvature all read clockwise on a plot -- the
one place a reader's intuition silently disagrees with the code.

Because +x is toward the vessel and the stinger lies at negative x, a plot
drawn with x rightward puts the stinger on the LEFT and the vessel on the
RIGHT with no axis flip: the starboard view, correct by construction. Only
the y-axis is inverted for display, and the data is never negated.

ARC LENGTH RUNS OPPOSITE TO x. `s` increases toward the stinger (the
direction the pipe travels); `x` increases toward the vessel. So ds/dx < 0
everywhere, and the minus sign lives in this module and nowhere else --
that containment is why the conversion is here rather than at each call
site.

GLOSSARY
    s           m. Arc length along the lay path from SR1. Negative on the
                deck, positive on the stinger.
    theta       rad. Turn angle of the arc, 0 at SR1. Only defined for s>=0.
    R           m. Stinger radius, measured to the ROLLER CENTRELINE -- not
                to the pipe, and not to the roller surface.
    tangent     unit vector in the direction of INCREASING s, i.e. pointing
                toward the stinger tip.
    normal      unit vector from the roller surface TOWARD the pipe: up and
                away from the arc centre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LayPath:
    """Deck plus stinger arc, as one curve parameterised on arc length."""

    R: float

    def __post_init__(self):
        if self.R <= 0:
            raise ValueError(f'stinger radius must be positive, got {self.R}')

    # -- angle ------------------------------------------------------------
    def theta(self, s: float) -> float:
        """Turn angle at arc position `s`. Zero on the deck and at SR1."""
        return max(s, 0.0) / self.R

    # -- geometry ---------------------------------------------------------
    def position(self, s: float) -> tuple:
        """(x, y) at arc position `s`.

        On the deck the pipe runs straight at y=0, and moving in +s moves in
        -x, so x = -s. On the arc, x = -R sin(theta) and y = R(1 - cos theta)
        -- x negative because the stinger lies toward -x, y positive because
        the arc descends and +y is down.
        """
        if s <= 0.0:
            return (-s, 0.0)
        th = self.theta(s)
        return (-self.R * math.sin(th), self.R * (1.0 - math.cos(th)))

    def tangent(self, s: float) -> tuple:
        """Unit vector in the direction of INCREASING s.

        Differentiating `position` with respect to s: on the deck (-1, 0),
        on the arc (-cos theta, sin theta). Both point toward the stinger
        tip, and they agree at s=0, so the path is tangent-continuous where
        the deck meets the arc.

        THE DIRECTION IS LOAD-BEARING. `normal` is this vector rotated, so
        reversing the tangent silently inverts the normal -- the hazard
        tracker item 28 names. It is asserted in the tests, not assumed.
        """
        if s <= 0.0:
            return (-1.0, 0.0)
        th = self.theta(s)
        return (-math.cos(th), math.sin(th))

    def normal(self, s: float) -> tuple:
        """Unit vector from the roller surface toward the pipe.

        The tangent rotated +90 degrees about +z, which in this frame is
        (x, y) -> (-y, x) -- the ordinary right-handed rotation, available
        unchanged because +z points into the page.

        On the arc that gives (-sin theta, -cos theta), matching the old
        implementation. At theta=0 it is (0, -1): -y is upward, so the
        roller pushes the pipe up, which is what a roller does.
        """
        tx, ty = self.tangent(s)
        return (-ty, tx)

    # -- extremes ---------------------------------------------------------
    def is_on_arc(self, s: float) -> bool:
        return s > 0.0

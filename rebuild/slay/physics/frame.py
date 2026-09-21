"""slay.physics.frame -- the ONE crossing from world vectors to model DOFs.

`scene` speaks WORLD: `+x` toward the vessel, `+y` down. `model`, `physics`
and `solve` speak MODEL: `s` is arc length increasing toward the stinger, so

    x_world = -(s + u_s)        y_world = y + u_y

A vector read off the Scene -- `path.normal(s)`, `path.tangent(s)` -- is a
WORLD vector. Used as coefficients on `(u_s, u_y)` or as a nodal `(fx, fy)`,
its `x` component is an `s` component with the sign flipped. `y` is shared by
both frames and is never touched.

WHY THIS IS A MODULE AND NOT A MINUS SIGN AT EACH SITE. Lesson L048: the
contact normal crossed this boundary unconverted and every check passed,
because `dn` is invariant under the error -- flip both `u_s` and `n_s` and
the dot product is unchanged. L049 is the same defect at the tension load,
found by asking the question this module's existence invites: what ELSE
reads a world vector? There were exactly two sites. Both go through here now,
and a third would be found by grepping for `path.tangent` or `path.normal`
outside `scene`.

THE REFERENCE PROGRAM HAS NO SUCH BOUNDARY. Its nodal coordinate IS world
`x` (`slay_sliding_v0_4.py:235`, "decreasing with node id"), so its
`nx = -sin(theta)` and its `fx = -T cos(theta)` are right there and wrong
here. A formula ported across a frame change is not a formula that survived
the port.
"""

from __future__ import annotations


def to_model_frame(v) -> tuple:
    """A world `(x, y)` vector -> components on model `(s, y)`."""
    vx, vy = v
    return (-vx, vy)

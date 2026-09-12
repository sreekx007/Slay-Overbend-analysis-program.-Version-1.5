"""slay.solve -- Newton iteration, contact active set, increment control.

Signature is `solve(problem, state_in=None) -> (Result, state_out)`.
Carried state is explicit (Rule 2), which is what reduces the Mode A /
Mode B difference to whether `state_out` is fed forward.

Workflow: YES -- irreducible; it is the physics.
"""

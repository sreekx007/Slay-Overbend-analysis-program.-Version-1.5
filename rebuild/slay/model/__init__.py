"""slay.model -- Nodes and elements. Discretisation only, no physics.

Turns structural lines into beam elements in arc length, honouring each
segment's own mesh advice. Rollers are deliberately absent: contact is
placed at a virtual point inside an element and distributed to the
bracketing nodes, so a roller never drives node placement (G1). That
exclusion is what makes the mesh shift-invariant and lets this layer sit
OUTSIDE the sweep loop.

Workflow: algorithmic only -- mesh grading, self-terminating.
"""

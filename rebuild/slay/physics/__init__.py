"""slay.physics -- Sections, materials, contact targets, loads and BCs for ONE position.

Emits a Problem: complete, solvable, and inert. A Problem carries no
knowledge that a sweep exists -- that is boundary Rule 1, and it is what
denies sweep logic any channel to reach down into the inner layers.

Workflow: none -- `shift` is an argument, never a range (G11).
"""

"""slay.report -- Strain and moment extraction, code checks, plots, IO.

Consumes Model and Result. A plotter computes no geometry of its own: a
figure that derives a shape rather than drawing a computed one asserts a
result nothing solved for (tracker item 27).

Workflow: none -- thin IO sequencing at most.
"""

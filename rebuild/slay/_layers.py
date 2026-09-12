"""slay/_layers.py -- the layer registry that `tools/check_layers.py` reads.

Decision D1 (11 Sep 2026) chose plain directory names over numbered ones, so
a module's layer is NOT visible in its path. It is declared here instead, and
the linter is what makes the declaration binding:

    a module in layer n may import from layer m only where m <= n

Nothing at runtime reads this file. It exists so the dependency rule is a
TEST rather than a convention. The boundaries in the old code were also
"obvious", and they still eroded -- four separate places ended up inventing
their own answer to the same question because nothing mechanical stopped
them.

To add a layer: insert it in LAYERS at the right depth. Order IS the rule;
the index is derived, never written down twice.
"""

from __future__ import annotations

LAYERS = (
    'data',       # constants, material curves
    'define',     # what a component IS; ILS-local frame
    'scene',      # stinger arc, rollers, placement; world/arc frame
    'model',      # nodes and elements; discretisation only
    'physics',    # sections, contact targets, loads, BCs -> Problem
    'solve',      # Newton + contact active set + increments
    'study',      # Mode A / Mode B sweeps
    'report',     # strains, checks, plots, IO
    'entry',      # case gate, CLI
)

LAYER_INDEX = {name: i for i, name in enumerate(LAYERS)}


# Modules that belong to a layer but do NOT live inside the `slay` package.
#
# The mirrored files stay flat in `rebuild/` deliberately: they are a
# snapshot of Slay-ILS-Designer-V1.0's `plotters/` directory and are kept
# honest by re-diffing against it. Moving them into the package tree would
# break that comparison, which is the only thing keeping the mirror from
# silently drifting (guardrail G7).
#
# `nlfea_v4` is the frozen FE kernel at the repo root. Listing it as `solve`
# is what stops any layer below the solver from reaching into it.
EXTERNAL_LAYER = {
    'config':         'data',
    'component_spec': 'define',
    'ils_builder':    'define',
    'nlfea_v4':       'solve',
}


def layer_of_module(name: str) -> str | None:
    """Layer for a fully-qualified module name, or None if it is not ours.

    Handles both `slay.<layer>.<mod>` and the flat external modules above.
    Anything else -- stdlib, numpy, pytest -- returns None and is ignored by
    the linter rather than guessed at.
    """
    parts = name.split('.')
    if parts[0] == 'slay' and len(parts) > 1 and parts[1] in LAYER_INDEX:
        return parts[1]
    return EXTERNAL_LAYER.get(parts[0])

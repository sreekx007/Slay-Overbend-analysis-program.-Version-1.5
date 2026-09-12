"""slay -- the S-Lay overbend analysis package.

Eight layers, each consuming one immutable artifact and emitting the next:

    CaseSpec -> ILS -> Scene -> Model -> Problem -> Result -> Study -> Report

The dependency rule (a module in layer n imports only from layer m <= n) is
declared in `_layers.py` and enforced by `tools/check_layers.py`.

Workflow -- sequencing stages and carrying state between them -- exists in
exactly three places: `solve` (physics iteration), `study` (the sweep), and
`entry` (thin CLI sequencing). The other five layers are pure transforms.
See docs/SLAY_BUILD_INSTRUCTION.md for the full contract.
"""

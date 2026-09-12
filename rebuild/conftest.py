"""Put the source roots on sys.path for the test run.

`rebuild/` holds the mirrored flat modules (`config`, `component_spec`,
`ils_builder`) alongside the `slay` package, because those four files are a
snapshot of Slay-ILS-Designer-V1.0's `plotters/` directory and stay flat so
they remain diffable against it. They import each other by bare name
(`import config`), so `rebuild/` itself has to be importable.

The repo root goes on too, for `nlfea_v4` -- the frozen FE kernel, which
sits beside the package rather than inside it and is reached only from the
solve layer.
"""

import sys
from pathlib import Path

REBUILD = Path(__file__).resolve().parent
for p in (REBUILD, REBUILD.parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

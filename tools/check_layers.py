#!/usr/bin/env python3
"""check_layers.py -- enforce the layer dependency rule.

    a module in layer n may import from layer m only where m <= n

Decision D1 put layer membership in a registry (`slay/_layers.py`) rather
than in directory names, which means nothing about a wrong import LOOKS
wrong. This script is the compensation: it turns the rule into a test that
fails, rather than a convention a reviewer has to hold in mind.

It reads imports statically with `ast` -- it never imports the modules it
checks, so a module with a missing third-party dependency or an expensive
import still gets linted.

Imports it cannot place -- stdlib, numpy, pytest -- are IGNORED rather than
guessed at. A guess here would either wave through a real violation or
block a legitimate import, and both are worse than declaring the module in
`EXTERNAL_LAYER` when it genuinely belongs to a layer.

Exit code 0 = clean, 1 = violations found (listed), 2 = the tree could not
be read at all.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / 'rebuild' / 'slay'

sys.path.insert(0, str(REPO / 'rebuild'))
from slay._layers import LAYER_INDEX, layer_of_module  # noqa: E402


def module_name_of(path: Path) -> str:
    """Dotted name for a file inside the package, e.g. slay.model.mesh."""
    rel = path.relative_to(REPO / 'rebuild').with_suffix('')
    parts = list(rel.parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def resolve_relative(importer: str, node: ast.ImportFrom) -> str | None:
    """Absolute module name for a relative import, or None if it escapes.

    `from . import x` inside slay.model.mesh resolves against slay.model;
    `from ..scene import y` against slay. Level counting matches Python's
    own: level 1 is the containing package.
    """
    parts = importer.split('.')[:-1] if importer.count('.') else [importer]
    base = parts[:len(parts) - (node.level - 1)] if node.level > 1 else parts
    if not base:
        return None
    return '.'.join(base + ([node.module] if node.module else []))


def imports_of(path: Path, importer: str):
    """(imported_module_name, lineno) for every import in the file."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            name = (resolve_relative(importer, node) if node.level
                    else node.module)
            if name:
                yield name, node.lineno


def main() -> int:
    if not PKG.is_dir():
        print(f'check_layers: package not found at {PKG}', file=sys.stderr)
        return 2

    violations = []
    checked = 0

    for path in sorted(PKG.rglob('*.py')):
        rel_parts = path.relative_to(PKG).parts
        layer = rel_parts[0] if rel_parts[0] in LAYER_INDEX else None
        if layer is None:
            continue                      # slay/__init__.py, slay/_layers.py
        checked += 1
        importer = module_name_of(path)
        here = LAYER_INDEX[layer]

        for name, lineno in imports_of(path, importer):
            target = layer_of_module(name)
            if target is None:
                continue                  # stdlib / third-party
            if LAYER_INDEX[target] > here:
                violations.append(
                    f'{path.relative_to(REPO)}:{lineno}: '
                    f'{layer!r} imports {name!r} from {target!r} '
                    f'-- {target!r} is an OUTER layer')

    if violations:
        print(f'LAYER VIOLATIONS ({len(violations)}):\n')
        for v in violations:
            print('  ' + v)
        print('\nA module may import only from its own layer or an inner one.')
        print('If the import is genuinely needed, the design is wrong, not '
              'the rule -- see docs/SLAY_BUILD_INSTRUCTION.md section 2.2.')
        return 1

    print(f'check_layers: OK -- {checked} modules, no violations')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

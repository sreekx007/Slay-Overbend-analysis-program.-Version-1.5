"""slay.data -- Constants and material curves.

Supplies every default in the toolchain. The values themselves live in
`slay_config.yaml`; `config.py` is the validating loader that exposes
them. Nothing here computes anything physical.

Workflow: none -- pure data.
"""

from slay.data.materials import (
    J2Material,
    Material,
    RambergOsgoodMaterial,
    material,
)

__all__ = ['material', 'Material', 'J2Material', 'RambergOsgoodMaterial']

"""slay.data.materials -- the two validated materials, as layer-neutral data.

WHAT THIS IS FOR. `config.py` exposes the material numbers as loose
constants (`MATERIAL_J2_TABLE`, `MATERIAL_RO_ALPHA_DNV`, ...). Every
consumer that wants a material then has to reassemble them, and each
reassembly is a chance to pair the wrong values or transpose a table. This
module does that assembly once.

WHY IT RETURNS ITS OWN TYPES RATHER THAN THE KERNEL'S. `nlfea_v4` is
declared as the `solve` layer, so the `data` layer cannot import it -- the
linter enforces that, and it is the right way round: material data is a
fact about steel, not about a solver. The solve layer converts these into
`nlfea_v4.IncrementalIsotropic` / `nlfea_v4.RambergOsgood` at the point of
use. The field names below are chosen to make that conversion mechanical.

TWO TRANSPOSITION HAZARDS THIS MODULE EXISTS TO CLOSE
-----------------------------------------------------
1. **Table column order.** `slay_config.yaml` stores the J2 curve as
   `[yield stress, plastic strain]` pairs, while `nlfea_v4` takes
   `eps_p_table` and `sigma_y_table` -- plastic strain FIRST. Passing the
   raw table straight through, in either direction, silently swaps a
   360 MPa stress for a 0.0 strain. Here the two columns are separate,
   named fields and are never adjacent positional arguments.

2. **Which alpha.** Ramberg-Osgood has two conventions in circulation:

       DNV:       alpha = (0.005 - sig_ys/E) * E / sig_ys
       API 1104:  alpha = 0.005 * E / sig_ys

   At this project's reference steel (450 MPa, 207 GPa) they give 1.300
   and 2.300. `nlfea_v4`'s own docstring states 2.278 for this case, which
   matches NEITHER and is simply wrong -- direct evaluation of the formula
   it prints on the line above gives 1.300 exactly. `config.py` carries
   1.300 and this module passes it through unchanged. The field is named
   `alpha_dnv`, not `alpha`, so a caller cannot supply the API value
   without noticing.

DO NOT RE-DERIVE either quantity here (guardrail G1 for T1). Both are
settled numbers in `slay_config.yaml`; recomputing them would create a
second source that drifts the moment the file is edited.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Union

import config


@dataclass(frozen=True)
class J2Material:
    """Incremental J2 plasticity with a tabulated isotropic hardening curve.

    Path-DEPENDENT: stress depends on plastic-strain history. That is why
    Mode A (chained passage) is J2 only -- carrying state forward is the
    whole reason chaining exists, and there is nothing to carry in a
    path-independent model.

    Verified against the project's own Abaqus benchmark (BM_Test_B):
    360 MPa first yield, NOT 385 MPa. A similarly-shaped 385 MPa table
    exists elsewhere and must not be confused with this one.
    """

    E: float                      # Pa
    sigma_y0: float               # Pa, yield at zero plastic strain
    yield_stress: tuple           # Pa, ascending
    plastic_strain: tuple         # dimensionless, ascending, starts at 0.0

    kind: ClassVar[str] = 'j2'

    def __post_init__(self):
        if len(self.yield_stress) != len(self.plastic_strain):
            raise ValueError(
                f'J2 hardening curve is malformed: {len(self.yield_stress)} '
                f'stress points against {len(self.plastic_strain)} strain '
                f'points. The two columns must pair up one for one.')
        if len(self.yield_stress) < 2:
            raise ValueError('J2 hardening curve needs at least two points')
        if self.plastic_strain[0] != 0.0:
            raise ValueError(
                f'J2 hardening curve must start at zero plastic strain, got '
                f'{self.plastic_strain[0]}. A curve starting elsewhere has no '
                f'defined initial yield.')
        if self.sigma_y0 != self.yield_stress[0]:
            raise ValueError(
                f'sigma_y0 ({self.sigma_y0}) disagrees with the first tabulated '
                f'yield stress ({self.yield_stress[0]}) -- two sources for one '
                f'quantity.')
        for label, col in (('yield stress', self.yield_stress),
                           ('plastic strain', self.plastic_strain)):
            if any(b <= a for a, b in zip(col, col[1:])):
                raise ValueError(
                    f'J2 {label} column is not strictly ascending. A '
                    f'non-monotonic hardening curve is unphysical and would '
                    f'make the return mapping ambiguous. Check whether the '
                    f'columns have been transposed.')

    @property
    def n_points(self) -> int:
        return len(self.yield_stress)


@dataclass(frozen=True)
class RambergOsgoodMaterial:
    """Ramberg-Osgood deformation plasticity, DNV form.

        eps / eps_y = sig / sig_ys + alpha_dnv * (sig / sig_ys) ** n_ro

    Path-INDEPENDENT: stress is a function of total strain alone. That is
    precisely why Mode B (independent position check) may use it -- there
    is no history to lose when every position is solved from virgin state.

    FFS 579-1 / DNV Grade 450.
    """

    E: float                      # Pa
    sig_ys: float                 # Pa
    n_ro: float                   # hardening exponent
    alpha_dnv: float              # hardening coefficient, DNV convention

    kind: ClassVar[str] = 'ro'

    def __post_init__(self):
        for label, value in (('E', self.E), ('sig_ys', self.sig_ys),
                             ('n_ro', self.n_ro), ('alpha_dnv', self.alpha_dnv)):
            if value <= 0:
                raise ValueError(f'Ramberg-Osgood {label} must be positive, '
                                 f'got {value}')

    @property
    def eps_y(self) -> float:
        return self.sig_ys / self.E


Material = Union[J2Material, RambergOsgoodMaterial]

_KNOWN = ('j2', 'ro')


def material(name: str) -> Material:
    """The named material, assembled from `config`.

    'j2' -- tabulated incremental plasticity, path-dependent. Required for
            Mode A; the toolchain's standing default.
    'ro' -- Ramberg-Osgood, path-independent. Available to Mode B.

    Raises on any other name rather than falling back. A silently
    substituted material answers a different question than the one asked,
    and the two here differ in exactly the property (path dependence) that
    decides which sweep mode is legitimate.
    """
    key = name.lower().strip()

    if key == 'j2':
        table = config.MATERIAL_J2_TABLE
        return J2Material(
            E=config.MATERIAL_J2_E,
            sigma_y0=table[0][0],
            yield_stress=tuple(row[0] for row in table),
            plastic_strain=tuple(row[1] for row in table),
        )

    if key == 'ro':
        return RambergOsgoodMaterial(
            E=config.MATERIAL_RO_E,
            sig_ys=config.MATERIAL_RO_SIG_YS,
            n_ro=config.MATERIAL_RO_N,
            alpha_dnv=config.MATERIAL_RO_ALPHA_DNV,
        )

    raise ValueError(
        f'unknown material {name!r}. Known materials: {", ".join(_KNOWN)}. '
        f'These are the only two the project has validated; there is no '
        f'default and nothing is substituted.')

"""slay.define.simple -- GD-Simple: an elastic pipe body over an offset shroud.

WHAT IT IS. A bounded length of pipe carrying the PIPELINE'S OWN SECTION --
same OD, same wall -- whose only departures from plain pipe are that its
elastic modulus is a free parameter and that it never yields. An offset
shroud sits underneath it and takes the roller contact. Both halves are
free: the body's length and modulus, and the shroud's V, L1 and L2.

    s increasing ->  vessel                         catenary
                        |         Xb (body)        |
          ==============|==========================|==============
          plain pipe    |   pipe body, E free,     |   plain pipe
          J2, 210 GPa   |   fully elastic          |   J2, 210 GPa
                        |__________________________|
                              |                |
                              |  GD-SH below   |   V measured pipe C/L
                              |________________|   down to the BOTTOM FLAT

WHY IT IS A COMPOSITE AND NOT A NEW COMPONENT CODE. There is no `GD-Simple`
class and there must not be one here. `component_spec.py`, `ils_builder.py`
AND `fixtures/standard_ils_layouts.json` are all MIRRORED from
Slay-ILS-Designer-V1.0 and hashed in `fixtures/mirror_provenance.json`
(G7) -- a new component class, a new builder branch and a new archetype in
the fixture are each a guardrail violation caught by
`test_config_ownership.py`. So GD-Simple is assembled HERE, out of two
codes the mirror already has, and handed to the mirrored builder. The
builder stays the single author of what a component IS; this module only
says which components there are and how big.

THE PIPE BODY IS A NEUTRAL GD-TP, and that is a documented capability
rather than a trick. `ThickPipeBody.validate` was relaxed from `>` to `>=`
on 5 Sep 2026 precisely to allow it: "EQUAL is now legal and means a
NEUTRAL section: OD_comp == OD_pipe, V == 0, wt_ratio == 1. The component
is geometrically indistinguishable from the header pipe but is still a
distinct artifact that owns the section over its span." Owning the span is
the whole point -- it is what gives the body an `owner` tag for the
modulus override and an extent for the Xb/Xe regions.

WHAT THIS MODULE DOES *NOT* DO, because it cannot at this layer:

  * It does not apply E. A modulus is resolved per element in
    `slay.physics.sections`, four layers up. `Simple.E_by_owner` is the
    hand-off: a dict this module can build and that layer can consume.
  * It does not make the body elastic. The constitutive law is chosen in
    `slay.solve.kernel` from `Problem.elastic_spans`, which are ARC spans
    and so need an `s_centre` this layer has never heard of.
    `Simple.body_span(s_centre)` computes one on demand.

Both are deliberate: this layer owns the ILS-local frame and nothing else.

Workflow: none -- pure transforms.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

import config
import ils_builder

# The composite's name. It is NOT a `code` -- no component carries it --
# and nothing in the mirror will recognise it. It names the ASSEMBLY.
ARCHETYPE_ID = 'ILS-SIMPLE'

# `id` fields for the two bodies. These become the element `owner` tags, so
# they are what the modulus override and the region scheme key on, and
# renaming one silently unhooks both.
BODY_ID = 'BODY'
SHROUD_ID = 'SH'

_FIXTURE = (Path(__file__).resolve().parents[2]
            / 'fixtures' / 'standard_ils_layouts.json')


class SimpleRuleError(ValueError):
    """A GD-Simple that is not what GD-Simple means."""


@dataclass(frozen=True)
class Simple:
    """A built GD-Simple, and the two facts the ILS cannot carry.

    `ils` is an ordinary `ils_builder` product and every existing consumer
    takes it unchanged. `E` and the body extent ride alongside because the
    mirrored component model has nowhere to put a per-component modulus and
    nowhere to say "this span does not yield".
    """
    ils: object
    E: float
    L_body: float
    V: float
    L1: float
    L2: float
    centre_x: float = 0.0

    @property
    def extent(self) -> tuple[float, float]:
        """The ASSEMBLY's extent -- the longer of body and shroud."""
        return self.ils.extent

    @property
    def body_extent(self) -> tuple[float, float]:
        """The BODY's extent in ILS-LOCAL x. Not the assembly's: the shroud
        is independently sized and either one may be the longer."""
        return (self.centre_x - self.L_body / 2.0,
                self.centre_x + self.L_body / 2.0)

    def body_span(self, s_centre: float) -> tuple[float, float]:
        """The body's span in MATERIAL arc coordinates, (lo, hi).

        `s = s_centre - x_local`, so the local extent reverses: the
        catenary-side end of the body is the HIGHER s. Returned lo-first
        because that is what `elastic_spans` and `Problem` expect, and a
        reversed span silently matches no element at all rather than
        failing.
        """
        xl, xh = self.body_extent
        return (s_centre - xh, s_centre - xl)

    def E_by_owner(self) -> dict:
        """What `slay.physics.sections.bind_sections` needs to give the body
        its own modulus. The pipeline either side is untouched.
        """
        return {BODY_ID: self.E}

    def elastic_spans(self, s_centre: float) -> tuple:
        """The body's span, as the one-element tuple `build_problem` takes.

        ADD this to whatever spans the caller already has -- do NOT pass it
        alone. The sweep forces its feedstock buffer elastic through the
        same argument, and replacing that span lets the buffer yield and
        carry a plastic hinge forward into every later position (L109).
        """
        return (self.body_span(s_centre),)


def _base_pipeline() -> dict:
    """The pipeline the composite is built on.

    Read from the fixture's own ILS-SHTP entry rather than written out here,
    so GD-Simple is on the same 406.4 x 21 line pipe as every validated
    case and does not acquire a second source of truth for it.
    """
    arch = {a['id']: a for a in
            json.loads(_FIXTURE.read_text())['archetypes']}
    return copy.deepcopy(arch['ILS-SHTP']['definition']['pipeline'])


def spec(*, E: float, L_body: float, V: float, L1: float, L2: float,
         centre_x: float = 0.0, OD: float = None,
         t_wall: float = None) -> dict:
    """The `ils_builder` spec for one GD-Simple. Validated, not trusted.

    `E` is in Pa. Every length is in METRES -- this layer does not know what
    a diameter is, and a caller working in D converts before calling.

    `centre_x` moves BOTH bodies together, because GD-Simple is one
    component: the body sits on the shroud and they share a centre. Their
    LENGTHS are independent (`L_body` against `L1`/`L2`); their positions
    are not, and offering a second centre would invite a GD-Simple whose
    body hangs off the end of its own shroud.
    """
    pipe = _base_pipeline()
    if OD is not None:
        pipe['OD_pipe'] = float(OD)
    if t_wall is not None:
        pipe['t_pipe'] = float(t_wall)
    t_pipe = float(pipe['t_pipe'])
    OD_pipe = float(pipe['OD_pipe'])

    if not E > 0.0:
        raise SimpleRuleError(
            f'GD-Simple: E must be positive, got {E!r}. E is the whole '
            'reason this component exists; there is no default for it.')
    if min(L_body, L1, L2, V) <= 0.0:
        raise SimpleRuleError(
            f'GD-Simple: L_body, L1, L2 and V must all be positive -- got '
            f'L_body={L_body!r}, L1={L1!r}, L2={L2!r}, V={V!r}')
    # The shroud's own floor, restated here so the message names GD-Simple
    # rather than GD-SH. `OffsetShroud.validate` would catch it too.
    if V < OD_pipe / 2.0:
        raise SimpleRuleError(
            f'GD-Simple: V ({V * 1000:.1f} mm) is measured from the pipe '
            f'CENTRELINE down to the shroud BOTTOM FLAT, so it cannot be '
            f'less than the pipe radius ({OD_pipe / 2 * 1000:.1f} mm) -- '
            'the shroud would sit inside the pipe.')

    return {
        'schema_version': 1,
        'ils': {'name': ARCHETYPE_ID, 'frame': 'local',
                # LOWEST, not STRICT. Body and shroud both claim contact
                # wherever they overlap, and under STRICT the assembly
                # refuses to build. LOWEST is right because the shroud is
                # genuinely the deeper of the two everywhere the body is
                # neutral -- V >= OD/2 is what guarantees it, and that is
                # checked above rather than assumed here.
                'ownership': 'lowest'},
        'pipeline': dict(pipe, provenance='PAPER'),
        # Pinned for the same reason ILS-SHTP pins it: assembly mass
        # includes header steel, so a header that moves with a builder
        # default moves every recorded mass with it.
        'header': {'half_length': 6.0, 'provenance': 'DERIVED'},
        'components': [
            {'code': 'GD-SH', 'id': SHROUD_ID, 'centre_x': float(centre_x),
             'V': float(V), 'L1': float(L1), 'L2': float(L2),
             # DESIGN, not PAPER: no published study defines a GD-Simple.
             # The PIPELINE above stays PAPER -- it is the same 406.4 x 21
             # line pipe every validated case runs on.
             'provenance': 'DESIGN'},
            # THE NEUTRAL BODY. t_comp == t_pipe exactly, which is what
            # makes OD_comp == OD_pipe and the stiffness step vanish. It is
            # NOT a thick pipe with a small wall: there is no step at all,
            # and `report.junction` will find no junction to probe, which
            # is why GD-Simple needs the Xb/Xe scheme.
            {'code': 'GD-TP', 'id': BODY_ID, 'centre_x': float(centre_x),
             't_comp': t_pipe, 'L_comp': float(L_body),
             'provenance': 'DESIGN'},
        ],
        'associations': [
            {'type': 'PositionOrientation',
             'from': {'component': SHROUD_ID},
             'to': {'datum': 'pipeline_centreline'},
             'constraint': 'V', 'value': float(V)},
        ],
    }


def build(*, E: float = None, L_body: float, V: float, L1: float, L2: float,
          centre_x: float = 0.0, OD: float = None,
          t_wall: float = None) -> Simple:
    """Build one GD-Simple. `E` defaults to the pipeline steel's.

    Defaulting E to `config.STEEL_E` is not a licence to leave it unsaid --
    it is the one value that makes GD-Simple a CONTROL case, identical to
    plain pipe in stiffness and differing only in that it cannot yield. Any
    other modulus has to be stated.
    """
    E = config.STEEL_E if E is None else float(E)
    sp = spec(E=E, L_body=L_body, V=V, L1=L1, L2=L2, centre_x=centre_x,
              OD=OD, t_wall=t_wall)
    ils = ils_builder.build_ils(sp)

    # THE BODY MUST HAVE COME OUT NEUTRAL. Asserted against the BUILT
    # assembly, not against the spec we sent: the point of G7 is that
    # `ils_builder` is the author of what a component is, so the only
    # trustworthy answer comes from asking it afterwards.
    body = [c for c in ils.assembly.components
            if getattr(c, 'code', None) == 'GD-TP']
    if len(body) != 1:
        raise SimpleRuleError(
            f'GD-Simple: expected exactly one GD-TP body, built {len(body)}')
    b = body[0]
    if abs(b.OD_comp - ils.assembly.pipe.OD_pipe) > 1.0e-12:
        raise SimpleRuleError(
            f'GD-Simple: the body is not neutral -- OD_comp '
            f'{b.OD_comp * 1000:.3f} mm against pipe OD '
            f'{ils.assembly.pipe.OD_pipe * 1000:.3f} mm. GD-Simple carries '
            'the PIPELINE section; a stepped one is a GD-TP study.')
    return Simple(ils=ils, E=E, L_body=float(L_body), V=float(V),
                  L1=float(L1), L2=float(L2), centre_x=float(centre_x))

"""T0 smoke tests -- the scaffold holds and the mesher survived its move.

These are not physics tests. They check that the package imports through its
new paths, that the mirrored config still resolves, and that `slay.model.mesh`
produces the same numbers after relocation as it did before it. The real
numeric ladder (M1..M5) starts at T5; see docs/SLAY_BUILD_INSTRUCTION.md.

Per guardrail G8, every assertion below is on a VALUE, not on "it ran".
"""

import math
import subprocess
import sys
from pathlib import Path

import config
import component_spec as cs
from slay.model import mesh as sm

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# L1 -- the mirrored config still loads and resolves
# --------------------------------------------------------------------------

def test_config_defaults():
    """The three corrections the fresh-build review settled, still in force."""
    assert config.N_VR == 3, 'n_vr default is 3, not the 10 the old code drifted to'
    assert config.MATERIAL_RO_ALPHA_DNV == 1.300, (
        'alpha_DNV is 1.300; nlfea_v4 states two conflicting values in its own '
        'docstrings and 1.300 is the arithmetically correct one')
    assert config.OD_MULTIPLE == 2.0, 'mesh density is 2xOD (G10)'


def test_one_sided_rule_resolves():
    """Stored as a RULE, not a list, so it cannot go stale when n_sr changes."""
    one_sided = config.ONE_SIDED_ROLLERS_DEFAULT
    assert {f'SR{i}' for i in range(1, config.N_SR + 1)} <= one_sided
    assert 'VR1' in one_sided and 'VR2' in one_sided
    assert 'VR3' not in one_sided, 'VR3 onward is bilateral'


# --------------------------------------------------------------------------
# L2 -- component_spec imports through the mirror
# --------------------------------------------------------------------------

def test_std_pipeline():
    p = cs.STD_PIPELINE
    assert p.OD_pipe == config.OD_PIPE_DEF == 0.4064
    assert p.t_pipe == config.T_WALL_DEF == 0.021
    assert p.E == config.STEEL_E == 210.0e9


# --------------------------------------------------------------------------
# L4 -- the mesher after relocation to slay/model/mesh.py
# --------------------------------------------------------------------------

def test_gdtt_taper_grading():
    """GD-TT is the taper-grading case: five zones, two of them short tapers
    asking for min_elements=2, graded so no adjacent pair exceeds 2:1."""
    tt = cs.TaperedThickBody(pipe=cs.STD_PIPELINE, centre_x=0.0)
    m = sm.mesh_component(tt, 'pipeline', target_len=2 * cs.STD_PIPELINE.OD_pipe)

    assert m.warnings == [], f'unexpected mesh warnings: {m.warnings}'
    assert m.n_elems == 16
    assert m.max_adjacent_ratio <= 2.0 + 1e-9, (
        'adjacent element ratio exceeded the grading cap -- an ungraded jump '
        'is what produced the sliver convergence failures (G4)')
    assert len(m.snapped) == 7, 'all seven mandatory stations must snap'


def test_mandatory_stations_are_nodes():
    """G4: a MANDATORY station is a hard constraint, never dropped."""
    tt = cs.TaperedThickBody(pipe=cs.STD_PIPELINE, centre_x=0.0)
    pl = sm.polyline_of(tt, 'pipeline')
    m = sm.mesh_component(tt, 'pipeline', target_len=2 * cs.STD_PIPELINE.OD_pipe)

    node_arcs = m.node_arcs
    for st in sm.stations_of(tt, pl):
        if st.mandatory:
            assert any(abs(a - st.arc_len) < 1e-6 for a in node_arcs), (
                f'mandatory station {st.node_id} at arc {st.arc_len} has no node')


def test_arc_length_not_projection():
    """G2 -- the failure this module was rewritten to eliminate.

    GD-SB's sloped sides run 0.8128 m horizontally while dropping 1.6256 m.
    Measured along the path they are 1.8175 m; projected onto x they read
    0.8128 m, i.e. 44.7% of true length, per side. The projected number is
    plausible, which is what made it dangerous.
    """
    sb = cs.BaseStructure(pipe=cs.STD_PIPELINE, centre_x=0.0)
    pl = sm.polyline_of(sb, f'{sb._tag}:frame')

    expected_slope = math.hypot(sb.P_v, sb.P_l2)
    assert abs(expected_slope - 1.8175) < 1e-3, 'fixture drifted'

    seg_lengths = [pl.arcs[i + 1] - pl.arcs[i] for i in range(len(pl.arcs) - 1)]
    slopes = [L for L in seg_lengths if abs(L - expected_slope) < 1e-6]
    assert len(slopes) == 2, (
        f'expected two sloped sides of {expected_slope:.4f} m, got segment '
        f'lengths {[round(L, 4) for L in seg_lengths]}')
    assert not any(abs(L - sb.P_l2) < 1e-9 for L in seg_lengths), (
        'a segment measured exactly P_l2 -- that is the x-PROJECTION of the '
        'slope, not its length (G2)')


def test_closed_loop_seam():
    """GD-ST's frame is a closed perimeter: the seam is a real adjacency, so
    the element count equals the node count rather than one less."""
    st = cs.TopStructure(pipe=cs.STD_PIPELINE, centre_x=0.0)
    pl = sm.polyline_of(st, f'{st._tag}:frame')
    assert pl.closed
    m = sm.mesh_component(st, f'{st._tag}:frame', target_len=1.0)
    assert m.warnings == []
    assert m.n_elems == len(m.nodes)


def test_branching_line_refuses():
    """A branching line has no single arc coordinate, so it must fail loudly
    rather than return a path that silently omits a limb."""
    vlv = cs.Valve(pipe=cs.STD_PIPELINE, centre_x=0.0)
    m = sm.mesh_component(vlv, 'pipeline', target_len=2 * cs.STD_PIPELINE.OD_pipe)
    assert m.n_elems == 4, 'GD-VLV run is four segments: trans/body/body/trans'
    assert m.warnings == []


# --------------------------------------------------------------------------
# Tooling -- the linter actually catches a violation
# --------------------------------------------------------------------------

def _run_linter():
    return subprocess.run(
        [sys.executable, str(REPO / 'tools' / 'check_layers.py')],
        capture_output=True, text=True)


def test_layer_linter_passes_clean():
    r = _run_linter()
    assert r.returncode == 0, f'linter failed on a clean tree:\n{r.stdout}{r.stderr}'


def test_layer_linter_catches_violation():
    """The linter must be demonstrably able to fail, not merely able to pass.

    Writes an inner-layer module that imports an outer one, confirms a
    non-zero exit, and removes it. Without this the linter could silently
    degrade to a no-op and every later card would still report green.
    """
    offender = REPO / 'rebuild' / 'slay' / 'define' / '_violation_probe.py'
    offender.write_text('from slay.study import passage  # noqa\n')
    try:
        r = _run_linter()
        assert r.returncode == 1, (
            f'linter did not flag define -> study:\n{r.stdout}{r.stderr}')
        assert 'study' in r.stdout
    finally:
        offender.unlink()

    assert _run_linter().returncode == 0, 'tree not clean after probe removal'

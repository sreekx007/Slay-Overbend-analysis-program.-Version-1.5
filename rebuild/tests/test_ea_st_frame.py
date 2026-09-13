"""The GD-ST frame on its own, fixed at its connector slots.

The first EA structure actually solved. Fixing the frame AT slots 2 and 4
replaces the connectors with real restraints, so neither Group B blocker
applies -- no penalty constraints, no zero-length connector element -- and
what is left is the question worth asking first: does the frame itself mesh
and solve correctly?

These tests also guard two post-processing bugs found while building the
study, both the same root cause. `nlfea_v4.assemble` unwraps element rotation
against `theta_states`, and passing NaN disables it. Any element whose chain
runs in -s then has theta0 = pi read against a deformed angle of ~-pi: a 2 pi
phantom rotation. It produced a moment of 8.6e6 kN.m -- identical for every
load, because it was measuring the wrap rather than the deformation -- and
reactions that overstated the applied load by 22%. The pipeline rig never saw
it because its elements all run one way.
"""

import math

import pytest

np = pytest.importorskip('numpy')
fe = pytest.importorskip('nlfea_v4')

import study_ea_st as study            # noqa: E402  (tools/, via conftest)


@pytest.fixture(scope='module')
def frame():
    m, elems, keep, renum = study.frame_model()
    return {
        'm': m, 'elems': elems, 'keep': keep, 'renum': renum,
        's2': study.part_node(m, keep, renum, 'sslot2'),
        's4': study.part_node(m, keep, renum, 'sslot4'),
        's3': study.part_node(m, keep, renum, 'sslot3'),
        'top': study.part_node(m, keep, renum, 'stop1'),
    }


def _run(f, node, P):
    return study.solve(f['keep'], f['elems'], f['renum'], (f['s2'], f['s4']),
                       node, P)


def test_frame_is_a_closed_ring(frame):
    """Eighteen elements, every node of degree two. A frame that had lost its
    closing segment would still solve and would be a different structure."""
    deg = {}
    for e in frame['elems']:
        for g in (e.n1, e.n2):
            deg[g] = deg.get(g, 0) + 1
    assert len(frame['elems']) == 18
    assert set(deg.values()) == {2}, 'the frame is not a closed ring'


def test_no_spurious_long_members(frame):
    """The longest real member is a 1.0837 m bottom-chord bay. Anything longer
    means the chain walk joined two nodes that are not neighbours."""
    keep, renum = frame['keep'], frame['renum']
    for e in frame['elems']:
        a, b = renum[e.n1], renum[e.n2]
        L = math.dist((keep[a].s, keep[a].y), (keep[b].s, keep[b].y))
        assert L < 1.2, f'member of {L:.4f} m between non-neighbours'


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_control_matches_the_closed_form(frame, P):
    """Fixing slots 2 and 4 decouples the rest of the frame, so a load at the
    bottom-chord centre is a plain fixed-fixed beam. This validates the rig,
    not the frame -- which is why the top-chord case exists too."""
    U, ms, _ = _run(frame, frame['s3'], P)
    d = U[3 * ms.user_node_to_mesh[frame['s3']] + 1]
    L = abs(frame['keep'][frame['s2']].s - frame['keep'][frame['s4']].s)
    assert d == pytest.approx(P * L**3 / (192 * study.EI_EFF), rel=2e-3)


@pytest.mark.parametrize('node_key', ('s3', 'top'))
@pytest.mark.parametrize('P', (20e3, 200e3))
def test_reactions_balance_the_applied_load(frame, node_key, P):
    """The check that caught the unwrap bug. It read 24.362 kN against 20 kN
    applied, and asymmetrically across two supports of a symmetric structure
    under a symmetric load -- which is impossible, and so was the reading."""
    U, ms, _ = _run(frame, frame[node_key], P)
    R = study.reactions(U, ms)
    total = sum(R[3 * ms.user_node_to_mesh[i] + 1]
                for i in (frame['s2'], frame['s4']))
    assert total == pytest.approx(-P, rel=1e-4)


@pytest.mark.parametrize('P', (20e3, 200e3))
def test_legs_carry_half_the_load_each(frame, P):
    """Load the top chord and it must reach the supports down the two legs.
    Peak axial comes out at exactly P/2 -- the cleanest evidence the frame is
    carrying load as a frame rather than as disconnected pieces."""
    U, ms, _ = _run(frame, frame['top'], P)
    N, _ = study.member_forces(U, ms)
    assert np.abs(N).max() == pytest.approx(P / 2, rel=1e-3)


def test_moments_scale_with_load(frame):
    """The unwrap bug gave a moment that did not move with load at all. Two
    load levels an order of magnitude apart is what exposes that."""
    _, m20 = study.member_forces(*_run(frame, frame['top'], 20e3)[:2])
    _, m200 = study.member_forces(*_run(frame, frame['top'], 200e3)[:2])
    assert m200.max() / m20.max() == pytest.approx(10.0, rel=5e-3)


def test_top_chord_load_is_far_softer_than_the_control(frame):
    """The two cases are meant to be different structures, not two views of
    one. A long load path through the frame against a short fixed-fixed span."""
    d_ctrl = _run(frame, frame['s3'], 20e3)
    d_ctrl = d_ctrl[0][3 * d_ctrl[1].user_node_to_mesh[frame['s3']] + 1]
    d_top = _run(frame, frame['top'], 20e3)
    d_top = d_top[0][3 * d_top[1].user_node_to_mesh[frame['top']] + 1]
    assert d_top / d_ctrl > 20

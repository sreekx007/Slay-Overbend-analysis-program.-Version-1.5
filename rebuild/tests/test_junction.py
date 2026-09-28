"""L8 -- junction extraction, and the moment recovery it rests on.

WHAT THIS PINS. Junctions are the SECTION steps the FE actually sees; moment
is continuous across one and strain is not; probes land where they say they
land or declare themselves clamped; and nothing is ever interpolated across
the step.
"""

import math

import pytest

pytest.importorskip('numpy')
import numpy as np                                           # noqa: E402

from slay.report import junction as jn                       # noqa: E402

OD = 0.4064


# -- a Problem stub, so the rules are testable without a solve ------------

class FakeSection:
    def __init__(self, index, OD, owner, t=0.021, E=207e9):
        self.index, self.OD, self.owner, self.t, self.E = index, OD, owner, t, E

    @property
    def I(self):
        return math.pi / 64.0 * (self.OD**4 - (self.OD - 2 * self.t)**4)


class FakeProblem:
    def __init__(self, bounds, ods, owners):
        self.nodes = tuple((i, s, 0.0) for i, s in enumerate(bounds))
        self.elements = tuple((i, i, i + 1, owners[i], 'L')
                              for i in range(len(bounds) - 1))
        self.sections = tuple(FakeSection(i, ods[i], owners[i])
                              for i in range(len(bounds) - 1))


class FakeResult:
    def __init__(self, eps, M):
        self.strains = tuple((i, 0.0, e) for i, e in enumerate(eps))
        self.moments = tuple((i, 0.0, m) for i, m in enumerate(M))
        self.status, self.converged = 'ok', True


class FakePosition:
    def __init__(self, result, shift=0.0):
        self.result, self.shift, self.index = result, shift, 0


def _case(n_pipe=6, n_comp=2, elem=OD * 2):
    """pipe | component | pipe, on a uniform grid."""
    n = n_pipe + n_comp + n_pipe
    bounds = [i * elem for i in range(n + 1)]
    ods = ([OD] * n_pipe + [0.4484] * n_comp + [OD] * n_pipe)
    owners = (['pipe'] * n_pipe + ['GD-TP'] * n_comp + ['pipe'] * n_pipe)
    return FakeProblem(bounds, ods, owners)


# -- finding the junctions -------------------------------------------------

def test_junctions_are_the_section_steps(  ):
    """Read off the MODEL, not off the component: exactly what the FE sees."""
    pr = _case()
    js = jn.junctions(pr)
    assert len(js) == 2
    a, b = js
    assert a.s == pytest.approx(6 * 2 * OD) and a.OD_in == pytest.approx(OD)
    assert a.OD_out == pytest.approx(0.4484) and a.owner_out == 'GD-TP'
    assert b.OD_in == pytest.approx(0.4484) and b.owner_out == 'pipe'
    assert [j.index for j in js] == [0, 1] and a.s < b.s


def test_a_component_that_does_not_step_has_no_junction():
    """A neutral body shares the pipe's section, so nothing steps and there
    is no discontinuity to measure. Correct, not a miss."""
    n = 6
    pr = FakeProblem([i * 2 * OD for i in range(2 * n + 1)],
                     [OD] * (2 * n), ['pipe'] * n + ['GD-TP'] * n)
    assert jn.junctions(pr) == ()


# -- the physics the extraction exists to capture -------------------------

def test_moment_is_continuous_and_strain_is_not(  ):
    """THE RESULT, stated as a test. The same moment on two section moduli
    gives two strains, so a junction reports BOTH sides and they differ."""
    pr = _case()
    n = len(pr.elements)
    M = [1.0e6] * n                                   # continuous by construction
    eps = [0.003] * 6 + [0.001] * 2 + [0.003] * 6     # steps at the junctions
    pos = FakePosition(FakeResult(eps, M))
    at_j = [p for p in jn.probes(pos, pr, jn.junctions(pr)[0], OD)
            if p.offset_OD == 0.0]
    assert len(at_j) == 2
    sides = {p.side: p for p in at_j}
    assert set(sides) == {'pipe', 'component'}
    assert sides['pipe'].moment == pytest.approx(sides['component'].moment)
    assert sides['pipe'].strain != pytest.approx(sides['component'].strain)
    assert sides['pipe'].strain == pytest.approx(0.003)
    assert sides['component'].strain == pytest.approx(0.001)


def test_nothing_is_interpolated_across_the_step():
    """A probe inside the pipe must never carry a component value, however
    close the junction is."""
    pr = _case()
    n = len(pr.elements)
    eps = [0.003] * 6 + [0.001] * 2 + [0.003] * 6
    pos = FakePosition(FakeResult(eps, [1.0e6] * n))
    for p in jn.measure(pos, pr, OD):
        if p.side == 'pipe':
            assert p.strain == pytest.approx(0.003), p
        elif p.side == 'component':
            assert p.strain == pytest.approx(0.001), p


# -- probes land where they say ------------------------------------------

def test_a_probe_lands_at_the_offset_it_is_labelled_with():
    """THE BUG THIS PINS. At the ruled 2xOD mesh no element CENTRE sits at
    2, 4 or 6 x OD from a junction -- midpoints land at ODD multiples of
    1xOD. Taking 'the element containing the point' put the -2xOD sample on
    the element centred 1xOD away, so a row labelled 2xOD carried the 1xOD
    number and duplicated the junction row exactly."""
    pr = _case(n_pipe=10, n_comp=2)
    n = len(pr.elements)
    pos = FakePosition(FakeResult([0.001 * (i + 1) for i in range(n)],
                                  [1.0e6] * n))
    j = jn.junctions(pr)[0]
    for p in jn.probes(pos, pr, j, OD):
        if p.offset_OD in (-2.0, -4.0, -6.0):
            assert not p.clamped, p
            assert p.s_elem == pytest.approx(p.s), \
                f'{p.offset_OD}xOD probe answered from {p.s_elem}, not {p.s}'
            assert p.s == pytest.approx(j.s + p.offset_OD * OD)


def test_offsets_on_one_side_are_distinct_values():
    """The duplication symptom, checked directly."""
    pr = _case(n_pipe=10, n_comp=2)
    n = len(pr.elements)
    pos = FakePosition(FakeResult([0.001 * (i + 1) for i in range(n)],
                                  [1.0e6 * (i + 1) for i in range(n)]))
    got = [p for p in jn.probes(pos, pr, jn.junctions(pr)[0], OD)
           if p.offset_OD < 0]
    vals = [round(p.strain, 12) for p in got]
    assert len(set(vals)) == len(vals), f'duplicated samples: {got}'


def test_a_probe_past_the_end_of_a_short_body_clamps_and_says_so():
    """A short component cannot be sampled 2xOD inside itself. Clamping is
    the honest answer; doing it silently is not.

    Built the way the mesher really builds one: the component's own elements
    are SHORTER than the pipe's, because its boundaries are snapped to nodes.
    So its last midpoint falls short of the 2xOD offset while the offset is
    still inside the body -- exactly the case seen on the built ILS-TP, where
    the +2xOD probe wanted s = 7.813 and the run ended at 7.750.
    """
    elem = 2 * OD
    bounds = [i * elem for i in range(7)]          # pipe, 6 elements
    j = bounds[-1]
    bounds += [j + 0.5, j + 1.0]                    # component, 2 x 0.5 m
    bounds += [j + 1.0 + i * elem for i in range(1, 7)]
    ods = [OD] * 6 + [0.4484] * 2 + [OD] * 6
    owners = ['pipe'] * 6 + ['GD-TP'] * 2 + ['pipe'] * 6
    pr = FakeProblem(bounds, ods, owners)
    n = len(pr.elements)
    pos = FakePosition(FakeResult([0.002] * n, [1.0e6] * n))
    got = [p for p in jn.probes(pos, pr, jn.junctions(pr)[0], OD)
           if p.offset_OD == 2.0]
    assert len(got) == 1 and got[0].side == 'component'
    assert got[0].clamped, 'the run ends at 0.75 m and the probe wants 0.813'
    assert got[0].s_elem < got[0].s


def test_the_junction_itself_is_always_clamped():
    """It IS the end of both runs -- there is no element centred on it."""
    pr = _case()
    n = len(pr.elements)
    pos = FakePosition(FakeResult([0.002] * n, [1.0e6] * n))
    for p in jn.measure(pos, pr, OD):
        if p.offset_OD == 0.0:
            assert p.clamped


def test_a_probe_off_the_model_is_a_miss_not_a_clamp_to_the_tip():
    """Clamping it would return the tip's number under a label saying it
    came from 6 diameters off a junction."""
    pr = _case(n_pipe=2, n_comp=2)
    n = len(pr.elements)
    pos = FakePosition(FakeResult([0.002] * n, [1.0e6] * n))
    out = [p for p in jn.probes(pos, pr, jn.junctions(pr)[0], OD)
           if not p.in_model]
    assert out, 'a 6xOD offset must run off this short model'
    for p in out:
        assert math.isnan(p.strain) and math.isnan(p.moment)


def test_station_coordinates_carry_the_shift():
    """A passage row must say where on the STINGER it was measured."""
    pr = _case()
    n = len(pr.elements)
    pos = FakePosition(FakeResult([0.002] * n, [1.0e6] * n), shift=3.0)
    for p in jn.measure(pos, pr, OD):
        assert p.s_station == pytest.approx(p.s + 3.0)


# -- the derived parameters ------------------------------------------------

def test_the_stiffness_ratio_comes_off_the_solved_sections():
    pr = _case()
    secs = {s.owner: s for s in pr.sections}
    assert jn.stiffness_ratio(pr) == pytest.approx(
        secs['GD-TP'].I / secs['pipe'].I)
    # This stub grows the OD at a FIXED wall, so the ratio is modest. The
    # real GD-TP keeps a constant bore and grows outward -- wall 42 mm against
    # the pipe's 21 -- which measures 2.3631 on the built archetype.
    assert jn.stiffness_ratio(pr) == pytest.approx(1.3631, abs=1e-4)


def test_plain_pipe_has_a_stiffness_ratio_of_one():
    """A plain-pipe row in the same dataset still needs the column."""
    n = 8
    pr = FakeProblem([i * 2 * OD for i in range(n + 1)],
                     [OD] * n, ['pipe'] * n)
    assert jn.stiffness_ratio(pr) == 1.0
    assert jn.body_peak(FakePosition(FakeResult([0.002] * n, [1e6] * n)),
                        pr) == (0.0, 0.0, 0.0)


def test_the_body_peak_is_on_the_component_only():
    pr = _case()
    n = len(pr.elements)
    eps = [0.009] * 6 + [0.001, 0.002] + [0.009] * 6   # pipe is worse
    pos = FakePosition(FakeResult(eps, [1.0e6] * n))
    e, _M, _s = jn.body_peak(pos, pr)
    assert e == pytest.approx(0.002), 'the component body, not the model peak'


# -- the moment recovery ---------------------------------------------------

def test_elastic_moment_is_EI_kappa_on_a_solved_arc():
    """The recovery checked against a closed form. On the stinger arc an
    elastic pipe carries about EI/R; on discrete rollers it oscillates about
    that, so the MEAN is what must land, not each element."""
    from slay.data import materials
    from slay.study import sweep
    R = 85.0
    sc = sweep.scene_for(R=R, spacing=9.0, L_comp=0.0,
                         clear_before=0.0, clear_after=0.0)
    pos = sweep.run(sc, None, L_comp=0.0, clear_before=0.0, clear_after=0.0,
                    step=1.0, tension=120 * 9806.65, material=None)
    r = pos[0].result
    assert r.moments and len(r.moments) == len(r.strains)
    import config
    t = config.T_WALL_DEF
    I = math.pi / 64.0 * (config.OD_PIPE_DEF**4
                          - (config.OD_PIPE_DEF - 2 * t)**4)
    EI_R = materials.material('j2').E * I / R
    on_arc = [m for (_i, s, m) in r.moments if 18.0 < s < 36.0]
    assert on_arc
    assert abs(float(np.mean(on_arc)) / EI_R - 1.0) < 0.10, \
        f'mean {np.mean(on_arc):.3e} against EI/R {EI_R:.3e}'


def test_moment_and_strain_agree_through_the_curvature():
    """Two independent recoveries -- the kernel's fibre strain and this
    module's fibre moment -- must satisfy eps_max = eps_membrane + kappa*r
    with a membrane term that is CONSTANT along a uniform run."""
    import config
    from slay.data import materials
    from slay.study import sweep
    sc = sweep.scene_for(R=85.0, spacing=9.0, L_comp=0.0,
                         clear_before=0.0, clear_after=0.0)
    pos = sweep.run(sc, None, L_comp=0.0, clear_before=0.0, clear_after=0.0,
                    step=1.0, tension=120 * 9806.65, material=None)
    r = pos[0].result
    OD_p, t = config.OD_PIPE_DEF, config.T_WALL_DEF
    I = math.pi / 64.0 * (OD_p**4 - (OD_p - 2 * t)**4)
    EI = materials.material('j2').E * I
    eps_of = {i: e for (i, _s, e) in r.strains}
    resid = [eps_of[i] - (M / EI) * OD_p / 2.0
             for (i, s, M) in r.moments if 24.0 < s < 30.0]
    assert resid
    assert max(resid) - min(resid) < 0.05 * max(resid), \
        f'membrane term is not constant: {resid}'


# -- the case row ----------------------------------------------------------

def test_the_case_row_carries_both_the_snapshot_and_the_envelope():
    """A location that does not govern peaks at a DIFFERENT position, so the
    snapshot understates it. Measured on GD-TP: the trailing junction reads
    0.3297% at the envelope position and 0.4620% at its own worst."""
    rows = [{'j0_at_pipe_strain': 0.002, 'j0_at_pipe_moment': 1.0,
             'j0_at_pipe_s': 7.0, 'j0_at_pipe_clamped': True},
            {'j0_at_pipe_strain': 0.005, 'j0_at_pipe_moment': 3.0,
             'j0_at_pipe_s': 7.0, 'j0_at_pipe_clamped': True},
            {'j0_at_pipe_strain': 0.004, 'j0_at_pipe_moment': 2.0,
             'j0_at_pipe_s': 7.0, 'j0_at_pipe_clamped': True}]
    got = jn.case_row(rows, env_index=0)
    assert got['j0_at_pipe_strain'] == pytest.approx(0.002), 'the snapshot'
    assert got['j0_at_pipe_strain_env'] == pytest.approx(0.005), 'the worst'
    assert got['j0_at_pipe_moment_env'] == pytest.approx(3.0)
    assert 'j0_at_pipe_s_env' not in got, 'a location is not maxed'
    assert 'j0_at_pipe_clamped_env' not in got, 'nor is a flag'


def test_the_case_row_skips_positions_that_failed():
    """A diverged position contributes no dict; it must not blank the row."""
    rows = [{'a_strain': 0.002}, {}, {'a_strain': 0.009}]
    got = jn.case_row(rows, env_index=0)
    assert got['a_strain'] == pytest.approx(0.002)
    assert got['a_strain_env'] == pytest.approx(0.009)


def test_a_case_with_no_junctions_gives_an_empty_row():
    """Plain pipe. The derived columns live on the passage record instead."""
    assert jn.case_row([{}, {}], env_index=0) == {}

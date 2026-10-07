"""The plotter reads a profile and nothing else.

TWO CLAIMS, both worth a test because both have been violated in this repo
by a tool that was correct and the wrong shape:

  1. `tools/plot_from_schema.py` imports nothing from `slay`. If it could,
     "drawn from the file" would be an aspiration rather than a fact, and
     the first missing column would be silently patched by a solver call
     instead of exposing the gap.

  2. Given three tables that satisfy the contract, it draws the five-panel
     figure -- with no Scene, no model, and no passage solved anywhere in
     this test. The rows below are SYNTHETIC on purpose: if the figure can
     be drawn from numbers this test made up, the contract is sufficient.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

from slay.report import profile as rprof
from slay.report import profile_schema as ps

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'tools' / 'plot_from_schema.py'


def _load_tool():
    spec = importlib.util.spec_from_file_location('pfs_under_test', TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['pfs_under_test'] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_plotter_imports_nothing_from_slay():
    """Claim 1, checked against the SOURCE rather than trusting the header."""
    src = TOOL.read_text()
    offenders = [ln.strip() for ln in src.splitlines()
                 if ln.strip().startswith(('import slay', 'from slay'))
                 or ' import slay' in ln and not ln.strip().startswith('#')]
    assert offenders == [], f'plot_from_schema reaches into slay: {offenders}'


# ---------------------------------------------------------------------------
# a synthetic profile that satisfies the contract
# ---------------------------------------------------------------------------

R = 85.0
OD = 0.4064
T_WALL = 0.0210
R_ROLLER = 0.30
# Where the pipe centreline sits when it is resting on the rollers: the
# roller-centre locus plus the roller radius plus the pipe radius. 0.5032 m,
# which is larger than most of the lift-off this fixture models -- the whole
# reason `off_arc` is reported relative to it rather than to the axles.
CONTACT_OFFSET = R_ROLLER + OD / 2.0
N = 160
S_MAX = 40.0
S_LO, S_HI = 16.0, 22.0        # the component's material span
ZONE = 34.0


def _region(s):
    """The five-region scheme over the synthetic shroud, catenary side high."""
    third = (S_HI - S_LO) / 3.0
    if s >= S_HI: return 'X1'
    if s >= S_HI - third: return 'X2'
    if s >= S_HI - 2 * third: return 'X3'
    if s >= S_LO: return 'X4'
    return 'X5'


def _ctx():
    return dict(profile_schema_version=ps.PROFILE_SCHEMA_VERSION,
                case_id='synthetic', table='', family='ILS-XX',
                R=R, spacing=9.0, OD=OD, t_wall=T_WALL, tension_mt=120.0,
                L_comp=S_HI - S_LO, s_centre=19.0, zone_s_max=ZONE,
                n_positions=2, stiffness_ratio=2.0, n_junctions=2,
                envelope_step=1, region_scheme='X1-X5/offset',
                # A synthetic profile stands for a GOOD one, so it declares
                # a complete passage. The truncated case has tests of its
                # own in test_passage_completion.py (L101).
                passage_complete=True, sweep_total=S_HI - S_LO + 2.0,
                sweep_ran=S_HI - S_LO + 2.0)


def _arc(s):
    """A circular arc of radius R, tangent to the deck at s = 0."""
    th = s / R
    return (-R * math.sin(th), R * (1.0 - math.cos(th)))


def _geometry(step, shift, shroud=False):
    ctx = _ctx()
    rows = []
    for k in range(N):
        s = S_MAX * k / (N - 1)
        s_sta = s + shift
        ax, ay = _arc(s_sta)
        th = s_sta / R
        nx, ny = math.sin(th), -math.cos(th)
        lift = 0.02 * math.exp(-((s - 19.0) / 3.0) ** 2)
        # The pipe rides on the roller TOPS, `CONTACT_OFFSET` above the
        # roller-centre locus, with `lift` the extra it is held off by.
        px = ax + (CONTACT_OFFSET + lift) * nx
        py = ay + (CONTACT_OFFSET + lift) * ny
        inside = S_LO <= s <= S_HI
        r = {k_: v for k_, v in ctx.items() if k_ in ps.header('geometry')}
        r.update(table='geometry', step=step, shift=shift, converged=True,
                 sample=k, s_material=s, s_station=s_sta, x=px, y=py,
                 arc_x=ax, arc_y=ay, normal_x=nx, normal_y=ny,
                 contact_offset=CONTACT_OFFSET,
                 off_arc=((px - ax) * nx + (py - ay) * ny) - CONTACT_OFFSET,
                 OD_section=(0.49 if (inside and not shroud) else OD),
                 t_section=T_WALL,
                 y_contact=(OD / 2.0 + 0.2 if (inside and shroud)
                            else OD / 2.0),
                 section_owner=('comp' if (inside and not shroud)
                                else 'pipe'),
                 contact_owner=('comp' if (inside and shroud) else 'pipe'),
                 region=(_region(s) if shroud else ''))
        rows.append(r)
    return rows


def _sections(step, shift, shroud=False):
    ctx = _ctx()
    rows = []
    n_el = 40
    for k in range(n_el):
        a = S_MAX * k / n_el
        b = S_MAX * (k + 1) / n_el
        inside = S_LO <= 0.5 * (a + b) <= S_HI
        eps = 0.004 + 0.002 * math.exp(-((0.5 * (a + b) - 19.0) / 4.0) ** 2)
        if inside and not shroud:
            eps *= 0.25
        r = {k_: v for k_, v in ctx.items() if k_ in ps.header('sections')}
        r.update(table='sections', step=step, shift=shift, converged=True,
                 element=k, s_material_0=a, s_material_1=b,
                 s_station_0=a + shift, s_station_1=b + shift,
                 x_0=-(a + shift), x_1=-(b + shift),
                 strain=eps, moment=1.2e6 * eps,
                 OD_section=(0.49 if (inside and not shroud) else OD),
                 section_owner=('comp' if (inside and not shroud)
                                else 'pipe'),
                 region=(_region(0.5 * (a + b)) if shroud else ''),
                 owner='pipeline', in_band=bool(b + shift < ZONE))
        rows.append(r)
    return rows


def _stations():
    ctx = _ctx()
    rows = []
    for k in range(5):
        s = 9.0 * k
        x, y = _arc(s)
        r = {k_: v for k_, v in ctx.items() if k_ in ps.header('stations')}
        r.update(table='stations', station=f'SR{k}', role='CONTACT',
                 s_station=s, x=x, y=y, radius=0.2, one_sided=(k > 1))
        rows.append(r)
    return rows


def _emit(tmp_path, shroud=False):
    stem = tmp_path / 'synthetic'
    geo = _geometry(0, 0.0, shroud) + _geometry(1, 2.0, shroud)
    sec = _sections(0, 0.0, shroud) + _sections(1, 2.0, shroud)
    rprof.write_table('geometry', geo, Path(f'{stem}.geometry.csv'))
    rprof.write_table('sections', sec, Path(f'{stem}.sections.csv'))
    rprof.write_table('stations', _stations(), Path(f'{stem}.stations.csv'))
    return stem


def test_synthetic_profile_satisfies_the_contract(tmp_path):
    """The rows this test invents are accepted by the WRITER's own checks.

    If they were not, the plotting test below would be exercising a file
    shape the real emitter can never produce.
    """
    stem = _emit(tmp_path)
    for t in ('geometry', 'sections', 'stations'):
        p = Path(f'{stem}.{t}.csv')
        back = list(csv.DictReader(p.open()))
        assert ps.unknown(t, back[0].keys()) == []
        side = json.loads(Path(f'{p}.schema.json').read_text())
        assert side['table'] == t


@pytest.mark.parametrize('shroud', [False, True])
def test_the_five_panel_figure_draws_from_the_files_alone(tmp_path, shroud):
    """Claim 2. A stiffener and a shroud take DIFFERENT drawing paths."""
    mod = _load_tool()
    stem = _emit(tmp_path, shroud=shroud)
    prof = mod.load_profile(stem)
    out = tmp_path / 'fig.png'
    got = mod.plot_profile(prof, str(out))

    assert out.exists() and out.stat().st_size > 20_000
    assert got['step'] == 1, 'should default to the declared envelope step'
    assert got['shift'] == pytest.approx(2.0)
    # A stiffener steps the section twice; a shroud steps it never. That is
    # the whole difference between the two bodies, and the figure has to get
    # it from the file rather than from the family name.
    assert got['junctions'] == (0 if shroud else 2)
    assert 0.003 < got['peak'] < 0.01


@pytest.mark.parametrize('shroud', [False, True])
def test_every_panel_runs_the_same_way_along_x(tmp_path, shroud):
    """L077. A mirrored panel is indistinguishable from a correct one.

    Panels 2 and 5 set their own limits (they are windows on a component,
    not the whole model), and the first version set them descending while
    panels 1, 3 and 4 ascended. Nothing about the result looked wrong: a
    mirrored close-up of a curve is still a curve. It is the same class of
    error as getting the world sign backwards (L070), which is why it gets
    a test rather than an eye.
    """
    mod = _load_tool()
    got = mod.plot_profile(mod.load_profile(_emit(tmp_path, shroud=shroud)),
                           str(tmp_path / 'fig.png'))
    for name, panel in got['panels'].items():
        lo, hi = panel.get_xlim()
        assert lo < hi, f'panel {name!r} runs right-to-left: xlim {lo}..{hi}'


def test_the_rollers_are_drawn_above_the_pipe_fills(tmp_path):
    """L077, the other half: drawn and then painted over reads as absent."""
    mod = _load_tool()
    got = mod.plot_profile(mod.load_profile(_emit(tmp_path)),
                           str(tmp_path / 'fig.png'))
    ex = got['panels']['closeup']
    circles = [p for p in ex.patches if type(p).__name__ == 'Circle']
    assert circles, 'no roller drawn in the close-up window'
    fills = [c.get_zorder() for c in ex.collections + list(ex.patches)
             if type(c).__name__ == 'Polygon']
    assert min(c.get_zorder() for c in circles) > max(fills or [0]), \
        'a roller sits under a fill and will be invisible'


def test_a_named_step_is_honoured(tmp_path):
    mod = _load_tool()
    prof = mod.load_profile(_emit(tmp_path))
    got = mod.plot_profile(prof, str(tmp_path / 'f0.png'), step=0)
    assert got['step'] == 0 and got['shift'] == pytest.approx(0.0)


def test_a_missing_table_is_refused_not_guessed(tmp_path):
    mod = _load_tool()
    stem = _emit(tmp_path)
    Path(f'{stem}.stations.csv').unlink()
    with pytest.raises(SystemExit, match='stations'):
        mod.load_profile(stem)


def test_a_missing_sidecar_is_refused(tmp_path):
    mod = _load_tool()
    stem = _emit(tmp_path)
    Path(f'{stem}.geometry.csv.schema.json').unlink()
    with pytest.raises(SystemExit, match='no schema'):
        mod.load_profile(stem)


def test_mismatched_schema_versions_are_refused(tmp_path):
    """Three tables written at different times must not be plotted together."""
    mod = _load_tool()
    stem = _emit(tmp_path)
    p = Path(f'{stem}.sections.csv.schema.json')
    d = json.loads(p.read_text())
    d['profile_schema_version'] = '0.9.0'
    p.write_text(json.dumps(d))
    with pytest.raises(SystemExit, match='disagree'):
        mod.load_profile(stem)

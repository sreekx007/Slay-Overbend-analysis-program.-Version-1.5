"""slay.report.profile -- build and write a PROFILE artifact. L8.

WHAT THIS REPLACES. Until now the only way to draw the pipe on the stinger
was a tool that imported the solver, built a Scene, meshed, and swept the
whole passage -- every time, for every figure. That tool is correct and it is
the wrong shape for the job: a figure is a READER of a result, and a reader
that has to re-run the analysis cannot check it, cannot be pointed at last
week's run, and has no way to be wrong loudly. This module writes the result
DOWN, to a declared contract, so the figure becomes a reader.

THE INVARIANTS ARE ENFORCED HERE, not documented and hoped for. `write`
refuses a file whose `per='case'` columns are not constant, whose
`per='position'` columns move within a step, or which carries a column the
contract does not declare. That is the same argument as `schema.unknown`:
an artifact is only worth trusting if writing a wrong one FAILS.

THE SHIFT IS APPLIED HERE (L070). The solver omits the rigid-body
translation of a pipe advancing down the stinger -- sliding along its own
axis strains nothing, so nothing drives it -- and is right to. But world
coordinates are exactly where that translation matters, and a profile is
written in world coordinates, so every `x` in this file already carries it:

    x = -(s_material + shift + u_s)        y = y_node + u_y

Leaving it out drew the component a whole metre short of the roller it had
already reached, on a figure whose numbers were all correct.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from slay.report import junction as jr
from slay.report import profile_schema as ps
from slay.report import regions as rg
from slay.scene.rollers import StationRole
from slay.solve.kernel import dof

# The drawing grid. NOT the structural mesh, and the difference is a lesson
# rather than a preference (L074): at the ruled 2xOD density (G10) a 6 m
# shroud spans seven nodes, its taper ends fall between them, and an outline
# sampled on the mesh showed a 95 mm step where the geometry goes smoothly to
# zero. The centreline is interpolated finely and the assembly asked at every
# sample, so the artifact carries the component's shape rather than the
# mesh's opinion of it.
N_SAMPLES = 1200


def _ctx(table: str, context: dict) -> dict:
    """The part of the case context a given table declares.

    One context is built per case and narrowed here rather than three being
    built separately, so the three tables cannot end up disagreeing about
    which case they describe -- the failure that would make a profile
    silently self-inconsistent.
    """
    want = set(ps.header(table))
    return {k: v for k, v in context.items() if k in want}


def _world(s_station, y, us, uy):
    """(x, y) in the world frame. The minus sign is the frame gate."""
    return (-(s_station + us), y + uy)


def _pipe_nodes(model, ms, U, shift):
    """(s_material, x, y) per pipeline node, ordered along the pipe."""
    at = {n.index: n for n in model.nodes}
    ids = sorted({i for e in model.elements if e.owner == 'pipeline'
                  for i in (e.n1, e.n2)}, key=lambda i: at[i].s)
    out = []
    for i in ids:
        n = at[i]
        x, y = _world(n.s + shift, n.y, U[dof(ms, i, 0)], U[dof(ms, i, 1)])
        out.append((n.s, x, y))
    return out


# ---------------------------------------------------------------------------
# table 1 -- geometry
# ---------------------------------------------------------------------------

def geometry_rows(scene, model, ms, U, ils, s_centre, OD, shift, step,
                  converged, context, n=N_SAMPLES, geom=None) -> list:
    """One row per sample, for ONE position.

    The assembly is queried at every sample rather than at every node, which
    is what lets a tapered body be drawn as the shape it is. `section_at`
    answers what carries the BENDING and `contact_at` what a roller TOUCHES;
    a shroud moves the second and not the first, and keeping them as separate
    columns is what stops a shroud being drawn as a stiffener (L073).
    """
    nodes = _pipe_nodes(model, ms, U, shift)
    s_nodes = np.array([r[0] for r in nodes])
    x_nodes = np.array([r[1] for r in nodes])
    y_nodes = np.array([r[2] for r in nodes])

    s_dense = np.linspace(s_nodes.min(), s_nodes.max(), n)
    xs = np.interp(s_dense, s_nodes, x_nodes)
    ys = np.interp(s_dense, s_nodes, y_nodes)

    rows = []
    for k, s_mat in enumerate(s_dense):
        s_sta = float(s_mat) + shift
        ax, ay = scene.path.position(s_sta)
        nx, ny = scene.path.normal(s_sta)
        px, py = float(xs[k]), float(ys[k])
        x_local = s_centre - float(s_mat)
        sec = ils.assembly.section_at(x_local) if ils is not None else None
        con = ils.assembly.contact_at(x_local) if ils is not None else None
        row = _ctx('geometry', context)
        row.update(
            table='geometry', step=step, shift=shift, converged=converged,
            sample=k, s_material=float(s_mat), s_station=s_sta,
            x=px, y=py, arc_x=float(ax), arc_y=float(ay),
            normal_x=float(nx), normal_y=float(ny),
            off_arc=(px - ax) * nx + (py - ay) * ny,
            OD_section=float(getattr(sec, 'OD', OD)) if sec else OD,
            t_section=float(getattr(sec, 't', 0.0) or 0.0) if sec else 0.0,
            y_contact=(float(getattr(con, 'y', OD / 2.0)) if con
                       else OD / 2.0),
            section_owner=(getattr(sec, 'owner', 'pipe') if sec else 'pipe'),
            contact_owner=(getattr(con, 'owner', 'pipe') if con else 'pipe'),
            region=rg.classify(float(s_mat), geom),
        )
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# table 2 -- sections
# ---------------------------------------------------------------------------

def s_to_x(model, ms, U, shift):
    """Interpolator material `s` -> world `x` ON THE SOLVED PIPE.

    The sections table needs the same x as the geometry table, and
    `-(s + shift)` is NOT it: that drops the axial displacement, so the
    staircase would sit a few millimetres off the shape it describes and the
    two tables would disagree about where an element is. Small, and exactly
    the kind of quiet mismatch this artifact exists to prevent.
    """
    nodes = _pipe_nodes(model, ms, U, shift)
    sv = np.array([r[0] for r in nodes])
    xv = np.array([r[1] for r in nodes])
    return lambda q: float(np.interp(q, sv, xv))


def section_rows(problem, result, shift, step, converged, zone_s_max,
                 context, fx=None, geom=None) -> list:
    """One row per element, for ONE position.

    BOTH ENDS, not a midpoint. Strain is piecewise constant per element, so
    drawing it at midpoints interpolates a gradient the model does not have
    and leaves a half-element gap against a junction that reads as missing
    data rather than as the step it is (L071).
    """
    if fx is None:
        def fx(q):
            return -(q + shift)
    secs = {q.index: q for q in problem.sections}
    s_of = {i: sv for (i, sv, _y) in problem.nodes}
    ends = {idx: sorted((s_of[n1], s_of[n2]))
            for (idx, n1, n2, _o, _l) in problem.elements}
    owner_of = {idx: o for (idx, _n1, _n2, o, _l) in problem.elements}
    moments = {i: m for (i, _s, m) in getattr(result, 'moments', ())}

    rows = []
    for (idx, _s_mid, eps) in sorted(getattr(result, 'strains', ()),
                                     key=lambda t: t[1]):
        lo, hi = ends.get(idx, (0.0, 0.0))
        sec = secs.get(idx)
        row = _ctx('sections', context)
        row.update(
            table='sections', step=step, shift=shift, converged=converged,
            element=int(idx),
            s_material_0=float(lo), s_material_1=float(hi),
            s_station_0=float(lo) + shift, s_station_1=float(hi) + shift,
            x_0=fx(float(lo)), x_1=fx(float(hi)),
            strain=float(eps), moment=float(moments.get(idx, 0.0)),
            OD_section=float(getattr(sec, 'OD', 0.0)) if sec else 0.0,
            section_owner=(getattr(sec, 'owner', 'pipe') if sec else 'pipe'),
            owner=str(owner_of.get(idx, 'pipeline')),
            region=rg.region_of_element(float(lo), float(hi), geom),
            in_band=bool(float(hi) + shift < zone_s_max),
        )
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# table 3 -- stations
# ---------------------------------------------------------------------------

def member_rows(problem, model, ms, U, shift, step, converged, context) -> list:
    """One row per NON-PIPELINE element, for ONE position.

    The attached structure and the connectors that fasten it. Both ends are
    given in world coordinates on the SOLVED structure, because that is what
    a drawing needs and re-deriving it from node ids would make the figure
    depend on the kernel's numbering.

    Empty for every model without an EA structure, which is why adding this
    table costs nothing where there is nothing to say.
    """
    at = {n.index: n for n in model.nodes}
    s_of = {i: sv for (i, sv, y) in problem.nodes}
    y_of = {i: y for (i, sv, y) in problem.nodes}
    ratio = {e.index: e.stiffness_ratio for e in model.elements}

    def world_of(i):
        n = at[i]
        return _world(n.s + shift, n.y, U[dof(ms, i, 0)], U[dof(ms, i, 1)])

    rows = []

    def add(idx, n1, n2, kind, owner, ctype, slot):
        x0, y0 = world_of(n1)
        x1, y1 = world_of(n2)
        row = _ctx('members', context)
        row.update(table='members', step=step, shift=shift,
                   converged=converged, element=int(idx), kind=kind,
                   owner=str(owner), x_0=x0, y_0=y0, x_1=x1, y_1=y1,
                   s_material_0=float(s_of[n1]), s_material_1=float(s_of[n2]),
                   stiffness_ratio=float(ratio.get(idx) or 1.0),
                   conn_type=str(ctype), slot=int(slot))
        rows.append(row)

    for (idx, n1, n2, owner, _line) in problem.elements:
        if owner == 'pipeline':
            continue
        add(idx, n1, n2, 'structure', owner, '', -1)
    for (idx, n1, n2, ctype, _length, slot) in problem.connectors:
        add(idx, n1, n2, 'connector', 'GD-Con', ctype, slot)
    return rows


def station_rows(scene, context) -> list:
    """One row per roller. No `step`: rollers do not move when the pipe does."""
    rows = []
    for st in scene.stations:
        row = _ctx('stations', context)
        row.update(
            table='stations', station=st.name, role=str(st.role.name),
            s_station=float(st.s_arc), x=float(st.x), y=float(st.y),
            radius=float(st.radius),
            one_sided=bool(st.role is StationRole.CONTACT
                           and getattr(st, 'one_sided', False)),
        )
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# writing, and the checks that make it worth trusting
# ---------------------------------------------------------------------------

def _check(table: str, rows: list) -> None:
    """Refuse rows the contract does not describe, or that break their grain.

    THREE FAILURES, EACH SEEN IN THIS PROJECT IN SOME FORM:
      * an undeclared column -- the union-of-whatever-was-passed defect the
        case schema was written to kill;
      * a `per='case'` column that is not constant -- a per-row value leaking
        into a header-ish column, which a reader would take as the case's;
      * a `per='position'` column moving inside a step -- two positions
        merged into one, which no plot would show.
    """
    if not rows:
        raise ValueError(f'{table}: refusing to write an empty table')
    cols = list(rows[0])
    bad = ps.unknown(table, cols)
    if bad:
        raise ValueError(f'{table}: undeclared columns {bad}')
    missing = [c for c in ps.header(table) if c not in cols]
    if missing:
        raise ValueError(f'{table}: missing declared columns {missing}')
    want = set(cols)
    for r in rows:
        if set(r) != want:
            raise ValueError(f'{table}: rows disagree on columns')

    for c in ps.constants(table):
        seen = {r[c] for r in rows}
        if len(seen) > 1:
            raise ValueError(
                f'{table}: {c!r} is declared per=case but takes '
                f'{len(seen)} values {sorted(map(str, seen))[:4]}')
    per_pos = ps.per_position(table)
    if per_pos and 'step' in cols:
        by_step = {}
        for r in rows:
            by_step.setdefault(r['step'], []).append(r)
        for stp, group in by_step.items():
            for c in per_pos:
                seen = {g[c] for g in group}
                if len(seen) > 1:
                    raise ValueError(
                        f'{table}: step {stp} has {len(seen)} values of '
                        f'{c!r}, which is declared per=position')


def _fmt(v):
    """One value, as CSV text.

    NUMPY SCALARS ARE NOT PYTHON FLOATS, and under numpy 2 their `repr` is
    `np.float64(-9.6196)` rather than `-9.6196`. A row built from a
    displacement array carries them without anyone noticing, and the file
    then parses as text: the members table went out with every coordinate
    wrapped like that and the plotter refused it. Coerced here, once, rather
    than by remembering to call `float()` at every site that builds a row.
    """
    if isinstance(v, bool) or isinstance(v, np.bool_):
        return 'true' if v else 'false'
    if isinstance(v, (float, np.floating)):
        return repr(float(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return v


def write_table(table: str, rows: list, path) -> dict:
    """Write one table plus its schema sidecar. Returns a small summary."""
    _check(table, rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ps.header(table)
    with path.open('w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([_fmt(r[c]) for c in cols])
    side = Path(str(path) + '.schema.json')
    side.write_text(json.dumps(ps.as_dict(table), indent=2) + '\n')
    return dict(table=table, path=str(path), rows=len(rows),
                columns=len(cols), schema=str(side))


def write(stem, scene, positions, model_of, ils, s_centre, OD, context,
          zone_s_max, n=N_SAMPLES) -> dict:
    """Write all three tables for a passage.

    `positions` is the solved sweep and `model_of(position)` hands back the
    `(model, ms, U, problem)` for one of them -- injected rather than rebuilt
    here, because assembling a model is L4's job and a report must not
    quietly become a second place that does it.
    """
    stem = Path(stem)
    # Measured ONCE, off the assembly, and shared by both tables. A region
    # boundary is a fixed point on the steel, so it must not be re-derived
    # per position -- the two tables would then disagree about where X2 is.
    geom = rg.offset_geometry(ils, s_centre, OD)
    geo, sec, mem = [], [], []
    for step, pos in enumerate(positions):
        model, ms, U, problem = model_of(pos)
        conv = bool(getattr(pos, 'converged', True))
        geo += geometry_rows(scene, model, ms, U, ils, s_centre, OD,
                             pos.shift, step, conv, context, n=n, geom=geom)
        sec += section_rows(problem, pos.result, pos.shift, step, conv,
                            zone_s_max, context, geom=geom,
                            fx=s_to_x(model, ms, U, pos.shift))
        mem += member_rows(problem, model, ms, U, pos.shift, step, conv,
                           context)
    out = {}
    for table, rows in (('geometry', geo), ('sections', sec),
                        ('stations', station_rows(scene, context)),
                        ('members', mem)):
        if not rows:
            continue          # no attached structure: no members table
        out[table] = write_table(
            table, rows, Path(str(stem) + ps.TABLE_SUFFIX[table]))
    return out


def case_context(case_id, family, scene, problem, OD, t_wall, tension_mt,
                 L_comp, s_centre, zone_s_max, n_positions,
                 envelope_step, region_scheme='') -> dict:
    """The per-case columns, built once so the three tables cannot disagree.

    `stiffness_ratio` and `n_junctions` come off the SOLVED problem rather
    than from the case definition: a shroud is defined as a component and
    solves as bare pipe, and the number that matters is the one the model
    actually has.
    """
    return dict(
        profile_schema_version=ps.PROFILE_SCHEMA_VERSION,
        case_id=str(case_id), family=str(family),
        R=float(scene.path.R), spacing=float(scene.spacing),
        OD=float(OD), t_wall=float(t_wall), tension_mt=float(tension_mt),
        L_comp=float(L_comp), s_centre=float(s_centre),
        zone_s_max=float(zone_s_max), n_positions=int(n_positions),
        stiffness_ratio=float(jr.stiffness_ratio(problem)),
        n_junctions=int(len(jr.junctions(problem))),
        envelope_step=int(envelope_step),
        region_scheme=str(region_scheme),
    )

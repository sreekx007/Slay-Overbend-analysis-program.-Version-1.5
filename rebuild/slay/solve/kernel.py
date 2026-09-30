"""slay.solve.kernel -- the boundary with `nlfea_v4`, and the one indirection
every caller owes it.

The kernel is FROZEN (G6) and it numbers its own mesh. This module is the
only place in the package that touches it, so the numbering rule lives in
exactly one spot.

THE INDIRECTION, and it is not optional. `MeshedStructure._mesh` assigns mesh
indices in ELEMENT-ENCOUNTER order, so `user_node_to_mesh` is a PERMUTATION
of our node ids and not the identity. Writing connector stiffness at
`3*node_id` put it on four frame nodes' worth of the wrong rows and left
theirs empty: twelve zero diagonals and an exactly singular matrix (L009).
The map is a bijection, and a bijection is all it is.

CONNECTORS ARE ASSEMBLED OUTSIDE THE KERNEL MESH. A corotational beam derives
its stiffness from its own length and the rule forbids that, so the kernel
gets the pipeline and the structure only, and `slay.physics.connector`
supplies the rest.
"""

from __future__ import annotations

import numpy as np

import config
import nlfea_v4 as fe
from slay.physics.connector import connector_k6, NOMINAL_AXIS

# The EA structure carries a `stiffness_ratio`, which scales EA and EI
# together -- so it is the same section at `ratio * E`, not a different
# section. Two kernel materials is all that needs.
MAT_PIPE, MAT_STRUCT = 1, 2


def ea_owner(model) -> str:
    """Which owner tag the EA structure carries in THIS model: 'ST' or 'SB'.

    Read off the elements rather than assumed. Both EA archetypes go through
    one code path, and nothing downstream should have to know which it got --
    a hardcoded 'ST' is three separate crashes on ILS-EASB (L036).
    """
    owners = {e.owner for e in model.elements} - {'pipeline', 'GD-Con'}
    if len(owners) != 1:
        raise ValueError(f'expected exactly one EA owner, got {sorted(owners)}')
    return owners.pop()


def structural_ratio(model) -> float:
    """The EA structure's `stiffness_ratio`, read off its elements."""
    ratios = {e.stiffness_ratio for e in model.elements
              if e.stiffness_ratio is not None}
    if not ratios:
        return 1.0
    if len(ratios) != 1:
        raise ValueError(f'expected one stiffness_ratio, got {sorted(ratios)}')
    return ratios.pop()


def mesh(model, OD: float = None, t_wall: float = None, E: float = None):
    """`MeshedStructure` for the beams only, plus the beam list behind it.

    Asserts the kernel did not alter the model. It used to: mesh nodes were
    keyed by rounded COORDINATE, so ILS-EASB's seven coincident pairs welded
    into each other (L001). The kernel keys on node id now, and this is the
    check that says so at every call rather than once in a test.
    """
    OD = config.OD_PIPE_DEF if OD is None else OD
    t_wall = config.T_WALL_DEF if t_wall is None else t_wall
    E = config.STEEL_E if E is None else E

    beams = [e for e in model.elements if e.connector is None]
    ea = ea_owner(model)
    ratio = structural_ratio(model)
    mdl = fe.Model(
        nodes=[fe.Node(n.index, n.s, n.y) for n in model.nodes],
        elements=[fe.UserElement(k, e.n1, e.n2,
                                 MAT_STRUCT if e.owner == ea else MAT_PIPE,
                                 1, seed=1)
                  for k, e in enumerate(beams)],
        sections=[fe.PipeSection(1, OD, t_wall)],
        materials=[fe.Material(MAT_PIPE, E),
                   fe.Material(MAT_STRUCT, ratio * E)])
    ms = fe.MeshedStructure(mdl)
    if ms.n_nodes != model.n_nodes:
        raise AssertionError(
            f'the kernel altered the model: {model.n_nodes} nodes in, '
            f'{ms.n_nodes} out. Coincident nodes are legal and must stay '
            f'distinct -- see G6 and L001.')
    return ms, beams


def dof(ms, node_index: int, comp: int) -> int:
    """Global DOF for one of OUR node indices. NOT `3*node_index + comp`."""
    return 3 * ms.user_node_to_mesh[node_index] + comp


def connector_elements(model):
    """(element, n1, n2, dx, dy) for each connector, chord pipe-side first."""
    at = {n.index: n for n in model.nodes}
    out = []
    for e in model.elements:
        if e.connector is None:
            continue
        a, b = at[e.n1], at[e.n2]
        out.append((e, e.n1, e.n2, b.s - a.s, b.y - a.y))
    return out


def assemble(model, ms, U, axis=NOMINAL_AXIS, OD=None, t_wall=None, E=None):
    """Tangent stiffness and internal force for beams AND connectors."""
    theta0 = np.arctan2(ms.elem_coords[:, 3] - ms.elem_coords[:, 1],
                        ms.elem_coords[:, 2] - ms.elem_coords[:, 0])
    Kf, Fint_f, _, _, _ = fe.assemble(ms, U, theta0, {}, [], 1.0)
    K = Kf.toarray()
    Fint = Fint_f.copy()
    for (_e, n1, n2, dx, dy) in connector_elements(model):
        k6 = connector_k6(dx, dy, axis=axis, OD=OD, t_wall=t_wall, E=E)
        d = [dof(ms, n1, 0), dof(ms, n1, 1), dof(ms, n1, 2),
             dof(ms, n2, 0), dof(ms, n2, 1), dof(ms, n2, 2)]
        K[np.ix_(d, d)] += k6
        Fint[d] += k6 @ U[d]
    return K, Fint


# ---------------------------------------------------------------------------
# a Problem, turned into a kernel mesh
# ---------------------------------------------------------------------------
#
# T4's `Problem` is flat and serialisable on purpose -- no Model object, no
# Scene, nothing live. That makes it the solver's real input rather than a
# side artifact, and this is where it becomes a mesh. Sections are per
# ELEMENT (a taper changes along its length), so distinct (OD, t) pairs are
# pooled into kernel sections and distinct E values into kernel materials.


def _kernel_material(mid: int, material, E: float):
    """A slay material at modulus `E`, as the kernel wants it.

    `E` comes from the SECTION, not the material: a `stiffness_ratio` scales
    the modulus on the same section, so two elements can share a material
    model and differ in E. The kernel's elastic `Material` carries E
    directly; the inelastic ones carry their own and are scaled by rebuilding
    them at the scaled modulus rather than by scaling their stress table,
    which would change the yield point instead of the stiffness.
    """
    from slay.data.materials import J2Material, RambergOsgoodMaterial
    if material is None:
        return fe.Material(mid, E)
    if isinstance(material, RambergOsgoodMaterial):
        return fe.RambergOsgood(
            id=mid, E=E, sig_y=material.sig_ys,
            alpha=material.alpha_dnv, n=material.n_ro)
    if isinstance(material, J2Material):
        return fe.IncrementalIsotropic(
            id=mid, E=E, sigma_y0=material.sigma_y0, H=0.0,
            eps_p_table=np.asarray(material.plastic_strain, float),
            sigma_y_table=np.asarray(material.yield_stress, float))
    raise TypeError(f'unknown material type {type(material).__name__}')


def pipe_section_of(problem):
    """(OD, t, E) of the PIPELINE section, for sizing connectors.

    A connector's own 6x6 is built on the pipe's section properties -- it is
    a clamp of pipe-like proportions, not a member with a section of its own
    -- so a non-default diameter has to come from the Problem rather than
    from `config`. Taken as the most common section among pipeline elements,
    because a tapered component gives the pipeline several and the modal one
    is the plain pipe.
    """
    secs = {s.index: s for s in problem.sections}
    counts = {}
    for (idx, _n1, _n2, owner, _line) in problem.elements:
        if owner != 'pipeline' or idx not in secs:
            continue
        s = secs[idx]
        counts[(s.OD, s.t, s.E)] = counts.get((s.OD, s.t, s.E), 0) + 1
    if not counts:
        return (config.OD_PIPE_DEF, config.T_WALL_DEF, config.STEEL_E)
    return max(counts, key=counts.get)


def problem_connectors(problem, ms, OD=None, t_wall=None, E=None):
    """[(dofs, k6)] -- one entry per connector on a Problem.

    WHY THIS EXISTS. `Problem` splits connectors out of `elements` into their
    own field, and `mesh_of_problem` builds the kernel mesh from `elements`
    alone -- correctly, because a corotational beam would take its stiffness
    from its own length and a connector's length is geometry, not stiffness
    (the module docstring above). But nothing then put the connectors BACK,
    so `solve.passage` assembled the EA frame attached to nothing at all:
    18 frame elements, 2 connectors dropped, a rigid-body mechanism and an
    exactly singular matrix. `kernel.assemble` does this for the Model path
    and had no counterpart here.

    G9 IS ENFORCED HERE. The solver implements type F only. A P, S or D
    connector is REFUSED rather than approximated, because approximating it
    would silently answer a different question -- the joint type selects
    which DOF the constraint ties, and substituting F ties all of them.
    """
    OD_p, t_p, E_p = pipe_section_of(problem)
    OD = OD_p if OD is None else OD
    t_wall = t_p if t_wall is None else t_wall
    E = E_p if E is None else E

    xy = {i: (sv, y) for (i, sv, y) in problem.nodes}
    out = []
    for (_idx, n1, n2, ctype, _length, slot) in problem.connectors:
        kind = str(ctype).upper().lstrip('TYPE').strip() or str(ctype).upper()
        if not kind.startswith('F'):
            raise ValueError(
                f'connector at slot {slot} is type {ctype!r}; the solver '
                f'implements F only and must refuse the rest rather than '
                f'approximate it (G9)')
        (s1, y1), (s2, y2) = xy[n1], xy[n2]
        k6 = connector_k6(s2 - s1, y2 - y1, axis=NOMINAL_AXIS,
                          OD=OD, t_wall=t_wall, E=E)
        dofs = [dof(ms, n1, 0), dof(ms, n1, 1), dof(ms, n1, 2),
                dof(ms, n2, 0), dof(ms, n2, 1), dof(ms, n2, 2)]
        out.append((dofs, k6))
    return out


def mesh_of_problem(problem, n_points_polar: int = 8, n_fibres: int = 20,
                    polar: bool = True):
    """(MeshedStructure, beams, element-index -> kernel element id).

    `polar` selects the B31-equivalent angular integration the reference runs
    use by default; `fibre` is the converged Cartesian scheme. They are not
    interchangeable and the choice changes the answer in deep plasticity, so
    it is an argument rather than a constant.
    """
    secs = {s.index: s for s in problem.sections}
    s_of = {i: sv for (i, sv, _y) in problem.nodes}

    def forced_elastic(n1, n2) -> bool:
        """Is this element inside a span the Problem forces elastic?

        Judged on the element MIDPOINT: an element straddling the boundary
        belongs to whichever side holds most of it, which is the same rule
        the section binder uses and avoids a half-elastic element.
        """
        mid = 0.5 * (s_of[n1] + s_of[n2])
        return any(lo - 1e-9 <= mid <= hi + 1e-9
                   for (lo, hi) in problem.elastic_spans)

    sec_key, mat_key = {}, {}
    sections, materials = [], []
    for s in problem.sections:
        k = (round(s.OD, 12), round(s.t, 12))
        if k not in sec_key:
            sec_key[k] = len(sections) + 1
            sections.append(
                fe.PipeSectionPolar(sec_key[k], s.OD, s.t, n_points_polar)
                if polar else fe.PipeSection(sec_key[k], s.OD, s.t, n_fibres))

    # Materials are keyed by (E, elastic?) rather than E alone, so a forced
    # -elastic span shares a section with its neighbours and differs only in
    # constitutive law. `_kernel_material(..., None, E)` is the kernel's
    # linear elastic path.
    def material_id(E, elastic):
        key = (round(E, 6), bool(elastic))
        if key not in mat_key:
            mat_key[key] = len(materials) + 1
            materials.append(_kernel_material(
                mat_key[key], None if elastic else problem.material, E))
        return mat_key[key]

    elems, index_of = [], {}
    for (idx, n1, n2, _owner, _line) in problem.elements:
        s = secs[idx]
        eid = len(elems)
        index_of[idx] = eid
        elems.append(fe.UserElement(eid, n1, n2,
                                    material_id(s.E, forced_elastic(n1, n2)),
                                    sec_key[(round(s.OD, 12),
                                             round(s.t, 12))], seed=1))
    mdl = fe.Model(
        nodes=[fe.Node(i, s, y) for (i, s, y) in problem.nodes],
        elements=elems, sections=sections, materials=materials)
    ms = fe.MeshedStructure(mdl)
    if ms.n_nodes != problem.n_nodes:
        raise AssertionError(
            f'the kernel altered the model: {problem.n_nodes} nodes in, '
            f'{ms.n_nodes} out (G6, L001)')
    return ms, mdl, index_of

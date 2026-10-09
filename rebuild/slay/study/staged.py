"""slay.study.staged -- the four-step staged sequence, as a workflow.

THE SEQUENCE, ruled 21 Sep 2026 (`T5_solve_spec.md` 5e):

    1  displacements   contact targets ramped 0 -> 1. ELASTIC, and EVERY
                       roller BIDIRECTIONAL -- nothing may lift off, so the
                       pipe is driven onto the arc with no active set to
                       chatter and no load fighting it.
    2  gravity         gravity on, ELASTIC, and LIFT-OFF ACTIVATED: the ruled
                       one-sided set takes effect and rollers may release.
    3  tension         lay tension at SR7. ELASTIC.
    4  plasticity      material switched to J2, everything else held.

WHY THIS ORDER WORKS where a single proportional solve does not. 120 MT on a
straight, unstressed pipe has nothing to react it: no geometric stiffness
exists yet, the first Newton step is 3.2 m against a 1.0 m threshold, and it
diverges (L050, L051). Here the pipe is already bent to the arc and already
carrying its own weight before the tension arrives, so the stiffness that
reacts it is there by the time it is needed.

Step 1's all-bidirectional set matters for the same reason from the other
side: a one-sided roller cannot pull, so with no tension yet applied the
stinger rollers would release and the pipe would never reach the arc at all.
Holding every roller through step 1 builds the geometry; step 2 then hands
the active set its real rule and lets whatever wants to lift off, lift off.

WHY IT IS A STUDY AND NOT A TOOL. `study` is where an ORDERED SERIES OF
PROBLEMS SOLVED WITH CHAINED STATE lives -- that is what `sweep.run` is, and
this has the same shape. It differs only in WHAT VARIES between steps: a
sweep moves the pipe, this one turns loads and the material on. It lived in
`tools/stage_run.py` until 9 Oct 2026, where `check_layers` did not police
it and nothing but that script could call it, and it carried three copies of
library code to do so -- `all_bidirectional` (which `scene.scene` already
had and `sweep` already used), the reporting window, and `DROP_AT_TIP`.

IT REPORTS NOTHING, deliberately. `report` is ABOVE `study` in the layer
order, so this module could not call `report.passage.zone` even if it wanted
to -- which is the rule working rather than an obstacle. The sequence returns
the posed Problems and their Results and the caller reports them, exactly as
`sweep.run` does. That is why the duplicate window could be deleted rather
than moved: it was never this layer's to own.

MATERIAL. `build_problem(material=None)` is the kernel's LINEAR ELASTIC path
(`_kernel_material` returns a bare `fe.Material`); 'j2' is incremental
plasticity, path-dependent, which is what "activate plasticity" means. 'ro'
is Ramberg-Osgood -- nonlinear but path-INDEPENDENT -- so it is not used
here, though it is what the reference `run_slay` runs by default.

Workflow: Mode S (staged). Compare `sweep.run`'s Mode A and Mode B.
"""

from __future__ import annotations

from dataclasses import dataclass

from slay.data.materials import material
from slay.model.assemble import build_model
from slay.physics.contact import DEFAULT_SURFACE, material_margin
from slay.physics.problem import build_problem
from slay.scene.scene import all_bidirectional, build_scene
from slay.solve.passage import solve

TON = 9806.65

#: The four steps, in order, as (label, needs_held_scene, gravity, tension,
#: material). Data rather than code so the sequence can be READ, and so a
#: caller can see what it is about to run without tracing a function.
STEPS = (
    ('1  displacements, elastic, all held', True,  False, False, None),
    ('2  + gravity, lift-off active',       False, True,  False, None),
    ('3  + tension at SR7',                 False, True,  True,  None),
    ('4  + plasticity (J2)',                False, True,  True,  'j2'),
)


@dataclass(frozen=True)
class Stage:
    """One step: what it was, what was posed, and what came back."""
    index: int
    label: str
    problem: object
    result: object

    @property
    def converged(self) -> bool:
        return bool(self.result.converged)


def scene_for(R: float = 85.0, spacing: float = None,
              elastic: float = 16.0,
              contact_surface: str = None):
    """The Scene the sequence runs on, with room for the contact surface.

    BUILT TWICE ON PURPOSE: once to measure the material correction this
    contact surface demands at the stinger end, once with room for it. A
    slot that falls outside the mesh is applied to the wrong steel and
    converges just as happily (the L048 class).
    """
    surface = DEFAULT_SURFACE if contact_surface is None else contact_surface
    probe = build_scene(R=R, spacing=spacing, elastic_length=elastic)
    return build_scene(R=R, spacing=spacing, elastic_length=elastic,
                       margin_stinger=material_margin(
                           probe, contact_surface=surface))


def problems(model, scene, tension_mt: float = 120.0,
             contact_surface: str = None) -> list:
    """`[(label, Problem)]` -- the four steps posed, none solved.

    Separated from `run` so the sequence can be inspected, diffed or
    re-posed without a solver: `differs_only_in_contact` and the Problem's
    own `to_json` both work on these.
    """
    surface = DEFAULT_SURFACE if contact_surface is None else contact_surface
    held = all_bidirectional(scene)
    T = tension_mt * TON
    out = []
    for label, hold, grav, ten, mat in STEPS:
        out.append((label, build_problem(
            model, held if hold else scene,
            material=None if mat is None else material(mat),
            gravity=grav,
            # FULL TENSION ON ITERATION 1 -- the kernel does not scale loads
            # by `lam` (L050), so "apply tension" is a STEP, not a ramp.
            tension=T if ten else 0.0,
            contact_surface=surface)))
    return out


def run(R: float = 85.0, tension_mt: float = 120.0, spacing: float = None,
        elastic: float = 16.0, contact_surface: str = None,
        scene=None, model=None, stop_on_failure: bool = True) -> tuple:
    """Run the sequence. Returns `(scene, [Stage], state)`.

    STATE IS CHAINED, step to step, which is the whole point: step 4's
    plasticity acts on the stress state steps 1 to 3 built, not on a virgin
    pipe. That is the same `state_in=` chaining `sweep.run` uses for mode A,
    and for the same reason.

    `stop_on_failure` stops at the first step that does not converge, since
    every later step is posed on a state that does not exist. Pass False to
    see them all fail, which is occasionally what a diagnosis wants.
    """
    sc = scene_for(R=R, spacing=spacing, elastic=elastic,
                   contact_surface=contact_surface) if scene is None else scene
    m = build_model(sc) if model is None else model

    out, state = [], None
    for i, (label, p) in enumerate(problems(m, sc, tension_mt=tension_mt,
                                            contact_surface=contact_surface)):
        r, state = solve(p, state_in=state)
        out.append(Stage(index=i, label=label, problem=p, result=r))
        if stop_on_failure and not r.converged:
            break
    return sc, out, state

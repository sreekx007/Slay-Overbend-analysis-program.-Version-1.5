"""slay.study.sweep -- the passage sweep. L7, and the ONLY place a position
loop is allowed to live (G11).

WHAT A SWEEP IS. The vessel moves ahead and pipe is paid out, so the whole
pipeline creeps along the stinger while the rollers stay bolted where they
are. Simulated as a sequence of positions: at each one the pipeline has
advanced a little further, and the model is solved again from the state the
last position ended in.

THE FRAME, and it is the thing to get right. `s` is a MATERIAL coordinate.
After the pipeline advances by `sigma`, material that began at `s_m` sits at
station position `s_m + sigma`, so a station at arc `s_arc` reads material
from `s_arc - sigma`. That is exactly `physics.contact_targets(shift=...)`,
and it is why nothing below L7 needs to know a sweep is happening: each
position is an ordinary `Problem` built at its own shift, and
`differs_only_in_contact` holds between any two of them -- which since
L105 admits the lay tension moving with the sweep, because the LOAD
station is a place on the stinger and not a piece of pipe.

SWEEP LENGTH IS DERIVED, NEVER GUESSED. It follows from the component's
length and where the passage should start and finish:

    start   the component is `clear_before` clear of SR2 on the approach
            side -- its LEADING (stinger-side) edge sits that far before it
    finish  the component is `clear_after` clear past SR2 -- its TRAILING
            (vessel-side) edge sits that far beyond it

    sigma_total = L_comp + clear_before + clear_after

Both clearances default to 1.0 m and are arguments. The travel therefore
grows with the component, which is the point: a 20D body needs a longer
passage than a 2.5D one to make the same traverse.

WHERE THE SWEPT LENGTH GOES: at the vessel end, beyond the last vessel
roller. Material leaves the model at the stinger end and needs nothing
there; it is the vessel end that runs dry. The reference program buys the
same buffer by configuring `n_vr = 10` against `run_slay`'s 3; here it is
the length itself rather than a roller count standing in for it.

THE BUFFER IS `sigma + TAIL_CLEAR`, NOT `sigma`. At exactly `sigma` the
tail of the pipe arrives at the last vessel roller precisely as the sweep
ends -- the roller would sit on the very end of the pipe, with the model's
end support on top of it. The extra metre keeps the tail, and its support,
clear of that roller for the whole passage.

THE BUFFER IS SUPPORTED AND ELASTIC, and both matter physically:

  * `vertical_at` puts a uy-only support under the tail, standing for the
    deck rollers the pipe really rests on behind the tensioner. Without it
    20 m of feedstock hangs off the back of the anchor as a bare cantilever
    and develops bending stress it has no business having. `uy` only: the
    pipe must stay free to move along its own axis, or the support fights
    the feed it exists to allow.
  * `elastic_spans` forces the buffer to a LINEAR ELASTIC material whatever
    the case runs. Feedstock is not part of the answer and must never be
    allowed to yield -- a plastic hinge in the buffer would be carried
    forward into every later position by the chained state.

MODE A vs MODE B (`docs/SLAY_BUILD_INSTRUCTION.md`). Mode A carries state
from position to position -- the real path a component travels. Mode B
solves every position from virgin state -- the worst position anywhere,
whether or not a real lay would reach it. They differ in one line, and that
line is `state_in`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from slay.model.assemble import build_model
from slay.physics.contact import DEFAULT_SURFACE, material_margin
from slay.physics.problem import build_problem
from slay.scene.scene import all_bidirectional
from slay.solve.passage import solve

CLEAR_BEFORE = 1.0        # m, leading edge clear of SR2 at the start
CLEAR_AFTER = 1.0         # m, trailing edge clear of SR2 at the finish
STATION = 'SR2'           # the station the passage is built around
TAIL_CLEAR = 1.0          # m, buffer length BEYOND the sweep -- see below


@dataclass(frozen=True)
class Position:
    """One solved lay position."""
    index: int
    shift: float                      # m the pipeline has advanced
    s_lead: float                     # component leading edge, station coords
    s_trail: float                    # component trailing edge
    result: object = field(repr=False)
    seeded: bool = False              # reached via the staged seed, not direct

    @property
    def converged(self) -> bool:
        return self.result.converged


def sweep_length(L_comp: float,
                 clear_before: float = CLEAR_BEFORE,
                 clear_after: float = CLEAR_AFTER) -> float:
    """Total travel for the component to traverse the station.

    `L_comp + clear_before + clear_after`. Derived from the geometry in the
    module docstring, not chosen.
    """
    if L_comp < 0:
        raise ValueError(f'L_comp must not be negative, got {L_comp}')
    for name, v in (('clear_before', clear_before),
                    ('clear_after', clear_after)):
        if v < 0:
            raise ValueError(f'{name} must not be negative, got {v}')
    return L_comp + clear_before + clear_after


@dataclass(frozen=True)
class Completion:
    """Did the passage actually finish, and if not how far did it get.

    WHY THIS IS A TYPE AND NOT A BOOLEAN. `run` stops at the first
    non-converged position, which is right -- mode A chains state and every
    later position would start from a diverged one. But a truncated passage
    returns a list of Positions that looks exactly like a complete one, and
    an envelope taken over it is a maximum over PART of the traverse. It is
    not a smaller number of the same kind; it is a different quantity, and
    comparing it to a published table is comparing two different things.
    L101 is what that costs: five of the seven TABLE XXXII / XXXIII shroud
    cases were tabulated against Paper 1 having swept between 6.3% and 38.4%
    of the travel they needed, and nothing in the artifact said so.

    `fraction` is of the TRAVEL, which is the honest denominator -- a case
    that solved nine positions of ten has not done 90% of anything if the
    schedule's steps are uneven.
    """
    complete: bool
    total: float               # m of travel the passage was sized for
    ran: float                 # m actually reached, converged
    n_positions: int           # positions attempted
    n_converged: int
    failed_at: float = None    # shift of the first position that did not
    status: str = ''           # that position's solver status

    @property
    def fraction(self) -> float:
        return 1.0 if self.total <= 0.0 else max(0.0, self.ran) / self.total

    def __str__(self) -> str:
        if self.complete:
            return f'passage COMPLETE: {self.ran:.3f} m of {self.total:.3f} m'
        return (f'passage INCOMPLETE: {self.ran:.3f} m of {self.total:.3f} m '
                f'({100 * self.fraction:.1f}%), stopped at shift '
                f'{self.failed_at:.4f} -- {self.status}')


def completion(positions, L_comp: float,
               clear_before: float = CLEAR_BEFORE,
               clear_after: float = CLEAR_AFTER) -> Completion:
    """Was this passage swept end to end? Pass it `run`'s own return value.

    Complete means the LAST position converged AND its shift reached the
    sweep length. Both halves are needed: a passage can stop early without
    a diverged position if the schedule was built short, and it can hold a
    converged final position that is not the final travel.
    """
    total = sweep_length(L_comp, clear_before, clear_after)
    ok = [p for p in positions if p.converged]
    bad = [p for p in positions if not p.converged]
    ran = max((p.shift for p in ok), default=0.0)
    return Completion(
        complete=bool(ok) and not bad and abs(ran - total) <= 1e-6,
        total=total, ran=ran,
        n_positions=len(positions), n_converged=len(ok),
        failed_at=(bad[0].shift if bad else None),
        status=(bad[0].result.status if bad else
                ('' if abs(ran - total) <= 1e-6
                 else 'schedule ended short of the sweep length')))


def start_centre(scene, L_comp: float,
                 clear_before: float = CLEAR_BEFORE,
                 station: str = STATION) -> float:
    """`s_centre` for `build_model` at shift 0.

    The leading edge starts `clear_before` short of the station, so the
    centre is half a component further back again.
    """
    return scene.by_name(station).s_arc - clear_before - L_comp / 2.0


def schedule(total: float, step: float, include=()) -> tuple:
    """Travels in metres, starting at 0 and INCLUDING `total`.

    The final position is the one the sweep was sized for, so it is never
    dropped for not landing on a step boundary -- the last interval is
    short instead.

    `include` are extra travels that must be solved whatever the step lands
    on -- see `critical_shifts`. Merged in, sorted, and de-duplicated to a
    micron, because two positions a nanometre apart are the same position
    solved twice.
    """
    if step <= 0:
        raise ValueError(f'step must be positive, got {step}')
    out, x = [0.0], 0.0
    while x < total - 1e-9:
        x = min(x + step, total)
        out.append(x)
    for v in include:
        if 0.0 <= v <= total:
            out.append(float(v))
    out.sort()
    keep = [out[0]]
    for v in out[1:]:
        if v - keep[-1] > 1e-6:
            keep.append(v)
    return tuple(keep)


def critical_shifts(scene, L_comp: float, s_centre: float,
                    contact_surface: str = DEFAULT_SURFACE,
                    OD: float = None) -> tuple:
    """Travels at which a component EDGE sits exactly on a contact station.

    WHY THESE ARE NOT OPTIONAL. The passage envelope is not at either end of
    the sweep and it is not on a step boundary: measured on GD-TP at R = 85 m,
    9 m spacing, 120 MT, it is where the LEADING EDGE crosses SR2, and the
    peak sharpens as the step refines --

        step 1.00 element   envelope 0.4772%   (missed it)
        step 0.50 element   envelope 0.5482%
        step 0.25 element   envelope 0.5678%   peak at lead = 9.016 ~ SR2

    A whole-element step undersamples the answer by 16%. Refining the step
    everywhere pays for that resolution across the entire passage; solving the
    edge-crossings exactly buys it where it actually lives. So these travels
    go into every schedule and the step only sets the sampling between them.

    A station is crossed by the leading edge when `s_centre + L/2 + shift`
    reaches THE MATERIAL THE STATION BEARS ON, and by the trailing edge when
    `s_centre - L/2 + shift` does. Both matter: the edges are where the
    section changes, and a section change over a roller is the whole reason
    this component is interesting.

    THE MATERIAL, NOT THE STATION'S OWN ARC, and they are the same number
    only under 'centreline'. `physics.contact.station_material` owns the
    mapping and is asked for it here rather than restated -- when the two
    disagreed the GD-TP envelope read 14.5% low and landed on the wrong
    position, because the schedule crossed edges where the slots no longer
    were.

    Empty for plain pipe -- there are no edges, and nothing distinguishes one
    travel from another.
    """
    from slay.physics.contact import station_material
    if L_comp <= 0.0:
        return ()
    out = []
    for s_ref in station_material(scene, contact_surface, OD).values():
        for edge in (s_centre + L_comp / 2.0, s_centre - L_comp / 2.0):
            out.append(s_ref - edge)
    return tuple(sorted(v for v in out if v > 0.0))


def buffer_length(L_comp: float,
                  clear_before: float = CLEAR_BEFORE,
                  clear_after: float = CLEAR_AFTER,
                  tail_clear: float = TAIL_CLEAR) -> float:
    """Pipe to add at the vessel end: the sweep, plus tail clearance."""
    if tail_clear < 0:
        raise ValueError(f'tail_clear must not be negative, got {tail_clear}')
    return sweep_length(L_comp, clear_before, clear_after) + tail_clear


def scene_for(R=None, spacing=None, L_comp=0.0,
              clear_before=CLEAR_BEFORE, clear_after=CLEAR_AFTER,
              tail_clear=TAIL_CLEAR, contact_surface=None, OD=None, **kw):
    """A Scene whose buffers are sized for this exact passage.

    BOTH ends are sized here. The vessel side carries the sweep buffer, as
    it always has. The stinger side carries the material correction the
    contact surface demands: a slot riding at `R + r_roller + OD/2` sits
    `(R_eff - R) * theta` outboard of its station, and a slot past the last
    node is applied to the wrong material (6 Oct 2026).

    Measured, not derived twice: the scene is built once to find the worst
    correction and once more with the room for it. Two cheap constructions
    beat a closed form that has to be kept in step with `station_material`.
    """
    from slay.physics.contact import DEFAULT_SURFACE, material_margin, material_margin
    from slay.scene.scene import build_scene
    surf = DEFAULT_SURFACE if contact_surface is None else contact_surface
    base = dict(R=R, spacing=spacing,
                margin_vessel=buffer_length(L_comp, clear_before,
                                            clear_after, tail_clear),
                **kw)
    probe = build_scene(**base)
    return build_scene(margin_stinger=material_margin(probe, OD, surf),
                       **base)


def buffer_span(scene) -> tuple:
    """(s_lo, s_first_station) -- the pipe added beyond the last station."""
    return (min(scene.extent), min(st.s_arc for st in scene.stations))


def check_reach(scene, total: float) -> None:
    """Refuse a sweep the model cannot feed.

    At travel `sigma` the innermost contact station reads material from
    `s_arc - sigma`. If that is short of the model's vessel end there is no
    pipe there to read, and the run would report a number for a station
    bearing on nothing.
    """
    from slay.scene.rollers import StationRole
    contacts = [st for st in scene.stations
                if st.role is StationRole.CONTACT]
    if not contacts:
        raise ValueError('scene has no contact stations to sweep past')
    inner = min(st.s_arc for st in contacts)
    s_lo = min(scene.extent)
    if inner - total < s_lo - 1e-9:
        # The SHORTFALL, not the whole sweep: the station already sits
        # `inner - s_lo` inboard of the model end, and that headroom counts.
        need = total - (inner - s_lo)
        raise ValueError(
            f'sweep of {total:.3f} m runs the innermost contact station '
            f'({inner:+.3f}) off the vessel end of the model ({s_lo:+.3f}). '
            f'It has {inner - s_lo:.3f} m of headroom, so this needs '
            f'margin_vessel >= {need:.3f} m -- or use study.sweep.scene_for, '
            f'which sizes it at the full {total:.3f} m and ignores the '
            f'headroom on purpose, so the buffer does not depend on where '
            f'the innermost roller happens to sit.')


def _required_stations(scene) -> tuple:
    """Arc positions the analysis needs a real node at.

    The FIXED station, because `physics.boundary_conditions` refuses a
    restraint with no node under it. Contact stations are NOT here: they are
    interpolated inside an element on purpose (G1).
    """
    from slay.scene.rollers import StationRole
    return tuple(st.s_arc for st in scene.stations
                 if st.role is StationRole.FIXED)


def seed_state(model, scene, problem_kw):
    """Build a converged state to start a hard first position from.

    (state, note). `state` is None when the seeding itself could not
    converge, and the caller is then no worse off than without it.

    WHY THE FIRST POSITION IS THE HARD ONE. `solve` ramps the contact targets
    by `lam` but applies tension and gravity at FULL VALUE from Newton
    iteration 1 -- the kernel does not scale loads, and that is deliberate
    (L050). So a cutback shrinks the targets and nothing else, and
    `CUTBACK EXHAUSTED at lam=0.0000` means the very first step was already
    beyond reach. On a straight unstressed pipe there is no geometric
    stiffness to react a lay tension with, and no amount of ramping creates
    any: 160 MT on 168.3 mm pipe is 9.4 times its own EI/L^2 at 12 m
    spacing.

    THE ORDER MATTERS AND THE OPPOSITE ORDER WAS TRIED AND REJECTED. Settling
    the LOADS first with the targets held at their anchors diverges above
    about 15 MT (`T5_solve_spec.md` 5, L050/L051). What works is the reverse:
    bend the pipe onto the rollers FIRST, so the geometric stiffness exists,
    and only then hand it the loads. Three elastic steps, each carrying
    state forward, exactly the first three of the staged sequence that
    reproduces the reference to within 1.7% (5e):

        1  every roller held, no loads      -- builds the geometry
        2  ruled one-sided set + gravity    -- lift-off, with weight to resist
        3  + tension                        -- onto a pipe already bent

    Step 4, plasticity, is the caller's own solve chained onto this. The
    seed is ELASTIC throughout: J2 is incremental and path-dependent, so
    letting it yield during seeding would write a plastic history that the
    real load path never went through.
    """
    held = all_bidirectional(scene)
    state = None
    tension = problem_kw.get('tension', 0.0)
    for sce, gravity, tens in ((held, False, 0.0),
                               (scene, True, 0.0),
                               (scene, True, tension)):
        kw = dict(problem_kw, material=None, gravity=gravity, tension=tens)
        result, state = solve(build_problem(model, sce, **kw),
                              state_in=state)
        if not result.converged:
            return None, result.status
    return state, 'seeded'


def run(scene, ils=None, *, L_comp=0.0, step=None,
        clear_before=CLEAR_BEFORE, clear_after=CLEAR_AFTER,
        station=STATION, mode='A', s_centre=None,
        target_len=None, include_critical=True, seed=True, verbose=False,
        emit_unenforced_conn_types=frozenset(), **problem_kw) -> list:
    """Solve the passage. Returns a list of `Position`, one per lay position.

    `mode='A'` carries state forward; `mode='B'` solves each position from
    virgin state. Any other keyword goes to `build_problem`.

    `include_critical` adds the edge-crossing travels (`critical_shifts`) to
    the schedule whatever `step` lands on. On by default because without them
    the envelope depends on the step -- see that function for the numbers.
    """
    if mode not in ('A', 'B'):
        raise ValueError(f"mode must be 'A' or 'B', got {mode!r}")
    total = sweep_length(L_comp, clear_before, clear_after)
    check_reach(scene, total)
    step = total if step is None else step

    if s_centre is None:
        s_centre = start_centre(scene, L_comp, clear_before, station)
    # THE ANCHOR NEEDS A NODE UNDER IT, and with a vessel-side buffer it no
    # longer gets one for free. `boundary_conditions` refuses a restraint
    # that has no node within 1e-6 m. At `margin_vessel = 0` the model's
    # vessel end coincided with the FIXED station, so `PIPE-LO` WAS the
    # anchor node by coincidence; push the end back and the mesh grid no
    # longer lands on it. `extra_stations` is the documented route for a
    # point an outside layer requires a node at.
    # `emit_unenforced_conn_types` is the mesher's NARROW opt-in: it emits a
    # joint's geometry and its declared Association and enforces nothing,
    # leaving the caller to enforce it in full. `solve.passage` now carries
    # the co-rotating frame an `S` needs, so passing 'S' through here is
    # taking that obligation on rather than evading it (G9).
    model = build_model(scene, ils, s_centre=s_centre,
                        extra_stations=_required_stations(scene),
                        emit_unenforced_conn_types=emit_unenforced_conn_types,
                        **({} if target_len is None
                           else {'target_len': target_len}))

    # The driver owns these three, because they must AGREE. `build_model`
    # places the component at `s_centre`; `contact_targets` looks its
    # surface up at `s_centre - s_mat`. The same number, or the contact
    # surface is read at the wrong place along the component.
    if ils is not None:
        problem_kw.setdefault('assembly', ils.assembly)
        problem_kw.setdefault('ils', ils)
    problem_kw['s_centre'] = s_centre

    # The buffer supports itself and stays elastic, for the whole passage.
    lo, hi = buffer_span(scene)
    if hi > lo + 1e-9:
        problem_kw.setdefault('vertical_at', (lo,))
        problem_kw.setdefault('elastic_spans', ((lo, hi),))

    # `s_centre` is a MATERIAL coordinate and does not move with the sweep.
    # The component stays where it is in the pipe; `shift` is what carries
    # the pipe past the rollers.
    # THE STINGER MARGIN AND THE OD ARE A HARD PAIR, and getting them out of
    # step does not fail loudly -- it brings back the M1 divergence.
    #
    # The margin exists to hold the terminal slot, which sits
    # `(r_roller + OD/2) * theta` outboard of its station. Size it with a
    # different OD than the targets use and the model ends somewhere other
    # than on that slot. TOO LITTLE and `contact_targets` refuses outright.
    # TOO MUCH is the dangerous one: the surplus is unconstrained pipe past
    # the last contact, which is exactly the free cantilever D6 removed, and
    # 160 MT on it diverges at lam=0.0000 (L050, L051). Measured: a 6 in
    # passage given a 16 in margin -- 0.32 m allocated where 0.17 m was
    # needed -- took the hard corner from 7/7 converged to failing at
    # position 0, while the same case with a matched margin converges
    # (6 Oct 2026).
    #
    # So this is checked here rather than trusted, because `scene_for` and
    # `run` are called separately and nothing else pairs their arguments.
    _surf = problem_kw.get('contact_surface', DEFAULT_SURFACE)
    _need = material_margin(scene, problem_kw.get('OD'), _surf)
    _have = max(scene.extent) - max(st.s_arc for st in scene.stations)
    if abs(_have - _need) > 1e-6:
        raise ValueError(
            f'the scene has {_have:.4f} m of pipe past its last station but '
            f'contact_surface={_surf!r} at this OD needs exactly '
            f'{_need:.4f} m: too little and a slot falls off the mesh, too '
            f'much and the surplus is unconstrained pipe past the terminal '
            f'slot, which diverges. Build the scene with the SAME OD and '
            f'surface, e.g. study.sweep.scene_for(..., OD=..., '
            f'contact_surface=...).')

    # The schedule must cross edges where the SLOTS are, so it reads the same
    # contact surface the Problems are built with.
    crit = critical_shifts(scene, L_comp, s_centre,
                           problem_kw.get('contact_surface',
                                          DEFAULT_SURFACE),
                           problem_kw.get('OD')) if include_critical else ()
    out, state = [], None
    for i, shift in enumerate(schedule(total, step, include=crit)):
        problem = build_problem(model, scene, shift=shift, **problem_kw)
        result, state_out = solve(problem, state_in=state)

        # SEEDING IS A FALLBACK, NOT THE DEFAULT PATH, and deliberately so.
        # Every case that converges directly keeps the exact load path it
        # had before this was added, so the fix cannot quietly move a
        # number that was already right; only cases that returned nothing
        # at all change. Applied when there is no carried state -- the
        # first position, or every position in mode B -- because a later
        # position starts from a pipe that is already bent and is not the
        # hard one. Re-seeding mid-passage would also discard the carried
        # plastic state, which is mode A's whole point.
        seeded = False
        if seed and not result.converged and state is None:
            primed, _note = seed_state(model, scene,
                                       dict(problem_kw, shift=shift))
            if primed is not None:
                retry, retry_state = solve(problem, state_in=primed)
                if retry.converged:
                    result, state_out, seeded = retry, retry_state, True

        out.append(Position(index=i, shift=shift,
                            s_lead=s_centre + L_comp / 2.0 + shift,
                            s_trail=s_centre - L_comp / 2.0 + shift,
                            result=result, seeded=seeded))
        if verbose:
            print(f'  pos {i:2d}  shift {shift:7.3f} m  {result.status}')
        state = state_out if mode == 'A' else None
        if not result.converged:
            break
    return out

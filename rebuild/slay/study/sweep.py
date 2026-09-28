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
`differs_only_in_contact` holds between any two of them.

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
from slay.physics.problem import build_problem
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


def critical_shifts(scene, L_comp: float, s_centre: float) -> tuple:
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

    A station at `s_arc` is crossed by the leading edge when
    `s_centre + L/2 + shift == s_arc`, and by the trailing edge when
    `s_centre - L/2 + shift == s_arc`. Both matter: the edges are where the
    section changes, and a section change over a roller is the whole reason
    this component is interesting.

    Empty for plain pipe -- there are no edges, and nothing distinguishes one
    travel from another.
    """
    from slay.scene.rollers import StationRole
    if L_comp <= 0.0:
        return ()
    out = []
    for st in scene.stations:
        if st.role is not StationRole.CONTACT:
            continue
        for edge in (s_centre + L_comp / 2.0, s_centre - L_comp / 2.0):
            out.append(st.s_arc - edge)
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
              tail_clear=TAIL_CLEAR, **kw):
    """A Scene whose vessel-side buffer is sized for this exact passage."""
    from slay.scene.scene import build_scene
    return build_scene(R=R, spacing=spacing,
                       margin_vessel=buffer_length(L_comp, clear_before,
                                                   clear_after, tail_clear),
                       **kw)


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


def run(scene, ils=None, *, L_comp=0.0, step=None,
        clear_before=CLEAR_BEFORE, clear_after=CLEAR_AFTER,
        station=STATION, mode='A', s_centre=None,
        target_len=None, include_critical=True, verbose=False,
        **problem_kw) -> list:
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
    model = build_model(scene, ils, s_centre=s_centre,
                        extra_stations=_required_stations(scene),
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
    crit = critical_shifts(scene, L_comp, s_centre) if include_critical else ()
    out, state = [], None
    for i, shift in enumerate(schedule(total, step, include=crit)):
        problem = build_problem(model, scene, shift=shift, **problem_kw)
        result, state_out = solve(problem, state_in=state)
        out.append(Position(index=i, shift=shift,
                            s_lead=s_centre + L_comp / 2.0 + shift,
                            s_trail=s_centre - L_comp / 2.0 + shift,
                            result=result))
        if verbose:
            print(f'  pos {i:2d}  shift {shift:7.3f} m  {result.status}')
        state = state_out if mode == 'A' else None
        if not result.converged:
            break
    return out

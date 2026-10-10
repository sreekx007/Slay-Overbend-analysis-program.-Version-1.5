#!/usr/bin/env python3
"""slide.py -- sequential sliding contact through the rebuild. NOT a single
position solve.

    python3 tools/slide.py                          plain pipe, 4xOD passage
    python3 tools/slide.py --archetype ILS-TP       GD-TP across SR2
    python3 tools/slide.py --archetype ILS-TP --csv out.csv
    python3 tools/slide.py --pipes 0.1683,0.4064,0.508

WHAT THIS IS THE COUNTERPART OF. `slay_sliding_v0_5.py::run_passage_sliding`
in the reference toolchain. The physics is the same and the layering is not:
there, one 450-line function owned the mesh, the slots, the Newton loop, the
strain recovery and the position loop together. Here each of those is a layer
and this file only sequences them -- `study.sweep` owns the position loop
(G11), `physics.contact` owns the slots, `solve.passage` owns Newton, and
`report.passage` owns the measurement.

WHY SLIDING AND NOT ONE POSITION. Measured here, GD-TP at R = 85 m, 9 m
spacing, 120 MT, step 1xOD:

    shift 0.000   band 0.4597%      <- where a single-position solve looks
    shift 1.219   band 0.5482%      <- the envelope, leading edge at SR2
    shift 3.000   band 0.4968%

The start position is 19% LOW. The worst position is not at either end of the
passage, so it cannot be reached by picking a position in advance; it has to
be swept for. That is the whole argument.

TWO THINGS THE PASSAGE GETS RIGHT THAT A READER SHOULD KNOW ABOUT.

  THE SWEEP LENGTH IS DERIVED. `L_comp + clear_before + clear_after`, so the
  component starts clear of SR2 and finishes clear past it. It is not a
  chosen number of metres and it grows with the component.

  THE ENVELOPE IS NOT AT A STEP BOUNDARY. It is where a component edge
  crosses a roller, so those travels are added to every schedule by
  `study.sweep.critical_shifts` and the step only samples between them.

  THE VESSEL END IS FED. Material advances toward the stinger, so the vessel
  end runs dry; `study.sweep` adds `sweep + 1 m` of buffer pipe there, holds
  its tail in `uy` alone, and forces it linear elastic. Feedstock is not part
  of the answer and must never yield.

CONTACT SURFACE. `--contact-surface bottom` rides the pipe centreline at
`R + r_roller + OD/2` instead of driving it onto the R arc, which is what the
rollers physically do -- `R` is measured to the roller CENTRELINE. Off by
default: 'centreline' is what every validated number in `docs/RESULTS.md` was
computed with, so the flag moves nothing until it is asked for. See
`physics.contact` for why it enters through the radius and never as a
per-roller offset.

MODE A vs MODE B. A carries state between positions -- the real path a
component travels, and the mode that captures accumulated plastic strain. B
solves each position from virgin state, which is the worst position anywhere
whether or not a real lay would reach it. A is the default because a lay is
sequential; B is the check.

VERIFIED, and this is the measurement that says the sliding is right: run
LINEAR ELASTIC on plain pipe, where station-space strain must be invariant
under a shift because the rollers impose the same geometry at every position.
`--verify` runs it. Measured:

    step = 2xOD (one element)      spread 0.03 - 0.08%   <- exact
    step = 1xOD (half an element)  spread 0.83% at SR2, 4.40% at SR1

So the sliding itself is EXACT: advance the pipe by a whole element and the
same station reads the same strain to 0.08%.

TWO STEP EFFECTS PULL OPPOSITE WAYS, and the bigger one wins.

  SLOT INTERPOLATION, worth 0.8% at SR2 and 4.4% at SR1. The half-element
  column above ALTERNATES -- 0.1947, 0.1863, 0.1947, 0.1863, 0.1948 -- with no
  trend. A contact point interpolated to the middle of an element is softer
  than one on a node, because the slot coefficients are LINEAR in the two
  bracketing nodes (`physics.contact`: Hermite "raised, measured, not silently
  changed"). This is that measurement.

  UNDERSAMPLING THE ENVELOPE, worth 16%. The passage peak is where the
  component's leading edge crosses a roller, and a whole-element step steps
  straight over it: GD-TP envelope 0.4772% at 1.00 element, 0.5482% at 0.50,
  0.5678% at 0.25, the peak converging on lead = 9.016 m ~ SR2.

So refine the step -- undersampling costs twenty times what the jitter does.
Better still, `study.sweep.critical_shifts` puts every edge-crossing travel
into the schedule whatever the step is, which is on by default and is what
makes the envelope independent of the step rather than a function of it.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'rebuild'))
sys.path.insert(0, str(REPO))

import ils_builder                                          # noqa: E402

from slay.physics.contact import DEFAULT_SURFACE
from slay.data.materials import material                    # noqa: E402
from slay.report import junction as jr                      # noqa: E402
from slay.report import passage as rp                       # noqa: E402
from slay.study import sweep                                # noqa: E402

TON = 9806.65
FIXTURE = REPO / 'rebuild' / 'fixtures' / 'standard_ils_layouts.json'

R_DEF = 85.0
SPACING_DEF = 9.0
TENSION_MT_DEF = 120.0
OD_DEF = 0.4064
PLAIN_TRAVEL_OD = 4.0            # plain pipe has no component: sweep 4xOD


def archetype(arch_id: str):
    """An ILS assembly by archetype id, or None for `none`/plain pipe.

    PLAIN PIPE IS PLAIN PIPE HERE. `sweep.run(scene, None)` builds a bare
    pipeline and no contact surface is consulted at all. The reference module
    needed `allow_plain_pipe=True` for this because its earlier revisions
    faked a baseline with a zero-length shroud whose lift cancelled -- right
    by accident, as v0.5 says. There is nothing to opt into here: no
    component means no assembly.
    """
    if arch_id in (None, '', 'none', 'plain'):
        return None
    d = json.loads(FIXTURE.read_text())
    by_id = {a['id']: a for a in d['archetypes']}
    if arch_id not in by_id:
        raise SystemExit(f'unknown archetype {arch_id!r}; '
                         f'have {", ".join(sorted(by_id))}')
    return ils_builder.build_ils(by_id[arch_id]['definition'])


def _problem_at(scene, ils, pos, L_comp, **kw):
    """Re-pose the Problem a solved Position came from.

    The sweep keeps only the `Result`, and junction extraction needs the
    SECTIONS -- which body each element belongs to. Rebuilt with the same
    placement the sweep used, never guessed: `s_centre` and `shift` are read
    off the sweep, so the sections line up with the strains element for
    element.
    """
    from slay.model.assemble import build_model
    from slay.physics.problem import build_problem
    # Popped UNCONDITIONALLY: inside the ternary it short-circuits on plain
    # pipe and leaks a sweep argument into `build_problem`.
    cb = kw.pop('clear_before')
    # Also popped unconditionally, and for the same reason: it belongs to
    # `build_model`, not to `build_problem`, and the model here must be the
    # SAME one the sweep meshed -- a connector the sweep emitted and this
    # rebuild refused would renumber every element after it.
    emit = kw.pop('emit_unenforced_conn_types', frozenset())
    c = sweep.start_centre(scene, L_comp, cb, sweep.STATION) \
        if L_comp > 0 else 0.0
    # THE MESH AND THE BUFFER MERGE ARE BOTH `sweep`'s, not this file's --
    # see `passage_model` and `repose`. This was four copies of the same two
    # calls, which is why L109 took four sites to fix.
    #
    # `OD` is NOT taken separately here: it already travels in `kw` when the
    # case is off the default pipe. Passing it both ways is a TypeError that
    # only fires on a non-default diameter -- invisible on the baseline.
    return sweep.repose(
        sweep.passage_model(scene, ils, s_centre=c,
                            emit_unenforced_conn_types=emit),
        scene, shift=pos.shift, s_centre=c, ils=ils,
        problem_kw={k: kw.pop(k) for k in ('vertical_at', 'elastic_spans')
                    if k in kw},
        **kw)


def passage(arch_id='none', R=R_DEF, spacing=SPACING_DEF,
            tension_mt=TENSION_MT_DEF, step=None, OD=OD_DEF, t_wall=None,
            mode='A', elastic=False, clear_before=None, clear_after=None,
            contact_surface=None, ils=None, verbose=True,
            emit_unenforced_conn_types=frozenset(),
            n_sr=None, n_vr=None, spacing_vr=None):
    """Run one passage.

    Returns `(scene, L_comp, records, junction rows, problems, positions,
    completion)`.

    THE COMPLETION IS RETURNED, NOT LEFT TO THE CALLER TO RECOMPUTE, because
    this function does not use the default clearances and a caller cannot
    know that without reading it. Plain pipe here sweeps `4 x OD` with NO
    lead clearance; `sweep.completion`'s default is `L_comp + 1 + 1`. Four
    study tools called it with that default and a 20 in plain-pipe passage
    that had swept every metre of its travel came back as "102%" and was
    voided against the paper. One sizing, computed once, handed back.
    The raw `positions` are handed back as well as the measured `records`
    because element-level strain lives on `position.result` and a record
    carries only the peaks -- the region scheme (`slay.report.regions`)
    needs the elements, and re-solving to get them would be a second answer
    to what was already computed.

    `ils` overrides `arch_id` with an already-built assembly, which is how
    the dataset runner varies component length and wall: those are fields of
    an ILS definition, not of a fixture name.

    `n_sr`, `n_vr` and `spacing_vr` are PASS-THROUGHS to `build_scene`, added
    10 Oct 2026 for a study that varies the stinger pitch while holding the
    vessel deck. `None` on all three reproduces the layout every validated
    number was computed with, so they move nothing until asked. They are
    here rather than being reached by calling `study.sweep` directly, because
    this function is the entry point the published Sec. 1 tables use and a
    dataset that bypassed it would stop being comparable to them.
    """
    # None means "whatever the library rules" -- this tool does not keep
    # its own copy of the contact-surface ruling (6 Oct).
    if contact_surface is None:
        contact_surface = DEFAULT_SURFACE

    ils = archetype(arch_id) if ils is None else ils
    if ils is None:
        # No component, so no traverse to size the sweep from. Sweep a fixed
        # multiple of the diameter instead, and say so rather than letting
        # `sweep_length(0)` quietly return the clearances alone.
        L_comp = 0.0
        cb = 0.0 if clear_before is None else clear_before
        ca = PLAIN_TRAVEL_OD * OD if clear_after is None else clear_after
    else:
        L_comp = ils.extent[1] - ils.extent[0]
        cb = sweep.CLEAR_BEFORE if clear_before is None else clear_before
        ca = sweep.CLEAR_AFTER if clear_after is None else clear_after

    total = sweep.sweep_length(L_comp, cb, ca)
    step = OD if step is None else step
    # THE SCENE AND THE RUN MUST AGREE ON BOTH, or `sweep.run` refuses the
    # pair (L096): the stinger margin holds the terminal slot, and its size
    # depends on the contact surface AND the diameter. This call used to pass
    # neither, which was harmless only while the default was 'centreline' and
    # the margin was zero.
    # The pass-throughs are omitted when None rather than forwarded as None,
    # so a scene built without them is byte-for-byte the call that was made
    # before they existed.
    scene_kw = {k: v for k, v in (('n_sr', n_sr), ('n_vr', n_vr),
                                  ('spacing_vr', spacing_vr))
                if v is not None}
    sc = sweep.scene_for(R=R, spacing=spacing, L_comp=L_comp,
                         clear_before=cb, clear_after=ca,
                         contact_surface=contact_surface,
                         OD=None if OD == OD_DEF else OD, **scene_kw)

    kw = dict(tension=tension_mt * TON,
              material=None if elastic else material('j2'),
              contact_surface=contact_surface)
    if OD != OD_DEF:
        kw['OD'] = OD
    if t_wall is not None:
        kw['t_wall'] = t_wall

    if verbose:
        s_max, label = rp.zone(sc)
        print(f'{arch_id:10s} R={R:.0f} m  spacing={spacing:.0f} m  '
              f'T={tension_mt:.0f} MT  OD={OD:.4f} m  mode {mode}'
              f'{"  ELASTIC" if elastic else ""}'
              f'  surface={contact_surface}')
        print(f'{"":10s} L_comp={L_comp:.3f} m  sweep={total:.3f} m  '
              f'step={step:.4f} m  buffer={sweep.buffer_length(L_comp, cb, ca):.3f} m')
        print(f'{"":10s} zone: station s < {s_max:.1f} m ({label})')
        _warn_step(step, OD)

    t0 = time.time()
    positions = sweep.run(sc, ils, L_comp=L_comp, step=step,
                          clear_before=cb, clear_after=ca, mode=mode,
                          emit_unenforced_conn_types=emit_unenforced_conn_types,
                          **kw)
    records = rp.measure(positions, sc, L_comp=L_comp)
    junc, probs = [], []
    for pos in positions:
        if not pos.converged:
            junc.append({})
            probs.append(None)
            continue
        pr = _problem_at(sc, ils, pos, L_comp, clear_before=cb,
                         emit_unenforced_conn_types=emit_unenforced_conn_types,
                         **kw)
        junc.append(jr.row(pos, pr, OD))
        # The Problems are returned too: the contact LIFT lives on their
        # targets, and re-posing them downstream would be a second answer to
        # where the component was.
        probs.append(pr)
    if verbose:
        _table(records, L_comp, time.time() - t0)
        _junction_table(records, junc)
    done = sweep.completion(positions, L_comp, total=total)
    return sc, L_comp, records, junc, probs, positions, done


def _warn_step(step, OD):
    """Say how the step sits against one element, and what that costs.

    One element is 2xOD (the ruled mesh density). A step that is not a whole
    number of them makes successive positions alternate between a node-
    aligned contact point and an interpolated one, which is worth up to 4.4%
    at SR1 -- see the module docstring. Reported, not corrected: a finer step
    resolves the component's position better and that may be the trade the
    caller wants.
    """
    elem = 2.0 * OD
    n = step / elem
    note = ('  <- a whole element: coarse enough to step over the envelope, '
            'which sits at an edge crossing') if abs(n - round(n)) < 1e-6 \
        else '  <- sub-element: up to 4.4% slot-interpolation jitter at SR1'
    print(f'{"":10s} step = {n:.3f} element ({elem:.4f} m at 2xOD){note}')
    print(f'{"":10s} edge-crossing travels are solved regardless of the step')


def _table(records, L_comp, secs):
    print(f'  {"pos":>3} {"shift":>8} {"status":>10} {"act":>7} '
          f'{"peak":>9} {"at sta":>8} {"at mat":>8}'
          + (f' {"lead":>8} {"trail":>8}' if L_comp > 0 else ''))
    for r in records:
        pk = f'{100 * r.peak_strain:8.4f}%' if r.converged else f'{"--":>9}'
        row = (f'  {r.index:3d} {r.shift:8.3f} {r.status:>10} '
               f'{r.n_active:3d}/{r.n_slots:<3d} {pk} '
               f'{r.peak_s_station:8.2f} {r.peak_s_material:8.2f}')
        if L_comp > 0:
            row += f' {r.s_lead:8.3f} {r.s_trail:8.3f}'
        print(row)
    try:
        env = rp.envelope(records)
    except ValueError as exc:
        print(f'  NO ENVELOPE: {exc}')
        return
    start = records[0]
    gain = (100.0 * (env.peak_strain / start.peak_strain - 1.0)
            if start.converged and start.peak_strain > 0 else float('nan'))
    print(f'  envelope {100 * env.peak_strain:.4f}% at position {env.index} '
          f'(shift {env.shift:.3f} m, station {env.peak_s_station:.2f} m)')
    print(f'  a single solve at the start position would read '
          f'{100 * start.peak_strain:.4f}% -- {gain:+.1f}% off the envelope')
    print(f'  {len(records)} positions in {secs:.1f} s')


def _junction_table(records, junc):
    """The junction numbers at the envelope position."""
    try:
        env = rp.envelope(records)
    except ValueError:
        return
    d = junc[env.index]
    if not d or not d.get('n_junctions'):
        return
    print(f'  junctions at the envelope (position {env.index}): '
          f'I_comp/I_pipe = {d["stiffness_ratio"]:.4f}, '
          f'body peak {100 * d["body_peak_strain"]:.4f}%')
    keys = sorted(k[:-7] for k in d if k.endswith('_strain')
                  and k != 'body_peak_strain')
    print(f'    {"location":22s}{"strain":>10}{"moment kNm":>13}{"":>3}')
    for k in keys:
        eps, M = d[k + '_strain'], d[k + '_moment']
        flag = ' clamped' if d.get(k + '_clamped') else ''
        print(f'    {k:22s}{100 * eps:9.4f}%{M / 1e3:13.1f}{flag}')


def verify(R=R_DEF, spacing=SPACING_DEF, tension_mt=TENSION_MT_DEF):
    """Plain pipe, LINEAR ELASTIC: station-space strain must not vary.

    The rollers impose the same geometry at every position, so a plain
    elastic pipe must give the same strain at the same STATION however far it
    has slid. What is left is discretisation: the interpolated contact point
    moves within an element as the shift advances. A trend here would mean
    the sliding is wrong; jitter without a trend is the mesh.

    The tip stations are reported but not judged -- D6 makes the terminal
    station a contact slot and the last three rollers are outside the zone.
    """
    sc, _L, _r, _j, _p, _ps = passage('none', R=R, spacing=spacing,
                                 tension_mt=tension_mt, elastic=True,
                                 verbose=False)
    positions = sweep.run(sc, None, L_comp=0.0, clear_before=0.0,
                          clear_after=PLAIN_TRAVEL_OD * OD_DEF,
                          step=OD_DEF, tension=tension_mt * TON, material=None)
    records = rp.measure(positions, sc)
    s_max, _ = rp.zone(sc)
    print('plain pipe, linear elastic -- strain by STATION, one column per shift')
    print(f'  {"station":>8} ' + ' '.join(f'{r.shift:8.3f}' for r in records)
          + f' {"spread":>8}  in zone')
    worst = 0.0
    for st in sorted((s for s in sc.stations if s.name.startswith('SR')),
                     key=lambda t: t.s_arc):
        vals = [r.stations.get(st.name) for r in records]
        if any(v is None for v in vals):
            continue
        spread = (max(vals) - min(vals)) / max(vals) * 100.0
        inzone = st.s_arc < s_max
        if inzone:
            worst = max(worst, spread)
        print(f'  {st.name:>8} ' + ' '.join(f'{100 * v:7.4f}%' for v in vals)
              + f' {spread:7.2f}%  {"yes" if inzone else "no"}')
    print(f'  worst in-zone spread {worst:.2f}% over '
          f'{records[-1].shift:.3f} m of travel')
    return worst


def main() -> int:
    a = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        if flag in a:
            return cast(a[a.index(flag) + 1])
        return default

    if '--verify' in a:
        verify(R=opt('--R', R_DEF, float),
               spacing=opt('--spacing', SPACING_DEF, float),
               tension_mt=opt('--tension', TENSION_MT_DEF, float))
        return 0

    kw = dict(arch_id=opt('--archetype', 'none'),
              R=opt('--R', R_DEF, float),
              spacing=opt('--spacing', SPACING_DEF, float),
              tension_mt=opt('--tension', TENSION_MT_DEF, float),
              step=opt('--step', None, float),
              mode=opt('--mode', 'A'),
              contact_surface=opt('--contact-surface', DEFAULT_SURFACE),
              elastic='--elastic' in a)
    csv_out = opt('--csv')

    pipes = opt('--pipes')
    ods = [float(x) for x in pipes.split(',')] if pipes else [opt('--OD', OD_DEF, float)]

    allrec = []
    for od in ods:
        if len(ods) > 1:
            print()
        sc, L, records, junc, _probs, _pos = passage(OD=od, **kw)
        allrec += [(od, L, r, junc[i]) for i, r in enumerate(records)]
    if csv_out:
        rows = [r for (_od, _L, r, _j) in allrec]
        rp.to_csv(rows, csv_out, per_row=[j for (_od, _L, _r, j) in allrec],
                  extra=dict(
            archetype=kw['arch_id'], R=kw['R'], spacing=kw['spacing'],
            tension_mt=kw['tension_mt'], mode=kw['mode'],
            contact_surface=kw['contact_surface'],
            OD=allrec[0][0], L_comp=allrec[0][1]))
        print(f'\nwrote {csv_out} ({len(rows)} rows)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

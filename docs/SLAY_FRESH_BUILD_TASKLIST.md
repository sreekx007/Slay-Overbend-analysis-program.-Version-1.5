# S-Lay Overbend — Task List (Fresh Build)

**Supersedes:** `SLAY_TASK_LIST.md` (12 Aug 2026, patch-based). That list scoped work
against the old files directly — remove `k_spring` from `_solve_state`, repoint
`run_landing_check`'s call site, and so on. Once the decision changed from patching to a
fresh build, that task shape stopped applying: there's no `_solve_state` to remove
`k_spring` from, because `slay_solver.py` is written new and never has it. **The
decisions in the old list are still correct and now inform the build below — the task
format doesn't carry over.**

**Companion to:** `SLAY_FRESH_BUILD_SPEC.md` (script list + aims, decisions on
`roller_offsets`/`vessel_offsets`, RO/`one_sided`, `n_vr`).

---

## Per-module process (agreed 12 Aug 2026)

Every module below follows the same sequence. No step is skipped, and no code is written
before the step above it is agreed:

1. **Algorithm in plain spoken language** — written as prose explaining what the module
   does and why, not as a codified spec. Delivered as a document for review.
2. **Review** — comments returned on the document itself.
3. **Flowchart (mermaid)** — produced once the algorithm is agreed. Skipped only where a
   module genuinely has no control flow to diagram, and that exemption is stated
   explicitly rather than assumed.
4. **Agreement** — algorithm and diagram both signed off.
5. **Code** — written only now.
6. **Test with sample input and output** — each module exercised on its own, with the
   actual numbers recorded.
7. **Save the record** — one living document per module, carrying the spec, the review
   status, and an action log of every revision. Later changes append to that same
   document rather than spawning a new one.

`config.py` has completed steps 1–4 (three review rounds, `config_py_spec_FINAL.docx`,
marked AGREED). It is ready for step 5.

---

## Build order

Bottom-up, matching the dependency graph — nothing gets written before what it depends on
exists and is verified.

### Stage 1 — Foundation

**1.1 `config.py` + `slay_config.yaml`** — spec AGREED, ready to code
- [x] Spec written, reviewed (3 rounds), agreed — `config_py_spec_FINAL.docx`
- [x] Flowchart agreed — `slay_config_loader_flow.mermaid`
- [x] Data file drafted — `slay_config.yaml`
- [ ] Write `config.py` as a loader: locate the YAML beside itself, parse, validate every
      section present, unpack, resolve the one-sided-roller rule into concrete names
- [ ] Test: valid file loads and exposes every expected constant; missing file, malformed
      YAML, and missing section each fail loudly with their own distinct message
- [ ] Test: one-sided-roller rule resolves correctly at the default `n_sr=6`, and still
      correctly at a changed `n_sr` (the reason it's a rule and not a fixed list)
- [ ] Log results in the module document

**1.2 `slay_geometry.py`**
- [ ] Algorithm in plain language → review → flowchart → agree (steps 1–4)
- [ ] Code: reference geometry, component-boundary snapping, `MeshTopology`, EA-ST frame
      construction, per-roller offset lookup (roller-OD-aware, not a global constant)
- [ ] Test: plain-pipe and EA-ST cases both produce expected node/element counts, and
      `MeshTopology` correctly separates the chains
- [ ] Log results

### Stage 2 — Contact and solve
- [ ] **2.1** `slay_contact.py` — sliding slot construction, envelope ownership (max, not
      sum), per-roller one-sided/bilateral configuration (VR1/VR2 one-sided, rest
      bilateral), EA-ST F connectors
- [ ] **2.2** `slay_solver.py` — Newton + contact loop, `reg_mult` retained, no `k_spring`
- [ ] **2.3** Verify against a case with a known answer: F1 EA-ST result should equal
      plain pipe bit-for-bit (a single shared connector node adds no bending continuity —
      this was confirmed in the old code, the fresh solver should reproduce it exactly,
      not approximately)

### Stage 3 — Orchestration
- [ ] **3.1** `slay_passage.py` — Mode A, J2 only, state chained
- [ ] **3.2** `slay_check.py` — Mode B, J2 and RO both available, no chaining
- [ ] **3.3** `slay_landing.py` — thin wrapper over `slay_check.py`
- [ ] **3.4** Verify Mode A against the corrected baseline table (SR5: 1.4028%, not the
      superseded 1.334% — see architecture plan §6)
- [ ] **3.5** Verify Mode B against its own validated reference cases

### Stage 4 — Postprocess and IO
- [ ] **4.1** `slay_postprocess.py` — `MeshTopology`-aware from first write
- [ ] **4.2** `slay_plot.py` — same
- [ ] **4.3** `slay_io.py` — checkpointing, provenance-tagged save/load
- [ ] **4.4** Verify: regenerate the plots for a known case, visual check plus peak-value
      check (not visual alone — a plot can look right and report the wrong number)

### Stage 5 — Specification and entry point
- [ ] **5.1** Update `slay_spec.py` (`slay_case.py`, already built) for the new module
      names; drop any `k_spring`/node-snapping knobs it has no reason to expose
- [ ] **5.2** `slay_cli.py`
- [ ] **5.3** Verify: every case in the baseline table, run via CLI, matches

---

## Decisions carried in from the `config.py` review

These were settled during that module's three review rounds and now apply to the whole
build, not just `config.py`:

- **Defaults live in YAML, not Python.** `slay_config.yaml` is the single source of truth
  for every system-wide default; `config.py` is a loader that reads, validates, and
  re-exposes them. Adds a runtime YAML-parser dependency the pure-constants design
  wouldn't have had.
- **Editing defaults vs. overriding per run are different things.** `slay_config.yaml`
  changes the baseline every run gets and should change rarely and deliberately. Trying a
  different parameter for one study goes through `slay_spec.py`'s case-level override
  instead, which tags the value as user-supplied and leaves the shared file untouched.
- **One-sided rollers corrected.** ALL stinger rollers are one-sided (they can only push
  the pipe along the arc, never hold it against it), plus VR1 and VR2. Everything further
  toward the vessel is bilateral. Because `n_sr` is configurable, this is stored as a rule
  and resolved into concrete names at load time — not a fixed list that would go stale.
- **`n_vr` default is 3**, not the 10 the old sliding module had drifted to.
- **`alpha_DNV` is 1.300.** The engine file states both 2.278 and 1.300 in different
  docstrings for the same formula; direct calculation confirms 1.300. The engine file is
  external and was not modified, so that discrepancy still exists there.

## What's still open going into Stage 1

- Nothing blocking `config.py` — it is ready to code.
- The per-roller offset/OD lookup structure (fresh-build spec item 1) still needs its
  shape confirmed, but that is now a `slay_geometry.py` question and gets settled during
  **that** module's step 1–4 review, not before `config.py` is written. `config.py` only
  holds the fallback radius; the lookup itself lives in geometry.

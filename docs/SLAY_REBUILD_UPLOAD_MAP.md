# Upload Map — S-Lay Rebuild Package

**Packaged:** 12 Aug 2026
**Contents:** planning documents, the first agreed module spec, three diagrams, and the
proposed defaults data file. **No rebuilt source code yet** — the fresh build is at the
specification stage for its first module.

Unzip and place the `slay-rebuild/` contents into the repository. The folder layout below
is the suggested structure; adjust paths to fit the existing repo if it already has
conventions, but keep the four groupings distinct — the `reference/` vs. everything-else
split in particular is load-bearing (see the warning at the bottom).

---

## File-by-file

### `docs/` — planning, read in this order

| File | What it is | State |
|---|---|---|
| `SLAY_FRESH_BUILD_SPEC.md` | The script list for the fresh build: 11 modules, what each one is for, and the decisions behind them (why sliding contact is kept and node-snapping isn't, where defaults live, roller behaviour). **Start here.** | Current |
| `SLAY_FRESH_BUILD_TASKLIST.md` | The build order and per-module process (plain-language algorithm → review → diagram → agree → code → test → log). Tracks what's done and what's next. | Current |
| `SLAY_ARCHITECTURE_AND_RESTRUCTURING_PLAN.md` | The layered architecture, the `MeshTopology` design, and the regression baseline table. Written before the decision to rebuild rather than restructure, so parts of its *phasing* are superseded by the two files above — but its **architecture and baseline table remain current and are referenced by them**. | Partly superseded, still needed |

### `docs/modules/` — one living document per module

| File | What it is | State |
|---|---|---|
| `config_py_spec_FINAL.docx` | Full specification for `config.py`: purpose, the YAML decision, both material reference tables (J2 31-point curve, Ramberg-Osgood parameters), the loader algorithm in plain language, review status, and an action log of all three review rounds. Contains tracked review comments. | **AGREED — ready to code** |

As each further module is specified, its document joins this folder. Revisions append to
the existing document rather than creating a new file.

### `docs/diagrams/` — mermaid, renders natively on GitHub

| File | What it shows |
|---|---|
| `slay_module_dependency.mermaid` | How the 11 modules depend on each other, by layer |
| `slay_mode_a_vs_b_flow.mermaid` | Mode A (chained passage, state carried) vs Mode B (independent position check, no history) side by side — the distinction that was blurred in the old code |
| `slay_config_loader_flow.mermaid` | `config.py`'s load-validate-resolve-expose sequence, including its three distinct failure paths |

### `config/` — actual data, not documentation

| File | What it is | State |
|---|---|---|
| `slay_config.yaml` | Every system-wide default: reference pipeline, stinger/roller geometry, mesh density, both material definitions, section integration, solver constants. **This is a real input file the program will read at runtime**, not a description of one. | Agreed, awaiting the loader that reads it |

### `reference/` — existing validated code, NOT part of the fresh build

| File | What it is | State |
|---|---|---|
| `slay_case.py` | Case validation and provenance tracking. Written earlier and already working — it becomes `slay_spec.py` in the new structure, with module-name updates. Included because the fresh build depends on it and it shouldn't be rewritten from scratch. | Working, needs renaming/rewiring only |

---

## What is deliberately NOT in this package

- **`nlfea_v4.py`** — the FE engine. External and unmodified throughout this project; it
  should already be in the repo and is not touched by the rebuild.
- **`slay_overbend_v1_50.py`, `slay_sliding_v0_5.py`** — the old monolithic files. The
  rebuild replaces these. If they're in the repo, leave them where they are for now (as
  reference for behaviour being reproduced) but they are not part of the new structure.
  The plan calls for archiving rather than deleting them once the rebuild is validated.
- **Any rebuilt module source.** None exists yet — `config.py` is specified and agreed but
  not written.

---

## Important: don't mix `reference/` into the new build

`slay_case.py` is the only working code in this package, and it predates the rebuild. It's
included because the new structure genuinely needs it, not because it's an example of the
new structure. Everything else here is specification. Keeping that distinction visible in
the folder layout is the point of the separate `reference/` directory — if it gets flattened
in with the rest, the next person (or the next session) can't tell agreed-and-built from
agreed-but-unwritten.

---

## Suggested first commit message

```
Add fresh-build planning docs, config.py spec (agreed), and defaults file

- 11-module architecture with layer boundaries and dependency graph
- Mode A / Mode B distinction made explicit (was implicit and blurred)
- config.py specified and agreed across 3 review rounds; defaults move
  to slay_config.yaml with config.py as a validating loader
- Corrections captured: n_vr default 3 (not 10), all SR rollers
  one-sided (not just VR1/VR2), alpha_DNV 1.300 (engine file states
  two conflicting values)
- No rebuilt source yet; config.py is next to be written
```

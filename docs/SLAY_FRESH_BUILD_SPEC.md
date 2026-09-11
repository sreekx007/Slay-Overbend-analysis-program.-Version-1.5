# S-Lay Overbend — Fresh Build: Script List and Aims

**Date:** 12 Aug 2026
**Status:** Planning — script list and aims first, code after this is agreed

## Why fresh, not patched

This session found three separate sweep mechanisms sharing one solve function
(`_solve_state`): `run_passage_v2` (chained, node-snapped), `run_passage()` v1.39 (an
older independent sweep with its own defaults), and `run_slay()` itself recursively
staging an "elastic_first" two-phase solve. None of this is described in the paper — the
published methodology is two modes only (chained/sliding, independent check), one
material (J2) for passage work. Patching forward risks carrying three generations of
exploratory branching into a codebase meant to be clean. Building fresh against what's
actually validated is the more reliable route.

**Ground rule for this build: scope is what the paper describes and the tech reference
validates. A feature from the old code needs a specific reason to be rebuilt, not a
default assumption that everything gets carried forward.**

---

## Decisions from review (12 Aug 2026)

| # | Item | Resolution |
|---|---|---|
| 1 | `roller_offsets`/`vessel_offsets` | Same concept (Abaqus V convention, `CL_lift = V − OD/2`), split across two dicts because the old geometry code represented the flat deck (`vessel_offsets`: VR1–VR3, SR1) and the stinger arc (`roller_offsets`: SR2+) differently. Real requirement, not exploratory: **the offset at a given roller must be decided by which component is currently contacting it** — this is exactly what `envelope_at(x, ...)` already does by evaluating ownership as a function of x. **New requirement surfaced in review: roller OD is not necessarily uniform.** `slay_geometry.py` needs a per-roller offset function, not a single global `r_roller` constant — open exactly how rollers of different diameter get specified (a dict keyed by roller name, most likely, matching the old `roller_offsets` dict's own shape). |
| 2 | RO material / `one_sided` contact | **Both validated, both required for Mode B.** Correcting the assumption in the previous version of this document: RO is not exploratory, it's the right choice specifically *because* Mode B has no history to lose — J2's path-memory only matters where state actually carries forward (Mode A). `one_sided` is **not** a material choice or a sweep-level flag — it's a **per-roller physical property**: J2 was run with both one-sided and bilateral contact. **Corrected 12 Aug 2026 during the `config.py` review:** ALL stinger rollers are one-sided — a roller riding the arc can only push the pipe along it, never hold it down against it — plus VR1 and VR2. Only vessel rollers further inboard (VR3 onward) are bilateral. An earlier draft had this backwards, listing only VR1/VR2 as one-sided. Since `n_sr` is configurable, this is stored as a **rule**, resolved into concrete roller names at load time, rather than a fixed list that would silently go stale. `slay_check.py` needs both materials available, and `slay_contact.py` needs per-roller one-sided/bilateral configuration as a first-class input, not a global toggle. |
| 3 | `n_vr` default | **3 is correct** (matches node-based; sliding's 10 was the wrong one). Increase only when the required sweep length exceeds one roller spacing (8m) — `config.py` carries `n_vr=3`. |
| 3a | Where defaults live | **Added 12 Aug 2026 from the `config.py` review:** defaults live in `slay_config.yaml`, not as Python literals. `config.py` becomes a loader — locate the file beside itself, parse, validate every section is present, unpack, resolve the one-sided-roller rule, expose under the same constant names every module already imports. Fails loudly on a missing file, bad YAML, or a missing section; never falls back to hidden built-in values. Adds a runtime YAML-parser dependency. Editing that file changes the baseline for every run; per-study parameter changes go through `slay_spec.py`'s case override instead. |
| 4 | Old `run_passage()` (v1.39) | **Out of scope, ignored per direction.** Not rebuilt, not investigated further. |

These feed directly into the script aims below — `slay_geometry.py` and `slay_contact.py`'s
descriptions are updated accordingly.


---

## Script list

### Layer 1 — unchanged
| Script | Aim |
|---|---|
| `nlfea_v4.py` | FE engine — element formulation, assembly, J2 plasticity. External, read-only, not rebuilt. |

### Layer 2 — solver core
| Script | Aim |
|---|---|
| `slay_geometry.py` | Build the stinger/roller reference geometry and the actual (component-boundary-snapped) mesh. Build `MeshTopology` — which chain (pipe vs. EA-ST frame) each node/element belongs to — as a first-class output here, not retrofitted later. Owns `shroud_offset_at` (CL_lift profile) and EA-ST frame construction. **Owns per-roller contact offset**, resolved by which component currently owns that station (via `envelope_at`) — not a single global `r_roller`, since roller OD is not assumed uniform; a per-roller lookup (name-keyed, matching the old `roller_offsets`/`vessel_offsets` shape) replaces the flat constant. No solver, no physics beyond geometry. |
| `slay_contact.py` | Build contact slots via interpolated (sliding) coefficients — the only contact-positioning method in this build, node-snapped correspondence is not rebuilt. Resolve the contact envelope by ownership (lowest surface wins) across however many bodies are present. **Per-roller one-sided/bilateral is a physical property of that roller, not a sweep-level flag** — VR1/VR2 one-sided, all others bilateral, both under J2. Build connector slots for EA-ST (F now; P/S/D are documented, not implemented — raise clearly if requested, don't approximate). |
| `slay_solver.py` | One Newton + contact solve loop, built from the proven `_solve_state_sliding` logic (not `_solve_state` — no reason to fresh-build the path being retired). `reg_mult` retained (validated stabiliser). No `k_spring` — tested and rejected, never rebuilt. |

### Layer 3 — orchestration
| Script | Aim |
|---|---|
| `slay_passage.py` | **Mode A** — continuous chained passage. Plastic state carried step to step; component's actual path through the stinger. J2 only (this is the paper's own stated reason chaining exists at all). One sweep mechanism, not the three the old code had. |
| `slay_check.py` | **Mode B** — independent position check. Each position solved from an unloaded state; no history; exhaustive search across the sweep range. Built directly on `slay_solver.py` at a single position — not a degenerate call into `slay_passage.py`, which is what caused this session's confusion (Mode B silently depending on Mode A's sweep machinery for convenience). **Supports both J2 and RO material** — RO is the right choice here specifically because there's no history to lose, not an exploratory leftover. |
| `slay_landing.py` | Thin, case-specific wrapper over `slay_check.py` for the landing-check use case. No solver logic of its own — position bookkeeping and result packaging only, same discipline the old file already stated for itself, now actually true of its dependency. |

### Sidecars
| Script | Aim |
|---|---|
| `slay_postprocess.py` | Strain/moment/curvature extraction. Takes `MeshTopology` from day one — every function here is chain-aware by construction, not patched to become so after the fact. |
| `slay_plot.py` | All plotting. Same `MeshTopology`-first discipline — this is what would have made `plot_east_step` a thin call instead of a hardcoded rewrite. |
| `slay_io.py` | Checkpointing, save/load, provenance-tagged results. |
| `config.py` | **Loader**, not a constants file (see decision 3a). Reads `slay_config.yaml`, validates it's complete, resolves the one-sided-roller rule into concrete names using `n_sr`, and exposes everything under the names every module already imports. One value per constant, not one per module (closes the `n_vr` 3-vs-10 split). Spec AGREED — `config_py_spec_FINAL.docx`. |

### Layer 4 / 5
| Script | Aim |
|---|---|
| `slay_spec.py` | Case validation and provenance (`slay_case.py`, already built this session — update for the new module names, and to drop the now-nonexistent `k_spring`/node-snapping knobs it currently has no reason to expose). |
| `slay_cli.py` | Entry point. `--case`, `--mode {A,B}`, `--batch`. |

---

## Flowcharts

Two Mermaid diagrams follow as separate files: the module dependency graph, and the Mode
A vs. Mode B execution flow side by side (the fork that matters most — this is exactly the
distinction that got blurred when Mode B was quietly built on Mode A's machinery).

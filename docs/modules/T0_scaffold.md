# T0 — Scaffold · module record

**Status:** COMPLETE · 12 Sep 2026
**Card:** `docs/SLAY_BUILD_INSTRUCTION.md` §6 T0

---

## Process exemption (§3)

Steps 1–4 of the per-module process (plain-language algorithm → review →
flowchart → agreement) are **exempted** for this card, and the exemption is
stated here rather than assumed, as §3 requires.

Reason: T0 builds no module. It creates directories, a registry, a static
linter and a test harness — there is no algorithm to describe in prose and
no control flow to diagram. The first card to which the full process applies
is T2 (Scene); T1 is a two-branch accessor and will carry its own judgement.

---

## What was built

| Path | Purpose |
|---|---|
| `rebuild/slay/` | Package root; nine layer subpackages with plain names (D1) |
| `rebuild/slay/_layers.py` | Layer registry — ordered `LAYERS`, plus `EXTERNAL_LAYER` for the flat mirrored modules and the frozen kernel |
| `rebuild/slay/*/__init__.py` | Each carries its layer's contract: what it owns, its frame, and whether workflow is permitted |
| `rebuild/slay/model/mesh.py` | Relocated from `rebuild/slay_mesh.py` via `git mv` (history preserved) |
| `rebuild/conftest.py` | Puts `rebuild/` and the repo root on `sys.path` for the test run |
| `rebuild/tests/test_smoke.py` | 10 tests |
| `tools/check_layers.py` | The layer linter |
| `tools/run_checks.sh` | The gate: linter, then tests |

### Why the mirrored files did not move

`config.py`, `component_spec.py`, `ils_builder.py` and `slay_config.yaml`
stay flat in `rebuild/`. They are a snapshot of Slay-ILS-Designer-V1.0's
`plotters/` directory and are kept honest by re-diffing against it; moving
them into the package tree would break that comparison, which is the only
mechanism preventing silent drift (G7). They are declared in
`EXTERNAL_LAYER` instead, so the linter still places them.

`slay_mesh.py` is ours, so it moved. It is now `slay.model.mesh`.

---

## Verification — recorded numbers

```
$ ./tools/run_checks.sh
== layer linter ==
check_layers: OK -- 10 modules, no violations

== tests ==
..........                                                     [100%]
10 passed in 0.18s
```

### The linter demonstrably fails (the card's DONE WHEN)

An inner layer importing an outer one:

```
$ echo 'from slay.solve import solver' > rebuild/slay/model/_probe.py
$ python3 tools/check_layers.py; echo "exit=$?"
LAYER VIOLATIONS (1):

  rebuild/slay/model/_probe.py:1: 'model' imports 'slay.solve' from 'solve'
      -- 'solve' is an OUTER layer
exit=1

$ rm rebuild/slay/model/_probe.py && python3 tools/check_layers.py; echo "exit=$?"
check_layers: OK -- 10 modules, no violations
exit=0
```

This is also locked as a permanent test (`test_layer_linter_catches_violation`),
which writes the probe, asserts exit 1, and removes it. Without that, the
linter could silently degrade to a no-op and every later card would still
report green — the same shape as the `phase1_peak=0.0` failure G8 exists for.

### Mesher regression after relocation

All numbers unchanged from before the move:

| Case | Result |
|---|---|
| GD-TT pipeline, 2×OD target | 16 elements, max adjacent ratio 2.0, 7/7 mandatory stations snapped, 0 warnings |
| GD-ST frame (closed loop) | `closed=True`, elements == nodes (seam is a real adjacency), 0 warnings |
| GD-VLV pipeline run | 4 elements (trans/body/body/trans), 0 warnings |
| GD-SB frame slopes | 1.8175 m per side measured along the path |

The GD-SB assertion is the G2 lock: the same sides measure 0.8128 m if
projected onto x — 44.7% of true length. The test asserts both that the
correct value appears twice **and** that the projected value appears
nowhere, because the projected number is plausible enough to survive review.

### §8 audit

| # | Criterion | Result |
|---|---|---|
| 1 | §3 steps logged | This document; steps 1–4 exempted above |
| 2 | `run_checks.sh` exits 0 | ✅ |
| 3 | Recorded numbers, freshly run | ✅ above |
| 4 | Workflow audit (L1–L5) | N/A — no logic built |
| 5 | No mirrored/frozen file edited | ✅ `git status` on those five paths: empty |
| 6 | Constants trace to `config.py` | ✅ tests read `config`, restate nothing |

---

## Action log

| Date | Action |
|---|---|
| 12 Sep 2026 | D1 resolved by user: plain layer names, membership in a registry. Card executed and closed. |

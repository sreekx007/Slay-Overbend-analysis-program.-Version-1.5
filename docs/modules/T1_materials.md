# T1 — `slay.data.materials` · module record

**Status:** COMPLETE · 12 Sep 2026
**Card:** `docs/SLAY_BUILD_INSTRUCTION.md` §6 T1
**Layer:** `data` (L1) · **Workflow:** none

---

## Process note (§3)

Steps 1–4 (plain-language algorithm → review → flowchart → agreement) are
**condensed** rather than exempted, and the judgement is recorded here.

The algorithm is a two-branch lookup over values that already exist and are
already validated: given a name, assemble the matching constants into a
typed object; refuse anything else. There is no control flow to diagram and
no physics to agree. What *did* need judgement is the shape of the returned
object, and that is argued in the module docstring and summarised below.

If you disagree with the returned shape, that is the reviewable decision —
not the lookup.

---

## The design question: what shape does a material have here?

`config.py` exposes material numbers as loose constants. Any consumer
wanting a material reassembles them, and each reassembly can pair the wrong
values. The obvious fix — return `nlfea_v4`'s own `IncrementalIsotropic` /
`RambergOsgood` objects — is **not available and should not be**:

- `nlfea_v4` is declared as the `solve` layer, so `data` cannot import it.
  The linter blocks it.
- That restriction is the correct way round. Material data is a fact about
  steel, not about a solver. Binding L1 to the kernel would mean swapping
  the solver later required editing the data layer.

So this module defines its own frozen dataclasses, and the `solve` layer
converts them at the point of use. The field names are chosen so that
conversion is mechanical.

---

## Two transposition hazards this module closes

Both produce plausible numbers rather than errors, which is why they get
dedicated tests rather than a comment.

### 1. Table column order

`slay_config.yaml` stores the J2 curve as `[yield stress, plastic strain]`.
`nlfea_v4.IncrementalIsotropic` takes `eps_p_table` **before**
`sigma_y_table` — plastic strain first. Passing the raw table through in
either direction puts 360e6 where a strain belongs. It does not raise; it
solves something else.

Closed by keeping the columns as separate named fields (`yield_stress`,
`plastic_strain`) that are never adjacent positional arguments, plus a
constructor check that rejects a transposed pair.

### 2. Which alpha convention

Ramberg-Osgood has two conventions in circulation:

| Convention | Formula | Value at 450 MPa / 207 GPa |
|---|---|---|
| DNV | `(0.005 − sig_ys/E)·E/sig_ys` | **1.300** |
| API 1104 | `0.005·E/sig_ys` | 2.300 |
| `nlfea_v4` docstring claims | — | 2.278 |

The kernel's stated 2.278 matches **neither**, and direct evaluation of the
formula printed on the line above it gives 1.300 exactly. `config.py`
carries 1.300; this module passes it through unchanged and names the field
`alpha_dnv` so a caller cannot supply the API value without noticing.

**Verified once, independently, during this card:**

```
alpha from kernel formula: 1.300000   (0.005 - sig/E)*E/sig
alpha_DNV in config      : 1.3
agree to 1e-4            : True
the rejected 2.278       : off by 0.9780
```

This was verification, not derivation. The module still reads the value
from `config` and computes nothing (G1 for this card).

---

## Verification — recorded output

```
material('j2')  -> J2Material(kind='j2')
  E              = 2.1e+11 Pa
  sigma_y0       = 3.6e+08 Pa
  n_points       = 31
  first pair     = (3.6e+08 Pa, 0.0)
  last  pair     = (5.3e+08 Pa, 0.052585)

material('ro')  -> RambergOsgoodMaterial(kind='ro')
  E              = 2.07e+11 Pa
  sig_ys         = 4.5e+08 Pa
  n_ro           = 20.59
  alpha_dnv      = 1.3
  eps_y          = 0.002174

material('j3')  -> ValueError: unknown material 'j3'. Known materials: j2, ro. ...
```

### Card VERIFY clause

| Requirement | Result |
|---|---|
| `material('j2')` returns a 31-point table, first point `(360.0e6, 0.0)` | ✅ |
| `material('ro')` returns `alpha_DNV == 1.300` | ✅ |

### Check gate

```
$ ./tools/run_checks.sh
== layer linter ==
check_layers: OK -- 11 modules, no violations

== tests ==
.......................                                        [100%]
23 passed in 0.19s
```

13 new tests. Beyond the two VERIFY assertions they cover: column
orientation by magnitude (Pa vs dimensionless), monotonicity, rejection of
a transposed construction, rejection of a `sigma_y0` that disagrees with
the table, both alpha conventions checked against their formulae, refusal
of an unknown name, and that the refusal message names the valid set.

### §8 audit

| # | Criterion | Result |
|---|---|---|
| 1 | §3 steps logged | This document; steps 1–4 condensed, reasoning above |
| 2 | `run_checks.sh` exits 0 | ✅ |
| 3 | Recorded numbers, freshly run | ✅ above |
| 4 | Workflow audit (L1–L5) | ✅ none — two branches and a raise, no loop, no state |
| 5 | No mirrored/frozen file edited | ✅ `git status` on those five paths: empty |
| 6 | Constants trace to `config.py` | ✅ every value read from `config`; nothing restated, nothing derived |

---

## Notes for later cards

- **T5 (solve)** owns the conversion to `nlfea_v4` types. `J2Material` maps
  to `IncrementalIsotropic(E, sigma_y0, H, eps_p_table, sigma_y_table)` —
  note `H`, the plastic tangent for the linear branch beyond the table, is
  **not** supplied here. It is a solver-side modelling choice about
  extrapolation past 5.26% plastic strain, not a property of the steel.
  Decide it at T5 and record it there.
- `kind` is a `ClassVar`, so it does not appear in the constructor but is
  available for provenance stamping, which `slay_case.py` already does for
  every other resolved value.

---

## Action log

| Date | Action |
|---|---|
| 12 Sep 2026 | Card executed and closed. `alpha_DNV = 1.300` independently verified against the DNV formula; the kernel's 2.278 confirmed wrong by 0.978. |

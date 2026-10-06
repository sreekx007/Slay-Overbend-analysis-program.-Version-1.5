# Validation ledgers

**Current version: [`VALIDATION_v2.0_2026-10-06.md`](VALIDATION_v2.0_2026-10-06.md).**

One file per revision, named `VALIDATION_v<major>.<minor>_<YYYY-MM-DD>.md`.
A ledger is dated and versioned because **a measured result is meaningless
without the configuration that produced it**, and a configuration ruling —
the contact surface, the mesh density, the staging order — changes every
number in the file at once. Editing results in place would leave no way to
tell a re-measurement from a correction.

**Superseded files are never edited.** They are the record of what was
measured, and the successor is a re-measurement of the same cases, so the
two have to stay comparable.

| Version | Date | Rebuild results computed with | Status |
|---|---|---|---|
| [2.0](VALIDATION_v2.0_2026-10-06.md) | 6 Oct 2026 | `contact_surface='bottom'` — `R + r_roller + OD/2`, the physical surface | **current** |
| [1.0](VALIDATION_v1.0_2026-10-06.md) | 6 Oct 2026 | `contact_surface='centreline'` — the pipe centreline on the `R` arc | superseded |

### Bump the version when

* a **configuration ruling** changes — contact surface, mesh density,
  staging, reporting zone, region scheme;
* a **defect is found** that invalidates recorded numbers rather than
  adding to them.

Adding rows for cases that were previously unrun is a **minor** bump and
does not need a new file unless the configuration also moved.

### One place to update

Links from elsewhere in the repo point at the current version by name, so
changing it means updating them. They are:
`docs/RESULTS.md`, `docs/TOOLCHAIN.md`,
`docs/modules/T9_components_spec.md`, `docs/modules/T9_physics_sequence.md`.

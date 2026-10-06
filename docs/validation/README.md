# Validation ledgers

**Current version: [`VALIDATION_v3.0_2026-10-06.md`](VALIDATION_v3.0_2026-10-06.md).**

One file per revision, named `VALIDATION_v<major>.<minor>_<YYYY-MM-DD>.md`.
A ledger is dated and versioned because **a measured result is meaningless
without the configuration that produced it**, and a configuration ruling —
the contact surface, the mesh density, the staging order — changes every
number in the file at once. Editing results in place would leave no way to
tell a re-measurement from a correction.

**Superseded files are never edited.** They are the record of what was
measured, and the successor is a re-measurement of the same cases, so the
two have to stay comparable.

| Version | Date | What | Status |
|---|---|---|---|
| [3.0](VALIDATION_v3.0_2026-10-06.md) | 6 Oct 2026 | Organised on the papers' own table numbering; rebuild against the papers only; bending moment for every case | **current** |
| [2.0](VALIDATION_v2.0_2026-10-06.md) | 6 Oct 2026 | Re-measured on `contact_surface='bottom'`, the physical surface | superseded |
| [1.0](VALIDATION_v1.0_2026-10-06.md) | 6 Oct 2026 | First consolidated ledger, on `contact_surface='centreline'` | superseded |

A **major** bump also covers a restructure that changes what the file is
for: v3.0 dropped the `run_slay` and previous-version columns, because the
question the ledger answers is *rebuild against the papers* and a table
carrying four comparisons answers it less well than one carrying two.

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

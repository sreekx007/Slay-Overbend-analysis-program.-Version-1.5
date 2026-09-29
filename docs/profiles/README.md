# Profile artifacts

A **profile** is the shape of one case: where the pipe sits, what it is made
of there, and the strain along it, at every position of the passage. It is
the artifact a figure reads.

Files here are **generated and git-ignored.** Regenerate with:

```bash
python3 tools/emit_profile.py --archetype ILS-SH --R 85
python3 tools/plot_from_schema.py --profile docs/profiles/ils-sh_R85_sp9_T120
```

## Why they are not committed

7.7 MB for two cases, and the geometry table grows as positions × samples.
The *recipe* is version controlled — the case definition, the emitter, and
the schema — so the output does not need to be. The **case dataset** under
`docs/dataset/` is committed instead: one row per passage is small, and it
is the thing worth diffing between runs.

## What a profile is

Three tables, one per grain, declared by `slay.report.profile_schema` and
described in full by the `.schema.json` written beside each one:

| File | Grain | Carries |
|---|---|---|
| `<case_id>.geometry.csv` | one row per sample per position | the solved centreline in world coordinates, the roller-centreline locus and the gap to it, and what the assembly is at that material point (`OD_section`, `y_contact`, and the two owners) |
| `<case_id>.sections.csv` | one row per element per position | strain and moment over each element's **own extent**, with the section that carries it |
| `<case_id>.stations.csv` | one row per roller | position, radius, and whether contact there is one-sided. No `step`: rollers do not move when the pipe does. |

The three share a `profile_schema_version` and join to a case row in
`docs/dataset/` by `case_id`. A profile deliberately does **not** repeat the
peaks and their locations — those live in the case row, under a separate
contract that versions separately.

## The rule this exists to serve

**G13 — a figure reads an artifact; it never generates one.**
`emit_profile.py` solves and writes. `plot_from_schema.py` reads and draws,
and imports nothing from `slay`. A quantity a figure needs and no contract
carries is a *missing column*, to be added to the schema — never a solver
call added to the plotter.

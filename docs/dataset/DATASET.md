# SLAY Overbend — ML case matrix

**7 of 200 cases run** in 0.01 h

| | |
|---|---|
| Date | 28 September 2026 |
| Branch | `claude/program-rebuild-status-bya72s` |
| Runner | `tools/dataset.py`, seed 20260928 |
| Converged fully | 7 (100%) |
| Converged partly | 0 (0%) |
| Failed | 0 (0%) |

Row = one case = one complete passage. Target columns come in two readings: the bare name is the **snapshot** at the envelope position, `_env` is the worst that location saw at **any** position. Both come from the same solve.

## Files

| File | Rows | Contents |
|---|---|---|
| `dataset_plain.csv` | 7 | plain pipe, no component |
| `dataset_gdtp.csv` | 0 | GD-TP thick component |

## Axes

| Axis | Values | Baseline |
|---|---|---|
| Stinger radius R (m) | 60, 70, 85, 105, 120, 150 | 85 |
| Roller spacing (m) | 6, 7.5, 9, 10.5, 12 | 9 |
| Pipe OD x WT (mm) | 168.3x11, 219.1x12.7, 273.1x15.9, 323.9x17.5, 406.4x21, 508x25.4, 610x28.6 | 406.4x21 |
| Tension (MT) | 40, 80, 120, 160, 200 | 120 |
| Component length (xOD) | 1, 2.5, 5, 10 | 2.5 |
| Component wall (x pipe) | 1.5, 2, 3, 4 | 2.0 |

## Plain pipe — every case

| case | design | R | sp | OD×WT | T | L/OD | t/t | envelope | at shift | I ratio | s | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P000 | ofat | 85 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 8s | ok |
| P001 | ofat | 60 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 10.4s | ok |
| P002 | ofat | 70 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 9s | ok |
| P003 | ofat | 105 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 5s | ok |
| P004 | ofat | 120 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 4.4s | ok |
| P005 | ofat | 150 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 4.2s | ok |
| P006 | ofat | 85 | 6 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 4.9s | ok |


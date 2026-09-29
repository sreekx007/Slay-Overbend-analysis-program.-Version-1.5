# SLAY Overbend — ML case matrix

**26 of 200 cases run** in 0.05 h

| | |
|---|---|
| Date | 28 September 2026 |
| Branch | `claude/program-rebuild-status-bya72s` |
| Runner | `tools/dataset.py`, seed 20260928 |
| Converged fully | 25 (96%) |
| Converged partly | 1 (4%) |
| Failed | 0 (0%) |

Row = one case = one complete passage. Target columns come in two readings: the bare name is the **snapshot** at the envelope position, `_env` is the worst that location saw at **any** position. Both come from the same solve.

## Files

| File | Rows | Contents |
|---|---|---|
| `dataset_plain.csv` | 26 | plain pipe, no component |
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
| P000 | ofat | 85 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 6.9s | ok |
| P001 | ofat | 60 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 10.1s | ok |
| P002 | ofat | 70 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 9.3s | ok |
| P003 | ofat | 105 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 4.3s | ok |
| P004 | ofat | 120 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 3.8s | ok |
| P005 | ofat | 150 | 9 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 3.2s | ok |
| P006 | ofat | 85 | 6 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 4.1s | ok |
| P007 | ofat | 85 | 7.5 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 5.4s | ok |
| P008 | ofat | 85 | 10.5 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 6.8s | ok |
| P009 | ofat | 85 | 12 | 406.4×21 | 120 | 0 | 0 | — | — | 1.000 | 10.7s | ok |
| P010 | ofat | 85 | 9 | 168.3×11 | 120 | 0 | 0 | — | — | 1.000 | 5.1s | ok |
| P011 | ofat | 85 | 9 | 219.1×12.7 | 120 | 0 | 0 | — | — | 1.000 | 4.2s | ok |
| P012 | ofat | 85 | 9 | 273.1×15.9 | 120 | 0 | 0 | — | — | 1.000 | 4.9s | ok |
| P013 | ofat | 85 | 9 | 323.9×17.5 | 120 | 0 | 0 | — | — | 1.000 | 4.2s | ok |
| P014 | ofat | 85 | 9 | 508×25.4 | 120 | 0 | 0 | — | — | 1.000 | 8.5s | ok |
| P015 | ofat | 85 | 9 | 610×28.6 | 120 | 0 | 0 | — | — | 1.000 | 11.5s | ok |
| P016 | ofat | 85 | 9 | 406.4×21 | 40 | 0 | 0 | — | — | 1.000 | 10.9s | ok |
| P017 | ofat | 85 | 9 | 406.4×21 | 80 | 0 | 0 | — | — | 1.000 | 6.2s | ok |
| P018 | ofat | 85 | 9 | 406.4×21 | 160 | 0 | 0 | — | — | 1.000 | 6.3s | ok |
| P019 | ofat | 85 | 9 | 406.4×21 | 200 | 0 | 0 | — | — | 1.000 | 7.3s | ok |
| P020 | lhs | 120 | 12 | 273.1×15.9 | 80 | 0 | 0 | — | — | 1.000 | 5.4s | ok |
| P021 | lhs | 105 | 6 | 323.9×17.5 | 40 | 0 | 0 | — | — | 1.000 | 2.5s | ok |
| P022 | lhs | 70 | 10.5 | 406.4×21 | 200 | 0 | 0 | — | — | 1.000 | 7.9s | partial 1/2 |
| P023 | lhs | 105 | 12 | 273.1×15.9 | 160 | 0 | 0 | — | — | 1.000 | 6.9s | ok |
| P024 | lhs | 150 | 10.5 | 219.1×12.7 | 200 | 0 | 0 | — | — | 1.000 | 4.7s | ok |
| P025 | lhs | 120 | 12 | 168.3×11 | 80 | 0 | 0 | — | — | 1.000 | 5.4s | ok |

## Cases that did not fully converge

Recorded, not dropped. A dataset holding only the cases that converged is biased toward the easy corner of the parameter space and says nothing about where the method stops working.

| case | R | sp | OD×WT | T | L/OD | t/t | status | reason |
|---|---|---|---|---|---|---|---|---|
| P022 | 70 | 10.5 | 406.4×21 | 200 | 0 | 0 | partial 1/2 | positions diverged |


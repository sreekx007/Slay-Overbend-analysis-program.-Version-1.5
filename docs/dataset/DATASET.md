# SLAY Overbend — ML case matrix

**17 of 200 cases run** in 0.04 h

| | |
|---|---|
| Date | 28 September 2026 |
| Branch | `claude/program-rebuild-status-bya72s` |
| Runner | `tools/dataset.py`, seed 20260928 |
| Converged fully | 17 (100%) |
| Converged partly | 0 (0%) |
| Failed | 0 (0%) |

Row = one case = one complete passage. Target columns come in two readings: the bare name is the **snapshot** at the envelope position, `_env` is the worst that location saw at **any** position. Both come from the same solve.

## Files

| File | Rows | Contents |
|---|---|---|
| `dataset_plain.csv` | 17 | plain pipe, no component |
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
| P000 | ofat | 85 | 9 | 406.4×21 | 120 | 0 | 0 | 0.4085% | 0.000 | 1.000 | 8.7s | ok |
| P001 | ofat | 60 | 9 | 406.4×21 | 120 | 0 | 0 | 0.7011% | 0.000 | 1.000 | 13.1s | ok |
| P002 | ofat | 70 | 9 | 406.4×21 | 120 | 0 | 0 | 0.5531% | 0.000 | 1.000 | 10.6s | ok |
| P003 | ofat | 105 | 9 | 406.4×21 | 120 | 0 | 0 | 0.2978% | 0.000 | 1.000 | 6.2s | ok |
| P004 | ofat | 120 | 9 | 406.4×21 | 120 | 0 | 0 | 0.2406% | 0.000 | 1.000 | 5.3s | ok |
| P005 | ofat | 150 | 9 | 406.4×21 | 120 | 0 | 0 | 0.1906% | 0.000 | 1.000 | 4.1s | ok |
| P006 | ofat | 85 | 6 | 406.4×21 | 120 | 0 | 0 | 0.3268% | 0.000 | 1.000 | 5.5s | ok |
| P007 | ofat | 85 | 7.5 | 406.4×21 | 120 | 0 | 0 | 0.3750% | 0.000 | 1.000 | 7.1s | ok |
| P008 | ofat | 85 | 10.5 | 406.4×21 | 120 | 0 | 0 | 0.4389% | 0.000 | 1.000 | 11s | ok |
| P009 | ofat | 85 | 12 | 406.4×21 | 120 | 0 | 0 | 0.4717% | 0.000 | 1.000 | 17.5s | ok |
| P010 | ofat | 85 | 9 | 168.3×11 | 120 | 0 | 0 | 0.5174% | 0.337 | 1.000 | 7s | ok |
| P011 | ofat | 85 | 9 | 219.1×12.7 | 120 | 0 | 0 | 0.3877% | 0.000 | 1.000 | 6.4s | ok |
| P012 | ofat | 85 | 9 | 273.1×15.9 | 120 | 0 | 0 | 0.3342% | 0.000 | 1.000 | 6.4s | ok |
| P013 | ofat | 85 | 9 | 323.9×17.5 | 120 | 0 | 0 | 0.3516% | 0.000 | 1.000 | 6.9s | ok |
| P014 | ofat | 85 | 9 | 508×25.4 | 120 | 0 | 0 | 0.4974% | 0.000 | 1.000 | 12.6s | ok |
| P015 | ofat | 85 | 9 | 610×28.6 | 120 | 0 | 0 | 0.5981% | 0.000 | 1.000 | 16.5s | ok |
| P016 | ofat | 85 | 9 | 406.4×21 | 40 | 0 | 0 | 0.3298% | 0.000 | 1.000 | 14.6s | ok |


#!/usr/bin/env python3
"""profile_status.py -- did this profile's passage actually happen?

    from profile_status import status, require_complete
    st = status('docs/profiles/xxxii_S2-6')

ONE READER, SO THERE IS ONE ANSWER. Every study tool that compares a result
to a published table needs the same gate, and a gate that each tool
reimplements is a gate each tool can get subtly wrong -- which is how L101
happened. `study_table_xxxii.py` read the sections table filtered on
`in_band`, and the single row that said the passage had stopped at 16% of
its travel is exactly the row that filter drops.

READS THE ARTIFACT, NOT THE SOLVER. It imports nothing from `slay`: the
three status columns are part of the profile contract (schema 1.5.0,
`passage_complete` / `sweep_total` / `sweep_ran`), carried on the geometry
table as case context, and reading them back is how a contract gets
checked. Only the first data row is parsed -- `per='case'` means the values
cannot vary within a file, and `profile.write` already refuses one where
they do.

A FILE WRITTEN BEFORE 1.5.0 HAS NO SUCH COLUMNS, and that is reported as
`complete=None`, UNKNOWN -- never as True. An old artifact is not evidence
of a complete passage; it is evidence of nothing, and the difference
matters because the whole point is to stop reading a partial traverse as a
finished one.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Status:
    """What the artifact says about its own passage."""
    case_id: str
    schema: str
    complete: object = None      # True / False / None when the file is old
    total: float = None          # m of travel the passage was sized for
    ran: float = None            # m actually reached

    @property
    def known(self) -> bool:
        return self.complete is not None

    @property
    def fraction(self) -> float:
        if not self.total:
            return float('nan')
        return self.ran / self.total

    def flag(self) -> str:
        """One short cell for a results table. Empty when all is well."""
        if self.complete is True:
            return ''
        if self.complete is None:
            return '  ?'
        return f'{100 * self.fraction:4.0f}%'

    def __str__(self) -> str:
        if self.complete is True:
            return f'{self.case_id}: passage complete ({self.ran:.3f} m)'
        if self.complete is None:
            return (f'{self.case_id}: passage completion UNKNOWN -- profile '
                    f'schema {self.schema} predates 1.5.0')
        return (f'{self.case_id}: passage INCOMPLETE -- {self.ran:.3f} m of '
                f'{self.total:.3f} m ({100 * self.fraction:.1f}%)')


def status(stem) -> Status:
    """Read `<stem>.geometry.csv`'s case context. Raises if it is not there."""
    f = Path(str(stem) + '.geometry.csv')
    with open(f, newline='') as fh:
        row = next(csv.DictReader(fh), None)
    if row is None:
        raise ValueError(f'{f} has no data rows')

    def num(key):
        v = (row.get(key) or '').strip()
        return float(v) if v else None

    raw = (row.get('passage_complete') or '').strip().lower()
    done = {'true': True, '1': True, 'false': False, '0': False}.get(raw)
    return Status(case_id=row.get('case_id', ''),
                  schema=row.get('profile_schema_version', ''),
                  complete=done, total=num('sweep_total'),
                  ran=num('sweep_ran'))


def require_complete(stem) -> Status:
    """`status`, but refuses anything but a finished passage.

    For the tools that compare against a published table. A partial traverse
    is not a conservative version of the answer, it is a different quantity,
    and comparing it to a paper's number produces a percentage that means
    nothing. Unknown is refused too: see the module docstring.
    """
    st = status(stem)
    if st.complete is not True:
        raise ValueError(
            f'{st} -- refusing to compare this with a published result. '
            f'Re-run the case, or report it as incomplete rather than as a '
            f'difference.')
    return st


if __name__ == '__main__':
    import sys
    bad = 0
    for arg in sys.argv[1:]:
        st = status(arg[:-len('.geometry.csv')]
                    if arg.endswith('.geometry.csv') else arg)
        print(st)
        bad += (st.complete is not True)
    raise SystemExit(1 if bad else 0)

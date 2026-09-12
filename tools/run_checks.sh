#!/usr/bin/env bash
# run_checks.sh -- the gate every task card must pass before it is DONE.
#
# Two checks, in order of how cheaply they fail:
#   1. layer linter -- static, no imports, catches a boundary breach instantly
#   2. test suite   -- the numbers
#
# Per guardrail G8, a green run here is necessary but NOT sufficient: a card
# is complete only when its own VERIFY clause has produced recorded numbers.
# "The checks passed" has never been evidence in this project.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

echo "== layer linter =="
python3 tools/check_layers.py

echo
echo "== tests =="
python3 -m pytest rebuild/tests -q

echo
echo "all checks passed"

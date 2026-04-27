#!/usr/bin/env bash
# Run the ticket reservation load test.
#
# Any arguments are forwarded directly to load_test.py.
#
# Usage:
#   ./run-load-test.sh
#   ./run-load-test.sh --users 200 --tickets 20
#   ./run-load-test.sh --users 500 --tickets 10 --concurrency 500
#
# Parameters:
#   --users N         Total simulated users; each fires one reservation attempt.
#   --tickets M       Tickets to generate. M < N creates contention (recommended).
#   --concurrency C   Max in-flight HTTP requests at once. Match N for full burst.
#
# Requires: services must be running (docker compose up -d)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOAD_TEST_DIR="$SCRIPT_DIR/load-test"
PYTHON="$LOAD_TEST_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: venv not found at $LOAD_TEST_DIR/.venv" >&2
  echo "       Run: cd load-test && uv venv && uv pip install httpx" >&2
  exit 1
fi

exec "$PYTHON" "$LOAD_TEST_DIR/load_test.py" "$@"

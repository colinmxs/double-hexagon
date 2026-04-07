#!/usr/bin/env bash
# Run backend tests per-directory to avoid module name collisions.
# Each lambda handler has its own handler.py, so they must run in isolation.
set -e

FAIL=0

# Shared modules
echo "=== lambda/shared ==="
python3 -m pytest lambda/shared/ -q || FAIL=1

# Each lambda handler directory
for dir in lambda/*/; do
  [ "$dir" = "lambda/shared/" ] && continue
  [ "$dir" = "lambda/fixtures/" ] && continue
  test_file="${dir}test_handler.py"
  [ -f "$test_file" ] || continue
  echo "=== $dir ==="
  python3 -m pytest "$test_file" -q || FAIL=1
done

# Backend lambdas (if any have tests)
for dir in backend/lambdas/*/; do
  test_file="${dir}test_handler.py"
  [ -f "$test_file" ] || continue
  echo "=== $dir ==="
  python3 -m pytest "$test_file" -q || FAIL=1
done

exit $FAIL

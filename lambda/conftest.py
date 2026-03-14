"""Root conftest for lambda tests.

Each Lambda subdirectory has its own handler.py. When running all tests
together, Python's module cache causes ``from handler import handler`` and
``@patch("handler.xxx")`` to resolve to whichever handler.py was imported
first.

SOLUTION: Run each Lambda directory as a separate pytest invocation, or use
the run_all_lambda_tests.sh script. When running a single directory
(e.g. ``pytest lambda/submit_application/``), no special handling is needed.

If running all directories at once, use --forked (requires pytest-forked)
or run each directory separately to avoid module cache collisions.
"""

"""Run all registered tests from one place: `python -m app.tests`."""
from app.tests.test_runner import run
from app.tests import test_settings_and_assignments  # noqa: F401  registers suites

if __name__ == "__main__":
    import sys
    sys.exit(run())

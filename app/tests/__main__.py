"""Run all registered tests from one place: `python -m app.tests`."""
from app.tests.test_runner import run
from app.tests import test_settings_and_assignments  # noqa: F401  registers suites
from app.tests import test_contiguous_lab_slots  # noqa: F401  registers suites
from app.tests import test_exam_date_separation  # noqa: F401  registers suites
from app.tests import test_async_generation  # noqa: F401  registers suites
from app.tests import test_variation  # noqa: F401  registers suites
from app.tests import test_combinations  # noqa: F401  registers suites
from app.tests import test_flexibility  # noqa: F401  registers suites
from app.tests import test_redis_integration  # noqa: F401  registers suites
from app.tests import test_email_notifications  # noqa: F401  registers suites
from app.tests import test_api_polish  # noqa: F401  registers suites
from app.tests import test_overrides  # noqa: F401  registers suites
from app.tests import test_my_schedule  # noqa: F401  registers suites
from app.tests import test_notifications  # noqa: F401  registers suites
from app.tests import test_security  # noqa: F401  registers suites
from app.tests import test_parallel_labs  # noqa: F401  registers suites
from app.tests import test_grid_real  # noqa: F401  registers suites
from app.tests import test_lab_windows  # noqa: F401  registers suites

if __name__ == "__main__":
    import sys
    sys.exit(run())

import os
from pathlib import Path
import pytest

_PROJECT_ROOT = Path(__file__).parent
_DEFAULT_GED = _PROJECT_ROOT / "../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged"


def pytest_addoption(parser):
    parser.addoption(
        "--gedfile",
        default=None,
        help="Path to the GEDCOM file to test (or set GED_FILE env var)",
    )


def pytest_configure(config):
    # Allow --gedfile CLI option to set the env var picked up by all test modules
    try:
        gedfile = config.getoption("--gedfile")
    except ValueError:
        gedfile = None
    if gedfile:
        os.environ["GED_FILE"] = gedfile
    # Fall back to merged.ged in the project root if it exists
    elif not os.environ.get("GED_FILE") and _DEFAULT_GED.exists():
        os.environ["GED_FILE"] = str(_DEFAULT_GED)


def pytest_runtest_setup(item):
    """Skip tests whose module requires GED_FILE if it is not set."""
    mod = item.module
    ged_path = getattr(mod, "GED_PATH", None)
    if ged_path is not None and not ged_path:
        pytest.skip("GED_FILE env var not set — use --gedfile or set GED_FILE")

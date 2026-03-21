import os
import pytest


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


def pytest_sessionstart(session):
    path = os.environ.get("GED_FILE", "")
    if not path:
        print(
            "\nNo GEDCOM file specified. "
            "Use --gedfile path/to/file.ged or set the GED_FILE environment variable.\n"
        )

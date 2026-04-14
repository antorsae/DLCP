from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help=(
            "run live hardware tests that require the DLCP rig, connected MAIN units, "
            "CONTROL, camera, and programmable IR emitter"
        ),
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-hardware"):
        return

    skip_hardware = pytest.mark.skip(
        reason="needs live DLCP hardware rig; pass --run-hardware to enable"
    )
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)

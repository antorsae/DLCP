from __future__ import annotations

import os
from pathlib import Path

import pytest

from dlcp_fw.cli import hardware_state_test as hw


pytestmark = [pytest.mark.hardware, pytest.mark.slow]


def _common_cli_args() -> list[str]:
    output_root = Path(
        os.environ.get(
            "DLCP_HW_OUTPUT_ROOT",
            str(hw.DEFAULT_OUTPUT_ROOT / "pytest"),
        )
    )
    args = ["--output-root", str(output_root)]

    flipper_port = os.environ.get("DLCP_HW_FLIPPER_PORT")
    if flipper_port:
        args.extend(["--flipper-port", flipper_port])

    camera_selector = os.environ.get("DLCP_HW_CAMERA_SELECTOR")
    if camera_selector:
        args.extend(["--camera-selector", camera_selector])

    camera_address = os.environ.get("DLCP_HW_CAMERA_ADDRESS")
    if camera_address:
        args.extend(["--address", camera_address])

    if os.environ.get("DLCP_HW_SKIP_CONFIGURE") == "1":
        args.append("--skip-configure")

    return args


def _current_pair_preset() -> str:
    states = hw._collect_main_roles(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
    left, right = hw._assert_left_right_roles(states)
    if left.active_preset not in {"A", "B"} or right.active_preset not in {"A", "B"}:
        raise RuntimeError(
            f"unable to determine current pair preset: left={left.active_preset!r} "
            f"right={right.active_preset!r}"
        )
    if left.active_preset != right.active_preset:
        raise RuntimeError(
            f"pair is already split before test start: left={left.active_preset!r} "
            f"right={right.active_preset!r}"
        )
    return left.active_preset


@pytest.mark.hardware
def test_live_preset_convergence_reaches_requested_target() -> None:
    current = _current_pair_preset()
    action = "F2" if current == "A" else "F1"

    rc = hw.main(
        _common_cli_args()
        + [
            "preset-convergence",
            "--action",
            action,
            "--timeout-s",
            "15",
            "--lcd-timeout-s",
            "25",
        ]
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_rapid_toggle_convergence_reaches_final_target() -> None:
    current = _current_pair_preset()
    sequence = "F2,F1,F2" if current == "A" else "F1,F2,F1"

    rc = hw.main(
        _common_cli_args()
        + [
            "rapid-toggle-convergence",
            "--sequence",
            sequence,
            "--inter-press-ms",
            os.environ.get("DLCP_HW_INTER_PRESS_MS", "250"),
            "--timeout-s",
            "15",
            "--lcd-timeout-s",
            "25",
        ]
    )

    assert rc == 0

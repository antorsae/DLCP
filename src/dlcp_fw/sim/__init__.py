"""DLCP preset simulation framework."""

from .bus import CurrentLoopBus, FaultProfile
from .control_gpsim import GpsimControlHarness, StepResult, TxTriplet
from .control_ui import ControlPersistentState, ControlStrings, ControlUISim
from .gpsim import GpsimRunConfig, GpsimRunResult, run_gpsim
from .hexio import assert_bytes, parse_intel_hex, write_intel_hex
from .lcd import LcdState, decode_lcd_bytes
from .main_model import MainUnitModel
from .main_gpsim import MainGpsimResult, run_main_mailbox_gpsim
from .main_gpsim_timer3 import (
    MainHarnessTimer3Result,
    Timer3ModelComparison,
    Timer3OverflowEvent,
    compare_timer3_models,
    run_main_mailbox_gpsim_harness_timer3,
)
from .overlay import OverlayError, OverlayManifest, OverlayResult, apply_overlay, apply_overlays
from .protocol import SerialFrame

__all__ = [
    "CurrentLoopBus",
    "FaultProfile",
    "ControlPersistentState",
    "ControlStrings",
    "ControlUISim",
    "GpsimControlHarness",
    "StepResult",
    "TxTriplet",
    "GpsimRunConfig",
    "GpsimRunResult",
    "run_gpsim",
    "assert_bytes",
    "parse_intel_hex",
    "write_intel_hex",
    "LcdState",
    "decode_lcd_bytes",
    "MainUnitModel",
    "MainGpsimResult",
    "run_main_mailbox_gpsim",
    "Timer3OverflowEvent",
    "MainHarnessTimer3Result",
    "Timer3ModelComparison",
    "run_main_mailbox_gpsim_harness_timer3",
    "compare_timer3_models",
    "OverlayError",
    "OverlayManifest",
    "OverlayResult",
    "apply_overlay",
    "apply_overlays",
    "SerialFrame",
]

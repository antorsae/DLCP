"""DLCP preset simulation framework."""

from .bus import CurrentLoopBus, FaultProfile
from .control_ui import ControlPersistentState, ControlStrings, ControlUISim
from .hexio import assert_bytes, parse_intel_hex, write_intel_hex
from .lcd import LcdState, decode_lcd_bytes
from .main_model import MainUnitModel
from .main_seed import build_seeded_main_sim_hex
from .overlay import OverlayError, OverlayManifest, OverlayResult, apply_overlay, apply_overlays
from .protocol import SerialFrame

__all__ = [
    "CurrentLoopBus",
    "FaultProfile",
    "ControlPersistentState",
    "ControlStrings",
    "ControlUISim",
    "assert_bytes",
    "parse_intel_hex",
    "write_intel_hex",
    "LcdState",
    "decode_lcd_bytes",
    "MainUnitModel",
    "build_seeded_main_sim_hex",
    "OverlayError",
    "OverlayManifest",
    "OverlayResult",
    "apply_overlay",
    "apply_overlays",
    "SerialFrame",
]

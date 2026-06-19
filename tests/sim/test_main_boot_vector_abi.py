"""MAIN fixed-entry bootloader/app ABI contracts.

The Microchip bootloader region is preserved when V3.x app-only MAIN images are
seeded for simulation or flashed over an existing device. These tests pin the
fixed-address contract between that bootloader and the app image.
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import (
    STOCK_MAIN_COMBINED_HEX,
    V32_MAIN_HEX,
    V33_MAIN_HEX,
    V34_MAIN_HEX,
    V35_MAIN_HEX,
)
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_seed import MAIN_APP_PATCH_LIMIT, MAIN_APP_PATCH_START


BOOT_RESET_VECTOR = 0x0000
BOOT_HIGH_IRQ_VECTOR = 0x0008
APP_RESET_ENTRY = 0x1000
APP_IRQ_STUB = 0x1008

GOTO_APP_RESET = bytes([0xC7, 0xEF, 0x02, 0xF0])
GOTO_APP_IRQ_STUB = bytes([0x04, 0xEF, 0x08, 0xF0])
MOVFF_FSR2L_TO_ISR_SAVE = bytes([0xD9, 0xCF, 0x01, 0xF0])
MOVFF_FSR2H_TO_ISR_SAVE = bytes([0xDA, 0xCF, 0x02, 0xF0])


def _seeded_bytes(app_hex) -> dict[int, int]:  # type: ignore[no-untyped-def]
    merged = dict(parse_intel_hex(STOCK_MAIN_COMBINED_HEX))
    for addr, value in parse_intel_hex(app_hex).items():
        if MAIN_APP_PATCH_START <= addr < MAIN_APP_PATCH_LIMIT:
            merged[addr] = value
    return merged


def _bytes_at(image: dict[int, int], addr: int, n: int) -> bytes:
    return bytes(image.get(addr + i, 0xFF) for i in range(n))


@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(V32_MAIN_HEX, id="v32"),
        pytest.param(V33_MAIN_HEX, id="v33"),
        pytest.param(
            V34_MAIN_HEX,
            marks=pytest.mark.xfail(
                strict=True,
                reason="BUG-V35-FNAME-EEPROM: V3.4 app IRQ stub starts at 0x1006",
            ),
            id="v34-current",
        ),
        pytest.param(V35_MAIN_HEX, id="v35"),
    ],
)
def test_seeded_main_bootloader_vectors_enter_expected_app_stubs(main_hex) -> None:  # type: ignore[no-untyped-def]
    image = _seeded_bytes(main_hex)

    assert _bytes_at(image, BOOT_RESET_VECTOR, 4) == GOTO_APP_RESET
    assert _bytes_at(image, BOOT_HIGH_IRQ_VECTOR, 4) == GOTO_APP_IRQ_STUB
    assert _bytes_at(image, APP_RESET_ENTRY, 2) in {
        bytes([0x0A, 0xEF]),  # goto app cold init path, V3.2/V3.3
        bytes([0x08, 0xD0]),  # bra app cold init path, V3.4
        bytes([0x09, 0xD0]),  # bra app cold init path, V3.5 after IRQ ABI pad
    }
    assert _bytes_at(image, APP_IRQ_STUB, 4) == MOVFF_FSR2L_TO_ISR_SAVE
    assert _bytes_at(image, APP_IRQ_STUB + 4, 4) == MOVFF_FSR2H_TO_ISR_SAVE

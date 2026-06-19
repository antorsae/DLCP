"""V3.5 MAIN volume command to TAS3108 coefficient semantics."""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V33_MAIN_HEX, V35_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc


ACTIVE_FLAGS = 0x05E
LOGICAL_VOLUME = 0x066
COMPUTED_VOLUME = 0x06E
EVENT_FLAGS = 0x07E
DSP_FAULT_FLAGS = 0x07F
PENDING_ROUTE_REQUEST = 0x093
USER_MUTE_LATCH = 0x094
ROUTE_VOLUME_TRIM_OFFSET = 0x09A
ROUTE_0_VOLUME_TRIM = 0x09B
APPLIED_ROUTE_SHADOW = 0x0AB

ACTIVE_GATE_MASK = 0x08
ACTIVE_MUTE_MASK = 0x10
ACTIVE_MUTE_SHADOW_MASK = 0x20
USER_MUTE_LATCH_MASK = 0x20
VOLUME_DIRTY_MASK = 0x08
MUTE_DIRTY_MASK = 0x20

TAS_REG_VOLUME_COEFF = 0x30
BOOT_TCY = 16_000_000
COMMAND_SETTLE_TCY = 1_000_000

EXPECTED_TAS30_BY_DATA = {
    0x72: "03f6a86c",
    0x71: "03887774",
    0x70: "03264460",
    0x6F: "02cec32c",
    0x6E: "0280b700",
    0x6D: "023b26ec",
    0x6C: "01fd1c90",
    0x6B: "01c5d436",
    0x6A: "01947e8c",
    0x69: "01688f3a",
    0x68: "01416318",
    0x67: "011e7672",
    0x66: "00ff568e",
    0x65: "00e398d5",
    0x64: "00cadc47",
    0x63: "00b4c901",
    0x62: "00a12162",
    0x61: "008f9ced",
    0x60: "00800000",
    0x5F: "007214a2",
    0x5E: "0065ab2e",
    0x5D: "005a9cac",
    0x5C: "0050c109",
    0x5B: "0047f814",
    0x5A: "00402308",
    0x59: "00392824",
    0x58: "0032f01a",
    0x57: "002d6416",
    0x56: "00287348",
    0x55: "00240c39",
    0x54: "00201f95",
    0x53: "001c9fad",
    0x52: "001981d1",
    0x51: "0016bac1",
    0x50: "0014408f",
    0x4F: "00120bdb",
    0x4E: "0010149f",
    0x4D: "000e542c",
    0x4C: "000cc441",
    0x4B: "000b6020",
    0x4A: "000a22c2",
    0x49: "000907c5",
    0x48: "00080bc2",
    0x47: "00072b42",
    0x46: "00066305",
    0x45: "0005b0c5",
    0x44: "000511df",
    0x43: "00048451",
    0x42: "00040625",
    0x41: "000395c4",
    0x40: "000331a3",
    0x3F: "0002d860",
    0x3E: "000288e6",
    0x3D: "00024216",
    0x3C: "000202fe",
    0x3B: "0001cabf",
    0x3A: "000198aa",
    0x39: "00016c0e",
    0x38: "00014446",
    0x37: "000120de",
    0x36: "00010150",
    0x35: "0000e536",
    0x34: "0000cc29",
    0x33: "0000b5da",
    0x32: "0000a1fd",
    0x31: "00009046",
    0x30: "00008082",
    0x2F: "00007277",
    0x2E: "000065f3",
    0x2D: "00005acd",
    0x2C: "000050df",
    0x2B: "00004808",
    0x2A: "00004026",
    0x29: "00003922",
    0x28: "000032e3",
    0x27: "00002d52",
    0x26: "0000285c",
    0x25: "000023f1",
    0x24: "00002002",
    0x23: "00001c81",
    0x22: "00001962",
    0x21: "0000169b",
    0x20: "00001421",
    0x1F: "000011ed",
    0x1E: "00000ff7",
    0x1D: "00000e37",
    0x1C: "00000ca8",
    0x1B: "00000b46",
    0x1A: "00000a09",
    0x19: "000008f0",
    0x18: "000007f5",
    0x17: "00000716",
    0x16: "0000064f",
    0x15: "0000059e",
    0x14: "00000500",
    0x13: "00000474",
    0x12: "000003f7",
    0x11: "00000388",
    0x10: "00000325",
    0x0F: "000002cc",
    0x0E: "0000027e",
    0x0D: "00000238",
    0x0C: "000001f9",
    0x0B: "000001c2",
    0x0A: "00000191",
    0x09: "00000165",
    0x08: "0000013e",
    0x07: "0000011b",
    0x06: "000000fc",
    0x05: "000000e0",
    0x04: "000000c7",
    0x03: "000000b1",
    0x02: "0000009e",
    0x01: "0000008d",
    0x00: "0000007d",
}


def _require_rust() -> None:
    if RustChain is None:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _boot_main(hex_path):
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(hex_path))
    chain.step_tcy(BOOT_TCY)
    _force_active_unmuted_no_trim_route(chain)
    chain.reset_main_dsp_write_log(0)
    chain.step_tcy(12_000_000)
    _force_active_unmuted_no_trim_route(chain)
    chain.reset_main_dsp_write_log(0)
    return chain


def _force_active_unmuted_no_trim_route(chain) -> None:
    active = chain.read_reg(ACTIVE_FLAGS) & 0xFF
    active |= ACTIVE_GATE_MASK
    active &= ~(ACTIVE_MUTE_MASK | ACTIVE_MUTE_SHADOW_MASK)
    chain.write_reg(ACTIVE_FLAGS, active)
    chain.write_reg(USER_MUTE_LATCH, chain.read_reg(USER_MUTE_LATCH) & ~USER_MUTE_LATCH_MASK)
    chain.write_reg(APPLIED_ROUTE_SHADOW, 0x01)
    chain.write_reg(ROUTE_VOLUME_TRIM_OFFSET, 0x00)
    for addr in range(ROUTE_0_VOLUME_TRIM, ROUTE_0_VOLUME_TRIM + 4):
        chain.write_reg(addr, 0x00)


def _int32_le_bytes(value: int) -> tuple[int, int, int, int]:
    raw = value & 0xFFFFFFFF
    return tuple((raw >> (8 * i)) & 0xFF for i in range(4))


def _volume_state(chain, base: int) -> tuple[int, int, int, int]:
    return tuple(chain.read_reg(base + i) & 0xFF for i in range(4))


def _tas_reg30_bytes(chain) -> bytes:
    return bytes(chain.read_main_dsp_reg(0, TAS_REG_VOLUME_COEFF + i) for i in range(4))


def _inject_volume(chain, data: int) -> None:
    delivered, overruns = chain.inject_main_frames_fifo([[0xB0, 0x07, data]], fifo_limit=47)
    assert delivered == 3 and overruns == 0


def _apply_volume_and_read_payload(
    chain,
    data: int,
    *,
    require_single: bool = True,
    forbid_volume_family_starts: bool = True,
) -> bytes:
    chain.reset_main_dsp_write_log(0)
    _inject_volume(chain, data)
    payloads: list[bytes] = []
    for _ in range(30):
        chain.step_tcy(COMMAND_SETTLE_TCY)
        payloads = chain.read_main_dsp_write_payloads(0, TAS_REG_VOLUME_COEFF)
        if payloads:
            break
    assert payloads, f"missing TAS 0x30 write for data 0x{data:02X}"
    if require_single:
        assert len(payloads) == 1, (
            f"expected exactly one TAS 0x30 write for data 0x{data:02X}, "
            f"got {[payload.hex() for payload in payloads]}"
        )
    else:
        assert all(payload == payloads[-1] for payload in payloads), (
            f"multiple TAS 0x30 writes for data 0x{data:02X} disagree: "
            f"{[payload.hex() for payload in payloads]}"
        )
    if forbid_volume_family_starts:
        for subaddr in range(0x31, 0x37):
            assert chain.read_main_dsp_write_payloads(0, subaddr) == [], (
                f"pure volume command emitted unexpected TAS start 0x{subaddr:02X}"
            )
    return payloads[-1]


def _sweep_volume_payloads(hex_path) -> dict[int, str]:
    chain = _boot_main(hex_path)
    payloads: dict[int, str] = {}
    for data in range(0x72, -1, -1):
        payload = _apply_volume_and_read_payload(
            chain,
            data,
            require_single=False,
            forbid_volume_family_starts=False,
        )
        payloads[data] = payload.hex()
    return payloads


def test_v35_serial_volume_full_range_writes_exact_tas30_coefficients() -> None:
    chain = _boot_main(V35_MAIN_HEX)
    values: list[int] = []

    for data in range(0x72, -1, -1):
        db = data - 0x60
        payload = _apply_volume_and_read_payload(chain, data)
        expected = bytes.fromhex(EXPECTED_TAS30_BY_DATA[data])
        assert payload == expected
        assert len(payload) == 4
        assert payload[0] & 0xF0 == 0
        assert _tas_reg30_bytes(chain) == payload
        assert _volume_state(chain, LOGICAL_VOLUME) == _int32_le_bytes(db)
        assert _volume_state(chain, COMPUTED_VOLUME) == _int32_le_bytes(db)
        assert not (chain.read_reg(EVENT_FLAGS) & (VOLUME_DIRTY_MASK | MUTE_DIRTY_MASK))
        assert not (chain.read_reg(DSP_FAULT_FLAGS) & 0x44)
        values.append(int.from_bytes(payload, "big"))

    assert values == sorted(values, reverse=True)
    assert len(EXPECTED_TAS30_BY_DATA) == 0x73


def test_v35_volume_sweep_matches_v33_payloads() -> None:
    assert _sweep_volume_payloads(V35_MAIN_HEX) == _sweep_volume_payloads(V33_MAIN_HEX)


@pytest.mark.parametrize("data", [0x72, 0x60, 0x42, 0x00])
def test_v35_no_trim_route_ignores_poisoned_pending_route_and_trim(data: int) -> None:
    chain = _boot_main(V35_MAIN_HEX)
    chain.write_reg(PENDING_ROUTE_REQUEST, 0x00)
    chain.write_reg(ROUTE_VOLUME_TRIM_OFFSET, 0x2A)
    for addr in range(ROUTE_0_VOLUME_TRIM, ROUTE_0_VOLUME_TRIM + 4):
        chain.write_reg(addr, 0x12)
    chain.write_reg(APPLIED_ROUTE_SHADOW, 0x01)

    payload = _apply_volume_and_read_payload(chain, data)

    assert payload.hex() == EXPECTED_TAS30_BY_DATA[data]

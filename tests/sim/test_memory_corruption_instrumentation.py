from __future__ import annotations

from hashlib import sha256

import pytest

from dlcp_fw.paths import V35_MAIN_HEX
from tests.sim.memory_corruption_helpers import (
    CONTROL_FNAME_EXPECTED_LEN,
    CONTROL_FNAME_FLAGS,
    CONTROL_FNAME_LEN,
    CONTROL_FNAME_RENDER_COL,
    CONTROL_FNAME_RENDER_OFF,
    CONTROL_PRESET_EEPROM,
    FILENAME_LEN,
    MAIN_HID_STATE_BASE,
    MAIN_HID_STATE_END,
    MAIN_INPUT_SELECT,
    MAIN_INPUT_SELECT_MIRROR,
    MAIN_RX_RING_RD,
    MAIN_RX_RING_SIZE,
    MAIN_RX_RING_WR,
    MAIN_ROUTE_SHADOW,
    MAIN_SETTINGS_EEPROM_LAST,
    MAIN_SRC_ROUTE_REQUEST,
    MAIN_USB_EP1_IN_BASE,
    MAIN_USB_EP1_IN_END,
    MAIN_USB_EP1_OUT_BASE,
    MAIN_USB_EP1_OUT_END,
    MAIN_V35_ASM,
    PRESET_A_EEPROM_BASE,
    PRESET_B_EEPROM_BASE,
    PRESET_JOB_END,
    PRESET_JOB_INDEX,
    PRESET_JOB_STATE,
    PRESET_JOB_TARGET,
    assert_trace_clean,
    assert_no_protected_memory_writes,
    control_filename_cache_watches,
    control_preset_eeprom_watches,
    firmware_path_repair_all_filename_slots,
    main_filename_eeprom_watches,
    main_filename_ram_watches,
    main_preset_job_watches,
    main_range_watches,
    main_route_state_watches,
    main_rx_ring_watches,
    protected_filename_watches,
    read_eeprom_slot,
    run_direct_main_rx_stimulus,
    run_live_like_churn,
    run_main_route_churn,
    run_preset_toggle_churn,
    run_usb_hid_readonly_churn,
    single_byte_eeprom_watch,
    slot,
    start_v173_v35_single_main,
    start_v173_v35_chain,
    start_v35_main_only,
    wait_preset_jobs_idle,
)

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc


pytestmark = pytest.mark.dual_supported


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


def _baseline_watches() -> list[dict[str, object]]:
    watches = []
    for watch in protected_filename_watches():
        item = dict(watch)
        item["protected"] = False
        item["fail_on_write"] = False
        item["stop_on_write"] = False
        watches.append(item)
    return watches


def _seeded_chain() -> tuple[object, bytes, bytes]:
    chain = start_v173_v35_chain()
    assert chain.main0 != chain.main1
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b)
    return chain, slot_a, slot_b


def _assert_filename_slots(chain, slot_a: bytes, slot_b: bytes) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        assert read_eeprom_slot(chain, unit, PRESET_A_EEPROM_BASE) == slot_a
        assert read_eeprom_slot(chain, unit, PRESET_B_EEPROM_BASE) == slot_b


def _biquad_image(chain, unit: int) -> bytes:  # type: ignore[no-untyped-def]
    return bytes(chain.read_main_dsp_reg(unit, subaddr) for subaddr in range(0x37, 0x91))


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()[:12]


def _strip_asm_comments(text: str) -> str:
    return "\n".join(line.split(";", 1)[0].rstrip() for line in text.splitlines())


def test_memory_trace_captures_firmware_eeprom_arm_and_commit() -> None:
    _require_rust()
    chain = start_v35_main_only()
    payload = slot("LX521.4 22MG10-vB")
    watched_addr = PRESET_B_EEPROM_BASE + 0x0C
    expected_byte = payload[watched_addr - PRESET_B_EEPROM_BASE]

    chain.begin_memory_trace(single_byte_eeprom_watch(addr=watched_addr), max_records=200)
    firmware_path_repair_all_filename_slots(chain, payload, payload, units=(0,))

    records = chain.memory_trace_records()
    watched = [record for record in records if record["addr"] == watched_addr]
    assert any(record["kind"] == "EepromArm" for record in watched)
    assert any(
        record["kind"] == "EepromCommit" and record["new"] == expected_byte
        for record in watched
    )
    commit = next(record for record in watched if record["kind"] == "EepromCommit")
    assert commit["role"] == "MAIN0"
    assert commit["arm"] is not None
    assert commit["arm"]["eeadr"] == watched_addr
    assert commit["cpu"]["fsr2"] <= 0x0FFF


def test_memory_trace_distinguishes_main1_host_eeprom_seed() -> None:
    _require_rust()
    chain = start_v173_v35_chain()
    assert chain.main0 != chain.main1
    watched_addr = PRESET_B_EEPROM_BASE + 0x0C

    chain.begin_memory_trace(
        single_byte_eeprom_watch(role="MAIN1", addr=watched_addr),
        max_records=20,
    )
    chain.write_main_eeprom_byte(1, watched_addr, 0x00)

    records = chain.memory_trace_records()
    assert len(records) == 1
    assert records[0]["role"] == "MAIN1"
    assert records[0]["kind"] == "HostEepromSeed"
    assert records[0]["space"] == "Eeprom"
    assert records[0]["addr"] == watched_addr


def test_v173_v35_baseline_writes_use_firmware_paths_for_both_mains() -> None:
    _require_rust()
    chain = start_v173_v35_chain()
    assert chain.main0 != chain.main1
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    watched_addr = PRESET_B_EEPROM_BASE + 0x0C

    chain.begin_memory_trace(_baseline_watches(), max_records=5_000)
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b)

    records = chain.memory_trace_records()
    for role in ("MAIN0", "MAIN1"):
        role_records = [
            record
            for record in records
            if record["role"] == role and record["space"] == "Eeprom"
        ]
        assert any(
            record["kind"] == "EepromArm"
            and record["addr"] == watched_addr
            and record["new"] == ord("1")
            for record in role_records
        )
        assert any(
            record["kind"] == "EepromCommit"
            and record["addr"] == watched_addr
            and record["new"] == ord("1")
            for record in role_records
        )

    for unit in (0, 1):
        assert read_eeprom_slot(chain, unit, PRESET_B_EEPROM_BASE) == slot_b

    chain.clear_memory_trace()
    summary = chain.memory_trace_summary()
    assert summary["total_count"] == 0
    assert summary["record_count"] == 0
    assert chain.memory_trace_first_violation() is None


def test_v173_v35_live_like_churn_keeps_preset_b_eeprom_clean() -> None:
    _require_rust()
    chain = start_v173_v35_chain()
    assert chain.main0 != chain.main1
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b)

    chain.begin_memory_trace(protected_filename_watches(), max_records=10_000)
    stimuli = run_live_like_churn(chain)

    assert any(
        item.phase == "preset-query"
        and item.action == "inject_main_frames_fifo"
        and item.params.get("frames") == [[0xB1, 0x26, 0x01]]
        for item in stimuli
    )
    query_observation = next(
        item for item in stimuli if item.phase == "preset-query" and item.action == "observe_uart"
    )
    tx_pairs = set(query_observation.params["tx_pairs_after_query"])
    assert "BF/2D" in tx_pairs
    assert "BF/30" in tx_pairs
    assert "BF/4E" in tx_pairs
    summary = chain.memory_trace_summary()
    assert not summary["overflowed"]
    assert summary["dropped_count"] == 0

    violation = chain.memory_trace_first_violation()
    assert violation is None

    for unit in (0, 1):
        assert read_eeprom_slot(chain, unit, PRESET_B_EEPROM_BASE) == slot_b


def test_v173_v35_filename_eeprom_guard_rejects_runtime_writes_after_repair() -> None:
    _require_rust()
    chain = start_v173_v35_chain()
    assert chain.main0 != chain.main1
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b)

    assert_no_protected_memory_writes(
        chain,
        run_live_like_churn,
        watches=protected_filename_watches(),
        scenario="v173-v35-filename-eeprom-clean-gate",
        seed=0x35_0173,
        max_records=10_000,
    )


def test_v173_v35_filename_guards_cover_preset_a_b_eeprom_slots() -> None:
    _require_rust()
    chain, slot_a, slot_b = _seeded_chain()

    watches = (
        main_filename_eeprom_watches(slots=("a", "b"))
        + main_filename_ram_watches()
        + main_preset_job_watches()
    )
    chain.begin_memory_trace(watches, max_records=20_000)
    run_live_like_churn(chain)

    assert_trace_clean(chain)
    _assert_filename_slots(chain, slot_a, slot_b)


def test_v173_v35_preset_job_block_stays_bounded_under_ab_churn() -> None:
    _require_rust()
    chain, slot_a, slot_b = _seeded_chain()

    watches = main_preset_job_watches() + main_filename_eeprom_watches(slots=("a", "b"))
    chain.begin_memory_trace(watches, max_records=20_000)
    run_preset_toggle_churn(chain)

    assert_trace_clean(chain)
    for unit in (0, 1):
        assert chain.read_main_reg(unit, PRESET_JOB_STATE) == 0
        assert chain.read_main_reg(unit, PRESET_JOB_TARGET) in (0, 1)
        assert 0 <= chain.read_main_reg(unit, PRESET_JOB_INDEX) <= 0xFF
    records = chain.memory_trace_records()
    assert any(
        record["role"] in ("MAIN0", "MAIN1")
        and record["space"] == "DataRam"
        and PRESET_JOB_STATE <= record["addr"] <= PRESET_JOB_END
        for record in records
    )
    _assert_filename_slots(chain, slot_a, slot_b)


def test_v35_rx_ring_raw_byte_stress_cannot_overrun_into_upper_bank2_state() -> None:
    _require_rust()
    chain = start_v35_main_only()
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b, units=(0,))

    watches = (
        main_rx_ring_watches(units=(0,))
        + main_filename_ram_watches(units=(0,), protected=True)
        + main_preset_job_watches(units=(0,), protected=True)
    )
    chain.begin_memory_trace(watches, max_records=20_000)
    for burst in (
        [0x00] * 96,
        [0xFF, 0xBF, 0x7F] * 32,
        [0xB0, 0x06, 0x05] * 24,
        [0xB1, 0x26] * 36,
    ):
        accepted, dropped = chain.inject_main_uart_rx_bytes(0, burst)
        assert accepted + dropped == len(burst)
        chain.step_ticks(30_000_000)

    assert_trace_clean(chain)
    assert 0 <= chain.read_main_reg(0, MAIN_RX_RING_RD) < MAIN_RX_RING_SIZE
    assert 0 <= chain.read_main_reg(0, MAIN_RX_RING_WR) < MAIN_RX_RING_SIZE
    assert read_eeprom_slot(chain, 0, PRESET_A_EEPROM_BASE) == slot_a
    assert read_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b


def test_v173_control_preset_persistence_writes_only_eeprom_0x74() -> None:
    _require_rust()
    chain = start_v173_v35_chain()

    chain.begin_memory_trace(control_preset_eeprom_watches(), max_records=200)
    run_preset_toggle_churn(chain)

    assert_trace_clean(chain)
    records = chain.memory_trace_records()
    eeprom_records = [
        record
        for record in records
        if record["role"] == "CONTROL" and record["space"] == "Eeprom"
    ]
    assert eeprom_records
    assert {record["addr"] for record in eeprom_records} == {CONTROL_PRESET_EEPROM}
    assert {record["new"] for record in eeprom_records if record["kind"] == "EepromCommit"} <= {
        0,
        1,
    }


def test_v173_control_filename_cache_writes_stay_inside_reserved_window() -> None:
    _require_rust()
    chain, _slot_a, _slot_b = _seeded_chain()

    watches = control_filename_cache_watches()
    chain.begin_memory_trace(watches, max_records=100_000)
    chain.press("RIGHT")
    chain.step_ticks(260_000_000)
    chain.inject_decoded_ir_event(addr=0x10, cmd=0x34)
    chain.step_ticks(20_000_000)

    assert_trace_clean(chain)
    assert chain.read_reg(CONTROL_FNAME_LEN) <= FILENAME_LEN
    assert chain.read_reg(CONTROL_FNAME_EXPECTED_LEN) <= FILENAME_LEN
    assert chain.read_reg(CONTROL_FNAME_RENDER_COL) <= 0x10
    assert chain.read_reg(CONTROL_FNAME_RENDER_OFF) <= FILENAME_LEN
    assert chain.read_reg(CONTROL_FNAME_FLAGS) <= 0xFF


def test_v35_settings_persist_does_not_touch_filename_or_reserved_eeprom() -> None:
    _require_rust()
    chain, slot_a, slot_b = _seeded_chain()

    protected_eeprom = []
    protected_eeprom.extend(
        main_range_watches(
            MAIN_SETTINGS_EEPROM_LAST + 1,
            PRESET_A_EEPROM_BASE - 1,
            "settings_eeprom_gap_before_names",
            space="Eeprom",
            protected=True,
        )
    )
    protected_eeprom.extend(main_filename_eeprom_watches(slots=("a", "b")))
    protected_eeprom.extend(
        main_range_watches(
            PRESET_A_EEPROM_BASE + FILENAME_LEN,
            PRESET_B_EEPROM_BASE - 1,
            "settings_eeprom_gap_between_names",
            space="Eeprom",
            protected=True,
        )
    )
    protected_eeprom.extend(
        main_range_watches(
            PRESET_B_EEPROM_BASE + FILENAME_LEN,
            0xBF,
            "settings_eeprom_gap_after_names",
            space="Eeprom",
            protected=True,
        )
    )
    chain.begin_memory_trace(protected_eeprom, max_records=10_000)

    chain.inject_decoded_ir_event(addr=0x10, cmd=0x34)
    chain.step_ticks(50_000_000)
    run_main_route_churn(chain)
    report = bytearray(64)
    report[0] = 0x05
    report[1] = 0x05
    report[5:9] = bytes([0xFF, 0xFF, 0xFF, 0xF0])
    chain.firmware_hid_report(0, report, max_steps=120_000)
    chain.step_ticks(20_000_000)

    assert_trace_clean(chain)
    _assert_filename_slots(chain, slot_a, slot_b)


def test_v35_src_route_churn_keeps_route_state_in_bounds() -> None:
    _require_rust()
    chain, slot_a, slot_b = _seeded_chain()

    watches = main_route_state_watches() + main_filename_eeprom_watches(slots=("a", "b"))
    chain.begin_memory_trace(watches, max_records=20_000)
    run_main_route_churn(chain)
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, 0x13, 0x03)
        chain.poke_main_src4382_reg(unit, 0x12, 0x00)
    chain.step_ticks(80_000_000)
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, 0x13, 0x00)
    chain.step_ticks(80_000_000)

    assert_trace_clean(chain)
    for unit in (0, 1):
        assert 0 <= chain.read_main_reg(unit, MAIN_SRC_ROUTE_REQUEST) <= 7
        assert 0 <= chain.read_main_reg(unit, MAIN_ROUTE_SHADOW) <= 7
        assert 0 <= chain.read_main_reg(unit, MAIN_INPUT_SELECT) <= 8
        assert 0 <= chain.read_main_reg(unit, MAIN_INPUT_SELECT_MIRROR) <= 8
    _assert_filename_slots(chain, slot_a, slot_b)


def test_v35_tas3108_preset_apply_does_not_mutate_filename_storage() -> None:
    _require_rust()
    chain, slot_a, slot_b = _seeded_chain()
    initial_images = tuple(_biquad_image(chain, unit) for unit in (0, 1))
    for unit in (0, 1):
        chain.reset_main_dsp_write_log(unit)

    watches = (
        main_filename_eeprom_watches(slots=("a", "b"))
        + main_filename_ram_watches()
        + main_preset_job_watches()
    )
    chain.begin_memory_trace(watches, max_records=40_000)
    run_preset_toggle_churn(chain)
    wait_preset_jobs_idle(chain)

    assert_trace_clean(chain)
    final_images = tuple(_biquad_image(chain, unit) for unit in (0, 1))
    assert final_images == initial_images, (
        tuple(_digest(image) for image in initial_images),
        tuple(_digest(image) for image in final_images),
    )
    for unit in (0, 1):
        assert any(
            chain.read_main_dsp_write_payloads(unit, subaddr)
            for subaddr in range(0x37, 0x91)
        )
    _assert_filename_slots(chain, slot_a, slot_b)


def test_v35_usb_hid_readonly_diagnostics_do_not_persist_or_escape_buffers() -> None:
    _require_rust()
    chain = start_v35_main_only()
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b, units=(0,))

    watches = (
        main_filename_eeprom_watches(slots=("a", "b"), units=(0,))
        + main_range_watches(
            MAIN_USB_EP1_OUT_BASE,
            MAIN_USB_EP1_OUT_END,
            "usb_ep1_out",
            units=(0,),
        )
        + main_range_watches(
            MAIN_USB_EP1_IN_BASE,
            MAIN_USB_EP1_IN_END,
            "usb_ep1_in",
            units=(0,),
        )
        + main_range_watches(
            MAIN_HID_STATE_BASE,
            MAIN_HID_STATE_END,
            "hid_dispatch_state",
            units=(0,),
        )
    )
    chain.begin_memory_trace(watches, max_records=30_000)
    run_usb_hid_readonly_churn(chain, unit=0)

    assert_trace_clean(chain)
    assert read_eeprom_slot(chain, 0, PRESET_A_EEPROM_BASE) == slot_a
    assert read_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b


def test_v35_eeprom_walker_keeps_live_tblptr_away_from_chain_copy_helpers() -> None:
    text = MAIN_V35_ASM.read_text()
    start = text.index("eeprom_persist_block_walker:")
    end = text.index("eeprom_persist_static_records:")
    code = _strip_asm_comments(text[start:end])

    assert "eeprom_persist_static_record_write_if_changed:" in code
    assert "call        eeprom_read_byte" in code
    assert "goto        eeprom_write_blocking" in code
    assert "chain_copy" not in code
    assert "eeprom_write_byte_if_changed" not in code


def test_main_only_direct_rx_isolation_does_not_recur() -> None:
    _require_rust()
    chain = start_v35_main_only()
    assert chain.main0 == chain.main1
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b, units=(0,))

    chain.begin_memory_trace(protected_filename_watches(), max_records=1_000)
    run_direct_main_rx_stimulus(chain, unit=0)

    summary = chain.memory_trace_summary()
    assert not summary["overflowed"]
    assert summary["dropped_count"] == 0
    assert chain.memory_trace_first_violation() is None
    assert read_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b
    assert read_eeprom_slot(chain, 1, PRESET_B_EEPROM_BASE) == slot_b


def test_control_single_main_direct_rx_isolation_does_not_recur() -> None:
    _require_rust()
    chain = start_v173_v35_single_main()
    assert chain.main0 == chain.main1
    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b, units=(0,))

    chain.begin_memory_trace(protected_filename_watches(), max_records=1_500)
    run_direct_main_rx_stimulus(chain, unit=0)

    summary = chain.memory_trace_summary()
    assert not summary["overflowed"]
    assert summary["dropped_count"] == 0
    assert chain.memory_trace_first_violation() is None
    assert read_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b
    assert read_eeprom_slot(chain, 1, PRESET_B_EEPROM_BASE) == slot_b


def test_memory_trace_api_rejects_empty_watches() -> None:
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(V35_MAIN_HEX))
    with pytest.raises(ValueError, match="at least one watch"):
        chain.begin_memory_trace([])

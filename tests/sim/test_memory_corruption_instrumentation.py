from __future__ import annotations

import pytest

from dlcp_fw.paths import V35_MAIN_HEX
from tests.sim.memory_corruption_helpers import (
    PRESET_B_EEPROM_BASE,
    assert_no_protected_memory_writes,
    firmware_path_repair_all_filename_slots,
    protected_filename_watches,
    read_eeprom_slot,
    run_direct_main_rx_stimulus,
    run_live_like_churn,
    single_byte_eeprom_watch,
    slot,
    start_v173_v35_single_main,
    start_v173_v35_chain,
    start_v35_main_only,
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


def test_v173_v35_live_like_churn_reproduces_preset_b_0x8f_nul() -> None:
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
    assert violation is not None
    assert violation["role"] == "MAIN0"
    assert violation["kind"] == "EepromArm"
    assert violation["addr"] == PRESET_B_EEPROM_BASE + 0x0C
    assert violation["old"] == ord("1")
    assert violation["new"] == 0x00
    assert violation["arm"]["eeadr"] == PRESET_B_EEPROM_BASE + 0x0C
    assert violation["arm"]["eedata"] == 0x00
    assert violation["pc"] == 0x3984  # nvm_unlock_and_set_wr: bsf EECON1.WR
    assert violation["cpu"]["tos"] == 0x396A  # eeprom_write_blocking wait loop
    assert violation["cpu"]["stack"] == [
        0x3E30,  # run_main_foreground_loop after run_main_service_pass
        0x3D28,  # run_main_service_pass after persist_dirty_runtime_state_to_eeprom
        0x20A6,  # persist_dirty_runtime_state_to_eeprom after block-0 walker call
        0x210E,  # eeprom_persist_block_walker record tail
        0x396A,  # eeprom_write_blocking wait loop
    ]
    assert any(
        item.phase == "menu"
        and item.action == "press"
        and item.params.get("key") == "RIGHT"
        and item.tick_before <= violation["tick"] <= item.tick_after
        for item in stimuli
    )

    for unit in (0, 1):
        observed = read_eeprom_slot(chain, unit, PRESET_B_EEPROM_BASE)
        assert observed[0x0C] == 0x00
        assert observed != slot_b


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

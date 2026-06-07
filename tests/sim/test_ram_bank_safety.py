from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dlcp_fw.analysis import ram_bank_safety as rbs
from dlcp_fw.asm.ram_bank_manifest import load_manifest


def _codes(findings: list[rbs.Finding]) -> set[str]:
    return {finding.code for finding in findings}


def test_current_targets_pass_ram_bank_safety_checker() -> None:
    assert rbs.check_targets(["main-v33", "control-v172"]) == []


def test_raw_ram_symbol_operand_fails() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    movwf   ram_0x0A1, BANKED
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_RAW_SYMBOL" in _codes(findings)


def test_raw_numeric_ram_operand_fails_but_sfr_numeric_is_allowed() -> None:
    ram_findings = rbs.check_source_text(
        "control-v172",
        """
test:
    movwf   0x40, BANKED       ; reg: 0x240
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_RAW_NUMERIC" in _codes(ram_findings)

    sfr_findings = rbs.check_source_text(
        "control-v172",
        """
test:
    btg     0x69, 0x2, A       ; reg: 0xf69
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_RAW_NUMERIC" not in _codes(sfr_findings)


def test_strict_bsr_fixture_accepts_matching_movlb() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x02
    movf    fn_job_idx_b2, W, BANKED
""",
        path=Path("fixture.asm"),
    )
    assert findings == []


def test_strict_bsr_fixture_rejects_mismatch_and_indeterminate() -> None:
    mismatch = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x00
    movf    fn_job_idx_b2, W, BANKED
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_MISMATCH" in _codes(mismatch)

    indeterminate = rbs.check_source_text(
        "main-v33",
        """
test:
    call    helper, 0x0
    movf    fn_job_idx_b2, W, BANKED
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_INDETERMINATE" in _codes(indeterminate)


def test_cfg_branch_targets_prove_bank_state() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x02
    bnz     use_bank2
    movlb   0x02
use_bank2:
    movf    fn_job_idx_b2, W, BANKED
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert findings == []


def test_cfg_merge_with_multiple_banks_is_indeterminate() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    btfss   STATUS, 0, ACCESS
    bra     bank2
    movlb   0x00
    bra     use_bank2
bank2:
    movlb   0x02
use_bank2:
    movf    fn_job_idx_b2, W, BANKED
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_INDETERMINATE" in _codes(findings)


def test_internal_calls_are_summarized_but_external_calls_clobber_bsr() -> None:
    internal = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x02
    call    preserve, 0x0
    movf    fn_job_idx_b2, W, BANKED
    return  0
preserve:
    btfss   STATUS, 0, ACCESS
    return  0
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert internal == []

    external = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x02
    call    external_helper, 0x0
    movf    fn_job_idx_b2, W, BANKED
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_INDETERMINATE" in _codes(external)


def test_routine_contracts_can_prove_numeric_and_preserved_exits() -> None:
    numeric = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x00
    call    force_bank2, 0x0
    movf    fn_job_idx_b2, W, BANKED
    return  0
;@routine force_bank2 entry_bsr=unknown exit_bsr=2
force_bank2:
    movlb   0x02
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert numeric == []

    preserved = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x02
    call    preserve_bsr, 0x0
    movf    fn_job_idx_b2, W, BANKED
    return  0
;@routine preserve_bsr entry_bsr=unknown exit_bsr=preserve
preserve_bsr:
    btfsc   STATUS, 0, ACCESS
    return  0
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert preserved == []


def test_routine_contract_entry_and_exit_mismatches_fail() -> None:
    entry_mismatch = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x00
    call    needs_bank1, 0x0
    return  0
;@routine needs_bank1 entry_bsr=1 exit_bsr=1
needs_bank1:
    movlb   0x01
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_CONTRACT_ENTRY_MISMATCH" in _codes(entry_mismatch)

    exit_mismatch = rbs.check_source_text(
        "main-v33",
        """
test:
    call    lies_about_exit, 0x0
    return  0
;@routine lies_about_exit entry_bsr=unknown exit_bsr=2
lies_about_exit:
    movlb   0x00
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_CONTRACT_EXIT_MISMATCH" in _codes(exit_mismatch)


def test_recursive_routine_contract_is_assumed_on_active_edge_and_verified() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    call    recursive_force_bank0, 0x0
    movf    an0_delay_b0, W, BANKED
    return  0
;@routine recursive_force_bank0 entry_bsr=unknown exit_bsr=0
recursive_force_bank0:
    movlb   0x00
    btfsc   STATUS, 0, ACCESS
    rcall   recursive_force_bank0
    movlb   0x00
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert findings == []


def test_labeled_unreachable_banked_access_fails_closed() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    return  0
dead_banked_access:
    movf    fn_job_idx_b2, W, BANKED
    return  0
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_UNREACHED" in _codes(findings)


def test_known_an0_delay_bug_shape_fails_without_bsr0() -> None:
    findings = rbs.check_source_text(
        "main-v33",
        """
test:
    movlb   0x02
    incf    an0_delay_b0, F, BANKED
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_BSR_MISMATCH" in _codes(findings)


def test_movff_and_lfsr_require_physical_aliases() -> None:
    bad = rbs.check_source_text(
        "main-v33",
        """
test:
    movff   fn_job_idx_b2, stock_003_b0_phys
    lfsr    FSR2, fn_job_idx_b2
""",
        path=Path("fixture.asm"),
    )
    codes = _codes(bad)
    assert "RAM_MOVFF_NEEDS_PHYS" in codes
    assert "RAM_LFSR_NEEDS_PHYS" in codes

    good = rbs.check_source_text(
        "main-v33",
        """
test:
    movff   fn_job_idx_b2_phys, stock_003_b0_phys
    lfsr    FSR2, fn_job_idx_b2_phys
""",
        path=Path("fixture.asm"),
    )
    assert "RAM_MOVFF_NEEDS_PHYS" not in _codes(good)
    assert "RAM_LFSR_NEEDS_PHYS" not in _codes(good)


def test_manifest_duplicate_physical_address_fails_without_alias(monkeypatch) -> None:
    original = load_manifest("main-v33")["fn_job_idx_b2"]
    duplicate = replace(original, source_name="duplicate_owner", alias="duplicate_b2", owner="duplicate_owner")

    def fake_manifest(target: str):
        assert target == "main-v33"
        return {
            original.alias: original,
            duplicate.alias: duplicate,
        }

    monkeypatch.setattr(rbs, "load_manifest", fake_manifest)
    findings = rbs.check_manifest_collisions("main-v33")
    assert "RAM_PHYS_COLLISION" in _codes(findings)

"""Coverage manifest for docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md.

This test is intentionally static: it fails when a required user-visible
diagnostics row loses its real-stimulus PB1/PB2 test, is hidden behind xfail,
or is reduced back to source/render-only coverage.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_DOC = ROOT / "docs" / "V171_V32_DIAG_FAULT_INJECTION_MATRIX.md"
IMPL_DOC = ROOT / "docs" / "IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md"
CHAIN_TEST = ROOT / "tests" / "sim" / "test_v171_v32_layer5_diag_chain.py"


REQUIRED_TESTS = {
    "stale_pending_static_pb_pages": {
        "name": "test_v171_v32_diag_entry_clears_stale_pending_timeout_state",
        "params": ("pb_idx,pending_target",),
        "requires": ("V171_DIAG_FLAG_RUNTIME_PENDING_MASK", "V171_DIAG_FLAG_RESET_PENDING_MASK"),
    },
    "I_src4382": {
        "name": "test_v171_v32_diag_lcd_surfaces_injected_src4382_i2c_fault",
        "params": ("unit,pb_label", "fault_kind"),
        "requires": (
            "inject_main_src4382_address_nack",
            "inject_main_src4382_data_nack",
            "address_nacks_consumed",
            "data_nacks_consumed",
            "_assert_diag_deltas_allowed",
            "_assert_diag_cache_value",
            "_assert_lcd_diag_token",
        ),
    },
    "S_B_events": {
        "name": "test_v171_v32_diag_lcd_surfaces_standby_wake_event_counters",
        "params": ("pb_idx,pb_label",),
        "requires": (
            "before_blocks",
            "_assert_diag_deltas_allowed",
            "_assert_diag_cache_value",
            "_assert_lcd_diag_token",
        ),
    },
    "D_tas3108": {
        "name": "test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode",
        "params": ("unit,pb_label",),
        "requires": ("address_nacks_consumed", "_assert_diag_cache_value", "_assert_lcd_diag_token"),
    },
    "R_volume": {
        "name": "test_v171_v32_diag_lcd_surfaces_volume_dsp_recovery_counter",
        "params": ("unit,pb_label",),
        "requires": ("_assert_diag_deltas_allowed", "_assert_diag_cache_value", "_assert_lcd_diag_token"),
    },
    "R_bounded_timeout": {
        "name": "test_v171_v32_diag_lcd_surfaces_bounded_i2c_timeout_recovery_counter",
        "params": ("unit,pb_label",),
        "requires": ("set_main_mssp_stop_fault", "_assert_diag_cache_value", "_assert_lcd_diag_token"),
    },
    "A_an0": {
        "name": "test_v171_v32_diag_lcd_surfaces_an0_standby_trigger",
        "params": ("unit,pb_label",),
        "requires": ("set_main_an0_sample", "_assert_diag_deltas_allowed", "_assert_lcd_diag_token"),
    },
    "P_ra1": {
        "name": "test_v171_v32_diag_lcd_surfaces_ra1_edge_counter",
        "params": ("unit,pb_label",),
        "requires": ("set_main_pin", "steady_p", "_assert_diag_deltas_allowed", "_assert_lcd_diag_token"),
    },
    "O_V_W_X_reset": {
        "name": "test_v171_v32_diag_lcd_surfaces_reset_cause_flags",
        "params": ("source,label,offset", "pb_idx,pb_label"),
        "requires": (
            "sources_by_unit",
            "mark_ctl_tx_capture_point",
            "mark_ctl_rx_capture_point",
            "0x22",
            "expected_reply",
            "_assert_diag_cache_value",
            "_assert_lcd_diag_token",
        ),
    },
}


def _function_spans(source: str) -> dict[str, str]:
    lines = source.splitlines()
    tree = ast.parse(source)
    spans: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        first = node.lineno
        if node.decorator_list:
            first = min(decorator.lineno for decorator in node.decorator_list)
        assert node.end_lineno is not None
        spans[node.name] = "\n".join(lines[first - 1:node.end_lineno])
    return spans


def _function_nodes(source: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(source)
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def test_diag_fault_matrix_manifest_required_tests_exist_and_are_active() -> None:
    assert MATRIX_DOC.exists(), f"missing matrix doc: {MATRIX_DOC}"
    assert IMPL_DOC.exists(), f"missing implementation doc: {IMPL_DOC}"
    source = CHAIN_TEST.read_text(encoding="utf-8")
    spans = _function_spans(source)
    functions = _function_nodes(source)

    missing = [
        spec["name"] for spec in REQUIRED_TESTS.values()
        if spec["name"] not in functions
    ]
    assert not missing, f"missing required diag fault-matrix tests: {missing}"

    for row, spec in REQUIRED_TESTS.items():
        name = spec["name"]
        span = spans[name]
        decorator_text = "\n".join(ast.unparse(d) for d in functions[name].decorator_list)
        assert "xfail" not in decorator_text, f"{row} coverage is xfailed: {name}"
        assert "skip" not in decorator_text, f"{row} coverage is skipped: {name}"
        assert "pytest.skip" not in span, f"{row} coverage contains an in-test skip: {name}"
        assert "_rust_set_main_diag_block" not in span, (
            f"{row} coverage must not seed MAIN diag RAM directly: {name}"
        )
        for param_signature in spec["params"]:
            assert param_signature in span, (
                f"{row} coverage does not advertise required parametrization "
                f"{param_signature!r}: {name}"
            )
        for required_text in spec["requires"]:
            assert required_text in span, (
                f"{row} coverage is missing required proof hook "
                f"{required_text!r}: {name}"
            )


def test_diag_fault_matrix_docs_keep_runtime_and_reset_transports_separate() -> None:
    matrix = MATRIX_DOC.read_text(encoding="utf-8")
    assert "cmd 0x21" in matrix and "BF/21..BF/27" in matrix, (
        "runtime counter transport must remain explicit in the matrix"
    )
    assert "cmd 0x22" in matrix and "BF/28..BF/2B" in matrix, (
        "reset-cause transport must remain explicit in the matrix"
    )
    assert "source hooks only" not in matrix.lower(), (
        "matrix must not claim source-hook-only coverage is sufficient"
    )

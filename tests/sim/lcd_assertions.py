"""Focused LCD assertion helpers for simulator tests."""

from __future__ import annotations

from typing import Callable, Protocol


class LcdReadable(Protocol):
    def lcd_lines(self) -> tuple[str, str]:
        ...


def _validate_row_pair(rows: tuple[str, str], *, label: str) -> None:
    assert len(rows) == 2, f"{label} must contain exactly two LCD rows: {rows!r}"
    for idx, row in enumerate(rows):
        assert len(row) == 16, (
            f"{label} row {idx} must be exactly 16 chars, got "
            f"{len(row)}: {row!r}"
        )


def assert_lcd_exact(
    lcd: LcdReadable | tuple[str, str],
    expected: tuple[str, str],
    *,
    context: str = "",
) -> tuple[str, str]:
    """Assert an exact 16x2 LCD snapshot and return the actual rows."""
    _validate_row_pair(expected, label="expected LCD")
    actual = lcd.lcd_lines() if hasattr(lcd, "lcd_lines") else lcd
    _validate_row_pair(actual, label="actual LCD")
    assert actual == expected, (
        f"LCD mismatch{f' ({context})' if context else ''}: "
        f"expected={expected!r} actual={actual!r}"
    )
    return actual


def wait_for_lcd_exact(
    chain: LcdReadable,
    expected: tuple[str, str],
    *,
    limit: int = 700,
    context: str = "",
    step: Callable[[], None] | None = None,
) -> tuple[str, str]:
    """Step until the simulator reaches an exact 16x2 LCD snapshot."""
    _validate_row_pair(expected, label="expected LCD")
    step_fn = step if step is not None else chain.step  # type: ignore[attr-defined]
    actual = chain.lcd_lines()
    for _ in range(limit):
        actual = chain.lcd_lines()
        _validate_row_pair(actual, label="actual LCD")
        if actual == expected:
            return actual
        step_fn()
    assert False, (
        f"LCD did not converge{f' ({context})' if context else ''}: "
        f"expected={expected!r} actual={actual!r}"
    )


def assert_lcd_row0_prefix_allowed(
    lcd: LcdReadable | tuple[str, str],
    prefix: str,
    *,
    reason: str,
    context: str = "",
) -> tuple[str, str]:
    """Document an intentional dynamic-row exception for a row-0 prefix check."""
    assert reason.strip(), "dynamic LCD prefix checks must provide a reason"
    actual = lcd.lcd_lines() if hasattr(lcd, "lcd_lines") else lcd
    _validate_row_pair(actual, label="actual LCD")
    assert actual[0].startswith(prefix), (
        f"LCD row 0 prefix mismatch{f' ({context})' if context else ''}: "
        f"prefix={prefix!r} actual={actual!r}; reason={reason}"
    )
    return actual

#!/usr/bin/env python3
"""Convert stock CONTROL V1.6b hex into a gpasm-compatible source (V1.7).

Pipeline
--------
1. Invoke ``gpdasm -p 18f25k20 -s -n`` on the stock V1.6b hex.  This already
   emits a compilable assembly source whose code, config-as-``db``, and
   EEPROM regions round-trip byte-identical through gpasm.
2. Post-process the output to:
     - add a ``dlcp_control_ram.inc`` include,
     - rewrite bank-0 access-bank GPR references to the named equates from
       that include (optional; ``--with-ram-equates``),
     - optionally rename auto-generated labels to the semantic names
       curated in ``firmware/disasm/control/v16b.asm``
       (``--with-semantic-names``),
     - optionally insert function-header banners from the same reference
       (``--with-function-headers``).

The V1.7 byte-identical build uses the raw gpdasm output plus the RAM
include.  The V1.7 ``_comments`` canonical source enables the semantic
name + header passes.

Usage
-----
    scripts/convert_v16b_asm_to_gpasm.py \
        --output src/dlcp_fw/asm/dlcp_control_v17.asm

    scripts/convert_v16b_asm_to_gpasm.py \
        --with-ram-equates --with-semantic-names --with-function-headers \
        --output src/dlcp_fw/asm/dlcp_control_v17_comments.asm
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
STOCK_HEX = REPO_ROOT / "firmware" / "stock" / "control" / "DLCP Control Firmware V1.6b.hex"
V16B_REFERENCE = REPO_ROOT / "firmware" / "disasm" / "control" / "v16b.asm"
RAM_INC_NAME = "dlcp_control_ram.inc"

# ---------------------------------------------------------------------------
# Immediate-value annotation table (spec §B2 / C2)
# ---------------------------------------------------------------------------
#
# Maps recognized CONTROL literal constants to a short human-readable
# label.  The annotation pass appends ``  ; <meaning>`` after the
# instruction (only when no meaningful comment already exists), letting
# readers of the commented source understand why a particular byte
# appears without having to cross-reference the protocol table.
#
# Categories (priority order per spec §B2):
#   CMD   — CONTROL→MAIN serial command byte
#   ROUTE — route byte (broadcast, addressed, or return)
#   RC5   — IR RC5 command code
#   SFR   — SFR config write (BAUDCON/etc.)
#
# The table is intentionally conservative: only literals whose meaning
# is fully determined by their value (i.e. not context-dependent) get
# annotated.  A ``movlw 0x03`` in a different context may not be a
# serial command byte, so the annotator only touches lines whose
# context (nearby movwf / call) fits the category's footprint.

_CMD_VALUES: Dict[int, str] = {
    0x03: "CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)",
    0x04: "CMD status_poll",
    0x05: "CMD raw_status (MAIN→CONTROL echo)",
    0x06: "CMD input_select",
    0x07: "CMD volume (offset 0x60)",
    0x08: "CMD dsp_fault (V1.63b+ BF/08 payload)",
    0x17: "CMD channel_src_1",
    0x18: "CMD channel_src_2 / power_on_notify (on BF return)",
    0x19: "CMD channel_src_3",
    0x1A: "CMD channel_src_4",
    0x1B: "CMD channel_src_5",
    0x1C: "CMD channel_src_6",
    0x1D: "CMD shared_cmd1d_setting (BL timeout / profile)",
    0x1E: "CMD link_address",
    0x20: "CMD preset_select",
    0x29: "CMD cmd29_status (preset_b_active bit reflect)",
    0x43: "CMD diag_memread (V3.1+ HID flash/EEPROM read)",
}

_ROUTE_VALUES: Dict[int, str] = {
    0xB0: "ROUTE broadcast CONTROL→MAIN",
    0xB1: "ROUTE addressed MAIN#1",
    0xB2: "ROUTE addressed MAIN#2",
    0xB3: "ROUTE addressed MAIN#3",
    0xB4: "ROUTE addressed MAIN#4",
    0xB5: "ROUTE addressed MAIN#5",
    0xB6: "ROUTE addressed MAIN#6",
    0xBF: "ROUTE MAIN→CONTROL return",
}

# Canonical Hypex RC5 codes (subset documented in SEMANTIC_FUNCTION_MAP).
_RC5_VALUES: Dict[int, str] = {
    0x0C: "RC5 0x0C standby toggle",
    0x10: "RC5 0x10 volume up",
    0x11: "RC5 0x11 volume down",
    0x12: "RC5 0x12 mute",
    0x1F: "RC5 0x1F channel up",
    0x20: "RC5 0x20 preset next",
    0x21: "RC5 0x21 preset prev / channel down",
}

# RAM names that appear as ``equ`` in dlcp_control_ram.inc.  Order matches
# the source; this is the authoritative mapping used for the RAM-equate
# substitution pass.
_RAM_EQUATES: Dict[int, str] = {
    0x01D: "ir_decoded_cmd",
    0x01E: "ir_decoded_addr",
    0x01F: "control_flags",
    0x027: "tx_data_staging",
    0x02F: "rx_parsed_cmd",
    0x030: "rx_parsed_data",
    0x036: "tx_ring_base",
    0x066: "rx_ring_base",
    0x096: "tx_ring_rd",
    0x097: "tx_ring_wr",
    0x098: "rx_ring_rd",
    0x099: "rx_ring_wr",
    0x09D: "idle_timeout_lo",
    0x09E: "idle_timeout_hi",
    0x09F: "full_sync_lo",
    0x0A0: "full_sync_hi",
    0x0A1: "raw_status_cache",
    0x0A6: "rx_frame_position",
    0x0A7: "cmd1d_setting_cache",
    0x0B7: "rx_ring_staging",
    0x0B8: "input_select_cache",
    0x0B9: "volume_cache",
    0x0BB: "button_debounce_counter",
    0x0BC: "button_last_scan",
    0x0BE: "button_debounced",
    0x0BF: "display_state_index",
    0x0C1: "saved_settings_base",
}


def _run_gpdasm(hex_path: Path) -> str:
    """Invoke gpdasm and return the compilable source text."""
    result = subprocess.run(
        ["gpdasm", "-p", "18f25k20", "-s", "-n", str(hex_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# v16b.asm parsing: extract label/function → semantic name mapping
# ---------------------------------------------------------------------------

_SEMANTIC_RE = re.compile(
    r";\s*[->]+\s*(?P<name>[A-Za-z_][A-Za-z_0-9]*)\s*\((?P<auto>(?:label|function|addr)_\w+)\)"
)
_FUNCTION_BANNER_RE = re.compile(
    r"^; =+\s*\n"
    r";\s*(?P<auto>function_\d+)\s+@\s+0x(?P<addr>[0-9A-Fa-f]+)\s+[-—]\s+(?P<name>[A-Za-z_][A-Za-z_0-9]*)\b",
    re.MULTILINE,
)
_AT_ADDR_RE = re.compile(
    r";\s*(?P<auto>(?:label|function)_\d+)\s+@\s+0x(?P<addr>[0-9A-Fa-f]+)\s+[-—]\s+(?P<name>[A-Za-z_][A-Za-z_0-9]*)\b"
)
_INLINE_ARROW_RE = re.compile(
    r";\s*(?P<auto>(?:label|function)_\d+)\s+[-—]\s+(?P<name>[A-Za-z_][A-Za-z_0-9]*_[A-Za-z_0-9]+)\b"
)
# "; -> name (label_NNN / address)" pattern used in v16b.asm headers.
_ARROW_ADDR_RE = re.compile(
    r";\s*[->]+\s*(?P<name>[A-Za-z_][A-Za-z_0-9]*)\b"
    r"[^\n;]*?0x(?P<addr>[0-9A-Fa-f]{4,6})"
)
# v16b.asm body lines: "; target_addr (label_NNN / semantic_name)"
#   e.g. "goto 0x007800             ; -> bootloader_entry (label_284)"
_GPDASM_COMMENT_RE = re.compile(
    r"0x(?P<addr>[0-9A-Fa-f]{4,6})\s+[^\n]*?[-—>]+\s*(?P<name>[A-Za-z_][A-Za-z_0-9]*_[A-Za-z_0-9]+)"
)


def _load_v16b_auto_to_name() -> Dict[str, str]:
    """Parse v16b.asm to build its **own** auto-label → semantic-name map.

    The auto-label numbers in v16b.asm come from a historic gpdasm pass
    and do NOT match the current fresh gpdasm output.  This map is used
    only to scrub v16b.asm commentary (function header banners, inline
    prose) that is ported verbatim into the commented source: references
    like ``function_082`` that are live in v16b.asm's number space get
    rewritten to their semantic names before the text is embedded into
    the V1.7 source.
    """
    text = V16B_REFERENCE.read_text(encoding="utf-8", errors="replace")
    mapping: Dict[str, str] = {}
    for m in _FUNCTION_BANNER_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    for m in _AT_ADDR_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    for m in _SEMANTIC_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    # Tight parenthetical form: "label_NNN (semantic_name)" or
    # "function_080 (bootloader_prompt_send at 0x7E60)".  We grab the
    # first multi-part identifier after the opening paren.
    for m in re.finditer(
        r"\b(?P<auto>(?:label|function)_\d+)\s*\(\s*(?P<name>[A-Za-z_][A-Za-z_0-9]*_[A-Za-z_0-9]+)\b",
        text,
    ):
        mapping.setdefault(m.group("auto"), m.group("name"))
    # Arrow form: "function_NNN — semantic_name".
    for m in _INLINE_ARROW_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    return mapping


def _load_semantic_names_by_address() -> Dict[int, str]:
    """Parse v16b.asm to build ``{address: semantic_name}`` mapping.

    The v16b.asm auto-label numbers (``label_NNN`` / ``function_NNN``)
    come from a historic gpdasm run; re-running gpdasm on the same hex
    can renumber labels.  Therefore the reliable join key between
    v16b.asm (semantic names) and the fresh gpdasm output is the
    program address, not the auto-label number.
    """
    text = V16B_REFERENCE.read_text(encoding="utf-8", errors="replace")
    mapping: Dict[int, str] = {}

    # Pattern B: "; function_NNN @ 0xADDR — semantic_name"
    for m in _FUNCTION_BANNER_RE.finditer(text):
        mapping.setdefault(int(m.group("addr"), 16), m.group("name"))
    for m in _AT_ADDR_RE.finditer(text):
        mapping.setdefault(int(m.group("addr"), 16), m.group("name"))

    # v16b.asm body lines like "goto 0x007800  ; -> bootloader_entry
    # (label_284)" look tempting as a source of address→name joins, but
    # the trailing comment can attach a semantic name to an inner entry
    # point of the named function (e.g. 0x0001D8 inside
    # delay_parameter_unit at 0x0000AA).  Trusting the body lines
    # therefore risks renaming multiple distinct labels to the same
    # semantic name and collapsing their addresses.  Only the
    # banner-anchored patterns above are authoritative.
    return mapping


def _load_semantic_names(addr_map: Optional[Dict[str, int]] = None) -> Dict[str, str]:
    """Return ``{auto_name: semantic_name}`` composing address-joined map.

    ``addr_map`` is the ``{auto_name: address}`` dict from the fresh gpdasm
    output (via ``_collect_label_addresses``).  When omitted, the function
    falls back to the legacy auto-label-match patterns; the caller is
    expected to pass ``addr_map`` for a deterministic semantic-rename
    pass.
    """
    addr_to_name = _load_semantic_names_by_address()
    mapping: Dict[str, str] = {}
    if addr_map:
        for auto, addr in addr_map.items():
            name = addr_to_name.get(addr)
            if name:
                mapping[auto] = name
        return mapping

    # Legacy fallback: best-effort token joins (kept for standalone tests).
    text = V16B_REFERENCE.read_text(encoding="utf-8", errors="replace")
    for m in _SEMANTIC_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    for m in _FUNCTION_BANNER_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    for m in _AT_ADDR_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    inline_re = re.compile(
        r"\b(?P<auto>(?:function|label)_\d+)\s*\(\s*(?P<name>[A-Za-z_][A-Za-z_0-9]*)\s*\)"
    )
    for m in inline_re.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    for m in _INLINE_ARROW_RE.finditer(text):
        mapping.setdefault(m.group("auto"), m.group("name"))
    return mapping


def _load_function_headers_by_address() -> Dict[int, str]:
    """Return ``{address: header_text}`` for each banner in v16b.asm."""
    text = V16B_REFERENCE.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    headers: Dict[int, str] = {}

    banner_start = re.compile(r"^;\s*=+\s*$")
    banner_mid = re.compile(
        r"^;\s*(?P<auto>function_\d+)\s+@\s+0x(?P<addr>[0-9A-Fa-f]+)\s+[-—]\s+(?P<name>[A-Za-z_][A-Za-z_0-9]*)"
    )

    i = 0
    n = len(lines)
    while i < n:
        if banner_start.match(lines[i]):
            start = i
            mid = None
            j = i + 1
            while j < n and lines[j].startswith(";"):
                if banner_mid.match(lines[j]):
                    mid = banner_mid.match(lines[j])
                j += 1
            if mid is not None:
                end = j
                header_lines = lines[start:end]
                while header_lines and banner_start.match(header_lines[-1]):
                    if len(header_lines) >= 2 and banner_start.match(header_lines[-2]):
                        header_lines.pop()
                    else:
                        break
                headers[int(mid.group("addr"), 16)] = "\n".join(header_lines)
                i = end
                continue
        i += 1

    return headers


def _load_function_headers(addr_map: Optional[Dict[str, int]] = None) -> Dict[str, str]:
    """Return ``{auto_name: header_text}`` composed via address joining.

    Header text is pre-scrubbed: any ``label_NNN`` / ``function_NNN``
    reference inside the banner is rewritten to its semantic name using
    v16b.asm's own auto-label → name map, since those auto-numbers do
    not survive a fresh gpdasm pass.
    """
    by_addr = _load_function_headers_by_address()
    v16b_rename = _load_v16b_auto_to_name()
    scrub_re = re.compile(r"\b((?:label|function)_\d+)\b")

    def _scrub(text: str) -> str:
        return scrub_re.sub(
            lambda m: v16b_rename.get(m.group(1), m.group(1)), text
        )

    out: Dict[str, str] = {}
    if addr_map:
        for auto, addr in addr_map.items():
            text = by_addr.get(addr)
            if text:
                out[auto] = _scrub(text)
    else:
        for addr, header in by_addr.items():
            out[f"addr_{addr:06X}"] = _scrub(header)
    return out


# ---------------------------------------------------------------------------
# Pass: rewrite Common_RAM references to named equates
# ---------------------------------------------------------------------------

_COMMON_RAM_PAT = re.compile(
    r"\(Common_RAM\s*\+\s*(?P<off>\d+|0x[0-9A-Fa-f]+)\)"
)


def _rewrite_ram(text: str) -> str:
    """Replace ``(Common_RAM + N)`` with the matching named equate.

    Emits the symbolic name as ``name`` (without parentheses) because the
    equate resolves to the absolute 8-bit GPR address.  Only offsets that
    are present in ``_RAM_EQUATES`` are rewritten; unnamed offsets are left
    untouched so the source stays byte-identical even for GPR slots the
    spec has not named yet.
    """

    def _sub(match: re.Match[str]) -> str:
        raw = match.group("off")
        value = int(raw, 0)
        name = _RAM_EQUATES.get(value)
        if name is None:
            return match.group(0)
        return name

    return _COMMON_RAM_PAT.sub(_sub, text)


# ---------------------------------------------------------------------------
# Pass: rename auto labels to semantic names
# ---------------------------------------------------------------------------

_LABEL_TOKEN_RE = re.compile(r"\b((?:label|function)_\d+)\b")
_LABEL_DEF_RE = re.compile(
    r"^(?P<name>(?:label|function)_\d+):\s*;\s*address:\s*0x(?P<addr>[0-9A-Fa-f]+)"
)


def _collect_label_addresses(text: str) -> Dict[str, int]:
    """Return ``{auto_name: address}`` for every label definition in *text*."""
    out: Dict[str, int] = {}
    for line in text.splitlines():
        m = _LABEL_DEF_RE.match(line)
        if m:
            out[m.group("name")] = int(m.group("addr"), 16)
    return out


def _fallback_name(auto_name: str, addr: int) -> str:
    """Mint a placeholder semantic name for an unmapped label.

    Functions → ``control_core_service_XXXX`` (matches spec § B1).
    Labels    → ``flow_local_XXXX``.
    """
    if auto_name.startswith("function_"):
        return f"control_core_service_{addr:04X}"
    return f"flow_local_{addr:04X}"


def _rewrite_labels(
    text: str,
    mapping: Dict[str, str],
    *,
    rename_unmapped: bool = False,
    addr_map: Optional[Dict[str, int]] = None,
) -> str:
    """Rename every auto-label token to its semantic name.

    When ``rename_unmapped`` is True, any ``function_NNN`` / ``label_NNN``
    that lacks a semantic entry is renamed to a deterministic placeholder
    based on its program address.  This ensures that
    ``dlcp_control_v17_comments.asm`` contains zero raw auto-labels
    (per spec Phase 2 acceptance criteria).

    ``addr_map`` can be passed to reuse addresses captured from an
    earlier pre-rewrite snapshot of the source; otherwise addresses are
    re-extracted from *text*.  Pre-capture is necessary when rewrite
    runs a second time on text whose label definitions have already
    been renamed (so the address-bearing label lines are gone).
    """
    if not mapping and not rename_unmapped:
        return text

    if rename_unmapped:
        if addr_map is None:
            addr_map = _collect_label_addresses(text)
    else:
        addr_map = {}
    full_map: Dict[str, str] = dict(mapping)
    if rename_unmapped:
        for auto, addr in addr_map.items():
            full_map.setdefault(auto, _fallback_name(auto, addr))

    def _sub(match: re.Match[str]) -> str:
        auto = match.group(1)
        return full_map.get(auto, auto)

    return _LABEL_TOKEN_RE.sub(_sub, text)


# ---------------------------------------------------------------------------
# Pass: TBLPTR literal → HIGH/LOW label conversion
# ---------------------------------------------------------------------------
#
# The V1.6b firmware loads TBLPTRH/TBLPTRL with pairs of ``movlw 0xHH`` /
# ``movlw 0xLL`` for LCD string bases (and similar program-memory reads).
# These are hardcoded program addresses that break under a code shift —
# gpdasm emits them verbatim, so the V1.7 source inherits the problem.
#
# This pass detects both orderings:
#
#     movlw   0xHH              ; 4-word pattern A
#     movwf   TBLPTRH, A
#     movlw   0xLL
#     movwf   TBLPTRL, A
#
#     movlw   0xLL              ; 4-word pattern B (L-first)
#     movwf   TBLPTRL, A
#     movlw   0xHH
#     movwf   TBLPTRH, A
#
# …computes target = HH<<8 | LL, emits a ``tbl_<XXXX>:`` anchor at that
# address (reusing a single label pool per target), and rewrites the
# two literal loads to ``movlw HIGH(tbl_<XXXX>)`` / ``movlw LOW(tbl_<XXXX>)``.
#
# Targets in the bootloader region (≥ 0x7800) are left alone: the
# bootloader is pinned by ``org 0x7800`` and does not shift.

_TBLPTR_BOOTLOADER_FLOOR = 0x7800
_APP_CODE_FLOOR = 0x004C
# Conservative upper bound for stock V1.6b application code: measured at
# 0x1A0B (last non-0xFF byte below 0x7000 in stock hex).  Targets past
# this address are almost certainly arithmetic literals, not program
# pointers, so we skip them to avoid false positives on values like
# ``0x2011`` or ``0x3210`` that appear in config-table loads.
_APP_CODE_CEILING = 0x1C00

# RAM cells known to flow into TBLPTR in the V1.6b firmware (discovered
# by searching for ``movff ram, TBLPTR*`` and ``addwf ram, W; movwf
# TBLPTR*`` patterns).  Pattern B only rewrites literal loads whose
# destination RAM pair matches one of these — otherwise we risk
# rewriting counter/scratch pairs like (0x1B, 0x1C) whose shifted
# values would silently differ from stock.
_POINTER_RAM_PAIRS: set[tuple[int, int]] = {
    (0x29, 0x2A),  # function_024 menu title pointer (LOW=0x29, HIGH=0x2A)
}

# Semantic names for the TBLPTR anchor addresses we know about.  Keeps
# the commented source readable ("menu_title_table" vs "tbl_100C") and
# documents intent so V1.71 edits can refer to named tables.
_TBLPTR_SEMANTIC_NAMES: Dict[int, str] = {
    0x0304: "lcd_str_firmware_v",
    0x0310: "lcd_str_waiting_for_dlcp",
    0x0322: "lcd_str_standby_zzz",
    0x0334: "lcd_str_waiting_for_dlcp_alt",
    0x0346: "lcd_str_db_suffix",
    0x0354: "lcd_str_mute",
    0x100C: "menu_title_table",
    0x13EE: "menu_setup_bl_timeout_entry",
    0x1572: "menu_source_channel_table",
    0x15E2: "menu_routing_table",
    0x1622: "menu_input_cat_spdif_table",
    0x1882: "menu_input_auto_detect_table",
}

_MOVLW_RE = re.compile(r"^(\s*)movlw\s+0x(?P<lit>[0-9A-Fa-f]+)\s*(?P<tail>;.*)?$")
_MOVWF_TBLPTR_RE = re.compile(
    r"^(\s*)movwf\s+TBLPTR(?P<half>[LH])\s*,?\s*A?\s*(;.*)?$"
)
# Match ``movwf (Common_RAM + N), A`` (captures offset as decimal/hex).
_MOVWF_COMMON_RE = re.compile(
    r"^(?P<indent>\s*)movwf\s+\(Common_RAM\s*\+\s*(?P<off>\d+|0x[0-9A-Fa-f]+)\)\s*,?\s*A?"
)
_ADDRESS_LABEL_RE = re.compile(
    r"^(?P<name>[A-Za-z_][\w]*)\s*:\s*;\s*address:\s*0x(?P<addr>[0-9A-Fa-f]+)"
)


def _collect_all_label_addresses(text: str) -> Dict[int, str]:
    """Return ``{address: first_label_name}`` for every label definition."""
    out: Dict[int, str] = {}
    for line in text.splitlines():
        m = _ADDRESS_LABEL_RE.match(line)
        if m:
            addr = int(m.group("addr"), 16)
            out.setdefault(addr, m.group("name"))
    return out


def _rewrite_tblptr_literals(text: str) -> str:
    """Replace literal TBLPTRH/L load pairs with label-relative HIGH/LOW.

    Emits an anchor label at each target and rewrites the four-line
    TBLPTR-load pattern to survive relocation.  Byte-identity across the
    V1.7 baseline is preserved because ``HIGH(label)`` and ``LOW(label)``
    evaluate to the same immediates the firmware used originally when
    the canonical source assembles at stock addresses.
    """
    lines = text.split("\n")
    # Pass 1: find TBLPTR-load sites and compute ``{target_addr: label}``.
    existing_labels = _collect_all_label_addresses(text)
    new_labels: Dict[int, str] = {}

    def _label_for(addr: int) -> str:
        if addr in existing_labels:
            return existing_labels[addr]
        if addr in new_labels:
            return new_labels[addr]
        name = _TBLPTR_SEMANTIC_NAMES.get(addr, f"tbl_{addr:04X}")
        new_labels[addr] = name
        return name

    def _maybe_anchor(target: int, *, strict: bool) -> Optional[str]:
        # Pattern A (literal→TBLPTR) spans the full app region up to the
        # bootloader floor, because even sparse / late addresses are
        # real program pointers.  Pattern B (literal→ram pair) is more
        # heuristic and must be constrained to the tighter code-body
        # ceiling to avoid misclassifying arithmetic literals.  Pattern
        # A's caller passes ``strict=False`` to opt out of the ceiling.
        if not (_APP_CODE_FLOOR <= target < _TBLPTR_BOOTLOADER_FLOOR):
            return None
        if strict and target >= _APP_CODE_CEILING:
            return None
        # PIC18 instruction / aligned-data addresses are always even.
        # An odd target is definitely a non-pointer literal and must not
        # trigger label insertion (doing so would drag a new label into
        # the middle of an instruction pair).
        if strict and (target & 1):
            return None
        return _label_for(target)

    i = 0
    n = len(lines)
    replacements: Dict[int, tuple[str, int]] = {}  # line_idx -> (new_text, target_addr)
    while i + 3 < n:
        m1 = _MOVLW_RE.match(lines[i])
        if not m1:
            i += 1
            continue
        m2_tbl = _MOVWF_TBLPTR_RE.match(lines[i + 1])
        m2_ram = _MOVWF_COMMON_RE.match(lines[i + 1]) if not m2_tbl else None
        m3 = _MOVLW_RE.match(lines[i + 2])
        if not m3:
            i += 1
            continue
        m4_tbl = _MOVWF_TBLPTR_RE.match(lines[i + 3])
        m4_ram = _MOVWF_COMMON_RE.match(lines[i + 3]) if not m4_tbl else None

        k1 = int(m1.group("lit"), 16)
        k2 = int(m3.group("lit"), 16)
        target: Optional[int] = None
        hi_idx = lo_idx = -1
        indent_hi = indent_lo = ""
        strict = True  # Pattern B uses tightened code-ceiling

        # Pattern A: literal→TBLPTRH + literal→TBLPTRL (in either order).
        if m2_tbl and m4_tbl and m2_tbl.group("half") != m4_tbl.group("half"):
            if m2_tbl.group("half") == "H":
                target = (k1 << 8) | k2
                hi_idx, lo_idx = i, i + 2
                indent_hi, indent_lo = m1.group(1), m3.group(1)
            else:
                target = (k2 << 8) | k1
                hi_idx, lo_idx = i + 2, i
                indent_hi, indent_lo = m3.group(1), m1.group(1)
            strict = False  # direct TBLPTR writes are unambiguous

        # Pattern B: literal→ram_X + literal→ram_Y where the RAM pair is
        # a known 16-bit TBLPTR pointer (``_POINTER_RAM_PAIRS``).  Adjacent
        # scratch/counter pairs like (0x1B, 0x1C) are skipped — they
        # happen to look like pointer loads in stock V1.6b but their
        # shifted values are irrelevant.
        elif m2_ram and m4_ram:
            ram_x = int(m2_ram.group("off"), 0)
            ram_y = int(m4_ram.group("off"), 0)
            lo_cell, hi_cell = sorted((ram_x, ram_y))
            if (lo_cell, hi_cell) in _POINTER_RAM_PAIRS:
                if ram_x > ram_y:
                    hi_val, lo_val = k1, k2
                    hi_idx, lo_idx = i, i + 2
                    indent_hi, indent_lo = m1.group(1), m3.group(1)
                else:
                    hi_val, lo_val = k2, k1
                    hi_idx, lo_idx = i + 2, i
                    indent_hi, indent_lo = m3.group(1), m1.group(1)
                candidate = (hi_val << 8) | lo_val
                if _APP_CODE_FLOOR <= candidate < _TBLPTR_BOOTLOADER_FLOOR:
                    target = candidate

        if target is not None:
            label = _maybe_anchor(target, strict=strict)
            if label:
                replacements[hi_idx] = (
                    f"{indent_hi}movlw   HIGH({label})                          ; shifted via label",
                    target,
                )
                replacements[lo_idx] = (
                    f"{indent_lo}movlw   LOW({label})                           ; shifted via label",
                    target,
                )
                i += 4
                continue
        i += 1

    # Pass 2: emit label anchors before the first code line at each target.
    # Use gpasm ``listing`` authoritative addresses: drop each line through
    # a throwaway gpasm pass with a ``.lst`` output, then re-parse the list
    # to get an accurate source-line → address map.  This avoids the
    # fragility of a hand-rolled PIC18 instruction-size walker.

    line_to_addr = _addresses_per_line(lines)

    # Build a reverse map: target-address → first line index at that addr.
    target_to_line: Dict[int, int] = {}
    for idx in sorted(line_to_addr.keys()):
        addr = line_to_addr[idx]
        if addr in new_labels and addr not in target_to_line:
            target_to_line[idx] = addr

    # Render output: apply replacements, then insert label anchors above
    # the recorded target lines.  Insertion happens bottom-up so earlier
    # indices stay valid.
    out = list(lines)
    for idx, (new_text, _target) in replacements.items():
        out[idx] = new_text

    insertions = sorted(target_to_line.items(), key=lambda kv: -kv[0])
    for line_idx, addr in insertions:
        label = new_labels[addr]
        # Anchor emits as a standalone label line so gpasm binds it to the
        # next-byte address (same byte offset as the line it precedes).
        out.insert(
            line_idx,
            f"{label}:                                                  ; address: 0x{addr:06x}  (tblptr anchor)",
        )

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Pass: annotate immediate values (spec §B2 / C2)
# ---------------------------------------------------------------------------
#
# The annotator appends ``  ; <meaning>`` to ``movlw 0xNN`` lines whose
# literal matches one of the CMD / ROUTE / RC5 tables above AND whose
# context identifies the literal as that category.  Context matching is
# deliberately narrow: a literal byte that also appears as, say, a loop
# counter would produce a misleading comment if we annotated
# unconditionally.  Current rules:
#
# * ROUTE bytes 0xB0..0xB6, 0xBF: always annotated (no other context
#   produces these values as immediate literals in stock V1.6b).
# * CMD bytes: annotated when the immediately-following line is a
#   ``movwf tx_data_staging`` / ``movwf (Common_RAM + 0x27)`` / direct
#   ``call tx_byte_enqueue`` (the stock CONTROL pattern for emitting a
#   frame byte) OR when the preceding ``cpfseq`` / ``xorlw`` compares
#   against a cmd byte in an RX-parser dispatch.
# * RC5 codes: annotated when the literal appears in an ``xorlw 0xNN``
#   / ``cpfseq ir_decoded_cmd`` comparison inside the IR dispatch body.
# * Lines that already carry an explanatory trailing comment (``; reg:
#   0xNN``, ``; dest: 0x...``, ``; shifted via label``, etc.) are left
#   untouched — we don't clobber gpdasm-supplied or converter-supplied
#   commentary.

# Only literal-operand mnemonics.  ``cpfseq`` / ``cpfslt`` / ``cpfsgt``
# are byte-oriented file-register instructions whose operand is a RAM
# address, not a literal — matching them here would misclassify every
# ``cpfseq 0xb6, B`` as a ROUTE load.
_IMM_TOKEN_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<mn>movlw|addlw|sublw|iorlw|xorlw|retlw|mullw|andlw)"
    r"\s+(?P<operand>0x[0-9A-Fa-f]+)(?P<rest>\b.*)?$"
)


def _annotate_immediates(text: str) -> str:
    """Append semantic annotations to recognized immediate-value loads.

    Conservative: only annotates literal values whose meaning is
    unambiguous in the CONTROL V1.6b protocol (route bytes, known
    CMD bytes in TX-frame context, RC5 codes in IR-dispatch context).
    Never overwrites an existing non-stock comment.
    """
    lines = text.split("\n")
    out: List[str] = []

    def _append_suffix(raw: str, suffix: str) -> str:
        # Preserve any existing gpdasm/our trailing comment: annotations
        # go BEFORE the existing ``; `` if present, joined by a middle
        # dot so multi-line greps stay usable.
        if ";" in raw:
            # Insert before existing comment.
            head, _, comment = raw.rpartition(";")
            head = head.rstrip()
            return f"{head:<60}; {suffix} · {comment.strip()}"
        return f"{raw:<60}; {suffix}"

    def _nearby_text(i: int, window: int = 3) -> str:
        start = max(0, i - window)
        end = min(len(lines), i + window + 1)
        return "\n".join(lines[start:end]).lower()

    def _tx_frame_context(i: int) -> bool:
        near = _nearby_text(i, window=3)
        return (
            "tx_data_staging" in near
            or "tx_byte_enqueue" in near
            or "common_ram + 39" in near  # tx_data_staging at 0x027
            or "serial_tx_routed_frame" in near
            or "volume_frame_send" in near
            or "input_frame_send" in near
            or "mute_frame_send" in near
            or "standby_wake_broadcast" in near
            or "cmd1d_setting_frame_send" in near
            or "poll_frame_send" in near
            or "full_sync_burst" in near
        )

    def _rx_parser_context(i: int) -> bool:
        near = _nearby_text(i, window=4)
        return "rx_parsed_cmd" in near or "rx_parser_entry" in near

    def _ir_dispatch_context(i: int) -> bool:
        near = _nearby_text(i, window=6)
        return "ir_decoded_cmd" in near or "ir_decoded_addr" in near or "ir_rc5_decode" in near

    for i, raw in enumerate(lines):
        m = _IMM_TOKEN_RE.match(raw)
        if not m:
            out.append(raw)
            continue
        try:
            value = int(m.group("operand"), 16)
        except ValueError:
            out.append(raw)
            continue

        suffix: Optional[str] = None

        if value in _ROUTE_VALUES:
            suffix = _ROUTE_VALUES[value]
        elif value in _CMD_VALUES and (_tx_frame_context(i) or _rx_parser_context(i)):
            suffix = _CMD_VALUES[value]
        elif value in _RC5_VALUES and _ir_dispatch_context(i):
            suffix = _RC5_VALUES[value]

        if suffix is None:
            out.append(raw)
            continue

        # Skip if the existing trailing comment already mentions the
        # semantic suffix.  Keeps idempotency so the annotator can be
        # re-run without bloating lines.
        if suffix.split()[0] in raw:
            out.append(raw)
            continue
        out.append(_append_suffix(raw, suffix))
    return "\n".join(out)


def _addresses_per_line(lines: List[str]) -> Dict[int, int]:
    """Drop *lines* through gpasm once and return ``{src_line_idx: addr}``.

    The listing produced by gpasm has one entry per non-empty source line
    of the form::

        001234 0E03           00567         movlw   0x03

    where ``001234`` is the absolute program address, ``0E03`` is the
    encoded word, and ``00567`` is the 1-based source line number.  We
    parse this file, convert to 0-based indices, and return the
    ``{src_line_idx: program_addr}`` map.  Lines with no address (blank,
    comment, directive) are omitted; callers use the next line's address
    as a fallback when anchoring a label at an intermediate address.
    """
    text = "\n".join(lines)
    with tempfile.TemporaryDirectory(prefix="v17_tblptr_lst_") as td:
        td_path = Path(td)
        # Stage the ram include alongside so gpasm can resolve it.
        ram_src = REPO_ROOT / "src" / "dlcp_fw" / "asm" / RAM_INC_NAME
        (td_path / RAM_INC_NAME).write_bytes(ram_src.read_bytes())
        asm = td_path / "tblptr_walk.asm"
        asm.write_text(text, encoding="utf-8")
        subprocess.run(
            ["gpasm", "-p18f25k20", "-o", str(asm.with_suffix(".hex")), str(asm)],
            capture_output=True,
            text=True,
        )
        lst = asm.with_suffix(".lst")
        if not lst.exists():
            raise RuntimeError(f"gpasm did not produce .lst at {lst}")
        lst_text = lst.read_text(encoding="utf-8", errors="replace")

    # ``NNNNNN XXXX           SSSSS  <source>`` — capture address + source line num.
    _LST_RE = re.compile(
        r"^(?P<addr>[0-9A-Fa-f]{6})\s+[0-9A-Fa-f]{4}(?:\s+[0-9A-Fa-f]{4})?\s+(?P<srcnum>\d{5})\s"
    )
    line_to_addr: Dict[int, int] = {}
    for raw in lst_text.splitlines():
        m = _LST_RE.match(raw)
        if not m:
            continue
        src_idx = int(m.group("srcnum")) - 1
        addr = int(m.group("addr"), 16)
        line_to_addr.setdefault(src_idx, addr)
    return line_to_addr

def _insert_function_headers(
    text: str,
    headers: Dict[str, str],
    name_map: Dict[str, str],
) -> str:
    """Insert commented banners before each function definition line."""
    if not headers:
        return text

    # After label renames, find labels by semantic name OR auto-name.
    out_lines: List[str] = []
    label_re = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z_0-9]*):\s*;.*$")

    # Build reverse map: semantic_name -> auto_name (for lookup after rename)
    reverse: Dict[str, str] = {}
    for auto, sem in name_map.items():
        reverse.setdefault(sem, auto)

    for line in text.splitlines():
        m = label_re.match(line)
        if m:
            label = m.group("name")
            auto = reverse.get(label, label)
            header = headers.get(auto)
            if header:
                out_lines.append("")
                out_lines.append(header)
                out_lines.append(f"; {label}:")
        out_lines.append(line)
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# Pass: add include directive for dlcp_control_ram.inc
# ---------------------------------------------------------------------------

def _add_ram_include(text: str) -> str:
    """Insert ``include "dlcp_control_ram.inc"`` after the processor include."""
    include_re = re.compile(r"(^\s*include\s+p18f25k20\.inc\s*$)", re.MULTILINE)
    replacement = (
        r"\1\n"
        f"        include {RAM_INC_NAME}\n"
    )
    return include_re.sub(replacement, text, count=1)


# ---------------------------------------------------------------------------
# Header banner
# ---------------------------------------------------------------------------

V17_BYTE_IDENTICAL_BANNER = """\
; ===========================================================================
; DLCP CONTROL V1.7 — byte-identical source rebuild of stock V1.6b
; ===========================================================================
; Target MCU : Microchip PIC18F25K20 @ ~16 MHz (4 MIPS)
; Output     : Assembles byte-identical to
;                firmware/stock/control/DLCP Control Firmware V1.6b.hex
;                in code, config, and EEPROM regions.
;
; Generated by scripts/convert_v16b_asm_to_gpasm.py.  See
; docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md for the full V1.7 spec.
;
; The "auto-labeled first pass" (this file) preserves the gpdasm-generated
; function_NNN / label_NNN identifiers; the semantic rename pass lives in
; dlcp_control_v17_comments.asm.
; ===========================================================================
"""

V17_COMMENTS_BANNER = """\
; ===========================================================================
; DLCP CONTROL V1.7 — canonical commented source (byte-identical to V1.6b)
; ===========================================================================
; Target MCU : Microchip PIC18F25K20 @ ~16 MHz (4 MIPS)
; Output     : Assembles byte-identical to
;                firmware/stock/control/DLCP Control Firmware V1.6b.hex
;                in code, config, and EEPROM regions.
;
; Generated by scripts/convert_v16b_asm_to_gpasm.py with
;   --with-ram-equates --with-semantic-names --with-function-headers.
;
; Semantic names and function banners come from
; firmware/disasm/control/v16b.asm (primary reference for V1.7).
; ===========================================================================
"""


def _prepend_banner(text: str, banner: str) -> str:
    return banner + "\n" + text


# ---------------------------------------------------------------------------
# Assembler post-flight sanity: catch accidental drift vs stock hex.
# ---------------------------------------------------------------------------

def _verify_byte_identity(asm_path: Path) -> None:
    """Assemble *asm_path* and diff against stock V1.6b; print summary."""
    asm_path = asm_path.resolve()
    hex_out = asm_path.with_suffix(".hex")
    lst_out = asm_path.with_suffix(".lst")
    # gpasm writes the hex relative to the output argument; request the
    # name so we can diff it later.
    cmd = [
        "gpasm",
        "-p18f25k20",
        "-o", str(hex_out),
        str(asm_path),
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True, cwd=str(asm_path.parent))
    output = cp.stdout + cp.stderr
    errors = [
        line for line in output.splitlines()
        if re.search(r"\bError(?:\[\d+\])?\b", line)
    ]
    if cp.returncode != 0 or errors:
        sys.stderr.write(
            "gpasm failed (rc=%d):\n%s\n" % (cp.returncode, "\n".join(errors[:20]) or output[:400])
        )
        raise SystemExit(cp.returncode or 1)
    # Cleanup: move the .lst next to the .asm if gpasm placed it elsewhere.
    auto_lst = asm_path.parent / (asm_path.stem + ".lst")
    if not lst_out.exists() and auto_lst.exists():
        lst_out.write_bytes(auto_lst.read_bytes())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hex", type=Path, default=STOCK_HEX, help="stock V1.6b hex to disassemble")
    ap.add_argument("--output", type=Path, required=True, help="destination .asm path")
    ap.add_argument(
        "--with-ram-equates",
        action="store_true",
        help="rewrite (Common_RAM + N) to named equates from dlcp_control_ram.inc",
    )
    ap.add_argument(
        "--with-semantic-names",
        action="store_true",
        help="rename auto-generated labels using v16b.asm semantic names",
    )
    ap.add_argument(
        "--rename-unmapped",
        action="store_true",
        help="also rename unmapped function_NNN/label_NNN to placeholder names "
             "based on program address (produces zero auto-labels)",
    )
    ap.add_argument(
        "--convert-tblptr-literals",
        action="store_true",
        help="rewrite 4-line TBLPTRH/L literal loads to HIGH(label)/LOW(label) "
             "so ROM-data pointers survive a code shift",
    )
    ap.add_argument(
        "--annotate-immediates",
        action="store_true",
        help="annotate recognized immediate-value loads (CMD bytes, ROUTE bytes, "
             "RC5 codes) with trailing semantic comments",
    )
    ap.add_argument(
        "--with-function-headers",
        action="store_true",
        help="prepend curated function header banners from v16b.asm",
    )
    ap.add_argument(
        "--banner",
        choices=("v17", "v17_comments", "none"),
        default="v17",
        help="which top-of-file banner to prepend",
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="after writing, run gpasm and verify assembles without errors",
    )
    args = ap.parse_args(argv)

    text = _run_gpdasm(args.hex)
    text = _add_ram_include(text)

    if args.with_ram_equates:
        text = _rewrite_ram(text)

    # Capture addresses from the pre-rewrite snapshot so later passes can
    # still resolve auto-names to addresses after renaming.
    addr_map = _collect_label_addresses(text)
    name_map: Dict[str, str] = {}
    if args.with_semantic_names:
        name_map = _load_semantic_names(addr_map=addr_map)
    if args.with_semantic_names or args.rename_unmapped:
        text = _rewrite_labels(
            text, name_map, rename_unmapped=args.rename_unmapped, addr_map=addr_map
        )

    if args.with_function_headers:
        headers = _load_function_headers(addr_map=addr_map)
        text = _insert_function_headers(text, headers, name_map)
        # Re-apply label rewrite so header commentary references the new
        # semantic names too; otherwise the ported v16b.asm banners would
        # still mention function_NNN.
        if args.with_semantic_names or args.rename_unmapped:
            text = _rewrite_labels(
                text, name_map, rename_unmapped=args.rename_unmapped, addr_map=addr_map
            )

    if args.convert_tblptr_literals:
        text = _rewrite_tblptr_literals(text)

    if args.annotate_immediates:
        text = _annotate_immediates(text)

    if args.banner != "none":
        banner = V17_BYTE_IDENTICAL_BANNER if args.banner == "v17" else V17_COMMENTS_BANNER
        text = _prepend_banner(text, banner)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    sys.stdout.write(f"Wrote {args.output} ({len(text)} bytes)\n")

    if args.verify:
        _verify_byte_identity(args.output)
        sys.stdout.write(f"Assembled {args.output.with_suffix('.hex')} OK\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""V1.7 CONTROL source-rewrite symbol parser and shift builder.

CONTROL-side analog of :mod:`dlcp_fw.sim.v30_symbols` for MAIN.  The
gpasm symbol-table parser is reused from the MAIN helpers; this file
adds the CONTROL-specific shift-test assembler helper and a
``parse_v17_symbols`` alias whose signature matches the spec.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

from .v30_symbols import parse_gpasm_symbols

# Re-export under the spec-mandated name.
parse_v17_symbols = parse_gpasm_symbols


# First application-code label after the vector block at stock 0x004C.
# The canonical commented source promotes ``control_core_service_004C``
# to ``app_entry_defensive_stub`` via the semantic-override table; the
# shift builder checks both names to stay compatible across polish
# passes that rename the defensive stub.
_VECTOR_BLOCK_END_LABELS = (
    "app_entry_defensive_stub",
    "control_core_service_004C",
)
_BOOTLOADER_LABEL = "bootloader_entry"
_RAM_INC_NAME = "dlcp_control_ram.inc"
_SHIFT_WORDS = 0x111  # 0x111 NOP words = 0x222 bytes (matches spec §A4)
_SHIFT_BYTES = _SHIFT_WORDS * 2


def assemble_v17(
    asm_path: Path,
    output_hex: Path,
    *,
    output_lst: Path | None = None,
    gpasm: str = "gpasm",
    pad_program_flash: bool = True,
) -> Path:
    """Assemble a V1.7 .asm source with gpasm (PIC18F25K20).

    When ``pad_program_flash`` is True (default), the produced hex is
    post-processed to add explicit 0xFF records for any gap in the
    program-flash app region (0x0000..0x77FF).  This is required because
    gpasm by default omits all-0xFF records from its hex output, which
    produces a sparse hex of ~10 KB while both the K20 stock bootloader's
    CRC verify AND HFD's hex validator expect the FULL 32 KB program
    flash to be explicitly covered.  Without padding, V1.71 hex is
    rejected by HFD ("Invalid hex file (not suited for DLCP)") and the
    bootloader's post-stream CRC verify fails because the bootloader
    sees a different byte sequence than the host computed CRC over.
    """
    cmd = [gpasm, "-p18f25k20", "-o", str(output_hex), str(asm_path)]
    cp = subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=str(asm_path.parent)
    )
    # gpasm for PIC18F25K20 emits benign warnings about CONFIG/IDLOCS
    # addresses exceeding the code range when we dump raw ``db`` bytes
    # at 0x200000/0x300000.  Only real errors should fail the build.
    errors = [
        line for line in (cp.stdout + cp.stderr).splitlines()
        if "Error" in line and "Warning" not in line
    ]
    if errors or cp.returncode != 0:
        raise RuntimeError(
            f"gpasm failed ({cp.returncode}):\n" + "\n".join(errors[:20])
        )
    auto_lsts = (
        asm_path.with_suffix(".lst"),
        output_hex.with_suffix(".lst"),
    )
    if output_lst is not None:
        import shutil
        existing = [path for path in auto_lsts if path.exists()]
        if not existing:
            raise RuntimeError(
                "gpasm did not produce a listing at any expected location: "
                + ", ".join(str(p) for p in auto_lsts)
            )
        freshest = max(existing, key=lambda p: p.stat().st_mtime_ns)
        if freshest.resolve() != output_lst.resolve():
            shutil.copy2(freshest, output_lst)
    if pad_program_flash:
        pad_hex_program_flash_app(output_hex)
    return output_hex


# K20 program-flash app window: 0x0000..0x77FF (30 KB).
# 0x7800..0x7FFF is the V1.6b stock bootloader (preserved by every
# release; flashing this region is refused by flash_control_safe.sh).
# Both HFD and the K20 stock bootloader's CRC verify expect explicit
# 0xFF coverage of the entire app window.
_K20_APP_WINDOW_START = 0x0000
_K20_APP_WINDOW_END_EXCL = 0x7800
_K20_PAD_BYTE = 0xFF
_K20_RECORD_SIZE = 16


def _ihex_checksum(data: bytes) -> int:
    """Intel HEX line checksum: two's-complement of the byte-sum."""
    return (-sum(data)) & 0xFF


def _emit_data_record(addr: int, data: bytes) -> str:
    """Format an Intel HEX type-00 (data) record."""
    if len(data) > 0xFF:
        raise ValueError(f"record too long: {len(data)} bytes")
    if not (0 <= addr <= 0xFFFF):
        raise ValueError(f"address out of 16-bit range: 0x{addr:X}")
    header = bytes([len(data), (addr >> 8) & 0xFF, addr & 0xFF, 0x00])
    body = header + data
    return f":{body.hex().upper()}{_ihex_checksum(body):02X}"


def _emit_ela_record(segment_high16: int) -> str:
    """Format an Intel HEX type-04 (extended linear address) record."""
    payload = bytes([0x02, 0x00, 0x00, 0x04,
                     (segment_high16 >> 8) & 0xFF,
                     segment_high16 & 0xFF])
    return f":{payload.hex().upper()}{_ihex_checksum(payload):02X}"


def pad_hex_program_flash_app(hex_path: Path) -> None:
    """Rewrite ``hex_path`` so the program-flash app window
    (``_K20_APP_WINDOW_START..._K20_APP_WINDOW_END_EXCL``) is fully
    covered by 16-byte data records, padding any gap with 0xFF bytes.

    Records OUTSIDE the program-flash app window are preserved verbatim
    in their original order (including any extended-linear-address
    records that switch to other segments such as CONFIG at 0x300000 or
    EEPROM at 0xF00000).  The bootloader region 0x7800..0x7FFF is left
    as gpasm emitted it (the safe-flash wrapper refuses to overwrite
    bootloader bytes anyway, but we still want to preserve whatever
    the build emitted in case a future release wants to update them).

    Background: gpasm omits records for any 16-byte chunk where every
    byte is 0xFF (the erased-flash default).  The K20 stock bootloader's
    CRC verify computes its checksum over the bytes IT receives — if
    our streaming sends only the gpasm-emitted records, the bootloader's
    CRC differs from the host-precomputed CRC over the full 32 KB
    region.  HFD's hex validator separately rejects sparse hex files
    with "Invalid hex file (not suited for DLCP)".

    Idempotent: running this on an already-padded hex produces an
    identical result.
    """
    text = hex_path.read_text(encoding="ascii")
    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]

    # Parse: collect program-flash bytes into a mem map, and split the
    # rest of the hex into "before" / "after" the first program-flash
    # data record so we can splice the padded records back in place.
    seg_high16 = 0x0000
    flash_map: Dict[int, int] = {}
    pre_lines: List[str] = []
    post_lines: List[str] = []
    seen_flash = False
    flash_in_pre = True
    cur_seg_in_app = True

    for ln in lines:
        if not ln or not ln.startswith(":"):
            continue
        rec_size = int(ln[1:3], 16)
        rec_addr = int(ln[3:7], 16)
        rec_type = int(ln[7:9], 16)

        if rec_type == 0x04:  # Extended Linear Address
            seg_high16 = int(ln[9:13], 16)
            cur_seg_in_app = (seg_high16 == 0x0000)
            # ELA records are preserved as-is in the appropriate
            # before/after bucket.  Once we've seen any program-flash
            # data record, every subsequent line goes to "post".
            if seen_flash:
                post_lines.append(ln)
            else:
                pre_lines.append(ln)
            continue

        if rec_type == 0x01:  # End-Of-File
            if seen_flash:
                post_lines.append(ln)
            else:
                pre_lines.append(ln)
            continue

        if rec_type == 0x00 and cur_seg_in_app:
            phys_addr = (seg_high16 << 16) | rec_addr
            data = bytes.fromhex(ln[9:9 + rec_size * 2])
            in_app_window = (
                _K20_APP_WINDOW_START <= phys_addr < _K20_APP_WINDOW_END_EXCL
            )
            if in_app_window:
                # First app-window data record marks the splice point.
                if not seen_flash:
                    seen_flash = True
                    flash_in_pre = False
                # Add to mem map (don't preserve the raw line — we'll
                # re-emit the entire window).
                for offset, byte_val in enumerate(data):
                    target = phys_addr + offset
                    if (
                        _K20_APP_WINDOW_START
                        <= target
                        < _K20_APP_WINDOW_END_EXCL
                    ):
                        flash_map[target] = byte_val
                # Any record bytes that fall OUTSIDE the app window
                # (overflowing past 0x77FF, etc.) are dropped — the
                # source-build for V1.7 should never emit those, and
                # the bootloader region records still come through
                # untouched in their original lines.
                for offset, byte_val in enumerate(data):
                    target = phys_addr + offset
                    if not (
                        _K20_APP_WINDOW_START
                        <= target
                        < _K20_APP_WINDOW_END_EXCL
                    ):
                        # Re-emit the overflow byte as a separate line
                        # in the post-bucket.  This is a defensive case
                        # — V1.7 source doesn't currently produce any.
                        post_lines.append(_emit_data_record(
                            (target & 0xFFFF), bytes([byte_val])
                        ))
                continue
            # Data record in segment 0x0000 but outside the app window
            # (e.g., the bootloader region at 0x7800..0x7FFF) — keep
            # verbatim in the appropriate bucket.
            if seen_flash:
                post_lines.append(ln)
            else:
                pre_lines.append(ln)
            continue

        # Non-app-segment data record (CONFIG / EEPROM / IDLOCS / etc.)
        if seen_flash:
            post_lines.append(ln)
        else:
            pre_lines.append(ln)

    if not seen_flash:
        # No program-flash records at all — nothing to pad.  Leave the
        # hex untouched.
        return

    # Re-emit the program-flash window as contiguous 16-byte records.
    padded_lines: List[str] = []
    for chunk_addr in range(
        _K20_APP_WINDOW_START,
        _K20_APP_WINDOW_END_EXCL,
        _K20_RECORD_SIZE,
    ):
        chunk = bytes(
            flash_map.get(chunk_addr + i, _K20_PAD_BYTE)
            for i in range(_K20_RECORD_SIZE)
        )
        padded_lines.append(_emit_data_record(chunk_addr & 0xFFFF, chunk))

    out_lines = pre_lines + padded_lines + post_lines
    hex_path.write_text("\n".join(out_lines) + "\n", encoding="ascii")


def build_shifted_asm(source_asm: Path, output_asm: Path) -> Path:
    """Create the V1.7 shift-test source from the canonical commented source.

    Transformations (spec §A4):

    1.  Insert 0x111 NOP words (= 0x222 bytes) of padding immediately before
        the first application-code label after the vector block
        (``control_core_service_004C`` at stock 0x004C).
    2.  Pin the bootloader at 0x7800 with an explicit ``org 0x7800``
        directive before ``bootloader_entry:`` and strip the erased-flash
        ``dw 0xffff`` fill that preceded the bootloader, because the
        shift pushes the fill past 0x7800 and would collide.

    The shifted source assembles with gpasm and produces a hex image whose
    vector block (0x0000–0x004B) is byte-identical to stock V1.6b, whose
    application code starts at 0x026E (stock 0x004C + 0x222), and whose
    bootloader (0x7800–0x7FFF) is byte-identical to stock.

    The RAM include file (``dlcp_control_ram.inc``) is symlinked into the
    output directory so gpasm can resolve it.
    """
    text = source_asm.read_text(encoding="utf-8")
    lines = text.split("\n")
    out: List[str] = []
    padding_inserted = False
    bootloader_pinned = False

    # Strip the leading ``dw 0xffff`` run immediately above bootloader_entry.
    # Walk from the bottom to find the bootloader and the last preceding
    # non-``dw 0xffff`` line, then blank out those dw lines.
    bootloader_idx = None
    for i, line in enumerate(lines):
        if line.startswith(f"{_BOOTLOADER_LABEL}:"):
            bootloader_idx = i
            break
    if bootloader_idx is None:
        raise RuntimeError(
            f"Could not find '{_BOOTLOADER_LABEL}:' in {source_asm}"
        )

    # Walk upward from bootloader_idx until we see a non-blank, non-``dw 0xffff``
    # line.  Mark the ``dw 0xffff`` lines for removal and record the insertion
    # point for ``org 0x7800``.
    drop_start = bootloader_idx
    i = bootloader_idx - 1
    while i >= 0:
        s = lines[i].strip()
        if s == "" or s == "dw      0xffff" or s == "dw 0xffff":
            drop_start = i
            i -= 1
            continue
        break
    dropped_range = range(drop_start, bootloader_idx)

    for idx, line in enumerate(lines):
        if idx in dropped_range:
            # Skip the pre-bootloader dw 0xffff fill; replaced by org below.
            continue
        if not bootloader_pinned and idx == bootloader_idx:
            out.append("")
            out.append("; --- Bootloader pinned at 0x7800 ---")
            out.append("        org     0x7800")
            out.append("")
            out.append(line)
            bootloader_pinned = True
            continue

        if not padding_inserted and any(
            line.startswith(f"{label}:") for label in _VECTOR_BLOCK_END_LABELS
        ):
            out.append("")
            out.append("; --- Relocation safety padding (shift test) ---")
            out.append(
                f"        fill    0x0000, 0x{_SHIFT_BYTES:X}"
                f"    ; 0x{_SHIFT_WORDS:X} NOP words = 0x{_SHIFT_BYTES:X} bytes"
            )
            out.append("")
            padding_inserted = True

        out.append(line)

    if not padding_inserted:
        raise RuntimeError(
            "Could not find first-app-code label to anchor padding; "
            f"expected one of: {', '.join(_VECTOR_BLOCK_END_LABELS)}"
        )
    if not bootloader_pinned:
        raise RuntimeError("Could not pin bootloader at 0x7800")

    output_asm.write_text("\n".join(out), encoding="utf-8")

    # Symlink the RAM include so gpasm can resolve it.
    ram_inc = source_asm.parent / _RAM_INC_NAME
    target_inc = output_asm.parent / _RAM_INC_NAME
    if ram_inc.exists() and not target_inc.exists():
        target_inc.symlink_to(ram_inc.resolve())

    return output_asm


__all__ = [
    "assemble_v17",
    "build_shifted_asm",
    "parse_v17_symbols",
]

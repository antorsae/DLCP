# V3.4 Size-Reclaim Campaign — Findings and Landed Result

Status: **2000-byte target met 2026-06-16** by the T-series size-reclaim
campaign.  Current canonical MAIN V3.4 rev `0x0083` ends at `0x442E`, leaving
**2002 contiguous free bytes** before the fixed `0x4C00` preset-table wall.
The canonical build and RAM-bank safety gate both pass at this revision.

Latest accepted 2026-06-16 slices include: counted POSTINC2->POSTINC1 copy
helper reuse, shared low-nibble hex emitter, page-1 FSR setup wrapper, direct
gate returns, parser frame-gap watchdog inlining, and USB reinit helper
inlining.  Preset banks remain fixed at `0x4C00..0x55FF` and
`0x5600..0x5FFF`; no release filename was minted outside the canonical V3.4
builder path.

Historical 2026-06-12 result: margin was **250 bytes by the headroom-gate
measure** (raw listing scan: 252; the gate convention is authoritative), from
a 28-byte starting point.  Landed as the S-series (S1 pair-copy helper, S2
EEPROM-source mode, S3 duplicate-run subroutines, S4 block descriptors) in
`dlcp_main_v34.asm` rev 0x90.

## Verified-exhausted mechanical classes

All scanners run against the rev-0x89/0x8A source/listing and re-run
against the post-S3 listing (rev 0x8E):

| Class | Result | Evidence |
| --- | --- | --- |
| `call` -> `rcall`, `goto` -> `bra` | **0 sites in relative reach** both scans; nearest miss 1047 words | reach scanner over the `.lst` symbol table |
| Helper factoring of repeated runs (>= 4 instr) | only the movff copy chains score above the call/return overhead | normalized n-gram scan, skip-shadow-aware |
| Cross-jump tail merges | zero candidates >= 8 B | suffix-group scan keyed on identical terminator |
| Shift-loop wrappers (`movlw K / rcall kernel / decfsz` idiom) | pairs only -> +-0 B after wrapper cost | idiom scan, 5 instances over 4 kernels |
| 32-bit constant staging quads | no repeated (cells, value) groups | quad scan |
| n=3..4 movff runs as descriptors | exactly break-even (movff = 4 B; n=4 descriptor = 16 B) | arithmetic; the original n>=5 cut was correct |

## The chain_copy engine (S1/S2/S4) — landed

A single table-driven copier replaces 15 inline copy runs.  Call shape
(descriptor as ONE `db` directive — see lesson 5):

```asm
    call        chain_copy, 0x0
    db          srcPage, dstPage, s0,d0,c0, s1,d1,c1, ..., 0xFF[, 0xFF]
```

- header: physical high bytes; `srcPage == 0xEE` switches the pair source
  to EEPROM via `eeprom_read_byte_at_w` (S2) — used by the boot settings
  load (13 cells incl. the 0x0D/0x14 odd forms) and the per-route trim
  load (0x10..0x13 -> 0x09B..0x09E).
- rows: `(srcL, dstL, count)` contiguous blocks (S4); scattered singles
  cost 3 B/cell, so one all-scattered site (the bank-1 settings restore)
  stayed inline movff.
- exit: TOS rewritten from TBLPTR (movf/movwf — movff may not target
  TOSx), odd resume PC consumes the pad byte; **BSR = 0 on exit, always**
  (block counters live in bank 3 and the engine banks there).
- scratch: `chain_copy_srch/dsth/srcl/dstl/cnt` at 0x3C5..0x3C9 (bank 3
  upper, movff-only, ISR-untouched, no stock aliasing).

S3: four duplicated 4-cell movff runs factored into plain subroutines
(`stage_tas3108_coeff_input_scratch`, `copy_transform_shadow_to_math_operand`, `copy_math_operand_to_secondary_shadow`,
`adc_stage_division_operands_from_sample_window`).

## Margin ledger

| Step | Margin |
| --- | --- |
| start (rev 0x86..0x8B pristine) | 28-30 B |
| S1 pair-mode chain_copy, 14 sites | 74 B |
| S2 EEPROM-source mode, 2 sites (+pins) | 120 B |
| S3 duplicate-run subroutines, 4 pairs | 154 B |
| S4 block descriptors + single-db packing | **250 B** (gate measure) |
| FIELD safety/counter work through rev 0xA4 | 10 B |
| T1 SRC4382 secondary-write table walker, rev 0xA5 | 102 B |
| FIELD-9/FIELD-10 safety work through rev 0xAC | **14 B** |
| T2 `fw_update_commit_hid_payload_page` pointerized HID upload copy, rev 0xAF | **70 B** |
| T3 boot-marker EEPROM compare peephole, rev 0xB0 | **80 B** |
| T4 direct-zero and FSR post-decrement peepholes, rev 0xB1 | **86 B** |
| T5 channel-config `cpfseq` dirty checks, rev 0xB2 | **122 B** |
| T6 WREG access-bank store peepholes, rev 0xB3 | **158 B** |
| T7 redundant live-W reload/copy peepholes, rev 0xB4 | **174 B** |
| T8 redundant local `movlb 0` assertions, rev 0xB5 | **180 B** |
| T9 HID upload-family range dispatch, rev 0xB6 | **198 B** |
| T10 UART terminal-recovery tail branch, rev 0xB7 | **200 B** |
| T11 local branch-trampoline collapses, rev 0xB8 | **206 B** |
| T12 SRC non-PCM Z-flag reuse, rev 0xB9 | **208 B** |
| T13 I2C timeout recovery tail branches, rev 0xBA | **230 B** |
| T14 unconditional helper tail branches, rev 0xBB | **238 B** |
| T15 preset-target compare helper, rev 0xBC | **248 B** |
| T16 volume-unmuted fall-through branch, rev 0xBD | **250 B** |
| T17 boolean staging/file-clear peepholes, rev 0xBE | **266 B** |
| T18 cmd19 status bit-fanout rotate carry, rev 0xBF | **300 B** |
| T19 EEPROM-write GIE snapshot peephole, rev 0xC0 | **302 B** |
| T20 cmd03 mute-off shared refresh tail, rev 0xC1 | **306 B** |
| T22 flash page/USB endpoint helper pair, rev 0xC4 | **324 B** |
| T23 fw-update status-buffer TX helper, rev 0xC5 | **332 B** |
| T24 CONFIG flash-write tail helper, rev 0xC6 | **340 B** |
| T25 cmd03 mute-refresh staging helper, rev 0xC7 | **348 B** |
| T26 Timer3 0xF830 preload helper, rev 0xC8 | **352 B** |
| T27 filename seqlock/base helpers, rev 0xC9 | **360 B** |
| T28 USB 0x5A/0x40 staging helper, rev 0xCA | **370 B** |
| T29 signed-high compare prelude helper, rev 0xCB | **374 B** |
| T30 FSR1 table-pointer read helper, rev 0xCC | **384 B** |
| T31 flash-write right-shift helper reuse, rev 0xCD | **392 B** |
| T32 left-shift helper for flash/math loops, rev 0xCE | **396 B** |
| T33 FSR1 page-1 copy helper, rev 0xCF | **402 B** |
| T34 filename reply id-frame helper, rev 0xD0 | **406 B** |
| T35 FSR2 stock_003/004 offset helper, rev 0xD1 | **410 B** |
| T36 USB saved-FSR2 setup helper, rev 0xD2 | **416 B** |
| T37 EEPROM-byte wrapper reuse in boot copy loops, rev 0xD3 | **428 B** |
| T38 runtime EEPROM metadata write helper, rev 0xD4 | **434 B** |
| T39 EEPROM read-to-INDF2 loop helper, rev 0xD5 | **436 B** |
| T40 chain-role UART/oscillator setup helper, rev 0xD6 | **440 B** |
| T41 LATA audio-pin clear helper, rev 0xD7 | **446 B** |
| T42 FSR2 bank-0 stock_007 helper, rev 0xD8 | **454 B** |
| T43 BF frame header TX helper, rev 0xD9 | **466 B** |
| T44 BF byte helper reuse, rev 0xDA | **472 B** |
| T45 firmware-update status clear helper, rev 0xDB | **482 B** |
| T46 parser forwarded-byte TX helper, rev 0xDC | **488 B** |
| T47 HID cmd04 staging helper, rev 0xDE | **490 B** |
| T48 shared I2C START-after-idle helper, rev 0xDF; current rebuild rev 0xE1 after rejected T49 | **496 B** |
| T50 firmware-update address compare helper, rev 0xE2; current rebuild rev 0xE4 after rejected T51 | **506 B** |
| T51 reachable flash-read helper `call` -> `rcall`, rev 0xE5 | **508 B** |
| T52 firmware-update 16-bit accumulator helper, rev 0xE6 | **512 B** |
| T53 firmware-update staging helper, rev 0xE7 | **514 B** |
| T54 rail/ADC threshold compare helper, rev 0xE8 | **522 B** |
| T55 volume DSP success-path redundant bank select removal, rev 0xE9 | **524 B** |
| T56 preset apply cursor-to-I2C helper, rev 0xEA | **544 B** |
| T57 preset apply cursor initialization helper, rev 0xEB | **552 B** |
| T58 preset apply cursor advance helper, rev 0xEC | **558 B** |
| T59 firmware-update duplicate nibble-mask peephole, rev 0xED | **560 B** |
| T60 firmware-update hex-digit helper reuse, rev 0xEE | **576 B** |
| T61 flash-write TBLPTR staging helper, rev 0xEF | **582 B** |
| T62 newly reachable far helper `rcall`s, rev 0xF0 | **586 B** |
| T63 math operand middle-copy helper, rev 0xF1 | **592 B** |
| T64 USB descriptor TBLPTR staging helper, rev 0xF2 | **596 B** |
| T65 USB service `stock_096` update helper, rev 0xF3 | **614 B** |
| T66 USB `stock_116` bank-store helper, rev 0xF4 | **620 B** |
| T67 i2c_apply_channel_route_sync_burst bank-0 clear wrapper, rev 0xF5 | **628 B** |
| T68 cmd_dispatch reg1f route-3 tail reuse, rev 0xF6 | **634 B** |
| T69 USB `stock_0C8`/offset prelude helper, rev 0xF7 | **636 B** |
| T70 UART TX retry tail reuse, rev 0xF8 | **642 B** |
| T71 Timer3 stop helper reuse, rev 0xF9 | **652 B** |
| T72 MSSP hard-reset SMP/master prelude helper, rev 0xFA | **662 B** |
| T73 LATA3/4/5 audio-pin clear tail share, rev 0xFB | **666 B** |
| T74 newly reachable `diag_inc_sat_fsr0` `rcall`, rev 0xFC | **668 B** |
| T75 TAS3108 reg1F zero-byte TX helper, rev 0xFD | **670 B** |
| T76 preset APPLY tail branches, rev 0xFE | **674 B** |
| T77 newly reachable SRC status-read timeout recovery `rcall`, rev 0xFF | **676 B** |
| V3.4 16-bit cmd 0x25 identity/display policy, rev 0x0001 | **669 B** |
| T78 UART channel-config mirror helper, rev 0x0002 | **689 B** |
| T79 route-bit I2C selector peephole, rev 0x0003 | **715 B** |
| T80 I2C random-read timeout tail cross-jump, rev 0x0004 | **719 B** |
| T81 redundant bank-select cleanup, rev 0x0005 | **727 B** |
| T82 math result FSR2 rewind tail share, rev 0x0006 | **731 B** |
| T83 HID settings-upload route-bit FSR2 rebuild, rev 0x0007 | **783 B** |
| T84 `i2c_emit_tas3108_coeff_from_staged_float` four-byte chain-copy descriptors, rev 0x0008 | **795 B** |
| T85 `i2c_emit_tas3108_coeff_from_staged_float` middle four-byte chain-copy descriptor, rev 0x0009 | **801 B** |
| T86 filename reply state-machine branch peepholes, rev 0x000A | **813 B** |
| T87 math counted-call repeat helpers, rev 0x000B | **827 B** |
| T88 volume-DSP four-byte chain-copy descriptors, rev 0x000C | **839 B** |
| T89 core 38a2 + volume mirror chain-copy descriptors, rev 0x000D | **863 B** |
| T90 math operand near chain-copy descriptors, rev 0x000E | **919 B** |
| T91 coeff staging chain-copy descriptors, rev 0x000F | **931 B** |
| T92 `float32_exp_limit1024_in_place` near chain-copy descriptors, rev 0x0010 | **955 B** |
| T93 math result helper chain-copy descriptors, rev 0x0011 | **985 B** |
| T94 S3 helper-body chain-copy descriptors, rev 0x0012 | **1005 B** |
| T95 trim mirrors + core 3398 chain-copy descriptors, rev 0x0013 | **1035 B** |
| T96 flash-write address snapshot chain-copy descriptor, rev 0x0014 | **1043 B** |
| T97 `float32_multiply_primary_by_secondary_in_place` final-save chain-copy descriptor, rev 0x0015 | **1051 B** |
| T98 core 3e0a + EEPROM writeback chain-copy descriptors, rev 0x0016 | **1059 B** |
| T100 reachable call/goto conversions, final accepted rev 0x001E | **1081 B** |
| T101 route-sync mailbox helper reuse, rev 0x001F | **1091 B** |
| T102 `usb_ep0_arm_out_pingpong_bd` duplicate `stock_119` store removal, rev 0x0020 | **1095 B** |
| T103 `float32_add_secondary_to_primary_in_place` decrement/mask helper, rev 0x0021 | **1099 B** |
| T104 I2C `stock_006` STOP helper, rev 0x0022 | **1101 B** |
| T105 cmd26 filename revision bit-test guards, rev 0x0023 | **1105 B** |
| T106 USB endpoint completion-marker FSR0 helper, rev 0x0024 | **1121 B** |
| T107 ADC division compare/subtract helper, rev 0x0025 | **1131 B** |
| T108 USB descriptor dirty-return tail, rev 0x0026 | **1135 B** |
| T109 `load_fsr2_from_target_ptr` helper + standby `rcall`, rev 0x0027 | **1163 B** |
| T110 `usb_ep0_arm_out_pingpong_bd` FSR2 rewind peephole, rev 0x0028 | **1167 B** |
| T111 firmware-update init clear prep reuse, rev 0x0029 | **1175 B** |
| T112 USB filename compare + `setup_fsr2_page1_from_w` compact forms, rev 0x002A | **1187 B** |
| T113 `propagate_carry_to_u32_scratch_high24` helper, rev 0x002B | **1189 B** |
| T114 settings source clamp W-literal reuse, rev 0x002C | **1195 B** |
| T115 trim clamp W-literal reuse, rev 0x002D | **1201 B** |
| T116 cumulative XOR compares in UART route/SRC index, rev 0x002E | **1205 B** |
| T117 branch-tail slice, rev 0x002F | **1211 B** |
| T118 zero-instruction alias entries, rev 0x0030 | **1225 B** |
| T119 computed-volume guard W=0 reuse, rev 0x0031 | **1229 B** |
| T120 dead-W zero tests via `tstfsz`, rev 0x0032 | **1243 B** |
| T121 high-window `chain_copy` `rcall` trampoline, rev 0x0033 | **1275 B** |
| T122 low-window `chain_copy` `rcall` trampoline, rev 0x0034 | **1289 B** |
| T123 `cmd26` filename source/range peepholes, rev 0x0035 | **1297 B** |
| T124 `float32_pack_mantissa_exponent_sign` zero-test simplification, rev 0x0036 | **1329 B** |
| T125 USB endpoint pointer/clear common tails, rev 0x0037 | **1341 B** |
| T126 immediate fall-through branch removals, rev 0x0038 | **1351 B** |
| T127 low-page USB descriptor dirty helper, rev 0x0039 | **1357 B** |
| T128 in-range branch inversions, rev 0x003A | **1377 B** |
| T129 boundary-range cmd03 dispatch branch inversion, rev 0x003B | **1379 B** |
| T130 firmware-update branch trampoline, rev 0x003C | **1381 B** |
| T131 cmd26 other-EEPROM source-kind helper, rev 0x003D | **1383 B** |
| T132 cmd26 source-kind EEPROM-base encoding, rev 0x003E | **1391 B** |
| T133 firmware-update static hex-byte POSTINC2 helper, rev 0x003F | **1423 B** |
| T134 firmware-update computed sequential hex writer, rev 0x0040 | **1451 B** |
| T135 cmd19 status-bit fanout helper, rev 0x0043 | **1461 B** |
| T136 logical-vs-computed volume compare helper, rev 0x0044 | **1473 B** |
| T137 HID route/cache byte-span compare helper, rev 0x0045 | **1497 B** |
| T138 generic byte-span compare reused for HID filename cache, rev 0x0046 | **1517 B** |
| T139 local peephole batch, rev 0x0047 | **1531 B** |
| T140 route-bit refresh loop, rev 0x0048 | **1565 B** |
| T141 firmware-update UART block-send helper, rev 0x0049 | **1579 B** |
| T142 firmware-update RAM-clear length helper, rev 0x004A | **1585 B** |
| T143 HID cmd44 counted snapshot copier, rev 0x004B | **1591 B** |
| T144 cold-init POSTINC0 clear helper, rev 0x004C | **1607 B** |
| T145 version-response literal peephole + direct tails, rev 0x004D | **1609 B** |
| T146 return-value `retlw` peepholes, rev 0x004E | **1613 B** |
| T147 generic POSTINC copy helper reuse, rev 0x004F | **1619 B** |
| T148-T180 final reclaim wave, rebuilt rev 0x0083 | **2002 B** |

Rev `0x0083` keeps the T124 scratch zero-fanout removal but restores the live
`float32_pack_mantissa_exponent_sign` final exponent merge (`stock_007 -> stock_006`).  The
bad rev computed zero TAS3108 volume coefficients after unmute/retry paths; the
fixed temp probe restores the expected `0x30` payload `0014408f`.

## T1 SRC4382 secondary-write table walker — landed 2026-06-14

T1 was a reclaim wave, not the final shipped margin.  It rebuilt the reserve
from the 10-byte floor to 102 bytes at rev `0xA5`; later FIELD-9/FIELD-10 safety
work consumed most of that reserve and the pre-T2 rev `0xAC` line sat at
14 bytes.

Scope:

- `i2c_secondary_apply_wake_init_table`: the ordered SRC4382/cfg71 cold-init write stream
  was converted from 16 inline `(value -> stock_006, register -> write)`
  blocks to `i2c_secondary_wake_init_table` plus `i2c_secondary_write_table_rows`.
- `hw_standby_shutdown`: the three rail-drop writes
  `(0x00,0x1B)`, `(0x00,0x1C)`, `(0x00,0x1D)` reuse the same row walker via
  `hw_standby_shutdown_i2c_table`.

Measured result:

- Before T1: `listing_app_end=0x4BF6`, free bytes before `0x4C00` = 10.
- After T1 canonical rebuild: `listing_app_end=0x4B9A`, free bytes before
  `0x4C00` = 102.
- Net reclaim: **+92 bytes** of margin.
- Canonical build: `scripts/build_v34_release.py`, EEPROM rev
  `0xA4 -> 0xA5`.

## T2 HID upload flash-copy pointerization — landed 2026-06-15

Scope:

- `fw_update_commit_hid_payload_page` used to recompute both source and destination FSR
  pointers for every byte in the 20-byte HID/programming payload copy.
- T2 stages the two initial pointers once, keeps the legacy `stock_11B` source
  skew (`0x011E` when zero, `0x011C` when nonzero), then copies with
  `movff POSTINC2, POSTINC1` and a 20-byte counter in `stock_01F`.
- A final exact-size cleanup uses the existing generated `usb_hid_out_arg3_phys`
  alias to stage the default source pointer with `lfsr` instead of literal
  `FSR2L`/`FSR2H` writes.
- No new descriptor stream or table was introduced by this batch; existing
  `chain_copy`/`db` descriptor packing remains covered by the refactoring
  source test and was inspected in `src/dlcp_fw/asm/dlcp_main_v34.lst`.

Measured result:

- Baseline canonical rebuild before code edit: EEPROM rev `0xAC -> 0xAD`,
  `listing_app_end=0x4BF2`, `last_used_pre_preset_b=0x4BF1`,
  `contiguous_free_before_0x4C00=14 bytes`, `free_object_words=7`.
- After T2 canonical rebuild and the `lfsr` cleanup: EEPROM rev
  `0xAE -> 0xAF`, `listing_app_end=0x4BBA`,
  `last_used_pre_preset_b=0x4BB9`,
  `contiguous_free_before_0x4C00=70 bytes`, `free_object_words=35`.
- Net reclaim: **+56 bytes** of margin.

Liveness/safety assumptions:

- `stock_01F` is local scratch for the copy loop after entry and is dead before
  the routine returns; later references are in separate routines.
- `FSR1`/`FSR2`, W, and STATUS were already clobbered by the original per-byte
  address computation.
- Valid `stock_0C5` staging offsets stay inside the 0x0300 page; the new setup
  still preserves the carry path into `FSR1H`.
- The old nonzero `stock_11B` source-skew mode remains present structurally and
  the normal HFD-style `0x07` upload path is exercised through native firmware
  HID dispatch.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xAE -> 0xAF)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v33_flash_remap_runtime.py
# 4 passed in 9.55s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py
# 59 passed, 1 xfailed in 92.97s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -n 16 -q \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py
# 137 passed, 3 xfailed in 135.29s
```

The three broad-gate xfails are the known `chain_copy` interrupt-safety proof and
the two Diagnostics-page front-panel STBY repros.  Exploratory gate status:
accepted net gain since the last exploratory run is 56 bytes, below the 100-byte
threshold, so no new exploratory run was required for T2.

## T3 boot-marker EEPROM compare peephole — landed 2026-06-15

Scope:

- `boot_init_peripherals_and_enter_adc_gate` accepted either EEPROM boot marker `0x77` or `0x88`
  at `EEADR=0xFF`, but stock code reread the same EEPROM byte for the second
  comparison.
- T3 keeps the single EEPROM read and first `xorlw 0x77`; on miss it applies
  `xorlw 0xFF`, which transforms the live W value from `byte ^ 0x77` to
  `byte ^ 0x88`.
- The accepted markers, `stock_003=0xFF` / `stock_004=0x00` scratch state, and
  downstream `stock_0FE` flash-write gate are preserved.

Measured result:

- Before T3: rev `0xAF`, `contiguous_free_before_0x4C00=70 bytes`.
- After T3 canonical rebuild: EEPROM rev `0xAF -> 0xB0`,
  `listing_app_end=0x4BB0`, `last_used_pre_preset_b=0x4BAF`,
  `contiguous_free_before_0x4C00=80 bytes`, `free_object_words=40`.
- Net reclaim: **+10 bytes** of margin for T3, **+66 bytes** since the last
  exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xAF -> 0xB0)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py
# 62 passed, 1 xfailed in 95.59s
```

The focused xfail is the known `chain_copy` interrupt-safety proof.  Exploratory
gate status: accepted net gain since the last exploratory run is 66 bytes, below
the 100-byte threshold, so no new exploratory run was required for T3.

## T4 direct-zero and FSR post-decrement peepholes — landed 2026-06-15

Scope:

- `cmd_dispatch_gated__apply_unmuted_volume_dirty`: replace zero-copy
  `movff stock_0A4 -> stock_0B0` with a direct `clrf stock_0B0`.
- `adaptive_baud_select`: replace zero-copy `movff stock_093 -> stock_0AB`
  with a direct `clrf stock_0AB`.
- `fw_update_signature_status_word_helper`: replace `movlw 0x00; iorwf POSTDEC2,F`, used
  only to read and post-decrement the high byte without changing it, with
  `movf POSTDEC2,F`.

Measured result:

- Before T4: rev `0xB0`, `contiguous_free_before_0x4C00=80 bytes`.
- After T4 canonical rebuild: EEPROM rev `0xB0 -> 0xB1`,
  `listing_app_end=0x4BAA`, `last_used_pre_preset_b=0x4BA9`,
  `contiguous_free_before_0x4C00=86 bytes`, `free_object_words=43`.
- Net reclaim: **+6 bytes** of margin for T4, **+72 bytes** since the last
  exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB0 -> 0xB1)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py
# 63 passed, 1 xfailed in 94.86s
```

The focused xfail is the known `chain_copy` interrupt-safety proof.  Exploratory
gate status: accepted net gain since the last exploratory run is 72 bytes, below
the 100-byte threshold, so no new exploratory run was required for T4.

## T5 channel-config `cpfseq` dirty checks — landed 2026-06-15

Scope:

- The six serial channel-config handlers for `stock_060..065` used to copy
  `current_cmd_data` into the active slot with `movff`, compare active vs
  mirror with `xorwf`, conditionally dirty `event_flags.bit4`, then copy active
  to mirror with a second `movff`.
- T5 keeps W loaded with `current_cmd_data`, stores active with `movwf`, uses
  PIC18 `cpfseq mirror` to skip the dirty-bit set when unchanged, then stores
  the mirror with `movwf`.
- This preserves the RAM end state and dirty-on-change contract while dropping
  the stale STATUS dependency from the old compare sequence.  The handlers
  already rely on BSR=0 through surrounding BANKED operands.

Measured result:

- Before T5: rev `0xB1`, `contiguous_free_before_0x4C00=86 bytes`.
- After T5 canonical rebuild: EEPROM rev `0xB1 -> 0xB2`,
  `listing_app_end=0x4B86`, `last_used_pre_preset_b=0x4B85`,
  `contiguous_free_before_0x4C00=122 bytes`, `free_object_words=61`.
- Net reclaim: **+36 bytes** of margin for T5, **+108 bytes** since the last
  exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB1 -> 0xB2)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py
# 121 passed, 1 xfailed in 152.43s
```

The focused xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 1h \
  --seed auto \
  --campaign all \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/sim/current/exploratory/size_reclaim_t5_1h_20260615 \
  --status-interval 60
```

Run:
`artifacts/sim/current/exploratory/size_reclaim_t5_1h_20260615/20260615_175120_95c86448850d70ca`

Summary:

- seed `0x95c86448850d70ca`
- 152 sessions, 19318 events, 14763 observations
- campaigns: `diag=17`, `preset-filename=26`, `ui=27`, `src=14`,
  `preset-phase-sweep=22`, `fault-recovery=15`, `saturation=12`,
  `standby-reset=19`
- incidents: `{'LOW': 4}`, duplicate signatures: 86
- no MEDIUM/HIGH incidents
- LOW incidents:
  - `EXP-000001` early `diag`: `ui.waiting.connected`
  - `EXP-000002..004` `preset-filename`: `link.saturation.delta`
    on `m1_to_ctl`, `m0_to_m1`, and `ctl_to_m0` (`delta=3189`)
- selected oracle cards:
  `artifacts/sim/current/exploratory/size_reclaim_t5_1h_20260615/oracle_cards`
  (`6` top divergence cards + `2` samples)
- read-only judge pass verdict: follow-up, not blocker.  No selected card maps
  directly to the T2-T5 touched code.  The strongest selected concern was
  session `23` (`preset-filename`, zero synthetic faults), where the final card
  sample showed PB state not fully settled after heavy USB filename churn.
- deterministic replay follow-up:
  `scripts/sim_chain_exploratory.py --replay ... --session-id 23` reproduced
  final LCD `Input: / USB Audio`.  A replay with extra post-final settle showed
  the concern was transient: exact final sample had unit 0
  `preset_job_state=2`, but after +60M ticks both MAINs had
  `preset_job_state=0` and `golden_coeff_match=true`; by +120M ticks filename
  dirty flags were clear.  No final-acceptance blocker was found.

The earlier 100-byte exploratory gate was satisfied at rev `0xB2`.  For the
current continuation campaign, the active exploratory threshold is 200 accepted
bytes; the next threshold is counted from the accepted bytes after this run.

## T6 WREG access-bank store peepholes — landed 2026-06-15

Scope:

- Eighteen `movff WREG, <scratch>_phys` stores whose destinations are in the
  PIC18 access-bank low window (`0x003..0x057`) were replaced with single-word
  `movwf <scratch>_acc, ACCESS`.
- The lone remaining `movff WREG` store, `cmd_dispatch_hid_mailbox_enable_phys`, was intentionally
  left alone because `0x0FD` is outside the access-bank low window and would
  need a proven BSR=0 contract to become a one-word `movwf`.
- This peephole preserves W, STATUS, BSR, and all downstream RAM values; it
  only changes the instruction encoding size for access-bank scratch stores.

Measured result:

- Before T6: rev `0xB2`, `contiguous_free_before_0x4C00=122 bytes`.
- After T6 canonical rebuild: EEPROM rev `0xB2 -> 0xB3`,
  `listing_app_end=0x4B62`, `last_used_pre_preset_b=0x4B61`,
  `contiguous_free_before_0x4C00=158 bytes`, `free_object_words=79`.
- Net reclaim: **+36 bytes** of margin for T6, **+36 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB2 -> 0xB3)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 143 passed, 1 xfailed in 274.99s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 22 passed, 1 xfailed in 0.22s
```

The xfail in both focused runs is the known `chain_copy` interrupt-safety
proof.  The T6 source contract pins the compact `movwf ..., ACCESS` shape and
the deliberate `cmd_dispatch_hid_mailbox_enable_phys` exception.

Exploratory gate status: the current continuation campaign requires one
30-minute exploratory chain hunt every 200+ accepted bytes.  T6 adds 36 accepted
bytes since the last exploratory run, so no new exploratory gate is due yet.

## T7 redundant live-W reload/copy peepholes — landed 2026-06-15

Scope:

- Removed redundant `movf <scratch>, W` reloads immediately after `movwf`
  when W was still the live original value.
- Replaced a few adjacent access-bank/SFR copies with `movwf` while W was still
  live: `saved_w -> SSPBUF`, `stock_017 -> stock_016`, the first
  `stock_006 -> stock_004` copy in `uart_tx_ascii_hex_byte`, and
  `stock_011 -> stock_003` in `uint8_to_float32_and_save`.
- The later copies in those routines were left intact when intervening calls or
  arithmetic clobbered W.

Measured result:

- Before T7: rev `0xB3`, `contiguous_free_before_0x4C00=158 bytes`.
- After T7 canonical rebuild: EEPROM rev `0xB3 -> 0xB4`,
  `listing_app_end=0x4B52`, `last_used_pre_preset_b=0x4B51`,
  `contiguous_free_before_0x4C00=174 bytes`, `free_object_words=87`.
- Net reclaim: **+16 bytes** of margin for T7, **+52 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB3 -> 0xB4)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 144 passed, 1 xfailed in 271.92s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract added for T6 now also rejects the redundant live-W reload/copy forms
removed by T7.

Exploratory gate status: accepted bytes since the last exploratory run are
52/200, so no new 30-minute exploratory gate is due yet.

## T8 redundant local `movlb 0` assertions — landed 2026-06-15

Scope:

- Removed three local `movlb 0` assertions whose only incoming paths already
  held BSR=0 and whose intervening instructions do not modify BSR:
  `usb_sie_endpoint_pump__select_ep0_out_bd`, the final `INDF2` set in
  `usb_ep0_arm_out_pingpong_bd`, and the second assertion in
  `i2c_timeout_skip_bus_probe`.
- Other duplicate-looking bank assertions were kept where a join can be reached
  from a call, an EEPROM-read branch, or a bank-4 path.

Measured result:

- Before T8: rev `0xB4`, `contiguous_free_before_0x4C00=174 bytes`.
- After T8 canonical rebuild: EEPROM rev `0xB4 -> 0xB5`,
  `listing_app_end=0x4B4C`, `last_used_pre_preset_b=0x4B4B`,
  `contiguous_free_before_0x4C00=180 bytes`, `free_object_words=90`.
- Net reclaim: **+6 bytes** of margin for T8, **+58 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB4 -> 0xB5)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 145 passed, 1 xfailed in 271.25s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract now rejects the three removed redundant bank assertions.

Exploratory gate status: accepted bytes since the last exploratory run are
58/200, so no new 30-minute exploratory gate is due yet.

## T9 HID upload-family range dispatch — landed 2026-06-15

Scope:

- The HID XOR dispatch ladder mapped commands `0x07..0x0B` to the same upload
  handler.  T9 replaced the five-command XOR ladder with a compact range check:
  reload original opcode from `i2c_coeff_2`, compute `cmd - 0x07`, and branch
  to the upload handler when the value is `0..4`.
- The `0x0C` check was kept explicitly by reloading the original opcode and
  restoring the same `cmd ^ 0x0C` W shape before the later `0x40/0x42/0x43/0x44`
  checks.
- A direct `bc hid_command_dispatch__stage_upload_payload` form was rejected because PIC18
  conditional branches are short-range; `gpasm` failed with
  `Argument out of range (-169 not between -128 and 127)`.  The accepted shape
  uses local `bnc` over a `bra`.

Measured result:

- Before T9: rev `0xB5`, `contiguous_free_before_0x4C00=180 bytes`.
- After T9 canonical rebuild: EEPROM rev `0xB5 -> 0xB6`,
  `listing_app_end=0x4B3A`, `last_used_pre_preset_b=0x4B39`,
  `contiguous_free_before_0x4C00=198 bytes`, `free_object_words=99`.
- Net reclaim: **+18 bytes** of margin for T9, **+76 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# rejected direct-BC attempt: gpasm Error[126] Argument out of range
# accepted shape built canonical V3.4 release ... (EEPROM rev 0xB5 -> 0xB6)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 146 passed, 1 xfailed in 267.66s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract pins the compact HID range-dispatch shape and removal of the old
ladder labels.

Exploratory gate status: accepted bytes since the last exploratory run are
76/200, so no new 30-minute exploratory gate is due yet.

## T10 UART terminal-recovery tail branch — landed 2026-06-15

Scope:

- `uart_tx_timeout` used a one-word `v31_hard_reset_jump2` trampoline after the
  second bounded TRMT timeout.
- The current layout places `hard_reset` within PIC18 short conditional-branch
  reach, so T10 changes the timeout branch to `bc hard_reset` and removes the
  trampoline label/body.
- The panic behavior is unchanged: the retry still re-runs `uart_config`, waits
  once more, and enters `hard_reset` only on the second bounded timeout.

Measured result:

- Before T10: rev `0xB6`, `contiguous_free_before_0x4C00=198 bytes`.
- After T10 canonical rebuild: EEPROM rev `0xB6 -> 0xB7`,
  `listing_app_end=0x4B38`, `last_used_pre_preset_b=0x4B37`,
  `contiguous_free_before_0x4C00=200 bytes`, `free_object_words=100`.
- Net reclaim: **+2 bytes** of margin for T10, **+78 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB6 -> 0xB7)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v32_no_pop_flash_entry.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_diag_src_counters.py
# 74 passed, 1 xfailed in 72.63s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract pins direct `bc hard_reset` and the absence of the old trampoline.

Exploratory gate status: accepted bytes since the last exploratory run are
78/200, so no new 30-minute exploratory gate is due yet.

## T11 local branch-trampoline collapses — landed 2026-06-15

Scope:

- Collapsed the final HID unknown-command trampoline by branching directly to
  `hid_command_dispatch__unsupported_opcode`.
- Collapsed two local `shift_003_006_right_clear_c` return trampolines by branching
  directly to `usb_ep0_dispatch_hid_setup_request__return`.
- Callable trampolines and preset-job labels were left alone; the UART parser
  join did not save code once the fall-through path was preserved.

Measured result:

- Before T11: rev `0xB7`, `contiguous_free_before_0x4C00=200 bytes`.
- After T11 canonical rebuild: EEPROM rev `0xB7 -> 0xB8`,
  `listing_app_end=0x4B32`, `last_used_pre_preset_b=0x4B31`,
  `contiguous_free_before_0x4C00=206 bytes`, `free_object_words=103`.
- Net reclaim: **+6 bytes** of margin for T11, **+84 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB7 -> 0xB8)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 144 passed, 1 xfailed in 269.93s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract pins the removed local trampoline labels.

Exploratory gate status: accepted bytes since the last exploratory run are
84/200, so no new 30-minute exploratory gate is due yet.

## T12 SRC non-PCM Z-flag reuse — landed 2026-06-15

Scope:

- In `poll_src4382_route_monitor__check_scan_index3`, the SRC4382 non-PCM random-read success
  path already returns W with STATUS.Z reflecting the received byte; the helper
  clears only C before returning.
- T12 stores W to `src4382_audio_format_latch_b0` and lets the existing `bnz` consume the live Z
  flag, removing the redundant `movf src4382_audio_format_latch_b0, W`.
- The timeout branch still exits before this path via C, so timeout behavior is
  unchanged.

Measured result:

- Before T12: rev `0xB8`, `contiguous_free_before_0x4C00=206 bytes`.
- After T12 canonical rebuild: EEPROM rev `0xB8 -> 0xB9`,
  `listing_app_end=0x4B30`, `last_used_pre_preset_b=0x4B2F`,
  `contiguous_free_before_0x4C00=208 bytes`, `free_object_words=104`.
- Net reclaim: **+2 bytes** of margin for T12, **+86 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB8 -> 0xB9)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v171_v32_source_select_parity.py
# 57 passed, 1 xfailed in 318.62s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract pins the removed SRC non-PCM reload.

Exploratory gate status: accepted bytes since the last exploratory run are
86/200, so no new 30-minute exploratory gate is due yet.

## T13 I2C timeout recovery tail branches — landed 2026-06-15

Scope:

- Converted final-action I2C timeout labels from `call/rcall recovery; return`
  to direct `goto`/`bra` tail branches where the recovery helper already
  returns to the original caller with C=1 and visible BF/08 diagnostics.
- Removed the single-use `preset_job_apply_i2c_recover` wrapper and pointed
  `preset_job_apply_i2c_timeout` directly at `i2c_timeout_recover_advertise`.
- Left timeout paths that must clear W or return a literal (`retlw 0x06`,
  `retlw 0x1F`, random-read zero-on-error) unchanged.

Measured result:

- Before T13: rev `0xB9`, `contiguous_free_before_0x4C00=208 bytes`.
- After T13 canonical rebuild: EEPROM rev `0xB9 -> 0xBA`,
  `listing_app_end=0x4B1A`, `last_used_pre_preset_b=0x4B19`,
  `contiguous_free_before_0x4C00=230 bytes`, `free_object_words=115`.
- Net reclaim: **+22 bytes** of margin for T13, **+108 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xB9 -> 0xBA)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py
# 140 passed, 1 xfailed in 263.22s
```

The xfail is the known `chain_copy` interrupt-safety proof.  Source contracts
pin the timeout tail branches and the removed preset-job wrapper.

Exploratory gate status: accepted bytes since the last exploratory run are
108/200, so no new 30-minute exploratory gate is due yet.

## T14 unconditional helper tail branches — landed 2026-06-15

Scope:

- Converted four unconditional `call/rcall helper; return` tails into direct
  `goto`/`bra` tail branches:
  `wake_input_failed -> send_dsp_fault_status`,
  `cmd_dispatch_gated__input_route_write_complete -> timer0_rearm_50ms_heartbeat`,
  `cmd_dispatch_route_sync_if_dirty -> timer0_rearm_50ms_heartbeat`, and
  `filename_read_source_eep -> eeprom_read_byte`.
- Rejected two nearby conditional-call tails (`usb_hid_mailbox_stage_selector5_if_enabled` and
  `usb_ep1_configure_if_enabled`) because the skip path still needs the local
  `return`; replacing the call with a branch would be break-even.

Measured result:

- Before T14: rev `0xBA`, `contiguous_free_before_0x4C00=230 bytes`.
- After T14 canonical rebuild: EEPROM rev `0xBA -> 0xBB`,
  `listing_app_end=0x4B12`, `last_used_pre_preset_b=0x4B11`,
  `contiguous_free_before_0x4C00=238 bytes`, `free_object_words=119`.
- Net reclaim: **+8 bytes** of margin for T14, **+116 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xBA -> 0xBB)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_diag_src_counters.py
# 141 passed, 1 xfailed in 272.30s
```

The xfail is the known `chain_copy` interrupt-safety proof.  Source contracts
pin the four direct tails.

Exploratory gate status: accepted bytes since the last exploratory run are
116/200, so no new 30-minute exploratory gate is due yet.

## T15 preset-target compare helper — landed 2026-06-15

Scope:

- Factored the repeated `preset_job_target_b2` vs active preset comparison into
  `preset_target_compare_active_bsr2`.
- The helper contract is intentionally narrow: caller has BSR=2, W returns as
  `target` or `target ^ 1` depending on `active_flags.bit2`, and STATUS.Z is
  the same branch predicate as the previous inline sequence.
- The four preset state-machine users are `rcall`-reachable; the wake re-arm
  site uses a far `call` and still saves one instruction word.

Measured result:

- Before T15: rev `0xBB`, `contiguous_free_before_0x4C00=238 bytes`.
- After T15 canonical rebuild: EEPROM rev `0xBB -> 0xBC`,
  `listing_app_end=0x4B08`, `last_used_pre_preset_b=0x4B07`,
  `contiguous_free_before_0x4C00=248 bytes`, `free_object_words=124`.
- Net reclaim: **+10 bytes** of margin for T15, **+126 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xBB -> 0xBC)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py
# 91 passed, 1 xfailed in 206.35s
```

The xfail is the known `chain_copy` interrupt-safety proof.  Source contracts
pin the helper body and all five call sites.

Exploratory gate status: accepted bytes since the last exploratory run are
126/200, so no new 30-minute exploratory gate is due yet.

## T16 volume-unmuted fall-through branch — landed 2026-06-15

Scope:

- Removed `bra cmd_dispatch_gated__select_applied_route_trim` where the target label was the
  immediately following line after the volume-unmuted zero peepholes.
- Nearby branch-to-return hits were rejected because they are loop or
  conditional-exit idioms and do not reduce code size.

Measured result:

- Before T16: rev `0xBC`, `contiguous_free_before_0x4C00=248 bytes`.
- After T16 canonical rebuild: EEPROM rev `0xBC -> 0xBD`,
  `listing_app_end=0x4B06`, `last_used_pre_preset_b=0x4B05`,
  `contiguous_free_before_0x4C00=250 bytes`, `free_object_words=125`.
- Net reclaim: **+2 bytes** of margin for T16, **+128 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xBC -> 0xBD)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py
# 120 passed, 1 xfailed in 142.18s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The zero-peephole
source contract pins the fall-through shape.

Exploratory gate status: accepted bytes since the last exploratory run are
128/200, so no new 30-minute exploratory gate is due yet.

## T17 boolean staging/file-clear peepholes — landed 2026-06-15

Scope:

- Replaced seven `movlw 1; bit-test; movlw 0; movwf scratch` boolean-staging
  idioms with `clrf scratch; bit-test; incf scratch`.
- Sites covered: HID filename/user-mute staging, wake gate-open staging,
  cmd 0x03 mute-on/off refresh staging, SRC4382 mute-status refresh staging,
  and the two bank-4 core-service flag staging blocks.
- Replaced `movlw 0; movwf POSTINC2; movwf POSTDEC2` in
  `fw_update_signature_status_word_helper` with direct `clrf POSTINC2; clrf POSTDEC2`.
- The source contract bounds each changed routine to its real local label range
  so unrelated later uses of the scratch registers do not mask a regression.

Measured result:

- Before T17: rev `0xBD`, `contiguous_free_before_0x4C00=250 bytes`.
- After T17 canonical rebuild: EEPROM rev `0xBD -> 0xBE`,
  `listing_app_end=0x4AF6`, `last_used_pre_preset_b=0x4AF5`,
  `contiguous_free_before_0x4C00=266 bytes`, `free_object_words=133`.
- Net reclaim: **+16 bytes** of margin for T17, **+144 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xBD -> 0xBE)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
f = check_targets(['main-v34'])
print('findings', len(f))
raise SystemExit(1 if f else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 139 passed, 1 xfailed in 264.32s
```

The xfail is the known `chain_copy` interrupt-safety proof.  Source contracts
pin the compact boolean-staging and FSR clear shapes.

Exploratory gate status: accepted bytes since the last exploratory run are
144/200, so no new 30-minute exploratory gate is due yet.

## T18 cmd19 status bit-fanout rotate carry — landed 2026-06-15

Scope:

- `stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot` materializes the HID/status payload byte
  fanout from `active_flags.bit4` and bits 0..5 of `stock_0A4`.
- T18 keeps `stock_163` as a direct `clrf`/conditional-`incf` boolean store.
- The six `stock_0A4` bit outputs (`stock_164`, `stock_165`, `stock_166`,
  `stock_168`, `stock_169`, `stock_16A`) now copy `stock_0A4` once into
  access scratch `stock_006`, then use `rrcf` to move each source bit into C
  and `clrf`/`rlcf` to write the destination byte as 0 or 1.
- BSR remains bank 1 across the fanout; `status_addr_high_or_i2c_payload_scratch_byte` is access-bank scratch
  and the following `chain_copy` call does not consume incoming STATUS.

Measured result:

- Before T18: rev `0xBE`, `contiguous_free_before_0x4C00=266 bytes`.
- After T18 canonical rebuild: EEPROM rev `0xBE -> 0xBF`,
  `listing_app_end=0x4AD4`, `last_used_pre_preset_b=0x4AD3`,
  `contiguous_free_before_0x4C00=300 bytes`, `free_object_words=150`.
- Net reclaim: **+34 bytes** of margin for T18, **+178 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xBE -> 0xBF)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_compatibility.py
# 143 passed, 1 xfailed in 266.80s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The source
contract pins the rotate-through-carry fanout and rejects the older repeated
`movlw`/`movlb`/`btfsc` materialization shape.

Exploratory gate status: accepted bytes since the last exploratory run are
178/200, so no new 30-minute exploratory gate is due yet.

## T19 EEPROM-write GIE snapshot peephole — landed 2026-06-15

Scope:

- `eeprom_write_blocking` snapshots `INTCON.GIE` into `stock_006.bit0` before
  clearing GIE for the PIC18 EEPROM unlock/write window.
- T19 replaced the literal `movlw 0; btfsc INTCON.GIE; movlw 1; movwf
  stock_006` shape with `clrf stock_006; btfsc INTCON.GIE; incf stock_006`.
- The following unlock helper (`nvm_unlock_and_set_wr`) writes only EECON2
  and EECON1.WR before returning; it does not consume incoming STATUS.

Measured result:

- Before T19: rev `0xBF`, `contiguous_free_before_0x4C00=300 bytes`.
- After T19 canonical rebuild: EEPROM rev `0xBF -> 0xC0`,
  `listing_app_end=0x4AD2`, `last_used_pre_preset_b=0x4AD1`,
  `contiguous_free_before_0x4C00=302 bytes`, `free_object_words=151`.
- Net reclaim: **+2 bytes** of margin for T19, **+180 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xBF -> 0xC0)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_ep0_eeprom_shadow_dump.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v34_field_bugs_20260610.py
# 140 passed, 1 xfailed, 3 warnings in 94.55s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
180/200, so no new 30-minute exploratory gate is due yet.

## T20 cmd03 mute-off shared refresh tail — landed 2026-06-15

Scope:

- `cmd03_mute_on_handler` already owned the common user-mute vs forced-mute
  xor/Z-test sequence at `uart_link_parser__mute_dirty_if_user_shadow_differs`.
- `cmd03_mute_off_apply` open-coded the same true-branch tail as
  `xorwf stock_005; bnz dirty; bra clean`.
- T20 keeps the false branch shared through `uart_link_parser__stage_zero_mute_compare_value`
  and changes the true branch to `movlw 1; bra uart_link_parser__mute_dirty_if_user_shadow_differs`.

Measured result:

- Before T20: rev `0xC0`, `contiguous_free_before_0x4C00=302 bytes`.
- After T20 canonical rebuild: EEPROM rev `0xC0 -> 0xC1`,
  `listing_app_end=0x4ACE`, `last_used_pre_preset_b=0x4ACD`,
  `contiguous_free_before_0x4C00=306 bytes`, `free_object_words=153`.
- Net reclaim: **+4 bytes** of margin for T20, **+184 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC0 -> 0xC1)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_v173_compatibility.py
# 159 passed, 1 xfailed in 256.10s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The boolean
staging source contract pins the shared-tail branch shape.

Exploratory gate status: accepted bytes since the last exploratory run are
184/200, so no new 30-minute exploratory gate is due yet.

## Rejected T21 preset-table setup helper — reverted 2026-06-15

Attempted scope:

- Factored the duplicated seven-word preset-table cursor initialization in
  `preset_replay_selected_table_blocking` and `preset_job_holding` into
  `preset_job_stage_active_table_bsr2`.
- The helper was in `rcall` reach from both users and built cleanly at rev
  `0xC2`, with margin temporarily increasing to 314 bytes.

Rejection:

- Focused preset/reconnect testing deterministically failed
  `test_coalesced_target_during_apply_restarts_from_row0_correct_source[False-True]`.
- The DSP coefficient images converged, but the LCD row remained
  `Volume:-17.0dB !` instead of ending in `B`, so this is a user-visible
  lifecycle/status regression.
- Reverted the helper and rebuilt canonically (`0xC2 -> 0xC3`); the repro
  passes again, RAM-bank safety is clean, and margin returned to the accepted
  T20 value of 306 bytes.
- Accepted-byte counter remains **184/200**; no exploratory gate is due from
  the rejected attempt.

## T22 flash page/USB endpoint helper pair — landed 2026-06-15

Scope:

- Added `fw_update_stage_flash_page_window`, which wraps the existing
  `fw_update_stage_flash_addr_from_cursor` helper plus the repeated
  `stock_007:008=0x00C0`, `stock_009=0`, `stock_00A=0x03` page-count setup.
  `fw_update_commit_hid_payload_page` now uses it before the initial `flash_read` and
  before the final `flash_write`.
- Added `usb_clear_uep1_7`, shared by USB reset/reinit paths
  `usb_bus_reset_reinitialize` and `usb_apply_set_configuration`.
- The alias block was refreshed with `scripts/check_ram_access_safety.py
  --target main-v34 --fix-aliases`; RAM-bank safety then passed cleanly.

Measured result:

- Before T22: rev `0xC3`, `contiguous_free_before_0x4C00=306 bytes`.
- After T22 canonical rebuild: EEPROM rev `0xC3 -> 0xC4`,
  `listing_app_end=0x4ABC`, `last_used_pre_preset_b=0x4ABB`,
  `contiguous_free_before_0x4C00=324 bytes`, `free_object_words=162`.
- Net reclaim: **+18 bytes** of margin for T22, **+202 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC3 -> 0xC4)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_dlcp_ep0_flash_probe.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_compatibility.py
# 135 passed, 1 xfailed, 3 warnings in 168.90s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m --status-interval 60 \
  --out-dir artifacts/reanalysis/v34_size_t22_exploratory_20260615_c4
# run 20260615_214002_ae420a5df3baffc6:
# 83 sessions, 9193 events, 6763 observations,
# incidents {'LOW': 1}, duplicate signatures 94

PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t22_exploratory_20260615_c4 \
  --out artifacts/reanalysis/v34_size_t22_exploratory_20260615_c4/cards \
  --top 8 --sample 2 --seed 196
# selected 10 cards; highest-ranked card was session 14
```

LLM judge evidence:

- Direct Codex judge over
  `cards/20260615_214002_ae420a5df3baffc6__s0014.md` wrote
  `artifacts/reanalysis/v34_size_t22_exploratory_20260615_c4/oracle_judge_direct/judge_s0014.json`.
  The verdict was `needs_human` for an asymmetric PB2 gate during a `Zzz`
  standby window after prior synthetic PB2 AN0/SRC fault stimuli.
- Normalized replay/minimization artifacts under
  `artifacts/reanalysis/v34_size_t22_exploratory_20260615_c4/replay_14/oracle_min_norm_*`
  proved the standby asymmetry disappears when all synthetic fault stimuli are
  removed: at event 30 both gates are `[0,0]`, both `S` counters increment, and
  the later mute applies to both MAINs.
- Skipping only post-standby fault events 34..42 did not remove the asymmetry,
  so the plausible cause is the earlier synthetic PB2 rail/fault context, not
  the T22 flash/USB helper changes.
- Nominal V1.73/V3.4 IR standby/wake coverage stayed green:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v34_diag_page_dispatches_ir_standby_and_wake \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_diag_page_ir_standby_wake_closes_and_reopens_both_main_gates
# 4 passed in 22.31s
```

Gate conclusion: no T22 regression accepted from the oracle item; carry it as
synthetic-fault-only evidence unless a future minimized, realistic replay
survives.  The accepted-byte exploratory counter is reset to **0/200** after
this gate.

## T23 fw-update status-buffer TX helper — landed 2026-06-15

Scope:

- Added local `fw_update_tx_status_text_transmit` in `fw_update_relay`.
- Replaced the two identical `stock_019:stock_018 = 0x019A` staging blocks
  plus `uart_tx_block_from_buffer` calls with `rcall`s to the helper.
- The helper ends with `goto uart_tx_block_from_buffer`, so the UART helper
  returns directly to each original caller's post-`rcall` continuation.

Measured result:

- Before T23: rev `0xC4`, `contiguous_free_before_0x4C00=324 bytes`.
- After T23 canonical rebuild: EEPROM rev `0xC4 -> 0xC5`,
  `listing_app_end=0x4AB4`, `last_used_pre_preset_b=0x4AB3`,
  `contiguous_free_before_0x4C00=332 bytes`, `free_object_words=166`.
- Net reclaim: **+8 bytes** of margin for T23, **+8 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC4 -> 0xC5)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 141 passed, 1 xfailed, 3 warnings in 59.18s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
8/200, so no new 30-minute exploratory gate is due yet.

## T24 CONFIG flash-write tail helper — landed 2026-06-15

Scope:

- Added local `config_flash_write_tablat_byte` inside
  `flash_write_with_gie_off`.
- Kept the two CONFIG TBLPTR setup sequences inline, but shared the duplicated
  `TABLAT` stage, `EECON1=0xC4`, `nvm_unlock_and_set_wr`, and WR-bit wait.
- GIE behavior remains the stock/known BUG-M7 contract: the routine still
  clears GIE at entry and relies on the caller-side restore after return.

Measured result:

- Before T24: rev `0xC5`, `contiguous_free_before_0x4C00=332 bytes`.
- After T24 canonical rebuild: EEPROM rev `0xC5 -> 0xC6`,
  `listing_app_end=0x4AAC`, `last_used_pre_preset_b=0x4AAB`,
  `contiguous_free_before_0x4C00=340 bytes`, `free_object_words=170`.
- Net reclaim: **+8 bytes** of margin for T24, **+16 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC5 -> 0xC6)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py
# 145 passed, 1 xfailed, 3 warnings in 69.35s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
16/200, so no new 30-minute exploratory gate is due yet.

## T25 cmd03 mute-refresh staging helper — landed 2026-06-15

Scope:

- Added local `cmd03_stage_mute_refresh_w`.
- Shared the duplicated cmd `0x03` mute-on/mute-off staging that computes
  `stock_005 = active_flags.bit4` and returns `W = active_flags.bit5`.
- Both call sites still branch into the existing XOR/dirty-bit refresh tail,
  preserving the mute-ownership contract and preset-job force-mute guards.

Measured result:

- Before T25: rev `0xC6`, `contiguous_free_before_0x4C00=340 bytes`.
- After T25 canonical rebuild: EEPROM rev `0xC6 -> 0xC7`,
  `listing_app_end=0x4AA4`, `last_used_pre_preset_b=0x4AA3`,
  `contiguous_free_before_0x4C00=348 bytes`, `free_object_words=174`.
- Net reclaim: **+8 bytes** of margin for T25, **+24 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC6 -> 0xC7)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_field_bugs_20260610.py
# 118 passed in 183.13s
```

Exploratory gate status: accepted bytes since the last exploratory run are
24/200, so no new 30-minute exploratory gate is due yet.

## T26 Timer3 0xF830 preload helper — landed 2026-06-15

Scope:

- Added midpoint helper `timer3_reload_high_speed_tick_preload` near `usb_apply_set_configuration`.
- Replaced the three exact Timer3 `0xF830` preload sites:
  the Timer3 ISR holding tick, the low-speed branch of
  `timer3_blocking_delay`, and `timer3_arm_interrupt_countdown`.
- Kept the oscillator-specific `0xFC18` preload inline.  The shared helper
  leaves `W=0x30`; the blocking-delay low-speed path branches around its
  existing common `TMR3L` store so it does not perform a duplicate low-byte
  write.
- Updated `test_v34_boolean_staging_uses_file_register_increment_shape` to
  validate the T25 `cmd03_stage_mute_refresh_w` helper as the owner of the
  boolean staging shape, then validate both cmd03 mute handlers call it.

Measured result:

- Before T26: rev `0xC7`, `contiguous_free_before_0x4C00=348 bytes`.
- After T26 canonical rebuild: EEPROM rev `0xC7 -> 0xC8`,
  `listing_app_end=0x4AA0`, `last_used_pre_preset_b=0x4A9F`,
  `contiguous_free_before_0x4C00=352 bytes`, `free_object_words=176`.
- Net reclaim: **+4 bytes** of margin for T26, **+28 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC7 -> 0xC8)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v172_v33_diag_identity.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py
# 154 passed, 3 xfailed in 567.68s
```

Exploratory gate status: accepted bytes since the last exploratory run are
28/200, so no new 30-minute exploratory gate is due yet.

## T27 filename seqlock/base helpers — landed 2026-06-15

Scope:

- Added local `preset_filename_begin_xact_w` for the shared filename
  seqlock-odd bump and active-preset EEPROM base selection.
- Added local `preset_filename_finish_xact_bsr0` for the shared seqlock-even
  bump and BSR restore to bank 0.
- Replaced the duplicated begin sequences in `preset_persist_filename` and
  `preset_load_filename`.
- Replaced the duplicated finish sequences; `preset_load_filename` branches
  into the finish helper so the helper's `return` still returns to the original
  caller.

Measured result:

- Before T27: rev `0xC8`, `contiguous_free_before_0x4C00=352 bytes`.
- After T27 canonical rebuild: EEPROM rev `0xC8 -> 0xC9`,
  `listing_app_end=0x4A98`, `last_used_pre_preset_b=0x4A97`,
  `contiguous_free_before_0x4C00=360 bytes`, `free_object_words=180`.
- Net reclaim: **+8 bytes** of margin for T27, **+36 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC8 -> 0xC9)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v32_usb_filename_xact_gate.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename \
  tests/sim/test_v34_v173_compatibility.py::test_mixed_new_old_filename_pairs_preserve_query_cache_and_reentry \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 250 passed, 1 xfailed in 452.64s
```

Exploratory gate status: accepted bytes since the last exploratory run are
36/200, so no new 30-minute exploratory gate is due yet.

## T28 USB 0x5A/0x40 staging helper — landed 2026-06-15

Scope:

- Added `usb_ep1_in_send_hid_reply_buffer` immediately before
  `usb_ep1_in_copy_scratch_buffer_to_bdt`.
- Replaced two USB call sites that staged `ram_clear_prepare_page1_address_high`,
  `stock_003=0x5A`, `stock_005=0x40`, then called
  `usb_ep1_in_copy_scratch_buffer_to_bdt`.
- The helper tail-branches into `usb_ep1_in_copy_scratch_buffer_to_bdt`; its `return`
  continues at the original caller's post-`rcall` instruction.

Measured result:

- Before T28: rev `0xC9`, `contiguous_free_before_0x4C00=360 bytes`.
- After T28 canonical rebuild: EEPROM rev `0xC9 -> 0xCA`,
  `listing_app_end=0x4A8E`, `last_used_pre_preset_b=0x4A8D`,
  `contiguous_free_before_0x4C00=370 bytes`, `free_object_words=185`.
- Net reclaim: **+10 bytes** of margin for T28, **+46 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xC9 -> 0xCA)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v32_usb_filename_xact_gate.py \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_boolean_staging_uses_file_register_increment_shape
# 259 passed, 3 warnings in 429.02s
```

The warnings are PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
46/200, so no new 30-minute exploratory gate is due yet.

## T29 signed-high compare prelude helper — landed 2026-06-16

Scope:

- Added `signed_hi_bias80_compare_prelude` between the two call sites.
- Replaced the duplicated signed-high-byte compare prelude in
  `truncate_float32_to_integral_float_in_place` and `format_int16_decimal_ascii_to_w_pointer`.
- The helper takes W as the high byte, returns with W=`0x00`, and preserves
  STATUS from `subwf PRODL,W` for the caller's existing `btfsc STATUS,Z`
  low-byte compare.

Measured result:

- Before T29: rev `0xCA`, `contiguous_free_before_0x4C00=370 bytes`.
- After T29 canonical rebuild: EEPROM rev `0xCA -> 0xCB`,
  `listing_app_end=0x4A8A`, `last_used_pre_preset_b=0x4A89`,
  `contiguous_free_before_0x4C00=374 bytes`, `free_object_words=187`.
- Net reclaim: **+4 bytes** of margin for T29, **+50 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xCA -> 0xCB)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 98 passed, 1 xfailed in 60.22s
```

Exploratory gate status: accepted bytes since the last exploratory run are
50/200, so no new 30-minute exploratory gate is due yet.

## T30 FSR1 table-pointer read helper — landed 2026-06-16

Scope:

- Added `tblrd_load_fsr1_pair_from_table_page_w` immediately before
  `i2c_apply_channel_route_sync_burst`.
- Replaced the duplicated `TBLPTRH/TBLPTRU` setup plus two `tblrd*+` reads
  that load an `(FSR1L, FSR1H)` pair from the dispatch/source tables.
- The helper takes W as the table high byte, preserves W and BSR, and leaves
  STATUS as the original inline `clrf TBLPTRU` sequence did.

Measured result:

- Before T30: rev `0xCB`, `contiguous_free_before_0x4C00=374 bytes`.
- After T30 canonical rebuild: EEPROM rev `0xCB -> 0xCC`,
  `listing_app_end=0x4A80`, `last_used_pre_preset_b=0x4A7F`,
  `contiguous_free_before_0x4C00=384 bytes`, `free_object_words=192`.
- Net reclaim: **+10 bytes** of margin for T30, **+60 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xCB -> 0xCC)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_main_i2c_service_2100_tables.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py
# 128 passed, 3 xfailed in 412.26s
```

Exploratory gate status: accepted bytes since the last exploratory run are
60/200, so no new 30-minute exploratory gate is due yet.

## T31 flash-write right-shift helper reuse — landed 2026-06-16

Scope:

- Replaced the inline 32-bit right-shift block in `flash_write` with the
  existing `shift_003_006_right_clear_c` helper.
- No new helper code was added; the existing helper already performs the same
  `bcf STATUS,C` plus four `rrcf` operations and returns with W unchanged.

Measured result:

- Before T31: rev `0xCC`, `contiguous_free_before_0x4C00=384 bytes`.
- After T31 canonical rebuild: EEPROM rev `0xCC -> 0xCD`,
  `listing_app_end=0x4A78`, `last_used_pre_preset_b=0x4A77`,
  `contiguous_free_before_0x4C00=392 bytes`, `free_object_words=196`.
- Net reclaim: **+8 bytes** of margin for T31, **+68 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xCC -> 0xCD)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v32_no_pop_flash_entry.py \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_boolean_staging_uses_file_register_increment_shape
# 68 passed, 3 warnings in 11.72s
```

The warnings are PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
68/200, so no new 30-minute exploratory gate is due yet.

## T32 left-shift helper for flash/math loops — landed 2026-06-16

Scope:

- Added `shift_scratch32_left_clear_carry` after `float32_pack_mantissa_exponent_sign`.
- Replaced the inline 32-bit left-shift block in `flash_write` and
  `float32_pack_mantissa_exponent_sign`.
- The helper preserves W and performs the same carry-clear plus four `rlcf`
  operations as both inline sites.

Measured result:

- Before T32: rev `0xCD`, `contiguous_free_before_0x4C00=392 bytes`.
- After T32 canonical rebuild: EEPROM rev `0xCD -> 0xCE`,
  `listing_app_end=0x4A74`, `last_used_pre_preset_b=0x4A73`,
  `contiguous_free_before_0x4C00=396 bytes`, `free_object_words=198`.
- Net reclaim: **+4 bytes** of margin for T32, **+72 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xCD -> 0xCE)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_main_gpsim_command_edges.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 154 passed, 1 xfailed, 3 warnings in 74.43s
```

The warnings are PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
72/200, so no new 30-minute exploratory gate is due yet.

## T33 FSR1 page-1 copy helper — landed 2026-06-16

Scope:

- Added `copy_indf2_to_page1_w` near the existing bank-1 helper block.
- Replaced two page-1 FSR1 setup plus `movff INDF2,INDF1` sequences in
  `fw_update_relay` and `copy_indexed_fsr2_byte_to_hid_ep1_in`.
- The helper preserves the carry from the caller's low-byte address add through
  to `addwfc FSR1H,F`, matching the inline page-crossing behavior.

Measured result:

- Before T33: rev `0xCE`, `contiguous_free_before_0x4C00=396 bytes`.
- After T33 canonical rebuild: EEPROM rev `0xCE -> 0xCF`,
  `listing_app_end=0x4A6E`, `last_used_pre_preset_b=0x4A6D`,
  `contiguous_free_before_0x4C00=402 bytes`, `free_object_words=201`.
- Net reclaim: **+6 bytes** of margin for T33, **+78 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xCE -> 0xCF)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 91 passed, 1 xfailed, 3 warnings in 15.22s
```

The warnings are PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
78/200, so no new 30-minute exploratory gate is due yet.

## T34 filename reply id-frame helper — landed 2026-06-16

Scope:

- Added `filename_emit_id_frame_cmd_w` for the two filename reply terminal
  states that emit a BF frame carrying the current filename job id.
- `filename_reply_send_start` now passes `fn_job_start_cmd_b2` in W to the
  helper before advancing to state 2.
- `filename_reply_send_end` now passes literal `0x4E` in W to the helper before
  clearing the filename job state.
- The helper keeps the original `i2c_flag_or_flash_math_uart_cmd_scratch_byte`/`flash_upper_or_uart_count_scratch_byte` staging,
  calls `filename_emit_frame`, and restores `BSR=2` before returning to the
  state update, matching the original inline tails.

Measured result:

- Before T34: rev `0xCF`, `contiguous_free_before_0x4C00=402 bytes`.
- After T34 canonical rebuild: EEPROM rev `0xCF -> 0xD0`,
  `listing_app_end=0x4A6A`, `last_used_pre_preset_b=0x4A69`,
  `contiguous_free_before_0x4C00=406 bytes`, `free_object_words=203`.
- Net reclaim: **+4 bytes** of margin for T34, **+82 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xCF -> 0xD0)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v32_usb_filename_xact_gate.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename \
  tests/sim/test_v34_v173_compatibility.py::test_mixed_new_old_filename_pairs_preserve_query_cache_and_reentry \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 244 passed, 1 xfailed in 441.50s (0:07:21)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
82/200, so no new 30-minute exploratory gate is due yet.

## T35 FSR2 stock_003/004 offset helper — landed 2026-06-16

Scope:

- Added `fsr2_from_scratch_base_plus_w`, a shared helper for building
  `FSR2 = stock_003:stock_004 + W`.
- `usb_ep1_in_copy_scratch_buffer_to_bdt` now calls the helper with its `count_flash_page_or_i2c_payload_scratch_byte` copy
  offset before copying the USB/core payload byte.
- `clear_ram_span_from_staged_addr_count` now calls the helper with its `status_addr_high_or_i2c_payload_scratch_byte` clear-loop
  offset before clearing `INDF2`.
- The helper leaves BSR unchanged and preserves the original final `addwfc`
  STATUS side effects across `return`.

Measured result:

- Before T35: rev `0xD0`, `contiguous_free_before_0x4C00=406 bytes`.
- After T35 canonical rebuild: EEPROM rev `0xD0 -> 0xD1`,
  `listing_app_end=0x4A66`, `last_used_pre_preset_b=0x4A65`,
  `contiguous_free_before_0x4C00=410 bytes`, `free_object_words=205`.
- Net reclaim: **+4 bytes** of margin for T35, **+86 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD0 -> 0xD1)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 87 passed, 1 xfailed, 3 warnings in 6.02s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
86/200, so no new 30-minute exploratory gate is due yet.

## T36 USB saved-FSR2 setup helper — landed 2026-06-16

Scope:

- Added `usb_setup_fsr2_from_selected_bdt_entry_ptr` for the USB endpoint loop's repeated
  saved-FSR2 pointer reconstruction from `usb_selected_bdt_entry_ptr_lo_b0:usb_selected_bdt_entry_ptr_hi_b0`.
- Replaced the two copies in `usb_sie_endpoint_pump__copy_setup_packet_byte`: one before
  reading the saved FSR2 pair and one before incrementing that saved pointer.
- The helper keeps W and STATUS aligned with the original final
  `addwfc FSR2H,F` result; the next instructions either do `movff` or overwrite
  flags with `incf`.

Measured result:

- Before T36: rev `0xD1`, `contiguous_free_before_0x4C00=410 bytes`.
- After T36 canonical rebuild: EEPROM rev `0xD1 -> 0xD2`,
  `listing_app_end=0x4A60`, `last_used_pre_preset_b=0x4A5F`,
  `contiguous_free_before_0x4C00=416 bytes`, `free_object_words=208`.
- Net reclaim: **+6 bytes** of margin for T36, **+92 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD1 -> 0xD2)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 87 passed, 1 xfailed, 3 warnings in 6.03s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
92/200, so no new 30-minute exploratory gate is due yet.

## T37 EEPROM-byte wrapper reuse in boot copy loops — landed 2026-06-16

Scope:

- Reused the existing `eeprom_read_byte_at_w` wrapper for the two remaining
  boot-time EEPROM copy loops in `restore_eeprom_settings_on_boot`.
- The first loop still sets FSR2 to the page-1 destination via
  `setup_fsr2_page1_from_w`, then reloads `eeprom_mask_or_flash_src_high_scratch_byte` into W for the EEPROM read.
- The second loop still sets FSR2 to the page-2 destination via
  `setup_fsr2_page2_from_w`, then reloads `eeprom_mask_or_flash_src_high_scratch_byte` into W for the EEPROM read.
- The wrapper handles `stock_003/stock_004` EEPROM address staging and leaves
  the loaded byte in W for the existing `movwf INDF2`.

Measured result:

- Before T37: rev `0xD2`, `contiguous_free_before_0x4C00=416 bytes`.
- After T37 canonical rebuild: EEPROM rev `0xD2 -> 0xD3`,
  `listing_app_end=0x4A54`, `last_used_pre_preset_b=0x4A53`,
  `contiguous_free_before_0x4C00=428 bytes`, `free_object_words=214`.
- Net reclaim: **+12 bytes** of margin for T37, **+104 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD2 -> 0xD3)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# 80 passed, 1 xfailed in 46.10s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
104/200, so no new 30-minute exploratory gate is due yet.

## T38 runtime EEPROM metadata write helper — landed 2026-06-16

Scope:

- Added `eeprom_write_runtime_version_03_at_w` for the two fixed runtime metadata writes
  that store `0x03` at EEPROM bytes `0x80` and `0x81`.
- The helper stages `count_flash_page_or_i2c_payload_scratch_byte` from W, clears `flash_end_high_or_loop_mask_scratch_byte` before the
  write, stages `flash_src_low_or_rx_length_scratch_byte=0x03`, calls `eeprom_write_byte_if_changed`, and
  clears `flash_end_high_or_loop_mask_scratch_byte` again for the following write.
- The builder-owned `V3.4_RUNTIME_EEPROM_REV_LO` literal for EEPROM byte `0x82`
  remains inline as the low-byte compatibility mirror; the full 16-bit release
  revision is owned by the cmd `0x25` identity literals and updated normally by
  `scripts/build_v34_release.py`.

Measured result:

- Before T38: rev `0xD3`, `contiguous_free_before_0x4C00=428 bytes`.
- After T38 canonical rebuild: EEPROM rev `0xD3 -> 0xD4`,
  `listing_app_end=0x4A4E`, `last_used_pre_preset_b=0x4A4D`,
  `contiguous_free_before_0x4C00=434 bytes`, `free_object_words=217`.
- Net reclaim: **+6 bytes** of margin for T38, **+110 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD3 -> 0xD4)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 98 passed, 1 xfailed, 3 warnings in 19.29s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
110/200, so no new 30-minute exploratory gate is due yet.

## T39 EEPROM read-to-INDF2 loop helper — landed 2026-06-16

Scope:

- Added `eeprom_read_indexed_byte_to_postinc2` for the two boot copy loops that read
  EEPROM byte `eeprom_mask_or_flash_src_high_scratch_byte`, store it through the already-staged FSR2
  destination, and increment `eeprom_mask_or_flash_src_high_scratch_byte`.
- The destination setup remains caller-specific (`setup_fsr2_page1_from_w` for the
  first loop, `setup_fsr2_page2_from_w` for the second loop).
- The helper preserves the final STATUS side effect from `incf eeprom_mask_or_flash_src_high_scratch_byte`,
  matching the original inline loop body.

Measured result:

- Before T39: rev `0xD4`, `contiguous_free_before_0x4C00=434 bytes`.
- After T39 canonical rebuild: EEPROM rev `0xD4 -> 0xD5`,
  `listing_app_end=0x4A4C`, `last_used_pre_preset_b=0x4A4B`,
  `contiguous_free_before_0x4C00=436 bytes`, `free_object_words=218`.
- Net reclaim: **+2 bytes** of margin for T39, **+112 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD4 -> 0xD5)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_v34_v173_refactoring_contracts.py
# 85 passed, 1 xfailed in 39.08s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
112/200, so no new 30-minute exploratory gate is due yet.

## T40 chain-role UART/oscillator setup helper — landed 2026-06-16

Scope:

- Added `uart_baud_chain_role_prefix` for the duplicated RC2-high role setup:
  `LATB.2=1`, `SPBRGH=0`, `SPBRG=0x3F`, and `OSCCON.SCS1=1`.
- Replaced the inline sequence in both `adaptive_baud_select` and
  `hw_standby_shutdown`.
- The helper preserves the original W value (`0x3F`) and STATUS state
  (`Z` from `clrf SPBRGH`) across return; subsequent convergence code is
  unchanged.

Measured result:

- Before T40: rev `0xD5`, `contiguous_free_before_0x4C00=436 bytes`.
- After T40 canonical rebuild: EEPROM rev `0xD5 -> 0xD6`,
  `listing_app_end=0x4A48`, `last_used_pre_preset_b=0x4A47`,
  `contiguous_free_before_0x4C00=440 bytes`, `free_object_words=220`.
- Net reclaim: **+4 bytes** of margin for T40, **+116 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD5 -> 0xD6)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# 87 passed, 3 xfailed in 376.99s (0:06:16)
```

The xfails are the known `chain_copy` interrupt-safety proof and the two
existing Diagnostics front-panel STBY repros.

Exploratory gate status: accepted bytes since the last exploratory run are
116/200, so no new 30-minute exploratory gate is due yet.

## T41 LATA audio-pin clear helper — landed 2026-06-16

Scope:

- Added `clear_lata_audio_pins` for the repeated clears of `LATA.6`,
  `LATA.3`, `LATA.4`, and `LATA.5`.
- Replaced the copies in `adaptive_baud_select` and `hw_standby_shutdown` with
  near `rcall`s.
- Replaced the copy in `flash_entry_mute_and_reset` with a long `call`, keeping
  the preceding `LATB.4` amp-enable clear inline and preserving the no-OSCCON /
  no-USB-shutdown flash-entry contract.
- The helper does not touch W, BSR, or STATUS; it only adds call/return latency
  before the same pin clears.

Measured result:

- Before T41: rev `0xD6`, `contiguous_free_before_0x4C00=440 bytes`.
- After T41 canonical rebuild: EEPROM rev `0xD6 -> 0xD7`,
  `listing_app_end=0x4A42`, `last_used_pre_preset_b=0x4A41`,
  `contiguous_free_before_0x4C00=446 bytes`, `free_object_words=223`.
- Net reclaim: **+6 bytes** of margin for T41, **+122 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD6 -> 0xD7)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 132 passed, 3 xfailed, 3 warnings in 377.46s (0:06:17)
```

The xfails are the known `chain_copy` interrupt-safety proof and the two
existing Diagnostics front-panel STBY repros.  The warnings are PyUSB/libusb0
deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
122/200, so no new 30-minute exploratory gate is due yet.

## T42 FSR2 bank-0 stock_007 helper — landed 2026-06-16

Scope:

- Added `fw_update_signature_load_fsr2_from_status_ptr` for the repeated
  `FSR2L=stock_007`, `FSR2H=0` setup in `fw_update_signature_status_word_helper`.
- Replaced the four inline setup triples that clear/write via `POSTINC2` /
  `POSTDEC2` during the flash/signature helper path.
- The helper ends with the original `clrf FSR2H`, so W remains
  `stock_007` and STATUS.Z remains set exactly as at the old call sites.
  BSR is untouched.
- Updated the refactoring source contract to require four helper calls and to
  pin the helper body, rather than requiring the old inline `clrf FSR2H` before
  the first `POSTINC2` clear.

Measured result:

- Before T42: rev `0xD7`, `contiguous_free_before_0x4C00=446 bytes`.
- After T42 canonical rebuild: EEPROM rev `0xD7 -> 0xD8`,
  `listing_app_end=0x4A3A`, `last_used_pre_preset_b=0x4A39`,
  `contiguous_free_before_0x4C00=454 bytes`, `free_object_words=227`.
- Net reclaim: **+8 bytes** of margin for T42, **+130 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD7 -> 0xD8)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v32_no_pop_flash_entry.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_happy_path.py
# 111 passed, 1 xfailed, 3 warnings in 18.67s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
130/200, so no new 30-minute exploratory gate is due yet.

## T43 BF frame header TX helper — landed 2026-06-16

Scope:

- Added `bf_frame_header_tx` for the common reply prefix:
  `mark_chain_tx_emitted_bsr0`, `0xBF`, `uart_tx_byte_blocking`.
- Added the smaller `bf_byte_tx` tail helper for callers that already need to
  mark before doing other work.
- Replaced the BF header in `report_cmd29_status`,
  `cmd23_health_query_handler`, `cmd25_identity_query_handler`, and
  `diag_low_nibble_reply_burst` with `rcall bf_frame_header_tx`.
- Updated `send_dsp_fault_status` to keep the original mark-then-snapshot order
  for `dsp_fault_flags`, then call `bf_byte_tx` before emitting BF/08/data.
- Updated the chain-TX source contract to pin `bf_frame_header_tx` as a valid
  participant and verify that it still calls `mark_chain_tx_emitted_bsr0` before
  the BF byte is transmitted.

Measured result:

- Before T43: rev `0xD8`, `contiguous_free_before_0x4C00=454 bytes`.
- After T43 canonical rebuild: EEPROM rev `0xD8 -> 0xD9`,
  `listing_app_end=0x4A2E`, `last_used_pre_preset_b=0x4A2D`,
  `contiguous_free_before_0x4C00=466 bytes`, `free_object_words=233`.
- Net reclaim: **+12 bytes** of margin for T43, **+142 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD8 -> 0xD9)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v172_v33_diag_identity.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v32_layer5_diag_counters.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v31_review_findings.py \
  tests/sim/test_v171_v32_chain_bf08_integration.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_preset_filename_lcd_spec.py
# 393 passed, 1 xfailed in 1203.12s (0:20:03)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
142/200, so no new 30-minute exploratory gate is due yet.

## T44 BF byte helper reuse — landed 2026-06-16

Scope:

- Reused `bf_byte_tx` for the remaining direct `0xBF` byte emitters:
  `send_status_burst_preamble`, `fw_update_emit_bf18_status`, and
  `filename_emit_frame`.
- `send_status_burst_preamble` uses a long `call bf_byte_tx` because it is
  outside `rcall` reach; this still saves one object word versus
  `movlw 0xBF` plus long `call uart_tx_byte_blocking`.
- `fw_update_emit_bf18_status` and `filename_emit_frame` use near `rcall`s.
- No caller gained or lost chain-TX marking: status burst and factory reset keep
  their existing unmarked behavior, while `filename_emit_frame` still sets
  `chain_tx_emitted_b2.0` before calling the byte helper.

Measured result:

- Before T44: rev `0xD9`, `contiguous_free_before_0x4C00=466 bytes`.
- After T44 canonical rebuild: EEPROM rev `0xD9 -> 0xDA`,
  `listing_app_end=0x4A28`, `last_used_pre_preset_b=0x4A27`,
  `contiguous_free_before_0x4C00=472 bytes`, `free_object_words=236`.
- Net reclaim: **+6 bytes** of margin for T44, **+148 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xD9 -> 0xDA)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_v32_usb_filename_xact_gate.py \
  tests/sim/test_main_gpsim_usb_engine.py
# 276 passed, 1 xfailed in 455.37s (0:07:35)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
148/200, so no new 30-minute exploratory gate is due yet.

## T45 firmware-update status clear helper — landed 2026-06-16

Scope:

- Added `fw_update_clear_relay_status_accumulators` for the two firmware-update status
  cleanup sites that clear the same eight bank-0 cells:
  `stock_07C/07D/080/081/084/085/086/087`.
- Replaced both inline eight-clear blocks in `fw_update_start_relay_handshake` and
  `hid_command_dispatch__reject_fw_update_signature` with near `rcall`s.
- Both callers already assert `movlb 0x0`; the helper uses only BANKED bank-0
  clears, does not touch W, leaves BSR at 0, and leaves STATUS.Z set from the
  final `clrf`, matching the old no-branch-through block behavior.
- The initial build attempt correctly tripped the generated RAM-alias freshness
  gate; running `scripts/check_ram_access_safety.py --fix-aliases` refreshed the
  alias block before the accepted build.

Measured result:

- Before T45: rev `0xDA`, `contiguous_free_before_0x4C00=472 bytes`.
- After T45 canonical rebuild: EEPROM rev `0xDA -> 0xDB`,
  `listing_app_end=0x4A1E`, `last_used_pre_preset_b=0x4A1D`,
  `contiguous_free_before_0x4C00=482 bytes`, `free_object_words=241`.
- Net reclaim: **+10 bytes** of margin for T45, **+158 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --fix-aliases
# main-v34: alias block updated

PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xDA -> 0xDB)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v32_no_pop_flash_entry.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py
# 131 passed, 1 xfailed, 3 warnings in 39.89s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
158/200, so no new 30-minute exploratory gate is due yet.

## T46 parser forwarded-byte TX helper — landed 2026-06-16

Scope:

- Added `uart_link_forward_parser_byte_and_mark_tx` for the two parser forwarding sites that
  mark chain TX, reload the current RX byte from `stock_00A`, and send it with
  `uart_tx_byte_blocking`.
- Replaced the route-byte and data-byte forward paths in
  `parser_route_phase_handler` / `uart_link_parser__payload_forward_gate` with near
  `rcall`s.
- The helper keeps the existing order: `mark_chain_tx_emitted_bsr0` first, then
  `movf eeprom_mask_or_flash_src_high_scratch_byte,W`, then a tail `goto uart_tx_byte_blocking`, so the UART
  routine returns to the original parser continuation.
- Updated the parser-forwarding source contract to pin the helper sequence.

Measured result:

- Before T46: rev `0xDB`, `contiguous_free_before_0x4C00=482 bytes`.
- After T46 canonical rebuild: EEPROM rev `0xDB -> 0xDC`,
  `listing_app_end=0x4A18`, `last_used_pre_preset_b=0x4A17`,
  `contiguous_free_before_0x4C00=488 bytes`, `free_object_words=244`.
- Net reclaim: **+6 bytes** of margin for T46, **+164 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xDB -> 0xDC)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_v32_layer5_diag_counters.py
# 172 passed, 1 xfailed in 721.94s (0:12:01)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
164/200, so no new 30-minute exploratory gate is due yet.

## T47 HID cmd04 staging helper — landed 2026-06-16

Scope:

- Added `hid_stage_opcode04_status_one` for the two HID cmd04 setup paths that
  stage `stock_0C1=0x04` and `stock_0C2=0x01`.
- Replaced the clean `hid_command_dispatch__opcode04_ack_action_one` literal stores and the
  fault-latching `hid_command_dispatch__opcode04_stage_fault_action` literal stores with near
  `rcall`s.
- Preserved side-effect order: the `0x0B8` setup-profile copy remains before
  the shared staging call, while `dsp_fault_flags.bit0` and `stock_094.bit4`
  are still latched after the `0x0C1/0x0C2` writes.  Both call sites arrive
  with `BSR=0`.
- Added a source contract pinning the helper body and the two call-site orders.

Measured result:

- Before T47: rev `0xDC`, `contiguous_free_before_0x4C00=488 bytes`.
- After T47 canonical rebuilds: EEPROM rev `0xDC -> 0xDE`
  (`0xDC -> 0xDD` for the object change, then `0xDD -> 0xDE` after
  whitespace-only source style normalization),
  `listing_app_end=0x4A16`, `last_used_pre_preset_b=0x4A15`,
  `contiguous_free_before_0x4C00=490 bytes`, `free_object_words=245`.
- Net reclaim: **+2 bytes** of margin for T47, **+166 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --fix-aliases
# control-v172: alias block already current
# control-v173: alias block already current
# main-v33: alias block updated
# main-v34: alias block updated
# ... RAM_ALIAS_BLOCK_STALE ... (expected fixer exit before rebuild)

PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xDC -> 0xDD)

PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xDD -> 0xDE)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py
# 107 passed, 1 xfailed in 119.29s (0:01:59)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
166/200, so no new 30-minute exploratory gate is due yet.

## T48 shared I2C START-after-idle helper — landed 2026-06-16

Scope:

- Added `i2c_start_after_idle_bounded` for the three I2C paths that perform
  `i2c_wait_bus_idle`, assert `SSPCON2.SEN`, then wait through
  `wait_sen_bounded`.
- Replaced the START preambles in `i2c_secondary_dev_random_read`,
  `i2c_tas3108_reg1f_write`, and `i2c_tas3108_coeff_write` with near
  `rcall`s.
- The helper tail-branches into `wait_sen_bounded`, so the bounded wait returns
  directly to the original caller and preserves the carry timeout contract for
  the immediate `bc` branch at each call site.
- Added a source contract pinning the helper sequence and the caller
  `rcall`-then-`bc` order.

Measured result:

- Before T48: rev `0xDE`, `contiguous_free_before_0x4C00=490 bytes`.
- After T48 canonical rebuild: EEPROM rev `0xDE -> 0xDF`,
  `listing_app_end=0x4A10`, `last_used_pre_preset_b=0x4A0F`,
  `contiguous_free_before_0x4C00=496 bytes`, `free_object_words=248`.
- Net reclaim: **+6 bytes** of margin for T48, **+172 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xDE -> 0xDF)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_review_findings.py
# 126 passed, 1 xfailed in 100.23s (0:01:40)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_review_findings.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_user_volume_and_preset_survive_por_power_cycle
# 127 passed, 1 xfailed in 122.72s (0:02:02)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Rejected follow-up:

- T49 attempted a shared `mssp_hard_reset_master_smp` tail helper for
  `adc_boot_gate__start_dsp_cold_init`, `dsp_ping_nack_reset`, and
  `i2c_timeout_recover_common` (estimated/measured +10 bytes, trial rev
  `0xE0`).  It was rejected and reverted because
  `test_v34_v173_compatibility.py::test_v173_v34_user_volume_and_preset_survive_por_power_cycle`
  failed deterministically: after POR the LCD row changed from the expected
  `Volume:-20.0dB !` to `Volume:-20.0dB B`.  Removing the helper and rebuilding
  to rev `0xE1` restored the POR test.  Hypothesis: the extra helper call/branch
  in the wake MSSP reset path perturbs the filename/issue-state timing enough to
  change the visible suffix; the 10-byte win is not accepted.

Exploratory gate status: accepted bytes since the last exploratory run are
172/200, so no new 30-minute exploratory gate is due yet.

## T50 firmware-update address compare helper — landed 2026-06-16

Scope:

- Added `fw_update_compare_relay_addr_limit_w`, a local firmware-update relay helper that
  takes the low threshold byte in W, asserts `BSR=0`, compares
  `stock_084/085` against `0x77xx`, and returns with the original carry
  compare result.
- Replaced the four inline `0x77C0` / `0x77BF` threshold compares in
  `fw_update_relay` with near `rcall`s.
- Added a source contract pinning the bank-0 compare helper and all four call
  sites.

Measured result:

- Before T50: rev `0xE1`, `contiguous_free_before_0x4C00=496 bytes`.
- After T50 canonical rebuild: EEPROM rev `0xE1 -> 0xE2`,
  `listing_app_end=0x4A06`, `last_used_pre_preset_b=0x4A05`,
  `contiguous_free_before_0x4C00=506 bytes`, `free_object_words=253`.
- Net reclaim: **+10 bytes** of margin for T50, **+182 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE1 -> 0xE2)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 93 passed, 1 xfailed, 3 warnings in 15.96s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Rejected follow-up:

- T51 attempted six call-return tail conversions in command dispatch, USB,
  preset apply, flash, and helper paths (trial rev `0xE3`).  It was rejected
  and reverted because every converted site still needed the adjacent `return`
  for a skip/fail path, so `call -> goto` or `rcall -> bra` did not move
  `listing_app_end` or `contiguous_free_before_0x4C00` at all.  Rebuilding the
  reverted T50 object state produced rev `0xE4`; margin stayed 506 bytes and
  RAM safety remained clean.

Exploratory gate status: accepted bytes since the last exploratory run are
182/200, so no new 30-minute exploratory gate is due yet.

## T51 reachable flash-read helper call-to-rcall — landed 2026-06-16

Scope:

- Converted the data-block `flash_read_to_scratch_buffer` call inside
  `preset_table_apply_entry_core` from far `call` to near `rcall`.
- Left the earlier header read as far `call` because the listing reach scan
  showed only the later callsite was in relative-call range.
- Updated the preset-apply source contract to pin the one-call/one-rcall split.

Measured result:

- Before T51: rev `0xE4`, `contiguous_free_before_0x4C00=506 bytes`.
- After T51 canonical rebuild: EEPROM rev `0xE4 -> 0xE5`,
  `listing_app_end=0x4A04`, `last_used_pre_preset_b=0x4A03`,
  `contiguous_free_before_0x4C00=508 bytes`, `free_object_words=254`.
- Net reclaim: **+2 bytes** of margin for T51, **+184 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE4 -> 0xE5)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v31_happy_path.py
# 69 passed, 1 xfailed in 280.05s (0:04:40)
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
184/200, so no new 30-minute exploratory gate is due yet.

## T52 firmware-update 16-bit accumulator helper — landed 2026-06-16

Scope:

- Added `fw_update_add_byte_to_relay_checksum`, a local helper that adds W into the
  firmware-update `stock_080/081` accumulator with the same carry propagation.
- Replaced the two adjacent checksum/status additions and the later single
  byte-add path in `fw_update_relay`.
- Extended the firmware-update source contract to pin the helper body and its
  three call sites.

Measured result:

- Before T52: rev `0xE5`, `contiguous_free_before_0x4C00=508 bytes`.
- After T52 canonical rebuild: EEPROM rev `0xE5 -> 0xE6`,
  `listing_app_end=0x4A00`, `last_used_pre_preset_b=0x49FF`,
  `contiguous_free_before_0x4C00=512 bytes`, `free_object_words=256`.
- Net reclaim: **+4 bytes** of margin for T52, **+188 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE5 -> 0xE6)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 93 passed, 1 xfailed, 3 warnings in 15.32s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
188/200, so no new 30-minute exploratory gate is due yet.

## T53 firmware-update staging helper — landed 2026-06-16

Scope:

- Added `fw_update_stage_uart_rx_window`, which stores the caller's W into
  `stock_005`, sets `BSR=1`, stages `stock_008=0x01`, and returns with W=1.
- Replaced the two matching firmware-update setup sequences in
  `fw_update_start_relay_handshake` and `fw_update_relay__poll_status_response`.
- Added a source contract pinning the helper and both call sites.

Measured result:

- Before T53: rev `0xE6`, `contiguous_free_before_0x4C00=512 bytes`.
- After T53 canonical rebuild: EEPROM rev `0xE6 -> 0xE7`,
  `listing_app_end=0x49FE`, `last_used_pre_preset_b=0x49FD`,
  `contiguous_free_before_0x4C00=514 bytes`, `free_object_words=257`.
- Net reclaim: **+2 bytes** of margin for T53, **+190 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE6 -> 0xE7)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 94 passed, 1 xfailed, 3 warnings in 15.45s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last exploratory run are
190/200, so no new 30-minute exploratory gate is due yet.

## T54 rail/ADC threshold compare helper — landed 2026-06-16

Scope:

- Added `compare_adc_rail_sample_to_threshold_w`, a carry-preserving helper for comparing
  `stock_088:089` against `0x02WW`.
- Replaced the boot-gate `0x0236` threshold compare, the standby rail
  `0x0228` threshold compare, and both periodic AN0 monitor compares
  (`0x0229` latch set and `0x0228` trip).
- Used a far `call` from `adc_boot_gate__check_rail_threshold` because the helper is out
  of relative range there; used `rcall` from the local standby and ADC monitor
  sites.
- Added a source contract pinning the helper body and all four call sites.

Measured result:

- Before T54: rev `0xE7`, `contiguous_free_before_0x4C00=514 bytes`.
- After T54 canonical rebuild: EEPROM rev `0xE7 -> 0xE8`,
  `listing_app_end=0x49F6`, `last_used_pre_preset_b=0x49F5`,
  `contiguous_free_before_0x4C00=522 bytes`, `free_object_words=261`.
- Net reclaim: **+8 bytes** of margin for T54, **+198 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE7 -> 0xE8)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v173_wake_responsiveness.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_layer5_diag_counters.py \
  tests/sim/test_v171_v32_standby_reconnect.py
# 190 passed, 1 xfailed in 271.01s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run are
198/200, so no new 30-minute exploratory gate is due yet.

## T55 volume DSP success-path redundant bank select — landed 2026-06-16

Scope:

- Removed the second `movlb 0x0` on the `volume_dsp_write` success path.
  The required post-I2C restore immediately before the NACK test already
  leaves BSR at bank 0, and the success path reaches the event/fault clears
  only by skipping the `bra vol_write_nacked`.
- Added a source contract pinning the single post-I2C bank restore and the
  success-path event/fault clears.

Measured result:

- Before T55: rev `0xE8`, `contiguous_free_before_0x4C00=522 bytes`.
- After T55 canonical rebuild: EEPROM rev `0xE8 -> 0xE9`,
  `listing_app_end=0x49F4`, `last_used_pre_preset_b=0x49F3`,
  `contiguous_free_before_0x4C00=524 bytes`, `free_object_words=262`.
- Net reclaim: **+2 bytes** of margin for T55, **+200 bytes** since the last
  exploratory run under the current 200-byte gate rule.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE8 -> 0xE9)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_review_findings.py::test_volume_dsp_write_retry_counter_increments \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_user_volume_and_preset_survive_por_power_cycle
# 59 passed, 1 xfailed in 37.08s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last exploratory run reached
200/200.  The required 30-minute exploratory chain hunt, card selection, and
subagent judge pass were completed immediately after T55; see the gate section
below.

## Exploratory gate after T55 — completed 2026-06-16

Trigger:

- T55 brought accepted bytes since the previous exploratory gate to **200/200**
  (`324 B -> 524 B` margin since the T22 gate reset).

Run evidence:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m \
  --status-interval 60 \
  --out-dir artifacts/reanalysis/v34_size_t55_exploratory_20260616
# run_dir=artifacts/reanalysis/v34_size_t55_exploratory_20260616/20260616_033524_480a827c50209f6a
# seed=0x480a827c50209f6a
# summary written: .../summary.md
```

Summary from `summary.md`:

- Sessions: 84
- Events: 8320
- Observations: 5807
- Incidents: `{'LOW': 1}`
- Duplicate incident signatures: 81
- Campaigns: saturation 10, preset-filename 15, ui 12, diag 11, src 11,
  standby-reset 8, preset-phase-sweep 8, fault-recovery 9

Card selection:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t55_exploratory_20260616 \
  --out artifacts/reanalysis/v34_size_t55_exploratory_20260616/cards \
  --top 8 --sample 2 --seed 200
# selected 10 cards (8 top + 2 sample)
```

Selected cards: sessions 19, 11, 69, 30, 65, 13, 43, 54, 68, 8.

Judge pass:

- Subagent judge output saved at
  `artifacts/reanalysis/v34_size_t55_exploratory_20260616/oracle_subagent_judge.json`.
- Verdict: `no_plausible_T54_T55_regression`.
- Cards reviewed: sessions 8, 11, 13, 19, 30, 43, 54, 65, 68, 69.
- Rationale summary: zero-synthetic preset/UI mismatch, waiting-connected, and
  transient coefficient-desync cards are concentrated in filename/UI,
  standby/reset, and preset-apply convergence stress paths, not in the T54
  rail/ADC threshold helper or T55 `volume_dsp_write` success-bank cleanup.
  Synthetic-heavy diag cards are better explained by SRC/TAS NACK and fault
  load.  No durable volume-write or rail-compare failure was evident.

Resolution:

- No T54/T55-specific rollback or follow-up fix is required.
- The exploratory gate is satisfied; accepted bytes since the last completed
  exploratory gate reset to **0/200** for the next batch.

## T56 preset apply cursor-to-I2C helper — landed 2026-06-16

Scope:

- Added `preset_job_apply_i2c_from_job_cursor`, which copies the job-owned
  physical preset table cursor (`preset_job_tbl_lo/hi`) into `stock_013:014`,
  calls `preset_job_apply_i2c_entry`, and returns with C preserved from the
  existing entry writer.
- Replaced four inline staging sequences: two in blocking
  `preset_replay_selected_table_blocking` replay and two in async `preset_job_apply` regular
  and final rows.
- Added source contracts pinning the helper body, both async retry branches,
  and both blocking replay call sites.

Measured result:

- Before T56: rev `0xE9`, `contiguous_free_before_0x4C00=524 bytes`.
- After T56 canonical rebuild: EEPROM rev `0xE9 -> 0xEA`,
  `listing_app_end=0x49E0`, `last_used_pre_preset_b=0x49DF`,
  `contiguous_free_before_0x4C00=544 bytes`, `free_object_words=272`.
- Net reclaim: **+20 bytes** of margin for T56, **+20 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xE9 -> 0xEA)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v32_src4382_autodetect_polling.py
# 123 passed, 1 xfailed in 350.66s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 20/200, so no new 30-minute exploratory gate is due yet.

## T57 preset apply cursor initialization helper — landed 2026-06-16

Scope:

- Added `preset_job_init_cursor_from_active`, which initializes the job-owned
  preset table cursor from `active_flags.bit2` and exits with `BSR=2`.
- Replaced the matching cursor initialization sequence in blocking
  `preset_replay_selected_table_blocking` and async `preset_job_holding`.
- Added source contracts pinning the helper body and both call sites.

Measured result:

- Before T57: rev `0xEA`, `contiguous_free_before_0x4C00=544 bytes`.
- After T57 canonical rebuild: EEPROM rev `0xEA -> 0xEB`,
  `listing_app_end=0x49D8`, `last_used_pre_preset_b=0x49D7`,
  `contiguous_free_before_0x4C00=552 bytes`, `free_object_words=276`.
- Net reclaim: **+8 bytes** of margin for T57, **+28 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xEA -> 0xEB)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v32_src4382_autodetect_polling.py
# 123 passed, 1 xfailed in 351.44s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 28/200, so no new 30-minute exploratory gate is due yet.

## T58 preset apply cursor advance helper — landed 2026-06-16

Scope:

- Added `preset_job_advance_cursor_to_next_table_row`, which advances the job-owned physical
  preset table cursor by one 0x18-byte row and increments
  `preset_job_index_b2`.
- Replaced the matching advance sequence in blocking `preset_replay_selected_table_blocking`
  and async `preset_job_apply`.
- Added source contracts pinning the helper body and both call sites.

Measured result:

- Before T58: rev `0xEB`, `contiguous_free_before_0x4C00=552 bytes`.
- After T58 canonical rebuild: EEPROM rev `0xEB -> 0xEC`,
  `listing_app_end=0x49D2`, `last_used_pre_preset_b=0x49D1`,
  `contiguous_free_before_0x4C00=558 bytes`, `free_object_words=279`.
- Net reclaim: **+6 bytes** of margin for T58, **+34 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xEB -> 0xEC)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v32_src4382_autodetect_polling.py
# 123 passed, 1 xfailed in 347.48s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 34/200, so no new 30-minute exploratory gate is due yet.

## T59 firmware-update duplicate nibble-mask peephole — landed 2026-06-16

Scope:

- Removed one duplicate `andwf fw_update_hex_or_float32_quotient_or_uart_block_scratch, F` after staging `movlw 0x0F`
  in `fw_update_relay` status/hex formatting.
- Added a source contract asserting the duplicate nibble mask stays removed.

Measured result:

- Before T59: rev `0xEC`, `contiguous_free_before_0x4C00=558 bytes`.
- After T59 canonical rebuild: EEPROM rev `0xEC -> 0xED`,
  `listing_app_end=0x49D0`, `last_used_pre_preset_b=0x49CF`,
  `contiguous_free_before_0x4C00=560 bytes`, `free_object_words=280`.
- Net reclaim: **+2 bytes** of margin for T59, **+36 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xEC -> 0xED)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 96 passed, 1 xfailed, 3 warnings in 15.40s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 36/200, so no new 30-minute exploratory gate is due yet.

## T60 firmware-update hex-digit helper reuse — landed 2026-06-16

Scope:

- Reused the existing `nibble_to_hex_ascii_from_01B` and
  `nibble_to_hex_ascii` helpers for the two `stock_080` firmware-update
  status hex digits.
- Removed the inline mask/lookup/`tblrd*` sequences; the caller still stages
  the same destination offsets (`0x9A`, `0x9B`) and writes TABLAT to INDF2.
- Added a source contract pinning the helper-based shape and blocking the old
  inline `hex_lookup_table_ptr` sequence from returning.

Measured result:

- Before T60: rev `0xED`, `contiguous_free_before_0x4C00=560 bytes`.
- After T60 canonical rebuild: EEPROM rev `0xED -> 0xEE`,
  `listing_app_end=0x49C0`, `last_used_pre_preset_b=0x49BF`,
  `contiguous_free_before_0x4C00=576 bytes`, `free_object_words=288`.
- Net reclaim: **+16 bytes** of margin for T60, **+52 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xED -> 0xEE)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 96 passed, 1 xfailed, 3 warnings in 15.34s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 52/200, so no new 30-minute exploratory gate is due yet.

## T61 flash-write TBLPTR staging helper — landed 2026-06-16

Scope:

- Added `flash_write_stage_block_cursor_shadow` for the repeated
  `stock_014..016 -> stock_011..013` TBLPTR staging sequence in
  `flash_write`.
- Replaced both inline staging copies (`flash_write__start_next_block` block restart
  and `flash_write__prepare_block_commit` block commit) with `rcall` sites.
- Added a source contract pinning the helper and blocking the old inline
  triple-`movff` sequence from returning.

Measured result:

- Before T61: rev `0xEE`, `contiguous_free_before_0x4C00=576 bytes`.
- After T61 canonical rebuild: EEPROM rev `0xEE -> 0xEF`,
  `listing_app_end=0x49BA`, `last_used_pre_preset_b=0x49B9`,
  `contiguous_free_before_0x4C00=582 bytes`, `free_object_words=291`.
- Net reclaim: **+6 bytes** of margin for T61, **+58 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xEE -> 0xEF)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 97 passed, 1 xfailed, 3 warnings in 15.25s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 58/200, so no new 30-minute exploratory gate is due yet.

## T62 newly reachable far helper rcalls — landed 2026-06-16

Scope:

- Replaced the now-in-range `call i2c_pen_timeout_recover_advertise` at
  `i2c_secondary_dev_random_pen_timeout` with `rcall`.
- Replaced the now-in-range volume-exhaustion `diag_r_b2` counter
  `call diag_inc_sat_fsr0` with `rcall`.
- Added a source contract for the two in-range conversions and left the later
  `diag_d_b2` call as a full `call`, since it is still outside `rcall` reach.

Measured result:

- Before T62: rev `0xEF`, `contiguous_free_before_0x4C00=582 bytes`.
- After T62 canonical rebuild: EEPROM rev `0xEF -> 0xF0`,
  `listing_app_end=0x49B6`, `last_used_pre_preset_b=0x49B5`,
  `contiguous_free_before_0x4C00=586 bytes`, `free_object_words=293`.
- Net reclaim: **+4 bytes** of margin for T62, **+62 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xEF -> 0xF0)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_v163b_robustness.py
# 138 passed, 1 xfailed in 246.91s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 62/200, so no new 30-minute exploratory gate is due yet.

## T63 math operand middle-copy helper — landed 2026-06-16

Scope:

- Added `copy_math_operand_low24_to_secondary` between the arithmetic callers so both
  users can reach it with `rcall`.
- Replaced the `float32_add_secondary_to_primary_in_place` middle operand copy
  (`stock_025..027 -> stock_029..02B`) with the helper while preserving the
  preceding `stock_024 -> stock_028` edge.
- Split `copy_math_operand_to_secondary_shadow` so it reuses the same middle-copy helper and still
  performs the trailing `stock_028 -> stock_02C` copy.

Measured result:

- Before T63: rev `0xF0`, `contiguous_free_before_0x4C00=586 bytes`.
- After T63 canonical rebuild: EEPROM rev `0xF0 -> 0xF1`,
  `listing_app_end=0x49B0`, `last_used_pre_preset_b=0x49AF`,
  `contiguous_free_before_0x4C00=592 bytes`, `free_object_words=296`.
- Net reclaim: **+6 bytes** of margin for T63, **+68 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF0 -> 0xF1)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_compatibility.py
# 77 passed, 1 xfailed in 98.47s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 68/200, so no new 30-minute exploratory gate is due yet.

## T64 USB descriptor TBLPTR staging helper — landed 2026-06-16

Scope:

- Added `usb_stage_tblptr_from_flash_ptr_cache` for the repeated USB descriptor
  `stock_075/076 -> TBLPTR` staging sequence.
- Replaced both the `usb_ep0_prepare_in_data_copy_pointers` setup path and the string
  descriptor pointer path in `usb_ep0_select_get_descriptor_payload` with `rcall` sites.
- Added a source contract pinning the shared staging helper and its two call
  sites.

Measured result:

- Before T64: rev `0xF1`, `contiguous_free_before_0x4C00=592 bytes`.
- After T64 canonical rebuild: EEPROM rev `0xF1 -> 0xF2`,
  `listing_app_end=0x49AC`, `last_used_pre_preset_b=0x49AB`,
  `contiguous_free_before_0x4C00=596 bytes`, `free_object_words=298`.
- Net reclaim: **+4 bytes** of margin for T64, **+72 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF1 -> 0xF2)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 100 passed, 1 xfailed, 3 warnings in 15.65s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 72/200, so no new 30-minute exploratory gate is due yet.

## T65 USB service stock_096 update helper — landed 2026-06-16

Scope:

- Added `usb_ep0_arm_next_out_pingpong_bd` for the duplicated
  `stock_096` countdown branch that sends either `0x01` or `0x00` through
  `usb_ep0_arm_out_pingpong_bd` and updates `stock_096`.
- Replaced both call-site copies in `usb_ep0_arm_control_transfer_response` /
  `usb_ep0_arm_control_transfer_response__arm_next_out_stage` with local `rcall`s while preserving their
  different post-helper branch/fall-through targets.
- Added a source contract pinning the helper and removal of the old local
  branch labels.

Measured result:

- Before T65: rev `0xF2`, `contiguous_free_before_0x4C00=596 bytes`.
- After T65 canonical rebuild: EEPROM rev `0xF2 -> 0xF3`,
  `listing_app_end=0x499A`, `last_used_pre_preset_b=0x4999`,
  `contiguous_free_before_0x4C00=614 bytes`, `free_object_words=307`.
- Net reclaim: **+18 bytes** of margin for T65, **+90 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF2 -> 0xF3)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 101 passed, 1 xfailed, 3 warnings in 15.64s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 90/200, so no new 30-minute exploratory gate is due yet.

## T66 USB stock_116 bank-store helper — landed 2026-06-16

Scope:

- Added `usb_stage_bdt_template_status_w` at a central `rcall`-reachable boundary
  between `main_core_service_38a2` and `adaptive_baud_select`.
- Replaced all five USB `stock_116` W stores with local `rcall`s:
  four in `shift_003_006_right_clear_c` and one in `usb_bus_reset_reinitialize`.
- The helper restores BSR to bank 0.  For the two original sites that entered
  `usb_ep0_arm_out_pingpong_bd` with BSR=1, this is safe because
  `usb_ep0_arm_out_pingpong_bd` stages W in access RAM and selects bank 1 before any
  BANKED access.

Measured result:

- Before T66: rev `0xF3`, `contiguous_free_before_0x4C00=614 bytes`.
- After T66 canonical rebuild: EEPROM rev `0xF3 -> 0xF4`,
  `listing_app_end=0x4994`, `last_used_pre_preset_b=0x4993`,
  `contiguous_free_before_0x4C00=620 bytes`, `free_object_words=310`.
- Net reclaim: **+6 bytes** of margin for T66, **+96 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF3 -> 0xF4)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 102 passed, 1 xfailed, 3 warnings in 15.47s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 96/200, so no new 30-minute exploratory gate is due yet.

## T67 i2c_apply_channel_route_sync_burst bank-0 clear wrapper — landed 2026-06-16

Scope:

- Added `ram_block_clear_four_bytes_bank0_from_w`, which accepts the low address in W, clears
  `stock_004`, restores BSR 0, and tail-branches into the existing
  `ram_block_clear_four_bytes_from_w` helper.
- Replaced the four bank-0 clear setup blocks in `i2c_apply_channel_route_sync_burst` with
  local `rcall`s to the wrapper.
- Preserved the three bank-1 clears through `ram_clear_prepare_page1_address_high` plus
  `ram_block_clear_four_bytes_from_w`.

Measured result:

- Before T67: rev `0xF4`, `contiguous_free_before_0x4C00=620 bytes`.
- After T67 canonical rebuild: EEPROM rev `0xF4 -> 0xF5`,
  `listing_app_end=0x498C`, `last_used_pre_preset_b=0x498B`,
  `contiguous_free_before_0x4C00=628 bytes`, `free_object_words=314`.
- Net reclaim: **+8 bytes** of margin for T67, **+104 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF4 -> 0xF5)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v32_main_i2c_service_2100_tables.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v32_src4382_audio_path_regression.py
# 84 passed, 1 xfailed in 25.51s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 104/200, so no new 30-minute exploratory gate is due yet.

## T68 cmd_dispatch reg1f route-3 tail reuse — landed 2026-06-16

Scope:

- Removed the duplicate `0x08/0x30` route-pair staging after
  `i2c_tas3108_reg1f_write` in `cmd_dispatch_gated__default_route_reg1f_write`.
- Replaced it with a direct branch to the existing
  `cmd_dispatch_gated__route_code_3_i2c_pair` route-3 setup owner.
- Added a source contract proving the reg1f path tails to that owner and no
  longer carries its own `stock_006` staging block.

Measured result:

- Before T68: rev `0xF5`, `contiguous_free_before_0x4C00=628 bytes`.
- After T68 canonical rebuild: EEPROM rev `0xF5 -> 0xF6`,
  `listing_app_end=0x4986`, `last_used_pre_preset_b=0x4985`,
  `contiguous_free_before_0x4C00=634 bytes`, `free_object_words=317`.
- Net reclaim: **+6 bytes** of margin for T68, **+110 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF5 -> 0xF6)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v171_v32_source_select_parity.py \
  tests/sim/test_v31_command_matrix.py
# 134 passed, 1 xfailed in 200.35s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 110/200, so no new 30-minute exploratory gate is due yet.

## T69 USB stock_0C8/offset prelude helper — landed 2026-06-16

Scope:

- Added `usb_ep0_stage_interface_alt_setting_offset`, which sets `stock_0C8=1` and returns
  W as `stock_0D3 + 0xEC`.
- Replaced the two identical preludes in `usb_ep0_dispatch_standard_setup_request__get_interface`
  and `usb_ep0_dispatch_standard_setup_request__set_interface`; each caller still consumes W in its
  original destination (`stock_005` vs `FSR2L`).
- Added a source contract pinning the helper and both call sites.

Measured result:

- Before T69: rev `0xF6`, `contiguous_free_before_0x4C00=634 bytes`.
- After T69 canonical rebuild: EEPROM rev `0xF6 -> 0xF7`,
  `listing_app_end=0x4984`, `last_used_pre_preset_b=0x4983`,
  `contiguous_free_before_0x4C00=636 bytes`, `free_object_words=318`.
- Net reclaim: **+2 bytes** of margin for T69, **+112 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF6 -> 0xF7)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 105 passed, 1 xfailed, 3 warnings in 15.64s
```

The xfail is the known `chain_copy` interrupt-safety proof.  The warnings are
PyUSB/libusb0 deprecations in `test_dlcp_main_flash.py`.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 112/200, so no new 30-minute exploratory gate is due yet.

## T70 UART TX retry tail reuse — landed 2026-06-16

Scope:

- Added `uart_tx_byte_send` at the existing normal `uart_tx_byte_blocking`
  transmit tail.
- Replaced the retry-after-timeout duplicate `TXREG`/W-restore/return tail with
  `bra uart_tx_byte_send`.
- The normal path remains fall-through; only the bounded TRMT timeout retry path
  branches to the already-proven send tail.

Measured result:

- Before T70: rev `0xF7`, `contiguous_free_before_0x4C00=636 bytes`.
- After T70 canonical rebuild: EEPROM rev `0xF7 -> 0xF8`,
  `listing_app_end=0x497E`, `last_used_pre_preset_b=0x497D`,
  `contiguous_free_before_0x4C00=642 bytes`, `free_object_words=321`.
- Net reclaim: **+6 bytes** of margin for T70, **+118 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF7 -> 0xF8)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_uart_terminal_recovery_branches_directly_to_hard_reset \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_reply_helpers_participate_in_chain_tx_emitted_contract \
  tests/sim/test_v32_layer5_diag_counters.py::test_v32_diag_send_burst_helper_uses_postinc0_indirect \
  tests/sim/test_v34_v173_i2c_recovery_contract.py::test_v34_i2c_timeout_recovery_sets_visible_diag_and_carry_contract \
  tests/sim/test_v31_review_findings.py::test_bf08_payload_bytes_on_dsp_fault \
  tests/sim/test_v171_v32_chain_bf08_integration.py::test_main0_dsp_nack_drives_bf08_through_wire_chain_to_control \
  tests/sim/test_v171_v32_chain_bf08_integration.py::test_clean_dsp_chain_does_not_set_control_dsp_fault_bit
# 7 passed in 21.01s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 118/200, so no new 30-minute exploratory gate is due yet.

## T71 Timer3 stop helper reuse — landed 2026-06-16

Scope:

- Reused the existing `timer3_stop_interrupt_countdown` Timer3 stop/flag helper in the
  reconnect full-apply cancellation path.
- Reused the same helper from `preset_job_cancel_unmute` and
  `preset_job_cancel`, replacing duplicate inline Timer3 stop/mask/clear blocks.
- The helper is ACCESS-SFR-only and BSR-neutral; the preset paths still clear
  `preset_job_state_b2` only through the existing `preset_job_service__clear_state_and_return` tail.

Measured result:

- Before T71: rev `0xF8`, `contiguous_free_before_0x4C00=642 bytes`.
- After T71 canonical rebuild: EEPROM rev `0xF8 -> 0xF9`,
  `listing_app_end=0x4974`, `last_used_pre_preset_b=0x4973`,
  `contiguous_free_before_0x4C00=652 bytes`, `free_object_words=326`.
- Net reclaim: **+10 bytes** of margin for T71, **+128 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF8 -> 0xF9)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v32_usb_filename_xact_gate.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v171_v32_standby_reconnect.py
# 82 passed, 1 xfailed in 144.53s
```

The xfail is the known `chain_copy` interrupt-safety proof.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 128/200, so no new 30-minute exploratory gate is due yet.

## T72 MSSP hard-reset SMP/master prelude helper — landed 2026-06-16

Scope:

- Added `mssp_hard_reset_smp_master`, which stages `stock_003=0x80` and W=`0x08`
  before tail-branching into `mssp_hard_reset`.
- Replaced the three identical SMP/master preludes in `run_wake_rail_gate_and_dsp_cold_init`,
  `dsp_ping_nack_reset`, and `i2c_timeout_recover_common`.
- The helper is ACCESS-only and preserves the original `mssp_hard_reset` return
  convention, including W left as the staged SSPSTAT byte.

Measured result:

- Before T72: rev `0xF9`, `contiguous_free_before_0x4C00=652 bytes`.
- After T72 canonical rebuild: EEPROM rev `0xF9 -> 0xFA`,
  `listing_app_end=0x496A`, `last_used_pre_preset_b=0x4969`,
  `contiguous_free_before_0x4C00=662 bytes`, `free_object_words=331`.
- Net reclaim: **+10 bytes** of margin for T72, **+138 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xF9 -> 0xFA)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_v163b_robustness.py \
  tests/sim/test_v31_review_findings.py::test_dsp_path_recovers_after_mssp_stop_fault_cleared \
  tests/sim/test_v31_review_findings.py::test_bf08_payload_bytes_on_dsp_fault \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v32_src4382_autodetect_polling.py::test_v32_mssp_hard_reset_clears_bclif_source_flag \
  tests/sim/test_v171_v32_standby_reconnect.py
# 26 passed in 29.09s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 138/200, so no new 30-minute exploratory gate is due yet.

## T73 LATA3/4/5 audio-pin clear tail share — landed 2026-06-16

Scope:

- Split a `clear_lata_source_select_pins` tail label out of `clear_lata_audio_pins`, preserving
  the existing LATA6/3/4/5 helper entry.
- Replaced the duplicate `i2c_tas3108_reg1f_02_clear_source_pins` LATA3/4/5 clear/return tail
  with `goto clear_lata_source_select_pins`.
- An initial `bra` attempt was rejected by gpasm as out of range; the accepted
  far `goto` keeps the tail share and saves 4 bytes.

Measured result:

- Before T73: rev `0xFA`, `contiguous_free_before_0x4C00=662 bytes`.
- After T73 canonical rebuild: EEPROM rev `0xFA -> 0xFB`,
  `listing_app_end=0x4966`, `last_used_pre_preset_b=0x4965`,
  `contiguous_free_before_0x4C00=666 bytes`, `free_object_words=333`.
- Net reclaim: **+4 bytes** of margin for T73, **+142 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# first build rejected `bra clear_lata_source_select_pins` as out of range; accepted build:
# built canonical V3.4 release ... (EEPROM rev 0xFA -> 0xFB)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v171_v32_standby_reconnect.py \
  tests/sim/test_main_stdby_pin_io.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py
# 53 passed in 62.92s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 142/200, so no new 30-minute exploratory gate is due yet.

## T74 newly reachable diag_inc_sat_fsr0 rcall — landed 2026-06-16

Scope:

- After T70-T73 shrinkage, the `diag_d` transition counter in the volume DSP
  retry-exhausted path became just reachable by `rcall`.
- Replaced the remaining far `call diag_inc_sat_fsr0` at the
  `vol_exhausted_skip_i2c` transition with `rcall diag_inc_sat_fsr0`.

Measured result:

- Before T74: rev `0xFB`, `contiguous_free_before_0x4C00=666 bytes`.
- After T74 canonical rebuild: EEPROM rev `0xFB -> 0xFC`,
  `listing_app_end=0x4964`, `last_used_pre_preset_b=0x4963`,
  `contiguous_free_before_0x4C00=668 bytes`, `free_object_words=334`.
- Net reclaim: **+2 bytes** of margin for T74, **+144 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xFB -> 0xFC)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_review_findings.py \
  tests/sim/test_v31_v163b_robustness.py \
  tests/sim/test_v32_layer5_diag_counters.py
# 68 passed in 20.51s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 144/200, so no new 30-minute exploratory gate is due yet.

## T75 TAS3108 reg1F zero-byte TX helper — landed 2026-06-16

Scope:

- Added `i2c_byte_tx_zero`, which stages W=`0x00` and tail-branches to
  `i2c_byte_tx`.
- Replaced the three zero upper-address-byte writes in
  `i2c_tas3108_reg1f_write` with `rcall i2c_byte_tx_zero`.
- This keeps the TAS3108 wire sequence
  `0x68, 0x1F, 0x00, 0x00, 0x00, <data>` and reuses the existing
  `i2c_byte_tx` return convention.

Measured result:

- Before T75: rev `0xFC`, `contiguous_free_before_0x4C00=668 bytes`.
- After T75 canonical rebuild: EEPROM rev `0xFC -> 0xFD`,
  `listing_app_end=0x4962`, `last_used_pre_preset_b=0x4961`,
  `contiguous_free_before_0x4C00=670 bytes`, `free_object_words=335`.
- Net reclaim: **+2 bytes** of margin for T75, **+146 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xFC -> 0xFD)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v34_mute_refresh_bug.py
# 48 passed in 54.76s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 146/200, so no new 30-minute exploratory gate is due yet.

## T76 preset APPLY tail branches — landed 2026-06-16

Scope:

- Replaced `preset_job_apply_i2c_from_job_cursor`'s final
  `rcall preset_job_apply_i2c_entry` / `return` pair with
  `bra preset_job_apply_i2c_entry`.
- Replaced the normal APPLY-step cursor-advance `rcall` / `return` pair with
  `bra preset_job_advance_cursor_to_next_table_row`.
- Updated the structural contract test to pin the tail-branch form while
  preserving the same retry and cursor ordering assertions.

Measured result:

- Before T76: rev `0xFD`, `contiguous_free_before_0x4C00=670 bytes`.
- After T76 canonical rebuild: EEPROM rev `0xFD -> 0xFE`,
  `listing_app_end=0x495E`, `last_used_pre_preset_b=0x495D`,
  `contiguous_free_before_0x4C00=674 bytes`, `free_object_words=337`.
- Net reclaim: **+4 bytes** of margin for T76, **+150 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xFD -> 0xFE)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_preset_apply_is_transaction_checked_and_physical_source_owned \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_field6_lifecycle_reassert_uses_validated_writer_and_route_drain \
  tests/sim/test_v34_v173_i2c_recovery_contract.py::test_v34_async_apply_timeout_retries_same_entry_after_visible_recovery \
  tests/sim/test_v34_v173_compatibility.py
# 11 passed in 73.83s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 150/200, so no new 30-minute exploratory gate is due yet.

## T77 SRC status-read timeout recovery `rcall` — landed 2026-06-16

Scope:

- `i2c_secondary_dev_random_timeout` became close enough to
  `i2c_timeout_recover_advertise` after the preceding shrink work to use an
  `rcall`.
- The timeout path still advertises the visible I2C recovery counters, clears W
  on return, and preserves the existing callers' `W=0` transport-loss contract
  for SRC4382 status reads.
- No route, mute, preset, or SRC retry policy changed.

Measured result:

- Before T77: rev `0xFE`, `contiguous_free_before_0x4C00=674 bytes`.
- After T77 canonical rebuild: EEPROM rev `0xFE -> 0xFF`,
  `listing_app_end=0x495C`, `last_used_pre_preset_b=0x495B`,
  `contiguous_free_before_0x4C00=676 bytes`, `free_object_words=338`.
- Net reclaim: **+2 bytes** of margin for T77, **+152 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xFE -> 0xFF)

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v32_src4382_autodetect_polling.py::test_v32_src4382_status_read_timeout_does_not_clear_good_route \
  tests/sim/test_v32_src4382_autodetect_polling.py::test_v32_i2c_byte_tx_wcol_enters_recovery_and_clears_latch \
  tests/sim/test_v32_src4382_audio_path_regression.py
# 18 passed in 11.99s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are 145/200 after the 16-bit identity policy, so no new 30-minute
exploratory gate is due.

Release-revision note: T77 advanced the legacy low-byte revision mirror at
EEPROM `0x82` to `0xFF`.  On 2026-06-16 the V3.4 release policy changed to a
16-bit cmd `0x25` identity revision; EEPROM `0x82` remains the low-byte
compatibility mirror because EEPROM `0x83` is the Preset-B filename slot.

## T78 UART channel-config mirror helper — landed 2026-06-16

Scope:

- The six MAIN UART channel-config handlers for `stock_060..065` and
  mirrors `stock_0A5..0AA` used to inline the same current-data store,
  `cpfseq` dirty check, event bit set, mirror update, and parser-tail branch.
- T78 keeps the six legacy dispatch labels but reduces each body to
  `movlw offset; bra uart_update_channel_config_cache_from_w_index`.
- The helper computes `FSR0 = stock_060 + offset` and `FSR1 = FSR0 + 0x45`,
  writes `current_cmd_data`, compares the mirror with `cpfseq INDF1`, sets
  `event_flags.bit4` only on a changed mirror, updates the mirror, and returns
  through the existing `uart_link_parser__handler_return_tail` parser tail.

Measured result:

- Before T78: V3.4 rev `0x0001`, `listing_app_end=0x4962`,
  `contiguous_free_before_0x4C00=669 bytes`.
- After T78 canonical rebuild: V3.4 rev `0x0002`,
  `listing_app_end=0x494E`,
  `contiguous_free_before_0x4C00=689 bytes`.
- Net reclaim: **+20 bytes** of margin for T78, **+20 bytes** since the
  16-bit identity policy.

Liveness/safety assumptions:

- `FSR0`/`FSR1` are local parser scratch on this path; the shared parser tail
  does not rely on their incoming values.
- The helper asserts `BSR=0` before `current_cmd_data_b0` and
  `event_flags_b0` banked accesses, matching the original bank-0 path.
- The active and mirror ranges are contiguous bank-0 spans separated by
  `0x45` bytes (`0x060..0x065` -> `0x0A5..0x0AA`), so the indexed helper cannot
  cross a bank boundary for the accepted offsets `0..5`.

## T79 route-bit I2C selector peephole — landed 2026-06-16

Scope:

- The six `event_flags.bit6` route/channel writes in `cmd_dispatch_gated`
  selected between literal pairs such as `0x1C/0x08`, `0x44/0x30`, ...
  `0xE4/0xD0` with a two-branch diamond per bit.
- T79 keeps the same write order and helper boundary, but uses the arithmetic
  identity `high = low - 0x14`: `movlw low; btfsc stock_0A4.bitN; addlw 0xEC`.
- At T79 time, the first five writes still used `i2c_381c_with_w_bank0` and
  the sixth remained the direct `movwf stock_013; call preset_table_apply_entry_legacy_blocking`
  tail.  T140 later superseded that local shape with a compact six-iteration
  loop while preserving T79's `+0xEC` selector rule.

Measured result:

- Before T79: V3.4 rev `0x0002`, `listing_app_end=0x494E`,
  `contiguous_free_before_0x4C00=689 bytes`.
- After T79 canonical rebuild: V3.4 rev `0x0003`,
  `listing_app_end=0x4934`,
  `contiguous_free_before_0x4C00=715 bytes`.
- Net reclaim: **+26 bytes** of margin for T79, **+46 bytes** since the
  16-bit identity policy.

Liveness/safety assumptions:

- `btfsc` preserves W when the bit is clear; when set, `addlw 0xEC` produces
  the exact old high literal modulo 8 bits.
- The existing helper reasserts `BSR=0` after each of the first five writes,
  so every following `btfsc channel_enable_mask_b0` still addresses bank 0.
- The final direct write had no post-call BSR dependency before
  `usb_hid_mailbox_stage_selector5_if_enabled`, which already sets BSR itself.

## T80 I2C random-read timeout tail cross-jump — landed 2026-06-16

Scope:

- `i2c_receive_sspbuf_bounded__timeout` had the same timeout-advertise, clear-W,
  return sequence as `i2c_secondary_dev_random_timeout`.
- T80 replaces the duplicate local tail with `bra i2c_secondary_dev_random_timeout`.

Measured result:

- Before T80: V3.4 rev `0x0003`, `listing_app_end=0x4934`,
  `contiguous_free_before_0x4C00=715 bytes`.
- After T80 canonical rebuild: V3.4 rev `0x0004`,
  `listing_app_end=0x4930`,
  `contiguous_free_before_0x4C00=719 bytes`.
- Net reclaim: **+4 bytes** of margin for T80, **+50 bytes** since the
  16-bit identity policy.

Liveness/safety assumptions:

- Both tails return with W cleared and the timeout recovery helper's carry/
  diagnostic side effects; no caller distinguishes which timeout label did
  the final clear/return.
- The branch is local-range and avoids adding stack depth.

## T81 redundant bank-select cleanup — landed 2026-06-16

Scope:

- Removed `movlb 0` before an ACCESS-only `bcf active_flags_acc,4` in
  `cmd03_mute_off_apply`; the path immediately selects bank 2 afterward.
- Removed the second `movlb 2` in `advance_preset_job_state_machine` dispatch; entry already
  selected bank 2 and the intervening active/reconnect tests use ACCESS
  addressing only.
- Removed two local `movlb 0` assertions in the SRC Auto Detect path where
  both paths immediately branch to `poll_src4382_route_monitor__finalize_pending_route`, whose
  first instruction reasserts bank 0.

Measured result:

- Before T81: V3.4 rev `0x0004`, `listing_app_end=0x4930`,
  `contiguous_free_before_0x4C00=719 bytes`.
- After T81 canonical rebuild: V3.4 rev `0x0005`,
  `listing_app_end=0x4928`,
  `contiguous_free_before_0x4C00=727 bytes`.
- Net reclaim: **+8 bytes** of margin for T81, **+58 bytes** since the
  16-bit identity policy.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0004 -> 0x0005)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_redundant_local_movlb_zero_assertions_stay_removed \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_zero_peepholes_stay_compact_without_status_sensitive_reuse \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_field6_lifecycle_reassert_uses_validated_writer_and_route_drain \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom
# 4 passed in 0.07s
```

Exploratory gate status: T81 brought accepted bytes since the last completed
exploratory gate to **203/200**, so the required 30-minute exploratory run,
card selection, and local judge pass were completed immediately after T81; see
the gate section below.

## Exploratory gate after T81 — completed 2026-06-16

Trigger:

- T78/T79/T80/T81 plus the 16-bit identity-policy adjustment brought accepted
  bytes since the previous exploratory gate to **203/200**.

Run evidence:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m \
  --status-interval 60 \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/reanalysis/v34_size_t81_exploratory_20260616
# run_dir=artifacts/reanalysis/v34_size_t81_exploratory_20260616/20260616_085226_300235eb145425db
# seed=0x300235eb145425db
# summary written: .../summary.md
```

Summary from `summary.md`:

- Sessions: 82
- Events: 10679
- Observations: 8379
- Incidents: `{'LOW': 1}`
- Duplicate incident signatures: 53
- Campaigns: diag 13, preset-filename 12, preset-phase-sweep 17, ui 16,
  fault-recovery 4, src 10, standby-reset 6, saturation 4

Card selection:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t81_exploratory_20260616 \
  --out artifacts/reanalysis/v34_size_t81_exploratory_20260616/cards \
  --top 8 --sample 2 --seed 203
# selected 10 cards (8 top + 2 sample)
```

Selected cards: sessions 50, 24, 13, 38, 68, 36, 9, 45, 71, 6.

Local judge verdict:

- Verdict: `no_plausible_T78_T81_regression`.
- The only deduplicated incident was `LOW ui.waiting.connected` in session 6;
  no MEDIUM/HIGH incidents were produced.
- Selected cards were concentrated in UI, diagnostics, standby/reset, and
  preset-filename stress paths.  Several high-divergence cards carried
  synthetic TAS/SRC fault load or reset/standby churn.
- No selected card implicated the touched T78-T81 code paths: UART
  channel-config mirror storage, route-bit I2C literal selection, random-read
  timeout tail sharing, or local bank-select removal.

Resolution:

- No T78/T79/T80/T81 rollback or follow-up fix is required.
- The exploratory gate is satisfied; accepted bytes since the last completed
  exploratory gate reset to **0/200** for the next batch.

## T82 math result FSR2 rewind tail share — landed 2026-06-16

Scope:

- `float32_multiply_ram_window_by_staged_operand_in_place` and `float32_add_staged_operand_to_ram_window_in_place` both wrote four bytes
  through FSR2 and then ended with the same `decf FSR2L` twice plus `return`.
- T82 labels the first tail as `rewind_fsr2_after_four_byte_math_result_store` and has the second
  helper branch to it after its final `POSTDEC2` write.

Measured result:

- Before T82: V3.4 rev `0x0005`, `listing_app_end=0x4928`,
  `contiguous_free_before_0x4C00=727 bytes`.
- After T82 canonical rebuild: V3.4 rev `0x0006`,
  `listing_app_end=0x4924`,
  `contiguous_free_before_0x4C00=731 bytes`.
- Net reclaim: **+4 bytes** of margin for T82, **+4 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0005 -> 0x0006)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_math_result_helpers_share_fsr2_rewind_tail \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom
# 2 passed in 0.13s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **4/200**, so no new 30-minute exploratory gate is due yet.

## Current rev 0x003D size snapshot

FIELD-9/FIELD-10 safety fixes after T1 consumed 88 bytes of the rev-`0xA5`
reserve; after the 16-bit identity policy and T2-T131, the current doc-margin
is 1383 bytes, a net 1369-byte gain over the post-FIELD-10 floor.  The current accepted floor is
10 bytes before `org 0x4C00`, not the older 64-object-word refactoring target.

Measured from the current `src/dlcp_fw/asm/dlcp_main_v34.lst`:

- current canonical MAIN: V3.4 rev `0x003D`
- `listing_app_end=0x4698`
- gate-style margin `0x4C00 - listing_app_end = 1384 bytes`
- `contiguous_free_before_0x4C00=1383 bytes`
- `free_object_words=692`

The 1383-byte margin keeps the promoted FIELD-10 safety line above the
user-relaxed floor while preserving both preset
capture banks at `0x4C00..0x55FF` and `0x5600..0x5FFF`.

Current campaign status:

- Rev `0x003D` is the current accepted canonical V3.4 size-reclaim state.
- Net accepted reclaim since the post-FIELD-10 rev `0xAC` floor is
  **1369 bytes** (`14 B -> 1383 B` before `0x4C00`).
- The T108-T124 batch moved doc-margin from 1131 to 1329 bytes.  The run
  counter reached the 200-byte exploratory threshold in gate-margin terms, so
  the T124 exploratory gate completed on 2026-06-16 before any further source
  edits.  T125-T131 add 54 accepted bytes after that gate, so accepted bytes
  since that gate are **54/200**.
- No functionality was demoted and no preset bank layout changed.
- T99's FIELD-10 fault-flag helper was rejected; the behavior-slice failures
  seen during that attempt were reproduced without T99/T100/T101 and are not
  attributed to the accepted size slices.

## Exploratory gate after T91 — completed 2026-06-16

Command:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m \
  --status-interval 60 \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/reanalysis/v34_size_t91_exploratory_20260616
```

Run:

- artifact dir:
  `artifacts/reanalysis/v34_size_t91_exploratory_20260616/20260616_101825_b06f83d6dcb2cfe0`
- seed: `0xb06f83d6dcb2cfe0`
- sessions/events/observations: 81 / 8880 / 6482
- campaigns: preset-phase-sweep, saturation, UI, SRC, preset-filename, diag,
  fault-recovery, standby-reset
- incidents: `{'LOW': 1}`, duplicate incident signatures: 55

The single deduplicated incident was the previously seen LOW
`waiting-connected` signature: CONTROL was connected but still rendering
`Waiting for DLCP` after a UI stress sequence with standby/host-preset
actions.  The snapshot did not show durable coefficient, volume, preset-job, or
identity corruption: PB1/PB2 logical and computed volume matched, preset jobs
were idle, and diagnostics state was coherent for the stress state.

Selected cards were rendered with:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t91_exploratory_20260616 \
  --out artifacts/reanalysis/v34_size_t91_exploratory_20260616/cards \
  --top 8 --sample 2 --seed 204
```

Local judge verdict: **no plausible T88-T91 regression**.  The selected cards
exercise diag/UI/standby-reset/preset-filename stress rather than a new failure
in the copy-descriptor paths.  The V1.73 display format is present in selected
diag cards as `PB1 OK v3.4 000F` / `PB2 OK v3.4 000F`, and selected
volume-changing observations kept MAIN logical/computed volume synchronized.
No rollback or follow-up patch is tied to this gate.

## Exploratory gate after T107 — completed 2026-06-16

T92/T93/T94/T95/T96/T97/T98/T100/T101/T102/T103/T104/T105/T106/T107 accepted
exactly 200 bytes since the T91 gate, so the next 30-minute exploratory gate
was due and was run before any further accepted reclaim.

Command:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m \
  --status-interval 60 \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/reanalysis/v34_size_t107_exploratory_20260616
```

Run:

- artifact dir:
  `artifacts/reanalysis/v34_size_t107_exploratory_20260616/20260616_121113_eeb9407fb961e730`
- seed: `0xeeb9407fb961e730`
- sessions/events/observations: 79 / 7224 / 4671
- campaigns: standby-reset, preset-filename, preset-phase-sweep, UI, SRC,
  fault-recovery, saturation, diag
- incidents: `{'LOW': 1}`, duplicate incident signatures: 82

The single deduplicated incident was again the known LOW `waiting-connected`
signature.  The snapshot showed connected MAINs with idle preset jobs,
coherent preset/volume state, and no new coefficient or identity corruption
signature tied to T100-T107.

Selected cards were rendered with:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t107_exploratory_20260616 \
  --out artifacts/reanalysis/v34_size_t107_exploratory_20260616/cards \
  --top 8 --sample 2 --seed 200
```

Local verdict: **no plausible T100-T107 regression**.  Accepted bytes since the
last completed exploratory gate reset to **0/200** for the next batch.

## Exploratory gate after T124 — completed 2026-06-16

T108-T124 crossed the current 200-byte exploratory threshold in gate-margin
terms, so a 30-minute chain hunt was run before any further accepted source
change.

Command:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m \
  --status-interval 60 \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/reanalysis/v34_size_t124_exploratory_20260616
```

Run:

- artifact dir:
  `artifacts/reanalysis/v34_size_t124_exploratory_20260616/20260616_141723_266342a4053ee66e`
- seed: `0x266342a4053ee66e`
- sessions/events/observations: 81 / 8924 / 6495
- campaigns: fault-recovery, standby-reset, preset-filename,
  preset-phase-sweep, diag, UI, SRC, saturation
- incidents: `{'LOW': 1}`, duplicate incident signatures: 98

The single deduplicated incident was the already-known LOW
`waiting-connected` signature: CONTROL connected while still rendering
`Waiting for DLCP` after UI/wake stress.  The incident snapshot showed idle
preset jobs, matching PB1/PB2 coefficient state, coherent reset/diagnostic
state, and no new identity, filename, volume, or chain-forwarding corruption
tied to T108-T124.

Selected cards were rendered with:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t124_exploratory_20260616 \
  --out artifacts/reanalysis/v34_size_t124_exploratory_20260616/cards \
  --top 8 --sample 2 --seed 202
```

Local verdict: **no plausible T108-T124 regression**.  The selected
diag/UI/preset-filename/fault-recovery cards either recovered from WAITING to a
normal page or reflected deliberate injected TAS/SRC/I2C faults.  Accepted
bytes since the last completed exploratory gate reset to **0/200** for the
next batch.

## T125 USB endpoint pointer/clear peepholes — landed 2026-06-16

Scope:

- `usb_sie_endpoint_pump` now stages the endpoint pointer high byte once,
  leaves W as `0x04` for the USTAT bit-1 case, and conditionally changes W to
  `0x00` only for the other endpoint before storing `stock_07A`.
- The nonzero-endpoint USTAT `0x04` path now clears `UIR.3` once before the
  branch that decides whether `usb_ep0_service_in_transaction` is needed, instead of
  carrying duplicate clear tails.

Measured result:

- Before T125: V3.4 rev `0x0036`,
  `contiguous_free_before_0x4C00=1329 bytes`.
- After T125 canonical rebuild: V3.4 rev `0x0037`,
  `listing_app_end=0x46C2`,
  `contiguous_free_before_0x4C00=1341 bytes`.
- Net reclaim: **+12 bytes** of margin for T125, **+12 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0036 -> 0x0037)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_service_endpoint_dispatch_uses_compact_common_tails \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_redundant_local_movlb_zero_assertions_stay_removed \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_usb_hid_dispatch.py
# 8 passed in 5.49s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **12/200**, so no new 30-minute exploratory gate is due yet.

## T126 immediate fall-through branch removals — landed 2026-06-16

Scope:

- Removed five unconditional `bra` instructions whose targets were the
  immediately following label:
  `flow_main_uart_service_1be6_1df0 -> uart_update_channel_config_cache_from_w_index`,
  `usb_sie_endpoint_pump__service_ep0_in_token_if_selected -> usb_sie_endpoint_pump__advance_transaction_scan`,
  `usb_ep1_in_send_hid_reply_buffer -> usb_ep1_in_copy_scratch_buffer_to_bdt`,
  `usb_ep1_in_copy_scratch_buffer_to_bdt -> usb_endpoint_mark_state_done`, and
  `mssp_hard_reset_smp_master -> mssp_hard_reset`.
- The edit changes only fall-through spelling; no helper latency, RAM write
  order, or preset/diagnostic behavior changes.

Measured result:

- Before T126: V3.4 rev `0x0037`,
  `contiguous_free_before_0x4C00=1341 bytes`.
- After T126 canonical rebuild: V3.4 rev `0x0038`,
  `listing_app_end=0x46B8`,
  `contiguous_free_before_0x4C00=1351 bytes`.
- Net reclaim: **+10 bytes** of margin for T126, **+22 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0037 -> 0x0038)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_redundant_immediate_fallthrough_branches_stay_removed \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_service_endpoint_dispatch_uses_compact_common_tails
# 2 passed in 0.12s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_redundant_immediate_fallthrough_branches_stay_removed \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_service_endpoint_dispatch_uses_compact_common_tails \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_wreg_access_stores_use_single_word_movwf_shape \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_channel_config_handlers_share_offset_indexed_mirror_dirty_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_unconditional_call_return_tails_are_direct_branches
# 5 passed in 0.04s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_main_gpsim_usb_engine.py
# 8 passed in 3.66s
```

One intermediate pytest invocation used two stale structural test names and
collected no tests; the valid focused names above were rerun and passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **22/200**, so no new 30-minute exploratory gate is due yet.

## T127 low-page USB descriptor dirty helper — landed 2026-06-16

Scope:

- Added `usb_ep0_stage_one_byte_lowpage_in_data_pointer` as a fall-through entry into
  the existing `usb_ep0_mark_one_byte_lowpage_in_data_ready` tail.
- Three low-page descriptor staging paths now set `stock_0C8`, load the low
  descriptor byte in W, and branch into the helper.  The helper preserves the
  RAM update order for descriptor address bytes (`stock_076` high clear, then
  `stock_075` low store) before falling into the dirty-return tail.
- The saved-W descriptor path in `usb_ep0_dispatch_standard_setup_request` now branches directly
  to `usb_ep0_mark_one_byte_lowpage_in_data_ready`; it already performs its high/low
  stores inline and does not use the W-input helper.

Measured result:

- Before T127: V3.4 rev `0x0038`,
  `contiguous_free_before_0x4C00=1351 bytes`.
- After T127 canonical rebuild: V3.4 rev `0x0039`,
  `listing_app_end=0x46B2`,
  `contiguous_free_before_0x4C00=1357 bytes`.
- Net reclaim: **+6 bytes** of margin for T127, **+28 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0038 -> 0x0039)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_descriptor_dirty_return_tail_is_shared
# 1 passed in 0.13s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_descriptor_dirty_return_tail_is_shared \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_service_4080_stock096_update_uses_shared_helper \
  tests/sim/test_main_gpsim_usb_engine.py
# 5 passed in 3.77s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_descriptor_tblptr_staging_uses_shared_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_descriptor_dirty_return_tail_is_shared
# 2 passed in 0.03s
```

One intermediate pytest invocation used a stale TBLPTR structural test name and
collected no tests; the valid focused names above were rerun and passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **28/200**, so no new 30-minute exploratory gate is due yet.

## T128 in-range branch inversions — landed 2026-06-16

Scope:

- Collapsed ten local `cond next; bra other; next:` shapes into the inverse
  conditional branch to `other`, allowing the original target to become the
  fall-through path.
- Only candidates whose inverse target was in PIC18 conditional-branch range
  were touched.  The out-of-range candidates stay in the two-branch spelling.
- Affected paths are the HID firmware-update handoff, firmware-update relay,
  UART volume/report/command dispatch, `stage_hid_ep1_in_report_from_selector` reply routing,
  and one `truncate_float32_to_integral_float_in_place` math bound check.

Measured result:

- Before T128: V3.4 rev `0x0039`,
  `contiguous_free_before_0x4C00=1357 bytes`.
- After T128 canonical rebuild: V3.4 rev `0x003A`,
  `listing_app_end=0x469E`,
  `contiguous_free_before_0x4C00=1377 bytes`.
- Net reclaim: **+20 bytes** of margin for T128, **+48 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0039 -> 0x003A)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_in_range_branch_inversions_stay_collapsed
# 1 passed in 0.12s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_in_range_branch_inversions_stay_collapsed \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_uart_route_b0_b1_compare_uses_cumulative_xor \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_channel_config_handlers_share_offset_indexed_mirror_dirty_helper \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_v31_command_matrix.py
# 35 passed in 32.84s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_descriptor_dirty_return_tail_is_shared
# 7 passed in 5.45s
```

One intermediate pytest invocation used a stale cmd-dispatch structural test
name and collected no tests; the valid command/dispatch and USB/HID slices
above were rerun and passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **48/200**, so no new 30-minute exploratory gate is due yet.

## T129 boundary-range cmd03 dispatch branch inversion — landed 2026-06-16

Scope:

- Collapsed the remaining in-range `cmd_dispatch_xor_chain` branch pair:
  `bnz uart_link_parser__dispatch_check_cmd04_status_poll; bra cmd03_subdispatch` is now
  `bz cmd03_subdispatch` with `uart_link_parser__dispatch_check_cmd04_status_poll` as the
  fall-through path.
- The inverse branch target sits on the PIC18 conditional-branch range
  boundary; the canonical gpasm build is the range proof.

Measured result:

- Before T129: V3.4 rev `0x003A`,
  `contiguous_free_before_0x4C00=1377 bytes`.
- After T129 canonical rebuild: V3.4 rev `0x003B`,
  `listing_app_end=0x469C`,
  `contiguous_free_before_0x4C00=1379 bytes`.
- Net reclaim: **+2 bytes** of margin for T129, **+50 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x003A -> 0x003B)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_in_range_branch_inversions_stay_collapsed
# 1 passed in 0.13s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_in_range_branch_inversions_stay_collapsed \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_uart_route_b0_b1_compare_uses_cumulative_xor \
  tests/sim/test_main_gpsim_command_matrix.py \
  tests/sim/test_v31_command_matrix.py
# 34 passed in 32.78s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **50/200**, so no new 30-minute exploratory gate is due yet.

## T130 firmware-update branch trampoline — landed 2026-06-16

Scope:

- Added the local `fw_update_relay__advance_cursor_trampoline` trampoline in the branch-protected
  gap before `fw_update_relay__check_saved_status_addr`.
- Two nearby firmware-update range guards now use inverse conditional branches
  to that local trampoline instead of `cond next; bra fw_update_relay__advance_payload_cursor`.
- The trampoline is not on any fall-through path; `fw_update_relay__check_address_alignment`
  either branches to `fw_update_relay__check_saved_status_addr`, branches to
  `fw_update_relay__forward_payload_byte`, or uses the new explicit trampoline branch.

Measured result:

- Before T130: V3.4 rev `0x003B`,
  `contiguous_free_before_0x4C00=1379 bytes`.
- After T130 canonical rebuild: V3.4 rev `0x003C`,
  `listing_app_end=0x469A`,
  `contiguous_free_before_0x4C00=1381 bytes`.
- Net reclaim: **+2 bytes** of margin for T130, **+52 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x003B -> 0x003C)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_in_range_branch_inversions_stay_collapsed
# 1 passed in 0.12s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_in_range_branch_inversions_stay_collapsed \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_command_matrix.py
# 23 passed in 20.30s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **52/200**, so no new 30-minute exploratory gate is due yet.

## T131 cmd26 other-EEPROM source-kind helper — landed 2026-06-16

Scope:

- Added `filename_stage_other_eep_source` for the duplicated cmd `0x26`
  source-kind selection: active PB2 maps the other EEPROM source to A (`0x01`),
  active PB1 maps it to B (`0x02`).
- Both the initial requested-slot mismatch path and the 16-byte prefix compare
  path now call the helper instead of carrying the same four-instruction
  active-preset selector inline.
- The helper is placed after `cmd26_filename_query_handler__suppress_ack_and_return`; normal query flow
  exits by `goto`, so the helper is only reached by `rcall`.

Measured result:

- Before T131: V3.4 rev `0x003C`,
  `contiguous_free_before_0x4C00=1381 bytes`.
- After T131 canonical rebuild: V3.4 rev `0x003D`,
  `listing_app_end=0x4698`,
  `contiguous_free_before_0x4C00=1383 bytes`.
- Net reclaim: **+2 bytes** of margin for T131, **+54 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x003C -> 0x003D)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_filename_reply_state_machine_keeps_compact_branch_shape
# 1 passed in 0.13s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_filename_reply_state_machine_keeps_compact_branch_shape \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py
# 7 passed in 5.25s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# 1 passed in 4.55s
```

One intermediate pytest invocation used two stale filename/compatibility test
names and collected no tests; the valid focused tests above were rerun and
passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **54/200**, so no new 30-minute exploratory gate is due yet.

## T132 cmd26 source-kind EEPROM-base encoding - landed 2026-06-16

Scope:

- Collapsed the cmd `0x26` other-slot filename source-kind selection to reuse
  the EEPROM-base branch result instead of staging a second active-preset
  discriminator.
- Preserved the public source-kind values: active PB1 asks the other EEPROM
  source as B (`0x02`), active PB2 asks it as A (`0x01`).

Measured result:

- Before T132: V3.4 rev `0x003D`,
  `contiguous_free_before_0x4C00=1383 bytes`.
- After T132 canonical rebuild: V3.4 rev `0x003E`,
  `listing_app_end=0x4690`,
  `contiguous_free_before_0x4C00=1391 bytes`.
- Net reclaim: **+8 bytes** of margin for T132, **+62 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x003D -> 0x003E)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_filename_reply_state_machine_keeps_compact_branch_shape \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **62/200**, so no new 30-minute exploratory gate is due yet.

## T133 firmware-update static hex-byte POSTINC2 helper - landed 2026-06-16

Scope:

- Added a shared firmware-update helper for the repeated "stage one static
  ASCII hex byte at `POSTINC2`" sequence.
- Replaced duplicated literal staging at firmware-update packet assembly sites
  without changing the packet contents or FSR2 progression.

Measured result:

- Before T133: V3.4 rev `0x003E`,
  `contiguous_free_before_0x4C00=1391 bytes`.
- After T133 canonical rebuild: V3.4 rev `0x003F`,
  `listing_app_end=0x4670`,
  `contiguous_free_before_0x4C00=1423 bytes`.
- Net reclaim: **+32 bytes** of margin for T133, **+94 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x003E -> 0x003F)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_firmware_update_static_hex_staging_uses_shared_postinc2_helper \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **94/200**, so no new 30-minute exploratory gate is due yet.

## T134 firmware-update computed sequential hex writer - landed 2026-06-16

Scope:

- Extended the T133 firmware-update byte staging shape to computed sequential
  hex bytes that feed the same `POSTINC2` destination.
- Kept the existing firmware-update response layout and FSR2 byte order.

Measured result:

- Before T134: V3.4 rev `0x003F`,
  `contiguous_free_before_0x4C00=1423 bytes`.
- After T134 canonical rebuild: V3.4 rev `0x0040`,
  `listing_app_end=0x4654`,
  `contiguous_free_before_0x4C00=1451 bytes`.
- Net reclaim: **+28 bytes** of margin for T134, **+122 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x003F -> 0x0040)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_firmware_update_static_hex_staging_uses_shared_postinc2_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_firmware_update_computed_hex_staging_uses_shared_postinc2_helper \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_main_gpsim_usb_engine.py
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **122/200**, so no new 30-minute exploratory gate is due yet.

## T135 tail-call peephole rejected; cmd19 status-bit helper landed - 2026-06-16

Rejected attempt:

- A generic tail-call peephole pass was tried and reverted after review because
  the candidate sites were either status-sensitive or did not have enough local
  proof to justify changing call/return shape.
- The revert left only revision churn and no accepted byte claim.

Accepted scope:

- Factored the repeated cmd `0x19` status-bit fanout into a small shared
  helper.
- Preserved the visible status byte contents and command reply framing.

Measured result:

- Before the accepted T135 slice: V3.4 rev `0x0042`,
  `contiguous_free_before_0x4C00=1451 bytes`.
- After T135 canonical rebuild: V3.4 rev `0x0043`,
  `listing_app_end=0x464A`,
  `contiguous_free_before_0x4C00=1461 bytes`.
- Net reclaim: **+10 bytes** of margin for the accepted T135 slice,
  **+132 bytes** since the last completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0042 -> 0x0043)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_cmd19_status_bit_fanout_uses_shared_helper \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_main_gpsim_command_matrix.py
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **132/200**, so no new 30-minute exploratory gate is due yet.

## T136 logical-vs-computed volume compare helper - landed 2026-06-16

Scope:

- Added a shared 32-bit compare helper for the duplicated logical-volume vs
  computed-volume equality checks.
- Kept the zero/non-zero branch contract local to the existing call sites.

Measured result:

- Before T136: V3.4 rev `0x0043`,
  `contiguous_free_before_0x4C00=1461 bytes`.
- After T136 canonical rebuild: V3.4 rev `0x0044`,
  `listing_app_end=0x463E`,
  `contiguous_free_before_0x4C00=1473 bytes`.
- Net reclaim: **+12 bytes** of margin for T136, **+144 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0043 -> 0x0044)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_volume_logical_computed_compare_uses_shared_32bit_helper \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **144/200**, so no new 30-minute exploratory gate is due yet.

## T137 HID route/cache byte-span compare helper - landed 2026-06-16

Scope:

- Replaced the inline six-channel HID route/cache compare with a shared
  FSR0/FSR1 byte-span compare helper.
- Preserved the existing dirty-flag behavior: the route/config dirty path is
  taken only if any compared byte differs.

Measured result:

- Before T137: V3.4 rev `0x0044`,
  `contiguous_free_before_0x4C00=1473 bytes`.
- After T137 canonical rebuild: V3.4 rev `0x0045`,
  `listing_app_end=0x4626`,
  `contiguous_free_before_0x4C00=1497 bytes`.
- Net reclaim: **+24 bytes** of margin for T137, **+168 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0044 -> 0x0045)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_hid_route_cache_compare_uses_shared_z_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_channel_config_handlers_share_offset_indexed_mirror_dirty_helper \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **168/200**, so no new 30-minute exploratory gate is due yet.

## T138 generic byte-span compare reused for HID filename cache - landed 2026-06-16

Scope:

- Generalized the T137 helper as `compare_fsr0_fsr1_bytes_z`.
- Replaced four repeated filename-cache byte compares between
  `stock_0AC..0AF` and `stock_09B..09E` with a four-byte FSR0/FSR1 compare.
- Kept the existing filename dirty behavior: on any difference, set
  `event_flags.3` and `filename_dirty_flags.3`.

Measured result:

- Before T138: V3.4 rev `0x0045`,
  `contiguous_free_before_0x4C00=1497 bytes`.
- After T138 canonical rebuild: V3.4 rev `0x0046`,
  `listing_app_end=0x4612`,
  `contiguous_free_before_0x4C00=1517 bytes`.
- Net reclaim: **+20 bytes** of margin for T138, **+188 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0045 -> 0x0046)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_hid_route_cache_compare_uses_shared_z_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_filename_compare_and_page1_setup_use_compact_forms \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_channel_config_handlers_share_offset_indexed_mirror_dirty_helper \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# passed
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **188/200**, so no new 30-minute exploratory gate is due yet.

## T139 local peephole batch - landed 2026-06-16

Scope:

- Replaced `movlw 0x7F; andwf length_mask_or_divisor_low_scratch_byte,F` with
  `bcf length_mask_or_divisor_low_scratch_byte,7` in `float32_pack_mantissa_exponent_sign`.
- Removed dead `movlw 0xFF` before `setf addr_low_counter_or_payload_scratch_byte` in
  `boot_init_peripherals_and_enter_adc_gate`.
- Replaced `movlw 0; bsf PLUSW2,7` with `bsf INDF2,7` in
  `usb_ep0_apply_clear_set_feature_request`.
- Replaced the boolean OR/postdecrement staging in `fw_update_signature_status_word_helper`
  with a direct conditional `bsf INDF2,0`.
- Removed dead `movlw 0xFF` before `setf addr_high_table_row_or_checksum_scratch_byte` in
  `usb_disconnect_wait_clear_state`.

Measured result:

- Before T139: V3.4 rev `0x0046`,
  `contiguous_free_before_0x4C00=1517 bytes`.
- After T139 canonical rebuild: V3.4 rev `0x0047`,
  `listing_app_end=0x4604`,
  `contiguous_free_before_0x4C00=1531 bytes`.
- Net reclaim: **+14 bytes** of margin for T139, **+202 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0046 -> 0x0047)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_zero_peepholes_stay_compact_without_status_sensitive_reuse \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_boot_marker_check_accepts_0x77_or_0x88_with_single_eeprom_read \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_fsr2_from_stock072073_is_shared \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_core30d8_keeps_live_exponent_or_without_scratch_zero_fanout \
  tests/sim/test_v33_flash_remap_runtime.py \
  tests/sim/test_dlcp_v34_release_flash.py
# 13 passed
```

Exploratory gate status: T139 brought accepted bytes since the last completed
exploratory gate to **202/200**, so the 30-minute chain exploratory gate was
due before any further firmware edits.

## Exploratory gate after T139 - completed 2026-06-16

Command:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m \
  --status-interval 60 \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/reanalysis/v34_size_t139_exploratory_20260616

PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/reanalysis/v34_size_t139_exploratory_20260616 \
  --out artifacts/reanalysis/v34_size_t139_exploratory_20260616/cards \
  --top 8 --sample 2 --seed 202
```

Run summary:

- Artifact dir:
  `artifacts/reanalysis/v34_size_t139_exploratory_20260616/20260616_161615_de04810f3a0eba5a`
- Seed: `0xde04810f3a0eba5a`.
- Sessions/events/observations: `79 / 9856 / 7491`.
- Campaign mix: `src=9`, `fault-recovery=5`, `standby-reset=13`,
  `saturation=10`, `ui=15`, `preset-phase-sweep=10`, `diag=9`,
  `preset-filename=8`.
- Incidents: one deduplicated LOW incident, `EXP-000001`, signature
  `waiting-connected`; duplicate incident signatures: `97`.

Gate verdict:

- Accepted.  No plausible regression from T137-T139 was found.
- The single deduplicated incident is the already-known CONTROL connection/UI
  state class: CONTROL is connected while showing `Waiting for DLCP` after
  reset/standby stress.
- The incident snapshot does not implicate the recent MAIN byte-saving work:
  both MAINs report reset `X:1`, no diagnostic counter growth, no DSP fault,
  idle preset jobs, zero TAS `0x30` activity while muted/blanked, and no new
  identity or filename corruption.
- Selected cards included a healthy diagnostics identity sample
  `PB2 OK v3.4 0047` and a coherent long filename sample for
  `Name_With_Underscore_123456789`; saturated synthetic fault cards did not
  show persistent volume/input/preset or cross-PB coefficient corruption.

Exploratory gate status: accepted bytes since the last completed exploratory
gate reset to **0/200** after this gate.  The current canonical V3.4 state is
rev `0x0047`, `listing_app_end=0x4604`,
`contiguous_free_before_0x4C00=1531 bytes`; the remaining target gap is
**469 bytes**.

## T140 route-bit refresh loop - landed 2026-06-16

Scope:

- Replaced the six unrolled `event_flags.bit6` route-refresh writes in
  `cmd_dispatch_gated__check_channel_enable_dirty` with a compact loop.
- The loop copies `stock_0A4` into `stock_04C`, rotates out bits 0..5 in
  order, walks the register-byte base in `stock_04B` by `0x28`, and preserves
  the old per-bit selector rule: add `0xEC` before each
  `preset_table_apply_entry_legacy_blocking` call when the corresponding route bit is set.
- Removed the now-unused `i2c_381c_with_w_bank0` helper.  The loop state lives
  in access-bank `stock_04B/04C`, which are not touched by
  `preset_table_apply_entry_legacy_blocking`, its flash-read path, or the I2C timeout recovery
  path.  The next `usb_hid_mailbox_stage_selector5_if_enabled` call reasserts BSR=0, so no
  per-iteration BSR restore is needed.

Measured result:

- Before T140: V3.4 rev `0x0047`,
  `contiguous_free_before_0x4C00=1531 bytes`.
- After T140 canonical rebuild: V3.4 rev `0x0048`,
  `listing_app_end=0x45E2`,
  `contiguous_free_before_0x4C00=1565 bytes`.
- Net reclaim: **+34 bytes** of margin for T140, **+34 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0047 -> 0x0048)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_channel_route_bit_fanout_uses_addlw_selector_shape \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_compatibility.py::test_v173_v34_chain_reaches_volume_and_preset_filename
# 12 passed in 33.05s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **34/200**, so no new 30-minute exploratory gate is due yet.

## T141 firmware-update UART block-send helper - landed 2026-06-16

Scope:

- Added `fw_update_tx_text_block_from_w`, which stages W into `stock_018`,
  clears `stock_019`, then tail-calls `uart_tx_block_from_buffer`.
- Replaced two literal firmware-update block sends (`0x1D` and `0x2F`) and
  one dynamic `format_int16_decimal_ascii_to_w_pointer` result send.
- Removed the dynamic site's temporary `stock_01B` staging; W is passed
  directly into the new helper before the UART block sender is entered.

Measured result:

- Before T141: V3.4 rev `0x0048`,
  `contiguous_free_before_0x4C00=1565 bytes`.
- After T141 canonical rebuild: V3.4 rev `0x0049`,
  `listing_app_end=0x45D4`,
  `contiguous_free_before_0x4C00=1579 bytes`.
- Net reclaim: **+14 bytes** of margin for T141, **+48 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0048 -> 0x0049)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_fw_update_addr77_compare_uses_shared_carry_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_fw_update_stages_005_and_008_with_shared_helper \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd40_app_to_bootloader_flips_mode \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd40_stream_then_cmd41_verify_round_trips_via_flasher_crc \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd41_verify_with_wrong_crc_returns_failure
# 10 passed in 17.25s
```

One intermediate pytest invocation used two stale
`test_v32_flasher_sim_backend_hid.py` test names and collected no tests; the
valid focused tests above were rerun and passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **48/200**, so no new 30-minute exploratory gate is due yet.

## T142 firmware-update RAM-clear length helper - landed 2026-06-16

Scope:

- Added `fw_update_clear_buffer_from_003_len_w`, which stores W into `stock_005` and
  tail-calls `clear_ram_span_from_staged_addr_count`.
- Replaced three firmware-update init clear sites that already staged
  `stock_003` and then loaded the block length literal immediately before
  calling `clear_ram_span_from_staged_addr_count`.
- Kept the cleared address/length pairs unchanged:
  `0xC7/0x0A`, `0x9A/0x2D`, and `0xD1/0x08`.

Measured result:

- Before T142: V3.4 rev `0x0049`,
  `contiguous_free_before_0x4C00=1579 bytes`.
- After T142 canonical rebuild: V3.4 rev `0x004A`,
  `listing_app_end=0x45CE`,
  `contiguous_free_before_0x4C00=1585 bytes`.
- Net reclaim: **+6 bytes** of margin for T142, **+54 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x0049 -> 0x004A)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_fw_update_stages_005_and_008_with_shared_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_fw_update_addr77_compare_uses_shared_carry_helper \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd40_app_to_bootloader_flips_mode \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd40_stream_then_cmd41_verify_round_trips_via_flasher_crc \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd41_verify_with_wrong_crc_returns_failure
# 10 passed in 17.95s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **54/200**, so no new 30-minute exploratory gate is due yet.

## T143 HID cmd44 counted snapshot copier - landed 2026-06-16

Scope:

- Added `hid_diag_copy_count_w`, a small counted POSTINC0-to-POSTINC2 copier
  using `stock_04C` as the loop counter.
- Replaced the three HID `cmd 0x44` diagnostic snapshot sentinel loops with
  explicit counts: 7 runtime counters, 4 reset-cause flags, and 5 V3.4
  SRC/DSP forensic counters.
- Preserved the user-visible response layout exactly: legacy cells remain at
  offsets `[3..13]`, and V3.4 SRC/DSP cells remain appended at `[14..18]`.

Measured result:

- Before T143: V3.4 rev `0x004A`,
  `contiguous_free_before_0x4C00=1585 bytes`.
- After T143 canonical rebuild: V3.4 rev `0x004B`,
  `listing_app_end=0x45C8`,
  `contiguous_free_before_0x4C00=1591 bytes`.
- Net reclaim: **+6 bytes** of margin for T143, **+60 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x004A -> 0x004B)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_diag_src_counters.py::test_cmd44_source_uses_counted_copy_helper \
  tests/sim/test_v34_diag_src_counters.py::test_cmd44_extended_payload_reflects_cells \
  tests/sim/test_v32_flasher_sim_backend_hid.py
# 21 passed in 109.92s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **60/200**, so no new 30-minute exploratory gate is due yet.

## T144 cold-init POSTINC0 clear helper - landed 2026-06-16

Scope:

- Added `clear_postinc0_count_w`, which clears W bytes through `POSTINC0` and
  returns with the same zero-WREG exit state as the old inline loops.
- Replaced the four broad cold-init RAM wipe loops plus the two V3.4 upper-bank
  runtime/SRC diagnostic clears with local `rcall`s.
- Preserved all clear ranges:
  `0x300/0xC0`, `0x200/0xDE`, `0x100/0xE5`, `0x060/0x8D`,
  `preset_job_state_b2/0x22`, and `diag_src_n/0x05`.

Measured result:

- Before T144: V3.4 rev `0x004B`,
  `contiguous_free_before_0x4C00=1591 bytes`.
- After T144 canonical rebuild: V3.4 rev `0x004C`,
  `listing_app_end=0x45B8`,
  `contiguous_free_before_0x4C00=1607 bytes`.
- Net reclaim: **+16 bytes** of margin for T144, **+76 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x004B -> 0x004C)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_cold_init_clears_all_upper_bank_runtime_lifecycle_cells \
  tests/sim/test_v32_layer5_diag_counters.py::test_v32_source_cold_init_classifies_reset_cause \
  tests/sim/test_v34_diag_src_counters.py::test_boot_baseline_counts_cold_walk_and_first_route \
  tests/sim/test_v34_diag_src_counters.py::test_cmd44_extended_payload_reflects_cells
# 4 passed in 6.41s
```

One intermediate pytest invocation used stale test names and collected no
tests; the valid focused tests above were rerun and passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **76/200**, so no new 30-minute exploratory gate is due yet.

## T145 version-response literal peephole + direct tails - landed 2026-06-16

Scope:

- Removed the duplicate `movlw 0x03` in the `stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup`
  V3.4 status/version response. The label entry still sets W to `0x03`
  before storing `stock_15B`, so `stock_15C` can reuse that W value.
- Converted several terminal `call`/`rcall` spellings to direct
  `goto`/`bra` tails where the callee return should return to the original
  caller. These are behavior-preserving but, because the shared return labels
  remain for skipped/alternate paths, they did not materially change the
  measured app end.
- Rejected the other duplicate-literal scan hits because they are public label
  entries or builder-owned V3.4 identity nibbles.

Measured result:

- Before T145: V3.4 rev `0x004C`,
  `contiguous_free_before_0x4C00=1607 bytes`.
- After T145 canonical rebuild: V3.4 rev `0x004D`,
  `listing_app_end=0x45B6`,
  `contiguous_free_before_0x4C00=1609 bytes`.
- Net reclaim: **+2 bytes** of margin for T145, **+78 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x004C -> 0x004D)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_unconditional_call_return_tails_are_direct_branches \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_dead_w_zero_tests_use_tstfsz_skip_shape \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_field6_lifecycle_reassert_uses_validated_writer_and_route_drain \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_trim_mirrors_and_core_3398_use_chain_copy_stage_runs \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_core_3e0a_and_eeprom_writeback_use_chain_copy_stage_runs
# 5 passed in 0.15s
```

One intermediate pytest invocation used a stale EEPROM test name and collected
no tests; the valid focused tests above were rerun and passed.

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **78/200**, so no new 30-minute exploratory gate is due yet.

## T146 return-value `retlw` peepholes - landed 2026-06-16

Scope:

- Replaced two unconditional `movlw K` / `return` value tails with `retlw K`:
  `usb_ep0_prepare_in_data_copy_pointers` returns `0x07`, and
  `signed_hi_bias80_compare_prelude` returns `0x00`.
- Rejected the similar-looking `cmd03_stage_mute_refresh_w` site because it is
  behind a skip instruction; replacing only the skipped `movlw 0x01` would
  remove the return from the zero path.

Measured result:

- Before T146: V3.4 rev `0x004D`,
  `contiguous_free_before_0x4C00=1609 bytes`.
- After T146 canonical rebuild: V3.4 rev `0x004E`,
  `listing_app_end=0x45B2`,
  `contiguous_free_before_0x4C00=1613 bytes`.
- Net reclaim: **+4 bytes** of margin for T146, **+82 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x004D -> 0x004E)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_descriptor_tblptr_staging_uses_shared_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_return_value_tails_use_retlw \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_i2c_service_39a6_uses_chain_copy_for_four_byte_stage_runs
# 3 passed in 0.13s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **82/200**, so no new 30-minute exploratory gate is due yet.

## T147 generic POSTINC copy helper reuse - landed 2026-06-16

Scope:

- Renamed the HID cmd `0x44` counted copier to
  `hid_diag_snapshot_copy_block_count_w`, keeping the existing
  `POSTINC0 -> POSTINC2` count-in-W contract and `diff_count_update_compare_or_route_mask_scratch_byte` loop counter.
- Reused that helper in `usb_ep0_arm_out_pingpong_bd` for the fixed
  `stock_116..stock_119 -> FSR2` staging run.  The destination pointer setup,
  trailing `FSR2L -= 4`, and endpoint flag-bit set are unchanged.
- An initial `rcall` from `usb_ep0_arm_out_pingpong_bd` was rejected by gpasm as out
  of range (`1764` words, outside `-1024..1023`); the accepted form uses a far
  `call`, still reclaiming three instruction words versus the four inline
  `movff` copies.

Measured result:

- Before T147: V3.4 rev `0x004E`,
  `contiguous_free_before_0x4C00=1613 bytes`.
- After T147 canonical rebuild: V3.4 rev `0x004F`,
  `listing_app_end=0x45AC`,
  `contiguous_free_before_0x4C00=1619 bytes`.
- Net reclaim: **+6 bytes** of margin for T147, **+88 bytes** since the last
  completed exploratory gate.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (release rev 0x004E -> 0x004F)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_diag_src_counters.py::test_cmd44_source_uses_counted_copy_helper \
  tests/sim/test_v34_diag_src_counters.py::test_cmd44_extended_payload_reflects_cells \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_usb_service_4080_stock096_update_uses_shared_helper \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_core_3e0a_and_eeprom_writeback_use_chain_copy_stage_runs
# 4 passed in 6.55s
```

Exploratory gate status: accepted bytes since the last completed exploratory
gate are **88/200**, so no new 30-minute exploratory gate is due yet.

Changed files in this acceptance set:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `src/dlcp_fw/asm/ram_bank_manifest.py`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/patch/build_v34_release.py`
- `tests/sim/test_v33_flash_remap_runtime.py`
- `tests/sim/test_firmware_version_label.py`
- `tests/sim/test_v172_v33_diag_identity.py`
- `tests/sim/test_v34_v173_i2c_recovery_contract.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_v34_v173_release_builders.py`
- `docs/V34_SIZE_OPTIMIZATION_FINDINGS.md`
- `docs/HARDWARE_TEST.md`
- `docs/IMPL_V171_V32_BUG_LEDGER.md`
- `docs/IMPL_REFACTORING_V34_V173.md`
- `docs/IMPL_V34_FIELD_BUGS_20260610.md`
- `docs/REFACTORING_V34_V173_SPEC.md`

Behavior-preservation proof:

- The cold-init table is pinned by
  `test_v34_src4382_cold_init_table_preserves_exact_ordered_writes`.
- The standby rail-drop table is pinned by
  `test_v34_standby_shutdown_secondary_write_table_preserves_rail_drop_order`.
- The executable walker label deliberately does **not** end in `_table`; the
  RAM-safety CFG treats `_table` labels as data anchors.
- The walker avoids TOS/return-address tricks and uses `TBLPTR` plus
  `flash_end_high_or_loop_mask_scratch_byte` as a local access-bank loop counter.  `flash_end_high_or_loop_mask_scratch_byte` is
  scratch at both call sites and is not clobbered by `i2c_secondary_dev_write`
  or its timeout/NACK recovery paths.  An FSR0-backed counter was rejected
  during implementation because the diagnostic timeout path uses FSR0.
- `TBLPTRU` is cleared inside the walker before the first `tblrd*+`, so callers
  only stage `TBLPTRL/H` and row count.

Historical rev-`0xFF` validation before the 16-bit policy:

```bash
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
raise SystemExit(1 if findings else 0)
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --fix-aliases
# control-v172: alias block already current
# control-v173: alias block already current
# main-v33: alias block updated
# main-v34: alias block already current
# RAM bank safety: OK (control-v172, control-v173, main-v33, main-v34)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_v172_v33_release_builders.py::test_build_v33_release_bumps_runtime_and_identity_revision_literals \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_newly_reachable_far_helpers_use_rcall_only_where_in_range
# 20 passed in 0.95s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -n 16 -q tests
# 1691 passed, 20 skipped, 3 xfailed, 7 warnings in 616.26s
```

The first full rev-`0xFF` run failed on generated/test-contract drift, not
firmware behavior: the shared `dlcp_main_ram.inc` alias block was exact-rendered
per target even though V3.3 and V3.4 share the include, and one V3.4 structural
test still expected the pre-T74 far `call` to `diag_inc_sat_fsr0`.  The accepted
fix renders generated aliases as the union of targets sharing an include,
regenerates the main alias block, and updates the structural assertion to the
accepted `rcall`.

The historical T77 canonical firmware build was `0xFE -> 0xFF`.  The current
canonical V3.4 firmware was rebuilt after the 16-bit policy change as rev
`0x0001`.

Post-FIELD-10 release evidence is tracked in
`docs/V34_FIELD_BUGS_20260610.md`:

```text
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# EEPROM rev 0xAB -> 0xAC
# V3.4 app_end=0x4BF2, last_used_pre_preset_b=0x4BF1
# contiguous_free_before_0x4C00=14 bytes, free_object_words=7
# erased_holes_before_0x4C00=160 bytes

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
# 1655 passed, 2 skipped, 3 xfailed, 7 warnings
```

Parked/rejected follow-up levers for this wave:

- The additional `movlw/movwf` init runs around source lines 5334/6043/9845
  were not touched by T1/T2/T3/T4/T5/T6/T7/T8/T9/T10/T11/T12/T13/T14/T15/T16/T17/T18/T19/T20/T22/T23/T24/T25 because they need a different RAM/SFR table writer.
  A 2026-06-15 arithmetic pass rejected the 5334 POR SFR-init table rewrite:
  the current init block is 29 words before `boot_config_marker_valid_b0`, while a simple
  TBLPTR/FSR0 indirect writer is about 36 words whether the zero writes stay
  inline or join the table.
- The 6043-adjacent sequential RAM fill is also rejected for this wave: the
  current `movlw`/`movwf` plus `movlb`/`retlw` shape is 16 words, while an
  `lfsr FSR0, tas3108_sync_stage0_reg_addr_phys` plus `addlw`/`POSTINC0` version is 17 words.
- XOR dispatch ladders remain rejected: likely break-even on PIC18 and higher
  behavioral risk.
- New descriptor rewrites remain rejected for this wave because the existing
  chain-copy interrupt-safety proof is still explicitly xfailed.  T121/T122
  accepted only local low/mid `goto chain_copy` trampolines so nearby callers
  can use `rcall`; those wrappers do not introduce new descriptor streams and
  are pinned structurally.
- Feature demotion remains off the table.

## Root causes found on the way (all fixed)

1. **Rust core TOS write-through gap** (`crates/dlcp-sim`): `movwf` to
   TOSL/TOSH/TOSU updated only the memory mirror; `return` popped the
   stale internal stack entry.  Real silicon honors TOS writes
   (DS39632E §5.1.2.1).  This made chain_copy's TOS-fixup return appear
   to jump back into the descriptor — and because PIC18 second
   instruction words decode as NOP, most descriptors executed as benign
   garbage ("boots fine"), while one site's bytes formed a CALL opcode
   and ran away (PcOutOfBounds at ~13.7 M Tcy).  The session-0 ledger
   blamed PROD liveness at the 19e6 volume chain — **that theory was
   wrong**; with the core fixed, the same conversion set is clean.
   Fix: staged TOS write applied to the call-stack array post-step
   (`tos_sw_write_pending`), pinning test
   `movwf_tos_write_through_patches_computed_return`.
2. **`inject_main_frames_fifo` ISR race** (sim facade): the injector
   wrote MAIN0's RX ring + wr index while the firmware's RX ISR was
   mid-enqueue holding the OLD wr in W (GIEH=0, RCIF=1 at the failing
   tick).  The ISR then overwrote the injected route byte at the stale
   index (B0 -> B1: broadcast became addressed; the PB1->PB2 forward
   silently disappeared) and left a phantom stale cell in the stream.
   Impossible on real hardware (CONTROL's bytes serialize through the
   same UART).  Fix: the facade defers injection (bounded) until
   GIEH=1 and RCIF=0.  Any phase-sensitive chain test could have hit
   this after ANY firmware change.
3. **gpasm pads every `db` directive to word alignment** (PIC18
   absolute mode).  Multi-line descriptors with odd-length rows gain
   phantom 0x00 bytes that desynchronize a stream parser (here: cnt=0
   was read, decfsz wrapped, 256-byte wild copy sprayed RAM and killed
   boot).  Emit descriptor streams as a SINGLE `db` with even total
   length.

## Lessons that bind any retry

1. Every converted chain needs per-site liveness proofs for W, STATUS,
   FSR0, TBLPTR (and BSR once the helper banks): the static RAM checker
   models movlb effects through calls, but audit anyway.
2. Boot-test with `step_tcy` (12 MHz instruction clock), NOT
   `step_ticks` (48 MHz universal clock); a 60 M-tick "boot OK" covers
   only 0.31 s.
3. `step_until_pc_hit(idx, lo, hi, 0)` is a pure PC read
   (checks-before-stepping); chunked stepping misses brief windows.
4. Descriptor-after-call designs need: a TOS write-through pinning test
   in `crates/dlcp-sim`, a >= 120 M-Tcy boot soak, and listing-level
   byte verification of at least one descriptor per emission shape.
5. When a converted build fails a timing-sensitive chain test, prove
   the frame actually reached the wire (`uart_tx_records_full` /
   `uart_rx_records_full`) before blaming the firmware: both sim-side
   root causes above produced "firmware-looking" symptoms.

## Wall facts

- `TABLE_SIZE = 0x0A00` per preset: the bake blankets `0x4C00..0x55FF`
  and `0x5600..0x5FFF` wholesale — no hidden executable flash in or
  between the capture regions; `0x4C00` is a hard wall.
- PIC18F2455 flash ends at `0x5FFF`; both capture banks are spoken for.

## Remaining (unspent) candidate inventory

| Candidate | Est. | Notes |
| --- | --- | --- |
| POR SFR-init walker around source line 5334 | reject for now | Arithmetic pass says a simple table writer grows from 29 to ~36 words. Only revisit if it can absorb additional adjacent setup without extra scratch or return tricks. |
| Sequential RAM fill around source line 6043 | reject for now | Arithmetic pass says the FSR0/`POSTINC0` form is 17 words versus the current 16. |
| cmd25 identity staging around source line 9845 | reject for now | Builder/release ceremony patches identity literals by matching inline bytes; tabling them risks breaking revision stamping unless the builder is redesigned. |
| Per-route trim-ladder table rewrite (`cmd_dispatch_gated__select_applied_route_trim`) | ~+20 B | touches the rev-0x87 SAFETY selector + an empirically load-bearing clrf; do not attempt casually |
| Feature demotion: RA1 edge counter (`diag_p`, sim-only) | ~+20-30 B | needs a ledger entry + test retirement + user sign-off |
| Hand passes over the top functions (32f8/adc_boot_gate__start_dsp_cold_init/2bb8/2328/38a2/19e6/39a6) | 10-20 % each | the proven road if more is ever needed |

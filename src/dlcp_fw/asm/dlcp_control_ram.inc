; DLCP CONTROL V1.7/V1.71 RAM variable definitions (PIC18F25K20)
; Seeded from the RAM layout section of firmware/disasm/control/v16b.asm.
;
; gpdasm emits access-bank GPR references as ``(Common_RAM + N), A``, where
; ``Common_RAM`` is the zero-origin bank-0 GPR base.  The equates below are
; optional pretty-names used by the _comments.asm source and the V1.71
; rewrite; the byte-identical V1.7 first-pass output still resolves through
; ``Common_RAM + N``.

Common_RAM                 equ  0x000000

; --- Named RAM variables (from v16b.asm RAM-layout block) ---
ir_decoded_cmd             equ  0x01D    ; RC5 cmd byte (from ir_rc5_decode)
ir_decoded_addr            equ  0x01E    ; RC5 addr byte
control_flags              equ  0x01F    ; bit0=ir_armed bit1=connected bit2=rx_route_seen
                                         ; bit3=event_exit bit4=display_refresh_pending (V1.6b)
                                         ; bit5=mute_state (V1.6b) bit6=preset_b_active (V1.61b+)
tx_data_staging            equ  0x027    ; byte to enqueue via tx_byte_enqueue
rx_parsed_cmd              equ  0x02F    ; latched by rx_parser_entry
rx_parsed_data             equ  0x030    ; latched by rx_parser_entry
tx_ring_base               equ  0x036    ; 48-byte TX ring (ISR consumer side)
rx_ring_base               equ  0x066    ; 48-byte RX ring (ISR producer side)
tx_ring_rd                 equ  0x096    ; ISR consumer index
tx_ring_wr                 equ  0x097    ; producer index
rx_ring_rd                 equ  0x098    ; parser consumer index
rx_ring_wr                 equ  0x099    ; ISR producer index
idle_timeout_lo            equ  0x09D    ; 16-bit idle timer lo, init 0xEA61
idle_timeout_hi            equ  0x09E    ; 16-bit idle timer hi
full_sync_lo               equ  0x09F    ; 16-bit full-sync counter lo, init 0x4E20
full_sync_hi               equ  0x0A0    ; 16-bit full-sync counter hi
raw_status_cache           equ  0x0A1    ; boot sentinel #4, init 0x80 until BF/05
rx_frame_position          equ  0x0A6    ; parser state: 0=route, 1=cmd, 2=data
cmd1d_setting_cache        equ  0x0A7    ; boot sentinel #3, init 0x80 until BF/1D
rx_ring_staging            equ  0x0B7    ; single-byte holding cell for parser
input_select_cache         equ  0x0B8    ; boot sentinel #1, init 0x80 until BF/06
volume_cache               equ  0x0B9    ; boot sentinel #2, init 0x80 until BF/07
button_debounce_counter    equ  0x0BB    ; threshold = 4
button_last_scan           equ  0x0BC    ; raw button sample
button_debounced           equ  0x0BE    ; debounced state
display_state_index        equ  0x0BF    ; menu screen 0..3 (Vol/Preset/Input/Setup)
saved_settings_base        equ  0x0C1    ; loaded by eeprom_settings_load (0x0C1..0x0CC)

; --- V1.71 additions ---
; V1.71 inlines the features from V1.61b (presets), V1.62b (reconnect
; robustness), V1.63b (BF/08 fault handler), and V1.64b (IR endpoints).
; These equates are inert for the byte-identical V1.7 source (their
; values never appear as references there); V1.71 activates them.
;
; Flag bits on ``control_flags`` (0x01F):
;   bit 0  IR_ARMED             stock
;   bit 1  CONNECTED            stock (display vs WAITING)
;   bit 2  STANDBY_BUS          stock
;   bit 3  RECONNECT_PENDING    V1.62b
;   bit 4  RECONNECT_PRIMED     V1.62b / also display_refresh_pending (V1.6b)
;   bit 5  RECONNECT_WAIT_DONE  V1.62b / also mute_state (V1.6b)
;   bit 6  PRESET_BIT           V1.61b (0 = preset A, 1 = preset B)
;   bit 7  DSP_FAULT_BIT        V1.63b (sticky DSP fault)
;
; Stock V1.6b uses bits 4 and 5 for ``display_refresh_pending`` and
; ``mute_state``; V1.71 either preserves those semantics or migrates
; them to adjacent flag bits — the IMPL spec documents the exact
; mapping.  Bit names below are the V1.71 canonical labels.

IR_ARMED                   equ  0x00
CONNECTED                  equ  0x01
STANDBY_BUS                equ  0x02
RECONNECT_PENDING          equ  0x03
RECONNECT_PRIMED           equ  0x04    ; stock V1.6b: display_refresh_pending
RECONNECT_WAIT_DONE        equ  0x05    ; stock V1.6b: mute_state
PRESET_BIT                 equ  0x06
DSP_FAULT_BIT              equ  0x07

; V1.71 scratch/storage cells (BF/08 fault handler + wake-frame emitter).
; Addresses chosen from free GPR slots per the IMPL spec audit; see
; docs/V16B_SOURCE_REWRITE_SPEC.md §Runtime state for the full map.
;
; The V1.63b binary overlay didn't actually store a fault byte — it
; only touched ``control_flags.DSP_FAULT_BIT``.  V1.71 adds the fault
; byte store as a new V1.71 feature (spec §V1.63b row on fault byte).
; A survey of free GPR slots in the V1.6b code finds 0x0AB safe:
; no direct ``movwf 0x0ab`` / ``movf 0x0ab`` in the stock disasm, and
; no ``lfsr`` pointing into 0x0A8..0x0AF.  Using 0x0CD instead would
; collide with the ``lfsr 0x0, 0x0cd`` / ``clrf POSTINC0`` pattern
; used by a settings-clear routine; 0x0BC collides with the button-
; scan write cycle.  0x0AB is the cleanest choice in the gap between
; ``cmd1d_setting_cache`` (0xA7) and ``rx_ring_staging`` (0xB7).
bf08_fault_byte            equ  0x0AB   ; unreferenced in stock V1.6b

; --- V1.71 WAITING-loop operator-recovery grace counter (2026-04-21) ---
; Saturating counter used by the WAITING-FOR-DLCP loops (cold-boot at
; asm:4448 and reconnect at asm:4716) to impose a grace period before
; enabling the RIGHT/LEFT button -> soft reset escape hatch.  Without
; the grace period, a spurious debounced button press during normal
; MAIN warmup (which can take a few seconds before MAIN's
; send_status_burst arrives) would cause an accidental CONTROL reset.
;
; Counter is cleared to 0 on each entry to a WAITING loop, incremented
; once per iteration, and saturated at V171_WAITING_GRACE_THRESHOLD.
; Reset-on-button fires only once the counter reaches the threshold.
; Slot chosen from the 0x0A8..0x0AA gap (no absolute references in the
; V1.71 source; no lfsr lands in this range).
v171_waiting_grace_count   equ  0x0A8

; Each WAITING-loop iteration is roughly display_loop_iteration +
; poll_frame_send + delay_short(0xC8) + rx_parser_entry, dominated by
; the 0xC8 delay_short (~200 ms wall clock on the K20 control loop).
; Threshold 0x32 (=50) gives ~10 s grace before the reset escape is
; armed.  Saturating comparator uses cpfseq, so threshold must fit in
; 1 byte and not equal 0 (otherwise cold entry would allow reset
; immediately).  Count is an 8-bit cell: pick a threshold that
; comfortably clears the POR->first-BF/05 window (~3-5 s observed on
; V3.2 MAIN) with margin.
V171_WAITING_GRACE_THRESHOLD equ 0x32

; RC5 codes that V1.71 dispatches (documented here for cross-reference
; with the annotator and ir_dispatch edits).
RC5_POWER_TOGGLE           equ  0x32
RC5_PRESET_A               equ  0x38
RC5_PRESET_B               equ  0x39
RC5_STANDBY_ENTER          equ  0x3A    ; V1.64b explicit standby
RC5_WAKE                   equ  0x3B    ; V1.64b explicit wake

; EEPROM slot for V1.71 preset-state byte.  V1.61b binary overlay
; pinned address 0x74; V1.71 preserves it so EEPROM images remain
; interchangeable between the overlay and the source build.
EEPROM_PRESET_STATE_ADDR   equ  0x74

; --- V1.71 Layer 2: one-frame-per-call full-sync state machine ---
; Replaces the V1.6b back-to-back 5-frame burst at full_sync_burst with
; a state machine that emits one frame per main-loop trigger.  Spreads
; chain traffic across multiple iterations so the 31,250-baud link
; never saturates, and makes preset value-bearing alongside volume /
; input / mute / cmd1d_setting / standby_wake (BUG C7 fix).
;
; v171_full_sync_step — REPURPOSES the V1.61b preset retry counter
;   slot.  Lives in BANK 1 at offset 0x70 (physical address 0x170);
;   the EQU value below is the BANKED-form 8-bit operand; full_sync_burst
;   sets BSR=1 before manipulating it.  gpsim CLI reads via the
;   physical address: `reg(0x170)`, NOT `reg(0x070)` (which would
;   read the bank-0 GPR slot of the same offset).
;
;   Encoding (1..6, wraps 6→1):
;     1 = volume_frame_send due
;     2 = input_frame_send due
;     3 = mute_frame_send due
;     4 = cmd1d_setting_frame_send due
;     5 = standby_wake_broadcast due
;     6 = preset frame due (v171_send_preset_frame_txonly, no EEPROM)
;   Initial value is 0 (uninitialized RAM); first call increments to 1
;   and emits volume.  No "idle" state — full_sync_burst always emits
;   the next frame on every trigger.
v171_full_sync_step        equ  0x070
;
; Note: 0x071 (V1.61b "preset primed flag") and the V1.61b preset
; retry mechanism it gated are now DEAD.  Layer 2 makes preset
; value-bearing in the periodic broadcast, so the event-driven retry
; queue is no longer needed.  The slot is intentionally left
; un-defined here so any stray reference produces an assembler error
; rather than silently picking up new semantics.

; --- V1.71 Layer 1: bounded tx_byte_enqueue ---
; Replaces the V1.6b indefinite busy-wait at tx_byte_enqueue when the
; producer would collide with the ISR consumer (BUG C6).  The bounded
; form gives the TX ISR a fixed budget of poll iterations to advance
; tx_ring_rd; if it fails to do so, the byte is dropped (NOT committed
; to tx_ring_wr), v171_tx_saturate_count is bumped (saturating at
; 0xFF), and tx_byte_enqueue returns C=1 so callers can react.
;
; v171_tx_enq_retry — ACCESS-bank scratch byte used only inside the
;   bounded retry loop.  Caller must not depend on its value across
;   the call.  Address chosen as the only free slot in the v1.71
;   0x028..0x02F scratch range (0x028..0x02C and 0x02E..0x02F are
;   live; 0x02D has no live reference).
v171_tx_enq_retry          equ  0x02D
;
; v171_tx_saturate_count — saturating counter of tx-ring-full events.
;   Lives in BANK 1 at offset 0xAD (physical address 0x1AD); the EQU
;   value below is the BANKED-form 8-bit operand; tx_byte_enqueue
;   sets BSR=1 before incrementing.  gpsim CLI reads via the physical
;   address: `reg(0x1AD)`, NOT `reg(0x0AD)` (which would read the
;   bank-0 GPR slot of the same offset).  Reset only on POR/BOR or
;   explicit clear; preserved across ordinary firmware reset.
;   Surfaced via the future Layer 5 diagnostics page if added to the
;   cmd 0x21 reply table.
v171_tx_saturate_count     equ  0x0AD

; --- V1.71 Layer 5 Phase B + V1.71 Tier-1 Phase 3: CONTROL diagnostics ---
; Per-PB cache of the diagnostic reply payloads from V3.2 rev 0x37 MAIN.
; Layer 5 baseline = 7 runtime counters per PB (BF/21..BF/27 from cmd 0x21).
; V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) extends each PB cache
; from 7 cells to 11 cells by adding 4 reset-cause flag cells (O V W X)
; populated by the new chain `cmd 0x22` 4-frame reply burst (BF/28..BF/2B).
; Each payload byte carries one cell in the LOW nibble (high nibble = 0).
; An earlier draft packed two counters per byte but produced data >= 0x80
; for any high counter > 7, which the chain forwarder treats as a route
; byte (corrupting PB2's reply specifically -- PB1's reply path is direct).
;
; Cache ordering matches the BF/2N replies:
;   *_i           = diag_i           (BF/21) -- I2C transport faults
;   *_d           = diag_d           (BF/22) -- DSP fault episodes
;   *_s           = diag_s           (BF/23) -- standby dispatches
;   *_b           = diag_b           (BF/24) -- bring-up dispatches
;   *_r           = diag_r           (BF/25) -- recovery branch entries
;   *_a           = diag_a           (BF/26) -- AN0-triggered standby
;   *_p           = diag_p           (BF/27) -- RA1 edge events (RUNTIME LAST FRAME)
;   *_reset_por   = diag_reset_por   (BF/28) -- POR (V3.2 rev 0x37 Tier-1)
;   *_reset_bor   = diag_reset_bor   (BF/29) -- BOR (Brown-Out)
;   *_reset_wdt   = diag_reset_wdt   (BF/2A) -- WDT timeout
;   *_reset_sw    = diag_reset_sw    (BF/2B) -- software reset (RESET LAST FRAME)
;
; All cache slots live in BANK 1.  The EQU values are BANKED-form 8-bit
; operands; callers must `movlb 0x01` before access.  gpsim CLI reads via
; the PHYSICAL address -- e.g. `reg(0x180)` not `reg(0x080)` (which would
; be the bank-0 GPR slot).
;
; Cache survives ordinary firmware reset / reconnect (uninitialized RAM
; keeps its value through soft reset on PIC18); cleared only on POR/BOR,
; the same gate as the MAIN-side diag block.
;
; CRITICAL: the V1.71 Tier-1 layout SHIFTED all cells up by 4 bytes per
; PB (and reorganized the trailing state cells).  Old code that hardcoded
; the legacy cell offsets (0x080..0x094) MUST be updated to use these
; equates.  The spec at V32_DIAG_TIER1_SPEC.md §"CONTROL diag cache
; layout (V1.71)" is the authoritative source for this layout.
v171_diag_pb1_i            equ  0x080  ; physical 0x180
v171_diag_pb1_d            equ  0x081
v171_diag_pb1_s            equ  0x082
v171_diag_pb1_b            equ  0x083
v171_diag_pb1_r            equ  0x084
v171_diag_pb1_a            equ  0x085
v171_diag_pb1_p            equ  0x086
v171_diag_pb1_reset_por    equ  0x087  ; Tier-1: POR flag
v171_diag_pb1_reset_bor    equ  0x088  ; Tier-1: BOR flag
v171_diag_pb1_reset_wdt    equ  0x089  ; Tier-1: WDT flag
v171_diag_pb1_reset_sw     equ  0x08A  ; Tier-1: SW-reset flag
v171_diag_pb2_i            equ  0x08B
v171_diag_pb2_d            equ  0x08C
v171_diag_pb2_s            equ  0x08D
v171_diag_pb2_b            equ  0x08E
v171_diag_pb2_r            equ  0x08F
v171_diag_pb2_a            equ  0x090
v171_diag_pb2_p            equ  0x091
v171_diag_pb2_reset_por    equ  0x092  ; Tier-1
v171_diag_pb2_reset_bor    equ  0x093  ; Tier-1
v171_diag_pb2_reset_wdt    equ  0x094  ; Tier-1
v171_diag_pb2_reset_sw     equ  0x095  ; Tier-1

; Poll-state cells (also BANK 1):
;   v171_diag_target       = 0 -> query PB1 next, 1 -> query PB2 next
;   v171_diag_present      = bit0 set when PB1 has ever replied,
;                            bit1 set when PB2 has ever replied
;                            (used to render "n/a" for never-seen PBs)
;   v171_diag_poll_lo/hi   = 16-bit countdown until the next query.
;                            Decremented once per v171_diag_screen tick.
;                            Reset to V171_DIAG_POLL_RELOAD on each query.
v171_diag_target           equ  0x096  ; physical 0x196
v171_diag_present          equ  0x097
v171_diag_poll_lo          equ  0x098
v171_diag_poll_hi          equ  0x099
; Snapshot of v171_diag_present at the last screen draw -- used by
; v171_diag_check_redraw to fire a screen redraw only when the
; present mask actually changed.  Lives in BANK 1 (not in the
; access-bank ram_0x005 scratch cell that other routines clobber).
v171_diag_present_snap     equ  0x09A
; LCD pad-loop counter for the n/a render path.  Must NOT live in
; access-bank ram_0x004 because lcd_char_write's internal helper
; routines clobber it (movff FSR0H, ram_0x004 in
; control_core_service_*).  Callers that use this cell must
; movlb 0x01 around access AND reload BSR after every
; lcd_char_write call (which can change BSR internally).
v171_diag_lcd_pad_count    equ  0x09B
; Bit-flag byte for the diagnostics page state machine:
;   bit 0  V171_DIAG_FLAG_DIRTY            cache changed since last redraw
;                                          (set by any cache write;
;                                          cleared by check_redraw)
;   bit 1  V171_DIAG_FLAG_RUNTIME_PENDING  cmd 0x21 in flight, awaiting BF/27
;                                          (set when cadence fires cmd 0x21;
;                                          cleared by the parser case on
;                                          BF/27 reception).  If still set
;                                          on the next cadence expiry,
;                                          target advances anyway so a
;                                          silent or unsupported PB can't
;                                          pin the poll target forever.
;   bit 2  V171_DIAG_FLAG_RESET_PENDING    Tier-1: cmd 0x22 in flight,
;                                          awaiting BF/2B (set when the
;                                          page-entry hook fires cmd 0x22;
;                                          cleared by the parser case on
;                                          BF/2B reception).  Distinct
;                                          from RUNTIME_PENDING so the
;                                          two queries can be in flight
;                                          to different PBs concurrently.
v171_diag_flags            equ  0x09C
V171_DIAG_FLAG_DIRTY            equ  0x00
V171_DIAG_FLAG_RUNTIME_PENDING  equ  0x01
V171_DIAG_FLAG_RESET_PENDING    equ  0x02
; Backward-compatibility alias.  Pre-Tier-1 code referenced
; V171_DIAG_FLAG_PENDING; the new name is V171_DIAG_FLAG_RUNTIME_PENDING.
; Keep the old name pointing at the same bit so a refactor that misses
; one call site doesn't silently shift bit assignments.
V171_DIAG_FLAG_PENDING          equ  V171_DIAG_FLAG_RUNTIME_PENDING

; Per-PB bitmask of "reset-cause cache is fresh OR query gave up".
;   bit 0 set: PB1 reset cells were populated since the last Diag-page
;              entry (cmd 0x22 to PB1 has completed via BF/2B) OR the
;              query timed out and CONTROL gave up on PB1's reset cells
;              for this Diag-page visit.
;   bit 1 set: same for PB2.
; Cleared on Diag-page entry so the page-entry hook re-fires cmd 0x22
; once per entry per PB.  The reset-cause flags don't change within a
; session, so re-querying every cadence cycle would waste chain bandwidth.
;
; Setting the bit on TIMEOUT (not just successful BF/2B) is the spec's
; "treat the reset-cause cache as unknown" gate (V32_DIAG_TIER1_SPEC.md
; §"Chain protocol" §"CONTROL parser side"): without it, a silent or
; pre-0x37 PB would lock RESET_PENDING set for the rest of the visit.
; Using the same bitmask for "saw it" and "gave up" is fine because
; the renderer only cares whether to re-issue cmd 0x22 (no), not why
; the cells are at 0.
v171_diag_reset_seen       equ  0x09D

; --- V1.71 Tier-1: cmd 0x22 timeout state (spec §"Chain protocol") ---
; The cmd 0x22 fire-once-per-PB hook in v171_diag_loop sets
; v171_diag_flags.RESET_PENDING when issuing the query, and the BF/2B
; parser case clears it on successful reception.  But pre-0x37 MAINs
; have no cmd 0x22 handler (they emit one stray 0x00 ACK byte and
; CONTROL drops it), and a silent / disconnected PB never replies at
; all -- without a timeout, RESET_PENDING would stay set forever and
; lock cmd 0x22 out for the OTHER PB and for subsequent Diag-page
; visits during the same session.  Spec calls for ~4 cadence cycles.
;
; v171_diag_reset_target captures v171_diag_target's bit 0 at the time
; cmd 0x22 was sent.  v171_diag_target itself can toggle independently
; via the cmd 0x21 BF/27 last-frame path between cmd 0x22 send and
; BF/2B reception, so we cannot trust v171_diag_target to identify the
; in-flight reset PB at timeout time.
v171_diag_reset_target     equ  0x09E

; v171_diag_reset_timeout is a small countdown decremented once per
; cadence cycle while RESET_PENDING is set.  Reloaded to
; V171_DIAG_RESET_TIMEOUT_RELOAD when cmd 0x22 is sent; on reaching
; zero, the cadence loop sets v171_diag_reset_seen.reset_target and
; clears RESET_PENDING (give-up path).
v171_diag_reset_timeout    equ  0x09F

; Cadence-cycle reload for the cmd 0x22 timeout.  Each cadence cycle
; is ~1 s (set by V171_DIAG_POLL_RELOAD_LO/HI).  A reload of 4 gives
; the spec's "4 cadence cycles" timeout window: cmd 0x22 fired ->
; 4 cadences pass without BF/2B -> give up.
V171_DIAG_RESET_TIMEOUT_RELOAD equ 0x04

; --- V1.71 Tier-1 Phase 3.4: per-PB Option-D sparse renderer scratch ---
; The Phase 3.4 sparse renderer (v171_diag_pb_screen / v171_diag_screen_draw)
; needs scratch cells that survive across the cadence loop's redraw path
; (`goto v171_diag_screen_draw` from check_redraw fires from inside the
; loop body, so the renderer cannot rely on access-bank scratch that
; display_loop_iteration / lcd_char_write helpers clobber).
;
; All cells live in BANK 1.  The EQU values are BANKED-form 8-bit
; operands; callers MUST `movlb 0x01` before any access -- a missing
; movlb 0x01 here would land at PHYSICAL 0x0CD..0x0D3 which IS a live
; region (see safety note below).  Test gate
; test_phase3_4_renderer_movlb_discipline_before_banked_writes
; pins the discipline.
;
; --- Safety note: BANK 0 co-residency at physical 0x0CD..0x0D3 ---
; The same operands 0xCD..0xD3 are ALSO accessed by the EEPROM
; saved-settings load/save/clear routines via ABSOLUTE addressing
; (`lfsr 0x0, 0x0CD` ... `clrf POSTINC0` walks at v171_asm lines
; ~2050, 2143, 2363, 4236, 5278, 5479).  Those FSR0 loads land at
; physical 0x0CD..0x0D3 (BANK 0) -- a DIFFERENT physical cell from
; our BANK 1 scratch at physical 0x1CD..0x1D3.
;
; The two regions live at the same operand value but in different
; physical banks, so they DO NOT alias under correct BSR discipline.
; But: a BSR=0 leak into one of our BANKED accesses below would
; SILENTLY CORRUPT the EEPROM saved-settings cache (and vice versa),
; reproducing the same class of bug as the 2026-04-20 Phase 3.1
; disaster.  Hence the strict movlb 0x01 requirement above.
;
; Why we picked this operand range despite the BANK 0 co-residency:
; the alternative ranges (above 0x0F8 in BANK 1, or BANK 2/3 with
; lfsr-based access) all had higher implementation cost and the
; BSR discipline above is enforced by the structural test gate.
; An earlier draft tried Common_RAM + 29 = 0x0E8 as access-bank
; scratch but that aliased ir_decoded_cmd's neighbours; the BANK 1
; sidestep here is strictly safer than that draft.
;
; v171_diag_render_pb_index: persists across cadence cycles (set on
;   v171_diag_pb_screen entry, read on every screen_draw redraw).
;   Other cells are scratch within a single screen_draw call only.
v171_diag_render_pb_index   equ  0x0CD   ; physical 0x1CD; 0=PB1, 1=PB2
v171_diag_render_count      equ  0x0CE   ; non-zero cells from pass 1 (0..11)
v171_diag_render_emitted    equ  0x0CF   ; entries emitted on current row
v171_diag_render_walk_idx   equ  0x0D0   ; cell index 0..10 during walk
v171_diag_render_value      equ  0x0D1   ; current cell value (saved across LCD calls)
v171_diag_render_skipped    equ  0x0D2   ; row-1 walk: non-zeros skipped from row 0
v171_diag_render_letter_tmp equ  0x0D3   ; v171_diag_letter_for_idx cascade scratch
; v171_diag_render_abnormal: count of non-zero "abnormal" cells (runtime
; counters + abnormal reset flags BOR/WDT/SW), excluding POR.  POR is
; set on every cold-init (Phase 2.2 reset-cause classification cascade)
; so counting it would make the "OK" healthy display path unreachable.
; Used by v171_diag_screen_present to gate healthy vs degraded:
;   abnormal == 0 -> healthy "PBn / OK" (POR may or may not be set;
;                    when set, omitted from the display per spec
;                    Option-D §"Healthy" + §"Status classification").
;   abnormal >  0 -> degraded sparse layout (renders ALL non-zero
;                    cells, including POR when set).
; See V32_DIAG_TIER1_SPEC.md §"LCD layouts (Option D)" + the
; ".../OK gate" follow-up section.
v171_diag_render_abnormal   equ  0x0D4   ; non-zero non-POR cells (0..10)

; Poll cadence reload value.  Each v171_diag_screen tick decrements
; the 16-bit countdown by 1; with display_loop_iteration on the K20
; control loop the per-tick wall time is on the order of single-digit
; ms.  Spec calls for "500 ms to 1 s cadence is sufficient".
; 0x0080 ticks (~1 s cadence) gives the firmware enough time for one
; full query/reply round-trip before the next cadence expires.
V171_DIAG_POLL_RELOAD_LO   equ  0x80
V171_DIAG_POLL_RELOAD_HI   equ  0x00

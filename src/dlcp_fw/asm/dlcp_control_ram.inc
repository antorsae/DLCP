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
button_event_latch         equ  0x09A    ; debounced/repeat button event bitmap consumed by UI pages
button_repeat_timer_lo     equ  0x09B    ; 16-bit button repeat/event timer lo
button_repeat_timer_hi     equ  0x09C    ; 16-bit button repeat/event timer hi
idle_timeout_lo            equ  0x09D    ; 16-bit idle timer lo, init 0xEA61
idle_timeout_hi            equ  0x09E    ; 16-bit idle timer hi
full_sync_lo               equ  0x09F    ; 16-bit full-sync counter lo, init 0x4E20
full_sync_hi               equ  0x0A0    ; 16-bit full-sync counter hi
raw_status_cache           equ  0x0A1    ; boot sentinel #4, init 0x80 until BF/05
menu_option_max_index      equ  0x0A4    ; inclusive max index for shared menu option editors
menu_option_selected_index equ  0x0A5    ; selected index for shared menu option editors
rx_frame_position          equ  0x0A6    ; parser state: 0=route, 1=cmd, 2=data
cmd1d_setting_cache        equ  0x0A7    ; boot sentinel #3, init 0x80 until BF/1D
backlight_elapsed_lo       equ  0x0B0    ; 32-bit backlight elapsed counter lo
backlight_elapsed_mid_lo   equ  0x0B1
backlight_elapsed_mid_hi   equ  0x0B2
backlight_elapsed_hi       equ  0x0B3
mute_blink_counter_lo      equ  0x0B4    ; muted-state backlight blink counter lo
mute_blink_counter_hi      equ  0x0B5
rx_parser_current_byte     equ  0x0B6    ; byte popped from RX ring for parser classification
rx_ring_staging            equ  0x0B7    ; single-byte holding cell for parser
input_select_cache         equ  0x0B8    ; boot sentinel #1, init 0x80 until BF/06
volume_cache               equ  0x0B9    ; boot sentinel #2, init 0x80 until BF/07
setup_submenu_index        equ  0x0BA    ; persisted setup/settings row index
button_debounce_counter    equ  0x0BB    ; threshold = 4
button_last_scan           equ  0x0BC    ; raw button sample
button_debounced_prev      equ  0x0BD    ; previous debounced button snapshot
button_debounced           equ  0x0BE    ; debounced state
display_state_index        equ  0x0BF    ; menu screen; legacy 0..5, split PB2-seen 0..6
source_channel_menu_index  equ  0x0C0    ; source/channel settings bank row index
saved_settings_base        equ  0x0C1    ; loaded by eeprom_settings_load (0x0C1..0x0CC)
backlight_timeout_selection equ  0x0EB   ; persisted backlight timeout menu selection
backlight_timeout_threshold_lo equ  0x0EC ; 32-bit backlight timeout threshold lo
backlight_timeout_threshold_mid_lo equ  0x0ED
backlight_timeout_threshold_mid_hi equ  0x0EE
backlight_timeout_threshold_hi equ  0x0EF

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
; Countdown for the legacy-link parser frame-gap timeout.
v171_rx_frame_gap_timeout  equ  0x0AC

; --- V1.71 WAITING-loop operator-recovery grace counter (2026-04-21) ---
; 16-bit saturating counter used by the WAITING-FOR-DLCP loops
; (cold-boot at asm:4448 and reconnect at asm:4716) to impose a grace
; period before enabling the RIGHT/LEFT button -> soft reset escape
; hatch.  Without the grace period, a spurious debounced button press
; during normal MAIN warmup (which can take a few seconds before
; MAIN's send_status_burst arrives) would cause an accidental CONTROL
; reset.
;
; Each WAITING-loop iteration is dominated by `delay_short(0xC8)`,
; which the routine's own header comment at asm:431-432 documents as
; "~200 cycles per unit (50 µs at 16 MHz)" with W=0xC8 -> "~10 ms".
; The remaining per-iteration work (button_scan_debounce,
; poll_frame_send, rx_parser_entry, sentinel check) totals well under
; 1 ms, so per-iteration wall time is ~10 ms.  Reaching ~10 s of
; grace therefore needs ~1000 iterations -- which does NOT fit in an
; 8-bit counter, so the implementation uses a 16-bit pair (lo at
; 0x0A8, hi at 0x0A9) and gates the reset on `grace_hi >=
; V171_WAITING_GRACE_THRESHOLD_HI` (= 4 -> 4*256 = 1024 iterations
; ~= 10.24 s).
;
; Slots chosen from the 0x0A8..0x0A9 gap (no absolute references in
; the V1.71 source; no lfsr lands in this range).  Both bytes are
; cleared to 0 on entry to each WAITING loop.  0x0AA was a retired
; deferred-IR latch; V1.73 claims it for the reconnect freshness mask.
v171_waiting_grace_count_lo equ  0x0A8
v171_waiting_grace_count_hi equ  0x0A9

; V1.73 BUG-V34V173-2: per-attempt reconnect liveness evidence (physical
; 0x0AA, BANK 0 so the RX parser and the WAITING loops -- both BSR=0 --
; touch it without movlb churn).  Cleared at reconnect_wait_loop entry;
; bit0 set by the BF/05 status-poll answer, bit1 by the BF/03/01 wake
; echo.  The reconnect exit tests this mask instead of the legacy
; four-sentinel cache compare (vacuously true on stale prior-session
; values, since the 0x80 sentinel seed happens exactly once at boot).
v173_reconnect_fresh_status_mask equ 0x0AA

; Threshold = 4 in the high byte.  Once `grace_hi` reaches 4 (i.e.
; the lo byte has wrapped past 0xFF four times), the button gate
; arms.  The implementation skips the increment once armed so the
; counter saturates at hi=4, lo=arbitrary -- the gate stays
; permanently armed for the rest of the WAITING session.
V171_WAITING_GRACE_THRESHOLD_HI equ 0x04
; Count-up timeout seed: with `infsnz`, 0x80 expires after 128 empty-loop
; ticks.  The old 0xF8/8-tick window could split valid 31.25 kbaud frames
; between route/cmd/data bytes in the foreground loop.
V171_RX_FRAME_GAP_RELOAD   equ  0x80

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
;
; v171_preset_bit_snapshot — BANK 1, physical 0x172.  Preset screen
; redraw dirty-check snapshot of control_flags.PRESET_BIT.
v171_preset_bit_snapshot  equ  0x072

; --- V1.71 Layer 1: bounded tx_byte_enqueue ---
; Replaces the V1.6b indefinite busy-wait at tx_byte_enqueue when the
; producer would collide with the ISR consumer (BUG C6).  The bounded
; form gives the TX ISR a fixed budget of poll iterations to advance
; tx_ring_rd; if it fails to do so, the byte is dropped (NOT committed
; to tx_ring_wr), v171_tx_saturate_count is bumped (saturating at
; 0xFF), and tx_byte_enqueue returns C=1 so callers can react.
;
; v171_tx_enq_retry — ACCESS-bank scratch byte used inside the
;   bounded retry loop and briefly by input_raw_status_full_fallback_save /
;   input_raw_status_restore.  Caller must not depend on its value across
;   either borrow.  Address chosen as the only free slot in the v1.71
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
;   v171_diag_target       = current in-flight query target:
;                            0 -> PB1, 1 -> PB2.  The Diag loop reloads
;                            this from v171_diag_render_pb_index before
;                            every send so the visible PB page gets the
;                            full ~1 s update cadence.
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
;                                          after the timeout window,
;                                          CONTROL clears PENDING and retries
;                                          the visible PB page.  A truly
;                                          absent PB keeps rendering n/a.
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

; v171_diag_runtime_target captures v171_diag_target's bit 0 at the time
; cmd 0x21 was sent.  The diagnostics page can interleave cmd 0x21 and
; cmd 0x22 replies, and v171_diag_target toggles on BF/27; routing all
; BF/21..BF/27 cells through this snapshot keeps an in-flight runtime
; burst pinned to the PB that was actually queried.
v171_diag_runtime_target   equ  0x0AE

; Runtime cmd 0x21 timeout counter.  While RUNTIME_PENDING is set, cadence
; expiry decrements this instead of immediately sending another cmd 0x21
; and overwriting v171_diag_runtime_target.  Only when it reaches zero do
; we treat the visible PB as silent, clear PENDING, and retry that page.
; This preserves the full BF/21..BF/27 burst as an atomic logical
; transaction from CONTROL's cache-routing perspective while keeping the
; active page's user-visible refresh cadence bounded.
v171_diag_runtime_timeout  equ  0x0AF
V171_DIAG_RUNTIME_TIMEOUT_RELOAD equ 0x10

; --- V1.71/V3.2 link-health freshness MVP (BANK 1) ---
; CONTROL-owned freshness state for the tiny cmd 0x23 / BF/2C health ping.
; Equate operands are BANKED-form; physical addresses are 0x1B0..0x1B9.
;
; Ages are coarse missed-health buckets, saturating at 0x0F.  A received
; expected BF/2C reply resets the addressed PB age to 0 and sets the
; corresponding seen bit.  Unknown-after-wake starts as seen_mask=0 and
; ages=0, so the main-screen suffix stays clear until real misses accrue.
v171_health_age_pb1        equ  0x0B0  ; physical 0x1B0
v171_health_age_pb2        equ  0x0B1  ; physical 0x1B1
v171_health_seen_mask      equ  0x0B2  ; physical 0x1B2; bit0 PB1, bit1 PB2
v171_health_flags          equ  0x0B3  ; physical 0x1B3
V171_HEALTH_FLAG_PENDING        equ 0x00
V171_HEALTH_FLAG_TARGET         equ 0x01  ; snapshot: 0 PB1, 1 PB2
V171_HEALTH_FLAG_DISPLAY_DIRTY  equ 0x02
v171_health_poll_target    equ  0x0B4  ; physical 0x1B4; 0 PB1, 1 PB2
v171_health_tick_div       equ  0x0B5  ; physical 0x1B5
v171_health_pending_ticks  equ  0x0B6  ; physical 0x1B6
v171_health_suffix_mask    equ  0x0B7  ; physical 0x1B7; LCD suffix scratch
v171_diag_effective_target equ  0x0B8  ; physical 0x1B8; BF/2N parser routing snapshot
v171_health_age_tmp        equ  0x0B9  ; physical 0x1B9; Diag stale/lost classifier scratch
V171_HEALTH_PENDING_TICKS  equ  0x20
V171_HEALTH_STALE_AGE      equ  0x03
V171_HEALTH_LOST_AGE       equ  0x0A

; --- V1.73 multi-PB input selection (BANK 1) ---
; Runtime-only PB split state.  PB1 reuses the legacy
; input_select_cache byte (0x0B8) because it is already the boot sentinel
; and legacy single-PB source of truth; PB2 needs a second CONTROL-owned
; intent byte once a second MAIN has been discovered.
input_split_flags          equ  0x0BA  ; physical 0x1BA
INPUT_SPLIT_FLAG_PB2_SEEN  equ  0x00   ; latched until cold boot
INPUT_SPLIT_FLAG_SYNC_TARGET equ 0x01  ; next full-sync target: 0 PB1, 1 PB2
INPUT_SPLIT_FLAG_PB2_LINKED equ 0x02   ; PB2 input follows PB1 via broadcast
INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE equ 0x03 ; sanitized persisted PB2 value is concrete
INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY equ 0x04 ; user changed PB2 setting; save once
INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE equ 0x05 ; unavailable persisted PB2 is temporarily linked
input_intent_pb2           equ  0x0BB  ; physical 0x1BB
input_send_target          equ  0x0BC  ; physical 0x1BC; scratch: 0 PB1, 1 PB2
input_pending_pb2          equ  0x0BD  ; physical 0x1BD; decoded persisted PB2 cmd06 payload

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
; the 16-bit countdown by 1.  Measured in the rust ring, the non-modal
; Diagnostics loop runs at roughly 7.7 kHz when idle; the old 0x0080
; reload therefore fired cmd 0x21 at ~60 Hz, causing excessive chain
; traffic and repeated full-LCD redraws on real hardware.  The page-entry
; clear path still makes the first query immediate.  V3.2's SRC4382 Auto
; Detect rewrite removed enough MAIN-side I2C load that the old 0x1E00
; value measured closer to 3 Hz in the full V1.71/V3.2 chain; 0x5A00
; restores the intended ~1 Hz operator-visible cadence without returning
; to modal waits.
V171_DIAG_POLL_RELOAD_LO   equ  0x00
V171_DIAG_POLL_RELOAD_HI   equ  0x5A

; --- V1.72/V3.3 Diagnostics MAIN identity cache (BANK 2) ---
; Physical 0x245..0x254 plus V1.73 16-bit revision extension cells at
; 0x26C..0x26E.  EQU operands are BANKED-form values; every firmware
; access must assert `movlb 0x02`.
v172_diag_id_pb1_major     equ  0x045
v172_diag_id_pb1_minor     equ  0x046
v172_diag_id_pb1_rev       equ  0x047   ; V1.73: low byte of 16-bit rev
v172_diag_id_pb2_major     equ  0x048
v172_diag_id_pb2_minor     equ  0x049
v172_diag_id_pb2_rev       equ  0x04A   ; V1.73: low byte of 16-bit rev
v172_diag_id_valid_mask    equ  0x04B
v172_diag_id_seen_mask     equ  0x04C
v172_diag_id_pending_id    equ  0x04D
v172_diag_id_flags         equ  0x04E
V172_DIAG_ID_FLAG_PENDING  equ  0x00
V172_DIAG_ID_FLAG_TARGET   equ  0x01
V172_DIAG_ID_FLAG_RETRIED  equ  0x02
v172_diag_id_timeout       equ  0x04F
v172_diag_id_next_gen      equ  0x050
v172_diag_id_expected_cmd  equ  0x051
v172_diag_id_tmp_major     equ  0x052
v172_diag_id_tmp_minor     equ  0x053
v172_diag_id_tmp_rev_hi    equ  0x054
v173_diag_id_pb1_rev_hi    equ  0x06C   ; physical 0x26C, high byte of 16-bit rev
v173_diag_id_pb2_rev_hi    equ  0x06D   ; physical 0x26D, high byte of 16-bit rev
v173_diag_id_tmp_rev_lo    equ  0x06E   ; physical 0x26E, staged low byte
V172_DIAG_ID_TIMEOUT_RELOAD equ 0x04

; --- V1.72/V3.3 Preset filename LCD cache/state (BANK 2) ---
; Physical 0x220..0x244 and 0x255..0x25D.  Keep 0x245..0x254
; reserved for the legacy diagnostics identity block above.  EQU operands
; are BANKED-form values; every firmware access must assert `movlb 0x02`.
v172_fname_cache           equ  0x020  ; physical 0x220..0x23D, 30 chars
v172_fname_len             equ  0x03E
v172_fname_expected_len    equ  0x03F
v172_fname_flags           equ  0x040
FNAME_VALID                equ  0x00
FNAME_PENDING              equ  0x01
FNAME_WANT_QUERY           equ  0x02
FNAME_ROW_DIRTY            equ  0x03
FNAME_ARMED                equ  0x04
FNAME_TAILDIR              equ  0x05
FNAME_LEN_SEEN             equ  0x06
FNAME_QUERY_WAIT           equ  0x07  ; delayed first filename query after Preset draw
FNAME_ROW0_HEALTH          equ  0x00
FNAME_ROW0_PRESET_B        equ  0x01
FNAME_ROW0_DSP_FAULT       equ  0x02
FNAME_ROW0_NOT_READY       equ  0x07
FNAME_ROW0_HEALTH_MASK     equ  0x01
FNAME_ROW0_PRESET_FAULT_MASK equ 0x06
FNAME_ROW0_SNAP_MASK       equ  0x87
v172_fname_gen             equ  0x041
v172_fname_id              equ  0x042
v172_fname_scroll_off      equ  0x043
v172_fname_scroll_hold     equ  0x044
v172_fname_scroll_div_lo   equ  0x055
v172_fname_scroll_div_hi   equ  0x056
v172_fname_deadline_lo     equ  0x057
v172_fname_deadline_hi     equ  0x058
v172_fname_render_col      equ  0x059
v172_fname_render_off      equ  0x05A
v172_fname_row0_status_snap equ 0x05B
v172_fname_tmp             equ  0x05C
; V1.73 BUG-V34V173-4: bounded filename retry budget.  Incremented by
; fname_reset_blank_maybe_retry on parser abort / pending-deadline expiry;
; cleared on successful reception (FNAME_VALID set) and on Preset page
; entry, so each page visit gets a fresh budget.
v172_fname_retry           equ  0x05D
v173_row0_reassert_div     equ  0x05E    ; bank2 0x25E: Preset row-0 re-assert pass divider (FIELD-3)
v173_isr_decode_save       equ  0x060    ; bank2 0x260..0x26A: 11-byte save area for the foreground
                                         ; scratch the blocking in-ISR RC5 decode clobbers
                                         ; (0x005,0x008,0x00C,0x00D,0x00E,0x010..0x013,0x014,0x015)
v173_mute_reassert_div     equ  0x06B    ; bank2 0x26B: health-poll divider for the periodic
                                         ; idempotent mute re-assert (session-49 lost-frame heal)
FNAME_RETRY_MAX            equ  0x03  ; initial query + 2 spaced retries
FNAME_PENDING_DEADLINE_HI  equ  0x40
FNAME_PENDING_DEADLINE_LO  equ  0x00
FNAME_QUERY_DELAY_A_HI     equ  0x30
FNAME_QUERY_DELAY_B_HI     equ  0x40
FNAME_QUERY_DELAY_LO       equ  0x00
FNAME_SCROLL_DIV_HI        equ  0x08
FNAME_SCROLL_DIV_LO        equ  0x00
FNAME_SCROLL_REST_HOLD     equ  0x06
FNAME_SCROLL_FAR_HOLD      equ  0x03

; --- RAM bank safety generated aliases: BEGIN ---
; Generated from ram_bank_manifest.py.  Do not hand-edit this block.
stock_010_acc                    EQU  0x010    ; phys 0x010, bank 0, owner stock-derived
stock_010_acc_op                 EQU  0x10     ; 8-bit f operand for stock_010_acc
stock_010_acc_phys               EQU  0x010    ; physical address for movff/lfsr
stock_010_b0                     EQU  0x010    ; phys 0x010, bank 0, owner stock-derived
stock_010_b0_op                  EQU  0x10     ; 8-bit f operand for stock_010_b0
stock_010_b0_phys                EQU  0x010    ; physical address for movff/lfsr
ir_decoded_cmd_acc               EQU  0x01D    ; phys 0x01D, bank 0, owner ir_decoded_cmd
ir_decoded_cmd_acc_op            EQU  0x1D     ; 8-bit f operand for ir_decoded_cmd_acc
ir_decoded_cmd_acc_phys          EQU  0x01D    ; physical address for movff/lfsr
ir_decoded_cmd_b0                EQU  0x01D    ; phys 0x01D, bank 0, owner ir_decoded_cmd
ir_decoded_cmd_b0_op             EQU  0x1D     ; 8-bit f operand for ir_decoded_cmd_b0
ir_decoded_cmd_b0_phys           EQU  0x01D    ; physical address for movff/lfsr
ir_decoded_addr_acc              EQU  0x01E    ; phys 0x01E, bank 0, owner ir_decoded_addr
ir_decoded_addr_acc_op           EQU  0x1E     ; 8-bit f operand for ir_decoded_addr_acc
ir_decoded_addr_acc_phys         EQU  0x01E    ; physical address for movff/lfsr
ir_decoded_addr_b0               EQU  0x01E    ; phys 0x01E, bank 0, owner ir_decoded_addr
ir_decoded_addr_b0_op            EQU  0x1E     ; 8-bit f operand for ir_decoded_addr_b0
ir_decoded_addr_b0_phys          EQU  0x01E    ; physical address for movff/lfsr
control_flags_acc                EQU  0x01F    ; phys 0x01F, bank 0, owner control_flags
control_flags_acc_op             EQU  0x1F     ; 8-bit f operand for control_flags_acc
control_flags_acc_phys           EQU  0x01F    ; physical address for movff/lfsr
control_flags_b0                 EQU  0x01F    ; phys 0x01F, bank 0, owner control_flags
control_flags_b0_op              EQU  0x1F     ; 8-bit f operand for control_flags_b0
control_flags_b0_phys            EQU  0x01F    ; physical address for movff/lfsr
stock_024_acc                    EQU  0x024    ; phys 0x024, bank 0, owner stock-derived
stock_024_acc_op                 EQU  0x24     ; 8-bit f operand for stock_024_acc
stock_024_acc_phys               EQU  0x024    ; physical address for movff/lfsr
stock_024_b0                     EQU  0x024    ; phys 0x024, bank 0, owner stock-derived
stock_024_b0_op                  EQU  0x24     ; 8-bit f operand for stock_024_b0
stock_024_b0_phys                EQU  0x024    ; physical address for movff/lfsr
tx_data_staging_acc              EQU  0x027    ; phys 0x027, bank 0, owner tx_data_staging
tx_data_staging_acc_op           EQU  0x27     ; 8-bit f operand for tx_data_staging_acc
tx_data_staging_acc_phys         EQU  0x027    ; physical address for movff/lfsr
tx_data_staging_b0               EQU  0x027    ; phys 0x027, bank 0, owner tx_data_staging
tx_data_staging_b0_op            EQU  0x27     ; 8-bit f operand for tx_data_staging_b0
tx_data_staging_b0_phys          EQU  0x027    ; physical address for movff/lfsr
v171_tx_enq_retry_acc            EQU  0x02D    ; phys 0x02D, bank 0, owner v171_tx_enq_retry
v171_tx_enq_retry_acc_op         EQU  0x2D     ; 8-bit f operand for v171_tx_enq_retry_acc
v171_tx_enq_retry_acc_phys       EQU  0x02D    ; physical address for movff/lfsr
v171_tx_enq_retry_b0             EQU  0x02D    ; phys 0x02D, bank 0, owner v171_tx_enq_retry
v171_tx_enq_retry_b0_op          EQU  0x2D     ; 8-bit f operand for v171_tx_enq_retry_b0
v171_tx_enq_retry_b0_phys        EQU  0x02D    ; physical address for movff/lfsr
rx_parsed_cmd_acc                EQU  0x02F    ; phys 0x02F, bank 0, owner rx_parsed_cmd
rx_parsed_cmd_acc_op             EQU  0x2F     ; 8-bit f operand for rx_parsed_cmd_acc
rx_parsed_cmd_acc_phys           EQU  0x02F    ; physical address for movff/lfsr
rx_parsed_cmd_b0                 EQU  0x02F    ; phys 0x02F, bank 0, owner rx_parsed_cmd
rx_parsed_cmd_b0_op              EQU  0x2F     ; 8-bit f operand for rx_parsed_cmd_b0
rx_parsed_cmd_b0_phys            EQU  0x02F    ; physical address for movff/lfsr
rx_parsed_data_acc               EQU  0x030    ; phys 0x030, bank 0, owner rx_parsed_data
rx_parsed_data_acc_op            EQU  0x30     ; 8-bit f operand for rx_parsed_data_acc
rx_parsed_data_acc_phys          EQU  0x030    ; physical address for movff/lfsr
rx_parsed_data_b0                EQU  0x030    ; phys 0x030, bank 0, owner rx_parsed_data
rx_parsed_data_b0_op             EQU  0x30     ; 8-bit f operand for rx_parsed_data_b0
rx_parsed_data_b0_phys           EQU  0x030    ; physical address for movff/lfsr
tx_ring_base_acc                 EQU  0x036    ; phys 0x036, bank 0, owner tx_ring_base
tx_ring_base_acc_op              EQU  0x36     ; 8-bit f operand for tx_ring_base_acc
tx_ring_base_acc_phys            EQU  0x036    ; physical address for movff/lfsr
tx_ring_base_b0                  EQU  0x036    ; phys 0x036, bank 0, owner tx_ring_base
tx_ring_base_b0_op               EQU  0x36     ; 8-bit f operand for tx_ring_base_b0
tx_ring_base_b0_phys             EQU  0x036    ; physical address for movff/lfsr
stock_043_acc                    EQU  0x043    ; phys 0x043, bank 0, owner stock-derived
stock_043_acc_op                 EQU  0x43     ; 8-bit f operand for stock_043_acc
stock_043_acc_phys               EQU  0x043    ; physical address for movff/lfsr
stock_043_b0                     EQU  0x043    ; phys 0x043, bank 0, owner stock-derived
stock_043_b0_op                  EQU  0x43     ; 8-bit f operand for stock_043_b0
stock_043_b0_phys                EQU  0x043    ; physical address for movff/lfsr
stock_065_b0                     EQU  0x065    ; phys 0x065, bank 0, owner stock-derived
stock_065_b0_op                  EQU  0x65     ; 8-bit f operand for stock_065_b0
stock_065_b0_phys                EQU  0x065    ; physical address for movff/lfsr
rx_ring_base_b0                  EQU  0x066    ; phys 0x066, bank 0, owner rx_ring_base
rx_ring_base_b0_op               EQU  0x66     ; 8-bit f operand for rx_ring_base_b0
rx_ring_base_b0_phys             EQU  0x066    ; physical address for movff/lfsr
stock_06C_b0                     EQU  0x06C    ; phys 0x06C, bank 0, owner stock-derived
stock_06C_b0_op                  EQU  0x6C     ; 8-bit f operand for stock_06C_b0
stock_06C_b0_phys                EQU  0x06C    ; physical address for movff/lfsr
stock_06D_b0                     EQU  0x06D    ; phys 0x06D, bank 0, owner stock-derived
stock_06D_b0_op                  EQU  0x6D     ; 8-bit f operand for stock_06D_b0
stock_06D_b0_phys                EQU  0x06D    ; physical address for movff/lfsr
stock_06F_b0                     EQU  0x06F    ; phys 0x06F, bank 0, owner stock-derived
stock_06F_b0_op                  EQU  0x6F     ; 8-bit f operand for stock_06F_b0
stock_06F_b0_phys                EQU  0x06F    ; physical address for movff/lfsr
stock_071_b0                     EQU  0x071    ; phys 0x071, bank 0, owner stock-derived
stock_071_b0_op                  EQU  0x71     ; 8-bit f operand for stock_071_b0
stock_071_b0_phys                EQU  0x071    ; physical address for movff/lfsr
stock_074_b0                     EQU  0x074    ; phys 0x074, bank 0, owner stock-derived
stock_074_b0_op                  EQU  0x74     ; 8-bit f operand for stock_074_b0
stock_074_b0_phys                EQU  0x074    ; physical address for movff/lfsr
stock_076_b0                     EQU  0x076    ; phys 0x076, bank 0, owner stock-derived
stock_076_b0_op                  EQU  0x76     ; 8-bit f operand for stock_076_b0
stock_076_b0_phys                EQU  0x076    ; physical address for movff/lfsr
stock_077_b0                     EQU  0x077    ; phys 0x077, bank 0, owner stock-derived
stock_077_b0_op                  EQU  0x77     ; 8-bit f operand for stock_077_b0
stock_077_b0_phys                EQU  0x077    ; physical address for movff/lfsr
stock_078_b0                     EQU  0x078    ; phys 0x078, bank 0, owner stock-derived
stock_078_b0_op                  EQU  0x78     ; 8-bit f operand for stock_078_b0
stock_078_b0_phys                EQU  0x078    ; physical address for movff/lfsr
stock_079_b0                     EQU  0x079    ; phys 0x079, bank 0, owner stock-derived
stock_079_b0_op                  EQU  0x79     ; 8-bit f operand for stock_079_b0
stock_079_b0_phys                EQU  0x079    ; physical address for movff/lfsr
stock_07A_b0                     EQU  0x07A    ; phys 0x07A, bank 0, owner stock-derived
stock_07A_b0_op                  EQU  0x7A     ; 8-bit f operand for stock_07A_b0
stock_07A_b0_phys                EQU  0x07A    ; physical address for movff/lfsr
stock_07B_b0                     EQU  0x07B    ; phys 0x07B, bank 0, owner stock-derived
stock_07B_b0_op                  EQU  0x7B     ; 8-bit f operand for stock_07B_b0
stock_07B_b0_phys                EQU  0x07B    ; physical address for movff/lfsr
stock_07C_b0                     EQU  0x07C    ; phys 0x07C, bank 0, owner stock-derived
stock_07C_b0_op                  EQU  0x7C     ; 8-bit f operand for stock_07C_b0
stock_07C_b0_phys                EQU  0x07C    ; physical address for movff/lfsr
stock_082_b0                     EQU  0x082    ; phys 0x082, bank 0, owner stock-derived
stock_082_b0_op                  EQU  0x82     ; 8-bit f operand for stock_082_b0
stock_082_b0_phys                EQU  0x082    ; physical address for movff/lfsr
tx_ring_rd_b0                    EQU  0x096    ; phys 0x096, bank 0, owner tx_ring_rd
tx_ring_rd_b0_op                 EQU  0x96     ; 8-bit f operand for tx_ring_rd_b0
tx_ring_rd_b0_phys               EQU  0x096    ; physical address for movff/lfsr
tx_ring_wr_b0                    EQU  0x097    ; phys 0x097, bank 0, owner tx_ring_wr
tx_ring_wr_b0_op                 EQU  0x97     ; 8-bit f operand for tx_ring_wr_b0
tx_ring_wr_b0_phys               EQU  0x097    ; physical address for movff/lfsr
rx_ring_rd_b0                    EQU  0x098    ; phys 0x098, bank 0, owner rx_ring_rd
rx_ring_rd_b0_op                 EQU  0x98     ; 8-bit f operand for rx_ring_rd_b0
rx_ring_rd_b0_phys               EQU  0x098    ; physical address for movff/lfsr
rx_ring_wr_b0                    EQU  0x099    ; phys 0x099, bank 0, owner rx_ring_wr
rx_ring_wr_b0_op                 EQU  0x99     ; 8-bit f operand for rx_ring_wr_b0
rx_ring_wr_b0_phys               EQU  0x099    ; physical address for movff/lfsr
button_event_latch_b0            EQU  0x09A    ; phys 0x09A, bank 0, owner button_event_latch
button_event_latch_b0_op         EQU  0x9A     ; 8-bit f operand for button_event_latch_b0
button_event_latch_b0_phys       EQU  0x09A    ; physical address for movff/lfsr
stock_09A_b0                     EQU  0x09A    ; phys 0x09A, bank 0, owner stock-derived
stock_09A_b0_op                  EQU  0x9A     ; 8-bit f operand for stock_09A_b0
stock_09A_b0_phys                EQU  0x09A    ; physical address for movff/lfsr
button_repeat_timer_lo_b0        EQU  0x09B    ; phys 0x09B, bank 0, owner button_repeat_timer_lo
button_repeat_timer_lo_b0_op     EQU  0x9B     ; 8-bit f operand for button_repeat_timer_lo_b0
button_repeat_timer_lo_b0_phys   EQU  0x09B    ; physical address for movff/lfsr
stock_09B_b0                     EQU  0x09B    ; phys 0x09B, bank 0, owner stock-derived
stock_09B_b0_op                  EQU  0x9B     ; 8-bit f operand for stock_09B_b0
stock_09B_b0_phys                EQU  0x09B    ; physical address for movff/lfsr
button_repeat_timer_hi_b0        EQU  0x09C    ; phys 0x09C, bank 0, owner button_repeat_timer_hi
button_repeat_timer_hi_b0_op     EQU  0x9C     ; 8-bit f operand for button_repeat_timer_hi_b0
button_repeat_timer_hi_b0_phys   EQU  0x09C    ; physical address for movff/lfsr
stock_09C_b0                     EQU  0x09C    ; phys 0x09C, bank 0, owner stock-derived
stock_09C_b0_op                  EQU  0x9C     ; 8-bit f operand for stock_09C_b0
stock_09C_b0_phys                EQU  0x09C    ; physical address for movff/lfsr
idle_timeout_lo_b0               EQU  0x09D    ; phys 0x09D, bank 0, owner idle_timeout_lo
idle_timeout_lo_b0_op            EQU  0x9D     ; 8-bit f operand for idle_timeout_lo_b0
idle_timeout_lo_b0_phys          EQU  0x09D    ; physical address for movff/lfsr
idle_timeout_hi_b0               EQU  0x09E    ; phys 0x09E, bank 0, owner idle_timeout_hi
idle_timeout_hi_b0_op            EQU  0x9E     ; 8-bit f operand for idle_timeout_hi_b0
idle_timeout_hi_b0_phys          EQU  0x09E    ; physical address for movff/lfsr
full_sync_lo_b0                  EQU  0x09F    ; phys 0x09F, bank 0, owner full_sync_lo
full_sync_lo_b0_op               EQU  0x9F     ; 8-bit f operand for full_sync_lo_b0
full_sync_lo_b0_phys             EQU  0x09F    ; physical address for movff/lfsr
full_sync_hi_b0                  EQU  0x0A0    ; phys 0x0A0, bank 0, owner full_sync_hi
full_sync_hi_b0_op               EQU  0xA0     ; 8-bit f operand for full_sync_hi_b0
full_sync_hi_b0_phys             EQU  0x0A0    ; physical address for movff/lfsr
raw_status_cache_b0              EQU  0x0A1    ; phys 0x0A1, bank 0, owner raw_status_cache
raw_status_cache_b0_op           EQU  0xA1     ; 8-bit f operand for raw_status_cache_b0
raw_status_cache_b0_phys         EQU  0x0A1    ; physical address for movff/lfsr
stock_0A2_b0                     EQU  0x0A2    ; phys 0x0A2, bank 0, owner stock-derived
stock_0A2_b0_op                  EQU  0xA2     ; 8-bit f operand for stock_0A2_b0
stock_0A2_b0_phys                EQU  0x0A2    ; physical address for movff/lfsr
stock_0A3_b0                     EQU  0x0A3    ; phys 0x0A3, bank 0, owner stock-derived
stock_0A3_b0_op                  EQU  0xA3     ; 8-bit f operand for stock_0A3_b0
stock_0A3_b0_phys                EQU  0x0A3    ; physical address for movff/lfsr
menu_option_max_index_b0         EQU  0x0A4    ; phys 0x0A4, bank 0, owner menu_option_max_index
menu_option_max_index_b0_op      EQU  0xA4     ; 8-bit f operand for menu_option_max_index_b0
menu_option_max_index_b0_phys    EQU  0x0A4    ; physical address for movff/lfsr
stock_0A4_b0                     EQU  0x0A4    ; phys 0x0A4, bank 0, owner stock-derived
stock_0A4_b0_op                  EQU  0xA4     ; 8-bit f operand for stock_0A4_b0
stock_0A4_b0_phys                EQU  0x0A4    ; physical address for movff/lfsr
menu_option_selected_index_b0    EQU  0x0A5    ; phys 0x0A5, bank 0, owner menu_option_selected_index
menu_option_selected_index_b0_op EQU  0xA5     ; 8-bit f operand for menu_option_selected_index_b0
menu_option_selected_index_b0_phys EQU  0x0A5    ; physical address for movff/lfsr
stock_0A5_b0                     EQU  0x0A5    ; phys 0x0A5, bank 0, owner stock-derived
stock_0A5_b0_op                  EQU  0xA5     ; 8-bit f operand for stock_0A5_b0
stock_0A5_b0_phys                EQU  0x0A5    ; physical address for movff/lfsr
rx_frame_position_b0             EQU  0x0A6    ; phys 0x0A6, bank 0, owner rx_frame_position
rx_frame_position_b0_op          EQU  0xA6     ; 8-bit f operand for rx_frame_position_b0
rx_frame_position_b0_phys        EQU  0x0A6    ; physical address for movff/lfsr
cmd1d_setting_cache_b0           EQU  0x0A7    ; phys 0x0A7, bank 0, owner cmd1d_setting_cache
cmd1d_setting_cache_b0_op        EQU  0xA7     ; 8-bit f operand for cmd1d_setting_cache_b0
cmd1d_setting_cache_b0_phys      EQU  0x0A7    ; physical address for movff/lfsr
v171_waiting_grace_count_lo_b0   EQU  0x0A8    ; phys 0x0A8, bank 0, owner v171_waiting_grace_count_lo
v171_waiting_grace_count_lo_b0_op EQU  0xA8     ; 8-bit f operand for v171_waiting_grace_count_lo_b0
v171_waiting_grace_count_lo_b0_phys EQU  0x0A8    ; physical address for movff/lfsr
v171_waiting_grace_count_hi_b0   EQU  0x0A9    ; phys 0x0A9, bank 0, owner v171_waiting_grace_count_hi
v171_waiting_grace_count_hi_b0_op EQU  0xA9     ; 8-bit f operand for v171_waiting_grace_count_hi_b0
v171_waiting_grace_count_hi_b0_phys EQU  0x0A9    ; physical address for movff/lfsr
v173_reconnect_fresh_status_mask_b0 EQU  0x0AA    ; phys 0x0AA, bank 0, owner v173_reconnect_fresh_status_mask
v173_reconnect_fresh_status_mask_b0_op EQU  0xAA     ; 8-bit f operand for v173_reconnect_fresh_status_mask_b0
v173_reconnect_fresh_status_mask_b0_phys EQU  0x0AA    ; physical address for movff/lfsr
bf08_fault_byte_b0               EQU  0x0AB    ; phys 0x0AB, bank 0, owner bf08_fault_byte
bf08_fault_byte_b0_op            EQU  0xAB     ; 8-bit f operand for bf08_fault_byte_b0
bf08_fault_byte_b0_phys          EQU  0x0AB    ; physical address for movff/lfsr
v171_rx_frame_gap_timeout_b0     EQU  0x0AC    ; phys 0x0AC, bank 0, owner v171_rx_frame_gap_timeout
v171_rx_frame_gap_timeout_b0_op  EQU  0xAC     ; 8-bit f operand for v171_rx_frame_gap_timeout_b0
v171_rx_frame_gap_timeout_b0_phys EQU  0x0AC    ; physical address for movff/lfsr
stock_0AE_b0                     EQU  0x0AE    ; phys 0x0AE, bank 0, owner stock-derived
stock_0AE_b0_op                  EQU  0xAE     ; 8-bit f operand for stock_0AE_b0
stock_0AE_b0_phys                EQU  0x0AE    ; physical address for movff/lfsr
stock_0AF_b0                     EQU  0x0AF    ; phys 0x0AF, bank 0, owner stock-derived
stock_0AF_b0_op                  EQU  0xAF     ; 8-bit f operand for stock_0AF_b0
stock_0AF_b0_phys                EQU  0x0AF    ; physical address for movff/lfsr
backlight_elapsed_lo_b0          EQU  0x0B0    ; phys 0x0B0, bank 0, owner backlight_elapsed_lo
backlight_elapsed_lo_b0_op       EQU  0xB0     ; 8-bit f operand for backlight_elapsed_lo_b0
backlight_elapsed_lo_b0_phys     EQU  0x0B0    ; physical address for movff/lfsr
stock_0B0_b0                     EQU  0x0B0    ; phys 0x0B0, bank 0, owner stock-derived
stock_0B0_b0_op                  EQU  0xB0     ; 8-bit f operand for stock_0B0_b0
stock_0B0_b0_phys                EQU  0x0B0    ; physical address for movff/lfsr
backlight_elapsed_mid_lo_b0      EQU  0x0B1    ; phys 0x0B1, bank 0, owner backlight_elapsed_mid_lo
backlight_elapsed_mid_lo_b0_op   EQU  0xB1     ; 8-bit f operand for backlight_elapsed_mid_lo_b0
backlight_elapsed_mid_lo_b0_phys EQU  0x0B1    ; physical address for movff/lfsr
stock_0B1_b0                     EQU  0x0B1    ; phys 0x0B1, bank 0, owner stock-derived
stock_0B1_b0_op                  EQU  0xB1     ; 8-bit f operand for stock_0B1_b0
stock_0B1_b0_phys                EQU  0x0B1    ; physical address for movff/lfsr
backlight_elapsed_mid_hi_b0      EQU  0x0B2    ; phys 0x0B2, bank 0, owner backlight_elapsed_mid_hi
backlight_elapsed_mid_hi_b0_op   EQU  0xB2     ; 8-bit f operand for backlight_elapsed_mid_hi_b0
backlight_elapsed_mid_hi_b0_phys EQU  0x0B2    ; physical address for movff/lfsr
stock_0B2_b0                     EQU  0x0B2    ; phys 0x0B2, bank 0, owner stock-derived
stock_0B2_b0_op                  EQU  0xB2     ; 8-bit f operand for stock_0B2_b0
stock_0B2_b0_phys                EQU  0x0B2    ; physical address for movff/lfsr
backlight_elapsed_hi_b0          EQU  0x0B3    ; phys 0x0B3, bank 0, owner backlight_elapsed_hi
backlight_elapsed_hi_b0_op       EQU  0xB3     ; 8-bit f operand for backlight_elapsed_hi_b0
backlight_elapsed_hi_b0_phys     EQU  0x0B3    ; physical address for movff/lfsr
stock_0B3_b0                     EQU  0x0B3    ; phys 0x0B3, bank 0, owner stock-derived
stock_0B3_b0_op                  EQU  0xB3     ; 8-bit f operand for stock_0B3_b0
stock_0B3_b0_phys                EQU  0x0B3    ; physical address for movff/lfsr
mute_blink_counter_lo_b0         EQU  0x0B4    ; phys 0x0B4, bank 0, owner mute_blink_counter_lo
mute_blink_counter_lo_b0_op      EQU  0xB4     ; 8-bit f operand for mute_blink_counter_lo_b0
mute_blink_counter_lo_b0_phys    EQU  0x0B4    ; physical address for movff/lfsr
stock_0B4_b0                     EQU  0x0B4    ; phys 0x0B4, bank 0, owner stock-derived
stock_0B4_b0_op                  EQU  0xB4     ; 8-bit f operand for stock_0B4_b0
stock_0B4_b0_phys                EQU  0x0B4    ; physical address for movff/lfsr
mute_blink_counter_hi_b0         EQU  0x0B5    ; phys 0x0B5, bank 0, owner mute_blink_counter_hi
mute_blink_counter_hi_b0_op      EQU  0xB5     ; 8-bit f operand for mute_blink_counter_hi_b0
mute_blink_counter_hi_b0_phys    EQU  0x0B5    ; physical address for movff/lfsr
stock_0B5_b0                     EQU  0x0B5    ; phys 0x0B5, bank 0, owner stock-derived
stock_0B5_b0_op                  EQU  0xB5     ; 8-bit f operand for stock_0B5_b0
stock_0B5_b0_phys                EQU  0x0B5    ; physical address for movff/lfsr
rx_parser_current_byte_b0        EQU  0x0B6    ; phys 0x0B6, bank 0, owner rx_parser_current_byte
rx_parser_current_byte_b0_op     EQU  0xB6     ; 8-bit f operand for rx_parser_current_byte_b0
rx_parser_current_byte_b0_phys   EQU  0x0B6    ; physical address for movff/lfsr
stock_0B6_b0                     EQU  0x0B6    ; phys 0x0B6, bank 0, owner stock-derived
stock_0B6_b0_op                  EQU  0xB6     ; 8-bit f operand for stock_0B6_b0
stock_0B6_b0_phys                EQU  0x0B6    ; physical address for movff/lfsr
rx_ring_staging_b0               EQU  0x0B7    ; phys 0x0B7, bank 0, owner rx_ring_staging
rx_ring_staging_b0_op            EQU  0xB7     ; 8-bit f operand for rx_ring_staging_b0
rx_ring_staging_b0_phys          EQU  0x0B7    ; physical address for movff/lfsr
input_select_cache_b0            EQU  0x0B8    ; phys 0x0B8, bank 0, owner input_select_cache
input_select_cache_b0_op         EQU  0xB8     ; 8-bit f operand for input_select_cache_b0
input_select_cache_b0_phys       EQU  0x0B8    ; physical address for movff/lfsr
volume_cache_b0                  EQU  0x0B9    ; phys 0x0B9, bank 0, owner volume_cache
volume_cache_b0_op               EQU  0xB9     ; 8-bit f operand for volume_cache_b0
volume_cache_b0_phys             EQU  0x0B9    ; physical address for movff/lfsr
setup_submenu_index_b0           EQU  0x0BA    ; phys 0x0BA, bank 0, owner setup_submenu_index
setup_submenu_index_b0_op        EQU  0xBA     ; 8-bit f operand for setup_submenu_index_b0
setup_submenu_index_b0_phys      EQU  0x0BA    ; physical address for movff/lfsr
stock_0BA_b0                     EQU  0x0BA    ; phys 0x0BA, bank 0, owner stock-derived
stock_0BA_b0_op                  EQU  0xBA     ; 8-bit f operand for stock_0BA_b0
stock_0BA_b0_phys                EQU  0x0BA    ; physical address for movff/lfsr
button_debounce_counter_b0       EQU  0x0BB    ; phys 0x0BB, bank 0, owner button_debounce_counter
button_debounce_counter_b0_op    EQU  0xBB     ; 8-bit f operand for button_debounce_counter_b0
button_debounce_counter_b0_phys  EQU  0x0BB    ; physical address for movff/lfsr
button_last_scan_b0              EQU  0x0BC    ; phys 0x0BC, bank 0, owner button_last_scan
button_last_scan_b0_op           EQU  0xBC     ; 8-bit f operand for button_last_scan_b0
button_last_scan_b0_phys         EQU  0x0BC    ; physical address for movff/lfsr
button_debounced_prev_b0         EQU  0x0BD    ; phys 0x0BD, bank 0, owner button_debounced_prev
button_debounced_prev_b0_op      EQU  0xBD     ; 8-bit f operand for button_debounced_prev_b0
button_debounced_prev_b0_phys    EQU  0x0BD    ; physical address for movff/lfsr
stock_0BD_b0                     EQU  0x0BD    ; phys 0x0BD, bank 0, owner stock-derived
stock_0BD_b0_op                  EQU  0xBD     ; 8-bit f operand for stock_0BD_b0
stock_0BD_b0_phys                EQU  0x0BD    ; physical address for movff/lfsr
button_debounced_b0              EQU  0x0BE    ; phys 0x0BE, bank 0, owner button_debounced
button_debounced_b0_op           EQU  0xBE     ; 8-bit f operand for button_debounced_b0
button_debounced_b0_phys         EQU  0x0BE    ; physical address for movff/lfsr
display_state_index_b0           EQU  0x0BF    ; phys 0x0BF, bank 0, owner display_state_index
display_state_index_b0_op        EQU  0xBF     ; 8-bit f operand for display_state_index_b0
display_state_index_b0_phys      EQU  0x0BF    ; physical address for movff/lfsr
source_channel_menu_index_b0     EQU  0x0C0    ; phys 0x0C0, bank 0, owner source_channel_menu_index
source_channel_menu_index_b0_op  EQU  0xC0     ; 8-bit f operand for source_channel_menu_index_b0
source_channel_menu_index_b0_phys EQU  0x0C0    ; physical address for movff/lfsr
stock_0C0_b0                     EQU  0x0C0    ; phys 0x0C0, bank 0, owner stock-derived
stock_0C0_b0_op                  EQU  0xC0     ; 8-bit f operand for stock_0C0_b0
stock_0C0_b0_phys                EQU  0x0C0    ; physical address for movff/lfsr
saved_settings_base_b0           EQU  0x0C1    ; phys 0x0C1, bank 0, owner saved_settings_base
saved_settings_base_b0_op        EQU  0xC1     ; 8-bit f operand for saved_settings_base_b0
saved_settings_base_b0_phys      EQU  0x0C1    ; physical address for movff/lfsr
stock_0C7_b0                     EQU  0x0C7    ; phys 0x0C7, bank 0, owner stock-derived
stock_0C7_b0_op                  EQU  0xC7     ; 8-bit f operand for stock_0C7_b0
stock_0C7_b0_phys                EQU  0x0C7    ; physical address for movff/lfsr
stock_0CD_b0                     EQU  0x0CD    ; phys 0x0CD, bank 0, owner stock-derived
stock_0CD_b0_op                  EQU  0xCD     ; 8-bit f operand for stock_0CD_b0
stock_0CD_b0_phys                EQU  0x0CD    ; physical address for movff/lfsr
stock_0D3_b0                     EQU  0x0D3    ; phys 0x0D3, bank 0, owner stock-derived
stock_0D3_b0_op                  EQU  0xD3     ; 8-bit f operand for stock_0D3_b0
stock_0D3_b0_phys                EQU  0x0D3    ; physical address for movff/lfsr
stock_0D9_b0                     EQU  0x0D9    ; phys 0x0D9, bank 0, owner stock-derived
stock_0D9_b0_op                  EQU  0xD9     ; 8-bit f operand for stock_0D9_b0
stock_0D9_b0_phys                EQU  0x0D9    ; physical address for movff/lfsr
stock_0DF_b0                     EQU  0x0DF    ; phys 0x0DF, bank 0, owner stock-derived
stock_0DF_b0_op                  EQU  0xDF     ; 8-bit f operand for stock_0DF_b0
stock_0DF_b0_phys                EQU  0x0DF    ; physical address for movff/lfsr
stock_0E5_b0                     EQU  0x0E5    ; phys 0x0E5, bank 0, owner stock-derived
stock_0E5_b0_op                  EQU  0xE5     ; 8-bit f operand for stock_0E5_b0
stock_0E5_b0_phys                EQU  0x0E5    ; physical address for movff/lfsr
backlight_timeout_selection_b0   EQU  0x0EB    ; phys 0x0EB, bank 0, owner backlight_timeout_selection
backlight_timeout_selection_b0_op EQU  0xEB     ; 8-bit f operand for backlight_timeout_selection_b0
backlight_timeout_selection_b0_phys EQU  0x0EB    ; physical address for movff/lfsr
stock_0EB_b0                     EQU  0x0EB    ; phys 0x0EB, bank 0, owner stock-derived
stock_0EB_b0_op                  EQU  0xEB     ; 8-bit f operand for stock_0EB_b0
stock_0EB_b0_phys                EQU  0x0EB    ; physical address for movff/lfsr
backlight_timeout_threshold_lo_b0 EQU  0x0EC    ; phys 0x0EC, bank 0, owner backlight_timeout_threshold_lo
backlight_timeout_threshold_lo_b0_op EQU  0xEC     ; 8-bit f operand for backlight_timeout_threshold_lo_b0
backlight_timeout_threshold_lo_b0_phys EQU  0x0EC    ; physical address for movff/lfsr
stock_0EC_b0                     EQU  0x0EC    ; phys 0x0EC, bank 0, owner stock-derived
stock_0EC_b0_op                  EQU  0xEC     ; 8-bit f operand for stock_0EC_b0
stock_0EC_b0_phys                EQU  0x0EC    ; physical address for movff/lfsr
backlight_timeout_threshold_mid_lo_b0 EQU  0x0ED    ; phys 0x0ED, bank 0, owner backlight_timeout_threshold_mid_lo
backlight_timeout_threshold_mid_lo_b0_op EQU  0xED     ; 8-bit f operand for backlight_timeout_threshold_mid_lo_b0
backlight_timeout_threshold_mid_lo_b0_phys EQU  0x0ED    ; physical address for movff/lfsr
stock_0ED_b0                     EQU  0x0ED    ; phys 0x0ED, bank 0, owner stock-derived
stock_0ED_b0_op                  EQU  0xED     ; 8-bit f operand for stock_0ED_b0
stock_0ED_b0_phys                EQU  0x0ED    ; physical address for movff/lfsr
backlight_timeout_threshold_mid_hi_b0 EQU  0x0EE    ; phys 0x0EE, bank 0, owner backlight_timeout_threshold_mid_hi
backlight_timeout_threshold_mid_hi_b0_op EQU  0xEE     ; 8-bit f operand for backlight_timeout_threshold_mid_hi_b0
backlight_timeout_threshold_mid_hi_b0_phys EQU  0x0EE    ; physical address for movff/lfsr
stock_0EE_b0                     EQU  0x0EE    ; phys 0x0EE, bank 0, owner stock-derived
stock_0EE_b0_op                  EQU  0xEE     ; 8-bit f operand for stock_0EE_b0
stock_0EE_b0_phys                EQU  0x0EE    ; physical address for movff/lfsr
backlight_timeout_threshold_hi_b0 EQU  0x0EF    ; phys 0x0EF, bank 0, owner backlight_timeout_threshold_hi
backlight_timeout_threshold_hi_b0_op EQU  0xEF     ; 8-bit f operand for backlight_timeout_threshold_hi_b0
backlight_timeout_threshold_hi_b0_phys EQU  0x0EF    ; physical address for movff/lfsr
stock_0EF_b0                     EQU  0x0EF    ; phys 0x0EF, bank 0, owner stock-derived
stock_0EF_b0_op                  EQU  0xEF     ; 8-bit f operand for stock_0EF_b0
stock_0EF_b0_phys                EQU  0x0EF    ; physical address for movff/lfsr
v171_full_sync_step_b1           EQU  0x170    ; phys 0x170, bank 1, owner v171_full_sync_step
v171_full_sync_step_b1_op        EQU  0x70     ; 8-bit f operand for v171_full_sync_step_b1
v171_full_sync_step_b1_phys      EQU  0x170    ; physical address for movff/lfsr
stock_172_b1                     EQU  0x172    ; phys 0x172, bank 1, owner stock-derived
stock_172_b1_op                  EQU  0x72     ; 8-bit f operand for stock_172_b1
stock_172_b1_phys                EQU  0x172    ; physical address for movff/lfsr
v171_preset_bit_snapshot_b1      EQU  0x172    ; phys 0x172, bank 1, owner v171_preset_bit_snapshot
v171_preset_bit_snapshot_b1_op   EQU  0x72     ; 8-bit f operand for v171_preset_bit_snapshot_b1
v171_preset_bit_snapshot_b1_phys EQU  0x172    ; physical address for movff/lfsr
stock_173_b1                     EQU  0x173    ; phys 0x173, bank 1, owner stock-derived
stock_173_b1_op                  EQU  0x73     ; 8-bit f operand for stock_173_b1
stock_173_b1_phys                EQU  0x173    ; physical address for movff/lfsr
v171_diag_pb1_i_b1               EQU  0x180    ; phys 0x180, bank 1, owner v171_diag_pb1_i
v171_diag_pb1_i_b1_op            EQU  0x80     ; 8-bit f operand for v171_diag_pb1_i_b1
v171_diag_pb1_i_b1_phys          EQU  0x180    ; physical address for movff/lfsr
v171_diag_pb1_d_b1               EQU  0x181    ; phys 0x181, bank 1, owner v171_diag_pb1_d
v171_diag_pb1_d_b1_op            EQU  0x81     ; 8-bit f operand for v171_diag_pb1_d_b1
v171_diag_pb1_d_b1_phys          EQU  0x181    ; physical address for movff/lfsr
v171_diag_pb1_s_b1               EQU  0x182    ; phys 0x182, bank 1, owner v171_diag_pb1_s
v171_diag_pb1_s_b1_op            EQU  0x82     ; 8-bit f operand for v171_diag_pb1_s_b1
v171_diag_pb1_s_b1_phys          EQU  0x182    ; physical address for movff/lfsr
v171_diag_pb1_b_b1               EQU  0x183    ; phys 0x183, bank 1, owner v171_diag_pb1_b
v171_diag_pb1_b_b1_op            EQU  0x83     ; 8-bit f operand for v171_diag_pb1_b_b1
v171_diag_pb1_b_b1_phys          EQU  0x183    ; physical address for movff/lfsr
v171_diag_pb1_r_b1               EQU  0x184    ; phys 0x184, bank 1, owner v171_diag_pb1_r
v171_diag_pb1_r_b1_op            EQU  0x84     ; 8-bit f operand for v171_diag_pb1_r_b1
v171_diag_pb1_r_b1_phys          EQU  0x184    ; physical address for movff/lfsr
v171_diag_pb1_a_b1               EQU  0x185    ; phys 0x185, bank 1, owner v171_diag_pb1_a
v171_diag_pb1_a_b1_op            EQU  0x85     ; 8-bit f operand for v171_diag_pb1_a_b1
v171_diag_pb1_a_b1_phys          EQU  0x185    ; physical address for movff/lfsr
v171_diag_pb1_p_b1               EQU  0x186    ; phys 0x186, bank 1, owner v171_diag_pb1_p
v171_diag_pb1_p_b1_op            EQU  0x86     ; 8-bit f operand for v171_diag_pb1_p_b1
v171_diag_pb1_p_b1_phys          EQU  0x186    ; physical address for movff/lfsr
v171_diag_pb1_reset_por_b1       EQU  0x187    ; phys 0x187, bank 1, owner v171_diag_pb1_reset_por
v171_diag_pb1_reset_por_b1_op    EQU  0x87     ; 8-bit f operand for v171_diag_pb1_reset_por_b1
v171_diag_pb1_reset_por_b1_phys  EQU  0x187    ; physical address for movff/lfsr
v171_diag_pb1_reset_bor_b1       EQU  0x188    ; phys 0x188, bank 1, owner v171_diag_pb1_reset_bor
v171_diag_pb1_reset_bor_b1_op    EQU  0x88     ; 8-bit f operand for v171_diag_pb1_reset_bor_b1
v171_diag_pb1_reset_bor_b1_phys  EQU  0x188    ; physical address for movff/lfsr
v171_diag_pb1_reset_wdt_b1       EQU  0x189    ; phys 0x189, bank 1, owner v171_diag_pb1_reset_wdt
v171_diag_pb1_reset_wdt_b1_op    EQU  0x89     ; 8-bit f operand for v171_diag_pb1_reset_wdt_b1
v171_diag_pb1_reset_wdt_b1_phys  EQU  0x189    ; physical address for movff/lfsr
v171_diag_pb1_reset_sw_b1        EQU  0x18A    ; phys 0x18A, bank 1, owner v171_diag_pb1_reset_sw
v171_diag_pb1_reset_sw_b1_op     EQU  0x8A     ; 8-bit f operand for v171_diag_pb1_reset_sw_b1
v171_diag_pb1_reset_sw_b1_phys   EQU  0x18A    ; physical address for movff/lfsr
v171_diag_pb2_i_b1               EQU  0x18B    ; phys 0x18B, bank 1, owner v171_diag_pb2_i
v171_diag_pb2_i_b1_op            EQU  0x8B     ; 8-bit f operand for v171_diag_pb2_i_b1
v171_diag_pb2_i_b1_phys          EQU  0x18B    ; physical address for movff/lfsr
v171_diag_pb2_d_b1               EQU  0x18C    ; phys 0x18C, bank 1, owner v171_diag_pb2_d
v171_diag_pb2_d_b1_op            EQU  0x8C     ; 8-bit f operand for v171_diag_pb2_d_b1
v171_diag_pb2_d_b1_phys          EQU  0x18C    ; physical address for movff/lfsr
v171_diag_pb2_s_b1               EQU  0x18D    ; phys 0x18D, bank 1, owner v171_diag_pb2_s
v171_diag_pb2_s_b1_op            EQU  0x8D     ; 8-bit f operand for v171_diag_pb2_s_b1
v171_diag_pb2_s_b1_phys          EQU  0x18D    ; physical address for movff/lfsr
v171_diag_pb2_b_b1               EQU  0x18E    ; phys 0x18E, bank 1, owner v171_diag_pb2_b
v171_diag_pb2_b_b1_op            EQU  0x8E     ; 8-bit f operand for v171_diag_pb2_b_b1
v171_diag_pb2_b_b1_phys          EQU  0x18E    ; physical address for movff/lfsr
v171_diag_pb2_r_b1               EQU  0x18F    ; phys 0x18F, bank 1, owner v171_diag_pb2_r
v171_diag_pb2_r_b1_op            EQU  0x8F     ; 8-bit f operand for v171_diag_pb2_r_b1
v171_diag_pb2_r_b1_phys          EQU  0x18F    ; physical address for movff/lfsr
v171_diag_pb2_a_b1               EQU  0x190    ; phys 0x190, bank 1, owner v171_diag_pb2_a
v171_diag_pb2_a_b1_op            EQU  0x90     ; 8-bit f operand for v171_diag_pb2_a_b1
v171_diag_pb2_a_b1_phys          EQU  0x190    ; physical address for movff/lfsr
v171_diag_pb2_p_b1               EQU  0x191    ; phys 0x191, bank 1, owner v171_diag_pb2_p
v171_diag_pb2_p_b1_op            EQU  0x91     ; 8-bit f operand for v171_diag_pb2_p_b1
v171_diag_pb2_p_b1_phys          EQU  0x191    ; physical address for movff/lfsr
v171_diag_pb2_reset_por_b1       EQU  0x192    ; phys 0x192, bank 1, owner v171_diag_pb2_reset_por
v171_diag_pb2_reset_por_b1_op    EQU  0x92     ; 8-bit f operand for v171_diag_pb2_reset_por_b1
v171_diag_pb2_reset_por_b1_phys  EQU  0x192    ; physical address for movff/lfsr
v171_diag_pb2_reset_bor_b1       EQU  0x193    ; phys 0x193, bank 1, owner v171_diag_pb2_reset_bor
v171_diag_pb2_reset_bor_b1_op    EQU  0x93     ; 8-bit f operand for v171_diag_pb2_reset_bor_b1
v171_diag_pb2_reset_bor_b1_phys  EQU  0x193    ; physical address for movff/lfsr
v171_diag_pb2_reset_wdt_b1       EQU  0x194    ; phys 0x194, bank 1, owner v171_diag_pb2_reset_wdt
v171_diag_pb2_reset_wdt_b1_op    EQU  0x94     ; 8-bit f operand for v171_diag_pb2_reset_wdt_b1
v171_diag_pb2_reset_wdt_b1_phys  EQU  0x194    ; physical address for movff/lfsr
v171_diag_pb2_reset_sw_b1        EQU  0x195    ; phys 0x195, bank 1, owner v171_diag_pb2_reset_sw
v171_diag_pb2_reset_sw_b1_op     EQU  0x95     ; 8-bit f operand for v171_diag_pb2_reset_sw_b1
v171_diag_pb2_reset_sw_b1_phys   EQU  0x195    ; physical address for movff/lfsr
v171_diag_target_b1              EQU  0x196    ; phys 0x196, bank 1, owner v171_diag_target
v171_diag_target_b1_op           EQU  0x96     ; 8-bit f operand for v171_diag_target_b1
v171_diag_target_b1_phys         EQU  0x196    ; physical address for movff/lfsr
v171_diag_present_b1             EQU  0x197    ; phys 0x197, bank 1, owner v171_diag_present
v171_diag_present_b1_op          EQU  0x97     ; 8-bit f operand for v171_diag_present_b1
v171_diag_present_b1_phys        EQU  0x197    ; physical address for movff/lfsr
v171_diag_poll_lo_b1             EQU  0x198    ; phys 0x198, bank 1, owner v171_diag_poll_lo
v171_diag_poll_lo_b1_op          EQU  0x98     ; 8-bit f operand for v171_diag_poll_lo_b1
v171_diag_poll_lo_b1_phys        EQU  0x198    ; physical address for movff/lfsr
v171_diag_poll_hi_b1             EQU  0x199    ; phys 0x199, bank 1, owner v171_diag_poll_hi
v171_diag_poll_hi_b1_op          EQU  0x99     ; 8-bit f operand for v171_diag_poll_hi_b1
v171_diag_poll_hi_b1_phys        EQU  0x199    ; physical address for movff/lfsr
v171_diag_present_snap_b1        EQU  0x19A    ; phys 0x19A, bank 1, owner v171_diag_present_snap
v171_diag_present_snap_b1_op     EQU  0x9A     ; 8-bit f operand for v171_diag_present_snap_b1
v171_diag_present_snap_b1_phys   EQU  0x19A    ; physical address for movff/lfsr
v171_diag_lcd_pad_count_b1       EQU  0x19B    ; phys 0x19B, bank 1, owner v171_diag_lcd_pad_count
v171_diag_lcd_pad_count_b1_op    EQU  0x9B     ; 8-bit f operand for v171_diag_lcd_pad_count_b1
v171_diag_lcd_pad_count_b1_phys  EQU  0x19B    ; physical address for movff/lfsr
v171_diag_flags_b1               EQU  0x19C    ; phys 0x19C, bank 1, owner v171_diag_flags
v171_diag_flags_b1_op            EQU  0x9C     ; 8-bit f operand for v171_diag_flags_b1
v171_diag_flags_b1_phys          EQU  0x19C    ; physical address for movff/lfsr
v171_diag_reset_seen_b1          EQU  0x19D    ; phys 0x19D, bank 1, owner v171_diag_reset_seen
v171_diag_reset_seen_b1_op       EQU  0x9D     ; 8-bit f operand for v171_diag_reset_seen_b1
v171_diag_reset_seen_b1_phys     EQU  0x19D    ; physical address for movff/lfsr
v171_diag_reset_target_b1        EQU  0x19E    ; phys 0x19E, bank 1, owner v171_diag_reset_target
v171_diag_reset_target_b1_op     EQU  0x9E     ; 8-bit f operand for v171_diag_reset_target_b1
v171_diag_reset_target_b1_phys   EQU  0x19E    ; physical address for movff/lfsr
v171_diag_reset_timeout_b1       EQU  0x19F    ; phys 0x19F, bank 1, owner v171_diag_reset_timeout
v171_diag_reset_timeout_b1_op    EQU  0x9F     ; 8-bit f operand for v171_diag_reset_timeout_b1
v171_diag_reset_timeout_b1_phys  EQU  0x19F    ; physical address for movff/lfsr
stock_1A0_b1                     EQU  0x1A0    ; phys 0x1A0, bank 1, owner stock-derived
stock_1A0_b1_op                  EQU  0xA0     ; 8-bit f operand for stock_1A0_b1
stock_1A0_b1_phys                EQU  0x1A0    ; physical address for movff/lfsr
v171_tx_saturate_count_b1        EQU  0x1AD    ; phys 0x1AD, bank 1, owner v171_tx_saturate_count
v171_tx_saturate_count_b1_op     EQU  0xAD     ; 8-bit f operand for v171_tx_saturate_count_b1
v171_tx_saturate_count_b1_phys   EQU  0x1AD    ; physical address for movff/lfsr
v171_diag_runtime_target_b1      EQU  0x1AE    ; phys 0x1AE, bank 1, owner v171_diag_runtime_target
v171_diag_runtime_target_b1_op   EQU  0xAE     ; 8-bit f operand for v171_diag_runtime_target_b1
v171_diag_runtime_target_b1_phys EQU  0x1AE    ; physical address for movff/lfsr
v171_diag_runtime_timeout_b1     EQU  0x1AF    ; phys 0x1AF, bank 1, owner v171_diag_runtime_timeout
v171_diag_runtime_timeout_b1_op  EQU  0xAF     ; 8-bit f operand for v171_diag_runtime_timeout_b1
v171_diag_runtime_timeout_b1_phys EQU  0x1AF    ; physical address for movff/lfsr
v171_health_age_pb1_b1           EQU  0x1B0    ; phys 0x1B0, bank 1, owner v171_health_age_pb1
v171_health_age_pb1_b1_op        EQU  0xB0     ; 8-bit f operand for v171_health_age_pb1_b1
v171_health_age_pb1_b1_phys      EQU  0x1B0    ; physical address for movff/lfsr
v171_health_age_pb2_b1           EQU  0x1B1    ; phys 0x1B1, bank 1, owner v171_health_age_pb2
v171_health_age_pb2_b1_op        EQU  0xB1     ; 8-bit f operand for v171_health_age_pb2_b1
v171_health_age_pb2_b1_phys      EQU  0x1B1    ; physical address for movff/lfsr
v171_health_seen_mask_b1         EQU  0x1B2    ; phys 0x1B2, bank 1, owner v171_health_seen_mask
v171_health_seen_mask_b1_op      EQU  0xB2     ; 8-bit f operand for v171_health_seen_mask_b1
v171_health_seen_mask_b1_phys    EQU  0x1B2    ; physical address for movff/lfsr
v171_health_flags_b1             EQU  0x1B3    ; phys 0x1B3, bank 1, owner v171_health_flags
v171_health_flags_b1_op          EQU  0xB3     ; 8-bit f operand for v171_health_flags_b1
v171_health_flags_b1_phys        EQU  0x1B3    ; physical address for movff/lfsr
v171_health_poll_target_b1       EQU  0x1B4    ; phys 0x1B4, bank 1, owner v171_health_poll_target
v171_health_poll_target_b1_op    EQU  0xB4     ; 8-bit f operand for v171_health_poll_target_b1
v171_health_poll_target_b1_phys  EQU  0x1B4    ; physical address for movff/lfsr
v171_health_tick_div_b1          EQU  0x1B5    ; phys 0x1B5, bank 1, owner v171_health_tick_div
v171_health_tick_div_b1_op       EQU  0xB5     ; 8-bit f operand for v171_health_tick_div_b1
v171_health_tick_div_b1_phys     EQU  0x1B5    ; physical address for movff/lfsr
v171_health_pending_ticks_b1     EQU  0x1B6    ; phys 0x1B6, bank 1, owner v171_health_pending_ticks
v171_health_pending_ticks_b1_op  EQU  0xB6     ; 8-bit f operand for v171_health_pending_ticks_b1
v171_health_pending_ticks_b1_phys EQU  0x1B6    ; physical address for movff/lfsr
v171_health_suffix_mask_b1       EQU  0x1B7    ; phys 0x1B7, bank 1, owner v171_health_suffix_mask
v171_health_suffix_mask_b1_op    EQU  0xB7     ; 8-bit f operand for v171_health_suffix_mask_b1
v171_health_suffix_mask_b1_phys  EQU  0x1B7    ; physical address for movff/lfsr
v171_diag_effective_target_b1    EQU  0x1B8    ; phys 0x1B8, bank 1, owner v171_diag_effective_target
v171_diag_effective_target_b1_op EQU  0xB8     ; 8-bit f operand for v171_diag_effective_target_b1
v171_diag_effective_target_b1_phys EQU  0x1B8    ; physical address for movff/lfsr
v171_health_age_tmp_b1           EQU  0x1B9    ; phys 0x1B9, bank 1, owner v171_health_age_tmp
v171_health_age_tmp_b1_op        EQU  0xB9     ; 8-bit f operand for v171_health_age_tmp_b1
v171_health_age_tmp_b1_phys      EQU  0x1B9    ; physical address for movff/lfsr
input_split_flags_b1             EQU  0x1BA    ; phys 0x1BA, bank 1, owner input_split_flags
input_split_flags_b1_op          EQU  0xBA     ; 8-bit f operand for input_split_flags_b1
input_split_flags_b1_phys        EQU  0x1BA    ; physical address for movff/lfsr
input_intent_pb2_b1              EQU  0x1BB    ; phys 0x1BB, bank 1, owner input_intent_pb2
input_intent_pb2_b1_op           EQU  0xBB     ; 8-bit f operand for input_intent_pb2_b1
input_intent_pb2_b1_phys         EQU  0x1BB    ; physical address for movff/lfsr
input_send_target_b1             EQU  0x1BC    ; phys 0x1BC, bank 1, owner input_send_target
input_send_target_b1_op          EQU  0xBC     ; 8-bit f operand for input_send_target_b1
input_send_target_b1_phys        EQU  0x1BC    ; physical address for movff/lfsr
input_pending_pb2_b1             EQU  0x1BD    ; phys 0x1BD, bank 1, owner input_pending_pb2
input_pending_pb2_b1_op          EQU  0xBD     ; 8-bit f operand for input_pending_pb2_b1
input_pending_pb2_b1_phys        EQU  0x1BD    ; physical address for movff/lfsr
v171_diag_render_pb_index_b1     EQU  0x1CD    ; phys 0x1CD, bank 1, owner v171_diag_render_pb_index
v171_diag_render_pb_index_b1_op  EQU  0xCD     ; 8-bit f operand for v171_diag_render_pb_index_b1
v171_diag_render_pb_index_b1_phys EQU  0x1CD    ; physical address for movff/lfsr
v171_diag_render_count_b1        EQU  0x1CE    ; phys 0x1CE, bank 1, owner v171_diag_render_count
v171_diag_render_count_b1_op     EQU  0xCE     ; 8-bit f operand for v171_diag_render_count_b1
v171_diag_render_count_b1_phys   EQU  0x1CE    ; physical address for movff/lfsr
v171_diag_render_emitted_b1      EQU  0x1CF    ; phys 0x1CF, bank 1, owner v171_diag_render_emitted
v171_diag_render_emitted_b1_op   EQU  0xCF     ; 8-bit f operand for v171_diag_render_emitted_b1
v171_diag_render_emitted_b1_phys EQU  0x1CF    ; physical address for movff/lfsr
v171_diag_render_walk_idx_b1     EQU  0x1D0    ; phys 0x1D0, bank 1, owner v171_diag_render_walk_idx
v171_diag_render_walk_idx_b1_op  EQU  0xD0     ; 8-bit f operand for v171_diag_render_walk_idx_b1
v171_diag_render_walk_idx_b1_phys EQU  0x1D0    ; physical address for movff/lfsr
v171_diag_render_value_b1        EQU  0x1D1    ; phys 0x1D1, bank 1, owner v171_diag_render_value
v171_diag_render_value_b1_op     EQU  0xD1     ; 8-bit f operand for v171_diag_render_value_b1
v171_diag_render_value_b1_phys   EQU  0x1D1    ; physical address for movff/lfsr
v171_diag_render_skipped_b1      EQU  0x1D2    ; phys 0x1D2, bank 1, owner v171_diag_render_skipped
v171_diag_render_skipped_b1_op   EQU  0xD2     ; 8-bit f operand for v171_diag_render_skipped_b1
v171_diag_render_skipped_b1_phys EQU  0x1D2    ; physical address for movff/lfsr
v171_diag_render_letter_tmp_b1   EQU  0x1D3    ; phys 0x1D3, bank 1, owner v171_diag_render_letter_tmp
v171_diag_render_letter_tmp_b1_op EQU  0xD3     ; 8-bit f operand for v171_diag_render_letter_tmp_b1
v171_diag_render_letter_tmp_b1_phys EQU  0x1D3    ; physical address for movff/lfsr
v171_diag_render_abnormal_b1     EQU  0x1D4    ; phys 0x1D4, bank 1, owner v171_diag_render_abnormal
v171_diag_render_abnormal_b1_op  EQU  0xD4     ; 8-bit f operand for v171_diag_render_abnormal_b1
v171_diag_render_abnormal_b1_phys EQU  0x1D4    ; physical address for movff/lfsr
v172_fname_cache_b2              EQU  0x220    ; phys 0x220, bank 2, owner v172_fname_cache
v172_fname_cache_b2_op           EQU  0x20     ; 8-bit f operand for v172_fname_cache_b2
v172_fname_cache_b2_phys         EQU  0x220    ; physical address for movff/lfsr
v172_fname_len_b2                EQU  0x23E    ; phys 0x23E, bank 2, owner v172_fname_len
v172_fname_len_b2_op             EQU  0x3E     ; 8-bit f operand for v172_fname_len_b2
v172_fname_len_b2_phys           EQU  0x23E    ; physical address for movff/lfsr
v172_fname_expected_len_b2       EQU  0x23F    ; phys 0x23F, bank 2, owner v172_fname_expected_len
v172_fname_expected_len_b2_op    EQU  0x3F     ; 8-bit f operand for v172_fname_expected_len_b2
v172_fname_expected_len_b2_phys  EQU  0x23F    ; physical address for movff/lfsr
v172_fname_flags_b2              EQU  0x240    ; phys 0x240, bank 2, owner v172_fname_flags
v172_fname_flags_b2_op           EQU  0x40     ; 8-bit f operand for v172_fname_flags_b2
v172_fname_flags_b2_phys         EQU  0x240    ; physical address for movff/lfsr
v172_fname_gen_b2                EQU  0x241    ; phys 0x241, bank 2, owner v172_fname_gen
v172_fname_gen_b2_op             EQU  0x41     ; 8-bit f operand for v172_fname_gen_b2
v172_fname_gen_b2_phys           EQU  0x241    ; physical address for movff/lfsr
v172_fname_id_b2                 EQU  0x242    ; phys 0x242, bank 2, owner v172_fname_id
v172_fname_id_b2_op              EQU  0x42     ; 8-bit f operand for v172_fname_id_b2
v172_fname_id_b2_phys            EQU  0x242    ; physical address for movff/lfsr
v172_fname_scroll_off_b2         EQU  0x243    ; phys 0x243, bank 2, owner v172_fname_scroll_off
v172_fname_scroll_off_b2_op      EQU  0x43     ; 8-bit f operand for v172_fname_scroll_off_b2
v172_fname_scroll_off_b2_phys    EQU  0x243    ; physical address for movff/lfsr
v172_fname_scroll_hold_b2        EQU  0x244    ; phys 0x244, bank 2, owner v172_fname_scroll_hold
v172_fname_scroll_hold_b2_op     EQU  0x44     ; 8-bit f operand for v172_fname_scroll_hold_b2
v172_fname_scroll_hold_b2_phys   EQU  0x244    ; physical address for movff/lfsr
v172_diag_id_pb1_major_b2        EQU  0x245    ; phys 0x245, bank 2, owner v172_diag_id_pb1_major
v172_diag_id_pb1_major_b2_op     EQU  0x45     ; 8-bit f operand for v172_diag_id_pb1_major_b2
v172_diag_id_pb1_major_b2_phys   EQU  0x245    ; physical address for movff/lfsr
v172_diag_id_pb1_minor_b2        EQU  0x246    ; phys 0x246, bank 2, owner v172_diag_id_pb1_minor
v172_diag_id_pb1_minor_b2_op     EQU  0x46     ; 8-bit f operand for v172_diag_id_pb1_minor_b2
v172_diag_id_pb1_minor_b2_phys   EQU  0x246    ; physical address for movff/lfsr
v172_diag_id_pb1_rev_b2          EQU  0x247    ; phys 0x247, bank 2, owner v172_diag_id_pb1_rev
v172_diag_id_pb1_rev_b2_op       EQU  0x47     ; 8-bit f operand for v172_diag_id_pb1_rev_b2
v172_diag_id_pb1_rev_b2_phys     EQU  0x247    ; physical address for movff/lfsr
v172_diag_id_pb2_major_b2        EQU  0x248    ; phys 0x248, bank 2, owner v172_diag_id_pb2_major
v172_diag_id_pb2_major_b2_op     EQU  0x48     ; 8-bit f operand for v172_diag_id_pb2_major_b2
v172_diag_id_pb2_major_b2_phys   EQU  0x248    ; physical address for movff/lfsr
v172_diag_id_pb2_minor_b2        EQU  0x249    ; phys 0x249, bank 2, owner v172_diag_id_pb2_minor
v172_diag_id_pb2_minor_b2_op     EQU  0x49     ; 8-bit f operand for v172_diag_id_pb2_minor_b2
v172_diag_id_pb2_minor_b2_phys   EQU  0x249    ; physical address for movff/lfsr
v172_diag_id_pb2_rev_b2          EQU  0x24A    ; phys 0x24A, bank 2, owner v172_diag_id_pb2_rev
v172_diag_id_pb2_rev_b2_op       EQU  0x4A     ; 8-bit f operand for v172_diag_id_pb2_rev_b2
v172_diag_id_pb2_rev_b2_phys     EQU  0x24A    ; physical address for movff/lfsr
v172_diag_id_valid_mask_b2       EQU  0x24B    ; phys 0x24B, bank 2, owner v172_diag_id_valid_mask
v172_diag_id_valid_mask_b2_op    EQU  0x4B     ; 8-bit f operand for v172_diag_id_valid_mask_b2
v172_diag_id_valid_mask_b2_phys  EQU  0x24B    ; physical address for movff/lfsr
v172_diag_id_seen_mask_b2        EQU  0x24C    ; phys 0x24C, bank 2, owner v172_diag_id_seen_mask
v172_diag_id_seen_mask_b2_op     EQU  0x4C     ; 8-bit f operand for v172_diag_id_seen_mask_b2
v172_diag_id_seen_mask_b2_phys   EQU  0x24C    ; physical address for movff/lfsr
v172_diag_id_pending_id_b2       EQU  0x24D    ; phys 0x24D, bank 2, owner v172_diag_id_pending_id
v172_diag_id_pending_id_b2_op    EQU  0x4D     ; 8-bit f operand for v172_diag_id_pending_id_b2
v172_diag_id_pending_id_b2_phys  EQU  0x24D    ; physical address for movff/lfsr
v172_diag_id_flags_b2            EQU  0x24E    ; phys 0x24E, bank 2, owner v172_diag_id_flags
v172_diag_id_flags_b2_op         EQU  0x4E     ; 8-bit f operand for v172_diag_id_flags_b2
v172_diag_id_flags_b2_phys       EQU  0x24E    ; physical address for movff/lfsr
v172_diag_id_timeout_b2          EQU  0x24F    ; phys 0x24F, bank 2, owner v172_diag_id_timeout
v172_diag_id_timeout_b2_op       EQU  0x4F     ; 8-bit f operand for v172_diag_id_timeout_b2
v172_diag_id_timeout_b2_phys     EQU  0x24F    ; physical address for movff/lfsr
v172_diag_id_next_gen_b2         EQU  0x250    ; phys 0x250, bank 2, owner v172_diag_id_next_gen
v172_diag_id_next_gen_b2_op      EQU  0x50     ; 8-bit f operand for v172_diag_id_next_gen_b2
v172_diag_id_next_gen_b2_phys    EQU  0x250    ; physical address for movff/lfsr
v172_diag_id_expected_cmd_b2     EQU  0x251    ; phys 0x251, bank 2, owner v172_diag_id_expected_cmd
v172_diag_id_expected_cmd_b2_op  EQU  0x51     ; 8-bit f operand for v172_diag_id_expected_cmd_b2
v172_diag_id_expected_cmd_b2_phys EQU  0x251    ; physical address for movff/lfsr
v172_diag_id_tmp_major_b2        EQU  0x252    ; phys 0x252, bank 2, owner v172_diag_id_tmp_major
v172_diag_id_tmp_major_b2_op     EQU  0x52     ; 8-bit f operand for v172_diag_id_tmp_major_b2
v172_diag_id_tmp_major_b2_phys   EQU  0x252    ; physical address for movff/lfsr
v172_diag_id_tmp_minor_b2        EQU  0x253    ; phys 0x253, bank 2, owner v172_diag_id_tmp_minor
v172_diag_id_tmp_minor_b2_op     EQU  0x53     ; 8-bit f operand for v172_diag_id_tmp_minor_b2
v172_diag_id_tmp_minor_b2_phys   EQU  0x253    ; physical address for movff/lfsr
v172_diag_id_tmp_rev_hi_b2       EQU  0x254    ; phys 0x254, bank 2, owner v172_diag_id_tmp_rev_hi
v172_diag_id_tmp_rev_hi_b2_op    EQU  0x54     ; 8-bit f operand for v172_diag_id_tmp_rev_hi_b2
v172_diag_id_tmp_rev_hi_b2_phys  EQU  0x254    ; physical address for movff/lfsr
v172_fname_scroll_div_lo_b2      EQU  0x255    ; phys 0x255, bank 2, owner v172_fname_scroll_div_lo
v172_fname_scroll_div_lo_b2_op   EQU  0x55     ; 8-bit f operand for v172_fname_scroll_div_lo_b2
v172_fname_scroll_div_lo_b2_phys EQU  0x255    ; physical address for movff/lfsr
v172_fname_scroll_div_hi_b2      EQU  0x256    ; phys 0x256, bank 2, owner v172_fname_scroll_div_hi
v172_fname_scroll_div_hi_b2_op   EQU  0x56     ; 8-bit f operand for v172_fname_scroll_div_hi_b2
v172_fname_scroll_div_hi_b2_phys EQU  0x256    ; physical address for movff/lfsr
v172_fname_deadline_lo_b2        EQU  0x257    ; phys 0x257, bank 2, owner v172_fname_deadline_lo
v172_fname_deadline_lo_b2_op     EQU  0x57     ; 8-bit f operand for v172_fname_deadline_lo_b2
v172_fname_deadline_lo_b2_phys   EQU  0x257    ; physical address for movff/lfsr
v172_fname_deadline_hi_b2        EQU  0x258    ; phys 0x258, bank 2, owner v172_fname_deadline_hi
v172_fname_deadline_hi_b2_op     EQU  0x58     ; 8-bit f operand for v172_fname_deadline_hi_b2
v172_fname_deadline_hi_b2_phys   EQU  0x258    ; physical address for movff/lfsr
v172_fname_render_col_b2         EQU  0x259    ; phys 0x259, bank 2, owner v172_fname_render_col
v172_fname_render_col_b2_op      EQU  0x59     ; 8-bit f operand for v172_fname_render_col_b2
v172_fname_render_col_b2_phys    EQU  0x259    ; physical address for movff/lfsr
v172_fname_render_off_b2         EQU  0x25A    ; phys 0x25A, bank 2, owner v172_fname_render_off
v172_fname_render_off_b2_op      EQU  0x5A     ; 8-bit f operand for v172_fname_render_off_b2
v172_fname_render_off_b2_phys    EQU  0x25A    ; physical address for movff/lfsr
v172_fname_row0_status_snap_b2   EQU  0x25B    ; phys 0x25B, bank 2, owner v172_fname_row0_status_snap
v172_fname_row0_status_snap_b2_op EQU  0x5B     ; 8-bit f operand for v172_fname_row0_status_snap_b2
v172_fname_row0_status_snap_b2_phys EQU  0x25B    ; physical address for movff/lfsr
v172_fname_tmp_b2                EQU  0x25C    ; phys 0x25C, bank 2, owner v172_fname_tmp
v172_fname_tmp_b2_op             EQU  0x5C     ; 8-bit f operand for v172_fname_tmp_b2
v172_fname_tmp_b2_phys           EQU  0x25C    ; physical address for movff/lfsr
v172_fname_retry_b2              EQU  0x25D    ; phys 0x25D, bank 2, owner v172_fname_retry
v172_fname_retry_b2_op           EQU  0x5D     ; 8-bit f operand for v172_fname_retry_b2
v172_fname_retry_b2_phys         EQU  0x25D    ; physical address for movff/lfsr
v173_row0_reassert_div_b2        EQU  0x25E    ; phys 0x25E, bank 2, owner v173_row0_reassert_div
v173_row0_reassert_div_b2_op     EQU  0x5E     ; 8-bit f operand for v173_row0_reassert_div_b2
v173_row0_reassert_div_b2_phys   EQU  0x25E    ; physical address for movff/lfsr
v173_isr_decode_save_b2          EQU  0x260    ; phys 0x260, bank 2, owner v173_isr_decode_save
v173_isr_decode_save_b2_op       EQU  0x60     ; 8-bit f operand for v173_isr_decode_save_b2
v173_isr_decode_save_b2_phys     EQU  0x260    ; physical address for movff/lfsr
v173_mute_reassert_div_b2        EQU  0x26B    ; phys 0x26B, bank 2, owner v173_mute_reassert_div
v173_mute_reassert_div_b2_op     EQU  0x6B     ; 8-bit f operand for v173_mute_reassert_div_b2
v173_mute_reassert_div_b2_phys   EQU  0x26B    ; physical address for movff/lfsr
v173_diag_id_pb1_rev_hi_b2       EQU  0x26C    ; phys 0x26C, bank 2, owner v173_diag_id_pb1_rev_hi
v173_diag_id_pb1_rev_hi_b2_op    EQU  0x6C     ; 8-bit f operand for v173_diag_id_pb1_rev_hi_b2
v173_diag_id_pb1_rev_hi_b2_phys  EQU  0x26C    ; physical address for movff/lfsr
v173_diag_id_pb2_rev_hi_b2       EQU  0x26D    ; phys 0x26D, bank 2, owner v173_diag_id_pb2_rev_hi
v173_diag_id_pb2_rev_hi_b2_op    EQU  0x6D     ; 8-bit f operand for v173_diag_id_pb2_rev_hi_b2
v173_diag_id_pb2_rev_hi_b2_phys  EQU  0x26D    ; physical address for movff/lfsr
v173_diag_id_tmp_rev_lo_b2       EQU  0x26E    ; phys 0x26E, bank 2, owner v173_diag_id_tmp_rev_lo
v173_diag_id_tmp_rev_lo_b2_op    EQU  0x6E     ; 8-bit f operand for v173_diag_id_tmp_rev_lo_b2
v173_diag_id_tmp_rev_lo_b2_phys  EQU  0x26E    ; physical address for movff/lfsr
; --- RAM bank safety generated aliases: END ---

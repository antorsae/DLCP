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

; --- V1.71 Layer 5 Phase B: CONTROL diagnostics page ---
; Per-PB cache of the seven BF/2N reply payloads from V3.2+ MAIN's
; cmd 0x21 diagnostics burst.  Each payload byte carries one counter
; in the LOW nibble (high nibble = 0).  An earlier draft packed two
; counters per byte but produced data >= 0x80 for any high counter
; > 7, which the chain forwarder treats as a route byte (corrupting
; PB2's reply specifically — PB1's reply path is direct).  See
; docs/V163B_DIAGNOSTICS_MENU_SPEC.md.
;
; Cache ordering matches the BF/2N replies:
;   *_i  = diag_i  (BF/21) — I2C transport faults
;   *_d  = diag_d  (BF/22) — DSP fault episodes
;   *_s  = diag_s  (BF/23) — standby dispatches
;   *_b  = diag_b  (BF/24) — bring-up dispatches
;   *_r  = diag_r  (BF/25) — recovery branch entries
;   *_a  = diag_a  (BF/26) — AN0-triggered standby
;   *_p  = diag_p  (BF/27) — RA1 edge events (LAST FRAME)
;
; All cache slots live in BANK 1 (physical 0x180..0x18D).  The EQU
; values are BANKED-form 8-bit operands; callers must `movlb 0x01`
; before access.  gpsim CLI reads via the PHYSICAL address — e.g.
; `reg(0x180)` not `reg(0x080)` (which would be the bank-0 GPR slot).
;
; Cache survives ordinary firmware reset / reconnect (uninitialized
; RAM keeps its value through soft reset on PIC18); cleared only on
; POR/BOR, the same gate as the MAIN-side diag block.
v171_diag_pb1_i            equ  0x080
v171_diag_pb1_d            equ  0x081
v171_diag_pb1_s            equ  0x082
v171_diag_pb1_b            equ  0x083
v171_diag_pb1_r            equ  0x084
v171_diag_pb1_a            equ  0x085
v171_diag_pb1_p            equ  0x086
v171_diag_pb2_i            equ  0x087
v171_diag_pb2_d            equ  0x088
v171_diag_pb2_s            equ  0x089
v171_diag_pb2_b            equ  0x08A
v171_diag_pb2_r            equ  0x08B
v171_diag_pb2_a            equ  0x08C
v171_diag_pb2_p            equ  0x08D

; Poll-state cells (also BANK 1):
;   v171_diag_target   = 0 → query PB1 next, 1 → query PB2 next
;   v171_diag_present  = bit0 set when PB1 has ever replied,
;                         bit1 set when PB2 has ever replied
;                         (used to render "n/a" for never-seen PBs)
;   v171_diag_poll_lo/hi = 16-bit countdown until the next query
;                          enqueue.  Decremented once per
;                          v171_diag_screen tick.  Reset to
;                          V171_DIAG_POLL_RELOAD on each query.
v171_diag_target           equ  0x08E
v171_diag_present          equ  0x08F
v171_diag_poll_lo          equ  0x090
v171_diag_poll_hi          equ  0x091
; Snapshot of v171_diag_present at the last screen draw — used by
; v171_diag_check_redraw to fire a screen redraw only when the
; present mask actually changed.  Lives in BANK 1 (not in the
; access-bank ram_0x005 scratch cell that other routines clobber).
v171_diag_present_snap     equ  0x092
; LCD pad-loop counter for the n/a render path.  Must NOT live in
; access-bank ram_0x004 because lcd_char_write's internal helper
; routines clobber it (movff FSR0H, ram_0x004 in
; control_core_service_*).  Callers that use this cell must
; movlb 0x01 around access AND reload BSR after every
; lcd_char_write call (which can change BSR internally).
v171_diag_lcd_pad_count    equ  0x093

; Poll cadence reload value.  Each v171_diag_screen tick decrements
; the 16-bit countdown by 1; with display_loop_iteration on the K20
; control loop the per-tick wall time is on the order of single-digit
; ms.  Spec calls for "500 ms to 1 s cadence is sufficient".
; 0x0080 ticks (~1 s cadence) gives the firmware enough time for one
; full query/reply round-trip before the next cadence expires.
; A faster cadence (e.g. 0x10) was tried and races against the
; reply arrival: the second cadence toggles target before the
; in-flight reply lands, corrupting the cache index.
V171_DIAG_POLL_RELOAD_LO   equ  0x80
V171_DIAG_POLL_RELOAD_HI   equ  0x00

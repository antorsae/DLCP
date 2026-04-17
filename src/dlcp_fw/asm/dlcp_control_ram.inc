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
; ``button_last_scan`` lives at 0x0BC in stock — V1.63b co-opted that
; slot for the BF/08 fault byte.  V1.71 keeps the same address so the
; wire-format is V1.63b-identical (tests that probe 0x0BC continue to
; work).  ``button_last_scan`` logic in stock preserves its semantics
; during non-fault windows since the fault byte is only written on a
; BF/08 RX event.
bf08_fault_byte            equ  0x0BC   ; collision with button_last_scan by design

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

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

; --- V1.71 additions (not used by V1.7 byte-identical source) ---
; Equates intentionally left for the V1.71 edits to place in free GPR slots
; after an audit against ``button_last_scan`` (0x0BC) overlap risk noted in
; docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md Phase 1 step 2.

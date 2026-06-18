    LIST P=18F2455
    #include <p18f2455.inc>
    #include "dlcp_main_ram.inc"


; ---------------------------------------------------------------------------
; Configuration Bits
; ---------------------------------------------------------------------------
    __CONFIG  _CONFIG1L, 0x3A
    __CONFIG  _CONFIG1H, 0x46
    __CONFIG  _CONFIG2L, 0x3E
    __CONFIG  _CONFIG2H, 0x1E
    __CONFIG  _CONFIG3H, 0x00
    __CONFIG  _CONFIG4L, 0x80
    __CONFIG  _CONFIG5L, 0x0F
    __CONFIG  _CONFIG5H, 0xC0
    __CONFIG  _CONFIG6L, 0x0F
    __CONFIG  _CONFIG6H, 0xA0
    __CONFIG  _CONFIG7L, 0x0F
    __CONFIG  _CONFIG7H, 0x40

; ---------------------------------------------------------------------------
; App Entry (0x1000)
; ---------------------------------------------------------------------------
    org 0x1000
    goto        app_entry__jump_to_cold_init
    dw          0xFFFF
    dw          0xFFFF
    movff       FSR2L, isr_save_fsr2l
    movff       FSR2H, isr_save_fsr2h
    call        isr_high_priority_dispatch, 0x1
app_entry__jump_to_cold_init:
    goto        boot_cold_init__clear_ram_and_runtime_state

; ---------------------------------------------------------------------------
; USB Descriptors and Data Tables (0x1018-0x10AB)
; ---------------------------------------------------------------------------
hex_lookup_sentinel:  ; NUL byte sentinel
    dw  0x3000, 0x3231, 0x3433, 0x3635, 0x3837, 0x4139, 0x4342, 0x4544
    dw  0xA646, 0x9A72
usb_config_descriptor:  ; USB Configuration Descriptor
    dw  0x0209, 0x0029, 0x0101, 0x8000, 0x0932, 0x0004, 0x0200, 0x0003
    dw  0x0000
usb_hid_descriptor:  ; USB HID Descriptor
    dw  0x2109, 0x0111, 0x0100, 0x1D22, 0x0700, 0x8105, 0x4003, 0x0100
usb_ep1_out_descriptor:  ; Endpoint 1 OUT (interrupt)
    dw  0x0507, 0x0301, 0x0040, 0x0601, 0xFF00, 0x0109, 0x01A1, 0x0119
    dw  0x4029, 0x0015, 0xFF26, 0x7500, 0x9508, 0x8140, 0x1900, 0x2901
    dw  0x9140, 0xC000
usb_string_desc_1:  ; String Descriptor 1: "Hypex BV"
    dw  0x0316, 0x0048, 0x0079, 0x0070, 0x0065, 0x0078, 0x0020, 0x0042
    dw  0x0056, 0x0000, 0x0000
usb_device_descriptor:  ; USB Device Descriptor
    dw  0x0112, 0x0200, 0x0000, 0x0800, 0x04D8, 0xFF89, 0x0001, 0x0201
    dw  0x0100
usb_string_desc_2:  ; String Descriptor 2: "DLCP"
    dw  0x030C, 0x0044, 0x004C, 0x0043, 0x0050, 0x0000
usb_string_desc_0:  ; String Descriptor 0: LANGID
    dw  0x0304, 0x0409
usb_data_pad:  ; Padding to code boundary
    dw  0x0000

; Sub-labels at odd byte addresses (EQU offsets)
hex_lookup_table  EQU  hex_lookup_sentinel + 0x1  ; ASCII hex digits: 0-9, A-F
string_desc_ptr_table  EQU  hex_lookup_sentinel + 0x11  ; String descriptor offset table
usb_interface_descriptor  EQU  usb_config_descriptor + 0x9  ; USB Interface Descriptor
usb_ep1_in_descriptor  EQU  usb_hid_descriptor + 0x9  ; Endpoint 1 IN (interrupt)
usb_hid_report_descriptor  EQU  usb_ep1_out_descriptor + 0x7  ; HID Report Descriptor

; ---------------------------------------------------------------------------
; Application Code
; ---------------------------------------------------------------------------


; ---------------------------------------------------------------------------
; Function: hid_command_dispatch
; Address : 0x10AC
; Notes   : USB HID command decode and top-level command/state dispatch.
; ---------------------------------------------------------------------------
hid_command_dispatch:
    movff       WREG, i2c_coeff_2
    lfsr        FSR2, 0x01ED
    lfsr        FSR1, 0x004D
    movlw       0x07
flow_hid_command_dispatch_10ba:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_hid_command_dispatch_10ba
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x42
    bnz         hid_command_dispatch__clear_relay_session_before_decode
    bra         hid_command_dispatch__decode_opcode_xor_chain
hid_command_dispatch__clear_relay_session_before_decode:
    movlb       0x0
    clrf        ram_0x0CB, BANKED
    bra         hid_command_dispatch__decode_opcode_xor_chain
hid_command_dispatch__handle_opcode_03:
    movff       ram_0x11B, ram_0x097
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x09
    bnz         hid_command_dispatch__probe_config_clear_subcommand
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
hid_command_dispatch__copy_sparse_config_byte_loop:
    rcall       hid_out_payload_index_to_fsr2
    movf        INDF2, W, ACCESS
    bz          hid_command_dispatch__fill_sparse_config_byte_ff
    rcall       hid_out_payload_index_to_fsr2
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x02
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         hid_command_dispatch__advance_sparse_config_index
hid_command_dispatch__fill_sparse_config_byte_ff:
    rcall       hid_config_fill_ff_at_index
hid_command_dispatch__advance_sparse_config_index:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         hid_command_dispatch__copy_sparse_config_byte_loop
hid_command_dispatch__probe_config_clear_subcommand:
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x0A
    bnz         hid_command_dispatch__stage_opcode03_status
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
hid_command_dispatch__fill_config_range_ff:
    rcall       hid_config_fill_ff_at_index
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         hid_command_dispatch__fill_config_range_ff
hid_command_dispatch__stage_opcode03_status:
    movlw       0x03
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movff       ram_0x11B, ram_0x0C2
    bsf         ram_0x0BD, 5, BANKED
hid_command_dispatch__arm_timer0_after_update:
    call        timer0_rearm_50ms_heartbeat, 0x0
hid_command_dispatch__delay_before_status_response:
    call        timer3_blocking_delay_1ms, 0x0
hid_command_dispatch__emit_status_response:
    call        stage_hid_ep1_in_report_from_selector, 0x0
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__handle_opcode_04:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         hid_command_dispatch__probe_opcode04_payload_mode
    movff       ram_0x11C, ram_0x0B7
    bra         hid_command_dispatch__dispatch_opcode04_action
hid_command_dispatch__opcode04_ack_action_one:
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bra         hid_command_dispatch__delay_before_status_response
hid_command_dispatch__opcode04_stage_fault_action:
    movff       ram_0x11D, ram_0x0B8
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bsf         ram_0x07F, 0, BANKED
    bsf         ram_0x094, 4, BANKED
    bra         hid_command_dispatch__delay_before_status_response
hid_command_dispatch__dispatch_opcode04_action:
    movlb       0x0
    movf        ram_0x0B7, W, BANKED
    xorlw       0x01
    bz          hid_command_dispatch__opcode04_ack_action_one
    xorlw       0x03
    bz          hid_command_dispatch__opcode04_stage_fault_action
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__probe_opcode04_payload_mode:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          hid_command_dispatch__handle_opcode04_payload_mode
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__handle_opcode04_payload_mode:
    movff       ram_0x11E, ram_0x0B5
    movlw       0x04
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movlw       0x02
    movwf       ram_0x0C2, BANKED
    movf        ram_0x0B5, W, BANKED
    xorlw       0x06
    bnz         hid_command_dispatch__check_opcode04_quick_status_modes
    movlw       0x05
    movwf       i2c_coeff_3, ACCESS
hid_command_dispatch__copy_opcode04_payload_loop:
    rcall       hid_out_payload_index_to_fsr2
    movf        INDF2, W, ACCESS
    bz          hid_command_dispatch__fill_opcode04_payload_byte_ff
    rcall       hid_out_payload_index_to_fsr2
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x00
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         hid_command_dispatch__advance_opcode04_payload_index
hid_command_dispatch__fill_opcode04_payload_byte_ff:
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
hid_command_dispatch__advance_opcode04_payload_index:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x13
    cpfsgt      i2c_coeff_3, ACCESS
    bra         hid_command_dispatch__copy_opcode04_payload_loop
    movlb       0x0
    bsf         ram_0x0BD, 4, BANKED
    bra         hid_command_dispatch__arm_timer0_after_update
hid_command_dispatch__check_opcode04_quick_status_modes:
    movf        ram_0x0B5, W, BANKED
    xorlw       0x05
    bz          hid_command_dispatch__delay_before_status_response
    movf        ram_0x0B5, W, BANKED
    xorlw       0x07
    bz          hid_command_dispatch__delay_before_status_response
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__apply_settings_payload:
    movff       ram_0x11B, input_select
    movff       ram_0x11F, computed_volume_3
    movff       ram_0x120, computed_volume_2
    movff       ram_0x121, computed_volume_1
    movff       ram_0x122, computed_volume
    movlb       0x1
    btfsc       ram_0x023, 0, BANKED
    bra         flow_hid_command_dispatch_11ec
    bcf         active_flags, 4, ACCESS
    bra         flow_hid_command_dispatch_11ee
flow_hid_command_dispatch_11ec:
    bsf         active_flags, 4, ACCESS
flow_hid_command_dispatch_11ee:
    movlb       0x1
    btfsc       ram_0x024, 0, BANKED
    bra         flow_hid_command_dispatch_11fa
    movlb       0x0
    bcf         ram_0x0A4, 0, BANKED
    bra         flow_hid_command_dispatch_11fe
flow_hid_command_dispatch_11fa:
    movlb       0x0
    bsf         ram_0x0A4, 0, BANKED
flow_hid_command_dispatch_11fe:
    movlb       0x1
    btfsc       ram_0x025, 0, BANKED
    bra         flow_hid_command_dispatch_120a
    movlb       0x0
    bcf         ram_0x0A4, 1, BANKED
    bra         flow_hid_command_dispatch_120e
flow_hid_command_dispatch_120a:
    movlb       0x0
    bsf         ram_0x0A4, 1, BANKED
flow_hid_command_dispatch_120e:
    movlb       0x1
    btfsc       ram_0x026, 0, BANKED
    bra         flow_hid_command_dispatch_121a
    movlb       0x0
    bcf         ram_0x0A4, 2, BANKED
    bra         flow_hid_command_dispatch_121e
flow_hid_command_dispatch_121a:
    movlb       0x0
    bsf         ram_0x0A4, 2, BANKED
flow_hid_command_dispatch_121e:
    movlb       0x1
    btfsc       ram_0x028, 0, BANKED
    bra         flow_hid_command_dispatch_122a
    movlb       0x0
    bcf         ram_0x0A4, 3, BANKED
    bra         flow_hid_command_dispatch_122e
flow_hid_command_dispatch_122a:
    movlb       0x0
    bsf         ram_0x0A4, 3, BANKED
flow_hid_command_dispatch_122e:
    movlb       0x1
    btfsc       ram_0x029, 0, BANKED
    bra         flow_hid_command_dispatch_123a
    movlb       0x0
    bcf         ram_0x0A4, 4, BANKED
    bra         flow_hid_command_dispatch_123e
flow_hid_command_dispatch_123a:
    movlb       0x0
    bsf         ram_0x0A4, 4, BANKED
flow_hid_command_dispatch_123e:
    movlb       0x1
    btfsc       ram_0x02A, 0, BANKED
    bra         flow_hid_command_dispatch_124a
    movlb       0x0
    bcf         ram_0x0A4, 5, BANKED
    bra         hid_command_dispatch__compare_settings_mirrors
flow_hid_command_dispatch_124a:
    movlb       0x0
    bsf         ram_0x0A4, 5, BANKED
hid_command_dispatch__compare_settings_mirrors:
    movff       ram_0x12C, ram_0x060
    movff       ram_0x12D, ram_0x061
    movff       ram_0x12E, ram_0x062
    movff       ram_0x12F, ram_0x063
    movff       ram_0x130, ram_0x064
    movff       ram_0x131, ram_0x065
    movff       ram_0x132, ram_0x05F
    movff       ram_0x133, ram_0x09B
    movff       ram_0x134, ram_0x09C
    movff       ram_0x135, ram_0x09D
    movff       ram_0x136, ram_0x09E
    movff       ram_0x138, ram_0x0B4
    movf        input_select_mirror, W, BANKED
    xorwf       input_select, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x094, 0, BANKED
    movf        logical_volume_3, W, BANKED
    xorwf       computed_volume_3, W, BANKED
    bnz         hid_command_dispatch__mark_volume_dirty_if_changed
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         hid_command_dispatch__mark_volume_dirty_if_changed
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         hid_command_dispatch__mark_volume_dirty_if_changed
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
hid_command_dispatch__mark_volume_dirty_if_changed:
    bz          hid_command_dispatch__check_route_trim_dirty
    bsf         event_flags, 3, BANKED
    bsf         ram_0x094, 1, BANKED
hid_command_dispatch__check_route_trim_dirty:
    movf        ram_0x0AC, W, BANKED
    xorwf       ram_0x09B, W, BANKED
    bz          flow_hid_command_dispatch_12ac
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12ac:
    movf        ram_0x0AD, W, BANKED
    xorwf       ram_0x09C, W, BANKED
    bz          flow_hid_command_dispatch_12b6
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12b6:
    movf        ram_0x0AE, W, BANKED
    xorwf       ram_0x09D, W, BANKED
    bz          flow_hid_command_dispatch_12c0
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12c0:
    movf        ram_0x0AF, W, BANKED
    xorwf       ram_0x09E, W, BANKED
    bz          hid_command_dispatch__check_mute_state_dirty
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
hid_command_dispatch__check_mute_state_dirty:
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x04C, ACCESS
    movlw       0x01
    btfss       active_flags, 5, ACCESS
    movlw       0x00
    xorwf       ram_0x04C, F, ACCESS
    bz          hid_command_dispatch__check_channel_setup_dirty
    bsf         event_flags, 5, BANKED
    bsf         ram_0x094, 3, BANKED
hid_command_dispatch__check_channel_setup_dirty:
    movf        ram_0x0B0, W, BANKED
    xorwf       ram_0x0A4, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 6, BANKED
    movf        ram_0x0B4, W, BANKED
    xorwf       ram_0x0B1, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x07F, 1, BANKED
    movf        ram_0x060, W, BANKED
    cpfseq      ram_0x0A5, BANKED
    bra         hid_command_dispatch__mark_channel_source_dirty
    movf        ram_0x0A6, W, BANKED
    lfsr        FSR2, 0x0061
    cpfseq      INDF2, ACCESS
    bra         hid_command_dispatch__mark_channel_source_dirty
    movf        ram_0x0A7, W, BANKED
    lfsr        FSR2, 0x0062
    cpfseq      INDF2, ACCESS
    bra         hid_command_dispatch__mark_channel_source_dirty
    movf        ram_0x0A8, W, BANKED
    lfsr        FSR2, 0x0063
    cpfseq      INDF2, ACCESS
    bra         hid_command_dispatch__mark_channel_source_dirty
    movf        ram_0x0A9, W, BANKED
    lfsr        FSR2, 0x0064
    cpfseq      INDF2, ACCESS
    bra         hid_command_dispatch__mark_channel_source_dirty
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
hid_command_dispatch__mark_channel_source_dirty:
    bsf         event_flags, 4, BANKED
    movff       input_select, input_select_mirror
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    btfss       active_flags, 4, ACCESS
    bra         hid_command_dispatch__clear_mute_shadow
    bsf         active_flags, 5, ACCESS
    bra         hid_command_dispatch__snapshot_settings_mirrors
hid_command_dispatch__clear_mute_shadow:
    bcf         active_flags, 5, ACCESS
hid_command_dispatch__snapshot_settings_mirrors:
    movff       ram_0x0A4, ram_0x0B0
    movff       ram_0x060, ram_0x0A5
    movff       ram_0x061, ram_0x0A6
    movff       ram_0x062, ram_0x0A7
    movff       ram_0x063, ram_0x0A8
    movff       ram_0x064, ram_0x0A9
    movff       ram_0x065, ram_0x0AA
    movff       ram_0x0B4, ram_0x0B1
    movff       ram_0x09B, ram_0x0AC
    movff       ram_0x09C, ram_0x0AD
    movff       ram_0x09D, ram_0x0AE
    movff       ram_0x09E, ram_0x0AF
hid_command_dispatch__stage_status_05:
    movlw       0x05
    bra         hid_command_dispatch__emit_selected_status
hid_command_dispatch__handle_opcode_06:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         hid_command_dispatch__probe_opcode06_alt_status
    call        timer3_blocking_delay_2ms, 0x0
    movlw       0x06
hid_command_dispatch__emit_selected_status:
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    bra         hid_command_dispatch__emit_status_response
hid_command_dispatch__probe_opcode06_alt_status:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          hid_command_dispatch__delay_before_status_05
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__delay_before_status_05:
    call        timer3_blocking_delay_2ms, 0x0
    bra         hid_command_dispatch__stage_status_05
hid_command_dispatch__handle_opcode_0c:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    xorlw       0x0F
    btfsc       STATUS, 2, ACCESS
    bsf         active_flags, 7, ACCESS
hid_command_dispatch__stage_upload_payload:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x07
    bnz         hid_command_dispatch__commit_upload_payload
    movlb       0x1
    tstfsz      ram_0x01B, BANKED
    bra         hid_command_dispatch__commit_upload_payload
    movlb       0x0
    clrf        ram_0x0C5, BANKED
    movlw       0x56
    movwf       ram_0x083, BANKED
    movlw       0x00
    clrf        ram_0x082, BANKED
hid_command_dispatch__commit_upload_payload:
    bcf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
    clrf        rx_ring_wr, BANKED
    clrf        rx_ring_rd, BANKED
    call        fw_update_commit_hid_payload_page, 0x0
hid_command_dispatch__emit_opcode_status:
    movff       i2c_coeff_2, ram_0x0C1
    bra         hid_command_dispatch__emit_status_response
hid_command_dispatch__enter_fw_update_boot_marker:
    movlw       0xA0
    movlb       0x0
    movwf       computed_volume, BANKED
    setf        computed_volume_1, BANKED
    setf        computed_volume_2, BANKED
    setf        computed_volume_3, BANKED
    movlw       0x01
    movwf       input_select, BANKED
    movlw       0x03
    movwf       ram_0x05F, ACCESS
    clrf        ram_0x060, BANKED
    clrf        ram_0x061, BANKED
    clrf        ram_0x062, BANKED
    movlw       0x01
    movwf       ram_0x063, BANKED
    movwf       ram_0x064, BANKED
    movwf       ram_0x065, BANKED
    movwf       ram_0x0B4, BANKED
    movlw       0x04
    movwf       ram_0x0B8, BANKED
    clrf        ram_0x09B, BANKED
    clrf        ram_0x09C, BANKED
    clrf        ram_0x09D, BANKED
    clrf        ram_0x09E, BANKED
    clrf        i2c_coeff_3, ACCESS
flow_hid_command_dispatch_1402:
    movlw       0xC0
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1D
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_1402
    clrf        i2c_coeff_3, ACCESS
flow_hid_command_dispatch_141a:
    movlw       0x00
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x0E
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_141a
    movlb       0x0
    bsf         ram_0x0BD, 0, BANKED
    bsf         ram_0x0BD, 5, BANKED
    bsf         ram_0x0BD, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    bsf         ram_0x0BD, 3, BANKED
    bsf         event_flags, 0, BANKED
    call        persist_dirty_runtime_state_to_eeprom, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x00
    clrf        ram_0x009, ACCESS
    call        eeprom_write_byte_if_changed, 0x0
    call        hard_reset, 0x0
    bra         hid_command_dispatch__clear_opcode_and_return
fw_update_start_relay_handshake:
    movlb       0x0
    tstfsz      ram_0x0CB, BANKED
    bra         fw_update_init_sequence__gate_relay_session
    clrf        ram_0x07C, BANKED
    clrf        ram_0x07D, BANKED
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
    clrf        ram_0x086, BANKED
    clrf        ram_0x087, BANKED
    clrf        ram_0x084, BANKED
    clrf        ram_0x085, BANKED
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xC7
    movwf       ram_0x003, ACCESS
    movlw       0x0A
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x9A
    movwf       ram_0x003, ACCESS
    movlw       0x2D
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xD1
    movwf       ram_0x003, ACCESS
    movlw       0x08
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    call        fw_update_emit_bf18_status, 0x0
    movlw       0x05
    movwf       ram_0x006, ACCESS
    movlw       0xDC
    movwf       ram_0x005, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       ram_0x008, ACCESS
    movlw       0xD1
    movwf       ram_0x007, ACCESS
    movlw       0x08
    movwf       ram_0x009, ACCESS
    call        uart_rx_with_framing, 0x0
    movwf       ram_0x04C, ACCESS
    movlw       0x05
    subwf       ram_0x04C, W, ACCESS
    bnc         fw_update_init_sequence__clear_failed_session
    movlw       0x01
    movwf       ram_0x0CB, BANKED
    clrf        i2c_coeff_3, ACCESS
fw_update_init_sequence__compare_echo_buffer_byte:
    movf        i2c_coeff_3, W, ACCESS
    addlw       0x4D
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    movwf       ram_0x04C, ACCESS
    movlw       0xD1
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    movf        INDF2, W, ACCESS
    xorwf       ram_0x04C, W, ACCESS
    bz          fw_update_init_sequence__advance_echo_compare
    movlb       0x0
    clrf        ram_0x0CB, BANKED
fw_update_init_sequence__advance_echo_compare:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x05
    cpfsgt      i2c_coeff_3, ACCESS
    bra         fw_update_init_sequence__compare_echo_buffer_byte
    bra         fw_update_init_sequence__gate_relay_session
fw_update_init_sequence__clear_failed_session:
    clrf        ram_0x0CB, BANKED
fw_update_init_sequence__gate_relay_session:
    movlb       0x0
    movf        ram_0x0CB, W, BANKED
    bnz         fw_update_init_sequence__run_relay_session
    bra         hid_command_dispatch__emit_opcode_status
fw_update_init_sequence__run_relay_session:
    call        fw_update_relay, 0x0
    bra         hid_command_dispatch__emit_opcode_status
hid_command_dispatch__validate_fw_update_signature:
    movff       ram_0x11E, i2c_coeff_1
    movff       ram_0x11F, i2c_coeff_0
    movff       i2c_coeff_2, ram_0x0C1
    call        stage_hid_ep1_in_report_from_selector, 0x0
    movf        ram_0x07D, W, BANKED
    xorwf       i2c_coeff_1, W, ACCESS
    bnz         hid_command_dispatch__check_fw_update_signature_result
    movf        ram_0x07C, W, BANKED
    xorwf       i2c_coeff_0, W, ACCESS
hid_command_dispatch__check_fw_update_signature_result:
    bnz         hid_command_dispatch__reject_fw_update_signature
    call        fw_update_emit_zero_status_lines, 0x0
    movlw       0xAA
    movlb       0x1
    movwf       ram_0x05C, BANKED
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__reject_fw_update_signature:
    movlw       0x11
    movlb       0x1
    movwf       ram_0x05B, BANKED
    movlb       0x0
    clrf        ram_0x084, BANKED
    clrf        ram_0x085, BANKED
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
    clrf        ram_0x086, BANKED
    clrf        ram_0x087, BANKED
    clrf        ram_0x07C, BANKED
    clrf        ram_0x07D, BANKED
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__unsupported_opcode:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__decode_opcode_xor_chain:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x01
    bz          hid_command_dispatch__clear_opcode_and_return
    xorlw       0x03
    bz          hid_command_dispatch__clear_opcode_and_return
    xorlw       0x01
    bnz         hid_command_dispatch__probe_opcode_04
    bra         hid_command_dispatch__handle_opcode_03
hid_command_dispatch__probe_opcode_04:
    xorlw       0x07
    bnz         hid_command_dispatch__probe_opcode_05
    bra         hid_command_dispatch__handle_opcode_04
hid_command_dispatch__probe_opcode_05:
    xorlw       0x01
    bnz         hid_command_dispatch__probe_opcode_06
    bra         hid_command_dispatch__apply_settings_payload
hid_command_dispatch__probe_opcode_06:
    xorlw       0x03
    bnz         hid_command_dispatch__probe_upload_opcode_range
    bra         hid_command_dispatch__handle_opcode_06
hid_command_dispatch__probe_upload_opcode_range:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_157a
    bra         hid_command_dispatch__stage_upload_payload
flow_hid_command_dispatch_157a:
    xorlw       0x0F
    bnz         flow_hid_command_dispatch_1580
    bra         hid_command_dispatch__stage_upload_payload
flow_hid_command_dispatch_1580:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1586
    bra         hid_command_dispatch__stage_upload_payload
flow_hid_command_dispatch_1586:
    xorlw       0x03
    bnz         flow_hid_command_dispatch_158c
    bra         hid_command_dispatch__stage_upload_payload
flow_hid_command_dispatch_158c:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1592
    bra         hid_command_dispatch__stage_upload_payload
flow_hid_command_dispatch_1592:
    xorlw       0x07
    bnz         hid_command_dispatch__probe_fw_boot_opcode_40
    bra         hid_command_dispatch__handle_opcode_0c
hid_command_dispatch__probe_fw_boot_opcode_40:
    xorlw       0x4C
    bnz         hid_command_dispatch__probe_fw_update_opcodes
    bra         hid_command_dispatch__enter_fw_update_boot_marker
hid_command_dispatch__probe_fw_update_opcodes:
    xorlw       0x01
    bz          hid_command_dispatch__validate_fw_update_signature
    xorlw       0x03
    bnz         hid_cmd_diag_snapshot_probe
    bra         fw_update_start_relay_handshake
hid_cmd_diag_snapshot_probe:
    bra         hid_command_dispatch__unsupported_opcode
hid_command_dispatch__clear_opcode_and_return:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: hid_out_payload_index_to_fsr2
; Address : 0x15B0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
hid_out_payload_index_to_fsr2:
    movlw       0x1A
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: hid_config_fill_ff_at_index
; Address : 0x15BE
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
hid_config_fill_ff_at_index:
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: fw_update_relay
; Address : 0x15CE
; Notes   : Inferred flash helper; touches flash. Calls: uart_tx_ascii_hex_byte, uart_tx_byte_blocking, uart_rx_with_framing.
; ---------------------------------------------------------------------------
fw_update_relay:
    lfsr        FSR2, 0x01E5
    lfsr        FSR1, 0x001D
    movlw       0x08
flow_fw_update_relay_15d8:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_fw_update_relay_15d8
    movlw       0x02
    movwf       ram_0x049, ACCESS
fw_update_relay__process_next_hid_payload_byte:
    movlw       0x1A
    addwf       ram_0x049, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    movf        INDF2, W, ACCESS
    movwf       ram_0x04A, ACCESS
    movlw       0xC0
    movlb       0x0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          fw_update_relay__check_minimum_flash_addr
    movff       ram_0x04A, ram_0x045
    clrf        ram_0x048, ACCESS
fw_update_relay__update_signature_bit_loop:
    btfss       ram_0x07D, 5, BANKED
    bra         fw_update_relay__clear_signature_feedback_flag
    movlw       0x01
    movwf       ram_0x044, ACCESS
    bra         fw_update_relay__shift_signature_with_payload_bit
fw_update_relay__clear_signature_feedback_flag:
    clrf        ram_0x044, ACCESS
fw_update_relay__shift_signature_with_payload_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x07C, F, BANKED
    rlcf        ram_0x07D, F, BANKED
    btfsc       ram_0x045, 0, ACCESS
    bsf         ram_0x07C, 0, BANKED
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x045, F, ACCESS
    movf        ram_0x044, W, ACCESS
    bz          fw_update_relay__advance_signature_bit_count
    movlw       0x02
    xorwf       ram_0x07C, F, BANKED
    movlw       0x44
    xorwf       ram_0x07D, F, BANKED
fw_update_relay__advance_signature_bit_count:
    incf        ram_0x048, F, ACCESS
    movlw       0x07
    cpfsgt      ram_0x048, ACCESS
    bra         fw_update_relay__update_signature_bit_loop
fw_update_relay__check_minimum_flash_addr:
    movlw       0x40
    subwf       ram_0x084, W, BANKED
    movlw       0x00
    subwfb      ram_0x085, W, BANKED
    bc          fw_update_relay__check_crc_region_limit
    bra         fw_update_relay__advance_payload_cursor
fw_update_relay__check_crc_region_limit:
    movlw       0xC0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bnc         fw_update_relay__check_address_alignment
    bra         fw_update_relay__advance_payload_cursor
fw_update_relay__check_address_alignment:
    movlw       0x0F
    andwf       ram_0x084, W, BANKED
    movwf       ram_0x08A, BANKED
    clrf        ram_0x08B, BANKED
    iorwf       ram_0x08B, W, BANKED
    bz          fw_update_relay__check_saved_status_addr
    bra         fw_update_relay__forward_payload_byte
fw_update_relay__check_saved_status_addr:
    movf        ram_0x087, W, BANKED
    iorwf       ram_0x086, W, BANKED
    bnz         fw_update_relay__emit_saved_addr_checksum
    bra         fw_update_relay__clear_retry_delay_counter
fw_update_relay__emit_saved_addr_checksum:
    movf        ram_0x086, W, BANKED
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    movf        ram_0x087, W, BANKED
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    comf        ram_0x080, W, BANKED
    movwf       ram_0x01B, ACCESS
    comf        ram_0x081, W, BANKED
    movwf       ram_0x01C, ACCESS
    movlw       0xF1
    addwf       ram_0x01B, W, ACCESS
    movwf       ram_0x080, BANKED
    movlw       0xFF
    addwfc      ram_0x01C, W, ACCESS
    movwf       ram_0x081, BANKED
    movf        ram_0x080, W, BANKED
    call        uart_tx_ascii_hex_byte, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    movff       ram_0x080, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    addlw       LOW(hex_lookup_table)               ; indexed TBLPTR -> hex_lookup_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    tblrd*
    movff       TABLAT, INDF2
    movff       ram_0x080, ram_0x01B
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    addlw       LOW(hex_lookup_table)               ; indexed TBLPTR -> hex_lookup_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    movlw       0x9B
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    tblrd*
    movff       TABLAT, INDF2
    movlw       0x9C
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    clrf        INDF2, ACCESS
    movlw       0x02
    addwf       ram_0x04B, F, ACCESS
    movlb       0x0
    clrf        ram_0x09F, BANKED
fw_update_relay__poll_status_response:
    clrf        ram_0x006, ACCESS
    movlw       0x0A
    movwf       ram_0x005, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       ram_0x008, ACCESS
    movlw       0xC7
    movwf       ram_0x007, ACCESS
    movlw       0x0A
    movwf       ram_0x009, ACCESS
    call        uart_rx_with_framing, 0x0
    movff       ram_0x1C8, ram_0x003
    movlb       0x1
    movf        rx_ring_wr, W, BANKED
    call        intel_hex_checksum_update, 0x0
    movlb       0x0
    xorwf       ram_0x080, W, BANKED
    bnz         fw_update_relay__handle_status_checksum_mismatch
    movlw       0x01
    movwf       ram_0x043, ACCESS
    bra         fw_update_relay__retry_until_response_matches
fw_update_relay__handle_status_checksum_mismatch:
    clrf        ram_0x043, ACCESS
    clrf        ram_0x019, ACCESS
    movlw       0x1D
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    movff       ram_0x09F, ram_0x012
    clrf        ram_0x013, ACCESS
    clrf        ram_0x015, ACCESS
    movlw       0x0A
    movwf       ram_0x014, ACCESS
    movlw       0x25
    call        format_int16_decimal_ascii_to_w_pointer, 0x0
    movwf       ram_0x01B, ACCESS
    clrf        ram_0x019, ACCESS
    movff       ram_0x01B, ram_0x018
    call        uart_tx_block_from_buffer, 0x0
    movlw       0x21
    call        uart_tx_byte_blocking, 0x0
    call        uart_rx_ring_drain_all, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    movlw       0x19
    movlb       0x0
    subwf       ram_0x09F, W, BANKED
    bc          fw_update_relay__return_after_retry_exhausted
    incf        ram_0x09F, F, BANKED
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    bra         fw_update_relay__retry_until_response_matches
fw_update_relay__return_after_retry_exhausted:
    incf        ram_0x09F, F, BANKED
    bra         flow_fw_update_relay_18dc
fw_update_relay__retry_until_response_matches:
    movf        ram_0x043, W, ACCESS
    bnz         fw_update_relay__maybe_delay_before_status_emit
    bra         fw_update_relay__poll_status_response
fw_update_relay__clear_retry_delay_counter:
    clrf        ram_0x08E, BANKED
fw_update_relay__maybe_delay_before_status_emit:
    movlw       0xBF
    movlb       0x0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          fw_update_relay__forward_payload_byte
    movlw       0x04
    subwf       ram_0x08E, W, BANKED
    bc          fw_update_relay__emit_active_addr_status_line
    incf        ram_0x08E, F, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
fw_update_relay__emit_active_addr_status_line:
    movff       ram_0x084, ram_0x086
    movff       ram_0x085, ram_0x087
    movlw       0x3A
    movlb       0x1
    movwf       ram_0x09A, BANKED
    movlw       0x31
    movwf       ram_0x09B, BANKED
    movlw       0x30
    movwf       ram_0x09C, BANKED
    movff       ram_0x087, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x19D
    movff       ram_0x087, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x19E
    movff       ram_0x086, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x19F
    movff       ram_0x086, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x1A0
    movlw       0x30
    movwf       ram_0x0A1, BANKED
    movwf       ram_0x0A2, BANKED
    clrf        ram_0x0A3, BANKED
    movlw       0x09
    movwf       ram_0x04B, ACCESS
    call        uart_rx_ring_drain_all, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
fw_update_relay__forward_payload_byte:
    movlw       0xBF
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          fw_update_relay__clear_checksum_after_range
    btfss       ram_0x084, 0, BANKED
    bra         fw_update_relay__stage_odd_payload_byte
    movff       ram_0x046, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x02F
    movff       ram_0x046, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x030
    movff       ram_0x04A, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x031
    movff       ram_0x04A, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x032
    clrf        ram_0x033, ACCESS
    clrf        ram_0x019, ACCESS
    movlw       0x2F
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    clrf        ram_0x047, ACCESS
    bra         fw_update_relay__copy_payload_text_until_nul
fw_update_relay__copy_payload_text_byte:
    movf        ram_0x047, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x047, F, ACCESS
    incf        ram_0x04B, F, ACCESS
fw_update_relay__copy_payload_text_until_nul:
    movf        ram_0x047, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    bnz         fw_update_relay__copy_payload_text_byte
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    clrf        INDF2, ACCESS
    bra         fw_update_relay__accumulate_payload_checksum
fw_update_relay__stage_odd_payload_byte:
    movff       ram_0x04A, ram_0x046
fw_update_relay__accumulate_payload_checksum:
    movf        ram_0x04A, W, ACCESS
    movlb       0x0
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    bra         fw_update_relay__advance_payload_cursor
fw_update_relay__clear_checksum_after_range:
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
fw_update_relay__advance_payload_cursor:
    infsnz      ram_0x084, F, BANKED
    incf        ram_0x085, F, BANKED
    incf        ram_0x049, F, ACCESS
    movlw       0x1F
    cpfsgt      ram_0x049, ACCESS
    bra         fw_update_relay__process_next_hid_payload_byte
flow_fw_update_relay_18dc:
    return      0


; ---------------------------------------------------------------------------
; Function: nibble_to_hex_ascii
; Address : 0x18DE
; Notes   : Converts low nibble to ASCII hex via program-memory lookup table.
; ---------------------------------------------------------------------------
nibble_to_hex_ascii:
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    addlw       LOW(hex_lookup_table)               ; indexed TBLPTR -> hex_lookup_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    tblrd*
    return      0

; ---------------------------------------------------------------------------
; Function: cmd_dispatch_gated
; Address : 0x18EE
; Notes   : Inferred i2c helper routine. Calls: i2c_secondary_dev_write, i2c_tas3108_reg1f_02_clear_source_pins, drive_audio_route_select_latches.
; ---------------------------------------------------------------------------
cmd_dispatch_gated:
    movff       WREG, ram_0x0FD
    btfss       active_flags, 3, ACCESS
    bra         cmd_gate_reject
    btfss       event_flags, 1, BANKED
    bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty
    bsf         event_flags, 3, BANKED
    bra         cmd_dispatch_gated__dispatch_input_route_code
cmd_dispatch_gated__route_code_1_i2c_pair:
    movlw       0x09
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x70
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        i2c_tas3108_reg1f_02_clear_source_pins, 0x0
    bra         cmd_dispatch_gated__input_route_write_complete
cmd_dispatch_gated__route_code_2_i2c_pair:
    movlw       0x0A
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0xB0
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        i2c_tas3108_reg1f_02_clear_source_pins, 0x0
    bra         cmd_dispatch_gated__input_route_write_complete
cmd_dispatch_gated__route_code_3_i2c_pair:
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        i2c_tas3108_reg1f_02_clear_source_pins, 0x0
    bra         cmd_dispatch_gated__input_route_write_complete
cmd_dispatch_gated__route_code_4_i2c_pair:
    movlw       0x0B
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0xF0
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        i2c_tas3108_reg1f_02_clear_source_pins, 0x0
    bra         cmd_dispatch_gated__input_route_write_complete
cmd_dispatch_gated__default_route_reg1f_write:
    call        drive_audio_route_select_latches, 0x0
    call        main_core_service_4954, 0x0
    bra         cmd_dispatch_gated__input_route_write_complete
cmd_dispatch_gated__dispatch_input_route_code:
    movf        ram_0x093, W, BANKED
    bz          cmd_dispatch_gated__default_route_reg1f_write
    xorlw       0x01
    bz          cmd_dispatch_gated__route_code_1_i2c_pair
    xorlw       0x03
    bz          cmd_dispatch_gated__route_code_2_i2c_pair
    xorlw       0x01
    bz          cmd_dispatch_gated__route_code_3_i2c_pair
    xorlw       0x07
    bz          cmd_dispatch_gated__route_code_4_i2c_pair
    xorlw       0x01
    bz          cmd_dispatch_gated__default_route_reg1f_write
    xorlw       0x03
    bz          cmd_dispatch_gated__default_route_reg1f_write
    xorlw       0x01
    bz          cmd_dispatch_gated__default_route_reg1f_write
cmd_dispatch_gated__input_route_write_complete:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        usb_hid_mailbox_send_reply_if_ready, 0x0
    movlb       0x0
    bcf         event_flags, 1, BANKED
    bsf         ram_0x0BD, 0, BANKED
    call        timer0_rearm_50ms_heartbeat, 0x0
cmd_dispatch_gated__check_reconnect_and_volume_dirty:
    movlb       0x0
    btfss       event_flags, 3, BANKED
    bra         cmd_dispatch_gated__check_reconnect_reapply
    bcf         active_flags, 4, ACCESS
    bcf         event_flags, 5, BANKED
    bsf         event_flags, 6, BANKED
    clrf        ram_0x0A4, BANKED
    movff       ram_0x0A4, ram_0x0B0
    clrf        ram_0x09A, BANKED
    bra         cmd_dispatch_gated__select_applied_route_trim
flow_cmd_dispatch_gated_19be:
    movff       ram_0x09B, ram_0x09A
    bra         cmd_dispatch_gated__stage_volume_coefficients
flow_cmd_dispatch_gated_19c4:
    movff       ram_0x09C, ram_0x09A
    bra         cmd_dispatch_gated__stage_volume_coefficients
flow_cmd_dispatch_gated_19ca:
    movff       ram_0x09D, ram_0x09A
    bra         cmd_dispatch_gated__stage_volume_coefficients
flow_cmd_dispatch_gated_19d0:
    movff       ram_0x09E, ram_0x09A
    bra         cmd_dispatch_gated__stage_volume_coefficients
cmd_dispatch_gated__select_applied_route_trim:
    movf        ram_0x093, W, BANKED
    bz          flow_cmd_dispatch_gated_19be
    xorlw       0x05
    bz          flow_cmd_dispatch_gated_19c4
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_19ca
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_19d0
cmd_dispatch_gated__stage_volume_coefficients:
    movf        ram_0x09A, W, BANKED
    addwf       computed_volume, W, BANKED
    movwf       ram_0x00D, ACCESS
    movlw       0x00
    addwfc      computed_volume_1, W, BANKED
    movwf       ram_0x00E, ACCESS
    movlw       0x00
    addwfc      computed_volume_2, W, BANKED
    movwf       ram_0x00F, ACCESS
    movlw       0x00
    addwfc      computed_volume_3, W, BANKED
    movwf       ram_0x010, ACCESS
    call        int32_to_float32_and_save, 0x0
    movff       ram_0x00D, ram_0x012
    movff       ram_0x00E, ram_0x013
    movff       ram_0x00F, ram_0x014
    movff       ram_0x010, ram_0x015
    movlw       0x47
    movwf       ram_0x016, ACCESS
    movlw       0xC9
    movwf       ram_0x017, ACCESS
    movlw       0xEB
    movwf       ram_0x018, ACCESS
    movlw       0x3D
    movwf       ram_0x019, ACCESS
    call        float32_multiply_primary_by_secondary_in_place, 0x0
    movff       ram_0x012, ram_0x0ED
    movff       ram_0x013, ram_0x0EE
    movff       ram_0x014, ram_0x0EF
    movff       ram_0x015, ram_0x0F0
    movff       ram_0x0ED, ram_0x02F
    movff       ram_0x0EE, ram_0x030
    movff       ram_0x0EF, ram_0x031
    movff       ram_0x0F0, ram_0x032
    call        float32_exp_limit1024_in_place, 0x0
    movff       ram_0x02F, i2c_coeff_0
    movff       ram_0x030, i2c_coeff_1
    movff       ram_0x031, i2c_coeff_2
    movff       ram_0x032, i2c_coeff_3
    call        i2c_tas3108_coeff_write, 0x0
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        usb_hid_mailbox_send_reply_if_ready, 0x0
    movlb       0x0
    bcf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 0, BANKED
    call        timer0_rearm_50ms_heartbeat, 0x0
cmd_dispatch_gated__check_reconnect_reapply:
    btfss       active_flags, 7, ACCESS
    bra         cmd_dispatch_gated__check_mute_dirty
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    call        preset_replay_selected_table_blocking, 0x0
    call        main_uart_service_495e, 0x0
    bcf         active_flags, 7, ACCESS
    movlb       0x0
    btfss       event_flags, 5, BANKED
    btfsc       active_flags, 4, ACCESS
    bra         cmd_dispatch_gated__check_mute_dirty
    bsf         event_flags, 3, BANKED
cmd_dispatch_gated__check_mute_dirty:
    movlb       0x0
    btfss       event_flags, 5, BANKED
    bra         cmd_dispatch_gated__check_channel_enable_dirty
    btfss       active_flags, 4, ACCESS
    bra         cmd_dispatch_gated__mute_dirty_unmuted
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    bra         cmd_dispatch_gated__mute_dirty_complete
cmd_dispatch_gated__mute_dirty_unmuted:
    bsf         event_flags, 3, BANKED
cmd_dispatch_gated__mute_dirty_complete:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        usb_hid_mailbox_send_reply_if_ready, 0x0
    movlb       0x0
    bcf         event_flags, 5, BANKED
cmd_dispatch_gated__check_channel_enable_dirty:
    btfss       event_flags, 6, BANKED
    bra         cmd_dispatch_gated__check_route_sync_dirty
    btfsc       ram_0x0A4, 0, BANKED
    bra         flow_cmd_dispatch_gated_1ada
    movlw       0x5F
    movwf       ram_0x0F2, BANKED
    movlw       0x1C
    bra         flow_cmd_dispatch_gated_1ae0
flow_cmd_dispatch_gated_1ada:
    movlw       0x5F
    movwf       ram_0x0F2, BANKED
    movlw       0x08
flow_cmd_dispatch_gated_1ae0:
    movwf       ram_0x0F1, BANKED
    movff       ram_0x0F1, ram_0x013
    movff       ram_0x0F2, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 1, BANKED
    bra         flow_cmd_dispatch_gated_1afc
    movlw       0x5F
    movwf       ram_0x0F4, BANKED
    movlw       0x44
    bra         flow_cmd_dispatch_gated_1b02
flow_cmd_dispatch_gated_1afc:
    movlw       0x5F
    movwf       ram_0x0F4, BANKED
    movlw       0x30
flow_cmd_dispatch_gated_1b02:
    movwf       ram_0x0F3, BANKED
    movff       ram_0x0F3, ram_0x013
    movff       ram_0x0F4, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 2, BANKED
    bra         flow_cmd_dispatch_gated_1b1e
    movlw       0x5F
    movwf       ram_0x0F6, BANKED
    movlw       0x6C
    bra         flow_cmd_dispatch_gated_1b24
flow_cmd_dispatch_gated_1b1e:
    movlw       0x5F
    movwf       ram_0x0F6, BANKED
    movlw       0x58
flow_cmd_dispatch_gated_1b24:
    movwf       ram_0x0F5, BANKED
    movff       ram_0x0F5, ram_0x013
    movff       ram_0x0F6, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 3, BANKED
    bra         flow_cmd_dispatch_gated_1b40
    movlw       0x5F
    movwf       ram_0x0F8, BANKED
    movlw       0x94
    bra         flow_cmd_dispatch_gated_1b46
flow_cmd_dispatch_gated_1b40:
    movlw       0x5F
    movwf       ram_0x0F8, BANKED
    movlw       0x80
flow_cmd_dispatch_gated_1b46:
    movwf       ram_0x0F7, BANKED
    movff       ram_0x0F7, ram_0x013
    movff       ram_0x0F8, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 4, BANKED
    bra         flow_cmd_dispatch_gated_1b62
    movlw       0x5F
    movwf       ram_0x0FA, BANKED
    movlw       0xBC
    bra         flow_cmd_dispatch_gated_1b68
flow_cmd_dispatch_gated_1b62:
    movlw       0x5F
    movwf       ram_0x0FA, BANKED
    movlw       0xA8
flow_cmd_dispatch_gated_1b68:
    movwf       ram_0x0F9, BANKED
    movff       ram_0x0F9, ram_0x013
    movff       ram_0x0FA, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 5, BANKED
    bra         flow_cmd_dispatch_gated_1b84
    movlw       0x5F
    movwf       ram_0x0FC, BANKED
    movlw       0xE4
    bra         flow_cmd_dispatch_gated_1b8a
flow_cmd_dispatch_gated_1b84:
    movlw       0x5F
    movwf       ram_0x0FC, BANKED
    movlw       0xD0
flow_cmd_dispatch_gated_1b8a:
    movwf       ram_0x0FB, BANKED
    movff       ram_0x0FB, ram_0x013
    movff       ram_0x0FC, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        usb_hid_mailbox_send_reply_if_ready, 0x0
    movlb       0x0
    bcf         event_flags, 6, BANKED
cmd_dispatch_gated__check_route_sync_dirty:
    btfss       event_flags, 4, BANKED
    bra         cmd_dispatch_gated__check_shared_setup_eeprom_dirty
    call        i2c_apply_channel_route_sync_burst, 0x0
    movlb       0x0
    bcf         event_flags, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    movlw       0x05
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        usb_hid_mailbox_send_reply_if_ready, 0x0
    call        timer0_rearm_50ms_heartbeat, 0x0
cmd_dispatch_gated__check_shared_setup_eeprom_dirty:
    movlb       0x0
    btfss       ram_0x07F, 0, BANKED
    bra         cmd_dispatch_gated__check_setup_profile_eeprom_dirty
    bcf         ram_0x07F, 0, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        timer0_rearm_50ms_heartbeat, 0x0
cmd_dispatch_gated__check_setup_profile_eeprom_dirty:
    movlb       0x0
    btfss       ram_0x07F, 1, BANKED
    bra         cmd_gate_reject
    bcf         ram_0x07F, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        timer0_rearm_50ms_heartbeat, 0x0
cmd_gate_reject:
    return      0


; ---------------------------------------------------------------------------
; Function: uart_link_parser_drain_rx_and_forward
; Address : 0x1BE6
; Notes   : Inferred uart helper routine. Calls: rx_ring_has_data, rx_ring_read, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
uart_link_parser_drain_rx_and_forward:
    clrf        ram_0x009, ACCESS
    bra         uart_link_parser__clear_pending_echo
uart_link_parser__poll_rx_ring:
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    bnz         uart_link_parser__read_next_byte
    bra         uart_link_parser__mark_no_rx_data_return
uart_link_parser__read_next_byte:
    call        rx_ring_read, 0x0
    movwf       ram_0x00A, ACCESS
    movlw       0x7F
    cpfsgt      ram_0x00A, ACCESS
    bra         uart_link_parser__payload_forward_gate
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB0
    bnz         uart_link_parser__check_b1_address_route
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
uart_link_parser__check_b1_address_route:
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB1
    bnz         uart_link_parser__handle_route_or_status_byte
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bsf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
uart_link_parser__handle_route_or_status_byte:
    clrf        rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    movff       ram_0x00A, ram_0x005
    movlw       0xF0
    andwf       ram_0x005, F, ACCESS
    movf        ram_0x005, W, ACCESS
    xorlw       0xB0
    bnz         parser_route_phase_handler
    movf        ram_0x00A, W, ACCESS
    xorlw       0xBF
    btfss       STATUS, 2, ACCESS
    decf        ram_0x00A, F, ACCESS
parser_route_phase_handler:
    btfsc       active_flags, 0, ACCESS
    bra         uart_link_parser__return_if_idle_else_poll
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__payload_forward_gate:
    btfsc       active_flags, 0, ACCESS
    bra         uart_link_parser__advance_payload_position
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          uart_link_parser__advance_payload_position
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
uart_link_parser__advance_payload_position:
    movlb       0x0
    movf        rx_frame_position, W, BANKED
    btfss       STATUS, 2, ACCESS
    incf        rx_frame_position, F, BANKED
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          uart_link_parser__latch_command_or_data
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__latch_command_or_data:
    movf        rx_frame_position, W, BANKED
    xorlw       0x02
    bnz         uart_link_parser__latch_data_and_dispatch_command
    movff       ram_0x00A, ram_0x0A2
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__latch_data_and_dispatch_command:
    movff       ram_0x00A, ram_0x0A3
    movff       ram_0x00A, ram_0x0BC
    bsf         active_flags, 6, ACCESS
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bra         cmd_dispatch_xor_chain
wake_request_handler:
    movlw       0x01
    btfsc       active_flags, 3, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    rlncf       ram_0x005, F, ACCESS
    rlncf       ram_0x005, F, ACCESS
    movf        event_flags, W, BANKED
    xorwf       ram_0x005, W, ACCESS
    andlw       0xFB
    xorwf       ram_0x005, W, ACCESS
    movwf       event_flags, BANKED
    btfsc       event_flags, 2, BANKED
    bsf         active_flags, 3, ACCESS
    bra         uart_link_parser__handler_return_tail
standby_request_handler:
    btfss       active_flags, 3, ACCESS
    bra         uart_link_parser__standby_duplicate_preserve_pending_event
    bsf         event_flags, 2, BANKED
    bra         uart_link_parser__standby_close_gate_if_event_pending
uart_link_parser__standby_duplicate_preserve_pending_event:
    movlb       0x0
    bcf         event_flags, 2, BANKED
uart_link_parser__standby_close_gate_if_event_pending:
    btfsc       event_flags, 2, BANKED
    bcf         active_flags, 3, ACCESS
    bra         uart_link_parser__handler_return_tail
cmd03_mute_on_handler:
    btfsc       ram_0x094, 3, BANKED
    bra         uart_link_parser__mute_query_reply
    bsf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         uart_link_parser__stage_zero_mute_compare_value
    movlw       0x01
    bra         uart_link_parser__mute_dirty_if_user_shadow_differs
uart_link_parser__stage_zero_mute_compare_value:
    movlw       0x00
uart_link_parser__mute_dirty_if_user_shadow_differs:
    xorwf       ram_0x005, F, ACCESS
    btfss       STATUS, 2, ACCESS
uart_link_parser__mark_mute_refresh_dirty:
    bsf         event_flags, 5, BANKED
uart_link_parser__sync_mute_shadow:
    btfss       active_flags, 4, ACCESS
    bra         uart_link_parser__mute_clear_shadow_bit
    bsf         active_flags, 5, ACCESS
    bra         uart_link_parser__mute_return_after_shadow_update
uart_link_parser__mute_clear_shadow_bit:
    bcf         active_flags, 5, ACCESS
uart_link_parser__mute_return_after_shadow_update:
    bra         uart_link_parser__handler_return_tail
uart_link_parser__mute_query_reply:
    movlw       0x02
    btfss       active_flags, 4, ACCESS
    movlw       0x03
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 3, BANKED
    bra         uart_link_parser__handler_return_tail
cmd03_mute_off_handler:
    btfsc       ram_0x094, 3, BANKED
    bra         uart_link_parser__mute_query_reply
    bcf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         uart_link_parser__stage_zero_mute_compare_value
    movlw       0x01
    xorwf       ram_0x005, F, ACCESS
    bnz         uart_link_parser__mark_mute_refresh_dirty
    bra         uart_link_parser__sync_mute_shadow
cmd03_subdispatch:
    movf        ram_0x0A3, W, BANKED
    bz          standby_request_handler
    xorlw       0x01
    bz          wake_request_handler
    xorlw       0x03
    bz          cmd03_mute_on_handler
    xorlw       0x01
    bz          cmd03_mute_off_handler
    bra         uart_link_parser__handler_return_tail
cmd04_status_response:
    call        send_status_burst, 0x0
    bra         uart_link_parser__handler_return_tail
cmd06_input_select_handler:
    btfsc       ram_0x094, 0, BANKED
    bra         uart_link_parser__input_select_query_reply
    movff       ram_0x0A3, input_select
    movff       input_select, input_select_mirror
    bra         uart_link_parser__handler_return_tail
uart_link_parser__input_select_query_reply:
    movff       input_select, ram_0x0BC
    bcf         ram_0x094, 0, BANKED
    bra         uart_link_parser__handler_return_tail
volume_cmd_handler:
    btfsc       ram_0x094, 1, BANKED
    bra         uart_link_parser__volume_query_reply
    movlw       0xA0
    movwf       ram_0x005, ACCESS
    setf        ram_0x006, ACCESS
    movf        ram_0x0A3, W, BANKED
    movwf       ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    movf        ram_0x005, W, ACCESS
    addwf       ram_0x007, F, ACCESS
    movf        ram_0x006, W, ACCESS
    addwfc      ram_0x008, F, ACCESS
    movff       ram_0x007, computed_volume
    movff       ram_0x008, computed_volume_1
    movlw       0x00
    btfsc       computed_volume_1, 7, BANKED
    movlw       0xFF
    movwf       computed_volume_2, BANKED
    movwf       computed_volume_3, BANKED
    xorwf       logical_volume_3, W, BANKED
    bnz         uart_link_parser__volume_return_if_unchanged
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         uart_link_parser__volume_return_if_unchanged
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         uart_link_parser__volume_return_if_unchanged
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
uart_link_parser__volume_return_if_unchanged:
    bnz         uart_link_parser__volume_mark_dirty
    bra         uart_link_parser__handler_return_tail
uart_link_parser__volume_mark_dirty:
    bsf         event_flags, 3, BANKED
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    bra         uart_link_parser__handler_return_tail
uart_link_parser__volume_query_reply:
    movf        computed_volume, W, BANKED
    addlw       0x60
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 1, BANKED
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd10_require_data_29:
    movf        ram_0x0A3, W, BANKED
    xorlw       0x29
    bnz         uart_link_parser__handler_return_tail
    call        report_cmd29_status, 0x0
    bra         uart_link_parser__handler_return_tail
flow_main_uart_service_1be6_1d96:
    movff       ram_0x0A3, ram_0x060
    movf        ram_0x0A5, W, BANKED
    xorwf       ram_0x060, W, BANKED
    bz          uart_link_parser__handler_return_tail
    bsf         event_flags, 4, BANKED
    movff       ram_0x060, ram_0x0A5
    bra         uart_link_parser__handler_return_tail
flow_main_uart_service_1be6_1da8:
    movff       ram_0x0A3, ram_0x061
    movf        ram_0x061, W, BANKED
    xorwf       ram_0x0A6, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x061, ram_0x0A6
    bra         uart_link_parser__handler_return_tail
flow_main_uart_service_1be6_1dba:
    movff       ram_0x0A3, ram_0x062
    movf        ram_0x062, W, BANKED
    xorwf       ram_0x0A7, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x062, ram_0x0A7
    bra         uart_link_parser__handler_return_tail
flow_main_uart_service_1be6_1dcc:
    movff       ram_0x0A3, ram_0x063
    movf        ram_0x063, W, BANKED
    xorwf       ram_0x0A8, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x063, ram_0x0A8
    bra         uart_link_parser__handler_return_tail
flow_main_uart_service_1be6_1dde:
    movff       ram_0x0A3, ram_0x064
    movf        ram_0x064, W, BANKED
    xorwf       ram_0x0A9, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x064, ram_0x0A9
    bra         uart_link_parser__handler_return_tail
flow_main_uart_service_1be6_1df0:
    movff       ram_0x0A3, ram_0x065
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x065, ram_0x0AA
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd1d_update_setup_timeout:
    btfsc       ram_0x094, 4, BANKED
    bra         uart_link_parser__cmd1d_query_reply
    movf        ram_0x0B8, W, BANKED
    xorwf       ram_0x0A3, W, BANKED
    bz          uart_link_parser__handler_return_tail
    movff       ram_0x0A3, ram_0x0B8
    bsf         ram_0x07F, 0, BANKED
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd1d_query_reply:
    movff       ram_0x0B8, ram_0x0BC
    bcf         ram_0x094, 4, BANKED
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd1e_update_link_address:
    movff       ram_0x0A3, ram_0x0C3
    movf        ram_0x0B2, W, BANKED
    xorwf       ram_0x0C3, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x0BD, 0, BANKED
    movff       ram_0x0C3, ram_0x0B2
    bra         uart_link_parser__handler_return_tail
cmd_dispatch_xor_chain:
    movf        ram_0x0A2, W, BANKED
    xorlw       0x03
    bnz         uart_link_parser__dispatch_check_cmd04_status_poll
    bra         cmd03_subdispatch
uart_link_parser__dispatch_check_cmd04_status_poll:
    xorlw       0x07
    bnz         uart_link_parser__dispatch_check_cmd06_input_select
    bra         cmd04_status_response
uart_link_parser__dispatch_check_cmd06_input_select:
    xorlw       0x02
    bnz         uart_link_parser__dispatch_check_cmd07_volume
    bra         cmd06_input_select_handler
uart_link_parser__dispatch_check_cmd07_volume:
    xorlw       0x01
    bnz         uart_link_parser__dispatch_check_cmd10_and_extended
    bra         volume_cmd_handler
uart_link_parser__dispatch_check_cmd10_and_extended:
    xorlw       0x17
    bz          uart_link_parser__cmd10_require_data_29
    xorlw       0x07
    bz          flow_main_uart_service_1be6_1d96
    xorlw       0x0F
    bz          flow_main_uart_service_1be6_1da8
    xorlw       0x01
    bz          flow_main_uart_service_1be6_1dba
    xorlw       0x03
    bz          flow_main_uart_service_1be6_1dcc
    xorlw       0x01
    bz          flow_main_uart_service_1be6_1dde
    xorlw       0x07
    bz          flow_main_uart_service_1be6_1df0
    xorlw       0x01
    bz          uart_link_parser__cmd1d_update_setup_timeout
    xorlw       0x03
    bz          uart_link_parser__cmd1e_update_link_address
uart_link_parser__handler_return_tail:
    btfss       active_flags, 6, ACCESS
    bra         uart_link_parser__return_if_idle_else_poll
    movlb       0x0
    movf        ram_0x0BC, W, BANKED
    call        uart_tx_byte_blocking, 0x0
uart_link_parser__clear_pending_echo:
    bcf         active_flags, 6, ACCESS
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__mark_no_rx_data_return:
    movlw       0x01
    movwf       ram_0x009, ACCESS
uart_link_parser__return_if_idle_else_poll:
    movf        ram_0x009, W, ACCESS
    btfss       STATUS, 2, ACCESS
    return      0
    bra         uart_link_parser__poll_rx_ring


; ---------------------------------------------------------------------------
; Function: restore_eeprom_settings_on_boot
; Address : 0x1E88
; Notes   : Inferred core helper routine. Calls: eeprom_read_byte, eeprom_write_byte_if_changed.
; ---------------------------------------------------------------------------
restore_eeprom_settings_on_boot:
    movlw       0x00
    clrf        ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       computed_volume_3, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       computed_volume_2, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x02
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       computed_volume_1, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x03
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       computed_volume, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x04
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       input_select, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x07
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x060, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x08
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x061, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x09
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x062, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x063, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0B
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x064, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0C
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x065, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0D
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       ram_0x05F, ACCESS
    clrf        ram_0x004, ACCESS
    movlw       0x14
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x0C3, BANKED
    movf        computed_volume_3, W, BANKED
    xorlw       0x80
    addlw       0x80
    bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum
    movlw       0x00
    subwf       computed_volume_2, W, BANKED
    bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum
    movlw       0x00
    subwf       computed_volume_1, W, BANKED
    bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum
    movlw       0x13
    subwf       computed_volume, W, BANKED
restore_eeprom_settings_on_boot__clamp_volume_minimum:
    bnc         restore_eeprom_settings_on_boot__validate_input_select
    movlw       0xA0
    movwf       computed_volume, BANKED
    setf        computed_volume_1, BANKED
    setf        computed_volume_2, BANKED
    setf        computed_volume_3, BANKED
restore_eeprom_settings_on_boot__validate_input_select:
    movlw       0x08
    cpfsgt      input_select, BANKED
    bra         restore_eeprom_settings_on_boot__validate_channel1_source
    movlw       0x01
    movwf       input_select, BANKED
restore_eeprom_settings_on_boot__validate_channel1_source:
    movlw       0x03
    cpfsgt      ram_0x060, BANKED
    bra         restore_eeprom_settings_on_boot__validate_channel2_source
    clrf        ram_0x060, BANKED
restore_eeprom_settings_on_boot__validate_channel2_source:
    lfsr        FSR2, 0x0061
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel3_source
    clrf        ram_0x061, BANKED
restore_eeprom_settings_on_boot__validate_channel3_source:
    lfsr        FSR2, 0x0062
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel4_source
    clrf        ram_0x062, BANKED
restore_eeprom_settings_on_boot__validate_channel4_source:
    lfsr        FSR2, 0x0063
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel5_source
    movlw       0x01
    movwf       ram_0x063, BANKED
restore_eeprom_settings_on_boot__validate_channel5_source:
    lfsr        FSR2, 0x0064
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel6_source
    movlw       0x01
    movwf       ram_0x064, BANKED
restore_eeprom_settings_on_boot__validate_channel6_source:
    lfsr        FSR2, 0x0065
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_src_route_status
    movlw       0x01
    movwf       ram_0x064, BANKED
restore_eeprom_settings_on_boot__validate_src_route_status:
    movlw       0x03
    cpfsgt      ram_0x05F, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_link_address
    movwf       ram_0x05F, ACCESS
restore_eeprom_settings_on_boot__validate_link_address:
    movlw       0x04
    cpfsgt      ram_0x0C3, BANKED
    bra         restore_eeprom_settings_on_boot__mirror_runtime_settings
    movlw       0x01
    movwf       ram_0x0C3, BANKED
restore_eeprom_settings_on_boot__mirror_runtime_settings:
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    movff       input_select, input_select_mirror
    movff       ram_0x060, ram_0x0A5
    movff       ram_0x061, ram_0x0A6
    movff       ram_0x062, ram_0x0A7
    movff       ram_0x063, ram_0x0A8
    movff       ram_0x064, ram_0x0A9
    movff       ram_0x065, ram_0x0AA
    movff       ram_0x0C3, ram_0x0B2
    clrf        ram_0x004, ACCESS
    movlw       0x0F
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x0B4, BANKED
    incf        ram_0x0B4, W, BANKED
    btfsc       STATUS, 2, ACCESS
    bcf         ram_0x0B4, 0, BANKED
    movff       ram_0x0B4, ram_0x0B1
    clrf        ram_0x004, ACCESS
    movlw       0x0E
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x0B8, BANKED
    movlw       0x03
    subwf       ram_0x0B8, W, BANKED
    bc          restore_eeprom_settings_on_boot__clamp_shared_setup_maximum
    movlw       0x03
    movwf       ram_0x0B8, BANKED
restore_eeprom_settings_on_boot__clamp_shared_setup_maximum:
    movlw       0x04
    cpfsgt      ram_0x0B8, BANKED
    bra         restore_eeprom_settings_on_boot__read_route_trim_eeprom
    movlw       0x03
    movwf       ram_0x0B8, BANKED
restore_eeprom_settings_on_boot__read_route_trim_eeprom:
    clrf        ram_0x004, ACCESS
    movlw       0x10
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x09B, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x11
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x09C, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x12
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x09D, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x13
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       ram_0x09E, BANKED
    movlw       0x12
    cpfsgt      ram_0x09B, BANKED
    bra         restore_eeprom_settings_on_boot__validate_route5_trim
    clrf        ram_0x09B, BANKED
restore_eeprom_settings_on_boot__validate_route5_trim:
    movlw       0x12
    cpfsgt      ram_0x09C, BANKED
    bra         restore_eeprom_settings_on_boot__validate_route6_trim
    clrf        ram_0x09C, BANKED
restore_eeprom_settings_on_boot__validate_route6_trim:
    movlw       0x12
    cpfsgt      ram_0x09D, BANKED
    bra         restore_eeprom_settings_on_boot__validate_route7_trim
    clrf        ram_0x09D, BANKED
restore_eeprom_settings_on_boot__validate_route7_trim:
    movlw       0x12
    cpfsgt      ram_0x09E, BANKED
    bra         restore_eeprom_settings_on_boot__mirror_route_trim_shadows
    clrf        ram_0x09E, BANKED
restore_eeprom_settings_on_boot__mirror_route_trim_shadows:
    movff       ram_0x09B, ram_0x0AC
    movff       ram_0x09C, ram_0x0AD
    movff       ram_0x09D, ram_0x0AE
    movff       ram_0x09E, ram_0x0AF
    movlw       0x50
    movwf       ram_0x00A, ACCESS
restore_eeprom_settings_on_boot__read_filter_window:
    movlb       0x1
    movlw       0xB0
    addwf       ram_0x00A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    addwfc      FSR2H, F, ACCESS
    movff       ram_0x00A, ram_0x003
    clrf        ram_0x004, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       INDF2, ACCESS
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         restore_eeprom_settings_on_boot__read_filter_window
    movlw       0x60
    movwf       ram_0x00A, ACCESS
restore_eeprom_settings_on_boot__read_preset_a_filename:
    movlb       0x2
    movlw       0x60
    addwf       ram_0x00A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    movff       ram_0x00A, ram_0x003
    clrf        ram_0x004, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       INDF2, ACCESS
    incf        ram_0x00A, F, ACCESS
    movlw       0x7D
    cpfsgt      ram_0x00A, ACCESS
    bra         restore_eeprom_settings_on_boot__read_preset_a_filename
    clrf        ram_0x008, ACCESS
    movlw       0x80
    movwf       ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x81
    movwf       ram_0x007, ACCESS
    movlw       0x03
    movwf       ram_0x009, ACCESS
    goto        eeprom_write_byte_if_changed


; ---------------------------------------------------------------------------
; Function: i2c_apply_channel_route_sync_burst
; Address : 0x2100
; Notes   : Inferred i2c helper; touches i2c. Calls: clear_ram_span_from_staged_addr_count, i2c_wait_bus_idle, map_audio_source_selector_to_route_pair.
; ---------------------------------------------------------------------------
i2c_apply_channel_route_sync_burst:
    clrf        ram_0x004, ACCESS
    movlw       0xD7
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDB
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDF
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xD9
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xE3
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xDD
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xE1
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        clear_ram_span_from_staged_addr_count, 0x0
    call        i2c_wait_bus_idle, 0x0
    clrf        ram_0x059, ACCESS
i2c_apply_channel_route_sync_burst__map_next_channel_route_pair:
    movf        ram_0x059, W, ACCESS
    movlb       0x0
    addlw       0x60
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        map_audio_source_selector_to_route_pair, 0x0
    bra         flow_main_i2c_service_2100_21c8
flow_main_i2c_service_2100_218c:
    movff       ram_0x0A0, ram_0x0D7
    movff       ram_0x0B9, ram_0x0D8
    bra         flow_main_i2c_service_2100_21e0
flow_main_i2c_service_2100_2196:
    movff       ram_0x0A0, ram_0x0DB
    movff       ram_0x0B9, ram_0x0DC
    bra         flow_main_i2c_service_2100_21e0
flow_main_i2c_service_2100_21a0:
    movff       ram_0x0A0, ram_0x0DF
    movff       ram_0x0B9, ram_0x0E0
    bra         flow_main_i2c_service_2100_21e0
flow_main_i2c_service_2100_21aa:
    movff       ram_0x0A0, ram_0x1D9
    movff       ram_0x0B9, ram_0x1DA
    bra         flow_main_i2c_service_2100_21e0
flow_main_i2c_service_2100_21b4:
    movff       ram_0x0A0, ram_0x0E4
    movff       ram_0x0B9, ram_0x0E5
    bra         flow_main_i2c_service_2100_21e0
flow_main_i2c_service_2100_21be:
    movff       ram_0x0A0, ram_0x1E0
    movff       ram_0x0B9, ram_0x1E1
    bra         flow_main_i2c_service_2100_21e0
flow_main_i2c_service_2100_21c8:
    movf        ram_0x059, W, ACCESS
    bz          flow_main_i2c_service_2100_218c
    xorlw       0x01
    bz          flow_main_i2c_service_2100_2196
    xorlw       0x03
    bz          flow_main_i2c_service_2100_21a0
    xorlw       0x01
    bz          flow_main_i2c_service_2100_21aa
    xorlw       0x07
    bz          flow_main_i2c_service_2100_21b4
    xorlw       0x01
    bz          flow_main_i2c_service_2100_21be
flow_main_i2c_service_2100_21e0:
    incf        ram_0x059, F, ACCESS
    movlw       0x05
    cpfsgt      ram_0x059, ACCESS
    bra         i2c_apply_channel_route_sync_burst__map_next_channel_route_pair
    clrf        ram_0x05A, ACCESS
    bra         i2c_apply_channel_route_sync_burst__stage_next_dsp_source_block
flow_main_i2c_service_2100_21ec:
    movff       ram_0x0D7, ram_0x06A
    movff       ram_0x0D8, ram_0x06B
    movff       ram_0x0D9, ram_0x06C
    movff       ram_0x0DA, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
flow_main_i2c_service_2100_21fe:
    movff       ram_0x0DB, ram_0x06A
    movff       ram_0x0DC, ram_0x06B
    movff       ram_0x0DD, ram_0x06C
    movff       ram_0x0DE, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
flow_main_i2c_service_2100_2210:
    movff       ram_0x0DF, ram_0x06A
    movff       ram_0x0E0, ram_0x06B
    movff       ram_0x0E1, ram_0x06C
    movff       ram_0x0E2, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
flow_main_i2c_service_2100_2222:
    movff       ram_0x1D9, ram_0x06A
    movff       ram_0x1DA, ram_0x06B
    movff       ram_0x1DB, ram_0x06C
    movff       ram_0x1DC, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
flow_main_i2c_service_2100_2234:
    movff       ram_0x0E3, ram_0x06A
    movff       ram_0x0E4, ram_0x06B
    movff       ram_0x0E5, ram_0x06C
    movff       ram_0x0E6, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
flow_main_i2c_service_2100_2246:
    movff       ram_0x1DD, ram_0x06A
    movff       ram_0x1DE, ram_0x06B
    movff       ram_0x1DF, ram_0x06C
    movff       ram_0x1E0, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
flow_main_i2c_service_2100_2258:
    movff       ram_0x1E1, ram_0x06A
    movff       ram_0x1E2, ram_0x06B
    movff       ram_0x1E3, ram_0x06C
    movff       ram_0x1E4, ram_0x06D
    bra         i2c_apply_channel_route_sync_burst__start_next_dsp_transaction
i2c_apply_channel_route_sync_burst__stage_next_dsp_source_block:
    movf        ram_0x05A, W, ACCESS
    bz          flow_main_i2c_service_2100_21ec
    xorlw       0x01
    bz          flow_main_i2c_service_2100_21fe
    xorlw       0x03
    bz          flow_main_i2c_service_2100_2210
    xorlw       0x01
    bz          flow_main_i2c_service_2100_2222
    xorlw       0x07
    bz          flow_main_i2c_service_2100_2234
    xorlw       0x01
    bz          flow_main_i2c_service_2100_2246
    xorlw       0x03
    bz          flow_main_i2c_service_2100_2258
i2c_apply_channel_route_sync_burst__start_next_dsp_transaction:
    bsf         SSPCON2, 0, ACCESS
flow_main_i2c_service_2100_2288:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_main_i2c_service_2100_2288
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlb       0x1
    movlw       0x0F
    addwf       ram_0x05A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    movf        INDF2, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        ram_0x05B, ACCESS
i2c_apply_channel_route_sync_burst__write_next_channel_coefficient:
    movf        ram_0x05B, W, ACCESS
    movlb       0x0
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    cpfseq      INDF2, ACCESS
    bra         i2c_apply_channel_route_sync_burst__check_source_code_three
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    movlw       0x3F
    bra         i2c_apply_channel_route_sync_burst__stage_forced_source_coefficients
i2c_apply_channel_route_sync_burst__check_source_code_three:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x03
    cpfseq      INDF2, ACCESS
    bra         i2c_apply_channel_route_sync_burst__compute_source_coefficients
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    movlw       0x80
    movwf       i2c_coeff_2, ACCESS
    movlw       0xBF
i2c_apply_channel_route_sync_burst__stage_forced_source_coefficients:
    movwf       i2c_coeff_3, ACCESS
    bra         i2c_apply_channel_route_sync_burst__write_staged_coefficients
i2c_apply_channel_route_sync_burst__compute_source_coefficients:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        uint8_to_float32_and_save, 0x0
    movff       ram_0x00D, i2c_coeff_0
    movff       ram_0x00E, i2c_coeff_1
    movff       ram_0x00F, i2c_coeff_2
    movff       ram_0x010, i2c_coeff_3
i2c_apply_channel_route_sync_burst__write_staged_coefficients:
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        i2c_emit_tas3108_coeff_from_staged_float, 0x0
    incf        ram_0x05B, F, ACCESS
    movlw       0x03
    cpfsgt      ram_0x05B, ACCESS
    bra         i2c_apply_channel_route_sync_burst__write_next_channel_coefficient
    bsf         SSPCON2, 2, ACCESS
flow_main_i2c_service_2100_231a:
    btfsc       SSPCON2, 2, ACCESS
    bra         flow_main_i2c_service_2100_231a
    incf        ram_0x05A, F, ACCESS
    movlw       0x06
    cpfsgt      ram_0x05A, ACCESS
    bra         i2c_apply_channel_route_sync_burst__stage_next_dsp_source_block
    retlw       0x06


; ---------------------------------------------------------------------------
; Function: stage_hid_ep1_in_report_from_selector
; Address : 0x2328
; Notes   : Inferred core helper routine. Calls: copy_indexed_fsr2_byte_to_hid_ep1_in.
; ---------------------------------------------------------------------------
stage_hid_ep1_in_report_from_selector:
    movff       ram_0x0C1, ram_0x15A
    bra         stage_hid_ep1_in_report_from_selector__dispatch_selector
stage_hid_ep1_in_report_from_selector__stage_selector3_page2_block:
    movff       ram_0x0C2, ram_0x15B
    movlw       0x02
    movwf       ram_0x003, ACCESS
stage_hid_ep1_in_report_from_selector__copy_selector3_payload_byte:
    movlw       0xBE
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    rcall       copy_indexed_fsr2_byte_to_hid_ep1_in
    movlw       0x1F
    cpfsgt      ram_0x003, ACCESS
    bra         stage_hid_ep1_in_report_from_selector__copy_selector3_payload_byte
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector4_opcode04_reply:
    movff       ram_0x0C2, ram_0x15B
    decf        ram_0x0C2, W, BANKED
    bnz         stage_hid_ep1_in_report_from_selector__check_selector4_mode2
    movff       ram_0x0B7, ram_0x15C
    movff       ram_0x0B8, ram_0x15D
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__check_selector4_mode2:
    movf        ram_0x0C2, W, BANKED
    xorlw       0x02
    bz          stage_hid_ep1_in_report_from_selector__stage_selector4_mode2_payload
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector4_mode2_payload:
    movff       ram_0x0B5, ram_0x15E
    movlw       0x05
    movwf       ram_0x003, ACCESS
stage_hid_ep1_in_report_from_selector__copy_selector4_page1_payload_byte:
    movlw       0xFB
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    rcall       copy_indexed_fsr2_byte_to_hid_ep1_in
    movlw       0x13
    cpfsgt      ram_0x003, ACCESS
    bra         stage_hid_ep1_in_report_from_selector__copy_selector4_page1_payload_byte
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot:
    movff       ram_0x093, ram_0x15B
    movff       input_select, ram_0x15C
    movlb       0x1
    clrf        ram_0x05D, BANKED
    clrf        active_flags, BANKED
    movff       computed_volume_3, ram_0x15F
    movff       computed_volume_2, ram_0x160
    movff       computed_volume_1, ram_0x161
    movff       computed_volume, ram_0x162
    movlw       0x00
    btfsc       active_flags, 4, ACCESS
    movlw       0x01
    movwf       ram_0x063, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 0, BANKED
    movlw       0x01
    movlb       0x1
    movwf       ram_0x064, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 1, BANKED
    movlw       0x01
    movlb       0x1
    movwf       ram_0x065, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 2, BANKED
    movlw       0x01
    movlb       0x1
    movwf       logical_volume, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 3, BANKED
    movlw       0x01
    movlb       0x1
    movwf       logical_volume_2, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 4, BANKED
    movlw       0x01
    movlb       0x1
    movwf       logical_volume_3, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 5, BANKED
    movlw       0x01
    movlb       0x1
    movwf       ram_0x06A, BANKED
    movff       ram_0x060, ram_0x16C
    movff       ram_0x061, ram_0x16D
    movff       ram_0x062, ram_0x16E
    movff       ram_0x063, ram_0x16F
    movff       ram_0x064, ram_0x170
    movff       ram_0x065, ram_0x171
    movff       ram_0x0B4, ram_0x178
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup:
    movlw       0x03
    movlb       0x1
    movwf       ram_0x05B, BANKED
    movlw       0x02
    movwf       ram_0x05C, BANKED
    movlw       0x03
    movwf       ram_0x05D, BANKED
    movff       input_select, ram_0x15E
    clrf        ram_0x05F, BANKED
    clrf        ram_0x060, BANKED
    clrf        ram_0x061, BANKED
    movff       ram_0x05F, ram_0x163
    movlw       0x06
    movwf       ram_0x064, BANKED
    movlw       0x0F
    movwf       ram_0x065, BANKED
    movwf       logical_volume, BANKED
    movwf       logical_volume_1, BANKED
    movwf       logical_volume_2, BANKED
    movwf       logical_volume_3, BANKED
    movwf       ram_0x06A, BANKED
    movlw       0x0A
    movwf       ram_0x06B, BANKED
    movwf       ram_0x06C, BANKED
    movwf       ram_0x06D, BANKED
    movwf       computed_volume, BANKED
    movwf       computed_volume_1, BANKED
    movwf       computed_volume_2, BANKED
    movlw       0x01
    movwf       computed_volume_3, BANKED
    movwf       ram_0x072, BANKED
    movff       ram_0x09B, ram_0x173
    movff       ram_0x09C, ram_0x174
    movff       ram_0x09D, ram_0x175
    movff       ram_0x09E, ram_0x176
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo:
    movff       ram_0x11B, ram_0x15B
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_empty_reply:
    movlb       0x1
    clrf        ram_0x05B, BANKED
    clrf        ram_0x05C, BANKED
    clrf        ram_0x05D, BANKED
    clrf        active_flags, BANKED
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__dispatch_selector:
    movlb       0x0
    movf        ram_0x0C1, W, BANKED
    xorlw       0x03
    bnz         stage_hid_ep1_in_report_from_selector__check_selector4
    bra         stage_hid_ep1_in_report_from_selector__stage_selector3_page2_block
stage_hid_ep1_in_report_from_selector__check_selector4:
    xorlw       0x07
    bnz         stage_hid_ep1_in_report_from_selector__check_selector5
    bra         stage_hid_ep1_in_report_from_selector__stage_selector4_opcode04_reply
stage_hid_ep1_in_report_from_selector__check_selector5:
    xorlw       0x01
    bnz         stage_hid_ep1_in_report_from_selector__check_selector6_or_echo_range
    bra         stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot
stage_hid_ep1_in_report_from_selector__check_selector6_or_echo_range:
    xorlw       0x03
    bz          stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup
    xorlw       0x01
    bz          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    xorlw       0x0F
    bz          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    xorlw       0x01
    bz          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    xorlw       0x03
    bz          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    xorlw       0x01
    bz          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    xorlw       0x07
    bz          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    bra         stage_hid_ep1_in_report_from_selector__stage_empty_reply
stage_hid_ep1_in_report_from_selector__clear_selector_and_return:
    movlb       0x0
    clrf        ram_0x0C1, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: copy_indexed_fsr2_byte_to_hid_ep1_in
; Address : 0x24AC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
copy_indexed_fsr2_byte_to_hid_ep1_in:
    addwfc      FSR2H, F, ACCESS
    movlw       0x5A
    addwf       ram_0x003, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x003, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: float32_add_secondary_to_primary_in_place
; Address : 0x24C2
; Notes   : Inferred core helper routine. Calls: main_core_service_2650, twos_complement_024_027_after_low_byte_complement, float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
float32_add_secondary_to_primary_in_place:
    movff       ram_0x020, ram_0x028
    movff       ram_0x021, ram_0x029
    movff       ram_0x022, ram_0x02A
    movff       ram_0x023, ram_0x02B
    movlw       0x18
    bra         flow_main_core_service_24c2_24d8
flow_main_core_service_24c2_24d6:
    rcall       main_core_service_2650
flow_main_core_service_24c2_24d8:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_24c2_24d6
    movf        ram_0x028, W, ACCESS
    movwf       ram_0x02E, ACCESS
    movff       ram_0x024, ram_0x028
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movlw       0x18
    bra         flow_main_core_service_24c2_24f6
flow_main_core_service_24c2_24f4:
    rcall       main_core_service_2650
flow_main_core_service_24c2_24f6:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_24c2_24f4
    movf        ram_0x028, W, ACCESS
    movwf       ram_0x02D, ACCESS
    movf        ram_0x02E, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__return_secondary_as_dominant_operand
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__check_primary_dominant_or_zero_secondary
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         float32_add_secondary_to_primary_in_place__check_primary_dominant_or_zero_secondary
float32_add_secondary_to_primary_in_place__return_secondary_as_dominant_operand:
    movff       ram_0x024, ram_0x020
    movff       ram_0x025, ram_0x021
    movff       ram_0x026, ram_0x022
    movff       ram_0x027, ram_0x023
    bra         float32_add_secondary_to_primary_in_place__return
float32_add_secondary_to_primary_in_place__check_primary_dominant_or_zero_secondary:
    movf        ram_0x02D, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__return_primary_as_dominant_operand
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__prepare_signed_mantissas_for_aligned_add
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         float32_add_secondary_to_primary_in_place__prepare_signed_mantissas_for_aligned_add
float32_add_secondary_to_primary_in_place__return_primary_as_dominant_operand:
    movff       ram_0x020, ram_0x020
    movff       ram_0x021, ram_0x021
    movff       ram_0x022, ram_0x022
    movff       ram_0x023, ram_0x023
    bra         float32_add_secondary_to_primary_in_place__return
float32_add_secondary_to_primary_in_place__prepare_signed_mantissas_for_aligned_add:
    movlw       0x06
    movwf       ram_0x02C, ACCESS
    btfsc       ram_0x023, 7, ACCESS
    bsf         ram_0x02C, 7, ACCESS
    btfsc       ram_0x027, 7, ACCESS
    bsf         ram_0x02C, 6, ACCESS
    bsf         ram_0x022, 7, ACCESS
    clrf        ram_0x023, ACCESS
    bsf         ram_0x026, 7, ACCESS
    clrf        ram_0x027, ACCESS
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__check_primary_higher_alignment_needed
float32_add_secondary_to_primary_in_place__left_shift_secondary_toward_primary_exponent:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x024, F, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    decf        ram_0x02D, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__finish_secondary_higher_alignment
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          float32_add_secondary_to_primary_in_place__finish_secondary_higher_alignment
    bra         float32_add_secondary_to_primary_in_place__left_shift_secondary_toward_primary_exponent
float32_add_secondary_to_primary_in_place__right_shift_primary_to_match_secondary:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x023, F, ACCESS
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    incf        ram_0x02E, F, ACCESS
float32_add_secondary_to_primary_in_place__finish_secondary_higher_alignment:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         float32_add_secondary_to_primary_in_place__right_shift_primary_to_match_secondary
    bra         float32_add_secondary_to_primary_in_place__apply_primary_sign_if_needed
float32_add_secondary_to_primary_in_place__check_primary_higher_alignment_needed:
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__apply_primary_sign_if_needed
float32_add_secondary_to_primary_in_place__left_shift_primary_toward_secondary_exponent:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x020, F, ACCESS
    rlcf        ram_0x021, F, ACCESS
    rlcf        ram_0x022, F, ACCESS
    rlcf        ram_0x023, F, ACCESS
    decf        ram_0x02E, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__finish_primary_higher_alignment
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          float32_add_secondary_to_primary_in_place__finish_primary_higher_alignment
    bra         float32_add_secondary_to_primary_in_place__left_shift_primary_toward_secondary_exponent
float32_add_secondary_to_primary_in_place__right_shift_secondary_to_match_primary:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    rrcf        ram_0x024, F, ACCESS
    incf        ram_0x02D, F, ACCESS
float32_add_secondary_to_primary_in_place__finish_primary_higher_alignment:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         float32_add_secondary_to_primary_in_place__right_shift_secondary_to_match_primary
float32_add_secondary_to_primary_in_place__apply_primary_sign_if_needed:
    btfss       ram_0x02C, 7, ACCESS
    bra         float32_add_secondary_to_primary_in_place__apply_secondary_sign_if_needed
    comf        ram_0x020, F, ACCESS
    comf        ram_0x021, F, ACCESS
    comf        ram_0x022, F, ACCESS
    comf        ram_0x023, F, ACCESS
    incf        ram_0x020, F, ACCESS
    movlw       0x00
    addwfc      ram_0x021, F, ACCESS
    addwfc      ram_0x022, F, ACCESS
    addwfc      ram_0x023, F, ACCESS
float32_add_secondary_to_primary_in_place__apply_secondary_sign_if_needed:
    btfss       ram_0x02C, 6, ACCESS
    bra         float32_add_secondary_to_primary_in_place__add_aligned_signed_mantissas
    comf        ram_0x024, F, ACCESS
    rcall       twos_complement_024_027_after_low_byte_complement
float32_add_secondary_to_primary_in_place__add_aligned_signed_mantissas:
    clrf        ram_0x02C, ACCESS
    movf        ram_0x020, W, ACCESS
    addwf       ram_0x024, F, ACCESS
    movf        ram_0x021, W, ACCESS
    addwfc      ram_0x025, F, ACCESS
    movf        ram_0x022, W, ACCESS
    addwfc      ram_0x026, F, ACCESS
    movf        ram_0x023, W, ACCESS
    addwfc      ram_0x027, F, ACCESS
    btfss       ram_0x027, 7, ACCESS
    bra         float32_add_secondary_to_primary_in_place__pack_sum_result
    comf        ram_0x024, F, ACCESS
    rcall       twos_complement_024_027_after_low_byte_complement
    movlw       0x01
    movwf       ram_0x02C, ACCESS
float32_add_secondary_to_primary_in_place__pack_sum_result:
    movff       ram_0x024, ram_0x003
    movff       ram_0x025, ram_0x004
    movff       ram_0x026, ram_0x005
    movff       ram_0x027, ram_0x006
    movff       ram_0x02E, ram_0x007
    movff       ram_0x02C, ram_0x008
    call        float32_pack_mantissa_exponent_sign, 0x0
    movff       ram_0x003, ram_0x020
    movff       ram_0x004, ram_0x021
    movff       ram_0x005, ram_0x022
    movff       ram_0x006, ram_0x023
float32_add_secondary_to_primary_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: twos_complement_024_027_after_low_byte_complement
; Address : 0x263E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
twos_complement_024_027_after_low_byte_complement:
    comf        ram_0x025, F, ACCESS
    comf        ram_0x026, F, ACCESS
    comf        ram_0x027, F, ACCESS
    incf        ram_0x024, F, ACCESS
    movlw       0x00
    addwfc      ram_0x025, F, ACCESS
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    retlw       0x00


; ---------------------------------------------------------------------------
; Function: main_core_service_2650
; Address : 0x2650
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2650:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x02B, F, ACCESS
    rrcf        ram_0x02A, F, ACCESS
    rrcf        ram_0x029, F, ACCESS
    rrcf        ram_0x028, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: persist_dirty_runtime_state_to_eeprom
; Address : 0x265C
; Notes   : Inferred core helper routine. Calls: eeprom_write_byte_if_changed.
; ---------------------------------------------------------------------------
persist_dirty_runtime_state_to_eeprom:
    movlb       0x0
    btfss       event_flags, 0, BANKED
    bra         persist_dirty_runtime_state_to_eeprom__return
    btfss       ram_0x0BD, 0, BANKED
    bra         flow_main_core_service_265c_26cc
    clrf        ram_0x008, ACCESS
    movlw       0x03
    movwf       ram_0x007, ACCESS
    movff       computed_volume, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x02
    movwf       ram_0x007, ACCESS
    movff       computed_volume_1, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x01
    movwf       ram_0x007, ACCESS
    movff       computed_volume_2, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    movlw       0x00
    clrf        ram_0x008, ACCESS
    clrf        ram_0x007, ACCESS
    movff       computed_volume_3, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x04
    movwf       ram_0x007, ACCESS
    movff       input_select, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0D
    movwf       ram_0x007, ACCESS
    movff       ram_0x05F, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x14
    movwf       ram_0x007, ACCESS
    movff       ram_0x0C3, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 0, BANKED
flow_main_core_service_265c_26cc:
    btfss       ram_0x0BD, 1, BANKED
    bra         flow_main_core_service_265c_2728
    clrf        ram_0x008, ACCESS
    movlw       0x07
    movwf       ram_0x007, ACCESS
    movff       ram_0x060, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x08
    movwf       ram_0x007, ACCESS
    movff       ram_0x061, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x09
    movwf       ram_0x007, ACCESS
    movff       ram_0x062, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0A
    movwf       ram_0x007, ACCESS
    movff       ram_0x063, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0B
    movwf       ram_0x007, ACCESS
    movff       ram_0x064, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0C
    movwf       ram_0x007, ACCESS
    movff       ram_0x065, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 1, BANKED
flow_main_core_service_265c_2728:
    btfss       ram_0x0BD, 2, BANKED
    bra         flow_main_core_service_265c_274c
    clrf        ram_0x008, ACCESS
    movlw       0x0F
    movwf       ram_0x007, ACCESS
    movff       ram_0x0B4, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0E
    movwf       ram_0x007, ACCESS
    movff       ram_0x0B8, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 2, BANKED
flow_main_core_service_265c_274c:
    btfss       ram_0x0BD, 3, BANKED
    bra         persist_dirty_runtime_state_to_eeprom__check_filter_window_dirty
    clrf        ram_0x008, ACCESS
    movlw       0x10
    movwf       ram_0x007, ACCESS
    movff       ram_0x09B, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x11
    movwf       ram_0x007, ACCESS
    movff       ram_0x09C, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x12
    movwf       ram_0x007, ACCESS
    movff       ram_0x09D, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x13
    movwf       ram_0x007, ACCESS
    movff       ram_0x09E, ram_0x009
    call        eeprom_write_byte_if_changed, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 3, BANKED
persist_dirty_runtime_state_to_eeprom__check_filter_window_dirty:
    btfss       ram_0x0BD, 4, BANKED
    bra         persist_dirty_runtime_state_to_eeprom__check_filename_dirty
    movlw       0x50
    movwf       ram_0x00A, ACCESS
persist_dirty_runtime_state_to_eeprom__persist_filter_window_byte:
    movff       ram_0x00A, ram_0x007
    clrf        ram_0x008, ACCESS
    movlb       0x1
    movlw       0xB0
    addwf       ram_0x00A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    addwfc      FSR2H, F, ACCESS
    movf        INDF2, W, ACCESS
    movwf       ram_0x009, ACCESS
    call        eeprom_write_byte_if_changed, 0x0
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         persist_dirty_runtime_state_to_eeprom__persist_filter_window_byte
    movlb       0x0
    bcf         ram_0x0BD, 4, BANKED
persist_dirty_runtime_state_to_eeprom__check_filename_dirty:
    btfss       ram_0x0BD, 5, BANKED
    bra         persist_dirty_runtime_state_to_eeprom__clear_filename_usb_transaction_gate
    movlw       0x60
    movwf       ram_0x00A, ACCESS
flow_main_core_service_265c_27c4:
    movff       ram_0x00A, ram_0x007
    clrf        ram_0x008, ACCESS
    movlb       0x2
    movlw       0x60
    addwf       ram_0x00A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    movf        INDF2, W, ACCESS
    movwf       ram_0x009, ACCESS
    call        eeprom_write_byte_if_changed, 0x0
    incf        ram_0x00A, F, ACCESS
    movlw       0x7D
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_core_service_265c_27c4
    movlb       0x0
    bcf         ram_0x0BD, 5, BANKED
persist_dirty_runtime_state_to_eeprom__clear_filename_usb_transaction_gate:
    bcf         event_flags, 0, BANKED
persist_dirty_runtime_state_to_eeprom__return:
    return      0


; ---------------------------------------------------------------------------
; Function: poll_src4382_route_monitor
; Address : 0x27F0
; Notes   : Inferred i2c helper routine. Calls: i2c_secondary_dev_write, i2c_secondary_dev_random_read.
; ---------------------------------------------------------------------------
poll_src4382_route_monitor:
    btfss       active_flags, 3, ACCESS
    bra         poll_src4382_route_monitor__return
    movlw       0x64
    movlb       0x0
    cpfsgt      ram_0x0BB, BANKED
    bra         poll_src4382_route_monitor__increment_refresh_watchdog
    clrf        ram_0x0BB, BANKED
    bra         poll_src4382_route_monitor__compute_route_request
poll_src4382_route_monitor__stage_next_autodetect_candidate:
    movf        ram_0x0B6, W, BANKED
    addlw       0x08
    movwf       ram_0x0BE, BANKED
    bra         poll_src4382_route_monitor__handle_autodetect_state
flow_main_i2c_service_27f0_2808:
    clrf        ram_0x093, BANKED
    bra         poll_src4382_route_monitor__handle_autodetect_state
flow_main_i2c_service_27f0_280c:
    movlw       0x01
    movwf       ram_0x093, BANKED
    movf        ram_0x05F, W, ACCESS
    bz          poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x05
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_2818:
    movlw       0x02
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_2824
    movlw       0x01
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2824:
    movlw       0x01
    cpfsgt      ram_0x05F, ACCESS
    bra         poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x06
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_282e:
    movlw       0x03
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_283a
    movlw       0x02
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_283a:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2844
    movlw       0x01
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2844:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x07
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_284e:
    movlw       0x04
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_285a
    movlw       0x03
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_285a:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2864
    movlw       0x02
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2864:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x01
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_286e:
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_2876
    movlw       0x04
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2876:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2880
    movlw       0x03
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2880:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x02
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_288a:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2894
    movlw       0x04
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2894:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x03
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_289e:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         poll_src4382_route_monitor__handle_autodetect_state
    movlw       0x04
flow_main_i2c_service_27f0_28a6:
    movwf       ram_0x093, BANKED
    bra         poll_src4382_route_monitor__handle_autodetect_state
poll_src4382_route_monitor__compute_route_request:
    movf        input_select, W, BANKED
    bz          poll_src4382_route_monitor__stage_next_autodetect_candidate
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_2808
    xorlw       0x03
    bz          flow_main_i2c_service_27f0_280c
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_2818
    xorlw       0x07
    bz          flow_main_i2c_service_27f0_282e
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_284e
    xorlw       0x03
    bz          flow_main_i2c_service_27f0_286e
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_288a
    xorlw       0x0F
    bz          flow_main_i2c_service_27f0_289e
poll_src4382_route_monitor__handle_autodetect_state:
    tstfsz      input_select, BANKED
    bra         poll_src4382_route_monitor__reset_autodetect_scan
    movff       ram_0x0BE, ram_0x006
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x13
    call        i2c_secondary_dev_random_read, 0x0
    movlb       0x0
    movwf       ram_0x0BE, BANKED
    tstfsz      ram_0x0BE, BANKED
    bra         poll_src4382_route_monitor__handle_rx_status_present
    clrf        ram_0x093, BANKED
    movlw       0x0A
    cpfsgt      ram_0x0BA, BANKED
    bra         flow_main_i2c_service_27f0_2906
    clrf        ram_0x0BA, BANKED
    movlw       0x04
    subwf       ram_0x0B6, W, BANKED
    btfss       STATUS, 0, ACCESS
    incf        ram_0x0B6, F, BANKED
    movf        ram_0x0B6, W, BANKED
    xorlw       0x04
    bnz         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__reset_autodetect_scan:
    clrf        ram_0x0B6, BANKED
    bra         poll_src4382_route_monitor__finalize_pending_route
flow_main_i2c_service_27f0_2906:
    incf        ram_0x0BA, F, BANKED
    bra         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__handle_rx_status_present:
    tstfsz      ram_0x0B6, BANKED
    bra         poll_src4382_route_monitor__check_scan_index1
    movlw       0x03
    movwf       ram_0x093, BANKED
poll_src4382_route_monitor__check_scan_index1:
    decf        ram_0x0B6, W, BANKED
    bnz         poll_src4382_route_monitor__check_scan_index2
    movlw       0x01
    movwf       ram_0x093, BANKED
poll_src4382_route_monitor__check_scan_index2:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x02
    bnz         poll_src4382_route_monitor__check_scan_index3
    movlw       0x02
    movwf       ram_0x093, BANKED
poll_src4382_route_monitor__check_scan_index3:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x03
    bnz         poll_src4382_route_monitor__read_audio_format
    movlw       0x04
    movwf       ram_0x093, BANKED
poll_src4382_route_monitor__read_audio_format:
    movlw       0x12
    call        i2c_secondary_dev_random_read, 0x0
    movlb       0x0
    movwf       ram_0x0BF, BANKED
    movf        ram_0x0BF, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x008, ACCESS
    movlw       0x01
    btfss       active_flags, 5, ACCESS
    movlw       0x00
    xorwf       ram_0x008, F, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 5, BANKED
    btfss       active_flags, 4, ACCESS
    bra         poll_src4382_route_monitor__clear_nonpcm_mute_mirror
    bsf         active_flags, 5, ACCESS
    bra         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__clear_nonpcm_mute_mirror:
    bcf         active_flags, 5, ACCESS
poll_src4382_route_monitor__finalize_pending_route:
    movlb       0x0
    movf        ram_0x093, W, BANKED
    xorlw       0x02
    btfsc       STATUS, 2, ACCESS
    btfsc       PORTC, 0, ACCESS
    bra         poll_src4382_route_monitor__compare_pending_route
    movff       ram_0x0C3, ram_0x093
poll_src4382_route_monitor__compare_pending_route:
    movf        ram_0x0AB, W, BANKED
    xorwf       ram_0x093, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 1, BANKED
    movff       ram_0x093, ram_0x0AB
    bra         poll_src4382_route_monitor__return
poll_src4382_route_monitor__increment_refresh_watchdog:
    incf        ram_0x0BB, F, BANKED
poll_src4382_route_monitor__return:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_exp_limit1024_in_place
; Address : 0x297E
; Notes   : Inferred core helper routine. Calls: float32_divide_primary_by_secondary_in_place, float32_add_secondary_to_primary_in_place, float32_multiply_ram_window_by_staged_operand_in_place.
; ---------------------------------------------------------------------------
float32_exp_limit1024_in_place:
    clrf        ram_0x011, ACCESS
    clrf        ram_0x012, ACCESS
    movlw       0x80
    movwf       ram_0x013, ACCESS
    movlw       0x44
    movwf       ram_0x014, ACCESS
    movff       ram_0x02F, ram_0x00D
    movff       ram_0x030, ram_0x00E
    movff       ram_0x031, ram_0x00F
    movff       ram_0x032, ram_0x010
    call        float32_divide_primary_by_secondary_in_place, 0x0
    movff       ram_0x00D, ram_0x020
    movff       ram_0x00E, ram_0x021
    movff       ram_0x00F, ram_0x022
    movff       ram_0x010, ram_0x023
    clrf        ram_0x024, ACCESS
    clrf        ram_0x025, ACCESS
    movlw       0x80
    movwf       ram_0x026, ACCESS
    movlw       0x3F
    movwf       ram_0x027, ACCESS
    call        float32_add_secondary_to_primary_in_place, 0x0
    movff       ram_0x020, ram_0x02F
    movff       ram_0x021, ram_0x030
    movff       ram_0x022, ram_0x031
    movff       ram_0x023, ram_0x032
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    movff       ram_0x02F, ram_0x02F
    movff       ram_0x030, ram_0x030
    movff       ram_0x031, ram_0x031
    movff       ram_0x032, ram_0x032
    return      0


; ---------------------------------------------------------------------------
; Function: float32_multiply_primary_by_secondary_in_place
; Address : 0x2ABC
; Notes   : Inferred core helper routine. Calls: main_core_service_2bac, add_shifted_multiplicand_to_product_accumulator, shift_multiplier_mantissa_right_clear_c.
; ---------------------------------------------------------------------------
float32_multiply_primary_by_secondary_in_place:
    movff       ram_0x012, ram_0x01A
    movff       ram_0x013, ram_0x01B
    movff       ram_0x014, ram_0x01C
    movff       ram_0x015, ram_0x01D
    movlw       0x18
    bra         flow_main_core_service_2abc_2ad2
flow_main_core_service_2abc_2ad0:
    rcall       main_core_service_2bac
flow_main_core_service_2abc_2ad2:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2abc_2ad0
    movf        ram_0x01A, W, ACCESS
    movwf       ram_0x01E, ACCESS
    tstfsz      ram_0x01E, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__unpack_secondary_top_byte
    bra         float32_multiply_primary_by_secondary_in_place__clear_zero_result
float32_multiply_primary_by_secondary_in_place__unpack_secondary_top_byte:
    movff       ram_0x016, ram_0x01A
    movff       ram_0x017, ram_0x01B
    movff       ram_0x018, ram_0x01C
    movff       ram_0x019, ram_0x01D
    movlw       0x18
    bra         flow_main_core_service_2abc_2af6
flow_main_core_service_2abc_2af4:
    rcall       main_core_service_2bac
flow_main_core_service_2abc_2af6:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2abc_2af4
    movf        ram_0x01A, W, ACCESS
    movwf       ram_0x024, ACCESS
    tstfsz      ram_0x024, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas
float32_multiply_primary_by_secondary_in_place__clear_zero_result:
    clrf        ram_0x012, ACCESS
    clrf        ram_0x013, ACCESS
    clrf        ram_0x014, ACCESS
    clrf        ram_0x015, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__return
float32_multiply_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas:
    movf        ram_0x024, W, ACCESS
    addlw       0x7B
    addwf       ram_0x01E, F, ACCESS
    movff       ram_0x015, ram_0x024
    movf        ram_0x019, W, ACCESS
    xorwf       ram_0x024, F, ACCESS
    movlw       0x80
    andwf       ram_0x024, F, ACCESS
    bsf         ram_0x014, 7, ACCESS
    bsf         ram_0x018, 7, ACCESS
    clrf        ram_0x019, ACCESS
    clrf        ram_0x01F, ACCESS
    clrf        ram_0x020, ACCESS
    clrf        ram_0x021, ACCESS
    clrf        ram_0x022, ACCESS
    movlw       0x07
    movwf       ram_0x023, ACCESS
float32_multiply_primary_by_secondary_in_place__multiply_low_mantissa_bits:
    btfss       ram_0x012, 0, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_multiplicand
    movf        ram_0x016, W, ACCESS
    rcall       add_shifted_multiplicand_to_product_accumulator
float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_multiplicand:
    rcall       shift_multiplier_mantissa_right_clear_c
    rlcf        ram_0x016, F, ACCESS
    rlcf        ram_0x017, F, ACCESS
    rlcf        ram_0x018, F, ACCESS
    rlcf        ram_0x019, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__multiply_low_mantissa_bits
    movlw       0x11
    movwf       ram_0x023, ACCESS
float32_multiply_primary_by_secondary_in_place__multiply_high_mantissa_bits:
    btfss       ram_0x012, 0, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_product
    movf        ram_0x016, W, ACCESS
    rcall       add_shifted_multiplicand_to_product_accumulator
float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_product:
    rcall       shift_multiplier_mantissa_right_clear_c
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    rrcf        ram_0x01F, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__multiply_high_mantissa_bits
    movff       ram_0x01F, ram_0x003
    movff       ram_0x020, ram_0x004
    movff       ram_0x021, ram_0x005
    movff       ram_0x022, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x024, ram_0x008
    call        float32_pack_mantissa_exponent_sign, 0x0
    movff       ram_0x003, ram_0x012
    movff       ram_0x004, ram_0x013
    movff       ram_0x005, ram_0x014
    movff       ram_0x006, ram_0x015
float32_multiply_primary_by_secondary_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: add_shifted_multiplicand_to_product_accumulator
; Address : 0x2B8E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
add_shifted_multiplicand_to_product_accumulator:
    addwf       ram_0x01F, F, ACCESS
    movf        ram_0x017, W, ACCESS
    addwfc      ram_0x020, F, ACCESS
    movf        ram_0x018, W, ACCESS
    addwfc      ram_0x021, F, ACCESS
    movf        ram_0x019, W, ACCESS
    addwfc      ram_0x022, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: shift_multiplier_mantissa_right_clear_c
; Address : 0x2B9E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
shift_multiplier_mantissa_right_clear_c:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x015, F, ACCESS
    rrcf        ram_0x014, F, ACCESS
    rrcf        ram_0x013, F, ACCESS
    rrcf        ram_0x012, F, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2bac
; Address : 0x2BAC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2bac:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x01D, F, ACCESS
    rrcf        ram_0x01C, F, ACCESS
    rrcf        ram_0x01B, F, ACCESS
    rrcf        ram_0x01A, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: fw_update_commit_hid_payload_page
; Address : 0x2BB8
; Notes   : Inferred flash helper routine. Calls: flash_read, flash_erase, flash_write.
; ---------------------------------------------------------------------------
fw_update_commit_hid_payload_page:
    tstfsz      ram_0x0C5, BANKED
    bra         fw_update_commit_hid_payload_page__copy_staged_payload
    movff       ram_0x082, ram_0x003
    movff       ram_0x083, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    clrf        ram_0x008, ACCESS
    movlw       0xC0
    movwf       ram_0x007, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       ram_0x00A, ACCESS
    movlw       0x00
    movwf       ram_0x009, ACCESS
    call        flash_read, 0x0
fw_update_commit_hid_payload_page__copy_staged_payload:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    bz          flow_main_flash_service_2bb8_2bea
    clrf        ram_0x01D, ACCESS
    movlw       0x02
    movwf       ram_0x01C, ACCESS
    bra         flow_main_flash_service_2bb8_2bee
flow_main_flash_service_2bb8_2bea:
    clrf        ram_0x01C, ACCESS
    clrf        ram_0x01D, ACCESS
flow_main_flash_service_2bb8_2bee:
    movff       ram_0x01C, ram_0x01E
    movlw       0x04
    movwf       ram_0x01F, ACCESS
flow_main_flash_service_2bb8_2bf6:
    movlw       0x1A
    movwf       ram_0x018, ACCESS
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movf        ram_0x01F, W, ACCESS
    addwf       ram_0x018, F, ACCESS
    movlw       0x00
    addwfc      ram_0x019, F, ACCESS
    movf        ram_0x01E, W, ACCESS
    subwf       ram_0x018, W, ACCESS
    movwf       FSR2L, ACCESS
    movf        ram_0x019, W, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x019, W, ACCESS
    movwf       FSR2H, ACCESS
    movlw       0x00
    movwf       ram_0x01A, ACCESS
    movlw       0x03
    movwf       ram_0x01B, ACCESS
    movlb       0x0
    movf        ram_0x0C5, W, BANKED
    addwf       ram_0x01A, F, ACCESS
    movlw       0x00
    addwfc      ram_0x01B, F, ACCESS
    movf        ram_0x01F, W, ACCESS
    addwf       ram_0x01A, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      ram_0x01B, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x01F, F, ACCESS
    movlw       0x17
    cpfsgt      ram_0x01F, ACCESS
    bra         flow_main_flash_service_2bb8_2bf6
    movlw       0x18
    addwf       ram_0x0C5, F, BANKED
    movlw       0xBF
    cpfsgt      ram_0x0C5, BANKED
    bra         fw_update_commit_hid_payload_page__return
    clrf        ram_0x0C5, BANKED
    movlw       0x3F
    subwf       ram_0x082, W, BANKED
    movlw       0x5F
    subwfb      ram_0x083, W, BANKED
    bc          fw_update_commit_hid_payload_page__return
    movff       ram_0x082, ram_0x003
    movff       ram_0x083, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movlw       0xBF
    addwf       ram_0x082, W, BANKED
    movwf       ram_0x018, ACCESS
    movlw       0x00
    addwfc      ram_0x083, W, BANKED
    movwf       ram_0x019, ACCESS
    movff       ram_0x018, ram_0x007
    movff       ram_0x019, ram_0x008
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    call        flash_erase, 0x0
    movff       ram_0x082, ram_0x003
    movff       ram_0x083, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    clrf        ram_0x008, ACCESS
    movlw       0xC0
    movwf       ram_0x007, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       ram_0x00A, ACCESS
    movlw       0x00
    movwf       ram_0x009, ACCESS
    call        flash_write, 0x0
    movlw       0xC0
    movlb       0x0
    addwf       ram_0x082, F, BANKED
    movlw       0x00
    addwfc      ram_0x083, F, BANKED
fw_update_commit_hid_payload_page__return:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_divide_primary_by_secondary_in_place
; Address : 0x2CA8
; Notes   : Inferred core helper routine. Calls: main_core_service_2d80, float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
float32_divide_primary_by_secondary_in_place:
    movff       ram_0x00D, ram_0x015
    movff       ram_0x00E, ram_0x016
    movff       ram_0x00F, ram_0x017
    movff       ram_0x010, ram_0x018
    movlw       0x18
    bra         flow_main_core_service_2ca8_2cbe
flow_main_core_service_2ca8_2cbc:
    rcall       main_core_service_2d80
flow_main_core_service_2ca8_2cbe:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2ca8_2cbc
    movf        ram_0x015, W, ACCESS
    movwf       ram_0x01E, ACCESS
    tstfsz      ram_0x01E, ACCESS
    bra         float32_divide_primary_by_secondary_in_place__unpack_divisor_top_byte
    bra         float32_divide_primary_by_secondary_in_place__clear_zero_result
float32_divide_primary_by_secondary_in_place__unpack_divisor_top_byte:
    movff       ram_0x011, ram_0x015
    movff       ram_0x012, ram_0x016
    movff       ram_0x013, ram_0x017
    movff       ram_0x014, ram_0x018
    movlw       0x18
    bra         flow_main_core_service_2ca8_2ce2
flow_main_core_service_2ca8_2ce0:
    rcall       main_core_service_2d80
flow_main_core_service_2ca8_2ce2:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2ca8_2ce0
    movf        ram_0x015, W, ACCESS
    movwf       ram_0x01F, ACCESS
    tstfsz      ram_0x01F, ACCESS
    bra         float32_divide_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas
float32_divide_primary_by_secondary_in_place__clear_zero_result:
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x010, ACCESS
    bra         flow_main_core_service_2ca8_2d7e
float32_divide_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas:
    movf        ram_0x01F, W, ACCESS
    addlw       0x89
    subwf       ram_0x01E, F, ACCESS
    movff       ram_0x010, ram_0x01F
    movf        ram_0x014, W, ACCESS
    xorwf       ram_0x01F, F, ACCESS
    movlw       0x80
    andwf       ram_0x01F, F, ACCESS
    bsf         ram_0x00F, 7, ACCESS
    clrf        ram_0x010, ACCESS
    bsf         ram_0x013, 7, ACCESS
    clrf        ram_0x014, ACCESS
    movlw       0x20
    movwf       ram_0x01D, ACCESS
float32_divide_primary_by_secondary_in_place__division_step_compare_subtract:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x019, F, ACCESS
    rlcf        ram_0x01A, F, ACCESS
    rlcf        ram_0x01B, F, ACCESS
    rlcf        ram_0x01C, F, ACCESS
    movf        ram_0x011, W, ACCESS
    subwf       ram_0x00D, W, ACCESS
    movf        ram_0x012, W, ACCESS
    subwfb      ram_0x00E, W, ACCESS
    movf        ram_0x013, W, ACCESS
    subwfb      ram_0x00F, W, ACCESS
    movf        ram_0x014, W, ACCESS
    subwfb      ram_0x010, W, ACCESS
    bnc         float32_divide_primary_by_secondary_in_place__advance_remainder_next_bit
    movf        ram_0x011, W, ACCESS
    subwf       ram_0x00D, F, ACCESS
    movf        ram_0x012, W, ACCESS
    subwfb      ram_0x00E, F, ACCESS
    movf        ram_0x013, W, ACCESS
    subwfb      ram_0x00F, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwfb      ram_0x010, F, ACCESS
    bsf         ram_0x019, 0, ACCESS
float32_divide_primary_by_secondary_in_place__advance_remainder_next_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x00D, F, ACCESS
    rlcf        ram_0x00E, F, ACCESS
    rlcf        ram_0x00F, F, ACCESS
    rlcf        ram_0x010, F, ACCESS
    decfsz      ram_0x01D, F, ACCESS
    bra         float32_divide_primary_by_secondary_in_place__division_step_compare_subtract
    movff       ram_0x019, ram_0x003
    movff       ram_0x01A, ram_0x004
    movff       ram_0x01B, ram_0x005
    movff       ram_0x01C, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x01F, ram_0x008
    call        float32_pack_mantissa_exponent_sign, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
flow_main_core_service_2ca8_2d7e:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2d80
; Address : 0x2D80
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2d80:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x018, F, ACCESS
    rrcf        ram_0x017, F, ACCESS
    rrcf        ram_0x016, F, ACCESS
    rrcf        ram_0x015, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: run_wake_rail_gate_and_dsp_cold_init
; Address : 0x2D8C
; Notes   : Inferred uart helper; touches adc,timer,uart. Calls: timer3_blocking_delay, main_i2c_service_4966, mssp_hard_reset.
; ---------------------------------------------------------------------------
run_wake_rail_gate_and_dsp_cold_init:
    bcf         INTCON, 7, ACCESS
    bcf         LATB, 2, ACCESS
    movlb       0x0
    clrf        ram_0x088, BANKED
    clrf        ram_0x089, BANKED
    bsf         ADCON0, 1, ACCESS
adc_boot_gate__poll_an0_rail_ready:
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    btfsc       ADCON0, 1, ACCESS
    bra         adc_boot_gate__check_rail_threshold
    movf        ADRESH, W, ACCESS
    movwf       ram_0x05D, ACCESS
    clrf        ram_0x05C, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       ram_0x05C, W, ACCESS
    movlb       0x0
    movwf       ram_0x088, BANKED
    movlw       0x00
    addwfc      ram_0x05D, W, ACCESS
    movwf       ram_0x089, BANKED
    bsf         ADCON0, 1, ACCESS
adc_boot_gate__check_rail_threshold:
    movlw       0x36
    movlb       0x0
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bnc         adc_boot_gate__poll_an0_rail_ready
adc_boot_gate__start_dsp_cold_init:
    clrf        ram_0x004, ACCESS
    movlw       0x46
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
    bcf         LATB, 4, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATB, 3, ACCESS
    call        main_i2c_service_4966, 0x0
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    clrf        ram_0x004, ACCESS
    movlw       0x64
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    bsf         LATB, 4, ACCESS
    movlw       0x05
    movwf       ram_0x004, ACCESS
    movlw       0xDC
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    movlw       0x80
    movwf       ram_0x003, ACCESS
    movlw       0x08
    call        mssp_hard_reset, 0x0
    bsf         LATA, 6, ACCESS
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    call        preset_replay_selected_table_blocking, 0x0
    bsf         LATB, 3, ACCESS
    call        timer3_blocking_delay_2ms, 0x0
    call        i2c_secondary_apply_wake_init_table, 0x0
    call        timer3_blocking_delay_2ms, 0x0
    movlb       0x0
    bsf         event_flags, 1, BANKED
    bsf         event_flags, 3, BANKED
    bsf         event_flags, 4, BANKED
    bsf         ram_0x07F, 0, BANKED
    bsf         ram_0x07F, 1, BANKED
    movlw       0x00
    call        cmd_dispatch_gated, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    bcf         INTCON, 5, ACCESS
    bcf         T0CON, 7, ACCESS
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    movlb       0x0
    clrf        ram_0x0A1, BANKED
    bcf         ram_0x094, 2, BANKED
    bsf         INTCON, 7, ACCESS
    goto        usb_reinit_after_wake__clear_pending_and_poll_host

; ---------------------------------------------------------------------------
; Function: flash_write
; Address : 0x2E6E
; Notes   : Inferred flash helper; touches flash. Calls: nvm_unlock_and_set_wr.
; ---------------------------------------------------------------------------
flash_write:
    clrf        ram_0x010, ACCESS
    movff       ram_0x003, ram_0x014
    movff       ram_0x004, ram_0x015
    movff       ram_0x005, ram_0x016
    movff       ram_0x006, ram_0x017
    movlw       0x05
    movwf       ram_0x00B, ACCESS
flash_write__shift_start_addr_to_block_index:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    decfsz      ram_0x00B, F, ACCESS
    bra         flash_write__shift_start_addr_to_block_index
    movlw       0x05
flash_write__restore_block_base_from_index:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    decfsz      WREG, F, ACCESS
    bra         flash_write__restore_block_base_from_index
    movlw       0x20
    addwf       ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movwf       ram_0x00F, ACCESS
    bra         flash_write__check_remaining_byte_count
flash_write__start_next_block:
    movff       ram_0x016, ram_0x013
    movff       ram_0x015, ram_0x012
    movff       ram_0x014, ram_0x011
    bra         flash_write__test_block_bytes_remaining
flash_write__copy_next_source_byte:
    movff       ram_0x009, FSR2L
    movff       ram_0x00A, FSR2H
    movf        INDF2, W, ACCESS
    movff       ram_0x011, TBLPTRL
    movff       ram_0x012, TBLPTRH
    movff       ram_0x013, TBLPTRU
    movwf       TABLAT, ACCESS
    tblwt*
    infsnz      ram_0x009, F, ACCESS
    incf        ram_0x00A, F, ACCESS
    incf        ram_0x011, F, ACCESS
    movlw       0x00
    addwfc      ram_0x012, F, ACCESS
    addwfc      ram_0x013, F, ACCESS
    decf        ram_0x007, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x008, F, ACCESS
    movf        ram_0x008, W, ACCESS
    iorwf       ram_0x007, W, ACCESS
    bz          flash_write__prepare_block_commit
flash_write__test_block_bytes_remaining:
    decf        ram_0x00F, F, ACCESS
    incf        ram_0x00F, W, ACCESS
    bnz         flash_write__copy_next_source_byte
flash_write__prepare_block_commit:
    movff       ram_0x013, ram_0x00E
    movff       ram_0x012, ram_0x00D
    movff       ram_0x011, ram_0x00C
    movff       ram_0x016, ram_0x013
    movff       ram_0x015, ram_0x012
    movff       ram_0x014, ram_0x011
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flash_write__unlock_and_clear_wren
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x010, ACCESS
flash_write__unlock_and_clear_wren:
    call        nvm_unlock_and_set_wr, 0x0
    bcf         EECON1, 2, ACCESS
    movf        ram_0x010, W, ACCESS
    bz          flash_write__reload_next_block_cursor
    bsf         INTCON, 7, ACCESS
    clrf        ram_0x010, ACCESS
flash_write__reload_next_block_cursor:
    movlw       0x20
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00C, W, ACCESS
    movwf       ram_0x014, ACCESS
    movf        ram_0x00D, W, ACCESS
    movwf       ram_0x015, ACCESS
    movf        ram_0x00E, W, ACCESS
    movwf       ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
flash_write__check_remaining_byte_count:
    movf        ram_0x008, W, ACCESS
    iorwf       ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flash_write__start_next_block


; ---------------------------------------------------------------------------
; Function: usb_sie_endpoint_pump
; Address : 0x2F4E
; Notes   : Inferred usb helper; touches usb. Calls: usb_poll_host_presence_reinit_or_shutdown, usb_clear_activity_interrupt_after_settle, usb_bus_reset_reinitialize.
; ---------------------------------------------------------------------------
usb_sie_endpoint_pump:
    call        usb_poll_host_presence_reinit_or_shutdown, 0x0
    tstfsz      ram_0x0CD, BANKED
    bra         usb_sie_endpoint_pump__service_enabled_state
    bra         usb_sie_endpoint_pump__return
usb_sie_endpoint_pump__service_enabled_state:
    btfsc       UIR, 2, ACCESS
    call        usb_clear_activity_interrupt_after_settle, 0x0
    btfsc       UCON, 1, ACCESS
    bra         usb_sie_endpoint_pump__return
    btfsc       UIR, 0, ACCESS
    call        usb_bus_reset_reinitialize, 0x0
    btfsc       UIR, 4, ACCESS
    call        main_usb_service_4720, 0x0
    movlw       0x03
    movlb       0x0
    subwf       ram_0x0CD, W, BANKED
    bnc         usb_sie_endpoint_pump__return
    clrf        ram_0x0C4, BANKED
usb_sie_endpoint_pump__poll_transaction_flag:
    btfss       UIR, 3, ACCESS
    bra         usb_sie_endpoint_pump__return
    movf        USTAT, W, ACCESS
    movff       USTAT, ram_0x006
    movlw       0x7C
    andwf       ram_0x006, F, ACCESS
    bnz         usb_sie_endpoint_pump__service_ep0_in_token_if_selected
    btfsc       USTAT, 1, ACCESS
    bra         flow_main_usb_service_2f4e_2f96
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
    movlw       0x00
    bra         usb_sie_endpoint_pump__select_ep0_out_bd
flow_main_usb_service_2f4e_2f96:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
usb_sie_endpoint_pump__select_ep0_out_bd:
    movlb       0x0
    movwf       ram_0x07A, BANKED
    bcf         UIR, 3, ACCESS
    movff       ram_0x07A, FSR2L
    movff       ram_0x07B, FSR2H
    rrcf        INDF2, W, ACCESS
    rrcf        WREG, F, ACCESS
    andlw       0x0F
    xorlw       0x0D
    bnz         usb_sie_endpoint_pump__advance_transaction_scan
    clrf        ram_0x090, BANKED
usb_sie_endpoint_pump__copy_setup_packet_byte:
    lfsr        FSR2, 0x0002
    movf        ram_0x07A, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        ram_0x07B, W, BANKED
    addwfc      FSR2H, F, ACCESS
    movff       POSTINC2, ram_0x006
    movff       POSTDEC2, ram_0x007
    movff       ram_0x006, FSR2L
    movff       ram_0x007, FSR2H
    movf        ram_0x090, W, BANKED
    addlw       0xCF
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movff       INDF2, INDF1
    lfsr        FSR2, 0x0002
    movf        ram_0x07A, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        ram_0x07B, W, BANKED
    addwfc      FSR2H, F, ACCESS
    incf        POSTINC2, F, ACCESS
    movlw       0x00
    addwfc      POSTDEC2, F, ACCESS
    incf        ram_0x090, F, BANKED
    movlw       0x07
    cpfsgt      ram_0x090, BANKED
    bra         usb_sie_endpoint_pump__copy_setup_packet_byte
    call        usb_ep0_service_setup_transaction, 0x0
    bra         usb_sie_endpoint_pump__advance_transaction_scan
usb_sie_endpoint_pump__service_ep0_in_token_if_selected:
    movf        USTAT, W, ACCESS
    xorlw       0x04
    bnz         flow_main_usb_service_2f4e_300c
    bcf         UIR, 3, ACCESS
    call        usb_ep0_service_in_transaction, 0x0
    bra         usb_sie_endpoint_pump__advance_transaction_scan
flow_main_usb_service_2f4e_300c:
    bcf         UIR, 3, ACCESS
usb_sie_endpoint_pump__advance_transaction_scan:
    movlb       0x0
    incf        ram_0x0C4, F, BANKED
    movlw       0x03
    cpfsgt      ram_0x0C4, BANKED
    bra         usb_sie_endpoint_pump__poll_transaction_flag
usb_sie_endpoint_pump__return:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_to_int32_in_place
; Address : 0x301A
; Notes   : Inferred core helper routine. Calls: main_core_service_30cc.
; ---------------------------------------------------------------------------
float32_to_int32_in_place:
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movff       ram_0x028, ram_0x02C
    movlw       0x18
    bra         flow_main_core_service_301a_3030
flow_main_core_service_301a_302e:
    rcall       main_core_service_30cc
flow_main_core_service_301a_3030:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_301a_302e
    movf        ram_0x029, W, ACCESS
    movwf       ram_0x02E, ACCESS
    tstfsz      ram_0x02E, ACCESS
    bra         float32_to_int32_in_place__unpack_sign_and_mantissa
float32_to_int32_in_place__clear_zero_or_out_of_range:
    clrf        ram_0x025, ACCESS
    clrf        ram_0x026, ACCESS
    clrf        ram_0x027, ACCESS
    clrf        ram_0x028, ACCESS
    bra         float32_to_int32_in_place__return
float32_to_int32_in_place__unpack_sign_and_mantissa:
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movff       ram_0x028, ram_0x02C
    movlw       0x20
    bra         flow_main_core_service_301a_305c
flow_main_core_service_301a_305a:
    rcall       main_core_service_30cc
flow_main_core_service_301a_305c:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_301a_305a
    movf        ram_0x029, W, ACCESS
    movwf       ram_0x02D, ACCESS
    bsf         ram_0x027, 7, ACCESS
    clrf        ram_0x028, ACCESS
    movlw       0x96
    subwf       ram_0x02E, F, ACCESS
    btfss       ram_0x02E, 7, ACCESS
    bra         float32_to_int32_in_place__check_left_shift_range
    movf        ram_0x02E, W, ACCESS
    xorlw       0x80
    movwf       ram_0x029, ACCESS
    movlw       0xE9
    xorlw       0x80
    subwf       ram_0x029, W, ACCESS
    bnc         float32_to_int32_in_place__clear_zero_or_out_of_range
float32_to_int32_in_place__shift_right_until_exponent_zero:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x028, F, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    incfsz      ram_0x02E, F, ACCESS
    bra         float32_to_int32_in_place__shift_right_until_exponent_zero
    bra         float32_to_int32_in_place__apply_sign_if_needed
float32_to_int32_in_place__check_left_shift_range:
    movlw       0x1F
    cpfsgt      ram_0x02E, ACCESS
    bra         float32_to_int32_in_place__shift_left_until_exponent_zero
    bra         float32_to_int32_in_place__clear_zero_or_out_of_range
float32_to_int32_in_place__shift_left_next_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    rlcf        ram_0x028, F, ACCESS
    decf        ram_0x02E, F, ACCESS
float32_to_int32_in_place__shift_left_until_exponent_zero:
    tstfsz      ram_0x02E, ACCESS
    bra         float32_to_int32_in_place__shift_left_next_bit
float32_to_int32_in_place__apply_sign_if_needed:
    movf        ram_0x02D, W, ACCESS
    bz          float32_to_int32_in_place__positive_result_ready
    comf        ram_0x028, F, ACCESS
    comf        ram_0x027, F, ACCESS
    comf        ram_0x026, F, ACCESS
    negf        ram_0x025, ACCESS
    movlw       0x00
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    addwfc      ram_0x028, F, ACCESS
float32_to_int32_in_place__positive_result_ready:
    movff       ram_0x025, ram_0x025
    movff       ram_0x026, ram_0x026
    movff       ram_0x027, ram_0x027
    movff       ram_0x028, ram_0x028
float32_to_int32_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_30cc
; Address : 0x30CC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_30cc:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x02C, F, ACCESS
    rrcf        ram_0x02B, F, ACCESS
    rrcf        ram_0x02A, F, ACCESS
    rrcf        ram_0x029, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: float32_pack_mantissa_exponent_sign
; Address : 0x30D8
; Notes   : Inferred core helper routine. Calls: shift_003_006_right_clear_c.
; ---------------------------------------------------------------------------
float32_pack_mantissa_exponent_sign:
    movf        ram_0x007, W, ACCESS
    bz          float32_pack_mantissa_exponent_sign__clear_zero_result
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    iorwf       ram_0x004, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         float32_pack_mantissa_exponent_sign__trim_high_guard_bits
float32_pack_mantissa_exponent_sign__clear_zero_result:
    clrf        ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    bra         float32_pack_mantissa_exponent_sign__return
float32_pack_mantissa_exponent_sign__shift_right_increment_exponent:
    incf        ram_0x007, F, ACCESS
    rcall       shift_003_006_right_clear_c
float32_pack_mantissa_exponent_sign__trim_high_guard_bits:
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    movlw       0xFE
    andwf       ram_0x006, W, ACCESS
    movwf       ram_0x00C, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    iorwf       ram_0x00B, W, ACCESS
    bz          float32_pack_mantissa_exponent_sign__check_guard_byte
    bra         float32_pack_mantissa_exponent_sign__shift_right_increment_exponent
float32_pack_mantissa_exponent_sign__round_guard_and_shift_right:
    incf        ram_0x007, F, ACCESS
    incf        ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    rcall       shift_003_006_right_clear_c
float32_pack_mantissa_exponent_sign__check_guard_byte:
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    movf        ram_0x006, W, ACCESS
    movwf       ram_0x00C, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    iorwf       ram_0x00B, W, ACCESS
    bz          float32_pack_mantissa_exponent_sign__normalize_left_to_mantissa_msb
    bra         float32_pack_mantissa_exponent_sign__round_guard_and_shift_right
float32_pack_mantissa_exponent_sign__shift_left_decrement_exponent:
    decf        ram_0x007, F, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
float32_pack_mantissa_exponent_sign__normalize_left_to_mantissa_msb:
    btfss       ram_0x005, 7, ACCESS
    bra         float32_pack_mantissa_exponent_sign__shift_left_decrement_exponent
    btfsc       ram_0x007, 0, ACCESS
    bra         float32_pack_mantissa_exponent_sign__merge_exponent_and_sign_bits
    movlw       0x7F
    andwf       ram_0x005, F, ACCESS
float32_pack_mantissa_exponent_sign__merge_exponent_and_sign_bits:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x007, F, ACCESS
    movff       ram_0x007, ram_0x009
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    clrf        ram_0x00C, ACCESS
    movff       ram_0x009, ram_0x00C
    clrf        ram_0x00B, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x009, ACCESS
    movf        ram_0x009, W, ACCESS
    iorwf       ram_0x003, F, ACCESS
    movf        ram_0x00A, W, ACCESS
    iorwf       ram_0x004, F, ACCESS
    movf        ram_0x00B, W, ACCESS
    iorwf       ram_0x005, F, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x006, F, ACCESS
    movf        ram_0x008, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x006, 7, ACCESS
    movff       ram_0x003, ram_0x003
    movff       ram_0x004, ram_0x004
    movff       ram_0x005, ram_0x005
    movff       ram_0x006, ram_0x006
float32_pack_mantissa_exponent_sign__return:
    return      0


; ---------------------------------------------------------------------------
; Function: shift_003_006_right_clear_c
; Address : 0x3188
; Notes   : Inferred core helper routine. Calls: main_core_service_496e, main_core_service_496c, usb_ep0_arm_out_pingpong_bd.
; ---------------------------------------------------------------------------
shift_003_006_right_clear_c:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    return      0
usb_ep0_dispatch_hid_setup_request:
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         usb_ep0_dispatch_hid_setup_request__return
    movf        ram_0x0D3, W, BANKED
    bnz         usb_ep0_dispatch_hid_setup_request__return
    movf        ram_0x0D0, W, BANKED
    xorlw       0x06
    bz          usb_ep0_dispatch_hid_setup_request__decode_get_descriptor_type
    bra         usb_ep0_dispatch_hid_setup_request__decode_class_request_type
usb_ep0_dispatch_hid_setup_request__stage_hid_descriptor:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x3E
    movwf       ram_0x075, BANKED
    clrf        ram_0x0E8, BANKED
    movlw       0x09
    bra         usb_ep0_dispatch_hid_setup_request__store_descriptor_length
usb_ep0_dispatch_hid_setup_request__handle_report_descriptor_request:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    decf        ram_0x0EB, W, BANKED
    bnz         usb_ep0_dispatch_hid_setup_request__maybe_set_report_descriptor_length
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x55
    movwf       ram_0x075, BANKED
usb_ep0_dispatch_hid_setup_request__maybe_set_report_descriptor_length:
    decf        ram_0x0EB, W, BANKED
    bnz         usb_ep0_dispatch_hid_setup_request__set_table_source_flag
    clrf        ram_0x0E8, BANKED
    movlw       0x1D
usb_ep0_dispatch_hid_setup_request__store_descriptor_length:
    movwf       ram_0x0E7, BANKED
    bra         usb_ep0_dispatch_hid_setup_request__set_table_source_flag
usb_ep0_dispatch_hid_setup_request__decode_get_descriptor_type:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x21
    bz          usb_ep0_dispatch_hid_setup_request__stage_hid_descriptor
    xorlw       0x03
    bz          usb_ep0_dispatch_hid_setup_request__handle_report_descriptor_request
    xorlw       0x01
usb_ep0_dispatch_hid_setup_request__set_table_source_flag:
    bsf         ram_0x0CE, 1, BANKED
usb_ep0_dispatch_hid_setup_request__decode_class_request_type:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         usb_ep0_dispatch_hid_setup_request__return
    bra         usb_ep0_dispatch_hid_setup_request__decode_class_request_code
flow_main_core_service_3188_31f4:
    call        main_core_service_496e, 0x0
    bra         usb_ep0_dispatch_hid_setup_request__return
flow_main_core_service_3188_31fa:
    call        main_core_service_496c, 0x0
    bra         usb_ep0_dispatch_hid_setup_request__return
usb_ep0_dispatch_hid_setup_request__stage_get_idle_reply:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEA
flow_main_core_service_3188_3208:
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         usb_ep0_dispatch_hid_setup_request__return
usb_ep0_dispatch_hid_setup_request__store_set_idle_duration:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D2, ram_0x0EA
    bra         usb_ep0_dispatch_hid_setup_request__return
usb_ep0_dispatch_hid_setup_request__stage_get_protocol_reply:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xE9
    bra         flow_main_core_service_3188_3208
usb_ep0_dispatch_hid_setup_request__store_set_protocol_value:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D1, ram_0x0E9
    bra         usb_ep0_dispatch_hid_setup_request__return
usb_ep0_dispatch_hid_setup_request__decode_class_request_code:
    movf        ram_0x0D0, W, BANKED
    xorlw       0x01
    bz          flow_main_core_service_3188_31f4
    xorlw       0x03
    bz          usb_ep0_dispatch_hid_setup_request__stage_get_idle_reply
    xorlw       0x01
    bz          usb_ep0_dispatch_hid_setup_request__stage_get_protocol_reply
    xorlw       0x0A
    bz          flow_main_core_service_3188_31fa
    xorlw       0x03
    bz          usb_ep0_dispatch_hid_setup_request__store_set_idle_duration
    xorlw       0x01
    bz          usb_ep0_dispatch_hid_setup_request__store_set_protocol_value
usb_ep0_dispatch_hid_setup_request__return:
    return      0
usb_ep0_arm_control_transfer_response:
    tstfsz      ram_0x0C8, BANKED
    bra         usb_ep0_arm_control_transfer_response__dispatch_by_direction
    movlw       0x04
    movlb       0x4
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         flow_main_core_service_3188_326c
    movlw       0x01
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    clrf        ram_0x096, BANKED
    bra         usb_ep0_arm_control_transfer_response__return
flow_main_core_service_3188_326c:
    movlw       0x00
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    bra         usb_ep0_arm_control_transfer_response__return
usb_ep0_arm_control_transfer_response__dispatch_by_direction:
    btfss       ram_0x0CF, 7, BANKED
    bra         usb_ep0_arm_control_transfer_response__handle_host_to_device_stage
    movlw       0x01
    movwf       ram_0x0C9, BANKED
    movf        ram_0x0E7, W, BANKED
    subwf       ram_0x0D5, W, BANKED
    movf        ram_0x0E8, W, BANKED
    subwfb      ram_0x0D6, W, BANKED
    bc          usb_ep0_arm_control_transfer_response__stage_in_data_packet
    movff       ram_0x0D5, ram_0x0E7
    movff       ram_0x0D6, ram_0x0E8
usb_ep0_arm_control_transfer_response__stage_in_data_packet:
    call        usb_ep0_stage_in_data_packet, 0x0
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x01
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    movlw       0x00
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    movlb       0x4
    movlw       0x04
    movwf       ram_0x00B, BANKED
    movlw       0x24
    movwf       ram_0x00A, BANKED
    bra         usb_ep0_arm_control_transfer_response__arm_in_bd
usb_ep0_arm_control_transfer_response__handle_host_to_device_stage:
    movlw       0x02
    movwf       ram_0x0C9, BANKED
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         usb_ep0_arm_control_transfer_response__arm_next_out_stage
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
usb_ep0_arm_control_transfer_response__arm_next_out_stage:
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         flow_main_core_service_3188_32dc
    movlw       0x01
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    clrf        ram_0x096, BANKED
    bra         usb_ep0_arm_control_transfer_response__maybe_arm_zero_length_in_status
flow_main_core_service_3188_32dc:
    movlw       0x00
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
usb_ep0_arm_control_transfer_response__maybe_arm_zero_length_in_status:
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         usb_ep0_arm_control_transfer_response__return
    movlb       0x4
    clrf        ram_0x009, BANKED
usb_ep0_arm_control_transfer_response__arm_in_bd:
    movlw       0x48
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
usb_ep0_arm_control_transfer_response__return:
    return      0


; ---------------------------------------------------------------------------
; Function: i2c_secondary_apply_wake_init_table
; Address : 0x32F8
; Notes   : Inferred i2c helper routine. Calls: i2c_wait_bus_idle, i2c_secondary_dev_write.
; ---------------------------------------------------------------------------
i2c_secondary_apply_wake_init_table:
    call        i2c_wait_bus_idle, 0x0
    movlw       0x3F
    movwf       ram_0x006, ACCESS
    movlw       0x01
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x03
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x04
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x05
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x06
    call        i2c_secondary_dev_write, 0x0
    movlw       0x34
    movwf       ram_0x006, ACCESS
    movlw       0x07
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0E
    call        i2c_secondary_dev_write, 0x0
    movlw       0x22
    movwf       ram_0x006, ACCESS
    movlw       0x0F
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x10
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x11
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x1D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x02
    movwf       ram_0x006, ACCESS
    movlw       0x2D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x20
    movwf       ram_0x006, ACCESS
    movlw       0x2E
    goto        i2c_secondary_dev_write


; ---------------------------------------------------------------------------
; Function: truncate_float32_to_integral_float_in_place
; Address : 0x3398
; Notes   : Inferred core helper routine. Calls: fw_update_signature_status_word_helper, float32_to_int32_in_place, int32_to_float32_and_save.
; ---------------------------------------------------------------------------
truncate_float32_to_integral_float_in_place:
    movff       ram_0x02F, ram_0x003
    movff       ram_0x030, ram_0x004
    movff       ram_0x031, ram_0x005
    movff       ram_0x032, ram_0x006
    movlw       0x37
    movwf       ram_0x007, ACCESS
    call        fw_update_signature_status_word_helper, 0x0
    movf        ram_0x038, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       ram_0x037, W, ACCESS
    bc          truncate_float32_to_integral_float_in_place__check_already_integral_range
    clrf        ram_0x02F, ACCESS
    clrf        ram_0x030, ACCESS
    clrf        ram_0x031, ACCESS
    clrf        ram_0x032, ACCESS
    bra         truncate_float32_to_integral_float_in_place__return
truncate_float32_to_integral_float_in_place__check_already_integral_range:
    movlw       0x1D
    subwf       ram_0x037, W, ACCESS
    movlw       0x00
    subwfb      ram_0x038, W, ACCESS
    bnc         truncate_float32_to_integral_float_in_place__convert_through_int32
    movff       ram_0x02F, ram_0x02F
    movff       ram_0x030, ram_0x030
    movff       ram_0x031, ram_0x031
    movff       ram_0x032, ram_0x032
    bra         truncate_float32_to_integral_float_in_place__return
truncate_float32_to_integral_float_in_place__convert_through_int32:
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    call        float32_to_int32_in_place, 0x0
    movff       ram_0x025, ram_0x00D
    movff       ram_0x026, ram_0x00E
    movff       ram_0x027, ram_0x00F
    movff       ram_0x028, ram_0x010
    call        int32_to_float32_and_save, 0x0
    movff       ram_0x00D, ram_0x033
    movff       ram_0x00E, ram_0x034
    movff       ram_0x00F, ram_0x035
    movff       ram_0x010, ram_0x036
    movff       ram_0x033, ram_0x02F
    movff       ram_0x034, ram_0x030
    movff       ram_0x035, ram_0x031
    movff       ram_0x036, ram_0x032
truncate_float32_to_integral_float_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_apply_clear_set_feature_request
; Address : 0x3432
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_apply_clear_set_feature_request:
    decf        ram_0x0D1, W, BANKED
    bnz         usb_ep0_apply_clear_set_feature_request__check_endpoint_halt
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bnz         usb_ep0_apply_clear_set_feature_request__check_endpoint_halt
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D0, W, BANKED
    xorlw       0x03
    bnz         usb_ep0_apply_clear_set_feature_request__clear_device_remote_wakeup
    bsf         ram_0x0CE, 0, BANKED
    bra         usb_ep0_apply_clear_set_feature_request__check_endpoint_halt
usb_ep0_apply_clear_set_feature_request__clear_device_remote_wakeup:
    bcf         ram_0x0CE, 0, BANKED
usb_ep0_apply_clear_set_feature_request__check_endpoint_halt:
    tstfsz      ram_0x0D1, BANKED
    bra         usb_ep0_apply_clear_set_feature_request__return
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    xorlw       0x02
    bnz         usb_ep0_apply_clear_set_feature_request__return
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    bz          usb_ep0_apply_clear_set_feature_request__return
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    mullw       0x08
    movlw       0x04
    movwf       ram_0x003, ACCESS
    movwf       ram_0x004, ACCESS
    movf        PRODL, W, ACCESS
    addwf       ram_0x003, F, ACCESS
    movf        PRODH, W, ACCESS
    addwfc      ram_0x004, F, ACCESS
    movlw       0x01
    btfss       ram_0x0D3, 7, BANKED
    movlw       0x00
    mullw       0x04
    movf        PRODL, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       ram_0x072, BANKED
    movf        PRODH, W, ACCESS
    addwfc      ram_0x004, W, ACCESS
    movwf       ram_0x073, BANKED
    movf        ram_0x0D0, W, BANKED
    xorlw       0x03
    bnz         usb_ep0_apply_clear_set_feature_request__clear_in_endpoint_halt
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x04
    bra         usb_ep0_apply_clear_set_feature_request__write_endpoint_halt_status
usb_ep0_apply_clear_set_feature_request__clear_in_endpoint_halt:
    btfss       ram_0x0D3, 7, BANKED
    bra         usb_ep0_apply_clear_set_feature_request__clear_out_endpoint_halt
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x40
    movwf       INDF2, ACCESS
    bra         usb_ep0_apply_clear_set_feature_request__return
usb_ep0_apply_clear_set_feature_request__clear_out_endpoint_halt:
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x08
usb_ep0_apply_clear_set_feature_request__write_endpoint_halt_status:
    movwf       INDF2, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x00
    bsf         PLUSW2, 7, ACCESS
usb_ep0_apply_clear_set_feature_request__return:
    return      0


; ---------------------------------------------------------------------------
; Function: format_uint16_radix_ascii_to_w_pointer
; Address : 0x34C8
; Notes   : Inferred core helper routine. Calls: adc_divide_staged_words, adc_remainder_staged_words.
; ---------------------------------------------------------------------------
format_uint16_radix_ascii_to_w_pointer:
    movff       WREG, ram_0x011
    movff       ram_0x00A, ram_0x00E
    movff       ram_0x00B, ram_0x00F
format_uint16_radix_ascii_to_w_pointer__count_digits:
    movff       ram_0x00E, ram_0x003
    movff       ram_0x00F, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        adc_divide_staged_words, 0x0
    movff       ram_0x003, ram_0x00E
    movff       ram_0x004, ram_0x00F
    incf        ram_0x011, F, ACCESS
    movf        ram_0x00F, W, ACCESS
    iorwf       ram_0x00E, W, ACCESS
    bnz         format_uint16_radix_ascii_to_w_pointer__count_digits
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    clrf        INDF2, ACCESS
    decf        ram_0x011, F, ACCESS
format_uint16_radix_ascii_to_w_pointer__emit_next_digit:
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        adc_remainder_staged_words, 0x0
    movf        ram_0x003, W, ACCESS
    movwf       ram_0x010, ACCESS
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        adc_divide_staged_words, 0x0
    movff       ram_0x003, ram_0x00A
    movff       ram_0x004, ram_0x00B
    movlw       0x09
    cpfsgt      ram_0x010, ACCESS
    bra         format_uint16_radix_ascii_to_w_pointer__store_ascii_digit
    movlw       0x07
    addwf       ram_0x010, F, ACCESS
format_uint16_radix_ascii_to_w_pointer__store_ascii_digit:
    movlw       0x30
    addwf       ram_0x010, F, ACCESS
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x010, INDF2
    decf        ram_0x011, F, ACCESS
    movf        ram_0x00B, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    bnz         format_uint16_radix_ascii_to_w_pointer__emit_next_digit
    incf        ram_0x011, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: boot_init_peripherals_and_enter_adc_gate
; Address : 0x355C
; Notes   : Inferred i2c helper; touches adc,i2c,timer. Calls: eeprom_read_byte, flash_write_with_gie_off, eeprom_write_byte_if_changed.
; ---------------------------------------------------------------------------
boot_init_peripherals_and_enter_adc_gate:
    clrf        INTCON, ACCESS
    clrf        PIE1, ACCESS
    clrf        PIE2, ACCESS
    clrf        PIR1, ACCESS
    clrf        PIR2, ACCESS
    clrf        PORTA, ACCESS
    clrf        PORTB, ACCESS
    clrf        PORTC, ACCESS
    movlw       0x07
    movwf       TRISA, ACCESS
    clrf        TRISB, ACCESS
    movlw       0x87
    movwf       TRISC, ACCESS
    movlw       0x70
    movwf       OSCCON, ACCESS
    movlw       0x38
    movwf       SSPCON1, ACCESS
    movlw       0x01
    movwf       ADCON0, ACCESS
    movlw       0x0C
    movwf       ADCON1, ACCESS
    movlw       0xB5
    movwf       ADCON2, ACCESS
    movlw       0x07
    movwf       T0CON, ACCESS
    movlw       0x80
    movwf       T1CON, ACCESS
    movlw       0x77
    movwf       SSPADD, ACCESS
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0FE, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0xFF
    setf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x77
    bz          boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits
    clrf        ram_0x004, ACCESS
    movlw       0xFF
    setf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x88
    bz          boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits
    movlb       0x0
    clrf        ram_0x0FE, BANKED
boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits:
    movlb       0x0
    movf        ram_0x0FE, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        flash_write_with_gie_off, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        eeprom_write_byte_if_changed, 0x0
    bsf         PORTB, 6, ACCESS
    call        adaptive_baud_select, 0x0
    movlw       0x03
    movwf       ram_0x004, ACCESS
    movlw       0xE8
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    call        restore_eeprom_settings_on_boot, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         active_flags, 3, ACCESS
    goto        run_wake_rail_gate_and_dsp_cold_init


; ---------------------------------------------------------------------------
; Function: usb_ep0_stage_in_data_packet
; Address : 0x35F0
; Notes   : Inferred flash helper; touches flash. Calls: usb_ep0_prepare_in_data_copy_pointers, read_low_memory_byte_at_tblptr, usb_ep0_store_in_data_byte_and_advance.
; ---------------------------------------------------------------------------
usb_ep0_stage_in_data_packet:
    movlw       0x08
    movwf       ram_0x08F, BANKED
    subwf       ram_0x0E7, W, BANKED
    movlw       0x00
    subwfb      ram_0x0E8, W, BANKED
    bc          usb_ep0_stage_in_data_packet__stage_packet_length_and_buffer
    movff       ram_0x0E7, ram_0x08F
    tstfsz      ram_0x0CC, BANKED
    bra         usb_ep0_stage_in_data_packet__advance_data_toggle_state
    movlw       0x01
    bra         usb_ep0_stage_in_data_packet__store_data_toggle_state
usb_ep0_stage_in_data_packet__advance_data_toggle_state:
    decf        ram_0x0CC, W, BANKED
    bnz         usb_ep0_stage_in_data_packet__stage_packet_length_and_buffer
    movlw       0x02
usb_ep0_stage_in_data_packet__store_data_toggle_state:
    movwf       ram_0x0CC, BANKED
usb_ep0_stage_in_data_packet__stage_packet_length_and_buffer:
    movff       ram_0x08F, ram_0x409
    movf        ram_0x08F, W, BANKED
    subwf       ram_0x0E7, F, BANKED
    movlw       0x00
    subwfb      ram_0x0E8, F, BANKED
    movlw       0x04
    movlb       0x0
    movwf       ram_0x073, BANKED
    movlw       0x24
    movwf       ram_0x072, BANKED
    btfsc       ram_0x0CE, 1, BANKED
    bra         usb_ep0_stage_in_data_packet__check_table_source_remaining
    bra         usb_ep0_stage_in_data_packet__check_lowpage_source_remaining
usb_ep0_stage_in_data_packet__copy_table_source_byte:
    rcall       usb_ep0_prepare_in_data_copy_pointers
    cpfsgt      TBLPTRH, ACCESS
    bra         usb_ep0_stage_in_data_packet__read_lowpage_table_byte
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         usb_ep0_stage_in_data_packet__store_table_source_byte
usb_ep0_stage_in_data_packet__read_lowpage_table_byte:
    call        read_low_memory_byte_at_tblptr, 0x0
usb_ep0_stage_in_data_packet__store_table_source_byte:
    rcall       usb_ep0_store_in_data_byte_and_advance
usb_ep0_stage_in_data_packet__check_table_source_remaining:
    tstfsz      ram_0x08F, BANKED
    bra         usb_ep0_stage_in_data_packet__copy_table_source_byte
    bra         usb_ep0_stage_in_data_packet__return
usb_ep0_stage_in_data_packet__copy_lowpage_source_byte:
    rcall       usb_ep0_prepare_in_data_copy_pointers
    cpfsgt      TBLPTRH, ACCESS
    bra         usb_ep0_stage_in_data_packet__read_lowpage_source_byte
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         usb_ep0_stage_in_data_packet__store_lowpage_source_byte
usb_ep0_stage_in_data_packet__read_lowpage_source_byte:
    call        read_low_memory_byte_at_tblptr, 0x0
usb_ep0_stage_in_data_packet__store_lowpage_source_byte:
    rcall       usb_ep0_store_in_data_byte_and_advance
usb_ep0_stage_in_data_packet__check_lowpage_source_remaining:
    tstfsz      ram_0x08F, BANKED
    bra         usb_ep0_stage_in_data_packet__copy_lowpage_source_byte
usb_ep0_stage_in_data_packet__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_prepare_in_data_copy_pointers
; Address : 0x365C
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
usb_ep0_prepare_in_data_copy_pointers:
    movff       ram_0x075, TBLPTRL
    movff       ram_0x076, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x07
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_store_in_data_byte_and_advance
; Address : 0x3672
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_store_in_data_byte_and_advance:
    movwf       INDF2, ACCESS
    movlb       0x0
    infsnz      ram_0x072, F, BANKED
    incf        ram_0x073, F, BANKED
    infsnz      ram_0x075, F, BANKED
    incf        ram_0x076, F, BANKED
    decf        ram_0x08F, F, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_dispatch_standard_setup_request
; Address : 0x3682
; Notes   : Inferred core helper routine. Calls: usb_ep0_select_get_descriptor_payload, usb_apply_set_configuration, usb_ep0_prepare_get_status_reply.
; ---------------------------------------------------------------------------
usb_ep0_dispatch_standard_setup_request:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    bnz         usb_ep0_dispatch_standard_setup_request__return
    bra         usb_ep0_dispatch_standard_setup_request__dispatch_request_code
usb_ep0_dispatch_standard_setup_request__set_address:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x04
    movwf       ram_0x0CD, BANKED
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__get_descriptor:
    call        usb_ep0_select_get_descriptor_payload, 0x0
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__set_configuration:
    call        usb_apply_set_configuration, 0x0
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__get_configuration:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEB
    movwf       ram_0x075, BANKED
flow_main_core_service_3682_36ac:
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__get_status:
    call        usb_ep0_prepare_get_status_reply, 0x0
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__clear_or_set_feature:
    call        usb_ep0_apply_clear_set_feature_request, 0x0
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__get_interface:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       ram_0x005, ACCESS
    clrf        ram_0x076, BANKED
    movff       ram_0x005, ram_0x075
    bra         flow_main_core_service_3682_36ac
usb_ep0_dispatch_standard_setup_request__set_interface:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x0D1, INDF2
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__dispatch_request_code:
    movf        ram_0x0D0, W, BANKED
    bz          usb_ep0_dispatch_standard_setup_request__get_status
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__clear_or_set_feature
    xorlw       0x02
    bz          usb_ep0_dispatch_standard_setup_request__clear_or_set_feature
    xorlw       0x06
    bz          usb_ep0_dispatch_standard_setup_request__set_address
    xorlw       0x03
    bz          usb_ep0_dispatch_standard_setup_request__get_descriptor
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__return
    xorlw       0x0F
    bz          usb_ep0_dispatch_standard_setup_request__get_configuration
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__set_configuration
    xorlw       0x03
    bz          usb_ep0_dispatch_standard_setup_request__get_interface
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__set_interface
    xorlw       0x07
usb_ep0_dispatch_standard_setup_request__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_prepare_get_status_reply
; Address : 0x3710
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_prepare_get_status_reply:
    movlb       0x4
    clrf        ram_0x024, BANKED
    clrf        ram_0x025, BANKED
    bra         usb_ep0_prepare_get_status_reply__dispatch_recipient
usb_ep0_prepare_get_status_reply__device_status:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    btfss       ram_0x0CE, 0, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
    movlb       0x4
    bsf         ram_0x024, 1, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
usb_ep0_prepare_get_status_reply__interface_status:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
usb_ep0_prepare_get_status_reply__endpoint_status:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    mullw       0x08
    movlw       0x04
    movwf       ram_0x003, ACCESS
    movwf       ram_0x004, ACCESS
    movf        PRODL, W, ACCESS
    addwf       ram_0x003, F, ACCESS
    movf        PRODH, W, ACCESS
    addwfc      ram_0x004, F, ACCESS
    movlw       0x01
    btfss       ram_0x0D3, 7, BANKED
    movlw       0x00
    mullw       0x04
    movf        PRODL, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       ram_0x072, BANKED
    movf        PRODH, W, ACCESS
    addwfc      ram_0x004, W, ACCESS
    movwf       ram_0x073, BANKED
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movf        INDF2, W, ACCESS
    movwf       ram_0x003, ACCESS
    btfss       ram_0x003, 2, ACCESS
    bra         usb_ep0_prepare_get_status_reply__stage_reply
    movlw       0x01
    movlb       0x4
    movwf       ram_0x024, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
usb_ep0_prepare_get_status_reply__dispatch_recipient:
    movlb       0x0
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bz          usb_ep0_prepare_get_status_reply__device_status
    xorlw       0x01
    bz          usb_ep0_prepare_get_status_reply__interface_status
    xorlw       0x03
    bz          usb_ep0_prepare_get_status_reply__endpoint_status
usb_ep0_prepare_get_status_reply__stage_reply:
    movlb       0x0
    decf        ram_0x0C8, W, BANKED
    bnz         usb_ep0_prepare_get_status_reply__return
    movlw       0x04
    movwf       ram_0x076, BANKED
    movlw       0x24
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x02
    movwf       ram_0x0E7, BANKED
usb_ep0_prepare_get_status_reply__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_select_get_descriptor_payload
; Address : 0x3796
; Notes   : Inferred flash helper; touches flash. Calls: read_low_memory_byte_at_tblptr.
; ---------------------------------------------------------------------------
usb_ep0_select_get_descriptor_payload:
    movf        ram_0x0CF, W, BANKED
    xorlw       0x80
    bz          usb_ep0_select_get_descriptor_payload__dispatch_descriptor_type
    bra         usb_ep0_select_get_descriptor_payload__return
usb_ep0_select_get_descriptor_payload__device_descriptor:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x88
    movwf       ram_0x075, BANKED
    movlw       0x12
    bra         usb_ep0_select_get_descriptor_payload__store_descriptor_length
usb_ep0_select_get_descriptor_payload__configuration_descriptor:
    tstfsz      ram_0x0D1, BANKED
    bra         usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x2C
    movwf       ram_0x075, BANKED
    movlw       0x00
    movwf       ram_0x0E8, BANKED
    movlw       0x29
usb_ep0_select_get_descriptor_payload__store_descriptor_length:
    movwf       ram_0x0E7, BANKED
    bra         usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty
usb_ep0_select_get_descriptor_payload__string_descriptor:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D1, W, BANKED
    addlw       LOW(string_desc_ptr_table)          ; indexed TBLPTR -> string_desc_ptr_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(string_desc_ptr_table)
    movwf       TBLPTRH, ACCESS
    tblrd*+
    movff       TABLAT, ram_0x075
    movwf       ram_0x076, BANKED
    movff       ram_0x075, TBLPTRL
    movff       ram_0x076, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movlw       0x07
    cpfsgt      TBLPTRH, ACCESS
    bra         usb_ep0_select_get_descriptor_payload__read_string_length_via_fsr
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         usb_ep0_select_get_descriptor_payload__store_string_length
usb_ep0_select_get_descriptor_payload__read_string_length_via_fsr:
    rcall       read_low_memory_byte_at_tblptr
usb_ep0_select_get_descriptor_payload__store_string_length:
    movlb       0x0
    movwf       ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bra         usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty
usb_ep0_select_get_descriptor_payload__dispatch_descriptor_type:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x01
    bz          usb_ep0_select_get_descriptor_payload__device_descriptor
    xorlw       0x03
    bz          usb_ep0_select_get_descriptor_payload__configuration_descriptor
    xorlw       0x01
    bz          usb_ep0_select_get_descriptor_payload__string_descriptor
usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty:
    bsf         ram_0x0CE, 1, BANKED
usb_ep0_select_get_descriptor_payload__return:
    return      0


; ---------------------------------------------------------------------------
; Function: read_low_memory_byte_at_tblptr
; Address : 0x3810
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
read_low_memory_byte_at_tblptr:
    movff       TBLPTRL, FSR1L
    movff       TBLPTRH, FSR1H
    movf        INDF1, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: preset_table_apply_entry_legacy_blocking
; Address : 0x381C
; Notes   : Inferred i2c helper; touches i2c. Calls: flash_read, i2c_byte_tx.
; ---------------------------------------------------------------------------
preset_table_apply_entry_legacy_blocking:
    movff       ram_0x013, ram_0x003
    movff       ram_0x014, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    clrf        ram_0x008, ACCESS
    movlw       0x04
    movwf       ram_0x007, ACCESS
    clrf        ram_0x00A, ACCESS
    movlw       0x17
    movwf       ram_0x009, ACCESS
    call        flash_read, 0x0
    movff       ram_0x018, ram_0x02F
    movff       ram_0x019, ram_0x031
    movlw       0x19
    subwf       ram_0x031, W, ACCESS
    bc          preset_table_apply_entry_legacy__success_return
    movlw       0x04
    addwf       ram_0x013, W, ACCESS
    movwf       ram_0x015, ACCESS
    movlw       0x00
    addwfc      ram_0x014, W, ACCESS
    movwf       ram_0x016, ACCESS
    movff       ram_0x015, ram_0x003
    movff       ram_0x016, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movff       ram_0x031, ram_0x007
    clrf        ram_0x008, ACCESS
    clrf        ram_0x00A, ACCESS
    movlw       0x17
    movwf       ram_0x009, ACCESS
    call        flash_read, 0x0
    bsf         SSPCON2, 0, ACCESS
flow_main_i2c_service_381c_3870:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_main_i2c_service_381c_3870
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movf        ram_0x02F, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        ram_0x030, ACCESS
    bra         flow_main_i2c_service_381c_3894
flow_main_i2c_service_381c_3884:
    movf        ram_0x030, W, ACCESS
    addlw       0x17
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        i2c_byte_tx, 0x0
    incf        ram_0x030, F, ACCESS
flow_main_i2c_service_381c_3894:
    movf        ram_0x031, W, ACCESS
    subwf       ram_0x030, W, ACCESS
    bnc         flow_main_i2c_service_381c_3884
    bsf         SSPCON2, 2, ACCESS
flow_main_i2c_service_381c_389c:
    btfsc       SSPCON2, 2, ACCESS
    bra         flow_main_i2c_service_381c_389c
preset_table_apply_entry_legacy__success_return:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_38a2
; Address : 0x38A2
; Notes   : Inferred core helper routine. Calls: truncate_float32_to_integral_float_in_place, main_core_service_432e, float32_add_staged_operand_to_ram_window_in_place.
; ---------------------------------------------------------------------------
main_core_service_38a2:
    movff       ram_0x041, ram_0x039
    movff       ram_0x042, ram_0x03A
    movff       ram_0x043, ram_0x03B
    movff       ram_0x044, ram_0x03C
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    call        truncate_float32_to_integral_float_in_place, 0x0
    movff       ram_0x02F, ram_0x03D
    movff       ram_0x030, ram_0x03E
    movff       ram_0x031, ram_0x03F
    movff       ram_0x032, ram_0x040
    call        main_core_service_432e, 0x0
    movff       ram_0x039, ram_0x045
    movff       ram_0x03A, ram_0x046
    movff       ram_0x03B, ram_0x047
    movff       ram_0x03C, ram_0x048
    movff       ram_0x045, ram_0x02F
    movff       ram_0x046, ram_0x030
    movff       ram_0x047, ram_0x031
    movff       ram_0x048, ram_0x032
    movlw       0x41
    call        float32_add_staged_operand_to_ram_window_in_place, 0x0
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    call        truncate_float32_to_integral_float_in_place, 0x0
    movff       ram_0x02F, ram_0x041
    movff       ram_0x030, ram_0x042
    movff       ram_0x031, ram_0x043
    movff       ram_0x032, ram_0x044
    return      0

; ---------------------------------------------------------------------------
; Function: adaptive_baud_select
; Address : 0x3926
; Notes   : Inferred uart helper; touches adc,timer,uart. Calls: uart_reconfigure_and_resync_parser.
; ---------------------------------------------------------------------------
adaptive_baud_select:
    btfss       PORTC, 2, ACCESS
    bra         adaptive_baud_select__master_role_31250_path
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         adaptive_baud_select__common_pin_and_uart_init
adaptive_baud_select__master_role_31250_path:
    bcf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
adaptive_baud_select__common_pin_and_uart_init:
    bcf         LATB, 4, ACCESS
    bcf         LATB, 5, ACCESS
    bcf         LATB, 3, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bcf         LATB, 7, ACCESS
    call        uart_reconfigure_and_resync_parser, 0x0
    bsf         INTCON, 7, ACCESS
    bsf         INTCON, 6, ACCESS
    clrf        ram_0x093, BANKED
    movff       ram_0x093, ram_0x0AB
    bcf         INTCON3, 4, ACCESS
    bcf         INTCON3, 1, ACCESS
    bcf         INTCON, 2, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    clrf        ram_0x0A4, BANKED
    clrf        ram_0x0B0, BANKED
    clrf        ram_0x0B6, BANKED
    clrf        ram_0x0BA, BANKED
    clrf        event_flags, BANKED
    clrf        ram_0x07F, BANKED
    clrf        ram_0x0BD, BANKED
    clrf        active_flags, ACCESS
    clrf        ram_0x0BB, BANKED
    clrf        ram_0x0BC, BANKED
    clrf        ram_0x0A1, BANKED
    clrf        ram_0x088, BANKED
    clrf        ram_0x089, BANKED
    bcf         ADCON0, 1, ACCESS
    clrf        ram_0x094, BANKED
    movlw       0x20
    movlb       0x1
    movwf       ram_0x00F, BANKED
    movlw       0x21
    movwf       ram_0x010, BANKED
    movlw       0x22
    movwf       ram_0x011, BANKED
    movlw       0x23
    movwf       ram_0x012, BANKED
    movlw       0x25
    movwf       ram_0x013, BANKED
    movlw       0x27
    movwf       ram_0x014, BANKED
    movlw       0x28
    movwf       ram_0x015, BANKED
    retlw       0x28


; ---------------------------------------------------------------------------
; Function: i2c_emit_tas3108_coeff_from_staged_float
; Address : 0x39A6
; Notes   : Inferred i2c helper routine. Calls: float32_multiply_primary_by_secondary_in_place, main_core_service_38a2, float32_to_int32_in_place.
; ---------------------------------------------------------------------------
i2c_emit_tas3108_coeff_from_staged_float:
    clrf        ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
    clrf        ram_0x018, ACCESS
    movlw       0x4B
    movwf       ram_0x019, ACCESS
    movff       ram_0x049, ram_0x012
    movff       ram_0x04A, ram_0x013
    movff       ram_0x04B, ram_0x014
    movff       ram_0x04C, ram_0x015
    call        float32_multiply_primary_by_secondary_in_place, 0x0
    movff       ram_0x012, ram_0x041
    movff       ram_0x013, ram_0x042
    movff       ram_0x014, ram_0x043
    movff       ram_0x015, ram_0x044
    call        main_core_service_38a2, 0x0
    movff       ram_0x041, ram_0x04D
    movff       ram_0x042, ram_0x04E
    movff       ram_0x043, ram_0x04F
    movff       ram_0x044, ram_0x050
    movff       ram_0x04D, ram_0x025
    movff       ram_0x04E, ram_0x026
    movff       ram_0x04F, ram_0x027
    movff       ram_0x050, ram_0x028
    call        float32_to_int32_in_place, 0x0
    movff       ram_0x025, ram_0x051
    movff       ram_0x026, ram_0x052
    movff       ram_0x027, ram_0x053
    movff       ram_0x028, ram_0x054
    movf        ram_0x054, W, ACCESS
    andlw       0x0F
    call        i2c_byte_tx, 0x0
    movf        ram_0x053, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        ram_0x052, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        ram_0x051, W, ACCESS
    goto        i2c_byte_tx


; ---------------------------------------------------------------------------
; Function: usb_hid_dispatch_out_report_if_ready
; Address : 0x3A26
; Notes   : Inferred usb helper; touches usb. Calls: main_uart_service_495e, usb_ep1_out_copy_packet_if_ready, hid_command_dispatch.
; ---------------------------------------------------------------------------
usb_hid_dispatch_out_report_if_ready:
    movlb       0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__skip_and_reprime_uart_rx
    btfss       active_flags, 3, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__skip_and_reprime_uart_rx
    btfsc       PORTC, 0, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__usb_runtime_ready
usb_hid_dispatch_out_report_if_ready__skip_and_reprime_uart_rx:
    call        main_uart_service_495e, 0x0
    bra         usb_hid_dispatch_out_report_if_ready__return
usb_hid_dispatch_out_report_if_ready__usb_runtime_ready:
    tstfsz      ram_0x0C0, BANKED
    bra         usb_hid_dispatch_out_report_if_ready__dispatch_latched_report
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         usb_hid_dispatch_out_report_if_ready__return
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x1A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        usb_ep1_out_copy_packet_if_ready, 0x0
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0C0, BANKED
    clrf        ram_0x059, ACCESS
usb_hid_dispatch_out_report_if_ready__clear_reply_buffer_loop:
    movlb       0x1
    movlw       0x5A
    addwf       ram_0x059, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x059, F, ACCESS
    movlw       0x3F
    cpfsgt      ram_0x059, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__clear_reply_buffer_loop
    bra         usb_hid_dispatch_out_report_if_ready__return
usb_hid_dispatch_out_report_if_ready__dispatch_latched_report:
    movlb       0x1
    movf        ram_0x01A, W, BANKED
    call        hid_command_dispatch, 0x0
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         usb_hid_dispatch_out_report_if_ready__return
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        usb_ep1_in_copy_scratch_buffer_to_bdt, 0x0
    movlb       0x0
    clrf        ram_0x0C0, BANKED
usb_hid_dispatch_out_report_if_ready__return:
    return      0

; ---------------------------------------------------------------------------
; Function: uart_rx_with_framing
; Address : 0x3AA4
; Notes   : Inferred uart helper routine. Calls: timer3_arm_interrupt_countdown, rx_ring_has_data, rx_ring_read.
; ---------------------------------------------------------------------------
uart_rx_with_framing:
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x00B, ACCESS
    movff       ram_0x005, ram_0x003
    movff       ram_0x006, ram_0x004
    call        timer3_arm_interrupt_countdown, 0x0
uart_rx_with_framing__poll_ring:
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    bz          uart_rx_with_framing__check_timeout_and_limits
    movff       ram_0x00F, ram_0x00A
    call        rx_ring_read, 0x0
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          uart_rx_with_framing__wait_for_colon
    movf        ram_0x00E, W, ACCESS
    addwf       ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x008, W, ACCESS
    movwf       FSR2H, ACCESS
    movff       ram_0x00F, INDF2
    incf        ram_0x00E, F, ACCESS
    bra         uart_rx_with_framing__check_crlf_terminator
uart_rx_with_framing__wait_for_colon:
    movf        ram_0x00F, W, ACCESS
    xorlw       0x3A
    bnz         uart_rx_with_framing__check_crlf_terminator
    movlw       0x01
    movwf       ram_0x00D, ACCESS
uart_rx_with_framing__check_crlf_terminator:
    clrf        ram_0x00C, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          uart_rx_with_framing__latch_record_complete_flag
    movf        ram_0x00A, W, ACCESS
    xorlw       0x0D
    bnz         uart_rx_with_framing__latch_record_complete_flag
    movf        ram_0x00F, W, ACCESS
    xorlw       0x0A
    bnz         uart_rx_with_framing__latch_record_complete_flag
    movlw       0x01
    movwf       ram_0x00C, ACCESS
uart_rx_with_framing__latch_record_complete_flag:
    movff       ram_0x00C, ram_0x00B
uart_rx_with_framing__check_timeout_and_limits:
    call        timer3_timeout_elapsed_carry, 0x0
    bc          uart_rx_with_framing__stop_timer_return_count
    movf        ram_0x009, W, ACCESS
    subwf       ram_0x00E, W, ACCESS
    bc          uart_rx_with_framing__stop_timer_return_count
    movf        ram_0x00B, W, ACCESS
    bz          uart_rx_with_framing__poll_ring
uart_rx_with_framing__stop_timer_return_count:
    call        timer3_stop_interrupt_countdown, 0x0
    movf        ram_0x00E, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: isr_high_priority_dispatch
; Address : 0x3B1E
; Notes   : Inferred uart helper; touches timer,uart.
; ---------------------------------------------------------------------------
isr_high_priority_dispatch:
    pop
    btfss       PIR2, 5, ACCESS
    bra         timer0_irq_handler
    bcf         PIR2, 5, ACCESS
    bcf         PIE2, 5, ACCESS
timer0_irq_handler:
    btfss       INTCON, 2, ACCESS
    bra         timer3_irq_handler
    movlb       0x0
    bsf         event_flags, 0, BANKED
    bcf         INTCON, 2, ACCESS
    bcf         INTCON, 5, ACCESS
    bcf         T0CON, 7, ACCESS
timer3_irq_handler:
    btfss       PIR2, 1, ACCESS
    bra         uart_rx_irq_enqueue
    bcf         T3CON, 0, ACCESS
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
    movwf       TMR3L, ACCESS
    bsf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS
    movlb       0x0
    movf        ram_0x08D, W, BANKED
    iorwf       ram_0x08C, W, BANKED
    bz          main_isr_dispatch__stop_timer3_hold_countdown
    decf        ram_0x08C, F, BANKED
    btfss       STATUS, 0, ACCESS
    decf        ram_0x08D, F, BANKED
    bra         uart_rx_irq_enqueue
main_isr_dispatch__stop_timer3_hold_countdown:
    bcf         T3CON, 0, ACCESS
    bcf         PIE2, 1, ACCESS
uart_rx_irq_enqueue:
    btfss       PIR1, 5, ACCESS
    bra         main_isr_dispatch__restore_fsr2_and_return
    movlw       0x00
    movlb       0x0
    addwf       rx_ring_wr, W, BANKED
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    movff       RCREG, INDF2
    incf        rx_ring_wr, F, BANKED
    movlw       0xBF
    cpfsgt      rx_ring_wr, BANKED
    bra         uart_oerr_recover
    clrf        rx_ring_wr, BANKED
uart_oerr_recover:
    btfss       RCSTA, 1, ACCESS
    bra         main_isr_dispatch__restore_fsr2_and_return
    bcf         RCSTA, 4, ACCESS
    dw          0xF000
    bsf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
main_isr_dispatch__restore_fsr2_and_return:
    movff       isr_save_fsr2h, FSR2H
    movff       isr_save_fsr2l, FSR2L
    retfie      1

; ---------------------------------------------------------------------------
; Function: send_status_burst
; Address : 0x3B96
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, timer3_blocking_delay_1ms.
; ---------------------------------------------------------------------------
send_status_burst:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x05
    call        uart_tx_byte_blocking, 0x0
    movf        ram_0x05F, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    call        timer3_blocking_delay_1ms, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x07
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        computed_volume, W, BANKED
    addlw       0x60
    call        uart_tx_byte_blocking, 0x0
    call        timer3_blocking_delay_1ms, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x03
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    btfss       active_flags, 3, ACCESS
    movlw       0x00
    call        uart_tx_byte_blocking, 0x0
    call        timer3_blocking_delay_1ms, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x06
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        input_select, W, BANKED
    call        uart_tx_byte_blocking, 0x0
    call        timer3_blocking_delay_1ms, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x1D
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        ram_0x0B8, W, BANKED
    goto        uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; Function: hw_standby_shutdown
; Address : 0x3C0C
; Notes   : Inferred uart helper; touches timer,uart. Calls: i2c_secondary_dev_write, timer3_blocking_delay.
; ---------------------------------------------------------------------------
hw_standby_shutdown:
    clrf        ram_0x006, ACCESS
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x1D
    call        i2c_secondary_dev_write, 0x0
    btfss       PORTC, 2, ACCESS
    bra         hw_standby_shutdown__select_master_baud
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         hw_standby_shutdown__drop_outputs_after_baud_select
hw_standby_shutdown__select_master_baud:
    bcf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
hw_standby_shutdown__drop_outputs_after_baud_select:
    bcf         LATB, 4, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    movlw       0x28
    movlb       0x0
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          hw_standby_shutdown__stop_timer0_and_usb
    clrf        ram_0x008, ACCESS
    clrf        ram_0x009, ACCESS
hw_standby_shutdown__rail_discharge_pulse_loop:
    movff       ram_0x008, ram_0x006
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    xorwf       ram_0x008, F, ACCESS
    clrf        ram_0x004, ACCESS
    movlw       0xFA
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    incf        ram_0x009, F, ACCESS
    movlw       0x04
    cpfsgt      ram_0x009, ACCESS
    bra         hw_standby_shutdown__rail_discharge_pulse_loop
hw_standby_shutdown__stop_timer0_and_usb:
    bcf         LATB, 3, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    goto        usb_shutdown


; ---------------------------------------------------------------------------
; Function: usb_ep1_out_copy_packet_if_ready
; Address : 0x3C82
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep1_out_copy_packet_if_ready:
    movlb       0x0
    clrf        ram_0x0CA, BANKED
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         flow_main_core_service_3c82_3ce6
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x00D, W, BANKED
    btfss       STATUS, 0, ACCESS
    movff       ram_0x40D, ram_0x005
    movlb       0x0
    clrf        ram_0x0CA, BANKED
    bra         usb_ep1_out_copy_packet_if_ready__check_remaining
usb_ep1_out_copy_packet_if_ready__copy_next_byte:
    movlw       0x2C
    movlb       0x0
    addwf       ram_0x0CA, W, BANKED
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x04
    addwfc      FSR2H, F, ACCESS
    movf        ram_0x0CA, W, BANKED
    addwf       ram_0x003, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x0CA, F, BANKED
usb_ep1_out_copy_packet_if_ready__check_remaining:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x0CA, W, BANKED
    bnc         usb_ep1_out_copy_packet_if_ready__copy_next_byte
    movlw       0x40
    movlb       0x4
    movwf       ram_0x00D, BANKED
    andwf       ram_0x00C, F, BANKED
    movlw       0x01
    btfsc       ram_0x00C, 6, BANKED
    movlw       0x00
    movwf       ram_0x006, ACCESS
    swapf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    movf        ram_0x00C, W, BANKED
    xorwf       ram_0x006, W, ACCESS
    andlw       0xBF
    xorwf       ram_0x006, W, ACCESS
    movwf       ram_0x00C, BANKED
    bsf         ram_0x00C, 3, BANKED
    bsf         ram_0x00C, 7, BANKED
flow_main_core_service_3c82_3ce6:
    return      0


; ---------------------------------------------------------------------------
; Function: fw_update_signature_status_word_helper
; Address : 0x3CE8
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
fw_update_signature_status_word_helper:
    lfsr        FSR2, 0x0003
    movf        POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    bnz         fw_update_signature_status_word_helper__decode_nonzero_signature
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    movwf       POSTINC2, ACCESS
    movwf       POSTDEC2, ACCESS
    bra         fw_update_signature_status_word_helper__return
fw_update_signature_status_word_helper__decode_nonzero_signature:
    movf        ram_0x006, W, ACCESS
    andlw       0x7F
    movwf       ram_0x008, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x008, W, ACCESS
    movwf       ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    rlcf        ram_0x00A, F, ACCESS
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x009, POSTINC2
    movff       ram_0x00A, POSTDEC2
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    btfss       ram_0x005, 7, ACCESS
    movlw       0x00
    iorwf       POSTINC2, F, ACCESS
    movlw       0x00
    iorwf       POSTDEC2, F, ACCESS
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x82
    addwf       POSTINC2, F, ACCESS
    movlw       0xFF
    addwfc      POSTDEC2, F, ACCESS
    movf        ram_0x006, W, ACCESS
    andlw       0x80
    iorlw       0x3F
    movwf       ram_0x006, ACCESS
    bcf         ram_0x005, 7, ACCESS
fw_update_signature_status_word_helper__return:
    return      0
boot_cold_init__clear_ram_and_runtime_state:
    lfsr        FSR0, 0x0300
    movlw       0xC0
flow_main_flash_service_3ce8_3d54:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d54
    lfsr        FSR0, 0x0200
    movlw       0xDE
flow_main_flash_service_3ce8_3d60:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d60
    lfsr        FSR0, 0x0100
    movlw       0xE5
flow_main_flash_service_3ce8_3d6c:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d6c
    lfsr        FSR0, 0x0060
    movlw       0x8D
flow_main_flash_service_3ce8_3d78:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d78
    clrf        ram_0x05F, ACCESS
    clrf        active_flags, ACCESS
    movlw       LOW(fw_update_status_text_seed_table)         ; TBLPTR -> fw_update_status_text_seed_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(fw_update_status_text_seed_table)
    movwf       TBLPTRH, ACCESS
    movlw       UPPER(fw_update_status_text_seed_table)
    movwf       TBLPTRU, ACCESS
    lfsr        FSR0, 0x01E5
    lfsr        FSR1, 0x0016
boot_cold_init__copy_fw_update_status_text_seed:
    tblrd*+
    movff       TABLAT, POSTINC0
    movf        POSTDEC1, W, ACCESS
    movf        FSR1L, W, ACCESS
    bnz         boot_cold_init__copy_fw_update_status_text_seed
    movlw       UPPER(0x0000)                       ; clear TBLPTRU to program space
    movwf       TBLPTRU, ACCESS
    movlb       0x0
    goto        boot_cold_init__run_peripheral_init

; ---------------------------------------------------------------------------
; Function: flash_erase
; Address : 0x3DAC
; Notes   : Inferred flash helper; touches flash. Calls: nvm_unlock_and_set_wr.
; ---------------------------------------------------------------------------
flash_erase:
    clrf        ram_0x00B, ACCESS
    movff       ram_0x003, ram_0x00C
    movff       ram_0x004, ram_0x00D
    movff       ram_0x005, ram_0x00E
    movff       ram_0x006, ram_0x00F
    bra         flash_erase__check_end_address
flash_erase__stage_next_block:
    movff       ram_0x00E, TBLPTRU
    movff       ram_0x00D, TBLPTRH
    movff       ram_0x00C, TBLPTRL
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    bsf         EECON1, 4, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flash_erase__unlock_and_advance_block
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x00B, ACCESS
flash_erase__unlock_and_advance_block:
    call        nvm_unlock_and_set_wr, 0x0
    movf        ram_0x00B, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         INTCON, 7, ACCESS
    movlw       0x40
    addwf       ram_0x00C, F, ACCESS
    movlw       0x00
    addwfc      ram_0x00D, F, ACCESS
    addwfc      ram_0x00E, F, ACCESS
    addwfc      ram_0x00F, F, ACCESS
flash_erase__check_end_address:
    movf        ram_0x007, W, ACCESS
    subwf       ram_0x00C, W, ACCESS
    movf        ram_0x008, W, ACCESS
    subwfb      ram_0x00D, W, ACCESS
    movf        ram_0x009, W, ACCESS
    subwfb      ram_0x00E, W, ACCESS
    movf        ram_0x00A, W, ACCESS
    subwfb      ram_0x00F, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         flash_erase__stage_next_block


; ---------------------------------------------------------------------------
; Function: int32_to_float32_and_save
; Address : 0x3E0A
; Notes   : Inferred core helper routine. Calls: float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
int32_to_float32_and_save:
    clrf        ram_0x011, ACCESS
    movf        ram_0x010, W, ACCESS
    xorlw       0x80
    addlw       0x80
    bnz         int32_to_float32_and_save__maybe_negate_magnitude
    movlw       0x00
    subwf       ram_0x00F, W, ACCESS
    bnz         int32_to_float32_and_save__maybe_negate_magnitude
    movlw       0x00
    subwf       ram_0x00E, W, ACCESS
    bnz         int32_to_float32_and_save__maybe_negate_magnitude
    movlw       0x00
    subwf       ram_0x00D, W, ACCESS
int32_to_float32_and_save__maybe_negate_magnitude:
    bc          int32_to_float32_and_save__pack_result
    comf        ram_0x010, F, ACCESS
    comf        ram_0x00F, F, ACCESS
    comf        ram_0x00E, F, ACCESS
    negf        ram_0x00D, ACCESS
    movlw       0x00
    addwfc      ram_0x00E, F, ACCESS
    addwfc      ram_0x00F, F, ACCESS
    addwfc      ram_0x010, F, ACCESS
    movlw       0x01
    movwf       ram_0x011, ACCESS
int32_to_float32_and_save__pack_result:
    movff       ram_0x00D, ram_0x003
    movff       ram_0x00E, ram_0x004
    movff       ram_0x00F, ram_0x005
    movff       ram_0x010, ram_0x006
    movlw       0x96
    movwf       ram_0x007, ACCESS
    movff       ram_0x011, ram_0x008
    call        float32_pack_mantissa_exponent_sign, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_byte_tx
; Address : 0x3E68
; Notes   : Inferred i2c helper; touches i2c,timer. Calls: i2c_wait_bus_idle.
; ---------------------------------------------------------------------------
i2c_byte_tx:
    movff       WREG, ram_0x005
    movff       ram_0x005, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         flow_i2c_byte_tx_3ec2
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_3e9c
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bz          flow_i2c_byte_tx_3e9c
    bsf         SSPCON1, 4, ACCESS
flow_i2c_byte_tx_3e92:
    btfss       PIR1, 3, ACCESS
    bra         flow_i2c_byte_tx_3e92
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         flow_i2c_byte_tx_3ec2
flow_i2c_byte_tx_3e9c:
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_3eb8
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bnz         flow_i2c_byte_tx_3ec2
flow_i2c_byte_tx_3eb8:
    btfsc       SSPSTAT, 0, ACCESS
    bra         flow_i2c_byte_tx_3eb8
    call        i2c_wait_bus_idle, 0x0
    movf        SSPCON2, W, ACCESS
flow_i2c_byte_tx_3ec2:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_multiply_ram_window_by_staged_operand_in_place
; Address : 0x3EC4
; Notes   : Inferred core helper routine. Calls: float32_multiply_primary_by_secondary_in_place.
; ---------------------------------------------------------------------------
float32_multiply_ram_window_by_staged_operand_in_place:
    movff       WREG, ram_0x02D
    movf        ram_0x02D, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       POSTINC2, ram_0x012
    movff       POSTINC2, ram_0x013
    movff       POSTINC2, ram_0x014
    movff       POSTINC2, ram_0x015
    movff       ram_0x025, ram_0x016
    movff       ram_0x026, ram_0x017
    movff       ram_0x027, ram_0x018
    movff       ram_0x028, ram_0x019
    call        float32_multiply_primary_by_secondary_in_place, 0x0
    movff       ram_0x012, ram_0x029
    movff       ram_0x013, ram_0x02A
    movff       ram_0x014, ram_0x02B
    movff       ram_0x015, ram_0x02C
    movf        ram_0x02D, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x029, POSTINC2
    movff       ram_0x02A, POSTINC2
    movff       ram_0x02B, POSTINC2
    movff       ram_0x02C, POSTDEC2
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: float32_add_staged_operand_to_ram_window_in_place
; Address : 0x3F1E
; Notes   : Inferred core helper routine. Calls: float32_add_secondary_to_primary_in_place.
; ---------------------------------------------------------------------------
float32_add_staged_operand_to_ram_window_in_place:
    movff       WREG, ram_0x037
    movf        ram_0x037, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       POSTINC2, ram_0x020
    movff       POSTINC2, ram_0x021
    movff       POSTINC2, ram_0x022
    movff       POSTINC2, ram_0x023
    movff       ram_0x02F, ram_0x024
    movff       ram_0x030, ram_0x025
    movff       ram_0x031, ram_0x026
    movff       ram_0x032, ram_0x027
    call        float32_add_secondary_to_primary_in_place, 0x0
    movff       ram_0x020, ram_0x033
    movff       ram_0x021, ram_0x034
    movff       ram_0x022, ram_0x035
    movff       ram_0x023, ram_0x036
    movf        ram_0x037, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x033, POSTINC2
    movff       ram_0x034, POSTINC2
    movff       ram_0x035, POSTINC2
    movff       ram_0x036, POSTDEC2
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: intel_hex_checksum_update
; Address : 0x3F78
; Notes   : Accumulates and validates Intel HEX checksum bytes.
; ---------------------------------------------------------------------------
intel_hex_checksum_update:
    movff       WREG, ram_0x005
    clrf        ram_0x004, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x005, ACCESS
    bra         intel_hex_checksum_update__decode_high_alpha_nibble
    movlw       0x3A
    subwf       ram_0x005, W, ACCESS
    bc          intel_hex_checksum_update__decode_high_alpha_nibble
    movf        ram_0x005, W, ACCESS
    addlw       0xD0
    bra         intel_hex_checksum_update__store_high_nibble
intel_hex_checksum_update__decode_high_alpha_nibble:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         intel_hex_checksum_update__decode_low_nibble
    movlw       0x47
    subwf       ram_0x005, W, ACCESS
    bc          intel_hex_checksum_update__decode_low_nibble
    movf        ram_0x005, W, ACCESS
    addlw       0xC9
intel_hex_checksum_update__store_high_nibble:
    movwf       ram_0x004, ACCESS
intel_hex_checksum_update__decode_low_nibble:
    swapf       ram_0x004, F, ACCESS
    movlw       0xF0
    andwf       ram_0x004, F, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x003, ACCESS
    bra         intel_hex_checksum_update__decode_low_alpha_nibble
    movlw       0x3A
    subwf       ram_0x003, W, ACCESS
    bc          intel_hex_checksum_update__decode_low_alpha_nibble
    movf        ram_0x003, W, ACCESS
    addlw       0xD0
    bra         intel_hex_checksum_update__add_low_nibble
intel_hex_checksum_update__decode_low_alpha_nibble:
    movlw       0x40
    cpfsgt      ram_0x003, ACCESS
    bra         intel_hex_checksum_update__return_decoded_byte
    movlw       0x47
    subwf       ram_0x003, W, ACCESS
    bc          intel_hex_checksum_update__return_decoded_byte
    movf        ram_0x003, W, ACCESS
    addlw       0xC9
intel_hex_checksum_update__add_low_nibble:
    addwf       ram_0x004, F, ACCESS
intel_hex_checksum_update__return_decoded_byte:
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep1_in_copy_scratch_buffer_to_bdt
; Address : 0x3FD0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep1_in_copy_scratch_buffer_to_bdt:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         usb_ep1_in_copy_scratch_buffer_to_bdt__length_clamped
    movwf       ram_0x005, ACCESS
usb_ep1_in_copy_scratch_buffer_to_bdt__length_clamped:
    clrf        ram_0x007, ACCESS
    bra         usb_ep1_in_copy_scratch_buffer_to_bdt__check_remaining
usb_ep1_in_copy_scratch_buffer_to_bdt__copy_next_byte:
    movf        ram_0x007, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR2H, ACCESS
    movlw       0x6C
    addwf       ram_0x007, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x04
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x007, F, ACCESS
usb_ep1_in_copy_scratch_buffer_to_bdt__check_remaining:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x007, W, ACCESS
    bnc         usb_ep1_in_copy_scratch_buffer_to_bdt__copy_next_byte
    movff       ram_0x005, ram_0x411
    movlw       0x40
    movlb       0x4
    andwf       ram_0x010, F, BANKED
    movlw       0x01
    btfsc       ram_0x010, 6, BANKED
    movlw       0x00
    movwf       ram_0x006, ACCESS
    swapf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    movf        ram_0x010, W, BANKED
    xorwf       ram_0x006, W, ACCESS
    andlw       0xBF
    xorwf       ram_0x006, W, ACCESS
    movwf       ram_0x010, BANKED
    bsf         ram_0x010, 3, BANKED
    bsf         ram_0x010, 7, BANKED
    return      0

; ---------------------------------------------------------------------------
; Function: flash_read
; Address : 0x4028
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
flash_read:
    movff       ram_0x003, ram_0x00B
    movff       ram_0x004, ram_0x00C
    movff       ram_0x005, ram_0x00D
    movff       ram_0x006, ram_0x00E
    movff       TBLPTRU, ram_0x011
    movff       TBLPTRH, ram_0x010
    movff       TBLPTRL, ram_0x00F
    movff       ram_0x00D, TBLPTRU
    movff       ram_0x00C, TBLPTRH
    movff       ram_0x00B, TBLPTRL
    bra         flash_read__test_remaining_byte_count
flash_read__copy_next_program_byte:
    tblrd*+
    movff       ram_0x009, FSR2L
    movff       ram_0x00A, FSR2H
    movff       TABLAT, INDF2
    infsnz      ram_0x009, F, ACCESS
    incf        ram_0x00A, F, ACCESS
flash_read__test_remaining_byte_count:
    decf        ram_0x007, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x008, F, ACCESS
    incf        ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    incf        ram_0x008, W, ACCESS
    bnz         flash_read__copy_next_program_byte
    movff       ram_0x011, TBLPTRU
    movff       ram_0x010, TBLPTRH
    movff       ram_0x00F, TBLPTRL
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_arm_out_pingpong_bd
; Address : 0x4080
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_arm_out_pingpong_bd:
    movff       WREG, ram_0x003
    movlw       0x08
    movlb       0x1
    movwf       ram_0x017, BANKED
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x1C
    movwf       ram_0x018, BANKED
    tstfsz      ram_0x003, ACCESS
    bra         usb_ep0_arm_out_pingpong_bd__select_odd_bd
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x14
    movwf       ram_0x018, BANKED
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
    movlw       0x00
    bra         usb_ep0_arm_out_pingpong_bd__copy_template_and_set_own
usb_ep0_arm_out_pingpong_bd__select_odd_bd:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
usb_ep0_arm_out_pingpong_bd__copy_template_and_set_own:
    movwf       ram_0x078, BANKED
    movff       ram_0x078, FSR2L
    movff       ram_0x079, FSR2H
    movff       ram_0x116, POSTINC2
    movff       ram_0x117, POSTINC2
    movff       ram_0x118, POSTINC2
    movff       ram_0x119, POSTINC2
    movff       ram_0x078, FSR2L
    movff       ram_0x079, FSR2H
    movlb       0x0
    bsf         INDF2, 7, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_bus_reset_reinitialize
; Address : 0x40D6
; Notes   : Inferred usb helper; touches usb. Calls: usb_disconnect_handler, usb_ep0_arm_out_pingpong_bd.
; ---------------------------------------------------------------------------
usb_bus_reset_reinitialize:
    movlw       0x03
    movlb       0x0
    movwf       ram_0x0CD, BANKED
    clrf        UEIE, ACCESS
    clrf        UIR, ACCESS
    movlw       0x7B
    movwf       UIE, ACCESS
    clrf        UADDR, ACCESS
    clrf        UEP1, ACCESS
    clrf        UEP2, ACCESS
    clrf        UEP3, ACCESS
    clrf        UEP4, ACCESS
    clrf        UEP5, ACCESS
    clrf        UEP6, ACCESS
    clrf        UEP7, ACCESS
    movlw       0x16
    movwf       UEP0, ACCESS
    bsf         UCON, 6, ACCESS
    bra         usb_bus_reset_reinitialize__drain_transaction_flags
usb_bus_reset_reinitialize__clear_transaction_flag:
    bcf         UIR, 3, ACCESS
    call        usb_disconnect_handler, 0x0
usb_bus_reset_reinitialize__drain_transaction_flags:
    btfsc       UIR, 3, ACCESS
    bra         usb_bus_reset_reinitialize__clear_transaction_flag
    bcf         UCON, 6, ACCESS
    bcf         UCON, 4, ACCESS
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x00
    call        usb_ep0_arm_out_pingpong_bd, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    clrf        ram_0x0CE, BANKED
    clrf        ram_0x0EB, BANKED
    movlw       0x00
    goto        usb_ep1_configure_if_enabled


; ---------------------------------------------------------------------------
; Function: adc_divide_staged_words
; Address : 0x4124
; Notes   : Inferred adc helper; touches adc.
; ---------------------------------------------------------------------------
adc_divide_staged_words:
    clrf        ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          adc_divide_staged_words__store_quotient_result
    movlw       0x01
    movwf       ram_0x009, ACCESS
    bra         adc_divide_staged_words__test_divisor_msb
adc_divide_staged_words__normalize_divisor_left:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x009, F, ACCESS
adc_divide_staged_words__test_divisor_msb:
    btfss       ram_0x006, 7, ACCESS
    bra         adc_divide_staged_words__normalize_divisor_left
adc_divide_staged_words__next_quotient_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x007, F, ACCESS
    rlcf        ram_0x008, F, ACCESS
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         adc_divide_staged_words__shift_divisor_right
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
    bsf         ram_0x007, 0, ACCESS
adc_divide_staged_words__shift_divisor_right:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x009, F, ACCESS
    bra         adc_divide_staged_words__next_quotient_bit
adc_divide_staged_words__store_quotient_result:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    return      0
an0_hysteresis_monitor:
    btfss       active_flags, 3, ACCESS
    bra         an0_hysteresis_monitor__return
    movf        ram_0x0A1, W, BANKED
    xorlw       0x64
    bnz         an0_hysteresis_monitor__increment_delay_counter
    btfsc       ADCON0, 1, ACCESS
    bra         an0_hysteresis_monitor__reset_delay_counter
    movf        ADRESH, W, ACCESS
    movwf       ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       ram_0x088, BANKED
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       ram_0x089, BANKED
    movlw       0x29
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    btfsc       STATUS, 0, ACCESS
    bsf         ram_0x094, 2, BANKED
    bsf         ADCON0, 1, ACCESS
    btfss       ram_0x094, 2, BANKED
    bra         an0_hysteresis_monitor__reset_delay_counter
    movlw       0x28
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          an0_hysteresis_monitor__reset_delay_counter
    bcf         active_flags, 3, ACCESS
    bsf         event_flags, 2, BANKED
an0_hysteresis_monitor__reset_delay_counter:
    clrf        ram_0x0A1, BANKED
    bra         an0_hysteresis_monitor__return
an0_hysteresis_monitor__increment_delay_counter:
    incf        ram_0x0A1, F, BANKED
an0_hysteresis_monitor__return:
    return      0


; ---------------------------------------------------------------------------
; Function: format_int16_decimal_ascii_to_w_pointer
; Address : 0x41B6
; Notes   : Inferred core helper routine. Calls: format_uint16_radix_ascii_to_w_pointer.
; ---------------------------------------------------------------------------
format_int16_decimal_ascii_to_w_pointer:
    movff       WREG, ram_0x017
    movff       ram_0x017, ram_0x016
    movf        ram_0x013, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       ram_0x012, W, ACCESS
    bc          format_int16_decimal_ascii_to_w_pointer__format_magnitude
    movf        ram_0x017, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x2D
    movwf       INDF2, ACCESS
    incf        ram_0x017, F, ACCESS
    negf        ram_0x012, ACCESS
    comf        ram_0x013, F, ACCESS
    btfsc       STATUS, 0, ACCESS
    incf        ram_0x013, F, ACCESS
format_int16_decimal_ascii_to_w_pointer__format_magnitude:
    movff       ram_0x012, ram_0x00A
    movff       ram_0x013, ram_0x00B
    movff       ram_0x014, ram_0x00C
    movff       ram_0x015, ram_0x00D
    movf        ram_0x017, W, ACCESS
    call        format_uint16_radix_ascii_to_w_pointer, 0x0
    movf        ram_0x016, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_apply_set_configuration
; Address : 0x41FE
; Notes   : Inferred usb helper; touches usb. Calls: usb_ep1_configure_if_enabled.
; ---------------------------------------------------------------------------
usb_apply_set_configuration:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    clrf        UEP1, ACCESS
    clrf        UEP2, ACCESS
    clrf        UEP3, ACCESS
    clrf        UEP4, ACCESS
    clrf        UEP5, ACCESS
    clrf        UEP6, ACCESS
    clrf        UEP7, ACCESS
    clrf        ram_0x091, BANKED
usb_apply_set_configuration__clear_config_status_byte:
    movf        ram_0x091, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x091, F, BANKED
    movf        ram_0x091, W, BANKED
    bz          usb_apply_set_configuration__clear_config_status_byte
    movff       ram_0x0D1, ram_0x0EB
    movf        ram_0x0EB, W, BANKED
    call        usb_ep1_configure_if_enabled, 0x0
    movlb       0x0
    tstfsz      ram_0x0D1, BANKED
    bra         usb_apply_set_configuration__configured_state
    movlw       0x05
    bra         usb_apply_set_configuration__store_device_state
usb_apply_set_configuration__configured_state:
    movlw       0x06
usb_apply_set_configuration__store_device_state:
    movwf       ram_0x0CD, BANKED
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_secondary_dev_random_read
; Address : 0x423C
; Notes   : Inferred i2c helper; touches i2c. Calls: i2c_wait_bus_idle, i2c_byte_tx, i2c_receive_sspbuf_bounded.
; ---------------------------------------------------------------------------
i2c_secondary_dev_random_read:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS
flow_i2c_secondary_dev_random_4246:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_i2c_secondary_dev_random_4246
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 1, ACCESS
flow_i2c_secondary_dev_random_4258:
    btfsc       SSPCON2, 1, ACCESS
    bra         flow_i2c_secondary_dev_random_4258
    movlw       0xE3
    call        i2c_byte_tx, 0x0
    call        i2c_receive_sspbuf_bounded, 0x0
    movwf       ram_0x007, ACCESS
    bsf         SSPCON2, 5, ACCESS
    bsf         SSPCON2, 4, ACCESS
flow_i2c_secondary_dev_random_426c:
    btfsc       SSPCON2, 4, ACCESS
    bra         flow_i2c_secondary_dev_random_426c
    bsf         SSPCON2, 2, ACCESS
flow_i2c_secondary_dev_random_4272:
    btfsc       SSPCON2, 2, ACCESS
    bra         flow_i2c_secondary_dev_random_4272
    movf        ram_0x007, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: adc_remainder_staged_words
; Address : 0x427A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
adc_remainder_staged_words:
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          adc_remainder_staged_words__return
    movlw       0x01
    movwf       ram_0x007, ACCESS
    bra         adc_remainder_staged_words__test_divisor_msb
adc_remainder_staged_words__normalize_divisor_left:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x007, F, ACCESS
adc_remainder_staged_words__test_divisor_msb:
    btfss       ram_0x006, 7, ACCESS
    bra         adc_remainder_staged_words__normalize_divisor_left
adc_remainder_staged_words__subtract_shifted_divisor:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         adc_remainder_staged_words__shift_divisor_right
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
adc_remainder_staged_words__shift_divisor_right:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x007, F, ACCESS
    bra         adc_remainder_staged_words__subtract_shifted_divisor
adc_remainder_staged_words__return:
    movff       ram_0x003, ram_0x003
    movff       ram_0x004, ram_0x004
    return      0

; ---------------------------------------------------------------------------
; Function: flash_write_with_gie_off
; Address : 0x42B8
; Notes   : Inferred flash helper; touches flash. Calls: nvm_unlock_and_set_wr.
; ---------------------------------------------------------------------------
flash_write_with_gie_off:
    bcf         INTCON, 7, ACCESS
    movlw       UPPER(_CONFIG6H)
    movwf       TBLPTRU, ACCESS
    clrf        TBLPTRH, ACCESS
    movlw       LOW(_CONFIG6H)                      ; TBLPTR -> _CONFIG6H
    movwf       TBLPTRL, ACCESS
    movlw       0xA0
    movwf       TABLAT, ACCESS
    tblwt*
    movlw       0xC4
    movwf       EECON1, ACCESS
    call        nvm_unlock_and_set_wr, 0x0
flow_flash_write_with_gie_off_42d2:
    btfsc       EECON1, 1, ACCESS
    bra         flow_flash_write_with_gie_off_42d2
    movlw       UPPER(_CONFIG1L)
    movwf       TBLPTRU, ACCESS
    clrf        TBLPTRH, ACCESS
    clrf        TBLPTRL, ACCESS
    movlw       0x3A
    movwf       TABLAT, ACCESS
    tblwt*
    movlw       0xC4
    movwf       EECON1, ACCESS
    call        nvm_unlock_and_set_wr, 0x0
flow_flash_write_with_gie_off_42ec:
    btfsc       EECON1, 1, ACCESS
    bra         flow_flash_write_with_gie_off_42ec
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_service_setup_transaction
; Address : 0x42F4
; Notes   : Inferred usb helper; touches usb. Calls: usb_ep0_dispatch_standard_setup_request, main_core_service_495a.
; ---------------------------------------------------------------------------
usb_ep0_service_setup_transaction:
    movlb       0x4
    clrf        ram_0x008, BANKED
    movlb       0x0
    clrf        ram_0x0CC, BANKED
    movlb       0x4
    btfss       ram_0x000, 7, BANKED
    bra         usb_ep0_service_setup_transaction__check_odd_out_bd
    clrf        ram_0x000, BANKED
    movlb       0x0
    clrf        ram_0x096, BANKED
usb_ep0_service_setup_transaction__check_odd_out_bd:
    movlb       0x4
    btfss       ram_0x004, 7, BANKED
    bra         usb_ep0_service_setup_transaction__clear_control_state_and_dispatch
    clrf        ram_0x004, BANKED
    movlw       0x01
    movlb       0x0
    movwf       ram_0x096, BANKED
usb_ep0_service_setup_transaction__clear_control_state_and_dispatch:
    movlb       0x0
    clrf        ram_0x0C9, BANKED
    clrf        ram_0x0C8, BANKED
    clrf        ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bcf         UCON, 4, ACCESS
    call        usb_ep0_dispatch_standard_setup_request, 0x0
    call        main_core_service_495a, 0x0
    goto        usb_ep0_arm_control_transfer_response


; ---------------------------------------------------------------------------
; Function: main_core_service_432e
; Address : 0x432E
; Notes   : Inferred core helper routine. Calls: float32_add_secondary_to_primary_in_place.
; ---------------------------------------------------------------------------
main_core_service_432e:
    movlw       0x80
    xorwf       ram_0x040, F, ACCESS
    movff       ram_0x039, ram_0x020
    movff       ram_0x03A, ram_0x021
    movff       ram_0x03B, ram_0x022
    movff       ram_0x03C, ram_0x023
    movff       ram_0x03D, ram_0x024
    movff       ram_0x03E, ram_0x025
    movff       ram_0x03F, ram_0x026
    movff       ram_0x040, ram_0x027
    call        float32_add_secondary_to_primary_in_place, 0x0
    movff       ram_0x020, ram_0x039
    movff       ram_0x021, ram_0x03A
    movff       ram_0x022, ram_0x03B
    movff       ram_0x023, ram_0x03C
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_tas3108_reg1f_write
; Address : 0x4368
; Notes   : Inferred i2c helper; touches i2c. Calls: i2c_wait_bus_idle, i2c_byte_tx.
; ---------------------------------------------------------------------------
i2c_tas3108_reg1f_write:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS
flow_i2c_tas3108_reg1f_write_4372:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_i2c_tas3108_reg1f_write_4372
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x1F
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS
flow_i2c_tas3108_reg1f_write_439c:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         flow_i2c_tas3108_reg1f_write_439c


; ---------------------------------------------------------------------------
; Function: uart_tx_ascii_hex_byte
; Address : 0x43A2
; Notes   : Inferred uart helper routine. Calls: hex_scratch_nibble_to_ascii, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
uart_tx_ascii_hex_byte:
    movff       WREG, ram_0x006
    movff       ram_0x006, ram_0x004
    swapf       ram_0x004, F, ACCESS
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    rcall       hex_scratch_nibble_to_ascii
    call        uart_tx_byte_blocking, 0x0
    movwf       ram_0x005, ACCESS
    movff       ram_0x006, ram_0x004
    movlw       0x0F
    rcall       hex_scratch_nibble_to_ascii
    call        uart_tx_byte_blocking, 0x0
    xorwf       ram_0x005, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: hex_scratch_nibble_to_ascii
; Address : 0x43C8
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
hex_scratch_nibble_to_ascii:
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    addlw       LOW(hex_lookup_table)               ; indexed TBLPTR -> hex_lookup_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    tblrd*
    movf        TABLAT, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: eeprom_write_blocking
; Address : 0x43DA
; Notes   : Inferred flash helper; touches flash. Calls: nvm_unlock_and_set_wr.
; ---------------------------------------------------------------------------
eeprom_write_blocking:
    movff       ram_0x003, EEADR
    movff       ram_0x005, EEDATA
    bcf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    movlw       0x00
    btfsc       INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x006, ACCESS
    bcf         INTCON, 7, ACCESS
    rcall       nvm_unlock_and_set_wr
eeprom_write_blocking__wait_write_complete:
    btfsc       EECON1, 1, ACCESS
    bra         eeprom_write_blocking__wait_write_complete
    btfsc       ram_0x006, 0, ACCESS
    bra         eeprom_write_blocking__restore_global_interrupt
    bcf         INTCON, 7, ACCESS
    bra         eeprom_write_blocking__clear_write_enable
eeprom_write_blocking__restore_global_interrupt:
    bsf         INTCON, 7, ACCESS
eeprom_write_blocking__clear_write_enable:
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: nvm_unlock_and_set_wr
; Address : 0x4406
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
nvm_unlock_and_set_wr:
    movlw       0x55
    movwf       EECON2, ACCESS
    movlw       0xAA
    movwf       EECON2, ACCESS
    bsf         EECON1, 1, ACCESS
    retlw       0xAA


; ---------------------------------------------------------------------------
; Function: usb_ep0_service_in_transaction
; Address : 0x4412
; Notes   : Inferred usb helper; touches usb. Calls: usb_ep0_stage_in_data_packet.
; ---------------------------------------------------------------------------
usb_ep0_service_in_transaction:
    movf        ram_0x0CD, W, BANKED
    xorlw       0x04
    bnz         usb_ep0_service_in_transaction__service_payload_stream
    movff       ram_0x0D1, UADDR
    movf        UADDR, W, ACCESS
    movlw       0x05
    btfsc       STATUS, 2, ACCESS
    movlw       0x03
    movwf       ram_0x0CD, BANKED
usb_ep0_service_in_transaction__service_payload_stream:
    decf        ram_0x0C9, W, BANKED
    bnz         usb_ep0_service_in_transaction__return
    call        usb_ep0_stage_in_data_packet, 0x0
    movf        ram_0x0CC, W, BANKED
    xorlw       0x02
    bnz         usb_ep0_service_in_transaction__select_next_data_toggle
    movlw       0x04
    movlb       0x4
    bra         usb_ep0_service_in_transaction__arm_in_bd
usb_ep0_service_in_transaction__select_next_data_toggle:
    movlb       0x4
    movlw       0x48
    btfsc       ram_0x008, 6, BANKED
    movlw       0x08
usb_ep0_service_in_transaction__arm_in_bd:
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
usb_ep0_service_in_transaction__return:
    return      0


; ---------------------------------------------------------------------------
; Function: map_audio_source_selector_to_route_pair
; Address : 0x4448
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
map_audio_source_selector_to_route_pair:
    movff       WREG, ram_0x003
    bra         map_audio_source_selector_to_route_pair__decode_selector
map_audio_source_selector_to_route_pair__selector_zero:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    clrf        ram_0x0B9, BANKED
    bra         map_audio_source_selector_to_route_pair__return
map_audio_source_selector_to_route_pair__selector_one:
    clrf        ram_0x0A0, BANKED
    movlw       0x01
    bra         map_audio_source_selector_to_route_pair__store_pair_byte1
map_audio_source_selector_to_route_pair__selector_two:
    movlw       0x02
    movwf       ram_0x0A0, BANKED
    bra         map_audio_source_selector_to_route_pair__store_pair_byte1
map_audio_source_selector_to_route_pair__selector_three:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    movlw       0x03
map_audio_source_selector_to_route_pair__store_pair_byte1:
    movwf       ram_0x0B9, BANKED
    bra         map_audio_source_selector_to_route_pair__return
map_audio_source_selector_to_route_pair__decode_selector:
    movf        ram_0x003, W, ACCESS
    bz          map_audio_source_selector_to_route_pair__selector_zero
    xorlw       0x01
    bz          map_audio_source_selector_to_route_pair__selector_one
    xorlw       0x03
    bz          map_audio_source_selector_to_route_pair__selector_two
    xorlw       0x01
    bz          map_audio_source_selector_to_route_pair__selector_three
map_audio_source_selector_to_route_pair__return:
    return      0

; ---------------------------------------------------------------------------
; Function: timer3_blocking_delay
; Address : 0x447E
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
timer3_blocking_delay:
    bcf         PIE2, 1, ACCESS
    movlw       0x98
    movwf       T3CON, ACCESS
    bsf         T3CON, 0, ACCESS
    bra         timer3_blocking_delay__check_countdown_remaining
timer3_blocking_delay__reload_next_tick:
    btfss       OSCCON, 1, ACCESS
    bra         timer3_blocking_delay__reload_high_speed_tick
    movlw       0xFC
    movwf       TMR3H, ACCESS
    movlw       0x18
    bra         timer3_blocking_delay__write_low_power_reload_low
timer3_blocking_delay__reload_high_speed_tick:
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
timer3_blocking_delay__write_low_power_reload_low:
    movwf       TMR3L, ACCESS
    bcf         PIR2, 1, ACCESS
timer3_blocking_delay__wait_overflow_flag:
    btfss       PIR2, 1, ACCESS
    bra         timer3_blocking_delay__wait_overflow_flag
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
timer3_blocking_delay__check_countdown_remaining:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    bnz         timer3_blocking_delay__reload_next_tick
    bcf         T3CON, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: uart_emit_formfeed_colon_text_line
; Address : 0x44B2
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, uart_tx_block_from_buffer.
; ---------------------------------------------------------------------------
uart_emit_formfeed_colon_text_line:
    movff       WREG, ram_0x01B
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0C
    call        uart_tx_byte_blocking, 0x0
    movlw       0x3A
    call        uart_tx_byte_blocking, 0x0
    clrf        ram_0x019, ACCESS
    movff       ram_0x01B, ram_0x018
    call        uart_tx_block_from_buffer, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    goto        uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; Function: i2c_tas3108_coeff_write
; Address : 0x44E4
; Notes   : Inferred i2c helper; touches i2c. Calls: i2c_wait_bus_idle, i2c_byte_tx, i2c_emit_tas3108_coeff_from_staged_float.
; ---------------------------------------------------------------------------
i2c_tas3108_coeff_write:
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS
flow_i2c_tas3108_coeff_write_44ea:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_i2c_tas3108_coeff_write_44ea
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x30
    call        i2c_byte_tx, 0x0
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        i2c_emit_tas3108_coeff_from_staged_float, 0x0
    bsf         SSPCON2, 2, ACCESS
flow_i2c_tas3108_coeff_write_4510:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         flow_i2c_tas3108_coeff_write_4510


; ---------------------------------------------------------------------------
; Function: drive_audio_route_select_latches
; Address : 0x4516
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
drive_audio_route_select_latches:
    tstfsz      ram_0x05F, ACCESS
    bra         drive_audio_route_select_latches__decode_route_code
drive_audio_route_select_latches__all_selects_low:
    bcf         LATA, 3, ACCESS
    bra         drive_audio_route_select_latches__clear_lata4_lata5
drive_audio_route_select_latches__set_lata3_clear_lata4_lata5:
    bsf         LATA, 3, ACCESS
drive_audio_route_select_latches__clear_lata4_lata5:
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bra         drive_audio_route_select_latches__return
drive_audio_route_select_latches__clear_lata3_lata4_set_lata5:
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bra         drive_audio_route_select_latches__set_lata5
drive_audio_route_select_latches__clear_lata3_set_lata4_lata5:
    bcf         LATA, 3, ACCESS
    bsf         LATA, 4, ACCESS
drive_audio_route_select_latches__set_lata5:
    bsf         LATA, 5, ACCESS
    bra         drive_audio_route_select_latches__return
drive_audio_route_select_latches__decode_route_code:
    movf        ram_0x093, W, BANKED
    bz          drive_audio_route_select_latches__all_selects_low
    xorlw       0x05
    bz          drive_audio_route_select_latches__set_lata3_clear_lata4_lata5
    xorlw       0x03
    bz          drive_audio_route_select_latches__clear_lata3_lata4_set_lata5
    xorlw       0x01
    bz          drive_audio_route_select_latches__clear_lata3_set_lata4_lata5
drive_audio_route_select_latches__return:
    return      0

; ---------------------------------------------------------------------------
; Function: uart_config
; Address : 0x4546
; Notes   : Inferred uart helper; touches timer,uart.
; ---------------------------------------------------------------------------
uart_config:
    bcf         RCSTA, 7, ACCESS
    bcf         RCON, 7, ACCESS
    movlb       0x0
    clrf        rx_ring_rd, BANKED
    clrf        rx_ring_wr, BANKED
    movlw       0x06
    movwf       TXSTA, ACCESS
    movlw       0x80
    movwf       RCSTA, ACCESS
    movlw       0x48
    movwf       BAUDCON, ACCESS
    bsf         TRISC, 7, ACCESS
    bsf         TRISC, 6, ACCESS
    bcf         PIE1, 4, ACCESS
    bcf         PIR1, 4, ACCESS
    bcf         PIR1, 5, ACCESS
    bcf         PIE1, 5, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bsf         TXSTA, 5, ACCESS
    bsf         RCSTA, 4, ACCESS
    retlw       0x7F


; ---------------------------------------------------------------------------
; Function: preset_replay_selected_table_blocking
; Address : 0x4574
; Notes   : Inferred core helper routine. Calls: preset_table_apply_entry_legacy_blocking.
; ---------------------------------------------------------------------------
preset_replay_selected_table_blocking:
    movlw       0x56
    movwf       ram_0x033, ACCESS
    movlw       0x00
    clrf        ram_0x032, ACCESS
    clrf        ram_0x034, ACCESS
preset_replay_selected_table_blocking__apply_next_entry:
    movff       ram_0x032, ram_0x013
    movff       ram_0x033, ram_0x014
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlw       0x18
    addwf       ram_0x032, F, ACCESS
    movlw       0x00
    addwfc      ram_0x033, F, ACCESS
    incf        ram_0x034, F, ACCESS
    movlw       0x5F
    cpfsgt      ram_0x034, ACCESS
    bra         preset_replay_selected_table_blocking__apply_next_entry
    movwf       ram_0x014, ACCESS
    clrf        ram_0x013, ACCESS
    goto        preset_table_apply_entry_legacy_blocking


; ---------------------------------------------------------------------------
; Function: usb_hid_mailbox_send_reply_if_ready
; Address : 0x45A2
; Notes   : Inferred usb helper; touches usb. Calls: stage_hid_ep1_in_report_from_selector, usb_ep1_in_copy_scratch_buffer_to_bdt.
; ---------------------------------------------------------------------------
usb_hid_mailbox_send_reply_if_ready:
    call        stage_hid_ep1_in_report_from_selector, 0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_45a2_45cc
    btfss       PORTC, 0, ACCESS
    bra         flow_main_usb_service_45a2_45cc
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         flow_main_usb_service_45a2_45cc
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        usb_ep1_in_copy_scratch_buffer_to_bdt, 0x0
flow_main_usb_service_45a2_45cc:
    return      0


; ---------------------------------------------------------------------------
; Function: uint8_to_float32_and_save
; Address : 0x45CE
; Notes   : Inferred core helper routine. Calls: float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
uint8_to_float32_and_save:
    movff       WREG, ram_0x011
    movf        ram_0x011, W, ACCESS
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movlw       0x96
    movwf       ram_0x007, ACCESS
    movlw       0x00
    clrf        ram_0x008, ACCESS
    call        float32_pack_mantissa_exponent_sign, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
    return      0

; ---------------------------------------------------------------------------
; Function: rx_ring_read
; Address : 0x45FA
; Notes   : Inferred core helper routine. Calls: rx_ring_has_data.
; ---------------------------------------------------------------------------
rx_ring_read:
    clrf        ram_0x004, ACCESS
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    bz          rx_ring_read__return_byte_or_zero
    movlw       0x00
    movlb       0x0
    addwf       rx_ring_rd, W, BANKED
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    movf        INDF2, W, ACCESS
    movwf       ram_0x004, ACCESS
    incf        rx_ring_rd, F, BANKED
    movlw       0xBF
    cpfsgt      rx_ring_rd, BANKED
    bra         rx_ring_read__return_byte_or_zero
    clrf        rx_ring_rd, BANKED
rx_ring_read__return_byte_or_zero:
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep1_configure_hid_buffers
; Address : 0x4624
; Notes   : Inferred usb helper; touches usb.
; ---------------------------------------------------------------------------
usb_ep1_configure_hid_buffers:
    clrf        ram_0x0CA, BANKED
    movlw       0x1E
    movwf       UEP1, ACCESS
    movlw       0x40
    movlb       0x4
    movwf       ram_0x00D, BANKED
    movlw       0x04
    movwf       ram_0x00F, BANKED
    movlw       0x2C
    movwf       ram_0x00E, BANKED
    movlw       0x08
    movwf       ram_0x00C, BANKED
    bsf         ram_0x00C, 7, BANKED
    movlw       0x04
    movwf       ram_0x013, BANKED
    movlw       0x6C
    movwf       ram_0x012, BANKED
    movlw       0x40
    movwf       ram_0x010, BANKED
    retlw       0x40


; ---------------------------------------------------------------------------
; Function: i2c_receive_sspbuf_bounded
; Address : 0x464C
; Notes   : Inferred i2c helper; touches i2c.
; ---------------------------------------------------------------------------
i2c_receive_sspbuf_bounded:
    movff       SSPCON1, ram_0x003
    movlw       0x0F
    andwf       ram_0x003, F, ACCESS
    movf        ram_0x003, W, ACCESS
    xorlw       0x08
    bz          i2c_receive_sspbuf_bounded__enable_rcen
    movff       SSPCON1, ram_0x003
    movlw       0x0F
    andwf       ram_0x003, F, ACCESS
    movf        ram_0x003, W, ACCESS
    xorlw       0x0B
    btfsc       STATUS, 2, ACCESS
i2c_receive_sspbuf_bounded__enable_rcen:
    bsf         SSPCON2, 3, ACCESS
flow_main_i2c_service_464c_466a:
    btfss       SSPSTAT, 0, ACCESS
    bra         flow_main_i2c_service_464c_466a
    movf        SSPBUF, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: fw_update_emit_zero_status_lines
; Address : 0x4672
; Notes   : Inferred core helper routine. Calls: uart_emit_formfeed_colon_text_line.
; ---------------------------------------------------------------------------
fw_update_emit_zero_status_lines:
    lfsr        FSR2, 0x01F4
    lfsr        FSR1, 0x001C
    movlw       0x07
flow_main_core_service_4672_467c:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_4672_467c
    movlw       0x1C
    call        uart_emit_formfeed_colon_text_line, 0x0
    movlw       0x1C
    call        uart_emit_formfeed_colon_text_line, 0x0
    movlw       0x1C
    goto        uart_emit_formfeed_colon_text_line


; ---------------------------------------------------------------------------
; Function: uart_tx_block_from_buffer
; Address : 0x4696
; Notes   : Transmits a buffered UART block one byte at a time.
; ---------------------------------------------------------------------------
uart_tx_block_from_buffer:
    clrf        ram_0x01A, ACCESS
    bra         uart_tx_block_from_buffer__check_terminator
uart_tx_block_from_buffer__emit_current_byte:
    rcall       uart_tx_block_load_indexed_byte
    call        uart_tx_byte_blocking, 0x0
    incf        ram_0x01A, F, ACCESS
uart_tx_block_from_buffer__check_terminator:
    rcall       uart_tx_block_load_indexed_byte
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         uart_tx_block_from_buffer__emit_current_byte


; ---------------------------------------------------------------------------
; Function: uart_tx_block_load_indexed_byte
; Address : 0x46AA
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
uart_tx_block_load_indexed_byte:
    movf        ram_0x01A, W, ACCESS
    addwf       ram_0x018, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x019, W, ACCESS
    movwf       FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_secondary_dev_write
; Address : 0x46BA
; Notes   : Inferred i2c helper; touches i2c. Calls: i2c_byte_tx.
; ---------------------------------------------------------------------------
i2c_secondary_dev_write:
    movff       WREG, ram_0x007
    bsf         SSPCON2, 0, ACCESS
flow_i2c_secondary_dev_write_46c0:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_i2c_secondary_dev_write_46c0
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        ram_0x007, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS
flow_i2c_secondary_dev_write_46d8:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         flow_i2c_secondary_dev_write_46d8


; ---------------------------------------------------------------------------
; Function: eeprom_write_byte_if_changed
; Address : 0x46DE
; Notes   : Inferred flash helper routine. Calls: eeprom_read_byte, eeprom_write_blocking.
; ---------------------------------------------------------------------------
eeprom_write_byte_if_changed:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    call        eeprom_read_byte, 0x0
    xorwf       ram_0x009, W, ACCESS
    bz          eeprom_write_byte_if_changed__return_unchanged
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    movff       ram_0x009, ram_0x005
    call        eeprom_write_blocking, 0x0
eeprom_write_byte_if_changed__return_unchanged:
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4700
; Address : 0x4700
; Notes   : Inferred usb helper; touches usb. Calls: usb_disconnect_wait_clear_state, usb_bus_reset_reinitialize.
; ---------------------------------------------------------------------------
main_usb_service_4700:
    decf        usb_reinit_pending, W, BANKED
    btfsc       STATUS, 2, ACCESS
    call        usb_disconnect_wait_clear_state, 0x0
    clrf        UCON, ACCESS
    movlw       0x15
    movwf       UCFG, ACCESS
    clrf        UIE, ACCESS
    bsf         UCON, 3, ACCESS
    call        usb_bus_reset_reinitialize, 0x0
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0CD, BANKED
    clrf        usb_reinit_pending, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4720
; Address : 0x4720
; Notes   : Inferred usb helper; touches timer,usb. Calls: main_core_service_496a.
; ---------------------------------------------------------------------------
main_usb_service_4720:
    movff       UIE, ram_0x092
    movlw       0x04
    movwf       UIE, ACCESS
    bcf         UIR, 4, ACCESS
    bsf         UCON, 1, ACCESS
    bcf         PIR2, 5, ACCESS
    bsf         PIE2, 5, ACCESS
    call        main_core_service_496a, 0x0
    bcf         PIE2, 5, ACCESS
    movlb       0x0
    movf        ram_0x092, W, BANKED
    iorwf       UIE, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: clear_ram_span_from_staged_addr_count
; Address : 0x473E
; Notes   : Clears a RAM span from an FSR2 pointer and byte count.
; ---------------------------------------------------------------------------
clear_ram_span_from_staged_addr_count:
    clrf        ram_0x006, ACCESS
    bra         ram_block_clear__check_remaining
ram_block_clear__clear_next_byte:
    movf        ram_0x006, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x006, F, ACCESS
ram_block_clear__check_remaining:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x006, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         ram_block_clear__clear_next_byte


; ---------------------------------------------------------------------------
; Function: usb_poll_host_presence_reinit_or_shutdown
; Address : 0x475C
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4700, usb_shutdown.
; ---------------------------------------------------------------------------
usb_poll_host_presence_reinit_or_shutdown:
    movlb       0x0
    decf        usb_reinit_pending, W, BANKED
    bz          usb_poll_host_presence_reinit_or_shutdown__return
    btfss       PORTC, 0, ACCESS
    bra         usb_poll_host_presence_reinit_or_shutdown__host_absent_shutdown_check
    btfss       UCON, 3, ACCESS
    call        main_usb_service_4700, 0x0
    bra         usb_poll_host_presence_reinit_or_shutdown__return
usb_poll_host_presence_reinit_or_shutdown__host_absent_shutdown_check:
    btfss       UCON, 3, ACCESS
    bra         usb_poll_host_presence_reinit_or_shutdown__return
    call        usb_shutdown, 0x0
    clrf        usb_reinit_pending, BANKED
usb_poll_host_presence_reinit_or_shutdown__return:
    return      0


; ---------------------------------------------------------------------------
; Function: timer3_arm_interrupt_countdown
; Address : 0x477A
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
timer3_arm_interrupt_countdown:
    movlw       0x98
    movwf       T3CON, ACCESS
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
    movwf       TMR3L, ACCESS
    movff       ram_0x003, ram_0x08C
    movff       ram_0x004, ram_0x08D
    bcf         PIR2, 1, ACCESS
    bsf         T3CON, 0, ACCESS
    bsf         PIE2, 1, ACCESS
    retlw       0x30

; ---------------------------------------------------------------------------
; Function: standby_event_dispatch
; Address : 0x4796
; Notes   : Inferred adc helper routine. Calls: run_wake_rail_gate_and_dsp_cold_init, hw_standby_shutdown.
; ---------------------------------------------------------------------------
standby_event_dispatch:
    movlb       0x0
    btfss       event_flags, 2, BANKED
    bra         standby_event_dispatch__tail_reconcile_state
    btfss       active_flags, 3, ACCESS
    bra         standby_event_dispatch__shutdown_path
    call        run_wake_rail_gate_and_dsp_cold_init, 0x0
    bra         standby_event_dispatch__clear_pending_event
standby_event_dispatch__shutdown_path:
    call        hw_standby_shutdown, 0x0
standby_event_dispatch__clear_pending_event:
    bcf         event_flags, 2, BANKED
standby_event_dispatch__tail_reconcile_state:
    movlw       0x01
    goto        cmd_dispatch_gated

; ---------------------------------------------------------------------------
; Function: mssp_hard_reset
; Address : 0x47B2
; Notes   : Inferred i2c helper; touches i2c.
; ---------------------------------------------------------------------------
mssp_hard_reset:
    movff       WREG, ram_0x004
    movlw       0x3F
    andwf       SSPSTAT, F, ACCESS
    clrf        SSPCON1, ACCESS
    clrf        SSPCON2, ACCESS
    movf        ram_0x004, W, ACCESS
    iorwf       SSPCON1, F, ACCESS
    movf        ram_0x003, W, ACCESS
    iorwf       SSPSTAT, F, ACCESS
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    bsf         SSPCON1, 5, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: run_main_service_pass
; Address : 0x47CE
; Notes   : Inferred core helper routine. Calls: usb_hid_dispatch_out_report_if_ready, uart_link_parser_drain_rx_and_forward, poll_src4382_route_monitor.
; ---------------------------------------------------------------------------
run_main_service_pass:
    call        usb_hid_dispatch_out_report_if_ready, 0x0
    call        uart_link_parser_drain_rx_and_forward, 0x0
    call        poll_src4382_route_monitor, 0x0
    call        standby_event_dispatch, 0x0
    call        persist_dirty_runtime_state_to_eeprom, 0x0
    goto        an0_hysteresis_monitor

; ---------------------------------------------------------------------------
; Inline Data Table (0x47E6-0x47FB)
; ---------------------------------------------------------------------------
fw_update_status_text_seed_table:  ; UART status strings for FW update
    dw  0x202D, 0x4146, 0x4C49, 0x0020, 0x5746, 0x555F, 0x6470, 0x3000
    dw  0x3030, 0x3030, 0x0030

; ---------------------------------------------------------------------------
; Remaining Code (0x47FC-0x496F)
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; Function: report_cmd29_status
; Address : 0x47FC
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
report_cmd29_status:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x29
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    btfss       active_flags, 1, ACCESS
    movlw       0x00
    goto        uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: usb_delay_countdown_with_clrwdt
; Address : 0x4812
; Notes   : Inferred usb helper routine. Calls: usb_disconnect_handler.
; ---------------------------------------------------------------------------
usb_delay_countdown_with_clrwdt:
    bra         usb_delay_countdown_with_clrwdt__check_remaining
usb_delay_countdown_with_clrwdt__decrement:
    call        usb_disconnect_handler, 0x0
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
usb_delay_countdown_with_clrwdt__check_remaining:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         usb_delay_countdown_with_clrwdt__decrement


; ---------------------------------------------------------------------------
; Function: usb_disconnect_wait_clear_state
; Address : 0x4828
; Notes   : Inferred usb helper; touches usb. Calls: usb_delay_countdown_with_clrwdt.
; ---------------------------------------------------------------------------
usb_disconnect_wait_clear_state:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlw       0xFF
    setf        ram_0x004, ACCESS
    setf        ram_0x003, ACCESS
    call        usb_delay_countdown_with_clrwdt, 0x0
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: usb_clear_activity_interrupt_after_settle
; Address : 0x483C
; Notes   : Inferred usb helper; touches usb. Calls: usb_activity_settle_delay_with_clrwdt.
; ---------------------------------------------------------------------------
usb_clear_activity_interrupt_after_settle:
    call        usb_activity_settle_delay_with_clrwdt, 0x0
    bcf         UCON, 1, ACCESS
    bcf         UIE, 2, ACCESS
    bra         usb_clear_activity_interrupt_after_settle__poll_flag
usb_clear_activity_interrupt_after_settle__clear_flag:
    bcf         UIR, 2, ACCESS
usb_clear_activity_interrupt_after_settle__poll_flag:
    btfss       UIR, 2, ACCESS
    return      0
    bra         usb_clear_activity_interrupt_after_settle__clear_flag


; ---------------------------------------------------------------------------
; Function: fw_update_emit_bf18_status
; Address : 0x484E
; Notes   : Emits BF/18/01 factory-reset status frame over UART.
; ---------------------------------------------------------------------------
fw_update_emit_bf18_status:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x18
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    goto        uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: uart_rx_ring_drain_all
; Address : 0x4860
; Notes   : Inferred uart helper routine. Calls: rx_ring_read, rx_ring_has_data.
; ---------------------------------------------------------------------------
uart_rx_ring_drain_all:
    bra         uart_rx_ring_drain_all__check_more
uart_rx_ring_drain_all__discard_next_byte:
    call        rx_ring_read, 0x0
uart_rx_ring_drain_all__check_more:
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         uart_rx_ring_drain_all__discard_next_byte


; ---------------------------------------------------------------------------
; Function: rx_ring_has_data
; Address : 0x4872
; Notes   : Checks whether RX ring has unread data (write index != read index).
; ---------------------------------------------------------------------------
rx_ring_has_data:
    movlb       0x0
    movf        rx_ring_wr, W, BANKED
    clrf        PRODL, ACCESS
    cpfseq      rx_ring_rd, BANKED
    incf        PRODL, F, ACCESS
    movff       PRODL, ram_0x003
    movf        ram_0x003, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: eeprom_read_byte
; Address : 0x4884
; Notes   : Reads one byte from EEPROM via EEADR/EECON1.RD.
; ---------------------------------------------------------------------------
eeprom_read_byte:
    movff       ram_0x003, EEADR
    bcf         EECON1, 6, ACCESS
    bcf         EECON1, 7, ACCESS
    bsf         EECON1, 0, ACCESS
    dw          0xF000
    dw          0xF000
    movf        EEDATA, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: uart_tx_byte_blocking
; Address : 0x4896
; Notes   : Inferred uart helper; touches uart.
; ---------------------------------------------------------------------------
uart_tx_byte_blocking:
    movff       WREG, ram_0x003
uart_tx_trmt_busywait:
    btfss       TXSTA, 1, ACCESS
    bra         uart_tx_trmt_busywait
    movff       ram_0x003, TXREG
    movf        ram_0x003, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: timer0_rearm_50ms_heartbeat
; Address : 0x48A6
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
timer0_rearm_50ms_heartbeat:
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    bcf         INTCON, 2, ACCESS
    bsf         INTCON, 5, ACCESS
    bsf         T0CON, 7, ACCESS
    retlw       0x71

; ---------------------------------------------------------------------------
; Function: i2c_wait_bus_idle
; Address : 0x48B6
; Notes   : Inferred i2c helper; touches i2c. Calls: boot_init_peripherals_and_enter_adc_gate, usb_sie_endpoint_pump, run_main_service_pass.
; ---------------------------------------------------------------------------
i2c_wait_bus_idle:
    movff       SSPCON2, ram_0x003
    movlw       0x1F
    andwf       ram_0x003, F, ACCESS
    btfsc       STATUS, 2, ACCESS
    btfsc       SSPSTAT, 2, ACCESS
    bra         i2c_wait_bus_idle
    retlw       0x1F
boot_cold_init__run_peripheral_init:
    call        boot_init_peripherals_and_enter_adc_gate, 0x0
run_main_foreground_loop:
    call        usb_sie_endpoint_pump, 0x0
    call        run_main_service_pass, 0x0
    bra         run_main_foreground_loop

; ---------------------------------------------------------------------------
; Function: hard_reset
; Address : 0x48D4
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
hard_reset:
    clrf        INTCON, ACCESS
    dw          0xF000
    dw          0xF000
    reset
    dw          0xF000
    dw          0xF000
    return      0


; ---------------------------------------------------------------------------
; Function: i2c_tas3108_reg1f_02_clear_source_pins
; Address : 0x48E2
; Notes   : Inferred i2c helper routine. Calls: i2c_tas3108_reg1f_write.
; ---------------------------------------------------------------------------
i2c_tas3108_reg1f_02_clear_source_pins:
    movlw       0x02
    call        i2c_tas3108_reg1f_write, 0x0
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: usb_shutdown
; Address : 0x48F0
; Notes   : Inferred usb helper; touches usb.
; ---------------------------------------------------------------------------
usb_shutdown:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    movlw       0x01
    movwf       usb_reinit_pending, BANKED
    retlw       0x01


; ---------------------------------------------------------------------------
; Function: usb_ep1_configure_if_enabled
; Address : 0x48FE
; Notes   : Inferred core helper routine. Calls: usb_ep1_configure_hid_buffers.
; ---------------------------------------------------------------------------
usb_ep1_configure_if_enabled:
    movff       WREG, ram_0x003
    decf        ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    call        usb_ep1_configure_hid_buffers, 0x0
    return      0


; ---------------------------------------------------------------------------
; Function: timer3_timeout_elapsed_carry
; Address : 0x490C
; Notes   : Inferred usb helper; touches timer,usb. Calls: usb_disconnect_wait_clear_state.
; ---------------------------------------------------------------------------
timer3_timeout_elapsed_carry:
    btfss       T3CON, 0, ACCESS
    bra         timer3_timeout_elapsed_carry__timer_stopped
    bcf         STATUS, 0, ACCESS
    bra         timer3_timeout_elapsed_carry__return
timer3_timeout_elapsed_carry__timer_stopped:
    bsf         STATUS, 0, ACCESS
timer3_timeout_elapsed_carry__return:
    return      0
usb_reinit_after_wake__clear_pending_and_poll_host:
    btfsc       UCON, 3, ACCESS
    call        usb_disconnect_wait_clear_state, 0x0
    clrf        usb_reinit_pending, BANKED
    goto        usb_poll_host_presence_reinit_or_shutdown


; ---------------------------------------------------------------------------
; Function: usb_activity_settle_delay_with_clrwdt
; Address : 0x4924
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_activity_settle_delay_with_clrwdt:
    movlw       0x03
    movwf       ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    goto        usb_delay_countdown_with_clrwdt__check_remaining


; ---------------------------------------------------------------------------
; Function: timer3_blocking_delay_1ms
; Address : 0x492E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
timer3_blocking_delay_1ms:
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    goto        timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: uart_reconfigure_and_resync_parser
; Address : 0x4938
; Notes   : Inferred uart helper routine. Calls: uart_config.
; ---------------------------------------------------------------------------
uart_reconfigure_and_resync_parser:
    call        uart_config, 0x0
    bcf         active_flags, 0, ACCESS
    clrf        rx_frame_position, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: timer3_blocking_delay_2ms
; Address : 0x4942
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
timer3_blocking_delay_2ms:
    clrf        ram_0x004, ACCESS
    movlw       0x02
    movwf       ram_0x003, ACCESS
    goto        timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: timer3_stop_interrupt_countdown
; Address : 0x494C
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
timer3_stop_interrupt_countdown:
    bcf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS
    bcf         PIE2, 1, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4954
; Address : 0x4954
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4954:
    movlw       0x01
    goto        i2c_tas3108_reg1f_write


; ---------------------------------------------------------------------------
; Function: main_core_service_495a
; Address : 0x495A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_495a:
    goto        usb_ep0_dispatch_hid_setup_request


; ---------------------------------------------------------------------------
; Function: main_uart_service_495e
; Address : 0x495E
; Notes   : Inferred uart helper; touches uart.
; ---------------------------------------------------------------------------
main_uart_service_495e:
    bsf         RCSTA, 4, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: usb_disconnect_handler
; Address : 0x4962
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_disconnect_handler:
    clrwdt
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_4966
; Address : 0x4966
; Notes   : Inferred i2c helper; touches i2c.
; ---------------------------------------------------------------------------
main_i2c_service_4966:
    bcf         SSPCON1, 5, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_496a
; Address : 0x496A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_496a:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_496c
; Address : 0x496C
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_496c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_496e
; Address : 0x496E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_496e:
    return      0

; ---------------------------------------------------------------------------
; Erased Flash Padding
; ---------------------------------------------------------------------------
    fill 0xFFFF, (0x5600 - $) / 2

; ---------------------------------------------------------------------------
; DSP Preset Table A
; ---------------------------------------------------------------------------
    org 0x5600
preset_table_a:
    dw  0xC801, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4201, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4401, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xC901, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5101, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5301, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCA01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5601, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6201, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCB01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6501, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7101, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCC01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7401, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7601, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCD01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8301, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8501, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x9001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xD401, 0x0004, 0x0000, 0x0100, 0x3101, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3101, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3201, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3201, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3301, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3301, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3401, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3401, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3501, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3501, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3601, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3601, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF

; ---------------------------------------------------------------------------
; EEPROM Data
; ---------------------------------------------------------------------------
    org 0xF00000
eeprom_data:
    db  0xFF, 0xFF, 0xFF, 0xA0, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x01, 0x03, 0x04, 0x01  ; ................
    db  0x00, 0x00, 0x00, 0x00, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0x03, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0x02, 0x03, 0x30, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ..0.............
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x02  ; ................

    END

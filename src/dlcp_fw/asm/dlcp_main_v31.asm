    LIST P=18F2455
    #include <p18f2455.inc>
    #include "dlcp_main_ram.inc"

; V3.1 named RAM aliases (multi-purpose registers)
dsp_fault_flags         EQU  0x07F   ; bit2=ACKSTAT, bit6=DSP ping, bits[5:3]=retry
timeout_lo              EQU  0x00B   ; bounded wait countdown low byte
timeout_hi              EQU  0x00C   ; bounded wait countdown high byte
saved_w                 EQU  0x005   ; saved WREG for i2c_byte_tx


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
    goto        flow_app_entry_1014
    dw          0xFFFF
    dw          0xFFFF
    movff       FSR2L, isr_save_fsr2l
    movff       FSR2H, isr_save_fsr2h
    call        main_isr_dispatch, 0x1
flow_app_entry_1014:
    goto        flow_main_flash_service_3ce8_3d4e

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
    bnz         flow_hid_command_dispatch_10ca
    bra         hid_cmd_xor_dispatch
flow_hid_command_dispatch_10ca:
    movlb       0x0
    clrf        ram_0x0CB, BANKED
    bra         hid_cmd_xor_dispatch
flow_hid_command_dispatch_10d0:
    movff       ram_0x11B, ram_0x097
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x09
    bnz         flow_hid_command_dispatch_1104
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
flow_hid_command_dispatch_10e0:
    rcall       main_core_service_15b0
    movf        INDF2, W, ACCESS
    bz          flow_hid_command_dispatch_10fa
    rcall       main_core_service_15b0
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x02
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         flow_hid_command_dispatch_10fc
flow_hid_command_dispatch_10fa:
    rcall       main_core_service_15be
flow_hid_command_dispatch_10fc:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_10e0
flow_hid_command_dispatch_1104:
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x0A
    bnz         flow_hid_command_dispatch_111a
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
flow_hid_command_dispatch_1110:
    rcall       main_core_service_15be
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_1110
flow_hid_command_dispatch_111a:
    movlw       0x03
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movff       ram_0x11B, ram_0x0C2
    bsf         ram_0x0BD, 5, BANKED
flow_hid_command_dispatch_1126:
    call        main_timer_service_48a6, 0x0
flow_hid_command_dispatch_112a:
    call        main_core_service_492e, 0x0
flow_hid_command_dispatch_112e:
    call        main_core_service_2328, 0x0
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1134:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         flow_hid_command_dispatch_116a
    movff       ram_0x11C, ram_0x0B7
    bra         flow_hid_command_dispatch_115c
flow_hid_command_dispatch_1140:
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bra         flow_hid_command_dispatch_112a
flow_hid_command_dispatch_114a:
    movff       ram_0x11D, ram_0x0B8
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bsf         ram_0x07F, 0, BANKED
    bsf         ram_0x094, 4, BANKED
    bra         flow_hid_command_dispatch_112a
flow_hid_command_dispatch_115c:
    movlb       0x0
    movf        ram_0x0B7, W, BANKED
    xorlw       0x01
    bz          flow_hid_command_dispatch_1140
    xorlw       0x03
    bz          flow_hid_command_dispatch_114a
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_116a:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          flow_hid_command_dispatch_1172
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1172:
    movff       ram_0x11E, ram_0x0B5
    movlw       0x04
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movlw       0x02
    movwf       ram_0x0C2, BANKED
    movf        ram_0x0B5, W, BANKED
    xorlw       0x06
    bnz         flow_hid_command_dispatch_11c0
    movlw       0x05
    movwf       i2c_coeff_3, ACCESS
flow_hid_command_dispatch_118a:
    rcall       main_core_service_15b0
    movf        INDF2, W, ACCESS
    bz          flow_hid_command_dispatch_11a4
    rcall       main_core_service_15b0
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x00
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         flow_hid_command_dispatch_11b2
flow_hid_command_dispatch_11a4:
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
flow_hid_command_dispatch_11b2:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x13
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_118a
    movlb       0x0
    bsf         ram_0x0BD, 4, BANKED
    bra         flow_hid_command_dispatch_1126
flow_hid_command_dispatch_11c0:
    movf        ram_0x0B5, W, BANKED
    xorlw       0x05
    bz          flow_hid_command_dispatch_112a
    movf        ram_0x0B5, W, BANKED
    xorlw       0x07
    bz          flow_hid_command_dispatch_112a
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_11ce:
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
    bra         flow_hid_command_dispatch_124e
flow_hid_command_dispatch_124a:
    movlb       0x0
    bsf         ram_0x0A4, 5, BANKED
flow_hid_command_dispatch_124e:
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
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
flow_hid_command_dispatch_129c:
    bz          flow_hid_command_dispatch_12a2
    bsf         event_flags, 3, BANKED
    bsf         ram_0x094, 1, BANKED
flow_hid_command_dispatch_12a2:
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
    bz          flow_hid_command_dispatch_12ca
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12ca:
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x04C, ACCESS
    movlw       0x01
    btfss       active_flags, 5, ACCESS
    movlw       0x00
    xorwf       ram_0x04C, F, ACCESS
    bz          flow_hid_command_dispatch_12e0
    bsf         event_flags, 5, BANKED
    bsf         ram_0x094, 3, BANKED
flow_hid_command_dispatch_12e0:
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
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A6, W, BANKED
    lfsr        FSR2, 0x0061
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A7, W, BANKED
    lfsr        FSR2, 0x0062
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A8, W, BANKED
    lfsr        FSR2, 0x0063
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A9, W, BANKED
    lfsr        FSR2, 0x0064
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
flow_hid_command_dispatch_1324:
    bsf         event_flags, 4, BANKED
    movff       input_select, input_select_mirror
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    btfss       active_flags, 4, ACCESS
    bra         flow_hid_command_dispatch_1342
    bsf         active_flags, 5, ACCESS
    bra         flow_hid_command_dispatch_1344
flow_hid_command_dispatch_1342:
    bcf         active_flags, 5, ACCESS
flow_hid_command_dispatch_1344:
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
flow_hid_command_dispatch_1374:
    movlw       0x05
    bra         flow_hid_command_dispatch_1384
flow_hid_command_dispatch_1378:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         flow_hid_command_dispatch_138a
    call        main_core_service_4942, 0x0
    movlw       0x06
flow_hid_command_dispatch_1384:
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    bra         flow_hid_command_dispatch_112e
flow_hid_command_dispatch_138a:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          flow_hid_command_dispatch_1392
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1392:
    call        main_core_service_4942, 0x0
    bra         flow_hid_command_dispatch_1374
flow_hid_command_dispatch_1398:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    xorlw       0x0F
    btfsc       STATUS, 2, ACCESS
    bsf         active_flags, 7, ACCESS
flow_hid_command_dispatch_13a2:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x07
    bnz         flow_hid_command_dispatch_13ba
    movlb       0x1
    tstfsz      ram_0x01B, BANKED
    bra         flow_hid_command_dispatch_13ba
    movlb       0x0
    clrf        ram_0x0C5, BANKED
    movlw       0x56
    movwf       ram_0x083, BANKED
    movlw       0x00
    clrf        ram_0x082, BANKED
flow_hid_command_dispatch_13ba:
    bcf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
    clrf        rx_ring_wr, BANKED
    clrf        rx_ring_rd, BANKED
    call        main_flash_service_2bb8, 0x0
flow_hid_command_dispatch_13ca:
    movff       i2c_coeff_2, ram_0x0C1
    bra         flow_hid_command_dispatch_112e
flow_hid_command_dispatch_13d0:
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
    call        main_core_service_265c, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x00
    clrf        ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    call        hard_reset, 0x0
    bra         flow_hid_command_dispatch_15aa
fw_update_init_sequence:
    movlb       0x0
    tstfsz      ram_0x0CB, BANKED
    bra         flow_hid_command_dispatch_14fc
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
    call        ram_block_clear, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x9A
    movwf       ram_0x003, ACCESS
    movlw       0x2D
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xD1
    movwf       ram_0x003, ACCESS
    movlw       0x08
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    call        factory_reset_status_emit, 0x0
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
    bnc         flow_hid_command_dispatch_14fa
    movlw       0x01
    movwf       ram_0x0CB, BANKED
    clrf        i2c_coeff_3, ACCESS
flow_hid_command_dispatch_14ce:
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
    bz          flow_hid_command_dispatch_14f0
    movlb       0x0
    clrf        ram_0x0CB, BANKED
flow_hid_command_dispatch_14f0:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x05
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_14ce
    bra         flow_hid_command_dispatch_14fc
flow_hid_command_dispatch_14fa:
    clrf        ram_0x0CB, BANKED
flow_hid_command_dispatch_14fc:
    movlb       0x0
    movf        ram_0x0CB, W, BANKED
    bnz         flow_hid_command_dispatch_1504
    bra         flow_hid_command_dispatch_13ca
flow_hid_command_dispatch_1504:
    call        fw_update_relay, 0x0
    bra         flow_hid_command_dispatch_13ca
flow_hid_command_dispatch_150a:
    movff       ram_0x11E, i2c_coeff_1
    movff       ram_0x11F, i2c_coeff_0
    movff       i2c_coeff_2, ram_0x0C1
    call        main_core_service_2328, 0x0
    movf        ram_0x07D, W, BANKED
    xorwf       i2c_coeff_1, W, ACCESS
    bnz         flow_hid_command_dispatch_1524
    movf        ram_0x07C, W, BANKED
    xorwf       i2c_coeff_0, W, ACCESS
flow_hid_command_dispatch_1524:
    bnz         flow_hid_command_dispatch_1532
    call        main_core_service_4672, 0x0
    movlw       0xAA
    movlb       0x1
    movwf       ram_0x05C, BANKED
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1532:
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
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_154c:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    bra         flow_hid_command_dispatch_15aa
hid_cmd_xor_dispatch:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x01
    bz          flow_hid_command_dispatch_15aa
    xorlw       0x03
    bz          flow_hid_command_dispatch_15aa
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1562
    bra         flow_hid_command_dispatch_10d0
flow_hid_command_dispatch_1562:
    xorlw       0x07
    bnz         flow_hid_command_dispatch_1568
    bra         flow_hid_command_dispatch_1134
flow_hid_command_dispatch_1568:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_156e
    bra         flow_hid_command_dispatch_11ce
flow_hid_command_dispatch_156e:
    xorlw       0x03
    bnz         flow_hid_command_dispatch_1574
    bra         flow_hid_command_dispatch_1378
flow_hid_command_dispatch_1574:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_157a
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_157a:
    xorlw       0x0F
    bnz         flow_hid_command_dispatch_1580
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_1580:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1586
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_1586:
    xorlw       0x03
    bnz         flow_hid_command_dispatch_158c
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_158c:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1592
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_1592:
    xorlw       0x07
    bnz         flow_hid_command_dispatch_1598
    bra         flow_hid_command_dispatch_1398
flow_hid_command_dispatch_1598:
    xorlw       0x4C
    bnz         flow_hid_command_dispatch_159e
    bra         flow_hid_command_dispatch_13d0
flow_hid_command_dispatch_159e:
    xorlw       0x01
    bz          flow_hid_command_dispatch_150a
    xorlw       0x03
    bnz         flow_hid_command_dispatch_15a8
    bra         fw_update_init_sequence
flow_hid_command_dispatch_15a8:
    bra         flow_hid_command_dispatch_154c
flow_hid_command_dispatch_15aa:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_15b0
; Address : 0x15B0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_15b0:
    movlw       0x1A
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_15be
; Address : 0x15BE
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_15be:
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
; Notes   : Inferred flash helper; touches flash. Calls: main_uart_service_43a2, uart_tx_byte_blocking, uart_rx_with_framing.
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
flow_fw_update_relay_15e4:
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
    bc          flow_fw_update_relay_1634
    movff       ram_0x04A, ram_0x045
    clrf        ram_0x048, ACCESS
flow_fw_update_relay_1606:
    btfss       ram_0x07D, 5, BANKED
    bra         flow_fw_update_relay_1610
    movlw       0x01
    movwf       ram_0x044, ACCESS
    bra         flow_fw_update_relay_1612
flow_fw_update_relay_1610:
    clrf        ram_0x044, ACCESS
flow_fw_update_relay_1612:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x07C, F, BANKED
    rlcf        ram_0x07D, F, BANKED
    btfsc       ram_0x045, 0, ACCESS
    bsf         ram_0x07C, 0, BANKED
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x045, F, ACCESS
    movf        ram_0x044, W, ACCESS
    bz          flow_fw_update_relay_162c
    movlw       0x02
    xorwf       ram_0x07C, F, BANKED
    movlw       0x44
    xorwf       ram_0x07D, F, BANKED
flow_fw_update_relay_162c:
    incf        ram_0x048, F, ACCESS
    movlw       0x07
    cpfsgt      ram_0x048, ACCESS
    bra         flow_fw_update_relay_1606
flow_fw_update_relay_1634:
    movlw       0x40
    subwf       ram_0x084, W, BANKED
    movlw       0x00
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_1640
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_1640:
    movlw       0xC0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bnc         flow_fw_update_relay_164c
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_164c:
    movlw       0x0F
    andwf       ram_0x084, W, BANKED
    movwf       ram_0x08A, BANKED
    clrf        ram_0x08B, BANKED
    iorwf       ram_0x08B, W, BANKED
    bz          flow_fw_update_relay_165a
    bra         flow_fw_update_relay_182e
flow_fw_update_relay_165a:
    movf        ram_0x087, W, BANKED
    iorwf       ram_0x086, W, BANKED
    bnz         flow_fw_update_relay_1662
    bra         flow_fw_update_relay_179c
flow_fw_update_relay_1662:
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
    call        main_uart_service_43a2, 0x0
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
flow_fw_update_relay_16fa:
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
    bnz         flow_fw_update_relay_172a
    movlw       0x01
    movwf       ram_0x043, ACCESS
    bra         flow_fw_update_relay_1796
flow_fw_update_relay_172a:
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
    call        main_core_service_41b6, 0x0
    movwf       ram_0x01B, ACCESS
    clrf        ram_0x019, ACCESS
    movff       ram_0x01B, ram_0x018
    call        uart_tx_block_from_buffer, 0x0
    movlw       0x21
    call        uart_tx_byte_blocking, 0x0
    call        main_uart_service_4860, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    movlw       0x19
    movlb       0x0
    subwf       ram_0x09F, W, BANKED
    bc          flow_fw_update_relay_1792
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
    bra         flow_fw_update_relay_1796
flow_fw_update_relay_1792:
    incf        ram_0x09F, F, BANKED
    bra         flow_fw_update_relay_18dc
flow_fw_update_relay_1796:
    movf        ram_0x043, W, ACCESS
    bnz         flow_fw_update_relay_179e
    bra         flow_fw_update_relay_16fa
flow_fw_update_relay_179c:
    clrf        ram_0x08E, BANKED
flow_fw_update_relay_179e:
    movlw       0xBF
    movlb       0x0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_182e
    movlw       0x04
    subwf       ram_0x08E, W, BANKED
    bc          flow_fw_update_relay_17bc
    incf        ram_0x08E, F, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
flow_fw_update_relay_17bc:
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
    call        main_uart_service_4860, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
flow_fw_update_relay_182e:
    movlw       0xBF
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_18cc
    btfss       ram_0x084, 0, BANKED
    bra         flow_fw_update_relay_18bc
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
    bra         flow_fw_update_relay_18a0
flow_fw_update_relay_1884:
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
flow_fw_update_relay_18a0:
    movf        ram_0x047, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    bnz         flow_fw_update_relay_1884
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    clrf        INDF2, ACCESS
    bra         flow_fw_update_relay_18c0
flow_fw_update_relay_18bc:
    movff       ram_0x04A, ram_0x046
flow_fw_update_relay_18c0:
    movf        ram_0x04A, W, ACCESS
    movlb       0x0
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_18cc:
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
flow_fw_update_relay_18d0:
    infsnz      ram_0x084, F, BANKED
    incf        ram_0x085, F, BANKED
    incf        ram_0x049, F, ACCESS
    movlw       0x1F
    cpfsgt      ram_0x049, ACCESS
    bra         flow_fw_update_relay_15e4
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
; Notes   : Inferred i2c helper routine. Calls: i2c_secondary_dev_write, main_i2c_service_48e2, main_core_service_4516.
; ---------------------------------------------------------------------------
cmd_dispatch_gated:
    movff       WREG, ram_0x0FD
    btfss       active_flags, 3, ACCESS
    bra         cmd_gate_reject
    btfss       event_flags, 1, BANKED
    bra         flow_cmd_dispatch_gated_19a8
    bsf         event_flags, 3, BANKED
    bra         flow_cmd_dispatch_gated_1970
flow_cmd_dispatch_gated_18fe:
    movlw       0x09
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x70
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        main_i2c_service_48e2, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1918:
    movlw       0x0A
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0xB0
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        main_i2c_service_48e2, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1932:
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        main_i2c_service_48e2, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_194c:
    movlw       0x0B
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0xF0
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        main_i2c_service_48e2, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1966:
    call        main_core_service_4516, 0x0
    call        main_core_service_4954, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1970:
    movf        ram_0x093, W, BANKED
    bz          flow_cmd_dispatch_gated_1966
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_18fe
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_1918
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_1932
    xorlw       0x07
    bz          flow_cmd_dispatch_gated_194c
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_1966
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_1966
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_1966
flow_cmd_dispatch_gated_1990:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    movlb       0x0
    bcf         event_flags, 1, BANKED
    bsf         ram_0x0BD, 0, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_19a8:
    movlb       0x0
    btfss       event_flags, 3, BANKED
    bra         flow_cmd_dispatch_gated_1a76
    bcf         active_flags, 4, ACCESS
    bcf         event_flags, 5, BANKED
    bsf         event_flags, 6, BANKED
    clrf        ram_0x0A4, BANKED
    movff       ram_0x0A4, ram_0x0B0
    clrf        ram_0x09A, BANKED
    bra         flow_cmd_dispatch_gated_19d6
flow_cmd_dispatch_gated_19be:
    movff       ram_0x09B, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19c4:
    movff       ram_0x09C, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19ca:
    movff       ram_0x09D, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19d0:
    movff       ram_0x09E, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19d6:
    movf        ram_0x093, W, BANKED
    bz          flow_cmd_dispatch_gated_19be
    xorlw       0x05
    bz          flow_cmd_dispatch_gated_19c4
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_19ca
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_19d0
flow_cmd_dispatch_gated_19e6:
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
    call        main_core_service_3e0a, 0x0
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
    call        main_core_service_2abc, 0x0
    movff       ram_0x012, ram_0x0ED
    movff       ram_0x013, ram_0x0EE
    movff       ram_0x014, ram_0x0EF
    movff       ram_0x015, ram_0x0F0
    movff       ram_0x0ED, ram_0x02F
    movff       ram_0x0EE, ram_0x030
    movff       ram_0x0EF, ram_0x031
    movff       ram_0x0F0, ram_0x032
    call        main_core_service_297e, 0x0
    movff       ram_0x02F, i2c_coeff_0
    movff       ram_0x030, i2c_coeff_1
    movff       ram_0x031, i2c_coeff_2
    movff       ram_0x032, i2c_coeff_3
    call        volume_dsp_write, 0x0       ; V3.1 Fix B: verified volume write
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    movlb       0x0
    nop                                     ; V3.1: dirty bit managed by volume_dsp_write
    bsf         ram_0x0BD, 0, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1a76:
    btfss       active_flags, 7, ACCESS
    bra         flow_cmd_dispatch_gated_1a9c
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    call        main_core_service_4574, 0x0
    call        main_uart_service_495e, 0x0
    bcf         active_flags, 7, ACCESS
    movlb       0x0
    btfss       event_flags, 5, BANKED
    btfsc       active_flags, 4, ACCESS
    bra         flow_cmd_dispatch_gated_1a9c
    bsf         event_flags, 3, BANKED
flow_cmd_dispatch_gated_1a9c:
    movlb       0x0
    btfss       event_flags, 5, BANKED
    bra         flow_cmd_dispatch_gated_1aca
    btfss       active_flags, 4, ACCESS
    bra         flow_cmd_dispatch_gated_1ab6
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    bra         flow_cmd_dispatch_gated_1ab8
flow_cmd_dispatch_gated_1ab6:
    bsf         event_flags, 3, BANKED
flow_cmd_dispatch_gated_1ab8:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    movlb       0x0
    bcf         event_flags, 5, BANKED
flow_cmd_dispatch_gated_1aca:
    btfss       event_flags, 6, BANKED
    bra         flow_cmd_dispatch_gated_1baa
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
    call        main_i2c_service_381c, 0x0
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
    call        main_i2c_service_381c, 0x0
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
    call        main_i2c_service_381c, 0x0
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
    call        main_i2c_service_381c, 0x0
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
    call        main_i2c_service_381c, 0x0
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
    call        main_i2c_service_381c, 0x0
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    movlb       0x0
    bcf         event_flags, 6, BANKED
flow_cmd_dispatch_gated_1baa:
    btfss       event_flags, 4, BANKED
    bra         flow_cmd_dispatch_gated_1bc8
    call        main_i2c_service_2100, 0x0
    movlb       0x0
    bcf         event_flags, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    movlw       0x05
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1bc8:
    movlb       0x0
    btfss       ram_0x07F, 0, BANKED
    bra         flow_cmd_dispatch_gated_1bd6
    bcf         ram_0x07F, 0, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1bd6:
    movlb       0x0
    btfss       ram_0x07F, 1, BANKED
    bra         cmd_gate_reject
    bcf         ram_0x07F, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        main_timer_service_48a6, 0x0
cmd_gate_reject:
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_1be6
; Address : 0x1BE6
; Notes   : Inferred uart helper routine. Calls: rx_ring_has_data, rx_ring_read, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
main_uart_service_1be6:
    clrf        ram_0x009, ACCESS
    bra         flow_main_uart_service_1be6_1e78
flow_main_uart_service_1be6_1bea:
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    bnz         flow_main_uart_service_1be6_1bf4
    bra         flow_main_uart_service_1be6_1e7c
flow_main_uart_service_1be6_1bf4:
    call        rx_ring_read, 0x0
    movwf       ram_0x00A, ACCESS
    movlw       0x7F
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_uart_service_1be6_1c42
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB0
    bnz         flow_main_uart_service_1be6_1c0e
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
flow_main_uart_service_1be6_1c0e:
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB1
    bnz         flow_main_uart_service_1be6_1c1c
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bsf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
flow_main_uart_service_1be6_1c1c:
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
    bra         flow_main_uart_service_1be6_1e80
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c42:
    btfsc       active_flags, 0, ACCESS
    bra         flow_main_uart_service_1be6_1c52
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          flow_main_uart_service_1be6_1c52
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
flow_main_uart_service_1be6_1c52:
    movlb       0x0
    movf        rx_frame_position, W, BANKED
    btfss       STATUS, 2, ACCESS
    incf        rx_frame_position, F, BANKED
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          flow_main_uart_service_1be6_1c62
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c62:
    movf        rx_frame_position, W, BANKED
    xorlw       0x02
    bnz         flow_main_uart_service_1be6_1c6e
    movff       ram_0x00A, ram_0x0A2
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c6e:
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
    bra         flow_main_uart_service_1be6_1e6c
standby_request_handler:
    btfss       active_flags, 3, ACCESS
    bra         flow_main_uart_service_1be6_1ca2
    bsf         event_flags, 2, BANKED
    bra         flow_main_uart_service_1be6_1ca6
flow_main_uart_service_1be6_1ca2:
    movlb       0x0
    bcf         event_flags, 2, BANKED
flow_main_uart_service_1be6_1ca6:
    btfsc       event_flags, 2, BANKED
    bcf         active_flags, 3, ACCESS
    bra         flow_main_uart_service_1be6_1e6c
cmd03_mute_on_handler:
    btfsc       ram_0x094, 3, BANKED
    bra         flow_main_uart_service_1be6_1cd6
    bsf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cc2
    movlw       0x01
    bra         flow_main_uart_service_1be6_1cc4
flow_main_uart_service_1be6_1cc2:
    movlw       0x00
flow_main_uart_service_1be6_1cc4:
    xorwf       ram_0x005, F, ACCESS
    btfss       STATUS, 2, ACCESS
flow_main_uart_service_1be6_1cc8:
    bsf         event_flags, 5, BANKED
flow_main_uart_service_1be6_1cca:
    btfss       active_flags, 4, ACCESS
    bra         flow_main_uart_service_1be6_1cd2
    bsf         active_flags, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cd4
flow_main_uart_service_1be6_1cd2:
    bcf         active_flags, 5, ACCESS
flow_main_uart_service_1be6_1cd4:
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1cd6:
    movlw       0x02
    btfss       active_flags, 4, ACCESS
    movlw       0x03
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 3, BANKED
    bra         flow_main_uart_service_1be6_1e6c
cmd03_mute_off_handler:
    btfsc       ram_0x094, 3, BANKED
    bra         flow_main_uart_service_1be6_1cd6
    bcf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cc2
    movlw       0x01
    xorwf       ram_0x005, F, ACCESS
    bnz         flow_main_uart_service_1be6_1cc8
    bra         flow_main_uart_service_1be6_1cca
cmd03_subdispatch:
    movf        ram_0x0A3, W, BANKED
    bz          standby_request_handler
    xorlw       0x01
    bz          wake_request_handler
    xorlw       0x03
    bz          cmd03_mute_on_handler
    xorlw       0x01
    bz          cmd03_mute_off_handler
    bra         flow_main_uart_service_1be6_1e6c
cmd04_status_response:
    call        send_status_burst, 0x0
    bra         flow_main_uart_service_1be6_1e6c
cmd06_input_select_handler:
    btfsc       ram_0x094, 0, BANKED
    bra         flow_main_uart_service_1be6_1d22
    movff       ram_0x0A3, input_select
    movff       input_select, input_select_mirror
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d22:
    movff       input_select, ram_0x0BC
    bcf         ram_0x094, 0, BANKED
    bra         flow_main_uart_service_1be6_1e6c
volume_cmd_handler:
    btfsc       ram_0x094, 1, BANKED
    bra         flow_main_uart_service_1be6_1d80
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
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
flow_main_uart_service_1be6_1d68:
    bnz         flow_main_uart_service_1be6_1d6c
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d6c:
    bsf         event_flags, 3, BANKED
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d80:
    movf        computed_volume, W, BANKED
    addlw       0x60
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 1, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d8a:
    movf        ram_0x0A3, W, BANKED
    xorlw       0x29
    bnz         flow_main_uart_service_1be6_1e6c
    call        report_cmd29_status, 0x0
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d96:
    movff       ram_0x0A3, ram_0x060
    movf        ram_0x0A5, W, BANKED
    xorwf       ram_0x060, W, BANKED
    bz          flow_main_uart_service_1be6_1e6c
    bsf         event_flags, 4, BANKED
    movff       ram_0x060, ram_0x0A5
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1da8:
    movff       ram_0x0A3, ram_0x061
    movf        ram_0x061, W, BANKED
    xorwf       ram_0x0A6, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x061, ram_0x0A6
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dba:
    movff       ram_0x0A3, ram_0x062
    movf        ram_0x062, W, BANKED
    xorwf       ram_0x0A7, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x062, ram_0x0A7
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dcc:
    movff       ram_0x0A3, ram_0x063
    movf        ram_0x063, W, BANKED
    xorwf       ram_0x0A8, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x063, ram_0x0A8
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dde:
    movff       ram_0x0A3, ram_0x064
    movf        ram_0x064, W, BANKED
    xorwf       ram_0x0A9, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x064, ram_0x0A9
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1df0:
    movff       ram_0x0A3, ram_0x065
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x065, ram_0x0AA
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e02:
    btfsc       ram_0x094, 4, BANKED
    bra         flow_main_uart_service_1be6_1e14
    movf        ram_0x0B8, W, BANKED
    xorwf       ram_0x0A3, W, BANKED
    bz          flow_main_uart_service_1be6_1e6c
    movff       ram_0x0A3, ram_0x0B8
    bsf         ram_0x07F, 0, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e14:
    movff       ram_0x0B8, ram_0x0BC
    bcf         ram_0x094, 4, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e1c:
    movff       ram_0x0A3, ram_0x0C3
    movf        ram_0x0B2, W, BANKED
    xorwf       ram_0x0C3, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x0BD, 0, BANKED
    movff       ram_0x0C3, ram_0x0B2
    bra         flow_main_uart_service_1be6_1e6c
cmd_dispatch_xor_chain:
    movf        ram_0x0A2, W, BANKED
    xorlw       0x03
    bnz         flow_main_uart_service_1be6_1e36
    bra         cmd03_subdispatch
flow_main_uart_service_1be6_1e36:
    xorlw       0x07
    bnz         flow_main_uart_service_1be6_1e3c
    bra         cmd04_status_response
flow_main_uart_service_1be6_1e3c:
    xorlw       0x02
    bnz         flow_main_uart_service_1be6_1e42
    bra         cmd06_input_select_handler
flow_main_uart_service_1be6_1e42:
    xorlw       0x01
    bnz         flow_main_uart_service_1be6_1e48
    bra         volume_cmd_handler
flow_main_uart_service_1be6_1e48:
    xorlw       0x17
    bz          flow_main_uart_service_1be6_1d8a
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
    bz          flow_main_uart_service_1be6_1e02
    xorlw       0x03
    bz          flow_main_uart_service_1be6_1e1c
    xorlw       0x3E                            ; V3.1: cumulative 0x1E ^ 0x3E = 0x20
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x20
    goto        preset_select_handler
flow_main_uart_service_1be6_1e6c:
    btfss       active_flags, 6, ACCESS
    bra         flow_main_uart_service_1be6_1e80
    movlb       0x0
    movf        ram_0x0BC, W, BANKED
    call        uart_tx_byte_blocking, 0x0
flow_main_uart_service_1be6_1e78:
    bcf         active_flags, 6, ACCESS
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1e7c:
    movlw       0x01
    movwf       ram_0x009, ACCESS
flow_main_uart_service_1be6_1e80:
    movf        ram_0x009, W, ACCESS
    btfss       STATUS, 2, ACCESS
    return      0
    bra         flow_main_uart_service_1be6_1bea


; ---------------------------------------------------------------------------
; Function: main_core_service_1e88
; Address : 0x1E88
; Notes   : Inferred core helper routine. Calls: eeprom_read_byte, main_flash_service_46de.
; ---------------------------------------------------------------------------
main_core_service_1e88:
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
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x00
    subwf       computed_volume_2, W, BANKED
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x00
    subwf       computed_volume_1, W, BANKED
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x13
    subwf       computed_volume, W, BANKED
flow_main_core_service_1e88_1f54:
    bnc         flow_main_core_service_1e88_1f60
    movlw       0xA0
    movwf       computed_volume, BANKED
    setf        computed_volume_1, BANKED
    setf        computed_volume_2, BANKED
    setf        computed_volume_3, BANKED
flow_main_core_service_1e88_1f60:
    movlw       0x08
    cpfsgt      input_select, BANKED
    bra         flow_main_core_service_1e88_1f6a
    movlw       0x01
    movwf       input_select, BANKED
flow_main_core_service_1e88_1f6a:
    movlw       0x03
    cpfsgt      ram_0x060, BANKED
    bra         flow_main_core_service_1e88_1f72
    clrf        ram_0x060, BANKED
flow_main_core_service_1e88_1f72:
    lfsr        FSR2, 0x0061
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f7e
    clrf        ram_0x061, BANKED
flow_main_core_service_1e88_1f7e:
    lfsr        FSR2, 0x0062
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f8a
    clrf        ram_0x062, BANKED
flow_main_core_service_1e88_1f8a:
    lfsr        FSR2, 0x0063
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f98
    movlw       0x01
    movwf       ram_0x063, BANKED
flow_main_core_service_1e88_1f98:
    lfsr        FSR2, 0x0064
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1fa6
    movlw       0x01
    movwf       ram_0x064, BANKED
flow_main_core_service_1e88_1fa6:
    lfsr        FSR2, 0x0065
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1fb4
    movlw       0x01
    movwf       ram_0x064, BANKED
flow_main_core_service_1e88_1fb4:
    movlw       0x03
    cpfsgt      ram_0x05F, ACCESS
    bra         flow_main_core_service_1e88_1fbc
    movwf       ram_0x05F, ACCESS
flow_main_core_service_1e88_1fbc:
    movlw       0x04
    cpfsgt      ram_0x0C3, BANKED
    bra         flow_main_core_service_1e88_1fc6
    movlw       0x01
    movwf       ram_0x0C3, BANKED
flow_main_core_service_1e88_1fc6:
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
    bc          flow_main_core_service_1e88_2026
    movlw       0x03
    movwf       ram_0x0B8, BANKED
flow_main_core_service_1e88_2026:
    movlw       0x04
    cpfsgt      ram_0x0B8, BANKED
    bra         flow_main_core_service_1e88_2030
    movlw       0x03
    movwf       ram_0x0B8, BANKED
flow_main_core_service_1e88_2030:
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
    bra         flow_main_core_service_1e88_2070
    clrf        ram_0x09B, BANKED
flow_main_core_service_1e88_2070:
    movlw       0x12
    cpfsgt      ram_0x09C, BANKED
    bra         flow_main_core_service_1e88_2078
    clrf        ram_0x09C, BANKED
flow_main_core_service_1e88_2078:
    movlw       0x12
    cpfsgt      ram_0x09D, BANKED
    bra         flow_main_core_service_1e88_2080
    clrf        ram_0x09D, BANKED
flow_main_core_service_1e88_2080:
    movlw       0x12
    cpfsgt      ram_0x09E, BANKED
    bra         flow_main_core_service_1e88_2088
    clrf        ram_0x09E, BANKED
flow_main_core_service_1e88_2088:
    movff       ram_0x09B, ram_0x0AC
    movff       ram_0x09C, ram_0x0AD
    movff       ram_0x09D, ram_0x0AE
    movff       ram_0x09E, ram_0x0AF
    movlw       0x50
    movwf       ram_0x00A, ACCESS
flow_main_core_service_1e88_209c:
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
    bra         flow_main_core_service_1e88_209c
    movlw       0x60
    movwf       ram_0x00A, ACCESS
flow_main_core_service_1e88_20c2:
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
    bra         flow_main_core_service_1e88_20c2
    clrf        ram_0x008, ACCESS
    movlw       0x80
    movwf       ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x81
    movwf       ram_0x007, ACCESS
    movlw       0x03
    movwf       ram_0x009, ACCESS
    goto        main_flash_service_46de


; ---------------------------------------------------------------------------
; Function: main_i2c_service_2100
; Address : 0x2100
; Notes   : Inferred i2c helper; touches i2c. Calls: ram_block_clear, i2c_wait_bus_idle, main_core_service_4448.
; ---------------------------------------------------------------------------
main_i2c_service_2100:
    clrf        ram_0x004, ACCESS
    movlw       0xD7
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDB
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDF
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xD9
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xE3
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xDD
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xE1
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    call        i2c_wait_bus_idle, 0x0
    clrf        ram_0x059, ACCESS
flow_main_i2c_service_2100_217a:
    movf        ram_0x059, W, ACCESS
    movlb       0x0
    addlw       0x60
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        main_core_service_4448, 0x0
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
    bra         flow_main_i2c_service_2100_217a
    clrf        ram_0x05A, ACCESS
    bra         flow_main_i2c_service_2100_226a
flow_main_i2c_service_2100_21ec:
    movff       ram_0x0D7, ram_0x06A
    movff       ram_0x0D8, ram_0x06B
    movff       ram_0x0D9, ram_0x06C
    movff       ram_0x0DA, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_21fe:
    movff       ram_0x0DB, ram_0x06A
    movff       ram_0x0DC, ram_0x06B
    movff       ram_0x0DD, ram_0x06C
    movff       ram_0x0DE, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_2210:
    movff       ram_0x0DF, ram_0x06A
    movff       ram_0x0E0, ram_0x06B
    movff       ram_0x0E1, ram_0x06C
    movff       ram_0x0E2, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_2222:
    movff       ram_0x1D9, ram_0x06A
    movff       ram_0x1DA, ram_0x06B
    movff       ram_0x1DB, ram_0x06C
    movff       ram_0x1DC, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_2234:
    movff       ram_0x0E3, ram_0x06A
    movff       ram_0x0E4, ram_0x06B
    movff       ram_0x0E5, ram_0x06C
    movff       ram_0x0E6, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_2246:
    movff       ram_0x1DD, ram_0x06A
    movff       ram_0x1DE, ram_0x06B
    movff       ram_0x1DF, ram_0x06C
    movff       ram_0x1E0, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_2258:
    movff       ram_0x1E1, ram_0x06A
    movff       ram_0x1E2, ram_0x06B
    movff       ram_0x1E3, ram_0x06C
    movff       ram_0x1E4, ram_0x06D
    bra         flow_main_i2c_service_2100_2286
flow_main_i2c_service_2100_226a:
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
flow_main_i2c_service_2100_2286:
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
flow_main_i2c_service_2100_22a8:
    movf        ram_0x05B, W, ACCESS
    movlb       0x0
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    cpfseq      INDF2, ACCESS
    bra         flow_main_i2c_service_2100_22c2
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    movlw       0x3F
    bra         flow_main_i2c_service_2100_22da
flow_main_i2c_service_2100_22c2:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x03
    cpfseq      INDF2, ACCESS
    bra         flow_main_i2c_service_2100_22de
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    movlw       0x80
    movwf       i2c_coeff_2, ACCESS
    movlw       0xBF
flow_main_i2c_service_2100_22da:
    movwf       i2c_coeff_3, ACCESS
    bra         flow_main_i2c_service_2100_22fc
flow_main_i2c_service_2100_22de:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        main_core_service_45ce, 0x0
    movff       ram_0x00D, i2c_coeff_0
    movff       ram_0x00E, i2c_coeff_1
    movff       ram_0x00F, i2c_coeff_2
    movff       ram_0x010, i2c_coeff_3
flow_main_i2c_service_2100_22fc:
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    incf        ram_0x05B, F, ACCESS
    movlw       0x03
    cpfsgt      ram_0x05B, ACCESS
    bra         flow_main_i2c_service_2100_22a8
    bsf         SSPCON2, 2, ACCESS
flow_main_i2c_service_2100_231a:
    btfsc       SSPCON2, 2, ACCESS
    bra         flow_main_i2c_service_2100_231a
    incf        ram_0x05A, F, ACCESS
    movlw       0x06
    cpfsgt      ram_0x05A, ACCESS
    bra         flow_main_i2c_service_2100_226a
    retlw       0x06


; ---------------------------------------------------------------------------
; Function: main_core_service_2328
; Address : 0x2328
; Notes   : Inferred core helper routine. Calls: main_core_service_24ac.
; ---------------------------------------------------------------------------
main_core_service_2328:
    movff       ram_0x0C1, ram_0x15A
    bra         flow_main_core_service_2328_2472
flow_main_core_service_2328_232e:
    movff       ram_0x0C2, ram_0x15B
    movlw       0x02
    movwf       ram_0x003, ACCESS
flow_main_core_service_2328_2336:
    movlw       0xBE
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    rcall       main_core_service_24ac
    movlw       0x1F
    cpfsgt      ram_0x003, ACCESS
    bra         flow_main_core_service_2328_2336
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_234a:
    movff       ram_0x0C2, ram_0x15B
    decf        ram_0x0C2, W, BANKED
    bnz         flow_main_core_service_2328_235c
    movff       ram_0x0B7, ram_0x15C
    movff       ram_0x0B8, ram_0x15D
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_235c:
    movf        ram_0x0C2, W, BANKED
    xorlw       0x02
    bz          flow_main_core_service_2328_2364
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2364:
    movff       ram_0x0B5, ram_0x15E
    movlw       0x05
    movwf       ram_0x003, ACCESS
flow_main_core_service_2328_236c:
    movlw       0xFB
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    rcall       main_core_service_24ac
    movlw       0x13
    cpfsgt      ram_0x003, ACCESS
    bra         flow_main_core_service_2328_236c
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2380:
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
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_240c:
    movlw       0x03
    movlb       0x1
    movwf       ram_0x05B, BANKED
    movlw       0x03                        ; V3.1: major version = 3
    movwf       ram_0x05C, BANKED
    movlw       0x01                        ; V3.1: minor version = 1
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
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2460:
    movff       ram_0x11B, ram_0x15B
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2466:
    movlb       0x1
    clrf        ram_0x05B, BANKED
    clrf        ram_0x05C, BANKED
    clrf        ram_0x05D, BANKED
    clrf        active_flags, BANKED
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2472:
    movlb       0x0
    movf        ram_0x0C1, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_2328_247c
    bra         flow_main_core_service_2328_232e
flow_main_core_service_2328_247c:
    xorlw       0x07
    bnz         flow_main_core_service_2328_2482
    bra         flow_main_core_service_2328_234a
flow_main_core_service_2328_2482:
    xorlw       0x01
    bnz         flow_main_core_service_2328_2488
    bra         flow_main_core_service_2328_2380
flow_main_core_service_2328_2488:
    xorlw       0x03
    bz          flow_main_core_service_2328_240c
    xorlw       0x01
    bz          flow_main_core_service_2328_2460
    xorlw       0x0F
    bz          flow_main_core_service_2328_2460
    xorlw       0x01
    bz          flow_main_core_service_2328_2460
    xorlw       0x03
    bz          flow_main_core_service_2328_2460
    xorlw       0x01
    bz          flow_main_core_service_2328_2460
    xorlw       0x07
    bz          flow_main_core_service_2328_2460
    bra         flow_main_core_service_2328_2466
flow_main_core_service_2328_24a6:
    movlb       0x0
    clrf        ram_0x0C1, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_24ac
; Address : 0x24AC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_24ac:
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
; Function: main_core_service_24c2
; Address : 0x24C2
; Notes   : Inferred core helper routine. Calls: main_core_service_2650, main_core_service_263e, main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_24c2:
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
    bz          flow_main_core_service_24c2_2514
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    bc          flow_main_core_service_24c2_2526
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         flow_main_core_service_24c2_2526
flow_main_core_service_24c2_2514:
    movff       ram_0x024, ram_0x020
    movff       ram_0x025, ram_0x021
    movff       ram_0x026, ram_0x022
    movff       ram_0x027, ram_0x023
    bra         flow_main_core_service_24c2_263c
flow_main_core_service_24c2_2526:
    movf        ram_0x02D, W, ACCESS
    bz          flow_main_core_service_24c2_253c
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          flow_main_core_service_24c2_254e
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         flow_main_core_service_24c2_254e
flow_main_core_service_24c2_253c:
    movff       ram_0x020, ram_0x020
    movff       ram_0x021, ram_0x021
    movff       ram_0x022, ram_0x022
    movff       ram_0x023, ram_0x023
    bra         flow_main_core_service_24c2_263c
flow_main_core_service_24c2_254e:
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
    bc          flow_main_core_service_24c2_259c
flow_main_core_service_24c2_2568:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x024, F, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    decf        ram_0x02D, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          flow_main_core_service_24c2_2594
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          flow_main_core_service_24c2_2594
    bra         flow_main_core_service_24c2_2568
flow_main_core_service_24c2_2588:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x023, F, ACCESS
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    incf        ram_0x02E, F, ACCESS
flow_main_core_service_24c2_2594:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         flow_main_core_service_24c2_2588
    bra         flow_main_core_service_24c2_25d4
flow_main_core_service_24c2_259c:
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          flow_main_core_service_24c2_25d4
flow_main_core_service_24c2_25a2:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x020, F, ACCESS
    rlcf        ram_0x021, F, ACCESS
    rlcf        ram_0x022, F, ACCESS
    rlcf        ram_0x023, F, ACCESS
    decf        ram_0x02E, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          flow_main_core_service_24c2_25ce
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          flow_main_core_service_24c2_25ce
    bra         flow_main_core_service_24c2_25a2
flow_main_core_service_24c2_25c2:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    rrcf        ram_0x024, F, ACCESS
    incf        ram_0x02D, F, ACCESS
flow_main_core_service_24c2_25ce:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         flow_main_core_service_24c2_25c2
flow_main_core_service_24c2_25d4:
    btfss       ram_0x02C, 7, ACCESS
    bra         flow_main_core_service_24c2_25ea
    comf        ram_0x020, F, ACCESS
    comf        ram_0x021, F, ACCESS
    comf        ram_0x022, F, ACCESS
    comf        ram_0x023, F, ACCESS
    incf        ram_0x020, F, ACCESS
    movlw       0x00
    addwfc      ram_0x021, F, ACCESS
    addwfc      ram_0x022, F, ACCESS
    addwfc      ram_0x023, F, ACCESS
flow_main_core_service_24c2_25ea:
    btfss       ram_0x02C, 6, ACCESS
    bra         flow_main_core_service_24c2_25f2
    comf        ram_0x024, F, ACCESS
    rcall       main_core_service_263e
flow_main_core_service_24c2_25f2:
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
    bra         flow_main_core_service_24c2_2610
    comf        ram_0x024, F, ACCESS
    rcall       main_core_service_263e
    movlw       0x01
    movwf       ram_0x02C, ACCESS
flow_main_core_service_24c2_2610:
    movff       ram_0x024, ram_0x003
    movff       ram_0x025, ram_0x004
    movff       ram_0x026, ram_0x005
    movff       ram_0x027, ram_0x006
    movff       ram_0x02E, ram_0x007
    movff       ram_0x02C, ram_0x008
    call        main_core_service_30d8, 0x0
    movff       ram_0x003, ram_0x020
    movff       ram_0x004, ram_0x021
    movff       ram_0x005, ram_0x022
    movff       ram_0x006, ram_0x023
flow_main_core_service_24c2_263c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_263e
; Address : 0x263E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_263e:
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
; Function: main_core_service_265c
; Address : 0x265C
; Notes   : Inferred core helper routine. Calls: main_flash_service_46de.
; ---------------------------------------------------------------------------
main_core_service_265c:
    movlb       0x0
    btfss       event_flags, 0, BANKED
    bra         flow_main_core_service_265c_27ee
    btfss       ram_0x0BD, 0, BANKED
    bra         flow_main_core_service_265c_26cc
    clrf        ram_0x008, ACCESS
    movlw       0x03
    movwf       ram_0x007, ACCESS
    movff       computed_volume, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x02
    movwf       ram_0x007, ACCESS
    movff       computed_volume_1, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x01
    movwf       ram_0x007, ACCESS
    movff       computed_volume_2, ram_0x009
    call        main_flash_service_46de, 0x0
    movlw       0x00
    clrf        ram_0x008, ACCESS
    clrf        ram_0x007, ACCESS
    movff       computed_volume_3, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x04
    movwf       ram_0x007, ACCESS
    movff       input_select, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0D
    movwf       ram_0x007, ACCESS
    movff       ram_0x05F, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x14
    movwf       ram_0x007, ACCESS
    movff       ram_0x0C3, ram_0x009
    call        main_flash_service_46de, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 0, BANKED
flow_main_core_service_265c_26cc:
    btfss       ram_0x0BD, 1, BANKED
    bra         flow_main_core_service_265c_2728
    clrf        ram_0x008, ACCESS
    movlw       0x07
    movwf       ram_0x007, ACCESS
    movff       ram_0x060, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x08
    movwf       ram_0x007, ACCESS
    movff       ram_0x061, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x09
    movwf       ram_0x007, ACCESS
    movff       ram_0x062, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0A
    movwf       ram_0x007, ACCESS
    movff       ram_0x063, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0B
    movwf       ram_0x007, ACCESS
    movff       ram_0x064, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0C
    movwf       ram_0x007, ACCESS
    movff       ram_0x065, ram_0x009
    call        main_flash_service_46de, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 1, BANKED
flow_main_core_service_265c_2728:
    btfss       ram_0x0BD, 2, BANKED
    bra         flow_main_core_service_265c_274c
    clrf        ram_0x008, ACCESS
    movlw       0x0F
    movwf       ram_0x007, ACCESS
    movff       ram_0x0B4, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0E
    movwf       ram_0x007, ACCESS
    movff       ram_0x0B8, ram_0x009
    call        main_flash_service_46de, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 2, BANKED
flow_main_core_service_265c_274c:
    btfss       ram_0x0BD, 3, BANKED
    bra         flow_main_core_service_265c_278c
    clrf        ram_0x008, ACCESS
    movlw       0x10
    movwf       ram_0x007, ACCESS
    movff       ram_0x09B, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x11
    movwf       ram_0x007, ACCESS
    movff       ram_0x09C, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x12
    movwf       ram_0x007, ACCESS
    movff       ram_0x09D, ram_0x009
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x13
    movwf       ram_0x007, ACCESS
    movff       ram_0x09E, ram_0x009
    call        main_flash_service_46de, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 3, BANKED
flow_main_core_service_265c_278c:
    btfss       ram_0x0BD, 4, BANKED
    bra         flow_main_core_service_265c_27bc
    movlw       0x50
    movwf       ram_0x00A, ACCESS
flow_main_core_service_265c_2794:
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
    call        main_flash_service_46de, 0x0
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_core_service_265c_2794
    movlb       0x0
    bcf         ram_0x0BD, 4, BANKED
flow_main_core_service_265c_27bc:
    btfss       ram_0x0BD, 5, BANKED
    bra         flow_main_core_service_265c_27ec
    call        preset_persist_filename, 0x0
flow_main_core_service_265c_27ec:
    bcf         event_flags, 0, BANKED
flow_main_core_service_265c_27ee:
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_27f0
; Address : 0x27F0
; Notes   : Inferred i2c helper routine. Calls: i2c_secondary_dev_write, i2c_secondary_dev_random_read.
; ---------------------------------------------------------------------------
main_i2c_service_27f0:
    btfss       active_flags, 3, ACCESS
    bra         flow_main_i2c_service_27f0_297c
    movlw       0x64
    movlb       0x0
    cpfsgt      ram_0x0BB, BANKED
    bra         flow_main_i2c_service_27f0_297a
    clrf        ram_0x0BB, BANKED
    bra         flow_main_i2c_service_27f0_28aa
flow_main_i2c_service_27f0_2800:
    movf        ram_0x0B6, W, BANKED
    addlw       0x08
    movwf       ram_0x0BE, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_2808:
    clrf        ram_0x093, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_280c:
    movlw       0x01
    movwf       ram_0x093, BANKED
    movf        ram_0x05F, W, ACCESS
    bz          flow_main_i2c_service_27f0_28ce
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
    bra         flow_main_i2c_service_27f0_28ce
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
    bnz         flow_main_i2c_service_27f0_28ce
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
    bnz         flow_main_i2c_service_27f0_28ce
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
    bnz         flow_main_i2c_service_27f0_28ce
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
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x03
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_289e:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x04
flow_main_i2c_service_27f0_28a6:
    movwf       ram_0x093, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_28aa:
    movf        input_select, W, BANKED
    bz          flow_main_i2c_service_27f0_2800
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
flow_main_i2c_service_27f0_28ce:
    tstfsz      input_select, BANKED
    bra         flow_main_i2c_service_27f0_2902
    movff       ram_0x0BE, ram_0x006
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x13
    call        i2c_secondary_dev_random_read, 0x0
    movlb       0x0
    movwf       ram_0x0BE, BANKED
    tstfsz      ram_0x0BE, BANKED
    bra         flow_main_i2c_service_27f0_290a
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
    bnz         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_2902:
    clrf        ram_0x0B6, BANKED
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_2906:
    incf        ram_0x0BA, F, BANKED
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_290a:
    tstfsz      ram_0x0B6, BANKED
    bra         flow_main_i2c_service_27f0_2912
    movlw       0x03
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2912:
    decf        ram_0x0B6, W, BANKED
    bnz         flow_main_i2c_service_27f0_291a
    movlw       0x01
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_291a:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2924
    movlw       0x02
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2924:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_292e
    movlw       0x04
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_292e:
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
    bra         flow_main_i2c_service_27f0_295a
    bsf         active_flags, 5, ACCESS
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_295a:
    bcf         active_flags, 5, ACCESS
flow_main_i2c_service_27f0_295c:
    movlb       0x0
    movf        ram_0x093, W, BANKED
    xorlw       0x02
    btfsc       STATUS, 2, ACCESS
    btfsc       PORTC, 0, ACCESS
    bra         flow_main_i2c_service_27f0_296c
    movff       ram_0x0C3, ram_0x093
flow_main_i2c_service_27f0_296c:
    movf        ram_0x0AB, W, BANKED
    xorwf       ram_0x093, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 1, BANKED
    movff       ram_0x093, ram_0x0AB
    bra         flow_main_i2c_service_27f0_297c
flow_main_i2c_service_27f0_297a:
    incf        ram_0x0BB, F, BANKED
flow_main_i2c_service_27f0_297c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_297e
; Address : 0x297E
; Notes   : Inferred core helper routine. Calls: main_core_service_2ca8, main_core_service_24c2, main_core_service_3ec4.
; ---------------------------------------------------------------------------
main_core_service_297e:
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
    call        main_core_service_2ca8, 0x0
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
    call        main_core_service_24c2, 0x0
    movff       ram_0x020, ram_0x02F
    movff       ram_0x021, ram_0x030
    movff       ram_0x022, ram_0x031
    movff       ram_0x023, ram_0x032
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    movff       ram_0x02F, ram_0x02F
    movff       ram_0x030, ram_0x030
    movff       ram_0x031, ram_0x031
    movff       ram_0x032, ram_0x032
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2abc
; Address : 0x2ABC
; Notes   : Inferred core helper routine. Calls: main_core_service_2bac, main_core_service_2b8e, main_core_service_2b9e.
; ---------------------------------------------------------------------------
main_core_service_2abc:
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
    bra         flow_main_core_service_2abc_2ae0
    bra         flow_main_core_service_2abc_2b02
flow_main_core_service_2abc_2ae0:
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
    bra         flow_main_core_service_2abc_2b0c
flow_main_core_service_2abc_2b02:
    clrf        ram_0x012, ACCESS
    clrf        ram_0x013, ACCESS
    clrf        ram_0x014, ACCESS
    clrf        ram_0x015, ACCESS
    bra         flow_main_core_service_2abc_2b8c
flow_main_core_service_2abc_2b0c:
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
flow_main_core_service_2abc_2b30:
    btfss       ram_0x012, 0, ACCESS
    bra         flow_main_core_service_2abc_2b38
    movf        ram_0x016, W, ACCESS
    rcall       main_core_service_2b8e
flow_main_core_service_2abc_2b38:
    rcall       main_core_service_2b9e
    rlcf        ram_0x016, F, ACCESS
    rlcf        ram_0x017, F, ACCESS
    rlcf        ram_0x018, F, ACCESS
    rlcf        ram_0x019, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         flow_main_core_service_2abc_2b30
    movlw       0x11
    movwf       ram_0x023, ACCESS
flow_main_core_service_2abc_2b4a:
    btfss       ram_0x012, 0, ACCESS
    bra         flow_main_core_service_2abc_2b52
    movf        ram_0x016, W, ACCESS
    rcall       main_core_service_2b8e
flow_main_core_service_2abc_2b52:
    rcall       main_core_service_2b9e
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    rrcf        ram_0x01F, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         flow_main_core_service_2abc_2b4a
    movff       ram_0x01F, ram_0x003
    movff       ram_0x020, ram_0x004
    movff       ram_0x021, ram_0x005
    movff       ram_0x022, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x024, ram_0x008
    call        main_core_service_30d8, 0x0
    movff       ram_0x003, ram_0x012
    movff       ram_0x004, ram_0x013
    movff       ram_0x005, ram_0x014
    movff       ram_0x006, ram_0x015
flow_main_core_service_2abc_2b8c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2b8e
; Address : 0x2B8E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2b8e:
    addwf       ram_0x01F, F, ACCESS
    movf        ram_0x017, W, ACCESS
    addwfc      ram_0x020, F, ACCESS
    movf        ram_0x018, W, ACCESS
    addwfc      ram_0x021, F, ACCESS
    movf        ram_0x019, W, ACCESS
    addwfc      ram_0x022, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2b9e
; Address : 0x2B9E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2b9e:
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
; Function: main_flash_service_2bb8
; Address : 0x2BB8
; Notes   : Inferred flash helper routine. Calls: flash_read, flash_erase, flash_write.
; ---------------------------------------------------------------------------
main_flash_service_2bb8:
    tstfsz      ram_0x0C5, BANKED
    bra         flow_main_flash_service_2bb8_2bdc
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
flow_main_flash_service_2bb8_2bdc:
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
    bra         flow_main_flash_service_2bb8_2ca6
    clrf        ram_0x0C5, BANKED
    movlw       0x3F
    subwf       ram_0x082, W, BANKED
    movlw       0x5F
    subwfb      ram_0x083, W, BANKED
    bc          flow_main_flash_service_2bb8_2ca6
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
flow_main_flash_service_2bb8_2ca6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2ca8
; Address : 0x2CA8
; Notes   : Inferred core helper routine. Calls: main_core_service_2d80, main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_2ca8:
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
    bra         flow_main_core_service_2ca8_2ccc
    bra         flow_main_core_service_2ca8_2cee
flow_main_core_service_2ca8_2ccc:
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
    bra         flow_main_core_service_2ca8_2cf8
flow_main_core_service_2ca8_2cee:
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x010, ACCESS
    bra         flow_main_core_service_2ca8_2d7e
flow_main_core_service_2ca8_2cf8:
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
flow_main_core_service_2ca8_2d16:
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
    bnc         flow_main_core_service_2ca8_2d44
    movf        ram_0x011, W, ACCESS
    subwf       ram_0x00D, F, ACCESS
    movf        ram_0x012, W, ACCESS
    subwfb      ram_0x00E, F, ACCESS
    movf        ram_0x013, W, ACCESS
    subwfb      ram_0x00F, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwfb      ram_0x010, F, ACCESS
    bsf         ram_0x019, 0, ACCESS
flow_main_core_service_2ca8_2d44:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x00D, F, ACCESS
    rlcf        ram_0x00E, F, ACCESS
    rlcf        ram_0x00F, F, ACCESS
    rlcf        ram_0x010, F, ACCESS
    decfsz      ram_0x01D, F, ACCESS
    bra         flow_main_core_service_2ca8_2d16
    movff       ram_0x019, ram_0x003
    movff       ram_0x01A, ram_0x004
    movff       ram_0x01B, ram_0x005
    movff       ram_0x01C, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x01F, ram_0x008
    call        main_core_service_30d8, 0x0
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
; Function: adc_boot_gate
; Address : 0x2D8C
; Notes   : Inferred uart helper; touches adc,timer,uart. Calls: timer3_blocking_delay, main_i2c_service_4966, mssp_hard_reset.
; ---------------------------------------------------------------------------
adc_boot_gate:
    bcf         INTCON, 7, ACCESS
    bcf         LATB, 2, ACCESS
    movlb       0x0
    clrf        ram_0x088, BANKED
    clrf        ram_0x089, BANKED
    bsf         ADCON0, 1, ACCESS
adc_boot_gate_loop:
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    btfsc       ADCON0, 1, ACCESS
    bra         flow_adc_boot_gate_2dbc
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
flow_adc_boot_gate_2dbc:
    movlw       0x36
    movlb       0x0
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bnc         adc_boot_gate_loop
adc_boot_gate_exit:
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
    call        main_core_service_4574, 0x0
    bsf         LATB, 3, ACCESS
    call        main_core_service_4942, 0x0
    call        main_i2c_service_32f8, 0x0
    call        main_core_service_4942, 0x0
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
    goto        flow_main_usb_service_490c_4918

; ---------------------------------------------------------------------------
; Function: flash_write (V3.1: preset B address remap prologue)
; Notes   : Remaps 0x56xx-0x5Fxx to 0x4Axx-0x53xx when preset B active.
; ---------------------------------------------------------------------------
flash_write:
    btfss       active_flags, 2, ACCESS     ; preset B active?
    bra         flash_write_stock
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         flash_write_stock
    movlw       0x56
    subwf       ram_0x004, W, ACCESS
    bnc         flash_write_stock
    movlw       0x60
    subwf       ram_0x004, W, ACCESS
    bc          flash_write_stock
    movlw       0x0A
    subwf       ram_0x004, F, ACCESS
flash_write_stock:
    clrf        ram_0x010, ACCESS
    movff       ram_0x003, ram_0x014
    movff       ram_0x004, ram_0x015
    movff       ram_0x005, ram_0x016
    movff       ram_0x006, ram_0x017
    movlw       0x05
    movwf       ram_0x00B, ACCESS
flow_flash_write_2e84:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    decfsz      ram_0x00B, F, ACCESS
    bra         flow_flash_write_2e84
    movlw       0x05
flow_flash_write_2e94:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    decfsz      WREG, F, ACCESS
    bra         flow_flash_write_2e94
    movlw       0x20
    addwf       ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movwf       ram_0x00F, ACCESS
    bra         flow_flash_write_2f44
flow_flash_write_2eb6:
    movff       ram_0x016, ram_0x013
    movff       ram_0x015, ram_0x012
    movff       ram_0x014, ram_0x011
    bra         flow_flash_write_2ef6
flow_flash_write_2ec4:
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
    bz          flow_flash_write_2efc
flow_flash_write_2ef6:
    decf        ram_0x00F, F, ACCESS
    incf        ram_0x00F, W, ACCESS
    bnz         flow_flash_write_2ec4
flow_flash_write_2efc:
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
    bra         flow_flash_write_2f24
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x010, ACCESS
flow_flash_write_2f24:
    call        main_flash_service_4406, 0x0
    bcf         EECON1, 2, ACCESS
    movf        ram_0x010, W, ACCESS
    bz          flow_flash_write_2f32
    bsf         INTCON, 7, ACCESS
    clrf        ram_0x010, ACCESS
flow_flash_write_2f32:
    movlw       0x20
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00C, W, ACCESS
    movwf       ram_0x014, ACCESS
    movf        ram_0x00D, W, ACCESS
    movwf       ram_0x015, ACCESS
    movf        ram_0x00E, W, ACCESS
    movwf       ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
flow_flash_write_2f44:
    movf        ram_0x008, W, ACCESS
    iorwf       ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_flash_write_2eb6


; ---------------------------------------------------------------------------
; Function: main_usb_service_2f4e
; Address : 0x2F4E
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_475c, main_usb_service_483c, main_usb_service_40d6.
; ---------------------------------------------------------------------------
main_usb_service_2f4e:
    call        main_usb_service_475c, 0x0
    tstfsz      ram_0x0CD, BANKED
    bra         flow_main_usb_service_2f4e_2f58
    bra         flow_main_usb_service_2f4e_3018
flow_main_usb_service_2f4e_2f58:
    btfsc       UIR, 2, ACCESS
    call        main_usb_service_483c, 0x0
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_2f4e_3018
    btfsc       UIR, 0, ACCESS
    call        main_usb_service_40d6, 0x0
    btfsc       UIR, 4, ACCESS
    call        main_usb_service_4720, 0x0
    movlw       0x03
    movlb       0x0
    subwf       ram_0x0CD, W, BANKED
    bnc         flow_main_usb_service_2f4e_3018
    clrf        ram_0x0C4, BANKED
flow_main_usb_service_2f4e_2f78:
    btfss       UIR, 3, ACCESS
    bra         flow_main_usb_service_2f4e_3018
    movf        USTAT, W, ACCESS
    movff       USTAT, ram_0x006
    movlw       0x7C
    andwf       ram_0x006, F, ACCESS
    bnz         flow_main_usb_service_2f4e_2ffe
    btfsc       USTAT, 1, ACCESS
    bra         flow_main_usb_service_2f4e_2f96
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
    movlw       0x00
    bra         flow_main_usb_service_2f4e_2f9c
flow_main_usb_service_2f4e_2f96:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
flow_main_usb_service_2f4e_2f9c:
    movlb       0x0
    movwf       ram_0x07A, BANKED
    bcf         UIR, 3, ACCESS
    movff       ram_0x07A, FSR2L
    movff       ram_0x07B, FSR2H
    rrcf        INDF2, W, ACCESS
    rrcf        WREG, F, ACCESS
    andlw       0x0F
    xorlw       0x0D
    bnz         flow_main_usb_service_2f4e_300e
    clrf        ram_0x090, BANKED
flow_main_usb_service_2f4e_2fb6:
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
    bra         flow_main_usb_service_2f4e_2fb6
    call        main_usb_service_42f4, 0x0
    bra         flow_main_usb_service_2f4e_300e
flow_main_usb_service_2f4e_2ffe:
    movf        USTAT, W, ACCESS
    xorlw       0x04
    bnz         flow_main_usb_service_2f4e_300c
    bcf         UIR, 3, ACCESS
    call        main_usb_service_4412, 0x0
    bra         flow_main_usb_service_2f4e_300e
flow_main_usb_service_2f4e_300c:
    bcf         UIR, 3, ACCESS
flow_main_usb_service_2f4e_300e:
    movlb       0x0
    incf        ram_0x0C4, F, BANKED
    movlw       0x03
    cpfsgt      ram_0x0C4, BANKED
    bra         flow_main_usb_service_2f4e_2f78
flow_main_usb_service_2f4e_3018:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_301a
; Address : 0x301A
; Notes   : Inferred core helper routine. Calls: main_core_service_30cc.
; ---------------------------------------------------------------------------
main_core_service_301a:
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
    bra         flow_main_core_service_301a_3046
flow_main_core_service_301a_303c:
    clrf        ram_0x025, ACCESS
    clrf        ram_0x026, ACCESS
    clrf        ram_0x027, ACCESS
    clrf        ram_0x028, ACCESS
    bra         flow_main_core_service_301a_30ca
flow_main_core_service_301a_3046:
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
    bra         flow_main_core_service_301a_308e
    movf        ram_0x02E, W, ACCESS
    xorlw       0x80
    movwf       ram_0x029, ACCESS
    movlw       0xE9
    xorlw       0x80
    subwf       ram_0x029, W, ACCESS
    bnc         flow_main_core_service_301a_303c
flow_main_core_service_301a_307e:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x028, F, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    incfsz      ram_0x02E, F, ACCESS
    bra         flow_main_core_service_301a_307e
    bra         flow_main_core_service_301a_30a6
flow_main_core_service_301a_308e:
    movlw       0x1F
    cpfsgt      ram_0x02E, ACCESS
    bra         flow_main_core_service_301a_30a2
    bra         flow_main_core_service_301a_303c
flow_main_core_service_301a_3096:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    rlcf        ram_0x028, F, ACCESS
    decf        ram_0x02E, F, ACCESS
flow_main_core_service_301a_30a2:
    tstfsz      ram_0x02E, ACCESS
    bra         flow_main_core_service_301a_3096
flow_main_core_service_301a_30a6:
    movf        ram_0x02D, W, ACCESS
    bz          flow_main_core_service_301a_30ba
    comf        ram_0x028, F, ACCESS
    comf        ram_0x027, F, ACCESS
    comf        ram_0x026, F, ACCESS
    negf        ram_0x025, ACCESS
    movlw       0x00
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    addwfc      ram_0x028, F, ACCESS
flow_main_core_service_301a_30ba:
    movff       ram_0x025, ram_0x025
    movff       ram_0x026, ram_0x026
    movff       ram_0x027, ram_0x027
    movff       ram_0x028, ram_0x028
flow_main_core_service_301a_30ca:
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
; Function: main_core_service_30d8
; Address : 0x30D8
; Notes   : Inferred core helper routine. Calls: main_core_service_3188.
; ---------------------------------------------------------------------------
main_core_service_30d8:
    movf        ram_0x007, W, ACCESS
    bz          flow_main_core_service_30d8_30e6
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    iorwf       ram_0x004, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         flow_main_core_service_30d8_30f4
flow_main_core_service_30d8_30e6:
    clrf        ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    bra         flow_main_core_service_30d8_3186
flow_main_core_service_30d8_30f0:
    incf        ram_0x007, F, ACCESS
    rcall       main_core_service_3188
flow_main_core_service_30d8_30f4:
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
    bz          flow_main_core_service_30d8_311a
    bra         flow_main_core_service_30d8_30f0
flow_main_core_service_30d8_310c:
    incf        ram_0x007, F, ACCESS
    incf        ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    rcall       main_core_service_3188
flow_main_core_service_30d8_311a:
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    movf        ram_0x006, W, ACCESS
    movwf       ram_0x00C, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    iorwf       ram_0x00B, W, ACCESS
    bz          flow_main_core_service_30d8_313c
    bra         flow_main_core_service_30d8_310c
flow_main_core_service_30d8_3130:
    decf        ram_0x007, F, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
flow_main_core_service_30d8_313c:
    btfss       ram_0x005, 7, ACCESS
    bra         flow_main_core_service_30d8_3130
    btfsc       ram_0x007, 0, ACCESS
    bra         flow_main_core_service_30d8_3148
    movlw       0x7F
    andwf       ram_0x005, F, ACCESS
flow_main_core_service_30d8_3148:
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
flow_main_core_service_30d8_3186:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3188
; Address : 0x3188
; Notes   : Inferred core helper routine. Calls: main_core_service_496c, main_core_service_4080.
; ---------------------------------------------------------------------------
main_core_service_3188:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    return      0
flow_main_core_service_3188_3194:
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         flow_main_core_service_3188_324a
    movf        ram_0x0D3, W, BANKED
    bnz         flow_main_core_service_3188_324a
    movf        ram_0x0D0, W, BANKED
    xorlw       0x06
    bz          flow_main_core_service_3188_31d8
    bra         flow_main_core_service_3188_31e6
flow_main_core_service_3188_31aa:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x3E
    movwf       ram_0x075, BANKED
    clrf        ram_0x0E8, BANKED
    movlw       0x09
    bra         flow_main_core_service_3188_31d4
flow_main_core_service_3188_31bc:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    decf        ram_0x0EB, W, BANKED
    bnz         flow_main_core_service_3188_31cc
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x55
    movwf       ram_0x075, BANKED
flow_main_core_service_3188_31cc:
    decf        ram_0x0EB, W, BANKED
    bnz         flow_main_core_service_3188_31e4
    clrf        ram_0x0E8, BANKED
    movlw       0x1D
flow_main_core_service_3188_31d4:
    movwf       ram_0x0E7, BANKED
    bra         flow_main_core_service_3188_31e4
flow_main_core_service_3188_31d8:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x21
    bz          flow_main_core_service_3188_31aa
    xorlw       0x03
    bz          flow_main_core_service_3188_31bc
    xorlw       0x01
flow_main_core_service_3188_31e4:
    bsf         ram_0x0CE, 1, BANKED
flow_main_core_service_3188_31e6:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         flow_main_core_service_3188_324a
    bra         flow_main_core_service_3188_3230
flow_main_core_service_3188_31f4:
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_31fa:
    call        main_core_service_496c, 0x0
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3200:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEA
flow_main_core_service_3188_3208:
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3212:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D2, ram_0x0EA
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_321c:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xE9
    bra         flow_main_core_service_3188_3208
flow_main_core_service_3188_3226:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D1, ram_0x0E9
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3230:
    movf        ram_0x0D0, W, BANKED
    xorlw       0x01
    bz          flow_main_core_service_3188_31f4
    xorlw       0x03
    bz          flow_main_core_service_3188_3200
    xorlw       0x01
    bz          flow_main_core_service_3188_321c
    xorlw       0x0A
    bz          flow_main_core_service_3188_31fa
    xorlw       0x03
    bz          flow_main_core_service_3188_3212
    xorlw       0x01
    bz          flow_main_core_service_3188_3226
flow_main_core_service_3188_324a:
    return      0
flow_main_core_service_3188_324c:
    tstfsz      ram_0x0C8, BANKED
    bra         flow_main_core_service_3188_3278
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
    call        main_core_service_4080, 0x0
    clrf        ram_0x096, BANKED
    bra         flow_main_core_service_3188_32f6
flow_main_core_service_3188_326c:
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    bra         flow_main_core_service_3188_32f6
flow_main_core_service_3188_3278:
    btfss       ram_0x0CF, 7, BANKED
    bra         flow_main_core_service_3188_32b4
    movlw       0x01
    movwf       ram_0x0C9, BANKED
    movf        ram_0x0E7, W, BANKED
    subwf       ram_0x0D5, W, BANKED
    movf        ram_0x0E8, W, BANKED
    subwfb      ram_0x0D6, W, BANKED
    bc          flow_main_core_service_3188_3292
    movff       ram_0x0D5, ram_0x0E7
    movff       ram_0x0D6, ram_0x0E8
flow_main_core_service_3188_3292:
    call        main_flash_service_35f0, 0x0
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x01
    call        main_core_service_4080, 0x0
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlb       0x4
    movlw       0x04
    movwf       ram_0x00B, BANKED
    movlw       0x24
    movwf       ram_0x00A, BANKED
    bra         flow_main_core_service_3188_32f0
flow_main_core_service_3188_32b4:
    movlw       0x02
    movwf       ram_0x0C9, BANKED
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         flow_main_core_service_3188_32cc
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
flow_main_core_service_3188_32cc:
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         flow_main_core_service_3188_32dc
    movlw       0x01
    call        main_core_service_4080, 0x0
    clrf        ram_0x096, BANKED
    bra         flow_main_core_service_3188_32e6
flow_main_core_service_3188_32dc:
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
flow_main_core_service_3188_32e6:
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         flow_main_core_service_3188_32f6
    movlb       0x4
    clrf        ram_0x009, BANKED
flow_main_core_service_3188_32f0:
    movlw       0x48
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
flow_main_core_service_3188_32f6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_32f8
; Address : 0x32F8
; Notes   : Inferred i2c helper routine. Calls: i2c_wait_bus_idle, i2c_secondary_dev_write.
; ---------------------------------------------------------------------------
main_i2c_service_32f8:
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
; Function: main_core_service_3398
; Address : 0x3398
; Notes   : Inferred core helper routine. Calls: main_flash_service_3ce8, main_core_service_301a, main_core_service_3e0a.
; ---------------------------------------------------------------------------
main_core_service_3398:
    movff       ram_0x02F, ram_0x003
    movff       ram_0x030, ram_0x004
    movff       ram_0x031, ram_0x005
    movff       ram_0x032, ram_0x006
    movlw       0x37
    movwf       ram_0x007, ACCESS
    call        main_flash_service_3ce8, 0x0
    movf        ram_0x038, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       ram_0x037, W, ACCESS
    bc          flow_main_core_service_3398_33cc
    clrf        ram_0x02F, ACCESS
    clrf        ram_0x030, ACCESS
    clrf        ram_0x031, ACCESS
    clrf        ram_0x032, ACCESS
    bra         flow_main_core_service_3398_3430
flow_main_core_service_3398_33cc:
    movlw       0x1D
    subwf       ram_0x037, W, ACCESS
    movlw       0x00
    subwfb      ram_0x038, W, ACCESS
    bnc         flow_main_core_service_3398_33e8
    movff       ram_0x02F, ram_0x02F
    movff       ram_0x030, ram_0x030
    movff       ram_0x031, ram_0x031
    movff       ram_0x032, ram_0x032
    bra         flow_main_core_service_3398_3430
flow_main_core_service_3398_33e8:
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    call        main_core_service_301a, 0x0
    movff       ram_0x025, ram_0x00D
    movff       ram_0x026, ram_0x00E
    movff       ram_0x027, ram_0x00F
    movff       ram_0x028, ram_0x010
    call        main_core_service_3e0a, 0x0
    movff       ram_0x00D, ram_0x033
    movff       ram_0x00E, ram_0x034
    movff       ram_0x00F, ram_0x035
    movff       ram_0x010, ram_0x036
    movff       ram_0x033, ram_0x02F
    movff       ram_0x034, ram_0x030
    movff       ram_0x035, ram_0x031
    movff       ram_0x036, ram_0x032
flow_main_core_service_3398_3430:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3432
; Address : 0x3432
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3432:
    decf        ram_0x0D1, W, BANKED
    bnz         flow_main_core_service_3432_344c
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bnz         flow_main_core_service_3432_344c
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D0, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_3432_344a
    bsf         ram_0x0CE, 0, BANKED
    bra         flow_main_core_service_3432_344c
flow_main_core_service_3432_344a:
    bcf         ram_0x0CE, 0, BANKED
flow_main_core_service_3432_344c:
    tstfsz      ram_0x0D1, BANKED
    bra         flow_main_core_service_3432_34c6
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    xorlw       0x02
    bnz         flow_main_core_service_3432_34c6
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    bz          flow_main_core_service_3432_34c6
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
    bnz         flow_main_core_service_3432_349c
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x04
    bra         flow_main_core_service_3432_34b8
flow_main_core_service_3432_349c:
    btfss       ram_0x0D3, 7, BANKED
    bra         flow_main_core_service_3432_34ae
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x40
    movwf       INDF2, ACCESS
    bra         flow_main_core_service_3432_34c6
flow_main_core_service_3432_34ae:
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x08
flow_main_core_service_3432_34b8:
    movwf       INDF2, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x00
    bsf         PLUSW2, 7, ACCESS
flow_main_core_service_3432_34c6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_34c8
; Address : 0x34C8
; Notes   : Inferred core helper routine. Calls: main_adc_service_4124, main_core_service_427a.
; ---------------------------------------------------------------------------
main_core_service_34c8:
    movff       WREG, ram_0x011
    movff       ram_0x00A, ram_0x00E
    movff       ram_0x00B, ram_0x00F
flow_main_core_service_34c8_34d4:
    movff       ram_0x00E, ram_0x003
    movff       ram_0x00F, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        main_adc_service_4124, 0x0
    movff       ram_0x003, ram_0x00E
    movff       ram_0x004, ram_0x00F
    incf        ram_0x011, F, ACCESS
    movf        ram_0x00F, W, ACCESS
    iorwf       ram_0x00E, W, ACCESS
    bnz         flow_main_core_service_34c8_34d4
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    clrf        INDF2, ACCESS
    decf        ram_0x011, F, ACCESS
flow_main_core_service_34c8_3504:
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        main_core_service_427a, 0x0
    movf        ram_0x003, W, ACCESS
    movwf       ram_0x010, ACCESS
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        main_adc_service_4124, 0x0
    movff       ram_0x003, ram_0x00A
    movff       ram_0x004, ram_0x00B
    movlw       0x09
    cpfsgt      ram_0x010, ACCESS
    bra         flow_main_core_service_34c8_3542
    movlw       0x07
    addwf       ram_0x010, F, ACCESS
flow_main_core_service_34c8_3542:
    movlw       0x30
    addwf       ram_0x010, F, ACCESS
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x010, INDF2
    decf        ram_0x011, F, ACCESS
    movf        ram_0x00B, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    bnz         flow_main_core_service_34c8_3504
    incf        ram_0x011, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_355c
; Address : 0x355C
; Notes   : Inferred i2c helper; touches adc,i2c,timer. Calls: eeprom_read_byte, flash_write_with_gie_off, main_flash_service_46de.
; ---------------------------------------------------------------------------
main_i2c_service_355c:
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
    bz          flow_main_i2c_service_355c_35bc
    clrf        ram_0x004, ACCESS
    movlw       0xFF
    setf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x88
    bz          flow_main_i2c_service_355c_35bc
    movlb       0x0
    clrf        ram_0x0FE, BANKED
flow_main_i2c_service_355c_35bc:
    movlb       0x0
    movf        ram_0x0FE, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        flash_write_with_gie_off, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    bsf         PORTB, 6, ACCESS
    call        adaptive_baud_select, 0x0
    movlw       0x03
    movwf       ram_0x004, ACCESS
    movlw       0xE8
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    call        main_core_service_1e88, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         active_flags, 3, ACCESS
    movlb       0x0
    bsf         event_flags, 7, BANKED      ; V3.1: boot complete — enable bounded PEN waits
    goto        adc_boot_gate


; ---------------------------------------------------------------------------
; Function: main_flash_service_35f0
; Address : 0x35F0
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_365c, main_flash_service_3810, main_core_service_3672.
; ---------------------------------------------------------------------------
main_flash_service_35f0:
    movlw       0x08
    movwf       ram_0x08F, BANKED
    subwf       ram_0x0E7, W, BANKED
    movlw       0x00
    subwfb      ram_0x0E8, W, BANKED
    bc          flow_main_flash_service_35f0_3610
    movff       ram_0x0E7, ram_0x08F
    tstfsz      ram_0x0CC, BANKED
    bra         flow_main_flash_service_35f0_3608
    movlw       0x01
    bra         flow_main_flash_service_35f0_360e
flow_main_flash_service_35f0_3608:
    decf        ram_0x0CC, W, BANKED
    bnz         flow_main_flash_service_35f0_3610
    movlw       0x02
flow_main_flash_service_35f0_360e:
    movwf       ram_0x0CC, BANKED
flow_main_flash_service_35f0_3610:
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
    bra         flow_main_flash_service_35f0_363e
    bra         flow_main_flash_service_35f0_3656
flow_main_flash_service_35f0_362c:
    rcall       main_flash_service_365c
    cpfsgt      TBLPTRH, ACCESS
    bra         flow_main_flash_service_35f0_3638
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         flow_main_flash_service_35f0_363c
flow_main_flash_service_35f0_3638:
    call        main_flash_service_3810, 0x0
flow_main_flash_service_35f0_363c:
    rcall       main_core_service_3672
flow_main_flash_service_35f0_363e:
    tstfsz      ram_0x08F, BANKED
    bra         flow_main_flash_service_35f0_362c
    bra         flow_main_flash_service_35f0_365a
flow_main_flash_service_35f0_3644:
    rcall       main_flash_service_365c
    cpfsgt      TBLPTRH, ACCESS
    bra         flow_main_flash_service_35f0_3650
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         flow_main_flash_service_35f0_3654
flow_main_flash_service_35f0_3650:
    call        main_flash_service_3810, 0x0
flow_main_flash_service_35f0_3654:
    rcall       main_core_service_3672
flow_main_flash_service_35f0_3656:
    tstfsz      ram_0x08F, BANKED
    bra         flow_main_flash_service_35f0_3644
flow_main_flash_service_35f0_365a:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_365c
; Address : 0x365C
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_365c:
    movff       ram_0x075, TBLPTRL
    movff       ram_0x076, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x07
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3672
; Address : 0x3672
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3672:
    movwf       INDF2, ACCESS
    movlb       0x0
    infsnz      ram_0x072, F, BANKED
    incf        ram_0x073, F, BANKED
    infsnz      ram_0x075, F, BANKED
    incf        ram_0x076, F, BANKED
    decf        ram_0x08F, F, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3682
; Address : 0x3682
; Notes   : Inferred core helper routine. Calls: main_flash_service_3796, main_usb_service_41fe, main_core_service_3710.
; ---------------------------------------------------------------------------
main_core_service_3682:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    bnz         flow_main_core_service_3682_370e
    bra         flow_main_core_service_3682_36e4
flow_main_core_service_3682_368c:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x04
    movwf       ram_0x0CD, BANKED
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_3696:
    call        main_flash_service_3796, 0x0
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_369c:
    call        main_usb_service_41fe, 0x0
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36a2:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEB
    movwf       ram_0x075, BANKED
flow_main_core_service_3682_36ac:
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36b4:
    call        main_core_service_3710, 0x0
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36ba:
    call        main_core_service_3432, 0x0
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36c0:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       ram_0x005, ACCESS
    clrf        ram_0x076, BANKED
    movff       ram_0x005, ram_0x075
    bra         flow_main_core_service_3682_36ac
flow_main_core_service_3682_36d2:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x0D1, INDF2
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36e4:
    movf        ram_0x0D0, W, BANKED
    bz          flow_main_core_service_3682_36b4
    xorlw       0x01
    bz          flow_main_core_service_3682_36ba
    xorlw       0x02
    bz          flow_main_core_service_3682_36ba
    xorlw       0x06
    bz          flow_main_core_service_3682_368c
    xorlw       0x03
    bz          flow_main_core_service_3682_3696
    xorlw       0x01
    bz          flow_main_core_service_3682_370e
    xorlw       0x0F
    bz          flow_main_core_service_3682_36a2
    xorlw       0x01
    bz          flow_main_core_service_3682_369c
    xorlw       0x03
    bz          flow_main_core_service_3682_36c0
    xorlw       0x01
    bz          flow_main_core_service_3682_36d2
    xorlw       0x07
flow_main_core_service_3682_370e:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3710
; Address : 0x3710
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3710:
    movlb       0x4
    clrf        ram_0x024, BANKED
    clrf        ram_0x025, BANKED
    bra         flow_main_core_service_3710_3770
flow_main_core_service_3710_3718:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    btfss       ram_0x0CE, 0, BANKED
    bra         flow_main_core_service_3710_3780
    movlb       0x4
    bsf         ram_0x024, 1, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_3726:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_372c:
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
    bra         flow_main_core_service_3710_3780
    movlw       0x01
    movlb       0x4
    movwf       ram_0x024, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_3770:
    movlb       0x0
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bz          flow_main_core_service_3710_3718
    xorlw       0x01
    bz          flow_main_core_service_3710_3726
    xorlw       0x03
    bz          flow_main_core_service_3710_372c
flow_main_core_service_3710_3780:
    movlb       0x0
    decf        ram_0x0C8, W, BANKED
    bnz         flow_main_core_service_3710_3794
    movlw       0x04
    movwf       ram_0x076, BANKED
    movlw       0x24
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x02
    movwf       ram_0x0E7, BANKED
flow_main_core_service_3710_3794:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_3796
; Address : 0x3796
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_3810.
; ---------------------------------------------------------------------------
main_flash_service_3796:
    movf        ram_0x0CF, W, BANKED
    xorlw       0x80
    bz          flow_main_flash_service_3796_37fe
    bra         flow_main_flash_service_3796_380e
flow_main_flash_service_3796_379e:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x88
    movwf       ram_0x075, BANKED
    movlw       0x12
    bra         flow_main_flash_service_3796_37c4
flow_main_flash_service_3796_37ae:
    tstfsz      ram_0x0D1, BANKED
    bra         flow_main_flash_service_3796_380c
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x2C
    movwf       ram_0x075, BANKED
    movlw       0x00
    movwf       ram_0x0E8, BANKED
    movlw       0x29
flow_main_flash_service_3796_37c4:
    movwf       ram_0x0E7, BANKED
    bra         flow_main_flash_service_3796_380c
flow_main_flash_service_3796_37c8:
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
    bra         flow_main_flash_service_3796_37f4
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         flow_main_flash_service_3796_37f6
flow_main_flash_service_3796_37f4:
    rcall       main_flash_service_3810
flow_main_flash_service_3796_37f6:
    movlb       0x0
    movwf       ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bra         flow_main_flash_service_3796_380c
flow_main_flash_service_3796_37fe:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x01
    bz          flow_main_flash_service_3796_379e
    xorlw       0x03
    bz          flow_main_flash_service_3796_37ae
    xorlw       0x01
    bz          flow_main_flash_service_3796_37c8
flow_main_flash_service_3796_380c:
    bsf         ram_0x0CE, 1, BANKED
flow_main_flash_service_3796_380e:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_3810
; Address : 0x3810
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_3810:
    movff       TBLPTRL, FSR1L
    movff       TBLPTRH, FSR1H
    movf        INDF1, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_381c
; Address : 0x381C
; Notes   : Inferred i2c helper; touches i2c. Calls: flash_read, i2c_byte_tx.
; ---------------------------------------------------------------------------
main_i2c_service_381c:
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
    bc          flow_main_i2c_service_381c_38a0
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
flow_main_i2c_service_381c_38a0:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_38a2
; Address : 0x38A2
; Notes   : Inferred core helper routine. Calls: main_core_service_3398, main_core_service_432e, main_core_service_3f1e.
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
    call        main_core_service_3398, 0x0
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
    call        main_core_service_3f1e, 0x0
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    call        main_core_service_3398, 0x0
    movff       ram_0x02F, ram_0x041
    movff       ram_0x030, ram_0x042
    movff       ram_0x031, ram_0x043
    movff       ram_0x032, ram_0x044
    return      0

; ---------------------------------------------------------------------------
; Function: adaptive_baud_select
; Address : 0x3926
; Notes   : Inferred uart helper; touches adc,timer,uart. Calls: main_uart_service_4938.
; ---------------------------------------------------------------------------
adaptive_baud_select:
    btfss       PORTC, 2, ACCESS
    bra         flow_adaptive_baud_select_3936
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         flow_adaptive_baud_select_3940
flow_adaptive_baud_select_3936:
    bcf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
flow_adaptive_baud_select_3940:
    bcf         LATB, 4, ACCESS
    bcf         LATB, 5, ACCESS
    bcf         LATB, 3, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bcf         LATB, 7, ACCESS
    call        main_uart_service_4938, 0x0
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
; Function: main_i2c_service_39a6
; Address : 0x39A6
; Notes   : Inferred i2c helper routine. Calls: main_core_service_2abc, main_core_service_38a2, main_core_service_301a.
; ---------------------------------------------------------------------------
main_i2c_service_39a6:
    clrf        ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
    clrf        ram_0x018, ACCESS
    movlw       0x4B
    movwf       ram_0x019, ACCESS
    movff       ram_0x049, ram_0x012
    movff       ram_0x04A, ram_0x013
    movff       ram_0x04B, ram_0x014
    movff       ram_0x04C, ram_0x015
    call        main_core_service_2abc, 0x0
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
    call        main_core_service_301a, 0x0
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
; Function: main_usb_service_3a26
; Address : 0x3A26
; Notes   : Inferred usb helper; touches usb. Calls: main_uart_service_495e, main_core_service_3c82, hid_command_dispatch.
; ---------------------------------------------------------------------------
main_usb_service_3a26:
    movlb       0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_3a26_3a3a
    btfss       active_flags, 3, ACCESS
    bra         flow_main_usb_service_3a26_3a3a
    btfsc       PORTC, 0, ACCESS
    bra         flow_main_usb_service_3a26_3a40
flow_main_usb_service_3a26_3a3a:
    call        main_uart_service_495e, 0x0
    bra         flow_main_usb_service_3a26_3aa2
flow_main_usb_service_3a26_3a40:
    tstfsz      ram_0x0C0, BANKED
    bra         flow_main_usb_service_3a26_3a7e
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         flow_main_usb_service_3a26_3aa2
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x1A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        main_core_service_3c82, 0x0
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0C0, BANKED
    clrf        ram_0x059, ACCESS
flow_main_usb_service_3a26_3a64:
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
    bra         flow_main_usb_service_3a26_3a64
    bra         flow_main_usb_service_3a26_3aa2
flow_main_usb_service_3a26_3a7e:
    movlb       0x1
    movf        ram_0x01A, W, BANKED
    call        hid_command_dispatch, 0x0
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         flow_main_usb_service_3a26_3aa2
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        main_core_service_3fd0, 0x0
    movlb       0x0
    clrf        ram_0x0C0, BANKED
flow_main_usb_service_3a26_3aa2:
    return      0

; ---------------------------------------------------------------------------
; Function: uart_rx_with_framing
; Address : 0x3AA4
; Notes   : Inferred uart helper routine. Calls: main_timer_service_477a, rx_ring_has_data, rx_ring_read.
; ---------------------------------------------------------------------------
uart_rx_with_framing:
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x00B, ACCESS
    movff       ram_0x005, ram_0x003
    movff       ram_0x006, ram_0x004
    call        main_timer_service_477a, 0x0
flow_uart_rx_with_framing_3ab8:
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    bz          flow_uart_rx_with_framing_3b06
    movff       ram_0x00F, ram_0x00A
    call        rx_ring_read, 0x0
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          flow_uart_rx_with_framing_3ae2
    movf        ram_0x00E, W, ACCESS
    addwf       ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x008, W, ACCESS
    movwf       FSR2H, ACCESS
    movff       ram_0x00F, INDF2
    incf        ram_0x00E, F, ACCESS
    bra         flow_uart_rx_with_framing_3aec
flow_uart_rx_with_framing_3ae2:
    movf        ram_0x00F, W, ACCESS
    xorlw       0x3A
    bnz         flow_uart_rx_with_framing_3aec
    movlw       0x01
    movwf       ram_0x00D, ACCESS
flow_uart_rx_with_framing_3aec:
    clrf        ram_0x00C, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          flow_uart_rx_with_framing_3b02
    movf        ram_0x00A, W, ACCESS
    xorlw       0x0D
    bnz         flow_uart_rx_with_framing_3b02
    movf        ram_0x00F, W, ACCESS
    xorlw       0x0A
    bnz         flow_uart_rx_with_framing_3b02
    movlw       0x01
    movwf       ram_0x00C, ACCESS
flow_uart_rx_with_framing_3b02:
    movff       ram_0x00C, ram_0x00B
flow_uart_rx_with_framing_3b06:
    call        main_usb_service_490c, 0x0
    bc          flow_uart_rx_with_framing_3b16
    movf        ram_0x009, W, ACCESS
    subwf       ram_0x00E, W, ACCESS
    bc          flow_uart_rx_with_framing_3b16
    movf        ram_0x00B, W, ACCESS
    bz          flow_uart_rx_with_framing_3ab8
flow_uart_rx_with_framing_3b16:
    call        main_timer_service_494c, 0x0
    movf        ram_0x00E, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: main_isr_dispatch
; Address : 0x3B1E
; Notes   : Inferred uart helper; touches timer,uart.
; ---------------------------------------------------------------------------
main_isr_dispatch:
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
    bz          flow_main_isr_dispatch_3b58
    decf        ram_0x08C, F, BANKED
    btfss       STATUS, 0, ACCESS
    decf        ram_0x08D, F, BANKED
    bra         uart_rx_irq_enqueue
flow_main_isr_dispatch_3b58:
    bcf         T3CON, 0, ACCESS
    bcf         PIE2, 1, ACCESS
uart_rx_irq_enqueue:
    btfss       PIR1, 5, ACCESS
    bra         flow_main_isr_dispatch_3b8c
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
    bra         flow_main_isr_dispatch_3b8c
    bcf         RCSTA, 4, ACCESS
    dw          0xF000
    bsf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
flow_main_isr_dispatch_3b8c:
    movff       isr_save_fsr2h, FSR2H
    movff       isr_save_fsr2l, FSR2L
    retfie      1

; ---------------------------------------------------------------------------
; Function: send_status_burst
; Address : 0x3B96
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, main_core_service_492e.
; ---------------------------------------------------------------------------
send_status_burst:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x05
    call        uart_tx_byte_blocking, 0x0
    movf        ram_0x05F, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    call        main_core_service_492e, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x07
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        computed_volume, W, BANKED
    addlw       0x60
    call        uart_tx_byte_blocking, 0x0
    call        main_core_service_492e, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x03
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    btfss       active_flags, 3, ACCESS
    movlw       0x00
    call        uart_tx_byte_blocking, 0x0
    call        main_core_service_492e, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x06
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        input_select, W, BANKED
    call        uart_tx_byte_blocking, 0x0
    call        main_core_service_492e, 0x0
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
    bra         flow_hw_standby_shutdown_3c34
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         flow_hw_standby_shutdown_3c3e
flow_hw_standby_shutdown_3c34:
    bcf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
flow_hw_standby_shutdown_3c3e:
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
    bc          flow_hw_standby_shutdown_3c78
    clrf        ram_0x008, ACCESS
    clrf        ram_0x009, ACCESS
flow_hw_standby_shutdown_3c58:
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
    bra         flow_hw_standby_shutdown_3c58
flow_hw_standby_shutdown_3c78:
    bcf         LATB, 3, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    goto        usb_shutdown


; ---------------------------------------------------------------------------
; Function: main_core_service_3c82
; Address : 0x3C82
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3c82:
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
    bra         flow_main_core_service_3c82_3cbc
flow_main_core_service_3c82_3c9c:
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
flow_main_core_service_3c82_3cbc:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x0CA, W, BANKED
    bnc         flow_main_core_service_3c82_3c9c
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
; Function: main_flash_service_3ce8
; Address : 0x3CE8
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_3ce8:
    lfsr        FSR2, 0x0003
    movf        POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    bnz         flow_main_flash_service_3ce8_3d04
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    movwf       POSTINC2, ACCESS
    movwf       POSTDEC2, ACCESS
    bra         flow_main_flash_service_3ce8_3d4c
flow_main_flash_service_3ce8_3d04:
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
flow_main_flash_service_3ce8_3d4c:
    return      0
flow_main_flash_service_3ce8_3d4e:
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
    movlw       LOW(inline_data_table_47E6)         ; TBLPTR -> inline_data_table_47E6
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(inline_data_table_47E6)
    movwf       TBLPTRH, ACCESS
    movlw       UPPER(inline_data_table_47E6)
    movwf       TBLPTRU, ACCESS
    lfsr        FSR0, 0x01E5
    lfsr        FSR1, 0x0016
flow_main_flash_service_3ce8_3d96:
    tblrd*+
    movff       TABLAT, POSTINC0
    movf        POSTDEC1, W, ACCESS
    movf        FSR1L, W, ACCESS
    bnz         flow_main_flash_service_3ce8_3d96
    movlw       UPPER(0x0000)                       ; clear TBLPTRU to program space
    movwf       TBLPTRU, ACCESS
    movlb       0x0
    goto        flow_i2c_wait_bus_idle_48c6

; ---------------------------------------------------------------------------
; Function: flash_erase (V3.1: preset B address remap prologue)
; Notes   : Remaps both start (ram_0x003-006) and end (ram_0x007-00A) addresses.
; ---------------------------------------------------------------------------
flash_erase:
    btfss       active_flags, 2, ACCESS     ; preset B active?
    bra         flash_erase_stock
    ; Remap start address (ram_0x004 = TBLPTRH)
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         flash_erase_remap_end
    movlw       0x56
    subwf       ram_0x004, W, ACCESS
    bnc         flash_erase_remap_end
    movlw       0x60
    subwf       ram_0x004, W, ACCESS
    bc          flash_erase_remap_end
    movlw       0x0A
    subwf       ram_0x004, F, ACCESS
flash_erase_remap_end:
    ; Remap end address (ram_0x008 = end TBLPTRH)
    movf        ram_0x00A, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    bnz         flash_erase_stock
    movlw       0x56
    subwf       ram_0x008, W, ACCESS
    bnc         flash_erase_stock
    movlw       0x60
    subwf       ram_0x008, W, ACCESS
    bc          flash_erase_stock
    movlw       0x0A
    subwf       ram_0x008, F, ACCESS
flash_erase_stock:
    clrf        ram_0x00B, ACCESS
    movff       ram_0x003, ram_0x00C
    movff       ram_0x004, ram_0x00D
    movff       ram_0x005, ram_0x00E
    movff       ram_0x006, ram_0x00F
    bra         flow_flash_erase_3df4
flow_flash_erase_3dc0:
    movff       ram_0x00E, TBLPTRU
    movff       ram_0x00D, TBLPTRH
    movff       ram_0x00C, TBLPTRL
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    bsf         EECON1, 4, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flow_flash_erase_3dde
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x00B, ACCESS
flow_flash_erase_3dde:
    call        main_flash_service_4406, 0x0
    movf        ram_0x00B, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         INTCON, 7, ACCESS
    movlw       0x40
    addwf       ram_0x00C, F, ACCESS
    movlw       0x00
    addwfc      ram_0x00D, F, ACCESS
    addwfc      ram_0x00E, F, ACCESS
    addwfc      ram_0x00F, F, ACCESS
flow_flash_erase_3df4:
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
    bra         flow_flash_erase_3dc0


; ---------------------------------------------------------------------------
; Function: main_core_service_3e0a
; Address : 0x3E0A
; Notes   : Inferred core helper routine. Calls: main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_3e0a:
    clrf        ram_0x011, ACCESS
    movf        ram_0x010, W, ACCESS
    xorlw       0x80
    addlw       0x80
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       ram_0x00F, W, ACCESS
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       ram_0x00E, W, ACCESS
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       ram_0x00D, W, ACCESS
flow_main_core_service_3e0a_3e24:
    bc          flow_main_core_service_3e0a_3e3a
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
flow_main_core_service_3e0a_3e3a:
    movff       ram_0x00D, ram_0x003
    movff       ram_0x00E, ram_0x004
    movff       ram_0x00F, ram_0x005
    movff       ram_0x010, ram_0x006
    movlw       0x96
    movwf       ram_0x007, ACCESS
    movff       ram_0x011, ram_0x008
    call        main_core_service_30d8, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_byte_tx (V3.1 enhanced)
; Notes   : Stock structure preserved (mode check, BF wait).
;           V3.1 adds: bounded BF wait, ACKSTAT latch (Fix A).
;           i2c_wait_bus_idle is already bounded (separate enhancement).
; ---------------------------------------------------------------------------
i2c_byte_tx:
    movff       WREG, ram_0x005
    movff       ram_0x005, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         flow_i2c_byte_tx_exit
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_master
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bz          flow_i2c_byte_tx_master
    bsf         SSPCON1, 4, ACCESS
flow_i2c_byte_tx_sspif:
    btfss       PIR1, 3, ACCESS
    bra         flow_i2c_byte_tx_sspif
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_master:
    ; Re-check mode (stock pattern preserved)
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_bf
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bnz         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_bf:
    ; V3.1: bounded BF wait (stock was unbounded loop)
    call        wait_bf_clear_bounded, 0x0
    bc          flow_i2c_byte_tx_exit
    call        i2c_wait_bus_idle, 0x0
    ; V3.1 Fix A: ACKSTAT check after successful master TX
    ; Save/restore BSR — callers may have any bank selected and stock
    ; i2c_byte_tx never touched BSR.
    movff       BSR, ram_0x00E              ; save caller's BSR
    movlb       0x0
    btfsc       SSPCON2, 6, ACCESS          ; ACKSTAT
    bsf         dsp_fault_flags, 2, BANKED
    movff       ram_0x00E, BSR              ; restore caller's BSR
    movf        SSPCON2, W, ACCESS
flow_i2c_byte_tx_exit:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3ec4
; Address : 0x3EC4
; Notes   : Inferred core helper routine. Calls: main_core_service_2abc.
; ---------------------------------------------------------------------------
main_core_service_3ec4:
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
    call        main_core_service_2abc, 0x0
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
; Function: main_core_service_3f1e
; Address : 0x3F1E
; Notes   : Inferred core helper routine. Calls: main_core_service_24c2.
; ---------------------------------------------------------------------------
main_core_service_3f1e:
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
    call        main_core_service_24c2, 0x0
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
    bra         flow_intel_hex_checksum_updat_3f90
    movlw       0x3A
    subwf       ram_0x005, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3f90
    movf        ram_0x005, W, ACCESS
    addlw       0xD0
    bra         flow_intel_hex_checksum_updat_3fa0
flow_intel_hex_checksum_updat_3f90:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         flow_intel_hex_checksum_updat_3fa2
    movlw       0x47
    subwf       ram_0x005, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fa2
    movf        ram_0x005, W, ACCESS
    addlw       0xC9
flow_intel_hex_checksum_updat_3fa0:
    movwf       ram_0x004, ACCESS
flow_intel_hex_checksum_updat_3fa2:
    swapf       ram_0x004, F, ACCESS
    movlw       0xF0
    andwf       ram_0x004, F, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x003, ACCESS
    bra         flow_intel_hex_checksum_updat_3fba
    movlw       0x3A
    subwf       ram_0x003, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fba
    movf        ram_0x003, W, ACCESS
    addlw       0xD0
    bra         flow_intel_hex_checksum_updat_3fca
flow_intel_hex_checksum_updat_3fba:
    movlw       0x40
    cpfsgt      ram_0x003, ACCESS
    bra         flow_intel_hex_checksum_updat_3fcc
    movlw       0x47
    subwf       ram_0x003, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fcc
    movf        ram_0x003, W, ACCESS
    addlw       0xC9
flow_intel_hex_checksum_updat_3fca:
    addwf       ram_0x004, F, ACCESS
flow_intel_hex_checksum_updat_3fcc:
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3fd0
; Address : 0x3FD0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3fd0:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         flow_main_core_service_3fd0_3fd8
    movwf       ram_0x005, ACCESS
flow_main_core_service_3fd0_3fd8:
    clrf        ram_0x007, ACCESS
    bra         flow_main_core_service_3fd0_3ffa
flow_main_core_service_3fd0_3fdc:
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
flow_main_core_service_3fd0_3ffa:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x007, W, ACCESS
    bnc         flow_main_core_service_3fd0_3fdc
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
; Function: flash_read (V3.1: preset B address remap prologue)
; Notes   : Remaps 0x56xx-0x5Fxx to 0x4Axx-0x53xx when preset B active.
; ---------------------------------------------------------------------------
flash_read:
    btfss       active_flags, 2, ACCESS     ; preset B active?
    bra         flash_read_stock
    movf        ram_0x006, W, ACCESS        ; check TBLPTRU = 0
    iorwf       ram_0x005, W, ACCESS
    bnz         flash_read_stock
    movlw       0x56
    subwf       ram_0x004, W, ACCESS        ; TBLPTRH >= 0x56?
    bnc         flash_read_stock
    movlw       0x60
    subwf       ram_0x004, W, ACCESS        ; TBLPTRH < 0x60?
    bc          flash_read_stock
    movlw       0x0A
    subwf       ram_0x004, F, ACCESS        ; remap: 0x56->0x4C etc.
flash_read_stock:
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
    bra         flow_flash_read_4064
flow_flash_read_4052:
    tblrd*+
    movff       ram_0x009, FSR2L
    movff       ram_0x00A, FSR2H
    movff       TABLAT, INDF2
    infsnz      ram_0x009, F, ACCESS
    incf        ram_0x00A, F, ACCESS
flow_flash_read_4064:
    decf        ram_0x007, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x008, F, ACCESS
    incf        ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    incf        ram_0x008, W, ACCESS
    bnz         flow_flash_read_4052
    movff       ram_0x011, TBLPTRU
    movff       ram_0x010, TBLPTRH
    movff       ram_0x00F, TBLPTRL
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4080
; Address : 0x4080
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4080:
    movff       WREG, ram_0x003
    movlw       0x08
    movlb       0x1
    movwf       ram_0x017, BANKED
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x1C
    movwf       ram_0x018, BANKED
    tstfsz      ram_0x003, ACCESS
    bra         flow_main_core_service_4080_40a8
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x14
    movwf       ram_0x018, BANKED
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
    movlw       0x00
    bra         flow_main_core_service_4080_40ae
flow_main_core_service_4080_40a8:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
flow_main_core_service_4080_40ae:
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
; Function: main_usb_service_40d6
; Address : 0x40D6
; Notes   : Inferred usb helper; touches usb. Calls: usb_disconnect_handler, main_core_service_4080.
; ---------------------------------------------------------------------------
main_usb_service_40d6:
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
    bra         flow_main_usb_service_40d6_4102
flow_main_usb_service_40d6_40fc:
    bcf         UIR, 3, ACCESS
    call        usb_disconnect_handler, 0x0
flow_main_usb_service_40d6_4102:
    btfsc       UIR, 3, ACCESS
    bra         flow_main_usb_service_40d6_40fc
    bcf         UCON, 6, ACCESS
    bcf         UCON, 4, ACCESS
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    clrf        ram_0x0CE, BANKED
    clrf        ram_0x0EB, BANKED
    movlw       0x00
    goto        main_core_service_48fe


; ---------------------------------------------------------------------------
; Function: main_adc_service_4124
; Address : 0x4124
; Notes   : Inferred adc helper; touches adc.
; ---------------------------------------------------------------------------
main_adc_service_4124:
    clrf        ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          flow_main_adc_service_4124_4164
    movlw       0x01
    movwf       ram_0x009, ACCESS
    bra         flow_main_adc_service_4124_413c
flow_main_adc_service_4124_4134:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x009, F, ACCESS
flow_main_adc_service_4124_413c:
    btfss       ram_0x006, 7, ACCESS
    bra         flow_main_adc_service_4124_4134
flow_main_adc_service_4124_4140:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x007, F, ACCESS
    rlcf        ram_0x008, F, ACCESS
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         flow_main_adc_service_4124_415a
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
    bsf         ram_0x007, 0, ACCESS
flow_main_adc_service_4124_415a:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x009, F, ACCESS
    bra         flow_main_adc_service_4124_4140
flow_main_adc_service_4124_4164:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    return      0
an0_hysteresis_monitor:
    btfss       active_flags, 3, ACCESS
    bra         flow_main_adc_service_4124_41b4
    movf        ram_0x0A1, W, BANKED
    xorlw       0x64
    bnz         flow_main_adc_service_4124_41b2
    btfsc       ADCON0, 1, ACCESS
    bra         flow_main_adc_service_4124_41ae
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
    bra         flow_main_adc_service_4124_41ae
    movlw       0x28
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          flow_main_adc_service_4124_41ae
    bcf         active_flags, 3, ACCESS
    bsf         event_flags, 2, BANKED
flow_main_adc_service_4124_41ae:
    clrf        ram_0x0A1, BANKED
    bra         flow_main_adc_service_4124_41b4
flow_main_adc_service_4124_41b2:
    incf        ram_0x0A1, F, BANKED
flow_main_adc_service_4124_41b4:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_41b6
; Address : 0x41B6
; Notes   : Inferred core helper routine. Calls: main_core_service_34c8.
; ---------------------------------------------------------------------------
main_core_service_41b6:
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
    bc          flow_main_core_service_41b6_41e4
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
flow_main_core_service_41b6_41e4:
    movff       ram_0x012, ram_0x00A
    movff       ram_0x013, ram_0x00B
    movff       ram_0x014, ram_0x00C
    movff       ram_0x015, ram_0x00D
    movf        ram_0x017, W, ACCESS
    call        main_core_service_34c8, 0x0
    movf        ram_0x016, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_41fe
; Address : 0x41FE
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_48fe.
; ---------------------------------------------------------------------------
main_usb_service_41fe:
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
flow_main_usb_service_41fe_4212:
    movf        ram_0x091, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x091, F, BANKED
    movf        ram_0x091, W, BANKED
    bz          flow_main_usb_service_41fe_4212
    movff       ram_0x0D1, ram_0x0EB
    movf        ram_0x0EB, W, BANKED
    call        main_core_service_48fe, 0x0
    movlb       0x0
    tstfsz      ram_0x0D1, BANKED
    bra         flow_main_usb_service_41fe_4236
    movlw       0x05
    bra         flow_main_usb_service_41fe_4238
flow_main_usb_service_41fe_4236:
    movlw       0x06
flow_main_usb_service_41fe_4238:
    movwf       ram_0x0CD, BANKED
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_secondary_dev_random_read
; Address : 0x423C
; Notes   : Inferred i2c helper; touches i2c. Calls: i2c_wait_bus_idle, i2c_byte_tx, main_i2c_service_464c.
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
    call        main_i2c_service_464c, 0x0
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
; Function: main_core_service_427a
; Address : 0x427A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_427a:
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          flow_main_core_service_427a_42ae
    movlw       0x01
    movwf       ram_0x007, ACCESS
    bra         flow_main_core_service_427a_428e
flow_main_core_service_427a_4286:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x007, F, ACCESS
flow_main_core_service_427a_428e:
    btfss       ram_0x006, 7, ACCESS
    bra         flow_main_core_service_427a_4286
flow_main_core_service_427a_4292:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         flow_main_core_service_427a_42a4
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
flow_main_core_service_427a_42a4:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x007, F, ACCESS
    bra         flow_main_core_service_427a_4292
flow_main_core_service_427a_42ae:
    movff       ram_0x003, ram_0x003
    movff       ram_0x004, ram_0x004
    return      0

; ---------------------------------------------------------------------------
; Function: flash_write_with_gie_off
; Address : 0x42B8
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_4406.
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
    call        main_flash_service_4406, 0x0
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
    call        main_flash_service_4406, 0x0
flow_flash_write_with_gie_off_42ec:
    btfsc       EECON1, 1, ACCESS
    bra         flow_flash_write_with_gie_off_42ec
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_42f4
; Address : 0x42F4
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_3682, flow_main_core_service_3188_3194.
; ---------------------------------------------------------------------------
main_usb_service_42f4:
    movlb       0x4
    clrf        ram_0x008, BANKED
    movlb       0x0
    clrf        ram_0x0CC, BANKED
    movlb       0x4
    btfss       ram_0x000, 7, BANKED
    bra         flow_main_usb_service_42f4_4308
    clrf        ram_0x000, BANKED
    movlb       0x0
    clrf        ram_0x096, BANKED
flow_main_usb_service_42f4_4308:
    movlb       0x4
    btfss       ram_0x004, 7, BANKED
    bra         flow_main_usb_service_42f4_4316
    clrf        ram_0x004, BANKED
    movlw       0x01
    movlb       0x0
    movwf       ram_0x096, BANKED
flow_main_usb_service_42f4_4316:
    movlb       0x0
    clrf        ram_0x0C9, BANKED
    clrf        ram_0x0C8, BANKED
    clrf        ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bcf         UCON, 4, ACCESS
    call        main_core_service_3682, 0x0
    call        flow_main_core_service_3188_3194, 0x0
    goto        flow_main_core_service_3188_324c


; ---------------------------------------------------------------------------
; Function: main_core_service_432e
; Address : 0x432E
; Notes   : Inferred core helper routine. Calls: main_core_service_24c2.
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
    call        main_core_service_24c2, 0x0
    movff       ram_0x020, ram_0x039
    movff       ram_0x021, ram_0x03A
    movff       ram_0x022, ram_0x03B
    movff       ram_0x023, ram_0x03C
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_tas3108_reg1f_write (V3.1 enhanced)
; Notes   : Bounded SEN/PEN waits via i2c_wait_bus_idle + i2c_byte_tx.
; ---------------------------------------------------------------------------
i2c_tas3108_reg1f_write:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    call        wait_sen_bounded, 0x0
    bc          i2c_reg1f_done
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
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    call        wait_pen_bounded, 0x0
i2c_reg1f_done:
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_43a2
; Address : 0x43A2
; Notes   : Inferred uart helper routine. Calls: tblrd_lookup, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
main_uart_service_43a2:
    movff       WREG, ram_0x006
    movff       ram_0x006, ram_0x004
    swapf       ram_0x004, F, ACCESS
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    rcall       tblrd_lookup
    call        uart_tx_byte_blocking, 0x0
    movwf       ram_0x005, ACCESS
    movff       ram_0x006, ram_0x004
    movlw       0x0F
    rcall       tblrd_lookup
    call        uart_tx_byte_blocking, 0x0
    xorwf       ram_0x005, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: tblrd_lookup
; Address : 0x43C8
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
tblrd_lookup:
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
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_4406.
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
    rcall       main_flash_service_4406
flow_eeprom_write_blocking_43f4:
    btfsc       EECON1, 1, ACCESS
    bra         flow_eeprom_write_blocking_43f4
    btfsc       ram_0x006, 0, ACCESS
    bra         flow_eeprom_write_blocking_4400
    bcf         INTCON, 7, ACCESS
    bra         flow_eeprom_write_blocking_4402
flow_eeprom_write_blocking_4400:
    bsf         INTCON, 7, ACCESS
flow_eeprom_write_blocking_4402:
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_4406
; Address : 0x4406
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_4406:
    movlw       0x55
    movwf       EECON2, ACCESS
    movlw       0xAA
    movwf       EECON2, ACCESS
    bsf         EECON1, 1, ACCESS
    retlw       0xAA


; ---------------------------------------------------------------------------
; Function: main_usb_service_4412
; Address : 0x4412
; Notes   : Inferred usb helper; touches usb. Calls: main_flash_service_35f0.
; ---------------------------------------------------------------------------
main_usb_service_4412:
    movf        ram_0x0CD, W, BANKED
    xorlw       0x04
    bnz         flow_main_usb_service_4412_4426
    movff       ram_0x0D1, UADDR
    movf        UADDR, W, ACCESS
    movlw       0x05
    btfsc       STATUS, 2, ACCESS
    movlw       0x03
    movwf       ram_0x0CD, BANKED
flow_main_usb_service_4412_4426:
    decf        ram_0x0C9, W, BANKED
    bnz         flow_main_usb_service_4412_4446
    call        main_flash_service_35f0, 0x0
    movf        ram_0x0CC, W, BANKED
    xorlw       0x02
    bnz         flow_main_usb_service_4412_443a
    movlw       0x04
    movlb       0x4
    bra         flow_main_usb_service_4412_4442
flow_main_usb_service_4412_443a:
    movlb       0x4
    movlw       0x48
    btfsc       ram_0x008, 6, BANKED
    movlw       0x08
flow_main_usb_service_4412_4442:
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
flow_main_usb_service_4412_4446:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4448
; Address : 0x4448
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4448:
    movff       WREG, ram_0x003
    bra         flow_main_core_service_4448_446c
flow_main_core_service_4448_444e:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    clrf        ram_0x0B9, BANKED
    bra         flow_main_core_service_4448_447c
flow_main_core_service_4448_4456:
    clrf        ram_0x0A0, BANKED
    movlw       0x01
    bra         flow_main_core_service_4448_4468
flow_main_core_service_4448_445c:
    movlw       0x02
    movwf       ram_0x0A0, BANKED
    bra         flow_main_core_service_4448_4468
flow_main_core_service_4448_4462:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    movlw       0x03
flow_main_core_service_4448_4468:
    movwf       ram_0x0B9, BANKED
    bra         flow_main_core_service_4448_447c
flow_main_core_service_4448_446c:
    movf        ram_0x003, W, ACCESS
    bz          flow_main_core_service_4448_444e
    xorlw       0x01
    bz          flow_main_core_service_4448_4456
    xorlw       0x03
    bz          flow_main_core_service_4448_445c
    xorlw       0x01
    bz          flow_main_core_service_4448_4462
flow_main_core_service_4448_447c:
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
    bra         flow_timer3_blocking_delay_44a8
flow_timer3_blocking_delay_4488:
    btfss       OSCCON, 1, ACCESS
    bra         flow_timer3_blocking_delay_4494
    movlw       0xFC
    movwf       TMR3H, ACCESS
    movlw       0x18
    bra         flow_timer3_blocking_delay_449a
flow_timer3_blocking_delay_4494:
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
flow_timer3_blocking_delay_449a:
    movwf       TMR3L, ACCESS
    bcf         PIR2, 1, ACCESS
flow_timer3_blocking_delay_449e:
    btfss       PIR2, 1, ACCESS
    bra         flow_timer3_blocking_delay_449e
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
flow_timer3_blocking_delay_44a8:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    bnz         flow_timer3_blocking_delay_4488
    bcf         T3CON, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_44b2
; Address : 0x44B2
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, uart_tx_block_from_buffer.
; ---------------------------------------------------------------------------
main_uart_service_44b2:
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
; Function: i2c_tas3108_coeff_write (V3.1 enhanced — Fix F: boot-gated PEN)
; Notes   : Bounded SEN wait. PEN wait is boot-gated: unbounded during boot
;           (safe — DSP always ACKs during init), bounded after boot complete.
; ---------------------------------------------------------------------------
i2c_tas3108_coeff_write:
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    call        wait_sen_bounded, 0x0
    bc          coeff_write_pen_done
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x30
    call        i2c_byte_tx, 0x0
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    ; Fix F: boot-gated PEN wait — bounded after boot, stock during boot
    btfss       event_flags, 7, BANKED      ; boot complete?
    bra         coeff_write_pen_stock       ; no: stock unbounded (safe during DSP init)
    call        wait_pen_bounded, 0x0
    bc          coeff_write_pen_timeout
    bra         coeff_write_pen_done
coeff_write_pen_timeout:
    ; PEN stuck: flag fault and force NACK for retry. On real HW the
    ; watchdog would catch true hangs; in gpsim the test harness
    ; force-clears SSPCON2 after clearing the fault model.
    bsf         dsp_fault_flags, 6, BANKED  ; flag DSP fault
    bsf         dsp_fault_flags, 2, BANKED  ; force NACK → volume_dsp_write retries
    bra         coeff_write_pen_done
coeff_write_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    bra         coeff_write_pen_done
    bra         coeff_write_pen_stock
coeff_write_pen_done:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4516
; Address : 0x4516
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4516:
    tstfsz      ram_0x05F, ACCESS
    bra         flow_main_core_service_4516_4534
flow_main_core_service_4516_451a:
    bcf         LATA, 3, ACCESS
    bra         flow_main_core_service_4516_4520
flow_main_core_service_4516_451e:
    bsf         LATA, 3, ACCESS
flow_main_core_service_4516_4520:
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bra         flow_main_core_service_4516_4544
flow_main_core_service_4516_4526:
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bra         flow_main_core_service_4516_4530
flow_main_core_service_4516_452c:
    bcf         LATA, 3, ACCESS
    bsf         LATA, 4, ACCESS
flow_main_core_service_4516_4530:
    bsf         LATA, 5, ACCESS
    bra         flow_main_core_service_4516_4544
flow_main_core_service_4516_4534:
    movf        ram_0x093, W, BANKED
    bz          flow_main_core_service_4516_451a
    xorlw       0x05
    bz          flow_main_core_service_4516_451e
    xorlw       0x03
    bz          flow_main_core_service_4516_4526
    xorlw       0x01
    bz          flow_main_core_service_4516_452c
flow_main_core_service_4516_4544:
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
; Function: main_core_service_4574
; Address : 0x4574
; Notes   : Inferred core helper routine. Calls: main_i2c_service_381c.
; ---------------------------------------------------------------------------
main_core_service_4574:
    movlw       0x56
    movwf       ram_0x033, ACCESS
    movlw       0x00
    clrf        ram_0x032, ACCESS
    clrf        ram_0x034, ACCESS
flow_main_core_service_4574_457e:
    movff       ram_0x032, ram_0x013
    movff       ram_0x033, ram_0x014
    call        main_i2c_service_381c, 0x0
    movlw       0x18
    addwf       ram_0x032, F, ACCESS
    movlw       0x00
    addwfc      ram_0x033, F, ACCESS
    incf        ram_0x034, F, ACCESS
    movlw       0x5F
    cpfsgt      ram_0x034, ACCESS
    bra         flow_main_core_service_4574_457e
    movwf       ram_0x014, ACCESS
    clrf        ram_0x013, ACCESS
    goto        main_i2c_service_381c


; ---------------------------------------------------------------------------
; Function: main_usb_service_45a2
; Address : 0x45A2
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_2328, main_core_service_3fd0.
; ---------------------------------------------------------------------------
main_usb_service_45a2:
    call        main_core_service_2328, 0x0
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
    call        main_core_service_3fd0, 0x0
flow_main_usb_service_45a2_45cc:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_45ce
; Address : 0x45CE
; Notes   : Inferred core helper routine. Calls: main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_45ce:
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
    call        main_core_service_30d8, 0x0
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
    bz          flow_rx_ring_read_4620
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
    bra         flow_rx_ring_read_4620
    clrf        rx_ring_rd, BANKED
flow_rx_ring_read_4620:
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4624
; Address : 0x4624
; Notes   : Inferred usb helper; touches usb.
; ---------------------------------------------------------------------------
main_usb_service_4624:
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
; Function: main_i2c_service_464c
; Address : 0x464C
; Notes   : Inferred i2c helper; touches i2c.
; ---------------------------------------------------------------------------
main_i2c_service_464c:
    movf        SSPCON1, W, ACCESS
    andlw       0x0F
    xorlw       0x08
    bz          flow_main_i2c_service_464c_4668
    xorlw       0x0B
    btfsc       STATUS, 2, ACCESS
flow_main_i2c_service_464c_4668:
    bsf         SSPCON2, 3, ACCESS
flow_main_i2c_service_464c_466a:
    btfss       SSPSTAT, 0, ACCESS
    bra         flow_main_i2c_service_464c_466a
    movf        SSPBUF, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4672
; Address : 0x4672
; Notes   : Inferred core helper routine. Calls: main_uart_service_44b2.
; ---------------------------------------------------------------------------
main_core_service_4672:
    lfsr        FSR2, 0x01F4
    lfsr        FSR1, 0x001C
    movlw       0x07
flow_main_core_service_4672_467c:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_4672_467c
    movlw       0x1C
    call        main_uart_service_44b2, 0x0
    movlw       0x1C
    call        main_uart_service_44b2, 0x0
    movlw       0x1C
    goto        main_uart_service_44b2


; ---------------------------------------------------------------------------
; Function: uart_tx_block_from_buffer
; Address : 0x4696
; Notes   : Transmits a buffered UART block one byte at a time.
; ---------------------------------------------------------------------------
uart_tx_block_from_buffer:
    clrf        ram_0x01A, ACCESS
    bra         flow_uart_tx_block_from_buffe_46a2
flow_uart_tx_block_from_buffe_469a:
    rcall       main_core_service_46aa
    call        uart_tx_byte_blocking, 0x0
    incf        ram_0x01A, F, ACCESS
flow_uart_tx_block_from_buffe_46a2:
    rcall       main_core_service_46aa
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_uart_tx_block_from_buffe_469a


; ---------------------------------------------------------------------------
; Function: main_core_service_46aa
; Address : 0x46AA
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_46aa:
    movf        ram_0x01A, W, ACCESS
    addwf       ram_0x018, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x019, W, ACCESS
    movwf       FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_secondary_dev_write (V3.1 enhanced)
; Notes   : Bounded SEN/PEN waits via wait helpers.
; ---------------------------------------------------------------------------
i2c_secondary_dev_write:
    movff       WREG, ram_0x007
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    call        wait_sen_bounded, 0x0
    bc          i2c_secondary_done
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        ram_0x007, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    call        wait_pen_bounded, 0x0
i2c_secondary_done:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_46de
; Address : 0x46DE
; Notes   : Inferred flash helper routine. Calls: eeprom_read_byte, eeprom_write_blocking.
; ---------------------------------------------------------------------------
main_flash_service_46de:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    call        eeprom_read_byte, 0x0
    xorwf       ram_0x009, W, ACCESS
    bz          flow_main_flash_service_46de_46fe
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    movff       ram_0x009, ram_0x005
    call        eeprom_write_blocking, 0x0
flow_main_flash_service_46de_46fe:
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4700
; Address : 0x4700
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4828, main_usb_service_40d6.
; ---------------------------------------------------------------------------
main_usb_service_4700:
    decf        usb_reinit_pending, W, BANKED
    btfsc       STATUS, 2, ACCESS
    call        main_usb_service_4828, 0x0
    clrf        UCON, ACCESS
    movlw       0x15
    movwf       UCFG, ACCESS
    clrf        UIE, ACCESS
    bsf         UCON, 3, ACCESS
    call        main_usb_service_40d6, 0x0
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0CD, BANKED
    clrf        usb_reinit_pending, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4720
; Address : 0x4720
; Notes   : Inferred usb helper; touches timer,usb.
; ---------------------------------------------------------------------------
main_usb_service_4720:
    movff       UIE, ram_0x092
    movlw       0x04
    movwf       UIE, ACCESS
    bcf         UIR, 4, ACCESS
    bsf         UCON, 1, ACCESS
    bcf         PIR2, 5, ACCESS
    bsf         PIE2, 5, ACCESS
    bcf         PIE2, 5, ACCESS
    movlb       0x0
    movf        ram_0x092, W, BANKED
    iorwf       UIE, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: ram_block_clear
; Address : 0x473E
; Notes   : Clears a RAM span from an FSR2 pointer and byte count.
; ---------------------------------------------------------------------------
ram_block_clear:
    clrf        ram_0x006, ACCESS
    bra         flow_ram_block_clear_4752
flow_ram_block_clear_4742:
    movf        ram_0x006, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x006, F, ACCESS
flow_ram_block_clear_4752:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x006, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         flow_ram_block_clear_4742


; ---------------------------------------------------------------------------
; Function: main_usb_service_475c
; Address : 0x475C
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4700, usb_shutdown.
; ---------------------------------------------------------------------------
main_usb_service_475c:
    movlb       0x0
    decf        usb_reinit_pending, W, BANKED
    bz          flow_main_usb_service_475c_4778
    btfss       PORTC, 0, ACCESS
    bra         flow_main_usb_service_475c_476e
    btfss       UCON, 3, ACCESS
    call        main_usb_service_4700, 0x0
    bra         flow_main_usb_service_475c_4778
flow_main_usb_service_475c_476e:
    btfss       UCON, 3, ACCESS
    bra         flow_main_usb_service_475c_4778
    call        usb_shutdown, 0x0
    clrf        usb_reinit_pending, BANKED
flow_main_usb_service_475c_4778:
    return      0


; ---------------------------------------------------------------------------
; Function: main_timer_service_477a
; Address : 0x477A
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
main_timer_service_477a:
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
; Notes   : Inferred adc helper routine. Calls: adc_boot_gate, hw_standby_shutdown.
; ---------------------------------------------------------------------------
standby_event_dispatch:
    movlb       0x0
    btfss       event_flags, 2, BANKED
    bra         flow_standby_event_dispatch_47ac
    btfss       active_flags, 3, ACCESS
    bra         flow_standby_event_dispatch_47a6
    call        adc_boot_gate, 0x0
    bra         flow_standby_event_dispatch_47aa
flow_standby_event_dispatch_47a6:
    call        hw_standby_shutdown, 0x0
flow_standby_event_dispatch_47aa:
    bcf         event_flags, 2, BANKED
flow_standby_event_dispatch_47ac:
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
; Function: periodic_service_loop
; Address : 0x47CE
; Notes   : Inferred core helper routine. Calls: main_usb_service_3a26, main_uart_service_1be6, main_i2c_service_27f0.
; ---------------------------------------------------------------------------
periodic_service_loop:
    call        main_usb_service_3a26, 0x0
    call        main_uart_service_1be6, 0x0
    call        main_i2c_service_27f0, 0x0
    call        standby_event_dispatch, 0x0
    call        main_core_service_265c, 0x0
    goto        an0_hysteresis_monitor

; ---------------------------------------------------------------------------
; Inline Data Table (0x47E6-0x47FB)
; ---------------------------------------------------------------------------
inline_data_table_47E6:  ; UART status strings for FW update
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
; Function: main_usb_service_4812
; Address : 0x4812
; Notes   : Inferred usb helper routine. Calls: usb_disconnect_handler.
; ---------------------------------------------------------------------------
main_usb_service_4812:
    bra         flow_main_usb_service_4812_481e
flow_main_usb_service_4812_4814:
    call        usb_disconnect_handler, 0x0
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
flow_main_usb_service_4812_481e:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_main_usb_service_4812_4814


; ---------------------------------------------------------------------------
; Function: main_usb_service_4828
; Address : 0x4828
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4812.
; ---------------------------------------------------------------------------
main_usb_service_4828:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlw       0xFF
    setf        ram_0x004, ACCESS
    setf        ram_0x003, ACCESS
    call        main_usb_service_4812, 0x0
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_483c
; Address : 0x483C
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_4924.
; ---------------------------------------------------------------------------
main_usb_service_483c:
    call        main_core_service_4924, 0x0
    bcf         UCON, 1, ACCESS
    bcf         UIE, 2, ACCESS
    bra         flow_main_usb_service_483c_4848
flow_main_usb_service_483c_4846:
    bcf         UIR, 2, ACCESS
flow_main_usb_service_483c_4848:
    btfss       UIR, 2, ACCESS
    return      0
    bra         flow_main_usb_service_483c_4846


; ---------------------------------------------------------------------------
; Function: factory_reset_status_emit
; Address : 0x484E
; Notes   : Emits BF/18/01 factory-reset status frame over UART.
; ---------------------------------------------------------------------------
factory_reset_status_emit:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x18
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    goto        uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: main_uart_service_4860
; Address : 0x4860
; Notes   : Inferred uart helper routine. Calls: rx_ring_read, rx_ring_has_data.
; ---------------------------------------------------------------------------
main_uart_service_4860:
    bra         flow_main_uart_service_4860_4866
flow_main_uart_service_4860_4862:
    call        rx_ring_read, 0x0
flow_main_uart_service_4860_4866:
    call        rx_ring_has_data, 0x0
    iorlw       0x00
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_main_uart_service_4860_4862


; ---------------------------------------------------------------------------
; Function: rx_ring_has_data
; Address : 0x4872
; Notes   : Checks whether RX ring has unread data (returns zero when write index == read index).
; ---------------------------------------------------------------------------
rx_ring_has_data:
    movlb       0x0
    movf        rx_ring_wr, W, BANKED
    xorwf       rx_ring_rd, W, BANKED
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
; Function: uart_tx_byte_blocking (V3.1 enhanced)
; Notes   : Bounded TRMT wait, two-strike recovery.
; ---------------------------------------------------------------------------
uart_tx_byte_blocking:
    movff       WREG, ram_0x003
    call        wait_trmt_bounded, 0x0
    bc          uart_tx_timeout
    movff       ram_0x003, TXREG
    movf        ram_0x003, W, ACCESS
    return      0
uart_tx_timeout:
    call        uart_config, 0x0
    call        wait_trmt_bounded, 0x0
    bc          v31_hard_reset_jump2
    movff       ram_0x003, TXREG
    movf        ram_0x003, W, ACCESS
    return      0
v31_hard_reset_jump2:
    goto        hard_reset


; ---------------------------------------------------------------------------
; Function: main_timer_service_48a6
; Address : 0x48A6
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
main_timer_service_48a6:
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    bcf         INTCON, 2, ACCESS
    bsf         INTCON, 5, ACCESS
    bsf         T0CON, 7, ACCESS
    retlw       0x71

; ---------------------------------------------------------------------------
; Function: i2c_wait_bus_idle (stock — unbounded spin)
; Notes   : Stock idle wait. Blocks until SSPCON2[4:0]==0 && R_nW==0.
;           Callers of coeff_write/reg1f_write have separate bus-busy guards.
; ---------------------------------------------------------------------------
i2c_wait_bus_idle:
    movff       SSPCON2, ram_0x003
    movlw       0x1F
    andwf       ram_0x003, F, ACCESS
    btfsc       STATUS, 2, ACCESS
    btfsc       SSPSTAT, 2, ACCESS
    bra         i2c_wait_bus_idle
    retlw       0x1F
flow_i2c_wait_bus_idle_48c6:
    call        main_i2c_service_355c, 0x0
main_processing_loop:
    call        main_usb_service_2f4e, 0x0
    call        periodic_service_loop, 0x0
    bra         main_processing_loop

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
; Function: main_i2c_service_48e2
; Address : 0x48E2
; Notes   : Inferred i2c helper routine. Calls: i2c_tas3108_reg1f_write.
; ---------------------------------------------------------------------------
main_i2c_service_48e2:
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
; Function: main_core_service_48fe
; Address : 0x48FE
; Notes   : Inferred core helper routine. Calls: main_usb_service_4624.
; ---------------------------------------------------------------------------
main_core_service_48fe:
    movff       WREG, ram_0x003
    decf        ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    call        main_usb_service_4624, 0x0
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_490c
; Address : 0x490C
; Notes   : Inferred usb helper; touches timer,usb. Calls: main_usb_service_4828.
; ---------------------------------------------------------------------------
main_usb_service_490c:
    btfss       T3CON, 0, ACCESS
    bra         flow_main_usb_service_490c_4914
    bcf         STATUS, 0, ACCESS
    bra         flow_main_usb_service_490c_4916
flow_main_usb_service_490c_4914:
    bsf         STATUS, 0, ACCESS
flow_main_usb_service_490c_4916:
    return      0
flow_main_usb_service_490c_4918:
    btfsc       UCON, 3, ACCESS
    call        main_usb_service_4828, 0x0
    clrf        usb_reinit_pending, BANKED
    goto        main_usb_service_475c


; ---------------------------------------------------------------------------
; Function: main_core_service_4924
; Address : 0x4924
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4924:
    movlw       0x03
    movwf       ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    goto        flow_main_usb_service_4812_481e


; ---------------------------------------------------------------------------
; Function: main_core_service_492e
; Address : 0x492E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_492e:
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    goto        timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: main_uart_service_4938
; Address : 0x4938
; Notes   : Inferred uart helper routine. Calls: uart_config.
; ---------------------------------------------------------------------------
main_uart_service_4938:
    call        uart_config, 0x0
    bcf         active_flags, 0, ACCESS
    clrf        rx_frame_position, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4942
; Address : 0x4942
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4942:
    clrf        ram_0x004, ACCESS
    movlw       0x02
    movwf       ram_0x003, ACCESS
    goto        timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: main_timer_service_494c
; Address : 0x494C
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
main_timer_service_494c:
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
; Function: main_core_service_496c
; Address : 0x496C
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_496c:
    return      0


; ===========================================================================
; V3.1 New Functions (after last stock function, before preset tables)
; ===========================================================================

; ---------------------------------------------------------------------------
; Bounded Wait Helpers (shared 16-bit timeout infrastructure)
; ---------------------------------------------------------------------------
wait_seed:
    clrf        timeout_lo, ACCESS
    movlw       0x10
    movwf       timeout_hi, ACCESS
    bcf         STATUS, 0, ACCESS           ; clear C
    return      0

wait_tick:
    decfsz      timeout_lo, F, ACCESS
    return      0
    decfsz      timeout_hi, F, ACCESS
    return      0
    bsf         STATUS, 0, ACCESS           ; C=1: timeout
    return      0

wait_trmt_bounded:
    call        wait_seed, 0x0
wait_trmt_loop:
    btfsc       TXSTA, 1, ACCESS            ; TRMT?
    bra         wait_wait_done
    call        wait_tick, 0x0
    bnc         wait_trmt_loop
    return      0

wait_sen_bounded:
    call        wait_seed, 0x0
wait_sen_loop:
    btfss       SSPCON2, 0, ACCESS          ; SEN clear?
    bra         wait_wait_done
    call        wait_tick, 0x0
    bnc         wait_sen_loop
    return      0

wait_pen_bounded:
    call        wait_seed, 0x0
wait_pen_loop:
    btfss       SSPCON2, 2, ACCESS          ; PEN clear?
    bra         wait_wait_done
    call        wait_tick, 0x0
    bnc         wait_pen_loop
    return      0

wait_bf_clear_bounded:
    call        wait_seed, 0x0
wait_bf_clear_loop:
    btfss       SSPSTAT, 0, ACCESS          ; BF set?
    bra         wait_wait_done              ; BF=0: buffer empty, done
    call        wait_tick, 0x0
    bnc         wait_bf_clear_loop
    return      0                           ; C=1: timed out
wait_wait_done:
    bcf         STATUS, 0, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Recovery Helpers
; ---------------------------------------------------------------------------
; ---------------------------------------------------------------------------
; I2C Bus Clear (Fix C) — 9 SCL clocks + manual STOP
; ---------------------------------------------------------------------------
i2c_bus_clear:
    bcf         SSPCON1, 5, ACCESS          ; SSPEN off — release pins
    bsf         TRISB, 1, ACCESS            ; RB1 (SCL) input (pulled high)
    bsf         TRISB, 0, ACCESS            ; RB0 (SDA) input (pulled high)
    movlw       0x09
    movwf       timeout_lo, ACCESS
i2c_bus_clear_clk:
    bcf         TRISB, 1, ACCESS            ; SCL low
    bcf         LATB, 1, ACCESS
    nop
    nop
    bsf         TRISB, 1, ACCESS            ; SCL high
    nop
    nop
    btfsc       PORTB, 0, ACCESS            ; SDA released?
    bra         i2c_bus_clear_stop
    decfsz      timeout_lo, F, ACCESS
    bra         i2c_bus_clear_clk
i2c_bus_clear_stop:
    bcf         TRISB, 0, ACCESS            ; SDA output
    bcf         LATB, 0, ACCESS             ; SDA low
    nop
    bsf         TRISB, 1, ACCESS            ; SCL high
    nop
    nop
    bsf         TRISB, 0, ACCESS            ; SDA high = STOP
    movlw       0x28                        ; I2C master + SSPEN
    movwf       SSPCON1, ACCESS
    return      0

; ---------------------------------------------------------------------------
; DSP Ping (Fix D) — TAS3108 address probe
; ---------------------------------------------------------------------------
dsp_ping:
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    call        wait_sen_bounded, 0x0
    bc          dsp_ping_nack
    movlw       0x68                        ; TAS3108 write addr
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    call        wait_pen_bounded, 0x0
    btfss       SSPCON2, 6, ACCESS          ; ACKSTAT?
    bcf         dsp_fault_flags, 6, BANKED  ; ACK: clear fault
    btfsc       SSPCON2, 6, ACCESS
    bra         dsp_ping_nack
    return      0
dsp_ping_nack:
    bsf         dsp_fault_flags, 6, BANKED  ; NACK: set fault
    return      0

; ---------------------------------------------------------------------------
; Send DSP Fault Status (Fix E) — BF/08 frame to CONTROL
; ---------------------------------------------------------------------------
send_dsp_fault_status:
    movlb       0x00
    movf        dsp_fault_flags, W, BANKED
    andlw       0x44                        ; bits 6 + 2
    movwf       ram_0x00D, ACCESS           ; save in ram_0x00D (uart_tx clobbers ram_0x003)
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x08
    call        uart_tx_byte_blocking, 0x0
    movf        ram_0x00D, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    return      0

; ---------------------------------------------------------------------------
; Volume DSP Write (Fix B + B' + recovery)
; ---------------------------------------------------------------------------
volume_dsp_write:
    movlb       0x0
    bcf         dsp_fault_flags, 2, BANKED  ; clear ACKSTAT latch
    call        i2c_tas3108_coeff_write, 0x0
    btfsc       dsp_fault_flags, 2, BANKED  ; NACKed?
    bra         vol_write_nacked
    ; Success: DSP responded, clear all fault state
    movlb       0x0
    bcf         event_flags, 3, BANKED      ; clear volume dirty
    bsf         event_flags, 7, BANKED      ; boot-complete gate
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    bcf         dsp_fault_flags, 6, BANKED  ; clear DSP fault (write worked)
    movlw       0xC7
    andwf       dsp_fault_flags, F, BANKED  ; clear retry counter, preserve bits 7,6
    call        send_dsp_fault_status, 0x0
    return      0
vol_write_nacked:
    movlw       0x08
    addwf       dsp_fault_flags, F, BANKED  ; bump retry [5:3]
    movf        dsp_fault_flags, W, BANKED
    andlw       0x38
    sublw       0x28                        ; 5 retries?
    bc          vol_retry_ok
    ; Exhausted: bus-clear + ping only if bus is idle (PEN not pending).
    ; If PEN stuck from fault model, skip I2C recovery to avoid corruption.
    btfsc       SSPCON2, 2, ACCESS          ; PEN pending?
    bra         vol_exhausted_skip_i2c
    call        i2c_bus_clear, 0x0
    call        dsp_ping, 0x0
vol_exhausted_skip_i2c:
    bsf         dsp_fault_flags, 6, BANKED  ; flag DSP fault
    call        send_dsp_fault_status, 0x0
    movlb       0x0
    bcf         event_flags, 3, BANKED
    movlw       0xC7
    andwf       dsp_fault_flags, F, BANKED  ; clear retry, preserve bit6 (DSP fault)
    return      0
vol_retry_ok:
    return      0                           ; dirty bit stays: main loop retries

; ---------------------------------------------------------------------------
; Preset Select Handler (V2.4 — cmd=0x20)
; ---------------------------------------------------------------------------
preset_select_handler:
    movf        ram_0x0A3, W, BANKED        ; data byte: 0=A, 1=B
    andlw       0x01
    btfsc       active_flags, 2, ACCESS     ; current preset B?
    xorlw       0x01                        ; invert to compare
    btfsc       STATUS, 2, ACCESS           ; Z = no change
    goto        flow_main_uart_service_1be6_1e6c
    ; Persist outgoing filename if dirty
    btfsc       ram_0x0BD, 5, BANKED        ; filename dirty?
    call        preset_persist_filename, 0x0
    ; Toggle preset
    movlb       0x0                         ; restore BSR after EEPROM ops
    btg         active_flags, 2, ACCESS     ; toggle preset B bit
    ; Reload filename from new EEPROM slot
    call        preset_load_filename, 0x0
    ; Trigger DSP re-apply and cmd03 dirty
    movlb       0x0
    bsf         event_flags, 0, BANKED      ; cmd03 dirty
    bsf         event_flags, 3, BANKED      ; trigger DSP re-apply
    call        main_core_service_4574, 0x0 ; re-apply preset table
    goto        flow_main_uart_service_1be6_1e6c

; --- Persist dirty filename to EEPROM (outgoing preset slot) ---
preset_persist_filename:
    movlw       0x60
    btfsc       active_flags, 2, ACCESS
    movlw       0x83
    movwf       ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    lfsr        FSR2, 0x02C0
    movlw       0x1E
    movwf       ram_0x00A, ACCESS
preset_pf_lp:
    movff       POSTINC2, ram_0x009
    call        main_flash_service_46de, 0x0
    incf        ram_0x007, F, ACCESS
    decfsz      ram_0x00A, F, ACCESS
    bra         preset_pf_lp
    bcf         ram_0x0BD, 5, BANKED
    return      0

; --- Load filename from EEPROM (incoming preset slot) ---
preset_load_filename:
    movlw       0x60
    btfsc       active_flags, 2, ACCESS
    movlw       0x83
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    lfsr        FSR2, 0x02C0
    movlw       0x1E
    movwf       ram_0x00A, ACCESS
preset_lf_lp:
    call        eeprom_read_byte, 0x0
    movwf       POSTINC2
    incf        ram_0x003, F, ACCESS
    decfsz      ram_0x00A, F, ACCESS
    bra         preset_lf_lp
    return      0

; ---------------------------------------------------------------------------
; DSP Preset Table B (clone of Preset A)
; ---------------------------------------------------------------------------
    org 0x4C00
preset_table_b:
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
; Erased Flash Padding to Preset A
; ---------------------------------------------------------------------------
    fill 0xFFFF, (0x5600 - $) / 2

; ---------------------------------------------------------------------------
; DSP Preset Table A (stock, pinned to flash ceiling)
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
; EEPROM Data (V3.1: version updated at offset 0x82)
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
    db  0x03, 0x01, 0x31, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; V3.1 version
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x02  ; ................

    END

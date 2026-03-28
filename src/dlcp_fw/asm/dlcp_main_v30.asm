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
    goto        label_000
    dw          0xFFFF
    dw          0xFFFF
    movff       FSR2L, isr_save_fsr2l
    movff       FSR2H, isr_save_fsr2h
    call        main_isr_dispatch, 0x1
label_000:
    goto        label_494

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

function_000:
    movff       WREG, i2c_coeff_2
    lfsr        FSR2, 0x01ED
    lfsr        FSR1, 0x004D
    movlw       0x07
label_001:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         label_001
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x42
    bnz         label_002
    bra         label_070
label_002:
    movlb       0x0
    clrf        ram_0x0CB, BANKED
    bra         label_070
label_003:
    movff       ram_0x11B, ram_0x097
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x09
    bnz         label_007
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
label_004:
    rcall       function_001
    movf        INDF2, W, ACCESS
    bz          label_005
    rcall       function_001
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x02
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         label_006
label_005:
    rcall       function_002
label_006:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         label_004
label_007:
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x0A
    bnz         label_009
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
label_008:
    rcall       function_002
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         label_008
label_009:
    movlw       0x03
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movff       ram_0x11B, ram_0x0C2
    bsf         ram_0x0BD, 5, BANKED
label_010:
    call        function_112, 0x0
label_011:
    call        function_120, 0x0
label_012:
    call        function_009, 0x0
    bra         label_083
label_013:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         label_017
    movff       ram_0x11C, ram_0x0B7
    bra         label_016
label_014:
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bra         label_011
label_015:
    movff       ram_0x11D, ram_0x0B8
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bsf         ram_0x07F, 0, BANKED
    bsf         ram_0x094, 4, BANKED
    bra         label_011
label_016:
    movlb       0x0
    movf        ram_0x0B7, W, BANKED
    xorlw       0x01
    bz          label_014
    xorlw       0x03
    bz          label_015
    bra         label_083
label_017:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          label_018
    bra         label_083
label_018:
    movff       ram_0x11E, ram_0x0B5
    movlw       0x04
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movlw       0x02
    movwf       ram_0x0C2, BANKED
    movf        ram_0x0B5, W, BANKED
    xorlw       0x06
    bnz         label_022
    movlw       0x05
    movwf       i2c_coeff_3, ACCESS
label_019:
    rcall       function_001
    movf        INDF2, W, ACCESS
    bz          label_020
    rcall       function_001
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x00
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         label_021
label_020:
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
label_021:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x13
    cpfsgt      i2c_coeff_3, ACCESS
    bra         label_019
    movlb       0x0
    bsf         ram_0x0BD, 4, BANKED
    bra         label_010
label_022:
    movf        ram_0x0B5, W, BANKED
    xorlw       0x05
    bz          label_011
    movf        ram_0x0B5, W, BANKED
    xorlw       0x07
    bz          label_011
    bra         label_083
label_023:
    movff       ram_0x11B, input_select
    movff       ram_0x11F, computed_volume_3
    movff       ram_0x120, computed_volume_2
    movff       ram_0x121, computed_volume_1
    movff       ram_0x122, computed_volume
    movlb       0x1
    btfsc       ram_0x023, 0, BANKED
    bra         label_024
    bcf         active_flags, 4, ACCESS
    bra         label_025
label_024:
    bsf         active_flags, 4, ACCESS
label_025:
    movlb       0x1
    btfsc       ram_0x024, 0, BANKED
    bra         label_026
    movlb       0x0
    bcf         ram_0x0A4, 0, BANKED
    bra         label_027
label_026:
    movlb       0x0
    bsf         ram_0x0A4, 0, BANKED
label_027:
    movlb       0x1
    btfsc       ram_0x025, 0, BANKED
    bra         label_028
    movlb       0x0
    bcf         ram_0x0A4, 1, BANKED
    bra         label_029
label_028:
    movlb       0x0
    bsf         ram_0x0A4, 1, BANKED
label_029:
    movlb       0x1
    btfsc       ram_0x026, 0, BANKED
    bra         label_030
    movlb       0x0
    bcf         ram_0x0A4, 2, BANKED
    bra         label_031
label_030:
    movlb       0x0
    bsf         ram_0x0A4, 2, BANKED
label_031:
    movlb       0x1
    btfsc       ram_0x028, 0, BANKED
    bra         label_032
    movlb       0x0
    bcf         ram_0x0A4, 3, BANKED
    bra         label_033
label_032:
    movlb       0x0
    bsf         ram_0x0A4, 3, BANKED
label_033:
    movlb       0x1
    btfsc       ram_0x029, 0, BANKED
    bra         label_034
    movlb       0x0
    bcf         ram_0x0A4, 4, BANKED
    bra         label_035
label_034:
    movlb       0x0
    bsf         ram_0x0A4, 4, BANKED
label_035:
    movlb       0x1
    btfsc       ram_0x02A, 0, BANKED
    bra         label_036
    movlb       0x0
    bcf         ram_0x0A4, 5, BANKED
    bra         label_037
label_036:
    movlb       0x0
    bsf         ram_0x0A4, 5, BANKED
label_037:
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
    bnz         label_038
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         label_038
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         label_038
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
label_038:
    bz          label_039
    bsf         event_flags, 3, BANKED
    bsf         ram_0x094, 1, BANKED
label_039:
    movf        ram_0x0AC, W, BANKED
    xorwf       ram_0x09B, W, BANKED
    bz          label_040
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
label_040:
    movf        ram_0x0AD, W, BANKED
    xorwf       ram_0x09C, W, BANKED
    bz          label_041
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
label_041:
    movf        ram_0x0AE, W, BANKED
    xorwf       ram_0x09D, W, BANKED
    bz          label_042
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
label_042:
    movf        ram_0x0AF, W, BANKED
    xorwf       ram_0x09E, W, BANKED
    bz          label_043
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
label_043:
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x04C, ACCESS
    movlw       0x01
    btfss       active_flags, 5, ACCESS
    movlw       0x00
    xorwf       ram_0x04C, F, ACCESS
    bz          label_044
    bsf         event_flags, 5, BANKED
    bsf         ram_0x094, 3, BANKED
label_044:
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
    bra         label_045
    movf        ram_0x0A6, W, BANKED
    lfsr        FSR2, 0x0061
    cpfseq      INDF2, ACCESS
    bra         label_045
    movf        ram_0x0A7, W, BANKED
    lfsr        FSR2, 0x0062
    cpfseq      INDF2, ACCESS
    bra         label_045
    movf        ram_0x0A8, W, BANKED
    lfsr        FSR2, 0x0063
    cpfseq      INDF2, ACCESS
    bra         label_045
    movf        ram_0x0A9, W, BANKED
    lfsr        FSR2, 0x0064
    cpfseq      INDF2, ACCESS
    bra         label_045
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
label_045:
    bsf         event_flags, 4, BANKED
    movff       input_select, input_select_mirror
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    btfss       active_flags, 4, ACCESS
    bra         label_046
    bsf         active_flags, 5, ACCESS
    bra         label_047
label_046:
    bcf         active_flags, 5, ACCESS
label_047:
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
label_048:
    movlw       0x05
    bra         label_050
label_049:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         label_051
    call        function_122, 0x0
    movlw       0x06
label_050:
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    bra         label_012
label_051:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          label_052
    bra         label_083
label_052:
    call        function_122, 0x0
    bra         label_048
label_053:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    xorlw       0x0F
    btfsc       STATUS, 2, ACCESS
    bsf         active_flags, 7, ACCESS
label_054:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x07
    bnz         label_055
    movlb       0x1
    tstfsz      ram_0x01B, BANKED
    bra         label_055
    movlb       0x0
    clrf        ram_0x0C5, BANKED
    movlw       0x56
    movwf       ram_0x083, BANKED
    movlw       0x00
    clrf        ram_0x082, BANKED
label_055:
    bcf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
    clrf        rx_ring_wr, BANKED
    clrf        rx_ring_rd, BANKED
    call        function_021, 0x0
label_056:
    movff       i2c_coeff_2, ram_0x0C1
    bra         label_012
label_057:
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
label_058:
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
    bra         label_058
    clrf        i2c_coeff_3, ACCESS
label_059:
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
    bra         label_059
    movlb       0x0
    bsf         ram_0x0BD, 0, BANKED
    bsf         ram_0x0BD, 5, BANKED
    bsf         ram_0x0BD, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    bsf         ram_0x0BD, 3, BANKED
    bsf         event_flags, 0, BANKED
    call        function_014, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x00
    clrf        ram_0x009, ACCESS
    call        function_094, 0x0
    call        hard_reset, 0x0
    bra         label_083
label_060:
    movlb       0x0
    tstfsz      ram_0x0CB, BANKED
    bra         label_064
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
    call        function_097, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x9A
    movwf       ram_0x003, ACCESS
    movlw       0x2D
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xD1
    movwf       ram_0x003, ACCESS
    movlw       0x08
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    call        function_107, 0x0
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
    bnc         label_063
    movlw       0x01
    movwf       ram_0x0CB, BANKED
    clrf        i2c_coeff_3, ACCESS
label_061:
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
    bz          label_062
    movlb       0x0
    clrf        ram_0x0CB, BANKED
label_062:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x05
    cpfsgt      i2c_coeff_3, ACCESS
    bra         label_061
    bra         label_064
label_063:
    clrf        ram_0x0CB, BANKED
label_064:
    movlb       0x0
    movf        ram_0x0CB, W, BANKED
    bnz         label_065
    bra         label_056
label_065:
    call        fw_update_relay, 0x0
    bra         label_056
label_066:
    movff       ram_0x11E, i2c_coeff_1
    movff       ram_0x11F, i2c_coeff_0
    movff       i2c_coeff_2, ram_0x0C1
    call        function_009, 0x0
    movf        ram_0x07D, W, BANKED
    xorwf       i2c_coeff_1, W, ACCESS
    bnz         label_067
    movf        ram_0x07C, W, BANKED
    xorwf       i2c_coeff_0, W, ACCESS
label_067:
    bnz         label_068
    call        function_090, 0x0
    movlw       0xAA
    movlb       0x1
    movwf       ram_0x05C, BANKED
    bra         label_083
label_068:
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
    bra         label_083
label_069:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    bra         label_083
label_070:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x01
    bz          label_083
    xorlw       0x03
    bz          label_083
    xorlw       0x01
    bnz         label_071
    bra         label_003
label_071:
    xorlw       0x07
    bnz         label_072
    bra         label_013
label_072:
    xorlw       0x01
    bnz         label_073
    bra         label_023
label_073:
    xorlw       0x03
    bnz         label_074
    bra         label_049
label_074:
    xorlw       0x01
    bnz         label_075
    bra         label_054
label_075:
    xorlw       0x0F
    bnz         label_076
    bra         label_054
label_076:
    xorlw       0x01
    bnz         label_077
    bra         label_054
label_077:
    xorlw       0x03
    bnz         label_078
    bra         label_054
label_078:
    xorlw       0x01
    bnz         label_079
    bra         label_054
label_079:
    xorlw       0x07
    bnz         label_080
    bra         label_053
label_080:
    xorlw       0x4C
    bnz         label_081
    bra         label_057
label_081:
    xorlw       0x01
    bz          label_066
    xorlw       0x03
    bnz         label_082
    bra         label_060
label_082:
    bra         label_069
label_083:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    return      0

function_001:
    movlw       0x1A
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    return      0

function_002:
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    setf        INDF2, ACCESS
    return      0
fw_update_relay:
    lfsr        FSR2, 0x01E5
    lfsr        FSR1, 0x001D
    movlw       0x08
label_084:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         label_084
    movlw       0x02
    movwf       ram_0x049, ACCESS
label_085:
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
    bc          label_090
    movff       ram_0x04A, ram_0x045
    clrf        ram_0x048, ACCESS
label_086:
    btfss       ram_0x07D, 5, BANKED
    bra         label_087
    movlw       0x01
    movwf       ram_0x044, ACCESS
    bra         label_088
label_087:
    clrf        ram_0x044, ACCESS
label_088:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x07C, F, BANKED
    rlcf        ram_0x07D, F, BANKED
    btfsc       ram_0x045, 0, ACCESS
    bsf         ram_0x07C, 0, BANKED
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x045, F, ACCESS
    movf        ram_0x044, W, ACCESS
    bz          label_089
    movlw       0x02
    xorwf       ram_0x07C, F, BANKED
    movlw       0x44
    xorwf       ram_0x07D, F, BANKED
label_089:
    incf        ram_0x048, F, ACCESS
    movlw       0x07
    cpfsgt      ram_0x048, ACCESS
    bra         label_086
label_090:
    movlw       0x40
    subwf       ram_0x084, W, BANKED
    movlw       0x00
    subwfb      ram_0x085, W, BANKED
    bc          label_091
    bra         label_108
label_091:
    movlw       0xC0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bnc         label_092
    bra         label_108
label_092:
    movlw       0x0F
    andwf       ram_0x084, W, BANKED
    movwf       ram_0x08A, BANKED
    clrf        ram_0x08B, BANKED
    iorwf       ram_0x08B, W, BANKED
    bz          label_093
    bra         label_102
label_093:
    movf        ram_0x087, W, BANKED
    iorwf       ram_0x086, W, BANKED
    bnz         label_094
    bra         label_099
label_094:
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
    call        function_073, 0x0
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
label_095:
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
    call        function_059, 0x0
    movlb       0x0
    xorwf       ram_0x080, W, BANKED
    bnz         label_096
    movlw       0x01
    movwf       ram_0x043, ACCESS
    bra         label_098
label_096:
    clrf        ram_0x043, ACCESS
    clrf        ram_0x019, ACCESS
    movlw       0x1D
    movwf       ram_0x018, ACCESS
    call        function_091, 0x0
    movlb       0x0
    movff       ram_0x09F, ram_0x012
    clrf        ram_0x013, ACCESS
    clrf        ram_0x015, ACCESS
    movlw       0x0A
    movwf       ram_0x014, ACCESS
    movlw       0x25
    call        function_065, 0x0
    movwf       ram_0x01B, ACCESS
    clrf        ram_0x019, ACCESS
    movff       ram_0x01B, ram_0x018
    call        function_091, 0x0
    movlw       0x21
    call        uart_tx_byte_blocking, 0x0
    call        function_108, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    movlw       0x19
    movlb       0x0
    subwf       ram_0x09F, W, BANKED
    bc          label_097
    incf        ram_0x09F, F, BANKED
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        function_091, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    call        uart_tx_byte_blocking, 0x0
    bra         label_098
label_097:
    incf        ram_0x09F, F, BANKED
    bra         label_109
label_098:
    movf        ram_0x043, W, ACCESS
    bnz         label_100
    bra         label_095
label_099:
    clrf        ram_0x08E, BANKED
label_100:
    movlw       0xBF
    movlb       0x0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          label_102
    movlw       0x04
    subwf       ram_0x08E, W, BANKED
    bc          label_101
    incf        ram_0x08E, F, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
label_101:
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
    rcall       function_004
    movff       TABLAT, ram_0x19D
    movff       ram_0x087, ram_0x01B
    movlw       0x0F
    rcall       function_004
    movff       TABLAT, ram_0x19E
    movff       ram_0x086, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       function_004
    movff       TABLAT, ram_0x19F
    movff       ram_0x086, ram_0x01B
    movlw       0x0F
    rcall       function_004
    movff       TABLAT, ram_0x1A0
    movlw       0x30
    movwf       ram_0x0A1, BANKED
    movwf       ram_0x0A2, BANKED
    clrf        ram_0x0A3, BANKED
    movlw       0x09
    movwf       ram_0x04B, ACCESS
    call        function_108, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        function_091, 0x0
    movlb       0x0
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
label_102:
    movlw       0xBF
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          label_107
    btfss       ram_0x084, 0, BANKED
    bra         label_105
    movff       ram_0x046, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       function_004
    movff       TABLAT, ram_0x02F
    movff       ram_0x046, ram_0x01B
    movlw       0x0F
    rcall       function_004
    movff       TABLAT, ram_0x030
    movff       ram_0x04A, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    rcall       function_004
    movff       TABLAT, ram_0x031
    movff       ram_0x04A, ram_0x01B
    movlw       0x0F
    rcall       function_004
    movff       TABLAT, ram_0x032
    clrf        ram_0x033, ACCESS
    clrf        ram_0x019, ACCESS
    movlw       0x2F
    movwf       ram_0x018, ACCESS
    call        function_091, 0x0
    clrf        ram_0x047, ACCESS
    bra         label_104
label_103:
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
label_104:
    movf        ram_0x047, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    bnz         label_103
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    clrf        INDF2, ACCESS
    bra         label_106
label_105:
    movff       ram_0x04A, ram_0x046
label_106:
    movf        ram_0x04A, W, ACCESS
    movlb       0x0
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    bra         label_108
label_107:
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
label_108:
    infsnz      ram_0x084, F, BANKED
    incf        ram_0x085, F, BANKED
    incf        ram_0x049, F, ACCESS
    movlw       0x1F
    cpfsgt      ram_0x049, ACCESS
    bra         label_085
label_109:
    return      0

function_004:
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    addlw       LOW(hex_lookup_table)               ; indexed TBLPTR -> hex_lookup_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    tblrd*
    return      0
cmd_dispatch_gated:
    movff       WREG, ram_0x0FD
    btfss       active_flags, 3, ACCESS
    bra         cmd_gate_reject
    btfss       event_flags, 1, BANKED
    bra         label_117
    bsf         event_flags, 3, BANKED
    bra         label_115
label_110:
    movlw       0x09
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x70
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        function_115, 0x0
    bra         label_116
label_111:
    movlw       0x0A
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0xB0
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        function_115, 0x0
    bra         label_116
label_112:
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        function_115, 0x0
    bra         label_116
label_113:
    movlw       0x0B
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0xF0
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        function_115, 0x0
    bra         label_116
label_114:
    call        function_082, 0x0
    call        function_124, 0x0
    bra         label_116
label_115:
    movf        ram_0x093, W, BANKED
    bz          label_114
    xorlw       0x01
    bz          label_110
    xorlw       0x03
    bz          label_111
    xorlw       0x01
    bz          label_112
    xorlw       0x07
    bz          label_113
    xorlw       0x01
    bz          label_114
    xorlw       0x03
    bz          label_114
    xorlw       0x01
    bz          label_114
label_116:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        function_085, 0x0
    movlb       0x0
    bcf         event_flags, 1, BANKED
    bsf         ram_0x0BD, 0, BANKED
    call        function_112, 0x0
label_117:
    movlb       0x0
    btfss       event_flags, 3, BANKED
    bra         label_124
    bcf         active_flags, 4, ACCESS
    bcf         event_flags, 5, BANKED
    bsf         event_flags, 6, BANKED
    clrf        ram_0x0A4, BANKED
    movff       ram_0x0A4, ram_0x0B0
    clrf        ram_0x09A, BANKED
    bra         label_122
label_118:
    movff       ram_0x09B, ram_0x09A
    bra         label_123
label_119:
    movff       ram_0x09C, ram_0x09A
    bra         label_123
label_120:
    movff       ram_0x09D, ram_0x09A
    bra         label_123
label_121:
    movff       ram_0x09E, ram_0x09A
    bra         label_123
label_122:
    movf        ram_0x093, W, BANKED
    bz          label_118
    xorlw       0x05
    bz          label_119
    xorlw       0x03
    bz          label_120
    xorlw       0x01
    bz          label_121
label_123:
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
    call        function_055, 0x0
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
    call        function_017, 0x0
    movff       ram_0x012, ram_0x0ED
    movff       ram_0x013, ram_0x0EE
    movff       ram_0x014, ram_0x0EF
    movff       ram_0x015, ram_0x0F0
    movff       ram_0x0ED, ram_0x02F
    movff       ram_0x0EE, ram_0x030
    movff       ram_0x0EF, ram_0x031
    movff       ram_0x0F0, ram_0x032
    call        function_016, 0x0
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
    call        function_085, 0x0
    movlb       0x0
    bcf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 0, BANKED
    call        function_112, 0x0
label_124:
    btfss       active_flags, 7, ACCESS
    bra         label_125
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    call        function_084, 0x0
    call        function_126, 0x0
    bcf         active_flags, 7, ACCESS
    movlb       0x0
    btfss       event_flags, 5, BANKED
    btfsc       active_flags, 4, ACCESS
    bra         label_125
    bsf         event_flags, 3, BANKED
label_125:
    movlb       0x0
    btfss       event_flags, 5, BANKED
    bra         label_128
    btfss       active_flags, 4, ACCESS
    bra         label_126
    movlw       0x00
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    call        i2c_tas3108_coeff_write, 0x0
    bra         label_127
label_126:
    bsf         event_flags, 3, BANKED
label_127:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        function_085, 0x0
    movlb       0x0
    bcf         event_flags, 5, BANKED
label_128:
    btfss       event_flags, 6, BANKED
    bra         label_141
    btfsc       ram_0x0A4, 0, BANKED
    bra         label_129
    movlw       0x5F
    movwf       ram_0x0F2, BANKED
    movlw       0x1C
    bra         label_130
label_129:
    movlw       0x5F
    movwf       ram_0x0F2, BANKED
    movlw       0x08
label_130:
    movwf       ram_0x0F1, BANKED
    movff       ram_0x0F1, ram_0x013
    movff       ram_0x0F2, ram_0x014
    call        function_043, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 1, BANKED
    bra         label_131
    movlw       0x5F
    movwf       ram_0x0F4, BANKED
    movlw       0x44
    bra         label_132
label_131:
    movlw       0x5F
    movwf       ram_0x0F4, BANKED
    movlw       0x30
label_132:
    movwf       ram_0x0F3, BANKED
    movff       ram_0x0F3, ram_0x013
    movff       ram_0x0F4, ram_0x014
    call        function_043, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 2, BANKED
    bra         label_133
    movlw       0x5F
    movwf       ram_0x0F6, BANKED
    movlw       0x6C
    bra         label_134
label_133:
    movlw       0x5F
    movwf       ram_0x0F6, BANKED
    movlw       0x58
label_134:
    movwf       ram_0x0F5, BANKED
    movff       ram_0x0F5, ram_0x013
    movff       ram_0x0F6, ram_0x014
    call        function_043, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 3, BANKED
    bra         label_135
    movlw       0x5F
    movwf       ram_0x0F8, BANKED
    movlw       0x94
    bra         label_136
label_135:
    movlw       0x5F
    movwf       ram_0x0F8, BANKED
    movlw       0x80
label_136:
    movwf       ram_0x0F7, BANKED
    movff       ram_0x0F7, ram_0x013
    movff       ram_0x0F8, ram_0x014
    call        function_043, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 4, BANKED
    bra         label_137
    movlw       0x5F
    movwf       ram_0x0FA, BANKED
    movlw       0xBC
    bra         label_138
label_137:
    movlw       0x5F
    movwf       ram_0x0FA, BANKED
    movlw       0xA8
label_138:
    movwf       ram_0x0F9, BANKED
    movff       ram_0x0F9, ram_0x013
    movff       ram_0x0FA, ram_0x014
    call        function_043, 0x0
    movlb       0x0
    btfsc       ram_0x0A4, 5, BANKED
    bra         label_139
    movlw       0x5F
    movwf       ram_0x0FC, BANKED
    movlw       0xE4
    bra         label_140
label_139:
    movlw       0x5F
    movwf       ram_0x0FC, BANKED
    movlw       0xD0
label_140:
    movwf       ram_0x0FB, BANKED
    movff       ram_0x0FB, ram_0x013
    movff       ram_0x0FC, ram_0x014
    call        function_043, 0x0
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        function_085, 0x0
    movlb       0x0
    bcf         event_flags, 6, BANKED
label_141:
    btfss       event_flags, 4, BANKED
    bra         label_142
    call        function_008, 0x0
    movlb       0x0
    bcf         event_flags, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    movlw       0x05
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        function_085, 0x0
    call        function_112, 0x0
label_142:
    movlb       0x0
    btfss       ram_0x07F, 0, BANKED
    bra         label_143
    bcf         ram_0x07F, 0, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        function_112, 0x0
label_143:
    movlb       0x0
    btfss       ram_0x07F, 1, BANKED
    bra         cmd_gate_reject
    bcf         ram_0x07F, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        function_112, 0x0
cmd_gate_reject:
    return      0

function_006:
    clrf        ram_0x009, ACCESS
    bra         label_191
label_145:
    call        function_109, 0x0
    iorlw       0x00
    bnz         label_146
    bra         label_192
label_146:
    call        rx_ring_read, 0x0
    movwf       ram_0x00A, ACCESS
    movlw       0x7F
    cpfsgt      ram_0x00A, ACCESS
    bra         label_150
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB0
    bnz         label_147
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
label_147:
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB1
    bnz         label_148
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bsf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
label_148:
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
    bra         label_193
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    bra         label_193
label_150:
    btfsc       active_flags, 0, ACCESS
    bra         label_151
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          label_151
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
label_151:
    movlb       0x0
    movf        rx_frame_position, W, BANKED
    btfss       STATUS, 2, ACCESS
    incf        rx_frame_position, F, BANKED
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          label_152
    bra         label_193
label_152:
    movf        rx_frame_position, W, BANKED
    xorlw       0x02
    bnz         label_153
    movff       ram_0x00A, ram_0x0A2
    bra         label_193
label_153:
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
    bra         label_190
standby_request_handler:
    btfss       active_flags, 3, ACCESS
    bra         label_156
    bsf         event_flags, 2, BANKED
    bra         label_157
label_156:
    movlb       0x0
    bcf         event_flags, 2, BANKED
label_157:
    btfsc       event_flags, 2, BANKED
    bcf         active_flags, 3, ACCESS
    bra         label_190
cmd03_mute_on_handler:
    btfsc       ram_0x094, 3, BANKED
    bra         label_165
    bsf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         label_159
    movlw       0x01
    bra         label_160
label_159:
    movlw       0x00
label_160:
    xorwf       ram_0x005, F, ACCESS
    btfss       STATUS, 2, ACCESS
label_161:
    bsf         event_flags, 5, BANKED
label_162:
    btfss       active_flags, 4, ACCESS
    bra         label_163
    bsf         active_flags, 5, ACCESS
    bra         label_164
label_163:
    bcf         active_flags, 5, ACCESS
label_164:
    bra         label_190
label_165:
    movlw       0x02
    btfss       active_flags, 4, ACCESS
    movlw       0x03
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 3, BANKED
    bra         label_190
cmd03_mute_off_handler:
    btfsc       ram_0x094, 3, BANKED
    bra         label_165
    bcf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         label_159
    movlw       0x01
    xorwf       ram_0x005, F, ACCESS
    bnz         label_161
    bra         label_162
cmd03_subdispatch:
    movf        ram_0x0A3, W, BANKED
    bz          standby_request_handler
    xorlw       0x01
    bz          wake_request_handler
    xorlw       0x03
    bz          cmd03_mute_on_handler
    xorlw       0x01
    bz          cmd03_mute_off_handler
    bra         label_190
cmd04_status_response:
    call        send_status_burst, 0x0
    bra         label_190
cmd06_input_select_handler:
    btfsc       ram_0x094, 0, BANKED
    bra         label_170
    movff       ram_0x0A3, input_select
    movff       input_select, input_select_mirror
    bra         label_190
label_170:
    movff       input_select, ram_0x0BC
    bcf         ram_0x094, 0, BANKED
    bra         label_190
volume_cmd_handler:
    btfsc       ram_0x094, 1, BANKED
    bra         label_174
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
    bnz         label_172
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         label_172
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         label_172
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
label_172:
    bnz         label_173
    bra         label_190
label_173:
    bsf         event_flags, 3, BANKED
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    bra         label_190
label_174:
    movf        computed_volume, W, BANKED
    addlw       0x60
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 1, BANKED
    bra         label_190
label_175:
    movf        ram_0x0A3, W, BANKED
    xorlw       0x29
    bnz         label_190
    call        report_cmd29_status, 0x0
    bra         label_190
label_176:
    movff       ram_0x0A3, ram_0x060
    movf        ram_0x0A5, W, BANKED
    xorwf       ram_0x060, W, BANKED
    bz          label_190
    bsf         event_flags, 4, BANKED
    movff       ram_0x060, ram_0x0A5
    bra         label_190
label_177:
    movff       ram_0x0A3, ram_0x061
    movf        ram_0x061, W, BANKED
    xorwf       ram_0x0A6, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x061, ram_0x0A6
    bra         label_190
label_178:
    movff       ram_0x0A3, ram_0x062
    movf        ram_0x062, W, BANKED
    xorwf       ram_0x0A7, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x062, ram_0x0A7
    bra         label_190
label_179:
    movff       ram_0x0A3, ram_0x063
    movf        ram_0x063, W, BANKED
    xorwf       ram_0x0A8, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x063, ram_0x0A8
    bra         label_190
label_180:
    movff       ram_0x0A3, ram_0x064
    movf        ram_0x064, W, BANKED
    xorwf       ram_0x0A9, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x064, ram_0x0A9
    bra         label_190
label_181:
    movff       ram_0x0A3, ram_0x065
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x065, ram_0x0AA
    bra         label_190
label_182:
    btfsc       ram_0x094, 4, BANKED
    bra         label_183
    movf        ram_0x0B8, W, BANKED
    xorwf       ram_0x0A3, W, BANKED
    bz          label_190
    movff       ram_0x0A3, ram_0x0B8
    bsf         ram_0x07F, 0, BANKED
    bra         label_190
label_183:
    movff       ram_0x0B8, ram_0x0BC
    bcf         ram_0x094, 4, BANKED
    bra         label_190
label_184:
    movff       ram_0x0A3, ram_0x0C3
    movf        ram_0x0B2, W, BANKED
    xorwf       ram_0x0C3, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x0BD, 0, BANKED
    movff       ram_0x0C3, ram_0x0B2
    bra         label_190
cmd_dispatch_xor_chain:
    movf        ram_0x0A2, W, BANKED
    xorlw       0x03
    bnz         label_186
    bra         cmd03_subdispatch
label_186:
    xorlw       0x07
    bnz         label_187
    bra         cmd04_status_response
label_187:
    xorlw       0x02
    bnz         label_188
    bra         cmd06_input_select_handler
label_188:
    xorlw       0x01
    bnz         label_189
    bra         volume_cmd_handler
label_189:
    xorlw       0x17
    bz          label_175
    xorlw       0x07
    bz          label_176
    xorlw       0x0F
    bz          label_177
    xorlw       0x01
    bz          label_178
    xorlw       0x03
    bz          label_179
    xorlw       0x01
    bz          label_180
    xorlw       0x07
    bz          label_181
    xorlw       0x01
    bz          label_182
    xorlw       0x03
    bz          label_184
label_190:
    btfss       active_flags, 6, ACCESS
    bra         label_193
    movlb       0x0
    movf        ram_0x0BC, W, BANKED
    call        uart_tx_byte_blocking, 0x0
label_191:
    bcf         active_flags, 6, ACCESS
    bra         label_193
label_192:
    movlw       0x01
    movwf       ram_0x009, ACCESS
label_193:
    movf        ram_0x009, W, ACCESS
    btfss       STATUS, 2, ACCESS
    return      0
    bra         label_145

function_007:
    movlw       0x00
    clrf        ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       computed_volume_3, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       computed_volume_2, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x02
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       computed_volume_1, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x03
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       computed_volume, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x04
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       input_select, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x07
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x060, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x08
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x061, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x09
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x062, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0A
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x063, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0B
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x064, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0C
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x065, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0D
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movwf       ram_0x05F, ACCESS
    clrf        ram_0x004, ACCESS
    movlw       0x14
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x0C3, BANKED
    movf        computed_volume_3, W, BANKED
    xorlw       0x80
    addlw       0x80
    bnz         label_194
    movlw       0x00
    subwf       computed_volume_2, W, BANKED
    bnz         label_194
    movlw       0x00
    subwf       computed_volume_1, W, BANKED
    bnz         label_194
    movlw       0x13
    subwf       computed_volume, W, BANKED
label_194:
    bnc         label_195
    movlw       0xA0
    movwf       computed_volume, BANKED
    setf        computed_volume_1, BANKED
    setf        computed_volume_2, BANKED
    setf        computed_volume_3, BANKED
label_195:
    movlw       0x08
    cpfsgt      input_select, BANKED
    bra         label_196
    movlw       0x01
    movwf       input_select, BANKED
label_196:
    movlw       0x03
    cpfsgt      ram_0x060, BANKED
    bra         label_197
    clrf        ram_0x060, BANKED
label_197:
    lfsr        FSR2, 0x0061
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         label_198
    clrf        ram_0x061, BANKED
label_198:
    lfsr        FSR2, 0x0062
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         label_199
    clrf        ram_0x062, BANKED
label_199:
    lfsr        FSR2, 0x0063
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         label_200
    movlw       0x01
    movwf       ram_0x063, BANKED
label_200:
    lfsr        FSR2, 0x0064
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         label_201
    movlw       0x01
    movwf       ram_0x064, BANKED
label_201:
    lfsr        FSR2, 0x0065
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         label_202
    movlw       0x01
    movwf       ram_0x064, BANKED
label_202:
    movlw       0x03
    cpfsgt      ram_0x05F, ACCESS
    bra         label_203
    movwf       ram_0x05F, ACCESS
label_203:
    movlw       0x04
    cpfsgt      ram_0x0C3, BANKED
    bra         label_204
    movlw       0x01
    movwf       ram_0x0C3, BANKED
label_204:
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
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x0B4, BANKED
    incf        ram_0x0B4, W, BANKED
    btfsc       STATUS, 2, ACCESS
    bcf         ram_0x0B4, 0, BANKED
    movff       ram_0x0B4, ram_0x0B1
    clrf        ram_0x004, ACCESS
    movlw       0x0E
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x0B8, BANKED
    movlw       0x03
    subwf       ram_0x0B8, W, BANKED
    bc          label_205
    movlw       0x03
    movwf       ram_0x0B8, BANKED
label_205:
    movlw       0x04
    cpfsgt      ram_0x0B8, BANKED
    bra         label_206
    movlw       0x03
    movwf       ram_0x0B8, BANKED
label_206:
    clrf        ram_0x004, ACCESS
    movlw       0x10
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x09B, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x11
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x09C, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x12
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x09D, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x13
    movwf       ram_0x003, ACCESS
    call        function_110, 0x0
    movlb       0x0
    movwf       ram_0x09E, BANKED
    movlw       0x12
    cpfsgt      ram_0x09B, BANKED
    bra         label_207
    clrf        ram_0x09B, BANKED
label_207:
    movlw       0x12
    cpfsgt      ram_0x09C, BANKED
    bra         label_208
    clrf        ram_0x09C, BANKED
label_208:
    movlw       0x12
    cpfsgt      ram_0x09D, BANKED
    bra         label_209
    clrf        ram_0x09D, BANKED
label_209:
    movlw       0x12
    cpfsgt      ram_0x09E, BANKED
    bra         label_210
    clrf        ram_0x09E, BANKED
label_210:
    movff       ram_0x09B, ram_0x0AC
    movff       ram_0x09C, ram_0x0AD
    movff       ram_0x09D, ram_0x0AE
    movff       ram_0x09E, ram_0x0AF
    movlw       0x50
    movwf       ram_0x00A, ACCESS
label_211:
    movlb       0x1
    movlw       0xB0
    addwf       ram_0x00A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    addwfc      FSR2H, F, ACCESS
    movff       ram_0x00A, ram_0x003
    clrf        ram_0x004, ACCESS
    call        function_110, 0x0
    movwf       INDF2, ACCESS
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         label_211
    movlw       0x60
    movwf       ram_0x00A, ACCESS
label_212:
    movlb       0x2
    movlw       0x60
    addwf       ram_0x00A, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    addwfc      FSR2H, F, ACCESS
    movff       ram_0x00A, ram_0x003
    clrf        ram_0x004, ACCESS
    call        function_110, 0x0
    movwf       INDF2, ACCESS
    incf        ram_0x00A, F, ACCESS
    movlw       0x7D
    cpfsgt      ram_0x00A, ACCESS
    bra         label_212
    clrf        ram_0x008, ACCESS
    movlw       0x80
    movwf       ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x81
    movwf       ram_0x007, ACCESS
    movlw       0x03
    movwf       ram_0x009, ACCESS
    goto        function_094

function_008:
    clrf        ram_0x004, ACCESS
    movlw       0xD7
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDB
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDF
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xD9
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xE3
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xDD
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0xE1
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    call        function_097, 0x0
    call        i2c_wait_bus_idle, 0x0
    clrf        ram_0x059, ACCESS
label_213:
    movf        ram_0x059, W, ACCESS
    movlb       0x0
    addlw       0x60
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        function_078, 0x0
    bra         label_220
label_214:
    movff       ram_0x0A0, ram_0x0D7
    movff       ram_0x0B9, ram_0x0D8
    bra         label_221
label_215:
    movff       ram_0x0A0, ram_0x0DB
    movff       ram_0x0B9, ram_0x0DC
    bra         label_221
label_216:
    movff       ram_0x0A0, ram_0x0DF
    movff       ram_0x0B9, ram_0x0E0
    bra         label_221
label_217:
    movff       ram_0x0A0, ram_0x1D9
    movff       ram_0x0B9, ram_0x1DA
    bra         label_221
label_218:
    movff       ram_0x0A0, ram_0x0E4
    movff       ram_0x0B9, ram_0x0E5
    bra         label_221
label_219:
    movff       ram_0x0A0, ram_0x1E0
    movff       ram_0x0B9, ram_0x1E1
    bra         label_221
label_220:
    movf        ram_0x059, W, ACCESS
    bz          label_214
    xorlw       0x01
    bz          label_215
    xorlw       0x03
    bz          label_216
    xorlw       0x01
    bz          label_217
    xorlw       0x07
    bz          label_218
    xorlw       0x01
    bz          label_219
label_221:
    incf        ram_0x059, F, ACCESS
    movlw       0x05
    cpfsgt      ram_0x059, ACCESS
    bra         label_213
    clrf        ram_0x05A, ACCESS
    bra         label_229
label_222:
    movff       ram_0x0D7, ram_0x06A
    movff       ram_0x0D8, ram_0x06B
    movff       ram_0x0D9, ram_0x06C
    movff       ram_0x0DA, ram_0x06D
    bra         label_230
label_223:
    movff       ram_0x0DB, ram_0x06A
    movff       ram_0x0DC, ram_0x06B
    movff       ram_0x0DD, ram_0x06C
    movff       ram_0x0DE, ram_0x06D
    bra         label_230
label_224:
    movff       ram_0x0DF, ram_0x06A
    movff       ram_0x0E0, ram_0x06B
    movff       ram_0x0E1, ram_0x06C
    movff       ram_0x0E2, ram_0x06D
    bra         label_230
label_225:
    movff       ram_0x1D9, ram_0x06A
    movff       ram_0x1DA, ram_0x06B
    movff       ram_0x1DB, ram_0x06C
    movff       ram_0x1DC, ram_0x06D
    bra         label_230
label_226:
    movff       ram_0x0E3, ram_0x06A
    movff       ram_0x0E4, ram_0x06B
    movff       ram_0x0E5, ram_0x06C
    movff       ram_0x0E6, ram_0x06D
    bra         label_230
label_227:
    movff       ram_0x1DD, ram_0x06A
    movff       ram_0x1DE, ram_0x06B
    movff       ram_0x1DF, ram_0x06C
    movff       ram_0x1E0, ram_0x06D
    bra         label_230
label_228:
    movff       ram_0x1E1, ram_0x06A
    movff       ram_0x1E2, ram_0x06B
    movff       ram_0x1E3, ram_0x06C
    movff       ram_0x1E4, ram_0x06D
    bra         label_230
label_229:
    movf        ram_0x05A, W, ACCESS
    bz          label_222
    xorlw       0x01
    bz          label_223
    xorlw       0x03
    bz          label_224
    xorlw       0x01
    bz          label_225
    xorlw       0x07
    bz          label_226
    xorlw       0x01
    bz          label_227
    xorlw       0x03
    bz          label_228
label_230:
    bsf         SSPCON2, 0, ACCESS
label_231:
    btfsc       SSPCON2, 0, ACCESS
    bra         label_231
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
label_232:
    movf        ram_0x05B, W, ACCESS
    movlb       0x0
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    cpfseq      INDF2, ACCESS
    bra         label_233
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    movlw       0x3F
    bra         label_234
label_233:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x03
    cpfseq      INDF2, ACCESS
    bra         label_235
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    movlw       0x80
    movwf       i2c_coeff_2, ACCESS
    movlw       0xBF
label_234:
    movwf       i2c_coeff_3, ACCESS
    bra         label_236
label_235:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        function_086, 0x0
    movff       ram_0x00D, i2c_coeff_0
    movff       ram_0x00E, i2c_coeff_1
    movff       ram_0x00F, i2c_coeff_2
    movff       ram_0x010, i2c_coeff_3
label_236:
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        function_046, 0x0
    incf        ram_0x05B, F, ACCESS
    movlw       0x03
    cpfsgt      ram_0x05B, ACCESS
    bra         label_232
    bsf         SSPCON2, 2, ACCESS
label_237:
    btfsc       SSPCON2, 2, ACCESS
    bra         label_237
    incf        ram_0x05A, F, ACCESS
    movlw       0x06
    cpfsgt      ram_0x05A, ACCESS
    bra         label_229
    retlw       0x06

function_009:
    movff       ram_0x0C1, ram_0x15A
    bra         label_248
label_238:
    movff       ram_0x0C2, ram_0x15B
    movlw       0x02
    movwf       ram_0x003, ACCESS
label_239:
    movlw       0xBE
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    rcall       function_010
    movlw       0x1F
    cpfsgt      ram_0x003, ACCESS
    bra         label_239
    bra         label_252
label_240:
    movff       ram_0x0C2, ram_0x15B
    decf        ram_0x0C2, W, BANKED
    bnz         label_241
    movff       ram_0x0B7, ram_0x15C
    movff       ram_0x0B8, ram_0x15D
    bra         label_252
label_241:
    movf        ram_0x0C2, W, BANKED
    xorlw       0x02
    bz          label_242
    bra         label_252
label_242:
    movff       ram_0x0B5, ram_0x15E
    movlw       0x05
    movwf       ram_0x003, ACCESS
label_243:
    movlw       0xFB
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    rcall       function_010
    movlw       0x13
    cpfsgt      ram_0x003, ACCESS
    bra         label_243
    bra         label_252
label_244:
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
    bra         label_252
label_245:
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
    bra         label_252
label_246:
    movff       ram_0x11B, ram_0x15B
    bra         label_252
label_247:
    movlb       0x1
    clrf        ram_0x05B, BANKED
    clrf        ram_0x05C, BANKED
    clrf        ram_0x05D, BANKED
    clrf        active_flags, BANKED
    bra         label_252
label_248:
    movlb       0x0
    movf        ram_0x0C1, W, BANKED
    xorlw       0x03
    bnz         label_249
    bra         label_238
label_249:
    xorlw       0x07
    bnz         label_250
    bra         label_240
label_250:
    xorlw       0x01
    bnz         label_251
    bra         label_244
label_251:
    xorlw       0x03
    bz          label_245
    xorlw       0x01
    bz          label_246
    xorlw       0x0F
    bz          label_246
    xorlw       0x01
    bz          label_246
    xorlw       0x03
    bz          label_246
    xorlw       0x01
    bz          label_246
    xorlw       0x07
    bz          label_246
    bra         label_247
label_252:
    movlb       0x0
    clrf        ram_0x0C1, BANKED
    return      0

function_010:
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

function_011:
    movff       ram_0x020, ram_0x028
    movff       ram_0x021, ram_0x029
    movff       ram_0x022, ram_0x02A
    movff       ram_0x023, ram_0x02B
    movlw       0x18
    bra         label_254
label_253:
    rcall       function_013
label_254:
    decfsz      WREG, F, ACCESS
    bra         label_253
    movf        ram_0x028, W, ACCESS
    movwf       ram_0x02E, ACCESS
    movff       ram_0x024, ram_0x028
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movlw       0x18
    bra         label_256
label_255:
    rcall       function_013
label_256:
    decfsz      WREG, F, ACCESS
    bra         label_255
    movf        ram_0x028, W, ACCESS
    movwf       ram_0x02D, ACCESS
    movf        ram_0x02E, W, ACCESS
    bz          label_257
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    bc          label_258
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         label_258
label_257:
    movff       ram_0x024, ram_0x020
    movff       ram_0x025, ram_0x021
    movff       ram_0x026, ram_0x022
    movff       ram_0x027, ram_0x023
    bra         label_272
label_258:
    movf        ram_0x02D, W, ACCESS
    bz          label_259
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          label_260
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         label_260
label_259:
    movff       ram_0x020, ram_0x020
    movff       ram_0x021, ram_0x021
    movff       ram_0x022, ram_0x022
    movff       ram_0x023, ram_0x023
    bra         label_272
label_260:
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
    bc          label_264
label_261:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x024, F, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    decf        ram_0x02D, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          label_263
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          label_263
    bra         label_261
label_262:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x023, F, ACCESS
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    incf        ram_0x02E, F, ACCESS
label_263:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         label_262
    bra         label_268
label_264:
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          label_268
label_265:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x020, F, ACCESS
    rlcf        ram_0x021, F, ACCESS
    rlcf        ram_0x022, F, ACCESS
    rlcf        ram_0x023, F, ACCESS
    decf        ram_0x02E, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          label_267
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          label_267
    bra         label_265
label_266:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    rrcf        ram_0x024, F, ACCESS
    incf        ram_0x02D, F, ACCESS
label_267:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         label_266
label_268:
    btfss       ram_0x02C, 7, ACCESS
    bra         label_269
    comf        ram_0x020, F, ACCESS
    comf        ram_0x021, F, ACCESS
    comf        ram_0x022, F, ACCESS
    comf        ram_0x023, F, ACCESS
    incf        ram_0x020, F, ACCESS
    movlw       0x00
    addwfc      ram_0x021, F, ACCESS
    addwfc      ram_0x022, F, ACCESS
    addwfc      ram_0x023, F, ACCESS
label_269:
    btfss       ram_0x02C, 6, ACCESS
    bra         label_270
    comf        ram_0x024, F, ACCESS
    rcall       function_012
label_270:
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
    bra         label_271
    comf        ram_0x024, F, ACCESS
    rcall       function_012
    movlw       0x01
    movwf       ram_0x02C, ACCESS
label_271:
    movff       ram_0x024, ram_0x003
    movff       ram_0x025, ram_0x004
    movff       ram_0x026, ram_0x005
    movff       ram_0x027, ram_0x006
    movff       ram_0x02E, ram_0x007
    movff       ram_0x02C, ram_0x008
    call        function_029, 0x0
    movff       ram_0x003, ram_0x020
    movff       ram_0x004, ram_0x021
    movff       ram_0x005, ram_0x022
    movff       ram_0x006, ram_0x023
label_272:
    return      0

function_012:
    comf        ram_0x025, F, ACCESS
    comf        ram_0x026, F, ACCESS
    comf        ram_0x027, F, ACCESS
    incf        ram_0x024, F, ACCESS
    movlw       0x00
    addwfc      ram_0x025, F, ACCESS
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    retlw       0x00

function_013:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x02B, F, ACCESS
    rrcf        ram_0x02A, F, ACCESS
    rrcf        ram_0x029, F, ACCESS
    rrcf        ram_0x028, F, ACCESS
    return      0

function_014:
    movlb       0x0
    btfss       event_flags, 0, BANKED
    bra         label_281
    btfss       ram_0x0BD, 0, BANKED
    bra         label_273
    clrf        ram_0x008, ACCESS
    movlw       0x03
    movwf       ram_0x007, ACCESS
    movff       computed_volume, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x02
    movwf       ram_0x007, ACCESS
    movff       computed_volume_1, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x01
    movwf       ram_0x007, ACCESS
    movff       computed_volume_2, ram_0x009
    call        function_094, 0x0
    movlw       0x00
    clrf        ram_0x008, ACCESS
    clrf        ram_0x007, ACCESS
    movff       computed_volume_3, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x04
    movwf       ram_0x007, ACCESS
    movff       input_select, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0D
    movwf       ram_0x007, ACCESS
    movff       ram_0x05F, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x14
    movwf       ram_0x007, ACCESS
    movff       ram_0x0C3, ram_0x009
    call        function_094, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 0, BANKED
label_273:
    btfss       ram_0x0BD, 1, BANKED
    bra         label_274
    clrf        ram_0x008, ACCESS
    movlw       0x07
    movwf       ram_0x007, ACCESS
    movff       ram_0x060, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x08
    movwf       ram_0x007, ACCESS
    movff       ram_0x061, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x09
    movwf       ram_0x007, ACCESS
    movff       ram_0x062, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0A
    movwf       ram_0x007, ACCESS
    movff       ram_0x063, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0B
    movwf       ram_0x007, ACCESS
    movff       ram_0x064, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0C
    movwf       ram_0x007, ACCESS
    movff       ram_0x065, ram_0x009
    call        function_094, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 1, BANKED
label_274:
    btfss       ram_0x0BD, 2, BANKED
    bra         label_275
    clrf        ram_0x008, ACCESS
    movlw       0x0F
    movwf       ram_0x007, ACCESS
    movff       ram_0x0B4, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x0E
    movwf       ram_0x007, ACCESS
    movff       ram_0x0B8, ram_0x009
    call        function_094, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 2, BANKED
label_275:
    btfss       ram_0x0BD, 3, BANKED
    bra         label_276
    clrf        ram_0x008, ACCESS
    movlw       0x10
    movwf       ram_0x007, ACCESS
    movff       ram_0x09B, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x11
    movwf       ram_0x007, ACCESS
    movff       ram_0x09C, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x12
    movwf       ram_0x007, ACCESS
    movff       ram_0x09D, ram_0x009
    call        function_094, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x13
    movwf       ram_0x007, ACCESS
    movff       ram_0x09E, ram_0x009
    call        function_094, 0x0
    movlb       0x0
    bcf         ram_0x0BD, 3, BANKED
label_276:
    btfss       ram_0x0BD, 4, BANKED
    bra         label_278
    movlw       0x50
    movwf       ram_0x00A, ACCESS
label_277:
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
    call        function_094, 0x0
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         label_277
    movlb       0x0
    bcf         ram_0x0BD, 4, BANKED
label_278:
    btfss       ram_0x0BD, 5, BANKED
    bra         label_280
    movlw       0x60
    movwf       ram_0x00A, ACCESS
label_279:
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
    call        function_094, 0x0
    incf        ram_0x00A, F, ACCESS
    movlw       0x7D
    cpfsgt      ram_0x00A, ACCESS
    bra         label_279
    movlb       0x0
    bcf         ram_0x0BD, 5, BANKED
label_280:
    bcf         event_flags, 0, BANKED
label_281:
    return      0

function_015:
    btfss       active_flags, 3, ACCESS
    bra         label_313
    movlw       0x64
    movlb       0x0
    cpfsgt      ram_0x0BB, BANKED
    bra         label_312
    clrf        ram_0x0BB, BANKED
    bra         label_300
label_282:
    movf        ram_0x0B6, W, BANKED
    addlw       0x08
    movwf       ram_0x0BE, BANKED
    bra         label_301
label_283:
    clrf        ram_0x093, BANKED
    bra         label_301
label_284:
    movlw       0x01
    movwf       ram_0x093, BANKED
    movf        ram_0x05F, W, ACCESS
    bz          label_301
    movlw       0x05
    bra         label_299
label_285:
    movlw       0x02
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         label_286
    movlw       0x01
    movwf       ram_0x093, BANKED
label_286:
    movlw       0x01
    cpfsgt      ram_0x05F, ACCESS
    bra         label_301
    movlw       0x06
    bra         label_299
label_287:
    movlw       0x03
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         label_288
    movlw       0x02
    movwf       ram_0x093, BANKED
label_288:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         label_289
    movlw       0x01
    movwf       ram_0x093, BANKED
label_289:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         label_301
    movlw       0x07
    bra         label_299
label_290:
    movlw       0x04
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         label_291
    movlw       0x03
    movwf       ram_0x093, BANKED
label_291:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         label_292
    movlw       0x02
    movwf       ram_0x093, BANKED
label_292:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         label_301
    movlw       0x01
    bra         label_299
label_293:
    decf        ram_0x05F, W, ACCESS
    bnz         label_294
    movlw       0x04
    movwf       ram_0x093, BANKED
label_294:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         label_295
    movlw       0x03
    movwf       ram_0x093, BANKED
label_295:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         label_301
    movlw       0x02
    bra         label_299
label_296:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         label_297
    movlw       0x04
    movwf       ram_0x093, BANKED
label_297:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         label_301
    movlw       0x03
    bra         label_299
label_298:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         label_301
    movlw       0x04
label_299:
    movwf       ram_0x093, BANKED
    bra         label_301
label_300:
    movf        input_select, W, BANKED
    bz          label_282
    xorlw       0x01
    bz          label_283
    xorlw       0x03
    bz          label_284
    xorlw       0x01
    bz          label_285
    xorlw       0x07
    bz          label_287
    xorlw       0x01
    bz          label_290
    xorlw       0x03
    bz          label_293
    xorlw       0x01
    bz          label_296
    xorlw       0x0F
    bz          label_298
label_301:
    tstfsz      input_select, BANKED
    bra         label_302
    movff       ram_0x0BE, ram_0x006
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x13
    call        i2c_secondary_dev_random_read, 0x0
    movlb       0x0
    movwf       ram_0x0BE, BANKED
    tstfsz      ram_0x0BE, BANKED
    bra         label_304
    clrf        ram_0x093, BANKED
    movlw       0x0A
    cpfsgt      ram_0x0BA, BANKED
    bra         label_303
    clrf        ram_0x0BA, BANKED
    movlw       0x04
    subwf       ram_0x0B6, W, BANKED
    btfss       STATUS, 0, ACCESS
    incf        ram_0x0B6, F, BANKED
    movf        ram_0x0B6, W, BANKED
    xorlw       0x04
    bnz         label_310
label_302:
    clrf        ram_0x0B6, BANKED
    bra         label_310
label_303:
    incf        ram_0x0BA, F, BANKED
    bra         label_310
label_304:
    tstfsz      ram_0x0B6, BANKED
    bra         label_305
    movlw       0x03
    movwf       ram_0x093, BANKED
label_305:
    decf        ram_0x0B6, W, BANKED
    bnz         label_306
    movlw       0x01
    movwf       ram_0x093, BANKED
label_306:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x02
    bnz         label_307
    movlw       0x02
    movwf       ram_0x093, BANKED
label_307:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x03
    bnz         label_308
    movlw       0x04
    movwf       ram_0x093, BANKED
label_308:
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
    bra         label_309
    bsf         active_flags, 5, ACCESS
    bra         label_310
label_309:
    bcf         active_flags, 5, ACCESS
label_310:
    movlb       0x0
    movf        ram_0x093, W, BANKED
    xorlw       0x02
    btfsc       STATUS, 2, ACCESS
    btfsc       PORTC, 0, ACCESS
    bra         label_311
    movff       ram_0x0C3, ram_0x093
label_311:
    movf        ram_0x0AB, W, BANKED
    xorwf       ram_0x093, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 1, BANKED
    movff       ram_0x093, ram_0x0AB
    bra         label_313
label_312:
    incf        ram_0x0BB, F, BANKED
label_313:
    return      0

function_016:
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
    call        function_022, 0x0
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
    call        function_011, 0x0
    movff       ram_0x020, ram_0x02F
    movff       ram_0x021, ram_0x030
    movff       ram_0x022, ram_0x031
    movff       ram_0x023, ram_0x032
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        function_057, 0x0
    movff       ram_0x02F, ram_0x02F
    movff       ram_0x030, ram_0x030
    movff       ram_0x031, ram_0x031
    movff       ram_0x032, ram_0x032
    return      0

function_017:
    movff       ram_0x012, ram_0x01A
    movff       ram_0x013, ram_0x01B
    movff       ram_0x014, ram_0x01C
    movff       ram_0x015, ram_0x01D
    movlw       0x18
    bra         label_315
label_314:
    rcall       function_020
label_315:
    decfsz      WREG, F, ACCESS
    bra         label_314
    movf        ram_0x01A, W, ACCESS
    movwf       ram_0x01E, ACCESS
    tstfsz      ram_0x01E, ACCESS
    bra         label_316
    bra         label_319
label_316:
    movff       ram_0x016, ram_0x01A
    movff       ram_0x017, ram_0x01B
    movff       ram_0x018, ram_0x01C
    movff       ram_0x019, ram_0x01D
    movlw       0x18
    bra         label_318
label_317:
    rcall       function_020
label_318:
    decfsz      WREG, F, ACCESS
    bra         label_317
    movf        ram_0x01A, W, ACCESS
    movwf       ram_0x024, ACCESS
    tstfsz      ram_0x024, ACCESS
    bra         label_320
label_319:
    clrf        ram_0x012, ACCESS
    clrf        ram_0x013, ACCESS
    clrf        ram_0x014, ACCESS
    clrf        ram_0x015, ACCESS
    bra         label_325
label_320:
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
label_321:
    btfss       ram_0x012, 0, ACCESS
    bra         label_322
    movf        ram_0x016, W, ACCESS
    rcall       function_018
label_322:
    rcall       function_019
    rlcf        ram_0x016, F, ACCESS
    rlcf        ram_0x017, F, ACCESS
    rlcf        ram_0x018, F, ACCESS
    rlcf        ram_0x019, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         label_321
    movlw       0x11
    movwf       ram_0x023, ACCESS
label_323:
    btfss       ram_0x012, 0, ACCESS
    bra         label_324
    movf        ram_0x016, W, ACCESS
    rcall       function_018
label_324:
    rcall       function_019
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    rrcf        ram_0x01F, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         label_323
    movff       ram_0x01F, ram_0x003
    movff       ram_0x020, ram_0x004
    movff       ram_0x021, ram_0x005
    movff       ram_0x022, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x024, ram_0x008
    call        function_029, 0x0
    movff       ram_0x003, ram_0x012
    movff       ram_0x004, ram_0x013
    movff       ram_0x005, ram_0x014
    movff       ram_0x006, ram_0x015
label_325:
    return      0

function_018:
    addwf       ram_0x01F, F, ACCESS
    movf        ram_0x017, W, ACCESS
    addwfc      ram_0x020, F, ACCESS
    movf        ram_0x018, W, ACCESS
    addwfc      ram_0x021, F, ACCESS
    movf        ram_0x019, W, ACCESS
    addwfc      ram_0x022, F, ACCESS
    return      0

function_019:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x015, F, ACCESS
    rrcf        ram_0x014, F, ACCESS
    rrcf        ram_0x013, F, ACCESS
    rrcf        ram_0x012, F, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0

function_020:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x01D, F, ACCESS
    rrcf        ram_0x01C, F, ACCESS
    rrcf        ram_0x01B, F, ACCESS
    rrcf        ram_0x01A, F, ACCESS
    return      0

function_021:
    tstfsz      ram_0x0C5, BANKED
    bra         label_326
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
label_326:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    bz          label_327
    clrf        ram_0x01D, ACCESS
    movlw       0x02
    movwf       ram_0x01C, ACCESS
    bra         label_328
label_327:
    clrf        ram_0x01C, ACCESS
    clrf        ram_0x01D, ACCESS
label_328:
    movff       ram_0x01C, ram_0x01E
    movlw       0x04
    movwf       ram_0x01F, ACCESS
label_329:
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
    bra         label_329
    movlw       0x18
    addwf       ram_0x0C5, F, BANKED
    movlw       0xBF
    cpfsgt      ram_0x0C5, BANKED
    bra         label_330
    clrf        ram_0x0C5, BANKED
    movlw       0x3F
    subwf       ram_0x082, W, BANKED
    movlw       0x5F
    subwfb      ram_0x083, W, BANKED
    bc          label_330
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
label_330:
    return      0

function_022:
    movff       ram_0x00D, ram_0x015
    movff       ram_0x00E, ram_0x016
    movff       ram_0x00F, ram_0x017
    movff       ram_0x010, ram_0x018
    movlw       0x18
    bra         label_332
label_331:
    rcall       function_023
label_332:
    decfsz      WREG, F, ACCESS
    bra         label_331
    movf        ram_0x015, W, ACCESS
    movwf       ram_0x01E, ACCESS
    tstfsz      ram_0x01E, ACCESS
    bra         label_333
    bra         label_336
label_333:
    movff       ram_0x011, ram_0x015
    movff       ram_0x012, ram_0x016
    movff       ram_0x013, ram_0x017
    movff       ram_0x014, ram_0x018
    movlw       0x18
    bra         label_335
label_334:
    rcall       function_023
label_335:
    decfsz      WREG, F, ACCESS
    bra         label_334
    movf        ram_0x015, W, ACCESS
    movwf       ram_0x01F, ACCESS
    tstfsz      ram_0x01F, ACCESS
    bra         label_337
label_336:
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x010, ACCESS
    bra         label_340
label_337:
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
label_338:
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
    bnc         label_339
    movf        ram_0x011, W, ACCESS
    subwf       ram_0x00D, F, ACCESS
    movf        ram_0x012, W, ACCESS
    subwfb      ram_0x00E, F, ACCESS
    movf        ram_0x013, W, ACCESS
    subwfb      ram_0x00F, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwfb      ram_0x010, F, ACCESS
    bsf         ram_0x019, 0, ACCESS
label_339:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x00D, F, ACCESS
    rlcf        ram_0x00E, F, ACCESS
    rlcf        ram_0x00F, F, ACCESS
    rlcf        ram_0x010, F, ACCESS
    decfsz      ram_0x01D, F, ACCESS
    bra         label_338
    movff       ram_0x019, ram_0x003
    movff       ram_0x01A, ram_0x004
    movff       ram_0x01B, ram_0x005
    movff       ram_0x01C, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x01F, ram_0x008
    call        function_029, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
label_340:
    return      0

function_023:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x018, F, ACCESS
    rrcf        ram_0x017, F, ACCESS
    rrcf        ram_0x016, F, ACCESS
    rrcf        ram_0x015, F, ACCESS
    return      0
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
    bra         label_342
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
label_342:
    movlw       0x36
    movlb       0x0
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bnc         adc_boot_gate_loop
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
    call        function_128, 0x0
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
    call        function_084, 0x0
    bsf         LATB, 3, ACCESS
    call        function_122, 0x0
    call        function_031, 0x0
    call        function_122, 0x0
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
    goto        label_610
flash_write:
    clrf        ram_0x010, ACCESS
    movff       ram_0x003, ram_0x014
    movff       ram_0x004, ram_0x015
    movff       ram_0x005, ram_0x016
    movff       ram_0x006, ram_0x017
    movlw       0x05
    movwf       ram_0x00B, ACCESS
label_343:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    decfsz      ram_0x00B, F, ACCESS
    bra         label_343
    movlw       0x05
label_344:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    decfsz      WREG, F, ACCESS
    bra         label_344
    movlw       0x20
    addwf       ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movwf       ram_0x00F, ACCESS
    bra         label_351
label_345:
    movff       ram_0x016, ram_0x013
    movff       ram_0x015, ram_0x012
    movff       ram_0x014, ram_0x011
    bra         label_347
label_346:
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
    bz          label_348
label_347:
    decf        ram_0x00F, F, ACCESS
    incf        ram_0x00F, W, ACCESS
    bnz         label_346
label_348:
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
    bra         label_349
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x010, ACCESS
label_349:
    call        function_076, 0x0
    bcf         EECON1, 2, ACCESS
    movf        ram_0x010, W, ACCESS
    bz          label_350
    bsf         INTCON, 7, ACCESS
    clrf        ram_0x010, ACCESS
label_350:
    movlw       0x20
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00C, W, ACCESS
    movwf       ram_0x014, ACCESS
    movf        ram_0x00D, W, ACCESS
    movwf       ram_0x015, ACCESS
    movf        ram_0x00E, W, ACCESS
    movwf       ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
label_351:
    movf        ram_0x008, W, ACCESS
    iorwf       ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         label_345

function_026:
    call        function_098, 0x0
    tstfsz      ram_0x0CD, BANKED
    bra         label_352
    bra         label_360
label_352:
    btfsc       UIR, 2, ACCESS
    call        function_106, 0x0
    btfsc       UCON, 1, ACCESS
    bra         label_360
    btfsc       UIR, 0, ACCESS
    call        function_063, 0x0
    btfsc       UIR, 4, ACCESS
    call        function_096, 0x0
    movlw       0x03
    movlb       0x0
    subwf       ram_0x0CD, W, BANKED
    bnc         label_360
    clrf        ram_0x0C4, BANKED
label_353:
    btfss       UIR, 3, ACCESS
    bra         label_360
    movf        USTAT, W, ACCESS
    movff       USTAT, ram_0x006
    movlw       0x7C
    andwf       ram_0x006, F, ACCESS
    bnz         label_357
    btfsc       USTAT, 1, ACCESS
    bra         label_354
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
    movlw       0x00
    bra         label_355
label_354:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
label_355:
    movlb       0x0
    movwf       ram_0x07A, BANKED
    bcf         UIR, 3, ACCESS
    movff       ram_0x07A, FSR2L
    movff       ram_0x07B, FSR2H
    rrcf        INDF2, W, ACCESS
    rrcf        WREG, F, ACCESS
    andlw       0x0F
    xorlw       0x0D
    bnz         label_359
    clrf        ram_0x090, BANKED
label_356:
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
    bra         label_356
    call        function_070, 0x0
    bra         label_359
label_357:
    movf        USTAT, W, ACCESS
    xorlw       0x04
    bnz         label_358
    bcf         UIR, 3, ACCESS
    call        function_077, 0x0
    bra         label_359
label_358:
    bcf         UIR, 3, ACCESS
label_359:
    movlb       0x0
    incf        ram_0x0C4, F, BANKED
    movlw       0x03
    cpfsgt      ram_0x0C4, BANKED
    bra         label_353
label_360:
    return      0

function_027:
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movff       ram_0x028, ram_0x02C
    movlw       0x18
    bra         label_362
label_361:
    rcall       function_028
label_362:
    decfsz      WREG, F, ACCESS
    bra         label_361
    movf        ram_0x029, W, ACCESS
    movwf       ram_0x02E, ACCESS
    tstfsz      ram_0x02E, ACCESS
    bra         label_364
label_363:
    clrf        ram_0x025, ACCESS
    clrf        ram_0x026, ACCESS
    clrf        ram_0x027, ACCESS
    clrf        ram_0x028, ACCESS
    bra         label_373
label_364:
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movff       ram_0x028, ram_0x02C
    movlw       0x20
    bra         label_366
label_365:
    rcall       function_028
label_366:
    decfsz      WREG, F, ACCESS
    bra         label_365
    movf        ram_0x029, W, ACCESS
    movwf       ram_0x02D, ACCESS
    bsf         ram_0x027, 7, ACCESS
    clrf        ram_0x028, ACCESS
    movlw       0x96
    subwf       ram_0x02E, F, ACCESS
    btfss       ram_0x02E, 7, ACCESS
    bra         label_368
    movf        ram_0x02E, W, ACCESS
    xorlw       0x80
    movwf       ram_0x029, ACCESS
    movlw       0xE9
    xorlw       0x80
    subwf       ram_0x029, W, ACCESS
    bnc         label_363
label_367:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x028, F, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    incfsz      ram_0x02E, F, ACCESS
    bra         label_367
    bra         label_371
label_368:
    movlw       0x1F
    cpfsgt      ram_0x02E, ACCESS
    bra         label_370
    bra         label_363
label_369:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    rlcf        ram_0x028, F, ACCESS
    decf        ram_0x02E, F, ACCESS
label_370:
    tstfsz      ram_0x02E, ACCESS
    bra         label_369
label_371:
    movf        ram_0x02D, W, ACCESS
    bz          label_372
    comf        ram_0x028, F, ACCESS
    comf        ram_0x027, F, ACCESS
    comf        ram_0x026, F, ACCESS
    negf        ram_0x025, ACCESS
    movlw       0x00
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    addwfc      ram_0x028, F, ACCESS
label_372:
    movff       ram_0x025, ram_0x025
    movff       ram_0x026, ram_0x026
    movff       ram_0x027, ram_0x027
    movff       ram_0x028, ram_0x028
label_373:
    return      0

function_028:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x02C, F, ACCESS
    rrcf        ram_0x02B, F, ACCESS
    rrcf        ram_0x02A, F, ACCESS
    rrcf        ram_0x029, F, ACCESS
    return      0

function_029:
    movf        ram_0x007, W, ACCESS
    bz          label_374
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    iorwf       ram_0x004, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         label_376
label_374:
    clrf        ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    bra         label_382
label_375:
    incf        ram_0x007, F, ACCESS
    rcall       function_030
label_376:
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
    bz          label_378
    bra         label_375
label_377:
    incf        ram_0x007, F, ACCESS
    incf        ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    rcall       function_030
label_378:
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    movf        ram_0x006, W, ACCESS
    movwf       ram_0x00C, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    iorwf       ram_0x00B, W, ACCESS
    bz          label_380
    bra         label_377
label_379:
    decf        ram_0x007, F, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
label_380:
    btfss       ram_0x005, 7, ACCESS
    bra         label_379
    btfsc       ram_0x007, 0, ACCESS
    bra         label_381
    movlw       0x7F
    andwf       ram_0x005, F, ACCESS
label_381:
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
label_382:
    return      0

function_030:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    return      0
label_383:
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         label_399
    movf        ram_0x0D3, W, BANKED
    bnz         label_399
    movf        ram_0x0D0, W, BANKED
    xorlw       0x06
    bz          label_388
    bra         label_390
label_384:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x3E
    movwf       ram_0x075, BANKED
    clrf        ram_0x0E8, BANKED
    movlw       0x09
    bra         label_387
label_385:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    decf        ram_0x0EB, W, BANKED
    bnz         label_386
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x55
    movwf       ram_0x075, BANKED
label_386:
    decf        ram_0x0EB, W, BANKED
    bnz         label_389
    clrf        ram_0x0E8, BANKED
    movlw       0x1D
label_387:
    movwf       ram_0x0E7, BANKED
    bra         label_389
label_388:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x21
    bz          label_384
    xorlw       0x03
    bz          label_385
    xorlw       0x01
label_389:
    bsf         ram_0x0CE, 1, BANKED
label_390:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         label_399
    bra         label_398
label_391:
    call        function_131, 0x0
    bra         label_399
label_392:
    call        function_130, 0x0
    bra         label_399
label_393:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEA
label_394:
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         label_399
label_395:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D2, ram_0x0EA
    bra         label_399
label_396:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xE9
    bra         label_394
label_397:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D1, ram_0x0E9
    bra         label_399
label_398:
    movf        ram_0x0D0, W, BANKED
    xorlw       0x01
    bz          label_391
    xorlw       0x03
    bz          label_393
    xorlw       0x01
    bz          label_396
    xorlw       0x0A
    bz          label_392
    xorlw       0x03
    bz          label_395
    xorlw       0x01
    bz          label_397
label_399:
    return      0
label_400:
    tstfsz      ram_0x0C8, BANKED
    bra         label_402
    movlw       0x04
    movlb       0x4
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         label_401
    movlw       0x01
    call        function_062, 0x0
    clrf        ram_0x096, BANKED
    bra         label_409
label_401:
    movlw       0x00
    call        function_062, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    bra         label_409
label_402:
    btfss       ram_0x0CF, 7, BANKED
    bra         label_404
    movlw       0x01
    movwf       ram_0x0C9, BANKED
    movf        ram_0x0E7, W, BANKED
    subwf       ram_0x0D5, W, BANKED
    movf        ram_0x0E8, W, BANKED
    subwfb      ram_0x0D6, W, BANKED
    bc          label_403
    movff       ram_0x0D5, ram_0x0E7
    movff       ram_0x0D6, ram_0x0E8
label_403:
    call        function_036, 0x0
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x01
    call        function_062, 0x0
    movlw       0x00
    call        function_062, 0x0
    movlb       0x4
    movlw       0x04
    movwf       ram_0x00B, BANKED
    movlw       0x24
    movwf       ram_0x00A, BANKED
    bra         label_408
label_404:
    movlw       0x02
    movwf       ram_0x0C9, BANKED
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         label_405
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
label_405:
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         label_406
    movlw       0x01
    call        function_062, 0x0
    clrf        ram_0x096, BANKED
    bra         label_407
label_406:
    movlw       0x00
    call        function_062, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
label_407:
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         label_409
    movlb       0x4
    clrf        ram_0x009, BANKED
label_408:
    movlw       0x48
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
label_409:
    return      0

function_031:
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

function_032:
    movff       ram_0x02F, ram_0x003
    movff       ram_0x030, ram_0x004
    movff       ram_0x031, ram_0x005
    movff       ram_0x032, ram_0x006
    movlw       0x37
    movwf       ram_0x007, ACCESS
    call        function_053, 0x0
    movf        ram_0x038, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       ram_0x037, W, ACCESS
    bc          label_410
    clrf        ram_0x02F, ACCESS
    clrf        ram_0x030, ACCESS
    clrf        ram_0x031, ACCESS
    clrf        ram_0x032, ACCESS
    bra         label_412
label_410:
    movlw       0x1D
    subwf       ram_0x037, W, ACCESS
    movlw       0x00
    subwfb      ram_0x038, W, ACCESS
    bnc         label_411
    movff       ram_0x02F, ram_0x02F
    movff       ram_0x030, ram_0x030
    movff       ram_0x031, ram_0x031
    movff       ram_0x032, ram_0x032
    bra         label_412
label_411:
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    call        function_027, 0x0
    movff       ram_0x025, ram_0x00D
    movff       ram_0x026, ram_0x00E
    movff       ram_0x027, ram_0x00F
    movff       ram_0x028, ram_0x010
    call        function_055, 0x0
    movff       ram_0x00D, ram_0x033
    movff       ram_0x00E, ram_0x034
    movff       ram_0x00F, ram_0x035
    movff       ram_0x010, ram_0x036
    movff       ram_0x033, ram_0x02F
    movff       ram_0x034, ram_0x030
    movff       ram_0x035, ram_0x031
    movff       ram_0x036, ram_0x032
label_412:
    return      0

function_033:
    decf        ram_0x0D1, W, BANKED
    bnz         label_414
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bnz         label_414
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D0, W, BANKED
    xorlw       0x03
    bnz         label_413
    bsf         ram_0x0CE, 0, BANKED
    bra         label_414
label_413:
    bcf         ram_0x0CE, 0, BANKED
label_414:
    tstfsz      ram_0x0D1, BANKED
    bra         label_418
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    xorlw       0x02
    bnz         label_418
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    bz          label_418
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
    bnz         label_415
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x04
    bra         label_417
label_415:
    btfss       ram_0x0D3, 7, BANKED
    bra         label_416
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x40
    movwf       INDF2, ACCESS
    bra         label_418
label_416:
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x08
label_417:
    movwf       INDF2, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x00
    bsf         PLUSW2, 7, ACCESS
label_418:
    return      0

function_034:
    movff       WREG, ram_0x011
    movff       ram_0x00A, ram_0x00E
    movff       ram_0x00B, ram_0x00F
label_419:
    movff       ram_0x00E, ram_0x003
    movff       ram_0x00F, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        function_064, 0x0
    movff       ram_0x003, ram_0x00E
    movff       ram_0x004, ram_0x00F
    incf        ram_0x011, F, ACCESS
    movf        ram_0x00F, W, ACCESS
    iorwf       ram_0x00E, W, ACCESS
    bnz         label_419
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    clrf        INDF2, ACCESS
    decf        ram_0x011, F, ACCESS
label_420:
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        function_068, 0x0
    movf        ram_0x003, W, ACCESS
    movwf       ram_0x010, ACCESS
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        function_064, 0x0
    movff       ram_0x003, ram_0x00A
    movff       ram_0x004, ram_0x00B
    movlw       0x09
    cpfsgt      ram_0x010, ACCESS
    bra         label_421
    movlw       0x07
    addwf       ram_0x010, F, ACCESS
label_421:
    movlw       0x30
    addwf       ram_0x010, F, ACCESS
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x010, INDF2
    decf        ram_0x011, F, ACCESS
    movf        ram_0x00B, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    bnz         label_420
    incf        ram_0x011, F, ACCESS
    return      0

function_035:
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
    call        function_110, 0x0
    xorlw       0x77
    bz          label_422
    clrf        ram_0x004, ACCESS
    movlw       0xFF
    setf        ram_0x003, ACCESS
    call        function_110, 0x0
    xorlw       0x88
    bz          label_422
    movlb       0x0
    clrf        ram_0x0FE, BANKED
label_422:
    movlb       0x0
    movf        ram_0x0FE, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        flash_write_with_gie_off, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        function_094, 0x0
    bsf         PORTB, 6, ACCESS
    call        adaptive_baud_select, 0x0
    movlw       0x03
    movwf       ram_0x004, ACCESS
    movlw       0xE8
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    call        function_007, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         active_flags, 3, ACCESS
    goto        adc_boot_gate

function_036:
    movlw       0x08
    movwf       ram_0x08F, BANKED
    subwf       ram_0x0E7, W, BANKED
    movlw       0x00
    subwfb      ram_0x0E8, W, BANKED
    bc          label_425
    movff       ram_0x0E7, ram_0x08F
    tstfsz      ram_0x0CC, BANKED
    bra         label_423
    movlw       0x01
    bra         label_424
label_423:
    decf        ram_0x0CC, W, BANKED
    bnz         label_425
    movlw       0x02
label_424:
    movwf       ram_0x0CC, BANKED
label_425:
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
    bra         label_429
    bra         label_433
label_426:
    rcall       function_037
    cpfsgt      TBLPTRH, ACCESS
    bra         label_427
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         label_428
label_427:
    call        function_042, 0x0
label_428:
    rcall       function_038
label_429:
    tstfsz      ram_0x08F, BANKED
    bra         label_426
    bra         label_434
label_430:
    rcall       function_037
    cpfsgt      TBLPTRH, ACCESS
    bra         label_431
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         label_432
label_431:
    call        function_042, 0x0
label_432:
    rcall       function_038
label_433:
    tstfsz      ram_0x08F, BANKED
    bra         label_430
label_434:
    return      0

function_037:
    movff       ram_0x075, TBLPTRL
    movff       ram_0x076, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x07
    return      0

function_038:
    movwf       INDF2, ACCESS
    movlb       0x0
    infsnz      ram_0x072, F, BANKED
    incf        ram_0x073, F, BANKED
    infsnz      ram_0x075, F, BANKED
    incf        ram_0x076, F, BANKED
    decf        ram_0x08F, F, BANKED
    return      0

function_039:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    bnz         label_445
    bra         label_444
label_435:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x04
    movwf       ram_0x0CD, BANKED
    bra         label_445
label_436:
    call        function_041, 0x0
    bra         label_445
label_437:
    call        function_066, 0x0
    bra         label_445
label_438:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEB
    movwf       ram_0x075, BANKED
label_439:
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         label_445
label_440:
    call        function_040, 0x0
    bra         label_445
label_441:
    call        function_033, 0x0
    bra         label_445
label_442:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       ram_0x005, ACCESS
    clrf        ram_0x076, BANKED
    movff       ram_0x005, ram_0x075
    bra         label_439
label_443:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x0D1, INDF2
    bra         label_445
label_444:
    movf        ram_0x0D0, W, BANKED
    bz          label_440
    xorlw       0x01
    bz          label_441
    xorlw       0x02
    bz          label_441
    xorlw       0x06
    bz          label_435
    xorlw       0x03
    bz          label_436
    xorlw       0x01
    bz          label_445
    xorlw       0x0F
    bz          label_438
    xorlw       0x01
    bz          label_437
    xorlw       0x03
    bz          label_442
    xorlw       0x01
    bz          label_443
    xorlw       0x07
label_445:
    return      0

function_040:
    movlb       0x4
    clrf        ram_0x024, BANKED
    clrf        ram_0x025, BANKED
    bra         label_449
label_446:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    btfss       ram_0x0CE, 0, BANKED
    bra         label_450
    movlb       0x4
    bsf         ram_0x024, 1, BANKED
    bra         label_450
label_447:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    bra         label_450
label_448:
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
    bra         label_450
    movlw       0x01
    movlb       0x4
    movwf       ram_0x024, BANKED
    bra         label_450
label_449:
    movlb       0x0
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bz          label_446
    xorlw       0x01
    bz          label_447
    xorlw       0x03
    bz          label_448
label_450:
    movlb       0x0
    decf        ram_0x0C8, W, BANKED
    bnz         label_451
    movlw       0x04
    movwf       ram_0x076, BANKED
    movlw       0x24
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x02
    movwf       ram_0x0E7, BANKED
label_451:
    return      0

function_041:
    movf        ram_0x0CF, W, BANKED
    xorlw       0x80
    bz          label_458
    bra         label_460
label_452:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x88
    movwf       ram_0x075, BANKED
    movlw       0x12
    bra         label_454
label_453:
    tstfsz      ram_0x0D1, BANKED
    bra         label_459
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x2C
    movwf       ram_0x075, BANKED
    movlw       0x00
    movwf       ram_0x0E8, BANKED
    movlw       0x29
label_454:
    movwf       ram_0x0E7, BANKED
    bra         label_459
label_455:
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
    bra         label_456
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         label_457
label_456:
    rcall       function_042
label_457:
    movlb       0x0
    movwf       ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bra         label_459
label_458:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x01
    bz          label_452
    xorlw       0x03
    bz          label_453
    xorlw       0x01
    bz          label_455
label_459:
    bsf         ram_0x0CE, 1, BANKED
label_460:
    return      0

function_042:
    movff       TBLPTRL, FSR1L
    movff       TBLPTRH, FSR1H
    movf        INDF1, W, ACCESS
    return      0

function_043:
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
    bc          label_465
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
label_461:
    btfsc       SSPCON2, 0, ACCESS
    bra         label_461
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movf        ram_0x02F, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        ram_0x030, ACCESS
    bra         label_463
label_462:
    movf        ram_0x030, W, ACCESS
    addlw       0x17
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    call        i2c_byte_tx, 0x0
    incf        ram_0x030, F, ACCESS
label_463:
    movf        ram_0x031, W, ACCESS
    subwf       ram_0x030, W, ACCESS
    bnc         label_462
    bsf         SSPCON2, 2, ACCESS
label_464:
    btfsc       SSPCON2, 2, ACCESS
    bra         label_464
label_465:
    return      0

function_044:
    movff       ram_0x041, ram_0x039
    movff       ram_0x042, ram_0x03A
    movff       ram_0x043, ram_0x03B
    movff       ram_0x044, ram_0x03C
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    call        function_032, 0x0
    movff       ram_0x02F, ram_0x03D
    movff       ram_0x030, ram_0x03E
    movff       ram_0x031, ram_0x03F
    movff       ram_0x032, ram_0x040
    call        function_071, 0x0
    movff       ram_0x039, ram_0x045
    movff       ram_0x03A, ram_0x046
    movff       ram_0x03B, ram_0x047
    movff       ram_0x03C, ram_0x048
    movff       ram_0x045, ram_0x02F
    movff       ram_0x046, ram_0x030
    movff       ram_0x047, ram_0x031
    movff       ram_0x048, ram_0x032
    movlw       0x41
    call        function_058, 0x0
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    call        function_032, 0x0
    movff       ram_0x02F, ram_0x041
    movff       ram_0x030, ram_0x042
    movff       ram_0x031, ram_0x043
    movff       ram_0x032, ram_0x044
    return      0
adaptive_baud_select:
    btfss       PORTC, 2, ACCESS
    bra         label_466
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         label_467
label_466:
    bcf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
label_467:
    bcf         LATB, 4, ACCESS
    bcf         LATB, 5, ACCESS
    bcf         LATB, 3, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bcf         LATB, 7, ACCESS
    call        function_121, 0x0
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

function_046:
    clrf        ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
    clrf        ram_0x018, ACCESS
    movlw       0x4B
    movwf       ram_0x019, ACCESS
    movff       ram_0x049, ram_0x012
    movff       ram_0x04A, ram_0x013
    movff       ram_0x04B, ram_0x014
    movff       ram_0x04C, ram_0x015
    call        function_017, 0x0
    movff       ram_0x012, ram_0x041
    movff       ram_0x013, ram_0x042
    movff       ram_0x014, ram_0x043
    movff       ram_0x015, ram_0x044
    call        function_044, 0x0
    movff       ram_0x041, ram_0x04D
    movff       ram_0x042, ram_0x04E
    movff       ram_0x043, ram_0x04F
    movff       ram_0x044, ram_0x050
    movff       ram_0x04D, ram_0x025
    movff       ram_0x04E, ram_0x026
    movff       ram_0x04F, ram_0x027
    movff       ram_0x050, ram_0x028
    call        function_027, 0x0
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

function_047:
    movlb       0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         label_468
    btfss       active_flags, 3, ACCESS
    bra         label_468
    btfsc       PORTC, 0, ACCESS
    bra         label_469
label_468:
    call        function_126, 0x0
    bra         label_472
label_469:
    tstfsz      ram_0x0C0, BANKED
    bra         label_471
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         label_472
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x1A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        function_052, 0x0
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0C0, BANKED
    clrf        ram_0x059, ACCESS
label_470:
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
    bra         label_470
    bra         label_472
label_471:
    movlb       0x1
    movf        ram_0x01A, W, BANKED
    call        function_000, 0x0
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         label_472
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        function_060, 0x0
    movlb       0x0
    clrf        ram_0x0C0, BANKED
label_472:
    return      0
uart_rx_with_framing:
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x00B, ACCESS
    movff       ram_0x005, ram_0x003
    movff       ram_0x006, ram_0x004
    call        function_099, 0x0
label_473:
    call        function_109, 0x0
    iorlw       0x00
    bz          label_477
    movff       ram_0x00F, ram_0x00A
    call        rx_ring_read, 0x0
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          label_474
    movf        ram_0x00E, W, ACCESS
    addwf       ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x008, W, ACCESS
    movwf       FSR2H, ACCESS
    movff       ram_0x00F, INDF2
    incf        ram_0x00E, F, ACCESS
    bra         label_475
label_474:
    movf        ram_0x00F, W, ACCESS
    xorlw       0x3A
    bnz         label_475
    movlw       0x01
    movwf       ram_0x00D, ACCESS
label_475:
    clrf        ram_0x00C, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          label_476
    movf        ram_0x00A, W, ACCESS
    xorlw       0x0D
    bnz         label_476
    movf        ram_0x00F, W, ACCESS
    xorlw       0x0A
    bnz         label_476
    movlw       0x01
    movwf       ram_0x00C, ACCESS
label_476:
    movff       ram_0x00C, ram_0x00B
label_477:
    call        function_118, 0x0
    bc          label_478
    movf        ram_0x009, W, ACCESS
    subwf       ram_0x00E, W, ACCESS
    bc          label_478
    movf        ram_0x00B, W, ACCESS
    bz          label_473
label_478:
    call        function_123, 0x0
    movf        ram_0x00E, W, ACCESS
    return      0
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
    bz          label_481
    decf        ram_0x08C, F, BANKED
    btfss       STATUS, 0, ACCESS
    decf        ram_0x08D, F, BANKED
    bra         uart_rx_irq_enqueue
label_481:
    bcf         T3CON, 0, ACCESS
    bcf         PIE2, 1, ACCESS
uart_rx_irq_enqueue:
    btfss       PIR1, 5, ACCESS
    bra         label_484
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
    bra         label_484
    bcf         RCSTA, 4, ACCESS
    dw          0xF000
    bsf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
label_484:
    movff       isr_save_fsr2h, FSR2H
    movff       isr_save_fsr2l, FSR2L
    retfie      1
send_status_burst:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x05
    call        uart_tx_byte_blocking, 0x0
    movf        ram_0x05F, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
    call        function_120, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x07
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        computed_volume, W, BANKED
    addlw       0x60
    call        uart_tx_byte_blocking, 0x0
    call        function_120, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x03
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    btfss       active_flags, 3, ACCESS
    movlw       0x00
    call        uart_tx_byte_blocking, 0x0
    call        function_120, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x06
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        input_select, W, BANKED
    call        uart_tx_byte_blocking, 0x0
    call        function_120, 0x0
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x1D
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    movf        ram_0x0B8, W, BANKED
    goto        uart_tx_byte_blocking
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
    bra         label_485
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         label_486
label_485:
    bcf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
label_486:
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
    bc          label_488
    clrf        ram_0x008, ACCESS
    clrf        ram_0x009, ACCESS
label_487:
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
    bra         label_487
label_488:
    bcf         LATB, 3, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    goto        usb_shutdown

function_052:
    movlb       0x0
    clrf        ram_0x0CA, BANKED
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         label_491
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x00D, W, BANKED
    btfss       STATUS, 0, ACCESS
    movff       ram_0x40D, ram_0x005
    movlb       0x0
    clrf        ram_0x0CA, BANKED
    bra         label_490
label_489:
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
label_490:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x0CA, W, BANKED
    bnc         label_489
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
label_491:
    return      0

function_053:
    lfsr        FSR2, 0x0003
    movf        POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    bnz         label_492
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    movwf       POSTINC2, ACCESS
    movwf       POSTDEC2, ACCESS
    bra         label_493
label_492:
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
label_493:
    return      0
label_494:
    lfsr        FSR0, 0x0300
    movlw       0xC0
label_495:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         label_495
    lfsr        FSR0, 0x0200
    movlw       0xDE
label_496:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         label_496
    lfsr        FSR0, 0x0100
    movlw       0xE5
label_497:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         label_497
    lfsr        FSR0, 0x0060
    movlw       0x8D
label_498:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         label_498
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
label_499:
    tblrd*+
    movff       TABLAT, POSTINC0
    movf        POSTDEC1, W, ACCESS
    movf        FSR1L, W, ACCESS
    bnz         label_499
    movlw       UPPER(0x0000)                       ; clear TBLPTRU to program space
    movwf       TBLPTRU, ACCESS
    movlb       0x0
    goto        label_606
flash_erase:
    clrf        ram_0x00B, ACCESS
    movff       ram_0x003, ram_0x00C
    movff       ram_0x004, ram_0x00D
    movff       ram_0x005, ram_0x00E
    movff       ram_0x006, ram_0x00F
    bra         label_502
label_500:
    movff       ram_0x00E, TBLPTRU
    movff       ram_0x00D, TBLPTRH
    movff       ram_0x00C, TBLPTRL
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    bsf         EECON1, 4, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         label_501
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x00B, ACCESS
label_501:
    call        function_076, 0x0
    movf        ram_0x00B, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         INTCON, 7, ACCESS
    movlw       0x40
    addwf       ram_0x00C, F, ACCESS
    movlw       0x00
    addwfc      ram_0x00D, F, ACCESS
    addwfc      ram_0x00E, F, ACCESS
    addwfc      ram_0x00F, F, ACCESS
label_502:
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
    bra         label_500

function_055:
    clrf        ram_0x011, ACCESS
    movf        ram_0x010, W, ACCESS
    xorlw       0x80
    addlw       0x80
    bnz         label_503
    movlw       0x00
    subwf       ram_0x00F, W, ACCESS
    bnz         label_503
    movlw       0x00
    subwf       ram_0x00E, W, ACCESS
    bnz         label_503
    movlw       0x00
    subwf       ram_0x00D, W, ACCESS
label_503:
    bc          label_504
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
label_504:
    movff       ram_0x00D, ram_0x003
    movff       ram_0x00E, ram_0x004
    movff       ram_0x00F, ram_0x005
    movff       ram_0x010, ram_0x006
    movlw       0x96
    movwf       ram_0x007, ACCESS
    movff       ram_0x011, ram_0x008
    call        function_029, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
    return      0
i2c_byte_tx:
    movff       WREG, ram_0x005
    movff       ram_0x005, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         label_508
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          label_506
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bz          label_506
    bsf         SSPCON1, 4, ACCESS
label_505:
    btfss       PIR1, 3, ACCESS
    bra         label_505
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         label_508
label_506:
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          label_507
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bnz         label_508
label_507:
    btfsc       SSPSTAT, 0, ACCESS
    bra         label_507
    call        i2c_wait_bus_idle, 0x0
    movf        SSPCON2, W, ACCESS
label_508:
    return      0

function_057:
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
    call        function_017, 0x0
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

function_058:
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
    call        function_011, 0x0
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

function_059:
    movff       WREG, ram_0x005
    clrf        ram_0x004, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x005, ACCESS
    bra         label_509
    movlw       0x3A
    subwf       ram_0x005, W, ACCESS
    bc          label_509
    movf        ram_0x005, W, ACCESS
    addlw       0xD0
    bra         label_510
label_509:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         label_511
    movlw       0x47
    subwf       ram_0x005, W, ACCESS
    bc          label_511
    movf        ram_0x005, W, ACCESS
    addlw       0xC9
label_510:
    movwf       ram_0x004, ACCESS
label_511:
    swapf       ram_0x004, F, ACCESS
    movlw       0xF0
    andwf       ram_0x004, F, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x003, ACCESS
    bra         label_512
    movlw       0x3A
    subwf       ram_0x003, W, ACCESS
    bc          label_512
    movf        ram_0x003, W, ACCESS
    addlw       0xD0
    bra         label_513
label_512:
    movlw       0x40
    cpfsgt      ram_0x003, ACCESS
    bra         label_514
    movlw       0x47
    subwf       ram_0x003, W, ACCESS
    bc          label_514
    movf        ram_0x003, W, ACCESS
    addlw       0xC9
label_513:
    addwf       ram_0x004, F, ACCESS
label_514:
    movf        ram_0x004, W, ACCESS
    return      0

function_060:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         label_515
    movwf       ram_0x005, ACCESS
label_515:
    clrf        ram_0x007, ACCESS
    bra         label_517
label_516:
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
label_517:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x007, W, ACCESS
    bnc         label_516
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
    bra         label_519
label_518:
    tblrd*+
    movff       ram_0x009, FSR2L
    movff       ram_0x00A, FSR2H
    movff       TABLAT, INDF2
    infsnz      ram_0x009, F, ACCESS
    incf        ram_0x00A, F, ACCESS
label_519:
    decf        ram_0x007, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x008, F, ACCESS
    incf        ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    incf        ram_0x008, W, ACCESS
    bnz         label_518
    movff       ram_0x011, TBLPTRU
    movff       ram_0x010, TBLPTRH
    movff       ram_0x00F, TBLPTRL
    return      0

function_062:
    movff       WREG, ram_0x003
    movlw       0x08
    movlb       0x1
    movwf       ram_0x017, BANKED
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x1C
    movwf       ram_0x018, BANKED
    tstfsz      ram_0x003, ACCESS
    bra         label_520
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x14
    movwf       ram_0x018, BANKED
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
    movlw       0x00
    bra         label_521
label_520:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
label_521:
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

function_063:
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
    bra         label_523
label_522:
    bcf         UIR, 3, ACCESS
    call        usb_disconnect_handler, 0x0
label_523:
    btfsc       UIR, 3, ACCESS
    bra         label_522
    bcf         UCON, 6, ACCESS
    bcf         UCON, 4, ACCESS
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x00
    call        function_062, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    clrf        ram_0x0CE, BANKED
    clrf        ram_0x0EB, BANKED
    movlw       0x00
    goto        function_117

function_064:
    clrf        ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          label_528
    movlw       0x01
    movwf       ram_0x009, ACCESS
    bra         label_525
label_524:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x009, F, ACCESS
label_525:
    btfss       ram_0x006, 7, ACCESS
    bra         label_524
label_526:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x007, F, ACCESS
    rlcf        ram_0x008, F, ACCESS
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         label_527
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
    bsf         ram_0x007, 0, ACCESS
label_527:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x009, F, ACCESS
    bra         label_526
label_528:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    return      0
an0_hysteresis_monitor:
    btfss       active_flags, 3, ACCESS
    bra         label_532
    movf        ram_0x0A1, W, BANKED
    xorlw       0x64
    bnz         label_531
    btfsc       ADCON0, 1, ACCESS
    bra         label_530
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
    bra         label_530
    movlw       0x28
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          label_530
    bcf         active_flags, 3, ACCESS
    bsf         event_flags, 2, BANKED
label_530:
    clrf        ram_0x0A1, BANKED
    bra         label_532
label_531:
    incf        ram_0x0A1, F, BANKED
label_532:
    return      0

function_065:
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
    bc          label_533
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
label_533:
    movff       ram_0x012, ram_0x00A
    movff       ram_0x013, ram_0x00B
    movff       ram_0x014, ram_0x00C
    movff       ram_0x015, ram_0x00D
    movf        ram_0x017, W, ACCESS
    call        function_034, 0x0
    movf        ram_0x016, W, ACCESS
    return      0

function_066:
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
label_534:
    movf        ram_0x091, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x091, F, BANKED
    movf        ram_0x091, W, BANKED
    bz          label_534
    movff       ram_0x0D1, ram_0x0EB
    movf        ram_0x0EB, W, BANKED
    call        function_117, 0x0
    movlb       0x0
    tstfsz      ram_0x0D1, BANKED
    bra         label_535
    movlw       0x05
    bra         label_536
label_535:
    movlw       0x06
label_536:
    movwf       ram_0x0CD, BANKED
    return      0
i2c_secondary_dev_random_read:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS
label_537:
    btfsc       SSPCON2, 0, ACCESS
    bra         label_537
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 1, ACCESS
label_538:
    btfsc       SSPCON2, 1, ACCESS
    bra         label_538
    movlw       0xE3
    call        i2c_byte_tx, 0x0
    call        function_089, 0x0
    movwf       ram_0x007, ACCESS
    bsf         SSPCON2, 5, ACCESS
    bsf         SSPCON2, 4, ACCESS
label_539:
    btfsc       SSPCON2, 4, ACCESS
    bra         label_539
    bsf         SSPCON2, 2, ACCESS
label_540:
    btfsc       SSPCON2, 2, ACCESS
    bra         label_540
    movf        ram_0x007, W, ACCESS
    return      0

function_068:
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          label_545
    movlw       0x01
    movwf       ram_0x007, ACCESS
    bra         label_542
label_541:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x007, F, ACCESS
label_542:
    btfss       ram_0x006, 7, ACCESS
    bra         label_541
label_543:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         label_544
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
label_544:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x007, F, ACCESS
    bra         label_543
label_545:
    movff       ram_0x003, ram_0x003
    movff       ram_0x004, ram_0x004
    return      0
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
    call        function_076, 0x0
label_546:
    btfsc       EECON1, 1, ACCESS
    bra         label_546
    movlw       UPPER(_CONFIG1L)
    movwf       TBLPTRU, ACCESS
    clrf        TBLPTRH, ACCESS
    clrf        TBLPTRL, ACCESS
    movlw       0x3A
    movwf       TABLAT, ACCESS
    tblwt*
    movlw       0xC4
    movwf       EECON1, ACCESS
    call        function_076, 0x0
label_547:
    btfsc       EECON1, 1, ACCESS
    bra         label_547
    bcf         EECON1, 2, ACCESS
    return      0

function_070:
    movlb       0x4
    clrf        ram_0x008, BANKED
    movlb       0x0
    clrf        ram_0x0CC, BANKED
    movlb       0x4
    btfss       ram_0x000, 7, BANKED
    bra         label_548
    clrf        ram_0x000, BANKED
    movlb       0x0
    clrf        ram_0x096, BANKED
label_548:
    movlb       0x4
    btfss       ram_0x004, 7, BANKED
    bra         label_549
    clrf        ram_0x004, BANKED
    movlw       0x01
    movlb       0x0
    movwf       ram_0x096, BANKED
label_549:
    movlb       0x0
    clrf        ram_0x0C9, BANKED
    clrf        ram_0x0C8, BANKED
    clrf        ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bcf         UCON, 4, ACCESS
    call        function_039, 0x0
    call        function_125, 0x0
    goto        label_400

function_071:
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
    call        function_011, 0x0
    movff       ram_0x020, ram_0x039
    movff       ram_0x021, ram_0x03A
    movff       ram_0x022, ram_0x03B
    movff       ram_0x023, ram_0x03C
    return      0
i2c_tas3108_reg1f_write:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS
label_550:
    btfsc       SSPCON2, 0, ACCESS
    bra         label_550
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
label_551:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         label_551

function_073:
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
    rcall       function_076
label_552:
    btfsc       EECON1, 1, ACCESS
    bra         label_552
    btfsc       ram_0x006, 0, ACCESS
    bra         label_553
    bcf         INTCON, 7, ACCESS
    bra         label_554
label_553:
    bsf         INTCON, 7, ACCESS
label_554:
    bcf         EECON1, 2, ACCESS
    return      0

function_076:
    movlw       0x55
    movwf       EECON2, ACCESS
    movlw       0xAA
    movwf       EECON2, ACCESS
    bsf         EECON1, 1, ACCESS
    retlw       0xAA

function_077:
    movf        ram_0x0CD, W, BANKED
    xorlw       0x04
    bnz         label_555
    movff       ram_0x0D1, UADDR
    movf        UADDR, W, ACCESS
    movlw       0x05
    btfsc       STATUS, 2, ACCESS
    movlw       0x03
    movwf       ram_0x0CD, BANKED
label_555:
    decf        ram_0x0C9, W, BANKED
    bnz         label_558
    call        function_036, 0x0
    movf        ram_0x0CC, W, BANKED
    xorlw       0x02
    bnz         label_556
    movlw       0x04
    movlb       0x4
    bra         label_557
label_556:
    movlb       0x4
    movlw       0x48
    btfsc       ram_0x008, 6, BANKED
    movlw       0x08
label_557:
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
label_558:
    return      0

function_078:
    movff       WREG, ram_0x003
    bra         label_564
label_559:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    clrf        ram_0x0B9, BANKED
    bra         label_565
label_560:
    clrf        ram_0x0A0, BANKED
    movlw       0x01
    bra         label_563
label_561:
    movlw       0x02
    movwf       ram_0x0A0, BANKED
    bra         label_563
label_562:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    movlw       0x03
label_563:
    movwf       ram_0x0B9, BANKED
    bra         label_565
label_564:
    movf        ram_0x003, W, ACCESS
    bz          label_559
    xorlw       0x01
    bz          label_560
    xorlw       0x03
    bz          label_561
    xorlw       0x01
    bz          label_562
label_565:
    return      0
timer3_blocking_delay:
    bcf         PIE2, 1, ACCESS
    movlw       0x98
    movwf       T3CON, ACCESS
    bsf         T3CON, 0, ACCESS
    bra         label_570
label_566:
    btfss       OSCCON, 1, ACCESS
    bra         label_567
    movlw       0xFC
    movwf       TMR3H, ACCESS
    movlw       0x18
    bra         label_568
label_567:
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
label_568:
    movwf       TMR3L, ACCESS
    bcf         PIR2, 1, ACCESS
label_569:
    btfss       PIR2, 1, ACCESS
    bra         label_569
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
label_570:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    bnz         label_566
    bcf         T3CON, 0, ACCESS
    return      0

function_080:
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
    call        function_091, 0x0
    movlw       0x0D
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A
    goto        uart_tx_byte_blocking
i2c_tas3108_coeff_write:
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS
label_571:
    btfsc       SSPCON2, 0, ACCESS
    bra         label_571
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x30
    call        i2c_byte_tx, 0x0
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        function_046, 0x0
    bsf         SSPCON2, 2, ACCESS
label_572:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         label_572

function_082:
    tstfsz      ram_0x05F, ACCESS
    bra         label_579
label_573:
    bcf         LATA, 3, ACCESS
    bra         label_575
label_574:
    bsf         LATA, 3, ACCESS
label_575:
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bra         label_580
label_576:
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bra         label_578
label_577:
    bcf         LATA, 3, ACCESS
    bsf         LATA, 4, ACCESS
label_578:
    bsf         LATA, 5, ACCESS
    bra         label_580
label_579:
    movf        ram_0x093, W, BANKED
    bz          label_573
    xorlw       0x05
    bz          label_574
    xorlw       0x03
    bz          label_576
    xorlw       0x01
    bz          label_577
label_580:
    return      0
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

function_084:
    movlw       0x56
    movwf       ram_0x033, ACCESS
    movlw       0x00
    clrf        ram_0x032, ACCESS
    clrf        ram_0x034, ACCESS
label_581:
    movff       ram_0x032, ram_0x013
    movff       ram_0x033, ram_0x014
    call        function_043, 0x0
    movlw       0x18
    addwf       ram_0x032, F, ACCESS
    movlw       0x00
    addwfc      ram_0x033, F, ACCESS
    incf        ram_0x034, F, ACCESS
    movlw       0x5F
    cpfsgt      ram_0x034, ACCESS
    bra         label_581
    movwf       ram_0x014, ACCESS
    clrf        ram_0x013, ACCESS
    goto        function_043

function_085:
    call        function_009, 0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         label_582
    btfss       PORTC, 0, ACCESS
    bra         label_582
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         label_582
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    call        function_060, 0x0
label_582:
    return      0

function_086:
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
    call        function_029, 0x0
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
    return      0
rx_ring_read:
    clrf        ram_0x004, ACCESS
    call        function_109, 0x0
    iorlw       0x00
    bz          label_583
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
    bra         label_583
    clrf        rx_ring_rd, BANKED
label_583:
    movf        ram_0x004, W, ACCESS
    return      0

function_088:
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

function_089:
    movff       SSPCON1, ram_0x003
    movlw       0x0F
    andwf       ram_0x003, F, ACCESS
    movf        ram_0x003, W, ACCESS
    xorlw       0x08
    bz          label_584
    movff       SSPCON1, ram_0x003
    movlw       0x0F
    andwf       ram_0x003, F, ACCESS
    movf        ram_0x003, W, ACCESS
    xorlw       0x0B
    btfsc       STATUS, 2, ACCESS
label_584:
    bsf         SSPCON2, 3, ACCESS
label_585:
    btfss       SSPSTAT, 0, ACCESS
    bra         label_585
    movf        SSPBUF, W, ACCESS
    return      0

function_090:
    lfsr        FSR2, 0x01F4
    lfsr        FSR1, 0x001C
    movlw       0x07
label_586:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         label_586
    movlw       0x1C
    call        function_080, 0x0
    movlw       0x1C
    call        function_080, 0x0
    movlw       0x1C
    goto        function_080

function_091:
    clrf        ram_0x01A, ACCESS
    bra         label_588
label_587:
    rcall       function_092
    call        uart_tx_byte_blocking, 0x0
    incf        ram_0x01A, F, ACCESS
label_588:
    rcall       function_092
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         label_587

function_092:
    movf        ram_0x01A, W, ACCESS
    addwf       ram_0x018, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x019, W, ACCESS
    movwf       FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    return      0
i2c_secondary_dev_write:
    movff       WREG, ram_0x007
    bsf         SSPCON2, 0, ACCESS
label_589:
    btfsc       SSPCON2, 0, ACCESS
    bra         label_589
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        ram_0x007, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS
label_590:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         label_590

function_094:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    call        function_110, 0x0
    xorwf       ram_0x009, W, ACCESS
    bz          label_591
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    movff       ram_0x009, ram_0x005
    call        eeprom_write_blocking, 0x0
label_591:
    return      0

function_095:
    decf        usb_reinit_pending, W, BANKED
    btfsc       STATUS, 2, ACCESS
    call        function_105, 0x0
    clrf        UCON, ACCESS
    movlw       0x15
    movwf       UCFG, ACCESS
    clrf        UIE, ACCESS
    bsf         UCON, 3, ACCESS
    call        function_063, 0x0
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0CD, BANKED
    clrf        usb_reinit_pending, BANKED
    return      0

function_096:
    movff       UIE, ram_0x092
    movlw       0x04
    movwf       UIE, ACCESS
    bcf         UIR, 4, ACCESS
    bsf         UCON, 1, ACCESS
    bcf         PIR2, 5, ACCESS
    bsf         PIE2, 5, ACCESS
    call        function_129, 0x0
    bcf         PIE2, 5, ACCESS
    movlb       0x0
    movf        ram_0x092, W, BANKED
    iorwf       UIE, F, ACCESS
    return      0

function_097:
    clrf        ram_0x006, ACCESS
    bra         label_593
label_592:
    movf        ram_0x006, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x006, F, ACCESS
label_593:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x006, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         label_592

function_098:
    movlb       0x0
    decf        usb_reinit_pending, W, BANKED
    bz          label_595
    btfss       PORTC, 0, ACCESS
    bra         label_594
    btfss       UCON, 3, ACCESS
    call        function_095, 0x0
    bra         label_595
label_594:
    btfss       UCON, 3, ACCESS
    bra         label_595
    call        usb_shutdown, 0x0
    clrf        usb_reinit_pending, BANKED
label_595:
    return      0

function_099:
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
standby_event_dispatch:
    movlb       0x0
    btfss       event_flags, 2, BANKED
    bra         label_598
    btfss       active_flags, 3, ACCESS
    bra         label_596
    call        adc_boot_gate, 0x0
    bra         label_597
label_596:
    call        hw_standby_shutdown, 0x0
label_597:
    bcf         event_flags, 2, BANKED
label_598:
    movlw       0x01
    goto        cmd_dispatch_gated
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
periodic_service_loop:
    call        function_047, 0x0
    call        function_006, 0x0
    call        function_015, 0x0
    call        standby_event_dispatch, 0x0
    call        function_014, 0x0
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
report_cmd29_status:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x29
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    btfss       active_flags, 1, ACCESS
    movlw       0x00
    goto        uart_tx_byte_blocking

function_104:
    bra         label_600
label_599:
    call        usb_disconnect_handler, 0x0
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
label_600:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         label_599

function_105:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlw       0xFF
    setf        ram_0x004, ACCESS
    setf        ram_0x003, ACCESS
    call        function_104, 0x0
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    return      0

function_106:
    call        function_119, 0x0
    bcf         UCON, 1, ACCESS
    bcf         UIE, 2, ACCESS
    bra         label_602
label_601:
    bcf         UIR, 2, ACCESS
label_602:
    btfss       UIR, 2, ACCESS
    return      0
    bra         label_601

function_107:
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movlw       0x18
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    goto        uart_tx_byte_blocking

function_108:
    bra         label_604
label_603:
    call        rx_ring_read, 0x0
label_604:
    call        function_109, 0x0
    iorlw       0x00
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         label_603

function_109:
    movlb       0x0
    movf        rx_ring_wr, W, BANKED
    clrf        PRODL, ACCESS
    cpfseq      rx_ring_rd, BANKED
    incf        PRODL, F, ACCESS
    movff       PRODL, ram_0x003
    movf        ram_0x003, W, ACCESS
    return      0

function_110:
    movff       ram_0x003, EEADR
    bcf         EECON1, 6, ACCESS
    bcf         EECON1, 7, ACCESS
    bsf         EECON1, 0, ACCESS
    dw          0xF000
    dw          0xF000
    movf        EEDATA, W, ACCESS
    return      0
uart_tx_byte_blocking:
    movff       WREG, ram_0x003
uart_tx_trmt_busywait:
    btfss       TXSTA, 1, ACCESS
    bra         uart_tx_trmt_busywait
    movff       ram_0x003, TXREG
    movf        ram_0x003, W, ACCESS
    return      0

function_112:
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    bcf         INTCON, 2, ACCESS
    bsf         INTCON, 5, ACCESS
    bsf         T0CON, 7, ACCESS
    retlw       0x71
i2c_wait_bus_idle:
    movff       SSPCON2, ram_0x003
    movlw       0x1F
    andwf       ram_0x003, F, ACCESS
    btfsc       STATUS, 2, ACCESS
    btfsc       SSPSTAT, 2, ACCESS
    bra         i2c_wait_bus_idle
    retlw       0x1F
label_606:
    call        function_035, 0x0
main_processing_loop:
    call        function_026, 0x0
    call        periodic_service_loop, 0x0
    bra         main_processing_loop
hard_reset:
    clrf        INTCON, ACCESS
    dw          0xF000
    dw          0xF000
    reset
    dw          0xF000
    dw          0xF000
    return      0

function_115:
    movlw       0x02
    call        i2c_tas3108_reg1f_write, 0x0
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    return      0
usb_shutdown:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    movlw       0x01
    movwf       usb_reinit_pending, BANKED
    retlw       0x01

function_117:
    movff       WREG, ram_0x003
    decf        ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    call        function_088, 0x0
    return      0

function_118:
    btfss       T3CON, 0, ACCESS
    bra         label_608
    bcf         STATUS, 0, ACCESS
    bra         label_609
label_608:
    bsf         STATUS, 0, ACCESS
label_609:
    return      0
label_610:
    btfsc       UCON, 3, ACCESS
    call        function_105, 0x0
    clrf        usb_reinit_pending, BANKED
    goto        function_098

function_119:
    movlw       0x03
    movwf       ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    goto        label_600

function_120:
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    goto        timer3_blocking_delay

function_121:
    call        uart_config, 0x0
    bcf         active_flags, 0, ACCESS
    clrf        rx_frame_position, BANKED
    return      0

function_122:
    clrf        ram_0x004, ACCESS
    movlw       0x02
    movwf       ram_0x003, ACCESS
    goto        timer3_blocking_delay

function_123:
    bcf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS
    bcf         PIE2, 1, ACCESS
    return      0

function_124:
    movlw       0x01
    goto        i2c_tas3108_reg1f_write

function_125:
    goto        label_383

function_126:
    bsf         RCSTA, 4, ACCESS
    return      0
usb_disconnect_handler:
    clrwdt
    return      0

function_128:
    bcf         SSPCON1, 5, ACCESS
    return      0

function_129:
    return      0

function_130:
    return      0

function_131:
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

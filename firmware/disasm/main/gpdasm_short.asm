        processor p18f2550
        radix dec

        include p18f2550.inc

; The recognition of labels and registers is not always good, therefore
; be treated cautiously the results.

        CONFIG  PLLDIV  = 3
        CONFIG  CPUDIV  = OSC4_PLL6
        CONFIG  USBDIV  = 2
        CONFIG  FOSC    = ECPLLIO_EC
        CONFIG  FCMEN   = ON
        CONFIG  IESO    = OFF
        CONFIG  PWRT    = ON
        CONFIG  BOR     = ON
        CONFIG  BORV    = 3
        CONFIG  VREGEN  = ON
        CONFIG  WDT     = OFF
        CONFIG  WDTPS   = 32768
        CONFIG  CCP2MX  = OFF
        CONFIG  PBADEN  = OFF
        CONFIG  LPT1OSC = OFF
        CONFIG  MCLRE   = OFF
        CONFIG  STVREN  = OFF
        CONFIG  LVP     = OFF
        CONFIG  XINST   = OFF
        CONFIG  DEBUG   = OFF
        CONFIG  CP0     = OFF
        CONFIG  CP1     = OFF
        CONFIG  CP2     = OFF
        CONFIG  CP3     = OFF
        CONFIG  CPB     = OFF
        CONFIG  CPD     = OFF
        CONFIG  WRT0    = OFF
        CONFIG  WRT1    = OFF
        CONFIG  WRT2    = OFF
        CONFIG  WRT3    = OFF
        CONFIG  WRTC    = OFF
        CONFIG  WRTB    = ON
        CONFIG  WRTD    = OFF
        CONFIG  EBTR0   = OFF
        CONFIG  EBTR1   = OFF
        CONFIG  EBTR2   = OFF
        CONFIG  EBTR3   = OFF
        CONFIG  EBTRB   = OFF

        __idlocs _IDLOC0, 0xFF
        __idlocs _IDLOC1, 0xFF
        __idlocs _IDLOC2, 0xFF
        __idlocs _IDLOC3, 0xFF
        __idlocs _IDLOC4, 0xFF
        __idlocs _IDLOC5, 0xFF
        __idlocs _IDLOC6, 0xFF
        __idlocs _IDLOC7, 0xFF

;===============================================================================
; DATA address definitions

Common_RAM      equ     0x000000                            ; size: 96 bytes

        ; code

        org     0x001000

        goto    label_000                                   ; dest: 0x001014
        dw      0xffff
        dw      0xffff
        movff   FSR2L, (Common_RAM + 1)                     ; reg1: 0xfd9, reg2: 0x001
        movff   FSR2H, (Common_RAM + 2)                     ; reg1: 0xfda, reg2: 0x002
        call    function_049, 0x1                           ; dest: 0x003b1e

label_000:                                                  ; address: 0x001014

        goto    label_494                                   ; dest: 0x003d4e
        rrcf    Common_RAM, W, A                            ; reg: 0x000
        rrcf    (Common_RAM + 49), F, A                     ; reg: 0x031
        rlcf    (Common_RAM + 51), W, A                     ; reg: 0x033
        rlcf    (Common_RAM + 53), F, A                     ; reg: 0x035
        swapf   (Common_RAM + 55), W, A                     ; reg: 0x037
        rrncf   (Common_RAM + 57), W, B                     ; reg: 0x039
        rrncf   (Common_RAM + 66), F, B                     ; reg: 0x042
        rlncf   (Common_RAM + 68), W, B                     ; reg: 0x044
        btfss   (Common_RAM + 70), 0x3, A                   ; reg: 0x046
        bcf     UEP2, 0x5, A                                ; reg: 0xf72
        mulwf   (Common_RAM + 9), A                         ; reg: 0x009
        dw      0x0029                                      ; ')'
        movlb   0x1
        bsf     0x00, 0x0, A                                ; reg: 0x100
        iorlw   0x32
        clrwdt
        mulwf   0x00, A                                     ; reg: 0x100
        sleep
        nop
        addwfc  0x09, W, B                                  ; reg: 0x109
        dw      0x0111
        movlb   0x0
        comf    (Common_RAM + 34), W, B                     ; reg: 0x022
        decf    Common_RAM, F, B                            ; reg: 0x000
        bsf     (Common_RAM + 5), 0x0, B                    ; reg: 0x005
        rrncf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movlb   0x0
        decf    (Common_RAM + 7), W, B                      ; reg: 0x007
        mulwf   (Common_RAM + 1), B                         ; reg: 0x001
        dw      0x0040                                      ; '@'
        decf    (Common_RAM + 1), F, A                      ; reg: 0x001
        dw      0xff00
        movlb   0x9
        dw      0x01a1
        dw      0x0119
        rrncf   0x29, W, A                                  ; reg: 0x929
        dw      0x0015
        dw      0xff26
        btg     0x00, 0x2, B                                ; reg: 0x900
        bcf     0x08, 0x2, B                                ; reg: 0x908
        bsf     0x40, 0x0, B                                ; reg: 0x940
        xorwf   0x00, W, B                                  ; reg: 0x900
        incf    0x01, W, B                                  ; reg: 0x901
        bcf     0x40, 0x0, B                                ; reg: 0x940
        dw      0xc000
        mulwf   0x16, B                                     ; reg: 0x916
        dw      0x0048                                      ; 'H'
        dw      0x0079                                      ; 'y'
        dw      0x0070                                      ; 'p'
        dw      0x0065                                      ; 'e'
        dw      0x0078                                      ; 'x'
        dw      0x0020                                      ; ' '
        dw      0x0042                                      ; 'B'
        dw      0x0056                                      ; 'V'
        nop
        nop
        dw      0x0112
        mulwf   0x00, A                                     ; reg: 0x900
        nop
        sublw   0x00
        decf    STATUS, W, A                                ; reg: 0xfd8
        dw      0xff89
        halt
        mulwf   0x01, A                                     ; reg: 0x901
        movlb   0x0
        mulwf   (Common_RAM + 12), B                        ; reg: 0x00c
        dw      0x0044                                      ; 'D'
        dw      0x004c                                      ; 'L'
        dw      0x0043                                      ; 'C'
        dw      0x0050                                      ; 'P'
        nop
        mulwf   (Common_RAM + 4), B                         ; reg: 0x004
        decf    (Common_RAM + 9), W, A                      ; reg: 0x009
        nop

function_000:                                               ; address: 0x0010ac

        movff   WREG, (Common_RAM + 87)                     ; reg1: 0xfe8, reg2: 0x057
        lfsr    0x2, 0x1ed
        lfsr    0x1, 0x04d
        movlw   0x07

label_001:                                                  ; address: 0x0010ba

        movff   POSTINC2, POSTINC1                          ; reg1: 0xfde, reg2: 0xfe6
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_001                                   ; dest: 0x0010ba
        movf    (Common_RAM + 87), W, A                     ; reg: 0x057
        xorlw   0x42
        bnz     label_002
        bra     label_070                                   ; dest: 0x001552

label_002:                                                  ; address: 0x0010ca

        movlb   0x0
        clrf    0xcb, B                                     ; reg: 0x0cb
        bra     label_070                                   ; dest: 0x001552

label_003:                                                  ; address: 0x0010d0

        movff   0x11b, 0x097
        movlb   0x0
        movf    0x97, W, B                                  ; reg: 0x097
        xorlw   0x09
        bnz     label_007
        movlw   0x02
        movwf   (Common_RAM + 88), A                        ; reg: 0x058

label_004:                                                  ; address: 0x0010e0

        rcall   function_001                                ; dest: 0x0015b0
        movf    INDF2, W, A                                 ; reg: 0xfdf
        bz      label_005
        rcall   function_001                                ; dest: 0x0015b0
        movlw   0xbe
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR1L, A                                    ; reg: 0xfe1
        clrf    FSR1H, A                                    ; reg: 0xfe2
        movlw   0x02
        addwfc  FSR1H, F, A                                 ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        bra     label_006                                   ; dest: 0x0010fc

label_005:                                                  ; address: 0x0010fa

        rcall   function_002                                ; dest: 0x0015be

label_006:                                                  ; address: 0x0010fc

        incf    (Common_RAM + 88), F, A                     ; reg: 0x058
        movlw   0x1f
        cpfsgt  (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_004                                   ; dest: 0x0010e0

label_007:                                                  ; address: 0x001104

        movlb   0x0
        movf    0x97, W, B                                  ; reg: 0x097
        xorlw   0x0a
        bnz     label_009
        movlw   0x02
        movwf   (Common_RAM + 88), A                        ; reg: 0x058

label_008:                                                  ; address: 0x001110

        rcall   function_002                                ; dest: 0x0015be
        incf    (Common_RAM + 88), F, A                     ; reg: 0x058
        movlw   0x1f
        cpfsgt  (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_008                                   ; dest: 0x001110

label_009:                                                  ; address: 0x00111a

        movlw   0x03
        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        movff   0x11b, 0x0c2
        bsf     0xbd, 0x5, B                                ; reg: 0x0bd

label_010:                                                  ; address: 0x001126

        call    function_112, 0x0                           ; dest: 0x0048a6

label_011:                                                  ; address: 0x00112a

        call    function_120, 0x0                           ; dest: 0x00492e

label_012:                                                  ; address: 0x00112e

        call    function_009, 0x0                           ; dest: 0x002328
        bra     label_083                                   ; dest: 0x0015aa

label_013:                                                  ; address: 0x001134

        movlb   0x1
        decf    0x1b, W, B                                  ; reg: 0x11b
        bnz     label_017
        movff   0x11c, 0x0b7
        bra     label_016                                   ; dest: 0x00115c

label_014:                                                  ; address: 0x001140

        movlw   0x04
        movwf   0xc1, B                                     ; reg: 0x0c1
        movlw   0x01
        movwf   0xc2, B                                     ; reg: 0x0c2
        bra     label_011                                   ; dest: 0x00112a

label_015:                                                  ; address: 0x00114a

        movff   0x11d, 0x0b8
        movlw   0x04
        movwf   0xc1, B                                     ; reg: 0x0c1
        movlw   0x01
        movwf   0xc2, B                                     ; reg: 0x0c2
        bsf     0x7f, 0x0, B                                ; reg: 0x07f
        bsf     0x94, 0x4, B                                ; reg: 0x094
        bra     label_011                                   ; dest: 0x00112a

label_016:                                                  ; address: 0x00115c

        movlb   0x0
        movf    0xb7, W, B                                  ; reg: 0x0b7
        xorlw   0x01
        bz      label_014
        xorlw   0x03
        bz      label_015
        bra     label_083                                   ; dest: 0x0015aa

label_017:                                                  ; address: 0x00116a

        movf    (Common_RAM + 27), W, B                     ; reg: 0x01b
        xorlw   0x02
        bz      label_018
        bra     label_083                                   ; dest: 0x0015aa

label_018:                                                  ; address: 0x001172

        movff   0x11e, 0x0b5
        movlw   0x04
        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        movlw   0x02
        movwf   0xc2, B                                     ; reg: 0x0c2
        movf    0xb5, W, B                                  ; reg: 0x0b5
        xorlw   0x06
        bnz     label_022
        movlw   0x05
        movwf   (Common_RAM + 88), A                        ; reg: 0x058

label_019:                                                  ; address: 0x00118a

        rcall   function_001                                ; dest: 0x0015b0
        movf    INDF2, W, A                                 ; reg: 0xfdf
        bz      label_020
        rcall   function_001                                ; dest: 0x0015b0
        movlw   0xfb
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR1L, A                                    ; reg: 0xfe1
        clrf    FSR1H, A                                    ; reg: 0xfe2
        movlw   0x00
        addwfc  FSR1H, F, A                                 ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        bra     label_021                                   ; dest: 0x0011b2

label_020:                                                  ; address: 0x0011a4

        movlw   0xfb
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        setf    INDF2, A                                    ; reg: 0xfdf

label_021:                                                  ; address: 0x0011b2

        incf    (Common_RAM + 88), F, A                     ; reg: 0x058
        movlw   0x13
        cpfsgt  (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_019                                   ; dest: 0x00118a
        movlb   0x0
        bsf     0xbd, 0x4, B                                ; reg: 0x0bd
        bra     label_010                                   ; dest: 0x001126

label_022:                                                  ; address: 0x0011c0

        movf    0xb5, W, B                                  ; reg: 0x0b5
        xorlw   0x05
        bz      label_011
        movf    0xb5, W, B                                  ; reg: 0x0b5
        xorlw   0x07
        bz      label_011
        bra     label_083                                   ; dest: 0x0015aa

label_023:                                                  ; address: 0x0011ce

        movff   0x11b, 0x099
        movff   0x11f, 0x071
        movff   0x120, 0x070
        movff   0x121, 0x06f
        movff   0x122, 0x06e
        movlb   0x1
        btfsc   0x23, 0x0, B                                ; reg: 0x123
        bra     label_024                                   ; dest: 0x0011ec
        bcf     (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bra     label_025                                   ; dest: 0x0011ee

label_024:                                                  ; address: 0x0011ec

        bsf     (Common_RAM + 94), 0x4, A                   ; reg: 0x05e

label_025:                                                  ; address: 0x0011ee

        movlb   0x1
        btfsc   0x24, 0x0, B                                ; reg: 0x124
        bra     label_026                                   ; dest: 0x0011fa
        movlb   0x0
        bcf     0xa4, 0x0, B                                ; reg: 0x0a4
        bra     label_027                                   ; dest: 0x0011fe

label_026:                                                  ; address: 0x0011fa

        movlb   0x0
        bsf     0xa4, 0x0, B                                ; reg: 0x0a4

label_027:                                                  ; address: 0x0011fe

        movlb   0x1
        btfsc   0x25, 0x0, B                                ; reg: 0x125
        bra     label_028                                   ; dest: 0x00120a
        movlb   0x0
        bcf     0xa4, 0x1, B                                ; reg: 0x0a4
        bra     label_029                                   ; dest: 0x00120e

label_028:                                                  ; address: 0x00120a

        movlb   0x0
        bsf     0xa4, 0x1, B                                ; reg: 0x0a4

label_029:                                                  ; address: 0x00120e

        movlb   0x1
        btfsc   0x26, 0x0, B                                ; reg: 0x126
        bra     label_030                                   ; dest: 0x00121a
        movlb   0x0
        bcf     0xa4, 0x2, B                                ; reg: 0x0a4
        bra     label_031                                   ; dest: 0x00121e

label_030:                                                  ; address: 0x00121a

        movlb   0x0
        bsf     0xa4, 0x2, B                                ; reg: 0x0a4

label_031:                                                  ; address: 0x00121e

        movlb   0x1
        btfsc   0x28, 0x0, B                                ; reg: 0x128
        bra     label_032                                   ; dest: 0x00122a
        movlb   0x0
        bcf     0xa4, 0x3, B                                ; reg: 0x0a4
        bra     label_033                                   ; dest: 0x00122e

label_032:                                                  ; address: 0x00122a

        movlb   0x0
        bsf     0xa4, 0x3, B                                ; reg: 0x0a4

label_033:                                                  ; address: 0x00122e

        movlb   0x1
        btfsc   0x29, 0x0, B                                ; reg: 0x129
        bra     label_034                                   ; dest: 0x00123a
        movlb   0x0
        bcf     0xa4, 0x4, B                                ; reg: 0x0a4
        bra     label_035                                   ; dest: 0x00123e

label_034:                                                  ; address: 0x00123a

        movlb   0x0
        bsf     0xa4, 0x4, B                                ; reg: 0x0a4

label_035:                                                  ; address: 0x00123e

        movlb   0x1
        btfsc   0x2a, 0x0, B                                ; reg: 0x12a
        bra     label_036                                   ; dest: 0x00124a
        movlb   0x0
        bcf     0xa4, 0x5, B                                ; reg: 0x0a4
        bra     label_037                                   ; dest: 0x00124e

label_036:                                                  ; address: 0x00124a

        movlb   0x0
        bsf     0xa4, 0x5, B                                ; reg: 0x0a4

label_037:                                                  ; address: 0x00124e

        movff   0x12c, 0x060
        movff   0x12d, 0x061
        movff   0x12e, 0x062
        movff   0x12f, 0x063
        movff   0x130, 0x064
        movff   0x131, 0x065
        movff   0x132, (Common_RAM + 95)                    ; reg2: 0x05f
        movff   0x133, 0x09b
        movff   0x134, 0x09c
        movff   0x135, 0x09d
        movff   0x136, 0x09e
        movff   0x138, 0x0b4
        movf    0xb3, W, B                                  ; reg: 0x0b3
        xorwf   0x99, W, B                                  ; reg: 0x099
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x94, 0x0, B                                ; reg: 0x094
        movf    0x69, W, B                                  ; reg: 0x069
        xorwf   0x71, W, B                                  ; reg: 0x071
        bnz     label_038
        movf    0x68, W, B                                  ; reg: 0x068
        xorwf   0x70, W, B                                  ; reg: 0x070
        bnz     label_038
        movf    0x67, W, B                                  ; reg: 0x067
        xorwf   0x6f, W, B                                  ; reg: 0x06f
        bnz     label_038
        movf    0x66, W, B                                  ; reg: 0x066
        xorwf   0x6e, W, B                                  ; reg: 0x06e

label_038:                                                  ; address: 0x00129c

        bz      label_039
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0x94, 0x1, B                                ; reg: 0x094

label_039:                                                  ; address: 0x0012a2

        movf    0xac, W, B                                  ; reg: 0x0ac
        xorwf   0x9b, W, B                                  ; reg: 0x09b
        bz      label_040
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0xbd, 0x3, B                                ; reg: 0x0bd

label_040:                                                  ; address: 0x0012ac

        movf    0xad, W, B                                  ; reg: 0x0ad
        xorwf   0x9c, W, B                                  ; reg: 0x09c
        bz      label_041
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0xbd, 0x3, B                                ; reg: 0x0bd

label_041:                                                  ; address: 0x0012b6

        movf    0xae, W, B                                  ; reg: 0x0ae
        xorwf   0x9d, W, B                                  ; reg: 0x09d
        bz      label_042
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0xbd, 0x3, B                                ; reg: 0x0bd

label_042:                                                  ; address: 0x0012c0

        movf    0xaf, W, B                                  ; reg: 0x0af
        xorwf   0x9e, W, B                                  ; reg: 0x09e
        bz      label_043
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0xbd, 0x3, B                                ; reg: 0x0bd

label_043:                                                  ; address: 0x0012ca

        movlw   0x01
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x00
        movwf   (Common_RAM + 76), A                        ; reg: 0x04c
        movlw   0x01
        btfss   (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        movlw   0x00
        xorwf   (Common_RAM + 76), F, A                     ; reg: 0x04c
        bz      label_044
        bsf     0x7e, 0x5, B                                ; reg: 0x07e
        bsf     0x94, 0x3, B                                ; reg: 0x094

label_044:                                                  ; address: 0x0012e0

        movf    0xb0, W, B                                  ; reg: 0x0b0
        xorwf   0xa4, W, B                                  ; reg: 0x0a4
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x6, B                                ; reg: 0x07e
        movf    0xb4, W, B                                  ; reg: 0x0b4
        xorwf   0xb1, W, B                                  ; reg: 0x0b1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7f, 0x1, B                                ; reg: 0x07f
        movf    0x60, W, B                                  ; reg: 0x060
        cpfseq  0xa5, B                                     ; reg: 0x0a5
        bra     label_045                                   ; dest: 0x001324
        movf    0xa6, W, B                                  ; reg: 0x0a6
        lfsr    0x2, 0x061
        cpfseq  INDF2, A                                    ; reg: 0xfdf
        bra     label_045                                   ; dest: 0x001324
        movf    0xa7, W, B                                  ; reg: 0x0a7
        lfsr    0x2, 0x062
        cpfseq  INDF2, A                                    ; reg: 0xfdf
        bra     label_045                                   ; dest: 0x001324
        movf    0xa8, W, B                                  ; reg: 0x0a8
        lfsr    0x2, 0x063
        cpfseq  INDF2, A                                    ; reg: 0xfdf
        bra     label_045                                   ; dest: 0x001324
        movf    0xa9, W, B                                  ; reg: 0x0a9
        lfsr    0x2, 0x064
        cpfseq  INDF2, A                                    ; reg: 0xfdf
        bra     label_045                                   ; dest: 0x001324
        movf    0x65, W, B                                  ; reg: 0x065
        xorwf   0xaa, W, B                                  ; reg: 0x0aa
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2

label_045:                                                  ; address: 0x001324

        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x099, 0x0b3
        movff   0x06e, 0x066
        movff   0x06f, 0x067
        movff   0x070, 0x068
        movff   0x071, 0x069
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bra     label_046                                   ; dest: 0x001342
        bsf     (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        bra     label_047                                   ; dest: 0x001344

label_046:                                                  ; address: 0x001342

        bcf     (Common_RAM + 94), 0x5, A                   ; reg: 0x05e

label_047:                                                  ; address: 0x001344

        movff   0x0a4, 0x0b0
        movff   0x060, 0x0a5
        movff   0x061, 0x0a6
        movff   0x062, 0x0a7
        movff   0x063, 0x0a8
        movff   0x064, 0x0a9
        movff   0x065, 0x0aa
        movff   0x0b4, 0x0b1
        movff   0x09b, 0x0ac
        movff   0x09c, 0x0ad
        movff   0x09d, 0x0ae
        movff   0x09e, 0x0af

label_048:                                                  ; address: 0x001374

        movlw   0x05
        bra     label_050                                   ; dest: 0x001384

label_049:                                                  ; address: 0x001378

        movlb   0x1
        decf    0x1b, W, B                                  ; reg: 0x11b
        bnz     label_051
        call    function_122, 0x0                           ; dest: 0x004942
        movlw   0x06

label_050:                                                  ; address: 0x001384

        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        bra     label_012                                   ; dest: 0x00112e

label_051:                                                  ; address: 0x00138a

        movf    (Common_RAM + 27), W, B                     ; reg: 0x01b
        xorlw   0x02
        bz      label_052
        bra     label_083                                   ; dest: 0x0015aa

label_052:                                                  ; address: 0x001392

        call    function_122, 0x0                           ; dest: 0x004942
        bra     label_048                                   ; dest: 0x001374

label_053:                                                  ; address: 0x001398

        movlb   0x1
        movf    0x1b, W, B                                  ; reg: 0x11b
        xorlw   0x0f
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x5e, 0x7, A                                ; reg: 0x15e

label_054:                                                  ; address: 0x0013a2

        movf    (Common_RAM + 87), W, A                     ; reg: 0x057
        xorlw   0x07
        bnz     label_055
        movlb   0x1
        tstfsz  0x1b, B                                     ; reg: 0x11b
        bra     label_055                                   ; dest: 0x0013ba
        movlb   0x0
        clrf    0xc5, B                                     ; reg: 0x0c5
        movlw   0x56
        movwf   0x83, B                                     ; reg: 0x083
        movlw   0x00
        clrf    0x82, B                                     ; reg: 0x082

label_055:                                                  ; address: 0x0013ba

        bcf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        bsf     (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        movlb   0x0
        clrf    0x98, B                                     ; reg: 0x098
        clrf    0xc7, B                                     ; reg: 0x0c7
        clrf    0xc6, B                                     ; reg: 0x0c6
        call    function_021, 0x0                           ; dest: 0x002bb8

label_056:                                                  ; address: 0x0013ca

        movff   (Common_RAM + 87), 0x0c1                    ; reg1: 0x057
        bra     label_012                                   ; dest: 0x00112e

label_057:                                                  ; address: 0x0013d0

        movlw   0xa0
        movlb   0x0
        movwf   0x6e, B                                     ; reg: 0x06e
        setf    0x6f, B                                     ; reg: 0x06f
        setf    0x70, B                                     ; reg: 0x070
        setf    0x71, B                                     ; reg: 0x071
        movlw   0x01
        movwf   0x99, B                                     ; reg: 0x099
        movlw   0x03
        movwf   (Common_RAM + 95), A                        ; reg: 0x05f
        clrf    0x60, B                                     ; reg: 0x060
        clrf    0x61, B                                     ; reg: 0x061
        clrf    0x62, B                                     ; reg: 0x062
        movlw   0x01
        movwf   0x63, B                                     ; reg: 0x063
        movwf   0x64, B                                     ; reg: 0x064
        movwf   0x65, B                                     ; reg: 0x065
        movwf   0xb4, B                                     ; reg: 0x0b4
        movlw   0x04
        movwf   0xb8, B                                     ; reg: 0x0b8
        clrf    0x9b, B                                     ; reg: 0x09b
        clrf    0x9c, B                                     ; reg: 0x09c
        clrf    0x9d, B                                     ; reg: 0x09d
        clrf    0x9e, B                                     ; reg: 0x09e
        clrf    (Common_RAM + 88), A                        ; reg: 0x058

label_058:                                                  ; address: 0x001402

        movlw   0xc0
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        setf    INDF2, A                                    ; reg: 0xfdf
        incf    (Common_RAM + 88), F, A                     ; reg: 0x058
        movlw   0x1d
        cpfsgt  (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_058                                   ; dest: 0x001402
        clrf    (Common_RAM + 88), A                        ; reg: 0x058

label_059:                                                  ; address: 0x00141a

        movlw   0x00
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        setf    INDF2, A                                    ; reg: 0xfdf
        incf    (Common_RAM + 88), F, A                     ; reg: 0x058
        movlw   0x0e
        cpfsgt  (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_059                                   ; dest: 0x00141a
        movlb   0x0
        bsf     0xbd, 0x0, B                                ; reg: 0x0bd
        bsf     0xbd, 0x5, B                                ; reg: 0x0bd
        bsf     0xbd, 0x4, B                                ; reg: 0x0bd
        bsf     0xbd, 0x1, B                                ; reg: 0x0bd
        bsf     0xbd, 0x2, B                                ; reg: 0x0bd
        bsf     0xbd, 0x3, B                                ; reg: 0x0bd
        bsf     0x7e, 0x0, B                                ; reg: 0x07e
        call    function_014, 0x0                           ; dest: 0x00265c
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        setf    (Common_RAM + 7), A                         ; reg: 0x007
        movlw   0x00
        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        call    function_114, 0x0                           ; dest: 0x0048d4
        bra     label_083                                   ; dest: 0x0015aa

label_060:                                                  ; address: 0x001456

        movlb   0x0
        tstfsz  0xcb, B                                     ; reg: 0x0cb
        bra     label_064                                   ; dest: 0x0014fc
        clrf    0x7c, B                                     ; reg: 0x07c
        clrf    0x7d, B                                     ; reg: 0x07d
        clrf    0x80, B                                     ; reg: 0x080
        clrf    0x81, B                                     ; reg: 0x081
        clrf    0x86, B                                     ; reg: 0x086
        clrf    0x87, B                                     ; reg: 0x087
        clrf    0x84, B                                     ; reg: 0x084
        clrf    0x85, B                                     ; reg: 0x085
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0xc7
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x0a
        movwf   0x05, A                                     ; reg: 0x105
        call    function_097, 0x0                           ; dest: 0x00473e
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0x9a
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x2d
        movwf   0x05, A                                     ; reg: 0x105
        call    function_097, 0x0                           ; dest: 0x00473e
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0xd1
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x08
        movwf   0x05, A                                     ; reg: 0x105
        call    function_097, 0x0                           ; dest: 0x00473e
        call    function_107, 0x0                           ; dest: 0x00484e
        movlw   0x05
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0xdc
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        movlb   0x1
        movlw   0x01
        movwf   0x08, A                                     ; reg: 0x108
        movlw   0xd1
        movwf   0x07, A                                     ; reg: 0x107
        movlw   0x08
        movwf   0x09, A                                     ; reg: 0x109
        call    function_048, 0x0                           ; dest: 0x003aa4
        movwf   (Common_RAM + 76), A                        ; reg: 0x04c
        movlw   0x05
        subwf   (Common_RAM + 76), W, A                     ; reg: 0x04c
        bnc     label_063
        movlw   0x01
        movwf   0xcb, B                                     ; reg: 0x0cb
        clrf    (Common_RAM + 88), A                        ; reg: 0x058

label_061:                                                  ; address: 0x0014ce

        movf    (Common_RAM + 88), W, A                     ; reg: 0x058
        addlw   0x4d
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movwf   (Common_RAM + 76), A                        ; reg: 0x04c
        movlw   0xd1
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        xorwf   (Common_RAM + 76), W, A                     ; reg: 0x04c
        bz      label_062
        movlb   0x0
        clrf    0xcb, B                                     ; reg: 0x0cb

label_062:                                                  ; address: 0x0014f0

        incf    (Common_RAM + 88), F, A                     ; reg: 0x058
        movlw   0x05
        cpfsgt  (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_061                                   ; dest: 0x0014ce
        bra     label_064                                   ; dest: 0x0014fc

label_063:                                                  ; address: 0x0014fa

        clrf    0xcb, B                                     ; reg: 0x0cb

label_064:                                                  ; address: 0x0014fc

        movlb   0x0
        movf    0xcb, W, B                                  ; reg: 0x0cb
        bnz     label_065
        bra     label_056                                   ; dest: 0x0013ca

label_065:                                                  ; address: 0x001504

        call    function_003, 0x0                           ; dest: 0x0015ce
        bra     label_056                                   ; dest: 0x0013ca

label_066:                                                  ; address: 0x00150a

        movff   0x11e, (Common_RAM + 86)                    ; reg2: 0x056
        movff   0x11f, (Common_RAM + 85)                    ; reg2: 0x055
        movff   (Common_RAM + 87), 0x0c1                    ; reg1: 0x057
        call    function_009, 0x0                           ; dest: 0x002328
        movf    0x7d, W, B                                  ; reg: 0x07d
        xorwf   (Common_RAM + 86), W, A                     ; reg: 0x056
        bnz     label_067
        movf    0x7c, W, B                                  ; reg: 0x07c
        xorwf   (Common_RAM + 85), W, A                     ; reg: 0x055

label_067:                                                  ; address: 0x001524

        bnz     label_068
        call    function_090, 0x0                           ; dest: 0x004672
        movlw   0xaa
        movlb   0x1
        movwf   0x5c, B                                     ; reg: 0x15c
        bra     label_083                                   ; dest: 0x0015aa

label_068:                                                  ; address: 0x001532

        movlw   0x11
        movlb   0x1
        movwf   0x5b, B                                     ; reg: 0x15b
        movlb   0x0
        clrf    0x84, B                                     ; reg: 0x084
        clrf    0x85, B                                     ; reg: 0x085
        clrf    0x80, B                                     ; reg: 0x080
        clrf    0x81, B                                     ; reg: 0x081
        clrf    0x86, B                                     ; reg: 0x086
        clrf    0x87, B                                     ; reg: 0x087
        clrf    0x7c, B                                     ; reg: 0x07c
        clrf    0x7d, B                                     ; reg: 0x07d
        bra     label_083                                   ; dest: 0x0015aa

label_069:                                                  ; address: 0x00154c

        movlb   0x1
        clrf    0x1a, B                                     ; reg: 0x11a
        bra     label_083                                   ; dest: 0x0015aa

label_070:                                                  ; address: 0x001552

        movf    (Common_RAM + 87), W, A                     ; reg: 0x057
        xorlw   0x01
        bz      label_083
        xorlw   0x03
        bz      label_083
        xorlw   0x01
        bnz     label_071
        bra     label_003                                   ; dest: 0x0010d0

label_071:                                                  ; address: 0x001562

        xorlw   0x07
        bnz     label_072
        bra     label_013                                   ; dest: 0x001134

label_072:                                                  ; address: 0x001568

        xorlw   0x01
        bnz     label_073
        bra     label_023                                   ; dest: 0x0011ce

label_073:                                                  ; address: 0x00156e

        xorlw   0x03
        bnz     label_074
        bra     label_049                                   ; dest: 0x001378

label_074:                                                  ; address: 0x001574

        xorlw   0x01
        bnz     label_075
        bra     label_054                                   ; dest: 0x0013a2

label_075:                                                  ; address: 0x00157a

        xorlw   0x0f
        bnz     label_076
        bra     label_054                                   ; dest: 0x0013a2

label_076:                                                  ; address: 0x001580

        xorlw   0x01
        bnz     label_077
        bra     label_054                                   ; dest: 0x0013a2

label_077:                                                  ; address: 0x001586

        xorlw   0x03
        bnz     label_078
        bra     label_054                                   ; dest: 0x0013a2

label_078:                                                  ; address: 0x00158c

        xorlw   0x01
        bnz     label_079
        bra     label_054                                   ; dest: 0x0013a2

label_079:                                                  ; address: 0x001592

        xorlw   0x07
        bnz     label_080
        bra     label_053                                   ; dest: 0x001398

label_080:                                                  ; address: 0x001598

        xorlw   0x4c
        bnz     label_081
        bra     label_057                                   ; dest: 0x0013d0

label_081:                                                  ; address: 0x00159e

        xorlw   0x01
        bz      label_066
        xorlw   0x03
        bnz     label_082
        bra     label_060                                   ; dest: 0x001456

label_082:                                                  ; address: 0x0015a8

        bra     label_069                                   ; dest: 0x00154c

label_083:                                                  ; address: 0x0015aa

        movlb   0x1
        clrf    0x1a, B                                     ; reg: 0x11a
        return  0x0

function_001:                                               ; address: 0x0015b0

        movlw   0x1a
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        return  0x0

function_002:                                               ; address: 0x0015be

        movlw   0xbe
        addwf   (Common_RAM + 88), W, A                     ; reg: 0x058
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        setf    INDF2, A                                    ; reg: 0xfdf
        return  0x0

function_003:                                               ; address: 0x0015ce

        lfsr    0x2, 0x1e5
        lfsr    0x1, 0x01d
        movlw   0x08

label_084:                                                  ; address: 0x0015d8

        movff   POSTINC2, POSTINC1                          ; reg1: 0xfde, reg2: 0xfe6
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_084                                   ; dest: 0x0015d8
        movlw   0x02
        movwf   (Common_RAM + 73), A                        ; reg: 0x049

label_085:                                                  ; address: 0x0015e4

        movlw   0x1a
        addwf   (Common_RAM + 73), W, A                     ; reg: 0x049
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movwf   (Common_RAM + 74), A                        ; reg: 0x04a
        movlw   0xc0
        movlb   0x0
        subwf   0x84, W, B                                  ; reg: 0x084
        movlw   0x77
        subwfb  0x85, W, B                                  ; reg: 0x085
        bc      label_090
        movff   (Common_RAM + 74), (Common_RAM + 69)        ; reg1: 0x04a, reg2: 0x045
        clrf    (Common_RAM + 72), A                        ; reg: 0x048

label_086:                                                  ; address: 0x001606

        btfss   0x7d, 0x5, B                                ; reg: 0x07d
        bra     label_087                                   ; dest: 0x001610
        movlw   0x01
        movwf   (Common_RAM + 68), A                        ; reg: 0x044
        bra     label_088                                   ; dest: 0x001612

label_087:                                                  ; address: 0x001610

        clrf    (Common_RAM + 68), A                        ; reg: 0x044

label_088:                                                  ; address: 0x001612

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    0x7c, F, B                                  ; reg: 0x07c
        rlcf    0x7d, F, B                                  ; reg: 0x07d
        btfsc   (Common_RAM + 69), 0x0, A                   ; reg: 0x045
        bsf     0x7c, 0x0, B                                ; reg: 0x07c
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 69), F, A                     ; reg: 0x045
        movf    (Common_RAM + 68), W, A                     ; reg: 0x044
        bz      label_089
        movlw   0x02
        xorwf   0x7c, F, B                                  ; reg: 0x07c
        movlw   0x44
        xorwf   0x7d, F, B                                  ; reg: 0x07d

label_089:                                                  ; address: 0x00162c

        incf    (Common_RAM + 72), F, A                     ; reg: 0x048
        movlw   0x07
        cpfsgt  (Common_RAM + 72), A                        ; reg: 0x048
        bra     label_086                                   ; dest: 0x001606

label_090:                                                  ; address: 0x001634

        movlw   0x40
        subwf   0x84, W, B                                  ; reg: 0x084
        movlw   0x00
        subwfb  0x85, W, B                                  ; reg: 0x085
        bc      label_091
        bra     label_108                                   ; dest: 0x0018d0

label_091:                                                  ; address: 0x001640

        movlw   0xc0
        subwf   0x84, W, B                                  ; reg: 0x084
        movlw   0x77
        subwfb  0x85, W, B                                  ; reg: 0x085
        bnc     label_092
        bra     label_108                                   ; dest: 0x0018d0

label_092:                                                  ; address: 0x00164c

        movlw   0x0f
        andwf   0x84, W, B                                  ; reg: 0x084
        movwf   0x8a, B                                     ; reg: 0x08a
        clrf    0x8b, B                                     ; reg: 0x08b
        iorwf   0x8b, W, B                                  ; reg: 0x08b
        bz      label_093
        bra     label_102                                   ; dest: 0x00182e

label_093:                                                  ; address: 0x00165a

        movf    0x87, W, B                                  ; reg: 0x087
        iorwf   0x86, W, B                                  ; reg: 0x086
        bnz     label_094
        bra     label_099                                   ; dest: 0x00179c

label_094:                                                  ; address: 0x001662

        movf    0x86, W, B                                  ; reg: 0x086
        addwf   0x80, F, B                                  ; reg: 0x080
        movlw   0x00
        addwfc  0x81, F, B                                  ; reg: 0x081
        movf    0x87, W, B                                  ; reg: 0x087
        addwf   0x80, F, B                                  ; reg: 0x080
        movlw   0x00
        addwfc  0x81, F, B                                  ; reg: 0x081
        comf    0x80, W, B                                  ; reg: 0x080
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        comf    0x81, W, B                                  ; reg: 0x081
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movlw   0xf1
        addwf   (Common_RAM + 27), W, A                     ; reg: 0x01b
        movwf   0x80, B                                     ; reg: 0x080
        movlw   0xff
        addwfc  (Common_RAM + 28), W, A                     ; reg: 0x01c
        movwf   0x81, B                                     ; reg: 0x081
        movf    0x80, W, B                                  ; reg: 0x080
        call    function_073, 0x0                           ; dest: 0x0043a2
        movlw   0x0d
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x0a
        call    function_111, 0x0                           ; dest: 0x004896
        movff   0x080, (Common_RAM + 27)                    ; reg2: 0x01b
        swapf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movlw   0x0f
        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movf    (Common_RAM + 27), W, A                     ; reg: 0x01b
        addlw   0x19
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x10
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x9a
        addwf   (Common_RAM + 75), W, A                     ; reg: 0x04b
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        tblrd*
        movff   TABLAT, INDF2                               ; reg1: 0xff5, reg2: 0xfdf
        movff   0x080, (Common_RAM + 27)                    ; reg2: 0x01b
        movlw   0x0f
        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movf    (Common_RAM + 27), W, A                     ; reg: 0x01b
        addlw   0x19
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x10
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x9b
        addwf   (Common_RAM + 75), W, A                     ; reg: 0x04b
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        tblrd*
        movff   TABLAT, INDF2                               ; reg1: 0xff5, reg2: 0xfdf
        movlw   0x9c
        addwf   (Common_RAM + 75), W, A                     ; reg: 0x04b
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        clrf    INDF2, A                                    ; reg: 0xfdf
        movlw   0x02
        addwf   (Common_RAM + 75), F, A                     ; reg: 0x04b
        movlb   0x0
        clrf    0x9f, B                                     ; reg: 0x09f

label_095:                                                  ; address: 0x0016fa

        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0a
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        movlb   0x1
        movlw   0x01
        movwf   0x08, A                                     ; reg: 0x108
        movlw   0xc7
        movwf   0x07, A                                     ; reg: 0x107
        movlw   0x0a
        movwf   0x09, A                                     ; reg: 0x109
        call    function_048, 0x0                           ; dest: 0x003aa4
        movff   0x1c8, (Common_RAM + 3)                     ; reg2: 0x003
        movlb   0x1
        movf    0xc7, W, B                                  ; reg: 0x1c7
        call    function_059, 0x0                           ; dest: 0x003f78
        movlb   0x0
        xorwf   0x80, W, B                                  ; reg: 0x080
        bnz     label_096
        movlw   0x01
        movwf   (Common_RAM + 67), A                        ; reg: 0x043
        bra     label_098                                   ; dest: 0x001796

label_096:                                                  ; address: 0x00172a

        clrf    (Common_RAM + 67), A                        ; reg: 0x043
        clrf    (Common_RAM + 25), A                        ; reg: 0x019
        movlw   0x1d
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        call    function_091, 0x0                           ; dest: 0x004696
        movlb   0x0
        movff   0x09f, (Common_RAM + 18)                    ; reg2: 0x012
        clrf    (Common_RAM + 19), A                        ; reg: 0x013
        clrf    (Common_RAM + 21), A                        ; reg: 0x015
        movlw   0x0a
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        movlw   0x25
        call    function_065, 0x0                           ; dest: 0x0041b6
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        clrf    (Common_RAM + 25), A                        ; reg: 0x019
        movff   (Common_RAM + 27), (Common_RAM + 24)        ; reg1: 0x01b, reg2: 0x018
        call    function_091, 0x0                           ; dest: 0x004696
        movlw   0x21
        call    function_111, 0x0                           ; dest: 0x004896
        call    function_108, 0x0                           ; dest: 0x004860
        movlw   0x0d
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x0a
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x19
        movlb   0x0
        subwf   0x9f, W, B                                  ; reg: 0x09f
        bc      label_097
        incf    0x9f, F, B                                  ; reg: 0x09f
        movlb   0x1
        movlw   0x01
        movwf   0x19, A                                     ; reg: 0x119
        movlw   0x9a
        movwf   0x18, A                                     ; reg: 0x118
        call    function_091, 0x0                           ; dest: 0x004696
        movlw   0x0d
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x0a
        call    function_111, 0x0                           ; dest: 0x004896
        bra     label_098                                   ; dest: 0x001796

label_097:                                                  ; address: 0x001792

        incf    0x9f, F, B                                  ; reg: 0x09f
        bra     label_109                                   ; dest: 0x0018dc

label_098:                                                  ; address: 0x001796

        movf    (Common_RAM + 67), W, A                     ; reg: 0x043
        bnz     label_100
        bra     label_095                                   ; dest: 0x0016fa

label_099:                                                  ; address: 0x00179c

        clrf    0x8e, B                                     ; reg: 0x08e

label_100:                                                  ; address: 0x00179e

        movlw   0xbf
        movlb   0x0
        subwf   0x84, W, B                                  ; reg: 0x084
        movlw   0x77
        subwfb  0x85, W, B                                  ; reg: 0x085
        bc      label_102
        movlw   0x04
        subwf   0x8e, W, B                                  ; reg: 0x08e
        bc      label_101
        incf    0x8e, F, B                                  ; reg: 0x08e
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0a
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e

label_101:                                                  ; address: 0x0017bc

        movff   0x084, 0x086
        movff   0x085, 0x087
        movlw   0x3a
        movlb   0x1
        movwf   0x9a, B                                     ; reg: 0x19a
        movlw   0x31
        movwf   0x9b, B                                     ; reg: 0x19b
        movlw   0x30
        movwf   0x9c, B                                     ; reg: 0x19c
        movff   0x087, (Common_RAM + 27)                    ; reg2: 0x01b
        swapf   0x1b, F, A                                  ; reg: 0x11b
        movlw   0x0f
        andwf   0x1b, F, A                                  ; reg: 0x11b
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, 0x19d                               ; reg1: 0xff5
        movff   0x087, (Common_RAM + 27)                    ; reg2: 0x01b
        movlw   0x0f
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, 0x19e                               ; reg1: 0xff5
        movff   0x086, (Common_RAM + 27)                    ; reg2: 0x01b
        swapf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movlw   0x0f
        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, 0x19f                               ; reg1: 0xff5
        movff   0x086, (Common_RAM + 27)                    ; reg2: 0x01b
        movlw   0x0f
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, 0x1a0                               ; reg1: 0xff5
        movlw   0x30
        movwf   0xa1, B                                     ; reg: 0x0a1
        movwf   0xa2, B                                     ; reg: 0x0a2
        clrf    0xa3, B                                     ; reg: 0x0a3
        movlw   0x09
        movwf   (Common_RAM + 75), A                        ; reg: 0x04b
        call    function_108, 0x0                           ; dest: 0x004860
        movlb   0x1
        movlw   0x01
        movwf   0x19, A                                     ; reg: 0x119
        movlw   0x9a
        movwf   0x18, A                                     ; reg: 0x118
        call    function_091, 0x0                           ; dest: 0x004696
        movlb   0x0
        clrf    0x80, B                                     ; reg: 0x080
        clrf    0x81, B                                     ; reg: 0x081

label_102:                                                  ; address: 0x00182e

        movlw   0xbf
        subwf   0x84, W, B                                  ; reg: 0x084
        movlw   0x77
        subwfb  0x85, W, B                                  ; reg: 0x085
        bc      label_107
        btfss   0x84, 0x0, B                                ; reg: 0x084
        bra     label_105                                   ; dest: 0x0018bc
        movff   (Common_RAM + 70), (Common_RAM + 27)        ; reg1: 0x046, reg2: 0x01b
        swapf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movlw   0x0f
        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, (Common_RAM + 47)                   ; reg1: 0xff5, reg2: 0x02f
        movff   (Common_RAM + 70), (Common_RAM + 27)        ; reg1: 0x046, reg2: 0x01b
        movlw   0x0f
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, (Common_RAM + 48)                   ; reg1: 0xff5, reg2: 0x030
        movff   (Common_RAM + 74), (Common_RAM + 27)        ; reg1: 0x04a, reg2: 0x01b
        swapf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movlw   0x0f
        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, (Common_RAM + 49)                   ; reg1: 0xff5, reg2: 0x031
        movff   (Common_RAM + 74), (Common_RAM + 27)        ; reg1: 0x04a, reg2: 0x01b
        movlw   0x0f
        rcall   function_004                                ; dest: 0x0018de
        movff   TABLAT, (Common_RAM + 50)                   ; reg1: 0xff5, reg2: 0x032
        clrf    (Common_RAM + 51), A                        ; reg: 0x033
        clrf    (Common_RAM + 25), A                        ; reg: 0x019
        movlw   0x2f
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        call    function_091, 0x0                           ; dest: 0x004696
        clrf    (Common_RAM + 71), A                        ; reg: 0x047
        bra     label_104                                   ; dest: 0x0018a0

label_103:                                                  ; address: 0x001884

        movf    (Common_RAM + 71), W, A                     ; reg: 0x047
        addlw   0x2f
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x9a
        addwf   (Common_RAM + 75), W, A                     ; reg: 0x04b
        movwf   FSR1L, A                                    ; reg: 0xfe1
        clrf    FSR1H, A                                    ; reg: 0xfe2
        movlw   0x01
        addwfc  FSR1H, F, A                                 ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        incf    (Common_RAM + 71), F, A                     ; reg: 0x047
        incf    (Common_RAM + 75), F, A                     ; reg: 0x04b

label_104:                                                  ; address: 0x0018a0

        movf    (Common_RAM + 71), W, A                     ; reg: 0x047
        addlw   0x2f
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        bnz     label_103
        movlw   0x9a
        addwf   (Common_RAM + 75), W, A                     ; reg: 0x04b
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        clrf    INDF2, A                                    ; reg: 0xfdf
        bra     label_106                                   ; dest: 0x0018c0

label_105:                                                  ; address: 0x0018bc

        movff   (Common_RAM + 74), (Common_RAM + 70)        ; reg1: 0x04a, reg2: 0x046

label_106:                                                  ; address: 0x0018c0

        movf    (Common_RAM + 74), W, A                     ; reg: 0x04a
        movlb   0x0
        addwf   0x80, F, B                                  ; reg: 0x080
        movlw   0x00
        addwfc  0x81, F, B                                  ; reg: 0x081
        bra     label_108                                   ; dest: 0x0018d0

label_107:                                                  ; address: 0x0018cc

        clrf    0x80, B                                     ; reg: 0x080
        clrf    0x81, B                                     ; reg: 0x081

label_108:                                                  ; address: 0x0018d0

        infsnz  0x84, F, B                                  ; reg: 0x084
        incf    0x85, F, B                                  ; reg: 0x085
        incf    (Common_RAM + 73), F, A                     ; reg: 0x049
        movlw   0x1f
        cpfsgt  (Common_RAM + 73), A                        ; reg: 0x049
        bra     label_085                                   ; dest: 0x0015e4

label_109:                                                  ; address: 0x0018dc

        return  0x0

function_004:                                               ; address: 0x0018de

        andwf   (Common_RAM + 27), F, A                     ; reg: 0x01b
        movf    (Common_RAM + 27), W, A                     ; reg: 0x01b
        addlw   0x19
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x10
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        tblrd*
        return  0x0

function_005:                                               ; address: 0x0018ee

        movff   WREG, 0x0fd                                 ; reg1: 0xfe8
        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_144                                   ; dest: 0x001be4
        btfss   0x7e, 0x1, B                                ; reg: 0x07e
        bra     label_117                                   ; dest: 0x0019a8
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bra     label_115                                   ; dest: 0x001970

label_110:                                                  ; address: 0x0018fe

        movlw   0x09
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x70
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x08
        call    function_093, 0x0                           ; dest: 0x0046ba
        call    function_115, 0x0                           ; dest: 0x0048e2
        bra     label_116                                   ; dest: 0x001990

label_111:                                                  ; address: 0x001918

        movlw   0x0a
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0xb0
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x08
        call    function_093, 0x0                           ; dest: 0x0046ba
        call    function_115, 0x0                           ; dest: 0x0048e2
        bra     label_116                                   ; dest: 0x001990

label_112:                                                  ; address: 0x001932

        movlw   0x08
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x30
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x08
        call    function_093, 0x0                           ; dest: 0x0046ba
        call    function_115, 0x0                           ; dest: 0x0048e2
        bra     label_116                                   ; dest: 0x001990

label_113:                                                  ; address: 0x00194c

        movlw   0x0b
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0xf0
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x08
        call    function_093, 0x0                           ; dest: 0x0046ba
        call    function_115, 0x0                           ; dest: 0x0048e2
        bra     label_116                                   ; dest: 0x001990

label_114:                                                  ; address: 0x001966

        call    function_082, 0x0                           ; dest: 0x004516
        call    function_124, 0x0                           ; dest: 0x004954
        bra     label_116                                   ; dest: 0x001990

label_115:                                                  ; address: 0x001970

        movf    0x93, W, B                                  ; reg: 0x093
        bz      label_114
        xorlw   0x01
        bz      label_110
        xorlw   0x03
        bz      label_111
        xorlw   0x01
        bz      label_112
        xorlw   0x07
        bz      label_113
        xorlw   0x01
        bz      label_114
        xorlw   0x03
        bz      label_114
        xorlw   0x01
        bz      label_114

label_116:                                                  ; address: 0x001990

        movlw   0x05
        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        movf    0xfd, W, B                                  ; reg: 0x0fd
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_085, 0x0                           ; dest: 0x0045a2
        movlb   0x0
        bcf     0x7e, 0x1, B                                ; reg: 0x07e
        bsf     0xbd, 0x0, B                                ; reg: 0x0bd
        call    function_112, 0x0                           ; dest: 0x0048a6

label_117:                                                  ; address: 0x0019a8

        movlb   0x0
        btfss   0x7e, 0x3, B                                ; reg: 0x07e
        bra     label_124                                   ; dest: 0x001a76
        bcf     (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bcf     0x7e, 0x5, B                                ; reg: 0x07e
        bsf     0x7e, 0x6, B                                ; reg: 0x07e
        clrf    0xa4, B                                     ; reg: 0x0a4
        movff   0x0a4, 0x0b0
        clrf    0x9a, B                                     ; reg: 0x09a
        bra     label_122                                   ; dest: 0x0019d6

label_118:                                                  ; address: 0x0019be

        movff   0x09b, 0x09a
        bra     label_123                                   ; dest: 0x0019e6

label_119:                                                  ; address: 0x0019c4

        movff   0x09c, 0x09a
        bra     label_123                                   ; dest: 0x0019e6

label_120:                                                  ; address: 0x0019ca

        movff   0x09d, 0x09a
        bra     label_123                                   ; dest: 0x0019e6

label_121:                                                  ; address: 0x0019d0

        movff   0x09e, 0x09a
        bra     label_123                                   ; dest: 0x0019e6

label_122:                                                  ; address: 0x0019d6

        movf    0x93, W, B                                  ; reg: 0x093
        bz      label_118
        xorlw   0x05
        bz      label_119
        xorlw   0x03
        bz      label_120
        xorlw   0x01
        bz      label_121

label_123:                                                  ; address: 0x0019e6

        movf    0x9a, W, B                                  ; reg: 0x09a
        addwf   0x6e, W, B                                  ; reg: 0x06e
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x00
        addwfc  0x6f, W, B                                  ; reg: 0x06f
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x00
        addwfc  0x70, W, B                                  ; reg: 0x070
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x00
        addwfc  0x71, W, B                                  ; reg: 0x071
        movwf   (Common_RAM + 16), A                        ; reg: 0x010
        call    function_055, 0x0                           ; dest: 0x003e0a
        movff   (Common_RAM + 13), (Common_RAM + 18)        ; reg1: 0x00d, reg2: 0x012
        movff   (Common_RAM + 14), (Common_RAM + 19)        ; reg1: 0x00e, reg2: 0x013
        movff   (Common_RAM + 15), (Common_RAM + 20)        ; reg1: 0x00f, reg2: 0x014
        movff   (Common_RAM + 16), (Common_RAM + 21)        ; reg1: 0x010, reg2: 0x015
        movlw   0x47
        movwf   (Common_RAM + 22), A                        ; reg: 0x016
        movlw   0xc9
        movwf   (Common_RAM + 23), A                        ; reg: 0x017
        movlw   0xeb
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x3d
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        call    function_017, 0x0                           ; dest: 0x002abc
        movff   (Common_RAM + 18), 0x0ed                    ; reg1: 0x012
        movff   (Common_RAM + 19), 0x0ee                    ; reg1: 0x013
        movff   (Common_RAM + 20), 0x0ef                    ; reg1: 0x014
        movff   (Common_RAM + 21), 0x0f0                    ; reg1: 0x015
        movff   0x0ed, (Common_RAM + 47)                    ; reg2: 0x02f
        movff   0x0ee, (Common_RAM + 48)                    ; reg2: 0x030
        movff   0x0ef, (Common_RAM + 49)                    ; reg2: 0x031
        movff   0x0f0, (Common_RAM + 50)                    ; reg2: 0x032
        call    function_016, 0x0                           ; dest: 0x00297e
        movff   (Common_RAM + 47), (Common_RAM + 85)        ; reg1: 0x02f, reg2: 0x055
        movff   (Common_RAM + 48), (Common_RAM + 86)        ; reg1: 0x030, reg2: 0x056
        movff   (Common_RAM + 49), (Common_RAM + 87)        ; reg1: 0x031, reg2: 0x057
        movff   (Common_RAM + 50), (Common_RAM + 88)        ; reg1: 0x032, reg2: 0x058
        call    function_081, 0x0                           ; dest: 0x0044e4
        movlw   0x05
        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        movf    0xfd, W, B                                  ; reg: 0x0fd
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_085, 0x0                           ; dest: 0x0045a2
        movlb   0x0
        bcf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0xbd, 0x0, B                                ; reg: 0x0bd
        call    function_112, 0x0                           ; dest: 0x0048a6

label_124:                                                  ; address: 0x001a76

        btfss   (Common_RAM + 94), 0x7, A                   ; reg: 0x05e
        bra     label_125                                   ; dest: 0x001a9c
        movlw   0x00
        clrf    (Common_RAM + 85), A                        ; reg: 0x055
        clrf    (Common_RAM + 86), A                        ; reg: 0x056
        clrf    (Common_RAM + 87), A                        ; reg: 0x057
        clrf    (Common_RAM + 88), A                        ; reg: 0x058
        call    function_081, 0x0                           ; dest: 0x0044e4
        call    function_084, 0x0                           ; dest: 0x004574
        call    function_126, 0x0                           ; dest: 0x00495e
        bcf     (Common_RAM + 94), 0x7, A                   ; reg: 0x05e
        movlb   0x0
        btfss   0x7e, 0x5, B                                ; reg: 0x07e
        btfsc   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bra     label_125                                   ; dest: 0x001a9c
        bsf     0x7e, 0x3, B                                ; reg: 0x07e

label_125:                                                  ; address: 0x001a9c

        movlb   0x0
        btfss   0x7e, 0x5, B                                ; reg: 0x07e
        bra     label_128                                   ; dest: 0x001aca
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bra     label_126                                   ; dest: 0x001ab6
        movlw   0x00
        clrf    (Common_RAM + 85), A                        ; reg: 0x055
        clrf    (Common_RAM + 86), A                        ; reg: 0x056
        clrf    (Common_RAM + 87), A                        ; reg: 0x057
        clrf    (Common_RAM + 88), A                        ; reg: 0x058
        call    function_081, 0x0                           ; dest: 0x0044e4
        bra     label_127                                   ; dest: 0x001ab8

label_126:                                                  ; address: 0x001ab6

        bsf     0x7e, 0x3, B                                ; reg: 0x07e

label_127:                                                  ; address: 0x001ab8

        movlw   0x05
        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        movf    0xfd, W, B                                  ; reg: 0x0fd
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_085, 0x0                           ; dest: 0x0045a2
        movlb   0x0
        bcf     0x7e, 0x5, B                                ; reg: 0x07e

label_128:                                                  ; address: 0x001aca

        btfss   0x7e, 0x6, B                                ; reg: 0x07e
        bra     label_141                                   ; dest: 0x001baa
        btfsc   0xa4, 0x0, B                                ; reg: 0x0a4
        bra     label_129                                   ; dest: 0x001ada
        movlw   0x5f
        movwf   0xf2, B                                     ; reg: 0x0f2
        movlw   0x1c
        bra     label_130                                   ; dest: 0x001ae0

label_129:                                                  ; address: 0x001ada

        movlw   0x5f
        movwf   0xf2, B                                     ; reg: 0x0f2
        movlw   0x08

label_130:                                                  ; address: 0x001ae0

        movwf   0xf1, B                                     ; reg: 0x0f1
        movff   0x0f1, (Common_RAM + 19)                    ; reg2: 0x013
        movff   0x0f2, (Common_RAM + 20)                    ; reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlb   0x0
        btfsc   0xa4, 0x1, B                                ; reg: 0x0a4
        bra     label_131                                   ; dest: 0x001afc
        movlw   0x5f
        movwf   0xf4, B                                     ; reg: 0x0f4
        movlw   0x44
        bra     label_132                                   ; dest: 0x001b02

label_131:                                                  ; address: 0x001afc

        movlw   0x5f
        movwf   0xf4, B                                     ; reg: 0x0f4
        movlw   0x30

label_132:                                                  ; address: 0x001b02

        movwf   0xf3, B                                     ; reg: 0x0f3
        movff   0x0f3, (Common_RAM + 19)                    ; reg2: 0x013
        movff   0x0f4, (Common_RAM + 20)                    ; reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlb   0x0
        btfsc   0xa4, 0x2, B                                ; reg: 0x0a4
        bra     label_133                                   ; dest: 0x001b1e
        movlw   0x5f
        movwf   0xf6, B                                     ; reg: 0x0f6
        movlw   0x6c
        bra     label_134                                   ; dest: 0x001b24

label_133:                                                  ; address: 0x001b1e

        movlw   0x5f
        movwf   0xf6, B                                     ; reg: 0x0f6
        movlw   0x58

label_134:                                                  ; address: 0x001b24

        movwf   0xf5, B                                     ; reg: 0x0f5
        movff   0x0f5, (Common_RAM + 19)                    ; reg2: 0x013
        movff   0x0f6, (Common_RAM + 20)                    ; reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlb   0x0
        btfsc   0xa4, 0x3, B                                ; reg: 0x0a4
        bra     label_135                                   ; dest: 0x001b40
        movlw   0x5f
        movwf   0xf8, B                                     ; reg: 0x0f8
        movlw   0x94
        bra     label_136                                   ; dest: 0x001b46

label_135:                                                  ; address: 0x001b40

        movlw   0x5f
        movwf   0xf8, B                                     ; reg: 0x0f8
        movlw   0x80

label_136:                                                  ; address: 0x001b46

        movwf   0xf7, B                                     ; reg: 0x0f7
        movff   0x0f7, (Common_RAM + 19)                    ; reg2: 0x013
        movff   0x0f8, (Common_RAM + 20)                    ; reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlb   0x0
        btfsc   0xa4, 0x4, B                                ; reg: 0x0a4
        bra     label_137                                   ; dest: 0x001b62
        movlw   0x5f
        movwf   0xfa, B                                     ; reg: 0x0fa
        movlw   0xbc
        bra     label_138                                   ; dest: 0x001b68

label_137:                                                  ; address: 0x001b62

        movlw   0x5f
        movwf   0xfa, B                                     ; reg: 0x0fa
        movlw   0xa8

label_138:                                                  ; address: 0x001b68

        movwf   0xf9, B                                     ; reg: 0x0f9
        movff   0x0f9, (Common_RAM + 19)                    ; reg2: 0x013
        movff   0x0fa, (Common_RAM + 20)                    ; reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlb   0x0
        btfsc   0xa4, 0x5, B                                ; reg: 0x0a4
        bra     label_139                                   ; dest: 0x001b84
        movlw   0x5f
        movwf   0xfc, B                                     ; reg: 0x0fc
        movlw   0xe4
        bra     label_140                                   ; dest: 0x001b8a

label_139:                                                  ; address: 0x001b84

        movlw   0x5f
        movwf   0xfc, B                                     ; reg: 0x0fc
        movlw   0xd0

label_140:                                                  ; address: 0x001b8a

        movwf   0xfb, B                                     ; reg: 0x0fb
        movff   0x0fb, (Common_RAM + 19)                    ; reg2: 0x013
        movff   0x0fc, (Common_RAM + 20)                    ; reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlw   0x05
        movlb   0x0
        movwf   0xc1, B                                     ; reg: 0x0c1
        movf    0xfd, W, B                                  ; reg: 0x0fd
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_085, 0x0                           ; dest: 0x0045a2
        movlb   0x0
        bcf     0x7e, 0x6, B                                ; reg: 0x07e

label_141:                                                  ; address: 0x001baa

        btfss   0x7e, 0x4, B                                ; reg: 0x07e
        bra     label_142                                   ; dest: 0x001bc8
        call    function_008, 0x0                           ; dest: 0x002100
        movlb   0x0
        bcf     0x7e, 0x4, B                                ; reg: 0x07e
        bsf     0xbd, 0x1, B                                ; reg: 0x0bd
        movlw   0x05
        movwf   0xc1, B                                     ; reg: 0x0c1
        movf    0xfd, W, B                                  ; reg: 0x0fd
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_085, 0x0                           ; dest: 0x0045a2
        call    function_112, 0x0                           ; dest: 0x0048a6

label_142:                                                  ; address: 0x001bc8

        movlb   0x0
        btfss   0x7f, 0x0, B                                ; reg: 0x07f
        bra     label_143                                   ; dest: 0x001bd6
        bcf     0x7f, 0x0, B                                ; reg: 0x07f
        bsf     0xbd, 0x2, B                                ; reg: 0x0bd
        call    function_112, 0x0                           ; dest: 0x0048a6

label_143:                                                  ; address: 0x001bd6

        movlb   0x0
        btfss   0x7f, 0x1, B                                ; reg: 0x07f
        bra     label_144                                   ; dest: 0x001be4
        bcf     0x7f, 0x1, B                                ; reg: 0x07f
        bsf     0xbd, 0x2, B                                ; reg: 0x0bd
        call    function_112, 0x0                           ; dest: 0x0048a6

label_144:                                                  ; address: 0x001be4

        return  0x0

function_006:                                               ; address: 0x001be6

        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        bra     label_191                                   ; dest: 0x001e78

label_145:                                                  ; address: 0x001bea

        call    function_109, 0x0                           ; dest: 0x004872
        iorlw   0x00
        bnz     label_146
        bra     label_192                                   ; dest: 0x001e7c

label_146:                                                  ; address: 0x001bf4

        call    function_087, 0x0                           ; dest: 0x0045fa
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        movlw   0x7f
        cpfsgt  (Common_RAM + 10), A                        ; reg: 0x00a
        bra     label_150                                   ; dest: 0x001c42
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        xorlw   0xb0
        bnz     label_147
        movlw   0x01
        movwf   0x98, B                                     ; reg: 0x098
        bcf     (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        bra     label_149                                   ; dest: 0x001c36

label_147:                                                  ; address: 0x001c0e

        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        xorlw   0xb1
        bnz     label_148
        movlw   0x01
        movwf   0x98, B                                     ; reg: 0x098
        bsf     (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        bra     label_149                                   ; dest: 0x001c36

label_148:                                                  ; address: 0x001c1c

        clrf    0x98, B                                     ; reg: 0x098
        bcf     (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        movff   (Common_RAM + 10), (Common_RAM + 5)         ; reg1: 0x00a, reg2: 0x005
        movlw   0xf0
        andwf   (Common_RAM + 5), F, A                      ; reg: 0x005
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        xorlw   0xb0
        bnz     label_149
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        xorlw   0xbf
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        decf    (Common_RAM + 10), F, A                     ; reg: 0x00a

label_149:                                                  ; address: 0x001c36

        btfsc   (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        bra     label_193                                   ; dest: 0x001e80
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        call    function_111, 0x0                           ; dest: 0x004896
        bra     label_193                                   ; dest: 0x001e80

label_150:                                                  ; address: 0x001c42

        btfsc   (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        bra     label_151                                   ; dest: 0x001c52
        movlw   0x02
        subwf   0x98, W, B                                  ; reg: 0x098
        bc      label_151
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        call    function_111, 0x0                           ; dest: 0x004896

label_151:                                                  ; address: 0x001c52

        movlb   0x0
        movf    0x98, W, B                                  ; reg: 0x098
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        incf    0x98, F, B                                  ; reg: 0x098
        movlw   0x02
        subwf   0x98, W, B                                  ; reg: 0x098
        bc      label_152
        bra     label_193                                   ; dest: 0x001e80

label_152:                                                  ; address: 0x001c62

        movf    0x98, W, B                                  ; reg: 0x098
        xorlw   0x02
        bnz     label_153
        movff   (Common_RAM + 10), 0x0a2                    ; reg1: 0x00a
        bra     label_193                                   ; dest: 0x001e80

label_153:                                                  ; address: 0x001c6e

        movff   (Common_RAM + 10), 0x0a3                    ; reg1: 0x00a
        movff   (Common_RAM + 10), 0x0bc                    ; reg1: 0x00a
        bsf     (Common_RAM + 94), 0x6, A                   ; reg: 0x05e
        movlw   0x01
        movwf   0x98, B                                     ; reg: 0x098
        bra     label_185                                   ; dest: 0x001e2e

label_154:                                                  ; address: 0x001c7e

        movlw   0x01
        btfsc   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        movlw   0x00
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        rlncf   (Common_RAM + 5), F, A                      ; reg: 0x005
        rlncf   (Common_RAM + 5), F, A                      ; reg: 0x005
        movf    0x7e, W, B                                  ; reg: 0x07e
        xorwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        andlw   0xfb
        xorwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        movwf   0x7e, B                                     ; reg: 0x07e
        btfsc   0x7e, 0x2, B                                ; reg: 0x07e
        bsf     (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_190                                   ; dest: 0x001e6c

label_155:                                                  ; address: 0x001c9a

        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_156                                   ; dest: 0x001ca2
        bsf     0x7e, 0x2, B                                ; reg: 0x07e
        bra     label_157                                   ; dest: 0x001ca6

label_156:                                                  ; address: 0x001ca2

        movlb   0x0
        bcf     0x7e, 0x2, B                                ; reg: 0x07e

label_157:                                                  ; address: 0x001ca6

        btfsc   0x7e, 0x2, B                                ; reg: 0x07e
        bcf     (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_190                                   ; dest: 0x001e6c

label_158:                                                  ; address: 0x001cac

        btfsc   0x94, 0x3, B                                ; reg: 0x094
        bra     label_165                                   ; dest: 0x001cd6
        bsf     (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x01
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x00
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        btfss   (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        bra     label_159                                   ; dest: 0x001cc2
        movlw   0x01
        bra     label_160                                   ; dest: 0x001cc4

label_159:                                                  ; address: 0x001cc2

        movlw   0x00

label_160:                                                  ; address: 0x001cc4

        xorwf   (Common_RAM + 5), F, A                      ; reg: 0x005
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2

label_161:                                                  ; address: 0x001cc8

        bsf     0x7e, 0x5, B                                ; reg: 0x07e

label_162:                                                  ; address: 0x001cca

        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bra     label_163                                   ; dest: 0x001cd2
        bsf     (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        bra     label_164                                   ; dest: 0x001cd4

label_163:                                                  ; address: 0x001cd2

        bcf     (Common_RAM + 94), 0x5, A                   ; reg: 0x05e

label_164:                                                  ; address: 0x001cd4

        bra     label_190                                   ; dest: 0x001e6c

label_165:                                                  ; address: 0x001cd6

        movlw   0x02
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x03
        movwf   0xbc, B                                     ; reg: 0x0bc
        bcf     0x94, 0x3, B                                ; reg: 0x094
        bra     label_190                                   ; dest: 0x001e6c

label_166:                                                  ; address: 0x001ce2

        btfsc   0x94, 0x3, B                                ; reg: 0x094
        bra     label_165                                   ; dest: 0x001cd6
        bcf     (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x01
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x00
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        btfss   (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        bra     label_159                                   ; dest: 0x001cc2
        movlw   0x01
        xorwf   (Common_RAM + 5), F, A                      ; reg: 0x005
        bnz     label_161
        bra     label_162                                   ; dest: 0x001cca

label_167:                                                  ; address: 0x001cfc

        movf    0xa3, W, B                                  ; reg: 0x0a3
        bz      label_155
        xorlw   0x01
        bz      label_154
        xorlw   0x03
        bz      label_158
        xorlw   0x01
        bz      label_166
        bra     label_190                                   ; dest: 0x001e6c

label_168:                                                  ; address: 0x001d0e

        call    function_050, 0x0                           ; dest: 0x003b96
        bra     label_190                                   ; dest: 0x001e6c

label_169:                                                  ; address: 0x001d14

        btfsc   0x94, 0x0, B                                ; reg: 0x094
        bra     label_170                                   ; dest: 0x001d22
        movff   0x0a3, 0x099
        movff   0x099, 0x0b3
        bra     label_190                                   ; dest: 0x001e6c

label_170:                                                  ; address: 0x001d22

        movff   0x099, 0x0bc
        bcf     0x94, 0x0, B                                ; reg: 0x094
        bra     label_190                                   ; dest: 0x001e6c

label_171:                                                  ; address: 0x001d2a

        btfsc   0x94, 0x1, B                                ; reg: 0x094
        bra     label_174                                   ; dest: 0x001d80
        movlw   0xa0
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        setf    (Common_RAM + 6), A                         ; reg: 0x006
        movf    0xa3, W, B                                  ; reg: 0x0a3
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        addwf   (Common_RAM + 7), F, A                      ; reg: 0x007
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        addwfc  (Common_RAM + 8), F, A                      ; reg: 0x008
        movff   (Common_RAM + 7), 0x06e                     ; reg1: 0x007
        movff   (Common_RAM + 8), 0x06f                     ; reg1: 0x008
        movlw   0x00
        btfsc   0x6f, 0x7, B                                ; reg: 0x06f
        movlw   0xff
        movwf   0x70, B                                     ; reg: 0x070
        movwf   0x71, B                                     ; reg: 0x071
        xorwf   0x69, W, B                                  ; reg: 0x069
        bnz     label_172
        movf    0x68, W, B                                  ; reg: 0x068
        xorwf   0x70, W, B                                  ; reg: 0x070
        bnz     label_172
        movf    0x67, W, B                                  ; reg: 0x067
        xorwf   0x6f, W, B                                  ; reg: 0x06f
        bnz     label_172
        movf    0x66, W, B                                  ; reg: 0x066
        xorwf   0x6e, W, B                                  ; reg: 0x06e

label_172:                                                  ; address: 0x001d68

        bnz     label_173
        bra     label_190                                   ; dest: 0x001e6c

label_173:                                                  ; address: 0x001d6c

        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        movff   0x06e, 0x066
        movff   0x06f, 0x067
        movff   0x070, 0x068
        movff   0x071, 0x069
        bra     label_190                                   ; dest: 0x001e6c

label_174:                                                  ; address: 0x001d80

        movf    0x6e, W, B                                  ; reg: 0x06e
        addlw   0x60
        movwf   0xbc, B                                     ; reg: 0x0bc
        bcf     0x94, 0x1, B                                ; reg: 0x094
        bra     label_190                                   ; dest: 0x001e6c

label_175:                                                  ; address: 0x001d8a

        movf    0xa3, W, B                                  ; reg: 0x0a3
        xorlw   0x29
        bnz     label_190
        call    function_103, 0x0                           ; dest: 0x0047fc
        bra     label_190                                   ; dest: 0x001e6c

label_176:                                                  ; address: 0x001d96

        movff   0x0a3, 0x060
        movf    0xa5, W, B                                  ; reg: 0x0a5
        xorwf   0x60, W, B                                  ; reg: 0x060
        bz      label_190
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x060, 0x0a5
        bra     label_190                                   ; dest: 0x001e6c

label_177:                                                  ; address: 0x001da8

        movff   0x0a3, 0x061
        movf    0x61, W, B                                  ; reg: 0x061
        xorwf   0xa6, W, B                                  ; reg: 0x0a6
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x061, 0x0a6
        bra     label_190                                   ; dest: 0x001e6c

label_178:                                                  ; address: 0x001dba

        movff   0x0a3, 0x062
        movf    0x62, W, B                                  ; reg: 0x062
        xorwf   0xa7, W, B                                  ; reg: 0x0a7
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x062, 0x0a7
        bra     label_190                                   ; dest: 0x001e6c

label_179:                                                  ; address: 0x001dcc

        movff   0x0a3, 0x063
        movf    0x63, W, B                                  ; reg: 0x063
        xorwf   0xa8, W, B                                  ; reg: 0x0a8
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x063, 0x0a8
        bra     label_190                                   ; dest: 0x001e6c

label_180:                                                  ; address: 0x001dde

        movff   0x0a3, 0x064
        movf    0x64, W, B                                  ; reg: 0x064
        xorwf   0xa9, W, B                                  ; reg: 0x0a9
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x064, 0x0a9
        bra     label_190                                   ; dest: 0x001e6c

label_181:                                                  ; address: 0x001df0

        movff   0x0a3, 0x065
        movf    0x65, W, B                                  ; reg: 0x065
        xorwf   0xaa, W, B                                  ; reg: 0x0aa
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        movff   0x065, 0x0aa
        bra     label_190                                   ; dest: 0x001e6c

label_182:                                                  ; address: 0x001e02

        btfsc   0x94, 0x4, B                                ; reg: 0x094
        bra     label_183                                   ; dest: 0x001e14
        movf    0xb8, W, B                                  ; reg: 0x0b8
        xorwf   0xa3, W, B                                  ; reg: 0x0a3
        bz      label_190
        movff   0x0a3, 0x0b8
        bsf     0x7f, 0x0, B                                ; reg: 0x07f
        bra     label_190                                   ; dest: 0x001e6c

label_183:                                                  ; address: 0x001e14

        movff   0x0b8, 0x0bc
        bcf     0x94, 0x4, B                                ; reg: 0x094
        bra     label_190                                   ; dest: 0x001e6c

label_184:                                                  ; address: 0x001e1c

        movff   0x0a3, 0x0c3
        movf    0xb2, W, B                                  ; reg: 0x0b2
        xorwf   0xc3, W, B                                  ; reg: 0x0c3
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0xbd, 0x0, B                                ; reg: 0x0bd
        movff   0x0c3, 0x0b2
        bra     label_190                                   ; dest: 0x001e6c

label_185:                                                  ; address: 0x001e2e

        movf    0xa2, W, B                                  ; reg: 0x0a2
        xorlw   0x03
        bnz     label_186
        bra     label_167                                   ; dest: 0x001cfc

label_186:                                                  ; address: 0x001e36

        xorlw   0x07
        bnz     label_187
        bra     label_168                                   ; dest: 0x001d0e

label_187:                                                  ; address: 0x001e3c

        xorlw   0x02
        bnz     label_188
        bra     label_169                                   ; dest: 0x001d14

label_188:                                                  ; address: 0x001e42

        xorlw   0x01
        bnz     label_189
        bra     label_171                                   ; dest: 0x001d2a

label_189:                                                  ; address: 0x001e48

        xorlw   0x17
        bz      label_175
        xorlw   0x07
        bz      label_176
        xorlw   0x0f
        bz      label_177
        xorlw   0x01
        bz      label_178
        xorlw   0x03
        bz      label_179
        xorlw   0x01
        bz      label_180
        xorlw   0x07
        bz      label_181
        xorlw   0x01
        bz      label_182
        xorlw   0x03
        bz      label_184

label_190:                                                  ; address: 0x001e6c

        btfss   (Common_RAM + 94), 0x6, A                   ; reg: 0x05e
        bra     label_193                                   ; dest: 0x001e80
        movlb   0x0
        movf    0xbc, W, B                                  ; reg: 0x0bc
        call    function_111, 0x0                           ; dest: 0x004896

label_191:                                                  ; address: 0x001e78

        bcf     (Common_RAM + 94), 0x6, A                   ; reg: 0x05e
        bra     label_193                                   ; dest: 0x001e80

label_192:                                                  ; address: 0x001e7c

        movlw   0x01
        movwf   (Common_RAM + 9), A                         ; reg: 0x009

label_193:                                                  ; address: 0x001e80

        movf    (Common_RAM + 9), W, A                      ; reg: 0x009
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        bra     label_145                                   ; dest: 0x001bea

function_007:                                               ; address: 0x001e88

        movlw   0x00
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x71, B                                     ; reg: 0x071
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x01
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x70, B                                     ; reg: 0x070
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x02
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x6f, B                                     ; reg: 0x06f
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x03
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x6e, B                                     ; reg: 0x06e
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x04
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x99, B                                     ; reg: 0x099
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x07
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x60, B                                     ; reg: 0x060
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x08
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x61, B                                     ; reg: 0x061
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x09
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x62, B                                     ; reg: 0x062
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0a
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x63, B                                     ; reg: 0x063
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0b
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x64, B                                     ; reg: 0x064
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0c
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x65, B                                     ; reg: 0x065
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0d
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movwf   (Common_RAM + 95), A                        ; reg: 0x05f
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x14
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0xc3, B                                     ; reg: 0x0c3
        movf    0x71, W, B                                  ; reg: 0x071
        xorlw   0x80
        addlw   0x80
        bnz     label_194
        movlw   0x00
        subwf   0x70, W, B                                  ; reg: 0x070
        bnz     label_194
        movlw   0x00
        subwf   0x6f, W, B                                  ; reg: 0x06f
        bnz     label_194
        movlw   0x13
        subwf   0x6e, W, B                                  ; reg: 0x06e

label_194:                                                  ; address: 0x001f54

        bnc     label_195
        movlw   0xa0
        movwf   0x6e, B                                     ; reg: 0x06e
        setf    0x6f, B                                     ; reg: 0x06f
        setf    0x70, B                                     ; reg: 0x070
        setf    0x71, B                                     ; reg: 0x071

label_195:                                                  ; address: 0x001f60

        movlw   0x08
        cpfsgt  0x99, B                                     ; reg: 0x099
        bra     label_196                                   ; dest: 0x001f6a
        movlw   0x01
        movwf   0x99, B                                     ; reg: 0x099

label_196:                                                  ; address: 0x001f6a

        movlw   0x03
        cpfsgt  0x60, B                                     ; reg: 0x060
        bra     label_197                                   ; dest: 0x001f72
        clrf    0x60, B                                     ; reg: 0x060

label_197:                                                  ; address: 0x001f72

        lfsr    0x2, 0x061
        movlw   0x03
        cpfsgt  INDF2, A                                    ; reg: 0xfdf
        bra     label_198                                   ; dest: 0x001f7e
        clrf    0x61, B                                     ; reg: 0x061

label_198:                                                  ; address: 0x001f7e

        lfsr    0x2, 0x062
        movlw   0x03
        cpfsgt  INDF2, A                                    ; reg: 0xfdf
        bra     label_199                                   ; dest: 0x001f8a
        clrf    0x62, B                                     ; reg: 0x062

label_199:                                                  ; address: 0x001f8a

        lfsr    0x2, 0x063
        movlw   0x03
        cpfsgt  INDF2, A                                    ; reg: 0xfdf
        bra     label_200                                   ; dest: 0x001f98
        movlw   0x01
        movwf   0x63, B                                     ; reg: 0x063

label_200:                                                  ; address: 0x001f98

        lfsr    0x2, 0x064
        movlw   0x03
        cpfsgt  INDF2, A                                    ; reg: 0xfdf
        bra     label_201                                   ; dest: 0x001fa6
        movlw   0x01
        movwf   0x64, B                                     ; reg: 0x064

label_201:                                                  ; address: 0x001fa6

        lfsr    0x2, 0x065
        movlw   0x03
        cpfsgt  INDF2, A                                    ; reg: 0xfdf
        bra     label_202                                   ; dest: 0x001fb4
        movlw   0x01
        movwf   0x64, B                                     ; reg: 0x064

label_202:                                                  ; address: 0x001fb4

        movlw   0x03
        cpfsgt  (Common_RAM + 95), A                        ; reg: 0x05f
        bra     label_203                                   ; dest: 0x001fbc
        movwf   (Common_RAM + 95), A                        ; reg: 0x05f

label_203:                                                  ; address: 0x001fbc

        movlw   0x04
        cpfsgt  0xc3, B                                     ; reg: 0x0c3
        bra     label_204                                   ; dest: 0x001fc6
        movlw   0x01
        movwf   0xc3, B                                     ; reg: 0x0c3

label_204:                                                  ; address: 0x001fc6

        movff   0x06e, 0x066
        movff   0x06f, 0x067
        movff   0x070, 0x068
        movff   0x071, 0x069
        movff   0x099, 0x0b3
        movff   0x060, 0x0a5
        movff   0x061, 0x0a6
        movff   0x062, 0x0a7
        movff   0x063, 0x0a8
        movff   0x064, 0x0a9
        movff   0x065, 0x0aa
        movff   0x0c3, 0x0b2
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0f
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0xb4, B                                     ; reg: 0x0b4
        incf    0xb4, W, B                                  ; reg: 0x0b4
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bcf     0xb4, 0x0, B                                ; reg: 0x0b4
        movff   0x0b4, 0x0b1
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0e
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0xb8, B                                     ; reg: 0x0b8
        movlw   0x03
        subwf   0xb8, W, B                                  ; reg: 0x0b8
        bc      label_205
        movlw   0x03
        movwf   0xb8, B                                     ; reg: 0x0b8

label_205:                                                  ; address: 0x002026

        movlw   0x04
        cpfsgt  0xb8, B                                     ; reg: 0x0b8
        bra     label_206                                   ; dest: 0x002030
        movlw   0x03
        movwf   0xb8, B                                     ; reg: 0x0b8

label_206:                                                  ; address: 0x002030

        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x10
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x9b, B                                     ; reg: 0x09b
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x11
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x9c, B                                     ; reg: 0x09c
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x12
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x9d, B                                     ; reg: 0x09d
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x13
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        movlb   0x0
        movwf   0x9e, B                                     ; reg: 0x09e
        movlw   0x12
        cpfsgt  0x9b, B                                     ; reg: 0x09b
        bra     label_207                                   ; dest: 0x002070
        clrf    0x9b, B                                     ; reg: 0x09b

label_207:                                                  ; address: 0x002070

        movlw   0x12
        cpfsgt  0x9c, B                                     ; reg: 0x09c
        bra     label_208                                   ; dest: 0x002078
        clrf    0x9c, B                                     ; reg: 0x09c

label_208:                                                  ; address: 0x002078

        movlw   0x12
        cpfsgt  0x9d, B                                     ; reg: 0x09d
        bra     label_209                                   ; dest: 0x002080
        clrf    0x9d, B                                     ; reg: 0x09d

label_209:                                                  ; address: 0x002080

        movlw   0x12
        cpfsgt  0x9e, B                                     ; reg: 0x09e
        bra     label_210                                   ; dest: 0x002088
        clrf    0x9e, B                                     ; reg: 0x09e

label_210:                                                  ; address: 0x002088

        movff   0x09b, 0x0ac
        movff   0x09c, 0x0ad
        movff   0x09d, 0x0ae
        movff   0x09e, 0x0af
        movlw   0x50
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a

label_211:                                                  ; address: 0x00209c

        movlb   0x1
        movlw   0xb0
        addwf   0x0a, W, A                                  ; reg: 0x10a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movff   (Common_RAM + 10), (Common_RAM + 3)         ; reg1: 0x00a, reg2: 0x003
        clrf    0x04, A                                     ; reg: 0x104
        call    function_110, 0x0                           ; dest: 0x004884
        movwf   INDF2, A                                    ; reg: 0xfdf
        incf    (Common_RAM + 10), F, A                     ; reg: 0x00a
        movlw   0x5e
        cpfsgt  (Common_RAM + 10), A                        ; reg: 0x00a
        bra     label_211                                   ; dest: 0x00209c
        movlw   0x60
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a

label_212:                                                  ; address: 0x0020c2

        movlb   0x2
        movlw   0x60
        addwf   0x0a, W, A                                  ; reg: 0x20a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movff   (Common_RAM + 10), (Common_RAM + 3)         ; reg1: 0x00a, reg2: 0x003
        clrf    0x04, A                                     ; reg: 0x204
        call    function_110, 0x0                           ; dest: 0x004884
        movwf   INDF2, A                                    ; reg: 0xfdf
        incf    (Common_RAM + 10), F, A                     ; reg: 0x00a
        movlw   0x7d
        cpfsgt  (Common_RAM + 10), A                        ; reg: 0x00a
        bra     label_212                                   ; dest: 0x0020c2
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x80
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movlw   0x02
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x81
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movlw   0x03
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        goto    function_094                                ; dest: 0x0046de

function_008:                                               ; address: 0x002100

        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0xd7
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movlw   0x04
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        call    function_097, 0x0                           ; dest: 0x00473e
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlb   0x0
        movlw   0xdb
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movlw   0x04
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        call    function_097, 0x0                           ; dest: 0x00473e
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlb   0x0
        movlw   0xdf
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movlw   0x04
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        call    function_097, 0x0                           ; dest: 0x00473e
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0xd9
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x04
        movwf   0x05, A                                     ; reg: 0x105
        call    function_097, 0x0                           ; dest: 0x00473e
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlb   0x0
        movlw   0xe3
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movlw   0x04
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        call    function_097, 0x0                           ; dest: 0x00473e
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0xdd
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x04
        movwf   0x05, A                                     ; reg: 0x105
        call    function_097, 0x0                           ; dest: 0x00473e
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0xe1
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x04
        movwf   0x05, A                                     ; reg: 0x105
        call    function_097, 0x0                           ; dest: 0x00473e
        call    function_113, 0x0                           ; dest: 0x0048b6
        clrf    (Common_RAM + 89), A                        ; reg: 0x059

label_213:                                                  ; address: 0x00217a

        movf    (Common_RAM + 89), W, A                     ; reg: 0x059
        movlb   0x0
        addlw   0x60
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        call    function_078, 0x0                           ; dest: 0x004448
        bra     label_220                                   ; dest: 0x0021c8

label_214:                                                  ; address: 0x00218c

        movff   0x0a0, 0x0d7
        movff   0x0b9, 0x0d8
        bra     label_221                                   ; dest: 0x0021e0

label_215:                                                  ; address: 0x002196

        movff   0x0a0, 0x0db
        movff   0x0b9, 0x0dc
        bra     label_221                                   ; dest: 0x0021e0

label_216:                                                  ; address: 0x0021a0

        movff   0x0a0, 0x0df
        movff   0x0b9, 0x0e0
        bra     label_221                                   ; dest: 0x0021e0

label_217:                                                  ; address: 0x0021aa

        movff   0x0a0, 0x1d9
        movff   0x0b9, 0x1da
        bra     label_221                                   ; dest: 0x0021e0

label_218:                                                  ; address: 0x0021b4

        movff   0x0a0, 0x0e4
        movff   0x0b9, 0x0e5
        bra     label_221                                   ; dest: 0x0021e0

label_219:                                                  ; address: 0x0021be

        movff   0x0a0, 0x1e0
        movff   0x0b9, 0x1e1
        bra     label_221                                   ; dest: 0x0021e0

label_220:                                                  ; address: 0x0021c8

        movf    (Common_RAM + 89), W, A                     ; reg: 0x059
        bz      label_214
        xorlw   0x01
        bz      label_215
        xorlw   0x03
        bz      label_216
        xorlw   0x01
        bz      label_217
        xorlw   0x07
        bz      label_218
        xorlw   0x01
        bz      label_219

label_221:                                                  ; address: 0x0021e0

        incf    (Common_RAM + 89), F, A                     ; reg: 0x059
        movlw   0x05
        cpfsgt  (Common_RAM + 89), A                        ; reg: 0x059
        bra     label_213                                   ; dest: 0x00217a
        clrf    (Common_RAM + 90), A                        ; reg: 0x05a
        bra     label_229                                   ; dest: 0x00226a

label_222:                                                  ; address: 0x0021ec

        movff   0x0d7, 0x06a
        movff   0x0d8, 0x06b
        movff   0x0d9, 0x06c
        movff   0x0da, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_223:                                                  ; address: 0x0021fe

        movff   0x0db, 0x06a
        movff   0x0dc, 0x06b
        movff   0x0dd, 0x06c
        movff   0x0de, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_224:                                                  ; address: 0x002210

        movff   0x0df, 0x06a
        movff   0x0e0, 0x06b
        movff   0x0e1, 0x06c
        movff   0x0e2, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_225:                                                  ; address: 0x002222

        movff   0x1d9, 0x06a
        movff   0x1da, 0x06b
        movff   0x1db, 0x06c
        movff   0x1dc, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_226:                                                  ; address: 0x002234

        movff   0x0e3, 0x06a
        movff   0x0e4, 0x06b
        movff   0x0e5, 0x06c
        movff   0x0e6, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_227:                                                  ; address: 0x002246

        movff   0x1dd, 0x06a
        movff   0x1de, 0x06b
        movff   0x1df, 0x06c
        movff   0x1e0, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_228:                                                  ; address: 0x002258

        movff   0x1e1, 0x06a
        movff   0x1e2, 0x06b
        movff   0x1e3, 0x06c
        movff   0x1e4, 0x06d
        bra     label_230                                   ; dest: 0x002286

label_229:                                                  ; address: 0x00226a

        movf    (Common_RAM + 90), W, A                     ; reg: 0x05a
        bz      label_222
        xorlw   0x01
        bz      label_223
        xorlw   0x03
        bz      label_224
        xorlw   0x01
        bz      label_225
        xorlw   0x07
        bz      label_226
        xorlw   0x01
        bz      label_227
        xorlw   0x03
        bz      label_228

label_230:                                                  ; address: 0x002286

        bsf     SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0

label_231:                                                  ; address: 0x002288

        btfsc   SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0
        bra     label_231                                   ; dest: 0x002288
        movlw   0x68
        call    function_056, 0x0                           ; dest: 0x003e68
        movlb   0x1
        movlw   0x0f
        addwf   0x5a, W, A                                  ; reg: 0x15a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        call    function_056, 0x0                           ; dest: 0x003e68
        clrf    (Common_RAM + 91), A                        ; reg: 0x05b

label_232:                                                  ; address: 0x0022a8

        movf    (Common_RAM + 91), W, A                     ; reg: 0x05b
        movlb   0x0
        addlw   0x6a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        cpfseq  INDF2, A                                    ; reg: 0xfdf
        bra     label_233                                   ; dest: 0x0022c2
        clrf    (Common_RAM + 85), A                        ; reg: 0x055
        clrf    (Common_RAM + 86), A                        ; reg: 0x056
        clrf    (Common_RAM + 87), A                        ; reg: 0x057
        movlw   0x3f
        bra     label_234                                   ; dest: 0x0022da

label_233:                                                  ; address: 0x0022c2

        movf    (Common_RAM + 91), W, A                     ; reg: 0x05b
        addlw   0x6a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x03
        cpfseq  INDF2, A                                    ; reg: 0xfdf
        bra     label_235                                   ; dest: 0x0022de
        clrf    (Common_RAM + 85), A                        ; reg: 0x055
        clrf    (Common_RAM + 86), A                        ; reg: 0x056
        movlw   0x80
        movwf   (Common_RAM + 87), A                        ; reg: 0x057
        movlw   0xbf

label_234:                                                  ; address: 0x0022da

        movwf   (Common_RAM + 88), A                        ; reg: 0x058
        bra     label_236                                   ; dest: 0x0022fc

label_235:                                                  ; address: 0x0022de

        movf    (Common_RAM + 91), W, A                     ; reg: 0x05b
        addlw   0x6a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        call    function_086, 0x0                           ; dest: 0x0045ce
        movff   (Common_RAM + 13), (Common_RAM + 85)        ; reg1: 0x00d, reg2: 0x055
        movff   (Common_RAM + 14), (Common_RAM + 86)        ; reg1: 0x00e, reg2: 0x056
        movff   (Common_RAM + 15), (Common_RAM + 87)        ; reg1: 0x00f, reg2: 0x057
        movff   (Common_RAM + 16), (Common_RAM + 88)        ; reg1: 0x010, reg2: 0x058

label_236:                                                  ; address: 0x0022fc

        movff   (Common_RAM + 85), (Common_RAM + 73)        ; reg1: 0x055, reg2: 0x049
        movff   (Common_RAM + 86), (Common_RAM + 74)        ; reg1: 0x056, reg2: 0x04a
        movff   (Common_RAM + 87), (Common_RAM + 75)        ; reg1: 0x057, reg2: 0x04b
        movff   (Common_RAM + 88), (Common_RAM + 76)        ; reg1: 0x058, reg2: 0x04c
        call    function_046, 0x0                           ; dest: 0x0039a6
        incf    (Common_RAM + 91), F, A                     ; reg: 0x05b
        movlw   0x03
        cpfsgt  (Common_RAM + 91), A                        ; reg: 0x05b
        bra     label_232                                   ; dest: 0x0022a8
        bsf     SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2

label_237:                                                  ; address: 0x00231a

        btfsc   SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2
        bra     label_237                                   ; dest: 0x00231a
        incf    (Common_RAM + 90), F, A                     ; reg: 0x05a
        movlw   0x06
        cpfsgt  (Common_RAM + 90), A                        ; reg: 0x05a
        bra     label_229                                   ; dest: 0x00226a
        retlw   0x06

function_009:                                               ; address: 0x002328

        movff   0x0c1, 0x15a
        bra     label_248                                   ; dest: 0x002472

label_238:                                                  ; address: 0x00232e

        movff   0x0c2, 0x15b
        movlw   0x02
        movwf   (Common_RAM + 3), A                         ; reg: 0x003

label_239:                                                  ; address: 0x002336

        movlw   0xbe
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        rcall   function_010                                ; dest: 0x0024ac
        movlw   0x1f
        cpfsgt  (Common_RAM + 3), A                         ; reg: 0x003
        bra     label_239                                   ; dest: 0x002336
        bra     label_252                                   ; dest: 0x0024a6

label_240:                                                  ; address: 0x00234a

        movff   0x0c2, 0x15b
        decf    0xc2, W, B                                  ; reg: 0x0c2
        bnz     label_241
        movff   0x0b7, 0x15c
        movff   0x0b8, 0x15d
        bra     label_252                                   ; dest: 0x0024a6

label_241:                                                  ; address: 0x00235c

        movf    0xc2, W, B                                  ; reg: 0x0c2
        xorlw   0x02
        bz      label_242
        bra     label_252                                   ; dest: 0x0024a6

label_242:                                                  ; address: 0x002364

        movff   0x0b5, 0x15e
        movlw   0x05
        movwf   (Common_RAM + 3), A                         ; reg: 0x003

label_243:                                                  ; address: 0x00236c

        movlw   0xfb
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        rcall   function_010                                ; dest: 0x0024ac
        movlw   0x13
        cpfsgt  (Common_RAM + 3), A                         ; reg: 0x003
        bra     label_243                                   ; dest: 0x00236c
        bra     label_252                                   ; dest: 0x0024a6

label_244:                                                  ; address: 0x002380

        movff   0x093, 0x15b
        movff   0x099, 0x15c
        movlb   0x1
        clrf    0x5d, B                                     ; reg: 0x15d
        clrf    0x5e, B                                     ; reg: 0x15e
        movff   0x071, 0x15f
        movff   0x070, 0x160
        movff   0x06f, 0x161
        movff   0x06e, 0x162
        movlw   0x00
        btfsc   0x5e, 0x4, A                                ; reg: 0x15e
        movlw   0x01
        movwf   0x63, B                                     ; reg: 0x163
        movlw   0x00
        movlb   0x0
        btfsc   0xa4, 0x0, B                                ; reg: 0x0a4
        movlw   0x01
        movlb   0x1
        movwf   0x64, B                                     ; reg: 0x164
        movlw   0x00
        movlb   0x0
        btfsc   0xa4, 0x1, B                                ; reg: 0x0a4
        movlw   0x01
        movlb   0x1
        movwf   0x65, B                                     ; reg: 0x165
        movlw   0x00
        movlb   0x0
        btfsc   0xa4, 0x2, B                                ; reg: 0x0a4
        movlw   0x01
        movlb   0x1
        movwf   0x66, B                                     ; reg: 0x166
        movlw   0x00
        movlb   0x0
        btfsc   0xa4, 0x3, B                                ; reg: 0x0a4
        movlw   0x01
        movlb   0x1
        movwf   0x68, B                                     ; reg: 0x168
        movlw   0x00
        movlb   0x0
        btfsc   0xa4, 0x4, B                                ; reg: 0x0a4
        movlw   0x01
        movlb   0x1
        movwf   0x69, B                                     ; reg: 0x169
        movlw   0x00
        movlb   0x0
        btfsc   0xa4, 0x5, B                                ; reg: 0x0a4
        movlw   0x01
        movlb   0x1
        movwf   0x6a, B                                     ; reg: 0x16a
        movff   0x060, 0x16c
        movff   0x061, 0x16d
        movff   0x062, 0x16e
        movff   0x063, 0x16f
        movff   0x064, 0x170
        movff   0x065, 0x171
        movff   0x0b4, 0x178
        bra     label_252                                   ; dest: 0x0024a6

label_245:                                                  ; address: 0x00240c

        movlw   0x03
        movlb   0x1
        movwf   0x5b, B                                     ; reg: 0x15b
        movlw   0x02
        movwf   0x5c, B                                     ; reg: 0x15c
        movlw   0x03
        movwf   0x5d, B                                     ; reg: 0x15d
        movff   0x099, 0x15e
        clrf    0x5f, B                                     ; reg: 0x15f
        clrf    0x60, B                                     ; reg: 0x160
        clrf    0x61, B                                     ; reg: 0x161
        movff   (Common_RAM + 95), 0x163                    ; reg1: 0x05f
        movlw   0x06
        movwf   0x64, B                                     ; reg: 0x164
        movlw   0x0f
        movwf   0x65, B                                     ; reg: 0x165
        movwf   0x66, B                                     ; reg: 0x166
        movwf   0x67, B                                     ; reg: 0x167
        movwf   0x68, B                                     ; reg: 0x168
        movwf   0x69, B                                     ; reg: 0x169
        movwf   0x6a, B                                     ; reg: 0x16a
        movlw   0x0a
        movwf   0x6b, B                                     ; reg: 0x16b
        movwf   0x6c, B                                     ; reg: 0x16c
        movwf   0x6d, B                                     ; reg: 0x16d
        movwf   0x6e, B                                     ; reg: 0x16e
        movwf   0x6f, B                                     ; reg: 0x16f
        movwf   0x70, B                                     ; reg: 0x170
        movlw   0x01
        movwf   0x71, B                                     ; reg: 0x171
        movwf   0x72, B                                     ; reg: 0x172
        movff   0x09b, 0x173
        movff   0x09c, 0x174
        movff   0x09d, 0x175
        movff   0x09e, 0x176
        bra     label_252                                   ; dest: 0x0024a6

label_246:                                                  ; address: 0x002460

        movff   0x11b, 0x15b
        bra     label_252                                   ; dest: 0x0024a6

label_247:                                                  ; address: 0x002466

        movlb   0x1
        clrf    0x5b, B                                     ; reg: 0x15b
        clrf    0x5c, B                                     ; reg: 0x15c
        clrf    0x5d, B                                     ; reg: 0x15d
        clrf    0x5e, B                                     ; reg: 0x15e
        bra     label_252                                   ; dest: 0x0024a6

label_248:                                                  ; address: 0x002472

        movlb   0x0
        movf    0xc1, W, B                                  ; reg: 0x0c1
        xorlw   0x03
        bnz     label_249
        bra     label_238                                   ; dest: 0x00232e

label_249:                                                  ; address: 0x00247c

        xorlw   0x07
        bnz     label_250
        bra     label_240                                   ; dest: 0x00234a

label_250:                                                  ; address: 0x002482

        xorlw   0x01
        bnz     label_251
        bra     label_244                                   ; dest: 0x002380

label_251:                                                  ; address: 0x002488

        xorlw   0x03
        bz      label_245
        xorlw   0x01
        bz      label_246
        xorlw   0x0f
        bz      label_246
        xorlw   0x01
        bz      label_246
        xorlw   0x03
        bz      label_246
        xorlw   0x01
        bz      label_246
        xorlw   0x07
        bz      label_246
        bra     label_247                                   ; dest: 0x002466

label_252:                                                  ; address: 0x0024a6

        movlb   0x0
        clrf    0xc1, B                                     ; reg: 0x0c1
        return  0x0

function_010:                                               ; address: 0x0024ac

        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movlw   0x5a
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   FSR1L, A                                    ; reg: 0xfe1
        clrf    FSR1H, A                                    ; reg: 0xfe2
        movlw   0x01
        addwfc  FSR1H, F, A                                 ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        incf    (Common_RAM + 3), F, A                      ; reg: 0x003
        return  0x0

function_011:                                               ; address: 0x0024c2

        movff   (Common_RAM + 32), (Common_RAM + 40)        ; reg1: 0x020, reg2: 0x028
        movff   (Common_RAM + 33), (Common_RAM + 41)        ; reg1: 0x021, reg2: 0x029
        movff   (Common_RAM + 34), (Common_RAM + 42)        ; reg1: 0x022, reg2: 0x02a
        movff   (Common_RAM + 35), (Common_RAM + 43)        ; reg1: 0x023, reg2: 0x02b
        movlw   0x18
        bra     label_254                                   ; dest: 0x0024d8

label_253:                                                  ; address: 0x0024d6

        rcall   function_013                                ; dest: 0x002650

label_254:                                                  ; address: 0x0024d8

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_253                                   ; dest: 0x0024d6
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 46), A                        ; reg: 0x02e
        movff   (Common_RAM + 36), (Common_RAM + 40)        ; reg1: 0x024, reg2: 0x028
        movff   (Common_RAM + 37), (Common_RAM + 41)        ; reg1: 0x025, reg2: 0x029
        movff   (Common_RAM + 38), (Common_RAM + 42)        ; reg1: 0x026, reg2: 0x02a
        movff   (Common_RAM + 39), (Common_RAM + 43)        ; reg1: 0x027, reg2: 0x02b
        movlw   0x18
        bra     label_256                                   ; dest: 0x0024f6

label_255:                                                  ; address: 0x0024f4

        rcall   function_013                                ; dest: 0x002650

label_256:                                                  ; address: 0x0024f6

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_255                                   ; dest: 0x0024f4
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 45), A                        ; reg: 0x02d
        movf    (Common_RAM + 46), W, A                     ; reg: 0x02e
        bz      label_257
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        subwf   (Common_RAM + 46), W, A                     ; reg: 0x02e
        bc      label_258
        movf    (Common_RAM + 46), W, A                     ; reg: 0x02e
        subwf   (Common_RAM + 45), W, A                     ; reg: 0x02d
        movwf   (Common_RAM + 40), A                        ; reg: 0x028
        movlw   0x21
        subwf   (Common_RAM + 40), W, A                     ; reg: 0x028
        bnc     label_258

label_257:                                                  ; address: 0x002514

        movff   (Common_RAM + 36), (Common_RAM + 32)        ; reg1: 0x024, reg2: 0x020
        movff   (Common_RAM + 37), (Common_RAM + 33)        ; reg1: 0x025, reg2: 0x021
        movff   (Common_RAM + 38), (Common_RAM + 34)        ; reg1: 0x026, reg2: 0x022
        movff   (Common_RAM + 39), (Common_RAM + 35)        ; reg1: 0x027, reg2: 0x023
        bra     label_272                                   ; dest: 0x00263c

label_258:                                                  ; address: 0x002526

        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        bz      label_259
        movf    (Common_RAM + 46), W, A                     ; reg: 0x02e
        subwf   (Common_RAM + 45), W, A                     ; reg: 0x02d
        bc      label_260
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        subwf   (Common_RAM + 46), W, A                     ; reg: 0x02e
        movwf   (Common_RAM + 40), A                        ; reg: 0x028
        movlw   0x21
        subwf   (Common_RAM + 40), W, A                     ; reg: 0x028
        bnc     label_260

label_259:                                                  ; address: 0x00253c

        movff   (Common_RAM + 32), (Common_RAM + 32)        ; reg1: 0x020, reg2: 0x020
        movff   (Common_RAM + 33), (Common_RAM + 33)        ; reg1: 0x021, reg2: 0x021
        movff   (Common_RAM + 34), (Common_RAM + 34)        ; reg1: 0x022, reg2: 0x022
        movff   (Common_RAM + 35), (Common_RAM + 35)        ; reg1: 0x023, reg2: 0x023
        bra     label_272                                   ; dest: 0x00263c

label_260:                                                  ; address: 0x00254e

        movlw   0x06
        movwf   (Common_RAM + 44), A                        ; reg: 0x02c
        btfsc   (Common_RAM + 35), 0x7, A                   ; reg: 0x023
        bsf     (Common_RAM + 44), 0x7, A                   ; reg: 0x02c
        btfsc   (Common_RAM + 39), 0x7, A                   ; reg: 0x027
        bsf     (Common_RAM + 44), 0x6, A                   ; reg: 0x02c
        bsf     (Common_RAM + 34), 0x7, A                   ; reg: 0x022
        clrf    (Common_RAM + 35), A                        ; reg: 0x023
        bsf     (Common_RAM + 38), 0x7, A                   ; reg: 0x026
        clrf    (Common_RAM + 39), A                        ; reg: 0x027
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        subwf   (Common_RAM + 46), W, A                     ; reg: 0x02e
        bc      label_264

label_261:                                                  ; address: 0x002568

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 36), F, A                     ; reg: 0x024
        rlcf    (Common_RAM + 37), F, A                     ; reg: 0x025
        rlcf    (Common_RAM + 38), F, A                     ; reg: 0x026
        rlcf    (Common_RAM + 39), F, A                     ; reg: 0x027
        decf    (Common_RAM + 45), F, A                     ; reg: 0x02d
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        xorwf   (Common_RAM + 46), W, A                     ; reg: 0x02e
        bz      label_263
        decf    (Common_RAM + 44), F, A                     ; reg: 0x02c
        movff   (Common_RAM + 44), (Common_RAM + 40)        ; reg1: 0x02c, reg2: 0x028
        movlw   0x07
        andwf   (Common_RAM + 40), F, A                     ; reg: 0x028
        bz      label_263
        bra     label_261                                   ; dest: 0x002568

label_262:                                                  ; address: 0x002588

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 35), F, A                     ; reg: 0x023
        rrcf    (Common_RAM + 34), F, A                     ; reg: 0x022
        rrcf    (Common_RAM + 33), F, A                     ; reg: 0x021
        rrcf    (Common_RAM + 32), F, A                     ; reg: 0x020
        incf    (Common_RAM + 46), F, A                     ; reg: 0x02e

label_263:                                                  ; address: 0x002594

        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        cpfseq  (Common_RAM + 46), A                        ; reg: 0x02e
        bra     label_262                                   ; dest: 0x002588
        bra     label_268                                   ; dest: 0x0025d4

label_264:                                                  ; address: 0x00259c

        movf    (Common_RAM + 46), W, A                     ; reg: 0x02e
        subwf   (Common_RAM + 45), W, A                     ; reg: 0x02d
        bc      label_268

label_265:                                                  ; address: 0x0025a2

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 32), F, A                     ; reg: 0x020
        rlcf    (Common_RAM + 33), F, A                     ; reg: 0x021
        rlcf    (Common_RAM + 34), F, A                     ; reg: 0x022
        rlcf    (Common_RAM + 35), F, A                     ; reg: 0x023
        decf    (Common_RAM + 46), F, A                     ; reg: 0x02e
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        xorwf   (Common_RAM + 46), W, A                     ; reg: 0x02e
        bz      label_267
        decf    (Common_RAM + 44), F, A                     ; reg: 0x02c
        movff   (Common_RAM + 44), (Common_RAM + 40)        ; reg1: 0x02c, reg2: 0x028
        movlw   0x07
        andwf   (Common_RAM + 40), F, A                     ; reg: 0x028
        bz      label_267
        bra     label_265                                   ; dest: 0x0025a2

label_266:                                                  ; address: 0x0025c2

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 39), F, A                     ; reg: 0x027
        rrcf    (Common_RAM + 38), F, A                     ; reg: 0x026
        rrcf    (Common_RAM + 37), F, A                     ; reg: 0x025
        rrcf    (Common_RAM + 36), F, A                     ; reg: 0x024
        incf    (Common_RAM + 45), F, A                     ; reg: 0x02d

label_267:                                                  ; address: 0x0025ce

        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        cpfseq  (Common_RAM + 46), A                        ; reg: 0x02e
        bra     label_266                                   ; dest: 0x0025c2

label_268:                                                  ; address: 0x0025d4

        btfss   (Common_RAM + 44), 0x7, A                   ; reg: 0x02c
        bra     label_269                                   ; dest: 0x0025ea
        comf    (Common_RAM + 32), F, A                     ; reg: 0x020
        comf    (Common_RAM + 33), F, A                     ; reg: 0x021
        comf    (Common_RAM + 34), F, A                     ; reg: 0x022
        comf    (Common_RAM + 35), F, A                     ; reg: 0x023
        incf    (Common_RAM + 32), F, A                     ; reg: 0x020
        movlw   0x00
        addwfc  (Common_RAM + 33), F, A                     ; reg: 0x021
        addwfc  (Common_RAM + 34), F, A                     ; reg: 0x022
        addwfc  (Common_RAM + 35), F, A                     ; reg: 0x023

label_269:                                                  ; address: 0x0025ea

        btfss   (Common_RAM + 44), 0x6, A                   ; reg: 0x02c
        bra     label_270                                   ; dest: 0x0025f2
        comf    (Common_RAM + 36), F, A                     ; reg: 0x024
        rcall   function_012                                ; dest: 0x00263e

label_270:                                                  ; address: 0x0025f2

        clrf    (Common_RAM + 44), A                        ; reg: 0x02c
        movf    (Common_RAM + 32), W, A                     ; reg: 0x020
        addwf   (Common_RAM + 36), F, A                     ; reg: 0x024
        movf    (Common_RAM + 33), W, A                     ; reg: 0x021
        addwfc  (Common_RAM + 37), F, A                     ; reg: 0x025
        movf    (Common_RAM + 34), W, A                     ; reg: 0x022
        addwfc  (Common_RAM + 38), F, A                     ; reg: 0x026
        movf    (Common_RAM + 35), W, A                     ; reg: 0x023
        addwfc  (Common_RAM + 39), F, A                     ; reg: 0x027
        btfss   (Common_RAM + 39), 0x7, A                   ; reg: 0x027
        bra     label_271                                   ; dest: 0x002610
        comf    (Common_RAM + 36), F, A                     ; reg: 0x024
        rcall   function_012                                ; dest: 0x00263e
        movlw   0x01
        movwf   (Common_RAM + 44), A                        ; reg: 0x02c

label_271:                                                  ; address: 0x002610

        movff   (Common_RAM + 36), (Common_RAM + 3)         ; reg1: 0x024, reg2: 0x003
        movff   (Common_RAM + 37), (Common_RAM + 4)         ; reg1: 0x025, reg2: 0x004
        movff   (Common_RAM + 38), (Common_RAM + 5)         ; reg1: 0x026, reg2: 0x005
        movff   (Common_RAM + 39), (Common_RAM + 6)         ; reg1: 0x027, reg2: 0x006
        movff   (Common_RAM + 46), (Common_RAM + 7)         ; reg1: 0x02e, reg2: 0x007
        movff   (Common_RAM + 44), (Common_RAM + 8)         ; reg1: 0x02c, reg2: 0x008
        call    function_029, 0x0                           ; dest: 0x0030d8
        movff   (Common_RAM + 3), (Common_RAM + 32)         ; reg1: 0x003, reg2: 0x020
        movff   (Common_RAM + 4), (Common_RAM + 33)         ; reg1: 0x004, reg2: 0x021
        movff   (Common_RAM + 5), (Common_RAM + 34)         ; reg1: 0x005, reg2: 0x022
        movff   (Common_RAM + 6), (Common_RAM + 35)         ; reg1: 0x006, reg2: 0x023

label_272:                                                  ; address: 0x00263c

        return  0x0

function_012:                                               ; address: 0x00263e

        comf    (Common_RAM + 37), F, A                     ; reg: 0x025
        comf    (Common_RAM + 38), F, A                     ; reg: 0x026
        comf    (Common_RAM + 39), F, A                     ; reg: 0x027
        incf    (Common_RAM + 36), F, A                     ; reg: 0x024
        movlw   0x00
        addwfc  (Common_RAM + 37), F, A                     ; reg: 0x025
        addwfc  (Common_RAM + 38), F, A                     ; reg: 0x026
        addwfc  (Common_RAM + 39), F, A                     ; reg: 0x027
        retlw   0x00

function_013:                                               ; address: 0x002650

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 43), F, A                     ; reg: 0x02b
        rrcf    (Common_RAM + 42), F, A                     ; reg: 0x02a
        rrcf    (Common_RAM + 41), F, A                     ; reg: 0x029
        rrcf    (Common_RAM + 40), F, A                     ; reg: 0x028
        return  0x0

function_014:                                               ; address: 0x00265c

        movlb   0x0
        btfss   0x7e, 0x0, B                                ; reg: 0x07e
        bra     label_281                                   ; dest: 0x0027ee
        btfss   0xbd, 0x0, B                                ; reg: 0x0bd
        bra     label_273                                   ; dest: 0x0026cc
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x03
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x06e, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x02
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x06f, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x01
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x070, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        movlw   0x00
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        clrf    (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x071, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x04
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x099, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x0d
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   (Common_RAM + 95), (Common_RAM + 9)         ; reg1: 0x05f, reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x14
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x0c3, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        movlb   0x0
        bcf     0xbd, 0x0, B                                ; reg: 0x0bd

label_273:                                                  ; address: 0x0026cc

        btfss   0xbd, 0x1, B                                ; reg: 0x0bd
        bra     label_274                                   ; dest: 0x002728
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x07
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x060, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x08
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x061, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x09
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x062, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x0a
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x063, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x0b
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x064, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x0c
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x065, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        movlb   0x0
        bcf     0xbd, 0x1, B                                ; reg: 0x0bd

label_274:                                                  ; address: 0x002728

        btfss   0xbd, 0x2, B                                ; reg: 0x0bd
        bra     label_275                                   ; dest: 0x00274c
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x0f
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x0b4, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x0e
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x0b8, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        movlb   0x0
        bcf     0xbd, 0x2, B                                ; reg: 0x0bd

label_275:                                                  ; address: 0x00274c

        btfss   0xbd, 0x3, B                                ; reg: 0x0bd
        bra     label_276                                   ; dest: 0x00278c
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x10
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x09b, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x11
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x09c, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x12
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x09d, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x13
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   0x09e, (Common_RAM + 9)                     ; reg2: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        movlb   0x0
        bcf     0xbd, 0x3, B                                ; reg: 0x0bd

label_276:                                                  ; address: 0x00278c

        btfss   0xbd, 0x4, B                                ; reg: 0x0bd
        bra     label_278                                   ; dest: 0x0027bc
        movlw   0x50
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a

label_277:                                                  ; address: 0x002794

        movff   (Common_RAM + 10), (Common_RAM + 7)         ; reg1: 0x00a, reg2: 0x007
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlb   0x1
        movlw   0xb0
        addwf   0x0a, W, A                                  ; reg: 0x10a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movwf   0x09, A                                     ; reg: 0x109
        call    function_094, 0x0                           ; dest: 0x0046de
        incf    (Common_RAM + 10), F, A                     ; reg: 0x00a
        movlw   0x5e
        cpfsgt  (Common_RAM + 10), A                        ; reg: 0x00a
        bra     label_277                                   ; dest: 0x002794
        movlb   0x0
        bcf     0xbd, 0x4, B                                ; reg: 0x0bd

label_278:                                                  ; address: 0x0027bc

        btfss   0xbd, 0x5, B                                ; reg: 0x0bd
        bra     label_280                                   ; dest: 0x0027ec
        movlw   0x60
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a

label_279:                                                  ; address: 0x0027c4

        movff   (Common_RAM + 10), (Common_RAM + 7)         ; reg1: 0x00a, reg2: 0x007
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlb   0x2
        movlw   0x60
        addwf   0x0a, W, A                                  ; reg: 0x20a
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movwf   0x09, A                                     ; reg: 0x209
        call    function_094, 0x0                           ; dest: 0x0046de
        incf    (Common_RAM + 10), F, A                     ; reg: 0x00a
        movlw   0x7d
        cpfsgt  (Common_RAM + 10), A                        ; reg: 0x00a
        bra     label_279                                   ; dest: 0x0027c4
        movlb   0x0
        bcf     0xbd, 0x5, B                                ; reg: 0x0bd

label_280:                                                  ; address: 0x0027ec

        bcf     0x7e, 0x0, B                                ; reg: 0x07e

label_281:                                                  ; address: 0x0027ee

        return  0x0

function_015:                                               ; address: 0x0027f0

        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_313                                   ; dest: 0x00297c
        movlw   0x64
        movlb   0x0
        cpfsgt  0xbb, B                                     ; reg: 0x0bb
        bra     label_312                                   ; dest: 0x00297a
        clrf    0xbb, B                                     ; reg: 0x0bb
        bra     label_300                                   ; dest: 0x0028aa

label_282:                                                  ; address: 0x002800

        movf    0xb6, W, B                                  ; reg: 0x0b6
        addlw   0x08
        movwf   0xbe, B                                     ; reg: 0x0be
        bra     label_301                                   ; dest: 0x0028ce

label_283:                                                  ; address: 0x002808

        clrf    0x93, B                                     ; reg: 0x093
        bra     label_301                                   ; dest: 0x0028ce

label_284:                                                  ; address: 0x00280c

        movlw   0x01
        movwf   0x93, B                                     ; reg: 0x093
        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        bz      label_301
        movlw   0x05
        bra     label_299                                   ; dest: 0x0028a6

label_285:                                                  ; address: 0x002818

        movlw   0x02
        movwf   0x93, B                                     ; reg: 0x093
        decf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        bnz     label_286
        movlw   0x01
        movwf   0x93, B                                     ; reg: 0x093

label_286:                                                  ; address: 0x002824

        movlw   0x01
        cpfsgt  (Common_RAM + 95), A                        ; reg: 0x05f
        bra     label_301                                   ; dest: 0x0028ce
        movlw   0x06
        bra     label_299                                   ; dest: 0x0028a6

label_287:                                                  ; address: 0x00282e

        movlw   0x03
        movwf   0x93, B                                     ; reg: 0x093
        decf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        bnz     label_288
        movlw   0x02
        movwf   0x93, B                                     ; reg: 0x093

label_288:                                                  ; address: 0x00283a

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x02
        bnz     label_289
        movlw   0x01
        movwf   0x93, B                                     ; reg: 0x093

label_289:                                                  ; address: 0x002844

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x03
        bnz     label_301
        movlw   0x07
        bra     label_299                                   ; dest: 0x0028a6

label_290:                                                  ; address: 0x00284e

        movlw   0x04
        movwf   0x93, B                                     ; reg: 0x093
        decf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        bnz     label_291
        movlw   0x03
        movwf   0x93, B                                     ; reg: 0x093

label_291:                                                  ; address: 0x00285a

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x02
        bnz     label_292
        movlw   0x02
        movwf   0x93, B                                     ; reg: 0x093

label_292:                                                  ; address: 0x002864

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x03
        bnz     label_301
        movlw   0x01
        bra     label_299                                   ; dest: 0x0028a6

label_293:                                                  ; address: 0x00286e

        decf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        bnz     label_294
        movlw   0x04
        movwf   0x93, B                                     ; reg: 0x093

label_294:                                                  ; address: 0x002876

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x02
        bnz     label_295
        movlw   0x03
        movwf   0x93, B                                     ; reg: 0x093

label_295:                                                  ; address: 0x002880

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x03
        bnz     label_301
        movlw   0x02
        bra     label_299                                   ; dest: 0x0028a6

label_296:                                                  ; address: 0x00288a

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x02
        bnz     label_297
        movlw   0x04
        movwf   0x93, B                                     ; reg: 0x093

label_297:                                                  ; address: 0x002894

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x03
        bnz     label_301
        movlw   0x03
        bra     label_299                                   ; dest: 0x0028a6

label_298:                                                  ; address: 0x00289e

        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        xorlw   0x03
        bnz     label_301
        movlw   0x04

label_299:                                                  ; address: 0x0028a6

        movwf   0x93, B                                     ; reg: 0x093
        bra     label_301                                   ; dest: 0x0028ce

label_300:                                                  ; address: 0x0028aa

        movf    0x99, W, B                                  ; reg: 0x099
        bz      label_282
        xorlw   0x01
        bz      label_283
        xorlw   0x03
        bz      label_284
        xorlw   0x01
        bz      label_285
        xorlw   0x07
        bz      label_287
        xorlw   0x01
        bz      label_290
        xorlw   0x03
        bz      label_293
        xorlw   0x01
        bz      label_296
        xorlw   0x0f
        bz      label_298

label_301:                                                  ; address: 0x0028ce

        tstfsz  0x99, B                                     ; reg: 0x099
        bra     label_302                                   ; dest: 0x002902
        movff   0x0be, (Common_RAM + 6)                     ; reg2: 0x006
        movlw   0x0d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x13
        call    function_067, 0x0                           ; dest: 0x00423c
        movlb   0x0
        movwf   0xbe, B                                     ; reg: 0x0be
        tstfsz  0xbe, B                                     ; reg: 0x0be
        bra     label_304                                   ; dest: 0x00290a
        clrf    0x93, B                                     ; reg: 0x093
        movlw   0x0a
        cpfsgt  0xba, B                                     ; reg: 0x0ba
        bra     label_303                                   ; dest: 0x002906
        clrf    0xba, B                                     ; reg: 0x0ba
        movlw   0x04
        subwf   0xb6, W, B                                  ; reg: 0x0b6
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        incf    0xb6, F, B                                  ; reg: 0x0b6
        movf    0xb6, W, B                                  ; reg: 0x0b6
        xorlw   0x04
        bnz     label_310

label_302:                                                  ; address: 0x002902

        clrf    0xb6, B                                     ; reg: 0x0b6
        bra     label_310                                   ; dest: 0x00295c

label_303:                                                  ; address: 0x002906

        incf    0xba, F, B                                  ; reg: 0x0ba
        bra     label_310                                   ; dest: 0x00295c

label_304:                                                  ; address: 0x00290a

        tstfsz  0xb6, B                                     ; reg: 0x0b6
        bra     label_305                                   ; dest: 0x002912
        movlw   0x03
        movwf   0x93, B                                     ; reg: 0x093

label_305:                                                  ; address: 0x002912

        decf    0xb6, W, B                                  ; reg: 0x0b6
        bnz     label_306
        movlw   0x01
        movwf   0x93, B                                     ; reg: 0x093

label_306:                                                  ; address: 0x00291a

        movf    0xb6, W, B                                  ; reg: 0x0b6
        xorlw   0x02
        bnz     label_307
        movlw   0x02
        movwf   0x93, B                                     ; reg: 0x093

label_307:                                                  ; address: 0x002924

        movf    0xb6, W, B                                  ; reg: 0x0b6
        xorlw   0x03
        bnz     label_308
        movlw   0x04
        movwf   0x93, B                                     ; reg: 0x093

label_308:                                                  ; address: 0x00292e

        movlw   0x12
        call    function_067, 0x0                           ; dest: 0x00423c
        movlb   0x0
        movwf   0xbf, B                                     ; reg: 0x0bf
        movf    0xbf, W, B                                  ; reg: 0x0bf
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x01
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        movlw   0x00
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x01
        btfss   (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        movlw   0x00
        xorwf   (Common_RAM + 8), F, A                      ; reg: 0x008
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x5, B                                ; reg: 0x07e
        btfss   (Common_RAM + 94), 0x4, A                   ; reg: 0x05e
        bra     label_309                                   ; dest: 0x00295a
        bsf     (Common_RAM + 94), 0x5, A                   ; reg: 0x05e
        bra     label_310                                   ; dest: 0x00295c

label_309:                                                  ; address: 0x00295a

        bcf     (Common_RAM + 94), 0x5, A                   ; reg: 0x05e

label_310:                                                  ; address: 0x00295c

        movlb   0x0
        movf    0x93, W, B                                  ; reg: 0x093
        xorlw   0x02
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        btfsc   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        bra     label_311                                   ; dest: 0x00296c
        movff   0x0c3, 0x093

label_311:                                                  ; address: 0x00296c

        movf    0xab, W, B                                  ; reg: 0x0ab
        xorwf   0x93, W, B                                  ; reg: 0x093
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     0x7e, 0x1, B                                ; reg: 0x07e
        movff   0x093, 0x0ab
        bra     label_313                                   ; dest: 0x00297c

label_312:                                                  ; address: 0x00297a

        incf    0xbb, F, B                                  ; reg: 0x0bb

label_313:                                                  ; address: 0x00297c

        return  0x0

function_016:                                               ; address: 0x00297e

        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        clrf    (Common_RAM + 18), A                        ; reg: 0x012
        movlw   0x80
        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        movlw   0x44
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        movff   (Common_RAM + 47), (Common_RAM + 13)        ; reg1: 0x02f, reg2: 0x00d
        movff   (Common_RAM + 48), (Common_RAM + 14)        ; reg1: 0x030, reg2: 0x00e
        movff   (Common_RAM + 49), (Common_RAM + 15)        ; reg1: 0x031, reg2: 0x00f
        movff   (Common_RAM + 50), (Common_RAM + 16)        ; reg1: 0x032, reg2: 0x010
        call    function_022, 0x0                           ; dest: 0x002ca8
        movff   (Common_RAM + 13), (Common_RAM + 32)        ; reg1: 0x00d, reg2: 0x020
        movff   (Common_RAM + 14), (Common_RAM + 33)        ; reg1: 0x00e, reg2: 0x021
        movff   (Common_RAM + 15), (Common_RAM + 34)        ; reg1: 0x00f, reg2: 0x022
        movff   (Common_RAM + 16), (Common_RAM + 35)        ; reg1: 0x010, reg2: 0x023
        clrf    (Common_RAM + 36), A                        ; reg: 0x024
        clrf    (Common_RAM + 37), A                        ; reg: 0x025
        movlw   0x80
        movwf   (Common_RAM + 38), A                        ; reg: 0x026
        movlw   0x3f
        movwf   (Common_RAM + 39), A                        ; reg: 0x027
        call    function_011, 0x0                           ; dest: 0x0024c2
        movff   (Common_RAM + 32), (Common_RAM + 47)        ; reg1: 0x020, reg2: 0x02f
        movff   (Common_RAM + 33), (Common_RAM + 48)        ; reg1: 0x021, reg2: 0x030
        movff   (Common_RAM + 34), (Common_RAM + 49)        ; reg1: 0x022, reg2: 0x031
        movff   (Common_RAM + 35), (Common_RAM + 50)        ; reg1: 0x023, reg2: 0x032
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        movlw   0x2f
        call    function_057, 0x0                           ; dest: 0x003ec4
        movff   (Common_RAM + 47), (Common_RAM + 47)        ; reg1: 0x02f, reg2: 0x02f
        movff   (Common_RAM + 48), (Common_RAM + 48)        ; reg1: 0x030, reg2: 0x030
        movff   (Common_RAM + 49), (Common_RAM + 49)        ; reg1: 0x031, reg2: 0x031
        movff   (Common_RAM + 50), (Common_RAM + 50)        ; reg1: 0x032, reg2: 0x032
        return  0x0

function_017:                                               ; address: 0x002abc

        movff   (Common_RAM + 18), (Common_RAM + 26)        ; reg1: 0x012, reg2: 0x01a
        movff   (Common_RAM + 19), (Common_RAM + 27)        ; reg1: 0x013, reg2: 0x01b
        movff   (Common_RAM + 20), (Common_RAM + 28)        ; reg1: 0x014, reg2: 0x01c
        movff   (Common_RAM + 21), (Common_RAM + 29)        ; reg1: 0x015, reg2: 0x01d
        movlw   0x18
        bra     label_315                                   ; dest: 0x002ad2

label_314:                                                  ; address: 0x002ad0

        rcall   function_020                                ; dest: 0x002bac

label_315:                                                  ; address: 0x002ad2

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_314                                   ; dest: 0x002ad0
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        movwf   (Common_RAM + 30), A                        ; reg: 0x01e
        tstfsz  (Common_RAM + 30), A                        ; reg: 0x01e
        bra     label_316                                   ; dest: 0x002ae0
        bra     label_319                                   ; dest: 0x002b02

label_316:                                                  ; address: 0x002ae0

        movff   (Common_RAM + 22), (Common_RAM + 26)        ; reg1: 0x016, reg2: 0x01a
        movff   (Common_RAM + 23), (Common_RAM + 27)        ; reg1: 0x017, reg2: 0x01b
        movff   (Common_RAM + 24), (Common_RAM + 28)        ; reg1: 0x018, reg2: 0x01c
        movff   (Common_RAM + 25), (Common_RAM + 29)        ; reg1: 0x019, reg2: 0x01d
        movlw   0x18
        bra     label_318                                   ; dest: 0x002af6

label_317:                                                  ; address: 0x002af4

        rcall   function_020                                ; dest: 0x002bac

label_318:                                                  ; address: 0x002af6

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_317                                   ; dest: 0x002af4
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        movwf   (Common_RAM + 36), A                        ; reg: 0x024
        tstfsz  (Common_RAM + 36), A                        ; reg: 0x024
        bra     label_320                                   ; dest: 0x002b0c

label_319:                                                  ; address: 0x002b02

        clrf    (Common_RAM + 18), A                        ; reg: 0x012
        clrf    (Common_RAM + 19), A                        ; reg: 0x013
        clrf    (Common_RAM + 20), A                        ; reg: 0x014
        clrf    (Common_RAM + 21), A                        ; reg: 0x015
        bra     label_325                                   ; dest: 0x002b8c

label_320:                                                  ; address: 0x002b0c

        movf    (Common_RAM + 36), W, A                     ; reg: 0x024
        addlw   0x7b
        addwf   (Common_RAM + 30), F, A                     ; reg: 0x01e
        movff   (Common_RAM + 21), (Common_RAM + 36)        ; reg1: 0x015, reg2: 0x024
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        xorwf   (Common_RAM + 36), F, A                     ; reg: 0x024
        movlw   0x80
        andwf   (Common_RAM + 36), F, A                     ; reg: 0x024
        bsf     (Common_RAM + 20), 0x7, A                   ; reg: 0x014
        bsf     (Common_RAM + 24), 0x7, A                   ; reg: 0x018
        clrf    (Common_RAM + 25), A                        ; reg: 0x019
        clrf    (Common_RAM + 31), A                        ; reg: 0x01f
        clrf    (Common_RAM + 32), A                        ; reg: 0x020
        clrf    (Common_RAM + 33), A                        ; reg: 0x021
        clrf    (Common_RAM + 34), A                        ; reg: 0x022
        movlw   0x07
        movwf   (Common_RAM + 35), A                        ; reg: 0x023

label_321:                                                  ; address: 0x002b30

        btfss   (Common_RAM + 18), 0x0, A                   ; reg: 0x012
        bra     label_322                                   ; dest: 0x002b38
        movf    (Common_RAM + 22), W, A                     ; reg: 0x016
        rcall   function_018                                ; dest: 0x002b8e

label_322:                                                  ; address: 0x002b38

        rcall   function_019                                ; dest: 0x002b9e
        rlcf    (Common_RAM + 22), F, A                     ; reg: 0x016
        rlcf    (Common_RAM + 23), F, A                     ; reg: 0x017
        rlcf    (Common_RAM + 24), F, A                     ; reg: 0x018
        rlcf    (Common_RAM + 25), F, A                     ; reg: 0x019
        decfsz  (Common_RAM + 35), F, A                     ; reg: 0x023
        bra     label_321                                   ; dest: 0x002b30
        movlw   0x11
        movwf   (Common_RAM + 35), A                        ; reg: 0x023

label_323:                                                  ; address: 0x002b4a

        btfss   (Common_RAM + 18), 0x0, A                   ; reg: 0x012
        bra     label_324                                   ; dest: 0x002b52
        movf    (Common_RAM + 22), W, A                     ; reg: 0x016
        rcall   function_018                                ; dest: 0x002b8e

label_324:                                                  ; address: 0x002b52

        rcall   function_019                                ; dest: 0x002b9e
        rrcf    (Common_RAM + 34), F, A                     ; reg: 0x022
        rrcf    (Common_RAM + 33), F, A                     ; reg: 0x021
        rrcf    (Common_RAM + 32), F, A                     ; reg: 0x020
        rrcf    (Common_RAM + 31), F, A                     ; reg: 0x01f
        decfsz  (Common_RAM + 35), F, A                     ; reg: 0x023
        bra     label_323                                   ; dest: 0x002b4a
        movff   (Common_RAM + 31), (Common_RAM + 3)         ; reg1: 0x01f, reg2: 0x003
        movff   (Common_RAM + 32), (Common_RAM + 4)         ; reg1: 0x020, reg2: 0x004
        movff   (Common_RAM + 33), (Common_RAM + 5)         ; reg1: 0x021, reg2: 0x005
        movff   (Common_RAM + 34), (Common_RAM + 6)         ; reg1: 0x022, reg2: 0x006
        movff   (Common_RAM + 30), (Common_RAM + 7)         ; reg1: 0x01e, reg2: 0x007
        movff   (Common_RAM + 36), (Common_RAM + 8)         ; reg1: 0x024, reg2: 0x008
        call    function_029, 0x0                           ; dest: 0x0030d8
        movff   (Common_RAM + 3), (Common_RAM + 18)         ; reg1: 0x003, reg2: 0x012
        movff   (Common_RAM + 4), (Common_RAM + 19)         ; reg1: 0x004, reg2: 0x013
        movff   (Common_RAM + 5), (Common_RAM + 20)         ; reg1: 0x005, reg2: 0x014
        movff   (Common_RAM + 6), (Common_RAM + 21)         ; reg1: 0x006, reg2: 0x015

label_325:                                                  ; address: 0x002b8c

        return  0x0

function_018:                                               ; address: 0x002b8e

        addwf   (Common_RAM + 31), F, A                     ; reg: 0x01f
        movf    (Common_RAM + 23), W, A                     ; reg: 0x017
        addwfc  (Common_RAM + 32), F, A                     ; reg: 0x020
        movf    (Common_RAM + 24), W, A                     ; reg: 0x018
        addwfc  (Common_RAM + 33), F, A                     ; reg: 0x021
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        addwfc  (Common_RAM + 34), F, A                     ; reg: 0x022
        return  0x0

function_019:                                               ; address: 0x002b9e

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 21), F, A                     ; reg: 0x015
        rrcf    (Common_RAM + 20), F, A                     ; reg: 0x014
        rrcf    (Common_RAM + 19), F, A                     ; reg: 0x013
        rrcf    (Common_RAM + 18), F, A                     ; reg: 0x012
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

function_020:                                               ; address: 0x002bac

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 29), F, A                     ; reg: 0x01d
        rrcf    (Common_RAM + 28), F, A                     ; reg: 0x01c
        rrcf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        rrcf    (Common_RAM + 26), F, A                     ; reg: 0x01a
        return  0x0

function_021:                                               ; address: 0x002bb8

        tstfsz  0xc5, B                                     ; reg: 0x0c5
        bra     label_326                                   ; dest: 0x002bdc
        movff   0x082, (Common_RAM + 3)                     ; reg2: 0x003
        movff   0x083, (Common_RAM + 4)                     ; reg2: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0xc0
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movlb   0x3
        movlw   0x03
        movwf   0x0a, A                                     ; reg: 0x30a
        movlw   0x00
        movwf   0x09, A                                     ; reg: 0x309
        call    function_061, 0x0                           ; dest: 0x004028

label_326:                                                  ; address: 0x002bdc

        movlb   0x1
        movf    0x1b, W, B                                  ; reg: 0x11b
        bz      label_327
        clrf    (Common_RAM + 29), A                        ; reg: 0x01d
        movlw   0x02
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        bra     label_328                                   ; dest: 0x002bee

label_327:                                                  ; address: 0x002bea

        clrf    (Common_RAM + 28), A                        ; reg: 0x01c
        clrf    (Common_RAM + 29), A                        ; reg: 0x01d

label_328:                                                  ; address: 0x002bee

        movff   (Common_RAM + 28), (Common_RAM + 30)        ; reg1: 0x01c, reg2: 0x01e
        movlw   0x04
        movwf   (Common_RAM + 31), A                        ; reg: 0x01f

label_329:                                                  ; address: 0x002bf6

        movlw   0x1a
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x01
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        movf    (Common_RAM + 31), W, A                     ; reg: 0x01f
        addwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x00
        addwfc  (Common_RAM + 25), F, A                     ; reg: 0x019
        movf    (Common_RAM + 30), W, A                     ; reg: 0x01e
        subwf   (Common_RAM + 24), W, A                     ; reg: 0x018
        movwf   FSR2L, A                                    ; reg: 0xfd9
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        decf    (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        movwf   (Common_RAM + 26), A                        ; reg: 0x01a
        movlw   0x03
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlb   0x0
        movf    0xc5, W, B                                  ; reg: 0x0c5
        addwf   (Common_RAM + 26), F, A                     ; reg: 0x01a
        movlw   0x00
        addwfc  (Common_RAM + 27), F, A                     ; reg: 0x01b
        movf    (Common_RAM + 31), W, A                     ; reg: 0x01f
        addwf   (Common_RAM + 26), W, A                     ; reg: 0x01a
        movwf   FSR1L, A                                    ; reg: 0xfe1
        movlw   0x00
        addwfc  (Common_RAM + 27), W, A                     ; reg: 0x01b
        movwf   FSR1H, A                                    ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        incf    (Common_RAM + 31), F, A                     ; reg: 0x01f
        movlw   0x17
        cpfsgt  (Common_RAM + 31), A                        ; reg: 0x01f
        bra     label_329                                   ; dest: 0x002bf6
        movlw   0x18
        addwf   0xc5, F, B                                  ; reg: 0x0c5
        movlw   0xbf
        cpfsgt  0xc5, B                                     ; reg: 0x0c5
        bra     label_330                                   ; dest: 0x002ca6
        clrf    0xc5, B                                     ; reg: 0x0c5
        movlw   0x3f
        subwf   0x82, W, B                                  ; reg: 0x082
        movlw   0x5f
        subwfb  0x83, W, B                                  ; reg: 0x083
        bc      label_330
        movff   0x082, (Common_RAM + 3)                     ; reg2: 0x003
        movff   0x083, (Common_RAM + 4)                     ; reg2: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0xbf
        addwf   0x82, W, B                                  ; reg: 0x082
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x00
        addwfc  0x83, W, B                                  ; reg: 0x083
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        movff   (Common_RAM + 24), (Common_RAM + 7)         ; reg1: 0x018, reg2: 0x007
        movff   (Common_RAM + 25), (Common_RAM + 8)         ; reg1: 0x019, reg2: 0x008
        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        call    function_054, 0x0                           ; dest: 0x003dac
        movff   0x082, (Common_RAM + 3)                     ; reg2: 0x003
        movff   0x083, (Common_RAM + 4)                     ; reg2: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0xc0
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movlb   0x3
        movlw   0x03
        movwf   0x0a, A                                     ; reg: 0x30a
        movlw   0x00
        movwf   0x09, A                                     ; reg: 0x309
        call    function_025, 0x0                           ; dest: 0x002e6e
        movlw   0xc0
        movlb   0x0
        addwf   0x82, F, B                                  ; reg: 0x082
        movlw   0x00
        addwfc  0x83, F, B                                  ; reg: 0x083

label_330:                                                  ; address: 0x002ca6

        return  0x0

function_022:                                               ; address: 0x002ca8

        movff   (Common_RAM + 13), (Common_RAM + 21)        ; reg1: 0x00d, reg2: 0x015
        movff   (Common_RAM + 14), (Common_RAM + 22)        ; reg1: 0x00e, reg2: 0x016
        movff   (Common_RAM + 15), (Common_RAM + 23)        ; reg1: 0x00f, reg2: 0x017
        movff   (Common_RAM + 16), (Common_RAM + 24)        ; reg1: 0x010, reg2: 0x018
        movlw   0x18
        bra     label_332                                   ; dest: 0x002cbe

label_331:                                                  ; address: 0x002cbc

        rcall   function_023                                ; dest: 0x002d80

label_332:                                                  ; address: 0x002cbe

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_331                                   ; dest: 0x002cbc
        movf    (Common_RAM + 21), W, A                     ; reg: 0x015
        movwf   (Common_RAM + 30), A                        ; reg: 0x01e
        tstfsz  (Common_RAM + 30), A                        ; reg: 0x01e
        bra     label_333                                   ; dest: 0x002ccc
        bra     label_336                                   ; dest: 0x002cee

label_333:                                                  ; address: 0x002ccc

        movff   (Common_RAM + 17), (Common_RAM + 21)        ; reg1: 0x011, reg2: 0x015
        movff   (Common_RAM + 18), (Common_RAM + 22)        ; reg1: 0x012, reg2: 0x016
        movff   (Common_RAM + 19), (Common_RAM + 23)        ; reg1: 0x013, reg2: 0x017
        movff   (Common_RAM + 20), (Common_RAM + 24)        ; reg1: 0x014, reg2: 0x018
        movlw   0x18
        bra     label_335                                   ; dest: 0x002ce2

label_334:                                                  ; address: 0x002ce0

        rcall   function_023                                ; dest: 0x002d80

label_335:                                                  ; address: 0x002ce2

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_334                                   ; dest: 0x002ce0
        movf    (Common_RAM + 21), W, A                     ; reg: 0x015
        movwf   (Common_RAM + 31), A                        ; reg: 0x01f
        tstfsz  (Common_RAM + 31), A                        ; reg: 0x01f
        bra     label_337                                   ; dest: 0x002cf8

label_336:                                                  ; address: 0x002cee

        clrf    (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        clrf    (Common_RAM + 15), A                        ; reg: 0x00f
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        bra     label_340                                   ; dest: 0x002d7e

label_337:                                                  ; address: 0x002cf8

        movf    (Common_RAM + 31), W, A                     ; reg: 0x01f
        addlw   0x89
        subwf   (Common_RAM + 30), F, A                     ; reg: 0x01e
        movff   (Common_RAM + 16), (Common_RAM + 31)        ; reg1: 0x010, reg2: 0x01f
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        xorwf   (Common_RAM + 31), F, A                     ; reg: 0x01f
        movlw   0x80
        andwf   (Common_RAM + 31), F, A                     ; reg: 0x01f
        bsf     (Common_RAM + 15), 0x7, A                   ; reg: 0x00f
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        bsf     (Common_RAM + 19), 0x7, A                   ; reg: 0x013
        clrf    (Common_RAM + 20), A                        ; reg: 0x014
        movlw   0x20
        movwf   (Common_RAM + 29), A                        ; reg: 0x01d

label_338:                                                  ; address: 0x002d16

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 25), F, A                     ; reg: 0x019
        rlcf    (Common_RAM + 26), F, A                     ; reg: 0x01a
        rlcf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        rlcf    (Common_RAM + 28), F, A                     ; reg: 0x01c
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        subwf   (Common_RAM + 13), W, A                     ; reg: 0x00d
        movf    (Common_RAM + 18), W, A                     ; reg: 0x012
        subwfb  (Common_RAM + 14), W, A                     ; reg: 0x00e
        movf    (Common_RAM + 19), W, A                     ; reg: 0x013
        subwfb  (Common_RAM + 15), W, A                     ; reg: 0x00f
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        subwfb  (Common_RAM + 16), W, A                     ; reg: 0x010
        bnc     label_339
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        subwf   (Common_RAM + 13), F, A                     ; reg: 0x00d
        movf    (Common_RAM + 18), W, A                     ; reg: 0x012
        subwfb  (Common_RAM + 14), F, A                     ; reg: 0x00e
        movf    (Common_RAM + 19), W, A                     ; reg: 0x013
        subwfb  (Common_RAM + 15), F, A                     ; reg: 0x00f
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        subwfb  (Common_RAM + 16), F, A                     ; reg: 0x010
        bsf     (Common_RAM + 25), 0x0, A                   ; reg: 0x019

label_339:                                                  ; address: 0x002d44

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        rlcf    (Common_RAM + 14), F, A                     ; reg: 0x00e
        rlcf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        rlcf    (Common_RAM + 16), F, A                     ; reg: 0x010
        decfsz  (Common_RAM + 29), F, A                     ; reg: 0x01d
        bra     label_338                                   ; dest: 0x002d16
        movff   (Common_RAM + 25), (Common_RAM + 3)         ; reg1: 0x019, reg2: 0x003
        movff   (Common_RAM + 26), (Common_RAM + 4)         ; reg1: 0x01a, reg2: 0x004
        movff   (Common_RAM + 27), (Common_RAM + 5)         ; reg1: 0x01b, reg2: 0x005
        movff   (Common_RAM + 28), (Common_RAM + 6)         ; reg1: 0x01c, reg2: 0x006
        movff   (Common_RAM + 30), (Common_RAM + 7)         ; reg1: 0x01e, reg2: 0x007
        movff   (Common_RAM + 31), (Common_RAM + 8)         ; reg1: 0x01f, reg2: 0x008
        call    function_029, 0x0                           ; dest: 0x0030d8
        movff   (Common_RAM + 3), (Common_RAM + 13)         ; reg1: 0x003, reg2: 0x00d
        movff   (Common_RAM + 4), (Common_RAM + 14)         ; reg1: 0x004, reg2: 0x00e
        movff   (Common_RAM + 5), (Common_RAM + 15)         ; reg1: 0x005, reg2: 0x00f
        movff   (Common_RAM + 6), (Common_RAM + 16)         ; reg1: 0x006, reg2: 0x010

label_340:                                                  ; address: 0x002d7e

        return  0x0

function_023:                                               ; address: 0x002d80

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 24), F, A                     ; reg: 0x018
        rrcf    (Common_RAM + 23), F, A                     ; reg: 0x017
        rrcf    (Common_RAM + 22), F, A                     ; reg: 0x016
        rrcf    (Common_RAM + 21), F, A                     ; reg: 0x015
        return  0x0

function_024:                                               ; address: 0x002d8c

        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        bcf     LATB, LATB2, A                              ; reg: 0xf8a, bit: 2
        movlb   0x0
        clrf    0x88, B                                     ; reg: 0x088
        clrf    0x89, B                                     ; reg: 0x089
        bsf     ADCON0, GO, A                               ; reg: 0xfc2, bit: 1

label_341:                                                  ; address: 0x002d98

        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x0a
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        btfsc   ADCON0, GO, A                               ; reg: 0xfc2, bit: 1
        bra     label_342                                   ; dest: 0x002dbc
        movf    ADRESH, W, A                                ; reg: 0xfc4
        movwf   (Common_RAM + 93), A                        ; reg: 0x05d
        clrf    (Common_RAM + 92), A                        ; reg: 0x05c
        movf    ADRESL, W, A                                ; reg: 0xfc3
        addwf   (Common_RAM + 92), W, A                     ; reg: 0x05c
        movlb   0x0
        movwf   0x88, B                                     ; reg: 0x088
        movlw   0x00
        addwfc  (Common_RAM + 93), W, A                     ; reg: 0x05d
        movwf   0x89, B                                     ; reg: 0x089
        bsf     ADCON0, GO, A                               ; reg: 0xfc2, bit: 1

label_342:                                                  ; address: 0x002dbc

        movlw   0x36
        movlb   0x0
        subwf   0x88, W, B                                  ; reg: 0x088
        movlw   0x02
        subwfb  0x89, W, B                                  ; reg: 0x089
        bnc     label_341
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x46
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        clrf    SPBRGH, A                                   ; reg: 0xfb0
        movlw   0x7f
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bcf     OSCCON, SCS1, A                             ; reg: 0xfd3, bit: 1
        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        bcf     LATA, LATA6, A                              ; reg: 0xf89, bit: 6
        bcf     LATB, LATB3, A                              ; reg: 0xf8a, bit: 3
        call    function_128, 0x0                           ; dest: 0x004966
        bsf     TRISB, RB1, A                               ; reg: 0xf93, bit: 1
        bsf     TRISB, RB0, A                               ; reg: 0xf93, bit: 0
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x64
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        bsf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        movlw   0x05
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0xdc
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        bsf     TRISB, RB1, A                               ; reg: 0xf93, bit: 1
        bsf     TRISB, RB0, A                               ; reg: 0xf93, bit: 0
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x01
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        movlw   0x80
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movlw   0x08
        call    function_101, 0x0                           ; dest: 0x0047b2
        bsf     LATA, LATA6, A                              ; reg: 0xf89, bit: 6
        movlw   0x00
        clrf    (Common_RAM + 85), A                        ; reg: 0x055
        clrf    (Common_RAM + 86), A                        ; reg: 0x056
        clrf    (Common_RAM + 87), A                        ; reg: 0x057
        clrf    (Common_RAM + 88), A                        ; reg: 0x058
        call    function_081, 0x0                           ; dest: 0x0044e4
        call    function_084, 0x0                           ; dest: 0x004574
        bsf     LATB, LATB3, A                              ; reg: 0xf8a, bit: 3
        call    function_122, 0x0                           ; dest: 0x004942
        call    function_031, 0x0                           ; dest: 0x0032f8
        call    function_122, 0x0                           ; dest: 0x004942
        movlb   0x0
        bsf     0x7e, 0x1, B                                ; reg: 0x07e
        bsf     0x7e, 0x3, B                                ; reg: 0x07e
        bsf     0x7e, 0x4, B                                ; reg: 0x07e
        bsf     0x7f, 0x0, B                                ; reg: 0x07f
        bsf     0x7f, 0x1, B                                ; reg: 0x07f
        movlw   0x00
        call    function_005, 0x0                           ; dest: 0x0018ee
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x1b
        call    function_093, 0x0                           ; dest: 0x0046ba
        bcf     INTCON, T0IE, A                             ; reg: 0xff2, bit: 5
        bcf     T0CON, TMR0ON, A                            ; reg: 0xfd5, bit: 7
        movlw   0xa4
        movwf   TMR0H, A                                    ; reg: 0xfd7
        movlw   0x71
        movwf   TMR0L, A                                    ; reg: 0xfd6
        movlb   0x0
        clrf    0xa1, B                                     ; reg: 0x0a1
        bcf     0x94, 0x2, B                                ; reg: 0x094
        bsf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        goto    label_610                                   ; dest: 0x004918

function_025:                                               ; address: 0x002e6e

        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        movff   (Common_RAM + 3), (Common_RAM + 20)         ; reg1: 0x003, reg2: 0x014
        movff   (Common_RAM + 4), (Common_RAM + 21)         ; reg1: 0x004, reg2: 0x015
        movff   (Common_RAM + 5), (Common_RAM + 22)         ; reg1: 0x005, reg2: 0x016
        movff   (Common_RAM + 6), (Common_RAM + 23)         ; reg1: 0x006, reg2: 0x017
        movlw   0x05
        movwf   (Common_RAM + 11), A                        ; reg: 0x00b

label_343:                                                  ; address: 0x002e84

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        rrcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rrcf    (Common_RAM + 4), F, A                      ; reg: 0x004
        rrcf    (Common_RAM + 3), F, A                      ; reg: 0x003
        decfsz  (Common_RAM + 11), F, A                     ; reg: 0x00b
        bra     label_343                                   ; dest: 0x002e84
        movlw   0x05

label_344:                                                  ; address: 0x002e94

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 3), F, A                      ; reg: 0x003
        rlcf    (Common_RAM + 4), F, A                      ; reg: 0x004
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_344                                   ; dest: 0x002e94
        movlw   0x20
        addwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movlw   0x00
        addwfc  (Common_RAM + 4), F, A                      ; reg: 0x004
        addwfc  (Common_RAM + 5), F, A                      ; reg: 0x005
        addwfc  (Common_RAM + 6), F, A                      ; reg: 0x006
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        subwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        bra     label_351                                   ; dest: 0x002f44

label_345:                                                  ; address: 0x002eb6

        movff   (Common_RAM + 22), (Common_RAM + 19)        ; reg1: 0x016, reg2: 0x013
        movff   (Common_RAM + 21), (Common_RAM + 18)        ; reg1: 0x015, reg2: 0x012
        movff   (Common_RAM + 20), (Common_RAM + 17)        ; reg1: 0x014, reg2: 0x011
        bra     label_347                                   ; dest: 0x002ef6

label_346:                                                  ; address: 0x002ec4

        movff   (Common_RAM + 9), FSR2L                     ; reg1: 0x009, reg2: 0xfd9
        movff   (Common_RAM + 10), FSR2H                    ; reg1: 0x00a, reg2: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movff   (Common_RAM + 17), TBLPTRL                  ; reg1: 0x011, reg2: 0xff6
        movff   (Common_RAM + 18), TBLPTRH                  ; reg1: 0x012, reg2: 0xff7
        movff   (Common_RAM + 19), TBLPTRU                  ; reg1: 0x013, reg2: 0xff8
        movwf   TABLAT, A                                   ; reg: 0xff5
        tblwt*
        infsnz  (Common_RAM + 9), F, A                      ; reg: 0x009
        incf    (Common_RAM + 10), F, A                     ; reg: 0x00a
        incf    (Common_RAM + 17), F, A                     ; reg: 0x011
        movlw   0x00
        addwfc  (Common_RAM + 18), F, A                     ; reg: 0x012
        addwfc  (Common_RAM + 19), F, A                     ; reg: 0x013
        decf    (Common_RAM + 7), F, A                      ; reg: 0x007
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        decf    (Common_RAM + 8), F, A                      ; reg: 0x008
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        iorwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        bz      label_348

label_347:                                                  ; address: 0x002ef6

        decf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        incf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        bnz     label_346

label_348:                                                  ; address: 0x002efc

        movff   (Common_RAM + 19), (Common_RAM + 14)        ; reg1: 0x013, reg2: 0x00e
        movff   (Common_RAM + 18), (Common_RAM + 13)        ; reg1: 0x012, reg2: 0x00d
        movff   (Common_RAM + 17), (Common_RAM + 12)        ; reg1: 0x011, reg2: 0x00c
        movff   (Common_RAM + 22), (Common_RAM + 19)        ; reg1: 0x016, reg2: 0x013
        movff   (Common_RAM + 21), (Common_RAM + 18)        ; reg1: 0x015, reg2: 0x012
        movff   (Common_RAM + 20), (Common_RAM + 17)        ; reg1: 0x014, reg2: 0x011
        bsf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7
        bcf     EECON1, CFGS, A                             ; reg: 0xfa6, bit: 6
        bsf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        btfss   INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        bra     label_349                                   ; dest: 0x002f24
        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x01
        movwf   (Common_RAM + 16), A                        ; reg: 0x010

label_349:                                                  ; address: 0x002f24

        call    function_076, 0x0                           ; dest: 0x004406
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        bz      label_350
        bsf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        clrf    (Common_RAM + 16), A                        ; reg: 0x010

label_350:                                                  ; address: 0x002f32

        movlw   0x20
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        movwf   (Common_RAM + 21), A                        ; reg: 0x015
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        movwf   (Common_RAM + 22), A                        ; reg: 0x016
        clrf    (Common_RAM + 23), A                        ; reg: 0x017

label_351:                                                  ; address: 0x002f44

        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        iorwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        bra     label_345                                   ; dest: 0x002eb6

function_026:                                               ; address: 0x002f4e

        call    function_098, 0x0                           ; dest: 0x00475c
        tstfsz  0xcd, B                                     ; reg: 0x0cd
        bra     label_352                                   ; dest: 0x002f58
        bra     label_360                                   ; dest: 0x003018

label_352:                                                  ; address: 0x002f58

        btfsc   UIR, ACTVIF, A                              ; reg: 0xf68, bit: 2
        call    function_106, 0x0                           ; dest: 0x00483c
        btfsc   UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        bra     label_360                                   ; dest: 0x003018
        btfsc   UIR, URSTIF, A                              ; reg: 0xf68, bit: 0
        call    function_063, 0x0                           ; dest: 0x0040d6
        btfsc   UIR, IDLEIF, A                              ; reg: 0xf68, bit: 4
        call    function_096, 0x0                           ; dest: 0x004720
        movlw   0x03
        movlb   0x0
        subwf   0xcd, W, B                                  ; reg: 0x0cd
        bnc     label_360
        clrf    0xc4, B                                     ; reg: 0x0c4

label_353:                                                  ; address: 0x002f78

        btfss   UIR, TRNIF, A                               ; reg: 0xf68, bit: 3
        bra     label_360                                   ; dest: 0x003018
        movf    USTAT, W, A                                 ; reg: 0xf6c
        movff   USTAT, (Common_RAM + 6)                     ; reg1: 0xf6c, reg2: 0x006
        movlw   0x7c
        andwf   (Common_RAM + 6), F, A                      ; reg: 0x006
        bnz     label_357
        btfsc   USTAT, PPBI, A                              ; reg: 0xf6c, bit: 1
        bra     label_354                                   ; dest: 0x002f96
        movlw   0x04
        movlb   0x0
        movwf   0x7b, B                                     ; reg: 0x07b
        movlw   0x00
        bra     label_355                                   ; dest: 0x002f9c

label_354:                                                  ; address: 0x002f96

        movlw   0x04
        movlb   0x0
        movwf   0x7b, B                                     ; reg: 0x07b

label_355:                                                  ; address: 0x002f9c

        movlb   0x0
        movwf   0x7a, B                                     ; reg: 0x07a
        bcf     UIR, TRNIF, A                               ; reg: 0xf68, bit: 3
        movff   0x07a, FSR2L                                ; reg2: 0xfd9
        movff   0x07b, FSR2H                                ; reg2: 0xfda
        rrcf    INDF2, W, A                                 ; reg: 0xfdf
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        andlw   0x0f
        xorlw   0x0d
        bnz     label_359
        clrf    0x90, B                                     ; reg: 0x090

label_356:                                                  ; address: 0x002fb6

        lfsr    0x2, 0x002
        movf    0x7a, W, B                                  ; reg: 0x07a
        addwf   FSR2L, F, A                                 ; reg: 0xfd9
        movf    0x7b, W, B                                  ; reg: 0x07b
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movff   POSTINC2, (Common_RAM + 6)                  ; reg1: 0xfde, reg2: 0x006
        movff   POSTDEC2, (Common_RAM + 7)                  ; reg1: 0xfdd, reg2: 0x007
        movff   (Common_RAM + 6), FSR2L                     ; reg1: 0x006, reg2: 0xfd9
        movff   (Common_RAM + 7), FSR2H                     ; reg1: 0x007, reg2: 0xfda
        movf    0x90, W, B                                  ; reg: 0x090
        addlw   0xcf
        movwf   FSR1L, A                                    ; reg: 0xfe1
        clrf    FSR1H, A                                    ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        lfsr    0x2, 0x002
        movf    0x7a, W, B                                  ; reg: 0x07a
        addwf   FSR2L, F, A                                 ; reg: 0xfd9
        movf    0x7b, W, B                                  ; reg: 0x07b
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        incf    POSTINC2, F, A                              ; reg: 0xfde
        movlw   0x00
        addwfc  POSTDEC2, F, A                              ; reg: 0xfdd
        incf    0x90, F, B                                  ; reg: 0x090
        movlw   0x07
        cpfsgt  0x90, B                                     ; reg: 0x090
        bra     label_356                                   ; dest: 0x002fb6
        call    function_070, 0x0                           ; dest: 0x0042f4
        bra     label_359                                   ; dest: 0x00300e

label_357:                                                  ; address: 0x002ffe

        movf    USTAT, W, A                                 ; reg: 0xf6c
        xorlw   0x04
        bnz     label_358
        bcf     UIR, TRNIF, A                               ; reg: 0xf68, bit: 3
        call    function_077, 0x0                           ; dest: 0x004412
        bra     label_359                                   ; dest: 0x00300e

label_358:                                                  ; address: 0x00300c

        bcf     UIR, TRNIF, A                               ; reg: 0xf68, bit: 3

label_359:                                                  ; address: 0x00300e

        movlb   0x0
        incf    0xc4, F, B                                  ; reg: 0x0c4
        movlw   0x03
        cpfsgt  0xc4, B                                     ; reg: 0x0c4
        bra     label_353                                   ; dest: 0x002f78

label_360:                                                  ; address: 0x003018

        return  0x0

function_027:                                               ; address: 0x00301a

        movff   (Common_RAM + 37), (Common_RAM + 41)        ; reg1: 0x025, reg2: 0x029
        movff   (Common_RAM + 38), (Common_RAM + 42)        ; reg1: 0x026, reg2: 0x02a
        movff   (Common_RAM + 39), (Common_RAM + 43)        ; reg1: 0x027, reg2: 0x02b
        movff   (Common_RAM + 40), (Common_RAM + 44)        ; reg1: 0x028, reg2: 0x02c
        movlw   0x18
        bra     label_362                                   ; dest: 0x003030

label_361:                                                  ; address: 0x00302e

        rcall   function_028                                ; dest: 0x0030cc

label_362:                                                  ; address: 0x003030

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_361                                   ; dest: 0x00302e
        movf    (Common_RAM + 41), W, A                     ; reg: 0x029
        movwf   (Common_RAM + 46), A                        ; reg: 0x02e
        tstfsz  (Common_RAM + 46), A                        ; reg: 0x02e
        bra     label_364                                   ; dest: 0x003046

label_363:                                                  ; address: 0x00303c

        clrf    (Common_RAM + 37), A                        ; reg: 0x025
        clrf    (Common_RAM + 38), A                        ; reg: 0x026
        clrf    (Common_RAM + 39), A                        ; reg: 0x027
        clrf    (Common_RAM + 40), A                        ; reg: 0x028
        bra     label_373                                   ; dest: 0x0030ca

label_364:                                                  ; address: 0x003046

        movff   (Common_RAM + 37), (Common_RAM + 41)        ; reg1: 0x025, reg2: 0x029
        movff   (Common_RAM + 38), (Common_RAM + 42)        ; reg1: 0x026, reg2: 0x02a
        movff   (Common_RAM + 39), (Common_RAM + 43)        ; reg1: 0x027, reg2: 0x02b
        movff   (Common_RAM + 40), (Common_RAM + 44)        ; reg1: 0x028, reg2: 0x02c
        movlw   0x20
        bra     label_366                                   ; dest: 0x00305c

label_365:                                                  ; address: 0x00305a

        rcall   function_028                                ; dest: 0x0030cc

label_366:                                                  ; address: 0x00305c

        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_365                                   ; dest: 0x00305a
        movf    (Common_RAM + 41), W, A                     ; reg: 0x029
        movwf   (Common_RAM + 45), A                        ; reg: 0x02d
        bsf     (Common_RAM + 39), 0x7, A                   ; reg: 0x027
        clrf    (Common_RAM + 40), A                        ; reg: 0x028
        movlw   0x96
        subwf   (Common_RAM + 46), F, A                     ; reg: 0x02e
        btfss   (Common_RAM + 46), 0x7, A                   ; reg: 0x02e
        bra     label_368                                   ; dest: 0x00308e
        movf    (Common_RAM + 46), W, A                     ; reg: 0x02e
        xorlw   0x80
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0xe9
        xorlw   0x80
        subwf   (Common_RAM + 41), W, A                     ; reg: 0x029
        bnc     label_363

label_367:                                                  ; address: 0x00307e

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 40), F, A                     ; reg: 0x028
        rrcf    (Common_RAM + 39), F, A                     ; reg: 0x027
        rrcf    (Common_RAM + 38), F, A                     ; reg: 0x026
        rrcf    (Common_RAM + 37), F, A                     ; reg: 0x025
        incfsz  (Common_RAM + 46), F, A                     ; reg: 0x02e
        bra     label_367                                   ; dest: 0x00307e
        bra     label_371                                   ; dest: 0x0030a6

label_368:                                                  ; address: 0x00308e

        movlw   0x1f
        cpfsgt  (Common_RAM + 46), A                        ; reg: 0x02e
        bra     label_370                                   ; dest: 0x0030a2
        bra     label_363                                   ; dest: 0x00303c

label_369:                                                  ; address: 0x003096

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 37), F, A                     ; reg: 0x025
        rlcf    (Common_RAM + 38), F, A                     ; reg: 0x026
        rlcf    (Common_RAM + 39), F, A                     ; reg: 0x027
        rlcf    (Common_RAM + 40), F, A                     ; reg: 0x028
        decf    (Common_RAM + 46), F, A                     ; reg: 0x02e

label_370:                                                  ; address: 0x0030a2

        tstfsz  (Common_RAM + 46), A                        ; reg: 0x02e
        bra     label_369                                   ; dest: 0x003096

label_371:                                                  ; address: 0x0030a6

        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        bz      label_372
        comf    (Common_RAM + 40), F, A                     ; reg: 0x028
        comf    (Common_RAM + 39), F, A                     ; reg: 0x027
        comf    (Common_RAM + 38), F, A                     ; reg: 0x026
        negf    (Common_RAM + 37), A                        ; reg: 0x025
        movlw   0x00
        addwfc  (Common_RAM + 38), F, A                     ; reg: 0x026
        addwfc  (Common_RAM + 39), F, A                     ; reg: 0x027
        addwfc  (Common_RAM + 40), F, A                     ; reg: 0x028

label_372:                                                  ; address: 0x0030ba

        movff   (Common_RAM + 37), (Common_RAM + 37)        ; reg1: 0x025, reg2: 0x025
        movff   (Common_RAM + 38), (Common_RAM + 38)        ; reg1: 0x026, reg2: 0x026
        movff   (Common_RAM + 39), (Common_RAM + 39)        ; reg1: 0x027, reg2: 0x027
        movff   (Common_RAM + 40), (Common_RAM + 40)        ; reg1: 0x028, reg2: 0x028

label_373:                                                  ; address: 0x0030ca

        return  0x0

function_028:                                               ; address: 0x0030cc

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 44), F, A                     ; reg: 0x02c
        rrcf    (Common_RAM + 43), F, A                     ; reg: 0x02b
        rrcf    (Common_RAM + 42), F, A                     ; reg: 0x02a
        rrcf    (Common_RAM + 41), F, A                     ; reg: 0x029
        return  0x0

function_029:                                               ; address: 0x0030d8

        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        bz      label_374
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        iorwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        iorwf   (Common_RAM + 4), W, A                      ; reg: 0x004
        iorwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        bnz     label_376

label_374:                                                  ; address: 0x0030e6

        clrf    (Common_RAM + 3), A                         ; reg: 0x003
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        bra     label_382                                   ; dest: 0x003186

label_375:                                                  ; address: 0x0030f0

        incf    (Common_RAM + 7), F, A                      ; reg: 0x007
        rcall   function_030                                ; dest: 0x003188

label_376:                                                  ; address: 0x0030f4

        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        movlw   0xfe
        andwf   (Common_RAM + 6), W, A                      ; reg: 0x006
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        iorwf   (Common_RAM + 9), W, A                      ; reg: 0x009
        iorwf   (Common_RAM + 10), W, A                     ; reg: 0x00a
        iorwf   (Common_RAM + 11), W, A                     ; reg: 0x00b
        bz      label_378
        bra     label_375                                   ; dest: 0x0030f0

label_377:                                                  ; address: 0x00310c

        incf    (Common_RAM + 7), F, A                      ; reg: 0x007
        incf    (Common_RAM + 3), F, A                      ; reg: 0x003
        movlw   0x00
        addwfc  (Common_RAM + 4), F, A                      ; reg: 0x004
        addwfc  (Common_RAM + 5), F, A                      ; reg: 0x005
        addwfc  (Common_RAM + 6), F, A                      ; reg: 0x006
        rcall   function_030                                ; dest: 0x003188

label_378:                                                  ; address: 0x00311a

        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        iorwf   (Common_RAM + 9), W, A                      ; reg: 0x009
        iorwf   (Common_RAM + 10), W, A                     ; reg: 0x00a
        iorwf   (Common_RAM + 11), W, A                     ; reg: 0x00b
        bz      label_380
        bra     label_377                                   ; dest: 0x00310c

label_379:                                                  ; address: 0x003130

        decf    (Common_RAM + 7), F, A                      ; reg: 0x007
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 3), F, A                      ; reg: 0x003
        rlcf    (Common_RAM + 4), F, A                      ; reg: 0x004
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    (Common_RAM + 6), F, A                      ; reg: 0x006

label_380:                                                  ; address: 0x00313c

        btfss   (Common_RAM + 5), 0x7, A                    ; reg: 0x005
        bra     label_379                                   ; dest: 0x003130
        btfsc   (Common_RAM + 7), 0x0, A                    ; reg: 0x007
        bra     label_381                                   ; dest: 0x003148
        movlw   0x7f
        andwf   (Common_RAM + 5), F, A                      ; reg: 0x005

label_381:                                                  ; address: 0x003148

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 7), F, A                      ; reg: 0x007
        movff   (Common_RAM + 7), (Common_RAM + 9)          ; reg1: 0x007, reg2: 0x009
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        clrf    (Common_RAM + 12), A                        ; reg: 0x00c
        movff   (Common_RAM + 9), (Common_RAM + 12)         ; reg1: 0x009, reg2: 0x00c
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        movf    (Common_RAM + 9), W, A                      ; reg: 0x009
        iorwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        iorwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movf    (Common_RAM + 11), W, A                     ; reg: 0x00b
        iorwf   (Common_RAM + 5), F, A                      ; reg: 0x005
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        iorwf   (Common_RAM + 6), F, A                      ; reg: 0x006
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     (Common_RAM + 6), 0x7, A                    ; reg: 0x006
        movff   (Common_RAM + 3), (Common_RAM + 3)          ; reg1: 0x003, reg2: 0x003
        movff   (Common_RAM + 4), (Common_RAM + 4)          ; reg1: 0x004, reg2: 0x004
        movff   (Common_RAM + 5), (Common_RAM + 5)          ; reg1: 0x005, reg2: 0x005
        movff   (Common_RAM + 6), (Common_RAM + 6)          ; reg1: 0x006, reg2: 0x006

label_382:                                                  ; address: 0x003186

        return  0x0

function_030:                                               ; address: 0x003188

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        rrcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rrcf    (Common_RAM + 4), F, A                      ; reg: 0x004
        rrcf    (Common_RAM + 3), F, A                      ; reg: 0x003
        return  0x0

label_383:                                                  ; address: 0x003194

        movf    0xcf, W, B                                  ; reg: 0x0cf
        andlw   0x1f
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        decf    (Common_RAM + 3), W, A                      ; reg: 0x003
        bnz     label_399
        movf    0xd3, W, B                                  ; reg: 0x0d3
        bnz     label_399
        movf    0xd0, W, B                                  ; reg: 0x0d0
        xorlw   0x06
        bz      label_388
        bra     label_390                                   ; dest: 0x0031e6

label_384:                                                  ; address: 0x0031aa

        movlw   0x02
        movwf   0xc8, B                                     ; reg: 0x0c8
        movlw   0x10
        movwf   0x76, B                                     ; reg: 0x076
        movlw   0x3e
        movwf   0x75, B                                     ; reg: 0x075
        clrf    0xe8, B                                     ; reg: 0x0e8
        movlw   0x09
        bra     label_387                                   ; dest: 0x0031d4

label_385:                                                  ; address: 0x0031bc

        movlw   0x02
        movwf   0xc8, B                                     ; reg: 0x0c8
        decf    0xeb, W, B                                  ; reg: 0x0eb
        bnz     label_386
        movlw   0x10
        movwf   0x76, B                                     ; reg: 0x076
        movlw   0x55
        movwf   0x75, B                                     ; reg: 0x075

label_386:                                                  ; address: 0x0031cc

        decf    0xeb, W, B                                  ; reg: 0x0eb
        bnz     label_389
        clrf    0xe8, B                                     ; reg: 0x0e8
        movlw   0x1d

label_387:                                                  ; address: 0x0031d4

        movwf   0xe7, B                                     ; reg: 0x0e7
        bra     label_389                                   ; dest: 0x0031e4

label_388:                                                  ; address: 0x0031d8

        movf    0xd2, W, B                                  ; reg: 0x0d2
        xorlw   0x21
        bz      label_384
        xorlw   0x03
        bz      label_385
        xorlw   0x01

label_389:                                                  ; address: 0x0031e4

        bsf     0xce, 0x1, B                                ; reg: 0x0ce

label_390:                                                  ; address: 0x0031e6

        swapf   0xcf, W, B                                  ; reg: 0x0cf
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        andlw   0x03
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        decf    (Common_RAM + 3), W, A                      ; reg: 0x003
        bnz     label_399
        bra     label_398                                   ; dest: 0x003230

label_391:                                                  ; address: 0x0031f4

        call    function_131, 0x0                           ; dest: 0x00496e
        bra     label_399                                   ; dest: 0x00324a

label_392:                                                  ; address: 0x0031fa

        call    function_130, 0x0                           ; dest: 0x00496c
        bra     label_399                                   ; dest: 0x00324a

label_393:                                                  ; address: 0x003200

        movlw   0x02
        movwf   0xc8, B                                     ; reg: 0x0c8
        clrf    0x76, B                                     ; reg: 0x076
        movlw   0xea

label_394:                                                  ; address: 0x003208

        movwf   0x75, B                                     ; reg: 0x075
        bcf     0xce, 0x1, B                                ; reg: 0x0ce
        movlw   0x01
        movwf   0xe7, B                                     ; reg: 0x0e7
        bra     label_399                                   ; dest: 0x00324a

label_395:                                                  ; address: 0x003212

        movlw   0x02
        movwf   0xc8, B                                     ; reg: 0x0c8
        movff   0x0d2, 0x0ea
        bra     label_399                                   ; dest: 0x00324a

label_396:                                                  ; address: 0x00321c

        movlw   0x02
        movwf   0xc8, B                                     ; reg: 0x0c8
        clrf    0x76, B                                     ; reg: 0x076
        movlw   0xe9
        bra     label_394                                   ; dest: 0x003208

label_397:                                                  ; address: 0x003226

        movlw   0x02
        movwf   0xc8, B                                     ; reg: 0x0c8
        movff   0x0d1, 0x0e9
        bra     label_399                                   ; dest: 0x00324a

label_398:                                                  ; address: 0x003230

        movf    0xd0, W, B                                  ; reg: 0x0d0
        xorlw   0x01
        bz      label_391
        xorlw   0x03
        bz      label_393
        xorlw   0x01
        bz      label_396
        xorlw   0x0a
        bz      label_392
        xorlw   0x03
        bz      label_395
        xorlw   0x01
        bz      label_397

label_399:                                                  ; address: 0x00324a

        return  0x0

label_400:                                                  ; address: 0x00324c

        tstfsz  0xc8, B                                     ; reg: 0x0c8
        bra     label_402                                   ; dest: 0x003278
        movlw   0x04
        movlb   0x4
        movwf   0x08, B                                     ; reg: 0x408
        bsf     0x08, 0x7, B                                ; reg: 0x408
        movlb   0x1
        movwf   0x16, B                                     ; reg: 0x116
        movlb   0x0
        decf    0x96, W, B                                  ; reg: 0x096
        bnz     label_401
        movlw   0x01
        call    function_062, 0x0                           ; dest: 0x004080
        clrf    0x96, B                                     ; reg: 0x096
        bra     label_409                                   ; dest: 0x0032f6

label_401:                                                  ; address: 0x00326c

        movlw   0x00
        call    function_062, 0x0                           ; dest: 0x004080
        movlw   0x01
        movwf   0x96, B                                     ; reg: 0x096
        bra     label_409                                   ; dest: 0x0032f6

label_402:                                                  ; address: 0x003278

        btfss   0xcf, 0x7, B                                ; reg: 0x0cf
        bra     label_404                                   ; dest: 0x0032b4
        movlw   0x01
        movwf   0xc9, B                                     ; reg: 0x0c9
        movf    0xe7, W, B                                  ; reg: 0x0e7
        subwf   0xd5, W, B                                  ; reg: 0x0d5
        movf    0xe8, W, B                                  ; reg: 0x0e8
        subwfb  0xd6, W, B                                  ; reg: 0x0d6
        bc      label_403
        movff   0x0d5, 0x0e7
        movff   0x0d6, 0x0e8

label_403:                                                  ; address: 0x003292

        call    function_036, 0x0                           ; dest: 0x0035f0
        movlw   0x48
        movlb   0x1
        movwf   0x16, B                                     ; reg: 0x116
        movlw   0x01
        call    function_062, 0x0                           ; dest: 0x004080
        movlw   0x00
        call    function_062, 0x0                           ; dest: 0x004080
        movlb   0x4
        movlw   0x04
        movwf   0x0b, B                                     ; reg: 0x40b
        movlw   0x24
        movwf   0x0a, B                                     ; reg: 0x40a
        bra     label_408                                   ; dest: 0x0032f0

label_404:                                                  ; address: 0x0032b4

        movlw   0x02
        movwf   0xc9, B                                     ; reg: 0x0c9
        movlw   0x04
        movlb   0x1
        movwf   0x16, B                                     ; reg: 0x116
        movlb   0x0
        movf    0xd6, W, B                                  ; reg: 0x0d6
        iorwf   0xd5, W, B                                  ; reg: 0x0d5
        bnz     label_405
        movlw   0x48
        movlb   0x1
        movwf   0x16, B                                     ; reg: 0x116

label_405:                                                  ; address: 0x0032cc

        movlb   0x0
        decf    0x96, W, B                                  ; reg: 0x096
        bnz     label_406
        movlw   0x01
        call    function_062, 0x0                           ; dest: 0x004080
        clrf    0x96, B                                     ; reg: 0x096
        bra     label_407                                   ; dest: 0x0032e6

label_406:                                                  ; address: 0x0032dc

        movlw   0x00
        call    function_062, 0x0                           ; dest: 0x004080
        movlw   0x01
        movwf   0x96, B                                     ; reg: 0x096

label_407:                                                  ; address: 0x0032e6

        movf    0xd6, W, B                                  ; reg: 0x0d6
        iorwf   0xd5, W, B                                  ; reg: 0x0d5
        bnz     label_409
        movlb   0x4
        clrf    0x09, B                                     ; reg: 0x409

label_408:                                                  ; address: 0x0032f0

        movlw   0x48
        movwf   (Common_RAM + 8), B                         ; reg: 0x008
        bsf     (Common_RAM + 8), 0x7, B                    ; reg: 0x008

label_409:                                                  ; address: 0x0032f6

        return  0x0

function_031:                                               ; address: 0x0032f8

        call    function_113, 0x0                           ; dest: 0x0048b6
        movlw   0x3f
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x01
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x30
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x03
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x04
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x08
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x05
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x06
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x34
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x07
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x30
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x08
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x08
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x08
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0e
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x22
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x0f
        call    function_093, 0x0                           ; dest: 0x0046ba
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x10
        call    function_093, 0x0                           ; dest: 0x0046ba
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x11
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x1c
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x1d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x02
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x2d
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x20
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x2e
        goto    function_093                                ; dest: 0x0046ba

function_032:                                               ; address: 0x003398

        movff   (Common_RAM + 47), (Common_RAM + 3)         ; reg1: 0x02f, reg2: 0x003
        movff   (Common_RAM + 48), (Common_RAM + 4)         ; reg1: 0x030, reg2: 0x004
        movff   (Common_RAM + 49), (Common_RAM + 5)         ; reg1: 0x031, reg2: 0x005
        movff   (Common_RAM + 50), (Common_RAM + 6)         ; reg1: 0x032, reg2: 0x006
        movlw   0x37
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        call    function_053, 0x0                           ; dest: 0x003ce8
        movf    (Common_RAM + 56), W, A                     ; reg: 0x038
        xorlw   0x80
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x80
        subwf   PRODL, W, A                                 ; reg: 0xff3
        movlw   0x00
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        subwf   (Common_RAM + 55), W, A                     ; reg: 0x037
        bc      label_410
        clrf    (Common_RAM + 47), A                        ; reg: 0x02f
        clrf    (Common_RAM + 48), A                        ; reg: 0x030
        clrf    (Common_RAM + 49), A                        ; reg: 0x031
        clrf    (Common_RAM + 50), A                        ; reg: 0x032
        bra     label_412                                   ; dest: 0x003430

label_410:                                                  ; address: 0x0033cc

        movlw   0x1d
        subwf   (Common_RAM + 55), W, A                     ; reg: 0x037
        movlw   0x00
        subwfb  (Common_RAM + 56), W, A                     ; reg: 0x038
        bnc     label_411
        movff   (Common_RAM + 47), (Common_RAM + 47)        ; reg1: 0x02f, reg2: 0x02f
        movff   (Common_RAM + 48), (Common_RAM + 48)        ; reg1: 0x030, reg2: 0x030
        movff   (Common_RAM + 49), (Common_RAM + 49)        ; reg1: 0x031, reg2: 0x031
        movff   (Common_RAM + 50), (Common_RAM + 50)        ; reg1: 0x032, reg2: 0x032
        bra     label_412                                   ; dest: 0x003430

label_411:                                                  ; address: 0x0033e8

        movff   (Common_RAM + 47), (Common_RAM + 37)        ; reg1: 0x02f, reg2: 0x025
        movff   (Common_RAM + 48), (Common_RAM + 38)        ; reg1: 0x030, reg2: 0x026
        movff   (Common_RAM + 49), (Common_RAM + 39)        ; reg1: 0x031, reg2: 0x027
        movff   (Common_RAM + 50), (Common_RAM + 40)        ; reg1: 0x032, reg2: 0x028
        call    function_027, 0x0                           ; dest: 0x00301a
        movff   (Common_RAM + 37), (Common_RAM + 13)        ; reg1: 0x025, reg2: 0x00d
        movff   (Common_RAM + 38), (Common_RAM + 14)        ; reg1: 0x026, reg2: 0x00e
        movff   (Common_RAM + 39), (Common_RAM + 15)        ; reg1: 0x027, reg2: 0x00f
        movff   (Common_RAM + 40), (Common_RAM + 16)        ; reg1: 0x028, reg2: 0x010
        call    function_055, 0x0                           ; dest: 0x003e0a
        movff   (Common_RAM + 13), (Common_RAM + 51)        ; reg1: 0x00d, reg2: 0x033
        movff   (Common_RAM + 14), (Common_RAM + 52)        ; reg1: 0x00e, reg2: 0x034
        movff   (Common_RAM + 15), (Common_RAM + 53)        ; reg1: 0x00f, reg2: 0x035
        movff   (Common_RAM + 16), (Common_RAM + 54)        ; reg1: 0x010, reg2: 0x036
        movff   (Common_RAM + 51), (Common_RAM + 47)        ; reg1: 0x033, reg2: 0x02f
        movff   (Common_RAM + 52), (Common_RAM + 48)        ; reg1: 0x034, reg2: 0x030
        movff   (Common_RAM + 53), (Common_RAM + 49)        ; reg1: 0x035, reg2: 0x031
        movff   (Common_RAM + 54), (Common_RAM + 50)        ; reg1: 0x036, reg2: 0x032

label_412:                                                  ; address: 0x003430

        return  0x0

function_033:                                               ; address: 0x003432

        decf    0xd1, W, B                                  ; reg: 0x0d1
        bnz     label_414
        movf    0xcf, W, B                                  ; reg: 0x0cf
        andlw   0x1f
        bnz     label_414
        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movf    0xd0, W, B                                  ; reg: 0x0d0
        xorlw   0x03
        bnz     label_413
        bsf     0xce, 0x0, B                                ; reg: 0x0ce
        bra     label_414                                   ; dest: 0x00344c

label_413:                                                  ; address: 0x00344a

        bcf     0xce, 0x0, B                                ; reg: 0x0ce

label_414:                                                  ; address: 0x00344c

        tstfsz  0xd1, B                                     ; reg: 0x0d1
        bra     label_418                                   ; dest: 0x0034c6
        movf    0xcf, W, B                                  ; reg: 0x0cf
        andlw   0x1f
        xorlw   0x02
        bnz     label_418
        movf    0xd3, W, B                                  ; reg: 0x0d3
        andlw   0x0f
        bz      label_418
        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movf    0xd3, W, B                                  ; reg: 0x0d3
        andlw   0x0f
        mullw   0x08
        movlw   0x04
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        movf    PRODL, W, A                                 ; reg: 0xff3
        addwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    PRODH, W, A                                 ; reg: 0xff4
        addwfc  (Common_RAM + 4), F, A                      ; reg: 0x004
        movlw   0x01
        btfss   0xd3, 0x7, B                                ; reg: 0x0d3
        movlw   0x00
        mullw   0x04
        movf    PRODL, W, A                                 ; reg: 0xff3
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   0x72, B                                     ; reg: 0x072
        movf    PRODH, W, A                                 ; reg: 0xff4
        addwfc  (Common_RAM + 4), W, A                      ; reg: 0x004
        movwf   0x73, B                                     ; reg: 0x073
        movf    0xd0, W, B                                  ; reg: 0x0d0
        xorlw   0x03
        bnz     label_415
        movff   0x072, FSR2L                                ; reg2: 0xfd9
        movff   0x073, FSR2H                                ; reg2: 0xfda
        movlw   0x04
        bra     label_417                                   ; dest: 0x0034b8

label_415:                                                  ; address: 0x00349c

        btfss   0xd3, 0x7, B                                ; reg: 0x0d3
        bra     label_416                                   ; dest: 0x0034ae
        movff   0x072, FSR2L                                ; reg2: 0xfd9
        movff   0x073, FSR2H                                ; reg2: 0xfda
        movlw   0x40
        movwf   INDF2, A                                    ; reg: 0xfdf
        bra     label_418                                   ; dest: 0x0034c6

label_416:                                                  ; address: 0x0034ae

        movff   0x072, FSR2L                                ; reg2: 0xfd9
        movff   0x073, FSR2H                                ; reg2: 0xfda
        movlw   0x08

label_417:                                                  ; address: 0x0034b8

        movwf   INDF2, A                                    ; reg: 0xfdf
        movff   0x072, FSR2L                                ; reg2: 0xfd9
        movff   0x073, FSR2H                                ; reg2: 0xfda
        movlw   0x00
        bsf     PLUSW2, 0x7, A                              ; reg: 0xfdb

label_418:                                                  ; address: 0x0034c6

        return  0x0

function_034:                                               ; address: 0x0034c8

        movff   WREG, (Common_RAM + 17)                     ; reg1: 0xfe8, reg2: 0x011
        movff   (Common_RAM + 10), (Common_RAM + 14)        ; reg1: 0x00a, reg2: 0x00e
        movff   (Common_RAM + 11), (Common_RAM + 15)        ; reg1: 0x00b, reg2: 0x00f

label_419:                                                  ; address: 0x0034d4

        movff   (Common_RAM + 14), (Common_RAM + 3)         ; reg1: 0x00e, reg2: 0x003
        movff   (Common_RAM + 15), (Common_RAM + 4)         ; reg1: 0x00f, reg2: 0x004
        movff   (Common_RAM + 12), (Common_RAM + 5)         ; reg1: 0x00c, reg2: 0x005
        movff   (Common_RAM + 13), (Common_RAM + 6)         ; reg1: 0x00d, reg2: 0x006
        call    function_064, 0x0                           ; dest: 0x004124
        movff   (Common_RAM + 3), (Common_RAM + 14)         ; reg1: 0x003, reg2: 0x00e
        movff   (Common_RAM + 4), (Common_RAM + 15)         ; reg1: 0x004, reg2: 0x00f
        incf    (Common_RAM + 17), F, A                     ; reg: 0x011
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        iorwf   (Common_RAM + 14), W, A                     ; reg: 0x00e
        bnz     label_419
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        clrf    INDF2, A                                    ; reg: 0xfdf
        decf    (Common_RAM + 17), F, A                     ; reg: 0x011

label_420:                                                  ; address: 0x003504

        movff   (Common_RAM + 10), (Common_RAM + 3)         ; reg1: 0x00a, reg2: 0x003
        movff   (Common_RAM + 11), (Common_RAM + 4)         ; reg1: 0x00b, reg2: 0x004
        movff   (Common_RAM + 12), (Common_RAM + 5)         ; reg1: 0x00c, reg2: 0x005
        movff   (Common_RAM + 13), (Common_RAM + 6)         ; reg1: 0x00d, reg2: 0x006
        call    function_068, 0x0                           ; dest: 0x00427a
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   (Common_RAM + 16), A                        ; reg: 0x010
        movff   (Common_RAM + 10), (Common_RAM + 3)         ; reg1: 0x00a, reg2: 0x003
        movff   (Common_RAM + 11), (Common_RAM + 4)         ; reg1: 0x00b, reg2: 0x004
        movff   (Common_RAM + 12), (Common_RAM + 5)         ; reg1: 0x00c, reg2: 0x005
        movff   (Common_RAM + 13), (Common_RAM + 6)         ; reg1: 0x00d, reg2: 0x006
        call    function_064, 0x0                           ; dest: 0x004124
        movff   (Common_RAM + 3), (Common_RAM + 10)         ; reg1: 0x003, reg2: 0x00a
        movff   (Common_RAM + 4), (Common_RAM + 11)         ; reg1: 0x004, reg2: 0x00b
        movlw   0x09
        cpfsgt  (Common_RAM + 16), A                        ; reg: 0x010
        bra     label_421                                   ; dest: 0x003542
        movlw   0x07
        addwf   (Common_RAM + 16), F, A                     ; reg: 0x010

label_421:                                                  ; address: 0x003542

        movlw   0x30
        addwf   (Common_RAM + 16), F, A                     ; reg: 0x010
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   (Common_RAM + 16), INDF2                    ; reg1: 0x010, reg2: 0xfdf
        decf    (Common_RAM + 17), F, A                     ; reg: 0x011
        movf    (Common_RAM + 11), W, A                     ; reg: 0x00b
        iorwf   (Common_RAM + 10), W, A                     ; reg: 0x00a
        bnz     label_420
        incf    (Common_RAM + 17), F, A                     ; reg: 0x011
        return  0x0

function_035:                                               ; address: 0x00355c

        clrf    INTCON, A                                   ; reg: 0xff2
        clrf    PIE1, A                                     ; reg: 0xf9d
        clrf    PIE2, A                                     ; reg: 0xfa0
        clrf    PIR1, A                                     ; reg: 0xf9e
        clrf    PIR2, A                                     ; reg: 0xfa1
        clrf    PORTA, A                                    ; reg: 0xf80
        clrf    PORTB, A                                    ; reg: 0xf81
        clrf    PORTC, A                                    ; reg: 0xf82
        movlw   0x07
        movwf   TRISA, A                                    ; reg: 0xf92
        clrf    TRISB, A                                    ; reg: 0xf93
        movlw   0x87
        movwf   TRISC, A                                    ; reg: 0xf94
        movlw   0x70
        movwf   OSCCON, A                                   ; reg: 0xfd3
        movlw   0x38
        movwf   SSPCON1, A                                  ; reg: 0xfc6
        movlw   0x01
        movwf   ADCON0, A                                   ; reg: 0xfc2
        movlw   0x0c
        movwf   ADCON1, A                                   ; reg: 0xfc1
        movlw   0xb5
        movwf   ADCON2, A                                   ; reg: 0xfc0
        movlw   0x07
        movwf   T0CON, A                                    ; reg: 0xfd5
        movlw   0x80
        movwf   T1CON, A                                    ; reg: 0xfcd
        movlw   0x77
        movwf   SSPADD, A                                   ; reg: 0xfc8
        movlw   0x01
        movlb   0x0
        movwf   0xfe, B                                     ; reg: 0x0fe
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0xff
        setf    (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        xorlw   0x77
        bz      label_422
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0xff
        setf    (Common_RAM + 3), A                         ; reg: 0x003
        call    function_110, 0x0                           ; dest: 0x004884
        xorlw   0x88
        bz      label_422
        movlb   0x0
        clrf    0xfe, B                                     ; reg: 0x0fe

label_422:                                                  ; address: 0x0035bc

        movlb   0x0
        movf    0xfe, W, B                                  ; reg: 0x0fe
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_069, 0x0                           ; dest: 0x0042b8
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        setf    (Common_RAM + 7), A                         ; reg: 0x007
        movlw   0x02
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        call    function_094, 0x0                           ; dest: 0x0046de
        bsf     PORTB, RB6, A                               ; reg: 0xf81, bit: 6
        call    function_045, 0x0                           ; dest: 0x003926
        movlw   0x03
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0xe8
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        call    function_007, 0x0                           ; dest: 0x001e88
        bsf     PIE1, RCIE, A                               ; reg: 0xf9d, bit: 5
        bsf     (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        goto    function_024                                ; dest: 0x002d8c

function_036:                                               ; address: 0x0035f0

        movlw   0x08
        movwf   0x8f, B                                     ; reg: 0x08f
        subwf   0xe7, W, B                                  ; reg: 0x0e7
        movlw   0x00
        subwfb  0xe8, W, B                                  ; reg: 0x0e8
        bc      label_425
        movff   0x0e7, 0x08f
        tstfsz  0xcc, B                                     ; reg: 0x0cc
        bra     label_423                                   ; dest: 0x003608
        movlw   0x01
        bra     label_424                                   ; dest: 0x00360e

label_423:                                                  ; address: 0x003608

        decf    0xcc, W, B                                  ; reg: 0x0cc
        bnz     label_425
        movlw   0x02

label_424:                                                  ; address: 0x00360e

        movwf   0xcc, B                                     ; reg: 0x0cc

label_425:                                                  ; address: 0x003610

        movff   0x08f, 0x409
        movf    0x8f, W, B                                  ; reg: 0x08f
        subwf   0xe7, F, B                                  ; reg: 0x0e7
        movlw   0x00
        subwfb  0xe8, F, B                                  ; reg: 0x0e8
        movlw   0x04
        movlb   0x0
        movwf   0x73, B                                     ; reg: 0x073
        movlw   0x24
        movwf   0x72, B                                     ; reg: 0x072
        btfsc   0xce, 0x1, B                                ; reg: 0x0ce
        bra     label_429                                   ; dest: 0x00363e
        bra     label_433                                   ; dest: 0x003656

label_426:                                                  ; address: 0x00362c

        rcall   function_037                                ; dest: 0x00365c
        cpfsgt  TBLPTRH, A                                  ; reg: 0xff7
        bra     label_427                                   ; dest: 0x003638
        tblrd*
        movf    TABLAT, W, A                                ; reg: 0xff5
        bra     label_428                                   ; dest: 0x00363c

label_427:                                                  ; address: 0x003638

        call    function_042, 0x0                           ; dest: 0x003810

label_428:                                                  ; address: 0x00363c

        rcall   function_038                                ; dest: 0x003672

label_429:                                                  ; address: 0x00363e

        tstfsz  0x8f, B                                     ; reg: 0x08f
        bra     label_426                                   ; dest: 0x00362c
        bra     label_434                                   ; dest: 0x00365a

label_430:                                                  ; address: 0x003644

        rcall   function_037                                ; dest: 0x00365c
        cpfsgt  TBLPTRH, A                                  ; reg: 0xff7
        bra     label_431                                   ; dest: 0x003650
        tblrd*
        movf    TABLAT, W, A                                ; reg: 0xff5
        bra     label_432                                   ; dest: 0x003654

label_431:                                                  ; address: 0x003650

        call    function_042, 0x0                           ; dest: 0x003810

label_432:                                                  ; address: 0x003654

        rcall   function_038                                ; dest: 0x003672

label_433:                                                  ; address: 0x003656

        tstfsz  0x8f, B                                     ; reg: 0x08f
        bra     label_430                                   ; dest: 0x003644

label_434:                                                  ; address: 0x00365a

        return  0x0

function_037:                                               ; address: 0x00365c

        movff   0x075, TBLPTRL                              ; reg2: 0xff6
        movff   0x076, TBLPTRH                              ; reg2: 0xff7
        clrf    TBLPTRU, A                                  ; reg: 0xff8
        movff   0x072, FSR2L                                ; reg2: 0xfd9
        movff   0x073, FSR2H                                ; reg2: 0xfda
        movlw   0x07
        return  0x0

function_038:                                               ; address: 0x003672

        movwf   INDF2, A                                    ; reg: 0xfdf
        movlb   0x0
        infsnz  0x72, F, B                                  ; reg: 0x072
        incf    0x73, F, B                                  ; reg: 0x073
        infsnz  0x75, F, B                                  ; reg: 0x075
        incf    0x76, F, B                                  ; reg: 0x076
        decf    0x8f, F, B                                  ; reg: 0x08f
        return  0x0

function_039:                                               ; address: 0x003682

        swapf   0xcf, W, B                                  ; reg: 0x0cf
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        andlw   0x03
        bnz     label_445
        bra     label_444                                   ; dest: 0x0036e4

label_435:                                                  ; address: 0x00368c

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movlw   0x04
        movwf   0xcd, B                                     ; reg: 0x0cd
        bra     label_445                                   ; dest: 0x00370e

label_436:                                                  ; address: 0x003696

        call    function_041, 0x0                           ; dest: 0x003796
        bra     label_445                                   ; dest: 0x00370e

label_437:                                                  ; address: 0x00369c

        call    function_066, 0x0                           ; dest: 0x0041fe
        bra     label_445                                   ; dest: 0x00370e

label_438:                                                  ; address: 0x0036a2

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        clrf    0x76, B                                     ; reg: 0x076
        movlw   0xeb
        movwf   0x75, B                                     ; reg: 0x075

label_439:                                                  ; address: 0x0036ac

        bcf     0xce, 0x1, B                                ; reg: 0x0ce
        movlw   0x01
        movwf   0xe7, B                                     ; reg: 0x0e7
        bra     label_445                                   ; dest: 0x00370e

label_440:                                                  ; address: 0x0036b4

        call    function_040, 0x0                           ; dest: 0x003710
        bra     label_445                                   ; dest: 0x00370e

label_441:                                                  ; address: 0x0036ba

        call    function_033, 0x0                           ; dest: 0x003432
        bra     label_445                                   ; dest: 0x00370e

label_442:                                                  ; address: 0x0036c0

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movf    0xd3, W, B                                  ; reg: 0x0d3
        addlw   0xec
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        clrf    0x76, B                                     ; reg: 0x076
        movff   (Common_RAM + 5), 0x075                     ; reg1: 0x005
        bra     label_439                                   ; dest: 0x0036ac

label_443:                                                  ; address: 0x0036d2

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movf    0xd3, W, B                                  ; reg: 0x0d3
        addlw   0xec
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   0x0d1, INDF2                                ; reg2: 0xfdf
        bra     label_445                                   ; dest: 0x00370e

label_444:                                                  ; address: 0x0036e4

        movf    0xd0, W, B                                  ; reg: 0x0d0
        bz      label_440
        xorlw   0x01
        bz      label_441
        xorlw   0x02
        bz      label_441
        xorlw   0x06
        bz      label_435
        xorlw   0x03
        bz      label_436
        xorlw   0x01
        bz      label_445
        xorlw   0x0f
        bz      label_438
        xorlw   0x01
        bz      label_437
        xorlw   0x03
        bz      label_442
        xorlw   0x01
        bz      label_443
        xorlw   0x07

label_445:                                                  ; address: 0x00370e

        return  0x0

function_040:                                               ; address: 0x003710

        movlb   0x4
        clrf    0x24, B                                     ; reg: 0x424
        clrf    0x25, B                                     ; reg: 0x425
        bra     label_449                                   ; dest: 0x003770

label_446:                                                  ; address: 0x003718

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        btfss   0xce, 0x0, B                                ; reg: 0x0ce
        bra     label_450                                   ; dest: 0x003780
        movlb   0x4
        bsf     0x24, 0x1, B                                ; reg: 0x424
        bra     label_450                                   ; dest: 0x003780

label_447:                                                  ; address: 0x003726

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        bra     label_450                                   ; dest: 0x003780

label_448:                                                  ; address: 0x00372c

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movf    0xd3, W, B                                  ; reg: 0x0d3
        andlw   0x0f
        mullw   0x08
        movlw   0x04
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        movf    PRODL, W, A                                 ; reg: 0xff3
        addwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    PRODH, W, A                                 ; reg: 0xff4
        addwfc  (Common_RAM + 4), F, A                      ; reg: 0x004
        movlw   0x01
        btfss   0xd3, 0x7, B                                ; reg: 0x0d3
        movlw   0x00
        mullw   0x04
        movf    PRODL, W, A                                 ; reg: 0xff3
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   0x72, B                                     ; reg: 0x072
        movf    PRODH, W, A                                 ; reg: 0xff4
        addwfc  (Common_RAM + 4), W, A                      ; reg: 0x004
        movwf   0x73, B                                     ; reg: 0x073
        movff   0x072, FSR2L                                ; reg2: 0xfd9
        movff   0x073, FSR2H                                ; reg2: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        btfss   (Common_RAM + 3), 0x2, A                    ; reg: 0x003
        bra     label_450                                   ; dest: 0x003780
        movlw   0x01
        movlb   0x4
        movwf   0x24, B                                     ; reg: 0x424
        bra     label_450                                   ; dest: 0x003780

label_449:                                                  ; address: 0x003770

        movlb   0x0
        movf    0xcf, W, B                                  ; reg: 0x0cf
        andlw   0x1f
        bz      label_446
        xorlw   0x01
        bz      label_447
        xorlw   0x03
        bz      label_448

label_450:                                                  ; address: 0x003780

        movlb   0x0
        decf    0xc8, W, B                                  ; reg: 0x0c8
        bnz     label_451
        movlw   0x04
        movwf   0x76, B                                     ; reg: 0x076
        movlw   0x24
        movwf   0x75, B                                     ; reg: 0x075
        bcf     0xce, 0x1, B                                ; reg: 0x0ce
        movlw   0x02
        movwf   0xe7, B                                     ; reg: 0x0e7

label_451:                                                  ; address: 0x003794

        return  0x0

function_041:                                               ; address: 0x003796

        movf    0xcf, W, B                                  ; reg: 0x0cf
        xorlw   0x80
        bz      label_458
        bra     label_460                                   ; dest: 0x00380e

label_452:                                                  ; address: 0x00379e

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movlw   0x10
        movwf   0x76, B                                     ; reg: 0x076
        movlw   0x88
        movwf   0x75, B                                     ; reg: 0x075
        movlw   0x12
        bra     label_454                                   ; dest: 0x0037c4

label_453:                                                  ; address: 0x0037ae

        tstfsz  0xd1, B                                     ; reg: 0x0d1
        bra     label_459                                   ; dest: 0x00380c
        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movlw   0x10
        movwf   0x76, B                                     ; reg: 0x076
        movlw   0x2c
        movwf   0x75, B                                     ; reg: 0x075
        movlw   0x00
        movwf   0xe8, B                                     ; reg: 0x0e8
        movlw   0x29

label_454:                                                  ; address: 0x0037c4

        movwf   0xe7, B                                     ; reg: 0x0e7
        bra     label_459                                   ; dest: 0x00380c

label_455:                                                  ; address: 0x0037c8

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        movf    0xd1, W, B                                  ; reg: 0x0d1
        addlw   0x29
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x10
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        tblrd*+
        movff   TABLAT, 0x075                               ; reg1: 0xff5
        movwf   0x76, B                                     ; reg: 0x076
        movff   0x075, TBLPTRL                              ; reg2: 0xff6
        movff   0x076, TBLPTRH                              ; reg2: 0xff7
        clrf    TBLPTRU, A                                  ; reg: 0xff8
        movlw   0x07
        cpfsgt  TBLPTRH, A                                  ; reg: 0xff7
        bra     label_456                                   ; dest: 0x0037f4
        tblrd*
        movf    TABLAT, W, A                                ; reg: 0xff5
        bra     label_457                                   ; dest: 0x0037f6

label_456:                                                  ; address: 0x0037f4

        rcall   function_042                                ; dest: 0x003810

label_457:                                                  ; address: 0x0037f6

        movlb   0x0
        movwf   0xe7, B                                     ; reg: 0x0e7
        clrf    0xe8, B                                     ; reg: 0x0e8
        bra     label_459                                   ; dest: 0x00380c

label_458:                                                  ; address: 0x0037fe

        movf    0xd2, W, B                                  ; reg: 0x0d2
        xorlw   0x01
        bz      label_452
        xorlw   0x03
        bz      label_453
        xorlw   0x01
        bz      label_455

label_459:                                                  ; address: 0x00380c

        bsf     0xce, 0x1, B                                ; reg: 0x0ce

label_460:                                                  ; address: 0x00380e

        return  0x0

function_042:                                               ; address: 0x003810

        movff   TBLPTRL, FSR1L                              ; reg1: 0xff6, reg2: 0xfe1
        movff   TBLPTRH, FSR1H                              ; reg1: 0xff7, reg2: 0xfe2
        movf    INDF1, W, A                                 ; reg: 0xfe7
        return  0x0

function_043:                                               ; address: 0x00381c

        movff   (Common_RAM + 19), (Common_RAM + 3)         ; reg1: 0x013, reg2: 0x003
        movff   (Common_RAM + 20), (Common_RAM + 4)         ; reg1: 0x014, reg2: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x04
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        movlw   0x17
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        call    function_061, 0x0                           ; dest: 0x004028
        movff   (Common_RAM + 24), (Common_RAM + 47)        ; reg1: 0x018, reg2: 0x02f
        movff   (Common_RAM + 25), (Common_RAM + 49)        ; reg1: 0x019, reg2: 0x031
        movlw   0x19
        subwf   (Common_RAM + 49), W, A                     ; reg: 0x031
        bc      label_465
        movlw   0x04
        addwf   (Common_RAM + 19), W, A                     ; reg: 0x013
        movwf   (Common_RAM + 21), A                        ; reg: 0x015
        movlw   0x00
        addwfc  (Common_RAM + 20), W, A                     ; reg: 0x014
        movwf   (Common_RAM + 22), A                        ; reg: 0x016
        movff   (Common_RAM + 21), (Common_RAM + 3)         ; reg1: 0x015, reg2: 0x003
        movff   (Common_RAM + 22), (Common_RAM + 4)         ; reg1: 0x016, reg2: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movff   (Common_RAM + 49), (Common_RAM + 7)         ; reg1: 0x031, reg2: 0x007
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        movlw   0x17
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        call    function_061, 0x0                           ; dest: 0x004028
        bsf     SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0

label_461:                                                  ; address: 0x003870

        btfsc   SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0
        bra     label_461                                   ; dest: 0x003870
        movlw   0x68
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 47), W, A                     ; reg: 0x02f
        call    function_056, 0x0                           ; dest: 0x003e68
        clrf    (Common_RAM + 48), A                        ; reg: 0x030
        bra     label_463                                   ; dest: 0x003894

label_462:                                                  ; address: 0x003884

        movf    (Common_RAM + 48), W, A                     ; reg: 0x030
        addlw   0x17
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        call    function_056, 0x0                           ; dest: 0x003e68
        incf    (Common_RAM + 48), F, A                     ; reg: 0x030

label_463:                                                  ; address: 0x003894

        movf    (Common_RAM + 49), W, A                     ; reg: 0x031
        subwf   (Common_RAM + 48), W, A                     ; reg: 0x030
        bnc     label_462
        bsf     SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2

label_464:                                                  ; address: 0x00389c

        btfsc   SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2
        bra     label_464                                   ; dest: 0x00389c

label_465:                                                  ; address: 0x0038a0

        return  0x0

function_044:                                               ; address: 0x0038a2

        movff   (Common_RAM + 65), (Common_RAM + 57)        ; reg1: 0x041, reg2: 0x039
        movff   (Common_RAM + 66), (Common_RAM + 58)        ; reg1: 0x042, reg2: 0x03a
        movff   (Common_RAM + 67), (Common_RAM + 59)        ; reg1: 0x043, reg2: 0x03b
        movff   (Common_RAM + 68), (Common_RAM + 60)        ; reg1: 0x044, reg2: 0x03c
        movff   (Common_RAM + 65), (Common_RAM + 47)        ; reg1: 0x041, reg2: 0x02f
        movff   (Common_RAM + 66), (Common_RAM + 48)        ; reg1: 0x042, reg2: 0x030
        movff   (Common_RAM + 67), (Common_RAM + 49)        ; reg1: 0x043, reg2: 0x031
        movff   (Common_RAM + 68), (Common_RAM + 50)        ; reg1: 0x044, reg2: 0x032
        call    function_032, 0x0                           ; dest: 0x003398
        movff   (Common_RAM + 47), (Common_RAM + 61)        ; reg1: 0x02f, reg2: 0x03d
        movff   (Common_RAM + 48), (Common_RAM + 62)        ; reg1: 0x030, reg2: 0x03e
        movff   (Common_RAM + 49), (Common_RAM + 63)        ; reg1: 0x031, reg2: 0x03f
        movff   (Common_RAM + 50), (Common_RAM + 64)        ; reg1: 0x032, reg2: 0x040
        call    function_071, 0x0                           ; dest: 0x00432e
        movff   (Common_RAM + 57), (Common_RAM + 69)        ; reg1: 0x039, reg2: 0x045
        movff   (Common_RAM + 58), (Common_RAM + 70)        ; reg1: 0x03a, reg2: 0x046
        movff   (Common_RAM + 59), (Common_RAM + 71)        ; reg1: 0x03b, reg2: 0x047
        movff   (Common_RAM + 60), (Common_RAM + 72)        ; reg1: 0x03c, reg2: 0x048
        movff   (Common_RAM + 69), (Common_RAM + 47)        ; reg1: 0x045, reg2: 0x02f
        movff   (Common_RAM + 70), (Common_RAM + 48)        ; reg1: 0x046, reg2: 0x030
        movff   (Common_RAM + 71), (Common_RAM + 49)        ; reg1: 0x047, reg2: 0x031
        movff   (Common_RAM + 72), (Common_RAM + 50)        ; reg1: 0x048, reg2: 0x032
        movlw   0x41
        call    function_058, 0x0                           ; dest: 0x003f1e
        movff   (Common_RAM + 65), (Common_RAM + 47)        ; reg1: 0x041, reg2: 0x02f
        movff   (Common_RAM + 66), (Common_RAM + 48)        ; reg1: 0x042, reg2: 0x030
        movff   (Common_RAM + 67), (Common_RAM + 49)        ; reg1: 0x043, reg2: 0x031
        movff   (Common_RAM + 68), (Common_RAM + 50)        ; reg1: 0x044, reg2: 0x032
        call    function_032, 0x0                           ; dest: 0x003398
        movff   (Common_RAM + 47), (Common_RAM + 65)        ; reg1: 0x02f, reg2: 0x041
        movff   (Common_RAM + 48), (Common_RAM + 66)        ; reg1: 0x030, reg2: 0x042
        movff   (Common_RAM + 49), (Common_RAM + 67)        ; reg1: 0x031, reg2: 0x043
        movff   (Common_RAM + 50), (Common_RAM + 68)        ; reg1: 0x032, reg2: 0x044
        return  0x0

function_045:                                               ; address: 0x003926

        btfss   PORTC, RC2, A                               ; reg: 0xf82, bit: 2
        bra     label_466                                   ; dest: 0x003936
        bsf     LATB, LATB2, A                              ; reg: 0xf8a, bit: 2
        clrf    SPBRGH, A                                   ; reg: 0xfb0
        movlw   0x3f
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bsf     OSCCON, SCS1, A                             ; reg: 0xfd3, bit: 1
        bra     label_467                                   ; dest: 0x003940

label_466:                                                  ; address: 0x003936

        bcf     LATB, LATB2, A                              ; reg: 0xf8a, bit: 2
        clrf    SPBRGH, A                                   ; reg: 0xfb0
        movlw   0x7f
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bcf     OSCCON, SCS1, A                             ; reg: 0xfd3, bit: 1

label_467:                                                  ; address: 0x003940

        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        bcf     LATB, LATB5, A                              ; reg: 0xf8a, bit: 5
        bcf     LATB, LATB3, A                              ; reg: 0xf8a, bit: 3
        bcf     LATA, LATA6, A                              ; reg: 0xf89, bit: 6
        bcf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3
        bcf     LATA, LATA4, A                              ; reg: 0xf89, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        bcf     LATB, LATB7, A                              ; reg: 0xf8a, bit: 7
        call    function_121, 0x0                           ; dest: 0x004938
        bsf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        bsf     INTCON, PEIE, A                             ; reg: 0xff2, bit: 6
        clrf    0x93, B                                     ; reg: 0x093
        movff   0x093, 0x0ab
        bcf     INTCON3, INT2E, A                           ; reg: 0xff0, bit: 4
        bcf     INTCON3, INT2F, A                           ; reg: 0xff0, bit: 1
        bcf     INTCON, T0IF, A                             ; reg: 0xff2, bit: 2
        bcf     T0CON, TMR0ON, A                            ; reg: 0xfd5, bit: 7
        bcf     INTCON, T0IE, A                             ; reg: 0xff2, bit: 5
        clrf    0xa4, B                                     ; reg: 0x0a4
        clrf    0xb0, B                                     ; reg: 0x0b0
        clrf    0xb6, B                                     ; reg: 0x0b6
        clrf    0xba, B                                     ; reg: 0x0ba
        clrf    0x7e, B                                     ; reg: 0x07e
        clrf    0x7f, B                                     ; reg: 0x07f
        clrf    0xbd, B                                     ; reg: 0x0bd
        clrf    (Common_RAM + 94), A                        ; reg: 0x05e
        clrf    0xbb, B                                     ; reg: 0x0bb
        clrf    0xbc, B                                     ; reg: 0x0bc
        clrf    0xa1, B                                     ; reg: 0x0a1
        clrf    0x88, B                                     ; reg: 0x088
        clrf    0x89, B                                     ; reg: 0x089
        bcf     ADCON0, GO, A                               ; reg: 0xfc2, bit: 1
        clrf    0x94, B                                     ; reg: 0x094
        movlw   0x20
        movlb   0x1
        movwf   0x0f, B                                     ; reg: 0x10f
        movlw   0x21
        movwf   0x10, B                                     ; reg: 0x110
        movlw   0x22
        movwf   0x11, B                                     ; reg: 0x111
        movlw   0x23
        movwf   0x12, B                                     ; reg: 0x112
        movlw   0x25
        movwf   0x13, B                                     ; reg: 0x113
        movlw   0x27
        movwf   0x14, B                                     ; reg: 0x114
        movlw   0x28
        movwf   0x15, B                                     ; reg: 0x115
        retlw   0x28

function_046:                                               ; address: 0x0039a6

        clrf    (Common_RAM + 22), A                        ; reg: 0x016
        clrf    (Common_RAM + 23), A                        ; reg: 0x017
        clrf    (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x4b
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        movff   (Common_RAM + 73), (Common_RAM + 18)        ; reg1: 0x049, reg2: 0x012
        movff   (Common_RAM + 74), (Common_RAM + 19)        ; reg1: 0x04a, reg2: 0x013
        movff   (Common_RAM + 75), (Common_RAM + 20)        ; reg1: 0x04b, reg2: 0x014
        movff   (Common_RAM + 76), (Common_RAM + 21)        ; reg1: 0x04c, reg2: 0x015
        call    function_017, 0x0                           ; dest: 0x002abc
        movff   (Common_RAM + 18), (Common_RAM + 65)        ; reg1: 0x012, reg2: 0x041
        movff   (Common_RAM + 19), (Common_RAM + 66)        ; reg1: 0x013, reg2: 0x042
        movff   (Common_RAM + 20), (Common_RAM + 67)        ; reg1: 0x014, reg2: 0x043
        movff   (Common_RAM + 21), (Common_RAM + 68)        ; reg1: 0x015, reg2: 0x044
        call    function_044, 0x0                           ; dest: 0x0038a2
        movff   (Common_RAM + 65), (Common_RAM + 77)        ; reg1: 0x041, reg2: 0x04d
        movff   (Common_RAM + 66), (Common_RAM + 78)        ; reg1: 0x042, reg2: 0x04e
        movff   (Common_RAM + 67), (Common_RAM + 79)        ; reg1: 0x043, reg2: 0x04f
        movff   (Common_RAM + 68), (Common_RAM + 80)        ; reg1: 0x044, reg2: 0x050
        movff   (Common_RAM + 77), (Common_RAM + 37)        ; reg1: 0x04d, reg2: 0x025
        movff   (Common_RAM + 78), (Common_RAM + 38)        ; reg1: 0x04e, reg2: 0x026
        movff   (Common_RAM + 79), (Common_RAM + 39)        ; reg1: 0x04f, reg2: 0x027
        movff   (Common_RAM + 80), (Common_RAM + 40)        ; reg1: 0x050, reg2: 0x028
        call    function_027, 0x0                           ; dest: 0x00301a
        movff   (Common_RAM + 37), (Common_RAM + 81)        ; reg1: 0x025, reg2: 0x051
        movff   (Common_RAM + 38), (Common_RAM + 82)        ; reg1: 0x026, reg2: 0x052
        movff   (Common_RAM + 39), (Common_RAM + 83)        ; reg1: 0x027, reg2: 0x053
        movff   (Common_RAM + 40), (Common_RAM + 84)        ; reg1: 0x028, reg2: 0x054
        movf    (Common_RAM + 84), W, A                     ; reg: 0x054
        andlw   0x0f
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 83), W, A                     ; reg: 0x053
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 82), W, A                     ; reg: 0x052
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 81), W, A                     ; reg: 0x051
        goto    function_056                                ; dest: 0x003e68

function_047:                                               ; address: 0x003a26

        movlb   0x0
        movf    0xcd, W, B                                  ; reg: 0x0cd
        xorlw   0x06
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        btfsc   UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        bra     label_468                                   ; dest: 0x003a3a
        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_468                                   ; dest: 0x003a3a
        btfsc   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        bra     label_469                                   ; dest: 0x003a40

label_468:                                                  ; address: 0x003a3a

        call    function_126, 0x0                           ; dest: 0x00495e
        bra     label_472                                   ; dest: 0x003aa2

label_469:                                                  ; address: 0x003a40

        tstfsz  0xc0, B                                     ; reg: 0x0c0
        bra     label_471                                   ; dest: 0x003a7e
        movlb   0x4
        btfsc   0x0c, 0x7, B                                ; reg: 0x40c
        bra     label_472                                   ; dest: 0x003aa2
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0x1a
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x40
        movwf   0x05, A                                     ; reg: 0x105
        call    function_052, 0x0                           ; dest: 0x003c82
        movlw   0x01
        movlb   0x0
        movwf   0xc0, B                                     ; reg: 0x0c0
        clrf    (Common_RAM + 89), A                        ; reg: 0x059

label_470:                                                  ; address: 0x003a64

        movlb   0x1
        movlw   0x5a
        addwf   0x59, W, A                                  ; reg: 0x159
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        clrf    INDF2, A                                    ; reg: 0xfdf
        incf    0x59, F, A                                  ; reg: 0x159
        movlw   0x3f
        cpfsgt  0x59, A                                     ; reg: 0x159
        bra     label_470                                   ; dest: 0x003a64
        bra     label_472                                   ; dest: 0x003aa2

label_471:                                                  ; address: 0x003a7e

        movlb   0x1
        movf    0x1a, W, B                                  ; reg: 0x11a
        call    function_000, 0x0                           ; dest: 0x0010ac
        movlb   0x4
        btfsc   0x10, 0x7, B                                ; reg: 0x410
        bra     label_472                                   ; dest: 0x003aa2
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0x5a
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x40
        movwf   0x05, A                                     ; reg: 0x105
        call    function_060, 0x0                           ; dest: 0x003fd0
        movlb   0x0
        clrf    0xc0, B                                     ; reg: 0x0c0

label_472:                                                  ; address: 0x003aa2

        return  0x0

function_048:                                               ; address: 0x003aa4

        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        clrf    (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 15), A                        ; reg: 0x00f
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        movff   (Common_RAM + 5), (Common_RAM + 3)          ; reg1: 0x005, reg2: 0x003
        movff   (Common_RAM + 6), (Common_RAM + 4)          ; reg1: 0x006, reg2: 0x004
        call    function_099, 0x0                           ; dest: 0x00477a

label_473:                                                  ; address: 0x003ab8

        call    function_109, 0x0                           ; dest: 0x004872
        iorlw   0x00
        bz      label_477
        movff   (Common_RAM + 15), (Common_RAM + 10)        ; reg1: 0x00f, reg2: 0x00a
        call    function_087, 0x0                           ; dest: 0x0045fa
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        bz      label_474
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        addwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        movwf   FSR2L, A                                    ; reg: 0xfd9
        movlw   0x00
        addwfc  (Common_RAM + 8), W, A                      ; reg: 0x008
        movwf   FSR2H, A                                    ; reg: 0xfda
        movff   (Common_RAM + 15), INDF2                    ; reg1: 0x00f, reg2: 0xfdf
        incf    (Common_RAM + 14), F, A                     ; reg: 0x00e
        bra     label_475                                   ; dest: 0x003aec

label_474:                                                  ; address: 0x003ae2

        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        xorlw   0x3a
        bnz     label_475
        movlw   0x01
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d

label_475:                                                  ; address: 0x003aec

        clrf    (Common_RAM + 12), A                        ; reg: 0x00c
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        bz      label_476
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        xorlw   0x0d
        bnz     label_476
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        xorlw   0x0a
        bnz     label_476
        movlw   0x01
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c

label_476:                                                  ; address: 0x003b02

        movff   (Common_RAM + 12), (Common_RAM + 11)        ; reg1: 0x00c, reg2: 0x00b

label_477:                                                  ; address: 0x003b06

        call    function_118, 0x0                           ; dest: 0x00490c
        bc      label_478
        movf    (Common_RAM + 9), W, A                      ; reg: 0x009
        subwf   (Common_RAM + 14), W, A                     ; reg: 0x00e
        bc      label_478
        movf    (Common_RAM + 11), W, A                     ; reg: 0x00b
        bz      label_473

label_478:                                                  ; address: 0x003b16

        call    function_123, 0x0                           ; dest: 0x00494c
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        return  0x0

function_049:                                               ; address: 0x003b1e

        pop
        btfss   PIR2, USBIF, A                              ; reg: 0xfa1, bit: 5
        bra     label_479                                   ; dest: 0x003b28
        bcf     PIR2, USBIF, A                              ; reg: 0xfa1, bit: 5
        bcf     PIE2, USBIE, A                              ; reg: 0xfa0, bit: 5

label_479:                                                  ; address: 0x003b28

        btfss   INTCON, T0IF, A                             ; reg: 0xff2, bit: 2
        bra     label_480                                   ; dest: 0x003b36
        movlb   0x0
        bsf     0x7e, 0x0, B                                ; reg: 0x07e
        bcf     INTCON, T0IF, A                             ; reg: 0xff2, bit: 2
        bcf     INTCON, T0IE, A                             ; reg: 0xff2, bit: 5
        bcf     T0CON, TMR0ON, A                            ; reg: 0xfd5, bit: 7

label_480:                                                  ; address: 0x003b36

        btfss   PIR2, TMR3IF, A                             ; reg: 0xfa1, bit: 1
        bra     label_482                                   ; dest: 0x003b5c
        bcf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        movlw   0xf8
        movwf   TMR3H, A                                    ; reg: 0xfb3
        movlw   0x30
        movwf   TMR3L, A                                    ; reg: 0xfb2
        bsf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        bcf     PIR2, TMR3IF, A                             ; reg: 0xfa1, bit: 1
        movlb   0x0
        movf    0x8d, W, B                                  ; reg: 0x08d
        iorwf   0x8c, W, B                                  ; reg: 0x08c
        bz      label_481
        decf    0x8c, F, B                                  ; reg: 0x08c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        decf    0x8d, F, B                                  ; reg: 0x08d
        bra     label_482                                   ; dest: 0x003b5c

label_481:                                                  ; address: 0x003b58

        bcf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        bcf     PIE2, TMR3IE, A                             ; reg: 0xfa0, bit: 1

label_482:                                                  ; address: 0x003b5c

        btfss   PIR1, RCIF, A                               ; reg: 0xf9e, bit: 5
        bra     label_484                                   ; dest: 0x003b8c
        movlw   0x00
        movlb   0x0
        addwf   0xc7, W, B                                  ; reg: 0x0c7
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movff   RCREG, INDF2                                ; reg1: 0xfae, reg2: 0xfdf
        incf    0xc7, F, B                                  ; reg: 0x0c7
        movlw   0xbf
        cpfsgt  0xc7, B                                     ; reg: 0x0c7
        bra     label_483                                   ; dest: 0x003b7c
        clrf    0xc7, B                                     ; reg: 0x0c7

label_483:                                                  ; address: 0x003b7c

        btfss   RCSTA, OERR, A                              ; reg: 0xfab, bit: 1
        bra     label_484                                   ; dest: 0x003b8c
        bcf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        dw      0xf000
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        bsf     (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        movlb   0x0
        clrf    0x98, B                                     ; reg: 0x098

label_484:                                                  ; address: 0x003b8c

        movff   (Common_RAM + 2), FSR2H                     ; reg1: 0x002, reg2: 0xfda
        movff   (Common_RAM + 1), FSR2L                     ; reg1: 0x001, reg2: 0xfd9
        retfie  0x1

function_050:                                               ; address: 0x003b96

        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x05
        call    function_111, 0x0                           ; dest: 0x004896
        movf    (Common_RAM + 95), W, A                     ; reg: 0x05f
        call    function_111, 0x0                           ; dest: 0x004896
        call    function_120, 0x0                           ; dest: 0x00492e
        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x07
        call    function_111, 0x0                           ; dest: 0x004896
        movlb   0x0
        movf    0x6e, W, B                                  ; reg: 0x06e
        addlw   0x60
        call    function_111, 0x0                           ; dest: 0x004896
        call    function_120, 0x0                           ; dest: 0x00492e
        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x03
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x01
        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        movlw   0x00
        call    function_111, 0x0                           ; dest: 0x004896
        call    function_120, 0x0                           ; dest: 0x00492e
        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x06
        call    function_111, 0x0                           ; dest: 0x004896
        movlb   0x0
        movf    0x99, W, B                                  ; reg: 0x099
        call    function_111, 0x0                           ; dest: 0x004896
        call    function_120, 0x0                           ; dest: 0x00492e
        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x1d
        call    function_111, 0x0                           ; dest: 0x004896
        movlb   0x0
        movf    0xb8, W, B                                  ; reg: 0x0b8
        goto    function_111                                ; dest: 0x004896

function_051:                                               ; address: 0x003c0c

        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x1b
        call    function_093, 0x0                           ; dest: 0x0046ba
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x1c
        call    function_093, 0x0                           ; dest: 0x0046ba
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x1d
        call    function_093, 0x0                           ; dest: 0x0046ba
        btfss   PORTC, RC2, A                               ; reg: 0xf82, bit: 2
        bra     label_485                                   ; dest: 0x003c34
        bsf     LATB, LATB2, A                              ; reg: 0xf8a, bit: 2
        clrf    SPBRGH, A                                   ; reg: 0xfb0
        movlw   0x3f
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bsf     OSCCON, SCS1, A                             ; reg: 0xfd3, bit: 1
        bra     label_486                                   ; dest: 0x003c3e

label_485:                                                  ; address: 0x003c34

        bcf     LATB, LATB2, A                              ; reg: 0xf8a, bit: 2
        clrf    SPBRGH, A                                   ; reg: 0xfb0
        movlw   0x7f
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bcf     OSCCON, SCS1, A                             ; reg: 0xfd3, bit: 1

label_486:                                                  ; address: 0x003c3e

        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        bcf     LATA, LATA6, A                              ; reg: 0xf89, bit: 6
        bcf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3
        bcf     LATA, LATA4, A                              ; reg: 0xf89, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        movlw   0x28
        movlb   0x0
        subwf   0x88, W, B                                  ; reg: 0x088
        movlw   0x02
        subwfb  0x89, W, B                                  ; reg: 0x089
        bc      label_488
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        clrf    (Common_RAM + 9), A                         ; reg: 0x009

label_487:                                                  ; address: 0x003c58

        movff   (Common_RAM + 8), (Common_RAM + 6)          ; reg1: 0x008, reg2: 0x006
        movlw   0x1c
        call    function_093, 0x0                           ; dest: 0x0046ba
        movlw   0x01
        xorwf   (Common_RAM + 8), F, A                      ; reg: 0x008
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0xfa
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        call    function_079, 0x0                           ; dest: 0x00447e
        incf    (Common_RAM + 9), F, A                      ; reg: 0x009
        movlw   0x04
        cpfsgt  (Common_RAM + 9), A                         ; reg: 0x009
        bra     label_487                                   ; dest: 0x003c58

label_488:                                                  ; address: 0x003c78

        bcf     LATB, LATB3, A                              ; reg: 0xf8a, bit: 3
        bcf     T0CON, TMR0ON, A                            ; reg: 0xfd5, bit: 7
        bcf     INTCON, T0IE, A                             ; reg: 0xff2, bit: 5
        goto    function_116                                ; dest: 0x0048f0

function_052:                                               ; address: 0x003c82

        movlb   0x0
        clrf    0xca, B                                     ; reg: 0x0ca
        movlb   0x4
        btfsc   0x0c, 0x7, B                                ; reg: 0x40c
        bra     label_491                                   ; dest: 0x003ce6
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 13), W, B                     ; reg: 0x00d
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        movff   0x40d, (Common_RAM + 5)                     ; reg2: 0x005
        movlb   0x0
        clrf    0xca, B                                     ; reg: 0x0ca
        bra     label_490                                   ; dest: 0x003cbc

label_489:                                                  ; address: 0x003c9c

        movlw   0x2c
        movlb   0x0
        addwf   0xca, W, B                                  ; reg: 0x0ca
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x04
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    0xca, W, B                                  ; reg: 0x0ca
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   FSR1L, A                                    ; reg: 0xfe1
        movlw   0x00
        addwfc  (Common_RAM + 4), W, A                      ; reg: 0x004
        movwf   FSR1H, A                                    ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        incf    0xca, F, B                                  ; reg: 0x0ca

label_490:                                                  ; address: 0x003cbc

        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   0xca, W, B                                  ; reg: 0x0ca
        bnc     label_489
        movlw   0x40
        movlb   0x4
        movwf   0x0d, B                                     ; reg: 0x40d
        andwf   0x0c, F, B                                  ; reg: 0x40c
        movlw   0x01
        btfsc   0x0c, 0x6, B                                ; reg: 0x40c
        movlw   0x00
        movwf   0x06, A                                     ; reg: 0x406
        swapf   0x06, F, A                                  ; reg: 0x406
        rlncf   0x06, F, A                                  ; reg: 0x406
        rlncf   0x06, F, A                                  ; reg: 0x406
        movf    0x0c, W, B                                  ; reg: 0x40c
        xorwf   0x06, W, A                                  ; reg: 0x406
        andlw   0xbf
        xorwf   0x06, W, A                                  ; reg: 0x406
        movwf   0x0c, B                                     ; reg: 0x40c
        bsf     0x0c, 0x3, B                                ; reg: 0x40c
        bsf     0x0c, 0x7, B                                ; reg: 0x40c

label_491:                                                  ; address: 0x003ce6

        return  0x0

function_053:                                               ; address: 0x003ce8

        lfsr    0x2, 0x003
        movf    POSTINC2, W, A                              ; reg: 0xfde
        iorwf   POSTINC2, W, A                              ; reg: 0xfde
        iorwf   POSTINC2, W, A                              ; reg: 0xfde
        iorwf   POSTINC2, W, A                              ; reg: 0xfde
        bnz     label_492
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x00
        movwf   POSTINC2, A                                 ; reg: 0xfde
        movwf   POSTDEC2, A                                 ; reg: 0xfdd
        bra     label_493                                   ; dest: 0x003d4c

label_492:                                                  ; address: 0x003d04

        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        andlw   0x7f
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        clrf    (Common_RAM + 10), A                        ; reg: 0x00a
        rlcf    (Common_RAM + 10), F, A                     ; reg: 0x00a
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   (Common_RAM + 9), POSTINC2                  ; reg1: 0x009, reg2: 0xfde
        movff   (Common_RAM + 10), POSTDEC2                 ; reg1: 0x00a, reg2: 0xfdd
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x01
        btfss   (Common_RAM + 5), 0x7, A                    ; reg: 0x005
        movlw   0x00
        iorwf   POSTINC2, F, A                              ; reg: 0xfde
        movlw   0x00
        iorwf   POSTDEC2, F, A                              ; reg: 0xfdd
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x82
        addwf   POSTINC2, F, A                              ; reg: 0xfde
        movlw   0xff
        addwfc  POSTDEC2, F, A                              ; reg: 0xfdd
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        andlw   0x80
        iorlw   0x3f
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        bcf     (Common_RAM + 5), 0x7, A                    ; reg: 0x005

label_493:                                                  ; address: 0x003d4c

        return  0x0

label_494:                                                  ; address: 0x003d4e

        lfsr    0x0, 0x300
        movlw   0xc0

label_495:                                                  ; address: 0x003d54

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decf    WREG, F, A                                  ; reg: 0xfe8
        bnz     label_495
        lfsr    0x0, 0x200
        movlw   0xde

label_496:                                                  ; address: 0x003d60

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decf    WREG, F, A                                  ; reg: 0xfe8
        bnz     label_496
        lfsr    0x0, 0x100
        movlw   0xe5

label_497:                                                  ; address: 0x003d6c

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decf    WREG, F, A                                  ; reg: 0xfe8
        bnz     label_497
        lfsr    0x0, 0x060
        movlw   0x8d

label_498:                                                  ; address: 0x003d78

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decf    WREG, F, A                                  ; reg: 0xfe8
        bnz     label_498
        clrf    (Common_RAM + 95), A                        ; reg: 0x05f
        clrf    (Common_RAM + 94), A                        ; reg: 0x05e
        movlw   0xe6
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x47
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x00
        movwf   TBLPTRU, A                                  ; reg: 0xff8
        lfsr    0x0, 0x1e5
        lfsr    0x1, 0x016

label_499:                                                  ; address: 0x003d96

        tblrd*+
        movff   TABLAT, POSTINC0                            ; reg1: 0xff5, reg2: 0xfee
        movf    POSTDEC1, W, A                              ; reg: 0xfe5
        movf    FSR1L, W, A                                 ; reg: 0xfe1
        bnz     label_499
        movlw   0x00
        movwf   TBLPTRU, A                                  ; reg: 0xff8
        movlb   0x0
        goto    label_606                                   ; dest: 0x0048c6

function_054:                                               ; address: 0x003dac

        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        movff   (Common_RAM + 3), (Common_RAM + 12)         ; reg1: 0x003, reg2: 0x00c
        movff   (Common_RAM + 4), (Common_RAM + 13)         ; reg1: 0x004, reg2: 0x00d
        movff   (Common_RAM + 5), (Common_RAM + 14)         ; reg1: 0x005, reg2: 0x00e
        movff   (Common_RAM + 6), (Common_RAM + 15)         ; reg1: 0x006, reg2: 0x00f
        bra     label_502                                   ; dest: 0x003df4

label_500:                                                  ; address: 0x003dc0

        movff   (Common_RAM + 14), TBLPTRU                  ; reg1: 0x00e, reg2: 0xff8
        movff   (Common_RAM + 13), TBLPTRH                  ; reg1: 0x00d, reg2: 0xff7
        movff   (Common_RAM + 12), TBLPTRL                  ; reg1: 0x00c, reg2: 0xff6
        bsf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7
        bcf     EECON1, CFGS, A                             ; reg: 0xfa6, bit: 6
        bsf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        bsf     EECON1, FREE, A                             ; reg: 0xfa6, bit: 4
        btfss   INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        bra     label_501                                   ; dest: 0x003dde
        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x01
        movwf   (Common_RAM + 11), A                        ; reg: 0x00b

label_501:                                                  ; address: 0x003dde

        call    function_076, 0x0                           ; dest: 0x004406
        movf    (Common_RAM + 11), W, A                     ; reg: 0x00b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x40
        addwf   (Common_RAM + 12), F, A                     ; reg: 0x00c
        movlw   0x00
        addwfc  (Common_RAM + 13), F, A                     ; reg: 0x00d
        addwfc  (Common_RAM + 14), F, A                     ; reg: 0x00e
        addwfc  (Common_RAM + 15), F, A                     ; reg: 0x00f

label_502:                                                  ; address: 0x003df4

        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        subwf   (Common_RAM + 12), W, A                     ; reg: 0x00c
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        subwfb  (Common_RAM + 13), W, A                     ; reg: 0x00d
        movf    (Common_RAM + 9), W, A                      ; reg: 0x009
        subwfb  (Common_RAM + 14), W, A                     ; reg: 0x00e
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        subwfb  (Common_RAM + 15), W, A                     ; reg: 0x00f
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        bra     label_500                                   ; dest: 0x003dc0

function_055:                                               ; address: 0x003e0a

        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        xorlw   0x80
        addlw   0x80
        bnz     label_503
        movlw   0x00
        subwf   (Common_RAM + 15), W, A                     ; reg: 0x00f
        bnz     label_503
        movlw   0x00
        subwf   (Common_RAM + 14), W, A                     ; reg: 0x00e
        bnz     label_503
        movlw   0x00
        subwf   (Common_RAM + 13), W, A                     ; reg: 0x00d

label_503:                                                  ; address: 0x003e24

        bc      label_504
        comf    (Common_RAM + 16), F, A                     ; reg: 0x010
        comf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        comf    (Common_RAM + 14), F, A                     ; reg: 0x00e
        negf    (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x00
        addwfc  (Common_RAM + 14), F, A                     ; reg: 0x00e
        addwfc  (Common_RAM + 15), F, A                     ; reg: 0x00f
        addwfc  (Common_RAM + 16), F, A                     ; reg: 0x010
        movlw   0x01
        movwf   (Common_RAM + 17), A                        ; reg: 0x011

label_504:                                                  ; address: 0x003e3a

        movff   (Common_RAM + 13), (Common_RAM + 3)         ; reg1: 0x00d, reg2: 0x003
        movff   (Common_RAM + 14), (Common_RAM + 4)         ; reg1: 0x00e, reg2: 0x004
        movff   (Common_RAM + 15), (Common_RAM + 5)         ; reg1: 0x00f, reg2: 0x005
        movff   (Common_RAM + 16), (Common_RAM + 6)         ; reg1: 0x010, reg2: 0x006
        movlw   0x96
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movff   (Common_RAM + 17), (Common_RAM + 8)         ; reg1: 0x011, reg2: 0x008
        call    function_029, 0x0                           ; dest: 0x0030d8
        movff   (Common_RAM + 3), (Common_RAM + 13)         ; reg1: 0x003, reg2: 0x00d
        movff   (Common_RAM + 4), (Common_RAM + 14)         ; reg1: 0x004, reg2: 0x00e
        movff   (Common_RAM + 5), (Common_RAM + 15)         ; reg1: 0x005, reg2: 0x00f
        movff   (Common_RAM + 6), (Common_RAM + 16)         ; reg1: 0x006, reg2: 0x010
        return  0x0

function_056:                                               ; address: 0x003e68

        movff   WREG, (Common_RAM + 5)                      ; reg1: 0xfe8, reg2: 0x005
        movff   (Common_RAM + 5), SSPBUF                    ; reg1: 0x005, reg2: 0xfc9
        btfsc   SSPCON1, WCOL, A                            ; reg: 0xfc6, bit: 7
        bra     label_508                                   ; dest: 0x003ec2
        movff   SSPCON1, (Common_RAM + 4)                   ; reg1: 0xfc6, reg2: 0x004
        movlw   0x0f
        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        xorlw   0x08
        bz      label_506
        movff   SSPCON1, (Common_RAM + 4)                   ; reg1: 0xfc6, reg2: 0x004
        movlw   0x0f
        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        xorlw   0x0b
        bz      label_506
        bsf     SSPCON1, CKP, A                             ; reg: 0xfc6, bit: 4

label_505:                                                  ; address: 0x003e92

        btfss   PIR1, SSPIF, A                              ; reg: 0xf9e, bit: 3
        bra     label_505                                   ; dest: 0x003e92
        btfss   SSPSTAT, R, A                               ; reg: 0xfc7, bit: 2
        movf    SSPSTAT, W, A                               ; reg: 0xfc7
        bra     label_508                                   ; dest: 0x003ec2

label_506:                                                  ; address: 0x003e9c

        movff   SSPCON1, (Common_RAM + 4)                   ; reg1: 0xfc6, reg2: 0x004
        movlw   0x0f
        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        xorlw   0x08
        bz      label_507
        movff   SSPCON1, (Common_RAM + 4)                   ; reg1: 0xfc6, reg2: 0x004
        movlw   0x0f
        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        xorlw   0x0b
        bnz     label_508

label_507:                                                  ; address: 0x003eb8

        btfsc   SSPSTAT, BF, A                              ; reg: 0xfc7, bit: 0
        bra     label_507                                   ; dest: 0x003eb8
        call    function_113, 0x0                           ; dest: 0x0048b6
        movf    SSPCON2, W, A                               ; reg: 0xfc5

label_508:                                                  ; address: 0x003ec2

        return  0x0

function_057:                                               ; address: 0x003ec4

        movff   WREG, (Common_RAM + 45)                     ; reg1: 0xfe8, reg2: 0x02d
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   POSTINC2, (Common_RAM + 18)                 ; reg1: 0xfde, reg2: 0x012
        movff   POSTINC2, (Common_RAM + 19)                 ; reg1: 0xfde, reg2: 0x013
        movff   POSTINC2, (Common_RAM + 20)                 ; reg1: 0xfde, reg2: 0x014
        movff   POSTINC2, (Common_RAM + 21)                 ; reg1: 0xfde, reg2: 0x015
        movff   (Common_RAM + 37), (Common_RAM + 22)        ; reg1: 0x025, reg2: 0x016
        movff   (Common_RAM + 38), (Common_RAM + 23)        ; reg1: 0x026, reg2: 0x017
        movff   (Common_RAM + 39), (Common_RAM + 24)        ; reg1: 0x027, reg2: 0x018
        movff   (Common_RAM + 40), (Common_RAM + 25)        ; reg1: 0x028, reg2: 0x019
        call    function_017, 0x0                           ; dest: 0x002abc
        movff   (Common_RAM + 18), (Common_RAM + 41)        ; reg1: 0x012, reg2: 0x029
        movff   (Common_RAM + 19), (Common_RAM + 42)        ; reg1: 0x013, reg2: 0x02a
        movff   (Common_RAM + 20), (Common_RAM + 43)        ; reg1: 0x014, reg2: 0x02b
        movff   (Common_RAM + 21), (Common_RAM + 44)        ; reg1: 0x015, reg2: 0x02c
        movf    (Common_RAM + 45), W, A                     ; reg: 0x02d
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   (Common_RAM + 41), POSTINC2                 ; reg1: 0x029, reg2: 0xfde
        movff   (Common_RAM + 42), POSTINC2                 ; reg1: 0x02a, reg2: 0xfde
        movff   (Common_RAM + 43), POSTINC2                 ; reg1: 0x02b, reg2: 0xfde
        movff   (Common_RAM + 44), POSTDEC2                 ; reg1: 0x02c, reg2: 0xfdd
        decf    FSR2L, F, A                                 ; reg: 0xfd9
        decf    FSR2L, F, A                                 ; reg: 0xfd9
        return  0x0

function_058:                                               ; address: 0x003f1e

        movff   WREG, (Common_RAM + 55)                     ; reg1: 0xfe8, reg2: 0x037
        movf    (Common_RAM + 55), W, A                     ; reg: 0x037
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   POSTINC2, (Common_RAM + 32)                 ; reg1: 0xfde, reg2: 0x020
        movff   POSTINC2, (Common_RAM + 33)                 ; reg1: 0xfde, reg2: 0x021
        movff   POSTINC2, (Common_RAM + 34)                 ; reg1: 0xfde, reg2: 0x022
        movff   POSTINC2, (Common_RAM + 35)                 ; reg1: 0xfde, reg2: 0x023
        movff   (Common_RAM + 47), (Common_RAM + 36)        ; reg1: 0x02f, reg2: 0x024
        movff   (Common_RAM + 48), (Common_RAM + 37)        ; reg1: 0x030, reg2: 0x025
        movff   (Common_RAM + 49), (Common_RAM + 38)        ; reg1: 0x031, reg2: 0x026
        movff   (Common_RAM + 50), (Common_RAM + 39)        ; reg1: 0x032, reg2: 0x027
        call    function_011, 0x0                           ; dest: 0x0024c2
        movff   (Common_RAM + 32), (Common_RAM + 51)        ; reg1: 0x020, reg2: 0x033
        movff   (Common_RAM + 33), (Common_RAM + 52)        ; reg1: 0x021, reg2: 0x034
        movff   (Common_RAM + 34), (Common_RAM + 53)        ; reg1: 0x022, reg2: 0x035
        movff   (Common_RAM + 35), (Common_RAM + 54)        ; reg1: 0x023, reg2: 0x036
        movf    (Common_RAM + 55), W, A                     ; reg: 0x037
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movff   (Common_RAM + 51), POSTINC2                 ; reg1: 0x033, reg2: 0xfde
        movff   (Common_RAM + 52), POSTINC2                 ; reg1: 0x034, reg2: 0xfde
        movff   (Common_RAM + 53), POSTINC2                 ; reg1: 0x035, reg2: 0xfde
        movff   (Common_RAM + 54), POSTDEC2                 ; reg1: 0x036, reg2: 0xfdd
        decf    FSR2L, F, A                                 ; reg: 0xfd9
        decf    FSR2L, F, A                                 ; reg: 0xfd9
        return  0x0

function_059:                                               ; address: 0x003f78

        movff   WREG, (Common_RAM + 5)                      ; reg1: 0xfe8, reg2: 0x005
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x2f
        cpfsgt  (Common_RAM + 5), A                         ; reg: 0x005
        bra     label_509                                   ; dest: 0x003f90
        movlw   0x3a
        subwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        bc      label_509
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        addlw   0xd0
        bra     label_510                                   ; dest: 0x003fa0

label_509:                                                  ; address: 0x003f90

        movlw   0x40
        cpfsgt  (Common_RAM + 5), A                         ; reg: 0x005
        bra     label_511                                   ; dest: 0x003fa2
        movlw   0x47
        subwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        bc      label_511
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        addlw   0xc9

label_510:                                                  ; address: 0x003fa0

        movwf   (Common_RAM + 4), A                         ; reg: 0x004

label_511:                                                  ; address: 0x003fa2

        swapf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movlw   0xf0
        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movlw   0x2f
        cpfsgt  (Common_RAM + 3), A                         ; reg: 0x003
        bra     label_512                                   ; dest: 0x003fba
        movlw   0x3a
        subwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        bc      label_512
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        addlw   0xd0
        bra     label_513                                   ; dest: 0x003fca

label_512:                                                  ; address: 0x003fba

        movlw   0x40
        cpfsgt  (Common_RAM + 3), A                         ; reg: 0x003
        bra     label_514                                   ; dest: 0x003fcc
        movlw   0x47
        subwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        bc      label_514
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        addlw   0xc9

label_513:                                                  ; address: 0x003fca

        addwf   (Common_RAM + 4), F, A                      ; reg: 0x004

label_514:                                                  ; address: 0x003fcc

        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        return  0x0

function_060:                                               ; address: 0x003fd0

        movlw   0x40
        cpfsgt  (Common_RAM + 5), A                         ; reg: 0x005
        bra     label_515                                   ; dest: 0x003fd8
        movwf   (Common_RAM + 5), A                         ; reg: 0x005

label_515:                                                  ; address: 0x003fd8

        clrf    (Common_RAM + 7), A                         ; reg: 0x007
        bra     label_517                                   ; dest: 0x003ffa

label_516:                                                  ; address: 0x003fdc

        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   FSR2L, A                                    ; reg: 0xfd9
        movlw   0x00
        addwfc  (Common_RAM + 4), W, A                      ; reg: 0x004
        movwf   FSR2H, A                                    ; reg: 0xfda
        movlw   0x6c
        addwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        movwf   FSR1L, A                                    ; reg: 0xfe1
        clrf    FSR1H, A                                    ; reg: 0xfe2
        movlw   0x04
        addwfc  FSR1H, F, A                                 ; reg: 0xfe2
        movff   INDF2, INDF1                                ; reg1: 0xfdf, reg2: 0xfe7
        incf    (Common_RAM + 7), F, A                      ; reg: 0x007

label_517:                                                  ; address: 0x003ffa

        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        bnc     label_516
        movff   (Common_RAM + 5), 0x411                     ; reg1: 0x005
        movlw   0x40
        movlb   0x4
        andwf   0x10, F, B                                  ; reg: 0x410
        movlw   0x01
        btfsc   0x10, 0x6, B                                ; reg: 0x410
        movlw   0x00
        movwf   0x06, A                                     ; reg: 0x406
        swapf   0x06, F, A                                  ; reg: 0x406
        rlncf   0x06, F, A                                  ; reg: 0x406
        rlncf   0x06, F, A                                  ; reg: 0x406
        movf    0x10, W, B                                  ; reg: 0x410
        xorwf   0x06, W, A                                  ; reg: 0x406
        andlw   0xbf
        xorwf   0x06, W, A                                  ; reg: 0x406
        movwf   0x10, B                                     ; reg: 0x410
        bsf     0x10, 0x3, B                                ; reg: 0x410
        bsf     0x10, 0x7, B                                ; reg: 0x410
        return  0x0

function_061:                                               ; address: 0x004028

        movff   (Common_RAM + 3), (Common_RAM + 11)         ; reg1: 0x003, reg2: 0x00b
        movff   (Common_RAM + 4), (Common_RAM + 12)         ; reg1: 0x004, reg2: 0x00c
        movff   (Common_RAM + 5), (Common_RAM + 13)         ; reg1: 0x005, reg2: 0x00d
        movff   (Common_RAM + 6), (Common_RAM + 14)         ; reg1: 0x006, reg2: 0x00e
        movff   TBLPTRU, (Common_RAM + 17)                  ; reg1: 0xff8, reg2: 0x011
        movff   TBLPTRH, (Common_RAM + 16)                  ; reg1: 0xff7, reg2: 0x010
        movff   TBLPTRL, (Common_RAM + 15)                  ; reg1: 0xff6, reg2: 0x00f
        movff   (Common_RAM + 13), TBLPTRU                  ; reg1: 0x00d, reg2: 0xff8
        movff   (Common_RAM + 12), TBLPTRH                  ; reg1: 0x00c, reg2: 0xff7
        movff   (Common_RAM + 11), TBLPTRL                  ; reg1: 0x00b, reg2: 0xff6
        bra     label_519                                   ; dest: 0x004064

label_518:                                                  ; address: 0x004052

        tblrd*+
        movff   (Common_RAM + 9), FSR2L                     ; reg1: 0x009, reg2: 0xfd9
        movff   (Common_RAM + 10), FSR2H                    ; reg1: 0x00a, reg2: 0xfda
        movff   TABLAT, INDF2                               ; reg1: 0xff5, reg2: 0xfdf
        infsnz  (Common_RAM + 9), F, A                      ; reg: 0x009
        incf    (Common_RAM + 10), F, A                     ; reg: 0x00a

label_519:                                                  ; address: 0x004064

        decf    (Common_RAM + 7), F, A                      ; reg: 0x007
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        decf    (Common_RAM + 8), F, A                      ; reg: 0x008
        incf    (Common_RAM + 7), W, A                      ; reg: 0x007
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        incf    (Common_RAM + 8), W, A                      ; reg: 0x008
        bnz     label_518
        movff   (Common_RAM + 17), TBLPTRU                  ; reg1: 0x011, reg2: 0xff8
        movff   (Common_RAM + 16), TBLPTRH                  ; reg1: 0x010, reg2: 0xff7
        movff   (Common_RAM + 15), TBLPTRL                  ; reg1: 0x00f, reg2: 0xff6
        return  0x0

function_062:                                               ; address: 0x004080

        movff   WREG, (Common_RAM + 3)                      ; reg1: 0xfe8, reg2: 0x003
        movlw   0x08
        movlb   0x1
        movwf   0x17, B                                     ; reg: 0x117
        movlw   0x04
        movwf   0x19, B                                     ; reg: 0x119
        movlw   0x1c
        movwf   0x18, B                                     ; reg: 0x118
        tstfsz  0x03, A                                     ; reg: 0x103
        bra     label_520                                   ; dest: 0x0040a8
        movlw   0x04
        movwf   (Common_RAM + 25), B                        ; reg: 0x019
        movlw   0x14
        movwf   (Common_RAM + 24), B                        ; reg: 0x018
        movlw   0x04
        movlb   0x0
        movwf   0x79, B                                     ; reg: 0x079
        movlw   0x00
        bra     label_521                                   ; dest: 0x0040ae

label_520:                                                  ; address: 0x0040a8

        movlw   0x04
        movlb   0x0
        movwf   0x79, B                                     ; reg: 0x079

label_521:                                                  ; address: 0x0040ae

        movwf   0x78, B                                     ; reg: 0x078
        movff   0x078, FSR2L                                ; reg2: 0xfd9
        movff   0x079, FSR2H                                ; reg2: 0xfda
        movff   0x116, POSTINC2                             ; reg2: 0xfde
        movff   0x117, POSTINC2                             ; reg2: 0xfde
        movff   0x118, POSTINC2                             ; reg2: 0xfde
        movff   0x119, POSTINC2                             ; reg2: 0xfde
        movff   0x078, FSR2L                                ; reg2: 0xfd9
        movff   0x079, FSR2H                                ; reg2: 0xfda
        movlb   0x0
        bsf     INDF2, 0x7, A                               ; reg: 0xfdf
        return  0x0

function_063:                                               ; address: 0x0040d6

        movlw   0x03
        movlb   0x0
        movwf   0xcd, B                                     ; reg: 0x0cd
        clrf    UEIE, A                                     ; reg: 0xf6b
        clrf    UIR, A                                      ; reg: 0xf68
        movlw   0x7b
        movwf   UIE, A                                      ; reg: 0xf69
        clrf    UADDR, A                                    ; reg: 0xf6e
        clrf    UEP1, A                                     ; reg: 0xf71
        clrf    UEP2, A                                     ; reg: 0xf72
        clrf    UEP3, A                                     ; reg: 0xf73
        clrf    UEP4, A                                     ; reg: 0xf74
        clrf    UEP5, A                                     ; reg: 0xf75
        clrf    UEP6, A                                     ; reg: 0xf76
        clrf    UEP7, A                                     ; reg: 0xf77
        movlw   0x16
        movwf   UEP0, A                                     ; reg: 0xf70
        bsf     UCON, PPBRST, A                             ; reg: 0xf6d, bit: 6
        bra     label_523                                   ; dest: 0x004102

label_522:                                                  ; address: 0x0040fc

        bcf     UIR, TRNIF, A                               ; reg: 0xf68, bit: 3
        call    function_127, 0x0                           ; dest: 0x004962

label_523:                                                  ; address: 0x004102

        btfsc   UIR, TRNIF, A                               ; reg: 0xf68, bit: 3
        bra     label_522                                   ; dest: 0x0040fc
        bcf     UCON, PPBRST, A                             ; reg: 0xf6d, bit: 6
        bcf     UCON, PKTDIS, A                             ; reg: 0xf6d, bit: 4
        movlw   0x04
        movlb   0x1
        movwf   0x16, B                                     ; reg: 0x116
        movlw   0x00
        call    function_062, 0x0                           ; dest: 0x004080
        movlw   0x01
        movwf   0x96, B                                     ; reg: 0x096
        clrf    0xce, B                                     ; reg: 0x0ce
        clrf    0xeb, B                                     ; reg: 0x0eb
        movlw   0x00
        goto    function_117                                ; dest: 0x0048fe

function_064:                                               ; address: 0x004124

        clrf    (Common_RAM + 7), A                         ; reg: 0x007
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        iorwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        bz      label_528
        movlw   0x01
        movwf   (Common_RAM + 9), A                         ; reg: 0x009
        bra     label_525                                   ; dest: 0x00413c

label_524:                                                  ; address: 0x004134

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        incf    (Common_RAM + 9), F, A                      ; reg: 0x009

label_525:                                                  ; address: 0x00413c

        btfss   (Common_RAM + 6), 0x7, A                    ; reg: 0x006
        bra     label_524                                   ; dest: 0x004134

label_526:                                                  ; address: 0x004140

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 7), F, A                      ; reg: 0x007
        rlcf    (Common_RAM + 8), F, A                      ; reg: 0x008
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        subwfb  (Common_RAM + 4), W, A                      ; reg: 0x004
        bnc     label_527
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        subwfb  (Common_RAM + 4), F, A                      ; reg: 0x004
        bsf     (Common_RAM + 7), 0x0, A                    ; reg: 0x007

label_527:                                                  ; address: 0x00415a

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        rrcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        decfsz  (Common_RAM + 9), F, A                      ; reg: 0x009
        bra     label_526                                   ; dest: 0x004140

label_528:                                                  ; address: 0x004164

        movff   (Common_RAM + 7), (Common_RAM + 3)          ; reg1: 0x007, reg2: 0x003
        movff   (Common_RAM + 8), (Common_RAM + 4)          ; reg1: 0x008, reg2: 0x004
        return  0x0

label_529:                                                  ; address: 0x00416e

        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_532                                   ; dest: 0x0041b4
        movf    0xa1, W, B                                  ; reg: 0x0a1
        xorlw   0x64
        bnz     label_531
        btfsc   ADCON0, GO, A                               ; reg: 0xfc2, bit: 1
        bra     label_530                                   ; dest: 0x0041ae
        movf    ADRESH, W, A                                ; reg: 0xfc4
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 3), A                         ; reg: 0x003
        movf    ADRESL, W, A                                ; reg: 0xfc3
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   0x88, B                                     ; reg: 0x088
        movlw   0x00
        addwfc  (Common_RAM + 4), W, A                      ; reg: 0x004
        movwf   0x89, B                                     ; reg: 0x089
        movlw   0x29
        subwf   0x88, W, B                                  ; reg: 0x088
        movlw   0x02
        subwfb  0x89, W, B                                  ; reg: 0x089
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        bsf     0x94, 0x2, B                                ; reg: 0x094
        bsf     ADCON0, GO, A                               ; reg: 0xfc2, bit: 1
        btfss   0x94, 0x2, B                                ; reg: 0x094
        bra     label_530                                   ; dest: 0x0041ae
        movlw   0x28
        subwf   0x88, W, B                                  ; reg: 0x088
        movlw   0x02
        subwfb  0x89, W, B                                  ; reg: 0x089
        bc      label_530
        bcf     (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bsf     0x7e, 0x2, B                                ; reg: 0x07e

label_530:                                                  ; address: 0x0041ae

        clrf    0xa1, B                                     ; reg: 0x0a1
        bra     label_532                                   ; dest: 0x0041b4

label_531:                                                  ; address: 0x0041b2

        incf    0xa1, F, B                                  ; reg: 0x0a1

label_532:                                                  ; address: 0x0041b4

        return  0x0

function_065:                                               ; address: 0x0041b6

        movff   WREG, (Common_RAM + 23)                     ; reg1: 0xfe8, reg2: 0x017
        movff   (Common_RAM + 23), (Common_RAM + 22)        ; reg1: 0x017, reg2: 0x016
        movf    (Common_RAM + 19), W, A                     ; reg: 0x013
        xorlw   0x80
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x80
        subwf   PRODL, W, A                                 ; reg: 0xff3
        movlw   0x00
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        subwf   (Common_RAM + 18), W, A                     ; reg: 0x012
        bc      label_533
        movf    (Common_RAM + 23), W, A                     ; reg: 0x017
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x2d
        movwf   INDF2, A                                    ; reg: 0xfdf
        incf    (Common_RAM + 23), F, A                     ; reg: 0x017
        negf    (Common_RAM + 18), A                        ; reg: 0x012
        comf    (Common_RAM + 19), F, A                     ; reg: 0x013
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        incf    (Common_RAM + 19), F, A                     ; reg: 0x013

label_533:                                                  ; address: 0x0041e4

        movff   (Common_RAM + 18), (Common_RAM + 10)        ; reg1: 0x012, reg2: 0x00a
        movff   (Common_RAM + 19), (Common_RAM + 11)        ; reg1: 0x013, reg2: 0x00b
        movff   (Common_RAM + 20), (Common_RAM + 12)        ; reg1: 0x014, reg2: 0x00c
        movff   (Common_RAM + 21), (Common_RAM + 13)        ; reg1: 0x015, reg2: 0x00d
        movf    (Common_RAM + 23), W, A                     ; reg: 0x017
        call    function_034, 0x0                           ; dest: 0x0034c8
        movf    (Common_RAM + 22), W, A                     ; reg: 0x016
        return  0x0

function_066:                                               ; address: 0x0041fe

        movlw   0x01
        movwf   0xc8, B                                     ; reg: 0x0c8
        clrf    UEP1, A                                     ; reg: 0xf71
        clrf    UEP2, A                                     ; reg: 0xf72
        clrf    UEP3, A                                     ; reg: 0xf73
        clrf    UEP4, A                                     ; reg: 0xf74
        clrf    UEP5, A                                     ; reg: 0xf75
        clrf    UEP6, A                                     ; reg: 0xf76
        clrf    UEP7, A                                     ; reg: 0xf77
        clrf    0x91, B                                     ; reg: 0x091

label_534:                                                  ; address: 0x004212

        movf    0x91, W, B                                  ; reg: 0x091
        addlw   0xec
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        clrf    INDF2, A                                    ; reg: 0xfdf
        incf    0x91, F, B                                  ; reg: 0x091
        movf    0x91, W, B                                  ; reg: 0x091
        bz      label_534
        movff   0x0d1, 0x0eb
        movf    0xeb, W, B                                  ; reg: 0x0eb
        call    function_117, 0x0                           ; dest: 0x0048fe
        movlb   0x0
        tstfsz  0xd1, B                                     ; reg: 0x0d1
        bra     label_535                                   ; dest: 0x004236
        movlw   0x05
        bra     label_536                                   ; dest: 0x004238

label_535:                                                  ; address: 0x004236

        movlw   0x06

label_536:                                                  ; address: 0x004238

        movwf   0xcd, B                                     ; reg: 0x0cd
        return  0x0

function_067:                                               ; address: 0x00423c

        movff   WREG, (Common_RAM + 6)                      ; reg1: 0xfe8, reg2: 0x006
        call    function_113, 0x0                           ; dest: 0x0048b6
        bsf     SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0

label_537:                                                  ; address: 0x004246

        btfsc   SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0
        bra     label_537                                   ; dest: 0x004246
        movlw   0xe2
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        call    function_056, 0x0                           ; dest: 0x003e68
        bsf     SSPCON2, RSEN, A                            ; reg: 0xfc5, bit: 1

label_538:                                                  ; address: 0x004258

        btfsc   SSPCON2, RSEN, A                            ; reg: 0xfc5, bit: 1
        bra     label_538                                   ; dest: 0x004258
        movlw   0xe3
        call    function_056, 0x0                           ; dest: 0x003e68
        call    function_089, 0x0                           ; dest: 0x00464c
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        bsf     SSPCON2, ACKDT, A                           ; reg: 0xfc5, bit: 5
        bsf     SSPCON2, ACKEN, A                           ; reg: 0xfc5, bit: 4

label_539:                                                  ; address: 0x00426c

        btfsc   SSPCON2, ACKEN, A                           ; reg: 0xfc5, bit: 4
        bra     label_539                                   ; dest: 0x00426c
        bsf     SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2

label_540:                                                  ; address: 0x004272

        btfsc   SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2
        bra     label_540                                   ; dest: 0x004272
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        return  0x0

function_068:                                               ; address: 0x00427a

        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        iorwf   (Common_RAM + 5), W, A                      ; reg: 0x005
        bz      label_545
        movlw   0x01
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        bra     label_542                                   ; dest: 0x00428e

label_541:                                                  ; address: 0x004286

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        incf    (Common_RAM + 7), F, A                      ; reg: 0x007

label_542:                                                  ; address: 0x00428e

        btfss   (Common_RAM + 6), 0x7, A                    ; reg: 0x006
        bra     label_541                                   ; dest: 0x004286

label_543:                                                  ; address: 0x004292

        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        subwfb  (Common_RAM + 4), W, A                      ; reg: 0x004
        bnc     label_544
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        subwfb  (Common_RAM + 4), F, A                      ; reg: 0x004

label_544:                                                  ; address: 0x0042a4

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rrcf    (Common_RAM + 6), F, A                      ; reg: 0x006
        rrcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        decfsz  (Common_RAM + 7), F, A                      ; reg: 0x007
        bra     label_543                                   ; dest: 0x004292

label_545:                                                  ; address: 0x0042ae

        movff   (Common_RAM + 3), (Common_RAM + 3)          ; reg1: 0x003, reg2: 0x003
        movff   (Common_RAM + 4), (Common_RAM + 4)          ; reg1: 0x004, reg2: 0x004
        return  0x0

function_069:                                               ; address: 0x0042b8

        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x30
        movwf   TBLPTRU, A                                  ; reg: 0xff8
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x0b
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0xa0
        movwf   TABLAT, A                                   ; reg: 0xff5
        tblwt*
        movlw   0xc4
        movwf   EECON1, A                                   ; reg: 0xfa6
        call    function_076, 0x0                           ; dest: 0x004406

label_546:                                                  ; address: 0x0042d2

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     label_546                                   ; dest: 0x0042d2
        movlw   0x30
        movwf   TBLPTRU, A                                  ; reg: 0xff8
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        clrf    TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x3a
        movwf   TABLAT, A                                   ; reg: 0xff5
        tblwt*
        movlw   0xc4
        movwf   EECON1, A                                   ; reg: 0xfa6
        call    function_076, 0x0                           ; dest: 0x004406

label_547:                                                  ; address: 0x0042ec

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     label_547                                   ; dest: 0x0042ec
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        return  0x0

function_070:                                               ; address: 0x0042f4

        movlb   0x4
        clrf    0x08, B                                     ; reg: 0x408
        movlb   0x0
        clrf    0xcc, B                                     ; reg: 0x0cc
        movlb   0x4
        btfss   0x00, 0x7, B                                ; reg: 0x400
        bra     label_548                                   ; dest: 0x004308
        clrf    Common_RAM, B                               ; reg: 0x000
        movlb   0x0
        clrf    0x96, B                                     ; reg: 0x096

label_548:                                                  ; address: 0x004308

        movlb   0x4
        btfss   0x04, 0x7, B                                ; reg: 0x404
        bra     label_549                                   ; dest: 0x004316
        clrf    (Common_RAM + 4), B                         ; reg: 0x004
        movlw   0x01
        movlb   0x0
        movwf   0x96, B                                     ; reg: 0x096

label_549:                                                  ; address: 0x004316

        movlb   0x0
        clrf    0xc9, B                                     ; reg: 0x0c9
        clrf    0xc8, B                                     ; reg: 0x0c8
        clrf    0xe7, B                                     ; reg: 0x0e7
        clrf    0xe8, B                                     ; reg: 0x0e8
        bcf     UCON, PKTDIS, A                             ; reg: 0xf6d, bit: 4
        call    function_039, 0x0                           ; dest: 0x003682
        call    function_125, 0x0                           ; dest: 0x00495a
        goto    label_400                                   ; dest: 0x00324c

function_071:                                               ; address: 0x00432e

        movlw   0x80
        xorwf   (Common_RAM + 64), F, A                     ; reg: 0x040
        movff   (Common_RAM + 57), (Common_RAM + 32)        ; reg1: 0x039, reg2: 0x020
        movff   (Common_RAM + 58), (Common_RAM + 33)        ; reg1: 0x03a, reg2: 0x021
        movff   (Common_RAM + 59), (Common_RAM + 34)        ; reg1: 0x03b, reg2: 0x022
        movff   (Common_RAM + 60), (Common_RAM + 35)        ; reg1: 0x03c, reg2: 0x023
        movff   (Common_RAM + 61), (Common_RAM + 36)        ; reg1: 0x03d, reg2: 0x024
        movff   (Common_RAM + 62), (Common_RAM + 37)        ; reg1: 0x03e, reg2: 0x025
        movff   (Common_RAM + 63), (Common_RAM + 38)        ; reg1: 0x03f, reg2: 0x026
        movff   (Common_RAM + 64), (Common_RAM + 39)        ; reg1: 0x040, reg2: 0x027
        call    function_011, 0x0                           ; dest: 0x0024c2
        movff   (Common_RAM + 32), (Common_RAM + 57)        ; reg1: 0x020, reg2: 0x039
        movff   (Common_RAM + 33), (Common_RAM + 58)        ; reg1: 0x021, reg2: 0x03a
        movff   (Common_RAM + 34), (Common_RAM + 59)        ; reg1: 0x022, reg2: 0x03b
        movff   (Common_RAM + 35), (Common_RAM + 60)        ; reg1: 0x023, reg2: 0x03c
        return  0x0

function_072:                                               ; address: 0x004368

        movff   WREG, (Common_RAM + 6)                      ; reg1: 0xfe8, reg2: 0x006
        call    function_113, 0x0                           ; dest: 0x0048b6
        bsf     SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0

label_550:                                                  ; address: 0x004372

        btfsc   SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0
        bra     label_550                                   ; dest: 0x004372
        movlw   0x68
        call    function_056, 0x0                           ; dest: 0x003e68
        movlw   0x1f
        call    function_056, 0x0                           ; dest: 0x003e68
        movlw   0x00
        call    function_056, 0x0                           ; dest: 0x003e68
        movlw   0x00
        call    function_056, 0x0                           ; dest: 0x003e68
        movlw   0x00
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        call    function_056, 0x0                           ; dest: 0x003e68
        bsf     SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2

label_551:                                                  ; address: 0x00439c

        btfss   SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2
        return  0x0
        bra     label_551                                   ; dest: 0x00439c

function_073:                                               ; address: 0x0043a2

        movff   WREG, (Common_RAM + 6)                      ; reg1: 0xfe8, reg2: 0x006
        movff   (Common_RAM + 6), (Common_RAM + 4)          ; reg1: 0x006, reg2: 0x004
        swapf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movlw   0x0f
        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        rcall   function_074                                ; dest: 0x0043c8
        call    function_111, 0x0                           ; dest: 0x004896
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        movff   (Common_RAM + 6), (Common_RAM + 4)          ; reg1: 0x006, reg2: 0x004
        movlw   0x0f
        rcall   function_074                                ; dest: 0x0043c8
        call    function_111, 0x0                           ; dest: 0x004896
        xorwf   (Common_RAM + 5), F, A                      ; reg: 0x005
        return  0x0

function_074:                                               ; address: 0x0043c8

        andwf   (Common_RAM + 4), F, A                      ; reg: 0x004
        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        addlw   0x19
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x10
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        tblrd*
        movf    TABLAT, W, A                                ; reg: 0xff5
        return  0x0

function_075:                                               ; address: 0x0043da

        movff   (Common_RAM + 3), EEADR                     ; reg1: 0x003, reg2: 0xfa9
        movff   (Common_RAM + 5), EEDATA                    ; reg1: 0x005, reg2: 0xfa8
        bcf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7
        bcf     EECON1, CFGS, A                             ; reg: 0xfa6, bit: 6
        bsf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        movlw   0x00
        btfsc   INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        rcall   function_076                                ; dest: 0x004406

label_552:                                                  ; address: 0x0043f4

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     label_552                                   ; dest: 0x0043f4
        btfsc   (Common_RAM + 6), 0x0, A                    ; reg: 0x006
        bra     label_553                                   ; dest: 0x004400
        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        bra     label_554                                   ; dest: 0x004402

label_553:                                                  ; address: 0x004400

        bsf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7

label_554:                                                  ; address: 0x004402

        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        return  0x0

function_076:                                               ; address: 0x004406

        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        retlw   0xaa

function_077:                                               ; address: 0x004412

        movf    0xcd, W, B                                  ; reg: 0x0cd
        xorlw   0x04
        bnz     label_555
        movff   0x0d1, UADDR                                ; reg2: 0xf6e
        movf    UADDR, W, A                                 ; reg: 0xf6e
        movlw   0x05
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x03
        movwf   0xcd, B                                     ; reg: 0x0cd

label_555:                                                  ; address: 0x004426

        decf    0xc9, W, B                                  ; reg: 0x0c9
        bnz     label_558
        call    function_036, 0x0                           ; dest: 0x0035f0
        movf    0xcc, W, B                                  ; reg: 0x0cc
        xorlw   0x02
        bnz     label_556
        movlw   0x04
        movlb   0x4
        bra     label_557                                   ; dest: 0x004442

label_556:                                                  ; address: 0x00443a

        movlb   0x4
        movlw   0x48
        btfsc   0x08, 0x6, B                                ; reg: 0x408
        movlw   0x08

label_557:                                                  ; address: 0x004442

        movwf   (Common_RAM + 8), B                         ; reg: 0x008
        bsf     (Common_RAM + 8), 0x7, B                    ; reg: 0x008

label_558:                                                  ; address: 0x004446

        return  0x0

function_078:                                               ; address: 0x004448

        movff   WREG, (Common_RAM + 3)                      ; reg1: 0xfe8, reg2: 0x003
        bra     label_564                                   ; dest: 0x00446c

label_559:                                                  ; address: 0x00444e

        movlw   0x01
        movwf   0xa0, B                                     ; reg: 0x0a0
        clrf    0xb9, B                                     ; reg: 0x0b9
        bra     label_565                                   ; dest: 0x00447c

label_560:                                                  ; address: 0x004456

        clrf    0xa0, B                                     ; reg: 0x0a0
        movlw   0x01
        bra     label_563                                   ; dest: 0x004468

label_561:                                                  ; address: 0x00445c

        movlw   0x02
        movwf   0xa0, B                                     ; reg: 0x0a0
        bra     label_563                                   ; dest: 0x004468

label_562:                                                  ; address: 0x004462

        movlw   0x01
        movwf   0xa0, B                                     ; reg: 0x0a0
        movlw   0x03

label_563:                                                  ; address: 0x004468

        movwf   0xb9, B                                     ; reg: 0x0b9
        bra     label_565                                   ; dest: 0x00447c

label_564:                                                  ; address: 0x00446c

        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        bz      label_559
        xorlw   0x01
        bz      label_560
        xorlw   0x03
        bz      label_561
        xorlw   0x01
        bz      label_562

label_565:                                                  ; address: 0x00447c

        return  0x0

function_079:                                               ; address: 0x00447e

        bcf     PIE2, TMR3IE, A                             ; reg: 0xfa0, bit: 1
        movlw   0x98
        movwf   T3CON, A                                    ; reg: 0xfb1
        bsf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        bra     label_570                                   ; dest: 0x0044a8

label_566:                                                  ; address: 0x004488

        btfss   OSCCON, SCS1, A                             ; reg: 0xfd3, bit: 1
        bra     label_567                                   ; dest: 0x004494
        movlw   0xfc
        movwf   TMR3H, A                                    ; reg: 0xfb3
        movlw   0x18
        bra     label_568                                   ; dest: 0x00449a

label_567:                                                  ; address: 0x004494

        movlw   0xf8
        movwf   TMR3H, A                                    ; reg: 0xfb3
        movlw   0x30

label_568:                                                  ; address: 0x00449a

        movwf   TMR3L, A                                    ; reg: 0xfb2
        bcf     PIR2, TMR3IF, A                             ; reg: 0xfa1, bit: 1

label_569:                                                  ; address: 0x00449e

        btfss   PIR2, TMR3IF, A                             ; reg: 0xfa1, bit: 1
        bra     label_569                                   ; dest: 0x00449e
        decf    (Common_RAM + 3), F, A                      ; reg: 0x003
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        decf    (Common_RAM + 4), F, A                      ; reg: 0x004

label_570:                                                  ; address: 0x0044a8

        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        iorwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        bnz     label_566
        bcf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        return  0x0

function_080:                                               ; address: 0x0044b2

        movff   WREG, (Common_RAM + 27)                     ; reg1: 0xfe8, reg2: 0x01b
        movlw   0x0d
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x0a
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x0c
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x3a
        call    function_111, 0x0                           ; dest: 0x004896
        clrf    (Common_RAM + 25), A                        ; reg: 0x019
        movff   (Common_RAM + 27), (Common_RAM + 24)        ; reg1: 0x01b, reg2: 0x018
        call    function_091, 0x0                           ; dest: 0x004696
        movlw   0x0d
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x0a
        goto    function_111                                ; dest: 0x004896

function_081:                                               ; address: 0x0044e4

        call    function_113, 0x0                           ; dest: 0x0048b6
        bsf     SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0

label_571:                                                  ; address: 0x0044ea

        btfsc   SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0
        bra     label_571                                   ; dest: 0x0044ea
        movlw   0x68
        call    function_056, 0x0                           ; dest: 0x003e68
        movlw   0x30
        call    function_056, 0x0                           ; dest: 0x003e68
        movff   (Common_RAM + 85), (Common_RAM + 73)        ; reg1: 0x055, reg2: 0x049
        movff   (Common_RAM + 86), (Common_RAM + 74)        ; reg1: 0x056, reg2: 0x04a
        movff   (Common_RAM + 87), (Common_RAM + 75)        ; reg1: 0x057, reg2: 0x04b
        movff   (Common_RAM + 88), (Common_RAM + 76)        ; reg1: 0x058, reg2: 0x04c
        call    function_046, 0x0                           ; dest: 0x0039a6
        bsf     SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2

label_572:                                                  ; address: 0x004510

        btfss   SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2
        return  0x0
        bra     label_572                                   ; dest: 0x004510

function_082:                                               ; address: 0x004516

        tstfsz  (Common_RAM + 95), A                        ; reg: 0x05f
        bra     label_579                                   ; dest: 0x004534

label_573:                                                  ; address: 0x00451a

        bcf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3
        bra     label_575                                   ; dest: 0x004520

label_574:                                                  ; address: 0x00451e

        bsf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3

label_575:                                                  ; address: 0x004520

        bcf     LATA, LATA4, A                              ; reg: 0xf89, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        bra     label_580                                   ; dest: 0x004544

label_576:                                                  ; address: 0x004526

        bcf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3
        bcf     LATA, LATA4, A                              ; reg: 0xf89, bit: 4
        bra     label_578                                   ; dest: 0x004530

label_577:                                                  ; address: 0x00452c

        bcf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3
        bsf     LATA, LATA4, A                              ; reg: 0xf89, bit: 4

label_578:                                                  ; address: 0x004530

        bsf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        bra     label_580                                   ; dest: 0x004544

label_579:                                                  ; address: 0x004534

        movf    0x93, W, B                                  ; reg: 0x093
        bz      label_573
        xorlw   0x05
        bz      label_574
        xorlw   0x03
        bz      label_576
        xorlw   0x01
        bz      label_577

label_580:                                                  ; address: 0x004544

        return  0x0

function_083:                                               ; address: 0x004546

        bcf     RCSTA, SPEN, A                              ; reg: 0xfab, bit: 7
        bcf     RCON, IPEN, A                               ; reg: 0xfd0, bit: 7
        movlb   0x0
        clrf    0xc6, B                                     ; reg: 0x0c6
        clrf    0xc7, B                                     ; reg: 0x0c7
        movlw   0x06
        movwf   TXSTA, A                                    ; reg: 0xfac
        movlw   0x80
        movwf   RCSTA, A                                    ; reg: 0xfab
        movlw   0x48
        movwf   BAUDCON, A                                  ; reg: 0xfb8
        bsf     TRISC, RC7, A                               ; reg: 0xf94, bit: 7
        bsf     TRISC, RC6, A                               ; reg: 0xf94, bit: 6
        bcf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        bcf     PIR1, TXIF, A                               ; reg: 0xf9e, bit: 4
        bcf     PIR1, RCIF, A                               ; reg: 0xf9e, bit: 5
        bcf     PIE1, RCIE, A                               ; reg: 0xf9d, bit: 5
        clrf    SPBRGH, A                                   ; reg: 0xfb0
        movlw   0x7f
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bsf     TXSTA, TXEN, A                              ; reg: 0xfac, bit: 5
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        retlw   0x7f

function_084:                                               ; address: 0x004574

        movlw   0x56
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x00
        clrf    (Common_RAM + 50), A                        ; reg: 0x032
        clrf    (Common_RAM + 52), A                        ; reg: 0x034

label_581:                                                  ; address: 0x00457e

        movff   (Common_RAM + 50), (Common_RAM + 19)        ; reg1: 0x032, reg2: 0x013
        movff   (Common_RAM + 51), (Common_RAM + 20)        ; reg1: 0x033, reg2: 0x014
        call    function_043, 0x0                           ; dest: 0x00381c
        movlw   0x18
        addwf   (Common_RAM + 50), F, A                     ; reg: 0x032
        movlw   0x00
        addwfc  (Common_RAM + 51), F, A                     ; reg: 0x033
        incf    (Common_RAM + 52), F, A                     ; reg: 0x034
        movlw   0x5f
        cpfsgt  (Common_RAM + 52), A                        ; reg: 0x034
        bra     label_581                                   ; dest: 0x00457e
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        clrf    (Common_RAM + 19), A                        ; reg: 0x013
        goto    function_043                                ; dest: 0x00381c

function_085:                                               ; address: 0x0045a2

        call    function_009, 0x0                           ; dest: 0x002328
        movf    0xcd, W, B                                  ; reg: 0x0cd
        xorlw   0x06
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        btfsc   UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        bra     label_582                                   ; dest: 0x0045cc
        btfss   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        bra     label_582                                   ; dest: 0x0045cc
        movlb   0x4
        btfsc   0x10, 0x7, B                                ; reg: 0x410
        bra     label_582                                   ; dest: 0x0045cc
        movlb   0x1
        movlw   0x01
        movwf   0x04, A                                     ; reg: 0x104
        movlw   0x5a
        movwf   0x03, A                                     ; reg: 0x103
        movlw   0x40
        movwf   0x05, A                                     ; reg: 0x105
        call    function_060, 0x0                           ; dest: 0x003fd0

label_582:                                                  ; address: 0x0045cc

        return  0x0

function_086:                                               ; address: 0x0045ce

        movff   WREG, (Common_RAM + 17)                     ; reg1: 0xfe8, reg2: 0x011
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x96
        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movlw   0x00
        clrf    (Common_RAM + 8), A                         ; reg: 0x008
        call    function_029, 0x0                           ; dest: 0x0030d8
        movff   (Common_RAM + 3), (Common_RAM + 13)         ; reg1: 0x003, reg2: 0x00d
        movff   (Common_RAM + 4), (Common_RAM + 14)         ; reg1: 0x004, reg2: 0x00e
        movff   (Common_RAM + 5), (Common_RAM + 15)         ; reg1: 0x005, reg2: 0x00f
        movff   (Common_RAM + 6), (Common_RAM + 16)         ; reg1: 0x006, reg2: 0x010
        return  0x0

function_087:                                               ; address: 0x0045fa

        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        call    function_109, 0x0                           ; dest: 0x004872
        iorlw   0x00
        bz      label_583
        movlw   0x00
        movlb   0x0
        addwf   0xc6, W, B                                  ; reg: 0x0c6
        movwf   FSR2L, A                                    ; reg: 0xfd9
        clrf    FSR2H, A                                    ; reg: 0xfda
        movlw   0x02
        addwfc  FSR2H, F, A                                 ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        incf    0xc6, F, B                                  ; reg: 0x0c6
        movlw   0xbf
        cpfsgt  0xc6, B                                     ; reg: 0x0c6
        bra     label_583                                   ; dest: 0x004620
        clrf    0xc6, B                                     ; reg: 0x0c6

label_583:                                                  ; address: 0x004620

        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        return  0x0

function_088:                                               ; address: 0x004624

        clrf    0xca, B                                     ; reg: 0x0ca
        movlw   0x1e
        movwf   UEP1, A                                     ; reg: 0xf71
        movlw   0x40
        movlb   0x4
        movwf   0x0d, B                                     ; reg: 0x40d
        movlw   0x04
        movwf   0x0f, B                                     ; reg: 0x40f
        movlw   0x2c
        movwf   0x0e, B                                     ; reg: 0x40e
        movlw   0x08
        movwf   0x0c, B                                     ; reg: 0x40c
        bsf     0x0c, 0x7, B                                ; reg: 0x40c
        movlw   0x04
        movwf   0x13, B                                     ; reg: 0x413
        movlw   0x6c
        movwf   0x12, B                                     ; reg: 0x412
        movlw   0x40
        movwf   0x10, B                                     ; reg: 0x410
        retlw   0x40

function_089:                                               ; address: 0x00464c

        movff   SSPCON1, (Common_RAM + 3)                   ; reg1: 0xfc6, reg2: 0x003
        movlw   0x0f
        andwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        xorlw   0x08
        bz      label_584
        movff   SSPCON1, (Common_RAM + 3)                   ; reg1: 0xfc6, reg2: 0x003
        movlw   0x0f
        andwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        xorlw   0x0b
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2

label_584:                                                  ; address: 0x004668

        bsf     SSPCON2, RCEN, A                            ; reg: 0xfc5, bit: 3

label_585:                                                  ; address: 0x00466a

        btfss   SSPSTAT, BF, A                              ; reg: 0xfc7, bit: 0
        bra     label_585                                   ; dest: 0x00466a
        movf    SSPBUF, W, A                                ; reg: 0xfc9
        return  0x0

function_090:                                               ; address: 0x004672

        lfsr    0x2, 0x1f4
        lfsr    0x1, 0x01c
        movlw   0x07

label_586:                                                  ; address: 0x00467c

        movff   POSTINC2, POSTINC1                          ; reg1: 0xfde, reg2: 0xfe6
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     label_586                                   ; dest: 0x00467c
        movlw   0x1c
        call    function_080, 0x0                           ; dest: 0x0044b2
        movlw   0x1c
        call    function_080, 0x0                           ; dest: 0x0044b2
        movlw   0x1c
        goto    function_080                                ; dest: 0x0044b2

function_091:                                               ; address: 0x004696

        clrf    (Common_RAM + 26), A                        ; reg: 0x01a
        bra     label_588                                   ; dest: 0x0046a2

label_587:                                                  ; address: 0x00469a

        rcall   function_092                                ; dest: 0x0046aa
        call    function_111, 0x0                           ; dest: 0x004896
        incf    (Common_RAM + 26), F, A                     ; reg: 0x01a

label_588:                                                  ; address: 0x0046a2

        rcall   function_092                                ; dest: 0x0046aa
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        bra     label_587                                   ; dest: 0x00469a

function_092:                                               ; address: 0x0046aa

        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        addwf   (Common_RAM + 24), W, A                     ; reg: 0x018
        movwf   FSR2L, A                                    ; reg: 0xfd9
        movlw   0x00
        addwfc  (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   FSR2H, A                                    ; reg: 0xfda
        movf    INDF2, W, A                                 ; reg: 0xfdf
        return  0x0

function_093:                                               ; address: 0x0046ba

        movff   WREG, (Common_RAM + 7)                      ; reg1: 0xfe8, reg2: 0x007
        bsf     SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0

label_589:                                                  ; address: 0x0046c0

        btfsc   SSPCON2, SEN, A                             ; reg: 0xfc5, bit: 0
        bra     label_589                                   ; dest: 0x0046c0
        movlw   0xe2
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        call    function_056, 0x0                           ; dest: 0x003e68
        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        call    function_056, 0x0                           ; dest: 0x003e68
        bsf     SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2

label_590:                                                  ; address: 0x0046d8

        btfss   SSPCON2, PEN, A                             ; reg: 0xfc5, bit: 2
        return  0x0
        bra     label_590                                   ; dest: 0x0046d8

function_094:                                               ; address: 0x0046de

        movff   (Common_RAM + 7), (Common_RAM + 3)          ; reg1: 0x007, reg2: 0x003
        movff   (Common_RAM + 8), (Common_RAM + 4)          ; reg1: 0x008, reg2: 0x004
        call    function_110, 0x0                           ; dest: 0x004884
        xorwf   (Common_RAM + 9), W, A                      ; reg: 0x009
        bz      label_591
        movff   (Common_RAM + 7), (Common_RAM + 3)          ; reg1: 0x007, reg2: 0x003
        movff   (Common_RAM + 8), (Common_RAM + 4)          ; reg1: 0x008, reg2: 0x004
        movff   (Common_RAM + 9), (Common_RAM + 5)          ; reg1: 0x009, reg2: 0x005
        call    function_075, 0x0                           ; dest: 0x0043da

label_591:                                                  ; address: 0x0046fe

        return  0x0

function_095:                                               ; address: 0x004700

        decf    0x95, W, B                                  ; reg: 0x095
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_105, 0x0                           ; dest: 0x004828
        clrf    UCON, A                                     ; reg: 0xf6d
        movlw   0x15
        movwf   UCFG, A                                     ; reg: 0xf6f
        clrf    UIE, A                                      ; reg: 0xf69
        bsf     UCON, USBEN, A                              ; reg: 0xf6d, bit: 3
        call    function_063, 0x0                           ; dest: 0x0040d6
        movlw   0x01
        movlb   0x0
        movwf   0xcd, B                                     ; reg: 0x0cd
        clrf    0x95, B                                     ; reg: 0x095
        return  0x0

function_096:                                               ; address: 0x004720

        movff   UIE, 0x092                                  ; reg1: 0xf69
        movlw   0x04
        movwf   UIE, A                                      ; reg: 0xf69
        bcf     UIR, IDLEIF, A                              ; reg: 0xf68, bit: 4
        bsf     UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        bcf     PIR2, USBIF, A                              ; reg: 0xfa1, bit: 5
        bsf     PIE2, USBIE, A                              ; reg: 0xfa0, bit: 5
        call    function_129, 0x0                           ; dest: 0x00496a
        bcf     PIE2, USBIE, A                              ; reg: 0xfa0, bit: 5
        movlb   0x0
        movf    0x92, W, B                                  ; reg: 0x092
        iorwf   UIE, F, A                                   ; reg: 0xf69
        return  0x0

function_097:                                               ; address: 0x00473e

        clrf    (Common_RAM + 6), A                         ; reg: 0x006
        bra     label_593                                   ; dest: 0x004752

label_592:                                                  ; address: 0x004742

        movf    (Common_RAM + 6), W, A                      ; reg: 0x006
        addwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        movwf   FSR2L, A                                    ; reg: 0xfd9
        movlw   0x00
        addwfc  (Common_RAM + 4), W, A                      ; reg: 0x004
        movwf   FSR2H, A                                    ; reg: 0xfda
        clrf    INDF2, A                                    ; reg: 0xfdf
        incf    (Common_RAM + 6), F, A                      ; reg: 0x006

label_593:                                                  ; address: 0x004752

        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        subwf   (Common_RAM + 6), W, A                      ; reg: 0x006
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        bra     label_592                                   ; dest: 0x004742

function_098:                                               ; address: 0x00475c

        movlb   0x0
        decf    0x95, W, B                                  ; reg: 0x095
        bz      label_595
        btfss   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        bra     label_594                                   ; dest: 0x00476e
        btfss   UCON, USBEN, A                              ; reg: 0xf6d, bit: 3
        call    function_095, 0x0                           ; dest: 0x004700
        bra     label_595                                   ; dest: 0x004778

label_594:                                                  ; address: 0x00476e

        btfss   UCON, USBEN, A                              ; reg: 0xf6d, bit: 3
        bra     label_595                                   ; dest: 0x004778
        call    function_116, 0x0                           ; dest: 0x0048f0
        clrf    0x95, B                                     ; reg: 0x095

label_595:                                                  ; address: 0x004778

        return  0x0

function_099:                                               ; address: 0x00477a

        movlw   0x98
        movwf   T3CON, A                                    ; reg: 0xfb1
        movlw   0xf8
        movwf   TMR3H, A                                    ; reg: 0xfb3
        movlw   0x30
        movwf   TMR3L, A                                    ; reg: 0xfb2
        movff   (Common_RAM + 3), 0x08c                     ; reg1: 0x003
        movff   (Common_RAM + 4), 0x08d                     ; reg1: 0x004
        bcf     PIR2, TMR3IF, A                             ; reg: 0xfa1, bit: 1
        bsf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        bsf     PIE2, TMR3IE, A                             ; reg: 0xfa0, bit: 1
        retlw   0x30

function_100:                                               ; address: 0x004796

        movlb   0x0
        btfss   0x7e, 0x2, B                                ; reg: 0x07e
        bra     label_598                                   ; dest: 0x0047ac
        btfss   (Common_RAM + 94), 0x3, A                   ; reg: 0x05e
        bra     label_596                                   ; dest: 0x0047a6
        call    function_024, 0x0                           ; dest: 0x002d8c
        bra     label_597                                   ; dest: 0x0047aa

label_596:                                                  ; address: 0x0047a6

        call    function_051, 0x0                           ; dest: 0x003c0c

label_597:                                                  ; address: 0x0047aa

        bcf     0x7e, 0x2, B                                ; reg: 0x07e

label_598:                                                  ; address: 0x0047ac

        movlw   0x01
        goto    function_005                                ; dest: 0x0018ee

function_101:                                               ; address: 0x0047b2

        movff   WREG, (Common_RAM + 4)                      ; reg1: 0xfe8, reg2: 0x004
        movlw   0x3f
        andwf   SSPSTAT, F, A                               ; reg: 0xfc7
        clrf    SSPCON1, A                                  ; reg: 0xfc6
        clrf    SSPCON2, A                                  ; reg: 0xfc5
        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        iorwf   SSPCON1, F, A                               ; reg: 0xfc6
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        iorwf   SSPSTAT, F, A                               ; reg: 0xfc7
        bsf     TRISB, RB1, A                               ; reg: 0xf93, bit: 1
        bsf     TRISB, RB0, A                               ; reg: 0xf93, bit: 0
        bsf     SSPCON1, SSPEN, A                           ; reg: 0xfc6, bit: 5
        return  0x0

function_102:                                               ; address: 0x0047ce

        call    function_047, 0x0                           ; dest: 0x003a26
        call    function_006, 0x0                           ; dest: 0x001be6
        call    function_015, 0x0                           ; dest: 0x0027f0
        call    function_100, 0x0                           ; dest: 0x004796
        call    function_014, 0x0                           ; dest: 0x00265c
        goto    label_529                                   ; dest: 0x00416e
        addwfc  (Common_RAM + 45), W, A                     ; reg: 0x02d
        rrncf   (Common_RAM + 70), W, B                     ; reg: 0x046
        dcfsnz  (Common_RAM + 73), W, A                     ; reg: 0x049
        dw      0x0020                                      ; ' '
        subfwb  (Common_RAM + 70), F, B                     ; reg: 0x046
        subfwb  (Common_RAM + 95), W, B                     ; reg: 0x05f
        cpfsgt  UEP0, A                                     ; reg: 0xf70
        rrcf    Common_RAM, W, A                            ; reg: 0x000
        rrcf    (Common_RAM + 48), W, A                     ; reg: 0x030
        rrcf    (Common_RAM + 48), W, A                     ; reg: 0x030
        dw      0x0030                                      ; '0'

function_103:                                               ; address: 0x0047fc

        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x29
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x01
        btfss   (Common_RAM + 94), 0x1, A                   ; reg: 0x05e
        movlw   0x00
        goto    function_111                                ; dest: 0x004896

function_104:                                               ; address: 0x004812

        bra     label_600                                   ; dest: 0x00481e

label_599:                                                  ; address: 0x004814

        call    function_127, 0x0                           ; dest: 0x004962
        decf    (Common_RAM + 3), F, A                      ; reg: 0x003
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        decf    (Common_RAM + 4), F, A                      ; reg: 0x004

label_600:                                                  ; address: 0x00481e

        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        iorwf   (Common_RAM + 3), W, A                      ; reg: 0x003
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        bra     label_599                                   ; dest: 0x004814

function_105:                                               ; address: 0x004828

        bcf     UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        clrf    UCON, A                                     ; reg: 0xf6d
        movlw   0xff
        setf    (Common_RAM + 4), A                         ; reg: 0x004
        setf    (Common_RAM + 3), A                         ; reg: 0x003
        call    function_104, 0x0                           ; dest: 0x004812
        movlb   0x0
        clrf    0xcd, B                                     ; reg: 0x0cd
        return  0x0

function_106:                                               ; address: 0x00483c

        call    function_119, 0x0                           ; dest: 0x004924
        bcf     UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        bcf     UIE, ACTVIE, A                              ; reg: 0xf69, bit: 2
        bra     label_602                                   ; dest: 0x004848

label_601:                                                  ; address: 0x004846

        bcf     UIR, ACTVIF, A                              ; reg: 0xf68, bit: 2

label_602:                                                  ; address: 0x004848

        btfss   UIR, ACTVIF, A                              ; reg: 0xf68, bit: 2
        return  0x0
        bra     label_601                                   ; dest: 0x004846

function_107:                                               ; address: 0x00484e

        movlw   0xbf
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x18
        call    function_111, 0x0                           ; dest: 0x004896
        movlw   0x01
        goto    function_111                                ; dest: 0x004896

function_108:                                               ; address: 0x004860

        bra     label_604                                   ; dest: 0x004866

label_603:                                                  ; address: 0x004862

        call    function_087, 0x0                           ; dest: 0x0045fa

label_604:                                                  ; address: 0x004866

        call    function_109, 0x0                           ; dest: 0x004872
        iorlw   0x00
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        bra     label_603                                   ; dest: 0x004862

function_109:                                               ; address: 0x004872

        movlb   0x0
        movf    0xc7, W, B                                  ; reg: 0x0c7
        clrf    PRODL, A                                    ; reg: 0xff3
        cpfseq  0xc6, B                                     ; reg: 0x0c6
        incf    PRODL, F, A                                 ; reg: 0xff3
        movff   PRODL, (Common_RAM + 3)                     ; reg1: 0xff3, reg2: 0x003
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        return  0x0

function_110:                                               ; address: 0x004884

        movff   (Common_RAM + 3), EEADR                     ; reg1: 0x003, reg2: 0xfa9
        bcf     EECON1, CFGS, A                             ; reg: 0xfa6, bit: 6
        bcf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7
        bsf     EECON1, RD, A                               ; reg: 0xfa6, bit: 0
        dw      0xf000
        dw      0xf000
        movf    EEDATA, W, A                                ; reg: 0xfa8
        return  0x0

function_111:                                               ; address: 0x004896

        movff   WREG, (Common_RAM + 3)                      ; reg1: 0xfe8, reg2: 0x003

label_605:                                                  ; address: 0x00489a

        btfss   TXSTA, TRMT, A                              ; reg: 0xfac, bit: 1
        bra     label_605                                   ; dest: 0x00489a
        movff   (Common_RAM + 3), TXREG                     ; reg1: 0x003, reg2: 0xfad
        movf    (Common_RAM + 3), W, A                      ; reg: 0x003
        return  0x0

function_112:                                               ; address: 0x0048a6

        movlw   0xa4
        movwf   TMR0H, A                                    ; reg: 0xfd7
        movlw   0x71
        movwf   TMR0L, A                                    ; reg: 0xfd6
        bcf     INTCON, T0IF, A                             ; reg: 0xff2, bit: 2
        bsf     INTCON, T0IE, A                             ; reg: 0xff2, bit: 5
        bsf     T0CON, TMR0ON, A                            ; reg: 0xfd5, bit: 7
        retlw   0x71

function_113:                                               ; address: 0x0048b6

        movff   SSPCON2, (Common_RAM + 3)                   ; reg1: 0xfc5, reg2: 0x003
        movlw   0x1f
        andwf   (Common_RAM + 3), F, A                      ; reg: 0x003
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        btfsc   SSPSTAT, R, A                               ; reg: 0xfc7, bit: 2
        bra     function_113                                ; dest: 0x0048b6
        retlw   0x1f

label_606:                                                  ; address: 0x0048c6

        call    function_035, 0x0                           ; dest: 0x00355c

label_607:                                                  ; address: 0x0048ca

        call    function_026, 0x0                           ; dest: 0x002f4e
        call    function_102, 0x0                           ; dest: 0x0047ce
        bra     label_607                                   ; dest: 0x0048ca

function_114:                                               ; address: 0x0048d4

        clrf    INTCON, A                                   ; reg: 0xff2
        dw      0xf000
        dw      0xf000
        reset
        dw      0xf000
        dw      0xf000
        return  0x0

function_115:                                               ; address: 0x0048e2

        movlw   0x02
        call    function_072, 0x0                           ; dest: 0x004368
        bcf     LATA, LATA3, A                              ; reg: 0xf89, bit: 3
        bcf     LATA, LATA4, A                              ; reg: 0xf89, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        return  0x0

function_116:                                               ; address: 0x0048f0

        bcf     UCON, SUSPND, A                             ; reg: 0xf6d, bit: 1
        clrf    UCON, A                                     ; reg: 0xf6d
        movlb   0x0
        clrf    0xcd, B                                     ; reg: 0x0cd
        movlw   0x01
        movwf   0x95, B                                     ; reg: 0x095
        retlw   0x01

function_117:                                               ; address: 0x0048fe

        movff   WREG, (Common_RAM + 3)                      ; reg1: 0xfe8, reg2: 0x003
        decf    (Common_RAM + 3), W, A                      ; reg: 0x003
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        call    function_088, 0x0                           ; dest: 0x004624
        return  0x0

function_118:                                               ; address: 0x00490c

        btfss   T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        bra     label_608                                   ; dest: 0x004914
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        bra     label_609                                   ; dest: 0x004916

label_608:                                                  ; address: 0x004914

        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

label_609:                                                  ; address: 0x004916

        return  0x0

label_610:                                                  ; address: 0x004918

        btfsc   UCON, USBEN, A                              ; reg: 0xf6d, bit: 3
        call    function_105, 0x0                           ; dest: 0x004828
        clrf    0x95, B                                     ; reg: 0x095
        goto    function_098                                ; dest: 0x00475c

function_119:                                               ; address: 0x004924

        movlw   0x03
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 3), A                         ; reg: 0x003
        goto    label_600                                   ; dest: 0x00481e

function_120:                                               ; address: 0x00492e

        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x01
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        goto    function_079                                ; dest: 0x00447e

function_121:                                               ; address: 0x004938

        call    function_083, 0x0                           ; dest: 0x004546
        bcf     (Common_RAM + 94), 0x0, A                   ; reg: 0x05e
        clrf    0x98, B                                     ; reg: 0x098
        return  0x0

function_122:                                               ; address: 0x004942

        clrf    (Common_RAM + 4), A                         ; reg: 0x004
        movlw   0x02
        movwf   (Common_RAM + 3), A                         ; reg: 0x003
        goto    function_079                                ; dest: 0x00447e

function_123:                                               ; address: 0x00494c

        bcf     T3CON, TMR3ON, A                            ; reg: 0xfb1, bit: 0
        bcf     PIR2, TMR3IF, A                             ; reg: 0xfa1, bit: 1
        bcf     PIE2, TMR3IE, A                             ; reg: 0xfa0, bit: 1
        return  0x0

function_124:                                               ; address: 0x004954

        movlw   0x01
        goto    function_072                                ; dest: 0x004368

function_125:                                               ; address: 0x00495a

        goto    label_383                                   ; dest: 0x003194

function_126:                                               ; address: 0x00495e

        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        return  0x0

function_127:                                               ; address: 0x004962

        clrwdt
        return  0x0

function_128:                                               ; address: 0x004966

        bcf     SSPCON1, SSPEN, A                           ; reg: 0xfc6, bit: 5
        return  0x0

function_129:                                               ; address: 0x00496a

        return  0x0

function_130:                                               ; address: 0x00496c

        return  0x0

function_131:                                               ; address: 0x00496e

        return  0x0
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xc801
        clrwdt
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        swapf   (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        swapf   (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        swapf   (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        swapf   (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        incfsz  (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        incfsz  (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        incfsz  (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        incfsz  (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrncf   (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop

label_611:                                                  ; address: 0x005704

        nop
        nop
        rrncf   (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrncf   (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrncf   (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlncf   (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlncf   (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dw      0xc901
        clrwdt
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlncf   (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlncf   (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        infsnz  (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        infsnz  (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        infsnz  (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        infsnz  (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dcfsnz  (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dcfsnz  (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dcfsnz  (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dcfsnz  (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        movf    (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        movf    (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        movf    (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        movf    (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subfwb  (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dw      0xca01
        clrwdt
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subfwb  (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subfwb  (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subfwb  (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwfb  (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwfb  (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwfb  (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwfb  (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwf   (Common_RAM + 1), W, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwf   (Common_RAM + 1), W, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwf   (Common_RAM + 1), F, A                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        subwf   (Common_RAM + 1), F, B                      ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        cpfslt  (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        cpfslt  (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        cpfseq  (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        cpfseq  (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dw      0xcb01
        clrwdt
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        cpfsgt  (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        cpfsgt  (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        tstfsz  (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        tstfsz  (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        setf    (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        setf    (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        clrf    (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        clrf    (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        negf    (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        negf    (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        movwf   (Common_RAM + 1), B                         ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x0, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x0, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x1, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dw      0xcc01
        clrwdt
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x1, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x2, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x2, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x3, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x3, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x4, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x4, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x5, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x5, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x6, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x6, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        btg     (Common_RAM + 1), 0x7, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x0, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x0, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dw      0xcd01
        clrwdt
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x1, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x1, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x2, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x2, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x3, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x3, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x4, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x4, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x5, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x5, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x6, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x6, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bsf     (Common_RAM + 1), 0x7, B                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bcf     (Common_RAM + 1), 0x0, A                    ; reg: 0x001
        callw
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        bra     label_611                                   ; dest: 0x005704
        clrwdt
        nop
        movlb   0x0
        rrcf    (Common_RAM + 1), W, B                      ; reg: 0x001
        retfie  0x0
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrcf    (Common_RAM + 1), W, B                      ; reg: 0x001
        retfie  0x0
        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrcf    (Common_RAM + 1), F, A                      ; reg: 0x001
        retfie  0x0
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrcf    (Common_RAM + 1), F, A                      ; reg: 0x001
        retfie  0x0
        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrcf    (Common_RAM + 1), F, B                      ; reg: 0x001
        retfie  0x0
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rrcf    (Common_RAM + 1), F, B                      ; reg: 0x001
        retfie  0x0
        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), W, A                      ; reg: 0x001
        retfie  0x0
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), W, A                      ; reg: 0x001
        retfie  0x0
        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), W, B                      ; reg: 0x001
        retfie  0x0
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), W, B                      ; reg: 0x001
        retfie  0x0
        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), F, A                      ; reg: 0x001
        retfie  0x0
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rlcf    (Common_RAM + 1), F, A                      ; reg: 0x001
        retfie  0x0
        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff

;===============================================================================
; EEDATA area

        ; eeprom

        org     __EEPROM_START                              ; address: 0xf00000

        db      0xff
        db      0xff
        db      0xff
        db      0xa0
        db      0x01
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x01
        db      0x01
        db      0x01
        db      0x03
        db      0x04
        db      0x01
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x01
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0x03
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0x02
        db      0x03
        db      0x30                                        ; '0'
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0x02

        end

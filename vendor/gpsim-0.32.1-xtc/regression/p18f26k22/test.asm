    ;; Definitions for the PIC18F14K22 version
        list    p=18f14k22
        include <p18f14k22.inc>


        CONFIG FOSC = IRC, PLLEN = ON, PCLKEN = OFF, FCMEN = OFF, IESO = OFF
        CONFIG PWRTEN = OFF, BOREN = OFF
        CONFIG WDTEN = ON, WDTPS = 128
        CONFIG HFOFST = ON, MCLRE = OFF
        CONFIG STVREN = OFF, LVP = OFF, BBSIZ = OFF, XINST = OFF, DEBUG = OFF
        CONFIG CP0 = OFF, CP1 = OFF
        CONFIG CPB = OFF, CPD = OFF
        CONFIG WRT0 = OFF, WRT1 = OFF
        CONFIG WRTC = OFF, WRTB = OFF, WRTD = OFF
        CONFIG EBTR0 = OFF, EBTR1 = OFF
        CONFIG EBTRB = OFF

    ;; Reset and interrupt vectors
    org 0x00
    goto    startup
    org 0x08
    retfie
    org 0x18
    retfie

    ;; Variables.
    cblock  0x00
        temp
    endc

    ;; *******************************************************************************
    ;; ******************************************************  Initialization  *******
    ;; *******************************************************************************

startup
    movlb   0x00                    ; Set bank 0 active.
    movlw   0xff
    movwf   temp
    goto    startup
    end

        include <p10f202.inc>           ; processor specific variable definitions
        include <coff.inc>  
    LIST    p=10f202
    __CONFIG _MCLRE_OFF & _CP_OFF & _WDT_OFF

GPR_DATA                UDATA
temp            RES     1
;----------------------------------------------------------------------
MAIN    CODE

    movlw	0
    tris	GPIO
    option
loop
    xorlw	0x4
    movwf	GPIO

    bsf		GPIO,1
    bsf		GPIO,0
    goto 	loop
 END

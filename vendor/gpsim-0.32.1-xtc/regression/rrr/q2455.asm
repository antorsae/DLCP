list P=PIC18f2455
#include <p18f2455.inc>

 ORG 0

MAIN_LOOP:
    movlw 0x09
    addlw 0x01
    movlw 0
    addwf PCL,F
    bsf   PCL,1
    clrf  PCL
    nop
    goto MAIN_LOOP

 END

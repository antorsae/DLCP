list P=PIC16F505
#include <p16f505.inc>

 ORG 0

MAIN_LOOP:
    movlw 0
    addwf PCL,F
    bsf   PCL,0
    clrf  PCL
    nop
    goto MAIN_LOOP

 END

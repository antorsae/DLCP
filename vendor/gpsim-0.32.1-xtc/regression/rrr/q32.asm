list P=PIC12F508
#include <p12f508.inc>

 ORG 0

MAIN_LOOP:
    movlw 0
    addwf PCL,F
    bsf   PCL,0
    clrf  PCL
    nop
    goto MAIN_LOOP

 END

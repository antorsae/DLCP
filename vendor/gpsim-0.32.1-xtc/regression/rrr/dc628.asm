list P=PIC16f628a
#include <p16f628a.inc>
 include <coff.inc>

 ORG 0

MAIN_LOOP:
    movlw 0x09
    addlw 0x01
    btfsc STATUS,DC
    goto  BAD
    addlw 0x06
    btfsc STATUS,DC
    goto  OK
BAD:
  .assert "\"DC set W -> 0x0a\""
    nop
OK:
  .assert "\"Test Passed\""
    nop
    goto MAIN_LOOP

 END

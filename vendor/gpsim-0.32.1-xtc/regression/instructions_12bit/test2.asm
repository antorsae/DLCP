        include <p10f222.inc>           ; processor specific variable definitions
        include <coff.inc>  
    LIST    p=10f222
;    __CONFIG _MCLRE_OFF & _CP_OFF & _WDT_OFF

    org 0
    CALL    ONE
    NOP
    GOTO    $

ONE:
	CALL TWO
	nop
	RETLW 0
TWO:
	call three
	nop
	RETLW 0

three:
	return
 END

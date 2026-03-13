
   ;;  16F628 tests
   ;;
   ;; This regression test exercises the 16f628.  
   ;; 
   ;;  Tests performed:
   ;;
   ;;  1) Verify Comparators can be disabled and that
   ;;     PORTA can work as a digital I/O port.


   list p=16f88

include "p16f88.inc"
include <coff.inc>

.command macro x
  .direct "C", x
  endm

   __CONFIG  _CONFIG1, _CP_OFF & _WDT_OFF & _INTRC_IO & _MCLR_ON
   __CONFIG  _CONFIG2, _IESO_OFF & _FCMEN_OFF

   cblock 0x20

        temp

   endc



	ORG	0

  .sim "p16f88.BreakOnReset = false"
  .sim "break c 0x10000"

	btfss	STATUS,NOT_TO
	goto	wdt_reset

        clrf    temp     ;
LOOP2   goto	$+1
	goto	$+1
	goto	$+1
	decfsz  temp, F   
        goto    LOOP2  

done:
  .assert "\"*** PASSED p16f88 no WDT test\""
    nop

	GOTO	$


wdt_reset:
    .assert "\"*** FAILED p16f88 unexpected WDT triggered\""
    nop
    goto $
  end

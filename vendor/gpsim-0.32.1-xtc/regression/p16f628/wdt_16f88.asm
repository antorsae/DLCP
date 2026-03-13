
   ;;  16F88 WDT tests
   ;;
   ;; This regression test, tests that the WDT is active
   ;;
   ;;     The test assumes that the clock speed is about 31,250 Hz
   ;; 


   list p=16f88

include "p16f88.inc"
include <coff.inc>

.command macro x
  .direct "C", x
  endm

;   __CONFIG  _CONFIG1, _CP_OFF & _WDT_ON & _INTRC_IO & _MCLR_ON
;   __CONFIG  _CONFIG2, _IESO_OFF & _FCMEN_OFF

   cblock 0x20

        temp
	phase

   endc

	ORG	0

  .sim "p16f88.BreakOnReset = false"
  .sim "break c 0x10000"
  .sim "p16f88.frequency=32150"

	btfss	STATUS,NOT_TO
	goto	wdt_reset

	clrf	phase

        clrf    temp     ;
LOOP1   clrwdt
	goto    $+1
        goto    $+1
        goto    $+1
        decfsz  temp, F
        goto    LOOP1

	incf	phase, F
        clrf    temp     ;
LOOP2   goto    $+1
        goto    $+1
        goto    $+1
        decfsz  temp, F
        goto    LOOP2


FAILED:
  .assert "\"*** FAILED p16f88 no WDT\""
	nop
	goto	$


wdt_reset:

    btfss phase,0
    goto FAILED

    .assert "\"*** PASSED p16f88 WDT triggered\""
    nop
    goto $
  end

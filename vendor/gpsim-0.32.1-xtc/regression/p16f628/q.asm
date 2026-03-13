
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

CONFIG_WORD	EQU	_CP_OFF & _WDT_ON & _INTRC_IO & _MCLR_OFF

        __CONFIG  _CONFIG1, CONFIG_WORD
	 __CONFIG    _CONFIG2, _IESO_OFF & _FCMEN_OFF

   cblock 0x20

	failures

   endc


	ORG	0

	btfss	STATUS,NOT_TO
	goto	wdt_reset

	goto $

FAILED:
	nop
done:
    nop

	GOTO	$


wdt_reset:
    nop
    goto $
  end

list p=16f628
include "p16f628.inc"
	__CONFIG _CP_OFF & _DATA_CP_OFF & _BODEN_ON & _MCLRE_OFF & _PWRTE_ON & _WDT_OFF & _INTRC_OSC_NOCLKOUT & _LVP_OFF

	org 0
	goto main

main:
	banksel T1CON

; Disable timer 1
	bcf T1CON, TMR1ON

	movlw 0x34
	movwf TMR1L
	movlw 0x12
	movwf TMR1H

; counter is set to 0x1234 - works

; Enable timer 1
	bsf T1CON, TMR1ON

; oops - counter is 0x1 now
; setting TMR1ON must have reset it to 0x0!

	goto $+0
end


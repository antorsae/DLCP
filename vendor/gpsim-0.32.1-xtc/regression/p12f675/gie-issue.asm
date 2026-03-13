	ERRORLEVEL	-302	; Remove message about using proper bank
	LIST		P=PIC12F683
	include		<p12f683.inc>
	radix		dec
	__CONFIG	_FCMEN_OFF & _IESO_OFF & _BOD_OFF & _CPD_OFF & _CP_OFF & _MCLRE_OFF & _PWRTE_OFF & _WDT_OFF & _INTOSCIO


	ORG	0
	goto	Init

	ORG	4
ISR	movf	INTCON, W	; Expected 0x24, reads as 0xa4
	movlw	0xa4		; Set T0IE, T0IF, and GIE
	movwf	INTCON		; Expected jump to ISR above
	movlw	0x20		; Set T0IE, clear T0IF and GIE
	movwf	INTCON
	movlw	0xf0		; Reduce time until next interrupt
	movwf	TMR0		;   should occur
	retfie

Init	bsf	STATUS, RP0	; BANK 1
	movlw	0xdf		; Enable internal TMR0 without prescaler
	movwf	OPTION_REG
	bcf	STATUS, RP0	; BANK 0
	movlw	0xa0		; Enable TMR0 interrupt
	movwf	INTCON
	movlw	0xf0		; Reduce time until interrupt happens
	movwf	TMR0
X	movf	INTCON, W	; Expected 0xa0, reads as 0x20 after
	goto	X		;   interrupt has occured once

	END

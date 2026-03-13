	list	p=18f25k20
	include <p18f25k20.inc>
	include <coff.inc>

	errorlevel -302

MAIN	CODE
start:
	.sim "node nra1"
	.sim "attach nra1 porta1"
	.sim "node nra2"
	.sim "attach nra2 porta2"
	.sim "node nra3"
	.sim "attach nra3 porta3"
	.sim "node nra4"
	.sim "attach nra4 porta4"
	.sim "node nrc0"
	.sim "attach nrc0 portc0"
	.sim "node nrc5"
	.sim "attach nrc5 portc5"
	.sim "node nrc6"
	.sim "attach nrc6 portc6"
	.sim "node nrc7"
	.sim "attach nrc7 portc7"

	movlw	0x12
	movwf	CM2CON0, ACCESS
	movf	CM2CON0, W, ACCESS
	xorlw	0x52
	bnz	BAD

	movlw	0x34
	movwf	CM1CON0, ACCESS
	movf	CM1CON0, W, ACCESS
	xorlw	0x74
	bnz	BAD

	movlw	0x56
	movwf	IOCB, ACCESS
	movf	IOCB, W, ACCESS
	xorlw	0x56
	bnz	BAD

	movlw	0x08
	movwf	ANSEL, ACCESS
	movf	ANSEL, W, ACCESS
	xorlw	0x08
	bnz	BAD

	movlw	0x0F
	movwf	ANSELH, ACCESS
	movf	ANSELH, W, ACCESS
	xorlw	0x0F
	bnz	BAD

	movlw	0x9A
	movwf	SPBRGH, ACCESS
	movf	SPBRGH, W, ACCESS
	xorlw	0x9A
	bnz	BAD

	movlw	0x4C
	movwf	BAUDCON, ACCESS
	movf	BAUDCON, W, ACCESS
	xorlw	0x4C
	bnz	BAD

	movlw	0xA5
	movwf	ADCON2, ACCESS
	movf	ADCON2, W, ACCESS
	xorlw	0xA5
	bnz	BAD

	.assert "'*** PASSED p18f25k20 sfr map test'"
	bra	$

BAD:
	.assert "'*** FAILED p18f25k20 sfr map test'"
	bra	$

	end

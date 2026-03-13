
;********************************************************************************

;Set up the assembler options (Chip type, clock source, other bits and pieces)
 LIST p=16F627A, r=DEC
#include <P16F627A.inc>
 __CONFIG _HS_OSC & _MCLRE_OFF & _LVP_OFF & _WDT_OFF

;********************************************************************************

;Vectors
	ORG	0
	goto	PROGRAMSTART
	ORG	4
	retfie

;********************************************************************************

;Start of program memory page 0
	ORG	5
PROGRAMSTART
;Initialisation routines
	movlw	7
	movwf	CMCON
	clrf	PORTA
	clrf	PORTB
	movlw	125
	banksel	PR2
	movwf	PR2
	banksel	T2CON
	movlw	6
	movwf	T2CON
	movlw	127
	movwf	CCPR1L
	movlw	12
	movwf	CCP1CON
	banksel	TRISB
	bcf	TRISB,3
Loop_1
	banksel	T2CON
	bcf	T2CON,T2CKPS1
	bsf	T2CON,T2CKPS1
	return
	goto	Loop_1

PROGRAMEND
	sleep
	goto	PROGRAMEND

 END

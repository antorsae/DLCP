	RADIX	DEC
	list    p=16f1825
#include <p16f1825.inc>
#include <coff.inc> 
; gpsim command
.command macro x
  .direct "C", x
  endm

	CONFIG	WDTE=OFF 
	CONFIG	PWRTE=ON 
	CONFIG	MCLRE=ON 
	CONFIG	CP=OFF
	CONFIG	CPD=OFF
	CONFIG	BOREN=OFF
	CONFIG	IESO=OFF
	CONFIG	FCMEN=OFF
	CONFIG	FOSC=XT
	CONFIG	STVREN=ON

	
RESET_VECTOR  CODE    0x000 
	GOTO	MAININIT
 .sim "symbol cycleCounter=0"

INT_VECTOR   CODE    0x004
	GOTO	$

;----------------------------------------------------------------------
;   ******************* MAIN CODE START LOCATION  ******************
;----------------------------------------------------------------------
MAIN    CODE

MAININIT:
;
; Timer4 setup
;
	BANKSEL	T2CON
	movlw	20
	movwf	PR2
;	clrf	PR2
	MOVLW	1<<TMR2ON|1<<T2OUTPS3|1<<T2OUTPS2|1<<T2OUTPS1|1<<T2OUTPS0|1<<T2CKPS1|1<<T2CKPS0
  .command "cycleCounter = cycles" 
	nop
	MOVWF	T2CON		; store timer2 config data
	btfss   TMR2,1
	goto	$-1

	movlw	0x20
;	movwf   TMR2
	clrf	TMR2
	BANKSEL PIR1
	bcf	PIR1,TMR2IF
	btfss	PIR1,TMR2IF
	goto	$-1
   .command  "cycleCounter = cycles - cycleCounter" 
	nop
   .assert "(cycleCounter >= 1024) && (cycleCounter <= 1030), '*** FAILED 16f1825 T2 count'"
	nop
	BANKSEL T2CON
	bcf	T2CON,TMR2ON
	NOP
	BANKSEL	T4CON
	MOVLW	1<<TMR4ON|1<<T4OUTPS3|1<<T4OUTPS2|1<<T4OUTPS1|1<<T4OUTPS0|1<<T4CKPS1|1<<T4CKPS0
  .command "cycleCounter = cycles" 
	nop
	MOVWF	T4CON		; store timer4 config data
	BANKSEL PIR3
	bcf	PIR3,TMR4IF
	btfss	PIR3,TMR4IF
	goto	$-1
   .command  "cycleCounter = cycles - cycleCounter" 
	nop
   .assert "(cycleCounter >= 262144) && (cycleCounter <= 262150), '*** FAILED 16f1825 T4 count'"
	nop
	BANKSEL T4CON
	bcf	T4CON,TMR4ON
	NOP
	BANKSEL	T6CON
;	postscale = 8, prescale = 64 PR6 = 255 so cycles  8 * 64 *256 = 131072
	MOVLW	1<<TMR6ON|1<<T6OUTPS2|1<<T6OUTPS1|1<<T6OUTPS0|1<<T6CKPS1|1<<T6CKPS0
  .command "cycleCounter = cycles" 
	nop
	MOVWF	T6CON		; store timer6 config data
	BANKSEL PIR3
	bcf	PIR3,TMR6IF
	btfss	PIR3,TMR6IF
	goto	$-1
   .command  "cycleCounter = cycles - cycleCounter" 
	nop
   .assert "(cycleCounter >= 131072) && (cycleCounter <= 131076), '*** FAILED 16f1825 T6 count'"
	nop
	nop
  .assert "'debug'"
	NOP
	END

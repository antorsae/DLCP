	; 18f2455 gpsim regression test
	;
	; The purpose of this test is to verify the stack
	; underflow and overflow conditions with STVREN off

	list	p=18f2455
        include <p18f2455.inc>
        include <coff.inc>

    CONFIG STVREN=OFF, WDT=ON

        radix   dec

; Printf Command
.command macro x
  .direct "C", x
  endm

GPR_DATA  UDATA
ResetSequence RES 1
optionShadow  RES 1
w_temp RES 1
status_temp RES 1
temp1 RES 1

  GLOBAL optionShadow, ResetSequence


    ; Define the reset conditions to be checked.

eRSTSequence_PowerOnReset	equ	1
eRSTSequence_AwakeMCLR		equ	2
eRSTSequence_AwakeWDT		equ	3
eRSTSequence_AwakeIO		equ	4
eRSTSequence_WDTTimeOut		equ	5

;----------------------------------------------------------------------
;   ********************* STARTUP LOCATION  ***************************
;----------------------------------------------------------------------
START  CODE    0x000                    ; 


;############################################################
;# Create a stimulus to simulate a switch
;


RESET_VECTOR  CODE    0x000              ; processor reset vector
  .assert "(trisa&0x1f)==0x1f, \"*** FAILED 18f2455 reset bad TRISA\""
  .assert "(trisb&0xff)==0xff, \"*** FAILED 18f2455 reset bad TRISB\""

        movlw  high  start               ; load upper byte of 'start' label
        movwf  PCLATH                    ; initialize PCLATH
        goto   start                     ; go to beginning of program




;------------------------------------------------------------------------
;
;  Interrupt Vector
;
;------------------------------------------------------------------------

INT_VECTOR   CODE    0x008               ; interrupt vector location

        movwf   w_temp
        swapf   STATUS,W
        movwf   status_temp

                
exit_int:               

        swapf   status_temp,w
        movwf   STATUS
        swapf   w_temp,f
        swapf   w_temp,w
        retfie





bSWITCH equ 0

;----------------------------------------------------------------------
;   ******************* MAIN CODE START LOCATION  ******************
;----------------------------------------------------------------------
MAIN    CODE 0x100
start
   	btfsc	STKPTR,STKUNF	; Stack undeflow has occured
	goto	test_overflow  
	btfsc   STKPTR,STKFUL	; Stack overflow reset has occured
	goto	finish

	return  ; this should cause underflow and go to pc=0
   .assert "\"***FAILED \""
	nop

test_overflow
	bcf	STKPTR,STKUNF
	clrf	temp1
   	call rrr
finish
   .assert "\"TEST passed\""
	nop
rrr:
	incf	temp1,F
	movf	STKPTR,W
	btfss   STKPTR,STKFUL	; Stack overflow has occured
	rcall rrr
	return

	end

	; 18f2455 gpsim regression test
	;
	; The purpose of this test is to verify that the 'C509
	; is implemented correctly. Here's a list of specific things
	; tested:	
	;
	; 1) Reset conditions
	; 2) WDT
	; 3) Sleep
	; 4) Wakeup on PIN change.

	list	p=18f2455
        include <p18f2455.inc>
        include <coff.inc>

  __CONFIG  _CONFIG2H,  _WDT_ON_2H
    CONFIG STRVEN=OFF

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

check_rbi:
        btfsc   INTCON,RBIF
         btfss  INTCON,RBIE
          goto  check_int

;        bsf     temp5,1         ;Set a flag to indicate rb4-7 int occured
        bcf     INTCON,RBIF
	movf	PORTB,w
        
check_int:
        btfsc   INTCON,INT0IF
         btfss  INTCON,INT0IE
          goto  check_t0

;        bsf     temp5,0         ;Set a flag to indicate rb0 int occured
        bcf     INTCON,INT0IF

check_t0:
        btfsc   INTCON,T0IF
         btfss  INTCON,T0IE
          goto  exit_int

    ;; tmr0 has rolled over
        
        bcf     INTCON,T0IF     ; Clear the pending interrupt
        bsf     temp1,0         ; Set a flag to indicate rollover
                
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

   return
   call rrr
rrr:
	call rrr
	return

	end

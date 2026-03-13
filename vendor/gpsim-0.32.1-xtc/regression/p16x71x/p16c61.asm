;
; 
; Copyright (c) 2013 Roy Rankin
;
; This file is part of the gpsim regression tests
; 
; This library is free software; you can redistribute it and/or
; modify it under the terms of the GNU Lesser General Public
; License as published by the Free Software Foundation; either
; version 2.1 of the License, or (at your option) any later version.
; 
; This library is distributed in the hope that it will be useful,
; but WITHOUT ANY WARRANTY; without even the implied warranty of
; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
; Lesser General Public License for more details.
; 
; You should have received a copy of the GNU Lesser General Public
; License along with this library; if not, see 
; <http://www.gnu.org/licenses/lgpl-2.1.html>.


        ;; The purpose of this program is to test gpsim's ability to 
        ;; simulate a pic 16F61.
        ;; Specifically, basic port operation, eerom, interrupts,
	;; a2d, dac, SR latch, capacitor sense, and enhanced instructions


	list    p=16c61                ; list directive to define processor
	include <p16c61.inc>           ; processor specific variable definitions
        include <coff.inc>              ; Grab some useful macros

;        __CONFIG _CONFIG1, _CP_OFF &  _FOSC_LP & _PWRTE_ON &  _BOREN_OFF 

;------------------------------------------------------------------------
; gpsim command
.command macro x
  .direct "C", x
  endm

TSEN  EQU H'0005'
TSRNG EQU H'0004'

;----------------------------------------------------------------------
GPR_DATA                UDATA
cmif_cnt	RES	1
tmr0_cnt	RES	1
tmr1_cnt	RES	1
eerom_cnt	RES	1
adr_cnt		RES	1
data_cnt	RES	1
inte_cnt	RES	1
iocaf_val	RES	1
w_temp		RES	1
status_temp		RES	1

  GLOBAL iocaf_val

;----------------------------------------------------------------------
;   ********************* RESET VECTOR LOCATION  ********************
;----------------------------------------------------------------------
RESET_VECTOR  CODE    0x000              ; processor reset vector
        goto   start                     ; go to beginning of program



;------------------------------------------------------------------------
;
;  Interrupt Vector
;
;------------------------------------------------------------------------
                                                                                
INT_VECTOR   CODE    0x004               ; interrupt vector location
	; many of the core registers now saved and restored automatically
                                                                                
        movwf   w_temp
        swapf   STATUS,W
        movwf   status_temp

  	btfsc	INTCON,T0IF
	    goto tmr0_int


	nop


; Interrupt from TMR0
tmr0_int
	incf	tmr0_cnt,F
	bcf 	INTCON,T0IF
	goto	exit_int



exit_int:
                                                                                
        retfie
                                                                                

;----------------------------------------------------------------------
;   ******************* MAIN CODE START LOCATION  ******************
;----------------------------------------------------------------------
MAIN    CODE
start
	;set clock to 16 Mhz


;	;
	; test pins in analog mode return 0 on register read
	BANKSEL TRISA
	clrf	STATUS
	clrf	TRISA
	nop
	BANKSEL PORTA
	movlw	0xff
	movwf	PORTA
	nop
	movf	PORTA,W

;
; test PORTA works as expected
;
	clrf	PORTA
	BANKSEL TRISA
	movlw	0x38
	movwf	TRISA		;PORTA 0,1,2 output 3,4,5 input

	nop
	movlw	0x07
	movwf	PORTA		; drive 0,1,2  bits high
	bsf	PORTB,7
	nop
	BANKSEL TRISA
	movlw	0x07
	movwf	TRISA  	; PORTA 3, 4, 5 output 0,1,2 input
	BANKSEL PORTA
	nop
	movlw	0x38
	movwf	PORTA		; drive output bits high
	nop

	call test_int
	goto	$




test_tmr0:
	return
	





test_int:
	BANKSEL TRISA
	bsf     TRISA,2
        bcf     TRISA,5
	BANKSEL PORTA
	clrf	PORTA

	BANKSEL OPTION_REG
	bsf 	OPTION_REG,INTEDG
	BANKSEL INTCON
	movlw	0x7f
	movwf	INTCON
	nop
	clrf	INTCON
        bsf     INTCON,GIE      ;Global interrupts

 	BANKSEL PORTA

        clrf    inte_cnt
        bsf     PORTA,5          ; make a rising edge
        nop
        movf    inte_cnt,w
        nop
	nop
        clrf    inte_cnt
        bcf     PORTA,5          ; make a falling edge
        nop
        movf    inte_cnt,w
        nop


        return


 	org 0x200
rrDATA
	dw 0x01, 0x02, 0x03
  end

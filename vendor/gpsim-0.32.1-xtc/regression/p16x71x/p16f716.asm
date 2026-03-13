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
        ;; simulate a pic 16F716.
        ;; Specifically, basic port operation, eerom, interrupts,
	;; a2d, dac, SR latch, capacitor sense, and enhanced instructions


	list    p=16f716                ; list directive to define processor
	include <p16f716.inc>           ; processor specific variable definitions
        include <coff.inc>              ; Grab some useful macros

        __CONFIG _CONFIG, _CP_OFF & _WDTE_ON &  _FOSC_LP & _PWRTE_ON &  _BOREN_OFF 

;------------------------------------------------------------------------
; gpsim command
.command macro x
  .direct "C", x
  endm

TSEN  EQU H'0005'
TSRNG EQU H'0004'

;----------------------------------------------------------------------
GPR_DATA                UDATA_SHR
cmif_cnt	RES	1
tmr0_cnt	RES	1
tmr1_cnt	RES	1
bioc_cnt  	RES	1
breg    	RES	1
adr_cnt		RES	1
data_cnt	RES	1
inte_cnt 	RES	1
ccp1_cnt 	RES	1
w_temp		RES	1
status_temp	RES	1

  GLOBAL ccp1_cnt, bioc_cnt, inte_cnt

;----------------------------------------------------------------------
;   ********************* RESET VECTOR LOCATION  ********************
;----------------------------------------------------------------------
RESET_VECTOR  CODE    0x000              ; processor reset vector
        goto   start                     ; go to beginning of program


  .sim "module library libgpsim_modules"
  ; Use a pullup resistor as a voltage source
  .sim "module load pullup V1"
  .sim "V1.resistance = 10000.0"
  .sim "V1.capacitance = 20e-12"
  .sim "V1.voltage=1.0"
  .sim "V1.xpos = 84"
  .sim "V1.ypos = 252"

  ; Vref for A/D
  .sim "module load pullup V2"
  .sim "V2.capacitance = 0"
  .sim "V2.resistance = 10000"
  .sim "V2.voltage = 4"
  .sim "V2.xpos = 252"
  .sim "V2.ypos = 48"


  ; pullup for porta4
  .sim "module load pullup PU1"
  .sim "PU1.capacitance = 0"
  .sim "PU1.resistance = 10000"
  .sim "PU1.voltage = 5"
  .sim "PU1.xpos = 260"
  .sim "PU1.ypos = 120"


  .sim "node n1"
  .sim "attach n1 porta0 porta3 V2.pin"
  .sim "node n2"
  .sim "attach n2 porta1 porta4 PU1.pin"
  .sim "node n3"
  .sim "attach n3 portb3 portb4"
  .sim "node n4"
  .sim "attach n4 portb0 V1.pin porta2"

  .sim "p16f716.xpos = 72"
  .sim "p16f716.ypos = 72"



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
  	btfsc	INTCON,INTF
	    goto b0_int
  	btfsc	INTCON,RBIF
	    goto rb_int
	btfsc	PIR1,CCP1IF
	    goto ccp1_int


	.assert "\"***FAILED p16f716 unexpected interrupt\""
	nop


; Interrupt from TMR0
tmr0_int
	incf	tmr0_cnt,F
	bcf 	INTCON,T0IF
	goto	exit_int

; Interrupt for B0 change
b0_int
	movf	PORTB,W
	movwf	breg
	incf	inte_cnt,F
	bcf	INTCON,INTF
	goto	exit_int

; Intterupt from B4-7 pin change
rb_int
	movf	PORTB,W
	movwf	breg
	incf	bioc_cnt,F
	bcf	INTCON,RBIF
	goto	exit_int

ccp1_int
	incf	ccp1_cnt,F
	bcf	PIR1,CCP1IF
	goto	exit_int

exit_int:
        swapf   status_temp,w
        movwf   STATUS
        swapf   w_temp,f
        swapf   w_temp,w
        retfie
                                                                                

;----------------------------------------------------------------------
;   ******************* MAIN CODE START LOCATION  ******************
;----------------------------------------------------------------------
MAIN    CODE
start
	;set clock to 16 Mhz

	call test_capture
	call  test_pir_pie_bits
	call  test_porta
	call test_int
	call test_a2d

	nop
  .assert  "\"*** PASSED 16f716 Functionality\""
	nop
	goto	$

test_capture
	clrf	ccp1_cnt
	clrf	INTCON
	BANKSEL PIE1
	movlw	(1<<CCP1IF)
	movwf	PIE1
	BANKSEL TRISB
	bcf	TRISB,4
	bsf	TRISB,3
	BANKSEL T1CON
	movlw	0x30	; prescale 1/8
	movwf	T1CON
	movwf	TMR1H
	movwf	TMR1L
	bsf	T1CON,TMR1ON	; start t1
	movlw	0x04	; capture every falling edge
	movwf	CCP1CON
	clrf	CCPR1H
	clrf	CCPR1L
	bsf	PORTB,4
	bcf	PORTB,4
  .assert "ccpr1l == tmr1l && ccpr1h == tmr1h, \"*** FAILED 16f716  ccp capture\""
	nop
        movlw	(1<<GIE) | (1<<PEIE)
	movwf	INTCON
  .assert "ccp1_cnt == 1, \"*** FAILED 16f716 CCP1 interrupt\""
	nop
	return

test_porta
;	;
	; test pins in analog mode return 0 on register read
	BANKSEL TRISA
	clrf	TRISA
   .assert "trisa == 0x00, \"*** FAILED 16f716  TRISA not clear \""
	nop
	BANKSEL PORTA
	movlw	0xff
	movwf	PORTA
   .assert "porta == 0x10, \"*** FAILED 16f716  analog bits read 0\""
	nop
	movf	PORTA,W

; set porta to digital
	BANKSEL ADCON1
	movlw	0x06
	movwf	ADCON1

   .assert "porta == 0x1f, \"*** FAILED 16f716  digital bits read 1\""
	nop

	BANKSEL PORTA

;
; test PORTA works as expected
;
	clrf	PORTA
	BANKSEL TRISA
	movlw	0x38
	movwf	TRISA		;PORTA 0,1,2 output 3,4 input

	BANKSEL PORTA
  .assert "porta == 0x00, \"PORTA = 0x00\""
	nop
	movlw	0x07
	movwf	PORTA		; drive 0,1,2  bits high
	bsf	PORTB,7
  .assert "porta == 0x1f, \"PORTA = 0x1f\""
	nop
	clrf	PORTB
	BANKSEL TRISA
	movlw	0x07
	movwf	TRISA  	; PORTA 3, 4, 5 output 0,1,2 input
	clrf	TRISB
	BANKSEL PORTA
  .assert "porta == 0x00, \"PORTA = 0x00 low drive 3,4,5\""
	nop
	movlw	0x38
	movwf	PORTA		; drive output bits high
	bsf	PORTB,0
  .assert "porta == 0x1f, \"PORTA = 0x1f drive 3,4,5\""
	nop
	return


test_pir_pie_bits:
	clrf	INTCON
	BANKSEL PIR1
	movlw	0xff
	movwf	PIR1
   .assert "pir1 == 0x47, \"*** FAILED 16f716 PIR1 write test\""
	nop
	clrf	PIR1

	BANKSEL	PIE1
	movwf	PIE1
   .assert "PIE1 == 0x47, \"*** FAILED 16f716 PIE1 write test\""
	nop
	clrf	PIE1
	return

test_a2d
	BANKSEL ADCON1      
	movlw   0x01		; analog pins a3 = Vref
	movwf   ADCON1		
	movlw   0xff
	movwf	TRISA
	movwf	TRISB
	BANKSEL ADCON0      	;
	; Fosc/8,  AN2, A/D on
	movlw   (1<<ADCS1)| (1<<CHS1)|(1<<ADON)	
	movwf   ADCON0      	
	call	a2dConvert
   .assert "adres == 0x40 , \"*** FAILED 16f716 A2D AN2=1V Vref=4V\""
	nop
	BANKSEL	ADCON1
	clrf	ADCON1		; all analog channels, Vref=Vdd
	BANKSEL ADCON0
	call	a2dConvert
   .assert "adres == 0x33 , \"*** FAILED 16f716 A2D AN2=1V Vref=5V\""
	nop

	return

;
;	Start A2D conversion and wait for results
;
a2dConvert
	bsf 	ADCON0,GO
	btfsc	ADCON0,GO
	goto	$-1
	movf	ADRES,W
	return


test_tmr0:
	return
	





test_int:
	BANKSEL TRISA
	bsf     TRISB,0
        bcf     TRISA,2
	BANKSEL PORTA
	clrf	PORTA

	BANKSEL OPTION_REG
	bsf 	OPTION_REG,INTEDG
	BANKSEL INTCON
	; GIE is 0 to prevent interrpts from clearing bits
	movlw	0x7f
	movwf	INTCON
   .assert "intcon == 0x7f, \"*** FAILED 16f716 INT test - INTCON all bits writable\""
	nop
	movlw	(1<<GIE) | (1<<INTE) | (1<<RBIE)
	movwf	INTCON

 	BANKSEL PORTA

        clrf    inte_cnt
	clrf	bioc_cnt
        bsf     PORTA,2          ; make a rising edge
        nop
        movf    inte_cnt,w
   .assert "W == 0x01, \"*** FAILED 16f716 INT test - No int +edge INTEDG=1\""
        nop
        clrf    inte_cnt
        bcf     PORTA,2          ; make a falling edge
        nop
        movf    inte_cnt,w
   .assert "W == 0x00, \"*** FAILED 16f716 INT test - Unexpected int -edge INTEDG=1\""
        nop

	BANKSEL	OPTION_REG
	bcf	OPTION_REG,INTEDG
	BANKSEL PORTA
        clrf    inte_cnt
        bsf     PORTA,2          ; make a rising edge
        nop
        movf    inte_cnt,w
   .assert "W == 0x00, \"*** FAILED 16f716 INT test - Unexpected int +edge INTEDG=0\""
        nop
        clrf    inte_cnt
        bcf     PORTA,2          ; make a falling edge
        nop
        movf    inte_cnt,w
   .assert "W == 0x01, \"*** FAILED 16f716 INT test - No int -edge INTEDG=0\""
        nop

	BANKSEL TRISB
	bcf	TRISB,3
	bsf	TRISB,4
	BANKSEL PORTB
	bsf	PORTB,3
	bcf	PORTB,3
   .assert "bioc_cnt == 2, \"*** FAILED 16f716 IOC test - both edges\"" 
	nop


        return


 	org 0x200
rrDATA
	dw 0x01, 0x02, 0x03
  end

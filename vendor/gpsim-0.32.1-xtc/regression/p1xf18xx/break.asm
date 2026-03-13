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
        ;; simulate a pic 12F1822.


	list    p=12f1822          ; list directive to define processor
	include <p12f1822.inc>     ; processor specific variable definitions
        include <coff.inc>         ; Grab some useful macros

        __CONFIG _CONFIG1, _CP_OFF & _WDTE_ON &  _FOSC_INTOSC & _PWRTE_ON &  _BOREN_OFF & _MCLRE_OFF & _CLKOUTEN_OFF
        __CONFIG _CONFIG2, _STVREN_ON ; & _WRT_BOOT

;------------------------------------------------------------------------
; gpsim command
.command macro x
  .direct "C", x
  endm

    GLOBAL temp, temp2, temp3, A0

;----------------------------------------------------------------------
GPR_DATA                UDATA_SHR
temp            RES     1
w_temp          RES     1
temp2           RES     1
temp3           RES     1
status_temp     RES     1
cmif_cnt	RES	1
tmr0_cnt	RES	1
tmr1_cnt	RES	1
eerom_cnt	RES	1
adr_cnt		RES	1
data_cnt	RES	1
inte_cnt	RES	1
iocaf_val	RES     1

GPR_DATA2	UDATA	0xa0
A0		RES	1

  GLOBAL iocaf_val

;----------------------------------------------------------------------
;   ********************* RESET VECTOR LOCATION  ********************
;----------------------------------------------------------------------
RESET_VECTOR  CODE    0x000              ; processor reset vector
        movlp  high  start               ; load upper byte of 'start' label
        goto   start                     ; go to beginning of program


  .sim "node n1"
  .sim "attach n1 porta0 porta3"
  .sim "node n2"
  .sim "attach n2 porta1 porta4"
  .sim "node n3"
  .sim "attach n3 porta2 porta5"
  .sim "p12f1822.BreakOnReset = false"
  .sim "log w W"
  .sim "log r W"
  ;.sim "log lxt"
  .sim "log on"


;------------------------------------------------------------------------
;
;  Interrupt Vector
;
;------------------------------------------------------------------------
                                                                                
INT_VECTOR   CODE    0x004               ; interrupt vector location
	; many of the core registers now saved and restored automatically
                                                                                
	clrf	BSR		; set bank 0

	btfsc	PIR2,EEIF
	    goto ee_int

  	btfsc	INTCON,T0IF
	    goto tmr0_int

  	btfsc	INTCON,IOCIF
	    goto inte_int

	.assert "'***FAILED p12f1822 unexpected interrupt'"
	nop


; Interrupt from TMR0
tmr0_int
	incf	tmr0_cnt,F
	bcf	INTCON,T0IF
	goto	exit_int

; Interrupt from eerom
ee_int
	incf	eerom_cnt,F
	bcf	PIR2,EEIF
	goto	exit_int

; Interrupt from INT pin
inte_int
	incf	inte_cnt,F
	BANKSEL IOCAF
	movf	IOCAF,W
	movwf	iocaf_val
	xorlw	0xff
	andwf 	IOCAF, F
	goto	exit_int

exit_int:
                                                                                
;; STATUS and W now restored by RETFIE
        retfie
                                                                                

;----------------------------------------------------------------------
;   ******************* MAIN CODE START LOCATION  ******************
;----------------------------------------------------------------------
MAIN    CODE
start
        BANKSEL PCON
        btfss   PCON,NOT_RI
        goto    soft_reset

	movlw	0xc0
	movwf	INTCON
	BANKSEL PIE1
	movlw	0x61
	movwf	PIE1
	BANKSEL APFCON
	movlw	0x84
	movwf	APFCON
	BANKSEL SPBRG
	movlw	25
	movwf	SPBRG
	bsf	RCSTA,SPEN
	movlw	(1<<SYNC)|(1<<BRGH)|(1<<TXEN)
	movwf	TXSTA
	bsf	RCSTA,CREN	
	
	BANKSEL ANSELA
	movlw	3
	movwf	ANSELA
	BANKSEL	TRISA
	movlw	0x23
	movwf	TRISA

	call test_pwm
	reset

soft_reset:
  .assert "cycles > 100, '*** FAILED 12f1822 Unexpected soft reset'"
	nop
  .assert  "'*** PASSED 12f1822 Functionality'"
	nop
	goto	$



test_pwm
	BANKSEL APFCON
;	bsf	APFCON,0	;PA1 RA5
	BANKSEL CCPR1L
	clrf	CCPR1L
	movlw	0x3c
	movwf	CCP1CON
	BANKSEL PR2
	movlw	0x0f
	movwf	PR2
	bsf	T2CON,TMR2ON

	movlw	5
	movwf	temp
pwm_loop:
	BANKSEL  PIR1
	clrf	PIR1
	btfss	PIR1,TMR2IF
	goto	$-1
	decfsz	temp,F
	goto	pwm_loop
	BANKSEL T2CON
	bcf	T2CON,TMR2ON
	BANKSEL CCP1CON
	clrf	CCP1CON
	BANKSEL APFCON
;	bcf	APFCON,0	;PA1 RA5

	return
	



  end

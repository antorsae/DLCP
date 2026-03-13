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
        ;; simulate a pic 16F1825.
        ;; Specifically, basic port operation, eerom, interrupts,
	;; a2d, dac, SR latch, capacitor sense, and enhanced instructions


	list    p=16f1825                ; list directive to define processor
	include <p16f1825.inc>           ; processor specific variable definitions
        include <coff.inc>              ; Grab some useful macros

        __CONFIG _CONFIG1, _CP_OFF & _WDTE_ON &  _FOSC_INTOSC & _PWRTE_ON &  _BOREN_OFF & _MCLRE_OFF & _CLKOUTEN_OFF
        __CONFIG _CONFIG2, _STVREN_ON ; & _WRT_BOOT

;------------------------------------------------------------------------
; gpsim command
.command macro x
  .direct "C", x
  endm


;----------------------------------------------------------------------
GPR_DATA                UDATA_SHR
cmif_cnt	RES	1
tmr0_cnt	RES	1
tmr1_cnt	RES	1
eerom_cnt	RES	1
adr_cnt		RES	1
data_cnt	RES	1
inte_cnt	RES	1
iocaf_val	RES	1

 GLOBAL inte_cnt, iocaf_val


;----------------------------------------------------------------------
;   ********************* RESET VECTOR LOCATION  ********************
;----------------------------------------------------------------------
RESET_VECTOR  CODE    0x000              ; processor reset vector
        movlp  high  start               ; load upper byte of 'start' label
        goto   start                     ; go to beginning of program


  .sim "module library libgpsim_modules"
  ; Use a pullup resistor as a voltage source
;  .sim "module load pullup V1"
;  .sim "V1.resistance = 10000.0"
;  .sim "V1.capacitance = 20e-12"
;  .sim "V1.voltage=1.0"

  .sim "node cin1"
  .sim "attach cin1 porta0 portc2"
  .sim "node min"
  .sim "attach min porta1 portc3"
  .sim "node cin2"
  .sim "attach cin2 porta2 portc5"
  .sim "scope.ch0 = \"portc4\""
  .sim "scope.ch1 = \"portc3\""
  .sim "scope.ch2 = \"portc2\""
  .sim "scope.ch3 = \"portc5\""
  .sim "p16f1825.xpos = 72"
  .sim "p16f1825.ypos = 72"

#define DRIVE_CIN1   PORTA,0
#define DRIVE_MIN    PORTA,1
#define DRIVE_CIN2   PORTA,2

;  .sim "V1.xpos = 216"
;  .sim "V1.ypos = 120"


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

	.assert "\"***FAILED p16f1825 unexpected interrupt\""
	nop


; Interrupt from TMR0
tmr0_int
	incf	tmr0_cnt,F
	bcf 	INTCON,T0IF
	goto	exit_int

; Interrupt from eerom
ee_int
	incf	eerom_cnt,F
	bcf 	PIR2,EEIF
	goto	exit_int

; Interrupt from INT pin
inte_int
	incf	inte_cnt,F
	bcf	INTCON,GIE	; stop interrupts
	goto	exit_int

exit_int:
                                                                                
        retfie
                                                                                

;----------------------------------------------------------------------
;   ******************* MAIN CODE START LOCATION  ******************
;----------------------------------------------------------------------
MAIN    CODE
start
	;set clock to 16 MHz
	BANKSEL OSCCON
	bsf 	OSCCON,6
	btfss	OSCSTAT,HFIOFL
	goto	$-1
   .assert "(oscstat & 0x19) == 0x19,  \"*** FAILED 16f1825 HFIO bit error\""
	nop
	BANKSEL ANSELA
	clrf    ANSELA
	clrf    ANSELC
	BANKSEL TRISA
	clrf	TRISA
	bcf	TRISC,4

	BANKSEL MDSRC
	movlw	0x01
	movwf	MDSRC	; MIN = MDIN pin
	movwf	MDCARL  ; CARL = MDCIN1
	movlw	0x02
	movwf	MDCARH	; CARH = MDCIN2
        movlw   (1<< MDEN) | (1<< MDOE)
	movwf	MDCON
        banksel PORTA
	clrf	PORTA
   .assert "portc == 0, \"DSM 16f1825 MIN=0 CH=0 CL=0 out=0\""
	nop
	bsf	DRIVE_CIN1		; CARL = 1
   .assert "portc == 0x14, \"DSM 16f1825 MIN=0 CH=0 CL=1 out=1\""
	nop
	bsf	DRIVE_MIN		; MIN = 1
   .assert "portc == 0x0c, \"DSM 16f1825 MIN=1 CH=0 CL=1 out=0\""
	nop
	BANKSEL MDCON
	bsf	MDCARH,MDCHPOL
   .assert "portc == 0x1c, \"DSM 16f1825 MIN=1 CH=0(INV) CL=1 out=1\""
	nop
	BANKSEL PORTA
	bcf	DRIVE_MIN
   .assert "portc == 0x14, \"DSM 16f1825 MIN=0 CH=0(INV) CL=1 out=1\""
	nop
	BANKSEL MDCON
	bsf	MDCARL,MDCLPOL
   .assert "portc == 0x04, \"DSM 16f1825 MIN=0 CH=0(INV) CL=1(INV) out=0\""
	nop
	bcf	MDCARL,MDCLPOL
	bcf	MDCARH,MDCHPOL
	clrf	MDSRC		; use MDBIT of MDCON
	bcf	MDCON,MDBIT
	BANKSEL PORTA
	bcf	DRIVE_CIN1
	bsf	DRIVE_CIN2
   .assert "portc == 0x20, \"DSM 16f1825 MDBIT=0 CH=1 CL=0 out=0\""
	nop
	BANKSEL MDCON
	bsf	MDCON,MDBIT
   .assert "portc == 0x30, \"DSM 16f1825 MDBIT=1 CH=1 CL=0 out=1\""
	nop
	bsf	MDCON,MDOPOL
   .assert "portc == 0x20, \"DSM 16f1825 MDBIT=1 CH=1 CL=0 out=0(INV)\""
	nop
	
	movlw	0x07
	movwf	PORTA
	clrf	PORTA
	bsf	PORTA,0
	bcf	PORTA,0
  .assert  "\"*** PASSED 16f1825 Functionality\""
	nop
	reset
	goto	$

  end

; 
; Copyright (c) 2022 Roy Rankin
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


        list    p=18f26k22
        include <p18f26k22.inc>
        include <coff.inc>

        CONFIG WDTEN=ON
        CONFIG WDTPS=128
        CONFIG MCLRE = INTMCLR
        CONFIG FOSC = INTIO67

        errorlevel -302 
        radix dec

.command macro x
  .direct "C", x
  endm

;----------------------------------------------------------------------
;----------------------------------------------------------------------
GPR_DATA                UDATA_SHR 0

;----------------------------------------------------------------------
;   ********************* RESET VECTOR LOCATION  ********************
;----------------------------------------------------------------------
RESET_VECTOR  CODE    0x000              ; processor reset vector
        bra   start                     ; go to beginning of program

        ;; 
        ;; Interrupt
        ;; 
INTERRUPT_VECTOR CODE 0X008

        goto    interrupt

MAIN    CODE
    .sim "node n0"
    .sim "attach n0 porta0 portc0"
    .sim "node n1"
    .sim "attach n1 portc1 portb0"
    .sim "symbol cycleCount=0"
start
       ;set clock to 16 Mhz

        BANKSEL OSCCON
        bsf     OSCCON,6

        clrf    STATUS
        BANKSEL ANSELA
	movlw	0x03	; a0, a1 analog
	movwf	ANSELA
	clrf	ANSELB
        clrf    ANSELC
	bcf	TRISC,0	;drive a0
	bcf	TRISC,1	;drive b0
	bcf	TRISA,4 ;SR latch Q
	bcf	TRISA,5	;SR latch NQ

	call	comp_srm
	call	sri	; test set reset inputs
	call	perf_srm

    .assert "'*** PASSED p18f26k22 SR Latch'"
	nop
; SR Latch Peripheral control
perf_srm:
	BANKSEL	SRCON0
	; enable SR LATCH and Q, NQ outputs
	movlw	(1<<SRLEN) | (1<<SRQEN) | (1<<SRNQEN)
	movwf	SRCON0
	movlw	(1<<SRSPE)	; ISR pin sets SR Latch
	movwf	SRCON1
	BANKSEL LATC
	bsf	LATC,1
    .assert "(porta & 0x30) == 0x10, '*** FAILED p18f26k22 SR Latch  SRSPE'"
	nop
	bcf	LATC,1
	BANKSEL SRCON1
	movlw	(1<<SRRPE)
	movwf	SRCON1
	BANKSEL LATC
	bsf	LATC,1
    .assert "(porta & 0x30) == 0x20, '*** FAILED p18f26k22 SR Latch  SRRPE'"
	nop
	bcf	LATC,1
	return

; compartor drive SR latch
comp_srm:
	BANKSEL VREFCON0
	movlw	(1<<FVREN) | (1<<FVRS1)
	movwf	VREFCON0
	btfss	VREFCON0,FVRST
	goto	$-1
	BANKSEL CM1CON0
	movlw	(1<<C1RSEL) | (1<<C2RSEL)
	movwf	CM2CON1		; FVR BUF1 routed to C12VREF input
	movlw	(1<<C1ON)|(1<<C1R) | (1<<C1POL)
	movwf	CM1CON0		;CM1 ON, FVR IN+ CM12IN0- invert
	movlw	(1<<C2ON)|(1<<C2R)  ; CM2 ON, FVR IN+ CM12IN0-
	movwf	CM2CON0
	BANKSEL SRCON0
	; enable SR LATCH and Q, NQ outputs
	movlw	(1<<SRLEN) | (1<<SRQEN) | (1<<SRNQEN)
	movwf	SRCON0
	bsf	SRCON0,SRPR	; reset
	; cm1 set cm2 reset
	movlw	(1<<SRSC1E)|(1<<SRRC2E)
	movwf	SRCON1
	BANKSEL LATC
	bsf	LATC,0
    .assert "(porta & 0x30) == 0x10, '*** FAILED p18f26k22 SR Latch CM1 set'"
	nop
	bcf	LATC,0
    .assert "(porta & 0x30) == 0x20, '*** FAILED p18f26k22 SR Latch CM2 reset'"
	nop
	BANKSEL SRCON0
       ; cm1 reset cm2 set
        movlw   (1<<SRRC1E)|(1<<SRSC2E)
        movwf   SRCON1
    .assert "(porta & 0x30) == 0x10, '*** FAILED p18f26k22 SR Latch CM2 set'"
	nop

	BANKSEL LATC
	bsf	LATC,0
    .assert "(porta & 0x30) == 0x20, '*** FAILED p18f26k22 SR Latch CM1 reset'"
	nop
	bcf	LATC,0
	BANKSEL SRCON0
	clrf	SRCON0
	clrf	SRCON1
	return
; 
; test set reset inputs
sri:
	BANKSEL SRCON0
	; enable SR LATCH and Q, NQ outputs
	movlw	(1<<SRLEN) | (1<<SRQEN) | (1<<SRNQEN)
	movwf	SRCON0
	bsf	SRCON0,SRPR
    .assert "(porta & 0x30) == 0x20, '*** FAILED p18f26k22 SR Latch clear'"
	nop
	bsf	SRCON0,SRPS
    .assert "(porta & 0x30) == 0x10, '*** FAILED p18f26k22 SR Latch pulse set'"
	nop
	bsf	SRCON0,SRPR
    .assert "(porta & 0x30) == 0x20, '*** FAILED p18f26k22 SR Latch pulse reset'"
	nop
	movlw	(1<<SRLEN) | (1<<SRQEN) | (1<<SRNQEN) | 0x70
	movwf	SRCON0
    .command "cycleCount = cycles"
        nop
	bsf	SRCON1,SRSCKE

    .command "cycleCount"
	nop
	btfss	PORTA,4
	goto	$-1
    .command "cycleCount = cycles - cycleCount"
        nop
    .assert "(cycleCount > 132) && (cycleCount < 136), ''*** FAILED p18f26k22 SR Latch pulse SRSCKE'"
	nop 
	bcf	SRCON1,SRSCKE
    .command "cycleCount = cycles"
        nop
	bsf	SRCON1,SRRCKE
	btfsc	PORTA,4
	goto	$-1
    .command "cycleCount = cycles - cycleCount"
        nop
    .assert "(cycleCount > 132) && (cycleCount < 136), ''*** FAILED p18f26k22 SR Latch pulse SRRCKE'"
	nop 
	clrf	SRCON0
	clrf	SRCON1
	return

interrupt

back_interrupt:
        retfie 1


	end

list p=16f628
include "p16f628.inc"
include <coff.inc>
	__CONFIG _CP_OFF &  _BODEN_ON & _MCLRE_OFF & _PWRTE_ON & _WDT_OFF & _INTRC_OSC_NOCLKOUT & _LVP_OFF

;----------------------------------------------------------------------
;----------------------------------------------------------------------
GPR_DATA                UDATA_SHR
temp            RES     1

w_temp          RES     1
status_temp     RES     1
tmr1_cnt        RES     1

	org 0
	goto main
;------------------------------------------------------------------------
;
;  Interrupt Vector
;
;------------------------------------------------------------------------
                                                                                
INT_VECTOR   CODE    0x004               ; interrupt vector location
                                                                                
        movwf   w_temp
        swapf   STATUS,W
        movwf   status_temp

        BANKSEL PIR1
        btfsc   PIR1,TMR1IF
           goto tmr1_int

       .assert "\"***FAILED p16f690 unexpected interrupt\""
        nop

	goto exit_int

; Interrupt from TMR1
tmr1_int
        incf    tmr1_cnt,F
        bcf     PIR1,TMR1IF
        goto    exit_int

exit_int:
                                                                                
        swapf   status_temp,w
        movwf   STATUS
        swapf   w_temp,f
        swapf   w_temp,w
        retfie



main:
	banksel T1CON

; Disable timer 1
	bcf T1CON, TMR1ON
	bsf T1CON, TMR1ON
	bcf T1CON, TMR1ON

	movlw 0x34
	movwf TMR1L
	movlw 0x12
	movwf TMR1H

	movf  TMR1L,W
 .assert "W==0x34, \"*** FAILED TMR1 test TMR1L write\""
	nop
	movf  TMR1H,W
 .assert "W==0x12, \"*** FAILED TMR1 test TMR1H write\""
	nop


; counter is set to 0x1234 - works

; Enable timer 1
	bsf T1CON, TMR1ON

 .assert "tmr1l==0x35, \"*** FAILED TMR1 test TMR1L reset on start\""
	nop
; oops - counter is 0x1 now
; setting TMR1ON must have reset it to 0x0!
	bcf	T1CON,TMR1CS
	banksel PIE1
	bsf	PIE1,TMR1IE
	bsf	INTCON,PEIE
	bsf	INTCON,GIE 
	sleep
	nop
	nop

 .assert "\"*** PASSED TMR1\""
	nop
	goto $+0
end


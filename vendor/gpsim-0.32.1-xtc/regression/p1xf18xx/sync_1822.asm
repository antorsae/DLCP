        list    p=12f1822
        include <p12f1822.inc>
        include <coff.inc>
       __CONFIG _CONFIG1, _CP_OFF & _WDTE_ON &  _FOSC_INTOSC & _PWRTE_ON &  _BOREN_OFF & _MCLRE_OFF & _CLKOUTEN_OFF



        errorlevel -302 
        radix dec

;SPBRG  :  3                      : 1 Mbits/se
;TXSTA  :  10110000  (B0h) : 8-bit tran
;RCSTA  :  10010000  (90h) : 8-bit rece


;*******************************************
; Sample Code For Synchronous Mode
;*******************************************

#define ClkFreq     16000000
#define baud(X)     ((10*ClkFreq/(4*X))+5)/10 - 1
#define TXSTA_INIT  0xB0
#define RCTSA_INIT  0x90

MAIN	CODE
start
       ;set clock to 16 Mhz
        BANKSEL OSCCON
        bsf     OSCCON,6

        clrf    STATUS
        BANKSEL ANSELA
        clrf    ANSELA  ; set port to digital


Setup_Sync_Master_Mode
        movlb 0
        movlw baud(1000000)
	BANKSEL	SPBRG
        movwf SPBRG
        movlw (1<<CSRC) | (1<<SYNC) | (1<<TXEN) ; TXSTA_INIT
        movwf TXSTA
        movlw (1<<SPEN) | (1<<CREN)	;RCSTA_INIT
        movwf RCSTA

  .assert "\"end\""

	nop

          return

    end

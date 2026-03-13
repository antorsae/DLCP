   ;;  EUSART test 
   ;;
   ;;  The purpose of this program is to verify that gpsim's
   ;; USART functions properly when configured as an EUSART. 
   ;; The USART module is used to loop
   ;; characters back to the receiver testing  RCIF interupts.
   ;;
   ;;
   ;;

	list	p=18f4455
	include <p18f4455.inc>
	include <coff.inc>

 CONFIG WDT=OFF
;;  
 CONFIG MCLRE=OFF  
 CONFIG  LPT1OSC=OFF 
 CONFIG PBADEN=OFF
 CONFIG CCP2MX=ON, FOSC = INTOSCIO_EC
;;  __CONFIG  _CONFIG2H,  _WDT_OFF_2H



        errorlevel -302 
	radix dec

BAUDHI  equ     ((100000/4)/48)-1
BAUDLO  equ     129


;----------------------------------------------------------------------
; RAM Declarations


;
INT_VAR        UDATA   0x00
w_temp          RES     1
status_temp     RES     1
pclath_temp     RES     1



GPR_DAT        UDATA

#define	RX_BUF_SIZE	0x10

temp1		RES	1
temp2		RES	1
temp3		RES	1

tx_ptr		RES	1

rxLastByte	RES	1
rxFlag		RES	1

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

INT_VECTOR   CODE    0x008               ; Hi priority interrupt vector location

        movwf   w_temp
        swapf   STATUS,W
        movwf   status_temp
	movf	PCLATH,w
	movwf	pclath_temp
	clrf	PCLATH
	goto	int_more

LOW_INT_VECTOR   CODE    0x018               ; interrupt vector location

	movwf	w_temp
	swapf	STATUS,w
	clrf	STATUS
	movwf	status_temp
	movf	PCLATH,w
	movwf	pclath_temp
	clrf	PCLATH

int_more:
	btfsc	INTCON,PEIE
	 btfss	PIR1,SPPIF
	  goto	int_done
	bcf	PIR1,SPPIF

int_done:
	clrf	STATUS
	movf	pclath_temp,w
	movwf	PCLATH
	swapf	status_temp,w
	movwf	STATUS
	swapf	w_temp,f
	swapf	w_temp,w
	retfie


;; ----------------------------------------------------
;;
;;            start
;;

MAIN    CODE
start	
	movlw	0xff
	movwf	ADCON1
	movlw	0xff
	movwf	TRISD
	bcf	TRISE,0
	bcf	TRISE,1
	bcf	TRISE,2
	bcf	TRISB,4
	bsf	PIE1,SPPIE
	bsf	INTCON,GIE
	bsf	INTCON,PEIE
	bsf	SPPCON,SPPEN
	bsf	SPPCFG,CLK1EN
	bsf	SPPCFG,CSEN
	call	spp_io
	bsf	SPPCFG,CLKCFG0
	call	spp_io
	bcf	SPPCON,SPPEN
	nop

spp_io:
	;; write odd address
	movlw	0xf5
	movwf	SPPEPS
	nop
	nop
	;; write even address
	movlw	0xf4
	movwf	SPPEPS
	nop
	nop
	;; write data
	movlw	0x5f
	movwf	SPPDATA
	nop
	nop
	;; read data
	movf	SPPDATA,W
	nop
	nop
	return

	end

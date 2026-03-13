;--------------------------------------------------------
; File Created by SDCC : free open source ANSI-C Compiler
; Version 2.9.0 #5416 (Feb  3 2010) (UNIX)
; This file was generated Mon Jan 14 09:25:17 2013
;--------------------------------------------------------
; PIC port for the 14-bit core
;--------------------------------------------------------
;	.file	"usart.c"
	list	p=16f690
	radix dec
	include "p16f690.inc"
;--------------------------------------------------------
; config word 
;--------------------------------------------------------
	__config 0x30d4
;--------------------------------------------------------
; external declarations
;--------------------------------------------------------
	extern	_ADCON0_bits
	extern	_ADCON1_bits
	extern	_ANSEL_bits
	extern	_ANSELH_bits
	extern	_BAUDCTL_bits
	extern	_CCP1CON_bits
	extern	_CM1CON0_bits
	extern	_CM2CON0_bits
	extern	_CM2CON1_bits
	extern	_ECCPAS_bits
	extern	_EECON1_bits
	extern	_INTCON_bits
	extern	_IOC_bits
	extern	_IOCA_bits
	extern	_IOCB_bits
	extern	_OPTION_REG_bits
	extern	_OSCCON_bits
	extern	_OSCTUNE_bits
	extern	_PCON_bits
	extern	_PIE1_bits
	extern	_PIE2_bits
	extern	_PIR1_bits
	extern	_PIR2_bits
	extern	_PORTA_bits
	extern	_PORTB_bits
	extern	_PORTC_bits
	extern	_PSTRCON_bits
	extern	_PWM1CON_bits
	extern	_RCSTA_bits
	extern	_SPBRG_bits
	extern	_SPBRGH_bits
	extern	_SRCON_bits
	extern	_SSPCON_bits
	extern	_SSPSTAT_bits
	extern	_STATUS_bits
	extern	_T1CON_bits
	extern	_T2CON_bits
	extern	_TRISA_bits
	extern	_TRISB_bits
	extern	_TRISC_bits
	extern	_TXSTA_bits
	extern	_VRCON_bits
	extern	_WDTCON_bits
	extern	_WPUA_bits
	extern	_WPUB_bits
	extern	_INDF
	extern	_TMR0
	extern	_PCL
	extern	_STATUS
	extern	_FSR
	extern	_PORTA
	extern	_PORTB
	extern	_PORTC
	extern	_PCLATH
	extern	_INTCON
	extern	_PIR1
	extern	_PIR2
	extern	_TMR1L
	extern	_TMR1H
	extern	_T1CON
	extern	_TMR2
	extern	_T2CON
	extern	_SSPBUF
	extern	_SSPCON
	extern	_CCPR1L
	extern	_CCPR1H
	extern	_CCP1CON
	extern	_RCSTA
	extern	_TXREG
	extern	_RCREG
	extern	_PWM1CON
	extern	_ECCPAS
	extern	_ADRESH
	extern	_ADCON0
	extern	_OPTION_REG
	extern	_TRISA
	extern	_TRISB
	extern	_TRISC
	extern	_PIE1
	extern	_PIE2
	extern	_PCON
	extern	_OSCCON
	extern	_OSCTUNE
	extern	_PR2
	extern	_SSPADD
	extern	_MSK
	extern	_SSPMSK
	extern	_SSPSTAT
	extern	_WPU
	extern	_WPUA
	extern	_IOC
	extern	_IOCA
	extern	_WDTCON
	extern	_TXSTA
	extern	_BAUDCTL
	extern	_ADRESL
	extern	_ADCON1
	extern	_EEDAT
	extern	_EEDATA
	extern	_EEADR
	extern	_EEDATH
	extern	_EEADRH
	extern	_WPUB
	extern	_IOCB
	extern	_VRCON
	extern	_CM1CON0
	extern	_CM2CON0
	extern	_CM2CON1
	extern	_EECON1
	extern	_EECON2
	extern	_PSTRCON
	extern	_SRCON
	extern	__gptrget1
	extern	__sdcc_gsinit_startup
;--------------------------------------------------------
; global declarations
;--------------------------------------------------------
	global	_main

	global PSAVE
	global SSAVE
	global WSAVE
	global STK12
	global STK11
	global STK10
	global STK09
	global STK08
	global STK07
	global STK06
	global STK05
	global STK04
	global STK03
	global STK02
	global STK01
	global STK00

sharebank udata_ovr 0x0070
PSAVE	res 1
SSAVE	res 1
WSAVE	res 1
STK12	res 1
STK11	res 1
STK10	res 1
STK09	res 1
STK08	res 1
STK07	res 1
STK06	res 1
STK05	res 1
STK04	res 1
STK03	res 1
STK02	res 1
STK01	res 1
STK00	res 1

;--------------------------------------------------------
; global definitions
;--------------------------------------------------------
;--------------------------------------------------------
; absolute symbol definitions
;--------------------------------------------------------
;--------------------------------------------------------
; compiler-defined variables
;--------------------------------------------------------
UDL_usart_0	udata
r0x1000	res	1
r0x1001	res	1
r0x1002	res	1
r0x1003	res	1
r0x1004	res	1
;--------------------------------------------------------
; initialized data
;--------------------------------------------------------

ID_usart_0	code
_str
	retlw 0x48

	retlw 0x65

	retlw 0x6c

	retlw 0x6c

	retlw 0x6f

	retlw 0x20

	retlw 0x77

	retlw 0x6f

	retlw 0x72

	retlw 0x6c

	retlw 0x64

	retlw 0x21

	retlw 0x00


;--------------------------------------------------------
; overlayable items in internal ram 
;--------------------------------------------------------
;	udata_ovr
;--------------------------------------------------------
; reset vector 
;--------------------------------------------------------
STARTUP	code 0x0000
	nop
	pagesel _main
	goto	_main
;--------------------------------------------------------
; code
;--------------------------------------------------------
code_usart	code
;***
;  pBlock Stats: dbName = M
;***
;entry:  _main	;Function start
; 2 exit points
;has an exit
;functions called:
;   __gptrget1
;   __gptrget1
;   __gptrget1
;   __gptrget1
;7 compiler assigned registers:
;   r0x1000
;   r0x1001
;   r0x1002
;   r0x1003
;   STK01
;   STK00
;   r0x1004
;; Starting pCode block
_main	;Function start
; 2 exit points
;	.line	42; "usart.c"	ANSEL = 0;
	BANKSEL	ANSEL
	CLRF	ANSEL
;	.line	43; "usart.c"	ANSELH = 0;
	CLRF	ANSELH
;	.line	46; "usart.c"	CM1CON0 = 0;
	CLRF	CM1CON0
;	.line	47; "usart.c"	CM2CON0 = 0;
	CLRF	CM2CON0
;	.line	49; "usart.c"	TRISB5 = 1;
	BANKSEL	TRISB
	BSF	TRISB,5
;	.line	50; "usart.c"	TRISB7 = 0;
	BCF	TRISB,7
;	.line	52; "usart.c"	PORTB = 1;
	MOVLW	0x01
	BANKSEL	PORTB
	MOVWF	PORTB
;	.line	54; "usart.c"	TX9 = 0;	
	BANKSEL	TXSTA
	BCF	TXSTA,6
;	.line	55; "usart.c"	BRG16 = 0;
	BCF	BAUDCTL,3
;	.line	56; "usart.c"	BRGH = 1;
	BSF	TXSTA,2
;	.line	58; "usart.c"	SPBRG = 25;
	MOVLW	0x19
	MOVWF	SPBRG
;	.line	60; "usart.c"	SYNC = 0;			// Disable Synchronous/Enable Asynchronous
	BCF	TXSTA,4
;	.line	61; "usart.c"	SPEN = 1;			// Enable serial port
	BANKSEL	RCSTA
	BSF	RCSTA,7
;	.line	62; "usart.c"	CREN = 0;
	BCF	RCSTA,4
;	.line	64; "usart.c"	TXEN = 1;			// Enable transmission mode
	BANKSEL	TXSTA
	BSF	TXSTA,5
;	.line	66; "usart.c"	for(i=0; str[i] != '\0'; i++)
	BANKSEL	r0x1000
	CLRF	r0x1000
	CLRF	r0x1001
_00108_DS_
	BANKSEL	r0x1000
	MOVF	r0x1000,W
	ADDLW	(_str + 0)
	MOVWF	r0x1002
	MOVLW	high (_str + 0)
	MOVWF	r0x1003
	MOVF	r0x1001,W
	BTFSC	STATUS,0
	INCFSZ	r0x1001,W
	ADDWF	r0x1003,F
	MOVF	r0x1002,W
	MOVWF	STK01
	MOVF	r0x1003,W
	MOVWF	STK00
	MOVLW	0x80
;;	PAGESEL	__gptrget1
;;	CALL	__gptrget1
	PAGESEL	$
	BANKSEL	r0x1004
	MOVWF	r0x1004
;	.line	68; "usart.c"	while (!TRMT) {}; // wait until TSR is empty
	MOVF	r0x1004,W
	BTFSC	STATUS,2
	GOTO	_00113_DS_
_00105_DS_
	BANKSEL	TXSTA
	BTFSS	TXSTA,1
	GOTO	_00105_DS_
;	.line	69; "usart.c"	TXREG = str[i];	// Add a character to the output buffer
	BANKSEL	r0x1000
	MOVF	r0x1000,W
	ADDLW	(_str + 0)
	MOVWF	r0x1002
	MOVLW	high (_str + 0)
	MOVWF	r0x1003
	MOVF	r0x1001,W
	BTFSC	STATUS,0
	INCFSZ	r0x1001,W
	ADDWF	r0x1003,F
	MOVF	r0x1002,W
	MOVWF	STK01
	MOVF	r0x1003,W
	MOVWF	STK00
	MOVLW	0x80
;;	PAGESEL	__gptrget1
;;	CALL	__gptrget1
	PAGESEL	$
	BANKSEL	TXREG
	MOVWF	TXREG
;	.line	66; "usart.c"	for(i=0; str[i] != '\0'; i++)
	BANKSEL	r0x1000
	INCF	r0x1000,F
	BTFSC	STATUS,2
	INCF	r0x1001,F
	GOTO	_00108_DS_
_00113_DS_
	GOTO	_00113_DS_
	RETURN	
; exit point of _main


;	code size estimation:
;	   62+   17 =    79 instructions (  192 byte)

	end

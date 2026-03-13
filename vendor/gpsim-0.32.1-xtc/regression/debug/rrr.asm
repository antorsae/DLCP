;--------------------------------------------------------
; File Created by SDCC : free open source ANSI-C Compiler
; Version 4.1.0 #12072 (Linux)
;--------------------------------------------------------
; PIC port for the 14-bit core
;--------------------------------------------------------
;	.file	"rrr.c"
	list	p=12f1822
	radix dec
	include "p12f1822.inc"
;--------------------------------------------------------
; config word(s)
;--------------------------------------------------------
	__config _CONFIG1, 0x39a4
;--------------------------------------------------------
; external declarations
;--------------------------------------------------------
	extern	_MDCON
	extern	_WPUA
	extern	_SPBRG
	extern	_ANSELA
	extern	_OSCCON
	extern	_OPTION_REG
	extern	_TRISA
	extern	_CPSCON1
	extern	_CPSCON0
	extern	_T1GCON
	extern	_T1CON
	extern	_TMR1H
	extern	_TMR1L
	extern	_TMR0
	extern	_PORTA
	extern	_TXSTAbits
	extern	_RCSTAbits
	extern	_APFCONbits
	extern	_CM1CON0bits
	extern	_PIE1bits
	extern	_PIR1bits
	extern	_INTCONbits
	extern	__sdcc_gsinit_startup
;--------------------------------------------------------
; global declarations
;--------------------------------------------------------
	global	_main

	global STK15
	global STK14
	global STK13
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
STK15	res 1
STK14	res 1
STK13	res 1
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
;--------------------------------------------------------
; initialized data
;--------------------------------------------------------
;--------------------------------------------------------
; initialized absolute data
;--------------------------------------------------------
;--------------------------------------------------------
; overlayable items in internal ram 
;--------------------------------------------------------
;	udata_ovr
;--------------------------------------------------------
; reset vector 
;--------------------------------------------------------
STARTUP	code 0x0000
	nop
	pagesel __sdcc_gsinit_startup
	goto	__sdcc_gsinit_startup
;--------------------------------------------------------
; code
;--------------------------------------------------------
code_rrr	code
;***
;  pBlock Stats: dbName = M
;***
;has an exit
;; Starting pCode block
S_rrr__main	code
_main:
; 2 exit points
;	.line	14; "rrr.c"	INTCONbits.GIE = 1 ; //Global interrupts enabled
	BANKSEL	_INTCONbits
	BSF	_INTCONbits,7
;	.line	15; "rrr.c"	INTCONbits.PEIE = 1 ; //Periferal interrupts enabled
	BSF	_INTCONbits,6
;	.line	16; "rrr.c"	INTCONbits.TMR0IE = 1 ;
	BSF	_INTCONbits,5
;	.line	17; "rrr.c"	PIE1bits.TMR1GIE = 1 ; //Timer1 Gate interrupts enabled
	BANKSEL	_PIE1bits
	BSF	_PIE1bits,7
;	.line	18; "rrr.c"	PIE1bits.RCIE = 0 ; //USART Receive interrupt
	BCF	_PIE1bits,5
;	.line	19; "rrr.c"	OSCCON = 0b11101000 ; //4MHz
	MOVLW	0xe8
	MOVWF	_OSCCON
;	.line	20; "rrr.c"	CM1CON0bits.C1ON = 0 ; //Comparator OFF CMxCON0:
	BANKSEL	_CM1CON0bits
	BCF	_CM1CON0bits,7
;	.line	21; "rrr.c"	MDCON = 0 ;
	BANKSEL	_MDCON
	CLRF	_MDCON
;	.line	22; "rrr.c"	ANSELA = 0x00 ;
	BANKSEL	_ANSELA
	CLRF	_ANSELA
;	.line	24; "rrr.c"	WPUA = 0x00 ; //pullups off
	BANKSEL	_WPUA
	CLRF	_WPUA
;	.line	25; "rrr.c"	TRISA = 0b00000001 ; //make all outputs except RA0 =input
	MOVLW	0x01
	BANKSEL	_TRISA
	MOVWF	_TRISA
;	.line	26; "rrr.c"	PORTA = 0 ; //make all pins low
	BANKSEL	_PORTA
	CLRF	_PORTA
;	.line	28; "rrr.c"	APFCONbits.RXDTSEL = 1 ; //RXDT on RA5
	BANKSEL	_APFCONbits
	BSF	_APFCONbits,7
;	.line	29; "rrr.c"	APFCONbits.TXCKSEL = 1 ; //TXCK  on RA4
	BSF	_APFCONbits,2
;	.line	30; "rrr.c"	APFCONbits.CCP1SEL = 0 ; //P1A on RA2 pin5 
	BCF	_APFCONbits,0
;	.line	31; "rrr.c"	ANSELA = 0b00000001 ; //AN0, AN1 analog input (prota prepei set APFCONbits)
	MOVLW	0x01
	BANKSEL	_ANSELA
	MOVWF	_ANSELA
;	.line	32; "rrr.c"	RCSTAbits.SPEN = 1 ;
	BSF	_RCSTAbits,7
;	.line	33; "rrr.c"	TXSTAbits.SYNC = 0 ;
	BCF	_TXSTAbits,4
;	.line	34; "rrr.c"	TXSTAbits.BRGH = 1 ;
	BSF	_TXSTAbits,2
;	.line	35; "rrr.c"	TXSTAbits.TXEN = 1 ;
	BSF	_TXSTAbits,5
;	.line	36; "rrr.c"	SPBRG = 25 ;
	MOVLW	0x19
	MOVWF	_SPBRG
;	.line	37; "rrr.c"	RCSTAbits.CREN = 1 ;
	BSF	_RCSTAbits,4
;	.line	39; "rrr.c"	OPTION_REG = 0b11010111 ; //Timer0 internal source, prescaler 256 
	MOVLW	0xd7
	BANKSEL	_OPTION_REG
	MOVWF	_OPTION_REG
;	.line	40; "rrr.c"	T1CON = 0b11000101 ; //cps, prescaler :0, timer1 ON
	MOVLW	0xc5
	BANKSEL	_T1CON
	MOVWF	_T1CON
;	.line	41; "rrr.c"	T1GCON = 0b11100001 ; //Gate Enable, Active high, Toggle Mode, Single pulse disabled, 0 done, source Timer0 overflow 
	MOVLW	0xe1
	MOVWF	_T1GCON
;	.line	42; "rrr.c"	TMR0 = 62 ; //proload for every 50ms
	MOVLW	0x3e
	MOVWF	_TMR0
;	.line	43; "rrr.c"	TMR1H = 0 ;  
	CLRF	_TMR1H
;	.line	44; "rrr.c"	TMR1L = 0 ; 
	CLRF	_TMR1L
;	.line	45; "rrr.c"	CPSCON1 = 0b0 ; //CPS ch0
	CLRF	_CPSCON1
;	.line	46; "rrr.c"	CPSCON0 = 0b10001100 ; //CPS on, Fixed VR, Current high range, Timer0 source pin
	MOVLW	0x8c
	MOVWF	_CPSCON0
;	.line	47; "rrr.c"	PIR1bits.TMR1GIF=0 ;
	BCF	_PIR1bits,7
;	.line	48; "rrr.c"	PIR1bits.RCIF = 0 ;
	BCF	_PIR1bits,5
;	.line	49; "rrr.c"	PIR1bits.TXIF = 0 ;
	BCF	_PIR1bits,4
_00106_DS_:
;	.line	53; "rrr.c"	goto arxi;
	GOTO	_00106_DS_
;	.line	54; "rrr.c"	}
	RETURN	
; exit point of _main


;	code size estimation:
;	   44+   12 =    56 instructions (  136 byte)

	end

;--------------------------------------------------------
; File Created by SDCC : free open source ANSI-C Compiler
; Version 4.1.0 #12072 (Linux)
;--------------------------------------------------------
; PIC port for the 14-bit core
;--------------------------------------------------------
;	.file	"tmr2_debug.c"
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
	extern	_CCP1CON
	extern	_CCPR1L
	extern	_WPUA
	extern	_SPBRG
	extern	_ANSELA
	extern	_FVRCON
	extern	_ADCON1
	extern	_ADCON0
	extern	_OSCCON
	extern	_TRISA
	extern	_PR2
	extern	_T1CON
	extern	_TMR1H
	extern	_TMR1L
	extern	_PORTA
	extern	_TXSTAbits
	extern	_RCSTAbits
	extern	_APFCONbits
	extern	_CM1CON0bits
	extern	_PIE1bits
	extern	_T2CONbits
	extern	_PIR1bits
	extern	_INTCONbits
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
;--------------------------------------------------------
; code
;--------------------------------------------------------
code_tmr2_debug	code
;***
;  pBlock Stats: dbName = M
;***
;has an exit
;; Starting pCode block
S_tmr2_debug__main	code
_main:
; 2 exit points
;	.line	14; "tmr2_debug.c"	INTCONbits.GIE = 1 ; //Global interrupts enabled
	BANKSEL	_INTCONbits
	BSF	_INTCONbits,7
;	.line	15; "tmr2_debug.c"	INTCONbits.PEIE = 1 ; //Periferal interrupts enabled
	BSF	_INTCONbits,6
;	.line	16; "tmr2_debug.c"	PIE1bits.ADIE = 1 ; //adc interrupt
	BANKSEL	_PIE1bits
	BSF	_PIE1bits,6
;	.line	17; "tmr2_debug.c"	PIE1bits.TMR1IE = 1 ; //Timer1 interrupts enabled
	BSF	_PIE1bits,0
;	.line	19; "tmr2_debug.c"	PIE1bits.RCIE = 1 ;
	BSF	_PIE1bits,5
;	.line	20; "tmr2_debug.c"	OSCCON = 0b11101000 ; //4MHz
	MOVLW	0xe8
	MOVWF	_OSCCON
;	.line	21; "tmr2_debug.c"	CM1CON0bits.C1ON = 0 ; //Comparator OFF CMxCON0:
	BANKSEL	_CM1CON0bits
	BCF	_CM1CON0bits,7
;	.line	22; "tmr2_debug.c"	MDCON = 0 ;
	BANKSEL	_MDCON
	CLRF	_MDCON
;	.line	23; "tmr2_debug.c"	ANSELA = 0x00 ;
	BANKSEL	_ANSELA
	CLRF	_ANSELA
;	.line	25; "tmr2_debug.c"	WPUA = 0x00 ; //pullups off
	BANKSEL	_WPUA
	CLRF	_WPUA
;	.line	26; "tmr2_debug.c"	TRISA = 0b00100011 ; //make all outputs except RA0, RA1, RA5 =input
	MOVLW	0x23
	BANKSEL	_TRISA
	MOVWF	_TRISA
;	.line	27; "tmr2_debug.c"	PORTA = 0 ; //make all pins low
	BANKSEL	_PORTA
	CLRF	_PORTA
;	.line	29; "tmr2_debug.c"	APFCONbits.RXDTSEL = 1 ; //RXDT on RA5
	BANKSEL	_APFCONbits
	BSF	_APFCONbits,7
;	.line	30; "tmr2_debug.c"	APFCONbits.TXCKSEL = 1 ; //TXCK on RA4
	BSF	_APFCONbits,2
;	.line	31; "tmr2_debug.c"	APFCONbits.CCP1SEL = 0 ; //P1A on RA2 pin5
	BCF	_APFCONbits,0
;	.line	32; "tmr2_debug.c"	ANSELA = 0b00000011 ; //AN0, AN1 analog input (prota prepei set APFCONbits)
	MOVLW	0x03
	BANKSEL	_ANSELA
	MOVWF	_ANSELA
;	.line	33; "tmr2_debug.c"	RCSTAbits.SPEN = 1 ;
	BSF	_RCSTAbits,7
;	.line	34; "tmr2_debug.c"	TXSTAbits.SYNC = 0 ;
	BCF	_TXSTAbits,4
;	.line	35; "tmr2_debug.c"	TXSTAbits.BRGH = 1 ;
	BSF	_TXSTAbits,2
;	.line	36; "tmr2_debug.c"	TXSTAbits.TXEN = 1 ;
	BSF	_TXSTAbits,5
;	.line	37; "tmr2_debug.c"	SPBRG = 25 ;
	MOVLW	0x19
	MOVWF	_SPBRG
;	.line	38; "tmr2_debug.c"	RCSTAbits.CREN = 1 ;
	BSF	_RCSTAbits,4
;	.line	40; "tmr2_debug.c"	FVRCON = 0b11000001 ; //Vref enabled 1.024V
	MOVLW	0xc1
	BANKSEL	_FVRCON
	MOVWF	_FVRCON
;	.line	41; "tmr2_debug.c"	ADCON0 = 0x00 ;
	BANKSEL	_ADCON0
	CLRF	_ADCON0
;	.line	42; "tmr2_debug.c"	ADCON1 = 0b11010011 ; //adfm=1, //f/16=62500Khz 16us, //Vref internal
	MOVLW	0xd3
	MOVWF	_ADCON1
;	.line	43; "tmr2_debug.c"	T1CON = 0b00100001 ; //clock instruction, prescaler :4, timer1 ON
	MOVLW	0x21
	BANKSEL	_T1CON
	MOVWF	_T1CON
;	.line	45; "tmr2_debug.c"	TMR1H = 0x0B ; //65555-3055 =62500 x4 =250000
	MOVLW	0x0b
	MOVWF	_TMR1H
;	.line	46; "tmr2_debug.c"	TMR1L = 0xBD ;
	MOVLW	0xbd
	MOVWF	_TMR1L
;	.line	47; "tmr2_debug.c"	PR2 = 66 ;
	MOVLW	0x42
	MOVWF	_PR2
;	.line	48; "tmr2_debug.c"	CCP1CON = 0b00111100 ;
	MOVLW	0x3c
	BANKSEL	_CCP1CON
	MOVWF	_CCP1CON
;	.line	52; "tmr2_debug.c"	CCPR1L = 0 ;//8 last bits of Duty Cycle
	CLRF	_CCPR1L
;	.line	53; "tmr2_debug.c"	PIR1bits.TMR2IF = 0 ; //Clear Interrupt Flag
	BANKSEL	_PIR1bits
	BCF	_PIR1bits,1
;	.line	54; "tmr2_debug.c"	T2CONbits.T2CKPS = 0 ; //TIMER2 prescaler=1
	MOVF	(_T2CONbits + 0),W
	ANDLW	0xfc
	MOVWF	(_T2CONbits + 0)
;	.line	55; "tmr2_debug.c"	T2CONbits.TMR2ON = 1 ; //TIMER2 ON
	BSF	_T2CONbits,2
_00106_DS_:
;	.line	60; "tmr2_debug.c"	goto arxi;
	GOTO	_00106_DS_
;	.line	61; "tmr2_debug.c"	}
	RETURN	
; exit point of _main


;	code size estimation:
;	   49+   15 =    64 instructions (  158 byte)

	end

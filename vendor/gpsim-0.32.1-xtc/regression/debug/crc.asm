;--------------------------------------------------------
; File Created by SDCC : free open source ANSI-C Compiler
; Version 4.1.0 #12072 (Linux)
;--------------------------------------------------------
; PIC port for the 14-bit core
;--------------------------------------------------------
;	.file	"crc.c"
	list	p=16f1614
	radix dec
	include "p16f1614.inc"
;--------------------------------------------------------
; external declarations
;--------------------------------------------------------
	extern	_WREG
	extern	__sdcc_gsinit_startup
;--------------------------------------------------------
; global declarations
;--------------------------------------------------------
	global	_main
	global	_i
	global	_data

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
UD_crc_0	udata
_i	res	1

;--------------------------------------------------------
; absolute symbol definitions
;--------------------------------------------------------
;--------------------------------------------------------
; compiler-defined variables
;--------------------------------------------------------
UDL_crc_0	udata
r0x1007	res	1
r0x1008	res	1
;--------------------------------------------------------
; initialized data
;--------------------------------------------------------

IDD_crc_0	idata
_data
	db	0x55	; 85	'U'
	db	0x66	; 102	'f'
	db	0x77	; 119	'w'
	db	0x88	; 136
	db	0x00	; 0
	db	0x00	; 0

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
code_crc	code
;***
;  pBlock Stats: dbName = M
;***
;has an exit
;2 compiler assigned registers:
;   r0x1007
;   r0x1008
;; Starting pCode block
S_crc__main	code
_main:
; 2 exit points
;	.line	14; "crc.c"	for (i = 1; i <3; i++)
	MOVLW	0x01
	BANKSEL	_i
	MOVWF	_i
_00107_DS_:
;	.line	15; "crc.c"	WREG = data[i];
	BANKSEL	_i
	MOVF	_i,W
	ADDLW	(_data + 0)
	BANKSEL	r0x1007
	MOVWF	r0x1007
	MOVLW	high (_data + 0)
	BTFSC	STATUS,0
	ADDLW	0x01
	MOVWF	r0x1008
	MOVF	r0x1007,W
	MOVWF	FSR0L
	MOVF	r0x1008,W
	MOVWF	FSR0H
	MOVF	INDF0,W
	BANKSEL	_WREG
	MOVWF	_WREG
;	.line	14; "crc.c"	for (i = 1; i <3; i++)
	BANKSEL	_i
	INCF	_i,F
;;unsigned compare: left < lit(0x3=3), size=1
	MOVLW	0x03
	SUBWF	_i,W
	BTFSS	STATUS,0
	GOTO	_00107_DS_
;;genSkipc:3307: created from rifx:0x7ffe88b9ada0
;	.line	16; "crc.c"	}
	RETURN	
; exit point of _main


;	code size estimation:
;	   21+    5 =    26 instructions (   62 byte)

	end

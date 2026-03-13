;--------------------------------------------------------
; File Created by SDCC : free open source ANSI-C Compiler
; Version 4.1.0 #12072 (Linux)
;--------------------------------------------------------
; PIC port for the 14-bit core
;--------------------------------------------------------
;	.file	"idata.c"
	list	p=12f1822
	radix dec
	include "p12f1822.inc"
;--------------------------------------------------------
; global declarations
;--------------------------------------------------------
	global	__sdcc_gsinit_startup
	EXTERN	_main

rrr	code
__sdcc_gsinit_startup:
	PAGESEL	_main
	GOTO	_main
	

	end

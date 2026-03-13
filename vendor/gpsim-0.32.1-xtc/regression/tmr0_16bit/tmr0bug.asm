	list	p=18F2455
	include p18f2455.inc
        radix   decimal
;Program Configuration Register 1H
;        __CONFIG    _CONFIG1H, _OSCS_OFF_1H & _HSPLL_OSC_1H
;Program Configuration Register 2L
;        __CONFIG    _CONFIG2L, _BOR_OFF_2L & _PWRT_ON_2L
;Program Configuration Register 2H
;         __CONFIG    _CONFIG2H, _WDT_OFF_2H
	cblock	0x20
	counth,countl	;for timer0 interrupt counter
	msecsh,msecsl
	seconds
	tmps,tmp10
	wsave
	ssave
	endc
;onecycle	equ	256-10000/128		;time for 1msec
onecycle	equ	0x78
        org     0
        goto    main
	org	8
	goto	highpint
	org	18
	retfie
highpint:
        movwf   wsave           ;save WREG
        swapf   STATUS,w        ;save STATUS
        movwf   ssave
	movlw	0xff
	movlw	0xec		;rrr
	movwf	TMR0H
	movlw	onecycle
        movwf   TMR0L		;re-initialize the timer for next time
	decf	msecsl,f
	bnz	skip0
	movf	msecsh,w
	btfsc	STATUS,Z
	goto	resetms
	decf	msecsh,f	;rrr changed w to f
	goto	skip0
resetms:
	movlw	1000&255
	movwf	msecsl
	movlw	1000>>8
	movwf	msecsh
	incf	seconds,f
skip0:
        bcf     INTCON,T0IF     ;re-enable interrupt
        swapf   ssave,w
        movwf   STATUS
        swapf   wsave,f
        swapf   wsave,w
        retfie
;
main:
	movlw	0x80	;tmr0on=1,t08bit=0,t0cs=0,t0se=-,psa=0,t0ps2=0,t0ps1=0,t0ps0=0
			;so timer0 will run at chip instruction frequency as a 16bit timer
	movwf	T0CON
	movlw	0xff
        movlw	0xec	; rrr`
	movwf	TMR0H
	movlw	onecycle
        movwf   TMR0L		;initialize the timer for 1 msec
	movlw	1000&255
	movwf	msecsl
	movlw	1000>>8
	movwf	msecsh
	clrf	seconds
        bcf     INTCON,T0IF     ;clear interrupt flag
        bsf     INTCON,T0IE     ;enable interrupt
        bsf     INTCON,GIE      ;enable interrupts
;
mainloop:
	goto	mainloop
	end

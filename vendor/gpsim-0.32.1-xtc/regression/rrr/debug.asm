       list            p=18F4550
        #include        p18f4550.inc
        org 0x0000
 
	goto 0x4000
;	goto decode
        clrf PCLATU
        movlw high decode
        movwf PCLATH
	movlw low decode
	movwf PCL
	nop
	org 0x0fe
	movlw 0x15
decode:
	movlw 0x10
	nop
	nop
	nop
	goto $
	org 0x4000
	nop
	nop
  end

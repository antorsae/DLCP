       list            p=18F4550
        #include        p18f4550.inc
        org 0x0000
	goto start

	org 0x100
start:
;	movf PCL,W
	movlw 0x0f
	incf  PCL,W
	addwf PCL,F
	nop
 
        clrf PCLATU
        movlw high decode
        movwf PCLATH
	movlw low decode
	movwf PCL
	nop
decode:
	nop
	nop
	nop
  end

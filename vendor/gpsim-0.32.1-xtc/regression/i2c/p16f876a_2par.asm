;
; Test reading, writing, to i2c2par module
; 
; Copyright (c) 2017 Roy Rankin
; MACROS and some code included the following
;************************************************************************
;*	Microchip Technology Inc. 2006
;*	02/15/06
;*	Designed to run at 20MHz
;************************************************************************
; gpsim command
.command macro x
  .direct "C", x
  endm



	list		p=16F876A
	#include	p16f876a.inc
        include <coff.inc>

#define I2C_ADD 0x1f	; 31

	__CONFIG _CP_OFF & _DEBUG_OFF & _WRT_OFF & _CPD_OFF  & _LVP_OFF  & _PWRTE_ON & _BODEN_ON & _WDT_OFF & _HS_OSC

	errorlevel	-302


variables	UDATA 0x30
temp1           RES     1
temp2           RES     1
write_flag      RES     1

 global write_flag

STARTUP CODE
	NOP
	goto	start
	NOP
	NOP
	NOP
PROG1 	CODE

;
start	
   .sim "break c 0x100000"
   .sim "module lib libgpsim_modules"
   .sim "module load i2c2par i2c"
   .sim "i2c.Slave_Address = 31"
   .sim "module load pu pu1"
   .sim "module load pu pu2"
   .sim "node n1"
   .sim "attach n1 portc4 portc5 pu1.pin i2c.SDA" ; SDA
   .sim "node n2"
   .sim "attach n2 portc3 portc2 pu2.pin i2c.SCL" ; SCL
   .sim "node n3"
   .sim "attach n3 portb0 i2c.p0"
   .sim "node n4"
   .sim "attach n4 portb1 i2c.p1"
   .sim "node n5"
   .sim "attach n5 portb2 i2c.p2"
   .sim "node n6"
   .sim "attach n6 portb3 i2c.p3"
   .sim "node n7"
   .sim "attach n7 portb4 i2c.p4"
   .sim "node n8"
   .sim "attach n8 portb5 i2c.p5"
   .sim "node n9"
   .sim "attach n9 portb6 i2c.p6"
   .sim "node n10"
   .sim "attach n10 portb7 i2c.p7"
   .sim "scope.ch0 = \"portc3\""
   .sim "scope.ch1 = \"portc4\""
   .sim "pu1.xpos = 240."
   .sim "pu1.ypos = 336."
   .sim "pu2.xpos = 216."
   .sim "pu2.ypos = 24."
   .sim "i2c.xpos = 48."
   .sim "i2c.ypos = 180."
   .sim "p16f876a.xpos = 240."
   .sim "p16f876a.ypos = 84."




	call	ProgInit		; Get everything running step-by-step
        call	I2CSendResult
	call	read_i2c2par
	call	write_i2c2par
	call	is_ready
	call	read_i2c2par

  .assert "\"*** PASSED p16f876a I2C2PAR test\""
	goto $






;****************************** SUBROUTINES  ****************************
;************************************************************************

START_I2C	MACRO
	banksel	SSPCON2			; Generate I2C start
	bsf	SSPCON2,SEN
	btfsc	SSPCON2,SEN
	goto	$-1	
	banksel PORTA
	ENDM

RSTART_I2C	MACRO
	banksel	SSPCON2			; Generate I2C repeat start
	bsf	SSPCON2,RSEN
	btfsc	SSPCON2,RSEN
	goto	$-1	
	banksel PORTA
	ENDM

STOP_I2C	MACRO
	banksel	SSPCON2			; Generate I2C stop
	bsf	SSPCON2,PEN
	btfsc	SSPCON2,PEN
	goto	$-1	
	banksel PORTA
	ENDM

IDLE_WAIT_I2C	MACRO
	banksel SSPCON2
	movlw	0x1f
	andwf	SSPCON2,W
	BNZ	$-3
	btfsc	SSPSTAT,R_W
	goto	$-1
	banksel PORTA
	ENDM




;****************** Initialize Registers and Variables  *****************
;************************************************************************
ProgInit

	banksel	PORTA
	clrf	PORTA			; Set all bits to zero on Port A
	movlw	0x55
	movwf	PORTB
	banksel TRISA
	clrf	TRISA
	clrf	TRISB
	


	banksel	SSPADD
	movlw	0x0C			; Set I2C baud rate to 385 kHz
	movwf	SSPADD
	banksel	SSPCON
	movlw	0x08			; Set for I2C master mode
	movwf	SSPCON
	movlw	0x28			; Enable I2C
	movwf	SSPCON
	

	return





;************************************************************************
I2CSendResult
	banksel	SSPCON2			; Generate I2C restart
	bsf	SSPCON2,RSEN
	btfsc	SSPCON2,RSEN
	goto	$-1	

	banksel	SSPCON2			; Generate I2C stop
	bsf	SSPCON2,PEN
	btfsc	SSPCON2,PEN
	goto	$-1	

	bsf	SSPCON2,SEN	       ; Start
	bcf	TRISC,2			; cause collision
	IDLE_WAIT_I2C
   .assert  "(pir2 & 0x08) == 0x08, \"*** FAILED BCLIF for start\""
	nop
	banksel TRISC
	bsf	TRISC,2			; clear collision
	banksel PIR2
	bcf	PIR2,BCLIF

	banksel	SSPCON2			; Generate I2C start
	bsf	SSPCON2,SEN
	IDLE_WAIT_I2C

  .assert "(portc & 0x18) == 0, \"*** FAILED Start SCL, SDL low\""
	nop
  .assert "(pir1 & 0x08) == 0x08, \"*** FAILED Start SSPIF set\""
	nop
  .assert "(pir2 & 0x08) == 0x00, \"*** FAILED Start BCLIF clear\""
	nop
  .assert "(sspstat & 0x3f) == 0x08, \"*** FAILED Start S bit set\""
	nop

	banksel PIR1
	bcf	PIR1,SSPIF

	banksel	SSPCON2			; Generate I2C restart
	bsf	SSPCON2,RSEN
	btfsc	SSPCON2,RSEN
	goto	$-1	

  .assert "(portc & 0x18) == 0, \"*** FAILED RStart SCL, SDL low\""
	nop
  .assert "(pir1 & 0x08) == 0x08, \"*** FAILED RStart SSPIF set\""
	nop
  .assert "(pir2 & 0x08) == 0x00, \"*** FAILED RStart BCLIF clear\""
	nop
  .assert "(sspstat & 0x3f) == 0x08, \"*** FAILED RStart S bit set\""
	nop

	banksel PIR1
	bcf	PIR1,SSPIF

	banksel SSPCON2
	bsf	SSPCON2,ACKDT			; send NACK
	bsf	SSPCON2,ACKEN
	btfsc	SSPCON2,ACKEN
	goto	$-1	
  .assert "(portc & 0x18) == 0x10, \"*** FAILED ACKEN SCL low, SDL high\""
	nop
  .assert "(pir1 & 0x08) == 0x08, \"*** FAILED ACKEN SSPIF set\""
	nop
  .assert "(pir2 & 0x08) == 0x00, \"*** FAILED ACKEN BCLIF clear\""
	nop
  .assert "(sspstat & 0x3f) == 0x08, \"*** FAILED ACKEN S bit set\""
	nop
	bcf	SSPCON2,ACKDT

	bsf	SSPCON2,PEN			; send STOP
	btfsc	SSPCON2,PEN
	goto	$-1	

	banksel PIR1
	bcf	PIR1,SSPIF

	banksel	SSPCON2				; Generate I2C restart
	bsf	SSPCON2,RSEN
	btfsc	SSPCON2,RSEN
	goto	$-1	

  .assert "(portc & 0x18) == 0, \"*** FAILED RStart SCL, SDL low\""
	nop
  .assert "(pir1 & 0x08) == 0x08, \"*** FAILED RStart SSPIF set\""
	nop
  .assert "(pir2 & 0x08) == 0x00, \"*** FAILED RStart BCLIF clear\""
	nop
  .assert "(sspstat & 0x3f) == 0x08, \"*** FAILED RStart S bit set\""
	nop

	banksel PIR1
	bcf	PIR1,SSPIF

	banksel	SSPCON2			; Generate I2C stop
	bsf	SSPCON2,PEN
	btfsc	SSPCON2,PEN
	goto	$-1	

  .assert "(portc & 0x18) == 0x18, \"*** FAILED Stop SCL, SDL high\""
	nop
  .assert "(pir1 & 0x08) == 0x08, \"*** FAILED Stop SSPIF set\""
	nop
  .assert "(pir2 & 0x08) == 0x00, \"*** FAILED Stop BCLIF clear\""
	nop
  .assert "(sspstat & 0x3f) == 0x10, \"*** FAILED Stop P bit set\""
	nop
	return
;
;	repeatedly send command to eeprom until an ACK
;	is received back
;
;
is_ready
	banksel SSPCON
	movlw	0x04
	movwf	temp2
	clrf	temp1
	banksel	SSPCON2		; Generate I2C start
	bsf	SSPCON2,SEN
	btfsc	SSPCON2,SEN
	goto	$-1	
	movlw	(I2C_ADD<<1)		; write command to i2c2par
	call	I2C_send_w
	call I2C_stop
	banksel	SSPCON2			; Generate I2C start
	btfsc	SSPCON2,ACKSTAT
	goto	is_ready
	banksel PIR2
	bcf	PIR2,BCLIF
	return
	
send_i2c2par_address
	BANKSEL PIR1
	clrf	PIR1
	banksel	SSPCON2			; Generate I2C start
	bsf	SSPCON2,SEN
	btfsc	SSPCON2,SEN
	goto	$-1	
	movlw	(I2C_ADD<<1)		; slave add bits 1-7
	banksel write_flag
	btfss   write_flag,0
	addlw	1		        ; add bit 0 for read
	call	I2C_send_w
  .assert "(sspcon2 & 0x40) == 0x00, \"*** FAILED write command to i2c2par ACK\""
	nop
  .assert "(sspstat & 0x01) == 0x00, \"*** FAILED write to i2c2par BF clear\""
	nop
	return

write_i2c2par
	BANKSEL TRISB
	movlw	0xff
	movwf	TRISB
	banksel write_flag
	bsf	write_flag,0
;	banksel	SSPCON2		; Generate I2C start
;	bsf	SSPCON2,SEN
;	btfsc	SSPCON2,SEN
;	goto	$-1	
	call 	send_i2c2par_address
	banksel PIR1
	bcf	PIR1,SSPIF
	movlw	0x80		; write data1
	call	I2C_send_w
  .assert "(sspcon2 & 0x40) == 0x00, \"*** FAILED write data1 to eeprom ACK\""
	nop
  .assert "portb ==0x80, \"*** FAILED p16f876a_2par output data1\""
	nop

	banksel PIR1
	bcf	PIR1,SSPIF
	movlw	0x81		; write data2
	call	I2C_send_w
  .assert "(sspcon2 & 0x40) == 0x00, \"*** FAILED write data2 to eeprom ACK\""
	nop
  .assert "portb ==0x81, \"*** FAILED p16f876a_2par output data2\""
	nop
	nop
	call I2C_stop
	return


read_i2c2par

	banksel	PORTB
	movlw	0x55
	movwf	PORTB
	banksel TRISB
	clrf	TRISB
;	banksel	SSPCON2		; Generate I2C start
;	bsf	SSPCON2,SEN
;	btfsc	SSPCON2,SEN
;	goto	$-1	
	banksel PIR1
	bcf	PIR1,SSPIF
	bcf	PIR2,BCLIF
	banksel write_flag
	bcf	write_flag,0
	call 	send_i2c2par_address

	banksel	SSPCON2
	bsf	SSPCON2,RCEN	; read data from i2c2par
	btfsc	SSPCON2,RCEN
	goto	$-1	
  .assert "(pir1 & 0x08) == 0x08, \"FAILED RCEN SSPIF set\""
	nop
  .assert "(pir2 & 0x08) == 0x00, \"FAILED RCEN BCLIF clear\""
	nop
  .assert "(sspstat & 0x01) == 0x01, \"FAILED RCEN BF set\""
	nop
	banksel SSPBUF
	movf	SSPBUF,W
  .assert "W == 0x55, \"FAILED RCEN, read Data\""
	nop
  
	banksel PIR1
	bcf	PIR1,SSPIF

	banksel	SSPCON2
	bsf	SSPCON2,ACKDT	; send NACK
	bsf	SSPCON2,ACKEN
	btfsc	SSPCON2,ACKEN
	goto	$-1	

	call	I2C_stop

	return

I2C_stop
	banksel	SSPCON2			; Generate I2C stop
	bsf	SSPCON2,PEN
	btfsc	SSPCON2,PEN
	goto	$-1	
	return
	
delay
        decfsz  temp1,f
         goto   $+2
        decfsz  temp2,f
         goto   delay
        return

;********************** Output byte in W via I2C bus ********************
;************************************************************************
I2C_send_w
	banksel	SSPBUF			; Second byte of data
	movwf	SSPBUF
	banksel	SSPSTAT
	btfsc	SSPSTAT,R_W
	goto	$-1

	return
	




	end	

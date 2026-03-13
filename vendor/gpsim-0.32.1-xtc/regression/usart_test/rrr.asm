   ;;  USART test 
   ;;
   ;;  The purpose of this program is to verify that gpsim's
   ;; USART functions properly. The USART module is used to loop
   ;; characters back to the receiver testing  RCIF interupts.
   ;;
   ;;
   ;;

	list	p=16f88
	include <p16f88.inc>
	include <coff.inc>
        __CONFIG _WDT_OFF


.command macro x
  .direct "C", x
  endm

        errorlevel -302 
	radix dec
MAIN    CODE
	;; Now Transmit some data and verify that it is transmitted correctly.
   .command "U1.tx = \"Hi!\r\n\""
	nop
	end

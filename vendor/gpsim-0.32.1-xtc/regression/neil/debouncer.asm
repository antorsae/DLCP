 list p=16f690
;;;; generated code for PIC header file
#include <p16f690.inc>
;;;; generated code for gpsim header file
#include <coff.inc>

;;;; generated code for variables
GLOBAL_VAR_UDATA udata
DISPLAY res 1

;;;;;; VIC_VAR_DEBOUNCE VARIABLES ;;;;;;;

VIC_VAR_DEBOUNCE_VAR_IDATA idata
;; initialize state to 1
VIC_VAR_DEBOUNCESTATE db 0x01
;; initialize counter to 0
VIC_VAR_DEBOUNCECOUNTER db 0x00
    global VIC_VAR_DEBOUNCECOUNTER



;;;;;; DELAY FUNCTIONS ;;;;;;;

VIC_VAR_DELAY_UDATA udata
VIC_VAR_DELAY   res 3



;;;; generated code for macros
;; 1MHz => 1us per instruction
;; each loop iteration is 3us each
;; there are 2 loops, one for (768 + 3) us
;; and one for the rest in ms
;; we add 3 instructions for the outer loop
;; number of outermost loops = msecs * 1000 / 771 = msecs * 13 / 10
m_delay_ms macro msecs
    local _delay_msecs_loop_0, _delay_msecs_loop_1
    variable msecs_1 = 0
msecs_1 = (msecs * D'13') / D'10'
    movlw   msecs_1
    movwf   VIC_VAR_DELAY + 1
_delay_msecs_loop_1:
    clrf   VIC_VAR_DELAY   ;; set to 0 which gets decremented to 0xFF
_delay_msecs_loop_0:
    decfsz  VIC_VAR_DELAY, F
    goto    _delay_msecs_loop_0
    decfsz  VIC_VAR_DELAY + 1, F
    goto    _delay_msecs_loop_1
    endm



	__config (_INTRC_OSC_NOCLKOUT & _WDT_OFF & _PWRTE_OFF & _MCLRE_OFF & _CP_OFF & _BOR_OFF & _IESO_OFF & _FCMEN_OFF)



	org 0

;;;; generated common code for the Simulator
	.sim "module library libgpsim_modules"
	.sim "p16f690.xpos = 200";
	.sim "p16f690.ypos = 200";
    .sim "p16f690.BreakOnReset = true"
    .sim "p16f690.SafeMode = true"
    .sim "p16f690.UnknownMode = true"
    .sim "p16f690.WarnMode = true"

;;;; generated code for Simulator
	.sim "module load led L0"
	.sim "L0.xpos = 400"
	.sim "L0.ypos = 50"
	.sim "node portc0led"
	.sim "attach portc0led portc0 L0.in"
	.sim "module load led L1"
	.sim "L1.xpos = 400"
	.sim "L1.ypos = 100"
	.sim "node portc1led"
	.sim "attach portc1led portc1 L1.in"
	.sim "module load led L2"
	.sim "L2.xpos = 400"
	.sim "L2.ypos = 150"
	.sim "node portc2led"
	.sim "attach portc2led portc2 L2.in"
	.sim "module load led L3"
	.sim "L3.xpos = 400"
	.sim "L3.ypos = 200"
	.sim "node portc3led"
	.sim "attach portc3led portc3 L3.in"

	.sim "log on debouncer.lxt"

	.sim "log r porta"
	.sim "log w porta"
    .sim "scope.ch0 = \"porta3\""
    ;;; create a stimulus to simulate a switch
    .sim "echo stimulus for switch"
    .sim "stimulus asynchronous_stimulus"
    .sim "initial_state 0"
    .sim "start_cycle 100"
    .sim "digital"
   ; .sim "period 1000"
    .sim "period 10000"
  ;  .sim "{ 300, 1, 400, 0, 420, 1, 500, 0, 520, 1, 600, 0 }"; 620, 1, 700, 0, 720, 1, 800, 0, 820, 1, 900, 0 }"
    .sim "{ 300, 1, 400, 0, 420, 1, 500, 0, 520, 1, 600, 0 , 620, 1, 700, 0, 720, 1, 800, 0, 820, 1, 900, 0 }"
    .sim "name switch_stim"
    .sim "end"
    .sim "echo end stimulus for switch"
    .sim "node sw0ra3"
    .sim "attach sw0ra3 switch_stim porta3"
    .sim "break c 100000000"


;;;; generated code for Main
_start:

    ;; set led pins as output
	banksel TRISC
	clrf TRISC
	banksel ANSEL
	movlw 0x0F
	andwf ANSEL, F
	clrf ANSEL
	banksel ANSELH
	movlw 0xFC
	andwf ANSELH, F
	clrf  ANSELH

	banksel PORTC
	clrf PORTC
    ;; set pin RA3 as input
	banksel TRISA
	bcf TRISA, TRISA3
;	bcf TRISA, 3
	bcf TRISA,0
	banksel PORTA

	;; moves 0 (0x00) to DISPLAY
	clrf DISPLAY

;;;; generated code for Loop1
_loop_1:

	;;; generate code for debounce A<3>
	call _delay_1ms

	btfss PORTA,3
	bcf	PORTA,0
	btfsc	PORTA,3
	bsf	PORTA,0
	;; has debounce state changed to down (bit 0 is 0)
	;; if yes go to debounce-state-down
	btfsc   VIC_VAR_DEBOUNCESTATE, 0
	goto    _debounce_state_up
_debounce_state_down:
	clrw
	btfss   PORTA, 3
	;; increment and move into counter
	incf    VIC_VAR_DEBOUNCECOUNTER, 0
	movwf   VIC_VAR_DEBOUNCECOUNTER
	goto    _debounce_state_check

_debounce_state_up:
	clrw
	btfsc   PORTA, 3
	incf    VIC_VAR_DEBOUNCECOUNTER, 0
	movwf   VIC_VAR_DEBOUNCECOUNTER
	goto    _debounce_state_check

_debounce_state_check:
	movf    VIC_VAR_DEBOUNCECOUNTER, W
	xorlw   0x02
	;; is counter == 0x05 ?
	btfss   STATUS, Z
	goto    _end_action_2
	;; after 0x05 straight, flip direction
	comf    VIC_VAR_DEBOUNCESTATE, 1
	clrf    VIC_VAR_DEBOUNCECOUNTER
	;; was it a key-down
	btfss   VIC_VAR_DEBOUNCESTATE, 0
	goto    _end_action_2
	goto    _action_2
_end_action_2:


	goto _loop_1 ;;;; end of _loop_1

_end_loop_1:

_end_start:

	goto $	;;;; end of Main

;;;; generated code for functions
;;;; generated code for Action2
_action_2:

	;; increments DISPLAY in place
	;; increment byte[0]
	incf DISPLAY, F

	;; moving DISPLAY to PORTC
	movf DISPLAY, W
	movwf PORTC

	goto _end_action_2 ;; go back to end of block

;;;; end of _action_2
_delay_1ms:
	m_delay_ms D'1'
	return


;;;; generated code for end-of-file
	end

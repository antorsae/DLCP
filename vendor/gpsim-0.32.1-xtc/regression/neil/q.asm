    list    p=16f690

  include <p16f690.inc>


GLOBAL_VAR_UDATA udata ;; uninitialized data
VAR1 res 1
VAR2 res 1

 GLOBAL VAR1, VAR2

    __config (_WDT_OFF & _MCLRE_OFF & _BOR_OFF)

    org 0

_start:
;;;; let's just add two numbers
    movlw 0x39
    movwf VAR1
    movlw 0x71
    addwf  VAR1, W   ;; now W has 0xAA
    movwf VAR2       

    goto $

    end


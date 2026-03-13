; compiler: jal jalv24q2 (compiled Jan 23 2014)

; command line:  /home/neil/JALv2/bin/jalv2 -s /home/neil/projects/3D_firmware/axis_controller/;/home/neil/JALv2/jallib/lib/ main.jal
                                list p=18f4520, r=dec
                                errorlevel -306 ; no page boundary warnings
                                errorlevel -302 ; no bank 0 warnings
                                errorlevel -202 ; no 'argument out of range' warnings

                             __config 0x00300000, 0x00
                             __config 0x00300001, 0x07
                             __config 0x00300002, 0x1f
                             __config 0x00300003, 0x1f
                             __config 0x00300004, 0x00
                             __config 0x00300005, 0x83
                             __config 0x00300006, 0x85
                             __config 0x00300007, 0x00
                             __config 0x00300008, 0x0f
                             __config 0x00300009, 0xc0
                             __config 0x0030000a, 0x0f
                             __config 0x0030000b, 0xe0
                             __config 0x0030000c, 0x0f
                             __config 0x0030000d, 0x40
v_latb                         EQU 0x0f8a  ; latb
v_latc                         EQU 0x0f8b  ; latc
v_latd                         EQU 0x0f8c  ; latd
v_late                         EQU 0x0f8d  ; late
v_trisa                        EQU 0x0f92  ; trisa
v_trisb                        EQU 0x0f93  ; trisb
v_trisc                        EQU 0x0f94  ; trisc
v_trisd                        EQU 0x0f95  ; trisd
v_trise                        EQU 0x0f96  ; trise
v_cmcon                        EQU 0x0fb4  ; cmcon
v_adcon2                       EQU 0x0fc0  ; adcon2
v_adcon1                       EQU 0x0fc1  ; adcon1
v_adcon0                       EQU 0x0fc2  ; adcon0
v__banked                      EQU 1
v__access                      EQU 0
v___x_124                      EQU 0x0f8a  ; x-->latb
v___x_125                      EQU 0x0f8b  ; x-->latc
v___x_126                      EQU 0x0f8c  ; x-->latd
v___x_127                      EQU 0x0f8d  ; x-->late
;    5 include global_configuration
                               org      0
l__main
;   17 initialise_io()
; /home/neil/JALv2/jallib/lib/18f4520.jal
; 1309    ADCON0 = 0b0000_0000         -- disable ADC
                               clrf     v_adcon0,v__access
; 1310    ADCON1 = 0b0000_1111
                               movlw    15
                               movwf    v_adcon1,v__access
; 1311    ADCON2 = 0b0000_0000
                               clrf     v_adcon2,v__access
; main.jal
;   17 initialise_io()
; /home/neil/JALv2/jallib/lib/18f4520.jal
; 1325    adc_off()
; main.jal
;   17 initialise_io()
; /home/neil/JALv2/jallib/lib/18f4520.jal
; 1318    CMCON  = 0b0000_0111        -- disable comparator
                               movlw    7
                               movwf    v_cmcon,v__access
; main.jal
;   17 initialise_io()
; /home/neil/JALv2/jallib/lib/18f4520.jal
; 1326    comparator_off()
; main.jal
;   17 initialise_io()
; hardware_library.jal
;    9    enable_digital_io()
;   10    PORTA_direction = 0b1111_1111
                               movlw    255
                               movwf    v_trisa,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   11    PORTB           = 0b1111_0000
                               movlw    240
                               movwf    v___x_124,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   11    PORTB           = 0b1111_0000
;   12    PORTB_direction = 0b1111_0000
                               movlw    240
                               movwf    v_trisb,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   13    PORTC           = 0b1111_1000
                               movlw    248
                               movwf    v___x_125,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   13    PORTC           = 0b1111_1000
;   14    PORTC_direction = 0b1111_1000
                               movlw    248
                               movwf    v_trisc,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   15    PORTD           = 0b0000_0000
                               clrf     v___x_126,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   15    PORTD           = 0b0000_0000
;   16    PORTD_direction = 0b0000_0000
                               clrf     v_trisd,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   17    PORTE           = 0b1111_1000
                               movlw    248
                               movwf    v___x_127,v__access
; main.jal
;   17 initialise_io()
; hardware_library.jal
;   17    PORTE           = 0b1111_1000
;   18    PORTE_direction = 0b1111_1000
                               movlw    248
                               movwf    v_trise,v__access
; main.jal
;   17 initialise_io()
;   23 forever loop
l__l190
;   24 end loop
                               goto     l__l190
                               end

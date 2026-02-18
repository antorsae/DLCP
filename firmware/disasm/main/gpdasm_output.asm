
; The recognition of labels and registers is not always good, therefore
; be treated cautiously the results.

;===============================================================================
; DATA address definitions

Common_RAM      equ     0x000000                            ; size: 96 bytes
001000:  ef0a  goto    label_000                            ; dest: 0x001014
001002:  f008
001004:  ffff  dw      0xffff
001006:  ffff  dw      0xffff
001008:  cfd9  movff   FSR2L, (Common_RAM + 1)              ; reg1: 0xfd9, reg2: 0x001
00100a:  f001
00100c:  cfda  movff   FSR2H, (Common_RAM + 2)              ; reg1: 0xfda, reg2: 0x002
00100e:  f002
001010:  ed8f  call    function_049, 0x1                    ; dest: 0x003b1e
001012:  f01d

label_000:                                                  ; address: 0x001014

001014:  efa7  goto    label_494                            ; dest: 0x003d4e
001016:  f01e
001018:  3000  rrcf    Common_RAM, W, A                     ; reg: 0x000
00101a:  3231  rrcf    (Common_RAM + 49), F, A              ; reg: 0x031
00101c:  3433  rlcf    (Common_RAM + 51), W, A              ; reg: 0x033
00101e:  3635  rlcf    (Common_RAM + 53), F, A              ; reg: 0x035
001020:  3837  swapf   (Common_RAM + 55), W, A              ; reg: 0x037
001022:  4139  rrncf   (Common_RAM + 57), W, B              ; reg: 0x039
001024:  4342  rrncf   (Common_RAM + 66), F, B              ; reg: 0x042
001026:  4544  rlncf   (Common_RAM + 68), W, B              ; reg: 0x044
001028:  a646  btfss   (Common_RAM + 70), 0x3, A            ; reg: 0x046
00102a:  9a72  bcf     UEP2, 0x5, A                         ; reg: 0xf72
00102c:  0209  mulwf   (Common_RAM + 9), A                  ; reg: 0x009
00102e:  0029  dw      0x0029                               ; ')'
001030:  0101  movlb   0x1
001032:  8000  bsf     0x00, 0x0, A                         ; reg: 0x100
001034:  0932  iorlw   0x32
001036:  0004  clrwdt
001038:  0200  mulwf   0x00, A                              ; reg: 0x100
00103a:  0003  sleep
00103c:  0000  nop
00103e:  2109  addwfc  0x09, W, B                           ; reg: 0x109
001040:  0111  dw      0x0111
001042:  0100  movlb   0x0
001044:  1d22  comf    (Common_RAM + 34), W, B              ; reg: 0x022
001046:  0700  decf    Common_RAM, F, B                     ; reg: 0x000
001048:  8105  bsf     (Common_RAM + 5), 0x0, B             ; reg: 0x005
00104a:  4003  rrncf   (Common_RAM + 3), W, A               ; reg: 0x003
00104c:  0100  movlb   0x0
00104e:  0507  decf    (Common_RAM + 7), W, B               ; reg: 0x007
001050:  0301  mulwf   (Common_RAM + 1), B                  ; reg: 0x001
001052:  0040  dw      0x0040                               ; '@'
001054:  0601  decf    (Common_RAM + 1), F, A               ; reg: 0x001
001056:  ff00  dw      0xff00
001058:  0109  movlb   0x9
00105a:  01a1  dw      0x01a1
00105c:  0119  dw      0x0119
00105e:  4029  rrncf   0x29, W, A                           ; reg: 0x929
001060:  0015  dw      0x0015
001062:  ff26  dw      0xff26
001064:  7500  btg     0x00, 0x2, B                         ; reg: 0x900
001066:  9508  bcf     0x08, 0x2, B                         ; reg: 0x908
001068:  8140  bsf     0x40, 0x0, B                         ; reg: 0x940
00106a:  1900  xorwf   0x00, W, B                           ; reg: 0x900
00106c:  2901  incf    0x01, W, B                           ; reg: 0x901
00106e:  9140  bcf     0x40, 0x0, B                         ; reg: 0x940
001070:  c000  dw      0xc000
001072:  0316  mulwf   0x16, B                              ; reg: 0x916
001074:  0048  dw      0x0048                               ; 'H'
001076:  0079  dw      0x0079                               ; 'y'
001078:  0070  dw      0x0070                               ; 'p'
00107a:  0065  dw      0x0065                               ; 'e'
00107c:  0078  dw      0x0078                               ; 'x'
00107e:  0020  dw      0x0020                               ; ' '
001080:  0042  dw      0x0042                               ; 'B'
001082:  0056  dw      0x0056                               ; 'V'
001084:  0000  nop
001086:  0000  nop
001088:  0112  dw      0x0112
00108a:  0200  mulwf   0x00, A                              ; reg: 0x900
00108c:  0000  nop
00108e:  0800  sublw   0x00
001090:  04d8  decf    STATUS, W, A                         ; reg: 0xfd8
001092:  ff89  dw      0xff89
001094:  0001  halt
001096:  0201  mulwf   0x01, A                              ; reg: 0x901
001098:  0100  movlb   0x0
00109a:  030c  mulwf   (Common_RAM + 12), B                 ; reg: 0x00c
00109c:  0044  dw      0x0044                               ; 'D'
00109e:  004c  dw      0x004c                               ; 'L'
0010a0:  0043  dw      0x0043                               ; 'C'
0010a2:  0050  dw      0x0050                               ; 'P'
0010a4:  0000  nop
0010a6:  0304  mulwf   (Common_RAM + 4), B                  ; reg: 0x004
0010a8:  0409  decf    (Common_RAM + 9), W, A               ; reg: 0x009
0010aa:  0000  nop

function_000:                                               ; address: 0x0010ac

0010ac:  cfe8  movff   WREG, (Common_RAM + 87)              ; reg1: 0xfe8, reg2: 0x057
0010ae:  f057
0010b0:  ee21  lfsr    0x2, 0x1ed
0010b2:  f0ed
0010b4:  ee10  lfsr    0x1, 0x04d
0010b6:  f04d
0010b8:  0e07  movlw   0x07

label_001:                                                  ; address: 0x0010ba

0010ba:  cfde  movff   POSTINC2, POSTINC1                   ; reg1: 0xfde, reg2: 0xfe6
0010bc:  ffe6
0010be:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
0010c0:  d7fc  bra     label_001                            ; dest: 0x0010ba
0010c2:  5057  movf    (Common_RAM + 87), W, A              ; reg: 0x057
0010c4:  0a42  xorlw   0x42
0010c6:  e101  bnz     label_002
0010c8:  d244  bra     label_070                            ; dest: 0x001552

label_002:                                                  ; address: 0x0010ca

0010ca:  0100  movlb   0x0
0010cc:  6bcb  clrf    0xcb, B                              ; reg: 0x0cb
0010ce:  d241  bra     label_070                            ; dest: 0x001552

label_003:                                                  ; address: 0x0010d0

0010d0:  c11b  movff   0x11b, 0x097
0010d2:  f097
0010d4:  0100  movlb   0x0
0010d6:  5197  movf    0x97, W, B                           ; reg: 0x097
0010d8:  0a09  xorlw   0x09
0010da:  e114  bnz     label_007
0010dc:  0e02  movlw   0x02
0010de:  6e58  movwf   (Common_RAM + 88), A                 ; reg: 0x058

label_004:                                                  ; address: 0x0010e0

0010e0:  da67  rcall   function_001                         ; dest: 0x0015b0
0010e2:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0010e4:  e00a  bz      label_005
0010e6:  da64  rcall   function_001                         ; dest: 0x0015b0
0010e8:  0ebe  movlw   0xbe
0010ea:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
0010ec:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
0010ee:  6ae2  clrf    FSR1H, A                             ; reg: 0xfe2
0010f0:  0e02  movlw   0x02
0010f2:  22e2  addwfc  FSR1H, F, A                          ; reg: 0xfe2
0010f4:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
0010f6:  ffe7
0010f8:  d001  bra     label_006                            ; dest: 0x0010fc

label_005:                                                  ; address: 0x0010fa

0010fa:  da61  rcall   function_002                         ; dest: 0x0015be

label_006:                                                  ; address: 0x0010fc

0010fc:  2a58  incf    (Common_RAM + 88), F, A              ; reg: 0x058
0010fe:  0e1f  movlw   0x1f
001100:  6458  cpfsgt  (Common_RAM + 88), A                 ; reg: 0x058
001102:  d7ee  bra     label_004                            ; dest: 0x0010e0

label_007:                                                  ; address: 0x001104

001104:  0100  movlb   0x0
001106:  5197  movf    0x97, W, B                           ; reg: 0x097
001108:  0a0a  xorlw   0x0a
00110a:  e107  bnz     label_009
00110c:  0e02  movlw   0x02
00110e:  6e58  movwf   (Common_RAM + 88), A                 ; reg: 0x058

label_008:                                                  ; address: 0x001110

001110:  da56  rcall   function_002                         ; dest: 0x0015be
001112:  2a58  incf    (Common_RAM + 88), F, A              ; reg: 0x058
001114:  0e1f  movlw   0x1f
001116:  6458  cpfsgt  (Common_RAM + 88), A                 ; reg: 0x058
001118:  d7fb  bra     label_008                            ; dest: 0x001110

label_009:                                                  ; address: 0x00111a

00111a:  0e03  movlw   0x03
00111c:  0100  movlb   0x0
00111e:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001120:  c11b  movff   0x11b, 0x0c2
001122:  f0c2
001124:  8bbd  bsf     0xbd, 0x5, B                         ; reg: 0x0bd

label_010:                                                  ; address: 0x001126

001126:  ec53  call    function_112, 0x0                    ; dest: 0x0048a6
001128:  f024

label_011:                                                  ; address: 0x00112a

00112a:  ec97  call    function_120, 0x0                    ; dest: 0x00492e
00112c:  f024

label_012:                                                  ; address: 0x00112e

00112e:  ec94  call    function_009, 0x0                    ; dest: 0x002328
001130:  f011
001132:  d23b  bra     label_083                            ; dest: 0x0015aa

label_013:                                                  ; address: 0x001134

001134:  0101  movlb   0x1
001136:  051b  decf    0x1b, W, B                           ; reg: 0x11b
001138:  e118  bnz     label_017
00113a:  c11c  movff   0x11c, 0x0b7
00113c:  f0b7
00113e:  d00e  bra     label_016                            ; dest: 0x00115c

label_014:                                                  ; address: 0x001140

001140:  0e04  movlw   0x04
001142:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001144:  0e01  movlw   0x01
001146:  6fc2  movwf   0xc2, B                              ; reg: 0x0c2
001148:  d7f0  bra     label_011                            ; dest: 0x00112a

label_015:                                                  ; address: 0x00114a

00114a:  c11d  movff   0x11d, 0x0b8
00114c:  f0b8
00114e:  0e04  movlw   0x04
001150:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001152:  0e01  movlw   0x01
001154:  6fc2  movwf   0xc2, B                              ; reg: 0x0c2
001156:  817f  bsf     0x7f, 0x0, B                         ; reg: 0x07f
001158:  8994  bsf     0x94, 0x4, B                         ; reg: 0x094
00115a:  d7e7  bra     label_011                            ; dest: 0x00112a

label_016:                                                  ; address: 0x00115c

00115c:  0100  movlb   0x0
00115e:  51b7  movf    0xb7, W, B                           ; reg: 0x0b7
001160:  0a01  xorlw   0x01
001162:  e0ee  bz      label_014
001164:  0a03  xorlw   0x03
001166:  e0f1  bz      label_015
001168:  d220  bra     label_083                            ; dest: 0x0015aa

label_017:                                                  ; address: 0x00116a

00116a:  511b  movf    (Common_RAM + 27), W, B              ; reg: 0x01b
00116c:  0a02  xorlw   0x02
00116e:  e001  bz      label_018
001170:  d21c  bra     label_083                            ; dest: 0x0015aa

label_018:                                                  ; address: 0x001172

001172:  c11e  movff   0x11e, 0x0b5
001174:  f0b5
001176:  0e04  movlw   0x04
001178:  0100  movlb   0x0
00117a:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
00117c:  0e02  movlw   0x02
00117e:  6fc2  movwf   0xc2, B                              ; reg: 0x0c2
001180:  51b5  movf    0xb5, W, B                           ; reg: 0x0b5
001182:  0a06  xorlw   0x06
001184:  e11d  bnz     label_022
001186:  0e05  movlw   0x05
001188:  6e58  movwf   (Common_RAM + 88), A                 ; reg: 0x058

label_019:                                                  ; address: 0x00118a

00118a:  da12  rcall   function_001                         ; dest: 0x0015b0
00118c:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
00118e:  e00a  bz      label_020
001190:  da0f  rcall   function_001                         ; dest: 0x0015b0
001192:  0efb  movlw   0xfb
001194:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
001196:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
001198:  6ae2  clrf    FSR1H, A                             ; reg: 0xfe2
00119a:  0e00  movlw   0x00
00119c:  22e2  addwfc  FSR1H, F, A                          ; reg: 0xfe2
00119e:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
0011a0:  ffe7
0011a2:  d007  bra     label_021                            ; dest: 0x0011b2

label_020:                                                  ; address: 0x0011a4

0011a4:  0efb  movlw   0xfb
0011a6:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
0011a8:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0011aa:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0011ac:  0e00  movlw   0x00
0011ae:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0011b0:  68df  setf    INDF2, A                             ; reg: 0xfdf

label_021:                                                  ; address: 0x0011b2

0011b2:  2a58  incf    (Common_RAM + 88), F, A              ; reg: 0x058
0011b4:  0e13  movlw   0x13
0011b6:  6458  cpfsgt  (Common_RAM + 88), A                 ; reg: 0x058
0011b8:  d7e8  bra     label_019                            ; dest: 0x00118a
0011ba:  0100  movlb   0x0
0011bc:  89bd  bsf     0xbd, 0x4, B                         ; reg: 0x0bd
0011be:  d7b3  bra     label_010                            ; dest: 0x001126

label_022:                                                  ; address: 0x0011c0

0011c0:  51b5  movf    0xb5, W, B                           ; reg: 0x0b5
0011c2:  0a05  xorlw   0x05
0011c4:  e0b2  bz      label_011
0011c6:  51b5  movf    0xb5, W, B                           ; reg: 0x0b5
0011c8:  0a07  xorlw   0x07
0011ca:  e0af  bz      label_011
0011cc:  d1ee  bra     label_083                            ; dest: 0x0015aa

label_023:                                                  ; address: 0x0011ce

0011ce:  c11b  movff   0x11b, 0x099
0011d0:  f099
0011d2:  c11f  movff   0x11f, 0x071
0011d4:  f071
0011d6:  c120  movff   0x120, 0x070
0011d8:  f070
0011da:  c121  movff   0x121, 0x06f
0011dc:  f06f
0011de:  c122  movff   0x122, 0x06e
0011e0:  f06e
0011e2:  0101  movlb   0x1
0011e4:  b123  btfsc   0x23, 0x0, B                         ; reg: 0x123
0011e6:  d002  bra     label_024                            ; dest: 0x0011ec
0011e8:  985e  bcf     (Common_RAM + 94), 0x4, A            ; reg: 0x05e
0011ea:  d001  bra     label_025                            ; dest: 0x0011ee

label_024:                                                  ; address: 0x0011ec

0011ec:  885e  bsf     (Common_RAM + 94), 0x4, A            ; reg: 0x05e

label_025:                                                  ; address: 0x0011ee

0011ee:  0101  movlb   0x1
0011f0:  b124  btfsc   0x24, 0x0, B                         ; reg: 0x124
0011f2:  d003  bra     label_026                            ; dest: 0x0011fa
0011f4:  0100  movlb   0x0
0011f6:  91a4  bcf     0xa4, 0x0, B                         ; reg: 0x0a4
0011f8:  d002  bra     label_027                            ; dest: 0x0011fe

label_026:                                                  ; address: 0x0011fa

0011fa:  0100  movlb   0x0
0011fc:  81a4  bsf     0xa4, 0x0, B                         ; reg: 0x0a4

label_027:                                                  ; address: 0x0011fe

0011fe:  0101  movlb   0x1
001200:  b125  btfsc   0x25, 0x0, B                         ; reg: 0x125
001202:  d003  bra     label_028                            ; dest: 0x00120a
001204:  0100  movlb   0x0
001206:  93a4  bcf     0xa4, 0x1, B                         ; reg: 0x0a4
001208:  d002  bra     label_029                            ; dest: 0x00120e

label_028:                                                  ; address: 0x00120a

00120a:  0100  movlb   0x0
00120c:  83a4  bsf     0xa4, 0x1, B                         ; reg: 0x0a4

label_029:                                                  ; address: 0x00120e

00120e:  0101  movlb   0x1
001210:  b126  btfsc   0x26, 0x0, B                         ; reg: 0x126
001212:  d003  bra     label_030                            ; dest: 0x00121a
001214:  0100  movlb   0x0
001216:  95a4  bcf     0xa4, 0x2, B                         ; reg: 0x0a4
001218:  d002  bra     label_031                            ; dest: 0x00121e

label_030:                                                  ; address: 0x00121a

00121a:  0100  movlb   0x0
00121c:  85a4  bsf     0xa4, 0x2, B                         ; reg: 0x0a4

label_031:                                                  ; address: 0x00121e

00121e:  0101  movlb   0x1
001220:  b128  btfsc   0x28, 0x0, B                         ; reg: 0x128
001222:  d003  bra     label_032                            ; dest: 0x00122a
001224:  0100  movlb   0x0
001226:  97a4  bcf     0xa4, 0x3, B                         ; reg: 0x0a4
001228:  d002  bra     label_033                            ; dest: 0x00122e

label_032:                                                  ; address: 0x00122a

00122a:  0100  movlb   0x0
00122c:  87a4  bsf     0xa4, 0x3, B                         ; reg: 0x0a4

label_033:                                                  ; address: 0x00122e

00122e:  0101  movlb   0x1
001230:  b129  btfsc   0x29, 0x0, B                         ; reg: 0x129
001232:  d003  bra     label_034                            ; dest: 0x00123a
001234:  0100  movlb   0x0
001236:  99a4  bcf     0xa4, 0x4, B                         ; reg: 0x0a4
001238:  d002  bra     label_035                            ; dest: 0x00123e

label_034:                                                  ; address: 0x00123a

00123a:  0100  movlb   0x0
00123c:  89a4  bsf     0xa4, 0x4, B                         ; reg: 0x0a4

label_035:                                                  ; address: 0x00123e

00123e:  0101  movlb   0x1
001240:  b12a  btfsc   0x2a, 0x0, B                         ; reg: 0x12a
001242:  d003  bra     label_036                            ; dest: 0x00124a
001244:  0100  movlb   0x0
001246:  9ba4  bcf     0xa4, 0x5, B                         ; reg: 0x0a4
001248:  d002  bra     label_037                            ; dest: 0x00124e

label_036:                                                  ; address: 0x00124a

00124a:  0100  movlb   0x0
00124c:  8ba4  bsf     0xa4, 0x5, B                         ; reg: 0x0a4

label_037:                                                  ; address: 0x00124e

00124e:  c12c  movff   0x12c, 0x060
001250:  f060
001252:  c12d  movff   0x12d, 0x061
001254:  f061
001256:  c12e  movff   0x12e, 0x062
001258:  f062
00125a:  c12f  movff   0x12f, 0x063
00125c:  f063
00125e:  c130  movff   0x130, 0x064
001260:  f064
001262:  c131  movff   0x131, 0x065
001264:  f065
001266:  c132  movff   0x132, (Common_RAM + 95)             ; reg2: 0x05f
001268:  f05f
00126a:  c133  movff   0x133, 0x09b
00126c:  f09b
00126e:  c134  movff   0x134, 0x09c
001270:  f09c
001272:  c135  movff   0x135, 0x09d
001274:  f09d
001276:  c136  movff   0x136, 0x09e
001278:  f09e
00127a:  c138  movff   0x138, 0x0b4
00127c:  f0b4
00127e:  51b3  movf    0xb3, W, B                           ; reg: 0x0b3
001280:  1999  xorwf   0x99, W, B                           ; reg: 0x099
001282:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001284:  8194  bsf     0x94, 0x0, B                         ; reg: 0x094
001286:  5169  movf    0x69, W, B                           ; reg: 0x069
001288:  1971  xorwf   0x71, W, B                           ; reg: 0x071
00128a:  e108  bnz     label_038
00128c:  5168  movf    0x68, W, B                           ; reg: 0x068
00128e:  1970  xorwf   0x70, W, B                           ; reg: 0x070
001290:  e105  bnz     label_038
001292:  5167  movf    0x67, W, B                           ; reg: 0x067
001294:  196f  xorwf   0x6f, W, B                           ; reg: 0x06f
001296:  e102  bnz     label_038
001298:  5166  movf    0x66, W, B                           ; reg: 0x066
00129a:  196e  xorwf   0x6e, W, B                           ; reg: 0x06e

label_038:                                                  ; address: 0x00129c

00129c:  e002  bz      label_039
00129e:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
0012a0:  8394  bsf     0x94, 0x1, B                         ; reg: 0x094

label_039:                                                  ; address: 0x0012a2

0012a2:  51ac  movf    0xac, W, B                           ; reg: 0x0ac
0012a4:  199b  xorwf   0x9b, W, B                           ; reg: 0x09b
0012a6:  e002  bz      label_040
0012a8:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
0012aa:  87bd  bsf     0xbd, 0x3, B                         ; reg: 0x0bd

label_040:                                                  ; address: 0x0012ac

0012ac:  51ad  movf    0xad, W, B                           ; reg: 0x0ad
0012ae:  199c  xorwf   0x9c, W, B                           ; reg: 0x09c
0012b0:  e002  bz      label_041
0012b2:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
0012b4:  87bd  bsf     0xbd, 0x3, B                         ; reg: 0x0bd

label_041:                                                  ; address: 0x0012b6

0012b6:  51ae  movf    0xae, W, B                           ; reg: 0x0ae
0012b8:  199d  xorwf   0x9d, W, B                           ; reg: 0x09d
0012ba:  e002  bz      label_042
0012bc:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
0012be:  87bd  bsf     0xbd, 0x3, B                         ; reg: 0x0bd

label_042:                                                  ; address: 0x0012c0

0012c0:  51af  movf    0xaf, W, B                           ; reg: 0x0af
0012c2:  199e  xorwf   0x9e, W, B                           ; reg: 0x09e
0012c4:  e002  bz      label_043
0012c6:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
0012c8:  87bd  bsf     0xbd, 0x3, B                         ; reg: 0x0bd

label_043:                                                  ; address: 0x0012ca

0012ca:  0e01  movlw   0x01
0012cc:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
0012ce:  0e00  movlw   0x00
0012d0:  6e4c  movwf   (Common_RAM + 76), A                 ; reg: 0x04c
0012d2:  0e01  movlw   0x01
0012d4:  aa5e  btfss   (Common_RAM + 94), 0x5, A            ; reg: 0x05e
0012d6:  0e00  movlw   0x00
0012d8:  1a4c  xorwf   (Common_RAM + 76), F, A              ; reg: 0x04c
0012da:  e002  bz      label_044
0012dc:  8b7e  bsf     0x7e, 0x5, B                         ; reg: 0x07e
0012de:  8794  bsf     0x94, 0x3, B                         ; reg: 0x094

label_044:                                                  ; address: 0x0012e0

0012e0:  51b0  movf    0xb0, W, B                           ; reg: 0x0b0
0012e2:  19a4  xorwf   0xa4, W, B                           ; reg: 0x0a4
0012e4:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0012e6:  8d7e  bsf     0x7e, 0x6, B                         ; reg: 0x07e
0012e8:  51b4  movf    0xb4, W, B                           ; reg: 0x0b4
0012ea:  19b1  xorwf   0xb1, W, B                           ; reg: 0x0b1
0012ec:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0012ee:  837f  bsf     0x7f, 0x1, B                         ; reg: 0x07f
0012f0:  5160  movf    0x60, W, B                           ; reg: 0x060
0012f2:  63a5  cpfseq  0xa5, B                              ; reg: 0x0a5
0012f4:  d017  bra     label_045                            ; dest: 0x001324
0012f6:  51a6  movf    0xa6, W, B                           ; reg: 0x0a6
0012f8:  ee20  lfsr    0x2, 0x061
0012fa:  f061
0012fc:  62df  cpfseq  INDF2, A                             ; reg: 0xfdf
0012fe:  d012  bra     label_045                            ; dest: 0x001324
001300:  51a7  movf    0xa7, W, B                           ; reg: 0x0a7
001302:  ee20  lfsr    0x2, 0x062
001304:  f062
001306:  62df  cpfseq  INDF2, A                             ; reg: 0xfdf
001308:  d00d  bra     label_045                            ; dest: 0x001324
00130a:  51a8  movf    0xa8, W, B                           ; reg: 0x0a8
00130c:  ee20  lfsr    0x2, 0x063
00130e:  f063
001310:  62df  cpfseq  INDF2, A                             ; reg: 0xfdf
001312:  d008  bra     label_045                            ; dest: 0x001324
001314:  51a9  movf    0xa9, W, B                           ; reg: 0x0a9
001316:  ee20  lfsr    0x2, 0x064
001318:  f064
00131a:  62df  cpfseq  INDF2, A                             ; reg: 0xfdf
00131c:  d003  bra     label_045                            ; dest: 0x001324
00131e:  5165  movf    0x65, W, B                           ; reg: 0x065
001320:  19aa  xorwf   0xaa, W, B                           ; reg: 0x0aa
001322:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2

label_045:                                                  ; address: 0x001324

001324:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001326:  c099  movff   0x099, 0x0b3
001328:  f0b3
00132a:  c06e  movff   0x06e, 0x066
00132c:  f066
00132e:  c06f  movff   0x06f, 0x067
001330:  f067
001332:  c070  movff   0x070, 0x068
001334:  f068
001336:  c071  movff   0x071, 0x069
001338:  f069
00133a:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
00133c:  d002  bra     label_046                            ; dest: 0x001342
00133e:  8a5e  bsf     (Common_RAM + 94), 0x5, A            ; reg: 0x05e
001340:  d001  bra     label_047                            ; dest: 0x001344

label_046:                                                  ; address: 0x001342

001342:  9a5e  bcf     (Common_RAM + 94), 0x5, A            ; reg: 0x05e

label_047:                                                  ; address: 0x001344

001344:  c0a4  movff   0x0a4, 0x0b0
001346:  f0b0
001348:  c060  movff   0x060, 0x0a5
00134a:  f0a5
00134c:  c061  movff   0x061, 0x0a6
00134e:  f0a6
001350:  c062  movff   0x062, 0x0a7
001352:  f0a7
001354:  c063  movff   0x063, 0x0a8
001356:  f0a8
001358:  c064  movff   0x064, 0x0a9
00135a:  f0a9
00135c:  c065  movff   0x065, 0x0aa
00135e:  f0aa
001360:  c0b4  movff   0x0b4, 0x0b1
001362:  f0b1
001364:  c09b  movff   0x09b, 0x0ac
001366:  f0ac
001368:  c09c  movff   0x09c, 0x0ad
00136a:  f0ad
00136c:  c09d  movff   0x09d, 0x0ae
00136e:  f0ae
001370:  c09e  movff   0x09e, 0x0af
001372:  f0af

label_048:                                                  ; address: 0x001374

001374:  0e05  movlw   0x05
001376:  d006  bra     label_050                            ; dest: 0x001384

label_049:                                                  ; address: 0x001378

001378:  0101  movlb   0x1
00137a:  051b  decf    0x1b, W, B                           ; reg: 0x11b
00137c:  e106  bnz     label_051
00137e:  eca1  call    function_122, 0x0                    ; dest: 0x004942
001380:  f024
001382:  0e06  movlw   0x06

label_050:                                                  ; address: 0x001384

001384:  0100  movlb   0x0
001386:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001388:  d6d2  bra     label_012                            ; dest: 0x00112e

label_051:                                                  ; address: 0x00138a

00138a:  511b  movf    (Common_RAM + 27), W, B              ; reg: 0x01b
00138c:  0a02  xorlw   0x02
00138e:  e001  bz      label_052
001390:  d10c  bra     label_083                            ; dest: 0x0015aa

label_052:                                                  ; address: 0x001392

001392:  eca1  call    function_122, 0x0                    ; dest: 0x004942
001394:  f024
001396:  d7ee  bra     label_048                            ; dest: 0x001374

label_053:                                                  ; address: 0x001398

001398:  0101  movlb   0x1
00139a:  511b  movf    0x1b, W, B                           ; reg: 0x11b
00139c:  0a0f  xorlw   0x0f
00139e:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0013a0:  8e5e  bsf     0x5e, 0x7, A                         ; reg: 0x15e

label_054:                                                  ; address: 0x0013a2

0013a2:  5057  movf    (Common_RAM + 87), W, A              ; reg: 0x057
0013a4:  0a07  xorlw   0x07
0013a6:  e109  bnz     label_055
0013a8:  0101  movlb   0x1
0013aa:  671b  tstfsz  0x1b, B                              ; reg: 0x11b
0013ac:  d006  bra     label_055                            ; dest: 0x0013ba
0013ae:  0100  movlb   0x0
0013b0:  6bc5  clrf    0xc5, B                              ; reg: 0x0c5
0013b2:  0e56  movlw   0x56
0013b4:  6f83  movwf   0x83, B                              ; reg: 0x083
0013b6:  0e00  movlw   0x00
0013b8:  6b82  clrf    0x82, B                              ; reg: 0x082

label_055:                                                  ; address: 0x0013ba

0013ba:  98ab  bcf     RCSTA, CREN, A                       ; reg: 0xfab, bit: 4
0013bc:  805e  bsf     (Common_RAM + 94), 0x0, A            ; reg: 0x05e
0013be:  0100  movlb   0x0
0013c0:  6b98  clrf    0x98, B                              ; reg: 0x098
0013c2:  6bc7  clrf    0xc7, B                              ; reg: 0x0c7
0013c4:  6bc6  clrf    0xc6, B                              ; reg: 0x0c6
0013c6:  ecdc  call    function_021, 0x0                    ; dest: 0x002bb8
0013c8:  f015

label_056:                                                  ; address: 0x0013ca

0013ca:  c057  movff   (Common_RAM + 87), 0x0c1             ; reg1: 0x057
0013cc:  f0c1
0013ce:  d6af  bra     label_012                            ; dest: 0x00112e

label_057:                                                  ; address: 0x0013d0

0013d0:  0ea0  movlw   0xa0
0013d2:  0100  movlb   0x0
0013d4:  6f6e  movwf   0x6e, B                              ; reg: 0x06e
0013d6:  696f  setf    0x6f, B                              ; reg: 0x06f
0013d8:  6970  setf    0x70, B                              ; reg: 0x070
0013da:  6971  setf    0x71, B                              ; reg: 0x071
0013dc:  0e01  movlw   0x01
0013de:  6f99  movwf   0x99, B                              ; reg: 0x099
0013e0:  0e03  movlw   0x03
0013e2:  6e5f  movwf   (Common_RAM + 95), A                 ; reg: 0x05f
0013e4:  6b60  clrf    0x60, B                              ; reg: 0x060
0013e6:  6b61  clrf    0x61, B                              ; reg: 0x061
0013e8:  6b62  clrf    0x62, B                              ; reg: 0x062
0013ea:  0e01  movlw   0x01
0013ec:  6f63  movwf   0x63, B                              ; reg: 0x063
0013ee:  6f64  movwf   0x64, B                              ; reg: 0x064
0013f0:  6f65  movwf   0x65, B                              ; reg: 0x065
0013f2:  6fb4  movwf   0xb4, B                              ; reg: 0x0b4
0013f4:  0e04  movlw   0x04
0013f6:  6fb8  movwf   0xb8, B                              ; reg: 0x0b8
0013f8:  6b9b  clrf    0x9b, B                              ; reg: 0x09b
0013fa:  6b9c  clrf    0x9c, B                              ; reg: 0x09c
0013fc:  6b9d  clrf    0x9d, B                              ; reg: 0x09d
0013fe:  6b9e  clrf    0x9e, B                              ; reg: 0x09e
001400:  6a58  clrf    (Common_RAM + 88), A                 ; reg: 0x058

label_058:                                                  ; address: 0x001402

001402:  0ec0  movlw   0xc0
001404:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
001406:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
001408:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00140a:  0e02  movlw   0x02
00140c:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
00140e:  68df  setf    INDF2, A                             ; reg: 0xfdf
001410:  2a58  incf    (Common_RAM + 88), F, A              ; reg: 0x058
001412:  0e1d  movlw   0x1d
001414:  6458  cpfsgt  (Common_RAM + 88), A                 ; reg: 0x058
001416:  d7f5  bra     label_058                            ; dest: 0x001402
001418:  6a58  clrf    (Common_RAM + 88), A                 ; reg: 0x058

label_059:                                                  ; address: 0x00141a

00141a:  0e00  movlw   0x00
00141c:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
00141e:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
001420:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
001422:  0e01  movlw   0x01
001424:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
001426:  68df  setf    INDF2, A                             ; reg: 0xfdf
001428:  2a58  incf    (Common_RAM + 88), F, A              ; reg: 0x058
00142a:  0e0e  movlw   0x0e
00142c:  6458  cpfsgt  (Common_RAM + 88), A                 ; reg: 0x058
00142e:  d7f5  bra     label_059                            ; dest: 0x00141a
001430:  0100  movlb   0x0
001432:  81bd  bsf     0xbd, 0x0, B                         ; reg: 0x0bd
001434:  8bbd  bsf     0xbd, 0x5, B                         ; reg: 0x0bd
001436:  89bd  bsf     0xbd, 0x4, B                         ; reg: 0x0bd
001438:  83bd  bsf     0xbd, 0x1, B                         ; reg: 0x0bd
00143a:  85bd  bsf     0xbd, 0x2, B                         ; reg: 0x0bd
00143c:  87bd  bsf     0xbd, 0x3, B                         ; reg: 0x0bd
00143e:  817e  bsf     0x7e, 0x0, B                         ; reg: 0x07e
001440:  ec2e  call    function_014, 0x0                    ; dest: 0x00265c
001442:  f013
001444:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
001446:  6807  setf    (Common_RAM + 7), A                  ; reg: 0x007
001448:  0e00  movlw   0x00
00144a:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009
00144c:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
00144e:  f023
001450:  ec6a  call    function_114, 0x0                    ; dest: 0x0048d4
001452:  f024
001454:  d0aa  bra     label_083                            ; dest: 0x0015aa

label_060:                                                  ; address: 0x001456

001456:  0100  movlb   0x0
001458:  67cb  tstfsz  0xcb, B                              ; reg: 0x0cb
00145a:  d050  bra     label_064                            ; dest: 0x0014fc
00145c:  6b7c  clrf    0x7c, B                              ; reg: 0x07c
00145e:  6b7d  clrf    0x7d, B                              ; reg: 0x07d
001460:  6b80  clrf    0x80, B                              ; reg: 0x080
001462:  6b81  clrf    0x81, B                              ; reg: 0x081
001464:  6b86  clrf    0x86, B                              ; reg: 0x086
001466:  6b87  clrf    0x87, B                              ; reg: 0x087
001468:  6b84  clrf    0x84, B                              ; reg: 0x084
00146a:  6b85  clrf    0x85, B                              ; reg: 0x085
00146c:  0101  movlb   0x1
00146e:  0e01  movlw   0x01
001470:  6e04  movwf   0x04, A                              ; reg: 0x104
001472:  0ec7  movlw   0xc7
001474:  6e03  movwf   0x03, A                              ; reg: 0x103
001476:  0e0a  movlw   0x0a
001478:  6e05  movwf   0x05, A                              ; reg: 0x105
00147a:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00147c:  f023
00147e:  0101  movlb   0x1
001480:  0e01  movlw   0x01
001482:  6e04  movwf   0x04, A                              ; reg: 0x104
001484:  0e9a  movlw   0x9a
001486:  6e03  movwf   0x03, A                              ; reg: 0x103
001488:  0e2d  movlw   0x2d
00148a:  6e05  movwf   0x05, A                              ; reg: 0x105
00148c:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00148e:  f023
001490:  0101  movlb   0x1
001492:  0e01  movlw   0x01
001494:  6e04  movwf   0x04, A                              ; reg: 0x104
001496:  0ed1  movlw   0xd1
001498:  6e03  movwf   0x03, A                              ; reg: 0x103
00149a:  0e08  movlw   0x08
00149c:  6e05  movwf   0x05, A                              ; reg: 0x105
00149e:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
0014a0:  f023
0014a2:  ec27  call    function_107, 0x0                    ; dest: 0x00484e
0014a4:  f024
0014a6:  0e05  movlw   0x05
0014a8:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
0014aa:  0edc  movlw   0xdc
0014ac:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
0014ae:  0101  movlb   0x1
0014b0:  0e01  movlw   0x01
0014b2:  6e08  movwf   0x08, A                              ; reg: 0x108
0014b4:  0ed1  movlw   0xd1
0014b6:  6e07  movwf   0x07, A                              ; reg: 0x107
0014b8:  0e08  movlw   0x08
0014ba:  6e09  movwf   0x09, A                              ; reg: 0x109
0014bc:  ec52  call    function_048, 0x0                    ; dest: 0x003aa4
0014be:  f01d
0014c0:  6e4c  movwf   (Common_RAM + 76), A                 ; reg: 0x04c
0014c2:  0e05  movlw   0x05
0014c4:  5c4c  subwf   (Common_RAM + 76), W, A              ; reg: 0x04c
0014c6:  e319  bnc     label_063
0014c8:  0e01  movlw   0x01
0014ca:  6fcb  movwf   0xcb, B                              ; reg: 0x0cb
0014cc:  6a58  clrf    (Common_RAM + 88), A                 ; reg: 0x058

label_061:                                                  ; address: 0x0014ce

0014ce:  5058  movf    (Common_RAM + 88), W, A              ; reg: 0x058
0014d0:  0f4d  addlw   0x4d
0014d2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0014d4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0014d6:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0014d8:  6e4c  movwf   (Common_RAM + 76), A                 ; reg: 0x04c
0014da:  0ed1  movlw   0xd1
0014dc:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
0014de:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0014e0:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0014e2:  0e01  movlw   0x01
0014e4:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0014e6:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0014e8:  184c  xorwf   (Common_RAM + 76), W, A              ; reg: 0x04c
0014ea:  e002  bz      label_062
0014ec:  0100  movlb   0x0
0014ee:  6bcb  clrf    0xcb, B                              ; reg: 0x0cb

label_062:                                                  ; address: 0x0014f0

0014f0:  2a58  incf    (Common_RAM + 88), F, A              ; reg: 0x058
0014f2:  0e05  movlw   0x05
0014f4:  6458  cpfsgt  (Common_RAM + 88), A                 ; reg: 0x058
0014f6:  d7eb  bra     label_061                            ; dest: 0x0014ce
0014f8:  d001  bra     label_064                            ; dest: 0x0014fc

label_063:                                                  ; address: 0x0014fa

0014fa:  6bcb  clrf    0xcb, B                              ; reg: 0x0cb

label_064:                                                  ; address: 0x0014fc

0014fc:  0100  movlb   0x0
0014fe:  51cb  movf    0xcb, W, B                           ; reg: 0x0cb
001500:  e101  bnz     label_065
001502:  d763  bra     label_056                            ; dest: 0x0013ca

label_065:                                                  ; address: 0x001504

001504:  ece7  call    function_003, 0x0                    ; dest: 0x0015ce
001506:  f00a
001508:  d760  bra     label_056                            ; dest: 0x0013ca

label_066:                                                  ; address: 0x00150a

00150a:  c11e  movff   0x11e, (Common_RAM + 86)             ; reg2: 0x056
00150c:  f056
00150e:  c11f  movff   0x11f, (Common_RAM + 85)             ; reg2: 0x055
001510:  f055
001512:  c057  movff   (Common_RAM + 87), 0x0c1             ; reg1: 0x057
001514:  f0c1
001516:  ec94  call    function_009, 0x0                    ; dest: 0x002328
001518:  f011
00151a:  517d  movf    0x7d, W, B                           ; reg: 0x07d
00151c:  1856  xorwf   (Common_RAM + 86), W, A              ; reg: 0x056
00151e:  e102  bnz     label_067
001520:  517c  movf    0x7c, W, B                           ; reg: 0x07c
001522:  1855  xorwf   (Common_RAM + 85), W, A              ; reg: 0x055

label_067:                                                  ; address: 0x001524

001524:  e106  bnz     label_068
001526:  ec39  call    function_090, 0x0                    ; dest: 0x004672
001528:  f023
00152a:  0eaa  movlw   0xaa
00152c:  0101  movlb   0x1
00152e:  6f5c  movwf   0x5c, B                              ; reg: 0x15c
001530:  d03c  bra     label_083                            ; dest: 0x0015aa

label_068:                                                  ; address: 0x001532

001532:  0e11  movlw   0x11
001534:  0101  movlb   0x1
001536:  6f5b  movwf   0x5b, B                              ; reg: 0x15b
001538:  0100  movlb   0x0
00153a:  6b84  clrf    0x84, B                              ; reg: 0x084
00153c:  6b85  clrf    0x85, B                              ; reg: 0x085
00153e:  6b80  clrf    0x80, B                              ; reg: 0x080
001540:  6b81  clrf    0x81, B                              ; reg: 0x081
001542:  6b86  clrf    0x86, B                              ; reg: 0x086
001544:  6b87  clrf    0x87, B                              ; reg: 0x087
001546:  6b7c  clrf    0x7c, B                              ; reg: 0x07c
001548:  6b7d  clrf    0x7d, B                              ; reg: 0x07d
00154a:  d02f  bra     label_083                            ; dest: 0x0015aa

label_069:                                                  ; address: 0x00154c

00154c:  0101  movlb   0x1
00154e:  6b1a  clrf    0x1a, B                              ; reg: 0x11a
001550:  d02c  bra     label_083                            ; dest: 0x0015aa

label_070:                                                  ; address: 0x001552

001552:  5057  movf    (Common_RAM + 87), W, A              ; reg: 0x057
001554:  0a01  xorlw   0x01
001556:  e029  bz      label_083
001558:  0a03  xorlw   0x03
00155a:  e027  bz      label_083
00155c:  0a01  xorlw   0x01
00155e:  e101  bnz     label_071
001560:  d5b7  bra     label_003                            ; dest: 0x0010d0

label_071:                                                  ; address: 0x001562

001562:  0a07  xorlw   0x07
001564:  e101  bnz     label_072
001566:  d5e6  bra     label_013                            ; dest: 0x001134

label_072:                                                  ; address: 0x001568

001568:  0a01  xorlw   0x01
00156a:  e101  bnz     label_073
00156c:  d630  bra     label_023                            ; dest: 0x0011ce

label_073:                                                  ; address: 0x00156e

00156e:  0a03  xorlw   0x03
001570:  e101  bnz     label_074
001572:  d702  bra     label_049                            ; dest: 0x001378

label_074:                                                  ; address: 0x001574

001574:  0a01  xorlw   0x01
001576:  e101  bnz     label_075
001578:  d714  bra     label_054                            ; dest: 0x0013a2

label_075:                                                  ; address: 0x00157a

00157a:  0a0f  xorlw   0x0f
00157c:  e101  bnz     label_076
00157e:  d711  bra     label_054                            ; dest: 0x0013a2

label_076:                                                  ; address: 0x001580

001580:  0a01  xorlw   0x01
001582:  e101  bnz     label_077
001584:  d70e  bra     label_054                            ; dest: 0x0013a2

label_077:                                                  ; address: 0x001586

001586:  0a03  xorlw   0x03
001588:  e101  bnz     label_078
00158a:  d70b  bra     label_054                            ; dest: 0x0013a2

label_078:                                                  ; address: 0x00158c

00158c:  0a01  xorlw   0x01
00158e:  e101  bnz     label_079
001590:  d708  bra     label_054                            ; dest: 0x0013a2

label_079:                                                  ; address: 0x001592

001592:  0a07  xorlw   0x07
001594:  e101  bnz     label_080
001596:  d700  bra     label_053                            ; dest: 0x001398

label_080:                                                  ; address: 0x001598

001598:  0a4c  xorlw   0x4c
00159a:  e101  bnz     label_081
00159c:  d719  bra     label_057                            ; dest: 0x0013d0

label_081:                                                  ; address: 0x00159e

00159e:  0a01  xorlw   0x01
0015a0:  e0b4  bz      label_066
0015a2:  0a03  xorlw   0x03
0015a4:  e101  bnz     label_082
0015a6:  d757  bra     label_060                            ; dest: 0x001456

label_082:                                                  ; address: 0x0015a8

0015a8:  d7d1  bra     label_069                            ; dest: 0x00154c

label_083:                                                  ; address: 0x0015aa

0015aa:  0101  movlb   0x1
0015ac:  6b1a  clrf    0x1a, B                              ; reg: 0x11a
0015ae:  0012  return  0x0

function_001:                                               ; address: 0x0015b0

0015b0:  0e1a  movlw   0x1a
0015b2:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
0015b4:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0015b6:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0015b8:  0e01  movlw   0x01
0015ba:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0015bc:  0012  return  0x0

function_002:                                               ; address: 0x0015be

0015be:  0ebe  movlw   0xbe
0015c0:  2458  addwf   (Common_RAM + 88), W, A              ; reg: 0x058
0015c2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0015c4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0015c6:  0e02  movlw   0x02
0015c8:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0015ca:  68df  setf    INDF2, A                             ; reg: 0xfdf
0015cc:  0012  return  0x0

function_003:                                               ; address: 0x0015ce

0015ce:  ee21  lfsr    0x2, 0x1e5
0015d0:  f0e5
0015d2:  ee10  lfsr    0x1, 0x01d
0015d4:  f01d
0015d6:  0e08  movlw   0x08

label_084:                                                  ; address: 0x0015d8

0015d8:  cfde  movff   POSTINC2, POSTINC1                   ; reg1: 0xfde, reg2: 0xfe6
0015da:  ffe6
0015dc:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
0015de:  d7fc  bra     label_084                            ; dest: 0x0015d8
0015e0:  0e02  movlw   0x02
0015e2:  6e49  movwf   (Common_RAM + 73), A                 ; reg: 0x049

label_085:                                                  ; address: 0x0015e4

0015e4:  0e1a  movlw   0x1a
0015e6:  2449  addwf   (Common_RAM + 73), W, A              ; reg: 0x049
0015e8:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0015ea:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0015ec:  0e01  movlw   0x01
0015ee:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0015f0:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0015f2:  6e4a  movwf   (Common_RAM + 74), A                 ; reg: 0x04a
0015f4:  0ec0  movlw   0xc0
0015f6:  0100  movlb   0x0
0015f8:  5d84  subwf   0x84, W, B                           ; reg: 0x084
0015fa:  0e77  movlw   0x77
0015fc:  5985  subwfb  0x85, W, B                           ; reg: 0x085
0015fe:  e21a  bc      label_090
001600:  c04a  movff   (Common_RAM + 74), (Common_RAM + 69) ; reg1: 0x04a, reg2: 0x045
001602:  f045
001604:  6a48  clrf    (Common_RAM + 72), A                 ; reg: 0x048

label_086:                                                  ; address: 0x001606

001606:  ab7d  btfss   0x7d, 0x5, B                         ; reg: 0x07d
001608:  d003  bra     label_087                            ; dest: 0x001610
00160a:  0e01  movlw   0x01
00160c:  6e44  movwf   (Common_RAM + 68), A                 ; reg: 0x044
00160e:  d001  bra     label_088                            ; dest: 0x001612

label_087:                                                  ; address: 0x001610

001610:  6a44  clrf    (Common_RAM + 68), A                 ; reg: 0x044

label_088:                                                  ; address: 0x001612

001612:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
001614:  377c  rlcf    0x7c, F, B                           ; reg: 0x07c
001616:  377d  rlcf    0x7d, F, B                           ; reg: 0x07d
001618:  b045  btfsc   (Common_RAM + 69), 0x0, A            ; reg: 0x045
00161a:  817c  bsf     0x7c, 0x0, B                         ; reg: 0x07c
00161c:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
00161e:  3245  rrcf    (Common_RAM + 69), F, A              ; reg: 0x045
001620:  5044  movf    (Common_RAM + 68), W, A              ; reg: 0x044
001622:  e004  bz      label_089
001624:  0e02  movlw   0x02
001626:  1b7c  xorwf   0x7c, F, B                           ; reg: 0x07c
001628:  0e44  movlw   0x44
00162a:  1b7d  xorwf   0x7d, F, B                           ; reg: 0x07d

label_089:                                                  ; address: 0x00162c

00162c:  2a48  incf    (Common_RAM + 72), F, A              ; reg: 0x048
00162e:  0e07  movlw   0x07
001630:  6448  cpfsgt  (Common_RAM + 72), A                 ; reg: 0x048
001632:  d7e9  bra     label_086                            ; dest: 0x001606

label_090:                                                  ; address: 0x001634

001634:  0e40  movlw   0x40
001636:  5d84  subwf   0x84, W, B                           ; reg: 0x084
001638:  0e00  movlw   0x00
00163a:  5985  subwfb  0x85, W, B                           ; reg: 0x085
00163c:  e201  bc      label_091
00163e:  d148  bra     label_108                            ; dest: 0x0018d0

label_091:                                                  ; address: 0x001640

001640:  0ec0  movlw   0xc0
001642:  5d84  subwf   0x84, W, B                           ; reg: 0x084
001644:  0e77  movlw   0x77
001646:  5985  subwfb  0x85, W, B                           ; reg: 0x085
001648:  e301  bnc     label_092
00164a:  d142  bra     label_108                            ; dest: 0x0018d0

label_092:                                                  ; address: 0x00164c

00164c:  0e0f  movlw   0x0f
00164e:  1584  andwf   0x84, W, B                           ; reg: 0x084
001650:  6f8a  movwf   0x8a, B                              ; reg: 0x08a
001652:  6b8b  clrf    0x8b, B                              ; reg: 0x08b
001654:  118b  iorwf   0x8b, W, B                           ; reg: 0x08b
001656:  e001  bz      label_093
001658:  d0ea  bra     label_102                            ; dest: 0x00182e

label_093:                                                  ; address: 0x00165a

00165a:  5187  movf    0x87, W, B                           ; reg: 0x087
00165c:  1186  iorwf   0x86, W, B                           ; reg: 0x086
00165e:  e101  bnz     label_094
001660:  d09d  bra     label_099                            ; dest: 0x00179c

label_094:                                                  ; address: 0x001662

001662:  5186  movf    0x86, W, B                           ; reg: 0x086
001664:  2780  addwf   0x80, F, B                           ; reg: 0x080
001666:  0e00  movlw   0x00
001668:  2381  addwfc  0x81, F, B                           ; reg: 0x081
00166a:  5187  movf    0x87, W, B                           ; reg: 0x087
00166c:  2780  addwf   0x80, F, B                           ; reg: 0x080
00166e:  0e00  movlw   0x00
001670:  2381  addwfc  0x81, F, B                           ; reg: 0x081
001672:  1d80  comf    0x80, W, B                           ; reg: 0x080
001674:  6e1b  movwf   (Common_RAM + 27), A                 ; reg: 0x01b
001676:  1d81  comf    0x81, W, B                           ; reg: 0x081
001678:  6e1c  movwf   (Common_RAM + 28), A                 ; reg: 0x01c
00167a:  0ef1  movlw   0xf1
00167c:  241b  addwf   (Common_RAM + 27), W, A              ; reg: 0x01b
00167e:  6f80  movwf   0x80, B                              ; reg: 0x080
001680:  0eff  movlw   0xff
001682:  201c  addwfc  (Common_RAM + 28), W, A              ; reg: 0x01c
001684:  6f81  movwf   0x81, B                              ; reg: 0x081
001686:  5180  movf    0x80, W, B                           ; reg: 0x080
001688:  ecd1  call    function_073, 0x0                    ; dest: 0x0043a2
00168a:  f021
00168c:  0e0d  movlw   0x0d
00168e:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001690:  f024
001692:  0e0a  movlw   0x0a
001694:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001696:  f024
001698:  c080  movff   0x080, (Common_RAM + 27)             ; reg2: 0x01b
00169a:  f01b
00169c:  3a1b  swapf   (Common_RAM + 27), F, A              ; reg: 0x01b
00169e:  0e0f  movlw   0x0f
0016a0:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
0016a2:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
0016a4:  501b  movf    (Common_RAM + 27), W, A              ; reg: 0x01b
0016a6:  0f19  addlw   0x19
0016a8:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
0016aa:  0e10  movlw   0x10
0016ac:  6ef7  movwf   TBLPTRH, A                           ; reg: 0xff7
0016ae:  0e9a  movlw   0x9a
0016b0:  244b  addwf   (Common_RAM + 75), W, A              ; reg: 0x04b
0016b2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0016b4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0016b6:  0e01  movlw   0x01
0016b8:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0016ba:  0008  tblrd*
0016bc:  cff5  movff   TABLAT, INDF2                        ; reg1: 0xff5, reg2: 0xfdf
0016be:  ffdf
0016c0:  c080  movff   0x080, (Common_RAM + 27)             ; reg2: 0x01b
0016c2:  f01b
0016c4:  0e0f  movlw   0x0f
0016c6:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
0016c8:  501b  movf    (Common_RAM + 27), W, A              ; reg: 0x01b
0016ca:  0f19  addlw   0x19
0016cc:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
0016ce:  0e10  movlw   0x10
0016d0:  6ef7  movwf   TBLPTRH, A                           ; reg: 0xff7
0016d2:  0e9b  movlw   0x9b
0016d4:  244b  addwf   (Common_RAM + 75), W, A              ; reg: 0x04b
0016d6:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0016d8:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0016da:  0e01  movlw   0x01
0016dc:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0016de:  0008  tblrd*
0016e0:  cff5  movff   TABLAT, INDF2                        ; reg1: 0xff5, reg2: 0xfdf
0016e2:  ffdf
0016e4:  0e9c  movlw   0x9c
0016e6:  244b  addwf   (Common_RAM + 75), W, A              ; reg: 0x04b
0016e8:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0016ea:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0016ec:  0e01  movlw   0x01
0016ee:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0016f0:  6adf  clrf    INDF2, A                             ; reg: 0xfdf
0016f2:  0e02  movlw   0x02
0016f4:  264b  addwf   (Common_RAM + 75), F, A              ; reg: 0x04b
0016f6:  0100  movlb   0x0
0016f8:  6b9f  clrf    0x9f, B                              ; reg: 0x09f

label_095:                                                  ; address: 0x0016fa

0016fa:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
0016fc:  0e0a  movlw   0x0a
0016fe:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
001700:  0101  movlb   0x1
001702:  0e01  movlw   0x01
001704:  6e08  movwf   0x08, A                              ; reg: 0x108
001706:  0ec7  movlw   0xc7
001708:  6e07  movwf   0x07, A                              ; reg: 0x107
00170a:  0e0a  movlw   0x0a
00170c:  6e09  movwf   0x09, A                              ; reg: 0x109
00170e:  ec52  call    function_048, 0x0                    ; dest: 0x003aa4
001710:  f01d
001712:  c1c8  movff   0x1c8, (Common_RAM + 3)              ; reg2: 0x003
001714:  f003
001716:  0101  movlb   0x1
001718:  51c7  movf    0xc7, W, B                           ; reg: 0x1c7
00171a:  ecbc  call    function_059, 0x0                    ; dest: 0x003f78
00171c:  f01f
00171e:  0100  movlb   0x0
001720:  1980  xorwf   0x80, W, B                           ; reg: 0x080
001722:  e103  bnz     label_096
001724:  0e01  movlw   0x01
001726:  6e43  movwf   (Common_RAM + 67), A                 ; reg: 0x043
001728:  d036  bra     label_098                            ; dest: 0x001796

label_096:                                                  ; address: 0x00172a

00172a:  6a43  clrf    (Common_RAM + 67), A                 ; reg: 0x043
00172c:  6a19  clrf    (Common_RAM + 25), A                 ; reg: 0x019
00172e:  0e1d  movlw   0x1d
001730:  6e18  movwf   (Common_RAM + 24), A                 ; reg: 0x018
001732:  ec4b  call    function_091, 0x0                    ; dest: 0x004696
001734:  f023
001736:  0100  movlb   0x0
001738:  c09f  movff   0x09f, (Common_RAM + 18)             ; reg2: 0x012
00173a:  f012
00173c:  6a13  clrf    (Common_RAM + 19), A                 ; reg: 0x013
00173e:  6a15  clrf    (Common_RAM + 21), A                 ; reg: 0x015
001740:  0e0a  movlw   0x0a
001742:  6e14  movwf   (Common_RAM + 20), A                 ; reg: 0x014
001744:  0e25  movlw   0x25
001746:  ecdb  call    function_065, 0x0                    ; dest: 0x0041b6
001748:  f020
00174a:  6e1b  movwf   (Common_RAM + 27), A                 ; reg: 0x01b
00174c:  6a19  clrf    (Common_RAM + 25), A                 ; reg: 0x019
00174e:  c01b  movff   (Common_RAM + 27), (Common_RAM + 24) ; reg1: 0x01b, reg2: 0x018
001750:  f018
001752:  ec4b  call    function_091, 0x0                    ; dest: 0x004696
001754:  f023
001756:  0e21  movlw   0x21
001758:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
00175a:  f024
00175c:  ec30  call    function_108, 0x0                    ; dest: 0x004860
00175e:  f024
001760:  0e0d  movlw   0x0d
001762:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001764:  f024
001766:  0e0a  movlw   0x0a
001768:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
00176a:  f024
00176c:  0e19  movlw   0x19
00176e:  0100  movlb   0x0
001770:  5d9f  subwf   0x9f, W, B                           ; reg: 0x09f
001772:  e20f  bc      label_097
001774:  2b9f  incf    0x9f, F, B                           ; reg: 0x09f
001776:  0101  movlb   0x1
001778:  0e01  movlw   0x01
00177a:  6e19  movwf   0x19, A                              ; reg: 0x119
00177c:  0e9a  movlw   0x9a
00177e:  6e18  movwf   0x18, A                              ; reg: 0x118
001780:  ec4b  call    function_091, 0x0                    ; dest: 0x004696
001782:  f023
001784:  0e0d  movlw   0x0d
001786:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001788:  f024
00178a:  0e0a  movlw   0x0a
00178c:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
00178e:  f024
001790:  d002  bra     label_098                            ; dest: 0x001796

label_097:                                                  ; address: 0x001792

001792:  2b9f  incf    0x9f, F, B                           ; reg: 0x09f
001794:  d0a3  bra     label_109                            ; dest: 0x0018dc

label_098:                                                  ; address: 0x001796

001796:  5043  movf    (Common_RAM + 67), W, A              ; reg: 0x043
001798:  e102  bnz     label_100
00179a:  d7af  bra     label_095                            ; dest: 0x0016fa

label_099:                                                  ; address: 0x00179c

00179c:  6b8e  clrf    0x8e, B                              ; reg: 0x08e

label_100:                                                  ; address: 0x00179e

00179e:  0ebf  movlw   0xbf
0017a0:  0100  movlb   0x0
0017a2:  5d84  subwf   0x84, W, B                           ; reg: 0x084
0017a4:  0e77  movlw   0x77
0017a6:  5985  subwfb  0x85, W, B                           ; reg: 0x085
0017a8:  e242  bc      label_102
0017aa:  0e04  movlw   0x04
0017ac:  5d8e  subwf   0x8e, W, B                           ; reg: 0x08e
0017ae:  e206  bc      label_101
0017b0:  2b8e  incf    0x8e, F, B                           ; reg: 0x08e
0017b2:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
0017b4:  0e0a  movlw   0x0a
0017b6:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
0017b8:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
0017ba:  f022

label_101:                                                  ; address: 0x0017bc

0017bc:  c084  movff   0x084, 0x086
0017be:  f086
0017c0:  c085  movff   0x085, 0x087
0017c2:  f087
0017c4:  0e3a  movlw   0x3a
0017c6:  0101  movlb   0x1
0017c8:  6f9a  movwf   0x9a, B                              ; reg: 0x19a
0017ca:  0e31  movlw   0x31
0017cc:  6f9b  movwf   0x9b, B                              ; reg: 0x19b
0017ce:  0e30  movlw   0x30
0017d0:  6f9c  movwf   0x9c, B                              ; reg: 0x19c
0017d2:  c087  movff   0x087, (Common_RAM + 27)             ; reg2: 0x01b
0017d4:  f01b
0017d6:  3a1b  swapf   0x1b, F, A                           ; reg: 0x11b
0017d8:  0e0f  movlw   0x0f
0017da:  161b  andwf   0x1b, F, A                           ; reg: 0x11b
0017dc:  d880  rcall   function_004                         ; dest: 0x0018de
0017de:  cff5  movff   TABLAT, 0x19d                        ; reg1: 0xff5
0017e0:  f19d
0017e2:  c087  movff   0x087, (Common_RAM + 27)             ; reg2: 0x01b
0017e4:  f01b
0017e6:  0e0f  movlw   0x0f
0017e8:  d87a  rcall   function_004                         ; dest: 0x0018de
0017ea:  cff5  movff   TABLAT, 0x19e                        ; reg1: 0xff5
0017ec:  f19e
0017ee:  c086  movff   0x086, (Common_RAM + 27)             ; reg2: 0x01b
0017f0:  f01b
0017f2:  3a1b  swapf   (Common_RAM + 27), F, A              ; reg: 0x01b
0017f4:  0e0f  movlw   0x0f
0017f6:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
0017f8:  d872  rcall   function_004                         ; dest: 0x0018de
0017fa:  cff5  movff   TABLAT, 0x19f                        ; reg1: 0xff5
0017fc:  f19f
0017fe:  c086  movff   0x086, (Common_RAM + 27)             ; reg2: 0x01b
001800:  f01b
001802:  0e0f  movlw   0x0f
001804:  d86c  rcall   function_004                         ; dest: 0x0018de
001806:  cff5  movff   TABLAT, 0x1a0                        ; reg1: 0xff5
001808:  f1a0
00180a:  0e30  movlw   0x30
00180c:  6fa1  movwf   0xa1, B                              ; reg: 0x0a1
00180e:  6fa2  movwf   0xa2, B                              ; reg: 0x0a2
001810:  6ba3  clrf    0xa3, B                              ; reg: 0x0a3
001812:  0e09  movlw   0x09
001814:  6e4b  movwf   (Common_RAM + 75), A                 ; reg: 0x04b
001816:  ec30  call    function_108, 0x0                    ; dest: 0x004860
001818:  f024
00181a:  0101  movlb   0x1
00181c:  0e01  movlw   0x01
00181e:  6e19  movwf   0x19, A                              ; reg: 0x119
001820:  0e9a  movlw   0x9a
001822:  6e18  movwf   0x18, A                              ; reg: 0x118
001824:  ec4b  call    function_091, 0x0                    ; dest: 0x004696
001826:  f023
001828:  0100  movlb   0x0
00182a:  6b80  clrf    0x80, B                              ; reg: 0x080
00182c:  6b81  clrf    0x81, B                              ; reg: 0x081

label_102:                                                  ; address: 0x00182e

00182e:  0ebf  movlw   0xbf
001830:  5d84  subwf   0x84, W, B                           ; reg: 0x084
001832:  0e77  movlw   0x77
001834:  5985  subwfb  0x85, W, B                           ; reg: 0x085
001836:  e24a  bc      label_107
001838:  a184  btfss   0x84, 0x0, B                         ; reg: 0x084
00183a:  d040  bra     label_105                            ; dest: 0x0018bc
00183c:  c046  movff   (Common_RAM + 70), (Common_RAM + 27) ; reg1: 0x046, reg2: 0x01b
00183e:  f01b
001840:  3a1b  swapf   (Common_RAM + 27), F, A              ; reg: 0x01b
001842:  0e0f  movlw   0x0f
001844:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
001846:  d84b  rcall   function_004                         ; dest: 0x0018de
001848:  cff5  movff   TABLAT, (Common_RAM + 47)            ; reg1: 0xff5, reg2: 0x02f
00184a:  f02f
00184c:  c046  movff   (Common_RAM + 70), (Common_RAM + 27) ; reg1: 0x046, reg2: 0x01b
00184e:  f01b
001850:  0e0f  movlw   0x0f
001852:  d845  rcall   function_004                         ; dest: 0x0018de
001854:  cff5  movff   TABLAT, (Common_RAM + 48)            ; reg1: 0xff5, reg2: 0x030
001856:  f030
001858:  c04a  movff   (Common_RAM + 74), (Common_RAM + 27) ; reg1: 0x04a, reg2: 0x01b
00185a:  f01b
00185c:  3a1b  swapf   (Common_RAM + 27), F, A              ; reg: 0x01b
00185e:  0e0f  movlw   0x0f
001860:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
001862:  d83d  rcall   function_004                         ; dest: 0x0018de
001864:  cff5  movff   TABLAT, (Common_RAM + 49)            ; reg1: 0xff5, reg2: 0x031
001866:  f031
001868:  c04a  movff   (Common_RAM + 74), (Common_RAM + 27) ; reg1: 0x04a, reg2: 0x01b
00186a:  f01b
00186c:  0e0f  movlw   0x0f
00186e:  d837  rcall   function_004                         ; dest: 0x0018de
001870:  cff5  movff   TABLAT, (Common_RAM + 50)            ; reg1: 0xff5, reg2: 0x032
001872:  f032
001874:  6a33  clrf    (Common_RAM + 51), A                 ; reg: 0x033
001876:  6a19  clrf    (Common_RAM + 25), A                 ; reg: 0x019
001878:  0e2f  movlw   0x2f
00187a:  6e18  movwf   (Common_RAM + 24), A                 ; reg: 0x018
00187c:  ec4b  call    function_091, 0x0                    ; dest: 0x004696
00187e:  f023
001880:  6a47  clrf    (Common_RAM + 71), A                 ; reg: 0x047
001882:  d00e  bra     label_104                            ; dest: 0x0018a0

label_103:                                                  ; address: 0x001884

001884:  5047  movf    (Common_RAM + 71), W, A              ; reg: 0x047
001886:  0f2f  addlw   0x2f
001888:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
00188a:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00188c:  0e9a  movlw   0x9a
00188e:  244b  addwf   (Common_RAM + 75), W, A              ; reg: 0x04b
001890:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
001892:  6ae2  clrf    FSR1H, A                             ; reg: 0xfe2
001894:  0e01  movlw   0x01
001896:  22e2  addwfc  FSR1H, F, A                          ; reg: 0xfe2
001898:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
00189a:  ffe7
00189c:  2a47  incf    (Common_RAM + 71), F, A              ; reg: 0x047
00189e:  2a4b  incf    (Common_RAM + 75), F, A              ; reg: 0x04b

label_104:                                                  ; address: 0x0018a0

0018a0:  5047  movf    (Common_RAM + 71), W, A              ; reg: 0x047
0018a2:  0f2f  addlw   0x2f
0018a4:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0018a6:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0018a8:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0018aa:  e1ec  bnz     label_103
0018ac:  0e9a  movlw   0x9a
0018ae:  244b  addwf   (Common_RAM + 75), W, A              ; reg: 0x04b
0018b0:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0018b2:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0018b4:  0e01  movlw   0x01
0018b6:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0018b8:  6adf  clrf    INDF2, A                             ; reg: 0xfdf
0018ba:  d002  bra     label_106                            ; dest: 0x0018c0

label_105:                                                  ; address: 0x0018bc

0018bc:  c04a  movff   (Common_RAM + 74), (Common_RAM + 70) ; reg1: 0x04a, reg2: 0x046
0018be:  f046

label_106:                                                  ; address: 0x0018c0

0018c0:  504a  movf    (Common_RAM + 74), W, A              ; reg: 0x04a
0018c2:  0100  movlb   0x0
0018c4:  2780  addwf   0x80, F, B                           ; reg: 0x080
0018c6:  0e00  movlw   0x00
0018c8:  2381  addwfc  0x81, F, B                           ; reg: 0x081
0018ca:  d002  bra     label_108                            ; dest: 0x0018d0

label_107:                                                  ; address: 0x0018cc

0018cc:  6b80  clrf    0x80, B                              ; reg: 0x080
0018ce:  6b81  clrf    0x81, B                              ; reg: 0x081

label_108:                                                  ; address: 0x0018d0

0018d0:  4b84  infsnz  0x84, F, B                           ; reg: 0x084
0018d2:  2b85  incf    0x85, F, B                           ; reg: 0x085
0018d4:  2a49  incf    (Common_RAM + 73), F, A              ; reg: 0x049
0018d6:  0e1f  movlw   0x1f
0018d8:  6449  cpfsgt  (Common_RAM + 73), A                 ; reg: 0x049
0018da:  d684  bra     label_085                            ; dest: 0x0015e4

label_109:                                                  ; address: 0x0018dc

0018dc:  0012  return  0x0

function_004:                                               ; address: 0x0018de

0018de:  161b  andwf   (Common_RAM + 27), F, A              ; reg: 0x01b
0018e0:  501b  movf    (Common_RAM + 27), W, A              ; reg: 0x01b
0018e2:  0f19  addlw   0x19
0018e4:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
0018e6:  0e10  movlw   0x10
0018e8:  6ef7  movwf   TBLPTRH, A                           ; reg: 0xff7
0018ea:  0008  tblrd*
0018ec:  0012  return  0x0

function_005:                                               ; address: 0x0018ee

0018ee:  cfe8  movff   WREG, 0x0fd                          ; reg1: 0xfe8
0018f0:  f0fd
0018f2:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
0018f4:  d177  bra     label_144                            ; dest: 0x001be4
0018f6:  a37e  btfss   0x7e, 0x1, B                         ; reg: 0x07e
0018f8:  d057  bra     label_117                            ; dest: 0x0019a8
0018fa:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
0018fc:  d039  bra     label_115                            ; dest: 0x001970

label_110:                                                  ; address: 0x0018fe

0018fe:  0e09  movlw   0x09
001900:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
001902:  0e0d  movlw   0x0d
001904:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
001906:  f023
001908:  0e70  movlw   0x70
00190a:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00190c:  0e08  movlw   0x08
00190e:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
001910:  f023
001912:  ec71  call    function_115, 0x0                    ; dest: 0x0048e2
001914:  f024
001916:  d03c  bra     label_116                            ; dest: 0x001990

label_111:                                                  ; address: 0x001918

001918:  0e0a  movlw   0x0a
00191a:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00191c:  0e0d  movlw   0x0d
00191e:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
001920:  f023
001922:  0eb0  movlw   0xb0
001924:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
001926:  0e08  movlw   0x08
001928:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00192a:  f023
00192c:  ec71  call    function_115, 0x0                    ; dest: 0x0048e2
00192e:  f024
001930:  d02f  bra     label_116                            ; dest: 0x001990

label_112:                                                  ; address: 0x001932

001932:  0e08  movlw   0x08
001934:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
001936:  0e0d  movlw   0x0d
001938:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00193a:  f023
00193c:  0e30  movlw   0x30
00193e:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
001940:  0e08  movlw   0x08
001942:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
001944:  f023
001946:  ec71  call    function_115, 0x0                    ; dest: 0x0048e2
001948:  f024
00194a:  d022  bra     label_116                            ; dest: 0x001990

label_113:                                                  ; address: 0x00194c

00194c:  0e0b  movlw   0x0b
00194e:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
001950:  0e0d  movlw   0x0d
001952:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
001954:  f023
001956:  0ef0  movlw   0xf0
001958:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00195a:  0e08  movlw   0x08
00195c:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00195e:  f023
001960:  ec71  call    function_115, 0x0                    ; dest: 0x0048e2
001962:  f024
001964:  d015  bra     label_116                            ; dest: 0x001990

label_114:                                                  ; address: 0x001966

001966:  ec8b  call    function_082, 0x0                    ; dest: 0x004516
001968:  f022
00196a:  ecaa  call    function_124, 0x0                    ; dest: 0x004954
00196c:  f024
00196e:  d010  bra     label_116                            ; dest: 0x001990

label_115:                                                  ; address: 0x001970

001970:  5193  movf    0x93, W, B                           ; reg: 0x093
001972:  e0f9  bz      label_114
001974:  0a01  xorlw   0x01
001976:  e0c3  bz      label_110
001978:  0a03  xorlw   0x03
00197a:  e0ce  bz      label_111
00197c:  0a01  xorlw   0x01
00197e:  e0d9  bz      label_112
001980:  0a07  xorlw   0x07
001982:  e0e4  bz      label_113
001984:  0a01  xorlw   0x01
001986:  e0ef  bz      label_114
001988:  0a03  xorlw   0x03
00198a:  e0ed  bz      label_114
00198c:  0a01  xorlw   0x01
00198e:  e0eb  bz      label_114

label_116:                                                  ; address: 0x001990

001990:  0e05  movlw   0x05
001992:  0100  movlb   0x0
001994:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001996:  51fd  movf    0xfd, W, B                           ; reg: 0x0fd
001998:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
00199a:  ecd1  call    function_085, 0x0                    ; dest: 0x0045a2
00199c:  f022
00199e:  0100  movlb   0x0
0019a0:  937e  bcf     0x7e, 0x1, B                         ; reg: 0x07e
0019a2:  81bd  bsf     0xbd, 0x0, B                         ; reg: 0x0bd
0019a4:  ec53  call    function_112, 0x0                    ; dest: 0x0048a6
0019a6:  f024

label_117:                                                  ; address: 0x0019a8

0019a8:  0100  movlb   0x0
0019aa:  a77e  btfss   0x7e, 0x3, B                         ; reg: 0x07e
0019ac:  d064  bra     label_124                            ; dest: 0x001a76
0019ae:  985e  bcf     (Common_RAM + 94), 0x4, A            ; reg: 0x05e
0019b0:  9b7e  bcf     0x7e, 0x5, B                         ; reg: 0x07e
0019b2:  8d7e  bsf     0x7e, 0x6, B                         ; reg: 0x07e
0019b4:  6ba4  clrf    0xa4, B                              ; reg: 0x0a4
0019b6:  c0a4  movff   0x0a4, 0x0b0
0019b8:  f0b0
0019ba:  6b9a  clrf    0x9a, B                              ; reg: 0x09a
0019bc:  d00c  bra     label_122                            ; dest: 0x0019d6

label_118:                                                  ; address: 0x0019be

0019be:  c09b  movff   0x09b, 0x09a
0019c0:  f09a
0019c2:  d011  bra     label_123                            ; dest: 0x0019e6

label_119:                                                  ; address: 0x0019c4

0019c4:  c09c  movff   0x09c, 0x09a
0019c6:  f09a
0019c8:  d00e  bra     label_123                            ; dest: 0x0019e6

label_120:                                                  ; address: 0x0019ca

0019ca:  c09d  movff   0x09d, 0x09a
0019cc:  f09a
0019ce:  d00b  bra     label_123                            ; dest: 0x0019e6

label_121:                                                  ; address: 0x0019d0

0019d0:  c09e  movff   0x09e, 0x09a
0019d2:  f09a
0019d4:  d008  bra     label_123                            ; dest: 0x0019e6

label_122:                                                  ; address: 0x0019d6

0019d6:  5193  movf    0x93, W, B                           ; reg: 0x093
0019d8:  e0f2  bz      label_118
0019da:  0a05  xorlw   0x05
0019dc:  e0f3  bz      label_119
0019de:  0a03  xorlw   0x03
0019e0:  e0f4  bz      label_120
0019e2:  0a01  xorlw   0x01
0019e4:  e0f5  bz      label_121

label_123:                                                  ; address: 0x0019e6

0019e6:  519a  movf    0x9a, W, B                           ; reg: 0x09a
0019e8:  256e  addwf   0x6e, W, B                           ; reg: 0x06e
0019ea:  6e0d  movwf   (Common_RAM + 13), A                 ; reg: 0x00d
0019ec:  0e00  movlw   0x00
0019ee:  216f  addwfc  0x6f, W, B                           ; reg: 0x06f
0019f0:  6e0e  movwf   (Common_RAM + 14), A                 ; reg: 0x00e
0019f2:  0e00  movlw   0x00
0019f4:  2170  addwfc  0x70, W, B                           ; reg: 0x070
0019f6:  6e0f  movwf   (Common_RAM + 15), A                 ; reg: 0x00f
0019f8:  0e00  movlw   0x00
0019fa:  2171  addwfc  0x71, W, B                           ; reg: 0x071
0019fc:  6e10  movwf   (Common_RAM + 16), A                 ; reg: 0x010
0019fe:  ec05  call    function_055, 0x0                    ; dest: 0x003e0a
001a00:  f01f
001a02:  c00d  movff   (Common_RAM + 13), (Common_RAM + 18) ; reg1: 0x00d, reg2: 0x012
001a04:  f012
001a06:  c00e  movff   (Common_RAM + 14), (Common_RAM + 19) ; reg1: 0x00e, reg2: 0x013
001a08:  f013
001a0a:  c00f  movff   (Common_RAM + 15), (Common_RAM + 20) ; reg1: 0x00f, reg2: 0x014
001a0c:  f014
001a0e:  c010  movff   (Common_RAM + 16), (Common_RAM + 21) ; reg1: 0x010, reg2: 0x015
001a10:  f015
001a12:  0e47  movlw   0x47
001a14:  6e16  movwf   (Common_RAM + 22), A                 ; reg: 0x016
001a16:  0ec9  movlw   0xc9
001a18:  6e17  movwf   (Common_RAM + 23), A                 ; reg: 0x017
001a1a:  0eeb  movlw   0xeb
001a1c:  6e18  movwf   (Common_RAM + 24), A                 ; reg: 0x018
001a1e:  0e3d  movlw   0x3d
001a20:  6e19  movwf   (Common_RAM + 25), A                 ; reg: 0x019
001a22:  ec5e  call    function_017, 0x0                    ; dest: 0x002abc
001a24:  f015
001a26:  c012  movff   (Common_RAM + 18), 0x0ed             ; reg1: 0x012
001a28:  f0ed
001a2a:  c013  movff   (Common_RAM + 19), 0x0ee             ; reg1: 0x013
001a2c:  f0ee
001a2e:  c014  movff   (Common_RAM + 20), 0x0ef             ; reg1: 0x014
001a30:  f0ef
001a32:  c015  movff   (Common_RAM + 21), 0x0f0             ; reg1: 0x015
001a34:  f0f0
001a36:  c0ed  movff   0x0ed, (Common_RAM + 47)             ; reg2: 0x02f
001a38:  f02f
001a3a:  c0ee  movff   0x0ee, (Common_RAM + 48)             ; reg2: 0x030
001a3c:  f030
001a3e:  c0ef  movff   0x0ef, (Common_RAM + 49)             ; reg2: 0x031
001a40:  f031
001a42:  c0f0  movff   0x0f0, (Common_RAM + 50)             ; reg2: 0x032
001a44:  f032
001a46:  ecbf  call    function_016, 0x0                    ; dest: 0x00297e
001a48:  f014
001a4a:  c02f  movff   (Common_RAM + 47), (Common_RAM + 85) ; reg1: 0x02f, reg2: 0x055
001a4c:  f055
001a4e:  c030  movff   (Common_RAM + 48), (Common_RAM + 86) ; reg1: 0x030, reg2: 0x056
001a50:  f056
001a52:  c031  movff   (Common_RAM + 49), (Common_RAM + 87) ; reg1: 0x031, reg2: 0x057
001a54:  f057
001a56:  c032  movff   (Common_RAM + 50), (Common_RAM + 88) ; reg1: 0x032, reg2: 0x058
001a58:  f058
001a5a:  ec72  call    function_081, 0x0                    ; dest: 0x0044e4
001a5c:  f022
001a5e:  0e05  movlw   0x05
001a60:  0100  movlb   0x0
001a62:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001a64:  51fd  movf    0xfd, W, B                           ; reg: 0x0fd
001a66:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001a68:  ecd1  call    function_085, 0x0                    ; dest: 0x0045a2
001a6a:  f022
001a6c:  0100  movlb   0x0
001a6e:  977e  bcf     0x7e, 0x3, B                         ; reg: 0x07e
001a70:  81bd  bsf     0xbd, 0x0, B                         ; reg: 0x0bd
001a72:  ec53  call    function_112, 0x0                    ; dest: 0x0048a6
001a74:  f024

label_124:                                                  ; address: 0x001a76

001a76:  ae5e  btfss   (Common_RAM + 94), 0x7, A            ; reg: 0x05e
001a78:  d011  bra     label_125                            ; dest: 0x001a9c
001a7a:  0e00  movlw   0x00
001a7c:  6a55  clrf    (Common_RAM + 85), A                 ; reg: 0x055
001a7e:  6a56  clrf    (Common_RAM + 86), A                 ; reg: 0x056
001a80:  6a57  clrf    (Common_RAM + 87), A                 ; reg: 0x057
001a82:  6a58  clrf    (Common_RAM + 88), A                 ; reg: 0x058
001a84:  ec72  call    function_081, 0x0                    ; dest: 0x0044e4
001a86:  f022
001a88:  ecba  call    function_084, 0x0                    ; dest: 0x004574
001a8a:  f022
001a8c:  ecaf  call    function_126, 0x0                    ; dest: 0x00495e
001a8e:  f024
001a90:  9e5e  bcf     (Common_RAM + 94), 0x7, A            ; reg: 0x05e
001a92:  0100  movlb   0x0
001a94:  ab7e  btfss   0x7e, 0x5, B                         ; reg: 0x07e
001a96:  b85e  btfsc   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001a98:  d001  bra     label_125                            ; dest: 0x001a9c
001a9a:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e

label_125:                                                  ; address: 0x001a9c

001a9c:  0100  movlb   0x0
001a9e:  ab7e  btfss   0x7e, 0x5, B                         ; reg: 0x07e
001aa0:  d014  bra     label_128                            ; dest: 0x001aca
001aa2:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001aa4:  d008  bra     label_126                            ; dest: 0x001ab6
001aa6:  0e00  movlw   0x00
001aa8:  6a55  clrf    (Common_RAM + 85), A                 ; reg: 0x055
001aaa:  6a56  clrf    (Common_RAM + 86), A                 ; reg: 0x056
001aac:  6a57  clrf    (Common_RAM + 87), A                 ; reg: 0x057
001aae:  6a58  clrf    (Common_RAM + 88), A                 ; reg: 0x058
001ab0:  ec72  call    function_081, 0x0                    ; dest: 0x0044e4
001ab2:  f022
001ab4:  d001  bra     label_127                            ; dest: 0x001ab8

label_126:                                                  ; address: 0x001ab6

001ab6:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e

label_127:                                                  ; address: 0x001ab8

001ab8:  0e05  movlw   0x05
001aba:  0100  movlb   0x0
001abc:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001abe:  51fd  movf    0xfd, W, B                           ; reg: 0x0fd
001ac0:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001ac2:  ecd1  call    function_085, 0x0                    ; dest: 0x0045a2
001ac4:  f022
001ac6:  0100  movlb   0x0
001ac8:  9b7e  bcf     0x7e, 0x5, B                         ; reg: 0x07e

label_128:                                                  ; address: 0x001aca

001aca:  ad7e  btfss   0x7e, 0x6, B                         ; reg: 0x07e
001acc:  d06e  bra     label_141                            ; dest: 0x001baa
001ace:  b1a4  btfsc   0xa4, 0x0, B                         ; reg: 0x0a4
001ad0:  d004  bra     label_129                            ; dest: 0x001ada
001ad2:  0e5f  movlw   0x5f
001ad4:  6ff2  movwf   0xf2, B                              ; reg: 0x0f2
001ad6:  0e1c  movlw   0x1c
001ad8:  d003  bra     label_130                            ; dest: 0x001ae0

label_129:                                                  ; address: 0x001ada

001ada:  0e5f  movlw   0x5f
001adc:  6ff2  movwf   0xf2, B                              ; reg: 0x0f2
001ade:  0e08  movlw   0x08

label_130:                                                  ; address: 0x001ae0

001ae0:  6ff1  movwf   0xf1, B                              ; reg: 0x0f1
001ae2:  c0f1  movff   0x0f1, (Common_RAM + 19)             ; reg2: 0x013
001ae4:  f013
001ae6:  c0f2  movff   0x0f2, (Common_RAM + 20)             ; reg2: 0x014
001ae8:  f014
001aea:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
001aec:  f01c
001aee:  0100  movlb   0x0
001af0:  b3a4  btfsc   0xa4, 0x1, B                         ; reg: 0x0a4
001af2:  d004  bra     label_131                            ; dest: 0x001afc
001af4:  0e5f  movlw   0x5f
001af6:  6ff4  movwf   0xf4, B                              ; reg: 0x0f4
001af8:  0e44  movlw   0x44
001afa:  d003  bra     label_132                            ; dest: 0x001b02

label_131:                                                  ; address: 0x001afc

001afc:  0e5f  movlw   0x5f
001afe:  6ff4  movwf   0xf4, B                              ; reg: 0x0f4
001b00:  0e30  movlw   0x30

label_132:                                                  ; address: 0x001b02

001b02:  6ff3  movwf   0xf3, B                              ; reg: 0x0f3
001b04:  c0f3  movff   0x0f3, (Common_RAM + 19)             ; reg2: 0x013
001b06:  f013
001b08:  c0f4  movff   0x0f4, (Common_RAM + 20)             ; reg2: 0x014
001b0a:  f014
001b0c:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
001b0e:  f01c
001b10:  0100  movlb   0x0
001b12:  b5a4  btfsc   0xa4, 0x2, B                         ; reg: 0x0a4
001b14:  d004  bra     label_133                            ; dest: 0x001b1e
001b16:  0e5f  movlw   0x5f
001b18:  6ff6  movwf   0xf6, B                              ; reg: 0x0f6
001b1a:  0e6c  movlw   0x6c
001b1c:  d003  bra     label_134                            ; dest: 0x001b24

label_133:                                                  ; address: 0x001b1e

001b1e:  0e5f  movlw   0x5f
001b20:  6ff6  movwf   0xf6, B                              ; reg: 0x0f6
001b22:  0e58  movlw   0x58

label_134:                                                  ; address: 0x001b24

001b24:  6ff5  movwf   0xf5, B                              ; reg: 0x0f5
001b26:  c0f5  movff   0x0f5, (Common_RAM + 19)             ; reg2: 0x013
001b28:  f013
001b2a:  c0f6  movff   0x0f6, (Common_RAM + 20)             ; reg2: 0x014
001b2c:  f014
001b2e:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
001b30:  f01c
001b32:  0100  movlb   0x0
001b34:  b7a4  btfsc   0xa4, 0x3, B                         ; reg: 0x0a4
001b36:  d004  bra     label_135                            ; dest: 0x001b40
001b38:  0e5f  movlw   0x5f
001b3a:  6ff8  movwf   0xf8, B                              ; reg: 0x0f8
001b3c:  0e94  movlw   0x94
001b3e:  d003  bra     label_136                            ; dest: 0x001b46

label_135:                                                  ; address: 0x001b40

001b40:  0e5f  movlw   0x5f
001b42:  6ff8  movwf   0xf8, B                              ; reg: 0x0f8
001b44:  0e80  movlw   0x80

label_136:                                                  ; address: 0x001b46

001b46:  6ff7  movwf   0xf7, B                              ; reg: 0x0f7
001b48:  c0f7  movff   0x0f7, (Common_RAM + 19)             ; reg2: 0x013
001b4a:  f013
001b4c:  c0f8  movff   0x0f8, (Common_RAM + 20)             ; reg2: 0x014
001b4e:  f014
001b50:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
001b52:  f01c
001b54:  0100  movlb   0x0
001b56:  b9a4  btfsc   0xa4, 0x4, B                         ; reg: 0x0a4
001b58:  d004  bra     label_137                            ; dest: 0x001b62
001b5a:  0e5f  movlw   0x5f
001b5c:  6ffa  movwf   0xfa, B                              ; reg: 0x0fa
001b5e:  0ebc  movlw   0xbc
001b60:  d003  bra     label_138                            ; dest: 0x001b68

label_137:                                                  ; address: 0x001b62

001b62:  0e5f  movlw   0x5f
001b64:  6ffa  movwf   0xfa, B                              ; reg: 0x0fa
001b66:  0ea8  movlw   0xa8

label_138:                                                  ; address: 0x001b68

001b68:  6ff9  movwf   0xf9, B                              ; reg: 0x0f9
001b6a:  c0f9  movff   0x0f9, (Common_RAM + 19)             ; reg2: 0x013
001b6c:  f013
001b6e:  c0fa  movff   0x0fa, (Common_RAM + 20)             ; reg2: 0x014
001b70:  f014
001b72:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
001b74:  f01c
001b76:  0100  movlb   0x0
001b78:  bba4  btfsc   0xa4, 0x5, B                         ; reg: 0x0a4
001b7a:  d004  bra     label_139                            ; dest: 0x001b84
001b7c:  0e5f  movlw   0x5f
001b7e:  6ffc  movwf   0xfc, B                              ; reg: 0x0fc
001b80:  0ee4  movlw   0xe4
001b82:  d003  bra     label_140                            ; dest: 0x001b8a

label_139:                                                  ; address: 0x001b84

001b84:  0e5f  movlw   0x5f
001b86:  6ffc  movwf   0xfc, B                              ; reg: 0x0fc
001b88:  0ed0  movlw   0xd0

label_140:                                                  ; address: 0x001b8a

001b8a:  6ffb  movwf   0xfb, B                              ; reg: 0x0fb
001b8c:  c0fb  movff   0x0fb, (Common_RAM + 19)             ; reg2: 0x013
001b8e:  f013
001b90:  c0fc  movff   0x0fc, (Common_RAM + 20)             ; reg2: 0x014
001b92:  f014
001b94:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
001b96:  f01c
001b98:  0e05  movlw   0x05
001b9a:  0100  movlb   0x0
001b9c:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001b9e:  51fd  movf    0xfd, W, B                           ; reg: 0x0fd
001ba0:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001ba2:  ecd1  call    function_085, 0x0                    ; dest: 0x0045a2
001ba4:  f022
001ba6:  0100  movlb   0x0
001ba8:  9d7e  bcf     0x7e, 0x6, B                         ; reg: 0x07e

label_141:                                                  ; address: 0x001baa

001baa:  a97e  btfss   0x7e, 0x4, B                         ; reg: 0x07e
001bac:  d00d  bra     label_142                            ; dest: 0x001bc8
001bae:  ec80  call    function_008, 0x0                    ; dest: 0x002100
001bb0:  f010
001bb2:  0100  movlb   0x0
001bb4:  997e  bcf     0x7e, 0x4, B                         ; reg: 0x07e
001bb6:  83bd  bsf     0xbd, 0x1, B                         ; reg: 0x0bd
001bb8:  0e05  movlw   0x05
001bba:  6fc1  movwf   0xc1, B                              ; reg: 0x0c1
001bbc:  51fd  movf    0xfd, W, B                           ; reg: 0x0fd
001bbe:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001bc0:  ecd1  call    function_085, 0x0                    ; dest: 0x0045a2
001bc2:  f022
001bc4:  ec53  call    function_112, 0x0                    ; dest: 0x0048a6
001bc6:  f024

label_142:                                                  ; address: 0x001bc8

001bc8:  0100  movlb   0x0
001bca:  a17f  btfss   0x7f, 0x0, B                         ; reg: 0x07f
001bcc:  d004  bra     label_143                            ; dest: 0x001bd6
001bce:  917f  bcf     0x7f, 0x0, B                         ; reg: 0x07f
001bd0:  85bd  bsf     0xbd, 0x2, B                         ; reg: 0x0bd
001bd2:  ec53  call    function_112, 0x0                    ; dest: 0x0048a6
001bd4:  f024

label_143:                                                  ; address: 0x001bd6

001bd6:  0100  movlb   0x0
001bd8:  a37f  btfss   0x7f, 0x1, B                         ; reg: 0x07f
001bda:  d004  bra     label_144                            ; dest: 0x001be4
001bdc:  937f  bcf     0x7f, 0x1, B                         ; reg: 0x07f
001bde:  85bd  bsf     0xbd, 0x2, B                         ; reg: 0x0bd
001be0:  ec53  call    function_112, 0x0                    ; dest: 0x0048a6
001be2:  f024

label_144:                                                  ; address: 0x001be4

001be4:  0012  return  0x0

function_006:                                               ; address: 0x001be6

001be6:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009
001be8:  d147  bra     label_191                            ; dest: 0x001e78

label_145:                                                  ; address: 0x001bea

001bea:  ec39  call    function_109, 0x0                    ; dest: 0x004872
001bec:  f024
001bee:  0900  iorlw   0x00
001bf0:  e101  bnz     label_146
001bf2:  d144  bra     label_192                            ; dest: 0x001e7c

label_146:                                                  ; address: 0x001bf4

001bf4:  ecfd  call    function_087, 0x0                    ; dest: 0x0045fa
001bf6:  f022
001bf8:  6e0a  movwf   (Common_RAM + 10), A                 ; reg: 0x00a
001bfa:  0e7f  movlw   0x7f
001bfc:  640a  cpfsgt  (Common_RAM + 10), A                 ; reg: 0x00a
001bfe:  d021  bra     label_150                            ; dest: 0x001c42
001c00:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
001c02:  0ab0  xorlw   0xb0
001c04:  e104  bnz     label_147
001c06:  0e01  movlw   0x01
001c08:  6f98  movwf   0x98, B                              ; reg: 0x098
001c0a:  905e  bcf     (Common_RAM + 94), 0x0, A            ; reg: 0x05e
001c0c:  d014  bra     label_149                            ; dest: 0x001c36

label_147:                                                  ; address: 0x001c0e

001c0e:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
001c10:  0ab1  xorlw   0xb1
001c12:  e104  bnz     label_148
001c14:  0e01  movlw   0x01
001c16:  6f98  movwf   0x98, B                              ; reg: 0x098
001c18:  805e  bsf     (Common_RAM + 94), 0x0, A            ; reg: 0x05e
001c1a:  d00d  bra     label_149                            ; dest: 0x001c36

label_148:                                                  ; address: 0x001c1c

001c1c:  6b98  clrf    0x98, B                              ; reg: 0x098
001c1e:  905e  bcf     (Common_RAM + 94), 0x0, A            ; reg: 0x05e
001c20:  c00a  movff   (Common_RAM + 10), (Common_RAM + 5)  ; reg1: 0x00a, reg2: 0x005
001c22:  f005
001c24:  0ef0  movlw   0xf0
001c26:  1605  andwf   (Common_RAM + 5), F, A               ; reg: 0x005
001c28:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
001c2a:  0ab0  xorlw   0xb0
001c2c:  e104  bnz     label_149
001c2e:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
001c30:  0abf  xorlw   0xbf
001c32:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001c34:  060a  decf    (Common_RAM + 10), F, A              ; reg: 0x00a

label_149:                                                  ; address: 0x001c36

001c36:  b05e  btfsc   (Common_RAM + 94), 0x0, A            ; reg: 0x05e
001c38:  d123  bra     label_193                            ; dest: 0x001e80
001c3a:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
001c3c:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001c3e:  f024
001c40:  d11f  bra     label_193                            ; dest: 0x001e80

label_150:                                                  ; address: 0x001c42

001c42:  b05e  btfsc   (Common_RAM + 94), 0x0, A            ; reg: 0x05e
001c44:  d006  bra     label_151                            ; dest: 0x001c52
001c46:  0e02  movlw   0x02
001c48:  5d98  subwf   0x98, W, B                           ; reg: 0x098
001c4a:  e203  bc      label_151
001c4c:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
001c4e:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001c50:  f024

label_151:                                                  ; address: 0x001c52

001c52:  0100  movlb   0x0
001c54:  5198  movf    0x98, W, B                           ; reg: 0x098
001c56:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001c58:  2b98  incf    0x98, F, B                           ; reg: 0x098
001c5a:  0e02  movlw   0x02
001c5c:  5d98  subwf   0x98, W, B                           ; reg: 0x098
001c5e:  e201  bc      label_152
001c60:  d10f  bra     label_193                            ; dest: 0x001e80

label_152:                                                  ; address: 0x001c62

001c62:  5198  movf    0x98, W, B                           ; reg: 0x098
001c64:  0a02  xorlw   0x02
001c66:  e103  bnz     label_153
001c68:  c00a  movff   (Common_RAM + 10), 0x0a2             ; reg1: 0x00a
001c6a:  f0a2
001c6c:  d109  bra     label_193                            ; dest: 0x001e80

label_153:                                                  ; address: 0x001c6e

001c6e:  c00a  movff   (Common_RAM + 10), 0x0a3             ; reg1: 0x00a
001c70:  f0a3
001c72:  c00a  movff   (Common_RAM + 10), 0x0bc             ; reg1: 0x00a
001c74:  f0bc
001c76:  8c5e  bsf     (Common_RAM + 94), 0x6, A            ; reg: 0x05e
001c78:  0e01  movlw   0x01
001c7a:  6f98  movwf   0x98, B                              ; reg: 0x098
001c7c:  d0d8  bra     label_185                            ; dest: 0x001e2e

label_154:                                                  ; address: 0x001c7e

001c7e:  0e01  movlw   0x01
001c80:  b65e  btfsc   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
001c82:  0e00  movlw   0x00
001c84:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
001c86:  4605  rlncf   (Common_RAM + 5), F, A               ; reg: 0x005
001c88:  4605  rlncf   (Common_RAM + 5), F, A               ; reg: 0x005
001c8a:  517e  movf    0x7e, W, B                           ; reg: 0x07e
001c8c:  1805  xorwf   (Common_RAM + 5), W, A               ; reg: 0x005
001c8e:  0bfb  andlw   0xfb
001c90:  1805  xorwf   (Common_RAM + 5), W, A               ; reg: 0x005
001c92:  6f7e  movwf   0x7e, B                              ; reg: 0x07e
001c94:  b57e  btfsc   0x7e, 0x2, B                         ; reg: 0x07e
001c96:  865e  bsf     (Common_RAM + 94), 0x3, A            ; reg: 0x05e
001c98:  d0e9  bra     label_190                            ; dest: 0x001e6c

label_155:                                                  ; address: 0x001c9a

001c9a:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
001c9c:  d002  bra     label_156                            ; dest: 0x001ca2
001c9e:  857e  bsf     0x7e, 0x2, B                         ; reg: 0x07e
001ca0:  d002  bra     label_157                            ; dest: 0x001ca6

label_156:                                                  ; address: 0x001ca2

001ca2:  0100  movlb   0x0
001ca4:  957e  bcf     0x7e, 0x2, B                         ; reg: 0x07e

label_157:                                                  ; address: 0x001ca6

001ca6:  b57e  btfsc   0x7e, 0x2, B                         ; reg: 0x07e
001ca8:  965e  bcf     (Common_RAM + 94), 0x3, A            ; reg: 0x05e
001caa:  d0e0  bra     label_190                            ; dest: 0x001e6c

label_158:                                                  ; address: 0x001cac

001cac:  b794  btfsc   0x94, 0x3, B                         ; reg: 0x094
001cae:  d013  bra     label_165                            ; dest: 0x001cd6
001cb0:  885e  bsf     (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001cb2:  0e01  movlw   0x01
001cb4:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001cb6:  0e00  movlw   0x00
001cb8:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
001cba:  aa5e  btfss   (Common_RAM + 94), 0x5, A            ; reg: 0x05e
001cbc:  d002  bra     label_159                            ; dest: 0x001cc2
001cbe:  0e01  movlw   0x01
001cc0:  d001  bra     label_160                            ; dest: 0x001cc4

label_159:                                                  ; address: 0x001cc2

001cc2:  0e00  movlw   0x00

label_160:                                                  ; address: 0x001cc4

001cc4:  1a05  xorwf   (Common_RAM + 5), F, A               ; reg: 0x005
001cc6:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2

label_161:                                                  ; address: 0x001cc8

001cc8:  8b7e  bsf     0x7e, 0x5, B                         ; reg: 0x07e

label_162:                                                  ; address: 0x001cca

001cca:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001ccc:  d002  bra     label_163                            ; dest: 0x001cd2
001cce:  8a5e  bsf     (Common_RAM + 94), 0x5, A            ; reg: 0x05e
001cd0:  d001  bra     label_164                            ; dest: 0x001cd4

label_163:                                                  ; address: 0x001cd2

001cd2:  9a5e  bcf     (Common_RAM + 94), 0x5, A            ; reg: 0x05e

label_164:                                                  ; address: 0x001cd4

001cd4:  d0cb  bra     label_190                            ; dest: 0x001e6c

label_165:                                                  ; address: 0x001cd6

001cd6:  0e02  movlw   0x02
001cd8:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001cda:  0e03  movlw   0x03
001cdc:  6fbc  movwf   0xbc, B                              ; reg: 0x0bc
001cde:  9794  bcf     0x94, 0x3, B                         ; reg: 0x094
001ce0:  d0c5  bra     label_190                            ; dest: 0x001e6c

label_166:                                                  ; address: 0x001ce2

001ce2:  b794  btfsc   0x94, 0x3, B                         ; reg: 0x094
001ce4:  d7f8  bra     label_165                            ; dest: 0x001cd6
001ce6:  985e  bcf     (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001ce8:  0e01  movlw   0x01
001cea:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
001cec:  0e00  movlw   0x00
001cee:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
001cf0:  aa5e  btfss   (Common_RAM + 94), 0x5, A            ; reg: 0x05e
001cf2:  d7e7  bra     label_159                            ; dest: 0x001cc2
001cf4:  0e01  movlw   0x01
001cf6:  1a05  xorwf   (Common_RAM + 5), F, A               ; reg: 0x005
001cf8:  e1e7  bnz     label_161
001cfa:  d7e7  bra     label_162                            ; dest: 0x001cca

label_167:                                                  ; address: 0x001cfc

001cfc:  51a3  movf    0xa3, W, B                           ; reg: 0x0a3
001cfe:  e0cd  bz      label_155
001d00:  0a01  xorlw   0x01
001d02:  e0bd  bz      label_154
001d04:  0a03  xorlw   0x03
001d06:  e0d2  bz      label_158
001d08:  0a01  xorlw   0x01
001d0a:  e0eb  bz      label_166
001d0c:  d0af  bra     label_190                            ; dest: 0x001e6c

label_168:                                                  ; address: 0x001d0e

001d0e:  eccb  call    function_050, 0x0                    ; dest: 0x003b96
001d10:  f01d
001d12:  d0ac  bra     label_190                            ; dest: 0x001e6c

label_169:                                                  ; address: 0x001d14

001d14:  b194  btfsc   0x94, 0x0, B                         ; reg: 0x094
001d16:  d005  bra     label_170                            ; dest: 0x001d22
001d18:  c0a3  movff   0x0a3, 0x099
001d1a:  f099
001d1c:  c099  movff   0x099, 0x0b3
001d1e:  f0b3
001d20:  d0a5  bra     label_190                            ; dest: 0x001e6c

label_170:                                                  ; address: 0x001d22

001d22:  c099  movff   0x099, 0x0bc
001d24:  f0bc
001d26:  9194  bcf     0x94, 0x0, B                         ; reg: 0x094
001d28:  d0a1  bra     label_190                            ; dest: 0x001e6c

label_171:                                                  ; address: 0x001d2a

001d2a:  b394  btfsc   0x94, 0x1, B                         ; reg: 0x094
001d2c:  d029  bra     label_174                            ; dest: 0x001d80
001d2e:  0ea0  movlw   0xa0
001d30:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
001d32:  6806  setf    (Common_RAM + 6), A                  ; reg: 0x006
001d34:  51a3  movf    0xa3, W, B                           ; reg: 0x0a3
001d36:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
001d38:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
001d3a:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
001d3c:  2607  addwf   (Common_RAM + 7), F, A               ; reg: 0x007
001d3e:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
001d40:  2208  addwfc  (Common_RAM + 8), F, A               ; reg: 0x008
001d42:  c007  movff   (Common_RAM + 7), 0x06e              ; reg1: 0x007
001d44:  f06e
001d46:  c008  movff   (Common_RAM + 8), 0x06f              ; reg1: 0x008
001d48:  f06f
001d4a:  0e00  movlw   0x00
001d4c:  bf6f  btfsc   0x6f, 0x7, B                         ; reg: 0x06f
001d4e:  0eff  movlw   0xff
001d50:  6f70  movwf   0x70, B                              ; reg: 0x070
001d52:  6f71  movwf   0x71, B                              ; reg: 0x071
001d54:  1969  xorwf   0x69, W, B                           ; reg: 0x069
001d56:  e108  bnz     label_172
001d58:  5168  movf    0x68, W, B                           ; reg: 0x068
001d5a:  1970  xorwf   0x70, W, B                           ; reg: 0x070
001d5c:  e105  bnz     label_172
001d5e:  5167  movf    0x67, W, B                           ; reg: 0x067
001d60:  196f  xorwf   0x6f, W, B                           ; reg: 0x06f
001d62:  e102  bnz     label_172
001d64:  5166  movf    0x66, W, B                           ; reg: 0x066
001d66:  196e  xorwf   0x6e, W, B                           ; reg: 0x06e

label_172:                                                  ; address: 0x001d68

001d68:  e101  bnz     label_173
001d6a:  d080  bra     label_190                            ; dest: 0x001e6c

label_173:                                                  ; address: 0x001d6c

001d6c:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
001d6e:  c06e  movff   0x06e, 0x066
001d70:  f066
001d72:  c06f  movff   0x06f, 0x067
001d74:  f067
001d76:  c070  movff   0x070, 0x068
001d78:  f068
001d7a:  c071  movff   0x071, 0x069
001d7c:  f069
001d7e:  d076  bra     label_190                            ; dest: 0x001e6c

label_174:                                                  ; address: 0x001d80

001d80:  516e  movf    0x6e, W, B                           ; reg: 0x06e
001d82:  0f60  addlw   0x60
001d84:  6fbc  movwf   0xbc, B                              ; reg: 0x0bc
001d86:  9394  bcf     0x94, 0x1, B                         ; reg: 0x094
001d88:  d071  bra     label_190                            ; dest: 0x001e6c

label_175:                                                  ; address: 0x001d8a

001d8a:  51a3  movf    0xa3, W, B                           ; reg: 0x0a3
001d8c:  0a29  xorlw   0x29
001d8e:  e16e  bnz     label_190
001d90:  ecfe  call    function_103, 0x0                    ; dest: 0x0047fc
001d92:  f023
001d94:  d06b  bra     label_190                            ; dest: 0x001e6c

label_176:                                                  ; address: 0x001d96

001d96:  c0a3  movff   0x0a3, 0x060
001d98:  f060
001d9a:  51a5  movf    0xa5, W, B                           ; reg: 0x0a5
001d9c:  1960  xorwf   0x60, W, B                           ; reg: 0x060
001d9e:  e066  bz      label_190
001da0:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001da2:  c060  movff   0x060, 0x0a5
001da4:  f0a5
001da6:  d062  bra     label_190                            ; dest: 0x001e6c

label_177:                                                  ; address: 0x001da8

001da8:  c0a3  movff   0x0a3, 0x061
001daa:  f061
001dac:  5161  movf    0x61, W, B                           ; reg: 0x061
001dae:  19a6  xorwf   0xa6, W, B                           ; reg: 0x0a6
001db0:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001db2:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001db4:  c061  movff   0x061, 0x0a6
001db6:  f0a6
001db8:  d059  bra     label_190                            ; dest: 0x001e6c

label_178:                                                  ; address: 0x001dba

001dba:  c0a3  movff   0x0a3, 0x062
001dbc:  f062
001dbe:  5162  movf    0x62, W, B                           ; reg: 0x062
001dc0:  19a7  xorwf   0xa7, W, B                           ; reg: 0x0a7
001dc2:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001dc4:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001dc6:  c062  movff   0x062, 0x0a7
001dc8:  f0a7
001dca:  d050  bra     label_190                            ; dest: 0x001e6c

label_179:                                                  ; address: 0x001dcc

001dcc:  c0a3  movff   0x0a3, 0x063
001dce:  f063
001dd0:  5163  movf    0x63, W, B                           ; reg: 0x063
001dd2:  19a8  xorwf   0xa8, W, B                           ; reg: 0x0a8
001dd4:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001dd6:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001dd8:  c063  movff   0x063, 0x0a8
001dda:  f0a8
001ddc:  d047  bra     label_190                            ; dest: 0x001e6c

label_180:                                                  ; address: 0x001dde

001dde:  c0a3  movff   0x0a3, 0x064
001de0:  f064
001de2:  5164  movf    0x64, W, B                           ; reg: 0x064
001de4:  19a9  xorwf   0xa9, W, B                           ; reg: 0x0a9
001de6:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001de8:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001dea:  c064  movff   0x064, 0x0a9
001dec:  f0a9
001dee:  d03e  bra     label_190                            ; dest: 0x001e6c

label_181:                                                  ; address: 0x001df0

001df0:  c0a3  movff   0x0a3, 0x065
001df2:  f065
001df4:  5165  movf    0x65, W, B                           ; reg: 0x065
001df6:  19aa  xorwf   0xaa, W, B                           ; reg: 0x0aa
001df8:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001dfa:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
001dfc:  c065  movff   0x065, 0x0aa
001dfe:  f0aa
001e00:  d035  bra     label_190                            ; dest: 0x001e6c

label_182:                                                  ; address: 0x001e02

001e02:  b994  btfsc   0x94, 0x4, B                         ; reg: 0x094
001e04:  d007  bra     label_183                            ; dest: 0x001e14
001e06:  51b8  movf    0xb8, W, B                           ; reg: 0x0b8
001e08:  19a3  xorwf   0xa3, W, B                           ; reg: 0x0a3
001e0a:  e030  bz      label_190
001e0c:  c0a3  movff   0x0a3, 0x0b8
001e0e:  f0b8
001e10:  817f  bsf     0x7f, 0x0, B                         ; reg: 0x07f
001e12:  d02c  bra     label_190                            ; dest: 0x001e6c

label_183:                                                  ; address: 0x001e14

001e14:  c0b8  movff   0x0b8, 0x0bc
001e16:  f0bc
001e18:  9994  bcf     0x94, 0x4, B                         ; reg: 0x094
001e1a:  d028  bra     label_190                            ; dest: 0x001e6c

label_184:                                                  ; address: 0x001e1c

001e1c:  c0a3  movff   0x0a3, 0x0c3
001e1e:  f0c3
001e20:  51b2  movf    0xb2, W, B                           ; reg: 0x0b2
001e22:  19c3  xorwf   0xc3, W, B                           ; reg: 0x0c3
001e24:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001e26:  81bd  bsf     0xbd, 0x0, B                         ; reg: 0x0bd
001e28:  c0c3  movff   0x0c3, 0x0b2
001e2a:  f0b2
001e2c:  d01f  bra     label_190                            ; dest: 0x001e6c

label_185:                                                  ; address: 0x001e2e

001e2e:  51a2  movf    0xa2, W, B                           ; reg: 0x0a2
001e30:  0a03  xorlw   0x03
001e32:  e101  bnz     label_186
001e34:  d763  bra     label_167                            ; dest: 0x001cfc

label_186:                                                  ; address: 0x001e36

001e36:  0a07  xorlw   0x07
001e38:  e101  bnz     label_187
001e3a:  d769  bra     label_168                            ; dest: 0x001d0e

label_187:                                                  ; address: 0x001e3c

001e3c:  0a02  xorlw   0x02
001e3e:  e101  bnz     label_188
001e40:  d769  bra     label_169                            ; dest: 0x001d14

label_188:                                                  ; address: 0x001e42

001e42:  0a01  xorlw   0x01
001e44:  e101  bnz     label_189
001e46:  d771  bra     label_171                            ; dest: 0x001d2a

label_189:                                                  ; address: 0x001e48

001e48:  0a17  xorlw   0x17
001e4a:  e09f  bz      label_175
001e4c:  0a07  xorlw   0x07
001e4e:  e0a3  bz      label_176
001e50:  0a0f  xorlw   0x0f
001e52:  e0aa  bz      label_177
001e54:  0a01  xorlw   0x01
001e56:  e0b1  bz      label_178
001e58:  0a03  xorlw   0x03
001e5a:  e0b8  bz      label_179
001e5c:  0a01  xorlw   0x01
001e5e:  e0bf  bz      label_180
001e60:  0a07  xorlw   0x07
001e62:  e0c6  bz      label_181
001e64:  0a01  xorlw   0x01
001e66:  e0cd  bz      label_182
001e68:  0a03  xorlw   0x03
001e6a:  e0d8  bz      label_184

label_190:                                                  ; address: 0x001e6c

001e6c:  ac5e  btfss   (Common_RAM + 94), 0x6, A            ; reg: 0x05e
001e6e:  d008  bra     label_193                            ; dest: 0x001e80
001e70:  0100  movlb   0x0
001e72:  51bc  movf    0xbc, W, B                           ; reg: 0x0bc
001e74:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
001e76:  f024

label_191:                                                  ; address: 0x001e78

001e78:  9c5e  bcf     (Common_RAM + 94), 0x6, A            ; reg: 0x05e
001e7a:  d002  bra     label_193                            ; dest: 0x001e80

label_192:                                                  ; address: 0x001e7c

001e7c:  0e01  movlw   0x01
001e7e:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009

label_193:                                                  ; address: 0x001e80

001e80:  5009  movf    (Common_RAM + 9), W, A               ; reg: 0x009
001e82:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
001e84:  0012  return  0x0
001e86:  d6b1  bra     label_145                            ; dest: 0x001bea

function_007:                                               ; address: 0x001e88

001e88:  0e00  movlw   0x00
001e8a:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001e8c:  6a03  clrf    (Common_RAM + 3), A                  ; reg: 0x003
001e8e:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001e90:  f024
001e92:  0100  movlb   0x0
001e94:  6f71  movwf   0x71, B                              ; reg: 0x071
001e96:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001e98:  0e01  movlw   0x01
001e9a:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001e9c:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001e9e:  f024
001ea0:  0100  movlb   0x0
001ea2:  6f70  movwf   0x70, B                              ; reg: 0x070
001ea4:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001ea6:  0e02  movlw   0x02
001ea8:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001eaa:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001eac:  f024
001eae:  0100  movlb   0x0
001eb0:  6f6f  movwf   0x6f, B                              ; reg: 0x06f
001eb2:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001eb4:  0e03  movlw   0x03
001eb6:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001eb8:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001eba:  f024
001ebc:  0100  movlb   0x0
001ebe:  6f6e  movwf   0x6e, B                              ; reg: 0x06e
001ec0:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001ec2:  0e04  movlw   0x04
001ec4:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001ec6:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001ec8:  f024
001eca:  0100  movlb   0x0
001ecc:  6f99  movwf   0x99, B                              ; reg: 0x099
001ece:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001ed0:  0e07  movlw   0x07
001ed2:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001ed4:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001ed6:  f024
001ed8:  0100  movlb   0x0
001eda:  6f60  movwf   0x60, B                              ; reg: 0x060
001edc:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001ede:  0e08  movlw   0x08
001ee0:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001ee2:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001ee4:  f024
001ee6:  0100  movlb   0x0
001ee8:  6f61  movwf   0x61, B                              ; reg: 0x061
001eea:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001eec:  0e09  movlw   0x09
001eee:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001ef0:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001ef2:  f024
001ef4:  0100  movlb   0x0
001ef6:  6f62  movwf   0x62, B                              ; reg: 0x062
001ef8:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001efa:  0e0a  movlw   0x0a
001efc:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001efe:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001f00:  f024
001f02:  0100  movlb   0x0
001f04:  6f63  movwf   0x63, B                              ; reg: 0x063
001f06:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001f08:  0e0b  movlw   0x0b
001f0a:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001f0c:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001f0e:  f024
001f10:  0100  movlb   0x0
001f12:  6f64  movwf   0x64, B                              ; reg: 0x064
001f14:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001f16:  0e0c  movlw   0x0c
001f18:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001f1a:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001f1c:  f024
001f1e:  0100  movlb   0x0
001f20:  6f65  movwf   0x65, B                              ; reg: 0x065
001f22:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001f24:  0e0d  movlw   0x0d
001f26:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001f28:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001f2a:  f024
001f2c:  6e5f  movwf   (Common_RAM + 95), A                 ; reg: 0x05f
001f2e:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001f30:  0e14  movlw   0x14
001f32:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001f34:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001f36:  f024
001f38:  0100  movlb   0x0
001f3a:  6fc3  movwf   0xc3, B                              ; reg: 0x0c3
001f3c:  5171  movf    0x71, W, B                           ; reg: 0x071
001f3e:  0a80  xorlw   0x80
001f40:  0f80  addlw   0x80
001f42:  e108  bnz     label_194
001f44:  0e00  movlw   0x00
001f46:  5d70  subwf   0x70, W, B                           ; reg: 0x070
001f48:  e105  bnz     label_194
001f4a:  0e00  movlw   0x00
001f4c:  5d6f  subwf   0x6f, W, B                           ; reg: 0x06f
001f4e:  e102  bnz     label_194
001f50:  0e13  movlw   0x13
001f52:  5d6e  subwf   0x6e, W, B                           ; reg: 0x06e

label_194:                                                  ; address: 0x001f54

001f54:  e305  bnc     label_195
001f56:  0ea0  movlw   0xa0
001f58:  6f6e  movwf   0x6e, B                              ; reg: 0x06e
001f5a:  696f  setf    0x6f, B                              ; reg: 0x06f
001f5c:  6970  setf    0x70, B                              ; reg: 0x070
001f5e:  6971  setf    0x71, B                              ; reg: 0x071

label_195:                                                  ; address: 0x001f60

001f60:  0e08  movlw   0x08
001f62:  6599  cpfsgt  0x99, B                              ; reg: 0x099
001f64:  d002  bra     label_196                            ; dest: 0x001f6a
001f66:  0e01  movlw   0x01
001f68:  6f99  movwf   0x99, B                              ; reg: 0x099

label_196:                                                  ; address: 0x001f6a

001f6a:  0e03  movlw   0x03
001f6c:  6560  cpfsgt  0x60, B                              ; reg: 0x060
001f6e:  d001  bra     label_197                            ; dest: 0x001f72
001f70:  6b60  clrf    0x60, B                              ; reg: 0x060

label_197:                                                  ; address: 0x001f72

001f72:  ee20  lfsr    0x2, 0x061
001f74:  f061
001f76:  0e03  movlw   0x03
001f78:  64df  cpfsgt  INDF2, A                             ; reg: 0xfdf
001f7a:  d001  bra     label_198                            ; dest: 0x001f7e
001f7c:  6b61  clrf    0x61, B                              ; reg: 0x061

label_198:                                                  ; address: 0x001f7e

001f7e:  ee20  lfsr    0x2, 0x062
001f80:  f062
001f82:  0e03  movlw   0x03
001f84:  64df  cpfsgt  INDF2, A                             ; reg: 0xfdf
001f86:  d001  bra     label_199                            ; dest: 0x001f8a
001f88:  6b62  clrf    0x62, B                              ; reg: 0x062

label_199:                                                  ; address: 0x001f8a

001f8a:  ee20  lfsr    0x2, 0x063
001f8c:  f063
001f8e:  0e03  movlw   0x03
001f90:  64df  cpfsgt  INDF2, A                             ; reg: 0xfdf
001f92:  d002  bra     label_200                            ; dest: 0x001f98
001f94:  0e01  movlw   0x01
001f96:  6f63  movwf   0x63, B                              ; reg: 0x063

label_200:                                                  ; address: 0x001f98

001f98:  ee20  lfsr    0x2, 0x064
001f9a:  f064
001f9c:  0e03  movlw   0x03
001f9e:  64df  cpfsgt  INDF2, A                             ; reg: 0xfdf
001fa0:  d002  bra     label_201                            ; dest: 0x001fa6
001fa2:  0e01  movlw   0x01
001fa4:  6f64  movwf   0x64, B                              ; reg: 0x064

label_201:                                                  ; address: 0x001fa6

001fa6:  ee20  lfsr    0x2, 0x065
001fa8:  f065
001faa:  0e03  movlw   0x03
001fac:  64df  cpfsgt  INDF2, A                             ; reg: 0xfdf
001fae:  d002  bra     label_202                            ; dest: 0x001fb4
001fb0:  0e01  movlw   0x01
001fb2:  6f64  movwf   0x64, B                              ; reg: 0x064

label_202:                                                  ; address: 0x001fb4

001fb4:  0e03  movlw   0x03
001fb6:  645f  cpfsgt  (Common_RAM + 95), A                 ; reg: 0x05f
001fb8:  d001  bra     label_203                            ; dest: 0x001fbc
001fba:  6e5f  movwf   (Common_RAM + 95), A                 ; reg: 0x05f

label_203:                                                  ; address: 0x001fbc

001fbc:  0e04  movlw   0x04
001fbe:  65c3  cpfsgt  0xc3, B                              ; reg: 0x0c3
001fc0:  d002  bra     label_204                            ; dest: 0x001fc6
001fc2:  0e01  movlw   0x01
001fc4:  6fc3  movwf   0xc3, B                              ; reg: 0x0c3

label_204:                                                  ; address: 0x001fc6

001fc6:  c06e  movff   0x06e, 0x066
001fc8:  f066
001fca:  c06f  movff   0x06f, 0x067
001fcc:  f067
001fce:  c070  movff   0x070, 0x068
001fd0:  f068
001fd2:  c071  movff   0x071, 0x069
001fd4:  f069
001fd6:  c099  movff   0x099, 0x0b3
001fd8:  f0b3
001fda:  c060  movff   0x060, 0x0a5
001fdc:  f0a5
001fde:  c061  movff   0x061, 0x0a6
001fe0:  f0a6
001fe2:  c062  movff   0x062, 0x0a7
001fe4:  f0a7
001fe6:  c063  movff   0x063, 0x0a8
001fe8:  f0a8
001fea:  c064  movff   0x064, 0x0a9
001fec:  f0a9
001fee:  c065  movff   0x065, 0x0aa
001ff0:  f0aa
001ff2:  c0c3  movff   0x0c3, 0x0b2
001ff4:  f0b2
001ff6:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
001ff8:  0e0f  movlw   0x0f
001ffa:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
001ffc:  ec42  call    function_110, 0x0                    ; dest: 0x004884
001ffe:  f024
002000:  0100  movlb   0x0
002002:  6fb4  movwf   0xb4, B                              ; reg: 0x0b4
002004:  29b4  incf    0xb4, W, B                           ; reg: 0x0b4
002006:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
002008:  91b4  bcf     0xb4, 0x0, B                         ; reg: 0x0b4
00200a:  c0b4  movff   0x0b4, 0x0b1
00200c:  f0b1
00200e:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002010:  0e0e  movlw   0x0e
002012:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002014:  ec42  call    function_110, 0x0                    ; dest: 0x004884
002016:  f024
002018:  0100  movlb   0x0
00201a:  6fb8  movwf   0xb8, B                              ; reg: 0x0b8
00201c:  0e03  movlw   0x03
00201e:  5db8  subwf   0xb8, W, B                           ; reg: 0x0b8
002020:  e202  bc      label_205
002022:  0e03  movlw   0x03
002024:  6fb8  movwf   0xb8, B                              ; reg: 0x0b8

label_205:                                                  ; address: 0x002026

002026:  0e04  movlw   0x04
002028:  65b8  cpfsgt  0xb8, B                              ; reg: 0x0b8
00202a:  d002  bra     label_206                            ; dest: 0x002030
00202c:  0e03  movlw   0x03
00202e:  6fb8  movwf   0xb8, B                              ; reg: 0x0b8

label_206:                                                  ; address: 0x002030

002030:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002032:  0e10  movlw   0x10
002034:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002036:  ec42  call    function_110, 0x0                    ; dest: 0x004884
002038:  f024
00203a:  0100  movlb   0x0
00203c:  6f9b  movwf   0x9b, B                              ; reg: 0x09b
00203e:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002040:  0e11  movlw   0x11
002042:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002044:  ec42  call    function_110, 0x0                    ; dest: 0x004884
002046:  f024
002048:  0100  movlb   0x0
00204a:  6f9c  movwf   0x9c, B                              ; reg: 0x09c
00204c:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
00204e:  0e12  movlw   0x12
002050:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002052:  ec42  call    function_110, 0x0                    ; dest: 0x004884
002054:  f024
002056:  0100  movlb   0x0
002058:  6f9d  movwf   0x9d, B                              ; reg: 0x09d
00205a:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
00205c:  0e13  movlw   0x13
00205e:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002060:  ec42  call    function_110, 0x0                    ; dest: 0x004884
002062:  f024
002064:  0100  movlb   0x0
002066:  6f9e  movwf   0x9e, B                              ; reg: 0x09e
002068:  0e12  movlw   0x12
00206a:  659b  cpfsgt  0x9b, B                              ; reg: 0x09b
00206c:  d001  bra     label_207                            ; dest: 0x002070
00206e:  6b9b  clrf    0x9b, B                              ; reg: 0x09b

label_207:                                                  ; address: 0x002070

002070:  0e12  movlw   0x12
002072:  659c  cpfsgt  0x9c, B                              ; reg: 0x09c
002074:  d001  bra     label_208                            ; dest: 0x002078
002076:  6b9c  clrf    0x9c, B                              ; reg: 0x09c

label_208:                                                  ; address: 0x002078

002078:  0e12  movlw   0x12
00207a:  659d  cpfsgt  0x9d, B                              ; reg: 0x09d
00207c:  d001  bra     label_209                            ; dest: 0x002080
00207e:  6b9d  clrf    0x9d, B                              ; reg: 0x09d

label_209:                                                  ; address: 0x002080

002080:  0e12  movlw   0x12
002082:  659e  cpfsgt  0x9e, B                              ; reg: 0x09e
002084:  d001  bra     label_210                            ; dest: 0x002088
002086:  6b9e  clrf    0x9e, B                              ; reg: 0x09e

label_210:                                                  ; address: 0x002088

002088:  c09b  movff   0x09b, 0x0ac
00208a:  f0ac
00208c:  c09c  movff   0x09c, 0x0ad
00208e:  f0ad
002090:  c09d  movff   0x09d, 0x0ae
002092:  f0ae
002094:  c09e  movff   0x09e, 0x0af
002096:  f0af
002098:  0e50  movlw   0x50
00209a:  6e0a  movwf   (Common_RAM + 10), A                 ; reg: 0x00a

label_211:                                                  ; address: 0x00209c

00209c:  0101  movlb   0x1
00209e:  0eb0  movlw   0xb0
0020a0:  240a  addwf   0x0a, W, A                           ; reg: 0x10a
0020a2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0020a4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0020a6:  0e00  movlw   0x00
0020a8:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0020aa:  c00a  movff   (Common_RAM + 10), (Common_RAM + 3)  ; reg1: 0x00a, reg2: 0x003
0020ac:  f003
0020ae:  6a04  clrf    0x04, A                              ; reg: 0x104
0020b0:  ec42  call    function_110, 0x0                    ; dest: 0x004884
0020b2:  f024
0020b4:  6edf  movwf   INDF2, A                             ; reg: 0xfdf
0020b6:  2a0a  incf    (Common_RAM + 10), F, A              ; reg: 0x00a
0020b8:  0e5e  movlw   0x5e
0020ba:  640a  cpfsgt  (Common_RAM + 10), A                 ; reg: 0x00a
0020bc:  d7ef  bra     label_211                            ; dest: 0x00209c
0020be:  0e60  movlw   0x60
0020c0:  6e0a  movwf   (Common_RAM + 10), A                 ; reg: 0x00a

label_212:                                                  ; address: 0x0020c2

0020c2:  0102  movlb   0x2
0020c4:  0e60  movlw   0x60
0020c6:  240a  addwf   0x0a, W, A                           ; reg: 0x20a
0020c8:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0020ca:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0020cc:  0e02  movlw   0x02
0020ce:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0020d0:  c00a  movff   (Common_RAM + 10), (Common_RAM + 3)  ; reg1: 0x00a, reg2: 0x003
0020d2:  f003
0020d4:  6a04  clrf    0x04, A                              ; reg: 0x204
0020d6:  ec42  call    function_110, 0x0                    ; dest: 0x004884
0020d8:  f024
0020da:  6edf  movwf   INDF2, A                             ; reg: 0xfdf
0020dc:  2a0a  incf    (Common_RAM + 10), F, A              ; reg: 0x00a
0020de:  0e7d  movlw   0x7d
0020e0:  640a  cpfsgt  (Common_RAM + 10), A                 ; reg: 0x00a
0020e2:  d7ef  bra     label_212                            ; dest: 0x0020c2
0020e4:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0020e6:  0e80  movlw   0x80
0020e8:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0020ea:  0e02  movlw   0x02
0020ec:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
0020ee:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0020f0:  f023
0020f2:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0020f4:  0e81  movlw   0x81
0020f6:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0020f8:  0e03  movlw   0x03
0020fa:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
0020fc:  ef6f  goto    function_094                         ; dest: 0x0046de
0020fe:  f023

function_008:                                               ; address: 0x002100

002100:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002102:  0ed7  movlw   0xd7
002104:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002106:  0e04  movlw   0x04
002108:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
00210a:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00210c:  f023
00210e:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002110:  0100  movlb   0x0
002112:  0edb  movlw   0xdb
002114:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002116:  0e04  movlw   0x04
002118:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
00211a:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00211c:  f023
00211e:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002120:  0100  movlb   0x0
002122:  0edf  movlw   0xdf
002124:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002126:  0e04  movlw   0x04
002128:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
00212a:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00212c:  f023
00212e:  0101  movlb   0x1
002130:  0e01  movlw   0x01
002132:  6e04  movwf   0x04, A                              ; reg: 0x104
002134:  0ed9  movlw   0xd9
002136:  6e03  movwf   0x03, A                              ; reg: 0x103
002138:  0e04  movlw   0x04
00213a:  6e05  movwf   0x05, A                              ; reg: 0x105
00213c:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00213e:  f023
002140:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002142:  0100  movlb   0x0
002144:  0ee3  movlw   0xe3
002146:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002148:  0e04  movlw   0x04
00214a:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
00214c:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
00214e:  f023
002150:  0101  movlb   0x1
002152:  0e01  movlw   0x01
002154:  6e04  movwf   0x04, A                              ; reg: 0x104
002156:  0edd  movlw   0xdd
002158:  6e03  movwf   0x03, A                              ; reg: 0x103
00215a:  0e04  movlw   0x04
00215c:  6e05  movwf   0x05, A                              ; reg: 0x105
00215e:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
002160:  f023
002162:  0101  movlb   0x1
002164:  0e01  movlw   0x01
002166:  6e04  movwf   0x04, A                              ; reg: 0x104
002168:  0ee1  movlw   0xe1
00216a:  6e03  movwf   0x03, A                              ; reg: 0x103
00216c:  0e04  movlw   0x04
00216e:  6e05  movwf   0x05, A                              ; reg: 0x105
002170:  ec9f  call    function_097, 0x0                    ; dest: 0x00473e
002172:  f023
002174:  ec5b  call    function_113, 0x0                    ; dest: 0x0048b6
002176:  f024
002178:  6a59  clrf    (Common_RAM + 89), A                 ; reg: 0x059

label_213:                                                  ; address: 0x00217a

00217a:  5059  movf    (Common_RAM + 89), W, A              ; reg: 0x059
00217c:  0100  movlb   0x0
00217e:  0f60  addlw   0x60
002180:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
002182:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
002184:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
002186:  ec24  call    function_078, 0x0                    ; dest: 0x004448
002188:  f022
00218a:  d01e  bra     label_220                            ; dest: 0x0021c8

label_214:                                                  ; address: 0x00218c

00218c:  c0a0  movff   0x0a0, 0x0d7
00218e:  f0d7
002190:  c0b9  movff   0x0b9, 0x0d8
002192:  f0d8
002194:  d025  bra     label_221                            ; dest: 0x0021e0

label_215:                                                  ; address: 0x002196

002196:  c0a0  movff   0x0a0, 0x0db
002198:  f0db
00219a:  c0b9  movff   0x0b9, 0x0dc
00219c:  f0dc
00219e:  d020  bra     label_221                            ; dest: 0x0021e0

label_216:                                                  ; address: 0x0021a0

0021a0:  c0a0  movff   0x0a0, 0x0df
0021a2:  f0df
0021a4:  c0b9  movff   0x0b9, 0x0e0
0021a6:  f0e0
0021a8:  d01b  bra     label_221                            ; dest: 0x0021e0

label_217:                                                  ; address: 0x0021aa

0021aa:  c0a0  movff   0x0a0, 0x1d9
0021ac:  f1d9
0021ae:  c0b9  movff   0x0b9, 0x1da
0021b0:  f1da
0021b2:  d016  bra     label_221                            ; dest: 0x0021e0

label_218:                                                  ; address: 0x0021b4

0021b4:  c0a0  movff   0x0a0, 0x0e4
0021b6:  f0e4
0021b8:  c0b9  movff   0x0b9, 0x0e5
0021ba:  f0e5
0021bc:  d011  bra     label_221                            ; dest: 0x0021e0

label_219:                                                  ; address: 0x0021be

0021be:  c0a0  movff   0x0a0, 0x1e0
0021c0:  f1e0
0021c2:  c0b9  movff   0x0b9, 0x1e1
0021c4:  f1e1
0021c6:  d00c  bra     label_221                            ; dest: 0x0021e0

label_220:                                                  ; address: 0x0021c8

0021c8:  5059  movf    (Common_RAM + 89), W, A              ; reg: 0x059
0021ca:  e0e0  bz      label_214
0021cc:  0a01  xorlw   0x01
0021ce:  e0e3  bz      label_215
0021d0:  0a03  xorlw   0x03
0021d2:  e0e6  bz      label_216
0021d4:  0a01  xorlw   0x01
0021d6:  e0e9  bz      label_217
0021d8:  0a07  xorlw   0x07
0021da:  e0ec  bz      label_218
0021dc:  0a01  xorlw   0x01
0021de:  e0ef  bz      label_219

label_221:                                                  ; address: 0x0021e0

0021e0:  2a59  incf    (Common_RAM + 89), F, A              ; reg: 0x059
0021e2:  0e05  movlw   0x05
0021e4:  6459  cpfsgt  (Common_RAM + 89), A                 ; reg: 0x059
0021e6:  d7c9  bra     label_213                            ; dest: 0x00217a
0021e8:  6a5a  clrf    (Common_RAM + 90), A                 ; reg: 0x05a
0021ea:  d03f  bra     label_229                            ; dest: 0x00226a

label_222:                                                  ; address: 0x0021ec

0021ec:  c0d7  movff   0x0d7, 0x06a
0021ee:  f06a
0021f0:  c0d8  movff   0x0d8, 0x06b
0021f2:  f06b
0021f4:  c0d9  movff   0x0d9, 0x06c
0021f6:  f06c
0021f8:  c0da  movff   0x0da, 0x06d
0021fa:  f06d
0021fc:  d044  bra     label_230                            ; dest: 0x002286

label_223:                                                  ; address: 0x0021fe

0021fe:  c0db  movff   0x0db, 0x06a
002200:  f06a
002202:  c0dc  movff   0x0dc, 0x06b
002204:  f06b
002206:  c0dd  movff   0x0dd, 0x06c
002208:  f06c
00220a:  c0de  movff   0x0de, 0x06d
00220c:  f06d
00220e:  d03b  bra     label_230                            ; dest: 0x002286

label_224:                                                  ; address: 0x002210

002210:  c0df  movff   0x0df, 0x06a
002212:  f06a
002214:  c0e0  movff   0x0e0, 0x06b
002216:  f06b
002218:  c0e1  movff   0x0e1, 0x06c
00221a:  f06c
00221c:  c0e2  movff   0x0e2, 0x06d
00221e:  f06d
002220:  d032  bra     label_230                            ; dest: 0x002286

label_225:                                                  ; address: 0x002222

002222:  c1d9  movff   0x1d9, 0x06a
002224:  f06a
002226:  c1da  movff   0x1da, 0x06b
002228:  f06b
00222a:  c1db  movff   0x1db, 0x06c
00222c:  f06c
00222e:  c1dc  movff   0x1dc, 0x06d
002230:  f06d
002232:  d029  bra     label_230                            ; dest: 0x002286

label_226:                                                  ; address: 0x002234

002234:  c0e3  movff   0x0e3, 0x06a
002236:  f06a
002238:  c0e4  movff   0x0e4, 0x06b
00223a:  f06b
00223c:  c0e5  movff   0x0e5, 0x06c
00223e:  f06c
002240:  c0e6  movff   0x0e6, 0x06d
002242:  f06d
002244:  d020  bra     label_230                            ; dest: 0x002286

label_227:                                                  ; address: 0x002246

002246:  c1dd  movff   0x1dd, 0x06a
002248:  f06a
00224a:  c1de  movff   0x1de, 0x06b
00224c:  f06b
00224e:  c1df  movff   0x1df, 0x06c
002250:  f06c
002252:  c1e0  movff   0x1e0, 0x06d
002254:  f06d
002256:  d017  bra     label_230                            ; dest: 0x002286

label_228:                                                  ; address: 0x002258

002258:  c1e1  movff   0x1e1, 0x06a
00225a:  f06a
00225c:  c1e2  movff   0x1e2, 0x06b
00225e:  f06b
002260:  c1e3  movff   0x1e3, 0x06c
002262:  f06c
002264:  c1e4  movff   0x1e4, 0x06d
002266:  f06d
002268:  d00e  bra     label_230                            ; dest: 0x002286

label_229:                                                  ; address: 0x00226a

00226a:  505a  movf    (Common_RAM + 90), W, A              ; reg: 0x05a
00226c:  e0bf  bz      label_222
00226e:  0a01  xorlw   0x01
002270:  e0c6  bz      label_223
002272:  0a03  xorlw   0x03
002274:  e0cd  bz      label_224
002276:  0a01  xorlw   0x01
002278:  e0d4  bz      label_225
00227a:  0a07  xorlw   0x07
00227c:  e0db  bz      label_226
00227e:  0a01  xorlw   0x01
002280:  e0e2  bz      label_227
002282:  0a03  xorlw   0x03
002284:  e0e9  bz      label_228

label_230:                                                  ; address: 0x002286

002286:  80c5  bsf     SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0

label_231:                                                  ; address: 0x002288

002288:  b0c5  btfsc   SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0
00228a:  d7fe  bra     label_231                            ; dest: 0x002288
00228c:  0e68  movlw   0x68
00228e:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
002290:  f01f
002292:  0101  movlb   0x1
002294:  0e0f  movlw   0x0f
002296:  245a  addwf   0x5a, W, A                           ; reg: 0x15a
002298:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
00229a:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00229c:  0e01  movlw   0x01
00229e:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0022a0:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0022a2:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
0022a4:  f01f
0022a6:  6a5b  clrf    (Common_RAM + 91), A                 ; reg: 0x05b

label_232:                                                  ; address: 0x0022a8

0022a8:  505b  movf    (Common_RAM + 91), W, A              ; reg: 0x05b
0022aa:  0100  movlb   0x0
0022ac:  0f6a  addlw   0x6a
0022ae:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0022b0:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0022b2:  0e02  movlw   0x02
0022b4:  62df  cpfseq  INDF2, A                             ; reg: 0xfdf
0022b6:  d005  bra     label_233                            ; dest: 0x0022c2
0022b8:  6a55  clrf    (Common_RAM + 85), A                 ; reg: 0x055
0022ba:  6a56  clrf    (Common_RAM + 86), A                 ; reg: 0x056
0022bc:  6a57  clrf    (Common_RAM + 87), A                 ; reg: 0x057
0022be:  0e3f  movlw   0x3f
0022c0:  d00c  bra     label_234                            ; dest: 0x0022da

label_233:                                                  ; address: 0x0022c2

0022c2:  505b  movf    (Common_RAM + 91), W, A              ; reg: 0x05b
0022c4:  0f6a  addlw   0x6a
0022c6:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0022c8:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0022ca:  0e03  movlw   0x03
0022cc:  62df  cpfseq  INDF2, A                             ; reg: 0xfdf
0022ce:  d007  bra     label_235                            ; dest: 0x0022de
0022d0:  6a55  clrf    (Common_RAM + 85), A                 ; reg: 0x055
0022d2:  6a56  clrf    (Common_RAM + 86), A                 ; reg: 0x056
0022d4:  0e80  movlw   0x80
0022d6:  6e57  movwf   (Common_RAM + 87), A                 ; reg: 0x057
0022d8:  0ebf  movlw   0xbf

label_234:                                                  ; address: 0x0022da

0022da:  6e58  movwf   (Common_RAM + 88), A                 ; reg: 0x058
0022dc:  d00f  bra     label_236                            ; dest: 0x0022fc

label_235:                                                  ; address: 0x0022de

0022de:  505b  movf    (Common_RAM + 91), W, A              ; reg: 0x05b
0022e0:  0f6a  addlw   0x6a
0022e2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0022e4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0022e6:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0022e8:  ece7  call    function_086, 0x0                    ; dest: 0x0045ce
0022ea:  f022
0022ec:  c00d  movff   (Common_RAM + 13), (Common_RAM + 85) ; reg1: 0x00d, reg2: 0x055
0022ee:  f055
0022f0:  c00e  movff   (Common_RAM + 14), (Common_RAM + 86) ; reg1: 0x00e, reg2: 0x056
0022f2:  f056
0022f4:  c00f  movff   (Common_RAM + 15), (Common_RAM + 87) ; reg1: 0x00f, reg2: 0x057
0022f6:  f057
0022f8:  c010  movff   (Common_RAM + 16), (Common_RAM + 88) ; reg1: 0x010, reg2: 0x058
0022fa:  f058

label_236:                                                  ; address: 0x0022fc

0022fc:  c055  movff   (Common_RAM + 85), (Common_RAM + 73) ; reg1: 0x055, reg2: 0x049
0022fe:  f049
002300:  c056  movff   (Common_RAM + 86), (Common_RAM + 74) ; reg1: 0x056, reg2: 0x04a
002302:  f04a
002304:  c057  movff   (Common_RAM + 87), (Common_RAM + 75) ; reg1: 0x057, reg2: 0x04b
002306:  f04b
002308:  c058  movff   (Common_RAM + 88), (Common_RAM + 76) ; reg1: 0x058, reg2: 0x04c
00230a:  f04c
00230c:  ecd3  call    function_046, 0x0                    ; dest: 0x0039a6
00230e:  f01c
002310:  2a5b  incf    (Common_RAM + 91), F, A              ; reg: 0x05b
002312:  0e03  movlw   0x03
002314:  645b  cpfsgt  (Common_RAM + 91), A                 ; reg: 0x05b
002316:  d7c8  bra     label_232                            ; dest: 0x0022a8
002318:  84c5  bsf     SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2

label_237:                                                  ; address: 0x00231a

00231a:  b4c5  btfsc   SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2
00231c:  d7fe  bra     label_237                            ; dest: 0x00231a
00231e:  2a5a  incf    (Common_RAM + 90), F, A              ; reg: 0x05a
002320:  0e06  movlw   0x06
002322:  645a  cpfsgt  (Common_RAM + 90), A                 ; reg: 0x05a
002324:  d7a2  bra     label_229                            ; dest: 0x00226a
002326:  0c06  retlw   0x06

function_009:                                               ; address: 0x002328

002328:  c0c1  movff   0x0c1, 0x15a
00232a:  f15a
00232c:  d0a2  bra     label_248                            ; dest: 0x002472

label_238:                                                  ; address: 0x00232e

00232e:  c0c2  movff   0x0c2, 0x15b
002330:  f15b
002332:  0e02  movlw   0x02
002334:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003

label_239:                                                  ; address: 0x002336

002336:  0ebe  movlw   0xbe
002338:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
00233a:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
00233c:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00233e:  0e02  movlw   0x02
002340:  d8b5  rcall   function_010                         ; dest: 0x0024ac
002342:  0e1f  movlw   0x1f
002344:  6403  cpfsgt  (Common_RAM + 3), A                  ; reg: 0x003
002346:  d7f7  bra     label_239                            ; dest: 0x002336
002348:  d0ae  bra     label_252                            ; dest: 0x0024a6

label_240:                                                  ; address: 0x00234a

00234a:  c0c2  movff   0x0c2, 0x15b
00234c:  f15b
00234e:  05c2  decf    0xc2, W, B                           ; reg: 0x0c2
002350:  e105  bnz     label_241
002352:  c0b7  movff   0x0b7, 0x15c
002354:  f15c
002356:  c0b8  movff   0x0b8, 0x15d
002358:  f15d
00235a:  d0a5  bra     label_252                            ; dest: 0x0024a6

label_241:                                                  ; address: 0x00235c

00235c:  51c2  movf    0xc2, W, B                           ; reg: 0x0c2
00235e:  0a02  xorlw   0x02
002360:  e001  bz      label_242
002362:  d0a1  bra     label_252                            ; dest: 0x0024a6

label_242:                                                  ; address: 0x002364

002364:  c0b5  movff   0x0b5, 0x15e
002366:  f15e
002368:  0e05  movlw   0x05
00236a:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003

label_243:                                                  ; address: 0x00236c

00236c:  0efb  movlw   0xfb
00236e:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
002370:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
002372:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
002374:  0e00  movlw   0x00
002376:  d89a  rcall   function_010                         ; dest: 0x0024ac
002378:  0e13  movlw   0x13
00237a:  6403  cpfsgt  (Common_RAM + 3), A                  ; reg: 0x003
00237c:  d7f7  bra     label_243                            ; dest: 0x00236c
00237e:  d093  bra     label_252                            ; dest: 0x0024a6

label_244:                                                  ; address: 0x002380

002380:  c093  movff   0x093, 0x15b
002382:  f15b
002384:  c099  movff   0x099, 0x15c
002386:  f15c
002388:  0101  movlb   0x1
00238a:  6b5d  clrf    0x5d, B                              ; reg: 0x15d
00238c:  6b5e  clrf    0x5e, B                              ; reg: 0x15e
00238e:  c071  movff   0x071, 0x15f
002390:  f15f
002392:  c070  movff   0x070, 0x160
002394:  f160
002396:  c06f  movff   0x06f, 0x161
002398:  f161
00239a:  c06e  movff   0x06e, 0x162
00239c:  f162
00239e:  0e00  movlw   0x00
0023a0:  b85e  btfsc   0x5e, 0x4, A                         ; reg: 0x15e
0023a2:  0e01  movlw   0x01
0023a4:  6f63  movwf   0x63, B                              ; reg: 0x163
0023a6:  0e00  movlw   0x00
0023a8:  0100  movlb   0x0
0023aa:  b1a4  btfsc   0xa4, 0x0, B                         ; reg: 0x0a4
0023ac:  0e01  movlw   0x01
0023ae:  0101  movlb   0x1
0023b0:  6f64  movwf   0x64, B                              ; reg: 0x164
0023b2:  0e00  movlw   0x00
0023b4:  0100  movlb   0x0
0023b6:  b3a4  btfsc   0xa4, 0x1, B                         ; reg: 0x0a4
0023b8:  0e01  movlw   0x01
0023ba:  0101  movlb   0x1
0023bc:  6f65  movwf   0x65, B                              ; reg: 0x165
0023be:  0e00  movlw   0x00
0023c0:  0100  movlb   0x0
0023c2:  b5a4  btfsc   0xa4, 0x2, B                         ; reg: 0x0a4
0023c4:  0e01  movlw   0x01
0023c6:  0101  movlb   0x1
0023c8:  6f66  movwf   0x66, B                              ; reg: 0x166
0023ca:  0e00  movlw   0x00
0023cc:  0100  movlb   0x0
0023ce:  b7a4  btfsc   0xa4, 0x3, B                         ; reg: 0x0a4
0023d0:  0e01  movlw   0x01
0023d2:  0101  movlb   0x1
0023d4:  6f68  movwf   0x68, B                              ; reg: 0x168
0023d6:  0e00  movlw   0x00
0023d8:  0100  movlb   0x0
0023da:  b9a4  btfsc   0xa4, 0x4, B                         ; reg: 0x0a4
0023dc:  0e01  movlw   0x01
0023de:  0101  movlb   0x1
0023e0:  6f69  movwf   0x69, B                              ; reg: 0x169
0023e2:  0e00  movlw   0x00
0023e4:  0100  movlb   0x0
0023e6:  bba4  btfsc   0xa4, 0x5, B                         ; reg: 0x0a4
0023e8:  0e01  movlw   0x01
0023ea:  0101  movlb   0x1
0023ec:  6f6a  movwf   0x6a, B                              ; reg: 0x16a
0023ee:  c060  movff   0x060, 0x16c
0023f0:  f16c
0023f2:  c061  movff   0x061, 0x16d
0023f4:  f16d
0023f6:  c062  movff   0x062, 0x16e
0023f8:  f16e
0023fa:  c063  movff   0x063, 0x16f
0023fc:  f16f
0023fe:  c064  movff   0x064, 0x170
002400:  f170
002402:  c065  movff   0x065, 0x171
002404:  f171
002406:  c0b4  movff   0x0b4, 0x178
002408:  f178
00240a:  d04d  bra     label_252                            ; dest: 0x0024a6

label_245:                                                  ; address: 0x00240c

00240c:  0e03  movlw   0x03
00240e:  0101  movlb   0x1
002410:  6f5b  movwf   0x5b, B                              ; reg: 0x15b
002412:  0e02  movlw   0x02
002414:  6f5c  movwf   0x5c, B                              ; reg: 0x15c
002416:  0e03  movlw   0x03
002418:  6f5d  movwf   0x5d, B                              ; reg: 0x15d
00241a:  c099  movff   0x099, 0x15e
00241c:  f15e
00241e:  6b5f  clrf    0x5f, B                              ; reg: 0x15f
002420:  6b60  clrf    0x60, B                              ; reg: 0x160
002422:  6b61  clrf    0x61, B                              ; reg: 0x161
002424:  c05f  movff   (Common_RAM + 95), 0x163             ; reg1: 0x05f
002426:  f163
002428:  0e06  movlw   0x06
00242a:  6f64  movwf   0x64, B                              ; reg: 0x164
00242c:  0e0f  movlw   0x0f
00242e:  6f65  movwf   0x65, B                              ; reg: 0x165
002430:  6f66  movwf   0x66, B                              ; reg: 0x166
002432:  6f67  movwf   0x67, B                              ; reg: 0x167
002434:  6f68  movwf   0x68, B                              ; reg: 0x168
002436:  6f69  movwf   0x69, B                              ; reg: 0x169
002438:  6f6a  movwf   0x6a, B                              ; reg: 0x16a
00243a:  0e0a  movlw   0x0a
00243c:  6f6b  movwf   0x6b, B                              ; reg: 0x16b
00243e:  6f6c  movwf   0x6c, B                              ; reg: 0x16c
002440:  6f6d  movwf   0x6d, B                              ; reg: 0x16d
002442:  6f6e  movwf   0x6e, B                              ; reg: 0x16e
002444:  6f6f  movwf   0x6f, B                              ; reg: 0x16f
002446:  6f70  movwf   0x70, B                              ; reg: 0x170
002448:  0e01  movlw   0x01
00244a:  6f71  movwf   0x71, B                              ; reg: 0x171
00244c:  6f72  movwf   0x72, B                              ; reg: 0x172
00244e:  c09b  movff   0x09b, 0x173
002450:  f173
002452:  c09c  movff   0x09c, 0x174
002454:  f174
002456:  c09d  movff   0x09d, 0x175
002458:  f175
00245a:  c09e  movff   0x09e, 0x176
00245c:  f176
00245e:  d023  bra     label_252                            ; dest: 0x0024a6

label_246:                                                  ; address: 0x002460

002460:  c11b  movff   0x11b, 0x15b
002462:  f15b
002464:  d020  bra     label_252                            ; dest: 0x0024a6

label_247:                                                  ; address: 0x002466

002466:  0101  movlb   0x1
002468:  6b5b  clrf    0x5b, B                              ; reg: 0x15b
00246a:  6b5c  clrf    0x5c, B                              ; reg: 0x15c
00246c:  6b5d  clrf    0x5d, B                              ; reg: 0x15d
00246e:  6b5e  clrf    0x5e, B                              ; reg: 0x15e
002470:  d01a  bra     label_252                            ; dest: 0x0024a6

label_248:                                                  ; address: 0x002472

002472:  0100  movlb   0x0
002474:  51c1  movf    0xc1, W, B                           ; reg: 0x0c1
002476:  0a03  xorlw   0x03
002478:  e101  bnz     label_249
00247a:  d759  bra     label_238                            ; dest: 0x00232e

label_249:                                                  ; address: 0x00247c

00247c:  0a07  xorlw   0x07
00247e:  e101  bnz     label_250
002480:  d764  bra     label_240                            ; dest: 0x00234a

label_250:                                                  ; address: 0x002482

002482:  0a01  xorlw   0x01
002484:  e101  bnz     label_251
002486:  d77c  bra     label_244                            ; dest: 0x002380

label_251:                                                  ; address: 0x002488

002488:  0a03  xorlw   0x03
00248a:  e0c0  bz      label_245
00248c:  0a01  xorlw   0x01
00248e:  e0e8  bz      label_246
002490:  0a0f  xorlw   0x0f
002492:  e0e6  bz      label_246
002494:  0a01  xorlw   0x01
002496:  e0e4  bz      label_246
002498:  0a03  xorlw   0x03
00249a:  e0e2  bz      label_246
00249c:  0a01  xorlw   0x01
00249e:  e0e0  bz      label_246
0024a0:  0a07  xorlw   0x07
0024a2:  e0de  bz      label_246
0024a4:  d7e0  bra     label_247                            ; dest: 0x002466

label_252:                                                  ; address: 0x0024a6

0024a6:  0100  movlb   0x0
0024a8:  6bc1  clrf    0xc1, B                              ; reg: 0x0c1
0024aa:  0012  return  0x0

function_010:                                               ; address: 0x0024ac

0024ac:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0024ae:  0e5a  movlw   0x5a
0024b0:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
0024b2:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
0024b4:  6ae2  clrf    FSR1H, A                             ; reg: 0xfe2
0024b6:  0e01  movlw   0x01
0024b8:  22e2  addwfc  FSR1H, F, A                          ; reg: 0xfe2
0024ba:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
0024bc:  ffe7
0024be:  2a03  incf    (Common_RAM + 3), F, A               ; reg: 0x003
0024c0:  0012  return  0x0

function_011:                                               ; address: 0x0024c2

0024c2:  c020  movff   (Common_RAM + 32), (Common_RAM + 40) ; reg1: 0x020, reg2: 0x028
0024c4:  f028
0024c6:  c021  movff   (Common_RAM + 33), (Common_RAM + 41) ; reg1: 0x021, reg2: 0x029
0024c8:  f029
0024ca:  c022  movff   (Common_RAM + 34), (Common_RAM + 42) ; reg1: 0x022, reg2: 0x02a
0024cc:  f02a
0024ce:  c023  movff   (Common_RAM + 35), (Common_RAM + 43) ; reg1: 0x023, reg2: 0x02b
0024d0:  f02b
0024d2:  0e18  movlw   0x18
0024d4:  d001  bra     label_254                            ; dest: 0x0024d8

label_253:                                                  ; address: 0x0024d6

0024d6:  d8bc  rcall   function_013                         ; dest: 0x002650

label_254:                                                  ; address: 0x0024d8

0024d8:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
0024da:  d7fd  bra     label_253                            ; dest: 0x0024d6
0024dc:  5028  movf    (Common_RAM + 40), W, A              ; reg: 0x028
0024de:  6e2e  movwf   (Common_RAM + 46), A                 ; reg: 0x02e
0024e0:  c024  movff   (Common_RAM + 36), (Common_RAM + 40) ; reg1: 0x024, reg2: 0x028
0024e2:  f028
0024e4:  c025  movff   (Common_RAM + 37), (Common_RAM + 41) ; reg1: 0x025, reg2: 0x029
0024e6:  f029
0024e8:  c026  movff   (Common_RAM + 38), (Common_RAM + 42) ; reg1: 0x026, reg2: 0x02a
0024ea:  f02a
0024ec:  c027  movff   (Common_RAM + 39), (Common_RAM + 43) ; reg1: 0x027, reg2: 0x02b
0024ee:  f02b
0024f0:  0e18  movlw   0x18
0024f2:  d001  bra     label_256                            ; dest: 0x0024f6

label_255:                                                  ; address: 0x0024f4

0024f4:  d8ad  rcall   function_013                         ; dest: 0x002650

label_256:                                                  ; address: 0x0024f6

0024f6:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
0024f8:  d7fd  bra     label_255                            ; dest: 0x0024f4
0024fa:  5028  movf    (Common_RAM + 40), W, A              ; reg: 0x028
0024fc:  6e2d  movwf   (Common_RAM + 45), A                 ; reg: 0x02d
0024fe:  502e  movf    (Common_RAM + 46), W, A              ; reg: 0x02e
002500:  e009  bz      label_257
002502:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
002504:  5c2e  subwf   (Common_RAM + 46), W, A              ; reg: 0x02e
002506:  e20f  bc      label_258
002508:  502e  movf    (Common_RAM + 46), W, A              ; reg: 0x02e
00250a:  5c2d  subwf   (Common_RAM + 45), W, A              ; reg: 0x02d
00250c:  6e28  movwf   (Common_RAM + 40), A                 ; reg: 0x028
00250e:  0e21  movlw   0x21
002510:  5c28  subwf   (Common_RAM + 40), W, A              ; reg: 0x028
002512:  e309  bnc     label_258

label_257:                                                  ; address: 0x002514

002514:  c024  movff   (Common_RAM + 36), (Common_RAM + 32) ; reg1: 0x024, reg2: 0x020
002516:  f020
002518:  c025  movff   (Common_RAM + 37), (Common_RAM + 33) ; reg1: 0x025, reg2: 0x021
00251a:  f021
00251c:  c026  movff   (Common_RAM + 38), (Common_RAM + 34) ; reg1: 0x026, reg2: 0x022
00251e:  f022
002520:  c027  movff   (Common_RAM + 39), (Common_RAM + 35) ; reg1: 0x027, reg2: 0x023
002522:  f023
002524:  d08b  bra     label_272                            ; dest: 0x00263c

label_258:                                                  ; address: 0x002526

002526:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
002528:  e009  bz      label_259
00252a:  502e  movf    (Common_RAM + 46), W, A              ; reg: 0x02e
00252c:  5c2d  subwf   (Common_RAM + 45), W, A              ; reg: 0x02d
00252e:  e20f  bc      label_260
002530:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
002532:  5c2e  subwf   (Common_RAM + 46), W, A              ; reg: 0x02e
002534:  6e28  movwf   (Common_RAM + 40), A                 ; reg: 0x028
002536:  0e21  movlw   0x21
002538:  5c28  subwf   (Common_RAM + 40), W, A              ; reg: 0x028
00253a:  e309  bnc     label_260

label_259:                                                  ; address: 0x00253c

00253c:  c020  movff   (Common_RAM + 32), (Common_RAM + 32) ; reg1: 0x020, reg2: 0x020
00253e:  f020
002540:  c021  movff   (Common_RAM + 33), (Common_RAM + 33) ; reg1: 0x021, reg2: 0x021
002542:  f021
002544:  c022  movff   (Common_RAM + 34), (Common_RAM + 34) ; reg1: 0x022, reg2: 0x022
002546:  f022
002548:  c023  movff   (Common_RAM + 35), (Common_RAM + 35) ; reg1: 0x023, reg2: 0x023
00254a:  f023
00254c:  d077  bra     label_272                            ; dest: 0x00263c

label_260:                                                  ; address: 0x00254e

00254e:  0e06  movlw   0x06
002550:  6e2c  movwf   (Common_RAM + 44), A                 ; reg: 0x02c
002552:  be23  btfsc   (Common_RAM + 35), 0x7, A            ; reg: 0x023
002554:  8e2c  bsf     (Common_RAM + 44), 0x7, A            ; reg: 0x02c
002556:  be27  btfsc   (Common_RAM + 39), 0x7, A            ; reg: 0x027
002558:  8c2c  bsf     (Common_RAM + 44), 0x6, A            ; reg: 0x02c
00255a:  8e22  bsf     (Common_RAM + 34), 0x7, A            ; reg: 0x022
00255c:  6a23  clrf    (Common_RAM + 35), A                 ; reg: 0x023
00255e:  8e26  bsf     (Common_RAM + 38), 0x7, A            ; reg: 0x026
002560:  6a27  clrf    (Common_RAM + 39), A                 ; reg: 0x027
002562:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
002564:  5c2e  subwf   (Common_RAM + 46), W, A              ; reg: 0x02e
002566:  e21a  bc      label_264

label_261:                                                  ; address: 0x002568

002568:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
00256a:  3624  rlcf    (Common_RAM + 36), F, A              ; reg: 0x024
00256c:  3625  rlcf    (Common_RAM + 37), F, A              ; reg: 0x025
00256e:  3626  rlcf    (Common_RAM + 38), F, A              ; reg: 0x026
002570:  3627  rlcf    (Common_RAM + 39), F, A              ; reg: 0x027
002572:  062d  decf    (Common_RAM + 45), F, A              ; reg: 0x02d
002574:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
002576:  182e  xorwf   (Common_RAM + 46), W, A              ; reg: 0x02e
002578:  e00d  bz      label_263
00257a:  062c  decf    (Common_RAM + 44), F, A              ; reg: 0x02c
00257c:  c02c  movff   (Common_RAM + 44), (Common_RAM + 40) ; reg1: 0x02c, reg2: 0x028
00257e:  f028
002580:  0e07  movlw   0x07
002582:  1628  andwf   (Common_RAM + 40), F, A              ; reg: 0x028
002584:  e007  bz      label_263
002586:  d7f0  bra     label_261                            ; dest: 0x002568

label_262:                                                  ; address: 0x002588

002588:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
00258a:  3223  rrcf    (Common_RAM + 35), F, A              ; reg: 0x023
00258c:  3222  rrcf    (Common_RAM + 34), F, A              ; reg: 0x022
00258e:  3221  rrcf    (Common_RAM + 33), F, A              ; reg: 0x021
002590:  3220  rrcf    (Common_RAM + 32), F, A              ; reg: 0x020
002592:  2a2e  incf    (Common_RAM + 46), F, A              ; reg: 0x02e

label_263:                                                  ; address: 0x002594

002594:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
002596:  622e  cpfseq  (Common_RAM + 46), A                 ; reg: 0x02e
002598:  d7f7  bra     label_262                            ; dest: 0x002588
00259a:  d01c  bra     label_268                            ; dest: 0x0025d4

label_264:                                                  ; address: 0x00259c

00259c:  502e  movf    (Common_RAM + 46), W, A              ; reg: 0x02e
00259e:  5c2d  subwf   (Common_RAM + 45), W, A              ; reg: 0x02d
0025a0:  e219  bc      label_268

label_265:                                                  ; address: 0x0025a2

0025a2:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
0025a4:  3620  rlcf    (Common_RAM + 32), F, A              ; reg: 0x020
0025a6:  3621  rlcf    (Common_RAM + 33), F, A              ; reg: 0x021
0025a8:  3622  rlcf    (Common_RAM + 34), F, A              ; reg: 0x022
0025aa:  3623  rlcf    (Common_RAM + 35), F, A              ; reg: 0x023
0025ac:  062e  decf    (Common_RAM + 46), F, A              ; reg: 0x02e
0025ae:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
0025b0:  182e  xorwf   (Common_RAM + 46), W, A              ; reg: 0x02e
0025b2:  e00d  bz      label_267
0025b4:  062c  decf    (Common_RAM + 44), F, A              ; reg: 0x02c
0025b6:  c02c  movff   (Common_RAM + 44), (Common_RAM + 40) ; reg1: 0x02c, reg2: 0x028
0025b8:  f028
0025ba:  0e07  movlw   0x07
0025bc:  1628  andwf   (Common_RAM + 40), F, A              ; reg: 0x028
0025be:  e007  bz      label_267
0025c0:  d7f0  bra     label_265                            ; dest: 0x0025a2

label_266:                                                  ; address: 0x0025c2

0025c2:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
0025c4:  3227  rrcf    (Common_RAM + 39), F, A              ; reg: 0x027
0025c6:  3226  rrcf    (Common_RAM + 38), F, A              ; reg: 0x026
0025c8:  3225  rrcf    (Common_RAM + 37), F, A              ; reg: 0x025
0025ca:  3224  rrcf    (Common_RAM + 36), F, A              ; reg: 0x024
0025cc:  2a2d  incf    (Common_RAM + 45), F, A              ; reg: 0x02d

label_267:                                                  ; address: 0x0025ce

0025ce:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
0025d0:  622e  cpfseq  (Common_RAM + 46), A                 ; reg: 0x02e
0025d2:  d7f7  bra     label_266                            ; dest: 0x0025c2

label_268:                                                  ; address: 0x0025d4

0025d4:  ae2c  btfss   (Common_RAM + 44), 0x7, A            ; reg: 0x02c
0025d6:  d009  bra     label_269                            ; dest: 0x0025ea
0025d8:  1e20  comf    (Common_RAM + 32), F, A              ; reg: 0x020
0025da:  1e21  comf    (Common_RAM + 33), F, A              ; reg: 0x021
0025dc:  1e22  comf    (Common_RAM + 34), F, A              ; reg: 0x022
0025de:  1e23  comf    (Common_RAM + 35), F, A              ; reg: 0x023
0025e0:  2a20  incf    (Common_RAM + 32), F, A              ; reg: 0x020
0025e2:  0e00  movlw   0x00
0025e4:  2221  addwfc  (Common_RAM + 33), F, A              ; reg: 0x021
0025e6:  2222  addwfc  (Common_RAM + 34), F, A              ; reg: 0x022
0025e8:  2223  addwfc  (Common_RAM + 35), F, A              ; reg: 0x023

label_269:                                                  ; address: 0x0025ea

0025ea:  ac2c  btfss   (Common_RAM + 44), 0x6, A            ; reg: 0x02c
0025ec:  d002  bra     label_270                            ; dest: 0x0025f2
0025ee:  1e24  comf    (Common_RAM + 36), F, A              ; reg: 0x024
0025f0:  d826  rcall   function_012                         ; dest: 0x00263e

label_270:                                                  ; address: 0x0025f2

0025f2:  6a2c  clrf    (Common_RAM + 44), A                 ; reg: 0x02c
0025f4:  5020  movf    (Common_RAM + 32), W, A              ; reg: 0x020
0025f6:  2624  addwf   (Common_RAM + 36), F, A              ; reg: 0x024
0025f8:  5021  movf    (Common_RAM + 33), W, A              ; reg: 0x021
0025fa:  2225  addwfc  (Common_RAM + 37), F, A              ; reg: 0x025
0025fc:  5022  movf    (Common_RAM + 34), W, A              ; reg: 0x022
0025fe:  2226  addwfc  (Common_RAM + 38), F, A              ; reg: 0x026
002600:  5023  movf    (Common_RAM + 35), W, A              ; reg: 0x023
002602:  2227  addwfc  (Common_RAM + 39), F, A              ; reg: 0x027
002604:  ae27  btfss   (Common_RAM + 39), 0x7, A            ; reg: 0x027
002606:  d004  bra     label_271                            ; dest: 0x002610
002608:  1e24  comf    (Common_RAM + 36), F, A              ; reg: 0x024
00260a:  d819  rcall   function_012                         ; dest: 0x00263e
00260c:  0e01  movlw   0x01
00260e:  6e2c  movwf   (Common_RAM + 44), A                 ; reg: 0x02c

label_271:                                                  ; address: 0x002610

002610:  c024  movff   (Common_RAM + 36), (Common_RAM + 3)  ; reg1: 0x024, reg2: 0x003
002612:  f003
002614:  c025  movff   (Common_RAM + 37), (Common_RAM + 4)  ; reg1: 0x025, reg2: 0x004
002616:  f004
002618:  c026  movff   (Common_RAM + 38), (Common_RAM + 5)  ; reg1: 0x026, reg2: 0x005
00261a:  f005
00261c:  c027  movff   (Common_RAM + 39), (Common_RAM + 6)  ; reg1: 0x027, reg2: 0x006
00261e:  f006
002620:  c02e  movff   (Common_RAM + 46), (Common_RAM + 7)  ; reg1: 0x02e, reg2: 0x007
002622:  f007
002624:  c02c  movff   (Common_RAM + 44), (Common_RAM + 8)  ; reg1: 0x02c, reg2: 0x008
002626:  f008
002628:  ec6c  call    function_029, 0x0                    ; dest: 0x0030d8
00262a:  f018
00262c:  c003  movff   (Common_RAM + 3), (Common_RAM + 32)  ; reg1: 0x003, reg2: 0x020
00262e:  f020
002630:  c004  movff   (Common_RAM + 4), (Common_RAM + 33)  ; reg1: 0x004, reg2: 0x021
002632:  f021
002634:  c005  movff   (Common_RAM + 5), (Common_RAM + 34)  ; reg1: 0x005, reg2: 0x022
002636:  f022
002638:  c006  movff   (Common_RAM + 6), (Common_RAM + 35)  ; reg1: 0x006, reg2: 0x023
00263a:  f023

label_272:                                                  ; address: 0x00263c

00263c:  0012  return  0x0

function_012:                                               ; address: 0x00263e

00263e:  1e25  comf    (Common_RAM + 37), F, A              ; reg: 0x025
002640:  1e26  comf    (Common_RAM + 38), F, A              ; reg: 0x026
002642:  1e27  comf    (Common_RAM + 39), F, A              ; reg: 0x027
002644:  2a24  incf    (Common_RAM + 36), F, A              ; reg: 0x024
002646:  0e00  movlw   0x00
002648:  2225  addwfc  (Common_RAM + 37), F, A              ; reg: 0x025
00264a:  2226  addwfc  (Common_RAM + 38), F, A              ; reg: 0x026
00264c:  2227  addwfc  (Common_RAM + 39), F, A              ; reg: 0x027
00264e:  0c00  retlw   0x00

function_013:                                               ; address: 0x002650

002650:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002652:  322b  rrcf    (Common_RAM + 43), F, A              ; reg: 0x02b
002654:  322a  rrcf    (Common_RAM + 42), F, A              ; reg: 0x02a
002656:  3229  rrcf    (Common_RAM + 41), F, A              ; reg: 0x029
002658:  3228  rrcf    (Common_RAM + 40), F, A              ; reg: 0x028
00265a:  0012  return  0x0

function_014:                                               ; address: 0x00265c

00265c:  0100  movlb   0x0
00265e:  a17e  btfss   0x7e, 0x0, B                         ; reg: 0x07e
002660:  d0c6  bra     label_281                            ; dest: 0x0027ee
002662:  a1bd  btfss   0xbd, 0x0, B                         ; reg: 0x0bd
002664:  d033  bra     label_273                            ; dest: 0x0026cc
002666:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002668:  0e03  movlw   0x03
00266a:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
00266c:  c06e  movff   0x06e, (Common_RAM + 9)              ; reg2: 0x009
00266e:  f009
002670:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002672:  f023
002674:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002676:  0e02  movlw   0x02
002678:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
00267a:  c06f  movff   0x06f, (Common_RAM + 9)              ; reg2: 0x009
00267c:  f009
00267e:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002680:  f023
002682:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002684:  0e01  movlw   0x01
002686:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002688:  c070  movff   0x070, (Common_RAM + 9)              ; reg2: 0x009
00268a:  f009
00268c:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
00268e:  f023
002690:  0e00  movlw   0x00
002692:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002694:  6a07  clrf    (Common_RAM + 7), A                  ; reg: 0x007
002696:  c071  movff   0x071, (Common_RAM + 9)              ; reg2: 0x009
002698:  f009
00269a:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
00269c:  f023
00269e:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026a0:  0e04  movlw   0x04
0026a2:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0026a4:  c099  movff   0x099, (Common_RAM + 9)              ; reg2: 0x009
0026a6:  f009
0026a8:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0026aa:  f023
0026ac:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026ae:  0e0d  movlw   0x0d
0026b0:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0026b2:  c05f  movff   (Common_RAM + 95), (Common_RAM + 9)  ; reg1: 0x05f, reg2: 0x009
0026b4:  f009
0026b6:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0026b8:  f023
0026ba:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026bc:  0e14  movlw   0x14
0026be:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0026c0:  c0c3  movff   0x0c3, (Common_RAM + 9)              ; reg2: 0x009
0026c2:  f009
0026c4:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0026c6:  f023
0026c8:  0100  movlb   0x0
0026ca:  91bd  bcf     0xbd, 0x0, B                         ; reg: 0x0bd

label_273:                                                  ; address: 0x0026cc

0026cc:  a3bd  btfss   0xbd, 0x1, B                         ; reg: 0x0bd
0026ce:  d02c  bra     label_274                            ; dest: 0x002728
0026d0:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026d2:  0e07  movlw   0x07
0026d4:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0026d6:  c060  movff   0x060, (Common_RAM + 9)              ; reg2: 0x009
0026d8:  f009
0026da:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0026dc:  f023
0026de:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026e0:  0e08  movlw   0x08
0026e2:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0026e4:  c061  movff   0x061, (Common_RAM + 9)              ; reg2: 0x009
0026e6:  f009
0026e8:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0026ea:  f023
0026ec:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026ee:  0e09  movlw   0x09
0026f0:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0026f2:  c062  movff   0x062, (Common_RAM + 9)              ; reg2: 0x009
0026f4:  f009
0026f6:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0026f8:  f023
0026fa:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0026fc:  0e0a  movlw   0x0a
0026fe:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002700:  c063  movff   0x063, (Common_RAM + 9)              ; reg2: 0x009
002702:  f009
002704:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002706:  f023
002708:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00270a:  0e0b  movlw   0x0b
00270c:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
00270e:  c064  movff   0x064, (Common_RAM + 9)              ; reg2: 0x009
002710:  f009
002712:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002714:  f023
002716:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002718:  0e0c  movlw   0x0c
00271a:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
00271c:  c065  movff   0x065, (Common_RAM + 9)              ; reg2: 0x009
00271e:  f009
002720:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002722:  f023
002724:  0100  movlb   0x0
002726:  93bd  bcf     0xbd, 0x1, B                         ; reg: 0x0bd

label_274:                                                  ; address: 0x002728

002728:  a5bd  btfss   0xbd, 0x2, B                         ; reg: 0x0bd
00272a:  d010  bra     label_275                            ; dest: 0x00274c
00272c:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00272e:  0e0f  movlw   0x0f
002730:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002732:  c0b4  movff   0x0b4, (Common_RAM + 9)              ; reg2: 0x009
002734:  f009
002736:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002738:  f023
00273a:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00273c:  0e0e  movlw   0x0e
00273e:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002740:  c0b8  movff   0x0b8, (Common_RAM + 9)              ; reg2: 0x009
002742:  f009
002744:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002746:  f023
002748:  0100  movlb   0x0
00274a:  95bd  bcf     0xbd, 0x2, B                         ; reg: 0x0bd

label_275:                                                  ; address: 0x00274c

00274c:  a7bd  btfss   0xbd, 0x3, B                         ; reg: 0x0bd
00274e:  d01e  bra     label_276                            ; dest: 0x00278c
002750:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002752:  0e10  movlw   0x10
002754:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002756:  c09b  movff   0x09b, (Common_RAM + 9)              ; reg2: 0x009
002758:  f009
00275a:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
00275c:  f023
00275e:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002760:  0e11  movlw   0x11
002762:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002764:  c09c  movff   0x09c, (Common_RAM + 9)              ; reg2: 0x009
002766:  f009
002768:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
00276a:  f023
00276c:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00276e:  0e12  movlw   0x12
002770:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002772:  c09d  movff   0x09d, (Common_RAM + 9)              ; reg2: 0x009
002774:  f009
002776:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002778:  f023
00277a:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00277c:  0e13  movlw   0x13
00277e:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002780:  c09e  movff   0x09e, (Common_RAM + 9)              ; reg2: 0x009
002782:  f009
002784:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
002786:  f023
002788:  0100  movlb   0x0
00278a:  97bd  bcf     0xbd, 0x3, B                         ; reg: 0x0bd

label_276:                                                  ; address: 0x00278c

00278c:  a9bd  btfss   0xbd, 0x4, B                         ; reg: 0x0bd
00278e:  d016  bra     label_278                            ; dest: 0x0027bc
002790:  0e50  movlw   0x50
002792:  6e0a  movwf   (Common_RAM + 10), A                 ; reg: 0x00a

label_277:                                                  ; address: 0x002794

002794:  c00a  movff   (Common_RAM + 10), (Common_RAM + 7)  ; reg1: 0x00a, reg2: 0x007
002796:  f007
002798:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00279a:  0101  movlb   0x1
00279c:  0eb0  movlw   0xb0
00279e:  240a  addwf   0x0a, W, A                           ; reg: 0x10a
0027a0:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0027a2:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0027a4:  0e00  movlw   0x00
0027a6:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0027a8:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0027aa:  6e09  movwf   0x09, A                              ; reg: 0x109
0027ac:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0027ae:  f023
0027b0:  2a0a  incf    (Common_RAM + 10), F, A              ; reg: 0x00a
0027b2:  0e5e  movlw   0x5e
0027b4:  640a  cpfsgt  (Common_RAM + 10), A                 ; reg: 0x00a
0027b6:  d7ee  bra     label_277                            ; dest: 0x002794
0027b8:  0100  movlb   0x0
0027ba:  99bd  bcf     0xbd, 0x4, B                         ; reg: 0x0bd

label_278:                                                  ; address: 0x0027bc

0027bc:  abbd  btfss   0xbd, 0x5, B                         ; reg: 0x0bd
0027be:  d016  bra     label_280                            ; dest: 0x0027ec
0027c0:  0e60  movlw   0x60
0027c2:  6e0a  movwf   (Common_RAM + 10), A                 ; reg: 0x00a

label_279:                                                  ; address: 0x0027c4

0027c4:  c00a  movff   (Common_RAM + 10), (Common_RAM + 7)  ; reg1: 0x00a, reg2: 0x007
0027c6:  f007
0027c8:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0027ca:  0102  movlb   0x2
0027cc:  0e60  movlw   0x60
0027ce:  240a  addwf   0x0a, W, A                           ; reg: 0x20a
0027d0:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0027d2:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0027d4:  0e02  movlw   0x02
0027d6:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
0027d8:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0027da:  6e09  movwf   0x09, A                              ; reg: 0x209
0027dc:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0027de:  f023
0027e0:  2a0a  incf    (Common_RAM + 10), F, A              ; reg: 0x00a
0027e2:  0e7d  movlw   0x7d
0027e4:  640a  cpfsgt  (Common_RAM + 10), A                 ; reg: 0x00a
0027e6:  d7ee  bra     label_279                            ; dest: 0x0027c4
0027e8:  0100  movlb   0x0
0027ea:  9bbd  bcf     0xbd, 0x5, B                         ; reg: 0x0bd

label_280:                                                  ; address: 0x0027ec

0027ec:  917e  bcf     0x7e, 0x0, B                         ; reg: 0x07e

label_281:                                                  ; address: 0x0027ee

0027ee:  0012  return  0x0

function_015:                                               ; address: 0x0027f0

0027f0:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
0027f2:  d0c4  bra     label_313                            ; dest: 0x00297c
0027f4:  0e64  movlw   0x64
0027f6:  0100  movlb   0x0
0027f8:  65bb  cpfsgt  0xbb, B                              ; reg: 0x0bb
0027fa:  d0bf  bra     label_312                            ; dest: 0x00297a
0027fc:  6bbb  clrf    0xbb, B                              ; reg: 0x0bb
0027fe:  d055  bra     label_300                            ; dest: 0x0028aa

label_282:                                                  ; address: 0x002800

002800:  51b6  movf    0xb6, W, B                           ; reg: 0x0b6
002802:  0f08  addlw   0x08
002804:  6fbe  movwf   0xbe, B                              ; reg: 0x0be
002806:  d063  bra     label_301                            ; dest: 0x0028ce

label_283:                                                  ; address: 0x002808

002808:  6b93  clrf    0x93, B                              ; reg: 0x093
00280a:  d061  bra     label_301                            ; dest: 0x0028ce

label_284:                                                  ; address: 0x00280c

00280c:  0e01  movlw   0x01
00280e:  6f93  movwf   0x93, B                              ; reg: 0x093
002810:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
002812:  e05d  bz      label_301
002814:  0e05  movlw   0x05
002816:  d047  bra     label_299                            ; dest: 0x0028a6

label_285:                                                  ; address: 0x002818

002818:  0e02  movlw   0x02
00281a:  6f93  movwf   0x93, B                              ; reg: 0x093
00281c:  045f  decf    (Common_RAM + 95), W, A              ; reg: 0x05f
00281e:  e102  bnz     label_286
002820:  0e01  movlw   0x01
002822:  6f93  movwf   0x93, B                              ; reg: 0x093

label_286:                                                  ; address: 0x002824

002824:  0e01  movlw   0x01
002826:  645f  cpfsgt  (Common_RAM + 95), A                 ; reg: 0x05f
002828:  d052  bra     label_301                            ; dest: 0x0028ce
00282a:  0e06  movlw   0x06
00282c:  d03c  bra     label_299                            ; dest: 0x0028a6

label_287:                                                  ; address: 0x00282e

00282e:  0e03  movlw   0x03
002830:  6f93  movwf   0x93, B                              ; reg: 0x093
002832:  045f  decf    (Common_RAM + 95), W, A              ; reg: 0x05f
002834:  e102  bnz     label_288
002836:  0e02  movlw   0x02
002838:  6f93  movwf   0x93, B                              ; reg: 0x093

label_288:                                                  ; address: 0x00283a

00283a:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
00283c:  0a02  xorlw   0x02
00283e:  e102  bnz     label_289
002840:  0e01  movlw   0x01
002842:  6f93  movwf   0x93, B                              ; reg: 0x093

label_289:                                                  ; address: 0x002844

002844:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
002846:  0a03  xorlw   0x03
002848:  e142  bnz     label_301
00284a:  0e07  movlw   0x07
00284c:  d02c  bra     label_299                            ; dest: 0x0028a6

label_290:                                                  ; address: 0x00284e

00284e:  0e04  movlw   0x04
002850:  6f93  movwf   0x93, B                              ; reg: 0x093
002852:  045f  decf    (Common_RAM + 95), W, A              ; reg: 0x05f
002854:  e102  bnz     label_291
002856:  0e03  movlw   0x03
002858:  6f93  movwf   0x93, B                              ; reg: 0x093

label_291:                                                  ; address: 0x00285a

00285a:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
00285c:  0a02  xorlw   0x02
00285e:  e102  bnz     label_292
002860:  0e02  movlw   0x02
002862:  6f93  movwf   0x93, B                              ; reg: 0x093

label_292:                                                  ; address: 0x002864

002864:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
002866:  0a03  xorlw   0x03
002868:  e132  bnz     label_301
00286a:  0e01  movlw   0x01
00286c:  d01c  bra     label_299                            ; dest: 0x0028a6

label_293:                                                  ; address: 0x00286e

00286e:  045f  decf    (Common_RAM + 95), W, A              ; reg: 0x05f
002870:  e102  bnz     label_294
002872:  0e04  movlw   0x04
002874:  6f93  movwf   0x93, B                              ; reg: 0x093

label_294:                                                  ; address: 0x002876

002876:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
002878:  0a02  xorlw   0x02
00287a:  e102  bnz     label_295
00287c:  0e03  movlw   0x03
00287e:  6f93  movwf   0x93, B                              ; reg: 0x093

label_295:                                                  ; address: 0x002880

002880:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
002882:  0a03  xorlw   0x03
002884:  e124  bnz     label_301
002886:  0e02  movlw   0x02
002888:  d00e  bra     label_299                            ; dest: 0x0028a6

label_296:                                                  ; address: 0x00288a

00288a:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
00288c:  0a02  xorlw   0x02
00288e:  e102  bnz     label_297
002890:  0e04  movlw   0x04
002892:  6f93  movwf   0x93, B                              ; reg: 0x093

label_297:                                                  ; address: 0x002894

002894:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
002896:  0a03  xorlw   0x03
002898:  e11a  bnz     label_301
00289a:  0e03  movlw   0x03
00289c:  d004  bra     label_299                            ; dest: 0x0028a6

label_298:                                                  ; address: 0x00289e

00289e:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
0028a0:  0a03  xorlw   0x03
0028a2:  e115  bnz     label_301
0028a4:  0e04  movlw   0x04

label_299:                                                  ; address: 0x0028a6

0028a6:  6f93  movwf   0x93, B                              ; reg: 0x093
0028a8:  d012  bra     label_301                            ; dest: 0x0028ce

label_300:                                                  ; address: 0x0028aa

0028aa:  5199  movf    0x99, W, B                           ; reg: 0x099
0028ac:  e0a9  bz      label_282
0028ae:  0a01  xorlw   0x01
0028b0:  e0ab  bz      label_283
0028b2:  0a03  xorlw   0x03
0028b4:  e0ab  bz      label_284
0028b6:  0a01  xorlw   0x01
0028b8:  e0af  bz      label_285
0028ba:  0a07  xorlw   0x07
0028bc:  e0b8  bz      label_287
0028be:  0a01  xorlw   0x01
0028c0:  e0c6  bz      label_290
0028c2:  0a03  xorlw   0x03
0028c4:  e0d4  bz      label_293
0028c6:  0a01  xorlw   0x01
0028c8:  e0e0  bz      label_296
0028ca:  0a0f  xorlw   0x0f
0028cc:  e0e8  bz      label_298

label_301:                                                  ; address: 0x0028ce

0028ce:  6799  tstfsz  0x99, B                              ; reg: 0x099
0028d0:  d018  bra     label_302                            ; dest: 0x002902
0028d2:  c0be  movff   0x0be, (Common_RAM + 6)              ; reg2: 0x006
0028d4:  f006
0028d6:  0e0d  movlw   0x0d
0028d8:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
0028da:  f023
0028dc:  0e13  movlw   0x13
0028de:  ec1e  call    function_067, 0x0                    ; dest: 0x00423c
0028e0:  f021
0028e2:  0100  movlb   0x0
0028e4:  6fbe  movwf   0xbe, B                              ; reg: 0x0be
0028e6:  67be  tstfsz  0xbe, B                              ; reg: 0x0be
0028e8:  d010  bra     label_304                            ; dest: 0x00290a
0028ea:  6b93  clrf    0x93, B                              ; reg: 0x093
0028ec:  0e0a  movlw   0x0a
0028ee:  65ba  cpfsgt  0xba, B                              ; reg: 0x0ba
0028f0:  d00a  bra     label_303                            ; dest: 0x002906
0028f2:  6bba  clrf    0xba, B                              ; reg: 0x0ba
0028f4:  0e04  movlw   0x04
0028f6:  5db6  subwf   0xb6, W, B                           ; reg: 0x0b6
0028f8:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
0028fa:  2bb6  incf    0xb6, F, B                           ; reg: 0x0b6
0028fc:  51b6  movf    0xb6, W, B                           ; reg: 0x0b6
0028fe:  0a04  xorlw   0x04
002900:  e12d  bnz     label_310

label_302:                                                  ; address: 0x002902

002902:  6bb6  clrf    0xb6, B                              ; reg: 0x0b6
002904:  d02b  bra     label_310                            ; dest: 0x00295c

label_303:                                                  ; address: 0x002906

002906:  2bba  incf    0xba, F, B                           ; reg: 0x0ba
002908:  d029  bra     label_310                            ; dest: 0x00295c

label_304:                                                  ; address: 0x00290a

00290a:  67b6  tstfsz  0xb6, B                              ; reg: 0x0b6
00290c:  d002  bra     label_305                            ; dest: 0x002912
00290e:  0e03  movlw   0x03
002910:  6f93  movwf   0x93, B                              ; reg: 0x093

label_305:                                                  ; address: 0x002912

002912:  05b6  decf    0xb6, W, B                           ; reg: 0x0b6
002914:  e102  bnz     label_306
002916:  0e01  movlw   0x01
002918:  6f93  movwf   0x93, B                              ; reg: 0x093

label_306:                                                  ; address: 0x00291a

00291a:  51b6  movf    0xb6, W, B                           ; reg: 0x0b6
00291c:  0a02  xorlw   0x02
00291e:  e102  bnz     label_307
002920:  0e02  movlw   0x02
002922:  6f93  movwf   0x93, B                              ; reg: 0x093

label_307:                                                  ; address: 0x002924

002924:  51b6  movf    0xb6, W, B                           ; reg: 0x0b6
002926:  0a03  xorlw   0x03
002928:  e102  bnz     label_308
00292a:  0e04  movlw   0x04
00292c:  6f93  movwf   0x93, B                              ; reg: 0x093

label_308:                                                  ; address: 0x00292e

00292e:  0e12  movlw   0x12
002930:  ec1e  call    function_067, 0x0                    ; dest: 0x00423c
002932:  f021
002934:  0100  movlb   0x0
002936:  6fbf  movwf   0xbf, B                              ; reg: 0x0bf
002938:  51bf  movf    0xbf, W, B                           ; reg: 0x0bf
00293a:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
00293c:  885e  bsf     (Common_RAM + 94), 0x4, A            ; reg: 0x05e
00293e:  0e01  movlw   0x01
002940:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
002942:  0e00  movlw   0x00
002944:  6e08  movwf   (Common_RAM + 8), A                  ; reg: 0x008
002946:  0e01  movlw   0x01
002948:  aa5e  btfss   (Common_RAM + 94), 0x5, A            ; reg: 0x05e
00294a:  0e00  movlw   0x00
00294c:  1a08  xorwf   (Common_RAM + 8), F, A               ; reg: 0x008
00294e:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
002950:  8b7e  bsf     0x7e, 0x5, B                         ; reg: 0x07e
002952:  a85e  btfss   (Common_RAM + 94), 0x4, A            ; reg: 0x05e
002954:  d002  bra     label_309                            ; dest: 0x00295a
002956:  8a5e  bsf     (Common_RAM + 94), 0x5, A            ; reg: 0x05e
002958:  d001  bra     label_310                            ; dest: 0x00295c

label_309:                                                  ; address: 0x00295a

00295a:  9a5e  bcf     (Common_RAM + 94), 0x5, A            ; reg: 0x05e

label_310:                                                  ; address: 0x00295c

00295c:  0100  movlb   0x0
00295e:  5193  movf    0x93, W, B                           ; reg: 0x093
002960:  0a02  xorlw   0x02
002962:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
002964:  b082  btfsc   PORTC, RC0, A                        ; reg: 0xf82, bit: 0
002966:  d002  bra     label_311                            ; dest: 0x00296c
002968:  c0c3  movff   0x0c3, 0x093
00296a:  f093

label_311:                                                  ; address: 0x00296c

00296c:  51ab  movf    0xab, W, B                           ; reg: 0x0ab
00296e:  1993  xorwf   0x93, W, B                           ; reg: 0x093
002970:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
002972:  837e  bsf     0x7e, 0x1, B                         ; reg: 0x07e
002974:  c093  movff   0x093, 0x0ab
002976:  f0ab
002978:  d001  bra     label_313                            ; dest: 0x00297c

label_312:                                                  ; address: 0x00297a

00297a:  2bbb  incf    0xbb, F, B                           ; reg: 0x0bb

label_313:                                                  ; address: 0x00297c

00297c:  0012  return  0x0

function_016:                                               ; address: 0x00297e

00297e:  6a11  clrf    (Common_RAM + 17), A                 ; reg: 0x011
002980:  6a12  clrf    (Common_RAM + 18), A                 ; reg: 0x012
002982:  0e80  movlw   0x80
002984:  6e13  movwf   (Common_RAM + 19), A                 ; reg: 0x013
002986:  0e44  movlw   0x44
002988:  6e14  movwf   (Common_RAM + 20), A                 ; reg: 0x014
00298a:  c02f  movff   (Common_RAM + 47), (Common_RAM + 13) ; reg1: 0x02f, reg2: 0x00d
00298c:  f00d
00298e:  c030  movff   (Common_RAM + 48), (Common_RAM + 14) ; reg1: 0x030, reg2: 0x00e
002990:  f00e
002992:  c031  movff   (Common_RAM + 49), (Common_RAM + 15) ; reg1: 0x031, reg2: 0x00f
002994:  f00f
002996:  c032  movff   (Common_RAM + 50), (Common_RAM + 16) ; reg1: 0x032, reg2: 0x010
002998:  f010
00299a:  ec54  call    function_022, 0x0                    ; dest: 0x002ca8
00299c:  f016
00299e:  c00d  movff   (Common_RAM + 13), (Common_RAM + 32) ; reg1: 0x00d, reg2: 0x020
0029a0:  f020
0029a2:  c00e  movff   (Common_RAM + 14), (Common_RAM + 33) ; reg1: 0x00e, reg2: 0x021
0029a4:  f021
0029a6:  c00f  movff   (Common_RAM + 15), (Common_RAM + 34) ; reg1: 0x00f, reg2: 0x022
0029a8:  f022
0029aa:  c010  movff   (Common_RAM + 16), (Common_RAM + 35) ; reg1: 0x010, reg2: 0x023
0029ac:  f023
0029ae:  6a24  clrf    (Common_RAM + 36), A                 ; reg: 0x024
0029b0:  6a25  clrf    (Common_RAM + 37), A                 ; reg: 0x025
0029b2:  0e80  movlw   0x80
0029b4:  6e26  movwf   (Common_RAM + 38), A                 ; reg: 0x026
0029b6:  0e3f  movlw   0x3f
0029b8:  6e27  movwf   (Common_RAM + 39), A                 ; reg: 0x027
0029ba:  ec61  call    function_011, 0x0                    ; dest: 0x0024c2
0029bc:  f012
0029be:  c020  movff   (Common_RAM + 32), (Common_RAM + 47) ; reg1: 0x020, reg2: 0x02f
0029c0:  f02f
0029c2:  c021  movff   (Common_RAM + 33), (Common_RAM + 48) ; reg1: 0x021, reg2: 0x030
0029c4:  f030
0029c6:  c022  movff   (Common_RAM + 34), (Common_RAM + 49) ; reg1: 0x022, reg2: 0x031
0029c8:  f031
0029ca:  c023  movff   (Common_RAM + 35), (Common_RAM + 50) ; reg1: 0x023, reg2: 0x032
0029cc:  f032
0029ce:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
0029d0:  f025
0029d2:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
0029d4:  f026
0029d6:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
0029d8:  f027
0029da:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
0029dc:  f028
0029de:  0e2f  movlw   0x2f
0029e0:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
0029e2:  f01f
0029e4:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
0029e6:  f025
0029e8:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
0029ea:  f026
0029ec:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
0029ee:  f027
0029f0:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
0029f2:  f028
0029f4:  0e2f  movlw   0x2f
0029f6:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
0029f8:  f01f
0029fa:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
0029fc:  f025
0029fe:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a00:  f026
002a02:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a04:  f027
002a06:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a08:  f028
002a0a:  0e2f  movlw   0x2f
002a0c:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a0e:  f01f
002a10:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a12:  f025
002a14:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a16:  f026
002a18:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a1a:  f027
002a1c:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a1e:  f028
002a20:  0e2f  movlw   0x2f
002a22:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a24:  f01f
002a26:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a28:  f025
002a2a:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a2c:  f026
002a2e:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a30:  f027
002a32:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a34:  f028
002a36:  0e2f  movlw   0x2f
002a38:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a3a:  f01f
002a3c:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a3e:  f025
002a40:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a42:  f026
002a44:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a46:  f027
002a48:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a4a:  f028
002a4c:  0e2f  movlw   0x2f
002a4e:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a50:  f01f
002a52:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a54:  f025
002a56:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a58:  f026
002a5a:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a5c:  f027
002a5e:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a60:  f028
002a62:  0e2f  movlw   0x2f
002a64:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a66:  f01f
002a68:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a6a:  f025
002a6c:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a6e:  f026
002a70:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a72:  f027
002a74:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a76:  f028
002a78:  0e2f  movlw   0x2f
002a7a:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a7c:  f01f
002a7e:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a80:  f025
002a82:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a84:  f026
002a86:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a88:  f027
002a8a:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002a8c:  f028
002a8e:  0e2f  movlw   0x2f
002a90:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002a92:  f01f
002a94:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
002a96:  f025
002a98:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
002a9a:  f026
002a9c:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
002a9e:  f027
002aa0:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
002aa2:  f028
002aa4:  0e2f  movlw   0x2f
002aa6:  ec62  call    function_057, 0x0                    ; dest: 0x003ec4
002aa8:  f01f
002aaa:  c02f  movff   (Common_RAM + 47), (Common_RAM + 47) ; reg1: 0x02f, reg2: 0x02f
002aac:  f02f
002aae:  c030  movff   (Common_RAM + 48), (Common_RAM + 48) ; reg1: 0x030, reg2: 0x030
002ab0:  f030
002ab2:  c031  movff   (Common_RAM + 49), (Common_RAM + 49) ; reg1: 0x031, reg2: 0x031
002ab4:  f031
002ab6:  c032  movff   (Common_RAM + 50), (Common_RAM + 50) ; reg1: 0x032, reg2: 0x032
002ab8:  f032
002aba:  0012  return  0x0

function_017:                                               ; address: 0x002abc

002abc:  c012  movff   (Common_RAM + 18), (Common_RAM + 26) ; reg1: 0x012, reg2: 0x01a
002abe:  f01a
002ac0:  c013  movff   (Common_RAM + 19), (Common_RAM + 27) ; reg1: 0x013, reg2: 0x01b
002ac2:  f01b
002ac4:  c014  movff   (Common_RAM + 20), (Common_RAM + 28) ; reg1: 0x014, reg2: 0x01c
002ac6:  f01c
002ac8:  c015  movff   (Common_RAM + 21), (Common_RAM + 29) ; reg1: 0x015, reg2: 0x01d
002aca:  f01d
002acc:  0e18  movlw   0x18
002ace:  d001  bra     label_315                            ; dest: 0x002ad2

label_314:                                                  ; address: 0x002ad0

002ad0:  d86d  rcall   function_020                         ; dest: 0x002bac

label_315:                                                  ; address: 0x002ad2

002ad2:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
002ad4:  d7fd  bra     label_314                            ; dest: 0x002ad0
002ad6:  501a  movf    (Common_RAM + 26), W, A              ; reg: 0x01a
002ad8:  6e1e  movwf   (Common_RAM + 30), A                 ; reg: 0x01e
002ada:  661e  tstfsz  (Common_RAM + 30), A                 ; reg: 0x01e
002adc:  d001  bra     label_316                            ; dest: 0x002ae0
002ade:  d011  bra     label_319                            ; dest: 0x002b02

label_316:                                                  ; address: 0x002ae0

002ae0:  c016  movff   (Common_RAM + 22), (Common_RAM + 26) ; reg1: 0x016, reg2: 0x01a
002ae2:  f01a
002ae4:  c017  movff   (Common_RAM + 23), (Common_RAM + 27) ; reg1: 0x017, reg2: 0x01b
002ae6:  f01b
002ae8:  c018  movff   (Common_RAM + 24), (Common_RAM + 28) ; reg1: 0x018, reg2: 0x01c
002aea:  f01c
002aec:  c019  movff   (Common_RAM + 25), (Common_RAM + 29) ; reg1: 0x019, reg2: 0x01d
002aee:  f01d
002af0:  0e18  movlw   0x18
002af2:  d001  bra     label_318                            ; dest: 0x002af6

label_317:                                                  ; address: 0x002af4

002af4:  d85b  rcall   function_020                         ; dest: 0x002bac

label_318:                                                  ; address: 0x002af6

002af6:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
002af8:  d7fd  bra     label_317                            ; dest: 0x002af4
002afa:  501a  movf    (Common_RAM + 26), W, A              ; reg: 0x01a
002afc:  6e24  movwf   (Common_RAM + 36), A                 ; reg: 0x024
002afe:  6624  tstfsz  (Common_RAM + 36), A                 ; reg: 0x024
002b00:  d005  bra     label_320                            ; dest: 0x002b0c

label_319:                                                  ; address: 0x002b02

002b02:  6a12  clrf    (Common_RAM + 18), A                 ; reg: 0x012
002b04:  6a13  clrf    (Common_RAM + 19), A                 ; reg: 0x013
002b06:  6a14  clrf    (Common_RAM + 20), A                 ; reg: 0x014
002b08:  6a15  clrf    (Common_RAM + 21), A                 ; reg: 0x015
002b0a:  d040  bra     label_325                            ; dest: 0x002b8c

label_320:                                                  ; address: 0x002b0c

002b0c:  5024  movf    (Common_RAM + 36), W, A              ; reg: 0x024
002b0e:  0f7b  addlw   0x7b
002b10:  261e  addwf   (Common_RAM + 30), F, A              ; reg: 0x01e
002b12:  c015  movff   (Common_RAM + 21), (Common_RAM + 36) ; reg1: 0x015, reg2: 0x024
002b14:  f024
002b16:  5019  movf    (Common_RAM + 25), W, A              ; reg: 0x019
002b18:  1a24  xorwf   (Common_RAM + 36), F, A              ; reg: 0x024
002b1a:  0e80  movlw   0x80
002b1c:  1624  andwf   (Common_RAM + 36), F, A              ; reg: 0x024
002b1e:  8e14  bsf     (Common_RAM + 20), 0x7, A            ; reg: 0x014
002b20:  8e18  bsf     (Common_RAM + 24), 0x7, A            ; reg: 0x018
002b22:  6a19  clrf    (Common_RAM + 25), A                 ; reg: 0x019
002b24:  6a1f  clrf    (Common_RAM + 31), A                 ; reg: 0x01f
002b26:  6a20  clrf    (Common_RAM + 32), A                 ; reg: 0x020
002b28:  6a21  clrf    (Common_RAM + 33), A                 ; reg: 0x021
002b2a:  6a22  clrf    (Common_RAM + 34), A                 ; reg: 0x022
002b2c:  0e07  movlw   0x07
002b2e:  6e23  movwf   (Common_RAM + 35), A                 ; reg: 0x023

label_321:                                                  ; address: 0x002b30

002b30:  a012  btfss   (Common_RAM + 18), 0x0, A            ; reg: 0x012
002b32:  d002  bra     label_322                            ; dest: 0x002b38
002b34:  5016  movf    (Common_RAM + 22), W, A              ; reg: 0x016
002b36:  d82b  rcall   function_018                         ; dest: 0x002b8e

label_322:                                                  ; address: 0x002b38

002b38:  d832  rcall   function_019                         ; dest: 0x002b9e
002b3a:  3616  rlcf    (Common_RAM + 22), F, A              ; reg: 0x016
002b3c:  3617  rlcf    (Common_RAM + 23), F, A              ; reg: 0x017
002b3e:  3618  rlcf    (Common_RAM + 24), F, A              ; reg: 0x018
002b40:  3619  rlcf    (Common_RAM + 25), F, A              ; reg: 0x019
002b42:  2e23  decfsz  (Common_RAM + 35), F, A              ; reg: 0x023
002b44:  d7f5  bra     label_321                            ; dest: 0x002b30
002b46:  0e11  movlw   0x11
002b48:  6e23  movwf   (Common_RAM + 35), A                 ; reg: 0x023

label_323:                                                  ; address: 0x002b4a

002b4a:  a012  btfss   (Common_RAM + 18), 0x0, A            ; reg: 0x012
002b4c:  d002  bra     label_324                            ; dest: 0x002b52
002b4e:  5016  movf    (Common_RAM + 22), W, A              ; reg: 0x016
002b50:  d81e  rcall   function_018                         ; dest: 0x002b8e

label_324:                                                  ; address: 0x002b52

002b52:  d825  rcall   function_019                         ; dest: 0x002b9e
002b54:  3222  rrcf    (Common_RAM + 34), F, A              ; reg: 0x022
002b56:  3221  rrcf    (Common_RAM + 33), F, A              ; reg: 0x021
002b58:  3220  rrcf    (Common_RAM + 32), F, A              ; reg: 0x020
002b5a:  321f  rrcf    (Common_RAM + 31), F, A              ; reg: 0x01f
002b5c:  2e23  decfsz  (Common_RAM + 35), F, A              ; reg: 0x023
002b5e:  d7f5  bra     label_323                            ; dest: 0x002b4a
002b60:  c01f  movff   (Common_RAM + 31), (Common_RAM + 3)  ; reg1: 0x01f, reg2: 0x003
002b62:  f003
002b64:  c020  movff   (Common_RAM + 32), (Common_RAM + 4)  ; reg1: 0x020, reg2: 0x004
002b66:  f004
002b68:  c021  movff   (Common_RAM + 33), (Common_RAM + 5)  ; reg1: 0x021, reg2: 0x005
002b6a:  f005
002b6c:  c022  movff   (Common_RAM + 34), (Common_RAM + 6)  ; reg1: 0x022, reg2: 0x006
002b6e:  f006
002b70:  c01e  movff   (Common_RAM + 30), (Common_RAM + 7)  ; reg1: 0x01e, reg2: 0x007
002b72:  f007
002b74:  c024  movff   (Common_RAM + 36), (Common_RAM + 8)  ; reg1: 0x024, reg2: 0x008
002b76:  f008
002b78:  ec6c  call    function_029, 0x0                    ; dest: 0x0030d8
002b7a:  f018
002b7c:  c003  movff   (Common_RAM + 3), (Common_RAM + 18)  ; reg1: 0x003, reg2: 0x012
002b7e:  f012
002b80:  c004  movff   (Common_RAM + 4), (Common_RAM + 19)  ; reg1: 0x004, reg2: 0x013
002b82:  f013
002b84:  c005  movff   (Common_RAM + 5), (Common_RAM + 20)  ; reg1: 0x005, reg2: 0x014
002b86:  f014
002b88:  c006  movff   (Common_RAM + 6), (Common_RAM + 21)  ; reg1: 0x006, reg2: 0x015
002b8a:  f015

label_325:                                                  ; address: 0x002b8c

002b8c:  0012  return  0x0

function_018:                                               ; address: 0x002b8e

002b8e:  261f  addwf   (Common_RAM + 31), F, A              ; reg: 0x01f
002b90:  5017  movf    (Common_RAM + 23), W, A              ; reg: 0x017
002b92:  2220  addwfc  (Common_RAM + 32), F, A              ; reg: 0x020
002b94:  5018  movf    (Common_RAM + 24), W, A              ; reg: 0x018
002b96:  2221  addwfc  (Common_RAM + 33), F, A              ; reg: 0x021
002b98:  5019  movf    (Common_RAM + 25), W, A              ; reg: 0x019
002b9a:  2222  addwfc  (Common_RAM + 34), F, A              ; reg: 0x022
002b9c:  0012  return  0x0

function_019:                                               ; address: 0x002b9e

002b9e:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002ba0:  3215  rrcf    (Common_RAM + 21), F, A              ; reg: 0x015
002ba2:  3214  rrcf    (Common_RAM + 20), F, A              ; reg: 0x014
002ba4:  3213  rrcf    (Common_RAM + 19), F, A              ; reg: 0x013
002ba6:  3212  rrcf    (Common_RAM + 18), F, A              ; reg: 0x012
002ba8:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002baa:  0012  return  0x0

function_020:                                               ; address: 0x002bac

002bac:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002bae:  321d  rrcf    (Common_RAM + 29), F, A              ; reg: 0x01d
002bb0:  321c  rrcf    (Common_RAM + 28), F, A              ; reg: 0x01c
002bb2:  321b  rrcf    (Common_RAM + 27), F, A              ; reg: 0x01b
002bb4:  321a  rrcf    (Common_RAM + 26), F, A              ; reg: 0x01a
002bb6:  0012  return  0x0

function_021:                                               ; address: 0x002bb8

002bb8:  67c5  tstfsz  0xc5, B                              ; reg: 0x0c5
002bba:  d010  bra     label_326                            ; dest: 0x002bdc
002bbc:  c082  movff   0x082, (Common_RAM + 3)              ; reg2: 0x003
002bbe:  f003
002bc0:  c083  movff   0x083, (Common_RAM + 4)              ; reg2: 0x004
002bc2:  f004
002bc4:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
002bc6:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
002bc8:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002bca:  0ec0  movlw   0xc0
002bcc:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002bce:  0103  movlb   0x3
002bd0:  0e03  movlw   0x03
002bd2:  6e0a  movwf   0x0a, A                              ; reg: 0x30a
002bd4:  0e00  movlw   0x00
002bd6:  6e09  movwf   0x09, A                              ; reg: 0x309
002bd8:  ec14  call    function_061, 0x0                    ; dest: 0x004028
002bda:  f020

label_326:                                                  ; address: 0x002bdc

002bdc:  0101  movlb   0x1
002bde:  511b  movf    0x1b, W, B                           ; reg: 0x11b
002be0:  e004  bz      label_327
002be2:  6a1d  clrf    (Common_RAM + 29), A                 ; reg: 0x01d
002be4:  0e02  movlw   0x02
002be6:  6e1c  movwf   (Common_RAM + 28), A                 ; reg: 0x01c
002be8:  d002  bra     label_328                            ; dest: 0x002bee

label_327:                                                  ; address: 0x002bea

002bea:  6a1c  clrf    (Common_RAM + 28), A                 ; reg: 0x01c
002bec:  6a1d  clrf    (Common_RAM + 29), A                 ; reg: 0x01d

label_328:                                                  ; address: 0x002bee

002bee:  c01c  movff   (Common_RAM + 28), (Common_RAM + 30) ; reg1: 0x01c, reg2: 0x01e
002bf0:  f01e
002bf2:  0e04  movlw   0x04
002bf4:  6e1f  movwf   (Common_RAM + 31), A                 ; reg: 0x01f

label_329:                                                  ; address: 0x002bf6

002bf6:  0e1a  movlw   0x1a
002bf8:  6e18  movwf   (Common_RAM + 24), A                 ; reg: 0x018
002bfa:  0e01  movlw   0x01
002bfc:  6e19  movwf   (Common_RAM + 25), A                 ; reg: 0x019
002bfe:  501f  movf    (Common_RAM + 31), W, A              ; reg: 0x01f
002c00:  2618  addwf   (Common_RAM + 24), F, A              ; reg: 0x018
002c02:  0e00  movlw   0x00
002c04:  2219  addwfc  (Common_RAM + 25), F, A              ; reg: 0x019
002c06:  501e  movf    (Common_RAM + 30), W, A              ; reg: 0x01e
002c08:  5c18  subwf   (Common_RAM + 24), W, A              ; reg: 0x018
002c0a:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
002c0c:  5019  movf    (Common_RAM + 25), W, A              ; reg: 0x019
002c0e:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
002c10:  0419  decf    (Common_RAM + 25), W, A              ; reg: 0x019
002c12:  6eda  movwf   FSR2H, A                             ; reg: 0xfda
002c14:  0e00  movlw   0x00
002c16:  6e1a  movwf   (Common_RAM + 26), A                 ; reg: 0x01a
002c18:  0e03  movlw   0x03
002c1a:  6e1b  movwf   (Common_RAM + 27), A                 ; reg: 0x01b
002c1c:  0100  movlb   0x0
002c1e:  51c5  movf    0xc5, W, B                           ; reg: 0x0c5
002c20:  261a  addwf   (Common_RAM + 26), F, A              ; reg: 0x01a
002c22:  0e00  movlw   0x00
002c24:  221b  addwfc  (Common_RAM + 27), F, A              ; reg: 0x01b
002c26:  501f  movf    (Common_RAM + 31), W, A              ; reg: 0x01f
002c28:  241a  addwf   (Common_RAM + 26), W, A              ; reg: 0x01a
002c2a:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
002c2c:  0e00  movlw   0x00
002c2e:  201b  addwfc  (Common_RAM + 27), W, A              ; reg: 0x01b
002c30:  6ee2  movwf   FSR1H, A                             ; reg: 0xfe2
002c32:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
002c34:  ffe7
002c36:  2a1f  incf    (Common_RAM + 31), F, A              ; reg: 0x01f
002c38:  0e17  movlw   0x17
002c3a:  641f  cpfsgt  (Common_RAM + 31), A                 ; reg: 0x01f
002c3c:  d7dc  bra     label_329                            ; dest: 0x002bf6
002c3e:  0e18  movlw   0x18
002c40:  27c5  addwf   0xc5, F, B                           ; reg: 0x0c5
002c42:  0ebf  movlw   0xbf
002c44:  65c5  cpfsgt  0xc5, B                              ; reg: 0x0c5
002c46:  d02f  bra     label_330                            ; dest: 0x002ca6
002c48:  6bc5  clrf    0xc5, B                              ; reg: 0x0c5
002c4a:  0e3f  movlw   0x3f
002c4c:  5d82  subwf   0x82, W, B                           ; reg: 0x082
002c4e:  0e5f  movlw   0x5f
002c50:  5983  subwfb  0x83, W, B                           ; reg: 0x083
002c52:  e229  bc      label_330
002c54:  c082  movff   0x082, (Common_RAM + 3)              ; reg2: 0x003
002c56:  f003
002c58:  c083  movff   0x083, (Common_RAM + 4)              ; reg2: 0x004
002c5a:  f004
002c5c:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
002c5e:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
002c60:  0ebf  movlw   0xbf
002c62:  2582  addwf   0x82, W, B                           ; reg: 0x082
002c64:  6e18  movwf   (Common_RAM + 24), A                 ; reg: 0x018
002c66:  0e00  movlw   0x00
002c68:  2183  addwfc  0x83, W, B                           ; reg: 0x083
002c6a:  6e19  movwf   (Common_RAM + 25), A                 ; reg: 0x019
002c6c:  c018  movff   (Common_RAM + 24), (Common_RAM + 7)  ; reg1: 0x018, reg2: 0x007
002c6e:  f007
002c70:  c019  movff   (Common_RAM + 25), (Common_RAM + 8)  ; reg1: 0x019, reg2: 0x008
002c72:  f008
002c74:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009
002c76:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
002c78:  ecd6  call    function_054, 0x0                    ; dest: 0x003dac
002c7a:  f01e
002c7c:  c082  movff   0x082, (Common_RAM + 3)              ; reg2: 0x003
002c7e:  f003
002c80:  c083  movff   0x083, (Common_RAM + 4)              ; reg2: 0x004
002c82:  f004
002c84:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
002c86:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
002c88:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
002c8a:  0ec0  movlw   0xc0
002c8c:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
002c8e:  0103  movlb   0x3
002c90:  0e03  movlw   0x03
002c92:  6e0a  movwf   0x0a, A                              ; reg: 0x30a
002c94:  0e00  movlw   0x00
002c96:  6e09  movwf   0x09, A                              ; reg: 0x309
002c98:  ec37  call    function_025, 0x0                    ; dest: 0x002e6e
002c9a:  f017
002c9c:  0ec0  movlw   0xc0
002c9e:  0100  movlb   0x0
002ca0:  2782  addwf   0x82, F, B                           ; reg: 0x082
002ca2:  0e00  movlw   0x00
002ca4:  2383  addwfc  0x83, F, B                           ; reg: 0x083

label_330:                                                  ; address: 0x002ca6

002ca6:  0012  return  0x0

function_022:                                               ; address: 0x002ca8

002ca8:  c00d  movff   (Common_RAM + 13), (Common_RAM + 21) ; reg1: 0x00d, reg2: 0x015
002caa:  f015
002cac:  c00e  movff   (Common_RAM + 14), (Common_RAM + 22) ; reg1: 0x00e, reg2: 0x016
002cae:  f016
002cb0:  c00f  movff   (Common_RAM + 15), (Common_RAM + 23) ; reg1: 0x00f, reg2: 0x017
002cb2:  f017
002cb4:  c010  movff   (Common_RAM + 16), (Common_RAM + 24) ; reg1: 0x010, reg2: 0x018
002cb6:  f018
002cb8:  0e18  movlw   0x18
002cba:  d001  bra     label_332                            ; dest: 0x002cbe

label_331:                                                  ; address: 0x002cbc

002cbc:  d861  rcall   function_023                         ; dest: 0x002d80

label_332:                                                  ; address: 0x002cbe

002cbe:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
002cc0:  d7fd  bra     label_331                            ; dest: 0x002cbc
002cc2:  5015  movf    (Common_RAM + 21), W, A              ; reg: 0x015
002cc4:  6e1e  movwf   (Common_RAM + 30), A                 ; reg: 0x01e
002cc6:  661e  tstfsz  (Common_RAM + 30), A                 ; reg: 0x01e
002cc8:  d001  bra     label_333                            ; dest: 0x002ccc
002cca:  d011  bra     label_336                            ; dest: 0x002cee

label_333:                                                  ; address: 0x002ccc

002ccc:  c011  movff   (Common_RAM + 17), (Common_RAM + 21) ; reg1: 0x011, reg2: 0x015
002cce:  f015
002cd0:  c012  movff   (Common_RAM + 18), (Common_RAM + 22) ; reg1: 0x012, reg2: 0x016
002cd2:  f016
002cd4:  c013  movff   (Common_RAM + 19), (Common_RAM + 23) ; reg1: 0x013, reg2: 0x017
002cd6:  f017
002cd8:  c014  movff   (Common_RAM + 20), (Common_RAM + 24) ; reg1: 0x014, reg2: 0x018
002cda:  f018
002cdc:  0e18  movlw   0x18
002cde:  d001  bra     label_335                            ; dest: 0x002ce2

label_334:                                                  ; address: 0x002ce0

002ce0:  d84f  rcall   function_023                         ; dest: 0x002d80

label_335:                                                  ; address: 0x002ce2

002ce2:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
002ce4:  d7fd  bra     label_334                            ; dest: 0x002ce0
002ce6:  5015  movf    (Common_RAM + 21), W, A              ; reg: 0x015
002ce8:  6e1f  movwf   (Common_RAM + 31), A                 ; reg: 0x01f
002cea:  661f  tstfsz  (Common_RAM + 31), A                 ; reg: 0x01f
002cec:  d005  bra     label_337                            ; dest: 0x002cf8

label_336:                                                  ; address: 0x002cee

002cee:  6a0d  clrf    (Common_RAM + 13), A                 ; reg: 0x00d
002cf0:  6a0e  clrf    (Common_RAM + 14), A                 ; reg: 0x00e
002cf2:  6a0f  clrf    (Common_RAM + 15), A                 ; reg: 0x00f
002cf4:  6a10  clrf    (Common_RAM + 16), A                 ; reg: 0x010
002cf6:  d043  bra     label_340                            ; dest: 0x002d7e

label_337:                                                  ; address: 0x002cf8

002cf8:  501f  movf    (Common_RAM + 31), W, A              ; reg: 0x01f
002cfa:  0f89  addlw   0x89
002cfc:  5e1e  subwf   (Common_RAM + 30), F, A              ; reg: 0x01e
002cfe:  c010  movff   (Common_RAM + 16), (Common_RAM + 31) ; reg1: 0x010, reg2: 0x01f
002d00:  f01f
002d02:  5014  movf    (Common_RAM + 20), W, A              ; reg: 0x014
002d04:  1a1f  xorwf   (Common_RAM + 31), F, A              ; reg: 0x01f
002d06:  0e80  movlw   0x80
002d08:  161f  andwf   (Common_RAM + 31), F, A              ; reg: 0x01f
002d0a:  8e0f  bsf     (Common_RAM + 15), 0x7, A            ; reg: 0x00f
002d0c:  6a10  clrf    (Common_RAM + 16), A                 ; reg: 0x010
002d0e:  8e13  bsf     (Common_RAM + 19), 0x7, A            ; reg: 0x013
002d10:  6a14  clrf    (Common_RAM + 20), A                 ; reg: 0x014
002d12:  0e20  movlw   0x20
002d14:  6e1d  movwf   (Common_RAM + 29), A                 ; reg: 0x01d

label_338:                                                  ; address: 0x002d16

002d16:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002d18:  3619  rlcf    (Common_RAM + 25), F, A              ; reg: 0x019
002d1a:  361a  rlcf    (Common_RAM + 26), F, A              ; reg: 0x01a
002d1c:  361b  rlcf    (Common_RAM + 27), F, A              ; reg: 0x01b
002d1e:  361c  rlcf    (Common_RAM + 28), F, A              ; reg: 0x01c
002d20:  5011  movf    (Common_RAM + 17), W, A              ; reg: 0x011
002d22:  5c0d  subwf   (Common_RAM + 13), W, A              ; reg: 0x00d
002d24:  5012  movf    (Common_RAM + 18), W, A              ; reg: 0x012
002d26:  580e  subwfb  (Common_RAM + 14), W, A              ; reg: 0x00e
002d28:  5013  movf    (Common_RAM + 19), W, A              ; reg: 0x013
002d2a:  580f  subwfb  (Common_RAM + 15), W, A              ; reg: 0x00f
002d2c:  5014  movf    (Common_RAM + 20), W, A              ; reg: 0x014
002d2e:  5810  subwfb  (Common_RAM + 16), W, A              ; reg: 0x010
002d30:  e309  bnc     label_339
002d32:  5011  movf    (Common_RAM + 17), W, A              ; reg: 0x011
002d34:  5e0d  subwf   (Common_RAM + 13), F, A              ; reg: 0x00d
002d36:  5012  movf    (Common_RAM + 18), W, A              ; reg: 0x012
002d38:  5a0e  subwfb  (Common_RAM + 14), F, A              ; reg: 0x00e
002d3a:  5013  movf    (Common_RAM + 19), W, A              ; reg: 0x013
002d3c:  5a0f  subwfb  (Common_RAM + 15), F, A              ; reg: 0x00f
002d3e:  5014  movf    (Common_RAM + 20), W, A              ; reg: 0x014
002d40:  5a10  subwfb  (Common_RAM + 16), F, A              ; reg: 0x010
002d42:  8019  bsf     (Common_RAM + 25), 0x0, A            ; reg: 0x019

label_339:                                                  ; address: 0x002d44

002d44:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002d46:  360d  rlcf    (Common_RAM + 13), F, A              ; reg: 0x00d
002d48:  360e  rlcf    (Common_RAM + 14), F, A              ; reg: 0x00e
002d4a:  360f  rlcf    (Common_RAM + 15), F, A              ; reg: 0x00f
002d4c:  3610  rlcf    (Common_RAM + 16), F, A              ; reg: 0x010
002d4e:  2e1d  decfsz  (Common_RAM + 29), F, A              ; reg: 0x01d
002d50:  d7e2  bra     label_338                            ; dest: 0x002d16
002d52:  c019  movff   (Common_RAM + 25), (Common_RAM + 3)  ; reg1: 0x019, reg2: 0x003
002d54:  f003
002d56:  c01a  movff   (Common_RAM + 26), (Common_RAM + 4)  ; reg1: 0x01a, reg2: 0x004
002d58:  f004
002d5a:  c01b  movff   (Common_RAM + 27), (Common_RAM + 5)  ; reg1: 0x01b, reg2: 0x005
002d5c:  f005
002d5e:  c01c  movff   (Common_RAM + 28), (Common_RAM + 6)  ; reg1: 0x01c, reg2: 0x006
002d60:  f006
002d62:  c01e  movff   (Common_RAM + 30), (Common_RAM + 7)  ; reg1: 0x01e, reg2: 0x007
002d64:  f007
002d66:  c01f  movff   (Common_RAM + 31), (Common_RAM + 8)  ; reg1: 0x01f, reg2: 0x008
002d68:  f008
002d6a:  ec6c  call    function_029, 0x0                    ; dest: 0x0030d8
002d6c:  f018
002d6e:  c003  movff   (Common_RAM + 3), (Common_RAM + 13)  ; reg1: 0x003, reg2: 0x00d
002d70:  f00d
002d72:  c004  movff   (Common_RAM + 4), (Common_RAM + 14)  ; reg1: 0x004, reg2: 0x00e
002d74:  f00e
002d76:  c005  movff   (Common_RAM + 5), (Common_RAM + 15)  ; reg1: 0x005, reg2: 0x00f
002d78:  f00f
002d7a:  c006  movff   (Common_RAM + 6), (Common_RAM + 16)  ; reg1: 0x006, reg2: 0x010
002d7c:  f010

label_340:                                                  ; address: 0x002d7e

002d7e:  0012  return  0x0

function_023:                                               ; address: 0x002d80

002d80:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002d82:  3218  rrcf    (Common_RAM + 24), F, A              ; reg: 0x018
002d84:  3217  rrcf    (Common_RAM + 23), F, A              ; reg: 0x017
002d86:  3216  rrcf    (Common_RAM + 22), F, A              ; reg: 0x016
002d88:  3215  rrcf    (Common_RAM + 21), F, A              ; reg: 0x015
002d8a:  0012  return  0x0

function_024:                                               ; address: 0x002d8c

002d8c:  9ef2  bcf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
002d8e:  948a  bcf     LATB, LATB2, A                       ; reg: 0xf8a, bit: 2
002d90:  0100  movlb   0x0
002d92:  6b88  clrf    0x88, B                              ; reg: 0x088
002d94:  6b89  clrf    0x89, B                              ; reg: 0x089
002d96:  82c2  bsf     ADCON0, GO, A                        ; reg: 0xfc2, bit: 1

label_341:                                                  ; address: 0x002d98

002d98:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002d9a:  0e0a  movlw   0x0a
002d9c:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002d9e:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
002da0:  f022
002da2:  b2c2  btfsc   ADCON0, GO, A                        ; reg: 0xfc2, bit: 1
002da4:  d00b  bra     label_342                            ; dest: 0x002dbc
002da6:  50c4  movf    ADRESH, W, A                         ; reg: 0xfc4
002da8:  6e5d  movwf   (Common_RAM + 93), A                 ; reg: 0x05d
002daa:  6a5c  clrf    (Common_RAM + 92), A                 ; reg: 0x05c
002dac:  50c3  movf    ADRESL, W, A                         ; reg: 0xfc3
002dae:  245c  addwf   (Common_RAM + 92), W, A              ; reg: 0x05c
002db0:  0100  movlb   0x0
002db2:  6f88  movwf   0x88, B                              ; reg: 0x088
002db4:  0e00  movlw   0x00
002db6:  205d  addwfc  (Common_RAM + 93), W, A              ; reg: 0x05d
002db8:  6f89  movwf   0x89, B                              ; reg: 0x089
002dba:  82c2  bsf     ADCON0, GO, A                        ; reg: 0xfc2, bit: 1

label_342:                                                  ; address: 0x002dbc

002dbc:  0e36  movlw   0x36
002dbe:  0100  movlb   0x0
002dc0:  5d88  subwf   0x88, W, B                           ; reg: 0x088
002dc2:  0e02  movlw   0x02
002dc4:  5989  subwfb  0x89, W, B                           ; reg: 0x089
002dc6:  e3e8  bnc     label_341
002dc8:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002dca:  0e46  movlw   0x46
002dcc:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002dce:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
002dd0:  f022
002dd2:  6ab0  clrf    SPBRGH, A                            ; reg: 0xfb0
002dd4:  0e7f  movlw   0x7f
002dd6:  6eaf  movwf   SPBRG, A                             ; reg: 0xfaf
002dd8:  92d3  bcf     OSCCON, SCS1, A                      ; reg: 0xfd3, bit: 1
002dda:  988a  bcf     LATB, LATB4, A                       ; reg: 0xf8a, bit: 4
002ddc:  9c89  bcf     LATA, LATA6, A                       ; reg: 0xf89, bit: 6
002dde:  968a  bcf     LATB, LATB3, A                       ; reg: 0xf8a, bit: 3
002de0:  ecb3  call    function_128, 0x0                    ; dest: 0x004966
002de2:  f024
002de4:  8293  bsf     TRISB, RB1, A                        ; reg: 0xf93, bit: 1
002de6:  8093  bsf     TRISB, RB0, A                        ; reg: 0xf93, bit: 0
002de8:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002dea:  0e64  movlw   0x64
002dec:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002dee:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
002df0:  f022
002df2:  888a  bsf     LATB, LATB4, A                       ; reg: 0xf8a, bit: 4
002df4:  0e05  movlw   0x05
002df6:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
002df8:  0edc  movlw   0xdc
002dfa:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002dfc:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
002dfe:  f022
002e00:  8293  bsf     TRISB, RB1, A                        ; reg: 0xf93, bit: 1
002e02:  8093  bsf     TRISB, RB0, A                        ; reg: 0xf93, bit: 0
002e04:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
002e06:  0e01  movlw   0x01
002e08:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002e0a:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
002e0c:  f022
002e0e:  0e80  movlw   0x80
002e10:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
002e12:  0e08  movlw   0x08
002e14:  ecd9  call    function_101, 0x0                    ; dest: 0x0047b2
002e16:  f023
002e18:  8c89  bsf     LATA, LATA6, A                       ; reg: 0xf89, bit: 6
002e1a:  0e00  movlw   0x00
002e1c:  6a55  clrf    (Common_RAM + 85), A                 ; reg: 0x055
002e1e:  6a56  clrf    (Common_RAM + 86), A                 ; reg: 0x056
002e20:  6a57  clrf    (Common_RAM + 87), A                 ; reg: 0x057
002e22:  6a58  clrf    (Common_RAM + 88), A                 ; reg: 0x058
002e24:  ec72  call    function_081, 0x0                    ; dest: 0x0044e4
002e26:  f022
002e28:  ecba  call    function_084, 0x0                    ; dest: 0x004574
002e2a:  f022
002e2c:  868a  bsf     LATB, LATB3, A                       ; reg: 0xf8a, bit: 3
002e2e:  eca1  call    function_122, 0x0                    ; dest: 0x004942
002e30:  f024
002e32:  ec7c  call    function_031, 0x0                    ; dest: 0x0032f8
002e34:  f019
002e36:  eca1  call    function_122, 0x0                    ; dest: 0x004942
002e38:  f024
002e3a:  0100  movlb   0x0
002e3c:  837e  bsf     0x7e, 0x1, B                         ; reg: 0x07e
002e3e:  877e  bsf     0x7e, 0x3, B                         ; reg: 0x07e
002e40:  897e  bsf     0x7e, 0x4, B                         ; reg: 0x07e
002e42:  817f  bsf     0x7f, 0x0, B                         ; reg: 0x07f
002e44:  837f  bsf     0x7f, 0x1, B                         ; reg: 0x07f
002e46:  0e00  movlw   0x00
002e48:  ec77  call    function_005, 0x0                    ; dest: 0x0018ee
002e4a:  f00c
002e4c:  0e01  movlw   0x01
002e4e:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
002e50:  0e1b  movlw   0x1b
002e52:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
002e54:  f023
002e56:  9af2  bcf     INTCON, T0IE, A                      ; reg: 0xff2, bit: 5
002e58:  9ed5  bcf     T0CON, TMR0ON, A                     ; reg: 0xfd5, bit: 7
002e5a:  0ea4  movlw   0xa4
002e5c:  6ed7  movwf   TMR0H, A                             ; reg: 0xfd7
002e5e:  0e71  movlw   0x71
002e60:  6ed6  movwf   TMR0L, A                             ; reg: 0xfd6
002e62:  0100  movlb   0x0
002e64:  6ba1  clrf    0xa1, B                              ; reg: 0x0a1
002e66:  9594  bcf     0x94, 0x2, B                         ; reg: 0x094
002e68:  8ef2  bsf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
002e6a:  ef8c  goto    label_610                            ; dest: 0x004918
002e6c:  f024

function_025:                                               ; address: 0x002e6e

002e6e:  6a10  clrf    (Common_RAM + 16), A                 ; reg: 0x010
002e70:  c003  movff   (Common_RAM + 3), (Common_RAM + 20)  ; reg1: 0x003, reg2: 0x014
002e72:  f014
002e74:  c004  movff   (Common_RAM + 4), (Common_RAM + 21)  ; reg1: 0x004, reg2: 0x015
002e76:  f015
002e78:  c005  movff   (Common_RAM + 5), (Common_RAM + 22)  ; reg1: 0x005, reg2: 0x016
002e7a:  f016
002e7c:  c006  movff   (Common_RAM + 6), (Common_RAM + 23)  ; reg1: 0x006, reg2: 0x017
002e7e:  f017
002e80:  0e05  movlw   0x05
002e82:  6e0b  movwf   (Common_RAM + 11), A                 ; reg: 0x00b

label_343:                                                  ; address: 0x002e84

002e84:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002e86:  3206  rrcf    (Common_RAM + 6), F, A               ; reg: 0x006
002e88:  3205  rrcf    (Common_RAM + 5), F, A               ; reg: 0x005
002e8a:  3204  rrcf    (Common_RAM + 4), F, A               ; reg: 0x004
002e8c:  3203  rrcf    (Common_RAM + 3), F, A               ; reg: 0x003
002e8e:  2e0b  decfsz  (Common_RAM + 11), F, A              ; reg: 0x00b
002e90:  d7f9  bra     label_343                            ; dest: 0x002e84
002e92:  0e05  movlw   0x05

label_344:                                                  ; address: 0x002e94

002e94:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
002e96:  3603  rlcf    (Common_RAM + 3), F, A               ; reg: 0x003
002e98:  3604  rlcf    (Common_RAM + 4), F, A               ; reg: 0x004
002e9a:  3605  rlcf    (Common_RAM + 5), F, A               ; reg: 0x005
002e9c:  3606  rlcf    (Common_RAM + 6), F, A               ; reg: 0x006
002e9e:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
002ea0:  d7f9  bra     label_344                            ; dest: 0x002e94
002ea2:  0e20  movlw   0x20
002ea4:  2603  addwf   (Common_RAM + 3), F, A               ; reg: 0x003
002ea6:  0e00  movlw   0x00
002ea8:  2204  addwfc  (Common_RAM + 4), F, A               ; reg: 0x004
002eaa:  2205  addwfc  (Common_RAM + 5), F, A               ; reg: 0x005
002eac:  2206  addwfc  (Common_RAM + 6), F, A               ; reg: 0x006
002eae:  5014  movf    (Common_RAM + 20), W, A              ; reg: 0x014
002eb0:  5c03  subwf   (Common_RAM + 3), W, A               ; reg: 0x003
002eb2:  6e0f  movwf   (Common_RAM + 15), A                 ; reg: 0x00f
002eb4:  d047  bra     label_351                            ; dest: 0x002f44

label_345:                                                  ; address: 0x002eb6

002eb6:  c016  movff   (Common_RAM + 22), (Common_RAM + 19) ; reg1: 0x016, reg2: 0x013
002eb8:  f013
002eba:  c015  movff   (Common_RAM + 21), (Common_RAM + 18) ; reg1: 0x015, reg2: 0x012
002ebc:  f012
002ebe:  c014  movff   (Common_RAM + 20), (Common_RAM + 17) ; reg1: 0x014, reg2: 0x011
002ec0:  f011
002ec2:  d019  bra     label_347                            ; dest: 0x002ef6

label_346:                                                  ; address: 0x002ec4

002ec4:  c009  movff   (Common_RAM + 9), FSR2L              ; reg1: 0x009, reg2: 0xfd9
002ec6:  ffd9
002ec8:  c00a  movff   (Common_RAM + 10), FSR2H             ; reg1: 0x00a, reg2: 0xfda
002eca:  ffda
002ecc:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
002ece:  c011  movff   (Common_RAM + 17), TBLPTRL           ; reg1: 0x011, reg2: 0xff6
002ed0:  fff6
002ed2:  c012  movff   (Common_RAM + 18), TBLPTRH           ; reg1: 0x012, reg2: 0xff7
002ed4:  fff7
002ed6:  c013  movff   (Common_RAM + 19), TBLPTRU           ; reg1: 0x013, reg2: 0xff8
002ed8:  fff8
002eda:  6ef5  movwf   TABLAT, A                            ; reg: 0xff5
002edc:  000c  tblwt*
002ede:  4a09  infsnz  (Common_RAM + 9), F, A               ; reg: 0x009
002ee0:  2a0a  incf    (Common_RAM + 10), F, A              ; reg: 0x00a
002ee2:  2a11  incf    (Common_RAM + 17), F, A              ; reg: 0x011
002ee4:  0e00  movlw   0x00
002ee6:  2212  addwfc  (Common_RAM + 18), F, A              ; reg: 0x012
002ee8:  2213  addwfc  (Common_RAM + 19), F, A              ; reg: 0x013
002eea:  0607  decf    (Common_RAM + 7), F, A               ; reg: 0x007
002eec:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
002eee:  0608  decf    (Common_RAM + 8), F, A               ; reg: 0x008
002ef0:  5008  movf    (Common_RAM + 8), W, A               ; reg: 0x008
002ef2:  1007  iorwf   (Common_RAM + 7), W, A               ; reg: 0x007
002ef4:  e003  bz      label_348

label_347:                                                  ; address: 0x002ef6

002ef6:  060f  decf    (Common_RAM + 15), F, A              ; reg: 0x00f
002ef8:  280f  incf    (Common_RAM + 15), W, A              ; reg: 0x00f
002efa:  e1e4  bnz     label_346

label_348:                                                  ; address: 0x002efc

002efc:  c013  movff   (Common_RAM + 19), (Common_RAM + 14) ; reg1: 0x013, reg2: 0x00e
002efe:  f00e
002f00:  c012  movff   (Common_RAM + 18), (Common_RAM + 13) ; reg1: 0x012, reg2: 0x00d
002f02:  f00d
002f04:  c011  movff   (Common_RAM + 17), (Common_RAM + 12) ; reg1: 0x011, reg2: 0x00c
002f06:  f00c
002f08:  c016  movff   (Common_RAM + 22), (Common_RAM + 19) ; reg1: 0x016, reg2: 0x013
002f0a:  f013
002f0c:  c015  movff   (Common_RAM + 21), (Common_RAM + 18) ; reg1: 0x015, reg2: 0x012
002f0e:  f012
002f10:  c014  movff   (Common_RAM + 20), (Common_RAM + 17) ; reg1: 0x014, reg2: 0x011
002f12:  f011
002f14:  8ea6  bsf     EECON1, EEPGD, A                     ; reg: 0xfa6, bit: 7
002f16:  9ca6  bcf     EECON1, CFGS, A                      ; reg: 0xfa6, bit: 6
002f18:  84a6  bsf     EECON1, WREN, A                      ; reg: 0xfa6, bit: 2
002f1a:  aef2  btfss   INTCON, GIE, A                       ; reg: 0xff2, bit: 7
002f1c:  d003  bra     label_349                            ; dest: 0x002f24
002f1e:  9ef2  bcf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
002f20:  0e01  movlw   0x01
002f22:  6e10  movwf   (Common_RAM + 16), A                 ; reg: 0x010

label_349:                                                  ; address: 0x002f24

002f24:  ec03  call    function_076, 0x0                    ; dest: 0x004406
002f26:  f022
002f28:  94a6  bcf     EECON1, WREN, A                      ; reg: 0xfa6, bit: 2
002f2a:  5010  movf    (Common_RAM + 16), W, A              ; reg: 0x010
002f2c:  e002  bz      label_350
002f2e:  8ef2  bsf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
002f30:  6a10  clrf    (Common_RAM + 16), A                 ; reg: 0x010

label_350:                                                  ; address: 0x002f32

002f32:  0e20  movlw   0x20
002f34:  6e0f  movwf   (Common_RAM + 15), A                 ; reg: 0x00f
002f36:  500c  movf    (Common_RAM + 12), W, A              ; reg: 0x00c
002f38:  6e14  movwf   (Common_RAM + 20), A                 ; reg: 0x014
002f3a:  500d  movf    (Common_RAM + 13), W, A              ; reg: 0x00d
002f3c:  6e15  movwf   (Common_RAM + 21), A                 ; reg: 0x015
002f3e:  500e  movf    (Common_RAM + 14), W, A              ; reg: 0x00e
002f40:  6e16  movwf   (Common_RAM + 22), A                 ; reg: 0x016
002f42:  6a17  clrf    (Common_RAM + 23), A                 ; reg: 0x017

label_351:                                                  ; address: 0x002f44

002f44:  5008  movf    (Common_RAM + 8), W, A               ; reg: 0x008
002f46:  1007  iorwf   (Common_RAM + 7), W, A               ; reg: 0x007
002f48:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
002f4a:  0012  return  0x0
002f4c:  d7b4  bra     label_345                            ; dest: 0x002eb6

function_026:                                               ; address: 0x002f4e

002f4e:  ecae  call    function_098, 0x0                    ; dest: 0x00475c
002f50:  f023
002f52:  67cd  tstfsz  0xcd, B                              ; reg: 0x0cd
002f54:  d001  bra     label_352                            ; dest: 0x002f58
002f56:  d060  bra     label_360                            ; dest: 0x003018

label_352:                                                  ; address: 0x002f58

002f58:  b468  btfsc   UIR, ACTVIF, A                       ; reg: 0xf68, bit: 2
002f5a:  ec1e  call    function_106, 0x0                    ; dest: 0x00483c
002f5c:  f024
002f5e:  b26d  btfsc   UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
002f60:  d05b  bra     label_360                            ; dest: 0x003018
002f62:  b068  btfsc   UIR, URSTIF, A                       ; reg: 0xf68, bit: 0
002f64:  ec6b  call    function_063, 0x0                    ; dest: 0x0040d6
002f66:  f020
002f68:  b868  btfsc   UIR, IDLEIF, A                       ; reg: 0xf68, bit: 4
002f6a:  ec90  call    function_096, 0x0                    ; dest: 0x004720
002f6c:  f023
002f6e:  0e03  movlw   0x03
002f70:  0100  movlb   0x0
002f72:  5dcd  subwf   0xcd, W, B                           ; reg: 0x0cd
002f74:  e351  bnc     label_360
002f76:  6bc4  clrf    0xc4, B                              ; reg: 0x0c4

label_353:                                                  ; address: 0x002f78

002f78:  a668  btfss   UIR, TRNIF, A                        ; reg: 0xf68, bit: 3
002f7a:  d04e  bra     label_360                            ; dest: 0x003018
002f7c:  506c  movf    USTAT, W, A                          ; reg: 0xf6c
002f7e:  cf6c  movff   USTAT, (Common_RAM + 6)              ; reg1: 0xf6c, reg2: 0x006
002f80:  f006
002f82:  0e7c  movlw   0x7c
002f84:  1606  andwf   (Common_RAM + 6), F, A               ; reg: 0x006
002f86:  e13b  bnz     label_357
002f88:  b26c  btfsc   USTAT, PPBI, A                       ; reg: 0xf6c, bit: 1
002f8a:  d005  bra     label_354                            ; dest: 0x002f96
002f8c:  0e04  movlw   0x04
002f8e:  0100  movlb   0x0
002f90:  6f7b  movwf   0x7b, B                              ; reg: 0x07b
002f92:  0e00  movlw   0x00
002f94:  d003  bra     label_355                            ; dest: 0x002f9c

label_354:                                                  ; address: 0x002f96

002f96:  0e04  movlw   0x04
002f98:  0100  movlb   0x0
002f9a:  6f7b  movwf   0x7b, B                              ; reg: 0x07b

label_355:                                                  ; address: 0x002f9c

002f9c:  0100  movlb   0x0
002f9e:  6f7a  movwf   0x7a, B                              ; reg: 0x07a
002fa0:  9668  bcf     UIR, TRNIF, A                        ; reg: 0xf68, bit: 3
002fa2:  c07a  movff   0x07a, FSR2L                         ; reg2: 0xfd9
002fa4:  ffd9
002fa6:  c07b  movff   0x07b, FSR2H                         ; reg2: 0xfda
002fa8:  ffda
002faa:  30df  rrcf    INDF2, W, A                          ; reg: 0xfdf
002fac:  32e8  rrcf    WREG, F, A                           ; reg: 0xfe8
002fae:  0b0f  andlw   0x0f
002fb0:  0a0d  xorlw   0x0d
002fb2:  e12d  bnz     label_359
002fb4:  6b90  clrf    0x90, B                              ; reg: 0x090

label_356:                                                  ; address: 0x002fb6

002fb6:  ee20  lfsr    0x2, 0x002
002fb8:  f002
002fba:  517a  movf    0x7a, W, B                           ; reg: 0x07a
002fbc:  26d9  addwf   FSR2L, F, A                          ; reg: 0xfd9
002fbe:  517b  movf    0x7b, W, B                           ; reg: 0x07b
002fc0:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
002fc2:  cfde  movff   POSTINC2, (Common_RAM + 6)           ; reg1: 0xfde, reg2: 0x006
002fc4:  f006
002fc6:  cfdd  movff   POSTDEC2, (Common_RAM + 7)           ; reg1: 0xfdd, reg2: 0x007
002fc8:  f007
002fca:  c006  movff   (Common_RAM + 6), FSR2L              ; reg1: 0x006, reg2: 0xfd9
002fcc:  ffd9
002fce:  c007  movff   (Common_RAM + 7), FSR2H              ; reg1: 0x007, reg2: 0xfda
002fd0:  ffda
002fd2:  5190  movf    0x90, W, B                           ; reg: 0x090
002fd4:  0fcf  addlw   0xcf
002fd6:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
002fd8:  6ae2  clrf    FSR1H, A                             ; reg: 0xfe2
002fda:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
002fdc:  ffe7
002fde:  ee20  lfsr    0x2, 0x002
002fe0:  f002
002fe2:  517a  movf    0x7a, W, B                           ; reg: 0x07a
002fe4:  26d9  addwf   FSR2L, F, A                          ; reg: 0xfd9
002fe6:  517b  movf    0x7b, W, B                           ; reg: 0x07b
002fe8:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
002fea:  2ade  incf    POSTINC2, F, A                       ; reg: 0xfde
002fec:  0e00  movlw   0x00
002fee:  22dd  addwfc  POSTDEC2, F, A                       ; reg: 0xfdd
002ff0:  2b90  incf    0x90, F, B                           ; reg: 0x090
002ff2:  0e07  movlw   0x07
002ff4:  6590  cpfsgt  0x90, B                              ; reg: 0x090
002ff6:  d7df  bra     label_356                            ; dest: 0x002fb6
002ff8:  ec7a  call    function_070, 0x0                    ; dest: 0x0042f4
002ffa:  f021
002ffc:  d008  bra     label_359                            ; dest: 0x00300e

label_357:                                                  ; address: 0x002ffe

002ffe:  506c  movf    USTAT, W, A                          ; reg: 0xf6c
003000:  0a04  xorlw   0x04
003002:  e104  bnz     label_358
003004:  9668  bcf     UIR, TRNIF, A                        ; reg: 0xf68, bit: 3
003006:  ec09  call    function_077, 0x0                    ; dest: 0x004412
003008:  f022
00300a:  d001  bra     label_359                            ; dest: 0x00300e

label_358:                                                  ; address: 0x00300c

00300c:  9668  bcf     UIR, TRNIF, A                        ; reg: 0xf68, bit: 3

label_359:                                                  ; address: 0x00300e

00300e:  0100  movlb   0x0
003010:  2bc4  incf    0xc4, F, B                           ; reg: 0x0c4
003012:  0e03  movlw   0x03
003014:  65c4  cpfsgt  0xc4, B                              ; reg: 0x0c4
003016:  d7b0  bra     label_353                            ; dest: 0x002f78

label_360:                                                  ; address: 0x003018

003018:  0012  return  0x0

function_027:                                               ; address: 0x00301a

00301a:  c025  movff   (Common_RAM + 37), (Common_RAM + 41) ; reg1: 0x025, reg2: 0x029
00301c:  f029
00301e:  c026  movff   (Common_RAM + 38), (Common_RAM + 42) ; reg1: 0x026, reg2: 0x02a
003020:  f02a
003022:  c027  movff   (Common_RAM + 39), (Common_RAM + 43) ; reg1: 0x027, reg2: 0x02b
003024:  f02b
003026:  c028  movff   (Common_RAM + 40), (Common_RAM + 44) ; reg1: 0x028, reg2: 0x02c
003028:  f02c
00302a:  0e18  movlw   0x18
00302c:  d001  bra     label_362                            ; dest: 0x003030

label_361:                                                  ; address: 0x00302e

00302e:  d84e  rcall   function_028                         ; dest: 0x0030cc

label_362:                                                  ; address: 0x003030

003030:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
003032:  d7fd  bra     label_361                            ; dest: 0x00302e
003034:  5029  movf    (Common_RAM + 41), W, A              ; reg: 0x029
003036:  6e2e  movwf   (Common_RAM + 46), A                 ; reg: 0x02e
003038:  662e  tstfsz  (Common_RAM + 46), A                 ; reg: 0x02e
00303a:  d005  bra     label_364                            ; dest: 0x003046

label_363:                                                  ; address: 0x00303c

00303c:  6a25  clrf    (Common_RAM + 37), A                 ; reg: 0x025
00303e:  6a26  clrf    (Common_RAM + 38), A                 ; reg: 0x026
003040:  6a27  clrf    (Common_RAM + 39), A                 ; reg: 0x027
003042:  6a28  clrf    (Common_RAM + 40), A                 ; reg: 0x028
003044:  d042  bra     label_373                            ; dest: 0x0030ca

label_364:                                                  ; address: 0x003046

003046:  c025  movff   (Common_RAM + 37), (Common_RAM + 41) ; reg1: 0x025, reg2: 0x029
003048:  f029
00304a:  c026  movff   (Common_RAM + 38), (Common_RAM + 42) ; reg1: 0x026, reg2: 0x02a
00304c:  f02a
00304e:  c027  movff   (Common_RAM + 39), (Common_RAM + 43) ; reg1: 0x027, reg2: 0x02b
003050:  f02b
003052:  c028  movff   (Common_RAM + 40), (Common_RAM + 44) ; reg1: 0x028, reg2: 0x02c
003054:  f02c
003056:  0e20  movlw   0x20
003058:  d001  bra     label_366                            ; dest: 0x00305c

label_365:                                                  ; address: 0x00305a

00305a:  d838  rcall   function_028                         ; dest: 0x0030cc

label_366:                                                  ; address: 0x00305c

00305c:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
00305e:  d7fd  bra     label_365                            ; dest: 0x00305a
003060:  5029  movf    (Common_RAM + 41), W, A              ; reg: 0x029
003062:  6e2d  movwf   (Common_RAM + 45), A                 ; reg: 0x02d
003064:  8e27  bsf     (Common_RAM + 39), 0x7, A            ; reg: 0x027
003066:  6a28  clrf    (Common_RAM + 40), A                 ; reg: 0x028
003068:  0e96  movlw   0x96
00306a:  5e2e  subwf   (Common_RAM + 46), F, A              ; reg: 0x02e
00306c:  ae2e  btfss   (Common_RAM + 46), 0x7, A            ; reg: 0x02e
00306e:  d00f  bra     label_368                            ; dest: 0x00308e
003070:  502e  movf    (Common_RAM + 46), W, A              ; reg: 0x02e
003072:  0a80  xorlw   0x80
003074:  6e29  movwf   (Common_RAM + 41), A                 ; reg: 0x029
003076:  0ee9  movlw   0xe9
003078:  0a80  xorlw   0x80
00307a:  5c29  subwf   (Common_RAM + 41), W, A              ; reg: 0x029
00307c:  e3df  bnc     label_363

label_367:                                                  ; address: 0x00307e

00307e:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
003080:  3228  rrcf    (Common_RAM + 40), F, A              ; reg: 0x028
003082:  3227  rrcf    (Common_RAM + 39), F, A              ; reg: 0x027
003084:  3226  rrcf    (Common_RAM + 38), F, A              ; reg: 0x026
003086:  3225  rrcf    (Common_RAM + 37), F, A              ; reg: 0x025
003088:  3e2e  incfsz  (Common_RAM + 46), F, A              ; reg: 0x02e
00308a:  d7f9  bra     label_367                            ; dest: 0x00307e
00308c:  d00c  bra     label_371                            ; dest: 0x0030a6

label_368:                                                  ; address: 0x00308e

00308e:  0e1f  movlw   0x1f
003090:  642e  cpfsgt  (Common_RAM + 46), A                 ; reg: 0x02e
003092:  d007  bra     label_370                            ; dest: 0x0030a2
003094:  d7d3  bra     label_363                            ; dest: 0x00303c

label_369:                                                  ; address: 0x003096

003096:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
003098:  3625  rlcf    (Common_RAM + 37), F, A              ; reg: 0x025
00309a:  3626  rlcf    (Common_RAM + 38), F, A              ; reg: 0x026
00309c:  3627  rlcf    (Common_RAM + 39), F, A              ; reg: 0x027
00309e:  3628  rlcf    (Common_RAM + 40), F, A              ; reg: 0x028
0030a0:  062e  decf    (Common_RAM + 46), F, A              ; reg: 0x02e

label_370:                                                  ; address: 0x0030a2

0030a2:  662e  tstfsz  (Common_RAM + 46), A                 ; reg: 0x02e
0030a4:  d7f8  bra     label_369                            ; dest: 0x003096

label_371:                                                  ; address: 0x0030a6

0030a6:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
0030a8:  e008  bz      label_372
0030aa:  1e28  comf    (Common_RAM + 40), F, A              ; reg: 0x028
0030ac:  1e27  comf    (Common_RAM + 39), F, A              ; reg: 0x027
0030ae:  1e26  comf    (Common_RAM + 38), F, A              ; reg: 0x026
0030b0:  6c25  negf    (Common_RAM + 37), A                 ; reg: 0x025
0030b2:  0e00  movlw   0x00
0030b4:  2226  addwfc  (Common_RAM + 38), F, A              ; reg: 0x026
0030b6:  2227  addwfc  (Common_RAM + 39), F, A              ; reg: 0x027
0030b8:  2228  addwfc  (Common_RAM + 40), F, A              ; reg: 0x028

label_372:                                                  ; address: 0x0030ba

0030ba:  c025  movff   (Common_RAM + 37), (Common_RAM + 37) ; reg1: 0x025, reg2: 0x025
0030bc:  f025
0030be:  c026  movff   (Common_RAM + 38), (Common_RAM + 38) ; reg1: 0x026, reg2: 0x026
0030c0:  f026
0030c2:  c027  movff   (Common_RAM + 39), (Common_RAM + 39) ; reg1: 0x027, reg2: 0x027
0030c4:  f027
0030c6:  c028  movff   (Common_RAM + 40), (Common_RAM + 40) ; reg1: 0x028, reg2: 0x028
0030c8:  f028

label_373:                                                  ; address: 0x0030ca

0030ca:  0012  return  0x0

function_028:                                               ; address: 0x0030cc

0030cc:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
0030ce:  322c  rrcf    (Common_RAM + 44), F, A              ; reg: 0x02c
0030d0:  322b  rrcf    (Common_RAM + 43), F, A              ; reg: 0x02b
0030d2:  322a  rrcf    (Common_RAM + 42), F, A              ; reg: 0x02a
0030d4:  3229  rrcf    (Common_RAM + 41), F, A              ; reg: 0x029
0030d6:  0012  return  0x0

function_029:                                               ; address: 0x0030d8

0030d8:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
0030da:  e005  bz      label_374
0030dc:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
0030de:  1003  iorwf   (Common_RAM + 3), W, A               ; reg: 0x003
0030e0:  1004  iorwf   (Common_RAM + 4), W, A               ; reg: 0x004
0030e2:  1005  iorwf   (Common_RAM + 5), W, A               ; reg: 0x005
0030e4:  e107  bnz     label_376

label_374:                                                  ; address: 0x0030e6

0030e6:  6a03  clrf    (Common_RAM + 3), A                  ; reg: 0x003
0030e8:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
0030ea:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
0030ec:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
0030ee:  d04b  bra     label_382                            ; dest: 0x003186

label_375:                                                  ; address: 0x0030f0

0030f0:  2a07  incf    (Common_RAM + 7), F, A               ; reg: 0x007
0030f2:  d84a  rcall   function_030                         ; dest: 0x003188

label_376:                                                  ; address: 0x0030f4

0030f4:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009
0030f6:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
0030f8:  6a0b  clrf    (Common_RAM + 11), A                 ; reg: 0x00b
0030fa:  0efe  movlw   0xfe
0030fc:  1406  andwf   (Common_RAM + 6), W, A               ; reg: 0x006
0030fe:  6e0c  movwf   (Common_RAM + 12), A                 ; reg: 0x00c
003100:  500c  movf    (Common_RAM + 12), W, A              ; reg: 0x00c
003102:  1009  iorwf   (Common_RAM + 9), W, A               ; reg: 0x009
003104:  100a  iorwf   (Common_RAM + 10), W, A              ; reg: 0x00a
003106:  100b  iorwf   (Common_RAM + 11), W, A              ; reg: 0x00b
003108:  e008  bz      label_378
00310a:  d7f2  bra     label_375                            ; dest: 0x0030f0

label_377:                                                  ; address: 0x00310c

00310c:  2a07  incf    (Common_RAM + 7), F, A               ; reg: 0x007
00310e:  2a03  incf    (Common_RAM + 3), F, A               ; reg: 0x003
003110:  0e00  movlw   0x00
003112:  2204  addwfc  (Common_RAM + 4), F, A               ; reg: 0x004
003114:  2205  addwfc  (Common_RAM + 5), F, A               ; reg: 0x005
003116:  2206  addwfc  (Common_RAM + 6), F, A               ; reg: 0x006
003118:  d837  rcall   function_030                         ; dest: 0x003188

label_378:                                                  ; address: 0x00311a

00311a:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009
00311c:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
00311e:  6a0b  clrf    (Common_RAM + 11), A                 ; reg: 0x00b
003120:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
003122:  6e0c  movwf   (Common_RAM + 12), A                 ; reg: 0x00c
003124:  500c  movf    (Common_RAM + 12), W, A              ; reg: 0x00c
003126:  1009  iorwf   (Common_RAM + 9), W, A               ; reg: 0x009
003128:  100a  iorwf   (Common_RAM + 10), W, A              ; reg: 0x00a
00312a:  100b  iorwf   (Common_RAM + 11), W, A              ; reg: 0x00b
00312c:  e007  bz      label_380
00312e:  d7ee  bra     label_377                            ; dest: 0x00310c

label_379:                                                  ; address: 0x003130

003130:  0607  decf    (Common_RAM + 7), F, A               ; reg: 0x007
003132:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
003134:  3603  rlcf    (Common_RAM + 3), F, A               ; reg: 0x003
003136:  3604  rlcf    (Common_RAM + 4), F, A               ; reg: 0x004
003138:  3605  rlcf    (Common_RAM + 5), F, A               ; reg: 0x005
00313a:  3606  rlcf    (Common_RAM + 6), F, A               ; reg: 0x006

label_380:                                                  ; address: 0x00313c

00313c:  ae05  btfss   (Common_RAM + 5), 0x7, A             ; reg: 0x005
00313e:  d7f8  bra     label_379                            ; dest: 0x003130
003140:  b007  btfsc   (Common_RAM + 7), 0x0, A             ; reg: 0x007
003142:  d002  bra     label_381                            ; dest: 0x003148
003144:  0e7f  movlw   0x7f
003146:  1605  andwf   (Common_RAM + 5), F, A               ; reg: 0x005

label_381:                                                  ; address: 0x003148

003148:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
00314a:  3207  rrcf    (Common_RAM + 7), F, A               ; reg: 0x007
00314c:  c007  movff   (Common_RAM + 7), (Common_RAM + 9)   ; reg1: 0x007, reg2: 0x009
00314e:  f009
003150:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
003152:  6a0b  clrf    (Common_RAM + 11), A                 ; reg: 0x00b
003154:  6a0c  clrf    (Common_RAM + 12), A                 ; reg: 0x00c
003156:  c009  movff   (Common_RAM + 9), (Common_RAM + 12)  ; reg1: 0x009, reg2: 0x00c
003158:  f00c
00315a:  6a0b  clrf    (Common_RAM + 11), A                 ; reg: 0x00b
00315c:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
00315e:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009
003160:  5009  movf    (Common_RAM + 9), W, A               ; reg: 0x009
003162:  1203  iorwf   (Common_RAM + 3), F, A               ; reg: 0x003
003164:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
003166:  1204  iorwf   (Common_RAM + 4), F, A               ; reg: 0x004
003168:  500b  movf    (Common_RAM + 11), W, A              ; reg: 0x00b
00316a:  1205  iorwf   (Common_RAM + 5), F, A               ; reg: 0x005
00316c:  500c  movf    (Common_RAM + 12), W, A              ; reg: 0x00c
00316e:  1206  iorwf   (Common_RAM + 6), F, A               ; reg: 0x006
003170:  5008  movf    (Common_RAM + 8), W, A               ; reg: 0x008
003172:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
003174:  8e06  bsf     (Common_RAM + 6), 0x7, A             ; reg: 0x006
003176:  c003  movff   (Common_RAM + 3), (Common_RAM + 3)   ; reg1: 0x003, reg2: 0x003
003178:  f003
00317a:  c004  movff   (Common_RAM + 4), (Common_RAM + 4)   ; reg1: 0x004, reg2: 0x004
00317c:  f004
00317e:  c005  movff   (Common_RAM + 5), (Common_RAM + 5)   ; reg1: 0x005, reg2: 0x005
003180:  f005
003182:  c006  movff   (Common_RAM + 6), (Common_RAM + 6)   ; reg1: 0x006, reg2: 0x006
003184:  f006

label_382:                                                  ; address: 0x003186

003186:  0012  return  0x0

function_030:                                               ; address: 0x003188

003188:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
00318a:  3206  rrcf    (Common_RAM + 6), F, A               ; reg: 0x006
00318c:  3205  rrcf    (Common_RAM + 5), F, A               ; reg: 0x005
00318e:  3204  rrcf    (Common_RAM + 4), F, A               ; reg: 0x004
003190:  3203  rrcf    (Common_RAM + 3), F, A               ; reg: 0x003
003192:  0012  return  0x0

label_383:                                                  ; address: 0x003194

003194:  51cf  movf    0xcf, W, B                           ; reg: 0x0cf
003196:  0b1f  andlw   0x1f
003198:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
00319a:  0403  decf    (Common_RAM + 3), W, A               ; reg: 0x003
00319c:  e156  bnz     label_399
00319e:  51d3  movf    0xd3, W, B                           ; reg: 0x0d3
0031a0:  e154  bnz     label_399
0031a2:  51d0  movf    0xd0, W, B                           ; reg: 0x0d0
0031a4:  0a06  xorlw   0x06
0031a6:  e018  bz      label_388
0031a8:  d01e  bra     label_390                            ; dest: 0x0031e6

label_384:                                                  ; address: 0x0031aa

0031aa:  0e02  movlw   0x02
0031ac:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0031ae:  0e10  movlw   0x10
0031b0:  6f76  movwf   0x76, B                              ; reg: 0x076
0031b2:  0e3e  movlw   0x3e
0031b4:  6f75  movwf   0x75, B                              ; reg: 0x075
0031b6:  6be8  clrf    0xe8, B                              ; reg: 0x0e8
0031b8:  0e09  movlw   0x09
0031ba:  d00c  bra     label_387                            ; dest: 0x0031d4

label_385:                                                  ; address: 0x0031bc

0031bc:  0e02  movlw   0x02
0031be:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0031c0:  05eb  decf    0xeb, W, B                           ; reg: 0x0eb
0031c2:  e104  bnz     label_386
0031c4:  0e10  movlw   0x10
0031c6:  6f76  movwf   0x76, B                              ; reg: 0x076
0031c8:  0e55  movlw   0x55
0031ca:  6f75  movwf   0x75, B                              ; reg: 0x075

label_386:                                                  ; address: 0x0031cc

0031cc:  05eb  decf    0xeb, W, B                           ; reg: 0x0eb
0031ce:  e10a  bnz     label_389
0031d0:  6be8  clrf    0xe8, B                              ; reg: 0x0e8
0031d2:  0e1d  movlw   0x1d

label_387:                                                  ; address: 0x0031d4

0031d4:  6fe7  movwf   0xe7, B                              ; reg: 0x0e7
0031d6:  d006  bra     label_389                            ; dest: 0x0031e4

label_388:                                                  ; address: 0x0031d8

0031d8:  51d2  movf    0xd2, W, B                           ; reg: 0x0d2
0031da:  0a21  xorlw   0x21
0031dc:  e0e6  bz      label_384
0031de:  0a03  xorlw   0x03
0031e0:  e0ed  bz      label_385
0031e2:  0a01  xorlw   0x01

label_389:                                                  ; address: 0x0031e4

0031e4:  83ce  bsf     0xce, 0x1, B                         ; reg: 0x0ce

label_390:                                                  ; address: 0x0031e6

0031e6:  39cf  swapf   0xcf, W, B                           ; reg: 0x0cf
0031e8:  32e8  rrcf    WREG, F, A                           ; reg: 0xfe8
0031ea:  0b03  andlw   0x03
0031ec:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
0031ee:  0403  decf    (Common_RAM + 3), W, A               ; reg: 0x003
0031f0:  e12c  bnz     label_399
0031f2:  d01e  bra     label_398                            ; dest: 0x003230

label_391:                                                  ; address: 0x0031f4

0031f4:  ecb7  call    function_131, 0x0                    ; dest: 0x00496e
0031f6:  f024
0031f8:  d028  bra     label_399                            ; dest: 0x00324a

label_392:                                                  ; address: 0x0031fa

0031fa:  ecb6  call    function_130, 0x0                    ; dest: 0x00496c
0031fc:  f024
0031fe:  d025  bra     label_399                            ; dest: 0x00324a

label_393:                                                  ; address: 0x003200

003200:  0e02  movlw   0x02
003202:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003204:  6b76  clrf    0x76, B                              ; reg: 0x076
003206:  0eea  movlw   0xea

label_394:                                                  ; address: 0x003208

003208:  6f75  movwf   0x75, B                              ; reg: 0x075
00320a:  93ce  bcf     0xce, 0x1, B                         ; reg: 0x0ce
00320c:  0e01  movlw   0x01
00320e:  6fe7  movwf   0xe7, B                              ; reg: 0x0e7
003210:  d01c  bra     label_399                            ; dest: 0x00324a

label_395:                                                  ; address: 0x003212

003212:  0e02  movlw   0x02
003214:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003216:  c0d2  movff   0x0d2, 0x0ea
003218:  f0ea
00321a:  d017  bra     label_399                            ; dest: 0x00324a

label_396:                                                  ; address: 0x00321c

00321c:  0e02  movlw   0x02
00321e:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003220:  6b76  clrf    0x76, B                              ; reg: 0x076
003222:  0ee9  movlw   0xe9
003224:  d7f1  bra     label_394                            ; dest: 0x003208

label_397:                                                  ; address: 0x003226

003226:  0e02  movlw   0x02
003228:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
00322a:  c0d1  movff   0x0d1, 0x0e9
00322c:  f0e9
00322e:  d00d  bra     label_399                            ; dest: 0x00324a

label_398:                                                  ; address: 0x003230

003230:  51d0  movf    0xd0, W, B                           ; reg: 0x0d0
003232:  0a01  xorlw   0x01
003234:  e0df  bz      label_391
003236:  0a03  xorlw   0x03
003238:  e0e3  bz      label_393
00323a:  0a01  xorlw   0x01
00323c:  e0ef  bz      label_396
00323e:  0a0a  xorlw   0x0a
003240:  e0dc  bz      label_392
003242:  0a03  xorlw   0x03
003244:  e0e6  bz      label_395
003246:  0a01  xorlw   0x01
003248:  e0ee  bz      label_397

label_399:                                                  ; address: 0x00324a

00324a:  0012  return  0x0

label_400:                                                  ; address: 0x00324c

00324c:  67c8  tstfsz  0xc8, B                              ; reg: 0x0c8
00324e:  d014  bra     label_402                            ; dest: 0x003278
003250:  0e04  movlw   0x04
003252:  0104  movlb   0x4
003254:  6f08  movwf   0x08, B                              ; reg: 0x408
003256:  8f08  bsf     0x08, 0x7, B                         ; reg: 0x408
003258:  0101  movlb   0x1
00325a:  6f16  movwf   0x16, B                              ; reg: 0x116
00325c:  0100  movlb   0x0
00325e:  0596  decf    0x96, W, B                           ; reg: 0x096
003260:  e105  bnz     label_401
003262:  0e01  movlw   0x01
003264:  ec40  call    function_062, 0x0                    ; dest: 0x004080
003266:  f020
003268:  6b96  clrf    0x96, B                              ; reg: 0x096
00326a:  d045  bra     label_409                            ; dest: 0x0032f6

label_401:                                                  ; address: 0x00326c

00326c:  0e00  movlw   0x00
00326e:  ec40  call    function_062, 0x0                    ; dest: 0x004080
003270:  f020
003272:  0e01  movlw   0x01
003274:  6f96  movwf   0x96, B                              ; reg: 0x096
003276:  d03f  bra     label_409                            ; dest: 0x0032f6

label_402:                                                  ; address: 0x003278

003278:  afcf  btfss   0xcf, 0x7, B                         ; reg: 0x0cf
00327a:  d01c  bra     label_404                            ; dest: 0x0032b4
00327c:  0e01  movlw   0x01
00327e:  6fc9  movwf   0xc9, B                              ; reg: 0x0c9
003280:  51e7  movf    0xe7, W, B                           ; reg: 0x0e7
003282:  5dd5  subwf   0xd5, W, B                           ; reg: 0x0d5
003284:  51e8  movf    0xe8, W, B                           ; reg: 0x0e8
003286:  59d6  subwfb  0xd6, W, B                           ; reg: 0x0d6
003288:  e204  bc      label_403
00328a:  c0d5  movff   0x0d5, 0x0e7
00328c:  f0e7
00328e:  c0d6  movff   0x0d6, 0x0e8
003290:  f0e8

label_403:                                                  ; address: 0x003292

003292:  ecf8  call    function_036, 0x0                    ; dest: 0x0035f0
003294:  f01a
003296:  0e48  movlw   0x48
003298:  0101  movlb   0x1
00329a:  6f16  movwf   0x16, B                              ; reg: 0x116
00329c:  0e01  movlw   0x01
00329e:  ec40  call    function_062, 0x0                    ; dest: 0x004080
0032a0:  f020
0032a2:  0e00  movlw   0x00
0032a4:  ec40  call    function_062, 0x0                    ; dest: 0x004080
0032a6:  f020
0032a8:  0104  movlb   0x4
0032aa:  0e04  movlw   0x04
0032ac:  6f0b  movwf   0x0b, B                              ; reg: 0x40b
0032ae:  0e24  movlw   0x24
0032b0:  6f0a  movwf   0x0a, B                              ; reg: 0x40a
0032b2:  d01e  bra     label_408                            ; dest: 0x0032f0

label_404:                                                  ; address: 0x0032b4

0032b4:  0e02  movlw   0x02
0032b6:  6fc9  movwf   0xc9, B                              ; reg: 0x0c9
0032b8:  0e04  movlw   0x04
0032ba:  0101  movlb   0x1
0032bc:  6f16  movwf   0x16, B                              ; reg: 0x116
0032be:  0100  movlb   0x0
0032c0:  51d6  movf    0xd6, W, B                           ; reg: 0x0d6
0032c2:  11d5  iorwf   0xd5, W, B                           ; reg: 0x0d5
0032c4:  e103  bnz     label_405
0032c6:  0e48  movlw   0x48
0032c8:  0101  movlb   0x1
0032ca:  6f16  movwf   0x16, B                              ; reg: 0x116

label_405:                                                  ; address: 0x0032cc

0032cc:  0100  movlb   0x0
0032ce:  0596  decf    0x96, W, B                           ; reg: 0x096
0032d0:  e105  bnz     label_406
0032d2:  0e01  movlw   0x01
0032d4:  ec40  call    function_062, 0x0                    ; dest: 0x004080
0032d6:  f020
0032d8:  6b96  clrf    0x96, B                              ; reg: 0x096
0032da:  d005  bra     label_407                            ; dest: 0x0032e6

label_406:                                                  ; address: 0x0032dc

0032dc:  0e00  movlw   0x00
0032de:  ec40  call    function_062, 0x0                    ; dest: 0x004080
0032e0:  f020
0032e2:  0e01  movlw   0x01
0032e4:  6f96  movwf   0x96, B                              ; reg: 0x096

label_407:                                                  ; address: 0x0032e6

0032e6:  51d6  movf    0xd6, W, B                           ; reg: 0x0d6
0032e8:  11d5  iorwf   0xd5, W, B                           ; reg: 0x0d5
0032ea:  e105  bnz     label_409
0032ec:  0104  movlb   0x4
0032ee:  6b09  clrf    0x09, B                              ; reg: 0x409

label_408:                                                  ; address: 0x0032f0

0032f0:  0e48  movlw   0x48
0032f2:  6f08  movwf   (Common_RAM + 8), B                  ; reg: 0x008
0032f4:  8f08  bsf     (Common_RAM + 8), 0x7, B             ; reg: 0x008

label_409:                                                  ; address: 0x0032f6

0032f6:  0012  return  0x0

function_031:                                               ; address: 0x0032f8

0032f8:  ec5b  call    function_113, 0x0                    ; dest: 0x0048b6
0032fa:  f024
0032fc:  0e3f  movlw   0x3f
0032fe:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003300:  0e01  movlw   0x01
003302:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003304:  f023
003306:  0e30  movlw   0x30
003308:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00330a:  0e03  movlw   0x03
00330c:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00330e:  f023
003310:  0e01  movlw   0x01
003312:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003314:  0e04  movlw   0x04
003316:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003318:  f023
00331a:  0e08  movlw   0x08
00331c:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00331e:  0e05  movlw   0x05
003320:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003322:  f023
003324:  0e01  movlw   0x01
003326:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003328:  0e06  movlw   0x06
00332a:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00332c:  f023
00332e:  0e34  movlw   0x34
003330:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003332:  0e07  movlw   0x07
003334:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003336:  f023
003338:  0e30  movlw   0x30
00333a:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00333c:  0e08  movlw   0x08
00333e:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003340:  f023
003342:  0e08  movlw   0x08
003344:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003346:  0e0d  movlw   0x0d
003348:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00334a:  f023
00334c:  0e08  movlw   0x08
00334e:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003350:  0e0e  movlw   0x0e
003352:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003354:  f023
003356:  0e22  movlw   0x22
003358:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00335a:  0e0f  movlw   0x0f
00335c:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00335e:  f023
003360:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
003362:  0e10  movlw   0x10
003364:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003366:  f023
003368:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
00336a:  0e11  movlw   0x11
00336c:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00336e:  f023
003370:  0e01  movlw   0x01
003372:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003374:  0e1c  movlw   0x1c
003376:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003378:  f023
00337a:  0e01  movlw   0x01
00337c:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
00337e:  0e1d  movlw   0x1d
003380:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003382:  f023
003384:  0e02  movlw   0x02
003386:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003388:  0e2d  movlw   0x2d
00338a:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
00338c:  f023
00338e:  0e20  movlw   0x20
003390:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003392:  0e2e  movlw   0x2e
003394:  ef5d  goto    function_093                         ; dest: 0x0046ba
003396:  f023

function_032:                                               ; address: 0x003398

003398:  c02f  movff   (Common_RAM + 47), (Common_RAM + 3)  ; reg1: 0x02f, reg2: 0x003
00339a:  f003
00339c:  c030  movff   (Common_RAM + 48), (Common_RAM + 4)  ; reg1: 0x030, reg2: 0x004
00339e:  f004
0033a0:  c031  movff   (Common_RAM + 49), (Common_RAM + 5)  ; reg1: 0x031, reg2: 0x005
0033a2:  f005
0033a4:  c032  movff   (Common_RAM + 50), (Common_RAM + 6)  ; reg1: 0x032, reg2: 0x006
0033a6:  f006
0033a8:  0e37  movlw   0x37
0033aa:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0033ac:  ec74  call    function_053, 0x0                    ; dest: 0x003ce8
0033ae:  f01e
0033b0:  5038  movf    (Common_RAM + 56), W, A              ; reg: 0x038
0033b2:  0a80  xorlw   0x80
0033b4:  6ef3  movwf   PRODL, A                             ; reg: 0xff3
0033b6:  0e80  movlw   0x80
0033b8:  5cf3  subwf   PRODL, W, A                          ; reg: 0xff3
0033ba:  0e00  movlw   0x00
0033bc:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0033be:  5c37  subwf   (Common_RAM + 55), W, A              ; reg: 0x037
0033c0:  e205  bc      label_410
0033c2:  6a2f  clrf    (Common_RAM + 47), A                 ; reg: 0x02f
0033c4:  6a30  clrf    (Common_RAM + 48), A                 ; reg: 0x030
0033c6:  6a31  clrf    (Common_RAM + 49), A                 ; reg: 0x031
0033c8:  6a32  clrf    (Common_RAM + 50), A                 ; reg: 0x032
0033ca:  d032  bra     label_412                            ; dest: 0x003430

label_410:                                                  ; address: 0x0033cc

0033cc:  0e1d  movlw   0x1d
0033ce:  5c37  subwf   (Common_RAM + 55), W, A              ; reg: 0x037
0033d0:  0e00  movlw   0x00
0033d2:  5838  subwfb  (Common_RAM + 56), W, A              ; reg: 0x038
0033d4:  e309  bnc     label_411
0033d6:  c02f  movff   (Common_RAM + 47), (Common_RAM + 47) ; reg1: 0x02f, reg2: 0x02f
0033d8:  f02f
0033da:  c030  movff   (Common_RAM + 48), (Common_RAM + 48) ; reg1: 0x030, reg2: 0x030
0033dc:  f030
0033de:  c031  movff   (Common_RAM + 49), (Common_RAM + 49) ; reg1: 0x031, reg2: 0x031
0033e0:  f031
0033e2:  c032  movff   (Common_RAM + 50), (Common_RAM + 50) ; reg1: 0x032, reg2: 0x032
0033e4:  f032
0033e6:  d024  bra     label_412                            ; dest: 0x003430

label_411:                                                  ; address: 0x0033e8

0033e8:  c02f  movff   (Common_RAM + 47), (Common_RAM + 37) ; reg1: 0x02f, reg2: 0x025
0033ea:  f025
0033ec:  c030  movff   (Common_RAM + 48), (Common_RAM + 38) ; reg1: 0x030, reg2: 0x026
0033ee:  f026
0033f0:  c031  movff   (Common_RAM + 49), (Common_RAM + 39) ; reg1: 0x031, reg2: 0x027
0033f2:  f027
0033f4:  c032  movff   (Common_RAM + 50), (Common_RAM + 40) ; reg1: 0x032, reg2: 0x028
0033f6:  f028
0033f8:  ec0d  call    function_027, 0x0                    ; dest: 0x00301a
0033fa:  f018
0033fc:  c025  movff   (Common_RAM + 37), (Common_RAM + 13) ; reg1: 0x025, reg2: 0x00d
0033fe:  f00d
003400:  c026  movff   (Common_RAM + 38), (Common_RAM + 14) ; reg1: 0x026, reg2: 0x00e
003402:  f00e
003404:  c027  movff   (Common_RAM + 39), (Common_RAM + 15) ; reg1: 0x027, reg2: 0x00f
003406:  f00f
003408:  c028  movff   (Common_RAM + 40), (Common_RAM + 16) ; reg1: 0x028, reg2: 0x010
00340a:  f010
00340c:  ec05  call    function_055, 0x0                    ; dest: 0x003e0a
00340e:  f01f
003410:  c00d  movff   (Common_RAM + 13), (Common_RAM + 51) ; reg1: 0x00d, reg2: 0x033
003412:  f033
003414:  c00e  movff   (Common_RAM + 14), (Common_RAM + 52) ; reg1: 0x00e, reg2: 0x034
003416:  f034
003418:  c00f  movff   (Common_RAM + 15), (Common_RAM + 53) ; reg1: 0x00f, reg2: 0x035
00341a:  f035
00341c:  c010  movff   (Common_RAM + 16), (Common_RAM + 54) ; reg1: 0x010, reg2: 0x036
00341e:  f036
003420:  c033  movff   (Common_RAM + 51), (Common_RAM + 47) ; reg1: 0x033, reg2: 0x02f
003422:  f02f
003424:  c034  movff   (Common_RAM + 52), (Common_RAM + 48) ; reg1: 0x034, reg2: 0x030
003426:  f030
003428:  c035  movff   (Common_RAM + 53), (Common_RAM + 49) ; reg1: 0x035, reg2: 0x031
00342a:  f031
00342c:  c036  movff   (Common_RAM + 54), (Common_RAM + 50) ; reg1: 0x036, reg2: 0x032
00342e:  f032

label_412:                                                  ; address: 0x003430

003430:  0012  return  0x0

function_033:                                               ; address: 0x003432

003432:  05d1  decf    0xd1, W, B                           ; reg: 0x0d1
003434:  e10b  bnz     label_414
003436:  51cf  movf    0xcf, W, B                           ; reg: 0x0cf
003438:  0b1f  andlw   0x1f
00343a:  e108  bnz     label_414
00343c:  0e01  movlw   0x01
00343e:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003440:  51d0  movf    0xd0, W, B                           ; reg: 0x0d0
003442:  0a03  xorlw   0x03
003444:  e102  bnz     label_413
003446:  81ce  bsf     0xce, 0x0, B                         ; reg: 0x0ce
003448:  d001  bra     label_414                            ; dest: 0x00344c

label_413:                                                  ; address: 0x00344a

00344a:  91ce  bcf     0xce, 0x0, B                         ; reg: 0x0ce

label_414:                                                  ; address: 0x00344c

00344c:  67d1  tstfsz  0xd1, B                              ; reg: 0x0d1
00344e:  d03b  bra     label_418                            ; dest: 0x0034c6
003450:  51cf  movf    0xcf, W, B                           ; reg: 0x0cf
003452:  0b1f  andlw   0x1f
003454:  0a02  xorlw   0x02
003456:  e137  bnz     label_418
003458:  51d3  movf    0xd3, W, B                           ; reg: 0x0d3
00345a:  0b0f  andlw   0x0f
00345c:  e034  bz      label_418
00345e:  0e01  movlw   0x01
003460:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003462:  51d3  movf    0xd3, W, B                           ; reg: 0x0d3
003464:  0b0f  andlw   0x0f
003466:  0d08  mullw   0x08
003468:  0e04  movlw   0x04
00346a:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
00346c:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
00346e:  50f3  movf    PRODL, W, A                          ; reg: 0xff3
003470:  2603  addwf   (Common_RAM + 3), F, A               ; reg: 0x003
003472:  50f4  movf    PRODH, W, A                          ; reg: 0xff4
003474:  2204  addwfc  (Common_RAM + 4), F, A               ; reg: 0x004
003476:  0e01  movlw   0x01
003478:  afd3  btfss   0xd3, 0x7, B                         ; reg: 0x0d3
00347a:  0e00  movlw   0x00
00347c:  0d04  mullw   0x04
00347e:  50f3  movf    PRODL, W, A                          ; reg: 0xff3
003480:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
003482:  6f72  movwf   0x72, B                              ; reg: 0x072
003484:  50f4  movf    PRODH, W, A                          ; reg: 0xff4
003486:  2004  addwfc  (Common_RAM + 4), W, A               ; reg: 0x004
003488:  6f73  movwf   0x73, B                              ; reg: 0x073
00348a:  51d0  movf    0xd0, W, B                           ; reg: 0x0d0
00348c:  0a03  xorlw   0x03
00348e:  e106  bnz     label_415
003490:  c072  movff   0x072, FSR2L                         ; reg2: 0xfd9
003492:  ffd9
003494:  c073  movff   0x073, FSR2H                         ; reg2: 0xfda
003496:  ffda
003498:  0e04  movlw   0x04
00349a:  d00e  bra     label_417                            ; dest: 0x0034b8

label_415:                                                  ; address: 0x00349c

00349c:  afd3  btfss   0xd3, 0x7, B                         ; reg: 0x0d3
00349e:  d007  bra     label_416                            ; dest: 0x0034ae
0034a0:  c072  movff   0x072, FSR2L                         ; reg2: 0xfd9
0034a2:  ffd9
0034a4:  c073  movff   0x073, FSR2H                         ; reg2: 0xfda
0034a6:  ffda
0034a8:  0e40  movlw   0x40
0034aa:  6edf  movwf   INDF2, A                             ; reg: 0xfdf
0034ac:  d00c  bra     label_418                            ; dest: 0x0034c6

label_416:                                                  ; address: 0x0034ae

0034ae:  c072  movff   0x072, FSR2L                         ; reg2: 0xfd9
0034b0:  ffd9
0034b2:  c073  movff   0x073, FSR2H                         ; reg2: 0xfda
0034b4:  ffda
0034b6:  0e08  movlw   0x08

label_417:                                                  ; address: 0x0034b8

0034b8:  6edf  movwf   INDF2, A                             ; reg: 0xfdf
0034ba:  c072  movff   0x072, FSR2L                         ; reg2: 0xfd9
0034bc:  ffd9
0034be:  c073  movff   0x073, FSR2H                         ; reg2: 0xfda
0034c0:  ffda
0034c2:  0e00  movlw   0x00
0034c4:  8edb  bsf     PLUSW2, 0x7, A                       ; reg: 0xfdb

label_418:                                                  ; address: 0x0034c6

0034c6:  0012  return  0x0

function_034:                                               ; address: 0x0034c8

0034c8:  cfe8  movff   WREG, (Common_RAM + 17)              ; reg1: 0xfe8, reg2: 0x011
0034ca:  f011
0034cc:  c00a  movff   (Common_RAM + 10), (Common_RAM + 14) ; reg1: 0x00a, reg2: 0x00e
0034ce:  f00e
0034d0:  c00b  movff   (Common_RAM + 11), (Common_RAM + 15) ; reg1: 0x00b, reg2: 0x00f
0034d2:  f00f

label_419:                                                  ; address: 0x0034d4

0034d4:  c00e  movff   (Common_RAM + 14), (Common_RAM + 3)  ; reg1: 0x00e, reg2: 0x003
0034d6:  f003
0034d8:  c00f  movff   (Common_RAM + 15), (Common_RAM + 4)  ; reg1: 0x00f, reg2: 0x004
0034da:  f004
0034dc:  c00c  movff   (Common_RAM + 12), (Common_RAM + 5)  ; reg1: 0x00c, reg2: 0x005
0034de:  f005
0034e0:  c00d  movff   (Common_RAM + 13), (Common_RAM + 6)  ; reg1: 0x00d, reg2: 0x006
0034e2:  f006
0034e4:  ec92  call    function_064, 0x0                    ; dest: 0x004124
0034e6:  f020
0034e8:  c003  movff   (Common_RAM + 3), (Common_RAM + 14)  ; reg1: 0x003, reg2: 0x00e
0034ea:  f00e
0034ec:  c004  movff   (Common_RAM + 4), (Common_RAM + 15)  ; reg1: 0x004, reg2: 0x00f
0034ee:  f00f
0034f0:  2a11  incf    (Common_RAM + 17), F, A              ; reg: 0x011
0034f2:  500f  movf    (Common_RAM + 15), W, A              ; reg: 0x00f
0034f4:  100e  iorwf   (Common_RAM + 14), W, A              ; reg: 0x00e
0034f6:  e1ee  bnz     label_419
0034f8:  5011  movf    (Common_RAM + 17), W, A              ; reg: 0x011
0034fa:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0034fc:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0034fe:  0e00  movlw   0x00
003500:  6adf  clrf    INDF2, A                             ; reg: 0xfdf
003502:  0611  decf    (Common_RAM + 17), F, A              ; reg: 0x011

label_420:                                                  ; address: 0x003504

003504:  c00a  movff   (Common_RAM + 10), (Common_RAM + 3)  ; reg1: 0x00a, reg2: 0x003
003506:  f003
003508:  c00b  movff   (Common_RAM + 11), (Common_RAM + 4)  ; reg1: 0x00b, reg2: 0x004
00350a:  f004
00350c:  c00c  movff   (Common_RAM + 12), (Common_RAM + 5)  ; reg1: 0x00c, reg2: 0x005
00350e:  f005
003510:  c00d  movff   (Common_RAM + 13), (Common_RAM + 6)  ; reg1: 0x00d, reg2: 0x006
003512:  f006
003514:  ec3d  call    function_068, 0x0                    ; dest: 0x00427a
003516:  f021
003518:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
00351a:  6e10  movwf   (Common_RAM + 16), A                 ; reg: 0x010
00351c:  c00a  movff   (Common_RAM + 10), (Common_RAM + 3)  ; reg1: 0x00a, reg2: 0x003
00351e:  f003
003520:  c00b  movff   (Common_RAM + 11), (Common_RAM + 4)  ; reg1: 0x00b, reg2: 0x004
003522:  f004
003524:  c00c  movff   (Common_RAM + 12), (Common_RAM + 5)  ; reg1: 0x00c, reg2: 0x005
003526:  f005
003528:  c00d  movff   (Common_RAM + 13), (Common_RAM + 6)  ; reg1: 0x00d, reg2: 0x006
00352a:  f006
00352c:  ec92  call    function_064, 0x0                    ; dest: 0x004124
00352e:  f020
003530:  c003  movff   (Common_RAM + 3), (Common_RAM + 10)  ; reg1: 0x003, reg2: 0x00a
003532:  f00a
003534:  c004  movff   (Common_RAM + 4), (Common_RAM + 11)  ; reg1: 0x004, reg2: 0x00b
003536:  f00b
003538:  0e09  movlw   0x09
00353a:  6410  cpfsgt  (Common_RAM + 16), A                 ; reg: 0x010
00353c:  d002  bra     label_421                            ; dest: 0x003542
00353e:  0e07  movlw   0x07
003540:  2610  addwf   (Common_RAM + 16), F, A              ; reg: 0x010

label_421:                                                  ; address: 0x003542

003542:  0e30  movlw   0x30
003544:  2610  addwf   (Common_RAM + 16), F, A              ; reg: 0x010
003546:  5011  movf    (Common_RAM + 17), W, A              ; reg: 0x011
003548:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
00354a:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00354c:  c010  movff   (Common_RAM + 16), INDF2             ; reg1: 0x010, reg2: 0xfdf
00354e:  ffdf
003550:  0611  decf    (Common_RAM + 17), F, A              ; reg: 0x011
003552:  500b  movf    (Common_RAM + 11), W, A              ; reg: 0x00b
003554:  100a  iorwf   (Common_RAM + 10), W, A              ; reg: 0x00a
003556:  e1d6  bnz     label_420
003558:  2a11  incf    (Common_RAM + 17), F, A              ; reg: 0x011
00355a:  0012  return  0x0

function_035:                                               ; address: 0x00355c

00355c:  6af2  clrf    INTCON, A                            ; reg: 0xff2
00355e:  6a9d  clrf    PIE1, A                              ; reg: 0xf9d
003560:  6aa0  clrf    PIE2, A                              ; reg: 0xfa0
003562:  6a9e  clrf    PIR1, A                              ; reg: 0xf9e
003564:  6aa1  clrf    PIR2, A                              ; reg: 0xfa1
003566:  6a80  clrf    PORTA, A                             ; reg: 0xf80
003568:  6a81  clrf    PORTB, A                             ; reg: 0xf81
00356a:  6a82  clrf    PORTC, A                             ; reg: 0xf82
00356c:  0e07  movlw   0x07
00356e:  6e92  movwf   TRISA, A                             ; reg: 0xf92
003570:  6a93  clrf    TRISB, A                             ; reg: 0xf93
003572:  0e87  movlw   0x87
003574:  6e94  movwf   TRISC, A                             ; reg: 0xf94
003576:  0e70  movlw   0x70
003578:  6ed3  movwf   OSCCON, A                            ; reg: 0xfd3
00357a:  0e38  movlw   0x38
00357c:  6ec6  movwf   SSPCON1, A                           ; reg: 0xfc6
00357e:  0e01  movlw   0x01
003580:  6ec2  movwf   ADCON0, A                            ; reg: 0xfc2
003582:  0e0c  movlw   0x0c
003584:  6ec1  movwf   ADCON1, A                            ; reg: 0xfc1
003586:  0eb5  movlw   0xb5
003588:  6ec0  movwf   ADCON2, A                            ; reg: 0xfc0
00358a:  0e07  movlw   0x07
00358c:  6ed5  movwf   T0CON, A                             ; reg: 0xfd5
00358e:  0e80  movlw   0x80
003590:  6ecd  movwf   T1CON, A                             ; reg: 0xfcd
003592:  0e77  movlw   0x77
003594:  6ec8  movwf   SSPADD, A                            ; reg: 0xfc8
003596:  0e01  movlw   0x01
003598:  0100  movlb   0x0
00359a:  6ffe  movwf   0xfe, B                              ; reg: 0x0fe
00359c:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
00359e:  0eff  movlw   0xff
0035a0:  6803  setf    (Common_RAM + 3), A                  ; reg: 0x003
0035a2:  ec42  call    function_110, 0x0                    ; dest: 0x004884
0035a4:  f024
0035a6:  0a77  xorlw   0x77
0035a8:  e009  bz      label_422
0035aa:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
0035ac:  0eff  movlw   0xff
0035ae:  6803  setf    (Common_RAM + 3), A                  ; reg: 0x003
0035b0:  ec42  call    function_110, 0x0                    ; dest: 0x004884
0035b2:  f024
0035b4:  0a88  xorlw   0x88
0035b6:  e002  bz      label_422
0035b8:  0100  movlb   0x0
0035ba:  6bfe  clrf    0xfe, B                              ; reg: 0x0fe

label_422:                                                  ; address: 0x0035bc

0035bc:  0100  movlb   0x0
0035be:  51fe  movf    0xfe, W, B                           ; reg: 0x0fe
0035c0:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0035c2:  ec5c  call    function_069, 0x0                    ; dest: 0x0042b8
0035c4:  f021
0035c6:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0035c8:  6807  setf    (Common_RAM + 7), A                  ; reg: 0x007
0035ca:  0e02  movlw   0x02
0035cc:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
0035ce:  ec6f  call    function_094, 0x0                    ; dest: 0x0046de
0035d0:  f023
0035d2:  8c81  bsf     PORTB, RB6, A                        ; reg: 0xf81, bit: 6
0035d4:  ec93  call    function_045, 0x0                    ; dest: 0x003926
0035d6:  f01c
0035d8:  0e03  movlw   0x03
0035da:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
0035dc:  0ee8  movlw   0xe8
0035de:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
0035e0:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
0035e2:  f022
0035e4:  ec44  call    function_007, 0x0                    ; dest: 0x001e88
0035e6:  f00f
0035e8:  8a9d  bsf     PIE1, RCIE, A                        ; reg: 0xf9d, bit: 5
0035ea:  865e  bsf     (Common_RAM + 94), 0x3, A            ; reg: 0x05e
0035ec:  efc6  goto    function_024                         ; dest: 0x002d8c
0035ee:  f016

function_036:                                               ; address: 0x0035f0

0035f0:  0e08  movlw   0x08
0035f2:  6f8f  movwf   0x8f, B                              ; reg: 0x08f
0035f4:  5de7  subwf   0xe7, W, B                           ; reg: 0x0e7
0035f6:  0e00  movlw   0x00
0035f8:  59e8  subwfb  0xe8, W, B                           ; reg: 0x0e8
0035fa:  e20a  bc      label_425
0035fc:  c0e7  movff   0x0e7, 0x08f
0035fe:  f08f
003600:  67cc  tstfsz  0xcc, B                              ; reg: 0x0cc
003602:  d002  bra     label_423                            ; dest: 0x003608
003604:  0e01  movlw   0x01
003606:  d003  bra     label_424                            ; dest: 0x00360e

label_423:                                                  ; address: 0x003608

003608:  05cc  decf    0xcc, W, B                           ; reg: 0x0cc
00360a:  e102  bnz     label_425
00360c:  0e02  movlw   0x02

label_424:                                                  ; address: 0x00360e

00360e:  6fcc  movwf   0xcc, B                              ; reg: 0x0cc

label_425:                                                  ; address: 0x003610

003610:  c08f  movff   0x08f, 0x409
003612:  f409
003614:  518f  movf    0x8f, W, B                           ; reg: 0x08f
003616:  5fe7  subwf   0xe7, F, B                           ; reg: 0x0e7
003618:  0e00  movlw   0x00
00361a:  5be8  subwfb  0xe8, F, B                           ; reg: 0x0e8
00361c:  0e04  movlw   0x04
00361e:  0100  movlb   0x0
003620:  6f73  movwf   0x73, B                              ; reg: 0x073
003622:  0e24  movlw   0x24
003624:  6f72  movwf   0x72, B                              ; reg: 0x072
003626:  b3ce  btfsc   0xce, 0x1, B                         ; reg: 0x0ce
003628:  d00a  bra     label_429                            ; dest: 0x00363e
00362a:  d015  bra     label_433                            ; dest: 0x003656

label_426:                                                  ; address: 0x00362c

00362c:  d817  rcall   function_037                         ; dest: 0x00365c
00362e:  64f7  cpfsgt  TBLPTRH, A                           ; reg: 0xff7
003630:  d003  bra     label_427                            ; dest: 0x003638
003632:  0008  tblrd*
003634:  50f5  movf    TABLAT, W, A                         ; reg: 0xff5
003636:  d002  bra     label_428                            ; dest: 0x00363c

label_427:                                                  ; address: 0x003638

003638:  ec08  call    function_042, 0x0                    ; dest: 0x003810
00363a:  f01c

label_428:                                                  ; address: 0x00363c

00363c:  d81a  rcall   function_038                         ; dest: 0x003672

label_429:                                                  ; address: 0x00363e

00363e:  678f  tstfsz  0x8f, B                              ; reg: 0x08f
003640:  d7f5  bra     label_426                            ; dest: 0x00362c
003642:  d00b  bra     label_434                            ; dest: 0x00365a

label_430:                                                  ; address: 0x003644

003644:  d80b  rcall   function_037                         ; dest: 0x00365c
003646:  64f7  cpfsgt  TBLPTRH, A                           ; reg: 0xff7
003648:  d003  bra     label_431                            ; dest: 0x003650
00364a:  0008  tblrd*
00364c:  50f5  movf    TABLAT, W, A                         ; reg: 0xff5
00364e:  d002  bra     label_432                            ; dest: 0x003654

label_431:                                                  ; address: 0x003650

003650:  ec08  call    function_042, 0x0                    ; dest: 0x003810
003652:  f01c

label_432:                                                  ; address: 0x003654

003654:  d80e  rcall   function_038                         ; dest: 0x003672

label_433:                                                  ; address: 0x003656

003656:  678f  tstfsz  0x8f, B                              ; reg: 0x08f
003658:  d7f5  bra     label_430                            ; dest: 0x003644

label_434:                                                  ; address: 0x00365a

00365a:  0012  return  0x0

function_037:                                               ; address: 0x00365c

00365c:  c075  movff   0x075, TBLPTRL                       ; reg2: 0xff6
00365e:  fff6
003660:  c076  movff   0x076, TBLPTRH                       ; reg2: 0xff7
003662:  fff7
003664:  6af8  clrf    TBLPTRU, A                           ; reg: 0xff8
003666:  c072  movff   0x072, FSR2L                         ; reg2: 0xfd9
003668:  ffd9
00366a:  c073  movff   0x073, FSR2H                         ; reg2: 0xfda
00366c:  ffda
00366e:  0e07  movlw   0x07
003670:  0012  return  0x0

function_038:                                               ; address: 0x003672

003672:  6edf  movwf   INDF2, A                             ; reg: 0xfdf
003674:  0100  movlb   0x0
003676:  4b72  infsnz  0x72, F, B                           ; reg: 0x072
003678:  2b73  incf    0x73, F, B                           ; reg: 0x073
00367a:  4b75  infsnz  0x75, F, B                           ; reg: 0x075
00367c:  2b76  incf    0x76, F, B                           ; reg: 0x076
00367e:  078f  decf    0x8f, F, B                           ; reg: 0x08f
003680:  0012  return  0x0

function_039:                                               ; address: 0x003682

003682:  39cf  swapf   0xcf, W, B                           ; reg: 0x0cf
003684:  32e8  rrcf    WREG, F, A                           ; reg: 0xfe8
003686:  0b03  andlw   0x03
003688:  e142  bnz     label_445
00368a:  d02c  bra     label_444                            ; dest: 0x0036e4

label_435:                                                  ; address: 0x00368c

00368c:  0e01  movlw   0x01
00368e:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003690:  0e04  movlw   0x04
003692:  6fcd  movwf   0xcd, B                              ; reg: 0x0cd
003694:  d03c  bra     label_445                            ; dest: 0x00370e

label_436:                                                  ; address: 0x003696

003696:  eccb  call    function_041, 0x0                    ; dest: 0x003796
003698:  f01b
00369a:  d039  bra     label_445                            ; dest: 0x00370e

label_437:                                                  ; address: 0x00369c

00369c:  ecff  call    function_066, 0x0                    ; dest: 0x0041fe
00369e:  f020
0036a0:  d036  bra     label_445                            ; dest: 0x00370e

label_438:                                                  ; address: 0x0036a2

0036a2:  0e01  movlw   0x01
0036a4:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0036a6:  6b76  clrf    0x76, B                              ; reg: 0x076
0036a8:  0eeb  movlw   0xeb
0036aa:  6f75  movwf   0x75, B                              ; reg: 0x075

label_439:                                                  ; address: 0x0036ac

0036ac:  93ce  bcf     0xce, 0x1, B                         ; reg: 0x0ce
0036ae:  0e01  movlw   0x01
0036b0:  6fe7  movwf   0xe7, B                              ; reg: 0x0e7
0036b2:  d02d  bra     label_445                            ; dest: 0x00370e

label_440:                                                  ; address: 0x0036b4

0036b4:  ec88  call    function_040, 0x0                    ; dest: 0x003710
0036b6:  f01b
0036b8:  d02a  bra     label_445                            ; dest: 0x00370e

label_441:                                                  ; address: 0x0036ba

0036ba:  ec19  call    function_033, 0x0                    ; dest: 0x003432
0036bc:  f01a
0036be:  d027  bra     label_445                            ; dest: 0x00370e

label_442:                                                  ; address: 0x0036c0

0036c0:  0e01  movlw   0x01
0036c2:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0036c4:  51d3  movf    0xd3, W, B                           ; reg: 0x0d3
0036c6:  0fec  addlw   0xec
0036c8:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
0036ca:  6b76  clrf    0x76, B                              ; reg: 0x076
0036cc:  c005  movff   (Common_RAM + 5), 0x075              ; reg1: 0x005
0036ce:  f075
0036d0:  d7ed  bra     label_439                            ; dest: 0x0036ac

label_443:                                                  ; address: 0x0036d2

0036d2:  0e01  movlw   0x01
0036d4:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0036d6:  51d3  movf    0xd3, W, B                           ; reg: 0x0d3
0036d8:  0fec  addlw   0xec
0036da:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0036dc:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0036de:  c0d1  movff   0x0d1, INDF2                         ; reg2: 0xfdf
0036e0:  ffdf
0036e2:  d015  bra     label_445                            ; dest: 0x00370e

label_444:                                                  ; address: 0x0036e4

0036e4:  51d0  movf    0xd0, W, B                           ; reg: 0x0d0
0036e6:  e0e6  bz      label_440
0036e8:  0a01  xorlw   0x01
0036ea:  e0e7  bz      label_441
0036ec:  0a02  xorlw   0x02
0036ee:  e0e5  bz      label_441
0036f0:  0a06  xorlw   0x06
0036f2:  e0cc  bz      label_435
0036f4:  0a03  xorlw   0x03
0036f6:  e0cf  bz      label_436
0036f8:  0a01  xorlw   0x01
0036fa:  e009  bz      label_445
0036fc:  0a0f  xorlw   0x0f
0036fe:  e0d1  bz      label_438
003700:  0a01  xorlw   0x01
003702:  e0cc  bz      label_437
003704:  0a03  xorlw   0x03
003706:  e0dc  bz      label_442
003708:  0a01  xorlw   0x01
00370a:  e0e3  bz      label_443
00370c:  0a07  xorlw   0x07

label_445:                                                  ; address: 0x00370e

00370e:  0012  return  0x0

function_040:                                               ; address: 0x003710

003710:  0104  movlb   0x4
003712:  6b24  clrf    0x24, B                              ; reg: 0x424
003714:  6b25  clrf    0x25, B                              ; reg: 0x425
003716:  d02c  bra     label_449                            ; dest: 0x003770

label_446:                                                  ; address: 0x003718

003718:  0e01  movlw   0x01
00371a:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
00371c:  a1ce  btfss   0xce, 0x0, B                         ; reg: 0x0ce
00371e:  d030  bra     label_450                            ; dest: 0x003780
003720:  0104  movlb   0x4
003722:  8324  bsf     0x24, 0x1, B                         ; reg: 0x424
003724:  d02d  bra     label_450                            ; dest: 0x003780

label_447:                                                  ; address: 0x003726

003726:  0e01  movlw   0x01
003728:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
00372a:  d02a  bra     label_450                            ; dest: 0x003780

label_448:                                                  ; address: 0x00372c

00372c:  0e01  movlw   0x01
00372e:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
003730:  51d3  movf    0xd3, W, B                           ; reg: 0x0d3
003732:  0b0f  andlw   0x0f
003734:  0d08  mullw   0x08
003736:  0e04  movlw   0x04
003738:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
00373a:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
00373c:  50f3  movf    PRODL, W, A                          ; reg: 0xff3
00373e:  2603  addwf   (Common_RAM + 3), F, A               ; reg: 0x003
003740:  50f4  movf    PRODH, W, A                          ; reg: 0xff4
003742:  2204  addwfc  (Common_RAM + 4), F, A               ; reg: 0x004
003744:  0e01  movlw   0x01
003746:  afd3  btfss   0xd3, 0x7, B                         ; reg: 0x0d3
003748:  0e00  movlw   0x00
00374a:  0d04  mullw   0x04
00374c:  50f3  movf    PRODL, W, A                          ; reg: 0xff3
00374e:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
003750:  6f72  movwf   0x72, B                              ; reg: 0x072
003752:  50f4  movf    PRODH, W, A                          ; reg: 0xff4
003754:  2004  addwfc  (Common_RAM + 4), W, A               ; reg: 0x004
003756:  6f73  movwf   0x73, B                              ; reg: 0x073
003758:  c072  movff   0x072, FSR2L                         ; reg2: 0xfd9
00375a:  ffd9
00375c:  c073  movff   0x073, FSR2H                         ; reg2: 0xfda
00375e:  ffda
003760:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
003762:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
003764:  a403  btfss   (Common_RAM + 3), 0x2, A             ; reg: 0x003
003766:  d00c  bra     label_450                            ; dest: 0x003780
003768:  0e01  movlw   0x01
00376a:  0104  movlb   0x4
00376c:  6f24  movwf   0x24, B                              ; reg: 0x424
00376e:  d008  bra     label_450                            ; dest: 0x003780

label_449:                                                  ; address: 0x003770

003770:  0100  movlb   0x0
003772:  51cf  movf    0xcf, W, B                           ; reg: 0x0cf
003774:  0b1f  andlw   0x1f
003776:  e0d0  bz      label_446
003778:  0a01  xorlw   0x01
00377a:  e0d5  bz      label_447
00377c:  0a03  xorlw   0x03
00377e:  e0d6  bz      label_448

label_450:                                                  ; address: 0x003780

003780:  0100  movlb   0x0
003782:  05c8  decf    0xc8, W, B                           ; reg: 0x0c8
003784:  e107  bnz     label_451
003786:  0e04  movlw   0x04
003788:  6f76  movwf   0x76, B                              ; reg: 0x076
00378a:  0e24  movlw   0x24
00378c:  6f75  movwf   0x75, B                              ; reg: 0x075
00378e:  93ce  bcf     0xce, 0x1, B                         ; reg: 0x0ce
003790:  0e02  movlw   0x02
003792:  6fe7  movwf   0xe7, B                              ; reg: 0x0e7

label_451:                                                  ; address: 0x003794

003794:  0012  return  0x0

function_041:                                               ; address: 0x003796

003796:  51cf  movf    0xcf, W, B                           ; reg: 0x0cf
003798:  0a80  xorlw   0x80
00379a:  e031  bz      label_458
00379c:  d038  bra     label_460                            ; dest: 0x00380e

label_452:                                                  ; address: 0x00379e

00379e:  0e01  movlw   0x01
0037a0:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0037a2:  0e10  movlw   0x10
0037a4:  6f76  movwf   0x76, B                              ; reg: 0x076
0037a6:  0e88  movlw   0x88
0037a8:  6f75  movwf   0x75, B                              ; reg: 0x075
0037aa:  0e12  movlw   0x12
0037ac:  d00b  bra     label_454                            ; dest: 0x0037c4

label_453:                                                  ; address: 0x0037ae

0037ae:  67d1  tstfsz  0xd1, B                              ; reg: 0x0d1
0037b0:  d02d  bra     label_459                            ; dest: 0x00380c
0037b2:  0e01  movlw   0x01
0037b4:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0037b6:  0e10  movlw   0x10
0037b8:  6f76  movwf   0x76, B                              ; reg: 0x076
0037ba:  0e2c  movlw   0x2c
0037bc:  6f75  movwf   0x75, B                              ; reg: 0x075
0037be:  0e00  movlw   0x00
0037c0:  6fe8  movwf   0xe8, B                              ; reg: 0x0e8
0037c2:  0e29  movlw   0x29

label_454:                                                  ; address: 0x0037c4

0037c4:  6fe7  movwf   0xe7, B                              ; reg: 0x0e7
0037c6:  d022  bra     label_459                            ; dest: 0x00380c

label_455:                                                  ; address: 0x0037c8

0037c8:  0e01  movlw   0x01
0037ca:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
0037cc:  51d1  movf    0xd1, W, B                           ; reg: 0x0d1
0037ce:  0f29  addlw   0x29
0037d0:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
0037d2:  0e10  movlw   0x10
0037d4:  6ef7  movwf   TBLPTRH, A                           ; reg: 0xff7
0037d6:  0009  tblrd*+
0037d8:  cff5  movff   TABLAT, 0x075                        ; reg1: 0xff5
0037da:  f075
0037dc:  6f76  movwf   0x76, B                              ; reg: 0x076
0037de:  c075  movff   0x075, TBLPTRL                       ; reg2: 0xff6
0037e0:  fff6
0037e2:  c076  movff   0x076, TBLPTRH                       ; reg2: 0xff7
0037e4:  fff7
0037e6:  6af8  clrf    TBLPTRU, A                           ; reg: 0xff8
0037e8:  0e07  movlw   0x07
0037ea:  64f7  cpfsgt  TBLPTRH, A                           ; reg: 0xff7
0037ec:  d003  bra     label_456                            ; dest: 0x0037f4
0037ee:  0008  tblrd*
0037f0:  50f5  movf    TABLAT, W, A                         ; reg: 0xff5
0037f2:  d001  bra     label_457                            ; dest: 0x0037f6

label_456:                                                  ; address: 0x0037f4

0037f4:  d80d  rcall   function_042                         ; dest: 0x003810

label_457:                                                  ; address: 0x0037f6

0037f6:  0100  movlb   0x0
0037f8:  6fe7  movwf   0xe7, B                              ; reg: 0x0e7
0037fa:  6be8  clrf    0xe8, B                              ; reg: 0x0e8
0037fc:  d007  bra     label_459                            ; dest: 0x00380c

label_458:                                                  ; address: 0x0037fe

0037fe:  51d2  movf    0xd2, W, B                           ; reg: 0x0d2
003800:  0a01  xorlw   0x01
003802:  e0cd  bz      label_452
003804:  0a03  xorlw   0x03
003806:  e0d3  bz      label_453
003808:  0a01  xorlw   0x01
00380a:  e0de  bz      label_455

label_459:                                                  ; address: 0x00380c

00380c:  83ce  bsf     0xce, 0x1, B                         ; reg: 0x0ce

label_460:                                                  ; address: 0x00380e

00380e:  0012  return  0x0

function_042:                                               ; address: 0x003810

003810:  cff6  movff   TBLPTRL, FSR1L                       ; reg1: 0xff6, reg2: 0xfe1
003812:  ffe1
003814:  cff7  movff   TBLPTRH, FSR1H                       ; reg1: 0xff7, reg2: 0xfe2
003816:  ffe2
003818:  50e7  movf    INDF1, W, A                          ; reg: 0xfe7
00381a:  0012  return  0x0

function_043:                                               ; address: 0x00381c

00381c:  c013  movff   (Common_RAM + 19), (Common_RAM + 3)  ; reg1: 0x013, reg2: 0x003
00381e:  f003
003820:  c014  movff   (Common_RAM + 20), (Common_RAM + 4)  ; reg1: 0x014, reg2: 0x004
003822:  f004
003824:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
003826:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
003828:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
00382a:  0e04  movlw   0x04
00382c:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
00382e:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
003830:  0e17  movlw   0x17
003832:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
003834:  ec14  call    function_061, 0x0                    ; dest: 0x004028
003836:  f020
003838:  c018  movff   (Common_RAM + 24), (Common_RAM + 47) ; reg1: 0x018, reg2: 0x02f
00383a:  f02f
00383c:  c019  movff   (Common_RAM + 25), (Common_RAM + 49) ; reg1: 0x019, reg2: 0x031
00383e:  f031
003840:  0e19  movlw   0x19
003842:  5c31  subwf   (Common_RAM + 49), W, A              ; reg: 0x031
003844:  e22d  bc      label_465
003846:  0e04  movlw   0x04
003848:  2413  addwf   (Common_RAM + 19), W, A              ; reg: 0x013
00384a:  6e15  movwf   (Common_RAM + 21), A                 ; reg: 0x015
00384c:  0e00  movlw   0x00
00384e:  2014  addwfc  (Common_RAM + 20), W, A              ; reg: 0x014
003850:  6e16  movwf   (Common_RAM + 22), A                 ; reg: 0x016
003852:  c015  movff   (Common_RAM + 21), (Common_RAM + 3)  ; reg1: 0x015, reg2: 0x003
003854:  f003
003856:  c016  movff   (Common_RAM + 22), (Common_RAM + 4)  ; reg1: 0x016, reg2: 0x004
003858:  f004
00385a:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
00385c:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
00385e:  c031  movff   (Common_RAM + 49), (Common_RAM + 7)  ; reg1: 0x031, reg2: 0x007
003860:  f007
003862:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
003864:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
003866:  0e17  movlw   0x17
003868:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
00386a:  ec14  call    function_061, 0x0                    ; dest: 0x004028
00386c:  f020
00386e:  80c5  bsf     SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0

label_461:                                                  ; address: 0x003870

003870:  b0c5  btfsc   SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0
003872:  d7fe  bra     label_461                            ; dest: 0x003870
003874:  0e68  movlw   0x68
003876:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
003878:  f01f
00387a:  502f  movf    (Common_RAM + 47), W, A              ; reg: 0x02f
00387c:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
00387e:  f01f
003880:  6a30  clrf    (Common_RAM + 48), A                 ; reg: 0x030
003882:  d008  bra     label_463                            ; dest: 0x003894

label_462:                                                  ; address: 0x003884

003884:  5030  movf    (Common_RAM + 48), W, A              ; reg: 0x030
003886:  0f17  addlw   0x17
003888:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
00388a:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00388c:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
00388e:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
003890:  f01f
003892:  2a30  incf    (Common_RAM + 48), F, A              ; reg: 0x030

label_463:                                                  ; address: 0x003894

003894:  5031  movf    (Common_RAM + 49), W, A              ; reg: 0x031
003896:  5c30  subwf   (Common_RAM + 48), W, A              ; reg: 0x030
003898:  e3f5  bnc     label_462
00389a:  84c5  bsf     SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2

label_464:                                                  ; address: 0x00389c

00389c:  b4c5  btfsc   SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2
00389e:  d7fe  bra     label_464                            ; dest: 0x00389c

label_465:                                                  ; address: 0x0038a0

0038a0:  0012  return  0x0

function_044:                                               ; address: 0x0038a2

0038a2:  c041  movff   (Common_RAM + 65), (Common_RAM + 57) ; reg1: 0x041, reg2: 0x039
0038a4:  f039
0038a6:  c042  movff   (Common_RAM + 66), (Common_RAM + 58) ; reg1: 0x042, reg2: 0x03a
0038a8:  f03a
0038aa:  c043  movff   (Common_RAM + 67), (Common_RAM + 59) ; reg1: 0x043, reg2: 0x03b
0038ac:  f03b
0038ae:  c044  movff   (Common_RAM + 68), (Common_RAM + 60) ; reg1: 0x044, reg2: 0x03c
0038b0:  f03c
0038b2:  c041  movff   (Common_RAM + 65), (Common_RAM + 47) ; reg1: 0x041, reg2: 0x02f
0038b4:  f02f
0038b6:  c042  movff   (Common_RAM + 66), (Common_RAM + 48) ; reg1: 0x042, reg2: 0x030
0038b8:  f030
0038ba:  c043  movff   (Common_RAM + 67), (Common_RAM + 49) ; reg1: 0x043, reg2: 0x031
0038bc:  f031
0038be:  c044  movff   (Common_RAM + 68), (Common_RAM + 50) ; reg1: 0x044, reg2: 0x032
0038c0:  f032
0038c2:  eccc  call    function_032, 0x0                    ; dest: 0x003398
0038c4:  f019
0038c6:  c02f  movff   (Common_RAM + 47), (Common_RAM + 61) ; reg1: 0x02f, reg2: 0x03d
0038c8:  f03d
0038ca:  c030  movff   (Common_RAM + 48), (Common_RAM + 62) ; reg1: 0x030, reg2: 0x03e
0038cc:  f03e
0038ce:  c031  movff   (Common_RAM + 49), (Common_RAM + 63) ; reg1: 0x031, reg2: 0x03f
0038d0:  f03f
0038d2:  c032  movff   (Common_RAM + 50), (Common_RAM + 64) ; reg1: 0x032, reg2: 0x040
0038d4:  f040
0038d6:  ec97  call    function_071, 0x0                    ; dest: 0x00432e
0038d8:  f021
0038da:  c039  movff   (Common_RAM + 57), (Common_RAM + 69) ; reg1: 0x039, reg2: 0x045
0038dc:  f045
0038de:  c03a  movff   (Common_RAM + 58), (Common_RAM + 70) ; reg1: 0x03a, reg2: 0x046
0038e0:  f046
0038e2:  c03b  movff   (Common_RAM + 59), (Common_RAM + 71) ; reg1: 0x03b, reg2: 0x047
0038e4:  f047
0038e6:  c03c  movff   (Common_RAM + 60), (Common_RAM + 72) ; reg1: 0x03c, reg2: 0x048
0038e8:  f048
0038ea:  c045  movff   (Common_RAM + 69), (Common_RAM + 47) ; reg1: 0x045, reg2: 0x02f
0038ec:  f02f
0038ee:  c046  movff   (Common_RAM + 70), (Common_RAM + 48) ; reg1: 0x046, reg2: 0x030
0038f0:  f030
0038f2:  c047  movff   (Common_RAM + 71), (Common_RAM + 49) ; reg1: 0x047, reg2: 0x031
0038f4:  f031
0038f6:  c048  movff   (Common_RAM + 72), (Common_RAM + 50) ; reg1: 0x048, reg2: 0x032
0038f8:  f032
0038fa:  0e41  movlw   0x41
0038fc:  ec8f  call    function_058, 0x0                    ; dest: 0x003f1e
0038fe:  f01f
003900:  c041  movff   (Common_RAM + 65), (Common_RAM + 47) ; reg1: 0x041, reg2: 0x02f
003902:  f02f
003904:  c042  movff   (Common_RAM + 66), (Common_RAM + 48) ; reg1: 0x042, reg2: 0x030
003906:  f030
003908:  c043  movff   (Common_RAM + 67), (Common_RAM + 49) ; reg1: 0x043, reg2: 0x031
00390a:  f031
00390c:  c044  movff   (Common_RAM + 68), (Common_RAM + 50) ; reg1: 0x044, reg2: 0x032
00390e:  f032
003910:  eccc  call    function_032, 0x0                    ; dest: 0x003398
003912:  f019
003914:  c02f  movff   (Common_RAM + 47), (Common_RAM + 65) ; reg1: 0x02f, reg2: 0x041
003916:  f041
003918:  c030  movff   (Common_RAM + 48), (Common_RAM + 66) ; reg1: 0x030, reg2: 0x042
00391a:  f042
00391c:  c031  movff   (Common_RAM + 49), (Common_RAM + 67) ; reg1: 0x031, reg2: 0x043
00391e:  f043
003920:  c032  movff   (Common_RAM + 50), (Common_RAM + 68) ; reg1: 0x032, reg2: 0x044
003922:  f044
003924:  0012  return  0x0

function_045:                                               ; address: 0x003926

003926:  a482  btfss   PORTC, RC2, A                        ; reg: 0xf82, bit: 2
003928:  d006  bra     label_466                            ; dest: 0x003936
00392a:  848a  bsf     LATB, LATB2, A                       ; reg: 0xf8a, bit: 2
00392c:  6ab0  clrf    SPBRGH, A                            ; reg: 0xfb0
00392e:  0e3f  movlw   0x3f
003930:  6eaf  movwf   SPBRG, A                             ; reg: 0xfaf
003932:  82d3  bsf     OSCCON, SCS1, A                      ; reg: 0xfd3, bit: 1
003934:  d005  bra     label_467                            ; dest: 0x003940

label_466:                                                  ; address: 0x003936

003936:  948a  bcf     LATB, LATB2, A                       ; reg: 0xf8a, bit: 2
003938:  6ab0  clrf    SPBRGH, A                            ; reg: 0xfb0
00393a:  0e7f  movlw   0x7f
00393c:  6eaf  movwf   SPBRG, A                             ; reg: 0xfaf
00393e:  92d3  bcf     OSCCON, SCS1, A                      ; reg: 0xfd3, bit: 1

label_467:                                                  ; address: 0x003940

003940:  988a  bcf     LATB, LATB4, A                       ; reg: 0xf8a, bit: 4
003942:  9a8a  bcf     LATB, LATB5, A                       ; reg: 0xf8a, bit: 5
003944:  968a  bcf     LATB, LATB3, A                       ; reg: 0xf8a, bit: 3
003946:  9c89  bcf     LATA, LATA6, A                       ; reg: 0xf89, bit: 6
003948:  9689  bcf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3
00394a:  9889  bcf     LATA, LATA4, A                       ; reg: 0xf89, bit: 4
00394c:  9a89  bcf     LATA, LATA5, A                       ; reg: 0xf89, bit: 5
00394e:  9e8a  bcf     LATB, LATB7, A                       ; reg: 0xf8a, bit: 7
003950:  ec9c  call    function_121, 0x0                    ; dest: 0x004938
003952:  f024
003954:  8ef2  bsf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
003956:  8cf2  bsf     INTCON, PEIE, A                      ; reg: 0xff2, bit: 6
003958:  6b93  clrf    0x93, B                              ; reg: 0x093
00395a:  c093  movff   0x093, 0x0ab
00395c:  f0ab
00395e:  98f0  bcf     INTCON3, INT2E, A                    ; reg: 0xff0, bit: 4
003960:  92f0  bcf     INTCON3, INT2F, A                    ; reg: 0xff0, bit: 1
003962:  94f2  bcf     INTCON, T0IF, A                      ; reg: 0xff2, bit: 2
003964:  9ed5  bcf     T0CON, TMR0ON, A                     ; reg: 0xfd5, bit: 7
003966:  9af2  bcf     INTCON, T0IE, A                      ; reg: 0xff2, bit: 5
003968:  6ba4  clrf    0xa4, B                              ; reg: 0x0a4
00396a:  6bb0  clrf    0xb0, B                              ; reg: 0x0b0
00396c:  6bb6  clrf    0xb6, B                              ; reg: 0x0b6
00396e:  6bba  clrf    0xba, B                              ; reg: 0x0ba
003970:  6b7e  clrf    0x7e, B                              ; reg: 0x07e
003972:  6b7f  clrf    0x7f, B                              ; reg: 0x07f
003974:  6bbd  clrf    0xbd, B                              ; reg: 0x0bd
003976:  6a5e  clrf    (Common_RAM + 94), A                 ; reg: 0x05e
003978:  6bbb  clrf    0xbb, B                              ; reg: 0x0bb
00397a:  6bbc  clrf    0xbc, B                              ; reg: 0x0bc
00397c:  6ba1  clrf    0xa1, B                              ; reg: 0x0a1
00397e:  6b88  clrf    0x88, B                              ; reg: 0x088
003980:  6b89  clrf    0x89, B                              ; reg: 0x089
003982:  92c2  bcf     ADCON0, GO, A                        ; reg: 0xfc2, bit: 1
003984:  6b94  clrf    0x94, B                              ; reg: 0x094
003986:  0e20  movlw   0x20
003988:  0101  movlb   0x1
00398a:  6f0f  movwf   0x0f, B                              ; reg: 0x10f
00398c:  0e21  movlw   0x21
00398e:  6f10  movwf   0x10, B                              ; reg: 0x110
003990:  0e22  movlw   0x22
003992:  6f11  movwf   0x11, B                              ; reg: 0x111
003994:  0e23  movlw   0x23
003996:  6f12  movwf   0x12, B                              ; reg: 0x112
003998:  0e25  movlw   0x25
00399a:  6f13  movwf   0x13, B                              ; reg: 0x113
00399c:  0e27  movlw   0x27
00399e:  6f14  movwf   0x14, B                              ; reg: 0x114
0039a0:  0e28  movlw   0x28
0039a2:  6f15  movwf   0x15, B                              ; reg: 0x115
0039a4:  0c28  retlw   0x28

function_046:                                               ; address: 0x0039a6

0039a6:  6a16  clrf    (Common_RAM + 22), A                 ; reg: 0x016
0039a8:  6a17  clrf    (Common_RAM + 23), A                 ; reg: 0x017
0039aa:  6a18  clrf    (Common_RAM + 24), A                 ; reg: 0x018
0039ac:  0e4b  movlw   0x4b
0039ae:  6e19  movwf   (Common_RAM + 25), A                 ; reg: 0x019
0039b0:  c049  movff   (Common_RAM + 73), (Common_RAM + 18) ; reg1: 0x049, reg2: 0x012
0039b2:  f012
0039b4:  c04a  movff   (Common_RAM + 74), (Common_RAM + 19) ; reg1: 0x04a, reg2: 0x013
0039b6:  f013
0039b8:  c04b  movff   (Common_RAM + 75), (Common_RAM + 20) ; reg1: 0x04b, reg2: 0x014
0039ba:  f014
0039bc:  c04c  movff   (Common_RAM + 76), (Common_RAM + 21) ; reg1: 0x04c, reg2: 0x015
0039be:  f015
0039c0:  ec5e  call    function_017, 0x0                    ; dest: 0x002abc
0039c2:  f015
0039c4:  c012  movff   (Common_RAM + 18), (Common_RAM + 65) ; reg1: 0x012, reg2: 0x041
0039c6:  f041
0039c8:  c013  movff   (Common_RAM + 19), (Common_RAM + 66) ; reg1: 0x013, reg2: 0x042
0039ca:  f042
0039cc:  c014  movff   (Common_RAM + 20), (Common_RAM + 67) ; reg1: 0x014, reg2: 0x043
0039ce:  f043
0039d0:  c015  movff   (Common_RAM + 21), (Common_RAM + 68) ; reg1: 0x015, reg2: 0x044
0039d2:  f044
0039d4:  ec51  call    function_044, 0x0                    ; dest: 0x0038a2
0039d6:  f01c
0039d8:  c041  movff   (Common_RAM + 65), (Common_RAM + 77) ; reg1: 0x041, reg2: 0x04d
0039da:  f04d
0039dc:  c042  movff   (Common_RAM + 66), (Common_RAM + 78) ; reg1: 0x042, reg2: 0x04e
0039de:  f04e
0039e0:  c043  movff   (Common_RAM + 67), (Common_RAM + 79) ; reg1: 0x043, reg2: 0x04f
0039e2:  f04f
0039e4:  c044  movff   (Common_RAM + 68), (Common_RAM + 80) ; reg1: 0x044, reg2: 0x050
0039e6:  f050
0039e8:  c04d  movff   (Common_RAM + 77), (Common_RAM + 37) ; reg1: 0x04d, reg2: 0x025
0039ea:  f025
0039ec:  c04e  movff   (Common_RAM + 78), (Common_RAM + 38) ; reg1: 0x04e, reg2: 0x026
0039ee:  f026
0039f0:  c04f  movff   (Common_RAM + 79), (Common_RAM + 39) ; reg1: 0x04f, reg2: 0x027
0039f2:  f027
0039f4:  c050  movff   (Common_RAM + 80), (Common_RAM + 40) ; reg1: 0x050, reg2: 0x028
0039f6:  f028
0039f8:  ec0d  call    function_027, 0x0                    ; dest: 0x00301a
0039fa:  f018
0039fc:  c025  movff   (Common_RAM + 37), (Common_RAM + 81) ; reg1: 0x025, reg2: 0x051
0039fe:  f051
003a00:  c026  movff   (Common_RAM + 38), (Common_RAM + 82) ; reg1: 0x026, reg2: 0x052
003a02:  f052
003a04:  c027  movff   (Common_RAM + 39), (Common_RAM + 83) ; reg1: 0x027, reg2: 0x053
003a06:  f053
003a08:  c028  movff   (Common_RAM + 40), (Common_RAM + 84) ; reg1: 0x028, reg2: 0x054
003a0a:  f054
003a0c:  5054  movf    (Common_RAM + 84), W, A              ; reg: 0x054
003a0e:  0b0f  andlw   0x0f
003a10:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
003a12:  f01f
003a14:  5053  movf    (Common_RAM + 83), W, A              ; reg: 0x053
003a16:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
003a18:  f01f
003a1a:  5052  movf    (Common_RAM + 82), W, A              ; reg: 0x052
003a1c:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
003a1e:  f01f
003a20:  5051  movf    (Common_RAM + 81), W, A              ; reg: 0x051
003a22:  ef34  goto    function_056                         ; dest: 0x003e68
003a24:  f01f

function_047:                                               ; address: 0x003a26

003a26:  0100  movlb   0x0
003a28:  51cd  movf    0xcd, W, B                           ; reg: 0x0cd
003a2a:  0a06  xorlw   0x06
003a2c:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
003a2e:  b26d  btfsc   UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
003a30:  d004  bra     label_468                            ; dest: 0x003a3a
003a32:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
003a34:  d002  bra     label_468                            ; dest: 0x003a3a
003a36:  b082  btfsc   PORTC, RC0, A                        ; reg: 0xf82, bit: 0
003a38:  d003  bra     label_469                            ; dest: 0x003a40

label_468:                                                  ; address: 0x003a3a

003a3a:  ecaf  call    function_126, 0x0                    ; dest: 0x00495e
003a3c:  f024
003a3e:  d031  bra     label_472                            ; dest: 0x003aa2

label_469:                                                  ; address: 0x003a40

003a40:  67c0  tstfsz  0xc0, B                              ; reg: 0x0c0
003a42:  d01d  bra     label_471                            ; dest: 0x003a7e
003a44:  0104  movlb   0x4
003a46:  bf0c  btfsc   0x0c, 0x7, B                         ; reg: 0x40c
003a48:  d02c  bra     label_472                            ; dest: 0x003aa2
003a4a:  0101  movlb   0x1
003a4c:  0e01  movlw   0x01
003a4e:  6e04  movwf   0x04, A                              ; reg: 0x104
003a50:  0e1a  movlw   0x1a
003a52:  6e03  movwf   0x03, A                              ; reg: 0x103
003a54:  0e40  movlw   0x40
003a56:  6e05  movwf   0x05, A                              ; reg: 0x105
003a58:  ec41  call    function_052, 0x0                    ; dest: 0x003c82
003a5a:  f01e
003a5c:  0e01  movlw   0x01
003a5e:  0100  movlb   0x0
003a60:  6fc0  movwf   0xc0, B                              ; reg: 0x0c0
003a62:  6a59  clrf    (Common_RAM + 89), A                 ; reg: 0x059

label_470:                                                  ; address: 0x003a64

003a64:  0101  movlb   0x1
003a66:  0e5a  movlw   0x5a
003a68:  2459  addwf   0x59, W, A                           ; reg: 0x159
003a6a:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003a6c:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003a6e:  0e01  movlw   0x01
003a70:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
003a72:  6adf  clrf    INDF2, A                             ; reg: 0xfdf
003a74:  2a59  incf    0x59, F, A                           ; reg: 0x159
003a76:  0e3f  movlw   0x3f
003a78:  6459  cpfsgt  0x59, A                              ; reg: 0x159
003a7a:  d7f4  bra     label_470                            ; dest: 0x003a64
003a7c:  d012  bra     label_472                            ; dest: 0x003aa2

label_471:                                                  ; address: 0x003a7e

003a7e:  0101  movlb   0x1
003a80:  511a  movf    0x1a, W, B                           ; reg: 0x11a
003a82:  ec56  call    function_000, 0x0                    ; dest: 0x0010ac
003a84:  f008
003a86:  0104  movlb   0x4
003a88:  bf10  btfsc   0x10, 0x7, B                         ; reg: 0x410
003a8a:  d00b  bra     label_472                            ; dest: 0x003aa2
003a8c:  0101  movlb   0x1
003a8e:  0e01  movlw   0x01
003a90:  6e04  movwf   0x04, A                              ; reg: 0x104
003a92:  0e5a  movlw   0x5a
003a94:  6e03  movwf   0x03, A                              ; reg: 0x103
003a96:  0e40  movlw   0x40
003a98:  6e05  movwf   0x05, A                              ; reg: 0x105
003a9a:  ece8  call    function_060, 0x0                    ; dest: 0x003fd0
003a9c:  f01f
003a9e:  0100  movlb   0x0
003aa0:  6bc0  clrf    0xc0, B                              ; reg: 0x0c0

label_472:                                                  ; address: 0x003aa2

003aa2:  0012  return  0x0

function_048:                                               ; address: 0x003aa4

003aa4:  6a0e  clrf    (Common_RAM + 14), A                 ; reg: 0x00e
003aa6:  6a0d  clrf    (Common_RAM + 13), A                 ; reg: 0x00d
003aa8:  6a0f  clrf    (Common_RAM + 15), A                 ; reg: 0x00f
003aaa:  6a0b  clrf    (Common_RAM + 11), A                 ; reg: 0x00b
003aac:  c005  movff   (Common_RAM + 5), (Common_RAM + 3)   ; reg1: 0x005, reg2: 0x003
003aae:  f003
003ab0:  c006  movff   (Common_RAM + 6), (Common_RAM + 4)   ; reg1: 0x006, reg2: 0x004
003ab2:  f004
003ab4:  ecbd  call    function_099, 0x0                    ; dest: 0x00477a
003ab6:  f023

label_473:                                                  ; address: 0x003ab8

003ab8:  ec39  call    function_109, 0x0                    ; dest: 0x004872
003aba:  f024
003abc:  0900  iorlw   0x00
003abe:  e023  bz      label_477
003ac0:  c00f  movff   (Common_RAM + 15), (Common_RAM + 10) ; reg1: 0x00f, reg2: 0x00a
003ac2:  f00a
003ac4:  ecfd  call    function_087, 0x0                    ; dest: 0x0045fa
003ac6:  f022
003ac8:  6e0f  movwf   (Common_RAM + 15), A                 ; reg: 0x00f
003aca:  500d  movf    (Common_RAM + 13), W, A              ; reg: 0x00d
003acc:  e00a  bz      label_474
003ace:  500e  movf    (Common_RAM + 14), W, A              ; reg: 0x00e
003ad0:  2407  addwf   (Common_RAM + 7), W, A               ; reg: 0x007
003ad2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003ad4:  0e00  movlw   0x00
003ad6:  2008  addwfc  (Common_RAM + 8), W, A               ; reg: 0x008
003ad8:  6eda  movwf   FSR2H, A                             ; reg: 0xfda
003ada:  c00f  movff   (Common_RAM + 15), INDF2             ; reg1: 0x00f, reg2: 0xfdf
003adc:  ffdf
003ade:  2a0e  incf    (Common_RAM + 14), F, A              ; reg: 0x00e
003ae0:  d005  bra     label_475                            ; dest: 0x003aec

label_474:                                                  ; address: 0x003ae2

003ae2:  500f  movf    (Common_RAM + 15), W, A              ; reg: 0x00f
003ae4:  0a3a  xorlw   0x3a
003ae6:  e102  bnz     label_475
003ae8:  0e01  movlw   0x01
003aea:  6e0d  movwf   (Common_RAM + 13), A                 ; reg: 0x00d

label_475:                                                  ; address: 0x003aec

003aec:  6a0c  clrf    (Common_RAM + 12), A                 ; reg: 0x00c
003aee:  500d  movf    (Common_RAM + 13), W, A              ; reg: 0x00d
003af0:  e008  bz      label_476
003af2:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
003af4:  0a0d  xorlw   0x0d
003af6:  e105  bnz     label_476
003af8:  500f  movf    (Common_RAM + 15), W, A              ; reg: 0x00f
003afa:  0a0a  xorlw   0x0a
003afc:  e102  bnz     label_476
003afe:  0e01  movlw   0x01
003b00:  6e0c  movwf   (Common_RAM + 12), A                 ; reg: 0x00c

label_476:                                                  ; address: 0x003b02

003b02:  c00c  movff   (Common_RAM + 12), (Common_RAM + 11) ; reg1: 0x00c, reg2: 0x00b
003b04:  f00b

label_477:                                                  ; address: 0x003b06

003b06:  ec86  call    function_118, 0x0                    ; dest: 0x00490c
003b08:  f024
003b0a:  e205  bc      label_478
003b0c:  5009  movf    (Common_RAM + 9), W, A               ; reg: 0x009
003b0e:  5c0e  subwf   (Common_RAM + 14), W, A              ; reg: 0x00e
003b10:  e202  bc      label_478
003b12:  500b  movf    (Common_RAM + 11), W, A              ; reg: 0x00b
003b14:  e0d1  bz      label_473

label_478:                                                  ; address: 0x003b16

003b16:  eca6  call    function_123, 0x0                    ; dest: 0x00494c
003b18:  f024
003b1a:  500e  movf    (Common_RAM + 14), W, A              ; reg: 0x00e
003b1c:  0012  return  0x0

function_049:                                               ; address: 0x003b1e

003b1e:  0006  pop
003b20:  aaa1  btfss   PIR2, USBIF, A                       ; reg: 0xfa1, bit: 5
003b22:  d002  bra     label_479                            ; dest: 0x003b28
003b24:  9aa1  bcf     PIR2, USBIF, A                       ; reg: 0xfa1, bit: 5
003b26:  9aa0  bcf     PIE2, USBIE, A                       ; reg: 0xfa0, bit: 5

label_479:                                                  ; address: 0x003b28

003b28:  a4f2  btfss   INTCON, T0IF, A                      ; reg: 0xff2, bit: 2
003b2a:  d005  bra     label_480                            ; dest: 0x003b36
003b2c:  0100  movlb   0x0
003b2e:  817e  bsf     0x7e, 0x0, B                         ; reg: 0x07e
003b30:  94f2  bcf     INTCON, T0IF, A                      ; reg: 0xff2, bit: 2
003b32:  9af2  bcf     INTCON, T0IE, A                      ; reg: 0xff2, bit: 5
003b34:  9ed5  bcf     T0CON, TMR0ON, A                     ; reg: 0xfd5, bit: 7

label_480:                                                  ; address: 0x003b36

003b36:  a2a1  btfss   PIR2, TMR3IF, A                      ; reg: 0xfa1, bit: 1
003b38:  d011  bra     label_482                            ; dest: 0x003b5c
003b3a:  90b1  bcf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
003b3c:  0ef8  movlw   0xf8
003b3e:  6eb3  movwf   TMR3H, A                             ; reg: 0xfb3
003b40:  0e30  movlw   0x30
003b42:  6eb2  movwf   TMR3L, A                             ; reg: 0xfb2
003b44:  80b1  bsf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
003b46:  92a1  bcf     PIR2, TMR3IF, A                      ; reg: 0xfa1, bit: 1
003b48:  0100  movlb   0x0
003b4a:  518d  movf    0x8d, W, B                           ; reg: 0x08d
003b4c:  118c  iorwf   0x8c, W, B                           ; reg: 0x08c
003b4e:  e004  bz      label_481
003b50:  078c  decf    0x8c, F, B                           ; reg: 0x08c
003b52:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
003b54:  078d  decf    0x8d, F, B                           ; reg: 0x08d
003b56:  d002  bra     label_482                            ; dest: 0x003b5c

label_481:                                                  ; address: 0x003b58

003b58:  90b1  bcf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
003b5a:  92a0  bcf     PIE2, TMR3IE, A                      ; reg: 0xfa0, bit: 1

label_482:                                                  ; address: 0x003b5c

003b5c:  aa9e  btfss   PIR1, RCIF, A                        ; reg: 0xf9e, bit: 5
003b5e:  d016  bra     label_484                            ; dest: 0x003b8c
003b60:  0e00  movlw   0x00
003b62:  0100  movlb   0x0
003b64:  25c7  addwf   0xc7, W, B                           ; reg: 0x0c7
003b66:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003b68:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003b6a:  0e02  movlw   0x02
003b6c:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
003b6e:  cfae  movff   RCREG, INDF2                         ; reg1: 0xfae, reg2: 0xfdf
003b70:  ffdf
003b72:  2bc7  incf    0xc7, F, B                           ; reg: 0x0c7
003b74:  0ebf  movlw   0xbf
003b76:  65c7  cpfsgt  0xc7, B                              ; reg: 0x0c7
003b78:  d001  bra     label_483                            ; dest: 0x003b7c
003b7a:  6bc7  clrf    0xc7, B                              ; reg: 0x0c7

label_483:                                                  ; address: 0x003b7c

003b7c:  a2ab  btfss   RCSTA, OERR, A                       ; reg: 0xfab, bit: 1
003b7e:  d006  bra     label_484                            ; dest: 0x003b8c
003b80:  98ab  bcf     RCSTA, CREN, A                       ; reg: 0xfab, bit: 4
003b82:  f000  dw      0xf000
003b84:  88ab  bsf     RCSTA, CREN, A                       ; reg: 0xfab, bit: 4
003b86:  805e  bsf     (Common_RAM + 94), 0x0, A            ; reg: 0x05e
003b88:  0100  movlb   0x0
003b8a:  6b98  clrf    0x98, B                              ; reg: 0x098

label_484:                                                  ; address: 0x003b8c

003b8c:  c002  movff   (Common_RAM + 2), FSR2H              ; reg1: 0x002, reg2: 0xfda
003b8e:  ffda
003b90:  c001  movff   (Common_RAM + 1), FSR2L              ; reg1: 0x001, reg2: 0xfd9
003b92:  ffd9
003b94:  0011  retfie  0x1

function_050:                                               ; address: 0x003b96

003b96:  0ebf  movlw   0xbf
003b98:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003b9a:  f024
003b9c:  0e05  movlw   0x05
003b9e:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003ba0:  f024
003ba2:  505f  movf    (Common_RAM + 95), W, A              ; reg: 0x05f
003ba4:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003ba6:  f024
003ba8:  ec97  call    function_120, 0x0                    ; dest: 0x00492e
003baa:  f024
003bac:  0ebf  movlw   0xbf
003bae:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bb0:  f024
003bb2:  0e07  movlw   0x07
003bb4:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bb6:  f024
003bb8:  0100  movlb   0x0
003bba:  516e  movf    0x6e, W, B                           ; reg: 0x06e
003bbc:  0f60  addlw   0x60
003bbe:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bc0:  f024
003bc2:  ec97  call    function_120, 0x0                    ; dest: 0x00492e
003bc4:  f024
003bc6:  0ebf  movlw   0xbf
003bc8:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bca:  f024
003bcc:  0e03  movlw   0x03
003bce:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bd0:  f024
003bd2:  0e01  movlw   0x01
003bd4:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
003bd6:  0e00  movlw   0x00
003bd8:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bda:  f024
003bdc:  ec97  call    function_120, 0x0                    ; dest: 0x00492e
003bde:  f024
003be0:  0ebf  movlw   0xbf
003be2:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003be4:  f024
003be6:  0e06  movlw   0x06
003be8:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bea:  f024
003bec:  0100  movlb   0x0
003bee:  5199  movf    0x99, W, B                           ; reg: 0x099
003bf0:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bf2:  f024
003bf4:  ec97  call    function_120, 0x0                    ; dest: 0x00492e
003bf6:  f024
003bf8:  0ebf  movlw   0xbf
003bfa:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003bfc:  f024
003bfe:  0e1d  movlw   0x1d
003c00:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
003c02:  f024
003c04:  0100  movlb   0x0
003c06:  51b8  movf    0xb8, W, B                           ; reg: 0x0b8
003c08:  ef4b  goto    function_111                         ; dest: 0x004896
003c0a:  f024

function_051:                                               ; address: 0x003c0c

003c0c:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
003c0e:  0e1b  movlw   0x1b
003c10:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003c12:  f023
003c14:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
003c16:  0e1c  movlw   0x1c
003c18:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003c1a:  f023
003c1c:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
003c1e:  0e1d  movlw   0x1d
003c20:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003c22:  f023
003c24:  a482  btfss   PORTC, RC2, A                        ; reg: 0xf82, bit: 2
003c26:  d006  bra     label_485                            ; dest: 0x003c34
003c28:  848a  bsf     LATB, LATB2, A                       ; reg: 0xf8a, bit: 2
003c2a:  6ab0  clrf    SPBRGH, A                            ; reg: 0xfb0
003c2c:  0e3f  movlw   0x3f
003c2e:  6eaf  movwf   SPBRG, A                             ; reg: 0xfaf
003c30:  82d3  bsf     OSCCON, SCS1, A                      ; reg: 0xfd3, bit: 1
003c32:  d005  bra     label_486                            ; dest: 0x003c3e

label_485:                                                  ; address: 0x003c34

003c34:  948a  bcf     LATB, LATB2, A                       ; reg: 0xf8a, bit: 2
003c36:  6ab0  clrf    SPBRGH, A                            ; reg: 0xfb0
003c38:  0e7f  movlw   0x7f
003c3a:  6eaf  movwf   SPBRG, A                             ; reg: 0xfaf
003c3c:  92d3  bcf     OSCCON, SCS1, A                      ; reg: 0xfd3, bit: 1

label_486:                                                  ; address: 0x003c3e

003c3e:  988a  bcf     LATB, LATB4, A                       ; reg: 0xf8a, bit: 4
003c40:  9c89  bcf     LATA, LATA6, A                       ; reg: 0xf89, bit: 6
003c42:  9689  bcf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3
003c44:  9889  bcf     LATA, LATA4, A                       ; reg: 0xf89, bit: 4
003c46:  9a89  bcf     LATA, LATA5, A                       ; reg: 0xf89, bit: 5
003c48:  0e28  movlw   0x28
003c4a:  0100  movlb   0x0
003c4c:  5d88  subwf   0x88, W, B                           ; reg: 0x088
003c4e:  0e02  movlw   0x02
003c50:  5989  subwfb  0x89, W, B                           ; reg: 0x089
003c52:  e212  bc      label_488
003c54:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
003c56:  6a09  clrf    (Common_RAM + 9), A                  ; reg: 0x009

label_487:                                                  ; address: 0x003c58

003c58:  c008  movff   (Common_RAM + 8), (Common_RAM + 6)   ; reg1: 0x008, reg2: 0x006
003c5a:  f006
003c5c:  0e1c  movlw   0x1c
003c5e:  ec5d  call    function_093, 0x0                    ; dest: 0x0046ba
003c60:  f023
003c62:  0e01  movlw   0x01
003c64:  1a08  xorwf   (Common_RAM + 8), F, A               ; reg: 0x008
003c66:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
003c68:  0efa  movlw   0xfa
003c6a:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
003c6c:  ec3f  call    function_079, 0x0                    ; dest: 0x00447e
003c6e:  f022
003c70:  2a09  incf    (Common_RAM + 9), F, A               ; reg: 0x009
003c72:  0e04  movlw   0x04
003c74:  6409  cpfsgt  (Common_RAM + 9), A                  ; reg: 0x009
003c76:  d7f0  bra     label_487                            ; dest: 0x003c58

label_488:                                                  ; address: 0x003c78

003c78:  968a  bcf     LATB, LATB3, A                       ; reg: 0xf8a, bit: 3
003c7a:  9ed5  bcf     T0CON, TMR0ON, A                     ; reg: 0xfd5, bit: 7
003c7c:  9af2  bcf     INTCON, T0IE, A                      ; reg: 0xff2, bit: 5
003c7e:  ef78  goto    function_116                         ; dest: 0x0048f0
003c80:  f024

function_052:                                               ; address: 0x003c82

003c82:  0100  movlb   0x0
003c84:  6bca  clrf    0xca, B                              ; reg: 0x0ca
003c86:  0104  movlb   0x4
003c88:  bf0c  btfsc   0x0c, 0x7, B                         ; reg: 0x40c
003c8a:  d02d  bra     label_491                            ; dest: 0x003ce6
003c8c:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
003c8e:  5d0d  subwf   (Common_RAM + 13), W, B              ; reg: 0x00d
003c90:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
003c92:  c40d  movff   0x40d, (Common_RAM + 5)              ; reg2: 0x005
003c94:  f005
003c96:  0100  movlb   0x0
003c98:  6bca  clrf    0xca, B                              ; reg: 0x0ca
003c9a:  d010  bra     label_490                            ; dest: 0x003cbc

label_489:                                                  ; address: 0x003c9c

003c9c:  0e2c  movlw   0x2c
003c9e:  0100  movlb   0x0
003ca0:  25ca  addwf   0xca, W, B                           ; reg: 0x0ca
003ca2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003ca4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003ca6:  0e04  movlw   0x04
003ca8:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
003caa:  51ca  movf    0xca, W, B                           ; reg: 0x0ca
003cac:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
003cae:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
003cb0:  0e00  movlw   0x00
003cb2:  2004  addwfc  (Common_RAM + 4), W, A               ; reg: 0x004
003cb4:  6ee2  movwf   FSR1H, A                             ; reg: 0xfe2
003cb6:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
003cb8:  ffe7
003cba:  2bca  incf    0xca, F, B                           ; reg: 0x0ca

label_490:                                                  ; address: 0x003cbc

003cbc:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
003cbe:  5dca  subwf   0xca, W, B                           ; reg: 0x0ca
003cc0:  e3ed  bnc     label_489
003cc2:  0e40  movlw   0x40
003cc4:  0104  movlb   0x4
003cc6:  6f0d  movwf   0x0d, B                              ; reg: 0x40d
003cc8:  170c  andwf   0x0c, F, B                           ; reg: 0x40c
003cca:  0e01  movlw   0x01
003ccc:  bd0c  btfsc   0x0c, 0x6, B                         ; reg: 0x40c
003cce:  0e00  movlw   0x00
003cd0:  6e06  movwf   0x06, A                              ; reg: 0x406
003cd2:  3a06  swapf   0x06, F, A                           ; reg: 0x406
003cd4:  4606  rlncf   0x06, F, A                           ; reg: 0x406
003cd6:  4606  rlncf   0x06, F, A                           ; reg: 0x406
003cd8:  510c  movf    0x0c, W, B                           ; reg: 0x40c
003cda:  1806  xorwf   0x06, W, A                           ; reg: 0x406
003cdc:  0bbf  andlw   0xbf
003cde:  1806  xorwf   0x06, W, A                           ; reg: 0x406
003ce0:  6f0c  movwf   0x0c, B                              ; reg: 0x40c
003ce2:  870c  bsf     0x0c, 0x3, B                         ; reg: 0x40c
003ce4:  8f0c  bsf     0x0c, 0x7, B                         ; reg: 0x40c

label_491:                                                  ; address: 0x003ce6

003ce6:  0012  return  0x0

function_053:                                               ; address: 0x003ce8

003ce8:  ee20  lfsr    0x2, 0x003
003cea:  f003
003cec:  50de  movf    POSTINC2, W, A                       ; reg: 0xfde
003cee:  10de  iorwf   POSTINC2, W, A                       ; reg: 0xfde
003cf0:  10de  iorwf   POSTINC2, W, A                       ; reg: 0xfde
003cf2:  10de  iorwf   POSTINC2, W, A                       ; reg: 0xfde
003cf4:  e107  bnz     label_492
003cf6:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
003cf8:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003cfa:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003cfc:  0e00  movlw   0x00
003cfe:  6ede  movwf   POSTINC2, A                          ; reg: 0xfde
003d00:  6edd  movwf   POSTDEC2, A                          ; reg: 0xfdd
003d02:  d024  bra     label_493                            ; dest: 0x003d4c

label_492:                                                  ; address: 0x003d04

003d04:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
003d06:  0b7f  andlw   0x7f
003d08:  6e08  movwf   (Common_RAM + 8), A                  ; reg: 0x008
003d0a:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
003d0c:  3408  rlcf    (Common_RAM + 8), W, A               ; reg: 0x008
003d0e:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
003d10:  6a0a  clrf    (Common_RAM + 10), A                 ; reg: 0x00a
003d12:  360a  rlcf    (Common_RAM + 10), F, A              ; reg: 0x00a
003d14:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
003d16:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003d18:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003d1a:  c009  movff   (Common_RAM + 9), POSTINC2           ; reg1: 0x009, reg2: 0xfde
003d1c:  ffde
003d1e:  c00a  movff   (Common_RAM + 10), POSTDEC2          ; reg1: 0x00a, reg2: 0xfdd
003d20:  ffdd
003d22:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
003d24:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003d26:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003d28:  0e01  movlw   0x01
003d2a:  ae05  btfss   (Common_RAM + 5), 0x7, A             ; reg: 0x005
003d2c:  0e00  movlw   0x00
003d2e:  12de  iorwf   POSTINC2, F, A                       ; reg: 0xfde
003d30:  0e00  movlw   0x00
003d32:  12dd  iorwf   POSTDEC2, F, A                       ; reg: 0xfdd
003d34:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
003d36:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003d38:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003d3a:  0e82  movlw   0x82
003d3c:  26de  addwf   POSTINC2, F, A                       ; reg: 0xfde
003d3e:  0eff  movlw   0xff
003d40:  22dd  addwfc  POSTDEC2, F, A                       ; reg: 0xfdd
003d42:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
003d44:  0b80  andlw   0x80
003d46:  093f  iorlw   0x3f
003d48:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
003d4a:  9e05  bcf     (Common_RAM + 5), 0x7, A             ; reg: 0x005

label_493:                                                  ; address: 0x003d4c

003d4c:  0012  return  0x0

label_494:                                                  ; address: 0x003d4e

003d4e:  ee03  lfsr    0x0, 0x300
003d50:  f000
003d52:  0ec0  movlw   0xc0

label_495:                                                  ; address: 0x003d54

003d54:  6aee  clrf    POSTINC0, A                          ; reg: 0xfee
003d56:  06e8  decf    WREG, F, A                           ; reg: 0xfe8
003d58:  e1fd  bnz     label_495
003d5a:  ee02  lfsr    0x0, 0x200
003d5c:  f000
003d5e:  0ede  movlw   0xde

label_496:                                                  ; address: 0x003d60

003d60:  6aee  clrf    POSTINC0, A                          ; reg: 0xfee
003d62:  06e8  decf    WREG, F, A                           ; reg: 0xfe8
003d64:  e1fd  bnz     label_496
003d66:  ee01  lfsr    0x0, 0x100
003d68:  f000
003d6a:  0ee5  movlw   0xe5

label_497:                                                  ; address: 0x003d6c

003d6c:  6aee  clrf    POSTINC0, A                          ; reg: 0xfee
003d6e:  06e8  decf    WREG, F, A                           ; reg: 0xfe8
003d70:  e1fd  bnz     label_497
003d72:  ee00  lfsr    0x0, 0x060
003d74:  f060
003d76:  0e8d  movlw   0x8d

label_498:                                                  ; address: 0x003d78

003d78:  6aee  clrf    POSTINC0, A                          ; reg: 0xfee
003d7a:  06e8  decf    WREG, F, A                           ; reg: 0xfe8
003d7c:  e1fd  bnz     label_498
003d7e:  6a5f  clrf    (Common_RAM + 95), A                 ; reg: 0x05f
003d80:  6a5e  clrf    (Common_RAM + 94), A                 ; reg: 0x05e
003d82:  0ee6  movlw   0xe6
003d84:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
003d86:  0e47  movlw   0x47
003d88:  6ef7  movwf   TBLPTRH, A                           ; reg: 0xff7
003d8a:  0e00  movlw   0x00
003d8c:  6ef8  movwf   TBLPTRU, A                           ; reg: 0xff8
003d8e:  ee01  lfsr    0x0, 0x1e5
003d90:  f0e5
003d92:  ee10  lfsr    0x1, 0x016
003d94:  f016

label_499:                                                  ; address: 0x003d96

003d96:  0009  tblrd*+
003d98:  cff5  movff   TABLAT, POSTINC0                     ; reg1: 0xff5, reg2: 0xfee
003d9a:  ffee
003d9c:  50e5  movf    POSTDEC1, W, A                       ; reg: 0xfe5
003d9e:  50e1  movf    FSR1L, W, A                          ; reg: 0xfe1
003da0:  e1fa  bnz     label_499
003da2:  0e00  movlw   0x00
003da4:  6ef8  movwf   TBLPTRU, A                           ; reg: 0xff8
003da6:  0100  movlb   0x0
003da8:  ef63  goto    label_606                            ; dest: 0x0048c6
003daa:  f024

function_054:                                               ; address: 0x003dac

003dac:  6a0b  clrf    (Common_RAM + 11), A                 ; reg: 0x00b
003dae:  c003  movff   (Common_RAM + 3), (Common_RAM + 12)  ; reg1: 0x003, reg2: 0x00c
003db0:  f00c
003db2:  c004  movff   (Common_RAM + 4), (Common_RAM + 13)  ; reg1: 0x004, reg2: 0x00d
003db4:  f00d
003db6:  c005  movff   (Common_RAM + 5), (Common_RAM + 14)  ; reg1: 0x005, reg2: 0x00e
003db8:  f00e
003dba:  c006  movff   (Common_RAM + 6), (Common_RAM + 15)  ; reg1: 0x006, reg2: 0x00f
003dbc:  f00f
003dbe:  d01a  bra     label_502                            ; dest: 0x003df4

label_500:                                                  ; address: 0x003dc0

003dc0:  c00e  movff   (Common_RAM + 14), TBLPTRU           ; reg1: 0x00e, reg2: 0xff8
003dc2:  fff8
003dc4:  c00d  movff   (Common_RAM + 13), TBLPTRH           ; reg1: 0x00d, reg2: 0xff7
003dc6:  fff7
003dc8:  c00c  movff   (Common_RAM + 12), TBLPTRL           ; reg1: 0x00c, reg2: 0xff6
003dca:  fff6
003dcc:  8ea6  bsf     EECON1, EEPGD, A                     ; reg: 0xfa6, bit: 7
003dce:  9ca6  bcf     EECON1, CFGS, A                      ; reg: 0xfa6, bit: 6
003dd0:  84a6  bsf     EECON1, WREN, A                      ; reg: 0xfa6, bit: 2
003dd2:  88a6  bsf     EECON1, FREE, A                      ; reg: 0xfa6, bit: 4
003dd4:  aef2  btfss   INTCON, GIE, A                       ; reg: 0xff2, bit: 7
003dd6:  d003  bra     label_501                            ; dest: 0x003dde
003dd8:  9ef2  bcf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
003dda:  0e01  movlw   0x01
003ddc:  6e0b  movwf   (Common_RAM + 11), A                 ; reg: 0x00b

label_501:                                                  ; address: 0x003dde

003dde:  ec03  call    function_076, 0x0                    ; dest: 0x004406
003de0:  f022
003de2:  500b  movf    (Common_RAM + 11), W, A              ; reg: 0x00b
003de4:  a4d8  btfss   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
003de6:  8ef2  bsf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
003de8:  0e40  movlw   0x40
003dea:  260c  addwf   (Common_RAM + 12), F, A              ; reg: 0x00c
003dec:  0e00  movlw   0x00
003dee:  220d  addwfc  (Common_RAM + 13), F, A              ; reg: 0x00d
003df0:  220e  addwfc  (Common_RAM + 14), F, A              ; reg: 0x00e
003df2:  220f  addwfc  (Common_RAM + 15), F, A              ; reg: 0x00f

label_502:                                                  ; address: 0x003df4

003df4:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
003df6:  5c0c  subwf   (Common_RAM + 12), W, A              ; reg: 0x00c
003df8:  5008  movf    (Common_RAM + 8), W, A               ; reg: 0x008
003dfa:  580d  subwfb  (Common_RAM + 13), W, A              ; reg: 0x00d
003dfc:  5009  movf    (Common_RAM + 9), W, A               ; reg: 0x009
003dfe:  580e  subwfb  (Common_RAM + 14), W, A              ; reg: 0x00e
003e00:  500a  movf    (Common_RAM + 10), W, A              ; reg: 0x00a
003e02:  580f  subwfb  (Common_RAM + 15), W, A              ; reg: 0x00f
003e04:  b0d8  btfsc   STATUS, C, A                         ; reg: 0xfd8, bit: 0
003e06:  0012  return  0x0
003e08:  d7db  bra     label_500                            ; dest: 0x003dc0

function_055:                                               ; address: 0x003e0a

003e0a:  6a11  clrf    (Common_RAM + 17), A                 ; reg: 0x011
003e0c:  5010  movf    (Common_RAM + 16), W, A              ; reg: 0x010
003e0e:  0a80  xorlw   0x80
003e10:  0f80  addlw   0x80
003e12:  e108  bnz     label_503
003e14:  0e00  movlw   0x00
003e16:  5c0f  subwf   (Common_RAM + 15), W, A              ; reg: 0x00f
003e18:  e105  bnz     label_503
003e1a:  0e00  movlw   0x00
003e1c:  5c0e  subwf   (Common_RAM + 14), W, A              ; reg: 0x00e
003e1e:  e102  bnz     label_503
003e20:  0e00  movlw   0x00
003e22:  5c0d  subwf   (Common_RAM + 13), W, A              ; reg: 0x00d

label_503:                                                  ; address: 0x003e24

003e24:  e20a  bc      label_504
003e26:  1e10  comf    (Common_RAM + 16), F, A              ; reg: 0x010
003e28:  1e0f  comf    (Common_RAM + 15), F, A              ; reg: 0x00f
003e2a:  1e0e  comf    (Common_RAM + 14), F, A              ; reg: 0x00e
003e2c:  6c0d  negf    (Common_RAM + 13), A                 ; reg: 0x00d
003e2e:  0e00  movlw   0x00
003e30:  220e  addwfc  (Common_RAM + 14), F, A              ; reg: 0x00e
003e32:  220f  addwfc  (Common_RAM + 15), F, A              ; reg: 0x00f
003e34:  2210  addwfc  (Common_RAM + 16), F, A              ; reg: 0x010
003e36:  0e01  movlw   0x01
003e38:  6e11  movwf   (Common_RAM + 17), A                 ; reg: 0x011

label_504:                                                  ; address: 0x003e3a

003e3a:  c00d  movff   (Common_RAM + 13), (Common_RAM + 3)  ; reg1: 0x00d, reg2: 0x003
003e3c:  f003
003e3e:  c00e  movff   (Common_RAM + 14), (Common_RAM + 4)  ; reg1: 0x00e, reg2: 0x004
003e40:  f004
003e42:  c00f  movff   (Common_RAM + 15), (Common_RAM + 5)  ; reg1: 0x00f, reg2: 0x005
003e44:  f005
003e46:  c010  movff   (Common_RAM + 16), (Common_RAM + 6)  ; reg1: 0x010, reg2: 0x006
003e48:  f006
003e4a:  0e96  movlw   0x96
003e4c:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
003e4e:  c011  movff   (Common_RAM + 17), (Common_RAM + 8)  ; reg1: 0x011, reg2: 0x008
003e50:  f008
003e52:  ec6c  call    function_029, 0x0                    ; dest: 0x0030d8
003e54:  f018
003e56:  c003  movff   (Common_RAM + 3), (Common_RAM + 13)  ; reg1: 0x003, reg2: 0x00d
003e58:  f00d
003e5a:  c004  movff   (Common_RAM + 4), (Common_RAM + 14)  ; reg1: 0x004, reg2: 0x00e
003e5c:  f00e
003e5e:  c005  movff   (Common_RAM + 5), (Common_RAM + 15)  ; reg1: 0x005, reg2: 0x00f
003e60:  f00f
003e62:  c006  movff   (Common_RAM + 6), (Common_RAM + 16)  ; reg1: 0x006, reg2: 0x010
003e64:  f010
003e66:  0012  return  0x0

function_056:                                               ; address: 0x003e68

003e68:  cfe8  movff   WREG, (Common_RAM + 5)               ; reg1: 0xfe8, reg2: 0x005
003e6a:  f005
003e6c:  c005  movff   (Common_RAM + 5), SSPBUF             ; reg1: 0x005, reg2: 0xfc9
003e6e:  ffc9
003e70:  bec6  btfsc   SSPCON1, WCOL, A                     ; reg: 0xfc6, bit: 7
003e72:  d027  bra     label_508                            ; dest: 0x003ec2
003e74:  cfc6  movff   SSPCON1, (Common_RAM + 4)            ; reg1: 0xfc6, reg2: 0x004
003e76:  f004
003e78:  0e0f  movlw   0x0f
003e7a:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
003e7c:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
003e7e:  0a08  xorlw   0x08
003e80:  e00d  bz      label_506
003e82:  cfc6  movff   SSPCON1, (Common_RAM + 4)            ; reg1: 0xfc6, reg2: 0x004
003e84:  f004
003e86:  0e0f  movlw   0x0f
003e88:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
003e8a:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
003e8c:  0a0b  xorlw   0x0b
003e8e:  e006  bz      label_506
003e90:  88c6  bsf     SSPCON1, CKP, A                      ; reg: 0xfc6, bit: 4

label_505:                                                  ; address: 0x003e92

003e92:  a69e  btfss   PIR1, SSPIF, A                       ; reg: 0xf9e, bit: 3
003e94:  d7fe  bra     label_505                            ; dest: 0x003e92
003e96:  a4c7  btfss   SSPSTAT, R, A                        ; reg: 0xfc7, bit: 2
003e98:  50c7  movf    SSPSTAT, W, A                        ; reg: 0xfc7
003e9a:  d013  bra     label_508                            ; dest: 0x003ec2

label_506:                                                  ; address: 0x003e9c

003e9c:  cfc6  movff   SSPCON1, (Common_RAM + 4)            ; reg1: 0xfc6, reg2: 0x004
003e9e:  f004
003ea0:  0e0f  movlw   0x0f
003ea2:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
003ea4:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
003ea6:  0a08  xorlw   0x08
003ea8:  e007  bz      label_507
003eaa:  cfc6  movff   SSPCON1, (Common_RAM + 4)            ; reg1: 0xfc6, reg2: 0x004
003eac:  f004
003eae:  0e0f  movlw   0x0f
003eb0:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
003eb2:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
003eb4:  0a0b  xorlw   0x0b
003eb6:  e105  bnz     label_508

label_507:                                                  ; address: 0x003eb8

003eb8:  b0c7  btfsc   SSPSTAT, BF, A                       ; reg: 0xfc7, bit: 0
003eba:  d7fe  bra     label_507                            ; dest: 0x003eb8
003ebc:  ec5b  call    function_113, 0x0                    ; dest: 0x0048b6
003ebe:  f024
003ec0:  50c5  movf    SSPCON2, W, A                        ; reg: 0xfc5

label_508:                                                  ; address: 0x003ec2

003ec2:  0012  return  0x0

function_057:                                               ; address: 0x003ec4

003ec4:  cfe8  movff   WREG, (Common_RAM + 45)              ; reg1: 0xfe8, reg2: 0x02d
003ec6:  f02d
003ec8:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
003eca:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003ecc:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003ece:  cfde  movff   POSTINC2, (Common_RAM + 18)          ; reg1: 0xfde, reg2: 0x012
003ed0:  f012
003ed2:  cfde  movff   POSTINC2, (Common_RAM + 19)          ; reg1: 0xfde, reg2: 0x013
003ed4:  f013
003ed6:  cfde  movff   POSTINC2, (Common_RAM + 20)          ; reg1: 0xfde, reg2: 0x014
003ed8:  f014
003eda:  cfde  movff   POSTINC2, (Common_RAM + 21)          ; reg1: 0xfde, reg2: 0x015
003edc:  f015
003ede:  c025  movff   (Common_RAM + 37), (Common_RAM + 22) ; reg1: 0x025, reg2: 0x016
003ee0:  f016
003ee2:  c026  movff   (Common_RAM + 38), (Common_RAM + 23) ; reg1: 0x026, reg2: 0x017
003ee4:  f017
003ee6:  c027  movff   (Common_RAM + 39), (Common_RAM + 24) ; reg1: 0x027, reg2: 0x018
003ee8:  f018
003eea:  c028  movff   (Common_RAM + 40), (Common_RAM + 25) ; reg1: 0x028, reg2: 0x019
003eec:  f019
003eee:  ec5e  call    function_017, 0x0                    ; dest: 0x002abc
003ef0:  f015
003ef2:  c012  movff   (Common_RAM + 18), (Common_RAM + 41) ; reg1: 0x012, reg2: 0x029
003ef4:  f029
003ef6:  c013  movff   (Common_RAM + 19), (Common_RAM + 42) ; reg1: 0x013, reg2: 0x02a
003ef8:  f02a
003efa:  c014  movff   (Common_RAM + 20), (Common_RAM + 43) ; reg1: 0x014, reg2: 0x02b
003efc:  f02b
003efe:  c015  movff   (Common_RAM + 21), (Common_RAM + 44) ; reg1: 0x015, reg2: 0x02c
003f00:  f02c
003f02:  502d  movf    (Common_RAM + 45), W, A              ; reg: 0x02d
003f04:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003f06:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003f08:  c029  movff   (Common_RAM + 41), POSTINC2          ; reg1: 0x029, reg2: 0xfde
003f0a:  ffde
003f0c:  c02a  movff   (Common_RAM + 42), POSTINC2          ; reg1: 0x02a, reg2: 0xfde
003f0e:  ffde
003f10:  c02b  movff   (Common_RAM + 43), POSTINC2          ; reg1: 0x02b, reg2: 0xfde
003f12:  ffde
003f14:  c02c  movff   (Common_RAM + 44), POSTDEC2          ; reg1: 0x02c, reg2: 0xfdd
003f16:  ffdd
003f18:  06d9  decf    FSR2L, F, A                          ; reg: 0xfd9
003f1a:  06d9  decf    FSR2L, F, A                          ; reg: 0xfd9
003f1c:  0012  return  0x0

function_058:                                               ; address: 0x003f1e

003f1e:  cfe8  movff   WREG, (Common_RAM + 55)              ; reg1: 0xfe8, reg2: 0x037
003f20:  f037
003f22:  5037  movf    (Common_RAM + 55), W, A              ; reg: 0x037
003f24:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003f26:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003f28:  cfde  movff   POSTINC2, (Common_RAM + 32)          ; reg1: 0xfde, reg2: 0x020
003f2a:  f020
003f2c:  cfde  movff   POSTINC2, (Common_RAM + 33)          ; reg1: 0xfde, reg2: 0x021
003f2e:  f021
003f30:  cfde  movff   POSTINC2, (Common_RAM + 34)          ; reg1: 0xfde, reg2: 0x022
003f32:  f022
003f34:  cfde  movff   POSTINC2, (Common_RAM + 35)          ; reg1: 0xfde, reg2: 0x023
003f36:  f023
003f38:  c02f  movff   (Common_RAM + 47), (Common_RAM + 36) ; reg1: 0x02f, reg2: 0x024
003f3a:  f024
003f3c:  c030  movff   (Common_RAM + 48), (Common_RAM + 37) ; reg1: 0x030, reg2: 0x025
003f3e:  f025
003f40:  c031  movff   (Common_RAM + 49), (Common_RAM + 38) ; reg1: 0x031, reg2: 0x026
003f42:  f026
003f44:  c032  movff   (Common_RAM + 50), (Common_RAM + 39) ; reg1: 0x032, reg2: 0x027
003f46:  f027
003f48:  ec61  call    function_011, 0x0                    ; dest: 0x0024c2
003f4a:  f012
003f4c:  c020  movff   (Common_RAM + 32), (Common_RAM + 51) ; reg1: 0x020, reg2: 0x033
003f4e:  f033
003f50:  c021  movff   (Common_RAM + 33), (Common_RAM + 52) ; reg1: 0x021, reg2: 0x034
003f52:  f034
003f54:  c022  movff   (Common_RAM + 34), (Common_RAM + 53) ; reg1: 0x022, reg2: 0x035
003f56:  f035
003f58:  c023  movff   (Common_RAM + 35), (Common_RAM + 54) ; reg1: 0x023, reg2: 0x036
003f5a:  f036
003f5c:  5037  movf    (Common_RAM + 55), W, A              ; reg: 0x037
003f5e:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003f60:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
003f62:  c033  movff   (Common_RAM + 51), POSTINC2          ; reg1: 0x033, reg2: 0xfde
003f64:  ffde
003f66:  c034  movff   (Common_RAM + 52), POSTINC2          ; reg1: 0x034, reg2: 0xfde
003f68:  ffde
003f6a:  c035  movff   (Common_RAM + 53), POSTINC2          ; reg1: 0x035, reg2: 0xfde
003f6c:  ffde
003f6e:  c036  movff   (Common_RAM + 54), POSTDEC2          ; reg1: 0x036, reg2: 0xfdd
003f70:  ffdd
003f72:  06d9  decf    FSR2L, F, A                          ; reg: 0xfd9
003f74:  06d9  decf    FSR2L, F, A                          ; reg: 0xfd9
003f76:  0012  return  0x0

function_059:                                               ; address: 0x003f78

003f78:  cfe8  movff   WREG, (Common_RAM + 5)               ; reg1: 0xfe8, reg2: 0x005
003f7a:  f005
003f7c:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
003f7e:  0e2f  movlw   0x2f
003f80:  6405  cpfsgt  (Common_RAM + 5), A                  ; reg: 0x005
003f82:  d006  bra     label_509                            ; dest: 0x003f90
003f84:  0e3a  movlw   0x3a
003f86:  5c05  subwf   (Common_RAM + 5), W, A               ; reg: 0x005
003f88:  e203  bc      label_509
003f8a:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
003f8c:  0fd0  addlw   0xd0
003f8e:  d008  bra     label_510                            ; dest: 0x003fa0

label_509:                                                  ; address: 0x003f90

003f90:  0e40  movlw   0x40
003f92:  6405  cpfsgt  (Common_RAM + 5), A                  ; reg: 0x005
003f94:  d006  bra     label_511                            ; dest: 0x003fa2
003f96:  0e47  movlw   0x47
003f98:  5c05  subwf   (Common_RAM + 5), W, A               ; reg: 0x005
003f9a:  e203  bc      label_511
003f9c:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
003f9e:  0fc9  addlw   0xc9

label_510:                                                  ; address: 0x003fa0

003fa0:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004

label_511:                                                  ; address: 0x003fa2

003fa2:  3a04  swapf   (Common_RAM + 4), F, A               ; reg: 0x004
003fa4:  0ef0  movlw   0xf0
003fa6:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
003fa8:  0e2f  movlw   0x2f
003faa:  6403  cpfsgt  (Common_RAM + 3), A                  ; reg: 0x003
003fac:  d006  bra     label_512                            ; dest: 0x003fba
003fae:  0e3a  movlw   0x3a
003fb0:  5c03  subwf   (Common_RAM + 3), W, A               ; reg: 0x003
003fb2:  e203  bc      label_512
003fb4:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
003fb6:  0fd0  addlw   0xd0
003fb8:  d008  bra     label_513                            ; dest: 0x003fca

label_512:                                                  ; address: 0x003fba

003fba:  0e40  movlw   0x40
003fbc:  6403  cpfsgt  (Common_RAM + 3), A                  ; reg: 0x003
003fbe:  d006  bra     label_514                            ; dest: 0x003fcc
003fc0:  0e47  movlw   0x47
003fc2:  5c03  subwf   (Common_RAM + 3), W, A               ; reg: 0x003
003fc4:  e203  bc      label_514
003fc6:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
003fc8:  0fc9  addlw   0xc9

label_513:                                                  ; address: 0x003fca

003fca:  2604  addwf   (Common_RAM + 4), F, A               ; reg: 0x004

label_514:                                                  ; address: 0x003fcc

003fcc:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
003fce:  0012  return  0x0

function_060:                                               ; address: 0x003fd0

003fd0:  0e40  movlw   0x40
003fd2:  6405  cpfsgt  (Common_RAM + 5), A                  ; reg: 0x005
003fd4:  d001  bra     label_515                            ; dest: 0x003fd8
003fd6:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005

label_515:                                                  ; address: 0x003fd8

003fd8:  6a07  clrf    (Common_RAM + 7), A                  ; reg: 0x007
003fda:  d00f  bra     label_517                            ; dest: 0x003ffa

label_516:                                                  ; address: 0x003fdc

003fdc:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
003fde:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
003fe0:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
003fe2:  0e00  movlw   0x00
003fe4:  2004  addwfc  (Common_RAM + 4), W, A               ; reg: 0x004
003fe6:  6eda  movwf   FSR2H, A                             ; reg: 0xfda
003fe8:  0e6c  movlw   0x6c
003fea:  2407  addwf   (Common_RAM + 7), W, A               ; reg: 0x007
003fec:  6ee1  movwf   FSR1L, A                             ; reg: 0xfe1
003fee:  6ae2  clrf    FSR1H, A                             ; reg: 0xfe2
003ff0:  0e04  movlw   0x04
003ff2:  22e2  addwfc  FSR1H, F, A                          ; reg: 0xfe2
003ff4:  cfdf  movff   INDF2, INDF1                         ; reg1: 0xfdf, reg2: 0xfe7
003ff6:  ffe7
003ff8:  2a07  incf    (Common_RAM + 7), F, A               ; reg: 0x007

label_517:                                                  ; address: 0x003ffa

003ffa:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
003ffc:  5c07  subwf   (Common_RAM + 7), W, A               ; reg: 0x007
003ffe:  e3ee  bnc     label_516
004000:  c005  movff   (Common_RAM + 5), 0x411              ; reg1: 0x005
004002:  f411
004004:  0e40  movlw   0x40
004006:  0104  movlb   0x4
004008:  1710  andwf   0x10, F, B                           ; reg: 0x410
00400a:  0e01  movlw   0x01
00400c:  bd10  btfsc   0x10, 0x6, B                         ; reg: 0x410
00400e:  0e00  movlw   0x00
004010:  6e06  movwf   0x06, A                              ; reg: 0x406
004012:  3a06  swapf   0x06, F, A                           ; reg: 0x406
004014:  4606  rlncf   0x06, F, A                           ; reg: 0x406
004016:  4606  rlncf   0x06, F, A                           ; reg: 0x406
004018:  5110  movf    0x10, W, B                           ; reg: 0x410
00401a:  1806  xorwf   0x06, W, A                           ; reg: 0x406
00401c:  0bbf  andlw   0xbf
00401e:  1806  xorwf   0x06, W, A                           ; reg: 0x406
004020:  6f10  movwf   0x10, B                              ; reg: 0x410
004022:  8710  bsf     0x10, 0x3, B                         ; reg: 0x410
004024:  8f10  bsf     0x10, 0x7, B                         ; reg: 0x410
004026:  0012  return  0x0

function_061:                                               ; address: 0x004028

004028:  c003  movff   (Common_RAM + 3), (Common_RAM + 11)  ; reg1: 0x003, reg2: 0x00b
00402a:  f00b
00402c:  c004  movff   (Common_RAM + 4), (Common_RAM + 12)  ; reg1: 0x004, reg2: 0x00c
00402e:  f00c
004030:  c005  movff   (Common_RAM + 5), (Common_RAM + 13)  ; reg1: 0x005, reg2: 0x00d
004032:  f00d
004034:  c006  movff   (Common_RAM + 6), (Common_RAM + 14)  ; reg1: 0x006, reg2: 0x00e
004036:  f00e
004038:  cff8  movff   TBLPTRU, (Common_RAM + 17)           ; reg1: 0xff8, reg2: 0x011
00403a:  f011
00403c:  cff7  movff   TBLPTRH, (Common_RAM + 16)           ; reg1: 0xff7, reg2: 0x010
00403e:  f010
004040:  cff6  movff   TBLPTRL, (Common_RAM + 15)           ; reg1: 0xff6, reg2: 0x00f
004042:  f00f
004044:  c00d  movff   (Common_RAM + 13), TBLPTRU           ; reg1: 0x00d, reg2: 0xff8
004046:  fff8
004048:  c00c  movff   (Common_RAM + 12), TBLPTRH           ; reg1: 0x00c, reg2: 0xff7
00404a:  fff7
00404c:  c00b  movff   (Common_RAM + 11), TBLPTRL           ; reg1: 0x00b, reg2: 0xff6
00404e:  fff6
004050:  d009  bra     label_519                            ; dest: 0x004064

label_518:                                                  ; address: 0x004052

004052:  0009  tblrd*+
004054:  c009  movff   (Common_RAM + 9), FSR2L              ; reg1: 0x009, reg2: 0xfd9
004056:  ffd9
004058:  c00a  movff   (Common_RAM + 10), FSR2H             ; reg1: 0x00a, reg2: 0xfda
00405a:  ffda
00405c:  cff5  movff   TABLAT, INDF2                        ; reg1: 0xff5, reg2: 0xfdf
00405e:  ffdf
004060:  4a09  infsnz  (Common_RAM + 9), F, A               ; reg: 0x009
004062:  2a0a  incf    (Common_RAM + 10), F, A              ; reg: 0x00a

label_519:                                                  ; address: 0x004064

004064:  0607  decf    (Common_RAM + 7), F, A               ; reg: 0x007
004066:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
004068:  0608  decf    (Common_RAM + 8), F, A               ; reg: 0x008
00406a:  2807  incf    (Common_RAM + 7), W, A               ; reg: 0x007
00406c:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
00406e:  2808  incf    (Common_RAM + 8), W, A               ; reg: 0x008
004070:  e1f0  bnz     label_518
004072:  c011  movff   (Common_RAM + 17), TBLPTRU           ; reg1: 0x011, reg2: 0xff8
004074:  fff8
004076:  c010  movff   (Common_RAM + 16), TBLPTRH           ; reg1: 0x010, reg2: 0xff7
004078:  fff7
00407a:  c00f  movff   (Common_RAM + 15), TBLPTRL           ; reg1: 0x00f, reg2: 0xff6
00407c:  fff6
00407e:  0012  return  0x0

function_062:                                               ; address: 0x004080

004080:  cfe8  movff   WREG, (Common_RAM + 3)               ; reg1: 0xfe8, reg2: 0x003
004082:  f003
004084:  0e08  movlw   0x08
004086:  0101  movlb   0x1
004088:  6f17  movwf   0x17, B                              ; reg: 0x117
00408a:  0e04  movlw   0x04
00408c:  6f19  movwf   0x19, B                              ; reg: 0x119
00408e:  0e1c  movlw   0x1c
004090:  6f18  movwf   0x18, B                              ; reg: 0x118
004092:  6603  tstfsz  0x03, A                              ; reg: 0x103
004094:  d009  bra     label_520                            ; dest: 0x0040a8
004096:  0e04  movlw   0x04
004098:  6f19  movwf   (Common_RAM + 25), B                 ; reg: 0x019
00409a:  0e14  movlw   0x14
00409c:  6f18  movwf   (Common_RAM + 24), B                 ; reg: 0x018
00409e:  0e04  movlw   0x04
0040a0:  0100  movlb   0x0
0040a2:  6f79  movwf   0x79, B                              ; reg: 0x079
0040a4:  0e00  movlw   0x00
0040a6:  d003  bra     label_521                            ; dest: 0x0040ae

label_520:                                                  ; address: 0x0040a8

0040a8:  0e04  movlw   0x04
0040aa:  0100  movlb   0x0
0040ac:  6f79  movwf   0x79, B                              ; reg: 0x079

label_521:                                                  ; address: 0x0040ae

0040ae:  6f78  movwf   0x78, B                              ; reg: 0x078
0040b0:  c078  movff   0x078, FSR2L                         ; reg2: 0xfd9
0040b2:  ffd9
0040b4:  c079  movff   0x079, FSR2H                         ; reg2: 0xfda
0040b6:  ffda
0040b8:  c116  movff   0x116, POSTINC2                      ; reg2: 0xfde
0040ba:  ffde
0040bc:  c117  movff   0x117, POSTINC2                      ; reg2: 0xfde
0040be:  ffde
0040c0:  c118  movff   0x118, POSTINC2                      ; reg2: 0xfde
0040c2:  ffde
0040c4:  c119  movff   0x119, POSTINC2                      ; reg2: 0xfde
0040c6:  ffde
0040c8:  c078  movff   0x078, FSR2L                         ; reg2: 0xfd9
0040ca:  ffd9
0040cc:  c079  movff   0x079, FSR2H                         ; reg2: 0xfda
0040ce:  ffda
0040d0:  0100  movlb   0x0
0040d2:  8edf  bsf     INDF2, 0x7, A                        ; reg: 0xfdf
0040d4:  0012  return  0x0

function_063:                                               ; address: 0x0040d6

0040d6:  0e03  movlw   0x03
0040d8:  0100  movlb   0x0
0040da:  6fcd  movwf   0xcd, B                              ; reg: 0x0cd
0040dc:  6a6b  clrf    UEIE, A                              ; reg: 0xf6b
0040de:  6a68  clrf    UIR, A                               ; reg: 0xf68
0040e0:  0e7b  movlw   0x7b
0040e2:  6e69  movwf   UIE, A                               ; reg: 0xf69
0040e4:  6a6e  clrf    UADDR, A                             ; reg: 0xf6e
0040e6:  6a71  clrf    UEP1, A                              ; reg: 0xf71
0040e8:  6a72  clrf    UEP2, A                              ; reg: 0xf72
0040ea:  6a73  clrf    UEP3, A                              ; reg: 0xf73
0040ec:  6a74  clrf    UEP4, A                              ; reg: 0xf74
0040ee:  6a75  clrf    UEP5, A                              ; reg: 0xf75
0040f0:  6a76  clrf    UEP6, A                              ; reg: 0xf76
0040f2:  6a77  clrf    UEP7, A                              ; reg: 0xf77
0040f4:  0e16  movlw   0x16
0040f6:  6e70  movwf   UEP0, A                              ; reg: 0xf70
0040f8:  8c6d  bsf     UCON, PPBRST, A                      ; reg: 0xf6d, bit: 6
0040fa:  d003  bra     label_523                            ; dest: 0x004102

label_522:                                                  ; address: 0x0040fc

0040fc:  9668  bcf     UIR, TRNIF, A                        ; reg: 0xf68, bit: 3
0040fe:  ecb1  call    function_127, 0x0                    ; dest: 0x004962
004100:  f024

label_523:                                                  ; address: 0x004102

004102:  b668  btfsc   UIR, TRNIF, A                        ; reg: 0xf68, bit: 3
004104:  d7fb  bra     label_522                            ; dest: 0x0040fc
004106:  9c6d  bcf     UCON, PPBRST, A                      ; reg: 0xf6d, bit: 6
004108:  986d  bcf     UCON, PKTDIS, A                      ; reg: 0xf6d, bit: 4
00410a:  0e04  movlw   0x04
00410c:  0101  movlb   0x1
00410e:  6f16  movwf   0x16, B                              ; reg: 0x116
004110:  0e00  movlw   0x00
004112:  ec40  call    function_062, 0x0                    ; dest: 0x004080
004114:  f020
004116:  0e01  movlw   0x01
004118:  6f96  movwf   0x96, B                              ; reg: 0x096
00411a:  6bce  clrf    0xce, B                              ; reg: 0x0ce
00411c:  6beb  clrf    0xeb, B                              ; reg: 0x0eb
00411e:  0e00  movlw   0x00
004120:  ef7f  goto    function_117                         ; dest: 0x0048fe
004122:  f024

function_064:                                               ; address: 0x004124

004124:  6a07  clrf    (Common_RAM + 7), A                  ; reg: 0x007
004126:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
004128:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
00412a:  1005  iorwf   (Common_RAM + 5), W, A               ; reg: 0x005
00412c:  e01b  bz      label_528
00412e:  0e01  movlw   0x01
004130:  6e09  movwf   (Common_RAM + 9), A                  ; reg: 0x009
004132:  d004  bra     label_525                            ; dest: 0x00413c

label_524:                                                  ; address: 0x004134

004134:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
004136:  3605  rlcf    (Common_RAM + 5), F, A               ; reg: 0x005
004138:  3606  rlcf    (Common_RAM + 6), F, A               ; reg: 0x006
00413a:  2a09  incf    (Common_RAM + 9), F, A               ; reg: 0x009

label_525:                                                  ; address: 0x00413c

00413c:  ae06  btfss   (Common_RAM + 6), 0x7, A             ; reg: 0x006
00413e:  d7fa  bra     label_524                            ; dest: 0x004134

label_526:                                                  ; address: 0x004140

004140:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
004142:  3607  rlcf    (Common_RAM + 7), F, A               ; reg: 0x007
004144:  3608  rlcf    (Common_RAM + 8), F, A               ; reg: 0x008
004146:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
004148:  5c03  subwf   (Common_RAM + 3), W, A               ; reg: 0x003
00414a:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
00414c:  5804  subwfb  (Common_RAM + 4), W, A               ; reg: 0x004
00414e:  e305  bnc     label_527
004150:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
004152:  5e03  subwf   (Common_RAM + 3), F, A               ; reg: 0x003
004154:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
004156:  5a04  subwfb  (Common_RAM + 4), F, A               ; reg: 0x004
004158:  8007  bsf     (Common_RAM + 7), 0x0, A             ; reg: 0x007

label_527:                                                  ; address: 0x00415a

00415a:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
00415c:  3206  rrcf    (Common_RAM + 6), F, A               ; reg: 0x006
00415e:  3205  rrcf    (Common_RAM + 5), F, A               ; reg: 0x005
004160:  2e09  decfsz  (Common_RAM + 9), F, A               ; reg: 0x009
004162:  d7ee  bra     label_526                            ; dest: 0x004140

label_528:                                                  ; address: 0x004164

004164:  c007  movff   (Common_RAM + 7), (Common_RAM + 3)   ; reg1: 0x007, reg2: 0x003
004166:  f003
004168:  c008  movff   (Common_RAM + 8), (Common_RAM + 4)   ; reg1: 0x008, reg2: 0x004
00416a:  f004
00416c:  0012  return  0x0

label_529:                                                  ; address: 0x00416e

00416e:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
004170:  d021  bra     label_532                            ; dest: 0x0041b4
004172:  51a1  movf    0xa1, W, B                           ; reg: 0x0a1
004174:  0a64  xorlw   0x64
004176:  e11d  bnz     label_531
004178:  b2c2  btfsc   ADCON0, GO, A                        ; reg: 0xfc2, bit: 1
00417a:  d019  bra     label_530                            ; dest: 0x0041ae
00417c:  50c4  movf    ADRESH, W, A                         ; reg: 0xfc4
00417e:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
004180:  6a03  clrf    (Common_RAM + 3), A                  ; reg: 0x003
004182:  50c3  movf    ADRESL, W, A                         ; reg: 0xfc3
004184:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
004186:  6f88  movwf   0x88, B                              ; reg: 0x088
004188:  0e00  movlw   0x00
00418a:  2004  addwfc  (Common_RAM + 4), W, A               ; reg: 0x004
00418c:  6f89  movwf   0x89, B                              ; reg: 0x089
00418e:  0e29  movlw   0x29
004190:  5d88  subwf   0x88, W, B                           ; reg: 0x088
004192:  0e02  movlw   0x02
004194:  5989  subwfb  0x89, W, B                           ; reg: 0x089
004196:  b0d8  btfsc   STATUS, C, A                         ; reg: 0xfd8, bit: 0
004198:  8594  bsf     0x94, 0x2, B                         ; reg: 0x094
00419a:  82c2  bsf     ADCON0, GO, A                        ; reg: 0xfc2, bit: 1
00419c:  a594  btfss   0x94, 0x2, B                         ; reg: 0x094
00419e:  d007  bra     label_530                            ; dest: 0x0041ae
0041a0:  0e28  movlw   0x28
0041a2:  5d88  subwf   0x88, W, B                           ; reg: 0x088
0041a4:  0e02  movlw   0x02
0041a6:  5989  subwfb  0x89, W, B                           ; reg: 0x089
0041a8:  e202  bc      label_530
0041aa:  965e  bcf     (Common_RAM + 94), 0x3, A            ; reg: 0x05e
0041ac:  857e  bsf     0x7e, 0x2, B                         ; reg: 0x07e

label_530:                                                  ; address: 0x0041ae

0041ae:  6ba1  clrf    0xa1, B                              ; reg: 0x0a1
0041b0:  d001  bra     label_532                            ; dest: 0x0041b4

label_531:                                                  ; address: 0x0041b2

0041b2:  2ba1  incf    0xa1, F, B                           ; reg: 0x0a1

label_532:                                                  ; address: 0x0041b4

0041b4:  0012  return  0x0

function_065:                                               ; address: 0x0041b6

0041b6:  cfe8  movff   WREG, (Common_RAM + 23)              ; reg1: 0xfe8, reg2: 0x017
0041b8:  f017
0041ba:  c017  movff   (Common_RAM + 23), (Common_RAM + 22) ; reg1: 0x017, reg2: 0x016
0041bc:  f016
0041be:  5013  movf    (Common_RAM + 19), W, A              ; reg: 0x013
0041c0:  0a80  xorlw   0x80
0041c2:  6ef3  movwf   PRODL, A                             ; reg: 0xff3
0041c4:  0e80  movlw   0x80
0041c6:  5cf3  subwf   PRODL, W, A                          ; reg: 0xff3
0041c8:  0e00  movlw   0x00
0041ca:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0041cc:  5c12  subwf   (Common_RAM + 18), W, A              ; reg: 0x012
0041ce:  e20a  bc      label_533
0041d0:  5017  movf    (Common_RAM + 23), W, A              ; reg: 0x017
0041d2:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0041d4:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
0041d6:  0e2d  movlw   0x2d
0041d8:  6edf  movwf   INDF2, A                             ; reg: 0xfdf
0041da:  2a17  incf    (Common_RAM + 23), F, A              ; reg: 0x017
0041dc:  6c12  negf    (Common_RAM + 18), A                 ; reg: 0x012
0041de:  1e13  comf    (Common_RAM + 19), F, A              ; reg: 0x013
0041e0:  b0d8  btfsc   STATUS, C, A                         ; reg: 0xfd8, bit: 0
0041e2:  2a13  incf    (Common_RAM + 19), F, A              ; reg: 0x013

label_533:                                                  ; address: 0x0041e4

0041e4:  c012  movff   (Common_RAM + 18), (Common_RAM + 10) ; reg1: 0x012, reg2: 0x00a
0041e6:  f00a
0041e8:  c013  movff   (Common_RAM + 19), (Common_RAM + 11) ; reg1: 0x013, reg2: 0x00b
0041ea:  f00b
0041ec:  c014  movff   (Common_RAM + 20), (Common_RAM + 12) ; reg1: 0x014, reg2: 0x00c
0041ee:  f00c
0041f0:  c015  movff   (Common_RAM + 21), (Common_RAM + 13) ; reg1: 0x015, reg2: 0x00d
0041f2:  f00d
0041f4:  5017  movf    (Common_RAM + 23), W, A              ; reg: 0x017
0041f6:  ec64  call    function_034, 0x0                    ; dest: 0x0034c8
0041f8:  f01a
0041fa:  5016  movf    (Common_RAM + 22), W, A              ; reg: 0x016
0041fc:  0012  return  0x0

function_066:                                               ; address: 0x0041fe

0041fe:  0e01  movlw   0x01
004200:  6fc8  movwf   0xc8, B                              ; reg: 0x0c8
004202:  6a71  clrf    UEP1, A                              ; reg: 0xf71
004204:  6a72  clrf    UEP2, A                              ; reg: 0xf72
004206:  6a73  clrf    UEP3, A                              ; reg: 0xf73
004208:  6a74  clrf    UEP4, A                              ; reg: 0xf74
00420a:  6a75  clrf    UEP5, A                              ; reg: 0xf75
00420c:  6a76  clrf    UEP6, A                              ; reg: 0xf76
00420e:  6a77  clrf    UEP7, A                              ; reg: 0xf77
004210:  6b91  clrf    0x91, B                              ; reg: 0x091

label_534:                                                  ; address: 0x004212

004212:  5191  movf    0x91, W, B                           ; reg: 0x091
004214:  0fec  addlw   0xec
004216:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
004218:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00421a:  6adf  clrf    INDF2, A                             ; reg: 0xfdf
00421c:  2b91  incf    0x91, F, B                           ; reg: 0x091
00421e:  5191  movf    0x91, W, B                           ; reg: 0x091
004220:  e0f8  bz      label_534
004222:  c0d1  movff   0x0d1, 0x0eb
004224:  f0eb
004226:  51eb  movf    0xeb, W, B                           ; reg: 0x0eb
004228:  ec7f  call    function_117, 0x0                    ; dest: 0x0048fe
00422a:  f024
00422c:  0100  movlb   0x0
00422e:  67d1  tstfsz  0xd1, B                              ; reg: 0x0d1
004230:  d002  bra     label_535                            ; dest: 0x004236
004232:  0e05  movlw   0x05
004234:  d001  bra     label_536                            ; dest: 0x004238

label_535:                                                  ; address: 0x004236

004236:  0e06  movlw   0x06

label_536:                                                  ; address: 0x004238

004238:  6fcd  movwf   0xcd, B                              ; reg: 0x0cd
00423a:  0012  return  0x0

function_067:                                               ; address: 0x00423c

00423c:  cfe8  movff   WREG, (Common_RAM + 6)               ; reg1: 0xfe8, reg2: 0x006
00423e:  f006
004240:  ec5b  call    function_113, 0x0                    ; dest: 0x0048b6
004242:  f024
004244:  80c5  bsf     SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0

label_537:                                                  ; address: 0x004246

004246:  b0c5  btfsc   SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0
004248:  d7fe  bra     label_537                            ; dest: 0x004246
00424a:  0ee2  movlw   0xe2
00424c:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
00424e:  f01f
004250:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
004252:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
004254:  f01f
004256:  82c5  bsf     SSPCON2, RSEN, A                     ; reg: 0xfc5, bit: 1

label_538:                                                  ; address: 0x004258

004258:  b2c5  btfsc   SSPCON2, RSEN, A                     ; reg: 0xfc5, bit: 1
00425a:  d7fe  bra     label_538                            ; dest: 0x004258
00425c:  0ee3  movlw   0xe3
00425e:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
004260:  f01f
004262:  ec26  call    function_089, 0x0                    ; dest: 0x00464c
004264:  f023
004266:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
004268:  8ac5  bsf     SSPCON2, ACKDT, A                    ; reg: 0xfc5, bit: 5
00426a:  88c5  bsf     SSPCON2, ACKEN, A                    ; reg: 0xfc5, bit: 4

label_539:                                                  ; address: 0x00426c

00426c:  b8c5  btfsc   SSPCON2, ACKEN, A                    ; reg: 0xfc5, bit: 4
00426e:  d7fe  bra     label_539                            ; dest: 0x00426c
004270:  84c5  bsf     SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2

label_540:                                                  ; address: 0x004272

004272:  b4c5  btfsc   SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2
004274:  d7fe  bra     label_540                            ; dest: 0x004272
004276:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
004278:  0012  return  0x0

function_068:                                               ; address: 0x00427a

00427a:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
00427c:  1005  iorwf   (Common_RAM + 5), W, A               ; reg: 0x005
00427e:  e017  bz      label_545
004280:  0e01  movlw   0x01
004282:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
004284:  d004  bra     label_542                            ; dest: 0x00428e

label_541:                                                  ; address: 0x004286

004286:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
004288:  3605  rlcf    (Common_RAM + 5), F, A               ; reg: 0x005
00428a:  3606  rlcf    (Common_RAM + 6), F, A               ; reg: 0x006
00428c:  2a07  incf    (Common_RAM + 7), F, A               ; reg: 0x007

label_542:                                                  ; address: 0x00428e

00428e:  ae06  btfss   (Common_RAM + 6), 0x7, A             ; reg: 0x006
004290:  d7fa  bra     label_541                            ; dest: 0x004286

label_543:                                                  ; address: 0x004292

004292:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
004294:  5c03  subwf   (Common_RAM + 3), W, A               ; reg: 0x003
004296:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
004298:  5804  subwfb  (Common_RAM + 4), W, A               ; reg: 0x004
00429a:  e304  bnc     label_544
00429c:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
00429e:  5e03  subwf   (Common_RAM + 3), F, A               ; reg: 0x003
0042a0:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
0042a2:  5a04  subwfb  (Common_RAM + 4), F, A               ; reg: 0x004

label_544:                                                  ; address: 0x0042a4

0042a4:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
0042a6:  3206  rrcf    (Common_RAM + 6), F, A               ; reg: 0x006
0042a8:  3205  rrcf    (Common_RAM + 5), F, A               ; reg: 0x005
0042aa:  2e07  decfsz  (Common_RAM + 7), F, A               ; reg: 0x007
0042ac:  d7f2  bra     label_543                            ; dest: 0x004292

label_545:                                                  ; address: 0x0042ae

0042ae:  c003  movff   (Common_RAM + 3), (Common_RAM + 3)   ; reg1: 0x003, reg2: 0x003
0042b0:  f003
0042b2:  c004  movff   (Common_RAM + 4), (Common_RAM + 4)   ; reg1: 0x004, reg2: 0x004
0042b4:  f004
0042b6:  0012  return  0x0

function_069:                                               ; address: 0x0042b8

0042b8:  9ef2  bcf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
0042ba:  0e30  movlw   0x30
0042bc:  6ef8  movwf   TBLPTRU, A                           ; reg: 0xff8
0042be:  6af7  clrf    TBLPTRH, A                           ; reg: 0xff7
0042c0:  0e0b  movlw   0x0b
0042c2:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
0042c4:  0ea0  movlw   0xa0
0042c6:  6ef5  movwf   TABLAT, A                            ; reg: 0xff5
0042c8:  000c  tblwt*
0042ca:  0ec4  movlw   0xc4
0042cc:  6ea6  movwf   EECON1, A                            ; reg: 0xfa6
0042ce:  ec03  call    function_076, 0x0                    ; dest: 0x004406
0042d0:  f022

label_546:                                                  ; address: 0x0042d2

0042d2:  b2a6  btfsc   EECON1, WR, A                        ; reg: 0xfa6, bit: 1
0042d4:  d7fe  bra     label_546                            ; dest: 0x0042d2
0042d6:  0e30  movlw   0x30
0042d8:  6ef8  movwf   TBLPTRU, A                           ; reg: 0xff8
0042da:  6af7  clrf    TBLPTRH, A                           ; reg: 0xff7
0042dc:  6af6  clrf    TBLPTRL, A                           ; reg: 0xff6
0042de:  0e3a  movlw   0x3a
0042e0:  6ef5  movwf   TABLAT, A                            ; reg: 0xff5
0042e2:  000c  tblwt*
0042e4:  0ec4  movlw   0xc4
0042e6:  6ea6  movwf   EECON1, A                            ; reg: 0xfa6
0042e8:  ec03  call    function_076, 0x0                    ; dest: 0x004406
0042ea:  f022

label_547:                                                  ; address: 0x0042ec

0042ec:  b2a6  btfsc   EECON1, WR, A                        ; reg: 0xfa6, bit: 1
0042ee:  d7fe  bra     label_547                            ; dest: 0x0042ec
0042f0:  94a6  bcf     EECON1, WREN, A                      ; reg: 0xfa6, bit: 2
0042f2:  0012  return  0x0

function_070:                                               ; address: 0x0042f4

0042f4:  0104  movlb   0x4
0042f6:  6b08  clrf    0x08, B                              ; reg: 0x408
0042f8:  0100  movlb   0x0
0042fa:  6bcc  clrf    0xcc, B                              ; reg: 0x0cc
0042fc:  0104  movlb   0x4
0042fe:  af00  btfss   0x00, 0x7, B                         ; reg: 0x400
004300:  d003  bra     label_548                            ; dest: 0x004308
004302:  6b00  clrf    Common_RAM, B                        ; reg: 0x000
004304:  0100  movlb   0x0
004306:  6b96  clrf    0x96, B                              ; reg: 0x096

label_548:                                                  ; address: 0x004308

004308:  0104  movlb   0x4
00430a:  af04  btfss   0x04, 0x7, B                         ; reg: 0x404
00430c:  d004  bra     label_549                            ; dest: 0x004316
00430e:  6b04  clrf    (Common_RAM + 4), B                  ; reg: 0x004
004310:  0e01  movlw   0x01
004312:  0100  movlb   0x0
004314:  6f96  movwf   0x96, B                              ; reg: 0x096

label_549:                                                  ; address: 0x004316

004316:  0100  movlb   0x0
004318:  6bc9  clrf    0xc9, B                              ; reg: 0x0c9
00431a:  6bc8  clrf    0xc8, B                              ; reg: 0x0c8
00431c:  6be7  clrf    0xe7, B                              ; reg: 0x0e7
00431e:  6be8  clrf    0xe8, B                              ; reg: 0x0e8
004320:  986d  bcf     UCON, PKTDIS, A                      ; reg: 0xf6d, bit: 4
004322:  ec41  call    function_039, 0x0                    ; dest: 0x003682
004324:  f01b
004326:  ecad  call    function_125, 0x0                    ; dest: 0x00495a
004328:  f024
00432a:  ef26  goto    label_400                            ; dest: 0x00324c
00432c:  f019

function_071:                                               ; address: 0x00432e

00432e:  0e80  movlw   0x80
004330:  1a40  xorwf   (Common_RAM + 64), F, A              ; reg: 0x040
004332:  c039  movff   (Common_RAM + 57), (Common_RAM + 32) ; reg1: 0x039, reg2: 0x020
004334:  f020
004336:  c03a  movff   (Common_RAM + 58), (Common_RAM + 33) ; reg1: 0x03a, reg2: 0x021
004338:  f021
00433a:  c03b  movff   (Common_RAM + 59), (Common_RAM + 34) ; reg1: 0x03b, reg2: 0x022
00433c:  f022
00433e:  c03c  movff   (Common_RAM + 60), (Common_RAM + 35) ; reg1: 0x03c, reg2: 0x023
004340:  f023
004342:  c03d  movff   (Common_RAM + 61), (Common_RAM + 36) ; reg1: 0x03d, reg2: 0x024
004344:  f024
004346:  c03e  movff   (Common_RAM + 62), (Common_RAM + 37) ; reg1: 0x03e, reg2: 0x025
004348:  f025
00434a:  c03f  movff   (Common_RAM + 63), (Common_RAM + 38) ; reg1: 0x03f, reg2: 0x026
00434c:  f026
00434e:  c040  movff   (Common_RAM + 64), (Common_RAM + 39) ; reg1: 0x040, reg2: 0x027
004350:  f027
004352:  ec61  call    function_011, 0x0                    ; dest: 0x0024c2
004354:  f012
004356:  c020  movff   (Common_RAM + 32), (Common_RAM + 57) ; reg1: 0x020, reg2: 0x039
004358:  f039
00435a:  c021  movff   (Common_RAM + 33), (Common_RAM + 58) ; reg1: 0x021, reg2: 0x03a
00435c:  f03a
00435e:  c022  movff   (Common_RAM + 34), (Common_RAM + 59) ; reg1: 0x022, reg2: 0x03b
004360:  f03b
004362:  c023  movff   (Common_RAM + 35), (Common_RAM + 60) ; reg1: 0x023, reg2: 0x03c
004364:  f03c
004366:  0012  return  0x0

function_072:                                               ; address: 0x004368

004368:  cfe8  movff   WREG, (Common_RAM + 6)               ; reg1: 0xfe8, reg2: 0x006
00436a:  f006
00436c:  ec5b  call    function_113, 0x0                    ; dest: 0x0048b6
00436e:  f024
004370:  80c5  bsf     SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0

label_550:                                                  ; address: 0x004372

004372:  b0c5  btfsc   SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0
004374:  d7fe  bra     label_550                            ; dest: 0x004372
004376:  0e68  movlw   0x68
004378:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
00437a:  f01f
00437c:  0e1f  movlw   0x1f
00437e:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
004380:  f01f
004382:  0e00  movlw   0x00
004384:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
004386:  f01f
004388:  0e00  movlw   0x00
00438a:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
00438c:  f01f
00438e:  0e00  movlw   0x00
004390:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
004392:  f01f
004394:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
004396:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
004398:  f01f
00439a:  84c5  bsf     SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2

label_551:                                                  ; address: 0x00439c

00439c:  a4c5  btfss   SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2
00439e:  0012  return  0x0
0043a0:  d7fd  bra     label_551                            ; dest: 0x00439c

function_073:                                               ; address: 0x0043a2

0043a2:  cfe8  movff   WREG, (Common_RAM + 6)               ; reg1: 0xfe8, reg2: 0x006
0043a4:  f006
0043a6:  c006  movff   (Common_RAM + 6), (Common_RAM + 4)   ; reg1: 0x006, reg2: 0x004
0043a8:  f004
0043aa:  3a04  swapf   (Common_RAM + 4), F, A               ; reg: 0x004
0043ac:  0e0f  movlw   0x0f
0043ae:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
0043b0:  d80b  rcall   function_074                         ; dest: 0x0043c8
0043b2:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0043b4:  f024
0043b6:  6e05  movwf   (Common_RAM + 5), A                  ; reg: 0x005
0043b8:  c006  movff   (Common_RAM + 6), (Common_RAM + 4)   ; reg1: 0x006, reg2: 0x004
0043ba:  f004
0043bc:  0e0f  movlw   0x0f
0043be:  d804  rcall   function_074                         ; dest: 0x0043c8
0043c0:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0043c2:  f024
0043c4:  1a05  xorwf   (Common_RAM + 5), F, A               ; reg: 0x005
0043c6:  0012  return  0x0

function_074:                                               ; address: 0x0043c8

0043c8:  1604  andwf   (Common_RAM + 4), F, A               ; reg: 0x004
0043ca:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
0043cc:  0f19  addlw   0x19
0043ce:  6ef6  movwf   TBLPTRL, A                           ; reg: 0xff6
0043d0:  0e10  movlw   0x10
0043d2:  6ef7  movwf   TBLPTRH, A                           ; reg: 0xff7
0043d4:  0008  tblrd*
0043d6:  50f5  movf    TABLAT, W, A                         ; reg: 0xff5
0043d8:  0012  return  0x0

function_075:                                               ; address: 0x0043da

0043da:  c003  movff   (Common_RAM + 3), EEADR              ; reg1: 0x003, reg2: 0xfa9
0043dc:  ffa9
0043de:  c005  movff   (Common_RAM + 5), EEDATA             ; reg1: 0x005, reg2: 0xfa8
0043e0:  ffa8
0043e2:  9ea6  bcf     EECON1, EEPGD, A                     ; reg: 0xfa6, bit: 7
0043e4:  9ca6  bcf     EECON1, CFGS, A                      ; reg: 0xfa6, bit: 6
0043e6:  84a6  bsf     EECON1, WREN, A                      ; reg: 0xfa6, bit: 2
0043e8:  0e00  movlw   0x00
0043ea:  bef2  btfsc   INTCON, GIE, A                       ; reg: 0xff2, bit: 7
0043ec:  0e01  movlw   0x01
0043ee:  6e06  movwf   (Common_RAM + 6), A                  ; reg: 0x006
0043f0:  9ef2  bcf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
0043f2:  d809  rcall   function_076                         ; dest: 0x004406

label_552:                                                  ; address: 0x0043f4

0043f4:  b2a6  btfsc   EECON1, WR, A                        ; reg: 0xfa6, bit: 1
0043f6:  d7fe  bra     label_552                            ; dest: 0x0043f4
0043f8:  b006  btfsc   (Common_RAM + 6), 0x0, A             ; reg: 0x006
0043fa:  d002  bra     label_553                            ; dest: 0x004400
0043fc:  9ef2  bcf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7
0043fe:  d001  bra     label_554                            ; dest: 0x004402

label_553:                                                  ; address: 0x004400

004400:  8ef2  bsf     INTCON, GIE, A                       ; reg: 0xff2, bit: 7

label_554:                                                  ; address: 0x004402

004402:  94a6  bcf     EECON1, WREN, A                      ; reg: 0xfa6, bit: 2
004404:  0012  return  0x0

function_076:                                               ; address: 0x004406

004406:  0e55  movlw   0x55
004408:  6ea7  movwf   EECON2, A                            ; reg: 0xfa7
00440a:  0eaa  movlw   0xaa
00440c:  6ea7  movwf   EECON2, A                            ; reg: 0xfa7
00440e:  82a6  bsf     EECON1, WR, A                        ; reg: 0xfa6, bit: 1
004410:  0caa  retlw   0xaa

function_077:                                               ; address: 0x004412

004412:  51cd  movf    0xcd, W, B                           ; reg: 0x0cd
004414:  0a04  xorlw   0x04
004416:  e107  bnz     label_555
004418:  c0d1  movff   0x0d1, UADDR                         ; reg2: 0xf6e
00441a:  ff6e
00441c:  506e  movf    UADDR, W, A                          ; reg: 0xf6e
00441e:  0e05  movlw   0x05
004420:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
004422:  0e03  movlw   0x03
004424:  6fcd  movwf   0xcd, B                              ; reg: 0x0cd

label_555:                                                  ; address: 0x004426

004426:  05c9  decf    0xc9, W, B                           ; reg: 0x0c9
004428:  e10e  bnz     label_558
00442a:  ecf8  call    function_036, 0x0                    ; dest: 0x0035f0
00442c:  f01a
00442e:  51cc  movf    0xcc, W, B                           ; reg: 0x0cc
004430:  0a02  xorlw   0x02
004432:  e103  bnz     label_556
004434:  0e04  movlw   0x04
004436:  0104  movlb   0x4
004438:  d004  bra     label_557                            ; dest: 0x004442

label_556:                                                  ; address: 0x00443a

00443a:  0104  movlb   0x4
00443c:  0e48  movlw   0x48
00443e:  bd08  btfsc   0x08, 0x6, B                         ; reg: 0x408
004440:  0e08  movlw   0x08

label_557:                                                  ; address: 0x004442

004442:  6f08  movwf   (Common_RAM + 8), B                  ; reg: 0x008
004444:  8f08  bsf     (Common_RAM + 8), 0x7, B             ; reg: 0x008

label_558:                                                  ; address: 0x004446

004446:  0012  return  0x0

function_078:                                               ; address: 0x004448

004448:  cfe8  movff   WREG, (Common_RAM + 3)               ; reg1: 0xfe8, reg2: 0x003
00444a:  f003
00444c:  d00f  bra     label_564                            ; dest: 0x00446c

label_559:                                                  ; address: 0x00444e

00444e:  0e01  movlw   0x01
004450:  6fa0  movwf   0xa0, B                              ; reg: 0x0a0
004452:  6bb9  clrf    0xb9, B                              ; reg: 0x0b9
004454:  d013  bra     label_565                            ; dest: 0x00447c

label_560:                                                  ; address: 0x004456

004456:  6ba0  clrf    0xa0, B                              ; reg: 0x0a0
004458:  0e01  movlw   0x01
00445a:  d006  bra     label_563                            ; dest: 0x004468

label_561:                                                  ; address: 0x00445c

00445c:  0e02  movlw   0x02
00445e:  6fa0  movwf   0xa0, B                              ; reg: 0x0a0
004460:  d003  bra     label_563                            ; dest: 0x004468

label_562:                                                  ; address: 0x004462

004462:  0e01  movlw   0x01
004464:  6fa0  movwf   0xa0, B                              ; reg: 0x0a0
004466:  0e03  movlw   0x03

label_563:                                                  ; address: 0x004468

004468:  6fb9  movwf   0xb9, B                              ; reg: 0x0b9
00446a:  d008  bra     label_565                            ; dest: 0x00447c

label_564:                                                  ; address: 0x00446c

00446c:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
00446e:  e0ef  bz      label_559
004470:  0a01  xorlw   0x01
004472:  e0f1  bz      label_560
004474:  0a03  xorlw   0x03
004476:  e0f2  bz      label_561
004478:  0a01  xorlw   0x01
00447a:  e0f3  bz      label_562

label_565:                                                  ; address: 0x00447c

00447c:  0012  return  0x0

function_079:                                               ; address: 0x00447e

00447e:  92a0  bcf     PIE2, TMR3IE, A                      ; reg: 0xfa0, bit: 1
004480:  0e98  movlw   0x98
004482:  6eb1  movwf   T3CON, A                             ; reg: 0xfb1
004484:  80b1  bsf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
004486:  d010  bra     label_570                            ; dest: 0x0044a8

label_566:                                                  ; address: 0x004488

004488:  a2d3  btfss   OSCCON, SCS1, A                      ; reg: 0xfd3, bit: 1
00448a:  d004  bra     label_567                            ; dest: 0x004494
00448c:  0efc  movlw   0xfc
00448e:  6eb3  movwf   TMR3H, A                             ; reg: 0xfb3
004490:  0e18  movlw   0x18
004492:  d003  bra     label_568                            ; dest: 0x00449a

label_567:                                                  ; address: 0x004494

004494:  0ef8  movlw   0xf8
004496:  6eb3  movwf   TMR3H, A                             ; reg: 0xfb3
004498:  0e30  movlw   0x30

label_568:                                                  ; address: 0x00449a

00449a:  6eb2  movwf   TMR3L, A                             ; reg: 0xfb2
00449c:  92a1  bcf     PIR2, TMR3IF, A                      ; reg: 0xfa1, bit: 1

label_569:                                                  ; address: 0x00449e

00449e:  a2a1  btfss   PIR2, TMR3IF, A                      ; reg: 0xfa1, bit: 1
0044a0:  d7fe  bra     label_569                            ; dest: 0x00449e
0044a2:  0603  decf    (Common_RAM + 3), F, A               ; reg: 0x003
0044a4:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
0044a6:  0604  decf    (Common_RAM + 4), F, A               ; reg: 0x004

label_570:                                                  ; address: 0x0044a8

0044a8:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
0044aa:  1003  iorwf   (Common_RAM + 3), W, A               ; reg: 0x003
0044ac:  e1ed  bnz     label_566
0044ae:  90b1  bcf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
0044b0:  0012  return  0x0

function_080:                                               ; address: 0x0044b2

0044b2:  cfe8  movff   WREG, (Common_RAM + 27)              ; reg1: 0xfe8, reg2: 0x01b
0044b4:  f01b
0044b6:  0e0d  movlw   0x0d
0044b8:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0044ba:  f024
0044bc:  0e0a  movlw   0x0a
0044be:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0044c0:  f024
0044c2:  0e0c  movlw   0x0c
0044c4:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0044c6:  f024
0044c8:  0e3a  movlw   0x3a
0044ca:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0044cc:  f024
0044ce:  6a19  clrf    (Common_RAM + 25), A                 ; reg: 0x019
0044d0:  c01b  movff   (Common_RAM + 27), (Common_RAM + 24) ; reg1: 0x01b, reg2: 0x018
0044d2:  f018
0044d4:  ec4b  call    function_091, 0x0                    ; dest: 0x004696
0044d6:  f023
0044d8:  0e0d  movlw   0x0d
0044da:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
0044dc:  f024
0044de:  0e0a  movlw   0x0a
0044e0:  ef4b  goto    function_111                         ; dest: 0x004896
0044e2:  f024

function_081:                                               ; address: 0x0044e4

0044e4:  ec5b  call    function_113, 0x0                    ; dest: 0x0048b6
0044e6:  f024
0044e8:  80c5  bsf     SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0

label_571:                                                  ; address: 0x0044ea

0044ea:  b0c5  btfsc   SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0
0044ec:  d7fe  bra     label_571                            ; dest: 0x0044ea
0044ee:  0e68  movlw   0x68
0044f0:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
0044f2:  f01f
0044f4:  0e30  movlw   0x30
0044f6:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
0044f8:  f01f
0044fa:  c055  movff   (Common_RAM + 85), (Common_RAM + 73) ; reg1: 0x055, reg2: 0x049
0044fc:  f049
0044fe:  c056  movff   (Common_RAM + 86), (Common_RAM + 74) ; reg1: 0x056, reg2: 0x04a
004500:  f04a
004502:  c057  movff   (Common_RAM + 87), (Common_RAM + 75) ; reg1: 0x057, reg2: 0x04b
004504:  f04b
004506:  c058  movff   (Common_RAM + 88), (Common_RAM + 76) ; reg1: 0x058, reg2: 0x04c
004508:  f04c
00450a:  ecd3  call    function_046, 0x0                    ; dest: 0x0039a6
00450c:  f01c
00450e:  84c5  bsf     SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2

label_572:                                                  ; address: 0x004510

004510:  a4c5  btfss   SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2
004512:  0012  return  0x0
004514:  d7fd  bra     label_572                            ; dest: 0x004510

function_082:                                               ; address: 0x004516

004516:  665f  tstfsz  (Common_RAM + 95), A                 ; reg: 0x05f
004518:  d00d  bra     label_579                            ; dest: 0x004534

label_573:                                                  ; address: 0x00451a

00451a:  9689  bcf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3
00451c:  d001  bra     label_575                            ; dest: 0x004520

label_574:                                                  ; address: 0x00451e

00451e:  8689  bsf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3

label_575:                                                  ; address: 0x004520

004520:  9889  bcf     LATA, LATA4, A                       ; reg: 0xf89, bit: 4
004522:  9a89  bcf     LATA, LATA5, A                       ; reg: 0xf89, bit: 5
004524:  d00f  bra     label_580                            ; dest: 0x004544

label_576:                                                  ; address: 0x004526

004526:  9689  bcf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3
004528:  9889  bcf     LATA, LATA4, A                       ; reg: 0xf89, bit: 4
00452a:  d002  bra     label_578                            ; dest: 0x004530

label_577:                                                  ; address: 0x00452c

00452c:  9689  bcf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3
00452e:  8889  bsf     LATA, LATA4, A                       ; reg: 0xf89, bit: 4

label_578:                                                  ; address: 0x004530

004530:  8a89  bsf     LATA, LATA5, A                       ; reg: 0xf89, bit: 5
004532:  d008  bra     label_580                            ; dest: 0x004544

label_579:                                                  ; address: 0x004534

004534:  5193  movf    0x93, W, B                           ; reg: 0x093
004536:  e0f1  bz      label_573
004538:  0a05  xorlw   0x05
00453a:  e0f1  bz      label_574
00453c:  0a03  xorlw   0x03
00453e:  e0f3  bz      label_576
004540:  0a01  xorlw   0x01
004542:  e0f4  bz      label_577

label_580:                                                  ; address: 0x004544

004544:  0012  return  0x0

function_083:                                               ; address: 0x004546

004546:  9eab  bcf     RCSTA, SPEN, A                       ; reg: 0xfab, bit: 7
004548:  9ed0  bcf     RCON, IPEN, A                        ; reg: 0xfd0, bit: 7
00454a:  0100  movlb   0x0
00454c:  6bc6  clrf    0xc6, B                              ; reg: 0x0c6
00454e:  6bc7  clrf    0xc7, B                              ; reg: 0x0c7
004550:  0e06  movlw   0x06
004552:  6eac  movwf   TXSTA, A                             ; reg: 0xfac
004554:  0e80  movlw   0x80
004556:  6eab  movwf   RCSTA, A                             ; reg: 0xfab
004558:  0e48  movlw   0x48
00455a:  6eb8  movwf   BAUDCON, A                           ; reg: 0xfb8
00455c:  8e94  bsf     TRISC, RC7, A                        ; reg: 0xf94, bit: 7
00455e:  8c94  bsf     TRISC, RC6, A                        ; reg: 0xf94, bit: 6
004560:  989d  bcf     PIE1, TXIE, A                        ; reg: 0xf9d, bit: 4
004562:  989e  bcf     PIR1, TXIF, A                        ; reg: 0xf9e, bit: 4
004564:  9a9e  bcf     PIR1, RCIF, A                        ; reg: 0xf9e, bit: 5
004566:  9a9d  bcf     PIE1, RCIE, A                        ; reg: 0xf9d, bit: 5
004568:  6ab0  clrf    SPBRGH, A                            ; reg: 0xfb0
00456a:  0e7f  movlw   0x7f
00456c:  6eaf  movwf   SPBRG, A                             ; reg: 0xfaf
00456e:  8aac  bsf     TXSTA, TXEN, A                       ; reg: 0xfac, bit: 5
004570:  88ab  bsf     RCSTA, CREN, A                       ; reg: 0xfab, bit: 4
004572:  0c7f  retlw   0x7f

function_084:                                               ; address: 0x004574

004574:  0e56  movlw   0x56
004576:  6e33  movwf   (Common_RAM + 51), A                 ; reg: 0x033
004578:  0e00  movlw   0x00
00457a:  6a32  clrf    (Common_RAM + 50), A                 ; reg: 0x032
00457c:  6a34  clrf    (Common_RAM + 52), A                 ; reg: 0x034

label_581:                                                  ; address: 0x00457e

00457e:  c032  movff   (Common_RAM + 50), (Common_RAM + 19) ; reg1: 0x032, reg2: 0x013
004580:  f013
004582:  c033  movff   (Common_RAM + 51), (Common_RAM + 20) ; reg1: 0x033, reg2: 0x014
004584:  f014
004586:  ec0e  call    function_043, 0x0                    ; dest: 0x00381c
004588:  f01c
00458a:  0e18  movlw   0x18
00458c:  2632  addwf   (Common_RAM + 50), F, A              ; reg: 0x032
00458e:  0e00  movlw   0x00
004590:  2233  addwfc  (Common_RAM + 51), F, A              ; reg: 0x033
004592:  2a34  incf    (Common_RAM + 52), F, A              ; reg: 0x034
004594:  0e5f  movlw   0x5f
004596:  6434  cpfsgt  (Common_RAM + 52), A                 ; reg: 0x034
004598:  d7f2  bra     label_581                            ; dest: 0x00457e
00459a:  6e14  movwf   (Common_RAM + 20), A                 ; reg: 0x014
00459c:  6a13  clrf    (Common_RAM + 19), A                 ; reg: 0x013
00459e:  ef0e  goto    function_043                         ; dest: 0x00381c
0045a0:  f01c

function_085:                                               ; address: 0x0045a2

0045a2:  ec94  call    function_009, 0x0                    ; dest: 0x002328
0045a4:  f011
0045a6:  51cd  movf    0xcd, W, B                           ; reg: 0x0cd
0045a8:  0a06  xorlw   0x06
0045aa:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0045ac:  b26d  btfsc   UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
0045ae:  d00e  bra     label_582                            ; dest: 0x0045cc
0045b0:  a082  btfss   PORTC, RC0, A                        ; reg: 0xf82, bit: 0
0045b2:  d00c  bra     label_582                            ; dest: 0x0045cc
0045b4:  0104  movlb   0x4
0045b6:  bf10  btfsc   0x10, 0x7, B                         ; reg: 0x410
0045b8:  d009  bra     label_582                            ; dest: 0x0045cc
0045ba:  0101  movlb   0x1
0045bc:  0e01  movlw   0x01
0045be:  6e04  movwf   0x04, A                              ; reg: 0x104
0045c0:  0e5a  movlw   0x5a
0045c2:  6e03  movwf   0x03, A                              ; reg: 0x103
0045c4:  0e40  movlw   0x40
0045c6:  6e05  movwf   0x05, A                              ; reg: 0x105
0045c8:  ece8  call    function_060, 0x0                    ; dest: 0x003fd0
0045ca:  f01f

label_582:                                                  ; address: 0x0045cc

0045cc:  0012  return  0x0

function_086:                                               ; address: 0x0045ce

0045ce:  cfe8  movff   WREG, (Common_RAM + 17)              ; reg1: 0xfe8, reg2: 0x011
0045d0:  f011
0045d2:  5011  movf    (Common_RAM + 17), W, A              ; reg: 0x011
0045d4:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
0045d6:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
0045d8:  6a05  clrf    (Common_RAM + 5), A                  ; reg: 0x005
0045da:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
0045dc:  0e96  movlw   0x96
0045de:  6e07  movwf   (Common_RAM + 7), A                  ; reg: 0x007
0045e0:  0e00  movlw   0x00
0045e2:  6a08  clrf    (Common_RAM + 8), A                  ; reg: 0x008
0045e4:  ec6c  call    function_029, 0x0                    ; dest: 0x0030d8
0045e6:  f018
0045e8:  c003  movff   (Common_RAM + 3), (Common_RAM + 13)  ; reg1: 0x003, reg2: 0x00d
0045ea:  f00d
0045ec:  c004  movff   (Common_RAM + 4), (Common_RAM + 14)  ; reg1: 0x004, reg2: 0x00e
0045ee:  f00e
0045f0:  c005  movff   (Common_RAM + 5), (Common_RAM + 15)  ; reg1: 0x005, reg2: 0x00f
0045f2:  f00f
0045f4:  c006  movff   (Common_RAM + 6), (Common_RAM + 16)  ; reg1: 0x006, reg2: 0x010
0045f6:  f010
0045f8:  0012  return  0x0

function_087:                                               ; address: 0x0045fa

0045fa:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
0045fc:  ec39  call    function_109, 0x0                    ; dest: 0x004872
0045fe:  f024
004600:  0900  iorlw   0x00
004602:  e00e  bz      label_583
004604:  0e00  movlw   0x00
004606:  0100  movlb   0x0
004608:  25c6  addwf   0xc6, W, B                           ; reg: 0x0c6
00460a:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
00460c:  6ada  clrf    FSR2H, A                             ; reg: 0xfda
00460e:  0e02  movlw   0x02
004610:  22da  addwfc  FSR2H, F, A                          ; reg: 0xfda
004612:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
004614:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
004616:  2bc6  incf    0xc6, F, B                           ; reg: 0x0c6
004618:  0ebf  movlw   0xbf
00461a:  65c6  cpfsgt  0xc6, B                              ; reg: 0x0c6
00461c:  d001  bra     label_583                            ; dest: 0x004620
00461e:  6bc6  clrf    0xc6, B                              ; reg: 0x0c6

label_583:                                                  ; address: 0x004620

004620:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
004622:  0012  return  0x0

function_088:                                               ; address: 0x004624

004624:  6bca  clrf    0xca, B                              ; reg: 0x0ca
004626:  0e1e  movlw   0x1e
004628:  6e71  movwf   UEP1, A                              ; reg: 0xf71
00462a:  0e40  movlw   0x40
00462c:  0104  movlb   0x4
00462e:  6f0d  movwf   0x0d, B                              ; reg: 0x40d
004630:  0e04  movlw   0x04
004632:  6f0f  movwf   0x0f, B                              ; reg: 0x40f
004634:  0e2c  movlw   0x2c
004636:  6f0e  movwf   0x0e, B                              ; reg: 0x40e
004638:  0e08  movlw   0x08
00463a:  6f0c  movwf   0x0c, B                              ; reg: 0x40c
00463c:  8f0c  bsf     0x0c, 0x7, B                         ; reg: 0x40c
00463e:  0e04  movlw   0x04
004640:  6f13  movwf   0x13, B                              ; reg: 0x413
004642:  0e6c  movlw   0x6c
004644:  6f12  movwf   0x12, B                              ; reg: 0x412
004646:  0e40  movlw   0x40
004648:  6f10  movwf   0x10, B                              ; reg: 0x410
00464a:  0c40  retlw   0x40

function_089:                                               ; address: 0x00464c

00464c:  cfc6  movff   SSPCON1, (Common_RAM + 3)            ; reg1: 0xfc6, reg2: 0x003
00464e:  f003
004650:  0e0f  movlw   0x0f
004652:  1603  andwf   (Common_RAM + 3), F, A               ; reg: 0x003
004654:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
004656:  0a08  xorlw   0x08
004658:  e007  bz      label_584
00465a:  cfc6  movff   SSPCON1, (Common_RAM + 3)            ; reg1: 0xfc6, reg2: 0x003
00465c:  f003
00465e:  0e0f  movlw   0x0f
004660:  1603  andwf   (Common_RAM + 3), F, A               ; reg: 0x003
004662:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
004664:  0a0b  xorlw   0x0b
004666:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2

label_584:                                                  ; address: 0x004668

004668:  86c5  bsf     SSPCON2, RCEN, A                     ; reg: 0xfc5, bit: 3

label_585:                                                  ; address: 0x00466a

00466a:  a0c7  btfss   SSPSTAT, BF, A                       ; reg: 0xfc7, bit: 0
00466c:  d7fe  bra     label_585                            ; dest: 0x00466a
00466e:  50c9  movf    SSPBUF, W, A                         ; reg: 0xfc9
004670:  0012  return  0x0

function_090:                                               ; address: 0x004672

004672:  ee21  lfsr    0x2, 0x1f4
004674:  f0f4
004676:  ee10  lfsr    0x1, 0x01c
004678:  f01c
00467a:  0e07  movlw   0x07

label_586:                                                  ; address: 0x00467c

00467c:  cfde  movff   POSTINC2, POSTINC1                   ; reg1: 0xfde, reg2: 0xfe6
00467e:  ffe6
004680:  2ee8  decfsz  WREG, F, A                           ; reg: 0xfe8
004682:  d7fc  bra     label_586                            ; dest: 0x00467c
004684:  0e1c  movlw   0x1c
004686:  ec59  call    function_080, 0x0                    ; dest: 0x0044b2
004688:  f022
00468a:  0e1c  movlw   0x1c
00468c:  ec59  call    function_080, 0x0                    ; dest: 0x0044b2
00468e:  f022
004690:  0e1c  movlw   0x1c
004692:  ef59  goto    function_080                         ; dest: 0x0044b2
004694:  f022

function_091:                                               ; address: 0x004696

004696:  6a1a  clrf    (Common_RAM + 26), A                 ; reg: 0x01a
004698:  d004  bra     label_588                            ; dest: 0x0046a2

label_587:                                                  ; address: 0x00469a

00469a:  d807  rcall   function_092                         ; dest: 0x0046aa
00469c:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
00469e:  f024
0046a0:  2a1a  incf    (Common_RAM + 26), F, A              ; reg: 0x01a

label_588:                                                  ; address: 0x0046a2

0046a2:  d803  rcall   function_092                         ; dest: 0x0046aa
0046a4:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0046a6:  0012  return  0x0
0046a8:  d7f8  bra     label_587                            ; dest: 0x00469a

function_092:                                               ; address: 0x0046aa

0046aa:  501a  movf    (Common_RAM + 26), W, A              ; reg: 0x01a
0046ac:  2418  addwf   (Common_RAM + 24), W, A              ; reg: 0x018
0046ae:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
0046b0:  0e00  movlw   0x00
0046b2:  2019  addwfc  (Common_RAM + 25), W, A              ; reg: 0x019
0046b4:  6eda  movwf   FSR2H, A                             ; reg: 0xfda
0046b6:  50df  movf    INDF2, W, A                          ; reg: 0xfdf
0046b8:  0012  return  0x0

function_093:                                               ; address: 0x0046ba

0046ba:  cfe8  movff   WREG, (Common_RAM + 7)               ; reg1: 0xfe8, reg2: 0x007
0046bc:  f007
0046be:  80c5  bsf     SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0

label_589:                                                  ; address: 0x0046c0

0046c0:  b0c5  btfsc   SSPCON2, SEN, A                      ; reg: 0xfc5, bit: 0
0046c2:  d7fe  bra     label_589                            ; dest: 0x0046c0
0046c4:  0ee2  movlw   0xe2
0046c6:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
0046c8:  f01f
0046ca:  5007  movf    (Common_RAM + 7), W, A               ; reg: 0x007
0046cc:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
0046ce:  f01f
0046d0:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
0046d2:  ec34  call    function_056, 0x0                    ; dest: 0x003e68
0046d4:  f01f
0046d6:  84c5  bsf     SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2

label_590:                                                  ; address: 0x0046d8

0046d8:  a4c5  btfss   SSPCON2, PEN, A                      ; reg: 0xfc5, bit: 2
0046da:  0012  return  0x0
0046dc:  d7fd  bra     label_590                            ; dest: 0x0046d8

function_094:                                               ; address: 0x0046de

0046de:  c007  movff   (Common_RAM + 7), (Common_RAM + 3)   ; reg1: 0x007, reg2: 0x003
0046e0:  f003
0046e2:  c008  movff   (Common_RAM + 8), (Common_RAM + 4)   ; reg1: 0x008, reg2: 0x004
0046e4:  f004
0046e6:  ec42  call    function_110, 0x0                    ; dest: 0x004884
0046e8:  f024
0046ea:  1809  xorwf   (Common_RAM + 9), W, A               ; reg: 0x009
0046ec:  e008  bz      label_591
0046ee:  c007  movff   (Common_RAM + 7), (Common_RAM + 3)   ; reg1: 0x007, reg2: 0x003
0046f0:  f003
0046f2:  c008  movff   (Common_RAM + 8), (Common_RAM + 4)   ; reg1: 0x008, reg2: 0x004
0046f4:  f004
0046f6:  c009  movff   (Common_RAM + 9), (Common_RAM + 5)   ; reg1: 0x009, reg2: 0x005
0046f8:  f005
0046fa:  eced  call    function_075, 0x0                    ; dest: 0x0043da
0046fc:  f021

label_591:                                                  ; address: 0x0046fe

0046fe:  0012  return  0x0

function_095:                                               ; address: 0x004700

004700:  0595  decf    0x95, W, B                           ; reg: 0x095
004702:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
004704:  ec14  call    function_105, 0x0                    ; dest: 0x004828
004706:  f024
004708:  6a6d  clrf    UCON, A                              ; reg: 0xf6d
00470a:  0e15  movlw   0x15
00470c:  6e6f  movwf   UCFG, A                              ; reg: 0xf6f
00470e:  6a69  clrf    UIE, A                               ; reg: 0xf69
004710:  866d  bsf     UCON, USBEN, A                       ; reg: 0xf6d, bit: 3
004712:  ec6b  call    function_063, 0x0                    ; dest: 0x0040d6
004714:  f020
004716:  0e01  movlw   0x01
004718:  0100  movlb   0x0
00471a:  6fcd  movwf   0xcd, B                              ; reg: 0x0cd
00471c:  6b95  clrf    0x95, B                              ; reg: 0x095
00471e:  0012  return  0x0

function_096:                                               ; address: 0x004720

004720:  cf69  movff   UIE, 0x092                           ; reg1: 0xf69
004722:  f092
004724:  0e04  movlw   0x04
004726:  6e69  movwf   UIE, A                               ; reg: 0xf69
004728:  9868  bcf     UIR, IDLEIF, A                       ; reg: 0xf68, bit: 4
00472a:  826d  bsf     UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
00472c:  9aa1  bcf     PIR2, USBIF, A                       ; reg: 0xfa1, bit: 5
00472e:  8aa0  bsf     PIE2, USBIE, A                       ; reg: 0xfa0, bit: 5
004730:  ecb5  call    function_129, 0x0                    ; dest: 0x00496a
004732:  f024
004734:  9aa0  bcf     PIE2, USBIE, A                       ; reg: 0xfa0, bit: 5
004736:  0100  movlb   0x0
004738:  5192  movf    0x92, W, B                           ; reg: 0x092
00473a:  1269  iorwf   UIE, F, A                            ; reg: 0xf69
00473c:  0012  return  0x0

function_097:                                               ; address: 0x00473e

00473e:  6a06  clrf    (Common_RAM + 6), A                  ; reg: 0x006
004740:  d008  bra     label_593                            ; dest: 0x004752

label_592:                                                  ; address: 0x004742

004742:  5006  movf    (Common_RAM + 6), W, A               ; reg: 0x006
004744:  2403  addwf   (Common_RAM + 3), W, A               ; reg: 0x003
004746:  6ed9  movwf   FSR2L, A                             ; reg: 0xfd9
004748:  0e00  movlw   0x00
00474a:  2004  addwfc  (Common_RAM + 4), W, A               ; reg: 0x004
00474c:  6eda  movwf   FSR2H, A                             ; reg: 0xfda
00474e:  6adf  clrf    INDF2, A                             ; reg: 0xfdf
004750:  2a06  incf    (Common_RAM + 6), F, A               ; reg: 0x006

label_593:                                                  ; address: 0x004752

004752:  5005  movf    (Common_RAM + 5), W, A               ; reg: 0x005
004754:  5c06  subwf   (Common_RAM + 6), W, A               ; reg: 0x006
004756:  b0d8  btfsc   STATUS, C, A                         ; reg: 0xfd8, bit: 0
004758:  0012  return  0x0
00475a:  d7f3  bra     label_592                            ; dest: 0x004742

function_098:                                               ; address: 0x00475c

00475c:  0100  movlb   0x0
00475e:  0595  decf    0x95, W, B                           ; reg: 0x095
004760:  e00b  bz      label_595
004762:  a082  btfss   PORTC, RC0, A                        ; reg: 0xf82, bit: 0
004764:  d004  bra     label_594                            ; dest: 0x00476e
004766:  a66d  btfss   UCON, USBEN, A                       ; reg: 0xf6d, bit: 3
004768:  ec80  call    function_095, 0x0                    ; dest: 0x004700
00476a:  f023
00476c:  d005  bra     label_595                            ; dest: 0x004778

label_594:                                                  ; address: 0x00476e

00476e:  a66d  btfss   UCON, USBEN, A                       ; reg: 0xf6d, bit: 3
004770:  d003  bra     label_595                            ; dest: 0x004778
004772:  ec78  call    function_116, 0x0                    ; dest: 0x0048f0
004774:  f024
004776:  6b95  clrf    0x95, B                              ; reg: 0x095

label_595:                                                  ; address: 0x004778

004778:  0012  return  0x0

function_099:                                               ; address: 0x00477a

00477a:  0e98  movlw   0x98
00477c:  6eb1  movwf   T3CON, A                             ; reg: 0xfb1
00477e:  0ef8  movlw   0xf8
004780:  6eb3  movwf   TMR3H, A                             ; reg: 0xfb3
004782:  0e30  movlw   0x30
004784:  6eb2  movwf   TMR3L, A                             ; reg: 0xfb2
004786:  c003  movff   (Common_RAM + 3), 0x08c              ; reg1: 0x003
004788:  f08c
00478a:  c004  movff   (Common_RAM + 4), 0x08d              ; reg1: 0x004
00478c:  f08d
00478e:  92a1  bcf     PIR2, TMR3IF, A                      ; reg: 0xfa1, bit: 1
004790:  80b1  bsf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
004792:  82a0  bsf     PIE2, TMR3IE, A                      ; reg: 0xfa0, bit: 1
004794:  0c30  retlw   0x30

function_100:                                               ; address: 0x004796

004796:  0100  movlb   0x0
004798:  a57e  btfss   0x7e, 0x2, B                         ; reg: 0x07e
00479a:  d008  bra     label_598                            ; dest: 0x0047ac
00479c:  a65e  btfss   (Common_RAM + 94), 0x3, A            ; reg: 0x05e
00479e:  d003  bra     label_596                            ; dest: 0x0047a6
0047a0:  ecc6  call    function_024, 0x0                    ; dest: 0x002d8c
0047a2:  f016
0047a4:  d002  bra     label_597                            ; dest: 0x0047aa

label_596:                                                  ; address: 0x0047a6

0047a6:  ec06  call    function_051, 0x0                    ; dest: 0x003c0c
0047a8:  f01e

label_597:                                                  ; address: 0x0047aa

0047aa:  957e  bcf     0x7e, 0x2, B                         ; reg: 0x07e

label_598:                                                  ; address: 0x0047ac

0047ac:  0e01  movlw   0x01
0047ae:  ef77  goto    function_005                         ; dest: 0x0018ee
0047b0:  f00c

function_101:                                               ; address: 0x0047b2

0047b2:  cfe8  movff   WREG, (Common_RAM + 4)               ; reg1: 0xfe8, reg2: 0x004
0047b4:  f004
0047b6:  0e3f  movlw   0x3f
0047b8:  16c7  andwf   SSPSTAT, F, A                        ; reg: 0xfc7
0047ba:  6ac6  clrf    SSPCON1, A                           ; reg: 0xfc6
0047bc:  6ac5  clrf    SSPCON2, A                           ; reg: 0xfc5
0047be:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
0047c0:  12c6  iorwf   SSPCON1, F, A                        ; reg: 0xfc6
0047c2:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
0047c4:  12c7  iorwf   SSPSTAT, F, A                        ; reg: 0xfc7
0047c6:  8293  bsf     TRISB, RB1, A                        ; reg: 0xf93, bit: 1
0047c8:  8093  bsf     TRISB, RB0, A                        ; reg: 0xf93, bit: 0
0047ca:  8ac6  bsf     SSPCON1, SSPEN, A                    ; reg: 0xfc6, bit: 5
0047cc:  0012  return  0x0

function_102:                                               ; address: 0x0047ce

0047ce:  ec13  call    function_047, 0x0                    ; dest: 0x003a26
0047d0:  f01d
0047d2:  ecf3  call    function_006, 0x0                    ; dest: 0x001be6
0047d4:  f00d
0047d6:  ecf8  call    function_015, 0x0                    ; dest: 0x0027f0
0047d8:  f013
0047da:  eccb  call    function_100, 0x0                    ; dest: 0x004796
0047dc:  f023
0047de:  ec2e  call    function_014, 0x0                    ; dest: 0x00265c
0047e0:  f013
0047e2:  efb7  goto    label_529                            ; dest: 0x00416e
0047e4:  f020
0047e6:  202d  addwfc  (Common_RAM + 45), W, A              ; reg: 0x02d
0047e8:  4146  rrncf   (Common_RAM + 70), W, B              ; reg: 0x046
0047ea:  4c49  dcfsnz  (Common_RAM + 73), W, A              ; reg: 0x049
0047ec:  0020  dw      0x0020                               ; ' '
0047ee:  5746  subfwb  (Common_RAM + 70), F, B              ; reg: 0x046
0047f0:  555f  subfwb  (Common_RAM + 95), W, B              ; reg: 0x05f
0047f2:  6470  cpfsgt  UEP0, A                              ; reg: 0xf70
0047f4:  3000  rrcf    Common_RAM, W, A                     ; reg: 0x000
0047f6:  3030  rrcf    (Common_RAM + 48), W, A              ; reg: 0x030
0047f8:  3030  rrcf    (Common_RAM + 48), W, A              ; reg: 0x030
0047fa:  0030  dw      0x0030                               ; '0'

function_103:                                               ; address: 0x0047fc

0047fc:  0ebf  movlw   0xbf
0047fe:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
004800:  f024
004802:  0e29  movlw   0x29
004804:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
004806:  f024
004808:  0e01  movlw   0x01
00480a:  a25e  btfss   (Common_RAM + 94), 0x1, A            ; reg: 0x05e
00480c:  0e00  movlw   0x00
00480e:  ef4b  goto    function_111                         ; dest: 0x004896
004810:  f024

function_104:                                               ; address: 0x004812

004812:  d005  bra     label_600                            ; dest: 0x00481e

label_599:                                                  ; address: 0x004814

004814:  ecb1  call    function_127, 0x0                    ; dest: 0x004962
004816:  f024
004818:  0603  decf    (Common_RAM + 3), F, A               ; reg: 0x003
00481a:  a0d8  btfss   STATUS, C, A                         ; reg: 0xfd8, bit: 0
00481c:  0604  decf    (Common_RAM + 4), F, A               ; reg: 0x004

label_600:                                                  ; address: 0x00481e

00481e:  5004  movf    (Common_RAM + 4), W, A               ; reg: 0x004
004820:  1003  iorwf   (Common_RAM + 3), W, A               ; reg: 0x003
004822:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
004824:  0012  return  0x0
004826:  d7f6  bra     label_599                            ; dest: 0x004814

function_105:                                               ; address: 0x004828

004828:  926d  bcf     UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
00482a:  6a6d  clrf    UCON, A                              ; reg: 0xf6d
00482c:  0eff  movlw   0xff
00482e:  6804  setf    (Common_RAM + 4), A                  ; reg: 0x004
004830:  6803  setf    (Common_RAM + 3), A                  ; reg: 0x003
004832:  ec09  call    function_104, 0x0                    ; dest: 0x004812
004834:  f024
004836:  0100  movlb   0x0
004838:  6bcd  clrf    0xcd, B                              ; reg: 0x0cd
00483a:  0012  return  0x0

function_106:                                               ; address: 0x00483c

00483c:  ec92  call    function_119, 0x0                    ; dest: 0x004924
00483e:  f024
004840:  926d  bcf     UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
004842:  9469  bcf     UIE, ACTVIE, A                       ; reg: 0xf69, bit: 2
004844:  d001  bra     label_602                            ; dest: 0x004848

label_601:                                                  ; address: 0x004846

004846:  9468  bcf     UIR, ACTVIF, A                       ; reg: 0xf68, bit: 2

label_602:                                                  ; address: 0x004848

004848:  a468  btfss   UIR, ACTVIF, A                       ; reg: 0xf68, bit: 2
00484a:  0012  return  0x0
00484c:  d7fc  bra     label_601                            ; dest: 0x004846

function_107:                                               ; address: 0x00484e

00484e:  0ebf  movlw   0xbf
004850:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
004852:  f024
004854:  0e18  movlw   0x18
004856:  ec4b  call    function_111, 0x0                    ; dest: 0x004896
004858:  f024
00485a:  0e01  movlw   0x01
00485c:  ef4b  goto    function_111                         ; dest: 0x004896
00485e:  f024

function_108:                                               ; address: 0x004860

004860:  d002  bra     label_604                            ; dest: 0x004866

label_603:                                                  ; address: 0x004862

004862:  ecfd  call    function_087, 0x0                    ; dest: 0x0045fa
004864:  f022

label_604:                                                  ; address: 0x004866

004866:  ec39  call    function_109, 0x0                    ; dest: 0x004872
004868:  f024
00486a:  0900  iorlw   0x00
00486c:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
00486e:  0012  return  0x0
004870:  d7f8  bra     label_603                            ; dest: 0x004862

function_109:                                               ; address: 0x004872

004872:  0100  movlb   0x0
004874:  51c7  movf    0xc7, W, B                           ; reg: 0x0c7
004876:  6af3  clrf    PRODL, A                             ; reg: 0xff3
004878:  63c6  cpfseq  0xc6, B                              ; reg: 0x0c6
00487a:  2af3  incf    PRODL, F, A                          ; reg: 0xff3
00487c:  cff3  movff   PRODL, (Common_RAM + 3)              ; reg1: 0xff3, reg2: 0x003
00487e:  f003
004880:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
004882:  0012  return  0x0

function_110:                                               ; address: 0x004884

004884:  c003  movff   (Common_RAM + 3), EEADR              ; reg1: 0x003, reg2: 0xfa9
004886:  ffa9
004888:  9ca6  bcf     EECON1, CFGS, A                      ; reg: 0xfa6, bit: 6
00488a:  9ea6  bcf     EECON1, EEPGD, A                     ; reg: 0xfa6, bit: 7
00488c:  80a6  bsf     EECON1, RD, A                        ; reg: 0xfa6, bit: 0
00488e:  f000  dw      0xf000
004890:  f000  dw      0xf000
004892:  50a8  movf    EEDATA, W, A                         ; reg: 0xfa8
004894:  0012  return  0x0

function_111:                                               ; address: 0x004896

004896:  cfe8  movff   WREG, (Common_RAM + 3)               ; reg1: 0xfe8, reg2: 0x003
004898:  f003

label_605:                                                  ; address: 0x00489a

00489a:  a2ac  btfss   TXSTA, TRMT, A                       ; reg: 0xfac, bit: 1
00489c:  d7fe  bra     label_605                            ; dest: 0x00489a
00489e:  c003  movff   (Common_RAM + 3), TXREG              ; reg1: 0x003, reg2: 0xfad
0048a0:  ffad
0048a2:  5003  movf    (Common_RAM + 3), W, A               ; reg: 0x003
0048a4:  0012  return  0x0

function_112:                                               ; address: 0x0048a6

0048a6:  0ea4  movlw   0xa4
0048a8:  6ed7  movwf   TMR0H, A                             ; reg: 0xfd7
0048aa:  0e71  movlw   0x71
0048ac:  6ed6  movwf   TMR0L, A                             ; reg: 0xfd6
0048ae:  94f2  bcf     INTCON, T0IF, A                      ; reg: 0xff2, bit: 2
0048b0:  8af2  bsf     INTCON, T0IE, A                      ; reg: 0xff2, bit: 5
0048b2:  8ed5  bsf     T0CON, TMR0ON, A                     ; reg: 0xfd5, bit: 7
0048b4:  0c71  retlw   0x71

function_113:                                               ; address: 0x0048b6

0048b6:  cfc5  movff   SSPCON2, (Common_RAM + 3)            ; reg1: 0xfc5, reg2: 0x003
0048b8:  f003
0048ba:  0e1f  movlw   0x1f
0048bc:  1603  andwf   (Common_RAM + 3), F, A               ; reg: 0x003
0048be:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
0048c0:  b4c7  btfsc   SSPSTAT, R, A                        ; reg: 0xfc7, bit: 2
0048c2:  d7f9  bra     function_113                         ; dest: 0x0048b6
0048c4:  0c1f  retlw   0x1f

label_606:                                                  ; address: 0x0048c6

0048c6:  ecae  call    function_035, 0x0                    ; dest: 0x00355c
0048c8:  f01a

label_607:                                                  ; address: 0x0048ca

0048ca:  eca7  call    function_026, 0x0                    ; dest: 0x002f4e
0048cc:  f017
0048ce:  ece7  call    function_102, 0x0                    ; dest: 0x0047ce
0048d0:  f023
0048d2:  d7fb  bra     label_607                            ; dest: 0x0048ca

function_114:                                               ; address: 0x0048d4

0048d4:  6af2  clrf    INTCON, A                            ; reg: 0xff2
0048d6:  f000  dw      0xf000
0048d8:  f000  dw      0xf000
0048da:  00ff  reset
0048dc:  f000  dw      0xf000
0048de:  f000  dw      0xf000
0048e0:  0012  return  0x0

function_115:                                               ; address: 0x0048e2

0048e2:  0e02  movlw   0x02
0048e4:  ecb4  call    function_072, 0x0                    ; dest: 0x004368
0048e6:  f021
0048e8:  9689  bcf     LATA, LATA3, A                       ; reg: 0xf89, bit: 3
0048ea:  9889  bcf     LATA, LATA4, A                       ; reg: 0xf89, bit: 4
0048ec:  9a89  bcf     LATA, LATA5, A                       ; reg: 0xf89, bit: 5
0048ee:  0012  return  0x0

function_116:                                               ; address: 0x0048f0

0048f0:  926d  bcf     UCON, SUSPND, A                      ; reg: 0xf6d, bit: 1
0048f2:  6a6d  clrf    UCON, A                              ; reg: 0xf6d
0048f4:  0100  movlb   0x0
0048f6:  6bcd  clrf    0xcd, B                              ; reg: 0x0cd
0048f8:  0e01  movlw   0x01
0048fa:  6f95  movwf   0x95, B                              ; reg: 0x095
0048fc:  0c01  retlw   0x01

function_117:                                               ; address: 0x0048fe

0048fe:  cfe8  movff   WREG, (Common_RAM + 3)               ; reg1: 0xfe8, reg2: 0x003
004900:  f003
004902:  0403  decf    (Common_RAM + 3), W, A               ; reg: 0x003
004904:  b4d8  btfsc   STATUS, Z, A                         ; reg: 0xfd8, bit: 2
004906:  ec12  call    function_088, 0x0                    ; dest: 0x004624
004908:  f023
00490a:  0012  return  0x0

function_118:                                               ; address: 0x00490c

00490c:  a0b1  btfss   T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
00490e:  d002  bra     label_608                            ; dest: 0x004914
004910:  90d8  bcf     STATUS, C, A                         ; reg: 0xfd8, bit: 0
004912:  d001  bra     label_609                            ; dest: 0x004916

label_608:                                                  ; address: 0x004914

004914:  80d8  bsf     STATUS, C, A                         ; reg: 0xfd8, bit: 0

label_609:                                                  ; address: 0x004916

004916:  0012  return  0x0

label_610:                                                  ; address: 0x004918

004918:  b66d  btfsc   UCON, USBEN, A                       ; reg: 0xf6d, bit: 3
00491a:  ec14  call    function_105, 0x0                    ; dest: 0x004828
00491c:  f024
00491e:  6b95  clrf    0x95, B                              ; reg: 0x095
004920:  efae  goto    function_098                         ; dest: 0x00475c
004922:  f023

function_119:                                               ; address: 0x004924

004924:  0e03  movlw   0x03
004926:  6e04  movwf   (Common_RAM + 4), A                  ; reg: 0x004
004928:  6a03  clrf    (Common_RAM + 3), A                  ; reg: 0x003
00492a:  ef0f  goto    label_600                            ; dest: 0x00481e
00492c:  f024

function_120:                                               ; address: 0x00492e

00492e:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
004930:  0e01  movlw   0x01
004932:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
004934:  ef3f  goto    function_079                         ; dest: 0x00447e
004936:  f022

function_121:                                               ; address: 0x004938

004938:  eca3  call    function_083, 0x0                    ; dest: 0x004546
00493a:  f022
00493c:  905e  bcf     (Common_RAM + 94), 0x0, A            ; reg: 0x05e
00493e:  6b98  clrf    0x98, B                              ; reg: 0x098
004940:  0012  return  0x0

function_122:                                               ; address: 0x004942

004942:  6a04  clrf    (Common_RAM + 4), A                  ; reg: 0x004
004944:  0e02  movlw   0x02
004946:  6e03  movwf   (Common_RAM + 3), A                  ; reg: 0x003
004948:  ef3f  goto    function_079                         ; dest: 0x00447e
00494a:  f022

function_123:                                               ; address: 0x00494c

00494c:  90b1  bcf     T3CON, TMR3ON, A                     ; reg: 0xfb1, bit: 0
00494e:  92a1  bcf     PIR2, TMR3IF, A                      ; reg: 0xfa1, bit: 1
004950:  92a0  bcf     PIE2, TMR3IE, A                      ; reg: 0xfa0, bit: 1
004952:  0012  return  0x0

function_124:                                               ; address: 0x004954

004954:  0e01  movlw   0x01
004956:  efb4  goto    function_072                         ; dest: 0x004368
004958:  f021

function_125:                                               ; address: 0x00495a

00495a:  efca  goto    label_383                            ; dest: 0x003194
00495c:  f018

function_126:                                               ; address: 0x00495e

00495e:  88ab  bsf     RCSTA, CREN, A                       ; reg: 0xfab, bit: 4
004960:  0012  return  0x0

function_127:                                               ; address: 0x004962

004962:  0004  clrwdt
004964:  0012  return  0x0

function_128:                                               ; address: 0x004966

004966:  9ac6  bcf     SSPCON1, SSPEN, A                    ; reg: 0xfc6, bit: 5
004968:  0012  return  0x0

function_129:                                               ; address: 0x00496a

00496a:  0012  return  0x0

function_130:                                               ; address: 0x00496c

00496c:  0012  return  0x0

function_131:                                               ; address: 0x00496e

00496e:  0012  return  0x0
004970:  ffff  dw      0xffff
004972:  ffff  dw      0xffff
004974:  ffff  dw      0xffff
004976:  ffff  dw      0xffff
004978:  ffff  dw      0xffff
00497a:  ffff  dw      0xffff
00497c:  ffff  dw      0xffff
00497e:  ffff  dw      0xffff
004980:  ffff  dw      0xffff
004982:  ffff  dw      0xffff
004984:  ffff  dw      0xffff
004986:  ffff  dw      0xffff
004988:  ffff  dw      0xffff
00498a:  ffff  dw      0xffff
00498c:  ffff  dw      0xffff
00498e:  ffff  dw      0xffff
004990:  ffff  dw      0xffff
004992:  ffff  dw      0xffff
004994:  ffff  dw      0xffff
004996:  ffff  dw      0xffff
004998:  ffff  dw      0xffff
00499a:  ffff  dw      0xffff
00499c:  ffff  dw      0xffff
00499e:  ffff  dw      0xffff
0049a0:  ffff  dw      0xffff
0049a2:  ffff  dw      0xffff
0049a4:  ffff  dw      0xffff
0049a6:  ffff  dw      0xffff
0049a8:  ffff  dw      0xffff
0049aa:  ffff  dw      0xffff
0049ac:  ffff  dw      0xffff
0049ae:  ffff  dw      0xffff
0049b0:  ffff  dw      0xffff
0049b2:  ffff  dw      0xffff
0049b4:  ffff  dw      0xffff
0049b6:  ffff  dw      0xffff
0049b8:  ffff  dw      0xffff
0049ba:  ffff  dw      0xffff
0049bc:  ffff  dw      0xffff
0049be:  ffff  dw      0xffff
0049c0:  ffff  dw      0xffff
0049c2:  ffff  dw      0xffff
0049c4:  ffff  dw      0xffff
0049c6:  ffff  dw      0xffff
0049c8:  ffff  dw      0xffff
0049ca:  ffff  dw      0xffff
0049cc:  ffff  dw      0xffff
0049ce:  ffff  dw      0xffff
0049d0:  ffff  dw      0xffff
0049d2:  ffff  dw      0xffff
0049d4:  ffff  dw      0xffff
0049d6:  ffff  dw      0xffff
0049d8:  ffff  dw      0xffff
0049da:  ffff  dw      0xffff
0049dc:  ffff  dw      0xffff
0049de:  ffff  dw      0xffff
0049e0:  ffff  dw      0xffff
0049e2:  ffff  dw      0xffff
0049e4:  ffff  dw      0xffff
0049e6:  ffff  dw      0xffff
0049e8:  ffff  dw      0xffff
0049ea:  ffff  dw      0xffff
0049ec:  ffff  dw      0xffff
0049ee:  ffff  dw      0xffff
0049f0:  ffff  dw      0xffff
0049f2:  ffff  dw      0xffff
0049f4:  ffff  dw      0xffff
0049f6:  ffff  dw      0xffff
0049f8:  ffff  dw      0xffff
0049fa:  ffff  dw      0xffff
0049fc:  ffff  dw      0xffff
0049fe:  ffff  dw      0xffff
004a00:  ffff  dw      0xffff
004a02:  ffff  dw      0xffff
004a04:  ffff  dw      0xffff
004a06:  ffff  dw      0xffff
004a08:  ffff  dw      0xffff
004a0a:  ffff  dw      0xffff
004a0c:  ffff  dw      0xffff
004a0e:  ffff  dw      0xffff
004a10:  ffff  dw      0xffff
004a12:  ffff  dw      0xffff
004a14:  ffff  dw      0xffff
004a16:  ffff  dw      0xffff
004a18:  ffff  dw      0xffff
004a1a:  ffff  dw      0xffff
004a1c:  ffff  dw      0xffff
004a1e:  ffff  dw      0xffff
004a20:  ffff  dw      0xffff
004a22:  ffff  dw      0xffff
004a24:  ffff  dw      0xffff
004a26:  ffff  dw      0xffff
004a28:  ffff  dw      0xffff
004a2a:  ffff  dw      0xffff
004a2c:  ffff  dw      0xffff
004a2e:  ffff  dw      0xffff
004a30:  ffff  dw      0xffff
004a32:  ffff  dw      0xffff
004a34:  ffff  dw      0xffff
004a36:  ffff  dw      0xffff
004a38:  ffff  dw      0xffff
004a3a:  ffff  dw      0xffff
004a3c:  ffff  dw      0xffff
004a3e:  ffff  dw      0xffff
004a40:  ffff  dw      0xffff
004a42:  ffff  dw      0xffff
004a44:  ffff  dw      0xffff
004a46:  ffff  dw      0xffff
004a48:  ffff  dw      0xffff
004a4a:  ffff  dw      0xffff
004a4c:  ffff  dw      0xffff
004a4e:  ffff  dw      0xffff
004a50:  ffff  dw      0xffff
004a52:  ffff  dw      0xffff
004a54:  ffff  dw      0xffff
004a56:  ffff  dw      0xffff
004a58:  ffff  dw      0xffff
004a5a:  ffff  dw      0xffff
004a5c:  ffff  dw      0xffff
004a5e:  ffff  dw      0xffff
004a60:  ffff  dw      0xffff
004a62:  ffff  dw      0xffff
004a64:  ffff  dw      0xffff
004a66:  ffff  dw      0xffff
004a68:  ffff  dw      0xffff
004a6a:  ffff  dw      0xffff
004a6c:  ffff  dw      0xffff
004a6e:  ffff  dw      0xffff
004a70:  ffff  dw      0xffff
004a72:  ffff  dw      0xffff
004a74:  ffff  dw      0xffff
004a76:  ffff  dw      0xffff
004a78:  ffff  dw      0xffff
004a7a:  ffff  dw      0xffff
004a7c:  ffff  dw      0xffff
004a7e:  ffff  dw      0xffff
004a80:  ffff  dw      0xffff
004a82:  ffff  dw      0xffff
004a84:  ffff  dw      0xffff
004a86:  ffff  dw      0xffff
004a88:  ffff  dw      0xffff
004a8a:  ffff  dw      0xffff
004a8c:  ffff  dw      0xffff
004a8e:  ffff  dw      0xffff
004a90:  ffff  dw      0xffff
004a92:  ffff  dw      0xffff
004a94:  ffff  dw      0xffff
004a96:  ffff  dw      0xffff
004a98:  ffff  dw      0xffff
004a9a:  ffff  dw      0xffff
004a9c:  ffff  dw      0xffff
004a9e:  ffff  dw      0xffff
004aa0:  ffff  dw      0xffff
004aa2:  ffff  dw      0xffff
004aa4:  ffff  dw      0xffff
004aa6:  ffff  dw      0xffff
004aa8:  ffff  dw      0xffff
004aaa:  ffff  dw      0xffff
004aac:  ffff  dw      0xffff
004aae:  ffff  dw      0xffff
004ab0:  ffff  dw      0xffff
004ab2:  ffff  dw      0xffff
004ab4:  ffff  dw      0xffff
004ab6:  ffff  dw      0xffff
004ab8:  ffff  dw      0xffff
004aba:  ffff  dw      0xffff
004abc:  ffff  dw      0xffff
004abe:  ffff  dw      0xffff
004ac0:  ffff  dw      0xffff
004ac2:  ffff  dw      0xffff
004ac4:  ffff  dw      0xffff
004ac6:  ffff  dw      0xffff
004ac8:  ffff  dw      0xffff
004aca:  ffff  dw      0xffff
004acc:  ffff  dw      0xffff
004ace:  ffff  dw      0xffff
004ad0:  ffff  dw      0xffff
004ad2:  ffff  dw      0xffff
004ad4:  ffff  dw      0xffff
004ad6:  ffff  dw      0xffff
004ad8:  ffff  dw      0xffff
004ada:  ffff  dw      0xffff
004adc:  ffff  dw      0xffff
004ade:  ffff  dw      0xffff
004ae0:  ffff  dw      0xffff
004ae2:  ffff  dw      0xffff
004ae4:  ffff  dw      0xffff
004ae6:  ffff  dw      0xffff
004ae8:  ffff  dw      0xffff
004aea:  ffff  dw      0xffff
004aec:  ffff  dw      0xffff
004aee:  ffff  dw      0xffff
004af0:  ffff  dw      0xffff
004af2:  ffff  dw      0xffff
004af4:  ffff  dw      0xffff
004af6:  ffff  dw      0xffff
004af8:  ffff  dw      0xffff
004afa:  ffff  dw      0xffff
004afc:  ffff  dw      0xffff
004afe:  ffff  dw      0xffff
004b00:  ffff  dw      0xffff
004b02:  ffff  dw      0xffff
004b04:  ffff  dw      0xffff
004b06:  ffff  dw      0xffff
004b08:  ffff  dw      0xffff
004b0a:  ffff  dw      0xffff
004b0c:  ffff  dw      0xffff
004b0e:  ffff  dw      0xffff
004b10:  ffff  dw      0xffff
004b12:  ffff  dw      0xffff
004b14:  ffff  dw      0xffff
004b16:  ffff  dw      0xffff
004b18:  ffff  dw      0xffff
004b1a:  ffff  dw      0xffff
004b1c:  ffff  dw      0xffff
004b1e:  ffff  dw      0xffff
004b20:  ffff  dw      0xffff
004b22:  ffff  dw      0xffff
004b24:  ffff  dw      0xffff
004b26:  ffff  dw      0xffff
004b28:  ffff  dw      0xffff
004b2a:  ffff  dw      0xffff
004b2c:  ffff  dw      0xffff
004b2e:  ffff  dw      0xffff
004b30:  ffff  dw      0xffff
004b32:  ffff  dw      0xffff
004b34:  ffff  dw      0xffff
004b36:  ffff  dw      0xffff
004b38:  ffff  dw      0xffff
004b3a:  ffff  dw      0xffff
004b3c:  ffff  dw      0xffff
004b3e:  ffff  dw      0xffff
004b40:  ffff  dw      0xffff
004b42:  ffff  dw      0xffff
004b44:  ffff  dw      0xffff
004b46:  ffff  dw      0xffff
004b48:  ffff  dw      0xffff
004b4a:  ffff  dw      0xffff
004b4c:  ffff  dw      0xffff
004b4e:  ffff  dw      0xffff
004b50:  ffff  dw      0xffff
004b52:  ffff  dw      0xffff
004b54:  ffff  dw      0xffff
004b56:  ffff  dw      0xffff
004b58:  ffff  dw      0xffff
004b5a:  ffff  dw      0xffff
004b5c:  ffff  dw      0xffff
004b5e:  ffff  dw      0xffff
004b60:  ffff  dw      0xffff
004b62:  ffff  dw      0xffff
004b64:  ffff  dw      0xffff
004b66:  ffff  dw      0xffff
004b68:  ffff  dw      0xffff
004b6a:  ffff  dw      0xffff
004b6c:  ffff  dw      0xffff
004b6e:  ffff  dw      0xffff
004b70:  ffff  dw      0xffff
004b72:  ffff  dw      0xffff
004b74:  ffff  dw      0xffff
004b76:  ffff  dw      0xffff
004b78:  ffff  dw      0xffff
004b7a:  ffff  dw      0xffff
004b7c:  ffff  dw      0xffff
004b7e:  ffff  dw      0xffff
004b80:  ffff  dw      0xffff
004b82:  ffff  dw      0xffff
004b84:  ffff  dw      0xffff
004b86:  ffff  dw      0xffff
004b88:  ffff  dw      0xffff
004b8a:  ffff  dw      0xffff
004b8c:  ffff  dw      0xffff
004b8e:  ffff  dw      0xffff
004b90:  ffff  dw      0xffff
004b92:  ffff  dw      0xffff
004b94:  ffff  dw      0xffff
004b96:  ffff  dw      0xffff
004b98:  ffff  dw      0xffff
004b9a:  ffff  dw      0xffff
004b9c:  ffff  dw      0xffff
004b9e:  ffff  dw      0xffff
004ba0:  ffff  dw      0xffff
004ba2:  ffff  dw      0xffff
004ba4:  ffff  dw      0xffff
004ba6:  ffff  dw      0xffff
004ba8:  ffff  dw      0xffff
004baa:  ffff  dw      0xffff
004bac:  ffff  dw      0xffff
004bae:  ffff  dw      0xffff
004bb0:  ffff  dw      0xffff
004bb2:  ffff  dw      0xffff
004bb4:  ffff  dw      0xffff
004bb6:  ffff  dw      0xffff
004bb8:  ffff  dw      0xffff
004bba:  ffff  dw      0xffff
004bbc:  ffff  dw      0xffff
004bbe:  ffff  dw      0xffff
004bc0:  ffff  dw      0xffff
004bc2:  ffff  dw      0xffff
004bc4:  ffff  dw      0xffff
004bc6:  ffff  dw      0xffff
004bc8:  ffff  dw      0xffff
004bca:  ffff  dw      0xffff
004bcc:  ffff  dw      0xffff
004bce:  ffff  dw      0xffff
004bd0:  ffff  dw      0xffff
004bd2:  ffff  dw      0xffff
004bd4:  ffff  dw      0xffff
004bd6:  ffff  dw      0xffff
004bd8:  ffff  dw      0xffff
004bda:  ffff  dw      0xffff
004bdc:  ffff  dw      0xffff
004bde:  ffff  dw      0xffff
004be0:  ffff  dw      0xffff
004be2:  ffff  dw      0xffff
004be4:  ffff  dw      0xffff
004be6:  ffff  dw      0xffff
004be8:  ffff  dw      0xffff
004bea:  ffff  dw      0xffff
004bec:  ffff  dw      0xffff
004bee:  ffff  dw      0xffff
004bf0:  ffff  dw      0xffff
004bf2:  ffff  dw      0xffff
004bf4:  ffff  dw      0xffff
004bf6:  ffff  dw      0xffff
004bf8:  ffff  dw      0xffff
004bfa:  ffff  dw      0xffff
004bfc:  ffff  dw      0xffff
004bfe:  ffff  dw      0xffff
004c00:  ffff  dw      0xffff
004c02:  ffff  dw      0xffff
004c04:  ffff  dw      0xffff
004c06:  ffff  dw      0xffff
004c08:  ffff  dw      0xffff
004c0a:  ffff  dw      0xffff
004c0c:  ffff  dw      0xffff
004c0e:  ffff  dw      0xffff
004c10:  ffff  dw      0xffff
004c12:  ffff  dw      0xffff
004c14:  ffff  dw      0xffff
004c16:  ffff  dw      0xffff
004c18:  ffff  dw      0xffff
004c1a:  ffff  dw      0xffff
004c1c:  ffff  dw      0xffff
004c1e:  ffff  dw      0xffff
004c20:  ffff  dw      0xffff
004c22:  ffff  dw      0xffff
004c24:  ffff  dw      0xffff
004c26:  ffff  dw      0xffff
004c28:  ffff  dw      0xffff
004c2a:  ffff  dw      0xffff
004c2c:  ffff  dw      0xffff
004c2e:  ffff  dw      0xffff
004c30:  ffff  dw      0xffff
004c32:  ffff  dw      0xffff
004c34:  ffff  dw      0xffff
004c36:  ffff  dw      0xffff
004c38:  ffff  dw      0xffff
004c3a:  ffff  dw      0xffff
004c3c:  ffff  dw      0xffff
004c3e:  ffff  dw      0xffff
004c40:  ffff  dw      0xffff
004c42:  ffff  dw      0xffff
004c44:  ffff  dw      0xffff
004c46:  ffff  dw      0xffff
004c48:  ffff  dw      0xffff
004c4a:  ffff  dw      0xffff
004c4c:  ffff  dw      0xffff
004c4e:  ffff  dw      0xffff
004c50:  ffff  dw      0xffff
004c52:  ffff  dw      0xffff
004c54:  ffff  dw      0xffff
004c56:  ffff  dw      0xffff
004c58:  ffff  dw      0xffff
004c5a:  ffff  dw      0xffff
004c5c:  ffff  dw      0xffff
004c5e:  ffff  dw      0xffff
004c60:  ffff  dw      0xffff
004c62:  ffff  dw      0xffff
004c64:  ffff  dw      0xffff
004c66:  ffff  dw      0xffff
004c68:  ffff  dw      0xffff
004c6a:  ffff  dw      0xffff
004c6c:  ffff  dw      0xffff
004c6e:  ffff  dw      0xffff
004c70:  ffff  dw      0xffff
004c72:  ffff  dw      0xffff
004c74:  ffff  dw      0xffff
004c76:  ffff  dw      0xffff
004c78:  ffff  dw      0xffff
004c7a:  ffff  dw      0xffff
004c7c:  ffff  dw      0xffff
004c7e:  ffff  dw      0xffff
004c80:  ffff  dw      0xffff
004c82:  ffff  dw      0xffff
004c84:  ffff  dw      0xffff
004c86:  ffff  dw      0xffff
004c88:  ffff  dw      0xffff
004c8a:  ffff  dw      0xffff
004c8c:  ffff  dw      0xffff
004c8e:  ffff  dw      0xffff
004c90:  ffff  dw      0xffff
004c92:  ffff  dw      0xffff
004c94:  ffff  dw      0xffff
004c96:  ffff  dw      0xffff
004c98:  ffff  dw      0xffff
004c9a:  ffff  dw      0xffff
004c9c:  ffff  dw      0xffff
004c9e:  ffff  dw      0xffff
004ca0:  ffff  dw      0xffff
004ca2:  ffff  dw      0xffff
004ca4:  ffff  dw      0xffff
004ca6:  ffff  dw      0xffff
004ca8:  ffff  dw      0xffff
004caa:  ffff  dw      0xffff
004cac:  ffff  dw      0xffff
004cae:  ffff  dw      0xffff
004cb0:  ffff  dw      0xffff
004cb2:  ffff  dw      0xffff
004cb4:  ffff  dw      0xffff
004cb6:  ffff  dw      0xffff
004cb8:  ffff  dw      0xffff
004cba:  ffff  dw      0xffff
004cbc:  ffff  dw      0xffff
004cbe:  ffff  dw      0xffff
004cc0:  ffff  dw      0xffff
004cc2:  ffff  dw      0xffff
004cc4:  ffff  dw      0xffff
004cc6:  ffff  dw      0xffff
004cc8:  ffff  dw      0xffff
004cca:  ffff  dw      0xffff
004ccc:  ffff  dw      0xffff
004cce:  ffff  dw      0xffff
004cd0:  ffff  dw      0xffff
004cd2:  ffff  dw      0xffff
004cd4:  ffff  dw      0xffff
004cd6:  ffff  dw      0xffff
004cd8:  ffff  dw      0xffff
004cda:  ffff  dw      0xffff
004cdc:  ffff  dw      0xffff
004cde:  ffff  dw      0xffff
004ce0:  ffff  dw      0xffff
004ce2:  ffff  dw      0xffff
004ce4:  ffff  dw      0xffff
004ce6:  ffff  dw      0xffff
004ce8:  ffff  dw      0xffff
004cea:  ffff  dw      0xffff
004cec:  ffff  dw      0xffff
004cee:  ffff  dw      0xffff
004cf0:  ffff  dw      0xffff
004cf2:  ffff  dw      0xffff
004cf4:  ffff  dw      0xffff
004cf6:  ffff  dw      0xffff
004cf8:  ffff  dw      0xffff
004cfa:  ffff  dw      0xffff
004cfc:  ffff  dw      0xffff
004cfe:  ffff  dw      0xffff
004d00:  ffff  dw      0xffff
004d02:  ffff  dw      0xffff
004d04:  ffff  dw      0xffff
004d06:  ffff  dw      0xffff
004d08:  ffff  dw      0xffff
004d0a:  ffff  dw      0xffff
004d0c:  ffff  dw      0xffff
004d0e:  ffff  dw      0xffff
004d10:  ffff  dw      0xffff
004d12:  ffff  dw      0xffff
004d14:  ffff  dw      0xffff
004d16:  ffff  dw      0xffff
004d18:  ffff  dw      0xffff
004d1a:  ffff  dw      0xffff
004d1c:  ffff  dw      0xffff
004d1e:  ffff  dw      0xffff
004d20:  ffff  dw      0xffff
004d22:  ffff  dw      0xffff
004d24:  ffff  dw      0xffff
004d26:  ffff  dw      0xffff
004d28:  ffff  dw      0xffff
004d2a:  ffff  dw      0xffff
004d2c:  ffff  dw      0xffff
004d2e:  ffff  dw      0xffff
004d30:  ffff  dw      0xffff
004d32:  ffff  dw      0xffff
004d34:  ffff  dw      0xffff
004d36:  ffff  dw      0xffff
004d38:  ffff  dw      0xffff
004d3a:  ffff  dw      0xffff
004d3c:  ffff  dw      0xffff
004d3e:  ffff  dw      0xffff
004d40:  ffff  dw      0xffff
004d42:  ffff  dw      0xffff
004d44:  ffff  dw      0xffff
004d46:  ffff  dw      0xffff
004d48:  ffff  dw      0xffff
004d4a:  ffff  dw      0xffff
004d4c:  ffff  dw      0xffff
004d4e:  ffff  dw      0xffff
004d50:  ffff  dw      0xffff
004d52:  ffff  dw      0xffff
004d54:  ffff  dw      0xffff
004d56:  ffff  dw      0xffff
004d58:  ffff  dw      0xffff
004d5a:  ffff  dw      0xffff
004d5c:  ffff  dw      0xffff
004d5e:  ffff  dw      0xffff
004d60:  ffff  dw      0xffff
004d62:  ffff  dw      0xffff
004d64:  ffff  dw      0xffff
004d66:  ffff  dw      0xffff
004d68:  ffff  dw      0xffff
004d6a:  ffff  dw      0xffff
004d6c:  ffff  dw      0xffff
004d6e:  ffff  dw      0xffff
004d70:  ffff  dw      0xffff
004d72:  ffff  dw      0xffff
004d74:  ffff  dw      0xffff
004d76:  ffff  dw      0xffff
004d78:  ffff  dw      0xffff
004d7a:  ffff  dw      0xffff
004d7c:  ffff  dw      0xffff
004d7e:  ffff  dw      0xffff
004d80:  ffff  dw      0xffff
004d82:  ffff  dw      0xffff
004d84:  ffff  dw      0xffff
004d86:  ffff  dw      0xffff
004d88:  ffff  dw      0xffff
004d8a:  ffff  dw      0xffff
004d8c:  ffff  dw      0xffff
004d8e:  ffff  dw      0xffff
004d90:  ffff  dw      0xffff
004d92:  ffff  dw      0xffff
004d94:  ffff  dw      0xffff
004d96:  ffff  dw      0xffff
004d98:  ffff  dw      0xffff
004d9a:  ffff  dw      0xffff
004d9c:  ffff  dw      0xffff
004d9e:  ffff  dw      0xffff
004da0:  ffff  dw      0xffff
004da2:  ffff  dw      0xffff
004da4:  ffff  dw      0xffff
004da6:  ffff  dw      0xffff
004da8:  ffff  dw      0xffff
004daa:  ffff  dw      0xffff
004dac:  ffff  dw      0xffff
004dae:  ffff  dw      0xffff
004db0:  ffff  dw      0xffff
004db2:  ffff  dw      0xffff
004db4:  ffff  dw      0xffff
004db6:  ffff  dw      0xffff
004db8:  ffff  dw      0xffff
004dba:  ffff  dw      0xffff
004dbc:  ffff  dw      0xffff
004dbe:  ffff  dw      0xffff
004dc0:  ffff  dw      0xffff
004dc2:  ffff  dw      0xffff
004dc4:  ffff  dw      0xffff
004dc6:  ffff  dw      0xffff
004dc8:  ffff  dw      0xffff
004dca:  ffff  dw      0xffff
004dcc:  ffff  dw      0xffff
004dce:  ffff  dw      0xffff
004dd0:  ffff  dw      0xffff
004dd2:  ffff  dw      0xffff
004dd4:  ffff  dw      0xffff
004dd6:  ffff  dw      0xffff
004dd8:  ffff  dw      0xffff
004dda:  ffff  dw      0xffff
004ddc:  ffff  dw      0xffff
004dde:  ffff  dw      0xffff
004de0:  ffff  dw      0xffff
004de2:  ffff  dw      0xffff
004de4:  ffff  dw      0xffff
004de6:  ffff  dw      0xffff
004de8:  ffff  dw      0xffff
004dea:  ffff  dw      0xffff
004dec:  ffff  dw      0xffff
004dee:  ffff  dw      0xffff
004df0:  ffff  dw      0xffff
004df2:  ffff  dw      0xffff
004df4:  ffff  dw      0xffff
004df6:  ffff  dw      0xffff
004df8:  ffff  dw      0xffff
004dfa:  ffff  dw      0xffff
004dfc:  ffff  dw      0xffff
004dfe:  ffff  dw      0xffff
004e00:  ffff  dw      0xffff
004e02:  ffff  dw      0xffff
004e04:  ffff  dw      0xffff
004e06:  ffff  dw      0xffff
004e08:  ffff  dw      0xffff
004e0a:  ffff  dw      0xffff
004e0c:  ffff  dw      0xffff
004e0e:  ffff  dw      0xffff
004e10:  ffff  dw      0xffff
004e12:  ffff  dw      0xffff
004e14:  ffff  dw      0xffff
004e16:  ffff  dw      0xffff
004e18:  ffff  dw      0xffff
004e1a:  ffff  dw      0xffff
004e1c:  ffff  dw      0xffff
004e1e:  ffff  dw      0xffff
004e20:  ffff  dw      0xffff
004e22:  ffff  dw      0xffff
004e24:  ffff  dw      0xffff
004e26:  ffff  dw      0xffff
004e28:  ffff  dw      0xffff
004e2a:  ffff  dw      0xffff
004e2c:  ffff  dw      0xffff
004e2e:  ffff  dw      0xffff
004e30:  ffff  dw      0xffff
004e32:  ffff  dw      0xffff
004e34:  ffff  dw      0xffff
004e36:  ffff  dw      0xffff
004e38:  ffff  dw      0xffff
004e3a:  ffff  dw      0xffff
004e3c:  ffff  dw      0xffff
004e3e:  ffff  dw      0xffff
004e40:  ffff  dw      0xffff
004e42:  ffff  dw      0xffff
004e44:  ffff  dw      0xffff
004e46:  ffff  dw      0xffff
004e48:  ffff  dw      0xffff
004e4a:  ffff  dw      0xffff
004e4c:  ffff  dw      0xffff
004e4e:  ffff  dw      0xffff
004e50:  ffff  dw      0xffff
004e52:  ffff  dw      0xffff
004e54:  ffff  dw      0xffff
004e56:  ffff  dw      0xffff
004e58:  ffff  dw      0xffff
004e5a:  ffff  dw      0xffff
004e5c:  ffff  dw      0xffff
004e5e:  ffff  dw      0xffff
004e60:  ffff  dw      0xffff
004e62:  ffff  dw      0xffff
004e64:  ffff  dw      0xffff
004e66:  ffff  dw      0xffff
004e68:  ffff  dw      0xffff
004e6a:  ffff  dw      0xffff
004e6c:  ffff  dw      0xffff
004e6e:  ffff  dw      0xffff
004e70:  ffff  dw      0xffff
004e72:  ffff  dw      0xffff
004e74:  ffff  dw      0xffff
004e76:  ffff  dw      0xffff
004e78:  ffff  dw      0xffff
004e7a:  ffff  dw      0xffff
004e7c:  ffff  dw      0xffff
004e7e:  ffff  dw      0xffff
004e80:  ffff  dw      0xffff
004e82:  ffff  dw      0xffff
004e84:  ffff  dw      0xffff
004e86:  ffff  dw      0xffff
004e88:  ffff  dw      0xffff
004e8a:  ffff  dw      0xffff
004e8c:  ffff  dw      0xffff
004e8e:  ffff  dw      0xffff
004e90:  ffff  dw      0xffff
004e92:  ffff  dw      0xffff
004e94:  ffff  dw      0xffff
004e96:  ffff  dw      0xffff
004e98:  ffff  dw      0xffff
004e9a:  ffff  dw      0xffff
004e9c:  ffff  dw      0xffff
004e9e:  ffff  dw      0xffff
004ea0:  ffff  dw      0xffff
004ea2:  ffff  dw      0xffff
004ea4:  ffff  dw      0xffff
004ea6:  ffff  dw      0xffff
004ea8:  ffff  dw      0xffff
004eaa:  ffff  dw      0xffff
004eac:  ffff  dw      0xffff
004eae:  ffff  dw      0xffff
004eb0:  ffff  dw      0xffff
004eb2:  ffff  dw      0xffff
004eb4:  ffff  dw      0xffff
004eb6:  ffff  dw      0xffff
004eb8:  ffff  dw      0xffff
004eba:  ffff  dw      0xffff
004ebc:  ffff  dw      0xffff
004ebe:  ffff  dw      0xffff
004ec0:  ffff  dw      0xffff
004ec2:  ffff  dw      0xffff
004ec4:  ffff  dw      0xffff
004ec6:  ffff  dw      0xffff
004ec8:  ffff  dw      0xffff
004eca:  ffff  dw      0xffff
004ecc:  ffff  dw      0xffff
004ece:  ffff  dw      0xffff
004ed0:  ffff  dw      0xffff
004ed2:  ffff  dw      0xffff
004ed4:  ffff  dw      0xffff
004ed6:  ffff  dw      0xffff
004ed8:  ffff  dw      0xffff
004eda:  ffff  dw      0xffff
004edc:  ffff  dw      0xffff
004ede:  ffff  dw      0xffff
004ee0:  ffff  dw      0xffff
004ee2:  ffff  dw      0xffff
004ee4:  ffff  dw      0xffff
004ee6:  ffff  dw      0xffff
004ee8:  ffff  dw      0xffff
004eea:  ffff  dw      0xffff
004eec:  ffff  dw      0xffff
004eee:  ffff  dw      0xffff
004ef0:  ffff  dw      0xffff
004ef2:  ffff  dw      0xffff
004ef4:  ffff  dw      0xffff
004ef6:  ffff  dw      0xffff
004ef8:  ffff  dw      0xffff
004efa:  ffff  dw      0xffff
004efc:  ffff  dw      0xffff
004efe:  ffff  dw      0xffff
004f00:  ffff  dw      0xffff
004f02:  ffff  dw      0xffff
004f04:  ffff  dw      0xffff
004f06:  ffff  dw      0xffff
004f08:  ffff  dw      0xffff
004f0a:  ffff  dw      0xffff
004f0c:  ffff  dw      0xffff
004f0e:  ffff  dw      0xffff
004f10:  ffff  dw      0xffff
004f12:  ffff  dw      0xffff
004f14:  ffff  dw      0xffff
004f16:  ffff  dw      0xffff
004f18:  ffff  dw      0xffff
004f1a:  ffff  dw      0xffff
004f1c:  ffff  dw      0xffff
004f1e:  ffff  dw      0xffff
004f20:  ffff  dw      0xffff
004f22:  ffff  dw      0xffff
004f24:  ffff  dw      0xffff
004f26:  ffff  dw      0xffff
004f28:  ffff  dw      0xffff
004f2a:  ffff  dw      0xffff
004f2c:  ffff  dw      0xffff
004f2e:  ffff  dw      0xffff
004f30:  ffff  dw      0xffff
004f32:  ffff  dw      0xffff
004f34:  ffff  dw      0xffff
004f36:  ffff  dw      0xffff
004f38:  ffff  dw      0xffff
004f3a:  ffff  dw      0xffff
004f3c:  ffff  dw      0xffff
004f3e:  ffff  dw      0xffff
004f40:  ffff  dw      0xffff
004f42:  ffff  dw      0xffff
004f44:  ffff  dw      0xffff
004f46:  ffff  dw      0xffff
004f48:  ffff  dw      0xffff
004f4a:  ffff  dw      0xffff
004f4c:  ffff  dw      0xffff
004f4e:  ffff  dw      0xffff
004f50:  ffff  dw      0xffff
004f52:  ffff  dw      0xffff
004f54:  ffff  dw      0xffff
004f56:  ffff  dw      0xffff
004f58:  ffff  dw      0xffff
004f5a:  ffff  dw      0xffff
004f5c:  ffff  dw      0xffff
004f5e:  ffff  dw      0xffff
004f60:  ffff  dw      0xffff
004f62:  ffff  dw      0xffff
004f64:  ffff  dw      0xffff
004f66:  ffff  dw      0xffff
004f68:  ffff  dw      0xffff
004f6a:  ffff  dw      0xffff
004f6c:  ffff  dw      0xffff
004f6e:  ffff  dw      0xffff
004f70:  ffff  dw      0xffff
004f72:  ffff  dw      0xffff
004f74:  ffff  dw      0xffff
004f76:  ffff  dw      0xffff
004f78:  ffff  dw      0xffff
004f7a:  ffff  dw      0xffff
004f7c:  ffff  dw      0xffff
004f7e:  ffff  dw      0xffff
004f80:  ffff  dw      0xffff
004f82:  ffff  dw      0xffff
004f84:  ffff  dw      0xffff
004f86:  ffff  dw      0xffff
004f88:  ffff  dw      0xffff
004f8a:  ffff  dw      0xffff
004f8c:  ffff  dw      0xffff
004f8e:  ffff  dw      0xffff
004f90:  ffff  dw      0xffff
004f92:  ffff  dw      0xffff
004f94:  ffff  dw      0xffff
004f96:  ffff  dw      0xffff
004f98:  ffff  dw      0xffff
004f9a:  ffff  dw      0xffff
004f9c:  ffff  dw      0xffff
004f9e:  ffff  dw      0xffff
004fa0:  ffff  dw      0xffff
004fa2:  ffff  dw      0xffff
004fa4:  ffff  dw      0xffff
004fa6:  ffff  dw      0xffff
004fa8:  ffff  dw      0xffff
004faa:  ffff  dw      0xffff
004fac:  ffff  dw      0xffff
004fae:  ffff  dw      0xffff
004fb0:  ffff  dw      0xffff
004fb2:  ffff  dw      0xffff
004fb4:  ffff  dw      0xffff
004fb6:  ffff  dw      0xffff
004fb8:  ffff  dw      0xffff
004fba:  ffff  dw      0xffff
004fbc:  ffff  dw      0xffff
004fbe:  ffff  dw      0xffff
004fc0:  ffff  dw      0xffff
004fc2:  ffff  dw      0xffff
004fc4:  ffff  dw      0xffff
004fc6:  ffff  dw      0xffff
004fc8:  ffff  dw      0xffff
004fca:  ffff  dw      0xffff
004fcc:  ffff  dw      0xffff
004fce:  ffff  dw      0xffff
004fd0:  ffff  dw      0xffff
004fd2:  ffff  dw      0xffff
004fd4:  ffff  dw      0xffff
004fd6:  ffff  dw      0xffff
004fd8:  ffff  dw      0xffff
004fda:  ffff  dw      0xffff
004fdc:  ffff  dw      0xffff
004fde:  ffff  dw      0xffff
004fe0:  ffff  dw      0xffff
004fe2:  ffff  dw      0xffff
004fe4:  ffff  dw      0xffff
004fe6:  ffff  dw      0xffff
004fe8:  ffff  dw      0xffff
004fea:  ffff  dw      0xffff
004fec:  ffff  dw      0xffff
004fee:  ffff  dw      0xffff
004ff0:  ffff  dw      0xffff
004ff2:  ffff  dw      0xffff
004ff4:  ffff  dw      0xffff
004ff6:  ffff  dw      0xffff
004ff8:  ffff  dw      0xffff
004ffa:  ffff  dw      0xffff
004ffc:  ffff  dw      0xffff
004ffe:  ffff  dw      0xffff
005000:  ffff  dw      0xffff
005002:  ffff  dw      0xffff
005004:  ffff  dw      0xffff
005006:  ffff  dw      0xffff
005008:  ffff  dw      0xffff
00500a:  ffff  dw      0xffff
00500c:  ffff  dw      0xffff
00500e:  ffff  dw      0xffff
005010:  ffff  dw      0xffff
005012:  ffff  dw      0xffff
005014:  ffff  dw      0xffff
005016:  ffff  dw      0xffff
005018:  ffff  dw      0xffff
00501a:  ffff  dw      0xffff
00501c:  ffff  dw      0xffff
00501e:  ffff  dw      0xffff
005020:  ffff  dw      0xffff
005022:  ffff  dw      0xffff
005024:  ffff  dw      0xffff
005026:  ffff  dw      0xffff
005028:  ffff  dw      0xffff
00502a:  ffff  dw      0xffff
00502c:  ffff  dw      0xffff
00502e:  ffff  dw      0xffff
005030:  ffff  dw      0xffff
005032:  ffff  dw      0xffff
005034:  ffff  dw      0xffff
005036:  ffff  dw      0xffff
005038:  ffff  dw      0xffff
00503a:  ffff  dw      0xffff
00503c:  ffff  dw      0xffff
00503e:  ffff  dw      0xffff
005040:  ffff  dw      0xffff
005042:  ffff  dw      0xffff
005044:  ffff  dw      0xffff
005046:  ffff  dw      0xffff
005048:  ffff  dw      0xffff
00504a:  ffff  dw      0xffff
00504c:  ffff  dw      0xffff
00504e:  ffff  dw      0xffff
005050:  ffff  dw      0xffff
005052:  ffff  dw      0xffff
005054:  ffff  dw      0xffff
005056:  ffff  dw      0xffff
005058:  ffff  dw      0xffff
00505a:  ffff  dw      0xffff
00505c:  ffff  dw      0xffff
00505e:  ffff  dw      0xffff
005060:  ffff  dw      0xffff
005062:  ffff  dw      0xffff
005064:  ffff  dw      0xffff
005066:  ffff  dw      0xffff
005068:  ffff  dw      0xffff
00506a:  ffff  dw      0xffff
00506c:  ffff  dw      0xffff
00506e:  ffff  dw      0xffff
005070:  ffff  dw      0xffff
005072:  ffff  dw      0xffff
005074:  ffff  dw      0xffff
005076:  ffff  dw      0xffff
005078:  ffff  dw      0xffff
00507a:  ffff  dw      0xffff
00507c:  ffff  dw      0xffff
00507e:  ffff  dw      0xffff
005080:  ffff  dw      0xffff
005082:  ffff  dw      0xffff
005084:  ffff  dw      0xffff
005086:  ffff  dw      0xffff
005088:  ffff  dw      0xffff
00508a:  ffff  dw      0xffff
00508c:  ffff  dw      0xffff
00508e:  ffff  dw      0xffff
005090:  ffff  dw      0xffff
005092:  ffff  dw      0xffff
005094:  ffff  dw      0xffff
005096:  ffff  dw      0xffff
005098:  ffff  dw      0xffff
00509a:  ffff  dw      0xffff
00509c:  ffff  dw      0xffff
00509e:  ffff  dw      0xffff
0050a0:  ffff  dw      0xffff
0050a2:  ffff  dw      0xffff
0050a4:  ffff  dw      0xffff
0050a6:  ffff  dw      0xffff
0050a8:  ffff  dw      0xffff
0050aa:  ffff  dw      0xffff
0050ac:  ffff  dw      0xffff
0050ae:  ffff  dw      0xffff
0050b0:  ffff  dw      0xffff
0050b2:  ffff  dw      0xffff
0050b4:  ffff  dw      0xffff
0050b6:  ffff  dw      0xffff
0050b8:  ffff  dw      0xffff
0050ba:  ffff  dw      0xffff
0050bc:  ffff  dw      0xffff
0050be:  ffff  dw      0xffff
0050c0:  ffff  dw      0xffff
0050c2:  ffff  dw      0xffff
0050c4:  ffff  dw      0xffff
0050c6:  ffff  dw      0xffff
0050c8:  ffff  dw      0xffff
0050ca:  ffff  dw      0xffff
0050cc:  ffff  dw      0xffff
0050ce:  ffff  dw      0xffff
0050d0:  ffff  dw      0xffff
0050d2:  ffff  dw      0xffff
0050d4:  ffff  dw      0xffff
0050d6:  ffff  dw      0xffff
0050d8:  ffff  dw      0xffff
0050da:  ffff  dw      0xffff
0050dc:  ffff  dw      0xffff
0050de:  ffff  dw      0xffff
0050e0:  ffff  dw      0xffff
0050e2:  ffff  dw      0xffff
0050e4:  ffff  dw      0xffff
0050e6:  ffff  dw      0xffff
0050e8:  ffff  dw      0xffff
0050ea:  ffff  dw      0xffff
0050ec:  ffff  dw      0xffff
0050ee:  ffff  dw      0xffff
0050f0:  ffff  dw      0xffff
0050f2:  ffff  dw      0xffff
0050f4:  ffff  dw      0xffff
0050f6:  ffff  dw      0xffff
0050f8:  ffff  dw      0xffff
0050fa:  ffff  dw      0xffff
0050fc:  ffff  dw      0xffff
0050fe:  ffff  dw      0xffff
005100:  ffff  dw      0xffff
005102:  ffff  dw      0xffff
005104:  ffff  dw      0xffff
005106:  ffff  dw      0xffff
005108:  ffff  dw      0xffff
00510a:  ffff  dw      0xffff
00510c:  ffff  dw      0xffff
00510e:  ffff  dw      0xffff
005110:  ffff  dw      0xffff
005112:  ffff  dw      0xffff
005114:  ffff  dw      0xffff
005116:  ffff  dw      0xffff
005118:  ffff  dw      0xffff
00511a:  ffff  dw      0xffff
00511c:  ffff  dw      0xffff
00511e:  ffff  dw      0xffff
005120:  ffff  dw      0xffff
005122:  ffff  dw      0xffff
005124:  ffff  dw      0xffff
005126:  ffff  dw      0xffff
005128:  ffff  dw      0xffff
00512a:  ffff  dw      0xffff
00512c:  ffff  dw      0xffff
00512e:  ffff  dw      0xffff
005130:  ffff  dw      0xffff
005132:  ffff  dw      0xffff
005134:  ffff  dw      0xffff
005136:  ffff  dw      0xffff
005138:  ffff  dw      0xffff
00513a:  ffff  dw      0xffff
00513c:  ffff  dw      0xffff
00513e:  ffff  dw      0xffff
005140:  ffff  dw      0xffff
005142:  ffff  dw      0xffff
005144:  ffff  dw      0xffff
005146:  ffff  dw      0xffff
005148:  ffff  dw      0xffff
00514a:  ffff  dw      0xffff
00514c:  ffff  dw      0xffff
00514e:  ffff  dw      0xffff
005150:  ffff  dw      0xffff
005152:  ffff  dw      0xffff
005154:  ffff  dw      0xffff
005156:  ffff  dw      0xffff
005158:  ffff  dw      0xffff
00515a:  ffff  dw      0xffff
00515c:  ffff  dw      0xffff
00515e:  ffff  dw      0xffff
005160:  ffff  dw      0xffff
005162:  ffff  dw      0xffff
005164:  ffff  dw      0xffff
005166:  ffff  dw      0xffff
005168:  ffff  dw      0xffff
00516a:  ffff  dw      0xffff
00516c:  ffff  dw      0xffff
00516e:  ffff  dw      0xffff
005170:  ffff  dw      0xffff
005172:  ffff  dw      0xffff
005174:  ffff  dw      0xffff
005176:  ffff  dw      0xffff
005178:  ffff  dw      0xffff
00517a:  ffff  dw      0xffff
00517c:  ffff  dw      0xffff
00517e:  ffff  dw      0xffff
005180:  ffff  dw      0xffff
005182:  ffff  dw      0xffff
005184:  ffff  dw      0xffff
005186:  ffff  dw      0xffff
005188:  ffff  dw      0xffff
00518a:  ffff  dw      0xffff
00518c:  ffff  dw      0xffff
00518e:  ffff  dw      0xffff
005190:  ffff  dw      0xffff
005192:  ffff  dw      0xffff
005194:  ffff  dw      0xffff
005196:  ffff  dw      0xffff
005198:  ffff  dw      0xffff
00519a:  ffff  dw      0xffff
00519c:  ffff  dw      0xffff
00519e:  ffff  dw      0xffff
0051a0:  ffff  dw      0xffff
0051a2:  ffff  dw      0xffff
0051a4:  ffff  dw      0xffff
0051a6:  ffff  dw      0xffff
0051a8:  ffff  dw      0xffff
0051aa:  ffff  dw      0xffff
0051ac:  ffff  dw      0xffff
0051ae:  ffff  dw      0xffff
0051b0:  ffff  dw      0xffff
0051b2:  ffff  dw      0xffff
0051b4:  ffff  dw      0xffff
0051b6:  ffff  dw      0xffff
0051b8:  ffff  dw      0xffff
0051ba:  ffff  dw      0xffff
0051bc:  ffff  dw      0xffff
0051be:  ffff  dw      0xffff
0051c0:  ffff  dw      0xffff
0051c2:  ffff  dw      0xffff
0051c4:  ffff  dw      0xffff
0051c6:  ffff  dw      0xffff
0051c8:  ffff  dw      0xffff
0051ca:  ffff  dw      0xffff
0051cc:  ffff  dw      0xffff
0051ce:  ffff  dw      0xffff
0051d0:  ffff  dw      0xffff
0051d2:  ffff  dw      0xffff
0051d4:  ffff  dw      0xffff
0051d6:  ffff  dw      0xffff
0051d8:  ffff  dw      0xffff
0051da:  ffff  dw      0xffff
0051dc:  ffff  dw      0xffff
0051de:  ffff  dw      0xffff
0051e0:  ffff  dw      0xffff
0051e2:  ffff  dw      0xffff
0051e4:  ffff  dw      0xffff
0051e6:  ffff  dw      0xffff
0051e8:  ffff  dw      0xffff
0051ea:  ffff  dw      0xffff
0051ec:  ffff  dw      0xffff
0051ee:  ffff  dw      0xffff
0051f0:  ffff  dw      0xffff
0051f2:  ffff  dw      0xffff
0051f4:  ffff  dw      0xffff
0051f6:  ffff  dw      0xffff
0051f8:  ffff  dw      0xffff
0051fa:  ffff  dw      0xffff
0051fc:  ffff  dw      0xffff
0051fe:  ffff  dw      0xffff
005200:  ffff  dw      0xffff
005202:  ffff  dw      0xffff
005204:  ffff  dw      0xffff
005206:  ffff  dw      0xffff
005208:  ffff  dw      0xffff
00520a:  ffff  dw      0xffff
00520c:  ffff  dw      0xffff
00520e:  ffff  dw      0xffff
005210:  ffff  dw      0xffff
005212:  ffff  dw      0xffff
005214:  ffff  dw      0xffff
005216:  ffff  dw      0xffff
005218:  ffff  dw      0xffff
00521a:  ffff  dw      0xffff
00521c:  ffff  dw      0xffff
00521e:  ffff  dw      0xffff
005220:  ffff  dw      0xffff
005222:  ffff  dw      0xffff
005224:  ffff  dw      0xffff
005226:  ffff  dw      0xffff
005228:  ffff  dw      0xffff
00522a:  ffff  dw      0xffff
00522c:  ffff  dw      0xffff
00522e:  ffff  dw      0xffff
005230:  ffff  dw      0xffff
005232:  ffff  dw      0xffff
005234:  ffff  dw      0xffff
005236:  ffff  dw      0xffff
005238:  ffff  dw      0xffff
00523a:  ffff  dw      0xffff
00523c:  ffff  dw      0xffff
00523e:  ffff  dw      0xffff
005240:  ffff  dw      0xffff
005242:  ffff  dw      0xffff
005244:  ffff  dw      0xffff
005246:  ffff  dw      0xffff
005248:  ffff  dw      0xffff
00524a:  ffff  dw      0xffff
00524c:  ffff  dw      0xffff
00524e:  ffff  dw      0xffff
005250:  ffff  dw      0xffff
005252:  ffff  dw      0xffff
005254:  ffff  dw      0xffff
005256:  ffff  dw      0xffff
005258:  ffff  dw      0xffff
00525a:  ffff  dw      0xffff
00525c:  ffff  dw      0xffff
00525e:  ffff  dw      0xffff
005260:  ffff  dw      0xffff
005262:  ffff  dw      0xffff
005264:  ffff  dw      0xffff
005266:  ffff  dw      0xffff
005268:  ffff  dw      0xffff
00526a:  ffff  dw      0xffff
00526c:  ffff  dw      0xffff
00526e:  ffff  dw      0xffff
005270:  ffff  dw      0xffff
005272:  ffff  dw      0xffff
005274:  ffff  dw      0xffff
005276:  ffff  dw      0xffff
005278:  ffff  dw      0xffff
00527a:  ffff  dw      0xffff
00527c:  ffff  dw      0xffff
00527e:  ffff  dw      0xffff
005280:  ffff  dw      0xffff
005282:  ffff  dw      0xffff
005284:  ffff  dw      0xffff
005286:  ffff  dw      0xffff
005288:  ffff  dw      0xffff
00528a:  ffff  dw      0xffff
00528c:  ffff  dw      0xffff
00528e:  ffff  dw      0xffff
005290:  ffff  dw      0xffff
005292:  ffff  dw      0xffff
005294:  ffff  dw      0xffff
005296:  ffff  dw      0xffff
005298:  ffff  dw      0xffff
00529a:  ffff  dw      0xffff
00529c:  ffff  dw      0xffff
00529e:  ffff  dw      0xffff
0052a0:  ffff  dw      0xffff
0052a2:  ffff  dw      0xffff
0052a4:  ffff  dw      0xffff
0052a6:  ffff  dw      0xffff
0052a8:  ffff  dw      0xffff
0052aa:  ffff  dw      0xffff
0052ac:  ffff  dw      0xffff
0052ae:  ffff  dw      0xffff
0052b0:  ffff  dw      0xffff
0052b2:  ffff  dw      0xffff
0052b4:  ffff  dw      0xffff
0052b6:  ffff  dw      0xffff
0052b8:  ffff  dw      0xffff
0052ba:  ffff  dw      0xffff
0052bc:  ffff  dw      0xffff
0052be:  ffff  dw      0xffff
0052c0:  ffff  dw      0xffff
0052c2:  ffff  dw      0xffff
0052c4:  ffff  dw      0xffff
0052c6:  ffff  dw      0xffff
0052c8:  ffff  dw      0xffff
0052ca:  ffff  dw      0xffff
0052cc:  ffff  dw      0xffff
0052ce:  ffff  dw      0xffff
0052d0:  ffff  dw      0xffff
0052d2:  ffff  dw      0xffff
0052d4:  ffff  dw      0xffff
0052d6:  ffff  dw      0xffff
0052d8:  ffff  dw      0xffff
0052da:  ffff  dw      0xffff
0052dc:  ffff  dw      0xffff
0052de:  ffff  dw      0xffff
0052e0:  ffff  dw      0xffff
0052e2:  ffff  dw      0xffff
0052e4:  ffff  dw      0xffff
0052e6:  ffff  dw      0xffff
0052e8:  ffff  dw      0xffff
0052ea:  ffff  dw      0xffff
0052ec:  ffff  dw      0xffff
0052ee:  ffff  dw      0xffff
0052f0:  ffff  dw      0xffff
0052f2:  ffff  dw      0xffff
0052f4:  ffff  dw      0xffff
0052f6:  ffff  dw      0xffff
0052f8:  ffff  dw      0xffff
0052fa:  ffff  dw      0xffff
0052fc:  ffff  dw      0xffff
0052fe:  ffff  dw      0xffff
005300:  ffff  dw      0xffff
005302:  ffff  dw      0xffff
005304:  ffff  dw      0xffff
005306:  ffff  dw      0xffff
005308:  ffff  dw      0xffff
00530a:  ffff  dw      0xffff
00530c:  ffff  dw      0xffff
00530e:  ffff  dw      0xffff
005310:  ffff  dw      0xffff
005312:  ffff  dw      0xffff
005314:  ffff  dw      0xffff
005316:  ffff  dw      0xffff
005318:  ffff  dw      0xffff
00531a:  ffff  dw      0xffff
00531c:  ffff  dw      0xffff
00531e:  ffff  dw      0xffff
005320:  ffff  dw      0xffff
005322:  ffff  dw      0xffff
005324:  ffff  dw      0xffff
005326:  ffff  dw      0xffff
005328:  ffff  dw      0xffff
00532a:  ffff  dw      0xffff
00532c:  ffff  dw      0xffff
00532e:  ffff  dw      0xffff
005330:  ffff  dw      0xffff
005332:  ffff  dw      0xffff
005334:  ffff  dw      0xffff
005336:  ffff  dw      0xffff
005338:  ffff  dw      0xffff
00533a:  ffff  dw      0xffff
00533c:  ffff  dw      0xffff
00533e:  ffff  dw      0xffff
005340:  ffff  dw      0xffff
005342:  ffff  dw      0xffff
005344:  ffff  dw      0xffff
005346:  ffff  dw      0xffff
005348:  ffff  dw      0xffff
00534a:  ffff  dw      0xffff
00534c:  ffff  dw      0xffff
00534e:  ffff  dw      0xffff
005350:  ffff  dw      0xffff
005352:  ffff  dw      0xffff
005354:  ffff  dw      0xffff
005356:  ffff  dw      0xffff
005358:  ffff  dw      0xffff
00535a:  ffff  dw      0xffff
00535c:  ffff  dw      0xffff
00535e:  ffff  dw      0xffff
005360:  ffff  dw      0xffff
005362:  ffff  dw      0xffff
005364:  ffff  dw      0xffff
005366:  ffff  dw      0xffff
005368:  ffff  dw      0xffff
00536a:  ffff  dw      0xffff
00536c:  ffff  dw      0xffff
00536e:  ffff  dw      0xffff
005370:  ffff  dw      0xffff
005372:  ffff  dw      0xffff
005374:  ffff  dw      0xffff
005376:  ffff  dw      0xffff
005378:  ffff  dw      0xffff
00537a:  ffff  dw      0xffff
00537c:  ffff  dw      0xffff
00537e:  ffff  dw      0xffff
005380:  ffff  dw      0xffff
005382:  ffff  dw      0xffff
005384:  ffff  dw      0xffff
005386:  ffff  dw      0xffff
005388:  ffff  dw      0xffff
00538a:  ffff  dw      0xffff
00538c:  ffff  dw      0xffff
00538e:  ffff  dw      0xffff
005390:  ffff  dw      0xffff
005392:  ffff  dw      0xffff
005394:  ffff  dw      0xffff
005396:  ffff  dw      0xffff
005398:  ffff  dw      0xffff
00539a:  ffff  dw      0xffff
00539c:  ffff  dw      0xffff
00539e:  ffff  dw      0xffff
0053a0:  ffff  dw      0xffff
0053a2:  ffff  dw      0xffff
0053a4:  ffff  dw      0xffff
0053a6:  ffff  dw      0xffff
0053a8:  ffff  dw      0xffff
0053aa:  ffff  dw      0xffff
0053ac:  ffff  dw      0xffff
0053ae:  ffff  dw      0xffff
0053b0:  ffff  dw      0xffff
0053b2:  ffff  dw      0xffff
0053b4:  ffff  dw      0xffff
0053b6:  ffff  dw      0xffff
0053b8:  ffff  dw      0xffff
0053ba:  ffff  dw      0xffff
0053bc:  ffff  dw      0xffff
0053be:  ffff  dw      0xffff
0053c0:  ffff  dw      0xffff
0053c2:  ffff  dw      0xffff
0053c4:  ffff  dw      0xffff
0053c6:  ffff  dw      0xffff
0053c8:  ffff  dw      0xffff
0053ca:  ffff  dw      0xffff
0053cc:  ffff  dw      0xffff
0053ce:  ffff  dw      0xffff
0053d0:  ffff  dw      0xffff
0053d2:  ffff  dw      0xffff
0053d4:  ffff  dw      0xffff
0053d6:  ffff  dw      0xffff
0053d8:  ffff  dw      0xffff
0053da:  ffff  dw      0xffff
0053dc:  ffff  dw      0xffff
0053de:  ffff  dw      0xffff
0053e0:  ffff  dw      0xffff
0053e2:  ffff  dw      0xffff
0053e4:  ffff  dw      0xffff
0053e6:  ffff  dw      0xffff
0053e8:  ffff  dw      0xffff
0053ea:  ffff  dw      0xffff
0053ec:  ffff  dw      0xffff
0053ee:  ffff  dw      0xffff
0053f0:  ffff  dw      0xffff
0053f2:  ffff  dw      0xffff
0053f4:  ffff  dw      0xffff
0053f6:  ffff  dw      0xffff
0053f8:  ffff  dw      0xffff
0053fa:  ffff  dw      0xffff
0053fc:  ffff  dw      0xffff
0053fe:  ffff  dw      0xffff
005400:  ffff  dw      0xffff
005402:  ffff  dw      0xffff
005404:  ffff  dw      0xffff
005406:  ffff  dw      0xffff
005408:  ffff  dw      0xffff
00540a:  ffff  dw      0xffff
00540c:  ffff  dw      0xffff
00540e:  ffff  dw      0xffff
005410:  ffff  dw      0xffff
005412:  ffff  dw      0xffff
005414:  ffff  dw      0xffff
005416:  ffff  dw      0xffff
005418:  ffff  dw      0xffff
00541a:  ffff  dw      0xffff
00541c:  ffff  dw      0xffff
00541e:  ffff  dw      0xffff
005420:  ffff  dw      0xffff
005422:  ffff  dw      0xffff
005424:  ffff  dw      0xffff
005426:  ffff  dw      0xffff
005428:  ffff  dw      0xffff
00542a:  ffff  dw      0xffff
00542c:  ffff  dw      0xffff
00542e:  ffff  dw      0xffff
005430:  ffff  dw      0xffff
005432:  ffff  dw      0xffff
005434:  ffff  dw      0xffff
005436:  ffff  dw      0xffff
005438:  ffff  dw      0xffff
00543a:  ffff  dw      0xffff
00543c:  ffff  dw      0xffff
00543e:  ffff  dw      0xffff
005440:  ffff  dw      0xffff
005442:  ffff  dw      0xffff
005444:  ffff  dw      0xffff
005446:  ffff  dw      0xffff
005448:  ffff  dw      0xffff
00544a:  ffff  dw      0xffff
00544c:  ffff  dw      0xffff
00544e:  ffff  dw      0xffff
005450:  ffff  dw      0xffff
005452:  ffff  dw      0xffff
005454:  ffff  dw      0xffff
005456:  ffff  dw      0xffff
005458:  ffff  dw      0xffff
00545a:  ffff  dw      0xffff
00545c:  ffff  dw      0xffff
00545e:  ffff  dw      0xffff
005460:  ffff  dw      0xffff
005462:  ffff  dw      0xffff
005464:  ffff  dw      0xffff
005466:  ffff  dw      0xffff
005468:  ffff  dw      0xffff
00546a:  ffff  dw      0xffff
00546c:  ffff  dw      0xffff
00546e:  ffff  dw      0xffff
005470:  ffff  dw      0xffff
005472:  ffff  dw      0xffff
005474:  ffff  dw      0xffff
005476:  ffff  dw      0xffff
005478:  ffff  dw      0xffff
00547a:  ffff  dw      0xffff
00547c:  ffff  dw      0xffff
00547e:  ffff  dw      0xffff
005480:  ffff  dw      0xffff
005482:  ffff  dw      0xffff
005484:  ffff  dw      0xffff
005486:  ffff  dw      0xffff
005488:  ffff  dw      0xffff
00548a:  ffff  dw      0xffff
00548c:  ffff  dw      0xffff
00548e:  ffff  dw      0xffff
005490:  ffff  dw      0xffff
005492:  ffff  dw      0xffff
005494:  ffff  dw      0xffff
005496:  ffff  dw      0xffff
005498:  ffff  dw      0xffff
00549a:  ffff  dw      0xffff
00549c:  ffff  dw      0xffff
00549e:  ffff  dw      0xffff
0054a0:  ffff  dw      0xffff
0054a2:  ffff  dw      0xffff
0054a4:  ffff  dw      0xffff
0054a6:  ffff  dw      0xffff
0054a8:  ffff  dw      0xffff
0054aa:  ffff  dw      0xffff
0054ac:  ffff  dw      0xffff
0054ae:  ffff  dw      0xffff
0054b0:  ffff  dw      0xffff
0054b2:  ffff  dw      0xffff
0054b4:  ffff  dw      0xffff
0054b6:  ffff  dw      0xffff
0054b8:  ffff  dw      0xffff
0054ba:  ffff  dw      0xffff
0054bc:  ffff  dw      0xffff
0054be:  ffff  dw      0xffff
0054c0:  ffff  dw      0xffff
0054c2:  ffff  dw      0xffff
0054c4:  ffff  dw      0xffff
0054c6:  ffff  dw      0xffff
0054c8:  ffff  dw      0xffff
0054ca:  ffff  dw      0xffff
0054cc:  ffff  dw      0xffff
0054ce:  ffff  dw      0xffff
0054d0:  ffff  dw      0xffff
0054d2:  ffff  dw      0xffff
0054d4:  ffff  dw      0xffff
0054d6:  ffff  dw      0xffff
0054d8:  ffff  dw      0xffff
0054da:  ffff  dw      0xffff
0054dc:  ffff  dw      0xffff
0054de:  ffff  dw      0xffff
0054e0:  ffff  dw      0xffff
0054e2:  ffff  dw      0xffff
0054e4:  ffff  dw      0xffff
0054e6:  ffff  dw      0xffff
0054e8:  ffff  dw      0xffff
0054ea:  ffff  dw      0xffff
0054ec:  ffff  dw      0xffff
0054ee:  ffff  dw      0xffff
0054f0:  ffff  dw      0xffff
0054f2:  ffff  dw      0xffff
0054f4:  ffff  dw      0xffff
0054f6:  ffff  dw      0xffff
0054f8:  ffff  dw      0xffff
0054fa:  ffff  dw      0xffff
0054fc:  ffff  dw      0xffff
0054fe:  ffff  dw      0xffff
005500:  ffff  dw      0xffff
005502:  ffff  dw      0xffff
005504:  ffff  dw      0xffff
005506:  ffff  dw      0xffff
005508:  ffff  dw      0xffff
00550a:  ffff  dw      0xffff
00550c:  ffff  dw      0xffff
00550e:  ffff  dw      0xffff
005510:  ffff  dw      0xffff
005512:  ffff  dw      0xffff
005514:  ffff  dw      0xffff
005516:  ffff  dw      0xffff
005518:  ffff  dw      0xffff
00551a:  ffff  dw      0xffff
00551c:  ffff  dw      0xffff
00551e:  ffff  dw      0xffff
005520:  ffff  dw      0xffff
005522:  ffff  dw      0xffff
005524:  ffff  dw      0xffff
005526:  ffff  dw      0xffff
005528:  ffff  dw      0xffff
00552a:  ffff  dw      0xffff
00552c:  ffff  dw      0xffff
00552e:  ffff  dw      0xffff
005530:  ffff  dw      0xffff
005532:  ffff  dw      0xffff
005534:  ffff  dw      0xffff
005536:  ffff  dw      0xffff
005538:  ffff  dw      0xffff
00553a:  ffff  dw      0xffff
00553c:  ffff  dw      0xffff
00553e:  ffff  dw      0xffff
005540:  ffff  dw      0xffff
005542:  ffff  dw      0xffff
005544:  ffff  dw      0xffff
005546:  ffff  dw      0xffff
005548:  ffff  dw      0xffff
00554a:  ffff  dw      0xffff
00554c:  ffff  dw      0xffff
00554e:  ffff  dw      0xffff
005550:  ffff  dw      0xffff
005552:  ffff  dw      0xffff
005554:  ffff  dw      0xffff
005556:  ffff  dw      0xffff
005558:  ffff  dw      0xffff
00555a:  ffff  dw      0xffff
00555c:  ffff  dw      0xffff
00555e:  ffff  dw      0xffff
005560:  ffff  dw      0xffff
005562:  ffff  dw      0xffff
005564:  ffff  dw      0xffff
005566:  ffff  dw      0xffff
005568:  ffff  dw      0xffff
00556a:  ffff  dw      0xffff
00556c:  ffff  dw      0xffff
00556e:  ffff  dw      0xffff
005570:  ffff  dw      0xffff
005572:  ffff  dw      0xffff
005574:  ffff  dw      0xffff
005576:  ffff  dw      0xffff
005578:  ffff  dw      0xffff
00557a:  ffff  dw      0xffff
00557c:  ffff  dw      0xffff
00557e:  ffff  dw      0xffff
005580:  ffff  dw      0xffff
005582:  ffff  dw      0xffff
005584:  ffff  dw      0xffff
005586:  ffff  dw      0xffff
005588:  ffff  dw      0xffff
00558a:  ffff  dw      0xffff
00558c:  ffff  dw      0xffff
00558e:  ffff  dw      0xffff
005590:  ffff  dw      0xffff
005592:  ffff  dw      0xffff
005594:  ffff  dw      0xffff
005596:  ffff  dw      0xffff
005598:  ffff  dw      0xffff
00559a:  ffff  dw      0xffff
00559c:  ffff  dw      0xffff
00559e:  ffff  dw      0xffff
0055a0:  ffff  dw      0xffff
0055a2:  ffff  dw      0xffff
0055a4:  ffff  dw      0xffff
0055a6:  ffff  dw      0xffff
0055a8:  ffff  dw      0xffff
0055aa:  ffff  dw      0xffff
0055ac:  ffff  dw      0xffff
0055ae:  ffff  dw      0xffff
0055b0:  ffff  dw      0xffff
0055b2:  ffff  dw      0xffff
0055b4:  ffff  dw      0xffff
0055b6:  ffff  dw      0xffff
0055b8:  ffff  dw      0xffff
0055ba:  ffff  dw      0xffff
0055bc:  ffff  dw      0xffff
0055be:  ffff  dw      0xffff
0055c0:  ffff  dw      0xffff
0055c2:  ffff  dw      0xffff
0055c4:  ffff  dw      0xffff
0055c6:  ffff  dw      0xffff
0055c8:  ffff  dw      0xffff
0055ca:  ffff  dw      0xffff
0055cc:  ffff  dw      0xffff
0055ce:  ffff  dw      0xffff
0055d0:  ffff  dw      0xffff
0055d2:  ffff  dw      0xffff
0055d4:  ffff  dw      0xffff
0055d6:  ffff  dw      0xffff
0055d8:  ffff  dw      0xffff
0055da:  ffff  dw      0xffff
0055dc:  ffff  dw      0xffff
0055de:  ffff  dw      0xffff
0055e0:  ffff  dw      0xffff
0055e2:  ffff  dw      0xffff
0055e4:  ffff  dw      0xffff
0055e6:  ffff  dw      0xffff
0055e8:  ffff  dw      0xffff
0055ea:  ffff  dw      0xffff
0055ec:  ffff  dw      0xffff
0055ee:  ffff  dw      0xffff
0055f0:  ffff  dw      0xffff
0055f2:  ffff  dw      0xffff
0055f4:  ffff  dw      0xffff
0055f6:  ffff  dw      0xffff
0055f8:  ffff  dw      0xffff
0055fa:  ffff  dw      0xffff
0055fc:  ffff  dw      0xffff
0055fe:  ffff  dw      0xffff
005600:  c801  dw      0xc801
005602:  0004  clrwdt
005604:  0000  nop
005606:  0000  nop
005608:  0000  nop
00560a:  0000  nop
00560c:  0000  nop
00560e:  0000  nop
005610:  0000  nop
005612:  0000  nop
005614:  0000  nop
005616:  0000  nop
005618:  3701  rlcf    (Common_RAM + 1), F, B               ; reg: 0x001
00561a:  0014  callw
00561c:  0000  nop
00561e:  0000  nop
005620:  0000  nop
005622:  0000  nop
005624:  0000  nop
005626:  0000  nop
005628:  0000  nop
00562a:  0000  nop
00562c:  0000  nop
00562e:  0000  nop
005630:  3801  swapf   (Common_RAM + 1), W, A               ; reg: 0x001
005632:  0014  callw
005634:  0000  nop
005636:  0000  nop
005638:  0000  nop
00563a:  0000  nop
00563c:  0000  nop
00563e:  0000  nop
005640:  0000  nop
005642:  0000  nop
005644:  0000  nop
005646:  0000  nop
005648:  3901  swapf   (Common_RAM + 1), W, B               ; reg: 0x001
00564a:  0014  callw
00564c:  0000  nop
00564e:  0000  nop
005650:  0000  nop
005652:  0000  nop
005654:  0000  nop
005656:  0000  nop
005658:  0000  nop
00565a:  0000  nop
00565c:  0000  nop
00565e:  0000  nop
005660:  3a01  swapf   (Common_RAM + 1), F, A               ; reg: 0x001
005662:  0014  callw
005664:  0000  nop
005666:  0000  nop
005668:  0000  nop
00566a:  0000  nop
00566c:  0000  nop
00566e:  0000  nop
005670:  0000  nop
005672:  0000  nop
005674:  0000  nop
005676:  0000  nop
005678:  3b01  swapf   (Common_RAM + 1), F, B               ; reg: 0x001
00567a:  0014  callw
00567c:  0000  nop
00567e:  0000  nop
005680:  0000  nop
005682:  0000  nop
005684:  0000  nop
005686:  0000  nop
005688:  0000  nop
00568a:  0000  nop
00568c:  0000  nop
00568e:  0000  nop
005690:  3c01  incfsz  (Common_RAM + 1), W, A               ; reg: 0x001
005692:  0014  callw
005694:  0000  nop
005696:  0000  nop
005698:  0000  nop
00569a:  0000  nop
00569c:  0000  nop
00569e:  0000  nop
0056a0:  0000  nop
0056a2:  0000  nop
0056a4:  0000  nop
0056a6:  0000  nop
0056a8:  3d01  incfsz  (Common_RAM + 1), W, B               ; reg: 0x001
0056aa:  0014  callw
0056ac:  0000  nop
0056ae:  0000  nop
0056b0:  0000  nop
0056b2:  0000  nop
0056b4:  0000  nop
0056b6:  0000  nop
0056b8:  0000  nop
0056ba:  0000  nop
0056bc:  0000  nop
0056be:  0000  nop
0056c0:  3e01  incfsz  (Common_RAM + 1), F, A               ; reg: 0x001
0056c2:  0014  callw
0056c4:  0000  nop
0056c6:  0000  nop
0056c8:  0000  nop
0056ca:  0000  nop
0056cc:  0000  nop
0056ce:  0000  nop
0056d0:  0000  nop
0056d2:  0000  nop
0056d4:  0000  nop
0056d6:  0000  nop
0056d8:  3f01  incfsz  (Common_RAM + 1), F, B               ; reg: 0x001
0056da:  0014  callw
0056dc:  0000  nop
0056de:  0000  nop
0056e0:  0000  nop
0056e2:  0000  nop
0056e4:  0000  nop
0056e6:  0000  nop
0056e8:  0000  nop
0056ea:  0000  nop
0056ec:  0000  nop
0056ee:  0000  nop
0056f0:  4001  rrncf   (Common_RAM + 1), W, A               ; reg: 0x001
0056f2:  0014  callw
0056f4:  0000  nop
0056f6:  0000  nop
0056f8:  0000  nop
0056fa:  0000  nop
0056fc:  0000  nop
0056fe:  0000  nop
005700:  0000  nop
005702:  0000  nop

label_611:                                                  ; address: 0x005704

005704:  0000  nop
005706:  0000  nop
005708:  4101  rrncf   (Common_RAM + 1), W, B               ; reg: 0x001
00570a:  0014  callw
00570c:  0000  nop
00570e:  0000  nop
005710:  0000  nop
005712:  0000  nop
005714:  0000  nop
005716:  0000  nop
005718:  0000  nop
00571a:  0000  nop
00571c:  0000  nop
00571e:  0000  nop
005720:  4201  rrncf   (Common_RAM + 1), F, A               ; reg: 0x001
005722:  0014  callw
005724:  0000  nop
005726:  0000  nop
005728:  0000  nop
00572a:  0000  nop
00572c:  0000  nop
00572e:  0000  nop
005730:  0000  nop
005732:  0000  nop
005734:  0000  nop
005736:  0000  nop
005738:  4301  rrncf   (Common_RAM + 1), F, B               ; reg: 0x001
00573a:  0014  callw
00573c:  0000  nop
00573e:  0000  nop
005740:  0000  nop
005742:  0000  nop
005744:  0000  nop
005746:  0000  nop
005748:  0000  nop
00574a:  0000  nop
00574c:  0000  nop
00574e:  0000  nop
005750:  4401  rlncf   (Common_RAM + 1), W, A               ; reg: 0x001
005752:  0014  callw
005754:  0000  nop
005756:  0000  nop
005758:  0000  nop
00575a:  0000  nop
00575c:  0000  nop
00575e:  0000  nop
005760:  0000  nop
005762:  0000  nop
005764:  0000  nop
005766:  0000  nop
005768:  4501  rlncf   (Common_RAM + 1), W, B               ; reg: 0x001
00576a:  0014  callw
00576c:  0000  nop
00576e:  0000  nop
005770:  0000  nop
005772:  0000  nop
005774:  0000  nop
005776:  0000  nop
005778:  0000  nop
00577a:  0000  nop
00577c:  0000  nop
00577e:  0000  nop
005780:  c901  dw      0xc901
005782:  0004  clrwdt
005784:  0000  nop
005786:  0000  nop
005788:  0000  nop
00578a:  0000  nop
00578c:  0000  nop
00578e:  0000  nop
005790:  0000  nop
005792:  0000  nop
005794:  0000  nop
005796:  0000  nop
005798:  4601  rlncf   (Common_RAM + 1), F, A               ; reg: 0x001
00579a:  0014  callw
00579c:  0000  nop
00579e:  0000  nop
0057a0:  0000  nop
0057a2:  0000  nop
0057a4:  0000  nop
0057a6:  0000  nop
0057a8:  0000  nop
0057aa:  0000  nop
0057ac:  0000  nop
0057ae:  0000  nop
0057b0:  4701  rlncf   (Common_RAM + 1), F, B               ; reg: 0x001
0057b2:  0014  callw
0057b4:  0000  nop
0057b6:  0000  nop
0057b8:  0000  nop
0057ba:  0000  nop
0057bc:  0000  nop
0057be:  0000  nop
0057c0:  0000  nop
0057c2:  0000  nop
0057c4:  0000  nop
0057c6:  0000  nop
0057c8:  4801  infsnz  (Common_RAM + 1), W, A               ; reg: 0x001
0057ca:  0014  callw
0057cc:  0000  nop
0057ce:  0000  nop
0057d0:  0000  nop
0057d2:  0000  nop
0057d4:  0000  nop
0057d6:  0000  nop
0057d8:  0000  nop
0057da:  0000  nop
0057dc:  0000  nop
0057de:  0000  nop
0057e0:  4901  infsnz  (Common_RAM + 1), W, B               ; reg: 0x001
0057e2:  0014  callw
0057e4:  0000  nop
0057e6:  0000  nop
0057e8:  0000  nop
0057ea:  0000  nop
0057ec:  0000  nop
0057ee:  0000  nop
0057f0:  0000  nop
0057f2:  0000  nop
0057f4:  0000  nop
0057f6:  0000  nop
0057f8:  4a01  infsnz  (Common_RAM + 1), F, A               ; reg: 0x001
0057fa:  0014  callw
0057fc:  0000  nop
0057fe:  0000  nop
005800:  0000  nop
005802:  0000  nop
005804:  0000  nop
005806:  0000  nop
005808:  0000  nop
00580a:  0000  nop
00580c:  0000  nop
00580e:  0000  nop
005810:  4b01  infsnz  (Common_RAM + 1), F, B               ; reg: 0x001
005812:  0014  callw
005814:  0000  nop
005816:  0000  nop
005818:  0000  nop
00581a:  0000  nop
00581c:  0000  nop
00581e:  0000  nop
005820:  0000  nop
005822:  0000  nop
005824:  0000  nop
005826:  0000  nop
005828:  4c01  dcfsnz  (Common_RAM + 1), W, A               ; reg: 0x001
00582a:  0014  callw
00582c:  0000  nop
00582e:  0000  nop
005830:  0000  nop
005832:  0000  nop
005834:  0000  nop
005836:  0000  nop
005838:  0000  nop
00583a:  0000  nop
00583c:  0000  nop
00583e:  0000  nop
005840:  4d01  dcfsnz  (Common_RAM + 1), W, B               ; reg: 0x001
005842:  0014  callw
005844:  0000  nop
005846:  0000  nop
005848:  0000  nop
00584a:  0000  nop
00584c:  0000  nop
00584e:  0000  nop
005850:  0000  nop
005852:  0000  nop
005854:  0000  nop
005856:  0000  nop
005858:  4e01  dcfsnz  (Common_RAM + 1), F, A               ; reg: 0x001
00585a:  0014  callw
00585c:  0000  nop
00585e:  0000  nop
005860:  0000  nop
005862:  0000  nop
005864:  0000  nop
005866:  0000  nop
005868:  0000  nop
00586a:  0000  nop
00586c:  0000  nop
00586e:  0000  nop
005870:  4f01  dcfsnz  (Common_RAM + 1), F, B               ; reg: 0x001
005872:  0014  callw
005874:  0000  nop
005876:  0000  nop
005878:  0000  nop
00587a:  0000  nop
00587c:  0000  nop
00587e:  0000  nop
005880:  0000  nop
005882:  0000  nop
005884:  0000  nop
005886:  0000  nop
005888:  5001  movf    (Common_RAM + 1), W, A               ; reg: 0x001
00588a:  0014  callw
00588c:  0000  nop
00588e:  0000  nop
005890:  0000  nop
005892:  0000  nop
005894:  0000  nop
005896:  0000  nop
005898:  0000  nop
00589a:  0000  nop
00589c:  0000  nop
00589e:  0000  nop
0058a0:  5101  movf    (Common_RAM + 1), W, B               ; reg: 0x001
0058a2:  0014  callw
0058a4:  0000  nop
0058a6:  0000  nop
0058a8:  0000  nop
0058aa:  0000  nop
0058ac:  0000  nop
0058ae:  0000  nop
0058b0:  0000  nop
0058b2:  0000  nop
0058b4:  0000  nop
0058b6:  0000  nop
0058b8:  5201  movf    (Common_RAM + 1), F, A               ; reg: 0x001
0058ba:  0014  callw
0058bc:  0000  nop
0058be:  0000  nop
0058c0:  0000  nop
0058c2:  0000  nop
0058c4:  0000  nop
0058c6:  0000  nop
0058c8:  0000  nop
0058ca:  0000  nop
0058cc:  0000  nop
0058ce:  0000  nop
0058d0:  5301  movf    (Common_RAM + 1), F, B               ; reg: 0x001
0058d2:  0014  callw
0058d4:  0000  nop
0058d6:  0000  nop
0058d8:  0000  nop
0058da:  0000  nop
0058dc:  0000  nop
0058de:  0000  nop
0058e0:  0000  nop
0058e2:  0000  nop
0058e4:  0000  nop
0058e6:  0000  nop
0058e8:  5401  subfwb  (Common_RAM + 1), W, A               ; reg: 0x001
0058ea:  0014  callw
0058ec:  0000  nop
0058ee:  0000  nop
0058f0:  0000  nop
0058f2:  0000  nop
0058f4:  0000  nop
0058f6:  0000  nop
0058f8:  0000  nop
0058fa:  0000  nop
0058fc:  0000  nop
0058fe:  0000  nop
005900:  ca01  dw      0xca01
005902:  0004  clrwdt
005904:  0000  nop
005906:  0000  nop
005908:  0000  nop
00590a:  0000  nop
00590c:  0000  nop
00590e:  0000  nop
005910:  0000  nop
005912:  0000  nop
005914:  0000  nop
005916:  0000  nop
005918:  5501  subfwb  (Common_RAM + 1), W, B               ; reg: 0x001
00591a:  0014  callw
00591c:  0000  nop
00591e:  0000  nop
005920:  0000  nop
005922:  0000  nop
005924:  0000  nop
005926:  0000  nop
005928:  0000  nop
00592a:  0000  nop
00592c:  0000  nop
00592e:  0000  nop
005930:  5601  subfwb  (Common_RAM + 1), F, A               ; reg: 0x001
005932:  0014  callw
005934:  0000  nop
005936:  0000  nop
005938:  0000  nop
00593a:  0000  nop
00593c:  0000  nop
00593e:  0000  nop
005940:  0000  nop
005942:  0000  nop
005944:  0000  nop
005946:  0000  nop
005948:  5701  subfwb  (Common_RAM + 1), F, B               ; reg: 0x001
00594a:  0014  callw
00594c:  0000  nop
00594e:  0000  nop
005950:  0000  nop
005952:  0000  nop
005954:  0000  nop
005956:  0000  nop
005958:  0000  nop
00595a:  0000  nop
00595c:  0000  nop
00595e:  0000  nop
005960:  5801  subwfb  (Common_RAM + 1), W, A               ; reg: 0x001
005962:  0014  callw
005964:  0000  nop
005966:  0000  nop
005968:  0000  nop
00596a:  0000  nop
00596c:  0000  nop
00596e:  0000  nop
005970:  0000  nop
005972:  0000  nop
005974:  0000  nop
005976:  0000  nop
005978:  5901  subwfb  (Common_RAM + 1), W, B               ; reg: 0x001
00597a:  0014  callw
00597c:  0000  nop
00597e:  0000  nop
005980:  0000  nop
005982:  0000  nop
005984:  0000  nop
005986:  0000  nop
005988:  0000  nop
00598a:  0000  nop
00598c:  0000  nop
00598e:  0000  nop
005990:  5a01  subwfb  (Common_RAM + 1), F, A               ; reg: 0x001
005992:  0014  callw
005994:  0000  nop
005996:  0000  nop
005998:  0000  nop
00599a:  0000  nop
00599c:  0000  nop
00599e:  0000  nop
0059a0:  0000  nop
0059a2:  0000  nop
0059a4:  0000  nop
0059a6:  0000  nop
0059a8:  5b01  subwfb  (Common_RAM + 1), F, B               ; reg: 0x001
0059aa:  0014  callw
0059ac:  0000  nop
0059ae:  0000  nop
0059b0:  0000  nop
0059b2:  0000  nop
0059b4:  0000  nop
0059b6:  0000  nop
0059b8:  0000  nop
0059ba:  0000  nop
0059bc:  0000  nop
0059be:  0000  nop
0059c0:  5c01  subwf   (Common_RAM + 1), W, A               ; reg: 0x001
0059c2:  0014  callw
0059c4:  0000  nop
0059c6:  0000  nop
0059c8:  0000  nop
0059ca:  0000  nop
0059cc:  0000  nop
0059ce:  0000  nop
0059d0:  0000  nop
0059d2:  0000  nop
0059d4:  0000  nop
0059d6:  0000  nop
0059d8:  5d01  subwf   (Common_RAM + 1), W, B               ; reg: 0x001
0059da:  0014  callw
0059dc:  0000  nop
0059de:  0000  nop
0059e0:  0000  nop
0059e2:  0000  nop
0059e4:  0000  nop
0059e6:  0000  nop
0059e8:  0000  nop
0059ea:  0000  nop
0059ec:  0000  nop
0059ee:  0000  nop
0059f0:  5e01  subwf   (Common_RAM + 1), F, A               ; reg: 0x001
0059f2:  0014  callw
0059f4:  0000  nop
0059f6:  0000  nop
0059f8:  0000  nop
0059fa:  0000  nop
0059fc:  0000  nop
0059fe:  0000  nop
005a00:  0000  nop
005a02:  0000  nop
005a04:  0000  nop
005a06:  0000  nop
005a08:  5f01  subwf   (Common_RAM + 1), F, B               ; reg: 0x001
005a0a:  0014  callw
005a0c:  0000  nop
005a0e:  0000  nop
005a10:  0000  nop
005a12:  0000  nop
005a14:  0000  nop
005a16:  0000  nop
005a18:  0000  nop
005a1a:  0000  nop
005a1c:  0000  nop
005a1e:  0000  nop
005a20:  6001  cpfslt  (Common_RAM + 1), A                  ; reg: 0x001
005a22:  0014  callw
005a24:  0000  nop
005a26:  0000  nop
005a28:  0000  nop
005a2a:  0000  nop
005a2c:  0000  nop
005a2e:  0000  nop
005a30:  0000  nop
005a32:  0000  nop
005a34:  0000  nop
005a36:  0000  nop
005a38:  6101  cpfslt  (Common_RAM + 1), B                  ; reg: 0x001
005a3a:  0014  callw
005a3c:  0000  nop
005a3e:  0000  nop
005a40:  0000  nop
005a42:  0000  nop
005a44:  0000  nop
005a46:  0000  nop
005a48:  0000  nop
005a4a:  0000  nop
005a4c:  0000  nop
005a4e:  0000  nop
005a50:  6201  cpfseq  (Common_RAM + 1), A                  ; reg: 0x001
005a52:  0014  callw
005a54:  0000  nop
005a56:  0000  nop
005a58:  0000  nop
005a5a:  0000  nop
005a5c:  0000  nop
005a5e:  0000  nop
005a60:  0000  nop
005a62:  0000  nop
005a64:  0000  nop
005a66:  0000  nop
005a68:  6301  cpfseq  (Common_RAM + 1), B                  ; reg: 0x001
005a6a:  0014  callw
005a6c:  0000  nop
005a6e:  0000  nop
005a70:  0000  nop
005a72:  0000  nop
005a74:  0000  nop
005a76:  0000  nop
005a78:  0000  nop
005a7a:  0000  nop
005a7c:  0000  nop
005a7e:  0000  nop
005a80:  cb01  dw      0xcb01
005a82:  0004  clrwdt
005a84:  0000  nop
005a86:  0000  nop
005a88:  0000  nop
005a8a:  0000  nop
005a8c:  0000  nop
005a8e:  0000  nop
005a90:  0000  nop
005a92:  0000  nop
005a94:  0000  nop
005a96:  0000  nop
005a98:  6401  cpfsgt  (Common_RAM + 1), A                  ; reg: 0x001
005a9a:  0014  callw
005a9c:  0000  nop
005a9e:  0000  nop
005aa0:  0000  nop
005aa2:  0000  nop
005aa4:  0000  nop
005aa6:  0000  nop
005aa8:  0000  nop
005aaa:  0000  nop
005aac:  0000  nop
005aae:  0000  nop
005ab0:  6501  cpfsgt  (Common_RAM + 1), B                  ; reg: 0x001
005ab2:  0014  callw
005ab4:  0000  nop
005ab6:  0000  nop
005ab8:  0000  nop
005aba:  0000  nop
005abc:  0000  nop
005abe:  0000  nop
005ac0:  0000  nop
005ac2:  0000  nop
005ac4:  0000  nop
005ac6:  0000  nop
005ac8:  6601  tstfsz  (Common_RAM + 1), A                  ; reg: 0x001
005aca:  0014  callw
005acc:  0000  nop
005ace:  0000  nop
005ad0:  0000  nop
005ad2:  0000  nop
005ad4:  0000  nop
005ad6:  0000  nop
005ad8:  0000  nop
005ada:  0000  nop
005adc:  0000  nop
005ade:  0000  nop
005ae0:  6701  tstfsz  (Common_RAM + 1), B                  ; reg: 0x001
005ae2:  0014  callw
005ae4:  0000  nop
005ae6:  0000  nop
005ae8:  0000  nop
005aea:  0000  nop
005aec:  0000  nop
005aee:  0000  nop
005af0:  0000  nop
005af2:  0000  nop
005af4:  0000  nop
005af6:  0000  nop
005af8:  6801  setf    (Common_RAM + 1), A                  ; reg: 0x001
005afa:  0014  callw
005afc:  0000  nop
005afe:  0000  nop
005b00:  0000  nop
005b02:  0000  nop
005b04:  0000  nop
005b06:  0000  nop
005b08:  0000  nop
005b0a:  0000  nop
005b0c:  0000  nop
005b0e:  0000  nop
005b10:  6901  setf    (Common_RAM + 1), B                  ; reg: 0x001
005b12:  0014  callw
005b14:  0000  nop
005b16:  0000  nop
005b18:  0000  nop
005b1a:  0000  nop
005b1c:  0000  nop
005b1e:  0000  nop
005b20:  0000  nop
005b22:  0000  nop
005b24:  0000  nop
005b26:  0000  nop
005b28:  6a01  clrf    (Common_RAM + 1), A                  ; reg: 0x001
005b2a:  0014  callw
005b2c:  0000  nop
005b2e:  0000  nop
005b30:  0000  nop
005b32:  0000  nop
005b34:  0000  nop
005b36:  0000  nop
005b38:  0000  nop
005b3a:  0000  nop
005b3c:  0000  nop
005b3e:  0000  nop
005b40:  6b01  clrf    (Common_RAM + 1), B                  ; reg: 0x001
005b42:  0014  callw
005b44:  0000  nop
005b46:  0000  nop
005b48:  0000  nop
005b4a:  0000  nop
005b4c:  0000  nop
005b4e:  0000  nop
005b50:  0000  nop
005b52:  0000  nop
005b54:  0000  nop
005b56:  0000  nop
005b58:  6c01  negf    (Common_RAM + 1), A                  ; reg: 0x001
005b5a:  0014  callw
005b5c:  0000  nop
005b5e:  0000  nop
005b60:  0000  nop
005b62:  0000  nop
005b64:  0000  nop
005b66:  0000  nop
005b68:  0000  nop
005b6a:  0000  nop
005b6c:  0000  nop
005b6e:  0000  nop
005b70:  6d01  negf    (Common_RAM + 1), B                  ; reg: 0x001
005b72:  0014  callw
005b74:  0000  nop
005b76:  0000  nop
005b78:  0000  nop
005b7a:  0000  nop
005b7c:  0000  nop
005b7e:  0000  nop
005b80:  0000  nop
005b82:  0000  nop
005b84:  0000  nop
005b86:  0000  nop
005b88:  6e01  movwf   (Common_RAM + 1), A                  ; reg: 0x001
005b8a:  0014  callw
005b8c:  0000  nop
005b8e:  0000  nop
005b90:  0000  nop
005b92:  0000  nop
005b94:  0000  nop
005b96:  0000  nop
005b98:  0000  nop
005b9a:  0000  nop
005b9c:  0000  nop
005b9e:  0000  nop
005ba0:  6f01  movwf   (Common_RAM + 1), B                  ; reg: 0x001
005ba2:  0014  callw
005ba4:  0000  nop
005ba6:  0000  nop
005ba8:  0000  nop
005baa:  0000  nop
005bac:  0000  nop
005bae:  0000  nop
005bb0:  0000  nop
005bb2:  0000  nop
005bb4:  0000  nop
005bb6:  0000  nop
005bb8:  7001  btg     (Common_RAM + 1), 0x0, A             ; reg: 0x001
005bba:  0014  callw
005bbc:  0000  nop
005bbe:  0000  nop
005bc0:  0000  nop
005bc2:  0000  nop
005bc4:  0000  nop
005bc6:  0000  nop
005bc8:  0000  nop
005bca:  0000  nop
005bcc:  0000  nop
005bce:  0000  nop
005bd0:  7101  btg     (Common_RAM + 1), 0x0, B             ; reg: 0x001
005bd2:  0014  callw
005bd4:  0000  nop
005bd6:  0000  nop
005bd8:  0000  nop
005bda:  0000  nop
005bdc:  0000  nop
005bde:  0000  nop
005be0:  0000  nop
005be2:  0000  nop
005be4:  0000  nop
005be6:  0000  nop
005be8:  7201  btg     (Common_RAM + 1), 0x1, A             ; reg: 0x001
005bea:  0014  callw
005bec:  0000  nop
005bee:  0000  nop
005bf0:  0000  nop
005bf2:  0000  nop
005bf4:  0000  nop
005bf6:  0000  nop
005bf8:  0000  nop
005bfa:  0000  nop
005bfc:  0000  nop
005bfe:  0000  nop
005c00:  cc01  dw      0xcc01
005c02:  0004  clrwdt
005c04:  0000  nop
005c06:  0000  nop
005c08:  0000  nop
005c0a:  0000  nop
005c0c:  0000  nop
005c0e:  0000  nop
005c10:  0000  nop
005c12:  0000  nop
005c14:  0000  nop
005c16:  0000  nop
005c18:  7301  btg     (Common_RAM + 1), 0x1, B             ; reg: 0x001
005c1a:  0014  callw
005c1c:  0000  nop
005c1e:  0000  nop
005c20:  0000  nop
005c22:  0000  nop
005c24:  0000  nop
005c26:  0000  nop
005c28:  0000  nop
005c2a:  0000  nop
005c2c:  0000  nop
005c2e:  0000  nop
005c30:  7401  btg     (Common_RAM + 1), 0x2, A             ; reg: 0x001
005c32:  0014  callw
005c34:  0000  nop
005c36:  0000  nop
005c38:  0000  nop
005c3a:  0000  nop
005c3c:  0000  nop
005c3e:  0000  nop
005c40:  0000  nop
005c42:  0000  nop
005c44:  0000  nop
005c46:  0000  nop
005c48:  7501  btg     (Common_RAM + 1), 0x2, B             ; reg: 0x001
005c4a:  0014  callw
005c4c:  0000  nop
005c4e:  0000  nop
005c50:  0000  nop
005c52:  0000  nop
005c54:  0000  nop
005c56:  0000  nop
005c58:  0000  nop
005c5a:  0000  nop
005c5c:  0000  nop
005c5e:  0000  nop
005c60:  7601  btg     (Common_RAM + 1), 0x3, A             ; reg: 0x001
005c62:  0014  callw
005c64:  0000  nop
005c66:  0000  nop
005c68:  0000  nop
005c6a:  0000  nop
005c6c:  0000  nop
005c6e:  0000  nop
005c70:  0000  nop
005c72:  0000  nop
005c74:  0000  nop
005c76:  0000  nop
005c78:  7701  btg     (Common_RAM + 1), 0x3, B             ; reg: 0x001
005c7a:  0014  callw
005c7c:  0000  nop
005c7e:  0000  nop
005c80:  0000  nop
005c82:  0000  nop
005c84:  0000  nop
005c86:  0000  nop
005c88:  0000  nop
005c8a:  0000  nop
005c8c:  0000  nop
005c8e:  0000  nop
005c90:  7801  btg     (Common_RAM + 1), 0x4, A             ; reg: 0x001
005c92:  0014  callw
005c94:  0000  nop
005c96:  0000  nop
005c98:  0000  nop
005c9a:  0000  nop
005c9c:  0000  nop
005c9e:  0000  nop
005ca0:  0000  nop
005ca2:  0000  nop
005ca4:  0000  nop
005ca6:  0000  nop
005ca8:  7901  btg     (Common_RAM + 1), 0x4, B             ; reg: 0x001
005caa:  0014  callw
005cac:  0000  nop
005cae:  0000  nop
005cb0:  0000  nop
005cb2:  0000  nop
005cb4:  0000  nop
005cb6:  0000  nop
005cb8:  0000  nop
005cba:  0000  nop
005cbc:  0000  nop
005cbe:  0000  nop
005cc0:  7a01  btg     (Common_RAM + 1), 0x5, A             ; reg: 0x001
005cc2:  0014  callw
005cc4:  0000  nop
005cc6:  0000  nop
005cc8:  0000  nop
005cca:  0000  nop
005ccc:  0000  nop
005cce:  0000  nop
005cd0:  0000  nop
005cd2:  0000  nop
005cd4:  0000  nop
005cd6:  0000  nop
005cd8:  7b01  btg     (Common_RAM + 1), 0x5, B             ; reg: 0x001
005cda:  0014  callw
005cdc:  0000  nop
005cde:  0000  nop
005ce0:  0000  nop
005ce2:  0000  nop
005ce4:  0000  nop
005ce6:  0000  nop
005ce8:  0000  nop
005cea:  0000  nop
005cec:  0000  nop
005cee:  0000  nop
005cf0:  7c01  btg     (Common_RAM + 1), 0x6, A             ; reg: 0x001
005cf2:  0014  callw
005cf4:  0000  nop
005cf6:  0000  nop
005cf8:  0000  nop
005cfa:  0000  nop
005cfc:  0000  nop
005cfe:  0000  nop
005d00:  0000  nop
005d02:  0000  nop
005d04:  0000  nop
005d06:  0000  nop
005d08:  7d01  btg     (Common_RAM + 1), 0x6, B             ; reg: 0x001
005d0a:  0014  callw
005d0c:  0000  nop
005d0e:  0000  nop
005d10:  0000  nop
005d12:  0000  nop
005d14:  0000  nop
005d16:  0000  nop
005d18:  0000  nop
005d1a:  0000  nop
005d1c:  0000  nop
005d1e:  0000  nop
005d20:  7e01  btg     (Common_RAM + 1), 0x7, A             ; reg: 0x001
005d22:  0014  callw
005d24:  0000  nop
005d26:  0000  nop
005d28:  0000  nop
005d2a:  0000  nop
005d2c:  0000  nop
005d2e:  0000  nop
005d30:  0000  nop
005d32:  0000  nop
005d34:  0000  nop
005d36:  0000  nop
005d38:  7f01  btg     (Common_RAM + 1), 0x7, B             ; reg: 0x001
005d3a:  0014  callw
005d3c:  0000  nop
005d3e:  0000  nop
005d40:  0000  nop
005d42:  0000  nop
005d44:  0000  nop
005d46:  0000  nop
005d48:  0000  nop
005d4a:  0000  nop
005d4c:  0000  nop
005d4e:  0000  nop
005d50:  8001  bsf     (Common_RAM + 1), 0x0, A             ; reg: 0x001
005d52:  0014  callw
005d54:  0000  nop
005d56:  0000  nop
005d58:  0000  nop
005d5a:  0000  nop
005d5c:  0000  nop
005d5e:  0000  nop
005d60:  0000  nop
005d62:  0000  nop
005d64:  0000  nop
005d66:  0000  nop
005d68:  8101  bsf     (Common_RAM + 1), 0x0, B             ; reg: 0x001
005d6a:  0014  callw
005d6c:  0000  nop
005d6e:  0000  nop
005d70:  0000  nop
005d72:  0000  nop
005d74:  0000  nop
005d76:  0000  nop
005d78:  0000  nop
005d7a:  0000  nop
005d7c:  0000  nop
005d7e:  0000  nop
005d80:  cd01  dw      0xcd01
005d82:  0004  clrwdt
005d84:  0000  nop
005d86:  0000  nop
005d88:  0000  nop
005d8a:  0000  nop
005d8c:  0000  nop
005d8e:  0000  nop
005d90:  0000  nop
005d92:  0000  nop
005d94:  0000  nop
005d96:  0000  nop
005d98:  8201  bsf     (Common_RAM + 1), 0x1, A             ; reg: 0x001
005d9a:  0014  callw
005d9c:  0000  nop
005d9e:  0000  nop
005da0:  0000  nop
005da2:  0000  nop
005da4:  0000  nop
005da6:  0000  nop
005da8:  0000  nop
005daa:  0000  nop
005dac:  0000  nop
005dae:  0000  nop
005db0:  8301  bsf     (Common_RAM + 1), 0x1, B             ; reg: 0x001
005db2:  0014  callw
005db4:  0000  nop
005db6:  0000  nop
005db8:  0000  nop
005dba:  0000  nop
005dbc:  0000  nop
005dbe:  0000  nop
005dc0:  0000  nop
005dc2:  0000  nop
005dc4:  0000  nop
005dc6:  0000  nop
005dc8:  8401  bsf     (Common_RAM + 1), 0x2, A             ; reg: 0x001
005dca:  0014  callw
005dcc:  0000  nop
005dce:  0000  nop
005dd0:  0000  nop
005dd2:  0000  nop
005dd4:  0000  nop
005dd6:  0000  nop
005dd8:  0000  nop
005dda:  0000  nop
005ddc:  0000  nop
005dde:  0000  nop
005de0:  8501  bsf     (Common_RAM + 1), 0x2, B             ; reg: 0x001
005de2:  0014  callw
005de4:  0000  nop
005de6:  0000  nop
005de8:  0000  nop
005dea:  0000  nop
005dec:  0000  nop
005dee:  0000  nop
005df0:  0000  nop
005df2:  0000  nop
005df4:  0000  nop
005df6:  0000  nop
005df8:  8601  bsf     (Common_RAM + 1), 0x3, A             ; reg: 0x001
005dfa:  0014  callw
005dfc:  0000  nop
005dfe:  0000  nop
005e00:  0000  nop
005e02:  0000  nop
005e04:  0000  nop
005e06:  0000  nop
005e08:  0000  nop
005e0a:  0000  nop
005e0c:  0000  nop
005e0e:  0000  nop
005e10:  8701  bsf     (Common_RAM + 1), 0x3, B             ; reg: 0x001
005e12:  0014  callw
005e14:  0000  nop
005e16:  0000  nop
005e18:  0000  nop
005e1a:  0000  nop
005e1c:  0000  nop
005e1e:  0000  nop
005e20:  0000  nop
005e22:  0000  nop
005e24:  0000  nop
005e26:  0000  nop
005e28:  8801  bsf     (Common_RAM + 1), 0x4, A             ; reg: 0x001
005e2a:  0014  callw
005e2c:  0000  nop
005e2e:  0000  nop
005e30:  0000  nop
005e32:  0000  nop
005e34:  0000  nop
005e36:  0000  nop
005e38:  0000  nop
005e3a:  0000  nop
005e3c:  0000  nop
005e3e:  0000  nop
005e40:  8901  bsf     (Common_RAM + 1), 0x4, B             ; reg: 0x001
005e42:  0014  callw
005e44:  0000  nop
005e46:  0000  nop
005e48:  0000  nop
005e4a:  0000  nop
005e4c:  0000  nop
005e4e:  0000  nop
005e50:  0000  nop
005e52:  0000  nop
005e54:  0000  nop
005e56:  0000  nop
005e58:  8a01  bsf     (Common_RAM + 1), 0x5, A             ; reg: 0x001
005e5a:  0014  callw
005e5c:  0000  nop
005e5e:  0000  nop
005e60:  0000  nop
005e62:  0000  nop
005e64:  0000  nop
005e66:  0000  nop
005e68:  0000  nop
005e6a:  0000  nop
005e6c:  0000  nop
005e6e:  0000  nop
005e70:  8b01  bsf     (Common_RAM + 1), 0x5, B             ; reg: 0x001
005e72:  0014  callw
005e74:  0000  nop
005e76:  0000  nop
005e78:  0000  nop
005e7a:  0000  nop
005e7c:  0000  nop
005e7e:  0000  nop
005e80:  0000  nop
005e82:  0000  nop
005e84:  0000  nop
005e86:  0000  nop
005e88:  8c01  bsf     (Common_RAM + 1), 0x6, A             ; reg: 0x001
005e8a:  0014  callw
005e8c:  0000  nop
005e8e:  0000  nop
005e90:  0000  nop
005e92:  0000  nop
005e94:  0000  nop
005e96:  0000  nop
005e98:  0000  nop
005e9a:  0000  nop
005e9c:  0000  nop
005e9e:  0000  nop
005ea0:  8d01  bsf     (Common_RAM + 1), 0x6, B             ; reg: 0x001
005ea2:  0014  callw
005ea4:  0000  nop
005ea6:  0000  nop
005ea8:  0000  nop
005eaa:  0000  nop
005eac:  0000  nop
005eae:  0000  nop
005eb0:  0000  nop
005eb2:  0000  nop
005eb4:  0000  nop
005eb6:  0000  nop
005eb8:  8e01  bsf     (Common_RAM + 1), 0x7, A             ; reg: 0x001
005eba:  0014  callw
005ebc:  0000  nop
005ebe:  0000  nop
005ec0:  0000  nop
005ec2:  0000  nop
005ec4:  0000  nop
005ec6:  0000  nop
005ec8:  0000  nop
005eca:  0000  nop
005ecc:  0000  nop
005ece:  0000  nop
005ed0:  8f01  bsf     (Common_RAM + 1), 0x7, B             ; reg: 0x001
005ed2:  0014  callw
005ed4:  0000  nop
005ed6:  0000  nop
005ed8:  0000  nop
005eda:  0000  nop
005edc:  0000  nop
005ede:  0000  nop
005ee0:  0000  nop
005ee2:  0000  nop
005ee4:  0000  nop
005ee6:  0000  nop
005ee8:  9001  bcf     (Common_RAM + 1), 0x0, A             ; reg: 0x001
005eea:  0014  callw
005eec:  0000  nop
005eee:  0000  nop
005ef0:  0000  nop
005ef2:  0000  nop
005ef4:  0000  nop
005ef6:  0000  nop
005ef8:  0000  nop
005efa:  0000  nop
005efc:  0000  nop
005efe:  0000  nop
005f00:  d401  bra     label_611                            ; dest: 0x005704
005f02:  0004  clrwdt
005f04:  0000  nop
005f06:  0100  movlb   0x0
005f08:  3101  rrcf    (Common_RAM + 1), W, B               ; reg: 0x001
005f0a:  0010  retfie  0x0
005f0c:  0000  nop
005f0e:  0000  nop
005f10:  0000  nop
005f12:  0000  nop
005f14:  0000  nop
005f16:  0000  nop
005f18:  0000  nop
005f1a:  0000  nop
005f1c:  3101  rrcf    (Common_RAM + 1), W, B               ; reg: 0x001
005f1e:  0010  retfie  0x0
005f20:  8000  bsf     Common_RAM, 0x0, A                   ; reg: 0x000
005f22:  0000  nop
005f24:  0000  nop
005f26:  0000  nop
005f28:  0000  nop
005f2a:  0000  nop
005f2c:  0000  nop
005f2e:  0000  nop
005f30:  3201  rrcf    (Common_RAM + 1), F, A               ; reg: 0x001
005f32:  0010  retfie  0x0
005f34:  0000  nop
005f36:  0000  nop
005f38:  0000  nop
005f3a:  0000  nop
005f3c:  0000  nop
005f3e:  0000  nop
005f40:  0000  nop
005f42:  0000  nop
005f44:  3201  rrcf    (Common_RAM + 1), F, A               ; reg: 0x001
005f46:  0010  retfie  0x0
005f48:  8000  bsf     Common_RAM, 0x0, A                   ; reg: 0x000
005f4a:  0000  nop
005f4c:  0000  nop
005f4e:  0000  nop
005f50:  0000  nop
005f52:  0000  nop
005f54:  0000  nop
005f56:  0000  nop
005f58:  3301  rrcf    (Common_RAM + 1), F, B               ; reg: 0x001
005f5a:  0010  retfie  0x0
005f5c:  0000  nop
005f5e:  0000  nop
005f60:  0000  nop
005f62:  0000  nop
005f64:  0000  nop
005f66:  0000  nop
005f68:  0000  nop
005f6a:  0000  nop
005f6c:  3301  rrcf    (Common_RAM + 1), F, B               ; reg: 0x001
005f6e:  0010  retfie  0x0
005f70:  8000  bsf     Common_RAM, 0x0, A                   ; reg: 0x000
005f72:  0000  nop
005f74:  0000  nop
005f76:  0000  nop
005f78:  0000  nop
005f7a:  0000  nop
005f7c:  0000  nop
005f7e:  0000  nop
005f80:  3401  rlcf    (Common_RAM + 1), W, A               ; reg: 0x001
005f82:  0010  retfie  0x0
005f84:  0000  nop
005f86:  0000  nop
005f88:  0000  nop
005f8a:  0000  nop
005f8c:  0000  nop
005f8e:  0000  nop
005f90:  0000  nop
005f92:  0000  nop
005f94:  3401  rlcf    (Common_RAM + 1), W, A               ; reg: 0x001
005f96:  0010  retfie  0x0
005f98:  8000  bsf     Common_RAM, 0x0, A                   ; reg: 0x000
005f9a:  0000  nop
005f9c:  0000  nop
005f9e:  0000  nop
005fa0:  0000  nop
005fa2:  0000  nop
005fa4:  0000  nop
005fa6:  0000  nop
005fa8:  3501  rlcf    (Common_RAM + 1), W, B               ; reg: 0x001
005faa:  0010  retfie  0x0
005fac:  0000  nop
005fae:  0000  nop
005fb0:  0000  nop
005fb2:  0000  nop
005fb4:  0000  nop
005fb6:  0000  nop
005fb8:  0000  nop
005fba:  0000  nop
005fbc:  3501  rlcf    (Common_RAM + 1), W, B               ; reg: 0x001
005fbe:  0010  retfie  0x0
005fc0:  8000  bsf     Common_RAM, 0x0, A                   ; reg: 0x000
005fc2:  0000  nop
005fc4:  0000  nop
005fc6:  0000  nop
005fc8:  0000  nop
005fca:  0000  nop
005fcc:  0000  nop
005fce:  0000  nop
005fd0:  3601  rlcf    (Common_RAM + 1), F, A               ; reg: 0x001
005fd2:  0010  retfie  0x0
005fd4:  0000  nop
005fd6:  0000  nop
005fd8:  0000  nop
005fda:  0000  nop
005fdc:  0000  nop
005fde:  0000  nop
005fe0:  0000  nop
005fe2:  0000  nop
005fe4:  3601  rlcf    (Common_RAM + 1), F, A               ; reg: 0x001
005fe6:  0010  retfie  0x0
005fe8:  8000  bsf     Common_RAM, 0x0, A                   ; reg: 0x000
005fea:  0000  nop
005fec:  0000  nop
005fee:  0000  nop
005ff0:  0000  nop
005ff2:  0000  nop
005ff4:  0000  nop
005ff6:  0000  nop
005ff8:  ffff  dw      0xffff
005ffa:  ffff  dw      0xffff
005ffc:  ffff  dw      0xffff
005ffe:  ffff  dw      0xffff

;===============================================================================
; EEDATA area
f00000:  ff    db      0xff
f00001:  ff    db      0xff
f00002:  ff    db      0xff
f00003:  a0    db      0xa0
f00004:  01    db      0x01
f00005:  00    db      0x00
f00006:  00    db      0x00
f00007:  00    db      0x00
f00008:  00    db      0x00
f00009:  00    db      0x00
f0000a:  01    db      0x01
f0000b:  01    db      0x01
f0000c:  01    db      0x01
f0000d:  03    db      0x03
f0000e:  04    db      0x04
f0000f:  01    db      0x01
f00010:  00    db      0x00
f00011:  00    db      0x00
f00012:  00    db      0x00
f00013:  00    db      0x00
f00014:  01    db      0x01
f00015:  ff    db      0xff
f00016:  ff    db      0xff
f00017:  ff    db      0xff
f00018:  ff    db      0xff
f00019:  ff    db      0xff
f0001a:  ff    db      0xff
f0001b:  ff    db      0xff
f0001c:  ff    db      0xff
f0001d:  ff    db      0xff
f0001e:  ff    db      0xff
f0001f:  ff    db      0xff
f00020:  ff    db      0xff
f00021:  ff    db      0xff
f00022:  ff    db      0xff
f00023:  ff    db      0xff
f00024:  ff    db      0xff
f00025:  ff    db      0xff
f00026:  ff    db      0xff
f00027:  ff    db      0xff
f00028:  ff    db      0xff
f00029:  ff    db      0xff
f0002a:  ff    db      0xff
f0002b:  ff    db      0xff
f0002c:  ff    db      0xff
f0002d:  ff    db      0xff
f0002e:  ff    db      0xff
f0002f:  ff    db      0xff
f00030:  ff    db      0xff
f00031:  ff    db      0xff
f00032:  ff    db      0xff
f00033:  ff    db      0xff
f00034:  ff    db      0xff
f00035:  ff    db      0xff
f00036:  ff    db      0xff
f00037:  ff    db      0xff
f00038:  ff    db      0xff
f00039:  ff    db      0xff
f0003a:  ff    db      0xff
f0003b:  ff    db      0xff
f0003c:  ff    db      0xff
f0003d:  ff    db      0xff
f0003e:  ff    db      0xff
f0003f:  ff    db      0xff
f00040:  03    db      0x03
f00041:  ff    db      0xff
f00042:  ff    db      0xff
f00043:  ff    db      0xff
f00044:  ff    db      0xff
f00045:  ff    db      0xff
f00046:  ff    db      0xff
f00047:  ff    db      0xff
f00048:  ff    db      0xff
f00049:  ff    db      0xff
f0004a:  ff    db      0xff
f0004b:  ff    db      0xff
f0004c:  ff    db      0xff
f0004d:  ff    db      0xff
f0004e:  ff    db      0xff
f0004f:  ff    db      0xff
f00050:  ff    db      0xff
f00051:  ff    db      0xff
f00052:  ff    db      0xff
f00053:  ff    db      0xff
f00054:  ff    db      0xff
f00055:  ff    db      0xff
f00056:  ff    db      0xff
f00057:  ff    db      0xff
f00058:  ff    db      0xff
f00059:  ff    db      0xff
f0005a:  ff    db      0xff
f0005b:  ff    db      0xff
f0005c:  ff    db      0xff
f0005d:  ff    db      0xff
f0005e:  ff    db      0xff
f0005f:  ff    db      0xff
f00060:  ff    db      0xff
f00061:  ff    db      0xff
f00062:  ff    db      0xff
f00063:  ff    db      0xff
f00064:  ff    db      0xff
f00065:  ff    db      0xff
f00066:  ff    db      0xff
f00067:  ff    db      0xff
f00068:  ff    db      0xff
f00069:  ff    db      0xff
f0006a:  ff    db      0xff
f0006b:  ff    db      0xff
f0006c:  ff    db      0xff
f0006d:  ff    db      0xff
f0006e:  ff    db      0xff
f0006f:  ff    db      0xff
f00070:  ff    db      0xff
f00071:  ff    db      0xff
f00072:  ff    db      0xff
f00073:  ff    db      0xff
f00074:  ff    db      0xff
f00075:  ff    db      0xff
f00076:  ff    db      0xff
f00077:  ff    db      0xff
f00078:  ff    db      0xff
f00079:  ff    db      0xff
f0007a:  ff    db      0xff
f0007b:  ff    db      0xff
f0007c:  ff    db      0xff
f0007d:  ff    db      0xff
f0007e:  ff    db      0xff
f0007f:  ff    db      0xff
f00080:  02    db      0x02
f00081:  03    db      0x03
f00082:  30    db      0x30                                 ; '0'
f00083:  ff    db      0xff
f00084:  ff    db      0xff
f00085:  ff    db      0xff
f00086:  ff    db      0xff
f00087:  ff    db      0xff
f00088:  ff    db      0xff
f00089:  ff    db      0xff
f0008a:  ff    db      0xff
f0008b:  ff    db      0xff
f0008c:  ff    db      0xff
f0008d:  ff    db      0xff
f0008e:  ff    db      0xff
f0008f:  ff    db      0xff
f00090:  ff    db      0xff
f00091:  ff    db      0xff
f00092:  ff    db      0xff
f00093:  ff    db      0xff
f00094:  ff    db      0xff
f00095:  ff    db      0xff
f00096:  ff    db      0xff
f00097:  ff    db      0xff
f00098:  ff    db      0xff
f00099:  ff    db      0xff
f0009a:  ff    db      0xff
f0009b:  ff    db      0xff
f0009c:  ff    db      0xff
f0009d:  ff    db      0xff
f0009e:  ff    db      0xff
f0009f:  ff    db      0xff
f000a0:  ff    db      0xff
f000a1:  ff    db      0xff
f000a2:  ff    db      0xff
f000a3:  ff    db      0xff
f000a4:  ff    db      0xff
f000a5:  ff    db      0xff
f000a6:  ff    db      0xff
f000a7:  ff    db      0xff
f000a8:  ff    db      0xff
f000a9:  ff    db      0xff
f000aa:  ff    db      0xff
f000ab:  ff    db      0xff
f000ac:  ff    db      0xff
f000ad:  ff    db      0xff
f000ae:  ff    db      0xff
f000af:  ff    db      0xff
f000b0:  ff    db      0xff
f000b1:  ff    db      0xff
f000b2:  ff    db      0xff
f000b3:  ff    db      0xff
f000b4:  ff    db      0xff
f000b5:  ff    db      0xff
f000b6:  ff    db      0xff
f000b7:  ff    db      0xff
f000b8:  ff    db      0xff
f000b9:  ff    db      0xff
f000ba:  ff    db      0xff
f000bb:  ff    db      0xff
f000bc:  ff    db      0xff
f000bd:  ff    db      0xff
f000be:  ff    db      0xff
f000bf:  ff    db      0xff
f000c0:  ff    db      0xff
f000c1:  ff    db      0xff
f000c2:  ff    db      0xff
f000c3:  ff    db      0xff
f000c4:  ff    db      0xff
f000c5:  ff    db      0xff
f000c6:  ff    db      0xff
f000c7:  ff    db      0xff
f000c8:  ff    db      0xff
f000c9:  ff    db      0xff
f000ca:  ff    db      0xff
f000cb:  ff    db      0xff
f000cc:  ff    db      0xff
f000cd:  ff    db      0xff
f000ce:  ff    db      0xff
f000cf:  ff    db      0xff
f000d0:  ff    db      0xff
f000d1:  ff    db      0xff
f000d2:  ff    db      0xff
f000d3:  ff    db      0xff
f000d4:  ff    db      0xff
f000d5:  ff    db      0xff
f000d6:  ff    db      0xff
f000d7:  ff    db      0xff
f000d8:  ff    db      0xff
f000d9:  ff    db      0xff
f000da:  ff    db      0xff
f000db:  ff    db      0xff
f000dc:  ff    db      0xff
f000dd:  ff    db      0xff
f000de:  ff    db      0xff
f000df:  ff    db      0xff
f000e0:  ff    db      0xff
f000e1:  ff    db      0xff
f000e2:  ff    db      0xff
f000e3:  ff    db      0xff
f000e4:  ff    db      0xff
f000e5:  ff    db      0xff
f000e6:  ff    db      0xff
f000e7:  ff    db      0xff
f000e8:  ff    db      0xff
f000e9:  ff    db      0xff
f000ea:  ff    db      0xff
f000eb:  ff    db      0xff
f000ec:  ff    db      0xff
f000ed:  ff    db      0xff
f000ee:  ff    db      0xff
f000ef:  ff    db      0xff
f000f0:  ff    db      0xff
f000f1:  ff    db      0xff
f000f2:  ff    db      0xff
f000f3:  ff    db      0xff
f000f4:  ff    db      0xff
f000f5:  ff    db      0xff
f000f6:  ff    db      0xff
f000f7:  ff    db      0xff
f000f8:  ff    db      0xff
f000f9:  ff    db      0xff
f000fa:  ff    db      0xff
f000fb:  ff    db      0xff
f000fc:  ff    db      0xff
f000fd:  ff    db      0xff
f000fe:  ff    db      0xff
f000ff:  02    db      0x02


firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  550620: 03 00                        	add	eax, dword ptr [eax]
  550622: 00 e8                        	add	al, ch
  550624: a8 93                        	test	al, -0x6d
  550626: f0                           	lock
  550627: ff ba 50 00 00 00            	<unknown>
  55062d: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550633: e8 c0 93 f0 ff               	call	0x4599f8 <CODE+0x589f8>
  550638: ba 7d 00 00 00               	mov	edx, 0x7d
  55063d: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550643: e8 d4 93 f0 ff               	call	0x459a1c <CODE+0x58a1c>
  550648: ba fc 16 55 00               	mov	edx, 0x5516fc
  55064d: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550653: e8 14 9c f0 ff               	call	0x45a26c <CODE+0x5926c>
  550658: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  55065e: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550664: ba 10 17 55 00               	mov	edx, 0x551710
  550669: 8b 08                        	mov	ecx, dword ptr [eax]
  55066b: ff 51 38                     	call	dword ptr [ecx + 0x38]
  55066e: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550674: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  55067a: ba 20 17 55 00               	mov	edx, 0x551720
  55067f: 8b 08                        	mov	ecx, dword ptr [eax]
  550681: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550684: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  55068a: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550690: ba 30 17 55 00               	mov	edx, 0x551730
  550695: 8b 08                        	mov	ecx, dword ptr [eax]
  550697: ff 51 38                     	call	dword ptr [ecx + 0x38]
  55069a: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5506a0: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5506a6: ba 40 17 55 00               	mov	edx, 0x551740
  5506ab: 8b 08                        	mov	ecx, dword ptr [eax]
  5506ad: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5506b0: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5506b6: 33 d2                        	xor	edx, edx
  5506b8: 89 90 20 01 00 00            	mov	dword ptr [eax + 0x120], edx
  5506be: 89 90 24 01 00 00            	mov	dword ptr [eax + 0x124], edx
  5506c4: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5506c9: 8b 00                        	mov	eax, dword ptr [eax]
  5506cb: 33 d2                        	xor	edx, edx
  5506cd: 8a 50 5e                     	mov	dl, byte ptr [eax + 0x5e]
  5506d0: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5506d6: e8 f9 94 ee ff               	call	0x439bd4 <CODE+0x38bd4>
  5506db: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5506e1: 89 98 24 01 00 00            	mov	dword ptr [eax + 0x124], ebx
  5506e7: c7 80 20 01 00 00 88 19 55 00	mov	dword ptr [eax + 0x120], 0x551988
  5506f1: b2 01                        	mov	dl, 0x1
  5506f3: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5506f9: e8 5e 9a f0 ff               	call	0x45a15c <CODE+0x5915c>
  5506fe: 8b cb                        	mov	ecx, ebx
  550700: b2 01                        	mov	dl, 0x1
  550702: a1 a0 78 43 00               	mov	eax, dword ptr [0x4378a0]
  550707: e8 2c 91 ee ff               	call	0x439838 <CODE+0x38838>
  55070c: 89 83 18 03 00 00            	mov	dword ptr [ebx + 0x318], eax
  550712: a1 b0 91 56 00               	mov	eax, dword ptr [0x5691b0]
  550717: 8b 00                        	mov	eax, dword ptr [eax]
  550719: ba 02 00 00 00               	mov	edx, 0x2
  55071e: e8 91 09 ef ff               	call	0x4410b4 <CODE+0x400b4>
  550723: 8b d0                        	mov	edx, eax
  550725: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  55072b: 8b 08                        	mov	ecx, dword ptr [eax]
  55072d: ff 51 68                     	call	dword ptr [ecx + 0x68]
  550730: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550736: 8b 50 40                     	mov	edx, dword ptr [eax + 0x40]
  550739: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  55073f: 03 50 48                     	add	edx, dword ptr [eax + 0x48]
  550742: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550748: e8 5f 92 f0 ff               	call	0x4599ac <CODE+0x589ac>
  55074d: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550753: 8b 50 44                     	mov	edx, dword ptr [eax + 0x44]
  550756: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  55075c: e8 6f 92 f0 ff               	call	0x4599d0 <CODE+0x589d0>
  550761: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550767: 8b 50 48                     	mov	edx, dword ptr [eax + 0x48]
  55076a: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550770: e8 83 92 f0 ff               	call	0x4599f8 <CODE+0x589f8>
  550775: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  55077b: 8b 50 4c                     	mov	edx, dword ptr [eax + 0x4c]
  55077e: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550784: e8 93 92 f0 ff               	call	0x459a1c <CODE+0x58a1c>
  550789: ba 54 17 55 00               	mov	edx, 0x551754
  55078e: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550794: e8 d3 9a f0 ff               	call	0x45a26c <CODE+0x5926c>
  550799: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  55079f: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5507a5: ba 10 17 55 00               	mov	edx, 0x551710
  5507aa: 8b 08                        	mov	ecx, dword ptr [eax]
  5507ac: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5507af: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  5507b5: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5507bb: ba 20 17 55 00               	mov	edx, 0x551720
  5507c0: 8b 08                        	mov	ecx, dword ptr [eax]
  5507c2: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5507c5: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  5507cb: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5507d1: ba 30 17 55 00               	mov	edx, 0x551730
  5507d6: 8b 08                        	mov	ecx, dword ptr [eax]
  5507d8: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5507db: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  5507e1: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5507e7: ba 40 17 55 00               	mov	edx, 0x551740
  5507ec: 8b 08                        	mov	ecx, dword ptr [eax]
  5507ee: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5507f1: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  5507f7: 33 d2                        	xor	edx, edx
  5507f9: 89 90 20 01 00 00            	mov	dword ptr [eax + 0x120], edx
  5507ff: 89 90 24 01 00 00            	mov	dword ptr [eax + 0x124], edx
  550805: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55080a: 8b 00                        	mov	eax, dword ptr [eax]
  55080c: 33 d2                        	xor	edx, edx
  55080e: 8a 50 5f                     	mov	dl, byte ptr [eax + 0x5f]
  550811: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550817: e8 b8 93 ee ff               	call	0x439bd4 <CODE+0x38bd4>
  55081c: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550822: 89 98 24 01 00 00            	mov	dword ptr [eax + 0x124], ebx
  550828: c7 80 20 01 00 00 88 19 55 00	mov	dword ptr [eax + 0x120], 0x551988
  550832: b2 01                        	mov	dl, 0x1
  550834: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  55083a: e8 1d 99 f0 ff               	call	0x45a15c <CODE+0x5915c>
  55083f: 8b cb                        	mov	ecx, ebx
  550841: b2 01                        	mov	dl, 0x1
  550843: a1 a0 78 43 00               	mov	eax, dword ptr [0x4378a0]
  550848: e8 eb 8f ee ff               	call	0x439838 <CODE+0x38838>
  55084d: 89 83 1c 03 00 00            	mov	dword ptr [ebx + 0x31c], eax
  550853: a1 b0 91 56 00               	mov	eax, dword ptr [0x5691b0]
  550858: 8b 00                        	mov	eax, dword ptr [eax]
  55085a: ba 02 00 00 00               	mov	edx, 0x2
  55085f: e8 50 08 ef ff               	call	0x4410b4 <CODE+0x400b4>
  550864: 8b d0                        	mov	edx, eax
  550866: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  55086c: 8b 08                        	mov	ecx, dword ptr [eax]
  55086e: ff 51 68                     	call	dword ptr [ecx + 0x68]
  550871: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550877: 8b 50 40                     	mov	edx, dword ptr [eax + 0x40]
  55087a: 8b 83 18 03 00 00            	mov	eax, dword ptr [ebx + 0x318]
  550880: 03 50 48                     	add	edx, dword ptr [eax + 0x48]
  550883: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  550889: e8 1e 91 f0 ff               	call	0x4599ac <CODE+0x589ac>
  55088e: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  550894: 8b 50 44                     	mov	edx, dword ptr [eax + 0x44]
  550897: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  55089d: e8 2e 91 f0 ff               	call	0x4599d0 <CODE+0x589d0>
  5508a2: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5508a8: 8b 50 48                     	mov	edx, dword ptr [eax + 0x48]
  5508ab: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5508b1: e8 42 91 f0 ff               	call	0x4599f8 <CODE+0x589f8>
  5508b6: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5508bc: 8b 50 4c                     	mov	edx, dword ptr [eax + 0x4c]
  5508bf: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5508c5: e8 52 91 f0 ff               	call	0x459a1c <CODE+0x58a1c>
  5508ca: ba 68 17 55 00               	mov	edx, 0x551768
  5508cf: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5508d5: e8 92 99 f0 ff               	call	0x45a26c <CODE+0x5926c>
  5508da: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5508e0: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5508e6: ba 10 17 55 00               	mov	edx, 0x551710
  5508eb: 8b 08                        	mov	ecx, dword ptr [eax]
  5508ed: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5508f0: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5508f6: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  5508fc: ba 20 17 55 00               	mov	edx, 0x551720
  550901: 8b 08                        	mov	ecx, dword ptr [eax]
  550903: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550906: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  55090c: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550912: ba 30 17 55 00               	mov	edx, 0x551730
  550917: 8b 08                        	mov	ecx, dword ptr [eax]
  550919: ff 51 38                     	call	dword ptr [ecx + 0x38]
  55091c: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  550922: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550928: ba 40 17 55 00               	mov	edx, 0x551740
  55092d: 8b 08                        	mov	ecx, dword ptr [eax]
  55092f: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550932: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  550938: 33 d2                        	xor	edx, edx
  55093a: 89 90 20 01 00 00            	mov	dword ptr [eax + 0x120], edx
  550940: 89 90 24 01 00 00            	mov	dword ptr [eax + 0x124], edx
  550946: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55094b: 8b 00                        	mov	eax, dword ptr [eax]
  55094d: 33 d2                        	xor	edx, edx
  55094f: 8a 50 60                     	mov	dl, byte ptr [eax + 0x60]
  550952: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  550958: e8 77 92 ee ff               	call	0x439bd4 <CODE+0x38bd4>
  55095d: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  550963: 89 98 24 01 00 00            	mov	dword ptr [eax + 0x124], ebx
  550969: c7 80 20 01 00 00 88 19 55 00	mov	dword ptr [eax + 0x120], 0x551988
  550973: b2 01                        	mov	dl, 0x1
  550975: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  55097b: e8 dc 97 f0 ff               	call	0x45a15c <CODE+0x5915c>
  550980: 8b cb                        	mov	ecx, ebx
  550982: b2 01                        	mov	dl, 0x1
  550984: a1 a0 78 43 00               	mov	eax, dword ptr [0x4378a0]
  550989: e8 aa 8e ee ff               	call	0x439838 <CODE+0x38838>
  55098e: 89 83 20 03 00 00            	mov	dword ptr [ebx + 0x320], eax
  550994: a1 b0 91 56 00               	mov	eax, dword ptr [0x5691b0]
  550999: 8b 00                        	mov	eax, dword ptr [eax]
  55099b: ba 02 00 00 00               	mov	edx, 0x2
  5509a0: e8 0f 07 ef ff               	call	0x4410b4 <CODE+0x400b4>
  5509a5: 8b d0                        	mov	edx, eax
  5509a7: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  5509ad: 8b 08                        	mov	ecx, dword ptr [eax]
  5509af: ff 51 68                     	call	dword ptr [ecx + 0x68]
  5509b2: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5509b8: 8b 50 40                     	mov	edx, dword ptr [eax + 0x40]
  5509bb: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5509c1: 03 50 48                     	add	edx, dword ptr [eax + 0x48]
  5509c4: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  5509ca: e8 dd 8f f0 ff               	call	0x4599ac <CODE+0x589ac>
  5509cf: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5509d5: 8b 50 44                     	mov	edx, dword ptr [eax + 0x44]
  5509d8: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  5509de: e8 ed 8f f0 ff               	call	0x4599d0 <CODE+0x589d0>
  5509e3: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5509e9: 8b 50 48                     	mov	edx, dword ptr [eax + 0x48]
  5509ec: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  5509f2: e8 01 90 f0 ff               	call	0x4599f8 <CODE+0x589f8>
  5509f7: 8b 83 14 03 00 00            	mov	eax, dword ptr [ebx + 0x314]
  5509fd: 8b 50 4c                     	mov	edx, dword ptr [eax + 0x4c]
  550a00: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a06: e8 11 90 f0 ff               	call	0x459a1c <CODE+0x58a1c>
  550a0b: ba 7c 17 55 00               	mov	edx, 0x55177c
  550a10: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a16: e8 51 98 f0 ff               	call	0x45a26c <CODE+0x5926c>
  550a1b: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a21: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550a27: ba 10 17 55 00               	mov	edx, 0x551710
  550a2c: 8b 08                        	mov	ecx, dword ptr [eax]
  550a2e: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550a31: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a37: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550a3d: ba 20 17 55 00               	mov	edx, 0x551720
  550a42: 8b 08                        	mov	ecx, dword ptr [eax]
  550a44: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550a47: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a4d: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550a53: ba 30 17 55 00               	mov	edx, 0x551730
  550a58: 8b 08                        	mov	ecx, dword ptr [eax]
  550a5a: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550a5d: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a63: 8b 80 14 02 00 00            	mov	eax, dword ptr [eax + 0x214]
  550a69: ba 40 17 55 00               	mov	edx, 0x551740
  550a6e: 8b 08                        	mov	ecx, dword ptr [eax]
  550a70: ff 51 38                     	call	dword ptr [ecx + 0x38]
  550a73: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a79: 33 d2                        	xor	edx, edx
  550a7b: 89 90 20 01 00 00            	mov	dword ptr [eax + 0x120], edx
  550a81: 89 90 24 01 00 00            	mov	dword ptr [eax + 0x124], edx
  550a87: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  550a8c: 8b 00                        	mov	eax, dword ptr [eax]
  550a8e: 33 d2                        	xor	edx, edx
  550a90: 8a 50 61                     	mov	dl, byte ptr [eax + 0x61]
  550a93: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550a99: e8 36 91 ee ff               	call	0x439bd4 <CODE+0x38bd4>
  550a9e: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550aa4: 89 98 24 01 00 00            	mov	dword ptr [eax + 0x124], ebx
  550aaa: c7 80 20 01 00 00 88 19 55 00	mov	dword ptr [eax + 0x120], 0x551988
  550ab4: b2 01                        	mov	dl, 0x1
  550ab6: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550abc: e8 9b 96 f0 ff               	call	0x45a15c <CODE+0x5915c>
  550ac1: 8b cb                        	mov	ecx, ebx
  550ac3: b2 01                        	mov	dl, 0x1
  550ac5: a1 a0 78 43 00               	mov	eax, dword ptr [0x4378a0]
  550aca: e8 69 8d ee ff               	call	0x439838 <CODE+0x38838>
  550acf: 89 83 24 03 00 00            	mov	dword ptr [ebx + 0x324], eax
  550ad5: a1 b0 91 56 00               	mov	eax, dword ptr [0x5691b0]
  550ada: 8b 00                        	mov	eax, dword ptr [eax]
  550adc: ba 02 00 00 00               	mov	edx, 0x2
  550ae1: e8 ce 05 ef ff               	call	0x4410b4 <CODE+0x400b4>
  550ae6: 8b d0                        	mov	edx, eax
  550ae8: 8b 83 24 03 00 00            	mov	eax, dword ptr [ebx + 0x324]
  550aee: 8b 08                        	mov	ecx, dword ptr [eax]
  550af0: ff 51 68                     	call	dword ptr [ecx + 0x68]
  550af3: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  550af9: 8b 50 40                     	mov	edx, dword ptr [eax + 0x40]
  550afc: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]


firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  554f1c: 50                           	push	eax
  554f1d: 68 98 4f 55 00               	push	0x554f98
  554f22: a1 70 96 56 00               	mov	eax, dword ptr [0x569670]
  554f27: 8b 00                        	mov	eax, dword ptr [eax]
  554f29: e8 52 56 f2 ff               	call	0x47a580 <CODE+0x79580>
  554f2e: a1 70 96 56 00               	mov	eax, dword ptr [0x569670]
  554f33: 8b 00                        	mov	eax, dword ptr [eax]
  554f35: 8b 40 30                     	mov	eax, dword ptr [eax + 0x30]
  554f38: 50                           	push	eax
  554f39: e8 a2 c2 f4 ff               	call	0x4a11e0 <CODE+0xa01e0>
  554f3e: b2 01                        	mov	dl, 0x1
  554f40: a1 a4 38 55 00               	mov	eax, dword ptr [0x5538a4]
  554f45: e8 fe f1 ea ff               	call	0x404148 <CODE+0x3148>
  554f4a: a3 78 b3 57 00               	mov	dword ptr [0x57b378], eax
  554f4f: c3                           	ret
  554f50: 53                           	push	ebx
  554f51: 56                           	push	esi
  554f52: be 78 b3 57 00               	mov	esi, 0x57b378
  554f57: 33 c0                        	xor	eax, eax
  554f59: 8b 1e                        	mov	ebx, dword ptr [esi]
  554f5b: c6 44 03 25 00               	mov	byte ptr [ebx + eax + 0x25], 0x0
  554f60: 40                           	inc	eax
  554f61: 83 f8 21                     	cmp	eax, 0x21
  554f64: 75 f3                        	jne	0x554f59 <CODE+0x153f59>
  554f66: 8b 06                        	mov	eax, dword ptr [esi]
  554f68: e8 23 f6 ff ff               	call	0x554590 <CODE+0x153590>
  554f6d: 68 89 ff 00 00               	push	0xff89
  554f72: 68 d8 04 00 00               	push	0x4d8
  554f77: e8 94 c2 f4 ff               	call	0x4a1210 <CODE+0xa0210>
  554f7c: a3 80 b3 57 00               	mov	dword ptr [0x57b380], eax
  554f81: 8b 06                        	mov	eax, dword ptr [esi]
  554f83: 83 c0 25                     	add	eax, 0x25
  554f86: 50                           	push	eax
  554f87: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  554f8c: 50                           	push	eax
  554f8d: e8 76 c2 f4 ff               	call	0x4a1208 <CODE+0xa0208>
  554f92: 5e                           	pop	esi
  554f93: 5b                           	pop	ebx
  554f94: c3                           	ret
  554f95: 8d 40 00                     	lea	eax, [eax]
  554f98: 53                           	push	ebx
  554f99: 56                           	push	esi
  554f9a: 57                           	push	edi
  554f9b: 8b da                        	mov	ebx, edx
  554f9d: 33 c0                        	xor	eax, eax
  554f9f: 81 3b c8 80 00 00            	cmp	dword ptr [ebx], 0x80c8
  554fa5: 0f 85 69 03 00 00            	jne	0x555314 <CODE+0x154314>
  554fab: 8b 53 04                     	mov	edx, dword ptr [ebx + 0x4]
  554fae: 4a                           	dec	edx
  554faf: 74 1a                        	je	0x554fcb <CODE+0x153fcb>
  554fb1: 4a                           	dec	edx
  554fb2: 0f 84 44 01 00 00            	je	0x5550fc <CODE+0x1540fc>
  554fb8: 4a                           	dec	edx
  554fb9: 0f 84 05 03 00 00            	je	0x5552c4 <CODE+0x1542c4>
  554fbf: 4a                           	dec	edx
  554fc0: 0f 84 02 03 00 00            	je	0x5552c8 <CODE+0x1542c8>
  554fc6: e9 49 03 00 00               	jmp	0x555314 <CODE+0x154314>
  554fcb: 68 89 ff 00 00               	push	0xff89
  554fd0: 68 d8 04 00 00               	push	0x4d8
  554fd5: e8 5e c2 f4 ff               	call	0x4a1238 <CODE+0xa0238>
  554fda: 83 f8 01                     	cmp	eax, 0x1
  554fdd: 1b c0                        	sbb	eax, eax
  554fdf: 40                           	inc	eax
  554fe0: 3c 01                        	cmp	al, 0x1
  554fe2: 0f 85 0d 01 00 00            	jne	0x5550f5 <CODE+0x1540f5>
  554fe8: e8 0b c2 f4 ff               	call	0x4a11f8 <CODE+0xa01f8>
  554fed: 8b f0                        	mov	esi, eax
  554fef: 4e                           	dec	esi
  554ff0: 85 f6                        	test	esi, esi
  554ff2: 0f 8c fd 00 00 00            	jl	0x5550f5 <CODE+0x1540f5>
  554ff8: 46                           	inc	esi
  554ff9: 33 ff                        	xor	edi, edi
  554ffb: 57                           	push	edi
  554ffc: e8 ef c1 f4 ff               	call	0x4a11f0 <CODE+0xa01f0>
  555001: a3 80 b3 57 00               	mov	dword ptr [0x57b380], eax
  555006: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  55500b: 50                           	push	eax
  55500c: e8 07 c2 f4 ff               	call	0x4a1218 <CODE+0xa0218>
  555011: 3d d8 04 00 00               	cmp	eax, 0x4d8
  555016: 0f 85 d1 00 00 00            	jne	0x5550ed <CODE+0x1540ed>
  55501c: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  555021: 50                           	push	eax
  555022: e8 f9 c1 f4 ff               	call	0x4a1220 <CODE+0xa0220>
  555027: 3d 89 ff 00 00               	cmp	eax, 0xff89
  55502c: 0f 85 bb 00 00 00            	jne	0x5550ed <CODE+0x1540ed>
  555032: 6a ff                        	push	-0x1
  555034: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  555039: 50                           	push	eax
  55503a: e8 f1 c1 f4 ff               	call	0x4a1230 <CODE+0xa0230>
  55503f: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  555044: 33 d2                        	xor	edx, edx
  555046: 52                           	push	edx
  555047: 50                           	push	eax
  555048: 8b 43 08                     	mov	eax, dword ptr [ebx + 0x8]
  55504b: 99                           	cdq
  55504c: 3b 54 24 04                  	cmp	edx, dword ptr [esp + 0x4]
  555050: 75 03                        	jne	0x555055 <CODE+0x154055>
  555052: 3b 04 24                     	cmp	eax, dword ptr [esp]
  555055: 5a                           	pop	edx
  555056: 58                           	pop	eax
  555057: 0f 85 90 00 00 00            	jne	0x5550ed <CODE+0x1540ed>
  55505d: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555062: 8b 00                        	mov	eax, dword ptr [eax]
  555064: 8b 80 ec 04 00 00            	mov	eax, dword ptr [eax + 0x4ec]
  55506a: b2 01                        	mov	dl, 0x1
  55506c: e8 9f 76 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555071: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555076: 8b 00                        	mov	eax, dword ptr [eax]
  555078: 8b 80 f0 04 00 00            	mov	eax, dword ptr [eax + 0x4f0]
  55507e: b2 01                        	mov	dl, 0x1
  555080: e8 8b 76 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555085: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55508a: 8b 00                        	mov	eax, dword ptr [eax]
  55508c: 8b 80 34 06 00 00            	mov	eax, dword ptr [eax + 0x634]
  555092: b2 01                        	mov	dl, 0x1
  555094: e8 77 76 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555099: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55509e: 8b 00                        	mov	eax, dword ptr [eax]
  5550a0: 8b 80 2c 06 00 00            	mov	eax, dword ptr [eax + 0x62c]
  5550a6: b2 01                        	mov	dl, 0x1
  5550a8: e8 63 76 f1 ff               	call	0x46c710 <CODE+0x6b710>
  5550ad: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  5550b2: 8b 00                        	mov	eax, dword ptr [eax]
  5550b4: 8b 80 64 03 00 00            	mov	eax, dword ptr [eax + 0x364]
  5550ba: 8b 80 6c 01 00 00            	mov	eax, dword ptr [eax + 0x16c]
  5550c0: ba 00 ff 00 00               	mov	edx, 0xff00
  5550c5: e8 22 2f ed ff               	call	0x427fec <CODE+0x26fec>
  5550ca: 68 00 01 00 00               	push	0x100
  5550cf: 68 84 b3 57 00               	push	0x57b384
  5550d4: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  5550d9: 50                           	push	eax
  5550da: e8 49 c1 f4 ff               	call	0x4a1228 <CODE+0xa0228>
  5550df: b1 01                        	mov	cl, 0x1
  5550e1: b2 06                        	mov	dl, 0x6
  5550e3: a1 70 b3 57 00               	mov	eax, dword ptr [0x57b370]
  5550e8: e8 63 fe ff ff               	call	0x554f50 <CODE+0x153f50>
  5550ed: 47                           	inc	edi
  5550ee: 4e                           	dec	esi
  5550ef: 0f 85 06 ff ff ff            	jne	0x554ffb <CODE+0x153ffb>
  5550f5: b0 01                        	mov	al, 0x1
  5550f7: e9 18 02 00 00               	jmp	0x555314 <CODE+0x154314>
  5550fc: 68 89 ff 00 00               	push	0xff89
  555101: 68 d8 04 00 00               	push	0x4d8
  555106: e8 2d c1 f4 ff               	call	0x4a1238 <CODE+0xa0238>
  55510b: 83 f8 01                     	cmp	eax, 0x1
  55510e: 1b c0                        	sbb	eax, eax
  555110: 40                           	inc	eax
  555111: 84 c0                        	test	al, al
  555113: 0f 85 a7 01 00 00            	jne	0x5552c0 <CODE+0x1542c0>
  555119: e8 ca c0 f4 ff               	call	0x4a11e8 <CODE+0xa01e8>
  55511e: a1 70 96 56 00               	mov	eax, dword ptr [0x569670]
  555123: 8b 00                        	mov	eax, dword ptr [eax]
  555125: 8b 40 30                     	mov	eax, dword ptr [eax + 0x30]
  555128: 50                           	push	eax
  555129: e8 b2 c0 f4 ff               	call	0x4a11e0 <CODE+0xa01e0>
  55512e: a1 78 b3 57 00               	mov	eax, dword ptr [0x57b378]
  555133: c6 40 56 00                  	mov	byte ptr [eax + 0x56], 0x0
  555137: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55513c: 8b 00                        	mov	eax, dword ptr [eax]
  55513e: 8b 80 ec 04 00 00            	mov	eax, dword ptr [eax + 0x4ec]
  555144: 33 d2                        	xor	edx, edx
  555146: e8 c5 75 f1 ff               	call	0x46c710 <CODE+0x6b710>
  55514b: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555150: 8b 00                        	mov	eax, dword ptr [eax]
  555152: 8b 80 f0 04 00 00            	mov	eax, dword ptr [eax + 0x4f0]
  555158: 33 d2                        	xor	edx, edx
  55515a: e8 b1 75 f1 ff               	call	0x46c710 <CODE+0x6b710>
  55515f: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555164: 8b 00                        	mov	eax, dword ptr [eax]
  555166: 8b 80 34 06 00 00            	mov	eax, dword ptr [eax + 0x634]
  55516c: 33 d2                        	xor	edx, edx
  55516e: e8 9d 75 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555173: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555178: 8b 00                        	mov	eax, dword ptr [eax]
  55517a: 8b 80 2c 06 00 00            	mov	eax, dword ptr [eax + 0x62c]
  555180: 33 d2                        	xor	edx, edx
  555182: e8 89 75 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555187: a1 20 9a 56 00               	mov	eax, dword ptr [0x569a20]
  55518c: 8b 00                        	mov	eax, dword ptr [eax]
  55518e: 80 78 57 01                  	cmp	byte ptr [eax + 0x57], 0x1
  555192: 75 1d                        	jne	0x5551b1 <CODE+0x1541b1>
  555194: a1 44 97 56 00               	mov	eax, dword ptr [0x569744]
  555199: 8b 00                        	mov	eax, dword ptr [eax]
  55519b: ba 20 53 55 00               	mov	edx, 0x555320
  5551a0: e8 93 69 ff ff               	call	0x54bb38 <CODE+0x14ab38>
  5551a5: a1 20 9a 56 00               	mov	eax, dword ptr [0x569a20]
  5551aa: 8b 00                        	mov	eax, dword ptr [eax]
  5551ac: e8 0f 1f f2 ff               	call	0x4770c0 <CODE+0x760c0>
  5551b1: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  5551b6: 8b 00                        	mov	eax, dword ptr [eax]
  5551b8: 8b 80 64 03 00 00            	mov	eax, dword ptr [eax + 0x364]
  5551be: 8b 80 6c 01 00 00            	mov	eax, dword ptr [eax + 0x16c]
  5551c4: ba ff 00 00 00               	mov	edx, 0xff
  5551c9: e8 1e 2e ed ff               	call	0x427fec <CODE+0x26fec>
  5551ce: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5551d3: 8b 00                        	mov	eax, dword ptr [eax]
  5551d5: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  5551db: 8b 10                        	mov	edx, dword ptr [eax]
  5551dd: ff 92 80 00 00 00            	call	dword ptr [edx + 0x80]
  5551e3: a1 78 b3 57 00               	mov	eax, dword ptr [0x57b378]
  5551e8: c6 40 4d 64                  	mov	byte ptr [eax + 0x4d], 0x64
  5551ec: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  5551f1: 8b 00                        	mov	eax, dword ptr [eax]
  5551f3: e8 c8 13 00 00               	call	0x5565c0 <CODE+0x1555c0>
  5551f8: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  5551fd: 8b 00                        	mov	eax, dword ptr [eax]
  5551ff: 8b 80 9c 03 00 00            	mov	eax, dword ptr [eax + 0x39c]
  555205: b2 01                        	mov	dl, 0x1
  555207: e8 04 75 f1 ff               	call	0x46c710 <CODE+0x6b710>
  55520c: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  555211: 8b 00                        	mov	eax, dword ptr [eax]
  555213: 8b 80 a0 03 00 00            	mov	eax, dword ptr [eax + 0x3a0]
  555219: b2 01                        	mov	dl, 0x1
  55521b: e8 f0 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555220: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  555225: 8b 00                        	mov	eax, dword ptr [eax]
  555227: 8b 80 a8 03 00 00            	mov	eax, dword ptr [eax + 0x3a8]
  55522d: b2 01                        	mov	dl, 0x1
  55522f: e8 dc 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555234: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  555239: 8b 00                        	mov	eax, dword ptr [eax]
  55523b: 8b 80 b0 03 00 00            	mov	eax, dword ptr [eax + 0x3b0]
  555241: b2 01                        	mov	dl, 0x1
  555243: e8 c8 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555248: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  55524d: 8b 00                        	mov	eax, dword ptr [eax]
  55524f: 8b 80 a4 03 00 00            	mov	eax, dword ptr [eax + 0x3a4]
  555255: b2 01                        	mov	dl, 0x1
  555257: e8 b4 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  55525c: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555261: 8b 00                        	mov	eax, dword ptr [eax]
  555263: 8b 80 d8 05 00 00            	mov	eax, dword ptr [eax + 0x5d8]
  555269: b2 01                        	mov	dl, 0x1
  55526b: e8 a0 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555270: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555275: 8b 00                        	mov	eax, dword ptr [eax]
  555277: 8b 80 dc 05 00 00            	mov	eax, dword ptr [eax + 0x5dc]
  55527d: b2 01                        	mov	dl, 0x1
  55527f: e8 8c 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555284: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  555289: 8b 00                        	mov	eax, dword ptr [eax]
  55528b: 8b 80 18 06 00 00            	mov	eax, dword ptr [eax + 0x618]
  555291: b2 01                        	mov	dl, 0x1
  555293: e8 78 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  555298: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55529d: 8b 00                        	mov	eax, dword ptr [eax]
  55529f: 8b 80 e0 05 00 00            	mov	eax, dword ptr [eax + 0x5e0]
  5552a5: b2 01                        	mov	dl, 0x1
  5552a7: e8 64 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  5552ac: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5552b1: 8b 00                        	mov	eax, dword ptr [eax]
  5552b3: 8b 80 14 06 00 00            	mov	eax, dword ptr [eax + 0x614]
  5552b9: b2 01                        	mov	dl, 0x1
  5552bb: e8 50 74 f1 ff               	call	0x46c710 <CODE+0x6b710>
  5552c0: b0 01                        	mov	al, 0x1
  5552c2: eb 50                        	jmp	0x555314 <CODE+0x154314>
  5552c4: b0 01                        	mov	al, 0x1
  5552c6: eb 4c                        	jmp	0x555314 <CODE+0x154314>
  5552c8: 8b 43 08                     	mov	eax, dword ptr [ebx + 0x8]
  5552cb: a3 80 b3 57 00               	mov	dword ptr [0x57b380], eax
  5552d0: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  5552d5: 50                           	push	eax
  5552d6: e8 3d bf f4 ff               	call	0x4a1218 <CODE+0xa0218>
  5552db: 3d d8 04 00 00               	cmp	eax, 0x4d8
  5552e0: 75 30                        	jne	0x555312 <CODE+0x154312>
  5552e2: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  5552e7: 50                           	push	eax
  5552e8: e8 33 bf f4 ff               	call	0x4a1220 <CODE+0xa0220>
  5552ed: 3d 89 ff 00 00               	cmp	eax, 0xff89
  5552f2: 75 1e                        	jne	0x555312 <CODE+0x154312>
  5552f4: a1 78 b3 57 00               	mov	eax, dword ptr [0x57b378]
  5552f9: 83 c0 04                     	add	eax, 0x4
  5552fc: 50                           	push	eax
  5552fd: a1 80 b3 57 00               	mov	eax, dword ptr [0x57b380]
  555302: 50                           	push	eax
  555303: e8 f8 be f4 ff               	call	0x4a1200 <CODE+0xa0200>
  555308: a1 78 b3 57 00               	mov	eax, dword ptr [0x57b378]
  55530d: e8 fe e5 ff ff               	call	0x553910 <CODE+0x152910>
  555312: b0 01                        	mov	al, 0x1
  555314: 5f                           	pop	edi
  555315: 5e                           	pop	esi
  555316: 5b                           	pop	ebx
  555317: c3                           	ret
  555318: ff ff                        	<unknown>
  55531a: ff ff                        	<unknown>
  55531c: 0f 00 00                     	sldt	word ptr [eax]
  55531f: 00 43 6f                     	add	byte ptr [ebx + 0x6f], al


firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  553910: 55                           	push	ebp
  553911: 8b ec                        	mov	ebp, esp
  553913: b9 04 00 00 00               	mov	ecx, 0x4
  553918: 6a 00                        	push	0x0
  55391a: 6a 00                        	push	0x0
  55391c: 49                           	dec	ecx
  55391d: 75 f9                        	jne	0x553918 <CODE+0x152918>
  55391f: 51                           	push	ecx
  553920: 53                           	push	ebx
  553921: 56                           	push	esi
  553922: 57                           	push	edi
  553923: 8b f8                        	mov	edi, eax
  553925: 33 c0                        	xor	eax, eax
  553927: 55                           	push	ebp
  553928: 68 42 44 55 00               	push	0x554442
  55392d: 64 ff 30                     	push	dword ptr fs:[eax]
  553930: 64 89 20                     	mov	dword ptr fs:[eax], esp
  553933: 8a 5f 05                     	mov	bl, byte ptr [edi + 0x5]
  553936: 33 c0                        	xor	eax, eax
  553938: 8a c3                        	mov	al, bl
  55393a: 83 f8 07                     	cmp	eax, 0x7
  55393d: 7d 1f                        	jge	0x55395e <CODE+0x15295e>
  55393f: 83 e8 03                     	sub	eax, 0x3
  553942: 74 42                        	je	0x553986 <CODE+0x152986>
  553944: 48                           	dec	eax
  553945: 0f 84 38 02 00 00            	je	0x553b83 <CODE+0x152b83>
  55394b: 48                           	dec	eax
  55394c: 0f 84 64 05 00 00            	je	0x553eb6 <CODE+0x152eb6>
  553952: 48                           	dec	eax
  553953: 0f 84 a3 06 00 00            	je	0x553ffc <CODE+0x152ffc>
  553959: e9 c9 0a 00 00               	jmp	0x554427 <CODE+0x153427>
  55395e: 83 c0 f9                     	add	eax, -0x7
  553961: 83 e8 07                     	sub	eax, 0x7
  553964: 0f 82 a6 07 00 00            	jb	0x554110 <CODE+0x153110>
  55396a: 83 e8 32                     	sub	eax, 0x32
  55396d: 0f 84 36 08 00 00            	je	0x5541a9 <CODE+0x1531a9>
  553973: 48                           	dec	eax
  553974: 0f 84 a9 09 00 00            	je	0x554323 <CODE+0x153323>
  55397a: 48                           	dec	eax
  55397b: 0f 84 e5 08 00 00            	je	0x554266 <CODE+0x153266>
  553981: e9 a1 0a 00 00               	jmp	0x554427 <CODE+0x153427>
  553986: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55398b: 8b 00                        	mov	eax, dword ptr [eax]
  55398d: 05 58 09 70 00               	add	eax, 0x700958
  553992: e8 9d 16 eb ff               	call	0x405034 <CODE+0x4034>
  553997: be 03 00 00 00               	mov	esi, 0x3
  55399c: 8d 45 fc                     	lea	eax, [ebp - 0x4]
  55399f: e8 90 16 eb ff               	call	0x405034 <CODE+0x4034>
  5539a4: 8a 5c 37 04                  	mov	bl, byte ptr [edi + esi + 0x4]
  5539a8: 80 fb ff                     	cmp	bl, -0x1
  5539ab: 74 23                        	je	0x5539d0 <CODE+0x1529d0>
  5539ad: 8d 45 fc                     	lea	eax, [ebp - 0x4]
  5539b0: 8b d3                        	mov	edx, ebx
  5539b2: e8 65 18 eb ff               	call	0x40521c <CODE+0x421c>
  5539b7: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5539bc: 8b 00                        	mov	eax, dword ptr [eax]
  5539be: 05 58 09 70 00               	add	eax, 0x700958
  5539c3: 8b 55 fc                     	mov	edx, dword ptr [ebp - 0x4]
  5539c6: e8 31 19 eb ff               	call	0x4052fc <CODE+0x42fc>
  5539cb: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5539d0: 46                           	inc	esi
  5539d1: 83 fe 21                     	cmp	esi, 0x21
  5539d4: 75 c6                        	jne	0x55399c <CODE+0x15299c>
  5539d6: a1 f8 99 56 00               	mov	eax, dword ptr [0x5699f8]
  5539db: 8b 00                        	mov	eax, dword ptr [eax]
  5539dd: 8b 80 18 03 00 00            	mov	eax, dword ptr [eax + 0x318]
  5539e3: ba 58 44 55 00               	mov	edx, 0x554458
  5539e8: e8 7f 68 f0 ff               	call	0x45a26c <CODE+0x5926c>
  5539ed: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5539f2: 8b 00                        	mov	eax, dword ptr [eax]
  5539f4: 83 b8 58 09 70 00 00         	cmp	dword ptr [eax + 0x700958], 0x0
  5539fb: 0f 84 26 0a 00 00            	je	0x554427 <CODE+0x153427>
  553a01: 80 7f 06 08                  	cmp	byte ptr [edi + 0x6], 0x8
  553a05: 74 30                        	je	0x553a37 <CODE+0x152a37>
  553a07: 80 7f 06 09                  	cmp	byte ptr [edi + 0x6], 0x9
  553a0b: 0f 85 16 0a 00 00            	jne	0x554427 <CODE+0x153427>
  553a11: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553a16: 8b 00                        	mov	eax, dword ptr [eax]
  553a18: 8b 80 58 09 70 00            	mov	eax, dword ptr [eax + 0x700958]
  553a1e: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553a24: 8b 12                        	mov	edx, dword ptr [edx]
  553a26: 8b 92 50 09 70 00            	mov	edx, dword ptr [edx + 0x700950]
  553a2c: e8 0f 1a eb ff               	call	0x405440 <CODE+0x4440>
  553a31: 0f 85 f0 09 00 00            	jne	0x554427 <CODE+0x153427>
  553a37: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553a3c: 8b 00                        	mov	eax, dword ptr [eax]
  553a3e: 8b 80 58 09 70 00            	mov	eax, dword ptr [eax + 0x700958]
  553a44: e8 ab 18 eb ff               	call	0x4052f4 <CODE+0x42f4>
  553a49: 83 f8 1e                     	cmp	eax, 0x1e
  553a4c: 75 63                        	jne	0x553ab1 <CODE+0x152ab1>
  553a4e: 8d 45 f8                     	lea	eax, [ebp - 0x8]
  553a51: 50                           	push	eax
  553a52: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553a57: 8b 00                        	mov	eax, dword ptr [eax]
  553a59: 8b 80 58 09 70 00            	mov	eax, dword ptr [eax + 0x700958]
  553a5f: b9 04 00 00 00               	mov	ecx, 0x4
  553a64: ba 1b 00 00 00               	mov	edx, 0x1b
  553a69: e8 e6 1a eb ff               	call	0x405554 <CODE+0x4554>
  553a6e: 8b 45 f8                     	mov	eax, dword ptr [ebp - 0x8]
  553a71: ba 80 44 55 00               	mov	edx, 0x554480
  553a76: e8 c5 19 eb ff               	call	0x405440 <CODE+0x4440>
  553a7b: 75 34                        	jne	0x553ab1 <CODE+0x152ab1>
  553a7d: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553a82: 8b 00                        	mov	eax, dword ptr [eax]
  553a84: 8b 88 58 09 70 00            	mov	ecx, dword ptr [eax + 0x700958]
  553a8a: 8d 45 f4                     	lea	eax, [ebp - 0xc]
  553a8d: ba 90 44 55 00               	mov	edx, 0x554490
  553a92: e8 a9 18 eb ff               	call	0x405340 <CODE+0x4340>
  553a97: 8b 55 f4                     	mov	edx, dword ptr [ebp - 0xc]
  553a9a: a1 f8 99 56 00               	mov	eax, dword ptr [0x5699f8]
  553a9f: 8b 00                        	mov	eax, dword ptr [eax]
  553aa1: 8b 80 18 03 00 00            	mov	eax, dword ptr [eax + 0x318]
  553aa7: e8 c0 67 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553aac: e9 76 09 00 00               	jmp	0x554427 <CODE+0x153427>
  553ab1: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553ab6: 8b 00                        	mov	eax, dword ptr [eax]
  553ab8: 8b 80 58 09 70 00            	mov	eax, dword ptr [eax + 0x700958]
  553abe: e8 31 18 eb ff               	call	0x4052f4 <CODE+0x42f4>
  553ac3: 83 f8 1e                     	cmp	eax, 0x1e
  553ac6: 0f 85 83 00 00 00            	jne	0x553b4f <CODE+0x152b4f>
  553acc: 8d 45 f0                     	lea	eax, [ebp - 0x10]
  553acf: 50                           	push	eax
  553ad0: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553ad5: 8b 00                        	mov	eax, dword ptr [eax]
  553ad7: 8b 80 58 09 70 00            	mov	eax, dword ptr [eax + 0x700958]
  553add: b9 04 00 00 00               	mov	ecx, 0x4
  553ae2: ba 1b 00 00 00               	mov	edx, 0x1b
  553ae7: e8 68 1a eb ff               	call	0x405554 <CODE+0x4554>
  553aec: 8b 45 f0                     	mov	eax, dword ptr [ebp - 0x10]
  553aef: ba 80 44 55 00               	mov	edx, 0x554480
  553af4: e8 47 19 eb ff               	call	0x405440 <CODE+0x4440>
  553af9: 74 54                        	je	0x553b4f <CODE+0x152b4f>
  553afb: 68 90 44 55 00               	push	0x554490
  553b00: 8d 45 e8                     	lea	eax, [ebp - 0x18]
  553b03: 50                           	push	eax
  553b04: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553b09: 8b 00                        	mov	eax, dword ptr [eax]
  553b0b: 8b 80 58 09 70 00            	mov	eax, dword ptr [eax + 0x700958]
  553b11: b9 1b 00 00 00               	mov	ecx, 0x1b
  553b16: ba 01 00 00 00               	mov	edx, 0x1
  553b1b: e8 34 1a eb ff               	call	0x405554 <CODE+0x4554>
  553b20: ff 75 e8                     	push	dword ptr [ebp - 0x18]
  553b23: 68 a8 44 55 00               	push	0x5544a8
  553b28: 8d 45 ec                     	lea	eax, [ebp - 0x14]
  553b2b: ba 03 00 00 00               	mov	edx, 0x3
  553b30: e8 7f 18 eb ff               	call	0x4053b4 <CODE+0x43b4>
  553b35: 8b 55 ec                     	mov	edx, dword ptr [ebp - 0x14]
  553b38: a1 f8 99 56 00               	mov	eax, dword ptr [0x5699f8]
  553b3d: 8b 00                        	mov	eax, dword ptr [eax]
  553b3f: 8b 80 18 03 00 00            	mov	eax, dword ptr [eax + 0x318]
  553b45: e8 22 67 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553b4a: e9 d8 08 00 00               	jmp	0x554427 <CODE+0x153427>
  553b4f: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553b54: 8b 00                        	mov	eax, dword ptr [eax]
  553b56: 8b 88 58 09 70 00            	mov	ecx, dword ptr [eax + 0x700958]
  553b5c: 8d 45 e4                     	lea	eax, [ebp - 0x1c]
  553b5f: ba 90 44 55 00               	mov	edx, 0x554490
  553b64: e8 d7 17 eb ff               	call	0x405340 <CODE+0x4340>
  553b69: 8b 55 e4                     	mov	edx, dword ptr [ebp - 0x1c]
  553b6c: a1 f8 99 56 00               	mov	eax, dword ptr [0x5699f8]
  553b71: 8b 00                        	mov	eax, dword ptr [eax]
  553b73: 8b 80 18 03 00 00            	mov	eax, dword ptr [eax + 0x318]
  553b79: e8 ee 66 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553b7e: e9 a4 08 00 00               	jmp	0x554427 <CODE+0x153427>
  553b83: 8a 47 06                     	mov	al, byte ptr [edi + 0x6]
  553b86: fe c8                        	dec	al
  553b88: 74 0d                        	je	0x553b97 <CODE+0x152b97>
  553b8a: fe c8                        	dec	al
  553b8c: 0f 84 ba 00 00 00            	je	0x553c4c <CODE+0x152c4c>
  553b92: e9 90 08 00 00               	jmp	0x554427 <CODE+0x153427>
  553b97: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553b9d: 8b 12                        	mov	edx, dword ptr [edx]
  553b9f: 8a 47 07                     	mov	al, byte ptr [edi + 0x7]
  553ba2: 88 82 75 09 70 00            	mov	byte ptr [edx + 0x700975], al
  553ba8: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553bae: 3c 01                        	cmp	al, 0x1
  553bb0: 75 76                        	jne	0x553c28 <CODE+0x152c28>
  553bb2: 8a 47 08                     	mov	al, byte ptr [edi + 0x8]
  553bb5: 3c 03                        	cmp	al, 0x3
  553bb7: 75 1c                        	jne	0x553bd5 <CODE+0x152bd5>
  553bb9: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553bbe: 8b 00                        	mov	eax, dword ptr [eax]
  553bc0: 8b 80 30 03 00 00            	mov	eax, dword ptr [eax + 0x330]
  553bc6: b2 01                        	mov	dl, 0x1
  553bc8: 8b 08                        	mov	ecx, dword ptr [eax]
  553bca: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  553bd0: e9 52 08 00 00               	jmp	0x554427 <CODE+0x153427>
  553bd5: 3c 04                        	cmp	al, 0x4
  553bd7: 75 1c                        	jne	0x553bf5 <CODE+0x152bf5>
  553bd9: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553bde: 8b 00                        	mov	eax, dword ptr [eax]
  553be0: 8b 80 34 03 00 00            	mov	eax, dword ptr [eax + 0x334]
  553be6: b2 01                        	mov	dl, 0x1
  553be8: 8b 08                        	mov	ecx, dword ptr [eax]
  553bea: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  553bf0: e9 32 08 00 00               	jmp	0x554427 <CODE+0x153427>
  553bf5: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553bfa: 8b 00                        	mov	eax, dword ptr [eax]
  553bfc: 8b 80 30 03 00 00            	mov	eax, dword ptr [eax + 0x330]
  553c02: 33 d2                        	xor	edx, edx
  553c04: 8b 08                        	mov	ecx, dword ptr [eax]
  553c06: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  553c0c: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553c11: 8b 00                        	mov	eax, dword ptr [eax]
  553c13: 8b 80 34 03 00 00            	mov	eax, dword ptr [eax + 0x334]
  553c19: 33 d2                        	xor	edx, edx
  553c1b: 8b 08                        	mov	ecx, dword ptr [eax]
  553c1d: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  553c23: e9 ff 07 00 00               	jmp	0x554427 <CODE+0x153427>
  553c28: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553c2e: 3c 02                        	cmp	al, 0x2
  553c30: 0f 85 f1 07 00 00            	jne	0x554427 <CODE+0x153427>
  553c36: a1 44 97 56 00               	mov	eax, dword ptr [0x569744]
  553c3b: 8b 00                        	mov	eax, dword ptr [eax]
  553c3d: ba b4 44 55 00               	mov	edx, 0x5544b4
  553c42: e8 f1 7e ff ff               	call	0x54bb38 <CODE+0x14ab38>
  553c47: e9 db 07 00 00               	jmp	0x554427 <CODE+0x153427>
  553c4c: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553c51: 8b 00                        	mov	eax, dword ptr [eax]
  553c53: 8b 80 30 06 00 00            	mov	eax, dword ptr [eax + 0x630]
  553c59: 33 d2                        	xor	edx, edx
  553c5b: e8 b0 51 ee ff               	call	0x438e10 <CODE+0x37e10>
  553c60: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553c65: 8b 00                        	mov	eax, dword ptr [eax]
  553c67: 8a 57 09                     	mov	dl, byte ptr [edi + 0x9]
  553c6a: 88 90 64 09 70 00            	mov	byte ptr [eax + 0x700964], dl
  553c70: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553c75: 8b 00                        	mov	eax, dword ptr [eax]
  553c77: 05 68 09 70 00               	add	eax, 0x700968
  553c7c: e8 b3 13 eb ff               	call	0x405034 <CODE+0x4034>
  553c81: be 06 00 00 00               	mov	esi, 0x6
  553c86: 8d 45 fc                     	lea	eax, [ebp - 0x4]
  553c89: e8 a6 13 eb ff               	call	0x405034 <CODE+0x4034>
  553c8e: 8a 44 37 04                  	mov	al, byte ptr [edi + esi + 0x4]
  553c92: 3c 2f                        	cmp	al, 0x2f
  553c94: 76 04                        	jbe	0x553c9a <CODE+0x152c9a>
  553c96: 3c 3a                        	cmp	al, 0x3a
  553c98: 72 1c                        	jb	0x553cb6 <CODE+0x152cb6>
  553c9a: 8a 54 37 04                  	mov	dl, byte ptr [edi + esi + 0x4]
  553c9e: 80 fa 40                     	cmp	dl, 0x40
  553ca1: 76 05                        	jbe	0x553ca8 <CODE+0x152ca8>
  553ca3: 80 fa 5b                     	cmp	dl, 0x5b
  553ca6: 72 0e                        	jb	0x553cb6 <CODE+0x152cb6>
  553ca8: 8a 4c 37 04                  	mov	cl, byte ptr [edi + esi + 0x4]
  553cac: 80 f9 60                     	cmp	cl, 0x60
  553caf: 76 2a                        	jbe	0x553cdb <CODE+0x152cdb>
  553cb1: 80 f9 7b                     	cmp	cl, 0x7b
  553cb4: 73 25                        	jae	0x553cdb <CODE+0x152cdb>
  553cb6: 8d 45 fc                     	lea	eax, [ebp - 0x4]
  553cb9: 8a 54 37 04                  	mov	dl, byte ptr [edi + esi + 0x4]
  553cbd: e8 5a 15 eb ff               	call	0x40521c <CODE+0x421c>
  553cc2: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553cc7: 8b 00                        	mov	eax, dword ptr [eax]
  553cc9: 05 68 09 70 00               	add	eax, 0x700968
  553cce: 8b 55 fc                     	mov	edx, dword ptr [ebp - 0x4]
  553cd1: e8 26 16 eb ff               	call	0x4052fc <CODE+0x42fc>
  553cd6: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553cdb: 46                           	inc	esi
  553cdc: 83 fe 15                     	cmp	esi, 0x15
  553cdf: 75 a5                        	jne	0x553c86 <CODE+0x152c86>
  553ce1: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553ce6: 8b 00                        	mov	eax, dword ptr [eax]
  553ce8: 80 b8 64 09 70 00 05         	cmp	byte ptr [eax + 0x700964], 0x5
  553cef: 75 3f                        	jne	0x553d30 <CODE+0x152d30>
  553cf1: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553cf6: 8b 00                        	mov	eax, dword ptr [eax]
  553cf8: 83 b8 68 09 70 00 00         	cmp	dword ptr [eax + 0x700968], 0x0
  553cff: 75 2f                        	jne	0x553d30 <CODE+0x152d30>
  553d01: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553d06: 8b 00                        	mov	eax, dword ptr [eax]
  553d08: 33 d2                        	xor	edx, edx
  553d0a: 8b 08                        	mov	ecx, dword ptr [eax]
  553d0c: ff 51 64                     	call	dword ptr [ecx + 0x64]
  553d0f: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553d14: 8b 00                        	mov	eax, dword ptr [eax]
  553d16: 33 d2                        	xor	edx, edx
  553d18: e8 d7 9f ef ff               	call	0x44dcf4 <CODE+0x4ccf4>
  553d1d: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553d22: 8b 00                        	mov	eax, dword ptr [eax]
  553d24: ba cc 44 55 00               	mov	edx, 0x5544cc
  553d29: e8 3e 65 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553d2e: eb 4a                        	jmp	0x553d7a <CODE+0x152d7a>
  553d30: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553d35: 8b 00                        	mov	eax, dword ptr [eax]
  553d37: 80 b8 64 09 70 00 05         	cmp	byte ptr [eax + 0x700964], 0x5
  553d3e: 75 3a                        	jne	0x553d7a <CODE+0x152d7a>
  553d40: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553d45: 8b 00                        	mov	eax, dword ptr [eax]
  553d47: 83 b8 68 09 70 00 00         	cmp	dword ptr [eax + 0x700968], 0x0
  553d4e: 74 2a                        	je	0x553d7a <CODE+0x152d7a>
  553d50: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553d55: 8b 00                        	mov	eax, dword ptr [eax]
  553d57: b2 01                        	mov	dl, 0x1
  553d59: 8b 08                        	mov	ecx, dword ptr [eax]
  553d5b: ff 51 64                     	call	dword ptr [ecx + 0x64]
  553d5e: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553d63: 8b 00                        	mov	eax, dword ptr [eax]
  553d65: b2 2a                        	mov	dl, 0x2a
  553d67: e8 88 9f ef ff               	call	0x44dcf4 <CODE+0x4ccf4>
  553d6c: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553d71: 8b 00                        	mov	eax, dword ptr [eax]
  553d73: 33 d2                        	xor	edx, edx
  553d75: e8 f2 64 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553d7a: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553d7f: 8b 00                        	mov	eax, dword ptr [eax]
  553d81: 80 b8 64 09 70 00 06         	cmp	byte ptr [eax + 0x700964], 0x6
  553d88: 75 3f                        	jne	0x553dc9 <CODE+0x152dc9>
  553d8a: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553d8f: 8b 00                        	mov	eax, dword ptr [eax]
  553d91: 8b 80 68 09 70 00            	mov	eax, dword ptr [eax + 0x700968]
  553d97: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553d9d: 8b 12                        	mov	edx, dword ptr [edx]
  553d9f: 8b 92 6c 09 70 00            	mov	edx, dword ptr [edx + 0x70096c]
  553da5: e8 96 16 eb ff               	call	0x405440 <CODE+0x4440>
  553daa: 75 1d                        	jne	0x553dc9 <CODE+0x152dc9>
  553dac: a1 44 97 56 00               	mov	eax, dword ptr [0x569744]
  553db1: 8b 00                        	mov	eax, dword ptr [eax]
  553db3: ba e4 44 55 00               	mov	edx, 0x5544e4
  553db8: e8 7b 7d ff ff               	call	0x54bb38 <CODE+0x14ab38>
  553dbd: a1 20 9a 56 00               	mov	eax, dword ptr [0x569a20]
  553dc2: 8b 00                        	mov	eax, dword ptr [eax]
  553dc4: e8 f7 32 f2 ff               	call	0x4770c0 <CODE+0x760c0>
  553dc9: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553dce: 8b 00                        	mov	eax, dword ptr [eax]
  553dd0: 80 b8 64 09 70 00 07         	cmp	byte ptr [eax + 0x700964], 0x7
  553dd7: 0f 85 4a 06 00 00            	jne	0x554427 <CODE+0x153427>
  553ddd: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553de2: 8b 00                        	mov	eax, dword ptr [eax]
  553de4: 83 b8 68 09 70 00 00         	cmp	dword ptr [eax + 0x700968], 0x0
  553deb: 0f 85 8a 00 00 00            	jne	0x553e7b <CODE+0x152e7b>
  553df1: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553df6: 8b 00                        	mov	eax, dword ptr [eax]
  553df8: 8b 80 70 09 70 00            	mov	eax, dword ptr [eax + 0x700970]
  553dfe: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553e04: 8b 12                        	mov	edx, dword ptr [edx]
  553e06: 3b 82 ec 04 00 00            	cmp	eax, dword ptr [edx + 0x4ec]
  553e0c: 75 0e                        	jne	0x553e1c <CODE+0x152e1c>
  553e0e: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553e13: 8b 00                        	mov	eax, dword ptr [eax]
  553e15: 8b d7                        	mov	edx, edi
  553e17: e8 d4 d8 00 00               	call	0x5616f0 <CODE+0x1606f0>
  553e1c: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553e21: 8b 00                        	mov	eax, dword ptr [eax]
  553e23: 8b 80 70 09 70 00            	mov	eax, dword ptr [eax + 0x700970]
  553e29: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553e2f: 8b 12                        	mov	edx, dword ptr [edx]
  553e31: 3b 82 f0 04 00 00            	cmp	eax, dword ptr [edx + 0x4f0]
  553e37: 75 0e                        	jne	0x553e47 <CODE+0x152e47>
  553e39: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553e3e: 8b 00                        	mov	eax, dword ptr [eax]
  553e40: 8b d7                        	mov	edx, edi
  553e42: e8 a5 da 00 00               	call	0x5618ec <CODE+0x1608ec>
  553e47: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553e4c: 8b 00                        	mov	eax, dword ptr [eax]
  553e4e: 8b 80 70 09 70 00            	mov	eax, dword ptr [eax + 0x700970]
  553e54: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  553e5a: 8b 12                        	mov	edx, dword ptr [edx]
  553e5c: 3b 82 34 06 00 00            	cmp	eax, dword ptr [edx + 0x634]
  553e62: 0f 85 bf 05 00 00            	jne	0x554427 <CODE+0x153427>
  553e68: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553e6d: 8b 00                        	mov	eax, dword ptr [eax]
  553e6f: 8b d7                        	mov	edx, edi
  553e71: e8 d2 db 00 00               	call	0x561a48 <CODE+0x160a48>
  553e76: e9 ac 05 00 00               	jmp	0x554427 <CODE+0x153427>
  553e7b: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553e80: 8b 00                        	mov	eax, dword ptr [eax]
  553e82: b2 01                        	mov	dl, 0x1
  553e84: 8b 08                        	mov	ecx, dword ptr [eax]
  553e86: ff 51 64                     	call	dword ptr [ecx + 0x64]
  553e89: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553e8e: 8b 00                        	mov	eax, dword ptr [eax]
  553e90: b2 2a                        	mov	dl, 0x2a
  553e92: e8 5d 9e ef ff               	call	0x44dcf4 <CODE+0x4ccf4>
  553e97: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553e9c: 8b 00                        	mov	eax, dword ptr [eax]
  553e9e: 33 d2                        	xor	edx, edx
  553ea0: e8 c7 63 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553ea5: a1 20 9a 56 00               	mov	eax, dword ptr [0x569a20]
  553eaa: 8b 00                        	mov	eax, dword ptr [eax]
  553eac: e8 47 f3 ff ff               	call	0x5531f8 <CODE+0x1521f8>
  553eb1: e9 71 05 00 00               	jmp	0x554427 <CODE+0x153427>
  553eb6: 8a 47 06                     	mov	al, byte ptr [edi + 0x6]
  553eb9: 88 47 4d                     	mov	byte ptr [edi + 0x4d], al
  553ebc: 8a 47 53                     	mov	al, byte ptr [edi + 0x53]
  553ebf: 3c 03                        	cmp	al, 0x3
  553ec1: 74 04                        	je	0x553ec7 <CODE+0x152ec7>
  553ec3: 3c 01                        	cmp	al, 0x1
  553ec5: 75 06                        	jne	0x553ecd <CODE+0x152ecd>
  553ec7: 8a 47 07                     	mov	al, byte ptr [edi + 0x7]
  553eca: 88 47 4c                     	mov	byte ptr [edi + 0x4c], al
  553ecd: 8a 47 53                     	mov	al, byte ptr [edi + 0x53]
  553ed0: 3c 02                        	cmp	al, 0x2
  553ed2: 74 08                        	je	0x553edc <CODE+0x152edc>
  553ed4: 3c 05                        	cmp	al, 0x5
  553ed6: 74 04                        	je	0x553edc <CODE+0x152edc>
  553ed8: 3c 07                        	cmp	al, 0x7
  553eda: 75 06                        	jne	0x553ee2 <CODE+0x152ee2>
  553edc: 8a 47 08                     	mov	al, byte ptr [edi + 0x8]
  553edf: 88 47 4e                     	mov	byte ptr [edi + 0x4e], al
  553ee2: 8a 47 09                     	mov	al, byte ptr [edi + 0x9]
  553ee5: 88 47 58                     	mov	byte ptr [edi + 0x58], al
  553ee8: 8d 4f 48                     	lea	ecx, [edi + 0x48]
  553eeb: b2 06                        	mov	dl, 0x6
  553eed: 8b c7                        	mov	eax, edi
  553eef: e8 60 0a 00 00               	call	0x554954 <CODE+0x153954>
  553ef4: 8a 47 0e                     	mov	al, byte ptr [edi + 0xe]
  553ef7: 88 47 50                     	mov	byte ptr [edi + 0x50], al
  553efa: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  553eff: 8b 00                        	mov	eax, dword ptr [eax]
  553f01: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  553f05: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  553f0b: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f11: 8a 4f 0f                     	mov	cl, byte ptr [edi + 0xf]
  553f14: 88 8c c2 28 10 00 00         	mov	byte ptr [edx + 8*eax + 0x1028], cl
  553f1b: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f21: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f27: 8a 4f 10                     	mov	cl, byte ptr [edi + 0x10]
  553f2a: 88 8c c2 58 20 00 00         	mov	byte ptr [edx + 8*eax + 0x2058], cl
  553f31: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f37: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f3d: 8a 4f 11                     	mov	cl, byte ptr [edi + 0x11]
  553f40: 88 8c c2 88 30 00 00         	mov	byte ptr [edx + 8*eax + 0x3088], cl
  553f47: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f4d: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f53: 8a 4f 13                     	mov	cl, byte ptr [edi + 0x13]
  553f56: 88 8c c2 b8 40 00 00         	mov	byte ptr [edx + 8*eax + 0x40b8], cl
  553f5d: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f63: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f69: 8a 4f 14                     	mov	cl, byte ptr [edi + 0x14]
  553f6c: 88 8c c2 e8 50 00 00         	mov	byte ptr [edx + 8*eax + 0x50e8], cl
  553f73: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f79: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f7f: 8a 4f 15                     	mov	cl, byte ptr [edi + 0x15]
  553f82: 88 8c c2 18 61 00 00         	mov	byte ptr [edx + 8*eax + 0x6118], cl
  553f89: 8a 47 23                     	mov	al, byte ptr [edi + 0x23]
  553f8c: 3c fe                        	cmp	al, -0x2
  553f8e: 73 05                        	jae	0x553f95 <CODE+0x152f95>
  553f90: 88 47 70                     	mov	byte ptr [edi + 0x70], al
  553f93: eb 04                        	jmp	0x553f99 <CODE+0x152f99>
  553f95: c6 47 70 00                  	mov	byte ptr [edi + 0x70], 0x0
  553f99: 8a 47 17                     	mov	al, byte ptr [edi + 0x17]
  553f9c: 88 47 5e                     	mov	byte ptr [edi + 0x5e], al
  553f9f: 8a 47 18                     	mov	al, byte ptr [edi + 0x18]
  553fa2: 88 47 5f                     	mov	byte ptr [edi + 0x5f], al
  553fa5: 8a 47 19                     	mov	al, byte ptr [edi + 0x19]
  553fa8: 88 47 60                     	mov	byte ptr [edi + 0x60], al
  553fab: 8a 47 1a                     	mov	al, byte ptr [edi + 0x1a]
  553fae: 88 47 61                     	mov	byte ptr [edi + 0x61], al
  553fb1: 8a 47 1b                     	mov	al, byte ptr [edi + 0x1b]
  553fb4: 88 47 62                     	mov	byte ptr [edi + 0x62], al
  553fb7: 8a 47 1c                     	mov	al, byte ptr [edi + 0x1c]
  553fba: 88 47 63                     	mov	byte ptr [edi + 0x63], al
  553fbd: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553fc2: 8b 00                        	mov	eax, dword ptr [eax]
  553fc4: e8 07 b5 00 00               	call	0x55f4d0 <CODE+0x15e4d0>
  553fc9: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  553fce: 8b 00                        	mov	eax, dword ptr [eax]
  553fd0: 8b d7                        	mov	edx, edi
  553fd2: e8 d5 1d 00 00               	call	0x555dac <CODE+0x154dac>
  553fd7: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553fdc: 8b 00                        	mov	eax, dword ptr [eax]
  553fde: 83 b8 2c 03 00 00 00         	cmp	dword ptr [eax + 0x32c], 0x0
  553fe5: 0f 84 3c 04 00 00            	je	0x554427 <CODE+0x153427>
  553feb: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553ff0: 8b 00                        	mov	eax, dword ptr [eax]
  553ff2: e8 51 b9 ff ff               	call	0x54f948 <CODE+0x14e948>
  553ff7: e9 2b 04 00 00               	jmp	0x554427 <CODE+0x153427>
  553ffc: 8a 47 06                     	mov	al, byte ptr [edi + 0x6]
  553fff: 88 47 53                     	mov	byte ptr [edi + 0x53], al
  554002: 8a 47 07                     	mov	al, byte ptr [edi + 0x7]
  554005: 88 47 54                     	mov	byte ptr [edi + 0x54], al
  554008: 8a 47 08                     	mov	al, byte ptr [edi + 0x8]
  55400b: 88 47 55                     	mov	byte ptr [edi + 0x55], al
  55400e: 8a 47 09                     	mov	al, byte ptr [edi + 0x9]
  554011: 88 47 4c                     	mov	byte ptr [edi + 0x4c], al
  554014: 8a 47 0a                     	mov	al, byte ptr [edi + 0xa]
  554017: 88 47 4e                     	mov	byte ptr [edi + 0x4e], al
  55401a: 8a 47 0b                     	mov	al, byte ptr [edi + 0xb]
  55401d: 88 47 51                     	mov	byte ptr [edi + 0x51], al
  554020: 8a 47 0c                     	mov	al, byte ptr [edi + 0xc]
  554023: 88 47 52                     	mov	byte ptr [edi + 0x52], al
  554026: 8a 47 0d                     	mov	al, byte ptr [edi + 0xd]
  554029: 88 47 57                     	mov	byte ptr [edi + 0x57], al
  55402c: 8a 47 0e                     	mov	al, byte ptr [edi + 0xe]
  55402f: 88 47 64                     	mov	byte ptr [edi + 0x64], al
  554032: 8a 47 0f                     	mov	al, byte ptr [edi + 0xf]
  554035: 88 47 7b                     	mov	byte ptr [edi + 0x7b], al
  554038: 8a 47 10                     	mov	al, byte ptr [edi + 0x10]
  55403b: 88 47 7c                     	mov	byte ptr [edi + 0x7c], al
  55403e: 8a 47 11                     	mov	al, byte ptr [edi + 0x11]
  554041: 88 47 7d                     	mov	byte ptr [edi + 0x7d], al
  554044: 8a 47 12                     	mov	al, byte ptr [edi + 0x12]
  554047: 88 47 7e                     	mov	byte ptr [edi + 0x7e], al
  55404a: 8a 47 13                     	mov	al, byte ptr [edi + 0x13]
  55404d: 88 47 7f                     	mov	byte ptr [edi + 0x7f], al
  554050: 8a 47 14                     	mov	al, byte ptr [edi + 0x14]
  554053: 88 87 80 00 00 00            	mov	byte ptr [edi + 0x80], al
  554059: 8a 47 15                     	mov	al, byte ptr [edi + 0x15]
  55405c: 88 87 81 00 00 00            	mov	byte ptr [edi + 0x81], al
  554062: 8a 47 16                     	mov	al, byte ptr [edi + 0x16]
  554065: 88 87 82 00 00 00            	mov	byte ptr [edi + 0x82], al
  55406b: 8a 47 17                     	mov	al, byte ptr [edi + 0x17]
  55406e: 88 87 83 00 00 00            	mov	byte ptr [edi + 0x83], al
  554074: 8a 47 18                     	mov	al, byte ptr [edi + 0x18]
  554077: 88 87 84 00 00 00            	mov	byte ptr [edi + 0x84], al
  55407d: 8a 47 19                     	mov	al, byte ptr [edi + 0x19]
  554080: 88 87 85 00 00 00            	mov	byte ptr [edi + 0x85], al
  554086: 8a 47 1a                     	mov	al, byte ptr [edi + 0x1a]
  554089: 88 87 86 00 00 00            	mov	byte ptr [edi + 0x86], al
  55408f: 8a 47 1b                     	mov	al, byte ptr [edi + 0x1b]
  554092: 88 87 87 00 00 00            	mov	byte ptr [edi + 0x87], al
  554098: 8a 47 1c                     	mov	al, byte ptr [edi + 0x1c]
  55409b: 88 47 59                     	mov	byte ptr [edi + 0x59], al
  55409e: 8a 47 1e                     	mov	al, byte ptr [edi + 0x1e]
  5540a1: 88 47 5a                     	mov	byte ptr [edi + 0x5a], al
  5540a4: 8a 47 1f                     	mov	al, byte ptr [edi + 0x1f]
  5540a7: 88 47 5b                     	mov	byte ptr [edi + 0x5b], al
  5540aa: 8a 47 20                     	mov	al, byte ptr [edi + 0x20]
  5540ad: 88 47 5c                     	mov	byte ptr [edi + 0x5c], al
  5540b0: 8a 47 21                     	mov	al, byte ptr [edi + 0x21]
  5540b3: 88 47 5d                     	mov	byte ptr [edi + 0x5d], al
  5540b6: 8a 47 22                     	mov	al, byte ptr [edi + 0x22]
  5540b9: 88 47 65                     	mov	byte ptr [edi + 0x65], al
  5540bc: 80 7f 59 01                  	cmp	byte ptr [edi + 0x59], 0x1
  5540c0: 76 08                        	jbe	0x5540ca <CODE+0x1530ca>
  5540c2: 8a 47 1d                     	mov	al, byte ptr [edi + 0x1d]
  5540c5: 88 47 58                     	mov	byte ptr [edi + 0x58], al
  5540c8: eb 04                        	jmp	0x5540ce <CODE+0x1530ce>
  5540ca: c6 47 58 00                  	mov	byte ptr [edi + 0x58], 0x0
  5540ce: 33 c0                        	xor	eax, eax
  5540d0: 89 47 6c                     	mov	dword ptr [edi + 0x6c], eax
  5540d3: 33 c0                        	xor	eax, eax
  5540d5: a3 64 b3 57 00               	mov	dword ptr [0x57b364], eax
  5540da: c6 05 60 b3 57 00 00         	mov	byte ptr [0x57b360], 0x0
  5540e1: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  5540e6: 8b 00                        	mov	eax, dword ptr [eax]
  5540e8: e8 b7 33 00 00               	call	0x5574a4 <CODE+0x1564a4>
  5540ed: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5540f2: 8b 00                        	mov	eax, dword ptr [eax]
  5540f4: c6 80 4c 09 70 00 01         	mov	byte ptr [eax + 0x70094c], 0x1
  5540fb: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554100: 8b 00                        	mov	eax, dword ptr [eax]
  554102: b1 02                        	mov	cl, 0x2
  554104: b2 06                        	mov	dl, 0x6
  554106: e8 45 0e 00 00               	call	0x554f50 <CODE+0x153f50>
  55410b: e9 17 03 00 00               	jmp	0x554427 <CODE+0x153427>
  554110: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554115: 8b 00                        	mov	eax, dword ptr [eax]
  554117: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  55411d: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  554123: ba 01 00 00 00               	mov	edx, 0x1
  554128: e8 8b d9 ee ff               	call	0x441ab8 <CODE+0x40ab8>
  55412d: ba 0c 45 55 00               	mov	edx, 0x55450c
  554132: e8 dd d8 ee ff               	call	0x441a14 <CODE+0x40a14>
  554137: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55413c: 8b 00                        	mov	eax, dword ptr [eax]
  55413e: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  554142: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  554148: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  55414e: 8d 04 c2                     	lea	eax, [edx + 8*eax]
  554151: 33 d2                        	xor	edx, edx
  554153: 8a d3                        	mov	dl, bl
  554155: 69 d2 06 02 00 00            	imul	edx, edx, 0x206
  55415b: 8b 94 d0 c8 8e ff ff         	mov	edx, dword ptr [eax + 8*edx - 0x7138]
  554162: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554167: 8b 00                        	mov	eax, dword ptr [eax]
  554169: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  55416f: e8 60 ea ee ff               	call	0x442bd4 <CODE+0x41bd4>
  554174: 33 d2                        	xor	edx, edx
  554176: 8a 57 4f                     	mov	dl, byte ptr [edi + 0x4f]
  554179: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55417e: 8b 00                        	mov	eax, dword ptr [eax]
  554180: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  554186: e8 59 ea ee ff               	call	0x442be4 <CODE+0x41be4>
  55418b: 8a 47 06                     	mov	al, byte ptr [edi + 0x6]
  55418e: 40                           	inc	eax
  55418f: 88 47 4f                     	mov	byte ptr [edi + 0x4f], al
  554192: 8b 15 64 97 56 00            	mov	edx, dword ptr [0x569764]
  554198: 8b 12                        	mov	edx, dword ptr [edx]
  55419a: 8b c8                        	mov	ecx, eax
  55419c: 8b c3                        	mov	eax, ebx
  55419e: 92                           	xchg	eax, edx
  55419f: e8 ac 0d 00 00               	call	0x554f50 <CODE+0x153f50>
  5541a4: e9 7e 02 00 00               	jmp	0x554427 <CODE+0x153427>
  5541a9: a1 04 92 56 00               	mov	eax, dword ptr [0x569204]
  5541ae: 8b 00                        	mov	eax, dword ptr [eax]
  5541b0: b9 1e 00 00 00               	mov	ecx, 0x1e
  5541b5: 99                           	cdq
  5541b6: f7 f9                        	idiv	ecx
  5541b8: 40                           	inc	eax
  5541b9: 89 47 68                     	mov	dword ptr [edi + 0x68], eax
  5541bc: a1 04 92 56 00               	mov	eax, dword ptr [0x569204]
  5541c1: 8b 00                        	mov	eax, dword ptr [eax]
  5541c3: b9 1e 00 00 00               	mov	ecx, 0x1e
  5541c8: 99                           	cdq
  5541c9: f7 f9                        	idiv	ecx
  5541cb: 89 15 68 b3 57 00            	mov	dword ptr [0x57b368], edx
  5541d1: ff 05 64 b3 57 00            	inc	dword ptr [0x57b364]
  5541d7: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5541dc: 8b 00                        	mov	eax, dword ptr [eax]
  5541de: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  5541e4: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  5541ea: ba 01 00 00 00               	mov	edx, 0x1
  5541ef: e8 c4 d8 ee ff               	call	0x441ab8 <CODE+0x40ab8>
  5541f4: ba 0c 45 55 00               	mov	edx, 0x55450c
  5541f9: e8 16 d8 ee ff               	call	0x441a14 <CODE+0x40a14>
  5541fe: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554203: 8b 00                        	mov	eax, dword ptr [eax]
  554205: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  55420b: 8b 57 68                     	mov	edx, dword ptr [edi + 0x68]
  55420e: e8 c1 e9 ee ff               	call	0x442bd4 <CODE+0x41bd4>
  554213: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554218: 8b 00                        	mov	eax, dword ptr [eax]
  55421a: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  554220: 8b 15 64 b3 57 00            	mov	edx, dword ptr [0x57b364]
  554226: e8 b9 e9 ee ff               	call	0x442be4 <CODE+0x41be4>
  55422b: a1 64 b3 57 00               	mov	eax, dword ptr [0x57b364]
  554230: 3b 47 68                     	cmp	eax, dword ptr [edi + 0x68]
  554233: 75 1c                        	jne	0x554251 <CODE+0x153251>
  554235: c6 05 59 b3 57 00 40         	mov	byte ptr [0x57b359], 0x40
  55423c: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554241: 8b 00                        	mov	eax, dword ptr [eax]
  554243: b1 01                        	mov	cl, 0x1
  554245: b2 41                        	mov	dl, 0x41
  554247: e8 04 0d 00 00               	call	0x554f50 <CODE+0x153f50>
  55424c: e9 d6 01 00 00               	jmp	0x554427 <CODE+0x153427>
  554251: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554256: 8b 00                        	mov	eax, dword ptr [eax]
  554258: b1 01                        	mov	cl, 0x1
  55425a: b2 40                        	mov	dl, 0x40
  55425c: e8 ef 0c 00 00               	call	0x554f50 <CODE+0x153f50>
  554261: e9 c1 01 00 00               	jmp	0x554427 <CODE+0x153427>
  554266: a1 04 92 56 00               	mov	eax, dword ptr [0x569204]
  55426b: 8b 00                        	mov	eax, dword ptr [eax]
  55426d: b9 1e 00 00 00               	mov	ecx, 0x1e
  554272: 99                           	cdq
  554273: f7 f9                        	idiv	ecx
  554275: 40                           	inc	eax
  554276: 89 47 68                     	mov	dword ptr [edi + 0x68], eax
  554279: a1 04 92 56 00               	mov	eax, dword ptr [0x569204]
  55427e: 8b 00                        	mov	eax, dword ptr [eax]
  554280: b9 1e 00 00 00               	mov	ecx, 0x1e
  554285: 99                           	cdq
  554286: f7 f9                        	idiv	ecx
  554288: 89 15 68 b3 57 00            	mov	dword ptr [0x57b368], edx
  55428e: ff 05 64 b3 57 00            	inc	dword ptr [0x57b364]
  554294: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554299: 8b 00                        	mov	eax, dword ptr [eax]
  55429b: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  5542a1: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  5542a7: ba 01 00 00 00               	mov	edx, 0x1
  5542ac: e8 07 d8 ee ff               	call	0x441ab8 <CODE+0x40ab8>
  5542b1: ba 0c 45 55 00               	mov	edx, 0x55450c
  5542b6: e8 59 d7 ee ff               	call	0x441a14 <CODE+0x40a14>
  5542bb: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5542c0: 8b 00                        	mov	eax, dword ptr [eax]
  5542c2: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  5542c8: 8b 57 68                     	mov	edx, dword ptr [edi + 0x68]
  5542cb: e8 04 e9 ee ff               	call	0x442bd4 <CODE+0x41bd4>
  5542d0: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5542d5: 8b 00                        	mov	eax, dword ptr [eax]
  5542d7: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  5542dd: 8b 15 64 b3 57 00            	mov	edx, dword ptr [0x57b364]
  5542e3: e8 fc e8 ee ff               	call	0x442be4 <CODE+0x41be4>
  5542e8: a1 64 b3 57 00               	mov	eax, dword ptr [0x57b364]
  5542ed: 3b 47 68                     	cmp	eax, dword ptr [edi + 0x68]
  5542f0: 75 1c                        	jne	0x55430e <CODE+0x15330e>
  5542f2: c6 05 59 b3 57 00 42         	mov	byte ptr [0x57b359], 0x42
  5542f9: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  5542fe: 8b 00                        	mov	eax, dword ptr [eax]
  554300: b1 01                        	mov	cl, 0x1
  554302: b2 41                        	mov	dl, 0x41
  554304: e8 47 0c 00 00               	call	0x554f50 <CODE+0x153f50>
  554309: e9 19 01 00 00               	jmp	0x554427 <CODE+0x153427>
  55430e: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554313: 8b 00                        	mov	eax, dword ptr [eax]
  554315: b1 01                        	mov	cl, 0x1
  554317: b2 42                        	mov	dl, 0x42
  554319: e8 32 0c 00 00               	call	0x554f50 <CODE+0x153f50>
  55431e: e9 04 01 00 00               	jmp	0x554427 <CODE+0x153427>
  554323: 33 c0                        	xor	eax, eax
  554325: a3 64 b3 57 00               	mov	dword ptr [0x57b364], eax
  55432a: 66 c7 05 6c b3 57 00 00 00   	mov	word ptr [0x57b36c], 0x0
  554333: 80 7f 07 aa                  	cmp	byte ptr [edi + 0x7], -0x56
  554337: 75 48                        	jne	0x554381 <CODE+0x153381>
  554339: c6 05 60 b3 57 00 00         	mov	byte ptr [0x57b360], 0x0
  554340: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554345: 8b 00                        	mov	eax, dword ptr [eax]
  554347: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  55434d: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  554353: ba 01 00 00 00               	mov	edx, 0x1
  554358: e8 5b d7 ee ff               	call	0x441ab8 <CODE+0x40ab8>
  55435d: ba 20 45 55 00               	mov	edx, 0x554520
  554362: e8 ad d6 ee ff               	call	0x441a14 <CODE+0x40a14>
  554367: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55436c: 8b 00                        	mov	eax, dword ptr [eax]
  55436e: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  554374: 8b 10                        	mov	edx, dword ptr [eax]
  554376: ff 92 88 00 00 00            	call	dword ptr [edx + 0x88]
  55437c: e9 a6 00 00 00               	jmp	0x554427 <CODE+0x153427>
  554381: 80 3d 60 b3 57 00 02         	cmp	byte ptr [0x57b360], 0x2
  554388: 76 1d                        	jbe	0x5543a7 <CODE+0x1533a7>
  55438a: c6 05 60 b3 57 00 00         	mov	byte ptr [0x57b360], 0x0
  554391: a1 44 97 56 00               	mov	eax, dword ptr [0x569744]
  554396: 8b 00                        	mov	eax, dword ptr [eax]
  554398: ba 44 45 55 00               	mov	edx, 0x554544
  55439d: e8 96 77 ff ff               	call	0x54bb38 <CODE+0x14ab38>
  5543a2: e9 80 00 00 00               	jmp	0x554427 <CODE+0x153427>
  5543a7: fe 05 60 b3 57 00            	inc	byte ptr [0x57b360]
  5543ad: 8d 55 dc                     	lea	edx, [ebp - 0x24]
  5543b0: 33 c0                        	xor	eax, eax
  5543b2: a0 60 b3 57 00               	mov	al, byte ptr [0x57b360]
  5543b7: e8 2c 5e eb ff               	call	0x40a1e8 <CODE+0x91e8>
  5543bc: 8b 4d dc                     	mov	ecx, dword ptr [ebp - 0x24]
  5543bf: 8d 45 e0                     	lea	eax, [ebp - 0x20]
  5543c2: ba 70 45 55 00               	mov	edx, 0x554570
  5543c7: e8 74 0f eb ff               	call	0x405340 <CODE+0x4340>
  5543cc: 8b 45 e0                     	mov	eax, dword ptr [ebp - 0x20]
  5543cf: 50                           	push	eax
  5543d0: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5543d5: 8b 00                        	mov	eax, dword ptr [eax]
  5543d7: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  5543dd: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  5543e3: ba 01 00 00 00               	mov	edx, 0x1
  5543e8: e8 cb d6 ee ff               	call	0x441ab8 <CODE+0x40ab8>
  5543ed: 5a                           	pop	edx
  5543ee: e8 21 d6 ee ff               	call	0x441a14 <CODE+0x40a14>
  5543f3: 80 3d 59 b3 57 00 40         	cmp	byte ptr [0x57b359], 0x40
  5543fa: 75 12                        	jne	0x55440e <CODE+0x15340e>
  5543fc: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554401: 8b 00                        	mov	eax, dword ptr [eax]
  554403: b1 01                        	mov	cl, 0x1
  554405: b2 40                        	mov	dl, 0x40
  554407: e8 44 0b 00 00               	call	0x554f50 <CODE+0x153f50>
  55440c: eb 19                        	jmp	0x554427 <CODE+0x153427>
  55440e: 80 3d 59 b3 57 00 42         	cmp	byte ptr [0x57b359], 0x42
  554415: 75 10                        	jne	0x554427 <CODE+0x153427>
  554417: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  55441c: 8b 00                        	mov	eax, dword ptr [eax]
  55441e: b1 01                        	mov	cl, 0x1
  554420: b2 42                        	mov	dl, 0x42
  554422: e8 29 0b 00 00               	call	0x554f50 <CODE+0x153f50>
  554427: 33 c0                        	xor	eax, eax
  554429: 5a                           	pop	edx
  55442a: 59                           	pop	ecx
  55442b: 59                           	pop	ecx
  55442c: 64 89 10                     	mov	dword ptr fs:[eax], edx
  55442f: 68 49 44 55 00               	push	0x554449
  554434: 8d 45 dc                     	lea	eax, [ebp - 0x24]
  554437: ba 09 00 00 00               	mov	edx, 0x9
  55443c: e8 17 0c eb ff               	call	0x405058 <CODE+0x4058>
  554441: c3                           	ret
  554442: e9 8d 04 eb ff               	jmp	0x4048d4 <CODE+0x38d4>
  554447: eb eb                        	jmp	0x554434 <CODE+0x153434>
  554449: 5f                           	pop	edi
  55444a: 5e                           	pop	esi
  55444b: 5b                           	pop	ebx
  55444c: 8b e5                        	mov	esp, ebp
  55444e: 5d                           	pop	ebp
  55444f: c3                           	ret
  554450: ff ff                        	<unknown>
  554452: ff ff                        	<unknown>
  554454: 1d 00 00 00 44               	sbb	eax, 0x44000000
  554459: 53                           	push	ebx
  55445a: 50                           	push	eax
  55445b: 20 66 69                     	and	byte ptr [esi + 0x69], ah
  55445e: 6c                           	insb	byte ptr es:[edi], dx
  55445f: 74 65                        	je	0x5544c6 <CODE+0x1534c6>
  554461: 72 3a                        	jb	0x55449d <CODE+0x15349d>
  554463: 20 4e 6f                     	and	byte ptr [esi + 0x6f], cl
  554466: 20 66 69                     	and	byte ptr [esi + 0x69], ah
  554469: 6c                           	insb	byte ptr es:[edi], dx
  55446a: 65 6e                        	outsb	dx, byte ptr gs:[esi]
  55446c: 61                           	popal
  55446d: 6d                           	insd	dword ptr es:[edi], dx
  55446e: 65 20 66 6f                  	and	byte ptr gs:[esi + 0x6f], ah
  554472: 75 6e                        	jne	0x5544e2 <CODE+0x1534e2>
  554474: 64 00 00                     	add	byte ptr fs:[eax], al
  554477: 00 ff                        	add	bh, bh
  554479: ff ff                        	<unknown>
  55447b: ff 04 00                     	inc	dword ptr [eax + eax]
  55447e: 00 00                        	add	byte ptr [eax], al
  554480: 2e 64 73 70                  	jae	0x5544f4 <CODE+0x1534f4>
  554484: 00 00                        	add	byte ptr [eax], al
  554486: 00 00                        	add	byte ptr [eax], al
  554488: ff ff                        	<unknown>
  55448a: ff ff                        	<unknown>
  55448c: 0c 00                        	or	al, 0x0
  55448e: 00 00                        	add	byte ptr [eax], al
  554490: 44                           	inc	esp
  554491: 53                           	push	ebx
  554492: 50                           	push	eax
  554493: 20 66 69                     	and	byte ptr [esi + 0x69], ah
  554496: 6c                           	insb	byte ptr es:[edi], dx
  554497: 74 65                        	je	0x5544fe <CODE+0x1534fe>
  554499: 72 3a                        	jb	0x5544d5 <CODE+0x1534d5>
  55449b: 20 00                        	and	byte ptr [eax], al
  55449d: 00 00                        	add	byte ptr [eax], al
  55449f: 00 ff                        	add	bh, bh
  5544a1: ff ff                        	<unknown>
  5544a3: ff 03                        	inc	dword ptr [ebx]
  5544a5: 00 00                        	add	byte ptr [eax], al
  5544a7: 00 2e                        	add	byte ptr [esi], ch
  5544a9: 2e 2e 00 ff                  	add	bh, bh
  5544ad: ff ff                        	<unknown>
  5544af: ff 0e                        	dec	dword ptr [esi]
  5544b1: 00 00                        	add	byte ptr [eax], al
  5544b3: 00 52 65                     	add	byte ptr [edx + 0x65], dl
  5544b6: 6d                           	insd	dword ptr es:[edi], dx
  5544b7: 6f                           	outsd	dx, dword ptr [esi]
  5544b8: 74 65                        	je	0x55451f <CODE+0x15351f>
  5544ba: 20 63 68                     	and	byte ptr [ebx + 0x68], ah
  5544bd: 61                           	popal
  5544be: 6e                           	outsb	dx, byte ptr [esi]
  5544bf: 67 65 64 00 00               	add	byte ptr fs:[bx + si], al
  5544c4: ff ff                        	<unknown>
  5544c6: ff ff                        	<unknown>
  5544c8: 0f 00 00                     	sldt	word ptr [eax]
  5544cb: 00 4e 6f                     	add	byte ptr [esi + 0x6f], cl
  5544ce: 20 70 61                     	and	byte ptr [eax + 0x61], dh
  5544d1: 73 73                        	jae	0x554546 <CODE+0x153546>
  5544d3: 77 6f                        	ja	0x554544 <CODE+0x153544>
  5544d5: 72 64                        	jb	0x55453b <CODE+0x15353b>
  5544d7: 20 73 65                     	and	byte ptr [ebx + 0x65], dh
  5544da: 74 00                        	je	0x5544dc <CODE+0x1534dc>
  5544dc: ff ff                        	<unknown>
  5544de: ff ff                        	<unknown>
  5544e0: 1c 00                        	sbb	al, 0x0
  5544e2: 00 00                        	add	byte ptr [eax], al
  5544e4: 50                           	push	eax
  5544e5: 61                           	popal
  5544e6: 73 73                        	jae	0x55455b <CODE+0x15355b>
  5544e8: 77 6f                        	ja	0x554559 <CODE+0x153559>
  5544ea: 72 64                        	jb	0x554550 <CODE+0x153550>
  5544ec: 20 73 75                     	and	byte ptr [ebx + 0x75], dh
  5544ef: 63 63 65                     	arpl	word ptr [ebx + 0x65], sp
  5544f2: 73 66                        	jae	0x55455a <CODE+0x15355a>
  5544f4: 75 6c                        	jne	0x554562 <CODE+0x153562>
  5544f6: 6c                           	insb	byte ptr es:[edi], dx
  5544f7: 79 20                        	jns	0x554519 <CODE+0x153519>
  5544f9: 63 68 61                     	arpl	word ptr [eax + 0x61], bp
  5544fc: 6e                           	outsb	dx, byte ptr [esi]
  5544fd: 67 65 64 00 00               	add	byte ptr fs:[bx + si], al
  554502: 00 00                        	add	byte ptr [eax], al
  554504: ff ff                        	<unknown>
  554506: ff ff                        	<unknown>
  554508: 0b 00                        	or	eax, dword ptr [eax]
  55450a: 00 00                        	add	byte ptr [eax], al
  55450c: 55                           	push	ebp
  55450d: 70 64                        	jo	0x554573 <CODE+0x153573>
  55450f: 61                           	popal
  554510: 74 69                        	je	0x55457b <CODE+0x15357b>
  554512: 6e                           	outsb	dx, byte ptr [esi]
  554513: 67 2e 2e 2e 00 ff            	addr16		add	bh, bh
  554519: ff ff                        	<unknown>
  55451b: ff 18                        	call	[eax]
  55451d: 00 00                        	add	byte ptr [eax], al
  55451f: 00 46 69                     	add	byte ptr [esi + 0x69], al

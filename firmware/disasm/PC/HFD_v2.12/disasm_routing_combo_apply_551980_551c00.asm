
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  551980: 74 69                        	je	0x5519eb <CODE+0x1509eb>
  551982: 6e                           	outsb	dx, byte ptr [esi]
  551983: 67 73 00                     	addr16		jae	0x551986 <CODE+0x150986>
  551986: 00 00                        	add	byte ptr [eax], al
  551988: 53                           	push	ebx
  551989: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  55198f: 8b 88 14 03 00 00            	mov	ecx, dword ptr [eax + 0x314]
  551995: 8a 89 18 02 00 00            	mov	cl, byte ptr [ecx + 0x218]
  55199b: 8b 1a                        	mov	ebx, dword ptr [edx]
  55199d: 88 4b 5e                     	mov	byte ptr [ebx + 0x5e], cl
  5519a0: 8b 88 18 03 00 00            	mov	ecx, dword ptr [eax + 0x318]
  5519a6: 8a 89 18 02 00 00            	mov	cl, byte ptr [ecx + 0x218]
  5519ac: 8b 1a                        	mov	ebx, dword ptr [edx]
  5519ae: 88 4b 5f                     	mov	byte ptr [ebx + 0x5f], cl
  5519b1: 8b 88 1c 03 00 00            	mov	ecx, dword ptr [eax + 0x31c]
  5519b7: 8a 89 18 02 00 00            	mov	cl, byte ptr [ecx + 0x218]
  5519bd: 8b 1a                        	mov	ebx, dword ptr [edx]
  5519bf: 88 4b 60                     	mov	byte ptr [ebx + 0x60], cl
  5519c2: 8b 88 20 03 00 00            	mov	ecx, dword ptr [eax + 0x320]
  5519c8: 8a 89 18 02 00 00            	mov	cl, byte ptr [ecx + 0x218]
  5519ce: 8b 1a                        	mov	ebx, dword ptr [edx]
  5519d0: 88 4b 61                     	mov	byte ptr [ebx + 0x61], cl
  5519d3: 8b 88 24 03 00 00            	mov	ecx, dword ptr [eax + 0x324]
  5519d9: 8a 89 18 02 00 00            	mov	cl, byte ptr [ecx + 0x218]
  5519df: 8b 1a                        	mov	ebx, dword ptr [edx]
  5519e1: 88 4b 62                     	mov	byte ptr [ebx + 0x62], cl
  5519e4: 8b 80 28 03 00 00            	mov	eax, dword ptr [eax + 0x328]
  5519ea: 8a 80 18 02 00 00            	mov	al, byte ptr [eax + 0x218]
  5519f0: 8b 0a                        	mov	ecx, dword ptr [edx]
  5519f2: 88 41 63                     	mov	byte ptr [ecx + 0x63], al
  5519f5: 8b 02                        	mov	eax, dword ptr [edx]
  5519f7: 80 78 05 06                  	cmp	byte ptr [eax + 0x5], 0x6
  5519fb: 74 0e                        	je	0x551a0b <CODE+0x150a0b>
  5519fd: 33 c9                        	xor	ecx, ecx
  5519ff: b2 05                        	mov	dl, 0x5
  551a01: a1 28 b1 56 00               	mov	eax, dword ptr [0x56b128]
  551a06: e8 45 35 00 00               	call	0x554f50 <CODE+0x153f50>
  551a0b: 5b                           	pop	ebx
  551a0c: c3                           	ret
  551a0d: 8d 40 00                     	lea	eax, [eax]
  551a10: 8b 0d fc 98 56 00            	mov	ecx, dword ptr [0x5698fc]
  551a16: 8b 09                        	mov	ecx, dword ptr [ecx]
  551a18: 80 b9 75 09 70 00 01         	cmp	byte ptr [ecx + 0x700975], 0x1
  551a1f: 0f 84 2c 01 00 00            	je	0x551b51 <CODE+0x150b51>
  551a25: 8b ca                        	mov	ecx, edx
  551a27: 3b 88 30 03 00 00            	cmp	ecx, dword ptr [eax + 0x330]
  551a2d: 0f 85 8d 00 00 00            	jne	0x551ac0 <CODE+0x150ac0>
  551a33: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  551a38: 8b 00                        	mov	eax, dword ptr [eax]
  551a3a: c6 80 75 09 70 00 02         	mov	byte ptr [eax + 0x700975], 0x2
  551a41: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  551a46: 8b 00                        	mov	eax, dword ptr [eax]
  551a48: c6 80 74 09 70 00 03         	mov	byte ptr [eax + 0x700974], 0x3
  551a4f: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551a54: 8b 00                        	mov	eax, dword ptr [eax]
  551a56: 80 78 53 01                  	cmp	byte ptr [eax + 0x53], 0x1
  551a5a: 0f 94 c0                     	sete	al
  551a5d: 3c 01                        	cmp	al, 0x1
  551a5f: 75 36                        	jne	0x551a97 <CODE+0x150a97>
  551a61: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551a66: 8b 00                        	mov	eax, dword ptr [eax]
  551a68: 80 78 54 02                  	cmp	byte ptr [eax + 0x54], 0x2
  551a6c: 0f 97 c0                     	seta	al
  551a6f: 3c 01                        	cmp	al, 0x1
  551a71: 74 3a                        	je	0x551aad <CODE+0x150aad>
  551a73: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551a78: 8b 00                        	mov	eax, dword ptr [eax]
  551a7a: 80 78 54 02                  	cmp	byte ptr [eax + 0x54], 0x2
  551a7e: 0f 94 c0                     	sete	al
  551a81: 3c 01                        	cmp	al, 0x1
  551a83: 75 12                        	jne	0x551a97 <CODE+0x150a97>
  551a85: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551a8a: 8b 00                        	mov	eax, dword ptr [eax]
  551a8c: 80 78 55 05                  	cmp	byte ptr [eax + 0x55], 0x5
  551a90: 0f 97 c0                     	seta	al
  551a93: 3c 01                        	cmp	al, 0x1
  551a95: 74 16                        	je	0x551aad <CODE+0x150aad>
  551a97: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551a9c: 8b 00                        	mov	eax, dword ptr [eax]
  551a9e: 80 78 53 01                  	cmp	byte ptr [eax + 0x53], 0x1
  551aa2: 0f 95 c0                     	setne	al
  551aa5: 3c 01                        	cmp	al, 0x1
  551aa7: 0f 85 b2 00 00 00            	jne	0x551b5f <CODE+0x150b5f>
  551aad: b1 01                        	mov	cl, 0x1
  551aaf: b2 04                        	mov	dl, 0x4
  551ab1: a1 28 b1 56 00               	mov	eax, dword ptr [0x56b128]
  551ab6: e8 95 34 00 00               	call	0x554f50 <CODE+0x153f50>
  551abb: e9 9f 00 00 00               	jmp	0x551b5f <CODE+0x150b5f>
  551ac0: 3b 88 34 03 00 00            	cmp	ecx, dword ptr [eax + 0x334]
  551ac6: 0f 85 93 00 00 00            	jne	0x551b5f <CODE+0x150b5f>
  551acc: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  551ad1: 8b 00                        	mov	eax, dword ptr [eax]
  551ad3: c6 80 75 09 70 00 02         	mov	byte ptr [eax + 0x700975], 0x2
  551ada: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  551adf: 8b 00                        	mov	eax, dword ptr [eax]
  551ae1: c6 80 74 09 70 00 04         	mov	byte ptr [eax + 0x700974], 0x4
  551ae8: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551aed: 8b 00                        	mov	eax, dword ptr [eax]
  551aef: 80 78 53 01                  	cmp	byte ptr [eax + 0x53], 0x1
  551af3: 0f 94 c0                     	sete	al
  551af6: 3c 01                        	cmp	al, 0x1
  551af8: 75 36                        	jne	0x551b30 <CODE+0x150b30>
  551afa: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551aff: 8b 00                        	mov	eax, dword ptr [eax]
  551b01: 80 78 54 02                  	cmp	byte ptr [eax + 0x54], 0x2
  551b05: 0f 97 c0                     	seta	al
  551b08: 3c 01                        	cmp	al, 0x1
  551b0a: 74 36                        	je	0x551b42 <CODE+0x150b42>
  551b0c: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551b11: 8b 00                        	mov	eax, dword ptr [eax]
  551b13: 80 78 54 02                  	cmp	byte ptr [eax + 0x54], 0x2
  551b17: 0f 94 c0                     	sete	al
  551b1a: 3c 01                        	cmp	al, 0x1
  551b1c: 75 12                        	jne	0x551b30 <CODE+0x150b30>
  551b1e: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551b23: 8b 00                        	mov	eax, dword ptr [eax]
  551b25: 80 78 55 05                  	cmp	byte ptr [eax + 0x55], 0x5
  551b29: 0f 97 c0                     	seta	al
  551b2c: 3c 01                        	cmp	al, 0x1
  551b2e: 74 12                        	je	0x551b42 <CODE+0x150b42>
  551b30: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  551b35: 8b 00                        	mov	eax, dword ptr [eax]
  551b37: 80 78 53 01                  	cmp	byte ptr [eax + 0x53], 0x1
  551b3b: 0f 95 c0                     	setne	al
  551b3e: 3c 01                        	cmp	al, 0x1
  551b40: 75 1d                        	jne	0x551b5f <CODE+0x150b5f>
  551b42: b1 01                        	mov	cl, 0x1
  551b44: b2 04                        	mov	dl, 0x4
  551b46: a1 28 b1 56 00               	mov	eax, dword ptr [0x56b128]
  551b4b: e8 00 34 00 00               	call	0x554f50 <CODE+0x153f50>
  551b50: c3                           	ret
  551b51: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  551b56: 8b 00                        	mov	eax, dword ptr [eax]
  551b58: c6 80 75 09 70 00 00         	mov	byte ptr [eax + 0x700975], 0x0
  551b5f: c3                           	ret
  551b60: 53                           	push	ebx
  551b61: 8b d8                        	mov	ebx, eax
  551b63: 8b 83 50 03 00 00            	mov	eax, dword ptr [ebx + 0x350]
  551b69: 8b 10                        	mov	edx, dword ptr [eax]
  551b6b: ff 92 c8 00 00 00            	call	dword ptr [edx + 0xc8]
  551b71: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  551b77: 8b 12                        	mov	edx, dword ptr [edx]
  551b79: 88 42 70                     	mov	byte ptr [edx + 0x70], al
  551b7c: 33 c9                        	xor	ecx, ecx
  551b7e: b2 05                        	mov	dl, 0x5
  551b80: a1 28 b1 56 00               	mov	eax, dword ptr [0x56b128]
  551b85: e8 c6 33 00 00               	call	0x554f50 <CODE+0x153f50>
  551b8a: 5b                           	pop	ebx
  551b8b: c3                           	ret
  551b8c: 55                           	push	ebp
  551b8d: 8b ec                        	mov	ebp, esp
  551b8f: 33 c0                        	xor	eax, eax
  551b91: 55                           	push	ebp
  551b92: 68 b1 1b 55 00               	push	0x551bb1
  551b97: 64 ff 30                     	push	dword ptr fs:[eax]
  551b9a: 64 89 20                     	mov	dword ptr fs:[eax], esp
  551b9d: ff 05 4c b1 56 00            	inc	dword ptr [0x56b14c]
  551ba3: 33 c0                        	xor	eax, eax
  551ba5: 5a                           	pop	edx
  551ba6: 59                           	pop	ecx
  551ba7: 59                           	pop	ecx
  551ba8: 64 89 10                     	mov	dword ptr fs:[eax], edx
  551bab: 68 b8 1b 55 00               	push	0x551bb8
  551bb0: c3                           	ret
  551bb1: e9 1e 2d eb ff               	jmp	0x4048d4 <CODE+0x38d4>
  551bb6: eb f8                        	jmp	0x551bb0 <CODE+0x150bb0>
  551bb8: 5d                           	pop	ebp
  551bb9: c3                           	ret
  551bba: 8b c0                        	mov	eax, eax
  551bbc: 83 2d 4c b1 56 00 01         	sub	dword ptr [0x56b14c], 0x1
  551bc3: c3                           	ret
  551bc4: 10 1c 55 00 00 00 00         	adc	byte ptr [2*edx], bl
		...
  551bd3: 00 d8                        	add	al, bl
  551bd5: 1d 55 00 00 00               	sbb	eax, 0x55
  551bda: 00 00                        	add	byte ptr [eax], al
  551bdc: 04 1d                        	add	al, 0x1d
  551bde: 55                           	push	ebp
  551bdf: 00 c2                        	add	dl, al
  551be1: 1d 55 00 ca 1d               	sbb	eax, 0x1dca0055
  551be6: 55                           	push	ebp
  551be7: 00 08                        	add	byte ptr [eax], cl
  551be9: 03 00                        	add	eax, dword ptr [eax]
  551beb: 00 58 01                     	add	byte ptr [eax + 0x1], bl
  551bee: 47                           	inc	edi
  551bef: 00 24 4b                     	add	byte ptr [ebx + 2*ecx], ah
  551bf2: 42                           	inc	edx
  551bf3: 00 fc                        	add	ah, bh
  551bf5: 2e 47                        	inc	edi
  551bf7: 00 b0 30 47 00 dc            	add	byte ptr [eax - 0x23ffb8d0], dh
  551bfd: 43                           	inc	ebx
  551bfe: 40                           	inc	eax
  551bff: 00 1c 55 47 00 10 41         	add	byte ptr [2*edx + 0x41100047], bl
